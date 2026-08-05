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
from dataclasses import dataclass, field
from pathlib import Path

# PyMuPDF (fitz) wird ERST BEI BEDARF geladen (~100 ms Importkosten). Es wird nur
# beim Einlesen/OCR gebraucht, nie beim App-Start – so erscheint das Fenster früher.
def _fitz():
    import fitz  # PyMuPDF
    return fitz

from .textlayout import (clean_text, join_wrapped_lines,
                         paragraphs_from_boxes, paragraphs_from_groups)


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


def _pdf_page_lines(page) -> list[tuple]:
    """Zeilen einer PDF-Seite mit Position: (text, x0, y0, x1, y1).

    Grundlage für die Absatzerkennung – ohne die Positionen wäre nicht
    erkennbar, ob ein Zeilenumbruch ein Absatzende oder nur ein Umbruch
    innerhalb des Absatzes ist.
    """
    lines: list[tuple] = []
    d = page.get_text("dict", sort=True)
    for block in d.get("blocks", []):
        if block.get("type") != 0:      # 1 = Bild
            continue
        for line in block.get("lines", []):
            text = "".join(s.get("text", "") for s in line.get("spans", []))
            if not text.strip():
                continue
            x0, y0, x1, y1 = line.get("bbox", (0.0, 0.0, 0.0, 0.0))
            lines.append((text, x0, y0, x1, y1))
    return lines


def _pdf_page_text(page) -> str:
    """Seitentext als Absätze. Fällt bei Problemen auf den Rohtext zurück."""
    try:
        text = paragraphs_from_boxes(_pdf_page_lines(page))
        if text:
            return text
    except Exception:
        import traceback
        traceback.print_exc()
    return clean_text(page.get_text("text", sort=True))


def extract_pdf(path: Path, force_ocr: bool = False) -> ExtractResult:
    res = ExtractResult()
    res.reliability = "sicher"      # PDF = feste, gedruckte Seiten
    res.engine = "PDF"
    with _fitz().open(path) as doc:
        empty_pages = 0
        for i, page in enumerate(doc, start=1):
            text = _pdf_page_text(page)
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
        # Sprache automatisch aus dem Schriftsystem bestimmen (Textebene bzw.
        # OSD) – kein Festnageln auf eine Sprache.
        ocr_pages = _try_ocr(path, _ocr_sprache(res.pages, path))
        # Die Textschicht NUR ersetzen, wenn OCR wirklich Text geliefert hat.
        # Sonst (OCR nicht verfügbar oder ohne Ergebnis) die vorhandene – ggf.
        # verstümmelte – Textschicht behalten. NIE leere Seiten speichern, wenn
        # eine Textschicht existiert (sonst zeigt der Leser nur „—").
        if ocr_pages is not None and any((t or "").strip() for _, t in ocr_pages):
            # Sicherheitsnetz: hier läuft jedes OCR-Ergebnis noch einmal durch
            # dieselbe Zeichen-/Leerraum-Bereinigung wie die Textschicht.
            res.pages = [(no, clean_text(t)) for no, t in ocr_pages]
            res.needs_ocr = False
            res.warnings.append("Text per OCR (Texterkennung) erfasst.")
        else:
            res.warnings.append(
                "OCR ohne Ergebnis – vorhandene Textschicht beibehalten.")
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


def _word_range_to_text(roh: str) -> str:
    """Word-Steuerzeichen ins Absatz-Format der App übersetzen: Absatzmarke \\r
    und vertikaler Umbruch \\x0b trennen Absätze; Zellen-(\\x07)/Seiten-(\\x0c)/
    sonstige Steuerzeichen raus. Jeder Absatz durch clean_text, Absätze durch
    Leerzeile getrennt (= ein Absatz pro Zeile)."""
    roh = (roh or "").replace("\x0b", "\r").replace("\x0c", "\r")
    sauber = []
    for a in roh.split("\r"):
        a = clean_text(a.replace("\x07", " "))
        if a.strip():
            sauber.append(a)
    return "\n\n".join(sauber)


