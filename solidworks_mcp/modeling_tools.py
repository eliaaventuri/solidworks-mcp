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

from .tools_ext import EXT_TOOLS

S, N, B, A, O = "string", "number", "boolean", "array", "object"
_UNIT = (S, "Length unit (default mm)")
_SK = (S, "Sketch name (default: active/last)")
_ENT = (None, "Sketch entity: draw_* id, '@x,y' (segment), 'pt@x,y' (point), 'origin'; add_sketch_dimension also accepts a MODEL "
              "edge/vertex/face as {\"edge\": [x,y,z]} (`unit`, a point on it)")
_ENT2 = (None, "Sketch entity (as entity1), or an external one for add_sketch_relation: {\"edge\"|\"vertex\":[x,y,z]} | "
              "{\"axis\":name} | {\"sketch\":name,\"entity\":id}")
_PT3 = (A, "Point [x,y,z] (`unit`) ON the entity")
_PTS3 = (A, "Points [[x,y,z],...] (`unit`), one ON each entity")
_DIR = (None, "{\"edge\":[x,y,z]} | {\"face\":[x,y,z]} | {\"plane\":name} | {\"axis\":name} | name")
_AXIS = (None, "Revolve axis: sketch segment id | reference axis name or {\"axis\":name} | {\"edge\":[x,y,z]} | "
               "{\"sketch\":name,\"entity\":id}")
_EC = "blind | through_all | through_all_both | mid_plane | up_to_next | up_to_surface | offset_from_surface"

