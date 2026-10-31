"""Prueba regiones reales, referencias y conservación de marcas entre lotes."""
from pathlib import Path
import tempfile
import unittest
from pydantic import ValidationError
from recording_studio.domain.models import FrameRegion
from recording_studio.infrastructure.config import Settings
from recording_studio.media.annotations import restore_visual_annotations,validate_frame_reference
from recording_studio.media.models import BatchAnalysis,StepGroup,VideoPlan,Frame


def group_fixture():
    """Devuelve dos pasos con una marca por paso sobre una captura identificada."""
    return StepGroup(id="G1",title="Revisión",objective="Revisar el expediente",steps=["Validar acceso","Registrar aprobación"],
        start=0,end=30,evidence_ids=["F1"],origin_ids=["G1"],frame_id="F1",annotations=[
            FrameRegion(step_index=0,x=.2,y=.2,width=.4,height=.1),FrameRegion(step_index=1,x=.2,y=.6,width=.4,height=.1)])

class RegionTests(unittest.TestCase):
    """Evita regiones inválidas o referencias visuales sin una captura disponible."""

    def test_coordinates_stay_in_full_frame(self):
        """Rechaza geometrías fuera del frame y valores no finitos."""
        for changes in ({'x': -0.1}, {'x': 0.9}, {'height': 0}, {'y': float('nan')}):
            with self.assertRaises(ValidationError):
                FrameRegion.model_validate({**group_fixture().annotations[0].model_dump(), **changes})

    def test_step_reference_must_exist_and_be_unique(self):
        """Una marca no puede apuntar a un paso inexistente ni duplicar otro índice."""
        data = group_fixture().model_dump()
        data['annotations'][1]['step_index'] = 3
        with self.assertRaises(ValidationError):
            StepGroup.model_validate(data)
        data['annotations'][1]['step_index'] = 0
        with self.assertRaises(ValidationError):
            StepGroup.model_validate(data)

    def test_transcript_cannot_supply_visual_coordinates(self):
        """Rechaza localizar elementos cuando el supuesto frame solo es texto o no existe."""
        with self.assertRaises(ValueError):
            validate_frame_reference(group_fixture(), [Frame(id='F1', timestamp=0)])
        with self.assertRaises(ValueError):
            validate_frame_reference(group_fixture(), [Frame(id='other', timestamp=0, path='local.png')])
        validate_frame_reference(group_fixture(), [Frame(id='F1', timestamp=0, path='local.png')])

    def test_consolidation_restores_origin_coordinates_after_reordering(self):
        """Reordena índices por texto y descarta coordenadas inventadas por el merge global."""
        original = group_fixture()
        merged = original.model_copy(deep=True)
        merged.steps = list(reversed(merged.steps))
        merged.annotations = [FrameRegion(step_index=0, x=0.01, y=0.01, width=0.05, height=0.05)]
        plan = VideoPlan(title='Guía', summary='Revisión', groups=[merged])
        restore_visual_annotations(plan, [BatchAnalysis(summary='Lote', groups=[original])])
        self.assertEqual(plan.groups[0].annotations[0].y, 0.6)
        self.assertEqual(plan.groups[0].annotations[1].y, 0.2)
        self.assertEqual([a.step_index for a in plan.groups[0].annotations], [0, 1])

    def test_changed_instruction_does_not_inherit_wrong_region(self):
        """Un paso nuevo no recibe el recuadro antiguo por tener la misma posición."""
        original = group_fixture()
        merged = original.model_copy(deep=True)
        merged.steps[0] = 'Revocar acceso'
        plan = VideoPlan(title='Guía', summary='Revisión', groups=[merged])
        restore_visual_annotations(plan, [BatchAnalysis(summary='Lote', groups=[original])])
        self.assertEqual([a.step_index for a in plan.groups[0].annotations], [1])

class AnnotatedPipelineTests(unittest.TestCase):
    """Prueba las marcas desde el contrato multimodal hasta el plan y los archivos exportados."""

    def test_pipeline_keeps_regions_through_duplicate_consolidation(self):
        """Dos lotes repetidos conservan una captura, sus dos marcas y ambos orígenes."""
        from PIL import Image
        from recording_studio.media.pipeline import VideoPipeline

        class Model:
            """Proveedor simulado que devuelve regiones y grupos sobre las capturas recibidas."""

            def generate(self, schema, instructions, context, **kwargs):
                """Analiza cada lote ficticio y conserva el grupo compacto al consolidar."""
                if schema is BatchAnalysis:
                    group = group_fixture()
                    group.frame_id = context['frames'][0]['id']
                    group.evidence_ids = [group.frame_id]
                    group.start = context['batch']['start']
                    group.end = context['batch']['end']
                    return (BatchAnalysis(summary='Caso visual', groups=[group]), {'simulated': True})
                return (VideoPlan(title='Guía', summary='Caso visual', groups=[StepGroup.model_validate(g) for b in context['batches'] for g in b['groups']]), {'simulated': True})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            Image.new('RGB', (800, 500), 'white').save(root / 'frame.png')
            frames = [Frame(id='F1', timestamp=0, path=str(root / 'frame.png')), Frame(id='F2', timestamp=1000, path=str(root / 'frame.png'))]
            plan, report, _, _ = VideoPipeline(Model(), Settings()).analyze(1800, [], frames, root / 'run', 'tenant/user/chat', 'Guía visual')
            self.assertEqual(len(plan.groups), 1)
            self.assertEqual(len(plan.groups[0].origin_ids), 2)
            self.assertEqual(len(plan.groups[0].annotations), 2)
            self.assertEqual(report['annotated_steps'], 2)
            self.assertEqual(report['steps'], 2)