"""Planifica ventanas largas y lee subtítulos sin cortar un video en cientos de fragmentos."""
import re
from recording_studio.media.models import Batch,Segment


def plan_batches(duration,target_seconds=900,overlap_seconds=15):
    """Divide por ventanas de 15 minutos y absorbe una cola corta en el lote anterior."""
    if duration<=0 or not 300<=target_seconds<=1800 or not 0<=overlap_seconds<=60:
        raise ValueError("Duración o configuración de lotes inválida")
    spans=[]
    start=0.0
    while start<duration:
        end=min(start+target_seconds,duration)
        if 0<duration-end<target_seconds*.4:end=duration
        spans.append((start,end));start=end
    return [Batch(id=f"B{i+1:04d}",start=a,end=b,context_start=max(0,a-overlap_seconds),context_end=min(duration,b+overlap_seconds)) for i,(a,b) in enumerate(spans)]


def seconds(value):
    """Convierte un timestamp VTT/SRT en segundos sin depender de la configuración regional."""
    values=value.replace(",",".").split(":")
    if len(values) not in (2,3):raise ValueError("Timestamp inválido")
    return sum(float(x)*60**i for i,x in enumerate(reversed(values)))


def parse_subtitles(text):
    """Lee VTT o SRT, conserva tiempos y elimina solamente las etiquetas del formato."""
    segments=[]
    blocks=re.split(r"\n\s*\n",text.replace("\r\n","\n").lstrip("\ufeff"))
    for block in blocks:
        lines=block.splitlines()
        timestamp=next((i for i,line in enumerate(lines) if "-->" in line),None)
        if timestamp is None:continue
        left,right=lines[timestamp].split("-->",1)
        start,end=seconds(left.strip()),seconds(right.strip().split()[0])
        content=re.sub(r"<[^>]*>",""," ".join(lines[timestamp+1:])).strip()
        if content:segments.append(Segment(id=f"T{len(segments)+1:05d}",start=start,end=end,text=content))
    if not segments:raise ValueError("No se encontraron subtítulos con tiempos")
    return sorted(segments,key=lambda s:(s.start,s.end))


def select_segments(segments,batch):
    """Incluye las frases que se cruzan con el borde compartido para preservar contexto."""
    return [s for s in segments if s.start<batch.context_end and s.end>batch.context_start]
