"""
Assiemi: vista esplosa (C3, C4). Mixin `AssemblyExplodeMixin` (usato da AssemblyOperations).

C3 - tipi di passo
  * traslazione lungo X/Y/Z dell'assieme (come prima);
  * direzione LIBERA: vettore [vx,vy,vz] qualsiasi -> SolidWorks accetta solo gli assi X/Y/Z dell'assieme in AddExplodeStep2, quindi
    il vettore e' scomposto in UN passo per asse non nullo (stesso componente, stesso verso); lo spostamento totale e' esattamente
    distanza * versore. Direzione da un'ENTITA' (spigolo, asse, faccia cilindrica, es. {"edge":[x,y,z]} o "Assi1@perno-1"): passo
    nativo con IExplodeStep.SetExplodeDirection (qualsiasi orientamento; il verso e' quello dell'entita');
  * RADIALE: "radial_axis": entita' (faccia cilindrica/asse) -> IConfiguration.AddRadialExplodeStep(distanza, angolo, divergente):
    i componenti si allontanano dall'asse in direzione radiale e ruotano di `angle` (verificato);
  * rotazione nei passi di traslazione: AddExplodeStep2(.., ExplAng, RotAxisIndex, ..) NON memorizza l'angolo in SolidWorks 2026
    (RotationAngle resta 0 con qualunque combinazione); il passo restituisce `rotation_applied` = False e il motivo. La rotazione
    funziona nei passi radiali (`angle`). Neanche scrivere IExplodeStep.RotationAngle dopo la creazione funziona (resta 0, 2026-10-17).
    Rotazione SENZA spostamento: un passo radiale con distanza 0 e `angle` dopo la traslazione ruota il componente di `angle` attorno
    alla direzione radiale (dall'asse scelto al componente), misurato 45,0000 gradi con distanza radiale invariata; l'asse quindi non
    e' libero, e un componente coassiale all'asse radiale da' errore (codice 1, direzione radiale indefinita).
  Dopo aver aggiunto i passi si commuta ShowExploded2(False/True): senza questo Transform2 restituisce le pose vecchie.

C4 - esplosione automatica
  * nativa: IAssemblyDoc.AutoExplode (PROPRIETA' in late binding: leggerla la esegue). Crea la vista e un passo "Catena" con tutti
    i componenti, lungo una direzione scelta da SolidWorks; non sempre produce passi (assieme con vista gia' presente = niente);
  * euristica ('mates'): ordine di smontaggio dalla struttura degli accoppiamenti (profondita' di accoppiamento dal componente
    base: i piu' interni escono per primi) e direzione lungo l'asse della coppia concentrica; il verso e' quello del lato "testa"
    (la parte piu' larga del componente, che non puo' passare dal foro), altrimenti il lato opposto al componente a cui e' accoppiato.
    Le distanze si ricavano dai bounding box: ogni componente si sposta lungo la sua direzione finche' il suo box dista almeno
    `gap` mm dai box di tutti gli altri (relaxation fino a convergenza), poi si controlla lo stato esploso REALE (GetBox).
"""

import math
import logging
from typing import Dict, List, Optional, Tuple

import win32com.client
import pythoncom

from ..constants import SwErrors

logger = logging.getLogger(__name__)

_DIRS = {"x": (0, False), "+x": (0, False), "-x": (0, True), "y": (1, False), "+y": (1, False), "-y": (1, True),
         "z": (2, False), "+z": (2, False), "-z": (2, True)}


def _i4():
    return win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _norm(a):
    return math.sqrt(_dot(a, a))


def _unit(a):
    n = _norm(a)
    return [x / n for x in a] if n > 1e-15 else [0.0, 0.0, 0.0]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


