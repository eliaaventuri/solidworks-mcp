"""
Assiemi: movimento dei componenti entro i gradi di liberta' consentiti (C7) e cancellazione di accoppiamenti con rapporto
sui gradi di liberta' (C6). Mixin `AssemblyMotionMixin` (usato da AssemblyOperations).

Idea (C7). `Component2.SetTransformAndSolve2` con una posa NON raggiungibile restituisce un compromesso del solutore: per un perno
con il solo concentrico, chiedere una rotazione attorno a Y lo faceva scivolare di 11,7 mm lungo l'asse; per la traslazione fuori
asse non si muoveva. Quindi i gradi di liberta' si MISURANO con piccole prove (0,5 mm / 3 gradi, posa poi ripristinata):
  - traslazioni: si prova lungo X,Y,Z; lo spostamento ottenuto (se c'e') indica la direzione libera, che poi si verifica
    provando proprio lungo quella direzione (anche assi inclinati);
  - rotazioni: si prova attorno a X,Y,Z passando per l'origine; l'asse ottenuto si verifica ruotando attorno a esso e, se
    l'origine si e' spostata, si ricava il punto dell'asse reale (rotazione attorno a un asse non passante per l'origine).
La richiesta di movimento si proietta sui soli gradi di liberta' trovati (traslazione = componente lungo le direzioni libere,
rotazione = angolo attorno agli assi liberi) e SOLO quella posa, raggiungibile, si passa al solutore.
"""

import math
import logging
from typing import Dict, List, Optional, Tuple

