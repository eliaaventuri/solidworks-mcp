"""
MCP Prompts for SolidWorks
--------------------------
Predefined prompts to guide the AI model through complex CAD/CAM/CAE workflows:
- create-part: Parametric part modeling workflow
- create-drawing: 2D ISO drawing creation and dimensioning
- run-simulation: FEA analysis (static, thermal, frequency, buckling)
- create-assembly: Assembly creation, mating, and exploded views
- export-model: Model export with safety and verification
"""

from typing import List, Optional, Dict
from mcp.types import Prompt, PromptArgument, PromptMessage, TextContent, GetPromptResult

PROMPTS: List[Prompt] = [
    Prompt(
        name="create-part",
        description="Guided workflow to model a parametric 3D part with sketches, features, and material.",
        arguments=[
            PromptArgument(
                name="description",
                description="Description and dimensions of the part to model (e.g. 'Mounting flange Ø120x15 mm with 6 M8 holes on Ø90 circle')",
                required=True,
            ),
            PromptArgument(
                name="material",
                description="Material to assign (e.g. 'AISI 304', '6061-T6', 'Plain Carbon Steel')",
                required=False,
            ),
            PromptArgument(
                name="unit",
                description="Measurement unit ('mm', 'inch', 'm', 'cm', default: 'mm')",
                required=False,
            ),
        ],
    ),
    Prompt(
        name="create-drawing",
        description="Guided workflow to create an ISO drawing sheet with standard views, dimensions, and PDF export.",
        arguments=[
            PromptArgument(
                name="part_name",
                description="Title or file path of the part or assembly to document (optional if already active)",
                required=False,
            ),
            PromptArgument(
                name="sheet_format",
                description="ISO drawing sheet format ('A4', 'A3', 'A2', 'A1', 'A0', default: 'A3')",
                required=False,
            ),
            PromptArgument(
                name="export_pdf",
                description="Whether to export to PDF ('true' or 'false', default: 'true')",
                required=False,
            ),
        ],
    ),
    Prompt(
        name="run-simulation",
        description="Guided workflow to setup and run an FEA study (static, thermal, frequency, or buckling) and inspect results.",
        arguments=[
            PromptArgument(
                name="load_description",
                description="Details of boundary conditions, fixtures, and loads (e.g. 'Fixed left face, 1500 N downward force on right edge')",
                required=True,
            ),
            PromptArgument(
                name="study_type",
                description="Analysis type: 'static', 'frequency', 'buckling', or 'thermal' (default: 'static')",
                required=False,
            ),
            PromptArgument(
                name="material",
                description="Material name if not already assigned to the model",
                required=False,
            ),
        ],
    ),
    Prompt(
        name="create-assembly",
        description="Guided workflow to insert components into an assembly, apply mates, and verify degrees of freedom.",
        arguments=[
            PromptArgument(
                name="components",
                description="List or description of components to insert and how they mate together",
                required=True,
            ),
            PromptArgument(
                name="assembly_name",
                description="Name for the new assembly file (default: 'Assembly1')",
                required=False,
            ),
        ],
    ),
    Prompt(
        name="export-model",
        description="Guided workflow to export models to standard CAD formats (STEP, STL, 3MF, etc.) with integrity verification.",
        arguments=[
            PromptArgument(
                name="format",
                description="Target CAD format: 'step' (AP214), 'stl', '3mf', 'iges', 'parasolid', 'pdf3d'",
                required=True,
            ),
            PromptArgument(
                name="filepath",
                description="Destination file path for the exported model",
                required=True,
            ),
            PromptArgument(
                name="configuration",
                description="Specific configuration name to export (optional)",
                required=False,
            ),
        ],
    ),
]


def _prompt_create_part(args: Dict[str, str]) -> str:
    desc = args.get("description", "Parametric 3D part")
    mat = args.get("material")
    unit = args.get("unit", "mm")
    mat_step = f"8. Apply material '{mat}' using assign_material." if mat else "8. (Optional) Assign an appropriate material using assign_material."
    return f"""Please model the following part in SolidWorks:

Part requirements:
{desc}
Target unit: {unit}

Follow this step-by-step workflow:
1. Ensure connection to SolidWorks (connect_solidworks) and set the default unit to '{unit}' via set_units.
2. Create a new part document using create_new_part.
3. Select an appropriate standard reference plane (Front, Top, or Right) and start a sketch using create_sketch.
4. Draw the base profile geometry (draw_line, draw_rectangle, draw_circle, draw_arc, etc.).
5. Add sketch dimensions (add_sketch_dimension) and relations (add_sketch_relation) to fully define the sketch.
6. Create the base feature (extrude_boss, revolve_boss, etc.).
7. Add subsequent features as required:
   - Holes via create_hole (Hole Wizard sizes, placed by coordinates)
   - Cuts via extrude_cut or revolve_cut (sketch on a body face with create_sketch_on_face)
   - Fillets and chamfers via fillet_at_points and chamfer_at_points
   - Patterns via linear_pattern, circular_pattern or mirror_feature if repeated features exist
{mat_step}
9. Verify the result using get_part_mass_properties (volume, mass, center of mass) and get_rebuild_errors (clean rebuild).
10. Generate a preview image using export_model_image if requested.
"""


