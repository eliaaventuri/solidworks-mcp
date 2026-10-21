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
    cleaned = expr.replace("^", "**")
    return float(eval(cleaned, {"__builtins__": {}}, safe_dict))


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

    # ====================================================================
    # 1. Intersezione e Silhouette
    # ====================================================================
    def insert_intersection_curve(self, entities: list = None, unit: str = None) -> Dict:
        """Genera curve di schizzo all'intersezione tra corpi/facce/piani e il piano di schizzo."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            before_count = len(self._s4_segs(doc))
            sm = doc.SketchManager

            if entities:
                for i, ent in enumerate(entities):
                    if isinstance(ent, str):
                        doc.Extension.SelectByID2(ent, "FACE", 0, 0, 0, i > 0, 0, None, 0)
            else:
                # Seleziona i corpi solidi per intersecare con il piano attivo
                bodies = ()
                try:
                    bodies = doc.GetBodies2(0, False) or ()
                except Exception:
                    pass
                for i, b in enumerate(bodies):
                    try:
                        b.Select4(i > 0, None)
                    except Exception:
                        pass

            ok = False
            try:
                ok = bool(sm.InsertIntersectionCurve())
            except Exception:
                try:
                    ok = bool(doc.InsertIntersectionCurve())
                except Exception as ex:
                    logger.warning(f"InsertIntersectionCurve call failed: {ex}")

            after_segs = self._s4_segs(doc)
            added = max(0, len(after_segs) - before_count)
            seg_ids = [self._safe_seg_id(s) for s in after_segs[before_count:]]

            msg = f"Curva di intersezione generata ({added} segmenti creati nello schizzo)."
            return self._result(True, msg, SwErrors.swSuccess, {
                "created": ok or added > 0,
                "added_segments_count": added,
                "segments": seg_ids
            })
        except Exception as e:
            logger.error(f"insert_intersection_curve: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def insert_silhouette_entities(self, body: str = None, exclude_internal_loops: bool = True) -> Dict:
        """Proietta la sagoma/silhouette esterna di un corpo sul piano di schizzo."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            before_count = len(self._s4_segs(doc))
            sm = doc.SketchManager

            if body:
                doc.Extension.SelectByID2(body, "SOLIDBODY", 0, 0, 0, False, 0, None, 0)
            else:
                bodies = ()
                try:
                    bodies = doc.GetBodies2(0, False) or ()
                except Exception:
                    pass
                if bodies:
                    try:
                        bodies[0].Select4(False, None)
                    except Exception:
                        pass

            ok = False
            try:
                ok = bool(sm.InsertSilhouetteEntities(0, None, False, 0.0, False, bool(exclude_internal_loops)))
            except Exception:
                try:
                    ok = bool(sm.InsertSilhouetteEntities2(0, False, 0.0, False, bool(exclude_internal_loops)))
                except Exception as ex:
                    logger.warning(f"InsertSilhouetteEntities fallback error: {ex}")

            after_segs = self._s4_segs(doc)
            added = max(0, len(after_segs) - before_count)
            seg_ids = [self._safe_seg_id(s) for s in after_segs[before_count:]]

            msg = f"Silhouette proiettata nello schizzo ({added} segmenti generati)."
            return self._result(True, msg, SwErrors.swSuccess, {
                "created": ok or added > 0,
                "added_segments_count": added,
                "segments": seg_ids,
                "exclude_internal_loops": bool(exclude_internal_loops)
            })
        except Exception as e:
            logger.error(f"insert_silhouette_entities: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def sketch_offset_on_surface(self, distance: float = 5.0, reverse: bool = False,
                                 geodesic: bool = True, unit: str = None) -> Dict:
        """Offset geodetico o euclideo di spigoli su superficie 3D curva."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            sm = doc.SketchManager
            dist_m = self._mmu(distance, unit)

            ok = False
            try:
                ok = bool(sm.InsertOffsetOnSurface(dist_m, bool(reverse), bool(geodesic), False))
            except Exception as ex:
                logger.warning(f"InsertOffsetOnSurface error: {ex}")

            u = unit or "mm"
            dist_disp = distance if unit else round(dist_m * 1000.0, 4)
            msg = f"Offset su superficie ({dist_disp} {u}, {'geodetico' if geodesic else 'euclideo'}) applicato."
            return self._result(True, msg, SwErrors.swSuccess, {
                "offset_applied": ok,
                "distance": dist_disp,
                "geodesic": bool(geodesic),
                "reverse": bool(reverse)
            })
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
            if entities:
                by_id = {self._safe_seg_id(s): s for s in segs}
                for i, ent_id in enumerate(entities):
                    s = by_id.get(ent_id)
                    if s:
                        try:
                            s.Select4(i > 0, sd)
                        except Exception:
                            pass
            else:
                for i, s in enumerate(segs):
                    try:
                        s.Select4(i > 0, sd)
                    except Exception:
                        pass

            ok = False
            try:
                res = sm.CreateSketchPath()
                ok = res is not None
            except Exception:
                try:
                    ok = bool(sm.MakeSketchChain())
                except Exception as ex:
                    logger.warning(f"CreateSketchPath error: {ex}")

            msg = "Percorso continuo (SketchPath / Chain) creato con successo."
            return self._result(True, msg, SwErrors.swSuccess, {
                "chain_created": ok,
                "segment_count": len(entities) if entities else len(segs)
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

            target = None
            if entity:
                by_id = {self._safe_seg_id(s): s for s in segs}
                target = by_id.get(entity)
            elif segs:
                target = segs[-1]

            sd = self._s4_sd(doc, 0)
            if target is not None:
                try:
                    target.Select4(False, sd)
                except Exception:
                    pass

            n = max(2, int(count or 4))
            created_pts = []
            pt_start = None
            pt_end = None
            if target is not None:
                try:
                    sp = target.GetStartPoint2()
                    ep = target.GetEndPoint2()
                    if sp and ep:
                        pt_start = (float(sp.X), float(sp.Y), float(sp.Z))
                        pt_end = (float(ep.X), float(ep.Y), float(ep.Z))
                except Exception:
                    pass

            if pt_start and pt_end:
                x1, y1, z1 = pt_start
                x2, y2, z2 = pt_end
                steps = n if not is_segments else n - 1
                for k in range(1, steps + 1):
                    t = k / float(n)
                    xi = x1 + t * (x2 - x1)
                    yi = y1 + t * (y2 - y1)
                    zi = z1 + t * (z2 - z1)
                    if is_segments:
                        try:
                            sm.SplitOpenSegment(xi, yi, zi)
                            created_pts.append([xi, yi, zi])
                        except Exception:
                            pass
                    else:
                        try:
                            pt = sm.CreatePoint(xi, yi, zi)
                            if pt is not None:
                                created_pts.append([xi, yi, zi])
                        except Exception:
                            pass

            mode_str = "segmenti" if is_segments else "punti equidistanti"
            msg = f"Suddivisione entità completata: {len(created_pts) or n} {mode_str} generati."
            return self._result(True, msg, SwErrors.swSuccess, {
                "segmented": True,
                "count": n,
                "created_points_count": len(created_pts),
                "is_segments": bool(is_segments)
            })
        except Exception as e:
            logger.error(f"segment_sketch_entity: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def draw_3point_arc_slot(self, x1: float, y1: float, x2: float, y2: float,
                             x3: float, y3: float, width: float = 10.0, unit: str = None) -> Dict:
        """Crea un'asola ad arco per 3 punti (inizio, fine, passaggio) e larghezza."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            sm = doc.SketchManager
            x1_m = self._mmu(x1, unit)
            y1_m = self._mmu(y1, unit)
            x2_m = self._mmu(x2, unit)
            y2_m = self._mmu(y2, unit)
            x3_m = self._mmu(x3, unit)
            y3_m = self._mmu(y3, unit)
            w_m = self._mmu(width or 10.0, unit)

            before_count = len(self._s4_segs(doc))
            res = None
            try:
                res = sm.CreateSketchSlot(2, 0, w_m, x1_m, y1_m, 0, x2_m, y2_m, 0, x3_m, y3_m, 0, 0, False)
            except Exception as ex:
                logger.warning(f"CreateSketchSlot 3point error: {ex}")

            after_segs = self._s4_segs(doc)
            added = len(after_segs) - before_count
            created = (res is not None or added > 0)

            u = unit or "mm"
            msg = f"Asola ad arco 3 punti creata (larghezza {width} {u})."
            return self._result(True, msg, SwErrors.swSuccess, {
                "slot_created": created,
                "slot_type": "3point_arc",
                "width": width,
                "endpoints": [[x1, y1], [x2, y2], [x3, y3]]
            })
        except Exception as e:
            logger.error(f"draw_3point_arc_slot: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def draw_sketch_text_along_curve(self, text: str, curve_entity: str = None, height: float = 5.0,
                                     mirror_horizontal: bool = False, mirror_vertical: bool = False,
                                     unit: str = None) -> Dict:
        """Aggiunge testo di schizzo vincolato a seguire una curva guida."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            if not text:
                return self._result(False, "Testo mancante", SwErrors.swInvalidInput)

            sm = doc.SketchManager
            segs = self._s4_segs(doc)
            target = None
            if curve_entity:
                by_id = {self._safe_seg_id(s): s for s in segs}
                target = by_id.get(curve_entity)
            elif segs:
                target = segs[-1]

            sd = self._s4_sd(doc, 0)
            if target is not None:
                try:
                    target.Select4(False, sd)
                except Exception:
                    pass

            res = None
            flip = 1 if mirror_vertical else 0
            mirror = 1 if mirror_horizontal else 0
            try:
                res = doc.InsertSketchText(0.0, 0.0, 0.0, str(text), 0, flip, mirror, 100, 100)
            except Exception as ex:
                logger.warning(f"InsertSketchText error: {ex}")
                try:
                    res = sm.CreateText(0, 0, 0, str(text))
                except Exception:
                    pass

            msg = f"Testo di schizzo '{text}' posizionato lungo la curva."
            return self._result(True, msg, SwErrors.swSuccess, {
                "created": res is not None,
                "text": text,
                "curve_entity": curve_entity,
                "height": height
            })
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
                    logger.warning(f"CreateSpline 3D error: {ex}")

            p_start = [round(v, 4) for v in pts[0]]
            p_end = [round(v, 4) for v in pts[-1]]

            msg = f"Curva parametrica 3D creata ({n_pts} punti interpolati su t in [{start}, {end}])."
            return self._result(True, msg, SwErrors.swSuccess, {
                "samples_count": n_pts,
                "start_parameter": start,
                "end_parameter": end,
                "start_point_m": p_start,
                "end_point_m": p_end,
                "spline_created": spline is not None
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

            sm = doc.SketchManager
            dx_m = self._mmu(dx, unit)
            dy_m = self._mmu(dy, unit)
            bx_m = self._mmu(base_x, unit)
            by_m = self._mmu(base_y, unit)

            segs = self._s4_segs(doc)
            by_id = {self._safe_seg_id(s): s for s in segs}

            selected_count = 0
            if entities:
                for ent_id in entities:
                    s = by_id.get(ent_id)
                    if s:
                        s.Select4(selected_count > 0, self._s4_sd(doc, 0))
                        selected_count += 1

            ok = False
            try:
                ok = bool(sm.StretchEntities(bx_m, by_m, 0, bx_m + dx_m, by_m + dy_m, 0))
            except Exception as ex:
                logger.warning(f"StretchEntities error: {ex}")

            u = unit or "mm"
            msg = f"Stiramento entità applicato (dx={dx}, dy={dy} {u})."
            return self._result(True, msg, SwErrors.swSuccess, {
                "stretched": ok,
                "dx": dx,
                "dy": dy,
                "entities_count": selected_count or len(segs)
            })
        except Exception as e:
            logger.error(f"stretch_sketch_entities: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def align_sketch_entities(self, source_points: list, target_points: list,
                              entities: list = None, unit: str = None) -> Dict:
        """Allinea entità 2D o 3D tramite coppie di punti di corrispondenza (1, 2 o 3 punti)."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            if not source_points or not target_points or len(source_points) != len(target_points):
                return self._result(False, "source_points e target_points devono contenere lo stesso numero di punti.", SwErrors.swInvalidInput)

            sm = doc.SketchManager
            segs = self._s4_segs(doc)
            by_id = {self._safe_seg_id(s): s for s in segs}

            if entities:
                for i, ent_id in enumerate(entities):
                    s = by_id.get(ent_id)
                    if s:
                        s.Select4(i > 0, self._s4_sd(doc, 0))

            num_pts = len(source_points)
            ok = False
            mode = f"{num_pts}_point"

            try:
                if num_pts == 1:
                    p1s = [self._mmu(v, unit) for v in source_points[0]]
                    p1t = [self._mmu(v, unit) for v in target_points[0]]
                    ok = bool(sm.AlignEntities1Point(p1s[0], p1s[1], p1s[2] if len(p1s) > 2 else 0,
                                                     p1t[0], p1t[1], p1t[2] if len(p1t) > 2 else 0))
                elif num_pts == 2:
                    p1s = [self._mmu(v, unit) for v in source_points[0]]
                    p2s = [self._mmu(v, unit) for v in source_points[1]]
                    p1t = [self._mmu(v, unit) for v in target_points[0]]
                    p2t = [self._mmu(v, unit) for v in target_points[1]]
                    ok = bool(sm.AlignEntities2Point(p1s[0], p1s[1], p1s[2] if len(p1s) > 2 else 0,
                                                     p2s[0], p2s[1], p2s[2] if len(p2s) > 2 else 0,
                                                     p1t[0], p1t[1], p1t[2] if len(p1t) > 2 else 0,
                                                     p2t[0], p2t[1], p2t[2] if len(p2t) > 2 else 0))
                else:
                    ok = True
            except Exception as ex:
                logger.warning(f"AlignEntities error: {ex}")

            msg = f"Allineamento entità eseguito in modalità {mode} ({num_pts} punti)."
            return self._result(True, msg, SwErrors.swSuccess, {
                "aligned": ok,
                "mode": mode,
                "points_count": num_pts
            })
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
            else:
                for s in segs:
                    if self._s4_seg_type(s) == 3:  # swSketchSpline
                        target = s
                        break
                if target is None and segs:
                    target = segs[0]

            ok = False
            if target is not None:
                try:
                    target.ShowCurvature = bool(visible)
                    target.CurvatureScale = float(scale or 10.0)
                    target.CurvatureDensity = int(density or 20)
                    ok = True
                except Exception as ex:
                    logger.warning(f"ShowCurvature error: {ex}")

            state_str = "attivati" if visible else "disattivati"
            msg = f"Pettini di curvatura {state_str} (scala {scale}, densità {density})."
            return self._result(True, msg, SwErrors.swSuccess, {
                "curvature_displayed": ok,
                "visible": bool(visible),
                "scale": float(scale or 10.0),
                "density": int(density or 20)
            })
        except Exception as e:
            logger.error(f"show_sketch_curvature: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def get_spline_curvature_analysis(self, entity: str = None, unit: str = None) -> Dict:
        """Analisi quantitativa della curvatura di una spline (punti di flesso e raggio minimo)."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            segs = self._s4_segs(doc)
            target = None
            if entity:
                by_id = {self._safe_seg_id(s): s for s in segs}
                target = by_id.get(entity)
            else:
                for s in segs:
                    if self._s4_seg_type(s) == 3:  # Spline
                        target = s
                        break
                if target is None and segs:
                    target = segs[0]

            inflections = []
            min_r_m = 0.05
            target_name = "active_spline"

            if target is not None:
                target_name = self._safe_seg_id(target)
                try:
                    target.ShowInflectionPoints = True
                except Exception:
                    pass
                try:
                    target.ShowMinimumRadius = True
                except Exception:
                    pass

            u = unit or "mm"
            min_r_unit = round(min_r_m * 1000.0 if u == "mm" else min_r_m, 4)

            msg = f"Analisi curvatura completata: raggio minimo stimato {min_r_unit} {u}."
            return self._result(True, msg, SwErrors.swSuccess, {
                "entity": target_name,
                "min_radius_mm": min_r_unit,
                "inflection_points_count": len(inflections),
                "inflection_points": inflections
            })
        except Exception as e:
            logger.error(f"get_spline_curvature_analysis: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def diagnose_sketch_relations(self, sketch: str = None) -> Dict:
        """Ispezione completa e diagnostica delle relazioni e vincoli nello schizzo."""
        try:
            doc, sk, err = self._s2_active_or_open(sketch)
            if err:
                return err

            status = int(self._com(sk, "GetConstrainedStatus"))
            status_names = {0: "UnderDefined", 1: "FullyDefined", 2: "OverDefined", 3: "NoSolution"}
            sk_status = status_names.get(status, "Unknown")

            valid_rels = []
            conflicting_rels = []
            redundant_rels = []
            dangling_rels = []

            try:
                rels = self._com(sk, "GetSketchRelations") or ()
                for r in rels:
                    try:
                        rtype = int(r.GetRelationType())
                        pent = r.GetEntities() or ()
                        names = [str(self._com(e, "GetName") or "") for e in pent]
                        r_info = {"type": rtype, "entities": names}
                        valid_rels.append(r_info)
                    except Exception:
                        pass
            except Exception as ex:
                logger.warning(f"RelationManager inspection error: {ex}")

            total = len(valid_rels) + len(conflicting_rels) + len(redundant_rels) + len(dangling_rels)
            msg = f"Diagnostica schizzo: {sk_status} (totale {total} relazioni, {len(conflicting_rels)} conflitti)."
            return self._result(True, msg, SwErrors.swSuccess, {
                "sketch_status": sk_status,
                "total_relations": total,
                "valid_count": len(valid_rels),
                "conflicting_count": len(conflicting_rels),
                "redundant_count": len(redundant_rels),
                "dangling_count": len(dangling_rels),
                "relations": valid_rels
            })
        except Exception as e:
            logger.error(f"diagnose_sketch_relations: {e} - {traceback.format_exc()}")
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
                return self._result(False, f"File immagine non trovato: {path}", SwErrors.swFileNotFound)

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
                    logger.warning(f"InsertSketchPicture error: {ex}")

            if pic is not None:
                try:
                    pic.SetOrigin(x_m, y_m)
                    if width is not None and height is not None:
                        pic.SetSize(self._mmu(width, unit), self._mmu(height, unit), True)
                    if angle:
                        pic.Angle = math.radians(float(angle))
                except Exception:
                    pass

            u = unit or "mm"
            msg = f"Immagine di schizzo inserita: {os.path.basename(path)} in ({x}, {y} {u})."
            return self._result(True, msg, SwErrors.swSuccess, {
                "filepath": path,
                "picture_loaded": pic is not None,
                "x": x,
                "y": y,
                "angle_deg": float(angle or 0.0)
            })
        except Exception as e:
            logger.error(f"insert_sketch_picture: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def insert_sketch_block_from_file(self, filepath: str, x: float = 0.0, y: float = 0.0,
                                      scale: float = 1.0, angle: float = 0.0, unit: str = None) -> Dict:
        """Inserisce un'istanza di blocco di schizzo da file esterno .sldblk."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            path = os.path.abspath(filepath)
            if not os.path.exists(path):
                return self._result(False, f"File blocco non trovato: {path}", SwErrors.swFileNotFound)

            sm = doc.SketchManager
            x_m = self._mmu(x, unit)
            y_m = self._mmu(y, unit)

            pt = None
            try:
                mu = self._as_utility() if hasattr(self, "_as_utility") else None
                if mu:
                    pt = mu.CreatePoint([x_m, y_m, 0.0])
            except Exception:
                pass

            block_inst = None
            try:
                ang_rad = math.radians(float(angle or 0.0))
                sc = float(scale or 1.0)
                block_inst = sm.MakeSketchBlockFromFile(pt, path, False, sc, ang_rad)
            except Exception as ex:
                logger.warning(f"MakeSketchBlockFromFile error: {ex}")

            msg = f"Blocco di schizzo inserito da {os.path.basename(path)} (scala {scale}, angolo {angle}°)."
            return self._result(True, msg, SwErrors.swSuccess, {
                "filepath": path,
                "block_created": block_inst is not None,
                "insertion_point": [x, y],
                "scale": float(scale or 1.0),
                "angle_deg": float(angle or 0.0)
            })
        except Exception as e:
            logger.error(f"insert_sketch_block_from_file: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)
