"""
Assiemi (blocco 2): componenti, ripetizioni, accoppiamenti, stato dei vincoli, spostamento.
Mixin `AssemblyOperations` (con `AssemblyAnalysisMixin` di assembly_analysis.py: vista esplosa, interferenze, massa, configurazioni).

Trappole SW 2026 (late binding, UI italiana) scoperte con questo blocco:
 - `AddComponent5` restituisce None se il file non e' gia' caricato in memoria: prima OpenDoc6 silenzioso, poi si
   riattiva l'assieme (ActivateDoc3). Inoltre X,Y,Z indicano il CENTRO DEL BOX del componente, non l'origine:
   dopo l'inserimento si imposta `Transform2` (MathTransform) per mettere l'origine dove richiesto.
 - `IMathUtility.CreateTransform` non e' richiamabile in late binding: `_oleobj_.Invoke(dispid, 0, DISPATCH_METHOD, True, array)`.
   Array di 16 double: 9 di rotazione (RIGHE = immagini degli assi X,Y,Z: p' = p*R + t), 3 di traslazione, scala, 3 zeri.
 - AddMate5: con assi di riferimento (datum) come entita' il concentrico fallisce (errore 0): si usa il coincidente
   fra i due assi (stesso vincolo). Con facce cilindriche il concentrico funziona. Errore 1 = nessun errore.
 - Ripetizione circolare/lineare di COMPONENTI: FeatureCircularPattern5 con componenti seme Mark 1 e asse Mark 2
   (NON Mark 4/1 come per le feature); lineare: seme Mark 1, direzione Mark 2. Number2 deve essere >= 1.
 - Le coordinate delle facce di un componente (GetBodies2) sono nello spazio del PEZZO: i punti dell'assieme si
   riportano nel pezzo con l'inversa della trasformazione. Con la vista esplosa attiva Transform2/GetBox danno la
   posizione ESPLOSA: le operazioni geometriche richiudono prima l'esploso.
 - GetErrorCode2 e' una proprieta' che restituisce (codice, avviso). Le proprieta' senza argomenti vanno lette con `_com`.
"""

import os
import math
import logging
import traceback
from typing import Dict, List, Tuple

import win32com.client
import pythoncom

from ..constants import SwErrors
from .assembly_analysis import AssemblyAnalysisMixin
from .assembly_motion import AssemblyMotionMixin
from .assembly_explode import AssemblyExplodeMixin

logger = logging.getLogger(__name__)

MATE_TYPES = {"coincident": 0, "concentric": 1, "perpendicular": 2, "parallel": 3, "tangent": 4, "distance": 5,
              "angle": 6, "symmetric": 8, "gear": 10, "width": 11, "lock": 16, "screw": 17}
MATE_NAMES = {v: k for k, v in MATE_TYPES.items()}
MATE_NAMES.update({12: "lock_to_sketch", 13: "rack_pinion", 15: "path", 18: "linear_coupler", 19: "universal_joint",
                   20: "coordinate", 21: "slot", 22: "hinge", 23: "slider", 24: "profile_center", 25: "magnetic"})
ALIGN = {"aligned": 0, "anti_aligned": 1, "anti-aligned": 1, "closest": 2}
ALIGN_NAMES = {0: "aligned", 1: "anti_aligned", 2: "closest"}
CONSTRAINED = {1: "sconosciuto", 2: "sottovincolato", 3: "completamente vincolato", 4: "sovravincolato",
               5: "nessuna soluzione", 6: "soluzione non valida", 7: "risoluzione automatica disattivata"}
ADD_MATE_ERRORS = {0: "errore sconosciuto", 1: "nessun errore", 2: "tipo di accoppiamento non adatto alle entita'",
                   3: "allineamento non valido", 4: "selezioni non valide", 5: "assieme sovravincolato",
                   6: "rapporto di ingranaggio non valido"}
_AXIS_DIR = {"x": (0, False), "+x": (0, False), "-x": (0, True), "y": (1, False), "+y": (1, False), "-y": (1, True),
             "z": (2, False), "+z": (2, False), "-z": (2, True)}


def _i4():
    return win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)


def _null():
    return win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)


def _rot_matrix(rx: float, ry: float, rz: float):
    """Matrice 3x3 (convenzione colonna, p' = M p) per rotazioni X poi Y poi Z (estrinseche), angoli in gradi."""
    a, b, c = math.radians(rx), math.radians(ry), math.radians(rz)
    ca, sa, cb, sb, cc, sc = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(c), math.sin(c)
    # M = Rz * Ry * Rx
    return [[cc * cb, cc * sb * sa - sc * ca, cc * sb * ca + sc * sa],
            [sc * cb, sc * sb * sa + cc * ca, sc * sb * ca - cc * sa],
            [-sb, cb * sa, cb * ca]]


def _array_from(M, t) -> List[float]:
    """M (colonna) + traslazione t [m] -> array di 16 double di SolidWorks (righe = immagini degli assi)."""
    return [M[0][0], M[1][0], M[2][0], M[0][1], M[1][1], M[2][1], M[0][2], M[1][2], M[2][2],
            t[0], t[1], t[2], 1.0, 0.0, 0.0, 0.0]


def _from_array(a) -> Tuple[list, list]:
    """array SolidWorks -> (M colonna, t [m])."""
    M = [[a[0], a[3], a[6]], [a[1], a[4], a[7]], [a[2], a[5], a[8]]]
    return M, [a[9], a[10], a[11]]


def _euler_deg(M) -> List[float]:
    sy = -M[2][0]
    ry = math.asin(max(-1.0, min(1.0, sy)))
    if abs(abs(sy) - 1.0) < 1e-9:
        return [round(math.degrees(math.atan2(-M[1][2], M[1][1])), 4), round(math.degrees(ry), 4), 0.0]
    return [round(math.degrees(math.atan2(M[2][1], M[2][2])), 4), round(math.degrees(ry), 4),
            round(math.degrees(math.atan2(M[1][0], M[0][0])), 4)]


