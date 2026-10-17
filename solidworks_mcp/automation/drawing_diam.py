"""
Quote dei diametri dei pezzi di rivoluzione (blocco 4)
------------------------------------------------------
Un albero importa dal modello quote RADIALI dello schizzo (10, 5, 2.5...): non sono quote da disegno ISO.
Qui si leggono i cilindri del modello, li si proietta sulla vista (ModelToViewTransform) e si creano quote
lineari tra le due silhouette di ogni gradino, con prefisso Ø. Le quote radiali importate vengono eliminate.
"""

import math
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MODEL_PART = 1


class DrawingDiamMixin:
    _dm_side: Dict[str, int] = {}

    def _dm_cylinders(self, v) -> Optional[Dict]:
        """Cilindri del pezzo con asse nel piano della vista: {'axis': 'H'|'V', 'c': coord asse (m), 'groups':
        [{'r': raggio sul foglio (m), 'lo','hi': estensione lungo l'asse, 'value': diametro modello (mm)}]}."""
        m = v.ReferencedDocument
        if m is None or int(m.GetType) != MODEL_PART:
            return None
        tf = [float(x) for x in v.ModelToViewTransform.ArrayData]
        R, t, s = tf[:9], tf[9:12], tf[12]

        def proj(p):
            return tuple(sum(p[i] * R[i * 3 + k] for i in range(3)) * (s if k < 2 else 1.0) + (t[k] if k < 2 else 0.0)
                         for k in range(3))

        def dirp(d):
            return tuple(sum(d[i] * R[i * 3 + k] for i in range(3)) for k in range(3))

        cands = []
        for b in (m.GetBodies2(0, True) or ()):
            for f in (b.GetFaces() or ()):
                try:
                    sf = f.GetSurface
                    if not sf.IsCylinder:
                        continue
                    cp = sf.CylinderParams
                    org, ax, r = cp[0:3], cp[3:6], float(cp[6])
                    d = dirp(ax)
                    if abs(d[2]) > 0.05:
                        continue
                    if abs(d[1]) < 0.05:
                        kind = "H"
                    elif abs(d[0]) < 0.05:
                        kind = "V"
                    else:
                        continue
                    bx = f.GetBox
                    xs, ys = [], []
                    for X in (bx[0], bx[3]):
                        for Y in (bx[1], bx[4]):
                            for Z in (bx[2], bx[5]):
                                q = proj((X, Y, Z))
                                xs.append(q[0])
                                ys.append(q[1])
                    po = proj(org)
                    lo, hi = (min(xs), max(xs)) if kind == "H" else (min(ys), max(ys))
                    c = po[1] if kind == "H" else po[0]
                    cands.append({"kind": kind, "c": c, "r": r * s, "rm": r, "lo": lo, "hi": hi,
                                  "area": float(f.GetArea)})
                except Exception as e:
                    logger.debug(f"cyl face: {e}")
        if not cands:
            return None
        # asse principale: gruppo (tipo, coordinata) con maggiore estensione totale
        axes: Dict[Tuple, List[Dict]] = {}
        for c in cands:
            axes.setdefault((c["kind"], round(c["c"] / 0.0003)), []).append(c)
        key = max(axes, key=lambda k: sum(x["hi"] - x["lo"] for x in axes[k]))
        fs = axes[key]
        rg: Dict[int, List[Dict]] = {}
        for c in fs:
            rg.setdefault(round(c["r"] / 0.00005), []).append(c)
        groups = []
        for k, g in rg.items():
            L = sum(x["hi"] - x["lo"] for x in g)
            full = sum(x["area"] for x in g)
            # solo cilindri pieni (non fori parziali, raccordi): area ~ 2*pi*r*L (modello in m)
            sc = (g[0]["r"] / g[0]["rm"]) if g[0]["rm"] else 1.0
            if L <= 1e-6 or full < 0.85 * 2 * math.pi * g[0]["rm"] * (L / sc):
                continue
            groups.append({"r": g[0]["r"], "lo": min(x["lo"] for x in g), "hi": max(x["hi"] for x in g),
                           "value": round(2 * g[0]["rm"] * 1000.0, 4)})
        if not groups:
            return None
        groups.sort(key=lambda x: x["r"])
        return {"axis": key[0], "c": sum(x["c"] for x in fs) / len(fs), "groups": groups}

    def _dm_remove_radial(self, doc, info, infos) -> int:
        """Elimina le quote lineari radiali importate (entrambe le ancore sull'asse o su un raggio dei cilindri)."""
        levels = [info["c"]] + [info["c"] + sg * g["r"] for g in info["groups"] for sg in (1, -1)]
        want_axis = "V" if info["axis"] == "H" else "H"
        n = 0
        for i in infos:
            if i["kind"] != "lin" or i["axis"] != want_axis or len(i["anchors"]) < 2:
                continue
            if all(any(abs(a - L) < 0.0004 for L in levels) for a, _ in i["anchors"]):
                if self._delete_dim_full(doc, i["sel"]):
                    n += 1
        return n

    def _dm_select_sil(self, doc, x: float, y: float, r: float, axis: str, c: float, append: bool) -> bool:
        """Seleziona la silhouette (tipo 46) nel punto: la zona sensibile e' spostata di 0.1-0.5 mm verso
        l'esterno rispetto al raggio geometrico, quindi si prova con scarti crescenti verso l'esterno."""
        sm = doc.SelectionManager
        nb = sm.GetSelectedObjectCount2(-1) if append else 0
        for off in (0.0003, 0.0002, 0.0004, 0.00015, 0.0005):
            if not append:
                doc.ClearSelection2(True)
            xx, yy = x, y
            if axis == "H":
                yy = y + off if y > c else y - off
            else:
                xx = x + off if x > c else x - off
            if doc.Extension.SelectByID2("", "SILEDGE", xx, yy, 0, append, 0, self._NULL, 0):
                n = sm.GetSelectedObjectCount2(-1)
                if n > nb and int(sm.GetSelectedObjectType3(n, -1)) == 46:
                    return True
                if n > nb:       # selezione sbagliata (faccia/vista): la tolgo
                    doc.ClearSelection2(True)
                    if append:
                        return False
        return False

    def _dm_add_diameters(self, doc, v, info, existing: set, side_count: Dict[int, int]) -> List[Dict]:
        axis, c = info["axis"], info["c"]
        groups = info["groups"]
        glo = min(g["lo"] for g in groups)
        ghi = max(g["hi"] for g in groups)
        vr = self._view_rect(v)
        made = []
        for g in groups:
            if any(abs(g["value"] - e) < 5e-3 for e in existing):
                continue
            L = g["hi"] - g["lo"]
            eps = 0.0005
            if g["hi"] >= ghi - eps and g["lo"] > glo + eps:
                side = 1
            elif g["lo"] <= glo + eps and g["hi"] < ghi - eps:
                side = -1
            else:
                side = 1 if side_count[1] <= side_count[-1] else -1
            inward = min(0.0025, L / 2.0)
            p = g["hi"] - inward if side > 0 else g["lo"] + inward
            pts = [(p, c + g["r"]), (p, c - g["r"])] if axis == "H" else [(c + g["r"], p), (c - g["r"], p)]
            if axis == "H":
                tx, ty = (vr[2] + 0.02 if side > 0 else vr[0] - 0.02), c
            else:
                tx, ty = c, (vr[3] + 0.02 if side > 0 else vr[1] - 0.02)
            dd = None
            for attempt in range(3):
                doc.ClearSelection2(True)
                ok = True
                for k, (x, y) in enumerate(pts):
                    ok = ok and self._dm_select_sil(doc, x, y, g["r"], axis, c, k > 0)
                if ok:
                    dd = doc.AddDimension2(tx, ty, 0)
                    doc.ClearSelection2(True)
                    if dd is not None:
                        break
                doc.ClearSelection2(True)
            if dd is None:
                continue
            try:
                dim = dd.GetDimension2(0)
                if abs(float(dim.Value) - g["value"]) > 0.02:
                    # misura sbagliata (spigoli non giusti): la tolgo
                    self._delete_dim_full(doc, str(dd.GetNameForSelection))
                    continue
                dd.SetText(1, "<MOD-DIAM>")
                dd.GetAnnotation.Color = 0
                sel = str(dd.GetNameForSelection)
                made.append({"value": g["value"], "side": side, "sel": sel, "view": self._com(v, "GetName2")})
                side_count[side] += 1
                existing.add(g["value"])
                self._dm_side[sel] = side
            except Exception as e:
                logger.debug(f"diameter dim: {e}")
        return made

    # ------------------------------------------------------------------ quote complementari (ingombri, fori)
    def _dm_proj(self, v):
        """Funzione di proiezione modello -> foglio per la vista (m)."""
        tf = [float(x) for x in v.ModelToViewTransform.ArrayData]
        R, t, s = tf[:9], tf[9:12], tf[12]

        def proj(p):
            return tuple(sum(p[i] * R[i * 3 + k] for i in range(3)) * (s if k < 2 else 1.0) + (t[k] if k < 2 else 0.0)
                         for k in range(3))

        def dirp(d):
            return tuple(sum(d[i] * R[i * 3 + k] for i in range(3)) for k in range(3))
        return proj, dirp, s

    def _dm_core(self, v) -> Optional[Tuple[float, float, float, float]]:
        """Contorno esatto del pezzo sulla vista (da GetPartBox proiettato); None per assiemi."""
        m = v.ReferencedDocument
        if m is None or int(m.GetType) != MODEL_PART:
            return None
        proj, _, s = self._dm_proj(v)
        bx = m.GetPartBox(True)
        xs, ys = [], []
        for X in (bx[0], bx[3]):
            for Y in (bx[1], bx[4]):
                for Z in (bx[2], bx[5]):
                    q = proj((X, Y, Z))
                    xs.append(q[0])
                    ys.append(q[1])
        return (min(xs), min(ys), max(xs), max(ys))

    def _dm_select_pair(self, doc, c1: List[Tuple[float, float, float]], c2: List[Tuple[float, float, float]]) -> bool:
        """Seleziona due spigoli (tipo 1 o silhouette 46) provando i punti candidati (x, y, direzione dello
        scarto: 0 = x, 1 = y) nell'ordine dato."""
        sm = doc.SelectionManager

        def one(p, append, before):
            for typ in ("EDGE", "SILEDGE"):
                for off in (0.0, 0.0002, -0.0002):
                    x, y = p[0] + off * (1 - p[2]), p[1] + off * p[2]
                    if not append:
                        doc.ClearSelection2(True)
                    if doc.Extension.SelectByID2("", typ, x, y, 0, append, 0, self._NULL, 0):
                        n = sm.GetSelectedObjectCount2(-1)
                        if n > before and int(sm.GetSelectedObjectType3(n, -1)) in (1, 46):
                            return True
                        if n > before:
                            return None     # selezione sbagliata: si riparte
            return False

        for p1 in c1:
            doc.ClearSelection2(True)
            if not one(p1, False, 0):
                continue
            for p2 in c2:
                r = one(p2, True, 1)
                if r:
                    return True
                if r is None:
                    doc.ClearSelection2(True)
                    if not one(p1, False, 0):
                        break
        doc.ClearSelection2(True)
        return False

    def _dm_finish(self, doc, dd, expected: float, prefix: str = None) -> Optional[str]:
        """Controlla il valore della quota creata (mm); se non torna la elimina. Restituisce il nome per la selezione."""
        try:
            dim = dd.GetDimension2(0)
            sel = str(dd.GetNameForSelection)
            if expected is not None and abs(float(dim.Value) - expected) > max(0.05, expected * 1e-3):
                self._delete_dim_full(doc, sel)
                return None
            if prefix:
                dd.SetText(1, prefix)
            dd.GetAnnotation.Color = 0
            return sel
        except Exception as e:
            logger.debug(f"dm_finish: {e}")
            return None

    def _dm_overall(self, doc, v, infos: List[Dict], lin_vals: set = None) -> List[Dict]:
        """Quote di ingombro (larghezza e altezza della vista) se non ce ne sono gia'."""
        core = self._dm_core(v)
        exact = bool(core)
        if not core:
            # (A7) assiemi: contorno dalla vista (GetOutline meno il margine di SolidWorks); quota verificata con tolleranza 3 %
            try:
                m_ = v.ReferencedDocument
                if m_ is None or int(m_.GetType) != 2:
                    return []
            except Exception:
                return []
            core = self._dq_core(v)
        _, _, s = self._dm_proj(v)
        made = []
        w, h = core[2] - core[0], core[3] - core[1]
        vn = self._com(v, "GetName2")
        fr = (0.5, 0.35, 0.65, 0.2, 0.8, 0.05, 0.95)
        for axis, size in (("H", w), ("V", h)):
            if size < 0.004:
                continue
            if any(i["kind"] == "lin" and i["axis"] == axis and (i["hi"] - i["lo"]) > size * 0.97 for i in infos):
                continue
            if lin_vals is not None and round(size / s * 1000.0, 2) in lin_vals:
                continue            # stessa misura gia' quotata in un'altra vista: niente duplicati
            if axis == "H":
                ys = [core[1] + (core[3] - core[1]) * f for f in fr]
                c1 = [(core[0], y, 0.0) for y in ys]
                c2 = [(core[2], y, 0.0) for y in ys]
                tx, ty = (core[0] + core[2]) / 2.0, core[3] + 0.02
            else:
                xs = [core[0] + (core[2] - core[0]) * f for f in fr]
                c1 = [(x, core[1], 1.0) for x in xs]
                c2 = [(x, core[3], 1.0) for x in xs]
                tx, ty = core[2] + 0.02, (core[1] + core[3]) / 2.0
            if not self._dm_select_pair(doc, c1, c2):
                continue
            dd = doc.AddDimension2(tx, ty, 0)
            doc.ClearSelection2(True)
            if dd is None:
                continue
            if exact:
                sel = self._dm_finish(doc, dd, size / s * 1000.0)
            else:
                try:
                    val = float(dd.GetDimension2(0).Value)
                    want = size / s * 1000.0
                    if abs(val - want) > 0.03 * want:
                        self._delete_dim_full(doc, str(dd.GetNameForSelection))
                        sel = None
                    else:
                        dd.GetAnnotation.Color = 0
                        sel = str(dd.GetNameForSelection)
                        size = val * s / 1000.0
                except Exception:
                    sel = None
            if sel:
                made.append({"view": vn, "axis": axis, "value": round(size / s * 1000.0, 3), "sel": sel})
                if lin_vals is not None:
                    lin_vals.add(round(size / s * 1000.0, 2))
        return made

    def _dm_holes(self, doc, v, existing: set) -> List[Dict]:
        """Diametro dei fori/cilindri con asse perpendicolare alla vista (cerchi): una quota per diametro, con
        il numero di fori uguali come prefisso (6x Ø9)."""
        m = v.ReferencedDocument
        if m is None or int(m.GetType) != MODEL_PART:
            return []
        proj, dirp, s = self._dm_proj(v)
        circles: Dict[int, Dict] = {}
        for b in (m.GetBodies2(0, True) or ()):
            for f in (b.GetFaces() or ()):
                try:
                    sf = f.GetSurface
                    if not sf.IsCylinder:
                        continue
                    cp = sf.CylinderParams
                    d = dirp(cp[3:6])
                    if abs(d[2]) < 0.95:
                        continue
                    r = float(cp[6])
                    po = proj(cp[0:3])
                    key = round(r * 1e5)
                    g = circles.setdefault(key, {"r": r, "rs": r * s, "centers": {}})
                    g["centers"][(round(po[0] / 0.0003), round(po[1] / 0.0003))] = (po[0], po[1])
                except Exception:
                    pass
        made = []
        vn = self._com(v, "GetName2")
        sm = doc.SelectionManager
        core0 = self._dm_core(v)
        for key in sorted(circles):
            g = circles[key]
            val = round(2 * g["r"] * 1000.0, 4)
            if any(abs(val - e) < 5e-3 for e in existing):
                continue
            ok = False
            for (cx, cy) in g["centers"].values():
                for ang in (0.0, 90.0, 180.0, 270.0, 45.0):
                    px = cx + g["rs"] * math.cos(math.radians(ang))
                    py = cy + g["rs"] * math.sin(math.radians(ang))
                    doc.ClearSelection2(True)
                    if doc.Extension.SelectByID2("", "EDGE", px, py, 0, False, 0, self._NULL, 0):
                        if int(sm.GetSelectedObjectType3(sm.GetSelectedObjectCount2(-1), -1)) == 1:
                            ok = True
                            break
                if ok:
                    break
            if not ok:
                doc.ClearSelection2(True)
                continue
            ux, uy = (0.7071, 0.7071)
            if core0:
                ux, uy = (core0[0] + core0[2]) / 2.0 - cx, (core0[1] + core0[3]) / 2.0 - cy
                nn = math.hypot(ux, uy)
                ux, uy = (ux / nn, uy / nn) if nn > 1e-6 else (0.7071, 0.7071)
            tx = cx + (g["rs"] + 0.006) * ux + (0.0 if ux >= 0 else -0.012)
            ty = cy + (g["rs"] + 0.006) * uy
            dd = doc.AddDimension2(tx, ty, 0)
            doc.ClearSelection2(True)
            if dd is None:
                continue
            n = len(g["centers"])
            sel = self._dm_finish(doc, dd, val, (f"{n}x <MOD-DIAM>" if n > 1 else None))
            if sel:
                made.append({"view": vn, "value": val, "count": n, "sel": sel})
                existing.add(val)
        return made


    # ------------------------------------------------------------------ cave / tasche rettangolari (A3)
    def _dm_cut_profiles(self, v) -> List[Dict]:
        """Profili chiusi di tagli estrusi (feature 'ICE') visti di fronte nella vista: [{'feature','box':(x0,y0,x1,y1) foglio (m),
        'kind':'rect'|'slot'}]. Il profilo e' letto dallo schizzo della feature e portato nel modello con l'inversa
        di ModelToSketchTransform (p_modello = (p_schizzo - t) * R^T), poi sul foglio con la trasformazione della vista."""
        out = []
        m = v.ReferencedDocument
        if m is None or int(m.GetType) != MODEL_PART:
            return out
        proj, dirp, sc = self._dm_proj(v)
        f = m.FirstFeature
        while f is not None:
            try:
                if str(f.GetTypeName2) == "ICE":
                    sub = f.GetFirstSubFeature
                    sk = sub.GetSpecificFeature2 if sub is not None else None
                    if sk is not None:
                        tf = [float(x) for x in sk.ModelToSketchTransform.ArrayData]
                        R, t = tf[:9], tf[9:12]

                        def tomodel(pt):
                            q = (pt[0] - t[0], pt[1] - t[1], pt[2] - t[2])
                            return tuple(sum(q[k] * R[j * 3 + k] for k in range(3)) for j in range(3))

                        nrm = dirp((R[2], R[5], R[8]))
                        if abs(nrm[2]) > 0.95:
                            lines, others, pts = 0, 0, []
                            for sg in (sk.GetSketchSegments or ()):
                                ty = int(sg.GetType)
                                if ty == 0:
                                    lines += 1
                                else:
                                    others += 1
                                try:
                                    for pp in (sg.GetStartPoint2, sg.GetEndPoint2):
                                        q = proj(tomodel((pp.X, pp.Y, pp.Z)))
                                        pts.append((q[0], q[1]))
                                except Exception:
                                    pass
                            if pts and lines >= 2:
                                xs, ys = [q[0] for q in pts], [q[1] for q in pts]
                                kind = "rect" if (lines == 4 and others == 0) else ("slot" if (lines == 2 and others == 2) else None)
                                if kind:
                                    out.append({"feature": str(f.Name), "box": (min(xs), min(ys), max(xs), max(ys)), "kind": kind})
            except Exception as e:
                logger.debug(f"cut profile: {e}")
            f = f.GetNextFeature
        return out

    def _dm_pockets(self, doc, v, lin_vals: set = None) -> List[Dict]:
        """(A3) Quote di cave/tasche rettangolari e asole (tagli estrusi visti di fronte): lunghezza, larghezza e posizione dalla
        testata piu' vicina (e laterale se non centrata). Le quote si creano selezionando gli spigoli veri del profilo."""
        made = []
        core = self._dm_core(v)
        if not core:
            return made
        _, _, s = self._dm_proj(v)
        vn = self._com(v, "GetName2")
        K3 = (0, 0.5, -0.5)
        for pr in self._dm_cut_profiles(v):
            x0, y0, x1, y1 = pr["box"]
            w, h = x1 - x0, y1 - y0
            if w < 0.002 or h < 0.002:
                continue
            xm, ym = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            horiz = w >= h
            specs = []
            if pr["kind"] == "rect":
                specs.append(("L", [(x0, ym + k * h * 0.2, 0.0) for k in K3], [(x1, ym + k * h * 0.2, 0.0) for k in K3],
                              w / s * 1000.0, (xm, y1 + 0.02)))
                specs.append(("W", [(xm + k * w * 0.2, y0, 1.0) for k in K3], [(xm + k * w * 0.2, y1, 1.0) for k in K3],
                              h / s * 1000.0, (x1 + 0.02, ym)))
            else:
                if horiz:
                    specs.append(("W", [(xm + k * w * 0.15, y0, 1.0) for k in K3], [(xm + k * w * 0.15, y1, 1.0) for k in K3],
                                  h / s * 1000.0, (x1 + 0.02, ym)))
                else:
                    specs.append(("W", [(x0, ym + k * h * 0.15, 0.0) for k in K3], [(x1, ym + k * h * 0.15, 0.0) for k in K3],
                                  w / s * 1000.0, (xm, y1 + 0.02)))
            fr = (0.5, 0.35, 0.65, 0.2, 0.8)
            if horiz:
                ycs = [core[1] + (core[3] - core[1]) * f_ for f_ in fr]
                if x0 - core[0] <= core[2] - x1:
                    specs.append(("P", [(core[0], y_, 0.0) for y_ in ycs], [(x0, ym + k * h * 0.2, 0.0) for k in K3],
                                  (x0 - core[0]) / s * 1000.0, (xm, y0 - 0.02)))
                else:
                    specs.append(("P", [(x1, ym + k * h * 0.2, 0.0) for k in K3], [(core[2], y_, 0.0) for y_ in ycs],
                                  (core[2] - x1) / s * 1000.0, (xm, y0 - 0.02)))
                off = ym - (core[1] + core[3]) / 2.0
                if abs(off) > 0.0003:
                    xcs = [xm + k * w * 0.2 for k in K3]
                    if off > 0:
                        specs.append(("Q", [(xx, core[3], 1.0) for xx in xcs], [(xx, y1, 1.0) for xx in xcs], (core[3] - y1) / s * 1000.0, (x1 + 0.03, ym)))
                    else:
                        specs.append(("Q", [(xx, y0, 1.0) for xx in xcs], [(xx, core[1], 1.0) for xx in xcs], (y0 - core[1]) / s * 1000.0, (x1 + 0.03, ym)))
            else:
                xcs = [core[0] + (core[2] - core[0]) * f_ for f_ in fr]
                if y0 - core[1] <= core[3] - y1:
                    specs.append(("P", [(xx, core[1], 1.0) for xx in xcs], [(xm + k * w * 0.2, y0, 1.0) for k in K3],
                                  (y0 - core[1]) / s * 1000.0, (x1 + 0.03, ym)))
                else:
                    specs.append(("P", [(xm + k * w * 0.2, y1, 1.0) for k in K3], [(xx, core[3], 1.0) for xx in xcs],
                                  (core[3] - y1) / s * 1000.0, (x1 + 0.03, ym)))
                off = xm - (core[0] + core[2]) / 2.0
                if abs(off) > 0.0003:
                    ycs = [ym + k * h * 0.2 for k in K3]
                    if off > 0:
                        specs.append(("Q", [(core[2], yy, 0.0) for yy in ycs], [(x1, yy, 0.0) for yy in ycs], (core[2] - x1) / s * 1000.0, (xm, y1 + 0.03)))
                    else:
                        specs.append(("Q", [(x0, yy, 0.0) for yy in ycs], [(core[0], yy, 0.0) for yy in ycs], (x0 - core[0]) / s * 1000.0, (xm, y1 + 0.03)))
            if not hasattr(self, "_pocket_done"):
                self._pocket_done = {}
            alive = {str(d_.GetNameForSelection) for d_ in self._dq_view_dims(v)}
            ttl = self._get_doc_title(doc)
            for name, c1, c2, expected, (tx, ty) in specs:
                if expected < 0.05:
                    continue
                key = (ttl, vn, pr["feature"], name)
                if self._pocket_done.get(key) in alive:
                    continue            # gia' quotata (la disposizione puo' essere rilanciata piu' volte)
                if not self._dm_select_pair(doc, c1, c2):
                    continue
                dd = doc.AddDimension2(tx, ty, 0)
                doc.ClearSelection2(True)
                if dd is None:
                    continue
                sel = self._dm_finish(doc, dd, expected)
                if sel:
                    self._pocket_done[key] = sel
                    made.append({"view": vn, "feature": pr["feature"], "role": name, "value": round(expected, 3), "sel": sel})
                    if lin_vals is not None:
                        lin_vals.add(round(expected, 2))
        return made

    # ------------------------------------------------------------------ quote di diametro su cerchi
    def _dm_circle_of(self, i: Dict, scale: float) -> Optional[Tuple[float, float, float]]:
        """Centro e raggio (foglio, m) di una quota di diametro dalle sue frecce/linee."""
        r = float(i["value"]) / (1000.0 if i["kind"] == "rad" else 2000.0) * scale
        ar = i["arrows"]
        if len(ar) >= 2 and i["kind"] != "rad":
            (x1, y1), (x2, y2) = ar[0], ar[1]
            d = math.hypot(x2 - x1, y2 - y1)
            if abs(d - 2 * r) < max(0.0006, 0.05 * r):
                return ((x1 + x2) / 2.0, (y1 + y2) / 2.0, d / 2.0)
        if not ar:
            return None
        ax, ay = ar[0]
        best = None
        for l in i["lines"]:
            for (px, py), (qx, qy) in (((l[0], l[1]), (l[2], l[3])), ((l[2], l[3]), (l[0], l[1]))):
                if math.hypot(px - ax, py - ay) < 3e-4:
                    ln = math.hypot(qx - px, qy - py)
                    want = r if i["kind"] == "rad" else 2 * r
                    if best is None or abs(ln - want) < best[0]:
                        best = (abs(ln - want), (qx - px) / (ln or 1.0), (qy - py) / (ln or 1.0))
        if best is None:
            return None
        return (ax + best[1] * r, ay + best[2] * r, r)

    def _dm_arrange_circles(self, doc, v, core: Tuple[float, float, float, float], blockers: List[Tuple],
                            placed: List[Tuple]) -> int:
        """Porta il testo delle quote di diametro dei cerchi FUORI dal contorno della vista, lungo raggi diversi
        (linea di quota radiale con freccia sul cerchio). Sceglie fra gli angoli candidati il primo libero."""
        from .drawing_dims import _inter, KIND_DIA, KIND_RAD
        scale = float(v.ScaleDecimal) or 1.0
        items = []
        for dd in self._dq_view_dims(v):
            try:
                i = self._dq_read(v, dd)
            except Exception:
                continue
            if i["kind"] not in (KIND_DIA, KIND_RAD):
                continue
            c = self._dm_circle_of(i, scale)
            if c:
                items.append((i, c))
        items.sort(key=lambda t: -t[1][2])
        base_angles = [45, 135, -45, -135, 20, 160, -20, -160, 70, 110, -70, -110, 0, 180, 90, -90]
        used = []
        used_c = []      # (cx, cy, angolo): cerchi concentrici non devono avere richiami collineari (A4)
        n_moved = 0
        gcore = (core[0] - 0.006, core[1] - 0.006, core[2] + 0.006, core[3] + 0.006)
        for i, (cx, cy, r) in items:
            tw = self._dq_text_w(i["text"], i["texts"][-1][3] if i["texts"] else 0.0035)
            th = i["texts"][-1][3] if i["texts"] else 0.0035
            best = None
            angles = base_angles
            n_corner = 0
            if i["kind"] == "rad" and i["arrows"]:
                # raggio: il testo va dalla parte dell'arco (direzione centro -> punto d'arrivo della freccia)
                a0 = math.degrees(math.atan2(i["arrows"][0][1] - cy, i["arrows"][0][0] - cx))
                angles = [round(a0 + d) for d in (0, 25, -25, 50, -50, 80, -80)] + base_angles
                # (A4) raccordo d'angolo: SolidWorks mette la freccia sul prolungamento del cerchio, dove il richiamo
                # attraversa il pezzo. Se il centro e' vicino a uno spigolo del contorno, l'arco reale e' verso quello
                # spigolo: il testo va in quella direzione (fuori dal pezzo) e la freccia cade sull'arco vero.
                corner_angles = []
                for qx, qy in ((core[0], core[1]), (core[2], core[1]), (core[0], core[3]), (core[2], core[3])):
                    dx_, dy_ = qx - cx, qy - cy
                    if 0.4 * r <= abs(dx_) <= 2.4 * r and 0.4 * r <= abs(dy_) <= 2.4 * r:
                        corner_angles.append((math.hypot(dx_, dy_), round(math.degrees(math.atan2(dy_, dx_)))))
                if corner_angles:
                    ca_ = min(corner_angles)[1]
                    angles = [ca_, ca_ + 12, ca_ - 12, ca_ + 25, ca_ - 25] + angles
                    n_corner = 5
            trials = [(a_, e_) for a_ in angles[:n_corner] for e_ in (0.0, 0.008, 0.016, 0.03)] + [(a_, 0.0) for a_ in angles[n_corner:]]
            for a, extra in trials:
                if a in used:
                    continue
                if any(abs(cx - ux_) < 2e-3 and abs(cy - uy_) < 2e-3 and min(abs((a - ua_) % 180.0), 180.0 - abs((a - ua_) % 180.0)) < 14.0
                       for ux_, uy_, ua_ in used_c):
                    continue
                ux, uy = math.cos(math.radians(a)), math.sin(math.radians(a))
                # uscita dal riquadro (core + margine) lungo il raggio
                t_exit = 1e9
                for lim, u0, c0 in ((gcore[2], ux, cx), (gcore[0], ux, cx), (gcore[3], uy, cy), (gcore[1], uy, cy)):
                    if abs(u0) > 1e-9:
                        t = (lim - c0) / u0
                        if t > 0:
                            t_exit = min(t_exit, t)
                t = t_exit + 0.003 + extra
                px, py = cx + ux * t, cy + uy * t
                # il testo (lungo il raggio, leggibile) ha il centro a mezza lunghezza oltre il punto di uscita
                tcx = px + ux * (tw / 2.0 + 0.003)
                tcy = py + uy * (tw / 2.0 + 0.003)
                ca, sa = abs(ux), abs(uy)
                hw_ = (ca * tw + sa * th * 1.3) / 2.0 + 0.002
                hh_ = (sa * tw + ca * th * 1.3) / 2.0 + 0.002
                rect = (tcx - hw_, tcy - hh_, tcx + hw_, tcy + hh_)
                bad = any(_inter(rect, b, 1e-4) for b in blockers + placed)
                us = self._dq_usable(doc)
                bad = bad or rect[0] < us[0] or rect[2] > us[2] or rect[1] < us[1] or rect[3] > us[3]
                if not bad:
                    best = (a, tcx, tcy, rect)
                    break
            if best is None:
                continue
            a, tcx, tcy, rect = best
            used.append(a)
            used_c.append((cx, cy, a))
            an = i["dd"].GetAnnotation
            pos = tuple(float(q) for q in an.GetPosition)
            for _ in range(2):
                tr = i.get("trect")
                cur = ((tr[0] + tr[2]) / 2.0, (tr[1] + tr[3]) / 2.0) if tr else (pos[0], pos[1])
                an.SetPosition2(pos[0] + (tcx - cur[0]), pos[1] + (tcy - cur[1]), pos[2])
                try:
                    i2 = self._dq_read(v, i["dd"])
                    i["trect"], pos = i2["trect"], tuple(float(q) for q in an.GetPosition)
                except Exception:
                    break
            placed.append(rect)
            n_moved += 1
        return n_moved
