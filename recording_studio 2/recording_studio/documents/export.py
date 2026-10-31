"""Exporta la capacitación aprobada: PPTX, guía Word opcional, evaluación y evidencia."""
import json
from pathlib import Path
import re
import shutil
from zipfile import ZipFile,ZIP_DEFLATED
from recording_studio.application.assessment import export_assessment
from recording_studio.documents.powerpoint import powerpoint
from recording_studio.media.annotations import numbered_steps


def word_guide(plan,theme,path):
    """Genera una guía Word complementaria con los mismos pasos globales del PowerPoint."""
    from docx import Document
    from docx.shared import Inches,Pt,RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    doc=Document()
    # Elimina líneas heredadas bajo Title/Subtitle en la plantilla base.
    for border in list(doc.styles.element.iter(qn("w:pBdr"))):border.getparent().remove(border)
    section=doc.sections[0]
    section.top_margin=section.bottom_margin=Inches(.8)
    section.left_margin=section.right_margin=Inches(.85)
    normal=doc.styles["Normal"];normal.font.name=theme.font;normal.font.size=Pt(10.5)
    normal.paragraph_format.space_after=Pt(7);normal.paragraph_format.line_spacing=1.12
    for name in ("Title","Subtitle","Heading 1","Heading 2"):
        style=doc.styles[name];style.font.name=theme.font;style.font.color.rgb=RGBColor(0,0,0)
        style.paragraph_format.keep_with_next=True
    doc.styles["Title"].font.size=Pt(28);doc.styles["Heading 1"].font.size=Pt(17);doc.styles["Heading 2"].font.size=Pt(12)
    doc.add_paragraph(theme.client,"Subtitle");doc.add_paragraph(plan.title,"Title")
    doc.add_paragraph("Explicar y aplicar las actividades de la grabación.")
    doc.add_heading("Resumen ejecutivo",1);doc.add_paragraph(plan.summary)
    doc.add_heading("Decisión requerida",2);doc.add_paragraph("Aplicar el proceso y resolver la evaluación adjunta.")
    doc.add_heading("Valores y capturas de referencia",2)
    doc.add_paragraph("Los valores mostrados pueden cambiar según usuario, fecha o entorno. Las capturas son una muestra de la grabación.")
    for group in plan.groups:
        doc.add_heading(group.title,1);body=[doc.add_paragraph(group.objective)]
        body.extend(doc.add_paragraph(step,"List Bullet") for step in numbered_steps(plan,group.id))
        if group.dynamic_fields:body.append(doc.add_paragraph("Los valores mostrados pueden cambiar. Campos variables: "+", ".join(group.dynamic_fields),"List Bullet"))
        for paragraph in body[:-1]:paragraph.paragraph_format.keep_with_next=True
    footer=section.footer.paragraphs[0];footer.text=theme.client+"   "
    field=OxmlElement("w:fldSimple");field.set(qn("w:instr"),"PAGE");footer._p.append(field)
    doc.core_properties.title=plan.title;doc.core_properties.author="Recording Studio";doc.save(path)


def export_bundle(plan,assessment,theme,directory,frames,report=None,segments=None,include_word=True):
    """Exporta formatos y originales, manteniendo marcas editables y respuestas separadas."""
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    powerpoint(plan,theme,directory/"entregable.pptx",frames=frames)
    files=["entregable.pptx"]
    if include_word:
        word_guide(plan,theme,directory/"entregable.docx");files.append("entregable.docx")
    files+=export_assessment(assessment,directory)
    (directory/"plan.json").write_text(plan.model_dump_json(indent=2),encoding="utf-8");files.append("plan.json")
    (directory/"theme.json").write_text(theme.model_dump_json(indent=2),encoding="utf-8");files.append("theme.json")
    if report is not None:
        (directory/"video_analysis.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8");files.append("video_analysis.json")
    used={ref for group in plan.groups for ref in group.evidence_ids}
    evidence=[segment.model_dump() for segment in segments or [] if segment.id in used]
    (directory/"transcript_used.json").write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding="utf-8");files.append("transcript_used.json")
    for ref in sorted(used&set(frames)):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}",ref):raise ValueError("ID de frame inválido")
        source=Path(frames[ref]);suffix=source.suffix.lower()
        if suffix not in (".jpg",".jpeg",".png"):raise ValueError("Formato de captura no permitido")
        target=directory/"frames"/(ref+suffix);target.parent.mkdir(exist_ok=True)
        if source.resolve()!=target.resolve():shutil.copyfile(source,target)
        files.append(target.relative_to(directory).as_posix())
    with ZipFile(directory/"paquete.zip","w",ZIP_DEFLATED) as archive:
        for name in files:archive.write(directory/name,name)
    return files+["paquete.zip"]
