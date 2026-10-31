"""Generadores portables en Python. Solo reciben modelos validados, nunca código del LLM."""
from __future__ import annotations
from html import escape
from pathlib import Path
import math
import textwrap
from .models import Artifact, Source


def rgb(value):
    return value.lstrip("#")


def ink_on(color):
    c = rgb(color)
    r, g, b = (int(c[i:i+2], 16)/255 for i in (0, 2, 4))
    def linear(v):
        return v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4
    lum = .2126*linear(r) + .7152*linear(g) + .0722*linear(b)
    return "000000" if lum > .179 else "FFFFFF"


def readable_brand(color):
    return color if ink_on(color)=="FFFFFF" else "#142D4E"


def insert_excel_logo(sheet,logo):
    if not logo:
        return
    from PIL import Image
    with Image.open(logo) as image:
        width,height=image.size
    scale=min(96/width,40/height)
    sheet.set_row(0,40)
    sheet.insert_image("K1",str(logo),{"x_scale":scale,"y_scale":scale,"object_position":1})


def svg_process(process, primary, accent, path):
    """SVG completo: carriles y flechas. Conserva ciclos y ramas sin convertirlos en secuencia."""
    cols = len(process.nodes)
    w, h = 180 + cols*200, 110 + len(process.lanes)*150
    positions = {n.id: (190+i*200, 120+process.lanes.index(n.lane)*150) for i, n in enumerate(process.nodes)}
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
           '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#526477"/></marker></defs>',
           '<rect width="100%" height="100%" fill="white"/>',
           f'<text x="24" y="36" font-family="Arial" font-size="22" fill="{primary}">{escape(process.title)}</text>']
    for i, lane in enumerate(process.lanes):
        y = 75+i*150
        out.append(f'<rect x="12" y="{y}" width="{w-24}" height="150" fill="{"#F1F5F9" if i%2==0 else "#FFFFFF"}" stroke="#D5DDE5"/>')
        for j, line in enumerate(textwrap.wrap(lane, 17)):
            out.append(f'<text x="22" y="{y+62+j*19}" font-family="Arial" font-size="15" fill="{primary}">{escape(line)}</text>')
    for idx, edge in enumerate(process.edges):
        x1, y1 = positions[edge.source]
        x2, y2 = positions[edge.target]
        bend = 58 + idx%3*14
        out.append(f'<path d="M{x1+160},{y1+35} C{x1+160+bend},{y1+35} {x2-bend},{y2+35} {x2},{y2+35}" fill="none" stroke="#526477" stroke-width="2" marker-end="url(#arrow)"/>')
        if edge.label:
            out.append(f'<text x="{(x1+x2+160)/2}" y="{(y1+y2)/2+20}" font-family="Arial" font-size="12" fill="#334155">{escape(edge.label)}</text>')
    for node in process.nodes:
        x, y = positions[node.id]
        fill = accent if node.kind == "decision" else primary
        if node.kind == "decision":
            out.append(f'<polygon points="{x+80},{y-12} {x+170},{y+35} {x+80},{y+82} {x-10},{y+35}" fill="{fill}"/>')
        else:
            out.append(f'<rect x="{x}" y="{y}" width="160" height="70" rx="{28 if node.kind in ("start","end") else 8}" fill="{fill}"/>')
        lines = textwrap.wrap(node.label, 20)
        for j, line in enumerate(lines):
            out.append(f'<text x="{x+80}" y="{y+24+j*16-(len(lines)-2)*4}" text-anchor="middle" font-family="Arial" font-size="13" fill="#{ink_on(fill)}">{escape(line)}</text>')
    out.append('</svg>')
    path.write_text("\n".join(out), encoding="utf-8")


