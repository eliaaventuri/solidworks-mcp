"""
Quote di posizione dei fori e quote di profilo (A17)
----------------------------------------------------
Le quote importate dal modello mettono i fori in "pitch" fra una riga e l'altra: le linee di richiamo partono dal centro
di un foro e attraversano gli altri fori, e nelle viste frontale/laterale non c'e' niente di utile (spessori, nervature).
Qui si fa pulizia e si completano le quote:

1. `_dp_remove_hole_dims`: le quote importate che ancorano un foro (punto di riferimento sull'asse di un foro) si tolgono
   e si rifanno dalla vista che mostra i cerchi;
2. `_dp_hole_chains`: nella vista con i fori, due catene di quote di posizione dal bordo del pezzo: righe (verticali) a destra,
   colonne (orizzontali) sotto; le linee di richiamo partono sempre dal foro piu' vicino alla linea di quota (nessun foro
   attraversato); l'ultimo tratto manca se esiste la quota d'ingombro (come nella prassi ISO);
3. `_dp_profile_chains`: per le altre viste ortogonali, catene di quote fra le ordinate degli spigoli rettilinei assiali visibili
   (spessori delle ali, altezza e spessore delle nervature, altezza totale), una sola volta per ogni direzione del modello
   e senza ripetere un valore gia' quotato.
"""

import math
import logging
from typing import Dict, List, Optional, Tuple, Any

import win32com.client
import pythoncom

logger = logging.getLogger(__name__)

TOL_CLUSTER = 0.0003            # m: ordinate che differiscono meno si considerano uguali
MIN_SEG = 0.0012                # m: tratti di catena piu' corti si ignorano


def _clusters(vals: List[float], tol: float = TOL_CLUSTER) -> List[float]:
    out: List[float] = []
    for v in sorted(vals):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


