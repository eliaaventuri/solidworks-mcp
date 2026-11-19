"""Lotto ASSIEMI 2: schemi dei tool -> automation/ext_assembly2.py (Assembly2Operations)."""

from ._common import S, B, A

TOOLS = {
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
}

DESTRUCTIVE = {
    "dissolve_subassembly": "Dissolves subassembly structure promoting children to parent level",
}

OVERWRITE = {
}
