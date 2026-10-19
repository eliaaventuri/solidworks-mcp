"""
Lotto SALDATURE (membri strutturali, taglia/estendi, tappi, fazzoletti, distinta di taglio, cordoni) (mixin).
Schemi in tools_ext/weldments.py. I metodi usano gli helper di ModelingBase/ModelingOperations tramite self
(_part, _select_point, _select_points, _finish, _names, _new_features, _volume_m3, _mmu, _result...).

Trappole API scoperte (SW 2026, laboratorio wld, vedi scripts_tmp/notes_weldments.md):
 - CreateStructuralMemberGroup() con late binding (win32com CDispatch) fallisce con "Impossibile trovare membro":
   la chiamata va fatta con Invoke(DISPATCH_METHOD) sul dispid di GetIDsOfNames (helper _wld_call).
 - La misura dei profili e' la configurazione del file .sldlfp (GetConfigurationNames), non un nome fisso.
"""

import os
import math
import logging
import traceback
from typing import Dict, List, Optional

import pythoncom
import win32com.client
from win32com.client import VARIANT

from ..constants import SwErrors

logger = logging.getLogger(__name__)

_VT_AD = pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH
_PROFILE_ROOT_PREF = 29                       # swFileLocationsWeldmentProfiles
_CORNER = {"miter": (True, 1), "butt_first": (True, 2), "butt_second": (True, 3), "none": (False, 0)}


