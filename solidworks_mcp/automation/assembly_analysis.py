"""
Assiemi: vista esplosa, analisi (interferenze, giochi, massa, conteggi) e configurazioni (mixin).

Trappole SW 2026 (late binding):
 - `AssemblyDoc.CreateExplodedView` e' una PROPRIETA' (leggerla la esegue). `Configuration.AddExplodeStep2(dist, dirIndex 0/1/2 = X/Y/Z
   dell'ASSIEME, inverti, angolo, asse rotazione (-1 = nessuna), invertiAng, ruotaOrigine, autoSpazio, errore)` vuole i
   componenti selezionati con **Mark 1** (Mark 0 -> errore 3 "nessun componente" e crea comunque un passo vuoto).
 - Con la vista esplosa attiva Transform2/GetBox dei componenti sono quelli ESPLOSI; `GetSpecificTransform(True)` da' la posa reale.
 - `InterferenceDetectionManager`: proprieta' dell'assieme; `GetInterferences` e' una proprieta' (tuple); `Interference.Volume` in m3;
   chiamare `Done()` a fine uso. TreatCoincidenceAsInterference=False: facce coincidenti non contano.
 - `Extension.CreateMeasure` + selezione di due componenti/entita' + `Calculate(NULL)` -> `Distance` (m).
 - (A1) LINEE DI ESPLOSIONE: `ISketchManager.InsertExplodeLineSketch` apre lo schizzo 3D (con l'esploso attivo), si selezionano le facce
   cilindriche da collegare (Face2.Select4) e `ISketch.InsertRouteLine(ItemsToConnect, Reverse, AlternatePath, AlongXYZ)` -> True e segmenti.
   InsertRouteLine e' invocato con `_oleobj_.Invoke` (altrimenti 'bool' object is not callable) e ItemsToConnect DEVE essere
   `VARIANT(VT_ARRAY|VT_VARIANT, oggetti)` con gli oggetti di `SelectionManager.GetSelectedObject6(i, -1)`: con VT_ARRAY|VT_DISPATCH
   delle facce stesse restituisce False. Si chiude con `SketchManager.InsertSketch(True)`; l'assieme va poi salvato.
"""

import os
import math
import logging
from typing import Dict, List, Optional

import win32com.client
import pythoncom

from ..constants import SwErrors

logger = logging.getLogger(__name__)

_DIRS = {"x": (0, False), "+x": (0, False), "-x": (0, True), "y": (1, False), "+y": (1, False), "-y": (1, True),
         "z": (2, False), "+z": (2, False), "-z": (2, True)}


def _i4():
    return win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)


def _null():
    return win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)


