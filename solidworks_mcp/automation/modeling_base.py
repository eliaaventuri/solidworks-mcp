"""
Modeling base helpers (mixin)
-----------------------------
Selezione per coordinate di facce / spigoli / vertici, ricerca feature, volume, chiusura schizzi.
Usato da sketch_constraints.py e modeling.py.

Trappole SW 2026 (late binding):
 - SelectByID2(..., "FACE"/"EDGE") usa un raggio nella direzione della vista: poco affidabile con la finestra
   nascosta -> qui la selezione e' GEOMETRICA: si cerca l'entita' il cui punto piu' vicino
   (GetClosestPointOn) dista meno della tolleranza dal punto dato, poi Select4 con un SelectData (Mark).
 - I membri senza argomenti sono proprieta': usare self._com().
"""

import math
import logging
from typing import Optional, Dict, List, Tuple, Any

import win32com.client
import pythoncom

from ..constants import SwErrors
from ..utils.sw_lang import std_plane_index

logger = logging.getLogger(__name__)

# swSelectType_e
SEL_EDGE, SEL_FACE, SEL_VERTEX, SEL_DATUMPLANE, SEL_DATUMAXIS, SEL_DATUMPOINT = 1, 2, 3, 4, 5, 6
SEL_SKETCH, SEL_SKETCHSEG, SEL_SKETCHPT, SEL_BODYFEATURE = 9, 10, 11, 22


def null_variant():
    return win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)


def r8_array(values):
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, tuple(float(v) for v in values))


def disp_array(objs):
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, tuple(objs))


