"""
Dati ed export: definizioni dei tool MCP (blocco 3) + smistamento verso DataExportOperations (automation/data_export.py).
Ogni voce: nome -> (metodo di SolidWorksAutomation, descrizione, {parametro: (tipo json | None, descrizione)}, [obbligatori]).

Convenzioni: misure in mm salvo `unit`; angoli in gradi; massa in kg; inerzie in kg*m2 (e kg*mm2);
entita' per coordinate: {"face":[x,y,z]} | {"edge":[x,y,z]} | {"vertex":[x,y,z]} (punto SULL'entita', coordinate del modello).
"""

from mcp.types import Tool

S, N, B, A, O = "string", "number", "boolean", "array", "object"
_UNIT = (S, "Length unit for inputs and results: mm, cm, m or inch (default mm)")
_CFG = (S, "Configuration name (empty = active configuration / the file)")
_CFGS = (None, "Configuration: name | list of names | 'all' (default the active one)")
_ENT = (O, "Entity by coordinates: {\"face\":[x,y,z]} | {\"edge\":[x,y,z]} | {\"vertex\":[x,y,z]} (a point ON the entity, model coordinates, mm)")

_TOOLS = {
    # ---------------------------------------------------------------- materiali
    "list_materials": ("list_materials",
        "SolidWorks material library (.sldmat files; names follow the SolidWorks UI language: 'Lega 6061' in Italian, '6061 Alloy' in English). No arguments: categories with counts; "
        "with `category` (e.g. 'Steel', 'Plastics') or `query` (e.g. '304', 'ABS'): matching materials with density in kg/m3. Reads every material library configured in SolidWorks (Options > File Locations > "
        "Material Databases), custom ones included; `libraries` lists the folders and files read, `duplicates` the repeated names (the first wins).",
        {"category": (S, "Category name (partial match)"), "query": (S, "Text contained in the material name"),
         "include_properties": (B, "Also return elastic modulus, yield strength, etc."),
         "limit": (N, "Maximum number of materials returned (count, default 400)")}, []),
    "assign_material": ("assign_material",
        "Assign a library material to the part (or to one body with `body`): 'AISI 304', 'Lega 6061' ('6061 Alloy' in English SolidWorks). Also sets the model's "
        "Material property (\"SW-Material@file\") so the drawing title block shows it. Materials of custom libraries configured in SolidWorks are included.",
        {"material": (S, "Material name (partial match accepted if unique)"), "category": (S, "Narrows the search to this category"),
         "body": (S, "Body name (default the whole part)"), "configuration": _CFGS,
         "link_title_block": (B, "Link Material to the title block (default true)")}, ["material"]),
    "get_material": ("get_material", "Current material of the part and of its bodies, the density used and the Material property.",
        {"body": (S, "Body name (default the whole part)"), "configuration": _CFG}, []),
    "link_material_to_title_block": ("link_material_to_title_block",
        "Set Material = \"SW-Material@file\" on the model so the drawing title block shows the assigned material.", {}, []),
    # ---------------------------------------------------------------- massa
    "get_part_mass_properties": ("get_part_mass_properties",
        "Full mass properties of a part or body: mass, volume, surface area, density used, center of mass, principal moments and axes, "
        "inertia tensor at the center of mass and at the origin (kg*m2 and kg*mm2), override status. With `coordinate_system` it also returns the center of mass and the inertia tensors "
        "in the origin and axes of that user coordinate system (in_coordinate_system).",
        {"body": (S, "Body name (default the whole part)"), "configuration": _CFG, "unit": _UNIT,
         "coordinate_system": (S, "Name of a coordinate system feature of the part (see create_coordinate_system): adds "
                               "in_coordinate_system with the center of mass and the inertia tensors expressed in that system's origin and axes")}, []),
    "set_mass_override": ("set_mass_override",
        "Override the mass (kg) with an optional center of mass. Without `mass` the override is removed.",
        {"mass": (N, "Mass in kg"), "center_of_mass": (A, "[x,y,z] in `unit` (default mm; default the computed center of mass)"), "unit": _UNIT,
         "configuration": _CFG}, []),
    # ---------------------------------------------------------------- proprieta' personalizzate
    "list_custom_properties": ("list_custom_properties",
        "List the custom properties of the active document (file level) or of a configuration, with value/expression and resolved value.",
        {"configuration": _CFG}, []),
    "get_custom_property": ("get_custom_property", "Read one custom property (value and resolved value, e.g. SW-Mass).",
        {"name": (S, "Property name"), "configuration": _CFG}, ["name"]),
    "set_custom_property": ("set_custom_property",
        "Write a custom property (file or configuration). The value may be an expression such as 'SW-Mass@part.SLDPRT' or "
        "'SW-Material@part.SLDPRT' (quotes added automatically).",
        {"name": (S, "Property name"), "value": (S, "Value or expression"), "configuration": _CFG,
         "type": (S, "text | number | double | date | yesno")},
        ["name", "value"]),
    "delete_custom_property": ("delete_custom_property", "Delete a custom property.",
        {"name": (S, "Property name"), "configuration": _CFG}, ["name"]),
    # ---------------------------------------------------------------- variabili globali / equazioni
    "list_equations": ("list_equations", "List equations and global variables (values in the document units).", {}, []),
    "set_global_variable": ("set_global_variable",
        "Create or change a global variable (\"name\" = value; a number in mm or an expression). Rebuilds and reports errors and volume.",
        {"name": (S, "Variable name"), "value": (None, "Number (mm) or expression (e.g. 50 or '\"other\"*2')")}, ["name", "value"]),
    "delete_global_variable": ("delete_global_variable", "Delete a global variable.", {"name": (S, "Variable name")}, ["name"]),
    "add_equation": ("add_equation",
        "Add an equation, e.g. '\"D1@Sketch1\" = \"length\" * 2' (dimension driven by a variable). Checked: removed again if it causes errors.",
        {"equation": (S, "Full equation text, e.g. '\"D1@Sketch1\" = \"length\" * 2'")}, ["equation"]),
    "update_equation": ("update_equation", "Replace the equation at the given index (see list_equations).",
        {"index": (N, "0-based equation index from list_equations"), "equation": (S, "New full equation text")}, ["index", "equation"]),
    "delete_equation": ("delete_equation", "Delete the equation at the given index.",
        {"index": (N, "0-based equation index from list_equations")}, ["index"]),
    "evaluate_equations": ("evaluate_equations", "Recalculate the equations, rebuild and check (feature errors, volume, values).", {}, []),
    # ---------------------------------------------------------------- configurazioni del pezzo
    "list_part_configurations": ("list_part_configurations",
        "Configurations of the part/assembly and the active one; with include_volume it activates each and reports its volume.",
        {"include_volume": (B, "Activate each configuration and report its volume (slower)")}, []),
    "add_part_configuration": ("add_part_configuration", "Add a configuration (it becomes active unless activate=false).",
        {"name": (S, "New configuration name"), "comment": (S, "Configuration comment"),
         "activate": (B, "Activate the new configuration (default true)")}, ["name"]),
    "activate_part_configuration": ("activate_part_configuration", "Activate a configuration of a part/assembly and rebuild.",
        {"name": (S, "Configuration name")}, ["name"]),
    "delete_part_configuration": ("delete_part_configuration", "Delete a configuration (not the only one).",
        {"name": (S, "Configuration name")}, ["name"]),
    "set_configuration_dimension": ("set_configuration_dimension",
        "Set a dimension ('D1@Sketch1') in the given configurations only (name | list | 'all'; default the active one). Angles in degrees.",
        {"dimension": (S, "Dimension full name, e.g. 'D1@Sketch1'"), "value": (N, "New value in `unit` (default mm; degrees for angular dimensions)"),
         "configuration": _CFGS, "unit": _UNIT}, ["dimension", "value"]),
    "set_configuration_suppression": ("set_configuration_suppression",
        "Suppress/unsuppress a feature in the given configurations only (name | list | 'all'; default the active one).",
        {"feature": (S, "Feature name"), "suppressed": (B, "True to suppress, false to unsuppress (default true)"), "configuration": _CFGS}, ["feature"]),
    "apply_configuration_table": ("apply_configuration_table",
        "Create or update the configurations of a PART from a table (no Excel needed): a CSV/JSON file path, CSV/JSON text, or inline rows. "
        "First column = configuration name; other columns use the design-table headers: 'D1@Sketch1' (dimension value, mm or degrees), "
        "'$STATE@Cut-Extrude1' (S = suppressed, R = active), '$PRP@PartNumber' (configuration custom property), '$MATERIAL', '$COMMENT'. "
        "Empty cell = leave unchanged. Example rows: [{\"Configuration\":\"Long\",\"D1@Sketch1\":60,\"$STATE@Cut-Extrude1\":\"R\","
        "\"$PRP@PartNumber\":\"A-002\"}]. Missing configurations are created (create_missing); the active configuration is restored at the "
        "end; dry_run=true only returns the plan. A real Excel design table is NOT created (InsertDesignTable is not available): the "
        "result reports whether Excel is installed.",
        {"table": (None, "File path (.csv/.json), CSV/JSON text, or array of row objects / object {configuration: {header: value}}"),
         "create_missing": (B, "Create configurations that do not exist (default true)"),
         "dry_run": (B, "Return the plan without changing the model (default false)"),
         "unit": _UNIT}, ["table"]),
    # ---------------------------------------------------------------- export / import
    "export_model": ("export_model",
        "Export the active part/assembly: stl | 3mf (3D printing) | step | iges | x_t | x_b | sat | pdf (3D PDF) | eprt/easm (eDrawings); format from the file extension. "
        "STL/3MF: quality coarse|fine|custom (+deviation, angle), binary, units. STEP: step_ap 203|214|242. Verifies the file "
        "(STL: triangles and box vs model; STEP: MANIFOLD_SOLID_BREP). Example: {\"filepath\":\"C:\\\\out\\\\part.stl\",\"quality\":\"custom\",\"deviation\":0.05,\"angle\":10}",
        {"filepath": (S, "Output file path; its extension selects the format"), "format": (S, "Format override if different from the extension"), "configuration": _CFG,
         "quality": (S, "coarse | fine | custom (STL/3MF)"), "deviation": (N, "Chord deviation in mm, for custom quality"), "angle": (N, "Angle tolerance in degrees, for custom quality"),
         "binary": (B, "Binary STL (default true)"), "step_ap": (N, "STEP application protocol number: 203, 214 or 242"), "units": (S, "mm | cm | m | inch (STL)"),
         "iges_representation": (S, "surfaces | brep | curves"), "one_file": (B, "Export an assembly as a single STL file"),
         "verify": (B, "Verify the exported file (default true)")}, ["filepath"]),
    "inspect_export_file": ("inspect_export_file",
        "Read and verify an exported file: STL (triangles, bounding box), 3MF, STEP (schema, MANIFOLD_SOLID_BREP), IGES, Parasolid, 3D PDF.",
        {"filepath": (S, "Path of the file to inspect")}, ["filepath"]),
    "import_model": ("import_model",
        "Open STEP/IGES/Parasolid/STL as a part and return the imported bodies (volume, box). STL: import_as solid|surface|graphics, units.",
        {"filepath": (S, "Path of the file to import"), "import_as": (S, "solid | surface | graphics (STL)"), "units": (S, "mm | cm | m | inch (STL)")}, ["filepath"]),
    "export_model_image": ("export_model_image",
        "PNG/JPG/BMP image of the part/assembly. view: isometric|front|back|left|right|top|bottom|trimetric|dimetric; "
        "style: shaded_edges|shaded|hidden_lines|hidden_gray|wireframe; width/height in pixels (PNG/BMP); hide_reference=true (default) "
        "hides planes, axes, origins, points and sketches; white_background for a white backdrop.",
        {"filepath": (S, "Output image path (.png, .jpg or .bmp)"), "view": (S, "Named view (default isometric)"), "style": (S, "Display style (default shaded_edges)"),
         "width": (N, "Image width in pixels"), "height": (N, "Image height in pixels"),
         "hide_reference": (B, "Hide planes, axes, origins, points and sketches, also inside assembly components (default true)"), "white_background": (B, "White backdrop"),
         "zoom_to_fit": (B, "Zoom to fit before capture (default true)")}, ["filepath"]),
    # ---------------------------------------------------------------- misure
    "measure_entities": ("measure_entities",
        "Measure between two entities given by coordinates (or one alone): distance, normal distance, XYZ delta, angle (degrees), parallel/perpendicular; "
        "radius/diameter/area/length where applicable.",
        {"entity1": _ENT, "entity2": _ENT, "unit": _UNIT}, ["entity1"]),
    "measure_face": ("measure_face",
        "Type and measures of the face containing the point: area; cylindrical: radius, diameter, axis; planar: normal; sphere/cone/torus.",
        {"x": (N, "Point X coordinate in `unit` (default mm)"), "y": (N, "Point Y coordinate in `unit` (default mm)"),
         "z": (N, "Point Z coordinate in `unit` (default mm)"), "unit": _UNIT}, ["x", "y", "z"]),
    "get_bounding_box": ("get_bounding_box",
        "Axis-aligned bounding box of a part (exact), body or assembly: min, max, size, center.",
        {"body": (S, "Body name (default the whole part)"), "unit": _UNIT}, []),
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
