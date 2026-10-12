"""
Sketch constraints & extra sketch entities (mixin)
--------------------------------------------------
Quote vere del modello (appaiono con insert_model_dimensions), relazioni geometriche, stato dello schizzo,
linea di costruzione, asse, spline, slot, ellisse, raccordo, offset, converti entita', specchia, testo.

Identificativi delle entita' dello schizzo (restituiti dai tool draw_*):
    segmento  "S<tipo>-<a>-<b>"  (tipo: 0 linea, 1 arco/cerchio, 2 ellisse, 3 spline, 4 testo)
    punto     "P<a>-<b>"
    "origin"  origine
    parti     "S1-0-1:center" | ":start" | ":end"
    per coordinate (nel piano dello schizzo, unita' `unit`): "@x,y" = segmento piu' vicino,
                                                              "pt@x,y" = punto piu' vicino

Trappole: GetID e' (indice_nel_tipo, id) -> NON unico fra tipi, per questo nell'id c'e' anche il tipo.
SelectByID2 su SKETCHSEGMENT fallisce spesso -> si seleziona con ISketchSegment.Select4 dopo ricerca geometrica.
"""

import math
import logging
import traceback
from typing import Optional, Dict, List, Tuple, Any

import win32com.client
import pythoncom

from ..constants import SwErrors
from .modeling_base import null_variant, r8_array

logger = logging.getLogger(__name__)

STATUS_NAMES = {1: "sconosciuto", 2: "sottodefinito", 3: "completamente definito", 4: "sovradefinito",
                5: "nessuna soluzione", 6: "soluzione non valida", 7: "risoluzione automatica disattivata"}
SEG_TYPES = {0: "line", 1: "arc", 2: "ellipse", 3: "spline", 4: "text", 5: "parabola"}

RELATIONS = {
    "horizontal": "sgHORIZONTAL2D", "orizzontale": "sgHORIZONTAL2D",
    "vertical": "sgVERTICAL2D", "verticale": "sgVERTICAL2D",
    "coincident": "sgCOINCIDENT", "coincidente": "sgCOINCIDENT",
    "tangent": "sgTANGENT", "tangente": "sgTANGENT",
    "concentric": "sgCONCENTRIC", "concentrico": "sgCONCENTRIC",
    "equal": "sgSAMELENGTH", "uguale": "sgSAMELENGTH",
    "parallel": "sgPARALLEL", "parallelo": "sgPARALLEL",
    "perpendicular": "sgPERPENDICULAR", "perpendicolare": "sgPERPENDICULAR",
    "symmetric": "sgSYMMETRIC", "simmetrico": "sgSYMMETRIC",
    "fixed": "sgFIXED", "fisso": "sgFIXED",
    "collinear": "sgCOLINEAR", "collineare": "sgCOLINEAR",
    "midpoint": "sgMIDPOINT", "punto_medio": "sgMIDPOINT",
    "horizontal_points": "sgHORIZONTALPOINTS2D", "vertical_points": "sgVERTICALPOINTS2D",
    "on_curve": "sgCOINCIDENT", "merge": "sgMERGEPOINTS",
}


