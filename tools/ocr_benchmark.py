# -*- coding: utf-8 -*-
"""Misst OCR-Qualität für Arabisch – Kandidaten für die Windows-Version.

Referenz: Apple Vision (auf diesem Buch nachweislich ~fehlerfrei).
Gemessen wird die Zeichen-Ähnlichkeit jedes Erkenners zur Referenz
(0–100 %) sowie die Zeit pro Seite.

Kandidaten (alle laufen auch auf Windows):
  * Tesseract (Standard)
  * Tesseract (tessdata_best + Vorverarbeitung)
  * Surya OCR (Transformer, gilt als stark bei Arabisch)
  * PaddleOCR arabisch (ONNX)

Ausgabe: tools/ocr_benchmark.html + Konsolenzusammenfassung
"""
from __future__ import annotations

import difflib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.request
from pathlib import Path

import fitz  # PyMuPDF

PDF = Path.home() / "Downloads" / \
    "شرح-الشيخ-جيل-لكتاب-عمدة-الراغب-النسخة-الرابعة.pdf"
PAGES = [21, 288, 124]
OUT = Path(__file__).parent / "ocr_benchmark.html"
TESSDATA = Path(__file__).parent / "tessdata_best"


def render(page_no: int, dpi: int) -> bytes:
    with fitz.open(PDF) as doc:
        return doc[page_no - 1].get_pixmap(dpi=dpi).tobytes("png")


