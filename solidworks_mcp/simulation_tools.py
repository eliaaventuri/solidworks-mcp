"""
Simulazione (blocco 5): definizioni dei tool MCP + smistamento verso SimulationOperations (automation/simulation.py).
Ogni voce: nome -> (metodo, descrizione, {parametro: (tipo json | None, descrizione)}, [obbligatori]).
Unita': mm, N, MPa, m/s2, N*m. Facce per coordinate: [[x,y,z],..] = punti SULLE facce (coordinate modello, mm).
"""

from mcp.types import Tool

S, N, B, A, O = "string", "number", "boolean", "array", "object"
_ST = (S, "Nome dello studio (default quello attivo)")
_FACES = (A, "Facce per coordinate: [[x,y,z],...] in mm (punto SULLA faccia)")

_TOOLS = {
    "simulation_status": ("simulation_status",
        "Verifica se SOLIDWORKS Simulation e' disponibile (add-in caricabile, versione, studi del documento attivo). "
        "Carica l'add-in nell'istanza se serve, senza renderlo permanente (ripristina la chiave di avvio nel registro).", {}, []),
    "create_static_study": ("create_static_study",
        "Crea uno studio statico lineare sul documento attivo (salvato) e lo rende attivo. Il materiale e' quello del pezzo.",
        {"name": (S, "Nome studio")}, []),
    "list_simulation_studies": ("list_simulation_studies", "Elenca gli studi del documento attivo (tipo, stato mesh, n. carichi).", {}, []),
    "delete_simulation_study": ("delete_simulation_study", "Elimina uno studio per nome.", {"name": (S, "")}, ["name"]),
    "set_study_material": ("set_study_material",
        "Materiale dello studio: senza `material` riporta quello preso dal pezzo (E, nu, densita', snervamento); con `material` "
        "(libreria SOLIDWORKS, es. 'AISI 1020') lo assegna allo studio.",
        {"material": (S, "Nome materiale"), "category": (S, "Restringe la ricerca"), "study": _ST}, []),
    "add_restraint": ("add_restraint",
        "Vincolo su facce per coordinate: fixed (fisso) | immovable | symmetry | roller (rullo/scorrevole su faccia piana) | "
        "hinge (cerniera fissa su faccia cilindrica).",
        {"kind": (S, "fixed | immovable | symmetry | roller | hinge"), "faces": _FACES, "study": _ST}, ["faces"]),
    "add_force": ("add_force",
        "Forza (N) su facce per coordinate. mode 'direction' (default): lungo `direction` [dx,dy,dz] in coordinate modello; "
        "mode 'normal': normale alla faccia (verso l'interno con valore positivo da verificare). Con piu' facce il valore vale per ogni faccia.",
        {"faces": _FACES, "value": (N, "Newton"), "mode": (S, "direction | normal"), "direction": (A, "[dx,dy,dz]"), "study": _ST},
        ["faces", "value"]),
    "add_torque": ("add_torque",
        "Coppia (N*m) su facce (es. estremita' di un albero) attorno all'asse di una faccia CILINDRICA di riferimento (punto su di essa).",
        {"faces": _FACES, "value": (N, "N*m"), "axis_face": (A, "[x,y,z] mm di un punto sulla faccia cilindrica"), "study": _ST},
        ["faces", "value", "axis_face"]),
    "add_pressure": ("add_pressure",
        "Pressione normale (MPa) su facce per coordinate (positiva = verso l'interno della faccia).",
        {"faces": _FACES, "value": (N, "MPa = N/mm2"), "study": _ST}, ["faces", "value"]),
    "add_gravity": ("add_gravity",
        "Gravita' sullo studio: accelerazione (m/s2, default 9.80665) lungo `direction` (default [0,0,-1], coordinate modello).",
        {"direction": (A, "[dx,dy,dz]"), "acceleration": (N, "m/s2"), "study": _ST}, []),
    "list_simulation_loads": ("list_simulation_loads", "Vincoli e carichi dello studio.", {"study": _ST}, []),
    "delete_simulation_load": ("delete_simulation_load", "Elimina un vincolo/carico per nome.", {"name": (S, ""), "study": _ST}, ["name"]),
    "set_simulation_contact": ("set_simulation_contact",
        "Contatto globale dello studio d'assieme: bonded (incollato, default) | free | no_penetration.",
        {"contact": (S, "bonded | free | no_penetration"), "study": _ST}, []),
    "create_simulation_mesh": ("create_simulation_mesh",
        "Crea la mesh solida. mesher 'standard' o 'curvature' (basata sulla curvatura); element_size mm (default il globale proposto da SW), "
        "tolerance mm; quality high|draft. Restituisce nodi, elementi e controllo qualita' (rapporto d'aspetto, jacobiano).",
        {"element_size": (N, "mm"), "tolerance": (N, "mm"), "mesher": (S, "standard | curvature"), "quality": (S, "high | draft"),
         "min_element_size": (N, "mm (curvature)"), "growth_ratio": (N, ""), "min_elements_in_circle": (N, ""), "study": _ST}, []),
    "run_simulation": ("run_simulation",
        "Esegue lo studio (mesh gia' creata). timeout in secondi (default 300): in istanza dedicata, allo scadere il processo SW viene terminato.",
        {"timeout": (N, "secondi"), "study": _ST}, []),
    "get_simulation_results": ("get_simulation_results",
        "Risultati: von Mises max/min (MPa) con posizione, spostamento risultante max (mm), fattore di sicurezza min, forze di reazione, mesh.",
        {"study": _ST, "step": (N, "Default 1")}, []),
    "get_simulation_stress_on_faces": ("get_simulation_stress_on_faces",
        "Tensione nodale (MPa) sui nodi di facce per coordinate, opzionalmente solo dentro un box [xmin,ymin,zmin,xmax,ymax,zmax] mm: "
        "min/max/media. Per misurare lontano dalle singolarita' (vincoli, spigoli vivi).",
        {"faces": _FACES, "box": (A, "6 numeri in mm (facoltativo)"),
         "component": (S, "vonmises | sx | sy | sz | txy | txz | tyz | p1 | p2 | p3"), "study": _ST, "step": (N, "")},
        ["faces"]),
    "export_simulation_plot": ("export_simulation_plot",
        "Esporta in PNG il grafico dei risultati (mappa a colori): von_mises | displacement | strain; vista isometric|front|top|...",
        {"filepath": (S, ""), "result": (S, "von_mises | displacement | strain"), "view": (S, ""), "study": _ST}, ["filepath"]),
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


SIMULATION_TOOLS = [Tool(name=n, description=d, inputSchema=_schema(p, r)) for n, (m, d, p, r) in _TOOLS.items()]
SIMULATION_DISPATCH = {n: (m, set(p)) for n, (m, d, p, r) in _TOOLS.items()}
