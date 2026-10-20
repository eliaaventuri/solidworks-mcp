"""Lotto FEATURE 3: schemi dei tool -> automation/ext_features3.py (Features3Operations)."""

from ._common import S, N, B, A, UNIT, SK, PT3, PTS3, DIR

TOOLS = {
    "rib_feature": (
        "rib_feature",
        "Create a solid rib/reinforcement feature from an open or closed sketch contour.",
        {
            "thickness": (N, "Rib wall thickness in mm (`unit`)"),
            "sketch": SK,
            "reverse_thickness": (B, "Reverse material thickness side (default false)"),
            "draft_angle": (N, "Draft angle in degrees (default 0.0)"),
            "draft_outward": (B, "Draft outward if draft angle > 0 (default false)"),
            "unit": UNIT,
        },
        ["thickness"],
    ),
    "boundary_boss": (
        "boundary_boss",
        "Create a solid boundary feature defined by curves in Direction 1 and optional Direction 2.",
        {
            "direction1_curves": (A, "List of sketch curve/edge names in Direction 1"),
            "direction2_curves": (A, "Optional list of guide curve/edge names in Direction 2"),
            "unit": UNIT,
        },
        ["direction1_curves"],
    ),
    "boundary_cut": (
        "boundary_cut",
        "Cut solid material using boundary curves in Direction 1 and optional Direction 2.",
        {
            "direction1_curves": (A, "List of sketch curve/edge names in Direction 1"),
            "direction2_curves": (A, "Optional list of guide curve/edge names in Direction 2"),
            "unit": UNIT,
        },
        ["direction1_curves"],
    ),
    "swept_cut": (
        "swept_cut",
        "Cut solid material along a swept path sketch or curve.",
        {
            "path_sketch": (S, "Path sketch or curve feature name"),
            "profile_sketch": (S, "Profile sketch name (or omitted if circular_diameter is set)"),
            "circular_diameter": (N, "Diameter in mm (`unit`) for a circular sweep cut profile"),
            "guide_sketches": (A, "Optional list of guide curve sketch names"),
            "thin_thickness": (N, "Thin wall cut thickness in mm (`unit`)"),
            "unit": UNIT,
        },
        ["path_sketch"],
    ),
    "solid_sweep_cut": (
        "solid_sweep_cut",
        "Simulate machining / milling cut by sweeping a solid tool body along a path.",
        {
            "tool_body_point": PT3,
            "path_sketch": (S, "Path sketch or trajectory curve name"),
            "guide_sketches": (A, "Optional list of guide curves"),
            "unit": UNIT,
        },
        ["tool_body_point", "path_sketch"],
    ),
    "lofted_cut": (
        "lofted_cut",
        "Cut solid material by lofting between two or more cross-section profile sketches.",
        {
            "profile_sketches": (A, "Ordered list of profile sketch names"),
            "guide_sketches": (A, "Optional list of guide curve sketch names"),
            "centerline_sketch": (S, "Optional centerline sketch or curve feature name"),
            "thin_thickness": (N, "Thin wall cut thickness in mm (`unit`)"),
            "unit": UNIT,
        },
        ["profile_sketches"],
    ),
    "thin_extrude_boss": (
        "thin_extrude_boss",
        "Create a thin-walled boss extrusion from an open or closed sketch profile.",
        {
            "thickness": (N, "Thin wall thickness in mm (`unit`)"),
            "depth": (N, "Extrusion depth in mm (`unit`, default 10.0)"),
            "sketch": SK,
            "thin_type": (S, "one_direction (default) | opposite_direction | mid_plane | two_directions"),
            "reverse": (B, "Reverse extrusion direction (default false)"),
            "unit": UNIT,
        },
        ["thickness"],
    ),
    "thin_extrude_cut": (
        "thin_extrude_cut",
        "Cut a thin-walled slot/cavity into a solid from an open or closed sketch profile.",
        {
            "thickness": (N, "Thin wall thickness in mm (`unit`)"),
            "depth": (N, "Extrusion depth in mm (`unit`, default 10.0)"),
            "sketch": SK,
            "thin_type": (S, "one_direction (default) | opposite_direction | mid_plane | two_directions"),
            "reverse": (B, "Reverse extrusion direction (default false)"),
            "unit": UNIT,
        },
        ["thickness"],
    ),
    "thin_revolve": (
        "thin_revolve",
        "Create a thin-walled revolved boss or cut feature about an axis of revolution.",
        {
            "thickness": (N, "Thin wall thickness in mm (`unit`)"),
            "angle": (N, "Revolution angle in degrees (default 360.0)"),
            "sketch": SK,
            "axis": DIR,
            "thin_type": (S, "one_direction (default) | opposite_direction | mid_plane"),
            "cut": (B, "True for revolved cut, false for boss (default false)"),
            "unit": UNIT,
        },
        ["thickness"],
    ),
    "hole_wizard_standard": (
        "hole_wizard_standard",
        "Create standardized Hole Wizard holes (counterbore, countersink, tapped) according to ISO/DIN/ANSI.",
        {
            "face_point": PT3,
            "hole_type": (S, "counterbore (default) | countersink | tap | simple"),
            "standard": (S, "Standard: 'ISO' (default) | 'DIN' | 'ANSI Metric' | 'ANSI Inch'"),
            "size": (S, "Standard thread/hole size designation (e.g. 'M8', 'M10', '1/4')"),
            "depth": (N, "Hole depth in mm (`unit`, default 20.0)"),
            "positions": PTS3,
            "unit": UNIT,
        },
        [],
    ),
    "advanced_hole": (
        "advanced_hole",
        "Create a multi-stage advanced hole with custom stacked steps (near-side, middle, far-side).",
        {
            "face_point": PT3,
            "stages": (A, "List of hole stage definitions (objects with diameter, depth, angle)"),
            "unit": UNIT,
        },
        ["face_point", "stages"],
    ),
    "mirror_body": (
        "mirror_body",
        "Mirror an entire solid or surface body in a multibody part across a plane or planar face.",
        {
            "body_point": PT3,
            "mirror_plane": (S, "Mirror reference plane name or planar face reference"),
            "unit": UNIT,
        },
        ["body_point", "mirror_plane"],
    ),
    "pattern_body": (
        "pattern_body",
        "Pattern an entire solid or surface body linearly or circularly in a multibody part.",
        {
            "body_point": PT3,
            "direction1": DIR,
            "count1": (N, "Number of pattern instances in direction 1 (count, default 2)"),
            "spacing1": (N, "Spacing between instances in direction 1 in mm (`unit`, default 10.0)"),
            "pattern_type": (S, "linear (default) | circular"),
            "count2": (N, "Number of pattern instances in direction 2 (count, default 1)"),
            "spacing2": (N, "Spacing between instances in direction 2 in mm (`unit`, default 0.0)"),
            "direction2": DIR,
            "unit": UNIT,
        },
        ["body_point", "direction1"],
    ),
    "variable_pattern": (
        "variable_pattern",
        "Create a variable pattern where individual feature instances vary according to a dimension table.",
        {
            "feature_name": (S, "Name of the seed feature to pattern"),
            "table_entries": (A, "List of pattern instance table rows specifying coordinates and dimension values"),
        },
        ["feature_name", "table_entries"],
    ),
    "freeform_feature": (
        "freeform_feature",
        "Deform or sculpt a solid/surface face organically using movable control curves and points.",
        {
            "face_point": PT3,
            "control_curves_count": (N, "Number of internal control curves to generate (count, default 2)"),
            "unit": UNIT,
        },
        ["face_point"],
    ),
    "save_bodies_as_parts": (
        "save_bodies_as_parts",
        "Save individual bodies of a multibody part to external .sldprt files.",
        {
            "body_points": (A, "List of points [[x,y,z],...], one on each body to export (default all bodies)"),
            "output_folder": (S, "Destination directory where part files are saved"),
            "create_assembly": (B, "Create an assembly (.sldasm) linking all exported bodies (default false)"),
            "overwrite": (B, "Overwrite existing part files (default false)"),
        },
        [],
    ),
    "insert_library_feature": (
        "insert_library_feature",
        "Insert a pre-configured library feature (.sldlfp) onto the active model.",
        {
            "feature_file": (S, "Path to the .sldlfp library feature file"),
            "placement_plane": (S, "Target placement plane or planar face"),
            "references": (A, "Optional list of reference entities to bind library feature parameters"),
        },
        ["feature_file"],
    ),
    "heal_edges": (
        "heal_edges",
        "Heal and merge fragmented or split edges on model faces into single continuous edges.",
        {
            "face_point": PT3,
            "tolerance": (N, "Edge healing tolerance in mm (`unit`, default 0.01)"),
            "unit": UNIT,
        },
        ["face_point"],
    ),
    "defeature_model": (
        "defeature_model",
        "Simplify model geometry by removing small features and internal cavities for lightweight export.",
        {
            "output_filepath": (S, "Optional path to save the defeatured model file"),
            "keep_features": (A, "List of important feature names to preserve"),
            "remove_internal_bodies": (B, "Remove internal closed bodies (default true)"),
        },
        [],
    ),
    "set_rollback_bar": (
        "set_rollback_bar",
        "Move the FeatureManager rollback bar before or after a specific feature.",
        {
            "target_feature": (S, "Target feature name (or empty string for beginning/end of tree)"),
            "position": (S, "Position: 'before' (default) | 'after' | 'start' | 'end'"),
        },
        [],
    ),
    "get_feature_tree": (
        "get_feature_tree",
        "Inspect the complete hierarchical parent-child structure of features, sketches, and bodies.",
        {
            "include_sketches": (B, "Include absorbed sketches in the tree (default true)"),
            "include_suppressed": (B, "Include suppressed features in the tree (default true)"),
        },
        [],
    ),
}

DESTRUCTIVE = {
    "boundary_cut": "Cuts solid material using boundary curves",
    "swept_cut": "Cuts solid material along a swept path",
    "solid_sweep_cut": "Cuts solid material using a tool body",
    "lofted_cut": "Cuts solid material between loft profiles",
    "thin_extrude_cut": "Cuts solid material using thin-walled profile",
    "defeature_model": "Removes features and internal cavities to simplify geometry",
}

OVERWRITE = {
    "save_bodies_as_parts": "output_folder",
    "defeature_model": "output_filepath",
}
