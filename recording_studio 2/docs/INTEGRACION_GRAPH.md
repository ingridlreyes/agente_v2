# Integración del procesador de grabaciones

## Contrato del SDK

`RecordingService.generate_file(principal, path, brief, output_directory, subtitles=None, theme=None, workspace_id="default", progress=None, include_word=True)` procesa una ruta elegida y autorizada por el backend. Usa esta entrada después de tu subida actual a Blob o almacenamiento local. No pases directamente una ruta enviada por un usuario HTTP.

`RecordingService.generate_graph(principal, reference, brief, output_directory, ...)` obtiene la grabación mediante Graph y ejecuta ese mismo flujo. `reference` acepta **un** `sharing_url` o **ambos** `drive_id` e `item_id`. La descarga temporal se elimina al terminar; el archivo original remoto no cambia.

La respuesta incluye `directory`, `files`, `report` y `elapsed_seconds`. La ruta Graph añade `elapsed_with_download_seconds`. Los callbacks de avance describen la etapa; conecta `progress` al estado de tu trabajo en la aplicación existente. Las funciones son síncronas y sus lotes sí se paralelizan: invócalas desde tu cola actual, fuera del hilo de la petición HTTP.

`theme` acepta cliente, colores principal/acento y tipografía permitida. Los números de los pasos se calculan al exportar y coinciden con las marcas. Para recibir únicamente PPTX y evaluación, pasa `include_word=False`.

## Resolver la identidad de Microsoft

```python
from recording_studio.integrations.microsoft_graph import GraphClient, GraphIdentityToken


def graph_token_for(principal):
    """Devuelve el token Graph de la misma identidad autenticada y validada por el host."""
    token = corporate_sessions.graph_access_token(principal.tenant_id, principal.user_id)
    return GraphIdentityToken(token, principal.tenant_id, principal.user_id)


client = GraphClient(graph_token_for)
```

`corporate_sessions` representa el servicio de sesiones que debes conectar en tu empresa. Nunca recibas el bearer Graph en un campo del formulario de generación. El cliente compara la identidad del token resuelto con `Principal`; la validación criptográfica de la sesión pertenece a tu host.

También se incluye `make_obo_provider(tenant_id, client_id, client_secret, assertion_resolver)`. El resolvedor devuelve una aserción Entra que el host ya validó: firma, issuer, audience, sujeto, tenant y vigencia. Instala el extra Azure y usa el gestor de secretos de tu plataforma. La función OBO no implementa por sí sola el login ni valida un JWT arbitrario.

## Enlaces reconocidos

- Vínculos compartidos de SharePoint o OneDrive.
- Enlaces Teams con `driveId` y `driveItemId`.
- Enlaces Teams que incluyen `fileUrl`, `objectUrl`, `recordingUrl` o `webUrl` de SharePoint/OneDrive.

Un enlace genérico de reunión o mensaje no siempre identifica una grabación. En ese caso, utiliza **Abrir en SharePoint / Copiar vínculo** del archivo de grabación. Los archivos eliminados, expirados o fuera de los permisos efectivos del usuario no son accesibles.

El adaptador hace GET y no agrega permisos ni usa `Prefer: redeemSharingLink`. Los permisos delegados documentados por Microsoft dependen del endpoint:

| Operación | Permiso mínimo documentado |
|---|---|
| Descargar un archivo conocido por IDs | `Files.Read` |
| Resolver el vínculo mediante `/shares/.../driveItem` | `Files.ReadWrite` según la tabla de `/shares` |
| Leer transcripciones de reunión | `OnlineMeetingTranscript.Read.All`, con acceso y políticas aplicables |

La resolución de un vínculo exige en la documentación un permiso de escritura aunque el código haga GET. Si la política corporativa lo impide, resuelve el vínculo con tu servicio existente y entrega `drive_id/item_id`. Los consentimientos no se conceden automáticamente desde este asset.

Al seguir la descarga firmada, el cliente retira `Authorization` y limita el destino a dominios Microsoft permitidos. Comprueba tamaño y eTag para no procesar una descarga incompleta o un archivo que cambió durante el streaming. Implementa Graph global; las nubes soberanas necesitan adaptar endpoint y dominios.

## Reutilizar transcripciones existentes

`client.transcripts(principal, organizer_id, meeting_id)` y `client.transcript_text(principal, organizer_id, meeting_id, transcript_id)` permiten recuperar un VTT existente. Pásalo como `subtitles`. El host obtiene esos IDs; no se descubren automáticamente desde cualquier URL de Teams.

Si usas un transcriptor distinto, inyecta un objeto con `transcribe(audio_path, batch) -> list[Segment]`. Si ya tienes capturas por cambio de escena, sustituye `MediaTools.prepare` preservando los IDs, tiempos y el frame original completo; así las regiones normalizadas mantienen su referencia.

## Referencias oficiales

- [Descargar driveItem](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0).
- [Enlaces compartidos y permisos](https://learn.microsoft.com/en-us/graph/api/shares-get?view=graph-rest-1.0).
- [Transcripciones de Teams](https://learn.microsoft.com/en-us/graph/api/onlinemeeting-list-transcripts?view=graph-rest-1.0).
- [Structured Outputs de OpenAI](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