def _word_text_by_page(path: Path) -> "list[tuple[int, str]] | None":
    """Liest den ECHTEN Word-Text SEITENWEISE über die Word-Automation (Windows).
    So bekommen Word-Dokumente perfekten Text mit Words eigener, exakter
    Paginierung – ohne Umweg über ein PDF und ohne OCR. None, wenn nicht
    verfügbar/fehlgeschlagen (dann greift die bisherige Kaskade)."""
    if os.name != "nt":
        return None
    try:
        import win32com.client as win32
    except Exception:
        return None
    WD_STAT_PAGES = 2       # wdStatisticPages
    WD_GOTO_PAGE = 1        # wdGoToPage
    WD_GOTO_ABSOLUTE = 1    # wdGoToAbsolute
    word = None
    try:
        word = win32.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(str(path), ReadOnly=True)
        try:
            total = int(doc.ComputeStatistics(WD_STAT_PAGES)) or 1
            starts = [word.Selection.GoTo(WD_GOTO_PAGE, WD_GOTO_ABSOLUTE, p).Start
                      for p in range(1, total + 1)]
            grenzen = starts + [doc.Content.End]
            pages = [(i + 1, _word_range_to_text(doc.Range(grenzen[i], grenzen[i + 1]).Text))
                     for i in range(total)]
        finally:
            doc.Close(False)
        return pages if any(t.strip() for _, t in pages) else None
    except Exception:
        import traceback
        traceback.print_exc()
        return None
    finally:
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass


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

        # Stufe 1: lokales Word (am genauesten, offline, kein Konto).
        if _word_installed():
            # Bevorzugt den ECHTEN Word-Text seitenweise direkt lesen – perfekter
            # Text mit Words eigener, exakter Paginierung, ohne PDF/OCR-Umweg.
            try:
                if progress:
                    progress("wird aus Word gelesen …")
                seiten = _word_text_by_page(path)
                if seiten:
                    res = ExtractResult()
                    res.pages = seiten
                    res.reliability = "exakt"
                    res.engine = "Word"
                    res.real_page_numbers = True
                    res.warnings.append(
                        "Text direkt aus Word gelesen – Seitenzahlen exakt wie in Word.")
                    return res
            except Exception:
                import traceback
                traceback.print_exc()
            # Rückfall: Word -> PDF -> Extraktion (wie bisher), falls das
            # direkte Lesen fehlschlägt.
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
    # Word kennt die Absätze exakt – deshalb hier Leerzeile statt Umbruch und
    # kein Zusammenfassen von Zeilen (das würde nur raten).
    full = "\n\n".join(par.text for par in d.paragraphs)
    res = _paginate_plain(full, join=False)
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


def _paginate_plain(text: str, chars_per_page: int = 2000,
                    join: bool = True) -> ExtractResult:
    """Künstliche Seiten aus reinem Text.

    Geschnitten wird weiterhin am Rohtext, damit sich die Seitengrenzen
    gegenüber früher nicht verschieben; erst danach wird der Text jeder
    Seite aufbereitet.
    """
    res = ExtractResult()
    pos, page_no = 0, 1
    while pos < len(text):
        seite = text[pos:pos + chars_per_page]
        res.pages.append(
            (page_no, join_wrapped_lines(seite) if join else clean_text(seite)))
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


def _ocr_sprache(pages, pdf_path) -> str:
    """Bestimmt automatisch die OCR-Sprache eines Dokuments. Grundlage ist das
    Schriftsystem der (ggf. verstümmelten) Textebene – die Zeichen stimmen auch
    bei falscher Reihenfolge. Ohne brauchbare Textebene (echter Scan) entscheidet
    Tesseracts OSD anhand der ersten Seite. Einzelschrift-Dokumente bekommen NUR
    ihre Sprache (keine Kreuz-Artefakte): arabisch → 'ara', lateinisch →
    'deu+eng'. Nur wenn wirklich beide Schriften vorkommen → 'ara+deu+eng'."""
    txt = " ".join(t or "" for _, t in pages)
    ar = len(re.findall(r"[؀-ۿ]", txt))
    la = len(re.findall(r"[A-Za-z]", txt))
    if ar + la >= 20:
        anteil = ar / (ar + la)
        if anteil >= 0.85:
            return "ara"
        if anteil <= 0.15:
            return "deu+eng"
        return "ara+deu+eng"
    return _osd_sprache(pdf_path)


