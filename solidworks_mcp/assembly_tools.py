"""
Assiemi: definizioni dei tool MCP (blocco 2) + smistamento verso AssemblyOperations (automation/assembly.py, assembly_analysis.py).
Ogni voce: nome -> (metodo di SolidWorksAutomation, descrizione, {parametro: (tipo json | None, descrizione)}, [obbligatori]).

Convenzioni:
 - misure in mm salvo `unit`; angoli in gradi; coordinate [x,y,z] = coordinate dell'ASSIEME;
 - componenti per nome istanza ("perno-1", come in list_components);
 - entita' degli accoppiamenti: "Piano frontale@perno-1" | "Assi1@staffa-1" | "Origine@perno-1" | {"face":[x,y,z]} |
   {"edge":[x,y,z]} | {"component":"perno-1","plane":"Piano destro"} (punti SULL'entita', in coordinate assieme);
 - le operazioni geometriche richiudono la vista esplosa se e' attiva.
"""

from mcp.types import Tool

S, N, B, A, O = "string", "number", "boolean", "array", "object"
_UNIT = (S, "Unita delle misure (default mm)")
_COMP = (S, "Nome istanza del componente (es. 'perno-1')")
_COMPS = (A, "Nomi istanza dei componenti (es. ['vite-1'])")
_ENT = (None, "Entita': 'Piano frontale@perno-1' | 'Assi1@staffa-1' | {\"face\":[x,y,z]} | {\"edge\":[x,y,z]} | "
              "{\"component\":'perno-1',\"plane\":'Piano destro'}")
_POS = (A, "[x,y,z] posizione dell'ORIGINE del componente")
_ROT = (A, "[rx,ry,rz] rotazione in gradi (X poi Y poi Z, assi dell'assieme)")

