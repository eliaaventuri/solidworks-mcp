"""
Sicurezza dei tool (gruppo B, B6): cosa puo' far perdere lavoro all'utente.

 1. Annotazioni MCP: i tool distruttivi portano `destructiveHint=True` e una nota "[DESTRUCTIVE ...]" nella descrizione,
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

from .tools_ext import EXT_DESTRUCTIVE, EXT_OVERWRITE

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
    "close_document": "closes the document; refuses if there are unsaved changes unless save=true or discard=true",
    "save_document": "writes to disk; a different existing file is overwritten only with overwrite=true",
    "save_drawing": "writes to disk; an existing file is overwritten only with overwrite=true",
    "export_drawing": "writes to disk; an existing file is overwritten only with overwrite=true",
    "export_model": "writes to disk; an existing file is overwritten only with overwrite=true",
    "export_model_image": "writes to disk; an existing file is overwritten only with overwrite=true",
    "export_simulation_plot": "writes to disk; an existing file is overwritten only with overwrite=true",
    "create_drawing": "with save_as writes to disk; an existing file is overwritten only with overwrite=true",
    "delete_feature": "deletes the feature with no undo; requires confirm=true",
    "delete_view": "deletes a drawing view",
    "delete_component": "deletes a component from the assembly",
    "delete_mate": "deletes a mate",
    "delete_sketch_entities": "deletes sketch entities, dimensions or relations with no undo",
    "split_sketch_entity": "replaces a sketch line with two lines; its dimensions and relations are lost",
    "delete_dimension": "deletes a sketch dimension with no undo",
    "replace_component": "replaces an assembly component",
    "delete_custom_property": "deletes a custom property",
    "delete_global_variable": "deletes a global variable",
    "delete_equation": "deletes an equation",
    "delete_part_configuration": "deletes a configuration",
    "delete_explode_step": "deletes an explode step",
    "mirror_components": "with opposite_hand=true creates NEW FILES; an existing file is overwritten only with overwrite=true",
    "delete_simulation_study": "deletes a simulation study and its results",
    "delete_simulation_load": "deletes a load/fixture of the study",
    "execute_python": "runs arbitrary code with the user's permissions",
}

# tool aggiunti per lotti (tools_ext/*.py)
OVERWRITE_GUARDS.update(EXT_OVERWRITE)
DESTRUCTIVE_TOOLS.update(EXT_DESTRUCTIVE)


DOCUMENT_PARAM = {"type": "string", "description": "Optional: title of an open document to make active before this tool "
                  "(as in list_open_documents, e.g. 'Parte1'). Without it the active document is used, and the result warns "
                  "if the active document changed since the previous call."}


def _with_document(t: Tool) -> Tool:
    """Aggiunge il parametro comune `document` allo schema di ogni tool (lo gestisce server._dispatch_tool)."""
    schema = dict(t.inputSchema or {})
    if schema.get("type") != "object":
        return t
    props = dict(schema.get("properties", {}))
    props.setdefault("document", DOCUMENT_PARAM)
    schema["properties"] = props
    return t.model_copy(update={"inputSchema": schema})


def decorate_tools(tools: List[Tool]) -> List[Tool]:
    """Aggiunge annotazioni MCP, nota nella descrizione e parametro `overwrite` ai tool a rischio."""
    out = []
    for t in (_with_document(x) for x in tools):
        if t.name not in DESTRUCTIVE_TOOLS:
            out.append(t)
            continue
        schema = dict(t.inputSchema or {})
        props = dict(schema.get("properties", {}))
        if t.name in OVERWRITE_GUARDS and "overwrite" not in props:
            props["overwrite"] = {"type": "boolean", "default": False,
                                  "description": "True = allow OVERWRITING an existing file (otherwise the call is refused)"}
        schema["properties"] = props
        desc = (t.description or "") + f" [DESTRUCTIVE: {DESTRUCTIVE_TOOLS[t.name]}.]"
        ann = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
        out.append(t.model_copy(update={"inputSchema": schema, "description": desc, "annotations": ann}))
    return out


def check_call(name: str, arguments: dict) -> Optional[str]:
    """Messaggio di rifiuto se la chiamata sovrascriverebbe un file esistente senza overwrite=true, altrimenti None."""
    if name == "execute_tool_sequence":
        for idx, step in enumerate((arguments or {}).get("steps", [])):
            if not isinstance(step, dict):
                continue
            s_tool = step.get("tool") or step.get("name")
            s_args = step.get("arguments") or {}
            refusal = check_call(s_tool, s_args)
            if refusal:
                return f"Step {idx + 1} ({s_tool}): {refusal}"
        return None
    arg = OVERWRITE_GUARDS.get(name)
    if not arg or name == "save_document":      # save_document controlla da se' (conosce il file del documento)
        return None
    path = (arguments or {}).get(arg)
    if path and not (arguments or {}).get("overwrite") and os.path.exists(os.path.abspath(str(path))):
        return (f"Rifiutato: il file esiste gia' ({os.path.abspath(str(path))}) e verrebbe SOVRASCRITTO. "
                f"Se e' voluto, ripeti con overwrite=true; altrimenti scegli un altro nome.")
    return None
