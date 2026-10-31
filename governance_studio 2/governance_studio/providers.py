"""Responses REST y recuperación Azure. Sin ejecución de código generado por el modelo."""
from __future__ import annotations
import json
import re
import time
from urllib import request, error, parse
from .models import Source


class ProviderError(RuntimeError):
    pass


def post_json(url, body, headers, timeout=60, attempts=3):
    data = json.dumps(body, ensure_ascii=False).encode()
    for attempt in range(attempts):
        req = request.Request(url, data=data, headers={"Content-Type": "application/json", **headers}, method="POST")
        try:
            with request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read(8_000_000))
        except error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise ProviderError(f"Servicio remoto devolvió HTTP {exc.code}") from None
            # Retry acotado; no imprimir cuerpos que podrían incluir datos privados.
            try:
                delay = min(float(exc.headers.get("Retry-After", 2 ** attempt)), 8)
            except ValueError:
                delay = 2 ** attempt
            time.sleep(max(0, delay))
        except (OSError, ValueError):
            raise ProviderError("No se pudo completar la conexión o interpretar la respuesta remota") from None


def strict_schema(schema):
    """Structured Outputs exige todos los campos requeridos, aun cuando acepten null."""
    if isinstance(schema, dict):
        schema = {k: strict_schema(v) for k, v in schema.items() if k not in ("default",)}
        if schema.get("type") == "object":
            schema["additionalProperties"] = False
            schema["required"] = list(schema.get("properties", {}))
    elif isinstance(schema, list):
        schema = [strict_schema(v) for v in schema]
    return schema


class ResponsesModel:
    def __init__(self, settings):
        self.settings = settings
        self.credential = None
        if settings.entra:
            from azure.identity import DefaultAzureCredential
            self.credential = DefaultAzureCredential()

    def headers(self):
        if self.credential:
            token = self.credential.get_token("https://ai.azure.com/.default").token
            return {"Authorization": "Bearer " + token}
        return {"api-key": self.settings.model_api_key}

    def generate(self, schema, instructions, context, role="writer", images=None):
        start=time.perf_counter()
        deployment = self.settings.router_model if role == "router" else self.settings.writer_model
        content = [{"type": "input_text", "text": json.dumps(context, ensure_ascii=False)}]
        for data_uri in images or []:
            content.append({"type": "input_image", "image_url": data_uri, "detail": "low"})
        body = {"model": deployment, "store": False, "instructions": instructions,
                "input": [{"role": "user", "content": content}],
                "max_output_tokens": 22000 if schema.__name__ == "Artifact" else 6000,
                "text": {"format": {"type": "json_schema", "name": schema.__name__, "strict": True,
                                      "schema": strict_schema(schema.model_json_schema())}}}
        payload = post_json(self.settings.model_base_url.rstrip("/") + "/responses", body,
                            self.headers(), self.settings.model_timeout)
        if payload.get("status") != "completed":
            raise ProviderError("El modelo no completó la respuesta. Reduce alcance o aumenta el límite de salida.")
        text = []
        for output in payload.get("output", []):
            for item in output.get("content", []):
                if item.get("type") == "refusal":
                    raise ProviderError("El modelo rechazó la solicitud")
                if item.get("type") == "output_text":
                    text.append(item["text"])
        try:
            result = schema.model_validate_json("".join(text))
        except ValueError:
            raise ProviderError("El modelo produjo una estructura inválida; no se publicó el archivo") from None
        return result, {"deployment": deployment, "usage": payload.get("usage", {}),"elapsed_seconds":round(time.perf_counter()-start,3)}


def odata(value):
    return "'" + value.replace("'", "''") + "'"


def security_filter(p, cid):
    return (f"tenant_id eq {odata(p.tenant_id)} and (scope eq 'base' or scope eq 'public' or "
            f"(scope eq 'private' and owner_id eq {odata(p.user_id)}) or "
            f"(scope eq 'conversation' and owner_id eq {odata(p.user_id)} and conversation_id eq {odata(cid)}))")


class Knowledge:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings
        self.credential = None
        if settings.mode == "azure" and settings.entra:
            from azure.identity import DefaultAzureCredential
            self.credential = DefaultAzureCredential()

    def retrieve(self, p, cid, query, limit=12):
        # Autorizar ANTES de la llamada remota y filtrar ANTES del ranking.
        rows = self.store.chunks(p, cid)
        terms = set(re.findall(r"\w{3,}", query.lower()))
        ranked = []
        for r in rows:
            words = set(re.findall(r"\w{3,}", (r["title"] + " " + r["content"]).lower()))
            score = len(words & terms)
            if score or r["scope"]=="conversation":
                score += 1 if r["scope"]=="conversation" else 0
                ranked.append((score, Source(id=r["id"], title=r["title"], locator=r["locator"],
                                             text=r["content"], scope=r["scope"])))
        if self.settings.mode == "azure":
            headers = ({"Authorization": "Bearer " + self.credential.get_token("https://search.azure.com/.default").token}
                       if self.credential else {"api-key": self.settings.search_api_key})
            endpoint = (self.settings.search_endpoint.rstrip("/") + "/indexes/" +
                        parse.quote(self.settings.search_index, safe="") + "/docs/search?api-version=" + self.settings.search_version)
            payload = post_json(endpoint, {"search": query[:3000], "top": limit,
                        "filter": security_filter(p, cid),
                        "select": "id,title,content,locator,scope,tenant_id,owner_id,conversation_id"}, headers)
            for r in payload.get("value", []):
                # Defensa adicional por si el índice o proxy está mal configurado.
                if r.get("tenant_id") != p.tenant_id:
                    raise ProviderError("Azure Search devolvió un resultado fuera del tenant")
                if r.get("scope") == "private" and r.get("owner_id") != p.user_id:
                    raise ProviderError("Azure Search devolvió un resultado sin permiso")
                if r.get("scope") == "conversation" and (r.get("owner_id") != p.user_id or r.get("conversation_id") != cid):
                    raise ProviderError("Azure Search devolvió un adjunto sin permiso")
                ranked.append((10 + float(r.get("@search.score", 0)), Source(id=r["id"], title=r["title"],
                              locator=r.get("locator", ""), text=r["content"], scope=r["scope"])))
        unique, total = {}, 0
        for _, s in sorted(ranked, key=lambda x: x[0], reverse=True):
            if s.id in unique or total >= 42000:
                continue
            s.text = s.text[:min(5500, 42000-total)]
            total += len(s.text)
            unique[s.id] = s
            if len(unique) == limit:
                break
        return list(unique.values())