class AssemblyExplodeMixin:
    """Vista esplosa: passi (traslazione/vettore libero/entita'/radiale), esplosione automatica nativa ed euristica."""

    # ====================================================================
    # Lettura
    # ====================================================================

    def _ex_steps(self, doc) -> List[Dict]:
        out = []
        try:
            cfg = self._ex_config(doc)
            n = int(cfg.GetNumberOfExplodeSteps)
            for i in range(n):
                st = cfg.GetExplodeStep(i)
                comps = [str(c.Name2) for c in (self._com(st, "GetComponents") or ())]
                row = {"index": i, "name": str(st.Name), "components": comps,
                       "distance_mm": round(float(st.ExplodeDistance) * 1000, 4),
                       "reverse": bool(st.ReverseTranslationDirection),
                       "rotation_deg": round(math.degrees(float(st.RotationAngle)), 4)}
                try:
                    row["type"] = {0: "translate", 1: "radial", 2: "subassembly"}.get(int(st.ExplodeStepType), "?")
                except Exception:
                    pass
                out.append(row)
        except Exception as e:
            logger.debug(f"_ex_steps: {e}")
        return out

    def _ex_refresh(self, doc, name: str = None) -> None:
        """Commuta esploso/compresso: le pose (Transform2/GetBox) si aggiornano solo cosi'."""
        names = self._ex_names(doc)
        if not names:
            return
        nm = name or names[0]
        doc.ShowExploded2(False, nm)
        doc.ShowExploded2(True, nm)

    def _ex_poses(self, doc) -> Dict[str, Dict]:
        """Pose ESPLOSE (assieme esploso attivo) dei componenti di primo livello: posizione mm, rotazione, matrice."""
        from .assembly import _euler_deg
        out = {}
        for c in self._as_top_components(doc, True):
            try:
                M, t = self._as_pose(c, ignore_explode=False)
                b = c.GetBox(False, False)
                out[str(c.Name2)] = {"position_mm": [round(v * 1000, 4) for v in t], "rotation_deg": _euler_deg(M),
                                     "matrix": [[round(v, 6) for v in row] for row in M],
                                     "box_mm": [round(v * 1000, 3) for v in b]}
            except Exception as e:
                out[str(c.Name2)] = {"error": str(e)[:80]}
        return out

    # ====================================================================
    # Direzione e passi
    # ====================================================================

    def _ex_parse_dir(self, direction):
        """'x' | '-y' | [vx,vy,vz] | entita'. -> ((kind, dati), errore). kind: 'axis' (idx, inverti) | 'vector' (versore) | 'entity'"""
        if isinstance(direction, str) and direction.strip().lower() in _DIRS:
            return ("axis", _DIRS[direction.strip().lower()]), None
        if isinstance(direction, (list, tuple)) and len(direction) == 3 and all(isinstance(v, (int, float)) for v in direction):
            v = [float(c) for c in direction]
            if _norm(v) < 1e-12:
                return None, "direction: vettore nullo"
            u = _unit(v)
            idx = max(range(3), key=lambda i: abs(u[i]))
            if sum(abs(u[i]) for i in range(3) if i != idx) < 1e-9:
                return ("axis", (idx, u[idx] < 0)), None
            return ("vector", u), None
        if isinstance(direction, (dict, str)):
            return ("entity", direction), None
        return None, "direction: x, y, z, -x, -y, -z, un vettore [vx,vy,vz] oppure un'entita' (spigolo/asse/faccia cilindrica)"

    def _ex_entity_object(self, doc, spec, unit=None):
        info, e = self._as_select_entity(doc, spec, unit, 0, False)
        if e:
            return None, e
        obj = doc.SelectionManager.GetSelectedObject6(1, -1)
        doc.ClearSelection2(True)
        return obj, None

    def _ex_add_step(self, doc, comps, direction, distance, unit=None, reverse=False, rotate_angle=0.0, rotate_axis=None,
                     radial_axis=None, angle=0.0, diverge=False):
        """Aggiunge UNO o piu' passi (vettore libero = fino a 3). -> (lista di passi creati [{'obj','name',...}], errore)"""
        cfg = self._ex_config(doc)
        dist = abs(self._mmu(distance, unit))
        made = []

        def new_step(call):
            n0 = int(cfg.GetNumberOfExplodeSteps)
            er = _i4()
            st = call(er)
            doc.ClearSelection2(True)
            if st is None or int(cfg.GetNumberOfExplodeSteps) != n0 + 1:
                if int(cfg.GetNumberOfExplodeSteps) > n0:
                    try:
                        cfg.DeleteExplodeStep(str(cfg.GetExplodeStep(int(cfg.GetNumberOfExplodeSteps) - 1).Name))
                    except Exception:
                        pass
                return None, er.value
            return st, 0

        if radial_axis is not None:
            self._as_select_comps(doc, comps, 1)
            info, e = self._as_select_entity(doc, radial_axis, unit, 2, True)
            if e:
                doc.ClearSelection2(True)
                return None, f"Asse radiale: {e}"
            ang = math.radians(float(angle or rotate_angle or 0.0))
            st, code = new_step(lambda er: cfg.AddRadialExplodeStep(dist, ang, bool(diverge), er))
            if st is None:
                return None, f"AddRadialExplodeStep fallito (codice {code}: 3 = nessun componente, 4 = asse radiale non valido)"
            made.append({"obj": st, "name": str(st.Name), "type": "radial", "distance_mm": round(dist * 1000, 4),
                         "angle_deg": round(math.degrees(float(st.RotationAngle)), 4)})
            return made, None
        kind, e = self._ex_parse_dir(direction)
        if e:
            return None, e
        kind, data = kind
        rot = math.radians(float(rotate_angle or 0.0))
        rot_idx = (_DIRS.get(str(rotate_axis or "x").lower()) or (0, False))[0] if rotate_angle else -1
        if kind == "axis":
            plan = [(data[0], data[1] != bool(reverse), dist, None)]
        elif kind == "vector":
            plan = []
            for i in range(3):
                if abs(data[i]) > 1e-9:
                    plan.append((i, (data[i] < 0) != bool(reverse), dist * abs(data[i]), None))
        else:
            obj, e = self._ex_entity_object(doc, data, unit)
            if e:
                return None, f"Direzione: {e}"
            plan = [(0, bool(reverse), dist, obj)]
        for (idx, rev, d, obj) in plan:
            self._as_select_comps(doc, comps, 1)
            st, code = new_step(lambda er: cfg.AddExplodeStep2(d, idx, rev, rot, rot_idx, False, False, True, er))
            if st is None:
                return None, f"AddExplodeStep2 fallito (codice {code}: 3 = nessun componente selezionato)"
            if obj is not None:
                try:
                    st.SetExplodeDirection(obj, 0)
                except Exception as ex:
                    return None, f"SetExplodeDirection fallito: {str(ex)[:80]}"
            row = {"obj": st, "name": str(st.Name), "type": "translate", "axis": "xyz"[idx] if obj is None else "entity",
                   "reverse": rev, "distance_mm": round(d * 1000, 4)}
            if rotate_angle:
                got = float(st.RotationAngle)
                row["rotation_requested_deg"] = float(rotate_angle)
                row["rotation_applied"] = abs(got - rot) < 1e-9
                if not row["rotation_applied"]:
                    row["rotation_note"] = ("SolidWorks non memorizza la rotazione nei passi di traslazione (RotationAngle=0): "
                                            "aggiungi un passo radiale con distanza 0 e `angle` (ruota attorno alla direzione "
                                            "radiale dall'asse scelto al componente)")
            made.append(row)
        return made, None

    def _ex_step_specs(self, doc, st: Dict, unit):
        comps, e = self._as_comps(doc, st.get("components"), True)
        if e:
            return None, e
        return comps, None

    def _ex_new_view(self, doc):
        names0 = set(self._ex_names(doc))
        getattr(doc, "CreateExplodedView")        # proprieta': leggerla crea la vista
        names1 = self._ex_names(doc)
        new = [n for n in names1 if n not in names0]
        if not new:
            return None
        cfg = self._ex_config(doc)
        for s in self._ex_steps(doc):             # un eventuale passo vuoto creato all'apertura viene tolto
            if not s["components"] or (s["distance_mm"] == 0 and s.get("type") == "translate" and len(s["components"]) >= len(self._as_top_components(doc, True))):
                try:
                    cfg.DeleteExplodeStep(s["name"])
                except Exception:
                    pass
        return new[0]

    def create_exploded_view(self, steps: list, unit: str = None, keep_exploded: bool = True) -> Dict:
        """Crea una vista esplosa nella configurazione attiva con una serie di passi (distanze in mm, angoli in gradi).
        Ogni passo: {"components": ["perno-1"], ...} piu':
          traslazione: "direction": "x"|"-y"|[1,1,0] (vettore LIBERO, scomposto in passi X/Y/Z)|{"edge":[x,y,z]} / "Assi1@perno-1"
                       (direzione di un'entita'), "distance", "reverse";
          radiale:     "radial_axis": faccia cilindrica/asse (es. {"face":[x,y,z],"component":"staffa-1"}), "distance", "angle"
                       (rotazione, gradi), "diverge" (divergente dall'asse).
        keep_exploded: lascia l'assieme esploso. Il risultato riporta le pose esplose dei componenti (`poses`)."""
        try:
            doc, err = self._asm()
            if err:
                return err
            if not steps:
                return self._result(False, "Servono passi di esplosione (steps)", SwErrors.swInvalidInput)
            self._as_collapse(doc)
            vname = self._ex_new_view(doc)
            if vname is None:
                return self._result(False, "SolidWorks non ha creato la vista esplosa.", SwErrors.swFeatureError)
            done = []
            for i, st in enumerate(steps):
                comps, e = self._as_comps(doc, st.get("components"), True)
                if e:
                    return self._result(False, f"Passo {i + 1}: {e}", SwErrors.swSelectionError, {"done": done})
                made, e = self._ex_add_step(doc, comps, st.get("direction", "x"), st.get("distance", 30), unit,
                                            bool(st.get("reverse", False)), float(st.get("rotate_angle", 0) or 0),
                                            st.get("rotate_axis"), st.get("radial_axis"), float(st.get("angle", 0) or 0),
                                            bool(st.get("diverge", False)))
                if e:
                    return self._result(False, f"Passo {i + 1}: {e}", SwErrors.swFeatureError, {"done": done})
                for m in made:
                    m.pop("obj", None)
                    m["components"] = [str(c.Name2) for c in comps]
                    done.append(m)
            self._ex_refresh(doc, vname)
            data = {"exploded_view": vname, "steps": done, "exploded": bool(self._com(doc, "IsExploded")),
                    "configuration": str(self._ex_config(doc).Name), "poses": self._ex_poses(doc)}
            if not keep_exploded:
                doc.ShowExploded2(False, vname)
                data["exploded"] = bool(self._com(doc, "IsExploded"))
            return self._result(True, f"Vista esplosa '{vname}' con {len(done)} passi", SwErrors.swSuccess, data)
        except Exception as e:
            return self._as_fail("create_exploded_view", e)

    def add_explode_step(self, components: list, direction="x", distance: float = 30.0, reverse: bool = False,
                         rotate_angle: float = 0.0, rotate_axis: str = None, radial_axis=None, angle: float = 0.0,
                         diverge: bool = False, unit: str = None) -> Dict:
        """Aggiunge un passo alla vista esplosa esistente (la crea se non c'e'). direction: x|y|z|-x.. | vettore libero [vx,vy,vz]
        (scomposto in passi X/Y/Z) | entita' (spigolo/asse/faccia cilindrica). radial_axis: passo RADIALE attorno all'asse indicato
        (distance, angle gradi, diverge). Riporta le pose esplose (`poses`)."""
        try:
            doc, err = self._asm()
            if err:
                return err
            self._as_collapse(doc)
            if not self._ex_names(doc):
                if self._ex_new_view(doc) is None:
                    return self._result(False, "SolidWorks non ha creato la vista esplosa.", SwErrors.swFeatureError)
            comps, e = self._as_comps(doc, components, True)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            made, e = self._ex_add_step(doc, comps, direction, distance, unit, reverse, rotate_angle, rotate_axis,
                                        radial_axis, angle, diverge)
            if e:
                return self._result(False, e, SwErrors.swFeatureError)
            for m in made:
                m.pop("obj", None)
            self._ex_refresh(doc)
            return self._result(True, f"Aggiunti {len(made)} passi: {', '.join(m['name'] for m in made)}", SwErrors.swSuccess,
                                {"new_steps": made, "steps": self._ex_steps(doc), "poses": self._ex_poses(doc)})
        except Exception as e:
            return self._as_fail("add_explode_step", e)

    def list_exploded_views(self) -> Dict:
        """Viste esplose della configurazione attiva con i loro passi; se l'assieme e' esploso, anche le pose esplose."""
        try:
            doc, err = self._asm()
            if err:
                return err
            names = self._ex_names(doc)
            data = {"views": names, "exploded": bool(self._com(doc, "IsExploded")),
                    "steps": self._ex_steps(doc), "configuration": str(self._ex_config(doc).Name)}
            if data["exploded"]:
                self._ex_refresh(doc)
                data["poses"] = self._ex_poses(doc)
            return self._result(True, f"{len(names)} viste esplose", SwErrors.swSuccess, data)
        except Exception as e:
            return self._as_fail("list_exploded_views", e)

    # ====================================================================
    # Esplosione automatica (C4)
    # ====================================================================

    def _ex_cyl_any(self, comp) -> List[Dict]:
        """Facce cilindriche del componente con asse in coordinate ASSIEME (qualsiasi orientamento), posa reale."""
        out = []
        try:
            M, t = self._as_pose(comp)
        except Exception:
            return out
        for b in (comp.GetBodies2(0) or ()):
            for f in (b.GetFaces() or ()):
                try:
                    sf = f.GetSurface
                    if not sf.IsCylinder:
                        continue
                    cp = sf.CylinderParams
                    o = [sum(M[j][i] * cp[i] for i in range(3)) + t[j] for j in range(3)]
                    a = _unit([sum(M[j][i] * cp[3 + i] for i in range(3)) for j in range(3)])
                    box = self._com(f, "GetBox")
                    corners = [[(box[0] if i & 1 == 0 else box[3]), (box[1] if i & 2 == 0 else box[4]),
                                (box[2] if i & 4 == 0 else box[5])] for i in range(8)]
                    proj = [_dot([sum(M[j][k] * c[k] for k in range(3)) + t[j] for j in range(3)], a) for c in corners]
                    out.append({"origin": o, "axis": a, "r": float(cp[6]), "lo": min(proj), "hi": max(proj)})
                except Exception as e:
                    logger.debug(f"cyl_any: {e}")
        return out

    @staticmethod
    def _ex_coaxial(c1, c2, tol=5e-5, tol_par=1e-3) -> bool:
        if _norm(_cross(c1["axis"], c2["axis"])) > tol_par:
            return False
        d = [c2["origin"][i] - c1["origin"][i] for i in range(3)]
        return _norm(_cross(d, c1["axis"])) <= tol

    def _ex_plan_mates(self, doc, gap_m: float, base_component: str = None) -> Tuple[Optional[Dict], Optional[str]]:
        """Piano dell'euristica 'mates'. -> ({'base','order','dirs','dist','depth','basis'}, errore). Distanze in m."""
        comps = [c for c in self._as_top_components(doc, True) if int(self._com(c, "GetSuppression")) != 0]
        if len(comps) < 2:
            return None, "Servono almeno 2 componenti"
        names = [str(c.Name2) for c in comps]
        by = dict(zip(names, comps))
        # grafo degli accoppiamenti fra componenti di primo livello
        adj = {n: set() for n in names}
        conc = []
        for f in self._as_mate_features(doc):
            try:
                info = self._as_mate_info(doc, f)
            except Exception:
                continue
            tops = []
            for c in info.get("components", []):
                n = str(c).split("/")[0]
                if n in adj and n not in tops:
                    tops.append(n)
            for i in range(len(tops)):
                for j in range(i + 1, len(tops)):
                    adj[tops[i]].add(tops[j])
                    adj[tops[j]].add(tops[i])
            if info.get("type") == "concentric" and len(tops) == 2:
                conc.append((tops[0], tops[1]))
        # base
        if base_component:
            bc, e = self._as_comp(doc, base_component, True)
            if e:
                return None, e
            base = str(bc.Name2)
        else:
            fixed = [n for n in names if bool(self._com(by[n], "IsFixed"))]
            base = fixed[0] if fixed else max(names, key=lambda n: len(adj[n]))
        # profondita' (BFS dal base); componenti non collegati: profondita' 1
        depth = {base: 0}
        queue = [base]
        while queue:
            cur = queue.pop(0)
            for nb in sorted(adj[cur]):
                if nb not in depth:
                    depth[nb] = depth[cur] + 1
                    queue.append(nb)
        for n in names:
            depth.setdefault(n, 1)
        boxes = {n: [float(v) for v in by[n].GetBox(False, False)] for n in names}
        center = {n: [(boxes[n][i] + boxes[n][i + 3]) / 2 for i in range(3)] for n in names}
        cyls = {n: self._ex_cyl_any(by[n]) for n in names}
        dirs, how = {}, {}
        for n in names:
            if n == base:
                continue
            best = None
            for (a, b) in conc:
                if n not in (a, b):
                    continue
                other = b if n == a else a
                for cn in cyls[n]:
                    for co in cyls[other]:
                        if self._ex_coaxial(cn, co):
                            if best is None or abs(cn["r"] - co["r"]) < abs(best[0]["r"] - best[1]["r"]):
                                best = (cn, co, other)
            if best is not None:
                cn, co, other = best
                ax = cn["axis"]
                same = [c for c in cyls[n] if self._ex_coaxial(cn, c)]
                big = max(same, key=lambda c: c["r"])
                sign = 0
                if big["r"] > cn["r"] * 1.05:
                    sign = 1.0 if (big["lo"] + big["hi"]) / 2 > (cn["lo"] + cn["hi"]) / 2 else -1.0
                    how[n] = "asse concentrico con " + other + "; verso dal lato della testa (raggio maggiore)"
                else:
                    sign = 1.0 if _dot(center[n], ax) >= _dot(center[other], ax) else -1.0
                    how[n] = "asse concentrico con " + other + "; verso opposto al componente accoppiato"
                dirs[n] = [sign * c for c in ax]
            else:
                d = [center[n][i] - center[base][i] for i in range(3)]
                i = max(range(3), key=lambda k: abs(d[k]))
                u = [0.0, 0.0, 0.0]
                u[i] = 1.0 if d[i] >= 0 else -1.0
                dirs[n] = u
                how[n] = "nessun concentrico: asse globale con maggiore scostamento dal componente base"
        movers = [n for n in names if n != base]
        order = sorted(movers, key=lambda n: (-depth[n], n))
        rank = {n: i for i, n in enumerate(order)}
        dist = {n: 0.0 for n in movers}

        def box_at(n):
            b = boxes[n]
            if n == base:
                return b
            u, d = dirs[n], dist[n]
            return [b[i] + u[i % 3] * d for i in range(6)]

        def need(n, m):
            """Spostamento extra di n lungo dirs[n] perche' il suo box disti >= gap dal box di m (None se non si sovrappongono)."""
            bn, bm = box_at(n), box_at(m)
            if any(bn[i] >= bm[i + 3] + gap_m or bn[i + 3] <= bm[i] - gap_m for i in range(3)):
                return None
            u = dirs[n]
            best = None
            for i in range(3):
                if abs(u[i]) < 1e-6:
                    continue
                if u[i] > 0:
                    s = (bm[i + 3] + gap_m - bn[i]) / u[i]
                else:
                    s = (bn[i + 3] - (bm[i] - gap_m)) / (-u[i])
                if best is None or s < best:
                    best = s
            return max(best if best is not None else 0.0, 1e-6)

        passes = 0
        changed = True
        while changed and passes < 300:
            changed = False
            passes += 1
            for i, n in enumerate(order):
                for m in names:
                    if m == n:
                        continue
                    if m in rank and rank[m] < rank[n]:
                        continue            # il piu' interno (rank minore) e' quello che si sposta
                    s = need(n, m)
                    if s is not None:
                        dist[n] += s
                        changed = True
        return {"base": base, "order": order, "dirs": dirs, "dist": dist, "depth": depth, "how": how, "passes": passes,
                "boxes": boxes, "converged": not changed}, None

    def _ex_overlaps(self, doc, tol_mm: float = 0.5) -> List[Dict]:
        """Coppie di componenti i cui bounding box (stato ESPLOSO reale) si sovrappongono in modo apprezzabile (> tol_mm)."""
        comps = [c for c in self._as_top_components(doc, True) if int(self._com(c, "GetSuppression")) != 0]
        boxes = {str(c.Name2): [float(v) for v in c.GetBox(False, False)] for c in comps}
        names = sorted(boxes)
        out = []
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = boxes[names[i]], boxes[names[j]]
                pen = min(min(a[k + 3], b[k + 3]) - max(a[k], b[k]) for k in range(3))
                if pen * 1000 > tol_mm:
                    out.append({"components": [names[i], names[j]], "min_penetration_mm": round(pen * 1000, 3)})
        return out

    def _ex_native(self, doc) -> Tuple[bool, str]:
        names0 = self._ex_names(doc)
        ok = self._com(doc, "AutoExplode")
        names1 = self._ex_names(doc)
        steps = self._ex_steps(doc)
        if not names1 or not steps:
            return False, ("AutoExplode ha risposto " + str(ok) + " ma non ha creato passi"
                           + (" (esiste gia' una vista esplosa: SolidWorks non la rigenera)" if names0 else ""))
        self._ex_refresh(doc, names1[0])
        return True, "ok"

    def auto_explode(self, axis: str = "x", gap: float = 30.0, base_component: str = None, mode: str = "axis",
                     unit: str = None) -> Dict:
        """Esplosione automatica. mode:
          'native'  IAssemblyDoc.AutoExplode di SolidWorks (un passo 'Catena'; direzione scelta da SolidWorks);
          'mates'   euristica dagli accoppiamenti: ordine di smontaggio per profondita' dal componente base, direzione = asse della
                    coppia concentrica (verso: lato della testa), distanze dai bounding box con distanza minima `gap` fra i componenti;
                    controlla poi lo stato esploso reale (`bbox_overlaps`);
          'auto'    prova 'native'; se non crea passi o lascia box sovrapposti, usa 'mates';
          'axis'    (default, compatibilita') un passo per componente lungo `axis`, a distanza gap * posizione nell'ordine.
        Il risultato riporta il metodo usato, i passi e le pose esplose."""
        try:
            doc, err = self._asm()
            if err:
                return err
            self._as_collapse(doc)
            mode = str(mode or "axis").lower()
            if mode not in ("axis", "native", "mates", "auto"):
                return self._result(False, "mode: axis | native | mates | auto", SwErrors.swInvalidInput)
            if mode in ("native", "auto"):
                had = bool(self._ex_names(doc))
                ok, why = self._ex_native(doc)
                if ok:
                    ov = self._ex_overlaps(doc)
                    if mode == "native" or not ov:
                        return self._result(True, f"Esplosione nativa: {len(self._ex_steps(doc))} passi, {len(ov)} sovrapposizioni dei box",
                                            SwErrors.swSuccess, {"method": "native", "steps": self._ex_steps(doc), "bbox_overlaps": ov,
                                                                 "exploded": bool(self._com(doc, "IsExploded")), "poses": self._ex_poses(doc)})
                elif mode == "native":
                    return self._result(False, "Esplosione nativa non riuscita: " + why, SwErrors.swFeatureError)
                # fallback: l'esploso nativo (se creato) viene lasciato com'e'; l'euristica lavora su una vista nuova solo se possibile
                if ok:
                    return self._result(False, "L'esplosione nativa lascia box sovrapposti e l'assieme ha gia' la sua vista: "
                                        "riprova su una copia o usa mode='mates' su un assieme senza vista esplosa",
                                        SwErrors.swFeatureError, {"method": "native", "bbox_overlaps": self._ex_overlaps(doc)})
                mode = "mates"
            if mode == "mates":
                gap_m = abs(self._mmu(float(gap) if gap else 15.0, unit))
                plan, e = self._ex_plan_mates(doc, gap_m, base_component)
                if e:
                    return self._result(False, e, SwErrors.swInvalidInput)
                # raggruppa i componenti con stessa direzione e stessa distanza
                groups = []
                for n in plan["order"]:
                    if plan["dist"][n] < 1e-9:
                        continue
                    key = (tuple(round(c, 6) for c in plan["dirs"][n]), round(plan["dist"][n], 6))
                    for g in groups:
                        if g["key"] == key:
                            g["components"].append(n)
                            break
                    else:
                        groups.append({"key": key, "components": [n]})
                steps = [{"components": g["components"], "direction": list(g["key"][0]), "distance": g["key"][1] * 1000.0}
                         for g in groups]
                if not steps:
                    return self._result(False, "Nessun componente da spostare", SwErrors.swInvalidInput)
                r = self.create_exploded_view(steps, unit="mm", keep_exploded=True)
                if not r["success"]:
                    return r
                ov = self._ex_overlaps(doc)
                d = r["data"]
                d.update({"method": "mates", "base_component": plan["base"], "disassembly_order": plan["order"],
                          "depth": plan["depth"], "directions": {n: [round(c, 6) for c in v] for n, v in plan["dirs"].items()},
                          "distances_mm": {n: round(v * 1000, 3) for n, v in plan["dist"].items()}, "how": plan["how"],
                          "relaxation_passes": plan["passes"], "converged": plan["converged"], "bbox_overlaps": ov,
                          "heuristic": "ordine dagli accoppiamenti, asse concentrico, distanze dai bounding box"})
                return self._result(True, f"Esplosione per accoppiamenti: {len(steps)} gruppi, {len(ov)} sovrapposizioni dei box",
                                    SwErrors.swSuccess, d)
            # ---- 'axis': comportamento storico
            d, e = self._ex_parse_dir(axis)
            if e or d[0] != "axis":
                return self._result(False, e or "axis: x, y, z, -x, -y, -z", SwErrors.swInvalidInput)
            idx = d[1][0]
            comps = [c for c in self._as_top_components(doc, True) if int(self._com(c, "GetSuppression")) != 0]
            if len(comps) < 2:
                return self._result(False, "Servono almeno 2 componenti", SwErrors.swInvalidInput)
            centers = {}
            for c in comps:
                b = c.GetBox(False, False)
                centers[str(c.Name2)] = (b[idx] + b[idx + 3]) / 2.0
            if base_component:
                base, e = self._as_comp(doc, base_component, True)
                if e:
                    return self._result(False, e, SwErrors.swSelectionError)
            else:
                fixed = [c for c in comps if bool(self._com(c, "IsFixed"))]
                base = fixed[0] if fixed else sorted(comps, key=lambda c: centers[str(c.Name2)])[0]
            bc = centers[str(base.Name2)]
            above = sorted([c for c in comps if centers[str(c.Name2)] > bc + 1e-9 and c is not base],
                           key=lambda c: centers[str(c.Name2)])
            below = sorted([c for c in comps if centers[str(c.Name2)] < bc - 1e-9 and c is not base],
                           key=lambda c: -centers[str(c.Name2)])
            same = [c for c in comps if abs(centers[str(c.Name2)] - bc) <= 1e-9 and c is not base]
            steps = []
            nm = "xyz"[idx]
            for k, c in enumerate(above, 1):
                steps.append({"components": [str(c.Name2)], "direction": nm, "distance": gap * k})
            for k, c in enumerate(below, 1):
                steps.append({"components": [str(c.Name2)], "direction": "-" + nm, "distance": gap * k})
            for k, c in enumerate(same, 1):
                steps.append({"components": [str(c.Name2)], "direction": nm, "distance": gap * (len(above) + k)})
            r = self.create_exploded_view(steps, unit=unit, keep_exploded=True)
            if r["success"]:
                r["data"]["method"] = "axis"
            return r
        except Exception as e:
            return self._as_fail("auto_explode", e)
