"""Lotto CURVE: schemi dei tool -> automation/ext_curves.py (CurvesOperations)."""

from ._common import S, N, B, A, UNIT

_SKC = (S, "Name of a sketch containing a circle (default: active/last sketch)")

TOOLS = {
    "create_helix": ("create_helix",
        "Create a helix or spiral from a circle in a sketch (Insert > Curve > Helix/Spiral). Returns the Helix feature "
        "with its measured length, start/end points and the length computed from the parameters. The result can be used "
        "as the path of `sweep` (path_sketch = the feature name) to make springs and threads.",
        {"sketch": _SKC,
         "definition": (S, "pitch_revolutions (default) | height_revolutions | height_pitch | spiral (pitch = radial pitch per revolution)"),
         "pitch": (N, "Pitch per revolution (`unit`); radial pitch for a spiral. Required by pitch_revolutions, height_pitch, spiral"),
         "height": (N, "Total height (`unit`). Required by height_revolutions and height_pitch"),
         "revolutions": (N, "Number of revolutions (count, may be fractional). Required by pitch_revolutions, height_revolutions, spiral"),
         "clockwise": (B, "Clockwise (true, default) or counterclockwise rotation, as the SolidWorks option"),
         "reverse_direction": (B, "Grow to the other side of the sketch plane; for a spiral it makes the spiral go inward"),
         "start_angle": (N, "Start angle (degrees, default 0)"),
         "taper_angle": (N, "Taper angle (degrees, 0 = cylindrical helix; not for spirals)"),
         "taper_outward": (B, "With taper_angle: radius grows (true, default) or shrinks (false) along the height"),
         "unit": UNIT}, []),
    "create_variable_pitch_helix": ("create_variable_pitch_helix",
        "Create a variable pitch helix: a table of segments, each with its END pitch (and optionally diameter); pitch and "
        "diameter change linearly along each segment. Example: segments=[{\"revolutions\":2,\"pitch\":4},"
        "{\"revolutions\":1,\"pitch\":8,\"diameter\":30}] starts at the circle of the sketch with pitch 4.",
        {"sketch": _SKC,
         "definition": (S, "pitch_revolutions (default; segment key 'revolutions') | height_pitch (segment key 'height')"),
         "segments": (A, "List of {\"revolutions\" (count) or \"height\" (`unit`) of the segment, \"pitch\" (`unit`) at its end, "
                         "\"diameter\" (`unit`, optional, default = previous)}"),
         "start_pitch": (N, "Pitch at the start (`unit`, default = pitch of the first segment)"),
         "start_diameter": (N, "Diameter at the start (`unit`, default = diameter of the sketch circle)"),
         "clockwise": (B, "Clockwise (true, default) or counterclockwise"),
         "reverse_direction": (B, "Grow to the other side of the sketch plane"),
         "start_angle": (N, "Start angle (degrees, default 0)"), "unit": UNIT}, ["segments"]),
    "project_curve": ("project_curve",
        "Create a projected curve (Insert > Curve > Projected): either a sketch projected onto one or more model faces "
        "(`face_points`) along the sketch normal, or a sketch projected onto another sketch (`target_sketch`, the curve is the "
        "intersection of the two extruded sketches). Returns the curve feature with its measured length and end points.",
        {"sketch": (S, "Sketch to project (default: active/last sketch)"),
         "face_points": (A, "Points [[x,y,z],...] (`unit`), one ON each face to project onto; use list_entities"),
         "target_sketch": (S, "Name of a second sketch (on a crossing plane) to project onto instead of faces"),
         "reverse": (B, "Project in the opposite direction (default direction: normal to the sketch plane)"),
         "both_directions": (B, "Also create the projection in the opposite direction as a second curve (reported as other_direction_feature)"),
         "unit": UNIT}, []),
    "composite_curve": ("composite_curve",
        "Join model edges and/or sketch entities into one composite curve (Insert > Curve > Composite). The entities must be "
        "contiguous (touching end to end). Returns the curve with its measured total length and end points; it can be the path of `sweep`.",
        {"edge_points": (A, "Points [[x,y,z],...] (`unit`), one ON each model edge to join"),
         "sketch_entities": (A, "Sketch entities to join: [{\"sketch\":\"Sketch1\",\"entity\":\"S0-1-2\"}] (entity = draw_* id or '@x,y' in sketch coordinates, `unit`)"),
         "unit": UNIT}, []),
    "curve_through_points": ("curve_through_points",
        "Create a spline curve through given XYZ points (Insert > Curve > Through XYZ Points), open or closed. Points can "
        "be coordinates and/or existing model vertices. Returns the curve with its measured length and end points.",
        {"points": (A, "Points [[x,y,z],...] (`unit`), in order"),
         "vertex_points": (A, "Points [[x,y,z],...] (`unit`), one ON each existing model vertex, appended after `points`"),
         "closed": (B, "Close the curve (adds the first point at the end)"),
         "unit": UNIT}, []),
    "split_line": ("split_line",
        "Split faces with a split line (Insert > Curve > Split Line): projection of a sketch onto faces (along the sketch "
        "normal, in both directions), silhouette (relative to a direction plane) or intersection (with a plane/face). The faces get divided: "
        "the result reports the face count before/after and the areas of the new faces. NOTE: mode=intersection is not "
        "supported by the SolidWorks 2026 API (the tool reports it).",
        {"mode": (S, "projection (default) | silhouette | intersection"),
         "sketch": (S, "projection: sketch to project, a closed loop or a curve crossing the faces (default: active/last sketch)"),
         "face_points": (A, "Points [[x,y,z],...] (`unit`), one ON each face to split; use list_entities"),
         "direction": (None, "silhouette: view direction as {\"plane\": name} (standard plane 'Top' or a reference plane) or {\"face\": [x,y,z]}"),
         "cutter": (None, "intersection: splitting tool as {\"plane\": name} or {\"face\": [x,y,z]}"),
         "unit": UNIT}, ["face_points"]),
}

DESTRUCTIVE = {
}
