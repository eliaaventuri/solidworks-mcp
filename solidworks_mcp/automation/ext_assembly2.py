"""
Lotto ASSIEMI 2: gestione componenti, ripetizioni avanzate, Pack and Go e controlli assieme (mixin Assembly2Operations).
Schemi in tools_ext/assembly2.py.
"""

import os
import time
import logging
import traceback
from typing import Dict

from ..constants import SwErrors
from .modeling_base import null_variant

logger = logging.getLogger(__name__)


class Assembly2Operations:
    """Mixin per operazioni estese su assiemi, viteria, cinghie, allineamenti e Pack and Go."""


    def copy_with_mates(self, component: str, mate_references: list, repeat_mates: list = None) -> Dict:
        """Duplica un componente replicando i suoi accoppiamenti su nuovi riferimenti geometrici."""
        try:
            doc, err = self._asm()
            if err:
                return err
            if not doc.Extension.SelectByID2(str(component), "COMPONENT", 0, 0, 0, False, 0, null_variant(), 0):
                return self._result(False, f"copy_with_mates: '{component}' non trovato", SwErrors.swSelectionError)
            res = doc.CopyWithMates(None, None, None, None, None)
            ign = [n for n, v in (("mate_references", mate_references), ("repeat_mates", repeat_mates)) if v]
            if not res:
                return self._result(
                    False, f"copy_with_mates: duplicazione di '{component}' non riuscita (nessuna copia creata).",
                    SwErrors.swFeatureError, {"component": component, "duplicated": False, "ignored_params": ign}
                )
            return self._result(
                True, f"Componente '{component}' duplicato da SolidWorks (riferimenti di accoppiamento non applicati).",
                SwErrors.swSuccess, {"component": component, "duplicated": True, "ignored_params": ign}
            )
        except Exception as e:
            logger.error(f"copy_with_mates: {e}\n{traceback.format_exc()}")
            return self._result(False, f"copy_with_mates: duplicazione non riuscita: {e}", SwErrors.swGenericError)


    def form_new_subassembly(self, components: list, subassembly_name: str = None) -> Dict:
        """Raggruppa componenti selezionati in un nuovo sottoassieme nidificato."""
        try:
            doc, err = self._asm()
            if err:
                return err
            if not components:
                return self._result(False, "form_new_subassembly: nessun componente indicato", SwErrors.swInvalidInput)
            doc.ClearSelection2(True)
            for c in components:
                if not doc.Extension.SelectByID2(str(c), "COMPONENT", 0, 0, 0, True, 0, null_variant(), 0):
                    return self._result(False, f"form_new_subassembly: '{c}' non trovato", SwErrors.swSelectionError)
            res = doc.FormNewSubAssembly()
            ign = ["subassembly_name"] if subassembly_name else []
            if not res:
                return self._result(
                    False, "form_new_subassembly: SolidWorks non ha creato il sottoassieme.",
                    SwErrors.swFeatureError, {"components": components, "created": False, "ignored_params": ign}
                )
            nota = " (nome non applicato)" if ign else ""
            return self._result(
                True, f"Nuovo sottoassieme formato da {len(components)} componenti{nota}.",
                SwErrors.swSuccess, {"components": components, "created": True, "ignored_params": ign}
            )
        except Exception as e:
            logger.error(f"form_new_subassembly: {e}\n{traceback.format_exc()}")
            return self._result(False, f"form_new_subassembly: raggruppamento non riuscito: {e}", SwErrors.swGenericError)

    def dissolve_subassembly(self, component_name: str) -> Dict:
        """Dissolve un sottoassieme promuovendo i suoi componenti al livello superiore."""
        try:
            doc, err = self._asm()
            if err:
                return err
            doc.ClearSelection2(True)
            if not doc.Extension.SelectByID2(str(component_name), "COMPONENT", 0, 0, 0, False, 0, null_variant(), 0):
                return self._result(False, f"dissolve_subassembly: '{component_name}' non trovato", SwErrors.swSelectionError)
            res = doc.DissolveSubAssembly()
            if not res:
                return self._result(
                    False, f"dissolve_subassembly: '{component_name}' non dissolto da SolidWorks.",
                    SwErrors.swFeatureError, {"component_name": component_name, "dissolved": False}
                )
            return self._result(
                True, f"Sottoassieme '{component_name}' dissolto nel livello genitore.",
                SwErrors.swSuccess, {"component_name": component_name, "dissolved": True}
            )
        except Exception as e:
            logger.error(f"dissolve_subassembly: {e}\n{traceback.format_exc()}")
            return self._result(False, f"dissolve_subassembly: scioglimento non riuscito: {e}", SwErrors.swGenericError)

    def set_component_suppression_state(self, name: str, state: str = "resolved") -> Dict:
        """Modifica lo stato di caricamento del componente (risolto o soppresso). 'lightweight' non e' supportato."""
        st = str(state).lower().strip()
        if st == "suppressed":
            return self.suppress_component(component=name, suppressed=True)
        if st == "resolved":
            return self.suppress_component(component=name, suppressed=False)
        return self._result(
            False, f"set_component_suppression_state: stato '{state}' non supportato (usa 'resolved' o 'suppressed'); "
                   "il componente non e' stato modificato.",
            SwErrors.swInvalidInput, {"name": name, "state": state}
        )


    def pack_and_go(self, output_folder: str = None, zip_filepath: str = None, include_drawings: bool = True,
                    include_simulation: bool = False, flatten: bool = False, overwrite: bool = False) -> Dict:
        """Esporta l'assieme con tutte le parti referenziate in una cartella o file ZIP (Pack and Go)."""
        try:
            doc, err = self._asm()
            if err:
                return err
            asm_path = self._com(doc, "GetPathName") or ""
            target = zip_filepath or output_folder or os.path.dirname(asm_path) or "."
            out_file = None
            if zip_filepath:
                out_file = os.path.abspath(zip_filepath)
            elif output_folder and asm_path:
                out_file = os.path.join(os.path.abspath(output_folder), os.path.basename(asm_path))
            if out_file and os.path.exists(out_file) and not overwrite:
                return self._result(
                    False, f"pack_and_go: '{out_file}' esiste gia' (overwrite=false); nulla e' stato scritto.",
                    SwErrors.swFileAlreadyExists, {"target": target}
                )
            pg = self._com(doc.Extension, "GetPackAndGo")
            if not pg:
                return self._result(False, "Impossibile ottenere l'interfaccia Pack and Go.", SwErrors.swGenericError)
            pg.IncludeDrawings = bool(include_drawings)
            pg.IncludeSimulationResults = bool(include_simulation)
            pg.FlattenToSingleFolder = bool(flatten)
            if zip_filepath:
                os.makedirs(os.path.dirname(os.path.abspath(zip_filepath)), exist_ok=True)
                pg.SetSaveToName(True, str(zip_filepath))
            elif output_folder:
                os.makedirs(output_folder, exist_ok=True)
                pg.SetSaveToName(True, str(output_folder))
            started = time.time()
            doc.Extension.SavePackAndGo(pg)
            if zip_filepath:
                ok = (os.path.isfile(out_file) and os.path.getsize(out_file) > 0
                      and os.path.getmtime(out_file) >= started - 1)
            else:
                folder = os.path.abspath(output_folder or os.path.dirname(asm_path) or ".")
                ok = False
                for root, _dirs, files in os.walk(folder):
                    for fn in files:
                        p = os.path.join(root, fn)
                        if os.path.getsize(p) > 0 and os.path.getmtime(p) >= started - 1:
                            ok = True
                            break
                    if ok:
                        break
            if not ok:
                return self._result(False, f"pack_and_go: nessun file scritto in {target}.",
                                    SwErrors.swExportError, {"target": target})
            return self._result(
                True, f"Pack and Go completato con successo in {target}.",
                SwErrors.swSuccess, {"target": target, "drawings": include_drawings, "simulation": include_simulation}
            )
        except Exception as e:
            logger.error(f"pack_and_go: {e}\n{traceback.format_exc()}")
            return self._result(False, f"pack_and_go: esportazione non riuscita: {e}", SwErrors.swGenericError)