def _osd_sprache(pdf_path) -> str:
    """Schriftsystem der ersten Seite via Tesseract-OSD; Rückfall 'ara'."""
    cmd = _tesseract_cmd()
    if not cmd:
        return "ara"
    tessdata = Path(cmd).parent / "tessdata"
    tdata = ["--tessdata-dir", str(tessdata)] if tessdata.exists() else []
    tmp = Path(tempfile.mkdtemp(prefix="aicp-osd-"))
    try:
        with _fitz().open(pdf_path) as doc:
            if len(doc) == 0:
                return "ara"
            png = tmp / "osd.png"
            doc[0].get_pixmap(dpi=300).save(str(png))
        out = subprocess.run([cmd, *tdata, "--psm", "0", str(png), "stdout"],
                             capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=60)
        m = re.search(r"Script:\s*(\w+)", out.stdout or "")
        skript = (m.group(1) if m else "").lower()
        if skript == "arabic":
            return "ara"
        if skript == "latin":
            return "deu+eng"
        return "ara"
    except Exception:
        return "ara"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _try_ocr(pdf_path: Path, lang: str = "ara") -> list[tuple[int, str]] | None:
    """OCR-Kette: Apple Vision (macOS, eingebaut) -> Tesseract -> None.
    `lang` ist die (automatisch erkannte) Sprache für Tesseract; Vision erkennt
    die Sprache selbst und ignoriert den Parameter."""
    import sys
    if sys.platform == "darwin":
        try:
            return _ocr_pdf_vision(pdf_path)
        except Exception:
            import traceback
            traceback.print_exc()
    if _tesseract_cmd():
        return _ocr_pdf_tesseract(pdf_path, lang)
    return None


def _ocr_pdf_vision(pdf_path: Path) -> list[tuple[int, str]]:
    """Arabische Texterkennung über das in macOS eingebaute Vision-Framework.

    Braucht: pip install pyobjc-framework-Vision (steht in requirements.txt).
    """
    import Vision
    from Foundation import NSData

    pages: list[tuple[int, str]] = []
    with _fitz().open(pdf_path) as doc:
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
            # Vision liefert normierte Boxen mit Ursprung UNTEN links. Für die
            # Absatzerkennung werden sie auf Bildpunkte mit Ursprung OBEN
            # links umgerechnet – erst dann sind waagerechte und senkrechte
            # Abstände miteinander vergleichbar.
            lines: list[tuple] = []
            for o in obs:
                cands = o.topCandidates_(1)
                if not (cands and len(cands)):
                    continue
                box = o.boundingBox()
                bx, by = box.origin.x, box.origin.y
                bw, bh = box.size.width, box.size.height
                lines.append((str(cands[0].string()),
                              bx * pix.width, (1.0 - by - bh) * pix.height,
                              (bx + bw) * pix.width, (1.0 - by) * pix.height))
            pages.append((i, paragraphs_from_boxes(lines)))
            print(f"OCR Seite {i}/{len(doc)}", flush=True)
    return pages


def _tesseract_tsv_to_text(tsv: str) -> str:
    """Baut aus Tesseracts TSV-Ausgabe Absätze.

    Tesseract erkennt die Absätze selbst und gibt sie in den Spalten
    block_num/par_num aus – genauer als jede Heuristik auf dem fertigen
    Text. Spalten: level, page, block, par, line, word, left, top, width,
    height, conf, text.
    """
    if not tsv:
        return ""
    gruppen: dict[tuple[int, int], dict[int, list[str]]] = {}
    reihenfolge: list[tuple[int, int]] = []
    for row in tsv.splitlines()[1:]:
        f = row.split("\t")
        if len(f) < 12 or f[0] != "5":       # 5 = Ebene "Wort"
            continue
        try:
            conf = float(f[10])
            block, par, line = int(f[2]), int(f[3]), int(f[4])
        except ValueError:
            continue
        wort = f[11].strip()
        if not wort or conf < 0:
            continue
        key = (block, par)
        if key not in gruppen:
            gruppen[key] = {}
            reihenfolge.append(key)
        gruppen[key].setdefault(line, []).append(wort)
    absaetze = [[" ".join(gruppen[k][ln]) for ln in sorted(gruppen[k])]
                for k in reihenfolge]
    return paragraphs_from_groups(absaetze)


