"""
Lotto ANALISI E RIFERIMENTI (box di delimitazione, centro di massa, riferimenti di accoppiamento, analisi di sformo e spessore,
sezione della vista, schizzo completamente definito) (mixin).
Schemi in tools_ext/analysis.py. I metodi usano gli helper di ModelingBase/ModelingOperations tramite self.

Trappole API scoperte (SW 2026, laboratorio ana, vedi scripts_tmp/notes_analysis.md):
 - InsertCenterOfMass() e InsertGlobalBoundingBox2 creano la feature ma in late binding il ritorno e' None: la chiamata
   puo' sollevare TypeError('NoneType'...) con la feature gia' creata. Si verifica sempre dalle feature nuove.
 - InsertMateReference2: gli argomenti secondo/terziario vanno passati come VARIANT(VT_DISPATCH, None) (con None semplice
   o con Missing dava errore di tipo). La feature risultante ha nome 'NOME-<1>' e tipo PosGroupFolder.
 - Il box di delimitazione lascia uno schizzo ('BoundingBoxProfileFeat') con 12 segmenti: le misure si leggono dagli estremi.
 - CreateSectionViewData e RemoveSectionView sono proprieta' (si leggono con self._com, non si chiamano).
 - IModelDoc2.GetRayIntersectionsPoints e' una proprieta' (tupla piatta: 6 valori per punto, il punto e' ai valori 3..5).
"""

import logging
import math
import traceback
from typing import Dict, List, Optional

import pythoncom
from win32com.client import VARIANT

from ..constants import SwErrors
from .modeling_base import r8_array, disp_array, null_variant

logger = logging.getLogger(__name__)

_MATE_TYPE = {"default": 0, "tangent": 1, "coincident": 2, "concentric": 3, "parallel": 4}   # swMateReferenceType_e
_MATE_ALIGN = {"any": 0, "aligned": 1, "anti_aligned": 2, "closest": 3}                    # swMateReferenceAlignment_e
_BBOX_STATUS = {0: "successo", 1: "nessun corpo valido", 2: "faccia non planare selezionata"}
_RELATIONS_ALL = 1023            # swSketchFullyDefineRelationType_e: somma di tutti i tipi di relazione
_AUTODIM_BASELINE = 1            # swAutodimScheme_e: baseline
_PLACE_ABOVE = 1                 # swAutodimHorizontalPlacement_e: sopra
_PLACE_RIGHT = 1                 # swAutodimVerticalPlacement_e: destra
_FLAT_COS = 0.99999              # |cos| oltre questa soglia = direzioni parallele
_DRAFT_VERTICAL_DEG = 0.01       # |sformo| sotto questa soglia = faccia verticale (nessuno sformo)
_RAY_MIN_T = 1e-4                # m: uscite a meno di 0,1 mm dalla faccia di partenza sono la faccia stessa (ignorate)
_RAY_PERP = 1e-5                 # m: tolleranza con cui un punto di uscita deve stare sul raggio


def _byref_int():
    return VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)


def _feature_call(fn, *args):
    """Chiama un metodo che crea una feature. In late binding la chiamata puo' sollevare errore (com_error 'Impossibile
    trovare membro' o TypeError 'NoneType') anche a feature creata: l'esito vero si legge dopo dalle feature nuove.
    -> (ritorno, testo dell'errore o None)"""
    try:
        return fn(*args), None
    except Exception as e:
        return None, str(e)


def _unit_vec(v) -> Optional[List[float]]:
    n = math.sqrt(sum(float(x) * float(x) for x in v))
    if n < 1e-12:
        return None
    return [float(x) / n for x in v]


def _dot(a, b) -> float:
    return sum(float(x) * float(y) for x, y in zip(a, b))


