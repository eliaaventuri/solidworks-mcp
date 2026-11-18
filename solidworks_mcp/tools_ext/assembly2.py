"""Lotto ASSIEMI 2: schemi dei tool -> automation/ext_assembly2.py (Assembly2Operations)."""

from ._common import S, B, A

TOOLS = {
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
