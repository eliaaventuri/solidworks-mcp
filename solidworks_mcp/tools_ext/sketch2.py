"""Lotto SCHIZZO 2 (strumenti di schizzo 2D/3D mancanti): schemi dei tool -> automation/ext_sketch2.py (Sketch2Operations)."""

from ._common import S, N, B, A, UNIT, SK, ENT

_PT2 = (A, "Point [x,y] (`unit`) in sketch coordinates")
_XY = lambda what: (N, f"{what} (`unit`), sketch coordinates")
_C3 = lambda what: (N, f"{what} (`unit`), model coordinates")
_ENTS = (A, "Sketch entities to act on: draw_* ids ('S0-1-2') or '@x,y' (segment nearest to that point)")

TOOLS = {
    # ------------------------------------------------------------------ trim / extend / chamfer
    "trim_sketch_entities": ("trim_sketch_entities",
        "Trim sketch entities. mode=power|closest: the part of `entity` nearest to `point` is removed up to the "
        "neighbouring intersections (an entity with no intersections is deleted). mode=corner|two_entities: trim `entity` "
        "and `entity2` to each other (SolidWorks picks the side that stays; the result lists what remains). "
        "mode=inside|outside: `boundaries` (2 entities) bound the cut of `entity`. The result is verified by re-reading the "
        "geometry (the SolidWorks return value is unreliable). Example: {\"mode\":\"power\",\"entity\":\"S0-0-1\",\"point\":[30,0]}",
        {"mode": (S, "power | closest | corner | two_entities | inside | outside (default power)"),
         "entity": ENT, "point": (A, "Pick point [x,y] (`unit`) on the part to remove (power/closest; default: the '@x,y' of entity)"),
         "entity2": ENT, "boundaries": (A, "Two boundary entities (inside/outside modes): ids or '@x,y'"),
         "unit": UNIT, "sketch": SK}, ["entity"]),
    "extend_sketch_entity": ("extend_sketch_entity",
        "Extend a sketch line or arc until it meets the next entity (verified by re-reading the geometry).",
        {"entity": ENT, "point": (A, "Point [x,y] (`unit`) near the END to extend (default: the '@x,y' of entity)"),
         "unit": UNIT, "sketch": SK}, ["entity"]),
    "sketch_chamfer": ("sketch_chamfer",
        "Chamfer the corner between two sketch lines. mode=distance_distance: `distance` along entity1 and `distance2` along "
        "entity2; distance_angle: `distance` and `angle`; equal: `distance` on both. Reports the chamfer length and the two legs.",
        {"entity1": ENT, "entity2": ENT, "corner": (A, "Corner point [x,y] (`unit`) shared by exactly two lines (instead of entity1/entity2)"),
         "mode": (S, "distance_distance | distance_angle | equal (default distance_distance)"),
         "distance": (N, "First chamfer distance (`unit`)"), "distance2": (N, "Second distance (`unit`, default = distance)"),
         "angle": (N, "Chamfer angle in degrees (distance_angle mode, default 45)"), "unit": UNIT, "sketch": SK}, []),
    # ------------------------------------------------------------------ patterns / transforms
    "sketch_linear_pattern": ("sketch_linear_pattern",
        "Linear pattern of sketch entities (count_x * count_y instances, seed included). Verified on the instance positions.",
        {"entities": _ENTS, "count_x": (N, "Instance count in direction X (default 2)"),
         "spacing_x": (N, "Spacing in direction X (`unit`)"), "count_y": (N, "Instance count in direction Y (default 1)"),
         "spacing_y": (N, "Spacing in direction Y (`unit`)"), "angle_x": (N, "Direction X angle in degrees from the sketch X axis (default 0)"),
         "angle_y": (N, "Direction Y angle in degrees (default angle_x + 90)"), "unit": UNIT, "sketch": SK}, ["entities"]),
    "sketch_circular_pattern": ("sketch_circular_pattern",
        "Circular pattern of sketch entities about `center` (count instances, seed included, counter-clockwise). "
        "Verified on the instance positions.",
        {"entities": _ENTS, "center": _PT2, "count": (N, "Total instance count, seed included (default 4)"),
         "spacing_angle": (N, "Angle between instances in degrees, counter-clockwise (default 360/count)"),
         "unit": UNIT, "sketch": SK}, ["entities", "center"]),
    "transform_sketch_entities": ("transform_sketch_entities",
        "Move, rotate or scale sketch entities, optionally leaving copies (copy=true, `copies` times; rotate and scale copies are "
        "cumulative: copy k is rotated by k*angle / scaled by scale^k). Verified by re-reading the geometry. "
        "Example: {\"operation\":\"rotate\",\"entities\":[\"S0-0-1\"],\"angle\":90,\"center\":[0,0],\"copy\":true,\"copies\":3}",
        {"operation": (S, "move | rotate | scale"), "entities": _ENTS,
         "dx": (N, "Move: displacement along X (`unit`)"), "dy": (N, "Move: displacement along Y (`unit`)"),
         "angle": (N, "Rotate: angle in degrees, counter-clockwise"), "scale": (N, "Scale: factor (ratio, > 0)"),
         "center": (A, "Rotate/scale center [x,y] (`unit`, default [0,0])"), "copy": (B, "Leave the original and create copies"),
         "copies": (N, "Number of copies (count, default 1, only with copy=true)"),
         "keep_relations": (B, "Keep sketch relations (default false: inferred relations such as horizontal block a rotation)"),
         "unit": UNIT, "sketch": SK}, ["operation", "entities"]),
    # ------------------------------------------------------------------ new entities
    "draw_center_rectangle": ("draw_center_rectangle",
        "Axis-aligned rectangle from its centre and one corner (also creates two construction diagonals).",
        {"cx": _XY("Centre X"), "cy": _XY("Centre Y"), "x2": _XY("Corner X"), "y2": _XY("Corner Y"), "unit": UNIT},
        ["cx", "cy", "x2", "y2"]),
    "draw_3point_rectangle": ("draw_3point_rectangle",
        "Rectangle at any angle from 3 points. Default: edge p1->p2, p3 sets the width (its distance from the edge line). "
        "center=true: p1 is the centre, p2 the midpoint of one side, p3 a corner.",
        {"x1": _XY("Point 1 X"), "y1": _XY("Point 1 Y"), "x2": _XY("Point 2 X"), "y2": _XY("Point 2 Y"),
         "x3": _XY("Point 3 X"), "y3": _XY("Point 3 Y"), "center": (B, "Centre-based variant (default false)"), "unit": UNIT},
        ["x1", "y1", "x2", "y2", "x3", "y3"]),
    "draw_parallelogram": ("draw_parallelogram",
        "Parallelogram from 3 vertices: p1, p2 (first edge) and p3; the fourth vertex is p1 + p3 - p2.",
        {"x1": _XY("Point 1 X"), "y1": _XY("Point 1 Y"), "x2": _XY("Point 2 X"), "y2": _XY("Point 2 Y"),
         "x3": _XY("Point 3 X"), "y3": _XY("Point 3 Y"), "unit": UNIT}, ["x1", "y1", "x2", "y2", "x3", "y3"]),
    "draw_tangent_arc": ("draw_tangent_arc",
        "Tangent arc that starts at the END of an existing line/arc at (x1,y1) and finishes at (x2,y2). Reports centre, radius "
        "and the measured tangent deviation. arc_type: tangent (default) | back give a tangent arc, left | right a normal arc.",
        {"x1": _XY("Start X (an endpoint of an existing entity)"), "y1": _XY("Start Y"), "x2": _XY("End X"),
         "y2": _XY("End Y"), "arc_type": (S, "tangent | back | left | right (default tangent)"), "unit": UNIT},
        ["x1", "y1", "x2", "y2"]),
    "draw_parabola": ("draw_parabola",
        "Parabola arc from focus, apex (vertex) and the two end points (which must lie on the parabola).",
        {"focus": _PT2, "apex": _PT2, "start": _PT2, "end": _PT2, "unit": UNIT}, ["focus", "apex", "start", "end"]),
    "draw_equation_curve": ("draw_equation_curve",
        "Curve from an equation. Explicit: y_expression in x (e.g. \"x^2/20\"), x from `start` to `end`. Parametric: "
        "x_expression and y_expression in t, t from `start` to `end`. Functions: sin cos tan asin acos atan sqr exp ln abs, "
        "operator ^, constant pi; trigonometry in radians. Values are in `unit`. The endpoints are checked against the equation.",
        {"y_expression": (S, "y = f(x) (variable x), or y(t) when x_expression is given"),
         "x_expression": (S, "x(t) for a parametric curve (variable t); omit for y=f(x)"),
         "start": (N, "Start of the x or t range (x in `unit`, t is a plain number)"),
         "end": (N, "End of the x or t range (x in `unit`, t is a plain number)"),
         "rotation": (N, "Rotation of the whole curve in degrees, counter-clockwise (default 0)"),
         "x_offset": _XY("Offset of the curve origin along X"), "y_offset": _XY("Offset of the curve origin along Y"),
         "unit": UNIT}, ["y_expression", "start", "end"]),
    # ------------------------------------------------------------------ 3D sketch
    "create_3d_sketch": ("create_3d_sketch",
        "Open a new 3D sketch (closes the active sketch first). Draw with draw_3d_line / draw_3d_spline / draw_3d_point, "
        "close it with close_sketch, then use its name as path or guide sketch of sweep, loft...", {}, []),
    "draw_3d_line": ("draw_3d_line",
        "Line in the active 3D sketch between two points given in model coordinates.",
        {"x1": _C3("Start X"), "y1": _C3("Start Y"), "z1": _C3("Start Z"), "x2": _C3("End X"), "y2": _C3("End Y"),
         "z2": _C3("End Z"), "unit": UNIT}, ["x1", "y1", "z1", "x2", "y2", "z2"]),
    "draw_3d_spline": ("draw_3d_spline",
        "Spline through points [[x,y,z],...] (at least 2) in the active 3D sketch.",
        {"points": (A, "Points [[x,y,z],...] (`unit`), model coordinates"), "unit": UNIT}, ["points"]),
    "draw_3d_point": ("draw_3d_point",
        "Point in the active 3D sketch.",
        {"x": _C3("X"), "y": _C3("Y"), "z": _C3("Z"), "unit": UNIT}, ["x", "y", "z"]),
}

DESTRUCTIVE = {
    "trim_sketch_entities": "removes parts of sketch entities (an entity with no intersections is deleted) with no undo",
}
