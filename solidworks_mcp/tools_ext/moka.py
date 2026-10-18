"""Lotto MOKA (PIANO_MOKA.md, strumenti nuovi): schemi dei tool -> automation/ext_moka.py (MokaOperations)."""

from ._common import S, N, B, A, UNIT

_BODY = (None, "Body: name (string), index (int, see list_bodies) or [x,y,z] (`unit`) ON a face of the body (list_bodies `face_point`)")

TOOLS = {
    "add_cosmetic_thread": ("add_cosmetic_thread",
        "ISO metric cosmetic thread (Machine Threads) on a CIRCULAR edge picked by coordinates: hole edge = internal (major "
        "diameter = nominal), shaft edge = external (minor diameter D - 1.0825 P - (0.015 + 0.011 P) mm, the value SolidWorks "
        "itself uses for M8 and M56). Reads the definition back (size, standard, diameter, depth). With through/up_to_next "
        "SolidWorks recomputes the depth from the geometry. Example: {\"edge_point\":[20,30,33.4],\"size\":\"M8\",\"depth\":12}.",
        {"edge_point": (A, "Point [x,y,z] (`unit`) ON the circular edge (list_entities kind=edge)"),
         "size": (S, "Metric size 'M6', 'M8', 'M56' (coarse pitch) or with pitch 'M8x1', 'M56x4' (pitch in mm)"),
         "kind": (S, "auto (default, deduced from the geometry) | internal | external"),
         "depth": (N, "Thread depth (`unit`); required when end_condition=blind"),
         "end_condition": (S, "blind (default) | through | up_to_next"), "unit": UNIT},
        ["edge_point", "size"]),
    "fill_pattern": ("fill_pattern",
        "Fill pattern: repeats existing features (`features`, e.g. a hole cut) OR a predefined cut (`shape` + `size`) inside a planar "
        "boundary (`face_point` on a planar face, or a closed `boundary_sketch`). Layouts: perforation (rows with stagger), "
        "concentric, square, polygon. The seed instance is at the boundary center, or at the existing feature (or `seed_point`). "
        "Margin is measured from the instance EDGE to the boundary. Reports instance count and volume change. "
        "Example: {\"face_point\":[5,50,30],\"shape\":\"circle\",\"size\":4,\"layout\":\"perforation\",\"spacing\":10,\"stagger_angle\":60,\"margin\":5}.",
        {"face_point": (A, "Fill boundary = planar face: point [x,y,z] (`unit`) ON it"),
         "boundary_sketch": (S, "Fill boundary = closed sketch name (instead of face_point)"),
         "features": (A, "Names of existing features to repeat (instead of shape), e.g. [\"Cut-Extrude1\"]"),
         "shape": (S, "Predefined seed cut (instead of features): circle | square | diamond | polygon"),
         "size": (N, "Seed size (`unit`): circle = diameter, square = side, diamond = diagonal, polygon = circumscribed diameter"),
         "layout": (S, "perforation (default) | concentric | square | polygon"),
         "spacing": (N, "Distance between instance centers (`unit`, default 10); with `count` it is ignored"),
         "loop_spacing": (N, "Distance between loops for concentric/square/polygon (`unit`, default = spacing)"),
         "count": (N, "Instances per loop/side (count) for concentric/square/polygon instead of spacing; not for perforation"),
         "stagger_angle": (N, "Row stagger for perforation (degrees, default 60)"),
         "margin": (N, "Distance instance edge to boundary (`unit`, default 0)"),
         "direction": (None, "Layout orientation: {\"edge\":[x,y,z]} | {\"axis\":name} (default: first straight side of the boundary)"),
         "polygon_sides": (N, "Number of sides of the polygon LAYOUT (count, default 6)"),
         "seed_polygon_sides": (N, "Number of sides of the polygon SEED cut (count, default 6)"),
         "rotation": (N, "Seed rotation, square/diamond/polygon (degrees, default 0)"),
         "seed_point": (None, "Seed location: [x,y,z] (`unit`) on a vertex, or {\"sketch\":name,\"entity\":\"pt@x,y\"}"),
         "flip_seed": (B, "Reverse the seed cut direction"),
         "geometry_pattern": (B, "Geometry pattern (exact copies of the seed)"), "unit": UNIT},
        []),
    "list_bodies": ("list_bodies",
        "List the bodies of the active part: name, solid/surface, volume, area, centroid, bounding box, face count and a point on a face "
        "(`face_point`) that identifies the body in delete_body / combine_bodies.",
        {"unit": UNIT}, []),
    "delete_body": ("delete_body",
        "Delete the given bodies (keep=false) or keep only them and delete all the others (keep=true) (Delete/Keep Body feature). "
        "Checks the body count afterwards. Example: {\"bodies\":[[20,40,40]],\"keep\":true}.",
        {"bodies": (A, "List of bodies: name | index | [x,y,z] on a face (see list_bodies)"),
         "keep": (B, "true = keep ONLY these bodies; false (default) = delete these bodies"), "unit": UNIT},
        ["bodies"]),
    "combine_bodies": ("combine_bodies",
        "Combine bodies (Combine feature): add = union of main + tools, subtract = main minus tools, common = intersection of main "
        "and tools. Reports the body count and the volume before/after. Example: {\"main\":\"Boss-Extrude1\",\"tools\":[\"Boss-Extrude2\"],\"operation\":\"subtract\"}.",
        {"main": _BODY, "tools": (A, "Other bodies: list of name | index | [x,y,z] on a face"),
         "operation": (S, "add (default) | subtract | common"), "unit": UNIT},
        ["main", "tools"]),
    "insert_part": ("insert_part",
        "Insert another .sldprt into the active part as body/bodies (Insert Part), optionally a configuration, then optionally move/rotate "
        "the inserted bodies. "
        "Example: {\"filepath\":\"C:\\\\parts\\\\screw.sldprt\",\"translate\":[10,0,0],\"rotate\":[0,90,0]}.",
        {"filepath": (S, "Path of the .sldprt to insert"), "configuration": (S, "Configuration name (default: active one)"),
         "translate": (A, "Translation [x,y,z] (`unit`) applied to the inserted bodies"),
         "rotate": (A, "Rotation [rx,ry,rz] (degrees) about X, Y, Z through rotation_origin"),
         "rotation_origin": (A, "Rotation center [x,y,z] (`unit`, default the origin)"),
         "link": (B, "Keep the link to the source file (default false = link broken)"), "unit": UNIT},
        ["filepath"]),
    "get_feature_definition": ("get_feature_definition",
        "Read the parameters of an existing feature in readable units: extrude/cut (end conditions both directions, depth, draft, start, "
        "reverse, merge), revolve (angles), Hole Wizard (standard, type, size, diameters, depths), linear/circular/fill patterns, "
        "cosmetic thread, fillet, chamfer, shell, reference plane (origin, normal), loft, sweep. Always: type, sketches used, parent and "
        "child features, dimensions. Other types: type + parents + dimensions + a note that the parameters are not read for that type.",
        {"name": (S, "Feature name (list_model_features)"), "unit": UNIT}, ["name"]),
}

DESTRUCTIVE = {
    "delete_body": "[DESTRUCTIVE: deletes solid/surface bodies (or all the others with keep=true); undo only by deleting the feature]",
}
