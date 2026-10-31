"""Casos de uso independientes: grabación local o Graph hacia guía, PPTX y evaluación."""
import hashlib
from pathlib import Path
import shutil
import tempfile
import time
from recording_studio.application.assessment import generate_assessment
from recording_studio.domain.models import Theme
from recording_studio.documents.export import export_bundle
from recording_studio.infrastructure.providers import ResponsesModel
from recording_studio.media.batching import parse_subtitles
from recording_studio.media.ffmpeg import MediaTools
from recording_studio.media.pipeline import VideoPipeline,file_digest
from recording_studio.media.transcription import AudioTranscriber


class RecordingService:
    """Procesador de grabaciones integrable en el backend actual, sin contexto conversacional."""
    def __init__(self,settings,model=None,graph=None,media=None,transcriber=None):
        """Inyecta inferencia, Graph y herramientas para usar servicios reales o proveedores de prueba."""
        self.settings=settings;self.graph=graph
        self.model=model or (ResponsesModel(settings) if settings.mode=="azure" else None)
        self.media=media or MediaTools(settings.ffmpeg_bin,settings.ffprobe_bin,settings.video_frames_per_batch)
        self.transcriber=transcriber or AudioTranscriber(settings)

    def _scope(self,principal,workspace_id):
        """Separa checkpoints por identidad y espacio de trabajo autenticados por el host."""
        import json
        raw=json.dumps([principal.tenant_id,principal.user_id,workspace_id],ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _ready(self,brief,subtitles):
        """Valida que haya modelo, objetivo y una vía de transcripción antes de descargar un video."""
        if self.model is None:raise ValueError("Configura el modelo para analizar grabaciones reales; demo solo reproduce un ejemplo")
        if not brief or len(brief)>12000:raise ValueError("Indica un objetivo de 1 a 12000 caracteres")
        if subtitles is not None and len(subtitles)>1000000:raise ValueError("Los subtítulos superan el presupuesto de texto")
        if not subtitles and not self.settings.transcriber_model:raise ValueError("Adjunta VTT/SRT o configura RS_TRANSCRIBER_MODEL")

    def generate_file(self,principal,path,brief,output_directory,subtitles=None,theme=None,workspace_id="default",progress=None,include_word=True):
        """Analiza una ruta autorizada por el backend y publica un paquete completo en un destino nuevo.

        El usuario HTTP no puede elegir esta ruta: integra la llamada después de tu subida
        existente, una vez autorizado el archivo y la identidad en tu aplicación.
        """
        started=time.perf_counter();self._ready(brief,subtitles)
        path=Path(path)
        if not path.is_file() or path.suffix.lower() not in (".mp4",".mov",".mkv",".webm",".avi") or path.stat().st_size>4*1024**3:
            raise ValueError("Video inválido o mayor de 4 GB")
        output=Path(output_directory)
        if output.exists():raise FileExistsError("Selecciona un directorio nuevo para conservar los resultados anteriores")
        theme=Theme.model_validate(theme.model_dump() if isinstance(theme,Theme) else theme or {})
        duration=self.media.duration(path);segments=parse_subtitles(subtitles) if subtitles else []
        scope=self._scope(principal,workspace_id);digest=file_digest(path)
        cache=Path(self.settings.data_dir)/"runs"/scope/digest
        pipeline=VideoPipeline(self.model,self.settings,self.media,self.transcriber)
        plan,report,frames,segments=pipeline.analyze(duration,segments,[],cache,scope,brief,video_path=path,video_digest=digest,progress=progress)
        if progress:progress("Generando las diez preguntas sobre la guía final")
        assessment,usage=generate_assessment(self.model,{"title":plan.title,"groups":[group.model_dump() for group in plan.groups]},
                                             {group.id for group in plan.groups})
        report["calls"].append({"stage":"assessment",**usage})
        report["analysis_and_assessment_seconds"]=round(time.perf_counter()-started,2)
        output.parent.mkdir(parents=True,exist_ok=True)
        staging=Path(tempfile.mkdtemp(prefix=".recording-export-",dir=output.parent))
        try:
            files=export_bundle(plan,assessment,theme,staging,{frame.id:frame.path for frame in frames if frame.path},report,segments,include_word)
            staging.rename(output)
        except Exception:
            shutil.rmtree(staging,ignore_errors=True);raise
        if progress:progress("Presentación y evaluación disponibles")
        return {"directory":str(output.resolve()),"files":files,"report":report,"elapsed_seconds":round(time.perf_counter()-started,2)}

    def generate_graph(self,principal,reference,brief,output_directory,subtitles=None,theme=None,workspace_id="default",progress=None,include_word=True):
        """Resuelve un enlace Teams/SharePoint autorizado, descarga por streaming y procesa la grabación."""
        self._ready(brief,subtitles)
        if self.graph is None:raise ValueError("Inyecta el cliente Graph desde tu backend autenticado")
        output=Path(output_directory)
        if output.exists():raise FileExistsError("Selecciona un directorio nuevo para la exportación")
        drive,item,metadata=self.graph.resolve_reference(principal,reference)
        suffix=Path(metadata.get("name","")).suffix.lower()
        if suffix not in (".mp4",".mov",".mkv",".webm",".avi"):raise ValueError("El elemento Graph no es una grabación admitida")
        folder=Path(self.settings.data_dir)/"downloads"/self._scope(principal,workspace_id);folder.mkdir(parents=True,exist_ok=True)
        started=time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="video-",dir=folder) as temporary:
            path=Path(temporary)/("recording"+suffix)
            if progress:progress("Descargando la grabación autorizada")
            self.graph.download(principal,drive,item,path)
            result=self.generate_file(principal,path,brief,output,subtitles,theme,workspace_id,progress,include_word)
        result["elapsed_with_download_seconds"]=round(time.perf_counter()-started,2)
        return result
