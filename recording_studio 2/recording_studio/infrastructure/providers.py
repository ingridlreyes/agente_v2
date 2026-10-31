"""Inferencia de texto y visión para analizar grabaciones. Sin ejecución de código generado por el modelo."""
from __future__ import annotations
import json
import re
import time
from threading import BoundedSemaphore
from urllib import request, error, parse


class ProviderError(RuntimeError):
    """Error sanitizado de proveedor que puede mostrarse sin filtrar secretos."""
    pass


def post_json(url, body, headers, timeout=60, attempts=3):
    """Envía JSON con timeout y reintentos acotados a errores transitorios."""
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
    """Adaptador de inferencia con Structured Outputs y concurrencia limitada."""
    def __init__(self, settings):
        """Configura el proveedor y sus dependencias desde Settings."""
        self.settings = settings
        self.limiter=BoundedSemaphore(settings.max_model_concurrency)
        self.credential = None
        if settings.entra:
            from azure.identity import DefaultAzureCredential
            self.credential = DefaultAzureCredential()

    def headers(self):
        """Obtiene credenciales de inferencia en el backend mediante clave o Entra."""
        if self.credential:
            token = self.credential.get_token("https://ai.azure.com/.default").token
            return {"Authorization": "Bearer " + token}
        return {"api-key": self.settings.model_api_key}

    def generate(self, schema, instructions, context, role="writer", images=None):
        """Limita todas las llamadas de texto y visión de esta instancia, incluidos los lotes."""
        with self.limiter:
            return self._generate(schema,instructions,context,role,images)

    def _generate(self, schema, instructions, context, role="writer", images=None):
        """Llama a Responses, rechaza respuestas incompletas y valida el contrato devuelto."""
        start=time.perf_counter()
        deployment = self.settings.writer_model
        content = [{"type": "input_text", "text": json.dumps(context, ensure_ascii=False)}]
        for data_uri in images or []:
            content.append({"type": "input_image", "image_url": data_uri, "detail": self.settings.vision_detail})
        body = {"model": deployment, "store": False, "instructions": instructions,
                "input": [{"role": "user", "content": content}],
                "max_output_tokens": 22000 if schema.__name__ in ("VideoPlan",) else 12000 if schema.__name__=="BatchAnalysis" else 6000,
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
