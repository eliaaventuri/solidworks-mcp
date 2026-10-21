"""
Drawing (messe in tavola) tool definitions for the MCP server.
Each entry: name -> (automation method, description, {param: (json type, description)}, [required]).
Arguments are passed by name to the method of SolidWorksAutomation (DrawingOperations mixin).
"""

from mcp.types import Tool

S, N, B, A, O = "string", "number", "boolean", "array", "object"
_VIEW = (S, "View name (partial ok, see list_drawing_views) or index; default first model view")
_UNIT = (S, "Unit of distances, default mm")
_SCALE = (S, "Scale: number (0.5 = 1:2) or 'A:B' text; empty = automatic")

_TOOLS = {
    "create_drawing": ("create_drawing",
        "Create a drawing from a part/assembly (model path, or the active saved document): paper A4..A0, orientation, "
        "first/third-angle projection, scale, template, ISO title block. "
        'Example: {"model_path":"C:/p/part.SLDPRT","paper_size":"A3","add_views":true,"save_as":"C:/p/part.SLDDRW"}.',
        {"model_path": (S, "Model .SLDPRT/.SLDASM path (empty = active saved document)"),
         "paper_size": (S, "A4, A3 (default), A2, A1, A0, or 'auto' (add_standard_views picks sheet and scale)"),
         "orientation": (S, "landscape | portrait"),
         "projection": (S, "first (first-angle, default) | third"),
         "scale": _SCALE, "template": (S, "Path of a .drwdot template (default: SolidWorks default)"),
         "sheet_format": (S, "iso (default) | din | none | path of a .slddrt sheet format"),
         "add_views": (B, "Insert front, top, right and isometric views at once"),
         "save_as": (S, "Save at once under this path (file name becomes the drawing number)"),
         "save_model": (B, "Save the model after adding title-block properties (default true)")}, []),
    "add_standard_views": ("add_standard_views",
        "Add standard views with automatic placement and scale. "
        "views: front, top, bottom, left, right, back, isometric, dimetric, trimetric. "
        'Example: {"views":["front","top","right","isometric"],"scale":"1:2"}.',
        {"views": (A, "Views to add (default front, top, right, isometric)"), "scale": _SCALE,
         "model_path": (S, "Model path (default: that of the existing views)"),
         "x_gap": (N, "Gap between views in mm; default: automatic"), "unit": _UNIT,
         "exploded": (B, "Show the exploded state in pictorial views (needs an exploded view saved in the assembly)")}, []),
    "add_model_view": ("add_model_view",
        "Add one view with the given orientation at sheet position x,y.",
        {"orientation": (S, "front, top, bottom, left, right, back, isometric, dimetric, trimetric, or a model view name"),
         "x": (N, "View center X on the sheet in mm; omit x or y = nearest free spot"),
         "y": (N, "View center Y on the sheet in mm"),
         "scale": _SCALE, "model_path": (S, "Model path (default: that of the existing views)"), "unit": _UNIT,
         "exploded": (B, "Show the assembly exploded (needs an exploded view saved in the assembly)"),
         "new_sheet_if_full": (B, "Default true: if the sheet is full, use a new sheet (same format and scale)")}, ["orientation"]),
    "add_projected_view": ("add_projected_view",
        "Add a projected view from a parent view: up, down, left, right, up_left, up_right, down_left, down_right.",
        {"parent_view": _VIEW, "direction": (S, "up | down | left | right | up_left | up_right | down_left | down_right"),
         "distance": (N, "Distance from the parent view in mm; default automatic"), "unit": _UNIT},
        ["direction"]),
    "add_section_view": ("add_section_view",
        "Add a section view from a parent view: horizontal/vertical cut line (offset from the view center), line through two points, "
        "or polyline for stepped/aligned sections. "
        'Example: {"parent_view":"Drawing View1","orientation":"vertical","offset":0,"label":"A"}.',
        {"parent_view": _VIEW, "orientation": (S, "horizontal | vertical | points | stepped | aligned"),
         "offset": (N, "Cut line distance from the view center in mm, model scale; 0 = through the center"),
         "points": (A, "Coordinates in mm from the view center: [x1,y1,x2,y2] for 'points'; polyline [x1,y1,x2,y2,x3,y3,...] for stepped/aligned"),
         "label": (S, "Label (A, B, ...)"), "flip": (B, "Reverse the viewing direction"),
         "view_x": (N, "Result view X in mm on the sheet; default automatic"),
         "view_y": (N, "Result view Y in mm on the sheet; default automatic"), "unit": _UNIT}, []),
    "add_detail_view": ("add_detail_view",
        "Add a detail view from a circle on the parent view (center relative to its center, radius), with label and scale.",
        {"parent_view": _VIEW, "center_x": (N, "Circle center X in mm from the parent view center, model scale"),
         "center_y": (N, "Circle center Y in mm from the parent view center, model scale"),
         "radius": (N, "Circle radius in mm, model scale"), "label": (S, "Detail label (B, C, ...)"), "scale": _SCALE,
         "view_x": (N, "Detail view X in mm on the sheet; default automatic"),
         "view_y": (N, "Detail view Y in mm on the sheet; default automatic"), "unit": _UNIT}, []),
    "add_broken_out_section": ("add_broken_out_section",
        "Add a broken-out section: a rectangle (relative to the view center) cut to a depth.",
        {"parent_view": _VIEW, "x1": (N, "Corner 1 X in mm from the view center"),
         "y1": (N, "Corner 1 Y in mm from the view center"),
         "x2": (N, "Corner 2 X in mm from the view center"),
         "y2": (N, "Corner 2 Y in mm from the view center"),
         "depth": (N, "Cut depth in mm from the view front face"), "unit": _UNIT}, []),
    "add_break_view": ("add_break_view",
        "Add a break view: two break lines (offsets from the view center) remove the part between them.",
        {"parent_view": _VIEW, "orientation": (S, "vertical (shortens the width) | horizontal (shortens the height)"),
         "position1": (N, "First break line, offset in mm from the view center"),
         "position2": (N, "Second break line, offset in mm from the view center"),
         "style": (N, "Break style index: 0 straight, 1-2 zig-zag, 3 freehand curve (ISO, default)"), "unit": _UNIT}, []),
    "add_auxiliary_view": ("add_auxiliary_view",
        "Add an auxiliary view perpendicular to a straight edge of the parent view (point on it, sheet coordinates).",
        {"parent_view": _VIEW, "edge_x": (N, "Sheet X in mm of a point on the edge"),
         "edge_y": (N, "Sheet Y in mm of a point on the edge"),
         "view_x": (N, "New view X in mm on the sheet (projected on the perpendicular to the edge)"),
         "view_y": (N, "New view Y in mm on the sheet (projected on the perpendicular to the edge)"),
         "flip": (B, "Reverse the viewing direction"), "label": (S, "View label letter"), "unit": _UNIT},
        ["edge_x", "edge_y"]),
    "add_crop_view": ("add_crop_view",
        "Crop a view with a closed profile: circle, rectangle (center, width x height) or polygon. "
        "Coordinates are relative to the view center, in unscaled model mm.",
        {"parent_view": _VIEW, "center_x": (N, "Center X in mm from the view center"),
         "center_y": (N, "Center Y in mm from the view center"),
         "radius": (N, "Radius in mm for circle"), "unit": _UNIT,
         "shape": (S, "circle (default) | rectangle | polygon"), "width": (N, "Width in mm for rectangle"),
         "height": (N, "Height in mm for rectangle"),
         "points": (A, "Vertices in mm from the view center: [x1,y1,x2,y2,x3,y3,...] (at least 3 points)")}, []),
    "insert_model_dimensions": ("insert_model_dimensions",
        "Import model dimensions into a view or all views.",
        {"view": _VIEW, "all_views": (B, "If true, import into all views"),
         "include_hidden_feature_dims": (B, "Also import dimensions of hidden features"),
         "arrange": (B, "Tidy per ISO 129 after import (default true): drop duplicates and chamfer dims, radial to diameter dims on shafts, add overall and hole sizes, stack at constant pitch")}, []),
    "arrange_drawing_dimensions": ("arrange_drawing_dimensions",
        "Tidy the active sheet dimensions per ISO 129: remove duplicates and chamfer dimensions (-> note), replace shaft radii with linear diameters, "
        "add missing overall and hole diameters, stack dimensions (shortest nearest the outline).",
        {"view": _VIEW, "pitch": (N, "Spacing between dimension rows in mm (default 8)"),
         "first_offset": (N, "Distance of the first dimension row from the outline in mm (default 10)"),
         "cleanup": (B, "Remove duplicates and chamfer dimensions (default true)"), "unit": _UNIT}, []),
    "get_drawing_layout": ("get_drawing_layout",
        "Geometric inventory of the active sheet (mm): sheet, title block, views and annotations with bounding boxes; dimensions with "
        "view, axis, side, distance from outline and row. Use it to check overlaps.", {}, []),
    "set_dimension_tolerance": ("set_dimension_tolerance",
        "Set tolerance and precision of a dimension: symmetric, bilateral, limit, min/max, ISO fits (H7/g6). "
        'Example: {"dimension":"D1@Sketch1@part.Part","tolerance_type":"fit","hole_fit":"H7","shaft_fit":"g6"}.',
        {"dimension": (S, "Dimension name (D1@Sketch1@part.Part) or displayed text/value (e.g. 30.00)"),
         "tolerance_type": (S, "none | basic | bilateral | limit | symmetric | min | max | fit | fit_with_tol | fit_tol_only"),
         "upper": (N, "Upper deviation in document units (symmetric: +-)"),
         "lower": (N, "Lower deviation in document units (positive = below)"),
         "hole_fit": (S, "Hole fit class, e.g. H7"), "shaft_fit": (S, "Shaft fit class, e.g. g6"),
         "precision": (N, "Decimal places of the dimension (count, 0..8)"), "tol_precision": (N, "Decimal places of the tolerance (count)"),
         "view": _VIEW, "unit": _UNIT,
         "apply_to_model": (B, "Default false: tolerance only on the drawing (an imported dimension becomes a reference dimension). true = also write it to the model dimension")},
        ["dimension"]),
    "add_hole_table": ("add_hole_table",
        "Add a hole table for a view (TAG, X, Y from the model origin, diameter) with labels A1, A2... on the holes.",
        {"view": _VIEW, "x": (N, "Table top-left X in mm on the sheet; omit = free area"),
         "y": (N, "Table top-left Y in mm on the sheet"),
         "tags": (B, "Label the holes on the view (default true)"), "unit": _UNIT}, []),
    "add_general_roughness": ("add_general_roughness",
        "Add the general roughness note (ISO 1302): 'Ra 6.3 ( symbol )', default at the top right.",
        {"value": (S, "Ra value in um, e.g. 6.3"),
         "x": (N, "Symbol tip X in mm on the sheet; omit = top right"),
         "y": (N, "Symbol tip Y in mm on the sheet"), "unit": _UNIT}, []),
    "auto_dimension": ("auto_dimension",
        "Automatically dimension an orthographic view (not isometric): removes duplicates and tidies.",
        {"view": _VIEW, "scheme": (S, "baseline | chain | ordinate"),
         "horizontal_placement": (S, "above | below"), "vertical_placement": (S, "right | left"),
         "tidy": (B, "Move the dimensions outside the view outline (default true)")}, []),
    "list_drawing_dimensions": ("list_drawing_dimensions",
        "List the dimensions of the active sheet (value, type, position, hole callout, duplicates, isometric-view dimensions).", {}, []),
    "add_center_marks": ("add_center_marks",
        "Add center marks/axes to the circles of a view (mode=auto), or an axis between two edges (mode=centerline, edge1/edge2 = sheet points).",
        {"view": _VIEW, "mode": (S, "auto | centerline"),
         "edge1": (A, "[x,y] sheet point in mm on the first edge"),
         "edge2": (A, "[x,y] sheet point in mm on the second edge"), "unit": _UNIT}, []),
    "add_note": ("add_note",
        "Add a text note to the sheet.",
        {"text": (S, "Note text"), "x": (N, "Sheet X in mm; default 50"),
         "y": (N, "Sheet Y in mm; default 50"),
         "height": (N, "Character height in mm (default 3.5)"), "unit": _UNIT}, ["text"]),
    "add_surface_finish": ("add_surface_finish",
        "Add a surface finish symbol (Ra in um), optionally attached to an edge.",
        {"x": (N, "Sheet X in mm; default 100"),
         "y": (N, "Sheet Y in mm; default 100"),
         "symbol": (S, "basic | machining_required (default) | no_machining"),
         "roughness": (S, "Ra value in um, e.g. 3.2"),
         "edge_x": (N, "Sheet X in mm of a point on the edge to attach to"),
         "edge_y": (N, "Sheet Y in mm of a point on the edge to attach to"),
         "unit": _UNIT}, []),
    "add_datum": ("add_datum",
        "Add a datum symbol attached to an edge (sheet point or model point) or to a dimension.",
        {"label": (S, "Datum letter, e.g. A"),
         "edge_x": (N, "Sheet X in mm of a point on the edge"),
         "edge_y": (N, "Sheet Y in mm of a point on the edge"), "unit": _UNIT,
         "view": _VIEW, "model_point": (A, "Alternative to edge_x/edge_y: [x,y,z] model point in mm on an edge of the view"),
         "on_dimension": (S, "Attach the datum to a dimension (name, text or value)")}, []),
    "add_geometric_tolerance": ("add_geometric_tolerance",
        "Add a geometric tolerance frame: characteristic (flatness, straightness, circularity, cylindricity, parallelism, "
        "perpendicularity, angularity, position, concentricity, symmetry, circular_runout, total_runout, "
        "profile_line, profile_surface), value, diameter, modifier M/L/S/P, up to 3 datums, composite frames. "
        "Given an edge point, it is attached there. "
        'Example: {"characteristic":"position","tolerance":"0.1","datum_refs":["A","B"],"diameter":true,"edge_x":120,"edge_y":80}.',
        {"characteristic": (S, "Characteristic, English or Italian (e.g. flatness, cilindricita, position)"),
         "tolerance": (S, "Tolerance value in mm, e.g. 0.1"), "datum_refs": (A, "Up to 3 datum letters"),
         "diameter": (B, "Diametral tolerance zone (diameter symbol)"),
         "material_condition": (S, "M (maximum material) | L (least material) | S | P (projected zone)"),
         "edge_x": (N, "Sheet X in mm of a point on the edge to attach to"),
         "edge_y": (N, "Sheet Y in mm of a point on the edge to attach to"),
         "x": (N, "Frame X in mm on the sheet"), "y": (N, "Frame Y in mm on the sheet"),
         "extra_frames": (A, "Extra frames below the first: objects with the same keys as one frame"),
         "view": _VIEW, "model_point": (A, "Attach to a feature: [x,y,z] model point in mm on an edge of the view"),
         "on_dimension": (S, "Attach to a feature: dimension name/text/value (frame next to its text)"),
         "unit": _UNIT}, []),
    "add_hole_callout": ("add_hole_callout",
        "Add a hole callout (dimension) on a circular edge.",
        {"edge_x": (N, "Sheet X in mm of a point on the circular edge"),
         "edge_y": (N, "Sheet Y in mm of a point on the circular edge"),
         "x": (N, "Text X in mm on the sheet"), "y": (N, "Text Y in mm on the sheet"),
         "unit": _UNIT}, ["edge_x", "edge_y"]),
    "set_drawing_properties": ("set_drawing_properties",
        "Set title-block properties: title, author, drawing_number, material, revision, date, company, "
        "checked_by, checked_date, finish, weight, approved_by (or custom names). "
        'Example: {"properties":{"title":"Bracket","author":"EV","material":"AISI 304"},"target":"both"}.',
        {"properties": (O, "Name-value pairs, e.g. {\"title\":\"Bracket\"}"), "target": (S, "drawing | model | both (default)")},
        ["properties"]),
    "list_sheets": ("list_sheets", "List the sheets of the active drawing.", {}, []),
    "add_sheet": ("add_sheet", "Add a sheet and make it active.",
        {"name": (S, "Sheet name (default: automatic)"), "paper_size": (S, "A4..A0 (default A3)"),
         "orientation": (S, "landscape (default) | portrait"), "projection": (S, "first (default) | third"),
         "scale": _SCALE, "sheet_format": (S, "iso (default) | din | none")}, []),
    "activate_sheet": ("activate_sheet", "Activate a sheet by name.", {"name": (S, "Sheet name")}, ["name"]),
    "set_sheet_properties": ("set_sheet_properties", "Change scale, paper size, orientation, projection or name of a sheet.",
        {"sheet": (S, "Sheet name (default: active sheet)"), "scale": _SCALE, "paper_size": (S, "A4..A0"),
         "orientation": (S, "landscape | portrait"), "projection": (S, "first | third"), "new_name": (S, "New sheet name")}, []),
    "list_drawing_views": ("list_drawing_views",
        "List the views of the active sheet: name, type, scale, position and size (mm).", {}, []),
    "set_view_properties": ("set_view_properties",
        "Change scale, display style and tangent edges of a view.",
        {"view": _VIEW, "scale": _SCALE,
         "display_style": (S, "wireframe | hidden_visible | hidden_removed | shaded | shaded_edges"),
         "show_tangent_edges": (B, "Show (true) or hide (false) tangent edges"),
         "exploded": (B, "Show/hide the exploded state in the view")}, []),
    "move_view": ("move_view", "Move a view center to sheet x,y, or shift it by x,y if relative=true.",
        {"view": _VIEW, "x": (N, "X in mm on the sheet: new center, or shift if relative"),
         "y": (N, "Y in mm on the sheet: new center, or shift if relative"),
         "relative": (B, "If true, x,y is a shift, not a position"), "unit": _UNIT}, ["x", "y"]),
    "delete_view": ("delete_view", "Delete a view of the active drawing, with the views depending on it.",
        {"view": (S, "View name")}, ["view"]),
    "add_bom": ("add_bom", "Add a bill of materials (assembly view).",
        {"view": _VIEW, "x": (N, "Table X in mm on the sheet; omit = automatic"),
         "y": (N, "Table Y in mm on the sheet; omit = automatic"),
         "bom_type": (S, "parts_only | top_level | indented"),
         "template": (S, "Path of a .sldbomtbt template"), "unit": _UNIT}, []),
    "list_bom": ("list_bom", "Read the bill of materials: item number, part name, description, quantity.", {}, []),
    "add_balloons": ("add_balloons", "Add automatic balloons to an assembly view.",
        {"view": _VIEW, "layout": (S, "square | circular | top | bottom | left | right")}, []),
    "export_drawing": ("export_drawing", "Export the drawing as PDF, DWG, DXF, PNG or JPG.",
        {"filepath": (S, "Destination path"), "format": (S, "pdf | dwg | dxf | png | jpg (default: from the file extension)")},
        ["filepath"]),
    "save_drawing": ("save_drawing", "Save the active drawing as a .SLDDRW file under `filepath` (required; to save in place "
                     "pass the current path, or use save_document without filepath).",
        {"filepath": (S, "Destination path")}, ["filepath"]),
    "audit_drawing": ("audit_drawing",
        "Perform a comprehensive quality and standards audit of the active drawing sheet: checks title block completeness, "
        "BOM table & balloon alignment (identifies missing or unlinked balloons), dangling dimensions, and annotation boundaries.",
        {"sheet": (S, "Sheet name to audit (default: active sheet)")}, []),
}


def _schema(props, required):
    p = {}
    for k, (t, desc) in props.items():
        d = {"type": t}
        if t == A:
            d["items"] = {"type": "string"} if k in ("views", "datum_refs") else (
                {"type": "object"} if k == "extra_frames" else {"type": "number"})
        if desc:
            d["description"] = desc
        p[k] = d
    return {"type": "object", "properties": p, "required": required}


DRAWING_TOOLS = [Tool(name=n, description=d, inputSchema=_schema(p, r))
                 for n, (m, d, p, r) in _TOOLS.items()]
DRAWING_DISPATCH = {n: (m, set(p)) for n, (m, d, p, r) in _TOOLS.items()}
