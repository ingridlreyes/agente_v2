import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from pydantic import ValidationError
from governance_studio.attachments import extract, ingest, save_logo, checked_zip
from governance_studio.config import Settings
from governance_studio.demo import sample
from governance_studio.engine import Engine
from governance_studio.models import Principal, Theme, ChatRequest, Artifact, WorkbookPlan, Source, Section, ConsultingReview
from governance_studio.providers import Knowledge, security_filter, strict_schema, ResponsesModel, ProviderError
from governance_studio.quality import review
from governance_studio.renderers import render, excel, powerpoint
from governance_studio.store import Store
from governance_studio.workbooks import metric_result
from governance_studio.server import Authenticator


def custom_workbook():
    return WorkbookPlan.model_validate({"datasets":[{"id":"calidad","name":"Calidad de datos","columns":[
        {"key":"dominio","label":"Dominio","kind":"text"},
        {"key":"validos","label":"Registros válidos","kind":"number"},
        {"key":"total","label":"Registros revisados","kind":"number"}],
        "rows":[{"values":["Proveedores",8,10]},{"values":["Clientes",12,20]}],"note":"Datos ficticios para pruebas", "source_ids":[]}],
        "metrics":[{"label":"Calidad ponderada","dataset_id":"calidad","operation":"ratio_sums","column":"validos","denominator_column":"total","unit":"ratio"}],
        "charts":[{"title":"Registros válidos por dominio","dataset_id":"calidad","category_column":"dominio","value_column":"validos","kind":"bar"}]})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.p = Principal(tenant_id="t1",user_id="alice")
        self.bob = Principal(tenant_id="t1",user_id="bob")
        self.other = Principal(tenant_id="t2",user_id="alice")
        self.admin = Principal(tenant_id="t1",user_id="admin",role="admin")
        self.store = Store(self.root)
        self.cid = self.store.create_conversation(self.p,Theme().model_dump())
    def tearDown(self):
        self.tmp.cleanup()


class SecurityTests(Base):
    def test_conversation_cannot_be_read_by_other_user_or_tenant(self):
        for p in (self.bob,self.other):
            with self.assertRaises(KeyError): self.store.conversation(p,self.cid)

    def test_acl_applied_before_retrieval(self):
        cid2 = self.store.create_conversation(self.p,Theme().model_dump())
        for p,scope,cid,text in [(self.p,"private",self.cid,"dato privado alice"),
                                 (self.bob,"private",self.cid,"dato privado bob"),
                                 (self.p,"conversation",self.cid,"dato conversación actual"),
                                 (self.p,"conversation",cid2,"dato conversación distinta"),
                                 (self.admin,"base",self.cid,"dato base"),
                                 (self.admin,"public",self.cid,"dato público")]:
            self.store.add_chunk(p,scope,cid,text,"test",text)
        k = Knowledge(self.store,Settings(data_dir=self.root))
        texts = " ".join(s.text for s in k.retrieve(self.p,self.cid,"dato"))
        self.assertIn("alice",texts); self.assertIn("base",texts);self.assertIn("público",texts)
        self.assertNotIn("bob",texts);self.assertNotIn("distinta",texts)

    def test_user_cannot_publish_to_shared_libraries(self):
        for scope in ("base","public"):
            with self.assertRaises(PermissionError): self.store.add_chunk(self.p,scope,self.cid,"x","x","x")

    def test_odata_quotes_escaped(self):
        p = Principal(tenant_id="x' or true",user_id="u'")
        f = security_filter(p,"c'")
        self.assertIn("tenant_id eq 'x'' or true'",f)
        self.assertIn("owner_id eq 'u'''",f)

    def test_azure_result_checked_again_after_filter(self):
        s = Settings(mode="azure",data_dir=self.root,search_endpoint="https://example.invalid",search_index="x")
        with patch("governance_studio.providers.post_json",return_value={"value":[{"tenant_id":"another"}]}):
            with self.assertRaises(ProviderError): Knowledge(self.store,s).retrieve(self.p,self.cid,"dato")

    def test_assets_isolated_by_conversation(self):
        from PIL import Image
        data = io.BytesIO();Image.new("RGB",(30,30),"blue").save(data,format="PNG")
        asset=save_logo(self.store,self.p,self.cid,data.getvalue())
        cid2=self.store.create_conversation(self.p,Theme().model_dump())
        with self.assertRaises(KeyError):self.store.asset(self.p,cid2,asset["logo_id"])

    def test_opaque_token_identity_from_server(self):
        token="a"*40
        auth=Authenticator(Settings(mode="azure",tokens_json=json.dumps({token:self.p.model_dump()})))
        self.assertEqual(auth.authenticate("Bearer "+token).user_id,"alice")
        with self.assertRaises(PermissionError):auth.authenticate("Bearer alice")


