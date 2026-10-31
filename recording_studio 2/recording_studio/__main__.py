"""CLI del proyecto de grabaciones; los enlaces Graph se integran mediante RecordingService."""
import argparse
import json
from pathlib import Path
from recording_studio.application.demo import build_demo
from recording_studio.application.service import RecordingService
from recording_studio.domain.models import Principal
from recording_studio.infrastructure.config import Settings


def main():
    """Genera el ejemplo o procesa un archivo local autorizado con la configuración RS_."""
    parser=argparse.ArgumentParser(description="Grabaciones a PPTX, frames anotados y evaluación")
    parser.add_argument("command",choices=["demo","analyze","check"])
    parser.add_argument("--output",default="examples/recording_demo")
    parser.add_argument("--video");parser.add_argument("--subtitles")
    parser.add_argument("--brief",default="Explicar el proceso de la grabación, conservando decisiones y excepciones.")
    parser.add_argument("--tenant",default="local");parser.add_argument("--user",default="local")
    args=parser.parse_args();settings=Settings.from_env()
    if args.command=="demo":print("Ejemplo ficticio: "+", ".join(build_demo(args.output)))
    elif args.command=="check":print("Configuración de grabaciones válida; no se comprobó conectividad")
    else:
        if not args.video:parser.error("analyze requiere --video")
        subtitles=Path(args.subtitles).read_text(encoding="utf-8-sig") if args.subtitles else None
        result=RecordingService(settings).generate_file(Principal(tenant_id=args.tenant,user_id=args.user),args.video,args.brief,args.output,subtitles=subtitles,progress=print)
        print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
