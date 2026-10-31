"""Configuración exclusiva de grabaciones, inferencia y lotes; variables con prefijo RS_."""
from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Límites de video y credenciales del backend para el procesador independiente."""
    mode: str = "demo"
    data_dir: Path = Path("runtime_recordings")
    model_base_url: str = ""
    model_api_key: str = ""
    writer_model: str = ""
    entra: bool = False
    model_timeout: int = 180
    video_batch_seconds: int = 900
    video_overlap_seconds: int = 15
    video_workers: int = 3
    video_frames_per_batch: int = 24
    video_max_slides: int = 30
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    transcriber_model: str = ""
    max_model_concurrency: int = 3
    vision_detail: str = "high"

    def __post_init__(self):
        """Rechaza tamaños, concurrencia y configuración de inferencia incompatibles."""
        if self.mode not in ("demo","azure"):raise ValueError("RS_MODE debe ser demo o azure")
        if not 300<=self.video_batch_seconds<=1800 or not 0<=self.video_overlap_seconds<=60:
            raise ValueError("Usa lotes de 5–30 minutos y solapamiento de 0–60 segundos")
        if not 1<=self.video_workers<=6 or not 1<=self.max_model_concurrency<=8:
            raise ValueError("Concurrencia de video o modelo inválida")
        if not 4<=self.video_frames_per_batch<=48 or not 2<=self.video_max_slides<=80:
            raise ValueError("Presupuesto de capturas o diapositivas inválido")
        if self.vision_detail not in ("low","high","auto"):raise ValueError("RS_VISION_DETAIL inválido")
        if not 10<=self.model_timeout<=1800:raise ValueError("Timeout de inferencia inválido")
        if self.mode=="azure" and (not self.model_base_url.startswith("https://") or not self.writer_model or not (self.model_api_key or self.entra)):
            raise ValueError("Configura endpoint HTTPS, deployment y clave o Entra para inferencia")

    @classmethod
    def from_env(cls):
        """Lee exclusivamente variables RS_, evitando mezclar configuración con otros proyectos."""
        return cls(mode=os.getenv("RS_MODE","demo"),data_dir=Path(os.getenv("RS_DATA_DIR","runtime_recordings")),
            model_base_url=os.getenv("RS_MODEL_BASE_URL",""),model_api_key=os.getenv("RS_MODEL_API_KEY",""),
            writer_model=os.getenv("RS_WRITER_MODEL",""),entra=os.getenv("RS_ENTRA")=="1",
            model_timeout=int(os.getenv("RS_MODEL_TIMEOUT","180")),video_batch_seconds=int(os.getenv("RS_VIDEO_BATCH_SECONDS","900")),
            video_overlap_seconds=int(os.getenv("RS_VIDEO_OVERLAP_SECONDS","15")),video_workers=int(os.getenv("RS_VIDEO_WORKERS","3")),
            video_frames_per_batch=int(os.getenv("RS_VIDEO_FRAMES_PER_BATCH","24")),video_max_slides=int(os.getenv("RS_VIDEO_MAX_SLIDES","30")),
            ffmpeg_bin=os.getenv("RS_FFMPEG_BIN","ffmpeg"),ffprobe_bin=os.getenv("RS_FFPROBE_BIN","ffprobe"),
            transcriber_model=os.getenv("RS_TRANSCRIBER_MODEL",""),max_model_concurrency=int(os.getenv("RS_MAX_MODEL_CONCURRENCY","3")),
            vision_detail=os.getenv("RS_VISION_DETAIL","high"))
