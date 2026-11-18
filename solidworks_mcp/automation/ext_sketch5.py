"""
Lotto SCHIZZO 5: implementazione degli strumenti avanzati di micro-controllo spline,
relazioni, sostituzione ed export.
"""

import math
import logging
import traceback

import pythoncom
from typing import Dict, Any, List

from ..constants import SwErrors

logger = logging.getLogger("solidworks_mcp.automation.sketch5")

# Constraint enum mapping per get_allowed_relations
CONSTRAINT_NAMES = {
    1: "Distance", 2: "Angle", 3: "Radius", 4: "Horizontal", 5: "Vertical",
    6: "Tangent", 7: "Parallel", 8: "Perpendicular", 9: "Coincident",
    10: "Concentric", 11: "Symmetric", 12: "AtMiddle", 13: "AtIntersect",
    14: "SameLength", 15: "Diameter", 17: "Fixed", 27: "Colinear",
    28: "Coradial", 40: "AtPierce", 42: "MergePoints", 45: "Normal",
    61: "EqualCurvature", 62: "EqualTangent"
}


class Sketch5Operations:
    """Operazioni esperte e di micro-controllo per schizzi 2D e 3D."""

    def _s5_sd(self, doc, mark: int = 0):
        try:
            return self._sd(doc, mark)
        except Exception:
            return None

    def _s5_segs(self, doc) -> List[Any]:
        try:
            sk = doc.SketchManager.ActiveSketch
            if sk is None:
                return []
            segs = self._com(sk, "GetSketchSegments")
            return list(segs) if segs else []
        except Exception:
            return []

    def _find_spline(self, doc, spline_id: str = None):
        segs = self._s5_segs(doc)
        if spline_id:
            for s in segs:
                if self._safe_seg_id(s) == spline_id:
                    return s
            return None
        for s in reversed(segs):
            try:
                if int(s.GetType) == 3:  # swSketchSPLINE
                    return s
            except Exception:
                pass
        return None

    # ====================================================================
    # 1. Micro-Controllo e Manipolazione Spline
    # ====================================================================
    def relax_sketch_spline(self, spline_entity: str = None) -> Dict:
        """Rilassa la spline distribuendo uniformemente la tensione e la curvatura."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            sp = self._find_spline(doc, spline_entity)
            if sp is None:
                return self._result(False, f"Spline '{spline_entity}' non trovata." if spline_entity else "Nessuna spline trovata nello schizzo.", SwErrors.swSelectionError)

            try:
                sp.RelaxSpline()
            except Exception as ex:
                return self._result(False, f"relax_sketch_spline: rilassamento non riuscito: {ex}", SwErrors.swSketchError)

            spline_name = self._safe_seg_id(sp)
            msg = f"Spline '{spline_name}' rilassata con successo."
            return self._result(True, msg, SwErrors.swSuccess, {
                "spline_entity": spline_name,
                "relaxed": True
            })
        except Exception as e:
            logger.error(f"relax_sketch_spline: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def simplify_sketch_spline(self, tolerance: float = 0.1, spline_entity: str = None, unit: str = None) -> Dict:
        """Semplifica la spline riducendo il numero di punti entro la tolleranza geometrica."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            sp = self._find_spline(doc, spline_entity)
            if sp is None:
                return self._result(False, f"Spline '{spline_entity}' non trovata." if spline_entity else "Nessuna spline trovata nello schizzo.", SwErrors.swSelectionError)

            tol_m = self._mmu(tolerance or 0.1, unit)
            try:
                sp.Simplify(float(tol_m))
            except Exception as ex:
                return self._result(False, f"simplify_sketch_spline: semplificazione non riuscita: {ex}", SwErrors.swSketchError)

            spline_name = self._safe_seg_id(sp)
            u = unit or "mm"
            msg = f"Spline '{spline_name}' semplificata entro tolleranza {tolerance} {u}."
            return self._result(True, msg, SwErrors.swSuccess, {
                "spline_entity": spline_name,
                "tolerance": tolerance,
                "simplified": True
            })
        except Exception as e:
            logger.error(f"simplify_sketch_spline: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def insert_spline_point(self, x: float, y: float, z: float = 0.0,
                            spline_entity: str = None, unit: str = None) -> Dict:
        """Inserisce un nuovo punto di passaggio/controllo lungo una spline esistente."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            sp = self._find_spline(doc, spline_entity)
            if sp is None:
                return self._result(False, f"Spline '{spline_entity}' non trovata." if spline_entity else "Nessuna spline trovata nello schizzo.", SwErrors.swSelectionError)

            xm = self._mmu(x, unit)
            ym = self._mmu(y, unit)
            zm = self._mmu(z or 0.0, unit)

            try:
                ok = bool(sp.InsertPoint(float(xm), float(ym), float(zm)))
            except Exception as ex:
                return self._result(False, f"insert_spline_point: inserimento punto non riuscito: {ex}", SwErrors.swSketchError)
            if not ok:
                return self._result(False, "insert_spline_point: SolidWorks non ha inserito il punto nella spline.", SwErrors.swSketchError)

            spline_name = self._safe_seg_id(sp)
            msg = f"Punto inserito nella spline '{spline_name}' alle coordinate ({x}, {y}, {z})."
            return self._result(True, msg, SwErrors.swSuccess, {
                "spline_entity": spline_name,
                "point": [x, y, z],
                "inserted": True
            })
        except Exception as e:
            logger.error(f"insert_spline_point: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)


    def edit_spline_handle(self, point_index: int = 0, magnitude: float = None,
                           radial_angle_deg: float = None, polar_angle_deg: float = None,
                           curvature: float = None, spline_entity: str = None) -> Dict:
        """Modifica manuale del manubrio di tangenza/curvatura di un punto della spline."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            sp = self._find_spline(doc, spline_entity)
            if sp is None:
                return self._result(False, f"Spline '{spline_entity}' non trovata." if spline_entity else "Nessuna spline trovata nello schizzo.", SwErrors.swSelectionError)

            handles = ()
            try:
                handles = self._com(sp, "GetSplineHandles") or ()
            except Exception:
                pass

            idx = max(0, int(point_index or 0))
            if idx >= len(handles):
                return self._result(False, f"edit_spline_handle: manubrio #{point_index} non trovato (manubri della spline: {len(handles)}).", SwErrors.swInvalidInput)
            h = handles[idx]
            try:
                h.TangentDriving = True
                if magnitude is not None:
                    h._oleobj_.Invoke(h._oleobj_.GetIDsOfNames("TangentMagnitude"), 0, pythoncom.DISPATCH_PROPERTYPUT, 0, 1, float(magnitude))
                if radial_angle_deg is not None:
                    h.TangentRadialDirection = float(math.radians(radial_angle_deg))
                if polar_angle_deg is not None:
                    h.TangentPolarDirection = float(math.radians(polar_angle_deg))
                if curvature is not None:
                    h.CurvatureControlled = True
                    h.Curvature = float(curvature)
            except Exception as ex:
                return self._result(False, f"edit_spline_handle: modifica manubrio non riuscita: {ex}", SwErrors.swSketchError)

            spline_name = self._safe_seg_id(sp)
            msg = f"Manubrio della spline '{spline_name}' al punto #{point_index} aggiornato."
            return self._result(True, msg, SwErrors.swSuccess, {
                "spline_entity": spline_name,
                "handle_index": point_index,
                "magnitude": magnitude,
                "radial_angle_deg": radial_angle_deg,
                "polar_angle_deg": polar_angle_deg,
                "curvature": curvature,
                "edited": True
            })
        except Exception as e:
            logger.error(f"edit_spline_handle: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    # ====================================================================
    # 2. Sostituzione Geometria e Cinghia 2D
    # ====================================================================
    def replace_sketch_entity(self, source_entity: str, target_entity: str,
                               make_construction: bool = True, make_contour: bool = False) -> Dict:
        """Sostituisce un'entità di schizzo esistente con una nuova geometria mantenendo i vincoli a valle."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            if not source_entity or not target_entity:
                return self._result(False, "source_entity e target_entity obbligatori", SwErrors.swInvalidInput)

            sm = doc.SketchManager
            doc.ClearSelection2(True)
            sel_src = bool(doc.Extension.SelectByID2(source_entity, "SKETCHSEGMENT", 0, 0, 0, False, 1, None, 0))
            sel_tgt = bool(doc.Extension.SelectByID2(target_entity, "SKETCHSEGMENT", 0, 0, 0, True, 2, None, 0))
            if not (sel_src and sel_tgt):
                return self._result(False, f"replace_sketch_entity: '{source_entity}' o '{target_entity}' non trovata/non selezionabile.", SwErrors.swSelectionError)

            try:
                ok = bool(sm.SketchReplace2(bool(make_construction), bool(make_contour)))
            except Exception as ex:
                return self._result(False, f"replace_sketch_entity: sostituzione non riuscita: {ex}", SwErrors.swSketchError)
            if not ok:
                return self._result(False, "replace_sketch_entity: SolidWorks non ha sostituito l'entità.", SwErrors.swSketchError)

            msg = f"Sostituzione entità '{source_entity}' -> '{target_entity}' completata."
            return self._result(True, msg, SwErrors.swSuccess, {
                "source_entity": source_entity,
                "target_entity": target_entity,
                "replaced": True,
                "make_construction": bool(make_construction),
                "make_contour": bool(make_contour)
            })
        except Exception as e:
            logger.error(f"replace_sketch_entity: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def create_sketch_belt(self, pulleys: list = None, thickness: float = 2.0, unit: str = None) -> Dict:
        """Crea una cinghia/catena cinematica puleggia-cinghia tra cerchi o archi nello schizzo."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            sm = doc.SketchManager
            segs = self._s5_segs(doc)
            th_m = self._mmu(thickness or 2.0, unit)

            selected_count = 0
            doc.ClearSelection2(True)
            sd = self._s5_sd(doc, 0)

            if pulleys:
                by_id = {self._safe_seg_id(s): s for s in segs}
                for ent_id in pulleys:
                    s = by_id.get(ent_id)
                    if s is None:
                        return self._result(False, f"create_sketch_belt: '{ent_id}' non trovata.", SwErrors.swSelectionError)
                    try:
                        sel_ok = bool(s.Select4(selected_count > 0, sd))
                    except Exception as ex:
                        return self._result(False, f"create_sketch_belt: selezione '{ent_id}' non riuscita: {ex}", SwErrors.swSelectionError)
                    if not sel_ok:
                        return self._result(False, f"create_sketch_belt: selezione '{ent_id}' non riuscita.", SwErrors.swSelectionError)
                    selected_count += 1
            else:
                for s in segs:
                    try:
                        t = int(s.GetType)
                        if t in (1, 2) and bool(s.Select4(selected_count > 0, sd)):  # swSketchARC, swSketchELLIPSE
                            selected_count += 1
                    except Exception:
                        pass

            if selected_count == 0:
                return self._result(False, "create_sketch_belt: nessuna puleggia (cerchio o arco) da collegare.", SwErrors.swSelectionError)

            try:
                ok = bool(sm.CreateSketchBelt(0.0, float(th_m), 1, selected_count,
                                              0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
            except Exception as ex:
                return self._result(False, f"create_sketch_belt: creazione cinghia non riuscita: {ex}", SwErrors.swSketchError)
            if not ok:
                return self._result(False, "create_sketch_belt: SolidWorks non ha creato la cinghia.", SwErrors.swSketchError)

            u = unit or "mm"
            msg = f"Cinghia di schizzo generata collegando {selected_count} pulegge (spessore {thickness} {u})."
            return self._result(True, msg, SwErrors.swSuccess, {
                "belt_created": True,
                "pulleys_count": selected_count,
                "thickness": thickness
            })
        except Exception as e:
            logger.error(f"create_sketch_belt: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    # ====================================================================
    # 3. Gestione e Ispezione Relazioni
    # ====================================================================
    def suppress_sketch_relation(self, relation_index: int = 0, suppress: bool = True) -> Dict:
        """Sospende o riattiva una specifica relazione geometrica dello schizzo attivo."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            sk = doc.SketchManager.ActiveSketch
            rm = sk.RelationManager
            rels = ()
            try:
                rels = rm.GetRelations(0) or ()
            except Exception:
                pass

            idx = max(0, int(relation_index or 0))
            if idx >= len(rels):
                return self._result(False, f"suppress_sketch_relation: relazione #{relation_index} fuori campo (relazioni dello schizzo: {len(rels)}).", SwErrors.swInvalidInput)
            r = rels[idx]
            try:
                r.set_Suppressed(bool(suppress))
            except Exception:
                try:
                    r.Suppressed = bool(suppress)
                except Exception as ex:
                    return self._result(False, f"suppress_sketch_relation: impostazione soppressione non riuscita: {ex}", SwErrors.swSketchError)

            action = "sospesa" if suppress else "riattivata"
            msg = f"Relazione #{relation_index} {action} con successo."
            return self._result(True, msg, SwErrors.swSuccess, {
                "relation_index": relation_index,
                "suppressed": bool(suppress),
                "success": True
            })
        except Exception as e:
            logger.error(f"suppress_sketch_relation: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def get_allowed_relations(self, entities: list = None) -> Dict:
        """Interroga SOLIDWORKS sui vincoli geometrici matematicamente consentiti tra entità selezionate."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            sk = doc.SketchManager.ActiveSketch
            rm = sk.RelationManager
            segs = self._s5_segs(doc)
            sd = self._s5_sd(doc, 0)

            if entities:
                doc.ClearSelection2(True)
                by_id = {self._safe_seg_id(s): s for s in segs}
                for i, ent_id in enumerate(entities):
                    s = by_id.get(ent_id)
                    if s:
                        try:
                            s.Select4(i > 0, sd)
                        except Exception:
                            pass

            allowed_ids = ()
            try:
                allowed_ids = rm.GetAllowedRelations(None) or ()
            except Exception as ex:
                logger.warning(f"GetAllowedRelations error: {ex}")

            allowed_names = [CONSTRAINT_NAMES.get(int(i), f"Constraint_{i}") for i in allowed_ids]

            msg = f"Individuati {len(allowed_names)} vincoli geometrici consentiti tra le entità."
            return self._result(True, msg, SwErrors.swSuccess, {
                "allowed_relations": allowed_names,
                "allowed_relation_ids": list(allowed_ids)
            })
        except Exception as e:
            logger.error(f"get_allowed_relations: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def delete_all_sketch_relations(self, sketch: str = None) -> Dict:
        """Elimina simultaneamente tutti i vincoli geometrici e quote dallo schizzo attivo."""
        try:
            doc, _sk, err = self._s2_active_or_open(sketch)
            if err:
                return err

            sk = doc.SketchManager.ActiveSketch
            rm = sk.RelationManager

            try:
                before = len(rm.GetRelations(0) or ())
            except Exception:
                before = -1
            ok = False
            try:
                ok = bool(self._com(rm, "DeleteAllRelations"))
            except Exception as ex:
                logger.warning(f"DeleteAllRelations error: {ex}")
                try:
                    ok = bool(doc.DeleteAllRelations())
                except Exception:
                    pass

            try:
                remaining = len(rm.GetRelations(0) or ())
            except Exception:
                remaining = -1
            if remaining != 0:
                return self._result(False, f"delete_all_sketch_relations: relazioni rimaste {remaining} (relazioni prima {before}, DeleteAllRelations={ok}).", SwErrors.swSketchError)

            msg = "Tutte le relazioni e vincoli di schizzo sono stati eliminati."
            return self._result(True, msg, SwErrors.swSuccess, {
                "all_relations_deleted": True,
                "remaining_relations": remaining
            })
        except Exception as e:
            logger.error(f"delete_all_sketch_relations: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    # ====================================================================
    # 4. Regioni, 3D e Blocchi
    # ====================================================================
    def list_sketch_regions(self, sketch: str = None) -> Dict:
        """Ispeziona ed elenca le regioni chiuse (aree d'intersezione) e i contorni dello schizzo."""
        try:
            doc, _sk, err = self._s2_active_or_open(sketch)
            if err:
                return err

            sk = doc.SketchManager.ActiveSketch
            try:
                regions = self._com(sk, "GetSketchRegions") or ()
            except Exception as ex:
                return self._result(False, f"list_sketch_regions: lettura delle regioni non riuscita: {ex}", SwErrors.swSketchError)
            try:
                contours = self._com(sk, "GetSketchContours") or ()
            except Exception as ex:
                return self._result(False, f"list_sketch_regions: lettura dei contorni non riuscita: {ex}", SwErrors.swSketchError)

            reg_list = []
            for i, r in enumerate(regions):
                edge_count = 0
                try:
                    edge_count = int(self._com(r, "GetEdgesCount"))
                except Exception:
                    pass
                reg_list.append({"region_index": i, "edges_count": edge_count})

            msg = f"Rilevate {len(reg_list)} regioni chiuse e {len(contours)} contorni nello schizzo."
            return self._result(True, msg, SwErrors.swSuccess, {
                "regions_count": len(reg_list),
                "contours_count": len(contours),
                "regions": reg_list
            })
        except Exception as e:
            logger.error(f"list_sketch_regions: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def rotate_copy_3d_sketch(self, angle_deg: float, base_x: float = 0.0, base_y: float = 0.0,
                              base_z: float = 0.0, vector_x: float = 0.0, vector_y: float = 0.0,
                              vector_z: float = 1.0, copy: bool = False, num_copies: int = 1,
                              entities: list = None, unit: str = None) -> Dict:
        """Ruota o copia entità di schizzo 3D attorno a un asse o vettore arbitrario nello spazio."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            sm = doc.SketchManager
            bx_m = self._mmu(base_x, unit)
            by_m = self._mmu(base_y, unit)
            bz_m = self._mmu(base_z, unit)
            rad = math.radians(float(angle_deg))

            segs = self._s5_segs(doc)
            sd = self._s5_sd(doc, 0)

            n_copies = max(1, int(num_copies or 1))
            if n_copies > 1000:
                return self._result(False, "rotate_copy_3d_sketch: num_copies massimo 1000.", SwErrors.swInvalidInput)

            sel_n = 0
            if entities:
                doc.ClearSelection2(True)
                by_id = {self._safe_seg_id(s): s for s in segs}
                for ent_id in entities:
                    s = by_id.get(ent_id)
                    if s is None:
                        return self._result(False, f"rotate_copy_3d_sketch: '{ent_id}' non trovata.", SwErrors.swSelectionError)
                    if not bool(s.Select4(sel_n > 0, sd)):
                        return self._result(False, f"rotate_copy_3d_sketch: selezione '{ent_id}' non riuscita.", SwErrors.swSelectionError)
                    sel_n += 1
            else:
                for s in segs:
                    if not bool(s.Select4(sel_n > 0, sd)):
                        return self._result(False, "rotate_copy_3d_sketch: selezione di un'entità non riuscita.", SwErrors.swSelectionError)
                    sel_n += 1
            if sel_n == 0:
                return self._result(False, "rotate_copy_3d_sketch: nessuna entità da trasformare.", SwErrors.swSelectionError)

            try:
                ok = bool(sm.RotateOrCopy3DAboutVector(bool(copy), n_copies, True,
                                                      float(bx_m), float(by_m), float(bz_m),
                                                      float(vector_x), float(vector_y), float(vector_z),
                                                      float(rad)))
            except Exception as ex:
                return self._result(False, f"rotate_copy_3d_sketch: trasformazione non riuscita: {ex}", SwErrors.swSketchError)
            if not ok:
                return self._result(False, "rotate_copy_3d_sketch: SolidWorks non ha eseguito la trasformazione.", SwErrors.swSketchError)

            mode_str = f"copia ({n_copies} istanze)" if copy else "rotazione"
            msg = f"Operazione 3D {mode_str} completata (angolo: {angle_deg}°)."
            return self._result(True, msg, SwErrors.swSuccess, {
                "transformed": True,
                "angle_deg": angle_deg,
                "copy": bool(copy),
                "num_copies": n_copies if copy else 0
            })
        except Exception as e:
            logger.error(f"rotate_copy_3d_sketch: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)


    def set_sketch_performance_mode(self, add_to_db: bool = False, auto_solve: bool = True,
                                    auto_inference: bool = True) -> Dict:
        """Configura le modalità di prestazione del disegno veloce di schizzo."""
        try:
            doc, err = self._part()
            if err:
                doc, err = self.get_active_doc()
                if err:
                    return err

            sm = doc.SketchManager
            impostazioni = {"AddToDB": add_to_db, "AutoSolve": auto_solve, "AutoInference": auto_inference}
            chiavi = {"AddToDB": "add_to_db", "AutoSolve": "auto_solve", "AutoInference": "auto_inference"}
            # (revisione 2026-11-12) valori di partenza letti prima: tornano al loro posto se il tool fallisce a meta' e
            # sono riportati nel risultato (le impostazioni RESTANO attive dopo il tool: e' il suo scopo)
            prima = {}
            for nome in impostazioni:
                try:
                    prima[nome] = bool(getattr(sm, nome))
                except Exception:
                    prima[nome] = None
            cambiati = []

            def _scrivi(nome, valore):
                try:
                    setattr(sm, nome, bool(valore))
                except Exception:
                    getattr(sm, "set_" + nome)(bool(valore))

            def _annulla():
                for n in reversed(cambiati):
                    if prima.get(n) is not None:
                        try:
                            _scrivi(n, prima[n])
                        except Exception as ex2:
                            logger.warning(f"set_sketch_performance_mode: {n} non ripristinato: {ex2}")
            for nome, valore in impostazioni.items():
                try:
                    _scrivi(nome, valore)
                except Exception as ex:
                    _annulla()
                    return self._result(False, f"set_sketch_performance_mode: {nome} non impostato: {ex} (le altre "
                                        "impostazioni sono tornate come prima)", SwErrors.swSketchError, {"previous": {chiavi[n]: v for n, v in prima.items()}})
                cambiati.append(nome)
                try:
                    letto = bool(getattr(sm, nome))
                except Exception:
                    letto = None
                if letto != bool(valore):
                    _annulla()
                    return self._result(False, f"set_sketch_performance_mode: {nome} non verificato (letto {letto}, atteso {bool(valore)}); "
                                        "le impostazioni sono tornate come prima.", SwErrors.swSketchError,
                                        {"previous": {chiavi[n]: v for n, v in prima.items()}})

            msg = (f"Modalità prestazioni schizzo aggiornata (AddToDB={add_to_db}, AutoSolve={auto_solve}, AutoInference={auto_inference}); "
                   "resta attiva finche' non la si cambia: per tornare indietro richiamare il tool con i valori in data.previous.")
            return self._result(True, msg, SwErrors.swSuccess, {
                "add_to_db": bool(add_to_db),
                "auto_solve": bool(auto_solve),
                "auto_inference": bool(auto_inference),
                "previous": {chiavi[n]: v for n, v in prima.items()}
            })
        except Exception as e:
            logger.error(f"set_sketch_performance_mode: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)
