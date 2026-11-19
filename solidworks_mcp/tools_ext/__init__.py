"""
Tool aggiunti per lotti (dal 2026-10-18): un modulo per lotto, ciascuno con
  TOOLS        nome -> (metodo di SolidWorksAutomation, descrizione, {parametro: (tipo json | None, descrizione)}, [obbligatori])
               (stesso formato di modeling_tools._TOOLS; lo smistamento passa da MODELING_DISPATCH, ma il GRUPPO di
               SW_MCP_TOOLSETS e' quello dell'area vera: EXT_GROUP, per modulo, vedi GROUP_OF_MODULE)
  DESTRUCTIVE  nome -> nota "[DESTRUCTIVE: ...]" (facoltativo, unito a safety.DESTRUCTIVE_TOOLS)
  OVERWRITE    nome -> argomento col percorso del file scritto (facoltativo, unito a safety.OVERWRITE_GUARDS)
I metodi stanno nei mixin automation/ext_<lotto>.py.
"""

from . import (moka, sketch2, features2, bodies2, curves, surfaces1, surfaces2, manage, sheetmetal, weldments,
               mold, analysis, sketch3, features3, sheetmetal2, assembly2, selection, sketch4, sketch5, assembly3, drawings2, features4, data2,
               simulation2, surfaces3, drawings3)

MODULES = (moka, sketch2, features2, bodies2, curves, surfaces1, surfaces2, manage, sheetmetal, weldments,
           mold, analysis, sketch3, features3, sheetmetal2, assembly2, selection, sketch4, sketch5, assembly3, drawings2, features4, data2,
           simulation2, surfaces3, drawings3)

# gruppo di SW_MCP_TOOLSETS per lotto (revisione 2026-11-12, sez. 4: prima tutti i tool dei lotti erano in 'modeling', anche
# quelli di tavole, assiemi, dati e simulazione); i lotti non elencati sono di modellazione
GROUP_OF_MODULE = {"drawings2": "drawings", "drawings3": "drawings", "assembly2": "assembly", "assembly3": "assembly", "data2": "data",
                   "simulation2": "simulation", "selection": "base"}

EXT_TOOLS = {}
EXT_DESTRUCTIVE = {}
EXT_OVERWRITE = {}
EXT_GROUP = {}
for _m in MODULES:
    for _n in _m.TOOLS:
        if _n in EXT_TOOLS:
            raise ValueError(f"tool {_n} definito in due lotti")
        EXT_GROUP[_n] = GROUP_OF_MODULE.get(_m.__name__.rsplit(".", 1)[-1], "modeling")
    EXT_TOOLS.update(_m.TOOLS)
    for _n, _note in getattr(_m, "DESTRUCTIVE", {}).items():
        # safety aggiunge da solo "[DESTRUCTIVE: ...]": se il lotto l'ha gia' scritto, lo si toglie
        _note = _note.strip()
        if _note.upper().startswith("[DESTRUCTIVE"):
            _note = _note.split(":", 1)[-1].rstrip("]").strip()
        EXT_DESTRUCTIVE[_n] = _note.rstrip(".")
    EXT_OVERWRITE.update(getattr(_m, "OVERWRITE", {}))
