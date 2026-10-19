"""Lotto CORPI 2: schemi dei tool -> automation/ext_bodies2.py (Bodies2Operations)."""

from ._common import S, N, B, A, UNIT

_BODIES = (None, "Bodies: a name, an index or a point [x,y,z] on a face (see `list_bodies`), or a list of those. "
                 "Example: [\"Boss-Extrude1\", 1, [20,0,10]]")
_REF = (None, "Reference(s): a plane name ('Front', 'Plane1'), {\"face\":[x,y,z]} (planar face), {\"plane\":name}, "
              "{\"feature\":name} (surface feature), or a list of those")

TOOLS = {
    "move_copy_body": ("move_copy_body",
        "Move, rotate or copy solid/surface bodies (Insert > Features > Move/Copy Body, no mates). Translation: `translate` "
        "[dx,dy,dz] or `from_point`+`to_point`. Rotation: `rotate_angle` about `rotate_axis` ('x'|'y'|'z' or {\"edge\":[x,y,z]} "
        "of a straight edge parallel to an axis) through `rotate_point`. `copies` > 0 makes that many copies (one operation "
        "repeated for each copy). Rotation and translation are two separate features (done in this order). Returns the box of "
        "every body after the operation and the solid volume before/after. "
        "Example: {\"bodies\":[0],\"translate\":[50,0,0],\"copies\":2}.",
        {"bodies": _BODIES,
         "translate": (A, "Translation [dx,dy,dz] (`unit`) in model axes"),
         "from_point": (A, "Start point [x,y,z] (`unit`) of a point-to-point move (with to_point)"),
         "to_point": (A, "End point [x,y,z] (`unit`) of a point-to-point move (with from_point)"),
         "rotate_angle": (N, "Rotation angle (degrees, positive = counterclockwise about the axis direction)"),
         "rotate_axis": (None, "Rotation axis: 'x' | 'y' | 'z' (default 'z') or {\"edge\":[x,y,z]} (point ON a straight edge parallel to an axis)"),
         "rotate_point": (A, "Point [x,y,z] (`unit`) the rotation axis passes through (default origin; ignored with an edge axis)"),
         "copies": (N, "Number of copies (count, default 0 = move the bodies)"),
         "unit": UNIT}, ["bodies"]),
    "split_body": ("split_body",
        "Split bodies with a plane, a planar face or a surface (Insert > Features > Split); every piece is kept as a new body. "
        "Optionally save the pieces as part files with `save_path` (pieces are written as <name>_1.sldprt, <name>_2.sldprt..., "
        "ordered by position X, Y, Z). Every body the tool crosses is split (SolidWorks does not let the API restrict the targets). "
        "Returns the pieces and the solid volume before/after (conserved). "
        "Example: {\"tools\":[\"Plane1\"]}.",
        {"tools": _REF,
         "save_path": (S, "Optional .sldprt path: the pieces are also saved as <name>_1.sldprt, <name>_2.sldprt... (existing files are refused)"),
         "unit": UNIT}, ["tools"]),
    "intersect_bodies": ("intersect_bodies",
        "Intersect bodies (and optionally planes, planar faces, surfaces): SolidWorks computes every region and you choose which "
        "to keep. `regions`='common' (default) keeps the region inside ALL the listed solid bodies; 'all' keeps every region; "
        "a list of region indices keeps those (the result lists every region with index, volume, box, kept). The original bodies "
        "are always consumed. Example: {\"bodies\":[0,1]} -> the volume common to both bodies.",
        {"bodies": _BODIES,
         "tools": _REF,
         "regions": (None, "'common' (default) | 'all' | list of region indices (index) to keep"),
         "cap_planar": (B, "Close the planar openings of surfaces/planes used as tools (default false)"),
         "merge": (B, "Merge the resulting regions into a single body when they touch (default false)"),
         "unit": UNIT}, ["bodies"]),
    "scale_body": ("scale_body",
        "Scale the bodies of the part (Insert > Features > Scale): uniform `factor`, or independent `factor_x`/`factor_y`/"
        "`factor_z` along the model axes (missing = 1). Scale about the bodies' centroid, the origin or a coordinate system. "
        "Without `bodies` every body is scaled. The tool checks that the solid volume becomes volume * fx*fy*fz. "
        "Example: {\"factor\":2} or {\"factor_x\":1,\"factor_y\":2,\"factor_z\":3,\"about\":\"origin\"}.",
        {"factor": (N, "Uniform scale factor (ratio, > 0)"),
         "factor_x": (N, "Scale factor along model X (ratio, > 0, default 1; non-uniform)"),
         "factor_y": (N, "Scale factor along model Y (ratio, > 0, default 1; non-uniform)"),
         "factor_z": (N, "Scale factor along model Z (ratio, > 0, default 1; non-uniform)"),
         "about": (S, "centroid (default) | origin | coordinate_system"),
         "coordinate_system": (S, "Name of the coordinate system feature (with about=coordinate_system)"),
         "bodies": _BODIES,
         "unit": UNIT}, []),
    "curve_driven_pattern": ("curve_driven_pattern",
        "Pattern features along a curve (Insert > Pattern/Mirror > Curve Driven Pattern). `count` instances in total (seed "
        "included): equally spaced along the curve (`equal_spacing`, default) or every `spacing` measured along the curve. "
        "`align`: 'tangent' (instances follow the curve) or 'seed' (same orientation as the original). Verified by the volume: "
        "added instances = count - 1. Example: {\"features\":[\"Boss-Extrude2\"],\"curve\":\"Sketch3\",\"count\":5}.",
        {"features": (A, "Names of the features to repeat (the seed), e.g. [\"Boss-Extrude2\"]"),
         "curve": (None, "Curve: a sketch name (e.g. 'Sketch3') or {\"edge\":[x,y,z]} (point ON an edge)"),
         "count": (N, "Total number of instances including the seed (count, >= 2)"),
         "spacing": (N, "Distance between instances along the curve (`unit`); needed when equal_spacing is false"),
         "equal_spacing": (B, "Spread the instances evenly along the whole curve (default true); false = use `spacing`"),
         "reverse": (B, "Reverse the direction along the curve (default false)"),
         "align": (S, "tangent (default, follow the curve) | seed (same orientation as the seed)"),
         "offset_curve": (B, "Offset the curve for each instance instead of transforming it (default false)"),
         "unit": UNIT}, ["features", "curve", "count"]),
    "sketch_driven_pattern": ("sketch_driven_pattern",
        "Pattern features on the points of a sketch (Insert > Pattern/Mirror > Sketch Driven Pattern): the centroid of the seed's faces "
        "is moved onto every sketch point (in the sketch plane). Verified by the volume: added instances = number of sketch points (a point on the "
        "seed itself or outside the body is reported as a mismatch). Example: {\"features\":[\"Boss-Extrude2\"],\"sketch\":\"Sketch3\"}.",
        {"features": (A, "Names of the features to repeat (the seed)"),
         "sketch": (S, "Name of the sketch containing the points"),
         "geometry_pattern": (B, "Geometry pattern: copy the faces without re-solving each instance (default false)"),
         "unit": UNIT}, ["features", "sketch"]),
    "table_driven_pattern": ("table_driven_pattern",
        "Pattern features on a table of X,Y points (Insert > Pattern/Mirror > Table Driven Pattern): the centroid of the seed's faces "
        "(not of its volume) is moved to every point in the XY plane of a coordinate system; the coordinate along its Z axis does not change. "
        "Without `coordinate_system` one with the model axes is created at `origin`. Verified by the volume: added instances = "
        "number of points (a point on the seed itself or outside the body is reported as a mismatch). "
        "Example: {\"features\":[\"Boss-Extrude2\"],\"points\":[[30,10],[50,30]],\"coordinate_system\":\"Coordinate System1\"}.",
        {"features": (A, "Names of the features to repeat (the seed)"),
         "points": (A, "Table of points [[x,y],...] (`unit`) in the coordinate system"),
         "coordinate_system": (S, "Name of a coordinate system feature (default: a new one with the model axes at `origin`)"),
         "origin": (A, "Origin [x,y,z] (`unit`) of the coordinate system created when none is given (default [0,0,0])"),
         "unit": UNIT}, ["features", "points"]),
}

DESTRUCTIVE = {
    "split_body": "with save_path it writes part files (never overwrites: existing files are refused)",
}

OVERWRITE = {
    "split_body": "save_path",
}
