# -*- coding: utf-8 -*-
"""Extraktion: liefert für jede Datei eine Liste (seitenzahl, text).

PDF   : seitenweise über PyMuPDF; erkennt Scans (kein Textlayer -> needs_ocr)
DOCX  : bevorzugt Konvertierung nach PDF via LibreOffice (echte Seitenzahlen);
        Fallback: reiner Text ohne verlässliche Seiten (wird markiert)
TXT   : eine künstliche "Seite" pro ~2000 Zeichen
OCR   : Tesseract (ara), falls installiert – für eingescannte PDFs
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

# Leerzeichen vor arabischen Vokalzeichen (kaputte PDF-Textschicht)
_SPACE_BEFORE_MARK = re.compile(r"[ \t]+(?=[ً-ٰ])")

# Obergrenze für eine plausible Buchseite (gemessen: echte Seiten liegen
# bei 1000–4000 Zeichen). Darüber sind Words Umbrüche unvollständig.
MAX_CHARS_PER_PAGE = 5000


def _clean_pdf_text(text: str) -> str:
    """Repariert typische Artefakte arabischer PDF-Textschichten.

    - NFKC: arabische Präsentationsformen (Ligaturen) -> normale Buchstaben
    - Leerzeichen, die zwischen Buchstabe und Vokalzeichen geraten sind
    """
    text = unicodedata.normalize("NFKC", text)
    text = _SPACE_BEFORE_MARK.sub("", text)
    return text


@dataclass
class ExtractResult:
    pages: list[tuple[int, str]] = field(default_factory=list)
    needs_ocr: bool = False
    real_page_numbers: bool = True
    # Wie verlässlich sind die Seitenzahlen?
    #   "exakt"    – von Words eigener Engine (Word installiert oder Cloud)
    #   "ungefähr" – von LibreOffice gerendert (kann leicht abweichen)
    #   "sicher"   – direkt aus einem PDF (die gedruckten Seiten)
    reliability: str = "sicher"
    engine: str = ""
    warnings: list[str] = field(default_factory=list)


def extract(path: str | Path, force_ocr: bool = False,
            progress=None) -> ExtractResult:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(p, force_ocr=force_ocr)
    if suffix == ".docx":
        return extract_docx(p, progress=progress)
    if suffix == ".txt":
        return extract_txt(p)
    raise ValueError(f"Nicht unterstützter Dateityp: {suffix}")


def _text_layer_broken(pages: list[tuple[int, str]]) -> bool:
    """Erkennt kaputte arabische Textschichten (visuelle/verdrehte
    Reihenfolge) über mehrere unabhängige Indizien:

    1. يف häufiger als في (häufigstes Wort rückwärts)
    2. Wörter, die mit ة (Ta Marbuta) BEGINNEN – im echten Arabisch
       unmöglich, in verdrehtem Text sehr häufig
    3. Mehr Wörter, die auf لا enden, als Wörter, die mit ال beginnen
       (rückwärts gedrehter Artikel)
    """
    full = " ".join(t for _, t in pages)
    tokens = re.findall(r"[ء-ي]+", full)
    if len(tokens) < 30:
        return False
    fi = sum(1 for t in tokens if t == "في")
    fi_rev = sum(1 for t in tokens if t == "يف")
    ta_start = sum(1 for t in tokens if t.startswith("ة"))
    al_start = sum(1 for t in tokens if t.startswith("ال"))
    la_end = sum(1 for t in tokens if t.endswith("لا") and len(t) > 3)

    indizien = 0
    if fi_rev > max(3, fi):
        indizien += 1
    if ta_start > max(4, len(tokens) * 0.003):
        indizien += 1
    if la_end > max(4, al_start):
        indizien += 1
    return indizien >= 1


def extract_pdf(path: Path, force_ocr: bool = False) -> ExtractResult:
    res = ExtractResult()
    res.reliability = "sicher"      # PDF = feste, gedruckte Seiten
    res.engine = "PDF"
    with fitz.open(path) as doc:
        empty_pages = 0
        for i, page in enumerate(doc, start=1):
            text = _clean_pdf_text(page.get_text("text", sort=True).strip())
            if not text:
                empty_pages += 1
            res.pages.append((i, text))
        is_scan = len(doc) > 0 and empty_pages / len(doc) > 0.5
    broken = _text_layer_broken(res.pages)
    if broken:
        res.warnings.append(
            "Kaputte Textschicht erkannt (falsche Zeichenreihenfolge).")

    if force_ocr or is_scan or broken:
        res.needs_ocr = True
        ocr_pages = _try_ocr(path)
        if ocr_pages is not None:
            res.pages = ocr_pages
            res.needs_ocr = False
            res.warnings.append("Text per OCR (Texterkennung) erfasst.")
        else:
            res.warnings.append(
                "OCR nicht verfügbar (weder Apple Vision noch Tesseract).")
    return res


def _find_soffice(progress=None) -> str | None:
    """Eingebaute/selbstgeladene Komponente bevorzugen (siehe components.py)."""
    from .components import find_soffice
    return find_soffice(auto_install=True, progress=progress)


def _word_installed() -> bool:
    if sys.platform == "darwin":
        return Path("/Applications/Microsoft Word.app").exists()
    if os.name == "nt":
        try:
            import winreg
            for key in (r"Word.Application\CLSID",):
                winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, key).Close()
            return True
        except Exception:
            return False
    return False


def convert_with_word(path: Path, out_dir: Path) -> Path | None:
    """Wandelt eine Word-Datei mit WORDS EIGENER Engine nach PDF – dadurch
    exakt dieselben Seitenumbrüche wie in Word. Nur wenn Word installiert ist.

    macOS: über AppleScript (Word ist sandboxed → in den eigenen Container
    exportieren, dann herauskopieren).
    Windows: über COM-Automation, komplett unsichtbar (Visible=False).
    """
    out = out_dir / (path.stem + ".pdf")

    if os.name == "nt":
        try:
            import win32com.client as win32
            word = win32.DispatchEx("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0
            try:
                doc = word.Documents.Open(str(path), ReadOnly=True)
                # 17 = wdFormatPDF
                doc.SaveAs(str(out), FileFormat=17)
                doc.Close(False)
            finally:
                word.Quit()
            return out if out.exists() else None
        except Exception:
            import traceback
            traceback.print_exc()
            return None

    if sys.platform == "darwin":
        # Word darf nur in seinen Container schreiben.
        container = (Path.home() / "Library" / "Containers"
                     / "com.microsoft.Word" / "Data" / "echoarchive-tmp")
        try:
            container.mkdir(parents=True, exist_ok=True)
        except Exception:
            return None
        tmp_pdf = container / (path.stem + ".pdf")
        tmp_pdf.unlink(missing_ok=True)
        script = (
            'with timeout of 1200 seconds\n'
            'tell application "Microsoft Word"\n'
            '  set wasRunning to running\n'
            f'  open POSIX file "{path}"\n'
            '  set theDoc to active document\n'
            f'  save as theDoc file name "{tmp_pdf}" '
            'file format format PDF\n'
            '  close theDoc saving no\n'
            'end tell\n'
            'end timeout\n')
        try:
            r = subprocess.run(["osascript", "-e", script],
                               capture_output=True, text=True, timeout=1260)
            if tmp_pdf.exists():
                import shutil as _sh
                _sh.copy(tmp_pdf, out)
                tmp_pdf.unlink(missing_ok=True)
                return out
            print("Word-Wandlung:", r.stderr.strip()[:150], flush=True)
        except Exception:
            import traceback
            traceback.print_exc()
        return None

    return None


def convert_docx_to_pdf(path: Path, out_dir: Path, progress=None) -> Path | None:
    """Wandelt eine Word-Datei in ein PDF – so wie Word es täte.

    Der Schlüssel: Der Konverter bekommt (a) die von der App mitgelieferten
    Schriften UND (b) die auf dem Rechner gefundenen Original-Schriften
    (auch aus Microsoft Offices Cloud-Font-Cache). Damit rendert er das
    Dokument mit derselben Schrift wie Word und trifft dessen Seitenumbrüche.

    Es wird NIE ein Fremdprogramm (Microsoft Word) benutzt.
    """
    soffice = _find_soffice(progress=progress)
    if not soffice:
        return None
    from .components import install_fonts_into_converter
    install_fonts_into_converter(soffice, progress)

    # Eigenes, temporäres Konverter-Profil: verhindert, dass sich der
    # Vorgang an eine bereits laufende (sichtbare) LibreOffice-Instanz
    # hängt und ein Fenster öffnet.
    # Eigenes Profil in einem festen Ordner (nicht temporär): verhindert,
    # dass sich der Vorgang an eine laufende, sichtbare LibreOffice-Instanz
    # hängt oder ein Fenster öffnet. Bewusst der normale 'soffice'-Starter
    # (NICHT soffice.bin) und nur die Standard-Headless-Flags – alles andere
    # bringt LibreOffice auf dem Mac zum Absturz.
    from .components import components_dir
    prof = components_dir() / "lo-profile"
    prof.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [soffice, f"-env:UserInstallation={prof.as_uri()}",
         "--headless", "--convert-to", "pdf",
         "--outdir", str(out_dir), str(path)],
        capture_output=True, timeout=1200)
    pdf = out_dir / (path.stem + ".pdf")
    if pdf.exists():
        return pdf
    print("Konvertierung fehlgeschlagen:",
          r.stderr.decode("utf-8", "replace")[:200], flush=True)
    return None


def extract_docx(path: Path, progress=None) -> ExtractResult:
    """Word-Dateien – nimmt immer die genaueste verfügbare Engine:

    1. Word installiert  -> Words eigene Engine (exakte Seitenzahlen)
    2. Cloud eingerichtet -> Microsofts Word-Engine online (exakt)
    3. sonst             -> LibreOffice (läuft überall, leichte Abweichung)
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmpd = Path(tmp)

        # Stufe 1: lokales Word (am genauesten, offline, kein Konto)
        if _word_installed():
            try:
                if progress:
                    progress("wird mit Word umgewandelt …")
                pdf = convert_with_word(path, tmpd)
                if pdf is not None:
                    res = extract_pdf(pdf)
                    res.reliability = "exakt"
                    res.engine = "Word"
                    res.warnings.append(
                        "Mit Words eigener Engine gewandelt – "
                        "Seitenzahlen exakt wie in Word.")
                    return res
            except Exception:
                import traceback
                traceback.print_exc()

        # Stufe 2: Microsoft-Cloud (falls eingerichtet)
        try:
            from .cloud_convert import convert_via_cloud, cloud_ready
            if cloud_ready():
                if progress:
                    progress("wird online (Word-Engine) umgewandelt …")
                pdf = convert_via_cloud(path, tmpd)
                if pdf is not None:
                    res = extract_pdf(pdf)
                    res.reliability = "exakt"
                    res.engine = "Word Cloud"
                    res.warnings.append(
                        "Über Microsofts Word-Engine (online) gewandelt – "
                        "Seitenzahlen exakt wie in Word.")
                    return res
        except Exception:
            pass

        # Stufe 3: LibreOffice (immer verfügbar, leichte Abweichung möglich)
        try:
            pdf = convert_docx_to_pdf(path, tmpd, progress)
            if pdf is not None:
                res = extract_pdf(pdf)
                res.reliability = "ungefähr"
                res.engine = "LibreOffice"
                res.warnings.append(
                    "Mit LibreOffice gewandelt – Seitenzahlen können bei "
                    "langen Dokumenten leicht abweichen.")
                return res
        except Exception:
            import traceback
            traceback.print_exc()

    # Allerletzte Notlösung: reiner Text, Seiten nur geschätzt.
    import docx  # python-docx
    d = docx.Document(str(path))
    full = "\n".join(par.text for par in d.paragraphs)
    res = _paginate_plain(full)
    res.real_page_numbers = False
    res.reliability = "ungefähr"
    res.warnings.append(
        "Kein Konverter verfügbar – Text übernommen, Seiten nur geschätzt.")
    return res


