"""
Lotto FEATURE AVANZATE (raccordi avanzati, sformo con linea di divisione, cupola, avvolgi, filettatura modellata, rientranza,
flessione) (mixin). Schemi in tools_ext/features2.py. I metodi usano gli helper di ModelingBase/ModelingOperations tramite self
(_part, _select_point, _select_points, _finish, _names, _new_features, _volume_m3, _mmu, _result...).

Trappole API scoperte (SW 2026, misurate nel laboratorio ft2, vedi scripts_tmp/notes_features2.md):
 - Raccordo a facce / arrotondamento completo: FeatureFillet3 con Ftyp=2/3 e marche NON funziona (a facce ritorna None, con
   Ftyp=3 crea un raccordo semplice di tipo 2 su un solo lato). Funziona CreateDefinition(swFmFillet=1) -> Initialize(2|3) ->
   SetFaces(lista, [facce]) -> CreateFeature, SENZA AccessSelections (su una definizione nuova solleva un'eccezione COM). Le liste di
   facce sono swSimpleFilletWhichFaces_e: a facce 1 e 2; arrotondamento completo 3 (laterale 1), 4 (centrale), 5 (laterale 2).
 - Raggi multipli: Initialize(0), Edges = [spigoli], IsMultipleRadius = True, poi SetRadius(elemento, r) per ogni elemento
   (GetFilletItemAtIndex); elemento <-> spigolo si riconosce con ISldWorks.IsSame (restituisce 1). Leggere GetRadius subito dopo
   SetRadius restituisce 0 (la feature creata ha il raggio giusto).
 - Setback: FeatureFillet3 con Options=3 (propaga|raggio uniforme), SetBackDistances = distanze (m) e il VERTICE selezionato dopo gli
   spigoli (la marca e' ininfluente). SetSetbackVertices/SetSetbackVertexDistance sulla definizione sollevano eccezioni COM.
 - Sformo con linea di divisione: InsertMultiFaceDraft(angolo, inverti, EdgeDraft=True, ...) con la faccia/piano della direzione di
   estrazione selezionata con marca 1 e gli SPIGOLI della linea di divisione con marca 4 (marche 2/8/16/0 non creano nulla).
   Lo sformo a gradino NON si ottiene: IsStepDraft e' ignorato, CreateDefinition(swFmDraft=3) ritorna None e su uno sformo
   esistente StepType si scrive ma Type resta 0 (ModifyDefinition con Type=3 ritorna False).
 - Cupola: IModelDoc2.InsertDome(altezza, inverti, ellittica) vuole la faccia selezionata con marca 1 (con marca 0 non fa niente).
 - Avvolgi: IFeatureManager.InsertWrapFeature2(tipo, spessore, inverti, metodo, mesh) con lo schizzo selezionato con marca 4 e la
   faccia con marca 1. Tipi: 0 rilievo, 1 incisione, 2 tracciatura (la feature si chiama 'Emboss' in ogni caso).
 - Filettatura modellata: CreateDefinition(swFmSweepThread=87) -> InitializeThreadData -> Type ('Metric Die' esterna / 'Metric Tap'
   interna: nomi dei file in ProgramData\\SOLIDWORKS 2026\\Thread Profiles), Size ('M10x1.5'), EndCondition 0, BlindDepth, con lo
   spigolo circolare PRESELEZIONATO -> CreateFeature. La feature si chiama 'SweepThread'.
 - Flessione: InsertFlexFeature(Rot*, Tan*, Rad*, Angolo, Pivot*, Tipo, TrimSx, TrimDx, bordi) col corpo selezionato (marca 1). Rot = asse
   di flessione, Tan = direzione lungo il corpo, Rad = Tan x Rot. TRIM a 0 = nessun effetto. Tipi: 0 flessione, 1 rastremazione,
   2 torsione, 3 allungamento. Angolo: flessione/torsione in radianti (totale fra le due estremita' della zona, ogni estremita'
   ruota di meta'); rastremazione: scala delle estremita' 1 -+ Angolo/2 (zona simmetrica); allungamento: lunghezza della zona
   moltiplicata per 1 + Angolo/pi.
"""

