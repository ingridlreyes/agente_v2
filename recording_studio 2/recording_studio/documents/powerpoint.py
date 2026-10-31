"""Presentaciones de capacitación con capturas, marcas editables y pasos continuos."""
from pathlib import Path
from types import SimpleNamespace


def rgb(value):
    """Normaliza un color hexadecimal para las bibliotecas de Office."""
    return value.lstrip("#")

def ink_on(color):
    """Escoge tinta negra o blanca según luminancia para mantener contraste."""
    c = rgb(color)
    r, g, b = (int(c[i:i+2], 16)/255 for i in (0, 2, 4))
    def linear(v):
        """Convierte un canal sRGB a luminancia lineal para calcular contraste."""
        return v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4
    lum = .2126*linear(r) + .7152*linear(g) + .0722*linear(b)
    return "000000" if lum > .179 else "FFFFFF"

def readable_brand(color):
    """Selecciona un color de marca que permita texto legible sobre fondo claro."""
    return color if ink_on(color)=="FFFFFF" else "#142D4E"


def presentation_spec(plan,theme):
    """Adapta el plan de video al layout aprobado sin depender de un agente conversacional."""
    return SimpleNamespace(title=plan.title,theme=theme,
        objective="Explicar y aplicar las actividades de la grabación.",
        decision="Aplicar el proceso y resolver la evaluación adjunta.",executive_summary=plan.summary,
        slides=[SimpleNamespace(layout="steps",title=g.title,message=g.objective,items=g.steps,
                evidence_ids=g.evidence_ids,frame_id=g.frame_id,annotations=g.annotations,dynamic_fields=g.dynamic_fields,
                notes=f"Intervalo de referencia {g.start:.1f}–{g.end:.1f} s. Evidencia: {', '.join(g.evidence_ids)}") for g in plan.groups])


def powerpoint(plan,theme,path,frames=None,logo=None):
    # Es un motor desplegable Python, no depende de herramientas del entorno de desarrollo.
    """Compone las láminas con texto, gráficos y diagramas nativos editables."""
    spec=presentation_spec(plan,theme)
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

    def text(slide, value, x, y, w, h, size=22, color="142D4E", bold=False):
        """Añade texto con posición, tamaño y color explícitos a la diapositiva."""
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
        """Crea la base de una lámina y aplica encabezado, mensaje y numeración."""
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
        """Guarda contexto y fuentes en las notas de la diapositiva."""
        slide.notes_slide.notes_text_frame.text = content

    cover = new_slide(spec.title, 1, True)
    text(cover, spec.objective, .75, 2.35, 10.8, 1.35, 25, ink_on(brand_primary))
    text(cover, "Decisión requerida", .75, 4.45, 10.8, .4, 16, ink_on(brand_primary), True)
    text(cover, spec.decision, .75, 5, 10.8, 1.4, 23, ink_on(brand_primary))
    notes(cover, spec.executive_summary)
    step_offset=0
    total_steps=sum(len(slide.items) for slide in spec.slides if slide.layout=="steps")
    for item in spec.slides:
        if item.layout=="steps":
            # Una pantalla con cuatro pasos siempre conserva los cuatro en una sola lámina.
            slide=new_slide(item.title,len(prs.slides)+1)
            text(slide,item.message,.75,1.95,11.6,.85,22,primary)
            # Una marca solo se aplica sobre su frame explícito; nunca sobre otra captura.
            frame_id=item.frame_id or next((ref for ref in item.evidence_ids if frames and ref in frames),None)
            frame=frames.get(frame_id) if frames and frame_id else None
            if item.annotations and not frame:
                raise ValueError("Falta la captura original para dibujar las marcas de la lámina")
            if frame:
                with Image.open(frame) as image:width,height=image.size
                scale=min(5.55/width,3.3/height)
                picture=slide.shapes.add_picture(str(frame),Inches(.8),Inches(3.0),width=Inches(width*scale),height=Inches(height*scale))
                picture.name="Frame "+frame_id
                if item.annotations:
                    from recording_studio.documents.frame_overlays import add_frame_overlays
                    add_frame_overlays(slide,item.annotations,(.8,3.0,width*scale,height*scale),step_offset,accent,spec.theme.font,ink_on(accent))
                for i,step in enumerate(item.items):
                    text(slide,f"Paso {step_offset+i+1}",6.75,2.95+i*.88,.85,.42,14,accent,True)
                    text(slide,step,7.75,2.95+i*.88,4.75,.86,16,primary)
            else:
                for i,step in enumerate(item.items):
                    x=.8+(i%2)*6.1;y=3.0+(i//2)*1.65
                    text(slide,f"Paso {step_offset+i+1}",x,y,1.15,.45,17,accent,True)
                    text(slide,step,x+1.2,y,4.6,1.3,20,primary)
            text(slide,f"Pasos {step_offset+1} a {step_offset+len(item.items)} de {total_steps}",.8,6.45,11.7,.25,11,primary)
            if item.dynamic_fields:
                text(slide,"Los valores mostrados pueden cambiar según el usuario, la fecha o el entorno.",.8,6.75,11.7,.25,11,primary)
            notes(slide,item.notes+f"\nPasos {step_offset+1} a {step_offset+len(item.items)} de {total_steps}."+"\nCampos variables: "+", ".join(item.dynamic_fields))
            step_offset+=len(item.items)
            continue
    prs.core_properties.title, prs.core_properties.author = spec.title, "Recording Studio"
    prs.save(path)
