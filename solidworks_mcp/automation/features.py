"""
SolidWorks Feature Operations
-----------------------------
Create 3D features: extrude, cut, fillet, chamfer, etc.

Modulo nato nel progetto originale (alisamsam/solidworks-mcp), poi corretto qui (cut_extrude through_all + both_directions, late binding).
Note dell'autore originale:
- FeatureExtrusion2 now uses correct 23 parameters for SW 2025
- Proper sketch close + select before extrude (fixes multi-profile sketches)
- Property vs method fixes (FirstFeature, GetNextFeature, GetTypeName2)
- Added _find_last_sketch helper for reliable sketch selection
- Added _get_sketch_info helper for better error diagnostics
- Better error messages with sketch profile count
"""

import logging
import traceback
from typing import Optional, Dict

from ..constants import SwErrors, SYSTEM_FOLDER_TYPES

logger = logging.getLogger(__name__)


class FeatureOperations:
    """
    Mixin class for feature operations
    
    Requires parent class to have:
    - get_active_doc(): Document access method
    - _result(): Result factory method
    - _units: UnitConverter instance
    """
    
    # ========================================================================
    # Helper Methods
    # ========================================================================
    
    def _find_last_sketch(self, doc) -> Optional[str]:
        """
        Find the name of the last sketch in the feature tree.
        Uses properties (not method calls) for SW 2025 compatibility.
        
        Returns:
            Sketch name string or None
        """
        last_sketch = None
        try:
            feat = doc.FirstFeature
            while feat is not None:
                try:
                    feat_type = feat.GetTypeName2
                    if feat_type == "ProfileFeature":
                        last_sketch = feat.Name
                except:
                    pass
                try:
                    feat = feat.GetNextFeature
                except:
                    break
        except Exception as e:
            logger.debug(f"_find_last_sketch error: {e}")
        return last_sketch
    
    def _get_sketch_info(self, doc) -> Dict:
        """
        Get diagnostic info about sketches in the document.
        Useful for error messages.
        
        Returns:
            Dict with sketch_count, sketch_names, has_active_sketch
        """
        info = {
            "sketch_count": 0,
            "sketch_names": [],
            "has_active_sketch": False,
            "feature_count": 0
        }
        try:
            # Check if sketch is active
            try:
                active_sketch = doc.SketchManager.ActiveSketch
                info["has_active_sketch"] = active_sketch is not None
            except:
                pass
            
            # Count sketches and features
            feat = doc.FirstFeature
            while feat is not None:
                try:
                    feat_type = feat.GetTypeName2
                    info["feature_count"] += 1
                    if feat_type == "ProfileFeature":
                        info["sketch_count"] += 1
                        info["sketch_names"].append(feat.Name)
                except:
                    pass
                try:
                    feat = feat.GetNextFeature
                except:
                    break
        except Exception as e:
            logger.debug(f"_get_sketch_info error: {e}")
        return info
    
    
    # ========================================================================
    # Extrude
    # ========================================================================
    
    
    # ========================================================================
    # Cut Extrude
    # ========================================================================
    
    
    # ========================================================================
    # Fillet
    # ========================================================================
    
    
    # ========================================================================
    # Chamfer
    # ========================================================================
    
    
    # ========================================================================
    # List Features (FIXED: properties not methods)
    # ========================================================================
    
    def list_features(self, include_system: bool = False, detail: bool = False) -> Dict:
        """
        Elenco delle feature del documento attivo. Di default NON include le cartelle di sistema dell'albero (Preferiti,
        Cronologia, Impostazioni selezione, Sensori, Design Binder, Annotazioni, Markup, Luci e videocamere, Corpi solidi/di
        superficie, Commenti, Equazioni, Materiale), riconosciute per TIPO (GetTypeName2, uguale in italiano e in inglese).
        Output compatto: una riga per feature, "nome (tipo)" + " [soppressa]" se soppressa. detail=true restituisce invece
        dizionari {name, type, suppressed}. include_system=true aggiunge le cartelle di sistema.
        """
        try:
            doc, err = self.get_active_doc()
            if err:
                return err
            rows = []
            skipped = 0
            for name, ftype, feat in self._features(doc):     # elenco in blocco (modeling_base._features)
                name, ftype = str(name), str(ftype)
                if ftype in SYSTEM_FOLDER_TYPES and not include_system:
                    skipped += 1
                    continue
                try:
                    sup = feat.IsSuppressed2(1, None)
                    sup = bool(sup[0] if isinstance(sup, (tuple, list)) else sup)
                except Exception:
                    sup = False
                rows.append((name, ftype, sup))
            if detail:
                items = [{"name": n, "type": t, "suppressed": sp} for n, t, sp in rows]
            else:
                items = [f"{n} ({t})" + (" [soppressa]" if sp else "") for n, t, sp in rows]
            data = {"features": items, "count": len(items)}
            if skipped:
                data["system_folders_hidden"] = skipped
            return self._result(True, f"{len(items)} features found", SwErrors.swSuccess, data)

        except Exception as e:
            logger.error(f"List features error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Error: {e}", SwErrors.swUnknownError)

    # ========================================================================
    # Edge Selection Helper
    # ========================================================================
    
