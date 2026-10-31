"""Reproduce los outputs visuales aprobados usando capturas ficticias y regiones conocidas."""
from pathlib import Path
from recording_studio.domain.models import Assessment,Theme
from recording_studio.media.models import VideoPlan
from recording_studio.documents.export import export_bundle


FIXTURES=Path(__file__).parent/"fixtures"


def build_demo(directory,theme=None):
    """Crea cuatro láminas, doce pasos, doce marcas nativas y diez preguntas de demostración."""
    plan=VideoPlan.model_validate_json((FIXTURES/"plan.json").read_text())
    assessment=Assessment.model_validate_json((FIXTURES/"evaluacion.json").read_text())
    theme=theme or Theme.model_validate_json((FIXTURES/"theme.json").read_text())
    frames={path.stem:str(path) for path in (FIXTURES/"frames").iterdir()}
    report={"mode":"demo","simulated":True,"slides_with_cover":4,"groups":3,"steps":12,"annotated_steps":12,
            "note":"Capturas ficticias y coordenadas conocidas; no se analizó una grabación real."}
    return export_bundle(plan,assessment,theme,directory,frames,report=report)
