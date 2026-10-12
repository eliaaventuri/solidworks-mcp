"""
Modellazione 3D: definizioni dei tool MCP (blocco 1) + smistamento verso ModelingOperations / SketchConstraintOperations.
Ogni voce: nome -> (metodo di SolidWorksAutomation, descrizione, {parametro: (tipo json | None, descrizione)}, [obbligatori]).
Tipo None = qualsiasi (id stringa, coppia [x,y], oggetto...). Gli argomenti sono passati per nome al metodo.

Convenzioni valide per tutti i tool:
 - misure in mm salvo `unit`; angoli in gradi;
 - punti 3D [x,y,z] = coordinate del MODELLO, il punto deve stare SULL'entita' (faccia/spigolo/vertice);
   usa list_entities per ottenere punti utilizzabili;
 - schizzi per nome ("Schizzo1"); se omesso e' lo schizzo attivo (che viene chiuso) o l'ultimo;
 - entita' di schizzo: id restituito dai draw_* ("S0-1-2"), "@x,y" (segmento piu' vicino), "pt@x,y" (punto), "origin".
"""

from mcp.types import Tool

S, N, B, A, O = "string", "number", "boolean", "array", "object"
_UNIT = (S, "Unita delle misure (default mm)")
_SK = (S, "Nome dello schizzo (default: attivo/ultimo)")
_ENT = (None, "Entita' di schizzo: id restituito dai draw_*, '@x,y' (segmento vicino), 'pt@x,y' (punto), 'origin'")
_PT3 = (A, "Punto [x,y,z] SULL'entita' (coordinate del modello)")
_PTS3 = (A, "Elenco di punti [[x,y,z],...], uno per entita'")
_DIR = (None, "Direzione/asse: {\"edge\":[x,y,z]} | {\"face\":[x,y,z]} | {\"plane\":\"Piano1\"} | {\"axis\":\"Asse1\"} | nome")