_TOOLS = {
    # ---------------------------------------------------------------- sketches: dimensions, relations, status
    "add_sketch_dimension": ("add_sketch_dimension",
        "Add a driving dimension to the active sketch (usable in drawings via insert_model_dimensions). 1 entity "
        "(line/circle/arc) or 2 (distance/angle).",
        {"kind": (S, "auto | length | horizontal | vertical | distance | radius | diameter | angle"),
         "entity1": _ENT, "entity2": _ENT2, "entity3": _ENT2,
         "value": (N, "Dimension value (`unit`); degrees for kind=angle. Angle quadrant: SolidWorks picks the side, a negative value does not flip it; check the endpoints with list_sketch_entities"), "unit": _UNIT,
         "orientation": (S, "horizontal | vertical, for kind=distance or length"),
         "name": (S, "Dimension name, e.g. 'width' -> 'width@Sketch1'"),
         "position": (A, "[x,y] position of the dimension text (`unit`)"), "sketch": _SK}, []),
    "add_sketch_relation": ("add_sketch_relation",
        "Add a sketch relation. Entities may also be OUTSIDE the active sketch: a model edge/vertex {\"edge\":[x,y,z]} / "
        "{\"vertex\":[x,y,z]} (`unit`, point ON it), a reference axis {\"axis\":\"Axis1\"}, or an entity of ANOTHER sketch "
        "{\"sketch\":\"Sketch1\",\"entity\":\"S0-1-2\"} (point \"P0-1\", \"pt@x,y\" or \"@x,y\" in that sketch's coordinates). "
        "pierce: a point of the active sketch pierces a curve (model edge, axis, line/arc/circle of another sketch); "
        "with another sketch's curve SolidWorks refuses the native relation, so the point is moved to the computed "
        "piercing position and made coincident with the projected curve (result key pierce_method). The result lists "
        "relations_added and the final coordinates of the sketch points. "
        "Example: {\"relation\":\"pierce\",\"entity1\":\"pt@5,5\",\"entity2\":{\"sketch\":\"Sketch1\",\"entity\":\"S0-0-1\"}}.",
        {"relation": (S, "horizontal | vertical | coincident | tangent | concentric | equal | parallel | perpendicular | "
                         "symmetric (two entities + axis) | fixed | collinear | on_line | midpoint | pierce"),
         "entity1": _ENT, "entity2": _ENT2, "entity3": _ENT2,
         "unit": _UNIT, "sketch": _SK}, ["relation"]),
    "list_sketch_relations": ("list_sketch_relations",
        "List the geometric relations of a sketch: type, entities (ids such as 'S0-1-2' or 'P0-1') and index, "
        "to find a wrong relation (e.g. a 'fixed' added by mistake) and delete it with delete_sketch_entities.",
        {"sketch": _SK}, []),
    "delete_sketch_entities": ("delete_sketch_entities",
        "Delete from a sketch what you pick: entities (ids such as 'S0-1-2', '@x,y' or 'pt@x,y'), dimensions by name "
        "('D2@Sketch34') and relations by index (indices from list_sketch_relations). Reports what was deleted and the "
        "sketch status. Destructive: no undo.",
        {"entities": (A, "Entities to delete: ids, '@x,y' or 'pt@x,y'"),
         "dimensions": (A, "Dimension names, e.g. 'D2@Sketch34'"),
         "relations": (A, "Relation indices from list_sketch_relations (integers)"), "sketch": _SK}, []),
    "delete_dimension": ("delete_dimension",
        "Delete one sketch dimension by name (e.g. 'D2@Sketch34'). Destructive: no undo.",
        {"name": (S, "Dimension name, e.g. 'D2@Sketch34'"), "sketch": _SK}, ["name"]),
    "set_dimension_driven": ("set_dimension_driven",
        "Make a sketch dimension a reference (driven=true: it measures and does not constrain the geometry) or put it back "
        "to driving (driven=false). Reports the sketch status.",
        {"name": (S, "Dimension name, e.g. 'D1@Sketch1'"),
         "driven": (B, "true = reference (driven), false = driving again; default true"), "sketch": _SK}, ["name"]),
    "split_sketch_entity": ("split_sketch_entity",
        "Split a LINE of a sketch at a point lying on it: the line is rebuilt as two lines meeting at that point. "
        "Dimensions and relations of the original line are lost. Lines only (arcs are refused). Destructive.",
        {"entity": (S, "Line id, e.g. 'S0-1-2' (from list_sketch_entities)"),
         "x": (N, "X of the split point (`unit`)"), "y": (N, "Y of the split point (`unit`)"),
         "unit": _UNIT, "sketch": _SK}, ["entity", "x", "y"]),
    "move_sketch_point": ("move_sketch_point",
        "Move a sketch point to new coordinates, like dragging it: point id 'P0-1' or 'pt@x,y' (the point at those "
        "coordinates). Reads the position back: if the constraints block it, it is reported as a failure.",
        {"point": (S, "Point id 'P0-1' or 'pt@x,y' (current coordinates, `unit`)"),
         "x": (N, "New X (`unit`)"), "y": (N, "New Y (`unit`)"), "unit": _UNIT, "sketch": _SK}, ["point", "x", "y"]),
    "toggle_construction": ("toggle_construction",
        "Set entities to construction geometry (reference only) or back to normal. Entities: ids such as 'S0-1-2'. "
        "Without `construction` the state is inverted.",
        {"entities": (A, "Entity ids, e.g. ['S0-1-2']"),
         "construction": (B, "true = construction, false = normal; omit to invert"), "sketch": _SK}, ["entities"]),
    "get_sketch_definition_status": ("get_sketch_definition_status",
        "Sketch status (fully/under/over-defined) with dimensions and entities.",
        {"sketch": _SK}, []),
    "get_sketch_plane_info": ("get_sketch_plane_info",
        "Sketch plane and axes: mapping of sketch (x,y) to model coordinates.",
        {"sketch": _SK}, []),
    "list_sketch_entities": ("list_sketch_entities", "List sketch entities with id, type and geometry.",
        {"sketch": _SK}, []),
    # ---------------------------------------------------------------- sketches: new entities
    "draw_construction_line": ("draw_construction_line", "Draw a construction line.",
        {"x1": (N, "Start X (`unit`)"), "y1": (N, "Start Y (`unit`)"),
         "x2": (N, "End X (`unit`)"), "y2": (N, "End Y (`unit`)"), "unit": _UNIT},
        ["x1", "y1", "x2", "y2"]),
    "draw_centerline_axis": ("draw_centerline_axis",
        "Draw a centerline (revolve axis, symmetry).",
        {"x1": (N, "Start X (`unit`)"), "y1": (N, "Start Y (`unit`)"),
         "x2": (N, "End X (`unit`)"), "y2": (N, "End Y (`unit`)"), "unit": _UNIT},
        ["x1", "y1", "x2", "y2"]),
    "draw_point": ("draw_point", "Draw a sketch point.",
        {"x": (N, "X (`unit`)"), "y": (N, "Y (`unit`)"), "unit": _UNIT}, ["x", "y"]),
    "draw_spline": ("draw_spline", "Draw a spline through points (at least 2).",
        {"points": (A, "Points [[x,y],...] (`unit`)"), "unit": _UNIT, "closed": (B, "Close the spline")},
        ["points"]),
    "draw_slot": ("draw_slot", "Draw a straight slot.",
        {"x1": (N, "X of end 1 (`unit`): arc center, or outer end if overall"),
         "y1": (N, "Y of end 1 (`unit`)"),
         "x2": (N, "X of end 2 (`unit`)"), "y2": (N, "Y of end 2 (`unit`)"),
         "width": (N, "Slot width (`unit`)"), "unit": _UNIT,
         "slot_type": (S, "center_to_center (default) | overall")},
        ["x1", "y1", "x2", "y2", "width"]),
    "draw_ellipse": ("draw_ellipse", "Draw an ellipse.",
        {"cx": (N, "Center X (`unit`)"), "cy": (N, "Center Y (`unit`)"),
         "semi_major": (N, "Semi-major axis (`unit`)"),
         "semi_minor": (N, "Semi-minor axis (`unit`)"),
         "angle": (N, "Tilt of the major axis in degrees (default 0)"), "unit": _UNIT},
        ["cx", "cy", "semi_major", "semi_minor"]),
    "draw_arc_3point": ("draw_arc_3point", "Draw an arc through 3 points (start, mid, end).",
        {"x1": (N, "Start X (`unit`)"), "y1": (N, "Start Y (`unit`)"),
         "x2": (N, "X of a point on the arc (`unit`)"), "y2": (N, "Y of a point on the arc (`unit`)"),
         "x3": (N, "End X (`unit`)"), "y3": (N, "End Y (`unit`)"), "unit": _UNIT},
        ["x1", "y1", "x2", "y2", "x3", "y3"]),
    "sketch_fillet": ("sketch_fillet", "Sketch fillet between two segments or at a vertex (corner).",
        {"radius": (N, "Fillet radius (`unit`)"), "entity1": _ENT, "entity2": _ENT2,
         "corner": (A, "[x,y] of the vertex (`unit`)"), "unit": _UNIT},
        ["radius"]),
    "offset_entities": ("offset_entities", "Offset sketch entities (chain picked automatically).",
        {"entities": (A, "List of entities (id or '@x,y')"), "offset": (N, "Offset distance (`unit`)"),
         "both_directions": (B, "Offset on both sides"), "make_construction": (B, "Make result construction geometry"),
         "cap_ends": (B, "Cap the ends of open chains"), "unit": _UNIT},
        ["entities", "offset"]),
    "convert_entities": ("convert_entities",
        "Project model edges (edge_points) or a face boundary (face_point) into the active sketch.",
        {"edge_points": (A, "Points [[x,y,z],...] (`unit`), one on each edge"), "face_point": _PT3,
         "chain": (B, "Select whole chain (default true)"), "unit": _UNIT,
         "construction": (B, "true = the new lines are construction geometry (reference for dimensions, not profile); default false")}, []),
    "mirror_sketch_entities": ("mirror_sketch_entities", "Mirror sketch entities about a line or axis.",
        {"entities": (A, "Entities to mirror (id or '@x,y')"), "axis": (None, "Mirror line/centerline (id or '@x,y')"), "unit": _UNIT,
         "keep_original": (B, "Keep originals (default true)")},
        ["entities", "axis"]),
    "add_sketch_text": ("add_sketch_text", "Add sketch text (usable as extrude/cut profile).",
        {"text": (S, "Text content"), "x": (N, "X of the text position (`unit`)"),
         "y": (N, "Y of the text position (`unit`)"),
         "height": (N, "Character height (`unit`, default 5)"), "unit": _UNIT},
        ["text", "x", "y"]),
    # ---------------------------------------------------------------- features
    "extrude_boss": ("extrude_boss",
        "Boss extrude from a sketch (end conditions, draft, second direction). start_from sets where the extrusion "
        "starts: sketch_plane (default) | offset (start_offset from the sketch plane, positive along the sketch normal) "
        "| surface (start_ref {\"face\":[x,y,z]}, a point ON a face) | vertex (start_ref {\"vertex\":[x,y,z]}); the "
        "extrusion keeps its direction and starts on the plane parallel to the sketch through that face/vertex. "
        "Example: {\"sketch\":\"Sketch1\",\"depth\":20,\"end_condition\":\"blind\"}; "
        "{\"depth\":10,\"start_from\":\"surface\",\"start_ref\":{\"face\":[10,20,25]}}.",
        {"sketch": _SK, "depth": (N, "Depth (`unit`, default 10)"), "end_condition": (S, _EC),
         "depth2": (N, "Depth, direction 2 (`unit`)"),
         "end_condition2": (S, "End condition, direction 2 (as end_condition)"),
         "draft_angle": (N, "Draft angle in degrees"), "draft_outward": (B, "Draft outward"),
         "up_to_face_point": _PT3, "offset": (N, "Offset from target surface (`unit`)"),
         "reverse": (B, "Reverse the direction"), "merge": (B, "Merge with the existing body (default true)"),
         "start_offset": (N, "Start plane offset from sketch (`unit`), used with start_from=offset (or alone)"), "unit": _UNIT,
         "start_from": (S, "sketch_plane (default) | offset | surface | vertex"),
         "start_ref": (None, "surface: {\"face\":[x,y,z]}, vertex: {\"vertex\":[x,y,z]} (`unit`, point ON the face/vertex)")}, []),
    "extrude_cut": ("extrude_cut", "Extruded cut (same options as extrude_boss, including start_from/start_ref).",
        {"sketch": _SK, "depth": (N, "Depth (`unit`, default 10)"), "end_condition": (S, "As in extrude_boss"),
         "depth2": (N, "Depth, direction 2 (`unit`)"),
         "end_condition2": (S, "End condition, direction 2"),
         "draft_angle": (N, "Draft angle in degrees"), "draft_outward": (B, "Draft outward"),
         "up_to_face_point": _PT3, "offset": (N, "Offset from target surface (`unit`)"),
         "reverse": (B, "Cut on the other side"),
         "start_offset": (N, "Start plane offset (`unit`)"), "unit": _UNIT,
         "start_from": (S, "sketch_plane (default) | offset | surface | vertex"),
         "start_ref": (None, "surface: {\"face\":[x,y,z]}, vertex: {\"vertex\":[x,y,z]} (`unit`, point ON the face/vertex)")}, []),
    "revolve_boss": ("revolve_boss",
        "Revolve about the sketch centerline (or `axis`). thin_thickness makes a thin-wall feature. `axis` can be the id of "
        "a sketch segment, the name of a reference axis (e.g. \"Axis1\" or {\"axis\":\"Axis1\"}), a straight model edge "
        "{\"edge\":[x,y,z]} (`unit`, point ON it) or a line of another sketch {\"sketch\":\"Sketch1\",\"entity\":\"S0-1-2\"}. "
        "Example: {\"sketch\":\"Sketch2\",\"axis\":{\"axis\":\"Axis1\"},\"angle\":360}.",
        {"sketch": _SK, "angle": (N, "Revolve angle in degrees (default 360)"), "axis": _AXIS,
         "both_directions": (B, "Revolve in both directions"),
         "thin_thickness": (N, "Wall thickness (`unit`) for a thin feature"), "unit": _UNIT}, []),
    "revolve_cut": ("revolve_cut", "Revolved cut (grooves, relief cuts).",
        {"sketch": _SK, "angle": (N, "Revolve angle in degrees (default 360)"),
         "axis": _AXIS, "both_directions": (B, "Revolve in both directions"),
         "unit": _UNIT}, []),
    "sweep": ("sweep", "Sweep (boss or cut): profile + path sketches, or path only with circular_diameter.",
        {"profile_sketch": (S, "Profile sketch name"), "path_sketch": (S, "Path sketch name"),
         "cut": (B, "Cut, not boss"),
         "circular_diameter": (N, "Circular profile diameter (`unit`), replaces profile_sketch"),
         "twist_angle": (N, "Twist along the path in degrees (default 0)"),
         "keep_normal": (B, "Keep profile normal to path (default true)"), "unit": _UNIT}, ["path_sketch"]),
    "loft": ("loft", "Loft between 2+ profile sketches with optional guides.",
        {"profile_sketches": (A, "Profile sketch names, in order"), "guide_sketches": (A, "Guide curve sketch names"),
         "closed": (B, "Close loft to first profile"), "cut": (B, "Cut, not boss"),
         "start_tangency": (B, "Tangent start condition")}, ["profile_sketches"]),
    "shell_body": ("shell_body", "Shell the body: thickness + faces to remove (by coordinates).",
        {"thickness": (N, "Wall thickness (`unit`)"),
         "remove_faces": (A, "Points [[x,y,z],...] (`unit`), one ON each face to remove"),
         "outward": (B, "Thicken outward instead of inward"), "unit": _UNIT}, ["thickness", "remove_faces"]),
    "rib": ("rib", "Rib from a sketch with an open line touching the walls (material side automatic).",
        {"sketch": _SK, "thickness": (N, "Rib thickness (`unit`, default 3)"),
         "both_sides": (B, "Symmetric about the sketch (default true)"),
         "flip_material": (B, "Flip the material direction"), "normal_to_sketch": (B, "Extrude normal to sketch"),
         "draft_angle": (N, "Draft angle in degrees"), "unit": _UNIT}, []),
    "draft_faces": ("draft_faces", "Draft faces relative to a planar neutral face.",
        {"angle": (N, "Draft angle in degrees"), "faces": _PTS3, "neutral_face_point": _PT3,
         "flip": (B, "Flip the draft direction"), "propagate_tangent": (B, "Propagate to tangent faces"),
         "unit": _UNIT}, ["angle", "faces", "neutral_face_point"]),
    "move_faces": ("move_faces",
        "Move faces (direct edit, like Insert > Face > Move): offset each face along its normal, translate by a vector, "
        "or rotate about an axis parallel to X, Y or Z. Example: {\"faces\":[[40,50,30]],\"mode\":\"offset\",\"distance\":5}; "
        "{\"faces\":[[40,50,30]],\"mode\":\"rotate\",\"axis\":\"y\",\"axis_point\":[40,0,0],\"angle\":5}.",
        {"faces": _PTS3, "mode": (S, "offset (default) | translate | rotate"),
         "distance": (N, "offset: distance along the face normal, negative = inward; translate: length along `direction` (`unit`)"),
         "vector": (A, "translate: move vector [dx,dy,dz] (`unit`)"),
         "direction": (A, "translate: direction [dx,dy,dz] (unitless, normalized), used with distance"),
         "axis": (S, "rotate: x | y | z, axis direction (right-hand rule)"),
         "axis_point": (A, "rotate: point [x,y,z] on the rotation axis (`unit`)"),
         "angle": (N, "rotate: angle in degrees"), "unit": _UNIT}, ["faces"]),
    "fillet_at_points": ("fillet_at_points", "Constant-radius fillet on edges picked by coordinates. "
        "Example: {\"radius\":5,\"edge_points\":[[10,0,5]]}.",
        {"radius": (N, "Fillet radius (`unit`)"), "edge_points": _PTS3,
         "tangent_propagation": (B, "Propagate to tangent edges (default true)"),
         "radius2": (N, "Second radius (`unit`), default equal to radius"), "unit": _UNIT},
        ["radius", "edge_points"]),
    "fillet_variable_radius": ("fillet_variable_radius", "Variable-radius fillet (start/end radius).",
        {"edge_point": _PT3, "radius_start": (N, "Radius at the edge start (`unit`)"),
         "radius_end": (N, "Radius at the edge end (`unit`)"), "unit": _UNIT},
        ["edge_point", "radius_start", "radius_end"]),
    "chamfer_at_points": ("chamfer_at_points", "Chamfer edges picked by coordinates: distance+angle or distance+distance2.",
        {"distance": (N, "Chamfer distance (`unit`)"), "edge_points": _PTS3,
         "angle": (N, "Angle in degrees (default 45)"),
         "distance2": (N, "Second distance (`unit`); replaces angle"), "unit": _UNIT},
        ["distance", "edge_points"]),
    # ---------------------------------------------------------------- patterns and mirrors
    "linear_pattern": ("linear_pattern",
        "Linear pattern of features (by name) in 1 or 2 directions; direction = {\"edge\":[x,y,z]} (parallel to edge) | "
        "{\"face\":[x,y,z]} (face normal) | axis name. If instances leave the body, reverse. "
        "Example: {\"features\":[\"Cut1\"],\"direction1\":{\"edge\":[10,0,5]},\"count1\":4,\"spacing1\":15}.",
        {"features": (A, "Feature names to repeat"), "direction1": _DIR,
         "count1": (N, "Instances in dir. 1 (count, incl. original)"),
         "spacing1": (N, "Spacing, dir. 1 (`unit`)"), "direction2": (None, "As direction1"),
         "count2": (N, "Instances in dir. 2 (count, incl. original)"),
         "spacing2": (N, "Spacing, dir. 2 (`unit`)"),
         "reverse1": (B, "Reverse dir. 1"), "reverse2": (B, "Reverse dir. 2"),
         "geometry_pattern": (B, "Geometry pattern (faster)"), "unit": _UNIT},
        ["features", "direction1", "count1", "spacing1"]),
    "circular_pattern": ("circular_pattern",
        "Circular pattern of features about an axis (same forms as direction in linear_pattern; face must be cylindrical).",
        {"features": (A, "Feature names to repeat"), "axis": _DIR,
         "count": (N, "Instances (count, incl. original)"),
         "angle": (N, "Total angle in degrees (default 360)"),
         "equal_spacing": (B, "Space instances equally"), "reverse": (B, "Reverse the direction"),
         "geometry_pattern": (B, "Geometry pattern (faster)"), "unit": _UNIT},
        ["features", "axis", "count"]),
    "mirror_feature": ("mirror_feature", "Mirror features (by name) or the whole body about a plane or planar face.",
        {"features": (A, "Feature names to mirror"), "plane": _DIR,
         "mirror_body": (B, "Mirror whole body"), "merge": (B, "Merge result into body"),
         "geometry_pattern": (B, "Geometry pattern (faster)"), "unit": _UNIT}, ["plane"]),
    # ---------------------------------------------------------------- Hole Wizard
    "create_hole": ("create_hole",
        "Hole Wizard hole on a planar, cylindrical or inclined face, placed by coordinates (normal to the face). "
        "UNI is not in the SolidWorks database. Metric sizes M3..M70 (ISO 261 coarse + M70x6). Above M20 the SolidWorks "
        "database has counterbores only for M24/M30/M36/M42/M48/M56/M64 and no countersinks; simple and tapped sizes it "
        "lacks (M60 clearance, M68, M70) are made as a generic hole with the computed diameter (flat bottom if blind) "
        "plus a cosmetic thread for tapped holes (result key `method`). "
        "head by kind: counterbore socket | cheese | pan | button | hex | hex_cap | hex_machine; "
        "countersink socket | flat | raised | oval; tapped bottoming. "
        "Every point given (face_point AND each of positions) becomes a hole center: for several holes pass only `positions`. "
        "Example: {\"kind\":\"tapped\",\"size\":\"M6\",\"face_point\":[0,0,10],\"through\":true}; 4 holes: "
        "{\"kind\":\"simple\",\"size\":\"M8\",\"positions\":[[10,0,10],[-10,0,10],[0,10,10],[0,-10,10]],\"through\":true}.",
        {"kind": (S, "simple | tapped | countersink | counterbore"),
         "size": (S, "Metric 'M3'..'M70' (or 'M8x1.25'); ANSI inch '#10', '1/4-20'"),
         "face_point": (A, "Center [x,y,z] (`unit`) of ONE hole, on the face (it is drilled too: omit it when using positions)"),
         "positions": (A, "Hole centers [[x,y,z],...] on the face (`unit`)"),
         "depth": (N, "Blind hole depth (`unit`, default 10)"),
         "through": (B, "Through hole"),
         "diameter": (N, "Override the hole diameter, (`unit`)"),
         "thread_depth": (N, "Thread depth (`unit`)"), "unit": _UNIT,
         "standard": (S, "iso (default) | ansi_metric | ansi_inch | din | bsi | jis"),
         "head": (S, "Screw type (see tool description)"),
         "fit": (S, "close | normal (default) | loose = ISO 273 clearance; database = database value")},
        ["kind", "size"]),
    # ---------------------------------------------------------------- reference geometry
    "create_reference_plane": ("create_reference_plane",
        "Reference plane: offset (base) | angle (base+edge_point) | three_points (points) | mid_plane (refs) | "
        "line_point (line+point) | normal_to_curve (line+point) | parallel_point (base+point). The result reports the pose "
        "(plane_origin, plane_normal). A reference is a plane name ('front', 'Plane1'), {\"face\":[x,y,z]}, "
        "{\"edge\":[x,y,z]}, {\"vertex\":[x,y,z]}, {\"axis\":name}, {\"point\":name} (reference point) or a sketch entity "
        "{\"sketch\":name,\"entity\":id}. mid_plane is built as an offset of half the distance from the first reference "
        "(SolidWorks refuses the native mid-plane constraint through the API) and verified. "
        "Examples: {\"mode\":\"mid_plane\",\"refs\":[{\"face\":[0,20,15]},{\"face\":[20,20,15]}]}; "
        "{\"mode\":\"line_point\",\"line\":{\"edge\":[0,20,0]},\"point\":{\"vertex\":[20,0,30]}}; "
        "{\"mode\":\"normal_to_curve\",\"line\":{\"edge\":[0,20,0]},\"point\":{\"vertex\":[0,40,0]}} (for a point inside "
        "the curve create a reference point first); {\"mode\":\"parallel_point\",\"base\":{\"face\":[0,20,15]},"
        "\"point\":{\"vertex\":[20,40,30]}}.",
        {"mode": (S, "offset (default) | angle | three_points | mid_plane | line_point | normal_to_curve | parallel_point"),
         "base": (None, "Base: 'front', 'top', 'right', a plane name or {\"face\":[x,y,z]} (offset, angle, parallel_point)"),
         "refs": (A, "mid_plane: two parallel planes/planar faces, e.g. [{\"face\":[x,y,z]}, 'Plane1']"),
         "line": (None, "line_point / normal_to_curve: {\"edge\":[x,y,z]} | {\"axis\":name} | {\"sketch\":name,\"entity\":id}"),
         "point": (None, "line_point / normal_to_curve / parallel_point: {\"vertex\":[x,y,z]} | {\"point\":name} | "
                         "{\"sketch\":name,\"entity\":\"P0-1\"}"),
         "distance": (N, "Offset distance (`unit`, default 10)"),
         "angle": (N, "Angle in degrees about the edge (default 45)"), "edge_point": _PT3,
         "points": (A, "3 vertices [[x,y,z],...] (`unit`)"),
         "flip": (B, "Flip the plane direction"), "unit": _UNIT}, []),
    "create_reference_axis": ("create_reference_axis",
        "Reference axis by mode.",
        {"mode": (S, "two_planes (default) | cylinder | edge | two_points"), "planes": (A, "Two plane names"),
         "face_point": _PT3, "edge_point": _PT3,
         "points": (A, "2 vertices [[x,y,z],...] (`unit`)"), "unit": _UNIT}, []),
    "create_reference_point": ("create_reference_point", "Reference point: face_center | edge_center | on_edge (percent).",
        {"mode": (S, "face_center (default) | edge_center | on_edge"), "face_point": _PT3, "edge_point": _PT3,
         "percent": (N, "Position along the edge, percent 0-100 (default 50)"), "unit": _UNIT}, []),
    "create_coordinate_system": ("create_coordinate_system", "Coordinate system: origin (vertex) and X/Y/Z axes (edges).",
        {"origin_point": _PT3, "x_edge_point": _PT3, "y_edge_point": _PT3, "z_edge_point": _PT3, "unit": _UNIT,
         "x_flip": (B, "Flip the X axis"), "y_flip": (B, "Flip the Y axis"), "z_flip": (B, "Flip the Z axis")}, []),
    # ---------------------------------------------------------------- feature management
    "list_model_features": ("list_model_features", "List features: type, suppression, errors, optional dimensions.",
        {"include_dimensions": (B, "Include dimensions")}, []),
    "suppress_feature": ("suppress_feature", "Suppress a feature by name.", {"name": (S, "Feature name")}, ["name"]),
    "unsuppress_feature": ("unsuppress_feature", "Unsuppress a suppressed feature.", {"name": (S, "Feature name")}, ["name"]),
    "delete_feature": ("delete_feature",
        "DESTRUCTIVE, no undo: deletes a feature and its absorbed sketch. Needs confirm=true; refuses and lists dependent "
        "features unless delete_children=true. Safe alternative: suppress_feature.",
        {"name": (S, "Feature name"), "delete_children": (B, "Also delete dependents"),
         "confirm": (B, "Must be true to delete")}, ["name"]),
    "rename_feature": ("rename_feature", "Rename a feature.",
        {"name": (S, "Current feature name"), "new_name": (S, "New feature name")}, ["name", "new_name"]),
    "set_dimension_value": ("set_dimension_value",
        "Change a dimension by name, rebuild, report the new volume.",
        {"name": (S, "Full dimension name, e.g. 'D1@Sketch1'"),
         "value": (N, "New value (`unit`); degrees for angles"), "unit": _UNIT,
         "rebuild": (B, "Rebuild after change (default true)")}, ["name", "value"]),
    "get_dimension_value": ("get_dimension_value", "Read a dimension by name.",
        {"name": (S, "Full dimension name, e.g. 'D1@Sketch1'"), "unit": _UNIT}, ["name"]),
    "rebuild_model": ("rebuild_model", "Rebuild the active PART (not assemblies); reports features with errors and the volume.",
        {"force": (B, "Force a full rebuild")}, []),
    "rollback_to_feature": ("rollback_to_feature", "Move the rollback bar.",
        {"name": (S, "Feature name"),
         "position": (S, "after (default) | before | end")}, []),
    # ---------------------------------------------------------------- selection / measures / images
    "select_at_point": ("select_at_point", "Select a face/edge/vertex by a point ON it.",
        {"kind": (S, "face | edge | vertex"), "x": (N, "X (`unit`)"), "y": (N, "Y (`unit`)"),
         "z": (N, "Z (`unit`)"), "unit": _UNIT,
         "append": (B, "Add to current selection"), "mark": (N, "Selection mark (integer index, default 0)"),
         "tolerance": (N, "Search tolerance in mm (default 0.05)")}, ["kind", "x", "y", "z"]),
    "list_entities": ("list_entities",
        "List faces/edges/vertices with a selection point and type. Faces: surface type (plane, cylinder, cone, sphere, "
        "torus, bspline, ...) and parameters: plane normal (outward), point_on_plane and distance_from_origin; cylinder "
        "radius, axis_origin, axis_dir; cone origin (on the axis), axis_dir, radius_at_origin, half_angle_deg, apex; sphere "
        "center, radius; torus center, axis_dir, major_radius, minor_radius. Edges: curve type; line: line_point + "
        "direction; circle: center, axis_dir, radius. Lengths in `unit`, directions are unit vectors, angles in degrees. "
        "Example: {\"kind\":\"face\",\"limit\":20}.",
        {"kind": (S, "face (default) | edge | vertex"), "unit": _UNIT,
         "limit": (N, "Max entities returned (count, default 60)"),
         "include_params": (B, "Include surface/curve parameters (default true; false = compact rows)")}, []),
    "get_mass_properties": ("get_mass_properties", "Volume, mass, area, center of mass.",
        {"unit": _UNIT}, []),
    "set_material": ("set_material", "Assign a material from the SolidWorks database (e.g. 'AISI 1020').",
        {"material": (S, "Material name (default 'AISI 1020')")}, []),
}

# tool aggiunti per lotti (tools_ext/*.py): stesso formato, stesso gruppo "modeling"
_TOOLS.update(EXT_TOOLS)


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