class SketchConstraintOperations:
    """Mixin: richiede ModelingBase (_part, _mm, _sd, _com, ...)."""

    # ------------------------------------------------------------------ id e ricerca
    @staticmethod
    def _seg_id(seg) -> str:
        t = int(seg.GetType)
        a, b = seg.GetID
        return f"S{t}-{a}-{b}"

    @staticmethod
    def _pt_id(pt) -> str:
        a, b = pt.GetID
        return f"P{a}-{b}"

    def _active_sketch(self, doc, sketch_name: Optional[str] = None):
        """ISketch attivo; se sketch_name e' dato e non e' quello attivo, lo si apre in modifica."""
        sm = doc.SketchManager
        sk = self._com(sm, "ActiveSketch")
        if sketch_name:
            cur = None
            if sk is not None:
                # nome dello schizzo attivo: lo si ricava confrontando i segmenti con quelli della feature
                cur = self._active_sketch_name(doc, sk)
            if cur != sketch_name:
                if sk is not None:
                    self._exit_sketch(doc)
                doc.ClearSelection2(True)
                if not self._select_feature(doc, sketch_name):
                    return None, self._result(False, f"Schizzo '{sketch_name}' non trovato.",
                                              SwErrors.swSelectionError)
                doc.EditSketch()
                sk = self._com(sm, "ActiveSketch")
        if sk is None:
            return None, self._result(False, "Nessuno schizzo attivo: usa create_sketch (o passa sketch=<nome>).",
                                      SwErrors.swSketchError)
        return sk, None

    def _active_sketch_name(self, doc, sk=None) -> Optional[str]:
        """Nome dello schizzo attivo: confronto d'identita' COM fra ISketch attivo e quello di ogni feature."""
        sk = sk or self._com(doc.SketchManager, "ActiveSketch")
        if sk is None:
            return None
        for n, t, f in self._features(doc):
            if t != "ProfileFeature":
                continue
            try:
                if self._com(f, "GetSpecificFeature2") == sk:
                    return n
            except Exception:
                continue
        return self._last_of_type(doc, "ProfileFeature")

    def _segments(self, sk) -> list:
        return list(self._com(sk, "GetSketchSegments") or [])

    def _points(self, sk) -> list:
        return list(self._com(sk, "GetSketchPoints2") or [])

    def _seg_distance(self, seg, x: float, y: float) -> float:
        """Distanza (m) fra (x,y) e il segmento (campionamento per archi/spline, esatta per linee)."""
        t = int(seg.GetType)
        try:
            a, b = seg.GetStartPoint2, seg.GetEndPoint2
        except Exception:
            return 1e9
        if t == 0:
            ax, ay, bx, by = a.X, a.Y, b.X, b.Y
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
            return math.hypot(x - (ax + u * dx), y - (ay + u * dy))
        try:
            cv = self._com(seg, "GetCurve")
            # campiona la curva in modo uniforme sul parametro
            p = cv.Evaluate2(0.0, 0)
        except Exception:
            p = None
        if t == 1:
            try:
                c = seg.GetCenterPoint2
                r = math.hypot(a.X - c.X, a.Y - c.Y)
                ang = math.atan2(y - c.Y, x - c.X)
                d_circle = abs(math.hypot(x - c.X, y - c.Y) - r)
                if self._com(seg, "IsCircle"):
                    return d_circle
                # arco: la proiezione deve cadere nell'arco, altrimenti distanza dagli estremi
                a0 = math.atan2(a.Y - c.Y, a.X - c.X)
                a1 = math.atan2(b.Y - c.Y, b.X - c.X)
                ccw = int(seg.GetRotationDir) == 1 if hasattr(seg, "GetRotationDir") else True
                def inside(an):
                    s, e = (a0, a1) if ccw else (a1, a0)
                    return ((an - s) % (2 * math.pi)) <= ((e - s) % (2 * math.pi)) + 1e-12
                if inside(ang):
                    return d_circle
                return min(math.hypot(x - a.X, y - a.Y), math.hypot(x - b.X, y - b.Y))
            except Exception:
                pass
        # ellisse / spline / altro: distanza dai punti noti (estremi, centro)
        pts = [(a.X, a.Y), (b.X, b.Y)]
        try:
            c = seg.GetCenterPoint2
            pts.append((c.X, c.Y))
        except Exception:
            pass
        return min(math.hypot(x - px, y - py) for px, py in pts)

    def _find_by_id(self, sk, ent_id: str):
        for s in self._segments(sk):
            if self._seg_id(s) == ent_id:
                return s
        return None

    def _resolve_entity(self, doc, sk, ref, unit=None):
        """-> (oggetto_selezionabile, descrizione, errore|None). oggetto: ISketchSegment o ISketchPoint."""
        if ref is None:
            return None, "", "entita' mancante"
        if isinstance(ref, dict):
            ref = ref.get("id") or ref.get("ref")
        if isinstance(ref, (list, tuple)) and len(ref) == 2:
            ref = "@%s,%s" % (ref[0], ref[1])
        ref = str(ref).strip()
        low = ref.lower()
        if low == "origin" or low == "origine":
            return "origin", "origine", None
        if low.startswith("pt@") or low.startswith("@"):
            point = low.startswith("pt@")
            try:
                xs, ys = ref.split("@", 1)[1].split(",")
                x, y = self._mmu(float(xs), unit), self._mmu(float(ys), unit)
            except Exception:
                return None, "", f"coordinate non valide in '{ref}' (atteso @x,y)"
            if point:
                best, bd = None, 1e9
                for p in self._points(sk):
                    d = math.hypot(p.X - x, p.Y - y)
                    if d < bd:
                        best, bd = p, d
                if best is None or bd > 0.0005:
                    if abs(x) < 1e-6 and abs(y) < 1e-6:
                        return "origin", "origine", None
                    return None, "", f"nessun punto dello schizzo vicino a ({xs},{ys}) (piu' vicino {bd * 1000:.2f} mm)"
                return best, self._pt_id(best), None
            best, bd = None, 1e9
            for s in self._segments(sk):
                d = self._seg_distance(s, x, y)
                if d < bd:
                    best, bd = s, d
            if best is None or bd > 0.001:
                return None, "", f"nessun segmento vicino a ({xs},{ys}) (piu' vicino {bd * 1000:.2f} mm)"
            return best, self._seg_id(best), None
        part = None
        if ":" in ref:
            ref, part = ref.split(":", 1)
            part = part.lower()
        if ref[0] in "Pp" and ref[1:2].isdigit():
            for p in self._points(sk):
                if self._pt_id(p).lower() == ref.lower():
                    return p, self._pt_id(p), None
            return None, "", f"punto '{ref}' non trovato"
        seg = self._find_by_id(sk, ref.upper() if ref[0] in "sS" else ref)
        if seg is None:
            return None, "", f"segmento '{ref}' non trovato nello schizzo"
        if part in ("start", "inizio"):
            return seg.GetStartPoint2, f"{ref}:start", None
        if part in ("end", "fine"):
            return seg.GetEndPoint2, f"{ref}:end", None
        if part in ("center", "centro"):
            try:
                return seg.GetCenterPoint2, f"{ref}:center", None
            except Exception:
                return None, "", f"'{ref}' non ha un centro"
        return seg, ref, None

    def _select_ref(self, doc, sk, ref, append: bool, unit=None, mark: int = 0) -> Tuple[bool, str]:
        obj, desc, e = self._resolve_entity(doc, sk, ref, unit)
        if e:
            return False, e
        if obj == "origin":
            ok = doc.Extension.SelectByID2("", "EXTSKETCHPOINT", 0, 0, 0, append, mark, null_variant(), 0)
            for name in ("Punto1@Origine", "Point1@Origin"):          # nome del punto origine: italiano / inglese
                if ok:
                    break
                ok = doc.Extension.SelectByID2(name, "EXTSKETCHPOINT", 0, 0, 0, append, mark, null_variant(), 0)
            return bool(ok), "origine non selezionabile"
        ok = bool(obj.Select4(append, self._sd(doc, mark)))
        return ok, f"selezione di '{desc}' rifiutata"

    def _ent_desc(self, sk, ref, unit=None):
        return self._resolve_entity(None, sk, ref, unit)

    def _entity_info(self, s) -> Dict:
        t = int(s.GetType)
        row = {"id": self._seg_id(s), "type": SEG_TYPES.get(t, str(t)),
               "construction": bool(s.ConstructionGeometry)}
        try:
            a, b = s.GetStartPoint2, s.GetEndPoint2
            row["start_mm"] = [round(a.X * 1000, 4), round(a.Y * 1000, 4)]
            row["end_mm"] = [round(b.X * 1000, 4), round(b.Y * 1000, 4)]
            row["start_id"], row["end_id"] = self._pt_id(a), self._pt_id(b)
        except Exception:
            pass
        try:
            c = s.GetCenterPoint2
            row["center_mm"] = [round(c.X * 1000, 4), round(c.Y * 1000, 4)]
            row["center_id"] = self._pt_id(c)
            if t == 1:
                row["radius_mm"] = round(math.hypot(a.X - c.X, a.Y - c.Y) * 1000, 4)
        except Exception:
            pass
        try:
            row["length_mm"] = round(float(s.GetLength) * 1000, 4)
        except Exception:
            pass
        return row

    def _sketch_plane_info(self, doc) -> Dict:
        """Assi dello schizzo attivo in coordinate MODELLO (mm): per passare da (u,v) dello schizzo a (x,y,z).
        ModelToSketchTransform.ArrayData = [M(9) t(3) scala ...]; schizzo = M^T * modello + t  ->
        modello = M * (schizzo - t)."""
        sk = self._com(doc.SketchManager, "ActiveSketch")
        a = list(self._com(self._com(sk, "ModelToSketchTransform"), "ArrayData"))
        M = [[a[0], a[1], a[2]], [a[3], a[4], a[5]], [a[6], a[7], a[8]]]
        t = a[9:12]
        sc = a[12] if a[12] else 1.0

        def to_model(s):
            v = [(s[i] - t[i]) / sc for i in range(3)]
            return [sum(M[r][c] * v[c] for c in range(3)) for r in range(3)]
        o = to_model([0, 0, 0])
        ux = to_model([1, 0, 0])
        uy = to_model([0, 1, 0])
        un = to_model([0, 0, 1])
        axis = lambda p: [round(p[i] - o[i], 4) for i in range(3)]
        return {"sketch_origin_mm": [round(v * 1000, 4) for v in o], "sketch_x_axis": axis(ux),
                "sketch_y_axis": axis(uy), "sketch_normal": axis(un),
                "note": "modello(mm) = origine + u*x_axis + v*y_axis (u,v = coordinate dello schizzo in mm)"}

    def get_sketch_plane_info(self, sketch: str = None) -> Dict:
        """Orientamento del piano di uno schizzo nello spazio modello (per convertire u,v -> x,y,z)."""
        try:
            doc, err = self._part()
            if err:
                return err
            sk, err = self._active_sketch(doc, sketch)
            if err:
                return err
            return self._result(True, "Assi dello schizzo", SwErrors.swSuccess, self._sketch_plane_info(doc))
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    # ------------------------------------------------------------------ elenco / stato
    def list_sketch_entities(self, sketch: str = None) -> Dict:
        """Entita' dello schizzo attivo (o di `sketch`) con id, geometria (mm) e stato di definizione."""
        try:
            doc, err = self._part()
            if err:
                return err
            sk, err = self._active_sketch(doc, sketch)
            if err:
                return err
            segs = [self._entity_info(s) for s in self._segments(sk)]
            status = int(self._com(sk, "GetConstrainedStatus"))
            return self._result(True, f"{len(segs)} segmenti, schizzo {STATUS_NAMES.get(status, status)}",
                                SwErrors.swSuccess,
                                {"sketch": self._active_sketch_name(doc, sk), "status": STATUS_NAMES.get(status),
                                 "segments": segs,
                                 "points": [{"id": self._pt_id(p), "mm": [round(p.X * 1000, 4), round(p.Y * 1000, 4)]}
                                            for p in self._points(sk)]})
        except Exception as e:
            logger.error(f"list_sketch_entities: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def get_sketch_definition_status(self, sketch: str = None) -> Dict:
        """Stato dello schizzo: completamente definito / sottodefinito / sovradefinito (+ quote presenti)."""
        try:
            doc, err = self._part()
            if err:
                return err
            was_active = self._com(doc.SketchManager, "ActiveSketch") is not None
            if sketch and not was_active or sketch:
                sk, err = self._active_sketch(doc, sketch)
                if err:
                    return err
                reopened = True
            else:
                sk, err = self._active_sketch(doc, None)
                reopened = False
                if err:
                    # nessuno schizzo attivo: usa l'ultimo
                    name = self._last_of_type(doc, "ProfileFeature")
                    if not name:
                        return err
                    sk, err = self._active_sketch(doc, name)
                    if err:
                        return err
                    reopened = True
            code = int(self._com(sk, "GetConstrainedStatus"))
            name = self._active_sketch_name(doc, sk)
            dims = self._sketch_dimensions(doc, name)
            data = {"sketch": name, "status_code": code, "status": STATUS_NAMES.get(code, str(code)),
                    "fully_defined": code == 3, "over_defined": code == 4,
                    "segments": len(self._segments(sk)), "dimensions": dims}
            if reopened and not was_active:
                self._exit_sketch(doc)
            return self._result(True, f"Schizzo {name}: {STATUS_NAMES.get(code, code)}", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"get_sketch_definition_status: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def _sketch_dimensions(self, doc, feature_name: Optional[str], unit: str = "mm") -> List[Dict]:
        """Quote di una feature (schizzo o feature 3D): nome, tipo, valore (mm o gradi)."""
        out = []
        feat = self._find_feature(doc, feature_name) if feature_name else None
        if feat is None:
            return out
        try:
            dd = self._com(feat, "GetFirstDisplayDimension")
            while dd is not None:
                try:
                    d = dd.GetDimension2(0)
                    full = self._com(d, "FullName")
                    short = full.rsplit("@", 1)[0] if full.count("@") >= 2 else full
                    si = float(self._com(d, "SystemValue"))
                    dtype = int(self._com(d, "GetType"))
                    angular = dtype == 3
                    out.append({"name": short, "type": dtype,
                                "value": round(math.degrees(si) if angular else self._from_m(si, unit), 6),
                                "unit": "deg" if angular else self._unit_name(unit),
                                "driven": int(self._com(d, "DrivenState")) == 1})
                except Exception as e:
                    logger.debug(f"dim read: {e}")
                dd = feat.GetNextDisplayDimension(dd)
        except Exception as e:
            logger.debug(f"_sketch_dimensions: {e}")
        return out

    # ------------------------------------------------------------------ quote
    def add_sketch_dimension(self, kind: str = "auto", entity1=None, entity2=None, entity3=None,
                             value: float = None, unit: str = None, orientation: str = None,
                             name: str = None, position=None, sketch: str = None) -> Dict:
        """Quota vera dello schizzo (smart dimension) con valore impostato.
        kind: auto | length | horizontal | vertical | distance | radius | diameter | angle."""
        try:
            doc, err = self._part()
            if err:
                return err
            sk, err = self._active_sketch(doc, sketch)
            if err:
                return err
            sk_name = self._active_sketch_name(doc, sk)
            kind = (kind or "auto").lower()
            kind = {"lunghezza": "length", "orizzontale": "horizontal", "verticale": "vertical",
                    "distanza": "distance", "raggio": "radius", "diametro": "diameter", "angolo": "angle"}.get(kind, kind)
            if kind in ("distance", "length") and orientation:
                o = orientation.lower()
                if o.startswith("h") or o.startswith("o"):
                    kind = "horizontal"
                elif o.startswith("v"):
                    kind = "vertical"
            refs = [r for r in (entity1, entity2, entity3) if r is not None]
            if not refs:
                return self._result(False, "Serve almeno entity1 (id da draw_* o '@x,y' / 'pt@x,y').",
                                    SwErrors.swInvalidInput)
            doc.ClearSelection2(True)
            descs, objs = [], []
            for i, r in enumerate(refs):
                ok, msg = self._select_ref(doc, sk, r, append=(i > 0), unit=unit)
                if not ok:
                    return self._result(False, f"Entita' {i + 1}: {msg}", SwErrors.swSelectionError)
                o, d, _ = self._resolve_entity(doc, sk, r, unit)
                objs.append(o)
                descs.append(d)
            # posizione del testo: vicino alle entita' (sempre in metri, piano dello schizzo)
            if position:
                tx, ty = self._mmu(position[0], unit), self._mmu(position[1], unit)
                tries = [(tx, ty)]
            else:
                bx, by = self._refs_center(sk, objs)
                tries = [(bx + 0.012, by + 0.012), (bx - 0.012, by + 0.012), (bx + 0.025, by - 0.02),
                         (bx - 0.03, by - 0.03), (bx, by + 0.045), (bx + 0.06, by)]
            fn = {"auto": "AddDimension2", "length": "AddDimension2", "distance": "AddDimension2",
                  "angle": "AddDimension2", "horizontal": "AddHorizontalDimension2",
                  "vertical": "AddVerticalDimension2", "radius": "AddRadialDimension2",
                  "diameter": "AddDiameterDimension2"}.get(kind)
            if fn is None:
                return self._result(False, f"kind sconosciuto: {kind}", SwErrors.swInvalidInput)
            dd = None
            n_before = len(self._sketch_dimensions(doc, sk_name))
            for (tx, ty) in tries:
                dd = getattr(doc, fn)(tx, ty, 0)
                if dd is not None:
                    break
            if dd is None:
                # SW a volte restituisce None ma la quota esiste
                if len(self._sketch_dimensions(doc, sk_name)) > n_before:
                    dd = True
            if dd is None:
                return self._result(False, f"AddDimension fallito per {descs} (tipo {kind}). "
                                    "Controlla che le entita' siano compatibili (es. diametro su cerchio/arco).",
                                    SwErrors.swSketchError)
            dim_obj = None
            if dd is not True:
                dim_obj = dd.GetDimension2(0)
            else:
                dims = self._sketch_dimensions(doc, sk_name)
                dim_obj = doc.Parameter(dims[-1]["name"])
            if dim_obj is None:
                return self._result(False, "Quota creata ma non recuperabile", SwErrors.swSketchError)
            full = self._com(dim_obj, "FullName")
            if name:
                try:
                    dim_obj.Name = name
                    full = self._com(dim_obj, "FullName")
                except Exception:
                    pass
            try:
                driven = int(self._com(dim_obj, "DrivenState")) == 1
            except Exception:
                driven = False
            if driven:
                doc.ClearSelection2(True)
                return self._result(False, f"Quota {full} creata come di RIFERIMENTO (guidata): lo schizzo e' gia' "
                                    "definito in quella direzione, il valore non e' stato imposto (eviterebbe la "
                                    "sovradefinizione). Elimina la quota guidata o la relazione in conflitto.",
                                    SwErrors.swSketchError, {"dimension": full, "driven": True, "sketch": sk_name})
            if value is not None:
                if kind == "angle":
                    si = math.radians(value)
                else:
                    si = self._mmu(value, unit)
                dim_obj.SystemValue = si
            doc.ClearSelection2(True)   # niente EditRebuild3: chiuderebbe lo schizzo attivo
            cur = float(self._com(dim_obj, "SystemValue"))
            is_angle = (kind == "angle") or (value is None and dd is not True and
                                                int(self._com(dd, "GetType") if False else 0) == 5)
            shown = math.degrees(cur) if kind == "angle" else self._from_m(cur, unit)
            short = full.rsplit("@", 1)[0] if full.count("@") >= 2 else full
            status = int(self._com(sk, "GetConstrainedStatus"))
            return self._result(True, f"Quota {short} = {shown:.4f} {'deg' if kind == 'angle' else self._unit_name(unit)}"
                                f" (schizzo {STATUS_NAMES.get(status)})", SwErrors.swSuccess,
                                {"dimension": short, "full_name": full, "value": round(shown, 6),
                                 "unit": "deg" if kind == "angle" else self._unit_name(unit),
                                 "sketch": sk_name, "sketch_status": STATUS_NAMES.get(status),
                                 "entities": descs})
        except Exception as e:
            logger.error(f"add_sketch_dimension: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def _refs_center(self, sk, objs) -> Tuple[float, float]:
        xs, ys = [], []
        for o in objs:
            try:
                if o == "origin":
                    xs.append(0.0)
                    ys.append(0.0)
                elif hasattr(o, "GetType") and not hasattr(o, "X"):
                    a, b = o.GetStartPoint2, o.GetEndPoint2
                    xs += [a.X, b.X]
                    ys += [a.Y, b.Y]
                    try:
                        c = o.GetCenterPoint2
                        xs.append(c.X + 0.0)
                        ys.append(c.Y + 0.0)
                    except Exception:
                        pass
                else:
                    xs.append(o.X)
                    ys.append(o.Y)
            except Exception:
                continue
        if not xs:
            return 0.0, 0.0
        return sum(xs) / len(xs), sum(ys) / len(ys)

    # ------------------------------------------------------------------ relazioni
    def add_sketch_relation(self, relation: str, entity1=None, entity2=None, entity3=None,
                            unit: str = None, sketch: str = None) -> Dict:
        """Relazione geometrica: horizontal, vertical, coincident, tangent, concentric, equal, parallel,
        perpendicular, symmetric (3 entita': due + asse), fixed, collinear, midpoint."""
        try:
            doc, err = self._part()
            if err:
                return err
            sk, err = self._active_sketch(doc, sketch)
            if err:
                return err
            code = RELATIONS.get((relation or "").lower())
            if not code:
                return self._result(False, f"Relazione sconosciuta: {relation}. Valide: "
                                    f"{sorted(set(k for k in RELATIONS if k.isascii()))}", SwErrors.swInvalidInput)
            refs = [r for r in (entity1, entity2, entity3) if r is not None]
            if not refs:
                return self._result(False, "Serve almeno entity1.", SwErrors.swInvalidInput)
            doc.ClearSelection2(True)
            descs = []
            for i, r in enumerate(refs):
                ok, msg = self._select_ref(doc, sk, r, append=(i > 0), unit=unit)
                if not ok:
                    return self._result(False, f"Entita' {i + 1}: {msg}", SwErrors.swSelectionError)
                descs.append(self._resolve_entity(doc, sk, r, unit)[1])
            before = int(self._com(sk, "GetConstrainedStatus"))
            doc.SketchAddConstraints(code)
            doc.ClearSelection2(True)
            after = int(self._com(sk, "GetConstrainedStatus"))
            return self._result(True, f"Relazione {relation} su {descs}: schizzo {STATUS_NAMES.get(after)}",
                                SwErrors.swSuccess,
                                {"relation": code, "entities": descs, "status_before": STATUS_NAMES.get(before),
                                 "sketch_status": STATUS_NAMES.get(after)})
        except Exception as e:
            logger.error(f"add_sketch_relation: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    # ------------------------------------------------------------------ nuove entita'
    def _ent_result(self, seg, label: str, extra: Dict = None) -> Dict:
        data = {"entity_id": self._seg_id(seg)}
        try:
            data["start_point_id"] = self._pt_id(seg.GetStartPoint2)
            data["end_point_id"] = self._pt_id(seg.GetEndPoint2)
        except Exception:
            pass
        try:
            data["center_point_id"] = self._pt_id(seg.GetCenterPoint2)
        except Exception:
            pass
        if extra:
            data.update(extra)
        return self._result(True, f"{label} [{data['entity_id']}]", SwErrors.swSuccess, data)

    def _sketch_ready(self):
        doc, err = self._part()
        if err:
            return None, None, err
        sm = doc.SketchManager
        if self._com(sm, "ActiveSketch") is None:
            return None, None, self._result(False, "Nessuno schizzo attivo: usa create_sketch.", SwErrors.swSketchError)
        return doc, sm, None

    def draw_construction_line(self, x1: float, y1: float, x2: float, y2: float, unit: str = None) -> Dict:
        try:
            doc, sm, err = self._sketch_ready()
            if err:
                return err
            seg = sm.CreateLine(self._mmu(x1, unit), self._mmu(y1, unit), 0, self._mmu(x2, unit), self._mmu(y2, unit), 0)
            if seg is None:
                return self._result(False, "CreateLine fallito", SwErrors.swSketchError)
            seg.ConstructionGeometry = True
            return self._ent_result(seg, "Linea di costruzione")
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def draw_centerline_axis(self, x1: float, y1: float, x2: float, y2: float, unit: str = None) -> Dict:
        """Asse di mezzeria (centerline): serve alla rivoluzione e alle simmetrie."""
        try:
            doc, sm, err = self._sketch_ready()
            if err:
                return err
            seg = sm.CreateCenterLine(self._mmu(x1, unit), self._mmu(y1, unit), 0,
                                      self._mmu(x2, unit), self._mmu(y2, unit), 0)
            if seg is None:
                return self._result(False, "CreateCenterLine fallito", SwErrors.swSketchError)
            return self._ent_result(seg, "Asse di mezzeria")
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def draw_point(self, x: float, y: float, unit: str = None) -> Dict:
        try:
            doc, sm, err = self._sketch_ready()
            if err:
                return err
            p = sm.CreatePoint(self._mmu(x, unit), self._mmu(y, unit), 0)
            if p is None:
                return self._result(False, "CreatePoint fallito", SwErrors.swSketchError)
            return self._result(True, f"Punto [{self._pt_id(p)}]", SwErrors.swSuccess, {"point_id": self._pt_id(p)})
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def draw_spline(self, points: list, unit: str = None, closed: bool = False) -> Dict:
        """Spline per punti [[x,y],...] (almeno 2)."""
        try:
            doc, sm, err = self._sketch_ready()
            if err:
                return err
            if not points or len(points) < 2:
                return self._result(False, "Servono almeno 2 punti.", SwErrors.swInvalidInput)
            pts = list(points) + ([points[0]] if closed else [])
            flat = []
            for p in pts:
                flat += [self._mmu(p[0], unit), self._mmu(p[1], unit), 0.0]
            seg = sm.CreateSpline2(r8_array(flat), True)
            if seg is None:
                return self._result(False, "CreateSpline2 fallito", SwErrors.swSketchError)
            return self._ent_result(seg, f"Spline per {len(pts)} punti")
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def draw_slot(self, x1: float, y1: float, x2: float, y2: float, width: float, unit: str = None,
                  slot_type: str = "center_to_center") -> Dict:
        """Asola retta: centri dei due estremi (center_to_center) o estremi (overall); width = larghezza."""
        try:
            doc, sm, err = self._sketch_ready()
            if err:
                return err
            t = 0 if slot_type.lower().startswith("center") else 1   # swSketchSlotCreationType_e
            before = {self._seg_id(s) for s in self._segments(self._com(sm, "ActiveSketch"))}
            res = sm.CreateSketchSlot(t, 0, self._mmu(width, unit),
                                      self._mmu(x1, unit), self._mmu(y1, unit), 0,
                                      self._mmu(x2, unit), self._mmu(y2, unit), 0, 0, 0, 0, 1, False)
            if res is None:
                return self._result(False, "CreateSketchSlot fallito", SwErrors.swSketchError)
            segs = [self._seg_id(s) for s in self._segments(self._com(sm, "ActiveSketch"))
                    if self._seg_id(s) not in before and not s.ConstructionGeometry]
            return self._result(True, "Asola creata", SwErrors.swSuccess,
                                {"width": width, "unit": self._unit_name(unit), "segment_ids": segs,
                                 "note": "linea centrale (costruzione) + 2 linee + 2 archi"})
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def draw_ellipse(self, cx: float, cy: float, semi_major: float, semi_minor: float,
                     angle: float = 0.0, unit: str = None) -> Dict:
        """Ellisse con centro, semiassi e inclinazione dell'asse maggiore (gradi)."""
        try:
            doc, sm, err = self._sketch_ready()
            if err:
                return err
            a = math.radians(angle)
            cxm, cym = self._mmu(cx, unit), self._mmu(cy, unit)
            M, m = self._mmu(semi_major, unit), self._mmu(semi_minor, unit)
            seg = sm.CreateEllipse(cxm, cym, 0, cxm + M * math.cos(a), cym + M * math.sin(a), 0,
                                   cxm - m * math.sin(a), cym + m * math.cos(a), 0)
            if seg is None:
                return self._result(False, "CreateEllipse fallito", SwErrors.swSketchError)
            return self._ent_result(seg, "Ellisse")
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def draw_arc_3point(self, x1: float, y1: float, x2: float, y2: float, x3: float, y3: float,
                        unit: str = None) -> Dict:
        """Arco per tre punti (inizio, punto sull'arco, fine)."""
        try:
            doc, sm, err = self._sketch_ready()
            if err:
                return err
            m = lambda v: self._mmu(v, unit)
            seg = sm.Create3PointArc(m(x1), m(y1), 0, m(x3), m(y3), 0, m(x2), m(y2), 0)
            if seg is None:
                return self._result(False, "Create3PointArc fallito", SwErrors.swSketchError)
            return self._ent_result(seg, "Arco per 3 punti")
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def sketch_fillet(self, radius: float, entity1=None, entity2=None, corner=None, unit: str = None) -> Dict:
        """Raccordo di schizzo fra due segmenti (entity1/entity2) o in un vertice (corner=[x,y])."""
        try:
            doc, err = self._part()
            if err:
                return err
            sk, err = self._active_sketch(doc, None)
            if err:
                return err
            doc.ClearSelection2(True)
            n0 = len(self._segments(sk))
            if corner is not None:
                ok, msg = self._select_ref(doc, sk, "pt@%s,%s" % (corner[0], corner[1]), False, unit)
                if not ok:
                    return self._result(False, msg, SwErrors.swSelectionError)
            else:
                for i, r in enumerate((entity1, entity2)):
                    ok, msg = self._select_ref(doc, sk, r, append=(i > 0), unit=unit)
                    if not ok:
                        return self._result(False, f"Entita' {i + 1}: {msg}", SwErrors.swSelectionError)
            res = doc.SketchManager.CreateFillet(self._mmu(radius, unit), 1)   # 1 = vincola gli angoli
            doc.ClearSelection2(True)
            if res is None or (hasattr(res, "GetType") is False and not res):
                return self._result(False, "CreateFillet fallito (le due entita' devono incontrarsi in un vertice)",
                                    SwErrors.swSketchError)
            arcs = [self._seg_id(s) for s in self._segments(sk) if int(s.GetType) == 1]
            return self._result(True, f"Raccordo R{radius} {self._unit_name(unit)}", SwErrors.swSuccess,
                                {"radius": radius, "segments_before": n0, "segments_after": len(self._segments(sk)),
                                 "arc_ids": arcs})
        except Exception as e:
            logger.error(f"sketch_fillet: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def offset_entities(self, entities: list, offset: float, both_directions: bool = False,
                        make_construction: bool = False, cap_ends: bool = False, unit: str = None) -> Dict:
        """Offset di entita' dello schizzo (id o '@x,y'); catena automatica."""
        try:
            doc, err = self._part()
            if err:
                return err
            sk, err = self._active_sketch(doc, None)
            if err:
                return err
            doc.ClearSelection2(True)
            for i, r in enumerate(entities or []):
                ok, msg = self._select_ref(doc, sk, r, append=(i > 0), unit=unit)
                if not ok:
                    return self._result(False, f"Entita' {i + 1}: {msg}", SwErrors.swSelectionError)
            n0 = len(self._segments(sk))
            res = doc.SketchManager.SketchOffset2(self._mmu(offset, unit), both_directions, True, cap_ends,
                                                  make_construction, False)
            doc.ClearSelection2(True)
            n1 = len(self._segments(sk))
            if not res and n1 <= n0:
                return self._result(False, "SketchOffset2 non ha creato nulla (offset troppo grande?)",
                                    SwErrors.swSketchError)
            return self._result(True, f"Offset {offset} {self._unit_name(unit)}: +{n1 - n0} segmenti",
                                SwErrors.swSuccess, {"new_segments": n1 - n0,
                                                     "ids": [self._seg_id(s) for s in self._segments(sk)][n0:]})
        except Exception as e:
            logger.error(f"offset_entities: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def convert_entities(self, edge_points: list = None, face_point: list = None, chain: bool = True,
                         unit: str = None) -> Dict:
        """Converti entita': proietta nello schizzo attivo spigoli (punti sugli spigoli) o i bordi di una faccia."""
        try:
            doc, err = self._part()
            if err:
                return err
            sk, err = self._active_sketch(doc, None)
            if err:
                return err
            doc.ClearSelection2(True)
            if face_point:
                ok, info = self._select_point(doc, "face", face_point, unit, False, 0)
            else:
                ok, msg = self._select_points(doc, "edge", edge_points or [], unit)
                info = {"error": msg}
            if not ok:
                return self._result(False, info.get("error", "selezione fallita"), SwErrors.swSelectionError)
            n0 = len(self._segments(sk))
            res = doc.SketchManager.SketchUseEdge3(chain, False)
            doc.ClearSelection2(True)
            n1 = len(self._segments(sk))
            if n1 <= n0:
                return self._result(False, "SketchUseEdge3 non ha aggiunto segmenti", SwErrors.swSketchError)
            return self._result(True, f"Convertite entita': +{n1 - n0} segmenti", SwErrors.swSuccess,
                                {"new_segments": n1 - n0, "ids": [self._seg_id(s) for s in self._segments(sk)][n0:]})
        except Exception as e:
            logger.error(f"convert_entities: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def mirror_sketch_entities(self, entities: list, axis, unit: str = None, keep_original: bool = True) -> Dict:
        """Specchia entita' dello schizzo rispetto a una linea / asse di mezzeria (id o '@x,y')."""
        try:
            doc, err = self._part()
            if err:
                return err
            sk, err = self._active_sketch(doc, None)
            if err:
                return err
            doc.ClearSelection2(True)
            for i, r in enumerate(entities or []):
                ok, msg = self._select_ref(doc, sk, r, append=(i > 0), unit=unit, mark=1)
                if not ok:
                    return self._result(False, f"Entita' {i + 1}: {msg}", SwErrors.swSelectionError)
            ok, msg = self._select_ref(doc, sk, axis, append=True, unit=unit, mark=2)
            if not ok:
                return self._result(False, f"Asse: {msg}", SwErrors.swSelectionError)
            n0 = len(self._segments(sk))
            doc.SketchMirror()
            doc.ClearSelection2(True)
            n1 = len(self._segments(sk))
            if n1 <= n0:
                return self._result(False, "SketchMirror non ha creato nulla", SwErrors.swSketchError)
            return self._result(True, f"Specchiate: +{n1 - n0} segmenti", SwErrors.swSuccess,
                                {"new_segments": n1 - n0, "ids": [self._seg_id(s) for s in self._segments(sk)][n0:]})
        except Exception as e:
            logger.error(f"mirror_sketch_entities: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)

    def add_sketch_text(self, text: str, x: float, y: float, height: float = 5.0, unit: str = None) -> Dict:
        """Testo nello schizzo (diventa profilo per estrusioni/tagli)."""
        try:
            doc, sm, err = self._sketch_ready()
            if err:
                return err
            st = doc.InsertSketchText(self._mmu(x, unit), self._mmu(y, unit), 0, text, 0, False, False, 100, 0)
            if st is None:
                return self._result(False, "InsertSketchText fallito", SwErrors.swSketchError)
            note = ""
            try:
                tf = st.GetTextFormat
                tf.CharHeight = self._mmu(height, unit)
                tf.CharHeightInPts = False
                st.SetTextFormat(False, tf)
            except Exception as e:
                note = f"altezza non impostata ({e})"
            return self._result(True, f"Testo '{text}'", SwErrors.swSuccess,
                                {"text": text, "height": height, "unit": self._unit_name(unit), "note": note})
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swSketchError)
