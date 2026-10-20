"""
Lotto SUPERFICI 1 (creazione: estrusa, rivoluzione, sweep, loft, piana, boundary, rigata, riempimento) (mixin).
Schemi in tools_ext/surfaces1.py. I metodi usano gli helper di ModelingBase/ModelingOperations tramite self
(_part, _select_feature, _resolve_sketch, _names, _new_features, _volume_m3, _mmu, _result...).

Trappole API scoperte (SW 2026, laboratorio srf1, vedi scripts_tmp/notes_surfaces1.md):
 - Coordinate del modello in questo template: lo schizzo sul piano "Front" ha normale +X (u -> Y, v -> Z), "Top" ha normale
   +Z (u -> Y, v -> -X), "Right" ha normale +Y (u -> -X, v -> Z). Le coordinate dei punti degli spigoli/facce sono quelle del
   modello (come le restituisce list_entities).
 - FeatureExtruRefSurface3, InsertSweepSurface3, InsertLoftRefSurface2 (doc), InsertPlanarRefSurface (PROPRIETA' del doc),
   InsertNetBlend2 non restituiscono la feature in modo affidabile: l'esito e' la feature nuova (per differenza) + la
   misura dei corpi superficie (IFace2.GetArea).
 - Estrusa: "fino alla superficie" funziona con UpToSelection (10) e la faccia con Mark 1; UpToSurface (4) e
   OffsetFromSurface (5) non creano nulla. Con `cap_end` + `cap_end2` (o piano di mezzeria) un profilo chiuso diventa
   un SOLIDO (closed surface). Lo sformo sposta solo la lunghezza: una linea 40 x 20 con 10 gradi -> 40*20/cos(10).
 - Sweep: torsione costante lungo il percorso = TwistCtrlOption 8 (1 = normale costante: nessuna torsione).
 - Rigata: Type 0 = normale alla superficie, 1 = tangente, 4 = perpendicolare al vettore; spigoli con Mark 4. Type 2 e 3
   (rastremata) non creano nulla; un vettore parallelo allo spigolo adiacente o alla normale puo' appendere la chiamata.
 - Boundary (InsertNetBlend2): Type 0 = boss (solido), 2 = superficie, 3 = taglio (1 non e' un taglio: si comporta da
   boss; 4 e 5 appendono SolidWorks). Curve direzione 1 = schizzi con Mark 1, direzione 2 = Mark 2. NON selezionare i
   segmenti dello schizzo: InsertNetBlend2 manda in crash SolidWorks.
 - Riempimento (InsertFillSurface2): la selezione NON funziona (e Mark 4 manda in crash SolidWorks): servono gli array
   VPatchBoundaries (IEdge, VT_ARRAY|VT_DISPATCH) e VCurvatureControlType (VT_ARRAY|VT_I4: 0 contatto, 1 tangente,
   2 curvatura) + VFaces (facce per spigolo, per tangente/curvatura). Options: 1 ottimizza, 2 prova a fare il solido,
   4 unisci, 8 inverti direzione, 16 inverti superficie; 4 + 2 chiude un buco e produce un solido.
"""

import math
import time
import logging
import traceback
from typing import Dict, List, Optional

import win32com.client
import pythoncom

from ..constants import SwErrors
from .modeling_base import null_variant

logger = logging.getLogger(__name__)

_EXTRUDE_END = {"blind": 0, "through_all": 1, "up_to_next": 2, "mid_plane": 6, "up_to_surface": 10}
_SKIP_TYPES = ("ProfileFeature", "RefPlane", "RefAxis", "RefPoint", "CoordSys")
_CONTINUITY = {"contact": 0, "tangent": 1, "curvature": 2}