class AssemblyAnalysisMixin:
    """Vista esplosa, interferenze, giochi, massa, conteggi, configurazioni dell'assieme."""

    # ====================================================================
    # Vista esplosa
    # ====================================================================

    def _ex_config(self, doc):
        return self._com(doc, "GetActiveConfiguration")

    def _ex_names(self, doc) -> List[str]:
        try:
            cfg = self._ex_config(doc)
            names = doc.GetExplodedViewNames2(str(cfg.Name))
            return [str(n) for n in (names or ())]
        except Exception:
            try:
                return [str(n) for n in (self._com(doc, "GetExplodedViewNames") or ())]
            except Exception:
                return []

    # ====================================================================
    # Linee di esplosione (A1)
    # ====================================================================

    def _ex_cyl_faces(self, comp, dir_idx: int, tol_par: float = 0.001) -> List[Dict]:
        """Facce cilindriche del componente con l'asse parallelo all'asse `dir_idx` (0/1/2 = X/Y/Z dell'assieme) nella posa
        CORRENTE (anche esplosa): [{'face','lat':(a,b) m,'axial': m,'r': m,'area': m2}]."""
        out = []
        try:
            xf = [float(v) for v in comp.Transform2.ArrayData]
        except Exception:
            return out
        Rm, t = xf[:9], xf[9:12]
        others = [k for k in range(3) if k != dir_idx]
        for b in (comp.GetBodies2(0) or ()):
            for f in (b.GetFaces() or ()):
                try:
                    sf = f.GetSurface
                    if not sf.IsCylinder:
                        continue
                    cp = sf.CylinderParams
                    ax = (cp[3], cp[4], cp[5])
                    axa = [sum(ax[i] * Rm[i * 3 + k] for i in range(3)) for k in range(3)]
                    if abs(abs(axa[dir_idx]) - 1.0) > tol_par:
                        continue
                    org = (cp[0], cp[1], cp[2])
                    oa = [sum(org[i] * Rm[i * 3 + k] for i in range(3)) + t[k] for k in range(3)]
                    out.append({"face": f, "lat": (oa[others[0]], oa[others[1]]), "axial": oa[dir_idx], "r": float(cp[6]),
                                "area": float(self._com(f, "GetArea"))})
                except Exception as e:
                    logger.debug(f"cyl face: {e}")
        return out

    def add_explode_lines(self, groups: list = None, direction: str = "auto", view_name: str = None,
                          tolerance: float = 0.5, unit: str = None) -> Dict:
        """Linee di esplosione (route lines) nella vista esplosa: una retta per ogni asse comune a facce cilindriche di componenti
        diversi (perno-boccola-foro della staffa, ciascuna vite con il suo foro...). groups = [[comp1, comp2, ...], ...] (nomi istanza,
        collegati sull'asse che hanno in comune) oppure None = automatico: tutti gli assi condivisi da almeno 2 componenti, nella
        direzione `direction` ('x' | 'y' | 'z' | 'auto' = quella con piu' linee). Serve la vista esplosa (create_exploded_view /
        auto_explode); DOPO si salva l'assieme (save_document) perche' le viste di disegno la leggano. tolerance = mm di scarto laterale."""
        try:
            doc, err = self._asm()
            if err:
                return err
            names = self._ex_names(doc)
            if not names:
                return self._result(False, "L'assieme non ha una vista esplosa (create_exploded_view / auto_explode).",
                                    SwErrors.swInvalidInput)
            vname = view_name or names[0]
            if vname not in names:
                return self._result(False, f"Vista esplosa '{vname}' non trovata. Presenti: {names}", SwErrors.swInvalidInput)
            if not bool(self._com(doc, "IsExploded")):
                doc.ShowExploded2(True, vname)
            if not bool(self._com(doc, "IsExploded")):
                return self._result(False, "Impossibile attivare la vista esplosa", SwErrors.swFeatureError)
            tol = self._mmu(float(tolerance), "mm") if tolerance else 0.0005
            comps = [c for c in self._as_top_components(doc, True) if int(self._com(c, "GetSuppression")) != 0]
            {str(c.Name2): c for c in comps}

            def clusters_for(dir_idx, only=None):
                """[{'lat','items':[(comp_name, cyl)]}] con almeno 2 componenti."""
                cl = []
                for c in comps:
                    n = str(c.Name2)
                    if only is not None and n not in only:
                        continue
                    for cyl in self._ex_cyl_faces(c, dir_idx):
                        for k in cl:
                            if math.hypot(k["lat"][0] - cyl["lat"][0], k["lat"][1] - cyl["lat"][1]) <= tol:
                                k["items"].append((n, cyl))
                                break
                        else:
                            cl.append({"lat": cyl["lat"], "items": [(n, cyl)]})
                out = []
                for k in cl:
                    if only is not None:
                        have = {n for n, _ in k["items"]}
                        if not all(o in have for o in only):
                            continue
                    elif len({n for n, _ in k["items"]}) < 2:
                        continue
                    out.append(k)
                return out

            plans = []          # lista di liste di (nome, faccia)

            def faces_of(cluster):
                chosen = {}
                for n, cyl in cluster["items"]:
                    if n not in chosen or cyl["area"] > chosen[n]["area"]:
                        chosen[n] = cyl
                items = sorted(chosen.items(), key=lambda kv: kv[1]["axial"])
                return [(n, c["face"]) for n, c in items]

            used_dir = None
            if groups:
                dirs = [_DIRS[direction.lower()][0]] if direction and direction.lower() in _DIRS else [0, 1, 2]
                for g in groups:
                    ok_g = False
                    for di in dirs:
                        cs = clusters_for(di, only=[str(self._as_comp(doc, n)[0].Name2) for n in g if self._as_comp(doc, n)[0] is not None])
                        if cs:
                            plans.append(faces_of(cs[0]))
                            used_dir = di
                            ok_g = True
                            break
                    if not ok_g:
                        return self._result(False, f"Nessun asse cilindrico comune ai componenti {g}", SwErrors.swInvalidInput)
            else:
                best = None
                dirs = [_DIRS[direction.lower()][0]] if direction and direction.lower() in _DIRS else [0, 1, 2]
                for di in dirs:
                    cs = clusters_for(di)
                    if best is None or len(cs) > len(best[1]):
                        best = (di, cs)
                if not best or not best[1]:
                    return self._result(False, "Nessun asse cilindrico condiviso fra componenti: nulla da collegare", SwErrors.swInvalidInput)
                used_dir = best[0]
                plans = [faces_of(k) for k in best[1]]
            ok_init = doc.SketchManager.InsertExplodeLineSketch
            if not ok_init:
                return self._result(False, "InsertExplodeLineSketch non riuscito (esiste gia' uno schizzo di esplosione in modifica?)",
                                    SwErrors.swFeatureError)
            sk = doc.GetActiveSketch2
            did = sk._oleobj_.GetIDsOfNames("InsertRouteLine")
            sd = doc.SelectionManager.CreateSelectData
            done, failed = [], []
            for items in plans:
                doc.ClearSelection2(True)
                sel = [bool(f.Select4(i > 0, sd)) for i, (_, f) in enumerate(items)]
                if len(items) < 2 or not all(sel):
                    failed.append([n for n, _ in items])
                    continue
                objs = [doc.SelectionManager.GetSelectedObject6(i + 1, -1) for i in range(len(items))]
                arr = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_VARIANT, tuple(objs))
                try:
                    r = sk._oleobj_.Invoke(did, 0, pythoncom.DISPATCH_METHOD, True, arr, False, False, False)
                except Exception as e:
                    logger.debug(f"route line: {e}")
                    r = False
                (done if r else failed).append([n for n, _ in items])
            nseg = 0
            try:
                nseg = len(sk.GetSketchSegments or ())
            except Exception:
                pass
            doc.ClearSelection2(True)
            doc.SketchManager.InsertSketch(True)
            doc.ClearSelection2(True)
            msg = f"Linee di esplosione: {len(done)} create ({nseg} segmenti)" + (f", {len(failed)} NON riuscite" if failed else "")
            return self._result(bool(done), msg, SwErrors.swSuccess if done else SwErrors.swFeatureError,
                                {"lines": len(done), "segments": nseg, "connected": done, "failed": failed,
                                 "direction": "xyz"[used_dir] if used_dir is not None else None, "explode_view": vname,
                                 "note": "salva l'assieme (save_document) perche' le viste di disegno vedano le linee"})
        except Exception as e:
            return self._as_fail("add_explode_lines", e)

    def show_exploded(self, exploded: bool = True, view_name: str = None) -> Dict:
        """Esplode (True) o comprime (False) l'assieme."""
        try:
            doc, err = self._asm()
            if err:
                return err
            names = self._ex_names(doc)
            if not names:
                return self._result(False, "L'assieme non ha una vista esplosa (create_exploded_view).", SwErrors.swInvalidInput)
            name = view_name or names[0]
            if name not in names:
                return self._result(False, f"Vista esplosa '{name}' non trovata. Presenti: {names}", SwErrors.swInvalidInput)
            doc.ShowExploded2(bool(exploded), name)
            now = bool(self._com(doc, "IsExploded"))
            return self._result(now == bool(exploded), f"Assieme {'esploso' if now else 'compresso'}",
                                SwErrors.swSuccess if now == bool(exploded) else SwErrors.swFeatureError,
                                {"exploded": now, "view": name})
        except Exception as e:
            return self._as_fail("show_exploded", e)

    def delete_explode_step(self, step: str) -> Dict:
        """Elimina un passo di esplosione per nome (come in list_exploded_views)."""
        try:
            doc, err = self._asm()
            if err:
                return err
            cfg = self._ex_config(doc)
            n0 = int(cfg.GetNumberOfExplodeSteps)
            cfg.DeleteExplodeStep(str(step))
            n1 = int(cfg.GetNumberOfExplodeSteps)
            return self._result(n1 < n0, f"Passi: {n0} -> {n1}", SwErrors.swSuccess if n1 < n0 else SwErrors.swFeatureError,
                                {"steps": self._ex_steps(doc)})
        except Exception as e:
            return self._as_fail("delete_explode_step", e)

    # ====================================================================
    # Interferenze e giochi
    # ====================================================================

    def check_interference(self, components: list = None, include_coincident: bool = False,
                           treat_subassemblies_as_components: bool = False) -> Dict:
        """Rileva le interferenze: coppie di componenti e volume (mm3). `components` (opzionale) limita il risultato alle
        coppie che coinvolgono quei componenti. include_coincident: conta come interferenza anche le facce coincidenti."""
        mgr = None
        try:
            doc, err = self._asm()
            if err:
                return err
            self._as_collapse(doc)
            doc.ForceRebuild2(False)
            mgr = doc.InterferenceDetectionManager
            mgr.TreatCoincidenceAsInterference = bool(include_coincident)
            mgr.TreatSubAssembliesAsComponents = bool(treat_subassemblies_as_components)
            try:
                mgr.IncludeMultibodyPartInterferences = False
            except Exception:
                pass
            ints = self._com(mgr, "GetInterferences") or ()
            only = None
            if components:
                cs, e = self._as_comps(doc, components, False)
                if e:
                    return self._result(False, e, SwErrors.swSelectionError)
                only = {str(c.Name2) for c in cs}
            rows = []
            for it in ints:
                names = [str(c.Name2) for c in (it.Components or ())]
                if only is not None and not (only & set(names)):
                    continue
                rows.append({"components": names, "volume_mm3": round(float(it.Volume) * 1e9, 4)})
            total = round(sum(r["volume_mm3"] for r in rows), 4)
            msg = (f"{len(rows)} interferenze, volume totale {total} mm3" if rows else "Nessuna interferenza")
            return self._result(True, msg, SwErrors.swSuccess,
                                {"count": len(rows), "interferences": rows, "total_volume_mm3": total})
        except Exception as e:
            return self._as_fail("check_interference", e)
        finally:
            try:
                if mgr is not None:
                    mgr.Done()
            except Exception:
                pass

    def _run_interference_check(self, doc, target_names: set = None, include_coincident: bool = False,
                                treat_subassemblies_as_components: bool = False) -> List[Dict]:
        """Esegue il controllo interferenze nativo dell'assieme e restituisce la lista di collisioni."""
        mgr = None
        rows = []
        try:
            mgr = doc.InterferenceDetectionManager
            mgr.TreatCoincidenceAsInterference = bool(include_coincident)
            mgr.TreatSubAssembliesAsComponents = bool(treat_subassemblies_as_components)
            try:
                mgr.IncludeMultibodyPartInterferences = False
            except Exception:
                pass
            ints = self._com(mgr, "GetInterferences") or ()
            for it in ints:
                names = [str(c.Name2) for c in (it.Components or ())]
                if target_names is not None and not (target_names & set(names)):
                    continue
                vol = round(float(it.Volume) * 1e9, 4) if hasattr(it, "Volume") else 0.0
                rows.append({"components": names, "volume_mm3": vol})
        finally:
            if mgr is not None:
                try:
                    mgr.Done()
                except Exception:
                    pass
        return rows

    def detect_collisions(self, moving_component: str = None,
                          dx: float = 0.0, dy: float = 0.0, dz: float = 0.0,
                          unit: str = None, steps: int = 10,
                          stop_on_collision: bool = True,
                          components: list = None,
                          include_coincident: bool = False,
                          treat_subassemblies_as_components: bool = False) -> Dict:
        """Rileva collisioni/interferenze nell'assieme, in modalita' statica o dinamica lungo una traiettoria lineare."""
        try:
            doc, err = self._asm()
            if err:
                return err
            self._as_collapse(doc)

            target_names = None
            if components:
                cs, e = self._as_comps(doc, components, False)
                if e:
                    return self._result(False, e, SwErrors.swSelectionError)
                target_names = {str(c.Name2) for c in cs}

            # 1. Modalita' STATICA: nessuna componente in movimento specificata
            if not moving_component:
                doc.ForceRebuild2(False)
                rows = self._run_interference_check(doc, target_names, include_coincident, treat_subassemblies_as_components)
                total = round(sum(r["volume_mm3"] for r in rows), 4)
                has_collision = len(rows) > 0
                msg = (f"Rilevate {len(rows)} interferenze (volume {total} mm3)" if has_collision else "Nessuna collisione rilevata nell'assieme.")
                return self._result(True, msg, SwErrors.swSuccess, {
                    "mode": "static",
                    "collision_detected": has_collision,
                    "count": len(rows),
                    "total_volume_mm3": total,
                    "collisions": rows
                })

            # 2. Modalita' DINAMICA: traiettoria del componente mobile
            comp, e = self._as_comp(doc, moving_component)
            if not comp:
                return self._result(False, f"Componente '{moving_component}' non trovato", SwErrors.swSelectionError)
            moving_name = str(comp.Name2)
            if target_names is None:
                target_names = {moving_name}
            else:
                target_names.add(moving_name)

            M0, t0 = self._as_pose(comp)
            dx_m = self._mmu(float(dx or 0.0), unit)
            dy_m = self._mmu(float(dy or 0.0), unit)
            dz_m = self._mmu(float(dz or 0.0), unit)

            total_dist_unit = math.sqrt((dx or 0.0)**2 + (dy or 0.0)**2 + (dz or 0.0)**2)
            n_steps = max(1, min(100, int(steps or 10)))

            trajectory_collisions = []
            first_collision = None

            try:
                for k in range(1, n_steps + 1):
                    frac = k / float(n_steps)
                    tk = [t0[0] + dx_m * frac, t0[1] + dy_m * frac, t0[2] + dz_m * frac]
                    try:
                        comp.Transform2 = self._as_transform(M0, tk)
                        doc.ForceRebuild2(False)
                    except Exception as ex:
                        logger.warning(f"detect_collisions step {k} transform error: {ex}")
                        continue

                    hits = self._run_interference_check(doc, target_names, include_coincident, treat_subassemblies_as_components)
                    moving_hits = [h for h in hits if moving_name in h["components"]]
                    if moving_hits:
                        colliding_partners = sorted({c for h in moving_hits for c in h["components"] if c != moving_name})
                        step_data = {
                            "step": k,
                            "fraction": round(frac, 4),
                            "displacement": [round((dx or 0.0) * frac, 4), round((dy or 0.0) * frac, 4), round((dz or 0.0) * frac, 4)],
                            "distance_traveled": round(total_dist_unit * frac, 4),
                            "colliding_with": colliding_partners,
                            "interferences": moving_hits
                        }
                        trajectory_collisions.append(step_data)
                        if first_collision is None:
                            first_collision = step_data
                        if stop_on_collision:
                            break
            finally:
                # Ripristino tassativo della posa iniziale
                try:
                    comp.Transform2 = self._as_transform(M0, t0)
                    doc.ForceRebuild2(False)
                except Exception:
                    pass

            has_collision = len(trajectory_collisions) > 0
            u = unit or "mm"
            if has_collision:
                fc_step = first_collision["step"]
                safe_frac = (fc_step - 1) / float(n_steps)
                max_safe = round(total_dist_unit * safe_frac, 4)
                msg = f"Collisione rilevata al passo {fc_step}/{n_steps} con {first_collision['colliding_with']} (corsa libera: {max_safe} {u})."
            else:
                max_safe = round(total_dist_unit, 4)
                msg = f"Nessuna collisione rilevata lungo la traiettoria ({total_dist_unit} {u} su {n_steps} passi)."

            return self._result(True, msg, SwErrors.swSuccess, {
                "mode": "dynamic",
                "moving_component": moving_name,
                "collision_detected": has_collision,
                "steps_tested": len(trajectory_collisions) if (stop_on_collision and has_collision) else n_steps,
                "first_collision_step": first_collision["step"] if first_collision else None,
                "max_safe_displacement": max_safe,
                "unit": u,
                "initial_pose_restored": True,
                "collisions": trajectory_collisions
            })
        except Exception as e:
            return self._as_fail("detect_collisions", e)

    def check_clearance(self, entity1, entity2, unit: str = None) -> Dict:
        """Distanza minima (gioco) fra due componenti ('perno-1') o due entita' ({"face":[x,y,z]}, 'Assi1@staffa-1'...).
        Distanza 0 = a contatto o interferenti."""
        try:
            doc, err = self._asm()
            if err:
                return err
            self._as_collapse(doc)
            doc.ClearSelection2(True)
            infos = []
            for i, spec in enumerate((entity1, entity2)):
                info, e = self._as_select_entity(doc, spec, unit, 0, i > 0)
                if e:
                    return self._result(False, f"Entita' {i + 1}: {e}", SwErrors.swSelectionError)
                infos.append(info)
            m = self._com(doc.Extension, "CreateMeasure")
            if m is None:
                return self._result(False, "CreateMeasure non disponibile", SwErrors.swUnknownError)
            try:
                ok = m.Calculate                       # proprieta' in late binding (la lettura calcola)
                if callable(ok) and not isinstance(ok, win32com.client.CDispatch):
                    ok = ok(_null())
            except Exception:
                ok = m.Calculate(_null())
            if not ok:
                doc.ClearSelection2(True)
                return self._result(False, "Misura non riuscita (selezione non misurabile).", SwErrors.swFeatureError)
            dist = float(m.Distance)
            contact = dist < 0                              # -1 = non misurabile: oggetti a contatto o sovrapposti
            data = {"distance_mm": 0.0 if contact else round(dist * 1000, 6), "contact_or_overlap": contact, "entities": infos}
            try:
                nd = float(m.NormalDistance)
                if nd >= 0:
                    data["normal_distance_mm"] = round(nd * 1000, 6)
            except Exception:
                pass
            doc.ClearSelection2(True)
            msg = "Componenti a contatto o sovrapposti (gioco 0)" if contact else f"Gioco minimo {dist * 1000:.4f} mm"
            return self._result(True, msg, SwErrors.swSuccess, data)
        except Exception as e:
            return self._as_fail("check_clearance", e)

    # ====================================================================
    # Massa e conteggi
    # ====================================================================

    def _model_mass(self, comp) -> Optional[float]:
        try:
            md = self._com(comp, "GetModelDoc2")
            if md is None:
                return None
            mp = self._mass_props(md)
            return float(self._com(mp, "Mass")) if mp is not None else None
        except Exception:
            return None

    def get_assembly_mass_properties(self, unit: str = None) -> Dict:
        """Massa, volume, area, baricentro dell'assieme + massa di ogni file (per istanza) e verifica massa = somma componenti."""
        try:
            doc, err = self._asm()
            if err:
                return err
            self._as_collapse(doc)
            doc.ForceRebuild2(False)
            mp = self._mass_props(doc)
            if mp is None:
                return self._result(False, "CreateMassProperty non disponibile", SwErrors.swUnknownError)
            mass = float(self._com(mp, "Mass"))
            vol = float(self._com(mp, "Volume"))
            area = float(self._com(mp, "SurfaceArea"))
            com = [round(v * 1000, 4) for v in self._com(mp, "CenterOfMass")]
            by_file: Dict[str, Dict] = {}
            for c in self._as_top_components(doc, False):
                try:
                    if int(self._com(c, "GetSuppression")) == 0:
                        continue
                    md = self._com(c, "GetModelDoc2")
                    if md is None or int(self._com(md, "GetType")) != 1:
                        continue                       # solo foglie (pezzi)
                    path = self._as_comp_path(c)
                    row = by_file.setdefault(path, {"file": os.path.basename(path), "count": 0,
                                                    "unit_mass_kg": self._model_mass(c)})
                    row["count"] += 1
                except Exception:
                    continue
            rows = sorted(by_file.values(), key=lambda r: r["file"])
            summed = sum((r["unit_mass_kg"] or 0.0) * r["count"] for r in rows)
            for r in rows:
                r["total_mass_kg"] = (r["unit_mass_kg"] or 0.0) * r["count"]
            return self._result(True, f"Massa {mass:.5f} kg, volume {vol * 1e9:.1f} mm3", SwErrors.swSuccess,
                                {"mass_kg": mass, "volume_mm3": round(vol * 1e9, 4), "surface_area_mm2": round(area * 1e6, 4),
                                 "center_of_mass_mm": com, "sum_of_components_kg": summed,
                                 "difference_kg": mass - summed, "files": rows})
        except Exception as e:
            return self._as_fail("get_assembly_mass_properties", e)

    def count_components(self, top_level_only: bool = False) -> Dict:
        """Conteggio dei componenti per file (istanze, soppresse, nomi)."""
        try:
            doc, err = self._asm()
            if err:
                return err
            by_file: Dict[str, Dict] = {}
            total = 0
            for c in self._as_top_components(doc, top_level_only):
                path = self._as_comp_path(c)
                sup = int(self._com(c, "GetSuppression")) == 0
                row = by_file.setdefault(path, {"file": os.path.basename(path), "path": path, "count": 0,
                                                "suppressed": 0, "instances": []})
                row["count"] += 1
                row["suppressed"] += 1 if sup else 0
                row["instances"].append(str(c.Name2))
                total += 1
            rows = sorted(by_file.values(), key=lambda r: r["file"])
            for r in rows:
                r["instances"].sort()
            return self._result(True, f"{total} componenti in {len(rows)} file", SwErrors.swSuccess,
                                {"total": total, "distinct_files": len(rows), "files": rows})
        except Exception as e:
            return self._as_fail("count_components", e)

    # ====================================================================
    # Configurazioni
    # ====================================================================

    def list_assembly_configurations(self) -> Dict:
        """Configurazioni dell'assieme (e quella attiva)."""
        try:
            doc, err = self._asm()
            if err:
                return err
            names = [str(n) for n in (self._com(doc, "GetConfigurationNames") or ())]
            active = str(self._ex_config(doc).Name)
            return self._result(True, f"{len(names)} configurazioni (attiva: {active})", SwErrors.swSuccess,
                                {"configurations": names, "active": active})
        except Exception as e:
            return self._as_fail("list_assembly_configurations", e)

    def add_assembly_configuration(self, name: str, comment: str = "", activate: bool = True) -> Dict:
        """Aggiunge una configurazione all'assieme (copia dello stato attuale)."""
        try:
            doc, err = self._asm()
            if err:
                return err
            cm = self._com(doc, "ConfigurationManager")
            cfg = cm.AddConfiguration(str(name), str(comment), "", 0, "", "")
            if cfg is None:
                return self._result(False, f"Configurazione '{name}' non creata (nome gia' usato?)", SwErrors.swFeatureError)
            if activate:
                doc.ShowConfiguration2(str(name))
            return self._result(True, f"Configurazione {name} creata", SwErrors.swSuccess,
                                {"configurations": [str(n) for n in (self._com(doc, "GetConfigurationNames") or ())],
                                 "active": str(self._ex_config(doc).Name)})
        except Exception as e:
            return self._as_fail("add_assembly_configuration", e)

    def activate_assembly_configuration(self, name: str) -> Dict:
        """Attiva una configurazione dell'assieme."""
        try:
            doc, err = self._asm()
            if err:
                return err
            names = [str(n) for n in (self._com(doc, "GetConfigurationNames") or ())]
            if name not in names:
                return self._result(False, f"Configurazione '{name}' non trovata. Presenti: {names}", SwErrors.swInvalidInput)
            doc.ShowConfiguration2(str(name))
            active = str(self._ex_config(doc).Name)
            return self._result(active == name, f"Configurazione attiva: {active}",
                                SwErrors.swSuccess if active == name else SwErrors.swFeatureError, {"active": active})
        except Exception as e:
            return self._as_fail("activate_assembly_configuration", e)

    def set_component_configuration(self, component: str, configuration: str) -> Dict:
        """Cambia la configurazione usata da un componente (del suo file)."""
        try:
            doc, err = self._asm()
            if err:
                return err
            comp, e = self._as_comp(doc, component, True)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            comp.ReferencedConfiguration = str(configuration)
            doc.ForceRebuild2(False)
            now = str(comp.ReferencedConfiguration)
            return self._result(now == configuration, f"{component}: configurazione {now}",
                                SwErrors.swSuccess if now == configuration else SwErrors.swFeatureError, {"configuration": now})
        except Exception as e:
            return self._as_fail("set_component_configuration", e)
