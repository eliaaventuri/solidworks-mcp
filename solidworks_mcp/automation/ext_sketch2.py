"""
Lotto SCHIZZO 2: strumenti di schizzo mancanti (mixin). Schemi in tools_ext/sketch2.py.
I metodi usano gli helper di SketchConstraintOperations/ModelingBase tramite self (_active_sketch, _select_ref, _resolve_entity...).

Trappole API misurate dal vivo (2026-10-18, SolidWorks 2026 SP4.1, prove in scripts_tmp/sk2_*.py):
  * SketchTrim(opzione, x, y, z): il valore di ritorno NON e' affidabile (a volte False con il lavoro fatto, a volte True
    senza effetto). Si verifica rileggendo la geometria. x,y sono nelle coordinate dello schizzo (valido su ogni piano).
    Serve SEMPRE una selezione: 0 closest / power trim = l'entita' selezionata viene tagliata dalle intersezioni attorno al
    punto (x,y); un'entita' senza intersezioni viene cancellata. 3 (EntityPoint) NON e' un power trim: taglia l'entita' nel
    punto e toglie il lato iniziale. 1 corner e 2 two entities ignorano il punto di pick (non lo registrano nemmeno
    SelectData.X/Y/Z): il lato che resta lo sceglie SolidWorks. 5 outside / 6 inside: selezionare i DUE confini e poi
    l'entita' da tagliare (marchi 0).
  * SketchExtend(x, y, z): richiede l'entita' selezionata; (x,y) = vicino all'estremo da allungare.
  * CreateChamfer(tipo, Distance, AngleORdist): tipo 0 distanza-angolo (angolo in RADIANTI), 1 distanza-distanza, 2 uguale
    (il terzo argomento non puo' essere 0 nemmeno per il tipo 2). La prima entita' selezionata riceve il TERZO argomento.
  * CreateLinearSketchStepAndRepeat(NumX, NumY, SpX, SpY, AngX, AngY[rad], "") e CreateCircularSketchStepAndRepeat(R, A, n,
    passo[rad], ruota, ""): il centro della ripetizione circolare e' = centro del riquadro della selezione + R*(cosA, sinA)
    e il passo positivo e' ORARIO; con ruota=False le istanze sono sbagliate (risolutore), con ruota=True giuste.
    La stringa DeleteInstances non ha avuto effetto con nessun formato provato (omessa).
  * MoveOrCopy / RotateOrCopy / ScaleOrCopy (ModelDocExtension): coordinate nello spazio dello SCHIZZO. RotateOrCopy ruota
    attorno all'asse base->dest (usare dest = base + (0,0,0.01)); con un centro diverso dall'origine lo schizzo diventa
    "soluzione non valida" e la geometria sparisce: si sposta il centro nell'origine, si ruota e si riporta indietro.
    Con KeepRelations=True le relazioni inferite (orizzontale, coincidente con l'origine) bloccano lo spostamento.
    ScaleOrCopy con copy=True non copia: si copia sul posto (MoveOrCopy con spostamento nullo) e si scala la copia.
  * CreateEquationSpline/2: espressioni e intervallo nell'unita' di lunghezza del DOCUMENTO (mm), seno e coseno in radianti;
    offset (x,y) in METRI, rotazione in radianti; espressione sbagliata -> None. Nessun GetStartPoint2 sulla spline da
    equazione: si legge con GetCurve.GetEndParams + Evaluate2.
  * CreateTangentArc(x1,y1,z,x2,y2,z, tipo): tipo 1 (forward) e 3 (back) danno l'arco tangente (relazione inferita), 2 e 4
    danno l'arco normale. CreateParabola / CreateConic danno entita' di tipo 5 (parabola); Evaluate2 del parabola e' inutilizzabile.
  * Schizzo 3D: Insert3DSketch(True); close_sketch (InsertSketch) lo chiude. CreateLine/CreateSpline2 accettano la Z.
    ATTENZIONE: chiamare prima doc.CreatePoint2 sporca il punto di SketchManager.CreatePoint (restava a 0,0,0).
"""

import math
import re
import logging
import traceback
from typing import Dict, List, Optional

import pythoncom
from win32com.client import VARIANT

from ..constants import SwErrors
from .modeling_base import r8_array

logger = logging.getLogger(__name__)

TRIM_MODES = {"power": 0, "closest": 0, "corner": 1, "two_entities": 2, "outside": 5, "inside": 6}
CHAMFER_MODES = {"distance_angle": 0, "distance_distance": 1, "equal": 2}
TANGENT_TYPES = {"tangent": 1, "forward": 1, "left": 2, "back": 3, "right": 4}
_LEN_UNIT_M = {0: 0.001, 1: 0.01, 2: 1.0, 3: 0.0254, 4: 0.3048, 5: 0.3048, 6: 1e-10, 7: 1e-9, 8: 1e-6, 9: 2.54e-5}

# funzioni ammesse nelle espressioni (verifica in Python dell'equazione); nomi SolidWorks e Python
_EQ_FUNCS = {"sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin, "acos": math.acos, "atan": math.atan,
             "atn": math.atan, "sqrt": math.sqrt, "sqr": math.sqrt, "exp": math.exp, "ln": math.log, "log": math.log10,
             "abs": abs, "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh, "pi": math.pi}


def _dist(p, q) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(p, q)))


