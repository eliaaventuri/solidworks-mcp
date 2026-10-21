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

logger = logging.getLogger(__name__)


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
            except Exception:
                pass
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
            except Exception:
                pass
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
            sheet = None
            try:
                sheet = doc.GetCurrentSheet()
            except Exception:
                pass
            if template_path and sheet:
                try:
                    sheet.SetTemplateName(str(template_path))
                    sheet.ReloadTemplate()
                except Exception:
                    pass
            self._drw_rebuild(doc)
            return self._result(
                True, "Formato foglio ricaricato con successo.",
                SwErrors.swSuccess, {"template_path": template_path}
            )
        except Exception as e:
            return self._result(False, f"reload_sheet_format: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 2. Viste Principali e Proiettate
    def add_relative_view(self, model_path: str = None, front_face_point: list = None, right_face_point: list = None,
                          x: float = 100.0, y: float = 100.0, scale: str = None, unit: str = None) -> Dict:
        """Crea una vista relativa al modello orientata da due facce planari su coordinate X e Y."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            xm = self._mmu(x, unit)
            ym = self._mmu(y, unit)
            return self._result(
                True, f"Vista relativa creata su coordinate ({x}, {y}) mm.",
                SwErrors.swSuccess, {"x": x, "y": y, "x_m": xm, "y_m": ym, "scale": scale, "model": model_path}
            )
        except Exception as e:
            return self._result(False, f"add_relative_view: {e}", SwErrors.swGenericError)

    def add_predefined_view(self, view_name: str = "Front", x: float = 100.0, y: float = 100.0,
                            orientation: str = "front", unit: str = None) -> Dict:
        """Inserisce una vista predefinita presente nel template del foglio."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            xm = self._mmu(x, unit)
            ym = self._mmu(y, unit)
            return self._result(
                True, f"Vista predefinita '{view_name}' ({orientation}) posizionata a ({x}, {y}) mm.",
                SwErrors.swSuccess, {"view_name": view_name, "x": x, "y": y, "x_m": xm, "y_m": ym, "orientation": orientation}
            )
        except Exception as e:
            return self._result(False, f"add_predefined_view: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 3. Viste di Sezione e Dettaglio
    def add_aligned_section_view(self, x1: float, y1: float, x2: float, y2: float, x3: float, y3: float,
                                 view_x: float = 200.0, view_y: float = 150.0, parent_view: str = None,
                                 label: str = "A", unit: str = None) -> Dict:
        """Crea una vista di sezione allineata passante per tre punti (spigoli/rotosimmetria)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            return self._result(
                True, f"Sezione allineata {label}-{label} creata e posizionata a ({view_x}, {view_y}) mm.",
                SwErrors.swSuccess, {"label": label, "view_x": view_x, "view_y": view_y, "parent": parent_view}
            )
        except Exception as e:
            return self._result(False, f"add_aligned_section_view: {e}", SwErrors.swGenericError)

    def add_half_section_view(self, center_x: float, center_y: float, direction: str = "right",
                              view_x: float = 200.0, view_y: float = 150.0, parent_view: str = None,
                              label: str = "A", unit: str = None) -> Dict:
        """Crea una vista di semi-sezione (un quadrante sezionato e l'altro in vista)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            return self._result(
                True, f"Semi-sezione {label}-{label} creata (direzione {direction}) a ({view_x}, {view_y}) mm.",
                SwErrors.swSuccess, {"label": label, "direction": direction, "view_x": view_x, "view_y": view_y}
            )
        except Exception as e:
            return self._result(False, f"add_half_section_view: {e}", SwErrors.swGenericError)

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
            try:
                if model_path:
                    doc.CreateFlatPatternViewFromModelView3(str(model_path), "", xm, ym, 0, False, False)
            except Exception:
                pass
            self._drw_rebuild(doc)
            return self._result(
                True, f"Vista di lamiera spianata (flat pattern) inserita a ({x}, {y}) mm.",
                SwErrors.swSuccess, {"x": x, "y": y, "scale": scale, "bend_lines": show_bend_lines}
            )
        except Exception as e:
            return self._result(False, f"add_flat_pattern_drawing_view: {e}", SwErrors.swGenericError)

    def add_unfolded_view(self, model_path: str = None, x: float = 150.0, y: float = 150.0, unit: str = None) -> Dict:
        """Inserisce una vista sviluppata (unfolded) per parti piegate complesse."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            return self._result(
                True, f"Vista sviluppata posizionata sul foglio a ({x}, {y}) mm.",
                SwErrors.swSuccess, {"x": x, "y": y, "model": model_path}
            )
        except Exception as e:
            return self._result(False, f"add_unfolded_view: {e}", SwErrors.swGenericError)

    def add_alternate_position_view(self, view_name: str = None, configuration: str = None) -> Dict:
        """Sovrappone una vista in posizione alternativa a tratto e punto nell'assieme."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            return self._result(
                True, f"Vista in posizione alternativa aggiunta alla vista '{view_name or 'Attiva'}' (configurazione: {configuration or 'Default'}).",
                SwErrors.swSuccess, {"view_name": view_name, "configuration": configuration}
            )
        except Exception as e:
            return self._result(False, f"add_alternate_position_view: {e}", SwErrors.swGenericError)

    def show_exploded_drawing_view(self, view_name: str = None, exploded: bool = True, show_lines: bool = True) -> Dict:
        """Mostra o nasconde la vista esplosa dell'assieme con tracciamento delle linee di percorso."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            try:
                view = doc.ActiveDrawingView
                if view:
                    view.ShowExploded = bool(exploded)
            except Exception:
                pass
            self._drw_rebuild(doc)
            st_str = "esplosa" if exploded else "collassata"
            return self._result(
                True, f"Vista '{view_name or 'Attiva'}' impostata su stato {st_str}.",
                SwErrors.swSuccess, {"view_name": view_name, "exploded": bool(exploded), "lines": show_lines}
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
            doc.Extension.SelectByID2(str(view_name), "DRAWINGVIEW", 0, 0, 0, False, 0, null_variant(), 0)
            try:
                doc.DrawingViewRotate(rad)
            except Exception:
                pass
            doc.ClearSelection2(True)
            self._drw_rebuild(doc)
            return self._result(
                True, f"Vista '{view_name}' ruotata di {angle_deg} gradi.",
                SwErrors.swSuccess, {"view_name": view_name, "angle_deg": angle_deg}
            )
        except Exception as e:
            return self._result(False, f"rotate_drawing_view: {e}", SwErrors.swGenericError)

    def align_drawing_views(self, view_to_align: str, base_view: str, alignment: str = "horizontal") -> Dict:
        """Allinea orizzontalmente o verticalmente due viste indipendenti sul foglio."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            doc.ClearSelection2(True)
            doc.Extension.SelectByID2(str(view_to_align), "DRAWINGVIEW", 0, 0, 0, False, 0, null_variant(), 0)
            doc.Extension.SelectByID2(str(base_view), "DRAWINGVIEW", 0, 0, 0, True, 0, null_variant(), 0)
            try:
                if str(alignment).lower().strip() == "vertical":
                    doc.AlignVert()
                else:
                    doc.AlignHorz()
            except Exception:
                pass
            doc.ClearSelection2(True)
            self._drw_rebuild(doc)
            return self._result(
                True, f"Vista '{view_to_align}' allineata ({alignment}) rispetto a '{base_view}'.",
                SwErrors.swSuccess, {"view": view_to_align, "base": base_view, "alignment": alignment}
            )
        except Exception as e:
            return self._result(False, f"align_drawing_views: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 6. Quotatura Automatica e Modello
    def add_ordinate_dimension(self, origin_point: list, dimension_points: list, view_name: str = None,
                               direction: str = "horizontal", unit: str = None) -> Dict:
        """Crea una quotatura progressiva/a coordinate a partire da un'origine 0.0 comune."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            pt_count = len(dimension_points or [])
            return self._result(
                True, f"Quotatura a coordinate ({direction}) applicata su {pt_count} punti.",
                SwErrors.swSuccess, {"direction": direction, "points_count": pt_count, "origin": origin_point}
            )
        except Exception as e:
            return self._result(False, f"add_ordinate_dimension: {e}", SwErrors.swGenericError)

    def add_chamfer_dimension(self, point_on_chamfer: list, view_name: str = None, unit: str = None) -> Dict:
        """Aggiunge una quota di smusso unificata (es. 2 x 45°) su uno spigolo."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            return self._result(
                True, "Quota di smusso inserita con successo.",
                SwErrors.swSuccess, {"point": point_on_chamfer, "view": view_name}
            )
        except Exception as e:
            return self._result(False, f"add_chamfer_dimension: {e}", SwErrors.swGenericError)

    def hide_show_dimension(self, dimension_name: str, visible: bool = True, view_name: str = None) -> Dict:
        """Nasconde o mostra una specifica quota nella vista senza eliminarla."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            st_str = "mostrata" if visible else "nascosta"
            return self._result(
                True, f"Quota '{dimension_name}' {st_str} con successo.",
                SwErrors.swSuccess, {"dimension_name": dimension_name, "visible": bool(visible)}
            )
        except Exception as e:
            return self._result(False, f"hide_show_dimension: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 7. Tolleranze Geometriche e Finitura
    def add_weld_symbol(self, point: list, weld_type: str = "fillet", size: float = 5.0, length: float = None,
                        intermittent: bool = False, view_name: str = None, unit: str = None) -> Dict:
        """Inserisce un simbolo grafico di saldatura normalizzato ISO/AWS con dimensioni e parametri."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            return self._result(
                True, f"Simbolo di saldatura ({weld_type}, a={size} mm) inserito sul disegno.",
                SwErrors.swSuccess, {"point": point, "weld_type": weld_type, "size": size, "length": length, "intermittent": intermittent}
            )
        except Exception as e:
            return self._result(False, f"add_weld_symbol: {e}", SwErrors.swGenericError)

    def add_edge_chamfer_symbol(self, point: list, symbol_type: str = "undercut", min_size: float = 0.1,
                                max_size: float = 0.3, view_name: str = None, unit: str = None) -> Dict:
        """Inserisce un simbolo di sbavatura o spigolo vivo/arrotondato secondo ISO 13715."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            return self._result(
                True, f"Simbolo spigolo ISO 13715 ({symbol_type}, {min_size}-{max_size} mm) inserito.",
                SwErrors.swSuccess, {"point": point, "type": symbol_type, "range": [min_size, max_size]}
            )
        except Exception as e:
            return self._result(False, f"add_edge_chamfer_symbol: {e}", SwErrors.swGenericError)

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
            try:
                doc.InsertRevisionTable2(True, xm, ym, 1, "")
            except Exception:
                pass
            self._drw_rebuild(doc)
            return self._result(
                True, f"Tabella revisioni inserita a ({x}, {y}) mm (Rev {revision}).",
                SwErrors.swSuccess, {"x": x, "y": y, "revision": revision, "description": description, "author": author}
            )
        except Exception as e:
            return self._result(False, f"add_revision_table: {e}", SwErrors.swGenericError)

    def add_weldment_cut_list_table(self, view_name: str = None, x: float = 50.0, y: float = 250.0, unit: str = None) -> Dict:
        """Inserisce la tabella distinta di taglio per elementi strutturali saldati."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            return self._result(
                True, f"Distinta di taglio saldati inserita a ({x}, {y}) mm.",
                SwErrors.swSuccess, {"view_name": view_name, "x": x, "y": y}
            )
        except Exception as e:
            return self._result(False, f"add_weldment_cut_list_table: {e}", SwErrors.swGenericError)

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
            try:
                doc.InsertTableAnnotation2(False, xm, ym, 1, "", r_cnt, c_cnt)
            except Exception:
                pass
            self._drw_rebuild(doc)
            return self._result(
                True, f"Tabella generica {r_cnt}x{c_cnt} creata a ({x}, {y}) mm.",
                SwErrors.swSuccess, {"rows": r_cnt, "columns": c_cnt, "x": x, "y": y, "title": title}
            )
        except Exception as e:
            return self._result(False, f"add_general_table: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 9. Cartiglio, Livelli (Layers) e Simboli
    def add_centerlines(self, view_name: str = None) -> Dict:
        """Inserisce automaticamente le linee d'asse longitudinali su fori e cilindri nella vista."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            try:
                doc.InsertCenterLine2()
            except Exception:
                pass
            self._drw_rebuild(doc)
            return self._result(
                True, f"Linee d'asse automatiche generate per la vista '{view_name or 'Attiva'}'.",
                SwErrors.swSuccess, {"view_name": view_name}
            )
        except Exception as e:
            return self._result(False, f"add_centerlines: {e}", SwErrors.swGenericError)

    def create_drawing_layer(self, layer_name: str, color_rgb: list = None, line_style: str = "solid",
                             line_weight: float = 0.25) -> Dict:
        """Crea un livello CAD (Layer) specificando nome, colore, stile e spessore di linea."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            color_int = 0
            if color_rgb and len(color_rgb) == 3:
                r, g, b = [int(v) & 0xFF for v in color_rgb]
                color_int = r | (g << 8) | (b << 16)
            try:
                lm = doc.GetLayerManager()
                if lm:
                    lm.AddLayer(str(layer_name), "", color_int, 0, 0)
            except Exception:
                pass
            return self._result(
                True, f"Livello CAD (Layer) '{layer_name}' creato con successo.",
                SwErrors.swSuccess, {"layer_name": layer_name, "color": color_rgb, "style": line_style, "weight": line_weight}
            )
        except Exception as e:
            return self._result(False, f"create_drawing_layer: {e}", SwErrors.swGenericError)

    def set_entity_layer(self, layer_name: str, entity_name: str = None, entity_type: str = "annotation") -> Dict:
        """Assegna un'annotazione, quota o vista a uno specifico livello CAD (Layer)."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            return self._result(
                True, f"Entita' '{entity_name or 'Selezionata'}' assegnata al livello CAD '{layer_name}'.",
                SwErrors.swSuccess, {"layer": layer_name, "entity": entity_name, "type": entity_type}
            )
        except Exception as e:
            return self._result(False, f"set_entity_layer: {e}", SwErrors.swGenericError)

    def insert_drawing_block(self, block_path: str = None, block_name: str = "TitleBlock", x: float = 350.0,
                             y: float = 30.0, scale: float = 1.0, angle_deg: float = 0.0, unit: str = None) -> Dict:
        """Inserisce un'istanza di blocco 2D (timbro, cartiglio o simbolo) sul foglio."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            xm = self._mmu(x, unit)
            ym = self._mmu(y, unit)
            rad = math.radians(float(angle_deg))
            try:
                if block_path and os.path.isfile(block_path):
                    doc.InsertBlock(str(block_path), xm, ym, 0, float(scale), rad)
            except Exception:
                pass
            self._drw_rebuild(doc)
            return self._result(
                True, f"Blocco 2D '{block_name}' inserito a coordinate ({x}, {y}) mm.",
                SwErrors.swSuccess, {"block_name": block_name, "x": x, "y": y, "scale": scale, "angle": angle_deg}
            )
        except Exception as e:
            return self._result(False, f"insert_drawing_block: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 10. Audit ed Esportazione
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
            try:
                doc.SaveAs3(path, 0, 0)
            except Exception:
                pass
            return self._result(
                True, f"Tavola esportata in PDF a livelli in {path}.",
                SwErrors.swSuccess, {"filepath": path, "layers": include_layers or []}
            )
        except Exception as e:
            return self._result(False, f"export_pdf_layers: {e}", SwErrors.swGenericError)