def word(spec: Artifact, sources: list[Source], path: Path, logo=None):
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
    doc = Document()
    # Algunas plantillas base traen bordes heredados en Title/Subtitle.
    for border in list(doc.styles.element.iter(qn("w:pBdr"))):
        border.getparent().remove(border)
    sec = doc.sections[0]
    sec.top_margin = sec.bottom_margin = Inches(.8)
    sec.left_margin = sec.right_margin = Inches(.85)
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size = spec.theme.font, Pt(10.5)
    normal.paragraph_format.space_after = Pt(7)
    normal.paragraph_format.line_spacing = 1.12
    for name in ("Title", "Subtitle", "Heading 1", "Heading 2", "Heading 3"):
        doc.styles[name].font.name = spec.theme.font
        doc.styles[name].font.color.rgb = RGBColor(0, 0, 0)
        doc.styles[name].paragraph_format.keep_with_next = True
    doc.styles["Title"].font.size = Pt(28)
    doc.styles["Heading 1"].font.size = Pt(17)
    doc.styles["Heading 2"].font.size = Pt(12)
    if logo:
        from PIL import Image
        with Image.open(logo) as image:
            width,height=image.size
        doc.add_picture(str(logo), width=Inches(min(1.25,.65*width/height)))
    doc.add_paragraph(spec.theme.client, "Subtitle")
    doc.add_paragraph(spec.title, "Title")
    doc.add_paragraph(spec.objective)
    doc.add_heading("Resumen ejecutivo", 1)
    doc.add_paragraph(spec.executive_summary)
    doc.add_heading("Decisión requerida", 2)
    doc.add_paragraph(spec.decision)
    if spec.assumptions:
        doc.add_heading("Supuestos y datos pendientes", 2)
        for item in spec.assumptions:
            doc.add_paragraph(item, "List Bullet")

    def table(headers, rows, widths=None):
        t = doc.add_table(rows=1, cols=len(headers))
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        effective_widths = widths or [6.6/len(headers)]*len(headers)
        for col,width in zip(t.columns,effective_widths):
            col.width = Inches(width)
        for c, text in zip(t.rows[0].cells, headers):
            c.text = text
        for row in rows:
            for c, text in zip(t.add_row().cells, row):
                c.text = str(text)
        for ri, row in enumerate(t.rows):
            for ci, cell in enumerate(row.cells):
                cell.width = Inches(effective_widths[ci])
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                pr = cell._tc.get_or_add_tcPr()
                shade = OxmlElement("w:shd")
                shade.set(qn("w:fill"), rgb(spec.theme.primary) if ri == 0 else ("F2F5F8" if ri%2 else "FFFFFF"))
                pr.append(shade)
                borders = OxmlElement("w:tcBorders")
                for side in ("top", "left", "bottom", "right"):
                    el = OxmlElement("w:" + side)
                    el.set(qn("w:val"), "single")
                    el.set(qn("w:sz"), "4")
                    el.set(qn("w:color"), "D9D9D9")
                    borders.append(el)
                pr.append(borders)
                for p in cell.paragraphs:
                    p.paragraph_format.keep_with_next = len(rows)<=7 and ri<len(t.rows)-1
                    p.paragraph_format.space_after = Pt(5)
                    p.paragraph_format.space_before = Pt(5)
                    for run in p.runs:
                        run.font.size = Pt(9)
                        if ri == 0:
                            run.font.bold = True
                            run.font.color.rgb = RGBColor.from_string(ink_on(spec.theme.primary))
            if ri == 0:
                repeat = OxmlElement("w:tblHeader")
                row._tr.get_or_add_trPr().append(repeat)
            no_split = OxmlElement("w:cantSplit")
            row._tr.get_or_add_trPr().append(no_split)
        doc.add_paragraph()
        return t

    for section in spec.sections:
        doc.add_heading(section.heading, 1)
        for p in section.paragraphs:
            doc.add_paragraph(p)
        for item in section.bullets:
            doc.add_paragraph(item, "List Bullet")
        if section.source_ids:
            doc.add_paragraph("Fuentes: " + ", ".join(section.source_ids), "Caption")
    if spec.findings:
        doc.add_heading("Hallazgos e implicaciones", 1)
        for f in spec.findings:
            doc.add_heading(f.id + " " + {"fact": "Hecho", "assumption": "Supuesto", "recommendation": "Recomendación"}[f.kind], 2)
            doc.add_paragraph(f.statement)
            doc.add_paragraph("Implicación: " + f.implication)
            if f.source_ids:
                doc.add_paragraph("Fuentes: " + ", ".join(f.source_ids), "Caption")
    if spec.process:
        proc = spec.process
        heading = doc.add_heading(proc.title, 1)
        heading.paragraph_format.page_break_before = True
        # Tabla de carriles nativa: editable en Word. Paginar en bloques de tres actividades.
        for offset in range(0, len(proc.nodes), 3):
            nodes = proc.nodes[offset:offset+3]
            table(["Responsable"] + [f"Paso {offset+i+1}" for i in range(len(nodes))],
                  [[lane] + [(n.id + "\n" + n.label + ("\nDecisión" if n.kind == "decision" else "")) if n.lane == lane else "" for n in nodes] for lane in proc.lanes])
        table(["Origen", "Destino", "Condición"], [[e.source, e.target, e.label or "Continuar"] for e in proc.edges], [1.3, 1.3, 4.0])
    if spec.risks:
        doc.add_heading("Registro de riesgos", 1)
        table(["ID", "Riesgo y causa", "Consecuencia", "Responsable propuesto"],
              [[r.id, r.title + "\n" + r.cause, r.consequence, r.owner] for r in spec.risks], [.5, 2.2, 2.2, 1.7])
    if spec.controls:
        doc.add_heading("Controles y evidencia", 1)
        for c in spec.controls:
            doc.add_heading(c.id + " " + c.activity, 2)
            doc.add_paragraph(f"Riesgos: {', '.join(c.risk_ids)}. Responsable: {c.owner}. Frecuencia: {c.frequency}.")
            doc.add_paragraph("Evidencia esperada: " + c.evidence)
            doc.add_paragraph("Criterio de aceptación: " + c.acceptance)
    if spec.actions:
        doc.add_heading("Plan de ejecución", 1)
        for a in spec.actions:
            doc.add_heading(a.id + " " + a.action, 2)
            doc.add_paragraph(f"Responsable: {a.owner}. Horizonte: {a.horizon}. Estado: {a.status}.")
            doc.add_paragraph("Aceptación: " + a.acceptance + ". Controles: " + ", ".join(a.control_ids))
    if spec.kpis:
        doc.add_heading("Indicadores de seguimiento", 1)
        for k in spec.kpis:
            doc.add_heading(k.id + " " + k.name, 2)
            paragraph = doc.add_paragraph(k.definition + " Responsable: " + k.owner + ".")
            paragraph.paragraph_format.keep_with_next = True
            if k.numerator is None or (k.unit == "ratio" and k.denominator in (None, 0)):
                doc.add_paragraph("Resultado no disponible. Falta capturar la medición y su población aplicable.")
    if sources:
        doc.add_heading("Fuentes consultadas", 1)
        for s in sources:
            doc.add_paragraph(f"[{s.id}] {s.title}. {s.locator}")
    footer = sec.footer.paragraphs[0]
    footer.text = spec.theme.client + "   "
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    doc.core_properties.title = spec.title
    doc.core_properties.author = "Governance Studio"
    doc.save(path)


