"""
Lotto CURVE (elica e spirale, curva proiettata, linea di divisione, curva composita, curve per punti) (mixin).
Schemi in tools_ext/curves.py. I metodi usano gli helper di ModelingBase/ModelingOperations tramite self
(_part, _select_point, _select_points, _finish, _names, _new_features, _volume_m3, _mmu, _result...).

Trappole API scoperte (SW 2026, misurate nel laboratorio crv, vedi scripts_tmp/notes_curves.md):
 - Una curva di riferimento (elica, proiezione, composita...) NON ha ne' volume ne' facce: per misurarla si usa
   `feat.GetSpecificFeature2` (IReferenceCurve) -> `GetSegments` (spigoli) -> `edge.GetCurve` / `GetCurveParams2` ->
   `ICurve.GetLength3(t0, t1)` ed `Evaluate2(t, 0)`. Vedi `_curve_summary`.
 - InsertHelix(Reversed, Clockwised, Tapered, Outward, Helixdef, Height, Pitch, Revolution, TaperAngle, Startangle) e'
   void: l'esito si legge dalla feature nuova (tipo "Helix"). Altezza e passo in metri, angoli in radianti. Si seleziona
   la FEATURE schizzo (Select2 mark 0). Spirale: `Reversed` la fa andare verso l'interno, `Outward` non cambia nulla.
 - `EndVariablePitchHelix` e' una PROPRIETA' (late binding), non un metodo. La prima riga della tabella si da' come
   primo segmento (altezza/giri 0, diametro, passo): AddVariablePitchHelixFirstPitchAndDiameter fa fallire la chiusura.
"""

import math
import logging
import traceback
from typing import Dict, List, Optional

from ..constants import SwErrors
from .modeling_base import r8_array

logger = logging.getLogger(__name__)

_HELIX_DEF = {"pitch_revolutions": 0, "height_revolutions": 1, "height_pitch": 2, "spiral": 3}


def _integrate_length(r_of, dr_of, dz_of, t_end: float, steps: int = 4000) -> float:
    """Lunghezza di una curva in coordinate cilindriche r(t), z(t), angolo t: integrale di sqrt(r^2 + r'^2 + z'^2) dt
    (Simpson). Serve per confrontare la lunghezza misurata da SolidWorks con quella calcolata."""
    n = steps + (steps % 2)
    h = t_end / n
    s = 0.0
    for i in range(n + 1):
        t = i * h
        f = math.sqrt(r_of(t) ** 2 + dr_of(t) ** 2 + dz_of(t) ** 2)
        s += f * (1 if i in (0, n) else 4 if i % 2 else 2)
    return s * h / 3.0


