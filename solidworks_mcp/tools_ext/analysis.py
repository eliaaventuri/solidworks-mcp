"""Lotto ANALISI E RIFERIMENTI: schemi dei tool -> automation/ext_analysis.py (AnalysisOperations)."""

from ._common import S, N, B, A, UNIT

TOOLS = {
    "insert_bounding_box": ("insert_bounding_box",
        "Insert a best-fit bounding box around all bodies of the part and read its three sizes (largest first) from the box "
        "sketch. Example: {\"best_fit\":true,\"include_surfaces\":false,\"unit\":\"mm\"}.",
        {"best_fit": (B, "true = best-fit box (the only mode supported); false is refused"),
         "include_surfaces": (B, "true = include surface bodies in the box (default false)"),
         "unit": UNIT},
        []),
    "insert_center_of_mass": ("insert_center_of_mass",
        "Insert the center of mass reference point of the part and report the center of mass position in `unit`. "
        "Example: {\"unit\":\"mm\"}.",
        {"unit": UNIT},
        []),
    "insert_mate_reference": ("insert_mate_reference",
        "Insert a mate reference on a face. The face is the one nearest to face_point. Example: "
        "{\"name\":\"RifTop\",\"face_point\":[10,0,15],\"type\":\"coincident\",\"alignment\":\"any\",\"unit\":\"mm\"}.",
        {"name": (S, "Name of the mate reference (text, no spaces recommended)"),
         "face_point": (A, "Point [x,y,z] (`unit`) lying ON the face to reference"),
         "type": (S, "Mate reference type: default | tangent | coincident | concentric | parallel"),
         "alignment": (S, "Alignment: any | aligned | anti_aligned | closest"),
         "unit": UNIT},
        ["name", "face_point"]),
    "draft_analysis": ("draft_analysis",
        "Numeric draft analysis (no colors): draft angle in degrees of every face against the pull direction. Positive = the wall "
        "narrows going in the pull direction; faces perpendicular to the direction report 90. Classes: positive, negative, "
        "below_min, vertical, flat, not_applicable. Examples: {\"direction\":\"z\",\"min_angle\":1.0} | "
        "{\"direction\":{\"face\":[10,0,15]}} | {\"direction\":[0,0,1]}.",
        {"direction": (None, "Pull direction: \"x\" | \"y\" | \"z\", [dx,dy,dz] (vector), or {\"face\":[x,y,z]} (planar face, point in `unit`)"),
         "min_angle": (N, "Minimum draft angle in degrees: smaller non-zero angles are classed below_min (default 1.0)"),
         "unit": UNIT},
        ["direction"]),
    "thickness_analysis": ("thickness_analysis",
        "Local wall thickness: rays are cast from sample points on the faces into the material along the inward normal; the "
        "distance to the first exit is the thickness. Reports minimum, maximum and the place of the minimum. "
        "Example: {\"samples\":400,\"unit\":\"mm\"}.",
        {"samples": (N, "Maximum number of sample points on the faces (count, 1 to 5000, default 400)"),
         "unit": UNIT},
        []),
    "section_view": ("section_view",
        "Create or remove the section view of the model (view only: the volume does not change). Example: "
        "{\"plane\":\"Front\",\"offset\":0,\"unit\":\"mm\"} or {\"remove\":true}.",
        {"plane": (S, "Front | Top | Right (any language) or the name of a plane feature"),
         "offset": (N, "Offset of the section plane from the plane, in `unit` (mm by default)"),
         "remove": (B, "true removes the section view (default false)"),
         "unit": UNIT},
        []),
    "fully_define_sketch": ("fully_define_sketch",
        "Fully define a sketch by adding automatic dimensions and relations (SolidWorks FullyDefineSketch); the status is read "
        "back and reported. Example: {\"sketch\":\"Schizzo1\",\"use_dimensions\":true,\"use_relations\":true}.",
        {"sketch": (S, "Sketch name (default: the active sketch)"),
         "use_dimensions": (B, "true = add dimensions where needed (default true)"),
         "use_relations": (B, "true = add geometric relations where needed (default true)")},
        []),
}

DESTRUCTIVE = {
}