import re
import math
import logging
import traceback
from typing import Dict

from ..constants import SwErrors
from .modeling import COARSE_PITCH
from .modeling_base import r8_array, disp_array

logger = logging.getLogger(__name__)

_WRAP_TYPES = {"emboss": 0, "engrave": 1, "scribe": 2}
_FLEX_TYPES = {"bending": 0, "tapering": 1, "twisting": 2, "stretching": 3}
_THREAD_TAP = "Metric Tap"
# Configurazioni dei profili "Metric Die" e "Metric Tap" (lette aprendo i file .SLDLFP di SOLIDWORKS 2026, 69 misure). SolidWorks NON
# rifiuta un nome sconosciuto: ripiega in silenzio su un'altra configurazione (misurato: "M10x1" invece di "M10x1.0" taglia 47 mm3
# invece di 268), per questo il nome si normalizza e si controlla qui.
_METRIC_THREAD_SIZES = set("""
M1.2x0.25 M1.4x0.3 M1.6x0.35 M2x0.4 M2.2x0.45 M2.5x0.45 M3x0.5 M3.5x0.6 M4x0.7 M5x0.8 M6x1.0 M7x1.0 M8x1.0 M8x1.25
M10x1.0 M10x1.25 M10x1.5 M12x1.25 M12x1.5 M12x1.75 M14x1.5 M14x2.0 M16x1.5 M16x2.0 M18x1.5 M18x2.0 M18x2.5 M20x1.5
M20x2.0 M20x2.5 M22x1.5 M22x2.0 M22x2.5 M24x2.0 M24x3.0 M27x2.0 M27x3.0 M30x2.0 M30x3.5 M33x2.0 M33x3.5 M36x2.0
M36x3.0 M36x4.0 M39x2.0 M39x3.0 M39x4.0 M42x3.0 M42x4.5 M45x1.5 M45x4.5 M48x3.0 M48x5.0 M52x5.0 M56x4.0 M56x5.5
M60x1.5 M60x5.5 M64x4.0 M64x6.0 M68x6.0 M72x4.0 M72x6.0 M80x4.0 M80x6.0 M90x4.0 M90x6.0 M100x4.0 M100x6.0
""".split())
_THREAD_DIE = "Metric Die"


def _unit_vec(v, name: str):
    try:
        x = [float(c) for c in v]
        assert len(x) == 3
    except Exception:
        raise ValueError(f"{name} deve essere [x,y,z]: {v}")
    n = math.sqrt(sum(c * c for c in x))
    if n < 1e-12:
        raise ValueError(f"{name} non puo' essere nullo")
    return [c / n for c in x]


def _normalize_metric_size(size: str):
    """'M10x1' -> 'M10x1.0'; 'M8' -> passo grosso ('M8x1.25'); 'm10X1.5' -> 'M10x1.5'. -> (nome|None, passo|None)."""
    m = re.fullmatch(r"\s*[Mm](\d+(?:\.\d+)?)\s*(?:[xX]\s*(\d+(?:\.\d+)?))?\s*", str(size))
    if not m:
        return None, None
    d = float(m.group(1))
    dtxt = f"{d:g}"
    if m.group(2):
        p = float(m.group(2))
    else:
        c = COARSE_PITCH.get(f"M{dtxt}")
        if c is None:
            return None, None
        p = float(c)
    ptxt = f"{p:.3f}".rstrip("0")
    if ptxt.endswith("."):
        ptxt += "0"
    return f"M{dtxt}x{ptxt}", p


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


