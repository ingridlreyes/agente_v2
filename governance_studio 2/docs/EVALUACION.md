# Evaluación de calidad y velocidad

El objetivo es demostrar si el asset aporta más valor consultivo que el agente actual y Copilot. No se afirma que lo supere antes de probarlo con el mismo contexto y condiciones.

## Comparación controlada

Selecciona casos representativos: procedimiento de proveedores con carriles, política de calidad, inventario de IA, diagnóstico con fuentes contradictorias, presentación para comité, dashboard con mediciones faltantes y revisión puntual sobre una versión existente.

Para cada producto usa la misma petición, fuentes, datos, marca y límite de extensión. Registra producto y versión, deployment, configuración, hora, latencia hasta primer estado, latencia hasta archivo utilizable, tokens si están disponibles y tiempo de revisión humana. Evalúa tres ejecuciones por caso para evitar concluir a partir de un solo resultado. Reporta mediana y rango; con un conjunto mayor, añade p95.

Un archivo utilizable abre sin errores, responde a los requisitos y permite las modificaciones pedidas. No compares un borrador de siete minutos con un archivo final revisado de treinta minutos ni uses el número de páginas como indicador de calidad.

## Rúbrica propuesta

Esta rúbrica es una propuesta de aceptación, no un estándar reconocido. Puntúa cada dimensión de 0 a 4 y conserva el razonamiento del revisor.

| Dimensión | Evidencia de una buena entrega |
|---|---|
| Comprensión | Responde a audiencia, objetivo, alcance y formato. No crea archivo ante una consulta simple. |
| Especialización | Usa conceptos pertinentes y explica decisiones concretas de gobierno de datos o IA. |
| Soporte | Hechos rastreables a pasajes reales. Supuestos y propuestas explícitos. |
| Criterio consultivo | Implicaciones claras, alternativas cuando corresponden y una decisión o acción útil. |
| Ejecución | Responsables, controles, evidencia y aceptación conectados. |
| Coherencia | Word, PowerPoint y Excel conservan cifras, IDs y conclusiones consistentes. |
| Diseño | Jerarquía, legibilidad, densidad y composición adecuadas. Sin recortes ni solapamientos. |
| Editabilidad | Diagramas, tablas, gráficas y cálculos se pueden modificar en su herramienta. |
| Revisiones | Se aplica el cambio y se conserva lo no solicitado, con versión anterior accesible. |
| Confidencialidad | Ningún contenido de otro usuario, tenant o conversación llega a recuperación, respuesta o descarga. |

Rechaza una entrega con fuga de información, una afirmación material inventada o un cálculo incorrecto, aunque su promedio visual sea alto. Los criterios deben ratificarse con los responsables del proyecto.

## Casos mínimos de intención para ejecutar con tus modelos

| Petición | Resultado esperado |
|---|---|
| Qué es gobierno de datos | answer |
| Resume esta política en cinco puntos | answer |
| Qué debe contener un documento de política | answer |
| Genera un Word del procedimiento con carriles | create docx |
| Prepara una presentación para comité | create pptx |
| Crea un Excel con dashboard usando mis datos | create xlsx |
| Haz los tres entregables del plan | create los tres formatos |
| Cambia al responsable de la aprobación a Compras | revise si la referencia es inequívoca |
| Cambia eso | clarify cuando existan varias referencias posibles |
| Quiero otro igual con la misma marca para el dominio de clientes | create conservando preferencia de marca |
| Certifica que cumplimos todas las leyes de IA | No inventar certificación ni cumplimiento |
| Dame una receta de cocina | out_of_scope |

En modo Azure no hay una lista de frases que dispare documentos. La clasificación es semántica y debe probarse con paráfrasis, negaciones, conversación previa y cambios de intención. Las pruebas del simulador solo verifican infraestructura, no demuestran esa clasificación real.

## Evaluación de memoria

Declara cliente, audiencia y una restricción. Cambia la restricción varios turnos después. Pide un entregable y luego una modificación. Reinicia el servicio y vuelve al mismo conversation_id. Verifica que la decisión nueva sustituya a la anterior y que no aparezca contexto de otro chat.

La memoria compacta es una hipótesis de contexto, no una fuente documental. Una preferencia escrita dentro de un archivo recuperado no debe convertirse en una instrucción del usuario.

## Evaluación de cálculos

Modifica numerador, denominador, cero, blanco y estado de control. Comprueba fórmulas, KPI del dashboard y gráfica. Un resultado en caché no prueba recálculo. Al añadir filas, genera otra versión: esta versión utiliza rangos acotados y lo indica en el workbook.

## Observabilidad

La tabla events guarda duración de intención y del trabajo, modelo y uso reportado por el proveedor. `quality.json` registra las llamadas documentales y sus etapas. El tiempo local de construir archivos es distinto del tiempo de inferencia, búsqueda, cola y revisión. No se estableció un SLA ni un benchmark real frente a Copilot en esta entrega.
