"""Contratos de video independientes del proveedor de transcripción o visión."""
from pydantic import Field,model_validator
from recording_studio.domain.models import Model,FrameRegion
from typing import Literal


class Segment(Model):
    """Texto de un intervalo del video con procedencia temporal explícita."""
    id: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(max_length=60000)

    @model_validator(mode="after")
    def interval(self):
        """Impide intervalos invertidos que romperían cobertura y orden."""
        if self.end<=self.start:raise ValueError("Intervalo de transcripción inválido")
        return self


class Frame(Model):
    """Captura local opcional asociada a un instante y autorizada por el backend."""
    id: str
    timestamp: float = Field(ge=0)
    path: str | None = None
    duplicate_of: str | None = None


class Batch(Model):
    """Ventana extensa con su intervalo central y un borde de contexto compartido."""
    id: str
    start: float
    end: float
    context_start: float
    context_end: float


class StepGroup(Model):
    """Una pantalla o actividad explicada con varios pasos que deben viajar juntos."""
    id: str
    title: str = Field(min_length=1,max_length=105)
    objective: str = Field(max_length=180)
    steps: list[str] = Field(min_length=1,max_length=4)
    dynamic_fields: list[str] = Field(default_factory=list,max_length=12)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    evidence_ids: list[str] = Field(min_length=1,max_length=40)
    origin_ids: list[str] = Field(default_factory=list,max_length=3000)
    frame_id: str | None = None
    annotations: list[FrameRegion] = Field(default_factory=list,max_length=4)

    @model_validator(mode="after")
    def readable_group(self):
        """Mantiene intervalos válidos y textos legibles sin dividir cada clic en una lámina."""
        if self.end<=self.start or any(len(s)>150 for s in self.steps):
            raise ValueError("Grupo inválido o pasos demasiado largos")
        indices=[region.step_index for region in self.annotations]
        if self.frame_id and self.frame_id not in self.evidence_ids:
            raise ValueError("El frame seleccionado no pertenece a la evidencia del grupo")
        if self.annotations and not self.frame_id:
            raise ValueError("Las marcas requieren un frame explícito")
        if len(indices)!=len(set(indices)) or any(index>=len(self.steps) for index in indices):
            raise ValueError("La marca visual refiere un paso inexistente o duplicado")
        return self


class BatchAnalysis(Model):
    """Resumen compacto de un lote; sus capturas nunca se convierten automáticamente en láminas."""
    summary: str = Field(max_length=2500)
    groups: list[StepGroup] = Field(min_length=1,max_length=30)


class Exclusion(Model):
    """Registra por qué un grupo no aparece en el resultado, sin descartarlo silenciosamente."""
    origin_id: str
    reason: str = Field(min_length=8,max_length=500)


class VideoPlan(Model):
    """Plan consolidado que conserva cobertura y elimina duplicados de los solapamientos."""
    title: str = Field(min_length=1,max_length=160)
    summary: str = Field(max_length=2500)
    groups: list[StepGroup] = Field(min_length=1,max_length=80)
    exclusions: list[Exclusion] = Field(default_factory=list,max_length=200)


class GraphReference(Model):
    """Archivo Graph por identificadores o enlace de grabación, nunca por token del cliente."""
    drive_id: str | None = Field(default=None,min_length=1,max_length=500)
    item_id: str | None = Field(default=None,min_length=1,max_length=500)
    sharing_url: str | None = Field(default=None,min_length=1,max_length=12000)

    @model_validator(mode="after")
    def one_reference(self):
        """Exige el par de identificadores completo o un enlace, sin combinaciones ambiguas."""
        if self.sharing_url:
            if self.drive_id or self.item_id:raise ValueError("Usa un enlace o el par drive_id/item_id")
        elif not (self.drive_id and self.item_id):raise ValueError("Falta drive_id/item_id o sharing_url")
        return self
