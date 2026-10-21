"""Lotto FEATURE 4: schemi dei tool estesi di modellazione 3D -> automation/ext_features4.py (Features4Operations)."""

from ._common import S, N, B, A, UNIT, SK, PT3, PTS3, DIR

TOOLS = {
    # 1. Estrusioni, Rivoluzioni e Tagli Solidi
    "extrude_from_surface": (
        "extrude_from_surface",
        "Create an extruded boss feature starting from a surface or offset face instead of the sketch plane.",
        {
            "depth": (N, "Extrusion depth in mm (`unit`)"),
            "sketch": SK,
            "start_surface_name": (S, "Name of the reference surface face to start extrusion from"),
            "offset_distance": (N, "Offset distance in mm (`unit`) from the starting surface"),
            "direction": DIR,
            "draft_angle": (N, "Draft angle in degrees (default 0.0)"),
            "unit": UNIT,
        },
        ["depth"],
    ),
    "intersect_solid_features": (
        "intersect_solid_features",
        "Intersect multiple solid bodies, surfaces, or planes to form combined composite volumes.",
        {
            "body_names": (A, "List of solid body or surface feature names to intersect"),
            "cap_planar_openings": (B, "Whether to cap planar surface openings (default true)"),
            "unit": UNIT,
        },
        ["body_names"],
    ),

    # 2. Loft, Sweep e Boundary Solidi
    "solid_sweep": (
        "solid_sweep",
        "Create a solid sweep boss feature by sweeping a solid tool body along a 3D path trajectory.",
        {
            "tool_body_name": (S, "Name of the solid cutter/tool body to sweep"),
            "path_sketch": (S, "Path sketch or 3D curve trajectory name"),
            "guide_sketches": (A, "Optional list of guide curve sketches"),
            "unit": UNIT,
        },
        ["tool_body_name", "path_sketch"],
    ),
    "variable_section_sweep": (
        "variable_section_sweep",
        "Create a sweep boss with variable cross-sections controlled by law curves, parameters or equations.",
        {
            "profile_sketch": (S, "Initial profile sketch name"),
            "path_sketch": (S, "Trajectory path sketch or curve name"),
            "guide_sketches": (A, "Optional list of guide curves"),
            "scale_factor": (N, "End-to-start cross section scale factor ratio (default 1.0)"),
            "twist_angle": (N, "Total twist angle along the path in degrees (default 0.0)"),
            "unit": UNIT,
        },
        ["profile_sketch", "path_sketch"],
    ),

    # 3. Raccordi, Smussi e Lavorazioni Spigoli
    "setback_fillet": (
        "setback_fillet",
        "Create a corner transition setback fillet at vertex intersections of three or more blended edges.",
        {
            "vertex_point": PT3,
            "setback_distances": (A, "List of setback transition distances in mm (`unit`) per edge"),
            "radius": (N, "Blend fillet radius in mm (`unit`)"),
            "unit": UNIT,
        },
        ["vertex_point", "radius"],
    ),
    "curvature_continuous_fillet": (
        "curvature_continuous_fillet",
        "Create a G2 curvature-continuous blend fillet on model edges to eliminate highlight breaks.",
        {
            "edge_points": PTS3,
            "radius": (N, "Fillet radius in mm (`unit`)"),
            "rho_conic": (N, "Conic parameter rho ratio between 0.05 and 0.95 (default 0.5)"),
            "unit": UNIT,
        },
        ["edge_points", "radius"],
    ),

    # 4. Forometria Avanzata e Filettature
    "stud_wizard": (
        "stud_wizard",
        "Create an external threaded stud fastener feature on a shaft or planar face (Stud Wizard).",
        {
            "face_point": PT3,
            "shaft_diameter": (N, "Stud shaft nominal diameter in mm (`unit`)"),
            "stud_length": (N, "Stud total length in mm (`unit`)"),
            "thread_length": (N, "Threaded section length in mm (`unit`)"),
            "standard": (S, "Thread standard specification (e.g. 'ISO', 'DIN', 'ANSI Metric') (default 'ISO')"),
            "size": (S, "Thread size designation (e.g. 'M8x1.25')"),
            "unit": UNIT,
        },
        ["face_point", "shaft_diameter", "stud_length"],
    ),
    "thread_lead_in": (
        "thread_lead_in",
        "Add a helical chamfer or lead-in run-in transition at the start of a threaded feature.",
        {
            "cylinder_face_point": PT3,
            "pitch": (N, "Thread pitch distance in mm (`unit`)"),
            "angle_deg": (N, "Lead-in entry chamfer angle in degrees (default 45.0)"),
            "unit": UNIT,
        },
        ["cylinder_face_point", "pitch"],
    ),

    # 5. Geometria di Riferimento e Assi
    "create_reference_curve_from_equation": (
        "create_reference_curve_from_equation",
        "Create a 3D parametric space reference curve from explicit coordinate equations X(t), Y(t), Z(t).",
        {
            "x_equation": (S, "Equation for X(t) in terms of parameter 't' (e.g. '50*cos(t)')"),
            "y_equation": (S, "Equation for Y(t) in terms of parameter 't' (e.g. '50*sin(t)')"),
            "z_equation": (S, "Equation for Z(t) in terms of parameter 't' (e.g. '10*t')"),
            "t_start": (N, "Parameter start value unit (default 0.0)"),
            "t_end": (N, "Parameter end value unit (default 1.0)"),
            "samples_count": (N, "Number of evaluation sample points count (default 50)"),
            "unit": UNIT,
        },
        ["x_equation", "y_equation", "z_equation"],
    ),

    # 6. Ripetizioni e Simmetrie 3D
    "chain_pattern": (
        "chain_pattern",
        "Pattern components or solid bodies along an open or closed chain trajectory loop.",
        {
            "chain_path_sketch": (S, "Sketch or curve name representing the chain trajectory loop"),
            "body_name": (S, "Name of the body or feature to pattern"),
            "instance_count": (N, "Number of chain pattern instances count"),
            "pitch_distance": (N, "Spacing pitch distance in mm (`unit`) between link instances"),
            "unit": UNIT,
        },
        ["chain_path_sketch", "instance_count"],
    ),
    "mirror_body_merge": (
        "mirror_body_merge",
        "Mirror solid bodies across a planar symmetry reference and automatically merge touching coplanar faces.",
        {
            "body_names": (A, "List of solid body names to mirror"),
            "mirror_plane": (S, "Name of the mirror plane or planar face"),
            "merge_bodies": (B, "Whether to automatically merge touching mirrored bodies (default true)"),
            "unit": UNIT,
        },
        ["body_names", "mirror_plane"],
    ),

    # 7. Gestione Multibody (Booleane e Tagli)
    "core_cavity_split": (
        "core_cavity_split",
        "Automatically split a raw tooling stock block into core and cavity halves.",
        {
            "block_size": PT3,
            "parting_surface_name": (S, "Name of the parting surface feature used for splitting"),
            "unit": UNIT,
        },
        ["block_size"],
    ),
    "body_replace_face": (
        "body_replace_face",
        "Replace planar or curved faces of a solid body with a complex target surface.",
        {
            "target_face_points": PTS3,
            "surface_name": (S, "Name of the target surface to replace face with"),
            "unit": UNIT,
        },
        ["target_face_points", "surface_name"],
    ),

    # 8. Modellazione di Superfici (Surfaces)
    "freeform_surface": (
        "freeform_surface",
        "Deform a target surface mesh organically using push-pull control curve points.",
        {
            "surface_face_point": PT3,
            "push_distance": (N, "Organic push-pull deformation distance in mm (`unit`)"),
            "curve_direction": DIR,
            "unit": UNIT,
        },
        ["surface_face_point", "push_distance"],
    ),
    "flatten_surface": (
        "flatten_surface",
        "Flatten a double-curvature developable or non-developable surface into a 2D planar patch.",
        {
            "surface_face_point": PT3,
            "accuracy_level": (N, "Approximation accuracy index level from 1 to 5 (default 3)"),
            "unit": UNIT,
        },
        ["surface_face_point"],
    ),
    "radiate_surface": (
        "radiate_surface",
        "Create a radiated surface extending radially outwards from selected boundary edges.",
        {
            "edge_points": PTS3,
            "radius_distance": (N, "Radiation extension distance in mm (`unit`)"),
            "direction_vector": DIR,
            "unit": UNIT,
        },
        ["edge_points", "radius_distance"],
    ),

    # 9. Lamiera (Sheet Metal)
    "cross_break": (
        "cross_break",
        "Add stiffening diagonal cross break kink lines to a flat sheet metal panel.",
        {
            "face_point": PT3,
            "depth": (N, "Cross break offset depth in mm (`unit`)"),
            "break_angle": (N, "Break kink angle in degrees (default 2.0)"),
            "unit": UNIT,
        },
        ["face_point", "depth"],
    ),
    "convert_to_sheet_metal": (
        "convert_to_sheet_metal",
        "Convert a solid body into a bent sheet metal part with automatic corner reliefs and rips.",
        {
            "thickness": (N, "Sheet metal thickness in mm (`unit`)"),
            "bend_radius": (N, "Inside bend radius in mm (`unit`)"),
            "fixed_face_point": PT3,
            "rip_edges": (A, "Optional list of edge points or names to rip"),
            "unit": UNIT,
        },
        ["thickness", "bend_radius", "fixed_face_point"],
    ),
    "vent_feature": (
        "vent_feature",
        "Create an air vent opening grid feature with boundary, ribs, spars and open area percentage.",
        {
            "boundary_sketch": (S, "Sketch containing the vent outer perimeter boundary"),
            "rib_width": (N, "Vent rib thickness width in mm (`unit`)"),
            "spar_width": (N, "Vent spar ring width in mm (`unit`)"),
            "rib_depth": (N, "Vent rib penetration depth in mm (`unit`)"),
            "unit": UNIT,
        },
        ["boundary_sketch", "rib_width"],
    ),
    "loft_bend": (
        "loft_bend",
        "Create a sheet metal transition duct (e.g. circle to rectangle) via lofted bend forming.",
        {
            "profile1_sketch": (S, "First open profile sketch name"),
            "profile2_sketch": (S, "Second open profile sketch name"),
            "thickness": (N, "Sheet metal wall thickness in mm (`unit`)"),
            "bend_count": (N, "Number of formed bend lines count per transition (default 4)"),
            "unit": UNIT,
        },
        ["profile1_sketch", "profile2_sketch", "thickness"],
    ),
    "curved_edge_flange": (
        "curved_edge_flange",
        "Create a sheet metal edge flange along a curved or non-planar boundary edge.",
        {
            "edge_point": PT3,
            "flange_length": (N, "Flange extension length in mm (`unit`)"),
            "angle_deg": (N, "Flange bend angle in degrees (default 90.0)"),
            "unit": UNIT,
        },
        ["edge_point", "flange_length"],
    ),

    # 10. Saldature e Strutture Metalliche
    "cosmetic_weld_bead": (
        "cosmetic_weld_bead",
        "Add a cosmetic lightweight weld bead annotation along intersecting faces or joints.",
        {
            "face_from_point": PT3,
            "face_to_point": PT3,
            "bead_size": (N, "Weld bead leg size in mm (`unit`)"),
            "unit": UNIT,
        },
        ["face_from_point", "face_to_point", "bead_size"],
    ),
    "update_cut_list": (
        "update_cut_list",
        "Calculate, group and update the structural cut list table for weldment structural members.",
        {
            "force_rebuild": (B, "Whether to trigger a forced rebuild before updating cut list (default true)"),
        },
        [],
    ),
    "subweldment_folder": (
        "subweldment_folder",
        "Organize and group structural members and plates into a dedicated sub-weldment folder.",
        {
            "folder_name": (S, "Name of the sub-weldment folder"),
            "member_names": (A, "List of structural member body or feature names to group"),
        },
        ["folder_name"],
    ),

    # 11. Stampi (Mold Design) e Plastica
    "insert_parting_line": (
        "insert_parting_line",
        "Generate mold parting line split contours on drafted faces along a pull direction.",
        {
            "direction_face_point": PT3,
            "draft_angle": (N, "Minimum draft angle threshold in degrees (default 1.0)"),
            "unit": UNIT,
        },
        ["direction_face_point"],
    ),
    "insert_shut_off_surfaces": (
        "insert_shut_off_surfaces",
        "Generate automatic shut-off patching surfaces for through holes in mold tooling design.",
        {
            "patch_all_openings": (B, "Whether to automatically patch all detected through openings (default true)"),
            "unit": UNIT,
        },
        [],
    ),
    "insert_parting_surface": (
        "insert_parting_surface",
        "Create an outer parting surface radiating from the parting line to separate mold halves.",
        {
            "parting_line_feature": (S, "Name of the parting line feature to radiate from"),
            "distance": (N, "Radiating parting surface distance in mm (`unit`)"),
            "unit": UNIT,
        },
        ["distance"],
    ),
    "insert_tooling_split": (
        "insert_tooling_split",
        "Perform core/cavity tooling split to cut a mold base into core and cavity blocks.",
        {
            "core_block_size": PT3,
            "cavity_block_size": PT3,
            "unit": UNIT,
        },
        ["core_block_size", "cavity_block_size"],
    ),
    "insert_lip_and_groove": (
        "insert_lip_and_groove",
        "Create interlocking male-female lip and groove mating joints on plastic housing rims.",
        {
            "edge_points": PTS3,
            "lip_depth": (N, "Lip insertion depth in mm (`unit`)"),
            "groove_width": (N, "Groove slot width in mm (`unit`)"),
            "draft_angle": (N, "Mating draft angle in degrees (default 1.0)"),
            "unit": UNIT,
        },
        ["edge_points", "lip_depth", "groove_width"],
    ),
    "insert_snap_hook": (
        "insert_snap_hook",
        "Create an injection molded plastic cantilever snap hook fastener for snap-fit assembly.",
        {
            "location_point": PT3,
            "hook_height": (N, "Snap hook total height in mm (`unit`)"),
            "beam_thickness": (N, "Cantilever beam thickness in mm (`unit`)"),
            "unit": UNIT,
        },
        ["location_point", "hook_height", "beam_thickness"],
    ),
    "insert_mounting_boss": (
        "insert_mounting_boss",
        "Create a plastic screw mounting boss tower with draft, counterbore and reinforcing ribs.",
        {
            "location_point": PT3,
            "height": (N, "Boss total height in mm (`unit`)"),
            "outer_diameter": (N, "Outer tower diameter in mm (`unit`)"),
            "inner_hole_diameter": (N, "Inner pilot hole diameter in mm (`unit`)"),
            "unit": UNIT,
        },
        ["location_point", "height", "outer_diameter", "inner_hole_diameter"],
    ),

    # 12. Analisi Geometrica e Qualità B-Rep
    "mesh_brep_converter": (
        "mesh_brep_converter",
        "Convert tessellated facet mesh bodies (STL, OBJ, 3MF) into standard solid B-Rep geometry.",
        {
            "body_name": (S, "Name of the mesh body to convert"),
            "target_type": (S, "Target B-Rep conversion type ('solid', 'surface') (default 'solid')"),
            "tolerance": (N, "Approximation deviation tolerance in mm (`unit`) (default 0.05)"),
            "unit": UNIT,
        },
        ["body_name"],
    ),
    "surface_deviation_analysis": (
        "surface_deviation_analysis",
        "Analyze geometric deviation, maximum gap and angular deviation between two faces or bodies.",
        {
            "face1_point": PT3,
            "face2_point": PT3,
            "samples_count": (N, "Number of evaluation sample points count (default 100)"),
            "unit": UNIT,
        },
        ["face1_point", "face2_point"],
    ),
}
