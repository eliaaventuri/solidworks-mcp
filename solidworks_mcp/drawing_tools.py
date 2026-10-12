"""
Drawing (messe in tavola) tool definitions for the MCP server.
Each entry: name -> (automation method, description, {param: (json type, description)}, [required]).
Arguments are passed by name to the method of SolidWorksAutomation (DrawingOperations mixin).
"""

from mcp.types import Tool

S, N, B, A, O = "string", "number", "boolean", "array", "object"
_VIEW = (S, "Nome della vista (come da list_drawing_views, anche parziale) o indice; default: prima vista modello")
_UNIT = (S, "Unita delle misure (default mm)")
_SCALE = (S, "Scala: numero (0.5, 2) o 'A:B' (es. '1:2'); vuoto = automatica")

_TOOLS = {
    "create_drawing": ("create_drawing",
        "Crea un disegno da un pezzo/assieme (path del modello o documento attivo salvato). Formato A4..A0, "
        "orizzontale/verticale, primo diedro (default, ISO europeo) o terzo diedro, scala, template, cartiglio ISO.",
        {"model_path": (S, "Path del .SLDPRT/.SLDASM (vuoto = documento attivo, salvato)"),
         "paper_size": (S, "A4, A3, A2, A1, A0 (default A3), oppure auto: il foglio (A4/A3, poi piu grandi) e la scala li sceglie add_standard_views"),
         "orientation": (S, "landscape | portrait"),
         "projection": (S, "first (primo diedro, default) | third"),
         "scale": _SCALE, "template": (S, "Path template .drwdot (default: quello di SolidWorks)"),
         "sheet_format": (S, "iso (default) | din | none | path .slddrt"),
         "add_views": (B, "Inserisce subito frontale, superiore, destra e isometrica"),
         "save_as": (S, "Salva subito il disegno con questo nome (il cartiglio mostra il nome file come N. disegno)"),
         "save_model": (B, "Salva il modello dopo aver aggiunto le proprieta del cartiglio (default true)")}, []),
    "add_standard_views": ("add_standard_views",
        "Viste standard con posizionamento e scala automatici secondo il diedro del foglio. "
        "views: front, top, bottom, left, right, back, isometric, dimetric, trimetric.",
        {"views": (A, "Elenco viste (default front, top, right, isometric)"), "scale": _SCALE,
         "model_path": (S, "Modello (default: quello delle viste esistenti)"),
         "x_gap": (N, "Distanza fra le viste"), "unit": _UNIT,
         "exploded": (B, "Vista esplosa nelle viste isometriche/dimetriche/trimetriche (serve una vista esplosa nell'assieme, salvato dopo averla creata)")}, []),
    "add_model_view": ("add_model_view",
        "Una vista con orientamento scelto (front/top/.../isometric o nome di vista del modello) nella posizione x,y del foglio.",
        {"orientation": (S, "Orientamento"), "x": (N, "X sul foglio (vuoto = posto libero automatico)"), "y": (N, "Y sul foglio"),
         "scale": _SCALE, "model_path": (S, "Modello"), "unit": _UNIT,
         "exploded": (B, "Mostra l'assieme ESPLOSO (serve una vista esplosa nell'assieme, salvato dopo averla creata)"),
         "new_sheet_if_full": (B, "Default true: se non c'e posto la vista va su un nuovo foglio (stesso formato/scala)")}, ["orientation"]),
    "add_projected_view": ("add_projected_view",
        "Vista proiettata da una vista madre: up, down, left, right, up_left, up_right, down_left, down_right.",
        {"parent_view": _VIEW, "direction": (S, "Direzione"), "distance": (N, "Distanza dalla madre"), "unit": _UNIT},
        ["direction"]),
    "add_section_view": ("add_section_view",
        "Sezione da una vista madre con linea orizzontale/verticale (offset dal centro della vista), per due punti, "
        "a gradini (orientation=stepped) o allineata (orientation=aligned) con una poligonale in points. "
        "La vista si allinea alla madre se c'e posto.",
        {"parent_view": _VIEW, "orientation": (S, "horizontal | vertical | points | stepped | aligned"),
         "offset": (N, "Distanza della linea dal centro della vista"),
         "points": (A, "[x1,y1,x2,y2] relativi al centro vista (points); poligonale [x1,y1,x2,y2,x3,y3,...] (stepped/aligned)"),
         "label": (S, "Etichetta (A, B...)"), "flip": (B, "Inverte la direzione di vista"),
         "view_x": (N, "X della vista risultante"), "view_y": (N, "Y della vista risultante"), "unit": _UNIT}, []),
    "add_detail_view": ("add_detail_view",
        "Vista di dettaglio da un cerchio (centro relativo al centro vista, raggio) con etichetta e scala.",
        {"parent_view": _VIEW, "center_x": (N, "X del centro del cerchio"), "center_y": (N, "Y del centro"),
         "radius": (N, "Raggio"), "label": (S, "Etichetta"), "scale": _SCALE,
         "view_x": (N, "X vista"), "view_y": (N, "Y vista"), "unit": _UNIT}, []),
    "add_broken_out_section": ("add_broken_out_section",
        "Sezione locale: rettangolo (relativo al centro vista) tagliato fino alla profondita indicata.",
        {"parent_view": _VIEW, "x1": (N, ""), "y1": (N, ""), "x2": (N, ""), "y2": (N, ""),
         "depth": (N, "Profondita di taglio"), "unit": _UNIT}, []),
    "add_break_view": ("add_break_view",
        "Vista interrotta con due linee di interruzione (posizioni relative al centro vista).",
        {"parent_view": _VIEW, "orientation": (S, "vertical | horizontal"), "position1": (N, ""),
         "position2": (N, ""), "style": (N, "0 retta tratteggiata, 1-2 zig-zag, 3 curva libera (ISO, default)"), "unit": _UNIT}, []),
    "add_auxiliary_view": ("add_auxiliary_view",
        "Vista ausiliaria perpendicolare a uno spigolo della vista madre (punto sullo spigolo in coordinate foglio).",
        {"parent_view": _VIEW, "edge_x": (N, "X di un punto sullo spigolo"), "edge_y": (N, "Y"),
         "view_x": (N, ""), "view_y": (N, ""), "flip": (B, ""), "label": (S, ""), "unit": _UNIT},
        ["edge_x", "edge_y"]),
    "add_crop_view": ("add_crop_view",
        "Ritaglia una vista con un profilo chiuso: cerchio (centro, raggio), rettangolo (centro, width x height) o poligono "
        "(points). Coordinate relative al centro vista, in unita del modello.",
        {"parent_view": _VIEW, "center_x": (N, ""), "center_y": (N, ""), "radius": (N, "Raggio (circle)"), "unit": _UNIT,
         "shape": (S, "circle (default) | rectangle | polygon"), "width": (N, "Larghezza (rectangle)"),
         "height": (N, "Altezza (rectangle)"), "points": (A, "[x1,y1,x2,y2,x3,y3,...] (polygon)")}, []),
    "insert_model_dimensions": ("insert_model_dimensions",
        "Importa le quote del modello nella vista (o in tutte).",
        {"view": _VIEW, "all_views": (B, "Tutte le viste"),
         "include_hidden_feature_dims": (B, "Include quote di feature nascoste"),
         "arrange": (B, "Dopo l'importazione riordina secondo ISO 129 (default true): duplicati e quote di smusso tolti, "
                        "quote radiali degli alberi sostituite da quote Ø, ingombri e fori, impilamento a passo costante")}, []),
    "arrange_drawing_dimensions": ("arrange_drawing_dimensions",
        "Riordina le quote del foglio attivo secondo ISO 129: toglie duplicati (anche fra viste) e quote di smusso (-> nota), "
        "sostituisce le quote radiali degli alberi con quote lineari Ø, aggiunge ingombri e diametri dei fori mancanti, "
        "impila le quote (orizzontali sopra/sotto, verticali a destra/sinistra, passo costante ~8 mm a 10 mm dal contorno, "
        "dalla piu corta alla piu lunga), porta i diametri dei cerchi fuori dal contorno e contiene gli archi angolari.",
        {"view": _VIEW, "pitch": (N, "Passo fra le righe di quote, mm (default 8)"),
         "first_offset": (N, "Distanza della prima riga dal contorno, mm (default 10)"),
         "cleanup": (B, "Rimuove duplicati e quote di smusso (default true)"), "unit": _UNIT}, []),
    "get_drawing_layout": ("get_drawing_layout",
        "Inventario geometrico del foglio attivo (mm): foglio, cartiglio, viste e annotazioni con riquadro; per le quote "
        "vista, asse, lato, distanza dal contorno e riga. Serve a verificare sovrapposizioni e uscite dal foglio.", {}, []),
    "set_dimension_tolerance": ("set_dimension_tolerance",
        "Tolleranza e precisione di una quota: simmetrica, bilaterale, limiti, min/max, classi ISO (es. H7/g6).",
        {"dimension": (S, "Nome della quota (D1@Schizzo1@pezzo.Part), o testo/valore mostrato (es. 30,00)"),
         "tolerance_type": (S, "none | basic | bilateral | limit | symmetric | min | max | fit | fit_with_tol | fit_tol_only"),
         "upper": (N, "Scostamento superiore (simmetrica: +-upper), unita del documento"),
         "lower": (N, "Scostamento inferiore (positivo = sotto)"),
         "hole_fit": (S, "Classe del foro, es. H7"), "shaft_fit": (S, "Classe dell'albero, es. g6"),
         "precision": (N, "Cifre decimali della quota (0..8)"), "tol_precision": (N, "Cifre decimali della tolleranza"),
         "view": _VIEW, "unit": _UNIT,
         "apply_to_model": (B, "Default false: la tolleranza resta SOLO sul disegno (una quota importata dal modello e' sostituita da "
                               "una quota di riferimento identica). true = scrive la tolleranza anche nella quota pilota del modello")},
        ["dimension"]),
    "add_hole_table": ("add_hole_table",
        "Tabella fori della vista (TAG, X, Y, diametro dall'origine del modello) con etichette A1, A2... accanto ai fori; "
        "collocata in un'area libera.",
        {"view": _VIEW, "x": (N, "Angolo in alto a sinistra della tabella (vuoto = area libera)"), "y": (N, ""),
         "tags": (B, "Etichette sui fori (default true)"), "unit": _UNIT}, []),
    "add_general_roughness": ("add_general_roughness",
        "Indicazione generale della rugosita (ISO 1302): 'Ra 6,3 ( simbolo )' in un'area libera in alto a destra.",
        {"value": (S, "Ra in um, es. 6.3"), "x": (N, ""), "y": (N, ""), "unit": _UNIT}, []),
    "auto_dimension": ("auto_dimension",
        "Quotatura automatica di una vista ortogonale (mai sulle isometriche): rimuove i duplicati e ordina le quote.",
        {"view": _VIEW, "scheme": (S, "baseline | chain | ordinate"),
         "horizontal_placement": (S, "above | below"), "vertical_placement": (S, "right | left"),
         "tidy": (B, "Ordina le quote fuori dal contorno della vista (default true)")}, []),
    "list_drawing_dimensions": ("list_drawing_dimensions",
        "Elenca le quote del foglio attivo (valore, tipo, posizione, callout foro, duplicati, quote su viste isometriche).", {}, []),
    "add_center_marks": ("add_center_marks",
        "Centri e assi sui cerchi di una vista (mode=auto) o asse fra due spigoli (mode=centerline, edge1/edge2 = punti sul foglio).",
        {"view": _VIEW, "mode": (S, "auto | centerline"), "edge1": (A, "[x,y]"), "edge2": (A, "[x,y]"), "unit": _UNIT}, []),
    "add_note": ("add_note",
        "Nota di testo sul foglio.",
        {"text": (S, "Testo"), "x": (N, ""), "y": (N, ""), "height": (N, "Altezza carattere (default 3.5 mm)"),
         "unit": _UNIT}, ["text"]),
    "add_surface_finish": ("add_surface_finish",
        "Simbolo di rugosita (Ra in um), opzionalmente agganciato a uno spigolo.",
        {"x": (N, ""), "y": (N, ""), "symbol": (S, "basic | machining_required | no_machining"),
         "roughness": (S, "Valore Ra, es. 3.2"), "edge_x": (N, "Punto sullo spigolo"), "edge_y": (N, ""),
         "unit": _UNIT}, []),
    "add_datum": ("add_datum",
        "Riferimento (datum) con lettera su uno spigolo (punto in coordinate foglio).",
        {"label": (S, "Lettera"), "edge_x": (N, "Punto sullo spigolo (coordinate foglio)"), "edge_y": (N, ""), "unit": _UNIT,
         "view": _VIEW, "model_point": (A, "In alternativa a edge_x/edge_y: punto [x,y,z] mm del modello su uno spigolo visto nella vista"),
         "on_dimension": (S, "Aggancia il riferimento a una quota (nome, testo o valore)")}, []),
    "add_geometric_tolerance": ("add_geometric_tolerance",
        "Tolleranza geometrica completa: caratteristica (planarita, rettilineita, circolarita, cilindricita, parallelismo, "
        "perpendicolarita, inclinazione, posizione, concentricita, simmetria, oscillazione_circolare, oscillazione_totale, "
        "profilo_linea, profilo_superficie), valore, Ø, modificatore M/L/S/P, fino a 3 riferimenti, riquadri composti. "
        "Agganciata a uno spigolo con linea di richiamo se si indica un punto su di esso.",
        {"characteristic": (S, "Caratteristica (nome inglese o italiano, es. flatness, cilindricita, position)"),
         "tolerance": (S, "Valore, es. 0.1"), "datum_refs": (A, "Fino a 3 lettere di riferimento"),
         "diameter": (B, "Zona di tolleranza diametrale (Ø)"),
         "material_condition": (S, "M (massimo materiale) | L (minimo) | S | P (zona proiettata)"),
         "edge_x": (N, "Punto sullo spigolo a cui agganciare il riquadro"), "edge_y": (N, ""),
         "x": (N, "Posizione del riquadro"), "y": (N, ""),
         "extra_frames": (A, "Altri riquadri sotto il primo: oggetti {characteristic, tolerance, datum_refs, diameter, material_condition}"),
         "view": _VIEW, "model_point": (A, "Aggancio alla feature: punto [x,y,z] mm del modello su uno spigolo visto nella vista (linea di richiamo con freccia, riquadro vicino)"),
         "on_dimension": (S, "Aggancio alla feature: nome/testo/valore di una quota (riquadro legato alla quota, accanto al testo)"),
         "unit": _UNIT}, []),
    "add_hole_callout": ("add_hole_callout",
        "Quota di foro (callout) su un bordo circolare.",
        {"edge_x": (N, "Punto sul bordo"), "edge_y": (N, ""), "x": (N, "Posizione testo"), "y": (N, ""),
         "unit": _UNIT}, ["edge_x", "edge_y"]),
    "set_drawing_properties": ("set_drawing_properties",
        "Proprieta per il cartiglio: title, author, drawing_number, material, revision, date, company, "
        "checked_by, checked_date, finish, weight, approved_by (o nomi personalizzati).",
        {"properties": (O, "Coppie nome-valore"), "target": (S, "drawing | model | both (default)")},
        ["properties"]),
    "list_sheets": ("list_sheets", "Elenca i fogli del disegno attivo.", {}, []),
    "add_sheet": ("add_sheet", "Aggiunge un foglio (e lo attiva).",
        {"name": (S, ""), "paper_size": (S, "A4..A0"), "orientation": (S, ""), "projection": (S, "first | third"),
         "scale": _SCALE, "sheet_format": (S, "iso | din | none")}, []),
    "activate_sheet": ("activate_sheet", "Attiva un foglio per nome.", {"name": (S, "Nome foglio")}, ["name"]),
    "set_sheet_properties": ("set_sheet_properties", "Scala, formato, proiezione, nome di un foglio.",
        {"sheet": (S, "Foglio (default attivo)"), "scale": _SCALE, "paper_size": (S, ""),
         "orientation": (S, ""), "projection": (S, "first | third"), "new_name": (S, "")}, []),
    "list_drawing_views": ("list_drawing_views",
        "Elenca le viste del foglio attivo: nome, tipo, scala, posizione e dimensioni (mm).", {}, []),
    "set_view_properties": ("set_view_properties",
        "Scala, stile di visualizzazione e tangenti di una vista.",
        {"view": _VIEW, "scale": _SCALE,
         "display_style": (S, "wireframe | hidden_visible | hidden_removed | shaded | shaded_edges"),
         "show_tangent_edges": (B, ""),
         "exploded": (B, "Mostra (true) o nasconde (false) l'esploso dell'assieme nella vista")}, []),
    "move_view": ("move_view", "Sposta una vista (centro) in x,y o di x,y se relative.",
        {"view": _VIEW, "x": (N, ""), "y": (N, ""), "relative": (B, ""), "unit": _UNIT}, ["x", "y"]),
    "delete_view": ("delete_view", "Elimina una vista del disegno attivo (con le viste che ne dipendono).",
        {"view": (S, "Nome della vista")}, ["view"]),
    "add_bom": ("add_bom", "Distinta base per una vista di assieme.",
        {"view": _VIEW, "x": (N, ""), "y": (N, ""), "bom_type": (S, "parts_only | top_level | indented"),
         "template": (S, "Path .sldbomtbt"), "unit": _UNIT}, []),
    "list_bom": ("list_bom", "Legge la distinta base del disegno attivo: n. articolo, nome parte, descrizione, quantita.", {}, []),
    "add_balloons": ("add_balloons", "Palloncini automatici per una vista di assieme.",
        {"view": _VIEW, "layout": (S, "square | circular | top | bottom | left | right")}, []),
    "export_drawing": ("export_drawing", "Esporta il disegno: PDF, DWG, DXF, PNG o JPG.",
        {"filepath": (S, "Percorso di destinazione"), "format": (S, "pdf|dwg|dxf|png|jpg (default: dall'estensione)")},
        ["filepath"]),
    "save_drawing": ("save_drawing", "Salva con nome il disegno attivo (.SLDDRW).",
        {"filepath": (S, "Percorso di destinazione")}, ["filepath"]),
}


def _schema(props, required):
    p = {}
    for k, (t, desc) in props.items():
        d = {"type": t}
        if t == A:
            d["items"] = {"type": "string"} if k in ("views", "datum_refs") else (
                {"type": "object"} if k == "extra_frames" else {"type": "number"})
        if desc:
            d["description"] = desc
        p[k] = d
    return {"type": "object", "properties": p, "required": required}


DRAWING_TOOLS = [Tool(name=n, description=d, inputSchema=_schema(p, r))
                 for n, (m, d, p, r) in _TOOLS.items()]
DRAWING_DISPATCH = {n: (m, set(p)) for n, (m, d, p, r) in _TOOLS.items()}
