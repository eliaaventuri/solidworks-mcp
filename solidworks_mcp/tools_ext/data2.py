"""Lotto DATI ED EXPORT 2: schemi dei tool estesi di gestione dati, configurazioni, export e DimXpert MBD -> automation/ext_data2.py (Data2Operations)."""

from ._common import S, N, B, A, UNIT, PT3, DIR

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

    # 2. Materiali e Database Materiali (.sldmat)
    "create_custom_material": (
        "create_custom_material",
        "Define and register a custom material with mechanical properties (density, elastic modulus, Poisson).",
        {
            "material_name": (S, "New material name"),
            "category": (S, "Material category folder (default 'Custom')"),
            "density": (N, "Mass density in kg/m3 (`unit`)"),
            "elastic_modulus": (N, "Elastic Young's modulus in MPa (`unit`)"),
            "poissons_ratio": (N, "Poisson's contraction ratio factor (default 0.3)"),
            "yield_strength": (N, "Tensile yield strength in MPa (`unit`)"),
            "unit": UNIT,
        },
        ["material_name", "density", "elastic_modulus"],
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

    # 4. Configurazioni e Tabelle di Progettazione
    "insert_design_table": (
        "insert_design_table",
        "Insert a linked Excel or native design table to drive configurations and dimensions.",
        {
            "excel_file": (S, "Optional source Excel workbook file path (.xlsx)"),
            "blank": (B, "Whether to create a blank internal design table (default true)"),
        },
        [],
    ),
    "edit_design_table": (
        "edit_design_table",
        "Update a specific parameter cell in the active design table by configuration row and column header.",
        {
            "row_index": (N, "Configuration 1-based row index count"),
            "column_name": (S, "Parameter column header name (e.g. 'D1@Sketch1')"),
            "value": (S, "New cell string or numeric value"),
        },
        ["row_index", "column_name", "value"],
    ),
    "export_design_table": (
        "export_design_table",
        "Export the active design table to an external spreadsheet file (.xlsx or .csv).",
        {
            "filepath": (S, "Destination spreadsheet file path"),
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

    # 5. Misure Geometriche e Massa
    "get_projected_area": (
        "get_projected_area",
        "Calculate the 2D projected silhouette surface area along a specified projection direction vector.",
        {
            "direction": DIR,
            "unit": UNIT,
        },
        [],
    ),
    "calculate_clearance_envelope": (
        "calculate_clearance_envelope",
        "Compute the expanded safety clearance volume bounding box around moving solid bodies.",
        {
            "body_names": (A, "List of solid body names to envelop"),
            "clearance_offset": (N, "Clearance safety offset distance in mm (`unit`)"),
            "unit": UNIT,
        },
        ["clearance_offset"],
    ),

    # 6. Esportazione Modelli 3D e CAD Neutri
    "export_step_ap242_pmi": (
        "export_step_ap242_pmi",
        "Export model to STEP AP242 with embedded 3D semantic PMI annotations and GD&T tolerances.",
        {
            "filepath": (S, "Destination STEP AP242 file path (.step, .stp)"),
            "include_pmi": (B, "Whether to include 3D semantic PMI annotations (default true)"),
            "overwrite": (B, "Overwrite existing file if present (default false)"),
        },
        ["filepath"],
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
    "export_jt": (
        "export_jt",
        "Export 3D model to lightweight high-performance JT (Jupiter Tessellation) format.",
        {
            "filepath": (S, "Destination JT file path (.jt)"),
            "tessellation_level": (N, "Tessellation mesh density level index from 1 to 5 (default 3)"),
            "overwrite": (B, "Overwrite existing file if present (default false)"),
        },
        ["filepath"],
    ),
    "export_ifc": (
        "export_ifc",
        "Export 3D geometry to Industry Foundation Classes (IFC) BIM format for architectural workflows.",
        {
            "filepath": (S, "Destination IFC file path (.ifc)"),
            "schema_version": (S, "IFC schema standard ('IFC2X3', 'IFC4') (default 'IFC4')"),
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

    # 7. Quotatura 3D MBD / DimXpert (PMI)
    "add_dimxpert_dimension": (
        "add_dimxpert_dimension",
        "Add a 3D PMI DimXpert size or distance dimension directly onto 3D solid faces without a 2D drawing.",
        {
            "face1_point": PT3,
            "face2_point": PT3,
            "dimension_type": (S, "Dimension type ('size', 'distance', 'angle') (default 'size')"),
            "tolerance_plus": (N, "Upper positive tolerance limit in mm (`unit`)"),
            "tolerance_minus": (N, "Lower negative tolerance limit in mm (`unit`)"),
            "unit": UNIT,
        },
        ["face1_point"],
    ),
    "add_dimxpert_datum": (
        "add_dimxpert_datum",
        "Define a 3D datum reference feature (e.g. Datum A, B, C) on a planar or cylindrical face.",
        {
            "face_point": PT3,
            "datum_label": (S, "Datum identification letter (e.g. 'A', 'B', 'C')"),
            "unit": UNIT,
        },
        ["face_point", "datum_label"],
    ),
    "add_dimxpert_geometric_tolerance": (
        "add_dimxpert_geometric_tolerance",
        "Apply a 3D GD&T geometric tolerance frame (flatness, position, runout) directly on solid geometry.",
        {
            "face_point": PT3,
            "tolerance_type": (S, "Geometric tolerance symbol ('flatness', 'cylindricity', 'perpendicularity', 'position')"),
            "tolerance_value": (N, "Tolerance zone band value in mm (`unit`)"),
            "datum_reference": (S, "Primary datum reference letter label (e.g. 'A')"),
            "unit": UNIT,
        },
        ["face_point", "tolerance_type", "tolerance_value"],
    ),
    "auto_dimension_scheme_dimxpert": (
        "auto_dimension_scheme_dimxpert",
        "Automatically generate a full 3D DimXpert dimension and tolerance scheme across the model.",
        {
            "part_type": (S, "Part topology category ('prismatic', 'turned') (default 'prismatic')"),
            "tolerance_type": (S, "Tolerance specification standard ('geometric', 'plus_minus') (default 'geometric')"),
        },
        [],
    ),
    "list_dimxpert_annotations": (
        "list_dimxpert_annotations",
        "List all 3D DimXpert PMI dimensions, datums and geometric tolerance annotations present on the model.",
        {},
        [],
    ),

    # 8. Rendering e Acquisizione Immagini
    "set_view_background": (
        "set_view_background",
        "Configure the 3D graphics viewport background appearance (plain white, gradient, studio ambient).",
        {
            "background_type": (S, "Background style preset ('white', 'gradient', 'studio', 'viewport') (default 'white')"),
            "color_rgb": (A, "Optional RGB background color triplet [R, G, B] integers"),
        },
        [],
    ),
    "apply_appearance": (
        "apply_appearance",
        "Apply photorealistic appearance material, color and surface texture onto faces or bodies.",
        {
            "appearance_name": (S, "Appearance material style (e.g. 'polished_chrome', 'matte_plastic', 'cast_iron')"),
            "color_rgb": (A, "Color tint RGB triplet [R, G, B] integers"),
            "transparency": (N, "Optical transparency factor ratio between 0.0 and 1.0 (default 0.0)"),
        },
        [],
    ),
}

OVERWRITE = {
    "export_equations_to_file": "filepath",
    "export_design_table": "filepath",
    "export_step_ap242_pmi": "filepath",
    "export_dxf_flat_pattern": "filepath",
    "export_jt": "filepath",
    "export_ifc": "filepath",
    "export_gltf_glb": "filepath",
    "export_3d_pdf": "filepath",
}