class AssemblyOperations(AssemblyExplodeMixin, AssemblyMotionMixin, AssemblyAnalysisMixin):
    """Mixin: assiemi. Richiede SolidWorksAutomation (base, ModelingBase)."""

    # ====================================================================
    # Helper
    # ====================================================================

    def _asm(self):
        """(doc, errore): documento attivo, deve essere un assieme."""
        doc, err = self.get_active_doc()
        if err:
            return None, err
        try:
            if int(doc.GetType) != 2:
                return None, self._result(False, f"Il documento attivo ({self._get_doc_title(doc)}) non e' un assieme "
                                          "(.SLDASM). Usa create_new_assembly o open_document.", SwErrors.swInvalidInput)
        except Exception:
            pass
        self._prepare_prefs()
        return doc, None

    def _as_fail(self, what: str, e: Exception) -> Dict:
        logger.error(f"{what}: {e}\n{traceback.format_exc()}")
        return self._result(False, f"{what}: {e}", SwErrors.swUnknownError)

    def _as_title(self, doc) -> str:
        t = str(self._get_doc_title(doc))
        return os.path.splitext(t)[0] if t.lower().endswith((".sldasm", ".sldprt")) else t

    def _as_utility(self):
        return self._com(self._sw_app, "GetMathUtility")

    def _as_transform(self, M, t):
        """MathTransform da matrice (colonna) e traslazione [m]."""
        mu = self._as_utility()
        arr = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, tuple(float(v) for v in _array_from(M, t)))
        did = mu._oleobj_.GetIDsOfNames("CreateTransform")
        return win32com.client.Dispatch(mu._oleobj_.Invoke(did, 0, pythoncom.DISPATCH_METHOD, True, arr))

    def _as_pose(self, comp, ignore_explode: bool = True):
        """(M, t[m]) del componente (posizione reale, non esplosa)."""
        try:
            xf = comp.GetSpecificTransform(bool(ignore_explode)) if ignore_explode else comp.Transform2
        except Exception:
            xf = comp.Transform2
        return _from_array(list(xf.ArrayData))

    def _as_collapse(self, doc) -> bool:
        """Richiude la vista esplosa se attiva (le coordinate sono quelle reali). True se l'ha chiusa."""
        try:
            if bool(self._com(doc, "IsExploded")):
                names = self._com(doc, "GetExplodedViewNames2") if False else None
                try:
                    cfg = self._com(doc, "GetActiveConfiguration")
                    names = doc.GetExplodedViewNames2(str(cfg.Name))
                except Exception:
                    names = self._com(doc, "GetExplodedViewNames")
                doc.ShowExploded2(False, (names or [""])[0])
                return True
        except Exception:
            pass
        return False

    def _as_top_components(self, doc, top_only: bool = True) -> list:
        try:
            comps = doc.GetComponents(bool(top_only))
        except Exception:
            comps = None
        return list(comps) if comps else []

    def _as_comp(self, doc, name, top_only: bool = False):
        """Componente per nome istanza ('perno-1', anche senza prefisso o senza '-N' se unico). (comp, errore)."""
        if name is None or str(name).strip() == "":
            return None, "Nome componente mancante"
        if not isinstance(name, str):
            try:
                if hasattr(name, "Name2"):
                    return name, None
            except Exception:
                pass
        s = str(name).strip()
        comps = self._as_top_components(doc, top_only)
        names = [str(c.Name2) for c in comps]
        for c, n in zip(comps, names):
            if n == s:
                return c, None
        low = s.lower()
        hit = [c for c, n in zip(comps, names) if n.lower() == low]
        if not hit:
            hit = [c for c, n in zip(comps, names) if n.lower().rsplit("-", 1)[0] == low or n.lower().endswith("/" + low)]
        if not hit:
            hit = [c for c, n in zip(comps, names) if low in n.lower()]
        if len(hit) == 1:
            return hit[0], None
        if not hit:
            return None, f"Componente '{s}' non trovato. Presenti: {', '.join(sorted(names))[:300]}"
        return None, f"Componente '{s}' ambiguo: {', '.join(sorted(str(c.Name2) for c in hit))[:300]}"

    def _as_comps(self, doc, names, top_only: bool = False):
        """Lista di componenti da nomi (str | lista). (lista, errore)."""
        if names is None:
            return [], "Elenco componenti mancante"
        if isinstance(names, str):
            names = [names]
        out = []
        for n in names:
            c, e = self._as_comp(doc, n, top_only)
            if e:
                return [], e
            out.append(c)
        return out, None

    def _as_comp_path(self, comp) -> str:
        try:
            return str(self._com(comp, "GetPathName"))
        except Exception:
            return ""

    def _as_state(self, comp) -> Dict:
        """Stato del componente (soppresso, nascosto, fisso, ...)."""
        out = {}
        try:
            out["suppressed"] = int(self._com(comp, "GetSuppression")) == 0
        except Exception:
            out["suppressed"] = None
        try:
            out["hidden"] = bool(comp.IsHidden(True))
        except Exception:
            out["hidden"] = None
        try:
            out["fixed"] = bool(self._com(comp, "IsFixed"))
        except Exception:
            out["fixed"] = None
        return out

    def _as_comp_info(self, comp, detail: bool = True) -> Dict:
        info = {"name": str(comp.Name2), "file": self._as_comp_path(comp)}
        info["file_name"] = os.path.basename(info["file"])
        try:
            info["configuration"] = str(comp.ReferencedConfiguration)
        except Exception:
            pass
        try:
            M, t = self._as_pose(comp)
            info["position_mm"] = [round(v * 1000, 4) for v in t]
            info["rotation_deg"] = _euler_deg(M)
            info["transform"] = [round(v, 6) for v in _array_from(M, t)[:12]]
        except Exception as e:
            info["pose_error"] = str(e)
        info.update(self._as_state(comp))
        if detail:
            try:
                info["constrained"] = CONSTRAINED.get(int(self._com(comp, "GetConstrainedStatus")), "?")
            except Exception:
                pass
            try:
                info["pattern_instance"] = bool(self._com(comp, "IsPatternInstance"))
            except Exception:
                pass
            try:
                info["exclude_from_bom"] = bool(comp.ExcludeFromBOM)
            except Exception:
                pass
        return info

    def _as_activate(self, title: str):
        err = _i4()
        try:
            self._sw_app.ActivateDoc3(title, False, 0, err)
        except Exception as e:
            logger.debug(f"ActivateDoc3 failed: {e}")

    def _as_load_model(self, doc, path: str):
        """Il file deve essere in memoria perche' AddComponent5 funzioni: lo apre in silenzio e riattiva l'assieme."""
        path = os.path.abspath(path)
        title = str(self._get_doc_title(doc))
        try:
            if self._sw_app.GetOpenDocumentByName(path) is not None:
                return True, None
        except Exception:
            pass
        ext = os.path.splitext(path)[1].lower()
        dtype = 2 if ext == ".sldasm" else 1
        e, w = _i4(), _i4()
        d = self._sw_app.OpenDoc6(path, dtype, 1, "", e, w)
        self._as_activate(title)
        if d is None:
            return False, f"Impossibile aprire {path} (errore {e.value})"
        return True, None

    def _as_select_comps(self, doc, comps, mark: int = 0) -> bool:
        doc.ClearSelection2(True)
        ok = True
        for i, c in enumerate(comps):
            ok = bool(c.Select2(i > 0, mark)) and ok
        return ok

    def _as_new_names(self, doc, before: set) -> List[str]:
        return sorted(str(c.Name2) for c in self._as_top_components(doc, False) if str(c.Name2) not in before)

    # ---- entita' (facce, spigoli, piani, assi) di un componente ------------------------------
    def _as_feature_of(self, comp, fname: str):
        f = None
        try:
            f = comp.FeatureByName(fname)
        except Exception:
            f = None
        if f is not None:
            return f
        # piani standard e origine per posizione/tipo: "Piano frontale" e "Front Plane" valgono in ogni lingua di SolidWorks
        try:
            f = self._std_ref_feature(comp, fname)
        except Exception:
            f = None
        if f is not None:
            return f
        # confronto senza maiuscole sulle feature del componente
        try:
            g = self._com(comp, "FirstFeature")
            while g is not None:
                if str(self._com(g, "Name")).lower() == fname.lower():
                    return g
                g = self._com(g, "GetNextFeature")
        except Exception:
            pass
        return None

    def _as_to_part(self, comp, p) -> List[float]:
        """punto dell'assieme [m] -> coordinate del pezzo."""
        M, t = self._as_pose(comp)
        d = [p[i] - t[i] for i in range(3)]
        return [M[0][j] * d[0] + M[1][j] * d[1] + M[2][j] * d[2] for j in range(3)]

    def _as_find_geom(self, doc, kind: str, pt_m, comp=None, tol_mm: float = 0.05):
        """Entita' (faccia/spigolo/vertice) piu' vicina al punto dell'assieme, fra i corpi dei componenti."""
        # C1: tutti i livelli (sotto-assiemi compresi). Transform2 di un componente annidato e' GIA' la trasformazione
        # composta (assieme principale <- pezzo), quindi _as_to_part vale a qualsiasi profondita'.
        comps = [comp] if comp is not None else self._as_top_components(doc, False)
        best, bd, bcomp = None, 1e9, None
        for c in comps:
            try:
                if int(self._com(c, "GetSuppression")) == 0:
                    continue
                bodies = c.GetBodies2(0)
            except Exception:
                continue
            if not bodies:
                continue
            q = self._as_to_part(c, pt_m)
            for b in bodies:
                try:
                    items = self._com(b, {"face": "GetFaces", "edge": "GetEdges"}.get(kind, "GetVertices"))
                except Exception:
                    items = None
                for ent in (items or ()):
                    try:
                        if kind == "vertex":
                            d = self._dist(self._com(ent, "GetPoint"), q)
                        else:
                            cp = ent.GetClosestPointOn(q[0], q[1], q[2])
                            d = self._dist(cp, q) if cp is not None else 1e9
                    except Exception:
                        continue
                    if d < bd:
                        best, bd, bcomp = ent, d, c
        if best is not None and bd * 1000 <= max(tol_mm, 0.001):
            return best, bcomp, bd
        return None, None, bd

    def _as_select_entity(self, doc, spec, unit, mark: int, append: bool, tol_mm: float = 0.05):
        """Seleziona un'entita' di componente. spec:
           - "Piano frontale@perno-1", "Assi1@staffa-1", "Origine@perno-1" (feature del componente)
           - {"face":[x,y,z]} | {"edge":[..]} | {"vertex":[..]} (coordinate dell'ASSIEME, + opzionale "component")
           - {"component":"perno-1", "plane"|"axis"|"feature": "Nome"}  - {"component":"perno-1"} (intero componente)
           - [x,y,z] = faccia.
        -> (info dict, errore str|None)"""
        try:
            sd = self._sd(doc, mark)
            if isinstance(spec, (list, tuple)) and len(spec) == 3 and all(isinstance(v, (int, float)) for v in spec):
                spec = {"face": list(spec)}
            if isinstance(spec, str):
                s = spec.strip()
                if "@" not in s:
                    comp, e = self._as_comp(doc, s)
                    if e:
                        # C5: nome di una feature dell'ASSIEME ("Piano destro", "Origine"...): piano di simmetria, ecc.
                        f = self._as_feature_of_doc(doc, s)
                        if f is not None and bool(f.Select2(append, mark)):
                            return {"component": None, "kind": str(self._com(f, "GetTypeName2")), "feature": s}, None
                        return None, e
                    ok = bool(comp.Select2(append, mark))
                    return ({"component": str(comp.Name2), "kind": "component"}, None) if ok else (None, f"Selezione di {s} fallita")
                parts = s.split("@")
                fname, cname = parts[0], parts[1]
                comp, e = self._as_comp(doc, cname)
                if e:
                    return None, e
                f = self._as_feature_of(comp, fname)
                if f is None:
                    return None, f"Feature '{fname}' non trovata nel componente {comp.Name2}"
                ok = bool(f.Select2(append, mark))
                return ({"component": str(comp.Name2), "kind": str(self._com(f, "GetTypeName2")), "feature": fname}, None) \
                    if ok else (None, f"Selezione di '{s}' fallita")
            if isinstance(spec, dict):
                comp = None
                if spec.get("component"):
                    comp, e = self._as_comp(doc, spec["component"])
                    if e:
                        return None, e
                for key in ("plane", "axis", "feature", "origin"):
                    if key in spec:
                        if comp is None:
                            return None, f"'{key}' richiede anche 'component'"
                        f = self._as_feature_of(comp, str(spec[key]) if key != "origin" else "origin")
                        if f is None:
                            return None, f"Feature '{spec[key]}' non trovata in {comp.Name2}"
                        ok = bool(f.Select2(append, mark))
                        return ({"component": str(comp.Name2), "kind": str(self._com(f, "GetTypeName2")),
                                 "feature": str(spec[key])}, None) if ok else (None, "Selezione fallita")
                for kind in ("face", "edge", "vertex"):
                    if kind in spec:
                        pt = spec[kind]
                        p = [self._mmu(float(v), unit) for v in pt]
                        ent, c, d = self._as_find_geom(doc, kind, p, comp, float(spec.get("tolerance", tol_mm)))
                        if ent is None:
                            return None, (f"Nessun {kind} entro {tol_mm} mm dal punto {list(pt)}"
                                          f"{' in ' + str(comp.Name2) if comp is not None else ''} (piu' vicino a "
                                          f"{d * 1000:.3f} mm). Coordinate dell'ASSIEME, punto SULL'entita'.")
                        try:
                            sd.X, sd.Y, sd.Z = p[0], p[1], p[2]
                        except Exception:
                            pass
                        ok = bool(ent.Select4(append, sd))
                        info = {"component": str(c.Name2), "kind": kind, "distance_mm": round(d * 1000, 5)}
                        try:
                            if kind == "face":
                                s_ = self._com(ent, "GetSurface")
                                info["surface"] = ("planar" if self._com(s_, "IsPlane") else
                                                   "cylindrical" if self._com(s_, "IsCylinder") else
                                                   "conical" if self._com(s_, "IsCone") else
                                                   "spherical" if self._com(s_, "IsSphere") else "other")
                        except Exception:
                            pass
                        return (info, None) if ok else (None, f"Select4 ha rifiutato il {kind}")
                if comp is not None:
                    ok = bool(comp.Select2(append, mark))
                    return ({"component": str(comp.Name2), "kind": "component"}, None) if ok else (None, "Selezione fallita")
            return None, f"Entita' non riconosciuta: {spec!r}"
        except Exception as e:
            return None, f"Selezione entita' {spec!r}: {e}"

    # ====================================================================
    # Componenti
    # ====================================================================

    def _as_place(self, comp, position_m, rotation_deg):
        rx, ry, rz = (list(rotation_deg or [0, 0, 0]) + [0, 0, 0])[:3]
        comp.Transform2 = self._as_transform(_rot_matrix(rx, ry, rz), position_m)

    def insert_component(self, file_path: str, x: float = 0, y: float = 0, z: float = 0, rotation: list = None,
                         configuration: str = None, fixed: bool = False, unit: str = None) -> Dict:
        """Inserisce un componente (pezzo o sotto-assieme) con l'ORIGINE del file in (x,y,z) e rotazione [rx,ry,rz] gradi."""
        try:
            doc, err = self._asm()
            if err:
                return err
            path = os.path.abspath(file_path)
            if not os.path.isfile(path):
                return self._result(False, f"File non trovato: {path}", SwErrors.swFileNotFoundError)
            self._as_collapse(doc)
            ok, msg = self._as_load_model(doc, path)
            if not ok:
                return self._result(False, msg, SwErrors.swFileLoadError)
            doc = self._sw_app.ActiveDoc
            pos = [self._mmu(float(v), unit) for v in (x, y, z)]
            comp = doc.AddComponent5(path, 0, "", False, configuration or "", pos[0], pos[1], pos[2])
            if comp is None:
                return self._result(False, "AddComponent5 non ha creato il componente (file in uso o configurazione errata).",
                                    SwErrors.swFeatureError)
            self._as_place(comp, pos, rotation)
            if fixed:
                self._as_select_comps(doc, [comp])
                doc.FixComponent()
                doc.ClearSelection2(True)
            doc.ForceRebuild2(False)
            return self._result(True, f"Componente inserito: {comp.Name2}", SwErrors.swSuccess, self._as_comp_info(comp))
        except Exception as e:
            return self._as_fail("insert_component", e)

    def insert_components(self, file_path: str, count: int = 2, positions: list = None, start: list = None,
                          step: list = None, rotation: list = None, fixed: bool = False, unit: str = None) -> Dict:
        """Inserisce piu' istanze dello stesso file: `positions` [[x,y,z],...] oppure `start` + `step` (count istanze)."""
        try:
            doc, err = self._asm()
            if err:
                return err
            if positions:
                pts = [list(p) for p in positions]
            else:
                s0 = list(start or [0, 0, 0])
                st = list(step or [0, 0, 0])
                pts = [[s0[i] + k * st[i] for i in range(3)] for k in range(int(count))]
            names = []
            for p in pts:
                r = self.insert_component(file_path, p[0], p[1], p[2], rotation, None, fixed, unit)
                if not r["success"]:
                    return self._result(False, f"Inserimento istanza {len(names) + 1} fallito: {r['message']}",
                                        SwErrors.swFeatureError, {"inserted": names})
                names.append(r["data"]["name"])
            return self._result(True, f"{len(names)} istanze inserite", SwErrors.swSuccess, {"components": names})
        except Exception as e:
            return self._as_fail("insert_components", e)

    def set_component_fixed(self, component: str, fixed: bool = True) -> Dict:
        """Fissa (True) o rende mobile (False) un componente."""
        try:
            doc, err = self._asm()
            if err:
                return err
            comp, e = self._as_comp(doc, component, True)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            self._as_select_comps(doc, [comp])
            if fixed:
                doc.FixComponent()
            else:
                doc.UnfixComponent()
            doc.ClearSelection2(True)
            now = bool(self._com(comp, "IsFixed"))
            return self._result(now == bool(fixed), f"{comp.Name2}: {'fisso' if now else 'mobile'}",
                                SwErrors.swSuccess if now == bool(fixed) else SwErrors.swFeatureError,
                                {"name": str(comp.Name2), "fixed": now})
        except Exception as e:
            return self._as_fail("set_component_fixed", e)

    def list_components(self, top_level_only: bool = True, include_details: bool = True) -> Dict:
        """Elenco componenti: nome istanza, file, configurazione, posizione (mm) e rotazione, fisso/mobile, soppresso, nascosto, stato vincoli."""
        try:
            doc, err = self._asm()
            if err:
                return err
            self._as_collapse(doc)
            comps = self._as_top_components(doc, top_level_only)
            infos = [self._as_comp_info(c, include_details) for c in comps]
            infos.sort(key=lambda d: d["name"])
            return self._result(True, f"{len(infos)} componenti", SwErrors.swSuccess,
                                {"count": len(infos), "components": infos})
        except Exception as e:
            return self._as_fail("list_components", e)

    def replace_component(self, component: str, new_file: str, configuration: str = None, replace_all: bool = False,
                          reattach_mates: bool = True) -> Dict:
        """Sostituisce un componente con un altro file (tutte le istanze se replace_all)."""
        try:
            doc, err = self._asm()
            if err:
                return err
            comp, e = self._as_comp(doc, component, True)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            path = os.path.abspath(new_file)
            if not os.path.isfile(path):
                return self._result(False, f"File non trovato: {path}", SwErrors.swFileNotFoundError)
            self._as_collapse(doc)
            ok, msg = self._as_load_model(doc, path)
            if not ok:
                return self._result(False, msg, SwErrors.swFileLoadError)
            doc = self._sw_app.ActiveDoc
            before = {str(c.Name2) for c in self._as_top_components(doc, False)}
            self._as_select_comps(doc, [comp])
            res = doc.ReplaceComponents2(path, configuration or "", bool(replace_all), 0, bool(reattach_mates))
            doc.ClearSelection2(True)
            after = {str(c.Name2) for c in self._as_top_components(doc, False)}
            if not res:
                return self._result(False, "ReplaceComponents2 non ha sostituito il componente.", SwErrors.swFeatureError)
            return self._result(True, f"Sostituito {comp.Name2 if False else component} con {os.path.basename(path)}",
                                SwErrors.swSuccess, {"new_components": sorted(after - before),
                                                     "removed": sorted(before - after)})
        except Exception as e:
            return self._as_fail("replace_component", e)

    def suppress_component(self, component: str, suppressed: bool = True) -> Dict:
        """Sopprime (True) o riattiva (False) un componente."""
        try:
            doc, err = self._asm()
            if err:
                return err
            comp, e = self._as_comp(doc, component, True)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            comp.SetSuppression2(0 if suppressed else 2)     # 0 swComponentSuppressed, 2 swComponentFullyResolved
            doc.ForceRebuild2(False)
            now = int(self._com(comp, "GetSuppression")) == 0
            return self._result(now == bool(suppressed), f"{component}: {'soppresso' if now else 'attivo'}",
                                SwErrors.swSuccess if now == bool(suppressed) else SwErrors.swFeatureError,
                                {"name": component, "suppressed": now})
        except Exception as e:
            return self._as_fail("suppress_component", e)

    def delete_component(self, component: str) -> Dict:
        """Elimina un componente dall'assieme (con i suoi accoppiamenti)."""
        try:
            doc, err = self._asm()
            if err:
                return err
            comp, e = self._as_comp(doc, component, True)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            name = str(comp.Name2)
            n0 = len(self._as_top_components(doc, False))
            self._as_select_comps(doc, [comp])
            doc.Extension.DeleteSelection2(3)
            doc.ClearSelection2(True)
            n1 = len(self._as_top_components(doc, False))
            if n1 >= n0:
                return self._result(False, f"Eliminazione di {name} non riuscita", SwErrors.swFeatureError)
            return self._result(True, f"Eliminato {name} ({n1} componenti rimasti)", SwErrors.swSuccess,
                                {"deleted": name, "remaining": n1})
        except Exception as e:
            return self._as_fail("delete_component", e)

    def set_component_visibility(self, component: str, visible: bool = True) -> Dict:
        """Nasconde (False) o mostra (True) un componente."""
        try:
            doc, err = self._asm()
            if err:
                return err
            comp, e = self._as_comp(doc, component, True)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            comp.Visible = 1 if visible else 0
            hidden = bool(comp.IsHidden(True))
            return self._result(hidden != bool(visible), f"{component}: {'nascosto' if hidden else 'visibile'}",
                                SwErrors.swSuccess if hidden != bool(visible) else SwErrors.swFeatureError,
                                {"name": component, "hidden": hidden})
        except Exception as e:
            return self._as_fail("set_component_visibility", e)

    def open_component(self, component: str) -> Dict:
        """Apre il documento di un componente in una finestra propria e lo rende attivo (poi activate_document per tornare all'assieme)."""
        try:
            doc, err = self._asm()
            if err:
                return err
            comp, e = self._as_comp(doc, component)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            path = self._as_comp_path(comp)
            if not path or not os.path.isfile(path):
                return self._result(False, f"File del componente non trovato: {path}", SwErrors.swFileNotFoundError)
            e1, w1 = _i4(), _i4()
            ext = os.path.splitext(path)[1].lower()
            d = self._sw_app.OpenDoc6(path, 2 if ext == ".sldasm" else 1, 1, "", e1, w1)
            if d is None:
                d = self._sw_app.GetOpenDocumentByName(path)
            if d is None:
                return self._result(False, f"Impossibile aprire {path} (errore {e1.value})", SwErrors.swFileLoadError)
            title = str(self._get_doc_title(d))
            self._as_activate(title)
            return self._result(True, f"Aperto {title}", SwErrors.swSuccess, {"title": title, "path": path})
        except Exception as e:
            return self._as_fail("open_component", e)

    def activate_document(self, name: str) -> Dict:
        """Rende attivo un documento gia' aperto (titolo come in list_open_documents, es. 'Assieme1' o 'staffa')."""
        try:
            if not self.is_connected:
                r = self.connect()
                if not r["success"]:
                    return r
            err = _i4()
            doc = self._sw_app.ActivateDoc3(str(name), False, 0, err)
            if doc is None:
                return self._result(False, f"Documento '{name}' non trovato o non attivabile (errore {err.value})",
                                    SwErrors.swNoActiveDocument)
            return self._result(True, f"Attivo: {self._get_doc_title(doc)}", SwErrors.swSuccess,
                                {"title": str(self._get_doc_title(doc))})
        except Exception as e:
            return self._as_fail("activate_document", e)

    # ====================================================================
    # Ripetizioni e specchiature di componenti
    # ====================================================================

    def _as_pattern_result(self, doc, feat, before, what: str) -> Dict:
        new = self._as_new_names(doc, before)
        if not new:
            return self._result(False, f"{what} non riuscita: SolidWorks non ha creato istanze. Controlla componente seme, "
                                "asse/direzione e conteggio.", SwErrors.swFeatureError)
        return self._result(True, f"{what}: {len(new)} nuove istanze", SwErrors.swSuccess,
                            {"feature": str(self._com(feat, "Name")) if feat is not None else None,
                             "new_components": new, "total_instances": len(new) + 1})

    def component_circular_pattern(self, components: list, axis, count: int = 6, angle: float = 360.0,
                                   equal_spacing: bool = True, reverse: bool = False, unit: str = None) -> Dict:
        """Ripetizione circolare di componenti attorno a un asse: 'Assi1@staffa-1' | {"face":[x,y,z] cilindrica, dell'assieme}
        | {"edge":[x,y,z]}. count = istanze totali (seme incluso); angle = angolo totale (equal_spacing) o passo."""
        try:
            doc, err = self._asm()
            if err:
                return err
            self._as_collapse(doc)
            comps, e = self._as_comps(doc, components, True)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            doc.ClearSelection2(True)
            for i, c in enumerate(comps):
                c.Select2(i > 0, 1)
            info, e = self._as_select_entity(doc, axis, unit, 2, True)
            if e:
                return self._result(False, f"Asse: {e}", SwErrors.swSelectionError)
            before = {str(c.Name2) for c in self._as_top_components(doc, False)}
            feat = doc.FeatureManager.FeatureCircularPattern5(int(count), math.radians(float(angle)), bool(reverse), "",
                                                              False, bool(equal_spacing), False, False, False, False,
                                                              1, 0.0, "", False)
            doc.ClearSelection2(True)
            return self._as_pattern_result(doc, feat, before, "Ripetizione circolare")
        except Exception as e:
            return self._as_fail("component_circular_pattern", e)

    def component_linear_pattern(self, components: list, direction1, count1: int = 2, spacing1: float = 10.0,
                                 direction2=None, count2: int = 1, spacing2: float = 10.0,
                                 reverse1: bool = False, reverse2: bool = False, unit: str = None) -> Dict:
        """Ripetizione lineare di componenti (1 o 2 direzioni). direction = spigolo {"edge":[x,y,z]} | asse 'Assi1@staffa-1'
        | faccia piana {"face":[x,y,z]}."""
        try:
            doc, err = self._asm()
            if err:
                return err
            self._as_collapse(doc)
            comps, e = self._as_comps(doc, components, True)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            doc.ClearSelection2(True)
            for i, c in enumerate(comps):
                c.Select2(i > 0, 1)
            info, e = self._as_select_entity(doc, direction1, unit, 2, True)
            if e:
                return self._result(False, f"Direzione 1: {e}", SwErrors.swSelectionError)
            two = direction2 is not None
            if two:
                info, e = self._as_select_entity(doc, direction2, unit, 3, True)
                if e:
                    return self._result(False, f"Direzione 2: {e}", SwErrors.swSelectionError)
            before = {str(c.Name2) for c in self._as_top_components(doc, False)}
            feat = doc.FeatureManager.FeatureLinearPattern5(
                int(count1), self._mmu(spacing1, unit), int(count2) if two else 1, self._mmu(spacing2, unit) if two else 0.0,
                bool(reverse1), bool(reverse2), "", "", False, False, False, False, False, False, False, False, False,
                False, 0.0, 0.0, False, False)
            doc.ClearSelection2(True)
            return self._as_pattern_result(doc, feat, before, "Ripetizione lineare")
        except Exception as e:
            return self._as_fail("component_linear_pattern", e)

    def component_derived_pattern(self, components: list, pattern_feature: str, pattern_component: str) -> Dict:
        """Ripetizione guidata da una ripetizione di feature: il componente seme segue le istanze della ripetizione
        (nome feature, es. 'RipetizioneCircolare1') presente nel pezzo `pattern_component`."""
        try:
            doc, err = self._asm()
            if err:
                return err
            self._as_collapse(doc)
            comps, e = self._as_comps(doc, components, True)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            pc, e = self._as_comp(doc, pattern_component, True)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            f = self._as_feature_of(pc, pattern_feature)
            if f is None:
                return self._result(False, f"Ripetizione '{pattern_feature}' non trovata in {pc.Name2}", SwErrors.swSelectionError)
            before = {str(c.Name2) for c in self._as_top_components(doc, False)}
            feat = None
            for seed_mark, pat_mark in ((2, 4), (1, 2), (4, 2), (1, 4)):
                doc.ClearSelection2(True)
                f.Select2(False, pat_mark)
                for c in comps:
                    c.Select2(True, seed_mark)
                try:
                    feat = doc.FeatureManager.InsertDerivedPattern()
                except Exception:
                    feat = None
                if self._as_new_names(doc, before):
                    break
            doc.ClearSelection2(True)
            return self._as_pattern_result(doc, feat, before, "Ripetizione guidata")
        except Exception as e:
            return self._as_fail("component_derived_pattern", e)

    def _as_comp_mass(self, comp) -> Dict:
        """Volume (mm3) e baricentro (mm) di un componente: nel suo pezzo e nell'assieme (posa reale)."""
        out = {}
        try:
            mp = comp.GetModelDoc2.Extension.CreateMassProperty
            com = [float(v) for v in mp.CenterOfMass]
            M, t = self._as_pose(comp)
            out["volume_mm3"] = round(float(mp.Volume) * 1e9, 4)
            out["center_of_mass_part_mm"] = [round(v * 1000, 4) for v in com]
            out["center_of_mass_assembly_mm"] = [round((sum(com[i] * M[j][i] for i in range(3)) + t[j]) * 1000, 4)
                                                 for j in range(3)]
        except Exception as e:
            out["mass_error"] = str(e)[:100]
        return out

    def _as_plane_world(self, doc, plane_obj, comp_name: str = None):
        """(normale unitaria, punto) di un piano (RefPlane o faccia piana) in coordinate ASSIEME; (None, None) se non leggibile."""
        try:
            n = o = None
            try:
                xf = list(plane_obj.GetSpecificFeature2.Transform.ArrayData)       # feature RefPlane: [6:9] normale, [9:12] origine
                n, o = xf[6:9], xf[9:12]
            except Exception:
                pp = self._com(self._com(plane_obj, "GetSurface"), "PlaneParams")  # faccia piana: normale + punto
                n, o = list(pp[0:3]), list(pp[3:6])
            if comp_name:
                comp, _ = self._as_comp(doc, comp_name)
                if comp is not None:
                    M, t = self._as_pose(comp)
                    n = [sum(M[j][i] * n[i] for i in range(3)) for j in range(3)]
                    o = [sum(M[j][i] * o[i] for i in range(3)) + t[j] for j in range(3)]
            ln = math.sqrt(sum(v * v for v in n))
            return [v / ln for v in n], o
        except Exception as e:
            logger.debug(f"_as_plane_world: {e}")
            return None, None

    def _as_mass_tensor(self, comp):
        """(baricentro [m], tensore d'inerzia 3x3 al baricentro) nel sistema del PEZZO; None se non leggibili."""
        try:
            ext = comp.GetModelDoc2.Extension
            mp = self._com(ext, "CreateMassProperty2")
            com = [float(v) for v in mp.CenterOfMass]
            try:
                I = [float(v) for v in mp.GetMomentOfInertia(0)]
            except Exception:
                I = None
            return com, I
        except Exception:
            return None, None

    def _as_last_mirror_feature(self, doc):
        last = None
        f = self._com(doc, "FirstFeature")
        while f is not None:
            try:
                if str(self._com(f, "GetTypeName2")) == "MirrorCompFeat":
                    last = f
            except Exception:
                pass
            f = self._com(f, "GetNextFeature")
        return last

    def _as_mirror_target(self, doc, src, new_name: str, n, p0) -> Dict:
        """Posa esatta dell'immagine speculare di `src` per il pezzo speculare `new_name` (piano: normale n, punto p0).
        1) si ricava quale asse k del pezzo e' stato riflesso da SolidWorks (F = riflessione di k, dal baricentro e dal tensore
        d'inerzia al baricentro, nel sistema del pezzo); 2) R' = Refl R_src F, t' = Refl_punto(t_src), cosi' R' F = Refl R_src."""
        new, _ = self._as_comp(doc, new_name, True)
        M0, t0 = self._as_pose(src)
        cs, Is = self._as_mass_tensor(src)
        cn, In = self._as_mass_tensor(new)
        if cs is None or cn is None:
            return {"error": "baricentro non leggibile"}
        best = None
        for k in range(3):
            F = [1.0, 1.0, 1.0]
            F[k] = -1.0
            err = sum(abs(cn[i] - F[i] * cs[i]) for i in range(3))
            if Is is not None and In is not None:
                err += sum(abs(In[3 * i + j] - F[i] * F[j] * Is[3 * i + j]) for i in range(3) for j in range(3))
            if best is None or err < best[0] - 1e-12:
                best = (err, k)
        err, k = best
        if err > 1e-6 and err > 1e-3 * (sum(abs(v) for v in cs) + 1e-9):
            return {"error": f"geometria speculare non riconosciuta come riflessione di un asse (scarto {err:.3g})"}
        Fm = [[-1.0 if (i == j == k) else (1.0 if i == j else 0.0) for j in range(3)] for i in range(3)]
        Refl = [[(1.0 if i == j else 0.0) - 2 * n[i] * n[j] for j in range(3)] for i in range(3)]
        mm = lambda A, B: [[sum(A[i][q] * B[q][j] for q in range(3)) for j in range(3)] for i in range(3)]
        Rn = mm(mm(Refl, M0), Fm)
        tnew = [sum(Refl[i][j] * t0[j] for j in range(3)) + 2 * sum(p0[q] * n[q] for q in range(3)) * n[i] for i in range(3)]
        return {"name": new_name, "R": Rn, "t": tnew, "axis": "xyz"[k]}

    def _as_mirror_pose_ok(self, doc, tg) -> bool:
        c, _ = self._as_comp(doc, tg["name"], True)
        M1, t1 = self._as_pose(c)
        return (all(abs(M1[i][j] - tg["R"][i][j]) < 1e-6 for i in range(3) for j in range(3)) and self._dist(t1, tg["t"]) < 1e-6)

    def _as_align_mirrored(self, doc, pairs, n, p0) -> Dict[str, Dict]:
        """Mette i pezzi speculari (pairs = [(originale, nome nuovo)]) esattamente nell'immagine speculare degli originali.
        SolidWorks sceglie l'orientamento del nuovo componente con un'opzione della feature di specchiatura che cambia fra sessioni (misurato:
        stessa geometria, R = diag(-1,-1,1) oppure diag(1,-1,-1)) e la feature rimette quella posa a ogni ricostruzione: se la posa non e'
        quella esatta si DISSOLVE la feature (IAssemblyDoc.DissolveComponentPattern: i componenti restano, indipendenti) e si imposta la posa."""
        targets, out = [], {}
        for src, nm in pairs:
            tg = self._as_mirror_target(doc, src, nm, n, p0)
            if "error" in tg:
                out[nm] = {"aligned": False, "reason": tg["error"]}
            else:
                targets.append(tg)
        dissolved = False
        before = {tg["name"]: self._as_pose(self._as_comp(doc, tg["name"], True)[0]) for tg in targets}
        if targets and not all(self._as_mirror_pose_ok(doc, tg) for tg in targets):
            f = self._as_last_mirror_feature(doc)
            if f is not None:
                doc.ClearSelection2(True)
                f.Select2(False, 0)
                dissolved = bool(self._com(doc, "DissolveComponentPattern"))
                doc.ClearSelection2(True)
                for tg in targets:
                    c, _ = self._as_comp(doc, tg["name"], True)
                    c.Transform2 = self._as_transform(tg["R"], tg["t"])
                try:
                    doc.ForceRebuild3(False)
                except Exception:
                    pass
        for tg in targets:
            c, _ = self._as_comp(doc, tg["name"], True)
            M1, t1 = self._as_pose(c)
            M0, t0 = before[tg["name"]]
            out[tg["name"]] = {"aligned": bool(self._as_mirror_pose_ok(doc, tg)), "mirrored_part_axis": tg["axis"],
                               "feature_dissolved": dissolved,
                               "initial_rotation_deg": _euler_deg(M0), "initial_position_mm": [round(v * 1000, 4) for v in t0],
                               "rotation_deg": _euler_deg(M1), "position_mm": [round(v * 1000, 4) for v in t1],
                               "plane_normal": [round(v, 6) for v in n]}
        return out

    def mirror_components(self, components: list, plane, orientation: int = 0, opposite_hand: bool = False,
                          name_suffix: str = "_mirror", folder: str = None, overwrite: bool = False,
                          align_exact: bool = True, unit: str = None) -> Dict:
        """Specchia componenti rispetto a un piano ('Piano destro' dell'assieme | 'Piano frontale@staffa-1' | {"face":[x,y,z]}).
        opposite_hand=False: crea ISTANZE dello stesso file (MirrorComponents3, componenti 'da istanziare'); `orientation`
          (0..3) sceglie come e' ruotata l'istanza (misurato: 0 = 180 gradi attorno a X, 1 = 180 gradi attorno a Z e spostamento
          dell'origine di 20 mm sul pezzo di prova, 2 = nessuna rotazione, 3 = 180 gradi attorno a Y; l'origine si riflette sempre).
        opposite_hand=True (C2): crea per ogni componente un NUOVO PEZZO speculare (versione 'opposta', geometria riflessa) salvato
          come <nome><name_suffix>.SLDPRT in `folder` (default: la cartella del pezzo originale). Se il file esiste rifiuta, salvo
          overwrite=true. Restituisce volume e baricentro (nel pezzo e nell'assieme) di ogni nuovo componente. align_exact=True
          (default): il nuovo componente viene messo esattamente nell'immagine speculare dell'originale (SolidWorks ne sceglie
          l'orientamento in base a una preferenza che cambia fra sessioni)."""
        try:
            doc, err = self._asm()
            if err:
                return err
            self._as_collapse(doc)
            comps, e = self._as_comps(doc, components, True)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            before = {str(c.Name2) for c in self._as_top_components(doc, False)}
            doc.ClearSelection2(True)
            if isinstance(plane, str) and "@" not in plane:
                plane_obj = self._as_feature_of_doc(doc, plane)
                if plane_obj is None:
                    return self._result(False, f"Piano '{plane}' non trovato nell'assieme", SwErrors.swSelectionError)
                plane_comp = None
            else:
                info, e = self._as_select_entity(doc, plane, unit, 0, False)
                if e:
                    return self._result(False, f"Piano: {e}", SwErrors.swSelectionError)
                plane_obj = doc.SelectionManager.GetSelectedObject6(1, -1)
                plane_comp = info.get("component")
                doc.ClearSelection2(True)
            from .modeling_base import disp_array
            empty_c = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, tuple())
            empty_s = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_BSTR, tuple())
            empty_i = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_I4, tuple())
            planned = []
            if opposite_hand:
                suffix = str(name_suffix or "_mirror")
                for c in comps:
                    src = self._as_comp_path(c)
                    base, ext = os.path.splitext(os.path.basename(src))
                    dst = os.path.join(os.path.abspath(folder) if folder else os.path.dirname(src), base + suffix + ext)
                    if os.path.exists(dst) and not overwrite:
                        return self._result(False, f"Rifiutato: il file {dst} esiste gia' e verrebbe SOVRASCRITTO. Ripeti con "
                                            "overwrite=true oppure scegli un altro name_suffix/folder.", SwErrors.swFileSaveError,
                                            {"refused": "file_exists", "file": dst})
                    planned.append(dst)
                for dst in planned:
                    if os.path.exists(dst):
                        try:
                            is_open = self._sw_app.GetOpenDocumentByName(dst) is not None
                        except Exception:
                            is_open = False
                        if is_open:
                            return self._result(False, f"Il file {dst} e' aperto in SolidWorks (e' gia' un componente?): non si puo' "
                                                "sovrascrivere. Elimina il componente e chiudi il documento, oppure usa un altro "
                                                "name_suffix.", SwErrors.swFileSaveError, {"refused": "file_in_use", "file": dst})
                        os.remove(dst)
                loc = os.path.abspath(folder) if folder else os.path.dirname(self._as_comp_path(comps[0]))
                doc.MirrorComponents3(plane_obj, empty_c, empty_i, False, disp_array(comps), False, empty_s if False else
                                      win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_BSTR,
                                                              tuple(os.path.splitext(p)[0] for p in planned)),
                                      1, suffix, loc, 0x1FFFF, False, False, False)
            else:
                ori = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_I4, tuple(int(orientation) for _ in comps))
                doc.MirrorComponents3(plane_obj, disp_array(comps), ori, False, empty_c, False, empty_s, 0, "", "", 0,
                                      False, False, False)
            doc.ClearSelection2(True)
            try:
                doc.ForceRebuild3(False)         # subito dopo MirrorComponents3 Transform2 e' ancora una posa intermedia
            except Exception:
                pass
            new = self._as_new_names(doc, before)
            if not new:
                return self._result(False, "MirrorComponents3 non ha creato componenti speculari.", SwErrors.swFeatureError)
            data = {"new_components": new, "opposite_hand": bool(opposite_hand)}
            if opposite_hand:
                rows = []
                pn, p0 = self._as_plane_world(doc, plane_obj, plane_comp) if align_exact else (None, None)
                srcs = {}
                for sc in comps:                       # il nuovo componente deriva dall'originale: stesso nome base + suffisso
                    base_name = str(sc.Name2).rsplit("-", 1)[0]
                    srcs[base_name + str(name_suffix or "_mirror")] = sc
                placement = {}
                if align_exact and pn is not None:
                    pairs = [(srcs[str(n).rsplit("-", 1)[0]], n) for n in new if str(n).rsplit("-", 1)[0] in srcs]
                    placement = self._as_align_mirrored(doc, pairs, pn, p0)
                for n in new:
                    c, _ = self._as_comp(doc, n, True)
                    if c is None:
                        continue
                    row = {"component": n, "file": self._as_comp_path(c)}
                    if align_exact:
                        row["placement"] = placement.get(n, {"aligned": False, "reason": "piano o componente d'origine non determinabili"})
                    row.update(self._as_comp_mass(c))
                    rows.append(row)
                data["mirrored"] = rows
                data["files_created"] = [r["file"] for r in rows if r["file"]]
            return self._result(True, f"Specchiati {len(comps)} componenti" + (" (versione opposta, nuovi file)" if opposite_hand else "")
                                + f": nuove istanze {new}", SwErrors.swSuccess, data)
        except Exception as e:
            return self._as_fail("mirror_components", e)

    def _as_feature_of_doc(self, doc, name: str):
        g = self._com(doc, "FirstFeature")
        while g is not None:
            if str(self._com(g, "Name")).lower() == name.lower():
                return g
            g = self._com(g, "GetNextFeature")
        return self._std_ref_feature(doc, name)        # piani standard / origine in qualunque lingua

    # ====================================================================
    # Accoppiamenti
    # ====================================================================

    def _as_mate_features(self, doc) -> list:
        out = []
        f = self._com(doc, "FirstFeature")
        while f is not None:
            try:
                if str(self._com(f, "GetTypeName2")) == "MateGroup":
                    s = self._com(f, "GetFirstSubFeature")
                    while s is not None:
                        out.append(s)
                        s = self._com(s, "GetNextSubFeature")
            except Exception:
                pass
            f = self._com(f, "GetNextFeature")
        return out

    def _as_feat_error(self, feat) -> int:
        try:
            code = feat.GetErrorCode2
            code = code[0] if isinstance(code, tuple) else code
            return int(code or 0)
        except Exception:
            return 0

    def _as_mate_dim(self, doc, feat, idx: int = 1):
        name = str(self._com(feat, "Name"))
        try:
            return doc.Parameter(f"D{idx}@{name}")
        except Exception:
            return None

    def _as_mate_info(self, doc, feat) -> Dict:
        name = str(self._com(feat, "Name"))
        info = {"name": name, "feature_type": str(self._com(feat, "GetTypeName2"))}
        try:
            sp = self._com(feat, "GetSpecificFeature2")
            t = int(self._com(sp, "Type"))
            info["type"] = MATE_NAMES.get(t, str(t))
            info["alignment"] = ALIGN_NAMES.get(int(self._com(sp, "Alignment")), "?")
            n = int(self._com(sp, "GetMateEntityCount"))
            comps = []
            for i in range(n):
                try:
                    comps.append(str(self._com(sp.MateEntity(i), "ReferenceComponent").Name2))
                except Exception:
                    comps.append("?")
            info["components"] = comps
            try:
                info["flipped"] = bool(self._com(sp, "Flipped"))
            except Exception:
                pass
            if t in (5, 6):
                d = self._as_mate_dim(doc, feat)
                if d is not None:
                    v = float(d.SystemValue)
                    info["value"] = round(v * 1000, 6) if t == 5 else round(math.degrees(v), 6)
                    info["unit"] = "mm" if t == 5 else "deg"
                    # accoppiamenti con limite (MateLimitDistanceDim / MateLimitPlanarAngleDim): intervallo ammesso per D1
                    try:
                        vmax, vmin = float(sp.MaximumVariation), float(sp.MinimumVariation)
                        if "Limit" in info["feature_type"]:
                            k = 1000.0 if t == 5 else 180.0 / math.pi
                            info["limits"] = {"min": round((v + vmin) * k, 6), "max": round((v + vmax) * k, 6)}
                    except Exception:
                        pass
            elif t in (10, 17):
                try:
                    md = self._com(feat, "GetDefinition")
                    if t == 10:
                        # SolidWorks restituisce il rapporto scambiato rispetto a quello passato (numeratore <-> denominatore)
                        info["gear_ratio_in_model"] = [float(md.GearRatioNumerator), float(md.GearRatioDenominator)]
                    else:
                        info["pitch_mm_per_rev"] = round(float(md.RevolutionVal) * 1000, 6)
                        info["revolution_type"] = int(md.RevolutionType)
                except Exception as e:
                    info["definition_error"] = str(e)[:80]
        except Exception as e:
            info["detail_error"] = str(e)
        try:
            info["suppressed"] = bool(self._com(feat, "IsSuppressed"))
        except Exception:
            pass
        code = self._as_feat_error(feat)
        info["error_code"] = code
        info["in_error"] = code != 0
        return info

    def add_mate(self, mate_type: str, entity1, entity2, entity3=None, align: str = "closest", flip: bool = False,
                 distance: float = None, angle: float = None, min_value: float = None, max_value: float = None,
                 gear_ratio: list = None, pitch: float = None, width_mode: str = None, tab_entities: list = None,
                 lock_rotation: bool = False, unit: str = None) -> Dict:
        """Accoppiamento fra due entita' di componenti diversi (o una e un piano/asse dell'assieme).
        mate_type: coincident | parallel | perpendicular | tangent | concentric | distance | angle | lock | symmetric
        (entity3 = piano di simmetria) | width (entity1+entity2 = facce larghezza, tab_entities = facce linguetta) |
        gear (gear_ratio=[a,b]) | screw (pitch).
        Entita': "Piano frontale@perno-1" | "Assi1@staffa-1" | {"face":[x,y,z]} (coordinate assieme, mm) | {"component":..,"plane":..}.
        Limite: min_value/max_value con distance|angle (mm / gradi). align: closest | aligned | anti_aligned."""
        try:
            doc, err = self._asm()
            if err:
                return err
            key = str(mate_type).lower().strip()
            mt = MATE_TYPES.get(key)
            if mt is None:
                return self._result(False, f"Tipo di accoppiamento sconosciuto: {mate_type}. Validi: {', '.join(MATE_TYPES)}",
                                    SwErrors.swInvalidInput)
            al = ALIGN.get(str(align).lower().replace(" ", "_"))
            if al is None:
                return self._result(False, "align: closest | aligned | anti_aligned", SwErrors.swInvalidInput)
            self._as_collapse(doc)
            n_before = len(self._as_mate_features(doc))
            doc.ClearSelection2(True)
            infos = []
            ents = [entity1, entity2] + ([entity3] if entity3 is not None else [])
            marks = [1, 1, 2] if mt == 8 else [1, 1, 1]
            for i, spec in enumerate(ents):
                info, e = self._as_select_entity(doc, spec, unit, marks[i], i > 0)
                if e:
                    doc.ClearSelection2(True)
                    return self._result(False, f"Entita' {i + 1}: {e}", SwErrors.swSelectionError)
                infos.append(info)
            for spec in (tab_entities or []):
                info, e = self._as_select_entity(doc, spec, unit, 2, True)
                if e:
                    doc.ClearSelection2(True)
                    return self._result(False, f"Entita' linguetta: {e}", SwErrors.swSelectionError)
                infos.append(info)
            # concentrico fra due assi di riferimento: SolidWorks lo rifiuta -> coincidente (stesso vincolo)
            used = key
            if mt == 1 and all(i_.get("kind") == "RefAxis" for i_ in infos[:2]):
                mt, used = 0, "coincident (assi)"
            dist_m = self._mmu(distance, unit) if distance is not None else 0.0
            ang_r = math.radians(float(angle)) if angle is not None else 0.0
            dmax = dmin = amax = amin = 0.0
            if mt == 5 and (min_value is not None or max_value is not None):
                dmin = self._mmu(min_value if min_value is not None else (distance or 0.0), unit)
                dmax = self._mmu(max_value if max_value is not None else (distance or 0.0), unit)
                if distance is None:
                    dist_m = (dmin + dmax) / 2
            if mt == 6 and (min_value is not None or max_value is not None):
                amin = math.radians(float(min_value if min_value is not None else (angle or 0.0)))
                amax = math.radians(float(max_value if max_value is not None else (angle or 0.0)))
                if angle is None:
                    ang_r = (amin + amax) / 2
            g1, g2 = (gear_ratio or [1, 1])[:2]
            wopt = {"centered": 0, "free": 1, "dimension": 2, "percent": 3}.get(str(width_mode or "centered").lower(), 0)
            err = _i4()
            if mt == 11:
                # larghezza: AddMate5 restituisce sempre 'errore sconosciuto' (misurato con ogni combinazione di Mark/allineamento);
                # funziona CreateMateData(11) + WidthSelection/TabSelection + CreateMate.
                from .modeling_base import disp_array
                sm = doc.SelectionManager
                objs = [sm.GetSelectedObject6(i, -1) for i in range(1, int(sm.GetSelectedObjectCount2(-1)) + 1)]
                if len(objs) < 4:
                    doc.ClearSelection2(True)
                    return self._result(False, "Larghezza: servono 2 facce di larghezza (entity1, entity2) e 1 o 2 facce della "
                                        "linguetta (tab_entities)", SwErrors.swInvalidInput)
                md = doc.CreateMateData(11)
                md.WidthSelection = disp_array(objs[:2])
                md.TabSelection = disp_array(objs[2:])
                md.ConstraintType = int(wopt)
                if wopt == 2:
                    md.DistanceFromEnd = dist_m
                elif wopt == 3:
                    md.PercentDistanceFromEnd = float(distance if distance is not None else 50.0) / 100.0
                mate = doc.CreateMate(md)
                code = 1 if mate is not None else 0
            elif mt == 17:
                # vite: il passo (distanza per giro) si imposta solo con i dati dell'accoppiamento (AddMate5 lascia 1 giro/1 m)
                from .modeling_base import disp_array
                sm = doc.SelectionManager
                objs = [sm.GetSelectedObject6(i, -1) for i in range(1, int(sm.GetSelectedObjectCount2(-1)) + 1)]
                if len(objs) < 2 or pitch is None:
                    doc.ClearSelection2(True)
                    return self._result(False, "Vite: servono due facce cilindriche (entity1, entity2) e il passo (pitch, mm/giro)",
                                        SwErrors.swInvalidInput)
                md = doc.CreateMateData(17)
                md.EntitiesToMate = disp_array(objs[:2])
                md.RevolutionType = 1                      # swDistancePerRevolution (0 = giri per unita' di lunghezza)
                md.RevolutionVal = self._mmu(pitch, unit)
                md.Reverse = bool(flip)
                mate = doc.CreateMate(md)
                code = 1 if mate is not None else 0
                if mate is not None:
                    # il passo impostato in CreateMateData NON viene memorizzato (resta 1 m/giro): si scrive nella quota D1 dell'accoppiamento
                    nf = self._as_mate_features(doc)[-1]
                    d1 = self._as_mate_dim(doc, nf, 1)
                    if d1 is not None:
                        d1.SystemValue = self._mmu(pitch, unit)
                        doc.ForceRebuild3(False)
            else:
                mate = doc.AddMate5(mt, al, bool(flip), dist_m, dmax, dmin, float(g1), float(g2), ang_r, amax, amin, False,
                                    bool(lock_rotation), wopt, err)
                code = int(err.value)
            doc.ClearSelection2(True)
            if mate is None:
                return self._result(False, f"Accoppiamento {used} non creato: {ADD_MATE_ERRORS.get(code, code)}",
                                    SwErrors.swFeatureError, {"error": code, "selected": infos})
            try:
                self._com(doc, "EditRebuild3")
            except Exception:
                pass
            # trova la feature appena creata (ultima della lista)
            mates = self._as_mate_features(doc)
            newf = mates[-1] if len(mates) > n_before else None
            info = self._as_mate_info(doc, newf) if newf is not None else {}
            info["requested"] = used
            info["selected"] = infos
            info["mates_total"] = len(mates)
            if info.get("in_error"):
                return self._result(False, f"Accoppiamento {info.get('name')} creato ma IN ERRORE (codice "
                                    f"{info.get('error_code')}): probabile sovravincolo o geometria incompatibile.",
                                    SwErrors.swFeatureError, info)
            return self._result(True, f"Accoppiamento {info.get('name', used)} creato", SwErrors.swSuccess, info)
        except Exception as e:
            return self._as_fail("add_mate", e)

    def list_mates(self) -> Dict:
        """Elenco accoppiamenti: nome, tipo, allineamento, componenti, valore (distanza/angolo), soppresso, errore."""
        try:
            doc, err = self._asm()
            if err:
                return err
            infos = [self._as_mate_info(doc, f) for f in self._as_mate_features(doc)]
            bad = [i["name"] for i in infos if i.get("in_error")]
            return self._result(True, f"{len(infos)} accoppiamenti" + (f", {len(bad)} in errore" if bad else ""),
                                SwErrors.swSuccess, {"count": len(infos), "mates": infos, "in_error": bad})
        except Exception as e:
            return self._as_fail("list_mates", e)

    def _as_mate_by_name(self, doc, name: str):
        for f in self._as_mate_features(doc):
            if str(self._com(f, "Name")).lower() == str(name).lower():
                return f
        return None

    def edit_mate(self, name: str, value: float = None, flip: bool = None, suppress: bool = None,
                  max_value: float = None, min_value: float = None, unit: str = None) -> Dict:
        """Modifica un accoppiamento: valore (distanza in mm / angolo in gradi), limiti, inversione, soppressione.
        Per gli accoppiamenti CON LIMITE (distanza/angolo) il valore e' la posizione corrente e puo' variare solo fra
        min_value e max_value: un valore fuori intervallo viene RIFIUTATO (il componente resta dov'era) e si riportano i limiti.
        min_value/max_value cambiano i limiti (devono contenere il valore). Con SetTransformAndSolve2 un componente con un
        accoppiamento a limite torna sempre al valore nominale: il modo di muoverlo nell'intervallo e' questo."""
        try:
            doc, err = self._asm()
            if err:
                return err
            self._as_collapse(doc)
            target = self._as_mate_by_name(doc, name)
            if target is None:
                return self._result(False, f"Accoppiamento '{name}' non trovato", SwErrors.swSelectionError)
            sp = self._com(target, "GetSpecificFeature2")
            t = int(self._com(sp, "Type"))
            changed = {}
            if value is not None or min_value is not None or max_value is not None:
                if t not in (5, 6, 17):
                    return self._result(False, "Il valore si modifica solo per accoppiamenti distanza/angolo/vite", SwErrors.swInvalidInput)
                conv = (lambda v: self._mmu(v, unit)) if t in (5, 17) else (lambda v: math.radians(float(v)))
                if (min_value is not None or max_value is not None) and t == 17:
                    return self._result(False, "La vite non ha limiti", SwErrors.swInvalidInput)
                if min_value is not None or max_value is not None:
                    md = self._com(target, "GetDefinition")
                    cur = self._as_mate_info(doc, target)
                    if "limits" not in cur:
                        return self._result(False, "Questo accoppiamento non ha limiti: ricrealo con add_mate(min_value, max_value)",
                                            SwErrors.swInvalidInput, cur)
                    lo = cur["limits"]["min"] if min_value is None else float(min_value)
                    hi = cur["limits"]["max"] if max_value is None else float(max_value)
                    if lo > hi:
                        return self._result(False, f"Limite minimo {lo} maggiore del massimo {hi}", SwErrors.swInvalidInput)
                    if t == 5:
                        md.MinimumDistance, md.MaximumDistance = conv(lo), conv(hi)
                    else:
                        md.MinimumAngle, md.MaximumAngle = conv(lo), conv(hi)
                    ok = target.ModifyDefinition(md, doc, win32com.client.VARIANT(pythoncom.VT_DISPATCH, None))
                    if not ok:
                        return self._result(False, "ModifyDefinition ha rifiutato i nuovi limiti", SwErrors.swFeatureError)
                    target = self._as_mate_by_name(doc, name)
                    changed["limits"] = {"min": lo, "max": hi}
                if value is not None:
                    d = self._as_mate_dim(doc, target, 1)
                    if d is None:
                        return self._result(False, "Quota D1 dell'accoppiamento non trovata", SwErrors.swFeatureError)
                    d.SystemValue = conv(value)
                    doc.ForceRebuild3(False)
                    target = self._as_mate_by_name(doc, name)
                    after = self._as_mate_info(doc, target)
                    if t == 17:
                        after["value"] = after.get("pitch_mm_per_rev")
                    if abs(after.get("value", 1e99) - float(value)) > 1e-6 * max(1.0, abs(float(value))):
                        lim = after.get("limits")
                        return self._result(False, f"Valore {value} rifiutato: l'accoppiamento resta a {after.get('value')} "
                                            + (f"(limiti ammessi {lim['min']} .. {lim['max']})" if lim else "(valore non applicabile)"),
                                            SwErrors.swFeatureError, after)
                    changed["D1"] = value
            if flip is not None:
                try:
                    sp.Flipped = bool(flip)
                    changed["flip"] = bool(flip)
                except Exception as e:
                    return self._result(False, f"Inversione non riuscita: {e}", SwErrors.swFeatureError)
            if suppress is not None:
                doc.ClearSelection2(True)
                target.Select2(False, 0)
                self._com(doc, "EditSuppress2" if suppress else "EditUnsuppress2")
                doc.ClearSelection2(True)
                changed["suppress"] = bool(suppress)
            doc.ForceRebuild2(False)
            target = self._as_mate_by_name(doc, name)
            info = self._as_mate_info(doc, target)
            if info.get("in_error"):
                return self._result(False, f"Modificato ma in errore (codice {info['error_code']})", SwErrors.swFeatureError, info)
            return self._result(True, f"Accoppiamento {name} modificato: {changed}", SwErrors.swSuccess, info)
        except Exception as e:
            return self._as_fail("edit_mate", e)

    def get_assembly_status(self, probe_dof: bool = True) -> Dict:
        """Stato dei vincoli: per componente (fisso, completamente vincolato / sottovincolato / sovravincolato, moti liberi misurati con
        probe_dof), accoppiamenti in errore, e se l'assieme e' completamente vincolato."""
        try:
            doc, err = self._asm()
            if err:
                return err
            self._as_collapse(doc)
            try:
                doc.ForceRebuild2(False)
            except Exception:
                pass
            comps = self._as_top_components(doc, True)
            rows, free, over = [], [], []
            for c in sorted(comps, key=lambda c: str(c.Name2)):
                st = self._as_state(c)
                try:
                    code = int(self._com(c, "GetConstrainedStatus"))
                except Exception:
                    code = 1
                row = {"name": str(c.Name2), "fixed": st["fixed"], "suppressed": st["suppressed"],
                       "constrained": CONSTRAINED.get(code, "?"), "status_code": code}
                if probe_dof and not st["fixed"] and not st["suppressed"] and code != 3:
                    row.update(self._as_dof(c))
                rows.append(row)
                if st["suppressed"]:
                    continue
                if code == 4:
                    over.append(row["name"])
                elif not st["fixed"] and code != 3:
                    free.append(row["name"])
            bad = [self._as_mate_info(doc, f) for f in self._as_mate_features(doc)]
            bad = [m["name"] for m in bad if m.get("in_error")]
            full = not free and not over and not bad
            msg = ("Assieme completamente vincolato" if full else
                   f"Assieme NON completamente vincolato: {len(free)} sottovincolati, {len(over)} sovravincolati, "
                   f"{len(bad)} accoppiamenti in errore")
            return self._result(True, msg, SwErrors.swSuccess,
                                {"fully_constrained": full, "under_constrained": free, "over_constrained": over,
                                 "mates_in_error": bad, "components": rows, "mates": len(self._as_mate_features(doc))})
        except Exception as e:
            return self._as_fail("get_assembly_status", e)
