from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    mode: str = "demo"
    data_dir: Path = Path("runtime")
    model_base_url: str = ""
    model_api_key: str = ""
    router_model: str = ""
    writer_model: str = ""
    entra: bool = False
    model_timeout: int = 180
    search_endpoint: str = ""
    search_index: str = ""
    search_api_key: str = ""
    search_version: str = "2024-07-01"
    workers: int = 2
    max_pending: int = 20
    tokens_json: str = "{}"
    blob_account_url: str = ""
    blob_container: str = ""
    section_workers: int = 2
    semantic_review: bool = True

    @classmethod
    def from_env(cls):
        s = cls(mode=os.getenv("GS_MODE", "demo"), data_dir=Path(os.getenv("GS_DATA_DIR", "runtime")),
                model_base_url=os.getenv("GS_MODEL_BASE_URL", ""), model_api_key=os.getenv("GS_MODEL_API_KEY", ""),
                router_model=os.getenv("GS_ROUTER_MODEL", ""), writer_model=os.getenv("GS_WRITER_MODEL", ""),
                entra=os.getenv("GS_ENTRA") == "1", model_timeout=int(os.getenv("GS_MODEL_TIMEOUT", "180")),
                search_endpoint=os.getenv("GS_SEARCH_ENDPOINT", ""), search_index=os.getenv("GS_SEARCH_INDEX", ""),
                search_api_key=os.getenv("GS_SEARCH_API_KEY", ""), search_version=os.getenv("GS_SEARCH_VERSION", "2024-07-01"),
                workers=int(os.getenv("GS_MAX_WORKERS", "2")), max_pending=int(os.getenv("GS_MAX_PENDING_JOBS", "20")),
                tokens_json=os.getenv("GS_TOKENS_JSON", "{}"), blob_account_url=os.getenv("GS_BLOB_ACCOUNT_URL", ""),
                blob_container=os.getenv("GS_BLOB_CONTAINER", ""),section_workers=int(os.getenv("GS_SECTION_WORKERS","2")),
                semantic_review=os.getenv("GS_SEMANTIC_REVIEW","1")=="1")
        if s.mode not in ("demo", "azure") or not 1 <= s.workers <= 8 or not 1 <= s.max_pending <= 200:
            raise ValueError("Configuración inválida")
        if not 1<=s.section_workers<=4:
            raise ValueError("GS_SECTION_WORKERS debe estar entre 1 y 4")
        if s.mode == "azure":
            if not all((s.model_base_url, s.router_model, s.writer_model, s.search_endpoint, s.search_index)):
                raise ValueError("Faltan endpoints o deployments de Azure")
            if not s.entra and not all((s.model_api_key, s.search_api_key)):
                raise ValueError("Configura claves o GS_ENTRA=1")
            if not s.model_base_url.startswith("https://") or not s.search_endpoint.startswith("https://"):
                raise ValueError("Los endpoints de Azure requieren HTTPS")
        return s