_TOOLS = {
    # ---------------------------------------------------------------- schizzi: quote, relazioni, stato
    "add_sketch_dimension": ("add_sketch_dimension",
        "Quota VERA dello schizzo con valore (visibile con insert_model_dimensions nei disegni). kind: auto | length | "
        "horizontal | vertical | distance | radius | diameter | angle. Con 1 entita' (linea/cerchio/arco) o 2 "
        "(distanza/angolo fra entita' o punti). Lo schizzo deve essere attivo (o indicare `sketch`).",
        {"kind": (S, "auto | length | horizontal | vertical | distance | radius | diameter | angle"),
         "entity1": _ENT, "entity2": _ENT, "entity3": _ENT,
         "value": (N, "Valore (mm o `unit`; gradi per angle)"), "unit": _UNIT,
         "orientation": (S, "horizontal | vertical per distance/length"),
         "name": (S, "Nome da dare alla quota (es. 'lunghezza' -> lunghezza@Schizzo1)"),
         "position": (A, "[x,y] posizione del testo della quota"), "sketch": _SK}, []),
    "add_sketch_relation": ("add_sketch_relation",
        "Relazione geometrica: horizontal, vertical, coincident, tangent, concentric, equal, parallel, perpendicular, "
        "symmetric (due entita' + asse), fixed, collinear, midpoint.",
        {"relation": (S, "Tipo di relazione"), "entity1": _ENT, "entity2": _ENT, "entity3": _ENT,
         "unit": _UNIT, "sketch": _SK}, ["relation"]),
    "get_sketch_definition_status": ("get_sketch_definition_status",
        "Stato dello schizzo: completamente definito / sottodefinito / sovradefinito (+ quote e entita').",
        {"sketch": _SK}, []),
    "get_sketch_plane_info": ("get_sketch_plane_info",
        "Piano e assi dello schizzo: come le coordinate (x,y) dello schizzo diventano coordinate del modello.",
        {"sketch": _SK}, []),
    "list_sketch_entities": ("list_sketch_entities", "Elenca le entita' dello schizzo con id, tipo e geometria.",
        {"sketch": _SK}, []),
    # ---------------------------------------------------------------- schizzi: nuove entita'
    "draw_construction_line": ("draw_construction_line", "Linea di costruzione (non genera profilo).",
        {"x1": (N, ""), "y1": (N, ""), "x2": (N, ""), "y2": (N, ""), "unit": _UNIT}, ["x1", "y1", "x2", "y2"]),
    "draw_centerline_axis": ("draw_centerline_axis",
        "Asse di mezzeria: usato dalla rivoluzione (asse) e dalle simmetrie.",
        {"x1": (N, ""), "y1": (N, ""), "x2": (N, ""), "y2": (N, ""), "unit": _UNIT}, ["x1", "y1", "x2", "y2"]),
    "draw_point": ("draw_point", "Punto di schizzo.", {"x": (N, ""), "y": (N, ""), "unit": _UNIT}, ["x", "y"]),
    "draw_spline": ("draw_spline", "Spline per punti [[x,y],...] (almeno 2).",
        {"points": (A, "[[x,y],...]"), "unit": _UNIT, "closed": (B, "Spline chiusa")}, ["points"]),
    "draw_slot": ("draw_slot", "Asola retta con larghezza.",
        {"x1": (N, "Centro estremo 1"), "y1": (N, ""), "x2": (N, "Centro estremo 2"), "y2": (N, ""),
         "width": (N, "Larghezza"), "unit": _UNIT, "slot_type": (S, "center_to_center | overall")},
        ["x1", "y1", "x2", "y2", "width"]),
    "draw_ellipse": ("draw_ellipse", "Ellisse.",
        {"cx": (N, ""), "cy": (N, ""), "semi_major": (N, "Semiasse maggiore"), "semi_minor": (N, "Semiasse minore"),
         "angle": (N, "Inclinazione asse maggiore (gradi)"), "unit": _UNIT}, ["cx", "cy", "semi_major", "semi_minor"]),
    "draw_arc_3point": ("draw_arc_3point", "Arco per tre punti (inizio, punto sull'arco, fine).",
        {"x1": (N, ""), "y1": (N, ""), "x2": (N, ""), "y2": (N, ""), "x3": (N, ""), "y3": (N, ""), "unit": _UNIT},
        ["x1", "y1", "x2", "y2", "x3", "y3"]),
    "sketch_fillet": ("sketch_fillet", "Raccordo di schizzo fra due segmenti o in un vertice (corner=[x,y]).",
        {"radius": (N, ""), "entity1": _ENT, "entity2": _ENT, "corner": (A, "[x,y] del vertice"), "unit": _UNIT},
        ["radius"]),
    "offset_entities": ("offset_entities", "Offset di entita' dello schizzo (catena automatica).",
        {"entities": (A, "Elenco di entita' (id o '@x,y')"), "offset": (N, "Distanza"),
         "both_directions": (B, ""), "make_construction": (B, ""), "cap_ends": (B, ""), "unit": _UNIT},
        ["entities", "offset"]),
    "convert_entities": ("convert_entities",
        "Converti entita': proietta nello schizzo attivo spigoli del modello (edge_points) o i bordi di una faccia (face_point).",
        {"edge_points": (A, "Punti [[x,y,z],...] sugli spigoli"), "face_point": _PT3,
         "chain": (B, "Seleziona la catena"), "unit": _UNIT}, []),
    "mirror_sketch_entities": ("mirror_sketch_entities", "Specchia entita' dello schizzo rispetto a una linea/asse.",
        {"entities": (A, "Entita' da specchiare"), "axis": _ENT, "unit": _UNIT, "keep_original": (B, "")},
        ["entities", "axis"]),
    "add_sketch_text": ("add_sketch_text", "Testo nello schizzo (profilo per estrusioni/tagli).",
        {"text": (S, ""), "x": (N, ""), "y": (N, ""), "height": (N, "Altezza caratteri"), "unit": _UNIT},
        ["text", "x", "y"]),
    # ---------------------------------------------------------------- feature
    "extrude_boss": ("extrude_boss",
        "Estrusione base con condizioni finali: blind | through_all | through_all_both | mid_plane | up_to_next | "
        "up_to_surface | offset_from_surface; sformo, seconda direzione (depth2/end_condition2).",
        {"sketch": _SK, "depth": (N, "Profondita"), "end_condition": (S, "blind | through_all | through_all_both | mid_plane | up_to_next | up_to_surface | offset_from_surface"),
         "depth2": (N, "Profondita seconda direzione"), "end_condition2": (S, "Condizione seconda direzione"),
         "draft_angle": (N, "Sformo (gradi)"), "draft_outward": (B, ""),
         "up_to_face_point": _PT3, "offset": (N, "Offset dalla superficie (offset_from_surface)"),
         "reverse": (B, "Inverte direzione"), "merge": (B, "Unisce al corpo esistente"),
         "start_offset": (N, "Offset iniziale"), "unit": _UNIT}, []),
    "extrude_cut": ("extrude_cut", "Taglio estruso con le stesse condizioni finali di extrude_boss.",
        {"sketch": _SK, "depth": (N, ""), "end_condition": (S, "blind | through_all | through_all_both | mid_plane | up_to_next | up_to_surface | offset_from_surface"),
         "depth2": (N, ""), "end_condition2": (S, ""), "draft_angle": (N, ""), "draft_outward": (B, ""),
         "up_to_face_point": _PT3, "offset": (N, ""), "reverse": (B, "Taglia dall'altra parte"),
         "start_offset": (N, ""), "unit": _UNIT}, []),
    "revolve_boss": ("revolve_boss",
        "Rivoluzione attorno all'asse di mezzeria dello schizzo (o `axis` = id di un segmento). thin_thickness = parete sottile.",
        {"sketch": _SK, "angle": (N, "Gradi (default 360)"), "axis": (S, "Id segmento asse"),
         "both_directions": (B, ""), "thin_thickness": (N, ""), "unit": _UNIT}, []),
    "revolve_cut": ("revolve_cut", "Taglio di rivoluzione (gole, scarichi).",
        {"sketch": _SK, "angle": (N, ""), "axis": (S, ""), "both_directions": (B, ""), "unit": _UNIT}, []),
    "sweep": ("sweep", "Sweep (base o taglio): profilo + percorso, oppure solo percorso con circular_diameter.",
        {"profile_sketch": (S, "Schizzo profilo"), "path_sketch": (S, "Schizzo percorso"), "cut": (B, ""),
         "circular_diameter": (N, "Profilo circolare senza schizzo"), "twist_angle": (N, ""),
         "keep_normal": (B, ""), "unit": _UNIT}, ["path_sketch"]),
    "loft": ("loft", "Loft fra 2 o piu' profili (schizzi in ordine) con guide opzionali.",
        {"profile_sketches": (A, "Nomi schizzi in ordine"), "guide_sketches": (A, "Nomi schizzi guida"),
         "closed": (B, ""), "cut": (B, ""), "start_tangency": (B, "")}, ["profile_sketches"]),
    "shell_body": ("shell_body", "Shell (svuotamento): spessore + facce da rimuovere scelte per coordinate.",
        {"thickness": (N, ""), "remove_faces": (A, "Punti [[x,y,z],...] sulle facce da rimuovere"),
         "outward": (B, "Spessore verso l'esterno"), "unit": _UNIT}, ["thickness", "remove_faces"]),
    "rib": ("rib", "Nervatura da uno schizzo con linea aperta che tocca le pareti (direzione materiale automatica).",
        {"sketch": _SK, "thickness": (N, ""), "both_sides": (B, "Spessore simmetrico"),
         "flip_material": (B, ""), "normal_to_sketch": (B, ""), "draft_angle": (N, ""), "unit": _UNIT}, []),
    "draft_faces": ("draft_faces", "Sformo di facce rispetto a una faccia piana neutra.",
        {"angle": (N, "Gradi"), "faces": _PTS3, "neutral_face_point": _PT3, "flip": (B, ""),
         "propagate_tangent": (B, ""), "unit": _UNIT}, ["angle", "faces", "neutral_face_point"]),
    "fillet_at_points": ("fillet_at_points", "Raccordo a raggio costante su spigoli scelti per coordinate.",
        {"radius": (N, ""), "edge_points": _PTS3, "tangent_propagation": (B, ""), "radius2": (N, ""), "unit": _UNIT},
        ["radius", "edge_points"]),
    "fillet_variable_radius": ("fillet_variable_radius", "Raccordo a raggio variabile (inizio/fine spigolo).",
        {"edge_point": _PT3, "radius_start": (N, ""), "radius_end": (N, ""), "unit": _UNIT},
        ["edge_point", "radius_start", "radius_end"]),
    "chamfer_at_points": ("chamfer_at_points", "Smusso su spigoli scelti per coordinate: distanza+angolo o distanza+distanza2.",
        {"distance": (N, ""), "edge_points": _PTS3, "angle": (N, "Default 45"), "distance2": (N, ""), "unit": _UNIT},
        ["distance", "edge_points"]),
    # ---------------------------------------------------------------- ripetizioni e simmetrie
    "linear_pattern": ("linear_pattern",
        "Ripetizione lineare di feature (nomi) in 1 o 2 direzioni. direction = {\"edge\":[x,y,z]} (spigolo parallelo) | "
        "{\"face\":[x,y,z]} (normale della faccia) | nome asse. Se le istanze escono dal corpo riprova invertendo.",
        {"features": (A, "Nomi delle feature da ripetere"), "direction1": _DIR, "count1": (N, "Numero istanze (originale incluso)"),
         "spacing1": (N, "Passo"), "direction2": _DIR, "count2": (N, ""), "spacing2": (N, ""),
         "reverse1": (B, ""), "reverse2": (B, ""), "geometry_pattern": (B, ""), "unit": _UNIT},
        ["features", "direction1", "count1", "spacing1"]),
    "circular_pattern": ("circular_pattern",
        "Ripetizione circolare di feature attorno a un asse ({\"edge\":..} | {\"face\":.. cilindrica} | {\"axis\":\"Asse1\"}).",
        {"features": (A, "Nomi delle feature"), "axis": _DIR, "count": (N, "Istanze totali"),
         "angle": (N, "Angolo totale (default 360)"), "equal_spacing": (B, ""), "reverse": (B, ""),
         "geometry_pattern": (B, ""), "unit": _UNIT}, ["features", "axis", "count"]),
    "mirror_feature": ("mirror_feature", "Specchia feature (nomi) o l'intero corpo (mirror_body) rispetto a un piano/faccia piana.",
        {"features": (A, "Nomi feature"), "plane": _DIR, "mirror_body": (B, ""), "merge": (B, ""),
         "geometry_pattern": (B, ""), "unit": _UNIT}, ["plane"]),
    # ---------------------------------------------------------------- Hole Wizard
    "create_hole": ("create_hole",
        "Foro guidato (Hole Wizard) su una faccia piana, cilindrica o inclinata, posizionato per coordinate (il foro e' "
        "normale alla faccia nel punto): simple | tapped (filettato) | countersink (svasato) | counterbore (lamato). "
        "standard: iso (default) | ansi_metric | ansi_inch | din | bsi | jis (UNI non c'e' nel database di SolidWorks). "
        "head = tipo di vite: lamato socket (cilindrica, esagono incassato) | cheese | pan | button | hex | hex_cap | "
        "hex_machine; svasato socket | flat | raised | oval; filettato bottoming. Cieco (depth) o passante (through).",
        {"kind": (S, "simple | tapped | countersink | counterbore"),
         "size": (S, "Metrica M3..M20 (anche 'M8x1.25'); ANSI pollici '#10', '1/4', '1/4-20'"),
         "face_point": _PT3, "positions": (A, "Centri [[x,y,z],...] sulla faccia"),
         "depth": (N, "Profondita (cieco)"), "through": (B, "Passante"), "diameter": (N, "Sovrascrive il diametro"),
         "thread_depth": (N, "Profondita filetto"), "unit": _UNIT,
         "standard": (S, "iso (default) | ansi_metric | ansi_inch | din | bsi | jis"),
         "head": (S, "Tipo di vite / variante (vedi descrizione)"),
         "fit": (S, "close | normal (default) | loose = Ø di passaggio ISO 273; database = valore del database")},
        ["kind", "size"]),
    # ---------------------------------------------------------------- riferimenti
    "create_reference_plane": ("create_reference_plane",
        "Piano di riferimento: offset (base = nome piano o {\"face\":[x,y,z]}) | angle (base + edge_point + angle) | three_points (points).",
        {"mode": (S, "offset | angle | three_points"), "base": (None, "Nome piano ('front','top','right') o {\"face\":[x,y,z]}"),
         "distance": (N, ""), "angle": (N, ""), "edge_point": _PT3, "points": (A, "3 vertici [[x,y,z],...]"),
         "flip": (B, ""), "unit": _UNIT}, []),
    "create_reference_axis": ("create_reference_axis",
        "Asse di riferimento: two_planes | cylinder (face_point) | edge (edge_point) | two_points (points).",
        {"mode": (S, ""), "planes": (A, "Due nomi di piano"), "face_point": _PT3, "edge_point": _PT3,
         "points": (A, ""), "unit": _UNIT}, []),
    "create_reference_point": ("create_reference_point", "Punto di riferimento: face_center | edge_center | on_edge (percent).",
        {"mode": (S, ""), "face_point": _PT3, "edge_point": _PT3, "percent": (N, ""), "unit": _UNIT}, []),
    "create_coordinate_system": ("create_coordinate_system", "Sistema di coordinate: origine (vertice) e assi X/Y/Z (spigoli).",
        {"origin_point": _PT3, "x_edge_point": _PT3, "y_edge_point": _PT3, "z_edge_point": _PT3, "unit": _UNIT,
         "x_flip": (B, "Inverte l'asse X"), "y_flip": (B, "Inverte l'asse Y"), "z_flip": (B, "Inverte l'asse Z")}, []),
    # ---------------------------------------------------------------- gestione feature
    "list_model_features": ("list_model_features", "Elenco feature con tipo, soppressione, errori e (opz.) quote.",
        {"include_dimensions": (B, "")}, []),
    "suppress_feature": ("suppress_feature", "Sopprime una feature per nome.", {"name": (S, "")}, ["name"]),
    "unsuppress_feature": ("unsuppress_feature", "Riattiva una feature soppressa.", {"name": (S, "")}, ["name"]),
    "delete_feature": ("delete_feature",
        "DISTRUTTIVO, senza annulla: elimina una feature (e lo schizzo assorbito). Richiede confirm=true; se altre feature "
        "ne dipendono rifiuta e le elenca, salvo delete_children=true (che le elimina tutte). Alternativa sicura: suppress_feature.",
        {"name": (S, ""), "delete_children": (B, "Elimina anche le feature dipendenti"),
         "confirm": (B, "Conferma esplicita dell'eliminazione (obbligatorio)")}, ["name"]),
    "rename_feature": ("rename_feature", "Rinomina una feature.", {"name": (S, ""), "new_name": (S, "")}, ["name", "new_name"]),
    "set_dimension_value": ("set_dimension_value",
        "Modifica una quota per nome ('D1@Schizzo1', 'D1@Estrusione1'), ricostruisce, riporta il nuovo volume.",
        {"name": (S, ""), "value": (N, ""), "unit": _UNIT, "rebuild": (B, "")}, ["name", "value"]),
    "get_dimension_value": ("get_dimension_value", "Legge una quota per nome.", {"name": (S, ""), "unit": _UNIT}, ["name"]),
    "rebuild_model": ("rebuild_model", "Ricostruisce il modello; riporta feature con errori e volume.",
        {"force": (B, "Ricostruzione completa")}, []),
    "rollback_to_feature": ("rollback_to_feature", "Barra di rollback: position = after | before | end.",
        {"name": (S, ""), "position": (S, "after | before | end")}, []),
    # ---------------------------------------------------------------- selezione / misure / immagini
    "select_at_point": ("select_at_point", "Seleziona faccia/spigolo/vertice per coordinate (punto sull'entita').",
        {"kind": (S, "face | edge | vertex"), "x": (N, ""), "y": (N, ""), "z": (N, ""), "unit": _UNIT,
         "append": (B, "Aggiunge alla selezione"), "mark": (N, ""), "tolerance": (N, "mm")}, ["kind", "x", "y", "z"]),
    "list_entities": ("list_entities", "Elenca facce/spigoli/vertici con un punto utilizzabile per selezionarli e il tipo.",
        {"kind": (S, "face | edge | vertex"), "unit": _UNIT, "limit": (N, "")}, []),
    "get_mass_properties": ("get_mass_properties", "Volume, massa, area, baricentro (CreateMassProperty).",
        {"unit": _UNIT}, []),
    "set_material": ("set_material", "Assegna un materiale del database SolidWorks (es. 'AISI 1020').",
        {"material": (S, "")}, []),
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


MODELING_TOOLS = [Tool(name=n, description=d, inputSchema=_schema(p, r)) for n, (m, d, p, r) in _TOOLS.items()]
MODELING_DISPATCH = {n: (m, set(p)) for n, (m, d, p, r) in _TOOLS.items()}
