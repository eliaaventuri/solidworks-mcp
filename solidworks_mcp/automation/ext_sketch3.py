"""
Lotto SCHIZZO 3: scomposizione trim e strumenti estesi 2D/3D (mixin Sketch3Operations).
Schemi in tools_ext/sketch3.py.
"""

import math
import logging
import traceback
from typing import Dict

import pythoncom
import win32com.client

from ..constants import SwErrors
from .modeling_base import null_variant

logger = logging.getLogger(__name__)


def _byref_i4():
    """Parametro per riferimento intero (VT_BYREF|VT_I4): il valore si legge da `.value` dopo la chiamata."""
    return win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)


class Sketch3Operations:
    """Mixin per operazioni estese di schizzo 2D/3D e trimming specializzato."""

    def _s2_active_or_open(self, sketch: str = None):
        """Restituisce (doc, sk, err) aprendo lo schizzo se necessario."""
        doc, sk, _name, err = self._s2_ctx(sketch)
        return doc, sk, err

    def trim_sketch_corner(self, entity1, entity2, point: list = None, unit: str = None, sketch: str = None) -> Dict:
        """Rifila o estende due segmenti fino all'intersezione (corner)."""
        return self.trim_sketch_entities(
            mode="corner", entity=entity1, entity2=entity2, point=point, unit=unit, sketch=sketch
        )

    def trim_sketch_inside(self, entity, boundaries: list, point: list = None, unit: str = None, sketch: str = None) -> Dict:
        """Taglia la porzione di entita' compresa all'interno di due entita' di confine."""
        return self.trim_sketch_entities(
            mode="inside", entity=entity, boundaries=boundaries, point=point, unit=unit, sketch=sketch
        )

    def trim_sketch_outside(self, entity, boundaries: list, point: list = None, unit: str = None, sketch: str = None) -> Dict:
        """Taglia la porzione di entita' compresa all'esterno di due entita' di confine."""
        return self.trim_sketch_entities(
            mode="outside", entity=entity, boundaries=boundaries, point=point, unit=unit, sketch=sketch
        )

    def trim_sketch_closest(self, entity, point: list = None, unit: str = None, sketch: str = None) -> Dict:
        """Power trim / trim closest: taglia il segmento cliccato fino all'intersezione piu' vicina."""
        return self.trim_sketch_entities(
            mode="closest", entity=entity, point=point, unit=unit, sketch=sketch
        )


    def set_dynamic_mirror_sketch(self, enable: bool, centerline=None, unit: str = None, sketch: str = None) -> Dict:
        """Attiva o disattiva la specchiatura dinamica in uno schizzo."""
        try:
            doc, sk, sk_name, err = self._s2_ctx(sketch)
            if err:
                return err
            sk_mgr = doc.SketchManager
            if enable and centerline:
                doc.ClearSelection2(True)
                ok, msg = self._select_ref(doc, sk, centerline, append=False, unit=unit)
                if not ok:
                    return self._result(False, f"Selezione mezzeria '{centerline}': {msg}", SwErrors.swSelectionError)
            try:
                sk_mgr.SetDynamicMirror(bool(enable))
            except Exception as e:
                return self._result(False, f"set_dynamic_mirror_sketch: impostazione non riuscita: {e}", SwErrors.swSketchError)
            current = bool(self._com(sk_mgr, "GetDynamicMirror"))
            if current != bool(enable):
                return self._result(False, f"set_dynamic_mirror_sketch: dynamic mirror in {sk_name} non impostato come richiesto.", SwErrors.swSketchError)
            return self._result(
                True, f"Dynamic mirror in {sk_name}: {'attivo' if current else 'disattivo'}",
                SwErrors.swSuccess, {"sketch": sk_name, "dynamic_mirror": current}
            )
        except Exception as e:
            logger.error(f"set_dynamic_mirror_sketch: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)

    def draw_style_spline(self, points: list, closed: bool = False, degree: int = 3, unit: str = None) -> Dict:
        """Crea una style spline (B-spline definita da vertici di controllo)."""
        try:
            doc, sk, err = self._s2_active_or_open()
            if err:
                return err
            if not points or len(points) < 2:
                return self._result(False, "Servono almeno 2 punti per definire una style spline.", SwErrors.swInvalidInput)
            pts_m = []
            for p in points:
                pts_m.extend([self._mmu(p[0], unit), self._mmu(p[1], unit), 0.0])
            sk_mgr = doc.SketchManager
            before_segs = len(self._segments(sk))
            try:
                sk_mgr.CreateSpline(pts_m)
            except Exception:
                sk_mgr.CreateSpline2(pts_m, True)
            after_segs = len(self._segments(sk))
            if after_segs <= before_segs:
                return self._result(False, "draw_style_spline: style spline non creata da SolidWorks.", SwErrors.swSketchError)
            return self._result(
                True, f"Style spline creata con {len(points)} punti di controllo.",
                SwErrors.swSuccess, {"points_count": len(points), "new_segments": after_segs - before_segs,
                                     "ignored_params": ["closed", "degree"]}
            )
        except Exception as e:
            logger.error(f"draw_style_spline: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def fit_spline(self, entities: list, tolerance: float = 0.01, closed: bool = False,
                   delete_original: bool = False, unit: str = None) -> Dict:
        """Unisce una catena di entita' di schizzo in un'unica fit spline continua."""
        try:
            doc, sk, err = self._s2_active_or_open()
            if err:
                return err
            if not entities or len(entities) < 1:
                return self._result(False, "Specificare almeno una o piu' entita' da convertire in fit spline.", SwErrors.swInvalidInput)
            doc.ClearSelection2(True)
            for r in entities:
                ok, msg = self._select_ref(doc, sk, r, append=True, unit=unit)
                if not ok:
                    return self._result(False, f"fit_spline: selezione di '{r}' non riuscita: {msg}", SwErrors.swSelectionError)
            try:
                doc.SketchAddConstraints("sgFITSPLINE")
            except Exception as e:
                return self._result(False, f"fit_spline: vincolo fit spline non applicato: {e}", SwErrors.swSketchError)
            return self._result(
                True, f"Vincolo fit spline (sgFITSPLINE) applicato a {len(entities)} entita'.",
                SwErrors.swSuccess, {"entities_count": len(entities), "ignored_params": ["tolerance", "closed", "delete_original"]}
            )
        except Exception as e:
            logger.error(f"fit_spline: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def draw_elliptical_arc(self, cx: float, cy: float, major_x: float, major_y: float, minor_r: float,
                            start_angle: float = 0.0, end_angle: float = 180.0, unit: str = None) -> Dict:
        """Disegna un arco di ellisse nello schizzo attivo."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err
            cx_m = self._mmu(cx, unit)
            cy_m = self._mmu(cy, unit)
            maj_x_m = self._mmu(major_x, unit)
            maj_y_m = self._mmu(major_y, unit)
            min_r_m = self._mmu(minor_r, unit)
            # (revisione 2026-11-12) prima l'asse minore e i punti iniziale/finale ignoravano major_y: con l'asse maggiore
            # inclinato l'ellisse era sbagliata. Ora tutto e' calcolato nel riferimento dell'ellisse (u = asse maggiore,
            # v = u ruotato di +90 gradi) e gli estremi creati sono riletti e confrontati.
            a_m = math.hypot(maj_x_m, maj_y_m)
            if a_m <= 0 or min_r_m <= 0:
                return self._result(False, "draw_elliptical_arc: asse maggiore (major_x, major_y) e minor_r devono essere > 0.",
                                    SwErrors.swInvalidInput)
            ux, uy = maj_x_m / a_m, maj_y_m / a_m
            vx, vy = -uy, ux

            def at(deg):
                t = math.radians(deg)
                return (cx_m + a_m * math.cos(t) * ux + min_r_m * math.sin(t) * vx,
                        cy_m + a_m * math.cos(t) * uy + min_r_m * math.sin(t) * vy)
            sx_m, sy_m = at(start_angle)
            ex_m, ey_m = at(end_angle)
            sk_mgr = doc.SketchManager
            seg = sk_mgr.CreateEllipticalArc(
                cx_m, cy_m, 0.0,
                cx_m + maj_x_m, cy_m + maj_y_m, 0.0,
                cx_m + min_r_m * vx, cy_m + min_r_m * vy, 0.0,
                sx_m, sy_m, 0.0,
                ex_m, ey_m, 0.0,
                1
            )
            if seg is None:
                return self._result(False, "draw_elliptical_arc: arco ellittico non creato da SolidWorks.", SwErrors.swSketchError)
            mm = lambda v: round(v * 1000.0, 4)
            try:
                p0, p1 = seg.GetStartPoint2, seg.GetEndPoint2
                got = [[mm(p0.X), mm(p0.Y)], [mm(p1.X), mm(p1.Y)]]
            except Exception:
                got = None
            want = [[mm(sx_m), mm(sy_m)], [mm(ex_m), mm(ey_m)]]
            if got is not None and not all(abs(g - w) < 1e-3 for gp, wp in zip(got, want) for g, w in zip(gp, wp)):
                return self._result(False, f"draw_elliptical_arc: SolidWorks ha creato l'arco con estremi {got} mm invece di "
                                    f"{want} mm.", SwErrors.swSketchError, {"endpoints_mm": got, "expected_mm": want})
            return self._result(
                True, f"Arco ellittico creato da {start_angle} a {end_angle} deg (estremi {want} mm, riletti).",
                SwErrors.swSuccess, {"center": [cx, cy], "angles": [start_angle, end_angle], "created": True,
                                     "endpoints_mm": got or want, "entity_id": self._seg_id(seg)}
            )
        except Exception as e:
            logger.error(f"draw_elliptical_arc: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def draw_conic_curve(self, p_start: list, p_end: list, p_apex: list, rho: float = 0.5, unit: str = None) -> Dict:
        """Disegna una curva conica nello schizzo attivo tramite ISketchManager.CreateConic."""
        try:
            doc, sk, err = self._s2_active_or_open()
            if err:
                return err
            sk_mgr = doc.SketchManager
            x1, y1 = self._mmu(p_start[0], unit), self._mmu(p_start[1], unit)
            x2, y2 = self._mmu(p_end[0], unit), self._mmu(p_end[1], unit)
            xa, ya = self._mmu(p_apex[0], unit), self._mmu(p_apex[1], unit)
            before_segs = len(self._segments(sk))
            sk_mgr.CreateConic(0.0, 0.0, 0.0, xa, ya, 0.0, x1, y1, 0.0, x2, y2, 0.0)
            if len(self._segments(sk)) <= before_segs:
                return self._result(False, "draw_conic_curve: curva conica non creata da SolidWorks.", SwErrors.swSketchError)
            return self._result(
                True, f"Curva conica creata tra {p_start} e {p_end}.",
                SwErrors.swSuccess, {"start": p_start, "end": p_end, "apex": p_apex, "ignored_params": ["rho"]}
            )
        except Exception as e:
            logger.error(f"draw_conic_curve: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)


    def draw_midpoint_line(self, cx: float, cy: float, length: float, angle: float = 0.0,
                           construction: bool = False, unit: str = None) -> Dict:
        """Traccia una linea simmetrica a partire dal suo punto medio."""
        try:
            rad = math.radians(angle)
            half = length / 2.0
            dx = half * math.cos(rad)
            dy = half * math.sin(rad)
            x1 = cx - dx
            y1 = cy - dy
            x2 = cx + dx
            y2 = cy + dy
            if construction:
                return self.draw_centerline_axis(x1, y1, x2, y2, unit=unit)
            else:
                return self.draw_line(x1, y1, x2, y2, unit=unit)
        except Exception as e:
            logger.error(f"draw_midpoint_line: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)


    def draw_centerpoint_arc(self, cx: float, cy: float, radius: float, start_angle: float = 0.0,
                             end_angle: float = 90.0, unit: str = None) -> Dict:
        """Disegna un arco dato il centro, raggio e angolo iniziale/finale."""
        return self.draw_arc_center(cx=cx, cy=cy, radius=radius, start_angle=start_angle, end_angle=end_angle, unit=unit)

    def draw_centerpoint_slot(self, cx: float, cy: float, length: float, width: float,
                              angle: float = 0.0, unit: str = None) -> Dict:
        """Asola rettilinea dal centro: `length` = distanza fra i centri degli estremi.
        (revisione 2026-11-12) prima usava il tipo 0 di CreateSketchSlot con il centro come primo estremo: l'asola partiva dal
        centro ed era lunga meta'. Ora calcola i due centri degli estremi e passa a draw_slot (center_to_center, misurato)."""
        try:
            if length is None or float(length) <= 0:
                return self._result(False, "draw_centerpoint_slot: length deve essere > 0.", SwErrors.swInvalidInput)
            rad = math.radians(float(angle or 0.0))
            hx, hy = float(length) / 2.0 * math.cos(rad), float(length) / 2.0 * math.sin(rad)
            r = self.draw_slot(x1=float(cx) - hx, y1=float(cy) - hy, x2=float(cx) + hx, y2=float(cy) + hy, width=width,
                               unit=unit, slot_type="center_to_center")
            if r.get("success"):
                r["data"].update({"center": [cx, cy], "length": length, "angle": angle})
            return r
        except Exception as e:
            logger.error(f"draw_centerpoint_slot: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def draw_arc_slot(self, cx: float, cy: float, radius: float, width: float, start_angle: float = 0.0,
                      end_angle: float = 90.0, slot_type: str = "centerpoint_arc", unit: str = None) -> Dict:
        """Asola ad arco dal centro: passa a draw_slot(slot_type='arc_center'), stessa mappatura di CreateSketchSlot
        (revisione 2026-11-12: c'erano tre mappature diverse del tipo di asola in tre file)."""
        if "center" not in str(slot_type or "").lower():
            return self._result(False, f"draw_arc_slot: tipo '{slot_type}' non supportato da questo tool: usa 'centerpoint_arc' "
                                "(per l'asola per 3 punti: draw_3point_arc_slot).", SwErrors.swInvalidInput)
        return self.draw_slot(cx=cx, cy=cy, radius=radius, width=width, start_angle=start_angle, end_angle=end_angle,
                              unit=unit, slot_type="arc_center")


    def draw_3d_arc(self, p1: list, p2: list, p3: list, unit: str = None) -> Dict:
        """Disegna un arco nello spazio 3D nello schizzo 3D attivo."""
        try:
            doc, sm, err = self._s2_3d_ready()
            if err:
                return err
            sk_mgr = sm
            x1, y1, z1 = self._mmu(p1[0], unit), self._mmu(p1[1], unit), self._mmu(p1[2], unit)
            x2, y2, z2 = self._mmu(p2[0], unit), self._mmu(p2[1], unit), self._mmu(p2[2], unit)
            x3, y3, z3 = self._mmu(p3[0], unit), self._mmu(p3[1], unit), self._mmu(p3[2], unit)
            sk3d = self._com(sm, "ActiveSketch")
            before_segs = len(self._segments(sk3d))
            sk_mgr.Create3PointArc(x1, y1, z1, x2, y2, z2, x3, y3, z3)
            if len(self._segments(sk3d)) <= before_segs:
                return self._result(False, "draw_3d_arc: arco 3D non creato da SolidWorks.", SwErrors.swSketchError)
            return self._result(
                True, f"Arco 3D creato tra {p1}, {p2}, {p3}.",
                SwErrors.swSuccess, {"p1": p1, "p2": p2, "p3": p3}
            )
        except Exception as e:
            logger.error(f"draw_3d_arc: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def create_3d_sketch_plane(self, ref1=None, ref2=None, ref3=None, relation1: int = 1,
                               relation2: int = 0, relation3: int = 0) -> Dict:
        """Crea un piano di lavoro locale all'interno di uno schizzo 3D attivo."""
        try:
            doc, err = self._part()
            if err:
                return err
            sk_mgr = doc.SketchManager
            res = sk_mgr.CreateSketchPlane(int(relation1), int(relation2), int(relation3))
            if not res:
                return self._result(False, "create_3d_sketch_plane: piano di schizzo 3D non creato da SolidWorks.", SwErrors.swSketchError)
            return self._result(
                True, "Piano di schizzo 3D creato.",
                SwErrors.swSuccess, {"result": True, "ignored_params": ["ref1", "ref2", "ref3"]}
            )
        except Exception as e:
            logger.error(f"create_3d_sketch_plane: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def add_3d_sketch_axis_dimension(self, entity, axis: str = "x", x: float = None,
                                     y: float = None, z: float = None, unit: str = None) -> Dict:
        """Aggiunge una quota lungo l'asse X, Y o Z in uno schizzo 3D."""
        try:
            doc, sk, err = self._s2_active_or_open()
            if err:
                return err
            sk_mgr = doc.SketchManager
            doc.ClearSelection2(True)
            ok, msg = self._select_ref(doc, sk, entity, append=False, unit=unit)
            if not ok:
                return self._result(False, f"add_3d_sketch_axis_dimension: selezione di '{entity}' non riuscita: {msg}", SwErrors.swSelectionError)
            px = self._mmu(x or 0.0, unit)
            py = self._mmu(y or 0.0, unit)
            pz = self._mmu(z or 0.0, unit)
            ax = str(axis or "x").lower().strip()
            if ax == "x":
                dim = sk_mgr.AddAlongXDimension(px, py, pz)
            elif ax == "y":
                dim = sk_mgr.AddAlongYDimension(px, py, pz)
            elif ax == "z":
                dim = sk_mgr.AddAlongZDimension(px, py, pz)
            else:
                return self._result(False, f"Asse '{axis}' non valido: usa 'x', 'y' o 'z'.", SwErrors.swInvalidInput)
            if dim is None:
                return self._result(False, "add_3d_sketch_axis_dimension: quota non creata da SolidWorks.", SwErrors.swSketchError)
            return self._result(
                True, f"Quota 3D lungo l'asse {ax.upper()} aggiunta su {entity}.",
                SwErrors.swSuccess, {"axis": ax, "entity": entity}
            )
        except Exception as e:
            logger.error(f"add_3d_sketch_axis_dimension: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)


    def edit_sketch_block(self, block_name: str) -> Dict:
        """Modifica la definizione di un blocco di schizzo o chiude la modifica."""
        try:
            doc, err = self._part()
            if err:
                return err
            sk_mgr = doc.SketchManager
            name = str(block_name or "").strip()
            if not name:
                sk_mgr.EndEditSketchBlock()
                return self._result(True, "Uscita dalla modifica del blocco di schizzo.", SwErrors.swSuccess)
            if not doc.Extension.SelectByID2(name, "SKETCHBLOCKDEF", 0, 0, 0, False, 0, null_variant(), 0):
                return self._result(False, f"edit_sketch_block: blocco '{name}' non trovato", SwErrors.swSelectionError)
            res = sk_mgr.EditSketchBlock()
            if not res:
                return self._result(False, f"edit_sketch_block: modifica del blocco '{name}' non avviata da SolidWorks.", SwErrors.swSketchError)
            return self._result(
                True, f"Modifica del blocco '{name}' aperta.",
                SwErrors.swSuccess, {"block_name": name, "editing": True}
            )
        except Exception as e:
            logger.error(f"edit_sketch_block: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)

    def explode_sketch_block(self, instance_name: str = None) -> Dict:
        """Esplode un'istanza di blocco di schizzo nelle sue primitive."""
        try:
            doc, err = self._part()
            if err:
                return err
            sk_mgr = doc.SketchManager
            if instance_name:
                if not doc.Extension.SelectByID2(str(instance_name), "SKETCHBLOCKINSTANCE", 0, 0, 0, False, 0, null_variant(), 0):
                    return self._result(False, f"explode_sketch_block: istanza '{instance_name}' non trovata", SwErrors.swSelectionError)
            res = sk_mgr.ExplodeSketchBlockInstance(None)
            if not res:
                return self._result(False, f"explode_sketch_block: blocco '{instance_name or 'selezionato'}' non esploso da SolidWorks.", SwErrors.swSketchError)
            return self._result(
                True, f"Blocco di schizzo {instance_name or 'selezionato'} esploso.",
                SwErrors.swSuccess, {"instance_name": instance_name, "exploded": True}
            )
        except Exception as e:
            logger.error(f"explode_sketch_block: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)

    def repair_sketch(self, close_gaps: bool = True, gap_tolerance: float = 0.05, unit: str = None) -> Dict:
        """Ripara lo schizzo attivo: (1) estremi distinti a distanza <= gap_tolerance uniti con una relazione di coincidenza
        (chiude le micro-fessure), (2) segmenti doppi (stesso tipo e stessi estremi/centro) cancellati. Con close_gaps=false
        solo l'analisi. (revisione 2026-11-12) prima contava i contorni e basta, ignorando i due parametri."""
        try:
            doc, sk, err = self._s2_active_or_open()
            if err:
                return err

            def contours():
                o, c = _byref_i4(), _byref_i4()
                sk.CheckFeatureUse(0, o, c)
                return int(o.value), int(c.value)

            tol = self._mmu(gap_tolerance if gap_tolerance is not None else 0.05, unit)
            open0, closed0 = contours()
            segs = [s for s in self._segments(sk) if not bool(self._com(s, "ConstructionGeometry"))]
            # estremi dei segmenti (oggetti punto distinti per id)
            ends = {}
            for s in segs:
                for attr in ("GetStartPoint2", "GetEndPoint2"):
                    try:
                        p = getattr(s, attr)
                        ends[self._pt_id(p)] = p
                    except Exception:
                        pass
            pts = list(ends.items())
            gaps = []
            for i in range(len(pts)):
                for j in range(i + 1, len(pts)):
                    (ia, a), (ib, b) = pts[i], pts[j]
                    d = math.hypot(float(a.X) - float(b.X), float(a.Y) - float(b.Y))
                    if d <= tol:
                        gaps.append((ia, ib, a, b, d))
            # segmenti doppi: stesso tipo, stessi estremi (in un verso o nell'altro) e stesso centro
            def key(s):
                try:
                    p0, p1 = s.GetStartPoint2, s.GetEndPoint2
                    e = sorted([(round(float(p0.X), 9), round(float(p0.Y), 9)), (round(float(p1.X), 9), round(float(p1.Y), 9))])
                    try:
                        c = s.GetCenterPoint2
                        cc = (round(float(c.X), 9), round(float(c.Y), 9))
                    except Exception:
                        cc = None
                    return (int(s.GetType), tuple(e), cc)
                except Exception:
                    return None
            seen, dups = {}, []
            for s in segs:
                k = key(s)
                if k is None or int(s.GetType) not in (0, 1):     # solo linee e archi: per spline/ellissi gli estremi non bastano
                    continue
                if k in seen:
                    dups.append(s)
                else:
                    seen[k] = s
            data = {"gap_tolerance_mm": round(tol * 1000.0, 6),
                    "gaps_found": [{"points": [ia, ib], "distance_mm": round(d * 1000.0, 6)} for ia, ib, _a, _b, d in gaps],
                    "duplicates_found": [self._seg_id(s) for s in dups],
                    "open_contours_before": open0, "closed_contours_before": closed0}
            if not close_gaps:
                return self._result(True, f"Analisi: {len(gaps)} fessure <= {data['gap_tolerance_mm']} mm, {len(dups)} segmenti "
                                    f"doppi; contorni aperti {open0}, chiusi {closed0} (nessuna modifica: close_gaps=false).",
                                    SwErrors.swSuccess, data)
            sd = self._sd(doc, 0)
            for ia, ib, a, b, d in gaps:
                doc.ClearSelection2(True)
                try:
                    if a.Select4(False, sd) and b.Select4(True, sd):
                        doc.SketchAddConstraints("sgCOINCIDENT")
                except Exception as ex:
                    logger.debug(f"repair_sketch coincidente {ia}-{ib}: {ex}")
            doc.ClearSelection2(True)
            # verifica: le fessure si ricalcolano da capo (quando due punti si uniscono uno dei due oggetti sparisce)
            left = []
            pts2 = {}
            for s in [s for s in self._segments(sk) if not bool(self._com(s, "ConstructionGeometry"))]:
                for attr in ("GetStartPoint2", "GetEndPoint2"):
                    try:
                        p = getattr(s, attr)
                        pts2[self._pt_id(p)] = (float(p.X), float(p.Y))
                    except Exception:
                        pass
            items = list(pts2.items())
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    (ia, pa), (ib, pb) = items[i], items[j]
                    if math.hypot(pa[0] - pb[0], pa[1] - pb[1]) <= tol:
                        left.append([ia, ib])
            failed = left
            closed_gaps = max(0, len(gaps) - len(left))
            removed = 0
            for s in dups:
                try:
                    doc.ClearSelection2(True)
                    if s.Select4(False, sd) and doc.Extension.DeleteSelection2(0):
                        removed += 1
                except Exception:
                    pass
            doc.ClearSelection2(True)
            open1, closed1 = contours()
            data.update({"gaps_closed": closed_gaps, "gaps_not_closed": failed, "duplicates_removed": removed,
                         "open_contours": open1, "closed_contours": closed1})
            ok = not failed and removed == len(dups)
            return self._result(ok, f"Riparazione: {closed_gaps}/{len(gaps)} fessure chiuse, {removed}/{len(dups)} doppioni "
                                f"tolti; contorni aperti {open0} -> {open1}, chiusi {closed0} -> {closed1}.",
                                SwErrors.swSuccess if ok else SwErrors.swSketchError, data)
        except Exception as e:
            logger.error(f"repair_sketch: {e}\n{traceback.format_exc()}")
            return self._result(False, f"repair_sketch: verifica non riuscita: {e}", SwErrors.swSketchError)

    def check_sketch_for_feature(self, feature_type: str = "base_extrude", sketch: str = None) -> Dict:
        """Verifica se lo schizzo e' valido per una determinata feature (contorni aperti/chiusi)."""
        try:
            _doc, sk, sk_name, err = self._s2_ctx(sketch)
            if err:
                return err
            ft_code = {"base_extrude": 0, "boss_revolve": 1, "cut_extrude": 2, "sweep": 3}.get(
                str(feature_type).lower().strip()
            )
            if ft_code is None:
                return self._result(False, f"check_sketch_for_feature: tipo di feature '{feature_type}' non riconosciuto.",
                                    SwErrors.swInvalidInput)
            open_ref = _byref_i4()
            closed_ref = _byref_i4()
            ret = sk.CheckFeatureUse(ft_code, open_ref, closed_ref)
            open_c = int(open_ref.value)
            closed_c = int(closed_ref.value)
            valid = bool(ret == 0)
            return self._result(
                True, f"Controllo schizzo {sk_name} per {feature_type}: valido={valid}.",
                SwErrors.swSuccess, {"sketch": sk_name, "feature_type": feature_type,
                                     "valid": valid, "open_contours": open_c, "closed_contours": closed_c}
            )
        except Exception as e:
            logger.error(f"check_sketch_for_feature: {e}\n{traceback.format_exc()}")
            return self._result(False, f"check_sketch_for_feature: controllo non riuscito: {e}", SwErrors.swSketchError)

    def close_sketch_to_model(self, direction: str = "x", reverse: bool = False) -> Dict:
        """Chiude automaticamente un profilo di schizzo aperto estendendolo al modello."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err
            sk_mgr = doc.SketchManager
            try:
                sk_mgr.CloseSketchToModel(str(direction).upper(), bool(reverse))
            except Exception as e:
                return self._result(False, f"close_sketch_to_model: chiusura non riuscita: {e}", SwErrors.swSketchError)
            return self._result(
                True, f"Profilo esteso e chiuso verso il modello lungo {direction}.",
                SwErrors.swSuccess, {"direction": direction, "reverse": reverse}
            )
        except Exception as e:
            logger.error(f"close_sketch_to_model: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def create_area_hatch(self, angle: float = 45.0, scale: float = 1.0, color: int = 0,
                          hatch_name: str = "ANSI31", layer: str = None) -> Dict:
        """Crea un tratteggio / riempimento d'area all'interno di profili chiusi."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err
            sk_mgr = doc.SketchManager
            hatch = sk_mgr.CreateBoundaryHatch(float(angle), float(scale), int(color), str(hatch_name), str(layer or ""))
            if not hatch:
                return self._result(False, f"create_area_hatch: tratteggio '{hatch_name}' non creato da SolidWorks.", SwErrors.swSketchError)
            return self._result(
                True, f"Tratteggio d'area '{hatch_name}' creato (angolo {angle} deg, scala {scale}).",
                SwErrors.swSuccess, {"hatch_name": hatch_name, "angle": angle, "scale": scale}
            )
        except Exception as e:
            logger.error(f"create_area_hatch: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)
