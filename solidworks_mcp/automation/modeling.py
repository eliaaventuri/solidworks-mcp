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


from ..constants import SwErrors
from .modeling_base import ModelingBase, r8_array, null_variant
from .sketch_constraints import SketchConstraintOperations
from ..utils.sw_lang import lang_folders

logger = logging.getLogger(__name__)

END_CONDITIONS = {
    "blind": 0, "through_all": 1, "through_all_both": 9, "up_to_next": 2, "up_to_surface": 4,
    "offset_from_surface": 5, "mid_plane": 6, "symmetric": 6, "up_to_body": 7, "up_to_vertex": 3,
}
# parete sottile: swThinWallType_e (misurato su FeatureExtrusionThin2.RevThinDir: 0 verso l'esterno del profilo,
# 1 verso l'interno, 2 mezzeria, 3 due direzioni con Thk1 + Thk2)
THIN_TYPES = {"one_direction": 0, "opposite_direction": 1, "mid_plane": 2, "two_directions": 3}

# Misure metriche M3..M70 (ISO 261, serie grossa): Ø di passaggio ISO 273 fine/media/grossa, punta per maschiatura
# (D - P) e passo grosso. M70 non e' nella serie grossa ne' in ISO 273: passo 6 (ISO 261, terza scelta), punta 64,
# Ø di passaggio interpolati fra M68 e M72 (72/76/80). Misurato (2026-10-18): il database di SolidWorks non ha M60 tra
# i fori di passaggio, M52 filettato solo come 'M52x5.0', M68 e M70 per nessun tipo -> create_hole ripiega da solo.
_METRIC = {   # misura: (passaggio fine, media, grossa, punta, passo grosso)
    "M3": (3.2, 3.4, 3.6, 2.5, "0.5"), "M4": (4.3, 4.5, 4.8, 3.3, "0.7"), "M5": (5.3, 5.5, 5.8, 4.2, "0.8"),
    "M6": (6.4, 6.6, 7.0, 5.0, "1.0"), "M8": (8.4, 9.0, 10.0, 6.8, "1.25"), "M10": (10.5, 11.0, 12.0, 8.5, "1.5"),
    "M12": (13.0, 13.5, 14.5, 10.2, "1.75"), "M14": (15.0, 15.5, 16.5, 12.0, "2.0"), "M16": (17.0, 17.5, 18.5, 14.0, "2.0"),
    "M18": (19.0, 20.0, 21.0, 15.5, "2.5"), "M20": (21.0, 22.0, 24.0, 17.5, "2.5"), "M22": (23.0, 24.0, 26.0, 19.5, "2.5"),
    "M24": (25.0, 26.0, 28.0, 21.0, "3.0"), "M27": (28.0, 30.0, 32.0, 24.0, "3.0"), "M30": (31.0, 33.0, 35.0, 26.5, "3.5"),
    "M33": (34.0, 36.0, 38.0, 29.5, "3.5"), "M36": (37.0, 39.0, 42.0, 32.0, "4.0"), "M39": (40.0, 42.0, 45.0, 35.0, "4.0"),
    "M42": (43.0, 45.0, 48.0, 37.5, "4.5"), "M45": (46.0, 48.0, 52.0, 40.5, "4.5"), "M48": (50.0, 52.0, 56.0, 43.0, "5.0"),
    "M52": (54.0, 56.0, 62.0, 47.0, "5.0"), "M56": (58.0, 62.0, 66.0, 50.5, "5.5"), "M60": (62.0, 66.0, 70.0, 54.5, "5.5"),
    "M64": (66.0, 70.0, 74.0, 58.0, "6.0"), "M68": (70.0, 74.0, 78.0, 62.0, "6.0"), "M70": (72.0, 76.0, 80.0, 64.0, "6.0"),
}
CLEARANCE_MM = {k: v[1] for k, v in _METRIC.items()}
TAP_DRILL_MM = {k: v[3] for k, v in _METRIC.items()}
NOMINAL_MM = {k: float(k[1:]) for k in _METRIC}
CLEARANCE_FIT_MM = {"close": {k: v[0] for k, v in _METRIC.items()}, "normal": CLEARANCE_MM,
                    "loose": {k: v[2] for k, v in _METRIC.items()}}
