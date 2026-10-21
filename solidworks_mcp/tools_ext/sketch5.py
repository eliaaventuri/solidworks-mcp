"""Lotto SCHIZZO 5: strumenti avanzati di micro-controllo spline, relazioni, sostituzione ed export."""

S, N, B, A, O = "string", "number", "boolean", "array", "object"
_UNIT = (S, "Length unit ('mm' | 'm' | 'in' | 'ft', default from document)")

TOOLS = {
    "relax_sketch_spline": (
        "relax_sketch_spline",
        "Relax a sketch spline by smoothly redistributing tension and curvature along its length.",
        {
            "spline_entity": (S, "Optional spline segment ID to relax; if omitted, relaxes the selected or most recent spline"),
        },
        [],
    ),
    "simplify_sketch_spline": (
        "simplify_sketch_spline",
        "Simplify a sketch spline by reducing the number of through-points while staying within a geometric tolerance.",
        {
            "tolerance": (N, "Maximum allowable geometric deviation in `unit` (default 0.1 mm)"),
            "spline_entity": (S, "Optional spline segment ID to simplify; if omitted, simplifies the selected or most recent spline"),
            "unit": _UNIT,
        },
        [],
    ),
    "insert_spline_point": (
        "insert_spline_point",
        "Insert a new control / through-point onto an existing sketch spline at specified coordinates.",
        {
            "x": (N, "Point X coordinate in `unit`"),
            "y": (N, "Point Y coordinate in `unit`"),
            "z": (N, "Point Z coordinate in `unit` (default 0.0)"),
            "spline_entity": (S, "Optional spline segment ID; if omitted, targets the selected or most recent spline"),
            "unit": _UNIT,
        },
        ["x", "y"],
    ),
    "delete_spline_point": (
        "delete_spline_point",
        "Delete an existing control or through-point from a sketch spline by its point index.",
        {
            "point_index": (N, "1-based index of the spline point to remove (index, default 1)"),
            "spline_entity": (S, "Optional spline segment ID; if omitted, targets the selected or most recent spline"),
        },
        [],
    ),
    "edit_spline_handle": (
        "edit_spline_handle",
        "Adjust tangent magnitude, radial/polar angle, or curvature value of a specific spline handle.",
        {
            "point_index": (N, "0-based index of the spline point / handle to edit (index, default 0)"),
            "magnitude": (N, "Tangent vector magnitude factor (scale, e.g. 1.5)"),
            "radial_angle_deg": (N, "Radial direction angle in degrees (degrees)"),
            "polar_angle_deg": (N, "Polar direction angle in degrees (degrees)"),
            "curvature": (N, "Target curvature value to impose at handle (ratio)"),
            "spline_entity": (S, "Optional spline segment ID; if omitted, targets the selected or most recent spline"),
        },
        [],
    ),
    "replace_sketch_entity": (
        "replace_sketch_entity",
        "Replace an existing sketch entity with a new one using SOLIDWORKS Replace Entity, preserving downstream relations and features.",
        {
            "source_entity": (S, "Existing sketch segment ID to be replaced"),
            "target_entity": (S, "New replacement sketch segment ID"),
            "make_construction": (B, "true = convert original replaced entity to construction geometry (default true)"),
            "make_contour": (B, "true = close contour automatically (default false)"),
        },
        ["source_entity", "target_entity"],
    ),
    "create_sketch_belt": (
        "create_sketch_belt",
        "Create a 2D pulley-belt mechanism feature in the active sketch connecting circular pulleys.",
        {
            "pulleys": (A, "Array of circle/arc segment IDs to wrap with the belt; if omitted, wraps all selected or active circles"),
            "thickness": (N, "Belt thickness in `unit` (default 2.0 mm)"),
            "unit": _UNIT,
        },
        [],
    ),
    "suppress_sketch_relation": (
        "suppress_sketch_relation",
        "Suppress or unsuppress a specific geometric sketch relation to evaluate kinematic freedom or alternative configurations.",
        {
            "relation_index": (N, "0-based index of the relation in the active sketch (index, default 0)"),
            "suppress": (B, "true = suppress relation; false = unsuppress/activate relation (default true)"),
        },
        [],
    ),
    "get_allowed_relations": (
        "get_allowed_relations",
        "Query SOLIDWORKS for all geometric relations mathematically permissible between selected sketch entities.",
        {
            "entities": (A, "Array of sketch segment or point IDs to test; if omitted, tests currently selected entities"),
        },
        [],
    ),
    "delete_all_sketch_relations": (
        "delete_all_sketch_relations",
        "Remove all geometric constraints and relations from the active sketch in a single operation.",
        {
            "sketch": (S, "Optional sketch name (default: active sketch)"),
        },
        [],
    ),
    "list_sketch_regions": (
        "list_sketch_regions",
        "Inspect all closed intersecting planar regions and contours in the active sketch (used for contour selection extrusions).",
        {
            "sketch": (S, "Optional sketch name (default: active sketch)"),
        },
        [],
    ),
    "rotate_copy_3d_sketch": (
        "rotate_copy_3d_sketch",
        "Rotate or copy 3D sketch entities around an arbitrary 3D vector or axis in space.",
        {
            "angle_deg": (N, "Rotation angle in degrees (degrees)"),
            "base_x": (N, "Rotation axis base origin X in `unit` (default 0.0)"),
            "base_y": (N, "Rotation axis base origin Y in `unit` (default 0.0)"),
            "base_z": (N, "Rotation axis base origin Z in `unit` (default 0.0)"),
            "vector_x": (N, "Rotation axis vector direction X (ratio, default 0.0)"),
            "vector_y": (N, "Rotation axis vector direction Y (ratio, default 0.0)"),
            "vector_z": (N, "Rotation axis vector direction Z (ratio, default 1.0)"),
            "copy": (B, "true = create rotated copies; false = rotate original entities (default false)"),
            "num_copies": (N, "Number of copies to generate if copy=true (count, default 1)"),
            "entities": (A, "Optional array of sketch segment IDs to rotate; if omitted, rotates all segments in sketch"),
            "unit": _UNIT,
        },
        ["angle_deg"],
    ),
    "merge_sketch_points": (
        "merge_sketch_points",
        "Merge sketch points that are coincident within a specified geometric distance tolerance.",
        {
            "distance": (N, "Maximum merge distance tolerance in `unit` (default 0.01 mm)"),
            "unit": _UNIT,
        },
        [],
    ),
    "save_sketch_block_to_file": (
        "save_sketch_block_to_file",
        "Export and save an existing 2D sketch block definition to an external .sldblk file for reuse.",
        {
            "block_name": (S, "Name of the sketch block definition to export"),
            "filepath": (S, "Destination file path (.sldblk)"),
            "overwrite": (B, "true = overwrite destination file if it already exists (default false)"),
        },
        ["block_name", "filepath"],
    ),
    "set_sketch_performance_mode": (
        "set_sketch_performance_mode",
        "Toggle high-speed batch sketching mode (AddToDB, AutoSolve, AutoInference) to generate complex sketches rapidly.",
        {
            "add_to_db": (B, "true = add entities directly to internal database bypassing interactive UI redraws (default false)"),
            "auto_solve": (B, "true = solve sketch constraints automatically after each operation; false = pause solver (default true)"),
            "auto_inference": (B, "true = infer geometric relations while drawing (default true)"),
        },
        [],
    ),
}

DESTRUCTIVE = {
    "delete_all_sketch_relations": "Deletes all geometric relations and dimensions from the active sketch",
    "delete_spline_point": "Removes a through-point from a sketch spline",
}

OVERWRITE = {
    "save_sketch_block_to_file": "filepath",
}
