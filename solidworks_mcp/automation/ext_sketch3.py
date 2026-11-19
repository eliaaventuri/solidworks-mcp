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
from .modeling_base import null_variant, r8_array

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


    def _mirror_probe(self, doc, x0, y0, nx, ny) -> bool:
        """True se la specchiatura dinamica e' attiva: una linea corta a 1 m (niente agganci) ne crea due; poi si toglie."""
        sm = doc.SketchManager
        segs0 = {self._seg_id(x) for x in self._s2_segs(doc)}
        cx, cy = x0 + nx * 1000.0, y0 + ny * 1000.0
        sm.CreateLine(cx / 1000, cy / 1000, 0.0, (cx + nx * 5) / 1000, (cy + ny * 5) / 1000, 0.0)
        new = [x for x in self._s2_segs(doc) if self._seg_id(x) not in segs0]
        self._s2_delete(doc, new)
        if any(self._seg_id(x) not in segs0 for x in self._s2_segs(doc)):
            raise RuntimeError("linea di prova non rimossa")
        return len(new) >= 2

    def set_dynamic_mirror_sketch(self, enable: bool, centerline=None, unit: str = None, sketch: str = None) -> Dict:
        """Attiva o disattiva la specchiatura dinamica attorno a una linea dello schizzo (da quel momento ogni entita'
        disegnata ha la copia speculare). Misurato 19/11: GetDynamicMirror restituisce SEMPRE False e SetDynamicMirror
        e' un INTERRUTTORE (True con la linea selezionata accende, True senza selezione spegne, False non fa nulla):
        lo stato si legge prima e dopo con una linea di prova (disegnata, contata, tolta)."""
        try:
            doc, sk, sk_name, err = self._s2_ctx(sketch)
            if err:
                return err
            sm = doc.SketchManager
            x0, y0, nx, ny = 137.0, -59.0, 0.6, 0.8      # prova "generica": non sta su un asse tipico (misurato: su x=0 la copia coincide)
            cl = None
            if enable:
                if not centerline:
                    return self._result(False, "Per attivarla serve la linea di simmetria (centerline: id o '@x,y').",
                                        SwErrors.swInvalidInput)
                cl, e = self._s2_resolve(doc, sk, centerline, unit)
                if e:
                    return self._result(False, f"Linea di simmetria '{centerline}': {e}", SwErrors.swSelectionError)
                g = self._s2_geo(cl)
                if g["kind"] != "L":
                    return self._result(False, "La linea di simmetria deve essere una linea.", SwErrors.swInvalidInput)
                (ax, ay, _), (bx, by, _) = g["s"], g["e"]
                L = math.hypot(bx - ax, by - ay) or 1.0
                x0, y0, nx, ny = (ax + bx) / 2, (ay + by) / 2, -(by - ay) / L, (bx - ax) / L
            before = self._mirror_probe(doc, x0, y0, nx, ny)
            if before != bool(enable):
                doc.ClearSelection2(True)
                if cl is not None:
                    cl.Select4(False, self._sd(doc, 0))
                sm.SetDynamicMirror(True)
                doc.ClearSelection2(True)
            after = self._mirror_probe(doc, x0, y0, nx, ny)
            data = {"sketch": sk_name, "dynamic_mirror": after, "was_active": before}
            if after != bool(enable):
                return self._result(False, f"Specchiatura dinamica non {'attivata' if enable else 'spenta'} "
                                    "(verificata con una linea di prova).", SwErrors.swSketchError, data)
            return self._result(True, f"Specchiatura dinamica in {sk_name}: {'attiva' if after else 'spenta'} "
                                "(verificata con una linea di prova, tolta)", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"set_dynamic_mirror_sketch: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)

    # ---- spline per punti con scarto misurato (style spline e fit spline: SolidWorks non ha API per crearle) ----
    def _spline_through(self, doc, sk, pts_mm, check_mm, closed):
        """Spline per i punti (mm dello schizzo) -> (segmento, scarto massimo mm dai punti di verifica)."""
        flat = []
        seq = list(pts_mm) + ([pts_mm[0]] if closed else [])
        for x, y in seq:
            flat += [x / 1000.0, y / 1000.0, 0.0]
        seg = doc.SketchManager.CreateSpline2(r8_array(flat), True)
        if seg is None:
            return None, None
        cv = self._com(seg, "GetCurve")      # la curva di un segmento di schizzo e' nello spazio dello SCHIZZO (misurato)
        dev = 0.0
        for x, y in check_mm:
            q = [x / 1000.0, y / 1000.0, 0.0]
            c = list(cv.GetClosestPointOn(q[0], q[1], q[2]))[:3]
            dev = max(dev, math.dist(q, c) * 1000.0)
        return seg, dev

    @staticmethod
    def _bspline_points(ctrl, degree, closed, n):
        """n punti (piu' n-1 punti di mezzo) di una B-spline uniforme (agganciata agli estremi se aperta)."""
        P = [tuple(c) for c in ctrl]
        p = degree
        if closed:
            P = P + P[:p]
            m = len(P)
            knots = list(range(m + p + 1))
            t0, t1 = knots[p], knots[m]
        else:
            m = len(P)
            inner = m - p - 1
            knots = [0.0] * (p + 1) + [i / (inner + 1) for i in range(1, inner + 1)] + [1.0] * (p + 1)
            t0, t1 = 0.0, 1.0

        def ev(t):
            k = p
            while k < m - 1 and t >= knots[k + 1]:
                k += 1
            d = [list(P[j + k - p]) for j in range(p + 1)]
            for r in range(1, p + 1):
                for j in range(p, r - 1, -1):
                    den = knots[j + 1 + k - r] - knots[j + k - p]
                    al = 0.0 if den == 0 else (t - knots[j + k - p]) / den
                    d[j] = [(1 - al) * d[j - 1][i] + al * d[j][i] for i in range(2)]
            return tuple(d[p])
        ts = [t0 + (t1 - t0) * i / (2 * n) for i in range(2 * n + 1)]
        allp = [ev(min(t, t1 - 1e-12) if closed else t) for t in ts]
        main, mids = allp[0::2], allp[1::2]
        if closed:
            main = main[:-1]
        dense = [ev(min(t0 + (t1 - t0) * i / 4000, t1 - 1e-12) if closed else t0 + (t1 - t0) * i / 4000)
                 for i in range(4001)]
        length = sum(math.dist(dense[i], dense[i + 1]) for i in range(4000))
        return main, mids, length

    def draw_style_spline(self, points: list, closed: bool = False, degree: int = 3, unit: str = None) -> Dict:
        """Curva B-spline (Bezier se i punti sono grado+1) definita da vertici di controllo. SolidWorks non ha un'API per la
        style spline: si crea una spline per punti che segue la B-spline entro 0,001 mm, con scarto misurato
        (ICurve.GetClosestPointOn) e lunghezza confrontata con quella calcolata."""
        try:
            doc, sk, err = self._s2_active_or_open()
            if err:
                return err
            if not points or len(points) < 2:
                return self._result(False, "Servono almeno 2 punti di controllo.", SwErrors.swInvalidInput)
            ctrl = [(float(self._from_m(self._mmu(p[0], unit), "mm")), float(self._from_m(self._mmu(p[1], unit), "mm")))
                    for p in points]
            deg = max(1, min(int(degree or 3), 5))
            note = ""
            if not closed and len(ctrl) < deg + 1:
                deg, note = len(ctrl) - 1, f" (grado ridotto a {len(ctrl) - 1}: servono grado+1 punti)"
            if closed and len(ctrl) < 3:
                return self._result(False, "Una curva chiusa richiede almeno 3 punti di controllo.", SwErrors.swInvalidInput)
            seg = dev = None
            for n in (16, 32, 64, 128):
                main, mids, length = self._bspline_points(ctrl, deg, bool(closed), max(n, 4 * len(ctrl)))
                seg, dev = self._spline_through(doc, sk, main, mids, bool(closed))
                if seg is None:
                    return self._result(False, "SolidWorks non ha creato la spline.", SwErrors.swSketchError)
                if dev <= 0.001:
                    break
                self._s2_delete(doc, [seg])
                seg = None
            if seg is None:
                return self._result(False, f"Scarto dalla curva {dev:.4f} mm anche con 128 punti: non creata.",
                                    SwErrors.swSketchError)
            got = float(seg.GetLength) * 1000.0
            data = {"entity_id": self._seg_id(seg), "control_points": len(ctrl), "degree": deg, "closed": bool(closed),
                    "through_points": len(main), "max_deviation_mm": round(dev, 6),
                    "length_mm": round(self._from_m(got / 1000.0, unit), 5),
                    "expected_length_mm": round(self._from_m(length / 1000.0, unit), 5),
                    "note": "spline per punti che segue la B-spline (la style spline di SolidWorks non ha API)"}
            if abs(got - length) > 1e-3 * max(1.0, length):
                self._s2_delete(doc, [seg])
                return self._result(False, f"Lunghezza {got:.4f} mm invece di {length:.4f} mm: spline tolta.",
                                    SwErrors.swSketchError, data)
            return self._result(True, f"Curva per {len(ctrl)} punti di controllo, grado {deg}{note}: lunghezza "
                                f"{got:.4f} mm, scarto {dev:.5f} mm", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"draw_style_spline: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def _chain_funcs(self, segs):
        """Catena ordinata di linee/archi -> lista di funzioni u in [0,1] -> (x, y) mm, orientate; errore se non e' una catena."""
        funcs = []
        for seg in segs:
            g = self._s2_geo(seg)
            if g["kind"] == "L":
                s, e = g["s"], g["e"]
                funcs.append([lambda u, s=s, e=e: (s[0] + u * (e[0] - s[0]), s[1] + u * (e[1] - s[1])), g["len"]])
            elif g["kind"] == "A":
                c, r = g["c"], g["r"]
                a0 = math.atan2(g["s"][1] - c[1], g["s"][0] - c[0])
                a1 = math.atan2(g["e"][1] - c[1], g["e"][0] - c[0])
                try:
                    ccw = int(self._com(seg, "GetRotationDir")) == 1
                except Exception:
                    ccw = True
                sw = (a1 - a0) % (2 * math.pi) if ccw else -((a0 - a1) % (2 * math.pi))
                funcs.append([lambda u, c=c, r=r, a0=a0, sw=sw: (c[0] + r * math.cos(a0 + u * sw),
                                                                  c[1] + r * math.sin(a0 + u * sw)), g["len"]])
            else:
                return None, f"{g['id']} non e' una linea ne' un arco"
        tol = 1e-3
        # orienta: il primo verso il secondo, poi ognuno parte dalla fine del precedente
        if len(funcs) > 1:
            f0, f1 = funcs[0][0], funcs[1][0]
            ends1 = (f1(0.0), f1(1.0))
            if min(math.dist(f0(0.0), q) for q in ends1) < min(math.dist(f0(1.0), q) for q in ends1) - tol:
                funcs[0][0] = (lambda f: lambda u: f(1.0 - u))(f0)
        for i in range(1, len(funcs)):
            prev_end = funcs[i - 1][0](1.0)
            f = funcs[i][0]
            if math.dist(f(0.0), prev_end) <= tol:
                continue
            if math.dist(f(1.0), prev_end) <= tol:
                funcs[i][0] = (lambda f: lambda u: f(1.0 - u))(f)
                continue
            return None, f"le entita' non sono collegate in catena (pezzo {i + 1})"
        return funcs, None

    def fit_spline(self, entities: list, tolerance: float = 0.01, closed: bool = False,
                   delete_original: bool = False, unit: str = None) -> Dict:
        """Una spline che segue una catena di linee e archi entro `tolerance` (scarto MISURATO con
        ICurve.GetClosestPointOn). Gli originali diventano costruzione (come Fit Spline) o si cancellano."""
        try:
            doc, sk, err = self._s2_active_or_open()
            if err:
                return err
            if not entities:
                return self._result(False, "Servono una o piu' entita' (linee/archi in catena).", SwErrors.swInvalidInput)
            segs = []
            for r in entities:
                seg, e = self._s2_resolve(doc, sk, r, unit)
                if e:
                    return self._result(False, f"fit_spline: {e}", SwErrors.swSelectionError)
                segs.append(seg)
            funcs, e = self._chain_funcs(segs)
            if e:
                return self._result(False, f"fit_spline: {e}", SwErrors.swSketchError)
            start, end = funcs[0][0](0.0), funcs[-1][0](1.0)
            if closed and math.dist(start, end) > 1e-3:
                return self._result(False, "closed=true ma la catena non e' chiusa.", SwErrors.swSketchError)
            tol_mm = self._from_m(self._mmu(float(tolerance or 0.01), unit), "mm")
            total = sum(L for _f, L in funcs)
            seg = dev = None
            for per_mm in (0.5, 1.0, 2.0, 4.0):        # punti al mm di catena
                main, mids = [], []
                for f, L in funcs:
                    k = max(2, int(math.ceil(L * per_mm)))
                    main += [f(i / k) for i in range(k)]
                    mids += [f((i + 0.5) / k) for i in range(k)]
                if not closed:
                    main.append(end)
                if len(main) > 800:
                    break
                seg, dev = self._spline_through(doc, sk, main, mids, bool(closed))
                if seg is None:
                    return self._result(False, "SolidWorks non ha creato la spline.", SwErrors.swSketchError)
                if dev <= tol_mm:
                    break
                self._s2_delete(doc, [seg])
                seg = None
            if seg is None:
                return self._result(False, f"Scarto {dev:.4f} mm oltre la tolleranza {tol_mm} mm (spigoli vivi nella "
                                    "catena?): spline non creata.", SwErrors.swSketchError, {"max_deviation_mm": dev})
            new_id = self._seg_id(seg)
            if delete_original:
                self._s2_delete(doc, segs)
            else:
                for s0 in segs:
                    try:
                        s0.ConstructionGeometry = True
                    except Exception:
                        pass
            left = [self._s2_geo(s0) for s0 in self._s2_segs(doc)]
            data = {"entity_id": new_id, "entities_count": len(segs), "through_points": len(main),
                    "max_deviation_mm": round(self._from_m(dev / 1000.0, unit), 6), "tolerance": tolerance,
                    "chain_length_mm": round(total, 5), "spline_length_mm": round(float(seg.GetLength) * 1000.0, 5),
                    "originals": "cancellati" if delete_original else "costruzione",
                    "original_segments_left": sum(1 for g in left if g["id"] in {self._seg_id(x) for x in segs}
                                                  and not g["construction"]) if not delete_original else None}
            return self._result(True, f"Spline per {len(main)} punti lungo {len(segs)} entita': scarto massimo "
                                f"{dev:.5f} mm (tolleranza {tol_mm} mm)", SwErrors.swSuccess, data)
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
        """Conica fra start ed end con le tangenti che si incontrano in p_apex e rapporto rho (0<rho<1: <0,5 ellisse,
        0,5 parabola, >0,5 iperbole). ISketchManager.CreateConic vuole (vertice, punto di spalla, inizio, fine): la spalla
        e' M + rho*(apex - M), M = punto medio di start-end (misurato: con questo ordine la lunghezza coincide con quella
        della quadratica razionale). La lunghezza si confronta con quella calcolata."""
        try:
            doc, sk, err = self._s2_active_or_open()
            if err:
                return err
            rho = float(rho if rho is not None else 0.5)
            if not 0.0 < rho < 1.0:
                return self._result(False, "rho deve stare fra 0 e 1 (esclusi).", SwErrors.swInvalidInput)
            A = (self._mmu(p_start[0], unit), self._mmu(p_start[1], unit))
            B = (self._mmu(p_end[0], unit), self._mmu(p_end[1], unit))
            T = (self._mmu(p_apex[0], unit), self._mmu(p_apex[1], unit))
            M = ((A[0] + B[0]) / 2, (A[1] + B[1]) / 2)
            S = (M[0] + rho * (T[0] - M[0]), M[1] + rho * (T[1] - M[1]))
            try:
                seg = doc.SketchManager.CreateConic(T[0], T[1], 0.0, S[0], S[1], 0.0, A[0], A[1], 0.0, B[0], B[1], 0.0)
            except Exception as ex:
                return self._result(False, f"SolidWorks rifiuta questa conica (rho {rho}: misurato che oltre ~0,9 "
                                    f"fallisce): {ex}", SwErrors.swSketchError)
            if seg is None:
                return self._result(False, "SolidWorks non ha creato la conica (punti allineati?).", SwErrors.swSketchError)
            w = rho / (1.0 - rho)

            def P(t):
                b0, b1, b2 = (1 - t) ** 2, 2 * t * (1 - t) * w, t * t
                d = b0 + b1 + b2
                return ((b0 * A[0] + b1 * T[0] + b2 * B[0]) / d, (b0 * A[1] + b1 * T[1] + b2 * B[1]) / d)
            calc, prev = 0.0, P(0.0)
            for i in range(1, 4001):
                q = P(i / 4000)
                calc += math.dist(q, prev)
                prev = q
            got = float(seg.GetLength)
            data = {"entity_id": self._seg_id(seg), "rho": rho,
                    "length": round(self._from_m(got, unit), 5), "expected_length": round(self._from_m(calc, unit), 5)}
            if abs(got - calc) > 1e-4 * calc:
                self._s2_delete(doc, [seg])
                return self._result(False, f"Conica di lunghezza {data['length']} invece di {data['expected_length']}: "
                                    "SolidWorks non l'ha costruita come chiesto (rho vicino a 1?), tolta.",
                                    SwErrors.swSketchError, data)
            return self._result(True, f"Conica rho {rho}: lunghezza {data['length']} (calcolata {data['expected_length']})",
                                SwErrors.swSuccess, data)
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
            before_ids = {self._seg_id(s0) for s0 in self._segments(sk3d)}
            # Create3PointArc(inizio, FINE, punto intermedio) (misurato 19/11): l'arco va da p1 a p3 passando per p2
            sk_mgr.Create3PointArc(x1, y1, z1, x3, y3, z3, x2, y2, z2)
            new = [s0 for s0 in self._segments(sk3d) if self._seg_id(s0) not in before_ids]
            if not new:
                return self._result(False, "draw_3d_arc: arco 3D non creato da SolidWorks (punti allineati?).", SwErrors.swSketchError)
            arc = new[0]
            P = lambda q: (float(q.X), float(q.Y), float(q.Z))
            c, a, b = P(arc.GetCenterPoint2), P(arc.GetStartPoint2), P(arc.GetEndPoint2)
            want = [(x1, y1, z1), (x2, y2, z2), (x3, y3, z3)]
            r = math.dist(c, a)
            data = {"entity_id": self._seg_id(arc), "center": [round(self._from_m(v, unit), 4) for v in c],
                    "radius": round(self._from_m(r, unit), 5), "length": round(self._from_m(float(arc.GetLength), unit), 5)}
            bad = [f"p{i + 1} a {round(self._from_m(abs(math.dist(c, q) - r), unit), 5)} dal cerchio" for i, q in enumerate(want)
                   if abs(math.dist(c, q) - r) > 1e-6]
            if math.dist(a, want[0]) > 1e-6 or math.dist(b, want[2]) > 1e-6:
                bad.append("estremi diversi da p1 e p3")
            if bad:
                return self._result(False, "Arco 3D non come chiesto: " + "; ".join(bad), SwErrors.swSketchError, data)
            return self._result(True, f"Arco 3D da {p1} a {p3} per {p2}: raggio {data['radius']}, lunghezza {data['length']}",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"draw_3d_arc: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def create_3d_sketch_plane(self, ref1=None, ref2=None, ref3=None, relation1: int = 4,
                               relation2: int = 0, relation3: int = 0) -> Dict:
        """Piano di lavoro dentro lo schizzo 3D attivo, vincolato a 1-3 riferimenti (piano/faccia/spigolo/punto: nome,
        'Front'/'Top'/'Right' o {"face":[x,y,z]}...). relationN = swRefPlaneReferenceConstraints: 4 coincidente
        (predefinito), 1 parallelo, 2 perpendicolare, 8 distanza, 16 angolo. Misurato 19/11: con 4 su un piano lo schizzo
        guadagna la relazione del piano; con un codice che non si applica CreateSketchPlane risponde True ma non aggiunge
        nulla: l'esito si legge dal numero di relazioni."""
        try:
            doc, err = self._part()
            if err:
                return err
            sm = doc.SketchManager
            sk = self._com(sm, "ActiveSketch")
            if sk is None or not self._s2_is3d(sk):
                return self._result(False, "Serve uno schizzo 3D aperto (create_3d_sketch).", SwErrors.swSketchError)
            refs = [r for r in (ref1, ref2, ref3) if r is not None]
            if not refs:
                return self._result(False, "Serve almeno ref1 (piano, faccia, spigolo o punto).", SwErrors.swInvalidInput)
            doc.ClearSelection2(True)
            for i, r in enumerate(refs):
                ok, msg, _o = self._select_any(doc, r, None, i > 0, 0)
                if not ok:
                    return self._result(False, f"Riferimento {i + 1} '{r}': {msg}", SwErrors.swSelectionError)
            rm = self._com(sk, "RelationManager")
            n0 = len(rm.GetRelations(0) or ())
            ok = bool(sm.CreateSketchPlane(int(relation1 or 0), int(relation2 or 0), int(relation3 or 0)))
            doc.ClearSelection2(True)
            n1 = len(rm.GetRelations(0) or ())
            data = {"references": [str(r) for r in refs], "relations": [relation1, relation2, relation3][:len(refs)],
                    "sketch_relations_added": n1 - n0}
            if not ok or n1 <= n0:
                return self._result(False, "SolidWorks non ha creato il piano nello schizzo 3D (nessuna relazione nuova: "
                                    "codice di relazione non adatto al riferimento?).", SwErrors.swSketchError, data)
            return self._result(True, f"Piano dello schizzo 3D creato su {data['references']} ({n1 - n0} relazioni nuove)",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"create_3d_sketch_plane: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def _seg3d_near(self, sk, q):
        """Segmento dello schizzo 3D piu' vicino al punto q (m) -> (segmento, distanza m)."""
        best, bd = None, 1e9
        for s0 in self._segments(sk):
            try:
                if int(s0.GetType) == 0:
                    a = s0.GetStartPoint2
                    b = s0.GetEndPoint2
                    A3, B3 = (a.X, a.Y, a.Z), (b.X, b.Y, b.Z)
                    v = [B3[i] - A3[i] for i in range(3)]
                    vv = sum(c * c for c in v) or 1e-30
                    t = max(0.0, min(1.0, sum((q[i] - A3[i]) * v[i] for i in range(3)) / vv))
                    d = math.dist(q, [A3[i] + t * v[i] for i in range(3)])
                else:
                    c = list(s0.GetCurve.GetClosestPointOn(q[0], q[1], q[2]))[:3]
                    d = math.dist(q, c)
            except Exception:
                continue
            if d < bd:
                best, bd = s0, d
        return best, bd

    def add_3d_sketch_axis_dimension(self, entity, axis: str = "x", x: float = None,
                                     y: float = None, z: float = None, unit: str = None) -> Dict:
        """Quota lungo l'asse X, Y o Z del modello in uno schizzo 3D (entity: id 'S0-1-2' o '@x,y,z' su di essa).
        Il valore si rilegge dalla quota creata e, per una linea, si confronta con la sua proiezione sull'asse."""
        try:
            doc, sk, err = self._s2_active_or_open()
            if err:
                return err
            if not self._s2_is3d(sk):
                return self._result(False, "Serve uno schizzo 3D aperto (create_3d_sketch).", SwErrors.swSketchError)
            sm = doc.SketchManager
            seg = None
            if isinstance(entity, str) and entity.strip().startswith("@") and entity.count(",") == 2:
                q = [self._mmu(float(v), unit) for v in entity.strip()[1:].split(",")]
                seg, d = self._seg3d_near(sk, q)
                if seg is None or d > 0.05e-3:
                    return self._result(False, f"Nessuna entita' dello schizzo 3D su {entity}.", SwErrors.swSelectionError)
            else:
                seg = next((s0 for s0 in self._segments(sk) if self._seg_id(s0) == str(entity)), None)
                if seg is None:
                    return self._result(False, f"Entita' '{entity}' non trovata (id o '@x,y,z').", SwErrors.swSelectionError)
            ax = str(axis or "x").lower().strip()
            if ax not in ("x", "y", "z"):
                return self._result(False, f"Asse '{axis}' non valido: usa 'x', 'y' o 'z'.", SwErrors.swInvalidInput)
            doc.ClearSelection2(True)
            seg.Select4(False, self._sd(doc, 0))
            px, py, pz = (self._mmu(v or 0.0, unit) for v in (x, y, z))
            dim = getattr(sm, {"x": "AddAlongXDimension", "y": "AddAlongYDimension", "z": "AddAlongZDimension"}[ax])(px, py, pz)
            doc.ClearSelection2(True)
            if dim is None:
                return self._result(False, "SolidWorks non ha creato la quota.", SwErrors.swSketchError)
            dm = dim.GetDimension2(0)
            val = float(dm.SystemValue)
            data = {"dimension": str(self._com(dm, "FullName")), "axis": ax, "entity": self._seg_id(seg),
                    "value": round(self._from_m(val, unit), 6)}
            if int(seg.GetType) == 0:
                a, b = seg.GetStartPoint2, seg.GetEndPoint2
                k = {"x": "X", "y": "Y", "z": "Z"}[ax]
                exp = abs(float(getattr(b, k)) - float(getattr(a, k)))
                data["expected"] = round(self._from_m(exp, unit), 6)
                if abs(exp - val) > 1e-7:
                    return self._result(False, f"Quota {data['value']} ma la linea misura {data['expected']} lungo {ax.upper()}.",
                                        SwErrors.swSketchError, data)
            return self._result(True, f"Quota {data['dimension']} lungo {ax.upper()} = {data['value']}", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"add_3d_sketch_axis_dimension: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def _block_instances(self, doc):
        sk = self._com(doc.SketchManager, "ActiveSketch")
        return sk, list((self._com(sk, "GetSketchBlockInstances") or ()) if sk is not None else ())

    def _block_counts(self, bd) -> Dict:
        out = {}
        for k, m in (("lines", "GetLineCount"), ("arcs", "GetArcCount"), ("points", "GetUserPointsCount")):
            try:
                out[k] = int(self._com(bd, m))
            except Exception:
                out[k] = None
        return out

    def edit_sketch_block(self, block_name: str) -> Dict:
        """Apre in modifica la definizione del blocco di un'istanza dello schizzo attivo (nome dell'istanza, es.
        'staffa-1', o della definizione 'staffa'): le entita' disegnate dopo vanno nel BLOCCO. block_name vuoto chiude
        la modifica salvando e riporta quante entita' ha la definizione prima e dopo. Misurato 19/11: durante la modifica
        ActiveSketch resta lo schizzo ospite (SolidWorks non espone lo stato), le entita' nuove finiscono nella
        definizione (linee 4 -> 5)."""
        try:
            doc, err = self._part()
            if err:
                return err
            sm = doc.SketchManager
            name = str(block_name or "").strip()
            state = getattr(self, "_block_edit", None)
            if not name:
                if not state:
                    return self._result(False, "Nessuna modifica di blocco aperta da edit_sketch_block.", SwErrors.swSketchError)
                sm.EndEditSketchBlock(True)
                self._block_edit = None
                after = self._block_counts(state["definition"])
                return self._result(True, f"Modifica del blocco {state['block']} chiusa: definizione {state['counts']} -> "
                                    f"{after}", SwErrors.swSuccess,
                                    {"block": state["block"], "editing": False, "before": state["counts"], "after": after})
            _sk, insts = self._block_instances(doc)
            inst = next((i for i in insts if str(self._com(i, "Name")) == name
                         or str(self._com(i, "Name")).rsplit("-", 1)[0] == name), None)
            if inst is None:
                return self._result(False, f"Nessuna istanza di blocco '{name}' nello schizzo attivo "
                                    f"({[str(self._com(i, 'Name')) for i in insts]}).", SwErrors.swSelectionError)
            doc.ClearSelection2(True)
            if not doc.Extension.SelectByID2(str(self._com(inst, "Name")), "SUBSKETCHINST", 0, 0, 0, False, 0, null_variant(), 0):
                return self._result(False, f"Istanza '{name}' non selezionabile.", SwErrors.swSelectionError)
            bd = self._com(inst, "Definition")
            counts = self._block_counts(bd)
            sm.EditSketchBlock()
            self._block_edit = {"block": name, "definition": bd, "counts": counts}
            return self._result(True, f"Modifica del blocco '{name}' aperta (definizione: {counts}); le entita' disegnate "
                                "ora vanno nel blocco; edit_sketch_block con nome vuoto la chiude e riporta il conteggio.",
                                SwErrors.swSuccess, {"block": name, "editing": True, "definition_counts": counts})
        except Exception as e:
            logger.error(f"edit_sketch_block: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)

    def explode_sketch_block(self, instance_name: str = None) -> Dict:
        """Esplode un'istanza di blocco dello schizzo attivo nelle sue entita' (senza nome: l'unica istanza presente).
        ExplodeSketchBlockInstance e' void: si controllano istanze e segmenti prima e dopo."""
        try:
            doc, err = self._part()
            if err:
                return err
            sk, insts = self._block_instances(doc)
            if sk is None:
                return self._result(False, "Nessuno schizzo attivo.", SwErrors.swSketchError)
            names = [str(self._com(i, "Name")) for i in insts]
            if instance_name:
                inst = next((i for i, n in zip(insts, names) if n == str(instance_name)), None)
            else:
                inst = insts[0] if len(insts) == 1 else None
            if inst is None:
                return self._result(False, f"Istanza '{instance_name}' non trovata (istanze: {names}; senza nome serve "
                                    "un'unica istanza).", SwErrors.swSelectionError)
            iname = str(self._com(inst, "Name"))
            n0 = len(self._com(sk, "GetSketchSegments") or ())
            doc.SketchManager.ExplodeSketchBlockInstance(inst)
            left = [str(self._com(i, "Name")) for i in (self._com(sk, "GetSketchBlockInstances") or ())]
            n1 = len(self._com(sk, "GetSketchSegments") or ())
            data = {"instance": iname, "segments_before": n0, "segments_after": n1, "instances_left": left}
            if iname in left or n1 <= n0:
                return self._result(False, f"SolidWorks non ha esploso '{iname}'.", SwErrors.swSketchError, data)
            return self._result(True, f"Blocco {iname} esploso: {n1 - n0} entita' nello schizzo", SwErrors.swSuccess, data)
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

    def create_area_hatch(self, angle: float = 45.0, scale: float = 1.0, color: int = 0,
                          hatch_name: str = "ANSI31", layer: str = None) -> Dict:
        """Crea un tratteggio / riempimento d'area all'interno di profili chiusi."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err
            sk_mgr = doc.SketchManager

            def counts():
                return (len(self._com(_sk, "GetSketchHatches") or ()), int(_sk.GetLineCount2(2)))  # 2 = solo tratteggio
            h0, l0 = counts()
            sk_mgr.CreateBoundaryHatch(float(angle), float(scale), int(color), str(hatch_name), str(layer or ""))
            h1, l1 = counts()
            data = {"hatch_name": hatch_name, "angle": angle, "scale": scale, "hatches": h1, "hatch_lines": l1 - l0}
            # (revisione) riletto: il numero di tratteggi e di linee di tratteggio dello schizzo deve crescere
            if h1 <= h0 or l1 <= l0:
                return self._result(False, f"create_area_hatch: tratteggio '{hatch_name}' non creato (servono contorni "
                                    "chiusi nello schizzo attivo).", SwErrors.swSketchError, data)
            return self._result(True, f"Tratteggio '{hatch_name}' creato: {l1 - l0} linee di tratteggio (angolo {angle} "
                                f"gradi, scala {scale})", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"create_area_hatch: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)
