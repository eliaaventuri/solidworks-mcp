"""
Lotto LAMIERA (flangia base, orlo, piega da schizzo, sviluppo, export DXF, parametri) (mixin).
Schemi in tools_ext/sheetmetal.py. I metodi usano gli helper di ModelingBase/ModelingOperations tramite self
(_part, _select_point, _finish, _names, _volume_m3, _mmu, _result, _features...).

Trappole API scoperte (SW 2026, laboratorio sm, vedi scripts_tmp/notes_sheetmetal.md):
 - FeatureManager.CreateCustomBendAllowance() non si chiama direttamente con il late binding ("Impossibile trovare
   membro"): prima va marcato `fm._FlagAsMethod("CreateCustomBendAllowance")`.
 - InsertSheetMetalBaseFlange2 non crea la feature (restituisce None, nessun errore): la flangia base si crea con
   CreateDefinition(34) -> proprieta' (Thickness, BendRadius, KFactor, D1EndConditionType/Distance) -> CreateFeature.
   Senza AccessSelections (per una feature nuova AccessSelections da' errore).
 - Per la flangia con profilo APERTO la profondita' e' D1EndConditionDistance (tipo 0 = cieca).
 - Modificare Thickness di "Lamiera1" (feature SheetMetal) NON cambia la flangia base: va modificata anche la
   flangia (SMBaseFlange) con GetDefinition -> AccessSelections -> ModifyDefinition.
 - Flangia sul bordo: InsertSheetMetalEdgeFlange2 crea la feature solo con uno schizzo del profilo in SketchFeats, creato
   da doc.InsertSketchForEdgeFlange (vuoto: flangia lunga zero); poi si modifica quello schizzo e si disegna il rettangolo
   del profilo (vedi sm_edge_flange). CreateDefinition(37) non crea nulla.
 - Export DXF dello sviluppo: ExportFlatPatternView(path, 1) BLOCCA lo script (COM appeso, serve --kill); SaveAs silent
   (Extension.SaveAs, opzioni 3) restituisce False errore 256 senza file; ExportToDWG2(path, "", 1, ...) False senza file.
   FUNZIONA: ExportToDWG2(path_dxf, path_sldprt_salvato, 1, True, byref R8, False, False, 1, nullo) -> True, file con
   ENTITIES. Serve il pezzo SALVATO; la mappa DXF si evita con la preferenza swDXFDontShowMap (21) = True, ripristinata
   in finally. Non usare ExportFlatPatternView (blocca).
 - Orlo rolled: InsertSheetMetalHem2 crea la feature solo con DAngle = pi (rad); con DAngle 0 non crea nulla.
 - Orlo tear_drop: nessuna feature in 7 varianti (ReliefTearTypes 0/1/3, UseDefaultRelief, DAngle pi, pi/2, DRad 0,002):
   tipo NON esposto.
 - K-factor del pezzo: la modifica di KFactor (ISheetMetalFeatureData e IBaseFlangeFeatureData, anche con
   OverrideKFactor e con l'oggetto GetCustomBendAllowance) NON si persiste (rilettura 0,5 dopo il set 0,4): sm_parameters
   legge K ma non lo modifica. Orlo e piega da schizzo usano K = 0,5 fisso (PCBA).
 - Orlo InsertSheetMetalHem2: funziona con lo spigolo SELEZIONATO prima (mark 0).
 - Piega da schizzo InsertSheetMetal3dBend: funziona con SOLO lo schizzo selezionato; con la faccia fissa
   selezionata in aggiunta non crea nulla (provato mark 1 e mark 0). Il lato fisso lo sceglie SolidWorks.
 - Sviluppo: feature "FlatPattern" creata da SolidWorks; IsSuppressed True = piegata (stato iniziale).
   SetSuppression2(1, 2, ...) = sviluppata (swUnSuppressFeature = 1), SetSuppression2(0, 2, ...) = piegata.
"""

import os
import math
import logging
import traceback
from typing import Dict

import pythoncom
import win32com.client

from ..constants import SwErrors

logger = logging.getLogger(__name__)

