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
_UNIT = (S, "Length unit (default 'mm')")
_COMP = (S, "Component instance name (e.g. 'perno-1', as in list_components)")
_COMPS = (A, "Component instance names (e.g. ['vite-1'])")
_ENT = (None, "Entity: 'Piano frontale@perno-1' | 'Assi1@staffa-1' | {\"face\":[x,y,z]} | {\"edge\":[x,y,z]} | "
              "{\"component\":\"perno-1\",\"plane\":\"Piano destro\"}; points in assembly coordinates (mm). Standard plane/origin "
              "names work in any language ('Front Plane', 'front', 'top', 'right', 'origin')")
_POS = (A, "[x,y,z] position of the component ORIGIN, in mm")
_ROT = (A, "[rx,ry,rz] rotation in degrees (X then Y then Z, assembly axes)")

_TOOLS = {
    # ---------------------------------------------------------------- componenti
    "insert_component": ("insert_component",
        "Insert a part or sub-assembly from file with its origin at (x,y,z) and optional rotation. The active document must be an "
        "assembly. fixed=true fixes it. Example: {\"file_path\":\"perno.SLDPRT\",\"x\":0,\"y\":0,\"z\":50,\"rotation\":[0,90,0]}",
        {"file_path": (S, "Path of the .SLDPRT/.SLDASM file"), "x": (N, "Origin X in mm"),
         "y": (N, "Origin Y in mm"), "z": (N, "Origin Z in mm"), "rotation": _ROT,
         "configuration": (S, "Component configuration name"), "fixed": (B, "true = insert as fixed component"), "unit": _UNIT},
        ["file_path"]),
    "insert_components": ("insert_components",
        "Insert several instances of one file: `positions` [[x,y,z],..], or `start` + `step` with `count` instances.",
        {"file_path": (S, "Path of the .SLDPRT/.SLDASM file"), "count": (N, "Number of instances (count, with start+step; default 2)"),
         "positions": (A, "[[x,y,z],...] origin of each instance, in mm"), "start": _POS,
         "step": (A, "[dx,dy,dz] offset between consecutive instances, in mm"), "rotation": _ROT,
         "fixed": (B, "true = insert as fixed components"), "unit": _UNIT},
        ["file_path"]),
    "set_component_fixed": ("set_component_fixed", "Fix (fixed=true) or free (fixed=false) a component.",
        {"component": _COMP, "fixed": (B, "true = fixed, false = movable")}, ["component"]),
    "list_components": ("list_components",
        "List components: instance name, file, configuration, position (mm) and transform (rotation, matrix), fixed/movable, "
        "suppressed, hidden, mate status.",
        {"top_level_only": (B, "true = first level only (default true)"),
         "include_details": (B, "true = include transform and mates (default true)")}, []),
    "replace_component": ("replace_component", "Replace a component with another file (replace_all = all instances).",
        {"component": _COMP, "new_file": (S, "Path of the replacement file"), "configuration": (S, "Configuration of the new file"),
         "replace_all": (B, "true = replace all instances of the file"),
         "reattach_mates": (B, "true = re-attach mates (default true)")}, ["component", "new_file"]),
    "suppress_component": ("suppress_component", "Suppress (suppressed=true) or restore a component.",
        {"component": _COMP, "suppressed": (B, "true = suppress, false = restore")}, ["component"]),
    "delete_component": ("delete_component", "Delete a component from the assembly (with its mates).",
        {"component": _COMP}, ["component"]),
    "set_component_visibility": ("set_component_visibility", "Hide (visible=false) or show a component.",
        {"component": _COMP, "visible": (B, "true = show, false = hide")}, ["component"]),
    "open_component": ("open_component",
        "Open a component's document and make it active (activate_document returns to the assembly).",
        {"component": _COMP}, ["component"]),
    "activate_document": ("activate_document", "Make an open document active (by title, e.g. 'Assieme1').",
        {"name": (S, "Document title")}, ["name"]),
    "component_circular_pattern": ("component_circular_pattern",
        "Circular pattern of components around an axis ('Assi1@staffa-1' or a cylindrical face {\"face\":[x,y,z]}).",
        {"components": _COMPS, "axis": _ENT, "count": (N, "Total instances (count, seed included)"),
         "angle": (N, "Total angle in degrees (default 360)"),
         "equal_spacing": (B, "true = spread instances evenly over `angle` (default true)"),
         "reverse": (B, "true = reverse direction"), "unit": _UNIT},
        ["components", "axis"]),
    "component_linear_pattern": ("component_linear_pattern",
        "Linear pattern of components in 1 or 2 directions (edge {\"edge\":[x,y,z]}, axis or planar face). "
        "Example: {\"components\":[\"vite-1\"],\"direction1\":{\"edge\":[0,0,0]},\"count1\":3,\"spacing1\":25}",
        {"components": _COMPS, "direction1": _ENT, "count1": (N, "Instances in direction 1 (count)"),
         "spacing1": (N, "Spacing in direction 1, in mm"), "direction2": _ENT,
         "count2": (N, "Instances in direction 2 (count)"),
         "spacing2": (N, "Spacing in direction 2, in mm"), "reverse1": (B, "true = reverse direction 1"),
         "reverse2": (B, "true = reverse direction 2"), "unit": _UNIT},
        ["components", "direction1"]),
    "component_derived_pattern": ("component_derived_pattern",
        "Pattern driven by a feature pattern of a part in the assembly (e.g. screws on the flange hole pattern).",
        {"components": _COMPS, "pattern_feature": (S, "Pattern feature name in the part, e.g. 'RipetizioneCircolare1'"),
         "pattern_component": _COMP}, ["components", "pattern_feature", "pattern_component"]),
    "mirror_components": ("mirror_components",
        "Mirror components about a plane. Default: mirrored INSTANCES of the same file; orientation (0..3, measured: 0 = 180 deg about "
        "X, 1 = 180 deg about Z, 2 = no rotation, 3 = 180 deg about Y) sets how the instance is rotated. opposite_hand=true instead "
        "creates a NEW mirrored PART per component (reflected geometry, 'opposite version') saved as <name><name_suffix>.SLDPRT in "
        "`folder` (default: folder of the source part); returns volume and centroid. Existing files are kept unless overwrite=true. Example: {\"components\":[\"staffa-1\"],\"plane\":\"Piano destro\",\"opposite_hand\":true}",
        {"components": _COMPS,
         "plane": (None, "Mirror plane: 'Piano destro' | 'Piano frontale@staffa-1' | {\"face\":[x,y,z]}"),
         "orientation": (N, "Instance orientation index 0-3 (ignored with opposite_hand)"),
         "opposite_hand": (B, "true = create new mirrored parts instead of instances"),
         "name_suffix": (S, "Suffix of the new file name (default '_mirror')"),
         "folder": (S, "Folder of the new files (default: folder of the source part)"),
         "overwrite": (B, "true = allow overwriting an existing file"),
         "align_exact": (B, "opposite_hand: place the new part exactly at the mirror image of the original (default true)"), "unit": _UNIT},
        ["components", "plane"]),
    "move_component": ("move_component",
        "Move/rotate a MOVABLE component honoring mates: relative (dx,dy,dz, rotate_by) or absolute (position, rotation). Motion is "
        "reduced to the ONLY degrees of freedom left by the mates (measured): e.g. a pin with only a concentric mate "
        "slides and spins about its own axis; the rest is discarded (see `ignored`/`applied`). For limit mates use "
        "edit_mate(value).",
        {"component": _COMP, "dx": (N, "Relative X shift in mm"), "dy": (N, "Relative Y shift in mm"),
         "dz": (N, "Relative Z shift in mm"), "position": _POS, "rotation": _ROT,
         "rotate_by": (A, "[rx,ry,rz] relative rotation in degrees"),
         "respect_mates": (B, "true = honor mates (default true)"), "unit": _UNIT}, ["component"]),
    # ---------------------------------------------------------------- accoppiamenti
    "add_mate": ("add_mate",
        "Mate between two component entities: coincident | parallel | perpendicular | tangent | concentric | distance | angle | lock | "
        "symmetric (entity3 = symmetry plane) | width (entity1+entity2 width faces, tab_entities = tab) | gear (gear_ratio=[a,b]) | "
        "screw (pitch). Distance in mm (distance), angle in degrees (angle); limit with min_value/max_value; align: closest | aligned | "
        "anti_aligned; flip reverses. Between two reference axes concentric becomes coincident. Entities may also be assembly planes "
        "such as 'Piano destro'. Width and screw mates are created from mate data (AddMate5 rejects them). Move limits with edit_mate(value). WARNING: lock, gear and screw are created and read back correctly, but the "
        "SolidWorks solver does not enforce them via API (SetTransformAndSolve2/DragOperator): see LIMITI.md C5. "
        "Example: {\"mate_type\":\"concentric\",\"entity1\":\"Assi1@perno-1\",\"entity2\":\"Assi1@staffa-1\"}",
        {"mate_type": (S, "coincident|parallel|perpendicular|tangent|concentric|distance|angle|lock|symmetric|width|gear|screw"),
         "entity1": _ENT, "entity2": _ENT, "entity3": _ENT, "align": (S, "closest | aligned | anti_aligned"),
         "flip": (B, "true = flip mate alignment"), "distance": (N, "Distance in mm"),
         "angle": (N, "Angle in degrees"),
         "min_value": (N, "Minimum limit (distance in mm / angle in degrees)"),
         "max_value": (N, "Maximum limit (distance in mm / angle in degrees)"),
         "gear_ratio": (A, "[numerator, denominator] gear ratio (ratio)"), "pitch": (N, "Screw pitch in mm per revolution"),
         "width_mode": (S, "centered | free | dimension | percent"), "tab_entities": (A, "Tab entities (width mate)"),
         "lock_rotation": (B, "true = lock rotation (concentric mate)"), "unit": _UNIT}, ["mate_type", "entity1", "entity2"]),
    "list_mates": ("list_mates", "List mates: name, type, alignment, components, value, suppressed, error.", {}, []),
    "delete_mate": ("delete_mate",
        "Delete a mate by name. Measures degrees of freedom of all movable components before and after (including chains) and reports those left under-defined (`freed_components`, `freed_not_in_mate`); "
        "positions do not change.",
        {"name": (S, "Mate name (as in list_mates)"),
         "check_dof": (B, "true = compare degrees of freedom before/after (default true)")}, ["name"]),
    "edit_mate": ("edit_mate",
        "Edit a mate: value (mm / degrees), min/max limits (limit mates), flip, suppression. For limit distance/angle mates the value "
        "is the current position: out of range it is rejected and the limits are reported.",
        {"name": (S, "Mate name (as in list_mates)"), "value": (N, "New mate value in mm / degrees"),
         "flip": (B, "true = flip alignment"), "suppress": (B, "true = suppress, false = restore"),
         "max_value": (N, "Maximum limit in mm / degrees"),
         "min_value": (N, "Minimum limit in mm / degrees"), "unit": _UNIT}, ["name"]),
    "get_assembly_status": ("get_assembly_status",
        "Constraint status: fully defined or not, under/over-defined components, degrees of freedom, mates in error.",
        {"probe_dof": (B, "true = measure free motion of under-defined components (default true; nudges and restores them)")},
        []),
    # ---------------------------------------------------------------- vista esplosa
    "create_exploded_view": ("create_exploded_view",
        "Create an exploded view from steps [{components:['perno-1'], direction:'x'|'-y'|[1,1,0]|entity, distance:40, reverse}] (free "
        "direction = any vector, split into X/Y/Z steps; entity direction = edge/axis/cylindrical face, e.g. {\"edge\":[x,y,z]}) or "
        "RADIAL steps [{components:[..], radial_axis:{\"face\":[x,y,z],\"component\":\"staffa-1\"}, distance:30, angle:30, "
        "diverge:false}] (move away from the axis, rotate by `angle` degrees). Rotation in translation steps (rotate_angle) is not "
        "stored by SolidWorks (rotation_applied=false). Returns the exploded poses; keep_exploded=false collapses afterwards. "
        "Example: {\"steps\":[{\"components\":[\"perno-1\"],\"direction\":\"z\",\"distance\":40}]}",
        {"steps": (A, "List of explode step objects (see tool description)"), "unit": _UNIT,
         "keep_exploded": (B, "true = keep exploded (default true)")}, ["steps"]),
    "add_explode_step": ("add_explode_step",
        "Add a step to the exploded view: translation (direction x|y|z|-x.. | free vector [vx,vy,vz] | entity) or radial "
        "(radial_axis + distance + angle). Returns the exploded poses. ",
        {"components": _COMPS,
         "direction": (None, "x|y|z|-x|-y|-z, free vector [vx,vy,vz] or entity (edge/axis/cylindrical face)"),
         "distance": (N, "Explode distance in mm (default 30)"), "reverse": (B, "true = reverse direction"),
         "rotate_angle": (N, "Rotation in degrees (not stored by SolidWorks in translation steps)"),
         "rotate_axis": (S, "Rotation axis (x|y|z) for rotate_angle"),
         "radial_axis": (None, "Cylindrical face/axis of the RADIAL step"),
         "angle": (N, "Rotation of the radial step, in degrees"),
         "diverge": (B, "true = radial step moves away from the axis"), "unit": _UNIT},
        ["components"]),
    "auto_explode": ("auto_explode",
        "Automatic explode. mode='native' = SolidWorks AutoExplode (one 'Chain' step; may produce no steps); mode='mates' = heuristic from mates (disassembly order from mate depth from the base component, direction along the "
        "concentric axis, distances from bounding boxes with minimum `gap`; reports `bbox_overlaps` of the exploded state); 'auto' = native, then 'mates'; 'axis' (default) = one step per component along "
        "`axis`, spaced by `gap`.",
        {"axis": (S, "x|y|z (mode=axis only)"),
         "gap": (N, "mode=axis: spacing between consecutive components; mode=mates: minimum box distance (mm)"),
         "base_component": _COMP, "mode": (S, "axis | native | mates | auto"), "unit": _UNIT}, []),
    "show_exploded": ("show_exploded", "Explode (true) or collapse (false) the assembly.",
        {"exploded": (B, "true = explode, false = collapse (default true)"),
         "view_name": (S, "Exploded view name (default: the first one)")}, []),
    "list_exploded_views": ("list_exploded_views",
        "Exploded views and steps of the active configuration (type, distance, components) and, if exploded, the poses.", {}, []),
    "add_explode_lines": ("add_explode_lines",
        "Explode (route) lines: connects coaxial cylindrical faces of different components (pin-bushing-hole, screw-hole) with a "
        "straight line. groups = lists of components to connect, or empty = automatic (every axis shared by 2+ components). "
        "Save the assembly afterwards so exploded drawing views show the lines.",
        {"groups": ("array", "E.g. [[\"perno-1\",\"boccola-1\",\"staffa-1\"],[\"vite-1\",\"staffa-1\"]]; empty = automatic"),
         "direction": ("string", "x | y | z | auto (default: the direction with the most lines)"),
         "view_name": ("string", "Exploded view name (default: the first one)"),
         "tolerance": ("number", "Max lateral axis offset, in mm (default 0.5)")}, []),
    "delete_explode_step": ("delete_explode_step", "Delete an explode step by name.",
        {"step": (S, "Step name (as in list_exploded_views)")}, ["step"]),
    # ---------------------------------------------------------------- analisi
    "check_interference": ("check_interference",
        "Detect interferences between components (real, non-exploded position): pairs and volume (mm3). `components` restricts the "
        "result to pairs involving them.",
        {"components": _COMPS, "include_coincident": (B, "true = count coincident faces too"),
         "treat_subassemblies_as_components": (B, "true = treat sub-assemblies as components")}, []),
    "detect_collisions": ("detect_collisions",
        "Detect collisions and interferences in the assembly, statically or dynamically along a linear motion trajectory. "
        "If `moving_component` is provided, sweeps the component along (dx, dy, dz) across `steps` intervals, detects any collision, "
        "and safely restores the initial pose.",
        {"moving_component": (S, "Optional component name to move dynamically along trajectory"),
         "dx": (N, "X displacement along trajectory, in mm (or document length unit; default 0.0)"),
         "dy": (N, "Y displacement along trajectory, in mm (or document length unit; default 0.0)"),
         "dz": (N, "Z displacement along trajectory, in mm (or document length unit; default 0.0)"),
         "unit": _UNIT,
         "steps": (N, "Number of intermediate trajectory check steps (count, default 10)"),
         "stop_on_collision": (B, "true = stop trajectory sweep upon first detected collision (default true)"),
         "components": _COMPS,
         "include_coincident": (B, "true = count coincident faces as collisions"),
         "treat_subassemblies_as_components": (B, "true = treat sub-assemblies as components")}, []),
    "check_clearance": ("check_clearance", "Clearance (minimum distance) between two components or two entities.",
        {"entity1": _ENT, "entity2": _ENT, "unit": _UNIT}, ["entity1", "entity2"]),
    "get_assembly_mass_properties": ("get_assembly_mass_properties",
        "Mass, volume, area, centroid of the assembly, mass per file, and a check that mass = sum of components.",
        {"unit": _UNIT}, []),
    "count_components": ("count_components", "Count components per file (instances, suppressed).",
        {"top_level_only": (B, "true = first level only")}, []),
    # ---------------------------------------------------------------- configurazioni
    "list_assembly_configurations": ("list_assembly_configurations", "Assembly configurations and the active one.", {}, []),
    "add_assembly_configuration": ("add_assembly_configuration", "Add a configuration to the assembly.",
        {"name": (S, "New configuration name"), "comment": (S, "Configuration comment"),
         "activate": (B, "true = activate it after creation")}, ["name"]),
    "activate_assembly_configuration": ("activate_assembly_configuration", "Activate an assembly configuration.",
        {"name": (S, "Configuration name")}, ["name"]),
    "set_component_configuration": ("set_component_configuration", "Change the configuration used by a component.",
        {"component": _COMP, "configuration": (S, "Configuration name to use")}, ["component", "configuration"]),
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
