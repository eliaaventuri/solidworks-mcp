"""
SolidWorks Modeling Operations (mixin)
--------------------------------------
Feature 3D (estrusione con condizioni finali, rivoluzione, sweep, loft, shell, nervatura, sformo, raccordi e
smussi autonomi), ripetizioni, specchiature, fori guidati, geometria di riferimento, gestione delle feature.

Tutte le selezioni 3D avvengono per COORDINATE (punto sull'entita', modello, unita' `unit`) tramite
ModelingBase._select_point. Gli schizzi si indicano per nome ("Schizzo1") o, se omesso, e' quello attivo
(che viene chiuso) oppure l'ultimo.

Trappole API scoperte (SW 2026, late binding, vedi STATO_STORICO.md):
 - Estrusioni: MidPlane=6, ThroughAllBoth=9 (il vecchio cut_extrude usava 2 = "fino al successivo").
 - Smusso: InsertFeatureChamfer(Options=0, tipo 1=angolo-distanza | 2=distanza-distanza, ...); il tipo 16 non scava.
 - Raccordo: FeatureFillet3(Options=3, R1, R2, Rho, 0, 0, 0, None x7).
 - Shell: doc.InsertFeatureShell(t, outward) e' void (nessuna feature restituita).
 - Specchia corpo: il corpo si seleziona con Mark=256 (piano Mark=2, feature Mark=1); con Mark=1 InsertMirrorFeature2 restituisce None.
 - Foro guidato: HoleWizard5 posiziona il foro nel PUNTO DI PICK della faccia (SelectData.X/Y/Z);
   gli argomenti Value1..12 devono avere angolo punta (Value5/Value6/Value2 secondo il tipo) NON nullo, altrimenti
   la ricerca nel database fallisce e si ottengono valori di default in pollici (50.8 mm...).
"""

import math
import logging
import traceback
from typing import Optional, Dict, List, Any

import win32com.client
import pythoncom

from ..constants import SwErrors
from .modeling_base import ModelingBase, null_variant, r8_array
from .sketch_constraints import SketchConstraintOperations
from ..utils.sw_lang import lang_folders

logger = logging.getLogger(__name__)

END_CONDITIONS = {
    "blind": 0, "through_all": 1, "through_all_both": 9, "up_to_next": 2, "up_to_surface": 4,
    "offset_from_surface": 5, "mid_plane": 6, "symmetric": 6, "up_to_body": 7,
}

# diametri ISO 273 (serie media) e punte per maschiatura, mm
CLEARANCE_MM = {"M3": 3.4, "M4": 4.5, "M5": 5.5, "M6": 6.6, "M8": 9.0, "M10": 11.0, "M12": 13.5,
                "M14": 15.5, "M16": 17.5, "M20": 22.0}
TAP_DRILL_MM = {"M3": 2.5, "M4": 3.3, "M5": 4.2, "M6": 5.0, "M8": 6.8, "M10": 8.5, "M12": 10.2,
                "M14": 12.0, "M16": 14.0, "M20": 17.5}
NOMINAL_MM = {"M3": 3, "M4": 4, "M5": 5, "M6": 6, "M8": 8, "M10": 10, "M12": 12, "M14": 14, "M16": 16, "M20": 20}

# Ø di passaggio ISO 273 (serie fine / media / grossa), mm
CLEARANCE_FIT_MM = {
    "close": {"M3": 3.2, "M4": 4.3, "M5": 5.3, "M6": 6.4, "M8": 8.4, "M10": 10.5, "M12": 13.0, "M14": 15.0, "M16": 17.0, "M20": 21.0},
    "normal": CLEARANCE_MM,
    "loose": {"M3": 3.6, "M4": 4.8, "M5": 5.8, "M6": 7.0, "M8": 10.0, "M10": 12.0, "M12": 14.5, "M14": 16.5, "M16": 18.5, "M20": 24.0},
}
COARSE_PITCH = {"M3": "0.5", "M4": "0.7", "M5": "0.8", "M6": "1.0", "M8": "1.25", "M10": "1.5", "M12": "1.75",
                "M14": "2.0", "M16": "2.0", "M20": "2.5"}
# punte per maschiatura UNC (mm): #43, #36, #29, #25, #7, F, 5/16, U, 27/64, 17/32, 21/32
TAP_DRILL_INCH_MM = {"#4": 2.261, "#6": 2.705, "#8": 3.454, "#10": 3.797, "1/4": 5.105, "5/16": 6.528, "3/8": 7.938,
                     "7/16": 9.347, "1/2": 10.716, "5/8": 13.494, "3/4": 16.669}
UNC_THREADS = {"#4": "40", "#6": "32", "#8": "32", "#10": "24", "1/4": "20", "5/16": "18", "3/8": "16", "7/16": "14",
               "1/2": "13", "5/8": "11", "3/4": "10"}

# Hole Wizard: standard -> (indice swWzdHoleStandards_e, {tipo: {head: indice swWzdHoleStandardFastenerTypes_e}},
#                           misure metriche?, passo nella misura dei filettati?). head None = variante predefinita.
HOLE_STANDARDS = {
    "iso": (8, {"simple": {None: 144}, "tapped": {None: 147, "bottoming": 146},
                "counterbore": {None: 139, "socket": 139, "cheese": 134, "pan": 138, "hex": 135, "hex_cap": 136, "hex_machine": 137},
                "countersink": {None: 140, "socket": 140, "flat": 141, "raised": 142}}, True, False),
    "ansi_metric": (1, {"simple": {None: 40}, "tapped": {None: 43, "bottoming": 42},
                        "counterbore": {None: 33, "socket": 33, "hex": 29, "hex_cap": 30, "button": 28, "pan": 32},
                        "countersink": {None: 35, "socket": 35, "flat": 36, "oval": 37}}, True, True),
    "ansi_inch": (0, {"simple": {None: 22}, "tapped": {None: 27, "bottoming": 26},
                      "counterbore": {None: 9, "socket": 9, "hex": 3, "hex_screw": 6, "button": 1, "pan": 8,
                                      "fillister": 2, "binding": 0},
                      "countersink": {None: 13, "socket": 13, "flat": 15, "flat100": 14, "oval": 16}}, False, False),
    "din": (4, {"simple": {None: 73}, "tapped": {None: 76, "bottoming": 75},
                "counterbore": {None: 67, "socket": 67, "cheese": 62, "hex": 63, "hex_cap": 64, "hex_machine": 65, "pan": 66},
                "countersink": {None: 68, "socket": 68, "flat": 69, "raised": 70}}, True, False),
    "bsi": (2, {"simple": {None: 55}, "tapped": {None: 58, "bottoming": 57},
                "counterbore": {None: 49, "socket": 49, "cheese": 44, "hex": 45, "hex_cap": 46, "hex_machine": 47, "pan": 48},
                "countersink": {None: 50, "socket": 50, "flat": 51, "oval": 52}}, True, True),
    "jis": (9, {"simple": {None: 161}, "tapped": {None: 164, "bottoming": 163},
                "counterbore": {None: 156, "socket": 156, "cheese": 149, "fillister": 150, "button": 151, "hex": 152,
                                "hex_cap": 153, "hex_machine": 154, "pan": 155},
                "countersink": {None: 158, "flat": 158, "raised": 159}}, True, True),
}


