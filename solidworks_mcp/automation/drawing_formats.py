"""
Formati foglio ISO verticali A3..A0 (A14)
-----------------------------------------
SolidWorks fornisce un formato ISO verticale solo per l'A4 (`a4 - iso.slddrt` e' gia' 210x297). Per A3, A2, A1, A0 in verticale
questo modulo GENERA il formato (cornice + cartiglio ISO 7200 con campi collegati alle proprieta') e lo salva come `.slddrt`
nella cartella `formats/` del progetto (mai nella cartella di SolidWorks).

Come si costruisce (verificato su SW 2026, istanza dedicata):
 - nuovo disegno con foglio personalizzato (w x h verticali), `IDrawingDoc.EditTemplate()` per entrare nel formato;
 - linee con `SketchManager.CreateLine` (poi `InsertSketch(True)` per uscire dallo schizzo) e note con `CreateText2`:
   le LINEE e le NOTE vengono salvate nel formato; le TABELLE NO (`InsertGeneralTableAnnotation` in modalita' formato non e' salvata);
 - `IDrawingDoc.EditSheet()` e `ISheet.SaveFormat(percorso)`;
 - il formato si applica con `ISheet.SetTemplateName(percorso)` + `ReloadTemplate(True)`.
Collegamenti nelle note: `$PRP:"SW-File Name"`, `$PRPSHEET:"SW-Sheet Scale"`, `$PRPSHEET:"SW-Current Sheet"`, `$PRPSHEET:"Description"`...

Geometria (mm): cornice con margine di rilegatura di 20 mm a sinistra e 10 mm sugli altri lati; cartiglio 185 x 70 in basso a destra
dentro la cornice (contenuto in `_title_rect`, che e' 195 x 80 dall'angolo del foglio).
"""

import logging
from pathlib import Path
from typing import Dict, Optional

from ..utils.sw_lang import drawing_text, format_suffix

logger = logging.getLogger(__name__)

PORTRAIT_PAPER_MM = {"A3": (297.0, 420.0), "A2": (420.0, 594.0), "A1": (594.0, 841.0), "A0": (841.0, 1189.0)}
FORMATS_DIR = Path(__file__).resolve().parents[2] / "formats"
MM = 0.001


