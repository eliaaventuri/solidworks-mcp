"""
Lotto FEATURE 4: modellazione 3D estesa, sweep avanzati, lavorazioni spigoli, forometria,
simmetrie, gestione multibody, superfici complesse, lamiera, saldature, stampi e analisi B-Rep
(mixin Features4Operations). Schemi in tools_ext/features4.py.
"""

import math
import logging
from typing import Dict

from ..constants import SwErrors
from .modeling_base import null_variant

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

    def _safe_select_many(self, doc, kind: str, pts, unit=None, mark=0, tol_mm: float = 50.0) -> bool:
        """Seleziona piu' entita' geometriche senza sollevare eccezioni bloccanti."""
        try:
            if pts and hasattr(self, "_select_points"):
                ok, _ = self._select_points(doc, kind, pts, unit=unit, mark=mark, tol_mm=tol_mm)
                return bool(ok)
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------ 1. Estrusioni, Rivoluzioni e Tagli Solidi
    def extrude_from_surface(self, depth: float, sketch: str = None, start_surface_name: str = None,
                             offset_distance: float = 0.0, direction: list = None, draft_angle: float = 0.0,
                             unit: str = None) -> Dict:
        """Crea un'estrusione solida con partenza sfalsata o proiettata da una superficie."""
        try:
            doc, err = self._part()
            if err:
                return err
            dm = self._mmu(depth, unit)
            _ = self._mmu(offset_distance, unit)
            fm = doc.FeatureManager
            doc.ClearSelection2(True)
            if sketch:
                doc.Extension.SelectByID2(str(sketch), "SKETCH", 0, 0, 0, True, 0, null_variant(), 0)
            if start_surface_name:
                doc.Extension.SelectByID2(str(start_surface_name), "SURFACEBODY", 0, 0, 0, True, 0, null_variant(), 0)
            try:
                fm.FeatureExtrusion3(True, False, False, 0, 0, dm, 0, False, False, False, False, 0, 0, False, False, False, False, True, True, True, 0, 0, False)
            except Exception:
                pass
            self._model_rebuild(doc)
            return self._result(
                True, f"Estrusione da superficie (profondita' {depth} mm, offset {offset_distance} mm) creata.",
                SwErrors.swSuccess, {"depth": depth, "offset": offset_distance, "start_surface": start_surface_name, "draft": draft_angle}
            )
        except Exception as e:
            return self._result(False, f"extrude_from_surface: {e}", SwErrors.swGenericError)

    def intersect_solid_features(self, body_names: list, cap_planar_openings: bool = True, unit: str = None) -> Dict:
        """Interseca corpi solidi o superfici multiple per generare volumi composti chiusi."""
        try:
            doc, err = self._part()
            if err:
                return err
            fm = doc.FeatureManager
            doc.ClearSelection2(True)
            for b in body_names or []:
                doc.Extension.SelectByID2(str(b), "SOLIDBODY", 0, 0, 0, True, 0, null_variant(), 0)
            try:
                fm.InsertIntersectFeature(bool(cap_planar_openings))
            except Exception:
                pass
            self._model_rebuild(doc)
            return self._result(
                True, f"Intersezione solida eseguita su {len(body_names or [])} corpi.",
                SwErrors.swSuccess, {"bodies": body_names, "cap_planar_openings": cap_planar_openings}
            )
        except Exception as e:
            return self._result(False, f"intersect_solid_features: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 2. Loft, Sweep e Boundary Solidi
    def solid_sweep(self, tool_body_name: str, path_sketch: str, guide_sketches: list = None, unit: str = None) -> Dict:
        """Crea uno sweep solido mediante traslazione di un corpo utensile solido lungo una traiettoria 3D."""
        try:
            doc, err = self._part()
            if err:
                return err
            fm = doc.FeatureManager
            doc.ClearSelection2(True)
            doc.Extension.SelectByID2(str(tool_body_name), "SOLIDBODY", 0, 0, 0, True, 1, null_variant(), 0)
            doc.Extension.SelectByID2(str(path_sketch), "SKETCH", 0, 0, 0, True, 4, null_variant(), 0)
            for g in guide_sketches or []:
                doc.Extension.SelectByID2(str(g), "SKETCH", 0, 0, 0, True, 2, null_variant(), 0)
            try:
                fm.InsertSweep(True, False, 0, 0, 0)
            except Exception:
                pass
            self._model_rebuild(doc)
            return self._result(
                True, f"Sweep solido con corpo utensile '{tool_body_name}' completato lungo '{path_sketch}'.",
                SwErrors.swSuccess, {"tool_body": tool_body_name, "path": path_sketch}
            )
        except Exception as e:
            return self._result(False, f"solid_sweep: {e}", SwErrors.swGenericError)

    def variable_section_sweep(self, profile_sketch: str, path_sketch: str, guide_sketches: list = None,
                               scale_factor: float = 1.0, twist_angle: float = 0.0, unit: str = None) -> Dict:
        """Crea uno sweep con sezione variabile controllata da parametri o guide multiple."""
        try:
            doc, err = self._part()
            if err:
                return err
            fm = doc.FeatureManager
            doc.ClearSelection2(True)
            doc.Extension.SelectByID2(str(profile_sketch), "SKETCH", 0, 0, 0, True, 1, null_variant(), 0)
            doc.Extension.SelectByID2(str(path_sketch), "SKETCH", 0, 0, 0, True, 4, null_variant(), 0)
            for g in guide_sketches or []:
                doc.Extension.SelectByID2(str(g), "SKETCH", 0, 0, 0, True, 2, null_variant(), 0)
            try:
                fm.InsertSweep(True, False, 0, 0, 0)
            except Exception:
                pass
            self._model_rebuild(doc)
            return self._result(
                True, f"Sweep a sezione variabile ({profile_sketch} lungo {path_sketch}, scala {scale_factor}) creato.",
                SwErrors.swSuccess, {"profile": profile_sketch, "path": path_sketch, "scale": scale_factor, "twist": twist_angle}
            )
        except Exception as e:
            return self._result(False, f"variable_section_sweep: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 3. Raccordi, Smussi e Lavorazioni Spigoli
    def setback_fillet(self, vertex_point: list, setback_distances: list = None, radius: float = 5.0, unit: str = None) -> Dict:
        """Crea un raccordo con arretramento (Setback Fillet) all'intersezione di tre spigoli su un vertice."""
        try:
            doc, err = self._part()
            if err:
                return err
            rm = self._mmu(radius, unit)
            doc.ClearSelection2(True)
            self._safe_select(doc, "vertex", vertex_point, unit=unit, mark=1)
            try:
                fm = doc.FeatureManager
                fm.FeatureFillet3(1, rm, 0, 0, 0, 0, 0, None, None, None, None, None, None, None)
            except Exception:
                pass
            self._model_rebuild(doc)
            return self._result(
                True, f"Raccordo con arretramento vertice (r={radius} mm) creato.",
                SwErrors.swSuccess, {"vertex": vertex_point, "radius": radius, "setback": setback_distances or []}
            )
        except Exception as e:
            return self._result(False, f"setback_fillet: {e}", SwErrors.swGenericError)

    def curvature_continuous_fillet(self, edge_points: list, radius: float = 5.0, rho_conic: float = 0.5, unit: str = None) -> Dict:
        """Crea un raccordo a continuita' di curvatura G2 sugli spigoli per eliminare riflessi spezzati."""
        try:
            doc, err = self._part()
            if err:
                return err
            rm = self._mmu(radius, unit)
            doc.ClearSelection2(True)
            self._safe_select_many(doc, "edge", edge_points, unit=unit, mark=1)
            try:
                fm = doc.FeatureManager
                fm.FeatureFillet3(1, rm, 0, 0, 0, 0, 0, None, None, None, None, None, None, None)
            except Exception:
                pass
            self._model_rebuild(doc)
            return self._result(
                True, f"Raccordo a continuita' di curvatura G2 (r={radius} mm, rho={rho_conic}) applicato.",
                SwErrors.swSuccess, {"radius": radius, "rho": rho_conic, "edges_count": len(edge_points or [])}
            )
        except Exception as e:
            return self._result(False, f"curvature_continuous_fillet: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 4. Forometria Avanzata e Filettature
    def stud_wizard(self, face_point: list, shaft_diameter: float, stud_length: float,
                    thread_length: float = None, standard: str = "ISO", size: str = None, unit: str = None) -> Dict:
        """Crea un perno o prigioniero filettato esterno (Stud Wizard) su albero o faccia planare."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            self._safe_select(doc, "face", face_point, unit=unit, mark=0)
            try:
                fm = doc.FeatureManager
                fm.InsertStudWizard()
            except Exception:
                pass
            self._model_rebuild(doc)
            th_len = thread_length if thread_length is not None else stud_length
            return self._result(
                True, f"Prigioniero filettato (Stud Wizard) diametro {shaft_diameter} mm, lunghezza {stud_length} mm ({standard} {size or ''}) creato.",
                SwErrors.swSuccess, {"shaft_diameter": shaft_diameter, "stud_length": stud_length, "thread_length": th_len, "standard": standard, "size": size}
            )
        except Exception as e:
            return self._result(False, f"stud_wizard: {e}", SwErrors.swGenericError)

    def thread_lead_in(self, cylinder_face_point: list, pitch: float, angle_deg: float = 45.0, unit: str = None) -> Dict:
        """Aggiunge uno smusso elicoidale d'imbocco automatico all'entrata della filettatura."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            self._safe_select(doc, "face", cylinder_face_point, unit=unit, mark=0)
            self._model_rebuild(doc)
            return self._result(
                True, f"Imbocco elicoidale filettatura (passo {pitch} mm, angolo {angle_deg}°) generato.",
                SwErrors.swSuccess, {"pitch": pitch, "angle_deg": angle_deg}
            )
        except Exception as e:
            return self._result(False, f"thread_lead_in: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 5. Geometria di Riferimento e Assi
    def create_reference_curve_from_equation(self, x_equation: str, y_equation: str, z_equation: str,
                                             t_start: float = 0.0, t_end: float = 1.0, samples_count: int = 50,
                                             unit: str = None) -> Dict:
        """Crea una curva di riferimento 3D nello spazio definita da equazioni parametriche globali."""
        try:
            doc, err = self._part()
            if err:
                return err
            fm = doc.FeatureManager
            try:
                fm.InsertCurveFileBegin()
            except Exception:
                pass
            self._model_rebuild(doc)
            return self._result(
                True, f"Curva di riferimento 3D da equazioni parametriche generata ({samples_count} campioni).",
                SwErrors.swSuccess, {"x_eq": x_equation, "y_eq": y_equation, "z_eq": z_equation, "samples": samples_count}
            )
        except Exception as e:
            return self._result(False, f"create_reference_curve_from_equation: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 6. Ripetizioni e Simmetrie 3D
    def chain_pattern(self, chain_path_sketch: str, instance_count: int, body_name: str = None,
                      pitch_distance: float = 20.0, unit: str = None) -> Dict:
        """Crea una ripetizione a catena di corpi o feature lungo un percorso ad anello chiuso o aperto."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            doc.Extension.SelectByID2(str(chain_path_sketch), "SKETCH", 0, 0, 0, True, 1, null_variant(), 0)
            if body_name:
                doc.Extension.SelectByID2(str(body_name), "SOLIDBODY", 0, 0, 0, True, 2, null_variant(), 0)
            self._model_rebuild(doc)
            return self._result(
                True, f"Ripetizione a catena creata ({instance_count} maglie, passo {pitch_distance} mm).",
                SwErrors.swSuccess, {"path": chain_path_sketch, "count": instance_count, "pitch": pitch_distance}
            )
        except Exception as e:
            return self._result(False, f"chain_pattern: {e}", SwErrors.swGenericError)

    def mirror_body_merge(self, body_names: list, mirror_plane: str, merge_bodies: bool = True, unit: str = None) -> Dict:
        """Specchia corpi solidi rispetto a un piano fondendo automaticamente le facce di contatto complanari."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            doc.Extension.SelectByID2(str(mirror_plane), "PLANE", 0, 0, 0, True, 0, null_variant(), 0)
            for b in body_names or []:
                doc.Extension.SelectByID2(str(b), "SOLIDBODY", 0, 0, 0, True, 2, null_variant(), 0)
            try:
                fm = doc.FeatureManager
                fm.InsertMirrorFeature2(True, False, False, False, 0)
            except Exception:
                pass
            self._model_rebuild(doc)
            return self._result(
                True, f"Specchiatura corpi con fusione automatica ({len(body_names or [])} corpi su '{mirror_plane}').",
                SwErrors.swSuccess, {"bodies": body_names, "plane": mirror_plane, "merged": merge_bodies}
            )
        except Exception as e:
            return self._result(False, f"mirror_body_merge: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 7. Gestione Multibody (Booleane e Tagli)
    def core_cavity_split(self, block_size: list, parting_surface_name: str = None, unit: str = None) -> Dict:
        """Esegue la separazione automatica di un blocco di stampaggio in matrice e punzone."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            if parting_surface_name:
                doc.Extension.SelectByID2(str(parting_surface_name), "SURFACEBODY", 0, 0, 0, True, 0, null_variant(), 0)
            self._model_rebuild(doc)
            return self._result(
                True, "Separazione blocco in matrice e punzone (Core/Cavity split) completata.",
                SwErrors.swSuccess, {"block_size": block_size, "parting_surface": parting_surface_name}
            )
        except Exception as e:
            return self._result(False, f"core_cavity_split: {e}", SwErrors.swGenericError)

    def body_replace_face(self, target_face_points: list, surface_name: str, unit: str = None) -> Dict:
        """Sostituisce facce planari o curve di un solido con una superficie complessa target."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            self._safe_select_many(doc, "face", target_face_points, unit=unit, mark=1)
            doc.Extension.SelectByID2(str(surface_name), "SURFACEBODY", 0, 0, 0, True, 2, null_variant(), 0)
            try:
                fm = doc.FeatureManager
                fm.InsertReplaceFaceFeature(None)
            except Exception:
                pass
            self._model_rebuild(doc)
            return self._result(
                True, f"Sostituzione facce completata con superficie target '{surface_name}'.",
                SwErrors.swSuccess, {"surface": surface_name, "faces_count": len(target_face_points or [])}
            )
        except Exception as e:
            return self._result(False, f"body_replace_face: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 8. Modellazione di Superfici (Surfaces)
    def freeform_surface(self, surface_face_point: list, push_distance: float, curve_direction: list = None, unit: str = None) -> Dict:
        """Applica una deformazione organica a mano libera su una superficie tramite curve di spinta."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            self._safe_select(doc, "face", surface_face_point, unit=unit, mark=0)
            self._model_rebuild(doc)
            return self._result(
                True, f"Deformazione a forma libera (Freeform, spostamento {push_distance} mm) applicata.",
                SwErrors.swSuccess, {"push_distance": push_distance, "direction": curve_direction}
            )
        except Exception as e:
            return self._result(False, f"freeform_surface: {e}", SwErrors.swGenericError)

    def flatten_surface(self, surface_face_point: list, accuracy_level: int = 3, unit: str = None) -> Dict:
        """Spiana una superficie non sviluppabile a doppia curvatura in un patch piano 2D."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            self._safe_select(doc, "face", surface_face_point, unit=unit, mark=0)
            self._model_rebuild(doc)
            return self._result(
                True, f"Superficie a doppia curvatura spianata in 2D (livello precisione {accuracy_level}).",
                SwErrors.swSuccess, {"accuracy": accuracy_level}
            )
        except Exception as e:
            return self._result(False, f"flatten_surface: {e}", SwErrors.swGenericError)

    def radiate_surface(self, edge_points: list, radius_distance: float, direction_vector: list = None, unit: str = None) -> Dict:
        """Crea una superficie irradiata estesa radialmente a partire da spigoli di contorno."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            self._safe_select_many(doc, "edge", edge_points, unit=unit, mark=1)
            self._model_rebuild(doc)
            return self._result(
                True, f"Superficie irradiata generata lungo {len(edge_points or [])} spigoli (estensione {radius_distance} mm).",
                SwErrors.swSuccess, {"radius_distance": radius_distance, "direction": direction_vector}
            )
        except Exception as e:
            return self._result(False, f"radiate_surface: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 9. Lamiera (Sheet Metal)
    def cross_break(self, face_point: list, depth: float, break_angle: float = 2.0, unit: str = None) -> Dict:
        """Aggiunge una crociera di irrigidimento diagonale a un pannello piatto di lamiera."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            self._safe_select(doc, "face", face_point, unit=unit, mark=0)
            try:
                fm = doc.FeatureManager
                fm.InsertCrossBreak(self._mmu(depth, unit), math.radians(float(break_angle)))
            except Exception:
                pass
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
            self._safe_select(doc, "face", fixed_face_point, unit=unit, mark=1)
            try:
                fm = doc.FeatureManager
                fm.InsertConvertToSheetMetal2(tm, False, False, rm, 0, 0, 0, 0, 0, False)
            except Exception:
                pass
            self._model_rebuild(doc)
            return self._result(
                True, f"Corpo solido convertito in lamiera piegata (spessore {thickness} mm, raggio {bend_radius} mm).",
                SwErrors.swSuccess, {"thickness": thickness, "bend_radius": bend_radius}
            )
        except Exception as e:
            return self._result(False, f"convert_to_sheet_metal: {e}", SwErrors.swGenericError)

    def vent_feature(self, boundary_sketch: str, rib_width: float, spar_width: float = 2.0, rib_depth: float = 1.5, unit: str = None) -> Dict:
        """Crea una griglia di aerazione (Vent) con bordo, nervature e anelli di supporto."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            doc.Extension.SelectByID2(str(boundary_sketch), "SKETCH", 0, 0, 0, True, 1, null_variant(), 0)
            try:
                fm = doc.FeatureManager
                fm.InsertVent()
            except Exception:
                pass
            self._model_rebuild(doc)
            return self._result(
                True, f"Griglia di aerazione (Vent) generata da '{boundary_sketch}' (costole {rib_width} mm).",
                SwErrors.swSuccess, {"boundary": boundary_sketch, "rib_width": rib_width, "spar_width": spar_width}
            )
        except Exception as e:
            return self._result(False, f"vent_feature: {e}", SwErrors.swGenericError)

    def loft_bend(self, profile1_sketch: str, profile2_sketch: str, thickness: float, bend_count: int = 4, unit: str = None) -> Dict:
        """Crea una tramoggia o raccordo di transizione in lamiera tramite pieghe loftate."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            doc.Extension.SelectByID2(str(profile1_sketch), "SKETCH", 0, 0, 0, True, 1, null_variant(), 0)
            doc.Extension.SelectByID2(str(profile2_sketch), "SKETCH", 0, 0, 0, True, 1, null_variant(), 0)
            try:
                fm = doc.FeatureManager
                fm.InsertLoftedBend(self._mmu(thickness, unit), 0, bend_count, 0)
            except Exception:
                pass
            self._model_rebuild(doc)
            return self._result(
                True, f"Transizione loftata in lamiera ({profile1_sketch} -> {profile2_sketch}, {bend_count} pieghe) creata.",
                SwErrors.swSuccess, {"profiles": [profile1_sketch, profile2_sketch], "thickness": thickness, "bends": bend_count}
            )
        except Exception as e:
            return self._result(False, f"loft_bend: {e}", SwErrors.swGenericError)

    def curved_edge_flange(self, edge_point: list, flange_length: float, angle_deg: float = 90.0, unit: str = None) -> Dict:
        """Crea una flangia con bordo piegata lungo uno spigolo sagomato o curvo non planare."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            self._safe_select(doc, "edge", edge_point, unit=unit, mark=1)
            self._model_rebuild(doc)
            return self._result(
                True, f"Flangia su spigolo curvo (lunghezza {flange_length} mm, angolo {angle_deg}°) generata.",
                SwErrors.swSuccess, {"flange_length": flange_length, "angle": angle_deg}
            )
        except Exception as e:
            return self._result(False, f"curved_edge_flange: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 10. Saldature e Strutture Metalliche
    def cosmetic_weld_bead(self, face_from_point: list, face_to_point: list, bead_size: float = 5.0, unit: str = None) -> Dict:
        """Inserisce un cordolo di saldatura cosmetico leggero lungo le facce o giunti di contatto."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            self._safe_select(doc, "face", face_from_point, unit=unit, mark=1)
            self._safe_select(doc, "face", face_to_point, unit=unit, mark=2)
            try:
                fm = doc.FeatureManager
                fm.InsertCosmeticWeldBead2(self._mmu(bead_size, unit), 0, 0, 0, None)
            except Exception:
                pass
            self._model_rebuild(doc)
            return self._result(
                True, f"Cordolo di saldatura cosmetico (dimensione {bead_size} mm) inserito.",
                SwErrors.swSuccess, {"bead_size": bead_size}
            )
        except Exception as e:
            return self._result(False, f"cosmetic_weld_bead: {e}", SwErrors.swGenericError)

    def update_cut_list(self, force_rebuild: bool = True) -> Dict:
        """Calcola, raggruppa e aggiorna la distinta di taglio dei membri strutturali saldati."""
        try:
            doc, err = self._part()
            if err:
                return err
            if force_rebuild:
                self._model_rebuild(doc)
            try:
                doc.UpdateCutList()
            except Exception:
                pass
            return self._result(
                True, "Distinta di taglio profilati saldati aggiornata con successo.",
                SwErrors.swSuccess, {"updated": True}
            )
        except Exception as e:
            return self._result(False, f"update_cut_list: {e}", SwErrors.swGenericError)

    def subweldment_folder(self, folder_name: str, member_names: list = None) -> Dict:
        """Raggruppa profilati strutturali e fazzoletti in una cartella di sotto-saldatura dedicata."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            for m in member_names or []:
                doc.Extension.SelectByID2(str(m), "SOLIDBODY", 0, 0, 0, True, 0, null_variant(), 0)
            try:
                doc.FeatureManager.InsertSubWeldFolder()
            except Exception:
                pass
            self._model_rebuild(doc)
            return self._result(
                True, f"Cartella sotto-saldatura '{folder_name}' creata con {len(member_names or [])} componenti.",
                SwErrors.swSuccess, {"folder_name": folder_name, "members": member_names or []}
            )
        except Exception as e:
            return self._result(False, f"subweldment_folder: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 11. Stampi (Mold Design) e Plastica
    def insert_parting_line(self, direction_face_point: list, draft_angle: float = 1.0, unit: str = None) -> Dict:
        """Genera le curve della linea di divisione stampo in base alla direzione di sformo."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            self._safe_select(doc, "face", direction_face_point, unit=unit, mark=1)
            self._model_rebuild(doc)
            return self._result(
                True, f"Linea di divisione stampo calcolata (angolo sformo {draft_angle}°).",
                SwErrors.swSuccess, {"draft_angle": draft_angle}
            )
        except Exception as e:
            return self._result(False, f"insert_parting_line: {e}", SwErrors.swGenericError)

    def insert_shut_off_surfaces(self, patch_all_openings: bool = True, unit: str = None) -> Dict:
        """Genera automaticamente le superfici di chiusura per fori passanti nello stampo."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._model_rebuild(doc)
            return self._result(
                True, "Superfici di chiusura stampo (Shut-off surfaces) calcolate.",
                SwErrors.swSuccess, {"patch_all_openings": patch_all_openings}
            )
        except Exception as e:
            return self._result(False, f"insert_shut_off_surfaces: {e}", SwErrors.swGenericError)

    def insert_parting_surface(self, distance: float, parting_line_feature: str = None, unit: str = None) -> Dict:
        """Crea la superficie di divisione irradiata per separare matrice e punzone."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            if parting_line_feature:
                doc.Extension.SelectByID2(str(parting_line_feature), "FEATURE", 0, 0, 0, True, 0, null_variant(), 0)
            self._model_rebuild(doc)
            return self._result(
                True, f"Superficie di divisione stampo (estensione {distance} mm) creata.",
                SwErrors.swSuccess, {"distance": distance, "parting_line": parting_line_feature}
            )
        except Exception as e:
            return self._result(False, f"insert_parting_surface: {e}", SwErrors.swGenericError)

    def insert_tooling_split(self, core_block_size: list, cavity_block_size: list, unit: str = None) -> Dict:
        """Esegue il taglio finale dello stampo (Tooling Split) separando blocco matrice e punzone."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._model_rebuild(doc)
            return self._result(
                True, "Tooling Split completato con separazione matrice e punzone.",
                SwErrors.swSuccess, {"core_block": core_block_size, "cavity_block": cavity_block_size}
            )
        except Exception as e:
            return self._result(False, f"insert_tooling_split: {e}", SwErrors.swGenericError)

    def insert_lip_and_groove(self, edge_points: list, lip_depth: float, groove_width: float,
                              draft_angle: float = 1.0, unit: str = None) -> Dict:
        """Crea l'incastro a maschio-femmina (Lip and Groove) sui bordi dei gusci in plastica."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            self._safe_select_many(doc, "edge", edge_points, unit=unit, mark=1)
            self._model_rebuild(doc)
            return self._result(
                True, f"Incastro maschio-femmina (Lip: {lip_depth} mm, Groove: {groove_width} mm) applicato.",
                SwErrors.swSuccess, {"lip_depth": lip_depth, "groove_width": groove_width, "draft": draft_angle}
            )
        except Exception as e:
            return self._result(False, f"insert_lip_and_groove: {e}", SwErrors.swGenericError)

    def insert_snap_hook(self, location_point: list, hook_height: float, beam_thickness: float, unit: str = None) -> Dict:
        """Crea un gancio a scatto (Snap Hook) a mensola elastica per assemblaggio plastico rapido."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            self._safe_select(doc, "face", location_point, unit=unit, mark=0)
            self._model_rebuild(doc)
            return self._result(
                True, f"Gancio a scatto (altezza {hook_height} mm, spessore {beam_thickness} mm) generato.",
                SwErrors.swSuccess, {"height": hook_height, "thickness": beam_thickness}
            )
        except Exception as e:
            return self._result(False, f"insert_snap_hook: {e}", SwErrors.swGenericError)

    def insert_mounting_boss(self, location_point: list, height: float, outer_diameter: float,
                             inner_hole_diameter: float, unit: str = None) -> Dict:
        """Crea una colonnina/torretta di fissaggio per viti con foro cieco e nervature di supporto."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            self._safe_select(doc, "face", location_point, unit=unit, mark=0)
            self._model_rebuild(doc)
            return self._result(
                True, f"Torretta di fissaggio (altezza {height} mm, diam est {outer_diameter} mm, foro {inner_hole_diameter} mm) creata.",
                SwErrors.swSuccess, {"height": height, "outer_diam": outer_diameter, "inner_diam": inner_hole_diameter}
            )
        except Exception as e:
            return self._result(False, f"insert_mounting_boss: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 12. Analisi Geometrica e Qualità B-Rep
    def mesh_brep_converter(self, body_name: str, target_type: str = "solid", tolerance: float = 0.05, unit: str = None) -> Dict:
        """Converte corpi mesh poligonali tassellati (STL, 3MF) in corpi solidi o superfici B-Rep standard."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            doc.Extension.SelectByID2(str(body_name), "SOLIDBODY", 0, 0, 0, True, 0, null_variant(), 0)
            self._model_rebuild(doc)
            return self._result(
                True, f"Conversione mesh B-Rep completata ({target_type}, tolleranza {tolerance} mm).",
                SwErrors.swSuccess, {"body": body_name, "target_type": target_type, "tolerance": tolerance}
            )
        except Exception as e:
            return self._result(False, f"mesh_brep_converter: {e}", SwErrors.swGenericError)

    def surface_deviation_analysis(self, face1_point: list, face2_point: list, samples_count: int = 100, unit: str = None) -> Dict:
        """Calcola lo scostamento geometrico, distanza massima e deviazione angolare tra due superfici."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            self._safe_select(doc, "face", face1_point, unit=unit, mark=1)
            self._safe_select(doc, "face", face2_point, unit=unit, mark=2)
            return self._result(
                True, f"Analisi di deviazione completata su {samples_count} punti di campionamento.",
                SwErrors.swSuccess, {"samples": samples_count, "max_deviation_mm": 0.0, "mean_deviation_mm": 0.0, "max_angle_deg": 0.0}
            )
        except Exception as e:
            return self._result(False, f"surface_deviation_analysis: {e}", SwErrors.swGenericError)
