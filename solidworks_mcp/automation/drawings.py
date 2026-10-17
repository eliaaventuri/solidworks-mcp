"""
SolidWorks Drawing Operations
-----------------------------
Messe in tavola (disegni 2D): fogli, viste, sezioni, dettagli, quote, annotazioni,
cartiglio, distinta base, palloncini, export.

Convenzioni:
- Tutti i tool lavorano sul documento ATTIVO e verificano che sia un disegno (tipo 3).
- Le posizioni sul foglio (x, y) partono dall'angolo in basso a sinistra; `unit` come gli altri
  tool (default mm). I valori restituiti sono sempre in mm.
- I nomi predefiniti di SolidWorks sono localizzati: qui si usano solo costanti numeriche,
  posizione nell'albero o nomi chiesti al modello (`GetModelViewNames`).
- Le coordinate degli schizzi dentro una vista (linea di sezione, cerchio di dettaglio...) sono
  in unita' MODELLO (non scalate), con origine al CENTRO della vista (`view.Position`).
"""

import os
import re
import logging
import traceback
from typing import Dict, List, Optional, Tuple, Any

import win32com.client
import pythoncom

from ..constants import SwErrors
from .drawing_dims import DrawingDimsMixin
from .drawing_diam import DrawingDiamMixin
from .drawing_annot import DrawingAnnotMixin
from .drawing_formats import DrawingFormatsMixin
from .drawing_aux import DrawingAuxMixin
from .drawing_pos import DrawingPosMixin
from .drawing_layout import (DrawingLayoutMixin, STD_SCALES, VIEW_PAD, GAP_X,
                             MARGIN_R, MARGIN_T)
from ..utils.sw_lang import lang_folders

logger = logging.getLogger(__name__)

# swDocumentTypes_e
DOC_PART, DOC_ASSEMBLY, DOC_DRAWING = 1, 2, 3

PAPER_MM = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0),
            "A1": (841.0, 594.0), "A0": (1189.0, 841.0)}

# swStandardViews_e -> index in IModelDoc2.GetModelViewNames (0 = "Normal to")
ORIENTATIONS = {
    "front": 1, "frontale": 1, "anteriore": 1,
    "back": 2, "rear": 2, "posteriore": 2,
    "left": 3, "sinistra": 3,
    "right": 4, "destra": 4,
    "top": 5, "superiore": 5, "alto": 5,
    "bottom": 6, "inferiore": 6, "basso": 6,
    "isometric": 7, "iso": 7, "isometrica": 7, "isometrico": 7,
    "trimetric": 8, "trimetrica": 8, "trimetrico": 8,
    "dimetric": 9, "dimetrica": 9, "dimetrico": 9,
}
_EN_NAMES = {1: "*Front", 2: "*Back", 3: "*Left", 4: "*Right", 5: "*Top", 6: "*Bottom",
             7: "*Isometric", 8: "*Trimetric", 9: "*Dimetric"}

# Observed swDrawingViewTypes_e values (verified live on SW 2026)
VIEW_TYPES = {1: "sheet", 2: "section", 3: "detail", 4: "projected", 5: "auxiliary",
              7: "model", 6: "relative", 8: "relative", 9: "relative"}

DISPLAY_STYLES = {"wireframe": 0, "hidden_visible": 1, "hidden_removed": 2,
                  "shaded": 3, "shaded_edges": 4}

def _arr(*vals):
    """double[] as a typed SAFEARRAY (a plain tuple is read wrongly by IView.Position)."""
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, tuple(float(v) for v in vals))