def extract_txt(path: Path) -> ExtractResult:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    res = _paginate_plain(text)
    res.real_page_numbers = False
    return res


def _paginate_plain(text: str, chars_per_page: int = 2000) -> ExtractResult:
    res = ExtractResult()
    pos, page_no = 0, 1
    while pos < len(text):
        res.pages.append((page_no, text[pos:pos + chars_per_page]))
        pos += chars_per_page
        page_no += 1
    if not res.pages:
        res.pages = [(1, "")]
    return res


def _tesseract_cmd() -> str | None:
    """Findet Tesseract: zuerst die mitgelieferte Kopie (Windows-Installer),
    dann eine systemweite Installation."""
    import sys
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", ""))
        cand = base / "tesseract" / ("tesseract.exe" if os.name == "nt"
                                     else "tesseract")
        if cand.exists():
            return str(cand)
    return shutil.which("tesseract")


def _try_ocr(pdf_path: Path) -> list[tuple[int, str]] | None:
    """OCR-Kette: Apple Vision (macOS, eingebaut) -> Tesseract -> None."""
    import sys
    if sys.platform == "darwin":
        try:
            return _ocr_pdf_vision(pdf_path)
        except Exception:
            import traceback
            traceback.print_exc()
    if _tesseract_cmd():
        return _ocr_pdf_tesseract(pdf_path)
    return None


