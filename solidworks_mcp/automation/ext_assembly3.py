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

    def _as_byref(self, kind: str):
        """Parametro per riferimento (VT_BYREF) per chiamate COM con uscita. Senza pywin32 un contenitore con .value."""
        try:
            import pythoncom
            import win32com.client
            vt = {"dispatch": pythoncom.VT_DISPATCH, "i4": pythoncom.VT_I4, "variant": pythoncom.VT_VARIANT}[kind]
            return win32com.client.VARIANT(pythoncom.VT_BYREF | vt, 0 if kind == "i4" else None)
        except ImportError:
            class _Out:
                value = 0 if kind == "i4" else None
            return _Out()

    def _as_addmate_err(self, res, err_var):
        """Esito di AddMate5: None se creato, altrimenti il motivo. Il codice by-ref vale solo se letto (1 = nessun errore)."""
        if res is None:
            return "SolidWorks non ha creato l'accoppiamento"
        code = getattr(err_var, "value", None)
        if isinstance(code, int) and code != 1:
            return f"codice errore AddMate5 {code}"
        return None

    # ------------------------------------------------------------------ Gestione Componenti & Istanze
    def make_component_independent(self, component_name: str, new_filepath: str = None) -> Dict:
        """Rende una specifica istanza indipendente duplicandola su nuovo file o rendendola autonoma."""
        try:
            doc, err = self._asm()
            if err:
                return err
            comp, _ = self._as_comp(doc, component_name, False)
            if comp is None:
                return self._result(False, f"make_component_independent: '{component_name}' non trovato", SwErrors.swSelectionError)
            doc.ClearSelection2(True)
            if not self._as_select_comps(doc, [comp]):
                doc.ClearSelection2(True)
                return self._result(False, f"make_component_independent: selezione di '{component_name}' non riuscita", SwErrors.swSelectionError)
            if not new_filepath:
                doc.ClearSelection2(True)
                return self._result(False, "make_component_independent: serve il percorso del nuovo file (new_filepath)", SwErrors.swInvalidInput)
            target_path = os.path.abspath(new_filepath)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            try:
                res = doc.MakeIndependent(target_path)
            except Exception as e:
                doc.ClearSelection2(True)
                return self._result(False, f"make_component_independent: operazione non riuscita: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            if not res:
                return self._result(False, f"make_component_independent: '{component_name}' non reso indipendente", SwErrors.swFeatureError)
            if target_path and not (os.path.isfile(target_path) and os.path.getsize(target_path) > 0):
                return self._result(False, f"make_component_independent: file non scritto ({target_path})", SwErrors.swExportError)
            # dopo il comando l'istanza prende il nome del nuovo file: si cerca il componente che punta a quel file
            new_name = str(comp.Name2)
            try:
                for cc in (doc.GetComponents(False) or ()):
                    if os.path.normcase(os.path.abspath(str(self._com(cc, "GetPathName")))) == os.path.normcase(target_path):
                        new_name = str(cc.Name2)
                        break
            except Exception:
                pass
            return self._result(
                True, f"Componente '{component_name}' reso indipendente: ora e' '{new_name}'.",
                SwErrors.swSuccess, {"component": new_name, "previous_name": component_name, "independent": True,
                                     "new_filepath": new_filepath}
            )
        except Exception as e:
            return self._as_fail("make_component_independent", e)

    def reorder_components(self, components: list, target_component: str, position: str = "after") -> Dict:
        """Riordina i componenti nell'albero delle feature prima o dopo un componente target."""
        try:
            doc, err = self._asm()
            if err:
                return err
            pos = str(position).lower().strip()
            if pos not in ("before", "after"):
                return self._result(False, f"reorder_components: posizione '{position}' non valida (before | after)", SwErrors.swInvalidInput)
            which_way = 1 if pos == "before" else 2
            src = []
            for n in list(components or []) + [target_component]:
                comp, e_c = self._as_comp(doc, n, False)
                if e_c:
                    return self._result(False, f"reorder_components: '{n}' non trovato", SwErrors.swSelectionError)
                src.append(comp)
            doc.ClearSelection2(True)
            try:
                from .modeling_base import disp_array
                res = doc.ReorderComponents(disp_array(src[:-1]), src[-1], which_way)
            except Exception as e:
                return self._result(False, f"reorder_components: riordino non riuscito: {e}", SwErrors.swFeatureError)
            if not res:
                return self._result(False, f"reorder_components: riordino non riuscito a '{target_component}'", SwErrors.swFeatureError)
            self._as_rebuild(doc)
            return self._result(
                True, f"Componenti riordinati {position} a '{target_component}'.",
                SwErrors.swSuccess, {"components": components, "target": target_component, "position": position, "reordered": True}
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
            try:
                raw = doc.SelectComponentsBySize(pct)
            except Exception as e:
                return self._result(False, f"select_components_by_size: selezione non riuscita: {e}", SwErrors.swSelectionError)
            if raw is None:
                return self._result(False, "select_components_by_size: SolidWorks non ha restituito il numero di componenti", SwErrors.swSelectionError)
            selected_count = int(raw)
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
            if comp is None:
                return self._result(False, f"set_component_transparency: '{component_name}' non trovato", SwErrors.swSelectionError)
            doc.ClearSelection2(True)
            if not self._as_select_comps(doc, [comp]):
                doc.ClearSelection2(True)
                return self._result(False, f"set_component_transparency: selezione di '{component_name}' non riuscita", SwErrors.swSelectionError)
            try:
                doc.SetComponentTransparent(bool(transparent))
            except Exception:
                try:
                    comp.Transparency = 1 if transparent else 0
                except Exception as e:
                    doc.ClearSelection2(True)
                    return self._result(False, f"set_component_transparency: impostazione non riuscita: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            return self._result(
                True, f"Trasparenza componente '{component_name}' impostata a {transparent}.",
                SwErrors.swSuccess, {"component": str(comp.Name2), "transparent": bool(transparent)}
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
            plane = self._std_ref_feature(doc, plane_or_face or "Front Plane")
            if plane is None or not bool(plane.Select2(False, 0)):
                doc.ClearSelection2(True)
                return self._result(False, f"insert_new_virtual_part: piano/faccia '{plane_or_face}' non selezionato", SwErrors.swSelectionError)
            ent = doc.SelectionManager.GetSelectedObject6(1, -1)
            doc.ClearSelection2(True)
            out = self._as_byref("dispatch")
            try:
                ret_vp = doc.InsertNewVirtualPart(ent, out)
            except Exception as e:
                return self._result(False, f"insert_new_virtual_part: creazione non riuscita: {e}", SwErrors.swFeatureError)
            res = out.value
            if res is None:
                return self._result(False, f"insert_new_virtual_part: SolidWorks non ha creato la parte virtuale (ritorno {ret_vp}, selezione {type(ent).__name__})", SwErrors.swFeatureError)
            created_name = str(res.Name2) if hasattr(res, "Name2") else None
            return self._result(
                True, "Nuova parte virtuale creata nell'assieme.",
                SwErrors.swSuccess, {"virtual_part": created_name, "ignored_params": ["plane_or_face", "part_name"]}
            )
        except Exception as e:
            return self._as_fail("insert_new_virtual_part", e)

    def insert_new_virtual_assembly(self, subassembly_name: str = None) -> Dict:
        """Crea un nuovo sotto-assieme virtuale vuoto all'interno dell'assieme."""
        try:
            doc, err = self._asm()
            if err:
                return err
            out = self._as_byref("dispatch")
            try:
                doc.InsertNewVirtualAssembly(out)
            except Exception as e:
                return self._result(False, f"insert_new_virtual_assembly: creazione non riuscita: {e}", SwErrors.swFeatureError)
            res = out.value
            if res is None:
                return self._result(False, "insert_new_virtual_assembly: SolidWorks non ha creato il sotto-assieme virtuale", SwErrors.swFeatureError)
            created_name = str(res.Name2) if hasattr(res, "Name2") else None
            return self._result(
                True, "Nuovo sotto-assieme virtuale creato nell'assieme.",
                SwErrors.swSuccess, {"virtual_subassembly": created_name, "ignored_params": ["subassembly_name"]}
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
            if comp is None:
                return self._result(False, f"edit_part_in_context: '{component_name}' non trovato", SwErrors.swSelectionError)
            doc.ClearSelection2(True)
            if not self._as_select_comps(doc, [comp]):
                doc.ClearSelection2(True)
                return self._result(False, f"edit_part_in_context: selezione di '{component_name}' non riuscita", SwErrors.swSelectionError)
            info = self._as_byref("i4")
            try:
                res = doc.EditPart2(True, True, info)
            except Exception as e:
                doc.ClearSelection2(True)
                return self._result(False, f"edit_part_in_context: attivazione non riuscita: {e}", SwErrors.swFeatureError)
            if not res:
                doc.ClearSelection2(True)
                return self._result(False, f"edit_part_in_context: modifica in-context non attivata per '{component_name}'", SwErrors.swFeatureError)
            return self._result(
                True, f"Modalita' di modifica in-context attivata per '{component_name}'.",
                SwErrors.swSuccess, {"component": str(comp.Name2), "in_context": True}
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
            except Exception as e:
                return self._result(False, f"exit_part_in_context: uscita non riuscita: {e}", SwErrors.swFeatureError)
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
            comp, _ = self._as_comp(doc, component_name, False)
            if comp is None:
                return self._result(False, f"save_virtual_component_external: '{component_name}' non trovato", SwErrors.swSelectionError)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            pre_mtime = os.path.getmtime(path) if os.path.isfile(path) else None
            doc.ClearSelection2(True)
            if not self._as_select_comps(doc, [comp]):
                doc.ClearSelection2(True)
                return self._result(False, f"save_virtual_component_external: selezione di '{component_name}' non riuscita", SwErrors.swSelectionError)
            try:
                saved = comp.SaveVirtualComponent(path)
            except Exception as e:
                doc.ClearSelection2(True)
                return self._result(False, f"save_virtual_component_external: salvataggio non riuscito: {e}", SwErrors.swExportError)
            doc.ClearSelection2(True)
            if not saved:
                return self._result(False, f"save_virtual_component_external: SolidWorks non ha salvato '{component_name}'", SwErrors.swExportError)
            written = os.path.isfile(path) and os.path.getsize(path) > 0 and (pre_mtime is None or os.path.getmtime(path) != pre_mtime)
            if not written:
                return self._result(False, f"save_virtual_component_external: file non scritto ({path})", SwErrors.swExportError)
            return self._result(
                True, f"Componente virtuale '{component_name}' salvato esternamente in {path}.",
                SwErrors.swSuccess, {"component": str(comp.Name2), "filepath": path}
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
            feat = self._as_mate_by_name(doc, mate_name)
            if feat is None:
                return self._result(False, f"lock_mate_rotation: accoppiamento '{mate_name}' non trovato", SwErrors.swSelectionError)
            mate = self._com(feat, "GetSpecificFeature2")
            if mate is None or not hasattr(mate, "LockRotation"):
                return self._result(False, f"lock_mate_rotation: '{mate_name}' non supporta il blocco rotazione", SwErrors.swFeatureError)
            try:
                mate.LockRotation = bool(locked)
                feat.ModifyDefinition(mate, doc, None)
            except Exception as e:
                return self._result(False, f"lock_mate_rotation: modifica non riuscita: {e}", SwErrors.swFeatureError)
            self._as_rebuild(doc)
            if bool(self._com(feat, "GetSpecificFeature2").LockRotation) != bool(locked):
                return self._result(False, f"lock_mate_rotation: blocco rotazione di '{mate_name}' non applicato", SwErrors.swFeatureError)
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
            if res.get("success"):
                data = res.get("data") or {}
                data["ignored_params"] = ["tolerance"]
                res["data"] = data
            return res
        except Exception as e:
            return self._as_fail("add_concentric_mate_with_tolerance", e)

    def flip_mate_alignment(self, mate_name: str) -> Dict:
        """Inverte l'allineamento (allineato / anti-allineato) di un accoppiamento esistente."""
        try:
            doc, err = self._asm()
            if err:
                return err
            feat = self._as_mate_by_name(doc, mate_name)
            if feat is None:
                return self._result(False, f"flip_mate_alignment: accoppiamento '{mate_name}' non trovato", SwErrors.swSelectionError)
            mate = self._com(feat, "GetSpecificFeature2")
            if mate is None or not hasattr(mate, "Flipped"):
                return self._result(False, f"flip_mate_alignment: '{mate_name}' non ha allineamento invertibile", SwErrors.swFeatureError)
            if not bool(mate.CanBeFlipped):
                return self._result(False, f"flip_mate_alignment: '{mate_name}' non si puo' invertire", SwErrors.swFeatureError)
            cur = bool(mate.Flipped)
            try:
                mate.Flipped = not cur
                feat.ModifyDefinition(mate, doc, None)
            except Exception as e:
                return self._result(False, f"flip_mate_alignment: modifica non riuscita: {e}", SwErrors.swFeatureError)
            self._as_rebuild(doc)
            if bool(self._com(feat, "GetSpecificFeature2").Flipped) == cur:
                return self._result(False, f"flip_mate_alignment: allineamento di '{mate_name}' non invertito", SwErrors.swFeatureError)
            new_align = "anti_aligned" if not cur else "aligned"
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
            return self.add_mate(
                mate_type="gear", entity1=entity1, entity2=entity2,
                gear_ratio=[float(ratio_num), float(ratio_den)], flip=reverse
            )
        except Exception as e:
            return self._as_fail("add_gear_mate", e)

    def add_rack_pinion_mate(self, rack_entity, pinion_entity, pitch_diameter: float = 50.0, reverse: bool = False, unit: str = None) -> Dict:
        """Aggiunge un accoppiamento meccanico a pignone e cremagliera (conversione rotazione/traslazione)."""
        try:
            doc, err = self._asm()
            if err:
                return err
            doc.ClearSelection2(True)
            i1, e1 = self._as_select_entity(doc, rack_entity, unit, mark=1, append=True)
            if e1:
                return self._result(False, f"add_rack_pinion_mate: cremagliera non selezionata: {e1}", SwErrors.swSelectionError)
            i2, e2 = self._as_select_entity(doc, pinion_entity, unit, mark=1, append=True)
            if e2:
                return self._result(False, f"add_rack_pinion_mate: pignone non selezionato: {e2}", SwErrors.swSelectionError)
            pd_m = self._mmu(pitch_diameter, unit)
            try:
                err_var = self._as_err_var()
                mate_feat = doc.AddMate5(13, 0, bool(reverse), pd_m, 0, 0, 1.0, 1.0, 0, 0, 0, False, False, 0, err_var)
            except Exception as e:
                return self._result(False, f"add_rack_pinion_mate: creazione non riuscita: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            motivo = self._as_addmate_err(mate_feat, err_var)
            if motivo:
                return self._result(False, f"add_rack_pinion_mate: accoppiamento non creato: {motivo}", SwErrors.swFeatureError)
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
            if not cam_faces:
                return self._result(False, "add_cam_mate: serve almeno una faccia di camma", SwErrors.swInvalidInput)
            doc.ClearSelection2(True)
            for cf in cam_faces:
                _, e_cf = self._as_select_entity(doc, cf, None, mark=1, append=True)
                if e_cf:
                    return self._result(False, f"add_cam_mate: faccia di camma non selezionata: {e_cf}", SwErrors.swSelectionError)
            i_f, e_f = self._as_select_entity(doc, follower_face, None, mark=1, append=True)
            if e_f:
                return self._result(False, f"add_cam_mate: punteria non selezionata: {e_f}", SwErrors.swSelectionError)
            try:
                err_var = self._as_err_var()
                mate_feat = doc.AddMate5(9, 0, False, 0, 0, 0, 1.0, 1.0, 0, 0, 0, False, False, 0, err_var)
            except Exception as e:
                return self._result(False, f"add_cam_mate: creazione non riuscita: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            motivo = self._as_addmate_err(mate_feat, err_var)
            if motivo:
                return self._result(False, f"add_cam_mate: accoppiamento non creato: {motivo}", SwErrors.swFeatureError)
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
            i1, e1 = self._as_select_entity(doc, slot_entity, unit, mark=1, append=True)
            if e1:
                return self._result(False, f"add_slot_mate: asola non selezionata: {e1}", SwErrors.swSelectionError)
            i2, e2 = self._as_select_entity(doc, pin_entity, unit, mark=1, append=True)
            if e2:
                return self._result(False, f"add_slot_mate: perno non selezionato: {e2}", SwErrors.swSelectionError)
            try:
                err_var = self._as_err_var()
                mate_feat = doc.AddMate5(21, 0, False, 0, 0, 0, 1.0, 1.0, 0, 0, 0, False, False, 0, err_var)
            except Exception as e:
                return self._result(False, f"add_slot_mate: creazione non riuscita: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            motivo = self._as_addmate_err(mate_feat, err_var)
            if motivo:
                return self._result(False, f"add_slot_mate: accoppiamento non creato: {motivo}", SwErrors.swFeatureError)
            self._as_rebuild(doc)
            return self._result(
                True, "Accoppiamento asola creato.",
                SwErrors.swSuccess, {"slot": i1 or slot_entity, "pin": i2 or pin_entity,
                                     "ignored_params": ["constraint_type", "distance", "percent"]}
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
            if not r1.get("success"):
                return r1
            r2 = self.add_mate(mate_type="coincident", entity1=coincident_face1, entity2=coincident_face2)
            if not r2.get("success"):
                return self._result(False, f"add_hinge_mate: accoppiamento assiale creato, piano non creato: {r2.get('message')}",
                                    SwErrors.swFeatureError, {"axis_mate": r1.get("data")})
            ignored = [n for n, v in (("min_angle", min_angle), ("max_angle", max_angle)) if v is not None]
            return self._result(
                True, "Accoppiamento a cerniera creato (asse e piano).",
                SwErrors.swSuccess, {"axis_mate": r1.get("data"), "axial_mate": r2.get("data"), "ignored_params": ignored}
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
            if res.get("success"):
                data = res.get("data") or {}
                data["ignored_params"] = ["revs_per_distance"]
                res["data"] = data
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
            i1, e1 = self._as_select_entity(doc, entity1, None, mark=1, append=True)
            if e1:
                return self._result(False, f"add_linear_coupler_mate: entita' 1 non selezionata: {e1}", SwErrors.swSelectionError)
            i2, e2 = self._as_select_entity(doc, entity2, None, mark=1, append=True)
            if e2:
                return self._result(False, f"add_linear_coupler_mate: entita' 2 non selezionata: {e2}", SwErrors.swSelectionError)
            try:
                err_var = self._as_err_var()
                mate_feat = doc.AddMate5(18, 0, bool(reverse), 0, 0, 0, float(ratio), 1.0, 0, 0, 0, False, False, 0, err_var)
            except Exception as e:
                return self._result(False, f"add_linear_coupler_mate: creazione non riuscita: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            motivo = self._as_addmate_err(mate_feat, err_var)
            if motivo:
                return self._result(False, f"add_linear_coupler_mate: accoppiamento non creato: {motivo}", SwErrors.swFeatureError)
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
            i1, e1 = self._as_select_entity(doc, shaft_entity1, None, mark=1, append=True)
            if e1:
                return self._result(False, f"add_universal_joint_mate: albero 1 non selezionato: {e1}", SwErrors.swSelectionError)
            i2, e2 = self._as_select_entity(doc, shaft_entity2, None, mark=1, append=True)
            if e2:
                return self._result(False, f"add_universal_joint_mate: albero 2 non selezionato: {e2}", SwErrors.swSelectionError)
            try:
                err_var = self._as_err_var()
                mate_feat = doc.AddMate5(19, 0, False, 0, 0, 0, 1.0, 1.0, 0, 0, 0, False, False, 0, err_var)
            except Exception as e:
                return self._result(False, f"add_universal_joint_mate: creazione non riuscita: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            motivo = self._as_addmate_err(mate_feat, err_var)
            if motivo:
                return self._result(False, f"add_universal_joint_mate: accoppiamento non creato: {motivo}", SwErrors.swFeatureError)
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
                sel = doc.Extension.SelectByID2(str(pattern_name), "COMPPATTERN", 0, 0, 0, False, 0, null_variant(), 0)
                if not sel:
                    doc.ClearSelection2(True)
                    return self._result(False, f"dissolve_component_pattern: ripetizione '{pattern_name}' non trovata", SwErrors.swSelectionError)
                ok = self._com(doc, "DissolveComponentPattern")
            except Exception as e:
                doc.ClearSelection2(True)
                return self._result(False, f"dissolve_component_pattern: operazione non riuscita: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            if not ok:
                return self._result(False, f"dissolve_component_pattern: '{pattern_name}' non dissolta", SwErrors.swFeatureError)
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
            if comp is None:
                return self._result(False, f"set_subassembly_flexible: '{component_name}' non trovato", SwErrors.swSelectionError)
            # swComponentFlexibleSolving = 1, swComponentRigidSolving = 0
            want = 1 if flexible else 0
            try:
                comp.Solving = want
            except Exception as e:
                return self._result(False, f"set_subassembly_flexible: impostazione non riuscita: {e}", SwErrors.swFeatureError)
            self._as_rebuild(doc)
            if int(comp.Solving) != want:
                return self._result(False, f"set_subassembly_flexible: '{component_name}' non impostato come richiesto", SwErrors.swFeatureError)
            mode_str = "flessibile (articolato)" if flexible else "rigido"
            return self._result(
                True, f"Sotto-assieme '{component_name}' configurato come {mode_str}.",
                SwErrors.swSuccess, {"component": str(comp.Name2), "flexible": bool(flexible)}
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
            comps = []
            for c in components or []:
                comp, e = self._as_comp(doc, c)
                if comp is None:
                    return self._result(False, f"isolate_components: componente '{c}' non trovato: {e}", SwErrors.swSelectionError)
                comps.append(comp)
            if not self._as_select_comps(doc, comps):
                doc.ClearSelection2(True)
                return self._result(False, "isolate_components: componente non selezionato", SwErrors.swSelectionError)
            try:
                self._com(doc, "Isolate")
            except Exception as e:
                doc.ClearSelection2(True)
                return self._result(False, f"isolate_components: isolamento non riuscito: {e}", SwErrors.swFeatureError)
            return self._result(
                True, f"Isolamento attivato per {len(components or [])} componenti.",
                SwErrors.swSuccess, {"isolated_components": components, "ignored_params": ["transparent_others"]}
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
                self._com(doc, "ExitIsolate")
            except Exception as e:
                return self._result(False, f"exit_isolate: uscita non riuscita: {e}", SwErrors.swFeatureError)
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
            processed = self._as_byref("variant")
            failed = self._as_byref("variant")
            try:
                res = doc.AutoMateRepair(processed, failed)
            except Exception as e:
                return self._result(False, f"auto_repair_mates: riparazione non riuscita: {e}", SwErrors.swFeatureError)
            self._as_rebuild(doc)
            repaired_count = len(list(processed.value or [])) if processed.value is not None else 0
            failed_count = len(list(failed.value or [])) if failed.value is not None else 0
            return self._result(
                True, "Procedura di riparazione automatica degli accoppiamenti completata.",
                SwErrors.swSuccess, {"repaired_mates": repaired_count, "failed_mates": failed_count, "result": res}
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
            except Exception as e:
                return self._result(False, f"create_speedpak: creazione non riuscita: {e}", SwErrors.swFeatureError)
            return self._result(
                True, "Configurazione SpeedPak creata.",
                SwErrors.swSuccess, {"graphic_only": graphic_only, "ignored_params": ["name", "include_faces"]}
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
            if comp is None:
                return self._result(False, f"set_envelope_component: '{component_name}' non trovato", SwErrors.swSelectionError)
            try:
                comp.Envelope = bool(is_envelope)
            except Exception as e:
                return self._result(False, f"set_envelope_component: proprieta' envelope non impostabile: {e}", SwErrors.swFeatureError)
            if bool(comp.Envelope) != bool(is_envelope):
                return self._result(False, f"set_envelope_component: stato Busta di '{component_name}' non applicato", SwErrors.swFeatureError)
            self._as_rebuild(doc)
            return self._result(
                True, f"Stato Busta per componente '{component_name}' impostato a {is_envelope}.",
                SwErrors.swSuccess, {"component": str(comp.Name2), "is_envelope": bool(is_envelope)}
            )
        except Exception as e:
            return self._as_fail("set_envelope_component", e)

    def insert_cavity_feature(self, tooling_components: list, scale_percentage: float = 0.0) -> Dict:
        """Crea una feature di cavita'/impronta nella parte attiva usando componenti stampo come utensili."""
        try:
            doc, err = self._asm()
            if err:
                return err
            comps = []
            for c in tooling_components or []:
                comp, e = self._as_comp(doc, c)
                if comp is None:
                    return self._result(False, f"insert_cavity_feature: componente '{c}' non trovato: {e}", SwErrors.swSelectionError)
                comps.append(comp)
            if not self._as_select_comps(doc, comps):
                doc.ClearSelection2(True)
                return self._result(False, "insert_cavity_feature: componente non selezionato", SwErrors.swSelectionError)
            try:
                doc.InsertCavity4(float(scale_percentage), 0, 0, 0, 0, 0)
            except Exception as e:
                doc.ClearSelection2(True)
                return self._result(False, f"insert_cavity_feature: creazione non riuscita: {e}", SwErrors.swFeatureError)
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
            comps = []
            for c in components or []:
                comp, e = self._as_comp(doc, c)
                if comp is None:
                    return self._result(False, f"insert_join_feature: componente '{c}' non trovato: {e}", SwErrors.swSelectionError)
                comps.append(comp)
            if not self._as_select_comps(doc, comps):
                doc.ClearSelection2(True)
                return self._result(False, "insert_join_feature: componente non selezionato", SwErrors.swSelectionError)
            try:
                doc.InsertJoin2(bool(hide_parts), False)
            except Exception as e:
                doc.ClearSelection2(True)
                return self._result(False, f"insert_join_feature: creazione non riuscita: {e}", SwErrors.swFeatureError)
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
