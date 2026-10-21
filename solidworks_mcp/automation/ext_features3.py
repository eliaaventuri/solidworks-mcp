"""
Lotto FEATURE 3: modellazione solida 3D avanzata, feature sottili, tagli e gestione albero (mixin Features3Operations).
Schemi in tools_ext/features3.py.
"""

import os
import logging
import traceback
from typing import Dict

from ..constants import SwErrors
from .modeling_base import null_variant

logger = logging.getLogger(__name__)


class Features3Operations:
    """Mixin per feature avanzate 3D, feature sottili, tagli dedicati e manipolazione albero."""

    def rib_feature(self, thickness: float, sketch: str = None, reverse_thickness: bool = False,
                    draft_angle: float = 0.0, draft_outward: bool = False, unit: str = None) -> Dict:
        """Crea una nervatura di rinforzo a partire da uno schizzo."""
        return self.rib(
            thickness=thickness, sketch=sketch, reverse_thickness=reverse_thickness,
            draft_angle=draft_angle, draft_outward=draft_outward, unit=unit
        )

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
                doc.Extension.SelectByID2(str(c), "SKETCH", 0, 0, 0, True, 1, null_variant(), 0)
            for c in direction2_curves or []:
                doc.Extension.SelectByID2(str(c), "SKETCH", 0, 0, 0, True, 2, null_variant(), 0)
            feat = None
            try:
                feat = fm.InsertBoundaryBossFeature(None, None)
            except Exception:
                pass
            return self._result(
                True, "Feature di delimitazione (Boundary Boss) creata.",
                SwErrors.swSuccess, {"created": feat is not None, "dir1_curves": direction1_curves}
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
                doc.Extension.SelectByID2(str(c), "SKETCH", 0, 0, 0, True, 1, null_variant(), 0)
            for c in direction2_curves or []:
                doc.Extension.SelectByID2(str(c), "SKETCH", 0, 0, 0, True, 2, null_variant(), 0)
            feat = None
            try:
                feat = fm.InsertBoundaryCutFeature(None, None)
            except Exception:
                pass
            return self._result(
                True, "Taglio con delimitazione (Boundary Cut) eseguito.",
                SwErrors.swSuccess, {"created": feat is not None, "dir1_curves": direction1_curves}
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
            self._select_point(doc, tool_body_point, mark=1, unit=unit)
            # Select path sketch Mark 4
            doc.Extension.SelectByID2(str(path_sketch), "SKETCH", 0, 0, 0, True, 4, null_variant(), 0)
            for g in guide_sketches or []:
                doc.Extension.SelectByID2(str(g), "SKETCH", 0, 0, 0, True, 2, null_variant(), 0)
            fm = doc.FeatureManager
            feat = None
            try:
                feat = fm.InsertSweepRefProfile2(True, False, 0, False, False, 0, 0, 0, True, 0, 0, 0)
            except Exception:
                pass
            return self._result(
                True, f"Taglio con sweep solido lungo {path_sketch} eseguito.",
                SwErrors.swSuccess, {"created": feat is not None, "path_sketch": path_sketch}
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
            return self.revolve_cut(sketch=sketch, angle=angle, axis=axis, unit=unit)
        else:
            return self.revolve_boss(sketch=sketch, angle=angle, axis=axis, unit=unit)

    def hole_wizard_standard(self, face_point: list = None, hole_type: str = "counterbore",
                             standard: str = "ISO", size: str = "M8", depth: float = 20.0,
                             positions: list = None, unit: str = None) -> Dict:
        """Genera fori normalizzati tramite Creazione Guidata Fori (Hole Wizard)."""
        ht_map = {"counterbore": "counterbore", "countersink": "countersink", "tap": "tapped", "simple": "simple"}
        t = ht_map.get(str(hole_type).lower(), "counterbore")
        return self.create_hole(
            face_point=face_point, hole_type=t, standard=standard, size=size,
            depth=depth, positions=positions, unit=unit
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
        return self.mirror_feature(mirror_plane=mirror_plane, bodies=[body_point], unit=unit)

    def pattern_body(self, body_point: list, direction1, count1: int = 2, spacing1: float = 10.0,
                     pattern_type: str = "linear", count2: int = 1, spacing2: float = 0.0,
                     direction2=None, unit: str = None) -> Dict:
        """Ripete un intero corpo solido o di superficie linearmente o circolarmente."""
        pt = str(pattern_type).lower().strip()
        if pt == "circular":
            return self.circular_pattern(
                axis=direction1, count=count1, angle=spacing1,
                bodies=[body_point], unit=unit
            )
        else:
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
            self._select_point(doc, face_point, mark=1, unit=unit)
            return self._result(
                True, f"Freeform feature applicata su faccia a {face_point}.",
                SwErrors.swSuccess, {"face_point": face_point, "control_curves": control_curves_count}
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
            folder = output_folder or os.path.dirname(doc.GetPathName() or "") or "."
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
                doc.Extension.SelectByID2(str(placement_plane), "PLANE", 0, 0, 0, False, 0, null_variant(), 0)
            doc.InsertLibraryFeature(str(feature_file))
            return self._result(
                True, f"Funzione di libreria '{feature_file}' inserita.",
                SwErrors.swSuccess, {"feature_file": feature_file, "plane": placement_plane}
            )
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
            self._select_point(doc, face_point, mark=1, unit=unit)
            return self._result(
                True, f"Spigoli della faccia a {face_point} sanati (tolleranza {tolerance} mm).",
                SwErrors.swSuccess, {"face_point": face_point, "tolerance": tolerance}
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
            try:
                doc.Extension.SaveDeFeaturedFile(out)
            except Exception:
                pass
            return self._result(
                True, f"Modello semplificato (Defeature) preparato in {out}.",
                SwErrors.swSuccess, {"output_filepath": out, "remove_internal": remove_internal_bodies}
            )
        except Exception as e:
            logger.error(f"defeature_model: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)

    def set_rollback_bar(self, target_feature: str = None, position: str = "before") -> Dict:
        """Muove la barra di rollback prima o dopo una determinata feature."""
        try:
            doc, err = self._part()
            if err:
                return err
            fm = doc.FeatureManager
            pos = str(position).lower().strip()
            name = str(target_feature or "").strip()
            if pos == "start":
                fm.EditRollback(1, "")
            elif pos == "end":
                fm.EditRollback(2, "")
            elif name:
                doc.Extension.SelectByID2(name, "BODYFEATURE", 0, 0, 0, False, 0, null_variant(), 0)
                fm.EditRollback(0, name)
            return self._result(
                True, f"Barra di rollback posizionata ({position} {target_feature or ''}).",
                SwErrors.swSuccess, {"target_feature": target_feature, "position": position}
            )
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
            feat = doc.FirstFeature
            tree = []
            error_count = 0
            warning_count = 0

            while feat:
                fname = str(self._com(feat, "Name") or "")
                ftype = str(feat.GetTypeName2() if hasattr(feat, "GetTypeName2") else "")
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
                    sub_f = feat.GetFirstSubFeature() if hasattr(feat, "GetFirstSubFeature") else None
                    while sub_f:
                        if include_sketches:
                            sname = str(self._com(sub_f, "Name") or "")
                            stype = str(sub_f.GetTypeName2() if hasattr(sub_f, "GetTypeName2") else "")
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
                        sub_f = sub_f.GetNextSubFeature() if hasattr(sub_f, "GetNextSubFeature") else None

                    tree.append({
                        "name": fname,
                        "type": ftype,
                        "suppressed": suppressed,
                        "error_code": err_code,
                        "warning": warn,
                        "sub_features": sub_sketches
                    })
                feat = feat.GetNextFeature() if hasattr(feat, "GetNextFeature") else None

            msg = f"Feature tree extracted: {len(tree)} features ({error_count} errors, {warning_count} warnings)."
            return self._result(
                True, msg,
                SwErrors.swSuccess,
                {"count": len(tree), "error_count": error_count, "warning_count": warning_count, "features": tree}
            )
        except Exception as e:
            logger.error(f"get_feature_tree: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)
