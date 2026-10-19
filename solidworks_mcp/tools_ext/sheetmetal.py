"""Lotto LAMIERA: schemi dei tool -> automation/ext_sheetmetal.py (SheetMetalOperations)."""

from ._common import S, N, B, A, UNIT

TOOLS = {
    "sm_base_flange": ("sm_base_flange",
        "Base flange of a sheet-metal part. A CLOSED sketch becomes a flat sheet; an OPEN sketch (line or chain) is extruded "
        "by `depth` and gets the thickness. Creates the sheet-metal parameters (Lamiera) and the flat pattern. Example: "
        "{\"sketch\":\"Sketch1\",\"thickness\":2,\"bend_radius\":2,\"k_factor\":0.5}.",
        {"sketch": (S, "Sketch name (default: active or last sketch)"),
         "thickness": (N, "Sheet thickness (`unit`, mm), required"),
         "bend_radius": (N, "Inside bend radius (`unit`, mm; default = thickness)"),
         "depth": (N, "Extrusion length for an OPEN sketch (`unit`, mm; 0 or omitted for a closed sketch)"),
         "k_factor": (N, "K-factor (ratio between 0 and 1, default 0.5)"),
         "reverse": (B, "Reverse the thickness / extrusion direction (boolean, default false)"),
         "unit": UNIT},
        ["thickness"]),
    "sm_hem": ("sm_hem",
        "Hem on one sheet-metal edge picked by coordinates (open, closed or rolled). Uses K-factor 0.5. "
        "Example: {\"edge_point\":[0,50,15],\"type\":\"closed\",\"length\":5,\"gap\":0.5,\"bend_radius\":0.5}.",
        {"edge_point": (A, "Point [x,y,z] (`unit`) ON the sheet edge (list_entities kind=edge)"),
         "type": (S, "Hem type: closed (default) | open | rolled"),
         "length": (N, "Hem leg length (`unit`, mm, default 5)"),
         "gap": (N, "Gap between hem and sheet (`unit`, mm, default 0.5)"),
         "bend_radius": (N, "Hem bend radius (`unit`, mm, default 0.5)"),
         "position": (S, "inside (default) | outside: side of the hem"),
         "unit": UNIT},
        ["edge_point"]),
    "sm_edge_flange": ("sm_edge_flange",
        "Edge flange on a straight sheet-metal edge picked by coordinates. The flange profile is a rectangle on the edge, "
        "`length` high (measured from the picked edge along the flange). Reports volume and bounding box before/after. "
        "Example: {\"edge_point\":[0,50,15],\"length\":20,\"angle\":90,\"bend_radius\":2}.",
        {"edge_point": (A, "Point [x,y,z] (`unit`) ON a straight edge of the sheet (list_entities kind=edge)"),
         "length": (N, "Flange profile height from the edge (`unit`, mm, default 20)"),
         "angle": (N, "Flange angle (degrees, 0 to 180, default 90)"),
         "bend_radius": (N, "Inside bend radius (`unit`, mm; omitted = sheet-metal default radius)"),
         "position": (S, "material_inside (default) | material_outside | bend_outside"),
         "flip": (B, "Flip the flange to the other side of the sheet (boolean, default false)"),
         "unit": UNIT},
        ["edge_point"]),
    "sm_sketched_bend": ("sm_sketched_bend",
        "Sheet-metal bend along a straight line of a sketch placed on a face of the sheet (the sketch line is the bend "
        "line; the fixed side is chosen by SolidWorks). Example: {\"sketch\":\"Sketch2\",\"angle\":90,\"bend_radius\":2}.",
        {"sketch": (S, "Sketch name with the bend line (default: active or last sketch)"),
         "angle": (N, "Bend angle (degrees, 0 to 180, default 90)"),
         "bend_radius": (N, "Inside bend radius (`unit`, mm; omitted = SolidWorks default radius)"),
         "position": (S, "material_inside (default) | material_outside | bend_outside"),
         "flip": (B, "Flip the bending direction (boolean, default false)"),
         "unit": UNIT},
        []),
    "sm_flatten": ("sm_flatten",
        "Show the flat pattern (flat=true, the sheet is unfolded) or fold it back (flat=false). Reports the bounding box "
        "in mm of the resulting state. Example: {\"flat\":true}.",
        {"flat": (B, "true = show the unfolded flat pattern, false = fold the sheet back")},
        ["flat"]),
    "sm_export_flat_pattern": ("sm_export_flat_pattern",
        "Export the flat pattern of the saved sheet-metal part to a DXF file (SolidWorks DXF/DWG export, sheet-metal action). "
        "The part must be saved first (save_document). Shows the flat pattern first. Refuses to overwrite an existing "
        "file unless overwrite=true. Example: {\"filepath\":\"C:\\Users\\elia\\Downloads\\flat.dxf\"}.",
        {"filepath": (S, "Absolute path of the .dxf file to write, folder must exist"),
         "overwrite": (B, "true = replace an existing file (boolean, default false)"),
         "bend_lines": (B, "true = include the bend lines in the DXF (boolean, default false)")},
        ["filepath"]),
    "sm_parameters": ("sm_parameters",
        "Read (no arguments) or change the sheet-metal parameters: thickness and bend radius of the Lamiera feature and of "
        "its base flanges. Reports the values read back, including the K-factor (read only). Example: {\"thickness\":3}.",
        {"thickness": (N, "New sheet thickness (`unit`, mm)"),
         "bend_radius": (N, "New inside bend radius (`unit`, mm)"),
         "unit": UNIT},
        []),
}

DESTRUCTIVE = {
}

OVERWRITE = {"sm_export_flat_pattern": "filepath"}
