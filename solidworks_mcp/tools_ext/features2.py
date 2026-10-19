"""Lotto FEATURE AVANZATE: schemi dei tool -> automation/ext_features2.py (Features2Operations)."""

from ._common import S, N, B, A, O, UNIT

_PTS_FACE = lambda what: (A, f"{what}: points [[x,y,z],...] (`unit`), one ON each face (list_entities kind=face)")

TOOLS = {
    "fillet_advanced": ("fillet_advanced",
        "Advanced fillets, verified by the volume change. mode=edges: constant radius, several radii (`radii`, one per edge) or a "
        "setback at a vertex. mode=faces: FACE fillet between two face sets (`face_set1`, `face_set2`, radius `radius`). "
        "mode=full_round: FULL ROUND fillet (`side_face1`, `center_face`, `side_face2`; the radius follows the geometry, e.g. a wall "
        "of thickness t gets a semicircle of radius t/2). Examples: {\"mode\":\"full_round\",\"side_face1\":[0,30,20],"
        "\"center_face\":[5,30,40],\"side_face2\":[10,30,20]} | {\"mode\":\"edges\",\"edge_points\":[[10,30,40],[10,0,20]],"
        "\"radii\":[2,4]} | {\"mode\":\"edges\",\"edge_points\":[[10,30,40],[10,0,20],[5,0,40]],\"radius\":2,"
        "\"setback\":{\"vertex\":[10,0,40],\"distances\":[4,4,4]}}.",
        {"mode": (S, "edges (default) | faces | full_round"),
         "radius": (N, "Fillet radius (`unit`); required for edges (unless radii) and faces"),
         "radii": (A, "mode=edges: one radius (`unit`) per entry of edge_points, same order, e.g. [2,4]"),
         "edge_points": (A, "mode=edges: points [[x,y,z],...] (`unit`), one ON each edge"),
         "face_set1": _PTS_FACE("mode=faces, first face set"), "face_set2": _PTS_FACE("mode=faces, second face set"),
         "side_face1": _PTS_FACE("mode=full_round, first side face(s)"), "center_face": _PTS_FACE("mode=full_round, center face(s)"),
         "side_face2": _PTS_FACE("mode=full_round, second side face(s)"),
         "setback": (O, "mode=edges: {\"vertex\":[x,y,z] (`unit`),\"distances\":[d1,d2,d3] (`unit`, one per edge "
                     "meeting at the vertex)}; needs a single radius"),
         "tangent_propagation": (B, "mode=edges: propagate along tangent edges (default true)"), "unit": UNIT},
        []),
    "draft_advanced": ("draft_advanced",
        "Parting-line draft: the faces on the pull side of the parting-line edges are drafted by `angle` about those edges, pulling along "
        "`direction`. Verified by the volume change. (Step draft is not available in this API: see the notes.) "
        "Example: {\"direction\":{\"face\":[0,0,40]},\"edge_points\":[[15,0,20],[-15,0,20],[0,15,20],[0,-15,20]],\"angle\":5}.",
        {"direction": (None, "Pull direction: {\"face\":[x,y,z]} (planar face, `unit`) | {\"plane\":name}"),
         "edge_points": (A, "Parting-line edges: points [[x,y,z],...] (`unit`), one ON each edge"),
         "angle": (N, "Draft angle (degrees, default 5)"),
         "flip": (B, "Reverse the draft direction"),
         "propagate_tangent": (B, "Propagate to tangent faces"), "unit": UNIT},
        ["direction", "edge_points"]),
    "dome": ("dome",
        "Dome on a face (Insert > Features > Dome): circular dome (spherical cap) or elliptical dome. reverse=true makes a dent. "
        "Reports the volume change. Example: {\"face_point\":[0,0,20],\"height\":5}.",
        {"face_point": (A, "Point [x,y,z] (`unit`) ON the face"),
         "height": (N, "Dome height (`unit`), > 0"),
         "reverse": (B, "Dome inwards (dent)"),
         "elliptical": (B, "Elliptical dome (half ellipsoid on a circular face)"), "unit": UNIT},
        ["face_point", "height"]),
    "wrap_feature": ("wrap_feature",
        "Wrap a sketch onto a cylindrical/conical/planar face: emboss (raised), engrave (cut) or scribe (imprint only). The sketch must "
        "lie on a plane tangent to the face. Reports the volume change. Example: {\"sketch\":\"Sketch2\",\"face_point\":[10,0,20],"
        "\"mode\":\"engrave\",\"depth\":1}.",
        {"sketch": (S, "Name of the sketch to wrap (default: active/last)"),
         "face_point": (A, "Point [x,y,z] (`unit`) ON the target face"),
         "mode": (S, "emboss | engrave (default) | scribe"),
         "depth": (N, "Emboss/engrave depth (`unit`, default 1); ignored for scribe"),
         "reverse": (B, "Reverse the wrap direction"),
         "method": (S, "analytical (default) | spline"), "unit": UNIT},
        ["face_point"]),
    "thread_feature": ("thread_feature",
        "Modelled thread (Insert > Features > Thread) on a CIRCULAR edge from a library profile: 'Metric Die' for shafts, 'Metric Tap' for "
        "holes (auto = deduced from the geometry), size = profile configuration such as 'M10x1.5'. The thread runs from the edge into "
        "the material for `length`. Reports pitch, size and the volume change. Example: {\"edge_point\":[5,0,30],\"size\":\"M10x1.5\","
        "\"length\":20}.",
        {"edge_point": (A, "Point [x,y,z] (`unit`) ON the circular start edge"),
         "size": (S, "Size name in the profile, e.g. M10x1.5, M6x1, M8"),
         "length": (N, "Thread length (`unit`), > 0"),
         "profile": (S, "auto (default) | Metric Die | Metric Tap | Inch Die | Inch Tap | name of a file in Thread Profiles"),
         "method": (S, "cut (default) | extrude"),
         "right_handed": (B, "Right-hand thread (default true)"),
         "reverse": (B, "Run the thread in the opposite direction along the axis"),
         "start_offset": (N, "Offset of the thread start from the edge (`unit`)"),
         "start_angle": (N, "Angle of the thread start (degrees)"), "unit": UNIT},
        ["edge_point", "size", "length"]),
    "flex_feature": ("flex_feature",
        "Flex (Insert > Features > Flex) of a body: bending, tapering, twisting or stretching along `axis` about `pivot`. `amount`: "
        "bending/twisting = total angle (degrees), tapering = taper ratio (the zone ends scale by 1 -/+ amount/2), stretching = length "
        "factor of the zone (1.25 = 25 % longer). The zone is the whole body unless `trim_before`/`trim_after` are given. Reports volume "
        "ratio and bounding boxes. Example: {\"mode\":\"bending\",\"amount\":30,\"axis\":[0,0,1],\"bend_axis\":[1,0,0]}.",
        {"body": (None, "Body: omit for a single-body part | index (0..) | [x,y,z] (`unit`) ON a face of the body"),
         "mode": (S, "bending (default) | tapering | twisting | stretching"),
         "amount": (N, "bending/twisting: degrees; tapering: ratio; stretching: length factor (default 30)"),
         "pivot": (A, "Flex triad origin [x,y,z] (`unit`), default: body bounding-box center"),
         "axis": (A, "Direction along the body [x,y,z] (default [0,0,1]): twist/taper/stretch axis"),
         "bend_axis": (A, "Bending axis [x,y,z], perpendicular to axis (default: any perpendicular)"),
         "trim_before": (N, "Zone length behind the pivot (`unit`), default up to the body end"),
         "trim_after": (N, "Zone length ahead of the pivot (`unit`), default up to the body end"),
         "hard_edges": (B, "Keep hard edges at the zone ends"), "unit": UNIT},
        []),
}

DESTRUCTIVE = {
}
