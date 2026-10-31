import argparse
import os
from pathlib import Path
from .config import Settings
from .engine import Engine
from .models import Principal
from .demo import sample
from .renderers import render
from .server import serve


def main():
    parser = argparse.ArgumentParser(description="Agente de gobierno de datos e IA")
    parser.add_argument("command",choices=["serve","demo","check"],nargs="?",default="serve")
    parser.add_argument("--output",default="examples/generated")
    args = parser.parse_args()
    settings = Settings.from_env()
    if args.command=="check":
        print("Configuración válida. No se ha comprobado conectividad ni compatibilidad de deployments.")
    elif args.command=="demo":
        spec = sample()
        files = render(spec,[],Path(args.output),["docx","pptx","xlsx"])
        print("Caso ficticio generado: " + ", ".join(files))
    else:
        engine = Engine(settings)
        if settings.mode=="demo":
            admin = Principal(tenant_id="demo",user_id="seed",role="admin")
            with engine.store.db() as db:
                exists = db.execute("SELECT 1 FROM chunks WHERE id='NIST-AIRMF'").fetchone()
            if not exists:
                engine.store.add_chunk(admin,"base","","NIST AI Risk Management Framework",
                    "https://www.nist.gov/itl/ai-risk-management-framework",
                    "El AI Risk Management Framework de NIST es un marco voluntario para gestionar riesgos de inteligencia artificial. Su uso no equivale a una certificación ni demuestra cumplimiento de obligaciones específicas.",chunk_id="NIST-AIRMF")
        serve(engine,os.getenv("GS_HOST","127.0.0.1"),int(os.getenv("GS_PORT","8080")))


if __name__=="__main__":
    main()
