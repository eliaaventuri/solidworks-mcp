"""Lotto LAMIERA 2: schemi dei tool -> automation/ext_sheetmetal2.py (SheetMetal2Operations)."""

from ._common import S, N, B, A, UNIT, SK, PT3

TOOLS = {
    "sm_swept_flange": (
        "sm_swept_flange",
        "Create a swept flange along a sheet metal body edge using an open profile sketch.",
        {
            "profile_sketch": (S, "Profile sketch name describing the flange cross-section"),
            "path_edge": (None, "Guide edge or edge point [x,y,z] along which the flange sweeps"),
            "bend_radius": (N, "Optional custom bend radius in mm (`unit`)"),
            "unit": UNIT,
        },
        ["profile_sketch"],
    ),
    "sm_normal_cut": (
        "sm_normal_cut",
        "Perform a cut normal to the sheet metal thickness to ensure clean perpendicular laser cutting faces.",
        {
            "sketch": SK,
            "depth": (N, "Optional cut depth in mm (`unit`, default through thickness)"),
            "optimize_geometry": (B, "Optimize cut geometry for manufacturing (default true)"),
            "unit": UNIT,
        },
        [],
    ),
    "sm_forming_tool": (
        "sm_forming_tool",
        "Apply a standard forming tool (louver, emboss, rib) from library to sheet metal.",
        {
            "tool_file": (S, "Path to the forming tool file (.sldftp or .sldprt)"),
            "face_point": PT3,
            "rotation_angle": (N, "Orientation angle in degrees (default 0.0)"),
            "flip": (B, "Flip forming tool direction (default false)"),
            "unit": UNIT,
        },
        ["tool_file", "face_point"],
    ),
    "sm_break_corner": (
        "sm_break_corner",
        "Apply chamfers or fillets to sharp sheet metal corners in flat or folded state.",
        {
            "edges": (A, "List of corner edge points or IDs"),
            "faces": (A, "List of face points on which to break all corners"),
            "distance": (N, "Chamfer distance or fillet radius in mm (`unit`, default 2.0)"),
            "break_type": (S, "chamfer (default) | fillet"),
            "internal_corners_only": (B, "Apply only to internal corners (default false)"),
            "unit": UNIT,
        },
        [],
    ),
    "sm_corner_trim": (
        "sm_corner_trim",
        "Trim sheet metal corners by applying corner chamfers, fillets, or relief cuts.",
        {
            "edges": (A, "List of corner edge points or IDs"),
            "faces": (A, "List of face points"),
            "distance": (N, "Chamfer distance or fillet radius in mm (`unit`, default 2.0)"),
            "break_type": (S, "chamfer (default) | fillet"),
            "unit": UNIT,
        },
        [],
    ),
}

DESTRUCTIVE = {
    "sm_normal_cut": "Cuts material perpendicular to sheet metal thickness",
    "sm_break_corner": "Removes sharp corners with chamfers or fillets",
    "sm_corner_trim": "Trims sheet metal corners",
}
