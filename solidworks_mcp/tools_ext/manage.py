"""Lotto ANALISI E GESTIONE: schemi dei tool -> automation/ext_manage.py (ManageOperations)."""

from ._common import S, N, A, UNIT

TOOLS = {
    "check_geometry": ("check_geometry",
        "Geometry check of the active part: solid defects per body (Check2), SolidWorks 'What's wrong' list and the error/warning "
        "code of every feature. Returns ok=true only when there are no body defects and no feature errors. "
        "Example: {}.",
        {}, []),
    "reorder_feature": ("reorder_feature",
        "Move a feature in the feature tree before/after another feature, to the end or to the top. "
        "Fails if the order does not change. Example: {\"name\":\"Boss-Extrude2\",\"target\":\"Boss-Extrude1\",\"position\":\"before\"}.",
        {"name": (S, "Feature to move (list_model_features)"),
         "target": (S, "Reference feature for position before/after (not used for end/top)"),
         "position": (S, "before (default) | after | end | top")},
        ["name"]),
    "create_feature_folder": ("create_feature_folder",
        "Group existing features into a feature tree folder (Containing) and rename it. The features stay unchanged; "
        "volume before/after is reported. Example: {\"features\":[\"Boss-Extrude1\",\"Fillet1\"],\"name\":\"Corpo\"}.",
        {"features": (A, "Names of the features to put in the folder (list_model_features)"),
         "name": (S, "Name of the folder")},
        ["features", "name"]),
    "set_appearance": ("set_appearance",
        "Set color and transparency of the part, a body, a face or a feature (MaterialPropertyValues). The value read back "
        "from SolidWorks is reported: RGB in 0..1 and transparency in 0..1 ratio. "
        "Examples: {\"target\":\"part\",\"color\":[255,0,0]} | {\"target\":\"face\",\"color\":[0,0,255],\"face_point\":[10,5,5]} | "
        "{\"target\":\"feature\",\"feature\":\"Boss-Extrude1\",\"color\":[200,200,200],\"transparency\":0.5}.",
        {"target": (S, "part | body | face | feature"),
         "color": (A, "Color [r,g,b] as 0-255 integer counts (0..255 each)"),
         "transparency": (N, "Transparency as 0..1 ratio (0 = opaque, 1 = fully transparent)"),
         "face_point": (A, "Point [x,y,z] (`unit`) lying ON the face, for target=face (list_entities kind=face)"),
         "body": (None, "Body for target=body: index (int, list_bodies) or name (string)"),
         "feature": (S, "Feature name for target=feature (list_model_features)"),
         "unit": UNIT},
        ["target", "color"]),
    "edit_sketch": ("edit_sketch",
        "Reopen an existing sketch for editing (Edit Sketch). Close it afterwards with close_sketch, then rebuild_model. "
        "Example: {\"sketch\":\"Schizzo1\"}.",
        {"sketch": (S, "Name of the existing sketch feature (list_model_features)")},
        ["sketch"]),
    "change_sketch_plane": ("change_sketch_plane",
        "Move an existing sketch onto another plane (Change Sketch Plane): the sketch is rotated, its geometry is kept. "
        "Reports the sketch plane before and after and the volume. "
        "Examples: {\"sketch\":\"Schizzo1\",\"plane\":\"Top\"} | {\"sketch\":\"Schizzo1\",\"plane\":{\"face\":[10,5,5]}}.",
        {"sketch": (S, "Name of the existing sketch feature (list_model_features)"),
         "plane": (None, "Front | Top | Right (standard planes, any language) or a plane feature name, or {\"face\":[x,y,z]} (point `unit` on the new face)"),
         "unit": UNIT},
        ["sketch", "plane"]),
}

DESTRUCTIVE = {
}
