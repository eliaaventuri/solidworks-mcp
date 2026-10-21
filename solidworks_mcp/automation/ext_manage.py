"""
Lotto ANALISI E GESTIONE (verifica geometria, riordino feature, cartelle, aspetto, modifica schizzo, piano dello schizzo) (mixin).
Schemi in tools_ext/manage.py. I metodi usano gli helper di ModelingBase/ModelingOperations tramite self
(_part, _select_point, _finish, _names, _new_features, _volume_m3, _mmu, _result...).

Trappole API scoperte (SW 2026, laboratorio mng, vedi scripts_tmp/notes_manage.md):
 - GetWhatsWrong(Features, ErrorCodes, Warnings) e GetErrorCode2(IsWarning): i parametri di uscita vanno passati come
   VARIANT(VT_BYREF|...); GetErrorCode2 restituisce il codice e il flag di avviso si rilegge dal VARIANT.
 - Un raggio sproporzionato (r=50 su un blocco 10x20x20) NON produce errori: SW lo accetta e il volume cambia (1094,9 mm3).
   Un raccordo r=12 su 4 spigoli invece viene rifiutato in creazione (nessuna feature creata).
"""

import logging
import traceback
from typing import Dict

import pythoncom
from win32com.client import VARIANT

from ..constants import SwErrors
from .modeling_base import r8_array

logger = logging.getLogger(__name__)

_MOVE = {"end": 1, "before": 2, "after": 3, "top": 4}     # swMoveLocation_e
_CONFIG_ALL = 2                                           # tutte le configurazioni
_FOLDER_CONTAINING = 2                                    # InsertFeatureTreeFolder2: cartella che contiene le feature selezionate
_DEFAULT_MATERIAL = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.0, 0.0]


def _byref(vt=pythoncom.VT_VARIANT):
    return VARIANT(pythoncom.VT_BYREF | vt, None)


def _as_list(v) -> list:
    """Valore di uscita (None, tupla, singolo) -> lista."""
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]


