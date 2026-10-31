"""Adaptador opcional de transcripción por lote para endpoints compatibles con Audio v1."""
import json
from pathlib import Path
from urllib import request
import uuid
from recording_studio.infrastructure.providers import ResponsesModel
from recording_studio.media.models import Segment


class AudioTranscriber:
    """Transcribe audio comprimido en una petición por lote, no una por paso."""
    def __init__(self,settings):
        """Reutiliza la autenticación de inferencia y un deployment de audio independiente."""
        self.settings=settings
        self.auth=ResponsesModel(settings)

    def transcribe(self,path,batch):
        """Devuelve texto con precisión temporal de lote, sin inventar tiempos por palabra."""
        if not self.settings.transcriber_model:
            raise ValueError("Adjunta VTT/SRT o configura RS_TRANSCRIBER_MODEL")
        path=Path(path)
        if path.stat().st_size>24*1024*1024:raise ValueError("El audio del lote supera 24 MB")
        boundary="gs-"+uuid.uuid4().hex
        parts=[]
        for key,value in {"model":self.settings.transcriber_model,"response_format":"json"}.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="batch.mp3"\r\nContent-Type: audio/mpeg\r\n\r\n'.encode()+path.read_bytes()+b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        url=self.settings.model_base_url.rstrip("/")+"/audio/transcriptions"
        req=request.Request(url,data=b"".join(parts),headers={**self.auth.headers(),"Content-Type":"multipart/form-data; boundary="+boundary},method="POST")
        with request.urlopen(req,timeout=self.settings.model_timeout) as response:
            text=json.loads(response.read(2_000_000)).get("text","").strip()
        if not text:raise ValueError("La transcripción no devolvió texto; revisa el audio")
        return [Segment(id=batch.id+"-T",start=batch.context_start,end=batch.context_end,text=text)]
