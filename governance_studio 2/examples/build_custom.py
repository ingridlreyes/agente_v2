"""Ejemplo alternativo: un workbook de calidad y una gráfica nativa en PowerPoint.
Ejecutar después de instalar el paquete: python examples/build_custom.py
"""
from pathlib import Path
from governance_studio.demo import sample
from governance_studio.models import WorkbookPlan
from governance_studio.renderers import render

spec = sample()
spec.title = "Seguimiento de calidad de datos por dominio"
spec.objective = "Demostrar un dashboard configurable con datos ficticios y una gráfica editable vinculada al mismo conjunto de datos."
spec.decision = "Definir responsables y umbrales después de validar los registros de origen."
spec.workbook = WorkbookPlan.model_validate({
    "datasets":[{"id":"calidad","name":"Calidad por dominio","columns":[
        {"key":"dominio","label":"Dominio","kind":"text"},
        {"key":"validos","label":"Registros válidos","kind":"number"},
        {"key":"total","label":"Registros revisados","kind":"number"}],
        "rows":[{"values":["Proveedores",80,100]},{"values":["Clientes",135,150]},{"values":["Productos",70,100]}],
        "source_ids":[],"note":"Todos los valores son ficticios para demostrar fórmulas y gráficas."}],
    "metrics":[
        {"label":"Registros revisados","dataset_id":"calidad","operation":"sum","column":"total","unit":"number"},
        {"label":"Registros válidos","dataset_id":"calidad","operation":"sum","column":"validos","unit":"number"},
        {"label":"Calidad ponderada","dataset_id":"calidad","operation":"ratio_sums","column":"validos","denominator_column":"total","unit":"ratio"}],
    "charts":[{"title":"Registros válidos por dominio","dataset_id":"calidad","category_column":"dominio","value_column":"validos","kind":"bar"}]
})
spec.slides = [spec.slides[-1].model_copy(update={"title":"Calidad de datos por dominio","message":"Los valores del ejemplo son ficticios. La gráfica y el dashboard comparten los mismos datos.","items":[],"dataset_id":"calidad","chart":"bar"})]
spec.process = None
render(spec,[],Path(__file__).parent/"custom_generated",["xlsx","pptx"])
print("Ejemplo personalizado generado en examples/custom_generated")