def norm(t: str) -> str:
    """Für den Vergleich: Diakritika raus, Leerraum vereinheitlichen.
    (Wir messen die Buchstaben-Treue, nicht die Vokalzeichen.)"""
    t = unicodedata.normalize("NFKC", t)
    t = re.sub(r"[ً-ْٰـ]", "", t)   # Tashkil/Tatweel
    t = re.sub(r"[أإآٱ]", "ا", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def similarity(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    # autojunk=False ist zwingend: sonst gelten häufige Buchstaben als
    # "Müll" und das Ergebnis wird unbrauchbar.
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() * 100


def _words(t: str) -> list[str]:
    return [w for w in re.findall(r"[ء-ي]+", norm(t)) if len(w) >= 3]


def order_score(ref: str, cand: str) -> float:
    """Stimmt die Reihenfolge der Wörter? (wichtig für Wortgruppen-Suche
    und für die Lesbarkeit im Leser)"""
    a, b = _words(ref), _words(cand)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() * 100


def findable(ref: str, cand: str) -> float:
    """DAS entscheidende Maß: Anteil der Referenzwörter, die im Kandidaten
    so korrekt stehen, dass unsere Wurzelsuche sie findet."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
    from echo_engine.normalize import normalize as _n
    from echo_engine.normalize import stem as _s
    rs = [_s(_n(w)) for w in _words(ref)]
    cs = {_s(_n(w)) for w in _words(cand)}
    if not rs:
        return 0.0
    return sum(1 for x in rs if x in cs) / len(rs) * 100


def tashkil_ratio(t: str) -> float:
    """Anteil Vokalzeichen – zeigt, ob der Erkenner Tashkil mitliest."""
    letters = len(re.findall(r"[ء-ي]", t))
    marks = len(re.findall(r"[ً-ْ]", t))
    return (marks / letters * 100) if letters else 0.0


# ---------------- Referenz: Apple Vision ----------------
def ocr_vision(png: bytes) -> str:
    import Vision
    from Foundation import NSData
    data = NSData.dataWithBytes_length_(png, len(png))
    h = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, None)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(0)
    req.setUsesLanguageCorrection_(True)
    try:
        req.setRecognitionLanguages_(["ar-SA"])
    except Exception:
        pass
    h.performRequests_error_([req], None)
    obs = list(req.results() or [])
    obs.sort(key=lambda o: -o.boundingBox().origin.y)
    out = []
    for o in obs:
        c = o.topCandidates_(1)
        if c and len(c):
            out.append(str(c[0].string()))
    return "\n".join(out)


# ---------------- Tesseract ----------------
def _tess(png: bytes, tessdata: Path | None, psm: str = "6",
          preprocess: bool = False) -> str:
    exe = shutil.which("tesseract")
    if not exe:
        return "(Tesseract fehlt)"
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "p.png"
        p.write_bytes(png)
        if preprocess:
            try:
                from PIL import Image, ImageOps
                img = Image.open(p).convert("L")
                img = ImageOps.autocontrast(img)
                # leichte Binarisierung hilft Tesseract oft deutlich
                img = img.point(lambda x: 0 if x < 165 else 255, "1")
                img.save(p)
            except Exception:
                pass
        env = dict(os.environ)
        if tessdata and tessdata.exists():
            env["TESSDATA_PREFIX"] = str(tessdata)
        r = subprocess.run([exe, str(p), "stdout", "-l", "ara",
                            "--oem", "1", "--psm", psm],
                           capture_output=True, text=True, timeout=300,
                           env=env)
        return r.stdout.strip() or f"(Fehler: {r.stderr[:150]})"


def ocr_tess_std(png: bytes) -> str:
    return _tess(png, None)


def ocr_tess_best(png: bytes) -> str:
    return _tess(png, TESSDATA, preprocess=True)


# ---------------- Surya ----------------
_surya = None


def ocr_surya(png: bytes) -> str:
    global _surya
    import io

    from PIL import Image
    try:
        from surya.detection import DetectionPredictor
        from surya.recognition import RecognitionPredictor
    except ImportError:
        return "(surya-ocr nicht installiert)"
    if _surya is None:
        try:
            # Neuere Surya-Versionen brauchen einen FoundationPredictor
            from surya.foundation import FoundationPredictor
            _surya = (RecognitionPredictor(FoundationPredictor()),
                      DetectionPredictor())
        except Exception:
            _surya = (RecognitionPredictor(), DetectionPredictor())
    rec, det = _surya
    img = Image.open(io.BytesIO(png)).convert("RGB")
    preds = None
    errors = []
    # Schnittstelle je nach Version – der Reihe nach durchprobieren
    for attempt in (
        lambda: rec([img]),                       # aktuelle API
        lambda: rec([img], det_predictor=det),    # 0.13/0.14
        lambda: rec([img], [["ar"]], det),        # alt
    ):
        try:
            preds = attempt()
            break
        except TypeError as e:
            errors.append(str(e)[:70])
    if preds is None:
        return f"(Surya-Aufruf fehlgeschlagen: {errors})"
    page = preds[0]
    lines = getattr(page, "text_lines", None)
    if lines is None:
        return f"(unbekanntes Surya-Ergebnis: {type(page)})"
    return "\n".join(l.text for l in lines)


# ---------------- EasyOCR ----------------
_easy = None


def assemble_rtl(res) -> str:
    """Setzt erkannte Textkästchen zu Zeilen zusammen – arabisch korrekt:
    Zeilen von oben nach unten, innerhalb der Zeile von RECHTS nach LINKS."""
    items = []
    for box, text, *_ in res:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        items.append({"x0": min(xs), "x1": max(xs),
                      "y0": min(ys), "y1": max(ys), "t": text})
    items.sort(key=lambda i: i["y0"])
    lines: list[dict] = []
    for it in items:
        placed = False
        for ln in lines:
            ov = min(ln["y1"], it["y1"]) - max(ln["y0"], it["y0"])
            h = min(ln["y1"] - ln["y0"], it["y1"] - it["y0"])
            if h > 0 and ov / h > 0.5:      # gleiche Zeile
                ln["items"].append(it)
                ln["y0"] = min(ln["y0"], it["y0"])
                ln["y1"] = max(ln["y1"], it["y1"])
                placed = True
                break
        if not placed:
            lines.append({"y0": it["y0"], "y1": it["y1"], "items": [it]})
    out = []
    for ln in sorted(lines, key=lambda l: l["y0"]):
        parts = sorted(ln["items"], key=lambda i: -i["x1"])  # rechts → links
        out.append(" ".join(p["t"] for p in parts))
    return "\n".join(out)


def ocr_easy(png: bytes) -> str:
    global _easy
    import io

    import numpy as np
    from PIL import Image
    try:
        import easyocr
    except ImportError:
        return "(easyocr nicht installiert)"
    if _easy is None:
        _easy = easyocr.Reader(["ar"], gpu=False, verbose=False)
    img = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
    res = _easy.readtext(img, detail=1, paragraph=False)
    return assemble_rtl(res)


# ---------------- PaddleOCR arabisch (ONNX) ----------------
_paddle = None
_PADDLE_FILES = {
    "rec": ("https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/master/"
            "onnx/PP-OCRv4/rec/arabic_PP-OCRv4_rec_infer.onnx",
            "arabic_rec.onnx"),
    "dict": ("https://raw.githubusercontent.com/RapidAI/RapidOCR/main/"
             "python/rapidocr_onnxruntime/models/arabic_dict.txt",
             "arabic_dict.txt"),
}


def ocr_paddle_ar(png: bytes) -> str:
    """Arabisches PaddleOCR-Modell über ONNX (Modelle legt das
    Begleitskript nach tools/models_ar/)."""
    global _paddle
    import io

    import numpy as np
    from PIL import Image
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return "(rapidocr nicht installiert)"
    d = Path(__file__).parent / "models_ar"
    rec, keys = d / "arabic_rec.onnx", d / "arabic_dict.txt"
    if not rec.exists() or not keys.exists():
        return "(arabisches Modell nicht vorhanden – Download fehlgeschlagen)"
    if _paddle is None:
        _paddle = RapidOCR(rec_model_path=str(rec), rec_keys_path=str(keys))
    img = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
    res, _ = _paddle(img)
    if not res:
        return "(keine Erkennung)"
    return "\n".join(line[1] for line in res)


def main():
    if not PDF.exists():
        print("PDF nicht gefunden:", PDF)
        return

    engines = [
        ("Tesseract Standard", ocr_tess_std),
        ("EasyOCR 200dpi", ocr_easy),
        ("EasyOCR 300dpi", ocr_easy),
    ]

    results = {name: [] for name, _ in engines}
    rows = []

    for page_no in PAGES:
        png300 = render(page_no, 300)
        png200 = render(page_no, 200)
        print(f"\n=== Seite {page_no} ===")
        t0 = time.time()
        ref = ocr_vision(png200)
        print(f"Referenz Apple Vision: {len(ref)} Zeichen, "
              f"{time.time()-t0:.1f}s, Tashkil {tashkil_ratio(ref):.0f}%")
        cells = [("Apple Vision (Referenz)", ref, time.time()-t0,
                  100.0, 100.0, 100.0)]

        for name, fn in engines:
            png = png300 if ("Tesseract" in name or "300dpi" in name) \
                else png200
            t0 = time.time()
            try:
                text = fn(png)
            except Exception as e:
                import traceback
                traceback.print_exc()
                text = f"(FEHLER: {e})"
            dt = time.time() - t0
            if text.strip().startswith("("):
                print(f"{name:28s} – {text.strip()[:70]}")
                cells.append((name, text, dt, 0.0, 0.0, 0.0))
                continue
            sim = similarity(ref, text)
            fnd = findable(ref, text)
            ordr = order_score(ref, text)
            results[name].append((sim, fnd, ordr, dt))
            print(f"{name:28s} AUFFINDBAR {fnd:5.1f}% · Reihenfolge {ordr:5.1f}%"
                  f" · Zeichen {sim:5.1f}% · {dt:5.1f}s · "
                  f"Tashkil {tashkil_ratio(text):3.0f}%")
            cells.append((name, text, dt, sim, fnd, ordr))
        rows.append((page_no, cells))

    print("\n" + "=" * 82)
    print(f"{'ENGINE':30s}{'AUFFINDBAR':>12s}{'Reihenfolge':>14s}"
          f"{'Zeichen':>10s}{'Sek./Seite':>13s}")
    print("=" * 82)
    for name, _ in engines:
        vals = results[name]
        if not vals:
            print(f"{name:30s}{'– fehlgeschlagen':>26s}")
            continue
        z = sum(v[0] for v in vals) / len(vals)
        f = sum(v[1] for v in vals) / len(vals)
        o = sum(v[2] for v in vals) / len(vals)
        s = sum(v[3] for v in vals) / len(vals)
        print(f"{name:30s}{f:11.1f}%{o:13.1f}%{z:9.1f}%{s:12.1f}s")
    print("\nAUFFINDBAR  = Anteil der Wörter, die unsere Suche wiederfindet")
    print("Reihenfolge = stimmt die Wortabfolge (für Wortgruppen & Lesbarkeit)")

    html = ["""<!DOCTYPE html><html lang="ar" dir="rtl"><head>
<meta charset="utf-8"><title>OCR-Benchmark</title><style>
body{font-family:"Noto Naskh Arabic","Amiri",Tahoma,sans-serif;
background:#f7f5f0;color:#1f2a24;margin:24px;}
h2{color:#0f6b4f;border-bottom:2px solid #e4e0d6;padding-bottom:6px;}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;
margin-bottom:34px;}
.card{background:#fff;border:1px solid #e4e0d6;border-radius:12px;padding:12px;}
.card h3{margin:0 0 4px;font-size:14px;color:#0f6b4f;}
.meta{font-size:12px;color:#6b7a72;margin-bottom:8px;}
.sim{font-weight:800;}
pre{white-space:pre-wrap;font-family:inherit;font-size:14px;
line-height:1.8;margin:0;max-height:460px;overflow:auto;}
</style></head><body>
<h1 style="color:#0f6b4f">OCR-Benchmark · Arabisch</h1>"""]
    for page_no, cells in rows:
        html.append(f"<h2>Seite {page_no}</h2><div class='grid'>")
        for name, text, dt, sim, fnd, ordr in cells:
            color = "#0f6b4f" if fnd >= 95 else \
                    "#b8860b" if fnd >= 85 else "#b3372f"
            html.append(
                f"<div class='card'><h3>{name}</h3>"
                f"<div class='meta'><span class='sim' style='color:{color}'>"
                f"{fnd:.0f}% auffindbar</span> · Reihenfolge {ordr:.0f}% · "
                f"Zeichen {sim:.0f}% · "
                f"{dt:.1f}s · Tashkil {tashkil_ratio(text):.0f}%</div>"
                f"<pre>{text.replace('&','&amp;').replace('<','&lt;')}</pre>"
                "</div>")
        html.append("</div>")
    html.append("</body></html>")
    OUT.write_text("\n".join(html), encoding="utf-8")
    print("\nBericht:", OUT)


if __name__ == "__main__":
    main()
