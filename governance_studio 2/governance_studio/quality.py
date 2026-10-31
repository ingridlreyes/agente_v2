from .models import Artifact, all_citations


def review(spec: Artifact, sources):
    known = {s.id for s in sources}
    unknown = all_citations(spec) - known
    errors, warnings = [], []
    if unknown:
        errors.append("Citas inexistentes: " + ", ".join(sorted(unknown)))
    for f in spec.findings:
        if f.kind == "fact" and not f.source_ids:
            errors.append(f"{f.id}: un hecho requiere al menos una fuente")
    for r in spec.risks:
        if not any(r.id in c.risk_ids for c in spec.controls):
            warnings.append(f"{r.id}: riesgo sin control definido")
    for c in spec.controls:
        if not any(c.id in a.control_ids for a in spec.actions) and c.status != "Implementado":
            warnings.append(f"{c.id}: control sin acción de implementación")
    if not sources:
        warnings.append("Sin fuentes recuperadas. El contenido debe revisarse como propuesta, no como diagnóstico comprobado.")
    if not spec.kpis:
        warnings.append("Sin indicadores de resultado definidos")
    if any(k.numerator is None for k in spec.kpis):
        warnings.append("Hay indicadores pendientes de medición")
    warnings.append("Las citas se validaron por identidad. Su soporte semántico y la calidad visual requieren revisión humana.")
    return {"errors": errors, "warnings": warnings, "status":"blocked" if errors else "requires_review",
            "checks": ["schema", "unique_ids", "risk_control_action_links", "source_ids", "missing_measurements"],
            "visual_review": "not_performed_at_runtime"}