def _ocr_pdf_tesseract(pdf_path: Path, lang: str = "ara") -> "list[tuple[int, str]] | None":
    import os as _os
    cmd = _tesseract_cmd()
    env = dict(_os.environ)
    # Mitgelieferte Sprachdaten liegen im Unterordner "tessdata" neben der
    # Binärdatei. WICHTIG: Tesseract 5 will TESSDATA_PREFIX bzw. --tessdata-dir
    # DIREKT auf diesen Ordner (nicht auf den Elternordner wie noch bei v4) –
    # sonst findet es die *.traineddata nicht und liefert leeren Text
    # ("Error opening data file … ara.traineddata"). --tessdata-dir ist
    # versionsunabhängig und eindeutig.
    tessdata = Path(cmd).parent / "tessdata"
    tdata_args: list[str] = []
    if tessdata.exists():
        env["TESSDATA_PREFIX"] = str(tessdata)
        tdata_args = ["--tessdata-dir", str(tessdata)]
    # Sprache kommt vom Aufrufer (automatisch erkannt). Wichtig: KEINE
    # Schriftsysteme mischen, wo es nicht nötig ist – deu/eng auf rein arabischen
    # Seiten erzeugen massenhaft lateinische Fehl-Lesungen und verschlechtern die
    # arabische Erkennung (gemessen). Darum ara-Dokumente nur mit "ara".
    sprache = ["-l", lang]
    pages: list[tuple[int, str]] = []
    hat_text = False       # mindestens eine Seite mit echtem Text erkannt?
    # Ob diese Tesseract-Installation die TSV-Ausgabe beherrscht, wird an der
    # ersten Seite entschieden – sonst liefe die (teure) Erkennung doppelt.
    tsv_moeglich = True
    # Eigener Temp-Ordner: die Seiten-PNG wird unter einem FRISCHEN Pfad
    # geschrieben, den Python NICHT offen hält. Sonst sperrt Windows die Datei,
    # und PyMuPDFs pix.save() bricht mit „cannot remove file … Permission denied"
    # ab (ein Virenscanner verschärft das). Aufräumen ist hier nie fatal.
    tmpdir = Path(tempfile.mkdtemp(prefix="aicp-ocr-"))
    try:
        with _fitz().open(pdf_path) as doc:
            for i, page in enumerate(doc, start=1):
                pix = page.get_pixmap(dpi=300)
                png = tmpdir / f"seite-{i}.png"
                pix.save(str(png))          # frischer Pfad, kein offenes Handle
                png_name = str(png)
                text = None
                # Bevorzugt TSV: enthält die Absätze der OCR-Engine selbst
                if tsv_moeglich:
                    try:
                        out = subprocess.run(
                            [cmd, *tdata_args, png_name, "stdout", *sprache,
                             "tsv"], capture_output=True, text=True,
                            encoding="utf-8", errors="replace",
                            timeout=120, env=env)
                        if out.returncode == 0:
                            text = _tesseract_tsv_to_text(out.stdout)
                        else:
                            tsv_moeglich = False
                    except subprocess.TimeoutExpired:
                        raise
                    except Exception:
                        tsv_moeglich = False
                        import traceback
                        traceback.print_exc()
                if text is None:
                    # Rückfall: reiner Text, Absätze über die Zeilenlängen.
                    out = subprocess.run(
                        [cmd, *tdata_args, png_name, "stdout", *sprache],
                        capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=120, env=env)
                    # Scheitert Tesseract (z. B. Sprachdaten nicht gefunden), ist
                    # die Ausgabe leer – dann keinen leeren Text erzwingen.
                    text = join_wrapped_lines(out.stdout) if out.returncode == 0 else ""
                pages.append((i, text))
                if text.strip():
                    hat_text = True
                try:
                    png.unlink()            # sofort aufräumen …
                except OSError:
                    pass                    # … aber nie den Upload abbrechen
                print(f"OCR Seite {i}/{len(doc)}", flush=True)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    # Hat OCR NICHTS Brauchbares geliefert (z. B. Tesseract-Fehler), als
    # Fehlschlag melden: der Aufrufer behält dann die vorhandene Textebene,
    # statt leere Seiten zu speichern.
    if not hat_text:
        return None
    return pages
