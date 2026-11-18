"""
Lotto DISEGNI 2: formati foglio, viste speciali (relative, allineate, semi-sezioni, lamiera aperta,
posizioni alternative, esploso), quotatura progressiva/smussi, simboli di saldatura/sbavatura ISO 13715,
tabelle (revisioni, distinta di taglio, generiche), livelli CAD (layers), blocchi ed export PDF a livelli (mixin Drawings2Operations).
Schemi in tools_ext/drawings2.py.
"""

import os
import math
import logging
from typing import Dict

from ..constants import SwErrors
from .modeling_base import null_variant
from ..utils.keep_file import keeps_old_file, set_aside

logger = logging.getLogger(__name__)


def _bi():
    import win32com.client
    import pythoncom
    return win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)


class Drawings2Operations:
    """Mixin per operazioni estese lotto 2 su disegni e tavole 2D (Drawings2Operations)."""

    def _drw_rebuild(self, doc) -> None:
        """Rigenera e ridisegna la tavola in modo sicuro."""
        try:
            self._com(doc, "EditRebuild3")
        except Exception:
            pass
        try:
            doc.ForceRebuild3(False)
        except Exception:
            pass


    # ------------------------------------------------------------------ 1. Fogli e Formati
    def edit_sheet_format(self) -> Dict:
        """Attiva la modalita' di modifica del cartiglio e delle linee di bordo del foglio."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            try:
                doc.EditTemplate()
            except Exception as e:
                return self._result(False, f"edit_sheet_format: modifica formato non riuscita: {e}", SwErrors.swGenericError)
            return self._result(
                True, "Modalita' di modifica del formato foglio (cartiglio/cornice) attivata.",
                SwErrors.swSuccess, {"editing_format": True}
            )
        except Exception as e:
            return self._result(False, f"edit_sheet_format: {e}", SwErrors.swGenericError)

    def exit_sheet_format(self) -> Dict:
        """Esce dalla modalita' modifica formato e ritorna all'editing delle viste sul foglio."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            try:
                doc.EditSheet()
            except Exception as e:
                return self._result(False, f"exit_sheet_format: uscita dal formato non riuscita: {e}", SwErrors.swGenericError)
            return self._result(
                True, "Uscita dalla modalita' formato foglio completata con successo.",
                SwErrors.swSuccess, {"editing_sheet": True}
            )
        except Exception as e:
            return self._result(False, f"exit_sheet_format: {e}", SwErrors.swGenericError)

    def reload_sheet_format(self, template_path: str = None) -> Dict:
        """Ricarica o aggiorna il formato foglio (.slddrt) rigenerando loghi e cartiglio."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            if template_path and not os.path.isfile(str(template_path)):
                return self._result(False, f"reload_sheet_format: template '{template_path}' non trovato", SwErrors.swFileNotFoundError)
            sheet = None
            try:
                sheet = self._com(doc, "GetCurrentSheet")
            except Exception:
                pass
            if template_path:
                if not sheet:
                    return self._result(False, "reload_sheet_format: foglio corrente non trovato", SwErrors.swSelectionError)
                try:
                    sheet.SetTemplateName(str(template_path))
                    ok = sheet.ReloadTemplate()
                except Exception as e:
                    return self._result(False, f"reload_sheet_format: applicazione template non riuscita: {e}", SwErrors.swFeatureError)
                if not ok:
                    return self._result(False, "reload_sheet_format: SolidWorks non ha ricaricato il template", SwErrors.swFeatureError)
            self._drw_rebuild(doc)
            msg = (f"Formato foglio ricaricato dal template '{template_path}'." if template_path
                   else "Foglio rigenerato (nessun template indicato: formato non ricaricato).")
            return self._result(True, msg, SwErrors.swSuccess, {"template_path": template_path})
        except Exception as e:
            return self._result(False, f"reload_sheet_format: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 2. Viste Principali e Proiettate
    def add_relative_view(self, model_path: str = None, front_face_point: list = None, right_face_point: list = None,
                          x: float = 100.0, y: float = 100.0, scale: str = None, unit: str = None) -> Dict:
        """Vista relativa al modello: la faccia piana `front_face_point` guarda verso chi osserva, la faccia
        `right_face_point` verso destra. Le facce si selezionano NEL MODELLO (attivato, Mark 1 e 2), poi
        CreateRelativeView(modello, x, y, FRONT=0, RIGHT=1) si chiama sull'oggetto della TAVOLA anche se non e' quella
        attiva (misurato 2026-10-24: normale della faccia davanti -> (0,0,1), della destra -> (1,0,0) nella vista)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            if not front_face_point or not right_face_point or len(front_face_point) != 3 or len(right_face_point) != 3:
                return self._result(False, "add_relative_view: servono front_face_point e right_face_point [x,y,z] (mm del modello)",
                                    SwErrors.swInvalidInput)
            path = self._model_path_for_drawing(doc, model_path)
            if not path or not os.path.isfile(path):
                return self._result(False, f"add_relative_view: modello non trovato ({path or 'nessuna vista nella tavola'})",
                                    SwErrors.swFileNotFoundError)
            mdoc, opened = self._get_model_doc(path)
            if mdoc is None:
                return self._result(False, f"add_relative_view: impossibile aprire {path}", SwErrors.swFileNotFoundError)
            # per riattivare la tavola: il nome del FILE se salvata (il titolo senza " - Foglio1" puo' coincidere con quello
            # del pezzo quando la tavola ha il nome del modello, e ActivateDoc3 riattiverebbe il pezzo)
            dpath = str(doc.GetPathName or "")
            dtitle = os.path.basename(dpath) if dpath else str(doc.GetTitle).split(" - ")[0]
            app = self._sw_app
            e = _bi()
            app.ActivateDoc3(str(mdoc.GetTitle), False, 0, e)
            normals = []
            try:
                mdoc.ClearSelection2(True)
                sm = mdoc.SelectionManager
                for mark, p in ((1, front_face_point), (2, right_face_point)):
                    # ricerca geometrica (SelectByID2 nel punto non trova le facce nascoste dietro altre, es. x=0)
                    ok_sel, info = self._select_point(mdoc, "face", p, unit, append=mark == 2, mark=mark)
                    if not ok_sel:
                        mdoc.ClearSelection2(True)
                        return self._result(False, f"add_relative_view: faccia nel punto {list(p)} del modello: {info.get('error')}",
                                            SwErrors.swSelectionError)
                    f = sm.GetSelectedObject6(mark, -1)
                    nrm = None
                    try:
                        if f.GetSurface.IsPlane:
                            nrm = [float(c) for c in f.Normal]
                    except Exception:
                        pass
                    if nrm is None:
                        mdoc.ClearSelection2(True)
                        return self._result(False, f"add_relative_view: la faccia nel punto {list(p)} non e' piana", SwErrors.swInvalidInput)
                    normals.append(nrm)
                v = doc.CreateRelativeView(path, self._m(float(x), unit), self._m(float(y), unit), 0, 1)
            finally:
                try:
                    mdoc.ClearSelection2(True)
                except Exception:
                    pass
                app.ActivateDoc3(dtitle, False, 0, _bi())
            if v is None:
                return self._result(False, "add_relative_view: SolidWorks non ha creato la vista (facce perpendicolari tra loro?)",
                                    SwErrors.swFeatureError)
            if scale:
                sc = self._parse_scale(scale)
                if sc:
                    self._set_view_scale(v, *sc)
            _, dirp, _ = self._dm_proj(v)
            got_f = [round(c, 4) for c in dirp(normals[0])]
            got_r = [round(c, 4) for c in dirp(normals[1])]
            ok = abs(got_f[2] - 1) < 1e-3 and abs(got_r[0] - 1) < 1e-3
            data = {**self._view_info(v), "front_normal_in_view": got_f, "right_normal_in_view": got_r, "model": path}
            if not ok:
                removed = self.delete_view(self._com(v, "GetName2")).get("success")
                return self._result(False, f"add_relative_view: orientamento non come chiesto (davanti {got_f}, destra {got_r}); "
                                           f"vista {'tolta' if removed else 'NON tolta'} (le due facce devono essere perpendicolari)",
                                    SwErrors.swFeatureError, data)
            return self._result(True, f"Vista relativa {self._com(v, 'GetName2')}: faccia davanti verso chi guarda, l'altra a destra",
                                SwErrors.swSuccess, data)
        except Exception as e:
            return self._result(False, f"add_relative_view: {e}", SwErrors.swGenericError)


    # ------------------------------------------------------------------ 3. Viste di Sezione e Dettaglio
    def add_aligned_section_view(self, x1: float, y1: float, x2: float, y2: float, x3: float, y3: float,
                                 view_x: float = None, view_y: float = None, parent_view: str = None,
                                 label: str = "A", unit: str = None) -> Dict:
        """Sezione allineata per tre punti del FOGLIO (inizio, vertice sull'asse, fine): stessa strada di
        add_section_view(orientation='aligned') con i punti resi relativi al centro della vista madre. Il tratto inclinato
        viene ruotato nel piano di taglio (opzione 2 di CreateSectionViewAt5, vedi drawings.py)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            parent, err = self._find_view(doc, parent_view)
            if err:
                return err
            px, py = (float(c) for c in tuple(parent.Position)[:2])
            rel = []
            for (xx, yy) in ((x1, y1), (x2, y2), (x3, y3)):
                rel += [(self._m(float(xx), unit) - px) * 1000.0, (self._m(float(yy), unit) - py) * 1000.0]
            vx = self._mm(self._m(float(view_x), unit)) if view_x is not None else None
            vy = self._mm(self._m(float(view_y), unit)) if view_y is not None else None
            r = self.add_section_view(parent_view=self._com(parent, "GetName2"), orientation="aligned", points=rel,
                                      label=label, view_x=vx, view_y=vy, unit="mm")
            if r.get("success"):
                r.setdefault("data", {})["points_relative_to_parent_mm"] = [round(c, 4) for c in rel]
                if not r["data"].get("aligned_rotated"):
                    r["success"] = False
                    r["message"] = "add_aligned_section_view: i tre punti sono allineati agli assi: serve un tratto inclinato"
            return r
        except Exception as e:
            return self._result(False, f"add_aligned_section_view: {e}", SwErrors.swGenericError)


    # ------------------------------------------------------------------ 4. Viste Speciali di Assieme e Lamiera
    def add_flat_pattern_drawing_view(self, model_path: str = None, x: float = 150.0, y: float = 150.0,
                                      scale: str = None, show_bend_lines: bool = True, unit: str = None) -> Dict:
        """Inserisce una vista di lamiera spianata (flat pattern) con linee e note di piega."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            xm = self._mmu(x, unit)
            ym = self._mmu(y, unit)
            if not model_path:
                return self._result(False, "add_flat_pattern_drawing_view: model_path obbligatorio", SwErrors.swInvalidInput)
            view = doc.CreateFlatPatternViewFromModelView3(str(model_path), "", xm, ym, 0, False, False)
            if not view:
                return self._result(False, "add_flat_pattern_drawing_view: vista flat pattern non creata", SwErrors.swFeatureError)
            self._drw_rebuild(doc)
            ignored = ["show_bend_lines"] + (["scale"] if scale is not None else [])
            return self._result(
                True, f"Vista di lamiera spianata (flat pattern) inserita a ({x}, {y}) mm.",
                SwErrors.swSuccess, {"x": x, "y": y, "scale": scale, "ignored_params": ignored}
            )
        except Exception as e:
            return self._result(False, f"add_flat_pattern_drawing_view: {e}", SwErrors.swGenericError)


    def show_exploded_drawing_view(self, view_name: str = None, exploded: bool = True, show_lines: bool = True) -> Dict:
        """Mostra o nasconde la vista esplosa dell'assieme con tracciamento delle linee di percorso."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            if view_name:
                view, err = self._find_view(doc, view_name)
                if err:
                    return err
            else:
                view = doc.ActiveDrawingView
                if not view:
                    return self._result(False, "show_exploded_drawing_view: nessuna vista attiva", SwErrors.swSelectionError)
            view.ShowExploded(bool(exploded))
            self._drw_rebuild(doc)
            read = self._view_exploded(view)
            if read != bool(exploded):
                return self._result(False, f"show_exploded_drawing_view: stato esploso non applicato (letto {read})", SwErrors.swFeatureError)
            st_str = "esplosa" if exploded else "collassata"
            return self._result(
                True, f"Vista '{self._com(view, 'GetName2')}' impostata su stato {st_str}.",
                SwErrors.swSuccess, {"view_name": view_name, "exploded": read, "ignored_params": ["show_lines"]}
            )
        except Exception as e:
            return self._result(False, f"show_exploded_drawing_view: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 5. Gestione, Layout e Allineamento Viste
    def rotate_drawing_view(self, view_name: str, angle_deg: float = 90.0) -> Dict:
        """Ruota l'orientamento di una vista sul foglio di un angolo in gradi."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            rad = math.radians(float(angle_deg))
            doc.ClearSelection2(True)
            if not doc.Extension.SelectByID2(str(view_name), "DRAWINGVIEW", 0, 0, 0, False, 0, null_variant(), 0):
                return self._result(False, f"rotate_drawing_view: vista '{view_name}' non trovata", SwErrors.swSelectionError)
            doc.DrawingViewRotate(rad)
            doc.ClearSelection2(True)
            self._drw_rebuild(doc)
            v, err = self._find_view(doc, view_name)
            if err:
                return err
            read = math.degrees(float(self._com(v, "Angle"))) % 360.0
            diff = (read - float(angle_deg) + 180.0) % 360.0 - 180.0
            if abs(diff) > 0.01:
                return self._result(False, f"rotate_drawing_view: angolo non applicato (letto {read:.4f} gradi, chiesto {angle_deg})", SwErrors.swFeatureError)
            return self._result(
                True, f"Vista '{view_name}' ruotata di {angle_deg} gradi.",
                SwErrors.swSuccess, {"view_name": view_name, "angle_deg": angle_deg, "angle_read_deg": round(read, 4)}
            )
        except Exception as e:
            return self._result(False, f"rotate_drawing_view: {e}", SwErrors.swGenericError)


    # ------------------------------------------------------------------ 6. Quotatura Automatica e Modello
    def _d2_view(self, doc, view_name):
        if view_name:
            return self._find_view(doc, view_name)
        vs = self._sheet_views(doc)
        if not vs:
            return None, self._result(False, "Nessuna vista nel foglio", SwErrors.swSelectionError)
        return vs[0], None

    def _d2_sheet_point(self, v, p, unit):
        """[x,y,z] mm del modello (proiettato con la vista) o [x,y] mm del foglio -> (x, y) in metri sul foglio."""
        if not isinstance(p, (list, tuple)) or len(p) not in (2, 3):
            return None
        if len(p) == 2:
            return self._m(float(p[0]), unit), self._m(float(p[1]), unit)
        proj, _, _ = self._dm_proj(v)
        q = proj(tuple(self._m(float(c), unit) for c in p))
        return q[0], q[1]

    def _d2_select_edge(self, doc, xy, append: bool) -> bool:
        """Seleziona lo spigolo (o la silhouette) nel punto del foglio, in aggiunta se append; toglie le viste che
        SelectByID2 seleziona insieme allo spigolo (tipo 12: con la vista prima, AddOrdinateDimension2 crea solo lo 0)."""
        x, y = xy
        ok = False
        for typ in ("EDGE", "SILEDGE"):
            for dx, dy in ((0, 0), (0.0003, 0), (-0.0003, 0), (0, 0.0003), (0, -0.0003), (0.0005, 0), (0, 0.0005)):
                if doc.Extension.SelectByID2("", typ, x + dx, y + dy, 0, append, 0, null_variant(), 0):
                    ok = True
                    break
            if ok:
                break
        sm = doc.SelectionManager
        i = int(sm.GetSelectedObjectCount2(-1))
        while i >= 1:
            if int(sm.GetSelectedObjectType3(i, -1)) == 12:
                sm.DeSelect2(i, -1)
            i -= 1
        return ok

    def _d2_dd_text(self, dd) -> str:
        try:
            d2 = dd.GetDisplayData
            return " ".join(str(d2.GetTextAtIndex(i)).strip() for i in range(int(self._com(d2, "GetTextCount"))))
        except Exception:
            return ""

    def add_ordinate_dimension(self, origin_point: list, dimension_points: list, view_name: str = None,
                               direction: str = "horizontal", offset: float = None, unit: str = None) -> Dict:
        """Catena di quote ordinate. AddOrdinateDimension2 con PIU' spigoli selezionati crea solo lo 0 (misurato 2026-10-24):
        si crea la base con il solo spigolo d'origine, poi per ogni spigolo si seleziona la base PER NOME
        (GetNameForSelection, tipo DIMENSION; Annotation.Select3 non seleziona) + lo spigolo e si chiama EditOrdinate."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            kind = {"horizontal": 3, "orizzontale": 3, "vertical": 2, "verticale": 2}.get(str(direction or "horizontal").lower())
            if kind is None:
                return self._result(False, "add_ordinate_dimension: direction = horizontal | vertical", SwErrors.swInvalidInput)
            if not dimension_points:
                return self._result(False, "add_ordinate_dimension: servono dimension_points", SwErrors.swInvalidInput)
            v, err = self._d2_view(doc, view_name)
            if err:
                return err
            o = self._d2_sheet_point(v, origin_point, unit)
            pts = [self._d2_sheet_point(v, p, unit) for p in dimension_points]
            if o is None or any(q is None for q in pts):
                return self._result(False, "add_ordinate_dimension: punti [x,y,z] (modello) o [x,y] (foglio)", SwErrors.swInvalidInput)
            vname = self._com(v, "GetName2")
            ords0 = {str(d.GetDimension2(0).FullName) for d in self._display_dims(v) if int(d.Type2) == 1}

            def ords():
                return [d for d in self._display_dims(v) if int(d.Type2) == 1 and str(d.GetDimension2(0).FullName) not in ords0]
            doc.ClearSelection2(True)
            if not self._d2_select_edge(doc, o, False):
                doc.ClearSelection2(True)
                return self._result(False, f"add_ordinate_dimension: nessuno spigolo nel punto d'origine della vista {vname}",
                                    SwErrors.swSelectionError)
            off = self._m(float(offset), unit) if offset is not None else 0.015
            loc = (o[0], o[1] - off) if kind == 3 else (o[0] - off, o[1])
            rc = doc.AddOrdinateDimension2(kind, loc[0], loc[1], 0)
            doc.ClearSelection2(True)
            new = ords()
            if not new:
                return self._result(False, f"add_ordinate_dimension: SolidWorks non ha creato la quota base (codice {rc})",
                                    SwErrors.swFeatureError)
            sel_name = str(new[0].GetNameForSelection)
            failed = []
            for i, q in enumerate(pts):
                n_before = len(new)
                doc.ClearSelection2(True)
                ok_b = doc.Extension.SelectByID2(sel_name, "DIMENSION", 0, 0, 0, False, 0, null_variant(), 0)
                ok_e = self._d2_select_edge(doc, q, True)
                if ok_b and ok_e:
                    self._com(doc, "EditOrdinate")
                doc.ClearSelection2(True)
                new = ords()
                if len(new) == n_before:
                    failed.append({"index": i, "point": dimension_points[i],
                                   "why": "spigolo non trovato" if not ok_e else
                                   "SolidWorks non ha aggiunto la quota (spigolo non perpendicolare alla direzione?)"})
            values = [{"name": str(d.GetDimension2(0).FullName), "value_mm": round(float(d.GetDimension2(0).Value), 4),
                       "text": self._d2_dd_text(d)} for d in new]
            data = {"view": vname, "direction": "horizontal" if kind == 3 else "vertical", "ordinates": values, "failed": failed}
            if failed:
                return self._result(False, f"add_ordinate_dimension: {len(failed)} spigoli non quotati su {len(pts)}: {failed}",
                                    SwErrors.swFeatureError, data)
            return self._result(True, f"Quote ordinate nella vista {vname}: {[x['value_mm'] for x in values]} mm",
                                SwErrors.swSuccess, data)
        except Exception as e:
            return self._result(False, f"add_ordinate_dimension: {e}", SwErrors.swGenericError)

    def add_chamfer_dimension(self, point_on_chamfer: list, reference_point: list, view_name: str = None,
                              x: float = None, y: float = None, unit: str = None) -> Dict:
        """Quota di smusso: spigolo dello smusso + spigolo adiacente selezionati, poi AddChamferDim(x, y, 0) (misurato
        2026-10-24: smusso 5 mm -> testo '5,00 X 45', Type2 10)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            v, err = self._d2_view(doc, view_name)
            if err:
                return err
            c = self._d2_sheet_point(v, point_on_chamfer, unit)
            r = self._d2_sheet_point(v, reference_point, unit)
            if c is None or r is None:
                return self._result(False, "add_chamfer_dimension: punti [x,y,z] (modello) o [x,y] (foglio)", SwErrors.swInvalidInput)
            vname = self._com(v, "GetName2")
            n0 = {str(d.GetDimension2(0).FullName) for d in self._display_dims(v)}
            doc.ClearSelection2(True)
            ok1 = self._d2_select_edge(doc, c, False)
            ok2 = self._d2_select_edge(doc, r, True)
            if not (ok1 and ok2):
                doc.ClearSelection2(True)
                return self._result(False, f"add_chamfer_dimension: spigolo {'dello smusso' if not ok1 else 'di riferimento'} "
                                           f"non trovato nella vista {vname}", SwErrors.swSelectionError)
            tx = self._m(float(x), unit) if x is not None else c[0] + 0.015
            ty = self._m(float(y), unit) if y is not None else c[1] + 0.015
            dd = doc.AddChamferDim(tx, ty, 0)
            doc.ClearSelection2(True)
            new = [d for d in self._display_dims(v) if str(d.GetDimension2(0).FullName) not in n0]
            if dd is None or not new:
                return self._result(False, "add_chamfer_dimension: SolidWorks non ha creato la quota (lo spigolo e' uno smusso? "
                                           "il riferimento e' adiacente?)", SwErrors.swFeatureError)
            d = new[0]
            text = self._d2_dd_text(d)
            data = {"view": vname, "name": str(d.GetDimension2(0).FullName), "text": text, "chamfer_type": int(d.Type2) == 10}
            return self._result(True, f"Quota di smusso '{text}' nella vista {vname}", SwErrors.swSuccess, data)
        except Exception as e:
            return self._result(False, f"add_chamfer_dimension: {e}", SwErrors.swGenericError)

    def _d2_dim_annotations(self, views, name: str):
        """(vista, annotazione, nome completo) delle quote che corrispondono a `name`, nascoste comprese."""
        q = str(name).strip().lower()
        out = []
        for v in views:
            for an in (v.GetAnnotations or ()):
                try:
                    if int(an.GetType) != 4:
                        continue
                    dim = an.GetSpecificAnnotation.GetDimension2(0)
                    full = str(dim.FullName)
                    parts = full.split("@")
                    names = {str(an.GetName).lower(), str(dim.Name).lower(), full.lower(), "@".join(parts[:2]).lower()}
                    if q in names:
                        out.append((v, an, full))
                except Exception as e:
                    logger.debug(f"_d2_dim_annotations: {e}")
        return out

    def hide_show_dimension(self, dimension_name: str, visible: bool = True, view_name: str = None) -> Dict:
        """Nasconde/mostra una quota con IAnnotation.Visible (1 visibile, 3 nascosta). Le quote nascoste spariscono da
        GetFirstDisplayDimension5 ma restano in View.GetAnnotations (misurato 2026-10-24): si cercano li'."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            views = self._sheet_views(doc)
            if view_name:
                v0, err = self._find_view(doc, view_name)
                if err:
                    return err
                views = [v0]
            found = self._d2_dim_annotations(views, dimension_name)
            if not found:
                return self._result(False, f"hide_show_dimension: quota '{dimension_name}' non trovata (anche fra le nascoste)",
                                    SwErrors.swSelectionError)
            if len(found) > 1:
                return self._result(False, f"hide_show_dimension: '{dimension_name}' e' ambiguo: {[f[2] for f in found]}; "
                                           "usa il nome completo", SwErrors.swInvalidInput)
            v, an, full = found[0]
            want = 1 if visible else 3
            an.Visible = want
            again = self._d2_dim_annotations([v], full)
            got = int(again[0][1].Visible) if again else None
            listed = any(str(d.GetDimension2(0).FullName) == full for d in self._display_dims(v))
            data = {"dimension": full, "view": self._com(v, "GetName2"), "visibility": got, "listed_as_visible": listed}
            if got != want or listed != bool(visible):
                return self._result(False, f"hide_show_dimension: visibilita' non applicata (riletta {got})", SwErrors.swFeatureError, data)
            return self._result(True, f"Quota {full} {'mostrata' if visible else 'nascosta'}", SwErrors.swSuccess, data)
        except Exception as e:
            return self._result(False, f"hide_show_dimension: {e}", SwErrors.swGenericError)


    # ------------------------------------------------------------------ 8. Tabelle, Distinte Base e Pallinatura
    def add_revision_table(self, x: float = 400.0, y: float = 280.0, revision: str = "A",
                           description: str = "Initial Release", author: str = None, unit: str = None) -> Dict:
        """Inserisce una tabella delle revisioni della tavola con indice, descrizione, data e autore."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            xm = self._mmu(x, unit)
            ym = self._mmu(y, unit)
            sheet = self._com(doc, "GetCurrentSheet")
            tabella = sheet.InsertRevisionTable2(True, xm, ym, 1, "", 1, True) if sheet else None
            if not tabella:
                return self._result(False, "add_revision_table: tabella revisioni non inserita", SwErrors.swFeatureError)
            rev_id = tabella.AddRevision(str(revision))
            read = str(tabella.GetRevisionForId(rev_id) or "")
            self._drw_rebuild(doc)
            if read != str(revision):
                return self._result(False, f"add_revision_table: riga di revisione '{revision}' non scritta (letta '{read}')", SwErrors.swFeatureError)
            return self._result(
                True, f"Tabella revisioni inserita a ({x}, {y}) mm con la revisione '{revision}' (descrizione e autore non scritti).",
                SwErrors.swSuccess,
                {"x": x, "y": y, "revision": revision, "revision_row": read, "description": description, "author": author,
                 "ignored_params": ["description", "author"]}
            )
        except Exception as e:
            return self._result(False, f"add_revision_table: {e}", SwErrors.swGenericError)


    def add_general_table(self, rows: int = 3, columns: int = 3, x: float = 100.0, y: float = 100.0,
                          data: list = None, title: str = None, unit: str = None) -> Dict:
        """Inserisce una tabella generica a griglia con numero di righe e colonne e dati testuali."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            r_cnt = max(1, int(rows))
            c_cnt = max(1, int(columns))
            xm = self._mmu(x, unit)
            ym = self._mmu(y, unit)
            tabella = doc.InsertTableAnnotation2(False, xm, ym, 1, "", r_cnt, c_cnt)
            if not tabella:
                return self._result(False, "add_general_table: tabella non inserita", SwErrors.swFeatureError)
            self._drw_rebuild(doc)
            ignored = [n for n, v in (("data", data), ("title", title)) if v is not None]
            return self._result(
                True, f"Tabella generica {r_cnt}x{c_cnt} inserita a ({x}, {y}) mm.",
                SwErrors.swSuccess, {"rows": r_cnt, "columns": c_cnt, "x": x, "y": y, "ignored_params": ignored}
            )
        except Exception as e:
            return self._result(False, f"add_general_table: {e}", SwErrors.swGenericError)


    def create_drawing_layer(self, layer_name: str, color_rgb: list = None, line_style: str = "solid",
                             line_weight: float = 0.25) -> Dict:
        """Crea un livello CAD (Layer) specificando nome, colore, stile e spessore di linea."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            color_int = 0
            if color_rgb is not None:
                if len(color_rgb) != 3:
                    return self._result(False, "create_drawing_layer: color_rgb deve avere 3 valori (R, G, B)", SwErrors.swInvalidInput)
                r, g, b = [int(v) & 0xFF for v in color_rgb]
                color_int = r | (g << 8) | (b << 16)
            lm = self._com(doc, "GetLayerManager")
            if not lm:
                return self._result(False, "create_drawing_layer: gestore livelli non disponibile", SwErrors.swFeatureError)
            lm.AddLayer(str(layer_name), "", color_int, 0, 0)
            layer = lm.GetLayer(str(layer_name))
            if not layer:
                return self._result(False, f"create_drawing_layer: livello '{layer_name}' non creato", SwErrors.swFeatureError)
            read = int(self._com(layer, "Color"))
            if read != color_int:
                return self._result(False, f"create_drawing_layer: colore del livello non applicato (letto {read}, atteso {color_int})", SwErrors.swFeatureError)
            return self._result(
                True, f"Livello CAD (Layer) '{layer_name}' creato con successo.",
                SwErrors.swSuccess,
                {"layer_name": layer_name, "color": color_rgb, "color_read": read, "ignored_params": ["line_style", "line_weight"]}
            )
        except Exception as e:
            return self._result(False, f"create_drawing_layer: {e}", SwErrors.swGenericError)


    # ------------------------------------------------------------------ 10. Audit ed Esportazione
    @keeps_old_file
    def export_pdf_layers(self, filepath: str, include_layers: list = None, overwrite: bool = False) -> Dict:
        """Esporta la tavola in un file PDF vettoriale preservando i layer CAD separati."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            path = os.path.abspath(filepath)
            if os.path.exists(path) and not overwrite:
                return self._result(False, f"Rifiutato: il file esiste gia' ({path}) e overwrite=False", SwErrors.swFileAlreadyExists)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            set_aside(self, path)            # il file vecchio torna al suo posto se l'export non riesce
            ok, _e, _w = self._save_as(doc, path)
            if not ok:
                return self._result(False, f"export_pdf_layers: esportazione PDF non riuscita ({path})", SwErrors.swExportError)
            if not (os.path.isfile(path) and os.path.getsize(path) > 0):
                return self._result(False, f"export_pdf_layers: file PDF non scritto ({path})", SwErrors.swExportError)
            ignored = ["include_layers"] if include_layers else []
            return self._result(
                True, f"Tavola esportata in PDF in {path}.",
                SwErrors.swSuccess, {"filepath": path, "ignored_params": ignored}
            )
        except Exception as e:
            return self._result(False, f"export_pdf_layers: {e}", SwErrors.swGenericError)
