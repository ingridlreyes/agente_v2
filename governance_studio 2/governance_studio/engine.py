from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Lock, BoundedSemaphore
import base64
import json
import re
import shutil
import time
from zipfile import ZipFile, ZIP_DEFLATED
from . import prompts
from .models import Artifact, Answer, Route, Source, Theme, Memory, Section, ConsultingReview
from .providers import ResponsesModel, Knowledge
from .demo import DemoModel
from .quality import review
from .renderers import render
from .store import Store, uid


class BusyError(RuntimeError):
    pass


class Engine:
    def __init__(self, settings, model=None):
        self.settings = settings
        self.store = Store(settings.data_dir)
        self.model = model or (DemoModel() if settings.mode == "demo" else ResponsesModel(settings))
        self.knowledge = Knowledge(self.store, settings)
        self.pool = ThreadPoolExecutor(max_workers=settings.workers,thread_name_prefix="document")
        self.capacity = BoundedSemaphore(settings.max_pending)
        self.guard = Lock()
        self.locks = {}
        self.store.recover_jobs()

    @contextmanager
    def lock(self, key):
        with self.guard:
            lock = self.locks.setdefault(key, Lock())
        with lock:
            yield

    def close(self):
        self.pool.shutdown(wait=True)

    def context(self, p, cid, message):
        conv = self.store.conversation(p,cid)
        history = self.store.messages(p,cid)
        attachments = [r for r in self.store.chunks(p,cid) if r["scope"]=="conversation"]
        attachment_context = []
        seen = set()
        for row in attachments:
            if row["title"] not in seen:
                seen.add(row["title"])
                attachment_context.append({"title":row["title"],"preview_untrusted":row["content"][:400]})
        # Presupuesto de contexto. El historial completo sigue guardado en SQLite.
        remaining, selected = 26000, []
        for m in reversed(history):
            if len(m["content"]) > remaining:
                break
            selected.append(m)
            remaining -= len(m["content"])
        return {"message":message,"history":list(reversed(selected)),"memory":conv["memory"],
                "theme":conv["theme"],"conversation_theme":conv["theme"],"artifacts":self.store.list_versions(p,cid)[:10],"attachments":attachment_context[:15]}

    def chat(self, p, cid, req):
        with self.lock("chat:"+cid):
            context = self.context(p,cid,req.message)
            context.update(requested_formats=req.formats,artifact_id=req.artifact_id)
            start = time.perf_counter()
            route, usage = self.model.generate(Route,prompts.ROUTE,context,role="router")
            self.store.event(p,"route",{"intent":route.intent,"elapsed_ms":round((time.perf_counter()-start)*1000),**usage})
            self.store.add_message(p,cid,"user",req.message)
            if route.intent == "out_of_scope" or route.domain == "outside":
                text = "Puedo ayudarte con gobierno de datos y gobierno de inteligencia artificial. Relaciona tu consulta con esos temas para que pueda apoyarte."
                self.store.add_message(p,cid,"assistant",text)
                return {"type":"answer","text":text,"sources":[],"mode":self.settings.mode}
            if route.intent == "clarify":
                text = route.clarification or "Indica el objetivo y el formato del entregable que necesitas."
                self.store.add_message(p,cid,"assistant",text)
                return {"type":"clarify","text":text,"mode":self.settings.mode}
            retrieval_start=time.perf_counter()
            sources = self.knowledge.retrieve(p,cid,route.brief + " " + req.message)
            self.store.event(p,"retrieval",{"elapsed_ms":round((time.perf_counter()-retrieval_start)*1000),"sources":len(sources)})
            context["sources"] = [s.model_dump() for s in sources]
            if route.intent == "answer":
                answer, usage = self.model.generate(Answer,prompts.ANSWER,context)
                known = {s.id for s in sources}
                inline = set(re.findall(r"\[([A-Za-z0-9_-]{3,80})\]",answer.text))
                if (set(answer.source_ids)|inline)-known:
                    raise ValueError("La respuesta incluyó fuentes inexistentes")
                self.store.add_message(p,cid,"assistant",answer.text)
                self.store.update_memory(p,cid,answer.memory.model_dump())
                self.store.event(p,"answer",usage)
                return {"type":"answer","text":answer.text,"sources":[s.model_dump(exclude={"text"}) for s in sources if s.id in answer.source_ids],"mode":self.settings.mode}
            previous = None
            if route.intent == "revise":
                aid = req.artifact_id or route.artifact_id
                if not aid:
                    return {"type":"clarify","text":"Indica qué entregable quieres modificar.","mode":self.settings.mode}
                previous = self.store.version(p,aid)
                if previous["conversation"] != cid:
                    raise KeyError("Entregable no encontrado en esta conversación")
            formats = req.formats or route.formats or (previous["formats"] if previous else ["docx"])
            context.update(brief=route.brief,previous=previous["spec"] if previous else None,
                           target_pages=route.target_pages,long_form=bool(route.target_pages and route.target_pages>=16 and not previous))
            if previous:
                # Conservar las fuentes del documento anterior para no romper sus referencias.
                merged = {s["id"]:s for s in previous["sources"]}
                merged.update({s.id:s.model_dump() for s in sources})
                context["sources"] = list(merged.values())
                context["theme"] = previous["spec"]["theme"]
            jid = self.submit(p,cid,context,formats,previous)
            label = ("Prepararé el caso ficticio de demostración de proveedores. Conecta Azure para generar contenido según tu petición." if self.settings.mode=="demo" else "Estoy preparando el entregable. Puedes consultar el avance y descargar la versión cuando termine.")
            self.store.add_message(p,cid,"assistant",label+" Trabajo "+jid)
            return {"type":"job","job_id":jid,"text":label,"mode":self.settings.mode}

    def submit(self, p, cid, context, formats, previous=None, spec=None):
        if not self.capacity.acquire(blocking=False):
            raise BusyError("La cola está llena. Intenta nuevamente cuando termine un trabajo.")
        try:
            payload = {"message":context.get("message",""),"formats":formats,"previous_version":previous["version"] if previous else None}
            jid = self.store.new_job(p,cid,payload)
            self.pool.submit(self._work,p,cid,jid,context,formats,previous,spec)
            return jid
        except Exception:
            self.capacity.release()
            raise

    def _work(self,p,cid,jid,context,formats,previous,spec):
        start = time.perf_counter()
        aid = previous["artifact"] if previous else uid()
        directory = None
        published = False
        try:
            with self.lock("artifact:"+aid):
                if previous and self.store.version(p,aid)["version"] != previous["version"]:
                    raise ValueError("Hay una versión más reciente. Repite la modificación sobre ella.")
                self.store.job_update(jid,"running","Diseñando contenido y estructura")
                metrics = {}
                model_calls = []
                semantic = None
                if spec is None:
                    images = []
                    logo_id = context.get("conversation_theme",{}).get("logo_id") or context.get("theme",{}).get("logo_id")
                    if logo_id:
                        asset = self.store.asset(p,cid,logo_id)
                        images = ["data:image/png;base64,"+base64.b64encode(Path(asset["path"]).read_bytes()).decode()]
                    spec, metrics = self.model.generate(Artifact,prompts.WRITE,context,images=images)
                    model_calls.append({"stage":"document",**metrics})
                    if context.get("long_form") and self.settings.mode!="demo":
                        self.store.job_update(jid,"running","Desarrollando secciones del informe")
                        target_words = min(2200,max(250,context["target_pages"]*350//len(spec.sections)))
                        registry = {key:spec.model_dump()[key] for key in ("risks","controls","actions","assumptions","objective","audience")}
                        def expand(section):
                            relevant=[s for s in context["sources"] if s["id"] in section.source_ids] or context["sources"][:6]
                            expanded, usage = self.model.generate(Section,prompts.EXPAND,
                                {"message":context["message"],"section":section.model_dump(),"outline":[{"id":s.id,"heading":s.heading} for s in spec.sections],
                                 "registry":registry,"sources":relevant,"target_words":target_words})
                            if expanded.id!=section.id or expanded.heading!=section.heading:
                                raise ValueError("La expansión cambió la identidad de una sección")
                            return expanded,usage
                        with ThreadPoolExecutor(max_workers=self.settings.section_workers) as sections_pool:
                            expanded=list(sections_pool.map(expand,spec.sections))
                        spec.sections=[s for s,_ in expanded]
                        model_calls.extend({"stage":"section",**usage} for _,usage in expanded)
                    if self.settings.mode!="demo" and self.settings.semantic_review:
                        self.store.job_update(jid,"running","Revisando evidencia y coherencia consultiva")
                        review_context={"message":context["message"],"artifact":spec.model_dump(),"sources":context.get("sources",[])}
                        semantic, usage = self.model.generate(ConsultingReview,prompts.REVIEW,review_context)
                        model_calls.append({"stage":"review",**usage})
                        if semantic.blocking_issues:
                            # Un intento acotado de reparación. No hay bucle ilimitado.
                            repaired_context={**context,"previous":spec.model_dump(),"corrections":semantic.blocking_issues,"long_form":False}
                            spec, usage = self.model.generate(Artifact,prompts.WRITE+"\nCorrige exclusivamente los errores de corrections. Conserva el resto.",repaired_context)
                            model_calls.append({"stage":"repair",**usage})
                            semantic,usage=self.model.generate(ConsultingReview,prompts.REVIEW,{**review_context,"artifact":spec.model_dump()})
                            model_calls.append({"stage":"review_after_repair",**usage})
                            if semantic.blocking_issues:
                                raise ValueError("Revisión consultiva: "+"; ".join(semantic.blocking_issues)[:700])
                sources = [Source.model_validate(s) for s in context.get("sources",[])]
                quality = review(spec,sources)
                quality["semantic_review"] = semantic.model_dump() if semantic else {"performed":False}
                if quality["errors"]:
                    raise ValueError("; ".join(quality["errors"]))
                # El modelo no puede escoger un logo de otra conversación.
                logo = self.store.asset(p,cid,spec.theme.logo_id)["path"] if spec.theme.logo_id else None
                self.store.job_update(jid,"running","Construyendo archivos editables")
                version = previous["version"]+1 if previous else 1
                directory = self.store.root/"artifacts"/aid/f"v{version}"
                directory.mkdir(parents=True,exist_ok=False)
                files = render(spec,sources,directory,formats,logo)
                quality["elapsed_seconds"] = round(time.perf_counter()-start,2)
                quality["model"] = metrics
                quality["model_calls"] = model_calls
                (directory/"quality.json").write_text(json.dumps(quality,ensure_ascii=False,indent=2),encoding="utf-8")
                files.append("quality.json")
                self.store.job_update(jid,"running","Empaquetando y guardando versión")
                with ZipFile(directory/"paquete.zip","w",ZIP_DEFLATED) as z:
                    for name in files:
                        z.write(directory/name,name)
                files.append("paquete.zip")
                if self.settings.blob_account_url and self.settings.blob_container:
                    from azure.identity import DefaultAzureCredential
                    from azure.storage.blob import BlobServiceClient, ContentSettings
                    import mimetypes
                    blob = BlobServiceClient(self.settings.blob_account_url,credential=DefaultAzureCredential()).get_container_client(self.settings.blob_container)
                    # IDs del usuario no se interpolan en rutas de Blob.
                    import hashlib
                    tenant = hashlib.sha256(p.tenant_id.encode()).hexdigest()[:24]
                    owner = hashlib.sha256(p.user_id.encode()).hexdigest()[:24]
                    for name in files:
                        with (directory/name).open("rb") as stream:
                            blob.upload_blob(f"{tenant}/{owner}/{aid}/v{version}/{jid}/{name}",stream,overwrite=False,
                                             content_settings=ContentSettings(content_type=mimetypes.guess_type(name)[0] or "application/octet-stream"))
                self.store.save_version(p,cid,aid,version,spec.model_dump(),[s.model_dump() for s in sources],formats,directory)
                published = True
                with self.lock("chat:"+cid):
                    memory = Memory.model_validate(self.store.conversation(p,cid)["memory"])
                    memory.decisions = (memory.decisions+[f"Entregable {aid} versión {version}: {spec.title}. Petición: {context.get('message','')[:500]}"])[-20:]
                    self.store.update_memory(p,cid,memory.model_dump())
                    self.store.add_message(p,cid,"assistant",f"Entregable disponible: {aid}, versión {version}. {spec.title}")
                self.store.job_update(jid,"completed","Disponible para revisión",{"artifact_id":aid,"version":version,"files":files,"quality":quality})
                self.store.event(p,"artifact_completed",{"job":jid,"version":version,"seconds":quality["elapsed_seconds"],**metrics})
        except Exception as exc:
            # No publicar versiones incompletas ni exponer detalles del proveedor o rutas internas.
            if directory and directory.exists() and not published:
                shutil.rmtree(directory,ignore_errors=True)
            allowed = isinstance(exc,(ValueError,KeyError))
            message = str(exc)[:350] if allowed else "Error al generar el entregable. Revisa conexiones y logs operativos del servidor."
            self.store.job_update(jid,"failed",message,{"error_type":type(exc).__name__})
            self.store.event(p,"artifact_failed",{"job":jid,"error_type":type(exc).__name__})
        finally:
            self.capacity.release()

    def revise_structured(self,p,cid,aid,changes):
        old = self.store.version(p,aid)
        if old["conversation"] != cid:
            raise KeyError("Entregable no encontrado")
        spec = Artifact.model_validate(old["spec"])
        # Edición explícita validada por IDs. Se rechazan campos desconocidos.
        allowed = {"theme","sections","nodes","decision","title"}
        if set(changes)-allowed:
            raise ValueError("Campos de revisión permitidos: theme, sections, nodes, decision, title")
        if "theme" in changes:
            spec.theme = Theme.model_validate({**spec.theme.model_dump(),**changes["theme"]})
        for key in ("decision","title"):
            if key in changes:
                setattr(spec,key,changes[key])
        for change in changes.get("sections",[]):
            section = next((s for s in spec.sections if s.id==change.get("id")),None)
            if not section or set(change)-{"id","heading","paragraphs","bullets","source_ids"}:
                raise ValueError("Sección o cambio inválido")
            index = spec.sections.index(section)
            spec.sections[index] = type(section).model_validate({**section.model_dump(),**change})
        for change in changes.get("nodes",[]):
            node = next((n for n in spec.process.nodes if n.id==change.get("id")),None) if spec.process else None
            if not node or set(change)-{"id","lane","label","kind"}:
                raise ValueError("Nodo o cambio inválido")
            spec.process.nodes[spec.process.nodes.index(node)] = type(node).model_validate({**node.model_dump(),**change})
        spec = Artifact.model_validate(spec.model_dump())
        context = {"message":"Edición estructurada por el usuario","sources":old["sources"],"theme":spec.theme.model_dump()}
        return self.submit(p,cid,context,old["formats"],old,spec)
