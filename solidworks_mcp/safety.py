"""
Sicurezza dei tool (gruppo B, B6): cosa puo' far perdere lavoro all'utente.

 1. Annotazioni MCP: i tool distruttivi portano `destructiveHint=True` e una nota "[DISTRUTTIVO ...]" nella descrizione,
    cosi' i client (Claude Desktop ecc.) chiedono conferma all'utente.
 2. Salvataggi/esportazioni su un file GIA' ESISTENTE: rifiutati se manca `overwrite=true` (guardia unica qui,
    applicata prima dello smistamento; `save_document` ha la stessa regola dentro il metodo).
 3. Protezioni con parametro esplicito dentro i metodi:
      close_document   save=true | discard=true | document=<titolo/percorso>   (rifiuta se ci sono modifiche non salvate)
      save_document    overwrite=true per sovrascrivere un altro file
      delete_feature   confirm=true (+ delete_children=true se ci sono feature dipendenti)
"""

import os
from typing import Dict, List, Optional

from mcp.types import Tool, ToolAnnotations

# tool che scrivono un file: nome -> argomento col percorso
OVERWRITE_GUARDS: Dict[str, str] = {
    "save_document": "filepath",
    "save_drawing": "filepath",
    "export_drawing": "filepath",
    "export_model": "filepath",
    "export_model_image": "filepath",
    "export_simulation_plot": "filepath",
    "create_drawing": "save_as",
}

# tool distruttivi: nome -> nota aggiunta alla descrizione
DESTRUCTIVE_TOOLS: Dict[str, str] = {
    "close_document": "chiude il documento: con modifiche non salvate rifiuta, salvo save=true o discard=true",
    "save_document": "scrive su disco: un file esistente diverso viene sovrascritto solo con overwrite=true",
    "save_drawing": "scrive su disco: un file esistente viene sovrascritto solo con overwrite=true",
    "export_drawing": "scrive su disco: un file esistente viene sovrascritto solo con overwrite=true",
    "export_model": "scrive su disco: un file esistente viene sovrascritto solo con overwrite=true",
    "export_model_image": "scrive su disco: un file esistente viene sovrascritto solo con overwrite=true",
    "export_simulation_plot": "scrive su disco: un file esistente viene sovrascritto solo con overwrite=true",
    "create_drawing": "con save_as scrive su disco: un file esistente viene sovrascritto solo con overwrite=true",
    "delete_feature": "elimina la feature senza annulla: richiede confirm=true",
    "delete_view": "elimina una vista del disegno",
    "delete_component": "elimina un componente dall'assieme",
    "delete_mate": "elimina un accoppiamento",
    "replace_component": "sostituisce un componente dell'assieme",
    "delete_custom_property": "elimina una proprieta' personalizzata",
    "delete_global_variable": "elimina una variabile globale",
    "delete_equation": "elimina un'equazione",
    "delete_part_configuration": "elimina una configurazione",
    "delete_explode_step": "elimina un passo di esplosione",
    "mirror_components": "con opposite_hand=true crea NUOVI FILE: un file esistente viene sovrascritto solo con overwrite=true",
    "delete_simulation_study": "elimina uno studio di simulazione con i suoi risultati",
    "delete_simulation_load": "elimina un carico/vincolo dello studio",
    "execute_python": "esegue codice arbitrario con i permessi dell'utente",
}


def decorate_tools(tools: List[Tool]) -> List[Tool]:
    """Aggiunge annotazioni MCP, nota nella descrizione e parametro `overwrite` ai tool a rischio."""
    out = []
    for t in tools:
        if t.name not in DESTRUCTIVE_TOOLS:
            out.append(t)
            continue
        schema = dict(t.inputSchema or {})
        props = dict(schema.get("properties", {}))
        if t.name in OVERWRITE_GUARDS and "overwrite" not in props:
            props["overwrite"] = {"type": "boolean", "default": False,
                                  "description": "True = consente di SOVRASCRIVERE un file gia' esistente (altrimenti rifiuta)"}
        schema["properties"] = props
        desc = (t.description or "") + f" [DISTRUTTIVO: {DESTRUCTIVE_TOOLS[t.name]}.]"
        ann = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
        out.append(t.model_copy(update={"inputSchema": schema, "description": desc, "annotations": ann}))
    return out


def check_call(name: str, arguments: dict) -> Optional[str]:
    """Messaggio di rifiuto se la chiamata sovrascriverebbe un file esistente senza overwrite=true, altrimenti None."""
    arg = OVERWRITE_GUARDS.get(name)
    if not arg or name == "save_document":      # save_document controlla da se' (conosce il file del documento)
        return None
    path = (arguments or {}).get(arg)
    if path and not (arguments or {}).get("overwrite") and os.path.exists(os.path.abspath(str(path))):
        return (f"Rifiutato: il file esiste gia' ({os.path.abspath(str(path))}) e verrebbe SOVRASCRITTO. "
                f"Se e' voluto, ripeti con overwrite=true; altrimenti scegli un altro nome.")
    return None
