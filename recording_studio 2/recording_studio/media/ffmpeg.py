"""Extrae audio y capturas por lote usando FFmpeg sin ejecutar comandos de shell."""
import json
from pathlib import Path
import subprocess
from recording_studio.media.models import Frame


class MediaTools:
    """Aísla los binarios multimedia para sustituirlos o probarlos sin videos reales."""
    def __init__(self,ffmpeg="ffmpeg",ffprobe="ffprobe",frames_per_batch=24):
        """Recibe rutas de binarios del servidor y un presupuesto de capturas por lote."""
        self.ffmpeg,self.ffprobe=ffmpeg,ffprobe
        self.frames_per_batch=frames_per_batch

    def _run(self,args):
        """Ejecuta un proceso sin shell, con timeout y errores que no revelan rutas privadas."""
        try:
            return subprocess.run(args,check=True,capture_output=True,timeout=600)
        except FileNotFoundError:
            raise RuntimeError("Configura FFmpeg y FFprobe en el servidor") from None
        except (subprocess.CalledProcessError,subprocess.TimeoutExpired):
            raise RuntimeError("No se pudo procesar el archivo multimedia") from None

    def duration(self,path):
        """Obtiene la duración real y rechaza archivos sin una duración utilizable."""
        result=self._run([self.ffprobe,"-v","error","-protocol_whitelist","file,pipe","-show_entries","format=duration","-of","json",str(path)])
        duration=float(json.loads(result.stdout)["format"]["duration"])
        if not 0<duration<=24*3600:raise ValueError("Duración inválida o mayor de 24 horas")
        return duration

    def prepare(self,path,batch,directory,need_audio):
        """Hace una extracción de capturas y, si hace falta, una de audio por lote extenso."""
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        length=batch.context_end-batch.context_start
        fps=self.frames_per_batch/length
        common=[self.ffmpeg,"-nostdin","-hide_banner","-loglevel","error","-y","-protocol_whitelist","file,pipe","-ss",str(batch.context_start),"-i",str(path),"-t",str(length)]
        self._run(common+["-an","-vf",f"fps={fps},scale=1280:-2","-frames:v",str(self.frames_per_batch),"-q:v","4",str(directory/"frame-%03d.jpg")])
        frames=[Frame(id=f"{batch.id}-F{i+1:03d}",timestamp=min(batch.context_end,batch.context_start+(i+.5)/fps),path=str(p)) for i,p in enumerate(sorted(directory.glob("frame-*.jpg")))]
        if not frames:raise ValueError("El archivo no contiene capturas de video")
        audio=None
        if need_audio:
            audio=directory/"audio.mp3"
            self._run(common+["-vn","-ac","1","-ar","16000","-b:a","32k",str(audio)])
        return frames,audio
