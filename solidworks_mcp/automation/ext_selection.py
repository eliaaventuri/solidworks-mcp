"""
Lotto SELEZIONE E TOPOLOGIA: selezione avanzata, raycasting, query topologiche, orientamento vista e screenshot etichettato (mixin SelectionOperations).
Schemi in tools_ext/selection.py.
"""

import math
import os
import logging
import traceback
from typing import Dict, List

from ..constants import SwErrors
from .data_export import _read_png, _write_png
from .modeling_base import null_variant

logger = logging.getLogger(__name__)

# Bitmap font 3x5 per cifre 0-9
FONT_3X5 = {
    '0': ['111', '101', '101', '101', '111'],
    '1': ['010', '110', '010', '010', '111'],
    '2': ['111', '001', '111', '100', '111'],
    '3': ['111', '001', '111', '001', '111'],
    '4': ['101', '101', '111', '001', '001'],
    '5': ['111', '100', '111', '001', '111'],
    '6': ['111', '100', '111', '101', '111'],
    '7': ['111', '001', '010', '010', '010'],
    '8': ['111', '101', '111', '101', '111'],
    '9': ['111', '101', '111', '001', '111'],
}


def _draw_badge(rows: List[bytearray], w: int, h: int, cx: int, cy: int, text: str,
                bg=(255, 230, 0), fg=(0, 0, 0), border=(0, 0, 0), scale: int = 2) -> None:
    """Disegna un badge numerato centrato su (cx, cy) nelle righe RGB del PNG."""
    tw = (len(text) * 4 - 1) * scale
    th = 5 * scale
    pad_x, pad_y = 3, 2
    bw = tw + pad_x * 2
    bh = th + pad_y * 2
    bx0 = max(0, min(w - bw, cx - bw // 2))
    by0 = max(0, min(h - bh, cy - bh // 2))

    for y in range(by0, by0 + bh):
        for x in range(bx0, bx0 + bw):
            is_border = (x == bx0 or x == bx0 + bw - 1 or y == by0 or y == by0 + bh - 1)
            c = border if is_border else bg
            rows[y][x * 3: x * 3 + 3] = bytes(c)

    cur_x = bx0 + pad_x
    cur_y = by0 + pad_y
    for ch in text:
        bitmap = FONT_3X5.get(ch, FONT_3X5['0'])
        for r_idx, row_str in enumerate(bitmap):
            for c_idx, val in enumerate(row_str):
                if val == '1':
                    for sy in range(scale):
                        for sx in range(scale):
                            px = cur_x + c_idx * scale + sx
                            py = cur_y + r_idx * scale + sy
                            if 0 <= px < w and 0 <= py < h:
                                rows[py][px * 3: px * 3 + 3] = bytes(fg)
        cur_x += 4 * scale


class SelectionOperations:
    """Mixin per selezione per ID/raggio, analisi topologica B-Rep, viste e cattura etichettata."""

    def select_by_id(self, name: str, object_type: str = "FACE", x: float = 0.0, y: float = 0.0, z: float = 0.0,
                     append: bool = False, mark: int = 0, unit: str = None) -> Dict:
        """Seleziona un'entita' geometrica o feature per nome/tipo tramite SelectByID2."""
        try:
            doc, err = self.get_active_doc()
            if err:
                return err
            ext = self._com(doc, "Extension")
            if ext is None:
                return self._result(False, "Estensione documento non disponibile", SwErrors.swUnknownError)
            x_m = self._mmu(float(x or 0.0), unit)
            y_m = self._mmu(float(y or 0.0), unit)
            z_m = self._mmu(float(z or 0.0), unit)
            obj_type = str(object_type or "FACE").strip().upper()
            ok = bool(ext.SelectByID2(str(name), obj_type, x_m, y_m, z_m, bool(append), int(mark or 0), null_variant(), 0))
            if not ok:
                feat = self._find_feature(doc, name) or self._std_plane_feature(doc, name)
                if feat is not None:
                    ok = bool(feat.Select2(bool(append), int(mark or 0)))
            count = self._sel_count(doc)
            msg = f"SelectByID2 '{name}' ({obj_type}): {'riuscita' if ok else 'fallita'}"
            return self._result(ok, msg, SwErrors.swSuccess if ok else SwErrors.swSelectionError,
                                {"selected": ok, "name": name, "object_type": obj_type, "total_selected": count})
        except Exception as e:
            logger.error(f"select_by_id error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore select_by_id: {e}", SwErrors.swUnknownError)

    def select_by_ray(self, origin: list, direction: list, radius: float = 1.0, type_wanted: int = 0,
                      append: bool = False, mark: int = 0, unit: str = None) -> Dict:
        """Seleziona un'entita' tramite raycasting vettoriale 3D (SelectByRay)."""
        try:
            doc, err = self.get_active_doc()
            if err:
                return err
            if not origin or len(origin) < 3:
                return self._result(False, "origin deve contenere [x, y, z]", SwErrors.swInvalidInput)
            if not direction or len(direction) < 3:
                return self._result(False, "direction deve contenere [dx, dy, dz]", SwErrors.swInvalidInput)
            ox = self._mmu(float(origin[0]), unit)
            oy = self._mmu(float(origin[1]), unit)
            oz = self._mmu(float(origin[2]), unit)
            dx = float(direction[0])
            dy = float(direction[1])
            dz = float(direction[2])
            rad_m = self._mmu(float(radius or 1.0), unit)
            ext = self._com(doc, "Extension")
            if ext is None:
                return self._result(False, "Estensione documento non disponibile", SwErrors.swUnknownError)
            tw = int(type_wanted) if type_wanted else 2  # default swSelFACES = 2
            ok = bool(ext.SelectByRay(ox, oy, oz, dx, dy, dz, rad_m, tw, bool(append), int(mark or 0), 0))
            count = self._sel_count(doc)
            msg = f"SelectByRay: {'colpito' if ok else 'mancato'}"
            return self._result(ok, msg, SwErrors.swSuccess if ok else SwErrors.swSelectionError,
                                {"hit": ok, "total_selected": count})
        except Exception as e:
            logger.error(f"select_by_ray error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore select_by_ray: {e}", SwErrors.swUnknownError)

    def query_topology_by_criteria(self, entity_type: str = "face", surface_type: str = None, normal: list = None,
                                   min_area: float = None, max_area: float = None, radius: float = None,
                                   tolerance: float = 0.01, unit: str = None) -> Dict:
        """Interroga e filtra la topologia B-Rep per proprieta' geometriche restituendo coordinate baricentriche."""
        try:
            doc, err = self.get_active_doc()
            if err:
                return err
            kind = {"faces": "face", "edges": "edge", "vertices": "vertex"}.get(
                str(entity_type or "face").lower().strip(), str(entity_type or "face").lower().strip()
            )
            entities = self._body_entities(doc, kind)
            matches = []

            for idx, e in enumerate(entities):
                try:
                    if kind == "face":
                        surf = self._com(e, "GetSurface")
                        stype = self._SURFACE_TYPES.get(int(self._com(surf, "Identity")), "other")
                        if surface_type and stype != str(surface_type).lower().strip():
                            continue
                        area_m2 = float(self._com(e, "GetArea"))
                        area_u2 = self._from_m(area_m2 ** 0.5, unit) ** 2
                        if min_area is not None and area_u2 < float(min_area):
                            continue
                        if max_area is not None and area_u2 > float(max_area):
                            continue
                        params = self._surface_params(surf, stype, unit, e)
                        if normal and stype == "plane" and len(normal) >= 3:
                            n = params.get("normal", [])
                            if len(n) == 3:
                                mag = math.sqrt(sum(float(v) ** 2 for v in normal)) or 1.0
                                un = [float(v) / mag for v in normal]
                                dot = sum(n[k] * un[k] for k in range(3))
                                if abs(dot - 1.0) > 0.05:
                                    continue
                        if radius is not None:
                            r = params.get("radius")
                            tol = float(tolerance or 0.01)
                            if r is None or abs(r - float(radius)) > tol:
                                continue
                        box = self._com(e, "GetBox")
                        c = [(box[k] + box[k + 3]) / 2.0 for k in range(3)]
                        q = e.GetClosestPointOn(c[0], c[1], c[2])
                        pt = [round(self._from_m(v, unit), 4) for v in list(q)[:3]]
                        matches.append({
                            "index": idx,
                            "type": stype,
                            "point": pt,
                            "area": round(area_u2, 4),
                            "params": params,
                        })
                    elif kind == "edge":
                        cv = self._com(e, "GetCurve")
                        ctype = self._CURVE_TYPES.get(int(self._com(cv, "Identity")), "other")
                        if surface_type and ctype != str(surface_type).lower().strip():
                            continue
                        cparams = self._curve_params(cv, ctype, unit)
                        if radius is not None and ctype == "circle":
                            r = cparams.get("radius")
                            tol = float(tolerance or 0.01)
                            if r is None or abs(r - float(radius)) > tol:
                                continue
                        v1 = self._com(e, "GetStartVertex")
                        v2 = self._com(e, "GetEndVertex")
                        sp = self._com(v1, "GetPoint") if v1 is not None else None
                        ep = self._com(v2, "GetPoint") if v2 is not None else None
                        pt = None
                        if sp is not None and ep is not None:
                            mid = e.GetClosestPointOn((sp[0] + ep[0]) / 2.0, (sp[1] + ep[1]) / 2.0, (sp[2] + ep[2]) / 2.0)
                            if mid is not None:
                                pt = [round(self._from_m(v, unit), 4) for v in list(mid)[:3]]
                        matches.append({
                            "index": idx,
                            "type": ctype,
                            "point": pt,
                            "params": cparams,
                        })
                    elif kind == "vertex":
                        p = self._com(e, "GetPoint")
                        pt = [round(self._from_m(v, unit), 4) for v in p] if p is not None else None
                        matches.append({
                            "index": idx,
                            "point": pt,
                        })
                except Exception:
                    continue

            return self._result(True, f"Trovate {len(matches)} entita' di tipo '{kind}' corrispondenti ai criteri",
                                SwErrors.swSuccess, {"count": len(matches), "entity_type": kind, "entities": matches})
        except Exception as e:
            logger.error(f"query_topology_by_criteria error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore query_topology_by_criteria: {e}", SwErrors.swUnknownError)

    def clear_selection(self) -> Dict:
        """Svuota il buffer di selezione del documento attivo."""
        try:
            doc, err = self.get_active_doc()
            if err:
                return err
            doc.ClearSelection2(True)
            return self._result(True, "Buffer di selezione svuotato con successo", SwErrors.swSuccess,
                                {"selection_count": 0})
        except Exception as e:
            logger.error(f"clear_selection error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore clear_selection: {e}", SwErrors.swUnknownError)

    def get_active_selection(self) -> Dict:
        """Elenca le entita' attualmente selezionate nel SelectionManager."""
        try:
            doc, err = self.get_active_doc()
            if err:
                return err
            sm = self._com(doc, "SelectionManager")
            if sm is None:
                return self._result(False, "SelectionManager non disponibile", SwErrors.swUnknownError)
            count = int(sm.GetSelectedObjectCount2(-1))
            items = []
            for i in range(1, count + 1):
                try:
                    stype = int(sm.GetSelectedObjectType3(i, -1))
                except Exception:
                    stype = 0
                try:
                    mark = int(sm.GetSelectedObjectMark(i, -1))
                except Exception:
                    mark = 0
                pt_coords = None
                try:
                    pt = sm.GetSelectionPoint2(i, -1)
                    if pt:
                        pt_coords = [round(float(v), 5) for v in pt]
                except Exception:
                    pass
                name = ""
                try:
                    obj = sm.GetSelectedObject6(i, -1)
                    if obj is not None and hasattr(obj, "GetName2"):
                        name = str(obj.GetName2() or "")
                except Exception:
                    pass
                items.append({
                    "index": i,
                    "type_id": stype,
                    "mark": mark,
                    "point": pt_coords,
                    "name": name,
                })
            return self._result(True, f"Selezione attiva: {count} entita'", SwErrors.swSuccess,
                                {"count": count, "items": items})
        except Exception as e:
            logger.error(f"get_active_selection error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore get_active_selection: {e}", SwErrors.swUnknownError)

    def set_view_orientation(self, orientation: str = "isometric") -> Dict:
        """Imposta l'orientamento della vista su una vista standard denominata."""
        try:
            doc, err = self.get_active_doc()
            if err:
                return err
            views = {
                "isometric": ("*Isometric", 7),
                "front": ("*Front", 1),
                "back": ("*Back", 2),
                "left": ("*Left", 3),
                "right": ("*Right", 4),
                "top": ("*Top", 5),
                "bottom": ("*Bottom", 6),
                "normal_to": ("*Normal To", 8),
                "normalto": ("*Normal To", 8),
                "dimetric": ("*Dimetric", 9),
                "trimetric": ("*Trimetric", 10),
            }
            key = str(orientation or "isometric").strip().lower()
            entry = views.get(key)
            if not entry:
                return self._result(False, f"Orientamento '{orientation}' non valido. Valori ammessi: {list(views.keys())}",
                                    SwErrors.swInvalidInput)
            doc.ShowNamedView2(entry[0], entry[1])
            doc.ViewZoomtofit2()
            return self._result(True, f"Orientamento vista impostato su '{entry[0]}'", SwErrors.swSuccess,
                                {"orientation": key, "view_name": entry[0], "view_id": entry[1]})
        except Exception as e:
            logger.error(f"set_view_orientation error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore set_view_orientation: {e}", SwErrors.swUnknownError)

    def zoom_to_fit(self) -> Dict:
        """Esegue lo zoom a tutto schermo dell'area grafica."""
        try:
            doc, err = self.get_active_doc()
            if err:
                return err
            doc.ViewZoomtofit2()
            return self._result(True, "Zoom to fit eseguito", SwErrors.swSuccess)
        except Exception as e:
            logger.error(f"zoom_to_fit error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore zoom_to_fit: {e}", SwErrors.swUnknownError)

    def export_labeled_viewport_image(self, filepath: str, entity_type: str = "face", max_labels: int = 30,
                                      width: int = 1920, height: int = 1080, overwrite: bool = False) -> Dict:
        """Cattura uno screenshot del modello con etichette numerate sovrapposte sulle entita' visibili."""
        try:
            doc, err = self.get_active_doc()
            if err:
                return err
            filepath = os.path.abspath(filepath)
            if os.path.exists(filepath) and not overwrite:
                return self._result(False, f"File gia' esistente: '{filepath}'. Usa overwrite=True per sovrascriverlo.",
                                    SwErrors.swFileSaveError)

            # 1. Esporta immagine base
            exp_res = self.export_model_image(filepath=filepath, view="isometric", width=width, height=height, zoom_to_fit=True)
            if not exp_res.get("success"):
                return exp_res

            # 2. Carica PNG
            w, h, _, rows = _read_png(filepath)

            # 3. Raccoglie punti entita' nel modello (in metri)
            kind = str(entity_type or "face").strip().lower()
            collected = []
            kinds_to_query = ["face"] if kind == "face" else (["edge"] if kind == "edge" else ["face", "edge"])
            for k in kinds_to_query:
                ents = self._body_entities(doc, k)
                for e in ents:
                    try:
                        if k == "face":
                            box = self._com(e, "GetBox")
                            c = [(box[i] + box[i + 3]) / 2.0 for i in range(3)]
                            q = e.GetClosestPointOn(c[0], c[1], c[2])
                            if q is not None:
                                collected.append({"kind": "face", "pt_m": list(q)[:3]})
                        elif k == "edge":
                            v1 = self._com(e, "GetStartVertex")
                            v2 = self._com(e, "GetEndVertex")
                            sp = self._com(v1, "GetPoint") if v1 is not None else None
                            ep = self._com(v2, "GetPoint") if v2 is not None else None
                            if sp is not None and ep is not None:
                                mid = e.GetClosestPointOn((sp[0] + ep[0]) / 2.0, (sp[1] + ep[1]) / 2.0, (sp[2] + ep[2]) / 2.0)
                                if mid is not None:
                                    collected.append({"kind": "edge", "pt_m": list(mid)[:3]})
                    except Exception:
                        continue

            collected = collected[:int(max_labels or 30)]

            # 4. Calcola coordinate di vista (ModelView.Transform)
            mv = doc.ActiveView
            tf = self._com(mv, "Transform")
            arr = list(self._com(tf, "ArrayData")) if tf is not None else None
            pts_view = []

            for item in collected:
                xm, ym, zm = item["pt_m"]
                if arr and len(arr) >= 12:
                    sc = float(arr[12]) if len(arr) > 12 else 1.0
                    xv = (arr[0] * xm + arr[1] * ym + arr[2] * zm) * sc + arr[9]
                    yv = (arr[3] * xm + arr[4] * ym + arr[5] * zm) * sc + arr[10]
                    zv = (arr[6] * xm + arr[7] * ym + arr[8] * zm) * sc + arr[11]
                    pts_view.append((xv, yv, zv, item))
                else:
                    pts_view.append((xm, ym, zm, item))

            # 5. Proietta su pixel (u, v) con margine del 15% attorno al modello
            labels_info = []
            if pts_view:
                min_x = min(p[0] for p in pts_view)
                max_x = max(p[0] for p in pts_view)
                min_y = min(p[1] for p in pts_view)
                max_y = max(p[1] for p in pts_view)
                span_x = (max_x - min_x) or 1.0
                span_y = (max_y - min_y) or 1.0

                for idx, (xv, yv, _zv, item) in enumerate(pts_view, start=1):
                    norm_x = (xv - min_x) / span_x
                    norm_y = (yv - min_y) / span_y
                    # Margine 15% interno per centratura zoom to fit
                    px = int(w * (0.15 + 0.70 * norm_x))
                    py = int(h * (0.85 - 0.70 * norm_y))
                    px = max(10, min(w - 10, px))
                    py = max(10, min(h - 10, py))

                    # Disegna badge giallo con bordo nero
                    _draw_badge(rows, w, h, px, py, str(idx), bg=(255, 230, 0), fg=(0, 0, 0), border=(0, 0, 0), scale=2)

                    labels_info.append({
                        "label": idx,
                        "type": item["kind"],
                        "point_mm": [round(v * 1000.0, 4) for v in item["pt_m"]],
                        "pixel": [px, py],
                    })

            # 6. Salva PNG modificato
            _write_png(filepath, w, h, rows)

            return self._result(True, f"Immagine etichettata salvata con {len(labels_info)} etichette in '{filepath}'",
                                SwErrors.swSuccess,
                                {"filepath": filepath, "label_count": len(labels_info), "labels": labels_info})
        except Exception as e:
            logger.error(f"export_labeled_viewport_image error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore export_labeled_viewport_image: {e}", SwErrors.swUnknownError)
