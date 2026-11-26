"""
Lotto TAVOLE 3 (revisione 2026-11-12, sez. 5): quota libera fra due spigoli di una vista, eliminazione di un foglio (mixin).
Schemi in tools_ext/drawings3.py. Coordinate dei punti = coordinate del FOGLIO in mm (come list_drawing_views e
get_drawing_layout), punti SUGLI spigoli visibili nella vista.
"""

import logging
import traceback
from typing import Dict

from ..constants import SwErrors

logger = logging.getLogger(__name__)

_KINDS = {"auto": "AddDimension2", "horizontal": "AddHorizontalDimension2", "vertical": "AddVerticalDimension2"}


class Drawings3Operations:
    """Mixin del lotto drawings3."""

    def add_drawing_dimension(self, edge1: list, edge2: list = None, position: list = None, kind: str = "auto",
                              expected: float = None) -> Dict:
        """Quota fra due spigoli (o lunghezza di uno spigolo se edge2 manca) presi da punti del foglio in mm SUGLI spigoli;
        kind auto | horizontal | vertical; position = punto del testo [x,y] mm (default: fra i due punti, 15 mm sopra).
        Il valore e' riletto (mm del modello); con `expected` una quota diversa (oltre 0,05 mm) viene cancellata e il tool
        fallisce."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            fn = _KINDS.get(str(kind or "auto").lower())
            if fn is None:
                return self._result(False, "kind: auto | horizontal | vertical", SwErrors.swInvalidInput)
            for nm, p in (("edge1", edge1), ("edge2", edge2), ("position", position)):
                if p is not None and (not isinstance(p, (list, tuple)) or len(p) != 2):
                    return self._result(False, f"{nm} = [x, y] in mm del foglio", SwErrors.swInvalidInput)
            if edge1 is None:
                return self._result(False, "edge1 obbligatorio ([x, y] mm del foglio, SU uno spigolo)", SwErrors.swInvalidInput)
            p1 = (float(edge1[0]) / 1000.0, float(edge1[1]) / 1000.0)
            c1 = [(p1[0], p1[1], 0.0), (p1[0], p1[1], 1.0)]
            if edge2 is not None:
                p2 = (float(edge2[0]) / 1000.0, float(edge2[1]) / 1000.0)
                c2 = [(p2[0], p2[1], 0.0), (p2[0], p2[1], 1.0)]
                if not self._dm_select_pair(doc, c1, c2):
                    return self._result(False, f"Spigoli non selezionabili in {list(edge1)} e {list(edge2)} mm (i punti devono "
                                        "stare SU spigoli visibili di una vista).", SwErrors.swSelectionError)
            else:
                doc.ClearSelection2(True)
                if not any(self._sheet_select(doc, typ, p1[0], p1[1]) for typ in ("EDGE", "SILEDGE")):
                    return self._result(False, f"Nessuno spigolo in {list(edge1)} mm del foglio.", SwErrors.swSelectionError)
                p2 = p1
            if position is not None:
                tx, ty = float(position[0]) / 1000.0, float(position[1]) / 1000.0
            else:
                tx, ty = (p1[0] + p2[0]) / 2.0, max(p1[1], p2[1]) + 0.015
            dd = getattr(doc, fn)(tx, ty, 0)
            doc.ClearSelection2(True)
            if dd is None:
                return self._result(False, f"{fn}: SolidWorks non ha creato la quota (spigoli non quotabili insieme con "
                                    f"kind={kind}?).", SwErrors.swFeatureError)
            dim = dd.GetDimension2(0)
            val = float(dim.Value)
            sel = str(dd.GetNameForSelection)
            data = {"value_mm": round(val, 4), "name": sel, "kind": kind, "position_mm": [round(tx * 1000, 3), round(ty * 1000, 3)]}
            try:
                data["driven"] = int(dim.DrivenState) == 1
            except Exception:
                pass
            if expected is not None and abs(val - float(expected)) > 0.05:
                self._delete_dim_full(doc, sel)
                return self._result(False, f"Quota creata ma vale {val:.4f} mm invece di {expected}: cancellata (spigoli diversi da "
                                    "quelli voluti?).", SwErrors.swFeatureError, data)
            return self._result(True, f"Quota {sel} = {val:.4f} mm (riletta)", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"add_drawing_dimension: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def delete_sheet(self, name: str) -> Dict:
        """Elimina un foglio della tavola (con le sue viste). Non elimina l'unico foglio. Verifica: il nome non c'e' piu'."""
        try:
            doc, err = self._drawing()
            if err:
                return err
            names = [str(n) for n in (self._com(doc, "GetSheetNames") or ())]
            if name not in names:
                return self._result(False, f"Foglio '{name}' non trovato. Fogli: {names}", SwErrors.swInvalidInput)
            if len(names) < 2:
                return self._result(False, "E' l'unico foglio della tavola: non si elimina.", SwErrors.swInvalidInput)
            cur = str(self._com(self._com(doc, "GetCurrentSheet"), "GetName"))
            if cur == name:                       # non si cancella il foglio attivo: si passa a un altro
                doc.ActivateSheet(next(n for n in names if n != name))
            doc.ClearSelection2(True)
            ok_sel = bool(doc.Extension.SelectByID2(name, "SHEET", 0, 0, 0, False, 0, self._NULL, 0))
            ok_del = bool(doc.Extension.DeleteSelection2(0)) if ok_sel else False
            doc.ClearSelection2(True)
            after = [str(n) for n in (self._com(doc, "GetSheetNames") or ())]
            data = {"sheets": after, "selected": ok_sel, "delete_api": ok_del}
            if name in after:
                return self._result(False, f"Foglio '{name}' NON eliminato (selezione {ok_sel}, cancellazione {ok_del}).",
                                    SwErrors.swUnknownError, data)
            self._sheet_ann_cache = None
            return self._result(True, f"Foglio '{name}' eliminato: restano {after}", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"delete_sheet: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)