class WeldmentsOperations:
    """Mixin del lotto weldments."""

    @staticmethod
    def _wld_call(obj, name: str, *args):
        """Chiamata di un metodo COM via Invoke(DISPATCH_METHOD): il late binding non trova alcuni metodi (es. CreateStructuralMemberGroup)."""
        oo = obj._oleobj_
        did = oo.GetIDsOfNames(0, name)
        res = oo.Invoke(did, 0, pythoncom.DISPATCH_METHOD, True, *args)
        return win32com.client.Dispatch(res) if res is not None else None

    def _wld_profile_root(self) -> str:
        return str(self._sw_app.GetUserPreferenceStringValue(_PROFILE_ROOT_PREF))

    def _wld_standards(self, root: str) -> List[str]:
        if not os.path.isdir(root):
            return []
        return sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))

    def _wld_profile_files(self, root: str, std: str) -> List[str]:
        d = os.path.join(root, std)
        return sorted(f for f in os.listdir(d) if f.lower().endswith(".sldlfp"))

    def _wld_configs(self, path: str) -> List[str]:
        try:
            return [str(c) for c in (self._sw_app.GetConfigurationNames(path) or [])]
        except Exception:
            return []

    def _wld_profile_path(self, standard: str, profile: str, size: Optional[str]):
        """-> (percorso .sldlfp, configurazione, errore). Nomi confrontati senza distinzione di maiuscole."""
        root = self._wld_profile_root()
        stds = self._wld_standards(root)
        std = next((s for s in stds if s.lower() == str(standard or "").lower()), None)
        if std is None:
            return None, None, self._result(False, f"Norma '{standard}' non trovata in {root}. Norme: {', '.join(stds)}",
                                            SwErrors.swInvalidInput)
        files = self._wld_profile_files(root, std)
        fname = next((f for f in files if os.path.splitext(f)[0].lower() == str(profile or "").lower()), None)
        if fname is None:
            return None, None, self._result(False, f"Profilo '{profile}' non trovato nella norma '{std}'. "
                                            f"Profili: {', '.join(os.path.splitext(f)[0] for f in files)}",
                                            SwErrors.swInvalidInput)
        path = os.path.join(root, std, fname)
        cfgs = self._wld_configs(path)
        if not cfgs:
            return None, None, self._result(False, f"Nessuna misura (configurazione) nel profilo {path}.",
                                            SwErrors.swFeatureError)
        if size is None:
            cfg = cfgs[0]
        else:
            cfg = next((c for c in cfgs if c.lower() == str(size).lower()), None)
            if cfg is None:
                return None, None, self._result(False, f"Misura '{size}' non presente nel profilo '{profile}'. "
                                                f"Misure (prime 30): {cfgs[:30]}", SwErrors.swInvalidInput)
        return path, cfg, None

    def list_weldment_profiles(self, standard: str = None, profile: str = None) -> Dict:
        """Norme dei profili di saldatura, tipi di profilo e misure (configurazioni) di ciascuno."""
        try:
            root = self._wld_profile_root()
            stds = self._wld_standards(root)
            if standard:
                stds = [s for s in stds if s.lower() == str(standard).lower()]
                if not stds:
                    return self._result(False, f"Norma '{standard}' non trovata in {root}.", SwErrors.swInvalidInput)
            out = []
            for std in stds:
                profs = []
                for f in self._wld_profile_files(root, std):
                    stem = os.path.splitext(f)[0]
                    if profile and stem.lower() != str(profile).lower():
                        continue
                    cfgs = self._wld_configs(os.path.join(root, std, f))
                    row = {"profile": stem, "count": len(cfgs)}
                    if profile:
                        row["sizes"] = cfgs
                    profs.append(row)
                if profs or not profile:
                    out.append({"standard": std, "profiles": profs})
            total = sum(len(s["profiles"]) for s in out)
            return self._result(True, f"{len(out)} norme, {total} profili (root {root})", SwErrors.swSuccess,
                                {"root": root, "standards": out})
        except Exception as e:
            logger.error(f"list_weldment_profiles: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def structural_member(self, sketch: str = None, segments: List[str] = None, standard: str = "iso",
                          profile: str = "square tube", size: str = None, corner_treatment: str = "miter",
                          rotation: float = 0.0) -> Dict:
        """Membri strutturali (Structural Member) sui segmenti di uno schizzo, con un profilo di saldatura."""
        try:
            doc, err = self._part()
            if err:
                return err
            name, err = self._resolve_sketch(doc, sketch)
            if err:
                return err
            feat = self._find_feature(doc, name)
            sk = self._com(feat, "GetSpecificFeature2")
            allseg = self._segments(sk)
            if segments:
                want = [segments] if isinstance(segments, str) else list(segments)
                by_id = {self._seg_id(s): s for s in allseg}
                missing = [w for w in want if w not in by_id]
                if missing:
                    return self._result(False, f"Segmenti non trovati nello schizzo '{name}': {missing}. "
                                        f"Id disponibili: {list(by_id)}", SwErrors.swSelectionError)
                chosen = [by_id[w] for w in want]
            else:
                chosen = allseg
            if not chosen:
                return self._result(False, f"Lo schizzo '{name}' non ha segmenti.", SwErrors.swSketchError)
            ct = str(corner_treatment or "miter").lower()
            if ct not in _CORNER:
                return self._result(False, "corner_treatment deve essere miter | butt_first | butt_second | none",
                                    SwErrors.swInvalidInput)
            path, cfg, err = self._wld_profile_path(standard, profile, size)
            if err:
                return err
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            nb0 = len(self._bodies(doc))
            doc.ClearSelection2(True)
            fm = doc.FeatureManager
            group = self._wld_call(fm, "CreateStructuralMemberGroup")
            group.Segments = VARIANT(_VT_AD, tuple(chosen))
            apply, ctype = _CORNER[ct]
            group.ApplyCornerTreatment = apply
            if apply:
                group.CornerTreatmentType = ctype
            group.Angle = math.radians(float(rotation or 0.0))
            feat_ins = fm.InsertStructuralWeldment5(path, 1, False, VARIANT(_VT_AD, (group,)), cfg)
            doc.ClearSelection2(True)
            nb1 = len(self._bodies(doc))
            extra = {"sketch": name, "segments": [self._seg_id(s) for s in chosen], "profile_file": path,
                     "configuration": cfg, "bodies_before": nb0, "bodies_after": nb1, "members": nb1 - nb0,
                     "corner_treatment": ct, "rotation_deg": float(rotation or 0.0)}
            if feat_ins is None and nb1 == nb0:
                return self._result(False, "SolidWorks non ha creato membri strutturali: controlla che lo schizzo sia "
                                    "chiuso e che i segmenti siano collegati.", SwErrors.swFeatureError, extra)
            return self._finish(doc, "Membro strutturale", feat_ins, v0, before, extra)
        except Exception as e:
            logger.error(f"structural_member: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def weldment_trim_extend(self, bodies_to_trim, trim_boundary, end_condition: str = "trim", gap: float = 0.0,
                             unit: str = None) -> Dict:
        """Taglia (o estende) membri strutturali fino a un corpo limite (Trim/Extend weldment)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            # EndCond 4 = swSolidworksWeldmentEndCondOptions_e.swEndConditionTrim; Options 0 = solo taglio, 1 = anche estensione
            # (misurato: con Options 0 un membro che si ferma prima del limite non viene allungato; con 1 si allunga a 130 mm)
            opt = {"trim": 0, "extend": 1}.get(str(end_condition or "trim").lower())
            if opt is None:
                return self._result(False, "end_condition: trim (taglia i membri che attraversano il limite) | "
                                    "extend (taglia e allunga anche i membri che si fermano prima)", SwErrors.swInvalidInput)
            allb = self._all_bodies(doc)
            ti, e = self._resolve_bodies(doc, bodies_to_trim, unit, allb)
            if e:
                return self._result(False, f"Membri da tagliare: {e}", SwErrors.swSelectionError)
            bi, e = self._resolve_body(doc, trim_boundary, unit, allb)
            if e:
                return self._result(False, f"Corpo limite: {e}", SwErrors.swSelectionError)
            ti = [i for i in ti if i != bi]
            if not ti:
                return self._result(False, "Il corpo limite non puo' essere anche il membro da tagliare.",
                                    SwErrors.swInvalidInput)
            names = [str(self._com(b, "Name")) for b in allb]
            trim_bodies = [allb[i] for i in ti]
            bound = allb[bi]
            v0 = self._volume_m3(doc)
            vol_each = {names[i]: round(self._body_volume(allb[i]) * 1e9, 4) for i in ti}
            before = self._names(doc)
            doc.ClearSelection2(True)
            gap_m = self._mmu(float(gap or 0.0), unit)
            feat = self._wld_call_trim(doc, opt, gap_m, trim_bodies, bound)
            doc.ClearSelection2(True)
            after = self._all_bodies(doc)
            vols_after = {}
            for b in after:
                try:
                    vols_after[str(self._com(b, "Name"))] = round(self._body_volume(b) * 1e9, 4)
                except Exception:
                    pass
            extra = {"trimmed": [names[i] for i in ti], "boundary": names[bi], "volume_each_before_mm3": vol_each,
                     "volume_each_after_mm3": vols_after, "end_condition": end_condition, "gap": float(gap or 0.0)}
            return self._finish(doc, "Taglia/estendi", feat, v0, before, extra)
        except Exception as e:
            logger.error(f"weldment_trim_extend: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def _body_volume(self, body) -> float:
        """Volume (m3) di un corpo, 0 se non misurabile."""
        try:
            return float(body.GetMassProperties(1000.0)[3])
        except Exception:
            return 0.0

    def _wld_call_trim(self, doc, options: int, gap_m: float, members, boundary):
        """InsertWeldmentTrimFeature2(EndCond=4 trim, Options (0 trim, 1 extend), GapValue, BodiesToTrim, BodiesOrFaces)."""
        return doc.FeatureManager.InsertWeldmentTrimFeature2(
            4, options, gap_m, VARIANT(_VT_AD, tuple(members)), VARIANT(_VT_AD, (boundary,)))

    def weldment_end_cap(self, face_point, thickness: float, offset: float = 0.0, chamfer: float = 0.0,
                         unit: str = None) -> Dict:
        """Tappo (End Cap) sull'estremita' di un membro strutturale: la faccia d'estremita' e' scelta da un punto."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            if float(thickness or 0) <= 0:
                return self._result(False, "thickness deve essere > 0 (`unit`).", SwErrors.swInvalidInput)
            doc.ClearSelection2(True)
            ok, info = self._select_point(doc, "face", face_point, unit)
            if not ok:
                return self._result(False, f"Faccia d'estremita' non selezionata: {info.get('error', info)}. "
                                    "Il punto deve stare SULLA faccia d'estremita' del membro (list_entities kind=face).",
                                    SwErrors.swSelectionError, {"selection": info})
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            nb0 = len(self._bodies(doc))
            off = float(offset or 0.0)
            cha = float(chamfer or 0.0)
            # swEndCapThicknessDirection_e 3 = swSpecifyInset (tappo a filo della sezione); misurato: 2 da' un anello, 1 un altro volume
            feat = doc.FeatureManager.InsertEndCapFeature3(
                self._mmu(float(thickness), unit), off != 0.0, cha > 0.0, self._mmu(off, unit), 1.0,
                self._mmu(cha, unit), False, 0.0, False, 3)
            doc.ClearSelection2(True)
            nb1 = len(self._bodies(doc))
            extra = {"face_point": list(face_point), "thickness": float(thickness), "offset": off, "chamfer": cha,
                     "bodies_before": nb0, "bodies_after": nb1, "end_cap_bodies": nb1 - nb0,
                     "face_area_mm2": info.get("area_mm2")}
            if feat is None and nb1 == nb0:
                return self._result(False, "SolidWorks non ha creato il tappo (controlla lo spessore e la faccia).",
                                    SwErrors.swFeatureError, extra)
            return self._finish(doc, "Tappo", feat, v0, before, extra)
        except Exception as e:
            logger.error(f"weldment_end_cap: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    @staticmethod
    def _wld_raw(obj, name: str, *args):
        """Invoke(DISPATCH_METHOD) del metodo COM, risultato grezzo (bool, array, oggetti)."""
        oo = obj._oleobj_
        did = oo.GetIDsOfNames(0, name)
        return oo.Invoke(did, 0, pythoncom.DISPATCH_METHOD, True, *args)

    def weldment_cut_list(self, update: bool = True) -> Dict:
        """Distinta di taglio della saldatura (cartella Elenco elementi): crea la cartella se manca, la aggiorna e legge i membri."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            folders = [f for n, t, f in self._features(doc) if t == "CutListFolder"]
            created = False
            if not folders:
                solids = self._bodies(doc)
                if not solids:
                    return self._result(False, "Nessun corpo solido per la distinta di taglio: crea prima i membri.",
                                        SwErrors.swSelectionError)
                self._wld_raw(doc.FeatureManager, "InsertWeldmentCutList2", VARIANT(_VT_AD, tuple(solids)))
                created = True
                folders = [f for n, t, f in self._features(doc) if t == "CutListFolder"]
            if not folders:
                return self._result(False, "SolidWorks non ha creato la cartella della distinta di taglio.",
                                    SwErrors.swFeatureError)
            feat = folders[0]
            fname = str(self._com(feat, "Name"))
            bf = self._com(feat, "GetSpecificFeature2")
            updated = None
            if update:
                updated = bool(self._wld_raw(bf, "UpdateCutList"))
            members = [win32com.client.Dispatch(b) for b in list(self._wld_raw(bf, "GetBodies") or [])]
            rows, groups = [], {}
            for b in members:
                bx = [round(float(v) * 1000, 3) for v in self._wld_raw(b, "GetBodyBox")]
                size = [round(bx[i + 3] - bx[i], 3) for i in range(3)]
                key = tuple(sorted(size))
                vol = round(self._body_volume(b) * 1e9, 3)
                rows.append({"body": str(self._com(b, "Name")), "box_size_mm": size, "volume_mm3": vol})
                g = groups.setdefault(key, {"quantity": 0, "box_size_mm": list(key), "volume_each_mm3": vol})
                g["quantity"] += 1
            items = list(groups.values())
            data = {"folder": fname, "created": created, "update_result": updated, "bodies": len(members),
                    "items": items, "members": rows}
            return self._result(True, f"Distinta di taglio '{fname}': {len(members)} corpi in {len(items)} voci "
                                f"(quantita' {[i['quantity'] for i in items]})", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"weldment_cut_list: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)
