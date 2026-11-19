"""Lotto SUPERFICI 3: cuci (anche in un solido), ispessisci, offset di superficie, elimina faccia -> automation/ext_surfaces3.py."""

from ._common import S, N, B, A, UNIT

TOOLS = {
    "knit_surfaces": (
        "knit_surfaces",
        "Knit surface bodies into one (Insert > Surface > Knit); with form_solid=true, surfaces that enclose a volume become a "
        "SOLID. Verified on the bodies: fewer surface bodies, or one more solid with its volume. Example: "
        "{\"form_solid\":true} knits all surface bodies of the part.",
        {
            "face_points": (A, "Points [[x,y,z],...] (`unit`), one ON a face of each surface body to knit (omit = all surface bodies)"),
            "form_solid": (B, "Try to form a solid from a closed volume (default false)"),
            "merge_faces": (B, "Merge coplanar faces of the result (default true)"),
            "gap_tolerance": (N, "Maximum gap between edges to knit, in `unit` (default 0.0025)"),
            "unit": UNIT,
        },
        [],
    ),
    "thicken_surface": (
        "thicken_surface",
        "Thicken a surface into a solid (Insert > Boss/Base > Thicken): the surface through face_point, by thickness on side1 | "
        "side2 | both. Verified: volume increase (reported with area x thickness for comparison).",
        {
            "face_point": (A, "[x,y,z] (`unit`) ON the surface to thicken"),
            "thickness": (N, "Thickness (`unit`)"),
            "side": (S, "side1 (default) | side2 | both"),
            "merge": (B, "Merge the result with the solid bodies it touches (default true)"),
            "unit": UNIT,
        },
        ["face_point", "thickness"],
    ),
    "offset_surface": (
        "offset_surface",
        "Create a surface at a constant distance from faces (of a solid or a surface); distance 0 copies the faces. Verified: "
        "one more surface body, area read back.",
        {
            "face_points": (A, "Points [[x,y,z],...] (`unit`), one ON each face to offset"),
            "distance": (N, "Offset distance (`unit`), 0 = copy"),
            "reverse": (B, "Offset to the other side (default false)"),
            "unit": UNIT,
        },
        ["face_points", "distance"],
    ),
    "delete_face": (
        "delete_face",
        "Delete faces (Insert > Surface > Delete Face): mode delete (the solid becomes an open surface) | patch (delete and heal "
        "by extending the neighbour faces, e.g. remove a fillet or a hole) | fill (delete and fill the gap). Verified: fewer "
        "faces; with patch/fill the solid must stay closed (otherwise undone).",
        {
            "face_points": (A, "Points [[x,y,z],...] (`unit`), one ON each face to delete"),
            "mode": (S, "patch (default) | delete | fill"),
            "unit": UNIT,
        },
        ["face_points"],
    ),
}

DESTRUCTIVE = {
    "delete_face": "Deletes faces of the model (the feature can be deleted to undo)",
}
