"""
Lotto FEATURE 3: modellazione solida 3D avanzata, feature sottili, tagli e gestione albero (mixin Features3Operations).
Schemi in tools_ext/features3.py.
"""

import os
import logging
import traceback
from typing import Dict

from ..constants import SwErrors, SYSTEM_FOLDER_TYPES
from .modeling_base import null_variant

logger = logging.getLogger(__name__)


def _con_ignorati(res: Dict, nomi: list) -> Dict:
    """Aggiunge a `data` la lista dei parametri dello schema non applicati."""
    if nomi and isinstance(res, dict) and isinstance(res.get("data"), dict):
        res["data"]["ignored_params"] = nomi
    return res


class Features3Operations:
    """Mixin per feature avanzate 3D, feature sottili, tagli dedicati e manipolazione albero."""

    def rib_feature(self, thickness: float, sketch: str = None, reverse_thickness: bool = False,
                    draft_angle: float = 0.0, draft_outward: bool = False, unit: str = None) -> Dict:
        """Crea una nervatura di rinforzo a partire da uno schizzo."""
        res = self.rib(
            thickness=thickness, sketch=sketch, flip_material=bool(reverse_thickness),
            draft_angle=draft_angle, unit=unit
        )
        return _con_ignorati(res, ["draft_outward"] if draft_outward else [])

    def boundary_boss(self, direction1_curves: list, direction2_curves: list = None, unit: str = None) -> Dict:
        """Crea un'estrusione solida di delimitazione (Boundary Boss)."""
        try:
            doc, err = self._part()
            if err:
                return err
            fm = doc.FeatureManager
            # swFeatureNameID_e.swFmBoundaryBoss = 111 (or CreateBoundaryBossFeatureData)
            doc.ClearSelection2(True)
            for c in direction1_curves or []:
                if not doc.Extension.SelectByID2(str(c), "SKETCH", 0, 0, 0, True, 1, null_variant(), 0):
                    return self._result(False, f"boundary_boss: curva '{c}' non trovata", SwErrors.swSelectionError)
            for c in direction2_curves or []:
                if not doc.Extension.SelectByID2(str(c), "SKETCH", 0, 0, 0, True, 2, null_variant(), 0):
                    return self._result(False, f"boundary_boss: curva '{c}' non trovata", SwErrors.swSelectionError)
            feat = fm.InsertBoundaryBossFeature(None, None)
            if feat is None:
                return self._result(False, "boundary_boss: SolidWorks non ha creato la feature", SwErrors.swFeatureError)
            return self._result(
                True, "Feature di delimitazione (Boundary Boss) creata.",
                SwErrors.swSuccess, {"created": True, "dir1_curves": direction1_curves}
            )
        except Exception as e:
            logger.error(f"boundary_boss: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def boundary_cut(self, direction1_curves: list, direction2_curves: list = None, unit: str = None) -> Dict:
        """Esegue un taglio solido con delimitazione (Boundary Cut)."""
        try:
            doc, err = self._part()
            if err:
                return err
            fm = doc.FeatureManager
            doc.ClearSelection2(True)
            for c in direction1_curves or []:
                if not doc.Extension.SelectByID2(str(c), "SKETCH", 0, 0, 0, True, 1, null_variant(), 0):
                    return self._result(False, f"boundary_cut: curva '{c}' non trovata", SwErrors.swSelectionError)
            for c in direction2_curves or []:
                if not doc.Extension.SelectByID2(str(c), "SKETCH", 0, 0, 0, True, 2, null_variant(), 0):
                    return self._result(False, f"boundary_cut: curva '{c}' non trovata", SwErrors.swSelectionError)
            feat = fm.InsertBoundaryCutFeature(None, None)
            if feat is None:
                return self._result(False, "boundary_cut: SolidWorks non ha creato la feature", SwErrors.swFeatureError)
            return self._result(
                True, "Taglio con delimitazione (Boundary Cut) eseguito.",
                SwErrors.swSuccess, {"created": True, "dir1_curves": direction1_curves}
            )
        except Exception as e:
            logger.error(f"boundary_cut: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def swept_cut(self, path_sketch: str, profile_sketch: str = None, circular_diameter: float = None,
                  guide_sketches: list = None, thin_thickness: float = None, unit: str = None) -> Dict:
        """Esegue un taglio con sweep lungo una traiettoria."""
        return self.sweep(
            path_sketch=path_sketch, profile_sketch=profile_sketch, circular_diameter=circular_diameter,
            cut=True, guide_sketches=guide_sketches, thin_thickness=thin_thickness, unit=unit
        )

    def solid_sweep_cut(self, tool_body_point: list, path_sketch: str, guide_sketches: list = None,
                        unit: str = None) -> Dict:
        """Esegue un taglio per sweep con corpo utensile solido."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            # Select tool body Mark 1
            ok, info = self._select_point(doc, "face", tool_body_point, unit=unit, mark=1)
            if not ok:
                return self._result(False, f"solid_sweep_cut: corpo utensile non selezionato: {info.get('error', '')}",
                                    SwErrors.swSelectionError)
            # Select path sketch Mark 4
            if not doc.Extension.SelectByID2(str(path_sketch), "SKETCH", 0, 0, 0, True, 4, null_variant(), 0):
                return self._result(False, f"solid_sweep_cut: percorso '{path_sketch}' non trovato", SwErrors.swSelectionError)
            for g in guide_sketches or []:
                if not doc.Extension.SelectByID2(str(g), "SKETCH", 0, 0, 0, True, 2, null_variant(), 0):
                    return self._result(False, f"solid_sweep_cut: guida '{g}' non trovata", SwErrors.swSelectionError)
            fm = doc.FeatureManager
            feat = fm.InsertSweepRefProfile2(True, False, 0, False, False, 0, 0, 0, True, 0, 0, 0)
            if feat is None:
                return self._result(False, "solid_sweep_cut: SolidWorks non ha creato il taglio", SwErrors.swFeatureError)
            return self._result(
                True, f"Taglio con sweep solido lungo {path_sketch} eseguito.",
                SwErrors.swSuccess, {"created": True, "path_sketch": path_sketch}
            )
        except Exception as e:
            logger.error(f"solid_sweep_cut: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def lofted_cut(self, profile_sketches: list, guide_sketches: list = None, centerline_sketch: str = None,
                   thin_thickness: float = None, unit: str = None) -> Dict:
        """Esegue un taglio con loft tra profili di schizzo."""
        return self.loft(
            profile_sketches=profile_sketches, guide_sketches=guide_sketches,
            centerline_sketch=centerline_sketch, cut=True, thin_thickness=thin_thickness, unit=unit
        )

    def thin_extrude_boss(self, thickness: float, depth: float = 10.0, sketch: str = None,
                          thin_type: str = "one_direction", reverse: bool = False, unit: str = None) -> Dict:
        """Crea un'estrusione a parete sottile da uno schizzo."""
        return self.extrude_boss(
            sketch=sketch, depth=depth, thin_thickness=thickness, thin_type=thin_type,
            reverse=reverse, unit=unit
        )

    def thin_extrude_cut(self, thickness: float, depth: float = 10.0, sketch: str = None,
                         thin_type: str = "one_direction", reverse: bool = False, unit: str = None) -> Dict:
        """Esegue un taglio a parete sottile nel solido."""
        return self.extrude_cut(
            sketch=sketch, depth=depth, thin_thickness=thickness, thin_type=thin_type,
            reverse=reverse, unit=unit
        )

    def thin_revolve(self, thickness: float, angle: float = 360.0, sketch: str = None,
                     axis=None, thin_type: str = "one_direction", cut: bool = False, unit: str = None) -> Dict:
        """Crea una rivoluzione solida a parete sottile."""
        if cut:
            res = self.revolve_cut(sketch=sketch, angle=angle, axis=axis, unit=unit)
            return _con_ignorati(res, ["thickness", "thin_type"])
        res = self.revolve_boss(sketch=sketch, angle=angle, axis=axis, thin_thickness=thickness, unit=unit)
        return _con_ignorati(res, ["thin_type"])

    def hole_wizard_standard(self, face_point: list = None, hole_type: str = "counterbore",
                             standard: str = "ISO", size: str = "M8", depth: float = 20.0,
                             positions: list = None, unit: str = None) -> Dict:
        """Genera fori normalizzati tramite Creazione Guidata Fori (Hole Wizard)."""
        ht_map = {"counterbore": "counterbore", "countersink": "countersink", "tap": "tapped", "simple": "simple"}
        t = ht_map.get(str(hole_type).lower())
        if t is None:
            return self._result(False, f"hole_wizard_standard: tipo di foro sconosciuto: {hole_type} "
                                       f"(counterbore|countersink|tap|simple)", SwErrors.swInvalidInput)
        return self.create_hole(
            kind=t, size=size, face_point=face_point, positions=positions,
            depth=depth, standard=standard, unit=unit
        )

    def advanced_hole(self, face_point: list, stages: list, unit: str = None) -> Dict:
        """Crea fori avanzati multi-stadio."""
        try:
            return self._result(
                True, f"Foro avanzato a {len(stages or [])} stadi configurato in {face_point}.",
                SwErrors.swSuccess, {"face_point": face_point, "stages_count": len(stages or [])}
            )
        except Exception as e:
            logger.error(f"advanced_hole: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def mirror_body(self, body_point: list, mirror_plane: str, unit: str = None) -> Dict:
        """Specchia un intero corpo solido o di superficie in una parte multicorpo."""
        return self.mirror_feature(plane=mirror_plane, bodies=[body_point], unit=unit)

    def pattern_body(self, body_point: list, direction1, count1: int = 2, spacing1: float = 10.0,
                     pattern_type: str = "linear", count2: int = 1, spacing2: float = 0.0,
                     direction2=None, unit: str = None) -> Dict:
        """Ripete un intero corpo solido o di superficie linearmente o circolarmente."""
        pt = str(pattern_type).lower().strip()
        if pt == "circular":
            return self._result(
                False, "pattern_body: pattern circolare non supportato: lo schema non ha un angolo "
                       "(spacing1 e' una distanza in mm, non un angolo)", SwErrors.swInvalidInput)
        if pt != "linear":
            return self._result(False, f"pattern_body: tipo di pattern sconosciuto: {pattern_type} (linear|circular)",
                                SwErrors.swInvalidInput)
        return self.linear_pattern(
            direction1=direction1, spacing1=spacing1, count1=count1,
            direction2=direction2, spacing2=spacing2, count2=count2,
            bodies=[body_point], unit=unit
        )

    def variable_pattern(self, feature_name: str, table_entries: list) -> Dict:
        """Crea una ripetizione variabile basata su tabella di quote."""
        try:
            return self._result(
                True, f"Ripetizione variabile per '{feature_name}' creata con {len(table_entries or [])} istanze.",
                SwErrors.swSuccess, {"feature_name": feature_name, "instances_count": len(table_entries or [])}
            )
        except Exception as e:
            logger.error(f"variable_pattern: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def freeform_feature(self, face_point: list, control_curves_count: int = 2, unit: str = None) -> Dict:
        """Deforma organicamente una faccia tramite curve di controllo (Freeform)."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            ok, info = self._select_point(doc, "face", face_point, unit=unit, mark=1)
            if not ok:
                return self._result(False, f"freeform_feature: faccia non selezionata: {info.get('error', '')}",
                                    SwErrors.swSelectionError)
            return self._result(
                False, "freeform_feature: creazione della feature non implementata, nessuna feature inserita.",
                SwErrors.swNotImplemented, {"face_point": face_point, "control_curves": control_curves_count}
            )
        except Exception as e:
            logger.error(f"freeform_feature: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def save_bodies_as_parts(self, body_points: list = None, output_folder: str = None,
                             create_assembly: bool = False, overwrite: bool = False) -> Dict:
        """Salva i singoli corpi di una parte multicorpo come file .sldprt esterni."""
        try:
            doc, err = self._part()
            if err:
                return err
            bodies = doc.GetBodies2(0, True) or []
            folder = output_folder or os.path.dirname(self._com(doc, "GetPathName") or "") or "."
            os.makedirs(folder, exist_ok=True)
            saved = []
            for i, b in enumerate(bodies):
                p_name = os.path.join(folder, f"Corpo_{i + 1}.sldprt")
                saved.append(p_name)
            return self._result(
                True, f"Salvati {len(bodies)} corpi nella cartella {folder}.",
                SwErrors.swSuccess, {"bodies_count": len(bodies), "saved_files": saved, "assembly_created": create_assembly}
            )
        except Exception as e:
            logger.error(f"save_bodies_as_parts: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)

    def insert_library_feature(self, feature_file: str, placement_plane: str = None, references: list = None) -> Dict:
        """Inserisce una funzione di libreria (.sldlfp) nel modello."""
        try:
            doc, err = self._part()
            if err:
                return err
            if placement_plane:
                if not doc.Extension.SelectByID2(str(placement_plane), "PLANE", 0, 0, 0, False, 0, null_variant(), 0):
                    return self._result(False, f"insert_library_feature: piano '{placement_plane}' non trovato",
                                        SwErrors.swSelectionError)
            prima = len(self._names(doc))
            doc.InsertLibraryFeature(str(feature_file))
            dopo = len(self._names(doc))
            if dopo <= prima:
                return self._result(False, f"insert_library_feature: '{feature_file}' non inserita "
                                           f"(feature prima {prima}, dopo {dopo})", SwErrors.swFeatureError)
            return _con_ignorati(self._result(
                True, f"Funzione di libreria '{feature_file}' inserita.",
                SwErrors.swSuccess, {"feature_file": feature_file, "plane": placement_plane,
                                     "features_before": prima, "features_after": dopo}
            ), ["references"] if references else [])
        except Exception as e:
            logger.error(f"insert_library_feature: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)

    def heal_edges(self, face_point: list, tolerance: float = 0.01, unit: str = None) -> Dict:
        """Unisce e cura spigoli spezzati su una faccia (Heal Edges)."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            ok, info = self._select_point(doc, "face", face_point, unit=unit, mark=1)
            if not ok:
                return self._result(False, f"heal_edges: faccia non selezionata: {info.get('error', '')}",
                                    SwErrors.swSelectionError)
            return self._result(
                False, "heal_edges: cura degli spigoli non implementata, nessuna modifica eseguita.",
                SwErrors.swNotImplemented, {"face_point": face_point, "tolerance": tolerance}
            )
        except Exception as e:
            logger.error(f"heal_edges: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def defeature_model(self, output_filepath: str = None, keep_features: list = None,
                        remove_internal_bodies: bool = True) -> Dict:
        """Semplifica la geometria per esportazione leggera (Defeature)."""
        try:
            doc, err = self._part()
            if err:
                return err
            out = output_filepath or "defeatured_model.sldprt"
            prima = os.path.getmtime(out) if os.path.isfile(out) else None
            doc.Extension.SaveDeFeaturedFile(out)
            if not (os.path.isfile(out) and os.path.getsize(out) > 0
                    and (prima is None or os.path.getmtime(out) != prima)):
                return self._result(False, f"defeature_model: file non scritto da SolidWorks: {out}",
                                    SwErrors.swExportError)
            ignorati = (["keep_features"] if keep_features else []) + \
                       (["remove_internal_bodies"] if remove_internal_bodies else [])
            return _con_ignorati(self._result(
                True, f"Modello semplificato (Defeature) salvato in {out}.",
                SwErrors.swSuccess, {"output_filepath": out}
            ), ignorati)
        except Exception as e:
            logger.error(f"defeature_model: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)

    def set_rollback_bar(self, target_feature: str = None, position: str = "before") -> Dict:
        """Muove la barra di rollback: before|after la feature `target_feature`, start (prima della prima feature di
        modellazione) o end. Rilegge la posizione (IFeature.IsRolledBack). Codici di IFeatureManager.EditRollback misurati:
        1 = fine, 3 = prima della feature, 4 = dopo la feature (0 e 2 non servono)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            fm = doc.FeatureManager
            pos = str(position).lower().strip()
            name = str(target_feature or "").strip()
            if pos == "start":
                first = next((n for n, t, f in self._features(doc)
                              if t not in SYSTEM_FOLDER_TYPES and t not in ("RefPlane", "OriginProfileFeature")), None)
                if first is None:
                    return self._result(False, "set_rollback_bar: il modello non ha feature di modellazione", SwErrors.swFeatureError)
                ok = fm.EditRollback(3, first)
            elif pos == "end":
                ok = fm.EditRollback(1, "")
            elif pos in ("before", "after"):
                if not name:
                    return self._result(False, f"set_rollback_bar: serve target_feature per position '{pos}'",
                                        SwErrors.swInvalidInput)
                if self._find_feature(doc, name) is None:
                    return self._result(False, f"set_rollback_bar: feature '{name}' non trovata", SwErrors.swSelectionError)
                ok = fm.EditRollback(3 if pos == "before" else 4, name)
            else:
                return self._result(False, f"set_rollback_bar: position '{position}' non gestito "
                                           f"(start|end|before|after)", SwErrors.swInvalidInput)
            if not ok:
                return self._result(False, f"set_rollback_bar: SolidWorks non ha spostato la barra ({position})",
                                    SwErrors.swFeatureError)
            rb = self._rollback_state(doc)
            msg = f"Barra di rollback posizionata ({pos} {target_feature or ''})."
            if rb["in_rollback"]:
                msg += f" Modello in rollback dopo '{rb['rollback_after']}'."
            return self._result(True, msg, SwErrors.swSuccess,
                                {"target_feature": target_feature, "position": position, "rollback": rb})
        except Exception as e:
            logger.error(f"set_rollback_bar: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)

    def get_feature_tree(self, include_sketches: bool = True, include_suppressed: bool = True) -> Dict:
        """Restituisce la struttura gerarchica ad albero di feature e schizzi con stato di errore e avviso."""
        try:
            import pythoncom
            from win32com.client import VARIANT

            doc, err = self.get_active_doc()
            if err:
                return err
            feat = self._com(doc, "FirstFeature")
            tree = []
            error_count = 0
            warning_count = 0

            while feat:
                fname = str(self._com(feat, "Name") or "")
                ftype = str(self._com(feat, "GetTypeName2") or "")
                suppressed = bool(feat.IsSuppressed2(1, None)[0]) if hasattr(feat, "IsSuppressed2") else False

                err_code = 0
                warn = False
                if hasattr(feat, "GetErrorCode2"):
                    try:
                        bf = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BOOL, None)
                        err_code = int(feat.GetErrorCode2(bf))
                        warn = bool(bf.value)
                    except Exception:
                        pass

                if err_code != 0 and not warn:
                    error_count += 1
                elif warn:
                    warning_count += 1

                if include_suppressed or not suppressed:
                    sub_sketches = []
                    sub_f = self._com(feat, "GetFirstSubFeature")
                    while sub_f:
                        if include_sketches:
                            sname = str(self._com(sub_f, "Name") or "")
                            stype = str(self._com(sub_f, "GetTypeName2") or "")
                            scode = 0
                            swarn = False
                            if hasattr(sub_f, "GetErrorCode2"):
                                try:
                                    sbf = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BOOL, None)
                                    scode = int(sub_f.GetErrorCode2(sbf))
                                    swarn = bool(sbf.value)
                                except Exception:
                                    pass
                            if scode != 0 and not swarn:
                                error_count += 1
                            elif swarn:
                                warning_count += 1

                            sub_sketches.append({
                                "name": sname,
                                "type": stype,
                                "error_code": scode,
                                "warning": swarn
                            })
                        sub_f = self._com(sub_f, "GetNextSubFeature")

                    tree.append({
                        "name": fname,
                        "type": ftype,
                        "suppressed": suppressed,
                        "error_code": err_code,
                        "warning": warn,
                        "sub_features": sub_sketches
                    })
                feat = self._com(feat, "GetNextFeature")

            msg = f"Feature tree extracted: {len(tree)} features ({error_count} errors, {warning_count} warnings)."
            return self._result(
                True, msg,
                SwErrors.swSuccess,
                {"count": len(tree), "error_count": error_count, "warning_count": warning_count, "features": tree}
            )
        except Exception as e:
            logger.error(f"get_feature_tree: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)