def _prompt_create_drawing(args: Dict[str, str]) -> str:
    part_name = args.get("part_name", "active model")
    fmt = args.get("sheet_format", "A3").upper()
    export_pdf = args.get("export_pdf", "true").lower() in ("true", "1", "yes")
    pdf_step = ("6. Export the finalized drawing sheet to PDF using export_drawing." if export_pdf
                else "6. Save the drawing document using save_drawing (the file path is required).")
    return f"""Please generate a complete ISO manufacturing drawing for {part_name}:

Target sheet format: ISO {fmt} (first-angle projection)

Follow this step-by-step workflow:
1. Create a new drawing document using create_drawing(paper_size='{fmt}') (the model must be saved).
2. Add the standard views with automatic placement and scale using add_standard_views (front, top, right, and isometric).
3. Insert model driving dimensions using insert_model_dimensions, then tidy them with arrange_drawing_dimensions.
4. Add section views (add_section_view) or detail views (add_detail_view) for internal or small geometry if needed.
5. Apply geometric tolerances (add_geometric_tolerance), datum references (add_datum), and surface roughness symbols (add_surface_finish) as appropriate.
{pdf_step}
7. Run audit_drawing (title block, dangling dimensions, annotations outside the sheet), export a PNG with export_drawing to check
   visually that no dimensions or labels overlap, and report the drawing status.
"""


def _prompt_run_simulation(args: Dict[str, str]) -> str:
    loads = args.get("load_description", "")
    study_type = args.get("study_type", "static").lower()
    mat = args.get("material")
    mat_step = (f"2. Ensure material '{mat}' is assigned to the model using assign_material." if mat
                else "2. Ensure the active part has a valid material assigned (check via get_part_mass_properties, assign with assign_material).")
    return f"""Please setup and execute an FEA simulation in SolidWorks Simulation:

Study type: {study_type}
Boundary conditions and loads:
{loads}

Follow this step-by-step workflow:
1. Verify the active part document and save it with save_document (a study needs a saved file).
{mat_step}
3. Create the study using create_static_study(name='{study_type.capitalize()}_Study', analysis='{study_type}')
   (analysis: static, frequency, buckling or thermal; for other study types look them up with search_tools).
4. Apply fixtures with add_restraint (faces picked by a point ON each face):
   - For fixed constraints: kind='fixed'.
   - For roller/slider, hinge or symmetry constraints: kind='roller', 'hinge' or 'symmetry'.
5. Apply external loads according to the specifications:
   - For forces: add_force
   - For pressure: add_pressure
   - For remote loads / bearing loads: add_remote_load / add_bearing_load
   - For thermal loads: add_temperature
6. For assemblies or multibody parts, define contact sets using add_simulation_contact (bonded, no-penetration, etc.).
7. Add local mesh controls on stress concentration areas (fillets, holes) using add_mesh_control, then mesh the geometry with create_simulation_mesh.
8. Run the solver using run_simulation.
9. Query and analyze results using get_simulation_results:
   - Maximum von Mises stress
   - Maximum displacement / deflection
   - Minimum Factor of Safety (FOS) and critical location
   - Reaction forces and moments
10. Generate stress and displacement plot images using export_simulation_plot.
"""


def _prompt_create_assembly(args: Dict[str, str]) -> str:
    components = args.get("components", "")
    asm_name = args.get("assembly_name", "Assembly1")
    return f"""Please create and configure the assembly '{asm_name}' in SolidWorks:

Components and assembly intent:
{components}

Follow this step-by-step workflow:
1. Create a new assembly document using create_new_assembly.
2. Insert the first base component using insert_component(fixed=true) at the origin (component files must be saved).
3. Insert subsequent components using insert_component(fixed=false), roughly near their final position.
4. Apply mating relationships using add_mate:
   - Standard mates: coincident, concentric, parallel, perpendicular, tangent, distance, angle.
   - Advanced mates: distance or angle limits (min_value / max_value), width, symmetric.
   - Mechanical mates: gear and screw (add_mate), hinge (add_hinge_mate).
5. Verify the assembly:
   - Constraint status and remaining degrees of freedom using get_assembly_status.
   - Test movement using move_component.
   - Check for interference using check_interference.
6. (Optional) Create an exploded view using create_exploded_view.
7. Save the assembly using save_document.
"""


def _prompt_export_model(args: Dict[str, str]) -> str:
    fmt = args.get("format", "step")
    filepath = args.get("filepath", "")
    cfg = args.get("configuration")
    cfg_note = f"Configuration: '{cfg}'" if cfg else "Active configuration"
    return f"""Please export the model to '{fmt.upper()}' format:

Target path: {filepath}
{cfg_note}

Follow this step-by-step workflow:
1. Verify the active model and make sure it rebuilds without errors (get_rebuild_errors).
2. If a specific configuration is requested, pass it as the configuration argument of export_model (no need to activate it first).
3. Export the file using export_model(filepath='{filepath}', format='{fmt}'{f", configuration='{cfg}'" if cfg else ""}).
4. Verify the export file integrity using inspect_export_file:
   - Check for manifold solid geometry
   - Verify file size and header compliance
   - If STEP, confirm application protocol (AP214) and body count
5. Report export verification status and output details.
"""


def get_prompt_content(name: str, arguments: Optional[Dict[str, str]] = None) -> GetPromptResult:
    args = arguments or {}
    dispatch = {
        "create-part": (_prompt_create_part, "Guided workflow to model a parametric 3D part"),
        "create-drawing": (_prompt_create_drawing, "Guided workflow to create an ISO drawing sheet"),
        "run-simulation": (_prompt_run_simulation, "Guided workflow to setup and run an FEA study"),
        "create-assembly": (_prompt_create_assembly, "Guided workflow to assemble components and apply mates"),
        "export-model": (_prompt_export_model, "Guided workflow to export models to standard CAD formats"),
    }
    if name not in dispatch:
        raise ValueError(f"Unknown prompt: {name}")

    fn, desc = dispatch[name]
    text = fn(args)
    return GetPromptResult(
        description=desc,
        messages=[
            PromptMessage(
                role="user",
                content=TextContent(type="text", text=text),
            )
        ],
    )
