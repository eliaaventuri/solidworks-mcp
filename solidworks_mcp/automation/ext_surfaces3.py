"""
Lotto SUPERFICI 3 (revisione 2026-11-12, sez. 5: "oggi si creano superfici ma non si chiudono in un solido"): cuci (con
formazione del solido), ispessisci, offset di superficie, elimina faccia (mixin). Schemi in tools_ext/surfaces3.py.

Ogni tool rilegge il risultato dai corpi (numero di corpi superficie e solidi, aree delle superfici, volume) con gli helper
del lotto surfaces1 (_sf_snapshot, _sf_pick) e, se SolidWorks non ha cambiato nulla, elimina la feature vuota e fallisce.
API usate: IFeatureManager.InsertSewRefSurface, IFeatureManager.FeatureBossThicken, IModelDoc2.InsertOffsetSurface,
IModelDoc2.InsertDeleteFace2 (swFaceDeleteOption_e: 0 elimina, 1 elimina e ricuci, 2 elimina e riempi).
"""

import logging
import traceback
from typing import Dict, List

from ..constants import SwErrors

logger = logging.getLogger(__name__)

_THICKEN_SIDE = {"side1": 0, "side2": 1, "both": 2}
_DELETE_MODE = {"delete": 0, "patch": 1, "fill": 2}