class Features2Operations:
    """Mixin del lotto features2."""

    # ================================================================== utilita'
    def _f2_entities(self, doc, kind: str, pts, unit, what: str):
        """Punti [[x,y,z],...] (o un solo [x,y,z]) -> (entita', errore). Ogni punto deve stare SULL'entita'."""
        if pts and isinstance(pts[0], (int, float)):
            pts = [pts]
        out = []
        for pt in (pts or []):
            try:
                p = [self._mmu(float(c), unit) for c in pt]
                assert len(p) == 3
            except Exception:
                return None, f"{what}: punto non valido {pt} (serve [x,y,z])"
            ent, d = self._find_entity(doc, kind, p, 0.0005)
            if ent is None:
                return None, (f"{what}: nessun {kind} entro 0,5 mm da {list(pt)} (piu' vicino a {d * 1000:.3f} mm). "
                              f"Il punto deve stare SULL'entita' (list_entities).")
            out.append(ent)
        if not out:
            return None, f"{what}: serve almeno un punto"
        return out, None

    def _f2_create_feature(self, doc, d):
        fm = doc.FeatureManager
        try:
            return fm.CreateFeature(d)
        except Exception as ex:
            logger.warning(f"CreateFeature: {ex}")
            return None

    # ================================================================== 1. fillet_advanced
    def fillet_advanced(self, mode: str = "edges", radius: float = None, radii: list = None, edge_points: list = None,
                        face_set1: list = None, face_set2: list = None, side_face1: list = None, center_face: list = None,
                        side_face2: list = None, setback: dict = None, tangent_propagation: bool = True,
                        unit: str = None) -> Dict:
        """Raccordo avanzato: mode edges (raggi multipli per spigolo, setback ai vertici), faces (raccordo a facce) o
        full_round (arrotondamento completo). Verifica col volume prima/dopo."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            mode = (mode or "edges").lower().replace("-", "_")
            if mode not in ("edges", "faces", "full_round"):
                return self._result(False, f"mode '{mode}' non valido (edges | faces | full_round)", SwErrors.swInvalidInput)
            doc.ClearSelection2(True)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            fm = doc.FeatureManager
            extra = {"mode": mode, "unit": self._unit_name(unit)}

            if mode in ("faces", "edges") and radius is None and not radii:
                return self._result(False, "Serve radius (nell'unita' scelta)" + (" o radii" if mode == "edges" else "") + ".",
                                    SwErrors.swInvalidInput)
            if mode == "edges":
                edges, e = self._f2_entities(doc, "edge", edge_points, unit, "edge_points")
                if e:
                    return self._result(False, e, SwErrors.swSelectionError)
                if radii:
                    if len(radii) != len(edges):
                        return self._result(False, f"radii ({len(radii)}) deve avere un valore per ogni punto di edge_points "
                                            f"({len(edges)}).", SwErrors.swInvalidInput)
                    if setback:
                        return self._result(False, "setback con raggi multipli non e' supportato: usa un raggio unico (radius).",
                                            SwErrors.swInvalidInput)
                if setback:
                    return self._fillet_setback(doc, fm, edges, radius, setback, tangent_propagation, unit, v0, before, extra)
                d = fm.CreateDefinition(1)
                if d is None:
                    return self._result(False, "SolidWorks non ha creato la definizione del raccordo.", SwErrors.swFeatureError)
                d.Initialize(0)
                d.Edges = disp_array(edges)
                d.PropagateToTangentFaces = bool(tangent_propagation)
                if radii:
                    d.IsMultipleRadius = True
                    if radius is not None:
                        d.DefaultRadius = self._mmu(radius, unit)
                    for i in range(int(d.FilletItemsCount)):
                        it = d.GetFilletItemAtIndex(i)
                        for ed, r in zip(edges, radii):
                            if int(self._sw_app.IsSame(it, ed)) == 1:
                                d.SetRadius(it, self._mmu(float(r), unit))
                                break
                    extra.update({"radii": [float(r) for r in radii], "fillet_type": "multiple_radius"})
                else:
                    d.DefaultRadius = self._mmu(radius, unit)
                    extra.update({"radius": radius, "fillet_type": "constant_radius"})
                extra["edges"] = len(edges)
                feat = self._f2_create_feature(doc, d)
                label = "Raccordo avanzato (spigoli)"
            elif mode == "faces":
                s1, e = self._f2_entities(doc, "face", face_set1, unit, "face_set1")
                if e:
                    return self._result(False, e, SwErrors.swSelectionError)
                s2, e = self._f2_entities(doc, "face", face_set2, unit, "face_set2")
                if e:
                    return self._result(False, e, SwErrors.swSelectionError)
                d = fm.CreateDefinition(1)
                if d is None:
                    return self._result(False, "SolidWorks non ha creato la definizione del raccordo.", SwErrors.swFeatureError)
                d.Initialize(2)
                d.SetFaces(1, disp_array(s1))
                d.SetFaces(2, disp_array(s2))
                d.DefaultRadius = self._mmu(radius, unit)
                extra.update({"radius": radius, "fillet_type": "face", "faces_set1": len(s1), "faces_set2": len(s2)})
                feat = self._f2_create_feature(doc, d)
                label = "Raccordo a facce"
            else:
                a, e = self._f2_entities(doc, "face", side_face1, unit, "side_face1")
                if e:
                    return self._result(False, e, SwErrors.swSelectionError)
                c, e = self._f2_entities(doc, "face", center_face, unit, "center_face")
                if e:
                    return self._result(False, e, SwErrors.swSelectionError)
                b, e = self._f2_entities(doc, "face", side_face2, unit, "side_face2")
                if e:
                    return self._result(False, e, SwErrors.swSelectionError)
                feat = None
                for swapped in (False, True):
                    d = fm.CreateDefinition(1)
                    if d is None:
                        return self._result(False, "SolidWorks non ha creato la definizione del raccordo.", SwErrors.swFeatureError)
                    d.Initialize(3)
                    d.SetFaces(3, disp_array(b if swapped else a))
                    d.SetFaces(4, disp_array(c))
                    d.SetFaces(5, disp_array(a if swapped else b))
                    d.DefaultRadius = self._mmu(radius, unit) if radius else 0.001
                    feat = self._f2_create_feature(doc, d)
                    if feat is not None or self._new_features(doc, before):
                        extra["sides_swapped"] = swapped
                        break
                extra.update({"fillet_type": "full_round", "faces_side1": len(a), "faces_center": len(c), "faces_side2": len(b)})
                label = "Raccordo ad arrotondamento completo"
            doc.ClearSelection2(True)
            res = self._finish(doc, label, feat, v0, before, extra, require_volume_change=True)
            return res
        except Exception as e:
            logger.error(f"fillet_advanced: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def _fillet_setback(self, doc, fm, edges, radius, setback, tangent_propagation, unit, v0, before, extra):
        """Raccordo con setback ai vertici: FeatureFillet3 con SetBackDistances, spigoli e poi il vertice selezionati."""
        if radius is None:
            return self._result(False, "Il setback richiede radius (raggio unico).", SwErrors.swInvalidInput)
        try:
            vtx = setback["vertex"]
            dists = [float(x) for x in setback["distances"]]
        except Exception:
            return self._result(False, 'setback = {"vertex":[x,y,z], "distances":[d1,d2,d3]} (una distanza per spigolo del vertice)',
                                SwErrors.swInvalidInput)
        doc.ClearSelection2(True)
        sd = self._sd(doc, 0)
        for i, ed in enumerate(edges):
            if not bool(ed.Select4(i > 0, sd)):
                return self._result(False, "SolidWorks ha rifiutato la selezione di uno spigolo.", SwErrors.swSelectionError)
        ok, info = self._select_point(doc, "vertex", vtx, unit, True, 0)
        if not ok:
            return self._result(False, "setback.vertex: " + info.get("error", ""), SwErrors.swSelectionError)
        r = self._mmu(radius, unit)
        opts = 2 | (1 if tangent_propagation else 0)
        try:
            feat = fm.FeatureFillet3(opts, r, r, 0, 0, 0, 0, None, None, None, r8_array([self._mmu(x, unit) for x in dists]),
                                     None, None, None)
        except Exception as ex:
            return self._result(False, f"FeatureFillet3 con setback fallita: {ex}", SwErrors.swFeatureError)
        doc.ClearSelection2(True)
        extra.update({"radius": radius, "fillet_type": "setback", "edges": len(edges), "setback_vertex": list(vtx),
                      "setback_distances": dists})
        return self._finish(doc, "Raccordo con setback", feat, v0, before, extra, require_volume_change=True)

    # ================================================================== 2. draft_advanced
    def draft_advanced(self, direction=None, edge_points: list = None, angle: float = 5.0, flip: bool = False,
                       propagate_tangent: bool = False, unit: str = None) -> Dict:
        """Sformo con linea di divisione (parting line): direzione di estrazione (faccia o piano) + spigoli della linea."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            if direction is None or not edge_points:
                return self._result(False, 'Servono direction ({"face":[x,y,z]} o {"plane":nome}) ed edge_points '
                                    "(spigoli della linea di divisione).", SwErrors.swInvalidInput)
            if abs(float(angle)) < 1e-9:
                return self._result(False, "angle deve essere diverso da 0 (gradi).", SwErrors.swInvalidInput)
            doc.ClearSelection2(True)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            ok, msg, desc = self._select_any(doc, direction, unit, False, 1)
            if not ok:
                return self._result(False, f"direction: {msg or 'selezione rifiutata'}", SwErrors.swSelectionError)
            ok, msg = self._select_points(doc, "edge", edge_points, unit, mark=4, append_first=True)
            if not ok:
                return self._result(False, f"edge_points: {msg}", SwErrors.swSelectionError)
            fm = doc.FeatureManager
            try:
                feat = fm.InsertMultiFaceDraft(math.radians(float(angle)), bool(flip), True, 1 if propagate_tangent else 0, False, False)
            except Exception as ex:
                return self._result(False, f"Sformo con linea di divisione fallito: {ex}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            return self._finish(doc, "Sformo con linea di divisione", feat, v0, before,
                                {"mode": "parting_line", "angle": angle, "flip": bool(flip), "edges": len(edge_points),
                                 "direction": desc}, require_volume_change=True)
        except Exception as e:
            logger.error(f"draft_advanced: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ================================================================== 3. dome
    def dome(self, face_point: list, height: float, reverse: bool = False, elliptical: bool = False, unit: str = None) -> Dict:
        """Cupola su una faccia (IModelDoc2.InsertDome), faccia scelta da un punto SULLA faccia."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            if height is None or float(height) <= 0:
                return self._result(False, "height deve essere > 0 (nell'unita' scelta); per una rientranza usa reverse=true.",
                                    SwErrors.swInvalidInput)
            doc.ClearSelection2(True)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            ok, info = self._select_point(doc, "face", face_point, unit, False, 1)
            if not ok:
                return self._result(False, "face_point: " + info.get("error", ""), SwErrors.swSelectionError)
            try:
                doc.InsertDome(self._mmu(float(height), unit), bool(reverse), bool(elliptical))
            except Exception as ex:
                return self._result(False, f"Cupola fallita: {ex}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            return self._finish(doc, "Cupola", None, v0, before,
                                {"height": height, "reverse": bool(reverse), "elliptical": bool(elliptical),
                                 "unit": self._unit_name(unit)}, require_volume_change=True)
        except Exception as e:
            logger.error(f"dome: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ================================================================== 4. wrap_feature
    def wrap_feature(self, face_point: list, sketch: str = None, mode: str = "engrave", depth: float = 1.0, reverse: bool = False,
                     method: str = "analytical", unit: str = None) -> Dict:
        """Avvolgi uno schizzo su una faccia: emboss (rilievo), engrave (incisione) o scribe (tracciatura)."""
        try:
            doc, err = self._part()
            if err:
                return err
            mode = (mode or "engrave").lower()
            if mode not in _WRAP_TYPES:
                return self._result(False, f"mode '{mode}' non valido (emboss | engrave | scribe)", SwErrors.swInvalidInput)
            method_l = (method or "analytical").lower()
            if method_l not in ("analytical", "spline"):
                return self._result(False, "method deve essere analytical | spline", SwErrors.swInvalidInput)
            sk_name, e = self._resolve_sketch(doc, sketch)
            if e:
                return e
            if mode != "scribe" and (depth is None or float(depth) <= 0):
                return self._result(False, "depth deve essere > 0 (nell'unita' scelta) per emboss/engrave.", SwErrors.swInvalidInput)
            doc.ClearSelection2(True)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            if not self._select_feature(doc, sk_name, False, 4):
                return self._result(False, f"Schizzo '{sk_name}' non selezionabile.", SwErrors.swSelectionError)
            ok, info = self._select_point(doc, "face", face_point, unit, True, 1)
            if not ok:
                return self._result(False, "face_point: " + info.get("error", ""), SwErrors.swSelectionError)
            fm = doc.FeatureManager
            th = self._mmu(float(depth), unit) if mode != "scribe" else 0.001      # la tracciatura ignora lo spessore ma con 0 non crea nulla
            faces0 = len(self._body_entities(doc, "face"))
            try:
                feat = fm.InsertWrapFeature2(_WRAP_TYPES[mode], th, bool(reverse), 0 if method_l == "analytical" else 1, 0)
            except Exception as ex:
                return self._result(False, f"Avvolgi fallito: {ex}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            faces1 = len(self._body_entities(doc, "face"))
            res = self._finish(doc, "Avvolgi", feat, v0, before,
                               {"mode": mode, "sketch": sk_name, "depth": depth if mode != "scribe" else None, "method": method_l,
                                "reverse": bool(reverse), "unit": self._unit_name(unit), "faces_before": faces0, "faces_after": faces1},
                               require_volume_change=(mode != "scribe"))
            if mode == "scribe" and res.get("success") and faces1 <= faces0:
                return self._result(False, "Tracciatura creata ma la faccia non e' stata divisa (controlla che lo schizzo stia sulla "
                                    "faccia).", SwErrors.swFeatureError, res.get("data"))
            return res
        except Exception as e:
            logger.error(f"wrap_feature: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ================================================================== 5. thread_feature
    def thread_feature(self, edge_point: list, size: str, length: float, profile: str = "auto", method: str = "cut",
                       right_handed: bool = True, reverse: bool = False, start_offset: float = None,
                       start_angle: float = None, unit: str = None) -> Dict:
        """Filettatura modellata (Inserisci > Feature > Filettatura) su uno spigolo circolare, profilo di libreria."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            method_l = (method or "cut").lower()
            if method_l not in ("cut", "extrude"):
                return self._result(False, "method deve essere cut | extrude", SwErrors.swInvalidInput)
            if length is None or float(length) <= 0:
                return self._result(False, "length deve essere > 0 (nell'unita' scelta).", SwErrors.swInvalidInput)
            doc.ClearSelection2(True)
            edges, e = self._f2_entities(doc, "edge", edge_point, unit, "edge_point")
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            edge = edges[0]
            ci = self._circle_edge_info(edge)
            if ci is None:
                return self._result(False, "Lo spigolo scelto non e' un cerchio intero: serve uno spigolo circolare di un "
                                    "cilindro o di un foro.", SwErrors.swSelectionError)
            prof = profile
            if not prof or str(prof).lower() == "auto":
                prof = _THREAD_TAP if ci["internal"] else _THREAD_DIE
            size_name, pitch_mm = str(size), None
            if prof in (_THREAD_DIE, _THREAD_TAP):
                size_name, pitch_mm = _normalize_metric_size(size)
                if size_name is None or size_name not in _METRIC_THREAD_SIZES:
                    near = ""
                    mm = re.match(r"\s*[Mm](\d+(?:\.\d+)?)", str(size))
                    if mm:
                        near = " Misure con quel diametro: " + ", ".join(sorted(
                            x for x in _METRIC_THREAD_SIZES if x.startswith(f"M{float(mm.group(1)):g}x"))) + "."
                    return self._result(False, f"size '{size}' non esiste nel profilo '{prof}' (nomi tipo 'M10x1.5', passo con "
                                        f"decimale: 'M10x1.0').{near}", SwErrors.swInvalidInput)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            fm = doc.FeatureManager
            d = fm.CreateDefinition(87)
            if d is None:
                return self._result(False, "SolidWorks non ha creato la definizione della filettatura.", SwErrors.swFeatureError)
            d.InitializeThreadData()
            d.Type = prof
            d.Size = size_name
            d.EndCondition = 0
            d.BlindDepth = self._mmu(float(length), unit)
            d.ThreadMethod = 0 if method_l == "cut" else 1
            d.RightHanded = bool(right_handed)
            d.ReverseDirection = bool(reverse)
            if start_offset:
                d.Offset = True
                d.OffsetDistance = self._mmu(float(start_offset), unit)
            if start_angle:
                d.ThreadStartAngle = math.radians(float(start_angle))
            if not bool(edge.Select4(False, self._sd(doc, 0))):
                return self._result(False, "SolidWorks ha rifiutato la selezione dello spigolo.", SwErrors.swSelectionError)
            feat = self._f2_create_feature(doc, d)
            doc.ClearSelection2(True)
            if feat is None and not self._new_features(doc, before):
                return self._result(False, f"Filettatura non creata: controlla profile '{prof}' (file in ProgramData\\SOLIDWORKS "
                                    f"<versione>\\Thread Profiles) e size '{size}' (nome di una configurazione del profilo, es. M10x1.5).",
                                    SwErrors.swFeatureError)
            extra = {"profile": prof, "size_requested": size, "size_used": size_name, "length": length, "method": method_l, "right_handed": bool(right_handed),
                     "reverse": bool(reverse), "unit": self._unit_name(unit), "edge_diameter_mm": round(ci["radius"] * 2000.0, 4),
                     "kind": "internal" if ci["internal"] else "external"}
            try:
                rd = (feat or self._find_feature(doc, self._new_features(doc, before)[0]["name"])).GetDefinition
                extra.update({"size": rd.Size, "profile_file": rd.Type, "depth": round(self._from_m(float(rd.BlindDepth), unit), 5),
                              "end_condition": int(rd.EndCondition)})
            except Exception:
                pass
            if pitch_mm is not None:
                extra["pitch_mm"] = pitch_mm
                extra["pitch_note"] = ("pitch from the size name; IThreadFeatureData.Pitch is NOT updated by SolidWorks (it keeps the "
                                       "10 mm default), the real pitch comes from the profile configuration")
            return self._finish(doc, "Filettatura", feat, v0, before, extra, require_volume_change=True)
        except Exception as e:
            logger.error(f"thread_feature: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ================================================================== 7. flex_feature
    def _f2_pick_body(self, doc, body, unit=None):
        """body: None (unico corpo solido) | indice | [x,y,z] SU una faccia del corpo -> (Body2, errore)."""
        bodies = self._bodies(doc)
        if not bodies:
            return None, "Nessun corpo solido nel pezzo."
        if body is None:
            if len(bodies) > 1:
                return None, f"Il pezzo ha {len(bodies)} corpi: indica body (indice 0.. o punto [x,y,z] su una sua faccia)."
            return bodies[0], None
        if isinstance(body, (int, float)) and not isinstance(body, bool):
            i = int(body)
            if 0 <= i < len(bodies):
                return bodies[i], None
            return None, f"body {i} fuori campo (0..{len(bodies) - 1})"
        if isinstance(body, (list, tuple)) and len(body) == 3:
            ent, d = self._find_entity(doc, "face", [self._mmu(float(c), unit) for c in body], 0.0005)
            if ent is None:
                return None, f"body: nessuna faccia entro 0,5 mm da {list(body)}."
            return ent.GetBody, None
        return None, f"body non valido: {body}"

    def flex_feature(self, body=None, mode: str = "bending", amount: float = 30.0, pivot: list = None, axis: list = None,
                     bend_axis: list = None, trim_before: float = None, trim_after: float = None, hard_edges: bool = False,
                     unit: str = None) -> Dict:
        """Flessione (Inserisci > Feature > Flessione): bending, tapering, twisting o stretching di un corpo."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            mode = (mode or "bending").lower()
            if mode not in _FLEX_TYPES:
                return self._result(False, f"mode '{mode}' non valido (bending | tapering | twisting | stretching)", SwErrors.swInvalidInput)
            bd, e = self._f2_pick_body(doc, body, unit)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            try:
                tan = _unit_vec(axis if axis is not None else [0, 0, 1], "axis")
                if bend_axis is None:
                    k = min(range(3), key=lambda i: abs(tan[i]))
                    helper = [0.0, 0.0, 0.0]
                    helper[k] = 1.0
                    rot = _unit_vec(_cross(tan, helper), "bend_axis")
                else:
                    rot = _unit_vec(bend_axis, "bend_axis")
            except ValueError as ve:
                return self._result(False, str(ve), SwErrors.swInvalidInput)
            if abs(sum(a * b for a, b in zip(tan, rot))) > 1e-6:
                return self._result(False, "axis e bend_axis devono essere perpendicolari.", SwErrors.swInvalidInput)
            rad = _cross(tan, rot)
            box0 = [float(x) for x in bd.GetBodyBox()]
            xs = [(box0[0], box0[3]), (box0[1], box0[4]), (box0[2], box0[5])]
            allpts = [[a, b, c] for a in xs[0] for b in xs[1] for c in xs[2]]
            if pivot is None:
                piv = [(box0[i] + box0[i + 3]) / 2 for i in range(3)]
            else:
                piv = [self._mmu(float(c), unit) for c in pivot]
            proj = [sum((p[i] - piv[i]) * tan[i] for i in range(3)) for p in allpts]
            lt = -min(proj) if trim_before is None else self._mmu(float(trim_before), unit)
            rt = max(proj) if trim_after is None else self._mmu(float(trim_after), unit)
            if lt <= 0 or rt <= 0:
                return self._result(False, "Il pivot deve stare dentro il corpo lungo axis (o fornisci trim_before e trim_after > 0).",
                                    SwErrors.swInvalidInput)
            if mode in ("bending", "twisting"):
                ang = math.radians(float(amount))
            elif mode == "stretching":
                if float(amount) <= 0:
                    return self._result(False, "stretching: amount e' il fattore di lunghezza della zona (> 0, es. 1.25).",
                                        SwErrors.swInvalidInput)
                ang = math.pi * (float(amount) - 1.0)
            else:
                ang = float(amount)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            if not bool(bd.Select2(False, self._sd(doc, 1))):
                return self._result(False, "SolidWorks ha rifiutato la selezione del corpo.", SwErrors.swSelectionError)
            fm = doc.FeatureManager
            try:
                feat = fm.InsertFlexFeature(rot[0], rot[1], rot[2], tan[0], tan[1], tan[2], rad[0], rad[1], rad[2], ang,
                                            piv[0], piv[1], piv[2], _FLEX_TYPES[mode], lt, rt, bool(hard_edges))
            except Exception as ex:
                return self._result(False, f"Flessione fallita: {ex}", SwErrors.swFeatureError)
            doc.ClearSelection2(True)
            bd2 = self._bodies(doc)
            box1 = None
            try:
                if bd2:
                    box1 = [float(x) for x in bd2[0].GetBodyBox()]
            except Exception:
                box1 = None
            extra = {"mode": mode, "amount": amount, "pivot": [round(self._from_m(c, unit), 5) for c in piv],
                     "axis": [round(c, 5) for c in tan], "bend_axis": [round(c, 5) for c in rot],
                     "trim_before": round(self._from_m(lt, unit), 5), "trim_after": round(self._from_m(rt, unit), 5),
                     "volume_before_mm3": round(v0 * 1e9, 3), "unit": self._unit_name(unit),
                     "bbox_before": [round(self._from_m(c, unit), 4) for c in box0]}
            if box1:
                extra["bbox_after"] = [round(self._from_m(c, unit), 4) for c in box1]
            v1 = self._volume_m3(doc)
            if v0 > 0:
                extra["volume_ratio"] = round(v1 / v0, 6)
            return self._finish(doc, "Flessione", feat, v0, before, extra)
        except Exception as e:
            logger.error(f"flex_feature: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)
