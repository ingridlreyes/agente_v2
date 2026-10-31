"""Contratos de identidad, marca, regiones visuales y evaluación de grabaciones."""
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator


class Model(BaseModel):
    """Base estricta de los contratos: rechaza campos inesperados y números no finitos."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class Principal(Model):
    """Identidad autenticada que el servidor utiliza para autorizar cada operación."""
    tenant_id: str = Field(min_length=1, max_length=100)
    user_id: str = Field(min_length=1, max_length=100)


class Theme(Model):
    """Marca configurable del cliente y referencia al logo autorizado."""
    client: str = Field(default="Cliente", max_length=100)
    primary: str = Field(default="#142D4E", pattern=r"^#[0-9a-fA-F]{6}$")
    accent: str = Field(default="#007F78", pattern=r"^#[0-9a-fA-F]{6}$")
    font: Literal["Aptos", "Arial", "Calibri"] = "Arial"


class FrameRegion(Model):
    """Región visible de una captura, con coordenadas normalizadas y paso local asociado."""
    step_index: int = Field(ge=0,le=3)
    x: float = Field(ge=0,lt=1)
    y: float = Field(ge=0,lt=1)
    width: float = Field(gt=0,le=1)
    height: float = Field(gt=0,le=1)

    @model_validator(mode="after")
    def inside_frame(self):
        """Impide dibujar marcas fuera de los límites de la captura original."""
        if self.x+self.width>1.000001 or self.y+self.height>1.000001:
            raise ValueError("La región señalada sale del frame")
        return self


class Question(Model):
    """Pregunta con cuatro opciones, solución explicada y evidencia del material."""
    id: str
    question: str = Field(min_length=12,max_length=500)
    options: list[str] = Field(min_length=4,max_length=4)
    correct_index: int = Field(ge=0,le=3)
    explanation: str = Field(min_length=10,max_length=1200)
    evidence_ids: list[str] = Field(min_length=1,max_length=8)


class Assessment(Model):
    """Evaluación de diez preguntas; la procedencia real se fija en el servidor."""
    title: str
    questions: list[Question] = Field(min_length=10,max_length=10)
    generation: Literal["llm","demo"] = "llm"

    @model_validator(mode="after")
    def unique_questions(self):
        """Rechaza IDs repetidos, preguntas duplicadas u opciones indistinguibles."""
        if len({q.id for q in self.questions})!=10 or len({q.question.casefold() for q in self.questions})!=10:
            raise ValueError("La evaluación debe contener diez preguntas distintas")
        if any(len({v.casefold() for v in q.options})!=4 for q in self.questions):
            raise ValueError("Las cuatro opciones deben ser distintas")
        return self