class Sketch2Operations:
    """Mixin: taglia/estendi, smusso di schizzo, ripetizioni di schizzo, sposta/copia/ruota/scala, entita' nuove, schizzo 3D."""

    # ------------------------------------------------------------------ helper: contesto, geometria, confronto
    def _s2_ctx(self, sketch: str = None):
        """-> (doc, sk, nome_schizzo, errore). Apre lo schizzo `sketch` se non e' quello attivo."""
        doc, err = self._part()
        if err:
            return None, None, None, err
        sk, err = self._active_sketch(doc, sketch)
        if err:
            return None, None, None, err
        return doc, sk, self._s2_name(doc, sk), None

    def _s2_name(self, doc, sk=None) -> Optional[str]:
        """Nome dello schizzo attivo, anche 3D (ProfileFeature o 3DProfileFeature)."""
        sk = sk or self._com(doc.SketchManager, "ActiveSketch")
        if sk is None:
            return None
        for n, t, f in self._features(doc):
            if t not in ("ProfileFeature", "3DProfileFeature"):
                continue
            try:
                if self._com(f, "GetSpecificFeature2") == sk:
                    return n
            except Exception:
                continue
        return self._last_of_type(doc, "3DProfileFeature") if self._s2_is3d(sk) else self._last_of_type(doc, "ProfileFeature")

    def _s2_is3d(self, sk) -> bool:
        try:
            return bool(self._com(sk, "Is3D"))
        except Exception:
            return False

    def _s2_segs(self, doc) -> list:
        sk = self._com(doc.SketchManager, "ActiveSketch")
        return self._segments(sk) if sk is not None else []

    def _s2_geo(self, seg) -> dict:
        """Descrizione numerica (mm) di un segmento: kind L linea / A arco / C cerchio / O altro."""
        t = int(seg.GetType)
        g = {"id": self._seg_id(seg), "t": t, "kind": "O", "construction": False, "len": None}
        try:
            g["construction"] = bool(seg.ConstructionGeometry)
        except Exception:
            pass
        try:
            g["len"] = float(seg.GetLength) * 1000.0
        except Exception:
            pass
        try:
            a, b = seg.GetStartPoint2, seg.GetEndPoint2
            g["s"] = (a.X * 1000.0, a.Y * 1000.0, a.Z * 1000.0)
            g["e"] = (b.X * 1000.0, b.Y * 1000.0, b.Z * 1000.0)
        except Exception:
            pass
        if t == 0 and "s" in g:
            g["kind"] = "L"
        elif t == 1 and "s" in g:
            try:
                c = seg.GetCenterPoint2
                g["c"] = (c.X * 1000.0, c.Y * 1000.0, c.Z * 1000.0)
                g["r"] = _dist(g["s"], g["c"])
                g["kind"] = "C" if _dist(g["s"], g["e"]) < 1e-6 else "A"
            except Exception:
                pass
        return g

    def _s2_snap(self, doc) -> List[dict]:
        return [self._s2_geo(s) for s in self._s2_segs(doc)]

    @staticmethod
    def _s2_close(a: dict, b: dict, tol: float = 0.02) -> bool:
        if a["kind"] != b["kind"]:
            return False
        k = a["kind"]
        if k == "L":
            return ((_dist(a["s"], b["s"]) < tol and _dist(a["e"], b["e"]) < tol)
                    or (_dist(a["s"], b["e"]) < tol and _dist(a["e"], b["s"]) < tol))
        if k == "C":
            return _dist(a["c"], b["c"]) < tol and abs(a["r"] - b["r"]) < tol
        if k == "A":
            if _dist(a["c"], b["c"]) >= tol or abs(a["r"] - b["r"]) >= tol:
                return False
            return ((_dist(a["s"], b["s"]) < tol and _dist(a["e"], b["e"]) < tol)
                    or (_dist(a["s"], b["e"]) < tol and _dist(a["e"], b["s"]) < tol))
        if a["t"] != b["t"]:
            return False
        la, lb = a.get("len"), b.get("len")
        return la is None or lb is None or abs(la - lb) < max(tol, 1e-3 * la)

    def _s2_unmatched(self, wanted: List[dict], actual: List[dict], tol: float = 0.02) -> List[dict]:
        """Elementi di `wanted` senza corrispondente in `actual` (ognuno si usa una volta sola)."""
        pool = list(actual)
        missing = []
        for w in wanted:
            for i, a in enumerate(pool):
                if self._s2_close(w, a, tol):
                    del pool[i]
                    break
            else:
                missing.append(w)
        return missing

    @staticmethod
    def _s2_brief(g: dict) -> dict:
        r = lambda p: [round(v, 4) for v in p]
        d = {"id": g["id"], "type": {0: "line", 1: "circle" if g["kind"] == "C" else "arc", 2: "ellipse", 3: "spline",
                                     5: "parabola"}.get(g["t"], str(g["t"]))}
        if g["construction"]:
            d["construction"] = True
        if "s" in g and g["kind"] != "C":
            d["start_mm"], d["end_mm"] = r(g["s"]), r(g["e"])
        if "c" in g:
            d["center_mm"] = r(g["c"])
            d["radius_mm"] = round(g["r"], 4)
        if g.get("len") is not None:
            d["length_mm"] = round(g["len"], 4)
        return d

    def _s2_select(self, doc, segs: list, mark: int = 0) -> bool:
        doc.ClearSelection2(True)
        ok = True
        for i, s in enumerate(segs):
            ok = bool(s.Select4(i > 0, self._sd(doc, mark))) and ok
        return ok

    def _s2_resolve(self, doc, sk, ref, unit):
        """-> (segmento, errore). Solo segmenti (non punti)."""
        obj, desc, e = self._resolve_entity(doc, sk, ref, unit)
        if e:
            return None, e
        if obj == "origin" or not hasattr(obj, "GetType") or not hasattr(obj, "GetLength"):
            return None, f"'{ref}' non e' un segmento dello schizzo"
        return obj, None

    def _s2_pick(self, ref, point, unit):
        """Punto di pick (m): `point` [x,y] oppure le coordinate di un riferimento '@x,y'."""
        if point is not None:
            return self._mmu(float(point[0]), unit), self._mmu(float(point[1]), unit)
        if isinstance(ref, str) and ref.strip().startswith("@"):
            xs, ys = ref.strip()[1:].split(",")
            return self._mmu(float(xs), unit), self._mmu(float(ys), unit)
        if isinstance(ref, (list, tuple)) and len(ref) == 2:
            return self._mmu(float(ref[0]), unit), self._mmu(float(ref[1]), unit)
        return None, None

    def _s2_new_ids(self, doc, before_ids: set) -> list:
        return [s for s in self._s2_segs(doc) if self._seg_id(s) not in before_ids]

    def _s2_delete(self, doc, segs: list) -> None:
        if not segs:
            return
        self._s2_select(doc, segs)
        doc.Extension.DeleteSelection2(0)
        doc.ClearSelection2(True)

    def _s2_curve_points(self, seg, fracs=(0.0, 0.5, 1.0)):
        """Punti (mm) della curva di un segmento a frazioni del suo parametro; None se illeggibile."""
        try:
            cv = seg.GetCurve
            a = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_R8, 0.0)
            b = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_R8, 0.0)
            c = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BOOL, False)
            d = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BOOL, False)
            cv.GetEndParams(a, b, c, d)
            out = []
            for f in fracs:
                ev = cv.Evaluate2(a.value + f * (b.value - a.value), 0)
                out.append(tuple(float(v) * 1000.0 for v in list(ev)[:3]))
            return out
        except Exception:
            return None

    def _s2_doc_unit_m(self, doc) -> float:
        """Metri per unita' di lunghezza del documento (le equazioni sono valutate in questa unita')."""
        try:
            return _LEN_UNIT_M.get(int(doc.Extension.GetUserPreferenceInteger(47, 0)), 0.001)
        except Exception:
            return 0.001

    def _s2_changed(self, before: List[dict], after: List[dict]) -> bool:
        return len(before) != len(after) or bool(self._s2_unmatched(before, after)) or bool(self._s2_unmatched(after, before))

    # ------------------------------------------------------------------ 1. taglia
    def trim_sketch_entities(self, mode: str = "power", entity=None, point: list = None, entity2=None,
                             boundaries: list = None, unit: str = None, sketch: str = None) -> Dict:
        """Taglia entita' di schizzo (SketchManager.SketchTrim). La riuscita si misura rileggendo la geometria."""
        try:
            m = str(mode or "power").lower().replace("-", "_").replace(" ", "_")
            if m not in TRIM_MODES:
                return self._result(False, f"mode '{mode}' sconosciuto: usa {', '.join(TRIM_MODES)}.", SwErrors.swInvalidInput)
            doc, sk, sk_name, err = self._s2_ctx(sketch)
            if err:
                return err
            if entity is None:
                return self._result(False, "Manca `entity` (l'entita' da tagliare).", SwErrors.swInvalidInput)
            px, py = self._s2_pick(entity, point, unit)
            if m in ("power", "closest") and px is None:
                return self._result(False, "power/closest: serve `point` [x,y] (il tratto vicino al punto viene tolto) "
                                    "oppure entity come '@x,y'.", SwErrors.swInvalidInput)
            if m in ("corner", "two_entities") and entity2 is None:
                return self._result(False, f"mode {m}: serve anche `entity2`.", SwErrors.swInvalidInput)
            if m in ("inside", "outside") and (not boundaries or len(boundaries) != 2):
                return self._result(False, f"mode {m}: servono esattamente 2 entita' di confine in `boundaries`.",
                                    SwErrors.swInvalidInput)
            refs = {"power": [entity], "closest": [entity], "corner": [entity, entity2], "two_entities": [entity, entity2],
                    "inside": list(boundaries or []) + [entity], "outside": list(boundaries or []) + [entity]}[m]
            doc.ClearSelection2(True)
            for i, r in enumerate(refs):
                ok, msg = self._select_ref(doc, sk, r, append=(i > 0), unit=unit)
                if not ok:
                    doc.ClearSelection2(True)
                    return self._result(False, f"Selezione di '{r}': {msg}", SwErrors.swSelectionError)
            before = self._s2_snap(doc)
            ret = doc.SketchManager.SketchTrim(TRIM_MODES[m], px or 0.0, py or 0.0, 0.0)
            doc.ClearSelection2(True)
            after = self._s2_snap(doc)
            if not self._s2_changed(before, after):
                return self._result(False, f"SketchTrim ({m}) non ha cambiato lo schizzo (ritorno {ret}): controlla che "
                                    "l'entita' abbia intersezioni vicino al punto e che il punto sia nelle coordinate dello schizzo.",
                                    SwErrors.swSketchError, {"sketch": sk_name, "segments": [self._s2_brief(g) for g in after]})
            removed = self._s2_unmatched(before, after)
            added = self._s2_unmatched(after, before)
            return self._result(True, f"Trim {m} in {sk_name}: -{len(removed)} +{len(added)} segmenti, restano {len(after)}",
                                SwErrors.swSuccess,
                                {"sketch": sk_name, "mode": m, "removed": [self._s2_brief(g) for g in removed],
                                 "added": [self._s2_brief(g) for g in added],
                                 "segments": [self._s2_brief(g) for g in after]})
        except Exception as e:
            logger.error(f"trim_sketch_entities: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    # ------------------------------------------------------------------ 2. estendi
    def extend_sketch_entity(self, entity=None, point: list = None, unit: str = None, sketch: str = None) -> Dict:
        """Estende una linea/arco fino alla prima entita' che incontra (SketchManager.SketchExtend)."""
        try:
            doc, sk, sk_name, err = self._s2_ctx(sketch)
            if err:
                return err
            if entity is None:
                return self._result(False, "Manca `entity`.", SwErrors.swInvalidInput)
            px, py = self._s2_pick(entity, point, unit)
            if px is None:
                return self._result(False, "Serve `point` [x,y] vicino all'estremo da allungare (o entity come '@x,y').",
                                    SwErrors.swInvalidInput)
            doc.ClearSelection2(True)
            ok, msg = self._select_ref(doc, sk, entity, append=False, unit=unit)
            if not ok:
                return self._result(False, f"Selezione di '{entity}': {msg}", SwErrors.swSelectionError)
            before = self._s2_snap(doc)
            ret = doc.SketchManager.SketchExtend(px, py, 0.0)
            doc.ClearSelection2(True)
            after = self._s2_snap(doc)
            if not self._s2_changed(before, after):
                return self._result(False, f"SketchExtend non ha cambiato lo schizzo (ritorno {ret}): serve un'entita' "
                                    "oltre l'estremo, nella direzione dell'entita', e `point` vicino a quell'estremo.",
                                    SwErrors.swSketchError, {"sketch": sk_name})
            old = self._s2_unmatched(before, after)
            new = self._s2_unmatched(after, before)
            return self._result(True, f"Estesa in {sk_name}: " + "; ".join(
                f"{self._s2_brief(g).get('start_mm')}->{self._s2_brief(g).get('end_mm')}" for g in new),
                SwErrors.swSuccess, {"sketch": sk_name, "before": [self._s2_brief(g) for g in old],
                                     "after": [self._s2_brief(g) for g in new]})
        except Exception as e:
            logger.error(f"extend_sketch_entity: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    # ------------------------------------------------------------------ 3. smusso di schizzo
    @staticmethod
    def _s2_line_intersection(a: dict, b: dict):
        x1, y1, _ = a["s"]
        x2, y2, _ = a["e"]
        x3, y3, _ = b["s"]
        x4, y4, _ = b["e"]
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(den) < 1e-12:
            return None
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1), 0.0)

    def sketch_chamfer(self, entity1=None, entity2=None, corner: list = None, mode: str = "distance_distance",
                       distance: float = 5.0, distance2: float = None, angle: float = 45.0, unit: str = None,
                       sketch: str = None) -> Dict:
        """Smusso fra due linee: distanza-distanza, distanza-angolo o uguale (SketchManager.CreateChamfer)."""
        try:
            m = str(mode or "distance_distance").lower().replace("-", "_").replace(" ", "_")
            if m not in CHAMFER_MODES:
                return self._result(False, f"mode '{mode}' sconosciuto: usa {', '.join(CHAMFER_MODES)}.", SwErrors.swInvalidInput)
            doc, sk, sk_name, err = self._s2_ctx(sketch)
            if err:
                return err
            d1 = self._mmu(distance, unit)
            d2 = self._mmu(distance2 if distance2 is not None else distance, unit)
            if d1 <= 0 or d2 <= 0:
                return self._result(False, "Le distanze devono essere positive.", SwErrors.swInvalidInput)
            if corner is not None:
                cx, cy = self._mmu(float(corner[0]), unit) * 1000, self._mmu(float(corner[1]), unit) * 1000
                hits = [s for s in self._s2_segs(doc) if int(s.GetType) == 0 and any(
                    math.hypot(p.X * 1000 - cx, p.Y * 1000 - cy) < 0.01 for p in (s.GetStartPoint2, s.GetEndPoint2))]
                if len(hits) != 2:
                    return self._result(False, f"Nel vertice ({corner[0]}, {corner[1]}) servono esattamente 2 linee "
                                        f"(trovate {len(hits)}).", SwErrors.swSelectionError)
                seg1, seg2 = hits
            else:
                if entity1 is None or entity2 is None:
                    return self._result(False, "Servono entity1 ed entity2 (due linee) oppure corner [x,y].", SwErrors.swInvalidInput)
                seg1, e1 = self._s2_resolve(doc, sk, entity1, unit)
                seg2, e2 = self._s2_resolve(doc, sk, entity2, unit)
                if e1 or e2:
                    return self._result(False, e1 or e2, SwErrors.swSelectionError)
            g1, g2 = self._s2_geo(seg1), self._s2_geo(seg2)
            if g1["kind"] != "L" or g2["kind"] != "L":
                return self._result(False, "sketch_chamfer: solo linee.", SwErrors.swInvalidInput)
            vtx = None
            for p in (g1["s"], g1["e"]):
                for q in (g2["s"], g2["e"]):
                    if _dist(p, q) < 0.01:
                        vtx = p
            if vtx is None:
                vtx = self._s2_line_intersection(g1, g2)
            if vtx is None:
                return self._result(False, "Le due linee sono parallele: niente smusso.", SwErrors.swInvalidInput)
            # distanza-angolo: la distanza va sulla SECONDA entita' selezionata (misurato), quindi si inverte l'ordine
            if not self._s2_select(doc, [seg2, seg1] if m == "distance_angle" else [seg1, seg2]):
                return self._result(False, "Selezione delle due linee rifiutata.", SwErrors.swSelectionError)
            before = self._s2_snap(doc)
            # la prima entita' selezionata riceve il TERZO argomento (misurato)
            if m == "distance_distance":
                res = doc.SketchManager.CreateChamfer(1, d2, d1)
            elif m == "equal":
                res = doc.SketchManager.CreateChamfer(2, d1, d1)
            else:
                res = doc.SketchManager.CreateChamfer(0, d1, math.radians(angle))
            doc.ClearSelection2(True)
            after = self._s2_snap(doc)
            if res is None or not self._s2_changed(before, after):
                return self._result(False, "CreateChamfer non ha creato lo smusso: le due linee devono incontrarsi in un "
                                    "vertice e le distanze stare dentro le linee.", SwErrors.swSketchError, {"sketch": sk_name})
            ch = self._s2_geo(res)                 # il ritorno e' il segmento dello smusso (le linee accorciate sono altre)
            legs = None
            if ch is not None and "s" in ch:
                # estremo dello smusso sulla prima linea = quello piu' vicino alla retta di g1
                def off_line(p):
                    dx, dy = g1["e"][0] - g1["s"][0], g1["e"][1] - g1["s"][1]
                    return abs(dx * (p[1] - g1["s"][1]) - dy * (p[0] - g1["s"][0])) / math.hypot(dx, dy)
                pa, pb = (ch["s"], ch["e"]) if off_line(ch["s"]) <= off_line(ch["e"]) else (ch["e"], ch["s"])
                legs = [round(_dist(pa, vtx), 4), round(_dist(pb, vtx), 4)]
            return self._result(True, f"Smusso {m} in {sk_name}: lunghezza {ch['len']:.4f} mm, tagli {legs} mm",
                                SwErrors.swSuccess,
                                {"sketch": sk_name, "chamfer": self._s2_brief(ch), "chamfer_length_mm": round(ch["len"], 4),
                                 "legs_mm": legs, "vertex_mm": [round(v, 4) for v in vtx[:2]],
                                 "segments": [self._s2_brief(g) for g in after]})
        except Exception as e:
            logger.error(f"sketch_chamfer: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    # ------------------------------------------------------------------ 4. ripetizioni di schizzo
    def _s2_pattern_select(self, doc, sk, entities, unit):
        if not entities:
            return None, self._result(False, "Manca `entities` (elenco di id/'@x,y' da ripetere).", SwErrors.swInvalidInput)
        segs = []
        for r in entities:
            s, e = self._s2_resolve(doc, sk, r, unit)
            if e:
                return None, self._result(False, f"Entita' '{r}': {e}", SwErrors.swSelectionError)
            if all(self._seg_id(s) != self._seg_id(x) for x in segs):
                segs.append(s)
        if not self._s2_select(doc, segs):
            doc.ClearSelection2(True)
            return None, self._result(False, "Selezione delle entita' rifiutata.", SwErrors.swSelectionError)
        return segs, None

    def sketch_linear_pattern(self, entities: list = None, count_x: int = 2, spacing_x: float = 10.0, count_y: int = 1,
                              spacing_y: float = 10.0, angle_x: float = 0.0, angle_y: float = None, unit: str = None,
                              sketch: str = None) -> Dict:
        """Ripetizione lineare di entita' di schizzo (CreateLinearSketchStepAndRepeat), verificata sulle posizioni."""
        try:
            doc, sk, sk_name, err = self._s2_ctx(sketch)
            if err:
                return err
            nx, ny = int(count_x), int(count_y)
            if nx < 1 or ny < 1 or nx * ny < 2:
                return self._result(False, "Servono count_x >= 1, count_y >= 1 e almeno 2 istanze in tutto.", SwErrors.swInvalidInput)
            ay = (angle_x + 90.0) if angle_y is None else angle_y
            segs, err = self._s2_pattern_select(doc, sk, entities, unit)
            if err:
                return err
            seeds = [self._s2_geo(s) for s in segs]
            before = self._s2_snap(doc)
            before_ids = {g["id"] for g in before}
            sx, sy = self._mmu(spacing_x, unit), self._mmu(spacing_y, unit)
            ret = doc.CreateLinearSketchStepAndRepeat(nx, ny, sx, sy, math.radians(angle_x), math.radians(ay), "")
            doc.ClearSelection2(True)
            after = self._s2_snap(doc)
            ux = (math.cos(math.radians(angle_x)), math.sin(math.radians(angle_x)))
            uy = (math.cos(math.radians(ay)), math.sin(math.radians(ay)))
            expected, last = [], None
            for j in range(ny):
                for i in range(nx):
                    if i == 0 and j == 0:
                        continue
                    off = (i * sx * 1000 * ux[0] + j * sy * 1000 * uy[0], i * sx * 1000 * ux[1] + j * sy * 1000 * uy[1])
                    for g in seeds:
                        expected.append(self._s2_apply(g, lambda p, o=off: (p[0] + o[0], p[1] + o[1], p[2])))
                    last = off
            missing = self._s2_unmatched(expected, after)
            new = [g for g in after if g["id"] not in before_ids]
            if missing or ret is False:
                return self._result(False, f"Ripetizione lineare non verificata: {len(missing)} istanze attese mancanti "
                                    f"(ritorno {ret}).", SwErrors.swSketchError,
                                    {"sketch": sk_name, "missing": [self._s2_brief(g) for g in missing][:6],
                                     "segments": [self._s2_brief(g) for g in after]})
            real = [g for g in new if not g["construction"]]
            lastg = self._s2_apply(seeds[0], lambda p, o=last: (p[0] + o[0], p[1] + o[1], p[2]))
            return self._result(True, f"Ripetizione lineare {nx}x{ny} in {sk_name}: +{len(real)} segmenti, ultima istanza "
                                f"spostata di ({last[0]:.4f}, {last[1]:.4f}) mm", SwErrors.swSuccess,
                                {"sketch": sk_name, "instances": nx * ny, "new_entity_ids": [g["id"] for g in real],
                                 "construction_ids": [g["id"] for g in new if g["construction"]],
                                 "last_instance_offset_mm": [round(last[0], 4), round(last[1], 4)],
                                 "last_instance": self._s2_brief(lastg)})
        except Exception as e:
            logger.error(f"sketch_linear_pattern: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    @staticmethod
    def _s2_apply(g: dict, f, k: float = 1.0) -> dict:
        """Geometria trasformata: f(punto mm) -> punto; k = fattore di scala di raggi e lunghezze."""
        h = dict(g)
        for key in ("s", "e", "c"):
            if key in g:
                h[key] = f(g[key])
        if "r" in g:
            h["r"] = g["r"] * k
        if g.get("len") is not None:
            h["len"] = g["len"] * k
        return h

    @staticmethod
    def _s2_rot(cx: float, cy: float, ang: float):
        ca, sa = math.cos(ang), math.sin(ang)
        return lambda p: (cx + (p[0] - cx) * ca - (p[1] - cy) * sa, cy + (p[0] - cx) * sa + (p[1] - cy) * ca, p[2])

    def _s2_bbox_center(self, geos: List[dict]):
        xs, ys = [], []
        for g in geos:
            if g["kind"] in ("L", "A", "O") and "s" in g:
                xs += [g["s"][0], g["e"][0]]
                ys += [g["s"][1], g["e"][1]]
            if g["kind"] in ("C", "A") and "c" in g:
                if g["kind"] == "C":
                    xs += [g["c"][0] - g["r"], g["c"][0] + g["r"]]
                    ys += [g["c"][1] - g["r"], g["c"][1] + g["r"]]
                else:
                    xs.append(g["c"][0])
                    ys.append(g["c"][1])
        if not xs:
            return None
        return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2

    def sketch_circular_pattern(self, entities: list = None, center: list = None, count: int = 4,
                                spacing_angle: float = None, unit: str = None, sketch: str = None) -> Dict:
        """Ripetizione circolare di entita' di schizzo attorno a `center`; verificata sulle posizioni."""
        try:
            doc, sk, sk_name, err = self._s2_ctx(sketch)
            if err:
                return err
            n = int(count)
            if n < 2:
                return self._result(False, "count deve essere almeno 2 (seme incluso).", SwErrors.swInvalidInput)
            if not center or len(center) != 2:
                return self._result(False, "Serve `center` [x,y] (centro della ripetizione).", SwErrors.swInvalidInput)
            step = (360.0 / n) if spacing_angle is None else float(spacing_angle)
            ccx, ccy = self._mmu(float(center[0]), unit) * 1000, self._mmu(float(center[1]), unit) * 1000
            segs, err = self._s2_pattern_select(doc, sk, entities, unit)
            if err:
                return err
            seeds = [self._s2_geo(s) for s in segs]
            before = self._s2_snap(doc)
            before_ids = {g["id"] for g in before}
            expected = []
            for k in range(1, n):
                rot = self._s2_rot(ccx, ccy, math.radians(step * k))
                expected += [self._s2_apply(g, rot) for g in seeds]
            ref = self._s2_bbox_center(seeds)
            method = "CreateCircularSketchStepAndRepeat"
            ok_native = False
            if ref is not None and math.hypot(ccx - ref[0], ccy - ref[1]) > 1e-6:
                R = math.hypot(ccx - ref[0], ccy - ref[1]) / 1000.0
                A_ = math.atan2(ccy - ref[1], ccx - ref[0])
                # passo positivo dell'API = orario: si passa il passo antiorario cambiato di segno
                doc.CreateCircularSketchStepAndRepeat(R, A_, n, -math.radians(step), True, "")
                doc.ClearSelection2(True)
                after = self._s2_snap(doc)
                ok_native = (len(after) == len(before) + len(expected)
                             and not self._s2_unmatched(expected, after))
            if not ok_native:
                # l'API ha sbagliato (o il riferimento e' ambiguo): tolgo cio' che ha creato e ruoto con RotateOrCopy
                if ref is not None and math.hypot(ccx - ref[0], ccy - ref[1]) > 1e-6:
                    self._s2_delete(doc, self._s2_new_ids(doc, before_ids))
                method = "RotateOrCopy (fallback)"
                self._s2_rotate_copies(doc, segs, ccx, ccy, math.radians(step), n - 1)
                after = self._s2_snap(doc)
            missing = self._s2_unmatched(expected, after)
            if missing or len(after) != len(before) + len(expected):
                return self._result(False, f"Ripetizione circolare non verificata: mancano {len(missing)} istanze, "
                                    f"segmenti {len(before)} -> {len(after)} (attesi +{len(expected)}).", SwErrors.swSketchError,
                                    {"sketch": sk_name, "segments": [self._s2_brief(g) for g in after]})
            new = [g for g in after if g["id"] not in before_ids]
            return self._result(True, f"Ripetizione circolare x{n} attorno a ({center[0]}, {center[1]}) in {sk_name} "
                                f"({method}): +{len(new)} segmenti", SwErrors.swSuccess,
                                {"sketch": sk_name, "instances": n, "method": method, "new_entity_ids": [g["id"] for g in new],
                                 "spacing_angle_deg": step, "last_instance": self._s2_brief(self._s2_apply(
                                     seeds[0], self._s2_rot(ccx, ccy, math.radians(step * (n - 1)))))})
        except Exception as e:
            logger.error(f"sketch_circular_pattern: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    # ------------------------------------------------------------------ 5. sposta / copia / ruota / scala
    def _s2_rotate_copies(self, doc, segs, cx_mm, cy_mm, ang, ncopies):
        """Copie ruotate di `ang` (antiorario) attorno a (cx,cy) mm: centro nell'origine, RotateOrCopy, ritorno."""
        before_ids = {self._seg_id(s) for s in self._s2_segs(doc)}
        self._s2_select(doc, segs)
        doc.Extension.MoveOrCopy(False, 0, False, cx_mm / 1000, cy_mm / 1000, 0.0, 0.0, 0.0, 0.0)
        self._s2_select(doc, segs)
        doc.Extension.RotateOrCopy(True, int(ncopies), False, 0.0, 0.0, 0.0, 0.0, 0.0, 0.01, ang)
        new = self._s2_new_ids(doc, before_ids)
        self._s2_select(doc, list(segs) + new)
        doc.Extension.MoveOrCopy(False, 0, False, 0.0, 0.0, 0.0, cx_mm / 1000, cy_mm / 1000, 0.0)
        doc.ClearSelection2(True)
        return new

    def transform_sketch_entities(self, operation: str = "move", entities: list = None, dx: float = 0.0, dy: float = 0.0,
                                  angle: float = 0.0, scale: float = 1.0, center: list = None, copy: bool = False,
                                  copies: int = 1, keep_relations: bool = False, unit: str = None,
                                  sketch: str = None) -> Dict:
        """Sposta / copia / ruota / scala entita' di schizzo (ModelDocExtension.MoveOrCopy / RotateOrCopy / ScaleOrCopy)."""
        try:
            op = str(operation or "move").lower()
            if op not in ("move", "rotate", "scale"):
                return self._result(False, f"operation '{operation}' sconosciuta: usa move, rotate o scale (copy=true per copiare).",
                                    SwErrors.swInvalidInput)
            doc, sk, sk_name, err = self._s2_ctx(sketch)
            if err:
                return err
            nc = max(1, int(copies)) if copy else 0
            c = center if center else [0.0, 0.0]
            ccx, ccy = self._mmu(float(c[0]), unit) * 1000, self._mmu(float(c[1]), unit) * 1000
            if op == "scale" and scale <= 0:
                return self._result(False, "scale deve essere > 0.", SwErrors.swInvalidInput)
            segs, err = self._s2_pattern_select(doc, sk, entities, unit)
            if err:
                return err
            seeds = [self._s2_geo(s) for s in segs]
            seed_ids = {g["id"] for g in seeds}
            before = self._s2_snap(doc)
            before_ids = {g["id"] for g in before}
            others = [g for g in before if g["id"] not in seed_ids]
            dxm, dym = self._mmu(dx, unit), self._mmu(dy, unit)
            expected = list(others)
            if op == "move":
                tf = lambda k: (lambda p: (p[0] + k * dxm * 1000, p[1] + k * dym * 1000, p[2]))
                k_scale = lambda k: 1.0
            elif op == "rotate":
                tf = lambda k: self._s2_rot(ccx, ccy, math.radians(angle * k))
                k_scale = lambda k: 1.0
            else:
                tf = lambda k: (lambda p, f=scale ** k: (ccx + (p[0] - ccx) * f, ccy + (p[1] - ccy) * f, p[2]))
                k_scale = lambda k: scale ** k
            if copy:
                expected += seeds
                for k in range(1, nc + 1):
                    expected += [self._s2_apply(g, tf(k), k_scale(k)) for g in seeds]
            else:
                expected += [self._s2_apply(g, tf(1), k_scale(1)) for g in seeds]
            # esecuzione
            if op == "move":
                self._s2_select(doc, segs)
                doc.Extension.MoveOrCopy(bool(copy), nc, bool(keep_relations), 0.0, 0.0, 0.0, dxm, dym, 0.0)
            elif op == "rotate":
                if abs(ccx) < 1e-9 and abs(ccy) < 1e-9:
                    self._s2_select(doc, segs)
                    doc.Extension.RotateOrCopy(bool(copy), nc, bool(keep_relations), 0.0, 0.0, 0.0, 0.0, 0.0, 0.01,
                                               math.radians(angle))
                elif copy:
                    self._s2_rotate_copies(doc, segs, ccx, ccy, math.radians(angle), nc)
                else:
                    self._s2_select(doc, segs)
                    doc.Extension.MoveOrCopy(False, 0, False, ccx / 1000, ccy / 1000, 0.0, 0.0, 0.0, 0.0)
                    self._s2_select(doc, segs)
                    doc.Extension.RotateOrCopy(False, 0, False, 0.0, 0.0, 0.0, 0.0, 0.0, 0.01, math.radians(angle))
                    self._s2_select(doc, segs)
                    doc.Extension.MoveOrCopy(False, 0, False, 0.0, 0.0, 0.0, ccx / 1000, ccy / 1000, 0.0)
            else:
                if not copy:
                    self._s2_select(doc, segs)
                    doc.Extension.ScaleOrCopy(False, 0, ccx / 1000, ccy / 1000, 0.0, float(scale))
                else:
                    for k in range(1, nc + 1):          # ScaleOrCopy non copia: copia sul posto e scala la copia
                        ids0 = {self._seg_id(s) for s in self._s2_segs(doc)}
                        self._s2_select(doc, segs)
                        doc.Extension.MoveOrCopy(True, 1, False, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                        new = self._s2_new_ids(doc, ids0)
                        self._s2_select(doc, new)
                        doc.Extension.ScaleOrCopy(False, 0, ccx / 1000, ccy / 1000, 0.0, float(scale) ** k)
            doc.ClearSelection2(True)
            after = self._s2_snap(doc)
            missing = self._s2_unmatched(expected, after)
            if missing or len(after) != len(expected):
                return self._result(False, f"{op}: geometria diversa dall'attesa ({len(missing)} segmenti attesi non trovati, "
                                    f"segmenti {len(after)} invece di {len(expected)}). Controlla relazioni e vincoli "
                                    "(keep_relations=false le ignora).", SwErrors.swSketchError,
                                    {"sketch": sk_name, "missing": [self._s2_brief(g) for g in missing][:6],
                                     "segments": [self._s2_brief(g) for g in after]})
            new = [g for g in after if g["id"] not in before_ids]
            return self._result(True, f"{op}{' + copia x' + str(nc) if copy else ''} in {sk_name}: {len(seeds)} entita', "
                                f"{len(new)} nuovi segmenti", SwErrors.swSuccess,
                                {"sketch": sk_name, "operation": op, "copies": nc, "new_entity_ids": [g["id"] for g in new],
                                 "result": [self._s2_brief(self._s2_apply(g, tf(max(1, nc) if copy else 1), k_scale(max(1, nc) if copy else 1)))
                                            for g in seeds],
                                 "segments": [self._s2_brief(g) for g in after]})
        except Exception as e:
            logger.error(f"transform_sketch_entities: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    # ------------------------------------------------------------------ 6. entita' nuove
    def _s2_created(self, doc, before_ids: set, label: str, extra: Dict = None) -> Dict:
        new = [self._s2_geo(s) for s in self._s2_segs(doc) if self._seg_id(s) not in before_ids]
        real = [g for g in new if not g["construction"]]
        data = {"entity_ids": [g["id"] for g in real], "construction_ids": [g["id"] for g in new if g["construction"]],
                "segments": [self._s2_brief(g) for g in real]}
        lines = [g for g in real if g["kind"] == "L"]
        if len(lines) == 4:
            verts = []
            for g in lines:
                for p in (g["s"], g["e"]):
                    if not any(_dist(p, v) < 0.001 for v in verts):
                        verts.append(p)
            data["vertices_mm"] = [[round(v[0], 4), round(v[1], 4)] for v in verts]
        if extra:
            data.update(extra)
        return self._result(True, f"{label} {data['entity_ids']}", SwErrors.swSuccess, data)

    def _s2_draw(self, label, fn):
        doc, sm, err = self._sketch_ready()
        if err:
            return err
        before_ids = {self._seg_id(s) for s in self._s2_segs(doc)}
        res = fn(sm)
        if res is None:
            return self._result(False, f"{label}: SolidWorks non ha creato nulla (controlla i punti).", SwErrors.swSketchError)
        return self._s2_created(doc, before_ids, label)

    def draw_center_rectangle(self, cx: float, cy: float, x2: float, y2: float, unit: str = None) -> Dict:
        """Rettangolo dal centro e da un angolo (asse: lati paralleli agli assi dello schizzo)."""
        try:
            m = lambda v: self._mmu(v, unit)
            return self._s2_draw("Rettangolo da centro", lambda sm: sm.CreateCenterRectangle(m(cx), m(cy), 0, m(x2), m(y2), 0))
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def draw_3point_rectangle(self, x1: float, y1: float, x2: float, y2: float, x3: float, y3: float,
                              center: bool = False, unit: str = None) -> Dict:
        """Rettangolo inclinato da 3 punti: spigolo p1->p2 e terzo punto (larghezza), oppure centro/meta' lato/angolo."""
        try:
            m = lambda v: self._mmu(v, unit)
            args = (m(x1), m(y1), 0, m(x2), m(y2), 0, m(x3), m(y3), 0)
            if center:
                return self._s2_draw("Rettangolo 3 punti da centro", lambda sm: sm.Create3PointCenterRectangle(*args))
            return self._s2_draw("Rettangolo 3 punti", lambda sm: sm.Create3PointCornerRectangle(*args))
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def draw_parallelogram(self, x1: float, y1: float, x2: float, y2: float, x3: float, y3: float, unit: str = None) -> Dict:
        """Parallelogramma da 3 vertici: p1, p2 consecutivi e p3 (il quarto e' p1 + p3 - p2)."""
        try:
            m = lambda v: self._mmu(v, unit)
            return self._s2_draw("Parallelogramma", lambda sm: sm.CreateParallelogram(m(x1), m(y1), 0, m(x2), m(y2), 0, m(x3), m(y3), 0))
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def draw_tangent_arc(self, x1: float, y1: float, x2: float, y2: float, arc_type: str = "tangent",
                         unit: str = None) -> Dict:
        """Arco tangente: parte dall'estremo (x1,y1) di un'entita' esistente e finisce in (x2,y2)."""
        try:
            doc, sm, err = self._sketch_ready()
            if err:
                return err
            at = TANGENT_TYPES.get(str(arc_type).lower())
            if at is None:
                return self._result(False, f"arc_type '{arc_type}' sconosciuto: usa {', '.join(TANGENT_TYPES)}.", SwErrors.swInvalidInput)
            m = lambda v: self._mmu(v, unit)
            before_ids = {self._seg_id(s) for s in self._s2_segs(doc)}
            geos = self._s2_snap(doc)
            host = None
            for g in geos:
                if "s" in g and g["kind"] == "L":
                    for key in ("s", "e"):
                        if math.hypot(g[key][0] - m(x1) * 1000, g[key][1] - m(y1) * 1000) < 0.01:
                            host = (g, key)
            res = sm.CreateTangentArc(m(x1), m(y1), 0, m(x2), m(y2), 0, at)
            if res is None:
                return self._result(False, "CreateTangentArc non ha creato l'arco: (x1,y1) deve essere un estremo di una "
                                    "linea o di un arco esistente.", SwErrors.swSketchError)
            arc = next((self._s2_geo(s) for s in self._s2_segs(doc) if self._seg_id(s) not in before_ids), None)
            extra = {}
            if arc is not None and "c" in arc:
                extra = {"center_mm": [round(arc["c"][0], 4), round(arc["c"][1], 4)], "radius_mm": round(arc["r"], 4)}
                if host is not None:
                    g, key = host
                    other = g["e"] if key == "s" else g["s"]
                    tx, ty = g[key][0] - other[0], g[key][1] - other[1]
                    rx, ry = g[key][0] - arc["c"][0], g[key][1] - arc["c"][1]
                    cosang = abs(tx * rx + ty * ry) / (math.hypot(tx, ty) * math.hypot(rx, ry))
                    extra["tangent_deviation_deg"] = round(math.degrees(math.asin(min(1.0, cosang))), 4)
                    extra["tangent"] = extra["tangent_deviation_deg"] < 0.01
            return self._s2_created(doc, before_ids, "Arco tangente", extra)
        except Exception as e:
            logger.error(f"draw_tangent_arc: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def _s2_conic(self, label, method, focus, apex, start, end, unit):
        try:
            doc, sm, err = self._sketch_ready()
            if err:
                return err
            m = lambda v: self._mmu(v, unit)
            before_ids = {self._seg_id(s) for s in self._s2_segs(doc)}
            res = getattr(sm, method)(m(focus[0]), m(focus[1]), 0, m(apex[0]), m(apex[1]), 0,
                                      m(start[0]), m(start[1]), 0, m(end[0]), m(end[1]), 0)
            if res is None:
                return self._result(False, f"{method}: SolidWorks non ha creato la curva (i punti non definiscono una "
                                    "curva valida: start/end devono stare sulla curva dal fuoco e dal vertice).", SwErrors.swSketchError)
            return self._s2_created(doc, before_ids, label)
        except Exception as e:
            logger.error(f"{method}: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def draw_parabola(self, focus: list, apex: list, start: list, end: list, unit: str = None) -> Dict:
        """Parabola da fuoco, vertice e due estremi (CreateParabola)."""
        return self._s2_conic("Parabola", "CreateParabola", focus, apex, start, end, unit)

    @staticmethod
    def _s2_eval(expr: str, var: str, value: float):
        """Valuta in Python l'espressione di un'equazione (solo funzioni ammesse); None se non e' possibile."""
        try:
            e = expr.replace("^", "**")
            for name in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", e):
                if name != var and name not in _EQ_FUNCS:
                    return None
            if re.search(r"[^0-9A-Za-z_+\-*/().,\s]", e):
                return None
            ns = dict(_EQ_FUNCS)
            ns[var] = value
            return float(eval(e, {"__builtins__": {}}, ns))
        except Exception:
            return None

    def draw_equation_curve(self, y_expression: str = None, x_expression: str = None, start: float = 0.0, end: float = 1.0,
                            rotation: float = 0.0, x_offset: float = 0.0, y_offset: float = 0.0, unit: str = None) -> Dict:
        """Curva da equazione: y=f(x) (solo y_expression, variabile x) o parametrica x(t), y(t) (variabile t)."""
        try:
            doc, sm, err = self._sketch_ready()
            if err:
                return err
            if not y_expression:
                return self._result(False, "Manca y_expression (y=f(x) in x, oppure y(t) con x_expression x(t)).", SwErrors.swInvalidInput)
            if end <= start:
                return self._result(False, "end deve essere maggiore di start.", SwErrors.swInvalidInput)
            parametric = bool(x_expression)
            # le equazioni sono valutate nell'unita' di lunghezza del documento: si converte quella di `unit`
            k = self._mmu(1.0, unit) / self._s2_doc_unit_m(doc)
            ye = y_expression if parametric else re.sub(r"\bx\b", "t", y_expression)
            xe = x_expression if parametric else "t"
            scale = (lambda s: s) if abs(k - 1.0) < 1e-12 else (lambda s: f"({s})*{k!r}")
            before_ids = {self._seg_id(s) for s in self._s2_segs(doc)}
            res = sm.CreateEquationSpline2(scale(xe), scale(ye), "0", repr(float(start)), repr(float(end)), False,
                                           math.radians(rotation), self._mmu(x_offset, unit), self._mmu(y_offset, unit),
                                           False, False)
            if res is None:
                return self._result(False, "CreateEquationSpline2 non ha creato la curva: espressione non valida per "
                                    "SolidWorks (usa sin, cos, tan, sqr, exp, ln, abs, ^, pi; variabile "
                                    f"'{'t' if parametric else 'x'}').", SwErrors.swSketchError)
            seg = next((s for s in self._s2_segs(doc) if self._seg_id(s) not in before_ids), None)
            pts = self._s2_curve_points(seg, (0.0, 0.5, 1.0)) if seg is not None else None
            extra = {"document_length_unit_m": self._s2_doc_unit_m(doc)}
            if pts:
                ku = self._mmu(1.0, unit) * 1000.0                       # mm per `unit`
                extra["points_mm"] = {"start": [round(v, 4) for v in pts[0][:2]], "mid": [round(v, 4) for v in pts[1][:2]],
                                      "end": [round(v, 4) for v in pts[2][:2]]}
                # verifica in Python agli estremi (se l'espressione e' valutabile)
                ca, sa = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
                chk = []
                for f, t in ((0, start), (2, end)):
                    xv = t if not parametric else self._s2_eval(xe, "t", t)
                    yv = self._s2_eval(ye, "t", t)
                    if xv is None or yv is None:
                        chk = None
                        break
                    xv, yv = xv * ku, yv * ku
                    ex = xv * ca - yv * sa + self._mmu(x_offset, unit) * 1000
                    ey = xv * sa + yv * ca + self._mmu(y_offset, unit) * 1000
                    chk.append(round(math.hypot(pts[f][0] - ex, pts[f][1] - ey), 5))
                if chk is not None:
                    extra["endpoint_error_mm"] = chk
                    if max(chk) > 0.01:
                        return self._result(False, f"La curva creata non coincide con l'equazione (scarto {max(chk)} mm agli "
                                            "estremi).", SwErrors.swSketchError, extra)
            return self._s2_created(doc, before_ids, "Curva da equazione", extra)
        except Exception as e:
            logger.error(f"draw_equation_curve: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    # ------------------------------------------------------------------ 7. schizzo 3D
    def create_3d_sketch(self) -> Dict:
        """Apre un nuovo schizzo 3D (chiude l'eventuale schizzo attivo); si chiude con close_sketch."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            doc.ClearSelection2(True)
            doc.SketchManager.Insert3DSketch(True)
            sk = self._com(doc.SketchManager, "ActiveSketch")
            if sk is None or not self._s2_is3d(sk):
                return self._result(False, "Insert3DSketch non ha aperto uno schizzo 3D.", SwErrors.swSketchError)
            name = self._s2_name(doc, sk)
            return self._result(True, f"Schizzo 3D '{name}' aperto (chiudilo con close_sketch)", SwErrors.swSuccess,
                                {"sketch": name, "is_3d": True})
        except Exception as e:
            logger.error(f"create_3d_sketch: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def _s2_3d_ready(self):
        doc, sm, err = self._sketch_ready()
        if err:
            return None, None, err
        if not self._s2_is3d(self._com(sm, "ActiveSketch")):
            return None, None, self._result(False, "Lo schizzo attivo non e' 3D: usa create_3d_sketch.", SwErrors.swSketchError)
        return doc, sm, None

    @staticmethod
    def _s2_xyz(p, scale: float = 1000.0):
        return [round(p.X * scale, 4), round(p.Y * scale, 4), round(p.Z * scale, 4)]

    def draw_3d_line(self, x1: float, y1: float, z1: float, x2: float, y2: float, z2: float, unit: str = None) -> Dict:
        """Linea nello schizzo 3D attivo (coordinate del modello)."""
        try:
            doc, sm, err = self._s2_3d_ready()
            if err:
                return err
            m = lambda v: self._mmu(v, unit)
            want = [m(x1) * 1000, m(y1) * 1000, m(z1) * 1000, m(x2) * 1000, m(y2) * 1000, m(z2) * 1000]
            seg = sm.CreateLine(m(x1), m(y1), m(z1), m(x2), m(y2), m(z2))
            if seg is None:
                return self._result(False, "CreateLine fallito (punti coincidenti?)", SwErrors.swSketchError)
            s, e = self._s2_xyz(seg.GetStartPoint2), self._s2_xyz(seg.GetEndPoint2)
            err_mm = max(abs(a - b) for a, b in zip(s + e, want))
            if err_mm > 0.001:
                return self._result(False, f"Linea 3D creata ma fuori posto di {err_mm:.4f} mm: {s} -> {e}", SwErrors.swSketchError)
            return self._ent_result(seg, f"Linea 3D {s} -> {e} mm", {"start_mm": s, "end_mm": e,
                                                                      "length_mm": round(float(seg.GetLength) * 1000, 4)})
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def draw_3d_spline(self, points: list, unit: str = None) -> Dict:
        """Spline per punti [[x,y,z],...] (almeno 2) nello schizzo 3D attivo."""
        try:
            doc, sm, err = self._s2_3d_ready()
            if err:
                return err
            if not points or len(points) < 2 or any(len(p) != 3 for p in points):
                return self._result(False, "Servono almeno 2 punti [x,y,z].", SwErrors.swInvalidInput)
            flat = []
            for p in points:
                flat += [self._mmu(p[0], unit), self._mmu(p[1], unit), self._mmu(p[2], unit)]
            seg = sm.CreateSpline2(r8_array(flat), True)
            if seg is None:
                return self._result(False, "CreateSpline2 fallito", SwErrors.swSketchError)
            ends = self._s2_curve_points(seg, (0.0, 1.0))
            extra = {"point_count": len(points)}
            if ends:
                first = [self._mmu(points[0][i], unit) * 1000 for i in range(3)]
                last = [self._mmu(points[-1][i], unit) * 1000 for i in range(3)]
                extra["endpoint_error_mm"] = [round(_dist(ends[0], first), 5), round(_dist(ends[1], last), 5)]
                extra["start_mm"] = [round(v, 4) for v in ends[0]]
                extra["end_mm"] = [round(v, 4) for v in ends[1]]
                if max(extra["endpoint_error_mm"]) > 0.01:
                    return self._result(False, f"La spline non passa per gli estremi (scarto {extra['endpoint_error_mm']} mm).",
                                        SwErrors.swSketchError, extra)
            return self._ent_result(seg, f"Spline 3D per {len(points)} punti", extra)
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def draw_3d_point(self, x: float, y: float, z: float, unit: str = None) -> Dict:
        """Punto nello schizzo 3D attivo."""
        try:
            doc, sm, err = self._s2_3d_ready()
            if err:
                return err
            m = lambda v: self._mmu(v, unit)
            p = sm.CreatePoint(m(x), m(y), m(z))
            if p is None:
                return self._result(False, "CreatePoint fallito", SwErrors.swSketchError)
            got = self._s2_xyz(p)
            want = [m(x) * 1000, m(y) * 1000, m(z) * 1000]
            if max(abs(a - b) for a, b in zip(got, want)) > 0.001:
                return self._result(False, f"Punto creato in {got} invece di {[round(v, 4) for v in want]} mm.", SwErrors.swSketchError)
            return self._result(True, f"Punto 3D [{self._pt_id(p)}] {got} mm", SwErrors.swSuccess,
                                {"point_id": self._pt_id(p), "position_mm": got})
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)
