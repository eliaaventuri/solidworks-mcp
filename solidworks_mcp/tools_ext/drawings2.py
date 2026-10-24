"""Lotto DISEGNI 2: schemi dei tool -> automation/ext_drawings2.py (Drawings2Operations)."""

from ._common import S, N, B, A, UNIT

TOOLS = {
    "edit_sheet_format": (
        "edit_sheet_format",
        "Activate sheet format editing mode on the active drawing sheet to edit title block and border lines.",
        {},
        [],
    ),
    "exit_sheet_format": (
        "exit_sheet_format",
        "Exit sheet format editing mode and return to standard drawing sheet view editing.",
        {},
        [],
    ),
    "reload_sheet_format": (
        "reload_sheet_format",
        "Reload or update sheet format (.slddrt) to refresh border lines, logos, and title block.",
        {
            "template_path": (S, "Optional path to the replacement .slddrt sheet format file"),
        },
        [],
    ),
    "add_relative_view": (
        "add_relative_view",
        "Create a drawing view oriented by two PLANAR faces of the model: the first face looks at the viewer (front), the "
        "second faces right. Useful for parts whose main faces are not aligned with the standard planes. The orientation is "
        "checked by projecting the two face normals through the new view.",
        {
            "model_path": (S, "Model file (default: the model of the first view of the drawing)"),
            "front_face_point": (A, "Point [x, y, z] on the planar face that must face the viewer, model mm (`unit`)"),
            "right_face_point": (A, "Point [x, y, z] on the planar face that must face right (perpendicular to the first), model mm"),
            "x": (N, "View centre X on the sheet, mm (`unit`, default 100)"),
            "y": (N, "View centre Y on the sheet, mm (`unit`, default 100)"),
            "scale": (S, "Optional view scale (e.g. '1:2', '2:1')"),
            "unit": UNIT,
        },
        ["front_face_point", "right_face_point"],
    ),
    "add_predefined_view": (
        "add_predefined_view",
        "Insert a predefined model drawing view configured on the sheet template at given X and Y coordinates.",
        {
            "view_name": (S, "Name of the predefined view (default 'Front')"),
            "x": (N, "X coordinate of view center on sheet in mm (`unit`, default 100.0)"),
            "y": (N, "Y coordinate of view center on sheet in mm (`unit`, default 100.0)"),
            "orientation": (S, "Standard view orientation: 'front' (default) | 'top' | 'right' | 'isometric'"),
            "unit": UNIT,
        },
        [],
    ),
    "add_aligned_section_view": (
        "add_aligned_section_view",
        "Create an aligned section view (typical of flanges / revolved parts): the cutting line goes from point 1 to the "
        "vertex (point 2, usually on the axis) and then to point 3 along an INCLINED leg, which SolidWorks rotates into the "
        "cutting plane (the section shows the true length of both legs). Points are SHEET coordinates in mm (see "
        "list_drawing_views for the parent view position); same as add_section_view(orientation='aligned') with points "
        "relative to the view centre.",
        {
            "x1": (N, "Start point X on the sheet, mm (`unit`), outside the part"),
            "y1": (N, "Start point Y on the sheet, mm"),
            "x2": (N, "Vertex X on the sheet, mm (usually the axis of the part)"),
            "y2": (N, "Vertex Y on the sheet, mm"),
            "x3": (N, "End point X on the sheet, mm, outside the part on the inclined leg"),
            "y3": (N, "End point Y on the sheet, mm"),
            "view_x": (N, "Section view position X on the sheet, mm (default: first free place aligned with the parent)"),
            "view_y": (N, "Section view position Y on the sheet, mm"),
            "parent_view": (S, "Parent drawing view (default: first view)"),
            "label": (S, "Section label (default 'A')"),
            "unit": UNIT,
        },
        ["x1", "y1", "x2", "y2", "x3", "y3"],
    ),
    "add_half_section_view": (
        "add_half_section_view",
        "Create a half-section view showing one quadrant/half in external view and the other in cross-section.",
        {
            "center_x": (N, "X coordinate of pivot center on drawing sheet in mm (`unit`)"),
            "center_y": (N, "Y coordinate of pivot center on drawing sheet in mm (`unit`)"),
            "direction": (S, "Cut quadrant direction: 'right' (default) | 'left' | 'top' | 'bottom'"),
            "view_x": (N, "X placement coordinate of section view in mm (`unit`, default 200.0)"),
            "view_y": (N, "Y placement coordinate of section view in mm (`unit`, default 150.0)"),
            "parent_view": (S, "Optional parent drawing view name"),
            "label": (S, "Section cut letter label (default 'A')"),
            "unit": UNIT,
        },
        ["center_x", "center_y"],
    ),
    "add_flat_pattern_drawing_view": (
        "add_flat_pattern_drawing_view",
        "Insert a flattened sheet metal flat-pattern drawing view with bend lines and bend direction callouts.",
        {
            "model_path": (S, "Optional sheet metal model path (.sldprt)"),
            "x": (N, "X placement coordinate on sheet in mm (`unit`, default 150.0)"),
            "y": (N, "Y placement coordinate on sheet in mm (`unit`, default 150.0)"),
            "scale": (S, "Optional view scale ratio (e.g. '1:1')"),
            "show_bend_lines": (B, "Show bend lines and annotations (default true)"),
            "unit": UNIT,
        },
        [],
    ),
    "add_unfolded_view": (
        "add_unfolded_view",
        "Insert an unfolded drawing view for complex formed sheet metal components.",
        {
            "model_path": (S, "Optional model path (.sldprt)"),
            "x": (N, "X placement coordinate on sheet in mm (`unit`, default 150.0)"),
            "y": (N, "Y placement coordinate on sheet in mm (`unit`, default 150.0)"),
            "unit": UNIT,
        },
        [],
    ),
    "add_alternate_position_view": (
        "add_alternate_position_view",
        "Overlay an alternate position view with phantom line style in an assembly view to show kinematic range.",
        {
            "view_name": (S, "Target drawing view name (default active view)"),
            "configuration": (S, "Assembly configuration name representing alternate kinematic position"),
        },
        [],
    ),
    "show_exploded_drawing_view": (
        "show_exploded_drawing_view",
        "Toggle exploded view display on an assembly drawing view with optional explosion routing lines.",
        {
            "view_name": (S, "Target drawing view name (default active view)"),
            "exploded": (B, "True to show exploded state, False for collapsed (default true)"),
            "show_lines": (B, "Display 3D explode sketch routing lines (default true)"),
        },
        [],
    ),
    "rotate_drawing_view": (
        "rotate_drawing_view",
        "Rotate orientation of a drawing view on the sheet by angle in degrees (deg).",
        {
            "view_name": (S, "Drawing view name to rotate (e.g. 'Drawing View1')"),
            "angle_deg": (N, "Rotation angle in degrees (deg, default 90.0)"),
        },
        ["view_name"],
    ),
    "align_drawing_views": (
        "align_drawing_views",
        "Align two independent drawing views horizontally or vertically on the sheet.",
        {
            "view_to_align": (S, "Name of drawing view to move and align"),
            "base_view": (S, "Name of reference base drawing view"),
            "alignment": (S, "Alignment direction: 'horizontal' (default) | 'vertical'"),
        },
        ["view_to_align", "base_view"],
    ),
    "add_ordinate_dimension": (
        "add_ordinate_dimension",
        "Create a chain of ordinate dimensions in a drawing view: the first edge is the 0 datum, every other edge gets its "
        "distance from it (read back from SolidWorks). Points pick EDGES of the view: [x, y, z] = a point on the edge in MODEL "
        "coordinates (mm, projected through the view), or [x, y] = a point on the SHEET (mm). For 'horizontal' pick edges that "
        "look vertical in the view, for 'vertical' edges that look horizontal.",
        {
            "origin_point": (A, "Point on the datum edge: [x, y, z] model mm or [x, y] sheet mm (`unit`)"),
            "dimension_points": (A, "Points on the edges to dimension: [[x, y, z], ...] model mm or [[x, y], ...] sheet mm"),
            "view_name": (S, "Drawing view (default: the first view of the sheet)"),
            "direction": (S, "'horizontal' (default) | 'vertical'"),
            "offset": (N, "Distance of the dimension line from the datum point on the sheet, mm (default 15)"),
            "unit": UNIT,
        },
        ["origin_point", "dimension_points"],
    ),
    "add_chamfer_dimension": (
        "add_chamfer_dimension",
        "Add a chamfer dimension (e.g. '5,00 X 45°') in a drawing view: it needs the chamfer edge and an adjacent edge as "
        "reference. Points: [x, y, z] model mm (projected through the view) or [x, y] sheet mm. Returns the text read back.",
        {
            "point_on_chamfer": (A, "Point on the chamfer edge: [x, y, z] model mm or [x, y] sheet mm (`unit`)"),
            "reference_point": (A, "Point on the adjacent edge the chamfer is measured from (same formats)"),
            "view_name": (S, "Drawing view (default: the first view of the sheet)"),
            "x": (N, "Text position X on the sheet, mm (default: 15 mm up-right of the chamfer)"),
            "y": (N, "Text position Y on the sheet, mm"),
            "unit": UNIT,
        },
        ["point_on_chamfer", "reference_point"],
    ),
    "hide_show_dimension": (
        "hide_show_dimension",
        "Hide or show a dimension of the drawing without deleting it (hidden dimensions are not listed by "
        "list_drawing_dimensions; this tool finds them anyway). The visibility is read back.",
        {
            "dimension_name": (S, "Dimension name as listed by list_drawing_dimensions (e.g. 'RD1', 'D1@Sketch1' or the full name)"),
            "visible": (B, "True to show, False to hide (default true)"),
            "view_name": (S, "Drawing view to search (default: all views of the sheet)"),
        },
        ["dimension_name"],
    ),
    "add_weld_symbol": (
        "add_weld_symbol",
        "Add an ISO/AWS welding symbol annotation on a drawing view with weld size in mm and length.",
        {
            "point": (A, "2D placement point [x, y] on drawing sheet in mm (`unit`)"),
            "weld_type": (S, "Type of weld: 'fillet' (default) | 'bevel' | 'v-groove' | 'square' | 'plug'"),
            "size": (N, "Weld leg/throat size in mm (`unit`, default 5.0)"),
            "length": (N, "Optional continuous or intermittent weld segment length in mm (`unit`)"),
            "intermittent": (B, "True for intermittent stitch weld (default false)"),
            "view_name": (S, "Optional drawing view name"),
            "unit": UNIT,
        },
        ["point"],
    ),
    "add_edge_chamfer_symbol": (
        "add_edge_chamfer_symbol",
        "Add an ISO 13715 edge symbol defining burr or undercut condition on a sheet edge.",
        {
            "point": (A, "2D placement point [x, y] on drawing sheet in mm (`unit`)"),
            "symbol_type": (S, "Condition: 'undercut' (default) | 'burr' | 'sharp'"),
            "min_size": (N, "Minimum edge deviation value in mm (`unit`, default 0.1)"),
            "max_size": (N, "Maximum edge deviation value in mm (`unit`, default 0.3)"),
            "view_name": (S, "Optional drawing view name"),
            "unit": UNIT,
        },
        ["point"],
    ),
    "add_revision_table": (
        "add_revision_table",
        "Insert an ISO revision table annotation recording revision letter, description, date and author.",
        {
            "x": (N, "X placement coordinate on sheet in mm (`unit`, default 400.0)"),
            "y": (N, "Y placement coordinate on sheet in mm (`unit`, default 280.0)"),
            "revision": (S, "Revision letter or index code (default 'A')"),
            "description": (S, "Modification description (default 'Initial Release')"),
            "author": (S, "Author name or initials (optional)"),
            "unit": UNIT,
        },
        [],
    ),
    "add_weldment_cut_list_table": (
        "add_weldment_cut_list_table",
        "Insert a weldment cut list table on drawing sheet detailing structural member lengths, angles and quantities.",
        {
            "view_name": (S, "Name of drawing view containing the weldment part"),
            "x": (N, "X placement coordinate on sheet in mm (`unit`, default 50.0)"),
            "y": (N, "Y placement coordinate on sheet in mm (`unit`, default 250.0)"),
            "unit": UNIT,
        },
        [],
    ),
    "add_general_table": (
        "add_general_table",
        "Insert a general grid table annotation with custom row count, column count, and cell text data.",
        {
            "rows": (N, "Total count of table rows (number, default 3)"),
            "columns": (N, "Total count of table columns (number, default 3)"),
            "x": (N, "X placement coordinate on sheet in mm (`unit`, default 100.0)"),
            "y": (N, "Y placement coordinate on sheet in mm (`unit`, default 100.0)"),
            "data": (A, "Optional matrix array of strings [[cell, ...], ...] for table contents"),
            "title": (S, "Optional header table title"),
            "unit": UNIT,
        },
        [],
    ),
    "add_centerlines": (
        "add_centerlines",
        "Automatically insert longitudinal centerline axes on all cylindrical holes and revolved features in a view.",
        {
            "view_name": (S, "Drawing view name (default active view)"),
        },
        [],
    ),
    "create_drawing_layer": (
        "create_drawing_layer",
        "Create a CAD drawing layer specifying name, RGB color array, line style, and line thickness weight in mm.",
        {
            "layer_name": (S, "Name of the new drawing layer (e.g. 'Annotations', 'Dimensions')"),
            "color_rgb": (A, "Optional RGB color array [r, g, b] as integer counts 0..255"),
            "line_style": (S, "Line font style: 'solid' (default) | 'dashed' | 'phantom' | 'center'"),
            "line_weight": (N, "Line thickness weight in mm (`unit`, default 0.25)"),
        },
        ["layer_name"],
    ),
    "set_entity_layer": (
        "set_entity_layer",
        "Assign a selected annotation, dimension, or drawing view onto a specific drawing layer.",
        {
            "layer_name": (S, "Destination drawing layer name"),
            "entity_name": (S, "Annotation or dimension entity name (optional, default selected)"),
            "entity_type": (S, "Entity type: 'annotation' (default) | 'dimension' | 'view'"),
        },
        ["layer_name"],
    ),
    "insert_drawing_block": (
        "insert_drawing_block",
        "Insert a 2D block instance or company seal/stamp onto the drawing sheet at position X and Y.",
        {
            "block_path": (S, "Optional path to external .sldblk block file"),
            "block_name": (S, "Name of block definition (default 'TitleBlock')"),
            "x": (N, "X placement coordinate on sheet in mm (`unit`, default 350.0)"),
            "y": (N, "Y placement coordinate on sheet in mm (`unit`, default 30.0)"),
            "scale": (N, "Scale magnification factor ratio (number, default 1.0)"),
            "angle_deg": (N, "Block rotation angle in degrees (deg, default 0.0)"),
            "unit": UNIT,
        },
        [],
    ),
    "export_pdf_layers": (
        "export_pdf_layers",
        "Export drawing sheet to high-resolution vector PDF preserving separate CAD layers for manufacturing.",
        {
            "filepath": (S, "Target destination path for .pdf file on disk"),
            "include_layers": (A, "Optional list of layer names to export (default all visible)"),
            "overwrite": (B, "Overwrite existing destination file (default false)"),
        },
        ["filepath"],
    ),
}

DESTRUCTIVE = {}

OVERWRITE = {
    "export_pdf_layers": "filepath",
}
