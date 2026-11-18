"""Lotto ASSIEMI 3: schemi dei tool -> automation/ext_assembly3.py (Assembly3Operations)."""

from ._common import S, N, B, A, UNIT

TOOLS = {
    "make_component_independent": (
        "make_component_independent",
        "Make a selected component instance independent, breaking link to original part and saving a unique duplicate.",
        {
            "component_name": (S, "Name of the component instance in the assembly (e.g. 'Part1-2')"),
            "new_filepath": (S, "Optional destination path for the independent component file (.sldprt)"),
        },
        ["component_name"],
    ),
    "reorder_components": (
        "reorder_components",
        "Reorder components in the assembly feature tree before or after a target component.",
        {
            "components": (A, "List of component names to reorder (e.g. ['Part2-1', 'Part3-1'])"),
            "target_component": (S, "Reference target component name (e.g. 'Part1-1')"),
            "position": (S, "Position relative to target: 'before' or 'after' (default 'after')"),
        },
        ["components", "target_component"],
    ),
    "select_components_by_size": (
        "select_components_by_size",
        "Select assembly components whose bounding box volume or size is within a percentage threshold of the entire assembly.",
        {
            "percentage": (N, "Percentage threshold ratio of total assembly size (0.0 to 100.0 percent, default 10.0)"),
        },
        [],
    ),
    "set_component_transparency": (
        "set_component_transparency",
        "Set visual transparency of an assembly component for internal assembly inspection.",
        {
            "component_name": (S, "Component name in the assembly (e.g. 'Housing-1')"),
            "transparent": (B, "True to make transparent, False for opaque (default true)"),
        },
        ["component_name"],
    ),
    "insert_new_virtual_assembly": (
        "insert_new_virtual_assembly",
        "Create a new virtual subassembly directly inside the assembly.",
        {
            "subassembly_name": (S, "Optional name prefix for the new virtual subassembly"),
        },
        [],
    ),
    "edit_part_in_context": (
        "edit_part_in_context",
        "Activate in-context part editing within the assembly to reference adjacent parts and sketch geometry.",
        {
            "component_name": (S, "Component name to edit in-context (e.g. 'Cover-1')"),
        },
        ["component_name"],
    ),
    "exit_part_in_context": (
        "exit_part_in_context",
        "Exit in-context part editing mode and return to top-level assembly editing.",
        {},
        [],
    ),
    "add_concentric_mate_with_tolerance": (
        "add_concentric_mate_with_tolerance",
        "Add a concentric mate between holes or cylindrical faces with compensatory positional hole tolerance.",
        {
            "entity1": (None, "First cylindrical face or hole entity: name or {'face': [x, y, z]}"),
            "entity2": (None, "Second cylindrical face or hole entity: name or {'face': [x, y, z]}"),
            "tolerance": (N, "Positional alignment tolerance in mm (`unit`, default 0.0)"),
            "align": (S, "Alignment: 'aligned' (default) | 'anti_aligned' | 'closest'"),
            "unit": UNIT,
        },
        ["entity1", "entity2"],
    ),
    "add_gear_mate": (
        "add_gear_mate",
        "Add a mechanical gear mate between two cylindrical faces, revolute axes, or pitch circles with a gear ratio.",
        {
            "entity1": (None, "First gear face/axis: name or {'face': [x, y, z]}"),
            "entity2": (None, "Second gear face/axis: name or {'face': [x, y, z]}"),
            "ratio_num": (N, "Gear ratio numerator or teeth count of gear 1 (default 1.0)"),
            "ratio_den": (N, "Gear ratio denominator or teeth count of gear 2 (default 1.0)"),
            "reverse": (B, "Reverse relative rotation direction (default false)"),
        },
        ["entity1", "entity2"],
    ),
    "add_hinge_mate": (
        "add_hinge_mate",
        "Add a mechanical hinge mate combining concentric and coincident/distance constraints with optional angular limits.",
        {
            "concentric_entity1": (None, "First cylindrical face for hinge axis: name or {'face': [x, y, z]}"),
            "concentric_entity2": (None, "Second cylindrical face for hinge axis: name or {'face': [x, y, z]}"),
            "coincident_face1": (None, "First planar face for axial location: name or {'face': [x, y, z]}"),
            "coincident_face2": (None, "Second planar face for axial location: name or {'face': [x, y, z]}"),
            "min_angle": (N, "Minimum rotation angle in degrees (optional)"),
            "max_angle": (N, "Maximum rotation angle in degrees (optional)"),
        },
        ["concentric_entity1", "concentric_entity2", "coincident_face1", "coincident_face2"],
    ),
    "add_screw_mate": (
        "add_screw_mate",
        "Add a mechanical screw mate linking rotation about an axis to linear displacement via a thread pitch.",
        {
            "axis_entity1": (None, "First cylindrical face or axis: name or {'face': [x, y, z]}"),
            "axis_entity2": (None, "Second cylindrical face or axis: name or {'face': [x, y, z]}"),
            "pitch": (N, "Pitch value in mm per revolution (`unit`, default 2.0)"),
            "revs_per_distance": (B, "True if pitch specifies revolutions per unit distance (default false)"),
            "reverse": (B, "Reverse thread direction / chirality (default false)"),
            "unit": UNIT,
        },
        ["axis_entity1", "axis_entity2"],
    ),
    "add_linear_coupler_mate": (
        "add_linear_coupler_mate",
        "Add an advanced linear coupler mate coupling the linear translation of two sliding components with a fixed ratio.",
        {
            "entity1": (None, "First sliding face or reference: name or {'face': [x, y, z]}"),
            "entity2": (None, "Second sliding face or reference: name or {'face': [x, y, z]}"),
            "ratio": (N, "Coupling movement ratio between component 1 and component 2 (default 1.0)"),
            "reverse": (B, "Reverse relative motion direction (default false)"),
        },
        ["entity1", "entity2"],
    ),
    "add_universal_joint_mate": (
        "add_universal_joint_mate",
        "Add a mechanical universal joint (Cardan) mate transmitting rotational motion between two non-collinear shafts.",
        {
            "shaft_entity1": (None, "First cylindrical shaft face or axis: name or {'face': [x, y, z]}"),
            "shaft_entity2": (None, "Second cylindrical shaft face or axis: name or {'face': [x, y, z]}"),
        },
        ["shaft_entity1", "shaft_entity2"],
    ),
    "dissolve_component_pattern": (
        "dissolve_component_pattern",
        "Dissolve an assembly component pattern, converting pattern instances into independent individual components.",
        {
            "pattern_name": (S, "Name of the component pattern feature to dissolve (e.g. 'LocalLPattern1')"),
        },
        ["pattern_name"],
    ),
    "edit_explode_step": (
        "edit_explode_step",
        "Edit the distance and/or the direction sense of an existing translation step of the exploded view of the active "
        "configuration. The new values are read back from SolidWorks and the exploded poses of the step's components are "
        "returned. To change the direction axis or the components, delete the step (delete_explode_step) and add a new one.",
        {
            "step_index": (N, "0-based index of the explode step, as listed by list_exploded_views (default 0)"),
            "step": (S, "Name of the explode step (e.g. 'Explode Step1'); overrides step_index"),
            "distance": (N, "New explode distance in mm (`unit`), > 0"),
            "reverse": (B, "Reverse the translation sense of the step"),
            "unit": UNIT,
        },
        [],
    ),
    "set_subassembly_flexible": (
        "set_subassembly_flexible",
        "Set subassembly solving mode to flexible (internal components can articulate in parent) or rigid.",
        {
            "component_name": (S, "Subassembly component instance name (e.g. 'SubAssy-1')"),
            "flexible": (B, "True for flexible solving, False for rigid (default true)"),
        },
        ["component_name"],
    ),
    "isolate_components": (
        "isolate_components",
        "Isolate selected components by hiding or rendering transparent all other components in the assembly.",
        {
            "components": (A, "List of component names to isolate"),
            "transparent_others": (B, "Render non-isolated components transparent instead of hiding them (default false)"),
        },
        ["components"],
    ),
    "exit_isolate": (
        "exit_isolate",
        "Exit component isolation mode, restoring the previous visibility of all components.",
        {},
        [],
    ),
    "auto_repair_mates": (
        "auto_repair_mates",
        "Attempt automatic repair and re-evaluation of dangling, broken, or misaligned mates in the assembly.",
        {},
        [],
    ),
    "check_mate_redundancy": (
        "check_mate_redundancy",
        "Analyze the top-level mates of the active assembly. Conflicting / broken mates come from SolidWorks error codes. "
        "Redundant mates (consistent duplicates that SolidWorks accepts silently) are found by measurement: each active mate "
        "is suppressed in turn and the measured degrees of freedom of every component are compared; if nothing gains freedom "
        "the mate is redundant. The mates are restored at the end and the result says whether the poses were restored.",
        {
            "max_mates": (N, "Maximum number of mates tested for redundancy (default 30; each test moves the components "
                             "slightly and restores them)"),
        },
        [],
    ),
    "create_speedpak": (
        "create_speedpak",
        "Create a lightweight, high-performance SpeedPak configuration for large assembly manipulation.",
        {
            "name": (S, "SpeedPak configuration name (default 'SpeedPak')"),
            "include_faces": (A, "Optional list of face names or points to include in SpeedPak"),
            "graphic_only": (B, "Graphic-only SpeedPak (no geometry selection) (default true)"),
        },
        [],
    ),
    "insert_cavity_feature": (
        "insert_cavity_feature",
        "Insert a cavity/impression feature into the in-context edited part using other components as core/tooling.",
        {
            "tooling_components": (A, "List of component names acting as tooling/core to subtract"),
            "scale_percentage": (N, "Shrinkage or scaling factor percentage (0.0 to 100.0 percent, default 0.0)"),
        },
        ["tooling_components"],
    ),
    "insert_join_feature": (
        "insert_join_feature",
        "Join two or more assembly components geometrically into a single merged solid body.",
        {
            "components": (A, "List of component names to combine into a merged part"),
            "hide_parts": (B, "Hide source components after creating joined body (default false)"),
        },
        ["components"],
    ),
}

DESTRUCTIVE = {
    "dissolve_component_pattern": "Converts pattern feature into individual independent component instances",
}

OVERWRITE = {
}
