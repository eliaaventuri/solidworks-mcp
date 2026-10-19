"""
Lotto CORPI 2 (sposta/copia, dividi, interseca, scala corpi; ripetizioni guidate da curva/schizzo/tabella) (mixin).
Schemi in tools_ext/bodies2.py. I metodi usano gli helper di ModelingBase/ModelingOperations e di MokaOperations tramite self
(_part, _select_any, _finish, _names, _new_features, _volume_m3, _mmu, _result, _all_bodies, _resolve_bodies, _body_row...).

Trappole API scoperte (SW 2026, misurate nel laboratorio bd2, vedi scripts_tmp/notes_bodies2.md):
 - PreSplitBody2 e' una PROPRIETA' (late binding) e restituisce i pezzi risultanti; PostSplitBody2(pezzi, consuma, ORIGINI, PERCORSI,
   modello) crea la feature SOLO se ORIGINI e' un array di corpi (si usano gli stessi pezzi) e PERCORSI un array di stringhe ("" =
   non salvare); con ORIGINI nulle restituisce None senza creare nulla e lascia SolidWorks in uno stato che fa fallire le chiamate
   seguenti. Con percorsi veri la chiamata scrive i file ma NON ritorna (appeso): per salvare si divide e poi si usa
   CreateSaveBodyFeature.
 - PreIntersect2(cap, tipo) restituisce le regioni (array di corpi); PostIntersect(ESCLUDI, unisci, consuma): ESCLUDI e' un array di
   BOOLEANI (VT_BOOL) uno per regione, True = escludi (array di corpi o di interi: ignorato).
"""

import os
import math
import logging
import traceback
from typing import Dict

import pythoncom
import win32com.client

from ..constants import SwErrors

logger = logging.getLogger(__name__)

_AXES = {"x": 0, "y": 1, "z": 2}


def _vt_disp(items):
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, tuple(items))


def _vt_str(items):
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_BSTR, tuple(items))


def _vt_bool(items):
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_BOOL, tuple(bool(x) for x in items))


