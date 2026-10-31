from __future__ import annotations
import csv
import io
from pathlib import Path
from zipfile import ZipFile, BadZipFile
import xml.etree.ElementTree as ET
from PIL import Image
from .store import uid


MAX_BYTES = 12 * 1024 * 1024
MAX_TEXT = 180000


def checked_zip(data):
    try:
        z = ZipFile(io.BytesIO(data))
        infos = z.infolist()
        if len(infos) > 3000 or sum(x.file_size for x in infos) > 60 * 1024 * 1024:
            raise ValueError("Archivo expandido demasiado grande")
        if any(x.file_size > 15 * 1024 * 1024 for x in infos):
            raise ValueError("Parte interna demasiado grande")
        if any("vbaProject" in x.filename for x in infos):
            raise ValueError("No se aceptan macros")
        return z
    except BadZipFile:
        raise ValueError("Archivo Office inválido") from None


def extract(data: bytes, filename: str) -> list[tuple[str, str]]:
    if not data or len(data) > MAX_BYTES:
        raise ValueError("El archivo debe pesar entre 1 byte y 12 MB")
    ext = Path(filename).suffix.lower()
    parts = []
    if ext in (".txt", ".md", ".csv"):
        parts = [("texto", data.decode("utf-8-sig"))]
    elif ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        if len(reader.pages) > 150:
            raise ValueError("Límite de 150 páginas por adjunto")
        parts = [(f"página {i+1}", page.extract_text() or "") for i, page in enumerate(reader.pages)]
    elif ext in (".docx", ".pptx", ".xlsx"):
        with checked_zip(data) as z:
            if ext == ".xlsx":
                ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                strings = []
                if "xl/sharedStrings.xml" in z.namelist():
                    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
                    strings = ["".join(x.itertext()) for x in root]
                for name in sorted(z.namelist()):
                    if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
                        root = ET.fromstring(z.read(name))
                        lines = []
                        for row in root.findall(".//m:row", ns):
                            values = []
                            for c in row.findall("m:c", ns):
                                v = c.find("m:v", ns)
                                text = v.text if v is not None and v.text else ""
                                if c.attrib.get("t") == "s" and text:
                                    text = strings[int(text)]
                                elif c.attrib.get("t") == "inlineStr":
                                    text = "".join(c.find("m:is", ns).itertext())
                                elif c.find("m:f", ns) is not None and not text:
                                    text = "[fórmula sin valor guardado]"
                                values.append(c.attrib.get("r", "") + ": " + text)
                            lines.append(" / ".join(values))
                        parts.append((name, "\n".join(lines)))
            else:
                names = (["word/document.xml"] if ext == ".docx" else
                         sorted(n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")))
                for name in names:
                    root = ET.fromstring(z.read(name))
                    texts = [n.text for n in root.iter() if n.tag.endswith("}t") and n.text]
                    parts.append((name, "\n".join(texts)))
    else:
        raise ValueError("Formatos de contexto: TXT, MD, CSV, PDF, DOCX, PPTX, XLSX")
    if sum(len(t) for _, t in parts) > MAX_TEXT:
        raise ValueError("El texto excede 180000 caracteres. Divide el archivo.")
    if not any(t.strip() for _, t in parts):
        raise ValueError("No se encontró texto. Los PDF escaneados requieren OCR externo.")
    return parts


def ingest(store, p, cid, filename, data, scope="conversation"):
    store.conversation(p, cid)
    # Extraer completamente antes de insertar para evitar ingestas parciales por error de parseo.
    parts = extract(data, filename)
    count = 0
    title = Path(filename).name[:180]
    for locator, text in parts:
        for start in range(0, len(text), 3000):
            chunk = text[start:start+3400]
            if chunk.strip():
                store.add_chunk(p, scope, cid, title, f"{title}, {locator}, carácter {start}", chunk)
                count += 1
    return {"chunks": count, "title": title, "scope": scope}


def save_logo(store, p, cid, data):
    store.conversation(p, cid)
    if not data or len(data) > 4 * 1024 * 1024:
        raise ValueError("Logo de máximo 4 MB")
    with Image.open(io.BytesIO(data)) as img:
        if img.format not in ("PNG", "JPEG") or img.width * img.height > 12000000:
            raise ValueError("Usa un PNG o JPEG de hasta 12 megapíxeles")
        image = img.convert("RGBA")
        image.thumbnail((1600, 1600))
        asset_id = uid()
        directory = store.root / "assets"
        directory.mkdir(exist_ok=True)
        path = directory / (asset_id + ".png")
        image.save(path)
    store.add_asset(p, cid, path, "image/png", asset_id)
    colors = image.convert("RGB").resize((80, 80)).quantize(colors=8).convert("RGB").getcolors(6400)
    candidates = []
    for count, rgb in sorted(colors or [], reverse=True):
        if max(rgb) - min(rgb) > 25 and 35 < sum(rgb)/3 < 220:
            candidates.append("#%02X%02X%02X" % rgb)
    return {"logo_id": asset_id, "suggested_primary": candidates[0] if candidates else "#142D4E",
            "suggested_accent": candidates[1] if len(candidates) > 1 else "#007F78"}