class DataTests(Base):
    def test_invalid_graph_reference_rejected(self):
        d=sample().model_dump();d["process"]["edges"][0]["target"]="missing"
        with self.assertRaises(ValidationError):Artifact.model_validate(d)

    def test_invalid_control_risk_link_rejected(self):
        d=sample().model_dump();d["controls"][0]["risk_ids"]=["missing"]
        with self.assertRaises(ValidationError):Artifact.model_validate(d)

    def test_duplicate_stable_id_rejected(self):
        d=sample().model_dump();d["sections"].append(d["sections"][0])
        with self.assertRaises(ValidationError):Artifact.model_validate(d)

    def test_fabricated_citation_blocks_publication(self):
        s=sample();s.sections[0].source_ids=["fake"]
        self.assertEqual(review(s,[])["status"],"blocked")

    def test_fact_requires_source(self):
        s=sample();s.findings[0].kind="fact"
        self.assertTrue(review(s,[])["errors"])

    def test_unknown_measurement_stays_missing(self):
        s=sample();self.assertIsNone(s.kpis[0].numerator)
        self.assertIn("Hay indicadores pendientes de medición",review(s,[])["warnings"])

    def test_invalid_workbook_numeric_type(self):
        d=custom_workbook().model_dump();d["datasets"][0]["rows"][0]["values"][1]="not a number"
        with self.assertRaises(ValidationError):WorkbookPlan.model_validate(d)

    def test_weighted_ratio_uses_matching_population(self):
        w=custom_workbook()
        self.assertAlmostEqual(metric_result(w.metrics[0],w.datasets[0]),20/30)
        w.datasets[0].rows[0].values[1]=None
        self.assertEqual(metric_result(w.metrics[0],w.datasets[0]),"")

    def test_zero_numerator_distinct_from_missing(self):
        w=custom_workbook()
        for r in w.datasets[0].rows:r.values[1]=0
        self.assertEqual(metric_result(w.metrics[0],w.datasets[0]),0)
        for r in w.datasets[0].rows:r.values[2]=0
        self.assertEqual(metric_result(w.metrics[0],w.datasets[0]),"")

    def test_strict_schema_has_required_and_no_additional_properties(self):
        schema=strict_schema(Artifact.model_json_schema())
        self.assertEqual(set(schema["required"]),set(schema["properties"]))
        self.assertFalse(schema["additionalProperties"])


class AttachmentTests(Base):
    def test_text_chunking_and_conversation_context(self):
        result=ingest(self.store,self.p,self.cid,"policy.txt",("dato "*1700).encode())
        self.assertGreater(result["chunks"],1)
        self.assertTrue(self.store.chunks(self.p,self.cid))

    def test_resume_attachment_keeps_context_without_keyword_overlap(self):
        ingest(self.store,self.p,self.cid,"politica.txt","Clasificación del catálogo corporativo y responsables del linaje".encode())
        k=Knowledge(self.store,Settings(data_dir=self.root))
        self.assertTrue(k.retrieve(self.p,self.cid,"Resume el adjunto"))

    def test_unknown_extension_rejected(self):
        with self.assertRaises(ValueError):extract(b"hello","program.exe")

    def test_macro_rejected(self):
        out=io.BytesIO()
        with ZipFile(out,"w") as z:z.writestr("word/vbaProject.bin",b"macro")
        with self.assertRaises(ValueError):checked_zip(out.getvalue())

    def test_office_document_text_extraction(self):
        from docx import Document
        d=Document();d.add_paragraph("Datos de proveedores");out=io.BytesIO();d.save(out)
        self.assertIn("Datos de proveedores",extract(out.getvalue(),"test.docx")[0][1])

    def test_empty_or_scanned_text_rejected(self):
        with self.assertRaises(ValueError):extract(b"   ","test.txt")


