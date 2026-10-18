"""
Lotto MOKA (PIANO_MOKA.md): strumenti nuovi per ricreare i pezzi della moka (mixin).
Schemi in tools_ext/moka.py. I metodi usano gli helper di ModelingBase/ModelingOperations tramite self
(_part, _select_point, _select_points, _finish, _names, _new_features, _volume_m3, _mmu, _result...).

Trappole API scoperte (SW 2026, misurate nel laboratorio moka2, vedi scripts_tmp/notes_moka2.md):
 - Filettatura cosmetica: InsertCosmeticThread3(Standard, StandardType, Size, Diameter, EndType, Depth, Note) IGNORA standard,
   tipo e misura (rilegge Standard=-2, Size=''): servono GetDefinition -> AccessSelections(doc, VARIANT nullo) -> set Standard
   (8 = ISO), StandardType ("Machine Threads", come nei file della moka), Size ("M56"), ThreadCallout ("M56 Machine Threads")
   -> ModifyDefinition. CreateDefinition(swFmCosmeticThread=29) restituisce None. DiameterType (2 = maggiore per
   i fori, 3 = minore per gli alberi) lo decide SolidWorks dallo spigolo e non e' scrivibile; il Diametro passato e' preso cosi'
   com'e' (per gli alberi serve il diametro MINORE, calcolato qui). Con "fino alla fine"/"fino al successivo" SolidWorks
   ricalcola da solo BlindDepth (= lunghezza reale).
"""

import re
import math
import logging
import traceback
from typing import Dict, Optional

import pythoncom
import win32com.client

from ..constants import SwErrors
from .modeling import COARSE_PITCH

logger = logging.getLogger(__name__)

_CT_ENDS = {"blind": 0, "up_to_next": 1, "through": 2}     # swCosmeticThreadType_e
_CT_STANDARD_ISO = 8                                      # swWzdHoleStandards_e.swStandardISO
_CT_TYPE = "Machine Threads"


def _null():
    return win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)


def _parse_metric(size: str):
    """'M8' / 'M8x1' / 'M8x1.25' / 'M56' -> (nominale mm, passo mm | None, esplicito?)."""
    m = re.fullmatch(r"\s*[Mm](\d+(?:\.\d+)?)\s*(?:[xX]\s*(\d+(?:\.\d+)?))?\s*", str(size))
    if not m:
        return None
    d = float(m.group(1))
    if m.group(2):
        return d, float(m.group(2)), True
    key = f"M{int(d) if d == int(d) else d}"
    p = COARSE_PITCH.get(key)
    return d, (float(p) if p else None), False


def iso_external_minor_mm(d: float, p: float) -> float:
    """Diametro minore di una filettatura esterna come lo usa SolidWorks: D1 ISO (D - 1,0825 P) meno lo scostamento 6g
    (es = -(15 + 11 P) um). Misurato sui file della moka: M8 6,619 (formula 6,618), M56 49,971 (formula 49,971)."""
    return d - 1.0825 * p - (0.015 + 0.011 * p)