class AnalysisOperations:
    """Mixin del lotto analysis."""

    # ------------------------------------------------------------------ box di delimitazione
    def _bbox_extent(self, feat) -> List[float]:
        """Dimensioni (m) del box: estremi di tutti i segmenti dello schizzo della feature, asse per asse."""
        sk = self._com(feat, "GetSpecificFeature2")
        segs = self._com(sk, "GetSketchSegments")
        pts = []
        for s in list(segs or []):
            for nm in ("GetStartPoint2", "GetEndPoint2"):
                p = self._com(s, nm)
                pts.append((float(p.X), float(p.Y), float(p.Z)))
        if not pts:
            return []
        return [max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3)]

    def insert_bounding_box(self, best_fit: bool = True, include_surfaces: bool = False, unit: str = None) -> Dict:
        """Box di delimitazione a migliore adattamento di tutti i corpi (InsertGlobalBoundingBox2); misure lette dallo schizzo."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            if not best_fit:
                return self._result(False, "Solo il box a migliore adattamento e' supportato (best_fit=true): il box su piano "
                                    "o su sistema di coordinate richiede altri parametri, non implementati.",
                                    SwErrors.swInvalidInput)
            names0 = self._names(doc)
            st = _byref_int()
            _feature_call(lambda: doc.FeatureManager.InsertGlobalBoundingBox2(1, 0, False, bool(include_surfaces), st))
            code = int(st.value) if st.value is not None else -1
            new = self._new_features(doc, names0)
            new_names = {x["name"] for x in new}
            cand = [(n, t, f) for n, t, f in self._features(doc) if t == "BoundingBoxProfileFeat" and n in new_names]
            if code != 0 or not cand:
                return self._result(False, f"Box non creato: SolidWorks ha risposto {code} "
                                    f"({_BBOX_STATUS.get(code, 'codice sconosciuto')}), feature nuove: {new}",
                                    SwErrors.swFeatureError, {"status": code, "new_features": new})
            name, typ, feat = cand[0]
            ext = self._bbox_extent(feat)
            if len(ext) != 3:
                return self._result(False, f"Box '{name}' creato ma senza segmenti leggibili nello schizzo.",
                                    SwErrors.swFeatureError, {"feature": name})
            xyz = [round(self._from_m(v, unit), 4) for v in ext]
            sizes = sorted(xyz, reverse=True)
            data = {"feature": name, "type": typ, "sizes": sizes, "sizes_xyz": xyz,
                    "unit": self._unit_name(unit), "status": code}
            return self._result(True, f"Box di delimitazione '{name}': {sizes[0]} x {sizes[1]} x {sizes[2]} "
                                f"{self._unit_name(unit)}", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"insert_bounding_box: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ centro di massa
    def insert_center_of_mass(self, unit: str = None) -> Dict:
        """Punto di riferimento del centro di massa (InsertCenterOfMass) e posizione letta dalle proprieta' di massa."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            names0 = self._names(doc)
            existing = [n for n, t, f in self._features(doc) if t in ("CenterOfMass", "CenterOfMassRefPoint")]
            _, cerr = _feature_call(lambda: doc.FeatureManager.InsertCenterOfMass())
            new = self._new_features(doc, names0)
            if not new and existing:
                new = [{"name": existing[0], "type": "gia' presente"}]
            if not new:
                return self._result(False, f"Punto del centro di massa non creato: SolidWorks non ha aggiunto feature ({cerr}).",
                                    SwErrors.swFeatureError, {})
            mp = self._mass_props(doc)
            if mp is None:
                return self._result(False, "Proprieta' di massa non disponibili (serve un solido).", SwErrors.swFeatureError)
            com = [round(self._from_m(float(v), unit), 4) for v in self._com(mp, "CenterOfMass")]
            data = {"center_of_mass": com, "features": new, "unit": self._unit_name(unit)}
            return self._result(True, f"Centro di massa {com} {self._unit_name(unit)} ({new[0]['type']})",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"insert_center_of_mass: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ riferimento di accoppiamento
    def insert_mate_reference(self, name: str, face_point: list, type: str = "coincident",
                              alignment: str = "any", unit: str = None) -> Dict:
        """Riferimento di accoppiamento su una faccia (InsertMateReference2): feature col nome dato, tipo letto dalla feature."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            if not name or not str(name).strip():
                return self._result(False, "Serve un nome per il riferimento.", SwErrors.swInvalidInput)
            tkey = str(type or "coincident").strip().lower()
            if tkey not in _MATE_TYPE:
                return self._result(False, f"type '{type}' non valido: usa default, tangent, coincident, concentric o parallel",
                                    SwErrors.swInvalidInput)
            akey = str(alignment or "any").strip().lower()
            if akey not in _MATE_ALIGN:
                return self._result(False, f"alignment '{alignment}' non valido: usa any, aligned, anti_aligned o closest",
                                    SwErrors.swInvalidInput)
            if not face_point or len(face_point) != 3:
                return self._result(False, "face_point deve essere [x,y,z] (un punto sulla faccia, in `unit`).",
                                    SwErrors.swInvalidInput)
            p = [self._mmu(v, unit) for v in face_point]
            ent, dist = self._find_entity(doc, "face", p, 0.0005)
            if ent is None:
                return self._result(False, f"Nessuna faccia entro 0,5 mm dal punto {face_point} ({self._unit_name(unit)}): "
                                    f"distanza {round(self._from_m(dist, unit), 4)} (list_entities kind=face).",
                                    SwErrors.swSelectionError)
            names0 = self._names(doc)
            _feature_call(lambda: doc.FeatureManager.InsertMateReference2(
                name, ent, _MATE_TYPE[tkey], _MATE_ALIGN[akey], False, null_variant(), 0, 0, False, null_variant(), 0, 0))
            new = self._new_features(doc, names0)
            found = [(n, t) for n, t, f in self._features(doc) if n == name or n.startswith(name + "-")]
            if not found:
                return self._result(False, f"Riferimento '{name}' non trovato dopo la creazione; feature nuove: {new}",
                                    SwErrors.swFeatureError, {"new_features": new})
            fname, ftype = found[0]
            data = {"feature": fname, "type": ftype, "type_option": tkey, "alignment": akey, "new_features": new}
            return self._result(True, f"Riferimento di accoppiamento '{fname}' ({ftype}) su faccia a {face_point}",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"insert_mate_reference: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ sformo
    def _surface_kind(self, face) -> str:
        surf = self._com(face, "GetSurface")
        return self._SURFACE_TYPES.get(int(self._com(surf, "Identity")), "other")

    def _draft_direction(self, doc, direction, unit):
        """-> (vettore unitario, errore). Accetta 'x'|'y'|'z', [dx,dy,dz] o {"face": [x,y,z]} (faccia piana)."""
        if isinstance(direction, str):
            key = direction.strip().lower()
            vec = {"x": [1.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0]}.get(key)
            if vec is None:
                return None, self._result(False, "direction testo non valida: usa x, y o z.", SwErrors.swInvalidInput)
            return vec, None
        if isinstance(direction, dict) and "face" in direction:
            pt = direction["face"]
            if not pt or len(pt) != 3:
                return None, self._result(False, "{\"face\":[x,y,z]}: servono 3 coordinate.", SwErrors.swInvalidInput)
            ent, dist = self._find_entity(doc, "face", [self._mmu(v, unit) for v in pt], 0.0005)
            if ent is None:
                return None, self._result(False, f"Nessuna faccia entro 0,5 mm dal punto {pt}.", SwErrors.swSelectionError)
            if self._surface_kind(ent) != "plane":
                return None, self._result(False, "La direzione da faccia richiede una faccia piana.", SwErrors.swInvalidInput)
            u = _unit_vec([float(v) for v in self._com(ent, "Normal")])
            if u is None:
                return None, self._result(False, "Normale della faccia non valida.", SwErrors.swFeatureError)
            return u, None
        if isinstance(direction, (list, tuple)) and len(direction) == 3:
            u = _unit_vec([float(v) for v in direction])
            if u is None:
                return None, self._result(False, "direction [dx,dy,dz] nulla.", SwErrors.swInvalidInput)
            return u, None
        return None, self._result(False, "direction non valida: 'x', 'y', 'z', [dx,dy,dz] o {\"face\":[x,y,z]}.",
                                  SwErrors.swInvalidInput)

    @staticmethod
    def _draft_class(stype: str, s: float, mina: float) -> Dict:
        if abs(s) < _DRAFT_VERTICAL_DEG:
            cls = "vertical"
        elif abs(s) < mina:
            cls = "below_min"
        elif s > 0:
            cls = "positive"
        else:
            cls = "negative"
        return {"type": stype, "class": cls, "sformo_deg": round(s, 4)}

    def _draft_row(self, face, d, mina: float) -> Dict:
        stype = self._surface_kind(face)
        if stype == "plane":
            u = _unit_vec([float(v) for v in self._com(face, "Normal")])
            c = _dot(u, d)
            if abs(c) > _FLAT_COS:
                return {"type": stype, "class": "flat", "sformo_deg": 90.0}
            s = 90.0 - math.degrees(math.acos(max(-1.0, min(1.0, c))))
            return self._draft_class(stype, s, mina)
        if stype == "cylinder":
            cp = [float(v) for v in self._com(self._com(face, "GetSurface"), "CylinderParams")]
            ax = _unit_vec(cp[3:6])
            if ax is not None and abs(_dot(ax, d)) > _FLAT_COS:
                return {"type": stype, "class": "vertical", "sformo_deg": 0.0}
            return {"type": stype, "class": "not_applicable", "sformo_deg": None}
        if stype == "cone":
            cp = [float(v) for v in self._com(self._com(face, "GetSurface"), "ConeParams")]
            ax = _unit_vec(cp[3:6])
            if ax is None or abs(_dot(ax, d)) <= _FLAT_COS:
                return {"type": stype, "class": "not_applicable", "sformo_deg": None}
            half = cp[7]
            if abs(math.tan(half)) < 1e-12:
                return {"type": stype, "class": "vertical", "sformo_deg": 0.0}
            h = cp[6] / math.tan(half)
            apex = [cp[i] + ax[i] * h for i in range(3)]
            box = self._com(face, "GetBox")
            c = [(box[k] + box[k + 3]) / 2 for k in range(3)]
            q = list(face.GetClosestPointOn(c[0], c[1], c[2]))[:3]
            sign = 1.0 if _dot([apex[i] - q[i] for i in range(3)], d) >= 0 else -1.0
            return self._draft_class(stype, sign * math.degrees(half), mina)
        return {"type": stype, "class": "not_applicable", "sformo_deg": None}

    def draft_analysis(self, direction, min_angle: float = 1.0, unit: str = None) -> Dict:
        """Sformo numerico di ogni faccia rispetto alla direzione di estrazione (gradi); nessun colore."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            d, err = self._draft_direction(doc, direction, unit)
            if err:
                return err
            mina = 1.0 if min_angle is None else float(min_angle)
            if mina < 0:
                return self._result(False, "min_angle negativo: usa gradi >= 0.", SwErrors.swInvalidInput)
            counts = {"positive": 0, "negative": 0, "below_min": 0, "vertical": 0, "flat": 0, "not_applicable": 0}
            rows = []
            for bi, body in enumerate(self._bodies(doc)):
                for fi, face in enumerate(list(self._com(body, "GetFaces") or [])):
                    row = self._draft_row(face, d, mina)
                    row["body"], row["face"] = bi, fi
                    counts[row["class"]] += 1
                    rows.append(row)
            side = [r["sformo_deg"] for r in rows if r["class"] not in ("flat", "not_applicable")]
            data = {"direction": [round(x, 6) for x in d], "min_angle_deg": mina, "counts": counts,
                    "side_faces": len(side), "sformo_min_deg": round(min(side), 4) if side else None,
                    "sformo_max_deg": round(max(side), 4) if side else None, "faces": rows,
                    "sign": "positivo = la parete si restringe andando nella direzione di estrazione"}
            msg = (f"Sformo (direzione {data['direction']}): {len(side)} facce laterali; positive {counts['positive']}, "
                   f"negative {counts['negative']}, sotto {mina} gradi {counts['below_min']}, verticali {counts['vertical']}; "
                   f"piane perpendicolari {counts['flat']}")
            return self._result(True, msg, SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"draft_analysis: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ spessore
    def thickness_analysis(self, samples: int = 400, unit: str = None) -> Dict:
        """Spessore locale: raggi dal centro di ogni triangolo della tessellazione verso l'interno (RayIntersections)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            nmax = 400 if samples is None else int(samples)
            if nmax < 1 or nmax > 5000:
                return self._result(False, "samples: da 1 a 5000 punti.", SwErrors.swInvalidInput)
            bodies = self._bodies(doc)
            if not bodies:
                return self._result(False, "Nessun corpo solido nel pezzo.", SwErrors.swSelectionError)
            cands, no_tess = [], 0
            for bi, body in enumerate(bodies):
                for fi, face in enumerate(list(self._com(body, "GetFaces") or [])):
                    tri = face.GetTessTriangles(False)
                    if tri is None:
                        no_tess += 1
                        continue
                    v = [float(x) * 0.001 for x in tri]     # GetTessTriangles e' in mm (GetBox e' in m, misurato)
                    nv = len(v) // 3
                    plane = self._surface_kind(face) == "plane"
                    fn = None
                    if plane:
                        fn = [float(x) for x in self._com(face, "Normal")]
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
                            n = [sum(tnv[3 * i + j] for i in ids) for j in range(3)]
                        u = _unit_vec(n)
                        if u is None:
                            continue
                        cands.append((bi, fi, c, [-x for x in u]))
            if not cands:
                return self._result(False, "Nessuna faccia tessellata: impossibile misurare lo spessore.",
                                    SwErrors.swFeatureError, {"faces_without_tessellation": no_tess})
            if len(cands) > nmax:
                step = len(cands) / float(nmax)
                cands = [cands[int(i * step)] for i in range(nmax)]
            pts, vec = [], []
            for _bi, _fi, c, dv in cands:
                pts += c
                vec += dv
            n_hits = doc.Extension.RayIntersections(disp_array(bodies), r8_array(pts), r8_array(vec), 0, 0.0, 0.0, False)
            raw = doc.GetRayIntersectionsPoints
            hits = [float(x) for x in raw] if raw else []
            hpts = [(hits[6 * k + 3], hits[6 * k + 4], hits[6 * k + 5]) for k in range(len(hits) // 6)]
            vals, no_exit = [], 0
            for bi, fi, o, d in cands:
                ts = []
                for h in hpts:
                    w = [h[i] - o[i] for i in range(3)]
                    tt = _dot(w, d)
                    if tt < _RAY_MIN_T:
                        continue
                    perp = math.sqrt(max(0.0, _dot(w, w) - tt * tt))
                    if perp <= _RAY_PERP:
                        ts.append(tt)
                if ts:
                    vals.append((min(ts), bi, fi, o))
                else:
                    no_exit += 1
            if not vals:
                return self._result(False, "Nessuna uscita dai raggi: spessore non misurabile (SolidWorks hits: "
                                    f"{n_hits}).", SwErrors.swFeatureError, {"hits": n_hits, "rays": len(cands)})
            lo = min(vals, key=lambda r: r[0])
            hi = max(vals, key=lambda r: r[0])
            data = {"min": round(self._from_m(lo[0], unit), 4), "max": round(self._from_m(hi[0], unit), 4),
                    "unit": self._unit_name(unit),
                    "min_location": [round(self._from_m(v, unit), 4) for v in lo[3]],
                    "min_at_body_face": [lo[1], lo[2]], "rays": len(cands), "valid": len(vals), "no_exit": no_exit,
                    "faces_without_tessellation": no_tess}
            msg = (f"Spessore minimo {data['min']} {data['unit']} (corpo {lo[1]}, faccia {lo[2]}), massimo "
                   f"{data['max']} {data['unit']}: {len(vals)} raggi misurati su {len(cands)}")
            return self._result(True, msg, SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"thickness_analysis: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ sezione della vista
    def section_view(self, plane: str = "Front", offset: float = 0.0, remove: bool = False, unit: str = None) -> Dict:
        """Crea o toglie la sezione della vista (solo visualizzazione: il volume non cambia)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            mvm = self._com(doc, "ModelViewManager")
            v0 = self._volume_m3(doc)
            if remove:
                ok = bool(self._com(mvm, "RemoveSectionView"))
                v1 = self._volume_m3(doc)
                data = {"removed": ok, "volume_mm3": round(v1 * 1e9, 4), "volume_before_mm3": round(v0 * 1e9, 4)}
                if not ok:
                    return self._result(False, "Nessuna sezione da togliere (SolidWorks ha risposto False).",
                                        SwErrors.swFeatureError, data)
                return self._result(True, f"Sezione tolta; volume {data['volume_mm3']} mm3", SwErrors.swSuccess, data)
            key = str(plane or "Front").strip().lower()
            if key in ("front", "top", "right"):
                feat = self._std_ref_feature(doc, key)
            else:
                feat = self._find_feature(doc, plane)
            if feat is None:
                return self._result(False, f"Piano '{plane}' non trovato: usa Front, Top, Right o il nome di un piano.",
                                    SwErrors.swSelectionError)
            off_m = self._mmu(float(offset or 0.0), unit)
            sdata = self._com(mvm, "CreateSectionViewData")
            sdata.FirstPlane = feat
            sdata.FirstOffset = off_m
            ok = bool(mvm.CreateSectionView(sdata))
            v1 = self._volume_m3(doc)
            data = {"plane": plane, "offset": offset, "unit": self._unit_name(unit), "created": ok,
                    "volume_mm3": round(v1 * 1e9, 4)}
            if not ok:
                return self._result(False, "Sezione non creata (SolidWorks ha risposto False).",
                                    SwErrors.swFeatureError, data)
            return self._result(True, f"Sezione su piano {plane} a {offset} {self._unit_name(unit)}",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"section_view: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ schizzo completamente definito
    def fully_define_sketch(self, sketch: str = None, use_dimensions: bool = True, use_relations: bool = True) -> Dict:
        """Quote e relazioni automatiche per rendere lo schizzo completamente definito (FullyDefineSketch)."""
        try:
            doc, err = self._part()
            if err:
                return err
            sk, err = self._active_sketch(doc, sketch)
            if err:
                return err
            name = self._active_sketch_name(doc, sk) or sketch
            rel = _RELATIONS_ALL if use_relations else 0
            nd = null_variant()
            doc.SketchManager.FullyDefineSketch(True, bool(use_relations), rel, bool(use_dimensions),
                                                _AUTODIM_BASELINE, nd, _AUTODIM_BASELINE, nd, _PLACE_ABOVE, _PLACE_RIGHT)
            st = self.get_sketch_definition_status(sketch=name)
            sd = st.get("data") or {}
            if not st.get("success"):
                return self._result(False, f"Stato dello schizzo non leggibile: {st.get('message')}", SwErrors.swSketchError)
            ok = bool(sd.get("fully_defined"))
            data = {"sketch": sd.get("sketch"), "status": sd.get("status"), "fully_defined": ok,
                    "dimensions": len(sd.get("dimensions", []))}
            if not ok:
                return self._result(False, f"Schizzo non completamente definito: {sd.get('status')}",
                                    SwErrors.swSketchError, data)
            return self._result(True, f"Schizzo {data['sketch']} completamente definito con {data['dimensions']} quote",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"fully_define_sketch: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)