class RenderTests(Base):
    def test_tall_logo_and_light_brand_render_in_all_formats(self):
        from PIL import Image
        logo=self.root/"logo.png";Image.new("RGB",(30,300),"purple").save(logo)
        s=sample();s.theme.primary="#FFFFFF"
        files=render(s,[],self.root/"brand",["docx","pptx","xlsx"],logo)
        self.assertIn("entregable.xlsx",files)
        with ZipFile(self.root/"brand"/"entregable.xlsx") as z:
            self.assertIn("xl/media/image1.png",z.namelist())

    def test_all_formats_are_valid_native_packages(self):
        s=sample();files=render(s,[],self.root/"out",["docx","pptx","xlsx"])
        self.assertIn("proceso.svg",files)
        for fmt in ("docx","pptx","xlsx"):
            with ZipFile(self.root/"out"/("entregable."+fmt)) as z:
                self.assertIsNone(z.testzip())
                for name in z.namelist():
                    if name.endswith(".xml"):ET.fromstring(z.read(name))

    def test_pptx_diagram_has_native_shapes_and_connectors(self):
        s=sample();powerpoint(s,[],self.root/"x.pptx")
        with ZipFile(self.root/"x.pptx") as z:
            xml="".join(z.read(n).decode() for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith("xml"))
            self.assertIn("cxnSp",xml);self.assertIn("diamond",xml);self.assertIn("N4",xml)

    def test_excel_user_text_cannot_become_formula(self):
        s=sample();s.risks[0].title='=HYPERLINK("https://evil.invalid","x")'
        excel(s,[],self.root/"x.xlsx")
        with ZipFile(self.root/"x.xlsx") as z:
            strings=z.read("xl/sharedStrings.xml").decode()
            self.assertIn("HYPERLINK",strings)
            xml=z.read("xl/worksheets/sheet2.xml").decode()
            self.assertNotIn("<f>HYPERLINK",xml)

    def test_custom_workbook_and_native_slide_chart(self):
        s=sample();s.workbook=custom_workbook()
        s.slides[0].dataset_id="calidad";s.slides[0].chart="bar"
        excel(s,[],self.root/"x.xlsx");powerpoint(s,[],self.root/"x.pptx")
        with ZipFile(self.root/"x.xlsx") as z:
            self.assertIn("xl/charts/chart1.xml",z.namelist())
            self.assertIn("SUM(",z.read("xl/worksheets/sheet1.xml").decode())
        with ZipFile(self.root/"x.pptx") as z:self.assertIn("ppt/charts/chart1.xml",z.namelist())


class EngineTests(Base):
    def setUp(self):
        super().setUp();self.engine=Engine(Settings(data_dir=self.root))
    def tearDown(self):
        self.engine.close();super().tearDown()
    def wait_job(self,jid):
        for _ in range(200):
            job=self.store.job(self.p,jid)
            if job["status"] in ("completed","failed"):return job
            time.sleep(.025)
        self.fail("Trabajo no terminó")

    def test_query_does_not_create_document(self):
        result=self.engine.chat(self.p,self.cid,ChatRequest(message="¿Qué es gobierno de datos?"))
        self.assertEqual(result["type"],"answer")
        self.assertEqual(self.store.list_versions(self.p,self.cid),[])

    def test_out_of_scope_stays_out(self):
        result=self.engine.chat(self.p,self.cid,ChatRequest(message="Dame una receta de pizza"))
        self.assertIn("gobierno de datos",result["text"])
        self.assertNotIn("job_id",result)

    def test_job_version_edit_preserves_original_and_untouched_sections(self):
        result=self.engine.chat(self.p,self.cid,ChatRequest(message="Genera un documento de proveedores",formats=["docx","xlsx"]))
        job=self.wait_job(result["job_id"])
        self.assertEqual(job["status"],"completed",job)
        aid=job["result"]["artifact_id"]
        before=self.store.version(self.p,aid)
        jid=self.engine.revise_structured(self.p,self.cid,aid,{"nodes":[{"id":"N4","lane":"Compras"}],"theme":{"primary":"#663399"}})
        updated=self.wait_job(jid)
        self.assertEqual(updated["status"],"completed",updated)
        v2=self.store.version(self.p,aid)
        self.assertEqual(v2["version"],2)
        self.assertEqual(v2["spec"]["process"]["nodes"][3]["lane"],"Compras")
        self.assertEqual(v2["spec"]["sections"],before["spec"]["sections"])
        self.assertEqual(self.store.version(self.p,aid,1)["spec"]["theme"]["primary"],"#142D4E")

    def test_artifact_cannot_be_revised_from_different_conversation(self):
        result=self.engine.chat(self.p,self.cid,ChatRequest(message="Genera un documento de datos"))
        job=self.wait_job(result["job_id"]);aid=job["result"]["artifact_id"]
        cid2=self.store.create_conversation(self.p,Theme().model_dump())
        with self.assertRaises(KeyError):self.engine.revise_structured(self.p,cid2,aid,{"title":"x"})
        with self.assertRaises(KeyError):self.store.version(self.bob,aid)

    def test_restart_preserves_history_and_memory(self):
        self.engine.chat(self.p,self.cid,ChatRequest(message="Explícame gobierno de datos"))
        second=Store(self.root)
        self.assertEqual(len(second.messages(self.p,self.cid)),2)
        self.assertTrue(second.conversation(self.p,self.cid)["memory"]["facts"])

    def test_failed_validation_does_not_publish_version(self):
        s=sample();s.source_ids=["fabricated"]
        jid=self.engine.submit(self.p,self.cid,{"message":"test","sources":[]},["docx"],spec=s)
        job=self.wait_job(jid)
        self.assertEqual(job["status"],"failed")
        self.assertEqual(self.store.list_versions(self.p,self.cid),[])


