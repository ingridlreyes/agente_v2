# API de referencia

El servidor sirve interfaz y endpoints en el mismo origen. Todas las rutas `/api` requieren `Authorization: Bearer TOKEN`, excepto el inicio de sesión del simulador local. No se habilita CORS abierto.

| Método | Ruta | Función |
|---|---|---|
| GET | /health | Estado, versión y modo |
| POST | /api/demo-session | Token efímero del simulador, solo en loopback |
| POST | /api/conversations | Crear conversación con tema |
| GET | /api/conversations/{id} | Mensajes, memoria, tema y versiones autorizadas |
| POST | /api/conversations/{id}/messages | Consultar, crear o revisar |
| POST | /api/conversations/{id}/attachments | Incorporar contexto |
| POST | /api/conversations/{id}/logo | Guardar imagen de marca |
| POST | /api/conversations/{id}/theme | Cambiar marca para nuevas creaciones |
| GET | /api/jobs/{id} | Estado del trabajo |
| GET | /api/artifacts/{id}?version=N | Modelo documental y fuentes |
| POST | /api/artifacts/{id}/revise | Editar por IDs sin modelo |
| GET | /api/artifacts/{id}/files/{name}?version=N | Descargar archivo autorizado |

## Crear conversación

```json
{"theme":{"client":"Cliente","primary":"#142D4E","accent":"#007F78","font":"Arial","logo_id":null}}
```

La respuesta contiene `conversation_id`. Conserva ese ID para mantener el hilo. Abrir una conversación nueva inicia otro contexto.

## Enviar mensaje

```json
{
  "message":"Prepara un proceso de incorporación de proveedores con carriles",
  "formats":["docx","pptx","xlsx"],
  "artifact_id":null
}
```

`formats` puede omitirse. Incluirlo no obliga a generar un archivo si la intención es una consulta. `artifact_id` permite seleccionar inequívocamente qué documento se desea modificar.

La respuesta tiene `type` answer, clarify o job. Una creación devuelve `job_id`. Consulta el estado cada dos segundos con espera creciente para trabajos largos. Los estados son queued, running, completed y failed. No se ofrece cancelación en esta versión.

`completed` significa que los archivos se construyeron y guardaron. **No significa aprobación consultiva ni revisión visual automática.** La calidad se devuelve como `requires_review`.

## Adjuntos

```json
{"filename":"politica.docx","data_base64":"BASE64_DEL_ARCHIVO","scope":"conversation"}
```

Scopes admitidos: conversation, private, base y public. Solo admin puede escribir base/public. Los archivos conversation se limitan a ese chat. Los private quedan disponibles para el mismo usuario dentro del tenant. La interfaz usa conversation por defecto.

Formatos: TXT, MD, CSV, PDF con texto, DOCX, PPTX y XLSX. Máximo 12 MB, 150 páginas PDF y 180000 caracteres extraídos. Los límites se comunican como errores, no se recorta silenciosamente el archivo en la ingesta. La recuperación posterior sí utiliza chunks seleccionados con un presupuesto de contexto.

## Logo y tema

El endpoint logo recibe `{"data_base64":"..."}` y devuelve logo_id y colores sugeridos. Después envía el tema completo al endpoint theme para aplicarlo. PNG/JPEG hasta 4 MB y 12 megapíxeles. Los archivos de imagen se normalizan para retirar metadata ajena a la imagen.

## Edición estructurada

```json
{
  "conversation_id":"ID_CONVERSACION",
  "changes":{
    "theme":{"primary":"#663399","accent":"#007F78"},
    "nodes":[{"id":"N4","lane":"Compras"}],
    "sections":[{"id":"alcance","heading":"Alcance del proceso de proveedores"}]
  }
}
```

Se genera una nueva versión y se conserva la anterior. Campos permitidos: theme, sections, nodes, title y decision. Cada sección o nodo requiere su ID existente. Las revisiones libres con el modelo pueden modificar también riesgos, controles, acciones y conexiones.

Una edición estructurada modifica exactamente los campos indicados. Si cambias un responsable en un nodo, también debes actualizar el texto o controles que lo mencionen si corresponde. Una revisión conversacional puede solicitar esa reconciliación semántica.

## Paquete de salida

- entregable.docx, entregable.pptx y/o entregable.xlsx según petición.
- proceso.svg y, si no se pidió PowerPoint, proceso_editable.pptx como complemento cuando hay proceso.
- artifact.json: modelo canónico que permite nuevas revisiones.
- sources.json: fuentes recuperadas para la versión. Puede contener extractos privados; no compartir fuera del público autorizado.
- quality.json: validaciones estructurales y limitaciones.
- paquete.zip: todos los archivos de la versión.

La API autoriza cada descarga. No entregues una ruta de disco directamente ni publiques `sources.json` sin revisar su audiencia. El contenido de las fuentes no incluye datos de otros usuarios que hayan sido rechazados por los filtros.
