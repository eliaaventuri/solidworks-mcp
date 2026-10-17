"""
Drawing dimension engine (blocco 4)
-----------------------------------
Disposizione robusta delle quote di un disegno e inventario delle annotazioni.

Idea: ogni quota viene LETTA dalla sua geometria reale (IDisplayDimension.GetDisplayData: frecce, linee,
testi in coordinate foglio), non dedotta dal valore. Da li' si ricavano orientamento (orizzontale/verticale),
posizione della linea di quota, estensione lungo l'asse e riquadro del testo. Poi:

1. pulizia: duplicati (stessi punti di riferimento nel modello, anche tra viste diverse), quote di smusso
   (raccolte in una nota), quote piccolissime inutili;
2. impilamento ISO 129: quote orizzontali sopra/sotto la vista, verticali a destra/sinistra, righe a passo
   costante (8 mm) a partire da 10 mm dal contorno, dalla piu' corta alla piu' lunga, senza incroci fra
   linee di richiamo e linee di quota; piu' quote non sovrapposte condividono la stessa riga (quote in serie);
3. quote angolari con arco di raggio contenuto, diametri/raggi spostati fuori dai conflitti;
4. verifica: riquadri di tutte le annotazioni, controllo sovrapposizioni e uscite dal foglio.

Tutte le lunghezze interne sono in metri (spazio foglio), come l'API SolidWorks.
"""

import re
import math
import logging
from typing import Dict, List, Optional, Tuple, Any

from ..constants import SwErrors
from .drawing_layout import _inter, Rect

logger = logging.getLogger(__name__)

DQ_PITCH = 0.008          # passo fra le righe di quote (ISO: 7-10 mm)
DQ_FIRST = 0.010          # prima riga: distanza dal contorno del pezzo
DQ_MIN_PITCH = 0.007
DQ_PAD = 0.006            # margine che GetOutline aggiunge al contorno reale
DQ_CLEAR = 0.0015         # distanza minima fra testi/quote vicine
DQ_ANG_R = 0.011          # raggio dell'arco delle quote angolari (m)
SHEET_MARGIN = 0.012      # le quote devono stare almeno a questa distanza dal bordo foglio

KIND_LIN, KIND_ANG, KIND_RAD, KIND_DIA, KIND_OTHER = "lin", "ang", "rad", "dia", "other"


def _union(rs: List[Rect]) -> Optional[Rect]:
    rs = [r for r in rs if r]
    if not rs:
        return None
    return (min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs))


def _grow(r: Rect, m: float) -> Rect:
    return (r[0] - m, r[1] - m, r[2] + m, r[3] + m)


def _shift(r: Rect, dx: float, dy: float) -> Rect:
    return (r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy)


