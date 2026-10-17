"""
Simulazione (blocco 5): definizioni dei tool MCP + smistamento verso SimulationOperations (automation/simulation.py).
Ogni voce: nome -> (metodo, descrizione, {parametro: (tipo json | None, descrizione)}, [obbligatori]).
Unita': mm, N, MPa, m/s2, N*m. Facce per coordinate: [[x,y,z],..] = punti SULLE facce (coordinate modello, mm).
"""

from mcp.types import Tool

S, N, B, A, O = "string", "number", "boolean", "array", "object"
_ST = (S, "Study name (default: active study)")
_FACES = (A, "Faces by coordinates: [[x,y,z],...] in mm (points ON the faces)")

_TOOLS = {
    "simulation_status": ("simulation_status",
        "Check whether SOLIDWORKS Simulation is available (add-in, version, studies of the active document). "
        "Loads the add-in into the instance if needed without making it permanent (restores the registry startup key).", {}, []),
    "create_static_study": ("create_static_study",
        "Create a linear static study on the active (saved) document and make it active. The material is the part's material.",
        {"name": (S, "Study name")}, []),
    "list_simulation_studies": ("list_simulation_studies", "List the studies of the active document (type, mesh state, number of loads).", {}, []),
    "delete_simulation_study": ("delete_simulation_study", "Delete a study by name.", {"name": (S, "Study name")}, ["name"]),
    "set_study_material": ("set_study_material",
        "Study material: without `material` reports the one taken from the part (E, nu, density, yield strength); with `material` "
        "(SOLIDWORKS library name, e.g. 'AISI 1020') assigns it to the study.",
        {"material": (S, "Material name"), "category": (S, "Library category to narrow the search"), "study": _ST}, []),
    "add_restraint": ("add_restraint",
        "Restraint on faces picked by coordinates: fixed | immovable | symmetry | roller (sliding on a flat face) | "
        "hinge (fixed hinge on a cylindrical face).",
        {"kind": (S, "fixed | immovable | symmetry | roller | hinge (default fixed)"), "faces": _FACES, "study": _ST}, ["faces"]),
    "add_force": ("add_force",
        "Force on faces picked by coordinates. mode 'direction' (default): along `direction` [dx,dy,dz] in model coordinates; "
        "mode 'normal': normal to the face (sign convention to be checked). With several faces the value applies to each face. "
        "Example: {\"faces\":[[0,0,50]],\"value\":1000,\"direction\":[0,0,-1]}",
        {"faces": _FACES, "value": (N, "Force in N"), "mode": (S, "direction | normal (default direction)"),
         "direction": (A, "Direction vector [dx,dy,dz] (unitless)"), "study": _ST},
        ["faces", "value"]),
    "add_torque": ("add_torque",
        "Torque on faces (e.g. shaft end) about the axis of a reference CYLINDRICAL face (a point on it).",
        {"faces": _FACES, "value": (N, "Torque in N*m"), "axis_face": (A, "[x,y,z] in mm: a point on the reference cylindrical face"), "study": _ST},
        ["faces", "value", "axis_face"]),
    "add_pressure": ("add_pressure",
        "Normal pressure on faces picked by coordinates (positive = towards the inside of the face).",
        {"faces": _FACES, "value": (N, "Pressure in MPa (= N/mm2)"), "study": _ST}, ["faces", "value"]),
    "add_gravity": ("add_gravity",
        "Gravity on the study: acceleration (default 9.80665 m/s2) along `direction` (default [0,0,-1], model coordinates).",
        {"direction": (A, "Direction vector [dx,dy,dz] (unitless)"), "acceleration": (N, "Acceleration in m/s2"), "study": _ST}, []),
    "list_simulation_loads": ("list_simulation_loads", "List the restraints and loads of the study.", {"study": _ST}, []),
    "delete_simulation_load": ("delete_simulation_load", "Delete a restraint or load by name.",
        {"name": (S, "Restraint or load name"), "study": _ST}, ["name"]),
    "set_simulation_contact": ("set_simulation_contact",
        "Global contact of an assembly study: bonded (default) | free | no_penetration.",
        {"contact": (S, "bonded | free | no_penetration"), "study": _ST}, []),
    "create_simulation_mesh": ("create_simulation_mesh",
        "Create the solid mesh. mesher 'standard' or 'curvature' (curvature-based; element_size is then the MAXIMUM size); "
        "element_size defaults to the global size proposed by SW; quality high|draft. "
        "Returns nodes, elements and quality check (aspect ratio, jacobian). Example: {\"element_size\":5,\"quality\":\"high\"}",
        {"element_size": (N, "Element size in mm"), "tolerance": (N, "Tolerance in mm (default 5% of element size)"),
         "mesher": (S, "standard | curvature (default standard)"), "quality": (S, "high | draft (default high)"),
         "min_element_size": (N, "Min element size in mm (curvature only; default size/3)"),
         "growth_ratio": (N, "Growth ratio (ratio, curvature only)"),
         "min_elements_in_circle": (N, "Min elements in a circle (count, curvature only)"), "study": _ST}, []),
    "run_simulation": ("run_simulation",
        "Run the study (mesh must exist). Default timeout 300 s: on a dedicated instance, the SW process is terminated when it expires.",
        {"timeout": (N, "Timeout in seconds (default 300)"), "study": _ST}, []),
    "get_simulation_results": ("get_simulation_results",
        "Results: max/min von Mises (MPa) with location, max resultant displacement (mm), min factor of safety, reaction forces, mesh.",
        {"study": _ST, "step": (N, "Solution step number, 1-based (default 1)")}, []),
    "get_simulation_stress_on_faces": ("get_simulation_stress_on_faces",
        "Nodal stress (MPa) on the nodes of faces picked by coordinates, optionally only inside a box [xmin,ymin,zmin,xmax,ymax,zmax] in mm: "
        "min/max/mean. Use it to measure away from singularities (restraints, sharp edges).",
        {"faces": _FACES, "box": (A, "Optional box [xmin,ymin,zmin,xmax,ymax,zmax], 6 numbers in mm"),
         "component": (S, "vonmises | sx | sy | sz | txy | txz | tyz | p1 | p2 | p3 (default vonmises)"), "study": _ST,
         "step": (N, "Solution step number, 1-based (default 1)")},
        ["faces"]),
    "export_simulation_plot": ("export_simulation_plot",
        "Export the results plot (color map) as PNG: von_mises | displacement | strain.",
        {"filepath": (S, "Output PNG file path"), "result": (S, "von_mises | displacement | strain, or a plot name (default von_mises)"),
         "view": (S, "isometric | front | back | left | right | top | bottom (default isometric)"), "study": _ST}, ["filepath"]),
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
