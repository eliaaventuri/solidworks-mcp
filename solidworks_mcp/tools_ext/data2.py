"""Lotto DATI ED EXPORT 2: schemi dei tool estesi di gestione dati, configurazioni, export e DimXpert MBD -> automation/ext_data2.py (Data2Operations)."""

from ._common import S, N, B, A, UNIT

TOOLS = {
    # 1. Proprietà Personalizzate e Metadati
    "get_config_custom_property": (
        "get_config_custom_property",
        "Read the resolved and expression value of a configuration-specific custom property.",
        {
            "property_name": (S, "Name of the custom property to read"),
            "configuration": (S, "Configuration name (or omitted for active configuration)"),
        },
        ["property_name"],
    ),
    "set_config_custom_property": (
        "set_config_custom_property",
        "Set or update a configuration-specific custom property on the model.",
        {
            "property_name": (S, "Name of the custom property to set"),
            "value": (S, "Text or numeric value of the property"),
            "configuration": (S, "Target configuration name (or omitted for active configuration)"),
            "property_type": (S, "Property type ('text', 'number', 'date', 'yesno') (default 'text')"),
        },
        ["property_name", "value"],
    ),
    "set_document_summary_info": (
        "set_document_summary_info",
        "Update the standard document summary metadata fields (title, subject, author, keywords, comments).",
        {
            "title": (S, "Document title metadata"),
            "subject": (S, "Document subject summary"),
            "author": (S, "Document author name"),
            "keywords": (S, "Keywords comma-separated tags"),
            "comments": (S, "General descriptive comments"),
        },
        [],
    ),


    # 3. Equazioni e Variabili Globali
    "export_equations_to_file": (
        "export_equations_to_file",
        "Export all equations and global variables to an external text file for cross-model synchronization.",
        {
            "filepath": (S, "Destination text file path (.txt)"),
            "overwrite": (B, "Overwrite existing file if present (default false)"),
        },
        ["filepath"],
    ),

    "create_derived_configuration": (
        "create_derived_configuration",
        "Create a child derived configuration under an existing parent configuration.",
        {
            "name": (S, "Name of the new derived configuration"),
            "parent_configuration": (S, "Parent configuration name to derive from"),
            "description": (S, "Optional descriptive comment for the variant"),
        },
        ["name", "parent_configuration"],
    ),


    "export_dxf_flat_pattern": (
        "export_dxf_flat_pattern",
        "Export sheet metal unfolded flat pattern directly to 1:1 DXF for CNC laser/punching cutting.",
        {
            "filepath": (S, "Destination DXF file path (.dxf)"),
            "include_bend_lines": (B, "Whether to include forming bend lines in DXF (default true)"),
            "overwrite": (B, "Overwrite existing file if present (default false)"),
        },
        ["filepath"],
    ),
    "export_ifc": (
        "export_ifc",
        "Export 3D geometry to Industry Foundation Classes (IFC) BIM format for architectural workflows.",
        {
            "filepath": (S, "Destination IFC file path (.ifc)"),
            "schema_version": (S, "IFC schema: only 'IFC2X3' is written by SolidWorks 2026 (default 'IFC2X3'; 'IFC4' is refused)"),
            "overwrite": (B, "Overwrite existing file if present (default false)"),
        },
        ["filepath"],
    ),
    "export_gltf_glb": (
        "export_gltf_glb",
        "Export 3D model to glTF / GLB format for web 3D interactive viewing and AR visualization.",
        {
            "filepath": (S, "Destination glTF/GLB file path (.gltf, .glb)"),
            "binary": (B, "Export as single self-contained binary .glb file (default true)"),
            "overwrite": (B, "Overwrite existing file if present (default false)"),
        },
        ["filepath"],
    ),
    "export_3d_pdf": (
        "export_3d_pdf",
        "Generate an interactive 3D PDF file viewable with 360-degree rotation in Adobe Reader.",
        {
            "filepath": (S, "Destination 3D PDF file path (.pdf)"),
            "quality_dpi": (N, "Page preview quality in dpi (default 300)"),
            "overwrite": (B, "Overwrite existing file if present (default false)"),
        },
        ["filepath"],
    ),


    "apply_appearance": (
        "apply_appearance",
        "Apply a SolidWorks appearance from the installed appearance library (.p2m files: chrome, aluminum, brushed steel, "
        "plastics, rubber, glass, wood, paint...) to the whole part/assembly, to some faces (points) or to assembly "
        "components. `appearance` is a file name or part of its library path (e.g. 'matte chrome', 'high gloss/red', "
        "'brushed aluminum'); if several match, the tool lists them. The result is read back from the model. For a plain "
        "colour use set_appearance.",
        {
            "appearance": (S, "Appearance name or library path fragment (English file names), or a full path to a .p2m file"),
            "face_points": (A, "Optional points [[x, y, z], ...] on the faces to paint, model mm (`unit`)"),
            "components": (A, "Optional assembly component names (e.g. ['bracket-1'])"),
            "unit": UNIT,
        },
        ["appearance"],
    ),
}

OVERWRITE = {
    "export_equations_to_file": "filepath",
    "export_dxf_flat_pattern": "filepath",
    "export_ifc": "filepath",
    "export_gltf_glb": "filepath",
    "export_3d_pdf": "filepath",
}
