"""
Lotto SCHIZZO 4: strumenti sketch avanzati (mixin Sketch4Operations).
Intersezioni 3D, silhouette, offset su superficie, sketch chain/path, segmentazione,
asole 3 punti, curve 3D da equazione, analisi di curvatura e diagnostica relazioni.
"""

import math
import os
import logging
import traceback
from typing import Dict, List, Any

import win32com.client
import pythoncom

from ..constants import SwErrors
from ..utils.safe_math import safe_eval

logger = logging.getLogger(__name__)


def _eval_math_expr(expr: str, t_val: float) -> float:
    """Valuta in sicurezza un'espressione matematica f(t) per curve parametriche."""
    safe_dict = {
        "t": t_val,
        "pi": math.pi,
        "e": math.e,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "asin": math.asin,
        "acos": math.acos,
        "atan": math.atan,
        "sinh": math.sinh,
        "cosh": math.cosh,
        "tanh": math.tanh,
        "sqrt": math.sqrt,
        "sqr": math.sqrt,
        "exp": math.exp,
        "log": math.log,
        "ln": math.log,
        "abs": abs,
    }
    return safe_eval(expr, safe_dict)            # niente eval: solo numeri, operatori e le funzioni elencate sopra


class Sketch4Operations:
    """Lotto 4: strumenti sketch avanzati (ISketchManager, ISketchSpline, ISketchPath)."""

    def _s4_sd(self, doc, mark: int = 0):
        try:
            return self._sd(doc, mark)
        except Exception:
            return None

    def _s4_segs(self, doc) -> List[Any]:
        """Elenco di segmenti dello schizzo attivo."""
        try:
            sk = self._com(doc.SketchManager, "ActiveSketch")
            if sk is None:
                return []
            return list(self._com(sk, "GetSketchSegments") or [])
        except Exception:
            return []

    def _s4_seg_type(self, s) -> int:
        try:
            t = getattr(s, "GetType", None)
            if callable(t):
                return int(t())
            return int(t)
        except Exception:
            return -1

    def _safe_seg_id(self, s) -> str:
        try:
            return self._seg_id(s)
        except Exception:
            try:
                n = getattr(s, "GetName", None)
                return str(n() if callable(n) else (n or "seg"))
            except Exception:
                return "seg"


    def sketch_offset_on_surface(self, edges: list = None, distance: float = 5.0, reverse: bool = False,
                                 unit: str = None) -> Dict:
        """Curva a distanza `distance` da spigoli del modello, SULLA faccia adiacente (Offset su superficie), in uno
        schizzo 3D (aperto se manca). IModelDocExtension.SketchOffsetOnSurface(distanza, inverti, UseFront=True, False):
        misurato 19/11 su un blocco: lo spigolo superiore va a 5 mm sulla faccia di sopra, con reverse sulla faccia di
        lato; con UseFront=False non crea nulla. Ogni curva nuova si controlla: il suo punto medio sta a `distance`
        dallo spigolo."""
        try:
            doc, err = self._part()
            if err:
                return err
            if not edges:
                return self._result(False, "Servono gli spigoli: edges = [[x,y,z], ...] (punti SUGLI spigoli).",
                                    SwErrors.swInvalidInput)
            sm = doc.SketchManager
            sk = self._com(sm, "ActiveSketch")
            opened = False
            if sk is None:
                sm.Insert3DSketch(True)
                sk, opened = self._com(sm, "ActiveSketch"), True
            elif not self._s2_is3d(sk):
                return self._result(False, "Serve uno schizzo 3D (o nessuno schizzo aperto): lo schizzo attivo e' 2D.",
                                    SwErrors.swSketchError)
            doc.ClearSelection2(True)
            picked = []
            for i, pt in enumerate(edges):
                ok, info = self._select_point(doc, "edge", pt, unit, i > 0, 0)
                if not ok:
                    return self._result(False, f"Spigolo {pt}: {info.get('error')}", SwErrors.swSelectionError)
                picked.append(doc.SelectionManager.GetSelectedObject6(i + 1, -1))
            d_m = self._mmu(distance, unit)
            before = {self._seg_id(x) for x in self._segments(sk)}
            ok = bool(doc.Extension.SketchOffsetOnSurface(d_m, bool(reverse), True, False))
            doc.ClearSelection2(True)
            new = [x for x in self._segments(sk) if self._seg_id(x) not in before]
            rows, bad = [], []
            for x in new:
                try:
                    c = list(x.GetCurve.GetClosestPointOn(0.0, 0.0, 0.0))[:3]        # un punto della curva nuova
                    a, b2 = x.GetStartPoint2, x.GetEndPoint2
                    mid = [(a.X + b2.X) / 2, (a.Y + b2.Y) / 2, (a.Z + b2.Z) / 2] if int(x.GetType) == 0 else c
                    dist = min(math.dist(mid, list(e.GetClosestPointOn(*mid))[:3]) for e in picked)
                except Exception:
                    dist = None
                rows.append({"id": self._seg_id(x), "length": round(self._from_m(float(x.GetLength), unit), 5),
                             "distance_from_edge": None if dist is None else round(self._from_m(dist, unit), 5)})
                if dist is None or abs(dist - d_m) > 1e-6:
                    bad.append(rows[-1]["id"])
            data = {"sketch": self._s2_name(doc, sk), "sketch_opened": opened, "curves": rows, "distance": distance,
                    "reverse": bool(reverse)}
            if not ok or not new or bad:
                return self._result(False, f"Offset su superficie non come chiesto: {len(new)} curve nuove"
                                    + (f", a distanza sbagliata: {bad}" if bad else ""), SwErrors.swSketchError, data)
            return self._result(True, f"{len(new)} curve a {distance} dallo spigolo sulla faccia (schizzo {data['sketch']})",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"sketch_offset_on_surface: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    # ====================================================================
    # 2. Percorsi, Asole e Segmentazione
    # ====================================================================
    def make_sketch_chain(self, entities: list = None) -> Dict:
        """Unisce segmenti continui in un unico oggetto SketchPath (perno per Path Mate)."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            sm = doc.SketchManager
            segs = self._s4_segs(doc)
            sd = self._s4_sd(doc, 0)
            doc.ClearSelection2(True)
            sel_n = 0
            if entities:
                by_id = {self._safe_seg_id(s): s for s in segs}
                for ent_id in entities:
                    s = by_id.get(ent_id)
                    if s is None:
                        return self._result(False, f"make_sketch_chain: '{ent_id}' non trovato", SwErrors.swSelectionError)
                    if not bool(s.Select4(sel_n > 0, sd)):
                        return self._result(False, f"make_sketch_chain: selezione '{ent_id}' non riuscita.", SwErrors.swSelectionError)
                    sel_n += 1
            else:
                for s in segs:
                    if not bool(s.Select4(sel_n > 0, sd)):
                        return self._result(False, "make_sketch_chain: selezione di un segmento non riuscita.", SwErrors.swSelectionError)
                    sel_n += 1
            if sel_n == 0:
                return self._result(False, "make_sketch_chain: nessun segmento da concatenare.", SwErrors.swSelectionError)

            paths_before = sum(1 for s in segs if int(self._com(s, "GetSketchPathCount") or 0) > 0)
            try:
                ok = bool(self._com(sm, "MakeSketchChain"))
            except Exception as ex:
                return self._result(False, f"make_sketch_chain: creazione percorso non riuscita: {ex}", SwErrors.swSketchError)
            paths_after = sum(1 for s in self._s4_segs(doc) if int(self._com(s, "GetSketchPathCount") or 0) > 0)
            if paths_after <= paths_before:
                return self._result(False, f"make_sketch_chain: SolidWorks non ha creato il percorso (MakeSketchChain={ok}, segmenti in percorso prima {paths_before} dopo {paths_after}).", SwErrors.swSketchError)

            msg = "Percorso continuo (SketchPath / Chain) creato con successo."
            return self._result(True, msg, SwErrors.swSuccess, {
                "chain_created": True,
                "segment_count": paths_after
            })
        except Exception as e:
            logger.error(f"make_sketch_chain: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def segment_sketch_entity(self, entity: str = None, count: int = 4, is_segments: bool = False) -> Dict:
        """Divide un'entità in N parti uguali o piazza N punti equidistanti."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            sm = doc.SketchManager
            segs = self._s4_segs(doc)

            # (revisione 2026-11-12) prima: senza `entity` prendeva l'ULTIMO segmento creato (non la selezione) e divideva
            # sempre per interpolazione lineare fra gli estremi, quindi su archi e cerchi i punti cadevano sulla corda.
            # Ora: entita' per id oppure il segmento selezionato; linee e archi/cerchi divisi a pari lunghezza sulla curva;
            # ellissi e spline rifiutate; il risultato e' riletto (punti o segmenti in piu' nello schizzo).
            target = None
            if entity:
                by_id = {self._safe_seg_id(s): s for s in segs}
                target = by_id.get(entity)
                if target is None:
                    return self._result(False, f"segment_sketch_entity: '{entity}' non trovato", SwErrors.swSelectionError)
            else:
                try:
                    sm_sel = doc.SelectionManager
                    for i in range(1, int(sm_sel.GetSelectedObjectCount2(-1)) + 1):
                        o = sm_sel.GetSelectedObject6(i, -1)
                        if o is not None and self._s4_seg_type(o) >= 0 and hasattr(o, "GetStartPoint2"):
                            target = o
                            break
                except Exception:
                    target = None
            if target is None:
                return self._result(False, "segment_sketch_entity: indica `entity` (id da list_sketch_entities) oppure "
                                    "seleziona prima il segmento.", SwErrors.swSelectionError)

            n = int(count or 4)
            if n < 2 or n > 1000:
                return self._result(False, "segment_sketch_entity: count fra 2 e 1000.", SwErrors.swInvalidInput)

            seg_type = self._s4_seg_type(target)            # 0 linea, 1 arco/cerchio
            if seg_type not in (0, 1):
                return self._result(False, f"segment_sketch_entity: solo linee, archi e cerchi (tipo {seg_type}): per "
                                    "ellissi e spline i punti a pari distanza non sono calcolabili qui.", SwErrors.swInvalidInput)
            try:
                sp = self._com(target, "GetStartPoint2")
                ep = self._com(target, "GetEndPoint2")
                x1, y1, z1 = float(sp.X), float(sp.Y), float(sp.Z)
                x2, y2, z2 = float(ep.X), float(ep.Y), float(ep.Z)
            except Exception as ex:
                return self._result(False, f"segment_sketch_entity: estremi dell'entità non leggibili ({ex}).", SwErrors.swSketchError)
            closed = False
            if seg_type == 0:
                def at(t):
                    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1), z1 + t * (z2 - z1))
            else:
                c = self._com(target, "GetCenterPoint2")
                cx, cy = float(c.X), float(c.Y)
                closed = bool(self._com(target, "IsCircle"))
                try:
                    r = float(self._com(target, "GetRadius"))
                except Exception:
                    r = math.hypot(x1 - cx, y1 - cy)
                if closed:          # per un cerchio il "punto iniziale" non sta sulla curva: si parte dall'asse +x
                    x1, y1 = cx + r, cy
                a0 = math.atan2(y1 - cy, x1 - cx)
                ccw = int(self._com(target, "GetRotationDir")) == 1
                if closed:
                    sweep = 2 * math.pi
                else:
                    a1 = math.atan2(y2 - cy, x2 - cx)
                    sweep = (a1 - a0) % (2 * math.pi) if ccw else -((a0 - a1) % (2 * math.pi))
                if closed and not ccw:
                    sweep = -sweep

                def at(t):
                    a = a0 + t * sweep
                    return (cx + r * math.cos(a), cy + r * math.sin(a), z1)

            n_pts_before = len(list(self._com(self._com(sm, "ActiveSketch"), "GetSketchPoints2") or []))
            n_segs_before = len(segs)
            pts = [at(k / float(n)) for k in range(1, n)]          # n-1 punti interni (n parti)
            if closed:
                pts = [at(0.0)] + pts                              # cerchio: n punti per n archi
            doc.ClearSelection2(True)
            if is_segments:
                try:
                    if closed:
                        # cerchio: la prima divisione vuole due punti (diventa due archi), poi come un segmento aperto
                        sm.SplitClosedSegment(pts[0][0], pts[0][1], pts[0][2], pts[1][0], pts[1][1], pts[1][2])
                        rest = pts[2:]
                    else:
                        rest = pts
                    for p in rest:
                        sm.SplitOpenSegment(p[0], p[1], p[2])
                except Exception as ex:
                    return self._result(False, f"segment_sketch_entity: divisione non riuscita: {ex}", SwErrors.swSketchError)
                got = len(self._s4_segs(doc)) - n_segs_before
                want = n - 1
            else:
                for k, p in enumerate(pts, 1):
                    if sm.CreatePoint(p[0], p[1], p[2]) is None:
                        return self._result(False, f"segment_sketch_entity: SolidWorks non ha creato il punto {k}.", SwErrors.swSketchError)
                got = len(list(self._com(self._com(sm, "ActiveSketch"), "GetSketchPoints2") or [])) - n_pts_before
                want = len(pts)
            pts_mm = [[round(p[0] * 1000, 4), round(p[1] * 1000, 4)] for p in pts]
            if got < want:
                return self._result(False, f"segment_sketch_entity: attesi {want} {'segmenti' if is_segments else 'punti'} "
                                    f"in piu', SolidWorks ne mostra {got}.", SwErrors.swSketchError,
                                    {"expected": want, "found": got, "points_mm": pts_mm})
            mode_str = "segmenti" if is_segments else "punti equidistanti"
            msg = f"Suddivisione in {n} parti: {want} {mode_str} in piu' (riletti dallo schizzo)."
            return self._result(True, msg, SwErrors.swSuccess, {
                "segmented": True,
                "count": n,
                "created_points_count": want,
                "points_mm": pts_mm,
                "is_segments": bool(is_segments)
            })
        except Exception as e:
            logger.error(f"segment_sketch_entity: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def draw_3point_arc_slot(self, x1: float, y1: float, x2: float, y2: float,
                             x3: float, y3: float, width: float = 10.0, unit: str = None) -> Dict:
        """Asola ad arco per 3 punti (centro dell'estremo iniziale, centro dell'estremo finale, punto sull'arco centrale).
        (revisione 2026-11-12) prima usava il tipo 2 di CreateSketchSlot (arco dal CENTRO) con tre punti di passaggio:
        un'asola diversa da quella chiesta. Ora passa a draw_slot(slot_type='arc_3point'), misurato."""
        r = self.draw_slot(x1=x1, y1=y1, x2=x2, y2=y2, x3=x3, y3=y3, width=width or 10.0, unit=unit, slot_type="arc_3point")
        if r.get("success"):
            r["data"].update({"slot_created": True, "slot_type": "3point_arc", "endpoints": [[x1, y1], [x2, y2], [x3, y3]]})
        return r

    def draw_sketch_text_along_curve(self, text: str, curve_entity: str = None, height: float = 5.0,
                                     mirror_horizontal: bool = False, mirror_vertical: bool = False,
                                     unit: str = None) -> Dict:
        """Testo di schizzo che segue una curva dello schizzo (id in curve_entity).
        (revisione 2026-11-12) prima la curva era selezionata con Mark 0 e il testo finiva nell'origine, orizzontale; l'altezza
        era ignorata. La guida dell'API (IModelDoc2.InsertSketchText) chiede la curva selezionata con Mark = 1 e, se sta nello
        stesso schizzo del testo, come geometria di costruzione. L'altezza si imposta con il formato del testo e si rilegge."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err
            if not text:
                return self._result(False, "Testo mancante", SwErrors.swInvalidInput)
            if not curve_entity:
                return self._result(False, "draw_sketch_text_along_curve: serve curve_entity (id da list_sketch_entities); per un "
                                    "testo libero usa add_sketch_text.", SwErrors.swInvalidInput)
            if height is None or float(height) <= 0:
                return self._result(False, "height deve essere > 0", SwErrors.swInvalidInput)
            segs = self._s4_segs(doc)
            by_id = {self._safe_seg_id(s): s for s in segs}
            target = by_id.get(curve_entity)
            if target is None:
                return self._result(False, f"draw_sketch_text_along_curve: curva '{curve_entity}' non trovata", SwErrors.swSelectionError)
            made_construction = False
            if not bool(self._com(target, "ConstructionGeometry")):
                target.ConstructionGeometry = True
                made_construction = True
            doc.ClearSelection2(True)
            if not bool(target.Select4(False, self._s4_sd(doc, 1))):
                return self._result(False, "draw_sketch_text_along_curve: selezione della curva (Mark 1) non riuscita.",
                                    SwErrors.swSelectionError)
            flip = 1 if mirror_vertical else 0
            mirror = 1 if mirror_horizontal else 0
            res = doc.InsertSketchText(0.0, 0.0, 0.0, str(text), 0, flip, mirror, 100, 100)
            doc.ClearSelection2(True)
            if res is None:
                return self._result(False, "draw_sketch_text_along_curve: SolidWorks non ha inserito il testo.", SwErrors.swSketchError)
            h_m = self._mmu(float(height), unit)
            got_h = None
            try:
                tf = self._com(res, "GetTextFormat")      # oggetto COM: _com non lo chiama
                tf.CharHeight = h_m
                res.SetTextFormat(False, tf)
                got_h = float(self._com(res, "GetTextFormat").CharHeight)
            except Exception as ex:
                logger.debug(f"altezza del testo: {ex}")
            try:
                pos = [round(float(c) * 1000, 4) for c in (self._com(res, "GetCoordinates") or ())]
            except Exception:
                pos = None
            data = {"created": True, "text": text, "curve_entity": curve_entity, "curve_made_construction": made_construction,
                    "height_mm": round(got_h * 1000, 4) if got_h is not None else None, "insertion_point_mm": pos}
            if got_h is None or abs(got_h - h_m) > 1e-7:
                return self._result(False, f"Testo inserito ma altezza non impostata (letta {data['height_mm']} mm, chiesta "
                                    f"{round(h_m * 1000, 4)} mm).", SwErrors.swSketchError, data)
            return self._result(True, f"Testo '{text}' inserito lungo {curve_entity} (altezza {data['height_mm']} mm, riletta)"
                                + ("; la curva e' diventata di costruzione" if made_construction else ""), SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"draw_sketch_text_along_curve: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    # ====================================================================
    # 3. Curve Parametriche 3D
    # ====================================================================
    def draw_equation_curve_3d(self, x_expression: str, y_expression: str, z_expression: str,
                               start: float = 0.0, end: float = 6.28318, samples: int = 50,
                               unit: str = None) -> Dict:
        """Crea una curva 3D parametrica nello spazio tramite x(t), y(t), z(t)."""
        try:
            doc, err = self._part()
            if err:
                return err

            sm = doc.SketchManager
            sk = self._com(sm, "ActiveSketch")
            if sk is None:
                sm.Insert3DSketch(True)

            n_pts = max(10, min(500, int(samples or 50)))
            pts = []
            dt = (float(end) - float(start)) / float(n_pts - 1)

            for i in range(n_pts):
                t_val = float(start) + i * dt
                x_val = _eval_math_expr(x_expression, t_val)
                y_val = _eval_math_expr(y_expression, t_val)
                z_val = _eval_math_expr(z_expression, t_val)
                pts.append((self._mmu(x_val, unit), self._mmu(y_val, unit), self._mmu(z_val, unit)))

            arr_pts = [c for pt in pts for c in pt]
            var_arr = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, tuple(arr_pts))

            spline = None
            try:
                spline = sm.CreateSpline(var_arr)
            except Exception:
                try:
                    spline = sm.CreateSpline2(var_arr, False)
                except Exception as ex:
                    return self._result(False, f"draw_equation_curve_3d: creazione spline 3D non riuscita: {ex}", SwErrors.swSketchError)
            if spline is None:
                return self._result(False, "draw_equation_curve_3d: SolidWorks non ha creato la spline 3D.", SwErrors.swSketchError)

            p_start = [round(v, 4) for v in pts[0]]
            p_end = [round(v, 4) for v in pts[-1]]

            msg = f"Curva parametrica 3D creata ({n_pts} punti interpolati su t in [{start}, {end}])."
            return self._result(True, msg, SwErrors.swSuccess, {
                "samples_count": n_pts,
                "start_parameter": start,
                "end_parameter": end,
                "start_point_m": p_start,
                "end_point_m": p_end,
                "spline_created": True
            })
        except Exception as e:
            logger.error(f"draw_equation_curve_3d: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    # ====================================================================
    # 4. Modifica Topologica (Stretch, Align)
    # ====================================================================
    def stretch_sketch_entities(self, dx: float, dy: float, entities: list = None,
                                base_x: float = 0.0, base_y: float = 0.0, unit: str = None) -> Dict:
        """Stira entità di schizzo muovendo i vertici selezionati di delta (dx, dy)."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            dx_m = self._mmu(dx, unit)
            dy_m = self._mmu(dy, unit)

            chosen = []
            for ent_id in entities or []:
                s, e = self._s2_resolve(doc, _sk, ent_id, unit)    # id 'S0-1-2' oppure '@x,y'
                if e:
                    return self._result(False, f"stretch_sketch_entities: {e}", SwErrors.swSelectionError)
                chosen.append(s)
            ids = [self._seg_id(s) for s in chosen]
            before = {g["id"]: g for g in self._s2_snap(doc)}
            doc.ClearSelection2(True)
            selected_count = 0
            if chosen:
                for ent_id, s in zip(ids, chosen):
                    if not bool(s.Select4(selected_count > 0, self._s4_sd(doc, 0))):
                        return self._result(False, f"stretch_sketch_entities: selezione '{ent_id}' non riuscita.", SwErrors.swSelectionError)
                    selected_count += 1
            if selected_count == 0:
                return self._result(False, "stretch_sketch_entities: nessuna entità selezionata da stirare.", SwErrors.swSelectionError)

            # IModelDocExtension.Stretch e MoveOrCopy non muovono nulla (misurato 19/11, con e senza KeepRelations): si
            # spostano i PUNTI delle entita' scelte (posizione assoluta, due passate per il risolutore); le entita'
            # collegate seguono e si allungano, come Stira entita'
            pts = {}
            for s0 in chosen:
                for getter in ("GetStartPoint2", "GetEndPoint2", "GetCenterPoint2"):
                    try:
                        q = getattr(s0, getter)
                    except Exception:
                        continue
                    if q is None or self._pt_id(q) in pts:
                        continue
                    pts[self._pt_id(q)] = (q, float(q.X) + dx_m, float(q.Y) + dy_m)
            doc.ClearSelection2(True)
            for _pass in range(2):
                for q, tx, ty in pts.values():
                    q.X, q.Y = tx, ty
            # (revisione) riletto: ogni entita' scelta deve essersi spostata di (dx, dy)
            doc.ClearSelection2(True)
            after = {g["id"]: g for g in self._s2_snap(doc)}
            dmm = (self._from_m(dx_m, "mm"), self._from_m(dy_m, "mm"))
            wrong = []
            for i in ids:
                b, a = before.get(i), after.get(i)
                if not b or not a or "s" not in a or "s" not in b:
                    wrong.append(f"{i}: non piu' leggibile")
                    continue
                for k in ("s", "e"):
                    if abs(a[k][0] - b[k][0] - dmm[0]) > 1e-3 or abs(a[k][1] - b[k][1] - dmm[1]) > 1e-3:
                        wrong.append(f"{i}: {k} da {[round(v, 4) for v in b[k][:2]]} a {[round(v, 4) for v in a[k][:2]]}")
                        break
            moved = [i for i in after if i in before and before[i].get("s") != after[i].get("s")]
            # il punto base non cambia lo stiramento (conta solo lo spostamento): si restituisce con la sua destinazione
            data = {"dx": dx, "dy": dy, "entities_count": selected_count, "entities_moved_or_stretched": moved,
                    "base_point": [base_x, base_y], "base_point_destination": [base_x + dx, base_y + dy]}
            if wrong:
                return self._result(False, "Stiramento non come chiesto: " + "; ".join(wrong), SwErrors.swSketchError, data)
            u = unit or "mm"
            msg = f"Entita' {ids} spostate di ({dx}, {dy}) {u}; toccate in tutto: {moved}"
            return self._result(True, msg, SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"stretch_sketch_entities: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def align_sketch_entities(self, source_points: list, target_points: list,
                              entities: list = None, unit: str = None) -> Dict:
        """Allinea entita' di uno schizzo 2D con 1 coppia di punti (spostamento) o 2 coppie (spostamento + rotazione:
        il primo punto va sul primo bersaglio, la direzione 1->2 su quella dei bersagli; la distanza non si scala).
        SolidWorks non ha un'API "allinea": si usa MoveOrCopy/RotateOrCopy (centro portato nell'origine, vedi ext_sketch2)
        e si rilegge la posizione di ogni entita' confrontandola con la trasformazione calcolata."""
        try:
            doc, sk, err = self._s2_active_or_open()
            if err:
                return err
            if not source_points or not target_points or len(source_points) != len(target_points):
                return self._result(False, "source_points e target_points devono contenere lo stesso numero di punti.",
                                    SwErrors.swInvalidInput)
            n = len(source_points)
            if n not in (1, 2):
                return self._result(False, f"Allineamento con {n} punti non supportato (1 o 2, schizzo 2D).",
                                    SwErrors.swInvalidInput)
            if any(len(q) > 2 and abs(float(q[2])) > 1e-9 for q in list(source_points) + list(target_points)):
                return self._result(False, "Solo schizzi 2D: i punti hanno una Z diversa da 0.", SwErrors.swInvalidInput)
            if not entities:
                return self._result(False, "Indica le entita' da allineare (id o '@x,y').", SwErrors.swInvalidInput)
            segs = []
            for ref in entities:
                seg, e = self._s2_resolve(doc, sk, ref, unit)
                if e:
                    return self._result(False, f"align_sketch_entities: {e}", SwErrors.swSelectionError)
                segs.append(seg)
            mm = lambda q: (self._from_m(self._mmu(float(q[0]), unit), "mm"), self._from_m(self._mmu(float(q[1]), unit), "mm"))
            s1, t1 = mm(source_points[0]), mm(target_points[0])
            ang = 0.0
            if n == 2:
                s2, t2 = mm(source_points[1]), mm(target_points[1])
                ang = math.atan2(t2[1] - t1[1], t2[0] - t1[0]) - math.atan2(s2[1] - s1[1], s2[0] - s1[0])
            ids = [self._seg_id(x) for x in segs]
            before = {g["id"]: g for g in self._s2_snap(doc)}
            self._s2_select(doc, segs)
            doc.Extension.MoveOrCopy(False, 0, False, s1[0] / 1000, s1[1] / 1000, 0.0, 0.0, 0.0, 0.0)
            if abs(ang) > 1e-12:
                self._s2_select(doc, segs)
                doc.Extension.RotateOrCopy(False, 0, False, 0.0, 0.0, 0.0, 0.0, 0.0, 0.01, ang)
            self._s2_select(doc, segs)
            doc.Extension.MoveOrCopy(False, 0, False, 0.0, 0.0, 0.0, t1[0] / 1000, t1[1] / 1000, 0.0)
            doc.ClearSelection2(True)
            after = {g["id"]: g for g in self._s2_snap(doc)}
            c, sn = math.cos(ang), math.sin(ang)

            def tf(q):
                x, y = q[0] - s1[0], q[1] - s1[1]
                return (t1[0] + c * x - sn * y, t1[1] + sn * x + c * y)
            wrong = []
            for i in ids:
                b0, a0 = before.get(i), after.get(i)
                if not b0 or not a0 or "s" not in a0:
                    wrong.append(f"{i}: non piu' leggibile")
                    continue
                for k in ("s", "e"):
                    want = tf(b0[k])
                    if math.dist(want, a0[k][:2]) > 1e-3:
                        wrong.append(f"{i}: {k} in {[round(v, 4) for v in a0[k][:2]]} invece di {[round(v, 4) for v in want]}")
                        break
            data = {"mode": f"{n}_point", "entities": ids, "rotation_deg": round(math.degrees(ang), 6),
                    "translation_mm": [round(t1[0] - s1[0], 6), round(t1[1] - s1[1], 6)]}
            if wrong:
                return self._result(False, "Allineamento non come chiesto: " + "; ".join(wrong), SwErrors.swSketchError, data)
            return self._result(True, f"{len(ids)} entita' allineate ({n} punti, rotazione {data['rotation_deg']} gradi)",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"align_sketch_entities: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    # ====================================================================
    # 5. Analisi Curvatura e Diagnostica Relazioni
    # ====================================================================
    def show_sketch_curvature(self, entity: str = None, scale: float = 10.0,
                              density: float = 20.0, visible: bool = True) -> Dict:
        """Visualizza e configura i pettini di curvatura su spline o archi di schizzo."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            segs = self._s4_segs(doc)
            target = None
            if entity:
                by_id = {self._safe_seg_id(s): s for s in segs}
                target = by_id.get(entity)
                if target is None:
                    return self._result(False, f"show_sketch_curvature: '{entity}' non trovata", SwErrors.swSelectionError)
            else:
                for s in segs:
                    if self._s4_seg_type(s) == 3:  # swSketchSpline
                        target = s
                        break
                if target is None and segs:
                    target = segs[0]
            if target is None:
                return self._result(False, "show_sketch_curvature: nessuna entità nello schizzo.", SwErrors.swSelectionError)

            sm = doc.SketchManager
            # (revisione 2026-11-12) scala e densita' di partenza: tornano al loro posto se il tool fallisce a meta' e sono
            # riportate nel risultato (i pettini restano come chiesti dopo il tool: e' il suo scopo)
            prev = {}
            for key, attr in (("scale", "CurvatureScale"), ("density", "CurvatureDensity")):
                try:
                    prev[key] = getattr(sm, attr)
                except Exception:
                    prev[key] = None
            done = []
            try:
                sm.CurvatureScale = float(scale or 10.0)
                done.append(("scale", "CurvatureScale"))
                sm.CurvatureDensity = int(density or 20)
                done.append(("density", "CurvatureDensity"))
                target.ShowCurvatureCombs = bool(visible)
            except Exception as ex:
                for key, attr in reversed(done):
                    if prev[key] is not None:
                        try:
                            setattr(sm, attr, prev[key])
                        except Exception as ex2:
                            logger.warning(f"show_sketch_curvature: {attr} non ripristinato: {ex2}")
                return self._result(False, f"show_sketch_curvature: impostazione pettini non riuscita: {ex} (scala e densita' "
                                    "tornate come prima)", SwErrors.swSketchError, {"previous": prev})
            shown = bool(target.ShowCurvatureCombs)
            if shown != bool(visible):
                return self._result(False, "show_sketch_curvature: SolidWorks non ha cambiato la visualizzazione dei pettini.", SwErrors.swSketchError)

            state_str = "attivati" if visible else "disattivati"
            msg = f"Pettini di curvatura {state_str} (scala {scale}, densità {density})."
            return self._result(True, msg, SwErrors.swSuccess, {
                "curvature_displayed": True,
                "visible": shown,
                "scale": float(scale or 10.0),
                "density": int(density or 20),
                "previous": prev
            })
        except Exception as e:
            logger.error(f"show_sketch_curvature: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)


    # ====================================================================
    # 6. Immagini e Blocchi da File
    # ====================================================================
    def insert_sketch_picture(self, filepath: str, x: float = 0.0, y: float = 0.0,
                              width: float = None, height: float = None, angle: float = 0.0,
                              transparency: float = 0.0, unit: str = None) -> Dict:
        """Inserisce un'immagine raster (PNG, JPG, BMP) sul piano di schizzo."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            path = os.path.abspath(filepath)
            if not os.path.exists(path):
                return self._result(False, f"File immagine non trovato: {path}", SwErrors.swFileNotFoundError)

            sm = doc.SketchManager
            x_m = self._mmu(x, unit)
            y_m = self._mmu(y, unit)

            pic = None
            try:
                pic = sm.InsertSketchPicture2(path)
            except Exception:
                try:
                    pic = sm.InsertSketchPicture(path)
                except Exception as ex:
                    return self._result(False, f"insert_sketch_picture: inserimento immagine non riuscito: {ex}", SwErrors.swSketchError)
            if pic is None:
                return self._result(False, "insert_sketch_picture: SolidWorks non ha inserito l'immagine.", SwErrors.swSketchError)

            def r8():
                return win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_R8, 0.0)

            def pair(getter):
                a, b = r8(), r8()
                getattr(pic, getter)(a, b)
                return float(a.value), float(b.value)

            # (revisione 2026-11-12) prima ogni errore qui era ingoiato e il risultato ripeteva i valori chiesti: ora
            # si applica, si rilegge da SolidWorks e si confronta
            errors = []
            for what, fn in (("origine", lambda: pic.SetOrigin(x_m, y_m)),
                             ("dimensioni", lambda: self._pic_set_size(pic, pair, width, height, unit)),
                             ("angolo", lambda: setattr(pic, "Angle", math.radians(float(angle))) if angle else None),
                             ("trasparenza", lambda: pic.SetTransparency(3, float(transparency), 0, 0.0)
                              if transparency else None)):
                try:
                    fn()
                except Exception as ex:
                    errors.append(f"{what}: {ex}")
            data = {"filepath": path, "picture_loaded": True}
            bad = []
            try:
                ox, oy = pair("GetOrigin")
                data["origin"] = [round(self._from_m(ox, unit), 4), round(self._from_m(oy, unit), 4)]
                if abs(ox - x_m) > 1e-6 or abs(oy - y_m) > 1e-6:
                    bad.append(f"origine {data['origin']} invece di [{x}, {y}]")
            except Exception as ex:
                bad.append(f"origine non leggibile ({ex})")
            try:
                w_m, h_m = pair("GetSize")
                data["width"] = round(self._from_m(w_m, unit), 4)
                data["height"] = round(self._from_m(h_m, unit), 4)
                for k, want in (("width", width), ("height", height)):
                    if want is not None and abs(data[k] - float(want)) > 1e-3 * max(1.0, abs(float(want))):
                        bad.append(f"{k} {data[k]} invece di {want}")
            except Exception as ex:
                bad.append(f"dimensioni non leggibili ({ex})")
            try:
                data["angle_deg"] = round(math.degrees(float(pic.Angle)), 4)
                if abs(data["angle_deg"] - float(angle or 0.0)) > 1e-3:
                    bad.append(f"angolo {data['angle_deg']} invece di {angle}")
            except Exception as ex:
                bad.append(f"angolo non leggibile ({ex})")
            if transparency:
                try:
                    st, tr = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0), r8()
                    pic.GetTransparency(st, tr, win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0), r8())
                    data["transparency"] = round(float(tr.value), 4)
                    if abs(data["transparency"] - float(transparency)) > 0.6 / 255:   # SolidWorks la tiene in 1/255
                        bad.append(f"trasparenza {data['transparency']} invece di {transparency}")
                except Exception as ex:
                    bad.append(f"trasparenza non leggibile ({ex})")
            if errors:
                data["set_errors"] = errors
            if bad:
                data["mismatch"] = bad
                return self._result(False, "Immagine inserita ma non come chiesto: " + "; ".join(bad)
                                    + " (undo per toglierla)", SwErrors.swSketchError, data)
            u = unit or "mm"
            msg = f"Immagine di schizzo inserita: {os.path.basename(path)} in ({x}, {y} {u}), {data['width']} x {data['height']} {u}."
            return self._result(True, msg, SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"insert_sketch_picture: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def _pic_set_size(self, pic, pair, width, height, unit):
        """Dimensioni dell'immagine: con un solo valore l'altro segue le proporzioni attuali."""
        if width is None and height is None:
            return
        w0, h0 = pair("GetSize")
        w = self._mmu(width, unit) if width is not None else w0 * self._mmu(height, unit) / h0
        h = self._mmu(height, unit) if height is not None else h0 * self._mmu(width, unit) / w0
        pic.SetSize(w, h, False)

    def insert_sketch_block_from_file(self, filepath: str, x: float = 0.0, y: float = 0.0,
                                      scale: float = 1.0, angle: float = 0.0, unit: str = None) -> Dict:
        """Inserisce un'istanza di blocco di schizzo da file esterno .sldblk."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            path = os.path.abspath(filepath)
            if not os.path.exists(path):
                return self._result(False, f"File blocco non trovato: {path}", SwErrors.swFileNotFoundError)

            sm = doc.SketchManager
            x_m = self._mmu(x, unit)
            y_m = self._mmu(y, unit)

            before = {str(self._com(i, "Name")) for i in (self._com(_sk, "GetSketchBlockInstances") or ())}
            sc = float(scale or 1.0)
            ang_rad = math.radians(float(angle or 0.0))
            try:
                pt = self._math_point([x_m, y_m, 0.0])
                sm.MakeSketchBlockFromFile(pt, path, False, sc, ang_rad)
            except Exception as ex:
                return self._result(False, f"insert_sketch_block_from_file: inserimento blocco non riuscito: {ex}", SwErrors.swSketchError)
            # (revisione) prima il punto d'inserimento falliva in silenzio e il risultato ripeteva i valori chiesti: ora
            # si rilegge l'istanza nuova (posizione, scala, angolo)
            new = [i for i in (self._com(_sk, "GetSketchBlockInstances") or ()) if str(self._com(i, "Name")) not in before]
            if not new:
                return self._result(False, "insert_sketch_block_from_file: SolidWorks non ha inserito il blocco.", SwErrors.swSketchError)
            inst = new[0]
            pos = [float(v) for v in list(self._com(self._com(inst, "InstancePosition"), "ArrayData"))[:2]]
            data = {"filepath": path, "instance": str(self._com(inst, "Name")),
                    "insertion_point": [round(self._from_m(pos[0], unit), 4), round(self._from_m(pos[1], unit), 4)],
                    "scale": round(float(self._com(inst, "Scale")), 6),
                    "angle_deg": round(math.degrees(float(self._com(inst, "Angle"))), 4)}
            bad = []
            if math.hypot(pos[0] - x_m, pos[1] - y_m) > 1e-6:
                bad.append(f"posizione {data['insertion_point']} invece di [{x}, {y}]")
            if abs(data["scale"] - sc) > 1e-6:
                bad.append(f"scala {data['scale']} invece di {sc}")
            if abs((data["angle_deg"] - float(angle or 0.0) + 180) % 360 - 180) > 1e-3:
                bad.append(f"angolo {data['angle_deg']} invece di {angle}")
            if bad:
                return self._result(False, "Blocco inserito ma non come chiesto: " + "; ".join(bad) + " (undo per toglierlo)",
                                    SwErrors.swSketchError, data)
            msg = (f"Blocco {data['instance']} da {os.path.basename(path)} in {data['insertion_point']}, scala "
                   f"{data['scale']}, angolo {data['angle_deg']} gradi")
            return self._result(True, msg, SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"insert_sketch_block_from_file: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)