_FM_BASE_FLANGE = 34            # swFeatureNameID_e.swFmBaseFlange
_HEM_TYPES = {"open": 0, "closed": 1, "rolled": 3}   # swHemTypes_e (tear_drop 2 non creato: vedi notes)
_HEM_POSITIONS = {"inside": 0, "outside": 1}                          # swHemPositionTypes_e
_BEND_POSITIONS = {"material_inside": 1, "material_outside": 2, "bend_outside": 3}   # swFlangePositionTypes_e
_K_DEFAULT = 0.5
_K_TYPE_RATIO = 2               # swBendAllowanceType: K-factor


class SheetMetalOperations:
    """Mixin del lotto sheetmetal."""

    # ----------------------------------------------------------------------------------------- helper interni
    @staticmethod
    def _sm_null():
        return win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)

    def _sm_cba(self, fm, k: float):
        """Oggetto CustomBendAllowance (K-factor) per le feature di lamiera."""
        fm._FlagAsMethod("CreateCustomBendAllowance")
        pc = fm.CreateCustomBendAllowance()
        pc.Type = _K_TYPE_RATIO
        pc.KFactor = float(k)
        return pc

    def _sm_box(self):
        """Ingombro del pezzo in mm: (min, max) oppure (None, None)."""
        try:
            r = self.get_bounding_box(unit="mm")
            d = r.get("data") or {}
            return d.get("min"), d.get("max")
        except Exception:
            return None, None

    def _sm_check_k(self, k):
        k = float(k)
        if not 0.0 <= k <= 1.0:
            return None, self._result(False, "k_factor deve essere fra 0 e 1 (ratio, tipico 0.5)", SwErrors.swInvalidInput)
        return k, None

    # ----------------------------------------------------------------------------------------- 1. flangia base
    def sm_base_flange(self, sketch: str = None, thickness: float = None, bend_radius: float = None,
                       depth: float = None, k_factor: float = _K_DEFAULT, reverse: bool = False, unit: str = None) -> Dict:
        """Flangia base (lamiera): da schizzo chiuso = lamiera piana; da schizzo aperto = profilo estruso di depth."""
        try:
            if thickness is None:
                return self._result(False, "thickness obbligatorio (spessore in `unit`, es. 2 mm)", SwErrors.swInvalidInput)
            k, err = self._sm_check_k(k_factor if k_factor is not None else _K_DEFAULT)
            if err:
                return err
            doc, err = self._part()
            if err:
                return err
            name, err = self._resolve_sketch(doc, sketch)
            if err:
                return err
            t = self._mmu(float(thickness), unit)
            if t <= 0:
                return self._result(False, "thickness deve essere > 0", SwErrors.swInvalidInput)
            r = self._mmu(float(bend_radius if bend_radius is not None else thickness), unit)
            d = self._mmu(float(depth), unit) if depth is not None else 0.0
            before = self._names(doc)
            v0 = self._volume_m3(doc)
            doc.ClearSelection2(True)
            self._select_feature(doc, name, False, 0)
            fm = doc.FeatureManager
            dd = fm.CreateDefinition(_FM_BASE_FLANGE)
            dd.Thickness = t
            dd.BendRadius = r
            dd.OverrideKFactor = True
            dd.KFactor = k
            dd.D1EndConditionType = 0          # cieca
            dd.D1EndConditionDistance = d
            dd.ReverseDirection = bool(reverse)
            feat = fm.CreateFeature(dd)
            doc.ClearSelection2(True)
            extra = {"sketch": name, "thickness_mm": round(t * 1000, 4), "bend_radius_mm": round(r * 1000, 4),
                     "k_factor": k, "depth_mm": round(d * 1000, 4)}
            return self._finish(doc, "Flangia base lamiera", feat, v0, before, extra)
        except Exception as e:
            logger.error(f"sm_base_flange: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ----------------------------------------------------------------------------------------- 2. orlo
    def sm_hem(self, edge_point, type: str = "closed", length: float = 5.0, gap: float = 0.5,
               bend_radius: float = 0.5, position: str = "inside", unit: str = None) -> Dict:
        """Orlo su uno spigolo di lamiera (open | closed | tear_drop | rolled); K-factor 0,5 fisso."""
        try:
            ht = _HEM_TYPES.get(str(type).lower())
            if ht is None:
                return self._result(False, "type deve essere open | closed | tear_drop | rolled", SwErrors.swInvalidInput)
            pos = _HEM_POSITIONS.get(str(position).lower())
            if pos is None:
                return self._result(False, "position deve essere inside | outside", SwErrors.swInvalidInput)
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            doc.ClearSelection2(True)
            ok, info = self._select_point(doc, "edge", edge_point, unit, False, 0, 0.05)
            if not ok:
                return self._result(False, f"Spigolo non trovato: {info.get('error')}", SwErrors.swSelectionError, info)
            L = self._mmu(float(length), unit)
            G = self._mmu(float(gap), unit)
            R = self._mmu(float(bend_radius), unit)
            before = self._names(doc)
            v0 = self._volume_m3(doc)
            fm = doc.FeatureManager
            pc = self._sm_cba(fm, _K_DEFAULT)
            angle = math.pi if str(type).lower() == "rolled" else 0.0      # rolled: senza DAngle = pi non crea nulla
            feat = fm.InsertSheetMetalHem2(ht, pos, False, L, G, angle, R, 0.0, pc, False, 1, 0, False, 0.5, 0.0, 0.0)
            doc.ClearSelection2(True)
            extra = {"hem_type": str(type).lower(), "position": str(position).lower(), "length_mm": round(L * 1000, 4),
                     "gap_mm": round(G * 1000, 4), "bend_radius_mm": round(R * 1000, 4), "k_factor": _K_DEFAULT,
                     "edge_distance_mm": info.get("distance_mm")}
            return self._finish(doc, "Orlo", feat, v0, before, extra)
        except Exception as e:
            logger.error(f"sm_hem: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ----------------------------------------------------------------------------------------- 2b. flangia sul bordo
    def sm_edge_flange(self, edge_point, length: float = 20.0, angle: float = 90.0, bend_radius: float = None,
                       position: str = "material_inside", flip: bool = False, unit: str = None) -> Dict:
        """Flangia sul bordo. Misurato (2026-10-19, laboratorio opus): InsertSheetMetalEdgeFlange2 crea la feature solo con
        uno schizzo del profilo nell'array SketchFeats; lo schizzo si crea con doc.InsertSketchForEdgeFlange(spigolo, angolo,
        flip) (metodo da marcare con _FlagAsMethod), che pero' lo lascia VUOTO (flangia lunga zero). Si modifica allora lo
        schizzo della flangia e si disegna il profilo: rettangolo con il lato inferiore sullo spigolo e altezza `length`
        lungo +y dello schizzo (che e' il verso della flangia). Lamiera 50x30x2, r 2, K 0,5, length 20 a 90 gradi:
        volume 4122,743 = t*w*((50-(r+t)) + (22-(r+t)) + pi/2*(r+t/2))."""
        try:
            pos = _BEND_POSITIONS.get(str(position).lower())
            if pos is None:
                return self._result(False, "position deve essere material_inside | material_outside | bend_outside",
                                    SwErrors.swInvalidInput)
            ang = float(angle)
            if not 0.0 < ang < 180.0:
                return self._result(False, "angle deve essere fra 0 e 180 (degrees)", SwErrors.swInvalidInput)
            h = self._mmu(float(length), unit)
            if h <= 0:
                return self._result(False, "length deve essere > 0", SwErrors.swInvalidInput)
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            doc.ClearSelection2(True)
            p = [self._mmu(float(c), unit) for c in edge_point]
            edge, dist = self._find_entity(doc, "edge", p, 0.0005)
            if edge is None:
                return self._result(False, f"Nessuno spigolo entro 0,5 mm da {list(edge_point)} (piu' vicino a {dist * 1000:.3f} mm). "
                                    "Usa list_entities(kind='edge').", SwErrors.swSelectionError)
            try:
                if not bool(self._com(self._com(edge, "GetCurve"), "IsLine")):
                    return self._result(False, "La flangia sul bordo richiede uno spigolo RETTILINEO.", SwErrors.swSelectionError)
            except Exception:
                pass
            before = self._names(doc)
            v0 = self._volume_m3(doc)
            box0 = self._sm_box()
            doc._FlagAsMethod("InsertSketchForEdgeFlange")
            doc.InsertSketchForEdgeFlange(edge, math.radians(ang), bool(flip))
            sk_new = [x["name"] for x in self._new_features(doc, before) if x["type"] == "ProfileFeature"]
            if not sk_new:
                return self._result(False, "InsertSketchForEdgeFlange non ha creato lo schizzo del profilo.", SwErrors.swFeatureError)
            self._exit_sketch(doc)
            skfeat = self._find_feature(doc, sk_new[0])
            edge, _ = self._find_entity(doc, "edge", p, 0.0005)
            arr = lambda objs: win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, tuple(objs))
            use_default = bend_radius is None
            r = 0.0 if use_default else self._mmu(float(bend_radius), unit)
            opts = 128 | (1 if use_default else 0)          # swInsertEdgeFlangeUseDefaultRelief | UseDefaultRadius
            fm = doc.FeatureManager
            doc.ClearSelection2(True)
            feat = fm.InsertSheetMetalEdgeFlange2(arr([edge]), arr([skfeat]), opts, math.radians(ang), r, pos, 0.0, 1,
                                                 0.5, 0.0005, 0.0005, 1, self._sm_null())
            new = self._new_features(doc, before)
            fl = [x["name"] for x in new if x["type"] == "EdgeFlange"]
            if feat is None and not fl:
                self._delete_features(doc, sk_new)
                return self._result(False, "SolidWorks non ha creato la flangia (spigolo non di bordo della lamiera?).",
                                    SwErrors.swFeatureError)
            fname = fl[0] if fl else self._com(feat, "Name")
            # profilo: lo schizzo assorbito dalla flangia (vuoto) -> rettangolo sul bordo, altezza h lungo +y dello schizzo
            ff = self._find_feature(doc, fname)
            sub = self._com(ff, "GetFirstSubFeature")
            prof = None
            while sub is not None:
                if self._com(sub, "GetTypeName2") == "ProfileFeature":
                    prof = self._com(sub, "Name")
                    break
                sub = self._com(sub, "GetNextSubFeature")
            if prof is None:
                return self._result(False, f"Flangia {fname} creata ma senza schizzo del profilo leggibile.", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            self._select_feature(doc, prof, False, 0)
            doc.EditSketch()
            sm = doc.SketchManager
            act = self._com(sm, "ActiveSketch")
            if act is None:
                return self._result(False, f"Impossibile modificare lo schizzo del profilo {prof}.", SwErrors.swFeatureError)
            a = [float(v) for v in self._com(self._com(act, "ModelToSketchTransform"), "ArrayData")]
            M, t, sc = [a[0:3], a[3:6], a[6:9]], a[9:12], (a[12] or 1.0)
            to_sk = lambda m: [sc * sum(M[k][i] * m[k] for k in range(3)) + t[i] for i in range(3)]
            e2, _ = self._find_entity(doc, "edge", p, 0.0005)
            s0 = self._com(e2 or edge, "GetStartVertex")
            s1 = self._com(e2 or edge, "GetEndVertex")
            q0 = to_sk([float(v) for v in self._com(s0, "GetPoint")])
            q1 = to_sk([float(v) for v in self._com(s1, "GetPoint")])
            pts = [(q0[0], q0[1]), (q1[0], q1[1]), (q1[0], q1[1] + h), (q0[0], q0[1] + h)]
            sm.AddToDB = True
            try:
                for i in range(4):
                    (xa, ya), (xb, yb) = pts[i], pts[(i + 1) % 4]
                    sm.CreateLine(xa, ya, 0.0, xb, yb, 0.0)
            finally:
                sm.AddToDB = False
            sm.InsertSketch(True)
            doc.ForceRebuild3(False)
            doc.ClearSelection2(True)
            box1 = self._sm_box()
            extra = {"edge_distance_mm": round(dist * 1000, 4), "length_mm": round(h * 1000, 4), "angle_deg": ang,
                     "bend_radius_mm": None if use_default else round(r * 1000, 4), "default_radius": use_default,
                     "position": str(position).lower(), "profile_sketch": prof,
                     "box_before_mm": box0, "box_after_mm": box1,
                     "length_note": "length = profile height from the picked edge along the flange (the outer virtual "
                                    "sharp length also includes the sheet thickness when the edge is on the far face)"}
            return self._finish(doc, "Flangia sul bordo", None, v0, before, extra, require_volume_change=True)
        except Exception as e:
            logger.error(f"sm_edge_flange: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ----------------------------------------------------------------------------------------- 3. piega da schizzo
    def sm_sketched_bend(self, sketch: str = None, angle: float = 90.0, bend_radius: float = None,
                         position: str = "material_inside", flip: bool = False, unit: str = None) -> Dict:
        """Piega lungo una linea di schizzo (su una faccia della lamiera). Il lato fisso lo sceglie SolidWorks."""
        try:
            pos = _BEND_POSITIONS.get(str(position).lower())
            if pos is None:
                return self._result(False, "position deve essere material_inside | material_outside | bend_outside",
                                    SwErrors.swInvalidInput)
            ang = float(angle)
            if not 0.0 < ang < 180.0:
                return self._result(False, "angle deve essere fra 0 e 180 (degrees)", SwErrors.swInvalidInput)
            doc, err = self._part()
            if err:
                return err
            name, err = self._resolve_sketch(doc, sketch)
            if err:
                return err
            use_default = bend_radius is None
            r = 0.0 if use_default else self._mmu(float(bend_radius), unit)
            before = self._names(doc)
            v0 = self._volume_m3(doc)
            doc.ClearSelection2(True)
            self._select_feature(doc, name, False, 0)
            fm = doc.FeatureManager
            pc = self._sm_cba(fm, _K_DEFAULT)
            feat = fm.InsertSheetMetal3dBend(math.radians(ang), use_default, r, bool(flip), pos, pc)
            doc.ClearSelection2(True)
            extra = {"sketch": name, "angle_deg": ang, "bend_radius_mm": None if use_default else round(r * 1000, 4),
                     "default_radius": use_default, "position": str(position).lower(), "k_factor": _K_DEFAULT}
            return self._finish(doc, "Piega da schizzo", feat, v0, before, extra)
        except Exception as e:
            logger.error(f"sm_sketched_bend: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ----------------------------------------------------------------------------------------- 4. sviluppo
    def sm_flatten(self, flat: bool = True) -> Dict:
        """Mostra lo sviluppo piano (flat=true) o ripiega la lamiera (flat=false) sopprimendo/attivando FlatPattern."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            fps = [(n, f) for n, t, f in self._features(doc) if t == "FlatPattern"]
            if not fps:
                return self._result(False, "Nessuna feature di sviluppo (FlatPattern): serve una lamiera (sm_base_flange).",
                                    SwErrors.swSelectionError)
            state = 1 if flat else 0                      # swUnSuppressFeature = 1 (sviluppata), swSuppressFeature = 0 (piegata)
            for n, f in fps:
                f.SetSuppression2(state, 2, self._sm_null())
            doc.EditRebuild3
            suppressed = {n: bool(self._com(f, "IsSuppressed")) for n, f in fps}
            mn, mx = self._sm_box()
            size = [round(mx[i] - mn[i], 4) for i in range(3)] if mn and mx else None
            data = {"flat": bool(flat), "suppressed": suppressed, "box_min_mm": mn, "box_max_mm": mx, "box_size_mm": size}
            if any(v == bool(flat) for v in suppressed.values()):
                return self._result(False, f"Stato dello sviluppo non cambiato: {suppressed}", SwErrors.swFeatureError, data)
            return self._result(True, ("Sviluppo mostrato" if flat else "Lamiera ripiegata") + f", ingombro {size} mm",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"sm_flatten: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ----------------------------------------------------------------------------------------- 5. export DXF
    def sm_export_flat_pattern(self, filepath: str, overwrite: bool = False, bend_lines: bool = False) -> Dict:
        """Esporta lo sviluppo piano in DXF (ExportToDWG2, azione swExportToDWG_ExportSheetMetal). Il pezzo deve essere salvato."""
        app = None
        prev = None
        try:
            path = os.path.abspath(str(filepath))
            if not path.lower().endswith(".dxf"):
                return self._result(False, "filepath deve terminare con .dxf (percorso assoluto)", SwErrors.swInvalidInput)
            if not os.path.isdir(os.path.dirname(path)):
                return self._result(False, f"Cartella inesistente: {os.path.dirname(path)}", SwErrors.swInvalidInput)
            if os.path.exists(path) and not overwrite:
                return self._result(False, f"Il file esiste gia' ({path}): ripeti con overwrite=true.", SwErrors.swInvalidInput)
            doc, err = self._part()
            if err:
                return err
            src = str(doc.GetPathName or "")
            if not src or not os.path.exists(src):
                return self._result(False, "Il pezzo non e' salvato: salvalo prima (save_document) e riprova, "
                                    "l'export DXF richiede il file .sldprt.", SwErrors.swInvalidInput)
            r = self.sm_flatten(True)
            if not r.get("success"):
                return r
            app = self._sw_app
            # finestra di dialogo della mappa DXF: preferenza swDXFDontShowMap (21) impostata a True e ripristinata
            prev = bool(app.GetUserPreferenceToggle(21))
            app.SetUserPreferenceToggle(21, True)
            try:
                if os.path.exists(path):
                    os.remove(path)
                al = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_R8, 0.0)
                ok = doc.ExportToDWG2(path, src, 1, True, al, False, False, 5 if bend_lines else 1, self._sm_null())
            finally:
                app.SetUserPreferenceToggle(21, prev)
            size = os.path.getsize(path) if os.path.exists(path) else 0
            data = {"filepath": path, "bytes": size, "export_return": bool(ok), "bend_lines": bool(bend_lines),
                    "source": src}
            if size <= 0:
                return self._result(False, "Export DXF non riuscito: file assente o vuoto.", SwErrors.swFeatureError, data)
            return self._result(True, f"Sviluppo esportato in DXF ({size} byte)", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"sm_export_flat_pattern: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ----------------------------------------------------------------------------------------- 6. parametri
    def _sm_read_sheet(self, sd) -> Dict:
        return {"thickness_mm": round(float(sd.Thickness) * 1000, 4), "bend_radius_mm": round(float(sd.BendRadius) * 1000, 4),
                "k_factor": round(float(sd.KFactor), 4), "bend_allowance_type": int(sd.BendAllowanceType)}

    def sm_parameters(self, thickness: float = None, bend_radius: float = None, unit: str = None) -> Dict:
        """Legge (senza argomenti) o modifica spessore e raggio di piega della lamiera e delle sue flange base (K solo in lettura)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            sheets = [f for n, t, f in self._features(doc) if t == "SheetMetal"]
            if not sheets:
                return self._result(False, "Nessuna lamiera nel modello (serve sm_base_flange).", SwErrors.swSelectionError)
            sheet = sheets[0]
            sd = sheet.GetDefinition
            sd.AccessSelections(doc, self._sm_null())
            if thickness is None and bend_radius is None:
                data = self._sm_read_sheet(sd)
                sd.ReleaseSelectionAccess()
                return self._result(True, f"Lamiera: spessore {data['thickness_mm']} mm, raggio {data['bend_radius_mm']} mm, "
                                    f"K {data['k_factor']}", SwErrors.swSuccess, data)
            t = self._mmu(float(thickness), unit) if thickness is not None else None
            r = self._mmu(float(bend_radius), unit) if bend_radius is not None else None
            if t is not None:
                sd.Thickness = t
            if r is not None:
                sd.BendRadius = r
            sheet.ModifyDefinition(sd, doc, self._sm_null())
            sd.ReleaseSelectionAccess()
            updated = []
            for n, t_, f in self._features(doc):
                if t_ != "SMBaseFlange":
                    continue
                bd = f.GetDefinition
                bd.AccessSelections(doc, self._sm_null())
                if t is not None:
                    bd.Thickness = t
                if r is not None:
                    bd.BendRadius = r
                f.ModifyDefinition(bd, doc, self._sm_null())
                bd.ReleaseSelectionAccess()
                updated.append(n)
            doc.EditRebuild3
            sheets = [f for n, t_, f in self._features(doc) if t_ == "SheetMetal"]
            sd2 = sheets[0].GetDefinition
            sd2.AccessSelections(doc, self._sm_null())
            data = self._sm_read_sheet(sd2)
            sd2.ReleaseSelectionAccess()
            data["updated_base_flanges"] = updated
            data["volume_mm3"] = round(self._volume_m3(doc) * 1e9, 4)
            return self._result(True, f"Parametri modificati: spessore {data['thickness_mm']} mm, volume "
                                f"{data['volume_mm3']} mm3", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"sm_parameters: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)
