"""
Vista ausiliaria SENZA CreateAuxiliaryViewAt2 (A16)
---------------------------------------------------
`IDrawingDoc.CreateAuxiliaryViewAt2` fa morire SolidWorks (RPC 0x800706BE) in modo casuale: su un'istanza dell'utente
significa perdere il lavoro non salvato. Qui la vista ausiliaria si costruisce con chiamate sicure:

1. lo spigolo scelto si cerca fra gli spigoli rettilinei VISIBILI della vista madre (`IView.GetVisibleEntities2`), senza
   selezioni sul foglio; si legge la sua direzione `e` dal modello;
2. direzione di osservazione: perpendicolare allo spigolo e parallela al piano della vista madre (n = Z_vista x e), rivolta
   verso l'esterno del pezzo; il sistema di riferimento della vista madre viene RUOTATO di 90 gradi attorno allo spigolo
   (come nella piegatura di una vista ausiliaria: la coordinata lungo lo spigolo non cambia);
3. quell'orientamento e' una vista nominata del modello (`IModelView.Orientation3` + `IModelDoc2.NameView`);
4. la vista del disegno e' `CreateDrawViewFromModelView3`, posta sulla perpendicolare allo spigolo, fuori dalla madre;
5. freccia (nota con richiamo agganciato allo spigolo) e lettera, piu' il titolo "VISTA x" sotto la vista.

Convenzione della matrice (verificata): colonne = assi X,Y,Z della vista espressi nel modello; array a 16 valori come
`ModelToViewTransform`/`Orientation3` (9 di rotazione per righe di modello, 3 di traslazione, scala, 3 di riempimento).
"""

import re
import math
import logging
from typing import Dict, List, Optional, Tuple

import win32com.client
import pythoncom

from ..constants import SwErrors
from ..utils.sw_lang import drawing_text

logger = logging.getLogger(__name__)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return tuple(x / n for x in a) if n > 1e-12 else None


def _arr16(vals):
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, tuple(float(v) for v in vals))


def _seg_hits_rect(sg, r) -> bool:
    """Il segmento (x0,y0,x1,y1) interseca il rettangolo r (Liang-Barsky)."""
    x0, y0, x1, y1 = sg
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p_, q_ in ((-dx, x0 - r[0]), (dx, r[2] - x0), (-dy, y0 - r[1]), (dy, r[3] - y0)):
        if abs(p_) < 1e-12:
            if q_ < 0:
                return False
        else:
            t = q_ / p_
            if p_ < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
    return t0 <= t1


def _seg_dist(p, a, b) -> float:
    """Distanza del punto p dal segmento a-b (2D)."""
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < 1e-18 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