class DrawingDimsMixin:
    """Mixin di DrawingOperations: lettura geometria quote, impilamento, inventario, tolleranze."""

    # ------------------------------------------------------------------ lettura di una quota
    @staticmethod
    def _dq_text_w(s: str, h: float) -> float:
        """Larghezza stimata di un testo di altezza h (i token <MOD-DIAM> contano come un carattere)."""
        s2 = re.sub(r"<[^>]+>", "0", s or "")
        w = 0.0
        for ch in s2:
            w += 0.30 * h if ch in " ,." else (0.62 * h if ch.isdigit() else 0.66 * h)
        return w

    def _dq_text_rect(self, s: str, x: float, y: float, h: float, ang: float) -> Rect:
        w = self._dq_text_w(s, h)
        u = (math.cos(ang), math.sin(ang))
        n = (-math.sin(ang), math.cos(ang))
        pts = [(x + a * u[0] + b * n[0], y + a * u[1] + b * n[1]) for a in (0.0, w) for b in (-0.15 * h, 1.20 * h)]
        return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))

    def _dq_dd_data(self, dd) -> Dict:
        """Frecce, linee, testi, archi (spazio foglio) dai dati di visualizzazione della quota."""
        data = dd.GetDisplayData
        out = {"arrows": [], "lines": [], "texts": [], "arcs": []}
        try:
            for i in range(int(self._com(data, "GetArrowHeadCount"))):
                a = data.GetArrowHeadAtIndex2(i)
                out["arrows"].append((float(a[0]), float(a[1])))
            for i in range(int(self._com(data, "GetLineCount"))):
                ln = data.GetLineAtIndex3(i)
                out["lines"].append((float(ln[4]), float(ln[5]), float(ln[7]), float(ln[8])))
            for i in range(int(self._com(data, "GetTextCount"))):
                p = data.GetTextPositionAtIndex(i)
                out["texts"].append((str(data.GetTextAtIndex(i)), float(p[0]), float(p[1]),
                                     float(data.GetTextHeightAtIndex(i)), float(data.GetTextAngleAtIndex(i))))
            for i in range(int(self._com(data, "GetArcCount"))):
                a = data.GetArcAtIndex2(i)
                out["arcs"].append(tuple(float(t) for t in a))
        except Exception as e:
            logger.debug(f"display data read failed: {e}")
        return out

    def _dq_refpoints(self, dim) -> List[Tuple[float, float, float]]:
        pts = []
        try:
            for p in (dim.ReferencePoints or ()):
                try:
                    a = p.ArrayData
                    pts.append((round(float(a[0]) * 1000, 3), round(float(a[1]) * 1000, 3), round(float(a[2]) * 1000, 3)))
                except Exception:
                    pass
        except Exception:
            pass
        return pts

    def _dq_read(self, v, dd) -> Dict:
        """Tutta la geometria di una quota di disegno (m, spazio foglio)."""
        dim = dd.GetDimension2(0)
        an = dd.GetAnnotation
        pos = tuple(float(t) for t in an.GetPosition)
        t2 = int(dd.Type2)
        d = self._dq_dd_data(dd)
        try:
            callout = bool(dd.IsHoleCallout)
        except Exception:
            callout = False
        if t2 in (2, 11, 12, 15, 14):
            kind = KIND_LIN
        elif t2 in (3, 16):
            kind = KIND_ANG
        elif t2 == 5:
            kind = KIND_RAD
        elif t2 == 6:
            kind = KIND_DIA
        else:
            kind = KIND_OTHER
        if callout:
            kind = KIND_DIA
        info = {"dd": dd, "view": v, "view_name": self._com(v, "GetName2"), "type": t2, "kind": kind,
                "callout": callout, "pos": pos, "value": float(dim.Value), "name": dim.Name,
                "full": dim.FullName, "sel": str(dd.GetNameForSelection), "arrows": d["arrows"], "lines": d["lines"], "texts": d["texts"],
                "arcs": d["arcs"], "axis": None, "c": None, "lo": None, "hi": None, "anchors": [],
                "text": " ".join(t[0].strip() for t in d["texts"] if t[0].strip())}
        trect = [self._dq_text_rect(s, x, y, h, a) for s, x, y, h, a in d["texts"] if s.strip()]
        info["trect"] = _union(trect)
        info["text_angle"] = d["texts"][-1][4] if d["texts"] else 0.0
        if kind == KIND_LIN and len(d["arrows"]) >= 2:
            (x1, y1), (x2, y2) = d["arrows"][0], d["arrows"][1]
            dx, dy = x2 - x1, y2 - y1
            ln = math.hypot(dx, dy)
            if ln < 1e-7 and d["lines"]:
                l0 = max(d["lines"], key=lambda t: math.hypot(t[2] - t[0], t[3] - t[1]))
                dx, dy = l0[2] - l0[0], l0[3] - l0[1]
                ln = math.hypot(dx, dy)
            if ln > 1e-9:
                ca, sa = abs(dx) / ln, abs(dy) / ln
                axis = "H" if sa < 0.12 else ("V" if ca < 0.12 else "O")
                info["axis"] = axis
                if axis == "H":
                    info["c"] = (y1 + y2) / 2.0
                    info["lo"], info["hi"] = min(x1, x2), max(x1, x2)
                elif axis == "V":
                    info["c"] = (x1 + x2) / 2.0
                    info["lo"], info["hi"] = min(y1, y2), max(y1, y2)
                if axis in ("H", "V"):
                    ai = 0 if axis == "H" else 1     # indice lungo l'asse
                    ni = 1 - ai
                    # linee di richiamo: segmenti perpendicolari all'asse; l'estremo lontano dalla linea di quota
                    # e' l'ancora sulla geometria
                    for l in d["lines"]:
                        seg = (l[0], l[1]), (l[2], l[3])
                        da = abs(seg[0][ai] - seg[1][ai])
                        dn = abs(seg[0][ni] - seg[1][ni])
                        if da < 1e-6 and dn > 1e-6:
                            a_coord = seg[0][ai]
                            far = max((seg[0][ni], seg[1][ni]), key=lambda t: abs(t - info["c"]))
                            info["anchors"].append((a_coord, far))
                    # linee di quota (parallele all'asse, sulla coordinata c)
                    body = []
                    for l in d["lines"]:
                        seg = (l[0], l[1]), (l[2], l[3])
                        if abs(seg[0][ni] - seg[1][ni]) < 1e-6 and abs(seg[0][ni] - info["c"]) < 3e-4 and \
                                abs(seg[0][ai] - seg[1][ai]) > 1e-6:
                            body.append((min(l[0], l[2]), min(l[1], l[3]), max(l[0], l[2]), max(l[1], l[3])))
                    info["_dimlines"] = body
        # riquadro "corpo" (linee di quota + frecce + testo, senza le linee di richiamo)
        parts = []
        if info.get("_dimlines"):
            parts += info["_dimlines"]
        elif kind != KIND_LIN or info["axis"] == "O" or not d["arrows"]:
            parts += [(min(l[0], l[2]), min(l[1], l[3]), max(l[0], l[2]), max(l[1], l[3])) for l in d["lines"]]
        for ax_, ay_ in d["arrows"]:
            parts.append((ax_ - 0.0005, ay_ - 0.0005, ax_ + 0.0005, ay_ + 0.0005))
        if info["trect"]:
            parts.append(info["trect"])
        for a in d["arcs"]:
            # arco (GetArcAtIndex2): [0:4] limiti fittizi, [4:7] punto iniziale, [7:10] punto finale, [10:13] centro.
            # Riquadro = punti dell'arco piu' corto fra inizio e fine (A10: prima si usava a[0],a[1] e veniva ~ +-1000 m)
            if len(a) >= 13:
                (sx, sy), (ex, ey), (ccx, ccy) = (a[4], a[5]), (a[7], a[8]), (a[10], a[11])
                r = math.hypot(sx - ccx, sy - ccy)
                a0 = math.atan2(sy - ccy, sx - ccx)
                a1 = math.atan2(ey - ccy, ex - ccx)
                da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi        # arco piu' corto, con segno
                pts_ = [(ccx + r * math.cos(a0 + da * k / 16.0), ccy + r * math.sin(a0 + da * k / 16.0)) for k in range(17)]
                parts.append((min(p_[0] for p_ in pts_), min(p_[1] for p_ in pts_), max(p_[0] for p_ in pts_), max(p_[1] for p_ in pts_)))
            elif len(a) >= 8:
                r = math.hypot(a[5] - a[0], a[6] - a[1]) if len(a) > 6 else 0.0
                parts.append((a[0] - r, a[1] - r, a[0] + r, a[1] + r))
        info["body"] = _union(parts) or (pos[0], pos[1], pos[0], pos[1])
        info["full_rect"] = _union(parts + [(min(l[0], l[2]), min(l[1], l[3]), max(l[0], l[2]), max(l[1], l[3]))
                                            for l in d["lines"]]) or info["body"]
        info["refpts"] = self._dq_refpoints(dim)
        return info

    def _dq_view_dims(self, v) -> List[Any]:
        return self._display_dims(v)

    def _dq_core(self, v) -> Rect:
        r = self._view_rect(v)
        return (r[0] + DQ_PAD, r[1] + DQ_PAD, r[2] - DQ_PAD, r[3] - DQ_PAD)

    # ------------------------------------------------------------------ spostamento di una quota
    def _dq_move_c(self, doc, info: Dict, target_c: float, target_a: float = None) -> bool:
        """Porta la linea di quota sulla coordinata (normale all'asse) target_c e, se dato, il centro del testo
        sulla coordinata target_a (lungo l'asse); rilegge la geometria e corregge (max 4 passi)."""
        axis = info["axis"]
        dd = info["dd"]
        an = dd.GetAnnotation
        ok = False
        for _ in range(4):
            cur = info["c"]
            tr = info.get("trect")
            if tr is not None:
                cur_a = (tr[0] + tr[2]) / 2.0 if axis == "H" else (tr[1] + tr[3]) / 2.0
            else:
                cur_a = None
            dc = target_c - cur
            da = (target_a - cur_a) if (target_a is not None and cur_a is not None) else 0.0
            if abs(dc) < 2e-4 and abs(da) < 6e-4:
                ok = True
                break
            pos = tuple(float(t) for t in an.GetPosition)
            if axis == "H":
                an.SetPosition2(pos[0] + da, pos[1] + dc, pos[2])
            else:
                an.SetPosition2(pos[0] + dc, pos[1] + da, pos[2])
            new = self._dq_read(info["view"], dd)
            for k in ("pos", "arrows", "lines", "texts", "c", "lo", "hi", "anchors", "body", "trect", "full_rect",
                      "_dimlines"):
                if k in new:
                    info[k] = new[k]
        return ok or abs(target_c - info["c"]) < 5e-4

    # ------------------------------------------------------------------ ostacoli e spazio libero
    def _dq_usable(self, doc) -> Rect:
        W, H, _ = self._sheet_dims(doc)
        return (SHEET_MARGIN + 0.013, SHEET_MARGIN + 0.013, W - SHEET_MARGIN - 0.013, H - SHEET_MARGIN - 0.013)

    def _dq_obstacles(self, doc, exclude_view=None) -> List[Rect]:
        """Viste altrui, cartiglio, zone riservate (es. distinta)."""
        W, H, _ = self._sheet_dims(doc)
        rects = [self._title_rect(W, H)] + self._reserved_rects(doc)
        ex = self._com(exclude_view, "GetName2") if exclude_view is not None else None
        for v in self._sheet_views(doc):
            if ex is not None and self._com(v, "GetName2") == ex:
                continue
            rects.append(self._view_rect(v))
        # tabelle, tolleranze, rugosita', note (non le quote: quelle sono gestite una per una)
        try:
            for a in self._dq_annotations(doc):
                if a["kind"] in ("table", "gtol", "surface_finish") or (a["kind"] == "note" and a.get("view") == "sheet"):
                    rects.append(tuple(a["rect"]))
        except Exception as e:
            logger.debug(f"obstacle annotations: {e}")
        return rects

    def _dq_room(self, doc, core: Rect, axis: str, side: int, obstacles: List[Rect]) -> float:
        """Spazio libero (m) oltre il contorno `core` nella direzione `side` (+1/-1) dell'asse normale
        (H: y; V: x), fino al primo ostacolo o al bordo utile del foglio."""
        use = self._dq_usable(doc)
        if axis == "H":
            lo, hi = core[0], core[2]
            edge = core[3] if side > 0 else core[1]
            limit = use[3] if side > 0 else use[1]
            best = abs(limit - edge)
            for r in obstacles:
                if r[2] <= lo or r[0] >= hi:
                    continue
                if side > 0 and r[1] >= edge - 1e-6:
                    best = min(best, r[1] - edge)
                elif side < 0 and r[3] <= edge + 1e-6:
                    best = min(best, edge - r[3])
        else:
            lo, hi = core[1], core[3]
            edge = core[2] if side > 0 else core[0]
            limit = use[2] if side > 0 else use[0]
            best = abs(limit - edge)
            for r in obstacles:
                if r[3] <= lo or r[1] >= hi:
                    continue
                if side > 0 and r[0] >= edge - 1e-6:
                    best = min(best, r[0] - edge)
                elif side < 0 and r[2] <= edge + 1e-6:
                    best = min(best, edge - r[2])
        return max(best, 0.0)

    # ------------------------------------------------------------------ pulizia
    def _dq_is_chamfer_dim(self, info: Dict) -> bool:
        try:
            dim = info["dd"].GetDimension2(0)
            feat = dim.GetFeatureOwner
            if feat is not None:
                tn = str(self._com(feat, "GetTypeName2"))
                return tn.lower() in ("chamfer",)
        except Exception:
            pass
        return False

    def _dq_cleanup(self, doc, views: List[Any], remove_chamfer_dims: bool = True) -> Dict:
        """Duplicati (anche fra viste), quote di smusso e quote inutilmente piccole. Restituisce statistiche."""
        stats = {"duplicates": 0, "chamfer": 0, "tiny": 0, "chamfer_note": []}
        infos = []
        for v in views:
            for dd in self._dq_view_dims(v):
                try:
                    infos.append(self._dq_read(v, dd))
                except Exception as e:
                    logger.debug(f"dim read failed: {e}")
        if not infos:
            return stats
        # ordine di preferenza delle viste: come nel foglio (la prima e' la frontale)
        order = {self._com(v, "GetName2"): i for i, v in enumerate(self._sheet_views(doc))}
        to_delete: List[Dict] = []

        def mark(i, why):
            if not any(i is t for t in to_delete):
                to_delete.append(i)
                stats[why] += 1

        # 1) smussi: quote delle feature smusso (angolo 45 + distanza) -> nota "SMUSSI ..."
        if remove_chamfer_dims:
            by_owner: Dict[str, List[Dict]] = {}
            for i in infos:
                if i["kind"] in (KIND_LIN, KIND_ANG) and self._dq_is_chamfer_dim(i):
                    try:
                        owner = str(self._com(i["dd"].GetDimension2(0).GetFeatureOwner, "Name"))
                    except Exception:
                        owner = i["name"].split("@")[1] if "@" in i["name"] else i["name"]
                    by_owner.setdefault(owner, []).append(i)
            for owner, ds in by_owner.items():
                ang = [d for d in ds if d["kind"] == KIND_ANG]
                lin = [d for d in ds if d["kind"] == KIND_LIN]
                if lin and ang and all(abs(abs(a["value"]) - 45.0) < 1e-6 or abs(abs(a["value"]) - 0.7853981634) < 1e-6
                                       for a in ang):
                    label = f"{lin[0]['value']:g}x45°"          # IDimension.Value e' nell'unita' del documento (mm)
                    stats["chamfer_note"].append(label)
                    for d in ds:
                        mark(d, "chamfer")
        # 2) duplicati: stessa chiave (valore, tipo, punti di riferimento del modello) -> teniamo la vista preferita
        groups: Dict[Tuple, List[Dict]] = {}
        for i in infos:
            if any(i is t for t in to_delete):
                continue
            if i["refpts"] and i["kind"] in (KIND_LIN, KIND_ANG, KIND_RAD, KIND_DIA):
                pts = tuple(sorted(i["refpts"]))
                key = (round(i["value"], 6), i["kind"], pts)
            else:
                key = (round(i["value"], 6), i["kind"], i["axis"], round(i["pos"][0] / 0.003), round(i["pos"][1] / 0.003),
                       i["view_name"])
            groups.setdefault(key, []).append(i)
        for key, g in groups.items():
            if len(g) > 1:
                g.sort(key=lambda t: (t["callout"] is False, order.get(t["view_name"], 99)))
                keep = g[0]
                for t in g:
                    if t is keep:
                        continue
                    mark(t, "duplicates")
        # un Ø semplice dello stesso valore di un callout foro nella stessa vista e' ridondante
        for v in views:
            vn = self._com(v, "GetName2")
            call_vals = {round(i["value"], 6) for i in infos if i["view_name"] == vn and i["callout"]}
            for i in infos:
                if i["view_name"] == vn and not i["callout"] and i["kind"] in (KIND_DIA, KIND_RAD) \
                        and round(i["value"], 6) in call_vals:
                    mark(i, "duplicates")
        for i in to_delete:
            self._delete_dim_full(doc, i["sel"])
        return stats

    def _delete_dim_full(self, doc, full: str) -> bool:
        doc.ClearSelection2(True)
        ok = doc.Extension.SelectByID2(full, "DIMENSION", 0, 0, 0, False, 0, self._NULL, 0)
        if ok:
            doc.Extension.DeleteSelection2(0)
        doc.ClearSelection2(True)
        return bool(ok)

    # ------------------------------------------------------------------ impilamento
    def _dq_assign_rows(self, items: List[Dict], axis_lo_key="lo") -> List[int]:
        """Righe di quote: dalla piu' corta alla piu' lunga, la riga piu' bassa libera, senza incroci fra le
        linee di richiamo di una quota e le quote delle righe interne. Restituisce la riga di ciascun item."""
        order = sorted(range(len(items)), key=lambda k: (items[k]["hi"] - items[k]["lo"], items[k]["lo"]))
        rows: List[int] = [-1] * len(items)
        placed: List[Tuple[int, int]] = []        # (indice item, riga)

        def span(it):
            if it.get("span"):
                return it["span"][0] - DQ_CLEAR, it["span"][1] + DQ_CLEAR
            lo, hi = it["lo"], it["hi"]
            b = it["body"]
            if it["axis"] == "H":
                lo, hi = min(lo, b[0]), max(hi, b[2])
            else:
                lo, hi = min(lo, b[1]), max(hi, b[3])
            return lo - DQ_CLEAR, hi + DQ_CLEAR

        def span_raw(it):
            if it.get("span"):
                return it["span"][0], it["span"][1]
            return it["lo"], it["hi"]

        def exts(it):
            return [a for a, _ in it["anchors"]] or [it["lo"], it["hi"]]

        for k in order:
            it = items[k]
            r = 0
            strict = True
            while True:
                if r > len(items) + 1:
                    strict = False        # incroci inevitabili: si guarda solo la sovrapposizione nella stessa riga
                if r > 4 * len(items) + 8:
                    break
                ok = True
                lo, hi = span(it)
                for (j, rj) in placed:
                    o = items[j]
                    lo2, hi2 = span(o)
                    if rj == r:
                        # quote in catena: due tratti che si toccano nello stesso punto d'ancoraggio stanno sulla stessa riga
                        # (il margine DQ_CLEAR non deve separarle)
                        a0, a1 = span_raw(it)
                        b0, b1 = span_raw(o)
                        touching = abs(a1 - b0) < 2e-4 or abs(b1 - a0) < 2e-4
                        if not touching and not (hi <= lo2 or hi2 <= lo):
                            ok = False
                            break
                    elif not strict:
                        continue
                    elif rj < r:
                        # le linee di richiamo di `it` attraversano la riga rj: non devono cadere dentro una quota di rj
                        # (un'ancora in comune e' la stessa linea di richiamo: non e' un incrocio)
                        if any(lo2 + DQ_CLEAR < e < hi2 - DQ_CLEAR and not any(abs(e - a2) < 5e-4 for a2 in exts(o)) for e in exts(it)):
                            ok = False
                            break
                    else:
                        if any(lo + DQ_CLEAR < e < hi - DQ_CLEAR and not any(abs(e - a2) < 5e-4 for a2 in exts(it)) for e in exts(o)):
                            ok = False
                            break
                if ok:
                    break
                r += 1
            rows[k] = r
            placed.append((k, r))
        return rows

    def _dq_arrange_view(self, doc, v, placed_rects: List[Rect], pitch: float, first: float) -> Dict:
        """Impila le quote lineari di una vista ortogonale, sistema angolari e diametri."""
        core = self._dq_core(v)
        vname = self._com(v, "GetName2")
        infos = []
        for dd in self._dq_view_dims(v):
            try:
                infos.append(self._dq_read(v, dd))
            except Exception as e:
                logger.debug(f"dim read failed: {e}")
        res = {"view": vname, "moved": 0, "warnings": [], "rows": {}}
        obstacles = self._dq_obstacles(doc, exclude_view=v) + placed_rects
        try:        # titolo della vista (SEZIONE A-A, DETTAGLIO B...): le quote non devono finirci sopra -> si sceglie l'altro lato
            obstacles += self._dq_label_rects(v)
        except Exception as e:
            logger.debug(f"view label obstacle: {e}")
        self._dq_usable(doc)
        for axis in ("H", "V"):
            items = [i for i in infos if i["kind"] == KIND_LIN and i["axis"] == axis]
            if not items:
                continue
            # lato: quello con piu' spazio libero (a parita', sopra / destra)
            rooms = {s: self._dq_room(doc, core, axis, s, obstacles) for s in (1, -1)}
            pref = 1 if rooms[1] >= rooms[-1] - 0.002 else -1
            cap = {s: (int((rooms[s] - first - 0.004) // pitch) + 1 if rooms[s] >= first + 0.004 else 0) for s in (1, -1)}
            for it in items:
                th = it["texts"][-1][3] if it["texts"] else 0.0035
                tw = self._dq_text_w(it["text"], th)
                if tw + 0.008 <= it["hi"] - it["lo"]:
                    it["along"] = (it["lo"] + it["hi"]) / 2.0
                    it["span"] = (it["lo"], it["hi"])
                    try:        # il testo ci sta fra le linee di richiamo: frecce dentro (altrimenti 'smart' le mette fuori e allunga la linea)
                        if tw + 0.012 <= it["hi"] - it["lo"] and int(it["dd"].ArrowSide) != 0:
                            it["dd"].ArrowSide = 0
                    except Exception:
                        pass
                else:
                    it["along"] = it["hi"] + 0.003 + tw / 2.0
                    it["span"] = (it["lo"], it["hi"] + 0.003 + tw)
            rows = self._dq_assign_rows(items)
            nrows = max(rows) + 1
            side_of = {}
            for it in items:
                it["pref"] = self._dm_side.get(it["sel"])
            if any(it["pref"] for it in items):
                side_of = {k: (items[k]["pref"] or pref) for k in range(len(items))}
                for s_ in (1, -1):
                    ks = [k for k in range(len(items)) if side_of[k] == s_]
                    rr = self._dq_assign_rows([items[k] for k in ks]) if ks else []
                    for k, r_ in zip(ks, rr):
                        rows[k] = r_
            elif nrows <= cap[pref]:
                side_of = {k: pref for k in range(len(items))}
            else:
                # le righe che non stanno vanno dall'altra parte (le piu' lunghe per ultime), se c'e' posto
                other = -pref
                if cap[pref] + cap[other] >= nrows or cap[other] > 0:
                    sub_pref = [k for k in range(len(items)) if rows[k] < max(cap[pref], 1)]
                    rest = [k for k in range(len(items)) if k not in sub_pref]
                    for k in sub_pref:
                        side_of[k] = pref
                    for k in rest:
                        side_of[k] = other
                    # ricalcola le righe per ciascun lato
                    for s in (pref, other):
                        ks = [k for k in range(len(items)) if side_of.get(k) == s]
                        rr = self._dq_assign_rows([items[k] for k in ks]) if ks else []
                        for k, r_ in zip(ks, rr):
                            rows[k] = r_
                else:
                    side_of = {k: pref for k in range(len(items))}
                    res["warnings"].append(f"{vname}: spazio insufficiente per {nrows} righe di quote {axis}")
            # altezza di ogni riga: almeno il passo, ma una quota alta (testo su due righe: limiti, tolleranze) ne richiede di piu'
            heights: Dict[Tuple[int, int], float] = {}
            for k, it in enumerate(items):
                b_ = it["body"]
                ext_ = (b_[3] - b_[1]) if axis == "H" else (b_[2] - b_[0])
                key_ = (side_of[k], rows[k])
                heights[key_] = max(heights.get(key_, 0.0), ext_ + DQ_CLEAR)

            def row_offset(s_, r_):
                return sum(max(pitch, heights.get((s_, q_), pitch)) for q_ in range(r_))
            for k, it in enumerate(items):
                s = side_of[k]
                if axis == "H":
                    edge = core[3] if s > 0 else core[1]
                else:
                    edge = core[2] if s > 0 else core[0]
                target = edge + s * (first + row_offset(s, rows[k]))
                if self._dq_move_c(doc, it, target, it.get("along")):
                    res["moved"] += 1
                it["_side"], it["_row"] = s, rows[k]
                res["rows"].setdefault(f"{axis}{'+' if s > 0 else '-'}", []).append(
                    {"value": round(it["value"], 4), "row": rows[k]})
        # angolari: ricostruiti sugli spigoli che si incontrano davvero (A10), altrimenti arco di raggio contenuto
        for i in infos:
            if i["kind"] != KIND_ANG:
                continue
            try:
                if self._dq_rebuild_angular(doc, v, i, core):
                    res["moved"] += 1
                    res.setdefault("angular_rebuilt", 0)
                    res["angular_rebuilt"] += 1
                elif self._dq_fix_angular(doc, i, core):
                    res["moved"] += 1
            except Exception as e:
                logger.debug(f"angular fix failed: {e}")
        # quote di diametro dei cerchi: testo fuori dal contorno, lungo raggi liberi
        try:
            blockers = []
            for dd_ in self._dq_view_dims(v):
                try:
                    i_ = self._dq_read(v, dd_)
                except Exception:
                    continue
                if i_["kind"] not in (KIND_DIA, KIND_RAD):
                    blockers.append(_grow(i_["body"], DQ_CLEAR))
            cc = self._dm_core(v) or core
            res["moved"] += self._dm_arrange_circles(doc, v, cc, blockers + obstacles, placed_rects)
        except Exception as e:
            logger.debug(f"circle dims failed: {e}")
        # raccolgo i riquadri delle quote rimaste nella vista come ostacoli per le viste successive
        for dd in self._dq_view_dims(v):
            try:
                i = self._dq_read(v, dd)
                placed_rects.append(_grow(i["body"], DQ_CLEAR))
            except Exception:
                pass
        return res

    # ------------------------------------------------------------------ quote angolari (A10)
    def _dq_rebuild_angular(self, doc, v, i: Dict, core: Rect) -> bool:
        """Quota angolare importata da uno schizzo fra due linee che NON si toccano nella vista: il vertice virtuale cade lontano
        (anche fuori dal foglio) e le linee di richiamo attraversano tutto. La si sostituisce con una quota angolare del
        disegno fra due spigoli della vista che condividono davvero un vertice e formano lo stesso angolo (theta o 180-theta);
        il testo sta fuori dal pezzo, sulla bisettrice dell'angolo, a ~15 mm dal vertice. Restituisce True se ricostruita."""
        m_ = re.search(r"(-?\d+(?:[.,]\d+)?)", i.get("text", "") or "")
        if not m_:
            return False
        theta = abs(float(m_.group(1).replace(",", ".")))
        if not (1.0 <= theta <= 179.0):
            return False
        segs, _ = self._an_geom_obstacles(v)
        # segmenti non degeneri, senza duplicati (spigoli anteriori e posteriori coincidenti)
        uniq = []
        for sg in segs:
            if math.hypot(sg[2] - sg[0], sg[3] - sg[1]) < 0.002:
                continue
            key = tuple(round(t / 0.0002) for t in (min((sg[0], sg[1]), (sg[2], sg[3])) + max((sg[0], sg[1]), (sg[2], sg[3]))))
            if all(k != key for k, _ in uniq):
                uniq.append((key, sg))
        segs = [sg for _, sg in uniq]
        cx, cy = (core[0] + core[2]) / 2.0, (core[1] + core[3]) / 2.0
        cands = []
        for a in range(len(segs)):
            for b in range(a + 1, len(segs)):
                for ea in (0, 1):
                    for eb in (0, 1):
                        pa = (segs[a][2 * ea], segs[a][2 * ea + 1])
                        pb = (segs[b][2 * eb], segs[b][2 * eb + 1])
                        if math.hypot(pa[0] - pb[0], pa[1] - pb[1]) > 2e-4:
                            continue
                        oa = (segs[a][2 * (1 - ea)], segs[a][2 * (1 - ea) + 1])
                        ob = (segs[b][2 * (1 - eb)], segs[b][2 * (1 - eb) + 1])
                        d1 = (oa[0] - pa[0], oa[1] - pa[1])
                        d2 = (ob[0] - pa[0], ob[1] - pa[1])
                        n1, n2 = math.hypot(*d1), math.hypot(*d2)
                        d1, d2 = (d1[0] / n1, d1[1] / n1), (d2[0] / n2, d2[1] / n2)
                        psi = math.degrees(math.acos(max(-1.0, min(1.0, d1[0] * d2[0] + d1[1] * d2[1]))))
                        if abs(psi - theta) < 0.4 or abs(psi - (180.0 - theta)) < 0.4:
                            cands.append({"v": pa, "d1": d1, "d2": d2, "a": a, "b": b, "psi": psi,
                                          "dist": math.hypot(pa[0] - cx, pa[1] - cy)})
        if not cands:
            return False
        cands.sort(key=lambda c: -c["dist"])
        i["dd"].GetAnnotation
        for c in cands[:3]:
            vx, vy = c["v"]
            d1, d2 = c["d1"], c["d2"]
            R_ = 0.015
            # direzioni delle due semirette che delimitano l'angolo theta: se l'angolo fra gli spigoli e' 180-theta,
            # si prolunga uno dei due (verso l'esterno del pezzo)
            opts = []
            if abs(c["psi"] - theta) < 0.4:
                opts.append((d1, d2))
            if abs(c["psi"] - (180.0 - theta)) < 0.4:
                opts.append(((-d1[0], -d1[1]), d2))
                opts.append((d1, (-d2[0], -d2[1])))
            best = None
            for ra, rb in opts:
                bx, by = ra[0] + rb[0], ra[1] + rb[1]
                bn = math.hypot(bx, by)
                if bn < 1e-6:
                    continue
                bx, by = bx / bn, by / bn
                outward = (vx + bx * R_ - cx) ** 2 + (vy + by * R_ - cy) ** 2
                if best is None or outward > best[0]:
                    best = (outward, bx, by)
            if best is None:
                continue
            _, bx, by = best
            tx, ty = vx + bx * R_, vy + by * R_

            def pts_on(seg, ea_):
                # tre punti candidati sul segmento (lontano dal vertice), scarto di selezione sull'asse meno parallelo
                out = []
                for f in (0.5, 0.35, 0.65):
                    x = seg[0] + (seg[2] - seg[0]) * f
                    y = seg[1] + (seg[3] - seg[1]) * f
                    out.append((x, y, 1.0 if abs(seg[2] - seg[0]) >= abs(seg[3] - seg[1]) else 0.0))
                return out
            if not self._dm_select_pair(doc, pts_on(segs[c["a"]], 0), pts_on(segs[c["b"]], 0)):
                continue
            dd2 = doc.AddDimension2(tx, ty, 0)
            doc.ClearSelection2(True)
            if dd2 is None:
                continue
            try:
                val = float(dd2.GetDimension2(0).Value)
                if abs(val) <= 6.5 and theta > 6.5:
                    val = math.degrees(val)
                if abs(abs(val) - theta) > 0.3:
                    # l'angolo letto e' il supplementare: prova a portare il testo nel quadrante opposto
                    self._delete_dim_full(doc, str(dd2.GetNameForSelection))
                    continue
                dd2.GetAnnotation.Color = 0
            except Exception as e:
                logger.debug(f"angular rebuild check: {e}")
                self._delete_dim_full(doc, str(dd2.GetNameForSelection))
                continue
            # il testo deve stare fuori dal contorno della vista: lo si allontana lungo la bisettrice
            try:
                an2 = dd2.GetAnnotation
                for _ in range(8):
                    tr = self._dq_read(v, dd2)["trect"]
                    if tr is None or not _inter(tr, _grow(core, -0.0003)):
                        break
                    pos2 = tuple(float(t) for t in an2.GetPosition)
                    an2.SetPosition2(pos2[0] + bx * 0.003, pos2[1] + by * 0.003, pos2[2])
            except Exception as e:
                logger.debug(f"angular push out: {e}")
            self._delete_dim_full(doc, i["sel"])
            return True
        return False

    def _dq_fix_angular(self, doc, i: Dict, core: Rect) -> bool:
        """Arco della quota angolare: centro = vertice (centro dell'arco nei dati), raggio ~ DQ_ANG_R, testo
        fuori dal contorno della vista, verso l'esterno."""
        arcs = i["arcs"]
        if not arcs:
            return False
        a = arcs[0]
        cx, cy = a[0], a[1]
        math.hypot(a[5] - cx, a[6] - cy) if len(a) > 6 else 0.0
        an = i["dd"].GetAnnotation
        pos = tuple(float(t) for t in an.GetPosition)
        # direzione dal vertice verso la posizione attuale del testo
        dx, dy = pos[0] - cx, pos[1] - cy
        n = math.hypot(dx, dy)
        # verso l'esterno rispetto al centro della vista
        ccx, ccy = (core[0] + core[2]) / 2.0, (core[1] + core[3]) / 2.0
        ox, oy = cx - ccx, cy - ccy
        on = math.hypot(ox, oy) or 1.0
        if n < 1e-9 or (dx * ox + dy * oy) < 0:
            dx, dy, n = ox, oy, on
        # il raggio deve portare il testo fuori dal contorno (margine DQ_PAD)
        r = DQ_ANG_R
        nx, ny = cx + dx / n * r, cy + dy / n * r
        an.SetPosition2(nx, ny, pos[2])
        return True

    # ------------------------------------------------------------------ API pubblica: disposizione
    def _dq_ortho_views(self, doc, view_name: Optional[str] = None) -> List[Any]:
        vs = []
        for v in self._sheet_views(doc):
            if view_name and self._com(v, "GetName2") != view_name:
                continue
            if self._is_pictorial(v):
                continue
            vs.append(v)
        return vs

    def _dq_turned(self, doc, views: List[Any]) -> Dict:
        """Pezzi di rivoluzione: quote radiali importate -> quote lineari con Ø sui cilindri."""
        res = {"removed": 0, "added": []}
        infos_all = []
        for v in views:
            for dd in self._dq_view_dims(v):
                try:
                    infos_all.append(self._dq_read(v, dd))
                except Exception:
                    pass
        existing = set()
        for i in infos_all:
            if i["kind"] == KIND_DIA:
                existing.add(round(i["value"], 4))
            elif i["kind"] == KIND_RAD:
                existing.add(round(2 * i["value"], 4))
        side_count = {1: 0, -1: 0}
        for v in views:
            info = self._dm_cylinders(v)
            if not info:
                continue
            vn = self._com(v, "GetName2")
            res["removed"] += self._dm_remove_radial(doc, info, [i for i in infos_all if i["view_name"] == vn])
            res["added"] += self._dm_add_diameters(doc, v, info, existing, side_count)
        res["overall"], res["holes"], res["pockets"] = [], [], []
        lin_vals = {round(float(i["value"]), 2) for i in infos_all if i["kind"] == KIND_LIN}
        for v in views:
            vn = self._com(v, "GetName2")
            vinfos = []
            for dd in self._dq_view_dims(v):
                try:
                    vinfos.append(self._dq_read(v, dd))
                except Exception:
                    pass
            try:
                res["overall"] += self._dm_overall(doc, v, vinfos, lin_vals)
                res["holes"] += self._dm_holes(doc, v, existing)
                res["pockets"] += self._dm_pockets(doc, v, lin_vals)
            except Exception as e:
                logger.warning(f"complete dims {vn}: {e}")
        try:        # (A17) fori in catena dal bordo, quote di profilo (spessori, nervature) senza duplicati
            res["positions"] = self._dp_complete(doc, views)
        except Exception as e:
            logger.warning(f"position dims: {e}")
        return res

    def _dq_dedupe_diameters(self, doc, views: List[Any]) -> int:
        """Una sola quota per ogni diametro (Ø lineare, Ø di cerchio, raggio*2): tiene quella con il numero di
        fori ('6x') o la prima della vista preferita."""
        infos = []
        for v in views:
            for dd in self._dq_view_dims(v):
                try:
                    infos.append(self._dq_read(v, dd))
                except Exception:
                    pass
        order = {self._com(v, "GetName2"): k for k, v in enumerate(self._sheet_views(doc))}
        groups: Dict[float, List[Dict]] = {}
        for i in infos:
            if i["kind"] == KIND_DIA:
                key = round(i["value"], 3)
            elif i["kind"] == KIND_RAD:
                key = round(2 * i["value"], 3)
            elif i["kind"] == KIND_LIN and "<MOD-DIAM>" in " ".join(t[0] for t in i["texts"]):
                key = round(i["value"], 3)
            else:
                continue
            groups.setdefault(key, []).append(i)
        n = 0
        for key, g in groups.items():
            if len(g) < 2:
                continue
            g.sort(key=lambda t: (0 if re.search(r"\dx", t["text"] or "") else 1, order.get(t["view_name"], 99)))
            for t in g[1:]:
                if self._delete_dim_full(doc, t["sel"]):
                    n += 1
        return n

    def _dq_label_rects(self, v) -> List[Rect]:
        """Riquadri delle note (titoli di vista, lettere) attaccate alla vista: lettura leggera, senza leggere le quote."""
        out = []
        a = v.GetFirstAnnotation3
        while a is not None:
            try:
                if int(a.GetType) == 6:
                    r = self._dq_note_rect(a)
                    if r:
                        out.append(tuple(r))
            except Exception:
                pass
            a = a.GetNext3
        return out

    def _dq_has_circle_dims(self, v) -> bool:
        try:
            for dd in self._dq_view_dims(v):
                try:
                    if int(dd.Type2) in (5, 6) or bool(dd.IsHoleCallout):
                        return True
                except Exception:
                    pass
        except Exception:
            pass
        return False

    def _dq_run(self, doc, views: List[Any], pitch: float = None, first: float = None,
                cleanup: bool = True, turned: bool = True) -> Dict:
        pitch = pitch or DQ_PITCH
        first = first or DQ_FIRST
        stats = {"duplicates": 0, "chamfer": 0, "tiny": 0, "chamfer_note": []}
        if cleanup:
            stats = self._dq_cleanup(doc, views)
        dia = {"removed": 0, "added": []}
        if turned:
            try:
                dia = self._dq_turned(doc, views)
            except Exception as e:
                logger.warning(f"turned dims failed: {e}")
        stats["diameters"] = dia
        try:
            stats["duplicates"] += self._dq_dedupe_diameters(doc, views)
        except Exception as e:
            logger.debug(f"dedupe diameters: {e}")
        placed: List[Rect] = []
        results = []
        # prima le viste con piu' quote (la frontale), cosi' le altre si adattano
        # le viste con quote di cerchi (callout dei fori, Ø) per ultime: i loro richiami lunghi evitano cosi' tutte le quote lineari
        # delle altre viste, gia' al loro posto (altrimenti il testo di un Ø finiva sopra le quote di una sezione)
        views_sorted = sorted(views, key=lambda v: (self._dq_has_circle_dims(v), -self._count_dims(v)))
        for v in views_sorted:
            results.append(self._dq_arrange_view(doc, v, placed, pitch, first))
        try:
            self._dq_chamfer_note(doc, stats.get("chamfer_note", []))
        except Exception as e:
            logger.debug(f"chamfer note: {e}")
        try:
            self._an_retag(doc)
        except Exception as e:
            logger.debug(f"retag after arrange: {e}")
        return {"cleanup": stats, "views": results}

    def arrange_drawing_dimensions(self, view: str = None, pitch: float = None, first_offset: float = None,
                                   cleanup: bool = True, unit: str = None) -> Dict:
        """Riordina le quote del foglio attivo (o di una vista): rimuove duplicati (anche fra viste) e quote di
        smusso, poi le impila secondo ISO 129 (orizzontali sopra/sotto, verticali a destra/sinistra, passo
        costante, dalla piu' corta alla piu' lunga, senza incroci); angolari con arco contenuto.
        pitch/first_offset in mm (default 8 / 10)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            vname = None
            if view:
                v, err = self._find_view(doc, view)
                if err:
                    return err
                vname = self._com(v, "GetName2")
            views = self._dq_ortho_views(doc, vname)
            if not views:
                return self._result(False, "Nessuna vista ortogonale da quotare.", SwErrors.swInvalidInput)
            pm = pitch / 1000.0 if pitch else None
            fm = first_offset / 1000.0 if first_offset else None
            out = self._dq_run(doc, views, pm, fm, cleanup)
            warns = [w for r in out["views"] for w in r["warnings"]]
            moved = sum(r["moved"] for r in out["views"])
            msg = f"Quote riordinate: {moved} spostate, {out['cleanup']['duplicates']} duplicati rimossi"
            if out["cleanup"]["chamfer"]:
                msg += f", {out['cleanup']['chamfer']} quote di smusso -> nota"
            if warns:
                msg += " - ATTENZIONE: " + "; ".join(warns)
            return self._result(True, msg, SwErrors.swSuccess, {
                "moved": moved, "duplicates_removed": out["cleanup"]["duplicates"],
                "chamfer_dims_removed": out["cleanup"]["chamfer"], "chamfer_note": out["cleanup"]["chamfer_note"],
                "warnings": warns, "views": [{k: r[k] for k in ("view", "moved", "rows")} for r in out["views"]]})
        except Exception as e:
            return self._fail("arrange_drawing_dimensions", e)

    # ------------------------------------------------------------------ inventario annotazioni
    def _dq_note_rect(self, ann) -> Optional[Rect]:
        try:
            n = ann.GetSpecificAnnotation
            ex = n.GetExtent
            if ex:
                try:        # note con richiamo (lettera della vista ausiliaria...): l'estensione include la linea di richiamo, che e' una
                    if int(ann.GetLeaderCount) > 0:      # freccia verso lo spigolo e non occupa spazio: si prende il solo testo
                        pos = [float(t) for t in ann.GetPosition]
                        lines_ = str(n.GetText).replace(chr(13), "").split(chr(10)) or [""]
                        w_ = max(len(l_) for l_ in lines_) * 0.0023 + 0.002
                        h_ = 0.0055 * len(lines_)
                        return (pos[0] - 0.0005, pos[1] - h_, pos[0] + w_, pos[1] + 0.0005)
                except Exception:
                    pass
                return (min(ex[0], ex[3]), min(ex[1], ex[4]), max(ex[0], ex[3]), max(ex[1], ex[4]))
        except Exception:
            pass
        return None

    def _dq_gtol_lines(self, ann):
        """Linee di una tolleranza geometrica (x0,y0,x1,y1 in m): (parallele agli assi = riquadro, oblique = linea di richiamo)."""
        frame, leader = [], []
        try:
            g = ann.GetSpecificAnnotation
            for i in range(int(self._com(g, "GetLineCount"))):
                l = g.GetLineAtIndex(i)
                seg = (l[1], l[2], l[4], l[5])
                if abs(seg[0] - seg[2]) < 1e-5 or abs(seg[1] - seg[3]) < 1e-5:
                    frame.append(seg)
                else:
                    leader.append(seg)
        except Exception:
            pass
        return frame, leader

    def _dq_gtol_rect(self, ann) -> Optional[Rect]:
        """Riquadro della tolleranza SENZA il bounding box della linea di richiamo obliqua (quella e' controllata a parte,
        come segmento: il suo rettangolo coprirebbe mezzo foglio)."""
        frame, leader = self._dq_gtol_lines(ann)
        pts = [(min(l[0], l[2]), min(l[1], l[3]), max(l[0], l[2]), max(l[1], l[3])) for l in (frame or leader)]
        return _union(pts) if pts else None

    def _dq_table_rect(self, ann) -> Optional[Rect]:
        try:
            t = ann.GetSpecificAnnotation
            w = sum(float(t.GetColumnWidth(i)) for i in range(int(t.ColumnCount)))
            h = sum(float(t.GetRowHeight(i)) for i in range(int(t.RowCount)))
            p = tuple(float(x) for x in ann.GetPosition)
            # AnchorType: l'angolo di ancoraggio e' tipicamente in alto a sinistra; verifica con i dati reali
            return (p[0], p[1] - h, p[0] + w, p[1])
        except Exception:
            return None

    def _dq_sf_rect(self, a, pos) -> Rect:
        """Riquadro di un simbolo di finitura (punta in `pos`): simbolo -2,95..+5,9 x 0..10 mm piu', se c'e', il testo sopra la barra."""
        r = [pos[0] - 0.00295, pos[1], pos[0] + 0.0059, pos[1] + 0.010]
        try:
            t = str(a.GetSpecificAnnotation.GetText(2) or "")
            if t:
                r[2] = max(r[2], pos[0] + 0.007 + 0.00232 * len(t) + 0.002)
                r[3] = pos[1] + 0.0145
        except Exception:
            pass
        return (r[0], r[1], r[2], r[3])

    def _dq_annotations(self, doc) -> List[Dict]:
        """Riquadri (m) di tutte le annotazioni dei fogli attivo: quote, note, tolleranze, rugosita', riferimenti,
        tabelle. Le quote hanno anche asse/lato/riga."""
        out = []
        W, H, _ = self._sheet_dims(doc)
        title = self._title_rect(W, H)
        use = (0.025, 0.025, W - 0.025, H - 0.025)
        for v in self._sheet_views(doc):
            vname = self._com(v, "GetName2")
            a = v.GetFirstAnnotation3
            while a is not None:
                t = int(a.GetType)
                try:
                    pos = tuple(float(x) for x in a.GetPosition)
                    if t == 4:
                        dd = a.GetSpecificAnnotation
                        i = self._dq_read(v, dd)
                        out.append({"kind": "dimension", "view": vname, "text": i["text"], "rect": i["body"],
                                    "full": i["full_rect"], "axis": i["axis"], "dim_kind": i["kind"], "c": i["c"],
                                    "lo": i["lo"], "hi": i["hi"], "value": i["value"], "type": i["type"],
                                    "text_angle": i["text_angle"], "refpts": i["refpts"], "name": i["name"],
                                    "callout": i["callout"], "dd": dd, "trect": i["trect"], "lines": i["lines"]})
                    elif t == 6:
                        r = self._dq_note_rect(a)
                        sp = a.GetSpecificAnnotation
                        balloon = False
                        try:
                            balloon = bool(sp.IsBomBalloon)
                        except Exception:
                            pass
                        if balloon:
                            # (A7) palloncino: cerchio (raggio ~4,5 mm) centrato sulla posizione; "full" = cerchio + linea di richiamo
                            circ = (pos[0] - 0.0045, pos[1] - 0.0045, pos[0] + 0.0045, pos[1] + 0.0045)
                            out.append({"kind": "balloon", "view": vname, "text": str(sp.GetText), "rect": circ, "full": r or circ})
                        elif r:
                            out.append({"kind": "note", "view": vname, "text": str(sp.GetText),
                                        "rect": r})
                    elif t == 5:
                        r = self._dq_gtol_rect(a) or (pos[0], pos[1] - 0.004, pos[0] + 0.03, pos[1] + 0.004)
                        try:
                            nl = int(a.GetLeaderCount)
                        except Exception:
                            nl = 0
                        out.append({"kind": "gtol", "view": vname, "text": "", "rect": r, "leaders": nl,
                                    "leader_segs": self._dq_gtol_lines(a)[1]})
                    elif t == 2:
                        out.append({"kind": "datum", "view": vname, "text": "",
                                    "rect": (pos[0] - 0.004, pos[1] - 0.004, pos[0] + 0.004, pos[1] + 0.004)})
                    elif t == 7:
                        out.append({"kind": "surface_finish", "view": vname, "text": "", "rect": self._dq_sf_rect(a, pos)})
                    elif t == 14:
                        r = self._dq_table_rect(a)
                        if r:
                            out.append({"kind": "table", "view": vname, "text": "", "rect": r})
                except Exception as e:
                    logger.debug(f"annotation read failed: {e}")
                a = a.GetNext3
        # annotazioni del foglio (note libere, tolleranze inserite sul foglio...): solo quelle nell'area utile.
        # La scansione e' lenta (le note del formato foglio sono decine, ~30 ms ciascuna): il risultato si tiene in
        # cache finche' il numero di annotazioni del foglio non cambia (chi sposta un'annotazione azzera la cache).
        try:
            sv = doc.GetFirstView
            key = (self._get_doc_title(doc), int(sv.GetAnnotationCount))
            cache = getattr(self, "_sheet_ann_cache", None)
            if cache and cache[0] == key:
                out.extend(dict(x) for x in cache[1])
                return out
            found = []
            a = sv.GetFirstAnnotation3
            while a is not None:
                t = int(a.GetType)
                r = None
                kind = None
                if t in (5, 6, 14):
                    # le note del formato foglio (cartiglio, lettere di zona) sono decine: si scartano dalla posizione
                    # (lettura leggera) senza chiedere l'estensione a ciascuna
                    try:
                        pp = tuple(float(x) for x in a.GetPosition)
                        if (pp[0] >= title[0] - 0.02 and pp[1] <= title[3] + 0.02) or pp[0] < use[0] - 0.003                                 or pp[0] > use[2] + 0.003 or pp[1] < use[1] - 0.003 or pp[1] > use[3] + 0.003:
                            a = a.GetNext3
                            continue
                    except Exception:
                        pass
                if t == 6:
                    r, kind = self._dq_note_rect(a), "note"
                elif t == 5:
                    r, kind = self._dq_gtol_rect(a), "gtol"
                elif t == 14:
                    r, kind = self._dq_table_rect(a), "table"
                if r and kind and r[0] > use[0] and r[2] < use[2] and r[1] > use[1] and r[3] < use[3]                         and not _inter(r, title, -1e-4):
                    txt = ""
                    try:
                        txt = str(a.GetSpecificAnnotation.GetText) if kind == "note" else ""
                    except Exception:
                        pass
                    found.append({"kind": kind, "view": "sheet", "text": txt, "rect": r})
                a = a.GetNext3
            self._sheet_ann_cache = (key, found)
            out.extend(dict(x) for x in found)
        except Exception as e:
            logger.debug(f"sheet annotations failed: {e}")
        return out

    def get_drawing_layout(self) -> Dict:
        """Inventario geometrico del foglio attivo (mm): contorno del foglio, cartiglio, zone riservate, viste
        (contorno e contorno reale del pezzo), annotazioni con riquadro; per le quote anche vista, asse
        (orizzontale/verticale), lato, distanza dal contorno e riga. Serve per verificare sovrapposizioni."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            W, H, _ = self._sheet_dims(doc)
            mm = lambda r: [round(t * 1000.0, 2) for t in r]
            views = []
            for v in self._sheet_views(doc):
                core = self._dq_core(v)
                vd = {"name": self._com(v, "GetName2"), "outline": mm(self._view_rect(v)), "core": mm(core),
                      "pictorial": self._is_pictorial(v), "scale": round(float(v.ScaleDecimal), 6)}
                if not vd["pictorial"]:
                    try:        # fori (cerchi) visibili: centro e raggio sul foglio, per controllare che nessuna linea li attraversi
                        hs, _, s_ = self._an_holes(v)
                        vd["holes"] = [{"cx": round(h["cx"] * 1000.0, 3), "cy": round(h["cy"] * 1000.0, 3),
                                        "r": round(h["r"] * s_ * 1000.0, 3)} for h in hs]
                    except Exception:
                        vd["holes"] = []
                views.append(vd)
            anns = []
            for a in self._dq_annotations(doc):
                d = {"kind": a["kind"], "view": a["view"], "text": a.get("text", ""), "rect": mm(a["rect"])}
                if "leaders" in a:
                    d["leaders"] = a["leaders"]
                if a.get("leader_segs"):
                    d["leader_segs"] = [mm(sg) for sg in a["leader_segs"]]
                if a["kind"] == "dimension":
                    d.update({"axis": a["axis"], "dim_kind": a["dim_kind"], "value": a["value"], "type": a["type"],
                              "text_angle_deg": round(math.degrees(a["text_angle"]) % 360.0, 1),
                              "callout": a["callout"], "name": a["name"],
                              "refpts": [list(p) for p in a["refpts"]],
                              "full_rect": mm(a["full"]), "text": a.get("text", ""), "lines": [mm(l_) for l_ in a.get("lines", [])],
                              "text_rect": mm(a["trect"]) if a.get("trect") else None})
                    v = next((x for x in views if x["name"] == a["view"]), None)
                    if v and a["dim_kind"] in ("rad", "dia") and a.get("lines"):
                        # (A4) lunghezza (mm) delle linee del richiamo che cadono DENTRO il contorno della vista
                        cr = [t / 1000.0 for t in v["core"]]
                        tot = 0.0
                        for l in a["lines"]:
                            x0, y0, x1, y1 = l
                            dx, dy = x1 - x0, y1 - y0
                            t0, t1 = 0.0, 1.0
                            okc = True
                            for p_, q_ in ((-dx, x0 - cr[0]), (dx, cr[2] - x0), (-dy, y0 - cr[1]), (dy, cr[3] - y0)):
                                if abs(p_) < 1e-12:
                                    if q_ < 0:
                                        okc = False
                                        break
                                else:
                                    tt = q_ / p_
                                    if p_ < 0:
                                        t0 = max(t0, tt)
                                    else:
                                        t1 = min(t1, tt)
                            if okc and t1 > t0:
                                tot += (t1 - t0) * math.hypot(dx, dy)
                        d["leader_in_core_mm"] = round(tot * 1000.0, 2)
                    if v and a["axis"] in ("H", "V") and a["c"] is not None:
                        core = v["core"]
                        c = a["c"] * 1000.0
                        if a["axis"] == "H":
                            d["side"] = "above" if c > core[3] else ("below" if c < core[1] else "inside")
                            d["offset_mm"] = round(c - core[3] if c > core[3] else (core[1] - c if c < core[1] else 0.0), 2)
                            d["span"] = [round(a["lo"] * 1000, 2), round(a["hi"] * 1000, 2)]
                        else:
                            d["side"] = "right" if c > core[2] else ("left" if c < core[0] else "inside")
                            d["offset_mm"] = round(c - core[2] if c > core[2] else (core[0] - c if c < core[0] else 0.0), 2)
                            d["span"] = [round(a["lo"] * 1000, 2), round(a["hi"] * 1000, 2)]
                anns.append(d)
            tbl = []
            for rr in self._reserved_rects(doc):
                tbl.append(mm(rr))
            data = {"sheet_mm": [round(W * 1000, 1), round(H * 1000, 1)], "title_block": mm(self._title_rect(W, H)),
                    "reserved": tbl, "views": views, "annotations": anns}
            return self._result(True, f"{len(views)} viste, {len(anns)} annotazioni", SwErrors.swSuccess, data)
        except Exception as e:
            return self._fail("get_drawing_layout", e)


    # ------------------------------------------------------------------ copia di riferimento di una quota del modello (A9)
    def _dq_ref_copy(self, doc, v, info: Dict):
        """Ricrea nel disegno (quota di riferimento, DrivenState 1) una quota lineare H/V importata dal modello: stessi due spigoli
        (ricavati dalle ancore delle linee di richiamo), stesso valore, testo nella stessa posizione; elimina l'originale dalla vista.
        Restituisce il nuovo IDisplayDimension o None (nulla di modificato)."""
        if info["kind"] != KIND_LIN or info["axis"] not in ("H", "V") or len(info["anchors"]) < 2:
            return None
        anc = sorted(info["anchors"], key=lambda t: t[0])
        (a1, f1), (a2, f2) = anc[0], anc[-1]
        if abs(a2 - a1) < 1e-5:
            return None
        axis = info["axis"]
        c = info["c"]
        self._dq_core(v)

        def cands(a, far):
            out = []
            sgn = -1.0 if far > c else 1.0           # verso la linea di quota
            for d in (0.0006, 0.0015, 0.0, 0.003, -0.0006, 0.0045):
                if axis == "H":
                    out.append((a, far + sgn * d, 0.0))
                else:
                    out.append((far + sgn * d, a, 1.0))
            return out

        # per quote H lo spigolo e' verticale (x = a): scarto di selezione lungo x (p[2]=0); per V orizzontale (y = a): scarto lungo y
        c1, c2 = cands(a1, f1), cands(a2, f2)
        if not self._dm_select_pair(doc, c1, c2):
            return None
        pos = tuple(float(t) for t in info["dd"].GetAnnotation.GetPosition)
        info.get("trect")
        tx, ty = (pos[0], pos[1])
        dd2 = doc.AddDimension2(tx, ty, 0)
        doc.ClearSelection2(True)
        if dd2 is None:
            return None
        try:
            dim2 = dd2.GetDimension2(0)
            if abs(float(dim2.Value) - info["value"]) > max(0.02, info["value"] * 1e-4) or int(dim2.DrivenState) != 1:
                self._delete_dim_full(doc, str(dd2.GetNameForSelection))
                return None
            dd2.GetAnnotation.Color = 0
            try:        # stesso numero di decimali dell'originale
                p = int(self._com(info["dd"], "GetPrimaryPrecision2"))
                dd2.SetPrecision3(p, 0, p, 0)
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"ref copy check: {e}")
            self._delete_dim_full(doc, str(dd2.GetNameForSelection))
            return None
        self._delete_dim_full(doc, info["sel"])
        return dd2

    # ------------------------------------------------------------------ tolleranze dimensionali
    _TOL_TYPES = {"none": 0, "basic": 1, "bilateral": 2, "limit": 3, "symmetric": 4, "min": 5, "max": 6,
                  "fit": 7, "fit_with_tol": 8, "fit_tol_only": 9, "block": 10, "general": 11}

    def set_dimension_tolerance(self, dimension: str, tolerance_type: str = "symmetric", upper: float = None,
                                lower: float = None, hole_fit: str = None, shaft_fit: str = None,
                                precision: int = None, tol_precision: int = None, view: str = None,
                                unit: str = None, apply_to_model: bool = False) -> Dict:
        """Tolleranza e precisione di una quota del disegno. dimension: nome completo (D1@Schizzo1@pezzo.Part),
        nome breve o testo/valore mostrato (es. '30,00' o '30'). tolerance_type: none | basic | bilateral | limit |
        symmetric | min | max | fit | fit_with_tol | fit_tol_only. upper/lower in unita' di `unit` (mm): simmetrica
        +-upper; bilaterale +upper/-lower (lower positivo = sotto); limite: quote min/max = valore+lower... Per le
        classi ISO: hole_fit='H7', shaft_fit='g6'. precision = cifre decimali della quota (0..8), tol_precision
        = cifre decimali della tolleranza.
        (A9) SOLO SUL DISEGNO: una quota importata dal modello (DrivenState 2, nome D2@Schizzo1@pezzo.Part) e' la quota
        PILOTA del modello: cambiarne la tolleranza cambia anche il modello. Le quote create nel disegno (RD1@Vista..., DrivenState 1)
        sono di riferimento e la tolleranza resta sul disegno. Per una quota del modello, con apply_to_model=False (default) il tool
        la sostituisce con una quota di riferimento identica (stessi spigoli, stesso valore, stessa posizione) e imposta la tolleranza
        su quella; se non e' possibile (quote non lineari orizzontali/verticali) NON modifica nulla e lo dichiara: con
        apply_to_model=True la tolleranza viene scritta nel modello (dichiarato nel risultato)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            tt = self._TOL_TYPES.get(str(tolerance_type).lower())
            if tt is None:
                return self._result(False, f"tolerance_type: {list(self._TOL_TYPES)}", SwErrors.swInvalidInput)
            vs = self._sheet_views(doc)
            if view:
                v0, err = self._find_view(doc, view)
                if err:
                    return err
                vs = [v0]
            q = str(dimension).strip()
            cand = []
            for v in vs:
                for dd in self._display_dims(v):
                    dim = dd.GetDimension2(0)
                    full, name = dim.FullName, dim.Name
                    txt = ""
                    try:
                        txt = " ".join(str(t).strip() for t in
                                       [dd.GetDisplayData.GetTextAtIndex(i)
                                        for i in range(int(self._com(dd.GetDisplayData, "GetTextCount")))])
                    except Exception:
                        pass
                    if q == full or q == name or q.lower() == full.lower():
                        cand.insert(0, (dd, dim, v))
                    elif q.replace(".", ",") in txt.replace("<MOD-DIAM>", "").split() or q in txt.split():
                        cand.append((dd, dim, v))
                    else:
                        try:
                            if abs(float(q.replace(",", ".")) - float(dim.Value)) < 1e-9:
                                cand.append((dd, dim, v))
                        except Exception:
                            pass
            if not cand:
                return self._result(False, f"Quota '{dimension}' non trovata nelle viste", SwErrors.swInvalidInput)
            dd, dim, vsel = cand[0]
            scope = "drawing"
            note = ""
            try:
                driving = int(dim.DrivenState) == 2
            except Exception:
                driving = "@" in dim.FullName and not dim.FullName.split("@")[1].lower().startswith(("vista", "view"))
            if driving and not apply_to_model:
                try:
                    info0 = self._dq_read(vsel, dd)
                    dd2 = self._dq_ref_copy(doc, vsel, info0)
                except Exception as e:
                    logger.debug(f"ref copy: {e}")
                    dd2 = None
                if dd2 is None:
                    return self._result(
                        False, f"La quota {dim.FullName} e' una quota del MODELLO: la sua tolleranza vive nel modello e non ho potuto "
                        "sostituirla con una quota di riferimento del disegno (solo quote lineari orizzontali/verticali). "
                        "Nulla e' stato modificato. Usa apply_to_model=true per scrivere la tolleranza anche nel modello.",
                        SwErrors.swInvalidInput, {"model_driven": True, "applied_to_model": False, "drawing_only": False})
                dd = dd2
                dim = dd.GetDimension2(0)
                note = " (sostituita da una quota di riferimento del disegno: il modello non e' toccato)"
            elif driving:
                scope = "model"
                note = " ATTENZIONE: quota pilota del modello, la tolleranza e' scritta anche nel modello"
            m = lambda x: self._m(float(x), unit)
            dim.SetToleranceType(tt)
            tol = dim.Tolerance
            applied = {"type": tolerance_type}
            if tt in (2, 3, 4, 5, 6):
                if tt == 4:
                    u = m(upper if upper is not None else (lower or 0))
                    tol.SetValues(-u, u)
                elif tt == 2:
                    tol.SetValues(-m(lower or 0), m(upper or 0))
                elif tt == 3:
                    tol.SetValues(-m(lower or 0), m(upper or 0))
                elif tt == 5:
                    tol.SetValues(0.0, 0.0)
                applied["max"], applied["min"] = float(self._com(tol, "GetMaxValue")) * 1000.0, float(self._com(tol, "GetMinValue")) * 1000.0
            if tt in (7, 8, 9):
                tol.SetFitValues(str(hole_fit or ""), str(shaft_fit or ""))
                if tt == 8 and (upper is not None or lower is not None):
                    tol.SetValues(-m(lower or 0), m(upper or 0))
                applied["hole_fit"], applied["shaft_fit"] = str(self._com(tol, "GetHoleFitValue")), str(self._com(tol, "GetShaftFitValue"))
            if precision is not None or tol_precision is not None:
                p = int(precision) if precision is not None else int(self._com(dd, "GetPrimaryPrecision2"))
                tp = int(tol_precision) if tol_precision is not None else int(self._com(dd, "GetPrimaryTolPrecision2"))
                dd.SetPrecision3(p, 0, tp, 0)
                applied["precision"], applied["tol_precision"] = p, tp
            dim_txt = ""
            try:
                dd2 = dd.GetDisplayData
                dim_txt = " | ".join(str(dd2.GetTextAtIndex(i)).strip() for i in range(int(self._com(dd2, "GetTextCount"))))
            except Exception:
                pass
            return self._result(True, f"Tolleranza {tolerance_type} impostata su {dim.FullName}{note}", SwErrors.swSuccess,
                                {"dimension": dim.FullName, "applied": applied, "text": dim_txt,
                                 "scope": scope, "drawing_only": scope == "drawing", "applied_to_model": scope == "model",
                                 "tolerance_type_read": int(self._com(dim, "GetToleranceType"))})
        except Exception as e:
            return self._fail("set_dimension_tolerance", e)
