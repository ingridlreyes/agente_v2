"""Valida exportación aislada, integración Graph y la separación del proyecto conversacional."""
import ast
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from pptx import Presentation
from recording_studio.application.assessment import grade_assessment,generate_assessment
from recording_studio.application.demo import FIXTURES,build_demo
from recording_studio.application.service import RecordingService
from recording_studio.domain.models import Assessment,Principal,Theme
from recording_studio.documents.powerpoint import powerpoint
from recording_studio.infrastructure.config import Settings
from recording_studio.infrastructure.providers import ResponsesModel
from recording_studio.media.models import BatchAnalysis,Frame,VideoPlan


class FakeModel:
    """Simula formatos y evidencia para probar orquestación, sin comprender videos reales."""
    def __init__(self):
        """Registra llamadas para comprobar que se reutilizan los lotes completados."""
        self.batches=0;self.invalid_assessment=False

    def generate(self,schema,instructions,context,**kwargs):
        """Devuelve un grupo visual conocido o las diez preguntas de fixture con IDs válidos."""
        if schema is BatchAnalysis:
            self.batches+=1
            group=VideoPlan.model_validate_json((FIXTURES/"plan.json").read_text()).groups[0]
            group.start=context["batch"]["start"];group.end=context["batch"]["end"];group.evidence_ids=["F1"]
            return BatchAnalysis(summary="Caso ficticio del lote",groups=[group]),{"simulated":True}
        if schema is Assessment:
            quiz=Assessment.model_validate_json((FIXTURES/"evaluacion.json").read_text())
            for question in quiz.questions:question.evidence_ids=["invented" if self.invalid_assessment else context["allowed_evidence_ids"][0]]
            return quiz,{"simulated":True}
        raise AssertionError(schema)


class FakeMedia:
    """Entrega la captura ficticia como si ya se hubiera extraído de un video autorizado."""
    def duration(self,path):
        """Fija una duración corta para comprobar el flujo completo sin codificar un video."""
        return 60

    def prepare(self,path,batch,directory,need_audio):
        """Devuelve un frame local cuya identidad coincide con el contrato simulado."""
        return [Frame(id="F1",timestamp=5,path=str(FIXTURES/"frames/F1.png"))],None


class DemoExportTests(unittest.TestCase):
    """Comprueba que el layout aprobado conserva todas las marcas y sus pasos continuos."""
    def test_native_marks_continuous_numbers_and_original_frames(self):
        """Inspecciona doce flechas/recuadros editables, pasos 1–12 y tres capturas originales."""
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);files=build_demo(root)
            deck=Presentation(root/"entregable.pptx");self.assertEqual(len(deck.slides),4)
            for index,slide in enumerate(list(deck.slides)[1:]):
                names=[shape.name for shape in slide.shapes]
                for kind in ("Recuadro","Flecha","Etiqueta"):self.assertEqual(sum(name.endswith("/ "+kind) for name in names),4)
                texts=[shape.text for shape in slide.shapes if shape.has_text_frame]
                for number in range(index*4+1,index*4+5):self.assertIn(f"Paso {number}",texts);self.assertIn(str(number),texts)
                for shape in slide.shapes:
                    if shape.name.endswith("/ Flecha"):self.assertTrue(shape._element.xpath(".//a:tailEnd[@type='triangle']"))
            for index in range(1,4):self.assertEqual((root/f"frames/F{index}.png").read_bytes(),(FIXTURES/f"frames/F{index}.png").read_bytes())
            with ZipFile(root/"paquete.zip") as archive:self.assertTrue({"entregable.pptx","evaluacion.md","respuestas_evaluacion.md","plan.json"}<=set(archive.namelist()))
            self.assertIn("entregable.docx",files)

    def test_missing_frame_blocks_annotated_export(self):
        """Una presentación anotada no se publica sin sus capturas de referencia."""
        plan=VideoPlan.model_validate_json((FIXTURES/"plan.json").read_text())
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError,"Falta la captura"):powerpoint(plan,Theme(),Path(temporary)/"broken.pptx")

    def test_ten_questions_and_grading(self):
        """Verifica el cuestionario completo y la calificación sin nuevas llamadas al modelo."""
        quiz=Assessment.model_validate_json((FIXTURES/"evaluacion.json").read_text())
        self.assertEqual(len(quiz.questions),10)
        self.assertEqual(grade_assessment(quiz,{question.id:question.correct_index for question in quiz.questions})["percentage"],100)
        self.assertEqual(grade_assessment(quiz,{})["percentage"],0)


