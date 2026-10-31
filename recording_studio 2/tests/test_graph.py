"""Valida identidad delegada, paginación y descargas Graph sin credenciales reales."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError
from recording_studio.domain.models import Principal
from recording_studio.integrations.microsoft_graph import GraphClient,GraphIdentityToken


class Response(io.BytesIO):
    """Respuesta HTTP mínima y local para probar el adaptador de descarga."""


class GraphTests(unittest.TestCase):
    """Pruebas de Graph."""
    def setUp(self):
        """Define una identidad ficticia que solo corresponde al usuario del caso."""
        self.p=Principal(tenant_id="t",user_id="u")
        self.client=GraphClient(lambda p:GraphIdentityToken("not-a-real-token","t","u"))

    def test_wrong_identity_never_contacts_graph(self):
        """Bloquea un token perteneciente a otro tenant antes de abrir una conexión."""
        client=GraphClient(lambda p:GraphIdentityToken("x","other","u"))
        with self.assertRaises(PermissionError):client.item(self.p,"d","i")

    def test_redirect_never_forwards_bearer(self):
        """Comprueba que una descarga firmada no reciba Authorization de Microsoft Graph."""
        requests=[]
        class Opener:
            """Simula metadatos Graph, redirección y contenido firmado."""
            def open(self,req,timeout):
                """Registra las cabeceras y devuelve una respuesta correspondiente a la ruta."""
                requests.append(req)
                if req.full_url.endswith("/content"):
                    raise HTTPError(req.full_url,302,"redirect",{"Location":"https://tenant.sharepoint.com/signed"},None)
                if req.full_url.endswith("/signed"):return Response(b"content")
                return Response(json.dumps({"name":"file.txt","file":{},"size":7,"eTag":"v1"}).encode())
        client=GraphClient(self.client.token_provider,opener=Opener())
        with tempfile.TemporaryDirectory() as temp:
            result=client.download(self.p,"drive","item",Path(temp)/"file")
            self.assertEqual(result["bytes"],7)
        signed=[r for r in requests if "sharepoint.com" in r.full_url][0]
        self.assertIsNone(signed.get_header("Authorization"))
        self.assertTrue(requests[0].get_header("Authorization").startswith("Bearer "))

    def test_untrusted_signed_host_is_rejected(self):
        """Impide que Graph entregue una descarga a un servidor arbitrario o local."""
        for url in ("http://tenant.sharepoint.com/x","https://evil.invalid/x","https://127.0.0.1/x","https://tenant.sharepoint.com.evil.invalid/x"):
            with self.assertRaises(ValueError):self.client._signed_download(url)

    def test_pagination_does_not_escape_graph(self):
        """Rechaza enlaces nextLink fuera del host oficial de Graph."""
        class Opener:
            """Devuelve una página con un enlace deliberadamente hostil."""
            def open(self,req,timeout):
                """Simula un resultado de paginación que el adaptador debe rechazar."""
                return Response(json.dumps({"value":[],"@odata.nextLink":"https://evil.invalid"}).encode())
        client=GraphClient(self.client.token_provider,opener=Opener())
        with self.assertRaises(ValueError):client.children(self.p,"d","i")

    def test_change_during_download_is_not_published(self):
        """Elimina la descarga parcial si el eTag cambia antes de terminar."""
        client=self.client;count=0
        def item(*args):
            """Simula dos versiones distintas del archivo durante la misma descarga."""
            nonlocal count
            count+=1
            return {"name":"x","file":{},"size":3,"eTag":str(count)}
        client.item=item;client._open=lambda *args:Response(b"123")
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"file"
            with self.assertRaises(ValueError):client.download(self.p,"d","i",path)
            self.assertFalse(path.exists());self.assertEqual(list(Path(temp).iterdir()),[])


class LinkTests(unittest.TestCase):
    """Pruebas de Link."""
    setUp=GraphTests.setUp
    """Prueba resolución de enlaces sin abrir URLs enviadas por el usuario."""
    def test_sharepoint_encoded_without_redemption(self):
        """Codifica el vínculo según Graph y conserva la identidad delegada."""
        import base64
        urls=[]
        class Opener:
            """Captura la única llamada Graph esperada para el enlace."""
            def open(self,req,timeout):
                """Devuelve IDs ficticios y detecta intentos de canjear permisos."""
                urls.append(req.full_url)
                assert req.get_header("Prefer") is None
                return Response(json.dumps({"id":"item","parentReference":{"driveId":"drive"}}).encode())
        client=GraphClient(self.client.token_provider,opener=Opener())
        url="https://tenant.sharepoint.com/:v:/s/training/example?e=123"
        drive,item,_=client.resolve_reference(self.p,{"sharing_url":url})
        self.assertEqual((drive,item),("drive","item"))
        self.assertIn("u!"+base64.urlsafe_b64encode(url.encode()).decode().rstrip("="),urls[0])
        self.assertTrue(urls[0].startswith("https://graph.microsoft.com/v1.0/shares/"))

    def test_teams_recording_ids_and_nested_sharepoint(self):
        """Reconoce archivos en Teams y enlaces anidados de SharePoint sin seguir redirecciones."""
        client=self.client;calls=[]
        def item(principal,drive,item):
            """Registra el par de identificadores que Teams proporcionó."""
            calls.append((drive,item));return {"id":item,"parentReference":{"driveId":drive}}
        client.item=item
        self.assertEqual(client.resolve_reference(self.p,{"sharing_url":"https://teams.microsoft.com/l/meetingrecap?driveId=d&driveItemId=i"})[:2],("d","i"))
        self.assertEqual(calls,[("d","i")])
        client._json=lambda p,path:{"id":"nested","parentReference":{"driveId":"share"}}
        self.assertEqual(client.resolve_reference(self.p,{"sharing_url":"https://teams.microsoft.com/l/file?fileUrl=https%3A%2F%2Ftenant.sharepoint.com%2Ffile.mp4"})[:2],("share","nested"))

    def test_unsupported_meeting_and_host_rejected(self):
        """Explica enlaces genéricos de reunión y rechaza URLs ajenas antes de usar la red."""
        for url in ("https://teams.microsoft.com/l/meetup-join/abc","https://evil.invalid/video","https://tenant.sharepoint.com.evil.invalid/file","http://tenant.sharepoint.com/file"):
            with self.assertRaises(ValueError):self.client.resolve_link(self.p,url)
