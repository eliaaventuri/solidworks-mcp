"""
Lotto DATI ED EXPORT 2: metadati di configurazione, tabelle di progettazione, MBD/DimXpert 3D,
misure d'ingombro, export avanzati (AP242 PMI, DXF flat pattern, JT, IFC, glTF/GLB, 3D PDF)
e personalizzazione grafica (mixin Data2Operations). Schemi in tools_ext/data2.py.
"""

import os
import re
import logging
from typing import Dict

from ..constants import SwErrors
from .modeling_base import null_variant

logger = logging.getLogger(__name__)


def _byref_i4():
    import win32com.client
    import pythoncom
    return win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)


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
            cfg_name = str(configuration) if configuration else self._dx_cfg_name(doc)
            cpm = doc.Extension.CustomPropertyManager(cfg_name)
            presenti = [str(n) for n in (cpm.GetNames or ())]
            if str(property_name) not in presenti:
                return self._result(False, f"get_config_custom_property: '{property_name}' non esiste sulla configurazione "
                                           f"'{cfg_name}' (presenti: {presenti})", SwErrors.swGenericError)
            letto = self._dx_read_prop(cpm, str(property_name))
            return self._result(
                True, f"Proprieta' '{property_name}' [Conf: {cfg_name}]: {letto['resolved'] or letto['value']}",
                SwErrors.swSuccess, {"property_name": property_name, "configuration": cfg_name, "value": letto["value"],
                                     "resolved": letto["resolved"]}
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
            cfg_name = str(configuration) if configuration else self._dx_cfg_name(doc)
            cpm = doc.Extension.CustomPropertyManager(cfg_name)
            errori = []
            try:
                cpm.Add3(str(property_name), 30, str(value), 1)
            except Exception as e:
                errori.append(f"Add3: {e}")
            try:
                cpm.Set2(str(property_name), str(value))
            except Exception as e:
                errori.append(f"Set2: {e}")
            letto = self._dx_read_prop(cpm, str(property_name))
            if str(value) not in (str(letto["value"]), str(letto["resolved"])):
                return self._result(
                    False, f"set_config_custom_property: '{property_name}' non impostata su configurazione '{cfg_name}' "
                           f"(riletto '{letto['value']}'). {' | '.join(errori)}",
                    SwErrors.swGenericError, {"property_name": property_name, "configuration": cfg_name, "read_back": letto,
                                              "ignored_params": ["property_type"]}
                )
            return self._result(
                True, f"Proprieta' '{property_name}' impostata a '{value}' su configurazione '{cfg_name}' (verificata rileggendola).",
                SwErrors.swSuccess, {"property_name": property_name, "configuration": cfg_name, "value": value,
                                     "ignored_params": ["property_type"]}
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
            verificati, non_verificati = [], []
            for idx, text in fields.items():
                if text is not None:
                    try:
                        doc.SummaryInfo(idx, str(text))
                    except Exception as e:
                        return self._result(False, f"set_document_summary_info: scrittura del campo {idx} non riuscita: {e}",
                                            SwErrors.swGenericError)
                    try:
                        letto = doc.SummaryInfo(idx)
                    except Exception:
                        letto = None
                    if letto is None:
                        non_verificati.append(idx)
                    elif str(letto) != str(text):
                        return self._result(False, f"set_document_summary_info: campo {idx} riletto '{letto}' invece di '{text}'",
                                            SwErrors.swGenericError)
                    else:
                        verificati.append(idx)
            return self._result(
                True, "Metadati di riepilogo del documento aggiornati.",
                SwErrors.swSuccess, {"title": title, "subject": subject, "author": author, "keywords": keywords, "comments": comments,
                                     "verified_fields": verificati, "unverified_fields": non_verificati}
            )
        except Exception as e:
            return self._result(False, f"set_document_summary_info: {e}", SwErrors.swGenericError)


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
            try:
                em = self._com(doc, "GetEquationMgr")
            except Exception as e:
                return self._result(False, f"export_equations_to_file: gestore equazioni non disponibile: {e}", SwErrors.swGenericError)
            if em is None:
                return self._result(False, "export_equations_to_file: gestore equazioni non disponibile", SwErrors.swGenericError)
            lines = []
            try:
                cnt = int(self._com(em, "GetCount"))
                for i in range(cnt):
                    eq = str(em.Equation(i))
                    lines.append(eq)
            except Exception as e:
                return self._result(False, f"export_equations_to_file: lettura delle equazioni non riuscita: {e}", SwErrors.swGenericError)
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) if lines else "# Nessuna equazione definita\n")
            if not (os.path.isfile(path) and os.path.getsize(path) > 0):
                return self._result(False, f"export_equations_to_file: file '{path}' assente o vuoto dopo la scrittura", SwErrors.swExportError)
            return self._result(
                True, f"Esportate {len(lines)} equazioni nel file '{path}'.",
                SwErrors.swSuccess, {"filepath": path, "count": len(lines)}
            )
        except Exception as e:
            return self._result(False, f"export_equations_to_file: {e}", SwErrors.swGenericError)


    def create_derived_configuration(self, name: str, parent_configuration: str, description: str = None) -> Dict:
        """Crea una configurazione figlia derivata sotto una specifica configurazione genitore."""
        try:
            doc, err = self._part_or_assembly()
            if err:
                return err
            cm = doc.ConfigurationManager
            try:
                cm.AddConfiguration2(str(name), "", str(description or ""), 0, str(parent_configuration), "", False)
            except Exception as e:
                return self._result(False, f"create_derived_configuration: creazione di '{name}' non riuscita: {e}", SwErrors.swGenericError)
            presenti = self._dx_cfg_names(doc)
            if str(name) not in presenti:
                return self._result(False, f"create_derived_configuration: '{name}' non compare tra le configurazioni {presenti}",
                                    SwErrors.swGenericError)
            return self._result(
                True, f"Configurazione derivata '{name}' creata da genitore '{parent_configuration}'.",
                SwErrors.swSuccess, {"name": name, "parent": parent_configuration, "description": description}
            )
        except Exception as e:
            return self._result(False, f"create_derived_configuration: {e}", SwErrors.swGenericError)


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
            except Exception as e:
                return self._result(False, f"export_dxf_flat_pattern: esportazione non riuscita: {e}", SwErrors.swExportError)
            if not (os.path.isfile(path) and os.path.getsize(path) > 0):
                return self._result(False, f"export_dxf_flat_pattern: file '{path}' assente o vuoto dopo l'esportazione", SwErrors.swExportError)
            return self._result(
                True, f"Lamiera spianata esportata in DXF 1:1 in '{path}'.",
                SwErrors.swSuccess, {"filepath": path, "bend_lines": include_bend_lines, "ignored_params": ["include_bend_lines"]}
            )
        except Exception as e:
            return self._result(False, f"export_dxf_flat_pattern: {e}", SwErrors.swGenericError)


    def export_ifc(self, filepath: str, schema_version: str = "IFC2X3", overwrite: bool = False) -> Dict:
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
                ok, errori, avvisi = self._save_as(doc, path)
            except Exception as e:
                return self._result(False, f"export_ifc: esportazione non riuscita: {e}", SwErrors.swExportError)
            if not ok:
                return self._result(False, f"export_ifc: SaveAs non riuscito (errori {errori}, avvisi {avvisi})", SwErrors.swExportError)
            if not (os.path.isfile(path) and os.path.getsize(path) > 0):
                return self._result(False, f"export_ifc: file '{path}' assente o vuoto dopo l'esportazione", SwErrors.swExportError)
            with open(path, "rb") as f:
                testa = f.read(65536).decode("latin-1")
            schemi = re.findall(r"FILE_SCHEMA\s*\(\(\s*'([^']+)'", testa)
            if not testa.startswith("ISO-10303-21") or not schemi:
                return self._result(False, f"export_ifc: '{path}' non e' un IFC (intestazione STEP/FILE_SCHEMA mancante)", SwErrors.swExportError)
            if str(schema_version).upper() not in [s.upper() for s in schemi]:
                return self._result(False, f"export_ifc: richiesto {schema_version} ma il file scritto e' {schemi[0]}: SolidWorks 2026 "
                                           f"non scrive {schema_version} via API (usa schema_version=IFC2X3)", SwErrors.swExportError,
                                    {"filepath": path, "schema_written": schemi[0]})
            return self._result(
                True, f"Geometria esportata in formato BIM IFC ({schemi[0]}) in '{path}'.",
                SwErrors.swSuccess, {"filepath": path, "schema": schemi[0], "ignored_params": []}
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
            if not binary:
                return self._result(False, "export_gltf_glb: solo GLB (binary=true): con binary=false SolidWorks 2026 non scrive il "
                                           ".gltf (SaveAs riuscito ma nessun file)", SwErrors.swInvalidInput)
            try:
                ok, errori, avvisi = self._save_as(doc, path)
            except Exception as e:
                return self._result(False, f"export_gltf_glb: esportazione non riuscita: {e}", SwErrors.swExportError)
            if not ok:
                return self._result(False, f"export_gltf_glb: SaveAs non riuscito (errori {errori}, avvisi {avvisi})", SwErrors.swExportError)
            if not (os.path.isfile(path) and os.path.getsize(path) > 0):
                return self._result(False, f"export_gltf_glb: file '{path}' assente o vuoto dopo l'esportazione", SwErrors.swExportError)
            with open(path, "rb") as f:
                magia = f.read(4)
            if magia != b"glTF":
                return self._result(False, f"export_gltf_glb: '{path}' non inizia con 'glTF' (trovato {magia!r})", SwErrors.swExportError)
            return self._result(
                True, f"Modello esportato in formato GLB in '{path}'.",
                SwErrors.swSuccess, {"filepath": path, "binary": binary, "ignored_params": []}
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
            return self.export_model(filepath=path, format="pdf")
        except Exception as e:
            return self._result(False, f"export_3d_pdf: {e}", SwErrors.swGenericError)


    def _d2_appearance_files(self):
        """File .p2m della libreria degli aspetti installata (<cartella di SLDWORKS.exe>\\data\\graphics\\Materials, 736 in
        SW 2026): i nomi dei file sono in inglese anche con l'interfaccia italiana."""
        import glob
        lib = os.path.join(str(self._sw_app.GetExecutablePath), "data", "graphics", "Materials")
        return lib, sorted(glob.glob(os.path.join(lib, "**", "*.p2m"), recursive=True))

    def apply_appearance(self, appearance: str, face_points: list = None, components: list = None,
                         unit: str = None) -> Dict:
        """Aspetto (.p2m della libreria di SolidWorks) su tutto il documento, su facce (punti) o su componenti di un assieme.
        IModelDocExtension.CreateRenderMaterial(file) -> IRenderMaterial.AddEntity(...) ->
        AddDisplayStateSpecificRenderMaterial(rm, 1 = questo stato di visualizzazione, ...): con l'opzione 0 risponde False
        e non applica nulla (misurato 2026-10-24). Esito riletto con GetRenderMaterials2."""
        try:
            doc, err = self._part_or_assembly()
            if err:
                return err
            q = str(appearance or "").strip()
            if not q:
                return self._result(False, "apply_appearance: indica appearance (nome o percorso di un file .p2m)", SwErrors.swInvalidInput)
            if q.lower().endswith(".p2m") and os.path.isfile(q):
                path = q
            else:
                lib, files = self._d2_appearance_files()
                key = q.lower().replace("_", " ").removesuffix(".p2m")
                exact = [f for f in files if os.path.splitext(os.path.basename(f))[0].lower() == key]
                part = [f for f in files if key in os.path.relpath(f, lib).lower().replace("\\", "/")]
                cands = exact or part
                if len(cands) != 1:
                    names = [os.path.relpath(f, lib).replace("\\", "/")[:-4] for f in cands[:15]]
                    why = "nessun aspetto" if not cands else f"{len(cands)} aspetti"
                    return self._result(False, f"apply_appearance: {why} per '{q}'" + (f"; per esempio: {names}" if names else
                                        "; prova con una parola (chrome, aluminum, plastic, rubber, glass, wood...)"),
                                        SwErrors.swInvalidInput, {"candidates": names, "library": lib})
                path = cands[0]
            ext = doc.Extension
            null = null_variant()
            before = int(ext.GetRenderMaterialsCount2(1, null))
            rm = ext.CreateRenderMaterial(path)
            if rm is None:
                return self._result(False, f"apply_appearance: SolidWorks non ha caricato {path}", SwErrors.swFeatureError)
            targets = []
            if face_points:
                for p in face_points:
                    ok, info = self._select_point(doc, "face", p, unit)
                    if not ok:
                        doc.ClearSelection2(True)
                        return self._result(False, f"apply_appearance: faccia nel punto {list(p)}: {info.get('error')}",
                                            SwErrors.swSelectionError)
                    targets.append(doc.SelectionManager.GetSelectedObject6(1, -1))
                    doc.ClearSelection2(True)
            if components:
                if int(doc.GetType) != 2:
                    return self._result(False, "apply_appearance: components vale solo negli assiemi", SwErrors.swInvalidInput)
                for name in components:
                    comp, _ = self._as_comp(doc, name, False)
                    if comp is None:
                        return self._result(False, f"apply_appearance: componente '{name}' non trovato", SwErrors.swSelectionError)
                    targets.append(comp)
            if not targets:
                targets = [doc]
            added = sum(1 for t in targets if rm.AddEntity(t))
            if added != len(targets):
                return self._result(False, f"apply_appearance: SolidWorks ha accettato {added} entita' su {len(targets)}",
                                    SwErrors.swFeatureError)
            i1 = _byref_i4()
            i2 = _byref_i4()
            ok = ext.AddDisplayStateSpecificRenderMaterial(rm, 1, null, i1, i2)
            after = int(ext.GetRenderMaterialsCount2(1, null))
            mine = [m for m in (ext.GetRenderMaterials2(1, null) or ())
                    if os.path.normcase(str(m.FileName)) == os.path.normcase(path)]
            n_ent = max((int(m.GetEntitiesCount) for m in mine), default=0)
            data = {"file": path, "appearance": os.path.splitext(os.path.basename(path))[0], "targets": len(targets),
                    "entities_read": n_ent, "appearances_before": before, "appearances_after": after,
                    "scope": "faces" if face_points else ("components" if components else "document")}
            if not ok or after <= before or n_ent < len(targets):
                return self._result(False, "apply_appearance: aspetto non applicato (riletto: "
                                           f"{after} aspetti, {n_ent} entita')", SwErrors.swFeatureError, data)
            try:
                doc.GraphicsRedraw2()
            except Exception:
                pass
            return self._result(True, f"Aspetto '{data['appearance']}' applicato a {len(targets)} "
                                      f"{'facce' if face_points else ('componenti' if components else 'documento')}",
                                SwErrors.swSuccess, data)
        except Exception as e:
            return self._result(False, f"apply_appearance: {e}", SwErrors.swGenericError)
