"""Lotto TAVOLE 3: quota libera fra due spigoli, eliminazione di un foglio -> automation/ext_drawings3.py."""

from ._common import S, N, A

TOOLS = {
    "add_drawing_dimension": (
        "add_drawing_dimension",
        "Add a dimension between two edges of a drawing view (or the length of one edge), picked by sheet points in mm ON the "
        "visible edges (see list_drawing_views / get_drawing_layout for view positions). kind auto | horizontal | vertical. "
        "The value is read back in model mm; with `expected`, a different value (over 0.05 mm) is deleted and reported. "
        "Example: {\"edge1\":[120,150],\"edge2\":[180,150],\"kind\":\"horizontal\",\"expected\":60}.",
        {
            "edge1": (A, "[x, y] sheet mm ON the first edge"),
            "edge2": (A, "[x, y] sheet mm ON the second edge (omit = length of edge1)"),
            "position": (A, "[x, y] sheet mm of the dimension text (default: 15 mm above the points)"),
            "kind": (S, "auto (default) | horizontal | vertical"),
            "expected": (N, "Expected value in mm: a dimension with a different value is deleted (optional check)"),
        },
        ["edge1"],
    ),
    "delete_sheet": (
        "delete_sheet",
        "Delete a sheet of the active drawing, with its views (never the only sheet). Verified: the sheet name is gone.",
        {"name": (S, "Sheet name (see list_sheets)")},
        ["name"],
    ),
}

DESTRUCTIVE = {
    "delete_sheet": "Deletes a drawing sheet and all its views",
}