class Surfaces1Operations:
    """Mixin del lotto surfaces1."""

    # ------------------------------------------------------------------ utilita' interne
    def _sf_snapshot(self, doc) -> Dict:
        """Stato dei corpi: aree dei corpi superficie (m2), numero di solidi, volume (m3)."""
        areas = []
        try:
            for b in (doc.GetBodies2(1, False) or []):
                faces = self._com(b, "GetFaces") or []
                areas.append(sum(float(self._com(f, "GetArea")) for f in faces))
        except Exception:
            pass
        try:
            solids = len(doc.GetBodies2(0, False) or [])
        except Exception:
            solids = 0
        return {"sheet_areas": areas, "solids": solids, "volume": self._volume_m3(doc) if solids else 0.0}

    def _sf_pick(self, doc, kind: str, point, unit, mark: int, append: bool, tol_mm: float = 0.05):
        """Seleziona spigolo/faccia (punto SULL'entita') fra TUTTI i corpi (solidi e superficie). -> (oggetto|None, errore)."""
        try:
            p = [self._mmu(float(c), unit) for c in point]
        except Exception:
            return None, f"punto non valido: {point}"
        if len(p) != 3:
            return None, f"il punto deve avere 3 coordinate: {point}"
        best, bd = None, 1e9
        for b in (doc.GetBodies2(-1, False) or []):
            for ent in (self._com(b, "GetEdges" if kind == "edge" else "GetFaces") or []):
                try:
                    q = ent.GetClosestPointOn(p[0], p[1], p[2])
                except Exception:
                    continue
                if q is None:
                    continue
                d = self._dist(q, p)
                if d < bd:
                    best, bd = ent, d
        if best is None or bd > max(tol_mm, 0.001) / 1000.0:
            return None, (f"nessun {'spigolo' if kind == 'edge' else 'faccia'} entro {tol_mm} mm dal punto {list(point)} "
                          f"(piu' vicino a {bd * 1000:.3f} mm). Il punto deve stare SULL'entita' (vedi list_entities).")
        sd = self._sd(doc, mark)
        try:
            sd.X, sd.Y, sd.Z = p[0], p[1], p[2]
        except Exception:
            pass
        if not best.Select4(append, sd):
            return None, f"selezione del {kind} rifiutata"
        return best, None

    def _sf_pick_objects(self, doc, kind: str, points, unit):
        """Come _sf_pick ma senza selezionare: lista di oggetti (per gli array dell'API). -> (lista, errore)."""
        out = []
        for pt in points:
            ent, err = self._sf_pick(doc, kind, pt, unit, 0, False)
            if err:
                return None, err
            out.append(ent)
            doc.ClearSelection2(True)
        return out, None

    def _sf_sketches_ok(self, doc, names) -> Optional[Dict]:
        for n in names:
            f = self._find_feature(doc, n)
            if f is None or self._com(f, "GetTypeName2") != "ProfileFeature":
                return self._result(False, f"Schizzo '{n}' non trovato. Schizzi: {self._feature_names(doc, 'ProfileFeature')}",
                                    SwErrors.swSelectionError)
        return None

    def _sf_create_errors(self, doc):
        """Motivo dell'ultimo CreateFeature fallito (IFeatureManager.GetCreateFeatureErrors) o None."""
        try:
            msgs = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_VARIANT, None)
            tname = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BSTR, "")
            code = doc.FeatureManager.GetCreateFeatureErrors(msgs, tname)
            return {"code": code, "messages": msgs.value if hasattr(msgs, "value") else None,
                    "type": tname.value if hasattr(tname, "value") else None}
        except Exception as e:
            return {"error": repr(e)[:100]}

    def _sf_finish(self, doc, label: str, feat, before: List[str], snap0: Dict, extra: Dict = None) -> Dict:
        """Esito comune: feature nuova (per differenza), corpi superficie e AREA misurati."""
        new = [x for x in self._new_features(doc, before)
               if x["type"] not in _SKIP_TYPES and not x["type"].endswith("Folder")]
        if not new:
            snap = self._sf_snapshot(doc)
            return self._result(False, f"{label} non riuscito (SolidWorks non ha creato nessuna feature). "
                                "Controlla schizzo/spigoli selezionati, profilo e parametri.", SwErrors.swFeatureError,
                                {"surface_areas_mm2": [round(a * 1e6, 3) for a in snap["sheet_areas"]],
                                 "solid_bodies": snap["solids"], "features": self._names(doc)[-6:],
                                 "create_errors": self._sf_create_errors(doc)})
        name, ftype = new[0]["name"], new[0]["type"]
        f = self._find_feature(doc, name)
        snap1 = self._sf_snapshot(doc)
        created = None
        try:
            faces = self._com(f, "GetFaces") or []
            created = sum(float(self._com(x, "GetArea")) for x in faces) if faces else None
        except Exception:
            created = None
        total0, total1 = sum(snap0["sheet_areas"]), sum(snap1["sheet_areas"])
        if not created:
            created = max(total1 - total0, 0.0) or None
        data = {"feature": name, "feature_type": ftype, "surface_bodies": len(snap1["sheet_areas"]),
                "surface_bodies_added": len(snap1["sheet_areas"]) - len(snap0["sheet_areas"]),
                "surface_area_mm2": round(created * 1e6, 3) if created else 0.0,
                "total_surface_area_mm2": round(total1 * 1e6, 3), "solid_bodies": snap1["solids"],
                "volume_mm3": round(snap1["volume"] * 1e9, 3),
                "volume_delta_mm3": round((snap1["volume"] - snap0["volume"]) * 1e9, 3)}
        try:
            code = self._com(f, "GetErrorCode2")
            code = code[0] if isinstance(code, tuple) else code
            if code:
                data["rebuild_error_code"] = int(code)
        except Exception:
            pass
        if extra:
            data.update(extra)
        msg = (f"{label}: {name} (superficie {data['surface_area_mm2']:.2f} mm2, corpi superficie "
               f"{data['surface_bodies']}, solidi {data['solid_bodies']})")
        if "rebuild_error_code" in data:
            return self._result(False, msg + f" - errore di ricostruzione {data['rebuild_error_code']}",
                                SwErrors.swFeatureError, data)
        return self._result(True, msg, SwErrors.swSuccess, data)

    # ------------------------------------------------------------------ 1. superficie estrusa
    def extrude_surface(self, sketch: str = None, depth: float = 10, end_condition: str = "blind",
                        depth2: float = None, end_condition2: str = None, draft_angle: float = 0,
                        draft_outward: bool = False, up_to_face_point: list = None, reverse: bool = False,
                        cap_end: bool = False, cap_end2: bool = False, start_offset: float = None,
                        unit: str = None) -> Dict:
        try:
            doc, err = self._part()
            if err:
                return err
            ec = (end_condition or "blind").lower()
            if ec not in _EXTRUDE_END and ec != "through_all_both":
                return self._result(False, f"end_condition sconosciuta: {end_condition}. Valide: "
                                    f"{sorted(list(_EXTRUDE_END) + ['through_all_both'])}", SwErrors.swInvalidInput)
            sk_name, err = self._resolve_sketch(doc, sketch)
            if err:
                return err
            t1, t2, sd = (1, 1, False) if ec == "through_all_both" else (_EXTRUDE_END[ec], 0, True)
            if depth2 is not None or end_condition2:
                ec2 = (end_condition2 or "blind").lower()
                if ec2 not in ("blind", "through_all") or ec == "through_all_both":
                    return self._result(False, "end_condition2 ammesse: blind | through_all (con end_condition diversa da "
                                        "through_all_both)", SwErrors.swInvalidInput)
                sd, t2 = False, (1 if ec2 == "through_all" else 0)
            if t1 == 10 and not up_to_face_point:
                return self._result(False, "Per up_to_surface serve up_to_face_point=[x,y,z] (punto sulla faccia o "
                                    "superficie di arresto, vedi list_entities).", SwErrors.swInvalidInput)
            snap0 = self._sf_snapshot(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            if not self._select_feature(doc, sk_name, False, 0):
                return self._result(False, f"Schizzo '{sk_name}' non selezionabile", SwErrors.swSelectionError)
            if t1 == 10:
                ent, e = self._sf_pick(doc, "face", up_to_face_point, unit, 1, True)
                if e:
                    return self._result(False, f"Faccia di arresto: {e}", SwErrors.swSelectionError)
            d1 = self._mmu(depth or 0, unit)
            d2 = self._mmu(depth2 or 0, unit)
            ang = math.radians(draft_angle or 0)
            dr = bool(draft_angle)
            t0, off = (3, self._mmu(start_offset, unit)) if start_offset else (0, 0.0)
            feat = None
            try:
                feat = doc.FeatureManager.FeatureExtruRefSurface3(
                    sd, bool(reverse), t0, off, t1, t2, d1, d2, dr, False, bool(draft_outward), False, ang, 0.0,
                    False, False, False, False, bool(cap_end), bool(cap_end2), False, False)
            except Exception as e:
                return self._result(False, f"Superficie estrusa fallita: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            return self._sf_finish(doc, "Superficie estrusa", feat, before, snap0,
                                   {"sketch": sk_name, "end_condition": ec, "depth": depth, "unit": self._unit_name(unit)})
        except Exception as e:
            logger.error(f"extrude_surface: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ 2. superficie di rivoluzione
    def _sf_select_axis(self, doc, sk_name: str, axis, unit):
        """Seleziona l'asse (Mark 4) DOPO lo schizzo. -> (tipo, errore)."""
        segs = self._sketch_segments_of(doc, sk_name)
        if isinstance(axis, dict) and "id" in axis:
            axis = axis["id"]
        if axis:
            if isinstance(axis, str):
                for s in segs:
                    if self._seg_id(s) == axis:
                        s.Select4(True, self._sd(doc, 4))
                        return "sketch_segment", None
            spec = axis if isinstance(axis, (dict, list, tuple)) else {"axis": axis}
            ok, msg, _ = self._select_any(doc, spec, unit, True, 4)
            if not ok:
                return None, (f"Asse '{axis}' non selezionabile: {msg} (id di un segmento dello schizzo {sk_name}, nome di "
                              "un asse di riferimento o {\"edge\":[x,y,z]})")
            return "reference", None
        cl = [s for s in segs if int(s.GetType) == 0 and bool(s.ConstructionGeometry)]
        if not cl:
            return None, ("Nessun asse: disegna una linea di mezzeria (draw_centerline_axis) nello schizzo o indica `axis`.")
        cl[0].Select4(True, self._sd(doc, 4))
        return "sketch_centerline", None

    def revolve_surface(self, sketch: str = None, angle: float = 360, axis=None, direction: str = "one_direction",
                        angle2: float = None, reverse: bool = False, unit: str = None) -> Dict:
        try:
            doc, err = self._part()
            if err:
                return err
            dmap = {"one_direction": 0, "mid_plane": 1, "two_directions": 2}
            dr = (direction or "one_direction").lower()
            if dr not in dmap:
                return self._result(False, f"direction sconosciuta: {direction}. Valide: {sorted(dmap)}", SwErrors.swInvalidInput)
            if dr == "two_directions" and angle2 is None:
                return self._result(False, "direction=two_directions richiede angle2 (gradi).", SwErrors.swInvalidInput)
            sk_name, err = self._resolve_sketch(doc, sketch)
            if err:
                return err
            snap0 = self._sf_snapshot(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            if not self._select_feature(doc, sk_name, False, 0):
                return self._result(False, f"Schizzo '{sk_name}' non selezionabile", SwErrors.swSelectionError)
            kind, e = self._sf_select_axis(doc, sk_name, axis, unit)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            feat = None
            try:
                feat = doc.FeatureManager.InsertRevolvedRefSurface(math.radians(angle), bool(reverse),
                                                                   math.radians(angle2 or 0.0), dmap[dr])
            except Exception as ex:
                return self._result(False, f"Superficie di rivoluzione fallita: {ex}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            return self._sf_finish(doc, "Superficie di rivoluzione", feat, before, snap0,
                                   {"sketch": sk_name, "angle": angle, "angle2": angle2, "direction": dr, "axis_kind": kind})
        except Exception as e:
            logger.error(f"revolve_surface: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ 3. superficie sweep
    def sweep_surface(self, profile_sketch: str = None, path_sketch: str = None, guide_sketches: list = None,
                      twist_control: str = "follow_path", twist_angle: float = 0, circular_diameter: float = None,
                      unit: str = None) -> Dict:
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            if not path_sketch:
                return self._result(False, "path_sketch obbligatorio", SwErrors.swInvalidInput)
            tmap = {"follow_path": 0, "keep_normal": 1, "twist": 8}
            tc = (twist_control or "follow_path").lower()
            if tc not in tmap:
                return self._result(False, f"twist_control sconosciuto: {twist_control}. Valide: {sorted(tmap)}",
                                    SwErrors.swInvalidInput)
            if twist_angle and tc != "twist":
                tc = "twist"
            circ = circular_diameter is not None
            names = ([] if circ else [profile_sketch]) + [path_sketch] + list(guide_sketches or [])
            if not circ and not profile_sketch:
                return self._result(False, "Serve profile_sketch oppure circular_diameter (profilo circolare).",
                                    SwErrors.swInvalidInput)
            bad = self._sf_sketches_ok(doc, names)
            if bad:
                return bad
            snap0 = self._sf_snapshot(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            first = True
            if not circ:
                self._select_feature(doc, profile_sketch, False, 1)
                first = False
            self._select_feature(doc, path_sketch, not first, 4)
            for g in (guide_sketches or []):
                self._select_feature(doc, g, True, 2)
            feat = None
            try:
                feat = doc.FeatureManager.InsertSweepSurface3(False, tmap[tc], False, False, 0, 0, 0, True, True,
                                                              math.radians(twist_angle or 0), True, circ,
                                                              self._mmu(circular_diameter or 0, unit), 0)
            except Exception as e:
                return self._result(False, f"Superficie sweep fallita: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            return self._sf_finish(doc, "Superficie sweep", feat, before, snap0,
                                   {"profile": profile_sketch, "path": path_sketch, "guides": list(guide_sketches or []),
                                    "twist_control": tc, "twist_angle": twist_angle})
        except Exception as e:
            logger.error(f"sweep_surface: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ 4. superficie loft
    def loft_surface(self, profile_sketches: list, guide_sketches: list = None, closed: bool = False) -> Dict:
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            if not profile_sketches or len(profile_sketches) < 2:
                return self._result(False, "Servono almeno 2 profili (profile_sketches).", SwErrors.swInvalidInput)
            bad = self._sf_sketches_ok(doc, list(profile_sketches) + list(guide_sketches or []))
            if bad:
                return bad
            snap0 = self._sf_snapshot(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            for i, n in enumerate(profile_sketches):
                self._select_feature(doc, n, i > 0, 1)
            for n in (guide_sketches or []):
                self._select_feature(doc, n, True, 2)
            try:
                doc.InsertLoftRefSurface2(bool(closed), False, False, 1.0, 0, 0)
            except Exception as e:
                return self._result(False, f"Superficie loft fallita: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            return self._sf_finish(doc, "Superficie loft", None, before, snap0,
                                   {"profiles": list(profile_sketches), "guides": list(guide_sketches or []), "closed": closed})
        except Exception as e:
            logger.error(f"loft_surface: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ 5. superficie piana
    def planar_surface(self, sketch: str = None, edge_points: list = None, unit: str = None) -> Dict:
        try:
            doc, err = self._part()
            if err:
                return err
            snap0 = self._sf_snapshot(doc)
            if edge_points:
                self._exit_sketch(doc)
                before = self._names(doc)
                doc.ClearSelection2(True)
                for i, pt in enumerate(edge_points):
                    ent, e = self._sf_pick(doc, "edge", pt, unit, 0, i > 0)
                    if e:
                        return self._result(False, f"Spigolo {i + 1}: {e}", SwErrors.swSelectionError)
                src = {"edge_points": len(edge_points)}
            else:
                sk_name, err = self._resolve_sketch(doc, sketch)
                if err:
                    return err
                before = self._names(doc)
                doc.ClearSelection2(True)
                if not self._select_feature(doc, sk_name, False, 0):
                    return self._result(False, f"Schizzo '{sk_name}' non selezionabile", SwErrors.swSelectionError)
                src = {"sketch": sk_name}
            try:
                self._com(doc, "InsertPlanarRefSurface")
            except Exception as e:
                return self._result(False, f"Superficie piana fallita: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            return self._sf_finish(doc, "Superficie piana", None, before, snap0, src)
        except Exception as e:
            logger.error(f"planar_surface: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ 6. boundary
    def boundary_feature(self, curves1: list, curves2: list = None, kind: str = "surface") -> Dict:
        try:
            doc, err = self._part()
            if err:
                return err
            kmap = {"surface": 2, "boss": 0, "cut": 3}
            k = (kind or "surface").lower()
            if k not in kmap:
                return self._result(False, f"kind sconosciuto: {kind}. Valide: surface | boss | cut", SwErrors.swInvalidInput)
            curves1, curves2 = list(curves1 or []), list(curves2 or [])
            if len(curves1) < 2:
                return self._result(False, "Servono almeno 2 curve (schizzi) in curves1.", SwErrors.swInvalidInput)
            if curves2 and len(curves2) < 2:
                return self._result(False, "curves2 richiede almeno 2 curve (schizzi) oppure nessuna.", SwErrors.swInvalidInput)
            self._exit_sketch(doc)
            bad = self._sf_sketches_ok(doc, curves1 + curves2)
            if bad:
                return bad
            snap0 = self._sf_snapshot(doc)
            if k == "cut" and not snap0["solids"]:
                return self._result(False, "Il boundary cut richiede un corpo solido da tagliare.", SwErrors.swInvalidInput)
            before = self._names(doc)
            doc.ClearSelection2(True)
            for i, n in enumerate(curves1):
                self._select_feature(doc, n, i > 0, 1)
            for n in curves2:
                self._select_feature(doc, n, True, 2)
            feat = None
            try:
                feat = doc.FeatureManager.InsertNetBlend2(kmap[k], len(curves1), len(curves2), False, 1.0, k != "surface",
                                                          True, False, True, False, 0.0, 0.0, False, 0, False, False, 0.0,
                                                          False, 0.0, False, False)
            except Exception as e:
                return self._result(False, f"Boundary fallito: {e}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            r = self._sf_finish(doc, f"Boundary ({k})", feat, before, snap0,
                                {"kind": k, "curves1": curves1, "curves2": curves2})
            if r.get("success") and k != "surface" and abs(r["data"]["volume_delta_mm3"]) < 1e-6:
                r["data"]["warning"] = "il volume non e' cambiato (profili non chiusi o fuori dal corpo?)"
            return r
        except Exception as e:
            logger.error(f"boundary_feature: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ 7. superficie rigata
    def ruled_surface(self, edge_points: list, ruled_type: str = "tangent", distance: float = 5, vector: list = None,
                      reverse: bool = False, unit: str = None) -> Dict:
        try:
            doc, err = self._part()
            if err:
                return err
            tmap = {"tangent": 1, "normal": 0, "perpendicular_to_vector": 4}
            rt = (ruled_type or "tangent").lower()
            if rt == "tapered_to_vector":
                return self._result(False, "ruled_type=tapered_to_vector non e' supportato: l'API di SolidWorks 2026 "
                                    "(InsertRuledSurfaceFromEdge2 tipo 2/3) non crea la feature. Usa tangent | normal | "
                                    "perpendicular_to_vector.", SwErrors.swInvalidInput)
            if rt not in tmap:
                return self._result(False, f"ruled_type sconosciuto: {ruled_type}. Valide: {sorted(tmap)}", SwErrors.swInvalidInput)
            if not edge_points:
                return self._result(False, "Servono edge_points (punti SUGLI spigoli).", SwErrors.swInvalidInput)
            vec = None
            if rt == "perpendicular_to_vector":
                if not vector or len(vector) != 3 or not any(abs(float(c)) > 0 for c in vector):
                    return self._result(False, "perpendicular_to_vector richiede vector=[x,y,z] (direzione non nulla).",
                                        SwErrors.swInvalidInput)
                n = math.sqrt(sum(float(c) ** 2 for c in vector))
                vec = [float(c) / n for c in vector]
            self._exit_sketch(doc)
            snap0 = self._sf_snapshot(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            for i, pt in enumerate(edge_points):
                ent, e = self._sf_pick(doc, "edge", pt, unit, 4, i > 0)
                if e:
                    return self._result(False, f"Spigolo {i + 1}: {e}", SwErrors.swSelectionError)
            x, y, z = vec or (0.0, 0.0, 0.0)
            feat = None
            try:
                feat = doc.FeatureManager.InsertRuledSurfaceFromEdge2(tmap[rt], self._mmu(distance, unit), False, bool(reverse),
                                                                      False, 0.0, vec is not None, x, y, z, False)
            except Exception as ex:
                return self._result(False, f"Superficie rigata fallita: {ex}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            return self._sf_finish(doc, "Superficie rigata", feat, before, snap0,
                                   {"ruled_type": rt, "distance": distance, "unit": self._unit_name(unit), "vector": vec})
        except Exception as e:
            logger.error(f"ruled_surface: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ 8. superficie di riempimento
    def fill_surface(self, edge_points: list, continuity=None, face_points: list = None, merge_result: bool = False,
                     form_solid: bool = False, optimize: bool = False, resolution: int = 1, unit: str = None) -> Dict:
        try:
            doc, err = self._part()
            if err:
                return err
            if not edge_points or len(edge_points) < 1:
                return self._result(False, "Servono edge_points (punti SUGLI spigoli del contorno da riempire).",
                                    SwErrors.swInvalidInput)
            n = len(edge_points)
            if continuity is None:
                cont = ["contact"] * n
            elif isinstance(continuity, str):
                cont = [continuity] * n
            else:
                cont = list(continuity)
            if len(cont) != n or any(str(c).lower() not in _CONTINUITY for c in cont):
                return self._result(False, f"continuity: una stringa o una lista di {n} valori fra {sorted(_CONTINUITY)}.",
                                    SwErrors.swInvalidInput)
            cont = [str(c).lower() for c in cont]
            if any(c != "contact" for c in cont) and not (face_points and len(face_points) == n):
                return self._result(False, f"Per tangent/curvature serve face_points: {n} punti, uno SULLA faccia adiacente "
                                    "di ciascuno spigolo.", SwErrors.swInvalidInput)
            self._exit_sketch(doc)
            snap0 = self._sf_snapshot(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            ca = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_I4, tuple(_CONTINUITY[c] for c in cont))
            opts = (1 if optimize else 0) | (2 if form_solid else 0) | (4 if merge_result else 0)
            feat = None
            attempts = 0
            # a volte (istanza appena avviata) la prima chiamata non crea nulla: si ricostruisce e si riprova, rileggendo gli oggetti
            for attempts in (1, 2, 3):
                if attempts > 1:
                    time.sleep(2.0 * (attempts - 1))      # istanza sotto carico: lascia finire le ricostruzioni
                    try:
                        doc.ForceRebuild3(False)
                    except Exception:
                        pass
                edges, e = self._sf_pick_objects(doc, "edge", edge_points, unit)
                if e:
                    return self._result(False, f"Spigolo: {e}", SwErrors.swSelectionError)
                faces_v = null_variant()
                if face_points:
                    faces, e = self._sf_pick_objects(doc, "face", face_points, unit)
                    if e:
                        return self._result(False, f"Faccia: {e}", SwErrors.swSelectionError)
                    faces_v = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, tuple(faces))
                ea = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, tuple(edges))
                try:
                    feat = doc.FeatureManager.InsertFillSurface2(int(resolution), opts, ea, ca, faces_v, null_variant())
                except Exception as ex:
                    return self._result(False, f"Superficie di riempimento fallita: {ex}", SwErrors.swFeatureError)
                if feat is not None or [x for x in self._new_features(doc, before)
                                        if x["type"] not in _SKIP_TYPES and not x["type"].endswith("Folder")]:
                    break
            doc.ClearSelection2(True)
            return self._sf_finish(doc, "Superficie di riempimento", feat, before, snap0,
                                   {"edges": n, "continuity": cont, "merge_result": merge_result, "form_solid": form_solid,
                                    "attempts": attempts})
        except Exception as e:
            logger.error(f"fill_surface: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)
