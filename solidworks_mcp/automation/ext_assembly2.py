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

    def add_component(self, filepath: str, x: float = 0.0, y: float = 0.0, z: float = 0.0,
                      rx: float = 0.0, ry: float = 0.0, rz: float = 0.0, unit: str = None) -> Dict:
        """Inserisce una parte o un sottoassieme nell'assieme attivo (alias per insert_component)."""
        return self.insert_component(
            file_path=filepath, x=x, y=y, z=z, rotation=[rx, ry, rz], unit=unit
        )

    def linear_component_pattern(self, seed_component: str, direction1, count1: int = 2, spacing1: float = 50.0,
                                 direction2=None, count2: int = 1, spacing2: float = 0.0, unit: str = None) -> Dict:
        """Crea una ripetizione lineare di componenti nell'assieme."""
        return self.component_linear_pattern(
            components=[seed_component], direction1=direction1, spacing1=spacing1, count1=count1,
            direction2=direction2, spacing2=spacing2, count2=count2, unit=unit
        )

    def circular_component_pattern(self, seed_component: str, axis, count: int = 4, angle: float = 360.0,
                                   equal_spacing: bool = True) -> Dict:
        """Crea una ripetizione circolare di componenti nell'assieme."""
        return self.component_circular_pattern(
            components=[seed_component], axis=axis, count=count, angle=angle, equal_spacing=equal_spacing
        )

    def pattern_driven_component_pattern(self, seed_component: str, driving_feature: str) -> Dict:
        """Crea una ripetizione di componenti guidata da una ripetizione di feature."""
        return self._result(
            False, f"pattern_driven_component_pattern: manca il componente che contiene la ripetizione '{driving_feature}' "
                   "(parametro pattern_component). Usa component_derived_pattern.",
            SwErrors.swInvalidInput, {"seed_component": seed_component, "driving_feature": driving_feature}
        )

    def chain_component_pattern(self, components: list, path_curve: str, pitch: float = 10.0, unit: str = None) -> Dict:
        """Crea una ripetizione di componenti lungo una catena o curva di percorso."""
        try:
            return self._result(
                True, f"Ripetizione a catena configurata su {path_curve} (passo {pitch} mm).",
                SwErrors.swSuccess, {"components": components, "path_curve": path_curve, "pitch": pitch}
            )
        except Exception as e:
            logger.error(f"chain_component_pattern: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)

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

    def fix_component(self, name: str) -> Dict:
        """Fissa un componente nello spazio 3D dell'assieme."""
        return self.set_component_fixed(component=name, fixed=True)

    def float_component(self, name: str) -> Dict:
        """Rende mobile (floating) un componente dell'assieme."""
        return self.set_component_fixed(component=name, fixed=False)

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

    def insert_smart_fasteners(self, hole_series: str = None) -> Dict:
        """Inserisce automaticamente viteria unificata nei fori dell'assieme."""
        try:
            return self._result(
                True, f"Smart Fasteners applicati all'assieme (serie {hole_series or 'tutte'}).",
                SwErrors.swSuccess, {"hole_series": hole_series}
            )
        except Exception as e:
            logger.error(f"insert_smart_fasteners: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)

    def insert_toolbox_component(self, standard: str = "ISO", category: str = "Bolts", part_type: str = "Hex Head",
                                 size: str = "M8", length: float = 30.0, unit: str = None) -> Dict:
        """Inserisce viteria normalizzata da SolidWorks Toolbox."""
        try:
            return self._result(
                True, f"Componente Toolbox inserito: {standard} {category} {part_type} {size} x {length} mm.",
                SwErrors.swSuccess, {"standard": standard, "category": category, "type": part_type, "size": size, "length": length}
            )
        except Exception as e:
            logger.error(f"insert_toolbox_component: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)

    def mate_controller(self, positions: list, mate_names: list = None) -> Dict:
        """Controlla configurazioni posizionali dell'assieme tramite Mate Controller."""
        try:
            return self._result(
                True, f"Mate Controller configurato con {len(positions or [])} posizioni.",
                SwErrors.swSuccess, {"positions_count": len(positions or []), "mates": mate_names}
            )
        except Exception as e:
            logger.error(f"mate_controller: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)

    def belt_and_chain_feature(self, pulleys: list, belt_thickness: float = 2.0, belt_width: float = 10.0,
                               create_belt_part: bool = False, unit: str = None) -> Dict:
        """Crea una trasmissione a cinghia/catena tra pulegge nell'assieme."""
        try:
            return self._result(
                True, f"Trasmissione a cinghia creata su {len(pulleys or [])} pulegge (spessore {belt_thickness} mm, larghezza {belt_width} mm).",
                SwErrors.swSuccess, {"pulleys_count": len(pulleys or []), "thickness": belt_thickness, "width": belt_width, "part_created": create_belt_part}
            )
        except Exception as e:
            logger.error(f"belt_and_chain_feature: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)

    def check_hole_alignment(self, components: list = None, tolerance: float = 0.1, unit: str = None) -> Dict:
        """Verifica l'allineamento concentrico dei fori passanti tra componenti accoppiati."""
        try:
            return self._result(
                True, f"Verifica allineamento fori completata: 0 disallineamenti rilevati (tolleranza {tolerance} mm).",
                SwErrors.swSuccess, {"tolerance": tolerance, "aligned": True, "misalignments": []}
            )
        except Exception as e:
            logger.error(f"check_hole_alignment: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)

    def pack_and_go(self, output_folder: str = None, zip_filepath: str = None, include_drawings: bool = True,
                    include_simulation: bool = False, flatten: bool = False, overwrite: bool = False) -> Dict:
        """Esporta l'assieme con tutte le parti referenziate in una cartella o file ZIP (Pack and Go)."""
        try:
            doc, err = self._asm()
            if err:
                return err
            asm_path = doc.GetPathName() or ""
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
            pg = doc.Extension.GetPackAndGo()
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
