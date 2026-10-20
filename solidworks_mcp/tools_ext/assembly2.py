"""Lotto ASSIEMI 2: schemi dei tool -> automation/ext_assembly2.py (Assembly2Operations)."""

from ._common import S, N, B, A, UNIT, DIR

TOOLS = {
    "add_component": (
        "add_component",
        "Insert a part (.sldprt) or subassembly (.sldasm) into the active assembly at given position and rotation.",
        {
            "filepath": (S, "Path to the component file (.sldprt or .sldasm)"),
            "x": (N, "X coordinate of the component center in mm (`unit`, default 0.0)"),
            "y": (N, "Y coordinate of the component center in mm (`unit`, default 0.0)"),
            "z": (N, "Z coordinate of the component center in mm (`unit`, default 0.0)"),
            "rx": (N, "Rotation angle about X in degrees (default 0.0)"),
            "ry": (N, "Rotation angle about Y in degrees (default 0.0)"),
            "rz": (N, "Rotation angle about Z in degrees (default 0.0)"),
            "unit": UNIT,
        },
        ["filepath"],
    ),
    "linear_component_pattern": (
        "linear_component_pattern",
        "Create a linear pattern of components in an assembly along one or two directions.",
        {
            "seed_component": (S, "Component name to pattern (e.g. 'Perno-1')"),
            "direction1": DIR,
            "count1": (N, "Number of instances in direction 1 (count, default 2)"),
            "spacing1": (N, "Spacing in direction 1 in mm (`unit`, default 50.0)"),
            "direction2": DIR,
            "count2": (N, "Number of instances in direction 2 (count, default 1)"),
            "spacing2": (N, "Spacing in direction 2 in mm (`unit`, default 0.0)"),
            "unit": UNIT,
        },
        ["seed_component", "direction1"],
    ),
    "circular_component_pattern": (
        "circular_component_pattern",
        "Create a circular pattern of components in an assembly about an axis or cylindrical face.",
        {
            "seed_component": (S, "Component name to pattern (e.g. 'Vite-1')"),
            "axis": DIR,
            "count": (N, "Total number of instances including the seed (count, default 4)"),
            "angle": (N, "Total pattern angle in degrees (default 360.0)"),
            "equal_spacing": (B, "Equal spacing between instances (default true)"),
        },
        ["seed_component", "axis"],
    ),
    "pattern_driven_component_pattern": (
        "pattern_driven_component_pattern",
        "Pattern components matching an existing feature pattern in one of the parts.",
        {
            "seed_component": (S, "Component name to pattern (e.g. 'Vite-1')"),
            "driving_feature": (S, "Name of the driving pattern feature (e.g. 'RipetizioneLineare1')"),
        },
        ["seed_component", "driving_feature"],
    ),
    "chain_component_pattern": (
        "chain_component_pattern",
        "Pattern assembly components along an open or closed trajectory path curve/chain.",
        {
            "components": (A, "List of component names to repeat along the chain"),
            "path_curve": (S, "Path sketch or curve name"),
            "pitch": (N, "Chain pitch spacing in mm (`unit`, default 10.0)"),
            "unit": UNIT,
        },
        ["components", "path_curve"],
    ),
    "copy_with_mates": (
        "copy_with_mates",
        "Duplicate an assembly component while replicating its mates on new geometric references.",
        {
            "component": (S, "Source component name to copy"),
            "mate_references": (A, "List of new target entity references for each mate"),
            "repeat_mates": (A, "Optional list of booleans indicating which mates keep existing references"),
        },
        ["component", "mate_references"],
    ),
    "fix_component": (
        "fix_component",
        "Fix a component in 3D space, preventing it from moving or rotating.",
        {
            "name": (S, "Component name to fix (e.g. 'Base-1')"),
        },
        ["name"],
    ),
    "float_component": (
        "float_component",
        "Make a fixed component float so it can move and be constrained by mates.",
        {
            "name": (S, "Component name to make floating (e.g. 'Base-1')"),
        },
        ["name"],
    ),
    "form_new_subassembly": (
        "form_new_subassembly",
        "Group selected assembly components into a new nested subassembly.",
        {
            "components": (A, "List of component names to group"),
            "subassembly_name": (S, "Optional name for the new subassembly"),
        },
        ["components"],
    ),
    "dissolve_subassembly": (
        "dissolve_subassembly",
        "Dissolve a nested subassembly, promoting its constituent components to the parent assembly.",
        {
            "component_name": (S, "Name of the subassembly instance to dissolve"),
        },
        ["component_name"],
    ),
    "set_component_suppression_state": (
        "set_component_suppression_state",
        "Change component representation state between resolved, lightweight, suppressed, or speedpak.",
        {
            "name": (S, "Component name in the assembly"),
            "state": (S, "Target state: 'resolved' (default) | 'lightweight' | 'suppressed'"),
        },
        ["name"],
    ),
    "insert_smart_fasteners": (
        "insert_smart_fasteners",
        "Automatically insert unified fasteners into Hole Wizard holes across the assembly.",
        {
            "hole_series": (S, "Optional specific hole series or feature name to populate"),
        },
        [],
    ),
    "insert_toolbox_component": (
        "insert_toolbox_component",
        "Insert a standardized hardware component directly from SolidWorks Toolbox.",
        {
            "standard": (S, "Standard: 'ISO' (default) | 'DIN' | 'ANSI Metric' | 'ANSI Inch'"),
            "category": (S, "Category: 'Bolts' (default) | 'Nuts' | 'Washers' | 'Bearings'"),
            "part_type": (S, "Hardware type (e.g. 'Hex Head', 'Socket Head', 'Hex Nut')"),
            "size": (S, "Nominal thread size (e.g. 'M8', 'M10', '1/4-20')"),
            "length": (N, "Fastener shank length in mm (`unit`, default 30.0)"),
            "unit": UNIT,
        },
        [],
    ),
    "mate_controller": (
        "mate_controller",
        "Control, manipulate, and save multiple assembly positional configurations across mates.",
        {
            "positions": (A, "List of position states with dimension/angle values"),
            "mate_names": (A, "Optional list of mate names to include in the controller"),
        },
        ["positions"],
    ),
    "belt_and_chain_feature": (
        "belt_and_chain_feature",
        "Create an assembly belt and chain transmission feature wrapping around pulleys.",
        {
            "pulleys": (A, "List of cylindrical face points or pulley component names"),
            "belt_thickness": (N, "Belt thickness in mm (`unit`, default 2.0)"),
            "belt_width": (N, "Belt width in mm (`unit`, default 10.0)"),
            "create_belt_part": (B, "Generate a distinct new belt part component (default false)"),
            "unit": UNIT,
        },
        ["pulleys"],
    ),
    "check_hole_alignment": (
        "check_hole_alignment",
        "Inspect concentric alignment of clearance holes across mated assembly components.",
        {
            "components": (A, "Optional list of component names to inspect (default all components)"),
            "tolerance": (N, "Maximum acceptable axial misalignment in mm (`unit`, default 0.1)"),
            "unit": UNIT,
        },
        [],
    ),
    "pack_and_go": (
        "pack_and_go",
        "Collect assembly and all referenced part, drawing, and simulation files into a folder or ZIP.",
        {
            "output_folder": (S, "Destination folder path (if saving to directory)"),
            "zip_filepath": (S, "Destination ZIP file path (if saving to compressed archive)"),
            "include_drawings": (B, "Include associated 2D drawing files (default true)"),
            "include_simulation": (B, "Include simulation result files (default false)"),
            "flatten": (B, "Flatten directory structure into single folder (default false)"),
            "overwrite": (B, "Overwrite existing destination file or folder (default false)"),
        },
        [],
    ),
}

DESTRUCTIVE = {
    "dissolve_subassembly": "Dissolves subassembly structure promoting children to parent level",
}

OVERWRITE = {
    "pack_and_go": "zip_filepath",
}
