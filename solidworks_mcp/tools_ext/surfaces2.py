"""Lotto SUPERFICI 2: schemi dei tool -> automation/ext_surfaces2.py (Surfaces2Operations)."""

from ._common import N, B, A, UNIT, PT3

TOOLS = {
    "thicken_cut": (
        "thicken_cut",
        "Cut solid geometry by thickening an intersecting surface body or face.",
        {
            "face_point": PT3,
            "thickness": (N, "Thickness value in mm (`unit`)"),
            "direction": (N, "Thicken direction: 0 (side 1) | 1 (side 2) | 2 (both sides, midplane) (index, default 0)"),
            "unit": UNIT,
        },
        ["face_point", "thickness"],
    ),
    "curve_through_reference_points": (
        "curve_through_reference_points",
        "Create an associative 3D curve passing through existing model vertices and sketch points.",
        {
            "points": (A, "List of 3D reference point coordinates [[x,y,z],...] (`unit`)"),
            "closed": (B, "Whether the 3D curve should form a closed loop (default false)"),
            "unit": UNIT,
        },
        ["points"],
    ),
    "reverse_surface_normal": (
        "reverse_surface_normal",
        "Reverse the surface normal vector orientation of a surface body.",
        {
            "face_point": PT3,
            "unit": UNIT,
        },
        ["face_point"],
    ),
    "find_open_surface_edges": (
        "find_open_surface_edges",
        "Inspect a surface body and identify all open, unknitted boundary edges.",
        {
            "surface_point": PT3,
            "unit": UNIT,
        },
        [],
    ),
    "check_watertight_surface": (
        "check_watertight_surface",
        "Verify whether a surface body forms a completely closed watertight volume ready for solid conversion.",
        {
            "surface_point": PT3,
            "unit": UNIT,
        },
        [],
    ),
    "zebra_stripes_display": (
        "zebra_stripes_display",
        "Toggle zebra stripes reflection display on the model for visual curvature continuity analysis.",
        {
            "enable": (B, "True to enable zebra stripes display, false to disable (default true)"),
        },
        [],
    ),
    "gaussian_curvature_display": (
        "gaussian_curvature_display",
        "Toggle Gaussian surface curvature color gradient mapping in the viewport.",
        {
            "enable": (B, "True to activate Gaussian curvature display, false to turn off (default true)"),
            "min_radius": (N, "Minimum radius of curvature threshold in mm (`unit`, default 0.1)"),
            "max_radius": (N, "Maximum radius of curvature threshold in mm (`unit`, default 100.0)"),
            "unit": UNIT,
        },
        [],
    ),
}

DESTRUCTIVE = {
    "thicken_cut": "Cuts solid material by thickening intersecting surface",
}
