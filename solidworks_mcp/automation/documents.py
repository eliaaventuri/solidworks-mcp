"""
SolidWorks Document Operations
------------------------------
Create, open, save, and manage SolidWorks documents.
"""

import os
import logging
import traceback
from typing import Dict

import win32com.client
import pythoncom

from ..constants import SwErrors, SwDocumentTypes
from ..utils import find_template

logger = logging.getLogger(__name__)


class DocumentOperations:
    """
    Mixin class for document operations
    
    Requires parent class to have:
    - self._sw_app: SolidWorks application object
    - self.is_connected: Connection status property
    - self.connect(): Connection method
    - self._result(): Result factory method
    - self._units: UnitConverter instance
    """
    
    def create_new_part(self) -> Dict:
        """
        Create a new part document
        
        Returns:
            Result dictionary with document info
        """
        try:
            if not self.is_connected:
                r = self.connect()
                if not r["success"]:
                    return r
            
            # Find part template
            template = find_template("part")
            if not template:
                template = self._default_template("part")
                logger.info("Using SolidWorks default part template")
            else:
                logger.info(f"Using template: {template}")
            
            # Create document
            doc = self._sw_app.NewDocument(template, 0, 0, 0)
            
            if doc is None:
                return self._result(False, "Failed to create part document",
                                  SwErrors.swFileLoadError)
            
            # Set view
            try:
                doc.ShowNamedView2("*Isometric", 7)
                doc.ViewZoomtofit2()
            except:
                pass
            
            title = self._get_doc_title(doc)
            
            return self._result(True, f"Created part: {title}",
                              SwErrors.swSuccess,
                              {"name": title, "type": "Part"})
            
        except Exception as e:
            logger.error(f"Create part error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Error: {e}", SwErrors.swFileLoadError)
    
    def create_new_assembly(self) -> Dict:
        """
        Create a new assembly document
        
        Returns:
            Result dictionary with document info
        """
        try:
            if not self.is_connected:
                r = self.connect()
                if not r["success"]:
                    return r
            
            template = find_template("assembly")
            if not template:
                template = self._default_template("assembly")
            
            doc = self._sw_app.NewDocument(template, 0, 0, 0)
            
            if doc is None:
                return self._result(False, "Failed to create assembly",
                                  SwErrors.swFileLoadError)
            
            try:
                doc.ShowNamedView2("*Isometric", 7)
                doc.ViewZoomtofit2()
            except:
                pass
            
            title = self._get_doc_title(doc)
            
            return self._result(True, f"Created assembly: {title}",
                              SwErrors.swSuccess,
                              {"name": title, "type": "Assembly"})
            
        except Exception as e:
            logger.error(f"Create assembly error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Error: {e}", SwErrors.swFileLoadError)
    
    def create_new_drawing(self, paper_size: str = "A4") -> Dict:
        """
        Create a new drawing document
        
        Args:
            paper_size: Paper size (A4, A3, A2, A1, Letter)
        
        Returns:
            Result dictionary with document info
        """
        try:
            if not self.is_connected:
                r = self.connect()
                if not r["success"]:
                    return r
            
            template = find_template("drawing")
            if not template:
                template = self._default_template("drawing")
            
            doc = self._sw_app.NewDocument(template, 0, 0, 0)
            
            if doc is None:
                return self._result(False, "Failed to create drawing",
                                  SwErrors.swFileLoadError)
            
            title = self._get_doc_title(doc)
            
            return self._result(True, f"Created drawing: {title}",
                              SwErrors.swSuccess,
                              {"name": title, "type": "Drawing", "paper_size": paper_size})
            
        except Exception as e:
            logger.error(f"Create drawing error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Error: {e}", SwErrors.swFileLoadError)
    
    def open_document(self, filepath: str) -> Dict:
        """
        Open an existing document
        
        Args:
            filepath: Path to SolidWorks file
        
        Returns:
            Result dictionary
        """
        try:
            if not self.is_connected:
                r = self.connect()
                if not r["success"]:
                    return r
            
            if not os.path.exists(filepath):
                return self._result(False, f"File not found: {filepath}",
                                  SwErrors.swFileNotFoundError)
            
            # Determine document type from extension
            ext = os.path.splitext(filepath)[1].lower()
            type_map = {
                ".sldprt": SwDocumentTypes.swDocPART,
                ".sldasm": SwDocumentTypes.swDocASSEMBLY,
                ".slddrw": SwDocumentTypes.swDocDRAWING,
            }
            doc_type = type_map.get(ext, SwDocumentTypes.swDocPART)
            
            # Open document
            errors = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            warnings = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            
            doc = self._sw_app.OpenDoc6(filepath, int(doc_type), 0, "", errors, warnings)
            
            if doc is None or errors.value != 0:
                return self._result(False, f"Failed to open (error {errors.value})",
                                  SwErrors.swFileLoadError)
            
            title = self._get_doc_title(doc)
            
            return self._result(True, f"Opened: {title}",
                              SwErrors.swSuccess,
                              {"name": title, "path": filepath})
            
        except Exception as e:
            logger.error(f"Open document error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Error: {e}", SwErrors.swFileLoadError)
    
    def save_document(self, filepath: str = None, overwrite: bool = False) -> Dict:
        """
        Save the active document
        FIXED v4.1: Use doc.SaveAs() as primary method (avoids COM type mismatch
        with Extension.SaveAs where None parameter fails in SW 2025).

        Args:
            filepath: Path to save (None = save in place)
            overwrite: obbligatorio (True) per scrivere su un file GIA' ESISTENTE diverso da quello del documento
                       (il salvataggio sul proprio file, o senza filepath, e' un normale "Salva")

        Returns:
            Result dictionary
        """
        try:
            doc, err = self.get_active_doc()
            if err:
                return err

            if filepath:
                # Ensure absolute path
                filepath = os.path.abspath(filepath)
                own = self._get_doc_path(doc)
                same = bool(own) and os.path.normcase(os.path.abspath(own)) == os.path.normcase(filepath)
                existed = os.path.exists(filepath)
                if existed and not same and not overwrite:
                    return self._result(False,
                        f"Rifiutato: il file esiste gia' ({filepath}) e verrebbe SOVRASCRITTO. Se e' voluto, ripeti con "
                        f"overwrite=true; altrimenti scegli un altro nome.", SwErrors.swFileSaveError,
                        {"path": filepath, "exists": True, "refused": "file_exists"})
                guard = self._export_guard(doc, filepath) if hasattr(self, "_export_guard") else None
                if guard:           # DXF/DWG con viste interrotte: crash di SolidWorks (A16)
                    return self._result(False, guard, SwErrors.swExportError)

                # Ensure directory exists
                dir_path = os.path.dirname(filepath)
                if dir_path and not os.path.exists(dir_path):
                    os.makedirs(dir_path)

                saved = False
                method_used = ""

                # Method 1: doc.SaveAs (simplest, most reliable for SW 2025)
                try:
                    result = doc.SaveAs(filepath)
                    if result:
                        saved = True
                        method_used = "SaveAs"
                except Exception as e:
                    logger.debug(f"doc.SaveAs failed: {e}")

                # Method 2: Extension.SaveAs with proper VARIANT null dispatch
                if not saved:
                    try:
                        empty_export = win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)
                        errors = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                        warnings = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)

                        result = doc.Extension.SaveAs(
                            filepath, 0, 0, empty_export, errors, warnings
                        )
                        if result and errors.value == 0:
                            saved = True
                            method_used = "Extension.SaveAs"
                    except Exception as e:
                        logger.debug(f"Extension.SaveAs failed: {e}")

                # Method 3: Extension.SaveAs2
                if not saved:
                    try:
                        errors = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                        warnings = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)

                        result = doc.Extension.SaveAs2(
                            filepath, 0, 0, None, "", False, errors, warnings
                        )
                        if result:
                            saved = True
                            method_used = "Extension.SaveAs2"
                    except Exception as e:
                        logger.debug(f"Extension.SaveAs2 failed: {e}")

                if not saved:
                    return self._result(False, "Save failed - all methods attempted",
                                      SwErrors.swFileSaveError)

                return self._result(True, f"Saved: {filepath} [{method_used}]",
                                  SwErrors.swSuccess,
                                  {"path": filepath, "method": method_used,
                                   "overwritten": bool(existed and not same)})
            else:
                # Save in place: Save3 vuole Errors/Warnings BYREF (con interi semplici da "Incompatibilita' tra tipi")
                path = self._get_doc_path(doc)
                if not path:
                    return self._result(False, "Il documento non e' mai stato salvato: indica filepath.",
                                      SwErrors.swFileSaveError)
                errors = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                warnings = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                result = doc.Save3(1, errors, warnings)
                if not result or errors.value != 0:
                    return self._result(False, f"Save failed (errori {errors.value})",
                                      SwErrors.swFileSaveError)
                return self._result(True, f"Saved: {path}",
                                  SwErrors.swSuccess, {"path": path})

        except Exception as e:
            logger.error(f"Save error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Error: {e}", SwErrors.swFileSaveError)

    # ------------------------------------------------------------------ chiusura sicura (B6)
    def _open_docs(self) -> list:
        """[(titolo, percorso, oggetto)] dei documenti aperti nell'istanza."""
        out = []
        for d in self._com(self._sw_app, "GetDocuments") or ():
            try:
                out.append((self._get_doc_title(d), self._get_doc_path(d) or "", d))
            except Exception:
                pass
        return out

    def _find_open_doc(self, ident: str):
        """Documento aperto per titolo ('Parte1', 'staffa.SLDPRT', 'staffa') o percorso completo -> (doc, errore)."""
        docs = self._open_docs()
        ident_s = str(ident).strip()
        norm = os.path.normcase(os.path.abspath(ident_s)) if (os.sep in ident_s or "/" in ident_s or ":" in ident_s) else None
        hits = []
        for title, path, d in docs:
            stem = os.path.splitext(title)[0].lower()
            if norm and path and os.path.normcase(os.path.abspath(path)) == norm:
                hits.append((title, path, d))
            elif not norm and ident_s.lower() in (title.lower(), stem, os.path.basename(path).lower(),
                                                 os.path.splitext(os.path.basename(path))[0].lower()):
                hits.append((title, path, d))
        if len(hits) == 1:
            return hits[0][2], None
        titles = [t for t, p, d in docs]
        if not hits:
            return None, self._result(False, f"Nessun documento aperto corrisponde a '{ident}'. Aperti: {titles}",
                                      SwErrors.swFileNotFoundError, {"open_documents": titles})
        return None, self._result(False, f"'{ident}' e' ambiguo ({[p or t for t, p, d in hits]}): indica il percorso completo.",
                                  SwErrors.swInvalidInput)

    def _unsaved_work(self, doc) -> list:
        """Motivi per cui chiudere il documento farebbe perdere lavoro (lista vuota = niente da perdere)."""
        reasons = []
        try:
            if bool(self._com(doc, "GetSaveFlag")):
                reasons.append("modifiche non salvate")
        except Exception:
            pass
        try:       # uno schizzo aperto non sempre aggiorna il flag di salvataggio
            if self._com(doc, "GetType") == 1 and doc.SketchManager.ActiveSketch is not None:
                reasons.append("schizzo in modifica")
        except Exception:
            pass
        try:       # assieme: componenti modificati e non salvati
            if self._com(doc, "GetType") == 2:
                dirty = []
                for comp in doc.GetComponents(False) or ():
                    m = comp.GetModelDoc2
                    if m is not None and bool(self._com(m, "GetSaveFlag")):
                        dirty.append(self._get_doc_title(m))
                if dirty:
                    reasons.append(f"componenti modificati e non salvati: {sorted(set(dirty))}")
        except Exception:
            pass
        return reasons

    def close_document(self, save: bool = False, discard: bool = False, document: str = None) -> Dict:
        """
        Chiude un documento in modo SICURO: non butta mai via lavoro non salvato per sbaglio.

        Args:
            save: salva e poi chiude (il documento deve gia' avere un file; altrimenti usa prima save_document(filepath))
            discard: chiude SCARTANDO le modifiche non salvate (dichiarato nel risultato)
            document: titolo ('Parte1', 'staffa.SLDPRT') o percorso completo del documento da chiudere
                      (default: il documento attivo; indicalo sempre se hai piu' documenti aperti)

        Senza save ne' discard: chiude solo se non c'e' nulla da perdere, altrimenti RIFIUTA e spiega.
        """
        try:
            if not self.is_connected:
                r = self.connect()
                if not r["success"]:
                    return r
            if save and discard:
                return self._result(False, "save e discard sono in contraddizione: scegline uno.", SwErrors.swInvalidInput)
            if document:
                doc, err = self._find_open_doc(document)
                if err:
                    return err
            else:
                doc, err = self.get_active_doc()
                if err:
                    return self._result(True, "No document to close")
            title = self._get_doc_title(doc)
            path = self._get_doc_path(doc)
            reasons = self._unsaved_work(doc)
            info = {"document": title, "path": path, "unsaved": reasons, "was_modified": bool(reasons)}
            action = "closed_clean"
            if reasons and not save and not discard:
                return self._result(False,
                    f"Rifiutato: '{title}' ha {'; '.join(reasons)}. Chiuderlo ora farebbe PERDERE il lavoro. "
                    f"Usa save=true (salva e chiudi) oppure discard=true (chiudi scartando).",
                    SwErrors.swUnknownError, {**info, "refused": "unsaved_changes", "closed": False})
            if save:
                if not path:
                    return self._result(False,
                        f"Rifiutato: '{title}' non e' mai stato salvato, save=true non sa dove scrivere. Usa prima "
                        f"save_document(filepath) oppure discard=true.", SwErrors.swFileSaveError,
                        {**info, "refused": "never_saved", "closed": False})
                errors = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                warnings = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                if not doc.Save3(1, errors, warnings) or errors.value != 0:
                    return self._result(False, f"Salvataggio di '{title}' fallito (errori {errors.value}): NON chiuso.",
                                        SwErrors.swFileSaveError, {**info, "refused": "save_failed", "closed": False})
                action = "saved_and_closed"
            elif reasons and discard:
                action = "discarded"
            self._sw_app.CloseDoc(path or title)
            still = any(t == title and p == path for t, p, d in self._open_docs())
            if still:
                return self._result(False, f"CloseDoc non ha chiuso '{title}'.", SwErrors.swUnknownError,
                                    {**info, "closed": False})
            msg = {"closed_clean": f"Closed: {title}",
                   "saved_and_closed": f"Closed: {title} (salvato prima di chiudere)",
                   "discarded": f"Closed: {title} (modifiche NON salvate SCARTATE: {'; '.join(reasons)})"}[action]
            return self._result(True, msg, SwErrors.swSuccess, {**info, "action": action, "closed": True})

        except Exception as e:
            logger.error(f"Close error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Error: {e}", SwErrors.swUnknownError)

    def get_document_info(self) -> Dict:
        """
        Get information about the active document
        
        Returns:
            Result dictionary with document details
        """
        try:
            doc, err = self.get_active_doc()
            if err:
                return err
            
            type_names = {
                0: "None",
                1: "Part",
                2: "Assembly",
                3: "Drawing"
            }
            
            doc_type = self._com(doc, "GetType")
            title = self._get_doc_title(doc)
            path = self._get_doc_path(doc)
            
            info = {
                "title": title,
                "path": path if path else "Not saved",
                "type": type_names.get(doc_type, "Unknown"),
                "type_code": doc_type,
            }
            
            return self._result(True, f"{title} ({info['type']})",
                              SwErrors.swSuccess, info)
            
        except Exception as e:
            logger.error(f"Get info error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Error: {e}", SwErrors.swUnknownError)
    
    def list_open_documents(self) -> Dict:
        """
        List all open documents
        
        Returns:
            Result dictionary with document list
        """
        try:
            if not self.is_connected:
                r = self.connect()
                if not r["success"]:
                    return r
            
            docs = []
            # GetFirstDocument is not exposed via late binding; GetDocuments is
            for doc in self._com(self._sw_app, "GetDocuments") or ():
                try:
                    title = self._get_doc_title(doc)
                    doc_type = self._com(doc, "GetType")
                    
                    type_names = {1: "Part", 2: "Assembly", 3: "Drawing"}
                    
                    docs.append({
                        "title": title,
                        "type": type_names.get(doc_type, "Unknown")
                    })
                except:
                    pass
            
            return self._result(True, f"{len(docs)} document(s) open",
                              SwErrors.swSuccess, {"documents": docs})
            
        except Exception as e:
            logger.error(f"List documents error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Error: {e}", SwErrors.swUnknownError)