class ManageOperations:
    """Mixin del lotto manage."""

    def _ww_name(self, obj) -> str:
        """Nome di una feature (oggetto COM) o testo/codice gia' leggibile."""
        if isinstance(obj, (int, float, str)):
            return str(obj)
        try:
            return str(self._com(obj, "Name"))
        except Exception:
            return str(obj)

    def check_geometry(self) -> Dict:
        """Verifica della geometria: difetti dei corpi (Check2), GetWhatsWrong e codice di errore/avviso di ogni feature."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            bodies = []
            for b in self._all_bodies(doc):
                try:
                    dfc = int(b.Check2())
                except Exception:
                    dfc = -1
                bodies.append({"name": str(self._com(b, "Name")), "defects": dfc})
            fs, ec, wn = _byref(), _byref(), _byref()
            doc.Extension.GetWhatsWrong(fs, ec, wn)
            ww_feats = [self._ww_name(x) for x in _as_list(fs.value)]
            ww_codes = [self._ww_name(x) for x in _as_list(ec.value)]
            features = []
            for name, typ, feat in self._features(doc):
                bf = _byref(pythoncom.VT_BOOL)
                code = int(feat.GetErrorCode2(bf))
                warn = bool(bf.value)
                if code != 0 or warn:
                    features.append({"name": name, "type": typ, "error_code": code, "warning": warn})
            errors = [f for f in features if not f["warning"]]
            warnings = [f for f in features if f["warning"]]
            bad = [b for b in bodies if b["defects"] != 0]
            ok = not bad and not errors and not ww_feats
            data = {"bodies": bodies, "bodies_with_defects": bad, "features_with_errors": errors,
                    "features_with_warnings": warnings, "whats_wrong_features": ww_feats,
                    "whats_wrong_codes": ww_codes, "ok": ok}
            msg = (f"Geometria {'OK' if ok else 'CON PROBLEMI'}: {len(bodies)} corpi ({len(bad)} con difetti), "
                   f"{len(errors)} feature con errore, {len(warnings)} con avviso")
            return self._result(True, msg, SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"check_geometry: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def reorder_feature(self, name: str, target: str = None, position: str = "before") -> Dict:
        """Sposta una feature prima/dopo un'altra, in fondo o in cima all'albero (ReorderFeature2)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            pos = str(position or "before").strip().lower()
            if pos not in _MOVE:
                return self._result(False, f"position '{position}' non valida: usa before, after, end o top", SwErrors.swInvalidInput)
            if self._find_feature(doc, name) is None:
                return self._result(False, f"Feature '{name}' non trovata (list_model_features).", SwErrors.swSelectionError)
            if pos in ("before", "after") and (not target or self._find_feature(doc, target) is None):
                return self._result(False, f"Con position={pos} serve una feature di riferimento 'target' esistente.",
                                    SwErrors.swSelectionError)
            names0 = self._names(doc)
            ok = bool(doc.Extension.ReorderFeature2(name, target or "", _MOVE[pos]))
            names1 = self._names(doc)
            data = {"moved": name, "target": target or None, "position": pos, "reported_ok": ok,
                    "index_before": names0.index(name), "index_after": names1.index(name) if name in names1 else None,
                    "order_before": names0, "order_after": names1}
            if names1 == names0:
                return self._result(False, f"Ordine invariato: '{name}' non e' stata spostata ({pos} {target or ''}); "
                                    f"SolidWorks ha risposto {ok}.", SwErrors.swFeatureError, data)
            return self._result(True, f"'{name}' spostata {pos} {target or 'in fondo/cima'}: posizione "
                                f"{data['index_before']} -> {data['index_after']}", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"reorder_feature: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def create_feature_folder(self, features: list, name: str) -> Dict:
        """Raggruppa le feature indicate in una cartella dell'albero (InsertFeatureTreeFolder2, Containing) e la rinomina."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            if not features or not name:
                return self._result(False, "Servono l'elenco delle feature e il nome della cartella.", SwErrors.swInvalidInput)
            doc.ClearSelection2(True)
            for i, fname in enumerate(features):
                if not self._select_feature(doc, fname, i > 0, 0):
                    doc.ClearSelection2(True)
                    return self._result(False, f"Feature '{fname}' non trovata o non selezionabile (list_model_features).",
                                        SwErrors.swSelectionError)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            folder = doc.FeatureManager.InsertFeatureTreeFolder2(_FOLDER_CONTAINING)
            doc.ClearSelection2(True)
            nf = self._new_features(doc, before)
            if folder is None and not nf:
                return self._result(False, "SolidWorks non ha creato la cartella.", SwErrors.swFeatureError)
            if folder is None:
                for n, t, f in self._features(doc):
                    if n == nf[0]["name"]:
                        folder = f
            folder.Name = name
            names = self._names(doc)
            ftype = self._com(folder, "GetTypeName2")
            vol = self._volume_m3(doc)
            data = {"folder": name, "folder_type": ftype, "contained": list(features), "created_names": [x["name"] for x in nf],
                    "volume_before_mm3": round(v0 * 1e9, 4), "volume_after_mm3": round(vol * 1e9, 4)}
            if name not in names:
                return self._result(False, f"Cartella rinominata '{name}' non ritrovata nell'albero.", SwErrors.swFeatureError, data)
            return self._result(True, f"Cartella '{name}' ({ftype}) con {len(features)} feature (volume {v0 * 1e9:.1f} -> "
                                f"{vol * 1e9:.1f} mm3)", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"create_feature_folder: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    @staticmethod
    def _appearance_vector(current, color, transparency):
        """Vettore SolidWorks a 9 valori: R,G,B (0..1), Ambient, Diffuse, Specular, Shininess, Transparency, Emission."""
        cur = list(current) if current is not None else []
        v = [float(x) for x in cur][:9] if len(cur) >= 9 else list(_DEFAULT_MATERIAL)
        v[0], v[1], v[2] = [c / 255.0 for c in color]
        if transparency is not None:
            v[7] = float(transparency)
        return v

    def set_appearance(self, target: str, color: list, transparency: float = None, face_point: list = None,
                       body=None, feature: str = None, unit: str = None) -> Dict:
        """Colore e trasparenza di pezzo, corpo, faccia o feature (MaterialPropertyValues), riletti dopo la scrittura."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            tgt = str(target or "").strip().lower()
            if tgt not in ("part", "body", "face", "feature"):
                return self._result(False, f"target '{target}' non valido: usa part, body, face o feature", SwErrors.swInvalidInput)
            if not isinstance(color, (list, tuple)) or len(color) != 3:
                return self._result(False, "color deve essere [r,g,b] con valori 0-255", SwErrors.swInvalidInput)
            if transparency is not None and not (0.0 <= float(transparency) <= 1.0):
                return self._result(False, "transparency deve essere tra 0 e 1 (ratio)", SwErrors.swInvalidInput)
            if tgt == "part":
                obj, cur = doc, doc.MaterialPropertyValues
            elif tgt == "body":
                allb = self._all_bodies(doc)
                obj = None
                if isinstance(body, int) and 0 <= body < len(allb):
                    obj = allb[body]
                elif isinstance(body, str):
                    hits = [b for b in allb if str(self._com(b, "Name")) == body]
                    obj = hits[0] if len(hits) == 1 else None
                if obj is None:
                    return self._result(False, f"Corpo '{body}' non trovato (indice 0..{len(allb) - 1} o nome, list_bodies).",
                                        SwErrors.swSelectionError)
                cur = obj.MaterialPropertyValues2
            elif tgt == "face":
                if not face_point or len(face_point) != 3:
                    return self._result(False, "Per target=face serve face_point [x,y,z]", SwErrors.swInvalidInput)
                p = [self._mmu(float(c), unit) for c in face_point]
                obj, dist = self._find_entity(doc, "face", p, 0.0005)
                if obj is None:
                    return self._result(False, f"Nessuna faccia a meno di 0,5 mm da {face_point} (piu' vicina {dist * 1000:.3f} mm).",
                                        SwErrors.swSelectionError)
                cur = obj.MaterialPropertyValues
            else:
                feat = self._find_feature(doc, feature)
                if feat is None:
                    return self._result(False, f"Feature '{feature}' non trovata (list_model_features).", SwErrors.swSelectionError)
                obj, cur = feat, self._com(feat, "GetMaterialPropertyValues")
            vec = self._appearance_vector(cur, color, transparency)
            arr = r8_array(vec)
            if tgt == "part":
                doc.MaterialPropertyValues = arr
                rd = doc.MaterialPropertyValues
            elif tgt == "body":
                obj.MaterialPropertyValues2 = arr
                rd = obj.MaterialPropertyValues2
            elif tgt == "face":
                obj.MaterialPropertyValues = arr
                rd = obj.MaterialPropertyValues
            else:
                obj.SetMaterialPropertyValues2(arr, _CONFIG_ALL, None)
                rd = self._com(obj, "GetMaterialPropertyValues")
            got = [float(x) for x in _as_list(rd)][:9]
            if len(got) < 9:
                return self._result(False, "Il materiale non e' stato riletto (vettore vuoto).", SwErrors.swFeatureError,
                                    {"target": tgt})
            rgb_read = [round(x, 4) for x in got[:3]]
            tr_read = round(got[7], 4)
            ok = all(abs(got[i] - vec[i]) <= 0.001 for i in range(3)) and (transparency is None or abs(got[7] - float(transparency)) <= 0.001)
            data = {"target": tgt, "rgb_read_0_1": rgb_read, "transparency_read": tr_read, "vector_read": [round(x, 4) for x in got]}
            if not ok:
                return self._result(False, f"Colore letto {rgb_read} / trasparenza {tr_read} diversi da quelli scritti.",
                                    SwErrors.swFeatureError, data)
            return self._result(True, f"Aspetto ({tgt}) impostato: RGB {rgb_read}, trasparenza {tr_read}", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"set_appearance: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def edit_sketch(self, sketch: str) -> Dict:
        """Riapre uno schizzo esistente per modificarlo (EditSketch). Si chiude con close_sketch."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            doc.ClearSelection2(True)
            if not self._select_feature(doc, sketch, False, 0):
                return self._result(False, f"Schizzo '{sketch}' non trovato o non selezionabile (list_model_features).",
                                    SwErrors.swSelectionError)
            try:
                doc.EditSketch()
            except Exception:
                _ = doc.EditSketch          # alcune versioni del binding lo espongono come proprieta'
            active = self._com(doc.SketchManager, "ActiveSketch")
            doc.ClearSelection2(True)
            if active is None:
                return self._result(False, f"SolidWorks non ha aperto lo schizzo '{sketch}' in modifica.", SwErrors.swSketchError)
            return self._result(True, f"Schizzo '{sketch}' aperto in modifica (chiudilo con close_sketch)", SwErrors.swSuccess,
                                {"sketch": sketch, "editing": True})
        except Exception as e:
            logger.error(f"edit_sketch: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def _plane_info_closed(self, doc, sketch: str) -> Dict:
        """Assi dello schizzo (get_sketch_plane_info) con lo schizzo richiuso: quella lettura lo lascia in modifica
        e a volume letto con uno schizzo aperto SolidWorks restituisce 0."""
        info = self.get_sketch_plane_info(sketch)
        self._exit_sketch(doc)
        doc.ClearSelection2(True)
        doc.ForceRebuild3(False)
        return info

    def change_sketch_plane(self, sketch: str, plane, unit: str = None) -> Dict:
        """Sposta uno schizzo su un altro piano (ChangeSketchPlane). plane: Front|Top|Right oppure {"face":[x,y,z]}."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            doc.ClearSelection2(True)
            before = self._plane_info_closed(doc, sketch)
            v0 = self._volume_m3(doc)
            if not self._select_feature(doc, sketch, False, 0):
                return self._result(False, f"Schizzo '{sketch}' non trovato o non selezionabile (list_model_features).",
                                    SwErrors.swSelectionError)
            if isinstance(plane, str):
                pf = self._std_ref_feature(doc, plane.strip().lower())
                new_name = str(self._com(pf, "Name")) if pf is not None else plane
                if not self._select_feature(doc, new_name, True, 0):
                    doc.ClearSelection2(True)
                    return self._result(False, f"Piano '{plane}' non trovato (usa Front, Top, Right o un piano esistente).",
                                        SwErrors.swSelectionError)
            elif isinstance(plane, dict) and isinstance(plane.get("face"), (list, tuple)) and len(plane["face"]) == 3:
                ok, info = self._select_point(doc, "face", plane["face"], unit, True, 0)
                if not ok:
                    doc.ClearSelection2(True)
                    return self._result(False, f"Faccia {plane['face']} non trovata: {info}", SwErrors.swSelectionError)
            else:
                return self._result(False, "plane deve essere Front, Top, Right oppure {\"face\":[x,y,z]}", SwErrors.swInvalidInput)
            reported = bool(doc.Extension.ChangeSketchPlane(1, None))
            doc.ClearSelection2(True)
            after = self._plane_info_closed(doc, sketch)
            vol = self._volume_m3(doc)
            data = {"sketch": sketch, "plane": plane, "reported_ok": reported, "plane_before": before.get("data"),
                    "plane_after": after.get("data"), "volume_before_mm3": round(v0 * 1e9, 4), "volume_after_mm3": round(vol * 1e9, 4)}
            if not reported:
                return self._result(False, "SolidWorks ha rifiutato il cambio di piano (ChangeSketchPlane).", SwErrors.swFeatureError, data)
            return self._result(True, f"Schizzo '{sketch}' spostato sul piano {plane} (volume {v0 * 1e9:.1f} -> {vol * 1e9:.1f} mm3)",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"change_sketch_plane: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)
    def get_rebuild_errors(self, force_rebuild: bool = False, top_only: bool = False) -> Dict:
        """Ispeziona errori e avvisi di ricostruzione del modello attivo (What's Wrong e codici di errore delle feature)."""
        try:
            doc, err = self.get_active_doc()
            if err:
                return err

            if force_rebuild:
                try:
                    doc.ForceRebuild3(bool(top_only))
                except Exception as ex:
                    logger.warning(f"ForceRebuild3 failed: {ex}")

            # 1. Interroga GetWhatsWrong
            ww_feats, ww_codes, ww_warns = [], [], []
            try:
                fs, ec, wn = _byref(), _byref(), _byref()
                doc.Extension.GetWhatsWrong(fs, ec, wn)
                ww_feats = [self._ww_name(x) for x in _as_list(fs.value)]
                ww_codes = [self._ww_name(x) for x in _as_list(ec.value)]
                ww_warns = [bool(x) for x in _as_list(wn.value)]
            except Exception as ex:
                logger.debug(f"GetWhatsWrong not available or empty: {ex}")

            # 2. Scansione dell'albero delle feature per codici di errore
            features_with_errors = []
            features_with_warnings = []
            try:
                feat = doc.FirstFeature
                while feat:
                    fname = str(self._com(feat, "Name") or "")
                    ftype = str(feat.GetTypeName2() if hasattr(feat, "GetTypeName2") else "")

                    code = 0
                    warn = False
                    if hasattr(feat, "GetErrorCode2"):
                        try:
                            bf = _byref(pythoncom.VT_BOOL)
                            code = int(feat.GetErrorCode2(bf))
                            warn = bool(bf.value)
                        except Exception:
                            pass

                    if code != 0 or warn:
                        item = {"name": fname, "type": ftype, "error_code": code, "warning": warn}
                        if warn:
                            features_with_warnings.append(item)
                        else:
                            features_with_errors.append(item)

                    # Controlla sub-features
                    if hasattr(feat, "GetFirstSubFeature"):
                        sub_f = feat.GetFirstSubFeature()
                        while sub_f:
                            sname = str(self._com(sub_f, "Name") or "")
                            stype = str(sub_f.GetTypeName2() if hasattr(sub_f, "GetTypeName2") else "")
                            scode = 0
                            swarn = False
                            if hasattr(sub_f, "GetErrorCode2"):
                                try:
                                    sbf = _byref(pythoncom.VT_BOOL)
                                    scode = int(sub_f.GetErrorCode2(sbf))
                                    swarn = bool(sbf.value)
                                except Exception:
                                    pass
                            if scode != 0 or swarn:
                                sitem = {"name": sname, "type": stype, "error_code": scode, "warning": swarn, "parent": fname}
                                if swarn:
                                    features_with_warnings.append(sitem)
                                else:
                                    features_with_errors.append(sitem)
                            sub_f = sub_f.GetNextSubFeature() if hasattr(sub_f, "GetNextSubFeature") else None

                    feat = feat.GetNextFeature() if hasattr(feat, "GetNextFeature") else None
            except Exception as ex:
                logger.debug(f"Feature tree error scan error: {ex}")

            has_errors = bool(features_with_errors or any(not w for w in ww_warns))
            has_warnings = bool(features_with_warnings or any(w for w in ww_warns))
            rebuild_ok = not has_errors

            ww_list = []
            for i in range(len(ww_feats)):
                f_name = ww_feats[i] if i < len(ww_feats) else "Unknown"
                c_val = ww_codes[i] if i < len(ww_codes) else ""
                is_w = ww_warns[i] if i < len(ww_warns) else False
                ww_list.append({"feature": f_name, "code": c_val, "warning": is_w})

            total_errs = len(features_with_errors)
            total_warns = len(features_with_warnings)

            if rebuild_ok and not has_warnings:
                msg = "Rebuild status: OK. 0 errors, 0 warnings across all features."
            elif rebuild_ok:
                msg = f"Rebuild status: OK with warnings. {total_warns} feature warning(s) detected."
            else:
                msg = f"Rebuild status: FAILED. {total_errs} error(s) and {total_warns} warning(s) detected. Fix sketches or feature inputs."

            data = {
                "rebuild_ok": rebuild_ok,
                "has_errors": has_errors,
                "has_warnings": has_warnings,
                "error_count": total_errs,
                "warning_count": total_warns,
                "errors": features_with_errors,
                "warnings": features_with_warnings,
                "whats_wrong": ww_list,
            }
            return self._result(True, msg, SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"get_rebuild_errors: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)