_TOOLS = {
    # ---------------------------------------------------------------- componenti
    "insert_component": ("insert_component",
        "Inserisce un componente (pezzo o sotto-assieme) da file con l'origine in (x,y,z) e rotazione opzionale. L'assieme attivo "
        "deve essere un assieme. fixed=true lo fissa.",
        {"file_path": (S, "Path del .SLDPRT/.SLDASM"), "x": (N, ""), "y": (N, ""), "z": (N, ""), "rotation": _ROT,
         "configuration": (S, "Configurazione del componente"), "fixed": (B, "Componente fisso"), "unit": _UNIT}, ["file_path"]),
    "insert_components": ("insert_components",
        "Inserisce piu' istanze dello stesso file: `positions` [[x,y,z],..] oppure `start`+`step` con `count` istanze.",
        {"file_path": (S, ""), "count": (N, "Numero istanze"), "positions": (A, "[[x,y,z],...]"), "start": _POS,
         "step": (A, "[dx,dy,dz] fra un'istanza e la successiva"), "rotation": _ROT, "fixed": (B, ""), "unit": _UNIT},
        ["file_path"]),
    "set_component_fixed": ("set_component_fixed", "Fissa (fixed=true) o rende mobile (fixed=false) un componente.",
        {"component": _COMP, "fixed": (B, "")}, ["component"]),
    "list_components": ("list_components",
        "Elenco componenti: nome istanza, file, configurazione, posizione (mm) e trasformazione (rotazione, matrice), "
        "fisso/mobile, soppresso, nascosto, stato dei vincoli.",
        {"top_level_only": (B, "Solo primo livello (default true)"), "include_details": (B, "")}, []),
    "replace_component": ("replace_component", "Sostituisce un componente con un altro file (replace_all = tutte le istanze).",
        {"component": _COMP, "new_file": (S, "Path del nuovo file"), "configuration": (S, ""),
         "replace_all": (B, ""), "reattach_mates": (B, "Riaggancia gli accoppiamenti (default true)")}, ["component", "new_file"]),
    "suppress_component": ("suppress_component", "Sopprime (suppressed=true) o riattiva un componente.",
        {"component": _COMP, "suppressed": (B, "")}, ["component"]),
    "delete_component": ("delete_component", "Elimina un componente dall'assieme (con i suoi accoppiamenti).",
        {"component": _COMP}, ["component"]),
    "set_component_visibility": ("set_component_visibility", "Nasconde (visible=false) o mostra un componente.",
        {"component": _COMP, "visible": (B, "")}, ["component"]),
    "open_component": ("open_component",
        "Apre il documento di un componente e lo rende attivo (usa activate_document per tornare all'assieme).",
        {"component": _COMP}, ["component"]),
    "activate_document": ("activate_document", "Rende attivo un documento aperto (titolo, es. 'Assieme1').",
        {"name": (S, "Titolo del documento")}, ["name"]),
    "component_circular_pattern": ("component_circular_pattern",
        "Ripetizione circolare di componenti attorno a un asse ('Assi1@staffa-1' o faccia cilindrica {\"face\":[x,y,z]}).",
        {"components": _COMPS, "axis": _ENT, "count": (N, "Istanze totali (seme incluso)"),
         "angle": (N, "Angolo totale (default 360)"), "equal_spacing": (B, ""), "reverse": (B, ""), "unit": _UNIT},
        ["components", "axis"]),
    "component_linear_pattern": ("component_linear_pattern",
        "Ripetizione lineare di componenti in 1 o 2 direzioni (spigolo {\"edge\":[x,y,z]}, asse o faccia piana).",
        {"components": _COMPS, "direction1": _ENT, "count1": (N, ""), "spacing1": (N, "Passo"), "direction2": _ENT,
         "count2": (N, ""), "spacing2": (N, ""), "reverse1": (B, ""), "reverse2": (B, ""), "unit": _UNIT},
        ["components", "direction1"]),
    "component_derived_pattern": ("component_derived_pattern",
        "Ripetizione guidata da una ripetizione di feature di un pezzo dell'assieme (es. viti sulla ripetizione di fori della flangia).",
        {"components": _COMPS, "pattern_feature": (S, "Nome della ripetizione nel pezzo, es. 'RipetizioneCircolare1'"),
         "pattern_component": _COMP}, ["components", "pattern_feature", "pattern_component"]),
    "mirror_components": ("mirror_components",
        "Specchia componenti rispetto a un piano. Default: crea ISTANZE speculari dello stesso file; orientation (0..3, misurato: 0 = "
        "180 gradi attorno a X, 1 = 180 gradi attorno a Z, 2 = nessuna rotazione, 3 = 180 gradi attorno a Y) sceglie come e' ruotata "
        "l'istanza. opposite_hand=true crea invece, per ogni componente, un NUOVO PEZZO speculare (geometria riflessa, 'versione "
        "opposta') salvato come <nome><name_suffix>.SLDPRT in `folder` (default: cartella del pezzo originale); riporta volume e "
        "baricentro (nel pezzo e nell'assieme). Un file esistente non viene sovrascritto senza overwrite=true.",
        {"components": _COMPS, "plane": (None, "'Piano destro' dell'assieme | 'Piano frontale@staffa-1' | {\"face\":[x,y,z]}"),
         "orientation": (N, "Orientamento dell'istanza: 0, 1, 2, 3 (solo senza opposite_hand)"),
         "opposite_hand": (B, "true = crea nuovi pezzi speculari (versione opposta) invece di istanze"),
         "name_suffix": (S, "Suffisso del nome del nuovo file (default '_mirror')"),
         "folder": (S, "Cartella dei nuovi file (default: quella del pezzo originale)"),
         "overwrite": (B, "true = consente di sovrascrivere un file esistente"),
         "align_exact": (B, "opposite_hand: mette il nuovo pezzo esattamente nell'immagine speculare dell'originale (default true; "
                            "SolidWorks sceglie l'orientamento da una preferenza che varia fra sessioni)"), "unit": _UNIT}, ["components", "plane"]),
    "move_component": ("move_component",
        "Sposta/ruota un componente MOBILE rispettando gli accoppiamenti: relativo (dx,dy,dz, rotate_by) o assoluto (position, rotation). "
        "Il movimento e' ridotto ai SOLI gradi di liberta' lasciati dagli accoppiamenti (misurati sul componente): es. un perno con il "
        "solo concentrico trasla e ruota solo lungo/attorno al proprio asse; il resto e' scartato e riportato in `ignored`/`applied`. "
        "Per gli accoppiamenti a limite usa edit_mate(value).",
        {"component": _COMP, "dx": (N, ""), "dy": (N, ""), "dz": (N, ""), "position": _POS, "rotation": _ROT,
         "rotate_by": (A, "[rx,ry,rz] gradi relativi"), "respect_mates": (B, "Default true"), "unit": _UNIT}, ["component"]),
    # ---------------------------------------------------------------- accoppiamenti
    "add_mate": ("add_mate",
        "Accoppiamento fra due entita' di componenti: coincident | parallel | perpendicular | tangent | concentric | distance | "
        "angle | lock | symmetric (entity3 = piano di simmetria) | width (entity1+entity2 facce larghezza, tab_entities = linguetta) | "
        "gear (gear_ratio=[a,b]) | screw (pitch). Distanza in mm (distance), angolo in gradi (angle); limite con min_value/max_value; "
        "align: closest | aligned | anti_aligned; flip inverte. Fra due assi di riferimento il concentrico diventa coincidente. "
        "Entita' anche del tipo 'Piano destro' (piano dell'ASSIEME, es. piano di simmetria). Larghezza (width) e vite (screw) si creano "
        "con i dati dell'accoppiamento (AddMate5 le rifiuta/ignora). Limiti distanza/angolo: poi si muovono con edit_mate(value). "
        "ATTENZIONE: blocco (lock), ingranaggio (gear) e vite (screw) sono creati e letti correttamente ma SolidWorks non li fa rispettare "
        "dal solutore via API (SetTransformAndSolve2/DragOperator): vedi LIMITI.md C5.",
        {"mate_type": (S, "coincident|parallel|perpendicular|tangent|concentric|distance|angle|lock|symmetric|width|gear|screw"),
         "entity1": _ENT, "entity2": _ENT, "entity3": _ENT, "align": (S, "closest | aligned | anti_aligned"),
         "flip": (B, ""), "distance": (N, "mm"), "angle": (N, "gradi"), "min_value": (N, "Limite minimo (distanza mm / angolo gradi)"),
         "max_value": (N, "Limite massimo"), "gear_ratio": (A, "[numeratore, denominatore]"), "pitch": (N, "Passo vite (mm/giro)"),
         "width_mode": (S, "centered | free | dimension | percent"), "tab_entities": (A, "Entita' linguetta (width)"),
         "lock_rotation": (B, "Blocca la rotazione (concentrico)"), "unit": _UNIT}, ["mate_type", "entity1", "entity2"]),
    "list_mates": ("list_mates", "Elenco accoppiamenti: nome, tipo, allineamento, componenti, valore, soppresso, in errore.", {}, []),
    "delete_mate": ("delete_mate",
        "Elimina un accoppiamento per nome. Misura i gradi di liberta' di tutti i componenti mobili prima e dopo (anche per effetto di "
        "catene: un perno accoppiato a una boccola segue la boccola) e riporta quelli diventati sottovincolati (`freed_components`, "
        "`freed_not_in_mate`); le posizioni non cambiano.",
        {"name": (S, "Nome (come in list_mates)"), "check_dof": (B, "Confronta i gradi di liberta' prima/dopo (default true)")},
        ["name"]),
    "edit_mate": ("edit_mate",
        "Modifica un accoppiamento: valore (mm / gradi), limiti min/max (accoppiamenti a limite), inversione, soppressione. Nei "
        "limite-distanza/angolo il valore e' la posizione corrente: fuori dall'intervallo viene rifiutato e si riportano i limiti.",
        {"name": (S, ""), "value": (N, ""), "flip": (B, ""), "suppress": (B, ""), "max_value": (N, ""), "min_value": (N, ""),
         "unit": _UNIT}, ["name"]),
    "get_assembly_status": ("get_assembly_status",
        "Stato dei vincoli: completamente vincolato o no, componenti sotto/sovravincolati, gradi di liberta', accoppiamenti in errore.",
        {"probe_dof": (B, "Misura i moti liberi dei componenti non vincolati (default true; li sposta di poco e li ripristina)")}, []),
    # ---------------------------------------------------------------- vista esplosa
    "create_exploded_view": ("create_exploded_view",
        "Crea una vista esplosa con passi [{components:['perno-1'], direction:'x'|'-y'|[1,1,0]|entita', distance:40, reverse}] "
        "(direzione libera = vettore qualsiasi, scomposto in passi X/Y/Z; direzione di un'entita' = spigolo/asse/faccia cilindrica, es. "
        "{\"edge\":[x,y,z]}) oppure passi RADIALI [{components:[..], radial_axis:{\"face\":[x,y,z],\"component\":\"staffa-1\"}, "
        "distance:30, angle:30, diverge:false}] (si allontanano dall'asse e ruotano di `angle` gradi). La rotazione nei passi di "
        "traslazione (rotate_angle) non viene memorizzata da SolidWorks (rotation_applied=false). Riporta le pose esplose. "
        "keep_exploded=false richiude l'esploso.",
        {"steps": (A, "Elenco passi"), "unit": _UNIT, "keep_exploded": (B, "")}, ["steps"]),
    "add_explode_step": ("add_explode_step",
        "Aggiunge un passo alla vista esplosa: traslazione (direction x|y|z|-x.. | vettore libero [vx,vy,vz] | entita') o radiale "
        "(radial_axis + distance + angle). Riporta le pose esplose.",
        {"components": _COMPS, "direction": (None, "x|y|z|-x|-y|-z, vettore libero [vx,vy,vz] o entita' (spigolo/asse/faccia cilindrica)"),
         "distance": (N, ""), "reverse": (B, ""), "rotate_angle": (N, "Non memorizzata da SolidWorks nei passi di traslazione"),
         "rotate_axis": (S, ""), "radial_axis": (None, "Faccia cilindrica/asse per il passo RADIALE"),
         "angle": (N, "Rotazione (gradi) del passo radiale"), "diverge": (B, "Radiale divergente dall'asse"), "unit": _UNIT},
        ["components"]),
    "auto_explode": ("auto_explode",
        "Esplosione automatica. mode='native' = AutoExplode di SolidWorks (un passo 'Catena', direzione scelta da SolidWorks; non sempre "
        "produce passi); mode='mates' = euristica dagli accoppiamenti (ordine di smontaggio dalla profondita' di accoppiamento dal "
        "componente base, direzione lungo l'asse concentrico, verso dal lato della testa, distanze dai bounding box con distanza minima "
        "`gap` fra i componenti; riporta `bbox_overlaps` dello stato esploso reale); 'auto' = nativa poi 'mates'; 'axis' (default) = un "
        "passo per componente lungo `axis`, distanziati di `gap`.",
        {"axis": (S, "x|y|z (solo mode=axis)"), "gap": (N, "mode=axis: distanza fra componenti successivi; mode=mates: distanza minima fra box (mm)"),
         "base_component": _COMP, "mode": (S, "axis | native | mates | auto"), "unit": _UNIT}, []),
    "show_exploded": ("show_exploded", "Esplode (true) o comprime (false) l'assieme.",
        {"exploded": (B, ""), "view_name": (S, "")}, []),
    "list_exploded_views": ("list_exploded_views",
        "Viste esplose e passi della configurazione attiva (tipo, distanza, componenti); se l'assieme e' esploso anche le pose esplose.",
        {}, []),
    "add_explode_lines": ("add_explode_lines",
        "Linee di esplosione (route lines) nella vista esplosa: collega con una retta le facce cilindriche coassiali di componenti "
        "diversi (perno-boccola-foro, vite-foro). groups = liste di componenti da collegare, oppure vuoto = automatico (tutti gli assi "
        "condivisi da almeno 2 componenti). Poi salva l'assieme: le viste esplose dei disegni mostrano le linee.",
        {"groups": ("array", "Es. [[\"perno-1\",\"boccola-1\",\"staffa-1\"],[\"vite-1\",\"staffa-1\"]]; vuoto = automatico"),
         "direction": ("string", "x | y | z | auto (default: la direzione con piu linee)"),
         "view_name": ("string", "Vista esplosa (default la prima)"),
         "tolerance": ("number", "Scarto laterale massimo fra assi, mm (default 0.5)")}, []),
    "delete_explode_step": ("delete_explode_step", "Elimina un passo di esplosione per nome.",
        {"step": (S, "Nome passo (come in list_exploded_views)")}, ["step"]),
    # ---------------------------------------------------------------- analisi
    "check_interference": ("check_interference",
        "Rileva le interferenze fra componenti (nella posizione reale, non esplosa): coppie e volume (mm3). `components` limita alle "
        "coppie che li coinvolgono.",
        {"components": _COMPS, "include_coincident": (B, "Conta come interferenza anche le facce coincidenti"),
         "treat_subassemblies_as_components": (B, "")}, []),
    "check_clearance": ("check_clearance", "Gioco (distanza minima) fra due componenti o due entita'.",
        {"entity1": _ENT, "entity2": _ENT, "unit": _UNIT}, ["entity1", "entity2"]),
    "get_assembly_mass_properties": ("get_assembly_mass_properties",
        "Massa, volume, area, baricentro dell'assieme + massa per file e verifica massa = somma dei componenti.",
        {"unit": _UNIT}, []),
    "count_components": ("count_components", "Conteggio dei componenti per file (istanze, soppresse).",
        {"top_level_only": (B, "")}, []),
    # ---------------------------------------------------------------- configurazioni
    "list_assembly_configurations": ("list_assembly_configurations", "Configurazioni dell'assieme e quella attiva.", {}, []),
    "add_assembly_configuration": ("add_assembly_configuration", "Aggiunge una configurazione all'assieme.",
        {"name": (S, ""), "comment": (S, ""), "activate": (B, "")}, ["name"]),
    "activate_assembly_configuration": ("activate_assembly_configuration", "Attiva una configurazione dell'assieme.",
        {"name": (S, "")}, ["name"]),
    "set_component_configuration": ("set_component_configuration", "Cambia la configurazione usata da un componente.",
        {"component": _COMP, "configuration": (S, "")}, ["component", "configuration"]),
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


ASSEMBLY_TOOLS = [Tool(name=n, description=d, inputSchema=_schema(p, r)) for n, (m, d, p, r) in _TOOLS.items()]
ASSEMBLY_DISPATCH = {n: (m, set(p)) for n, (m, d, p, r) in _TOOLS.items()}