class ProviderTests(unittest.TestCase):
    def test_response_refusal_and_incomplete_not_parsed_as_success(self):
        model=ResponsesModel(Settings(model_base_url="https://example.invalid/"))
        for payload in ({"status":"incomplete"},{"status":"completed","output":[{"content":[{"type":"refusal"}]}]}):
            with patch("governance_studio.providers.post_json",return_value=payload):
                with self.assertRaises(ProviderError):model.generate(Artifact,"x",{})

    def test_valid_responses_contract(self):
        model=ResponsesModel(Settings(model_base_url="https://example.invalid/openai/v1/",writer_model="deployment"))
        payload={"status":"completed","output":[{"type":"message","content":[{"type":"output_text","text":sample().model_dump_json()}]}],"usage":{"total_tokens":100}}
        with patch("governance_studio.providers.post_json",return_value=payload) as call:
            s,usage=model.generate(Artifact,"instructions",{})
            self.assertEqual(s.title,sample().title)
            self.assertFalse(call.call_args.args[1]["store"])
            self.assertEqual(call.call_args.args[1]["model"],"deployment")


class ConsultingPipelineTests(Base):
    def test_long_form_expands_sections_and_reviews(self):
        class Fake:
            def generate(self,schema,instructions,context,**kw):
                if schema is Artifact:return sample(),{"simulated":True}
                if schema is Section:
                    s=Section.model_validate(context["section"])
                    s.paragraphs.append("Detalle expandido para prueba del flujo.")
                    return s,{"simulated":True}
                if schema is ConsultingReview:return ConsultingReview(),{"simulated":True}
                raise AssertionError(schema)
        engine=Engine(Settings(mode="azure",data_dir=self.root),model=Fake())
        try:
            jid=engine.submit(self.p,self.cid,{"message":"Informe de 30 páginas","long_form":True,"target_pages":30,"sources":[]},["docx"])
            for _ in range(200):
                job=self.store.job(self.p,jid)
                if job["status"] in ("completed","failed"):break
                time.sleep(.025)
            self.assertEqual(job["status"],"completed",job)
            record=self.store.version(self.p,job["result"]["artifact_id"])
            self.assertIn("Detalle expandido",record["spec"]["sections"][0]["paragraphs"][-1])
            self.assertEqual(len(job["result"]["quality"]["model_calls"]),6)
        finally:engine.close()

    def test_material_review_failure_never_publishes(self):
        class Fake:
            calls=0
            def generate(self,schema,instructions,context,**kw):
                self.calls+=1
                if schema is Artifact:return sample(),{}
                if schema is ConsultingReview:return ConsultingReview(blocking_issues=["Falta un requisito material"]),{}
                raise AssertionError(schema)
        fake=Fake();engine=Engine(Settings(mode="azure",data_dir=self.root),model=fake)
        try:
            jid=engine.submit(self.p,self.cid,{"message":"test","sources":[]},["docx"])
            for _ in range(200):
                job=self.store.job(self.p,jid)
                if job["status"] in ("completed","failed"):break
                time.sleep(.025)
            self.assertEqual(job["status"],"failed")
            self.assertEqual(fake.calls,4)
            self.assertEqual(self.store.list_versions(self.p,self.cid),[])
        finally:engine.close()


if __name__=="__main__":
    unittest.main()