class CurvesOperations:
    """Mixin del lotto curves."""

    # ------------------------------------------------------------------ utilita'
    def _curve_edges(self, feat) -> list:
        """Spigoli (IEdge) che compongono una curva di riferimento (IReferenceCurve.GetSegments)."""
        try:
            sp = self._com(feat, "GetSpecificFeature2")
            return [e for e in (self._com(sp, "GetSegments") or []) if e is not None]
        except Exception:
            return []

    def _edge_end_points(self, edge):
        """(inizio, fine) di uno spigolo in metri: dai vertici, oppure valutando la curva ai parametri estremi."""
        cv = self._com(edge, "GetCurve")
        prm = self._com(edge, "GetCurveParams2")
        pts = []
        for vname, t in (("GetStartVertex", prm[6]), ("GetEndVertex", prm[7])):
            p = None
            try:
                v = self._com(edge, vname)
                if v is not None:
                    p = list(self._com(v, "GetPoint"))[:3]
            except Exception:
                p = None
            if p is None:
                p = list(cv.Evaluate2(t, 0))[:3]
            pts.append([float(c) for c in p])
        return pts[0], pts[1]

    def _curve_summary(self, feat, unit: str = None) -> Dict:
        """Misura di una curva di riferimento: numero di spigoli, lunghezza totale, punto iniziale e finale (in `unit`)."""
        edges = self._curve_edges(feat)
        info = {"segments": len(edges)}
        if not edges:
            return info
        total, first, last = 0.0, None, None
        for e in edges:
            try:
                cv = self._com(e, "GetCurve")
                prm = self._com(e, "GetCurveParams2")
                total += float(cv.GetLength3(prm[6], prm[7]))
                a, b = self._edge_end_points(e)
                if first is None:
                    first = a
                last = b
            except Exception as ex:
                logger.debug(f"_curve_summary: {ex}")
        info["length"] = round(self._from_m(total, unit), 5)
        info["length_unit"] = self._unit_name(unit)
        if first is not None:
            info["start_point"] = [round(self._from_m(c, unit), 5) for c in first]
            info["end_point"] = [round(self._from_m(c, unit), 5) for c in last]
        pts = self._curve_sample(feat, unit)
        if len(pts) >= 3:
            info["mid_point"] = pts[len(pts) // 2]       # punto intermedio (tassellazione): serve per le verifiche di chiusura/forma
        return info

    def _handedness(self, feat) -> Optional[str]:
        """'right' | 'left': verso d'avvolgimento dell'elica rispetto alla direzione di avanzamento (inizio -> fine)."""
        pts = self._curve_sample(feat, "mm", chord_mm=1.0)
        if len(pts) < 4:
            return None
        t1 = [b - a for a, b in zip(pts[0], pts[1])]
        t2 = [b - a for a, b in zip(pts[1], pts[2])]
        adv = [b - a for a, b in zip(pts[0], pts[-1])]
        cr = [t1[1] * t2[2] - t1[2] * t2[1], t1[2] * t2[0] - t1[0] * t2[2], t1[0] * t2[1] - t1[1] * t2[0]]
        d = sum(c * a for c, a in zip(cr, adv))
        return None if abs(d) < 1e-12 else ("right" if d > 0 else "left")

    def _curve_sample(self, feat, unit: str = None, chord_mm: float = 0.2) -> List[List[float]]:
        """Punti (tassellazione dello spigolo, passo ~chord_mm) lungo la curva, in `unit`: servono per le verifiche. Piu' spigoli
        = punti in sequenza. (ICurve.Evaluate2 non e' affidabile fuori dall'elica: i parametri non coincidono con lo spigolo.)"""
        out = []
        for e in self._curve_edges(feat):
            try:
                cv = self._com(e, "GetCurve")
                a, b = self._edge_end_points(e)
                tol = chord_mm / 1000.0
                raw = cv.GetTessPts(tol, tol, r8_array(a), r8_array(b))
                raw = list(raw or [])
                for i in range(0, len(raw) - 2, 3):
                    out.append([round(self._from_m(float(c), unit), 5) for c in raw[i:i + 3]])
            except Exception as ex:
                logger.debug(f"_curve_sample: {ex}")
        return out

    def _curve_distance(self, feat, point_m) -> Optional[float]:
        """Distanza minima (m) fra un punto (m) e la curva (ISpigolo.GetClosestPointOn); None se non misurabile."""
        best = None
        for e in self._curve_edges(feat):
            try:
                q = e.GetClosestPointOn(point_m[0], point_m[1], point_m[2])
                d = math.dist(list(q)[:3], point_m)
                best = d if best is None else min(best, d)
            except Exception:
                continue
        return best

    def _rebuild_error(self, feat) -> int:
        try:
            code = feat.GetErrorCode2
            code = code[0] if isinstance(code, tuple) else code
            return int(code or 0)
        except Exception:
            return 0

    def _sketch_circle_radius(self, doc, sketch_name: str) -> Optional[float]:
        """Raggio (m) del primo cerchio/arco dello schizzo `sketch_name`; None se non c'e'."""
        for seg in self._sketch_segments_of(doc, sketch_name):
            try:
                if int(self._com(seg, "GetType")) == 1:
                    return float(self._com(seg, "GetRadius"))
            except Exception:
                continue
        return None

    def _select_sketch_for_curve(self, doc, sketch: Optional[str]):
        """Chiude lo schizzo attivo, risolve il nome e lo seleziona (mark 0). -> (nome, errore|None)."""
        name, err = self._resolve_sketch(doc, sketch)
        if err:
            return None, err
        doc.ClearSelection2(True)
        if not self._select_feature(doc, name, False, 0):
            return None, self._result(False, f"Schizzo '{name}' non selezionabile.", SwErrors.swSelectionError)
        return name, None

    def _new_curve_feature(self, doc, before: List[str], types=("Helix", "RefCurve", "CurveInFile", "CompositeCurve",
                                                                "ProjectionCurve", "SplitLine", "CurveThroughPoints")):
        """Prima feature nuova non-schizzo creata dopo `before`: (feature, voce di _new_features, elenco)."""
        new = self._new_features(doc, before)
        cand = [x for x in new if x["type"] != "ProfileFeature"] or new
        if not cand:
            return None, None, new
        pick = next((x for x in cand if x["type"] in types), cand[0])
        return self._find_feature(doc, pick["name"]), pick, new

    # ------------------------------------------------------------------ 1. elica / spirale
    def create_helix(self, sketch: str = None, definition: str = "pitch_revolutions", pitch: float = None,
                     height: float = None, revolutions: float = None, clockwise: bool = True,
                     reverse_direction: bool = False, start_angle: float = 0.0, taper_angle: float = 0.0,
                     taper_outward: bool = True, unit: str = None) -> Dict:
        """Elica o spirale a partire da un cerchio di schizzo (IModelDoc2.InsertHelix)."""
        try:
            doc, err = self._part()
            if err:
                return err
            definition = (definition or "pitch_revolutions").lower().replace("-", "_")
            if definition not in _HELIX_DEF:
                return self._result(False, f"definition '{definition}' non valida: {sorted(_HELIX_DEF)}",
                                    SwErrors.swInvalidInput)
            need = {"pitch_revolutions": ("pitch", "revolutions"), "height_revolutions": ("height", "revolutions"),
                    "height_pitch": ("height", "pitch"), "spiral": ("pitch", "revolutions")}[definition]
            vals = {"pitch": pitch, "height": height, "revolutions": revolutions}
            for k in need:
                if vals[k] is None or float(vals[k]) <= 0:
                    return self._result(False, f"Con definition={definition} serve {k} > 0 "
                                        f"(pitch/height nell'unita' scelta, revolutions = numero di giri).",
                                        SwErrors.swInvalidInput)
            taper = float(taper_angle or 0.0)
            if abs(taper) >= 89:
                return self._result(False, "taper_angle deve essere fra -89 e 89 gradi.", SwErrors.swInvalidInput)
            if taper and definition == "spiral":
                return self._result(False, "La conicita' non si applica alla spirale (definition=spiral).",
                                    SwErrors.swInvalidInput)
            name, err = self._select_sketch_for_curve(doc, sketch)
            if err:
                return err
            radius = self._sketch_circle_radius(doc, name)
            h_m = self._mmu(float(height), unit) if height is not None else 0.0
            p_m = self._mmu(float(pitch), unit) if pitch is not None else 0.0
            rev = float(revolutions) if revolutions is not None else 0.0
            before = self._names(doc)
            try:
                doc.InsertHelix(bool(reverse_direction), bool(clockwise), bool(taper), bool(taper_outward and taper),
                                _HELIX_DEF[definition], h_m, p_m, rev, math.radians(abs(taper)),
                                math.radians(float(start_angle or 0.0)))
            except Exception as e:
                return self._result(False, f"InsertHelix fallito: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            feat, pick, new = self._new_curve_feature(doc, before)
            if feat is None:
                hint = ("Una spirale verso l'interno (reverse_direction=true) non puo' avere un raggio che diventa "
                        "negativo: raggio del cerchio > passo * giri. " if definition == "spiral" and reverse_direction
                        else "")
                return self._result(False, "L'elica non e' stata creata (SolidWorks non ha prodotto nessuna feature). "
                                    + hint + f"Lo schizzo '{name}' deve contenere un cerchio.", SwErrors.swFeatureError)
            data = {"feature": pick["name"], "feature_type": pick["type"], "sketch": name, "definition": definition,
                    "new_features": new}
            try:
                d = self._com(feat, "GetDefinition")
                data.update({"pitch": round(self._from_m(float(d.Pitch), unit), 5),
                             "height": round(self._from_m(float(d.Height), unit), 5),
                             "revolutions": round(float(d.Revolution), 5)})
                if definition != "spiral":
                    # per le definizioni a altezza il passo/giri riletti sono quelli risolti da SolidWorks
                    pass
            except Exception:
                pass
            data.update(self._curve_summary(feat, unit))
            if definition != "spiral":
                data["handedness"] = self._handedness(feat)
            err_code = self._rebuild_error(feat)
            if err_code:
                data["rebuild_error_code"] = err_code
            # lunghezza calcolata (confronto con quella misurata)
            if radius:
                try:
                    p_res = self._mmu(data["pitch"], unit) if data.get("pitch") else p_m
                    rev_res = data.get("revolutions") or rev
                    t_end = 2 * math.pi * rev_res
                    b = p_res / (2 * math.pi)
                    if definition == "spiral":
                        sgn = -1.0 if reverse_direction else 1.0
                        calc = _integrate_length(lambda t: radius + sgn * b * t, lambda t: sgn * b, lambda t: 0.0, t_end)
                    else:
                        k = (math.tan(math.radians(abs(taper))) * (1 if taper_outward else -1)) if taper else 0.0
                        calc = _integrate_length(lambda t: radius + k * b * t, lambda t: k * b, lambda t: b, t_end)
                    data["radius"] = round(self._from_m(radius, unit), 5)
                    data["expected_length"] = round(self._from_m(calc, unit), 5)
                    if data.get("length"):
                        data["length_error_percent"] = round(abs(data["length"] - data["expected_length"])
                                                             / data["expected_length"] * 100, 4)
                except Exception as e:
                    logger.debug(f"create_helix: lunghezza attesa: {e}")
            return self._result(True, f"Elica creata: {pick['name']} (lunghezza {data.get('length')} {self._unit_name(unit)}, "
                                f"{data.get('revolutions')} giri)", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"create_helix: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ 2. elica a passo variabile
    def create_variable_pitch_helix(self, sketch: str = None, definition: str = "pitch_revolutions", segments: list = None,
                                    start_pitch: float = None, start_diameter: float = None, clockwise: bool = True,
                                    reverse_direction: bool = False, start_angle: float = 0.0, unit: str = None) -> Dict:
        """Elica a passo (e diametro) variabile: tabella di segmenti, ciascuno con passo/diametro FINALI (variazione lineare)."""
        try:
            doc, err = self._part()
            if err:
                return err
            definition = (definition or "pitch_revolutions").lower().replace("-", "_")
            if definition not in ("pitch_revolutions", "height_pitch"):
                return self._result(False, "definition: pitch_revolutions | height_pitch.", SwErrors.swInvalidInput)
            if not segments or not isinstance(segments, list):
                return self._result(False, 'Serve segments, es. [{"revolutions":2,"pitch":4},{"revolutions":1,"pitch":8,"diameter":30}].',
                                    SwErrors.swInvalidInput)
            key = "revolutions" if definition == "pitch_revolutions" else "height"
            name, err = self._select_sketch_for_curve(doc, sketch)
            if err:
                return err
            radius = self._sketch_circle_radius(doc, name)
            d0 = self._mmu(float(start_diameter), unit) if start_diameter else (2 * radius if radius else None)
            if d0 is None:
                return self._result(False, "Diametro iniziale non deducibile dallo schizzo: passa start_diameter.",
                                    SwErrors.swInvalidInput)
            rows = []      # (cumulativo giri | altezza (m), diametro (m), passo (m))
            cum = 0.0
            p_prev, d_prev = None, d0
            for i, s in enumerate(segments):
                if not isinstance(s, dict) or s.get(key) is None or float(s[key]) <= 0 or s.get("pitch") is None:
                    return self._result(False, f"Segmento {i}: servono '{key}' > 0 e 'pitch' > 0 (oggetto JSON).",
                                        SwErrors.swInvalidInput)
                p = self._mmu(float(s["pitch"]), unit)
                if p <= 0:
                    return self._result(False, f"Segmento {i}: pitch deve essere > 0.", SwErrors.swInvalidInput)
                if p_prev is None:
                    p_prev = self._mmu(float(start_pitch), unit) if start_pitch else p
                    rows.append((0.0, d0, p_prev))
                dseg = self._mmu(float(s["diameter"]), unit) if s.get("diameter") else d_prev
                cum += float(s[key]) if key == "revolutions" else self._mmu(float(s[key]), unit)
                rows.append((cum, dseg, p))
                p_prev, d_prev = p, dseg
            fm = doc.FeatureManager
            before = self._names(doc)
            try:
                ok = fm.InsertVariablePitchHelix(bool(reverse_direction), bool(clockwise),
                                                 0 if definition == "pitch_revolutions" else 2,
                                                 math.radians(float(start_angle or 0.0)))
                if not ok:
                    return self._result(False, "InsertVariablePitchHelix ha rifiutato la selezione (serve uno schizzo con un cerchio).",
                                        SwErrors.swSelectionError)
                for c, dia, p in rows:
                    fm.AddVariablePitchHelixSegment(c, dia, p)
                fm.EndVariablePitchHelix       # proprieta' in late binding: la lettura chiude la feature
            except Exception as e:
                return self._result(False, f"Elica a passo variabile fallita: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            feat, pick, new = self._new_curve_feature(doc, before)
            if feat is None:
                return self._result(False, "L'elica a passo variabile non e' stata creata: controlla segmenti (passi e diametri "
                                    "positivi) e che lo schizzo contenga un cerchio.", SwErrors.swFeatureError)
            data = {"feature": pick["name"], "feature_type": pick["type"], "sketch": name, "definition": definition,
                    "segments_count": len(segments), "new_features": new}
            data.update(self._curve_summary(feat, unit))
            # lunghezza attesa: passo lineare nell'angolo, diametro lineare nell'altezza, in ogni segmento
            try:
                total = 0.0
                z_tot = 0.0
                for (c0, d_a, p_a), (c1, d_b, p_b) in zip(rows[:-1], rows[1:]):
                    rev = (c1 - c0) if definition == "pitch_revolutions" else 2 * (c1 - c0) / (p_a + p_b)
                    t_end = 2 * math.pi * rev
                    q = (p_b - p_a) / t_end / (2 * math.pi)                  # dz/dt = p_a/2pi + q t (passo lineare nell'angolo)
                    dz = rev * (p_a + p_b) / 2
                    k = ((d_b - d_a) / 2) / dz                               # il raggio varia linearmente con l'ALTEZZA (misurato)
                    r0, p0 = d_a / 2, p_a
                    total += _integrate_length(lambda t, r0=r0, k=k, p0=p0, q=q: r0 + k * (p0 * t / (2 * math.pi) + q * t * t / 2),
                                               lambda t, k=k, p0=p0, q=q: k * (p0 / (2 * math.pi) + q * t),
                                               lambda t, p0=p0, q=q: p0 / (2 * math.pi) + q * t, t_end)
                    z_tot += rev * (p_a + p_b) / 2
                data["expected_length"] = round(self._from_m(total, unit), 5)
                data["expected_height"] = round(self._from_m(z_tot, unit), 5)
                if data.get("length"):
                    data["length_error_percent"] = round(abs(data["length"] - data["expected_length"])
                                                         / data["expected_length"] * 100, 4)
            except Exception as e:
                logger.debug(f"create_variable_pitch_helix: lunghezza attesa: {e}")
            return self._result(True, f"Elica a passo variabile creata: {pick['name']} (lunghezza {data.get('length')} "
                                f"{self._unit_name(unit)})", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"create_variable_pitch_helix: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ 3. curva proiettata
    def project_curve(self, sketch: str = None, face_points: list = None, target_sketch: str = None, reverse: bool = False,
                      both_directions: bool = False, unit: str = None) -> Dict:
        """Curva proiettata: schizzo su una o piu' facce (face_points) oppure schizzo su schizzo (target_sketch)."""
        try:
            doc, err = self._part()
            if err:
                return err
            if bool(face_points) == bool(target_sketch):
                return self._result(False, "Indica ESATTAMENTE una fra face_points (schizzo su facce) e target_sketch "
                                    "(schizzo su schizzo).", SwErrors.swInvalidInput)
            name, err = self._select_sketch_for_curve(doc, sketch)
            if err:
                return err
            data = {"sketch": name, "reverse": bool(reverse), "new_features": []}
            curves = []
            for k, rev in enumerate([bool(reverse)] + ([not reverse] if both_directions else [])):
                # la selezione va rifatta a ogni proiezione (InsertProjectedSketch2 la consuma)
                doc.ClearSelection2(True)
                if not self._select_feature(doc, name, False, 0):
                    return self._result(False, f"Schizzo '{name}' non selezionabile.", SwErrors.swSelectionError)
                if target_sketch:
                    if target_sketch == name or not self._select_feature(doc, target_sketch, True, 0):
                        return self._result(False, f"target_sketch '{target_sketch}' non trovato o uguale allo schizzo da "
                                            "proiettare.", SwErrors.swSelectionError)
                else:
                    ok, msg = self._select_points(doc, "face", face_points, unit, mark=0, append_first=True)
                    if not ok:
                        return self._result(False, f"Faccia non selezionata: {msg}", SwErrors.swSelectionError)
                before = self._names(doc)
                try:
                    doc.InsertProjectedSketch2(1 if rev else 0)
                except Exception as e:
                    return self._result(False, f"InsertProjectedSketch2 fallito: {e}", SwErrors.swFeatureError)
                doc.ClearSelection2(True)
                feat, pick, new = self._new_curve_feature(doc, before)
                if feat is None:
                    if k == 0:
                        return self._result(False, "La proiezione non ha prodotto nessuna curva: lo schizzo deve proiettarsi "
                                            "(in direzione normale al suo piano) sulle facce indicate; prova reverse=true.",
                                            SwErrors.swFeatureError)
                    data["second_direction_error"] = "nessuna curva nel verso opposto"
                    continue
                data["new_features"] += new
                curves.append((pick, feat))
            pick, feat = curves[0]
            data.update({"feature": pick["name"], "feature_type": pick["type"]})
            data.update(self._curve_summary(feat, unit))
            if len(curves) > 1:
                # SolidWorks non permette di cambiare Bidirectional dall'API (ModifyDefinition solleva un'eccezione):
                # il verso opposto e' una seconda curva
                data["both_directions"] = True
                data["other_direction_feature"] = curves[1][0]["name"]
                data["other_direction"] = self._curve_summary(curves[1][1], unit)
            code = self._rebuild_error(feat)
            if code:
                data["rebuild_error_code"] = code
            return self._result(True, f"Curva proiettata: {pick['name']} ({data.get('segments')} segmenti, lunghezza "
                                f"{data.get('length')} {self._unit_name(unit)})", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"project_curve: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ 5. curva composita
    def composite_curve(self, edge_points: list = None, sketch_entities: list = None, unit: str = None) -> Dict:
        """Curva composita: unisce spigoli del modello (edge_points) e/o entita' di schizzi (sketch_entities)."""
        try:
            doc, err = self._part()
            if err:
                return err
            if not edge_points and not sketch_entities:
                return self._result(False, "Servono edge_points e/o sketch_entities (almeno 2 entita' contigue in totale).",
                                    SwErrors.swInvalidInput)
            self._exit_sketch(doc)
            doc.ClearSelection2(True)
            count = 0
            for pt in (edge_points or []):
                ok, info = self._select_point(doc, "edge", pt, unit, append=count > 0, mark=1)
                if not ok:
                    return self._result(False, f"Spigolo non selezionato: {info.get('error')}", SwErrors.swSelectionError)
                count += 1
            for item in (sketch_entities or []):
                if not isinstance(item, dict) or not item.get("sketch") or item.get("entity") is None:
                    return self._result(False, 'Ogni voce di sketch_entities e\' {"sketch": nome, "entity": id | "@x,y"}.',
                                        SwErrors.swInvalidInput)
                f = self._find_feature(doc, item["sketch"])
                if f is None:
                    return self._result(False, f"Schizzo '{item['sketch']}' non trovato.", SwErrors.swSelectionError)
                sk = self._com(f, "GetSpecificFeature2")
                obj, desc, e = self._resolve_entity(doc, sk, item["entity"], unit)
                if e or obj in (None, "origin"):
                    return self._result(False, f"Entita' di schizzo non valida: {e or item['entity']}", SwErrors.swSelectionError)
                if not obj.Select4(count > 0, self._sd(doc, 1)):
                    return self._result(False, f"Selezione di '{desc}' in '{item['sketch']}' rifiutata.", SwErrors.swSelectionError)
                count += 1
            before = self._names(doc)
            try:
                doc.InsertCompositeCurve      # proprieta' in late binding: la lettura esegue il comando
            except Exception as e:
                return self._result(False, f"InsertCompositeCurve fallito: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            feat, pick, new = self._new_curve_feature(doc, before)
            if feat is None:
                return self._result(False, "La curva composita non e' stata creata: le entita' devono essere contigue "
                                    "(estremi coincidenti) e non formare diramazioni.", SwErrors.swFeatureError)
            data = {"feature": pick["name"], "feature_type": pick["type"], "entities": count, "new_features": new}
            data.update(self._curve_summary(feat, unit))
            code = self._rebuild_error(feat)
            if code:
                data["rebuild_error_code"] = code
            return self._result(True, f"Curva composita: {pick['name']} ({count} entita', lunghezza {data.get('length')} "
                                f"{self._unit_name(unit)})", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"composite_curve: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ 6. curva per punti
    _LENGTH_UNIT_M = {0: 0.001, 1: 0.01, 2: 1.0, 3: 0.0254, 4: 0.3048, 6: 1e-10, 7: 1e-9}     # swLengthUnit_e -> metri

    def _doc_length_unit_m(self, doc) -> float:
        """Metri per unita' di lunghezza del documento (il file dei punti e' letto in queste unita')."""
        try:
            return self._LENGTH_UNIT_M.get(int(doc.Extension.GetUserPreferenceInteger(47, 0)), 0.001)
        except Exception:
            return 0.001

    def curve_through_points(self, points: list = None, vertex_points: list = None, closed: bool = False,
                             unit: str = None) -> Dict:
        """Curva (spline) per punti XYZ dati, e/o per vertici del modello (vertex_points)."""
        import os
        import tempfile
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            pts_m = []
            for p in (points or []):
                try:
                    q = [self._mmu(float(c), unit) for c in p]
                    assert len(q) == 3
                except Exception:
                    return self._result(False, f"Punto non valido: {p} (serve [x,y,z]).", SwErrors.swInvalidInput)
                pts_m.append(q)
            for p in (vertex_points or []):
                v, d = self._find_entity(doc, "vertex", [self._mmu(float(c), unit) for c in p], 0.0005)
                if v is None:
                    return self._result(False, f"Nessun vertice entro 0,5 mm da {list(p)}.", SwErrors.swSelectionError)
                pts_m.append([float(c) for c in self._com(v, "GetPoint")])
            if len(pts_m) < 2:
                return self._result(False, "Servono almeno 2 punti (points e/o vertex_points).", SwErrors.swInvalidInput)
            if closed and len(pts_m) < 3:
                return self._result(False, "Una curva chiusa richiede almeno 3 punti.", SwErrors.swInvalidInput)
            seq = pts_m + ([pts_m[0]] if closed else [])
            k = self._doc_length_unit_m(doc)
            fd, path = tempfile.mkstemp(suffix=".txt", prefix="swcurve_")
            try:
                with os.fdopen(fd, "w") as fh:
                    for q in seq:
                        fh.write("%.9f %.9f %.9f\n" % tuple(c / k for c in q))
                doc.ClearSelection2(True)
                before = self._names(doc)
                try:
                    doc.InsertCurveFile(path)
                except Exception as e:
                    return self._result(False, f"InsertCurveFile fallito: {e}", SwErrors.swFeatureError)
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass
            feat, pick, new = self._new_curve_feature(doc, before)
            if feat is None:
                return self._result(False, "La curva non e' stata creata: controlla che i punti siano distinti e non "
                                    "tutti allineati/duplicati.", SwErrors.swFeatureError)
            data = {"feature": pick["name"], "feature_type": pick["type"], "points": len(pts_m), "closed": bool(closed),
                    "new_features": new}
            data.update(self._curve_summary(feat, unit))
            devs = [self._curve_distance(feat, q) for q in pts_m]
            devs = [d for d in devs if d is not None]
            if devs:
                data["max_point_deviation"] = round(self._from_m(max(devs), unit), 6)    # distanza massima dei punti dati dalla curva
            code = self._rebuild_error(feat)
            if code:
                data["rebuild_error_code"] = code
            return self._result(True, f"Curva per {len(pts_m)} punti: {pick['name']} (lunghezza {data.get('length')} "
                                f"{self._unit_name(unit)})", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"curve_through_points: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ 4. linea di divisione
    def _face_areas_m2(self, doc) -> List[float]:
        out = []
        for f in self._body_entities(doc, "face"):
            try:
                out.append(float(self._com(f, "GetArea")))
            except Exception:
                pass
        return out

    def split_line(self, mode: str = "projection", sketch: str = None, face_points: list = None, direction=None,
                   cutter=None, unit: str = None) -> Dict:
        """Linea di divisione (Split Line) su facce: per proiezione di uno schizzo, per silhouette o per intersezione."""
        try:
            doc, err = self._part()
            if err:
                return err
            mode = (mode or "projection").lower()
            if mode not in ("projection", "silhouette", "intersection"):
                return self._result(False, "mode: projection | silhouette | intersection.", SwErrors.swInvalidInput)
            if not face_points:
                return self._result(False, "face_points obbligatorio: un punto [x,y,z] SU ogni faccia da dividere "
                                    "(list_entities).", SwErrors.swInvalidInput)
            self._exit_sketch(doc)
            doc.ClearSelection2(True)
            # Marks misurati (SW 2026): proiezione = schizzo mark 4 + facce mark 1; silhouette = piano di direzione mark 2 +
            # facce mark 1; (intersezione = strumento mark 2 + facce mark 1: vedi sotto)
            label = {"projection": "Linea di divisione per proiezione", "silhouette": "Linea di divisione per silhouette",
                     "intersection": "Linea di divisione per intersezione"}[mode]
            if mode == "projection":
                name, err = self._resolve_sketch(doc, sketch)
                if err:
                    return err
                if not self._select_feature(doc, name, False, 4):
                    return self._result(False, f"Schizzo '{name}' non selezionabile.", SwErrors.swSelectionError)
            else:
                name = None
                spec = direction if mode == "silhouette" else cutter
                if spec is None:
                    return self._result(False, ("direction" if mode == "silhouette" else "cutter") +
                                        " obbligatorio: {\"plane\": nome} (piano standard o di riferimento) o {\"face\": [x,y,z]}.",
                                        SwErrors.swInvalidInput)
                ok, why = self._select_edge_or_axis(doc, spec, unit, mark=2, append=False)
                if not ok:
                    return self._result(False, f"Direzione/strumento non selezionato: {why}", SwErrors.swSelectionError)
            ok, why = self._select_points(doc, "face", face_points, unit, mark=1, append_first=True)
            if not ok:
                return self._result(False, f"Faccia non selezionata: {why}", SwErrors.swSelectionError)
            areas0 = self._face_areas_m2(doc)
            before = self._names(doc)
            try:
                if mode == "projection":
                    doc.InsertSplitLineProject(False, False)      # IsDirectional=False: proietta in entrambi i versi (misurato)
                elif mode == "silhouette":
                    doc.InsertSplitLineSil()
                else:
                    doc.FeatureManager.InsertSplitLineIntersect(0)
            except Exception as e:
                return self._result(False, f"{label} fallita: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            areas1 = self._face_areas_m2(doc)
            new = self._new_features(doc, before)
            if len(areas1) <= len(areas0) and not [x for x in new if x["type"] != "ProfileFeature"]:
                hint = ""
                if mode == "intersection":
                    hint = (" Limite noto: con SolidWorks 2026 InsertSplitLineIntersect non crea la feature con un piano come "
                            "strumento (provati tutti i mark 1/2/4/8 e le opzioni 0-3, anche con il corpo come bersaglio).")
                elif mode == "projection":
                    hint = " Lo schizzo deve proiettarsi sulle facce nella direzione normale al suo piano (in entrambi i versi)."
                return self._result(False, f"{label}: SolidWorks non ha creato nessuna feature (facce {len(areas0)} -> "
                                    f"{len(areas1)})." + hint, SwErrors.swFeatureError)
            # facce nuove = aree presenti dopo e non prima (multiinsieme)
            pool = list(areas0)
            fresh = []
            for a in areas1:
                for i, b in enumerate(pool):
                    if abs(a - b) <= 1e-9 + 1e-7 * abs(b):
                        pool.pop(i)
                        break
                else:
                    fresh.append(a)
            f_name = next((x for x in new if x["type"] != "ProfileFeature"), None)
            data = {"mode": mode, "sketch": name, "faces_before": len(areas0), "faces_after": len(areas1),
                    "new_face_areas": sorted(round(a * 1e6, 4) for a in fresh), "area_unit": "mm2", "new_features": new}
            if f_name:
                data["feature"] = f_name["name"]
                data["feature_type"] = f_name["type"]
                f2 = self._find_feature(doc, f_name["name"])
                code = self._rebuild_error(f2) if f2 is not None else 0
                if code:
                    data["rebuild_error_code"] = code
            return self._result(True, f"{label}: {data.get('feature')} (facce {len(areas0)} -> {len(areas1)})",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"split_line: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)