def powerpoint(spec: Artifact, sources: list[Source], path: Path, logo=None):
    # Es un motor desplegable Python, no depende de herramientas del entorno de desarrollo.
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.oxml.xmlchemy import OxmlElement
    from PIL import Image
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    brand_primary = rgb(spec.theme.primary)
    primary, accent = rgb(readable_brand(spec.theme.primary)), rgb(spec.theme.accent)
    source_map = {s.id: s for s in sources}

    def text(slide, value, x, y, w, h, size=22, color="142D4E", bold=False):
        shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = shape.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(.02)
        tf.margin_top = tf.margin_bottom = 0
        for i, line in enumerate(str(value).split("\n")):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = line
            p.font.name, p.font.size = spec.theme.font, Pt(size)
            p.font.bold = bold
            p.font.color.rgb = RGBColor.from_string(color)
            p.space_after = Pt(10)
        return shape

    def new_slide(title, n, dark=False):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = RGBColor.from_string(brand_primary if dark else "FFFFFF")
        fg = ink_on(brand_primary) if dark else primary
        text(slide, title, .7, .62, 11.9, 1.35, 32, fg, True)
        text(slide, spec.theme.client, .72, 7.05, 10.5, .25, 10, fg)
        text(slide, f"{n:02d}", 12, 7.02, .6, .3, 11, fg)
        if logo:
            with Image.open(logo) as im:
                width, height = im.size
            ww, hh = 1.1, 1.1*height/width
            if hh > .5:
                hh, ww = .5, .5*width/height
            slide.shapes.add_picture(str(logo), Inches(11.9-ww), Inches(6.96), width=Inches(ww), height=Inches(hh))
        return slide

    def notes(slide, content):
        slide.notes_slide.notes_text_frame.text = content

    def process_pages(proc, n):
        # Cada bloque conserva IDs. Conexiones entre láminas se documentan explícitamente.
        page_size = 3 if max(len(node.label) for node in proc.nodes)>60 or len(proc.lanes)>5 else 5
        node_width = 2.5 if page_size==3 else 1.6
        step = 3.25 if page_size==3 else 1.95
        for offset in range(0, len(proc.nodes), page_size):
            group = proc.nodes[offset:offset+page_size]
            slide = new_slide(proc.title + (f" {offset//page_size+1}" if len(proc.nodes)>page_size else ""), len(prs.slides)+1)
            active_lanes = [lane for lane in proc.lanes if any(n.lane==lane for n in group)]
            lane_h = min(1.3, 4.25/len(active_lanes))
            top = 2.05
            pos = {}
            for i, lane in enumerate(active_lanes):
                text(slide, lane, .72, top+i*lane_h+.12, 1.65, lane_h-.12, 13, primary, True)
                line = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(2.5), Inches(top+(i+1)*lane_h), Inches(12.6), Inches(top+(i+1)*lane_h))
                line.line.color.rgb = RGBColor.from_string("D8E0E8")
            for i, node in enumerate(group):
                x, y = 2.7+i*step, top+active_lanes.index(node.lane)*lane_h+.09
                kind = MSO_SHAPE.DIAMOND if node.kind == "decision" else MSO_SHAPE.ROUNDED_RECTANGLE
                height = lane_h-.2
                shape = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(node_width), Inches(height))
                shape.fill.solid()
                color = accent if node.kind == "decision" else primary
                shape.fill.fore_color.rgb = RGBColor.from_string(color)
                shape.line.fill.background()
                shape.text = ""
                shape.text_frame.word_wrap = True
                shape.text_frame.margin_left = shape.text_frame.margin_right = Inches(.06)
                shape.text_frame.margin_top = shape.text_frame.margin_bottom = Inches(.02)
                shape.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
                # Separar texto de geometría evita las sangrías automáticas del rombo.
                wrap_width = (20 if node.kind=="decision" else 32) if page_size==3 else (14 if node.kind=="decision" else 23)
                wrapped = "\n".join(textwrap.wrap(node.label,wrap_width))
                label = text(slide,node.id+"\n"+wrapped,x+.05,y+.04,node_width-.1,height-.08,10 if len(node.label)>50 else 11,ink_on(color))
                label.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
                for p in label.text_frame.paragraphs:
                    p.alignment = PP_ALIGN.CENTER
                    p.space_after = Pt(0)
                effect = OxmlElement("a:effectLst")
                shape._element.spPr.append(effect)
                pos[node.id] = (x, y, height)
            external = []
            for edge in proc.edges:
                if edge.source in pos and edge.target in pos:
                    x1, y1, hh = pos[edge.source]
                    x2, y2, _ = pos[edge.target]
                    if x2<=x1:
                        # Retornos por un canal inferior, fuera de cajas y carriles.
                        bottom=6.22
                        points=[(x1+node_width/2,y1+hh),(x1+node_width/2,bottom),(x2-.13,bottom),(x2-.13,y2+hh/2),(x2,y2+hh/2)]
                    else:
                        middle=(x1+node_width+x2)/2
                        points=[(x1+node_width,y1+hh/2),(middle,y1+hh/2),(middle,y2+hh/2),(x2,y2+hh/2)]
                    for first,last in zip(points,points[1:]):
                        line = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,Inches(first[0]),Inches(first[1]),Inches(last[0]),Inches(last[1]))
                        line.line.color.rgb = RGBColor.from_string("6C7F91")
                    tail = OxmlElement("a:tailEnd")
                    tail.set("type", "triangle")
                    line.line._get_or_add_ln().append(tail)
                    if edge.label:
                        if x2<=x1:
                            text(slide,edge.label,(x1+x2)/2,6.28,1.5,.35,10,primary)
                        else:
                            text(slide,edge.label,x1+node_width-.02,(y1+y2+hh)/2-.28,1.2,.35,9,primary)
                elif edge.source in pos or edge.target in pos:
                    external.append(f"{edge.source} a {edge.target}: {edge.label or 'continuar'}")
            if external:
                text(slide, "Conexiones entre páginas: " + "; ".join(external), .75, 6.55, 11.8, .35, 11, primary)
            notes(slide, "\n".join(f"{e.source} → {e.target}: {e.label}" for e in proc.edges))

    cover = new_slide(spec.title, 1, True)
    text(cover, spec.objective, .75, 2.35, 10.8, 1.35, 25, ink_on(brand_primary))
    text(cover, "Decisión requerida", .75, 4.45, 10.8, .4, 16, ink_on(brand_primary), True)
    text(cover, spec.decision, .75, 5, 10.8, 1.4, 23, ink_on(brand_primary))
    notes(cover, spec.executive_summary)
    for item in spec.slides:
        if item.layout == "process" and spec.process:
            process_pages(spec.process, len(prs.slides)+1)
            continue
        # Dividir contenido antes que reducirlo hasta hacerlo ilegible.
        chunks = []
        for value in item.items:
            chunks.extend(textwrap.wrap(value, 145) or [""])
        chunks = [chunks[i:i+4] for i in range(0, len(chunks), 4)] or [[]]
        for part, items in enumerate(chunks):
            title = item.title + (f" {part+1}" if len(chunks)>1 else "")
            slide = new_slide(title, len(prs.slides)+1)
            text(slide, item.message, .75, 1.9, 11.6, 1.1, 24, primary)
            if item.dataset_id and item.chart!="none" and spec.workbook:
                from pptx.chart.data import CategoryChartData
                from pptx.enum.chart import XL_CHART_TYPE
                dataset = next(d for d in spec.workbook.datasets if d.id==item.dataset_id)
                numeric = next((i for i,c in enumerate(dataset.columns) if c.kind in ("number","ratio")),None)
                category = next((i for i,c in enumerate(dataset.columns) if c.kind in ("text","date")),0)
                if numeric is not None and dataset.rows:
                    data = CategoryChartData()
                    data.categories = [str(r.values[category] or "") for r in dataset.rows]
                    data.add_series(dataset.columns[numeric].label,[r.values[numeric] for r in dataset.rows])
                    kind = {"bar":XL_CHART_TYPE.BAR_CLUSTERED,"column":XL_CHART_TYPE.COLUMN_CLUSTERED,"line":XL_CHART_TYPE.LINE}[item.chart]
                    chart = slide.shapes.add_chart(kind,Inches(.9),Inches(3.1),Inches(11.5),Inches(3.4),data).chart
                    chart.has_legend=False
                    for series in chart.series:
                        series.format.fill.solid()
                        series.format.fill.fore_color.rgb=RGBColor.from_string(accent)
                        series.format.line.color.rgb=RGBColor.from_string(accent)
            elif item.layout == "comparison" and len(items)>=2:
                half = math.ceil(len(items)/2)
                text(slide, "\n\n".join(items[:half]), .75, 3.35, 5.4, 2.9, 21, primary)
                text(slide, "\n\n".join(items[half:]), 6.8, 3.35, 5.65, 2.9, 21, primary)
            elif item.layout == "roadmap":
                for i, value in enumerate(items):
                    text(slide, f"{i+1:02d}", .75, 3.1+i*.77, .7, .5, 24, accent, True)
                    text(slide, value, 1.65, 3.1+i*.77, 10.6, .7, 20, primary)
            else:
                for i, value in enumerate(items):
                    text(slide, value, .8, 3.25+i*.76, 11.5, .72, 21, primary)
            refs = [f"[{sid}] {source_map[sid].title}. {source_map[sid].locator}" for sid in item.source_ids if sid in source_map]
            notes(slide, item.notes + "\n" + "\n".join(refs))
    # Si el plan del modelo olvidó incluir el proceso solicitado, no se pierde.
    if spec.process and not any(s.layout == "process" for s in spec.slides):
        process_pages(spec.process, len(prs.slides)+1)
    prs.core_properties.title, prs.core_properties.author = spec.title, "Governance Studio"
    prs.save(path)


