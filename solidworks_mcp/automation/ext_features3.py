"""
Lotto FEATURE 3: modellazione solida 3D avanzata, feature sottili, tagli e gestione albero (mixin Features3Operations).
Schemi in tools_ext/features3.py.
"""

import os
import logging
import traceback
import win32com.client
import pythoncom
from typing import Dict

from ..constants import SwErrors, SYSTEM_FOLDER_TYPES

logger = logging.getLogger(__name__)


class Features3Operations:
    """Mixin per feature avanzate 3D, feature sottili, tagli dedicati e manipolazione albero."""


    def _picked(self, doc, spec, unit):
        """Seleziona spec (come _select_any) e restituisce l'oggetto selezionato, o (None, errore)."""
        doc.ClearSelection2(True)
        ok, msg, _d = self._select_any(doc, spec, unit, False, 0)
        if not ok:
            return None, msg or f"riferimento {spec} non selezionato"
        obj = doc.SelectionManager.GetSelectedObject6(1, -1)
        doc.ClearSelection2(True)
        return (obj, None) if obj is not None else (None, f"riferimento {spec} non leggibile")

    def insert_library_feature(self, feature_file: str, placement_plane=None, references: list = None,
                               unit: str = None) -> Dict:
        """Funzione di libreria (.sldlfp) con ILibraryFeatureData: posizionamento su una faccia/piano e i riferimenti che
        il file chiede (nomi e numero letti dal file: senza i riferimenti giusti la feature nasce in errore). Si
        controllano errori di ricostruzione e volume; se qualcosa non va le feature create si tolgono."""
        try:
            doc, err = self._part()
            if err:
                return err
            path = os.path.abspath(str(feature_file))
            if not os.path.isfile(path):
                return self._result(False, f"File non trovato: {path}", SwErrors.swFileNotFoundError)
            fm = doc.FeatureManager
            fd = fm.CreateDefinition(69)                       # swFmLibraryFeature
            if fd is None or not bool(fd.Initialize(path)):
                return self._result(False, f"SolidWorks non apre '{path}' come funzione di libreria.", SwErrors.swFeatureError)
            t = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_VARIANT, None)
            nm = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_VARIANT, None)
            try:
                fd.GetReferences3(0, t, nm)
                need = [str(x) for x in (nm.value or ())]
            except Exception:
                need = []
            refs = list(references or [])
            if len(refs) != len(need):
                return self._result(False, f"Questa funzione di libreria chiede {len(need)} riferimenti {need} "
                                    f"(spigoli: [x,y,z] o {{\"edge\":[x,y,z]}}), ricevuti {len(refs)}.",
                                    SwErrors.swInvalidInput, {"references_needed": need})
            if placement_plane is None:
                return self._result(False, "Serve placement_plane: faccia {\"face\":[x,y,z]} o piano (nome).",
                                    SwErrors.swInvalidInput, {"references_needed": need})
            place, e = self._picked(doc, placement_plane, unit)
            if e:
                return self._result(False, f"Posizionamento: {e}", SwErrors.swSelectionError)
            objs = []
            for i, r in enumerate(refs):
                o, e = self._picked(doc, r, unit)
                if e:
                    return self._result(False, f"Riferimento {i + 1} ({need[i]}): {e}", SwErrors.swSelectionError)
                objs.append(o)
            fd.SetPlacementPlane(place)
            if objs:
                fd.SetReferences(win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, objs))
            def create():
                doc.ClearSelection2(True)        # misurato 19/11: senza il posizionamento SELEZIONATO CreateFeature -> None
                place.Select4(False, self._sd(doc, 0))
                return fm.CreateFeature(fd)
            return self._create_checked(doc, f"Funzione di libreria {os.path.basename(path)}", create,
                                        extra={"feature_file": path, "references_needed": need})
        except Exception as e:
            logger.error(f"insert_library_feature: {e}\n{traceback.format_exc()}")
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

                err_code, warn = self._feat_error(feat) if hasattr(feat, "GetErrorCode2") else (0, False)
                err_code = err_code or 0          # illeggibile: non contato (la lettura unica e' in base._feat_error)

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
                            scode, swarn = self._feat_error(sub_f) if hasattr(sub_f, "GetErrorCode2") else (0, False)
                            scode = scode or 0
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