class DrawingAuxMixin:

    # ------------------------------------------------------------------ geometria
    @staticmethod
    def _aux_frame(v) -> Tuple[tuple, tuple, tuple]:
        """Assi X, Y, Z della vista (nel modello)."""
        tf = [float(x) for x in v.ModelToViewTransform.ArrayData]
        R = tf[:9]
        return (R[0], R[3], R[6]), (R[1], R[4], R[7]), (R[2], R[5], R[8])

    def _aux_proj(self, v):
        tf = [float(x) for x in v.ModelToViewTransform.ArrayData]
        R, t, s = tf[:9], tf[9:12], tf[12]

        def proj(p):
            return tuple(sum(p[i] * R[i * 3 + k] for i in range(3)) * (s if k < 2 else 1.0) + (t[k] if k < 2 else 0.0)
                         for k in range(3))
        return proj

    def _aux_pick_edge(self, v, sx: float, sy: float, tol: float = 0.008) -> Optional[Dict]:
        """Spigolo rettilineo visibile della vista piu' vicino al punto del foglio (sx, sy), in metri."""
        proj = self._aux_proj(v)
        try:
            es = v.GetVisibleEntities2(win32com.client.VARIANT(pythoncom.VT_DISPATCH, None), 1)
        except Exception as e:
            logger.debug(f"GetVisibleEntities2: {e}")
            return None
        best = None
        for e in (es or ()):
            try:
                c = self._com(e, "GetCurve")
                if c is None or not bool(self._com(c, "IsLine")):
                    continue
                lp = [float(x) for x in self._com(c, "LineParams")]
                d = _unit(lp[3:6])
                p0 = self._com(self._com(e, "GetStartVertex"), "GetPoint")
                p1 = self._com(self._com(e, "GetEndVertex"), "GetPoint")
                a, b = proj(tuple(p0)), proj(tuple(p1))
                dist = _seg_dist((sx, sy), a, b)
                if d is not None and (best is None or dist < best["dist"]):
                    best = {"edge": e, "dist": dist, "dir": d, "p0": tuple(p0), "p1": tuple(p1), "a": a, "b": b}
            except Exception as ex:
                logger.debug(f"aux edge: {ex}")
        if best is None or best["dist"] > tol:
            return None
        return best

    def _aux_face_ratio(self, edge, nrm) -> Optional[Dict]:
        """Faccia piana adiacente allo spigolo con la normale piu' vicina alla direzione di osservazione `nrm`
        (verso lo spettatore): {'area_mm2', 'cos'}."""
        try:
            faces = self._com(edge, "GetTwoAdjacentFaces2")
        except Exception:
            return None
        best = None
        for f in (faces or ()):
            try:
                sf = self._com(f, "GetSurface")
                if not bool(self._com(sf, "IsPlane")):
                    continue
                pp = [float(x) for x in self._com(sf, "PlaneParams")]
                n = tuple(pp[:3])
                if not bool(self._com(f, "FaceInSurfaceSense")):
                    n = tuple(-x for x in n)
                c = _dot(n, nrm)
                if best is None or abs(c) > abs(best["cos"]):
                    best = {"cos": c, "area_mm2": round(float(self._com(f, "GetArea")) * 1e6, 3), "normal": n}
            except Exception as ex:
                logger.debug(f"aux face: {ex}")
        return best

    # ------------------------------------------------------------------ vista nominata
    def _aux_named_view(self, doc, mdoc, mpath: str, cols) -> Tuple[Optional[str], str]:
        """Crea nel modello la vista nominata con gli assi `cols` (X', Y', Z' nel modello). Ripristina l'orientamento
        e la finestra del disegno. Se il modello era pulito lo salva (la vista nominata resta nel file)."""
        app = self._sw_app
        dtitle = self._get_doc_title(doc)
        mtitle = self._get_doc_title(mdoc)
        names = [str(n) for n in (self._com(mdoc, "GetModelViewNames") or ())]
        k = 1
        while f"AUX_{k}" in names:
            k += 1
        name = f"AUX_{k}"
        err = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        was_dirty = False
        try:
            was_dirty = bool(self._com(mdoc, "GetSaveFlag"))
        except Exception:
            pass
        X, Y, Z = cols
        vals = [X[0], Y[0], Z[0], X[1], Y[1], Z[1], X[2], Y[2], Z[2], 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
        msg = ""
        try:
            app.ActivateDoc3(mtitle, False, 0, err)
            md = app.ActiveDoc
            if md is None or self._get_doc_title(md) != mtitle:
                return None, "modello non attivabile"
            mv = md.ActiveView
            old = mv.Orientation3
            mu = self._com(app, "GetMathUtility")
            did = mu._oleobj_.GetIDsOfNames("CreateTransform")
            tr = win32com.client.Dispatch(mu._oleobj_.Invoke(did, 0, pythoncom.DISPATCH_METHOD, True, _arr16(vals)))
            mv.Orientation3 = tr
            md.NameView(name)
            try:
                mv.Orientation3 = old
            except Exception:
                pass
            if not was_dirty and bool(self._com(md, "GetSaveFlag")):
                e1 = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                w1 = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                md.Save3(1, e1, w1)
                msg = "modello salvato con la vista nominata"
        except Exception as ex:
            logger.debug(f"named view: {ex}")
            return None, str(ex)
        finally:
            try:
                app.ActivateDoc3(dtitle, False, 0, win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0))
            except Exception:
                pass
        return name, msg

    # ------------------------------------------------------------------ lettera
    def _aux_next_label(self, doc, wanted: str) -> str:
        used = set(getattr(self, "_aux_labels", {}).get(self._get_doc_title(doc), set()))
        for v in self._sheet_views(doc):
            nm = str(self._com(v, "GetName2"))
            for m in re.finditer(r"\b([A-Z])-\1\b|\b(?:dettaglio|vista|view|detail)\s+([A-Z])\b", nm, re.I):
                used.add((m.group(1) or m.group(2) or "").upper())
        if wanted and wanted.strip():
            return wanted.strip()[:3]
        for ch in "ABCDEFGHJKLMNPRSTUVWXYZ":
            if ch not in used:
                return ch
        return "A"

    # ------------------------------------------------------------------ tool
    def add_auxiliary_view(self, parent_view: str = None, edge_x: float = 0.0, edge_y: float = 0.0,
                           view_x: float = None, view_y: float = None, flip: bool = False,
                           label: str = "", unit: str = None) -> Dict:
        """Vista ausiliaria perpendicolare a uno spigolo rettilineo della vista madre (che di norma e' la faccia inclinata
        vista di taglio): la faccia appare in vera grandezza. (edge_x, edge_y) = punto su/vicino allo spigolo, coordinate
        foglio. NON usa CreateAuxiliaryViewAt2 (instabile): vista nominata AUX_n nel modello + CreateDrawViewFromModelView3.
        La vista si pone sulla perpendicolare allo spigolo (view_x/view_y: si usa la proiezione su quella retta);
        freccia con lettera sullo spigolo e titolo "VISTA x"."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            parent, err = self._find_view(doc, parent_view)
            if err:
                return err
            mpath = self._view_model_path(parent)
            mdoc = parent.ReferencedDocument
            if mdoc is None or int(self._com(mdoc, "GetType")) != 1:
                return self._result(False, "La vista ausiliaria e' disponibile per viste di un PEZZO (non di un assieme)",
                                    SwErrors.swInvalidInput)
            if self._is_pictorial(parent):
                return self._result(False, "La vista madre non puo' essere un'isometrica: usa una vista ortogonale",
                                    SwErrors.swInvalidInput)
            ex, ey = self._m(edge_x, unit), self._m(edge_y, unit)
            pk = self._aux_pick_edge(parent, ex, ey)
            if pk is None:
                return self._result(False, "Nessuno spigolo rettilineo visibile vicino al punto indicato nella vista madre",
                                    SwErrors.swInvalidInput)
            X, Y, Z = self._aux_frame(parent)
            e = pk["dir"]
            ep = _unit(tuple(e[i] - _dot(e, Z) * Z[i] for i in range(3)))
            if ep is None or math.sqrt(max(0.0, 1.0 - _dot(e, Z) ** 2)) < 0.1:
                return self._result(False, "Lo spigolo e' perpendicolare alla vista (si vede come un punto): sceglierne un altro",
                                    SwErrors.swInvalidInput)
            n3 = _unit(_cross(Z, ep))
            ns = (_dot(n3, X), _dot(n3, Y))
            mid = ((pk["a"][0] + pk["b"][0]) / 2.0, (pk["a"][1] + pk["b"][1]) / 2.0)
            pr = self._view_rect(parent)
            pc = ((pr[0] + pr[2]) / 2.0, (pr[1] + pr[3]) / 2.0)
            if (mid[0] - pc[0]) * ns[0] + (mid[1] - pc[1]) * ns[1] < 0:
                n3, ns = tuple(-x for x in n3), (-ns[0], -ns[1])
            if flip:
                n3, ns = tuple(-x for x in n3), (-ns[0], -ns[1])
            sinp = _dot(_cross(ep, Z), n3)
            sinp = 1.0 if sinp >= 0 else -1.0

            def rot(vv):
                c = _cross(ep, vv)
                d = _dot(ep, vv)
                return tuple(ep[i] * d + sinp * c[i] for i in range(3))
            cols = (rot(X), rot(Y), n3)

            lab = self._aux_next_label(doc, label)
            vname, nmsg = self._aux_named_view(doc, mdoc, mpath, cols)
            if not vname:
                return self._result(False, f"Vista nominata non creata: {nmsg}", SwErrors.swUnknownError)
            doc2, err = self._drawing()
            if err:
                return err
            doc = doc2
            W, H, _ = self._sheet_dims(doc)
            av = doc.CreateDrawViewFromModelView3(mpath, vname, W / 2, H / 2, 0)
            doc.ClearSelection2(True)
            if av is None:
                return self._result(False, "Creazione della vista ausiliaria fallita", SwErrors.swUnknownError)
            try:
                av.UseSheetScale = False
                av.ScaleDecimal = float(parent.ScaleDecimal)
            except Exception:
                pass
            try:
                av.SetName2(f"Vista {lab}")
            except Exception:
                pass
            if not hasattr(self, "_aux_labels"):
                self._aux_labels = {}
            self._aux_labels.setdefault(self._get_doc_title(doc), set()).add(lab.upper())

            # posizione: sulla perpendicolare allo spigolo, fuori dalla madre e dalle altre viste
            ar = self._view_rect(av)
            aw, ah = ar[2] - ar[0], ar[3] - ar[1]
            occ = self._occupied(doc, exclude=av)
            occ.append(tuple(pr))


            def rect_at(t):
                cx, cy = pc[0] + ns[0] * t, pc[1] + ns[1] * t
                return (cx - aw / 2, cy - ah / 2, cx + aw / 2, cy + ah / 2)

            from .drawing_layout import _inter
            t_found = None
            ok_rect = lambda r, g: (r[0] >= 0.01 and r[1] >= 0.01 and r[2] <= W - 0.01 and r[3] <= H - 0.01
                                    and not any(_inter(r, o, g) for o in occ))
            if view_x is not None and view_y is not None:
                vx_, vy_ = self._m(view_x, unit), self._m(view_y, unit)
                t_req = max(0.0, (vx_ - pc[0]) * ns[0] + (vy_ - pc[1]) * ns[1])
                if ok_rect(rect_at(t_req), 0.004):          # la posizione richiesta e' libera: la si rispetta
                    t_found = t_req
            if t_found is None:
                for gap in (0.025, 0.012, 0.005):
                    t = 0.03
                    while t < 0.9 and t_found is None:
                        if ok_rect(rect_at(t), gap):
                            t_found = t
                        t += 0.005
                    if t_found is not None:
                        break
            on_line = t_found is not None
            placed = on_line
            if not on_line:
                t_found = 0.0
                self._place_free(doc, av, (pc[0] + ns[0] * 0.1, pc[1] + ns[1] * 0.1))
                placed = bool(getattr(self, "_last_place_ok", False))
            else:
                self._set_pos(av, pc[0] + ns[0] * t_found, pc[1] + ns[1] * t_found)
            ar = self._view_rect(av)
            aligned = False
            if on_line and (abs(ns[0]) < 0.02 or abs(ns[1]) < 0.02):
                aligned = self._aux_align(av, parent, vertical=abs(ns[0]) < 0.02)

            # verifica sul risultato reale: la faccia di riferimento deve guardare lo spettatore
            Xa, Ya, Za = self._aux_frame(av)
            face = self._aux_face_ratio(pk["edge"], Za)
            ratio = round(abs(face["cos"]), 5) if face else None

            note = self._aux_annotate(doc, parent, av, pk, lab, ns, mid)
            doc.ClearSelection2(True)
            info = self._view_info(av)
            info.update({"label": lab, "named_view": vname, "view_direction_in_model": [round(x, 4) for x in n3],
                         "sheet_direction": [round(ns[0], 4), round(ns[1], 4)],
                         "edge_direction_deg": round(math.degrees(math.atan2(pk["b"][1] - pk["a"][1], pk["b"][0] - pk["a"][0])) % 180.0, 2),
                         "aligned_with_parent": aligned, "placed_in_free_space": placed, "on_projection_line": on_line,
                         "reference_face_area_mm2": face["area_mm2"] if face else None,
                         "reference_face_true_size_ratio": ratio, "model_note": nmsg,
                         "arrow_note": note})
            msg = f"Vista ausiliaria {lab}: {self._com(av, 'GetName2')}"
            if ratio is not None:
                msg += f" (faccia in vera grandezza al {ratio * 100:.1f}%)"
            if not placed:
                msg += " - ATTENZIONE: nessuno spazio libero sul foglio, la vista si sovrappone"
            elif not on_line:
                msg += " (non sulla perpendicolare allo spigolo: li' non c'era posto)"
            return self._result(True, msg, SwErrors.swSuccess, info)
        except Exception as e:
            return self._fail("add_auxiliary_view", e)

    def _aux_align(self, av, parent, vertical: bool) -> bool:
        """Allinea la vista ausiliaria alla madre (stessa colonna o stessa riga dei centri) se la posizione resta quella."""
        try:
            before = self._view_rect(av)
            av.AlignWithView(3 if vertical else 1, parent)       # 3 = centri verticali (stesso X), 1 = centri orizzontali (stesso Y)
            after = self._view_rect(av)
            return abs(after[0] - before[0]) < 5e-4 and abs(after[1] - before[1]) < 5e-4
        except Exception as e:
            logger.debug(f"AlignWithView: {e}")
            return False

    def _aux_annotate(self, doc, parent, av, pk, lab: str, ns, mid) -> Dict:
        """Freccia di direzione (nota con richiamo e punta sullo spigolo) + lettera, e titolo 'VISTA x' sotto la vista."""
        out = {"arrow": False, "title": False}
        try:
            mx, my = mid
            # posto della lettera: sulla perpendicolare uscente dallo spigolo, il primo a distanza crescente dove ne' il testo ne' la
            # linea di richiamo toccano linee di quota, altre note, altre viste
            from .drawing_layout import _inter
            obst, segs = [], []
            try:
                for a_ in self._dq_annotations(doc):
                    if a_["kind"] == "dimension":
                        segs += [tuple(l) for l in a_.get("lines", [])]
                        obst.append(tuple(a_["rect"]))
                    elif a_.get("view") == "sheet" or a_["kind"] in ("note", "gtol", "table", "surface_finish", "balloon"):
                        obst.append(tuple(a_["rect"]))
                for v_ in self._sheet_views(doc):
                    if self._com(v_, "GetName2") != self._com(av, "GetName2"):
                        obst.append(tuple(self._view_rect(v_)))
                obst.append(tuple(self._view_rect(av)))
            except Exception as e:
                logger.debug(f"aux obstacles: {e}")
            tw, th = 0.0035 * max(1, len(lab)) + 0.002, 0.0055
            best = None
            for dist in (0.022, 0.028, 0.034, 0.042, 0.052):
                for lat in (0.0, 0.008, -0.008):
                    px = mx + ns[0] * dist - ns[1] * lat
                    py = my + ns[1] * dist + ns[0] * lat
                    rect = (px - 0.001, py - th - 0.001, px + tw + 0.001, py + 0.001)
                    if any(_inter(rect, o, 0.0005) for o in obst):
                        continue
                    leader = (mx, my, px + tw / 2.0, py - th / 2.0)
                    if any(_seg_hits_rect(sg, rect) or _seg_hits_rect(leader, (min(sg[0], sg[2]) - 1e-4, min(sg[1], sg[3]) - 1e-4,
                                                                                max(sg[0], sg[2]) + 1e-4, max(sg[1], sg[3]) + 1e-4))
                           for sg in segs):
                        continue
                    best = (px, py)
                    break
                if best:
                    break
            if best is None:
                best = (mx + ns[0] * 0.022, my + ns[1] * 0.022)
            if self._select_edge_at(doc, mx * 1000.0, my * 1000.0, "mm"):
                note = doc.InsertNote(lab)
                if note is not None:
                    ann = note.GetAnnotation
                    ann.SetPosition2(best[0], best[1], 0)
                    out["arrow"] = int(ann.GetLeaderCount) > 0
            doc.ClearSelection2(True)
        except Exception as e:
            logger.debug(f"aux arrow: {e}")
        try:
            ar = self._view_rect(av)
            h = 0.0035
            txt = f"{drawing_text('aux_view', self._ui_language())} {lab}"
            tw = 0.0028 * len(txt)
            x0 = (ar[0] + ar[2]) / 2.0 - tw / 2.0
            y0 = ar[1] - 0.004 - h
            W, H, _ = self._sheet_dims(doc)
            if y0 < 0.012:
                y0 = ar[3] + 0.004
            n = doc.CreateText2(txt, x0, y0, 0, h, 0)
            out["title"] = n is not None
        except Exception as e:
            logger.debug(f"aux title: {e}")
        return out
