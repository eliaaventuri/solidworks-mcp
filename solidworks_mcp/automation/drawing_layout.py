"""
Drawing layout helpers
----------------------
Automatic scale/position of views, free-space search for added views, dimension tidy-up and
title-block properties. Mixed into DrawingOperations (see drawings.py).

All lengths are in metres (sheet space), like the SolidWorks API.
"""

import os
import logging
import tempfile
from typing import Dict, List, Optional, Tuple, Any

from ..constants import SwErrors
from ..utils.sw_lang import TITLE_BLOCK_ERROR_RE

import win32com.client
import pythoncom

logger = logging.getLogger(__name__)

Rect = Tuple[float, float, float, float]  # x0, y0, x1, y1

# Series of preferred scales (sheet : model), largest first (ISO 5455 / UNI)
STD_SCALES = [(100, 1), (50, 1), (20, 1), (10, 1), (5, 1), (2, 1), (1, 1), (1, 2), (1, 5),
              (1, 10), (1, 20), (1, 50), (1, 100), (1, 200), (1, 500), (1, 1000)]

MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 0.03, 0.03, 0.03, 0.09
GAP_X, GAP_Y = 0.050, 0.045        # room for dimensions between ortho views
VIEW_PAD = 0.012                   # SolidWorks outlines are ~6 mm larger than the geometry
DIM_ROW = 0.0075                   # spacing between stacked dimension lines
DIM_FIRST = 0.011                  # first dimension line distance from the view outline

# Title-block properties referenced by the ISO/DIN sheet formats (the formats show "ERRORE:<name>"
# when the property is missing). The list is completed at run time from the exported text.
TITLEBLOCK_PROPS = ["CompanyName", "Description", "DrawnBy", "DrawnDate", "CheckedBy", "CheckedDate",
                    "EngineeringApproval", "EngAppDate", "ManufacturingApproval", "MfgAppDate",
                    "QAApproval", "QAAppDate", "Material", "Finish", "Revision", "Weight"]


def _inter(a: Rect, b: Rect, pad: float = 0.0) -> bool:
    return not (a[2] + pad <= b[0] or b[2] + pad <= a[0] or a[3] + pad <= b[1] or b[3] + pad <= a[1])


def _arr(*vals):
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, tuple(float(v) for v in vals))


