"""Lotto LAMIERA 2: schemi dei tool -> automation/ext_sheetmetal2.py (SheetMetal2Operations)."""

from ._common import S, N, B, A, UNIT, SK, PT3

TOOLS = {
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
            "unit": UNIT,
        },
        [],
    ),
}

DESTRUCTIVE = {
    "sm_normal_cut": "Cuts material perpendicular to sheet metal thickness",
    "sm_break_corner": "Removes sharp corners with chamfers or fillets",
}
