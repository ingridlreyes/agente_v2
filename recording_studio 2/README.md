# Recording Studio · Grabaciones a presentaciones

Asset independiente en Python para convertir grabaciones de procesos y capacitaciones en una presentación compacta, frames anotados y una evaluación de diez preguntas. Se integra mediante SDK o CLI en el backend que ya tienes.

El diseño es el que aprobaste: captura de pantalla a la izquierda, flechas y recuadros editables, instrucciones a la derecha y pasos numerados del 1 al n. Cuatro pasos relacionados permanecen en una sola diapositiva. El ejemplo usa interfaces ficticias del proceso de proveedores; el analizador acepta grabaciones de otros temas.

## Probar el ejemplo

Requiere Python 3.11 o posterior. Para analizar video real instala también FFmpeg y FFprobe.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m recording_studio demo --output examples/recording_demo
```

En Windows: `.venv\Scripts\activate`. El ejemplo listo para revisar está en `examples/aprobado`: cuatro láminas, tres capturas ficticias, doce pasos y doce marcas. Las preguntas del ejemplo están marcadas como demo; no se llamó a un modelo para producirlas.

## Flujo

```text
Video local autorizado o enlace Teams/SharePoint
  → descarga Graph cuando corresponde
  → lotes extensos y paralelos de capturas + transcripción
  → actividades agrupadas y repetición consolidada
  → regiones visibles verificadas por contrato
  → PPTX con marcas nativas y pasos continuos
  → diez preguntas sobre el material final + clave separada
```

La entrada es una grabación y su objetivo. Este paquete no utiliza AI Search, índices documentales, bibliotecas privadas/públicas, detección de intención ni memoria de un chat. Las variables de entorno tienen prefijo **RS_** y el paquete se llama **recording_studio**, para mantenerlo separado del otro proyecto.

## Carpetas

```text
recording_studio/
  application/      # Servicio integrable, evaluación y demostración
    fixtures/       # Capturas y contenido ficticios del ejemplo aprobado
  media/            # Lotes, FFmpeg, transcripción, caché y consolidación
  integrations/     # Microsoft Graph: enlaces, descargas, transcripciones y OBO
  documents/        # PowerPoint, superposiciones editables y guía Word opcional
  domain/           # Contratos de identidad, marca, región y evaluación
  infrastructure/   # Configuración RS_ y adaptador de inferencia
examples/aprobado/   # Entregables para revisar
scripts/            # Auditoría de documentación del código
tests/              # Pruebas de medios, cobertura, Graph y entrega
docs/               # Integración, optimización y validación
```

Todos los módulos, clases y funciones Python tienen docstrings de propósito. Puedes verificarlo con `python scripts/check_documentation.py`.

## Configurar inferencia para grabaciones reales

Usa las variables documentadas en `.env.example`; el programa no carga ese archivo automáticamente. El deployment debe admitir imágenes y Structured Outputs mediante Responses en tu endpoint. Es configurable, sin imponer un nombre de modelo.

```bash
export RS_MODE=azure
export RS_MODEL_BASE_URL='https://TU-RECURSO.openai.azure.com/openai/v1/'
export RS_WRITER_MODEL='TU-DEPLOYMENT-MULTIMODAL'
export RS_MODEL_API_KEY='SECRETO_DEL_BACKEND'
python -m recording_studio check
python -m recording_studio analyze --video '/ruta/autorizada/video.mp4' --subtitles '/ruta/video.vtt' --brief 'Explica el proceso y sus excepciones' --output '/ruta/nueva/guia'
```

Puedes usar `RS_ENTRA=1` y el extra `python -m pip install -e '.[azure]'` en lugar de una clave. Si no hay VTT/SRT, configura `RS_TRANSCRIBER_MODEL` con un deployment compatible con el endpoint de transcripción de audio del mismo recurso.

`check` solo valida configuración local. No demuestra que el deployment o los permisos del recurso sean compatibles. El destino real debe ser una carpeta nueva; no se sobrescriben entregables anteriores.

## Usar tus enlaces de Teams y SharePoint

El cliente Graph está listo para inyectarse con el token delegado de la sesión corporativa. No contiene una conexión activa a tu tenant. `RecordingService.generate_graph` acepta el vínculo de la grabación o el par `drive_id/item_id`.

```python
from recording_studio.application.service import RecordingService
from recording_studio.domain.models import Principal
from recording_studio.infrastructure.config import Settings
from recording_studio.integrations.microsoft_graph import GraphClient

# graph_token_for es tu resolvedor de tokens de la sesión corporativa validada.
service = RecordingService(Settings.from_env(), graph=GraphClient(graph_token_for))
principal = Principal(tenant_id=tenant_validado, user_id=usuario_validado)
result = service.generate_graph(
    principal,
    {"sharing_url": enlace_de_la_grabacion},
    brief="Preparar la capacitación agrupando pasos repetidos y conservando excepciones",
    output_directory=carpeta_nueva_autorizada,
    subtitles=texto_vtt_opcional,
    workspace_id=espacio_de_trabajo_validado,
    progress=actualizar_estado_del_trabajo,
)
```

Los nombres de sesión, carpetas y callbacks del ejemplo representan tu infraestructura existente. Tu host valida identidad, autoriza archivos y conserva la cola/API de trabajos. Este asset no añade un servidor web ni un sistema de autenticación alternativo.

[Integración Graph y contrato del SDK](docs/INTEGRACION_GRAPH.md) · [Lotes, repetición y controles de calidad](docs/OPTIMIZACION.md) · [Validación](docs/VALIDACION.md)

## Qué se entrega por grabación

- `entregable.pptx`: frames, recuadros, flechas y números como objetos editables.
- `evaluacion.md`: diez preguntas para participantes.
- `respuestas_evaluacion.md`: clave y explicaciones para el instructor.
- `evaluacion.json`: contrato completo con respuestas y referencias.
- `plan.json`, `theme.json` y `video_analysis.json`: estructura y diagnóstico del procesamiento.
- `transcript_used.json` y `frames/`: evidencia utilizada.
- `entregable.docx`: guía complementaria con la misma numeración; opcional con `include_word=False` en el SDK.
- `paquete.zip`: conjunto completo, **incluye las respuestas**. Distribuye a participantes únicamente los archivos sin clave.

## Límites actuales

El muestreo uniforme puede perder una pantalla fugaz; una región dentro de los límites no prueba que el modelo haya localizado el control correcto. La inferencia, transcripción, permisos y tiempos reales siguen pendientes de medición con tus videos y deployments. Los ejemplos y pruebas simuladas no acreditan esa precisión.

La guía Word contiene instrucciones numeradas; las capturas anotadas están en el PowerPoint. Las marcas permanecen separadas de la imagen original. Cambios manuales en PowerPoint no vuelven automáticamente al plan JSON. Para regenerar, vuelve a procesar el mismo video y objetivo: los lotes completos se reutilizan dentro de la misma identidad y espacio de trabajo.
