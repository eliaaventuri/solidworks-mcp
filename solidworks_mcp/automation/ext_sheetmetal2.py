"""
Lotto LAMIERA 2: flangia con sweep, taglio normale, utensili di formatura e smussi spigoli (mixin SheetMetal2Operations).
Schemi in tools_ext/sheetmetal2.py.
"""

import logging
import os
import math
import traceback
import win32com.client
import pythoncom
from typing import Dict

from ..constants import SwErrors
from .modeling_base import null_variant

logger = logging.getLogger(__name__)


class SheetMetal2Operations:
    """Mixin per flangia con sweep, tagli normali, utensili di formatura e smussi su lamiera."""

    def sm_normal_cut(self, sketch: str = None, depth: float = None, optimize_geometry: bool = True, unit: str = None) -> Dict:
        """Esegue un taglio normale allo spessore della lamiera."""
        try:
            doc, err = self._part()
            if err:
                return err
            # (misurato 2026-11-19) con lo schizzo aperto il volume letto vale 0: lo schizzo si chiude, si misura e si
            # riseleziona per nome; il taglio "passante" va fatto nei due versi (lo schizzo sta su una faccia della lamiera)
            sk_name, err = self._resolve_sketch(doc, sketch)
            if err:
                return err
            self._exit_sketch(doc)
            doc.ClearSelection2(True)
            if not self._select_feature(doc, sk_name, False, 0):
                return self._result(False, f"sm_normal_cut: schizzo '{sk_name}' non selezionabile", SwErrors.swSelectionError)
            fm = doc.FeatureManager
            # (revisione 2026-11-12) prima depth mancante diventava una profondita' cieca di 0 mm (lo schema dice "tutto lo
            # spessore"): ora senza depth il taglio e' passante (T1 = 1, swEndCondThroughAll); controllo del volume.
            if depth is not None and float(depth) <= 0:
                return self._result(False, "sm_normal_cut: depth deve essere > 0 (oppure omesso = tutto lo spessore).",
                                    SwErrors.swInvalidInput)
            d_m = self._mmu(float(depth), unit) if depth is not None else 0.0
            doc.ClearSelection2(True)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            # tentativi: (sd, flip, T1, T2) - passante nei due versi, oppure cieco da un lato e poi dall'altro
            tries = [(False, False, 1, 1)] if depth is None else [(True, False, 0, 0), (True, True, 0, 0)]
            feat = None
            for sd_, flip, t1, t2 in tries:
                doc.ClearSelection2(True)
                self._select_feature(doc, sk_name, False, 0)
                feat = fm.FeatureCut4(
                    sd_, flip, False, t1, t2, d_m, d_m, False, False, False, False,
                    0.0, 0.0, False, False, False, False, True, False, True, False, False, False,
                    0, 0.0, False, optimize_geometry
                )
                if feat is not None and self._volume_m3(doc) < v0 - 1e-12:
                    break
                if feat is not None:          # creato ma senza effetto (verso sbagliato): via e si prova l'altro
                    self._delete_features(doc, [x["name"] for x in self._new_features(doc, before) if x["type"] != "ProfileFeature"])
                    feat = None
            if feat is None:
                return self._result(False, "sm_normal_cut: taglio normale allo spessore non creato da SolidWorks",
                                    SwErrors.swFeatureError, {"created": False, "sketch": sk_name})
            v1 = self._volume_m3(doc)
            data = {"created": True, "sketch": sk_name, "optimize": optimize_geometry,
                    "depth": depth if depth is not None else "through_all", "volume_removed_mm3": round((v0 - v1) * 1e9, 4)}
            if v0 - v1 <= 1e-12:
                self._delete_features(doc, [x["name"] for x in self._new_features(doc, before) if x["type"] != "ProfileFeature"])
                return self._result(False, "sm_normal_cut: il taglio non toglie materiale (schizzo fuori dalla lamiera?): "
                                    "eliminato.", SwErrors.swFeatureError, data)
            return self._result(
                True, f"Taglio normale allo spessore eseguito: tolti {data['volume_removed_mm3']} mm3.",
                SwErrors.swSuccess, data
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
            ok, info = self._select_point(doc, "face", face_point, unit=unit, mark=1)
            if not ok:
                return self._result(False, f"sm_forming_tool: faccia {face_point} non selezionata: {info.get('error', info)}",
                                    SwErrors.swSelectionError)
            fm = doc.FeatureManager
            path = os.path.abspath(str(tool_file))
            if not os.path.isfile(path):
                return self._result(False, f"File non trovato: {path}", SwErrors.swFileNotFoundError)
            res = self._create_checked(
                doc, f"Utensile {os.path.basename(path)}",
                lambda: fm.InsertFormToolFeature(path, bool(flip), math.radians(float(rotation_angle)), "", False, True,
                                                 True, True, False),
                extra={"tool_file": path, "face_point": face_point})
            return res
        except Exception as e:
            logger.error(f"sm_forming_tool: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def sm_break_corner(self, edges: list = None, faces: list = None, distance: float = 2.0,
                        break_type: str = "chamfer", unit: str = None) -> Dict:
        """Applica smussi o raccordi agli spigoli vivi della lamiera piegata o spiegata."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            for e in edges or []:
                if isinstance(e, (list, tuple)):
                    ok, info = self._select_point(doc, "edge", e, unit=unit, append=True)
                    if not ok:
                        return self._result(False, f"sm_break_corner: spigolo {e} non selezionato: {info.get('error', info)}",
                                            SwErrors.swSelectionError)
                else:
                    if not doc.Extension.SelectByID2(str(e), "EDGE", 0, 0, 0, True, 0, null_variant(), 0):
                        return self._result(False, f"sm_break_corner: spigolo '{e}' non selezionato", SwErrors.swSelectionError)
            for f in faces or []:
                if isinstance(f, (list, tuple)):
                    ok, info = self._select_point(doc, "face", f, unit=unit, append=True)
                    if not ok:
                        return self._result(False, f"sm_break_corner: faccia {f} non selezionata: {info.get('error', info)}",
                                            SwErrors.swSelectionError)
            # (revisione 19/11) prima InsertSheetMetalCornerTrim (e' il RIFILA ANGOLO del modello spianato): sul modello
            # piegato non faceva nulla. Lo spezza-angolo e' IModelDoc2.InsertSheetMetalBreakCorner(tipo, distanza), void:
            # l'esito si legge da feature nuove, errori e volume
            if not int(doc.SelectionManager.GetSelectedObjectCount2(-1)):
                return self._result(False, "sm_break_corner: indica gli spigoli (lungo lo spessore) o le facce.",
                                    SwErrors.swInvalidInput)
            btype = 1 if "chamfer" in str(break_type).lower() else 0          # swBreakCornerTypes: 1 smusso, 0 raccordo
            d_m = self._mmu(distance, unit)
            ents = [None] * int(doc.SelectionManager.GetSelectedObjectCount2(-1))
            return self._create_checked(
                doc, f"Angoli spezzati ({'chamfer' if btype else 'fillet'} {distance})",
                lambda: doc.InsertSheetMetalBreakCorner(btype, d_m),
                extra={"break_type": "chamfer" if btype else "fillet", "distance": distance, "entities": len(ents)})
        except Exception as e:
            logger.error(f"sm_break_corner: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

