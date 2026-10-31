# Governance Studio

Agente de referencia en Python especializado en gobierno de datos y gobierno de inteligencia artificial. Incluye chat, recuperación con permisos, memoria persistente, adjuntos, marca configurable, creación de Word, PowerPoint y Excel y revisiones con versiones.

El diferenciador está en la conexión entre evidencia, hallazgos, implicaciones, riesgos, controles, responsables y acciones. Los tres formatos comparten un modelo documental con IDs estables. Las láminas tienen una narrativa propia y el Excel calcula sus indicadores. No se supone que más páginas equivalgan a más calidad.

## Probar en cinco minutos

Requiere Python 3.11 o posterior.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m governance_studio serve
```

En Windows activa con `.venv\Scripts\activate`. Abre [la interfaz local](http://127.0.0.1:8080). El modo inicial es **demo**, sin llamadas a modelos ni credenciales. Es un simulador: muestra contexto recuperado y genera un caso ficticio fijo de proveedores. **No interpreta preguntas ni revisiones libres como un modelo real.** La interfaz lo anuncia explícitamente. La edición estructurada por API sí funciona sin modelo.

```bash
python -m governance_studio demo --output examples/generated
python -m unittest discover -s tests -v
```

Los archivos de ejemplo ya están en `examples/generated`. `examples/build_custom.py` demuestra datasets, dashboards y gráficas personalizados con datos ficticios. `python examples/build_custom.py` los vuelve a generar después de instalar el paquete.

## Conectar el modelo y la búsqueda de tu empresa

No incluyas secretos en el repositorio. `.env.example` documenta las variables; el programa lee variables de entorno y **no carga ese archivo automáticamente**. Usa el gestor de secretos de tu plataforma.

```bash
export GS_MODE=azure
export GS_MODEL_BASE_URL='https://TU-RECURSO.openai.azure.com/openai/v1/'
export GS_ROUTER_MODEL='TU-DEPLOYMENT-DE-ENRUTAMIENTO'
export GS_WRITER_MODEL='TU-DEPLOYMENT-DOCUMENTAL'
export GS_SEARCH_ENDPOINT='https://TU-BUSCADOR.search.windows.net'
export GS_SEARCH_INDEX='TU-INDICE'
export GS_ENTRA=1
python -m pip install -e '.[azure]'
```

Configura `GS_TOKENS_JSON` mediante un secreto del servidor, con un token opaco largo por identidad. Ejemplo de estructura, sin tokens utilizables:

```json
{
  "REEMPLAZAR_POR_UN_TOKEN_ALEATORIO_DE_AL_MENOS_32_CARACTERES": {
    "tenant_id": "empresa",
    "user_id": "usuario",
    "role": "user"
  }
}
```

Para autenticación corporativa, integra el motor detrás de tu gateway y sustituye `Authenticator` por validación de Entra con firma, issuer, audience y vigencia. La identidad nunca debe provenir de un campo del cuerpo ni de encabezados sin validar. Los tokens opacos incluidos son un adaptador de referencia, no una implementación de SSO.

Si no utilizas identidad administrada, configura `GS_MODEL_API_KEY` y `GS_SEARCH_API_KEY` y omite `GS_ENTRA`. En Azure las credenciales se utilizan en el servidor, nunca en el navegador. `DefaultAzureCredential` requiere permisos de inferencia, consulta de Search y, si se habilita, escritura de Blob para la identidad efectiva.

**El deployment documental es configurable.** Puedes usar el deployment que tengas habilitado para GPT‑5.1 si admite Responses y Structured Outputs en tu recurso. El proyecto no comprueba su disponibilidad ni sustituye automáticamente un modelo por otro. La compatibilidad real se comprueba en tu entorno.

```bash
python -m governance_studio check
python -m governance_studio serve
```

`check` valida configuración local, no realiza una prueba de conexión.

## Qué incluye

| Función | Implementación |
|---|---|
| Intención | Clasificación semántica con esquema validado en modo Azure. Las reglas léxicas pertenecen exclusivamente al simulador. |
| Consultas | Respuesta especializada, fuentes recuperadas y separación entre explicación y diagnóstico del cliente. |
| Memoria | Historial completo en SQLite, ventana reciente y memoria acumulada de hechos, decisiones, preferencias y pendientes. |
| Fuentes | Base general, biblioteca pública, privada por usuario y adjuntos por conversación. En este asset, pública significa compartida dentro del tenant. |
| Word | Secciones variables, estilos, matrices de riesgos, controles, acciones, indicadores y carriles en tablas editables. |
| PowerPoint | Portada, varios layouts, narrativa ejecutiva, notas con fuentes, gráficas y diagrama de carriles nativos. |
| Excel | Dashboard del plan o datasets y métricas personalizados, fórmulas, validaciones, tablas y gráficas nativas. |
| Marca | Colores, cliente, tipografía y logo. La paleta sugerida se extrae de PNG/JPEG y se puede cambiar. |
| Edición | Revisión conversacional con el modelo o edición estructurada por IDs. Se conserva cada versión. |
| Ejecución | Trabajos en segundo plano, cola limitada, expansión concurrente para informes extensos, revisión consultiva con reparación acotada, estado y tiempos. |
| Integración | REST, uso directo del motor y publicación opcional en un Blob privado. |

No se ejecuta código producido por el modelo. El modelo devuelve contenido estructurado que los generadores convierten a archivos. El diseño tiene reglas de composición, pero el contenido, marca, datasets, métricas y narrativa se deciden por petición.

## Integrarlo sin reemplazar tu chat

```python
from governance_studio.config import Settings
from governance_studio.engine import Engine
from governance_studio.models import Principal, Theme, ChatRequest