class Bodies2Operations:
    """Mixin del lotto bodies2."""

    # ------------------------------------------------------------------ utilita'
    def _bd2_solid_volume(self, bodies) -> float:
        """Somma dei volumi (mm3) dei corpi solidi della lista."""
        tot = 0.0
        for b in bodies:
            try:
                if int(self._com(b, "GetType")) == 0:
                    tot += float(b.GetMassProperties(1000.0)[3]) * 1e9
            except Exception:
                pass
        return tot

    def _bd2_boxes(self, bodies, unit) -> list:
        out = []
        for b in bodies:
            bx = self._body_box(b)
            out.append({"name": str(self._com(b, "Name")),
                        "box_min": [round(self._from_m(v, unit), 4) for v in bx[0:3]],
                        "box_max": [round(self._from_m(v, unit), 4) for v in bx[3:6]]})
        return out

    def _bd2_open_titles(self) -> list:
        """Titoli dei documenti aperti in SolidWorks."""
        out = []
        try:
            d = self._sw_app.GetFirstDocument
            while d is not None and len(out) < 200:
                out.append(str(self._com(d, "GetTitle")))
                d = self._com(d, "GetNext")
        except Exception:
            pass
        return out

    def _bd2_select_bodies(self, doc, bodies, idx, mark: int, append: bool = False) -> bool:
        sd = self._sd(doc, mark)
        for k, i in enumerate(idx):
            if not bool(bodies[i].Select2(append or k > 0, sd)):
                return False
        return True

    def _bd2_select_refs(self, doc, refs, unit, mark: int, append: bool):
        """Seleziona riferimenti generici (piani, facce piane, superfici...) -> errore | None."""
        if refs is None:
            return None
        if not isinstance(refs, (list, tuple)) or (len(refs) == 3 and all(isinstance(c, (int, float)) for c in refs)):
            refs = [refs]
        for k, r in enumerate(refs):
            ok, msg, _ = self._select_any(doc, r, unit, append=(append or k > 0), mark=mark)
            if not ok:
                return f"Riferimento {r}: {msg}"
        return None

    def _bd2_axis_spec(self, doc, axis, point, unit):
        """Asse di rotazione parallelo a X/Y/Z -> (indice asse 0..2, punto sull'asse in m, errore). axis: 'x'|'y'|'z' oppure
        {"edge":[x,y,z]} (spigolo rettilineo parallelo a un asse coordinato: il punto e' preso sullo spigolo)."""
        if isinstance(axis, str):
            k = _AXES.get(axis.strip().lower())
            if k is None:
                return None, None, f"asse '{axis}' non valido (x | y | z | {{\"edge\":[x,y,z]}})"
            p = [0.0, 0.0, 0.0] if point is None else [self._mmu(float(c), unit) for c in point]
            return k, p, None
        if isinstance(axis, dict) and "edge" in axis:
            p0 = [self._mmu(float(c), unit) for c in axis["edge"]]
            ent, _ = self._find_entity(doc, "edge", p0, 0.00005)
            if ent is None:
                return None, None, f"nessuno spigolo a meno di 0,05 mm da {axis['edge']}"
            try:
                lp = list(self._com(self._com(ent, "GetCurve"), "LineParams"))
            except Exception:
                return None, None, "lo spigolo dell'asse non e' rettilineo"
            if len(lp) < 6:
                return None, None, "lo spigolo dell'asse non e' rettilineo"
            dvec = [float(v) for v in lp[3:6]]
            n = math.sqrt(sum(v * v for v in dvec)) or 1.0
            dvec = [v / n for v in dvec]
            k = max(range(3), key=lambda i: abs(dvec[i]))
            if abs(dvec[k]) < 0.999999:
                return None, None, ("SolidWorks (InsertMoveCopyBody2) ruota solo attorno ad assi paralleli a X, Y o Z: "
                                    f"lo spigolo ha direzione {[round(v, 4) for v in dvec]}")
            return k, [float(v) for v in lp[0:3]], None
        return None, None, f"asse non valido: {axis}"

    # ------------------------------------------------------------------ move_copy_body
    def move_copy_body(self, bodies, translate=None, from_point=None, to_point=None, rotate_angle: float = None,
                       rotate_axis="z", rotate_point=None, copies: int = 0, unit: str = None) -> Dict:
        """Sposta / ruota / copia corpi (InsertMoveCopyBody2). Rotazione e traslazione sono due feature distinte
        (SolidWorks non le accetta insieme); con `copies` > 0 si ottiene UNA delle due operazioni ripetuta."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            allb = self._all_bodies(doc)
            idx, e = self._resolve_bodies(doc, bodies, unit, allb)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            if translate is not None and (from_point is not None or to_point is not None):
                return self._result(False, "Usa `translate` OPPURE `from_point`+`to_point`.", SwErrors.swInvalidInput)
            if (from_point is None) != (to_point is None):
                return self._result(False, "from_point e to_point vanno dati insieme.", SwErrors.swInvalidInput)
            if from_point is not None:
                if len(from_point) != 3 or len(to_point) != 3:
                    return self._result(False, "from_point e to_point vogliono 3 numeri [x,y,z].", SwErrors.swInvalidInput)
                translate = [float(t) - float(f) for f, t in zip(from_point, to_point)]
            tr = None
            if translate is not None:
                if len(translate) != 3:
                    return self._result(False, "translate vuole 3 numeri [dx,dy,dz].", SwErrors.swInvalidInput)
                tr = [self._mmu(float(c), unit) for c in translate]
                if all(abs(c) < 1e-12 for c in tr):
                    tr = None
            rot = None
            if rotate_angle is not None and abs(float(rotate_angle)) > 1e-12:
                k, p, e = self._bd2_axis_spec(doc, rotate_axis, rotate_point, unit)
                if e:
                    return self._result(False, e, SwErrors.swInvalidInput)
                ang = [0.0, 0.0, 0.0]
                ang[k] = math.radians(float(rotate_angle))
                rot = (p, ang)
            ncop = int(copies or 0)
            if ncop < 0:
                return self._result(False, "copies deve essere >= 0.", SwErrors.swInvalidInput)
            if tr is None and rot is None:
                return self._result(False, "Niente da fare: serve una traslazione (translate | from_point+to_point) e/o una "
                                    "rotazione (rotate_angle).", SwErrors.swInvalidInput)
            if ncop > 0 and tr is not None and rot is not None:
                return self._result(False, "Con `copies` > 0 si ripete UNA sola operazione: dai la traslazione oppure la rotazione.",
                                    SwErrors.swInvalidInput)
            names0 = [str(self._com(b, "Name")) for b in allb]
            sel_names = [names0[i] for i in idx]
            keys0 = {self._body_key(b) for b in allb}
            v0 = self._bd2_solid_volume(allb)
            steps = []
            if rot is not None:
                p, ang = rot
                # misurato (moka2): RotAngleX/Y/Z ruotano attorno agli assi Z/Y/X -> si invertono
                steps.append(("rotation", (0.0, 0.0, 0.0, 0.0, p[0], p[1], p[2], ang[2], ang[1], ang[0])))
            if tr is not None:
                steps.append(("translation", (tr[0], tr[1], tr[2], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)))
            feats = []
            for what, args in steps:
                cur = self._all_bodies(doc)
                cidx = [i for i, b in enumerate(cur) if str(self._com(b, "Name")) in sel_names]
                doc.ClearSelection2(True)
                if not cidx or not self._bd2_select_bodies(doc, cur, cidx, 1):
                    doc.ClearSelection2(True)
                    return self._result(False, "Selezione dei corpi rifiutata da SolidWorks.", SwErrors.swSelectionError)
                before = self._names(doc)
                mv = doc.FeatureManager.InsertMoveCopyBody2(*args, ncop > 0, max(ncop, 0))
                doc.ClearSelection2(True)
                created = self._new_features(doc, before)
                if mv is None and not created:
                    return self._result(False, f"SolidWorks non ha creato la feature ({what}).", SwErrors.swFeatureError,
                                        {"features_done": feats})
                feats.append(str(self._com(mv, "Name")) if mv is not None else created[0]["name"])
            after = self._all_bodies(doc)
            new_b = [b for b in after if self._body_key(b) not in keys0]
            v1 = self._bd2_solid_volume(after)
            data = {"features": feats, "bodies_before": len(allb), "bodies_after": len(after), "copies": ncop,
                    "selected": sel_names, "solid_volume_before_mm3": round(v0, 4), "solid_volume_after_mm3": round(v1, 4),
                    "boxes_after": self._bd2_boxes(after, unit), "moved_or_new": self._bd2_boxes(new_b, unit),
                    "unit": self._unit_name(unit)}
            if ncop > 0 and len(after) != len(allb) + ncop * len(idx):
                return self._result(False, f"Copie attese {ncop * len(idx)}, corpi passati da {len(allb)} a {len(after)}.",
                                    SwErrors.swFeatureError, data)
            what = "Copiati" if ncop else "Spostati"
            return self._result(True, f"{what} {len(idx)} corpi ({'+'.join(f[0] for f in steps)}): {len(allb)} -> {len(after)} corpi, "
                                f"volume solido {v0:.1f} -> {v1:.1f} mm3", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"move_copy_body: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ split_body
    def split_body(self, tools, save_path: str = None, unit: str = None) -> Dict:
        """Divide corpi con piani / facce piane / superfici (PreSplitBody2 + PostSplitBody2); tiene tutti i pezzi e, se
        `save_path` e' dato, li salva come file <nome>_1.sldprt, <nome>_2.sldprt... (CreateSaveBodyFeature)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            allb = self._all_bodies(doc)
            if save_path:
                base, ext = os.path.splitext(os.path.abspath(str(save_path)))
                ext = ext or ".sldprt"
                if ext.lower() != ".sldprt":
                    return self._result(False, "save_path deve avere estensione .sldprt", SwErrors.swInvalidInput)
                try:
                    os.makedirs(os.path.dirname(base), exist_ok=True)
                except OSError as ex:
                    return self._result(False, f"Cartella non creabile ({os.path.dirname(base)}): {ex}", SwErrors.swInvalidInput)
            names0 = [str(self._com(b, "Name")) for b in allb]
            v0 = self._bd2_solid_volume(allb)
            before = self._names(doc)
            doc.ClearSelection2(True)
            e = self._bd2_select_refs(doc, tools, unit, 2, False)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            fm = doc.FeatureManager
            pieces = list(fm.PreSplitBody2 or [])
            if len(pieces) < 2:
                doc.ClearSelection2(True)
                return self._result(False, "Lo strumento non divide nessun corpo (non attraversa il corpo?).",
                                    SwErrors.swFeatureError, {"pieces": len(pieces)})
            feat = fm.PostSplitBody2(_vt_disp(pieces), False, _vt_disp(pieces), _vt_str([""] * len(pieces)), "")
            doc.ClearSelection2(True)
            created = [x for x in self._new_features(doc, before) if x["type"] != "ProfileFeature"]
            after = self._all_bodies(doc)
            if feat is None and not created:
                return self._result(False, "SolidWorks non ha creato la feature Dividi.", SwErrors.swFeatureError,
                                    {"pieces_expected": len(pieces)})
            v1 = self._bd2_solid_volume(after)
            new_b = [b for b in after if str(self._com(b, "Name")) not in names0]
            data = {"feature": str(self._com(feat, "Name")) if feat is not None else created[0]["name"],
                    "bodies_before": len(allb), "bodies_after": len(after), "pieces": len(pieces),
                    "solid_volume_before_mm3": round(v0, 4), "solid_volume_after_mm3": round(v1, 4),
                    "bodies": [dict(self._body_row(b, i, unit)) for i, b in enumerate(after)], "unit": self._unit_name(unit)}
            ok_msg = f"Diviso in {len(pieces)} pezzi: {len(allb)} -> {len(after)} corpi, volume {v0:.1f} -> {v1:.1f} mm3"
            if abs(v1 - v0) > 1e-4 * max(v0, 1.0):
                return self._result(False, ok_msg + " - il volume non si conserva.", SwErrors.swFeatureError, data)
            if save_path:
                order = sorted(new_b, key=lambda b: tuple(self._body_box(b)[0:3]))
                targets_paths = [f"{base}_{k + 1}{ext}" for k in range(len(order))]
                existing = [t for t in targets_paths if os.path.exists(t)]
                if existing:
                    return self._result(False, f"Divisione fatta ({data['feature']}) ma il salvataggio e' rifiutato: file gia' "
                                        f"esistenti {existing}. Scegli un altro save_path.", SwErrors.swFeatureError, data)
                order_names = [str(self._com(b, "Name")) for b in order]
                titles0 = self._bd2_open_titles()
                title_doc = self._get_doc_title(doc)
                sv = fm.CreateSaveBodyFeature(_vt_disp(order), _vt_str(targets_paths), "", False, False)
                doc.ClearSelection2(True)
                # la feature apre i pezzi salvati e crea un assieme senza nome: si richiudono (i file sono gia' su disco)
                closed = []
                for t in self._bd2_open_titles():
                    if t not in titles0:
                        self.close_document(discard=True, document=t)
                        closed.append(t)
                if closed:
                    self.activate_document(title_doc)
                    data["closed_temporary_documents"] = closed
                files = [{"body": nm, "path": t, "exists": os.path.isfile(t),
                          "size": os.path.getsize(t) if os.path.isfile(t) else 0} for nm, t in zip(order_names, targets_paths)]
                data["saved_files"] = files
                data["save_feature"] = str(self._com(sv, "Name")) if sv is not None else None
                if sv is None or not all(f["exists"] and f["size"] > 0 for f in files):
                    return self._result(False, ok_msg + " - salvataggio dei pezzi non riuscito.", SwErrors.swFeatureError, data)
                ok_msg += f"; salvati {len(files)} file"
            return self._result(True, ok_msg, SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"split_body: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ intersect_bodies
    def _bd2_region_inside(self, region, solids) -> list:
        """Per ogni corpo solido: True se la regione sta dentro di lui (intersezione non vuota con una copia)."""
        out = []
        for s in solids:
            try:
                r = region.Copy2(True).Operations2(15901, s.Copy2(True), 0)       # swBodyOperationType_e.SWBODYINTERSECT
                out.append(r[0] is not None)
            except Exception:
                out.append(None)
        return out

    def intersect_bodies(self, bodies, tools=None, regions="common", cap_planar: bool = False, merge: bool = False,
                         unit: str = None) -> Dict:
        """Interseca corpi (e piani / facce / superfici come strumenti): PreIntersect2 + PostIntersect. `regions` sceglie quali
        regioni tenere: 'common' (dentro a TUTTI i corpi solidi indicati, default) | 'all' | lista di indici (ordine del
        risultato `regions`)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            allb = self._all_bodies(doc)
            idx, e = self._resolve_bodies(doc, bodies, unit, allb)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            if not (isinstance(regions, (list, tuple)) or regions in ("common", "all")):
                return self._result(False, "regions deve essere 'common' | 'all' | lista di indici", SwErrors.swInvalidInput)
            if len(idx) + (len(tools) if isinstance(tools, (list, tuple)) else (1 if tools else 0)) < 2:
                return self._result(False, "Servono almeno due oggetti da intersecare (corpi e/o strumenti).", SwErrors.swInvalidInput)
            solids = []
            for i in idx:
                try:
                    if int(self._com(allb[i], "GetType")) == 0:
                        solids.append(allb[i])
                except Exception:
                    pass
            names0 = [str(self._com(b, "Name")) for b in allb]
            v0 = self._bd2_solid_volume(allb)
            before = self._names(doc)
            doc.ClearSelection2(True)
            if not self._bd2_select_bodies(doc, allb, idx, 1):
                doc.ClearSelection2(True)
                return self._result(False, "Selezione dei corpi rifiutata.", SwErrors.swSelectionError)
            e = self._bd2_select_refs(doc, tools, unit, 1, True)
            if e:
                doc.ClearSelection2(True)
                return self._result(False, e, SwErrors.swSelectionError)
            fm = doc.FeatureManager
            regs = list(fm.PreIntersect2(bool(cap_planar), 0) or [])
            if not regs:
                doc.ClearSelection2(True)
                return self._result(False, "Nessuna regione di intersezione (gli oggetti non si incontrano).", SwErrors.swFeatureError)
            info = []
            for i, r in enumerate(regs):
                inside = self._bd2_region_inside(r, solids)
                bx = self._body_box(r)
                try:
                    vol = float(r.GetMassProperties(1000.0)[3]) * 1e9
                except Exception:
                    vol = 0.0
                info.append({"index": i, "volume_mm3": round(vol, 4), "inside": inside,
                             "box_min": [round(self._from_m(v, unit), 4) for v in bx[0:3]],
                             "box_max": [round(self._from_m(v, unit), 4) for v in bx[3:6]]})
            if regions == "all":
                keep = [True] * len(regs)
            elif regions == "common":
                keep = [all(x is True for x in inf["inside"]) for inf in info]
            else:
                want = {int(x) for x in regions}
                keep = [i in want for i in range(len(regs))]
            for inf, k in zip(info, keep):
                inf["kept"] = bool(k)
            dropped_all = not any(keep)
            flags = [(not k) for k in keep] if not dropped_all else [False] * len(regs)
            feat = fm.PostIntersect(_vt_bool(flags), bool(merge), True)
            doc.ClearSelection2(True)
            created = [x for x in self._new_features(doc, before) if x["type"] != "ProfileFeature"]
            if dropped_all:
                if created:
                    self._delete_features(doc, [x["name"] for x in created])
                return self._result(False, "Nessuna regione da tenere con questa scelta (`regions`): l'intersezione e' annullata.",
                                    SwErrors.swFeatureError, {"regions": info})
            after = self._all_bodies(doc)
            v1 = self._bd2_solid_volume(after)
            data = {"feature": str(self._com(feat, "Name")) if feat is not None else (created[0]["name"] if created else None),
                    "regions": info, "bodies_before": len(allb), "bodies_after": len(after),
                    "solid_volume_before_mm3": round(v0, 4), "solid_volume_after_mm3": round(v1, 4),
                    "boxes_after": self._bd2_boxes(after, unit), "original_bodies": names0, "unit": self._unit_name(unit)}
            if feat is None and not created:
                return self._result(False, "SolidWorks non ha creato la feature Interseca.", SwErrors.swFeatureError, data)
            return self._result(True, f"Interseca: {len(regs)} regioni, tenute {sum(keep)}; {len(allb)} -> {len(after)} corpi, "
                                f"volume solido {v0:.1f} -> {v1:.1f} mm3", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"intersect_bodies: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ scale_body
    def scale_body(self, factor: float = None, factor_x: float = None, factor_y: float = None, factor_z: float = None,
                   about: str = "centroid", coordinate_system: str = None, bodies=None, unit: str = None) -> Dict:
        """Scala corpi (InsertScale) in modo uniforme (`factor`) o per assi (factor_x/y/z, mancanti = 1) rispetto al baricentro,
        all'origine o a un sistema di coordinate. Senza `bodies` scala tutti i corpi della parte."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            if factor is not None and any(f is not None for f in (factor_x, factor_y, factor_z)):
                return self._result(False, "Usa `factor` (uniforme) OPPURE factor_x/y/z (per assi).", SwErrors.swInvalidInput)
            if factor is None and all(f is None for f in (factor_x, factor_y, factor_z)):
                return self._result(False, "Serve `factor` oppure almeno uno fra factor_x, factor_y, factor_z.", SwErrors.swInvalidInput)
            uniform = factor is not None
            fx, fy, fz = ((float(factor),) * 3) if uniform else tuple(1.0 if f is None else float(f)
                                                                       for f in (factor_x, factor_y, factor_z))
            if min(fx, fy, fz) <= 0:
                return self._result(False, "I fattori di scala devono essere > 0.", SwErrors.swInvalidInput)
            stype = {"centroid": 0, "origin": 1, "coordinate_system": 2}.get((about or "centroid").lower())
            if stype is None:
                return self._result(False, "about deve essere centroid | origin | coordinate_system", SwErrors.swInvalidInput)
            if stype == 2 and not coordinate_system:
                return self._result(False, "about=coordinate_system richiede `coordinate_system` (nome della feature).",
                                    SwErrors.swInvalidInput)
            allb = self._all_bodies(doc)
            idx = None
            if bodies is not None:
                idx, e = self._resolve_bodies(doc, bodies, unit, allb)
                if e:
                    return self._result(False, e, SwErrors.swSelectionError)
            names0 = [str(self._com(b, "Name")) for b in allb]
            v0 = self._bd2_solid_volume(allb)
            before = self._names(doc)
            boxes0 = self._bd2_boxes(allb, unit)
            scaled = list(range(len(allb))) if idx is None else idx
            exp = v0 + self._bd2_solid_volume([allb[i] for i in scaled]) * (fx * fy * fz - 1)     # prima dell'operazione
            doc.ClearSelection2(True)
            if idx is not None and not self._bd2_select_bodies(doc, allb, idx, 0):
                doc.ClearSelection2(True)
                return self._result(False, "Selezione dei corpi rifiutata.", SwErrors.swSelectionError)
            if stype == 2:
                cs = self._find_feature(doc, coordinate_system)
                if cs is None or not bool(cs.Select2(idx is not None, 0)):
                    doc.ClearSelection2(True)
                    return self._result(False, f"Sistema di coordinate '{coordinate_system}' non trovato o non selezionabile.",
                                        SwErrors.swSelectionError)
            feat = doc.FeatureManager.InsertScale(stype, bool(uniform), fx, fy, fz)
            doc.ClearSelection2(True)
            created = [x for x in self._new_features(doc, before) if x["type"] != "ProfileFeature"]
            if feat is None and not created:
                return self._result(False, "SolidWorks non ha creato la feature Scala.", SwErrors.swFeatureError)
            after = self._all_bodies(doc)
            v1 = self._bd2_solid_volume(after)
            data = {"feature": str(self._com(feat, "Name")) if feat is not None else created[0]["name"],
                    "factors": [fx, fy, fz], "uniform": bool(uniform), "about": about,
                    "scaled_bodies": [names0[i] for i in scaled], "solid_volume_before_mm3": round(v0, 4),
                    "solid_volume_after_mm3": round(v1, 4), "expected_volume_mm3": round(exp, 4),
                    "boxes_before": boxes0, "boxes_after": self._bd2_boxes(after, unit), "unit": self._unit_name(unit)}
            if abs(v1 - exp) > 1e-4 * max(abs(exp), 1.0):
                return self._result(False, f"Scala: volume {v1:.2f} mm3, atteso {exp:.2f} mm3.", SwErrors.swFeatureError, data)
            return self._result(True, f"Scala {fx:g} x {fy:g} x {fz:g} ({about}): volume {v0:.1f} -> {v1:.1f} mm3",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"scale_body: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ ripetizioni guidate
    def _bd2_pattern_eval(self, doc, v0: float, seed: float):
        """-> (istanze aggiunte, delta volume mm3). seed = effetto del seme sul volume (m3, negativo = materiale aggiunto)."""
        vol = self._volume_m3(doc)
        delta = v0 - vol                 # positivo = materiale in meno
        if abs(seed) < 1e-15:
            return None, round((vol - v0) * 1e9, 4), None
        ratio = delta / seed
        return int(round(ratio)), round((vol - v0) * 1e9, 4), round(ratio, 4)

    def _bd2_read_pattern(self, doc, feat, props) -> dict:
        """Legge dalla definizione della feature le proprieta' indicate (nome -> valore)."""
        out = {}
        try:
            fd = self._com(feat, "GetDefinition")
            try:
                fd.AccessSelections(doc, win32com.client.VARIANT(pythoncom.VT_DISPATCH, None))
            except Exception:
                pass
            for p in props:
                try:
                    v = self._com(fd, p)
                    out[p] = v if isinstance(v, (int, float, bool, str)) else str(v)
                except Exception:
                    pass
            try:
                fd.ReleaseSelectionAccess()
            except Exception:
                pass
        except Exception:
            pass
        return out

    def _bd2_pattern_done(self, doc, label, feat, v0, before, seed, expected, extra):
        """Esito comune delle ripetizioni: feature creata, istanze aggiunte (dal volume) confrontate con le attese."""
        doc.ClearSelection2(True)
        created = [x for x in self._new_features(doc, before) if x["type"] != "ProfileFeature"]
        if feat is None and not created:
            return self._result(False, f"{label} non riuscita (SolidWorks non ha creato la feature). Controlla le selezioni e i "
                                "parametri: le istanze devono cadere sul corpo.", SwErrors.swFeatureError)
        name = str(self._com(feat, "Name")) if feat is not None else created[0]["name"]
        added, dvol, ratio = self._bd2_pattern_eval(doc, v0, seed)
        data = {"feature": name, "feature_type": created[0]["type"] if created else None,
                "instances_added": added, "instances_volume_ratio": ratio, "instances_expected": expected, "seed_volume_mm3": round(abs(seed) * 1e9, 4),
                "volume_delta_mm3": dvol, "volume_mm3": round(self._volume_m3(doc) * 1e9, 4)}
        data.update(extra)
        if ratio is not None and abs(ratio - added) > 0.02:
            return self._result(False, f"{label}: il volume aggiunto vale {ratio:.3f} volte quello del seme (non un numero intero): "
                                "alcune istanze sono parziali (escono dal corpo o cadono in una posizione diversa dal previsto).",
                                SwErrors.swFeatureError, data)
        if added is not None and expected is not None and added != expected:
            if added <= 0:
                self._delete_features(doc, [x["name"] for x in created])
                return self._result(False, f"{label}: nessuna istanza creata (attese {expected}): annullata.", SwErrors.swFeatureError, data)
            return self._result(False, f"{label}: istanze create {added}, attese {expected} (alcune cadono fuori dal corpo o "
                                "coincidono con il seme).", SwErrors.swFeatureError, data)
        return self._result(True, f"{label}: {name}, {added} istanze aggiunte (volume {dvol:+.2f} mm3)", SwErrors.swSuccess, data)

    # ------------------------------------------------------------------ curve_driven_pattern
    def curve_driven_pattern(self, features, curve, count: int, spacing: float = None, equal_spacing: bool = True,
                             reverse: bool = False, align: str = "tangent", offset_curve: bool = False,
                             unit: str = None) -> Dict:
        """Ripetizione di feature lungo una curva (schizzo, spigolo): `count` istanze (seme compreso) a distanza uguale lungo
        la curva (equal_spacing) oppure ogni `spacing` (misurata lungo la curva); allineamento 'tangent' (segue la curva)
        o 'seed' (come l'originale)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            if not features:
                return self._result(False, "Servono le feature da ripetere (nomi).", SwErrors.swInvalidInput)
            if int(count) < 2:
                return self._result(False, "count deve essere >= 2 (istanze totali, seme compreso).", SwErrors.swInvalidInput)
            if not equal_spacing and (spacing is None or float(spacing) <= 0):
                return self._result(False, "Con equal_spacing=false serve spacing > 0.", SwErrors.swInvalidInput)
            al = (align or "tangent").lower()
            if al not in ("tangent", "seed"):
                return self._result(False, "align deve essere tangent | seed", SwErrors.swInvalidInput)
            seed = self._seed_effect(doc, list(features))
            if abs(seed) < 1e-15:
                return self._result(False, "Le feature indicate non cambiano il volume: impossibile verificare le istanze.",
                                    SwErrors.swInvalidInput)
            v0 = self._volume_m3(doc)
            doc.ClearSelection2(True)
            ok, msg, _ = self._select_any(doc, curve, unit, append=False, mark=1)
            if not ok:
                return self._result(False, f"Curva: {msg}", SwErrors.swSelectionError)
            e = self._select_features_mark(doc, list(features), 4, append=True)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            sp = self._mmu(float(spacing), unit) if spacing is not None else 0.01       # con spacing 0 la chiamata si appende anche a distanza uguale
            before = self._names(doc)
            try:
                doc.FeatureCurvePattern(int(count), sp, 1, 0.0, bool(reverse), False, bool(equal_spacing), False, False,
                                        al == "seed", bool(offset_curve), False)
            except Exception as ex:
                return self._result(False, f"Ripetizione guidata da curva fallita: {ex}", SwErrors.swFeatureError)
            feat = None
            for n, t, f in self._features(doc):
                if n not in before and t == "CurvePattern":
                    feat = f
            extra = {"count": int(count), "equal_spacing": bool(equal_spacing), "spacing": spacing, "align": al,
                     "reverse": bool(reverse), "unit": self._unit_name(unit)}
            if feat is not None:
                extra["definition"] = self._bd2_read_pattern(doc, feat, ("D1InstanceCount", "D1Spacing", "D1IsEqualSpaced",
                                                                         "D1AlignmentMethod", "D1CurveMethod"))
            return self._bd2_pattern_done(doc, "Ripetizione guidata da curva", feat, v0, before, seed, int(count) - 1, extra)
        except Exception as e:
            logger.error(f"curve_driven_pattern: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ sketch_driven_pattern
    def sketch_driven_pattern(self, features, sketch: str, geometry_pattern: bool = False, unit: str = None) -> Dict:
        """Ripetizione di feature sui punti di uno schizzo: il baricentro del seme va su ogni punto dello schizzo."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            if not features:
                return self._result(False, "Servono le feature da ripetere (nomi).", SwErrors.swInvalidInput)
            sk = self._find_feature(doc, sketch)
            if sk is None or self._com(sk, "GetTypeName2") != "ProfileFeature":
                return self._result(False, f"Schizzo '{sketch}' non trovato.", SwErrors.swSelectionError)
            try:
                npts = len([p for p in (self._com(self._com(sk, "GetSpecificFeature2"), "GetSketchPoints2") or []) if p is not None])
            except Exception:
                npts = None
            seed = self._seed_effect(doc, list(features))
            if abs(seed) < 1e-15:
                return self._result(False, "Le feature indicate non cambiano il volume: impossibile verificare le istanze.",
                                    SwErrors.swInvalidInput)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            if not self._select_feature(doc, sketch, False, 1):
                return self._result(False, f"Schizzo '{sketch}' non selezionabile.", SwErrors.swSelectionError)
            e = self._select_features_mark(doc, list(features), 4, append=True)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            try:
                feat = doc.FeatureManager.FeatureSketchDrivenPattern(True, bool(geometry_pattern))
            except Exception as ex:
                return self._result(False, f"Ripetizione guidata da schizzo fallita: {ex}", SwErrors.swFeatureError)
            return self._bd2_pattern_done(doc, "Ripetizione guidata da schizzo", feat, v0, before,
                                          0.0 if geometry_pattern else seed, None if geometry_pattern else npts,
                                          {"sketch": sketch, "sketch_points": npts, "use_centroid": True,
                                           "geometry_pattern": bool(geometry_pattern)})
        except Exception as e:
            logger.error(f"sketch_driven_pattern: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    # ------------------------------------------------------------------ table_driven_pattern
    def table_driven_pattern(self, features, points, coordinate_system: str = None, origin=None, unit: str = None) -> Dict:
        """Ripetizione di feature su una tabella di punti [x, y] nel piano XY di un sistema di coordinate: il baricentro del seme
        va su ogni punto (la quota lungo Z del sistema resta quella del seme). Senza `coordinate_system` ne crea uno con gli
        assi del modello in `origin` (default l'origine)."""
        try:
            doc, err = self._part()
            if err:
                return err
            self._exit_sketch(doc)
            if not features:
                return self._result(False, "Servono le feature da ripetere (nomi).", SwErrors.swInvalidInput)
            if not isinstance(points, (list, tuple)) or not points:
                return self._result(False, "points deve essere una lista [[x,y],...].", SwErrors.swInvalidInput)
            pts = []
            for p in points:
                if not isinstance(p, (list, tuple)) or len(p) != 2:
                    return self._result(False, f"Punto non valido {p}: serve [x,y] (coordinate nel sistema di coordinate).",
                                        SwErrors.swInvalidInput)
                pts.extend([self._mmu(float(p[0]), unit), self._mmu(float(p[1]), unit)])
            created_cs = None
            if coordinate_system:
                if self._find_feature(doc, coordinate_system) is None:
                    return self._result(False, f"Sistema di coordinate '{coordinate_system}' non trovato.", SwErrors.swSelectionError)
                cs = coordinate_system
            else:
                r = self.create_coordinate_system(origin=list(origin) if origin is not None else [0, 0, 0],
                                                  rotation=[0, 0, 0], unit=unit)
                if not r.get("success"):
                    return self._result(False, f"Sistema di coordinate non creato: {r.get('message')}", SwErrors.swFeatureError)
                cs = r["data"]["feature"]
                created_cs = cs
            seed = self._seed_effect(doc, list(features))
            if abs(seed) < 1e-15:
                return self._result(False, "Le feature indicate non cambiano il volume: impossibile verificare le istanze.",
                                    SwErrors.swInvalidInput)
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            doc.ClearSelection2(True)
            # misurato: marche 16 = sistema di coordinate, 4 = feature da ripetere; i punti sono coppie piatte [x1,y1,x2,y2...] (m)
            if not self._select_feature(doc, cs, False, 16):
                return self._result(False, f"Sistema di coordinate '{cs}' non selezionabile.", SwErrors.swSelectionError)
            e = self._select_features_mark(doc, list(features), 4, append=True)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            arr = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, tuple(pts))
            try:
                feat = doc.FeatureManager.InsertTableDrivenPattern2("", arr, True, False, False)
            except Exception as ex:
                return self._result(False, f"Ripetizione guidata da tabella fallita: {ex}", SwErrors.swFeatureError)
            return self._bd2_pattern_done(doc, "Ripetizione guidata da tabella", feat, v0, before, seed, len(points),
                                          {"points": [list(map(float, p)) for p in points], "coordinate_system": cs,
                                           "coordinate_system_created": created_cs, "unit": self._unit_name(unit)})
        except Exception as e:
            logger.error(f"table_driven_pattern: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)