class DrawingLayoutMixin:

    # ------------------------------------------------------------------ geometry helpers
    def _view_rect(self, v) -> Rect:
        ol = tuple(self._com(v, "GetOutline"))
        return (ol[0], ol[1], ol[2], ol[3])

    def _title_rect(self, W: float, H: float) -> Rect:
        """Title block of the ISO sheet formats (bottom-right)."""
        return (W - 0.195, 0.0, W, 0.08)

    def _reserved_rects(self, doc) -> List[Rect]:
        return list(getattr(self, "_reserved", {}).get(self._get_doc_title(doc), []))

    def _occupied(self, doc, exclude=None, pad: float = 0.0) -> List[Rect]:
        W, H, _ = self._sheet_dims(doc)
        rects = [self._title_rect(W, H)] + self._reserved_rects(doc)
        ex = self._com(exclude, "GetName2") if exclude is not None else None
        for v in self._sheet_views(doc):
            if ex is not None and self._com(v, "GetName2") == ex:
                continue
            r = self._view_rect(v)
            rects.append((r[0] - pad, r[1] - pad, r[2] + pad, r[3] + pad))
        # annotazioni gia' presenti (quote, note, tabelle, tolleranze): una nuova vista non deve coprirle.
        # Quelle delle vista `exclude` si muovono con lei e non contano.
        if getattr(self, "_occupied_annotations", True):
            try:
                for a in self._dq_annotations(doc):
                    if ex is not None and a.get("view") == ex:
                        continue
                    if a["kind"] == "dimension" and a.get("dim_kind") in ("dia", "rad", "ang") and a.get("trect"):
                        r = a["trect"]
                    else:
                        r = a["rect"]
                    rects.append((r[0] - pad, r[1] - pad, r[2] + pad, r[3] + pad))
            except Exception as e:
                logger.debug(f"occupied annotations: {e}")
        return rects

    def _free_spot(self, doc, w: float, h: float, near: Tuple[float, float], exclude=None,
                   gap: float = 0.03, step: float = 0.005) -> Optional[Tuple[float, float]]:
        """Centre (x, y) of the free sheet area of size (w, h) closest to `near`."""
        W, H, _ = self._sheet_dims(doc)
        occ = self._occupied(doc, exclude)
        x0, x1, y0, y1 = 0.025, W - 0.025, 0.025, H - 0.025
        best, best_d = None, 1e9
        y = y0 + h / 2
        while y <= y1 - h / 2 + 1e-9:
            x = x0 + w / 2
            while x <= x1 - w / 2 + 1e-9:
                cand = (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
                if not any(_inter(cand, o, gap) for o in occ):
                    d = (x - near[0]) ** 2 + (y - near[1]) ** 2
                    if d < best_d:
                        best, best_d = (x, y), d
                x += step
            y += step
        return best

    def _set_pos(self, v, x: float, y: float) -> bool:
        """Move the CENTRE of the view outline to (x, y). `View.Position` is not always the outline centre
        (e.g. detail views), so the offset is measured and compensated."""
        try:
            v.Position = _arr(x, y)
            r = self._view_rect(v)
            cx, cy = (r[0] + r[2]) / 2.0, (r[1] + r[3]) / 2.0
            if abs(cx - x) > 5e-4 or abs(cy - y) > 5e-4:
                p = tuple(v.Position)
                v.Position = _arr(p[0] + (x - cx), p[1] + (y - cy))
            return True
        except Exception as e:
            logger.debug(f"Position set failed: {e}")
            return False

    def _place_free(self, doc, v, near: Tuple[float, float], axis: Optional[str] = None) -> Tuple[float, float]:
        """Move view `v` to the nearest free area. axis 'x'/'y' = the view is aligned with its parent and
        can slide only along that axis (the other coordinate is kept)."""
        r = self._view_rect(v)
        w, h = r[2] - r[0], r[3] - r[1]
        pos = tuple(v.Position)
        self._last_place_ok = False
        if axis is None:
            for gap in (0.03, 0.015, 0.006):
                spot = self._free_spot(doc, w, h, near, exclude=v, gap=gap)
                if spot:
                    self._set_pos(v, *spot)
                    self._last_place_ok = True
                    break
            return tuple(v.Position)
        occ = self._occupied(doc, v)
        W, H, _ = self._sheet_dims(doc)
        best, best_d = None, 1e9
        t = 0.02
        while t < max(W, H):
            for sgn in (1, -1):
                if axis == "y":
                    c = (pos[0], near[1] + sgn * t)
                else:
                    c = (near[0] + sgn * t, pos[1])
                cand = (c[0] - w / 2, c[1] - h / 2, c[0] + w / 2, c[1] + h / 2)
                inside = cand[0] >= 0.025 and cand[2] <= W - 0.025 and cand[1] >= 0.025 and cand[3] <= H - 0.025
                if inside and not any(_inter(cand, o, 0.03) for o in occ):
                    d = abs(t)
                    if d < best_d:
                        best, best_d = c, d
            if best:
                break
            t += 0.005
        if best:
            self._set_pos(v, *best)
            self._last_place_ok = True
            return tuple(v.Position)
        # no room along the alignment axis: break the alignment and look anywhere on the sheet
        try:
            self._com(v, "RemoveAlignment")
        except Exception as e:
            logger.debug(f"RemoveAlignment failed: {e}")
        for gap in (0.03, 0.015, 0.006):
            spot = self._free_spot(doc, w, h, near, exclude=v, gap=gap)
            if spot:
                self._set_pos(v, *spot)
                self._last_place_ok = True
                break
        return tuple(v.Position)

    def _fit_view_free(self, doc, v, near, min_scale: float) -> Tuple[bool, float]:
        """Non-aligned view (e.g. detail): find a free area, reducing the view scale along the ISO series
        (not below `min_scale`) until it fits. Returns (placed, scale)."""
        s0 = float(v.ScaleDecimal)
        cands = [n / d for n, d in STD_SCALES if min_scale - 1e-9 <= n / d <= s0 + 1e-9]
        cands = sorted(set(cands), reverse=True) or [s0]
        for gap in (0.03, 0.015, 0.006):
            for s in cands:
                if abs(s - float(v.ScaleDecimal)) > 1e-9:
                    n, d = next((n, d) for n, d in STD_SCALES if abs(n / d - s) < 1e-9)
                    self._set_view_scale(v, n, d)
                r = self._view_rect(v)
                spot = self._free_spot(doc, r[2] - r[0], r[3] - r[1], near, exclude=v, gap=gap)
                if spot:
                    self._set_pos(v, *spot)
                    return True, s
        return False, float(v.ScaleDecimal)

    # ------------------------------------------------------------------ standard views layout
    def _plan_layout(self, W, H, first, keys, sizes, gx=GAP_X, gy=GAP_Y):
        """Positions (centres) of the standard views. sizes: {key: (w, h)} in metres at the final scale.
        Keys follow swStandardViews_e: 1 front 2 back 3 left 4 right 5 top 6 bottom 7-9 pictorial.
        The orthographic block (front + projected views, gaps for the dimension rows) and the pictorial
        views are placed by a search over candidate positions with full collision checks (title block,
        sheet frame, each other). The gaps shrink (down to 64 %) before the layout is declared not fitting.
        Returns (positions, fits)."""
        sel = set(keys)
        above, below = (6, 5) if first else (5, 6)
        leftc, rightc = (4, 3) if first else (3, 4)
        fw, fh = sizes[1]
        lw = sizes[leftc][0] if leftc in sel else 0.0
        rw = sizes[rightc][0] if rightc in sel else 0.0
        bw = sizes[2][0] if 2 in sel else 0.0
        ah = sizes[above][1] if above in sel else 0.0
        bh = sizes[below][1] if below in sel else 0.0
        isos = [k for k in (7, 8, 9) if k in sel]
        ux0, uy0, ux1, uy1 = 0.025 + 0.006, 0.025 + 0.006, W - 0.025 - 0.006, H - 0.025 - 0.006
        title = self._title_rect(W, H)
        tit = (title[0] - 0.004, title[1], title[2], title[3] + 0.006)
        reserved = [(r[0] - 0.01, r[1] - 0.01, r[2] + 0.01, r[3] + 0.01) for r in
                    getattr(self, "_reserved", {}).get(getattr(self, "_layout_title", None), [])]
        best_pos = None
        for factor in (1.0, 0.8, 0.64, 0.5, 0.4):
            gxx, gyy = gx * factor, gy * factor
            block_w = lw + (gxx if lw else 0) + fw + ((gxx + rw) if rw else 0) + ((gxx + bw) if bw else 0)
            block_h = ((ah + gyy) if ah else 0) + fh + ((gyy + bh) if bh else 0)
            if block_w > ux1 - ux0 or block_h > uy1 - uy0:
                continue

            def build(bx0, by0):
                pos = {}
                fx = bx0 + lw + (gxx if lw else 0) + fw / 2
                fy = by0 + ((bh + gyy) if bh else 0) + fh / 2
                pos[1] = (fx, fy)
                if above in sel:
                    pos[above] = (fx, fy + fh / 2 + gyy + ah / 2)
                if below in sel:
                    pos[below] = (fx, fy - fh / 2 - gyy - bh / 2)
                if leftc in sel:
                    pos[leftc] = (fx - fw / 2 - gxx - lw / 2, fy)
                redge = fx + fw / 2
                if rightc in sel:
                    pos[rightc] = (redge + gxx + rw / 2, fy)
                    redge += gxx + rw
                if 2 in sel:
                    pos[2] = (redge + gxx + bw / 2, fy)
                return pos

            # pictorial views: stacked in a corner of the usable area (priority: top-right, top-left,
            # bottom-left, bottom-right)
            tw = max([sizes[k][0] for k in isos] or [0.0])
            th = sum(sizes[k][1] for k in isos) + 0.03 * max(len(isos) - 1, 0)
            corners = [(ux1 - tw, uy1 - th), (ux0, uy1 - th), (ux0, uy0), (ux1 - tw, uy0)] if isos else [None]
            for corner in corners:
                iso_pos, iso_rects = {}, []
                if corner is not None:
                    y_top = corner[1] + th
                    for k in isos:
                        w, h = sizes[k]
                        iso_pos[k] = (corner[0] + tw - w / 2 if corner[0] > ux0 else corner[0] + w / 2, y_top - h / 2)
                        x0 = iso_pos[k][0] - w / 2
                        iso_rects.append((x0, y_top - h, x0 + w, y_top))
                        y_top -= h + 0.03
                    if any(_inter(r, tit, 0.0) for r in iso_rects) or any(_inter(r, q, 0.0) for r in iso_rects for q in reserved):
                        continue
                nx, ny = 9, 9
                cands = []
                for i in range(nx):
                    for j in range(ny):
                        bx0 = ux0 + (ux1 - ux0 - block_w) * i / (nx - 1)
                        by0 = uy0 + (uy1 - uy0 - block_h) * j / (ny - 1)
                        blk = (bx0, by0, bx0 + block_w, by0 + block_h)
                        if _inter(blk, tit, 0.0) or any(_inter(blk, q, 0.0) for q in reserved):
                            continue
                        if any(_inter(blk, r, 0.030) for r in iso_rects):
                            continue
                        # preference: centred in the horizontal free area, a bit above the vertical centre
                        cx = bx0 + block_w / 2
                        free_l = ux0
                        free_r = (min(r[0] for r in iso_rects) - 0.030) if iso_rects and corner[0] > ux0 else ux1
                        if iso_rects and corner[0] <= ux0:
                            free_l = max(r[2] for r in iso_rects) + 0.030
                        cost = abs(cx - (free_l + free_r) / 2) + 0.5 * abs(by0 + block_h / 2 - (uy0 + uy1) / 2 - 0.02)
                        cands.append((cost, bx0, by0))
                if cands:
                    cands.sort()
                    _, bx0, by0 = cands[0]
                    pos = build(bx0, by0)
                    pos.update(iso_pos)
                    return pos, True
            if best_pos is None:
                best_pos = build(ux0, uy0)
        if best_pos is None:
            best_pos = {1: (W / 2, H / 2)}
        for k in sel:
            best_pos.setdefault(k, (W / 2, H / 2))
        return best_pos, False

    def _choose_scale(self, W, H, first, keys, box) -> Tuple[int, int]:
        dx, dy, dz = box
        iso = ((dx + dz) * 0.87, dy * 0.82 + (dx + dz) * 0.5)
        base = {1: (dx, dy), 2: (dx, dy), 5: (dx, dz), 6: (dx, dz), 3: (dz, dy), 4: (dz, dy),
                7: iso, 8: iso, 9: iso}
        for n, d in STD_SCALES:
            s = n / d
            sizes = {k: (base[k][0] * s + VIEW_PAD, base[k][1] * s + VIEW_PAD) for k in keys}
            if 1 not in sizes:
                sizes[1] = (base[1][0] * s + VIEW_PAD, base[1][1] * s + VIEW_PAD)
            _, ok = self._plan_layout(W, H, first, list(keys), sizes)
            if ok:
                return n, d
        return STD_SCALES[-1]

    # ------------------------------------------------------------------ dimensions
    def _pictorial_names(self, model_path: str) -> List[str]:
        names = []
        for idx in (7, 8, 9):
            n, _ = self._model_view_name(model_path, idx)
            if n:
                names.append(n)
        return names

    def _is_pictorial(self, v) -> bool:
        try:
            name = str(self._com(v, "GetOrientationName"))
        except Exception:
            return False
        mp = self._view_model_path(v)
        if mp:
            try:
                return name in self._pictorial_names(mp)
            except Exception:
                pass
        return name.lower().lstrip("*").startswith(("iso", "tri", "dim"))

    def _display_dims(self, v) -> List[Any]:
        out = []
        dd = v.GetFirstDisplayDimension5
        while dd is not None:
            out.append(dd)
            dd = dd.GetNext3
        return out

    def _dim_info(self, dd) -> Dict:
        dim = dd.GetDimension2(0)
        an = dd.GetAnnotation
        pos = tuple(an.GetPosition)
        try:
            callout = bool(dd.IsHoleCallout)
        except Exception:
            callout = False
        return {"dd": dd, "value": round(float(dim.Value), 9), "type": int(dd.Type2), "pos": pos,
                "callout": callout, "name": dim.Name, "full": dim.FullName}

    def _dim_key(self, i: Dict) -> Tuple:
        """Duplicate key: diameters/radii/callouts by value; linear dimensions by value AND position
        (a horizontal and a vertical 30 mm are different dimensions)."""
        if i["type"] in (5, 6) or i["callout"]:
            return (i["value"], "round")
        return (i["value"], i["type"], round(i["pos"][0] / 0.003), round(i["pos"][1] / 0.003))

    def _delete_dim(self, doc, info) -> bool:
        doc.ClearSelection2(True)
        ok = doc.Extension.SelectByID2(info["full"], "DIMENSION", 0, 0, 0, False, 0, self._NULL, 0)
        if ok:
            doc.Extension.DeleteSelection2(0)
        doc.ClearSelection2(True)
        return bool(ok)

    def _remove_duplicate_dims(self, doc, view) -> int:
        """Delete duplicated dimensions in a view (same value and type). A hole callout wins over a plain
        diameter dimension of the same size."""
        infos = [self._dim_info(d) for d in self._display_dims(view)]
        removed = 0
        seen: Dict[Tuple, Dict] = {}
        callout_vals = {i["value"] for i in infos if i["callout"]}
        for i in infos:
            key = self._dim_key(i)
            if not i["callout"] and i["type"] in (5, 6) and i["value"] in callout_vals:
                removed += int(self._delete_dim(doc, i))
                continue
            if key in seen and not i["callout"]:
                removed += int(self._delete_dim(doc, i))
                continue
            seen[key] = i
        return removed

    def _tidy_dims(self, doc, view) -> int:
        """Re-position the dimensions of an orthographic view outside its outline, in separate rows:
        horizontal ones above, vertical ones on the right, diameters/radii on the left (staggered)."""
        r = self._view_rect(view)
        # real geometry box: outline minus the ~6 mm padding
        y0, x1, y1 = r[1] + 0.006, r[2] - 0.006, r[3] - 0.006
        infos = [self._dim_info(d) for d in self._display_dims(view)]
        above, right, rad = [], [], []
        for i in infos:
            x, y = i["pos"][0], i["pos"][1]
            if i["type"] in (5, 6):
                rad.append(i)
            elif y >= y1 - 1e-4 and not (x > x1 + 0.002):
                above.append(i)
            elif x > x1 + 0.002:
                right.append(i)
            elif y <= y0 + 1e-4:
                above.append(i)
            else:
                right.append(i)
        n = 0
        for k, i in enumerate(sorted(above, key=lambda t: t["value"])):
            ax, ay = i["pos"][0], y1 + DIM_FIRST + k * DIM_ROW
            i["dd"].GetAnnotation.SetPosition2(ax, ay, i["pos"][2])
            n += 1
        for k, i in enumerate(sorted(right, key=lambda t: t["value"])):
            ax, ay = x1 + DIM_FIRST + k * (DIM_ROW + 0.002), i["pos"][1]
            i["dd"].GetAnnotation.SetPosition2(ax, ay, i["pos"][2])
            n += 1
        return n

    def list_drawing_dimensions(self) -> Dict:
        """All dimensions of the active sheet (per view): value (mm), kind, position, hole callout flag,
        whether the view is pictorial (isometric...), plus the number of duplicates."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            rows, dup = [], 0
            for v in self._sheet_views(doc):
                vname = self._com(v, "GetName2")
                pict = self._is_pictorial(v)
                seen = set()
                for d in self._display_dims(v):
                    i = self._dim_info(d)
                    key = self._dim_key(i)
                    isdup = key in seen
                    seen.add(key)
                    dup += int(isdup)
                    rows.append({"view": vname, "pictorial_view": pict, "name": i["name"],
                                 "value_mm": round(i["value"] * 1000, 4), "type": i["type"],
                                 "hole_callout": i["callout"], "duplicate": isdup,
                                 "x_mm": self._mm(i["pos"][0]), "y_mm": self._mm(i["pos"][1])})
            return self._result(True, f"{len(rows)} quote, {dup} duplicate", SwErrors.swSuccess,
                                {"dimensions": rows, "duplicates": dup,
                                 "on_pictorial_views": sum(1 for r in rows if r["pictorial_view"])})
        except Exception as e:
            return self._fail("list_drawing_dimensions", e)


    # ------------------------------------------------------------------ N. DISEGNO del cartiglio (A8)
    def _fit_title_number(self, doc) -> Dict:
        """(A8) Il formato ISO scrive il nome file (N. DISEGNO) in carattere da 6,35 mm in una cella larga ~70 mm:
        con nomi lunghi esce dalla cella. Riduce l'altezza del carattere della nota (e se anche 2 mm non bastano
        lo dichiara). Restituisce {'text','height_mm','fits'}."""
        out = {"text": None, "height_mm": None, "fits": True}
        try:
            W, H, _ = self._sheet_dims(doc)
            tb = self._title_rect(W, H)
            sv = doc.GetFirstView
            a = sv.GetFirstAnnotation3
            while a is not None:
                if int(a.GetType) == 6:
                    try:
                        pos = tuple(float(x) for x in a.GetPosition)
                    except Exception:
                        pos = None
                    if pos and tb[0] < pos[0] < tb[2] and tb[1] < pos[1] < tb[3]:
                        tf = a.GetTextFormat(0)
                        h = float(tf.CharHeight)
                        if abs(h - 0.00635) < 2e-4:
                            txt = str(a.GetSpecificAnnotation.GetText)
                            # il testo di N. DISEGNO e' il nome file: e' quello che coincide con il titolo del documento
                            base = os.path.splitext(os.path.basename(str(self._get_doc_path(doc) or "")))[0]
                            if txt and (txt.strip() == base or txt.strip() == self._get_doc_title(doc).split(" - ")[0].strip()):
                                n = len(txt)
                                cell = 0.060           # larghezza utile della cella (m), A4..A0 uguale
                                want = min(0.00635, cell / (0.70 * max(n, 1)))
                                new_h = max(want, 0.0015)
                                out.update({"text": txt, "height_mm": round(new_h * 1000, 2), "fits": want >= 0.0015})
                                if new_h < h - 1e-6:
                                    tf.CharHeight = new_h
                                    a.SetTextFormat(0, False, tf)
                                break
                a = a.GetNext3
        except Exception as e:
            logger.debug(f"fit title number: {e}")
        return out

    # ------------------------------------------------------------------ title-block properties
    def _model_mass_expr(self, mdoc) -> str:
        return f"SW-Mass@{os.path.basename(self._get_doc_path(mdoc))}"

    def _ensure_titleblock_props(self, doc, mdoc, extra: Optional[List[str]] = None) -> List[str]:
        """Create (empty) every property the sheet format references, on drawing and model, so no
        "ERRORE:<name>" appears. Weight is linked to the real mass. Returns the created names."""
        created = []
        names = list(TITLEBLOCK_PROPS) + [n for n in (extra or []) if n not in TITLEBLOCK_PROPS]
        targets = [("drawing", doc)]
        if mdoc is not None:
            targets.append(("model", mdoc))
        for label, d in targets:
            cpm = d.Extension.CustomPropertyManager("")
            existing = set(self._com(cpm, "GetNames") or ())
            for n in names:
                if n in existing:
                    continue
                value = ""
                if n == "Weight":
                    # the format shows the property twice: only the model carries the (real) mass
                    value = self._model_mass_expr(mdoc) if (mdoc is not None and label == "model") else ""
                elif n == "Description" and mdoc is not None:
                    value = os.path.splitext(os.path.basename(self._get_doc_path(mdoc)))[0]
                cpm.Add3(n, 30, value, 1)
                created.append(f"{label}:{n}")
        return created

    def _missing_props_from_dxf(self, doc) -> List[str]:
        """Export a temporary DXF and look for 'ERRORE:<prop>' texts (title block of the format)."""
        tmp = os.path.join(tempfile.gettempdir(), "swmcp_probe_titleblock.dxf")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
            ok, _, _ = self._save_as(doc, tmp)
            if not ok or not os.path.exists(tmp):
                return []
            txt = open(tmp, "r", encoding="latin-1", errors="ignore").read()
            return sorted(set(TITLE_BLOCK_ERROR_RE.findall(txt)))      # "ERRORE:<nome>" (it) / "ERROR:<nome>" (en)
        except Exception as e:
            logger.debug(f"missing props probe failed: {e}")
            return []
        finally:
            try:
                os.remove(tmp)
            except Exception:
                pass
