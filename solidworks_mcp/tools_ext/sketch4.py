"""Lotto SCHIZZO 4: strumenti sketch avanzati (ISketchManager, ISketchSpline, ISketchPath)."""

S, N, B, A, O = "string", "number", "boolean", "array", "object"
_UNIT = (S, "Length unit ('mm' | 'm' | 'in' | 'ft', default from document)")

TOOLS = {
    "sketch_offset_on_surface": (
        "sketch_offset_on_surface",
        "Create a geodesic or Euclidean 3D offset curve directly on a curved model face from selected edges.",
        {
            "distance": (N, "Offset distance in `unit` (default 5.0 mm)"),
            "reverse": (B, "true = reverse offset direction along face (default false)"),
            "geodesic": (B, "true = shortest distance along curved surface; false = Euclidean distance (default true)"),
            "unit": _UNIT,
        },
        [],
    ),
    "make_sketch_chain": (
        "make_sketch_chain",
        "Combine connected tangent sketch segments (lines, arcs, splines) into a continuous SketchPath object (essential for Path Mates in assemblies).",
        {
            "entities": (A, "Array of sketch segment IDs to combine into path; if omitted, combines currently selected or all active contiguous segments"),
        },
        [],
    ),
    "segment_sketch_entity": (
        "segment_sketch_entity",
        "Divide a sketch line, arc or circle into N equal parts: split it into N segments (is_segments=true) or add the N-1 inner points (a circle gets N points). Points are computed on the curve (equal arc length) and re-read from the sketch. Ellipses and splines are refused.",
        {
            "entity": (S, "Sketch segment ID to divide (or omit to use selected entity)"),
            "count": (N, "Number of equal parts, 2-1000 (default 4)"),
            "is_segments": (B, "true = split into N separate sketch segments; false = place the dividing sketch points (default false)"),
        },
        [],
    ),
    "draw_3point_arc_slot": (
        "draw_3point_arc_slot",
        "Create a curved slot passing through 3 points on its center arc (start point, end point, intermediate through-point) with specified width.",
        {
            "x1": (N, "Center arc start point X in `unit`"),
            "y1": (N, "Center arc start point Y in `unit`"),
            "x2": (N, "Center arc end point X in `unit`"),
            "y2": (N, "Center arc end point Y in `unit`"),
            "x3": (N, "Center arc intermediate pass point X in `unit`"),
            "y3": (N, "Center arc intermediate pass point Y in `unit`"),
            "width": (N, "Full slot width in `unit` (default 10.0 mm)"),
            "unit": _UNIT,
        },
        ["x1", "y1", "x2", "y2", "x3", "y3"],
    ),
    "draw_sketch_text_along_curve": (
        "draw_sketch_text_along_curve",
        "Add sketch text constrained to follow a guide curve, arc, or line profile.",
        {
            "text": (S, "Text string to place in sketch"),
            "curve_entity": (S, "ID of the sketch curve, arc, or line to follow"),
            "height": (N, "Text font height in `unit` (default 5.0 mm)"),
            "mirror_horizontal": (B, "true = mirror text horizontally (default false)"),
            "mirror_vertical": (B, "true = mirror text vertically (default false)"),
            "unit": _UNIT,
        },
        ["text"],
    ),
    "draw_equation_curve_3d": (
        "draw_equation_curve_3d",
        "Create a 3D parametric spatial curve defined by x(t), y(t), z(t) expressions over parameter t in [start, end].",
        {
            "x_expression": (S, "Parametric formula for x(t), e.g. '20*cos(t)'"),
            "y_expression": (S, "Parametric formula for y(t), e.g. '20*sin(t)'"),
            "z_expression": (S, "Parametric formula for z(t), e.g. '5*t'"),
            "start": (N, "Start parameter t value in radians or units (default 0.0)"),
            "end": (N, "End parameter t value in radians or units (default 6.28318)"),
            "samples": (N, "Number of interpolation evaluation points along curve (count, default 50)"),
            "unit": _UNIT,
        },
        ["x_expression", "y_expression", "z_expression"],
    ),
    "stretch_sketch_entities": (
        "stretch_sketch_entities",
        "Stretch and deform selected sketch entities by moving vertices from a base point by delta (dx, dy).",
        {
            "entities": (A, "Array of sketch segment IDs to stretch"),
            "base_x": (N, "Reference base point X in `unit` (default 0.0)"),
            "base_y": (N, "Reference base point Y in `unit` (default 0.0)"),
            "dx": (N, "Displacement delta X in `unit`"),
            "dy": (N, "Displacement delta Y in `unit`"),
            "unit": _UNIT,
        },
        ["dx", "dy"],
    ),
    "align_sketch_entities": (
        "align_sketch_entities",
        "Align 2D or 3D sketch geometry using 1, 2, or 3 correspondence point pairs (translates, rotates, and orients entities).",
        {
            "entities": (A, "Array of sketch segment IDs to align"),
            "source_points": (A, "List of source points [[x,y],...] or [[x,y,z],...]"),
            "target_points": (A, "List of target destination points [[x,y],...] or [[x,y,z],...]"),
            "unit": _UNIT,
        },
        ["source_points", "target_points"],
    ),
    "show_sketch_curvature": (
        "show_sketch_curvature",
        "Display and configure curvature combs on sketch splines and curves to analyze G1/G2 continuity.",
        {
            "entity": (S, "Spline or curve segment ID (default: active spline)"),
            "scale": (N, "Curvature comb visualization scale factor (scale, default 10.0)"),
            "density": (N, "Curvature comb tooth density (count, default 20)"),
            "visible": (B, "true = display combs; false = hide combs (default true)"),
        },
        [],
    ),
    "insert_sketch_picture": (
        "insert_sketch_picture",
        "Insert a raster image (PNG, JPG, BMP) onto the active sketch plane for tracing, blueprint modeling, or reverse engineering.",
        {
            "filepath": (S, "Path to image file (.png, .jpg, .bmp)"),
            "x": (N, "Bottom-left corner X in `unit` (default 0.0)"),
            "y": (N, "Bottom-left corner Y in `unit` (default 0.0)"),
            "width": (N, "Image display width in `unit` (default auto/native)"),
            "height": (N, "Image display height in `unit` (default auto/native)"),
            "angle": (N, "Rotation angle in degrees (degrees, default 0.0)"),
            "transparency": (N, "Transparency factor 0.0 (opaque) to 1.0 (transparent) (fraction, default 0.0)"),
            "unit": _UNIT,
        },
        ["filepath"],
    ),
    "insert_sketch_block_from_file": (
        "insert_sketch_block_from_file",
        "Insert an instance of a reusable 2D sketch block from an external .sldblk file into the active sketch.",
        {
            "filepath": (S, "Path to .sldblk block file"),
            "x": (N, "Insertion point X in `unit` (default 0.0)"),
            "y": (N, "Insertion point Y in `unit` (default 0.0)"),
            "scale": (N, "Block scale factor (scale, default 1.0)"),
            "angle": (N, "Rotation angle in degrees (degrees, default 0.0)"),
            "unit": _UNIT,
        },
        ["filepath"],
    ),
}

DESTRUCTIVE = {}
OVERWRITE = {}