class MokaOperations:
    """Mixin: filettature cosmetiche, ripetizione di riempimento, corpi (elimina/inserisci/combina), lettura delle feature."""

    # ================================================================== 1. filettatura cosmetica
    def _circle_edge_info(self, edge) -> Optional[Dict]:
        """Spigolo circolare -> {center, axis, radius (m), internal (True foro / False albero / None non deducibile)}."""
        try:
            curve = self._com(edge, "GetCurve")
            if curve is None or not bool(self._com(curve, "IsCircle")):
                return None
            cp = self._com(curve, "CircleParams")
            info = {"center": [float(cp[0]), float(cp[1]), float(cp[2])], "axis": [float(cp[3]), float(cp[4]), float(cp[5])],
                    "radius": float(cp[6]), "internal": None}
        except Exception:
            return None
        try:
            faces = self._com(edge, "GetTwoAdjacentFaces2")
            for f in (faces or []):
                if f is None:
                    continue
                surf = self._com(f, "GetSurface")
                if surf is not None and bool(self._com(surf, "IsCylinder")):
                    # la normale della superficie cilindrica punta fuori dall'asse; FaceInSurfaceSense = faccia opposta
                    # alla superficie: normale uscente dal materiale verso l'asse -> foro
                    info["internal"] = bool(self._com(f, "FaceInSurfaceSense"))
                    break
        except Exception:
            pass
        return info

    def add_cosmetic_thread(self, edge_point, size: str, kind: str = "auto", depth: float = None,
                            end_condition: str = "blind", unit: str = None) -> Dict:
        """Filettatura cosmetica ISO (Machine Threads) su uno spigolo circolare scelto per coordinate."""
        try:
            doc, err = self._part()
            if err:
                return err
            end_condition = (end_condition or "blind").lower().replace("-", "_")
            if end_condition in ("upto_next", "to_next"):
                end_condition = "up_to_next"
            if end_condition not in _CT_ENDS:
                return self._result(False, f"end_condition '{end_condition}' non valida (blind | through | up_to_next)",
                                    SwErrors.swInvalidInput)
            kind = (kind or "auto").lower()
            if kind not in ("auto", "internal", "external"):
                return self._result(False, "kind deve essere auto | internal | external", SwErrors.swInvalidInput)
            parsed = _parse_metric(size)
            if parsed is None:
                return self._result(False, f"Misura '{size}' non valida: usa 'M6', 'M8x1', 'M56'...", SwErrors.swInvalidInput)
            nom, pitch, explicit = parsed
            if end_condition == "blind" and (depth is None or float(depth) <= 0):
                return self._result(False, "Con end_condition=blind serve depth > 0 (nell'unita' scelta).", SwErrors.swInvalidInput)
            self._exit_sketch(doc)
            doc.ClearSelection2(True)
            try:
                p = [self._mmu(float(c), unit) for c in edge_point]
                assert len(p) == 3
            except Exception:
                return self._result(False, f"edge_point non valido: {edge_point} (serve [x,y,z] SULLO spigolo)", SwErrors.swInvalidInput)
            edge, dist = self._find_entity(doc, "edge", p, 0.0005)
            if edge is None:
                return self._result(False, f"Nessuno spigolo entro 0,5 mm da {list(edge_point)} (piu' vicino a "
                                    f"{dist * 1000:.3f} mm). Usa list_entities(kind='edge').", SwErrors.swSelectionError)
            ci = self._circle_edge_info(edge)
            if ci is None:
                return self._result(False, "Lo spigolo scelto non e' un cerchio intero: la filettatura cosmetica richiede "
                                    "uno spigolo circolare.", SwErrors.swSelectionError)
            internal = ci["internal"]
            if kind == "internal":
                internal = True
            elif kind == "external":
                internal = False
            elif internal is None:
                return self._result(False, "Impossibile dedurre se lo spigolo e' di un foro o di un albero: passa kind=internal "
                                    "o external.", SwErrors.swInvalidInput)
            edge_d_mm = ci["radius"] * 2000.0
            warn = []
            if internal:
                dia_mm = nom
                if not (nom * 0.7 <= edge_d_mm <= nom * 1.02):
                    warn.append(f"il foro misura Ø{edge_d_mm:.3f} mm: atteso fra {nom * 0.7:.2f} (punta) e {nom} mm")
            else:
                if pitch is None:
                    return self._result(False, f"Per un albero serve il passo: scrivi la misura come '{size}x<passo>'.",
                                        SwErrors.swInvalidInput)
                dia_mm = iso_external_minor_mm(nom, pitch)
                if not (dia_mm * 0.98 <= edge_d_mm <= nom * 1.02):
                    warn.append(f"l'albero misura Ø{edge_d_mm:.3f} mm: atteso fra {dia_mm:.2f} (minore) e {nom} mm")
            depth_m = self._mmu(float(depth), unit) if depth else nom / 1000.0
            sd = self._sd(doc, 0)
            if not bool(edge.Select4(False, sd)):
                return self._result(False, "SolidWorks ha rifiutato la selezione dello spigolo.", SwErrors.swSelectionError)
            fm = doc.FeatureManager
            try:
                feat = fm.InsertCosmeticThread3(_CT_STANDARD_ISO, _CT_TYPE, size, dia_mm / 1000.0, _CT_ENDS[end_condition],
                                                depth_m, "")
            except Exception as ex:
                doc.ClearSelection2(True)
                return self._result(False, f"InsertCosmeticThread3 fallita: {ex}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            if feat is None:
                return self._result(False, "SolidWorks non ha creato la filettatura cosmetica (spigolo gia' filettato?).",
                                    SwErrors.swFeatureError)
            # standard, tipo, misura e richiamo: InsertCosmeticThread3 li ignora, si scrivono con ModifyDefinition
            base_size = size
            if explicit:
                coarse = COARSE_PITCH.get(f"M{int(nom) if nom == int(nom) else nom}")
                if coarse is not None and abs(float(coarse) - pitch) < 1e-9:
                    base_size = f"M{int(nom) if nom == int(nom) else nom}"
            fd = feat.GetDefinition
            if fd is None:
                return self._result(False, "Filettatura creata ma definizione non leggibile.", SwErrors.swFeatureError)
            fd.AccessSelections(doc, _null())
            fd.Standard = _CT_STANDARD_ISO
            fd.StandardType = _CT_TYPE
            fd.Size = base_size
            fd.ThreadCallout = f"{base_size} {_CT_TYPE}"
            ok = feat.ModifyDefinition(fd, doc, _null())
            try:
                fd.ReleaseSelectionAccess()
            except Exception:
                pass
            doc.ForceRebuild3(False)
            rd = feat.GetDefinition
            got = {
                "feature": self._com(feat, "Name"), "feature_type": self._com(feat, "GetTypeName2"),
                "standard": int(rd.Standard), "standard_type": rd.StandardType, "size": rd.Size, "callout": rd.ThreadCallout,
                "diameter": round(self._from_m(float(rd.Diameter), unit), 5),
                "diameter_kind": {2: "major", 3: "minor"}.get(int(rd.DiameterType), int(rd.DiameterType)),
                "depth": round(self._from_m(float(rd.BlindDepth), unit), 5),
                "end_condition": {v: k for k, v in _CT_ENDS.items()}.get(int(rd.EndCondition), int(rd.EndCondition)),
                "kind": "internal" if internal else "external", "unit": self._unit_name(unit),
                "edge_diameter_mm": round(edge_d_mm, 4), "diameter_mm": round(float(rd.Diameter) * 1000, 5),
            }
            if ci["internal"] is not None and ci["internal"] != internal:
                warn.append(f"kind={kind} contraddice la geometria (lo spigolo e' di un {'foro' if ci['internal'] else 'albero'}): "
                            "SolidWorks sceglie diametro maggiore/minore dallo spigolo, non da kind")
            if got["diameter_kind"] != ("major" if internal else "minor"):
                warn.append(f"SolidWorks ha usato il diametro {got['diameter_kind']}")
            if not internal:
                got["minor_diameter_formula"] = "D - 1.0825 P - (0.015 + 0.011 P) mm (ISO D1 minus 6g deviation, = SolidWorks values)"
            if warn:
                got["warnings"] = warn
            if not ok:
                return self._result(False, "ModifyDefinition ha rifiutato standard/misura della filettatura.", SwErrors.swFeatureError, got)
            if got["feature_type"] != "CosmeticThread" or got["size"] != base_size or got["standard"] != _CT_STANDARD_ISO:
                return self._result(False, "La filettatura creata non ha i valori richiesti.", SwErrors.swFeatureError, got)
            return self._result(True, f"Filettatura cosmetica {base_size} {'interna' if internal else 'esterna'}: {got['feature']} "
                                f"(Ø{got['diameter']} {got['diameter_kind']}, profondita' {got['depth']} {got['unit']}, {got['end_condition']})",
                                SwErrors.swSuccess, got)
        except Exception as e:
            logger.error(f"add_cosmetic_thread: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ================================================================== 2. ripetizione di riempimento
    _FILL_LAYOUTS = {"perforation": 3, "concentric": 0, "circular": 0, "square": 1, "polygon": 2}
    _FILL_SHAPES = {"circle": 1, "square": 2, "diamond": 3, "polygon": 4}

    def _modify_definition(self, doc, feat, props: dict):
        """ModifyDefinition di una feature con le proprieta' date (nome -> valore). -> None se ok, altrimenti il messaggio."""
        try:
            fd = feat.GetDefinition
            fd.AccessSelections(doc, _null())
            try:
                for k, v in props.items():
                    setattr(fd, k, v)
                ok = feat.ModifyDefinition(fd, doc, _null())
            finally:
                try:
                    fd.ReleaseSelectionAccess()
                except Exception:
                    pass
            doc.ForceRebuild3(False)
            return None if ok else "ModifyDefinition ha restituito False"
        except Exception as ex:
            return f"modifica della definizione fallita: {ex}"

    def _auto_fill_direction(self, doc, face_point, boundary_sketch, unit) -> bool:
        """Seleziona (marca 1) il primo lato rettilineo del confine: spigolo della faccia o segmento dello schizzo."""
        try:
            if face_point is not None:
                p = [self._mmu(float(c), unit) for c in face_point]
                face, _ = self._find_entity(doc, "face", p, 0.0005)
                for e in (self._com(face, "GetEdges") or []):
                    cv = self._com(e, "GetCurve")
                    if cv is not None and bool(self._com(cv, "IsLine")):
                        return bool(e.Select4(True, self._sd(doc, 1)))
                return False
            for seg in self._sketch_segments_of(doc, boundary_sketch):
                if int(self._com(seg, "GetType")) == 0:        # swSketchLINE
                    return bool(seg.Select4(True, self._sd(doc, 1)))
        except Exception:
            return False
        return False

    def fill_pattern(self, face_point=None, boundary_sketch: str = None, features=None, shape: str = None,
                     size: float = None, layout: str = "perforation", spacing: float = 10.0, loop_spacing: float = None,
                     count: int = None, stagger_angle: float = 60.0, margin: float = 0.0, direction=None,
                     polygon_sides: int = 6, seed_polygon_sides: int = 6, rotation: float = 0.0, seed_point=None,
                     flip_seed: bool = False, geometry_pattern: bool = False, unit: str = None) -> Dict:
        """Ripetizione di riempimento (Fill Pattern) con elemento = feature esistenti o forma predefinita tagliata."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            lay = self._FILL_LAYOUTS.get(str(layout or "perforation").lower())
            if lay is None:
                return self._result(False, "layout deve essere perforation | concentric | square | polygon", SwErrors.swInvalidInput)
            if (face_point is None) == (boundary_sketch is None):
                return self._result(False, "Indica il confine con UNO fra face_point (punto su una faccia piana) e boundary_sketch.",
                                    SwErrors.swInvalidInput)
            if features and shape:
                return self._result(False, "Usa features OPPURE shape, non entrambi.", SwErrors.swInvalidInput)
            if not features and not shape:
                return self._result(False, "Serve features (nomi delle feature da ripetere) oppure shape (circle | square | diamond | polygon).",
                                    SwErrors.swInvalidInput)
            seed_cut = 0
            if shape:
                seed_cut = self._FILL_SHAPES.get(str(shape).lower(), 0)
                if not seed_cut:
                    return self._result(False, "shape deve essere circle | square | diamond | polygon", SwErrors.swInvalidInput)
                if size is None or float(size) <= 0:
                    return self._result(False, "Con shape serve size > 0 (circle: diametro; square: lato; diamond: diagonale; "
                                        "polygon: diametro circoscritto).", SwErrors.swInvalidInput)
            if float(spacing) <= 0:
                return self._result(False, "spacing deve essere > 0", SwErrors.swInvalidInput)
            if isinstance(features, str):
                features = [features]
            for n in (features or []):
                if self._find_feature(doc, n) is None:
                    return self._result(False, f"Feature '{n}' non trovata.", SwErrors.swSelectionError)
            if count is not None and lay == 3:
                return self._result(False, "count vale per i layout concentric | square | polygon, non per perforation.", SwErrors.swInvalidInput)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            faces0 = len(self._body_entities(doc, "face"))
            seed_faces = None
            if features:
                try:
                    sf = self._find_feature(doc, features[0])
                    seed_faces = len(list(self._com(sf, "GetFaces") or []))
                except Exception:
                    seed_faces = None
            # selezioni (marche della documentazione di IFillPatternFeatureData): confine 16384, direzione 1, punto seme 3, feature 4
            doc.ClearSelection2(True)
            if face_point is not None:
                ok, info = self._select_point(doc, "face", face_point, unit, False, 16384)
                if not ok:
                    return self._result(False, f"Confine: {info.get('error')}", SwErrors.swSelectionError)
            else:
                f = self._find_feature(doc, boundary_sketch)
                if f is None or self._com(f, "GetTypeName2") != "ProfileFeature":
                    return self._result(False, f"Schizzo '{boundary_sketch}' non trovato.", SwErrors.swSelectionError)
                if not bool(f.Select2(False, 16384)):
                    return self._result(False, f"Schizzo '{boundary_sketch}' non selezionabile come confine.", SwErrors.swSelectionError)
            if direction is not None:
                ok, msg = self._select_edge_or_axis(doc, direction, unit, mark=1, append=True)
                if not ok:
                    doc.ClearSelection2(True)
                    return self._result(False, f"Direzione: {msg}", SwErrors.swSelectionError)
            else:
                # senza direzione SolidWorks rifiuta la ripetizione (misurato): si usa un lato rettilineo del confine
                if not self._auto_fill_direction(doc, face_point, boundary_sketch, unit):
                    doc.ClearSelection2(True)
                    return self._result(False, "Il confine non ha un lato rettilineo da usare come direzione: indica direction "
                                        "({\"edge\":[x,y,z]} o {\"axis\":nome}).", SwErrors.swSelectionError)
            if seed_point is not None:
                spec = {"vertex": seed_point} if isinstance(seed_point, (list, tuple)) else seed_point
                ok, msg, _ = self._select_any(doc, spec, unit, append=True, mark=3)
                if not ok:
                    doc.ClearSelection2(True)
                    return self._result(False, f"Punto seme: {msg}", SwErrors.swSelectionError)
            for n in (features or []):
                self._find_feature(doc, n).Select2(True, 4)
            fm = doc.FeatureManager
            fd = fm.CreateDefinition(105)           # swFmFillPattern
            if fd is None:
                doc.ClearSelection2(True)
                return self._result(False, "CreateDefinition(swFmFillPattern) non ha restituito nulla.", SwErrors.swFeatureError)
            by_count = count is not None and lay != 3
            fd.PatternLayoutType = lay
            fd.LayoutSpacingType = 1 if by_count else 0
            fd.InstanceSpacing = self._mmu(spacing, unit)
            fd.LoopSpacing = self._mmu(loop_spacing if loop_spacing is not None else spacing, unit)
            fd.Margins = self._mmu(margin, unit)
            fd.StaggerAngle = math.radians(float(stagger_angle))
            fd.NoOfInstances = int(count) if by_count else 1
            fd.PatternLayoutPolygonSides = int(polygon_sides)
            fd.FeaturesToPatternType = 1 if seed_cut else 0
            fd.CreateSeedCutType = seed_cut
            fd.GeometryPattern = bool(geometry_pattern)
            seed_props = {}
            if seed_cut:
                s_m = self._mmu(size, unit)
                seed_props = {"Rotation": math.radians(float(rotation)), "SeedCutFlipShapeDirection": bool(flip_seed)}
                if seed_cut == 1:
                    seed_props["Diameter"] = s_m
                elif seed_cut == 2:
                    seed_props["Dimension"] = s_m
                elif seed_cut == 3:
                    seed_props["Diagonal"] = s_m
                    seed_props["Dimension"] = s_m / math.sqrt(2.0)
                else:
                    n_s = max(3, int(seed_polygon_sides))
                    seed_props["CreateSeedCutPolygonSides"] = n_s
                    seed_props["OuterRadius"] = s_m / 2.0
                    seed_props["InnerRadius"] = s_m / 2.0 * math.cos(math.pi / n_s)
                for k, v in seed_props.items():
                    setattr(fd, k, v)
            try:
                feat = fm.CreateFeature(fd)
            except Exception as ex:
                doc.ClearSelection2(True)
                return self._result(False, f"CreateFeature fallita: {ex}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            new = self._new_features(doc, before)
            if feat is None and not [x for x in new if x["type"] != "ProfileFeature"]:
                return self._result(False, "SolidWorks non ha creato la ripetizione di riempimento: controlla che il confine sia piano, "
                                    "che l'elemento (o il punto seme) stia dentro il confine meno il margine e che spacing/size "
                                    "siano compatibili.", SwErrors.swFeatureError)
            fobj = feat if feat is not None else self._find_feature(doc, [x for x in new if x["type"] != "ProfileFeature"][0]["name"])
            seed_note = None
            if seed_props:
                # misurato: alla creazione SolidWorks ignora le misure del seme (usa i suoi 8 mm di default): si correggono con ModifyDefinition
                seed_note = self._modify_definition(doc, fobj, seed_props)
            vol = self._volume_m3(doc)
            faces1 = len(self._body_entities(doc, "face"))
            data = {"feature": self._com(feat, "Name") if feat is not None else [x for x in new if x["type"] != "ProfileFeature"][0]["name"],
                    "layout": layout, "unit": self._unit_name(unit), "spacing": spacing, "margin": margin,
                    "volume_before_mm3": round(v0 * 1e9, 4), "volume_after_mm3": round(vol * 1e9, 4),
                    "volume_delta_mm3": round((vol - v0) * 1e9, 4), "faces_added": faces1 - faces0}
            data["feature_type"] = "APattern"
            if seed_note:
                data["seed_size_warning"] = seed_note
            per = {1: 1, 2: 4, 3: 4, 4: max(3, int(seed_polygon_sides))}.get(seed_cut) if seed_cut else seed_faces
            if per:
                if seed_cut:
                    data["instances"] = int(round((faces1 - faces0) / per))
                else:
                    data["instances"] = 1 + int(round((faces1 - faces0) / per))
                data["instances_note"] = "contate dalle facce create / facce di una istanza (seme incluso)"
            try:
                fo = self._find_feature(doc, data["feature"])
                code = fo.GetErrorCode2
                code = code[0] if isinstance(code, tuple) else code
                if code:
                    data["rebuild_error_code"] = int(code)
            except Exception:
                pass
            return self._result(True, f"Ripetizione di riempimento {data['feature']}: {data.get('instances', '?')} istanze, volume "
                                f"{v0 * 1e9:.1f} -> {vol * 1e9:.1f} mm3", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"fill_pattern: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ================================================================== 4. lettura della definizione di una feature
    _FD_END = {0: "blind", 1: "through_all", 2: "up_to_next", 3: "up_to_vertex", 4: "up_to_surface", 5: "offset_from_surface",
               6: "mid_plane", 7: "up_to_body", 9: "through_all_both", 10: "up_to_selection", 11: "up_to_next"}
    _FD_LAYOUT = {0: "concentric", 1: "square", 2: "polygon", 3: "perforation"}
    _FD_SEED = {0: "none", 1: "circle", 2: "square", 3: "diamond", 4: "polygon"}
    _FD_HOLE_TYPE = {0: "counterbore", 1: "countersink", 2: "hole", 3: "pipe_tap", 4: "tap", 5: "legacy",
                     6: "counterbore_slot", 7: "countersink_slot", 8: "hole_slot"}
    _FD_REVOLVE = {0: "one_direction", 1: "mid_plane", 2: "two_directions", 3: "one_direction_360", 4: "mid_plane_360",
                   5: "two_directions_360"}
    _FD_FROM = {0: "sketch_plane", 1: "surface", 2: "vertex", 3: "offset"}

    @staticmethod
    def _gp(fd, name, *args):
        """Legge un membro di una *FeatureData (proprieta' o metodo con argomenti); None se manca o da' errore."""
        try:
            v = getattr(fd, name)
            if callable(v) and not isinstance(v, win32com.client.CDispatch):
                return v(*args)
            return v
        except Exception:
            return None

    def _obj_desc(self, o, unit=None):
        """Descrizione breve di un oggetto COM di SolidWorks (feature, faccia, spigolo, segmento...)."""
        if o is None:
            return None
        try:
            n = self._com(o, "Name")
            t = self._com(o, "GetTypeName2")
            return {"name": str(n), "type": str(t)}
        except Exception:
            pass
        try:
            return {"face_area": round(self._from_m(float(self._com(o, "GetArea")) ** 0.5, unit) ** 2, 4)}
        except Exception:
            pass
        try:
            cv = self._com(o, "GetCurve")
            return {"edge": True, "curve": "line" if bool(self._com(cv, "IsLine")) else ("circle" if bool(self._com(cv, "IsCircle")) else "curve")}
        except Exception:
            pass
        return {"object": str(type(o).__name__)}

    def _obj_list(self, arr, unit=None, limit=30):
        try:
            items = list(arr) if arr is not None else []
        except Exception:
            return []
        return [self._obj_desc(x, unit) for x in items[:limit]]

    def _fd_extrude(self, fd, unit):
        L = lambda v: None if v is None else round(self._from_m(float(v), unit), 5)
        G = lambda v: None if v is None else round(math.degrees(float(v)), 5)
        both = bool(self._gp(fd, "BothDirections"))
        out = {"kind": "extrude"}
        for fwd, key in ((True, "direction1"), (False, "direction2")):
            if not fwd and not both:
                continue
            ec = self._gp(fd, "GetEndCondition", fwd)
            row = {"end_condition": self._FD_END.get(ec, ec), "depth": L(self._gp(fd, "GetDepth", fwd)),
                   "draft_angle_deg": G(self._gp(fd, "GetDraftAngle", fwd)), "draft_outward": self._gp(fd, "GetDraftOutward", fwd),
                   "draft_while_extruding": self._gp(fd, "GetDraftWhileExtruding", fwd)}
            wall = self._gp(fd, "GetWallThickness", fwd)
            if wall:
                row["wall_thickness"] = L(wall)
            out[key] = row
        out["both_directions"] = both
        out["reverse_direction"] = self._gp(fd, "ReverseDirection")
        ft = self._gp(fd, "FromType")
        out["start"] = {"type": self._FD_FROM.get(ft, ft)}
        if ft == 3:
            out["start"]["offset"] = L(self._gp(fd, "FromOffsetDistance"))
            out["start"]["offset_reverse"] = self._gp(fd, "FromOffsetReverse")
        out["merge"] = self._gp(fd, "Merge")
        out["thin_wall_type"] = self._gp(fd, "ThinWallType")
        out["flip_side_to_cut"] = self._gp(fd, "FlipSideToCut")
        out["feature_scope"] = self._gp(fd, "FeatureScope")
        out["auto_select_bodies"] = self._gp(fd, "AutoSelect")
        out["unit"] = self._unit_name(unit)
        return out

    def _fd_revolve(self, fd, unit):
        G = lambda v: None if v is None else round(math.degrees(float(v)), 5)
        t = self._gp(fd, "Type")
        out = {"kind": "revolve", "revolve_type": self._FD_REVOLVE.get(t, t), "angle1_deg": G(self._gp(fd, "GetRevolutionAngle", True)),
               "reverse_direction": self._gp(fd, "ReverseDirection"), "merge": self._gp(fd, "Merge"),
               "thin_wall_type": self._gp(fd, "ThinWallType")}
        if t in (2, 5):
            out["angle2_deg"] = G(self._gp(fd, "GetRevolutionAngle", False))
        out["axis"] = self._obj_desc(self._gp(fd, "Axis"), unit)
        out["axis_type"] = self._gp(fd, "GetAxisType")
        return out

    def _fd_hole(self, fd, unit):
        L = lambda v: round(self._from_m(float(v), unit), 5)
        out = {"kind": "hole_wizard", "standard": self._gp(fd, "Standard"), "fastener_type": self._gp(fd, "FastenerType"),
               "size": self._gp(fd, "FastenerSize"), "hole_type": self._FD_HOLE_TYPE.get(self._gp(fd, "Type"), self._gp(fd, "Type")),
               "end_condition": self._FD_END.get(self._gp(fd, "EndCondition"), self._gp(fd, "EndCondition")),
               "reverse_direction": self._gp(fd, "ReverseDirection")}
        for k, key in (("Diameter", "diameter"), ("HoleDiameter", "hole_diameter"), ("ThruHoleDiameter", "thru_hole_diameter"),
                       ("TapDrillDiameter", "tap_drill_diameter"), ("ThreadDiameter", "thread_diameter"),
                       ("MajorDiameter", "major_diameter"), ("MinorDiameter", "minor_diameter"),
                       ("CounterBoreDiameter", "counterbore_diameter"), ("CounterSinkDiameter", "countersink_diameter"),
                       ("Depth", "depth"), ("HoleDepth", "hole_depth"), ("ThruHoleDepth", "thru_hole_depth"),
                       ("TapDrillDepth", "tap_drill_depth"), ("ThreadDepth", "thread_depth"),
                       ("CounterBoreDepth", "counterbore_depth")):
            v = self._gp(fd, k)
            if isinstance(v, float) and abs(v) > 0:
                out[key] = L(v)
        for k, key in (("CounterSinkAngle", "countersink_angle_deg"), ("DrillAngle", "drill_angle_deg"), ("ThreadAngle", "thread_angle_deg")):
            v = self._gp(fd, k)
            if isinstance(v, float) and abs(v) > 0:
                out[key] = round(math.degrees(v), 4)
        out["cosmetic_thread_type"] = self._gp(fd, "CosmeticThreadType")
        out["sketch_points"] = self._gp(fd, "GetSketchPointCount")
        out["unit"] = self._unit_name(unit)
        return out

    def _fd_linear(self, fd, unit):
        L = lambda v: None if v is None else round(self._from_m(float(v), unit), 5)
        out = {"kind": "linear_pattern", "direction1": {"instances": self._gp(fd, "D1TotalInstances"), "spacing": L(self._gp(fd, "D1Spacing")),
                                                        "reverse": self._gp(fd, "D1ReverseDirection"),
                                                        "reference": self._obj_desc(self._gp(fd, "D1Axis"), unit)}}
        n2 = self._gp(fd, "D2TotalInstances")
        if n2 and n2 > 1:
            out["direction2"] = {"instances": n2, "spacing": L(self._gp(fd, "D2Spacing")), "reverse": self._gp(fd, "D2ReverseDirection"),
                                 "reference": self._obj_desc(self._gp(fd, "D2Axis"), unit), "seed_only": self._gp(fd, "D2PatternSeedOnly")}
        out["geometry_pattern"] = self._gp(fd, "GeometryPattern")
        out["vary_sketch"] = self._gp(fd, "VarySketch")
        out["patterned_features"] = self._obj_list(self._gp(fd, "PatternFeatureArray"), unit)
        out["patterned_faces"] = len(list(self._gp(fd, "PatternFaceArray") or []))
        out["patterned_bodies"] = len(list(self._gp(fd, "PatternBodyArray") or []))
        out["unit"] = self._unit_name(unit)
        return out

    def _fd_circular(self, fd, unit):
        G = lambda v: None if v is None else round(math.degrees(float(v)), 5)
        out = {"kind": "circular_pattern", "instances": self._gp(fd, "TotalInstances"), "spacing_deg": G(self._gp(fd, "Spacing")),
               "equal_spacing": self._gp(fd, "EqualSpacing"), "reverse_direction": self._gp(fd, "ReverseDirection"),
               "axis": self._obj_desc(self._gp(fd, "Axis"), unit), "geometry_pattern": self._gp(fd, "GeometryPattern"),
               "vary_sketch": self._gp(fd, "VarySketch")}
        if self._gp(fd, "Direction2"):
            out["direction2"] = {"instances": self._gp(fd, "TotalInstances2"), "spacing_deg": G(self._gp(fd, "Spacing2")),
                                 "symmetric": self._gp(fd, "Symmetric")}
        out["patterned_features"] = self._obj_list(self._gp(fd, "PatternFeatureArray"), unit)
        out["patterned_faces"] = len(list(self._gp(fd, "PatternFaceArray") or []))
        out["patterned_bodies"] = len(list(self._gp(fd, "PatternBodyArray") or []))
        return out

    def _fd_fill(self, fd, unit):
        L = lambda v: None if v is None else round(self._from_m(float(v), unit), 5)
        G = lambda v: None if v is None else round(math.degrees(float(v)), 5)
        seed = self._gp(fd, "CreateSeedCutType")
        out = {"kind": "fill_pattern", "layout": self._FD_LAYOUT.get(self._gp(fd, "PatternLayoutType"), self._gp(fd, "PatternLayoutType")),
               "spacing_by": "instances" if self._gp(fd, "LayoutSpacingType") == 1 else "target_spacing",
               "instance_spacing": L(self._gp(fd, "InstanceSpacing")), "loop_spacing": L(self._gp(fd, "LoopSpacing")),
               "stagger_angle_deg": G(self._gp(fd, "StaggerAngle")), "margin": L(self._gp(fd, "Margins")),
               "instances_per_loop": self._gp(fd, "NoOfInstances"), "layout_polygon_sides": self._gp(fd, "PatternLayoutPolygonSides"),
               "pattern_of": "seed_cut" if self._gp(fd, "FeaturesToPatternType") == 1 else "features",
               "geometry_pattern": self._gp(fd, "GeometryPattern"),
               "boundary": self._obj_list(self._gp(fd, "PatternFillBoundaryArray"), unit),
               "patterned_features": self._obj_list(self._gp(fd, "PatternFeatureArray"), unit), "unit": self._unit_name(unit)}
        if self._gp(fd, "FeaturesToPatternType") == 1:
            seed_row = {"shape": self._FD_SEED.get(seed, seed), "rotation_deg": G(self._gp(fd, "Rotation"))}
            if seed == 1:
                seed_row["diameter"] = L(self._gp(fd, "Diameter"))
            elif seed == 2:
                seed_row["side"] = L(self._gp(fd, "Dimension"))
            elif seed == 3:
                seed_row["diagonal"] = L(self._gp(fd, "Diagonal"))
                seed_row["side"] = L(self._gp(fd, "Dimension"))
            elif seed == 4:
                seed_row.update({"sides": self._gp(fd, "CreateSeedCutPolygonSides"), "outer_radius": L(self._gp(fd, "OuterRadius")),
                                 "inner_radius": L(self._gp(fd, "InnerRadius"))})
            out["seed_cut"] = seed_row
        return out

    def _fd_cosmetic(self, fd, unit):
        dk = self._gp(fd, "DiameterType")
        return {"kind": "cosmetic_thread", "standard": self._gp(fd, "Standard"), "standard_type": self._gp(fd, "StandardType"),
                "size": self._gp(fd, "Size"), "callout": self._gp(fd, "ThreadCallout"),
                "diameter": round(self._from_m(float(self._gp(fd, "Diameter") or 0.0), unit), 5),
                "diameter_kind": {1: "conical_offset", 2: "major", 3: "minor"}.get(dk, dk),
                "depth": round(self._from_m(float(self._gp(fd, "BlindDepth") or 0.0), unit), 5),
                "end_condition": {0: "blind", 1: "up_to_next", 2: "through"}.get(self._gp(fd, "EndCondition"), self._gp(fd, "EndCondition")),
                "edge": self._obj_desc(self._gp(fd, "Edge"), unit), "unit": self._unit_name(unit)}

    def _fd_fillet(self, fd, unit):
        L = lambda v: None if v is None else round(self._from_m(float(v), unit), 5)
        t = self._gp(fd, "Type")
        out = {"kind": "fillet", "fillet_type": {0: "constant_radius", 1: "variable_radius", 2: "face", 3: "full_round"}.get(t, t),
               "radius": L(self._gp(fd, "DefaultRadius")), "multiple_radius": self._gp(fd, "IsMultipleRadius"),
               "edges": self._gp(fd, "GetEdgeCount"), "propagate_to_tangent_faces": self._gp(fd, "PropagateToTangentFaces"),
               "round_corners": self._gp(fd, "RoundCorners"), "overflow_type": self._gp(fd, "OverflowType"), "unit": self._unit_name(unit)}
        if self._gp(fd, "AsymmetricFillet"):
            out["asymmetric_distance"] = L(self._gp(fd, "DefaultDistance"))
        n = self._gp(fd, "FilletItemsCount")
        if self._gp(fd, "IsMultipleRadius") and n:
            radii = []
            for i in range(int(n)):
                item = self._gp(fd, "GetFilletItemAtIndex", i)
                r = self._gp(fd, "GetRadius", item) if item is not None else None
                radii.append(L(r))
            out["radii"] = radii
        return out

    def _fd_chamfer(self, fd, unit):
        L = lambda v: None if v is None else round(self._from_m(float(v), unit), 5)
        t = self._gp(fd, "Type")
        out = {"kind": "chamfer", "chamfer_type": {1: "angle_distance", 2: "distance_distance", 3: "vertex", 16: "equal_distance"}.get(t, t),
               "distance1": L(self._gp(fd, "GetEdgeChamferDistance", 0)), "distance2": L(self._gp(fd, "GetEdgeChamferDistance", 1)),
               "angle_deg": None, "equal_distance": self._gp(fd, "EqualDistance"), "edges": self._gp(fd, "GetEdgeCount"),
               "faces": self._gp(fd, "GetFaceCount"), "tangent_propagation": self._gp(fd, "TangentPropagation"), "unit": self._unit_name(unit)}
        a = self._gp(fd, "EdgeChamferAngle")
        if a is not None:
            out["angle_deg"] = round(math.degrees(float(a)), 5)
        return out

    def _fd_shell(self, fd, unit):
        L = lambda v: None if v is None else round(self._from_m(float(v), unit), 5)
        out = {"kind": "shell", "thickness": L(self._gp(fd, "Thickness")), "outward": self._gp(fd, "Direction"),
               "faces_removed": self._gp(fd, "FacesRemovedCount"), "unit": self._unit_name(unit)}
        n = self._gp(fd, "GetMultipleThicknessFacesCount")
        if n:
            out["multi_thickness"] = [L(self._gp(fd, "GetMultipleThicknessAtIndex", i)) for i in range(int(n))]
        return out

    def _fd_refplane(self, feat, fd, unit):
        L = lambda v: round(self._from_m(float(v), unit), 5)
        out = {"kind": "reference_plane", "unit": self._unit_name(unit)}
        t = self._gp(fd, "Type")
        out["constraints_mask"] = t
        d = self._gp(fd, "Distance")
        if d:
            out["distance"] = L(d)
        a = self._gp(fd, "Angle")
        if a:
            out["angle_deg"] = round(math.degrees(float(a)), 5)
        try:
            rp = self._com(feat, "GetSpecificFeature2")
            tr = self._com(rp, "Transform")
            ad = list(self._com(tr, "ArrayData"))
            # MathTransform: 9 della rotazione (righe = assi X, Y, Z del piano), poi traslazione (m), poi scala
            xa, za = ad[0:3], ad[6:9]      # misurato: gli assi sono le RIGHE della matrice (piano frontale spostato in X: normale [1,0,0])
            out["origin"] = [L(ad[9]), L(ad[10]), L(ad[11])]
            out["normal"] = [round(c + 0.0, 6) for c in za]
            out["x_axis"] = [round(c + 0.0, 6) for c in xa]
        except Exception:
            pass
        return out

    def _fd_loft(self, fd, unit):
        out = {"kind": "loft", "profiles": self._obj_list(self._gp(fd, "Profiles"), unit),
               "guides": self._obj_list(self._gp(fd, "GuideCurves"), unit), "start_tangency": self._gp(fd, "StartTangencyType"),
               "end_tangency": self._gp(fd, "EndTangencyType"), "closed": self._gp(fd, "Close"), "merge": self._gp(fd, "Merge"),
               "thin_wall_type": self._gp(fd, "ThinWallType"), "centerline": self._obj_desc(self._gp(fd, "Centerline"), unit)}
        out["profile_count"] = self._gp(fd, "GetProfileCount")
        return out

    def _fd_sweep(self, fd, unit):
        out = {"kind": "sweep", "profile": self._obj_desc(self._gp(fd, "Profile"), unit), "path": self._obj_desc(self._gp(fd, "Path"), unit),
               "guides": self._obj_list(self._gp(fd, "GuideCurves"), unit), "merge": self._gp(fd, "Merge"),
               "twist_control": self._gp(fd, "TwistControlType"), "circular_profile": self._gp(fd, "CircularProfile"),
               "thin_wall_type": self._gp(fd, "ThinWallType"), "start_tangency": self._gp(fd, "StartTangencyType"),
               "end_tangency": self._gp(fd, "EndTangencyType"), "unit": self._unit_name(unit)}
        if out["circular_profile"]:
            out["circular_profile_diameter"] = round(self._from_m(float(self._gp(fd, "CircularProfileDiameter") or 0.0), unit), 5)
        return out

    def get_feature_definition(self, name: str, unit: str = None) -> Dict:
        """Parametri di una feature esistente (condizioni di fine, profondita', quote, riferimenti...) con genitori e figlie."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            feat = self._find_feature(doc, name)
            if feat is None:
                return self._result(False, f"Feature '{name}' non trovata. Feature: {self._names(doc)}", SwErrors.swSelectionError)
            tname = str(self._com(feat, "GetTypeName2"))
            data = {"name": str(self._com(feat, "Name")), "type": tname, "unit": self._unit_name(unit)}
            try:
                code = feat.GetErrorCode2
                code = code[0] if isinstance(code, tuple) else code
                data["rebuild_error_code"] = int(code or 0)
            except Exception:
                pass
            try:
                s = feat.IsSuppressed2(1, None)
                data["suppressed"] = bool(s[0] if isinstance(s, (tuple, list)) else s)
            except Exception:
                pass
            parents = self._obj_list(self._gp(feat, "GetParents"), unit)
            children = self._obj_list(self._gp(feat, "GetChildren"), unit)
            data["parents"] = parents
            data["children"] = children
            sk = [p["name"] for p in parents if p.get("type") == "ProfileFeature"]
            data["sketches"] = sk
            data["dimensions"] = self._sketch_dimensions(doc, data["name"], unit)
            if sk:
                data["sketch_dimensions"] = {s: self._sketch_dimensions(doc, s, unit) for s in sk}
            fd = None
            try:
                fd = feat.GetDefinition
            except Exception:
                fd = None
            params = None
            if fd is not None:
                acc = False
                try:
                    acc = bool(fd.AccessSelections(doc, _null()))
                except Exception:
                    acc = False
                try:
                    params = self._fd_params(feat, fd, tname, unit)
                finally:
                    if acc:
                        try:
                            fd.ReleaseSelectionAccess()
                        except Exception:
                            pass
            if params is None:
                data["note"] = "parametri non letti per questo tipo"
            else:
                data["definition"] = params
            kind = params["kind"] if params else tname
            return self._result(True, f"{data['name']} ({tname}): {kind}, {len(sk)} schizzi, {len(data['dimensions'])} quote",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"get_feature_definition: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def _fd_params(self, feat, fd, tname: str, unit):
        """Smista sul lettore giusto: prima per nome del tipo, poi riconoscendo i membri dell'oggetto definizione."""
        t = tname.lower()
        if t == "cosmeticthread":
            return self._fd_cosmetic(fd, unit)
        if t == "refplane":
            return self._fd_refplane(feat, fd, unit)
        if t == "hole wzd" or t == "holewzd":
            return self._fd_hole(fd, unit)
        probes = (("GetEndCondition", self._fd_extrude), ("GetRevolutionAngle", self._fd_revolve),
                  ("FastenerSize", self._fd_hole), ("D1Spacing", self._fd_linear), ("PatternLayoutType", self._fd_fill),
                  ("TotalInstances", self._fd_circular), ("BlindDepth", self._fd_cosmetic), ("DefaultRadius", self._fd_fillet),
                  ("EdgeChamferAngle", self._fd_chamfer), ("Thickness", self._fd_shell), ("GetProfileCount", self._fd_loft),
                  ("Profile", self._fd_sweep))
        for attr, fn in probes:
            try:
                getattr(fd, attr)
            except Exception:
                continue
            return fn(fd, unit)
        return None

    # ================================================================== 3. corpi
    def _all_bodies(self, doc) -> list:
        """Tutti i corpi del pezzo (solidi e di superficie), nell'ordine di SolidWorks."""
        try:
            b = doc.GetBodies2(-1, False)       # swAllBodies
            return list(b) if b else []
        except Exception:
            return []

    def _body_row(self, body, idx: int, unit) -> Dict:
        row = {"index": idx}
        try:
            row["name"] = str(self._com(body, "Name"))
        except Exception:
            row["name"] = ""
        try:
            t = int(self._com(body, "GetType"))
        except Exception:
            t = -1
        row["type"] = {0: "solid", 1: "surface"}.get(t, f"other({t})")
        try:
            mp = body.GetMassProperties(1000.0)
            if mp:
                row["volume_mm3"] = round(float(mp[3]) * 1e9, 4)
                row["area_mm2"] = round(float(mp[4]) * 1e6, 4)
                row["centroid"] = [round(self._from_m(float(v), unit), 4) for v in list(mp)[0:3]]
        except Exception:
            pass
        try:
            bx = [float(v) for v in self._com(body, "GetBodyBox")]
            row["box_min"] = [round(self._from_m(v, unit), 4) for v in bx[0:3]]
            row["box_max"] = [round(self._from_m(v, unit), 4) for v in bx[3:6]]
            row["box_size"] = [round(self._from_m(bx[3 + i] - bx[i], unit), 4) for i in range(3)]
        except Exception:
            bx = None
        try:
            row["faces"] = int(self._com(body, "GetFaceCount"))
        except Exception:
            pass
        return row

    def _body_face_point(self, body, others: list):
        """Punto (m) su una faccia del corpo, lontano (> 0,1 mm) dalle facce degli altri corpi: identifica il corpo senza ambiguita'."""
        try:
            faces = [(float(self._com(f, "GetArea")), f) for f in (self._com(body, "GetFaces") or [])]
        except Exception:
            return None
        faces.sort(key=lambda t: -t[0])
        other_faces = []
        for o in others:
            other_faces.extend(self._com(o, "GetFaces") or [])
        fallback = None
        for _, f in faces:
            try:
                bx = self._com(f, "GetBox")
                c = [(bx[k] + bx[k + 3]) / 2 for k in range(3)]
                q = [float(v) for v in list(f.GetClosestPointOn(c[0], c[1], c[2]))[:3]]
            except Exception:
                continue
            if fallback is None:
                fallback = q
            try:
                if all(self._closest(of, "face", q) > 0.0001 for of in other_faces):
                    return q
            except Exception:
                return q
        return fallback

    def list_bodies(self, unit: str = None) -> Dict:
        """Corpi del pezzo: nome, tipo, volume, ingombro, facce e un punto su una faccia per selezionarli."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            allb = self._all_bodies(doc)
            rows = [self._body_row(b, i, unit) for i, b in enumerate(allb)]
            for i, b in enumerate(allb):
                pt = self._body_face_point(b, [x for j, x in enumerate(allb) if j != i])
                if pt is not None:
                    rows[i]["face_point"] = [round(self._from_m(v, unit), 4) for v in pt]
            tot = round(sum(r.get("volume_mm3", 0.0) for r in rows if r["type"] == "solid"), 4)
            return self._result(True, f"{len(rows)} corpi (volume solido totale {tot:.1f} mm3)", SwErrors.swSuccess,
                                {"bodies": rows, "count": len(rows), "solid_volume_mm3": tot, "unit": self._unit_name(unit)})
        except Exception as e:
            logger.error(f"list_bodies: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def _resolve_body(self, doc, spec, unit, bodies: list):
        """spec: nome (str), indice (int), [x,y,z] su una faccia del corpo, {"name"|"index"|"face_point": ...} -> (indice, errore)."""
        if isinstance(spec, dict):
            for k in ("name", "index", "face_point", "point"):
                if k in spec:
                    return self._resolve_body(doc, spec[k], unit, bodies)
            return None, f"specifica di corpo non riconosciuta: {spec}"
        if isinstance(spec, bool):
            return None, f"specifica di corpo non valida: {spec}"
        if isinstance(spec, int) or (isinstance(spec, float) and float(spec).is_integer()):
            i = int(spec)
            if 0 <= i < len(bodies):
                return i, None
            return None, f"indice di corpo {i} fuori dall'intervallo 0..{len(bodies) - 1}"
        if isinstance(spec, str):
            low = spec.strip().lower()
            hits = [i for i, b in enumerate(bodies) if str(self._com(b, "Name")).lower() == low]
            if len(hits) == 1:
                return hits[0], None
            if len(hits) > 1:
                return None, f"il nome '{spec}' e' di {len(hits)} corpi: usa l'indice o un punto su una faccia (list_bodies)"
            return None, f"nessun corpo chiamato '{spec}' (list_bodies: {[str(self._com(b, 'Name')) for b in bodies]})"
        if isinstance(spec, (list, tuple)) and len(spec) == 3:
            try:
                p = [self._mmu(float(c), unit) for c in spec]
            except Exception:
                return None, f"punto non valido: {spec}"
            best, bd = None, 1e9
            for i, b in enumerate(bodies):
                for f in (self._com(b, "GetFaces") or []):
                    try:
                        d = self._closest(f, "face", p)
                    except Exception:
                        continue
                    if d < bd:
                        best, bd = i, d
            if best is not None and bd <= 0.00005:
                return best, None
            return None, f"nessuna faccia di nessun corpo a meno di 0,05 mm da {list(spec)} (piu' vicina {bd * 1000:.3f} mm)"
        return None, f"specifica di corpo non valida: {spec}"

    def _resolve_bodies(self, doc, specs, unit, bodies):
        """-> (lista indici senza doppioni, errore)."""
        if specs is None or (isinstance(specs, (list, tuple)) and len(specs) == 0):
            return None, "elenco di corpi vuoto"
        if not isinstance(specs, (list, tuple)) or (len(specs) == 3 and all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in specs)):
            specs = [specs]
        out = []
        for s in specs:
            i, e = self._resolve_body(doc, s, unit, bodies)
            if e:
                return None, e
            if i not in out:
                out.append(i)
        return out, None

    def delete_body(self, bodies, keep: bool = False, unit: str = None) -> Dict:
        """Elimina i corpi indicati (keep=false) oppure mantiene solo quelli ed elimina gli altri (keep=true)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            allb = self._all_bodies(doc)
            if len(allb) < 1:
                return self._result(False, "Il pezzo non ha corpi.", SwErrors.swInvalidInput)
            idx, e = self._resolve_bodies(doc, bodies, unit, allb)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            if not keep and len(idx) >= len(allb):
                return self._result(False, "Cosi' si eliminerebbero tutti i corpi: SolidWorks lo rifiuta.", SwErrors.swInvalidInput)
            names_before = [str(self._com(b, "Name")) for b in allb]
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            sd = self._sd(doc, 0)
            for k, i in enumerate(idx):
                if not bool(allb[i].Select2(k > 0, sd)):
                    doc.ClearSelection2(True)
                    return self._result(False, f"Selezione del corpo '{names_before[i]}' rifiutata.", SwErrors.swSelectionError)
            feat = doc.FeatureManager.InsertDeleteBody2(bool(keep))
            doc.ClearSelection2(True)
            after = self._all_bodies(doc)
            exp_n = len(idx) if keep else len(allb) - len(idx)
            vol = self._volume_m3(doc)
            data = {"bodies_before": len(allb), "bodies_after": len(after), "expected_bodies_after": exp_n,
                    "selected": [names_before[i] for i in idx], "keep": bool(keep),
                    "volume_before_mm3": round(v0 * 1e9, 4), "volume_after_mm3": round(vol * 1e9, 4)}
            if feat is not None:
                data["feature"] = self._com(feat, "Name")
                data["feature_type"] = self._com(feat, "GetTypeName2")
            else:
                nf = self._new_features(doc, before)
                if nf:
                    data["feature"], data["feature_type"] = nf[0]["name"], nf[0]["type"]
            if len(after) != exp_n:
                return self._result(False, f"Corpi dopo l'operazione: {len(after)}, attesi {exp_n}.", SwErrors.swFeatureError, data)
            return self._result(True, f"{'Mantenuti' if keep else 'Eliminati'} {len(idx)} corpi: restano {len(after)} "
                                f"(volume {v0 * 1e9:.1f} -> {vol * 1e9:.1f} mm3)", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"delete_body: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def combine_bodies(self, main, tools, operation: str = "add", unit: str = None) -> Dict:
        """Combina corpi: add (unione) | subtract (principale meno strumenti) | common (intersezione)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            op = {"add": 15903, "subtract": 15902, "common": 15901}.get((operation or "add").lower())   # swBodyOperationType_e
            if op is None:
                return self._result(False, "operation deve essere add | subtract | common", SwErrors.swInvalidInput)
            allb = self._all_bodies(doc)
            mi, e = self._resolve_body(doc, main, unit, allb)
            if e:
                return self._result(False, f"Corpo principale: {e}", SwErrors.swSelectionError)
            ti, e = self._resolve_bodies(doc, tools, unit, allb)
            if e:
                return self._result(False, f"Corpi strumento: {e}", SwErrors.swSelectionError)
            ti = [i for i in ti if i != mi]
            if not ti:
                return self._result(False, "Servono altri corpi oltre al principale.", SwErrors.swInvalidInput)
            names = [str(self._com(b, "Name")) for b in allb]
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            # add e common: corpo principale nullo e TUTTI i corpi negli strumenti; subtract: principale + strumenti (misurato:
            # con i valori 0/1/2 di swCombineBodiesOperationType_e la chiamata non crea nulla, servono quelli di swBodyOperationType_e)
            if op == 15902:
                main_arg, group = allb[mi], [allb[i] for i in ti]
            else:
                main_arg, group = _null(), [allb[mi]] + [allb[i] for i in ti]
            tool_arr = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, tuple(group))
            feat = doc.FeatureManager.InsertCombineFeature(op, main_arg, tool_arr)
            doc.ClearSelection2(True)
            after = self._all_bodies(doc)
            vol = self._volume_m3(doc)
            data = {"operation": operation, "main": names[mi], "tools": [names[i] for i in ti],
                    "bodies_before": len(allb), "bodies_after": len(after),
                    "volume_before_mm3": round(v0 * 1e9, 4), "volume_after_mm3": round(vol * 1e9, 4)}
            if feat is not None:
                data["feature"] = self._com(feat, "Name")
                data["feature_type"] = self._com(feat, "GetTypeName2")
            else:
                nf = self._new_features(doc, before)
                if nf:
                    data["feature"], data["feature_type"] = nf[0]["name"], nf[0]["type"]
            if feat is None and not data.get("feature"):
                return self._result(False, "SolidWorks non ha creato la feature Combina (corpi che non si toccano? "
                                    "operazione 'common' senza intersezione?).", SwErrors.swFeatureError, data)
            return self._result(True, f"Combina {operation}: {len(allb)} -> {len(after)} corpi, volume {v0 * 1e9:.1f} -> "
                                f"{vol * 1e9:.1f} mm3", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"combine_bodies: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def insert_part(self, filepath: str, configuration: str = None, translate=None, rotate=None, rotation_origin=None,
                    link: bool = False, unit: str = None) -> Dict:
        """Inserisce un altro .sldprt come corpo/i nel pezzo attivo; poi (facoltativo) lo trasla e/o lo ruota."""
        import os
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            path = os.path.abspath(str(filepath))
            if not os.path.isfile(path):
                return self._result(False, f"File non trovato: {path}", SwErrors.swInvalidInput)
            if not path.lower().endswith(".sldprt"):
                return self._result(False, "insert_part accetta solo file .sldprt", SwErrors.swInvalidInput)
            tr = [0.0, 0.0, 0.0] if translate is None else [self._mmu(float(c), unit) for c in translate]
            rot = [0.0, 0.0, 0.0] if rotate is None else [math.radians(float(c)) for c in rotate]
            org = [0.0, 0.0, 0.0] if rotation_origin is None else [self._mmu(float(c), unit) for c in rotation_origin]
            if len(tr) != 3 or len(rot) != 3 or len(org) != 3:
                return self._result(False, "translate, rotate e rotation_origin vogliono 3 numeri [x,y,z]", SwErrors.swInvalidInput)
            moved = any(abs(c) > 0 for c in tr + rot)
            before_b = self._all_bodies(doc)
            ids_before = {self._body_key(b) for b in before_b}
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            opts = 1 | 2 | (0 if link else 512)       # solidi + superfici (+ rompi il collegamento al file)
            feat = doc.InsertPart3(path, opts, configuration or "")
            doc.ClearSelection2(True)
            after_b = self._all_bodies(doc)
            new_b = [b for b in after_b if self._body_key(b) not in ids_before]
            vol1 = self._volume_m3(doc)
            data = {"file": path, "configuration": configuration or "(active)", "bodies_before": len(before_b),
                    "bodies_after": len(after_b), "new_bodies": [str(self._com(b, "Name")) for b in new_b],
                    "volume_before_mm3": round(v0 * 1e9, 4), "volume_after_mm3": round(vol1 * 1e9, 4),
                    "volume_added_mm3": round((vol1 - v0) * 1e9, 4)}
            nf = [x for x in self._new_features(doc, before) if x["type"] != "ProfileFeature"]
            if feat is not None:
                data["feature"] = self._com(feat, "Name")
            elif nf:
                data["feature"] = nf[0]["name"]
            if feat is None and not nf:
                return self._result(False, "SolidWorks non ha inserito il pezzo (file aperto altrove in modo esclusivo? "
                                    "configurazione inesistente?).", SwErrors.swFeatureError, data)
            if moved:
                if not new_b:
                    return self._result(False, "Pezzo inserito ma non e' un corpo separato (si e' fuso con un corpo esistente): "
                                        "impossibile spostarlo. Inseriscilo in un pezzo vuoto o dopo aver reso disgiunta la zona.",
                                        SwErrors.swFeatureError, data)
                bx0 = [self._body_box(b) for b in new_b]
                steps = []
                if any(abs(c) > 0 for c in rot):
                    steps.append(("rotation", (0.0, 0.0, 0.0, 0.0, org[0], org[1], org[2], rot[2], rot[1], rot[0])))   # misurato: i parametri RotAngleX/Y/Z ruotano attorno a Z/Y/X
                if any(abs(c) > 0 for c in tr):
                    steps.append(("translation", (tr[0], tr[1], tr[2], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)))
                feats = []
                for what, args in steps:
                    # misurato: i corpi si selezionano con marca 1; traslazione e rotazione non stanno nella stessa feature
                    cur = [b for b in self._all_bodies(doc) if self._body_key(b) not in ids_before] if what == "translation" and feats else new_b
                    doc.ClearSelection2(True)
                    sd = self._sd(doc, 1)
                    for k, b in enumerate(cur):
                        b.Select2(k > 0, sd)
                    nm = self._names(doc)
                    mv = doc.FeatureManager.InsertMoveCopyBody2(*args, False, 0)
                    doc.ClearSelection2(True)
                    created = self._new_features(doc, nm)
                    if mv is None and not created:
                        return self._result(False, f"Pezzo inserito ma la {what} non e' stata creata.", SwErrors.swFeatureError, data)
                    feats.append(self._com(mv, "Name") if mv is not None else created[0]["name"])
                data["move_features"] = feats
                nb2 = [b for b in self._all_bodies(doc) if self._body_key(b) not in ids_before]
                data["box_before_move_mm"] = [[round(v * 1000, 4) for v in b] for b in bx0]
                data["box_after_move_mm"] = [[round(v * 1000, 4) for v in self._body_box(b)] for b in nb2]
            return self._result(True, f"Inserito {os.path.basename(path)}: {len(new_b)} nuovi corpi, volume {v0 * 1e9:.1f} -> "
                                f"{self._volume_m3(doc) * 1e9:.1f} mm3", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"insert_part: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def _body_box(self, body):
        try:
            return [float(v) for v in self._com(body, "GetBodyBox")]
        except Exception:
            return [0.0] * 6

    def _body_key(self, body):
        """Chiave per riconoscere un corpo prima/dopo un'operazione: nome + ingombro (m, 6 decimali)."""
        return (str(self._com(body, "Name")), tuple(round(v, 6) for v in self._body_box(body)))
