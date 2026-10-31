"""Lectura de OneDrive, SharePoint y transcripciones de Teams mediante Graph v1.0.

Cada operación recibe un Principal ya autenticado. El resolvedor de tokens debe
entregar un token delegado de ese mismo usuario. Nunca se acepta un token Graph
ni una identidad enviada en el cuerpo de una petición HTTP del usuario.
"""
from dataclasses import dataclass
import base64
import json
from pathlib import Path
import time
from urllib import request,error,parse
import uuid


@dataclass(frozen=True)
class GraphIdentityToken:
    """Token Graph unido a una identidad que el host ya validó criptográficamente."""
    token: str
    tenant_id: str
    user_id: str


class NoRedirect(request.HTTPRedirectHandler):
    """Impide reenviar automáticamente Authorization a la URL firmada de descarga."""
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        """Devuelve el control al cliente para retirar credenciales antes de redirigir."""
        return None


class GraphClient:
    """Cliente delegado y de solo lectura; la aplicación host resuelve el token."""
    def __init__(self,token_provider,download_hosts=("sharepoint.com","sharepointonline.com","1drv.com"),opener=None):
        """Configura el resolvedor de identidad y los dominios de descarga permitidos."""
        self.token_provider=token_provider
        self.download_hosts=download_hosts
        self.opener=opener or request.build_opener(NoRedirect())

    def _headers(self,principal):
        """Rechaza tokens de otro tenant o usuario antes de contactar a Microsoft."""
        identity=self.token_provider(principal)
        if not isinstance(identity,GraphIdentityToken) or (identity.tenant_id,identity.user_id)!=(principal.tenant_id,principal.user_id):
            raise PermissionError("El token Graph no corresponde a la identidad autenticada")
        return {"Authorization":"Bearer "+identity.token,"Accept":"application/json"}

    def _open(self,url,headers):
        """Aplica timeout y backoff acotado a throttling y fallos transitorios."""
        for attempt in range(3):
            try:
                return self.opener.open(request.Request(url,headers=headers),timeout=120)
            except error.HTTPError as exc:
                if exc.code not in (429,502,503,504) or attempt==2:raise
                try:delay=min(15,float(exc.headers.get("Retry-After",2**attempt)))
                except ValueError:delay=2**attempt
                time.sleep(max(0,delay))

    def _json(self,principal,path):
        """Consulta solamente Graph v1.0; valida también los enlaces de paginación."""
        url=path if path.startswith("https://") else "https://graph.microsoft.com/v1.0/"+path.lstrip("/")
        parsed=parse.urlsplit(url)
        if parsed.netloc!="graph.microsoft.com" or not parsed.path.startswith("/v1.0/"):
            raise ValueError("URL Graph no permitida")
        with self._open(url,self._headers(principal)) as response:
            return json.loads(response.read(8_000_000))

    def item(self,principal,drive_id,item_id):
        """Obtiene metadatos bajo los permisos delegados efectivos del usuario."""
        return self._json(principal,f"drives/{parse.quote(drive_id,safe='')}/items/{parse.quote(item_id,safe='')}")

    def resolve_link(self,principal,url):
        """Resuelve enlaces SharePoint/OneDrive o Teams que identifican su archivo de grabación.

        Un enlace genérico de reunión o mensaje no identifica necesariamente un archivo.
        No sigue URLs del cliente ni canjea enlaces para otorgar acceso permanente.
        """
        for _ in range(3):
            parsed=parse.urlsplit(url)
            host=(parsed.hostname or "").lower()
            if parsed.scheme!="https" or parsed.username or parsed.password or parsed.port not in (None,443):
                raise ValueError("Usa un enlace HTTPS válido de Teams, SharePoint o OneDrive")
            if host in ("teams.microsoft.com","teams.cloud.microsoft"):
                query=parse.parse_qs(parsed.query)
                drive=query.get("driveId",[None])[0];item=query.get("driveItemId",[None])[0]
                if drive and item:return self.item(principal,drive,item)
                nested=next((query[k][0] for k in ("fileUrl","objectUrl","recordingUrl","webUrl") if query.get(k)),None)
                if nested:
                    url=nested;continue
                raise ValueError("Este enlace de Teams no identifica la grabación. Abre la grabación y usa Copiar vínculo o Abrir en SharePoint")
            allowed=host in ("1drv.ms","onedrive.live.com") or host.endswith(".sharepoint.com")
            if not allowed:raise ValueError("El enlace no pertenece a SharePoint, OneDrive o Teams")
            encoded="u!"+base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
            metadata=self._json(principal,"shares/"+encoded+"/driveItem")
            remote=metadata.get("remoteItem")
            return remote if remote and remote.get("parentReference",{}).get("driveId") else metadata
        raise ValueError("Demasiados enlaces anidados de Teams")

    def resolve_reference(self,principal,reference):
        """Normaliza la referencia validada a metadatos y un par de IDs autorizado por Graph."""
        from recording_studio.media.models import GraphReference
        ref=GraphReference.model_validate(reference)
        meta=self.resolve_link(principal,ref.sharing_url) if ref.sharing_url else self.item(principal,ref.drive_id,ref.item_id)
        drive=meta.get("parentReference",{}).get("driveId") or ref.drive_id
        item=meta.get("id") or ref.item_id
        if not drive or not item:raise ValueError("Graph no devolvió los identificadores del archivo; usa drive_id/item_id")
        return drive,item,meta

    def children(self,principal,drive_id,item_id):
        """Lista una carpeta con paginación completa y un límite explícito de seguridad."""
        path=f"drives/{parse.quote(drive_id,safe='')}/items/{parse.quote(item_id,safe='')}/children"
        result=[]
        for _ in range(100):
            payload=self._json(principal,path)
            result.extend(payload.get("value",[]))
            path=payload.get("@odata.nextLink")
            if not path:return result
        raise ValueError("La carpeta supera 100 páginas; consulta una subcarpeta")

    def _signed_download(self,url):
        """Abre una URL temporal permitida sin adjuntar el bearer de Graph."""
        parsed=parse.urlsplit(url)
        host=parsed.hostname or ""
        allowed=any(host==suffix or host.endswith("."+suffix) for suffix in self.download_hosts)
        if parsed.scheme!="https" or not allowed or parsed.username or parsed.password or parsed.port not in (None,443):
            raise ValueError("Destino de descarga de Microsoft no permitido")
        return self._open(url,{"Accept":"application/octet-stream"})

    def download(self,principal,drive_id,item_id,destination,max_bytes=4*1024**3):
        """Descarga por streaming, limita tamaño y verifica que el archivo no haya cambiado."""
        metadata=self.item(principal,drive_id,item_id)
        if "file" not in metadata or metadata.get("size",0)>max_bytes:
            raise ValueError("El elemento no es un archivo o supera el límite de tamaño")
        path=f"https://graph.microsoft.com/v1.0/drives/{parse.quote(drive_id,safe='')}/items/{parse.quote(item_id,safe='')}/content"
        try:
            response=self._open(path,self._headers(principal))
        except error.HTTPError as exc:
            if exc.code not in (301,302,303,307,308):raise
            response=self._signed_download(exc.headers.get("Location",""))
        destination=Path(destination)
        destination.parent.mkdir(parents=True,exist_ok=True)
        temporary=destination.with_name(destination.name+"."+uuid.uuid4().hex+".part")
        try:
            total=0
            with response,temporary.open("wb") as stream:
                while chunk:=response.read(1024*1024):
                    total+=len(chunk)
                    if total>max_bytes:raise ValueError("La descarga superó el límite permitido")
                    stream.write(chunk)
            current=self.item(principal,drive_id,item_id)
            if metadata.get("eTag")!=current.get("eTag"):
                raise ValueError("El archivo cambió durante la descarga; vuelve a solicitarlo")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return {"path":str(destination),"name":metadata["name"],"etag":metadata.get("eTag"),"bytes":total}

    def transcripts(self,principal,organizer_id,meeting_id):
        """Lista transcripciones accesibles de una reunión de Teams, sin generar una nueva."""
        path=f"users/{parse.quote(organizer_id,safe='')}/onlineMeetings/{parse.quote(meeting_id,safe='')}/transcripts"
        records=[]
        for _ in range(100):
            payload=self._json(principal,path);records.extend(payload.get("value",[]))
            path=payload.get("@odata.nextLink")
            if not path:return records
        raise ValueError("Demasiadas páginas de transcripciones")

    def transcript_text(self,principal,organizer_id,meeting_id,transcript_id):
        """Recupera el contenido VTT autorizado de una transcripción existente."""
        ids=[parse.quote(v,safe="") for v in (organizer_id,meeting_id,transcript_id)]
        path=f"https://graph.microsoft.com/v1.0/users/{ids[0]}/onlineMeetings/{ids[1]}/transcripts/{ids[2]}/content"
        with self._open(path,self._headers(principal)) as response:
            content=response.read(12_000_001)
        if len(content)>12_000_000:raise ValueError("La transcripción supera el límite de texto")
        return content.decode("utf-8-sig")


def make_obo_provider(tenant_id,client_id,client_secret,assertion_resolver):
    """Prepara OBO para un host que ya valida firma, issuer, audience y vigencia de Entra.

    assertion_resolver recibe Principal y devuelve GraphIdentityToken cuyo token
    contiene la aserción Entra validada, no un token tomado del cuerpo de la API.
    Esta función no sustituye la validación JWT del gateway corporativo.
    """
    def resolve(principal):
        """Intercambia la aserción del mismo usuario por un token delegado de Graph."""
        from azure.identity import OnBehalfOfCredential
        assertion=assertion_resolver(principal)
        if principal.tenant_id!=tenant_id or (assertion.tenant_id,assertion.user_id)!=(principal.tenant_id,principal.user_id):
            raise PermissionError("Aserción Entra de otra identidad")
        with OnBehalfOfCredential(tenant_id,client_id,client_secret,assertion.token) as credential:
            token=credential.get_token("https://graph.microsoft.com/.default").token
        return GraphIdentityToken(token,principal.tenant_id,principal.user_id)
    return resolve
