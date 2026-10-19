"""Lotto SALDATURE: schemi dei tool -> automation/ext_weldments.py (WeldmentsOperations)."""

# importare da ._common solo le costanti usate (S, N, B, A, O, UNIT, SK, ENT, PT3, PTS3, DIR)
from ._common import S, N, B, A, UNIT, SK

TOOLS = {
    "list_weldment_profiles": ("list_weldment_profiles",
        "List the weldment profile standards (folders of the SolidWorks weldment profiles), their profile types and the sizes "
        "(configurations) of each profile. Without `profile` only the counts are returned; with `profile` the full size list. "
        "Example: {\"standard\":\"iso\",\"profile\":\"square tube\"}.",
        {"standard": (S, "Standard folder, e.g. iso, ansi, DIN, BSI (case-insensitive); omit for all standards"),
         "profile": (S, "Profile name without extension, e.g. 'square tube', 'pipe' (case-insensitive); omit for all")},
        []),
    "structural_member": ("structural_member",
        "Structural members (Structural Member feature) along the segments of a sketch, with a weldment profile and a size "
        "(configuration). The sketch must contain connected lines; corners get a 45 degree miter by default. Reports bodies "
        "before/after, volume before/after and the profile file. Example: {\"sketch\":\"Sketch1\",\"standard\":\"iso\","
        "\"profile\":\"square tube\",\"size\":\"40 x 40 x 4\",\"corner_treatment\":\"miter\"}.",
        {"sketch": SK,
         "segments": (A, "Segment ids to use, e.g. [\"S0-1-2\"] (omit for all segments of the sketch)"),
         "standard": (S, "Standard folder: iso, ansi, DIN, BSI, ... (default iso)"),
         "profile": (S, "Profile name without extension, e.g. 'square tube' (default), 'pipe', 'angle iron'"),
         "size": (S, "Size = configuration of the profile, e.g. '40 x 40 x 4' (default: first size of the profile)"),
         "corner_treatment": (S, "miter (default, 45 degrees) | butt_first | butt_second | none"),
         "rotation": (N, "Rotation of the profile about its path, in degrees (default 0)")},
        []),
    "weldment_trim_extend": ("weldment_trim_extend",
        "Trim or extend structural member bodies up to a boundary body (Trim/Extend weldment feature): a member that "
        "crosses the boundary is cut at its surface; with extend, a member that stops short is lengthened to it. Indices come from "
        "list_bodies. Example: {\"bodies_to_trim\":[1],\"trim_boundary\":[0]}.",
        {"bodies_to_trim": (A, "Members to trim or extend: list of body name | index | [x,y,z] on a face (see list_bodies)"),
         "trim_boundary": (None, "Boundary body: name | index | [x,y,z] on a face (see list_bodies)"),
         "end_condition": (S, "trim (default: cut the members that cross the boundary) | extend (also extend the members that stop short of it)"),
         "gap": (N, "Gap between the trimmed member and the boundary (`unit`, default 0)"),
         "unit": UNIT},
        ["bodies_to_trim", "trim_boundary"]),
    "weldment_end_cap": ("weldment_end_cap",
        "End cap (End Cap feature) closing the end face of a structural member: the cap is a plate set flush inside the "
        "section (inner square) with the given thickness, optionally inset by an offset and chamfered. Example: "
        "{\"face_point\":[0,0,18],\"thickness\":10}.",
        {"face_point": (A, "Point [x,y,z] (`unit`) ON the end face of the member (see list_entities kind=face)"),
         "thickness": (N, "Cap thickness (`unit`), must be > 0"),
         "offset": (N, "Inset of the cap from the end face (`unit`, default 0 = flush)"),
         "chamfer": (N, "Chamfer size on the cap edge (`unit`, default 0 = none)"),
         "unit": UNIT},
        ["face_point", "thickness"]),
    "weldment_cut_list": ("weldment_cut_list",
        "Weldment cut list (folder 'Elenco elementi'): creates it from the solid bodies if missing, updates it and returns "
        "each member with its quantity and bounding-box size in mm (a 45 degree miter makes the box longer than the centerline). "
        "Example: {\"update\":true}.",
        {"update": (B, "true (default) = update the cut list before reading it; false = read only")},
        []),
}

DESTRUCTIVE = {
    "weldment_trim_extend": "trims structural member bodies",
}