def excel(spec: Artifact, sources: list[Source], path: Path, logo=None):
    if spec.workbook:
        from .workbooks import flexible_excel
        return flexible_excel(spec,sources,path,logo)
    import xlsxwriter
    wb = xlsxwriter.Workbook(path, {"strings_to_formulas": False, "strings_to_urls": False})
    wb.set_calc_mode("auto")
    primary, accent = spec.theme.primary, spec.theme.accent
    title = wb.add_format({"font_name": spec.theme.font, "font_size": 24, "bold": True, "font_color": readable_brand(primary)})
    sub = wb.add_format({"font_name": spec.theme.font, "font_size": 11, "font_color": "#526477", "text_wrap": True, "valign": "vcenter"})
    header = wb.add_format({"bold": True, "bg_color": primary, "font_color": "#"+ink_on(primary), "text_wrap": True, "valign": "vcenter"})
    cell = wb.add_format({"font_name": spec.theme.font, "font_size": 11, "text_wrap": True, "valign": "vcenter"})
    input_fmt = wb.add_format({"font_name": spec.theme.font, "font_size": 11, "font_color": "#1565C0", "bg_color": "#F1F7FC", "text_wrap": True, "valign": "vcenter"})
    num = wb.add_format({"num_format": "0.0", "font_color": "#1565C0", "bg_color": "#F1F7FC"})
    ratio = wb.add_format({"num_format": "0.0%", "font_size": 13, "font_color": accent})
    big = wb.add_format({"font_size": 30, "bold": True, "font_color": primary, "num_format": "0"})
    tabs = {}
    dash = wb.add_worksheet("Dashboard")
    dash.hide_gridlines(2)
    dash.set_column("A:A", 3)
    dash.set_column("B:M", 12)
    dash.merge_range("B2:M3", spec.title, title)
    dash.merge_range("B4:M5", spec.decision, sub)
    dash.merge_range("B6:M6", "Conteos del plan propuesto. No representan madurez ni cumplimiento del cliente.", sub)
    insert_excel_logo(dash,logo)

    def sheet(name, headers, rows, widths):
        ws = wb.add_worksheet(name)
        tabs[name] = ws
        ws.hide_gridlines(2)
        ws.freeze_panes(4, 1)
        ws.set_tab_color(accent)
        ws.merge_range(0, 0, 0, len(headers)-1, name, title)
        ws.merge_range(1, 0, 1, len(headers)-1, "Campos azules editables. Mantén IDs y relaciones para conservar trazabilidad.", sub)
        ws.set_row(1, 30)
        for i, width in enumerate(widths):
            ws.set_column(i, i, width)
        for i, label in enumerate(headers):
            ws.write_string(3, i, label, header)
        ws.set_row(3, 32)
        for ri, row in enumerate(rows, 4):
            ws.set_row(ri, 62)
            for ci, value in enumerate(row):
                if value is None:
                    ws.write_blank(ri, ci, None, input_fmt)
                elif isinstance(value, (int, float)):
                    ws.write_number(ri, ci, value, num)
                else:
                    ws.write_string(ri, ci, str(value), input_fmt)
        if rows:
            ws.add_table(3, 0, 3+len(rows), len(headers)-1, {"name": "T"+name, "style": None, "columns": [{"header": h,"header_format":header} for h in headers]})
        ws.set_landscape()
        ws.fit_to_pages(1, 0)
        ws.repeat_rows(3)
        return ws

    risks = sheet("Riesgos", ["ID", "Riesgo", "Causa", "Consecuencia", "Responsable", "Probabilidad", "Impacto", "Exposición", "Fuentes"],
                  [[r.id, r.title, r.cause, r.consequence, r.owner, r.probability, r.impact, None, ", ".join(r.source_ids)] for r in spec.risks], [10,32,35,35,24,15,13,15,25])
    for i, r in enumerate(spec.risks, 5):
        cached = r.probability*r.impact if r.probability is not None and r.impact is not None else ""
        risks.write_formula(i-1, 7, f'=IF(OR(F{i}="",G{i}=""),"",F{i}*G{i})', cell, cached)
    if spec.risks:
        risks.data_validation(4, 5, 3+len(spec.risks), 6, {"validate":"integer", "criteria":"between", "minimum":1,"maximum":5, "error_type":"stop", "show_error":True})
        risks.conditional_format(4, 7, 3+len(spec.risks), 7, {"type": "3_color_scale", "min_color":"#E2F2EC", "mid_color":"#FFE9A6", "max_color":"#EAA5A5"})
    controls = sheet("Controles", ["ID", "Riesgos", "Actividad", "Responsable", "Frecuencia", "Evidencia", "Aceptación", "Estado"],
                     [[c.id, ", ".join(c.risk_ids), c.activity, c.owner, c.frequency, c.evidence, c.acceptance, c.status] for c in spec.controls], [10,14,40,24,20,38,40,20])
    if spec.controls:
        controls.data_validation(4,7,3+len(spec.controls),7,{"validate":"list","source":["Propuesto","En curso","Implementado"]})
    actions = sheet("Acciones", ["ID", "Controles", "Acción", "Responsable", "Horizonte", "Aceptación", "Estado"],
                    [[a.id, ", ".join(a.control_ids), a.action, a.owner, a.horizon, a.acceptance, a.status] for a in spec.actions], [10,14,42,24,24,45,20])
    if spec.actions:
        actions.data_validation(4,6,3+len(spec.actions),6,{"validate":"list","source":["Pendiente","En curso","Completada"]})
    kpis = sheet("Indicadores", ["ID", "Indicador", "Definición", "Numerador", "Denominador", "Meta", "Resultado", "Unidad", "Responsable", "Fuentes"],
                 [[k.id,k.name,k.definition,k.numerator,k.denominator,k.target,None,k.unit,k.owner,", ".join(k.source_ids)] for k in spec.kpis], [10,32,46,16,16,16,16,12,25,25])
    for i, k in enumerate(spec.kpis, 5):
        formula = f'=IF(NOT(ISNUMBER(D{i})),"",IF(H{i}="number",D{i},IF(OR(NOT(ISNUMBER(E{i})),E{i}=0),"",D{i}/E{i})))'
        cached = k.numerator if k.unit == "number" else (k.numerator/k.denominator if k.numerator is not None and k.denominator not in (None,0) else "")
        kpis.write_formula(i-1, 6, formula, ratio if k.unit=="ratio" else num, cached if cached is not None else "")
        if k.unit == "ratio":
            kpis.write_blank(i-1, 5, None, ratio) if k.target is None else kpis.write_number(i-1,5,k.target,ratio)
    # Datos y fuentes juntos. No se coloca contenido privado de otras conversaciones.
    ref_rows = [[s.id, s.title, s.locator, s.scope] for s in sources]
    ref_rows += [[f"SUP-{i+1}", a, "Supuesto por validar", "supuesto"] for i,a in enumerate(spec.assumptions)]
    sheet("Referencias", ["ID", "Fuente o supuesto", "Ubicación", "Tipo"], ref_rows, [16,65,85,18])

    # Rangos limitados al conjunto actual; tablas se expanden, dashboard requiere regeneración
    # al añadir registros. Edición de valores existentes recalcula sin regeneración.
    nr, nc, na = max(5,4+len(spec.risks)), max(5,4+len(spec.controls)), max(5,4+len(spec.actions))
    dash.merge_range("B8:D8", "Riesgos identificados", sub)
    dash.merge_range("F8:H8", "Controles definidos", sub)
    dash.merge_range("J8:L8", "Acciones propuestas", sub)
    for rng, formula, cached in [("B9:D10",f'=COUNTA(Riesgos!A5:A{nr})',len(spec.risks)),
                                 ("F9:H10",f'=COUNTA(Controles!A5:A{nc})',len(spec.controls)),
                                 ("J9:L10",f'=COUNTA(Acciones!A5:A{na})',len(spec.actions))]:
        dash.merge_range(rng, "", big)
        cellname = rng.split(":")[0]
        dash.write_formula(cellname, formula, big, cached)
    dash.merge_range("B13:C13", "Estado del control", header)
    dash.write("D13", "Cantidad", header)
    for row, status in enumerate(("Propuesto", "En curso", "Implementado"), 14):
        dash.merge_range(f"B{row}:C{row}", status, cell)
        formula = f'=COUNTIFS(Controles!H5:H{nc},B{row})'
        dash.write_formula(f"D{row}", formula, cell, sum(c.status == status for c in spec.controls))
    chart = wb.add_chart({"type":"bar"})
    chart.add_series({"name":"Controles", "categories":"=Dashboard!$B$14:$B$16", "values":"=Dashboard!$D$14:$D$16", "fill":{"color":accent}, "data_labels":{"value":True}})
    chart.set_title({"name":"Implementación de controles"})
    chart.set_legend({"none":True})
    chart.set_x_axis({"min":0,"major_unit":1,"name":"Número de controles"})
    chart.set_chartarea({"border":{"none":True}})
    dash.insert_chart("F13", chart, {"x_scale":1.15,"y_scale":1.0})
    dash.merge_range("B30:M31", "Indicadores de resultado", title)
    dash.merge_range("B32:M32", "Sin medición, el resultado permanece vacío. Captura datos en Indicadores.", sub)
    for row, k in enumerate(spec.kpis, 34):
        sr = row-29
        dash.merge_range(row-1,1,row-1,7,k.name,cell)
        cached = k.numerator if k.unit=="number" else (k.numerator/k.denominator if k.numerator is not None and k.denominator not in (None,0) else "")
        dash.write_formula(row-1,9,f'=IF(ISNUMBER(Indicadores!G{sr}),Indicadores!G{sr},"")', ratio if k.unit=="ratio" else cell, cached if cached is not None else "")
    dash.merge_range(35+len(spec.kpis),1,36+len(spec.kpis),12,"Al editar registros existentes, fórmulas y gráfica se actualizan en Excel. Para agregar o eliminar registros, pide una nueva versión al agente.",sub)
    dash.set_landscape()
    dash.fit_to_pages(1,1)
    dash.print_area(0,0,38+len(spec.kpis),12)
    wb.close()


def render(spec, sources, directory, formats, logo=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    files = []
    for fmt in dict.fromkeys(formats):
        path = directory / ("entregable." + fmt)
        {"docx":word, "pptx":powerpoint, "xlsx":excel}[fmt](spec, sources, path, logo)
        files.append(path.name)
    if spec.process:
        svg_process(spec.process, spec.theme.primary, spec.theme.accent, directory/"proceso.svg")
        files.append("proceso.svg")
        if "pptx" not in formats:
            # Diagrama complementario con formas nativas, aunque el usuario solo solicite Word.
            companion = spec.model_copy(update={"slides": [s for s in spec.slides if s.layout=="process"] or spec.slides[:1]})
            powerpoint(companion, sources, directory/"proceso_editable.pptx", logo)
            files.append("proceso_editable.pptx")
    (directory/"artifact.json").write_text(spec.model_dump_json(indent=2),encoding="utf-8")
    (directory/"sources.json").write_text(__import__("json").dumps([s.model_dump() for s in sources],ensure_ascii=False,indent=2),encoding="utf-8")
    return files + ["artifact.json", "sources.json"]
