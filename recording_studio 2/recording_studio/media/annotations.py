"""Valida regiones de frames y conserva su relación con pasos al consolidar actividades."""
from collections import defaultdict


def step_key(text):
    """Compara instrucciones conservando números y significado, normalizando solo espacios y caja."""
    return " ".join(text.casefold().split())


def numbered_steps(plan,group_id):
    """Devuelve los pasos de una actividad con numeración continua del 1 al total de la guía."""
    offset=0
    for group in plan.groups:
        if group.id==group_id:return [f"Paso {offset+i+1}. {step}" for i,step in enumerate(group.steps)]
        offset+=len(group.steps)
    raise ValueError("El grupo no pertenece al plan")


def validate_frame_reference(group,frames):
    """Rechaza regiones cuya captura no existe o no estuvo disponible como imagen local."""
    available={frame.id for frame in frames if frame.path}
    if group.frame_id and group.frame_id not in available:
        raise ValueError("El frame seleccionado no estuvo disponible como captura")
    if group.annotations and not group.frame_id:
        raise ValueError("No se pueden localizar regiones solo con una transcripción")


def restore_visual_annotations(plan,analyses):
    """Recupera marcas de origen, nunca coordenadas nuevas inventadas por el consolidado.

    Escoge una sola captura por actividad: la que conserva más pasos reconocibles.
    Si el consolidado cambia la redacción, no transfiere una marca a otro paso por posición.
    Las variantes que no estén en esa captura permanecen como texto sin marca inventada.
    """
    originals={group.id:group for analysis in analyses for group in analysis.groups}
    for group in plan.groups:
        candidates=defaultdict(dict)
        for origin_id in group.origin_ids:
            original=originals[origin_id]
            if not original.frame_id:continue
            candidates[original.frame_id]
            for region in original.annotations:
                key=step_key(original.steps[region.step_index])
                candidates[original.frame_id].setdefault(key,region)
        # El plan global puede proponer un ID, pero solo se aceptan capturas de sus orígenes.
        frame_id=max(candidates,key=lambda fid:sum(step_key(step) in candidates[fid] for step in group.steps),default=None)
        regions=[]
        if frame_id:
            for index,step in enumerate(group.steps):
                source=candidates[frame_id].get(step_key(step))
                if source:regions.append(source.model_copy(update={"step_index":index}))
        if frame_id and frame_id not in group.evidence_ids:
            group.evidence_ids=[frame_id]+group.evidence_ids[:39]
        group.frame_id=frame_id
        group.annotations=regions
    return plan
