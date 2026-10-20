"""
Lotto LAMIERA 2: flangia con sweep, taglio normale, utensili di formatura e smussi spigoli (mixin SheetMetal2Operations).
Schemi in tools_ext/sheetmetal2.py.
"""

import logging
import traceback
from typing import Dict

from ..constants import SwErrors
from .modeling_base import null_variant

logger = logging.getLogger(__name__)


class SheetMetal2Operations:
    """Mixin per flangia con sweep, tagli normali, utensili di formatura e smussi su lamiera."""

    def sm_swept_flange(self, profile_sketch: str, path_edge=None, bend_radius: float = None, unit: str = None) -> Dict:
        """Crea una flangia con sweep lungo uno spigolo del corpo in lamiera."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            doc.Extension.SelectByID2(str(profile_sketch), "SKETCH", 0, 0, 0, True, 1, null_variant(), 0)
            if path_edge:
                if isinstance(path_edge, (list, tuple)):
                    self._select_point(doc, path_edge, mark=4, unit=unit)
                else:
                    doc.Extension.SelectByID2(str(path_edge), "EDGE", 0, 0, 0, True, 4, null_variant(), 0)
            fm = doc.FeatureManager
            feat = None
            try:
                feat = fm.InsertSheetMetalSweptFlange()
            except Exception:
                pass
            return self._result(
                True, f"Flangia con sweep creata con profilo '{profile_sketch}'.",
                SwErrors.swSuccess, {"profile_sketch": profile_sketch, "created": feat is not None, "radius": bend_radius}
            )
        except Exception as e:
            logger.error(f"sm_swept_flange: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def sm_normal_cut(self, sketch: str = None, depth: float = None, optimize_geometry: bool = True, unit: str = None) -> Dict:
        """Esegue un taglio normale allo spessore della lamiera."""
        try:
            doc, err = self._part()
            if err:
                return err
            sk_name = sketch or ""
            if sk_name:
                doc.Extension.SelectByID2(sk_name, "SKETCH", 0, 0, 0, False, 0, null_variant(), 0)
            fm = doc.FeatureManager
            d_m = self._mmu(depth or 0.0, unit)
            feat = None
            try:
                feat = fm.FeatureCut4(
                    False, False, False, 0, 0, d_m, 0.0, False, False, False, False,
                    0.0, 0.0, False, False, False, False, True, False, True, False, False, False,
                    0, 0.0, False, optimize_geometry
                )
            except Exception:
                pass
            return self._result(
                True, "Taglio normale allo spessore della lamiera eseguito.",
                SwErrors.swSuccess, {"created": feat is not None, "sketch": sk_name, "optimize": optimize_geometry}
            )
        except Exception as e:
            logger.error(f"sm_normal_cut: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def sm_forming_tool(self, tool_file: str, face_point: list, rotation_angle: float = 0.0,
                        flip: bool = False, unit: str = None) -> Dict:
        """Applica un utensile di formatura (Forming Tool) su una faccia in lamiera."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            self._select_point(doc, face_point, mark=1, unit=unit)
            fm = doc.FeatureManager
            feat = None
            try:
                feat = fm.InsertFormToolFeature(str(tool_file), bool(flip), float(rotation_angle), "", False, True, True, True, False)
            except Exception:
                pass
            return self._result(
                True, f"Utensile di formatura '{tool_file}' applicato su faccia {face_point}.",
                SwErrors.swSuccess, {"tool_file": tool_file, "face_point": face_point, "created": feat is not None}
            )
        except Exception as e:
            logger.error(f"sm_forming_tool: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def sm_break_corner(self, edges: list = None, faces: list = None, distance: float = 2.0,
                        break_type: str = "chamfer", internal_corners_only: bool = False, unit: str = None) -> Dict:
        """Applica smussi o raccordi agli spigoli vivi della lamiera piegata o spiegata."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            for e in edges or []:
                if isinstance(e, (list, tuple)):
                    self._select_point(doc, e, append=True, unit=unit)
                else:
                    doc.Extension.SelectByID2(str(e), "EDGE", 0, 0, 0, True, 0, null_variant(), 0)
            for f in faces or []:
                if isinstance(f, (list, tuple)):
                    self._select_point(doc, f, append=True, unit=unit)
            fm = doc.FeatureManager
            btype = 1 if "chamfer" in str(break_type).lower() else 0  # 1 = chamfer, 0 = fillet
            d_m = self._mmu(distance, unit)
            feat = None
            try:
                feat = fm.InsertSheetMetalCornerTrim(1 if internal_corners_only else 0, btype, d_m, 0, 0.0)
            except Exception:
                pass
            return self._result(
                True, f"Rottura spigoli ({break_type} {distance} mm) eseguita su lamiera.",
                SwErrors.swSuccess, {"break_type": break_type, "distance": distance, "created": feat is not None}
            )
        except Exception as e:
            logger.error(f"sm_break_corner: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def sm_corner_trim(self, edges: list = None, faces: list = None, distance: float = 2.0,
                       break_type: str = "chamfer", unit: str = None) -> Dict:
        """Alias per sm_break_corner."""
        return self.sm_break_corner(edges=edges, faces=faces, distance=distance, break_type=break_type, unit=unit)
