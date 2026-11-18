"""
Lotto FEATURE 4: modellazione 3D estesa, sweep avanzati, lavorazioni spigoli, forometria,
simmetrie, gestione multibody, superfici complesse, lamiera, saldature, stampi e analisi B-Rep
(mixin Features4Operations). Schemi in tools_ext/features4.py.
"""

import math
import logging
from typing import Dict

import pythoncom
from win32com.client import VARIANT

from ..constants import SwErrors

logger = logging.getLogger(__name__)


class Features4Operations:
    """Mixin per le 33 feature e operazioni estese di modellazione 3D (Features4Operations)."""

    def _model_rebuild(self, doc) -> None:
        """Rigenera il modello in modo sicuro senza sollevare errori su late-binding."""
        try:
            self._com(doc, "EditRebuild3")
        except Exception:
            pass
        try:
            doc.ForceRebuild3(False)
        except Exception:
            pass

    def _safe_select(self, doc, kind: str, pt, unit=None, mark=0, tol_mm: float = 50.0) -> bool:
        """Seleziona un'entita' geometrica senza bloccare l'esecuzione in caso di scostamento di coordinate."""
        try:
            if pt is not None and hasattr(self, "_select_point"):
                ok, _ = self._select_point(doc, kind, pt, unit=unit, mark=mark, tol_mm=tol_mm)
                return bool(ok)
        except Exception:
            pass
        return False


    def _creata(self, doc, n0: int, res) -> bool:
        """Prova di creazione: il risultato della chiamata non e' None/False e le feature sono aumentate."""
        if res is None or res is False:
            return False
        try:
            return len(self._features(doc)) > n0
        except Exception:
            return False


    def intersect_solid_features(self, body_names: list, cap_planar_openings: bool = True, unit: str = None) -> Dict:
        """Interseca corpi solidi o superfici multiple per generare volumi composti chiusi (PreIntersect2 + PostIntersect)."""
        try:
            return self.intersect_bodies(bodies=body_names, cap_planar=bool(cap_planar_openings), unit=unit)
        except Exception as e:
            return self._result(False, f"intersect_solid_features: {e}", SwErrors.swGenericError)


    def variable_section_sweep(self, profile_sketch: str, path_sketch: str, guide_sketches: list = None,
                               scale_factor: float = 1.0, twist_angle: float = 0.0, unit: str = None) -> Dict:
        """Crea uno sweep con sezione variabile controllata da guide multiple (scala non ancora supportata)."""
        try:
            if abs(float(scale_factor) - 1.0) > 1e-9:
                return self._result(False, f"variable_section_sweep: scale_factor {scale_factor} non supportato (usare 1.0 e guide_sketches per la sezione variabile)", SwErrors.swInvalidInput)
            return self.sweep(profile_sketch=profile_sketch, path_sketch=path_sketch, guide_sketches=guide_sketches,
                              twist_angle=twist_angle, unit=unit)
        except Exception as e:
            return self._result(False, f"variable_section_sweep: {e}", SwErrors.swGenericError)


    def mirror_body_merge(self, body_names: list, mirror_plane: str, merge_bodies: bool = True, unit: str = None) -> Dict:
        """Specchia corpi solidi rispetto a un piano fondendo automaticamente le facce di contatto complanari."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            ok_p, msg_p = self._select_edge_or_axis(doc, mirror_plane, unit, mark=2, append=False)
            if not ok_p:
                return self._result(False, f"mirror_body_merge: piano '{mirror_plane}' non trovato ({msg_p})", SwErrors.swSelectionError)
            for b in body_names or []:
                hit = [o for o in self._bodies(doc) if str(self._com(o, "Name")) == str(b)]
                if not hit or not hit[0].Select2(True, self._sd(doc, 256)):
                    return self._result(False, f"mirror_body_merge: corpo '{b}' non trovato", SwErrors.swSelectionError)
            fm = doc.FeatureManager
            n0 = len(self._features(doc))
            res = fm.InsertMirrorFeature2(True, False, bool(merge_bodies), False, 0)
            if not self._creata(doc, n0, res):
                return self._result(False, "mirror_body_merge: specchiatura non creata da SolidWorks (nessuna feature nuova)", SwErrors.swFeatureError)
            self._model_rebuild(doc)
            return self._result(
                True, f"Specchiatura corpi creata ({len(body_names or [])} corpi su '{mirror_plane}').",
                SwErrors.swSuccess, {"bodies": body_names, "plane": mirror_plane, "merge_bodies": bool(merge_bodies)}
            )
        except Exception as e:
            return self._result(False, f"mirror_body_merge: {e}", SwErrors.swGenericError)


    # ------------------------------------------------------------------ 9. Lamiera (Sheet Metal)
    def cross_break(self, face_point: list, depth: float, break_angle: float = 2.0, unit: str = None) -> Dict:
        """Aggiunge una crociera di irrigidimento diagonale a un pannello piatto di lamiera."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            if not self._safe_select(doc, "face", face_point, unit=unit, mark=0):
                return self._result(False, f"cross_break: faccia {face_point} non trovata", SwErrors.swSelectionError)
            fm = doc.FeatureManager
            n0 = len(self._features(doc))
            res = fm.InsertCrossBreak(self._mmu(depth, unit), math.radians(float(break_angle)))
            if not self._creata(doc, n0, res):
                return self._result(False, "cross_break: crociera non creata da SolidWorks (nessuna feature nuova)", SwErrors.swFeatureError)
            self._model_rebuild(doc)
            return self._result(
                True, f"Crociera di piega (Cross Break) inserita (profondita' {depth} mm, angolo {break_angle}°).",
                SwErrors.swSuccess, {"depth": depth, "angle": break_angle}
            )
        except Exception as e:
            return self._result(False, f"cross_break: {e}", SwErrors.swGenericError)

    def convert_to_sheet_metal(self, thickness: float, bend_radius: float, fixed_face_point: list,
                               rip_edges: list = None, unit: str = None) -> Dict:
        """Converte un corpo solido pieno in una parte in lamiera piegata con scarichi automatici."""
        try:
            doc, err = self._part()
            if err:
                return err
            tm = self._mmu(thickness, unit)
            rm = self._mmu(bend_radius, unit)
            doc.ClearSelection2(True)
            if not self._safe_select(doc, "face", fixed_face_point, unit=unit, mark=1):
                return self._result(False, f"convert_to_sheet_metal: faccia fissa {fixed_face_point} non trovata", SwErrors.swSelectionError)
            fm = doc.FeatureManager
            n0 = len(self._features(doc))
            v0 = self._volume_m3(doc)
            res = fm.InsertConvertToSheetMetal2(tm, False, False, rm, 0, 0, 0, 0, 0, False)
            if not (bool(res) or len(self._features(doc)) > n0) or abs(self._volume_m3(doc) - v0) < 1e-12:
                return self._result(False, "convert_to_sheet_metal: conversione non creata da SolidWorks (nessuna feature nuova)", SwErrors.swFeatureError)
            self._model_rebuild(doc)
            return self._result(
                True, f"Corpo solido convertito in lamiera piegata (spessore {thickness} mm, raggio {bend_radius} mm).",
                SwErrors.swSuccess, {"thickness": thickness, "bend_radius": bend_radius,
                                     "ignored_params": ["rip_edges"]}
            )
        except Exception as e:
            return self._result(False, f"convert_to_sheet_metal: {e}", SwErrors.swGenericError)


    def update_cut_list(self, force_rebuild: bool = True) -> Dict:
        """Calcola, raggruppa e aggiorna la distinta di taglio dei membri strutturali saldati."""
        try:
            doc, err = self._part()
            if err:
                return err
            if force_rebuild:
                self._model_rebuild(doc)
            folders = [f for n, t, f in self._features(doc) if t == "CutListFolder"]
            if not folders:
                return self._result(False, "update_cut_list: nessuna distinta di taglio nel modello (crea prima weldment_cut_list)", SwErrors.swSelectionError)
            bf = self._com(folders[0], "GetSpecificFeature2")
            self._wld_raw(bf, "UpdateCutList")
            members = list(self._wld_raw(bf, "GetBodies") or [])
            if not members:
                return self._result(False, "update_cut_list: la distinta di taglio non elenca nessun membro dopo l'aggiornamento", SwErrors.swFeatureError)
            return self._result(
                True, f"Distinta di taglio profilati saldati aggiornata ({len(members)} membri).",
                SwErrors.swSuccess, {"updated": True, "members": len(members)}
            )
        except Exception as e:
            return self._result(False, f"update_cut_list: {e}", SwErrors.swGenericError)

    def subweldment_folder(self, folder_name: str, member_names: list = None) -> Dict:
        """Raggruppa profilati strutturali e fazzoletti in una cartella di sotto-saldatura dedicata."""
        try:
            doc, err = self._part()
            if err:
                return err
            wanted = list(member_names or [])
            members = [b for b in self._bodies(doc) if str(self._com(b, "Name")) in wanted]
            if len(members) != len(wanted) or not members:
                names = [str(self._com(b, "Name")) for b in self._bodies(doc)]
                return self._result(False, f"subweldment_folder: componente/i {wanted} non trovati fra i corpi {names}", SwErrors.swSelectionError)
            n0 = len(self._features(doc))
            res = self._wld_raw(doc.FeatureManager, "InsertSubWeldFolder2", VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, tuple(members)))
            if not self._creata(doc, n0, res):
                return self._result(False, "subweldment_folder: cartella non creata da SolidWorks (nessuna feature nuova)", SwErrors.swFeatureError)
            self._model_rebuild(doc)
            return self._result(
                True, f"Cartella sotto-saldatura creata con {len(member_names or [])} componenti.",
                SwErrors.swSuccess, {"members": wanted, "ignored_params": ["folder_name"]}
            )
        except Exception as e:
            return self._result(False, f"subweldment_folder: {e}", SwErrors.swGenericError)

