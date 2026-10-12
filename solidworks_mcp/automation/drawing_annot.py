"""
Annotazioni di tavola (blocco 4): tabella fori e indicazione generale della rugosita'.
"""

import math
import logging
from typing import Dict, List, Optional, Tuple

import pythoncom

from ..constants import SwErrors

logger = logging.getLogger(__name__)

PUT = pythoncom.DISPATCH_PROPERTYPUT
TEXT_DISPID = 131108            # ITableAnnotation.Text(Row, Column)


class DrawingAnnotMixin:

    # ------------------------------------------------------------------ fori della vista
    def _an_holes(self, v) -> Tuple[List[Dict], Optional[Tuple[float, float]], float]:
        """Fori (cilindri concavi con asse perpendicolare alla vista): [{'cx','cy','r'}] (foglio, m, r del modello),
        origine del modello proiettata, scala vista."""
        m = v.ReferencedDocument
        if m is None or int(m.GetType) != 1:
            return [], None, 1.0
        proj, dirp, s = self._dm_proj(v)
        out: Dict[Tuple, Dict] = {}
        for b in (m.GetBodies2(0, True) or ()):
            for f in (b.GetFaces() or ()):
                try:
                    sf = f.GetSurface
                    if not sf.IsCylinder:
                        continue
                    cp = sf.CylinderParams
                    d = dirp(cp[3:6])
                    if abs(d[2]) < 0.95:
                        continue
                    if not bool(self._com(f, "FaceInSurfaceSense")):  # verificato: fori/alesaggi = True, perni = False
                        continue
                    po = proj(cp[0:3])
                    key = (round(po[0] / 0.0003), round(po[1] / 0.0003))
                    r = float(cp[6])
                    if key not in out or r < out[key]["r"]:        # foro con svasatura/lamatura: il diametro minimo
                        out[key] = {"cx": po[0], "cy": po[1], "r": r}
                except Exception as e:
                    logger.debug(f"hole face: {e}")
        o = proj((0.0, 0.0, 0.0))
        return list(out.values()), (o[0], o[1]), s

    def add_hole_table(self, view: str = None, x: float = None, y: float = None, tags: bool = True,
                       unit: str = None) -> Dict:
        """Tabella fori della vista (cerchi visibili): TAG, X, Y (mm dall'origine del modello, nel verso
        del foglio) e diametro. Con tags=True ogni foro riceve l'etichetta (A1, A2, ... per diametro) accanto al cerchio.
        La tabella e' collocata in un'area libera del foglio (o in x, y = angolo in alto a sinistra)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            v, err = self._find_view(doc, view)
            if err:
                return err
            holes, org, s = self._an_holes(v)
            if not holes:
                return self._result(False, "Nessun foro circolare (cilindro concavo) visibile in questa vista",
                                    SwErrors.swInvalidInput)
            # etichette per diametro: A, B, C... (A1, A2 ... in ordine di posizione)
            dias = sorted({round(2 * h["r"] * 1000.0, 3) for h in holes})
            rows = []
            for k, dv in enumerate(dias):
                letter = chr(ord("A") + k)
                grp = [h for h in holes if abs(round(2 * h["r"] * 1000.0, 3) - dv) < 1e-6]
                grp.sort(key=lambda h: (-round(h["cy"] / 0.001), h["cx"]))
                for n, h in enumerate(grp, start=1):
                    h["tag"] = f"{letter}{n}"
                    rows.append(h)
            if len(rows) > 40:
                return self._result(False, f"Troppi fori ({len(rows)}) per una tabella", SwErrors.swInvalidInput)
            # tabella verticale (un foro per riga) o orizzontale (un foro per colonna): vince quella che trova posto
            RH = 0.006
            cells_v = [["TAG", "X", "Y", "\u00d8"]] + [
                [h["tag"], f"{(h['cx'] - org[0]) / s * 1000.0:.2f}", f"{(h['cy'] - org[1]) / s * 1000.0:.2f}",
                 f"{2 * h['r'] * 1000.0:.2f}"] for h in rows]
            cells_h = [list(c) for c in zip(*cells_v)]
            wv = [0.013, 0.021, 0.021, 0.019]
            wh = [0.012] + [0.0185] * len(rows)
            layouts = [(cells_v, wv), (cells_h, wh)] if len(rows) <= 6 else [(cells_h, wh), (cells_v, wv)]
            sw_, sh_ = self._sheet_dims(doc)[:2]
            chosen, spot = None, None
            if x is not None and y is not None:
                chosen = layouts[0]
                tx, ty = self._m(x, unit), self._m(y, unit)
            else:
                for cells, widths in layouts:
                    tw_, th_ = sum(widths), RH * len(cells)
                    spot = self._an_free_spot(doc, tw_ + 0.008, th_ + 0.008, (0.5 * sw_, sh_ - 0.04 - th_ / 2))
                    if spot:
                        chosen = (cells, widths)
                        tx, ty = spot[0] - tw_ / 2, spot[1] + th_ / 2
                        break
                if chosen is None:
                    return self._result(False, "Nessuna area libera abbastanza grande per la tabella fori "
                                        "(usa un foglio piu' grande o indica x, y)", SwErrors.swInvalidInput)
            cells, widths = chosen
            nrows, ncols = len(cells), len(widths)
            t = doc.Extension.InsertGeneralTableAnnotation(False, tx, ty, 1, "", nrows, ncols)
            if t is None:
                return self._result(False, "Tabella non creata", SwErrors.swUnknownError)
            for r_, line in enumerate(cells):
                for c_, txt in enumerate(line):
                    t._oleobj_.Invoke(TEXT_DISPID, 0, PUT, 0, r_, c_, txt)
            for c_, w_ in enumerate(widths):
                t.SetColumnWidth(c_, w_, 0)
            for r_ in range(nrows):
                t.SetRowHeight(r_, RH, 0)
            tw, th = sum(widths), RH * nrows
            t.GetAnnotation.SetPosition2(tx, ty, 0)
            made_tags = 0
            if tags and len(rows) <= 16:
                made_tags = self._an_place_tags(doc, v, rows, org, s)
            doc.ClearSelection2(True)
            return self._result(True, f"Tabella fori: {len(rows)} fori, {len(dias)} diametri",
                                SwErrors.swSuccess,
                                {"rows": [{"tag": h["tag"], "x_mm": round((h["cx"] - org[0]) / s * 1000.0, 3),
                                           "y_mm": round((h["cy"] - org[1]) / s * 1000.0, 3),
                                           "diameter_mm": round(2 * h["r"] * 1000.0, 3)} for h in rows],
                                 "tags_placed": made_tags, "tags_clearance_mm": getattr(self, "_tags_clearance_mm", None),
                                 "table_rect_mm": [round(tx * 1000, 1), round((ty - th) * 1000, 1),
                                                   round((tx + tw) * 1000, 1), round(ty * 1000, 1)]})
        except Exception as e:
            return self._fail("add_hole_table", e)




    def _an_retag(self, doc) -> int:
        """Riposiziona le etichette dei fori gia' inserite (dopo che quote/viste nuove hanno occupato altro spazio)."""
        st = getattr(self, "_tag_state", {}).get(self._get_doc_title(doc))
        if not st or not st["notes"]:
            return 0
        try:
            v, err = self._find_view(doc, st["view"])
            if err:
                return 0
            self._sheet_ann_cache = None
            return self._an_place_tags(doc, v, st["rows"], st["org"], st["s"], notes=st["notes"])
        except Exception as e:
            logger.debug(f"retag: {e}")
            return 0

    def _an_geom_obstacles(self, v) -> Tuple[List[Tuple], List[Tuple]]:
        """Segmenti (x0,y0,x1,y1) e cerchi (cx,cy,r) in coordinate foglio (m) di tutti gli spigoli del pezzo proiettati sulla vista
        (visibili o no: e' un controllo prudenziale per non appoggiare etichette sulle linee del disegno)."""
        segs, circs = [], []
        m = v.ReferencedDocument
        if m is None or int(m.GetType) != 1:
            return segs, circs
        proj, dirp, sc = self._dm_proj(v)
        for b in (m.GetBodies2(0, True) or ()):
            for e in (b.GetEdges() or ()):
                try:
                    cv = e.GetCurve
                    if cv is None:
                        continue
                    if cv.IsLine:
                        a = e.GetStartVertex.GetPoint
                        c = e.GetEndVertex.GetPoint
                        p1, p2 = proj(a), proj(c)
                        segs.append((p1[0], p1[1], p2[0], p2[1]))
                    elif cv.IsCircle:
                        cp = cv.CircleParams
                        d = dirp(cp[3:6])
                        if abs(d[2]) > 0.95:
                            po = proj(cp[0:3])
                            circs.append((po[0], po[1], float(cp[6]) * sc))
                except Exception as ex:
                    logger.debug(f"edge obstacle: {ex}")
        return segs, circs

    @staticmethod
    def _seg_hits_rect(sg, r) -> bool:
        """Il segmento (x0,y0,x1,y1) interseca il rettangolo r (Liang-Barsky)."""
        x0, y0, x1, y1 = sg
        dx, dy = x1 - x0, y1 - y0
        t0, t1 = 0.0, 1.0
        for p_, q_ in ((-dx, x0 - r[0]), (dx, r[2] - x0), (-dy, y0 - r[1]), (dy, r[3] - y0)):
            if abs(p_) < 1e-12:
                if q_ < 0:
                    return False
            else:
                t = q_ / p_
                if p_ < 0:
                    if t > t1:
                        return False
                    t0 = max(t0, t)
                else:
                    if t < t0:
                        return False
                    t1 = min(t1, t)
        return t0 <= t1

    def _an_place_tags(self, doc, v, rows, org, s, notes=None) -> int:
        """(A5) Etichette dei fori (A1...) accanto al cerchio SENZA toccare simboli di foro, assi, altri fori, quote ed etichette.
        Per ogni foro si provano posizioni sulle diagonali (gli assi del centro sono orizzontali/verticali) a distanza
        crescente, con controllo di collisione contro: dischi di tutti i fori (raggio + prolungamento dell'asse), etichette gia' messe,
        riquadri delle altre annotazioni, contorno utile del foglio."""
        from .drawing_layout import _inter
        core = self._dm_core(v)
        cc = ((core[0] + core[2]) / 2.0, (core[1] + core[3]) / 2.0) if core else org
        ext = 0.0032                                # prolungamento dell'asse oltre il cerchio
        segs, circs = self._an_geom_obstacles(v)
        disks = [(h["cx"], h["cy"], h["r"] * s + ext) for h in rows]
        rings = [(cx_, cy_, r_) for cx_, cy_, r_ in circs if not any(abs(cx_ - d_[0]) < 3e-4 and abs(cy_ - d_[1]) < 3e-4 and r_ <= d_[2] + 1e-4 for d_ in disks)]
        for dv_, dcx, dcy, dr in getattr(self, "_detail_circles", {}).get(self._get_doc_title(doc), []):
            if dv_ == self._com(v, "GetName2"):
                rings.append((dcx, dcy, dr))
        boxes = []
        segs = list(segs)
        try:
            mytags = {h["tag"] for h in rows} if notes else set()
            for a in self._dq_annotations(doc):
                if a["kind"] == "note" and str(a.get("text", "")).strip() in mytags:
                    continue            # le mie etichette (riposizionamento)
                r_ = a.get("trect") if (a["kind"] == "dimension" and a.get("dim_kind") in ("dia", "rad", "ang") and a.get("trect")) else a["rect"]
                boxes.append(tuple(r_))
                if a["kind"] == "dimension" and a.get("lines"):
                    segs = segs + [tuple(l) for l in a["lines"]]
        except Exception as e:
            logger.debug(f"tags obstacles: {e}")
        use = self._dq_usable(doc)
        placed, made, clear = [], 0, []
        notes = notes if notes is not None else {}
        for h in rows:
            tw = self._dq_text_w(h["tag"], 0.0035) + 0.0012
            th = 0.0046
            rs = h["r"] * s
            ux, uy = h["cx"] - cc[0], h["cy"] - cc[1]
            base = math.degrees(math.atan2(uy, ux)) if math.hypot(ux, uy) > 1e-6 else 45.0
            diag = sorted((45, 135, 225, 315), key=lambda a: abs((a - base + 180) % 360 - 180)) +                 sorted((0, 90, 180, 270, 20, 70, 110, 160, 200, 250, 290, 340), key=lambda a: abs((a - base + 180) % 360 - 180))
            best = None
            for dist in (rs + ext + 0.0012, rs + ext + 0.004, rs + ext + 0.008, rs + ext + 0.014):
                for ang in diag:
                    c_, s_ = math.cos(math.radians(ang)), math.sin(math.radians(ang))
                    # centro dell'etichetta: punto sulla diagonale + meta' del riquadro verso l'esterno
                    tx = h["cx"] + c_ * dist + (tw / 2.0) * (1 if c_ > 0 else -1)
                    ty = h["cy"] + s_ * dist + (th / 2.0) * (1 if s_ > 0 else -1)
                    box = (tx - tw / 2.0, ty - th / 2.0, tx + tw / 2.0, ty + th / 2.0)
                    bad = box[0] < use[0] or box[2] > use[2] or box[1] < use[1] or box[3] > use[3]
                    for (dx_, dy_, rr) in disks:      # disco contro rettangolo
                        nx = min(max(dx_, box[0]), box[2])
                        ny = min(max(dy_, box[1]), box[3])
                        if math.hypot(nx - dx_, ny - dy_) < rr:
                            bad = True
                            break
                    if not bad:
                        for (rx_, ry_, rr_) in rings:        # cerchio: conta la circonferenza (con un po' di margine), non il disco
                            nx = min(max(rx_, box[0]), box[2])
                            ny = min(max(ry_, box[1]), box[3])
                            dmin = math.hypot(nx - rx_, ny - ry_)
                            dmax = max(math.hypot(px_ - rx_, py_ - ry_) for px_ in (box[0], box[2]) for py_ in (box[1], box[3]))
                            if dmin < rr_ + 0.0008 and dmax > rr_ - 0.0008:
                                bad = True
                                break
                    if not bad:
                        bad = any(_inter(box, q, 1e-4) for q in placed + boxes)
                    if not bad:
                        gb = (box[0] - 0.0008, box[1] - 0.0008, box[2] + 0.0008, box[3] + 0.0008)
                        bad = any(self._seg_hits_rect(sg, gb) for sg in segs)
                    if not bad:
                        best = box
                        break
                if best:
                    break
            if best is None:
                continue
            placed.append(best)
            for (dx_, dy_, rr) in [(h2["cx"], h2["cy"], h2["r"] * s + ext) for h2 in rows]:
                nx = min(max(dx_, best[0]), best[2])
                ny = min(max(dy_, best[1]), best[3])
                clear.append(math.hypot(nx - dx_, ny - dy_) - rr)
            try:
                note = notes.get(h["tag"])
                if note is None:
                    note = doc.InsertNote(h["tag"])
                if note is not None:
                    note.GetAnnotation.SetPosition2(best[0], best[3], 0)     # il punto e' l'angolo in alto a sinistra del testo
                    notes[h["tag"]] = note
                    made += 1
            except Exception as e:
                logger.debug(f"tag note: {e}")
        self._sheet_ann_cache = None
        if not hasattr(self, "_tag_state"):
            self._tag_state = {}
        self._tag_state[self._get_doc_title(doc)] = {"view": self._com(v, "GetName2"), "rows": rows, "org": org, "s": s, "notes": notes}
        self._tags_clearance_mm = round(min(clear) * 1000.0, 2) if clear else None     # >= 0: nessuna etichetta tocca un simbolo di foro
        return made


    # ------------------------------------------------------------------ aggancio di tolleranze/riferimenti (A2)
    def _an_find_dim(self, doc, dimension: str, view: str = None):
        """(IDisplayDimension, IDimension, vista) di una quota data per nome (D1@..., RD2@Vista...), testo o valore."""
        vs = self._sheet_views(doc)
        if view:
            v0, err = self._find_view(doc, view)
            if err:
                return None
            vs = [v0]
        q = str(dimension).strip()
        cand = []
        for v in vs:
            for dd in self._display_dims(v):
                dim = dd.GetDimension2(0)
                full, name = dim.FullName, dim.Name
                txt = ""
                try:
                    d2 = dd.GetDisplayData
                    txt = " ".join(str(d2.GetTextAtIndex(i)).strip() for i in range(int(self._com(d2, "GetTextCount"))))
                except Exception:
                    pass
                if q == full or q == name or q.lower() == full.lower() or q == str(dd.GetNameForSelection):
                    cand.insert(0, (dd, dim, v))
                elif q.replace(".", ",") in txt.replace("<MOD-DIAM>", "").split() or q in txt.split():
                    cand.append((dd, dim, v))
                else:
                    try:
                        if abs(float(q.replace(",", ".")) - float(dim.Value)) < 1e-9:
                            cand.append((dd, dim, v))
                    except Exception:
                        pass
        return cand[0] if cand else None

    def _an_model_point_to_sheet(self, doc, view: str, model_point, unit: str = None):
        """Punto del modello (x, y, z nell'unita' `unit`, default mm) -> coordinate foglio (m) della vista."""
        v, err = self._find_view(doc, view)
        if err:
            return None, None
        proj, _, _ = self._dm_proj(v)
        q = proj(tuple(self._m(float(c), unit) for c in model_point))
        return (q[0], q[1]), v

    def _an_place_near(self, doc, w: float, h: float, target, kind: str = "edge", away_from=None, exclude_rect=None):
        """Posto libero (angolo in alto a sinistra) per un riquadro w x h VICINO al bersaglio: accanto al testo di una quota
        (kind='dimension', target = riquadro del testo) o fuori dal contorno, vicino a un punto di spigolo (kind='edge',
        target = (x, y), away_from = centro della vista). Evita viste, quote, note, tabelle, cartiglio."""
        from .drawing_layout import _inter
        occ = list(self._occupied(doc, None))
        if exclude_rect is not None:
            er = exclude_rect

            def area(r):
                return max(r[2] - r[0], 0.0) * max(r[3] - r[1], 0.0)
            keep = []
            for r in occ:
                ix = min(r[2], er[2]) - max(r[0], er[0])
                iy = min(r[3], er[3]) - max(r[1], er[1])
                if ix > 0 and iy > 0 and ix * iy > 0.5 * min(area(r), area(er)) and area(r) < 40 * area(er):
                    continue
                keep.append(r)
            occ = keep
        use = self._dq_usable(doc)
        boxes = []
        if kind == "dimension":
            tr = target
            cx, cy = (tr[0] + tr[2]) / 2.0, (tr[1] + tr[3]) / 2.0
            gap = 0.0025
            boxes = [(tr[2] + gap, cy - h / 2.0), (tr[0] - gap - w, cy - h / 2.0), (cx - w / 2.0, tr[3] + gap), (cx - w / 2.0, tr[1] - gap - h)]
            boxes = [(x0, y0, x0 + w, y0 + h) for x0, y0 in boxes]
        else:
            px, py = target
            ax, ay = away_from if away_from else (px, py - 1.0)
            base = math.degrees(math.atan2(py - ay, px - ax))
            for d in (0.012, 0.02, 0.03, 0.045, 0.065):
                for da in (0, 25, -25, 50, -50, 80, -80, 120, -120, 180):
                    a_ = math.radians(base + da)
                    ux, uy = math.cos(a_), math.sin(a_)
                    dc = d + 0.5 * (abs(ux) * w + abs(uy) * h)
                    cx, cy = px + ux * dc, py + uy * dc
                    boxes.append((cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0))
        # testi delle quote: la linea di richiamo (bersaglio -> riquadro) non deve attraversarli
        texts = []
        if kind == "edge":
            try:
                for a_ in self._dq_annotations(doc):
                    if a_["kind"] == "dimension" and a_.get("trect"):
                        t_ = a_["trect"]
                        texts.append((t_[0] - 0.001, t_[1] - 0.001, t_[2] + 0.001, t_[3] + 0.001))
            except Exception as e:
                logger.debug(f"place_near texts: {e}")

        def leader_ok(b):
            if not texts:
                return True
            bx, by = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
            return not any(self._seg_hits_rect((target[0], target[1], bx, by), t_) for t_ in texts)
        fallback = None
        for b in boxes:
            if b[0] < use[0] or b[2] > use[2] or b[1] < use[1] or b[3] > use[3]:
                continue
            if any(_inter(b, o, 0.0015) for o in occ):
                continue
            if kind == "edge" and not leader_ok(b):
                fallback = fallback or b
                continue
            return b[0], b[3]
        if fallback:
            return fallback[0], fallback[3]
        if kind == "dimension":
            # niente posto accanto al testo (le quote sono impilate a 8 mm): un posto libero piu' lontano, outward rispetto alla vista;
            # SolidWorks collega il riquadro alla quota con una linea di richiamo
            tr = target
            ctr = ((tr[0] + tr[2]) / 2.0, (tr[1] + tr[3]) / 2.0)
            best_v, best_d = None, 1e9
            for v_ in self._sheet_views(doc):
                r_ = self._view_rect(v_)
                c_ = ((r_[0] + r_[2]) / 2.0, (r_[1] + r_[3]) / 2.0)
                d_ = math.hypot(c_[0] - ctr[0], c_[1] - ctr[1])
                if d_ < best_d:
                    best_v, best_d = c_, d_
            return self._an_place_near(doc, w, h, ctr, "edge", best_v, exclude_rect)
        return None

    @staticmethod
    def _an_frame_size(frames) -> Tuple[float, float]:
        """Misura analitica (m) di un riquadro di tolleranza geometrica: 7 mm per riga; celle: simbolo 7 mm + valore + 7 mm per riferimento."""
        w_, h_ = 0.0, 0.007 * len(frames)
        for f in frames:
            refs_n = len([r for r in (f.get("datum_refs") or []) if r])
            vw = 0.0023 * len(str(f.get("tolerance", ""))) + 0.006 + (0.0045 if f.get("diameter") else 0.0) \
                + (0.006 if f.get("material_condition") else 0.0)
            w_ = max(w_, 0.007 + vw + 0.007 * refs_n)
        return w_, h_

    # ------------------------------------------------------------------ rugosita' generale
    # simbolo di finitura SolidWorks (stile ISO): geometria relativa alla punta (m); testo Ra nello slot 2 a (7, 10) mm
    _SF_L, _SF_R, _SF_H = -0.00295, 0.0059, 0.010

    def add_general_roughness(self, value: str = "6.3", x: float = None, y: float = None, unit: str = None) -> Dict:
        """Indicazione generale della rugosita' secondo ISO 1302: simbolo di lavorazione con 'Ra x' e, fra parentesi, il simbolo
        base (V senza valori) = "tutte le altre superfici come indicato". Si compone con misure vere: le parentesi (testo alto
        quanto il simbolo) sono centrate in verticale sul simbolo e a 1,5 mm dai suoi lati. In alto a destra del foglio (o con
        la punta del simbolo principale in x, y). Le superfici con una rugosita' diversa vanno indicate con add_surface_finish."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            W, H, _ = self._sheet_dims(doc)
            val = str(value).replace(".", ",")
            txt = f"Ra {val}"
            L, R, SH = self._SF_L, self._SF_R, self._SF_H
            w_text = 0.00232 * len(txt)
            main_r = 0.007 + w_text + 0.002          # estremo destro del simbolo principale (dalla punta)
            par_h = 0.008
            par_w = 0.0039
            gap = 0.0015
            total = (-L) + main_r + 0.004 + par_w + gap + (R - L) + gap + par_w
            if x is not None and y is not None:
                tx, ty = self._m(x, unit), self._m(y, unit)
            else:
                spot = self._an_free_spot(doc, total + 0.008, SH + 0.012, (W - 0.03 - total / 2, H - 0.04))
                if spot is None:
                    return self._result(False, "Nessuna area libera per l'indicazione generale della rugosita'",
                                        SwErrors.swInvalidInput)
                tx, ty = spot[0] - total / 2 - L, spot[1] - SH / 2 - 0.002
            # 1) simbolo principale con il valore (slot 2 = testo sopra la barra)
            main = doc.Extension.InsertSurfaceFinishSymbol3(1, 0, tx, ty, 0, 0, 0, "", "", "", "", "", "", "")
            if main is None:
                return self._result(False, "Simbolo principale non creato", SwErrors.swUnknownError)
            main.SetText(2, txt)
            main.GetAnnotation.SetPosition2(tx, ty, 0)
            doc.ClearSelection2(True)
            cy = ty + SH / 2.0

            def paren(ch: str, left: float):
                """Nota ( o ) con il bordo sinistro in `left` e il centro verticale in cy (misurati con GetExtent)."""
                n = doc.CreateText2(ch, left, cy + 0.005, 0, par_h, 0)
                if n is None:
                    return None
                ex = [float(t) for t in n.GetExtent]
                ann = n.GetAnnotation
                pos = [float(t) for t in ann.GetPosition]
                ann.SetPosition2(pos[0] + (left - ex[0]), pos[1] + (cy - (ex[1] + ex[4]) / 2.0), 0)
                ex = [float(t) for t in n.GetExtent]
                return (ex[0], ex[1], ex[3], ex[4])

            p1 = paren("(", tx + main_r + 0.004)
            if p1 is None:
                return self._result(False, "Parentesi non creata", SwErrors.swUnknownError)
            btx = p1[2] + gap - L
            basic = doc.Extension.InsertSurfaceFinishSymbol3(0, 0, btx, ty, 0, 0, 0, "", "", "", "", "", "", "")
            if basic is not None:
                basic.GetAnnotation.SetPosition2(btx, ty, 0)
            doc.ClearSelection2(True)
            p2 = paren(")", btx + R + gap)
            doc.ClearSelection2(True)
            rects = {"main_symbol": [tx + L, ty, tx + main_r, ty + SH + 0.004], "paren_open": list(p1),
                     "basic_symbol": [btx + L, ty, btx + R, ty + SH], "paren_close": list(p2) if p2 else None}
            return self._result(True, f"Rugosita' generale Ra {val} inserita (ISO 1302)", SwErrors.swSuccess,
                                {"x_mm": round(tx * 1000, 1), "y_mm": round(ty * 1000, 1), "symbol": basic is not None,
                                 "rects_mm": {k: [round(t * 1000, 2) for t in v] for k, v in rects.items() if v},
                                 "symbol_center_y_mm": round(cy * 1000, 2)})
        except Exception as e:
            return self._fail("add_general_roughness", e)

    @staticmethod
    def _rect_hit(a, b) -> bool:
        return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])

    def _an_obstacles(self, doc) -> List[Tuple[float, float, float, float]]:
        """Viste, cartiglio, zone riservate e riquadri di tutte le annotazioni gia' presenti (_occupied le include)."""
        return list(self._occupied(doc, None))

    def _an_free_spot(self, doc, w: float, h: float, near: Tuple[float, float], gap: float = 0.006,
                      step: float = 0.005, obstacles=None) -> Optional[Tuple[float, float]]:
        from .drawing_layout import _inter
        W, H, _ = self._sheet_dims(doc)
        occ = self._an_obstacles(doc) if obstacles is None else obstacles
        x0, x1, y0, y1 = 0.03, W - 0.03, 0.03, H - 0.03
        best, best_d = None, 1e9
        y = y0 + h / 2
        while y <= y1 - h / 2 + 1e-9:
            x = x0 + w / 2
            while x <= x1 - w / 2 + 1e-9:
                cand = (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
                if not any(_inter(cand, o, gap) for o in occ):
                    d = (x - near[0]) ** 2 + (y - near[1]) ** 2
                    if d < best_d:
                        best, best_d = (x, y), d
                x += step
            y += step
        return best

    def _dq_chamfer_note(self, doc, labels: List[str]) -> bool:
        """Le quote di smusso tolte dalle viste diventano una nota 'SMUSSI NON QUOTATI: 1x45, ...' in area libera."""
        labels = sorted(set(l.replace("\u00b0", "") for l in labels))
        if not labels:
            return False
        text = "SMUSSI NON QUOTATI: " + ", ".join(labels).replace(".", ",")
        for a in self._dq_annotations(doc):
            if a["kind"] == "note" and str(a.get("text", "")).startswith("SMUSSI NON QUOTATI"):
                return False
        W, H, _ = self._sheet_dims(doc)
        w_est = self._dq_text_w(text, 0.0035) + 0.004
        spot = self._an_free_spot(doc, w_est + 0.006, 0.012, (0.04 + w_est / 2, 0.045))
        if spot is None:
            return False
        note = doc.InsertNote(text)
        if note is None:
            return False
        note.GetAnnotation.SetPosition2(spot[0] - w_est / 2, spot[1] - 0.003, 0)
        doc.ClearSelection2(True)
        return True
