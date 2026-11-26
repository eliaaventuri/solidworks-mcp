"""Lotto FEATURE 3: schemi dei tool -> automation/ext_features3.py (Features3Operations)."""

from ._common import S, B, A, UNIT

TOOLS = {
    "insert_library_feature": (
        "insert_library_feature",
        "Insert a library feature (.sldlfp, e.g. from the SolidWorks design library) on a planar face or plane. The file "
        "decides how many locating references it needs (their names are reported when the count is wrong). Rebuild errors "
        "and volume are checked; on failure the created features are removed.",
        {
            "feature_file": (S, "Path to the .sldlfp library feature file"),
            "placement_plane": (None, "Placement: planar face {\"face\":[x,y,z]} or plane name"),
            "references": (A, "Locating references required by the file, in order: edges [x,y,z] or {\"edge\":[x,y,z]}"),
            "unit": UNIT,
        },
        ["feature_file"],
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
}

OVERWRITE = {
}
