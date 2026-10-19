"""
Lotto STAMPI (analisi dei sottosquadri per la direzione di estrazione) (mixin).
Schemi in tools_ext/mold.py. I metodi usano gli helper di ModelingBase/ModelingOperations tramite self
(_part, _bodies, _surface_kind, _from_m, _result...).

Trappole API scoperte (SW 2026, laboratorio mld, vedi scripts_tmp/notes_mold.md):
 - InsertMoldPartingLine / InsertMoldShutOffSurface non creano nessuna feature in questa istanza (la prima restituisce
   None senza errore, la seconda 'Impossibile trovare membro'); nel registro non c'e' nessun add-in Mold Tools.
   Per questo i tool linea/superficie di divisione, chiusura e divisione maschio/matrice non sono esposti.
 - Il sottosquadro e' calcolato in Python con RayIntersections (come lo spessore): una faccia e' in sottosquadro se il
   raggio che esce dalla faccia dal suo lato di estrazione (verso +direzione se la faccia guarda +direzione, verso
   -direzione altrimenti) incontra il corpo. Le pareti parallele alla direzione non sono mai in sottosquadro.
"""

import logging
import math
import traceback
from typing import Dict, List, Optional

from ..constants import SwErrors
from .modeling_base import r8_array, disp_array

logger = logging.getLogger(__name__)

_RAY_MIN_T = 1e-4          # m: intersezioni a meno di 0,1 mm dal punto di partenza sono la faccia stessa (ignorate)
_RAY_PERP = 1e-5           # m: tolleranza con cui un punto di intersezione deve stare sul raggio
_PARALLEL_COS = 0.05       # |n.d| sotto questa soglia = parete parallela alla direzione (non puo' essere in sottosquadro)
_MAX_SAMPLES = 1500        # campioni (triangoli) massimi per l'analisi
_MAX_LISTED = 50           # facce in sottosquadro elencate nei dati
_DEFAULT_DIRECTION = [0.0, 0.0, 1.0]


def _unit_vec(v) -> Optional[List[float]]:
    n = math.sqrt(sum(float(x) * float(x) for x in v))
    if n < 1e-12:
        return None
    return [float(x) / n for x in v]


def _dot(a, b) -> float:
    return sum(float(x) * float(y) for x, y in zip(a, b))


def _direction(spec) -> Optional[List[float]]:
    """'+X', '-Y', 'z' (stringa) o [dx,dy,dz] -> vettore unitario; None se non valido."""
    if spec is None:
        return list(_DEFAULT_DIRECTION)
    if isinstance(spec, str):
        s = spec.strip().lower().replace(" ", "")
        sign = -1.0 if s.startswith("-") else 1.0
        idx = {"x": 0, "y": 1, "z": 2}.get(s.lstrip("+-"))
        if idx is None:
            return None
        v = [0.0, 0.0, 0.0]
        v[idx] = sign
        return v
    if isinstance(spec, (list, tuple)) and len(spec) == 3:
        try:
            return _unit_vec([float(x) for x in spec])
        except Exception:
            return None
    return None


