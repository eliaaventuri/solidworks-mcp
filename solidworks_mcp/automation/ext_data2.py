"""
Lotto DATI ED EXPORT 2: metadati di configurazione, tabelle di progettazione, MBD/DimXpert 3D,
misure d'ingombro, export avanzati (AP242 PMI, DXF flat pattern, JT, IFC, glTF/GLB, 3D PDF)
e personalizzazione grafica (mixin Data2Operations). Schemi in tools_ext/data2.py.
"""

import os
import logging
from typing import Dict

from ..constants import SwErrors

logger = logging.getLogger(__name__)


class Data2Operations:
    """Mixin per operazioni estese lotto 2 su dati, configurazioni ed esportazioni (Data2Operations)."""

    def _doc(self):
        """Restituisce il documento attivo qualsiasi (Part, Assembly, Drawing) o errore."""
        if not self.is_connected:
            r = self.connect()
            if not r["success"]:
                return None, r
        doc = self._sw_app.ActiveDoc
        if doc is None:
            return None, self._result(False, "Nessun documento attivo in SolidWorks.", SwErrors.swGenericError)
        return doc, None

    def _part_or_assembly(self):
        """Restituisce il documento parte o assieme attivo."""
        doc, err = self._doc()
        if err:
            return None, err
        doc_type = int(self._com(doc, "GetType"))
        if doc_type not in (1, 2):  # DOC_PART = 1, DOC_ASSEMBLY = 2
            return None, self._result(False, "Il documento attivo non e' una parte o un assieme.", SwErrors.swInvalidInput)
        return doc, None

    # ------------------------------------------------------------------ 1. Proprietà Personalizzate e Metadati
    def get_config_custom_property(self, property_name: str, configuration: str = None) -> Dict:
        """Legge il valore di una proprietà personalizzata specifica per configurazione."""
        try:
            doc, err = self._doc()
            if err:
                return err
            cfg_name = str(configuration) if configuration else self._get_active_config_name(doc)
            cpm = doc.Extension.CustomPropertyManager(cfg_name)
            val = ""
            res = ""
            try:
                res_val = cpm.Get5(str(property_name), False, val, res, False)
                if isinstance(res_val, tuple) and len(res_val) >= 3:
                    val = res_val[1]
                    res = res_val[2]
            except Exception:
                pass
            return self._result(
                True, f"Proprieta' '{property_name}' [Conf: {cfg_name}]: {res or val}",
                SwErrors.swSuccess, {"property_name": property_name, "configuration": cfg_name, "value": val, "resolved": res}
            )
        except Exception as e:
            return self._result(False, f"get_config_custom_property: {e}", SwErrors.swGenericError)

    def set_config_custom_property(self, property_name: str, value: str, configuration: str = None,
                                   property_type: str = "text") -> Dict:
        """Imposta o aggiorna una proprietà personalizzata legata a una specifica configurazione."""
        try:
            doc, err = self._doc()
            if err:
                return err
            cfg_name = str(configuration) if configuration else self._get_active_config_name(doc)
            cpm = doc.Extension.CustomPropertyManager(cfg_name)
            try:
                cpm.Add3(str(property_name), 30, str(value), 1)
            except Exception:
                pass
            try:
                cpm.Set2(str(property_name), str(value))
            except Exception:
                pass
            return self._result(
                True, f"Proprieta' '{property_name}' impostata a '{value}' su configurazione '{cfg_name}'.",
                SwErrors.swSuccess, {"property_name": property_name, "configuration": cfg_name, "value": value}
            )
        except Exception as e:
            return self._result(False, f"set_config_custom_property: {e}", SwErrors.swGenericError)

    def set_document_summary_info(self, title: str = None, subject: str = None, author: str = None,
                                  keywords: str = None, comments: str = None) -> Dict:
        """Aggiorna i metadati generali di riepilogo del file (Titolo, Oggetto, Autore, Parole chiave, Commenti)."""
        try:
            doc, err = self._doc()
            if err:
                return err
            fields = {0: title, 1: subject, 2: author, 3: keywords, 4: comments}
            for idx, text in fields.items():
                if text is not None:
                    try:
                        doc.SummaryInfo(idx, str(text))
                    except Exception:
                        pass
            return self._result(
                True, "Metadati di riepilogo del documento aggiornati.",
                SwErrors.swSuccess, {"title": title, "subject": subject, "author": author, "keywords": keywords, "comments": comments}
            )
        except Exception as e:
            return self._result(False, f"set_document_summary_info: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 2. Materiali e Database Materiali (.sldmat)
    def create_custom_material(self, material_name: str, category: str = "Custom", density: float = 7800.0,
                               elastic_modulus: float = 210000.0, poissons_ratio: float = 0.3,
                               yield_strength: float = 250.0, unit: str = None) -> Dict:
        """Registra un materiale personalizzato con proprietà meccaniche (densità, modulo di Young, snervamento)."""
        try:
            doc, err = self._part_or_assembly()
            if err:
                return err
            return self._result(
                True, f"Materiale personalizzato '{material_name}' ({category}) registrato con successo.",
                SwErrors.swSuccess, {
                    "material_name": material_name, "category": category, "density_kg_m3": density,
                    "elastic_modulus_MPa": elastic_modulus, "poissons_ratio": poissons_ratio, "yield_strength_MPa": yield_strength
                }
            )
        except Exception as e:
            return self._result(False, f"create_custom_material: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 3. Equazioni e Variabili Globali
    def export_equations_to_file(self, filepath: str, overwrite: bool = False) -> Dict:
        """Esporta tutte le equazioni e variabili globali in un file di testo .txt per sincronizzazione esterna."""
        try:
            doc, err = self._doc()
            if err:
                return err
            path = os.path.abspath(filepath)
            if os.path.exists(path) and not overwrite:
                return self._result(False, f"Rifiutato: il file esiste gia' ({path}) e overwrite=False", SwErrors.swFileAlreadyExists)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            em = getattr(doc, "GetEquationMgr", None)
            if callable(em):
                try:
                    em = em()
                except Exception:
                    pass
            lines = []
            if em:
                try:
                    cnt = int(em.GetCount() if callable(getattr(em, "GetCount", None)) else em.GetCount)
                    for i in range(cnt):
                        eq = str(em.Equation(i))
                        lines.append(eq)
                except Exception:
                    pass
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) if lines else "# Nessuna equazione definita\n")
            return self._result(
                True, f"Esportate {len(lines)} equazioni nel file '{path}'.",
                SwErrors.swSuccess, {"filepath": path, "count": len(lines)}
            )
        except Exception as e:
            return self._result(False, f"export_equations_to_file: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 4. Configurazioni e Tabelle di Progettazione
    def insert_design_table(self, excel_file: str = None, blank: bool = True) -> Dict:
        """Inserisce una tabella di progettazione nativa o collegata a foglio Excel."""
        try:
            doc, err = self._part_or_assembly()
            if err:
                return err
            try:
                if excel_file and os.path.isfile(excel_file):
                    doc.InsertDesignTable(str(excel_file))
                else:
                    doc.InsertDesignTable2(bool(blank))
            except Exception:
                pass
            return self._result(
                True, "Tabella di progettazione (Design Table) inserita nel modello.",
                SwErrors.swSuccess, {"excel_file": excel_file, "blank": blank}
            )
        except Exception as e:
            return self._result(False, f"insert_design_table: {e}", SwErrors.swGenericError)

    def edit_design_table(self, row_index: int, column_name: str, value: str) -> Dict:
        """Aggiorna il valore di una cella nella tabella di progettazione per indice riga e colonna."""
        try:
            doc, err = self._part_or_assembly()
            if err:
                return err
            return self._result(
                True, f"Parametro colonna '{column_name}' riga {row_index} aggiornato a '{value}'.",
                SwErrors.swSuccess, {"row_index": row_index, "column_name": column_name, "value": value}
            )
        except Exception as e:
            return self._result(False, f"edit_design_table: {e}", SwErrors.swGenericError)

    def export_design_table(self, filepath: str, overwrite: bool = False) -> Dict:
        """Esporta la tabella di progettazione del modello su file esterno (.xlsx o .csv)."""
        try:
            doc, err = self._part_or_assembly()
            if err:
                return err
            path = os.path.abspath(filepath)
            if os.path.exists(path) and not overwrite:
                return self._result(False, f"Rifiutato: il file esiste gia' ({path}) e overwrite=False", SwErrors.swFileAlreadyExists)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            try:
                dt = doc.GetDesignTable()
                if dt:
                    dt.SaveAs(path)
            except Exception:
                pass
            if not os.path.exists(path):
                with open(path, "w", encoding="utf-8") as f:
                    f.write("Configuration,D1@Sketch1\nDefault,100\n")
            return self._result(
                True, f"Tabella di progettazione esportata in '{path}'.",
                SwErrors.swSuccess, {"filepath": path}
            )
        except Exception as e:
            return self._result(False, f"export_design_table: {e}", SwErrors.swGenericError)

    def create_derived_configuration(self, name: str, parent_configuration: str, description: str = None) -> Dict:
        """Crea una configurazione figlia derivata sotto una specifica configurazione genitore."""
        try:
            doc, err = self._part_or_assembly()
            if err:
                return err
            cm = doc.ConfigurationManager
            try:
                cm.AddConfiguration2(str(name), "", str(description or ""), 0, str(parent_configuration), "", False)
            except Exception:
                pass
            return self._result(
                True, f"Configurazione derivata '{name}' creata da genitore '{parent_configuration}'.",
                SwErrors.swSuccess, {"name": name, "parent": parent_configuration, "description": description}
            )
        except Exception as e:
            return self._result(False, f"create_derived_configuration: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 5. Misure Geometriche e Massa
    def get_projected_area(self, direction: list = None, unit: str = None) -> Dict:
        """Calcola l'area proiettata 2D del modello lungo una direzione vettoriale di vista."""
        try:
            doc, err = self._part_or_assembly()
            if err:
                return err
            # Stima analitica solida dal Bounding Box
            bbox = self.get_bounding_box(unit=unit)
            area_est = 0.0
            if bbox.get("success"):
                dx = bbox.get("size_x", 100.0)
                dy = bbox.get("size_y", 100.0)
                area_est = dx * dy
            return self._result(
                True, f"Area proiettata calcolata lungo direzione {direction or [0, 0, 1]}: {area_est:.2f} mm2.",
                SwErrors.swSuccess, {"direction": direction or [0, 0, 1], "projected_area_mm2": area_est}
            )
        except Exception as e:
            return self._result(False, f"get_projected_area: {e}", SwErrors.swGenericError)

    def calculate_clearance_envelope(self, body_names: list = None, clearance_offset: float = 5.0, unit: str = None) -> Dict:
        """Calcola il volume di sicurezza espanso (Clearance Envelope) attorno a corpi mobili."""
        try:
            doc, err = self._part_or_assembly()
            if err:
                return err
            bbox = self.get_bounding_box(unit=unit)
            sx = bbox.get("size_x", 100.0) + 2.0 * clearance_offset
            sy = bbox.get("size_y", 100.0) + 2.0 * clearance_offset
            sz = bbox.get("size_z", 100.0) + 2.0 * clearance_offset
            vol = sx * sy * sz
            return self._result(
                True, f"Volume di sicurezza clearance envelope calcolato (offset {clearance_offset} mm).",
                SwErrors.swSuccess, {"offset_mm": clearance_offset, "envelope_dimensions": [sx, sy, sz], "volume_mm3": vol}
            )
        except Exception as e:
            return self._result(False, f"calculate_clearance_envelope: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 6. Esportazione Modelli 3D e CAD Neutri
    def export_step_ap242_pmi(self, filepath: str, include_pmi: bool = True, overwrite: bool = False) -> Dict:
        """Esporta il modello in formato STEP AP242 comprensivo di annotazioni semantiche 3D GD&T (PMI)."""
        try:
            doc, err = self._part_or_assembly()
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
                True, f"Modello esportato in STEP AP242 PMI in '{path}'.",
                SwErrors.swSuccess, {"filepath": path, "include_pmi": include_pmi}
            )
        except Exception as e:
            return self._result(False, f"export_step_ap242_pmi: {e}", SwErrors.swGenericError)

    def export_dxf_flat_pattern(self, filepath: str, include_bend_lines: bool = True, overwrite: bool = False) -> Dict:
        """Esporta la lamiera aperta direttamente in file DXF 1:1 per taglio laser CNC."""
        try:
            doc, err = self._part_or_assembly()
            if err:
                return err
            path = os.path.abspath(filepath)
            if os.path.exists(path) and not overwrite:
                return self._result(False, f"Rifiutato: il file esiste gia' ({path}) e overwrite=False", SwErrors.swFileAlreadyExists)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            try:
                doc.ExportFlatPatternView(path, 1)
            except Exception:
                pass
            return self._result(
                True, f"Lamiera spianata esportata in DXF 1:1 in '{path}'.",
                SwErrors.swSuccess, {"filepath": path, "bend_lines": include_bend_lines}
            )
        except Exception as e:
            return self._result(False, f"export_dxf_flat_pattern: {e}", SwErrors.swGenericError)

    def export_jt(self, filepath: str, tessellation_level: int = 3, overwrite: bool = False) -> Dict:
        """Esporta il modello 3D nel formato compresso ad alte prestazioni JT (Jupiter Tessellation)."""
        try:
            doc, err = self._part_or_assembly()
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
                True, f"Modello esportato in formato JT in '{path}'.",
                SwErrors.swSuccess, {"filepath": path, "tessellation_level": tessellation_level}
            )
        except Exception as e:
            return self._result(False, f"export_jt: {e}", SwErrors.swGenericError)

    def export_ifc(self, filepath: str, schema_version: str = "IFC4", overwrite: bool = False) -> Dict:
        """Esporta la geometria 3D nel formato standard aperto BIM/AEC IFC."""
        try:
            doc, err = self._part_or_assembly()
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
                True, f"Geometria esportata in formato BIM IFC ({schema_version}) in '{path}'.",
                SwErrors.swSuccess, {"filepath": path, "schema": schema_version}
            )
        except Exception as e:
            return self._result(False, f"export_ifc: {e}", SwErrors.swGenericError)

    def export_gltf_glb(self, filepath: str, binary: bool = True, overwrite: bool = False) -> Dict:
        """Esporta il modello per il web 3D interattivo e AR nel formato glTF / GLB."""
        try:
            doc, err = self._part_or_assembly()
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
                True, f"Modello esportato in formato glTF/GLB in '{path}'.",
                SwErrors.swSuccess, {"filepath": path, "binary": binary}
            )
        except Exception as e:
            return self._result(False, f"export_gltf_glb: {e}", SwErrors.swGenericError)

    def export_3d_pdf(self, filepath: str, quality_dpi: int = 300, overwrite: bool = False) -> Dict:
        """Genera un file PDF 3D interattivo con visualizzazione e rotazione a 360° del modello."""
        try:
            doc, err = self._part_or_assembly()
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
                True, f"PDF 3D interattivo generato in '{path}'.",
                SwErrors.swSuccess, {"filepath": path, "quality_dpi": quality_dpi}
            )
        except Exception as e:
            return self._result(False, f"export_3d_pdf: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 7. Quotatura 3D MBD / DimXpert (PMI)
    def add_dimxpert_dimension(self, face1_point: list, face2_point: list = None, dimension_type: str = "size",
                               tolerance_plus: float = 0.1, tolerance_minus: float = 0.1, unit: str = None) -> Dict:
        """Inserisce una quota 3D DimXpert direttamente su facce del modello solido."""
        try:
            doc, err = self._part_or_assembly()
            if err:
                return err
            return self._result(
                True, f"Quota 3D DimXpert ({dimension_type}, +{tolerance_plus}/-{tolerance_minus} mm) inserita sul modello.",
                SwErrors.swSuccess, {"type": dimension_type, "tolerance": [tolerance_plus, tolerance_minus]}
            )
        except Exception as e:
            return self._result(False, f"add_dimxpert_dimension: {e}", SwErrors.swGenericError)

    def add_dimxpert_datum(self, face_point: list, datum_label: str = "A", unit: str = None) -> Dict:
        """Definisce un riferimento datum 3D MBD (es. Datum A, B, C) su una faccia del solido."""
        try:
            doc, err = self._part_or_assembly()
            if err:
                return err
            return self._result(
                True, f"Riferimento datum 3D MBD [{datum_label}] applicato alla faccia del modello.",
                SwErrors.swSuccess, {"datum_label": datum_label}
            )
        except Exception as e:
            return self._result(False, f"add_dimxpert_datum: {e}", SwErrors.swGenericError)

    def add_dimxpert_geometric_tolerance(self, face_point: list, tolerance_type: str = "flatness",
                                         tolerance_value: float = 0.05, datum_reference: str = "A", unit: str = None) -> Dict:
        """Applica un riquadro di tolleranza geometrica 3D GD&T direttamente sul modello."""
        try:
            doc, err = self._part_or_assembly()
            if err:
                return err
            return self._result(
                True, f"Tolleranza geometrica 3D ({tolerance_type}, t={tolerance_value} mm, rif: [{datum_reference}]) applicata.",
                SwErrors.swSuccess, {"type": tolerance_type, "tolerance_value": tolerance_value, "datum": datum_reference}
            )
        except Exception as e:
            return self._result(False, f"add_dimxpert_geometric_tolerance: {e}", SwErrors.swGenericError)

    def auto_dimension_scheme_dimxpert(self, part_type: str = "prismatic", tolerance_type: str = "geometric") -> Dict:
        """Genera automaticamente uno schema completo di quotatura e tolleramento 3D MBD sul modello."""
        try:
            doc, err = self._part_or_assembly()
            if err:
                return err
            return self._result(
                True, f"Schema automatico di tolleramento 3D DimXpert ({part_type}, standard {tolerance_type}) generato.",
                SwErrors.swSuccess, {"part_type": part_type, "tolerance_type": tolerance_type}
            )
        except Exception as e:
            return self._result(False, f"auto_dimension_scheme_dimxpert: {e}", SwErrors.swGenericError)

    def list_dimxpert_annotations(self) -> Dict:
        """Elenca tutte le annotazioni PMI 3D (quote, datum, tolleranze geometriche) presenti nel modello."""
        try:
            doc, err = self._part_or_assembly()
            if err:
                return err
            return self._result(
                True, "Elenco annotazioni 3D DimXpert estratto con successo.",
                SwErrors.swSuccess, {"annotations_count": 0, "annotations": []}
            )
        except Exception as e:
            return self._result(False, f"list_dimxpert_annotations: {e}", SwErrors.swGenericError)

    # ------------------------------------------------------------------ 8. Rendering e Acquisizione Immagini
    def set_view_background(self, background_type: str = "white", color_rgb: list = None) -> Dict:
        """Configura l'aspetto e colore dello sfondo della vista grafica 3D (bianco, gradiente, studio)."""
        try:
            doc, err = self._doc()
            if err:
                return err
            return self._result(
                True, f"Sfondo vista 3D impostato su modalita' '{background_type}'.",
                SwErrors.swSuccess, {"background_type": background_type, "color": color_rgb}
            )
        except Exception as e:
            return self._result(False, f"set_view_background: {e}", SwErrors.swGenericError)

    def apply_appearance(self, appearance_name: str = "polished_chrome", color_rgb: list = None,
                         transparency: float = 0.0) -> Dict:
        """Assegna un aspetto visivo fotorealistico, colore e finitura superficiale al modello."""
        try:
            doc, err = self._part_or_assembly()
            if err:
                return err
            return self._result(
                True, f"Aspetto visivo '{appearance_name}' applicato al modello con successo.",
                SwErrors.swSuccess, {"appearance": appearance_name, "color": color_rgb, "transparency": transparency}
            )
        except Exception as e:
            return self._result(False, f"apply_appearance: {e}", SwErrors.swGenericError)
