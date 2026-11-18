"""Lotto FEATURE 3: schemi dei tool -> automation/ext_features3.py (Features3Operations)."""

from ._common import S, B, A, UNIT, PT3

TOOLS = {
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
        "Parent-child tree of features, sketches and bodies. Flat lists: list_features (compact), list_model_features (errors, dimensions).",
        {
            "include_sketches": (B, "Include absorbed sketches in the tree (default true)"),
            "include_suppressed": (B, "Include suppressed features in the tree (default true)"),
        },
        [],
    ),
}

DESTRUCTIVE = {
    "boundary_cut": "Cuts solid material using boundary curves",
    "solid_sweep_cut": "Cuts solid material using a tool body",
    "defeature_model": "Removes features and internal cavities to simplify geometry",
}

OVERWRITE = {
    "defeature_model": "output_filepath",
}
