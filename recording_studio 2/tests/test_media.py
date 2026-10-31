"""Prueba lotes, cobertura, caché, medios y repeticiones del proyecto de grabaciones."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from threading import Lock
import time
import unittest
from recording_studio.domain.models import Assessment
from recording_studio.infrastructure.config import Settings
from recording_studio.media.batching import plan_batches,parse_subtitles
from recording_studio.media.ffmpeg import MediaTools
from recording_studio.media.models import Segment,Frame,StepGroup,BatchAnalysis,VideoPlan
from recording_studio.media.pipeline import VideoPipeline,validate_plan,deduplicate_frames,deduplicate_groups


class VideoModel:
    """Proveedor simulado que registra concurrencia sin atribuirse comprensión de imágenes."""

    def __init__(self):
        """Inicializa contadores compartidos por los workers del test."""
        self.lock = Lock()
        self.calls = 0
        self.active = 0
        self.peak = 0

    def generate(self, schema, instructions, context, **kwargs):
        """Devuelve grupos deterministas para probar únicamente la orquestación."""
        if schema is BatchAnalysis:
            with self.lock:
                self.calls += 1
                self.active += 1
                self.peak = max(self.active, self.peak)
            try:
                time.sleep(0.015)
                batch = context['batch']
                ref = context['frames'][0]['id'] if context['frames'] else context['transcript'][0]['id']
                group = StepGroup(id='G', title='Revisión del expediente', objective='Completar la revisión antes de aprobar.', steps=['Registrar la finalidad del uso.', 'Clasificar los datos previstos.', 'Revisar la evidencia requerida.', 'Enviar el expediente a aprobación.'], dynamic_fields=['Identificador', 'Fecha'], start=batch['start'], end=batch['end'], evidence_ids=[ref])
                return (BatchAnalysis(summary='Caso de prueba de gobierno de datos.', groups=[group]), {'simulated': True})
            finally:
                with self.lock:
                    self.active -= 1
        if schema is VideoPlan:
            groups = [StepGroup.model_validate(g) for b in context['batches'] for g in b['groups']]
            return (VideoPlan(title='Guía del expediente', summary='Caso ficticio para probar la agrupación.', groups=groups), {'simulated': True})
        raise AssertionError(schema)

class BatchTests(unittest.TestCase):
    """Pruebas de Batch."""

    def test_two_hours_use_eight_large_batches(self):
        """Verifica cobertura continua de dos horas con ocho ventanas de quince minutos."""
        batches = plan_batches(7200)
        self.assertEqual(len(batches), 8)
        self.assertEqual(batches[0].start, 0)
        self.assertEqual(batches[-1].end, 7200)
        self.assertTrue(all((a.end == b.start for a, b in zip(batches, batches[1:]))))
        self.assertEqual(batches[1].context_start, 885)

    def test_short_tail_is_absorbed(self):
        """Evita crear un último fragmento de pocos segundos en una grabación larga."""
        batches = plan_batches(1810)
        self.assertEqual(len(batches), 2)
        self.assertEqual(batches[-1].end, 1810)
        self.assertGreaterEqual(min((b.end - b.start for b in batches)), 900)

    def test_rejects_micro_batches(self):
        """Rechaza configurar ventanas diminutas que multiplicarían llamadas y perderían contexto."""
        with self.assertRaises(ValueError):
            plan_batches(7200, 30)

    def test_subtitle_times_and_order(self):
        """Lee VTT y SRT conservando sus tiempos y eliminando etiquetas de formato."""
        text = 'WEBVTT\n\n00:00:03.000 --> 00:00:06.000\n<b>Validar datos</b>\n\n2\n00:00:07,000 --> 00:00:09,000\nAprobar\n'
        result = parse_subtitles(text)
        self.assertEqual(result[0].start, 3)
        self.assertEqual(result[0].text, 'Validar datos')
        self.assertEqual(result[1].end, 9)

class PipelineTests(unittest.TestCase):
    """Pruebas de Pipeline."""

    def setUp(self):
        """Crea un espacio temporal de trabajo para aislar checkpoints del caso de prueba."""
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = Settings(video_workers=3)
        self.model = VideoModel()
        self.pipeline = VideoPipeline(self.model, self.settings)
        self.segments = [Segment(id=f'T{i}', start=i * 900, end=(i + 1) * 900, text='Revisión de finalidad, clasificación, evidencia y aprobación.') for i in range(8)]

    def tearDown(self):
        """Retira los datos sintéticos del test después de cerrar sus workers."""
        self.temp.cleanup()

    def analyze(self, scope='tenant/user/workspace', brief='Guía de gobierno de datos'):
        """Ejecuta el caso sintético de dos horas con la misma configuración reproducible."""
        return self.pipeline.analyze(7200, self.segments, [], self.root, scope, brief)

    def test_parallelism_order_and_cache(self):
        """Demuestra concurrencia acotada, orden temporal y cero reanálisis de lotes completos."""
        plan, report, _, _ = self.analyze()
        self.assertEqual(report['batches'], 8)
        self.assertEqual(self.model.calls, 8)
        self.assertEqual(report['exact_duplicate_groups_merged'], 7)
        self.assertEqual(report['slides_with_cover'], 2)
        self.assertGreater(self.model.peak, 1)
        self.assertLessEqual(self.model.peak, 3)
        self.assertEqual([g.start for g in plan.groups], sorted((g.start for g in plan.groups)))
        _, again, _, _ = self.analyze()
        self.assertEqual(again['cache_hits'], 8)
        self.assertEqual(self.model.calls, 8)

    def test_cache_is_scoped_to_user_and_request(self):
        """Impide reutilizar un análisis de otra identidad o de un objetivo distinto."""
        self.analyze()
        self.analyze(scope='tenant/another/workspace')
        self.assertEqual(self.model.calls, 16)
        self.analyze(brief='Otro objetivo de análisis')
        self.assertEqual(self.model.calls, 24)

    def test_failed_batch_preserves_successful_checkpoints(self):
        """Permite reanudar después de un fallo sin publicar un plan incompleto."""
        base = self.model.generate

        def fail(schema, instructions, context, **kwargs):
            """Simula un error material de proveedor en un único lote del conjunto."""
            if schema is BatchAnalysis and context['batch']['id'] == 'B0004':
                raise RuntimeError('simulated')
            return base(schema, instructions, context, **kwargs)
        self.model.generate = fail
        with self.assertRaises(RuntimeError):
            self.analyze()
        self.assertTrue(list((self.root / 'checkpoints').glob('*.json')))
        self.assertFalse((self.root / 'video_analysis.json').exists())
        self.model.generate = base
        _, report, _, _ = self.analyze()
        self.assertGreater(report['cache_hits'], 0)

    def test_no_silent_omission_and_four_steps_kept(self):
        """Bloquea la consolidación que pierda un origen o fragmente cuatro pasos del mismo frame."""
        plan, _, _, _ = self.analyze()
        originals = []
        for group in plan.groups:
            for origin in group.origin_ids:
                original = copy.deepcopy(group)
                original.id = origin
                original.origin_ids = [origin]
                originals.append(original)
        analyses = [BatchAnalysis(summary='x', groups=[original]) for original in originals]
        broken = plan.model_copy(deep=True)
        broken.groups.pop()
        with self.assertRaises(ValueError):
            validate_plan(broken, analyses, 7200, 29, {s.id for s in self.segments})
        broken = plan.model_copy(deep=True)
        broken.groups[0].steps = broken.groups[0].steps[:1]
        with self.assertRaises(ValueError):
            validate_plan(broken, analyses, 7200, 29, {s.id for s in self.segments})

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg no instalado')
class RealMediaTests(unittest.TestCase):
    """Pruebas de RealMedia."""

    def test_real_probe_frames_and_audio(self):
        """Prueba extracción real en un video sintético corto, sin enviar contenido a un modelo."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            video = root / 'fixture.mp4'
            subprocess.run([shutil.which('ffmpeg'), '-nostdin', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=c=gray:s=320x180:r=2:d=6', '-f', 'lavfi', '-i', 'anullsrc=r=16000:cl=mono', '-t', '6', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(video)], check=True, timeout=60)
            tools = MediaTools(frames_per_batch=4)
            duration = tools.duration(video)
            self.assertAlmostEqual(duration, 6, places=0)
            batch = plan_batches(duration)[0]
            frames, audio = tools.prepare(video, batch, root / 'parts', True)
            self.assertEqual(len(frames), 4)
            self.assertTrue(audio.is_file())
            self.assertTrue(all((Path(f.path).is_file() for f in frames)))

class DeduplicationTests(unittest.TestCase):
    """Comprueba que solo las repeticiones se consoliden y que sus orígenes sigan auditables."""

    def test_exact_frames_keep_alias_and_changed_pixel(self):
        """Conserva un cambio mínimo de valor y evita reenviar una captura idéntica."""
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            im = Image.new('RGB', (40, 20), 'white')
            im.save(root / 'a.png')
            im.save(root / 'b.png')
            im.putpixel((0, 0), (0, 0, 0))
            im.save(root / 'c.png')
            frames = [Frame(id=name, timestamp=i, path=str(root / (name + '.png'))) for i, name in enumerate('abc')]
            result = deduplicate_frames(frames)
            self.assertEqual([f.duplicate_of for f in result], [None, 'a', None])
            self.assertEqual([f.id for f in result], list('abc'))

    def test_repeated_activities_anywhere_keep_variants(self):
        """Une actividades iguales distantes y mantiene un cambio de instrucción como variante."""
        base = StepGroup(id='first', title='Revisar', objective='Validar evidencia', steps=['Comprobar los 4 campos'], start=0, end=10, evidence_ids=['F1'], origin_ids=['first'])
        repeat = base.model_copy(deep=True)
        repeat.id = 'later'
        repeat.origin_ids = ['later']
        repeat.start = 900
        repeat.end = 910
        repeat.evidence_ids = ['F2']
        variant = repeat.model_copy(deep=True)
        variant.id = 'variant'
        variant.origin_ids = ['variant']
        variant.steps = ['Comprobar los 5 campos']
        analyses = [BatchAnalysis(summary='Caso', groups=[g]) for g in (base, repeat, variant)]
        result = deduplicate_groups(analyses)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].origin_ids, ['first', 'later'])
        self.assertEqual(result[0].evidence_ids, ['F1', 'F2'])
        plan = VideoPlan(title='Guía', summary='Caso', groups=result)
        validate_plan(plan, analyses, 1000, 29, {'F1', 'F2'})
        self.assertEqual(base.origin_ids, ['first'])