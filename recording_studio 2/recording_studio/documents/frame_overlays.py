"""Superpone recuadros, flechas y números nativos sobre capturas sin modificar la imagen."""
from pptx.util import Inches,Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE,MSO_CONNECTOR
from pptx.enum.text import MSO_ANCHOR,PP_ALIGN
from pptx.oxml.xmlchemy import OxmlElement


def add_frame_overlays(slide,regions,image_rect,step_offset,color,font,foreground="FFFFFF"):
    """Transforma regiones 0..1 a pulgadas y vincula cada marca con el paso global.

    image_rect contiene la posición y tamaño reales de la captura ajustada sin recorte.
    Cada recuadro, flecha y etiqueta permanece como forma editable en PowerPoint.
    """
    left,top,width,height=image_rect
    labels=[]
    for region in regions:
        number=step_offset+region.step_index+1
        x=left+region.x*width;y=top+region.y*height
        w=region.width*width;h=region.height*height
        box=slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,Inches(x),Inches(y),Inches(w),Inches(h))
        box.name=f"Paso {number} / Recuadro"
        box.fill.background();box.line.color.rgb=RGBColor.from_string(color);box.line.width=Pt(2.25)
        label_x=max(left-.4,x-.52);target_y=y+h/2
        label_y=target_y-.16
        # Desplaza etiquetas coincidentes sin mover el recuadro que identifica el objetivo real.
        for shift in (0,-.38,.38,-.76,.76,-1.14,1.14):
            candidate=min(top+height-.32,max(top,label_y+shift))
            if all(abs(label_x-lx)>.34 or abs(candidate-ly)>.34 for lx,ly in labels):
                label_y=candidate;break
        labels.append((label_x,label_y))
        arrow=slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,Inches(label_x+.32),Inches(label_y+.16),Inches(x-.02),Inches(target_y))
        arrow.name=f"Paso {number} / Flecha";arrow.line.color.rgb=RGBColor.from_string(color);arrow.line.width=Pt(2)
        end=OxmlElement("a:tailEnd");end.set("type","triangle");arrow.line._get_or_add_ln().append(end)
        badge=slide.shapes.add_shape(MSO_SHAPE.OVAL,Inches(label_x),Inches(label_y),Inches(.32),Inches(.32))
        badge.name=f"Paso {number} / Etiqueta"
        badge.fill.solid();badge.fill.fore_color.rgb=RGBColor.from_string(color)
        badge.line.color.rgb=RGBColor(255,255,255);badge.line.width=Pt(.75)
        text=badge.text_frame;text.clear()
        text.margin_left=text.margin_right=text.margin_top=text.margin_bottom=0
        text.vertical_anchor=MSO_ANCHOR.MIDDLE
        paragraph=text.paragraphs[0];paragraph.text=str(number);paragraph.alignment=PP_ALIGN.CENTER
        paragraph.font.name=font;paragraph.font.size=Pt(12 if number<100 else 10)
        paragraph.font.bold=True;paragraph.font.color.rgb=RGBColor.from_string(foreground)
