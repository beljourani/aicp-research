# -*- coding: utf-8 -*-
"""Vergleicht OCR-Engines an denselben Seiten eines arabischen Buchs.

Verglichen werden:
  1. Apple Vision   (macOS eingebaut – heutige Mac-Lösung)
  2. Tesseract      (heutige Windows-Lösung, falls installiert)
  3. RapidOCR/ONNX  (Kandidat: identisch auf Mac UND Windows)

Ausgabe: tools/ocr_vergleich.html (nebeneinander lesbar)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

import fitz  # PyMuPDF

PDF = Path.home() / "Downloads" / \
    "شرح-الشيخ-جيل-لكتاب-عمدة-الراغب-النسخة-الرابعة.pdf"
PAGES = [21, 288, 124]     # gemischte Seiten (Fließtext, Fußnoten, Tabelle)
OUT = Path(__file__).parent / "ocr_vergleich.html"


def render(page_no: int, dpi: int = 200) -> bytes:
    with fitz.open(PDF) as doc:
        return doc[page_no - 1].get_pixmap(dpi=dpi).tobytes("png")


# ---------- 1. Apple Vision ----------
def ocr_vision(png: bytes) -> str:
    import Vision
    from Foundation import NSData
    data = NSData.dataWithBytes_length_(png, len(png))
    handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(
        data, None)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(0)
    req.setUsesLanguageCorrection_(True)
    try:
        req.setRecognitionLanguages_(["ar-SA"])
    except Exception:
        pass
    handler.performRequests_error_([req], None)
    obs = list(req.results() or [])
    obs.sort(key=lambda o: -o.boundingBox().origin.y)
    out = []
    for o in obs:
        c = o.topCandidates_(1)
        if c and len(c):
            out.append(str(c[0].string()))
    return "\n".join(out)


# ---------- 2. Tesseract ----------
def ocr_tesseract(png: bytes) -> str:
    import shutil
    import subprocess
    import tempfile
    exe = shutil.which("tesseract")
    if not exe:
        return "(Tesseract nicht installiert)"
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(png)
        path = f.name
    r = subprocess.run([exe, path, "stdout", "-l", "ara"],
                       capture_output=True, text=True, timeout=180)
    return r.stdout.strip() or f"(Fehler: {r.stderr[:200]})"


# ---------- 3. RapidOCR (ONNX) ----------
_rapid = None


def ocr_rapid(png: bytes) -> str:
    global _rapid
    import numpy as np
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return "(rapidocr-onnxruntime nicht installiert)"
    if _rapid is None:
        _rapid = RapidOCR()
    import io

    from PIL import Image
    img = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
    res, _ = _rapid(img)
    if not res:
        return "(keine Erkennung)"
    return "\n".join(line[1] for line in res)


def main():
    if not PDF.exists():
        print("PDF nicht gefunden:", PDF)
        return
    engines = [("Apple Vision (Mac heute)", ocr_vision),
               ("Tesseract (Windows heute)", ocr_tesseract),
               ("RapidOCR/ONNX (Kandidat)", ocr_rapid)]

    rows = []
    for page_no in PAGES:
        png = render(page_no)
        cells = []
        for name, fn in engines:
            t0 = time.time()
            try:
                text = fn(png)
            except Exception as e:
                import traceback
                traceback.print_exc()
                text = f"(FEHLER: {e})"
            dt = time.time() - t0
            print(f"Seite {page_no} · {name}: {len(text)} Zeichen, {dt:.1f}s")
            cells.append((name, text, dt))
        rows.append((page_no, cells))

    html = ["""<!DOCTYPE html><html lang="ar" dir="rtl"><head>
<meta charset="utf-8"><title>OCR-Vergleich</title><style>
body{font-family:"Noto Naskh Arabic","Amiri",Tahoma,sans-serif;
background:#f7f5f0;color:#1f2a24;margin:24px;}
h2{color:#0f6b4f;border-bottom:2px solid #e4e0d6;padding-bottom:6px;}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;
margin-bottom:34px;}
.card{background:#fff;border:1px solid #e4e0d6;border-radius:12px;
padding:14px;}
.card h3{margin:0 0 4px;font-size:15px;color:#0f6b4f;}
.meta{font-size:12px;color:#6b7a72;margin-bottom:10px;}
pre{white-space:pre-wrap;font-family:inherit;font-size:15px;
line-height:1.9;margin:0;max-height:520px;overflow:auto;}
</style></head><body>
<h1 style="color:#0f6b4f">OCR-Vergleich · مقارنة التعرّف الضوئي</h1>"""]
    for page_no, cells in rows:
        html.append(f"<h2>Seite {page_no} · صفحة</h2><div class='grid'>")
        for name, text, dt in cells:
            html.append(
                f"<div class='card'><h3>{name}</h3>"
                f"<div class='meta'>{len(text)} Zeichen · {dt:.1f}s</div>"
                f"<pre>{text.replace('&','&amp;').replace('<','&lt;')}</pre>"
                f"</div>")
        html.append("</div>")
    html.append("</body></html>")
    OUT.write_text("\n".join(html), encoding="utf-8")
    print("\nErgebnis:", OUT)


if __name__ == "__main__":
    main()