class DrawingFormatsMixin:

    def _pf_path(self, paper: str) -> Path:
        # un file per lingua delle scritte del cartiglio: italiano = file storici, altre lingue = suffisso ' en'
        return FORMATS_DIR / f"{paper.lower()} - iso portrait{format_suffix(self._ui_language())}.slddrt"

    def _pf_build(self, doc, W: float, H: float, paper: str) -> Dict:
        """Disegna cornice e cartiglio nel formato (siamo in EditTemplate). W, H in mm."""
        sk = doc.SketchManager
        n_lines, n_notes = 0, 0

        def line(x0, y0, x1, y1, thick=False):
            nonlocal n_lines
            sg = sk.CreateLine(x0 * MM, y0 * MM, 0, x1 * MM, y1 * MM, 0)
            if sg is not None:
                n_lines += 1
                try:
                    sg.Color = 0
                except Exception:
                    pass
                if thick:
                    try:
                        sg.Width = 3
                    except Exception:
                        pass

        def note(text, x, y_top, h):
            nonlocal n_notes
            t = doc.CreateText2(text, x * MM, y_top * MM, 0, h * MM, 0)
            if t is not None:
                n_notes += 1
                try:
                    t.GetAnnotation.SetPosition2(x * MM, y_top * MM, 0)
                except Exception:
                    pass
            return t

        FX0, FY0, FX1, FY1 = 20.0, 10.0, W - 10.0, H - 10.0
        # cornice (linea spessa) e filetto di taglio esterno
        for a, b in (((FX0, FY0), (FX1, FY0)), ((FX1, FY0), (FX1, FY1)), ((FX1, FY1), (FX0, FY1)), ((FX0, FY1), (FX0, FY0))):
            line(a[0], a[1], b[0], b[1], thick=True)
        # tacche di centratura sui quattro lati (5 mm, dal bordo del foglio)
        cx, cy = W / 2.0, H / 2.0
        line(cx, 0, cx, FY0 + 0.0)
        line(cx, H, cx, FY1)
        line(0, cy, FX0, cy)
        line(W, cy, FX1, cy)
        # cartiglio 185 x 70
        TW, TH = 185.0, 70.0
        X0, Y0 = FX1 - TW, FY0
        X1, Y1 = FX1, FY0 + TH
        for a, b in (((X0, Y0), (X1, Y0)), ((X1, Y0), (X1, Y1)), ((X1, Y1), (X0, Y1)), ((X0, Y1), (X0, Y0))):
            line(a[0], a[1], b[0], b[1], thick=True)
        line(X0, Y0 + 10, X1, Y0 + 10)             # sopra SCALA/FORMATO/FOGLIO
        line(X0, Y0 + 30, X1, Y0 + 30)             # sopra MATERIALE / N. DISEGNO
        line(X0 + 92, Y0 + 10, X0 + 92, Y1)        # colonna destra: N. DISEGNO e TITOLO
        line(X0 + 62, Y0, X0 + 62, Y0 + 10)
        line(X0 + 124, Y0, X0 + 124, Y0 + 10)
        line(X0 + 92, Y0 + 60, X1, Y0 + 60)        # striscia azienda / revisione
        line(X0 + 150, Y0 + 60, X0 + 150, Y1)
        for k in (40.0, 50.0, 60.0):               # blocco firme (a sinistra, sopra MATERIALE)
            line(X0, Y0 + k, X0 + 92, Y0 + k)
        line(X0 + 60, Y0 + 30, X0 + 60, Y0 + 70)   # nome | data
        lab, val = 1.8, 3.5

        lang = self._ui_language()

        def T(key):
            return drawing_text(key, lang)

        def cell(label, value, x, y_top, w_cell, h_cell, vh=val):
            note(label, x + 1.0, y_top - 1.0, lab)
            if value:
                note(value, x + 2.0, y_top - 1.0 - lab - 1.5 - (0.0 if vh <= val else 0.0), vh)

        # riga bassa
        cell(T("scale"), '$PRP:"SW-Sheet Scale"', X0, Y0 + 10, 62, 10)
        cell(T("size"), paper, X0 + 62, Y0 + 10, 62, 10)
        cell(T("sheet"), '$PRP:"SW-Current Sheet" / $PRP:"SW-Total Sheets"', X0 + 124, Y0 + 10, 61, 10)
        # materiale / n. disegno
        cell(T("material"), '$PRPSHEET:"Material"', X0, Y0 + 30, 92, 20)
        note(T("dwg_no"), X0 + 93.0, Y0 + 29.0, lab)
        note('$PRP:"SW-File Name"', X0 + 95.0, Y0 + 25.0, 6.35)
        # titolo
        note(T("title"), X0 + 93.0, Y0 + 59.0, lab)
        note('$PRPSHEET:"Description"', X0 + 95.0, Y0 + 52.0, 5.0)
        # azienda / revisione
        cell(T("company"), '$PRPSHEET:"CompanyName"', X0 + 92, Y0 + 70, 58, 10)
        cell(T("rev"), '$PRPSHEET:"Revision"', X0 + 150, Y0 + 70, 35, 10)
        # firme
        cell(T("drawn"), '$PRPSHEET:"DrawnBy"', X0, Y0 + 70, 60, 10, vh=2.5)
        cell(T("date"), '$PRPSHEET:"DrawnDate"', X0 + 60, Y0 + 70, 32, 10, vh=2.5)
        cell(T("checked"), '$PRPSHEET:"CheckedBy"', X0, Y0 + 60, 60, 10, vh=2.5)
        cell(T("date"), '$PRPSHEET:"CheckedDate"', X0 + 60, Y0 + 60, 32, 10, vh=2.5)
        cell(T("approved"), '$PRPSHEET:"EngineeringApproval"', X0, Y0 + 50, 60, 10, vh=2.5)
        cell(T("date"), '$PRPSHEET:"EngAppDate"', X0 + 60, Y0 + 50, 32, 10, vh=2.5)
        cell(T("weight"), '$PRPSHEET:"Weight"', X0, Y0 + 40, 92, 10, vh=2.5)
        # note generali e proiezione
        note(T("units_note"), FX0 + 2.0, Y0 + 14.0, 2.5)
        note(T("projection_note"), FX0 + 2.0, Y0 + 9.0, 2.5)
        return {"lines": n_lines, "notes": n_notes, "title_block_mm": [X0, Y0, X1, Y1], "frame_mm": [FX0, FY0, FX1, FY1]}

    def ensure_portrait_format(self, paper_size: str) -> Optional[str]:
        """Percorso del formato ISO verticale A3..A0 (lo genera se manca). None se non possibile. Va chiamato PRIMA di creare
        il disegno finale: crea (e chiude) un disegno temporaneo."""
        paper = str(paper_size).strip().upper()
        if paper not in PORTRAIT_PAPER_MM:
            return None
        path = self._pf_path(paper)
        if path.is_file() and path.stat().st_size > 1000:
            return str(path)
        try:
            FORMATS_DIR.mkdir(parents=True, exist_ok=True)
            W, H = PORTRAIT_PAPER_MM[paper]
            tpl = self._default_template("drawing")
            prev = None
            try:
                prev = self._sw_app.ActiveDoc
                prev_title = self._get_doc_title(prev) if prev is not None else None
            except Exception:
                prev_title = None
            doc = self._sw_app.NewDocument(tpl, 12, W * MM, H * MM)
            if doc is None:
                return None
            title = self._get_doc_title(doc)
            sheet = self._com(doc, "GetCurrentSheet")
            sheet.SetProperties2(12, 12, 1.0, 1.0, True, W * MM, H * MM, True)
            doc.EditTemplate()
            info = self._pf_build(doc, W, H, paper)
            try:
                doc.SketchManager.InsertSketch(True)
            except Exception:
                pass
            doc.EditSheet()
            if path.exists():
                path.unlink()
            ok = bool(sheet.SaveFormat(str(path)))
            try:
                self._sw_app.CloseDoc(title)
            except Exception:
                pass
            if prev_title:
                try:
                    import win32com.client
                    import pythoncom
                    err = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                    self._sw_app.ActivateDoc3(prev_title, False, 0, err)
                except Exception:
                    pass
            logger.info(f"formato verticale {paper}: {info} -> {path} ({ok})")
            return str(path) if ok and path.is_file() else None
        except Exception as e:
            logger.warning(f"ensure_portrait_format {paper}: {e}")
            return None