class Surfaces3Operations:
    """Mixin del lotto surfaces3."""

    def _s3_new(self, doc, before: List[str]) -> List[str]:
        return [x["name"] for x in self._new_features(doc, before)
                if x["type"] not in ("ProfileFeature", "RefPlane", "RefAxis", "RefPoint")]

    def _s3_undo(self, doc, before: List[str]):
        try:
            self._delete_features(doc, self._s3_new(doc, before))
        except Exception as e:
            logger.debug(f"surfaces3 undo: {e}")

    def _s3_pick_faces(self, doc, face_points, unit):
        """Seleziona (in aggiunta) la faccia sotto ogni punto, fra corpi solidi e superficie. -> errore | None."""
        doc.ClearSelection2(True)
        for i, pt in enumerate(face_points or []):
            _ent, err = self._sf_pick(doc, "face", pt, unit, 0, i > 0)
            if err:
                return f"punto {i + 1}: {err}"
        return None

    @staticmethod
    def _s3_data(snap0, snap1) -> Dict:
        return {"surface_bodies_before": len(snap0["sheet_areas"]), "surface_bodies": len(snap1["sheet_areas"]),
                "solid_bodies_before": snap0["solids"], "solid_bodies": snap1["solids"],
                "surface_areas_mm2": [round(a * 1e6, 3) for a in snap1["sheet_areas"]],
                "volume_mm3": round(snap1["volume"] * 1e9, 3),
                "volume_delta_mm3": round((snap1["volume"] - snap0["volume"]) * 1e9, 3)}

    # ------------------------------------------------------------------ cuci
    def knit_surfaces(self, face_points: list = None, form_solid: bool = False, merge_faces: bool = True,
                      gap_tolerance: float = 0.0025, unit: str = None) -> Dict:
        """Cuce corpi superficie (uno per punto in face_points; senza punti: tutti i corpi superficie) in uno solo; con
        form_solid=True, se chiudono un volume, ne fa un solido. Verifica: corpi superficie diminuiti, e con form_solid un
        solido in piu' con volume > 0."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            snap0 = self._sf_snapshot(doc)
            if len(snap0["sheet_areas"]) < 1:
                return self._result(False, "knit_surfaces: nessun corpo superficie nel pezzo.", SwErrors.swInvalidInput)
            before = self._names(doc)
            def targets():
                """Corpi da cucire (riletti a ogni tentativo: dopo un annulla i vecchi oggetti COM non valgono piu')."""
                if face_points:
                    fs = []
                    for i, pt in enumerate(face_points):
                        f_, e_ = self._sf_pick(doc, "face", pt, unit, 1, False)
                        if e_:
                            return None, f"punto {i + 1}: {e_}"
                        fs.append(f_)
                    doc.ClearSelection2(True)
                    return [f_.GetBody for f_ in fs], None
                return list(doc.GetBodies2(1, False) or []), None

            tol = self._mmu(float(gap_tolerance), unit)
            fm = doc.FeatureManager
            attempts = []
            feat = None
            # misurato 2026-11-19: Mark 0 -> niente; UNA faccia per corpo (Mark 1) cuce solo quella faccia; corpi con Mark 1 ->
            # cucitura giusta; il SOLIDO si forma solo con UseGapFilters=true (con false resta una superficie chiusa)
            for label, use_gap, by in (("corpi mark 1", True, "bodies"), ("tutte le facce mark 1", True, "faces"),
                                       ("corpi mark 1 senza filtro", False, "bodies")):
                bodies, e = targets()
                if e:
                    return self._result(False, f"knit_surfaces: {e}", SwErrors.swSelectionError)
                if len(bodies) < 1:
                    break
                doc.ClearSelection2(True)
                if by == "bodies":
                    ok_sel = all(bd.Select2(i > 0, self._sd(doc, 1)) for i, bd in enumerate(bodies))
                else:
                    allf = [f_ for bd in bodies for f_ in (self._com(bd, "GetFaces") or [])]
                    ok_sel = bool(allf) and all(f_.Select4(i > 0, self._sd(doc, 1)) for i, f_ in enumerate(allf))
                if not ok_sel:
                    attempts.append(f"{label}: selezione rifiutata")
                    continue
                n_sb0 = len(doc.GetBodies2(1, False) or [])
                feat = fm.InsertSewRefSurface(bool(use_gap), bool(form_solid), bool(merge_faces), max(tol, 1e-5), max(10 * tol, 1e-4))
                new_ = self._s3_new(doc, before)
                n_sb1 = len(doc.GetBodies2(1, False) or [])
                n_sol = len(doc.GetBodies2(0, False) or [])
                attempts.append(f"{label}: {'feature' if (feat is not None or new_) else 'niente'}, corpi superficie {n_sb0}->{n_sb1}, "
                                f"solidi {n_sol}")
                if feat is not None or new_:
                    good = (n_sol > snap0["solids"]) if form_solid else (n_sb1 <= n_sb0 - len(bodies) + 1)
                    if good:
                        break
                    self._s3_undo(doc, before)          # risultato parziale: si annulla e si prova il modo seguente
                    feat = None
            doc.ClearSelection2(True)
            snap1 = self._sf_snapshot(doc)
            data = self._s3_data(snap0, snap1)
            new = self._s3_new(doc, before)
            data["feature"] = new[0] if new else None
            data["attempts"] = attempts
            if feat is None and not new:
                return self._result(False, "knit_surfaces: SolidWorks non ha creato la cucitura (bordi non coincidenti entro "
                                    "la tolleranza?).", SwErrors.swFeatureError, data)
            if form_solid:
                if snap1["solids"] <= snap0["solids"] or snap1["volume"] <= snap0["volume"]:
                    self._s3_undo(doc, before)
                    return self._result(False, "knit_surfaces: cucitura fatta ma NESSUN solido formato (le superfici non chiudono "
                                        "un volume?): annullata.", SwErrors.swFeatureError, data)
            elif data["surface_bodies"] >= data["surface_bodies_before"]:
                self._s3_undo(doc, before)
                return self._result(False, "knit_surfaces: i corpi superficie non sono diminuiti (niente da cucire?): annullata.",
                                    SwErrors.swFeatureError, data)
            what = (f"solido formato, volume {data['volume_mm3']} mm3" if form_solid else
                    f"corpi superficie {data['surface_bodies_before']} -> {data['surface_bodies']}")
            return self._result(True, f"Superfici cucite ({data['feature']}): {what}", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"knit_surfaces: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ ispessisci
    def thicken_surface(self, face_point: list, thickness: float, side: str = "side1", merge: bool = True,
                        unit: str = None) -> Dict:
        """Ispessisce una superficie in un solido (Ispessimento, boss): la superficie che passa per face_point, di `thickness`
        sul lato side1 | side2 | both. Verifica: volume aumentato; per una superficie piana deve valere area x spessore."""
        try:
            doc, err = self._part()
            if err:
                return err
            sd = _THICKEN_SIDE.get(str(side).lower())
            if sd is None:
                return self._result(False, "side: side1 | side2 | both", SwErrors.swInvalidInput)
            t = self._mmu(float(thickness), unit)
            if t <= 0:
                return self._result(False, "thickness deve essere > 0", SwErrors.swInvalidInput)
            self._exit_sketch(doc)
            snap0 = self._sf_snapshot(doc)
            before = self._names(doc)
            face, e = self._sf_pick(doc, "face", face_point, unit, 1, False)     # Mark 1: misurato (mark 0 -> nulla)
            if e:
                return self._result(False, f"thicken_surface: {e}", SwErrors.swSelectionError)
            try:
                area = sum(float(self._com(f, "GetArea")) for f in (self._com(face.GetBody, "GetFaces") or []))
            except Exception:
                area = None
            feat = doc.FeatureManager.FeatureBossThicken(t, sd, 0, False, bool(merge), False, False)
            doc.ClearSelection2(True)
            snap1 = self._sf_snapshot(doc)
            data = self._s3_data(snap0, snap1)
            data.update({"thickness": thickness, "side": side, "surface_area_mm2": round(area * 1e6, 3) if area else None,
                         "feature": (self._s3_new(doc, before) or [None])[0]})
            if feat is None and not data["feature"]:
                return self._result(False, "thicken_surface: SolidWorks non ha creato l'ispessimento.", SwErrors.swFeatureError, data)
            dv = snap1["volume"] - snap0["volume"]
            if dv <= 0:
                self._s3_undo(doc, before)
                return self._result(False, "thicken_surface: ispessimento creato ma il volume non e' aumentato: annullato.",
                                    SwErrors.swFeatureError, data)
            if area:
                data["expected_volume_if_flat_mm3"] = round(area * t * 1e9, 3)
            return self._result(True, f"Superficie ispessita ({data['feature']}): +{round(dv * 1e9, 3)} mm3"
                                + (f" (superficie piana: area x spessore = {data['expected_volume_if_flat_mm3']} mm3)" if area else ""),
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"thicken_surface: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ offset di superficie
    def offset_surface(self, face_points: list, distance: float, reverse: bool = False, unit: str = None) -> Dict:
        """Superficie a distanza costante dalle facce indicate (anche di un solido). distance 0 = copia delle facce.
        Verifica: un corpo superficie in piu' (area riletta)."""
        try:
            doc, err = self._part()
            if err:
                return err
            if not face_points:
                return self._result(False, "face_points: almeno un punto su una faccia", SwErrors.swInvalidInput)
            self._exit_sketch(doc)
            snap0 = self._sf_snapshot(doc)
            before = self._names(doc)
            e = self._s3_pick_faces(doc, face_points, unit)
            if e:
                return self._result(False, f"offset_surface: {e}", SwErrors.swSelectionError)
            doc.InsertOffsetSurface(self._mmu(float(distance), unit), bool(reverse))
            doc.ClearSelection2(True)
            snap1 = self._sf_snapshot(doc)
            data = self._s3_data(snap0, snap1)
            data.update({"distance": distance, "reverse": bool(reverse), "feature": (self._s3_new(doc, before) or [None])[0]})
            added = len(snap1["sheet_areas"]) - len(snap0["sheet_areas"])
            if added < 1:
                self._s3_undo(doc, before)
                return self._result(False, "offset_surface: nessun corpo superficie nuovo (distanza troppo grande per la "
                                    "curvatura delle facce?).", SwErrors.swFeatureError, data)
            data["new_surface_area_mm2"] = round(sum(sorted(snap1["sheet_areas"])[-added:]) * 1e6, 3) if added else 0
            return self._result(True, f"Superficie offset ({data['feature']}) a {distance}: {added} corpo superficie nuovo",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"offset_surface: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ elimina faccia
    def delete_face(self, face_points: list, mode: str = "patch", unit: str = None) -> Dict:
        """Elimina facce (Inserisci > Superficie > Elimina faccia): mode delete (il solido diventa superficie aperta) |
        patch (elimina e richiude estendendo le facce vicine: es. togliere un raccordo o un foro) | fill (elimina e riempie
        con una toppa). Verifica: facce del modello diminuite (e per patch/fill il solido resta)."""
        try:
            doc, err = self._part()
            if err:
                return err
            m = _DELETE_MODE.get(str(mode).lower())
            if m is None:
                return self._result(False, "mode: delete | patch | fill", SwErrors.swInvalidInput)
            if not face_points:
                return self._result(False, "face_points: almeno un punto su una faccia", SwErrors.swInvalidInput)
            self._exit_sketch(doc)

            def n_faces():
                return sum(len(self._com(b, "GetFaces") or []) for b in (doc.GetBodies2(-1, False) or []))
            f0 = n_faces()
            snap0 = self._sf_snapshot(doc)
            before = self._names(doc)
            e = self._s3_pick_faces(doc, face_points, unit)
            if e:
                return self._result(False, f"delete_face: {e}", SwErrors.swSelectionError)
            ok = doc.InsertDeleteFace2(m)
            doc.ClearSelection2(True)
            snap1 = self._sf_snapshot(doc)
            data = self._s3_data(snap0, snap1)
            data.update({"mode": mode, "faces_before": f0, "faces_after": n_faces(), "api_ok": bool(ok),
                         "feature": (self._s3_new(doc, before) or [None])[0]})
            changed = data["faces_after"] < f0 or (m == 0 and snap1["solids"] < snap0["solids"])
            if not data["feature"] or not changed:
                self._s3_undo(doc, before)
                return self._result(False, f"delete_face: nessuna faccia eliminata (InsertDeleteFace2={bool(ok)}).",
                                    SwErrors.swFeatureError, data)
            if m in (1, 2) and snap1["solids"] < snap0["solids"]:
                self._s3_undo(doc, before)
                return self._result(False, "delete_face: con patch/fill il solido doveva restare chiuso, invece e' diventato "
                                    "superficie: annullato (prova mode='fill' o un'altra faccia).", SwErrors.swFeatureError, data)
            return self._result(True, f"Facce eliminate ({data['feature']}, {mode}): facce {f0} -> {data['faces_after']}, "
                                f"volume {data['volume_mm3']} mm3", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"delete_face: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)
