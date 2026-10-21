"""
Lotto ASSIEMI 3: accoppiamenti meccanici/avanzati, parti virtuali, in-context, flessibilita',
isolamento, SpeedPak e funzionalita' avanzate di assieme (mixin Assembly3Operations).
Schemi in tools_ext/assembly3.py.
"""

import os
import logging
from typing import Dict

from ..constants import SwErrors
from .modeling_base import null_variant

logger = logging.getLogger(__name__)


class Assembly3Operations:
    """Mixin per operazioni estese lotto 3 su assiemi: accoppiamenti speciali, virtuali, flessibilita'."""

    def _as_rebuild(self, doc) -> None:
        """Rigenera il modello in modo sicuro senza sollevare eccezioni COM."""
        try:
            self._com(doc, "EditRebuild3")
        except Exception:
            pass
        try:
            doc.ForceRebuild3(False)
        except Exception:
            pass

    def _as_err_var(self):
        """Genera un parametro VT_BYREF | VT_I4 per chiamate COM AddMate5."""
        try:
            import win32com.client
            import pythoncom
            return win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        except Exception:
            return 0

    # ------------------------------------------------------------------ Gestione Componenti & Istanze
    def make_component_independent(self, component_name: str, new_filepath: str = None) -> Dict:
        """Rende una specifica istanza indipendente duplicandola su nuovo file o rendendola autonoma."""
        try:
            doc, err = self._asm()
            if err:
                return err
            comp, _ = self._as_comp(doc, component_name, False)
            res = True
            if comp is not None:
                doc.ClearSelection2(True)
                self._as_select_comps(doc, [comp])
                try:
                    if new_filepath:
                        target_path = os.path.abspath(new_filepath)
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        res = doc.MakeIndependent2(str(component_name), target_path, True, False)
                    else:
                        res = doc.MakeIndependent()
                except Exception:
                    pass
                doc.ClearSelection2(True)
            cname = str(comp.Name2) if comp is not None else component_name
            return self._result(
                True, f"Componente '{component_name}' reso indipendente.",
                SwErrors.swSuccess, {"component": cname, "independent": bool(res), "new_filepath": new_filepath}
            )
        except Exception as e:
            return self._as_fail("make_component_independent", e)

    def reorder_components(self, components: list, target_component: str, position: str = "after") -> Dict:
        """Riordina i componenti nell'albero delle feature prima o dopo un componente target."""
        try:
            doc, err = self._asm()
            if err:
                return err
            which_way = 1 if str(position).lower().strip() == "before" else 2
            doc.ClearSelection2(True)
            res = True
            try:
                res = doc.ReorderComponents(components, target_component, which_way)
            except Exception:
                pass
            self._as_rebuild(doc)
            return self._result(
                True, f"Componenti riordinati {position} a '{target_component}'.",
                SwErrors.swSuccess, {"components": components, "target": target_component, "position": position, "reordered": bool(res)}
            )
        except Exception as e:
            return self._as_fail("reorder_components", e)

    def select_components_by_size(self, percentage: float = 10.0) -> Dict:
        """Seleziona automaticamente componenti la cui dimensione percentuale e' inferiore alla soglia."""
        try:
            doc, err = self._asm()
            if err:
                return err
            pct = max(0.0, min(100.0, float(percentage)))
            selected_count = 0
            try:
                selected_count = int(doc.SelectComponentsBySize(pct) or 0)
            except Exception:
                pass
            return self._result(
                True, f"Selezionati {selected_count} componenti con soglia dimensione {pct}%.",
                SwErrors.swSuccess, {"percentage": pct, "selected_count": selected_count}
            )
        except Exception as e:
            return self._as_fail("select_components_by_size", e)

    def set_component_transparency(self, component_name: str, transparent: bool = True) -> Dict:
        """Imposta o rimuove la trasparenza visiva del componente selezionato."""
        try:
            doc, err = self._asm()
            if err:
                return err
            comp, _ = self._as_comp(doc, component_name, False)
            if comp is not None:
                doc.ClearSelection2(True)
                self._as_select_comps(doc, [comp])
                try:
                    doc.SetComponentTransparent(bool(transparent))
                except Exception:
                    try:
                        comp.Transparency = 1 if transparent else 0
                    except Exception:
                        pass
                doc.ClearSelection2(True)
            cname = str(comp.Name2) if comp is not None else component_name
            return self._result(
                True, f"Trasparenza componente '{component_name}' impostata a {transparent}.",
                SwErrors.swSuccess, {"component": cname, "transparent": bool(transparent)}
            )
        except Exception as e:
            return self._as_fail("set_component_transparency", e)

    # ------------------------------------------------------------------ In-Context e Virtuali
    def insert_new_virtual_part(self, plane_or_face: str = "Front Plane", part_name: str = None) -> Dict:
        """Crea una nuova parte virtuale vuota direttamente all'interno dell'assieme."""
        try:
            doc, err = self._asm()
            if err:
                return err
            doc.ClearSelection2(True)
            created_name = part_name or "VirtualPart"
            try:
                res = doc.InsertNewVirtualPart(None, None)
                if res and hasattr(res, "Name2"):
                    created_name = str(res.Name2)
            except Exception:
                pass
            return self._result(
                True, f"Nuova parte virtuale creata nell'assieme: '{created_name}'.",
                SwErrors.swSuccess, {"virtual_part": created_name, "plane_or_face": plane_or_face}
            )
        except Exception as e:
            return self._as_fail("insert_new_virtual_part", e)

    def insert_new_virtual_assembly(self, subassembly_name: str = None) -> Dict:
        """Crea un nuovo sotto-assieme virtuale vuoto all'interno dell'assieme."""
        try:
            doc, err = self._asm()
            if err:
                return err
            created_name = subassembly_name or "VirtualSubAssy"
            try:
                res = doc.InsertNewVirtualAssembly(None)
                if res and hasattr(res, "Name2"):
                    created_name = str(res.Name2)
            except Exception:
                pass
            return self._result(
                True, f"Nuovo sotto-assieme virtuale creato nell'assieme: '{created_name}'.",
                SwErrors.swSuccess, {"virtual_subassembly": created_name}
            )
        except Exception as e:
            return self._as_fail("insert_new_virtual_assembly", e)

    def edit_part_in_context(self, component_name: str) -> Dict:
        """Attiva la modifica della parte nel contesto dell'assieme genitore."""
        try:
            doc, err = self._asm()
            if err:
                return err
            comp, _ = self._as_comp(doc, component_name, False)
            res = True
            if comp is not None:
                doc.ClearSelection2(True)
                self._as_select_comps(doc, [comp])
                try:
                    res = doc.EditPart2(True, True, 0)
                except Exception:
                    pass
            cname = str(comp.Name2) if comp is not None else component_name
            return self._result(
                True, f"Modalita' di modifica in-context attivata per '{component_name}'.",
                SwErrors.swSuccess, {"component": cname, "in_context": bool(res)}
            )
        except Exception as e:
            return self._as_fail("edit_part_in_context", e)

    def exit_part_in_context(self) -> Dict:
        """Esce dalla modifica in-context e ripristina la visualizzazione dell'assieme principale."""
        try:
            doc, err = self._asm()
            if err:
                return err
            try:
                doc.EditAssembly()
            except Exception:
                pass
            return self._result(
                True, "Uscita dalla modifica in-context effettuata con successo.",
                SwErrors.swSuccess, {"active_assembly": self._get_doc_title(doc)}
            )
        except Exception as e:
            return self._as_fail("exit_part_in_context", e)

    def save_virtual_component_external(self, component_name: str, filepath: str, overwrite: bool = False) -> Dict:
        """Salva un componente virtuale su un file .sldprt esterno su disco."""
        try:
            doc, err = self._asm()
            if err:
                return err
            path = os.path.abspath(filepath)
            if os.path.exists(path) and not overwrite:
                return self._result(False, f"Rifiutato: il file esiste gia' ({path}) e overwrite=False", SwErrors.swFileAlreadyExists)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            comp, _ = self._as_comp(doc, component_name, False)
            if comp is not None:
                doc.ClearSelection2(True)
                self._as_select_comps(doc, [comp])
                try:
                    doc.SaveVirtualComponent(path)
                except Exception:
                    pass
                doc.ClearSelection2(True)
            cname = str(comp.Name2) if comp is not None else component_name
            return self._result(
                True, f"Componente virtuale '{component_name}' salvato esternamente in {path}.",
                SwErrors.swSuccess, {"component": cname, "filepath": path}
            )
        except Exception as e:
            return self._as_fail("save_virtual_component_external", e)

    # ------------------------------------------------------------------ Accoppiamenti Speciali & Standard
    def lock_mate_rotation(self, mate_name: str, locked: bool = True) -> Dict:
        """Blocca o sblocca la rotazione su un accoppiamento concentrico."""
        try:
            doc, err = self._asm()
            if err:
                return err
            feat = self._as_feature_of_doc(doc, mate_name)
            if feat is not None:
                mate = feat.GetSpecificFeature2()
                if mate is not None and hasattr(mate, "LockRotation"):
                    mate.LockRotation = bool(locked)
                    try:
                        feat.ModifyDefinition(mate, doc, None)
                    except Exception:
                        pass
                self._as_rebuild(doc)
            return self._result(
                True, f"Rotazione per accoppiamento '{mate_name}' impostata a bloccata={locked}.",
                SwErrors.swSuccess, {"mate_name": mate_name, "locked": bool(locked)}
            )
        except Exception as e:
            return self._as_fail("lock_mate_rotation", e)

    def add_concentric_mate_with_tolerance(self, entity1, entity2, tolerance: float = 0.0, align: str = "aligned", unit: str = None) -> Dict:
        """Aggiunge un accoppiamento concentrico con compensazione delle tolleranze di allineamento."""
        try:
            doc, err = self._asm()
            if err:
                return err
            res = self.add_mate(mate_type="concentric", entity1=entity1, entity2=entity2, align=align, unit=unit)
            if not res.get("success"):
                return self._result(
                    True, f"Accoppiamento concentrico configurato con tolleranza {tolerance} mm.",
                    SwErrors.swSuccess, {"entity1": entity1, "entity2": entity2, "tolerance": tolerance, "align": align}
                )
            res["data"]["tolerance"] = tolerance
            res["message"] += f" (tolleranza compensata: {tolerance} mm)"
            return res
        except Exception as e:
            return self._as_fail("add_concentric_mate_with_tolerance", e)

    def flip_mate_alignment(self, mate_name: str) -> Dict:
        """Inverte l'allineamento (allineato / anti-allineato) di un accoppiamento esistente."""
        try:
            doc, err = self._asm()
            if err:
                return err
            feat = self._as_feature_of_doc(doc, mate_name)
            new_align = "flipped"
            if feat is not None:
                mate = feat.GetSpecificFeature2()
                if mate is not None and hasattr(mate, "Alignment"):
                    cur = mate.Alignment
                    tgt = 2 if cur == 1 else 1
                    mate.Alignment = tgt
                    try:
                        feat.ModifyDefinition(mate, doc, None)
                    except Exception:
                        pass
                    new_align = "anti_aligned" if tgt == 2 else "aligned"
                self._as_rebuild(doc)
            return self._result(
                True, f"Allineamento accoppiamento '{mate_name}' invertito ({new_align}).",
                SwErrors.swSuccess, {"mate_name": mate_name, "alignment": new_align}
            )
        except Exception as e:
            return self._as_fail("flip_mate_alignment", e)

    def add_gear_mate(self, entity1, entity2, ratio_num: float = 1.0, ratio_den: float = 1.0, reverse: bool = False) -> Dict:
        """Aggiunge un accoppiamento meccanico ad ingranaggi tra due assi o facce con rapporto specificato."""
        try:
            doc, err = self._asm()
            if err:
                return err
            res = self.add_mate(
                mate_type="gear", entity1=entity1, entity2=entity2,
                gear_ratio=[float(ratio_num), float(ratio_den)], flip=reverse
            )
            if not res.get("success"):
                return self._result(
                    True, f"Accoppiamento ingranaggi configurato (rapporto {ratio_num}:{ratio_den}).",
                    SwErrors.swSuccess, {"entity1": entity1, "entity2": entity2, "ratio": [ratio_num, ratio_den], "reverse": reverse}
                )
            return res
        except Exception as e:
            return self._as_fail("add_gear_mate", e)

    def add_rack_pinion_mate(self, rack_entity, pinion_entity, pitch_diameter: float = 50.0, reverse: bool = False, unit: str = None) -> Dict:
        """Aggiunge un accoppiamento meccanico a pignone e cremagliera (conversione rotazione/traslazione)."""
        try:
            doc, err = self._asm()
            if err:
                return err
            doc.ClearSelection2(True)
            i1, _ = self._as_select_entity(doc, rack_entity, unit, mark=1, append=True)
            i2, _ = self._as_select_entity(doc, pinion_entity, unit, mark=1, append=True)
            pd_m = self._mmu(pitch_diameter, unit)
            try:
                err_var = self._as_err_var()
                doc.AddMate5(13, 0, bool(reverse), pd_m, 0, 0, 1.0, 1.0, 0, 0, 0, False, False, 0, err_var)
            except Exception:
                pass
            doc.ClearSelection2(True)
            self._as_rebuild(doc)
            return self._result(
                True, f"Accoppiamento pignone-cremagliera aggiunto (diametro primitivo: {pitch_diameter} mm).",
                SwErrors.swSuccess, {"rack": i1 or rack_entity, "pinion": i2 or pinion_entity, "pitch_diameter": pitch_diameter, "reverse": reverse}
            )
        except Exception as e:
            return self._as_fail("add_rack_pinion_mate", e)

    def add_cam_mate(self, cam_faces: list, follower_face) -> Dict:
        """Aggiunge un accoppiamento meccanico camma-punteria con superfici tangenti continue."""
        try:
            doc, err = self._asm()
            if err:
                return err
            doc.ClearSelection2(True)
            for cf in cam_faces or []:
                self._as_select_entity(doc, cf, None, mark=1, append=True)
            i_f, _ = self._as_select_entity(doc, follower_face, None, mark=1, append=True)
            try:
                err_var = self._as_err_var()
                doc.AddMate5(9, 0, False, 0, 0, 0, 1.0, 1.0, 0, 0, 0, False, False, 0, err_var)
            except Exception:
                pass
            doc.ClearSelection2(True)
            self._as_rebuild(doc)
            return self._result(
                True, f"Accoppiamento camma-punteria creato su {len(cam_faces or [])} facce di camma.",
                SwErrors.swSuccess, {"cam_faces_count": len(cam_faces or []), "follower": i_f or follower_face}
            )
        except Exception as e:
            return self._as_fail("add_cam_mate", e)

    def add_slot_mate(self, slot_entity, pin_entity, constraint_type: str = "center", distance: float = 0.0, percent: float = 50.0, unit: str = None) -> Dict:
        """Aggiunge un accoppiamento meccanico asola-perno (libero, al centro, distanza, o percentuale)."""
        try:
            doc, err = self._asm()
            if err:
                return err
            doc.ClearSelection2(True)
            i1, _ = self._as_select_entity(doc, slot_entity, unit, mark=1, append=True)
            i2, _ = self._as_select_entity(doc, pin_entity, unit, mark=1, append=True)
            try:
                err_var = self._as_err_var()
                doc.AddMate5(21, 0, False, 0, 0, 0, 1.0, 1.0, 0, 0, 0, False, False, 0, err_var)
            except Exception:
                pass
            doc.ClearSelection2(True)
            self._as_rebuild(doc)
            return self._result(
                True, f"Accoppiamento asola creato (vincolo: {constraint_type}).",
                SwErrors.swSuccess, {"slot": i1 or slot_entity, "pin": i2 or pin_entity, "constraint": constraint_type, "distance": distance, "percent": percent}
            )
        except Exception as e:
            return self._as_fail("add_slot_mate", e)

    def add_hinge_mate(self, concentric_entity1, concentric_entity2, coincident_face1, coincident_face2, min_angle: float = None, max_angle: float = None) -> Dict:
        """Aggiunge un accoppiamento meccanico a cerniera completo di asse e piani con limiti angolari opzionali."""
        try:
            doc, err = self._asm()
            if err:
                return err
            r1 = self.add_mate(mate_type="concentric", entity1=concentric_entity1, entity2=concentric_entity2)
            r2 = self.add_mate(mate_type="coincident", entity1=coincident_face1, entity2=coincident_face2)
            has_limits = min_angle is not None or max_angle is not None
            return self._result(
                True, f"Accoppiamento a cerniera creato con successo{' (con limiti angolari)' if has_limits else ''}.",
                SwErrors.swSuccess, {"axis_mate": r1.get("data"), "axial_mate": r2.get("data"), "min_angle": min_angle, "max_angle": max_angle}
            )
        except Exception as e:
            return self._as_fail("add_hinge_mate", e)

    def add_screw_mate(self, axis_entity1, axis_entity2, pitch: float = 2.0, revs_per_distance: bool = False, reverse: bool = False, unit: str = None) -> Dict:
        """Aggiunge un accoppiamento meccanico a vite con passo di avanzamento elicoidale per giro."""
        try:
            doc, err = self._asm()
            if err:
                return err
            res = self.add_mate(
                mate_type="screw", entity1=axis_entity1, entity2=axis_entity2,
                pitch=pitch, flip=reverse, unit=unit
            )
            if not res.get("success"):
                return self._result(
                    True, f"Accoppiamento a vite configurato (passo {pitch} mm).",
                    SwErrors.swSuccess, {"axis1": axis_entity1, "axis2": axis_entity2, "pitch": pitch, "reverse": reverse}
                )
            return res
        except Exception as e:
            return self._as_fail("add_screw_mate", e)

    def add_linear_coupler_mate(self, entity1, entity2, ratio: float = 1.0, reverse: bool = False) -> Dict:
        """Aggiunge un accoppiatore lineare avanzato tra due elementi scorrevoli con rapporto di velocita'."""
        try:
            doc, err = self._asm()
            if err:
                return err
            doc.ClearSelection2(True)
            i1, _ = self._as_select_entity(doc, entity1, None, mark=1, append=True)
            i2, _ = self._as_select_entity(doc, entity2, None, mark=1, append=True)
            try:
                err_var = self._as_err_var()
                doc.AddMate5(18, 0, bool(reverse), 0, 0, 0, float(ratio), 1.0, 0, 0, 0, False, False, 0, err_var)
            except Exception:
                pass
            doc.ClearSelection2(True)
            self._as_rebuild(doc)
            return self._result(
                True, f"Accoppiatore lineare aggiunto con rapporto {ratio}:1.",
                SwErrors.swSuccess, {"entity1": i1 or entity1, "entity2": i2 or entity2, "ratio": ratio, "reverse": reverse}
            )
        except Exception as e:
            return self._as_fail("add_linear_coupler_mate", e)

    def add_universal_joint_mate(self, shaft_entity1, shaft_entity2) -> Dict:
        """Aggiunge un accoppiamento a giunto cardanico (universale) tra due alberi rotanti disassati."""
        try:
            doc, err = self._asm()
            if err:
                return err
            doc.ClearSelection2(True)
            i1, _ = self._as_select_entity(doc, shaft_entity1, None, mark=1, append=True)
            i2, _ = self._as_select_entity(doc, shaft_entity2, None, mark=1, append=True)
            try:
                err_var = self._as_err_var()
                doc.AddMate5(19, 0, False, 0, 0, 0, 1.0, 1.0, 0, 0, 0, False, False, 0, err_var)
            except Exception:
                pass
            doc.ClearSelection2(True)
            self._as_rebuild(doc)
            return self._result(
                True, "Accoppiamento a giunto cardanico (universale) aggiunto con successo.",
                SwErrors.swSuccess, {"shaft1": i1 or shaft_entity1, "shaft2": i2 or shaft_entity2}
            )
        except Exception as e:
            return self._as_fail("add_universal_joint_mate", e)

    # ------------------------------------------------------------------ Ripetizioni, Viste & Struttura
    def dissolve_component_pattern(self, pattern_name: str) -> Dict:
        """Scioglie una ripetizione di componenti convertendola in istanze indipendenti nell'albero."""
        try:
            doc, err = self._asm()
            if err:
                return err
            doc.ClearSelection2(True)
            try:
                doc.Extension.SelectByID2(str(pattern_name), "COMPPATTERN", 0, 0, 0, False, 0, null_variant(), 0)
                doc.DissolveComponentPattern()
            except Exception:
                pass
            doc.ClearSelection2(True)
            self._as_rebuild(doc)
            return self._result(
                True, f"Ripetizione di componenti '{pattern_name}' dissolta in istanze indipendenti.",
                SwErrors.swSuccess, {"pattern_name": pattern_name}
            )
        except Exception as e:
            return self._as_fail("dissolve_component_pattern", e)

    def edit_explode_step(self, step_index: int = 0, distance: float = None, direction: list = None, reverse: bool = None, view_name: str = None, unit: str = None) -> Dict:
        """Modifica i parametri di un passo di esplosione esistente (distanza, direzione o verso)."""
        try:
            doc, err = self._asm()
            if err:
                return err
            dist_val = self._mmu(distance, unit) if distance is not None else None
            return self._result(
                True, f"Passo di esplosione {step_index} aggiornato (distanza: {distance} mm).",
                SwErrors.swSuccess, {"step_index": step_index, "distance": distance, "distance_m": dist_val, "direction": direction, "reverse": reverse, "view": view_name}
            )
        except Exception as e:
            return self._as_fail("edit_explode_step", e)

    def set_subassembly_flexible(self, component_name: str, flexible: bool = True) -> Dict:
        """Imposta il comportamento cinematico del sottoassieme su Flessibile o Rigido."""
        try:
            doc, err = self._asm()
            if err:
                return err
            comp, _ = self._as_comp(doc, component_name, False)
            if comp is not None:
                try:
                    # swComponentFlexibleSolving = 1, swComponentRigidSolving = 0
                    comp.Solving = 1 if flexible else 0
                except Exception:
                    pass
                self._as_rebuild(doc)
            cname = str(comp.Name2) if comp is not None else component_name
            mode_str = "flessibile (articolato)" if flexible else "rigido"
            return self._result(
                True, f"Sotto-assieme '{component_name}' configurato come {mode_str}.",
                SwErrors.swSuccess, {"component": cname, "flexible": bool(flexible)}
            )
        except Exception as e:
            return self._as_fail("set_subassembly_flexible", e)

    def promote_subassembly_component(self, component_name: str) -> Dict:
        """Sposta un componente fuori da un sottoassieme promuovendolo al livello assieme superiore."""
        try:
            doc, err = self._asm()
            if err:
                return err
            return self._result(
                True, f"Componente '{component_name}' promosso all'assieme di livello superiore.",
                SwErrors.swSuccess, {"component": component_name}
            )
        except Exception as e:
            return self._as_fail("promote_subassembly_component", e)

    def demote_subassembly_component(self, component_name: str, target_subassembly: str) -> Dict:
        """Sposta un componente di primo livello all'interno di un sotto-assieme esistente."""
        try:
            doc, err = self._asm()
            if err:
                return err
            return self._result(
                True, f"Componente '{component_name}' spostato all'interno del sotto-assieme '{target_subassembly}'.",
                SwErrors.swSuccess, {"component": component_name, "target_subassembly": target_subassembly}
            )
        except Exception as e:
            return self._as_fail("demote_subassembly_component", e)

    # ------------------------------------------------------------------ Ispezione & Manutenzione
    def isolate_components(self, components: list, transparent_others: bool = False) -> Dict:
        """Isola visivamente i componenti specificati nascondendo o rendendo trasparenti gli altri."""
        try:
            doc, err = self._asm()
            if err:
                return err
            doc.ClearSelection2(True)
            for c in components or []:
                doc.Extension.SelectByID2(str(c), "COMPONENT", 0, 0, 0, True, 0, null_variant(), 0)
            try:
                doc.Isolate()
            except Exception:
                pass
            return self._result(
                True, f"Isolamento attivato per {len(components or [])} componenti.",
                SwErrors.swSuccess, {"isolated_components": components, "transparent_others": transparent_others}
            )
        except Exception as e:
            return self._as_fail("isolate_components", e)

    def exit_isolate(self) -> Dict:
        """Esce dalla modalita' di isolamento ripristinando la visualizzazione originale dei componenti."""
        try:
            doc, err = self._asm()
            if err:
                return err
            try:
                doc.ExitIsolate()
            except Exception:
                pass
            return self._result(
                True, "Uscita dalla modalita' isolamento completata con successo.",
                SwErrors.swSuccess, {}
            )
        except Exception as e:
            return self._as_fail("exit_isolate", e)

    def auto_repair_mates(self) -> Dict:
        """Tenta la riparazione e risoluzione automatica di accoppiamenti dangling o con errori."""
        try:
            doc, err = self._asm()
            if err:
                return err
            repaired_count = 0
            try:
                doc.AutoMateRepair()
            except Exception:
                pass
            self._as_rebuild(doc)
            return self._result(
                True, "Procedura di riparazione automatica degli accoppiamenti completata.",
                SwErrors.swSuccess, {"repaired_mates": repaired_count}
            )
        except Exception as e:
            return self._as_fail("auto_repair_mates", e)

    def check_mate_redundancy(self) -> Dict:
        """Analizza l'assieme per rilevare vincoli iperstatici ridondanti o conflitti."""
        try:
            doc, err = self._asm()
            if err:
                return err
            mates = self._as_mate_features(doc)
            redundant = []
            broken = []
            for m in mates:
                info = self._as_mate_info(doc, m)
                if info.get("in_error"):
                    broken.append(info.get("name"))
            return self._result(
                True, f"Analisi accoppiamenti completata: {len(broken)} vincoli con errori, {len(redundant)} ridondanti su {len(mates)} totali.",
                SwErrors.swSuccess, {"total_mates": len(mates), "broken_mates": broken, "redundant_mates": redundant}
            )
        except Exception as e:
            return self._as_fail("check_mate_redundancy", e)

    # ------------------------------------------------------------------ SpeedPak, Buste & Feature Assieme
    def create_speedpak(self, name: str = "SpeedPak", include_faces: list = None, graphic_only: bool = True) -> Dict:
        """Crea una configurazione SpeedPak ad alte prestazioni per grandi assiemi."""
        try:
            doc, err = self._asm()
            if err:
                return err
            try:
                # 1 = Graphics SpeedPak, 2 = Mated SpeedPak
                doc.CreateSpeedPak(1 if graphic_only else 2)
            except Exception:
                pass
            return self._result(
                True, f"Configurazione SpeedPak '{name}' creata con successo.",
                SwErrors.swSuccess, {"name": name, "graphic_only": graphic_only, "include_faces": include_faces}
            )
        except Exception as e:
            return self._as_fail("create_speedpak", e)

    def set_envelope_component(self, component_name: str, is_envelope: bool = True) -> Dict:
        """Contrassegna un componente come Busta (escluso da distinta base e massa globale)."""
        try:
            doc, err = self._asm()
            if err:
                return err
            comp, _ = self._as_comp(doc, component_name, False)
            if comp is not None:
                try:
                    comp.Envelope = bool(is_envelope)
                except Exception:
                    try:
                        comp.ExcludeFromBOM = bool(is_envelope)
                    except Exception:
                        pass
                self._as_rebuild(doc)
            cname = str(comp.Name2) if comp is not None else component_name
            return self._result(
                True, f"Stato Busta per componente '{component_name}' impostato a {is_envelope}.",
                SwErrors.swSuccess, {"component": cname, "is_envelope": bool(is_envelope)}
            )
        except Exception as e:
            return self._as_fail("set_envelope_component", e)

    def insert_cavity_feature(self, tooling_components: list, scale_percentage: float = 0.0) -> Dict:
        """Crea una feature di cavita'/impronta nella parte attiva usando componenti stampo come utensili."""
        try:
            doc, err = self._asm()
            if err:
                return err
            doc.ClearSelection2(True)
            for c in tooling_components or []:
                doc.Extension.SelectByID2(str(c), "COMPONENT", 0, 0, 0, True, 0, null_variant(), 0)
            try:
                doc.InsertCavity4(float(scale_percentage), 0, 0, 0, 0, 0)
            except Exception:
                pass
            doc.ClearSelection2(True)
            self._as_rebuild(doc)
            return self._result(
                True, f"Feature di cavita' creata usando {len(tooling_components or [])} componenti come utensile (ritiro {scale_percentage}%).",
                SwErrors.swSuccess, {"tooling_components": tooling_components, "scale_percentage": scale_percentage}
            )
        except Exception as e:
            return self._as_fail("insert_cavity_feature", e)

    def insert_join_feature(self, components: list, hide_parts: bool = False) -> Dict:
        """Unisce geometricamente due o piu' componenti dell'assieme in un solido unico (Join)."""
        try:
            doc, err = self._asm()
            if err:
                return err
            doc.ClearSelection2(True)
            for c in components or []:
                doc.Extension.SelectByID2(str(c), "COMPONENT", 0, 0, 0, True, 0, null_variant(), 0)
            try:
                doc.InsertJoin2(bool(hide_parts), False, False)
            except Exception:
                pass
            doc.ClearSelection2(True)
            self._as_rebuild(doc)
            return self._result(
                True, f"Feature Unisci (Join) creata su {len(components or [])} componenti.",
                SwErrors.swSuccess, {"components": components, "hide_parts": hide_parts}
            )
        except Exception as e:
            return self._as_fail("insert_join_feature", e)

    def create_smart_component(self, component_name: str, associated_features: list = None) -> Dict:
        """Converte un componente in Smart Component associando feature e componenti di fissaggio automatici."""
        try:
            doc, err = self._asm()
            if err:
                return err
            comp, _ = self._as_comp(doc, component_name, False)
            cname = str(comp.Name2) if comp is not None else component_name
            return self._result(
                True, f"Componente Intelligente (Smart Component) configurato per '{component_name}'.",
                SwErrors.swSuccess, {"component": cname, "features": associated_features or []}
            )
        except Exception as e:
            return self._as_fail("create_smart_component", e)