class ModelingBase:
    """Helper comuni ai mixin di modellazione. Richiede get_active_doc(), _result(), _units, _com()."""

    # ------------------------------------------------------------------ documento
    def _part(self):
        """(doc, errore): documento attivo, deve essere un pezzo."""
        doc, err = self.get_active_doc()
        if err:
            return None, err
        try:
            if int(doc.GetType) != 1:
                return None, self._result(False, "Il documento attivo non e' un pezzo (.SLDPRT).",
                                          SwErrors.swInvalidInput)
        except Exception:
            pass
        self._prepare_prefs()
        return doc, None

    _DIALOG_PREFS = ((10, False),      # swInputDimValOnCreate: chiede il valore a ogni quota (finestra che blocca la chiamata COM)
                     (96, False),      # swSketchPromptToCloseSketch
                     (100, False),     # swSketchOverdefiningDimsPromptToSetState
                     (101, True))      # swSketchOverdefiningDimsSetDrivenByDefault

    def _prepare_prefs(self):
        """Niente finestre di dialogo durante il tool. Le preferenze sono GLOBALI (finiscono nel registro): il valore originale
        si salva qui la prima volta e `_restore_prefs` lo rimette alla fine di ogni chiamata (server.call_tool), cosi' il lavoro
        a mano di Elia non cambia, ne' sulla sua istanza ne' tramite il registro scritto dall'istanza dedicata alla chiusura."""
        app = self._sw_app
        if app is None:
            return
        saved = self.__dict__.setdefault("_saved_prefs", {})
        for pref, val in self._DIALOG_PREFS:
            try:
                if pref not in saved:
                    saved[pref] = bool(app.GetUserPreferenceToggle(pref))
                app.SetUserPreferenceToggle(pref, val)
            except Exception:
                pass

    def _restore_prefs(self):
        """Rimette le preferenze cambiate da `_prepare_prefs` (chiamato alla fine di ogni tool e prima di chiudere l'istanza)."""
        saved = self.__dict__.pop("_saved_prefs", None)
        app = self._sw_app
        if not saved or app is None:
            return
        for pref, val in saved.items():
            try:
                app.SetUserPreferenceToggle(pref, val)
            except Exception:
                pass

    def _mmu(self, value, unit=None) -> float:
        """valore -> metri (unita' interne di SW)"""
        return self._units.to_meters(value, unit)

    def _unit_name(self, unit=None) -> str:
        return unit or self._units.default_unit.value

    def _from_m(self, value, unit=None) -> float:
        return self._units.from_meters(value, unit)

    def _sd(self, doc, mark: int = 0):
        sd = self._com(doc.SelectionManager, "CreateSelectData")
        sd.Mark = mark
        return sd

    def _sel_count(self, doc) -> int:
        try:
            return int(doc.SelectionManager.GetSelectedObjectCount2(-1))
        except Exception:
            return 0

    def _clear(self, doc):
        doc.ClearSelection2(True)

    # ------------------------------------------------------------------ massa / volume
    def _mass_props(self, doc):
        # CreateMassProperty2 tiene conto del materiale (la versione 1 usa sempre 1000 kg/m3)
        for name in ("CreateMassProperty2", "CreateMassProperty"):
            try:
                mp = self._com(doc.Extension, name)
                if mp is not None:
                    return mp
            except Exception:
                continue
        return None

    def _volume_m3(self, doc) -> float:
        """Volume (m3). Dopo aver aperto/chiuso uno schizzo vuoto SW puo' restituire 0 finche' il modello non viene
        ricostruito: in quel caso si ricostruisce una volta e si rilegge."""
        def read():
            mp = self._mass_props(doc)
            return float(self._com(mp, "Volume")) if mp is not None else 0.0
        try:
            v = read()
            if v == 0.0 and self._sketch_free(doc):
                try:
                    doc.EditRebuild3
                except Exception:
                    pass
                v = read()
            return v
        except Exception:
            return 0.0

    def _sketch_free(self, doc) -> bool:
        try:
            return self._com(doc.SketchManager, "ActiveSketch") is None
        except Exception:
            return True

    # ------------------------------------------------------------------ feature
    def _features(self, doc) -> List[Tuple[str, str, Any]]:
        out = []
        feat = self._com(doc, "FirstFeature")
        while feat is not None:
            try:
                out.append((self._com(feat, "Name"), self._com(feat, "GetTypeName2"), feat))
            except Exception:
                pass
            feat = self._com(feat, "GetNextFeature")
        return out

    def _find_feature(self, doc, name: str):
        if not name:
            return None
        try:
            f = doc.FeatureByName(name)
            if f is not None:
                return f
        except Exception:
            pass
        low = name.lower()
        for n, t, f in self._features(doc):
            if n.lower() == low:
                return f
        return None

    def _select_feature(self, doc, name: str, append: bool = False, mark: int = 0) -> bool:
        feat = self._find_feature(doc, name)
        if feat is None:
            return False
        try:
            return bool(feat.Select2(append, mark))
        except Exception:
            return False

    def _feature_names(self, doc, type_name: str) -> List[str]:
        return [n for n, t, f in self._features(doc) if t == type_name]

    def _last_of_type(self, doc, type_name: str) -> Optional[str]:
        names = self._feature_names(doc, type_name)
        return names[-1] if names else None

    def _exit_sketch(self, doc) -> Optional[str]:
        """Chiude lo schizzo attivo (se c'e') e ne restituisce il nome (la chiusura lo lascia selezionato)."""
        sm = doc.SketchManager
        if self._com(sm, "ActiveSketch") is None:
            return None
        doc.ClearSelection2(True)
        sm.InsertSketch(True)
        name = None
        try:
            if self._sel_count(doc) >= 1 and int(doc.SelectionManager.GetSelectedObjectType3(1, -1)) == SEL_SKETCH:
                name = self._com(doc.SelectionManager.GetSelectedObject6(1, -1), "Name")
        except Exception:
            name = None
        return name or self._last_of_type(doc, "ProfileFeature")

    def _resolve_sketch(self, doc, sketch: Optional[str]) -> Tuple[Optional[str], Optional[Dict]]:
        """Nome dello schizzo da usare: quello indicato, o l'attivo (che viene chiuso), o l'ultimo."""
        closed = self._exit_sketch(doc)
        if sketch:
            if self._find_feature(doc, sketch) is None:
                return None, self._result(False, f"Schizzo '{sketch}' non trovato. "
                                          f"Schizzi: {self._feature_names(doc, 'ProfileFeature')}",
                                          SwErrors.swSelectionError)
            return sketch, None
        name = closed or self._last_of_type(doc, "ProfileFeature")
        if not name:
            return None, self._result(False, "Nessuno schizzo nel modello.", SwErrors.swSketchError)
        return name, None

    def _feature_info(self, doc, feat, vol_before: float = None) -> Dict:
        info = {}
        try:
            info["feature"] = self._com(feat, "Name")
            info["feature_type"] = self._com(feat, "GetTypeName2")
        except Exception:
            pass
        vol = self._volume_m3(doc)
        info["volume_mm3"] = round(vol * 1e9, 3)
        if vol_before is not None:
            info["volume_delta_mm3"] = round((vol - vol_before) * 1e9, 3)
        return info

    def _feature_error(self, doc, what: str, extra: str = "") -> Dict:
        msg = f"{what} non riuscito. {extra}".strip()
        return self._result(False, msg, SwErrors.swFeatureError)

    # ------------------------------------------------------------------ corpi / entita'
    def _bodies(self, doc) -> list:
        try:
            b = doc.GetBodies2(0, False)   # swSolidBody
            return list(b) if b else []
        except Exception:
            return []

    def _body_entities(self, doc, kind: str) -> list:
        out = []
        for body in self._bodies(doc):
            try:
                items = self._com(body, {"face": "GetFaces", "edge": "GetEdges"}.get(kind, "GetVertices"))
            except Exception:
                items = None
            if items:
                out.extend(items)
        return out

    @staticmethod
    def _dist(a, b) -> float:
        return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))

    def _closest(self, ent, kind: str, p) -> float:
        """distanza (m) fra il punto p (m) e l'entita'."""
        if kind == "vertex":
            q = self._com(ent, "GetPoint")
            return self._dist(q, p)
        q = ent.GetClosestPointOn(p[0], p[1], p[2])
        if q is None:
            return 1e9
        return self._dist(q, p)

    def _find_entity(self, doc, kind: str, p, tol_m: float):
        """Entita' piu' vicina a p (m); None se oltre tol_m."""
        best, bd = None, 1e9
        for ent in self._body_entities(doc, kind):
            try:
                d = self._closest(ent, kind, p)
            except Exception:
                continue
            if d < bd:
                best, bd = ent, d
        if best is not None and bd <= tol_m:
            return best, bd
        return None, bd

    def select_at_point(self, kind: str, x: float, y: float, z: float, unit: str = None,
                        append: bool = False, mark: int = 0, tolerance: float = 0.05) -> Dict:
        """Seleziona una faccia / uno spigolo / un vertice per coordinate (punto sull'entita', modello in `unit`)."""
        doc, err = self._part()
        if err:
            return err
        ok, info = self._select_point(doc, kind, (x, y, z), unit, append, mark, tolerance)
        if not ok:
            return self._result(False, info["error"], SwErrors.swSelectionError, info)
        return self._result(True, f"Selezionato {kind} a ({x}, {y}, {z})", SwErrors.swSuccess, info)

    def _select_point(self, doc, kind: str, pt, unit=None, append=False, mark=0, tol_mm: float = 0.05):
        """-> (ok, info). tol_mm in millimetri (indipendente da `unit`)."""
        kind = {"faccia": "face", "spigolo": "edge", "vertice": "vertex", "faces": "face",
                "edges": "edge", "vertices": "vertex"}.get(kind.lower(), kind.lower())
        if kind not in ("face", "edge", "vertex"):
            return False, {"error": f"Tipo di entita' sconosciuto: {kind} (face|edge|vertex)"}
        try:
            p = [self._mmu(float(c), unit) for c in pt]
        except Exception:
            return False, {"error": f"Punto non valido: {pt}"}
        if len(p) != 3:
            return False, {"error": f"Il punto deve avere 3 coordinate: {pt}"}
        ent, d = self._find_entity(doc, kind, p, max(tol_mm, 0.001) / 1000.0)
        if ent is None:
            return False, {"error": f"Nessun {kind} entro {tol_mm} mm dal punto {list(pt)} {self._unit_name(unit)} "
                                    f"(piu' vicino a {d * 1000:.3f} mm). Il punto deve stare SULL'entita'.",
                           "closest_mm": round(d * 1000, 4) if d < 1e8 else None}
        sd = self._sd(doc, mark)
        try:
            sd.X, sd.Y, sd.Z = p[0], p[1], p[2]     # punto di pick (serve al foro guidato)
        except Exception:
            pass
        ok = bool(ent.Select4(append, sd))
        info = {"kind": kind, "point": list(pt), "distance_mm": round(d * 1000, 5)}
        try:
            if kind == "face":
                info["area_mm2"] = round(float(self._com(ent, "GetArea")) * 1e6, 3)
        except Exception:
            pass
        if not ok:
            info["error"] = f"Select4 ha rifiutato il {kind}"
        return ok, info

    def _select_points(self, doc, kind: str, points, unit=None, mark=0, append_first=False,
                       tol_mm: float = 0.05):
        """Seleziona molte entita' (append). -> (ok, errore|None)."""
        first = not append_first
        for pt in (points or []):
            ok, info = self._select_point(doc, kind, pt, unit, append=not first, mark=mark, tol_mm=tol_mm)
            if not ok:
                return False, info.get("error", "selezione fallita")
            first = False
        return True, None

    def _std_plane_feature(self, doc, name: str):
        """Piano standard per nome inglese (front/top/right) o italiano, in base alla posizione nell'albero."""
        return self._std_ref_feature(doc, name) if std_plane_index(name) is not None else None

    def _select_edge_or_axis(self, doc, spec, unit, mark=0, append=False, tol_mm=0.05):
        """Direzione / asse: {"edge":[x,y,z]} (spigolo), {"face":[x,y,z]} (faccia piana o cilindrica),
        {"plane":"Piano1"}, {"axis":"Asse1"}, {"sketch_line": ...} oppure un semplice [x,y,z] = spigolo."""
        if spec is None:
            return False, "Direzione/asse mancante"
        if isinstance(spec, (list, tuple)):
            return self._select_point(doc, "edge", spec, unit, append, mark, tol_mm)[0], "spigolo non trovato"
        if isinstance(spec, str):
            spec = {"plane": spec}
        if "edge" in spec:
            ok, info = self._select_point(doc, "edge", spec["edge"], unit, append, mark, tol_mm)
            return ok, info.get("error", "")
        if "face" in spec:
            ok, info = self._select_point(doc, "face", spec["face"], unit, append, mark, tol_mm)
            return ok, info.get("error", "")
        for key in ("plane", "axis", "feature"):
            if key in spec:
                name = spec[key]
                feat = self._find_feature(doc, name) or self._std_plane_feature(doc, name)
                if feat is None:
                    return False, f"Feature '{name}' non trovata"
                return bool(feat.Select2(append, mark)), f"Feature '{name}' non selezionabile"
        return False, "Specifica non riconosciuta (usa edge/face/plane/axis)"

    # ------------------------------------------------------------------ elenco entita'
    def list_entities(self, kind: str = "face", unit: str = None, limit: int = 60) -> Dict:
        """Elenca facce / spigoli / vertici del corpo con un punto utilizzabile per selezionarli."""
        doc, err = self._part()
        if err:
            return err
        kind = {"faces": "face", "edges": "edge", "vertices": "vertex"}.get(kind.lower(), kind.lower())
        items, out = self._body_entities(doc, kind), []
        for i, e in enumerate(items[:limit]):
            row = {"index": i}
            try:
                if kind == "face":
                    surf = self._com(e, "GetSurface")
                    row["area"] = round(self._from_m(float(self._com(e, "GetArea")) ** 0.5, unit) ** 2, 3)
                    row["type"] = ("plane" if self._com(surf, "IsPlane") else "cylinder" if self._com(surf, "IsCylinder")
                                   else "cone" if self._com(surf, "IsCone") else "sphere" if self._com(surf, "IsSphere")
                                   else "torus" if self._com(surf, "IsTorus") else "other")
                    box = self._com(e, "GetBox")
                    c = [(box[k] + box[k + 3]) / 2 for k in range(3)]
                    q = e.GetClosestPointOn(c[0], c[1], c[2])
                    row["point"] = [round(self._from_m(v, unit), 4) for v in list(q)[:3]]
                    if row["type"] == "plane":
                        row["normal"] = [round(v, 4) for v in self._com(e, "Normal")]
                    elif row["type"] == "cylinder":
                        cp = self._com(surf, "CylinderParams")
                        row["radius"] = round(self._from_m(cp[6], unit), 4)
                        row["axis_origin"] = [round(self._from_m(v, unit), 4) for v in cp[0:3]]
                        row["axis_dir"] = [round(v, 4) for v in cp[3:6]]
                elif kind == "edge":
                    cv = self._com(e, "GetCurve")
                    v1, v2 = self._com(e, "GetStartVertex"), self._com(e, "GetEndVertex")
                    sp = self._com(v1, "GetPoint") if v1 is not None else None
                    ep = self._com(v2, "GetPoint") if v2 is not None else None
                    row["type"] = ("line" if self._com(cv, "IsLine") else "circle" if self._com(cv, "IsCircle")
                                   else "other")
                    if sp is not None and ep is not None:
                        mid = e.GetClosestPointOn((sp[0] + ep[0]) / 2, (sp[1] + ep[1]) / 2, (sp[2] + ep[2]) / 2)
                        row["start"] = [round(self._from_m(v, unit), 4) for v in sp]
                        row["end"] = [round(self._from_m(v, unit), 4) for v in ep]
                        row["point"] = [round(self._from_m(v, unit), 4) for v in list(mid)[:3]]
                    elif self._com(cv, "IsCircle"):
                        cp = self._com(cv, "CircleParams")
                        row["radius"] = round(self._from_m(cp[6], unit), 4)
                        row["center"] = [round(self._from_m(v, unit), 4) for v in cp[0:3]]
                        pt = e.GetClosestPointOn(cp[0] + cp[6], cp[1], cp[2])
                        row["point"] = [round(self._from_m(v, unit), 4) for v in list(pt)[:3]]
                else:
                    row["point"] = [round(self._from_m(v, unit), 4) for v in self._com(e, "GetPoint")]
            except Exception as ex:
                row["note"] = f"dati parziali: {ex}"
            out.append(row)
        return self._result(True, f"{len(items)} {kind} (mostrati {len(out)})", SwErrors.swSuccess,
                            {"kind": kind, "count": len(items), "unit": self._unit_name(unit), "entities": out})