engine = Engine(Settings.from_env())
principal = Principal(tenant_id=tenant_validado, user_id=usuario_validado)
cid = engine.store.create_conversation(principal, Theme().model_dump())
response = engine.chat(principal, cid, ChatRequest(
    message="Prepara un procedimiento de incorporación de proveedores con carriles",
    formats=["docx", "pptx", "xlsx"],
))
# Si response.type == job, consulta engine.store.job(principal, response['job_id']).
# Mantén el Engine durante la vida del servicio y llama close() al apagarlo.
```

Si tu sistema ya entiende consultas e intenciones, puedes reutilizar `Artifact`, `render` y `revise_structured` directamente. Si ya recupera fuentes, sustituye `Knowledge.retrieve` y conserva la autorización del lado del servidor. No es necesario duplicar tus Blob Storage ni tu indexer.

## Lecturas para implementación

- [Arquitectura y contratos de integración](docs/INTEGRACION.md)
- [Endpoints y ejemplos de revisión](docs/API.md)
- [Evaluación de calidad y comparación con Copilot](docs/EVALUACION.md)
- [Validación realizada y límites](docs/VALIDACION.md)

## Límites importantes de esta versión

- Es un asset funcional de referencia para integrar y evaluar, **no un despliegue productivo certificado**. El servidor de la biblioteca estándar es para desarrollo o uso detrás de infraestructura corporativa adecuada.
- Azure, Blob e inferencia real no se probaron con recursos de tu empresa. El modo demo no prueba calidad semántica ni tiempos del modelo.
- Los controles automáticos verifican estructura, relaciones, citas por ID y ausencia de mediciones. No demuestran que una cita respalde una afirmación ni que exista cumplimiento normativo. Hay que revisar el contenido y el diseño con casos del cliente.
- La memoria no equivale a contexto ilimitado. El historial se conserva, pero el modelo recibe una ventana y memoria compacta. Es posible que deba recuperar o confirmar un detalle antiguo.
- Ante una extensión explícita de 16 páginas o más, se genera un plan y se expanden sus secciones con concurrencia limitada. La extensión es orientativa y no garantiza un número exacto de páginas. Si una respuesta queda incompleta, no se publica una versión parcial. Ese flujo se probó con modelo simulado; falta medirlo con tus deployments.
- El parser acepta texto de PDF, Office y CSV. No hace OCR, no lee macros ni ejecuta fórmulas o enlaces externos. Los PDF complejos pueden requerir extracción corporativa adicional.
- El contenido seleccionado por recuperación tiene presupuesto: no se garantiza procesar de una vez todos los registros de un adjunto grande. Para análisis exhaustivos usa extracción tabular directa y reconciliación de conteos.
- Los dashboards recalculan al editar filas existentes. Para añadir o eliminar registros, genera una nueva versión. No se incluyen PivotTables, slicers ni What‑If Data Tables.
- Los cambios externos hechos directamente al Word o PowerPoint no vuelven solos al modelo documental. Adjunta la versión modificada y pide una revisión; para sincronización exacta se necesita un importador de diferencias.
- SQLite y la cola viven en un solo proceso. Al reiniciar, los trabajos incompletos se marcan fallidos y se pueden reenviar. Para varias réplicas se necesitan base y cola compartidas.

## Documentación oficial usada para los contratos

El adaptador de inferencia implementa salida estructurada conforme a [Structured Outputs de OpenAI](https://developers.openai.com/api/docs/guides/structured-outputs) y el endpoint de [Responses en Azure](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/responses). La búsqueda aplica [filtros de seguridad de Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-security-trimming-for-azure-search). El contenido de ejemplo sobre NIST enlaza al [AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework), de adopción voluntaria.
