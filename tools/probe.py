# -*- coding: utf-8 -*-
"""Diagnose: Welche OCR-Schnittstellen sind wie aufzurufen?"""
import inspect
import ssl
import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent / "probe.txt"
lines = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    lines.append(s)


log("Python:", sys.version.split()[0])

# --- Zertifikate ---
try:
    import certifi
    log("certifi:", certifi.where())
except ImportError:
    log("certifi: FEHLT")
try:
    ctx = ssl.create_default_context()
    with urllib.request.urlopen("https://pypi.org", timeout=10) as r:
        log("HTTPS ohne Zusatz: OK", r.status)
except Exception as e:
    log("HTTPS ohne Zusatz: FEHLER", type(e).__name__, str(e)[:80])

# --- Surya ---
try:
    from surya.recognition import RecognitionPredictor
    log("\nsurya: installiert")
    try:
        import surya
        log("surya-Version:", getattr(surya, "__version__", "?"))
    except Exception:
        pass
    sig = inspect.signature(RecognitionPredictor.__call__)
    log("RecognitionPredictor.__call__", sig)
    from surya.detection import DetectionPredictor
    log("DetectionPredictor.__call__",
        inspect.signature(DetectionPredictor.__call__))
except ImportError as e:
    log("\nsurya: NICHT installiert", e)
except Exception as e:
    log("\nsurya: Fehler", type(e).__name__, str(e)[:120])

# --- EasyOCR ---
try:
    import easyocr
    log("\neasyocr: installiert", getattr(easyocr, "__version__", "?"))
except ImportError:
    log("\neasyocr: NICHT installiert")

# --- RapidOCR ---
try:
    from rapidocr_onnxruntime import RapidOCR
    log("\nrapidocr: installiert")
    log("RapidOCR.__init__", inspect.signature(RapidOCR.__init__))
except ImportError:
    log("\nrapidocr: NICHT installiert")

# --- Modell-Quellen für arabisches PaddleOCR prüfen ---
log("\n--- Download-Quellen testen ---")
urls = [
    "https://paddleocr.bj.bcebos.com/PP-OCRv3/multilingual/arabic_PP-OCRv3_rec_infer.tar",
    "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/arabic_PP-OCRv3_mobile_rec_infer.tar",
    "https://huggingface.co/SWHL/RapidOCR/resolve/main/onnx/PP-OCRv3/rec/arabic_PP-OCRv3_rec_infer.onnx",
    "https://huggingface.co/OleehyO/RapidOCR-onnx/resolve/main/arabic_PP-OCRv3_rec_infer.onnx",
]
for u in urls:
    try:
        req = urllib.request.Request(u, method="HEAD")
        with urllib.request.urlopen(req, timeout=15) as r:
            size = r.headers.get("Content-Length", "?")
            log(f"OK   {r.status}  {int(size)/1e6:.1f} MB  {u[:78]}")
    except Exception as e:
        log(f"FAIL {type(e).__name__}: {str(e)[:40]}  {u[:78]}")

OUT.write_text("\n".join(lines), encoding="utf-8")
print("\n->", OUT)
