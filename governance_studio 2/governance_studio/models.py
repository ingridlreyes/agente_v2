from __future__ import annotations

from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class Principal(Model):
    tenant_id: str = Field(min_length=1, max_length=100)
    user_id: str = Field(min_length=1, max_length=100)
    role: Literal["user", "admin"] = "user"


class Theme(Model):
    client: str = Field(default="Cliente", max_length=100)
    primary: str = Field(default="#142D4E", pattern=r"^#[0-9a-fA-F]{6}$")
    accent: str = Field(default="#007F78", pattern=r"^#[0-9a-fA-F]{6}$")
    font: Literal["Aptos", "Arial", "Calibri"] = "Arial"
    logo_id: str | None = None


class Source(Model):
    id: str
    title: str
    locator: str
    text: str
    scope: Literal["base", "public", "private", "conversation"]


class Memory(Model):
    facts: list[str] = Field(default_factory=list, max_length=20)
    decisions: list[str] = Field(default_factory=list, max_length=20)
    preferences: list[str] = Field(default_factory=list, max_length=12)
    open_questions: list[str] = Field(default_factory=list, max_length=12)


class Route(Model):
    intent: Literal["answer", "create", "revise", "clarify", "out_of_scope"]
    domain: Literal["data_governance", "ai_governance", "both", "outside"]
    formats: list[Literal["docx", "pptx", "xlsx"]] = Field(default_factory=list, max_length=3)
    brief: str = Field(max_length=5000)
    artifact_id: str | None = None
    clarification: str | None = None
    target_pages: int | None = Field(default=None,ge=1,le=100)


class Answer(Model):
    text: str = Field(min_length=1, max_length=18000)
    source_ids: list[str] = Field(default_factory=list)
    memory: Memory


class ConsultingReview(Model):
    blocking_issues: list[str] = Field(default_factory=list,max_length=12)
    recommendations: list[str] = Field(default_factory=list,max_length=12)


class Section(Model):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,60}$")
    heading: str = Field(min_length=1, max_length=160)
    paragraphs: list[str] = Field(default_factory=list, max_length=30)
    bullets: list[str] = Field(default_factory=list, max_length=20)
    source_ids: list[str] = Field(default_factory=list)


class Finding(Model):
    id: str
    statement: str
    kind: Literal["fact", "assumption", "recommendation"]
    source_ids: list[str] = Field(default_factory=list)
    implication: str


class Risk(Model):
    id: str
    title: str
    cause: str
    consequence: str
    owner: str
    probability: int | None = Field(default=None, ge=1, le=5)
    impact: int | None = Field(default=None, ge=1, le=5)
    source_ids: list[str] = Field(default_factory=list)


class Control(Model):
    id: str
    risk_ids: list[str]
    activity: str
    owner: str
    frequency: str
    evidence: str
    acceptance: str
    status: Literal["Propuesto", "En curso", "Implementado"] = "Propuesto"


class Action(Model):
    id: str
    control_ids: list[str]
    action: str
    owner: str
    horizon: str
    acceptance: str
    status: Literal["Pendiente", "En curso", "Completada"] = "Pendiente"


class KPI(Model):
    id: str
    name: str
    definition: str
    numerator: float | None = None
    denominator: float | None = Field(default=None, ge=0)
    target: float | None = None
    unit: Literal["ratio", "number"] = "ratio"
    owner: str
    source_ids: list[str] = Field(default_factory=list)


class Node(Model):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,60}$")
    lane: str
    label: str = Field(min_length=1, max_length=110)
    kind: Literal["activity", "decision", "start", "end"] = "activity"


class Edge(Model):
    source: str
    target: str
    label: str = Field(default="", max_length=60)


class Process(Model):
    title: str
    lanes: list[str] = Field(min_length=1, max_length=8)
    nodes: list[Node] = Field(min_length=1, max_length=40)
    edges: list[Edge] = Field(default_factory=list, max_length=80)

    @model_validator(mode="after")
    def graph(self):
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)) or len(self.lanes) != len(set(self.lanes)):
            raise ValueError("IDs y carriles deben ser únicos")
        if any(n.lane not in self.lanes for n in self.nodes):
            raise ValueError("Carril desconocido")
        if any(e.source not in ids or e.target not in ids for e in self.edges):
            raise ValueError("Conexión a nodo inexistente")
        if len(ids) > 1:
            linked = {x for e in self.edges for x in (e.source, e.target)}
            if set(ids) - linked:
                raise ValueError("Hay nodos aislados")
        return self


class Slide(Model):
    layout: Literal["statement", "comparison", "roadmap", "process", "risks", "metrics"]
    title: str = Field(min_length=1, max_length=105)
    message: str = Field(max_length=350)
    items: list[str] = Field(default_factory=list, max_length=6)
    source_ids: list[str] = Field(default_factory=list)
    notes: str = ""
    dataset_id: str | None = None
    chart: Literal["bar", "column", "line", "none"] = "none"


class Column(Model):
    key: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]{0,35}$")
    label: str = Field(min_length=1, max_length=80)
    kind: Literal["text", "number", "ratio", "date"]


class DataRow(Model):
    values: list[str | float | None] = Field(max_length=20)


