"""Servidor local de referencia. Producción: ejecutar detrás de TLS y gateway corporativo."""
from __future__ import annotations
import base64
import binascii
import hmac
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import secrets
from threading import Lock, BoundedSemaphore
import time
from urllib.parse import urlsplit, parse_qs
from .models import Principal, Theme, ChatRequest
from .attachments import ingest, save_logo
from .engine import BusyError


STATIC = Path(__file__).parent/"static"


class Authenticator:
    def __init__(self, settings):
        self.mode = settings.mode
        self.tokens = {token:Principal.model_validate(p) for token,p in json.loads(settings.tokens_json).items()}
        if settings.mode=="azure" and (not self.tokens or any(len(k)<32 for k in self.tokens)):
            raise ValueError("Configura tokens opacos de al menos 32 caracteres, o sustituye Authenticator por Entra validado")
        self.demo_token = secrets.token_urlsafe(32)
        if settings.mode=="demo":
            self.tokens[self.demo_token] = Principal(tenant_id="demo",user_id="local")
        self.lock = Lock()
        self.buckets = {}

    def authenticate(self, header):
        value = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
        for token,p in self.tokens.items():
            if hmac.compare_digest(token,value):
                return p
        raise PermissionError("Token inválido o ausente")

    def rate(self,p,write):
        now = time.monotonic()
        key = (p.tenant_id,p.user_id,"write" if write else "read")
        with self.lock:
            times = [t for t in self.buckets.get(key,[]) if now-t<60]
            if len(times)>=(20 if write else 180):
                raise BusyError("Límite temporal de solicitudes. Espera un minuto.")
            self.buckets[key] = times+[now]