class ServiceTests(unittest.TestCase):
    """Prueba casos de uso del SDK con rutas y fuentes elegidas por el backend."""
    def setUp(self):
        """Crea video, configuración y proveedor simulados en un directorio temporal propio."""
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.video=self.root/"recording.mp4";self.video.write_bytes(b"test-fixture-not-real-video")
        self.principal=Principal(tenant_id="t",user_id="u");self.model=FakeModel()
        self.service=RecordingService(Settings(data_dir=self.root/"runtime"),model=self.model,media=FakeMedia())
        self.subtitles="WEBVTT\n\n00:00:00.000 --> 00:01:00.000\nRegistrar propósito, categorías, responsables y evidencia.\n"

    def tearDown(self):
        """Retira únicamente los archivos temporales creados por la prueba."""
        self.temp.cleanup()

    def generate(self,name="result",principal=None):
        """Ejecuta el mismo caso autorizado para comprobar publicación y caché."""
        return self.service.generate_file(principal or self.principal,self.video,"Guía del proceso",self.root/name,subtitles=self.subtitles)

    def test_full_run_publishes_guide_quiz_report_and_marks(self):
        """Recorre análisis, regiones, evaluación y exportación con el SDK aislado."""
        result=self.generate();root=Path(result["directory"])
        self.assertEqual(result["report"]["annotated_steps"],4)
        self.assertEqual(len(Presentation(root/"entregable.pptx").slides),2)
        self.assertEqual(len(json.loads((root/"evaluacion.json").read_text())["questions"]),10)
        self.assertTrue((root/"video_analysis.json").is_file())

    def test_repeated_run_uses_scoped_checkpoints(self):
        """Reutiliza el lote al exportar otra versión del mismo video y objetivo."""
        self.generate("first");result=self.generate("second")
        self.assertEqual(self.model.batches,1);self.assertEqual(result["report"]["cache_hits"],1)

    def test_other_user_does_not_reuse_checkpoints(self):
        """Aísla análisis aunque dos usuarios envíen el mismo video y objetivo."""
        self.generate("first");result=self.generate("second",Principal(tenant_id="t",user_id="another"))
        self.assertEqual(self.model.batches,2);self.assertEqual(result["report"]["cache_hits"],0)

    def test_failed_quiz_never_publishes_partial_result(self):
        """Conserva checkpoints pero no crea un entregable si las preguntas inventan evidencia."""
        self.model.invalid_assessment=True
        with self.assertRaises(ValueError):self.generate()
        self.assertFalse((self.root/"result").exists())
        self.assertTrue(list((self.root/"runtime/runs").rglob("checkpoints/*.json")))

    def test_existing_destination_is_not_overwritten(self):
        """Protege entregables previos antes de gastar otra llamada al modelo."""
        target=self.root/"result";target.mkdir();(target/"keep.txt").write_text("keep")
        with self.assertRaises(FileExistsError):self.generate()
        self.assertEqual((target/"keep.txt").read_text(),"keep");self.assertEqual(self.model.batches,0)

    def test_graph_link_uses_delegate_and_cleans_download(self):
        """Resuelve la URL con la identidad recibida y elimina la copia temporal descargada."""
        calls=[]
        class Graph:
            """Simula únicamente los dos métodos del contrato de archivos Graph."""
            def resolve_reference(self,principal,reference):
                """Registra la identidad que el backend autorizó y devuelve IDs ficticios."""
                calls.append((principal.user_id,reference));return "drive","item",{"name":"recording.mp4"}
            def download(self,principal,drive,item,path):
                """Guarda bytes ficticios que FakeMedia acepta durante la prueba."""
                Path(path).write_bytes(b"fixture")
        self.service.graph=Graph()
        self.service.generate_graph(self.principal,{"sharing_url":"https://tenant.sharepoint.com/video"},"Guía del proceso",self.root/"graph",subtitles=self.subtitles)
        self.assertEqual(calls[0][0],"u")
        self.assertEqual(list((self.root/"runtime/downloads").rglob("*.mp4")),[])


class SeparationTests(unittest.TestCase):
    """Evita reintroducir dependencias o configuración del proyecto conversacional."""
    def test_settings_do_not_require_search_or_router(self):
        """La inferencia de video funciona sin índice, bibliotecas ni deployment de intención."""
        with patch.dict(os.environ,{"RS_MODE":"azure","RS_MODEL_BASE_URL":"https://example.invalid/openai/v1/","RS_WRITER_MODEL":"video-deployment","RS_MODEL_API_KEY":"fake-for-test"},clear=True):
            settings=Settings.from_env()
        self.assertFalse(hasattr(settings,"search_endpoint"));self.assertFalse(hasattr(settings,"router_model"))

    def test_no_import_of_conversational_project(self):
        """Comprueba estáticamente que todos los imports propios pertenecen al paquete de grabaciones."""
        root=Path(__file__).resolve().parents[1]/"recording_studio"
        for path in root.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                names=[node.module] if isinstance(node,ast.ImportFrom) else [alias.name for alias in node.names] if isinstance(node,ast.Import) else []
                self.assertFalse(any(name and name.startswith("governance_studio") for name in names),path)

    def test_model_uses_configured_video_deployment_and_image_detail(self):
        """Valida el contrato Responses sin llamar a servicios reales ni clasificar intención."""
        quiz=Assessment.model_validate_json((FIXTURES/"evaluacion.json").read_text());sent=[]
        def post(url,body,*args):
            """Captura el payload y devuelve el contrato completo de una respuesta simulada."""
            sent.append(body)
            return {"status":"completed","output":[{"content":[{"type":"output_text","text":quiz.model_dump_json()}]}]}
        settings=Settings(mode="azure",model_base_url="https://example.invalid/openai/v1/",writer_model="video-deployment",model_api_key="fake")
        with patch("recording_studio.infrastructure.providers.post_json",side_effect=post):ResponsesModel(settings).generate(Assessment,"Prueba",{},images=["data:image/png;base64,AA=="])
        self.assertEqual(sent[0]["model"],"video-deployment");self.assertFalse(sent[0]["store"])
        self.assertEqual(sent[0]["input"][0]["content"][1]["detail"],"high")
