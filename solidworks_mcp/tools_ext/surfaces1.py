"""Lotto SUPERFICI 1: schemi dei tool -> automation/ext_surfaces1.py (Surfaces1Operations)."""

from ._common import S, N, B, A, UNIT, SK

_RESULT = (" Returns the new feature, the number of surface bodies, the MEASURED area of the surface it created "
           "(surface_area_mm2, in mm2) and the total area of all surface bodies.")

TOOLS = {
    "extrude_surface": ("extrude_surface",
        "Create an extruded surface (Insert > Surface > Extrude) from an open or closed sketch." + _RESULT +
        " With cap_end (and cap_end2, or mid_plane) a closed profile becomes a SOLID (the result reports solid_bodies and "
        "the volume). Draft only changes the slant length of the surface. Example: a 40 mm line extruded 20 mm gives 800 mm2.",
        {"sketch": SK,
         "depth": (N, "Depth of direction 1 (`unit`, default 10); ignored by through_all, up_to_surface"),
         "end_condition": (S, "blind (default) | mid_plane | through_all | through_all_both | up_to_next | up_to_surface "
                              "(needs up_to_face_point; offset_from_surface is not supported by SolidWorks for surfaces)"),
         "depth2": (N, "Depth of the second direction (`unit`); makes the extrusion go both ways"),
         "end_condition2": (S, "Second direction: blind (default) | through_all"),
         "draft_angle": (N, "Draft angle (degrees, default 0)"),
         "draft_outward": (B, "Draft outward instead of inward"),
         "up_to_face_point": (A, "Point [x,y,z] (`unit`) ON the face/surface to stop at (end_condition=up_to_surface); use list_entities"),
         "reverse": (B, "Extrude in the opposite direction"),
         "cap_end": (B, "Cap the end of direction 1 with a planar face (closed profiles)"),
         "cap_end2": (B, "Cap the other end (direction 2 or the second half of mid_plane); with cap_end the closed surface becomes a solid"),
         "start_offset": (N, "Start the extrusion at this offset from the sketch plane (`unit`)"),
         "unit": UNIT}, []),
    "revolve_surface": ("revolve_surface",
        "Create a revolved surface (Insert > Surface > Revolve) from a sketch profile. The axis is the centerline of the "
        "sketch (draw_centerline_axis), a sketch segment id or a reference axis / model edge." + _RESULT +
        " Example: a 30 mm line parallel to the axis at distance 10, revolved 360 degrees, gives 2*pi*10*30 = 1885 mm2.",
        {"sketch": SK,
         "angle": (N, "Revolution angle (degrees, default 360)"),
         "axis": (None, "Axis: id of a sketch segment ('S0-1-2'), name of a reference axis, {\"edge\":[x,y,z]} or {\"axis\":name}; "
                        "default: the centerline of the sketch"),
         "direction": (S, "one_direction (default) | mid_plane (angle split on both sides) | two_directions (needs angle2)"),
         "angle2": (N, "Angle of the second direction (degrees, direction=two_directions)"),
         "reverse": (B, "Revolve in the opposite direction"),
         "unit": UNIT}, []),
    "sweep_surface": ("sweep_surface",
        "Create a swept surface (Insert > Surface > Sweep): a profile sketch moved along a path sketch, optionally with guide "
        "curves and twist; or just a path with circular_diameter (tube surface)." + _RESULT +
        " Example: a 10 mm line swept along a straight 50 mm path gives 500 mm2.",
        {"profile_sketch": (S, "Profile sketch name (not needed with circular_diameter)"),
         "path_sketch": (S, "Path sketch name"),
         "guide_sketches": (A, "Names of guide curve sketches (optional)"),
         "twist_control": (S, "follow_path (default) | keep_normal | twist (constant twist along the path, uses twist_angle)"),
         "twist_angle": (N, "Total twist along the path (degrees); a non-zero value selects twist_control=twist"),
         "circular_diameter": (N, "Circular profile diameter (`unit`) instead of a profile sketch"),
         "unit": UNIT}, ["path_sketch"]),
    "loft_surface": ("loft_surface",
        "Create a lofted surface (Insert > Surface > Loft) through 2 or more profile sketches in order, with optional guide "
        "curves." + _RESULT + " Example: two parallel 40 mm lines 30 mm apart give 1200 mm2.",
        {"profile_sketches": (A, "Profile sketch names, in order (at least 2)"),
         "guide_sketches": (A, "Guide curve sketch names (optional)"),
         "closed": (B, "Close the loft (the last profile connects to the first)")}, ["profile_sketches"]),
    "planar_surface": ("planar_surface",
        "Create a planar surface (Insert > Surface > Planar) from a closed sketch, or from a closed loop of model edges "
        "(edge_points; e.g. to close a hole or an open end of a surface)." + _RESULT +
        " Example: a circle of radius 10 gives pi*100 = 314.16 mm2.",
        {"sketch": SK,
         "edge_points": (A, "Points [[x,y,z],...] (`unit`), one ON each edge of a closed planar loop (instead of a sketch); use list_entities"),
         "unit": UNIT}, []),
    "boundary_feature": ("boundary_feature",
        "Create a boundary feature (Insert > Surface > Boundary Surface, or Boundary Boss/Base, or Boundary Cut) through "
        "curves of direction 1 (sketches, in order) and optional curves of direction 2 that cross them. kind=boss and "
        "kind=cut need CLOSED profiles; boss/cut report the measured volume change. Example: curves1=[\"Sketch1\",\"Sketch2\"], "
        "two parallel 40 mm lines 30 mm apart, kind=surface gives 1200 mm2." + _RESULT,
        {"curves1": (A, "Sketch names of the direction 1 curves, in order (at least 2)"),
         "curves2": (A, "Sketch names of the direction 2 curves (optional, at least 2, they must touch the direction 1 curves)"),
         "kind": (S, "surface (default) | boss (solid from closed profiles) | cut (removes the boundary solid from the model)")},
        ["curves1"]),
    "ruled_surface": ("ruled_surface",
        "Create a ruled surface from model/surface edges (Insert > Surface > Ruled Surface): it extends the edge by a distance "
        "tangent to its face, normal to its face, or perpendicular to a given vector. tapered_to_vector is NOT supported "
        "(the SolidWorks API creates nothing)." + _RESULT + " Example: a 40 mm edge with distance 5 gives 200 mm2. "
        "Caution: a vector parallel to the faces next to the edge may hang SolidWorks.",
        {"edge_points": (A, "Points [[x,y,z],...] (`unit`), one ON each edge; use list_entities"),
         "ruled_type": (S, "tangent (default) | normal | perpendicular_to_vector"),
         "distance": (N, "Length of the ruled surface (`unit`, default 5)"),
         "vector": (A, "Direction [x,y,z] in model coordinates (unitless), for perpendicular_to_vector"),
         "reverse": (B, "Flip the direction of the surface"),
         "unit": UNIT}, ["edge_points"]),
    "fill_surface": ("fill_surface",
        "Create a fill surface (Insert > Surface > Fill) that patches a closed loop of edges, with contact, tangent or curvature "
        "continuity per edge. With merge_result it is knitted to the adjacent surface; with merge_result + form_solid, if "
        "the patch closes a hole in a closed shell, the result is a SOLID (reports solid_bodies and the volume)." + _RESULT +
        " Example: closing the open end of a 20x10 mm tube surface adds the 200 mm2 of the missing face.",
        {"edge_points": (A, "Points [[x,y,z],...] (`unit`), one ON each edge of the boundary loop; use list_entities"),
         "continuity": (None, "contact (default) | tangent | curvature, one string for all edges or a list with one value per edge"),
         "face_points": (A, "Points [[x,y,z],...] (`unit`), one ON the adjacent face of each edge (required for tangent/curvature)"),
         "merge_result": (B, "Knit the patch to the surface it closes (one surface body)"),
         "form_solid": (B, "Try to form a solid if the knitted result is a closed volume"),
         "optimize": (B, "Optimize the surface (SolidWorks option)"),
         "resolution": (N, "Resolution of the patch (count, default 1)"),
         "unit": UNIT}, ["edge_points"]),
}

DESTRUCTIVE = {
    "boundary_feature": "[DESTRUCTIVE: with kind=cut it removes material from the solid]",
}
