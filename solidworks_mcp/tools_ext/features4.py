"""Lotto FEATURE 4: schemi dei tool estesi di modellazione 3D -> automation/ext_features4.py (Features4Operations)."""

from ._common import S, N, B, A, UNIT, PT3

TOOLS = {
    "intersect_solid_features": (
        "intersect_solid_features",
        "Intersect multiple solid bodies, surfaces, or planes to form combined composite volumes.",
        {
            "body_names": (A, "List of solid body or surface feature names to intersect"),
            "cap_planar_openings": (B, "Whether to cap planar surface openings (default true)"),
            "unit": UNIT,
        },
        ["body_names"],
    ),

    "variable_section_sweep": (
        "variable_section_sweep",
        "Create a sweep boss with variable cross-sections controlled by law curves, parameters or equations.",
        {
            "profile_sketch": (S, "Initial profile sketch name"),
            "path_sketch": (S, "Trajectory path sketch or curve name"),
            "guide_sketches": (A, "Optional list of guide curves"),
            "scale_factor": (N, "End-to-start cross section scale factor ratio (default 1.0)"),
            "twist_angle": (N, "Total twist angle along the path in degrees (default 0.0)"),
            "unit": UNIT,
        },
        ["profile_sketch", "path_sketch"],
    ),


    "mirror_body_merge": (
        "mirror_body_merge",
        "Mirror solid bodies across a planar symmetry reference and automatically merge touching coplanar faces.",
        {
            "body_names": (A, "List of solid body names to mirror"),
            "mirror_plane": (S, "Name of the mirror plane or planar face"),
            "merge_bodies": (B, "Whether to automatically merge touching mirrored bodies (default true)"),
            "unit": UNIT,
        },
        ["body_names", "mirror_plane"],
    ),


    # 9. Lamiera (Sheet Metal)
    "cross_break": (
        "cross_break",
        "Add stiffening diagonal cross break kink lines to a flat sheet metal panel.",
        {
            "face_point": PT3,
            "depth": (N, "Cross break offset depth in mm (`unit`)"),
            "break_angle": (N, "Break kink angle in degrees (default 2.0)"),
            "unit": UNIT,
        },
        ["face_point", "depth"],
    ),
    "convert_to_sheet_metal": (
        "convert_to_sheet_metal",
        "Convert a solid body into a bent sheet metal part with automatic corner reliefs and rips.",
        {
            "thickness": (N, "Sheet metal thickness in mm (`unit`)"),
            "bend_radius": (N, "Inside bend radius in mm (`unit`)"),
            "fixed_face_point": PT3,
            "rip_edges": (A, "Optional list of edge points or names to rip"),
            "unit": UNIT,
        },
        ["thickness", "bend_radius", "fixed_face_point"],
    ),

    "update_cut_list": (
        "update_cut_list",
        "Calculate, group and update the structural cut list table for weldment structural members.",
        {
            "force_rebuild": (B, "Whether to trigger a forced rebuild before updating cut list (default true)"),
        },
        [],
    ),
    "subweldment_folder": (
        "subweldment_folder",
        "Organize and group structural members and plates into a dedicated sub-weldment folder.",
        {
            "folder_name": (S, "Name of the sub-weldment folder"),
            "member_names": (A, "List of structural member body or feature names to group"),
        },
        ["folder_name"],
    ),


}