class Dataset(Model):
    id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]{0,25}$")
    name: str = Field(min_length=1, max_length=27)
    columns: list[Column] = Field(min_length=2, max_length=20)
    rows: list[DataRow] = Field(default_factory=list, max_length=1500)
    source_ids: list[str] = Field(default_factory=list)
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def data_types(self):
        keys = [c.key for c in self.columns]
        if len(keys)!=len(set(keys)):
            raise ValueError("Columnas duplicadas")
        for row in self.rows:
            if len(row.values)!=len(self.columns):
                raise ValueError("La fila no coincide con las columnas")
            for value,col in zip(row.values,self.columns):
                if value is None:
                    continue
                if col.kind in ("number","ratio") and not isinstance(value,(float,int)):
                    raise ValueError("Columna numérica contiene texto")
                if col.kind=="date":
                    date.fromisoformat(str(value))
        return self


class Metric(Model):
    label: str = Field(min_length=1, max_length=90)
    dataset_id: str
    operation: Literal["count", "sum", "average", "count_equal", "ratio_sums"]
    column: str
    denominator_column: str | None = None
    equals: str | None = None
    unit: Literal["number", "ratio"] = "number"


class Chart(Model):
    title: str = Field(max_length=100)
    dataset_id: str
    category_column: str
    value_column: str
    kind: Literal["bar", "column", "line"]


class WorkbookPlan(Model):
    datasets: list[Dataset] = Field(min_length=1, max_length=10)
    metrics: list[Metric] = Field(default_factory=list, max_length=12)
    charts: list[Chart] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def refs(self):
        by_id = {d.id:d for d in self.datasets}
        if len(by_id)!=len(self.datasets) or len({d.name.lower() for d in self.datasets})!=len(self.datasets):
            raise ValueError("Datasets duplicados")
        for d in self.datasets:
            if any(c in d.name for c in "[]:*?/\\") or d.name.lower()=="dashboard" or d.name.startswith("'") or d.name.endswith("'"):
                raise ValueError("Nombre de hoja inválido")
        for m in self.metrics:
            dataset = by_id.get(m.dataset_id)
            if not dataset:
                raise ValueError("Dataset inexistente en métrica")
            columns = {c.key:c for c in dataset.columns}
            if m.column not in columns:
                raise ValueError("Columna inexistente en métrica")
            if m.operation in ("sum","average","ratio_sums") and columns[m.column].kind not in ("number","ratio"):
                raise ValueError("Agregación sobre texto")
            if m.operation=="ratio_sums" and (m.denominator_column not in columns or columns[m.denominator_column].kind not in ("number","ratio")):
                raise ValueError("Denominador inválido")
            if m.operation=="count_equal" and m.equals is None:
                raise ValueError("Falta criterio de conteo")
        for chart in self.charts:
            d = by_id.get(chart.dataset_id)
            if not d:
                raise ValueError("Dataset inexistente en gráfica")
            columns = {c.key:c for c in d.columns}
            if chart.category_column not in columns or chart.value_column not in columns or columns[chart.value_column].kind not in ("number","ratio"):
                raise ValueError("Columnas inválidas en gráfica")
        return self


class Artifact(Model):
    title: str = Field(min_length=1, max_length=160)
    objective: str = Field(min_length=1, max_length=1500)
    audience: str
    executive_summary: str = Field(min_length=1, max_length=2500)
    decision: str = Field(min_length=1, max_length=1000)
    theme: Theme = Field(default_factory=Theme)
    assumptions: list[str] = Field(default_factory=list, max_length=30)
    sections: list[Section] = Field(min_length=1, max_length=40)
    findings: list[Finding] = Field(default_factory=list, max_length=60)
    risks: list[Risk] = Field(default_factory=list, max_length=60)
    controls: list[Control] = Field(default_factory=list, max_length=80)
    actions: list[Action] = Field(default_factory=list, max_length=80)
    kpis: list[KPI] = Field(default_factory=list, max_length=20)
    process: Process | None = None
    slides: list[Slide] = Field(min_length=1, max_length=35)
    source_ids: list[str] = Field(default_factory=list)
    workbook: WorkbookPlan | None = None

    @model_validator(mode="after")
    def relations(self):
        for name in ("sections", "findings", "risks", "controls", "actions", "kpis"):
            ids = [x.id for x in getattr(self, name)]
            if len(ids) != len(set(ids)):
                raise ValueError(f"IDs duplicados en {name}")
        risks = {x.id for x in self.risks}
        controls = {x.id for x in self.controls}
        if any(set(c.risk_ids) - risks for c in self.controls):
            raise ValueError("Control refiere riesgo inexistente")
        if any(set(a.control_ids) - controls for a in self.actions):
            raise ValueError("Acción refiere control inexistente")
        for slide in self.slides:
            if slide.dataset_id and (not self.workbook or slide.dataset_id not in {d.id for d in self.workbook.datasets}):
                raise ValueError("Dataset inexistente en lámina")
            if slide.chart!="none" and not slide.dataset_id:
                raise ValueError("Una gráfica requiere dataset_id")
        return self


class ChatRequest(Model):
    message: str = Field(min_length=1, max_length=12000)
    formats: list[Literal["docx", "pptx", "xlsx"]] = Field(default_factory=list, max_length=3)
    artifact_id: str | None = None


def all_citations(artifact: Artifact) -> set[str]:
    ids = set(artifact.source_ids)
    for group in (artifact.sections, artifact.findings, artifact.risks, artifact.kpis, artifact.slides):
        for item in group:
            ids.update(item.source_ids)
    if artifact.workbook:
        for dataset in artifact.workbook.datasets:
            ids.update(dataset.source_ids)
    return ids