from ..constants import SwErrors

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- algebra 3x3 (convenzione colonna: x_mondo = M q + t)
def _mm(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _tr(A):
    return [[A[j][i] for j in range(3)] for i in range(3)]


def _mv(A, v):
    return [sum(A[i][k] * v[k] for k in range(3)) for i in range(3)]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _norm(a):
    return math.sqrt(_dot(a, a))


def _unit(a):
    n = _norm(a)
    return [x / n for x in a] if n > 1e-15 else [0.0, 0.0, 0.0]


def _sub(a, b):
    return [x - y for x, y in zip(a, b)]


def _add(a, b):
    return [x + y for x, y in zip(a, b)]


def _scale(a, s):
    return [x * s for x in a]


def _rodrigues(axis, ang):
    """Rotazione di `ang` rad attorno a `axis` (unitario), matrice colonna."""
    x, y, z = axis
    c, s = math.cos(ang), math.sin(ang)
    C = 1.0 - c
    return [[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
            [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
            [z * x * C - y * s, z * y * C + x * s, c + z * z * C]]


def _axis_angle(R):
    """(asse unitario, angolo in [0, pi]) di una rotazione."""
    c = max(-1.0, min(1.0, (R[0][0] + R[1][1] + R[2][2] - 1.0) / 2.0))
    ang = math.acos(c)
    if ang < 1e-9:
        return [0.0, 0.0, 1.0], 0.0
    if math.pi - ang < 1e-6:
        # asse = autovettore con autovalore 1: colonna di (R + I) di norma massima
        cols = [[R[i][j] + (1.0 if i == j else 0.0) for i in range(3)] for j in range(3)]
        v = max(cols, key=_norm)
        return _unit(v), ang
    w = [R[2][1] - R[1][2], R[0][2] - R[2][0], R[1][0] - R[0][1]]
    return _unit(w), ang


def _gram(c, basis):
    for b in basis:
        c = _sub(c, _scale(b, _dot(c, b)))
    return c


def _label(v) -> str:
    """'x' / '-y' ... se la direzione e' un asse del mondo, altrimenti '(0.71,0.71,0)'."""
    for i, n in enumerate("xyz"):
        if abs(abs(v[i]) - 1.0) < 1e-3:
            return n if v[i] > 0 else "-" + n
    return "(" + ",".join(f"{c:.3f}" for c in v) + ")"


class AssemblyMotionMixin:
    """Gradi di liberta' misurati, movimento filtrato (C7) e delete_mate con confronto dei gradi di liberta' (C6)."""

    # ====================================================================
    # Gradi di liberta' misurati
    # ====================================================================

    def _as_dof_basis(self, comp, st: float = 0.0005, sr_deg: float = 3.0, others=None, on_probe=None) -> Dict:
        """Base dei moti liberi del componente nella posa corrente:
        {'translations': [u,...] direzioni unitarie (mondo), 'rotations': [(w, p0),...] asse unitario e un punto dell'asse [m]}.
        La posa viene ripristinata alla fine. Con `others` (altri componenti) e `on_probe(kind, vettore)` si osserva anche chi
        SEGUE il componente durante ogni prova valida (catene di accoppiamenti): le pose di `others` vengono ripristinate."""
        M0, t0 = self._as_pose(comp)
        sr = math.radians(sr_deg)
        others_base = [(o,) + tuple(self._as_pose(o)) for o in (others or [])]

        def solve(M, t):
            comp.SetTransformAndSolve2(self._as_transform(M, t))
            return self._as_pose(comp)

        def restore():
            try:
                comp.Transform2 = self._as_transform(M0, t0)
            except Exception:
                pass
            for (o, Mo, to) in others_base:
                try:
                    o.Transform2 = self._as_transform(Mo, to)
                except Exception:
                    pass
            return self._as_pose(comp)

        trans: List[List[float]] = []
        rots: List[Tuple[List[float], List[float]]] = []
        try:
            # ---- traslazioni
            cands = []
            for ax in range(3):
                v = [0.0, 0.0, 0.0]
                v[ax] = st
                _, t = solve(M0, _add(t0, v))
                d = _sub(t, t0)
                restore()
                if _norm(d) > 0.05 * st:
                    cands.append(_unit(d))
            for c in cands:
                c = _gram(c, trans)
                if _norm(c) < 0.2:
                    continue
                c = _unit(c)
                _, t = solve(M0, _add(t0, _scale(c, st)))
                d = _sub(t, t0)
                along = _dot(d, c)
                good = along >= 0.9 * st and _norm(_sub(d, _scale(c, along))) <= 0.1 * st
                if good and on_probe is not None:
                    on_probe("t", c)
                restore()
                if good:
                    trans.append(c)
            # ---- rotazioni
            cands = []
            for ax in range(3):
                e = [0.0, 0.0, 0.0]
                e[ax] = 1.0
                M, t = solve(_mm(_rodrigues(e, sr), M0), t0)
                w, phi = _axis_angle(_mm(M, _tr(M0)))
                restore()
                if phi > 0.05 * sr:
                    cands.append(w)
            for c in cands:
                c = _gram(c, [r[0] for r in rots])
                if _norm(c) < 0.2:
                    continue
                c = _unit(c)
                M, t = solve(_mm(_rodrigues(c, sr), M0), t0)
                w, phi = _axis_angle(_mm(M, _tr(M0)))
                delta = _sub(t, t0)
                if on_probe is not None and phi >= 0.9 * sr and abs(_dot(w, c)) >= 0.995:
                    on_probe("r", c)
                restore()
                if phi < 0.9 * sr or abs(_dot(w, c)) < 0.995:
                    continue
                if _dot(w, c) < 0:
                    w = _scale(w, -1.0)
                # punto dell'asse reale: delta = (R - I)(O - p0)  ->  O - p0 = (a d - b w x d)/(a^2+b^2)
                dperp = _sub(delta, _scale(w, _dot(delta, w)))
                a, b = -(1.0 - math.cos(phi)), math.sin(phi)
                wd = _cross(w, dperp)
                r = [(a * dperp[i] - b * wd[i]) / (a * a + b * b) for i in range(3)]
                rots.append((w, _sub(t0, r)))
        finally:
            restore()
        return {"translations": trans, "rotations": rots, "pose": (M0, t0)}

    def _as_dof(self, comp) -> Dict:
        """Gradi di liberta' residui MISURATI (vedi _as_dof_basis): moti liberi come etichette ('x', '-y', '(0.707,0.707,0.000)'),
        conteggio e controllo che la posa sia stata ripristinata."""
        try:
            M0, t0 = self._as_pose(comp)
            b = self._as_dof_basis(comp)
            M1, t1 = self._as_pose(comp)
            restored = self._dist(t1, t0) < 1e-7
            return {"free_translations": [_label(u) for u in b["translations"]],
                    "free_rotations": [_label(w) for w, _ in b["rotations"]],
                    "rotation_axes_points_mm": [[round(c * 1000, 4) for c in p] for _, p in b["rotations"]],
                    "dof_count": len(b["translations"]) + len(b["rotations"]), "pose_restored": restored}
        except Exception as e:
            return {"dof_error": str(e)[:100]}

    def _as_dof_snapshot(self, doc, st: float = 0.0005, sr_deg: float = 3.0) -> Dict[str, Dict]:
        """Gradi di liberta' misurati di ogni componente di primo livello attivo, TENENDO CONTO DELLE CATENE: durante la prova di
        un componente si osserva anche chi lo segue (un perno accoppiato a una boccola che ha perso un vincolo segue la boccola e
        quindi ha anch'esso un moto in piu' anche se i suoi accoppiamenti non sono cambiati). Per ogni componente:
        {'fixed', 'dof_count', 'free_translations', 'free_rotations', 'status_code'} (moti propri + indotti da altri)."""
        sr = math.radians(sr_deg)
        comps = [c for c in sorted(self._as_top_components(doc, True), key=lambda c: str(c.Name2))
                 if not self._as_state(c).get("suppressed")]
        names = [str(c.Name2) for c in comps]
        base = {n: self._as_pose(c) for n, c in zip(names, comps)}
        mot = {n: {"t": [], "r": []} for n in names}

        def add(n, kind, v):
            lst = mot[n][kind]
            if len(lst) >= 3:
                return
            for u in lst:
                if _norm(_cross(u, v)) < 0.2:
                    return
            lst.append(v)

        out = {}
        for c, n in zip(comps, names):
            fixed = bool(self._as_state(c).get("fixed"))
            try:
                code = int(self._com(c, "GetConstrainedStatus"))
            except Exception:
                code = 1
            out[n] = {"fixed": fixed, "status_code": code}
            if fixed:
                continue
            others = [o for o in comps if o is not c]

            def on_probe(kind, vec, _others=others):
                for o in _others:
                    on = str(o.Name2)
                    if self._as_state(o).get("fixed"):
                        continue
                    Mo, to = self._as_pose(o)
                    M0o, t0o = base[on]
                    if kind == "t":
                        d = _sub(to, t0o)
                        if _norm(d) > 0.5 * st:
                            add(on, "t", _unit(d))
                    else:
                        w, ang = _axis_angle(_mm(Mo, _tr(M0o)))
                        if ang > 0.5 * sr:
                            add(on, "r", w)

            try:
                b = self._as_dof_basis(c, st, sr_deg, others=others, on_probe=on_probe)
                for u in b["translations"]:
                    add(n, "t", u)
                for w, _ in b["rotations"]:
                    add(n, "r", w)
            except Exception as e:
                logger.debug(f"snapshot {n}: {e}")
        for n in names:
            if out[n]["fixed"]:
                out[n].update({"dof_count": 0, "free_translations": [], "free_rotations": []})
            else:
                out[n].update({"dof_count": len(mot[n]["t"]) + len(mot[n]["r"]),
                               "free_translations": [_label(u) for u in mot[n]["t"]],
                               "free_rotations": [_label(w) for w in mot[n]["r"]]})
        return out

    # ====================================================================
    # Spostamento componenti
    # ====================================================================

    def move_component(self, component: str, dx: float = 0, dy: float = 0, dz: float = 0, position: list = None,
                       rotation: list = None, rotate_by: list = None, respect_mates: bool = True, unit: str = None) -> Dict:
        """Sposta/ruota un componente MOBILE. Relativo (dx,dy,dz in mm; rotate_by=[rx,ry,rz] gradi attorno all'origine del
        componente, assi dell'assieme) oppure assoluto (position=[x,y,z], rotation=[rx,ry,rz]).
        respect_mates=True (default): il movimento e' ridotto ai SOLI gradi di liberta' lasciati dagli accoppiamenti, misurati
        sul componente (C7): la traslazione e' la componente lungo le direzioni libere, la rotazione e' l'angolo attorno agli
        assi liberi (anche non passanti per l'origine); cio' che i vincoli vietano viene scartato e riportato in `ignored`.
        I limiti degli accoppiamenti con limite (distanza/angolo) si pilotano con edit_mate(value=...). Un componente fisso non si
        muove. respect_mates=False: imposta la posa senza risolvere gli accoppiamenti."""
        try:
            doc, err = self._asm()
            if err:
                return err
            self._as_collapse(doc)
            comp, e = self._as_comp(doc, component, True)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            if bool(self._com(comp, "IsFixed")):
                return self._result(False, f"{comp.Name2} e' fisso: usa set_component_fixed(fixed=False) prima di muoverlo.",
                                    SwErrors.swInvalidInput)
            from .assembly import _rot_matrix
            M0, t0 = self._as_pose(comp)
            if position is not None or rotation is not None:
                t1 = [self._mmu(float(v), unit) for v in position] if position is not None else list(t0)
                M1 = _rot_matrix(*(list(rotation) + [0, 0, 0])[:3]) if rotation is not None else M0
                T_req = _sub(t1, t0)
                R_req = _mm(M1, _tr(M0))
            else:
                T_req = [self._mmu(dx, unit), self._mmu(dy, unit), self._mmu(dz, unit)]
                R_req = _rot_matrix(*(list(rotate_by) + [0, 0, 0])[:3]) if rotate_by else [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
            w_req, phi_req = _axis_angle(R_req)
            extra = {}
            if not respect_mates:
                comp.Transform2 = self._as_transform(_mm(R_req, M0), _add(t0, T_req)) if False else \
                    self._as_transform(_mm(R_req, M0), _add(t0, T_req))
            else:
                # le prove di SetTransformAndSolve2 trascinano anche altri componenti (es. la seconda ruota di un ingranaggio:
                # +1,72 gradi per prova): si rimettono tutti a posto, non solo `comp`
                others = [o for o in self._as_top_components(doc, False) if str(o.Name2) != str(comp.Name2)]
                basis = self._as_dof_basis(comp, others=others)
                U, Rax = basis["translations"], basis["rotations"]
                free_all = len(U) == 3 and len(Rax) == 3
                if free_all:
                    xf_M, xf_t = _mm(R_req, M0), _add(t0, T_req)
                    applied_T, applied_rot = T_req, [(w_req, phi_req)]
                else:
                    # traslazione: proiezione sulle direzioni libere
                    applied_T = [0.0, 0.0, 0.0]
                    for u in U:
                        applied_T = _add(applied_T, _scale(u, _dot(T_req, u)))
                    # rotazione: angolo attorno a ciascun asse libero (assi ortonormali) = componente del vettore di rotazione
                    om = _scale(w_req, phi_req)
                    xf_M, xf_t = [r[:] for r in M0], list(t0)
                    applied_rot = []
                    for w, p0 in Rax:
                        th = _dot(om, w)
                        if abs(th) < 1e-9:
                            continue
                        R = _rodrigues(w, th)
                        xf_M = _mm(R, xf_M)
                        xf_t = _add(_mv(R, _sub(xf_t, p0)), p0)
                        applied_rot.append((w, th))
                    xf_t = _add(xf_t, applied_T)
                ign_T = _norm(_sub(T_req, applied_T))
                ign_rot = 0.0
                if not free_all:
                    om = _scale(w_req, phi_req)
                    rest = om
                    for w, th in applied_rot:
                        rest = _sub(rest, _scale(w, th))
                    ign_rot = _norm(rest)
                extra = {"free_translation_directions": [_label(u) for u in U],
                         "free_rotation_axes": [_label(w) for w, _ in Rax],
                         "requested": {"translation_mm": [round(v * 1000, 4) for v in T_req],
                                       "rotation_deg": round(math.degrees(phi_req), 4)},
                         "applied": {"translation_mm": [round(v * 1000, 4) for v in applied_T],
                                     "rotation_deg_about_free_axes": [round(math.degrees(th), 4) for _, th in applied_rot]},
                         "ignored": {"translation_mm": round(ign_T * 1000, 4), "rotation_deg": round(math.degrees(ign_rot), 4)}}
                if not U and not Rax:
                    extra["note"] = "nessun grado di liberta': il componente e' completamente vincolato"
                elif len(U) + len(Rax) > 0 and not free_all and (ign_T > 1e-9 or ign_rot > 1e-9):
                    extra["note"] = ("parte del movimento richiesto e' vietata dagli accoppiamenti ed e' stata scartata "
                                     "(vedi 'ignored')")
                mech = self._as_mech_mates(doc, comp) if (applied_rot and not free_all) else []
                if mech and len(applied_rot) == 1 and _norm(applied_T) < 1e-12:
                    # ingranaggio/vite/pignone: rotazione pilotata, cosi' il solutore muove anche chi e' collegato (C5)
                    dr = self._as_drive_rotation(doc, comp, applied_rot[0][0], applied_rot[0][1])
                    extra["mechanical_drive"] = {"mates": mech, **dr}
                    if not dr["ok"]:
                        extra["note"] = (dr.get("note") or "") + "; applicata senza propagare gli accoppiamenti meccanici"
                        comp.SetTransformAndSolve2(self._as_transform(xf_M, xf_t))
                elif U or Rax:
                    if mech:
                        extra["note"] = ("accoppiamenti meccanici " + ", ".join(mech) + ": la propagazione funziona solo per una "
                                         "rotazione attorno a un solo asse libero, senza traslazione")
                    comp.SetTransformAndSolve2(self._as_transform(xf_M, xf_t))
            doc.ForceRebuild2(False)
            info = self._as_comp_info(comp)
            moved = self._dist(self._as_pose(comp)[1], t0) * 1000
            info["moved_mm"] = round(moved, 4)
            info.update(extra)
            return self._result(True, f"{comp.Name2} spostato di {moved:.3f} mm", SwErrors.swSuccess, info)
        except Exception as e:
            return self._as_fail("move_component", e)

    # ====================================================================
    # rotazione pilotata per gli accoppiamenti meccanici (C5)
    # ====================================================================
    # SetTransformAndSolve2 e IDragOperator NON propagano ingranaggio/vite/pignone (la seconda ruota non segue, la
    # chiocciola non avanza). Un accoppiamento d'ANGOLO temporaneo invece passa dal solutore completo, che rispetta anche
    # i meccanici (misurato 2026-10-17, istanza nascosta: ingranaggio 2:1 -> B/A = -2,0000; vite 2 mm/giro -> 2,0000).

    MECHANICAL_MATES = ("gear", "screw", "rack_pinion")

    def _as_mech_mates(self, doc, comp) -> List[str]:
        """Tipi degli accoppiamenti meccanici in cui compare il componente."""
        name = str(comp.Name2).lower()
        out = []
        for f in self._as_mate_features(doc):
            info = self._as_mate_info(doc, f)
            if info.get("type") in self.MECHANICAL_MATES and \
                    any(str(c).split("/")[0].lower() == name for c in info.get("components", [])):
                out.append(info["type"])
        return out

    def _as_signed_rot(self, comp, M0, w) -> float:
        """Angolo (radianti, con segno attorno a w) della rotazione del componente rispetto alla matrice M0."""
        axis, ang = _axis_angle(_mm(self._as_pose(comp)[0], _tr(M0)))
        return ang if _dot(axis, w) >= 0 else -ang

    def _as_drive_rotation(self, doc, comp, w, theta) -> Dict:
        """Ruota `comp` di theta (radianti) attorno all'asse libero w con un accoppiamento d'angolo temporaneo fra un piano
        standard del componente e uno dell'assieme (entrambi paralleli a w). -> {"ok", "rotation_deg", "note"}."""
        M0, _ = self._as_pose(comp)
        planes_c = []
        for nm in ("front", "top", "right"):
            f = self._std_ref_feature(comp, nm)
            if f is None:
                continue
            t = [float(v) for v in f.GetSpecificFeature2.Transform.ArrayData]
            planes_c.append((nm, _unit(_mv(M0, t[6:9]))))
        planes_a = []
        for nm in ("front", "top", "right"):
            f = self._std_ref_feature(doc, nm)
            t = [float(v) for v in f.GetSpecificFeature2.Transform.ArrayData]
            planes_a.append((str(self._com(f, "Name")), _unit(t[6:9])))
        pc = next(((n, v) for n, v in planes_c if abs(_dot(v, w)) < 1e-6), None)
        pa = next(((n, v) for n, v in planes_a if abs(_dot(v, w)) < 1e-6), None)
        if pc is None or pa is None:
            return {"ok": False, "note": "asse di rotazione non parallelo ai piani standard: rotazione pilotata non disponibile"}
        th0 = math.degrees(math.acos(max(-1.0, min(1.0, _dot(pc[1], pa[1])))))
        r = self.add_mate(mate_type="angle", entity1={"component": comp.Name2, "plane": pc[0]}, entity2=pa[0], angle=th0)
        mname = (r.get("data") or {}).get("name")
        if not r.get("success") or not mname:
            return {"ok": False, "note": f"accoppiamento d'angolo temporaneo non creato: {r.get('message')}"}
        try:
            r0 = self._as_signed_rot(comp, M0, w)
            self.edit_mate(name=mname, value=(th0 + 10.0) % 360.0)
            doc.ForceRebuild3(False)
            r1 = self._as_signed_rot(comp, M0, w)
            s = (r1 - r0) / math.radians(10.0)
            if abs(abs(s) - 1.0) > 1e-3:
                return {"ok": False, "note": f"risposta dell'angolo pilota non lineare (pendenza {s:.4f})"}
            v = th0 + 10.0 + math.degrees((theta - r1) / s)
            self.edit_mate(name=mname, value=v % 360.0)
            doc.ForceRebuild3(False)
        finally:
            self.delete_mate(name=mname, check_dof=False)
            doc.ForceRebuild3(False)
        got = self._as_signed_rot(comp, M0, w)
        ok = abs(got - theta) < math.radians(1e-3)
        return {"ok": ok, "rotation_deg": round(math.degrees(got), 4),
                "note": None if ok else f"rotazione ottenuta {math.degrees(got):.4f} gradi invece di {math.degrees(theta):.4f}"}

    # ====================================================================
    # delete_mate con confronto dei gradi di liberta' (C6)
    # ====================================================================

    def delete_mate(self, name: str, check_dof: bool = True) -> Dict:
        """Elimina un accoppiamento per nome (come in list_mates). Con check_dof (default) misura i gradi di liberta' di tutti i
        componenti mobili PRIMA e DOPO e riporta chi e' diventato piu' libero (`freed_components`): anche i componenti che non
        compaiono nell'accoppiamento eliminato, perche' vincolati tramite catene di accoppiamenti (es. un perno mettato alla
        boccola, che segue la boccola quando questa perde un vincolo). Le posizioni non cambiano con l'eliminazione."""
        try:
            doc, err = self._asm()
            if err:
                return err
            self._as_collapse(doc)
            target = None
            for f in self._as_mate_features(doc):
                if str(self._com(f, "Name")).lower() == str(name).lower():
                    target = f
            if target is None:
                return self._result(False, f"Accoppiamento '{name}' non trovato", SwErrors.swSelectionError)
            info = self._as_mate_info(doc, target)
            involved = set()
            for c in info.get("components", []):
                involved.add(str(c).split("/")[0])
            before = self._as_dof_snapshot(doc) if check_dof else {}
            n0 = len(self._as_mate_features(doc))
            doc.ClearSelection2(True)
            target.Select2(False, 0)
            doc.Extension.DeleteSelection2(3)
            doc.ClearSelection2(True)
            try:
                doc.ForceRebuild2(False)
            except Exception:
                pass
            n1 = len(self._as_mate_features(doc))
            if n1 >= n0:
                return self._result(False, f"Eliminazione di '{name}' non riuscita", SwErrors.swFeatureError)
            data = {"remaining": n1, "deleted": info.get("name", name), "deleted_type": info.get("type"),
                    "components_in_mate": sorted(involved)}
            msg = f"Accoppiamento {name} eliminato ({n1} rimasti)"
            if check_dof:
                after = self._as_dof_snapshot(doc)
                freed = []
                for n, a in after.items():
                    b = before.get(n)
                    if b is None or a.get("fixed"):
                        continue
                    if a["dof_count"] > b["dof_count"]:
                        freed.append({"component": n, "dof_before": b["dof_count"], "dof_after": a["dof_count"],
                                      "free_translations_before": b["free_translations"],
                                      "free_translations_after": a["free_translations"],
                                      "free_rotations_before": b["free_rotations"], "free_rotations_after": a["free_rotations"],
                                      "in_deleted_mate": n in involved})
                others = [f["component"] for f in freed if not f["in_deleted_mate"]]
                data.update({"dof_before": {n: v["dof_count"] for n, v in before.items()},
                             "dof_after": {n: v["dof_count"] for n, v in after.items()},
                             "freed_components": freed, "freed_not_in_mate": others})
                if freed:
                    msg += ("; ATTENZIONE: " + ", ".join(f"{f['component']} {f['dof_before']}->{f['dof_after']} gradi di liberta'"
                                                         for f in freed)
                            + (f" (di cui {', '.join(others)} non erano nell'accoppiamento: seguivano un altro componente)"
                               if others else ""))
                    data["warning"] = "componenti sottovincolati dopo l'eliminazione"
            return self._result(True, msg, SwErrors.swSuccess, data)
        except Exception as e:
            return self._as_fail("delete_mate", e)
