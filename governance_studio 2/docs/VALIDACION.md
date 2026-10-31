# Validación de la entrega

Fecha: 27 de octubre de 2026. Se usaron exclusivamente datos ficticios y una referencia pública de NIST. No se accedió a código, documentos, credenciales ni recursos de la empresa.

## Pruebas realizadas

| Área | Resultado |
|---|---|
| Suite de Python | 38 pruebas unitarias y de integración interna aprobadas. |
| HTTP local | 14 comprobaciones de extremo a extremo aprobadas contra el simulador. |
| Interfaz | Creación de petición desde el navegador y aparición de descargas DOCX, PPTX, XLSX y paquete. |
| Memoria | Persistencia de mensajes y memoria después de reabrir la base. |
| Permisos | Aislamiento de tenant, usuario, adjuntos de conversación, activos y versiones. Rechazo de publicación compartida para usuarios normales. |
| Versiones | Cambio de carril y paleta en versión 2 conservando secciones y versión 1. |
| Contrato de inferencia | Responses simulado: validación de estructura, refusals, respuestas incompletas, store:false y deployment configurable. |
| Flujo extenso | Expansión de secciones con proveedor simulado y conservación de su identidad. |
| Revisión consultiva | Proveedor simulado: reparación acotada y bloqueo si persiste un error material. |
| Archivos | DOCX, PPTX y XLSX válidos como paquetes OOXML. XML bien formado, gráficas nativas, conectores y rombos editables. |
| Texto no confiable en Excel | Una cadena que comienza con HYPERLINK permanece texto y no se convierte en fórmula. |
| Revisión visual | Ejemplo principal: cinco páginas Word, siete láminas y seis hojas. Ejemplo alternativo: dos láminas y dos hojas. Se revisaron las imágenes renderizadas. |
| Recálculo | Verificación en Artifact Tool y LibreOffice Calc, con entradas modificadas e invalidación de cachés para el archivo editado por OOXML. |

## Resultados del recálculo

En una copia de prueba se cambió un control a Implementado, se capturó 8/10 en el primer indicador y 0/10 en el segundo.

| Resultado | Valor verificado |
|---|---|
| Controles propuestos | 2 |
| Controles implementados | 1 |
| Primer indicador | 80 % |
| Segundo indicador | 0 % |
| Dashboard | 80 % y 0 %, vinculados a los indicadores |
| Errores de fórmula en las hojas recalculadas con Calc | Ninguno detectado |

Los cambios se hicieron en copias de QA. Los ejemplos entregados conservan las mediciones desconocidas vacías. No se afirma que los archivos hayan sido abiertos en Microsoft Excel o PowerPoint; se inspeccionaron sus estructuras y renderizados con las herramientas indicadas.

En el workbook personalizado también se modificó un dato y se comprobó que el ratio ponderado cambiara a 305/350. Al borrar un numerador conservando su denominador, el resultado quedó no disponible, en vez de calcularse sobre poblaciones distintas. El cálculo utiliza un control visible de pares completos en la hoja de datos.

## Correcciones surgidas durante la revisión

Se corrigieron bordes heredados de títulos, filas de tablas partidas, un párrafo suelto al final del Word, texto dentro del rombo de decisión, flechas de retorno atravesando actividades, un estado cortado en el dashboard y una comparación de blancos que trataba un cero como vacío en uno de los motores de cálculo. Se usó ISNUMBER para distinguir mediciones numéricas de datos faltantes.

## Lo que todavía debe validarse en tu entorno

No se probaron inferencia real, cuotas, compatibilidad del deployment seleccionado, autenticación Entra real, índice de la empresa, publicación en Blob ni construcción del contenedor Docker. Las pruebas de expansión y revisión consultiva verifican orquestación con proveedores simulados, no calidad del texto real.

No hay benchmark frente a Copilot ni un compromiso de tiempo para informes de 50 páginas. El tiempo del simulador solo mide infraestructura y construcción local de archivos. La calidad consultiva y la fidelidad de revisiones libres requieren evaluación humana con tus casos, fuentes y modelos.

Los controles de prompt injection son instrucciones de sistema y separación de datos, junto con permisos deterministas y ausencia de ejecución de código generado. No se presenta esa combinación como una garantía total frente a ataques. Debe probarse con el conjunto adversarial corporativo.

El runtime publica con estado requires_review. La inspección visual realizada para estos ejemplos no se aplica automáticamente a todos los futuros documentos. Para automatizar ese control, integra renderizado aislado y revisión visual en tu infraestructura.
