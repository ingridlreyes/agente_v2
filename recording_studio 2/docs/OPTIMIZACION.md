# Procesamiento y optimización de grabaciones

## Configuración inicial

| Variable | Inicial | Función |
|---|---:|---|
| `RS_VIDEO_BATCH_SECONDS` | 900 | Lotes de 15 minutos; admite 300–1800 segundos |
| `RS_VIDEO_OVERLAP_SECONDS` | 15 | Contexto entre bordes; admite 0–60 segundos |
| `RS_VIDEO_WORKERS` | 3 | Hasta tres lotes simultáneos por grabación; admite 1–6 |
| `RS_VIDEO_FRAMES_PER_BATCH` | 24 | Presupuesto de capturas; admite 4–48 |
| `RS_VIDEO_MAX_SLIDES` | 30 | Máximo incluida la portada; admite 2–80 |
| `RS_MAX_MODEL_CONCURRENCY` | 3 | Máximo de llamadas Responses por instancia |
| `RS_VISION_DETAIL` | high | Detalle de imagen: high, low o auto |
| `RS_TRANSCRIBER_MODEL` | vacío | Deployment de audio si no hay VTT/SRT |

El detalle alto está preparado para leer interfaces y localizar sus elementos. El costo y el tiempo dependen del modelo y del contenido; mide la diferencia antes de reducirlo. La caché distingue la configuración de detalle visual.

Dos horas se cubren con ocho ventanas centrales, con sus bordes compartidos. Una cola muy corta se absorbe en la ventana anterior. No se crea un lote por cada paso ni se genera una diapositiva por cada captura.

## Repeticiones y pasos

1. Capturas idénticas por todos sus píxeles: se envía una imagen y se conservan alias/tiempos. Un cambio de un píxel mantiene otra captura, evitando ocultar cambios de valor.
2. Una llamada multimodal por lote extrae actividades de uno a cuatro pasos, evidencia y regiones visibles. Las marcas se solicitan en esa misma llamada, sin otra consulta por flecha o clic.
3. Las actividades con título, objetivo, instrucciones y campos variables textualmente iguales se consolidan en todo el video conservando sus orígenes.
4. Una consolidación LLM global reúne también repeticiones con distinta redacción y conserva decisiones, variantes y excepciones.
5. Cada grupo original debe aparecer una vez o tener una exclusión justificada. Un grupo de cuatro pasos conserva cuatro pasos al consolidar.
6. Una llamada adicional genera las diez preguntas a partir del material final. El render de PPTX no vuelve a llamar al modelo.

Si el contenido relevante excede el presupuesto de láminas, se solicita acotar el alcance o ampliar el presupuesto mediante un error explícito. No se borran pasos silenciosamente. La evaluación se entrega aparte y no añade diez láminas.

## Frames y anotaciones

`frame_id` identifica la captura original de una actividad. `annotations` contiene regiones `{step_index, x, y, width, height}`. El índice es local de base cero; las coordenadas van de 0 a 1 sobre el frame completo antes de ajustarlo a la lámina. El backend calcula los números globales 1…n.

Se rechazan regiones fuera del frame, índices duplicados o inexistentes y marcas sin imagen disponible. Al consolidar, se recuperan regiones del análisis original vinculadas por instrucción; una instrucción cambiada no hereda un recuadro por su posición. Si varios frames contribuyen a una actividad, se muestra la captura que conserva más marcas. No se coloca una región de una captura sobre otra.

Las formas son nativas, superpuestas sobre la imagen sin modificarla: recuadro, flecha y etiqueta se pueden editar en PowerPoint. Los campos dinámicos generan una leyenda visible. Una geometría válida no acredita la precisión semántica de la localización; revisa una muestra contra los videos reales.

## Caché y publicación

Los checkpoints completos son atómicos y se separan por identidad, espacio de trabajo, huella del video, objetivo, deployment, endpoint, transcriptor, capturas, detalle de imagen y versión del prompt. Reprocesar el mismo video con el mismo objetivo reutiliza lotes completos. Cambiar usuario, archivo u objetivo evita reutilizar contexto ajeno. La consolidación global y las preguntas se regeneran.

Los archivos finales se construyen en una carpeta temporal y se publican juntos al completar la exportación. El SDK requiere un destino nuevo, para preservar las versiones previas. Los checkpoints válidos sobreviven a un fallo; el directorio de entrega no se publica si la evaluación o el render fallan.

El paralelismo de lotes es por grabación; las llamadas Responses se limitan por instancia del proveedor. En varias réplicas aplica cuotas, semáforos y cola compartidos en tu host. La caché no tiene caducidad automática: incorpora limpieza y retención en tu infraestructura.

## Medir con videos reales

El informe incluye duración, lotes, cache hits, capturas idénticas evitadas, grupos exactos consolidados, pasos, pasos anotados, exclusiones y llamadas. `elapsed_seconds` del resultado del SDK incluye análisis, evaluación y exportación; `elapsed_with_download_seconds` añade descarga en la entrada Graph. Los tiempos de pruebas con proveedores simulados no son un benchmark de inferencia.

Compara el mismo video, objetivo, contenido y calidad entre versiones. Mide p50/p95 por descarga, extracción, transcripción, visión, consolidación, cuestionario y exportación. Más workers pueden causar throttling y no necesariamente reducen el tiempo.

El muestreo uniforme de 24 frames en 15 minutos puede perder pantallas fugaces. Aumenta capturas o integra tu extractor por cambio de escena cuando haga falta. La cobertura es de grupos detectados, no prueba comprensión de todos los pasos reales. El ASR JSON entrega tiempos por lote, no por palabra.

Límites: 4 GB por video, 24 horas de duración, timeout de extracción de 10 minutos, audio de lote hasta 24 MiB, hasta 60 000 caracteres por segmento y 80 000 de transcripción por lote. Se rechaza el exceso; no se trunca el material silenciosamente.