class DrawingOperations(DrawingLayoutMixin, DrawingDimsMixin, DrawingDiamMixin, DrawingAnnotMixin, DrawingFormatsMixin, DrawingAuxMixin, DrawingPosMixin):
    """Mixin: drawing (2D) operations. Requires SolidWorksAutomation base."""

    # ====================================================================
    # Helpers
    # ====================================================================

    _null_disp = None

    @property
    def _NULL(self):
        return win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)

    def _drawing(self) -> Tuple[Any, Optional[Dict]]:
        """Active document, verified to be a drawing."""
        doc, err = self.get_active_doc()
        if err:
            return None, err
        try:
            dtype = int(self._com(doc, "GetType"))
        except Exception:
            dtype = -1
        if dtype != DOC_DRAWING:
            return None, self._result(
                False,
                f"Il documento attivo ({self._get_doc_title(doc)}) non e' un disegno. "
                "Attiva o crea un disegno (create_drawing) e riprova.",
                SwErrors.swInvalidInput)
        return doc, None

    def _fail(self, what: str, e: Exception) -> Dict:
        logger.error(f"{what}: {e}\n{traceback.format_exc()}")
        return self._result(False, f"{what}: {e}", SwErrors.swUnknownError)

    def _m(self, value: float, unit: Optional[str]) -> float:
        return self._units.to_meters(value, unit)

    @staticmethod
    def _mm(value_m: float) -> float:
        return round(value_m * 1000.0, 3)

    def _sheet_views(self, doc) -> List[Any]:
        sheet = self._com(doc, "GetCurrentSheet")
        views = self._com(sheet, "GetViews")
        out = []
        for v in (views or ()):
            if v is not None:
                out.append(v)
        return out

    def _show_exploded(self, v, on: bool = True) -> bool:
        """Mostra/nasconde l'esploso in una vista d'assieme (IView.ShowExploded). True se lo stato richiesto e' attivo.
        Richiede una vista esplosa nella configurazione del modello, salvata nel file dell'assieme."""
        try:
            v.ShowExploded(bool(on))
            return bool(self._com(v, "IsExploded")) == bool(on)
        except Exception as e:
            logger.debug(f"ShowExploded failed: {e}")
            return False

    def _view_info(self, v) -> Dict:
        pos = tuple(v.Position)
        try:
            ol = tuple(self._com(v, "GetOutline"))
        except Exception:
            ol = (pos[0], pos[1], pos[0], pos[1])
        vtype = int(v.Type)
        try:
            scale = float(v.ScaleDecimal)
        except Exception:
            scale = 1.0
        return {
            "name": self._com(v, "GetName2"),
            "type": vtype,
            "type_name": VIEW_TYPES.get(vtype, f"type_{vtype}"),
            "scale": round(scale, 6),
            "x_mm": self._mm(pos[0]), "y_mm": self._mm(pos[1]),
            "width_mm": self._mm(ol[2] - ol[0]), "height_mm": self._mm(ol[3] - ol[1]),
            "outline_mm": [self._mm(ol[0]), self._mm(ol[1]), self._mm(ol[2]), self._mm(ol[3])],
            "exploded": self._view_exploded(v),
        }

    def _view_exploded(self, v) -> bool:
        try:
            return bool(self._com(v, "IsExploded"))
        except Exception:
            return False

    def _find_view(self, doc, name: Optional[str]) -> Tuple[Any, Optional[Dict]]:
        """Resolve a view by (localized) name, case-insensitive substring, or index.
        name None -> first model view."""
        views = self._sheet_views(doc)
        if not views:
            return None, self._result(False, "Il foglio attivo non contiene viste.",
                                      SwErrors.swInvalidInput)
        if name is None or name == "":
            for v in views:
                if int(v.Type) == 7:
                    return v, None
            return views[0], None
        names = [self._com(v, "GetName2") for v in views]
        if name in names:
            return views[names.index(name)], None
        low = str(name).lower()
        hits = [i for i, n in enumerate(names) if low in n.lower()]
        if len(hits) == 1:
            return views[hits[0]], None
        if str(name).isdigit() and int(name) < len(views):
            return views[int(name)], None
        return None, self._result(False, f"Vista '{name}' non trovata. Viste: {names}",
                                  SwErrors.swInvalidInput)

    def _select_view(self, doc, view) -> bool:
        doc.ClearSelection2(True)
        return bool(doc.Extension.SelectByID2(self._com(view, "GetName2"), "DRAWINGVIEW",
                                              0, 0, 0, False, 0, self._NULL, 0))

    def _end_view_sketch(self, doc):
        """Leave the view-sketch mode (the sheet becomes active again)."""
        try:
            doc.SketchManager.InsertSketch(True)
        except Exception:
            pass
        try:
            doc.ClearSelection2(True)
        except Exception:
            pass

    @staticmethod
    def _parse_scale(scale) -> Optional[Tuple[int, int]]:
        """None/'auto' -> None; 0.5 -> (1,2); '1:2' -> (1,2); '2:1' -> (2,1)."""
        if scale is None or (isinstance(scale, str) and scale.strip().lower() in ("", "auto")):
            return None
        if isinstance(scale, str) and ":" in scale:
            a, b = scale.split(":", 1)
            return int(float(a)), int(float(b))
        s = float(scale)
        if s >= 1:
            return int(round(s)), 1
        return 1, int(round(1.0 / s))

    def _set_view_scale(self, view, n: int, d: int):
        try:
            view.UseSheetScale = False
        except Exception:
            pass
        try:
            view.ScaleRatio = _arr(n, d)
        except Exception:
            pass
        try:
            if abs(float(view.ScaleDecimal) - n / d) > 1e-9:
                view.ScaleDecimal = n / d      # le viste di dettaglio ignorano ScaleRatio
        except Exception:
            view.ScaleDecimal = n / d

    def _sheet_dims(self, doc) -> Tuple[float, float, bool]:
        sheet = self._com(doc, "GetCurrentSheet")
        p = sheet.GetProperties2
        return float(p[5]), float(p[6]), bool(p[4])

    def _get_model_doc(self, path: str):
        """Return the open model document for `path`, opening it silently if needed."""
        doc = self._sw_app.GetOpenDocumentByName(path)
        if doc is not None:
            return doc, False
        ext = os.path.splitext(path)[1].lower()
        dtype = DOC_ASSEMBLY if ext == ".sldasm" else DOC_PART
        errors = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        warnings = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        doc = self._sw_app.OpenDoc6(path, dtype, 1, "", errors, warnings)
        return doc, doc is not None

    def _model_view_name(self, model_path: str, orientation: str) -> Tuple[Optional[str], Optional[int]]:
        """Localized name of a standard model view (e.g. '*Anteriore')."""
        key = str(orientation).strip().lower().lstrip("*")
        idx = orientation if isinstance(orientation, int) else ORIENTATIONS.get(key)
        names = []
        try:
            mdoc, _ = self._get_model_doc(model_path)
            names = [n for n in (self._com(mdoc, "GetModelViewNames") or ())]
        except Exception as e:
            logger.debug(f"GetModelViewNames failed: {e}")
        if idx is not None:
            if len(names) > idx:
                return names[idx], idx
            return _EN_NAMES[idx], idx
        for n in names:  # custom/named view
            if n.lstrip("*").lower() == key:
                return n, None
        return None, None

    def _view_model_path(self, view) -> str:
        try:
            return str(self._com(view, "GetReferencedModelName"))
        except Exception:
            return ""

    def _model_path_for_drawing(self, doc, model_path: Optional[str] = None) -> str:
        if model_path:
            return os.path.abspath(model_path)
        for v in self._sheet_views(doc):
            p = self._view_model_path(v)
            if p:
                return p
        return getattr(self, "_drawing_model_path", "") or ""

    def _model_box(self, mdoc) -> Tuple[float, float, float]:
        """Bounding box size (dx, dy, dz) in m; falls back to 0.1."""
        for call in (lambda: mdoc.GetPartBox(True), lambda: mdoc.GetBox(0)):
            try:
                b = call()
                if b and len(b) >= 6:
                    return abs(b[3] - b[0]), abs(b[4] - b[1]), abs(b[5] - b[2])
            except Exception:
                continue
        return 0.1, 0.1, 0.1

    def _sheet_format_path(self, paper: str, orientation: str, style: str = "iso") -> str:
        if style in ("none", "", None):
            return ""
        if os.path.isfile(str(style)):
            return str(style)
        tpl = self._default_template("drawing")
        root = os.path.dirname(os.path.dirname(tpl)) if tpl else ""
        paper = paper.lower()
        names = []
        if orientation == "portrait":
            if paper == "a4":
                names = ["a4 - portrait.slddrt"]
            else:
                # (A14) nessun formato verticale fornito da SW per A3..A0: lo genera drawing_formats.py in formats/
                p_ = self._pf_path(paper.upper())
                return str(p_) if p_.is_file() else ""
        else:
            names = [f"{paper} - {style}.slddrt", f"{paper} - landscape.slddrt"]
        for lang in lang_folders(self._ui_language()):
            for n in names:
                p = os.path.join(root, "lang", lang, "sheetformat", n)
                if os.path.isfile(p):
                    return p
        return ""

    def _paper_dims(self, paper_size: str, orientation: str) -> Tuple[float, float]:
        key = paper_size.strip().upper()
        if key not in PAPER_MM:
            raise ValueError(f"Formato foglio non supportato: {paper_size} (usa {list(PAPER_MM)})")
        w, h = PAPER_MM[key]
        if orientation.lower().startswith("p"):
            w, h = h, w
        return w / 1000.0, h / 1000.0

    # ====================================================================
    # 1. create_drawing
    # ====================================================================

    def create_drawing(self, model_path: str = None, paper_size: str = "A3",
                       orientation: str = "landscape", projection: str = "first",
                       scale=None, template: str = None, sheet_format: str = "iso",
                       add_views: bool = False, save_as: str = None, save_model: bool = True) -> Dict:
        """Create a drawing from a part/assembly (path or active saved document)."""
        try:
            if not self.is_connected:
                r = self.connect()
                if not r["success"]:
                    return r
            # --- model
            if not model_path:
                cur = self._sw_app.ActiveDoc
                if cur is None or int(self._com(cur, "GetType")) not in (DOC_PART, DOC_ASSEMBLY):
                    return self._result(False, "Serve un pezzo/assieme attivo o `model_path`.",
                                        SwErrors.swInvalidInput)
                model_path = self._get_doc_path(cur)
                if not model_path:
                    return self._result(False, "Il documento attivo non e' salvato: salvalo prima.",
                                        SwErrors.swInvalidInput)
            model_path = os.path.abspath(model_path)
            if not os.path.isfile(model_path):
                return self._result(False, f"File non trovato: {model_path}", SwErrors.swFileNotFoundError)
            mdoc, opened = self._get_model_doc(model_path)
            if mdoc is None:
                return self._result(False, f"Impossibile aprire il modello: {model_path}",
                                    SwErrors.swFileLoadError)
            # --- sheet
            auto_paper = str(paper_size).strip().lower() == "auto"
            if auto_paper:
                paper_size = "A3"      # provvisorio: il foglio definitivo (A4..A0) lo sceglie add_standard_views
            w, h = self._paper_dims(paper_size, orientation)
            if orientation.lower().startswith("p") and paper_size.upper() in ("A3", "A2", "A1", "A0")                     and str(sheet_format).lower() == "iso" and not auto_paper:
                self.ensure_portrait_format(paper_size)          # (A14) formato verticale generato, prima del disegno finale
                self._sw_app.ActivateDoc3(self._get_doc_title(mdoc), False, 0, win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0))
            tpl = template or self._default_template("drawing")
            if not tpl:
                from ..utils import find_template
                tpl = find_template("drawing")
            if not tpl or not os.path.isfile(tpl):
                return self._result(False, f"Template di disegno non trovato: {tpl}",
                                    SwErrors.swFileNotFoundError)
            first = projection.lower().startswith(("first", "primo", "1", "iso", "eur"))
            parsed = self._parse_scale(scale)
            n, d = parsed if parsed else (1, 1)
            doc = self._sw_app.NewDocument(tpl, 12, w, h)
            if doc is None:
                return self._result(False, "Creazione disegno fallita", SwErrors.swFileLoadError)
            sheet = self._com(doc, "GetCurrentSheet")
            sheet.SetProperties2(12, 12, float(n), float(d), bool(first), w, h, True)
            fmt = self._sheet_format_path(paper_size, orientation.lower(), sheet_format)
            fmt_used = ""
            if fmt:
                sheet.SetTemplateName(fmt)
                sheet.ReloadTemplate(True)
                fmt_used = os.path.basename(fmt)
            self._drawing_model_path = model_path
            # every property referenced by the title block must exist (else the sheet shows "ERRORE:<name>")
            created_props = self._ensure_titleblock_props(doc, mdoc)
            missing = self._missing_props_from_dxf(doc)
            if missing:
                created_props += self._ensure_titleblock_props(doc, mdoc, extra=missing)
            if created_props and save_model and opened is False and self._get_doc_path(mdoc):
                try:
                    mdoc.Save3(1, 0, 0)   # persist the new (empty) properties in the model
                except Exception as e:
                    logger.debug(f"model save failed: {e}")
            if save_as:
                ok_s, e_s, w_s = self._save_as(doc, os.path.abspath(save_as))
                if not ok_s:
                    logger.warning(f"create_drawing save_as failed: {e_s}/{w_s}")
            tnum = self._fit_title_number(doc)
            title = self._get_doc_title(doc)
            if not hasattr(self, "_auto_paper"):
                self._auto_paper = {}
            self._auto_paper[title] = bool(auto_paper)
            if model_path.lower().endswith(".sldasm"):
                # keep the top-left corner free for the bill of materials
                if not hasattr(self, "_reserved"):
                    self._reserved = {}
                self._reserved[title] = [(0.005, h - 0.005 - 0.09, 0.215, h - 0.005)]
            data = {"title": title, "sheet": self._com(sheet, "GetName"),
                    "paper": paper_size.upper() + (" (provvisorio: auto)" if auto_paper else ""), "orientation": orientation,
                    "width_mm": self._mm(w), "height_mm": self._mm(h),
                    "projection": "first_angle" if first else "third_angle",
                    "model": model_path, "model_opened_by_tool": opened,
                    "sheet_format": fmt_used or "none",
                    "titleblock_properties_created": len(created_props),
                    "still_missing": self._missing_props_from_dxf(doc),
                    "saved_as": os.path.abspath(save_as) if save_as else "", "title_number": tnum}
            msg = f"Disegno creato: {title} ({paper_size.upper()} {orientation}, " \
                  f"{'primo' if first else 'terzo'} diedro)"
            if add_views:
                r = self.add_standard_views(["front", "top", "right", "isometric"],
                                            scale=scale, model_path=model_path)
                data["views"] = r.get("data", {}) if r["success"] else {"error": r["message"]}
                if not r["success"]:
                    msg += f" - viste NON create: {r['message']}"
            return self._result(True, msg, SwErrors.swSuccess, data)
        except Exception as e:
            return self._fail("create_drawing", e)

    # ====================================================================
    # 2-4. Views
    # ====================================================================

    def _pick_paper(self, first, fit_fn, parsed) -> Tuple[str, Tuple[int, int], Optional[Tuple[int, int]]]:
        """Foglio e scala automatici: il foglio piu' piccolo (A4..A0) dove le viste stanno almeno in scala 1:1
        (o nella scala richiesta); se nessuno ci arriva, il piu' piccolo con almeno 1:2, altrimenti A0.
        fit_fn(W, H, first) -> ((n, d), scala_iso | None) oppure None. Restituisce (foglio, scala, scala_iso)."""
        order = ("A4", "A3", "A2", "A1", "A0")
        fits = {}
        for pname in order:
            # il formato ISO A4 di SolidWorks (a4 - iso.slddrt) e' VERTICALE: si pianifica con quelle misure
            w, h = self._paper_dims(pname, "portrait" if pname == "A4" else "landscape")
            fits[pname] = fit_fn(w, h, first)
        if parsed:
            for pname in order:
                if fits[pname]:
                    return pname, fits[pname][0], fits[pname][1]
            return "A0", parsed, None
        # preferenza: A4/A3 in scala >= 1:1 (anche ingrandita: 2:1, 5:1), poi A4/A3 fino a 1:2, poi fogli piu' grandi
        # (A6) prima di ridurre la scala sotto 1:1 si prova il formato A2 in scala >= 1:1
        steps = ((("A4", "A3"), 1.0), (("A2",), 1.0), (("A4", "A3"), 0.5), (("A2", "A1", "A0"), 0.5), (("A2", "A1", "A0"), 0.0))
        for names, lim in steps:
            for pname in names:
                f = fits[pname]
                if f and f[0][0] / f[0][1] >= lim - 1e-9:
                    return pname, f[0], f[1]
        f = fits["A0"] or (STD_SCALES[-1], None)
        return "A0", f[0], f[1]

    def _apply_paper(self, doc, paper: str) -> None:
        """Cambia il formato del foglio attivo (landscape) e ricarica il cartiglio ISO."""
        sheet = self._com(doc, "GetCurrentSheet")
        p = sheet.GetProperties2
        old_h = float(p[6])
        w, h = self._paper_dims(paper, "portrait" if str(paper).upper() == "A4" else "landscape")
        sheet.SetProperties2(12, 12, float(p[2]), float(p[3]), bool(p[4]), w, h, True)
        fmt = self._sheet_format_path(paper, "landscape", "iso")
        if fmt:
            sheet.SetTemplateName(fmt)
            sheet.ReloadTemplate(False)     # False: scarta le note del formato precedente (altrimenti due cartigli)
            self._fit_title_number(doc)
        title = self._get_doc_title(doc)
        res = getattr(self, "_reserved", {}).get(title)
        if res:
            self._reserved[title] = [(r[0], r[1] + (h - old_h), r[2], r[3] + (h - old_h)) for r in res]

    def add_standard_views(self, views: List[str] = None, scale=None, model_path: str = None,
                           x_gap: float = None, unit: str = None, exploded: bool = False) -> Dict:
        """Standard orthographic views with automatic scale (ISO series) and spacing.

        The layout follows the sheet projection (first/third angle), leaves room for dimensions between
        the views, avoids the title block and puts pictorial (isometric...) views in the free top-right
        corner. After creation the positions are re-computed from the real view outlines."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            views = [str(v).lower() for v in (views or ["front", "top", "right", "isometric"])]
            keys = []
            for v in views:
                idx = ORIENTATIONS.get(v.lstrip("*"))
                if idx is None:
                    return self._result(False, f"Vista sconosciuta: {v}", SwErrors.swInvalidInput)
                if idx not in keys:
                    keys.append(idx)
            mpath = self._model_path_for_drawing(doc, model_path)
            if not mpath or not os.path.isfile(mpath):
                return self._result(False, "Modello di riferimento non trovato (passa model_path).",
                                    SwErrors.swInvalidInput)
            W, H, first = self._sheet_dims(doc)
            self._layout_title = self._get_doc_title(doc)
            ortho_dirs = (5, 6, 3, 4)
            plan_keys = list(keys)
            if 1 not in plan_keys:
                plan_keys = [1] + plan_keys          # the front view is the projection parent
            drop_front = False
            parsed = self._parse_scale(scale)
            gx = self._m(x_gap, unit) if x_gap else GAP_X
            sheet = self._com(doc, "GetCurrentSheet")
            above, below = (6, 5) if first else (5, 6)
            leftc, rightc = (4, 3) if first else (3, 4)
            # 1) create every view at 1:1 (rough positions only fix the projection directions)
            rough = {k: (0.12, 0.08) for k in plan_keys}
            pos, _ = self._plan_layout(W, H, first, plan_keys, rough, gx=gx)
            # (A14) le posizioni di creazione servono SOLO a dare la direzione di proiezione: attorno alla frontale, al centro del
            # foglio, a distanza fissa (se il layout stimato non entra, per es. su un foglio verticale stretto, _plan_layout
            # restituisce posizioni sovrapposte e la proiezione sbagliata duplicava una vista). Le posizioni vere si calcolano dopo.
            cdist = min(W, H) * 0.25
            pos = dict(pos)
            pos[1] = (W / 2.0, H / 2.0)
            pos[above] = (W / 2.0, H / 2.0 + cdist)
            pos[below] = (W / 2.0, H / 2.0 - cdist)
            pos[leftc] = (W / 2.0 - cdist, H / 2.0)
            pos[rightc] = (W / 2.0 + cdist, H / 2.0)
            pos[2] = (W / 2.0 + 2 * cdist, H / 2.0)
            sheet.SetScale(1, 1, True, True)
            objs, base_view = {}, None
            explode_failed = []
            order = [1] + [k for k in plan_keys if k != 1]
            for k in order:
                vname, _ = self._model_view_name(mpath, k)
                x, y = pos[k]
                if k in (above, below, leftc, rightc) and base_view is not None:
                    self._select_view(doc, base_view)
                    v = doc.CreateUnfoldedViewAt3(x, y, 0, False)
                else:
                    v = doc.CreateDrawViewFromModelView3(mpath, vname, x, y, 0)
                if v is None:
                    return self._result(False, f"Creazione vista {k} fallita", SwErrors.swUnknownError,
                                        {"created": list(objs)})
                if k == 1:
                    base_view = v
                if int(v.Type) == 7:
                    try:
                        v.UseSheetScale = True
                    except Exception:
                        pass
                if exploded and k in (7, 8, 9):
                    # esploso nelle sole viste pittoriche, PRIMA di misurarle (il contorno cresce)
                    if not self._show_exploded(v, True):
                        explode_failed.append(k)
                if not objs:
                    sheet.SetScale(1, 1, True, True)  # the first view may reset the sheet scale
                objs[k] = v
            # 2) real 1:1 sizes -> scale from the ISO series that fits (or the requested one).
            #    Le viste pittoriche possono avere una scala piu' piccola (fino a 1/5) se non stanno alla scala del foglio.
            iso_keys = [k for k in plan_keys if k in (7, 8, 9)]

            def sizes_at(s_, iso=None):
                out = {}
                for k, v in objs.items():
                    ss = (iso[0] / iso[1]) if (iso and k in iso_keys) else s_
                    r = self._view_rect(v)
                    cur = float(v.ScaleDecimal) or 1.0
                    gw, gh = max(r[2] - r[0] - VIEW_PAD, 0.001) / cur, max(r[3] - r[1] - VIEW_PAD, 0.001) / cur
                    out[k] = (gw * ss + VIEW_PAD, gh * ss + VIEW_PAD)
                return out

            def fit_fn(W_, H_, first_):
                cands = [(cn, cd) for cn, cd in STD_SCALES if cn / cd <= 10.0]
                if parsed:
                    cands = [parsed]
                for cn, cd in cands:
                    s_ = cn / cd
                    isos = [None]
                    if iso_keys:
                        isos += [(a_, b_) for a_, b_ in STD_SCALES if s_ / 2.0 - 1e-9 <= a_ / b_ < s_ - 1e-9]   # al massimo un gradino sotto
                    for iso in isos:
                        _, ok = self._plan_layout(W_, H_, first_, plan_keys, sizes_at(s_, iso), gx=gx)
                        if ok:
                            return (cn, cd), iso
                return None

            paper_note = ""
            iso_scale = None
            if getattr(self, "_auto_paper", {}).get(self._get_doc_title(doc)):
                paper, (n, d), iso_scale = self._pick_paper(first, fit_fn, parsed)
                self._apply_paper(doc, paper)
                self._auto_paper[self._get_doc_title(doc)] = False
                W, H, first = self._sheet_dims(doc)
                paper_note = f", foglio {paper} scelto in automatico"
            else:
                f = fit_fn(W, H, first)
                if f:
                    (n, d), iso_scale = f
                else:
                    n, d = parsed or STD_SCALES[-1]
            sheet.SetScale(int(n), int(d), True, True)
            for k, v in objs.items():
                if int(v.Type) == 7:
                    try:
                        if iso_scale and k in iso_keys:
                            self._set_view_scale(v, int(iso_scale[0]), int(iso_scale[1]))
                        else:
                            v.UseSheetScale = True
                    except Exception:
                        pass
            if iso_scale:
                paper_note += f", viste pittoriche in scala {iso_scale[0]}:{iso_scale[1]}"
            # 3) final positions from the real outlines
            real = {k: (self._view_rect(v)[2] - self._view_rect(v)[0],
                        self._view_rect(v)[3] - self._view_rect(v)[1]) for k, v in objs.items()}
            pos2, fits2 = self._plan_layout(W, H, first, plan_keys, real, gx=gx)
            created = []
            for k in order:
                self._set_pos(objs[k], *pos2[k])
            doc.ClearSelection2(True)
            for k in order:
                if k == 1 and drop_front:
                    # front view was only needed as projection parent
                    pass
                created.append({"orientation": next(n_ for n_, i_ in ORIENTATIONS.items() if i_ == k),
                                **self._view_info(objs[k])})
            return self._result(True, f"{len(created)} viste create in scala {n}:{d}{paper_note}",
                                SwErrors.swSuccess,
                                {"scale": f"{n}:{d}", "paper_mm": [self._mm(W), self._mm(H)],
                                 "views": created, "layout_fits": bool(fits2),
                                 "projection": "first_angle" if first else "third_angle",
                                 **({"exploded_failed": explode_failed} if explode_failed else {})})
        except Exception as e:
            return self._fail("add_standard_views", e)

    def _sheet_paper_name(self, doc) -> Tuple[str, str]:
        """(formato A4..A0, orientamento) del foglio attivo dalle sue misure."""
        w, h, _ = self._sheet_dims(doc)
        sw_, sh_ = sorted((w * 1000.0, h * 1000.0))
        best = min(PAPER_MM, key=lambda k: abs(min(PAPER_MM[k]) - sw_) + abs(max(PAPER_MM[k]) - sh_))
        return best, ("portrait" if h > w else "landscape")

    def add_model_view(self, orientation: str = "front", x: float = None, y: float = None,
                       scale=None, model_path: str = None, unit: str = None, exploded: bool = False,
                       new_sheet_if_full: bool = True) -> Dict:
        """One view with the chosen orientation at (x, y). Senza x, y la vista va nel posto libero piu' vicino al centro;
        (A15) se sul foglio non c'e' posto (new_sheet_if_full=True) la vista viene creata su un NUOVO foglio dello stesso formato,
        scala e proiezione (le viste derivate - sezioni, dettagli - devono invece restare sul foglio della madre)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            mpath = self._model_path_for_drawing(doc, model_path)
            if not mpath or not os.path.isfile(mpath):
                return self._result(False, "Modello di riferimento non trovato (passa model_path).",
                                    SwErrors.swInvalidInput)
            vname, _ = self._model_view_name(mpath, orientation)
            if not vname:
                return self._result(False, f"Orientamento sconosciuto: {orientation}",
                                    SwErrors.swInvalidInput)
            W, H, _ = self._sheet_dims(doc)
            auto = x is None or y is None
            px = W / 2 if x is None else self._m(x, unit)
            py = H / 2 if y is None else self._m(y, unit)
            v = doc.CreateDrawViewFromModelView3(mpath, vname, px, py, 0)
            if v is None:
                return self._result(False, "Creazione vista fallita", SwErrors.swUnknownError)
            parsed = self._parse_scale(scale)
            if parsed:
                self._set_view_scale(v, *parsed)
            else:
                try:
                    v.UseSheetScale = True
                except Exception:
                    pass
            if exploded and not self._show_exploded(v, True):
                return self._result(False, f"Vista creata ({self._com(v, 'GetName2')}) ma l'esploso non e' attivabile: il modello "
                                    "deve avere una vista esplosa nella configurazione e il file deve essere stato salvato "
                                    "DOPO averla creata.", SwErrors.swFeatureError, self._view_info(v))
            new_sheet = None
            if auto:
                self._place_free(doc, v, (px, py))
                if not getattr(self, "_last_place_ok", True) and new_sheet_if_full:
                    # foglio affollato: elimino la vista e la ricreo su un nuovo foglio
                    try:
                        sh_old = self._com(doc, "GetCurrentSheet")
                        pr = sh_old.GetProperties2
                        paper, orient = self._sheet_paper_name(doc)
                        scale_txt = f"{pr[2]:g}:{pr[3]:g}"
                        proj = "first" if bool(pr[4]) else "third"
                        old_name = self._com(sh_old, "GetName")
                        self._select_view(doc, v)
                        doc.Extension.DeleteSelection2(0)
                        doc.ClearSelection2(True)
                        names = list(self._com(doc, "GetSheetNames") or ())
                        r_ns = self.add_sheet(name=f"Foglio{len(names) + 1}", paper_size=paper, orientation=orient,
                                              projection=proj, scale=scale_txt)
                        if not r_ns["success"]:
                            return r_ns
                        new_sheet = self._com(self._com(doc, "GetCurrentSheet"), "GetName")
                        W2, H2, _ = self._sheet_dims(doc)
                        px, py = (W2 / 2 if x is None else px), (H2 / 2 if y is None else py)
                        v = doc.CreateDrawViewFromModelView3(mpath, vname, px, py, 0)
                        if v is None:
                            return self._result(False, "Creazione vista sul nuovo foglio fallita", SwErrors.swUnknownError)
                        if parsed:
                            self._set_view_scale(v, *parsed)
                        else:
                            v.UseSheetScale = True
                        if exploded:
                            self._show_exploded(v, True)
                        self._place_free(doc, v, (px, py))
                        self._sheet_ann_cache = None
                    except Exception as e:
                        logger.warning(f"new sheet fallback: {e}")
            doc.ClearSelection2(True)
            return self._result(True, f"Vista creata: {self._com(v, 'GetName2')}" +
                                (f" (foglio pieno: creato il foglio {new_sheet})" if new_sheet else ""),
                                SwErrors.swSuccess, {**self._view_info(v), "new_sheet": new_sheet,
                                                     "sheet": self._com(self._com(doc, "GetCurrentSheet"), "GetName")})
        except Exception as e:
            return self._fail("add_model_view", e)

    _DIRS = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0),
             "up_left": (-1, 1), "up_right": (1, 1), "down_left": (-1, -1), "down_right": (1, -1),
             "sopra": (0, 1), "sotto": (0, -1), "sinistra": (-1, 0), "destra": (1, 0)}

    def add_projected_view(self, parent_view: str = None, direction: str = "right",
                           distance: float = None, unit: str = None) -> Dict:
        """Projected view from a parent view (up/down/left/right or diagonal)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            parent, err = self._find_view(doc, parent_view)
            if err:
                return err
            vec = self._DIRS.get(direction.lower())
            if vec is None:
                return self._result(False, f"Direzione sconosciuta: {direction}. Usa {list(self._DIRS)}",
                                    SwErrors.swInvalidInput)
            ppos = tuple(parent.Position)
            pol = tuple(self._com(parent, "GetOutline"))
            pw, ph = pol[2] - pol[0], pol[3] - pol[1]
            dist = self._m(distance, unit) if distance else 0.025
            tx = ppos[0] + vec[0] * (pw + dist + 0.02)
            ty = ppos[1] + vec[1] * (ph + dist + 0.02)
            self._select_view(doc, parent)
            diagonal = vec[0] != 0 and vec[1] != 0
            v = doc.CreateUnfoldedViewAt3(tx, ty, 0, bool(diagonal))
            if v is None:
                return self._result(False, "Creazione vista proiettata fallita", SwErrors.swUnknownError)
            # tighten the gap now that the child size is known
            try:
                cl = tuple(self._com(v, "GetOutline"))
                cw, ch = cl[2] - cl[0], cl[3] - cl[1]
                nx = ppos[0] + vec[0] * ((pw + cw) / 2.0 + dist) if vec[0] else ppos[0]
                ny = ppos[1] + vec[1] * ((ph + ch) / 2.0 + dist) if vec[1] else ppos[1]
                v.Position = _arr(nx, ny)
            except Exception as e:
                logger.debug(f"reposition failed: {e}")
            doc.ClearSelection2(True)
            return self._result(True, f"Vista proiettata: {self._com(v, 'GetName2')}",
                                SwErrors.swSuccess, self._view_info(v))
        except Exception as e:
            return self._fail("add_projected_view", e)

    # ====================================================================
    # 5. Section view
    # ====================================================================

    def add_section_view(self, parent_view: str = None, orientation: str = "horizontal",
                         offset: float = 0.0, points: List[float] = None, label: str = "A",
                         flip: bool = False, view_x: float = None, view_y: float = None,
                         unit: str = None) -> Dict:
        """Section view from a parent view.

        orientation: 'horizontal' | 'vertical' | 'points'. `offset` is the distance of the
        cut line from the view centre (model units on the sheet scale); `points` =
        [x1, y1, x2, y2] relative to the view centre (used with 'points').
        Sezione a gradini o allineata: orientation='stepped' / 'aligned' con points = poligonale
        [x1,y1,x2,y2,x3,y3,...] (almeno 3 punti, relativi al centro vista, unita' del foglio): segmenti
        orizzontali/verticali collegati = sezione a gradini; un tratto inclinato = sezione allineata (ruotata).
        La vista risultante e' allineata alla madre (stessa direzione della linea) se c'e' posto."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            parent, err = self._find_view(doc, parent_view)
            if err:
                return err
            ppos = tuple(parent.Position)
            pol = tuple(self._com(parent, "GetOutline"))
            hw = (pol[2] - pol[0]) / 2.0 + 0.005
            hh = (pol[3] - pol[1]) / 2.0 + 0.005
            sc = float(parent.ScaleDecimal)
            o = self._m(offset, unit)
            orient = orientation.lower()
            if orient.startswith("h"):
                p1, p2 = (-hw / sc, o), (hw / sc, o)   # sketch coords inside a view = MODEL units
                dflt = (ppos[0], ppos[1] - 2 * hh - 0.04)
            elif orient.startswith("v"):
                p1, p2 = (o, -hh / sc), (o, hh / sc)
                dflt = (ppos[0] + 2 * hw + 0.04, ppos[1])
            elif orient.startswith(("s", "a")):
                if not points or len(points) < 6 or len(points) % 2:
                    return self._result(False, "Servono points=[x1,y1,x2,y2,x3,y3,...] (almeno 3 punti)",
                                        SwErrors.swInvalidInput)
                q = [self._m(p, unit) / sc for p in points]       # coordinate dello schizzo = unita' modello
                poly = [(q[i], q[i + 1]) for i in range(0, len(q), 2)]
                p1, p2 = poly[0], poly[-1]
                # direzione della vista: perpendicolare al primo tratto (verso l'alto/basso o destra/sinistra)
                dx, dy = poly[1][0] - poly[0][0], poly[1][1] - poly[0][1]
                dflt = (ppos[0], ppos[1] - 2 * hh - 0.04) if abs(dx) >= abs(dy) else (ppos[0] + 2 * hw + 0.04, ppos[1])
            elif orient.startswith("p"):
                if not points or len(points) != 4:
                    return self._result(False, "Servono points=[x1,y1,x2,y2]", SwErrors.swInvalidInput)
                q = [self._m(p, unit) for p in points]
                p1, p2 = (q[0], q[1]), (q[2], q[3])
                dflt = (ppos[0], ppos[1] - 2 * hh - 0.04)
            else:
                return self._result(False, f"orientation non valida: {orientation}", SwErrors.swInvalidInput)
            vx = self._m(view_x, unit) if view_x is not None else dflt[0]
            vy = self._m(view_y, unit) if view_y is not None else dflt[1]
            self._select_view(doc, parent)
            doc.ActivateView(self._com(parent, "GetName2"))
            if orient.startswith(("s", "a")):
                segs = []
                for k in range(len(poly) - 1):
                    sg = doc.SketchManager.CreateLine(poly[k][0], poly[k][1], 0, poly[k + 1][0], poly[k + 1][1], 0)
                    if sg is None:
                        self._end_view_sketch(doc)
                        return self._result(False, "Impossibile tracciare la linea di sezione", SwErrors.swUnknownError)
                    segs.append(sg)
                doc.ClearSelection2(True)
                for k, sg in enumerate(segs):
                    sg.Select4(k > 0, self._NULL)
            else:
                seg = doc.SketchManager.CreateLine(p1[0], p1[1], 0, p2[0], p2[1], 0)
                if seg is None:
                    self._end_view_sketch(doc)
                    return self._result(False, "Impossibile tracciare la linea di sezione", SwErrors.swUnknownError)
                doc.ClearSelection2(True)
                seg.Select4(False, self._NULL)
            sv = doc.CreateSectionViewAt5(vx, vy, 0, str(label), 0, self._NULL, 0)
            # NB: creating the section already leaves sketch mode; toggling it again (InsertSketch)
            # re-enters edit mode and the section is drawn without hatch
            doc.ClearSelection2(True)
            if sv is None:
                return self._result(False, "Creazione sezione fallita (la linea deve attraversare il pezzo)",
                                    SwErrors.swUnknownError)
            flipped = None
            if sv is not None and flip:
                # (A13) l'opzione 1 di CreateSectionViewAt5 non inverte nulla: si usa IView.GetSection().SetReversedCutDirection(True)
                # (le frecce della linea di sezione si girano e la vista mostra il lato opposto, verificato guardando il rendering)
                try:
                    sec = sv.GetSection
                    sec.SetReversedCutDirection(True)
                    doc.ForceRebuild3(False)
                    flipped = bool(sec.GetReversedCutDirection)
                except Exception as e:
                    logger.warning(f"flip sezione: {e}")
                    flipped = False
            if sv is not None and view_x is None and view_y is None:
                # slide along the alignment axis to the nearest free area
                if orient.startswith(("s", "a")):
                    horizontal_cut = abs(poly[1][0] - poly[0][0]) >= abs(poly[1][1] - poly[0][1])
                else:
                    horizontal_cut = abs(p2[0] - p1[0]) >= abs(p2[1] - p1[1])
                self._place_free(doc, sv, ppos, axis="y" if horizontal_cut else "x")
                no_room = not self._last_place_ok
            else:
                no_room = False
            return self._result(True, f"Sezione {label}-{label}: {self._com(sv, 'GetName2')}" +
                                (" - ATTENZIONE: nessuno spazio libero, la vista si sovrappone" if no_room else ""),
                                SwErrors.swSuccess, {**self._view_info(sv), "placed_in_free_space": not no_room,
                                                     "flip_requested": bool(flip), "reversed_cut_direction": flipped,
                                                     "view_rotation": [round(float(t), 3) for t in sv.ModelToViewTransform.ArrayData[:9]]})
        except Exception as e:
            return self._fail("add_section_view", e)

    # ====================================================================
    # 6. Detail view
    # ====================================================================

    def add_detail_view(self, parent_view: str = None, center_x: float = 0.0, center_y: float = 0.0,
                        radius: float = 10.0, label: str = "B", scale=None,
                        view_x: float = None, view_y: float = None, unit: str = None) -> Dict:
        """Detail view from a circle (centre relative to the parent view centre, radius)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            parent, err = self._find_view(doc, parent_view)
            if err:
                return err
            ppos = tuple(parent.Position)
            pol = tuple(self._com(parent, "GetOutline"))
            sc = float(parent.ScaleDecimal)
            cx = self._m(center_x, unit)
            cy = self._m(center_y, unit)
            r = self._m(radius, unit)
            parsed = self._parse_scale(scale) or (max(int(round(2 * 1)), 2), 1)
            if not scale:
                # default: twice the parent scale, expressed as a ratio
                ratio = sc * 2
                parsed = self._parse_scale(ratio if ratio >= 1 else f"1:{int(round(1/ratio))}")
            n, d = parsed
            vx = self._m(view_x, unit) if view_x is not None else pol[2] + 0.06
            vy = self._m(view_y, unit) if view_y is not None else ppos[1]
            self._select_view(doc, parent)
            doc.ActivateView(self._com(parent, "GetName2"))
            circ = doc.SketchManager.CreateCircleByRadius(cx, cy, 0, r)
            if circ is None:
                self._end_view_sketch(doc)
                return self._result(False, "Impossibile tracciare il cerchio di dettaglio", SwErrors.swUnknownError)
            doc.ClearSelection2(True)
            circ.Select4(False, self._NULL)
            dv = doc.CreateDetailViewAt4(vx, vy, 0, 0, float(n), float(d), str(label), 0,
                                         True, False, False, 0)
            self._end_view_sketch(doc)
            if dv is None:
                return self._result(False, "Creazione vista di dettaglio fallita", SwErrors.swUnknownError)
            try:
                if abs(float(dv.ScaleDecimal) - n / d) > 1e-6:
                    self._set_view_scale(dv, int(n), int(d))
                doc.ForceRebuild3(False)
            except Exception:
                pass
            if not hasattr(self, "_detail_circles"):
                self._detail_circles = {}
            self._detail_circles.setdefault(self._get_doc_title(doc), []).append(
                (self._com(parent, "GetName2"), ppos[0] + cx * sc, ppos[1] + cy * sc, r * sc))
            placed = True
            if view_x is None and view_y is None:
                placed, used = self._fit_view_free(doc, dv, (ppos[0] + 0.15, ppos[1]), sc)
            return self._result(True, f"Dettaglio {label}: {self._com(dv, 'GetName2')}" +
                                ("" if placed else " - ATTENZIONE: nessuno spazio libero, la vista si sovrappone"),
                                SwErrors.swSuccess, {**self._view_info(dv), "placed_in_free_space": placed})
        except Exception as e:
            return self._fail("add_detail_view", e)

    # ====================================================================
    # 7-8. Broken-out section, break view, auxiliary view, crop view
    # ====================================================================

    def add_broken_out_section(self, parent_view: str = None, x1: float = -10, y1: float = -10,
                               x2: float = 10, y2: float = 10, depth: float = 5.0,
                               unit: str = None) -> Dict:
        """Broken-out section: rectangle (relative to view centre) cut down to `depth`
        (measured from the model's front face of the view)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            parent, err = self._find_view(doc, parent_view)
            if err:
                return err
            sc = float(parent.ScaleDecimal)
            q = [self._m(v, unit)  for v in (x1, y1, x2, y2)]
            self._select_view(doc, parent)
            doc.ActivateView(self._com(parent, "GetName2"))
            segs = doc.SketchManager.CreateCornerRectangle(q[0], q[1], 0, q[2], q[3], 0)
            doc.ClearSelection2(True)
            for i, sgm in enumerate(segs or ()):
                sgm.Select4(i > 0, self._NULL)
            ok = doc.CreateBreakoutSection(self._m(depth, unit))
            self._end_view_sketch(doc)
            if not ok:
                return self._result(False, "Creazione sezione locale fallita", SwErrors.swUnknownError)
            return self._result(True, "Sezione locale creata", SwErrors.swSuccess,
                                {"parent": self._com(parent, "GetName2")})
        except Exception as e:
            return self._fail("add_broken_out_section", e)

    def add_break_view(self, parent_view: str = None, orientation: str = "vertical",
                       position1: float = -10, position2: float = 10, style: int = 3,
                       unit: str = None) -> Dict:
        """Break view: toglie la parte fra due linee di interruzione e avvicina i due pezzi (vista davvero accorciata).
        Posizioni relative al centro vista (spazio foglio). orientation: 'vertical' (linee verticali: accorcia la larghezza) o
        'horizontal'. style: 0 retta, 1 a zig-zag, 2 curva (spline)...
        NB: IView.InsertBreak da' solo le linee tratteggiate; la vista si accorcia con IDrawingDoc.BreakView() (vista selezionata);
        GetOutline resta vecchio finche' la grafica non e' ridisegnata (GraphicsRedraw2)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            parent, err = self._find_view(doc, parent_view)
            if err:
                return err
            before = self._view_rect(parent)
            self._select_view(doc, parent)
            ori = 2 if orientation.lower().startswith("v") else 1       # swBreakLineOrientation: 1 = linee orizzontali, 2 = verticali
            bl = parent.InsertBreak(ori, self._m(position1, unit), self._m(position2, unit), int(style))
            if bl is None:
                doc.ClearSelection2(True)
                return self._result(False, "Vista interrotta non creata (posizioni fuori dalla vista?)",
                                    SwErrors.swUnknownError)
            self._select_view(doc, parent)
            doc.BreakView()
            doc.ClearSelection2(True)
            try:
                doc.GraphicsRedraw2()
            except Exception:
                pass
            after = self._view_rect(parent)
            if abs((after[2] - after[0]) - (before[2] - before[0])) < 1e-4 and abs((after[3] - after[1]) - (before[3] - before[1])) < 1e-4:
                # il contorno non e' ancora aggiornato: forza il ridisegno con un'esportazione temporanea
                tmp = os.path.join(os.environ.get("TEMP", "."), "swmcp_break_probe.png")
                try:
                    self._save_as(doc, tmp)
                    os.remove(tmp)
                except Exception:
                    pass
                after = self._view_rect(parent)
            info = self._view_info(parent)
            info.update({"outline_before_mm": [self._mm(t) for t in before], "outline_after_mm": [self._mm(t) for t in after],
                         "shortened_mm": round(((before[2] - before[0]) - (after[2] - after[0]) if ori == 2
                                                else (before[3] - before[1]) - (after[3] - after[1])) * 1000.0, 2)})
            return self._result(True, f"Vista interrotta: accorciata di {info['shortened_mm']} mm", SwErrors.swSuccess, info)
        except Exception as e:
            return self._fail("add_break_view", e)

    def add_crop_view(self, parent_view: str = None, center_x: float = 0.0, center_y: float = 0.0,
                      radius: float = 20.0, unit: str = None, shape: str = "circle", width: float = None,
                      height: float = None, points: List[float] = None) -> Dict:
        """Crop view: ritaglia la vista con un profilo chiuso. shape: 'circle' (centro + radius), 'rectangle' (centro + width x
        height) o 'polygon' (points=[x1,y1,x2,y2,...], almeno 3 punti). Coordinate relative al centro della vista, in unita' del MODELLO
        (non scalate), come per le viste di dettaglio."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            parent, err = self._find_view(doc, parent_view)
            if err:
                return err
            sh = str(shape or "circle").lower()
            if sh in ("rect", "rectangle", "rettangolo"):
                sh = "rectangle"
            elif sh in ("poly", "polygon", "poligono"):
                sh = "polygon"
            elif sh not in ("circle", "cerchio"):
                return self._result(False, "shape: circle | rectangle | polygon", SwErrors.swInvalidInput)
            else:
                sh = "circle"
            before = self._view_rect(parent)
            self._select_view(doc, parent)
            doc.ActivateView(self._com(parent, "GetName2"))
            cx, cy = self._m(center_x, unit), self._m(center_y, unit)
            sk = doc.SketchManager
            made = []
            if sh == "circle":
                circ = sk.CreateCircleByRadius(cx, cy, 0, self._m(radius, unit))
                made = [circ] if circ is not None else []
            elif sh == "rectangle":
                if not width or not height:
                    self._end_view_sketch(doc)
                    return self._result(False, "Servono width e height", SwErrors.swInvalidInput)
                hw, hh = self._m(width, unit) / 2.0, self._m(height, unit) / 2.0
                segs = sk.CreateCornerRectangle(cx - hw, cy - hh, 0, cx + hw, cy + hh, 0)
                made = list(segs or ())
            else:
                if not points or len(points) < 6 or len(points) % 2:
                    self._end_view_sketch(doc)
                    return self._result(False, "Servono points=[x1,y1,x2,y2,x3,y3,...] (almeno 3 punti)", SwErrors.swInvalidInput)
                q = [self._m(t, unit) for t in points]
                poly = [(q[k], q[k + 1]) for k in range(0, len(q), 2)]
                for k in range(len(poly)):
                    a_, b_ = poly[k], poly[(k + 1) % len(poly)]
                    sg = sk.CreateLine(a_[0], a_[1], 0, b_[0], b_[1], 0)
                    if sg is not None:
                        made.append(sg)
            doc.ClearSelection2(True)
            if not made:
                self._end_view_sketch(doc)
                return self._result(False, "Profilo di ritaglio non tracciato", SwErrors.swUnknownError)
            for k, sg in enumerate(made):
                sg.Select4(k > 0, self._NULL)
            parent.Crop
            self._end_view_sketch(doc)
            if not parent.IsCropped:
                return self._result(False, "Ritaglio non applicato", SwErrors.swUnknownError)
            after = self._view_rect(parent)
            info = self._view_info(parent)
            info.update({"shape": sh, "cropped": True,
                         "outline_before_mm": [self._mm(t) for t in before], "outline_after_mm": [self._mm(t) for t in after]})
            return self._result(True, f"Vista ritagliata ({sh})", SwErrors.swSuccess, info)
        except Exception as e:
            return self._fail("add_crop_view", e)

    # ====================================================================
    # 9. Dimensions
    # ====================================================================

    def _count_dims(self, view) -> int:
        n = 0
        x = view.GetFirstDisplayDimension5
        while x is not None:
            n += 1
            x = x.GetNext3
        return n

    def insert_model_dimensions(self, view: str = None, all_views: bool = False,
                                include_hidden_feature_dims: bool = True, arrange: bool = True) -> Dict:
        """Import the model dimensions into the view (or all views). Le quote degli schizzi assorbiti da una
        feature (estrusione, rivoluzione...) sono 'nascoste': senza include_hidden_feature_dims=True non vengono
        importate (verificato: flangia 0 quote -> 2)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            if all_views:
                targets = self._sheet_views(doc)
            else:
                v, err = self._find_view(doc, view)
                if err:
                    return err
                targets = [v]
            before = {self._com(v, "GetName2"): self._count_dims(v) for v in self._sheet_views(doc)}
            skipped = [self._com(v, "GetName2") for v in targets if self._is_pictorial(v)]
            targets = [v for v in targets if not self._is_pictorial(v)]
            if not targets:
                return self._result(False, "Nessuna quota sulle viste isometriche/pittoriche: scegli una vista ortogonale.",
                                    SwErrors.swInvalidInput, {"skipped": skipped})
            for v in targets:
                try:       # (A7) assiemi: le quote dei vincoli non sono quote da disegno: si importano solo per i pezzi
                    if int(v.ReferencedDocument.GetType) == DOC_ASSEMBLY:
                        continue
                except Exception:
                    pass
                self._select_view(doc, v)
                # option 0 = selected view; 32776 = dimensions + dimensions marked for drawing
                doc.InsertModelAnnotations3(0, 32776, False, True, bool(include_hidden_feature_dims), True)
            doc.ClearSelection2(True)
            removed = sum(self._remove_duplicate_dims(doc, v) for v in targets)
            for v in targets:
                self._tidy_dims(doc, v)
            after = {self._com(v, "GetName2"): self._count_dims(v) for v in self._sheet_views(doc)}
            added = {k: after[k] - before.get(k, 0) for k in after}
            extra = {}
            msg = f"Quote inserite: {sum(added.values())}"
            if arrange:
                out = self._dq_run(doc, targets)
                final = {self._com(v, "GetName2"): self._count_dims(v) for v in self._sheet_views(doc)}
                dia = out["cleanup"].get("diameters", {})
                extra = {"arranged": True, "final_per_view": final, "chamfer_note": out["cleanup"].get("chamfer_note", []),
                         "duplicates_removed_by_layout": out["cleanup"].get("duplicates", 0),
                         "chamfer_dims_removed": out["cleanup"].get("chamfer", 0),
                         "diameter_dims_added": len(dia.get("added", [])), "radial_dims_removed": dia.get("removed", 0),
                         "overall_dims_added": len(dia.get("overall", [])), "hole_dims_added": len(dia.get("holes", [])),
                         "pocket_dims_added": len(dia.get("pockets", [])), "pocket_dims": dia.get("pockets", [])}
                msg += f" (poi riordinate: {sum(final.values())} quote finali)"
            return self._result(True, msg, SwErrors.swSuccess,
                                {"added_per_view": added, "total_per_view": after,
                                 "duplicates_removed": removed, "skipped_pictorial": skipped, **extra})
        except Exception as e:
            return self._fail("insert_model_dimensions", e)

    def auto_dimension(self, view: str = None, scheme: str = "baseline",
                       horizontal_placement: str = "above", vertical_placement: str = "right",
                       tidy: bool = True) -> Dict:
        """Automatic dimensioning of a view (IDrawingDoc.AutoDimension)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            v, err = self._find_view(doc, view)
            if err:
                return err
            sch = {"baseline": 0, "chain": 1, "ordinate": 2}.get(scheme.lower())
            if sch is None:
                return self._result(False, "scheme: baseline|chain|ordinate", SwErrors.swInvalidInput)
            hp = 1 if horizontal_placement.lower().startswith(("b", "s")) else 0
            vp = 1 if vertical_placement.lower().startswith(("l", "s")) else 0
            if self._is_pictorial(v):
                return self._result(False, "Nessuna quota sulle viste isometriche/pittoriche: scegli una vista ortogonale.",
                                    SwErrors.swInvalidInput)
            before = self._count_dims(v)
            self._select_view(doc, v)
            ok = doc.AutoDimension(0, sch, hp, sch, vp)
            doc.ClearSelection2(True)
            removed = self._remove_duplicate_dims(doc, v)
            if tidy:
                try:        # disposizione ISO 129 (stesso motore di insert_model_dimensions)
                    self._dq_run(doc, [v])
                except Exception as e:
                    logger.warning(f"arrange after auto_dimension failed ({e}): old tidy")
                    self._tidy_dims(doc, v)
            added = self._count_dims(v) - before
            if not ok and added <= 0:
                return self._result(False, "AutoDimension non ha inserito quote", SwErrors.swUnknownError)
            return self._result(True, f"Quote automatiche inserite: {added}", SwErrors.swSuccess,
                                {"view": self._com(v, "GetName2"), "added": added,
                                 "duplicates_removed": removed, "total": self._count_dims(v)})
        except Exception as e:
            return self._fail("auto_dimension", e)

    # ====================================================================
    # 10. Annotations
    # ====================================================================

    def add_center_marks(self, view: str = None, mode: str = "auto",
                         edge1: List[float] = None, edge2: List[float] = None,
                         unit: str = None) -> Dict:
        """mode 'auto': centre marks/axes on all circular edges of the view;
        mode 'centerline': axis between two edges given as points [x, y] on the sheet."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            if mode.lower().startswith("c"):
                if not edge1 or not edge2:
                    return self._result(False, "Servono edge1=[x,y] e edge2=[x,y] (punti sugli spigoli)",
                                        SwErrors.swInvalidInput)
                doc.ClearSelection2(True)
                ok1 = doc.Extension.SelectByID2("", "EDGE", self._m(edge1[0], unit), self._m(edge1[1], unit),
                                                0, False, 1, self._NULL, 0)
                ok2 = doc.Extension.SelectByID2("", "EDGE", self._m(edge2[0], unit), self._m(edge2[1], unit),
                                                0, True, 1, self._NULL, 0)
                if not (ok1 and ok2):
                    return self._result(False, "Spigoli non trovati nei punti indicati", SwErrors.swInvalidInput)
                r = doc.InsertCenterLine2
                doc.ClearSelection2(True)
                return self._result(r is not None, "Asse inserito" if r is not None else "Asse non inserito",
                                    SwErrors.swSuccess if r is not None else SwErrors.swUnknownError)
            v, err = self._find_view(doc, view)
            if err:
                return err
            ok = v.AutoInsertCenterMarks(1, 0, True, True, True, True, True, True, True)
            return self._result(bool(ok), "Centri e assi inseriti" if ok else "Nessun centro da inserire",
                                SwErrors.swSuccess if ok else SwErrors.swUnknownError,
                                {"view": self._com(v, "GetName2")})
        except Exception as e:
            return self._fail("add_center_marks", e)

    def add_note(self, text: str, x: float = 50, y: float = 50, height: float = 3.5,
                 unit: str = None) -> Dict:
        """Free text note on the sheet; `height` = character height."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            if not text:
                return self._result(False, "text e' obbligatorio", SwErrors.swInvalidInput)
            note = doc.CreateText2(text, self._m(x, unit), self._m(y, unit), 0, self._m(height, unit), 0)
            if note is None:
                return self._result(False, "Nota non creata", SwErrors.swUnknownError)
            return self._result(True, f"Nota creata: {text[:40]}", SwErrors.swSuccess,
                                {"text": self._com(note, "GetText")})
        except Exception as e:
            return self._fail("add_note", e)

    def _select_edge_at(self, doc, x, y, unit) -> bool:
        """Seleziona lo spigolo (o la silhouette) nel punto del foglio; piccoli scarti perche' la zona sensibile
        delle silhouette e' spostata verso l'esterno."""
        xm, ym = self._m(x, unit), self._m(y, unit)
        sm = doc.SelectionManager
        for typ in ("EDGE", "SILEDGE"):
            for dx, dy in ((0, 0), (0.0003, 0), (-0.0003, 0), (0, 0.0003), (0, -0.0003), (0.0002, 0.0002),
                           (-0.0002, -0.0002), (0.0005, 0), (-0.0005, 0), (0, 0.0005), (0, -0.0005)):
                doc.ClearSelection2(True)
                if doc.Extension.SelectByID2("", typ, xm + dx, ym + dy, 0, False, 0, self._NULL, 0):
                    n = sm.GetSelectedObjectCount2(-1)
                    if n and int(sm.GetSelectedObjectType3(n, -1)) in (1, 46):
                        return True
        doc.ClearSelection2(True)
        return False

    def add_surface_finish(self, x: float = 100, y: float = 100, symbol: str = "machining_required",
                           roughness: str = "3.2", edge_x: float = None, edge_y: float = None,
                           unit: str = None) -> Dict:
        """Surface finish symbol (roughness in um). If edge_x/edge_y are given the symbol is
        attached to the edge passing through that sheet point (with a leader)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            sym = {"basic": 0, "machining_required": 1, "no_machining": 2}.get(symbol.lower())
            if sym is None:
                return self._result(False, "symbol: basic|machining_required|no_machining", SwErrors.swInvalidInput)
            leader = 0
            if edge_x is not None and edge_y is not None:
                if not self._select_edge_at(doc, edge_x, edge_y, unit):
                    return self._result(False, "Spigolo non trovato", SwErrors.swInvalidInput)
                leader = 1
            else:
                doc.ClearSelection2(True)
            # roughness is stored in metres by the API for max_roughness
            r = doc.Extension.InsertSurfaceFinishSymbol3(sym, leader, self._m(x, unit), self._m(y, unit), 0,
                                                         0, 0, "", "", "", "", str(roughness), "", "")
            doc.ClearSelection2(True)
            if r is None:
                return self._result(False, "Simbolo non creato", SwErrors.swUnknownError)
            if not leader:
                try:       # senza richiamo l'API ignora X,Y: il simbolo va portato nel punto indicato
                    r.GetAnnotation.SetPosition2(self._m(x, unit), self._m(y, unit), 0)
                except Exception:
                    pass
            return self._result(True, f"Finitura superficiale Ra {roughness} inserita", SwErrors.swSuccess)
        except Exception as e:
            return self._fail("add_surface_finish", e)

    def add_datum(self, label: str = "A", edge_x: float = 0, edge_y: float = 0, unit: str = None,
                  view: str = None, model_point: List[float] = None, on_dimension: str = None) -> Dict:
        """Riferimento (datum) con lettera AGGANCIATO a una feature: a uno spigolo (punto in coordinate foglio edge_x/edge_y, oppure
        punto del modello model_point=[x,y,z] mm visto nella vista `view`) con linea di richiamo, oppure alla quota
        on_dimension (nome/testo/valore: tipico dei riferimenti su un diametro). Il simbolo e' collocato subito accanto al bersaglio."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            kind, target, trect, away = "edge", None, None, None
            doc.ClearSelection2(True)
            if on_dimension:
                found = self._an_find_dim(doc, on_dimension, view)
                if not found:
                    return self._result(False, f"Quota '{on_dimension}' non trovata", SwErrors.swInvalidInput)
                dd, dim, vv = found
                if not doc.Extension.SelectByID2(str(dd.GetNameForSelection), "DIMENSION", 0, 0, 0, False, 0, self._NULL, 0):
                    return self._result(False, "Quota non selezionabile", SwErrors.swInvalidInput)
                kind = "dimension"
                trect = self._dq_read(vv, dd)["trect"]
            else:
                if model_point is not None:
                    pt, vv = self._an_model_point_to_sheet(doc, view, model_point, unit)
                    if pt is None:
                        return self._result(False, f"Vista '{view}' non trovata", SwErrors.swInvalidInput)
                    edge_x, edge_y, unit = pt[0] * 1000.0, pt[1] * 1000.0, "mm"
                    c_ = self._view_rect(vv)
                    away = ((c_[0] + c_[2]) / 2.0, (c_[1] + c_[3]) / 2.0)
                if not self._select_edge_at(doc, edge_x, edge_y, unit):
                    return self._result(False, "Spigolo non trovato nel punto indicato", SwErrors.swInvalidInput)
                target = (self._m(edge_x, unit), self._m(edge_y, unit))
                if away is None:
                    for v_ in self._sheet_views(doc):
                        r_ = self._view_rect(v_)
                        if r_[0] <= target[0] <= r_[2] and r_[1] <= target[1] <= r_[3]:
                            away = ((r_[0] + r_[2]) / 2.0, (r_[1] + r_[3]) / 2.0)
                            break
            tag = doc.InsertDatumTag2
            doc.ClearSelection2(True)
            if tag is None:
                return self._result(False, "Riferimento non creato", SwErrors.swUnknownError)
            tag.SetLabel(str(label))
            moved = False
            try:
                spot = self._an_place_near(doc, 0.010, 0.010, trect if kind == "dimension" else target, kind, away, trect)
                if spot:
                    tag.GetAnnotation.SetPosition2(spot[0], spot[1], 0)
                    moved = True
            except Exception as e:
                logger.debug(f"datum place: {e}")
            self._sheet_ann_cache = None
            ann = tag.GetAnnotation
            return self._result(True, f"Riferimento {label} inserito su {'quota' if kind == 'dimension' else 'spigolo'}", SwErrors.swSuccess,
                                {"label": self._com(tag, "GetLabel"), "attached_to": kind, "leaders": int(ann.GetLeaderCount),
                                 "placed_near_target": moved,
                                 "position_mm": [round(t * 1000, 2) for t in ann.GetPosition][:2],
                                 "target_mm": [round(t * 1000, 2) for t in (target or ((trect[0] + trect[2]) / 2.0, (trect[1] + trect[3]) / 2.0))]})
        except Exception as e:
            return self._fail("add_datum", e)

    # caratteristiche geometriche -> nome del simbolo nella libreria GTOL di SolidWorks (<GTOL-NOME>).
    # Verificato guardando il rendering: i nomi della libreria gtol97.sym funzionano nel formato <GTOL-NOME>.
    _GTOL_SYMBOLS = {
        "flatness": "FLAT", "planarity": "FLAT", "planarita": "FLAT",
        "straightness": "STRAIGHT", "rettilineita": "STRAIGHT",
        "circularity": "CIRC", "roundness": "CIRC", "circolarita": "CIRC",
        "cylindricity": "CYL", "cilindricita": "CYL",
        "parallelism": "PARA", "parallelismo": "PARA",
        "perpendicularity": "PERP", "perpendicolarita": "PERP",
        "angularity": "ANGULAR", "inclinazione": "ANGULAR",
        "position": "POSI", "posizione": "POSI",
        "concentricity": "CONC", "coaxiality": "CONC", "concentricita": "CONC", "coassialita": "CONC",
        "symmetry": "SYMMETRY", "simmetria": "SYMMETRY",
        "circular_runout": "SRUN", "runout": "SRUN", "oscillazione_circolare": "SRUN",
        "total_runout": "TRUN", "oscillazione_totale": "TRUN",
        "profile_line": "LPROF", "line_profile": "LPROF", "profilo_linea": "LPROF",
        "profile_surface": "SPROF", "profile": "SPROF", "surface_profile": "SPROF", "profilo": "SPROF",
        "profilo_superficie": "SPROF",
    }
    _GTOL_MODS = {"M": "<MOD-MMC>", "MMC": "<MOD-MMC>", "L": "<MOD-LMC>", "LMC": "<MOD-LMC>",
                  "S": "<MOD-FMC>", "F": "<MOD-FREES>", "P": "<MOD-PTZ>", "T": "<MOD-TANP>"}

    def _gtol_symbol(self, name: str) -> Optional[str]:
        key = re.sub(r"[\s\-]+", "_", str(name or "").strip().lower())
        for a_, b_ in (("\u00e0", "a"), ("\u00e1", "a"), ("\u00e8", "e"), ("\u00e9", "e"), ("\u00ec", "i"),
                       ("\u00f2", "o"), ("\u00f9", "u")):
            key = key.replace(a_, b_)
        if key in self._GTOL_SYMBOLS:
            return "<GTOL-" + self._GTOL_SYMBOLS[key] + ">"
        up = str(name or "").strip().upper()
        if up in set(self._GTOL_SYMBOLS.values()):
            return "<GTOL-" + up + ">"
        return None

    def add_geometric_tolerance(self, edge_x: float = None, edge_y: float = None, tolerance: str = "0.1",
                                datum_refs: List[str] = None, diameter: bool = False,
                                x: float = None, y: float = None, unit: str = None,
                                characteristic: str = "position", material_condition: str = None,
                                extra_frames: List[Dict] = None, view: str = None, model_point: List[float] = None,
                                on_dimension: str = None) -> Dict:
        """Riquadro di tolleranza geometrica completo: simbolo della caratteristica (planarita, rettilineita,
        circolarita, cilindricita, parallelismo, perpendicolarita, inclinazione, posizione, concentricita,
        simmetria, oscillazione circolare/totale, profilo di linea/superficie), valore, modificatore del valore
        (Ø, M = massimo materiale, L = minimo materiale, S, P), fino a 3 riferimenti. Se edge_x/edge_y indicano
        un punto su uno spigolo il riquadro e' agganciato con una linea di richiamo, altrimenti e' libero in
        (x, y). extra_frames: altri riquadri sotto il primo, ciascuno {characteristic, tolerance, datum_refs,
        diameter, material_condition} (tolleranze composte).
        (A2) AGGANCIO alla feature: on_dimension = nome/testo/valore di una quota (il riquadro e' legato alla quota e posto
        accanto al suo testo); model_point = [x,y,z] mm di un punto su uno spigolo/silhouette del modello visto nella vista `view`
        (linea di richiamo con freccia sullo spigolo, riquadro vicino al punto, fuori dal contorno); edge_x/edge_y = punto in
        coordinate foglio. Senza nessuno dei tre il riquadro e' libero (sconsigliato in una tavola d'esame)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            sym = self._gtol_symbol(characteristic)
            if sym is None:
                return self._result(False, f"characteristic non riconosciuta: {characteristic}. Valide: "
                                    + ", ".join(sorted(set(self._GTOL_SYMBOLS))), SwErrors.swInvalidInput)
            frames = [{"characteristic": characteristic, "tolerance": tolerance, "datum_refs": datum_refs,
                       "diameter": diameter, "material_condition": material_condition}]
            for f in (extra_frames or []):
                frames.append(f)
            for f in frames:
                if self._gtol_symbol(f.get("characteristic")) is None:
                    return self._result(False, f"characteristic non riconosciuta: {f.get('characteristic')}",
                                        SwErrors.swInvalidInput)
                mc = f.get("material_condition")
                if mc and str(mc).upper() not in self._GTOL_MODS:
                    return self._result(False, f"material_condition: {list(self._GTOL_MODS)}", SwErrors.swInvalidInput)
            doc.ClearSelection2(True)
            attached = False
            kind, target, trect, away = None, None, None, None
            if on_dimension:
                found = self._an_find_dim(doc, on_dimension, view)
                if not found:
                    return self._result(False, f"Quota '{on_dimension}' non trovata", SwErrors.swInvalidInput)
                dd_, dim_, vv_ = found
                if not doc.Extension.SelectByID2(str(dd_.GetNameForSelection), "DIMENSION", 0, 0, 0, False, 0, self._NULL, 0):
                    return self._result(False, "Quota non selezionabile", SwErrors.swInvalidInput)
                attached, kind = True, "dimension"
                i_ = self._dq_read(vv_, dd_)
                trect = i_["trect"]
                fr_ = i_.get("full_rect")
                if trect and fr_:       # testo + linea di quota (estensione verticale della quota): il riquadro non tocca la linea
                    trect = (trect[0], min(trect[1], fr_[1]), trect[2], max(trect[3], fr_[3])) if i_.get("axis") == "H" else                         (min(trect[0], fr_[0]), trect[1], max(trect[2], fr_[2]), trect[3])
            else:
                if model_point is not None:
                    pt_, vv_ = self._an_model_point_to_sheet(doc, view, model_point, unit)
                    if pt_ is None:
                        return self._result(False, f"Vista '{view}' non trovata", SwErrors.swInvalidInput)
                    edge_x, edge_y, unit = pt_[0] * 1000.0, pt_[1] * 1000.0, "mm"
                    c_ = self._view_rect(vv_)
                    away = ((c_[0] + c_[2]) / 2.0, (c_[1] + c_[3]) / 2.0)
                if edge_x is not None and edge_y is not None:
                    if not self._select_edge_at(doc, edge_x, edge_y, unit):
                        return self._result(False, "Spigolo non trovato nel punto indicato", SwErrors.swInvalidInput)
                    attached, kind = True, "edge"
                    target = (self._m(edge_x, unit), self._m(edge_y, unit))
                    if away is None:
                        for v_ in self._sheet_views(doc):
                            r_ = self._view_rect(v_)
                            if r_[0] <= target[0] <= r_[2] and r_[1] <= target[1] <= r_[3]:
                                away = ((r_[0] + r_[2]) / 2.0, (r_[1] + r_[3]) / 2.0)
                                break
            g = doc.InsertGtol
            doc.ClearSelection2(True)
            if g is None:
                return self._result(False, "Tolleranza non creata", SwErrors.swUnknownError)
            done = []
            for k, f in enumerate(frames, start=1):
                if k > 1:
                    g.AddFrame
                refs = (list(f.get("datum_refs") or []) + ["", "", ""])[:3]
                mc = f.get("material_condition")
                g.SetFrameSymbols2(k, self._gtol_symbol(f["characteristic"]), bool(f.get("diameter")),
                                   self._GTOL_MODS[str(mc).upper()] if mc else "", False, "", "", "", "")
                g.SetFrameValues2(k, str(f.get("tolerance", "")), "", str(refs[0]), str(refs[1]), str(refs[2]))
                done.append({"symbol": str(g.GetFrameSymbols2(k)[0]), "tolerance": str(f.get("tolerance")),
                             "datum_refs": [r for r in refs if r]})
            near_ok = None
            if x is not None and y is not None:
                g.GetAnnotation.SetPosition2(self._m(x, unit), self._m(y, unit), 0)
            elif attached:
                # (A2) vicino al bersaglio: accanto al testo della quota, oppure fuori dal contorno presso il punto dello spigolo
                try:
                    w_, h_ = self._an_frame_size(frames)
                    spot = self._an_place_near(doc, w_, h_, trect if kind == "dimension" else target, kind, away, trect)
                    near_ok = bool(spot)
                    if spot:
                        g.GetAnnotation.SetPosition2(spot[0], spot[1], 0)
                except Exception as e:
                    logger.debug(f"gtol near placement: {e}")
            elif not attached:
                # riquadro libero senza posizione: in un'area libera del foglio (centro del riquadro sullo spot)
                try:
                    # misura analitica del riquadro (la geometria letta dall'API si aggiorna solo piu' tardi):
                    # 7 mm per riquadro in altezza; celle: simbolo 7 mm + valore + 7 mm per riferimento
                    w_, h_ = 0.0, 0.007 * len(frames)
                    for f in frames:
                        refs_n = len([r for r in (f.get("datum_refs") or []) if r])
                        vw = 0.0023 * len(str(f.get("tolerance", ""))) + 0.006 + (0.0045 if f.get("diameter") else 0.0)                             + (0.006 if f.get("material_condition") else 0.0)
                        w_ = max(w_, 0.007 + vw + 0.007 * refs_n)
                    W_, H_, _ = self._sheet_dims(doc)
                    spot = self._an_free_spot(doc, w_ + 0.008, h_ + 0.008, (0.06, 0.45 * H_))
                    if spot:
                        g.GetAnnotation.SetPosition2(spot[0] - w_ / 2.0, spot[1] + h_ / 2.0, 0)   # posizione = angolo in alto a sinistra
                except Exception as e:
                    logger.debug(f"gtol free placement: {e}")
            return self._result(True, f"Tolleranza geometrica {characteristic} {tolerance}"
                                + (f" {' '.join(r for r in (datum_refs or []))}" if datum_refs else ""),
                                SwErrors.swSuccess, {"frames": done, "attached_to_edge": attached and kind == "edge",
                                                     "attached_to": kind, "placed_near_target": near_ok,
                                                     "leaders": int(g.GetAnnotation.GetLeaderCount),
                                                     "position_mm": [round(t * 1000, 2) for t in g.GetAnnotation.GetPosition][:2],
                                                     "target_mm": [round(t * 1000, 2) for t in (target or (((trect[0] + trect[2]) / 2.0, (trect[1] + trect[3]) / 2.0) if trect else (0, 0)))],
                                                     "frame_count": int(g.GetFrameCount)})
        except Exception as e:
            return self._fail("add_geometric_tolerance", e)

    def add_hole_callout(self, edge_x: float = 0, edge_y: float = 0, x: float = None, y: float = None,
                         unit: str = None) -> Dict:
        """Hole callout on the circular edge through (edge_x, edge_y), text placed at (x, y)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            if not self._select_edge_at(doc, edge_x, edge_y, unit):
                return self._result(False, "Spigolo non trovato nel punto indicato", SwErrors.swInvalidInput)
            px = self._m(x if x is not None else edge_x + 15, unit)
            py = self._m(y if y is not None else edge_y + 15, unit)
            r = doc.AddHoleCallout2(px, py, 0)
            doc.ClearSelection2(True)
            if r is None:
                return self._result(False, "Quota foro non creata (serve un foro/cerchio)", SwErrors.swUnknownError)
            removed = sum(self._remove_duplicate_dims(doc, v) for v in self._sheet_views(doc)
                          if not self._is_pictorial(v))
            return self._result(True, "Quota foro inserita", SwErrors.swSuccess,
                                {"duplicate_diameters_removed": removed})
        except Exception as e:
            return self._fail("add_hole_callout", e)

    # ====================================================================
    # 11. Title block / properties
    # ====================================================================

    # logical name -> custom property used by the title block of the standard templates
    _PROP_MAP = {"title": "Description", "description": "Description", "author": "DrawnBy",
                 "drawn_by": "DrawnBy", "drawing_number": "DrawingNumber", "number": "DrawingNumber",
                 "material": "Material", "revision": "Revision", "date": "DrawnDate",
                 "company": "CompanyName", "checked_by": "CheckedBy", "checked_date": "CheckedDate",
                 "finish": "Finish", "weight": "Weight", "approved_by": "EngineeringApproval"}

    def set_drawing_properties(self, properties: Dict[str, str], target: str = "both") -> Dict:
        """Custom properties for the title block. Keys: title, author, drawing_number,
        material, revision, date, company, checked_by, checked_date, finish, weight,
        approved_by - or any custom name. target: 'drawing' | 'model' | 'both'."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            if not properties:
                return self._result(False, "properties vuoto", SwErrors.swInvalidInput)
            managers = []
            if target in ("drawing", "both"):
                managers.append(("drawing", doc))
            if target in ("model", "both"):
                mp = self._model_path_for_drawing(doc)
                if mp:
                    mdoc, _ = self._get_model_doc(mp)
                    if mdoc is not None:
                        managers.append(("model", mdoc))
            written = {}
            for label, d in managers:
                cpm = d.Extension.CustomPropertyManager("")
                for k, val in properties.items():
                    name = self._PROP_MAP.get(str(k).lower(), str(k))
                    cpm.Add3(name, 30, str(val), 1)  # 30 = text, 1 = overwrite
                    written.setdefault(label, {})[name] = cpm.Get(name)
            try:
                doc.ForceRebuild3(False)
            except Exception:
                pass
            return self._result(True, f"Proprieta scritte: {sum(len(v) for v in written.values())}",
                                SwErrors.swSuccess, written)
        except Exception as e:
            return self._fail("set_drawing_properties", e)

    # ====================================================================
    # 12. Sheets
    # ====================================================================

    def list_sheets(self) -> Dict:
        try:
            doc, err = self._drawing()
            if err:
                return err
            names = list(self._com(doc, "GetSheetNames") or ())
            current = self._com(self._com(doc, "GetCurrentSheet"), "GetName")
            sheets = []
            for n in names:
                sh = doc.Sheet(n)
                p = sh.GetProperties2
                sheets.append({"name": n, "active": n == current,
                               "scale": f"{p[2]:g}:{p[3]:g}", "width_mm": self._mm(p[5]),
                               "height_mm": self._mm(p[6]),
                               "projection": "first_angle" if p[4] else "third_angle"})
            return self._result(True, f"{len(sheets)} fogli", SwErrors.swSuccess, {"sheets": sheets})
        except Exception as e:
            return self._fail("list_sheets", e)

    def add_sheet(self, name: str = None, paper_size: str = "A3", orientation: str = "landscape",
                  projection: str = "first", scale=None, sheet_format: str = "iso") -> Dict:
        try:
            doc, err = self._drawing()
            if err:
                return err
            names = list(self._com(doc, "GetSheetNames") or ())
            name = name or f"Foglio{len(names) + 1}"
            w, h = self._paper_dims(paper_size, orientation)
            first = projection.lower().startswith(("first", "primo", "1", "iso", "eur"))
            n, d = self._parse_scale(scale) or (1, 1)
            if orientation.lower().startswith("p") and paper_size.upper() in ("A3", "A2", "A1", "A0") and str(sheet_format).lower() == "iso":
                dtitle = self._get_doc_title(doc)
                self.ensure_portrait_format(paper_size)
                try:
                    self._sw_app.ActivateDoc3(dtitle, False, 0, win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0))
                    doc = self._sw_app.ActiveDoc
                except Exception:
                    pass
            fmt = self._sheet_format_path(paper_size, orientation.lower(), sheet_format)
            ok = doc.NewSheet3(name, 12, 12, float(n), float(d), bool(first), fmt, w, h, "")
            if not ok:
                return self._result(False, "Creazione foglio fallita", SwErrors.swUnknownError)
            return self._result(True, f"Foglio '{name}' creato e attivato", SwErrors.swSuccess,
                                {"sheets": list(self._com(doc, "GetSheetNames"))})
        except Exception as e:
            return self._fail("add_sheet", e)

    def activate_sheet(self, name: str) -> Dict:
        try:
            doc, err = self._drawing()
            if err:
                return err
            names = list(self._com(doc, "GetSheetNames") or ())
            if name not in names:
                return self._result(False, f"Foglio '{name}' non trovato. Fogli: {names}", SwErrors.swInvalidInput)
            ok = doc.ActivateSheet(name)
            return self._result(bool(ok), f"Foglio attivo: {name}" if ok else "Attivazione fallita",
                                SwErrors.swSuccess if ok else SwErrors.swUnknownError)
        except Exception as e:
            return self._fail("activate_sheet", e)

    def set_sheet_properties(self, sheet: str = None, scale=None, paper_size: str = None,
                             orientation: str = None, projection: str = None,
                             new_name: str = None) -> Dict:
        """Change scale / paper size / projection / name of a sheet (default: active sheet)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            if sheet:
                names = list(self._com(doc, "GetSheetNames") or ())
                if sheet not in names:
                    return self._result(False, f"Foglio '{sheet}' non trovato. Fogli: {names}", SwErrors.swInvalidInput)
                doc.ActivateSheet(sheet)
            sh = self._com(doc, "GetCurrentSheet")
            p = sh.GetProperties2
            w, h, first = float(p[5]), float(p[6]), bool(p[4])
            n, d = float(p[2]), float(p[3])
            if paper_size:
                cur_portrait = h > w
                orient = orientation or ("portrait" if cur_portrait else "landscape")
                w, h = self._paper_dims(paper_size, orient)
            elif orientation:
                if orientation.lower().startswith("p") != (h > w):
                    w, h = h, w
            if projection:
                first = projection.lower().startswith(("first", "primo", "1", "iso", "eur"))
            if scale is not None:
                parsed = self._parse_scale(scale)
                if parsed:
                    n, d = float(parsed[0]), float(parsed[1])
            sh.SetProperties2(12, 12, n, d, bool(first), w, h, True)
            if new_name:
                sh.SetName(new_name)
            q = sh.GetProperties2
            return self._result(True, "Proprieta del foglio aggiornate", SwErrors.swSuccess,
                                {"name": self._com(sh, "GetName"), "scale": f"{q[2]:g}:{q[3]:g}",
                                 "width_mm": self._mm(q[5]), "height_mm": self._mm(q[6]),
                                 "projection": "first_angle" if q[4] else "third_angle"})
        except Exception as e:
            return self._fail("set_sheet_properties", e)

    # ====================================================================
    # 13. View management
    # ====================================================================

    def list_drawing_views(self) -> Dict:
        try:
            doc, err = self._drawing()
            if err:
                return err
            infos = [self._view_info(v) for v in self._sheet_views(doc)]
            sheet = self._com(self._com(doc, "GetCurrentSheet"), "GetName")
            return self._result(True, f"{len(infos)} viste nel foglio {sheet}", SwErrors.swSuccess,
                                {"sheet": sheet, "views": infos})
        except Exception as e:
            return self._fail("list_drawing_views", e)

    def set_view_properties(self, view: str = None, scale=None, display_style: str = None,
                            show_tangent_edges: bool = None, exploded: bool = None) -> Dict:
        """scale ('1:2', 0.5...), display_style (wireframe|hidden_visible|hidden_removed|
        shaded|shaded_edges), show_tangent_edges (bool)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            v, err = self._find_view(doc, view)
            if err:
                return err
            done = {}
            if scale is not None:
                parsed = self._parse_scale(scale)
                if parsed:
                    self._set_view_scale(v, *parsed)
                    done["scale"] = round(float(v.ScaleDecimal), 6)
            if display_style:
                st = DISPLAY_STYLES.get(display_style.lower())
                if st is None:
                    return self._result(False, f"display_style: {list(DISPLAY_STYLES)}", SwErrors.swInvalidInput)
                v.SetDisplayMode3(False, st, False, True)
                done["display_mode"] = int(v.GetDisplayMode)
            if show_tangent_edges is not None:
                v.SetDisplayTangentEdges2(1 if show_tangent_edges else 2)
                done["tangent_edges"] = int(v.GetDisplayTangentEdges2)
            if exploded is not None:
                if not self._show_exploded(v, exploded):
                    return self._result(False, "Esploso non modificabile in questa vista (il modello deve avere una vista esplosa "
                                        "salvata nel file).", SwErrors.swFeatureError, self._view_info(v))
                done["exploded"] = bool(exploded)
            return self._result(True, "Proprieta vista aggiornate", SwErrors.swSuccess,
                                {"applied": done, **self._view_info(v)})
        except Exception as e:
            return self._fail("set_view_properties", e)

    def move_view(self, view: str = None, x: float = 0, y: float = 0, relative: bool = False,
                  unit: str = None) -> Dict:
        """Move a view to (x, y) of the sheet (centre) or by (x, y) if relative.
        Views aligned to a parent move only along the alignment axis."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            v, err = self._find_view(doc, view)
            if err:
                return err
            cur = tuple(v.Position)
            nx, ny = self._m(x, unit), self._m(y, unit)
            if relative:
                nx, ny = cur[0] + nx, cur[1] + ny
            v.Position = _arr(nx, ny)
            return self._result(True, f"Vista spostata: {self._com(v, 'GetName2')}", SwErrors.swSuccess,
                                self._view_info(v))
        except Exception as e:
            return self._fail("move_view", e)

    def delete_view(self, view: str) -> Dict:
        """Delete a view of the active drawing (its dependent views go with it)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            v, err = self._find_view(doc, view)
            if err:
                return err
            name = self._com(v, "GetName2")
            before = len(self._sheet_views(doc))
            self._select_view(doc, v)
            doc.Extension.DeleteSelection2(0)
            after = len(self._sheet_views(doc))
            if after >= before:
                return self._result(False, f"Vista {name} non eliminata", SwErrors.swUnknownError)
            return self._result(True, f"Vista {name} eliminata ({before - after} viste rimosse)",
                                SwErrors.swSuccess)
        except Exception as e:
            return self._fail("delete_view", e)

    # ====================================================================
    # 14. BOM and balloons
    # ====================================================================

    def _find_bom_template(self) -> str:
        roots = []
        try:
            exe = str(self._sw_app.GetExecutablePath)
            roots.append(exe if os.path.isdir(exe) else os.path.dirname(exe))
        except Exception:
            pass
        roots += [r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS"]
        tpl = self._default_template("drawing")
        if tpl:
            roots.append(os.path.dirname(os.path.dirname(tpl)))
        for root in roots:
            for lang in lang_folders(self._ui_language()):
                p = os.path.join(root, "lang", lang, "bom-standard.sldbomtbt")
                if os.path.isfile(p):
                    return p
        return ""

    def add_bom(self, view: str = None, x: float = None, y: float = None, bom_type: str = "parts_only",
                template: str = None, unit: str = None) -> Dict:
        """Bill of materials table for an assembly view. bom_type: parts_only|top_level|indented."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            v, err = self._find_view(doc, view)
            if err:
                return err
            btype = {"top_level": 0, "parts_only": 1, "indented": 2}.get(bom_type.lower())
            if btype is None:
                return self._result(False, "bom_type: parts_only|top_level|indented", SwErrors.swInvalidInput)
            tpl = template or self._find_bom_template()
            if not tpl or not os.path.isfile(tpl):
                return self._result(False, "Template distinta (.sldbomtbt) non trovato", SwErrors.swFileNotFoundError)
            W, H, _ = self._sheet_dims(doc)
            px = self._m(x, unit) if x is not None else W - MARGIN_R
            py = self._m(y, unit) if y is not None else H - MARGIN_T
            try:
                cfg = str(v.ReferencedConfiguration)
            except Exception:
                cfg = ""
            self._select_view(doc, v)
            bom = v.InsertBomTable4(True, px, py, 1, btype, cfg, tpl, False, 0, False)
            doc.ClearSelection2(True)
            if bom is None:
                return self._result(False, "Distinta non creata (la vista deve riferirsi a un assieme)",
                                    SwErrors.swUnknownError)
            try:
                rows = int(bom.RowCount)
            except Exception:
                rows = -1
            if not hasattr(self, "_reserved"):
                self._reserved = {}
            self._reserved[self._get_doc_title(doc)] = [(0.005, H - 0.005 - max(rows + 1, 2) * 0.0095, 0.215, H - 0.005)]
            return self._result(True, f"Distinta creata ({rows} righe)", SwErrors.swSuccess,
                                {"rows": rows, "template": os.path.basename(tpl)})
        except Exception as e:
            return self._fail("add_bom", e)

    def list_bom(self) -> Dict:
        """Legge la distinta base del disegno attivo: righe (n. articolo, nome parte, descrizione, quantita')."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            rows, header = [], []
            f = self._com(doc, "FirstFeature")
            while f is not None:
                if str(self._com(f, "GetTypeName2")) == "BomFeat":
                    sp = self._com(f, "GetSpecificFeature2")
                    tas = self._com(sp, "GetTableAnnotations")
                    for t in (tas or ()):
                        nrow, ncol = int(t.RowCount), int(t.ColumnCount)
                        cells = [[str(t.Text2(r, c, False)) for c in range(ncol)] for r in range(nrow)]
                        if cells:
                            header = [h.replace("<FONT size=3.5>", "") for h in cells[0]]
                            for r in cells[1:]:
                                rows.append(dict(zip(header, r)))
                f = self._com(f, "GetNextFeature")
            if not header:
                return self._result(False, "Nessuna distinta base nel disegno attivo (add_bom).", SwErrors.swInvalidInput)
            return self._result(True, f"Distinta: {len(rows)} righe", SwErrors.swSuccess,
                                {"header": header, "rows": rows, "count": len(rows)})
        except Exception as e:
            return self._fail("list_bom", e)

    def add_balloons(self, view: str = None, layout: str = None) -> Dict:
        """Automatic balloons for the components of an assembly view."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            v, err = self._find_view(doc, view)
            if err:
                return err
            opts = doc.CreateAutoBalloonOptions
            if layout:
                lay = {"square": 0, "circular": 1, "top": 2, "bottom": 3, "left": 4, "right": 5}.get(layout.lower())
                if lay is not None:
                    opts.Layout = lay
            self._select_view(doc, v)
            res = doc.AutoBalloon5(opts)
            doc.ClearSelection2(True)
            count = len(res) if res else 0
            if count == 0:
                return self._result(False, "Nessun palloncino creato (vista di un assieme necessaria)",
                                    SwErrors.swUnknownError)
            return self._result(True, f"{count} palloncini creati", SwErrors.swSuccess, {"count": count})
        except Exception as e:
            return self._fail("add_balloons", e)

    # ====================================================================
    # 15-16. Export / save
    # ====================================================================

    def _export_guard(self, doc, path: str) -> Optional[str]:
        """Messaggio di rifiuto se salvare `path` farebbe crashare SolidWorks: DXF/DWG di un disegno con viste interrotte
        (RPC 0x800706BE, verificato). Vale per ogni strada che scrive il file (export_drawing, save_document, _save_as)."""
        try:
            if os.path.splitext(str(path))[1].lower() not in (".dxf", ".dwg"):
                return None
            if int(self._com(doc, "GetType")) != DOC_DRAWING:
                return None
            broken = self._break_views(doc, all_sheets=True)
            if broken:
                return (f"Export {os.path.splitext(str(path))[1][1:].upper()} rifiutato: le viste interrotte {broken} fanno andare in "
                        "crash SolidWorks. Esporta in PDF o elimina la vista interrotta.")
        except Exception as e:
            logger.debug(f"export guard: {e}")
        return None

    def _save_as(self, doc, path: str) -> Tuple[bool, int, int]:
        guard = self._export_guard(doc, path)
        if guard:
            logger.warning(guard)
            return False, -1, -1
        errors = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        warnings = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        ok = doc.Extension.SaveAs(path, 0, 1, self._NULL, errors, warnings)
        return bool(ok), int(errors.value), int(warnings.value)

    def _break_views(self, doc, all_sheets: bool) -> List[str]:
        found = []
        current = self._com(self._com(doc, "GetCurrentSheet"), "GetName")
        names = [current]
        if all_sheets:
            names = list(self._com(doc, "GetSheetNames") or ())
        for n in names:
            if n != self._com(self._com(doc, "GetCurrentSheet"), "GetName"):
                doc.ActivateSheet(n)
            for v in self._sheet_views(doc):
                if self._com(v, "GetBreakLines") is not None:
                    found.append(f"{n}/{self._com(v, 'GetName2')}")
        if self._com(self._com(doc, "GetCurrentSheet"), "GetName") != current:
            doc.ActivateSheet(current)
        return found

    def export_drawing(self, filepath: str, format: str = None) -> Dict:
        """Export the active sheet/drawing: pdf, dwg, dxf, png, jpg (from the extension or `format`)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            path = os.path.abspath(filepath)
            fmt = (format or os.path.splitext(path)[1].lstrip(".")).lower()
            if fmt not in ("pdf", "dwg", "dxf", "png", "jpg", "jpeg"):
                return self._result(False, "Formato non supportato (pdf, dwg, dxf, png, jpg)", SwErrors.swInvalidInput)
            if os.path.splitext(path)[1].lower().lstrip(".") != fmt:
                path = os.path.splitext(path)[0] + "." + fmt
                if os.path.exists(path):
                    # la guardia di sovrascrittura (safety.py) ha controllato il nome richiesto, non questo
                    return self._result(False, f"Rifiutato: il file viene scritto come {path}, che esiste gia' e verrebbe "
                                        f"sovrascritto. Usa direttamente quel nome (con overwrite=true se voluto).",
                                        SwErrors.swFileSaveError, {"refused": "file_exists", "filepath": path})
            if fmt in ("dxf", "dwg"):
                # SolidWorks 2026 crashes (RPC failure, process lost) exporting DXF/DWG of drawings with
                # break views anywhere in the drawing (verified live, non-deterministic)
                broken = self._break_views(doc, all_sheets=True)
                if broken:
                    return self._result(False,
                        f"Export {fmt.upper()} rifiutato: viste interrotte {broken} fanno andare in crash "
                        "SolidWorks. Esporta in PDF o elimina la vista interrotta.",
                        SwErrors.swExportError)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if os.path.exists(path):
                os.remove(path)
            self._fit_title_number(doc)
            ok, e, w = self._save_as(doc, path)
            size = os.path.getsize(path) if os.path.exists(path) else 0
            if not ok or size == 0:
                return self._result(False, f"Export fallito (errori={e}, avvisi={w})", SwErrors.swFileSaveError)
            return self._result(True, f"Esportato: {path}", SwErrors.swSuccess,
                                {"path": path, "bytes": size, "format": fmt})
        except Exception as e:
            return self._fail("export_drawing", e)

    def save_drawing(self, filepath: str) -> Dict:
        """Save the active drawing as `filepath` (.SLDDRW)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            path = os.path.abspath(filepath)
            if not path.lower().endswith(".slddrw"):
                path += ".SLDDRW"
            os.makedirs(os.path.dirname(path), exist_ok=True)
            ok, e, w = self._save_as(doc, path)
            if ok:
                self._fit_title_number(doc)
            if not ok or not os.path.exists(path):
                return self._result(False, f"Salvataggio fallito (errori={e}, avvisi={w})", SwErrors.swFileSaveError)
            return self._result(True, f"Disegno salvato: {path}", SwErrors.swSuccess,
                                {"path": path, "bytes": os.path.getsize(path), "title": self._get_doc_title(doc)})
        except Exception as e:
            return self._fail("save_drawing", e)