def _ocr_pdf_vision(pdf_path: Path) -> list[tuple[int, str]]:
    """Arabische Texterkennung über das in macOS eingebaute Vision-Framework.

    Braucht: pip install pyobjc-framework-Vision (steht in requirements.txt).
    """
    import Vision
    from Foundation import NSData

    pages: list[tuple[int, str]] = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=200)
            png = pix.tobytes("png")
            data = NSData.dataWithBytes_length_(png, len(png))
            handler = (Vision.VNImageRequestHandler.alloc()
                       .initWithData_options_(data, None))
            req = Vision.VNRecognizeTextRequest.alloc().init()
            req.setRecognitionLevel_(0)  # 0 = accurate
            req.setUsesLanguageCorrection_(True)
            try:
                req.setRecognitionLanguages_(["ar-SA", "de-DE", "en-US"])
            except Exception:
                pass
            handler.performRequests_error_([req], None)
            obs = list(req.results() or [])
            # Von oben nach unten sortieren (Vision: Ursprung unten links)
            obs.sort(key=lambda o: -o.boundingBox().origin.y)
            lines = []
            for o in obs:
                cands = o.topCandidates_(1)
                if cands and len(cands):
                    lines.append(str(cands[0].string()))
            pages.append((i, "\n".join(lines)))
            print(f"OCR Seite {i}/{len(doc)}", flush=True)
    return pages


def _ocr_pdf_tesseract(pdf_path: Path) -> list[tuple[int, str]]:
    import os as _os
    cmd = _tesseract_cmd()
    env = dict(_os.environ)
    # Mitgelieferte Sprachdaten benutzen (liegen neben der Binärdatei)
    tessdata = Path(cmd).parent / "tessdata"
    if tessdata.exists():
        env["TESSDATA_PREFIX"] = str(tessdata.parent)
    pages: list[tuple[int, str]] = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=300)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                pix.save(f.name)
                out = subprocess.run(
                    [cmd, f.name, "stdout", "-l", "ara+deu+eng"],
                    capture_output=True, text=True, timeout=120, env=env)
            pages.append((i, out.stdout.strip()))
            print(f"OCR Seite {i}/{len(doc)}", flush=True)
    return pages
