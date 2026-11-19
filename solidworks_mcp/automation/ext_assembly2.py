"""
Lotto ASSIEMI 2: gestione componenti, ripetizioni avanzate, Pack and Go e controlli assieme (mixin Assembly2Operations).
Schemi in tools_ext/assembly2.py.
"""

import os
import logging
import traceback
from typing import Dict

from ..constants import SwErrors

logger = logging.getLogger(__name__)


class Assembly2Operations:
    """Mixin per operazioni estese su assiemi, viteria, cinghie, allineamenti e Pack and Go."""


    def form_new_subassembly(self, components: list, subassembly_name: str = None) -> Dict:
        """Sposta i componenti indicati in un sottoassieme NUOVO (IAssemblyDoc.MakeAssemblyFromSelectedComponents: misurato
        19/11; FormNewSubAssembly non esiste e InsertNewAssembly crea un sottoassieme virtuale VUOTO). SolidWorks lo crea
        VIRTUALE (vive dentro l'assieme); `subassembly_name` diventa il suo nome. Si rilegge: il sottoassieme nuovo e' fra
        i componenti di primo livello e contiene esattamente quelli indicati."""
        try:
            doc, err = self._asm()
            if err:
                return err
            if not components:
                return self._result(False, "form_new_subassembly: nessun componente indicato", SwErrors.swInvalidInput)
            asm_path = str(self._com(doc, "GetPathName") or "")
            if not asm_path:
                return self._result(False, "Salva prima l'assieme: il sottoassieme nuovo va salvato accanto.",
                                    SwErrors.swInvalidInput)
            base = str(subassembly_name or "Sottoassieme").strip()
            path = os.path.join(os.path.dirname(asm_path), base + ".SLDASM")
            if os.path.exists(path):
                return self._result(False, f"Esiste gia' {path}: scegli un altro subassembly_name.", SwErrors.swInvalidInput)
            comps = []
            for c in components:
                comp, e = self._as_comp(doc, c, True)
                if e:
                    return self._result(False, e, SwErrors.swSelectionError)
                comps.append(comp)
            wanted = sorted(str(self._com(x, "Name2")) for x in comps)
            top0 = {str(self._com(x, "Name2")) for x in (doc.GetComponents(True) or ())}
            doc.ClearSelection2(True)
            for i, comp in enumerate(comps):
                comp.Select4(i > 0, self._sd(doc, 0), False)
            rc = bool(doc.MakeAssemblyFromSelectedComponents(path))
            doc.ClearSelection2(True)
            doc.EditRebuild3
            top1 = list(doc.GetComponents(True) or ())
            new = [x for x in top1 if str(self._com(x, "Name2")) not in top0]
            subs = [x for x in new if str(self._com(x, "GetPathName") or "").lower().endswith(".sldasm")]
            data = {"components": wanted, "file": path, "api_result": rc}
            if not subs:
                return self._result(False, "SolidWorks non ha creato il sottoassieme.", SwErrors.swFeatureError, data)
            sub = subs[0]
            inside = sorted(str(self._com(x, "Name2")).split("/")[-1] for x in (sub.GetChildren or ()))
            real = str(self._com(sub, "GetPathName") or "")
            virtual = "^" in os.path.basename(real)
            if subassembly_name:                  # misurato 19/11: SolidWorks lo crea VIRTUALE (Assieme3^...): si rinomina
                try:
                    sub.Name2 = base
                except Exception:
                    pass
            data.update({"subassembly": str(self._com(sub, "Name2")), "children": inside, "virtual": virtual,
                         "file": real, "top_level_now": sorted(str(self._com(x, "Name2")) for x in doc.GetComponents(True) or ())})
            if inside != wanted:
                return self._result(False, f"Sottoassieme {data['subassembly']} con {inside} invece di {wanted}.",
                                    SwErrors.swFeatureError, data)
            return self._result(True, f"Sottoassieme {data['subassembly']} con {inside}"
                                + (" (virtuale: vive dentro l'assieme, nessun file esterno)" if virtual else f" (file {real})"),
                                SwErrors.swSuccess, data)
        except Exception as ex:
            logger.error(f"form_new_subassembly: {ex}\n{traceback.format_exc()}")
            return self._result(False, f"form_new_subassembly: raggruppamento non riuscito: {ex}", SwErrors.swGenericError)

    def dissolve_subassembly(self, component_name: str) -> Dict:
        """Dissolve un sottoassieme: i suoi componenti passano all'assieme superiore (IAssemblyDoc.DissolveSubAssembly).
        Si rilegge: il sottoassieme sparisce dal primo livello e i suoi figli ci compaiono."""
        try:
            doc, err = self._asm()
            if err:
                return err
            comp, e = self._as_comp(doc, component_name, True)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            sname = str(self._com(comp, "Name2"))
            kids = sorted(str(self._com(x, "Name2")).split("/")[-1] for x in (comp.GetChildren or ()))
            if not kids:
                return self._result(False, f"'{sname}' non e' un sottoassieme (nessun componente figlio).", SwErrors.swInvalidInput)
            doc.ClearSelection2(True)
            comp.Select4(False, self._sd(doc, 0), False)
            rc = bool(self._com(doc, "DissolveSubAssembly"))     # senza argomenti: e' una PROPRIETA' in late binding
            doc.ClearSelection2(True)
            top = sorted(str(self._com(x, "Name2")) for x in (doc.GetComponents(True) or ()))
            data = {"component_name": sname, "children": kids, "top_level_now": top, "api_result": rc}
            gone = sname not in top
            arrived = all(any(t.split("-")[0] == k.split("-")[0] for t in top) for k in kids)
            if not (gone and arrived):
                return self._result(False, f"'{sname}' non dissolto come atteso (ancora presente: {not gone}).",
                                    SwErrors.swFeatureError, data)
            return self._result(True, f"Sottoassieme {sname} dissolto: {kids} ora al primo livello", SwErrors.swSuccess, data)
        except Exception as ex:
            logger.error(f"dissolve_subassembly: {ex}\n{traceback.format_exc()}")
            return self._result(False, f"dissolve_subassembly: scioglimento non riuscito: {ex}", SwErrors.swGenericError)

    _SUPP_STATES = {"suppressed": (0, (0,)), "lightweight": (1, (1, 4)), "resolved": (2, (2, 3))}

    def set_component_suppression_state(self, name: str, state: str = "resolved") -> Dict:
        """Stato di caricamento di un componente: resolved (risolto), lightweight (leggero: SolidWorks carica solo la
        grafica, il pezzo resta nell'assieme), suppressed (soppresso). IComponent2.SetSuppression2(0/1/2); lo stato si
        rilegge con GetSuppression2 (leggero = 1 o 4, risolto = 2 o 3). Su un componente leggero le misure sul pezzo
        (facce, massa del singolo pezzo) richiedono di riportarlo a resolved."""
        try:
            st = str(state or "resolved").lower().strip()
            if st not in self._SUPP_STATES:
                return self._result(False, f"Stato '{state}' sconosciuto: resolved | lightweight | suppressed.",
                                    SwErrors.swInvalidInput)
            doc, err = self._asm()
            if err:
                return err
            comp, e = self._as_comp(doc, name)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            code, ok_codes = self._SUPP_STATES[st]
            before = int(comp.GetSuppression2)
            rc = comp.SetSuppression2(code)
            doc.EditRebuild3
            now = int(comp.GetSuppression2)
            names = {0: "suppressed", 1: "lightweight", 2: "resolved", 3: "resolved", 4: "lightweight"}
            data = {"component": str(self._com(comp, "Name2")), "state": names.get(now, now), "state_code": now,
                    "before": names.get(before, before), "api_result": rc}
            if now not in ok_codes:
                hint = (" (SolidWorks non alleggerisce un componente il cui documento e' aperto in una sua finestra, o "
                        "non salvato: chiudi il pezzo e riprova)" if st == "lightweight" else "")
                return self._result(False, f"{data['component']}: stato {data['state']} invece di {st}{hint}.",
                                    SwErrors.swFeatureError, data)
            return self._result(True, f"{data['component']}: {data['before']} -> {data['state']} (riletto)",
                                SwErrors.swSuccess, data)
        except Exception as ex:
            logger.error(f"set_component_suppression_state: {ex}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {ex}", SwErrors.swGenericError)

