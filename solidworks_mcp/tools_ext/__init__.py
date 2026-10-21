"""
Tool aggiunti per lotti (dal 2026-10-18): un modulo per lotto, ciascuno con
  TOOLS        nome -> (metodo di SolidWorksAutomation, descrizione, {parametro: (tipo json | None, descrizione)}, [obbligatori])
               (stesso formato di modeling_tools._TOOLS; finiscono nel gruppo 'modeling' di SW_MCP_TOOLSETS)
  DESTRUCTIVE  nome -> nota "[DESTRUCTIVE: ...]" (facoltativo, unito a safety.DESTRUCTIVE_TOOLS)
  OVERWRITE    nome -> argomento col percorso del file scritto (facoltativo, unito a safety.OVERWRITE_GUARDS)
I metodi stanno nei mixin automation/ext_<lotto>.py.
"""

from . import (moka, sketch2, features2, bodies2, curves, surfaces1, surfaces2, manage, sheetmetal, weldments,
               mold, analysis, sketch3, features3, sheetmetal2, assembly2, selection, sketch4)

MODULES = (moka, sketch2, features2, bodies2, curves, surfaces1, surfaces2, manage, sheetmetal, weldments,
           mold, analysis, sketch3, features3, sheetmetal2, assembly2, selection, sketch4)

EXT_TOOLS = {}
EXT_DESTRUCTIVE = {}
EXT_OVERWRITE = {}
for _m in MODULES:
    for _n in _m.TOOLS:
        if _n in EXT_TOOLS:
            raise ValueError(f"tool {_n} definito in due lotti")
    EXT_TOOLS.update(_m.TOOLS)
    for _n, _note in getattr(_m, "DESTRUCTIVE", {}).items():
        # safety aggiunge da solo "[DESTRUCTIVE: ...]": se il lotto l'ha gia' scritto, lo si toglie
        _note = _note.strip()
        if _note.upper().startswith("[DESTRUCTIVE"):
            _note = _note.split(":", 1)[-1].rstrip("]").strip()
        EXT_DESTRUCTIVE[_n] = _note.rstrip(".")
    EXT_OVERWRITE.update(getattr(_m, "OVERWRITE", {}))
