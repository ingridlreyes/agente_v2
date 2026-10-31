"""Prueba HTTP contra un servidor DEMO ya iniciado. No utiliza servicios remotos.
python tests/http_smoke.py http://127.0.0.1:8080
"""
import base64
import io
import json
import sys
import time
from urllib import request,error
from zipfile import ZipFile


def run(base):
    token=""
    checks=[]
    def call(path,body=None,raw=False,authenticated=True):
        headers={"Content-Type":"application/json"}
        if authenticated:headers["Authorization"]="Bearer "+token
        req=request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        with request.urlopen(req,timeout=240) as r:
            data=r.read()
            return data if raw else json.loads(data)
    def check(name,value):
        if not value:raise AssertionError(name)
        checks.append(name)
    def wait(jid):
        for _ in range(300):
            job=call("/api/jobs/"+jid)
            if job["status"] in ("completed","failed"):return job
            time.sleep(.1)
        raise AssertionError("El trabajo excedió 30 segundos en demo")

    check("servidor en modo demo",call("/health")["mode"]=="demo")
    token=call("/api/demo-session",{})["token"]
    cid=call("/api/conversations",{})["conversation_id"]
    check("crear y leer conversación",call("/api/conversations/"+cid)["conversation_id"]==cid)
    base64_text=base64.b64encode("El dueño del dato del dominio proveedores es la función de Compras. DATO-FICTICIO-TEST".encode()).decode()
    attachment=call(f"/api/conversations/{cid}/attachments",{"filename":"contexto.txt","data_base64":base64_text,"scope":"conversation"})
    check("ingesta de contexto",attachment["chunks"]==1)
    answer=call(f"/api/conversations/{cid}/messages",{"message":"Consulta gobierno de datos del dominio proveedores"})
    check("consulta sin generación",answer["type"]=="answer")
    check("contexto recuperado autorizado","DATO-FICTICIO-TEST" in answer["text"])
    check("memoria persistente",bool(call("/api/conversations/"+cid)["memory"]["facts"]))
    result=call(f"/api/conversations/{cid}/messages",{"message":"Genera Word, PowerPoint y Excel para gobierno de proveedores","formats":["docx","pptx","xlsx"]})
    job=wait(result["job_id"])
    check("generación asíncrona",job["status"]=="completed")
    aid=job["result"]["artifact_id"]
    for fmt in ("docx","pptx","xlsx"):
        binary=call(f"/api/artifacts/{aid}/files/entregable.{fmt}?version=1",raw=True)
        with ZipFile(io.BytesIO(binary)) as z:check("descarga válida "+fmt,z.testzip() is None)
    before=call(f"/api/artifacts/{aid}?version=1")
    revision=call(f"/api/artifacts/{aid}/revise",{"conversation_id":cid,"changes":{"nodes":[{"id":"N4","lane":"Compras"}],"theme":{"primary":"#663399"}}})
    check("revisión completa",wait(revision["job_id"])["status"]=="completed")
    after=call(f"/api/artifacts/{aid}")
    check("nueva versión con cambio puntual",after["version"]==2 and after["spec"]["process"]["nodes"][3]["lane"]=="Compras")
    check("se conserva la versión original",call(f"/api/artifacts/{aid}?version=1")["spec"]==before["spec"])
    try:
        call(f"/api/artifacts/{aid}",authenticated=False)
        raise AssertionError("Acceso anónimo permitido")
    except error.HTTPError as exc:check("descarga y lectura exigen autenticación",exc.code==403)
    return {"passed":len(checks),"checks":checks,"model_calls":"none","mode":"demo"}


if __name__=="__main__":
    print(json.dumps(run(sys.argv[1] if len(sys.argv)>1 else "http://127.0.0.1:8080"),ensure_ascii=False,indent=2))