class ModelingOperations(ModelingBase, SketchConstraintOperations):
    """Mixin di modellazione 3D."""

    # ------------------------------------------------------------------ utilita' interne
    def _names(self, doc) -> List[str]:
        return [n for n, t, f in self._features(doc)]

    def _new_features(self, doc, before: List[str]) -> List[Dict]:
        return [{"name": n, "type": t} for n, t, f in self._features(doc) if n not in before]

    def _finish(self, doc, label: str, feat, v0: float, before: List[str], extra: Dict = None,
                require_volume_change: bool = False) -> Dict:
        """Esito comune di una feature: feature creata (restituita o trovata per differenza) + volumi."""
        new = self._new_features(doc, before)
        if feat is None and not new:
            return self._result(False, f"{label} non riuscito (SolidWorks non ha creato nessuna feature). "
                                "Controlla profilo chiuso, selezioni e parametri.", SwErrors.swFeatureError)
        info = {}
        if feat is not None:
            info = self._feature_info(doc, feat, v0)
        else:
            nf = [x for x in new if x["type"] != "ProfileFeature"] or new
            info = {"feature": nf[0]["name"], "feature_type": nf[0]["type"]}
            vol = self._volume_m3(doc)
            info["volume_mm3"] = round(vol * 1e9, 3)
            info["volume_delta_mm3"] = round((vol - v0) * 1e9, 3)
        if not info.get("feature") and new:
            nf = [x for x in new if x["type"] != "ProfileFeature"] or new
            info["feature"], info["feature_type"] = nf[0]["name"], nf[0]["type"]
        info["new_features"] = new
        # errori di ricostruzione
        try:
            f = self._find_feature(doc, info.get("feature"))
            if f is not None:
                code = f.GetErrorCode2
                code = code[0] if isinstance(code, tuple) else code
                if code:
                    info["rebuild_error_code"] = int(code)
        except Exception:
            pass
        if extra:
            info.update(extra)
        msg = f"{label}: {info.get('feature')} (volume {info['volume_mm3']:.1f} mm3, delta {info['volume_delta_mm3']:+.1f})"
        if require_volume_change and abs(info["volume_delta_mm3"]) < 1e-6:
            return self._result(False, msg + " - il volume non e' cambiato: feature senza effetto.",
                                SwErrors.swFeatureError, info)
        return self._result(True, msg, SwErrors.swSuccess, info)

    def _delete_features(self, doc, names: List[str]):
        doc.ClearSelection2(True)
        for i, n in enumerate(names):
            self._select_feature(doc, n, append=(i > 0))
        try:
            doc.Extension.DeleteSelection2(3)
        except Exception:
            pass

    def _sketch_segments_of(self, doc, sketch_name: str) -> list:
        f = self._find_feature(doc, sketch_name)
        if f is None:
            return []
        try:
            sk = self._com(f, "GetSpecificFeature2")
            return list(self._com(sk, "GetSketchSegments") or [])
        except Exception:
            return []

    # ------------------------------------------------------------------ massa / materiale
    def get_mass_properties(self, unit: str = None) -> Dict:
        """Volume, massa, area, baricentro (Extension.CreateMassProperty)."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ForceRebuild3(False)
            mp = self._mass_props(doc)
            if mp is None:
                return self._result(False, "CreateMassProperty non disponibile", SwErrors.swUnknownError)
            vol = float(self._com(mp, "Volume"))
            mass = float(self._com(mp, "Mass"))
            area = float(self._com(mp, "SurfaceArea"))
            com = [round(v * 1000, 4) for v in self._com(mp, "CenterOfMass")]
            try:
                dens = float(self._com(mp, "Density"))
            except Exception:
                dens = mass / vol if vol else 0.0
            return self._result(True, f"Volume {vol * 1e9:.2f} mm3, massa {mass:.5f} kg", SwErrors.swSuccess,
                                {"volume_mm3": round(vol * 1e9, 4), "mass_kg": mass, "surface_area_mm2": round(area * 1e6, 4),
                                 "density_kg_m3": round(dens, 3), "center_of_mass_mm": com,
                                 "bodies": len(self._bodies(doc))})
        except Exception as e:
            logger.error(f"get_mass_properties: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def _material_db(self):
        """File .sldmat del database materiali di SolidWorks (lingua dell'interfaccia, altrimenti inglese)."""
        import os
        try:
            base = self._com(self._sw_app, "GetExecutablePath")
            if base.lower().endswith(".exe"):
                base = os.path.dirname(base)
        except Exception:
            base = r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS"
        for sub in [os.path.join("lang", lg, "sldmaterials") for lg in lang_folders(self._ui_language())] + ["sldmaterials"]:
            p = os.path.join(base, sub, "solidworks materials.sldmat")
            if os.path.exists(p):
                return p
        return None

    def set_material(self, material: str = "AISI 1020") -> Dict:
        """Assegna un materiale del database SolidWorks (nome come nell'interfaccia, anche parziale):
        serve a ottenere la massa corretta in get_mass_properties."""
        try:
            import re
            doc, err = self._part()
            if err:
                return err
            db = self._material_db()
            if not db:
                return self._result(False, "Database materiali non trovato", SwErrors.swUnknownError)
            txt = open(db, "rb").read().decode("utf-16", errors="ignore")
            names = re.findall(r'<material name="([^"]+)"', txt)
            low = material.lower()
            match = next((n for n in names if n.lower() == low), None) or                 next((n for n in names if low in n.lower()), None)
            if not match:
                return self._result(False, f"Materiale '{material}' non trovato ({len(names)} nel database).",
                                    SwErrors.swInvalidInput)
            cfg = self._com(self._com(doc.ConfigurationManager, "ActiveConfiguration"), "Name")
            doc.SetMaterialPropertyName2(cfg, db, match)
            doc.EditRebuild3
            mp = self._mass_props(doc)
            dens = float(self._com(mp, "Density")) if mp is not None else 0.0
            return self._result(True, f"Materiale {match} (densita' {dens:.0f} kg/m3)", SwErrors.swSuccess,
                                {"material": match, "density_kg_m3": dens, "database": db})
        except Exception as e:
            logger.error(f"set_material: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ estrusioni avanzate
    def _extrude_common(self, cut: bool, sketch, depth, end_condition, depth2, end_condition2, draft_angle,
                        draft_outward, up_to_face_point, offset, reverse, flip_side_to_cut, merge, unit,
                        start_offset, label):
        doc, err = self._part()
        if err:
            return err
        sk_name, err = self._resolve_sketch(doc, sketch)
        if err:
            return err
        ec = (end_condition or "blind").lower()
        if ec not in END_CONDITIONS:
            return self._result(False, f"end_condition sconosciuta: {end_condition}. Valide: {sorted(END_CONDITIONS)}",
                                SwErrors.swInvalidInput)
        t1 = END_CONDITIONS[ec]
        both = ec == "through_all_both"
        sd = True
        t2 = 0
        if both:
            t1, t2, sd = 1, 1, False
        elif depth2 is not None or end_condition2:
            sd = False
            t2 = END_CONDITIONS.get((end_condition2 or "blind").lower(), 0)
        v0 = self._volume_m3(doc)
        before = self._names(doc)
        doc.ClearSelection2(True)
        if not self._select_feature(doc, sk_name, False, 0):
            return self._result(False, f"Schizzo '{sk_name}' non selezionabile", SwErrors.swSelectionError)
        if t1 in (4, 5):
            if not up_to_face_point:
                return self._result(False, "Per up_to_surface/offset_from_surface serve up_to_face_point=[x,y,z] "
                                    "(punto sulla faccia di arresto).", SwErrors.swInvalidInput)
            ok, info = self._select_point(doc, "face", up_to_face_point, unit, True, 1)
            if not ok:
                return self._result(False, info.get("error", "faccia di arresto non trovata"), SwErrors.swSelectionError)
        d1 = self._mmu(offset if t1 == 5 else (depth or 0), unit)
        d2 = self._mmu(depth2 or 0, unit)
        dr = bool(draft_angle)
        ang = math.radians(draft_angle or 0)
        fm = doc.FeatureManager
        feat = None
        try:
            if cut:
                feat = fm.FeatureCut4(sd, bool(reverse), False, t1, t2, d1, d2, dr, False, bool(draft_outward), False,
                                      ang, 0.0, False, False, False, False, False, True, True, False, False, False,
                                      0, self._mmu(start_offset or 0, unit), False, False)
            else:
                feat = fm.FeatureExtrusion3(sd, bool(reverse), False, t1, t2, d1, d2, dr, False, bool(draft_outward),
                                            False, ang, 0.0, False, False, False, False, bool(merge), True, True,
                                            0, self._mmu(start_offset or 0, unit), False)
        except Exception as e:
            return self._result(False, f"{label} fallito: {e}", SwErrors.swFeatureError)
        doc.ClearSelection2(True)
        extra = {"sketch": sk_name, "end_condition": ec, "depth": depth, "unit": self._unit_name(unit),
                 "draft_angle": draft_angle or 0}
        return self._finish(doc, label, feat, v0, before, extra, require_volume_change=True)

    def extrude_boss(self, sketch: str = None, depth: float = 10, end_condition: str = "blind",
                     depth2: float = None, end_condition2: str = None, draft_angle: float = 0,
                     draft_outward: bool = False, up_to_face_point: list = None, offset: float = 0,
                     reverse: bool = False, merge: bool = True, start_offset: float = 0, unit: str = None) -> Dict:
        """Estrusione base/aggiunta con condizioni finali: blind | through_all | through_all_both | mid_plane |
        up_to_next | up_to_surface | offset_from_surface; sformo (gradi) e seconda direzione."""
        try:
            return self._extrude_common(False, sketch, depth, end_condition, depth2, end_condition2, draft_angle,
                                        draft_outward, up_to_face_point, offset, reverse, False, merge, unit,
                                        start_offset, "Estrusione")
        except Exception as e:
            logger.error(f"extrude_boss: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def extrude_cut(self, sketch: str = None, depth: float = 10, end_condition: str = "blind",
                    depth2: float = None, end_condition2: str = None, draft_angle: float = 0,
                    draft_outward: bool = False, up_to_face_point: list = None, offset: float = 0,
                    reverse: bool = False, start_offset: float = 0, unit: str = None) -> Dict:
        """Taglio estruso con le stesse condizioni finali di extrude_boss (reverse=True taglia dall'altra parte)."""
        try:
            return self._extrude_common(True, sketch, depth, end_condition, depth2, end_condition2, draft_angle,
                                        draft_outward, up_to_face_point, offset, reverse, False, True, unit,
                                        start_offset, "Taglio estruso")
        except Exception as e:
            logger.error(f"extrude_cut: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ rivoluzione
    def _revolve(self, cut: bool, sketch, angle, axis, both_directions, thin_thickness, unit):
        doc, err = self._part()
        if err:
            return err
        sk_name, err = self._resolve_sketch(doc, sketch)
        if err:
            return err
        v0 = self._volume_m3(doc)
        before = self._names(doc)
        doc.ClearSelection2(True)
        if not self._select_feature(doc, sk_name, False, 0):
            return self._result(False, f"Schizzo '{sk_name}' non selezionabile", SwErrors.swSelectionError)
        # asse: entita' indicata, altrimenti l'unica linea di costruzione/asse di mezzeria dello schizzo
        segs = self._sketch_segments_of(doc, sk_name)
        axis_seg = None
        if axis:
            for s in segs:
                if self._seg_id(s) == axis:
                    axis_seg = s
        else:
            cl = [s for s in segs if int(s.GetType) == 0 and bool(s.ConstructionGeometry)]
            if len(cl) >= 1:
                axis_seg = cl[0]
        if axis_seg is not None:
            axis_seg.Select4(True, self._sd(doc, 4))
        elif axis:
            return self._result(False, f"Asse '{axis}' non trovato nello schizzo {sk_name}", SwErrors.swSelectionError)
        ang = math.radians(angle)
        thin = thin_thickness is not None
        fm = doc.FeatureManager
        feat = None
        try:
            feat = fm.FeatureRevolve2(not both_directions, True, thin, cut, False, False, 0, 0, ang,
                                      ang if both_directions else 0.0, False, False, 0.0, 0.0, 0,
                                      self._mmu(thin_thickness or 0, unit), 0.0, True, True, True)
        except Exception as e:
            return self._result(False, f"Rivoluzione fallita: {e}", SwErrors.swFeatureError)
        doc.ClearSelection2(True)
        return self._finish(doc, "Taglio rivoluzione" if cut else "Rivoluzione", feat, v0, before,
                            {"sketch": sk_name, "angle": angle, "axis_found": axis_seg is not None},
                            require_volume_change=True)

    def revolve_boss(self, sketch: str = None, angle: float = 360, axis: str = None,
                     both_directions: bool = False, thin_thickness: float = None, unit: str = None) -> Dict:
        """Rivoluzione attorno all'asse di mezzeria dello schizzo (o `axis` = id di un segmento dello schizzo)."""
        try:
            return self._revolve(False, sketch, angle, axis, both_directions, thin_thickness, unit)
        except Exception as e:
            logger.error(f"revolve_boss: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def revolve_cut(self, sketch: str = None, angle: float = 360, axis: str = None,
                    both_directions: bool = False, unit: str = None) -> Dict:
        """Taglio di rivoluzione (gole, scarichi)."""
        try:
            return self._revolve(True, sketch, angle, axis, both_directions, None, unit)
        except Exception as e:
            logger.error(f"revolve_cut: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ sweep / loft
    def sweep(self, profile_sketch: str = None, path_sketch: str = None, cut: bool = False,
              circular_diameter: float = None, twist_angle: float = 0, keep_normal: bool = True,
              unit: str = None) -> Dict:
        """Sweep (base o taglio): schizzo profilo + schizzo percorso; oppure solo percorso con
        circular_diameter (profilo circolare)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            if not path_sketch:
                return self._result(False, "path_sketch obbligatorio", SwErrors.swInvalidInput)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            circ = circular_diameter is not None
            if not circ:
                if not profile_sketch or not self._select_feature(doc, profile_sketch, False, 1):
                    return self._result(False, f"Profilo '{profile_sketch}' non trovato", SwErrors.swSelectionError)
            if not self._select_feature(doc, path_sketch, not circ, 4):
                return self._result(False, f"Percorso '{path_sketch}' non trovato", SwErrors.swSelectionError)
            fm = doc.FeatureManager
            dia = self._mmu(circular_diameter or 0, unit)
            tw = 1 if twist_angle else 0     # 0 segui percorso, 1 = torsione
            try:
                if cut:
                    feat = fm.InsertCutSwept5(False, 0, 0 if keep_normal else tw, False, False, 0, 0, False, 0.0, 0.0, 0, 0,
                                              True, True, math.radians(twist_angle), True, False, False, False,
                                              circ, dia, 0)
                else:
                    feat = fm.InsertProtrusionSwept4(False, 0, 0 if keep_normal else tw, False, False, 0, 0, False,
                                                     0.0, 0.0, 0, 0, True, True, True, math.radians(twist_angle), True,
                                                     circ, dia, 0)
            except Exception as e:
                return self._result(False, f"Sweep fallito: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            return self._finish(doc, "Sweep taglio" if cut else "Sweep", feat, v0, before,
                                {"profile": profile_sketch, "path": path_sketch}, require_volume_change=True)
        except Exception as e:
            logger.error(f"sweep: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def loft(self, profile_sketches: list, guide_sketches: list = None, closed: bool = False,
             cut: bool = False, start_tangency: bool = False) -> Dict:
        """Loft fra 2 o piu' profili (schizzi in ordine) con guide opzionali."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            if not profile_sketches or len(profile_sketches) < 2:
                return self._result(False, "Servono almeno 2 profili.", SwErrors.swInvalidInput)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            for i, n in enumerate(profile_sketches):
                if not self._select_feature(doc, n, i > 0, 1):
                    return self._result(False, f"Profilo '{n}' non trovato", SwErrors.swSelectionError)
            for n in (guide_sketches or []):
                if not self._select_feature(doc, n, True, 2):
                    return self._result(False, f"Guida '{n}' non trovata", SwErrors.swSelectionError)
            fm = doc.FeatureManager
            try:
                if cut:
                    feat = fm.InsertCutBlend(closed, False, False, 1.0, 0, 0, False, 0.0, 0.0, 0, True, True)
                else:
                    feat = fm.InsertProtrusionBlend2(closed, False, False, 1.0, 0, 0, 0.0, 0.0, 0, 0, False, 0.0, 0.0, 0,
                                                     True, True, True, 0)
            except Exception as e:
                return self._result(False, f"Loft fallito: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            return self._finish(doc, "Loft taglio" if cut else "Loft", feat, v0, before,
                                {"profiles": profile_sketches, "guides": guide_sketches or []},
                                require_volume_change=True)
        except Exception as e:
            logger.error(f"loft: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ shell / nervatura / sformo
    def shell_body(self, thickness: float, remove_faces: list, outward: bool = False, unit: str = None) -> Dict:
        """Shell: spessore e facce da rimuovere indicate da un punto su ciascuna faccia [[x,y,z],...]."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            ok, msg = self._select_points(doc, "face", remove_faces or [], unit)
            if not ok:
                return self._result(False, msg, SwErrors.swSelectionError)
            doc.InsertFeatureShell(self._mmu(thickness, unit), bool(outward))
            doc.ClearSelection2(True)
            return self._finish(doc, "Shell", None, v0, before,
                                {"thickness": thickness, "unit": self._unit_name(unit), "faces_removed": len(remove_faces or [])},
                                require_volume_change=True)
        except Exception as e:
            logger.error(f"shell_body: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def rib(self, sketch: str = None, thickness: float = 3, both_sides: bool = True, flip_material: bool = False,
            normal_to_sketch: bool = False, draft_angle: float = 0, unit: str = None) -> Dict:
        """Nervatura da uno schizzo con una linea aperta. Se la direzione del materiale e' sbagliata
        (volume invariato) riprova da sola con la direzione opposta."""
        try:
            doc, err = self._part()
            if err:
                return err
            sk_name, err = self._resolve_sketch(doc, sketch)
            if err:
                return err
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            fm = doc.FeatureManager
            tried = []
            for flip in (bool(flip_material), not flip_material):
                doc.ClearSelection2(True)
                self._select_feature(doc, sk_name, False, 0)
                try:
                    feat = fm.InsertRib(bool(both_sides), False, self._mmu(thickness, unit), 0, flip,
                                        bool(draft_angle), False, math.radians(draft_angle or 0),
                                        bool(normal_to_sketch), False)
                except Exception as e:
                    tried.append(str(e))
                    feat = None
                doc.ClearSelection2(True)
                new = self._new_features(doc, before)
                vol = self._volume_m3(doc)
                if (feat is not None or new) and vol > v0 + 1e-12:
                    return self._finish(doc, "Nervatura", feat, v0, before,
                                        {"sketch": sk_name, "thickness": thickness, "flip_material": flip})
                if new:
                    self._delete_features(doc, [x["name"] for x in new if x["type"] != "ProfileFeature"])
                tried.append(f"flip={flip}: volume invariato")
            return self._result(False, f"Nervatura non riuscita ({tried}). La linea dello schizzo deve toccare "
                                "le pareti del pezzo.", SwErrors.swFeatureError)
        except Exception as e:
            logger.error(f"rib: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def draft_faces(self, angle: float, faces: list, neutral_face_point: list, flip: bool = False,
                    propagate_tangent: bool = False, unit: str = None) -> Dict:
        """Sformo (draft) di facce [[x,y,z],...] rispetto a un piano neutro (punto su una faccia piana)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            ok, info = self._select_point(doc, "face", neutral_face_point, unit, False, 1)
            if not ok:
                return self._result(False, "Piano neutro: " + info.get("error", ""), SwErrors.swSelectionError)
            ok, msg = self._select_points(doc, "face", faces or [], unit, mark=2, append_first=True)
            if not ok:
                return self._result(False, msg, SwErrors.swSelectionError)
            fm = doc.FeatureManager
            try:
                feat = fm.InsertMultiFaceDraft(math.radians(angle), bool(flip), False, 1 if propagate_tangent else 0,
                                               False, False)
            except Exception as e:
                return self._result(False, f"Sformo fallito: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            return self._finish(doc, "Sformo", feat, v0, before, {"angle": angle}, require_volume_change=True)
        except Exception as e:
            logger.error(f"draft_faces: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ raccordi / smussi autonomi
    def fillet_at_points(self, radius: float, edge_points: list, tangent_propagation: bool = True,
                         radius2: float = None, unit: str = None) -> Dict:
        """Raccordo a raggio costante sugli spigoli indicati da un punto SULLO spigolo [[x,y,z],...]."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            ok, msg = self._select_points(doc, "edge", edge_points or [], unit)
            if not ok:
                return self._result(False, msg, SwErrors.swSelectionError)
            r = self._mmu(radius, unit)
            opts = 2 | (1 if tangent_propagation else 0)
            fm = doc.FeatureManager
            try:
                feat = fm.FeatureFillet3(opts, r, self._mmu(radius2, unit) if radius2 else r, 0, 0, 0, 0,
                                         None, None, None, None, None, None, None)
            except Exception as e:
                return self._result(False, f"Raccordo fallito: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            return self._finish(doc, "Raccordo", feat, v0, before,
                                {"radius": radius, "unit": self._unit_name(unit), "edges": len(edge_points or [])},
                                require_volume_change=True)
        except Exception as e:
            logger.error(f"fillet_at_points: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def fillet_variable_radius(self, edge_point: list, radius_start: float, radius_end: float,
                               unit: str = None) -> Dict:
        """Raccordo a raggio variabile su uno spigolo: raggio all'inizio e alla fine dello spigolo."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            ok, info = self._select_point(doc, "edge", edge_point, unit, False, 0)
            if not ok:
                return self._result(False, info.get("error", ""), SwErrors.swSelectionError)
            fm = doc.FeatureManager
            feat = None
            err_msgs = []
            for variant in (0, 1):
                try:
                    # Ftyp=1 raggio variabile; Radii = raggi ai due vertici; PointRadiusArray vuoto
                    radii = r8_array([self._mmu(radius_start, unit), self._mmu(radius_end, unit)])
                    feat = fm.FeatureFillet3(1 | 4, self._mmu(radius_start, unit), self._mmu(radius_start, unit), 0, 1, 0, 0,
                                             radii, None, None, None, None, None, None)
                except Exception as e:
                    err_msgs.append(str(e))
                if feat is not None or self._new_features(doc, before):
                    break
            doc.ClearSelection2(True)
            return self._finish(doc, "Raccordo variabile", feat, v0, before,
                                {"radius_start": radius_start, "radius_end": radius_end},
                                require_volume_change=True)
        except Exception as e:
            logger.error(f"fillet_variable_radius: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def chamfer_at_points(self, distance: float, edge_points: list, angle: float = 45.0,
                          distance2: float = None, unit: str = None) -> Dict:
        """Smusso sugli spigoli indicati da un punto sullo spigolo. distance + angle (default 45) oppure
        distance + distance2."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            ok, msg = self._select_points(doc, "edge", edge_points or [], unit)
            if not ok:
                return self._result(False, msg, SwErrors.swSelectionError)
            fm = doc.FeatureManager
            d1 = self._mmu(distance, unit)
            try:
                if distance2:
                    feat = fm.InsertFeatureChamfer(0, 2, d1, 0.0, self._mmu(distance2, unit), 0.0, 0.0, 0.0)
                else:
                    feat = fm.InsertFeatureChamfer(0, 1, d1, math.radians(angle), 0.0, 0.0, 0.0, 0.0)
            except Exception as e:
                return self._result(False, f"Smusso fallito: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            return self._finish(doc, "Smusso", feat, v0, before,
                                {"distance": distance, "angle": angle, "distance2": distance2,
                                 "unit": self._unit_name(unit), "edges": len(edge_points or [])},
                                require_volume_change=True)
        except Exception as e:
            logger.error(f"chamfer_at_points: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ ripetizioni / specchiatura
    def _select_features_mark(self, doc, names: List[str], mark: int, append: bool = False) -> Optional[str]:
        for i, n in enumerate(names):
            if not self._select_feature(doc, n, append or i > 0, mark):
                return f"Feature '{n}' non trovata. Feature: {self._names(doc)}"
        return None

    def _seed_effect(self, doc, names: List[str]) -> float:
        """Effetto sul volume (m3, positivo = materiale in meno) delle feature `names`: serve a verificare che
        una ripetizione abbia prodotto tutte le istanze (un'istanza fuori dal corpo viene saltata in silenzio)."""
        try:
            feats = [self._find_feature(doc, n) for n in names]
            if any(f is None for f in feats):
                return 0.0
            v_on = self._volume_m3(doc)
            try:
                for f in feats:
                    f.SetSuppression2(0, 1, None)
                v_off = self._volume_m3(doc)
            finally:                                # le feature tornano attive anche se la misura fallisce
                for f in feats:
                    try:
                        f.SetSuppression2(1, 1, None)
                    except Exception:
                        pass
                self._volume_m3(doc)
            return v_off - v_on
        except Exception:
            return 0.0

    def _pattern_ok(self, doc, v0: float, seed: float, n_instances: int) -> bool:
        """True se il volume e' cambiato come atteso per n_instances-1 copie (tolleranza 1%)."""
        if abs(seed) < 1e-15 or n_instances <= 1:
            return True
        delta_cut = v0 - self._volume_m3(doc)
        expected = seed * (n_instances - 1)
        return abs(delta_cut - expected) <= 0.01 * abs(expected) + 1e-15

    def linear_pattern(self, features: list, direction1, count1: int, spacing1: float,
                       direction2=None, count2: int = 1, spacing2: float = 0, reverse1: bool = False,
                       reverse2: bool = False, geometry_pattern: bool = False, unit: str = None) -> Dict:
        """Ripetizione lineare di feature (nomi) in 1 o 2 direzioni. direction = {"edge":[x,y,z]} (spigolo
        parallelo alla direzione) oppure {"face":[x,y,z]} (faccia piana: direzione = normale) oppure nome di asse."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            two = direction2 is not None and count2 and count2 > 1
            combos = [(bool(reverse1), bool(reverse2))]
            for c in ((not reverse1, bool(reverse2)), (bool(reverse1), not reverse2), (not reverse1, not reverse2)):
                if c not in combos and (two or c[1] == bool(reverse2)):
                    combos.append(c)
            feat = None
            used = None
            fm = doc.FeatureManager
            seed = 0.0 if geometry_pattern else self._seed_effect(doc, features)
            n_tot = int(count1) * (int(count2) if two else 1)
            for (r1, r2) in combos:
                doc.ClearSelection2(True)
                e = self._select_features_mark(doc, features, 4)
                if e:
                    return self._result(False, e, SwErrors.swSelectionError)
                ok, msg = self._select_edge_or_axis(doc, direction1, unit, mark=1, append=True)
                if not ok:
                    return self._result(False, f"Direzione 1: {msg}", SwErrors.swSelectionError)
                if two:
                    ok, msg = self._select_edge_or_axis(doc, direction2, unit, mark=2, append=True)
                    if not ok:
                        return self._result(False, f"Direzione 2: {msg}", SwErrors.swSelectionError)
                try:
                    feat = fm.FeatureLinearPattern5(int(count1), self._mmu(spacing1, unit), int(count2) if two else 1,
                                                    self._mmu(spacing2, unit) if two else 0.0, r1, r2,
                                                    "", "", bool(geometry_pattern), False, False, False, False, False,
                                                    False, False, False, False, 0.0, 0.0, False, False)
                except Exception as ex:
                    return self._result(False, f"Ripetizione lineare fallita: {ex}", SwErrors.swFeatureError)
                if feat is not None or self._new_features(doc, before):
                    if self._pattern_ok(doc, v0, seed, n_tot):
                        used = (r1, r2)
                        break
                    # istanze mancanti (direzione sbagliata): elimina e riprova con le direzioni invertite
                    doc.ClearSelection2(True)
                    self._delete_features(doc, [x["name"] for x in self._new_features(doc, before)
                                                if x["type"] != "ProfileFeature"])
                    feat = None
            if used is None:
                return self._result(False, "Ripetizione lineare fallita (anche invertendo le direzioni): le istanze "
                                    "devono cadere sul corpo e non sovrapporsi.", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            return self._finish(doc, "Ripetizione lineare", feat, v0, before,
                                {"count1": count1, "spacing1": spacing1, "count2": count2 if two else 1,
                                 "spacing2": spacing2 if two else 0, "unit": self._unit_name(unit),
                                 "reversed": {"dir1": used[0], "dir2": used[1]}})
        except Exception as e:
            logger.error(f"linear_pattern: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def circular_pattern(self, features: list, axis, count: int, angle: float = 360.0,
                         equal_spacing: bool = True, reverse: bool = False, geometry_pattern: bool = False,
                         unit: str = None) -> Dict:
        """Ripetizione circolare attorno a un asse: {"edge":[x,y,z]} (spigolo circolare/lineare), {"face":[x,y,z]}
        (faccia cilindrica), nome di asse di riferimento ("Asse1") o asse temporaneo."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            seed = 0.0 if geometry_pattern else self._seed_effect(doc, features)
            e = self._select_features_mark(doc, features, 4)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            ok, msg = self._select_edge_or_axis(doc, axis, unit, mark=1, append=True)
            if not ok:
                return self._result(False, f"Asse: {msg}", SwErrors.swSelectionError)
            fm = doc.FeatureManager
            try:
                feat = fm.FeatureCircularPattern5(int(count), math.radians(angle), bool(reverse), "",
                                                  bool(geometry_pattern), bool(equal_spacing), False, False, False,
                                                  False, 1, 0.0, "", False)
            except Exception as ex:
                return self._result(False, f"Ripetizione circolare fallita: {ex}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            if seed and not self._pattern_ok(doc, v0, seed, int(count)):
                return self._result(False, f"Ripetizione circolare: il volume non corrisponde a {count} istanze "
                                    "(alcune cadono fuori dal corpo?).", SwErrors.swFeatureError)
            return self._finish(doc, "Ripetizione circolare", feat, v0, before,
                                {"count": count, "angle": angle, "equal_spacing": equal_spacing})
        except Exception as e:
            logger.error(f"circular_pattern: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def mirror_feature(self, features: list = None, plane=None, mirror_body: bool = False,
                       merge: bool = True, geometry_pattern: bool = False, unit: str = None) -> Dict:
        """Specchia feature (nomi) oppure l'intero corpo (mirror_body=True) rispetto a un piano di riferimento
        (nome, es. 'Piano destro') o a una faccia piana ({"face":[x,y,z]})."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            ok, msg = self._select_edge_or_axis(doc, plane, unit, mark=2, append=False)
            if not ok:
                return self._result(False, f"Piano di specchiatura: {msg}", SwErrors.swSelectionError)
            if mirror_body:
                bodies = self._bodies(doc)
                if not bodies:
                    return self._result(False, "Nessun corpo da specchiare", SwErrors.swFeatureError)
                bodies[0].Select2(True, self._sd(doc, 256))   # corpi da specchiare: Mark 256 (non 1)
            else:
                e = self._select_features_mark(doc, features or [], 1, append=True)
                if e:
                    return self._result(False, e, SwErrors.swSelectionError)
            fm = doc.FeatureManager
            try:
                feat = fm.InsertMirrorFeature2(bool(mirror_body), bool(geometry_pattern), bool(merge), False, 0)
            except Exception as ex:
                return self._result(False, f"Specchiatura fallita: {ex}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            return self._finish(doc, "Specchiatura", feat, v0, before,
                                {"features": features or [], "mirror_body": mirror_body})
        except Exception as e:
            logger.error(f"mirror_feature: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ fori guidati
    def create_hole(self, kind: str, size: str, face_point: list = None, positions: list = None,
                    depth: float = 10, through: bool = False, diameter: float = None,
                    thread_depth: float = None, unit: str = None, standard: str = "iso", head: str = None,
                    fit: str = "normal") -> Dict:
        """Foro guidato (Hole Wizard) su una faccia piana, cilindrica o inclinata (il foro e' normale alla faccia nel
        punto indicato). kind: simple | tapped | countersink | counterbore.
        standard: iso (default) | ansi_metric | ansi_inch | din | bsi | jis (UNI non esiste nel database di SolidWorks).
        head (tipo di vite o variante, vedi HOLE_STANDARDS): lamato -> socket (testa cilindrica con esagono incassato),
        cheese, pan, button, hex, hex_cap, hex_machine; svasato -> socket, flat, raised, oval; filettato -> bottoming
        (con fondo filettato); semplice -> nessuno.
        size: M3..M20 (anche 'M8x1.25'); ANSI pollici: '#10', '1/4', '1/4-20' (tapped: UNC grosso se manca il passo).
        positions: [[x,y,z],...] punti sulla faccia = centri dei fori (face_point per un solo foro).
        depth: profondita' (cieco). diameter: sovrascrive il Ø di passaggio/punta.
        fit: close | normal | loose = Ø di passaggio ISO 273 (default medio); database = valore del database."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            pts = list(positions or [])
            if face_point is not None:
                pts = [face_point] + pts
            if not pts:
                return self._result(False, "Servono positions (o face_point): punti sulla faccia.",
                                    SwErrors.swInvalidInput)
            std_key = str(standard or "iso").lower().replace(" ", "_").replace("-", "_")
            std_key = {"ansi": "ansi_metric", "ansimetric": "ansi_metric", "ansiinch": "ansi_inch",
                       "ansi_pollici": "ansi_inch"}.get(std_key, std_key)
            if std_key not in HOLE_STANDARDS:
                extra = " UNI non e' presente nel database Hole Wizard/Toolbox di SolidWorks." if std_key == "uni" else ""
                return self._result(False, f"Standard non supportato: {standard}. Validi: {sorted(HOLE_STANDARDS)}.{extra}",
                                    SwErrors.swInvalidInput)
            std_idx, std_map, metric, pitch_suffix = HOLE_STANDARDS[std_key]
            kind_key = {"simple": "simple", "semplice": "simple", "hole": "simple", "clearance": "simple",
                        "tapped": "tapped", "filettato": "tapped", "tap": "tapped",
                        "countersink": "countersink", "svasato": "countersink", "csk": "countersink",
                        "counterbore": "counterbore", "lamato": "counterbore", "cbore": "counterbore"}.get(str(kind).lower())
            if kind_key is None:
                return self._result(False, f"kind sconosciuto: {kind} (simple|tapped|countersink|counterbore)",
                                    SwErrors.swInvalidInput)
            head_key = str(head).lower().replace(" ", "_").replace("-", "_") if head else None
            if head_key in ("", "default", "clearance"):
                head_key = None
            heads = std_map[kind_key]
            if head_key not in heads:
                return self._result(False, f"head '{head}' non valido per {kind_key} {std_key}. Validi: "
                                    f"{sorted(k for k in heads if k) or 'nessuno'}", SwErrors.swInvalidInput)
            fast = heads[head_key]
            # misura: metrica 'M6' (ANSI metrico/BSI/JIS filettati vogliono il passo 'M6x1.0'), pollici '1/4' o '1/4-20'
            sz = str(size).strip()
            base = None
            if metric:
                sz_u = sz.upper().replace(" ", "")
                base = sz_u.split("X")[0]
                if base not in CLEARANCE_MM:
                    return self._result(False, f"Misura non supportata: {size}. Valide: {sorted(CLEARANCE_MM)}",
                                        SwErrors.swInvalidInput)
                if pitch_suffix and kind_key == "tapped" and "X" not in sz_u:
                    sz_u = f"{base}X{COARSE_PITCH[base]}"
                sz = sz_u.replace("X", "x")
            elif kind_key == "tapped":
                if "-" not in sz:
                    if sz not in UNC_THREADS:
                        return self._result(False, f"Misura ANSI pollici '{size}' non valida per un foro filettato: usa il "
                                            f"passo ('1/4-20') oppure una di {sorted(UNC_THREADS)}.", SwErrors.swInvalidInput)
                    sz = f"{sz}-{UNC_THREADS[sz]}"
            else:
                sz = sz.split("-")[0].strip()
            gen = {"simple": 2, "tapped": 4, "countersink": 1, "counterbore": 0}[kind_key]
            da = math.radians(118)
            vals = [0.0] * 12
            if kind_key == "simple":
                vals[1] = da
                label = "Foro semplice"
            elif kind_key == "tapped":
                td = thread_depth if thread_depth else depth * 0.8
                vals[0] = self._mmu(td, unit)
                vals[5] = da
                label = "Foro filettato"
            elif kind_key == "countersink":
                vals[1] = math.radians(90)
                vals[4] = da
                label = "Foro svasato"
            else:
                vals[4] = da
                label = "Foro lamato"
            # diametro: Ø di passaggio ISO 273 / punta da maschio (metrici); in pollici sceglie il database
            fit_l = str(fit or "normal").lower()
            dia_m = 0.0
            if diameter is not None:
                dia_m = self._mmu(diameter, unit)
            elif metric and kind_key == "tapped":
                dia_m = TAP_DRILL_MM[base] / 1000.0
            elif kind_key == "tapped":      # pollici: senza Ø della punta il database usa 25.4 mm (!)
                tb = sz.split("-")[0]
                if tb not in TAP_DRILL_INCH_MM:
                    return self._result(False, f"Foro filettato ANSI pollici: per '{size}' indica diameter (Ø punta).",
                                        SwErrors.swInvalidInput)
                dia_m = TAP_DRILL_INCH_MM[tb] / 1000.0
            elif metric and fit_l != "database":
                if fit_l not in CLEARANCE_FIT_MM:
                    return self._result(False, f"fit sconosciuto: {fit} (close|normal|loose|database)", SwErrors.swInvalidInput)
                dia_m = CLEARANCE_FIT_MM[fit_l][base] / 1000.0
            dep_m = self._mmu(depth, unit)
            if kind_key == "simple" and through and metric:
                vals[2] = 0.0001   # csk di ingresso trascurabile (altrimenti il database non risolve)
            end_t = 1 if through else 0
            use_depth = dep_m if not through else max(dep_m, 0.02)
            fm = doc.FeatureManager
            created, fails, infos = [], [], []
            v0 = self._volume_m3(doc)
            before_all = self._names(doc)
            for i, pt in enumerate(pts):
                doc.ClearSelection2(True)
                ok, info = self._select_point(doc, "face", pt, unit, False, 0)
                if not ok:
                    fails.append(info.get("error", "faccia non trovata"))
                    continue
                before = self._names(doc)
                try:
                    feat = fm.HoleWizard5(gen, std_idx, fast, sz, end_t, dia_m, use_depth, 0.0, *vals, 0, False, True, True,
                                          True, True, True)
                except Exception as ex:
                    fails.append(f"punto {pt}: {ex}")
                    continue
                doc.ClearSelection2(True)
                if feat is None:
                    fails.append(f"punto {pt}: HoleWizard5 ha restituito None (parametri non validi per {kind} {sz} {std_key}: "
                                 f"controlla misura e head)")
                    continue
                created.append(self._com(feat, "Name"))
                try:
                    fd = feat.GetDefinition
                    d = {}
                    for k in ("HoleDiameter", "ThruHoleDiameter", "TapDrillDiameter", "TapDrillDepth", "ThreadDiameter",
                              "ThreadDepth", "CounterBoreDiameter", "CounterBoreDepth", "CounterSinkDiameter",
                              "CounterSinkAngle", "HoleDepth", "ThruHoleDepth", "ThruTapDrillDiameter"):
                        try:
                            v = getattr(fd, k)
                            if isinstance(v, float) and v > 0:
                                d[k] = round(v * 1000, 4) if "Angle" not in k else round(math.degrees(v), 3)
                        except Exception:
                            pass
                    infos.append(d)
                except Exception:
                    pass
            if not created:
                return self._result(False, f"Nessun foro creato: {fails}", SwErrors.swFeatureError)
            vol = self._volume_m3(doc)
            msg = f"{label} {sz}: {len(created)} foro/i " + (f"({len(fails)} falliti: {fails})" if fails else "")
            return self._result(not fails, msg, SwErrors.swSuccess if not fails else SwErrors.swFeatureError,
                                {"features": created, "feature": created[0], "dimensions_mm": infos[:1],
                                 "volume_mm3": round(vol * 1e9, 3), "volume_delta_mm3": round((vol - v0) * 1e9, 3),
                                 "failures": fails, "through": through, "standard": std_key, "head": head_key,
                                 "size_used": sz, "fastener_index": fast, "fit": fit_l if metric else "database",
                                 "note": "tapped blind: la zona filettata e' modellata a Ø nominale per thread_depth, "
                                         "poi Ø punta fino a depth + punta a 118 gradi"})
        except Exception as e:
            logger.error(f"create_hole: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ geometria di riferimento
    def _plane_pose(self, doc, name: str, unit: str = None) -> Dict:
        """Origine e assi di un piano di riferimento letti dall'API (IRefPlane.Transform): ArrayData = righe
        [asse u][asse v][normale] + traslazione in metri. -> {plane_origin, plane_normal, plane_u, plane_v}."""
        try:
            f = self._find_feature(doc, name)
            t = list(f.GetSpecificFeature2.Transform.ArrayData)
            return {"plane_origin": [round(self._from_m(v, unit), 4) for v in t[9:12]],
                    "plane_u": [round(v, 6) for v in t[0:3]], "plane_v": [round(v, 6) for v in t[3:6]],
                    "plane_normal": [round(v, 6) for v in t[6:9]], "pose_unit": self._unit_name(unit)}
        except Exception as ex:
            logger.debug(f"_plane_pose: {ex}")
            return {}

    def create_reference_plane(self, mode: str = "offset", base: Any = "front", distance: float = 10,
                               angle: float = 45, edge_point: list = None, points: list = None,
                               flip: bool = False, unit: str = None) -> Dict:
        """Piano di riferimento. mode: offset (base = nome piano o {"face":[x,y,z]}) | angle (base + edge_point,
        angolo in gradi attorno allo spigolo) | three_points (points = 3 vertici [[x,y,z],..])."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            fm = doc.FeatureManager
            m = mode.lower()
            feat = None
            try:
                if m == "offset":
                    ok, msg = self._select_edge_or_axis(doc, base, unit, 0, False)
                    if not ok:
                        return self._result(False, f"Base: {msg}", SwErrors.swSelectionError)
                    feat = fm.InsertRefPlane(8 | (256 if flip else 0), self._mmu(distance, unit), 0, 0, 0, 0)
                elif m == "angle":
                    ok, msg = self._select_edge_or_axis(doc, {"edge": edge_point}, unit, 0, False)
                    if not ok:
                        return self._result(False, f"Spigolo: {msg}", SwErrors.swSelectionError)
                    ok, msg = self._select_edge_or_axis(doc, base, unit, 0, True)
                    if not ok:
                        return self._result(False, f"Base: {msg}", SwErrors.swSelectionError)
                    # InsertRefPlane(4,0,16,ang,..) restituisce None con spigolo+faccia (B2): serve CreatePlaneAtAngle3
                    feat = doc.CreatePlaneAtAngle3(math.radians(angle), bool(flip), True)
                elif m in ("three_points", "3_points", "tre_punti"):
                    if len(points or []) != 3:
                        return self._result(False, "three_points: servono 3 vertici [[x,y,z],..]", SwErrors.swInvalidInput)
                    ok, msg = self._select_points(doc, "vertex", points or [], unit)
                    if not ok:
                        return self._result(False, msg, SwErrors.swSelectionError)
                    # InsertRefPlane(4,0,4,0,4,0) restituisce None (B2): serve CreatePlaneThru3Points3
                    feat = doc.CreatePlaneThru3Points3(True)
                else:
                    return self._result(False, f"mode sconosciuto: {mode} (offset|angle|three_points)",
                                        SwErrors.swInvalidInput)
            except Exception as ex:
                return self._result(False, f"Piano fallito: {ex}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            if feat is None and not self._new_features(doc, before):
                return self._result(False, "InsertRefPlane non ha creato il piano (selezioni incompatibili)",
                                    SwErrors.swFeatureError)
            extra = {"mode": m}
            new = self._new_features(doc, before)
            fname = None
            try:
                fname = self._com(feat, "Name") if feat is not None else None
            except Exception:
                pass
            fname = fname or (new[0]["name"] if new else None)
            if fname:
                extra.update(self._plane_pose(doc, fname, unit))
            return self._finish(doc, "Piano di riferimento", feat, self._volume_m3(doc), before, extra)
        except Exception as e:
            logger.error(f"create_reference_plane: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def create_reference_axis(self, mode: str = "two_planes", planes: list = None, face_point: list = None,
                              edge_point: list = None, points: list = None, unit: str = None) -> Dict:
        """Asse di riferimento: two_planes (nomi di due piani), cylinder (face_point su faccia cilindrica),
        edge (edge_point), two_points (points = 2 vertici)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            m = mode.lower()
            if m == "two_planes":
                if not planes or len(planes) != 2:
                    return self._result(False, "planes: 2 nomi di piano", SwErrors.swInvalidInput)
                for i, p in enumerate(planes):
                    ok, msg = self._select_edge_or_axis(doc, p if isinstance(p, dict) else {"plane": p}, unit, 0, i > 0)
                    if not ok:
                        return self._result(False, f"Piano {p}: {msg}", SwErrors.swSelectionError)
            elif m == "cylinder":
                ok, info = self._select_point(doc, "face", face_point, unit, False, 0)
                if not ok:
                    return self._result(False, info.get("error", ""), SwErrors.swSelectionError)
            elif m == "edge":
                ok, info = self._select_point(doc, "edge", edge_point, unit, False, 0)
                if not ok:
                    return self._result(False, info.get("error", ""), SwErrors.swSelectionError)
            elif m == "two_points":
                ok, msg = self._select_points(doc, "vertex", points or [], unit)
                if not ok:
                    return self._result(False, msg, SwErrors.swSelectionError)
            else:
                return self._result(False, f"mode sconosciuto: {mode}", SwErrors.swInvalidInput)
            try:
                doc.InsertAxis2(True)
            except Exception as ex:
                return self._result(False, f"Asse fallito: {ex}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            return self._finish(doc, "Asse di riferimento", None, self._volume_m3(doc), before, {"mode": m})
        except Exception as e:
            logger.error(f"create_reference_axis: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def create_reference_point(self, mode: str = "face_center", face_point: list = None, edge_point: list = None,
                               percent: float = 50, unit: str = None) -> Dict:
        """Punto di riferimento: face_center (centro di una faccia), edge_center (centro spigolo), on_edge (percent)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            fm = doc.FeatureManager
            m = mode.lower()
            if m == "face_center":
                ok, info = self._select_point(doc, "face", face_point, unit, False, 0)
                t, a, d = 4, 0, 0.0
            elif m == "edge_center":
                ok, info = self._select_point(doc, "edge", edge_point, unit, False, 0)
                t, a, d = 3, 0, 0.0
            elif m == "on_edge":
                ok, info = self._select_point(doc, "edge", edge_point, unit, False, 0)
                t, a, d = 2, 1, percent / 100.0
            else:
                return self._result(False, f"mode sconosciuto: {mode}", SwErrors.swInvalidInput)
            if not ok:
                return self._result(False, info.get("error", ""), SwErrors.swSelectionError)
            try:
                feat = fm.InsertReferencePoint(t, a, d, 1)
            except Exception as ex:
                return self._result(False, f"Punto fallito: {ex}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            return self._finish(doc, "Punto di riferimento", feat, self._volume_m3(doc), before, {"mode": m})
        except Exception as e:
            logger.error(f"create_reference_point: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def create_coordinate_system(self, origin_point: list = None, x_edge_point: list = None,
                                 y_edge_point: list = None, z_edge_point: list = None, unit: str = None,
                                 x_flip: bool = False, y_flip: bool = False, z_flip: bool = False) -> Dict:
        """Sistema di coordinate: origine = vertice (origin_point), assi X/Y/Z = spigoli (punti su di essi).
        x_flip/y_flip/z_flip invertono il verso dell'asse (il verso di partenza e' quello dello spigolo).
        Il risultato riporta origine e assi letti dall'API (origin, x_axis, y_axis, z_axis)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            first = True
            if origin_point:
                ok, info = self._select_point(doc, "vertex", origin_point, unit, False, 1)
                if not ok:
                    return self._result(False, "Origine: " + info.get("error", ""), SwErrors.swSelectionError)
                first = False
            for pt, mk in ((x_edge_point, 2), (y_edge_point, 4), (z_edge_point, 8)):
                if pt:
                    ok, info = self._select_point(doc, "edge", pt, unit, not first, mk)
                    if not ok:
                        return self._result(False, f"Asse (mark {mk}): " + info.get("error", ""), SwErrors.swSelectionError)
                    first = False
            fm = doc.FeatureManager
            try:
                feat = fm.InsertCoordinateSystem(bool(x_flip), bool(y_flip), bool(z_flip))
            except Exception as ex:
                return self._result(False, f"Sistema di coordinate fallito: {ex}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            extra = {}
            new = self._new_features(doc, before)
            fname = (self._com(feat, "Name") if feat is not None else None) or (new[0]["name"] if new else None)
            try:
                t = list(doc.Extension.GetCoordinateSystemTransformByName(fname).ArrayData)
                extra = {"origin": [round(self._from_m(v, unit), 4) for v in t[9:12]],
                         "x_axis": [round(v, 6) for v in t[0:3]], "y_axis": [round(v, 6) for v in t[3:6]],
                         "z_axis": [round(v, 6) for v in t[6:9]], "pose_unit": self._unit_name(unit)}
            except Exception as ex:
                logger.debug(f"coordinate system pose: {ex}")
            return self._finish(doc, "Sistema di coordinate", feat, self._volume_m3(doc), before, extra)
        except Exception as e:
            logger.error(f"create_coordinate_system: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ gestione feature
    def list_model_features(self, include_dimensions: bool = False) -> Dict:
        """Elenco feature con tipo, stato di soppressione, errori e (opz.) quote."""
        try:
            doc, err = self._part()
            if err:
                return err
            rows = []
            for n, t, f in self._features(doc):
                if t in ("CommentsFolder", "FavoriteFolder", "HistoryFolder", "SelectionSetFolder", "SensorFolder",
                         "DocsFolder", "DetailCabinet", "SurfaceBodyFolder", "SolidBodyFolder", "EnvFolder",
                         "InkMarkupFolder", "EqnFolder", "MaterialFolder", "OriginProfileFeature"):
                    continue
                row = {"name": n, "type": t}
                try:
                    row["suppressed"] = bool(f.IsSuppressed2(1, None)[0] if isinstance(f.IsSuppressed2(1, None), tuple)
                                             else f.IsSuppressed2(1, None))
                except Exception:
                    try:
                        row["suppressed"] = bool(self._com(f, "IsSuppressed"))
                    except Exception:
                        pass
                try:
                    code = f.GetErrorCode2
                    code = code[0] if isinstance(code, tuple) else code
                    if code:
                        row["error_code"] = int(code)
                except Exception:
                    pass
                if include_dimensions:
                    row["dimensions"] = self._sketch_dimensions(doc, n)
                rows.append(row)
            return self._result(True, f"{len(rows)} feature", SwErrors.swSuccess, {"features": rows, "count": len(rows)})
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def _suppress(self, name: str, suppress: bool) -> Dict:
        doc, err = self._part()
        if err:
            return err
        self._exit_sketch(doc)
        feat = self._find_feature(doc, name)
        if feat is None:
            return self._result(False, f"Feature '{name}' non trovata. Feature: {self._names(doc)}",
                                SwErrors.swSelectionError)
        v0 = self._volume_m3(doc)
        ok = False
        try:
            ok = bool(feat.SetSuppression2(0 if suppress else 1, 1, None))
        except Exception:
            doc.ClearSelection2(True)
            self._select_feature(doc, name)
            try:
                ok = bool(doc.EditSuppress2() if suppress else doc.EditUnsuppress2())
            except Exception as e:
                return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
        vol = self._volume_m3(doc)
        state = "soppressa" if suppress else "riattivata"
        return self._result(True, f"Feature {name} {state} (volume {vol * 1e9:.1f} mm3, delta {(vol - v0) * 1e9:+.1f})",
                            SwErrors.swSuccess, {"feature": name, "suppressed": suppress, "api_ok": ok,
                                                 "volume_mm3": round(vol * 1e9, 3),
                                                 "volume_delta_mm3": round((vol - v0) * 1e9, 3)})

    def suppress_feature(self, name: str) -> Dict:
        try:
            return self._suppress(name, True)
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def unsuppress_feature(self, name: str) -> Dict:
        try:
            return self._suppress(name, False)
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def delete_feature(self, name: str, delete_children: bool = False, confirm: bool = False) -> Dict:
        """Elimina una feature (e lo schizzo assorbito). DISTRUTTIVO e senza annulla:
        - serve confirm=True (esplicito);
        - se altre feature ne dipendono (ripetizioni, raccordi, schizzi sulle sue facce...) RIFIUTA e le elenca, a meno di
          delete_children=True (le elimina tutte; il risultato riporta l'elenco di quelle eliminate)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            feat = self._find_feature(doc, name)
            if feat is None:
                return self._result(False, f"Feature '{name}' non trovata", SwErrors.swSelectionError)
            kids = []
            try:
                kids = [k.Name for k in (feat.GetChildren or ())]
            except Exception:
                pass
            if not confirm:
                return self._result(False,
                    f"Rifiutato: eliminare '{name}' e' irreversibile (nessun annulla). Ripeti con confirm=true"
                    + (f"; ATTENZIONE: ne dipendono {kids} (servira' anche delete_children=true)." if kids else "."),
                    SwErrors.swFeatureError, {"feature": name, "refused": "confirm_required", "dependents": kids})
            if kids and not delete_children:
                return self._result(False,
                    f"Rifiutato: da '{name}' dipendono {kids}: eliminarla le cancellerebbe. Se e' voluto usa "
                    f"delete_children=true, altrimenti sopprimi la feature (suppress_feature).",
                    SwErrors.swFeatureError, {"feature": name, "refused": "has_dependents", "dependents": kids})
            before = self._names(doc)
            v0 = self._volume_m3(doc)
            doc.ClearSelection2(True)
            self._select_feature(doc, name)
            ok = bool(doc.Extension.DeleteSelection2(3 if delete_children else 2))
            doc.ClearSelection2(True)
            gone = self._find_feature(doc, name) is None
            vol = self._volume_m3(doc)
            after = self._names(doc)
            removed = [n for n in before if n not in after]
            return self._result(gone, f"Feature {name} {'eliminata' if gone else 'NON eliminata'}"
                                + (f" (con {len(removed) - 1} altre: {[n for n in removed if n != name]})" if len(removed) > 1 else ""),
                                SwErrors.swSuccess if gone else SwErrors.swFeatureError,
                                {"feature": name, "api_ok": ok, "volume_mm3": round(vol * 1e9, 3),
                                 "volume_delta_mm3": round((vol - v0) * 1e9, 3), "deleted_features": removed})
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def rename_feature(self, name: str, new_name: str) -> Dict:
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            feat = self._find_feature(doc, name)
            if feat is None:
                return self._result(False, f"Feature '{name}' non trovata", SwErrors.swSelectionError)
            feat.Name = new_name
            now = self._com(feat, "Name")
            return self._result(now == new_name, f"{name} -> {now}",
                                SwErrors.swSuccess if now == new_name else SwErrors.swFeatureError,
                                {"old_name": name, "new_name": now})
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def set_dimension_value(self, name: str, value: float, unit: str = None, rebuild: bool = True) -> Dict:
        """Modifica una quota esistente per nome: 'D1@Schizzo1', 'D1@Estrusione-Estrusione1', ... Gli angoli
        in gradi. Ricostruisce e riporta il nuovo volume."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            d = doc.Parameter(name)
            if d is None:
                return self._result(False, f"Quota '{name}' non trovata (usa il formato D1@Schizzo1).",
                                    SwErrors.swSelectionError)
            try:
                angular = int(self._com(d, "GetType")) == 3
            except Exception:
                angular = False
            old = float(self._com(d, "SystemValue"))
            v0 = self._volume_m3(doc)
            si = math.radians(value) if angular else self._mmu(value, unit)
            d.SystemValue = si
            if rebuild:
                doc.EditRebuild3
            new = float(self._com(d, "SystemValue"))
            vol = self._volume_m3(doc)
            conv = (lambda v: round(math.degrees(v), 6)) if angular else (lambda v: round(self._from_m(v, unit), 6))
            return self._result(True, f"{name}: {conv(old)} -> {conv(new)}; volume {v0 * 1e9:.1f} -> {vol * 1e9:.1f} mm3",
                                SwErrors.swSuccess,
                                {"dimension": name, "old_value": conv(old), "new_value": conv(new),
                                 "unit": "deg" if angular else self._unit_name(unit),
                                 "volume_before_mm3": round(v0 * 1e9, 3), "volume_mm3": round(vol * 1e9, 3)})
        except Exception as e:
            logger.error(f"set_dimension_value: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def get_dimension_value(self, name: str, unit: str = None) -> Dict:
        try:
            doc, err = self._part()
            if err:
                return err
            d = doc.Parameter(name)
            if d is None:
                return self._result(False, f"Quota '{name}' non trovata", SwErrors.swSelectionError)
            angular = int(self._com(d, "GetType")) == 3
            si = float(self._com(d, "SystemValue"))
            v = math.degrees(si) if angular else self._from_m(si, unit)
            return self._result(True, f"{name} = {v:.6f}", SwErrors.swSuccess,
                                {"dimension": name, "value": round(v, 6), "unit": "deg" if angular else self._unit_name(unit)})
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def rebuild_model(self, force: bool = False) -> Dict:
        """Ricostruisce il modello e riporta le feature con errore + volume."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            ok = bool(doc.ForceRebuild3(False) if force else doc.EditRebuild3)
            bad = []
            for n, t, f in self._features(doc):
                try:
                    code = f.GetErrorCode2
                    code = code[0] if isinstance(code, tuple) else code
                    if code:
                        bad.append({"name": n, "error_code": int(code)})
                except Exception:
                    pass
            vol = self._volume_m3(doc)
            return self._result(not bad, f"Ricostruito: {len(bad)} feature con errori; volume {vol * 1e9:.1f} mm3",
                                SwErrors.swSuccess if not bad else SwErrors.swFeatureError,
                                {"rebuild_ok": ok, "errors": bad, "volume_mm3": round(vol * 1e9, 3)})
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def rollback_to_feature(self, name: str = None, position: str = "after") -> Dict:
        """Barra di rollback: position = after (dopo la feature) | before | end (riporta alla fine)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            fm = doc.FeatureManager
            p = (position or "after").lower()
            if p == "end" or not name:
                fm.EditRollback(1, "")
            else:
                if self._find_feature(doc, name) is None:
                    return self._result(False, f"Feature '{name}' non trovata", SwErrors.swSelectionError)
                fm.EditRollback(3 if p == "before" else 4, name)
            vol = self._volume_m3(doc)
            return self._result(True, f"Rollback {p} {name or ''}: volume {vol * 1e9:.1f} mm3", SwErrors.swSuccess,
                                {"position": p, "feature": name, "volume_mm3": round(vol * 1e9, 3)})
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)