class MoldOperations:
    """Mixin del lotto mold."""

    def undercut_analysis(self, direction=None, unit: str = None) -> Dict:
        """Facce in sottosquadro rispetto alla direzione di estrazione (raggi con RayIntersections su campioni tessellati)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            d = _direction(direction)
            if d is None:
                return self._result(False, f"direction non valida: {direction!r}. Usa '+X', '-Y', '+Z'... o [dx,dy,dz] "
                                    "con vettore non nullo.", SwErrors.swInvalidInput)
            bodies = self._bodies(doc)
            if not bodies:
                return self._result(False, "Nessun corpo solido nel pezzo.", SwErrors.swSelectionError)
            cands, faces_info, no_tess, parallel, faces_total = [], {}, 0, 0, 0
            for bi, body in enumerate(bodies):
                for fi, face in enumerate(list(self._com(body, "GetFaces") or [])):
                    faces_total += 1
                    tri = face.GetTessTriangles(False)
                    if tri is None:
                        no_tess += 1
                        continue
                    v = [float(x) * 0.001 for x in tri]     # GetTessTriangles e' in mm (come thickness_analysis)
                    nv = len(v) // 3
                    plane = self._surface_kind(face) == "plane"
                    fn = None
                    tnv = []
                    if plane:
                        fn = _unit_vec([float(x) for x in self._com(face, "Normal")])
                    else:
                        tn = self._com(face, "GetTessNorms")
                        tnv = [float(x) for x in tn] if tn is not None else []
                        if len(tnv) < 3 * nv:
                            no_tess += 1
                            continue
                    for t in range(nv // 3):
                        ids = [3 * t + k for k in range(3)]
                        c = [sum(v[3 * i + j] for i in ids) / 3.0 for j in range(3)]
                        if plane:
                            n = fn
                        else:
                            n = _unit_vec([sum(tnv[3 * i + j] for i in ids) for j in range(3)])
                        if n is None:
                            continue
                        nd = _dot(n, d)
                        if abs(nd) < _PARALLEL_COS:
                            parallel += 1
                            continue
                        side = 1.0 if nd > 0 else -1.0     # verso del raggio: lato di estrazione della faccia
                        u = [side * x for x in d]
                        cands.append((bi, fi, c, u))
                        if (bi, fi) not in faces_info:
                            faces_info[(bi, fi)] = {"face": face, "centre": c, "flagged": 0, "samples": 0}
            if not cands:
                return self._result(True, "Nessuna faccia non parallela alla direzione: nessun sottosquadro.",
                                    SwErrors.swSuccess, {"undercut_faces": 0, "faces_total": faces_total,
                                                         "parallel_samples": parallel})
            if len(cands) > _MAX_SAMPLES:
                step = len(cands) / float(_MAX_SAMPLES)
                cands = [cands[int(i * step)] for i in range(_MAX_SAMPLES)]
            pts, vec = [], []
            for _bi, _fi, c, u in cands:
                pts += c
                vec += u
            n_hits = doc.Extension.RayIntersections(disp_array(bodies), r8_array(pts), r8_array(vec), 0, 0.0, 0.0, False)
            raw = doc.GetRayIntersectionsPoints
            hits = [float(x) for x in raw] if raw else []
            hpts = [(hits[6 * k + 3], hits[6 * k + 4], hits[6 * k + 5]) for k in range(len(hits) // 6)]
            for bi, fi, o, u in cands:
                blocked = False
                for h in hpts:
                    w = [h[i] - o[i] for i in range(3)]
                    tt = _dot(w, u)
                    if tt < _RAY_MIN_T:
                        continue
                    perp = math.sqrt(max(0.0, _dot(w, w) - tt * tt))
                    if perp <= _RAY_PERP:
                        blocked = True
                        break
                info = faces_info[(bi, fi)]
                info["samples"] += 1
                if blocked:
                    info["flagged"] += 1
            under = [(k, i) for k, i in faces_info.items() if i["flagged"] > 0]
            listed = []
            for (bi, fi), i in under[:_MAX_LISTED]:
                try:
                    area = round(float(self._com(i["face"], "GetArea")) * 1e6, 3)
                except Exception:
                    area = None
                listed.append({"body": bi, "face": fi, "area_mm2": area,
                               "centre": [round(self._from_m(x, unit), 4) for x in i["centre"]],
                               "flagged_samples": i["flagged"], "samples": i["samples"]})
            data = {"direction": [round(x, 6) for x in d], "undercut_faces": len(under),
                    "faces_analyzed": len(faces_info), "faces_total": faces_total, "samples": len(cands),
                    "rays_hits": n_hits, "parallel_samples": parallel, "faces_without_tessellation": no_tess,
                    "faces": listed, "unit": self._unit_name(unit)}
            msg = (f"{len(under)} facce in sottosquadro su {len(faces_info)} analizzate (direzione "
                   f"{[round(x, 3) for x in d]}, {len(cands)} campioni)")
            return self._result(True, msg, SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"undercut_analysis: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)
