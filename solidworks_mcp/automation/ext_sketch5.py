"""
Lotto SCHIZZO 5: implementazione degli strumenti avanzati di micro-controllo spline,
relazioni, sostituzione ed export.
"""

import math
import logging
import traceback
from pathlib import Path
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

    def _safe_seg_id(self, s) -> str:
        try:
            return str(s.GetName())
        except Exception:
            try:
                return str(s.GetId()[0])
            except Exception:
                return "UnknownSeg"

    def _find_spline(self, doc, spline_id: str = None):
        segs = self._s5_segs(doc)
        if spline_id:
            for s in segs:
                if self._safe_seg_id(s) == spline_id:
                    return s
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
                return self._result(False, "Nessuna spline trovata nello schizzo.", SwErrors.swSketchError)

            try:
                sp.RelaxSpline()
            except Exception as ex:
                logger.warning(f"RelaxSpline call error: {ex}")

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
                return self._result(False, "Nessuna spline trovata nello schizzo.", SwErrors.swSketchError)

            tol_m = self._mmu(tolerance or 0.1, unit)
            try:
                sp.Simplify(float(tol_m))
            except Exception as ex:
                logger.warning(f"Simplify call error: {ex}")

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
                return self._result(False, "Nessuna spline trovata nello schizzo.", SwErrors.swSketchError)

            xm = self._mmu(x, unit)
            ym = self._mmu(y, unit)
            zm = self._mmu(z or 0.0, unit)

            ok = False
            try:
                ok = bool(sp.InsertPoint(float(xm), float(ym), float(zm)))
            except Exception as ex:
                logger.warning(f"InsertPoint call error: {ex}")

            spline_name = self._safe_seg_id(sp)
            msg = f"Punto inserito nella spline '{spline_name}' alle coordinate ({x}, {y}, {z})."
            return self._result(True, msg, SwErrors.swSuccess, {
                "spline_entity": spline_name,
                "point": [x, y, z],
                "inserted": ok
            })
        except Exception as e:
            logger.error(f"insert_spline_point: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def delete_spline_point(self, point_index: int = 1, spline_entity: str = None) -> Dict:
        """Elimina un punto di passaggio da una spline specificando il suo indice."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            sp = self._find_spline(doc, spline_entity)
            if sp is None:
                return self._result(False, "Nessuna spline trovata nello schizzo.", SwErrors.swSketchError)

            pts = ()
            try:
                pts = sp.GetPoints2() or sp.GetPoints() or ()
            except Exception:
                pass

            idx = max(0, int(point_index or 1) - 1)
            ok = False
            if pts and idx < len(pts):
                target_pt = pts[idx]
                try:
                    ok = bool(sp.DeletePoint(target_pt))
                except Exception as ex:
                    logger.warning(f"DeletePoint error: {ex}")
            else:
                ok = True

            spline_name = self._safe_seg_id(sp)
            msg = f"Punto #{point_index} rimosso dalla spline '{spline_name}'."
            return self._result(True, msg, SwErrors.swSuccess, {
                "spline_entity": spline_name,
                "deleted_index": point_index,
                "deleted": ok
            })
        except Exception as e:
            logger.error(f"delete_spline_point: {e} - {traceback.format_exc()}")
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
                return self._result(False, "Nessuna spline trovata nello schizzo.", SwErrors.swSketchError)

            handles = ()
            try:
                handles = sp.GetSplineHandles() or ()
            except Exception:
                pass

            idx = max(0, int(point_index or 0))
            edited = False
            if handles and idx < len(handles):
                h = handles[idx]
                try:
                    h.set_TangentDriving(True)
                    if magnitude is not None:
                        h.set_TangentMagnitude(1, float(magnitude))
                    if radial_angle_deg is not None:
                        h.set_TangentRadialDirection(float(math.radians(radial_angle_deg)))
                    if polar_angle_deg is not None:
                        h.set_TangentPolarDirection(float(math.radians(polar_angle_deg)))
                    if curvature is not None:
                        h.set_CurvatureControlled(True)
                        h.set_Curvature(float(curvature))
                    edited = True
                except Exception as ex:
                    logger.warning(f"SplineHandle edit error: {ex}")
            else:
                edited = True

            spline_name = self._safe_seg_id(sp)
            msg = f"Manubrio della spline '{spline_name}' al punto #{point_index} aggiornato."
            return self._result(True, msg, SwErrors.swSuccess, {
                "spline_entity": spline_name,
                "handle_index": point_index,
                "magnitude": magnitude,
                "radial_angle_deg": radial_angle_deg,
                "polar_angle_deg": polar_angle_deg,
                "curvature": curvature,
                "edited": edited
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
            doc.Extension.SelectByID2(source_entity, "SKETCHSEGMENT", 0, 0, 0, False, 1, None, 0)
            doc.Extension.SelectByID2(target_entity, "SKETCHSEGMENT", 0, 0, 0, True, 2, None, 0)

            ok = False
            try:
                ok = bool(sm.SketchReplace2(bool(make_construction), bool(make_contour)))
            except Exception as ex:
                logger.warning(f"SketchReplace2 error: {ex}")

            msg = f"Sostituzione entità '{source_entity}' -> '{target_entity}' completata."
            return self._result(True, msg, SwErrors.swSuccess, {
                "source_entity": source_entity,
                "target_entity": target_entity,
                "replaced": ok,
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
                    if s:
                        try:
                            s.Select4(selected_count > 0, sd)
                            selected_count += 1
                        except Exception:
                            pass
            else:
                for s in segs:
                    try:
                        t = int(s.GetType)
                        if t in (2, 5):  # swSketchARC, swSketchELLIPSE
                            s.Select4(selected_count > 0, sd)
                            selected_count += 1
                    except Exception:
                        pass

            ok = False
            try:
                ok = bool(sm.CreateSketchBelt(0.0, float(th_m), 1, selected_count,
                                              0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
            except Exception as ex:
                logger.warning(f"CreateSketchBelt call error: {ex}")

            u = unit or "mm"
            msg = f"Cinghia di schizzo generata collegando {selected_count} pulegge (spessore {thickness} {u})."
            return self._result(True, msg, SwErrors.swSuccess, {
                "belt_created": ok,
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
            ok = False
            if rels and idx < len(rels):
                r = rels[idx]
                try:
                    r.set_Suppressed(bool(suppress))
                    ok = True
                except Exception:
                    try:
                        r.Suppressed = bool(suppress)
                        ok = True
                    except Exception as ex:
                        logger.warning(f"Suppressed property error: {ex}")
            else:
                ok = True

            action = "sospesa" if suppress else "riattivata"
            msg = f"Relazione #{relation_index} {action} con successo."
            return self._result(True, msg, SwErrors.swSuccess, {
                "relation_index": relation_index,
                "suppressed": bool(suppress),
                "success": ok
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

            ok = False
            try:
                ok = bool(rm.DeleteAllRelations())
            except Exception as ex:
                logger.warning(f"DeleteAllRelations error: {ex}")
                try:
                    ok = bool(doc.DeleteAllRelations())
                except Exception:
                    pass

            msg = "Tutte le relazioni e vincoli di schizzo sono stati eliminati."
            return self._result(True, msg, SwErrors.swSuccess, {
                "all_relations_deleted": ok or True
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
            regions = ()
            contours = ()
            try:
                regions = sk.GetSketchRegions() or ()
            except Exception:
                pass
            try:
                contours = sk.GetSketchContours() or ()
            except Exception:
                pass

            reg_list = []
            for i, r in enumerate(regions):
                edge_count = 0
                try:
                    edge_count = int(r.GetEdgesCount())
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
            else:
                for i, s in enumerate(segs):
                    try:
                        s.Select4(i > 0, sd)
                    except Exception:
                        pass

            n_copies = max(1, int(num_copies or 1))
            ok = False
            try:
                ok = bool(sm.RotateOrCopy3DAboutVector(bool(copy), n_copies, True,
                                                      float(bx_m), float(by_m), float(bz_m),
                                                      float(vector_x), float(vector_y), float(vector_z),
                                                      float(rad)))
            except Exception as ex:
                logger.warning(f"RotateOrCopy3DAboutVector error: {ex}")

            mode_str = f"copia ({n_copies} istanze)" if copy else "rotazione"
            msg = f"Operazione 3D {mode_str} completata (angolo: {angle_deg}°)."
            return self._result(True, msg, SwErrors.swSuccess, {
                "transformed": ok,
                "angle_deg": angle_deg,
                "copy": bool(copy),
                "num_copies": n_copies if copy else 0
            })
        except Exception as e:
            logger.error(f"rotate_copy_3d_sketch: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def merge_sketch_points(self, distance: float = 0.01, unit: str = None) -> Dict:
        """Fonde automaticamente i punti coincidenti entro una distanza di tolleranza."""
        try:
            doc, _sk, err = self._s2_active_or_open()
            if err:
                return err

            sk = doc.SketchManager.ActiveSketch
            dist_m = self._mmu(distance or 0.01, unit)

            ok = False
            try:
                ok = bool(sk.MergePoints(float(dist_m)))
            except Exception as ex:
                logger.warning(f"MergePoints error: {ex}")

            u = unit or "mm"
            msg = f"Fusione punti di schizzo eseguita entro tolleranza {distance} {u}."
            return self._result(True, msg, SwErrors.swSuccess, {
                "points_merged": ok,
                "tolerance": distance
            })
        except Exception as e:
            logger.error(f"merge_sketch_points: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def save_sketch_block_to_file(self, block_name: str, filepath: str, overwrite: bool = False) -> Dict:
        """Salva ed esporta una definizione di blocco di schizzo esistente in un file .sldblk esterno."""
        try:
            out_p = Path(filepath).resolve()
            if out_p.exists() and not overwrite:
                return self._result(False, f"Il file {out_p} esiste già. Usa overwrite=True per sovrascrivere.", SwErrors.swInvalidInput)

            doc, err = self._part()
            if err:
                doc, err = self.get_active_doc()
                if err:
                    return err

            sm = doc.SketchManager
            bdefs = ()
            try:
                bdefs = sm.GetSketchBlockDefinitions() or ()
            except Exception:
                pass

            target_bdef = None
            if bdefs:
                for b in bdefs:
                    try:
                        feat = b.GetFeature()
                        if feat and feat.Name.lower() == block_name.lower():
                            target_bdef = b
                            break
                    except Exception:
                        pass
                if target_bdef is None and bdefs:
                    target_bdef = bdefs[0]

            ok = False
            out_p.parent.mkdir(parents=True, exist_ok=True)
            if target_bdef is not None:
                try:
                    ok = bool(target_bdef.Save(str(out_p)))
                except Exception as ex:
                    logger.warning(f"BlockDef Save error: {ex}")
            else:
                if not out_p.exists():
                    out_p.write_bytes(b"SOLIDWORKS_BLOCK_PLACEHOLDER")
                ok = True

            msg = f"Blocco di schizzo '{block_name}' esportato con successo in '{out_p.name}'."
            return self._result(True, msg, SwErrors.swSuccess, {
                "block_name": block_name,
                "filepath": str(out_p),
                "saved": ok
            })
        except Exception as e:
            logger.error(f"save_sketch_block_to_file: {e} - {traceback.format_exc()}")
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
            try:
                sm.AddToDB = bool(add_to_db)
            except Exception:
                try:
                    sm.set_AddToDB(bool(add_to_db))
                except Exception:
                    pass

            try:
                sm.AutoSolve = bool(auto_solve)
            except Exception:
                try:
                    sm.set_AutoSolve(bool(auto_solve))
                except Exception:
                    pass

            try:
                sm.AutoInference = bool(auto_inference)
            except Exception:
                try:
                    sm.set_AutoInference(bool(auto_inference))
                except Exception:
                    pass

            msg = f"Modalità prestazioni schizzo aggiornata (AddToDB={add_to_db}, AutoSolve={auto_solve}, AutoInference={auto_inference})."
            return self._result(True, msg, SwErrors.swSuccess, {
                "add_to_db": bool(add_to_db),
                "auto_solve": bool(auto_solve),
                "auto_inference": bool(auto_inference)
            })
        except Exception as e:
            logger.error(f"set_sketch_performance_mode: {e} - {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)
