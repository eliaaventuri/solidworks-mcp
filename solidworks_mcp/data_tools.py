"""
Dati ed export: definizioni dei tool MCP (blocco 3) + smistamento verso DataExportOperations (automation/data_export.py).
Ogni voce: nome -> (metodo di SolidWorksAutomation, descrizione, {parametro: (tipo json | None, descrizione)}, [obbligatori]).

Convenzioni: misure in mm salvo `unit`; angoli in gradi; massa in kg; inerzie in kg*m2 (e kg*mm2);
entita' per coordinate: {"face":[x,y,z]} | {"edge":[x,y,z]} | {"vertex":[x,y,z]} (punto SULL'entita', coordinate del modello).
"""

from mcp.types import Tool

S, N, B, A, O = "string", "number", "boolean", "array", "object"
_UNIT = (S, "Unita delle misure (default mm)")
_CFG = (S, "Nome configurazione (vuoto = quella attiva / il file)")
_CFGS = (None, "Configurazione: nome | lista | 'all' (default l'attiva)")
_ENT = (O, "Entita' per coordinate: {\"face\":[x,y,z]} | {\"edge\":[x,y,z]} | {\"vertex\":[x,y,z]}")

_TOOLS = {
    # ---------------------------------------------------------------- materiali
    "list_materials": ("list_materials",
        "Libreria materiali SolidWorks (file .sldmat, nomi nella lingua di SolidWorks: 'Lega 6061' in italiano, '6061 Alloy' in inglese). Senza argomenti: categorie con conteggio; con `category` "
        "(es. 'Acciaio', 'Plastiche', 'Leghe di alluminio') o `query` (es. '304', 'ABS'): elenco con densita' kg/m3.",
        {"category": (S, "Categoria (anche parziale)"), "query": (S, "Testo nel nome"),
         "include_properties": (B, "Aggiunge modulo elastico, snervamento, ecc."), "limit": (N, "")}, []),
    "assign_material": ("assign_material",
        "Assegna un materiale della libreria al pezzo (o a un corpo con `body`): 'AISI 304', 'Lega 6061' (SolidWorks in inglese: '6061 Alloy'). Imposta anche "
        "la proprieta' Material del modello (\"SW-Material@file\") cosi' il cartiglio dei disegni lo mostra.",
        {"material": (S, "Nome materiale (anche parziale se univoco)"), "category": (S, "Restringe la ricerca"),
         "body": (S, "Nome del corpo (default tutto il pezzo)"), "configuration": _CFGS,
         "link_title_block": (B, "Collega Material al cartiglio (default true)")}, ["material"]),
    "get_material": ("get_material", "Materiale corrente del pezzo e dei corpi, densita' usata, proprieta' Material.",
        {"body": (S, ""), "configuration": _CFG}, []),
    "link_material_to_title_block": ("link_material_to_title_block",
        "Imposta Material = \"SW-Material@file\" sul modello: il cartiglio del disegno mostra il materiale assegnato.", {}, []),
    # ---------------------------------------------------------------- massa
    "get_part_mass_properties": ("get_part_mass_properties",
        "Proprieta' di massa complete di pezzo o corpo: massa, volume, area, densita' usata, baricentro, momenti e assi principali, "
        "tensore d'inerzia nel baricentro e nell'origine (kg*m2 e kg*mm2), stato di sovrascrittura.",
        {"body": (S, "Nome corpo (default tutto il pezzo)"), "configuration": _CFG, "unit": _UNIT}, []),
    "set_mass_override": ("set_mass_override",
        "Massa sovrascritta (kg) con baricentro opzionale. Senza `mass` rimuove la sovrascrittura.",
        {"mass": (N, "kg"), "center_of_mass": (A, "[x,y,z] (default il baricentro calcolato)"), "unit": _UNIT,
         "configuration": _CFG}, []),
    # ---------------------------------------------------------------- proprieta' personalizzate
    "list_custom_properties": ("list_custom_properties",
        "Elenca le proprieta' personalizzate del documento attivo (file) o di una configurazione, con valore/espressione e valore risolto.",
        {"configuration": _CFG}, []),
    "get_custom_property": ("get_custom_property", "Legge una proprieta' (valore e risolto, es. SW-Mass).",
        {"name": (S, ""), "configuration": _CFG}, ["name"]),
    "set_custom_property": ("set_custom_property",
        "Scrive una proprieta' personalizzata (file o configurazione). Il valore puo' essere un'espressione: 'SW-Mass@pezzo.SLDPRT', "
        "'SW-Material@pezzo.SLDPRT' (virgolette automatiche). type: text | number | double | date | yesno.",
        {"name": (S, ""), "value": (S, ""), "configuration": _CFG, "type": (S, "text | number | double | date | yesno")},
        ["name", "value"]),
    "delete_custom_property": ("delete_custom_property", "Elimina una proprieta' personalizzata.",
        {"name": (S, ""), "configuration": _CFG}, ["name"]),
    # ---------------------------------------------------------------- variabili globali / equazioni
    "list_equations": ("list_equations", "Equazioni e variabili globali (valori nelle unita' del documento).", {}, []),
    "set_global_variable": ("set_global_variable",
        "Crea o modifica una variabile globale (\"nome\" = valore; numero in mm o espressione). Ricostruisce e riporta errori e volume.",
        {"name": (S, ""), "value": (None, "Numero o espressione (es. 50 oppure '\"altra\"*2')")}, ["name", "value"]),
    "delete_global_variable": ("delete_global_variable", "Elimina una variabile globale.", {"name": (S, "")}, ["name"]),
    "add_equation": ("add_equation",
        "Aggiunge un'equazione, es. '\"D1@Schizzo1\" = \"lunghezza\" * 2' (quota guidata da variabile). Verifica: se produce errori viene rimossa.",
        {"equation": (S, "")}, ["equation"]),
    "update_equation": ("update_equation", "Modifica l'equazione di indice dato (vedi list_equations).",
        {"index": (N, ""), "equation": (S, "")}, ["index", "equation"]),
    "delete_equation": ("delete_equation", "Elimina l'equazione di indice dato.", {"index": (N, "")}, ["index"]),
    "evaluate_equations": ("evaluate_equations", "Ricalcola le equazioni, ricostruisce e verifica (errori feature, volume, valori).", {}, []),
    # ---------------------------------------------------------------- configurazioni del pezzo
    "list_part_configurations": ("list_part_configurations",
        "Configurazioni del pezzo/assieme e quella attiva; con include_volume attiva ciascuna e riporta il volume.",
        {"include_volume": (B, "")}, []),
    "add_part_configuration": ("add_part_configuration", "Aggiunge una configurazione (diventa attiva salvo activate=false).",
        {"name": (S, ""), "comment": (S, ""), "activate": (B, "")}, ["name"]),
    "activate_part_configuration": ("activate_part_configuration", "Attiva una configurazione di un pezzo/assieme e ricostruisce.",
        {"name": (S, "")}, ["name"]),
    "delete_part_configuration": ("delete_part_configuration", "Elimina una configurazione (non l'unica).",
        {"name": (S, "")}, ["name"]),
    "set_configuration_dimension": ("set_configuration_dimension",
        "Imposta una quota ('D1@Schizzo1') solo nelle configurazioni indicate (nome | lista | 'all'; default l'attiva).",
        {"dimension": (S, ""), "value": (N, ""), "configuration": _CFGS, "unit": _UNIT}, ["dimension", "value"]),
    "set_configuration_suppression": ("set_configuration_suppression",
        "Sopprime/riattiva una feature solo nelle configurazioni indicate (nome | lista | 'all'; default l'attiva).",
        {"feature": (S, ""), "suppressed": (B, "Default true"), "configuration": _CFGS}, ["feature"]),
    # ---------------------------------------------------------------- export / import
    "export_model": ("export_model",
        "Esporta pezzo/assieme: stl | 3mf (stampa 3D) | step | iges | x_t | x_b | sat | pdf (PDF 3D) | eprt/easm (eDrawings); formato dall'estensione. "
        "STL/3MF: quality coarse|fine|custom (+deviation mm, angle gradi), binary, units. STEP: step_ap 203|214|242. Verifica il file "
        "(STL: triangoli e box vs modello; STEP: MANIFOLD_SOLID_BREP).",
        {"filepath": (S, ""), "format": (S, "Se diverso dall'estensione"), "configuration": _CFG,
         "quality": (S, "coarse | fine | custom"), "deviation": (N, "mm, per custom"), "angle": (N, "gradi, per custom"),
         "binary": (B, "STL binario (default true)"), "step_ap": (N, "203 | 214 | 242"), "units": (S, "mm | cm | m | inch (STL)"),
         "iges_representation": (S, "surfaces | brep | curves"), "one_file": (B, "Assieme STL in un solo file"),
         "verify": (B, "Default true")}, ["filepath"]),
    "inspect_export_file": ("inspect_export_file",
        "Legge e verifica un file esportato: STL (triangoli, bounding box), 3MF, STEP (schema, MANIFOLD_SOLID_BREP), IGES, Parasolid, PDF 3D.",
        {"filepath": (S, "")}, ["filepath"]),
    "import_model": ("import_model",
        "Apre STEP/IGES/Parasolid/STL come pezzo e restituisce i corpi importati (volume, box). STL: import_as solid|surface|graphics, units.",
        {"filepath": (S, ""), "import_as": (S, "solid | surface | graphics (STL)"), "units": (S, "mm | cm | m | inch (STL)")}, ["filepath"]),
    "export_model_image": ("export_model_image",
        "Immagine PNG/JPG/BMP del pezzo/assieme. view: isometric|front|back|left|right|top|bottom|trimetric|dimetric; "
        "style: shaded_edges|shaded|hidden_lines|hidden_gray|wireframe; width/height px (PNG/BMP); hide_reference=true (default) "
        "nasconde piani, assi, origini, punti e schizzi; white_background per lo sfondo bianco.",
        {"filepath": (S, ""), "view": (S, ""), "style": (S, ""), "width": (N, "pixel"), "height": (N, "pixel"),
         "hide_reference": (B, "Default true"), "white_background": (B, ""), "zoom_to_fit": (B, "")}, ["filepath"]),
    # ---------------------------------------------------------------- misure
    "measure_entities": ("measure_entities",
        "Misura fra due entita' per coordinate (o su una): distanza, distanza normale, delta XYZ, angolo (gradi), parallele/perpendicolari; "
        "raggio/diametro/area/lunghezza se applicabili.",
        {"entity1": _ENT, "entity2": _ENT, "unit": _UNIT}, ["entity1"]),
    "measure_face": ("measure_face",
        "Tipo e misure della faccia che contiene il punto: area; cilindrica: raggio, diametro, asse; piana: normale; sfera/cono/toro.",
        {"x": (N, ""), "y": (N, ""), "z": (N, ""), "unit": _UNIT}, ["x", "y", "z"]),
    "get_bounding_box": ("get_bounding_box",
        "Bounding box allineato agli assi di pezzo (esatto), corpo o assieme: min, max, dimensioni, centro.",
        {"body": (S, ""), "unit": _UNIT}, []),
}


def _schema(props, required):
    p = {}
    for k, (t, desc) in props.items():
        d = {}
        if t:
            d["type"] = t
        if desc:
            d["description"] = desc
        p[k] = d
    return {"type": "object", "properties": p, "required": required}


DATA_TOOLS = [Tool(name=n, description=d, inputSchema=_schema(p, r)) for n, (m, d, p, r) in _TOOLS.items()]
DATA_DISPATCH = {n: (m, set(p)) for n, (m, d, p, r) in _TOOLS.items()}