class DrawingPosMixin:
    _dp_done: Dict[Tuple, str] = {}
    _dp_hcache: Dict[str, Any] = {}

    def _dp_holes(self, v):
        """`_an_holes` (scorre tutte le facce del modello) con memoria per la durata di una disposizione delle quote."""
        key = str(self._com(v, "GetName2"))
        if key not in self._dp_hcache:
            self._dp_hcache[key] = self._an_holes(v)
        return self._dp_hcache[key]

    # ------------------------------------------------------------------ fori nel modello
    def _dp_hole_axes(self, m) -> List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]:
        """Assi dei fori (cilindri concavi): [(punto m, direzione unitaria)]."""
        out = []
        try:
            for b in (m.GetBodies2(0, True) or ()):
                for f in (b.GetFaces() or ()):
                    try:
                        sf = f.GetSurface
                        if not sf.IsCylinder or not bool(self._com(f, "FaceInSurfaceSense")):
                            continue
                        cp = sf.CylinderParams
                        out.append((tuple(float(x) for x in cp[0:3]), tuple(float(x) for x in cp[3:6])))
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"hole axes: {e}")
        return out

    @staticmethod
    def _dp_on_axis(p_mm, axes, tol_mm: float = 0.15) -> bool:
        p = (p_mm[0] / 1000.0, p_mm[1] / 1000.0, p_mm[2] / 1000.0)
        for o, d in axes:
            w = (p[0] - o[0], p[1] - o[1], p[2] - o[2])
            t = w[0] * d[0] + w[1] * d[1] + w[2] * d[2]
            r = math.sqrt(max(0.0, sum(c * c for c in w) - t * t))
            if r * 1000.0 < tol_mm:
                return True
        return False

    def _dp_plain_view(self, v) -> bool:
        """Vista ortogonale/proiettata di un pezzo (non sezione, dettaglio, ausiliaria, isometrica)."""
        try:
            m = v.ReferencedDocument
            return int(v.Type) in (4, 7) and not self._is_pictorial(v) and m is not None and int(m.GetType) == 1
        except Exception:
            return False

    def _dp_grid_ok(self, v) -> bool:
        """I fori della vista stanno su una griglia rettangolare (righe x colonne = numero di fori): solo li' hanno senso le catene
        di quote dal bordo (fori su una circonferenza si quotano con diametro di centri e numero, non con coordinate)."""
        if not self._dp_plain_view(v):
            return False
        holes = self._dp_holes(v)[0]
        if len(holes) < 2 or len(holes) > 40 or not self._dm_core(v):
            return False
        return len(holes) == len(_clusters([h["cx"] for h in holes])) * len(_clusters([h["cy"] for h in holes]))

    def _dp_remove_hole_dims(self, doc, views: List[Any]) -> int:
        """Toglie le quote lineari importate con un punto di riferimento sull'asse di un foro, se almeno una vista mostra i
        cerchi dei fori (li' si rifanno in catena). Non tocca le quote create da questo modulo."""
        if not any(self._dp_grid_ok(v) for v in self._sheet_views(doc)):
            return 0
        mine = set(self._dp_done.values())
        n = 0
        for v in views:
            if self._is_pictorial(v):
                continue
            m = v.ReferencedDocument
            try:
                if m is None or int(m.GetType) != 1:
                    continue
            except Exception:
                continue
            axes = self._dp_hole_axes(m)
            if not axes:
                continue
            for dd in self._dq_view_dims(v):
                i = self._dp_info(v, dd)
                if i is None or i["sel"] in mine or i["callout"]:
                    continue
                pts = i["refpts"][:2]
                if len(pts) >= 2 and any(self._dp_on_axis(p, axes) for p in pts):
                    if self._delete_dim_full(doc, i["sel"]):
                        n += 1
        return n

    def _dp_remove_interior_dims(self, doc, v, core) -> int:
        """Quote lineari importate le cui linee di richiamo, dal lato scelto (`_dm_side`), correrebbero per piu' di 8 mm DENTRO il
        contorno del pezzo: distanza del punto di riferimento (proiettato sul foglio) dal bordo del lato scelto."""
        proj = self._dm_proj(v)[0]
        mine = set(self._dp_done.values()) | set(getattr(self, "_pocket_done", {}).values())
        n = 0
        for dd in self._dq_view_dims(v):
            i = self._dp_info(v, dd)
            if i is None or i["sel"] in mine or i["axis"] not in ("H", "V") or i["callout"]:
                continue
            side = self._dm_side.get(i["sel"])
            if not side:
                continue
            depth = 0.0
            for p in i["refpts"][:2]:
                q = proj((p[0] / 1000.0, p[1] / 1000.0, p[2] / 1000.0))
                if i["axis"] == "V":     # linee di richiamo orizzontali, verso destra (+1) o sinistra (-1)
                    d = (core[2] - q[0]) if side > 0 else (q[0] - core[0])
                else:
                    d = (core[3] - q[1]) if side > 0 else (q[1] - core[1])
                depth = max(depth, d)
            if depth > 0.008 and self._delete_dim_full(doc, i["sel"]):
                n += 1
        return n

    # ------------------------------------------------------------------ lettura leggera di una quota
    def _dp_info(self, v, dd) -> Optional[Dict]:
        """Quota lineare: {'axis','lo','hi','value','refpts','sel','callout'} leggendo solo le frecce (la lettura completa
        `_dq_read`, con linee e testi, costa ~0,5 s a quota). None se non e' lineare."""
        try:
            if int(dd.Type2) not in (2, 11, 12, 15, 14):
                return None
            data = dd.GetDisplayData
            n = int(self._com(data, "GetArrowHeadCount"))
            if n < 2:
                return None
            a0, a1 = data.GetArrowHeadAtIndex2(0), data.GetArrowHeadAtIndex2(1)
            x1, y1, x2, y2 = float(a0[0]), float(a0[1]), float(a1[0]), float(a1[1])
            dx, dy = x2 - x1, y2 - y1
            ln = math.hypot(dx, dy)
            if ln < 1e-7:
                return None
            axis = "H" if abs(dy) / ln < 0.12 else ("V" if abs(dx) / ln < 0.12 else "O")
            lo, hi = (min(x1, x2), max(x1, x2)) if axis == "H" else (min(y1, y2), max(y1, y2))
            dim = dd.GetDimension2(0)
            return {"axis": axis, "lo": lo, "hi": hi, "value": float(dim.Value), "refpts": self._dq_refpoints(dim),
                    "sel": str(dd.GetNameForSelection), "callout": bool(dd.IsHoleCallout)}
        except Exception as e:
            logger.debug(f"dp_info: {e}")
            return None

    # ------------------------------------------------------------------ helper
    def _dp_overall_exists(self, v, axis: str, size: float) -> bool:
        for dd in self._dq_view_dims(v):
            i = self._dp_info(v, dd)
            if i is not None and i["axis"] == axis and (i["hi"] - i["lo"]) > size * 0.97:
                return True
        return False

    def _dp_make(self, doc, key: Tuple, c1, c2, expected: float, vertical: bool, tx: float, ty: float, side: int) -> Optional[str]:
        """Quota fra due spigoli/cerchi scelti (lista di punti candidati); `expected` in mm. Registro per rilanci."""
        alive = {str(d_.GetNameForSelection) for v_ in self._sheet_views(doc) for d_ in self._dq_view_dims(v_)}
        if self._dp_done.get(key) in alive:
            return self._dp_done[key]
        if not self._dm_select_pair(doc, c1, c2):
            return None
        dd = doc.AddVerticalDimension2(tx, ty, 0) if vertical else doc.AddHorizontalDimension2(tx, ty, 0)
        doc.ClearSelection2(True)
        if dd is None:
            return None
        sel = self._dm_finish(doc, dd, expected)
        if sel:
            self._dp_done[key] = sel
            self._dm_side[sel] = side
            try:
                if expected >= 10.0:
                    dd.ArrowSide = 0          # frecce dentro (la modalita' 'smart' le mette fuori a meno di ~30 mm e allunga la linea)
            except Exception:
                pass
        return sel

    # ------------------------------------------------------------------ catene di posizione dei fori
    def _dp_hole_chains(self, doc, v) -> List[Dict]:
        holes, org, s = self._dp_holes(v)
        core = self._dm_core(v)
        if not holes or not core:
            return []
        ttl = self._get_doc_title(doc)
        vn = self._com(v, "GetName2")
        made = []
        cols = _clusters([h["cx"] for h in holes])
        rows = _clusters([h["cy"] for h in holes])

        def circle_pts(h):
            r = h["r"] * s
            return [(h["cx"] + r, h["cy"], 0.0), (h["cx"], h["cy"] + r, 1.0), (h["cx"] - r, h["cy"], 0.0), (h["cx"], h["cy"] - r, 1.0)]

        # righe (quote verticali, a destra): bordo alto, righe dall'alto al basso, bordo basso. Foro = il piu' a destra della riga
        rows_desc = sorted(rows, reverse=True)
        ords = [("edge_top", core[3])] + [("row", y) for y in rows_desc] + [("edge_bot", core[1])]
        ov_v = self._dp_overall_exists(v, "V", core[3] - core[1])
        steps = list(zip(ords[:-1], ords[1:]))
        if ov_v and len(steps) > 1:
            steps = steps[:-1]
        W = core[2] - core[0]

        def ent_row(o):
            kind, y = o
            if kind == "row":
                hs = [h for h in holes if abs(h["cy"] - y) < TOL_CLUSTER]
                h = max(hs, key=lambda t: t["cx"])
                return circle_pts(h)
            yy = core[3] if kind == "edge_top" else core[1]
            return [(core[0] + W * f, yy, 1.0) for f in (0.95, 0.8, 0.6, 0.4)]

        for k, (a, b) in enumerate(steps):
            dv = abs(a[1] - b[1]) / s * 1000.0
            if dv < 0.05 or abs(a[1] - b[1]) < MIN_SEG:
                continue
            sel = self._dp_make(doc, (ttl, vn, "hrow", k), ent_row(a), ent_row(b), dv, True,
                                core[2] + 0.02, (a[1] + b[1]) / 2.0, +1)
            if sel:
                made.append({"view": vn, "role": "row", "value": round(dv, 3), "sel": sel})
        # colonne (quote orizzontali, sotto): bordo sinistro, colonne da sinistra a destra, bordo destro. Foro = il piu' in basso
        ords = [("edge_l", core[0])] + [("col", x) for x in cols] + [("edge_r", core[2])]
        ov_h = self._dp_overall_exists(v, "H", core[2] - core[0])
        steps = list(zip(ords[:-1], ords[1:]))
        if ov_h and len(steps) > 1:
            steps = steps[:-1]
        Hh = core[3] - core[1]

        def ent_col(o):
            kind, x = o
            if kind == "col":
                hs = [h for h in holes if abs(h["cx"] - x) < TOL_CLUSTER]
                h = min(hs, key=lambda t: t["cy"])
                return circle_pts(h)
            xx = core[0] if kind == "edge_l" else core[2]
            return [(xx, core[1] + Hh * f, 0.0) for f in (0.05, 0.2, 0.4, 0.6)]

        for k, (a, b) in enumerate(steps):
            dv = abs(a[1] - b[1]) / s * 1000.0
            if dv < 0.05 or abs(a[1] - b[1]) < MIN_SEG:
                continue
            sel = self._dp_make(doc, (ttl, vn, "hcol", k), ent_col(a), ent_col(b), dv, False,
                                (a[1] + b[1]) / 2.0, core[1] - 0.02, -1)
            if sel:
                made.append({"view": vn, "role": "col", "value": round(dv, 3), "sel": sel})
        if made:
            # le altre quote della vista (nervature, ingombri): le totali accanto alle catene, le altre dal lato opposto
            mine = set(self._dp_done.values())
            for dd in self._dq_view_dims(v):
                i = self._dp_info(v, dd)
                if i is None or i["sel"] in mine or i["axis"] not in ("H", "V") or i["callout"]:
                    continue
                size = (core[3] - core[1]) if i["axis"] == "V" else (core[2] - core[0])
                total = (i["hi"] - i["lo"]) > size * 0.97
                if i["axis"] == "V":
                    self._dm_side[i["sel"]] = +1 if total else -1
                else:
                    self._dm_side[i["sel"]] = -1 if total else +1
            try:        # quelle i cui richiami attraverserebbero il pezzo dal lato scelto: si tolgono (le misure utili tornano altrove)
                self._dp_remove_interior_dims(doc, v, core)
            except Exception as e:
                logger.debug(f"interior dims: {e}")
        return made

    # ------------------------------------------------------------------ catene di profilo
    def _dp_lines(self, v, inclined: bool = False) -> List[Tuple[float, float, float, float]]:
        """Spigoli rettilinei visibili della vista: assiali sul foglio (default) o inclinati: (x0, y0, x1, y1) in m."""
        proj = self._dm_proj(v)[0]
        out = []
        try:
            es = v.GetVisibleEntities2(win32com.client.VARIANT(pythoncom.VT_DISPATCH, None), 1)
        except Exception:
            return out
        for e in (es or ()):
            try:
                c = self._com(e, "GetCurve")
                if c is None or not bool(self._com(c, "IsLine")):
                    continue
                p0 = proj(tuple(self._com(self._com(e, "GetStartVertex"), "GetPoint")))
                p1 = proj(tuple(self._com(self._com(e, "GetEndVertex"), "GetPoint")))
                axial = abs(p0[0] - p1[0]) < 1e-5 or abs(p0[1] - p1[1]) < 1e-5
                if axial != inclined:
                    out.append((p0[0], p0[1], p1[0], p1[1]))
            except Exception:
                pass
        return out

    @staticmethod
    def _dp_is_dup(vals: Dict[float, set], vn: str, axis: str, val: float) -> bool:
        """Lo stesso valore e' gia' quotato in un'altra vista, o nella stessa vista sullo stesso asse."""
        return any(e[0] != vn or e[1] == axis for e in vals.get(round(val, 2), ()))

    def _dp_profile_chains(self, doc, v, vals: Dict[float, set]) -> List[Dict]:
        core = self._dm_core(v)
        if not core:
            return []
        _, _, s = self._dm_proj(v)
        ttl = self._get_doc_title(doc)
        vn = self._com(v, "GetName2")
        lines = [l for l in self._dp_lines(v) if math.hypot(l[2] - l[0], l[3] - l[1]) >= 0.0015]
        made = []
        for axis in ("V", "H"):
            # H: ordinate = x dei segmenti verticali; V: ordinate = y dei segmenti orizzontali
            segs = [l for l in lines if (abs(l[0] - l[2]) < 1e-5) == (axis == "H")]
            coord = (lambda l: l[0]) if axis == "H" else (lambda l: l[1])
            ords = _clusters([coord(l) for l in segs])
            if len(ords) < 2 or len(ords) > 7:
                continue
            lo, hi = ords[0], ords[-1]
            pairs = list(zip(ords[:-1], ords[1:]))
            if len(pairs) > 1:
                pairs = pairs[:-1]          # l'ultimo tratto e' implicito nella quota d'ingombro

            def cands(o):
                ss = [l for l in segs if abs(coord(l) - o) <= TOL_CLUSTER]
                ss.sort(key=lambda l: -math.hypot(l[2] - l[0], l[3] - l[1]))
                out = []
                for l in ss[:3]:
                    for f in (0.5, 0.3, 0.7):
                        x, y = l[0] + (l[2] - l[0]) * f, l[1] + (l[3] - l[1]) * f
                        out.append((x, y, 0.0 if axis == "H" else 1.0))
                return out

            def add(val, key, c1, c2, tx, ty, role):
                sel = self._dp_make(doc, key, c1, c2, val, axis == "V", tx, ty, +1)
                if sel:
                    vals.setdefault(round(val, 2), set()).add((vn, axis))
                    made.append({"view": vn, "role": role, "value": round(val, 3), "sel": sel})

            for k, (a, b) in enumerate(pairs):
                dv = (b - a) / s * 1000.0
                if (b - a) < MIN_SEG or self._dp_is_dup(vals, vn, axis, dv):
                    continue
                cx_ = (a + b) / 2.0
                tx, ty = (cx_, core[3] + 0.02) if axis == "H" else (core[2] + 0.02, cx_)
                add(dv, (ttl, vn, "prof" + axis, k), cands(a), cands(b), tx, ty, "profile" + axis)
            # quota d'ingombro mancante nella vista (se il valore non e' gia' quotato altrove)
            size = hi - lo
            sv = size / s * 1000.0
            if size >= MIN_SEG and not self._dp_overall_exists(v, axis, size) and not self._dp_is_dup(vals, vn, axis, sv):
                tx, ty = ((lo + hi) / 2.0, core[3] + 0.03) if axis == "H" else (core[2] + 0.03, (lo + hi) / 2.0)
                add(sv, (ttl, vn, "profO" + axis, 0), cands(lo), cands(hi), tx, ty, "overall" + axis)
        # spigoli inclinati (gambe di nervature, smussi grandi): estensione orizzontale e verticale, una volta per valore
        for k, l in enumerate(self._dp_lines(v, inclined=True)):
            dx, dy = abs(l[2] - l[0]), abs(l[3] - l[1])
            if min(dx, dy) < 0.003 or math.hypot(dx, dy) < 0.008:
                continue
            ang = math.degrees(math.atan2(dy, dx))
            if abs(ang - 45.0) > 40.0:       # quasi assiale: gia' coperto
                continue
            mxp, myp = (l[0] + l[2]) / 2.0, (l[1] + l[3]) / 2.0
            for axis, ext in (("H", dx), ("V", dy)):
                val = ext / s * 1000.0
                if self._dp_is_dup(vals, vn, axis, val):
                    continue
                key = (ttl, vn, "incl" + axis, k)
                alive = {str(d_.GetNameForSelection) for d_ in self._dq_view_dims(v)}
                if self._dp_done.get(key) in alive:
                    continue
                doc.ClearSelection2(True)
                if not self._select_edge_at(doc, mxp * 1000.0, myp * 1000.0, "mm"):
                    continue
                tx, ty = (mxp, core[3] + 0.02) if axis == "H" else (core[2] + 0.02, myp)
                dd = doc.AddVerticalDimension2(tx, ty, 0) if axis == "V" else doc.AddHorizontalDimension2(tx, ty, 0)
                doc.ClearSelection2(True)
                if dd is None:
                    continue
                sel = self._dm_finish(doc, dd, val)
                if sel:
                    self._dp_done[key] = sel
                    self._dm_side[sel] = +1
                    vals.setdefault(round(val, 2), set()).add((vn, axis))
                    made.append({"view": vn, "role": "inclined" + axis, "value": round(val, 3), "sel": sel})
        return made

    # ------------------------------------------------------------------ entrata
    def _dp_complete(self, doc, views: List[Any]) -> Dict:
        """Chiamata da _dq_turned dopo le quote d'ingombro/fori/cave: pulizia dei fori, catene di posizione, catene di profilo."""
        res = {"hole_dims_removed": 0, "hole_chains": [], "profile": []}
        self._dp_hcache = {}
        try:
            res["hole_dims_removed"] = self._dp_remove_hole_dims(doc, views)
        except Exception as e:
            logger.warning(f"remove hole dims: {e}")
        with_chain = set()
        for v in views:
            if self._is_pictorial(v):
                continue
            try:
                if not self._dp_grid_ok(v):
                    continue
                made = self._dp_hole_chains(doc, v)
                if made:
                    with_chain.add(self._com(v, "GetName2"))
                    res["hole_chains"] += made
            except Exception as e:
                logger.warning(f"hole chains: {e}")
        res["profile"] += self._dp_profile_all(doc, views, with_chain)
        return res

    def _dp_profile_all(self, doc, views: List[Any], skip: set) -> List[Dict]:
        out: List[Dict] = []
        vals: Dict[float, set] = {}
        for v in self._sheet_views(doc):
            vn_ = self._com(v, "GetName2")
            for dd in self._dq_view_dims(v):
                i = self._dp_info(v, dd)
                if i is not None:
                    vals.setdefault(round(float(i["value"]), 2), set()).add((vn_, i["axis"]))
        for v in views:
            if self._is_pictorial(v) or self._com(v, "GetName2") in skip:
                continue
            try:
                if not self._dp_plain_view(v):
                    continue
                out += self._dp_profile_chains(doc, v, vals)
            except Exception as e:
                logger.warning(f"profile chains: {e}")
        return out
