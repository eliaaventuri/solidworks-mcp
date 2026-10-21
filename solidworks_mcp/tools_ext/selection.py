"""Lotto SELEZIONE E TOPOLOGIA: schemi dei tool -> automation/ext_selection.py (SelectionOperations)."""

from ._common import S, N, B, A, UNIT, PT3, DIR

TOOLS = {
    "select_by_id": (
        "select_by_id",
        "Select a geometric entity or feature by name/identifier and type using SelectByID2.",
        {
            "name": (S, "Name or identifier of the entity, feature, or plane"),
            "object_type": (S, "Object type string: 'FACE' (default) | 'EDGE' | 'VERTEX' | 'PLANE' | 'BODYFEATURE' | 'COMPONENT'"),
            "x": (N, "X coordinate in mm (`unit`, default 0.0)"),
            "y": (N, "Y coordinate in mm (`unit`, default 0.0)"),
            "z": (N, "Z coordinate in mm (`unit`, default 0.0)"),
            "append": (B, "Append to current selection (default false)"),
            "mark": (N, "Selection mark integer (count, default 0)"),
            "unit": UNIT,
        },
        ["name"],
    ),
    "select_by_ray": (
        "select_by_ray",
        "Select an entity using a 3D raycast vector with origin, direction, and cylinder radius.",
        {
            "origin": PT3,
            "direction": DIR,
            "radius": (N, "Ray cylinder radius in mm (`unit`, default 1.0)"),
            "type_wanted": (N, "SolidWorks selection type filter integer (count, default 2 for face, 1 for edge)"),
            "append": (B, "Append to current selection (default false)"),
            "mark": (N, "Selection mark integer (count, default 0)"),
            "unit": UNIT,
        },
        ["origin", "direction"],
    ),
    "query_topology_by_criteria": (
        "query_topology_by_criteria",
        "Filter and query B-Rep topology (faces, edges, vertices) by geometric properties with centroid coordinates.",
        {
            "entity_type": (S, "Entity type: 'face' (default) | 'edge' | 'vertex'"),
            "surface_type": (S, "Filter by surface type: 'plane' | 'cylinder' | 'cone' | 'sphere' | 'torus' | 'bspline'"),
            "normal": (A, "Filter planar faces by normal vector [nx, ny, nz]"),
            "min_area": (N, "Minimum surface area in mm2 (`unit`)"),
            "max_area": (N, "Maximum surface area in mm2 (`unit`)"),
            "radius": (N, "Filter cylindrical/spherical faces by radius in mm (`unit`)"),
            "tolerance": (N, "Geometric comparison tolerance in mm (`unit`, default 0.01)"),
            "unit": UNIT,
        },
        [],
    ),
    "clear_selection": (
        "clear_selection",
        "Clear all currently selected entities from the SolidWorks selection buffer.",
        {},
        [],
    ),
    "get_active_selection": (
        "get_active_selection",
        "List all entities currently selected in the SelectionManager with types, marks, and coordinates.",
        {},
        [],
    ),
    "set_view_orientation": (
        "set_view_orientation",
        "Set the 3D viewport camera to a standard named view orientation.",
        {
            "orientation": (S, "View orientation: 'isometric' (default) | 'front' | 'back' | 'top' | 'bottom' | 'right' | 'left' | 'normal_to'"),
        },
        [],
    ),
    "zoom_to_fit": (
        "zoom_to_fit",
        "Zoom the active graphics viewport to fit all model geometry onto the screen.",
        {},
        [],
    ),
    "export_labeled_viewport_image": (
        "export_labeled_viewport_image",
        "Capture a rendered screenshot with overlay numbered labels on visible model faces and edges. Returns native ImageContent for Vision LLMs.",
        {
            "filepath": (S, "Output image file path (.png)"),
            "entity_type": (S, "Entity labels to overlay: 'face' (default) | 'edge' | 'both'"),
            "max_labels": (N, "Maximum number of numbered labels to overlay (count, default 30)"),
            "width": (N, "Image width in pixels (count, default 1920)"),
            "height": (N, "Image height in pixels (count, default 1080)"),
            "overwrite": (B, "Overwrite existing image file (default false)"),
        },
        ["filepath"],
    ),
}

DESTRUCTIVE = {}

OVERWRITE = {
    "export_labeled_viewport_image": "filepath",
}