def serve(engine,host="127.0.0.1",port=8080):
    if engine.settings.mode=="demo" and host not in ("127.0.0.1","localhost","::1"):
        raise ValueError("El modo demo solo puede escuchar en loopback")
    auth = Authenticator(engine.settings)
    inflight = BoundedSemaphore(8)

    class Handler(BaseHTTPRequestHandler):
        server_version = "GovernanceStudio"

        def log_message(self,format,*args):
            # No loguear URLs, IDs, encabezados ni cuerpos de conversaciones.
            pass

        def respond(self,status,data,ctype="application/json; charset=utf-8",download=None):
            if ctype.startswith("application/json"):
                data = json.dumps(data,ensure_ascii=False).encode()
            elif isinstance(data,str):
                data = data.encode()
            self.send_response(status)
            self.send_header("Content-Type",ctype)
            self.send_header("Content-Length",str(len(data)))
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Referrer-Policy","no-referrer")
            self.send_header("Cache-Control","no-store")
            self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if download:
                self.send_header("Content-Disposition",f'attachment; filename="{download}"')
            self.end_headers()
            self.wfile.write(data)

        def body(self):
            try:
                length = int(self.headers.get("Content-Length","0"))
            except ValueError:
                raise ValueError("Content-Length inválido")
            if length<=0 or length>17*1024*1024:
                raise ValueError("Cuerpo de solicitud vacío o demasiado grande")
            if not self.headers.get("Content-Type","").startswith("application/json"):
                raise ValueError("Se requiere application/json")
            return json.loads(self.rfile.read(length))

        def do_GET(self):
            self.handle_request("GET")

        def do_POST(self):
            self.handle_request("POST")

        def handle_request(self,method):
            if not inflight.acquire(blocking=False):
                self.respond(429,{"error":"Servidor ocupado"})
                return
            try:
                self.connection.settimeout(240)
                self.dispatch(method)
            except PermissionError as exc:
                self.respond(403,{"error":str(exc)})
            except KeyError:
                self.respond(404,{"error":"Recurso no encontrado"})
            except BusyError as exc:
                self.respond(429,{"error":str(exc)})
            except (ValueError,UnicodeError,binascii.Error) as exc:
                self.respond(400,{"error":str(exc)[:500]})
            except (BrokenPipeError,ConnectionResetError):
                pass
            except Exception:
                self.respond(502,{"error":"No se pudo completar la operación. Revisa la configuración de los servicios."})
            finally:
                inflight.release()

        def dispatch(self,method):
            if engine.settings.mode=="demo":
                host_header = self.headers.get("Host","").split(":")[0]
                if host_header not in ("127.0.0.1","localhost"):
                    raise PermissionError("Host local inválido")
            parsed = urlsplit(self.path)
            path = parsed.path
            if method=="GET" and path in ("/","/app.js","/style.css"):
                filename = {"/":"index.html","/app.js":"app.js","/style.css":"style.css"}[path]
                ctype = {"/":"text/html; charset=utf-8","/app.js":"text/javascript; charset=utf-8","/style.css":"text/css; charset=utf-8"}[path]
                return self.respond(200,(STATIC/filename).read_bytes(),ctype)
            if method=="GET" and path=="/health":
                return self.respond(200,{"status":"ok","mode":engine.settings.mode,"version":"0.1.0"})
            if method=="POST" and path=="/api/demo-session" and engine.settings.mode=="demo":
                # Solo se expone en loopback y se entrega al JS del mismo origen.
                origin = self.headers.get("Origin")
                expected = "http://"+self.headers.get("Host","")
                if origin and origin!=expected:
                    raise PermissionError("Origen inválido")
                return self.respond(200,{"token":auth.demo_token,"mode":"demo"})
            p = auth.authenticate(self.headers.get("Authorization",""))
            auth.rate(p,method=="POST")
            parts = [x for x in path.split("/") if x]
            if method=="POST" and path=="/api/conversations":
                body = self.body()
                theme = Theme.model_validate(body.get("theme",{}))
                if theme.logo_id:
                    raise ValueError("Primero crea la conversación y después sube su logo")
                cid = engine.store.create_conversation(p,theme.model_dump())
                return self.respond(201,{"conversation_id":cid})
            if len(parts)==3 and parts[:2]==["api","jobs"] and method=="GET":
                return self.respond(200,engine.store.job(p,parts[2]))
            if len(parts)>=3 and parts[:2]==["api","conversations"]:
                cid = parts[2]
                conv = engine.store.conversation(p,cid)
                if len(parts)==3 and method=="GET":
                    return self.respond(200,{"conversation_id":cid,"theme":conv["theme"],"memory":conv["memory"],"messages":engine.store.messages(p,cid,300),"artifacts":engine.store.list_versions(p,cid)})
                if len(parts)==4 and method=="POST":
                    body = self.body()
                    if parts[3]=="messages":
                        return self.respond(200,engine.chat(p,cid,ChatRequest.model_validate(body)))
                    if parts[3]=="theme":
                        theme = Theme.model_validate(body)
                        if theme.logo_id:
                            engine.store.asset(p,cid,theme.logo_id)
                        engine.store.update_theme(p,cid,theme.model_dump())
                        return self.respond(200,theme.model_dump())
                    if parts[3] in ("attachments","logo"):
                        data = base64.b64decode(body.get("data_base64",""),validate=True)
                        if parts[3]=="logo":
                            return self.respond(201,save_logo(engine.store,p,cid,data))
                        return self.respond(201,ingest(engine.store,p,cid,body.get("filename","archivo.txt"),data,body.get("scope","conversation")))
            if len(parts)>=3 and parts[:2]==["api","artifacts"]:
                aid = parts[2]
                if len(parts)==4 and parts[3]=="revise" and method=="POST":
                    body = self.body()
                    jid = engine.revise_structured(p,body["conversation_id"],aid,body["changes"])
                    return self.respond(202,{"job_id":jid})
                version_arg = parse_qs(parsed.query).get("version",[None])[0]
                version = int(version_arg) if version_arg else None
                record = engine.store.version(p,aid,version)
                if len(parts)==3 and method=="GET":
                    return self.respond(200,{k:record[k] for k in ("artifact","version","conversation","spec","sources","formats","created")})
                if len(parts)==5 and parts[3]=="files" and method=="GET":
                    name = parts[4]
                    if name not in ("entregable.docx","entregable.pptx","entregable.xlsx","proceso.svg","proceso_editable.pptx","artifact.json","sources.json","quality.json","paquete.zip"):
                        raise KeyError("Archivo desconocido")
                    file = Path(record["directory"])/name
                    if not file.is_file():
                        raise KeyError("Archivo no encontrado")
                    return self.respond(200,file.read_bytes(),mimetypes.guess_type(name)[0] or "application/octet-stream",name)
            raise KeyError("Endpoint desconocido")

    server = ThreadingHTTPServer((host,port),Handler)
    print(f"Governance Studio [{engine.settings.mode}] http://{host}:{port}",flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        engine.close()