COARSE_PITCH = {k: v[4] for k, v in _METRIC.items()}
# Lamati e svasati sopra M20 nel database (misurato 2026-10-18, ISO e DIN): la norma della vite decide le misure.
BIG_HEAD_SIZES = {"counterbore": "M24, M30, M36, M42, M48, M56, M64 (head socket, hex, hex_cap, hex_machine)",
                  "countersink": "nessuna (DIN socket: M24)"}
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

    def _readback(self, doc, feature: str, props: Dict[str, str]) -> Dict:
        """Rilegge dalla definizione della feature le proprieta' indicate {chiave risultato: nome proprieta'}."""
        out = {}
        try:
            f = self._find_feature(doc, feature)
            d = f.GetDefinition if f is not None else None
            for key, prop in props.items():
                try:
                    out[key] = self._com(d, prop)
                except Exception:
                    pass
        except Exception:
            pass
        return out

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
    START_CONDITIONS = {"sketch_plane": 0, "surface": 1, "face": 1, "vertex": 2, "offset": 3}

    def _extrude_common(self, cut: bool, sketch, depth, end_condition, depth2, end_condition2, draft_angle,
                        draft_outward, up_to_face_point, offset, reverse, flip_side_to_cut, merge, unit,
                        start_offset, label, start_from=None, start_ref=None, thin_thickness=None, thin_type=None,
                        thin_thickness2=None, cap_ends=False, cap_thickness=None, up_to_vertex_point=None):
        doc, err = self._part()
        if err:
            return err
        sf = (start_from or ("offset" if start_offset else "sketch_plane")).lower()
        if sf not in self.START_CONDITIONS:
            return self._result(False, f"start_from sconosciuto: {start_from}. Valide: sketch_plane | offset | surface | vertex",
                                SwErrors.swInvalidInput)
        t0 = self.START_CONDITIONS[sf]
        if sf in ("surface", "face", "vertex") and not start_ref:
            return self._result(False, f"start_from={sf} richiede start_ref: " +
                                ("{\"face\":[x,y,z]} (punto sulla faccia o sulla superficie)" if sf != "vertex" else
                                 "{\"vertex\":[x,y,z]}"), SwErrors.swInvalidInput)
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
        if t1 == 3:
            if not up_to_vertex_point:
                return self._result(False, "Per up_to_vertex serve up_to_vertex_point=[x,y,z] (punto SUL vertice di arresto).",
                                    SwErrors.swInvalidInput)
            ok, info = self._select_point(doc, "vertex", up_to_vertex_point, unit, True, 1)
            if not ok:
                return self._result(False, info.get("error", "vertice di arresto non trovato"), SwErrors.swSelectionError)
        if t1 == 7:
            if not up_to_face_point:
                return self._result(False, "Per up_to_body serve up_to_face_point=[x,y,z] (punto su una faccia del corpo "
                                    "di arresto).", SwErrors.swInvalidInput)
            body = self._body_of_point(doc, up_to_face_point, unit)
            if body is None:
                return self._result(False, f"Nessun corpo ha una faccia nel punto {list(up_to_face_point)}.",
                                    SwErrors.swSelectionError)
            if not body.Select2(True, self._sd(doc, 1)):
                return self._result(False, "Corpo di arresto non selezionabile.", SwErrors.swSelectionError)
        if t0 in (1, 2):
            # partenza da superficie / vertice: l'entita' si seleziona con Mark=32 (superficie) / 0 (vertice) DOPO lo schizzo
            ref = start_ref
            if isinstance(ref, (list, tuple)):
                ref = {"face" if t0 == 1 else "vertex": ref}
            if not isinstance(ref, dict) or ("face" if t0 == 1 else "vertex") not in ref:
                return self._result(False, f"start_ref per start_from={sf}: " +
                                    ("{\"face\":[x,y,z]}" if t0 == 1 else "{\"vertex\":[x,y,z]}"), SwErrors.swInvalidInput)
            ok, msg, _ = self._select_any(doc, ref, unit, True, 32 if t0 == 1 else 0)
            if not ok:
                return self._result(False, f"Partenza ({sf}): {msg}", SwErrors.swSelectionError)
        d1 = self._mmu(offset if t1 == 5 else (depth or 0), unit)
        d2 = self._mmu(depth2 or 0, unit)
        dr = bool(draft_angle)
        ang = math.radians(draft_angle or 0)
        fm = doc.FeatureManager
        feat = None
        thin = thin_thickness is not None and float(thin_thickness) > 0
        tt = (thin_type or "one_direction").lower()
        if thin and tt not in THIN_TYPES:
            return self._result(False, f"thin_type sconosciuto: {thin_type}. Valide: {sorted(THIN_TYPES)}", SwErrors.swInvalidInput)
        try:
            if thin:
                thk1 = self._mmu(thin_thickness, unit)
                thk2 = self._mmu(thin_thickness2 if thin_thickness2 is not None else 0, unit)
                if tt == "two_directions" and thk2 <= 0:
                    return self._result(False, "thin_type=two_directions richiede thin_thickness2 > 0.", SwErrors.swInvalidInput)
                endthk = self._mmu(cap_thickness if cap_thickness is not None else thin_thickness, unit)
                cap = 1 if cap_ends else 0
                if cut:
                    feat = fm.FeatureCutThin2(sd, bool(reverse), False, t1, t2, d1, d2, dr, False, bool(draft_outward), False,
                                              ang, 0.0, False, False, False, False, thk1, thk2, endthk, THIN_TYPES[tt], cap,
                                              False, 0.0, True, True, t0, self._mmu(start_offset or 0, unit), False)
                else:
                    feat = fm.FeatureExtrusionThin2(sd, bool(reverse), False, t1, t2, d1, d2, dr, False, bool(draft_outward),
                                                    False, ang, 0.0, False, False, False, False, bool(merge), thk1, thk2,
                                                    endthk, THIN_TYPES[tt], cap, False, 0.0, True, True, t0,
                                                    self._mmu(start_offset or 0, unit), False)
            elif cut:
                feat = fm.FeatureCut4(sd, bool(reverse), False, t1, t2, d1, d2, dr, False, bool(draft_outward), False,
                                      ang, 0.0, False, False, False, False, False, True, True, False, False, False,
                                      t0, self._mmu(start_offset or 0, unit), False, False)
            else:
                feat = fm.FeatureExtrusion3(sd, bool(reverse), False, t1, t2, d1, d2, dr, False, bool(draft_outward),
                                            False, ang, 0.0, False, False, False, False, bool(merge), True, True,
                                            t0, self._mmu(start_offset or 0, unit), False)
        except Exception as e:
            return self._result(False, f"{label} fallito: {e}", SwErrors.swFeatureError)
        doc.ClearSelection2(True)
        extra = {"sketch": sk_name, "end_condition": ec, "depth": depth, "unit": self._unit_name(unit),
                 "draft_angle": draft_angle or 0, "start_from": sf}
        if thin:
            extra.update({"thin_thickness": thin_thickness, "thin_type": tt, "cap_ends": bool(cap_ends)})
            if tt == "two_directions":
                extra["thin_thickness2"] = thin_thickness2
        if sf == "offset":
            extra["start_offset"] = start_offset
        return self._finish(doc, label, feat, v0, before, extra, require_volume_change=True)

    def _body_of_point(self, doc, pt, unit=None, tol_mm: float = 0.05):
        """Corpo che ha una faccia passante per il punto `pt` (modello, `unit`); None se non c'e'."""
        p = [self._mmu(float(c), unit) for c in pt]
        for body in self._bodies(doc):
            try:
                for f in (self._com(body, "GetFaces") or []):
                    if self._closest(f, "face", p) <= max(tol_mm, 0.001) / 1000.0:
                        return body
            except Exception:
                continue
        return None

    def extrude_boss(self, sketch: str = None, depth: float = 10, end_condition: str = "blind",
                     depth2: float = None, end_condition2: str = None, draft_angle: float = 0,
                     draft_outward: bool = False, up_to_face_point: list = None, offset: float = 0,
                     reverse: bool = False, merge: bool = True, start_offset: float = 0, unit: str = None,
                     start_from: str = None, start_ref: Any = None, thin_thickness: float = None,
                     thin_type: str = None, thin_thickness2: float = None, cap_ends: bool = False,
                     cap_thickness: float = None, up_to_vertex_point: list = None) -> Dict:
        """Estrusione base/aggiunta con condizioni finali: blind | through_all | through_all_both | mid_plane |
        up_to_next | up_to_surface | offset_from_surface | up_to_vertex (up_to_vertex_point) | up_to_body (up_to_face_point =
        punto su una faccia del corpo); sformo (gradi) e seconda direzione. Partenza `start_from`:
        sketch_plane (default) | offset (start_offset) | surface (start_ref={"face":[x,y,z]}) | vertex (start_ref={"vertex":[..]}).
        Parete sottile: thin_thickness (+ thin_type one_direction | opposite_direction | mid_plane | two_directions con
        thin_thickness2; cap_ends/cap_thickness per chiudere i profili chiusi)."""
        try:
            return self._extrude_common(False, sketch, depth, end_condition, depth2, end_condition2, draft_angle,
                                        draft_outward, up_to_face_point, offset, reverse, False, merge, unit,
                                        start_offset, "Estrusione", start_from, start_ref, thin_thickness, thin_type,
                                        thin_thickness2, cap_ends, cap_thickness, up_to_vertex_point)
        except Exception as e:
            logger.error(f"extrude_boss: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def extrude_cut(self, sketch: str = None, depth: float = 10, end_condition: str = "blind",
                    depth2: float = None, end_condition2: str = None, draft_angle: float = 0,
                    draft_outward: bool = False, up_to_face_point: list = None, offset: float = 0,
                    reverse: bool = False, start_offset: float = 0, unit: str = None,
                    start_from: str = None, start_ref: Any = None, thin_thickness: float = None,
                    thin_type: str = None, thin_thickness2: float = None, cap_ends: bool = False,
                    cap_thickness: float = None, up_to_vertex_point: list = None) -> Dict:
        """Taglio estruso con le stesse condizioni finali, partenze e parete sottile di extrude_boss (reverse=True
        taglia dall'altra parte)."""
        try:
            return self._extrude_common(True, sketch, depth, end_condition, depth2, end_condition2, draft_angle,
                                        draft_outward, up_to_face_point, offset, reverse, False, True, unit,
                                        start_offset, "Taglio estruso", start_from, start_ref, thin_thickness, thin_type,
                                        thin_thickness2, cap_ends, cap_thickness, up_to_vertex_point)
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
        # asse: id di un segmento dello schizzo, oppure asse di riferimento (nome o {"axis":nome}), spigolo lineare del
        # modello ({"edge":[x,y,z]}), linea di un altro schizzo ({"sketch":..,"entity":..}); senza `axis` l'unica linea
        # di costruzione/asse di mezzeria dello schizzo
        segs = self._sketch_segments_of(doc, sk_name)
        axis_seg = None
        axis_kind = None
        if isinstance(axis, dict) and "id" in axis:
            axis = axis["id"]
        if axis:
            if isinstance(axis, str):
                for s in segs:
                    if self._seg_id(s) == axis:
                        axis_seg = s
                        axis_kind = "sketch_segment"
            if axis_seg is None:
                spec = axis if isinstance(axis, (dict, list, tuple)) else {"axis": axis}
                if isinstance(spec, dict) and "sketch" in spec and "entity" in spec:
                    # linea di un ALTRO schizzo: Select4 viene accettato ma FeatureRevolve2 non la usa (misurato);
                    # funziona SelectByID2("<nome>@<schizzo>", "SKETCHSEGMENT", .., Mark=4) anche se restituisce False
                    obj, desc, e = self._sketch_entity_obj(doc, spec["sketch"], spec["entity"], unit)
                    if e:
                        return self._result(False, f"Asse: {e}", SwErrors.swSelectionError)
                    nm = self._com(obj, "GetName")
                    doc.Extension.SelectByID2(f"{nm}@{spec['sketch']}", "SKETCHSEGMENT", 0, 0, 0, True, 4, null_variant(), 0)
                    ok, msg = self._sel_count(doc) >= 2, "linea dell'altro schizzo non selezionata"
                else:
                    ok, msg, desc = self._select_any(doc, spec, unit, True, 4)
                if not ok:
                    return self._result(False, f"Asse '{axis}' non selezionabile: {msg} (id di un segmento dello schizzo "
                                        f"{sk_name}, nome di un asse di riferimento, {{\"edge\":[x,y,z]}} o "
                                        "{\"sketch\":nome,\"entity\":id})", SwErrors.swSelectionError)
                axis_kind = ("model_edge" if isinstance(spec, (list, tuple)) or "edge" in spec else
                             "other_sketch" if "sketch" in spec else "reference_axis")
        else:
            cl = [s for s in segs if int(s.GetType) == 0 and bool(s.ConstructionGeometry)]
            if len(cl) >= 1:
                axis_seg = cl[0]
                axis_kind = "sketch_centerline"
        if axis_seg is not None:
            axis_seg.Select4(True, self._sd(doc, 4))
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
                            {"sketch": sk_name, "angle": angle,
                             "axis_found": axis_seg is not None or axis_kind is not None, "axis_kind": axis_kind},
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
    # swTangencyType_e (sweep: partenza/arrivo; loft: condizione iniziale/finale)
    TANGENCY = {"none": 0, "normal_to_profile": 1, "path_tangent": 1, "tangent": 1, "direction_vector": 2, "all_faces": 3}

    def _tangency(self, value, what: str):
        """-> (codice swTangencyType_e, errore). value: nome, bool (True = normal_to_profile) o None."""
        if value is None or value is False:
            return 0, None
        if value is True:
            return 1, None
        key = str(value).lower()
        if key not in self.TANGENCY:
            return None, self._result(False, f"{what} sconosciuta: {value}. Valide: {sorted(self.TANGENCY)}",
                                      SwErrors.swInvalidInput)
        return self.TANGENCY[key], None

    def _thin_args(self, thin_thickness, thin_thickness2, thin_type, unit):
        """-> (is_thin, spessore1, spessore2, tipo swThinWallType_e, errore)."""
        if thin_thickness is None or float(thin_thickness) <= 0:
            return False, 0.0, 0.0, 0, None
        tt = (thin_type or "one_direction").lower()
        if tt not in THIN_TYPES:
            return False, 0.0, 0.0, 0, self._result(False, f"thin_type sconosciuto: {thin_type}. Valide: {sorted(THIN_TYPES)}",
                                                    SwErrors.swInvalidInput)
        t2 = self._mmu(thin_thickness2, unit) if thin_thickness2 else 0.0
        if tt == "two_directions" and t2 <= 0:
            return False, 0.0, 0.0, 0, self._result(False, "thin_type=two_directions richiede thin_thickness2 > 0.",
                                                    SwErrors.swInvalidInput)
        return True, self._mmu(thin_thickness, unit), t2, THIN_TYPES[tt], None

    def sweep(self, profile_sketch: str = None, path_sketch: str = None, cut: bool = False,
              circular_diameter: float = None, twist_angle: float = 0, keep_normal: bool = True,
              unit: str = None, guide_sketches: list = None, thin_thickness: float = None,
              thin_type: str = None, thin_thickness2: float = None, start_tangency=None, end_tangency=None,
              merge: bool = True) -> Dict:
        """Sweep (base o taglio): schizzo profilo + percorso; oppure solo percorso con circular_diameter (profilo
        circolare). Il percorso e' uno schizzo (anche 3D) o QUALUNQUE feature curva (elica, curva composita, curva per punti).
        guide_sketches = curve guida (nomi di schizzi/curve); thin_thickness (+ thin_type, thin_thickness2) = parete sottile;
        start_tangency / end_tangency = none | path_tangent | all_faces; merge = unisci al corpo esistente (solo base)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            if not path_sketch:
                return self._result(False, "path_sketch obbligatorio", SwErrors.swInvalidInput)
            st, e1 = self._tangency(start_tangency, "start_tangency")
            if e1:
                return e1
            et, e2 = self._tangency(end_tangency, "end_tangency")
            if e2:
                return e2
            is_thin, thk1, thk2, thin_code, e3 = self._thin_args(thin_thickness, thin_thickness2, thin_type, unit)
            if e3:
                return e3
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            circ = circular_diameter is not None
            if not circ:
                if not profile_sketch or not self._select_feature(doc, profile_sketch, False, 1):
                    return self._result(False, f"Profilo '{profile_sketch}' non trovato", SwErrors.swSelectionError)
            if not self._select_feature(doc, path_sketch, not circ, 4):
                return self._result(False, f"Percorso '{path_sketch}' non trovato", SwErrors.swSelectionError)
            for g in (guide_sketches or []):
                if not self._select_feature(doc, g, True, 2):
                    return self._result(False, f"Guida '{g}' non trovata", SwErrors.swSelectionError)
            fm = doc.FeatureManager
            dia = self._mmu(circular_diameter or 0, unit)
            tw = 1 if twist_angle else 0     # 0 segui percorso, 1 = torsione
            if guide_sketches:
                tw = 2                       # segui percorso e prima guida (le guide scalano il profilo)
            elif keep_normal:
                tw = 0
            try:
                if cut:
                    feat = fm.InsertCutSwept5(False, 0, tw, False, False, st, et, is_thin, thk1, thk2, thin_code, 0,
                                              True, True, math.radians(twist_angle), True, False, False, False,
                                              circ, dia, 0)
                else:
                    feat = fm.InsertProtrusionSwept4(False, 0, tw, False, False, st, et, is_thin, thk1, thk2, thin_code, 0,
                                                     bool(merge), True, True, math.radians(twist_angle), True,
                                                     circ, dia, 0)
            except Exception as e:
                return self._result(False, f"Sweep fallito: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            extra = {"profile": profile_sketch, "path": path_sketch, "guides": guide_sketches or []}
            if is_thin:
                extra.update({"thin_thickness": thin_thickness, "thin_type": (thin_type or "one_direction").lower()})
            if st or et:
                extra.update({"start_tangency": st, "end_tangency": et})
            res = self._finish(doc, "Sweep taglio" if cut else "Sweep", feat, v0, before, extra,
                               require_volume_change=True)
            if res.get("success"):
                res["data"].update(self._readback(doc, res["data"].get("feature"),
                                                  {"start_tangency_readback": "StartTangencyType",
                                                   "end_tangency_readback": "EndTangencyType",
                                                   "guide_count": "GetGuideCurvesCount"}))
            return res
        except Exception as e:
            logger.error(f"sweep: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def loft(self, profile_sketches: list, guide_sketches: list = None, closed: bool = False,
             cut: bool = False, start_tangency: bool = False, start_condition=None, end_condition=None,
             start_direction=None, end_direction=None, start_tangent_length: float = 1.0,
             end_tangent_length: float = 1.0, thin_thickness: float = None, thin_type: str = None,
             thin_thickness2: float = None, merge: bool = True, centerline_sketch: str = None,
             unit: str = None, start_reverse: bool = False, end_reverse: bool = False) -> Dict:
        """Loft fra 2 o piu' profili (schizzi in ordine) con guide opzionali, condizione iniziale/finale
        (start_condition / end_condition = none | normal_to_profile | direction_vector con start_direction /
        end_direction = riferimento {"edge"|"plane"|"axis"...} e lunghezza tangente), parete sottile, merge e curva
        centrale (centerline_sketch)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            if not profile_sketches or len(profile_sketches) < 2:
                return self._result(False, "Servono almeno 2 profili.", SwErrors.swInvalidInput)
            sc, e1 = self._tangency(start_condition if start_condition is not None else start_tangency, "start_condition")
            if e1:
                return e1
            ec, e2 = self._tangency(end_condition, "end_condition")
            if e2:
                return e2
            is_thin, thk1, thk2, thin_code, e3 = self._thin_args(thin_thickness, thin_thickness2, thin_type, unit)
            if e3:
                return e3
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            for i, n in enumerate(profile_sketches):
                if not self._select_feature(doc, n, i > 0, 1):
                    return self._result(False, f"Profilo '{n}' non trovato", SwErrors.swSelectionError)
            for n in (guide_sketches or []):
                if not self._select_feature(doc, n, True, 2):
                    return self._result(False, f"Guida '{n}' non trovata", SwErrors.swSelectionError)
            if centerline_sketch and not self._select_feature(doc, centerline_sketch, True, 4):
                return self._result(False, f"Curva centrale '{centerline_sketch}' non trovata", SwErrors.swSelectionError)
            for code, ref, what, mk in ((sc, start_direction, "start_direction", 8), (ec, end_direction, "end_direction", 16)):
                if code == 2:
                    ok, msg, _ = self._select_any(doc, ref, unit, True, mk)
                    if not ok:
                        return self._result(False, f"{what}: {msg}", SwErrors.swSelectionError)
            fm = doc.FeatureManager
            try:
                if cut:
                    feat = fm.InsertCutBlend(closed, False, False, 1.0, sc, ec, is_thin, thk1, thk2, thin_code, True, True)
                else:
                    feat = fm.InsertProtrusionBlend2(closed, False, False, 1.0, sc, ec, float(start_tangent_length),
                                                     float(end_tangent_length), bool(start_reverse), bool(end_reverse), is_thin, thk1, thk2, thin_code,
                                                     bool(merge), True, True, 0)
            except Exception as e:
                return self._result(False, f"Loft fallito: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            extra = {"profiles": profile_sketches, "guides": guide_sketches or [], "start_condition": sc, "end_condition": ec}
            if centerline_sketch:
                extra["centerline"] = centerline_sketch
            if is_thin:
                extra.update({"thin_thickness": thin_thickness, "thin_type": (thin_type or "one_direction").lower()})
            res = self._finish(doc, "Loft taglio" if cut else "Loft", feat, v0, before, extra,
                               require_volume_change=True)
            if res.get("success"):
                res["data"].update(self._readback(doc, res["data"].get("feature"),
                                                  {"start_condition_readback": "StartTangencyType",
                                                   "end_condition_readback": "EndTangencyType",
                                                   "profile_count": "GetProfileCount",
                                                   "guide_count": "GetGuideCurvesCount"}))
            return res
        except Exception as e:
            logger.error(f"loft: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ shell / nervatura / sformo
    def shell_body(self, thickness: float, remove_faces: list, outward: bool = False, unit: str = None,
                   multi_thickness: list = None) -> Dict:
        """Shell: spessore e facce da rimuovere indicate da un punto su ciascuna faccia [[x,y,z],...].
        multi_thickness = [{"face":[x,y,z],"thickness":t}, ...]: facce PIANE (punto sulla faccia esterna del corpo di
        partenza) con spessore diverso. IShellFeatureData.SetMultipleThicknessAtIndex non ha effetto in SW 2026 (late
        binding: lo spessore resta 0 e la parete sparisce; provati CreateDefinition = None, indici 0/1/-1, tipi
        VT_R8/VT_R4/BYREF, InsertFeatureShellAddThickness): lo spessore diverso si ottiene con lo shell uniforme
        `thickness` + spostamento (InsertMoveFace3) della faccia interna della parete di (t_faccia - thickness)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            mt = list(multi_thickness or [])
            if mt and outward:
                return self._result(False, "multi_thickness non e' disponibile con outward=true.", SwErrors.swInvalidInput)
            plan = []
            for m in mt:
                if not isinstance(m, dict) or "face" not in m or m.get("thickness") is None or float(m["thickness"]) <= 0:
                    return self._result(False, "multi_thickness: lista di {\"face\":[x,y,z],\"thickness\":t > 0}.",
                                        SwErrors.swInvalidInput)
                p = [self._mmu(float(c), unit) for c in m["face"]]
                ent, d = self._find_entity(doc, "face", p, 0.00005)
                if ent is None:
                    return self._result(False, f"multi_thickness: nessuna faccia nel punto {m['face']}.", SwErrors.swSelectionError)
                if int(self._com(self._com(ent, "GetSurface"), "Identity")) != 4001:
                    return self._result(False, f"multi_thickness: la faccia in {m['face']} non e' piana (solo facce piane).",
                                        SwErrors.swInvalidInput)
                plan.append((p, [float(c) for c in self._com(ent, "Normal")], float(m["thickness"]), m["face"]))
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            ok, msg = self._select_points(doc, "face", remove_faces or [], unit)
            if not ok:
                return self._result(False, msg, SwErrors.swSelectionError)
            doc.InsertFeatureShell(self._mmu(thickness, unit), bool(outward))
            doc.ClearSelection2(True)
            res = self._finish(doc, "Shell", None, v0, before,
                               {"thickness": thickness, "unit": self._unit_name(unit), "faces_removed": len(remove_faces or [])},
                               require_volume_change=True)
            if not res.get("success") or not plan:
                return res
            t0 = self._mmu(thickness, unit)
            applied = []
            for p, n, tf_user, pt in plan:
                tf = self._mmu(tf_user, unit)
                if abs(tf - t0) < 1e-9:
                    applied.append({"face": pt, "thickness": tf_user})
                    continue
                q = [p[i] - n[i] * t0 for i in range(3)]          # faccia interna della parete
                inner, _ = self._find_entity(doc, "face", q, 0.00005)
                if inner is None:
                    res["success"] = False
                    res["message"] = f"Shell creato, ma la faccia interna della parete in {pt} non e' stata trovata."
                    res["data"]["multi_thickness_applied"] = applied
                    return res
                area = float(self._com(inner, "GetArea"))
                vb = self._volume_m3(doc)
                r = self.move_faces([[self._from_m(c, unit) for c in q]], mode="offset",
                                    distance=self._from_m(tf - t0, unit), unit=unit)
                if not r.get("success"):
                    res["success"] = False
                    res["message"] = (f"Shell creato ma lo spessore {tf_user} sulla faccia {pt} non e' applicabile: "
                                      f"{r.get('message')}")
                    res["data"]["multi_thickness_applied"] = applied
                    return res
                applied.append({"face": pt, "thickness": tf_user,
                                "volume_delta_mm3": round((self._volume_m3(doc) - vb) * 1e9, 3),
                                "expected_delta_mm3": round(area * (tf - t0) * 1e9, 3)})
            vol = self._volume_m3(doc)
            res["data"].update({"multi_thickness_applied": applied, "volume_mm3": round(vol * 1e9, 3),
                                "volume_delta_mm3": round((vol - v0) * 1e9, 3),
                                "method": "shell uniforme + move_faces (SetMultipleThicknessAtIndex non funziona)"})
            return res
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

    def move_faces(self, faces: list, mode: str = "offset", distance: float = None, vector: list = None,
                   direction: list = None, direction_edge: list = None, direction_axis: str = None,
                   axis: str = None, axis_point: list = None, axis_edge: list = None, angle: float = None,
                   unit: str = None) -> Dict:
        """Sposta facce (Inserisci > Facce > Sposta, InsertMoveFace3) indicate da un punto su ciascuna [[x,y,z],...].
        mode offset: ogni faccia si sposta lungo la propria normale di `distance` (negativo = verso l'interno).
        mode translate: tutte le facce si spostano del vettore `vector` [dx,dy,dz], oppure di `distance` lungo `direction`,
        oppure di `distance` lungo uno spigolo `direction_edge` o un asse `direction_axis`.
        mode rotate: rotazione di `angle` gradi attorno a un asse parallelo a X, Y o Z (`axis`) passante per `axis_point`,
        oppure attorno a uno spigolo lineare `axis_edge` [x,y,z], oppure attorno a un asse di riferimento `axis` ('Axis1')."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            mode_l = str(mode or "offset").lower()
            mode_l = {"sposta": "translate", "trasla": "translate", "ruota": "rotate", "offset": "offset"}.get(mode_l, mode_l)
            if mode_l not in ("offset", "translate", "rotate"):
                return self._result(False, f"mode sconosciuto: {mode} (offset | translate | rotate)", SwErrors.swInvalidInput)
            if not faces:
                return self._result(False, "Servono faces: un punto [x,y,z] su ogni faccia da spostare.",
                                    SwErrors.swInvalidInput)
            tp, rp, dist, rev = None, None, 0.0, False
            angle_rad = 0.0
            ref_spec_translate = None
            ref_spec_rotate = None

            if mode_l == "offset":
                if distance is None or float(distance) == 0:
                    return self._result(False, "offset: serve distance diversa da 0.", SwErrors.swInvalidInput)
                dist, rev = self._mmu(abs(float(distance)), unit), float(distance) < 0
            elif mode_l == "translate":
                if direction_edge is not None or direction_axis is not None:
                    if distance is None or float(distance) == 0:
                        return self._result(False, "translate: serve distance diversa da 0 quando si specifica un asse o spigolo.",
                                            SwErrors.swInvalidInput)
                    dist, rev = self._mmu(abs(float(distance)), unit), float(distance) < 0
                    ref_spec_translate = direction_edge if direction_edge is not None else {"axis": direction_axis}
                    v = None
                elif vector is not None:
                    v = [float(c) for c in vector]
                elif direction is not None and distance is not None:
                    d = [float(c) for c in direction]
                    n = math.sqrt(sum(c * c for c in d))
                    if n == 0:
                        return self._result(False, "translate: direction nulla.", SwErrors.swInvalidInput)
                    v = [c / n * float(distance) for c in d]
                else:
                    return self._result(False, "translate: serve vector [dx,dy,dz] oppure direction + distance, oppure direction_edge/axis + distance.",
                                        SwErrors.swInvalidInput)
                if v is not None:
                    if len(v) != 3 or not any(v):
                        return self._result(False, "translate: vettore di 3 componenti non tutte nulle.", SwErrors.swInvalidInput)
                    tp = r8_array([self._mmu(c, unit) for c in v])
            else:
                if angle is None:
                    return self._result(False, "rotate: serve angle (gradi).", SwErrors.swInvalidInput)
                if axis_edge is not None:
                    ref_spec_rotate = axis_edge
                    angle_rad = math.radians(float(angle))
                elif axis is not None and str(axis).lower() not in ("x", "y", "z"):
                    ref_spec_rotate = {"axis": axis} if isinstance(axis, str) else axis
                    angle_rad = math.radians(float(angle))
                else:
                    ax = str(axis or "").lower()
                    if ax not in ("x", "y", "z") or axis_point is None:
                        return self._result(False, "rotate: servono axis (x | y | z) e axis_point [x,y,z], oppure axis_edge [x,y,z], oppure asse di riferimento in axis.",
                                            SwErrors.swInvalidInput)
                    rot = [0.0, 0.0, 0.0]
                    rot["xyz".index(ax)] = math.radians(float(angle))
                    rp = r8_array([self._mmu(float(c), unit) for c in axis_point] + rot)

            v0 = self._volume_m3(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            ok, msg = self._select_points(doc, "face", faces, unit, mark=1)     # con mark 0 nessuna feature (misurato)
            if not ok:
                return self._result(False, msg, SwErrors.swSelectionError)

            if mode_l == "translate" and ref_spec_translate is not None:
                ok, msg = self._select_edge_or_axis(doc, ref_spec_translate, unit, mark=2, append=True)
                if not ok:
                    return self._result(False, f"Riferimento di direzione per traslazione fallito: {msg}", SwErrors.swSelectionError)

            if mode_l == "rotate" and ref_spec_rotate is not None:
                ok, msg = self._select_edge_or_axis(doc, ref_spec_rotate, unit, mark=4, append=True)
                if not ok:
                    return self._result(False, f"Riferimento asse di rotazione fallito: {msg}", SwErrors.swSelectionError)

            mt = {"offset": 0, "translate": 1, "rotate": 2}[mode_l]
            try:
                feat = doc.FeatureManager.InsertMoveFace3(mt, rev, angle_rad, dist, tp, rp, 0, 0.0)
            except Exception as e:
                return self._result(False, f"Sposta facce fallito: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            extra = {"mode": mode_l, "faces": len(faces), "unit": self._unit_name(unit)}
            if mode_l == "offset":
                extra["distance"] = distance
            elif mode_l == "translate":
                if v is not None:
                    extra["vector"] = [round(c, 6) for c in v]
                else:
                    extra["distance"] = distance
                    if direction_edge:
                        extra["direction_edge"] = direction_edge
                    if direction_axis:
                        extra["direction_axis"] = direction_axis
            else:
                extra["angle"] = angle
                if ref_spec_rotate is not None:
                    if axis_edge:
                        extra["axis_edge"] = axis_edge
                    else:
                        extra["axis"] = axis
                else:
                    extra.update({"axis": ax, "axis_point": axis_point})
            return self._finish(doc, "Sposta facce", feat, v0, before, extra)
        except Exception as e:
            logger.error(f"move_faces: {e}\n{traceback.format_exc()}")
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

    def chamfer_at_points(self, distance: float = None, edge_points: list = None, angle: float = 45.0,
                          distance2: float = None, unit: str = None, vertex_point: list = None,
                          vertex_distances: list = None, equal_distance: bool = False) -> Dict:
        """Smusso sugli spigoli indicati da un punto sullo spigolo: distance + angle (default 45), distance + distance2,
        oppure equal_distance=True (stessa distanza sui due lati). Smusso a VERTICE: vertex_point (punto SUL vertice) +
        vertex_distances [d1,d2,d3] (distanze lungo i tre spigoli; se manca, tre volte `distance`)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            vertex_mode = vertex_point is not None
            if not vertex_mode and (distance is None or not edge_points):
                return self._result(False, "Servono distance + edge_points (smusso di spigoli) oppure vertex_point + "
                                    "vertex_distances (smusso a vertice).", SwErrors.swInvalidInput)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            fm = doc.FeatureManager
            if vertex_mode:
                vd = list(vertex_distances) if vertex_distances else ([distance] * 3 if distance else None)
                if not vd or len(vd) != 3 or min(vd) <= 0:
                    return self._result(False, "vertex_distances deve essere [d1,d2,d3] con valori > 0.", SwErrors.swInvalidInput)
                ok, info = self._select_point(doc, "vertex", vertex_point, unit, False, 0)
                if not ok:
                    return self._result(False, info.get("error", "vertice non trovato"), SwErrors.swSelectionError)
                try:
                    feat = fm.InsertFeatureChamfer(0, 3, 0.0, 0.0, 0.0, self._mmu(vd[0], unit), self._mmu(vd[1], unit),
                                                   self._mmu(vd[2], unit))
                except Exception as e:
                    return self._result(False, f"Smusso a vertice fallito: {e}", SwErrors.swFeatureError)
                doc.ClearSelection2(True)
                return self._finish(doc, "Smusso a vertice", feat, v0, before,
                                    {"vertex_distances": vd, "unit": self._unit_name(unit), "mode": "vertex"},
                                    require_volume_change=True)
            ok, msg = self._select_points(doc, "edge", edge_points or [], unit)
            if not ok:
                return self._result(False, msg, SwErrors.swSelectionError)
            d1 = self._mmu(distance, unit)
            mode = "distance_distance" if distance2 else ("equal_distance" if equal_distance else "distance_angle")
            try:
                if distance2:
                    feat = fm.InsertFeatureChamfer(0, 2, d1, 0.0, self._mmu(distance2, unit), 0.0, 0.0, 0.0)
                elif equal_distance:
                    # il tipo 16 (EqualDistance) crea una feature che non scava (misurato): distanza-distanza con d1 = d2
                    feat = fm.InsertFeatureChamfer(0, 2, d1, 0.0, d1, 0.0, 0.0, 0.0)
                else:
                    feat = fm.InsertFeatureChamfer(0, 1, d1, math.radians(angle), 0.0, 0.0, 0.0, 0.0)
            except Exception as e:
                return self._result(False, f"Smusso fallito: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            return self._finish(doc, "Smusso", feat, v0, before,
                                {"distance": distance, "angle": angle, "distance2": distance2, "mode": mode,
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

    def _select_bodies(self, doc, points, unit, mark: int, append: bool = False):
        """Seleziona i corpi indicati da un punto SU una loro faccia ([[x,y,z],...]). -> (ok, errore, numero di corpi)."""
        seen = []
        for i, pt in enumerate(points or []):
            body = self._body_of_point(doc, pt, unit)
            if body is None:
                return False, f"Nessun corpo ha una faccia nel punto {list(pt)} (punto SU una faccia del corpo).", 0
            if any(self._com(body, "Name") == self._com(b, "Name") for b in seen):
                continue
            if not body.Select2(append or bool(seen), self._sd(doc, mark)):
                return False, f"Corpo in {list(pt)} non selezionabile (mark {mark}).", 0
            seen.append(body)
        return True, None, len(seen)

    def _pattern_ok(self, doc, v0: float, seed: float, n_instances: int) -> bool:
        """True se il volume e' cambiato come atteso per n_instances-1 copie (tolleranza 1%)."""
        if abs(seed) < 1e-15 or n_instances <= 1:
            return True
        delta_cut = v0 - self._volume_m3(doc)
        expected = seed * (n_instances - 1)
        return abs(delta_cut - expected) <= 0.01 * abs(expected) + 1e-15

    def linear_pattern(self, features: list = None, direction1=None, count1: int = 2, spacing1: float = 10,
                       direction2=None, count2: int = 1, spacing2: float = 0, reverse1: bool = False,
                       reverse2: bool = False, geometry_pattern: bool = False, unit: str = None,
                       bodies: list = None) -> Dict:
        """Ripetizione lineare di feature (nomi) e/o di CORPI (`bodies` = [[x,y,z],...], un punto SU una faccia di ciascun
        corpo) in 1 o 2 direzioni. direction = {"edge":[x,y,z]} (spigolo parallelo alla direzione) oppure
        {"face":[x,y,z]} (faccia piana: direzione = normale) oppure nome di asse."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            if not features and not bodies:
                return self._result(False, "Servono features (nomi) e/o bodies (punti su una faccia dei corpi).",
                                    SwErrors.swInvalidInput)
            if direction1 is None:
                return self._result(False, "direction1 obbligatoria.", SwErrors.swInvalidInput)
            features = features or []
            v0 = self._volume_m3(doc)
            n_bodies0 = len(self._bodies(doc))
            before = self._names(doc)
            two = direction2 is not None and count2 and count2 > 1
            combos = [(bool(reverse1), bool(reverse2))]
            for c in ((not reverse1, bool(reverse2)), (bool(reverse1), not reverse2), (not reverse1, not reverse2)):
                if c not in combos and (two or c[1] == bool(reverse2)):
                    combos.append(c)
            feat = None
            used = None
            fm = doc.FeatureManager
            seed = 0.0 if (geometry_pattern or not features) else self._seed_effect(doc, features)
            n_tot = int(count1) * (int(count2) if two else 1)
            n_sel = 0
            for (r1, r2) in combos:
                doc.ClearSelection2(True)
                e = self._select_features_mark(doc, features, 4)
                if e:
                    return self._result(False, e, SwErrors.swSelectionError)
                if bodies:
                    okb, eb, n_sel = self._select_bodies(doc, bodies, unit, 256, append=bool(features))
                    if not okb:
                        return self._result(False, eb, SwErrors.swSelectionError)
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
                    if bodies and not features:
                        ok_inst = len(self._bodies(doc)) > n_bodies0
                    else:
                        ok_inst = self._pattern_ok(doc, v0, seed, n_tot)
                    if ok_inst:
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
            extra = {"count1": count1, "spacing1": spacing1, "count2": count2 if two else 1,
                     "spacing2": spacing2 if two else 0, "unit": self._unit_name(unit),
                     "reversed": {"dir1": used[0], "dir2": used[1]}}
            if bodies:
                nb = len(self._bodies(doc))
                extra.update({"bodies_before": n_bodies0, "bodies_after": nb,
                              "bodies_expected_if_separate": n_bodies0 + (n_tot - 1) * n_sel})
            return self._finish(doc, "Ripetizione lineare", feat, v0, before, extra)
        except Exception as e:
            logger.error(f"linear_pattern: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def circular_pattern(self, features: list = None, axis=None, count: int = 2, angle: float = 360.0,
                         equal_spacing: bool = True, reverse: bool = False, geometry_pattern: bool = False,
                         unit: str = None, bodies: list = None) -> Dict:
        """Ripetizione circolare di feature (nomi) e/o di CORPI (`bodies` = [[x,y,z],...], un punto SU una faccia di ciascun
        corpo) attorno a un asse: {"edge":[x,y,z]} (spigolo circolare/lineare), {"face":[x,y,z]}
        (faccia cilindrica), nome di asse di riferimento ("Asse1") o asse temporaneo."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            if not features and not bodies:
                return self._result(False, "Servono features (nomi) e/o bodies (punti su una faccia dei corpi).",
                                    SwErrors.swInvalidInput)
            if axis is None:
                return self._result(False, "axis obbligatorio.", SwErrors.swInvalidInput)
            features = features or []
            v0 = self._volume_m3(doc)
            n_bodies0 = len(self._bodies(doc))
            before = self._names(doc)
            doc.ClearSelection2(True)
            seed = 0.0 if (geometry_pattern or not features) else self._seed_effect(doc, features)
            e = self._select_features_mark(doc, features, 4)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            n_sel = 0
            if bodies:
                okb, eb, n_sel = self._select_bodies(doc, bodies, unit, 256, append=bool(features))
                if not okb:
                    return self._result(False, eb, SwErrors.swSelectionError)
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
            extra = {"count": count, "angle": angle, "equal_spacing": equal_spacing}
            if bodies:
                nb = len(self._bodies(doc))
                extra.update({"bodies_before": n_bodies0, "bodies_after": nb,
                              "bodies_expected_if_separate": n_bodies0 + (int(count) - 1) * n_sel})
                if nb <= n_bodies0 and not features:
                    return self._result(False, "Ripetizione di corpi: il numero di corpi non e' aumentato (istanze fuse o "
                                        "fuori posto?).", SwErrors.swFeatureError, extra)
            return self._finish(doc, "Ripetizione circolare", feat, v0, before, extra)
        except Exception as e:
            logger.error(f"circular_pattern: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def mirror_feature(self, features: list = None, plane=None, mirror_body: bool = False,
                       merge: bool = True, geometry_pattern: bool = False, unit: str = None,
                       bodies: list = None) -> Dict:
        """Specchia feature (nomi), l'intero primo corpo (mirror_body=True) oppure i CORPI scelti (`bodies` = [[x,y,z],...],
        un punto SU una faccia di ciascun corpo) rispetto a un piano di riferimento (nome, es. 'Piano destro') o a una
        faccia piana ({"face":[x,y,z]})."""
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
            n_bodies0 = len(self._bodies(doc))
            if bodies:
                mirror_body = True
                okb, eb, _ = self._select_bodies(doc, bodies, unit, 256, append=True)
                if not okb:
                    return self._result(False, eb, SwErrors.swSelectionError)
            elif mirror_body:
                bl = self._bodies(doc)
                if not bl:
                    return self._result(False, "Nessun corpo da specchiare", SwErrors.swFeatureError)
                bl[0].Select2(True, self._sd(doc, 256))   # corpi da specchiare: Mark 256 (non 1)
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
            extra = {"features": features or [], "mirror_body": mirror_body}
            if bodies:
                extra.update({"bodies_before": n_bodies0, "bodies_after": len(self._bodies(doc)), "merge": bool(merge)})
            return self._finish(doc, "Specchiatura", feat, v0, before, extra)
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
        size: M3..M70 (anche 'M8x1.25'); ANSI pollici: '#10', '1/4', '1/4-20' (tapped: UNC grosso se manca il passo).
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
                    return self._result(False, f"Misura non supportata: {size}. Valide: {', '.join(_METRIC)}",
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
            self._names(doc)
            pick_map = None         # (F, R) dal primo foro su faccia curva: punto di pick = F^T R^T p (vedi _hw_pick)
            pos_errs = []

            # varianti provate in ordine (2026-10-18, misurato): misura del database; filettato senza passo -> con il passo
            # grosso ('M52' c'e' solo come 'M52x5.0'); foro semplice o filettato assente dal database (M60 di passaggio, M68,
            # M70) -> foro generico (Hole Wizard "legacy", tipo 5) col diametro calcolato, fondo piatto, piu' filettatura
            # cosmetica per i filettati.
            variants = [("hw", sz)]
            if metric and kind_key == "tapped" and "x" not in sz.lower():
                variants.append(("hw", f"{base}x{COARSE_PITCH[base]}"))
            if metric and kind_key in ("simple", "tapped"):
                variants.append(("legacy", sz))
            state = {"i": 0}
            cthreads = []

            def hw():
                mode, s_ = variants[state["i"]]
                if mode == "legacy":
                    return fm.HoleWizard5(5, std_idx, 0, "", end_t, dia_m, use_depth, 0.0, *([0.0] * 12), 0, False, True,
                                          True, True, True, True)
                return fm.HoleWizard5(gen, std_idx, fast, s_, end_t, dia_m, use_depth, 0.0, *vals, 0, False, True, True,
                                      True, True, True)

            u_m = self._mmu(1.0, unit)          # metri per unita' dell'utente
            for i, pt in enumerate(pts):
                doc.ClearSelection2(True)
                ok, info = self._select_point(doc, "face", pt, unit, False, 0)
                if not ok:
                    fails.append(info.get("error", "faccia non trovata"))
                    continue
                p_m = [self._mmu(float(c), unit) for c in pt]
                normal = None
                try:
                    face = doc.SelectionManager.GetSelectedObject6(1, -1)
                    curved = not bool(face.GetSurface.IsPlane)
                    if not curved:
                        normal = [float(c) for c in face.Normal]
                except Exception:
                    curved = False
                feat, err, exc = None, None, None
                for _ in range(len(variants)):
                    if curved:
                        try:
                            feat, err, pick_map = self._hw_on_curved(doc, hw, pt, p_m, unit, pick_map)
                        except Exception as ex:
                            exc = ex
                    else:
                        doc.ClearSelection2(True)
                        self._select_point(doc, "face", pt, unit, False, 0)
                        try:
                            feat = hw()
                        except Exception as ex:
                            exc = ex
                        doc.ClearSelection2(True)
                    if feat is not None or state["i"] + 1 >= len(variants):
                        break
                    state["i"] += 1                 # vale anche per i punti seguenti
                if feat is None:
                    why = f"{exc}" if exc else ("HoleWizard5 non ha creato il foro" + (" sulla faccia curva" if curved else ""))
                    hint = ""
                    if metric and kind_key in ("counterbore", "countersink") and NOMINAL_MM[base] > 20:
                        hint = (f"; sopra M20 il database di SolidWorks ha {kind_key} solo per {BIG_HEAD_SIZES[kind_key]}: "
                                f"la norma della vite non prevede {base}")
                    fails.append(f"punto {pt}: {why} (parametri non validi per {kind} {sz} {std_key}: controlla misura e "
                                 f"head{', oppure punto non raggiungibile' if curved else ''}){hint}")
                    continue
                if curved:
                    if err is None or err > 1e-5:
                        fails.append(f"punto {pt}: foro creato ma il centro e' a "
                                     f"{'?' if err is None else round(err * 1000, 4)} mm dal punto richiesto")
                    if err is not None:
                        pos_errs.append(round(err * 1000, 6))
                if variants[state["i"]][0] == "legacy" and kind_key == "tapped":
                    # filettatura cosmetica sullo spigolo d'ingresso (Ø punta): tipo 1 = passante, 0 = cieca per thread_depth
                    ct_name = None
                    if normal is not None:
                        a = [1.0, 0.0, 0.0] if abs(normal[0]) < 0.9 else [0.0, 1.0, 0.0]
                        uu = [normal[1] * a[2] - normal[2] * a[1], normal[2] * a[0] - normal[0] * a[2],
                              normal[0] * a[1] - normal[1] * a[0]]
                        ln = math.sqrt(sum(c * c for c in uu))
                        r_u = dia_m / 2 / u_m
                        ep = [float(c) + r_u * uu[k] / ln for k, c in enumerate(pt)]
                        doc.ClearSelection2(True)
                        okc, _ = self._select_point(doc, "edge", ep, unit, False, 0)
                        if okc:
                            p_txt = (sz.lower().split("x")[1] if "x" in sz.lower() else COARSE_PITCH[base])
                            p_txt = p_txt[:-2] if p_txt.endswith(".0") else p_txt
                            try:
                                ct = fm.InsertCosmeticThread2(1 if through else 0, NOMINAL_MM[base] / 1000.0,
                                                              0.0 if through else vals[0], f"{base}x{p_txt}")
                                ct_name = self._com(ct, "Name") if ct is not None else None
                            except Exception:
                                ct_name = None
                        doc.ClearSelection2(True)
                    cthreads.append(ct_name)
                    if ct_name is None:
                        fails.append(f"punto {pt}: foro Ø{round(dia_m * 1000, 3)} creato, ma filettatura cosmetica "
                                     f"{base} non aggiunta" + (" (faccia curva)" if normal is None else ""))
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
                                 "curved_face_position_error_mm": pos_errs or None,
                                 "curved_face_pick_corrected": pick_map is not None,
                                 "method": {"hw": "hole_wizard", "legacy": "generic_hole"}[variants[state["i"]][0]],
                                 "database_size": variants[state["i"]][1] if variants[state["i"]][0] == "hw" else None,
                                 "cosmetic_threads": cthreads or None,
                                 "generic_hole_note": ("misura assente dal database Hole Wizard di SolidWorks: foro generico "
                                                       "col diametro calcolato (fondo piatto se cieco), filettatura cosmetica "
                                                       "per i filettati" if variants[state["i"]][0] == "legacy" else None),
                                 "size_note": ("M70: passo 6 (ISO 261), diametri di passaggio non normati (ISO 273 salta da "
                                               "M68 a M72): valori interpolati 72/76/80" if base == "M70" else None),
                                 "note": "tapped blind: la zona filettata e' modellata a Ø nominale per thread_depth, "
                                         "poi Ø punta fino a depth + punta a 118 gradi"})
        except Exception as e:
            logger.error(f"create_hole: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ foro guidato su facce curve (B4)
    # Su una faccia NON piana HoleWizard5 crea uno schizzo 3D di posizione e ci mette il punto di pick espresso nel sistema
    # del Piano frontale (F) come se fossero coordinate dello schizzo 3D (sistema R): punto reale = R F p. Con il modello
    # di parte standard F = R = identita' e non succede nulla; con un modello orientato diversamente il foro finiva ruotato
    # (2026-10-17: pick a 45 gradi -> foro a -37). Si passa quindi il pick g = F^T R^T p (misurato: scarto 0).
    def _hw_front_frame(self, doc) -> List[List[float]]:
        """Righe = asse u, asse v, normale del Piano frontale in coordinate del modello (IRefPlane.Transform)."""
        t = [float(v) for v in self._std_ref_feature(doc, "front").GetSpecificFeature2.Transform.ArrayData]
        return [t[0:3], t[3:6], t[6:9]]

    @staticmethod
    def _hw_sketch_point(feat):
        """(punto in metri nel modello, R) dello schizzo 3D di posizione di un foro guidato; None se manca."""
        try:
            sub = feat.GetFirstSubFeature
            while sub is not None:
                if sub.GetTypeName2 == "3DProfileFeature":
                    sk = sub.GetSpecificFeature2
                    a = [float(v) for v in sk.ModelToSketchTransform.ArrayData]
                    R, t = [a[0:3], a[3:6], a[6:9]], a[9:12]
                    pts = sk.GetSketchPoints2 or []
                    if len(pts) != 1:
                        return None
                    s = [pts[0].X - t[0], pts[0].Y - t[1], pts[0].Z - t[2]]   # schizzo = R^T modello + t
                    return [sum(R[i][j] * s[j] for j in range(3)) for i in range(3)], R
                sub = sub.GetNextSubFeature
        except Exception as ex:
            logger.debug(f"_hw_sketch_point: {ex}")
        return None

    _HW_R_CACHE: Dict[tuple, list] = {}      # F del modello di parte -> R misurata (vale per tutti i documenti con quel F)

    @staticmethod
    def _rotations24() -> List[List[List[int]]]:
        """Le 24 rotazioni che scambiano gli assi (matrici di permutazione con segno, determinante +1)."""
        import itertools
        out = []
        for perm in itertools.permutations(range(3)):
            for signs in itertools.product((1, -1), repeat=3):
                M = [[0] * 3 for _ in range(3)]
                for i in range(3):
                    M[i][perm[i]] = signs[i]
                det = (M[0][0] * (M[1][1] * M[2][2] - M[1][2] * M[2][1]) - M[0][1] * (M[1][0] * M[2][2] - M[1][2] * M[2][0])
                       + M[0][2] * (M[1][0] * M[2][1] - M[1][1] * M[2][0]))
                if det == 1:
                    out.append(M)
        return out

    def _hw_on_curved(self, doc, hw, pt, p_m, unit, pick_map):
        """Foro su faccia curva nel punto p_m. -> (feature o None, scarto in metri o None, pick_map).
        Ordine: R gia' nota (cache per F) -> pick diretto (se il foro esce fuori posto si legge R dal suo schizzo e si rifa')
        -> se HoleWizard5 rifiuta il pick diretto (il punto ruotato cade fuori dalla faccia), le 24 rotazioni possibili.
        Ogni foro e' accettato solo se il punto del suo schizzo di posizione coincide con quello richiesto."""
        F = self._hw_front_frame(doc)
        key = tuple(round(v, 6) for row in F for v in row)
        if pick_map is None and key in self._HW_R_CACHE:
            pick_map = (F, self._HW_R_CACHE[key])

        def attempt(pick):
            doc.ClearSelection2(True)
            self._select_point(doc, "face", pt, unit, False, 0, pick=pick)
            f = hw()
            doc.ClearSelection2(True)
            if f is None:
                return None, None, None
            got = self._hw_sketch_point(f)
            return f, (math.dist(got[0], p_m) if got else None), (got[1] if got else None)

        def drop(f):
            f.Select2(False, 0)
            doc.Extension.DeleteSelection2(1)           # swDelete_Absorbed: anche lo schizzo di posizione
            doc.ClearSelection2(True)

        tried = []
        if pick_map is not None:
            tried.append(pick_map[1])
            f, err, R = attempt(self._hw_pick(pick_map, p_m))
            if f is not None and err is not None and err <= 1e-5:
                return f, err, pick_map
            if f is not None:
                drop(f)
        f, err, R = attempt(None)                       # pick diretto
        if f is not None and err is not None and err <= 1e-6:
            return f, err, pick_map
        if f is not None and R is not None:
            drop(f)
            pick_map = (F, R)
            f, err, _ = attempt(self._hw_pick(pick_map, p_m))
            if f is not None and err is not None and err <= 1e-5:
                self._HW_R_CACHE[key] = R
                return f, err, pick_map
            if f is not None:
                drop(f)
            tried.append(R)
        for Rc in self._rotations24():
            if Rc in tried:
                continue
            f, err, _ = attempt(self._hw_pick((F, Rc), p_m))
            if f is None:
                continue
            if err is not None and err <= 1e-5:
                self._HW_R_CACHE[key] = Rc
                return f, err, (F, Rc)
            drop(f)
        return None, None, pick_map

    @staticmethod
    def _hw_pick(pick_map, p) -> List[float]:
        """Punto di pick da dare a HoleWizard5 perche' il foro cada in p: g = F^T R^T p."""
        F, R = pick_map
        u = [sum(R[j][i] * p[j] for j in range(3)) for i in range(3)]          # R^T p
        return [sum(F[j][i] * u[j] for j in range(3)) for i in range(3)]       # F^T u

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

    def _plane_ref_geom(self, doc, spec, unit):
        """Normale (uscente per le facce) e un punto (m) di un piano di riferimento o di una faccia piana:
        spec = nome del piano ("front", "Piano1") o {"plane":nome} o {"face":[x,y,z]}. -> (normale, punto, errore)."""
        if isinstance(spec, dict) and "face" in spec:
            p = [self._mmu(float(c), unit) for c in spec["face"]]
            ent, d = self._find_entity(doc, "face", p, 0.0005)
            if ent is None:
                return None, None, f"nessuna faccia nel punto {list(spec['face'])}"
            surf = self._com(ent, "GetSurface")
            if not self._com(surf, "IsPlane"):
                return None, None, f"la faccia nel punto {list(spec['face'])} non e' piana"
            pp = [float(v) for v in self._com(surf, "PlaneParams")]
            return [float(v) for v in self._com(ent, "Normal")], pp[3:6], None
        name = spec.get("plane") if isinstance(spec, dict) else spec
        feat = (self._find_feature(doc, name) or self._std_plane_feature(doc, name)) if name else None
        if feat is None:
            return None, None, f"piano '{name}' non trovato"
        try:
            t = [float(v) for v in self._com(feat, "GetSpecificFeature2").Transform.ArrayData]
        except Exception:
            return None, None, f"'{name}' non e' un piano di riferimento"
        return t[6:9], t[9:12], None

    def _plane_from_doc_call(self, doc, label: str, items: list, unit, call):
        """Seleziona items [(nome, specifica per _select_any)] e chiama call(doc) (metodo CreatePlane... di
        IModelDoc2). -> (feat, errore)."""
        doc.ClearSelection2(True)
        for i, (nm, spec) in enumerate(items):
            ok, msg, _ = self._select_any(doc, spec, unit, i > 0, 0)
            if not ok:
                return None, self._result(False, f"{nm}: {msg}", SwErrors.swSelectionError)
        try:
            return call(doc), None
        except Exception as ex:
            return None, self._result(False, f"{label} fallito: {ex}", SwErrors.swFeatureError)

    def _mid_plane(self, doc, refs, flip, unit):
        """Piano di mezzeria fra due piani/facce piane parallele. InsertRefPlane con il vincolo MidPlane (128) non crea
        nulla in SW 2026 (provati 128, 128|4, 128|8|256, 128|1/2, tutti i valori 0..42 e le coppie con 128 come secondo
        vincolo: None) e RefPlaneFeatureData non permette di cambiare tipo/vincoli. Si crea quindi un piano a distanza d/2
        dal primo riferimento e si CONTROLLA (rilettura del piano) che stia a meta' (verso scelto provando l'inversione).
        -> (feat, errore, info)."""
        if not isinstance(refs, (list, tuple)) or len(refs) != 2:
            return None, self._result(False, "mid_plane: refs = lista di 2 riferimenti (nome di piano o {\"face\":[x,y,z]})",
                                      SwErrors.swInvalidInput), None
        g = []
        for i, r in enumerate(refs):
            n, pt, e = self._plane_ref_geom(doc, r, unit)
            if e:
                return None, self._result(False, f"mid_plane, riferimento {i + 1}: {e}", SwErrors.swInvalidInput), None
            nn = math.sqrt(sum(c * c for c in n)) or 1.0
            g.append(([c / nn for c in n], pt))
        (n1, p1), (n2, p2) = g
        cr = [n1[1] * n2[2] - n1[2] * n2[1], n1[2] * n2[0] - n1[0] * n2[2], n1[0] * n2[1] - n1[1] * n2[0]]
        if math.sqrt(sum(c * c for c in cr)) > 1e-5:
            return None, self._result(False, "mid_plane: i due riferimenti non sono paralleli.", SwErrors.swInvalidInput), None
        d = sum((p2[i] - p1[i]) * n1[i] for i in range(3))
        if abs(d) < 1e-9:
            return None, self._result(False, "mid_plane: i due riferimenti sono coincidenti.", SwErrors.swInvalidInput), None
        mid = [(p1[i] + p2[i]) / 2 for i in range(3)]
        fm = doc.FeatureManager
        for fl in ((True, False) if flip else (False, True)):
            before = self._names(doc)
            doc.ClearSelection2(True)
            ok, msg, _ = self._select_any(doc, refs[0], unit, False, 0)
            if not ok:
                return None, self._result(False, f"mid_plane, riferimento 1: {msg}", SwErrors.swSelectionError), None
            feat = fm.InsertRefPlane(8 | (256 if fl else 0), abs(d) / 2, 0, 0, 0, 0)
            new = self._new_features(doc, before)
            if feat is None and not new:
                return None, self._result(False, "mid_plane: SolidWorks non ha creato il piano.", SwErrors.swFeatureError), None
            try:
                t = [float(v) for v in self._com(self._find_feature(doc, new[0]["name"]), "GetSpecificFeature2").Transform.ArrayData]
                o, nn = t[9:12], t[6:9]
            except Exception:
                o = nn = None
            if o and nn and abs(sum((mid[i] - o[i]) * nn[i] for i in range(3))) < 1e-6:
                return feat, None, {"between_refs": round(self._from_m(abs(d), unit), 4),
                                    "offset_each": round(self._from_m(abs(d) / 2, unit), 4),
                                    "method": "offset_half_distance"}
            self._delete_features(doc, [x["name"] for x in new])
        return None, self._result(False, "mid_plane: il piano creato non e' a meta' fra i due riferimenti.",
                                  SwErrors.swFeatureError), None

    def create_reference_plane(self, mode: str = "offset", base: Any = "front", distance: float = 10,
                               angle: float = 45, edge_point: list = None, points: list = None,
                               flip: bool = False, unit: str = None, refs: list = None, line: Any = None,
                               point: Any = None) -> Dict:
        """Piano di riferimento. mode: offset (base = nome piano o {"face":[x,y,z]}) | angle (base + edge_point,
        angolo in gradi attorno allo spigolo) | three_points (points = 3 vertici [[x,y,z],..]) |
        mid_plane (refs = 2 piani/facce piane parallele) | line_point (line = {"edge":[..]}/{"axis":nome}/schizzo +
        point = {"vertex":[..]}/{"point":nome}/schizzo) | normal_to_curve (line = spigolo o curva, point = punto della
        curva) | parallel_point (base = piano/faccia piana, point = vertice o punto)."""
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
            mode_extra = {}
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
                elif m in ("mid_plane", "midplane", "mezzeria"):
                    feat, err, info = self._mid_plane(doc, refs, flip, unit)
                    if err:
                        return err
                    mode_extra.update(info)
                elif m in ("line_point", "line_and_point"):
                    feat, err = self._plane_from_doc_call(doc, "Piano per linea e punto", [("Linea", line), ("Punto", point)],
                                                          unit, lambda d: d.CreatePlaneThruLineAndPt(True))
                    if err:
                        return err
                elif m in ("normal_to_curve", "normal_curve"):
                    feat, err = self._plane_from_doc_call(doc, "Piano normale alla curva", [("Curva", line), ("Punto", point)],
                                                          unit, lambda d: d.CreatePlanePerCurveAndPassPoint3(True, True))
                    if err:
                        return err
                elif m in ("parallel_point", "parallel_through_point"):
                    feat, err = self._plane_from_doc_call(doc, "Piano parallelo per un punto", [("Piano", base), ("Punto", point)],
                                                          unit, lambda d: d.CreatePlaneThruPtParallelToPlane(True))
                    if err:
                        return err
                else:
                    return self._result(False, f"mode sconosciuto: {mode} "
                                        "(offset|angle|three_points|mid_plane|line_point|normal_to_curve|parallel_point)",
                                        SwErrors.swInvalidInput)
            except Exception as ex:
                return self._result(False, f"Piano fallito: {ex}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            if feat is None and not self._new_features(doc, before):
                return self._result(False, "InsertRefPlane non ha creato il piano (selezioni incompatibili: per line_point "
                                    "il punto non deve stare sulla linea; per parallel_point serve un punto fuori dal piano)",
                                    SwErrors.swFeatureError)
            extra = {"mode": m}
            extra.update(mode_extra)
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

    def _cs_result(self, doc, feat, before, unit, extra: Dict) -> Dict:
        """Esito di un sistema di coordinate: feature + origine e assi riletti dall'API."""
        new = self._new_features(doc, before)
        fname = (self._com(feat, "Name") if feat is not None else None) or (new[0]["name"] if new else None)
        try:
            t = list(doc.Extension.GetCoordinateSystemTransformByName(fname).ArrayData)
            extra.update({"origin": [round(self._from_m(v, unit), 4) for v in t[9:12]],
                          "x_axis": [round(v, 6) for v in t[0:3]], "y_axis": [round(v, 6) for v in t[3:6]],
                          "z_axis": [round(v, 6) for v in t[6:9]], "pose_unit": self._unit_name(unit)})
        except Exception as ex:
            logger.debug(f"coordinate system pose: {ex}")
        return self._finish(doc, "Sistema di coordinate", feat, self._volume_m3(doc), before, extra)

    def create_coordinate_system(self, origin_point: list = None, x_edge_point: list = None,
                                 y_edge_point: list = None, z_edge_point: list = None, unit: str = None,
                                 x_flip: bool = False, y_flip: bool = False, z_flip: bool = False,
                                 origin: list = None, rotation: list = None) -> Dict:
        """Sistema di coordinate: origine = vertice (origin_point), assi X/Y/Z = spigoli (punti su di essi).
        Modo NUMERICO: origin [x,y,z] (`unit`, rispetto all'origine del modello) e/o rotation [rx,ry,rz] (gradi, attorno
        a X, Y, Z) con CreateCoordinateSystemUsingNumericalValues.
        x_flip/y_flip/z_flip invertono il verso dell'asse (il verso di partenza e' quello dello spigolo).
        Il risultato riporta origine e assi letti dall'API (origin, x_axis, y_axis, z_axis)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            numeric = origin is not None or rotation is not None
            if numeric:
                if (origin is not None and len(origin) != 3) or (rotation is not None and len(rotation) != 3):
                    return self._result(False, "origin e rotation devono avere 3 valori ([x,y,z], [rx,ry,rz] gradi).",
                                        SwErrors.swInvalidInput)
                if origin_point or x_edge_point or y_edge_point or z_edge_point:
                    return self._result(False, "Modo numerico (origin/rotation) e modo per selezione (origin_point, "
                                        "*_edge_point) non si combinano.", SwErrors.swInvalidInput)
                o = [self._mmu(float(c), unit) for c in (origin or [0, 0, 0])]
                r = [math.radians(float(c)) for c in (rotation or [0, 0, 0])]
                try:
                    feat = doc.FeatureManager.CreateCoordinateSystemUsingNumericalValues(
                        origin is not None, o[0], o[1], o[2], rotation is not None, r[0], r[1], r[2])
                except Exception as ex:
                    return self._result(False, f"Sistema di coordinate numerico fallito: {ex}", SwErrors.swFeatureError)
                extra = {"mode": "numeric", "requested_origin": list(origin) if origin is not None else None,
                         "requested_rotation_deg": list(rotation) if rotation is not None else None}
                return self._cs_result(doc, feat, before, unit, extra)
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
            return self._cs_result(doc, feat, before, unit, {})
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
            # Angolo se SolidWorks lo dice (tipo 3) oppure se l'utente scrive l'unita' in gradi:
            # senza questo, un angolo veniva letto/scritto come millimetri (523,6 "mm" per 30 gradi).
            try:
                angular = int(self._com(d, "GetType")) == 3
            except Exception:
                angular = False
            angular = angular or str(unit or "").lower() in ("deg", "degree", "degrees", "gradi", "grado", "°")
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
