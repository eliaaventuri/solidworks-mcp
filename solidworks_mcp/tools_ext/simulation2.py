"""Lotto SIMULAZIONE 2: schemi dei tool estesi FEA (studi speciali, carichi avanzati, connettori, termica, mesh shell/beam, sonde e report) -> automation/ext_simulation2.py (Simulation2Operations)."""

from ._common import S, N, B, UNIT, PT3, DIR

TOOLS = {
    # 1. Creazione e Gestione Studi FEA
    "create_frequency_study": (
        "create_frequency_study",
        "Create a modal frequency FEA study to calculate resonance modes and natural frequencies in Hz.",
        {
            "study_name": (S, "Name of the frequency study (default 'Frequency 1')"),
            "num_frequencies": (N, "Number of resonant natural frequencies count (default 5)"),
        },
        [],
    ),
    "create_buckling_study": (
        "create_buckling_study",
        "Create an elastic linear buckling study to calculate critical load factor multipliers.",
        {
            "study_name": (S, "Name of the buckling study (default 'Buckling 1')"),
            "num_modes": (N, "Number of buckling modes count (default 4)"),
        },
        [],
    ),
    "create_thermal_study": (
        "create_thermal_study",
        "Create a steady-state or transient thermal FEA study for temperature distribution and heat flux.",
        {
            "study_name": (S, "Name of the thermal study (default 'Thermal 1')"),
            "transient": (B, "Whether the study is transient time-dependent (default false for steady-state)"),
            "total_time_seconds": (N, "Total transient duration in seconds (`unit`) (default 60.0)"),
        },
        [],
    ),
    "create_drop_test_study": (
        "create_drop_test_study",
        "Create an explicit dynamic drop test impact study onto a rigid target floor.",
        {
            "study_name": (S, "Name of the drop test study (default 'Drop Test 1')"),
            "drop_height": (N, "Drop height in mm (`unit`) (default 1000.0)"),
        },
        [],
    ),
    "create_fatigue_study": (
        "create_fatigue_study",
        "Create an alternating stress fatigue life study based on S-N Wöhler material curves.",
        {
            "study_name": (S, "Name of the fatigue life study (default 'Fatigue 1')"),
            "event_cycles": (N, "Loading event duration cycles count (default 100000)"),
        },
        [],
    ),
    "create_topology_study": (
        "create_topology_study",
        "Create a topology optimization study to maximize stiffness while reducing target mass.",
        {
            "study_name": (S, "Name of the topology optimization study (default 'Topology 1')"),
            "target_mass_percent": (N, "Target mass reduction percent ratio (default 50.0)"),
        },
        [],
    ),
    "create_linear_dynamic_study": (
        "create_linear_dynamic_study",
        "Create a linear dynamic structural study for modal harmonic or random vibration response.",
        {
            "study_name": (S, "Name of the linear dynamic study (default 'Dynamic 1')"),
            "dynamic_type": (S, "Dynamic study type ('harmonic', 'random_vibration', 'time_history') (default 'harmonic')"),
        },
        [],
    ),

    # 2. Vincoli, Fissaggi e Supporti
    "add_elastic_support": (
        "add_elastic_support",
        "Apply an elastic foundation support on faces with specified subgrade spring stiffness.",
        {
            "face_point": PT3,
            "stiffness": (N, "Foundation subgrade spring stiffness in N/mm3 (`unit`)"),
            "study_name": (S, "Study name (or active study if omitted)"),
            "unit": UNIT,
        },
        ["face_point", "stiffness"],
    ),
    "add_prescribed_displacement": (
        "add_prescribed_displacement",
        "Apply a prescribed nonzero translation displacement or rotation on model faces.",
        {
            "face_point": PT3,
            "displacement_mm": (N, "Prescribed displacement magnitude in mm (`unit`)"),
            "direction": DIR,
            "study_name": (S, "Study name (or active study if omitted)"),
            "unit": UNIT,
        },
        ["face_point", "displacement_mm"],
    ),
    "add_cylindrical_restraint": (
        "add_cylindrical_restraint",
        "Apply cylindrical coordinate restraint with independent radial, axial, and circumferential boundary conditions.",
        {
            "cylinder_face_point": PT3,
            "radial_free": (B, "Allow free radial expansion (default false)"),
            "axial_free": (B, "Allow free axial translation (default false)"),
            "circumferential_free": (B, "Allow free circumferential rotation (default true)"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["cylinder_face_point"],
    ),

    # 3. Carichi Meccanici Esterni
    "add_centrifugal_load": (
        "add_centrifugal_load",
        "Apply a rotating body centrifugal acceleration load defined by angular velocity around an axis.",
        {
            "angular_velocity_rad_s": (N, "Rotational angular speed in rad/s (`unit`)"),
            "axis_point": PT3,
            "axis_direction": DIR,
            "study_name": (S, "Study name (or active study if omitted)"),
            "unit": UNIT,
        },
        ["angular_velocity_rad_s"],
    ),
    "add_thermal_shrinkage_load": (
        "add_thermal_shrinkage_load",
        "Apply thermal expansion or contraction strain pre-stress caused by a uniform temperature delta.",
        {
            "face_point": PT3,
            "delta_temperature_c": (N, "Temperature difference delta in C (`unit`)"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["face_point", "delta_temperature_c"],
    ),

    # 4. Connettori Meccanici (Bulloni, Perni, Molle)
    "add_bolt_connector": (
        "add_bolt_connector",
        "Insert a preloaded bolt connector fastener with thread size, torque or tensile clamping force.",
        {
            "bolt_face_point": PT3,
            "bolt_diameter": (N, "Nominal bolt thread diameter in mm (`unit`)"),
            "preload_force_n": (N, "Axial bolt preload tension force in N (`unit`)"),
            "tightening_torque_nm": (N, "Bolt tightening torque in Nm (`unit`)"),
            "study_name": (S, "Study name (or active study if omitted)"),
            "unit": UNIT,
        },
        ["bolt_face_point", "bolt_diameter"],
    ),
    "add_pin_connector": (
        "add_pin_connector",
        "Insert a cylindrical pin or dowel connector between coaxial cylindrical faces with shear capacity.",
        {
            "pin_face_point": PT3,
            "pin_diameter": (N, "Cylindrical pin diameter in mm (`unit`)"),
            "study_name": (S, "Study name (or active study if omitted)"),
            "unit": UNIT,
        },
        ["pin_face_point", "pin_diameter"],
    ),
    "add_spring_connector": (
        "add_spring_connector",
        "Connect two entities with a linear or torsional elastic spring connector with specified stiffness.",
        {
            "point1": PT3,
            "point2": PT3,
            "stiffness_n_mm": (N, "Translational spring stiffness in N/mm (`unit`)"),
            "study_name": (S, "Study name (or active study if omitted)"),
            "unit": UNIT,
        },
        ["point1", "point2", "stiffness_n_mm"],
    ),
    "add_spot_weld_connector": (
        "add_spot_weld_connector",
        "Connect overlapping sheet metal plates with a resistance spot weld nugget.",
        {
            "point": PT3,
            "spot_diameter": (N, "Resistance spot weld nugget diameter in mm (`unit`)"),
            "study_name": (S, "Study name (or active study if omitted)"),
            "unit": UNIT,
        },
        ["point", "spot_diameter"],
    ),

    # 5. Condizioni Termiche (Convezione, Irraggiamento)
    "add_convection_load": (
        "add_convection_load",
        "Apply a surface film convection cooling/heating condition with film coefficient and ambient temperature.",
        {
            "face_point": PT3,
            "convection_coefficient": (N, "Film heat transfer coefficient h in W/m2*K (`unit`)"),
            "ambient_temperature_c": (N, "Bulk ambient fluid temperature in C (`unit`)"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["face_point", "convection_coefficient"],
    ),
    "add_radiation_load": (
        "add_radiation_load",
        "Apply a surface thermal radiation condition with emissivity and surrounding ambient temperature.",
        {
            "face_point": PT3,
            "emissivity": (N, "Surface optical emissivity factor ratio between 0.0 and 1.0 (default 0.9)"),
            "ambient_temperature_c": (N, "Surrounding ambient radiation temperature in C (`unit`)"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["face_point"],
    ),
    "add_heat_power_load": (
        "add_heat_power_load",
        "Apply a thermal heat source power load in Watts on solid bodies or surfaces.",
        {
            "face_point": PT3,
            "heat_power_w": (N, "Thermal heat source power in W (`unit`)"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["face_point", "heat_power_w"],
    ),

    # 6. Contatti tra Corpi e Giunzioni
    "add_shrink_fit_contact": (
        "add_shrink_fit_contact",
        "Apply interference fit contact between shaft and hub to compute contact stresses.",
        {
            "face_hub_point": PT3,
            "face_shaft_point": PT3,
            "radial_interference_mm": (N, "Radial diametral interference fit in mm (`unit`)"),
            "friction_coefficient": (N, "Coulomb friction coefficient ratio factor (default 0.15)"),
            "study_name": (S, "Study name (or active study if omitted)"),
            "unit": UNIT,
        },
        ["face_hub_point", "face_shaft_point", "radial_interference_mm"],
    ),
    "add_virtual_wall_contact": (
        "add_virtual_wall_contact",
        "Apply a virtual wall boundary condition to simulate planar floor/wall contact without modeling the fixture.",
        {
            "face_point": PT3,
            "friction_coefficient": (N, "Contact friction factor ratio (default 0.1)"),
            "rigid_wall": (B, "Whether the virtual wall is rigid (default true)"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["face_point"],
    ),

    # 7. Materiali e Proprietà di Calcolo
    "set_orthotropic_material": (
        "set_orthotropic_material",
        "Assign an orthotropic or composite material with direction-dependent stiffness moduli Ex, Ey, Ez.",
        {
            "body_name": (S, "Name of the target body or component"),
            "ex_mpa": (N, "Young modulus Ex along primary fiber axis in MPa (`unit`)"),
            "ey_mpa": (N, "Young modulus Ey along transverse axis in MPa (`unit`)"),
            "ez_mpa": (N, "Young modulus Ez along through-thickness axis in MPa (`unit`)"),
            "study_name": (S, "Study name (or active study if omitted)"),
            "unit": UNIT,
        },
        ["ex_mpa", "ey_mpa", "ez_mpa"],
    ),

    # 8. Mesh Solida, Shell e Beam (1D/2D/3D)
    "define_shell_mesh": (
        "define_shell_mesh",
        "Convert thin planar or curved faces into 2D shell elements with specified thickness.",
        {
            "face_point": PT3,
            "thickness": (N, "Shell membrane thickness in mm (`unit`)"),
            "mid_plane": (B, "Position shell formulation on mid-surface (default true)"),
            "study_name": (S, "Study name (or active study if omitted)"),
            "unit": UNIT,
        },
        ["face_point", "thickness"],
    ),
    "define_beam_mesh": (
        "define_beam_mesh",
        "Model structural weldments or slender extrusions as 1D beam elements with cross-section properties.",
        {
            "body_name": (S, "Name of the solid body or structural member"),
            "beam_type": (S, "Beam element formulation ('beam', 'truss') (default 'beam')"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["body_name"],
    ),
    "get_mesh_quality_metrics": (
        "get_mesh_quality_metrics",
        "Check mesh element quality diagnostics (Jacobian aspect ratio, collapsed elements, % high quality).",
        {
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        [],
    ),

    # 9. Solutore ed Esecuzione
    "set_solver_options": (
        "set_solver_options",
        "Configure FEA numerical solver type (FFEPlus, Direct Sparse) and large displacement formulation.",
        {
            "solver_type": (S, "Numeric equation solver ('FFEPlus', 'DirectSparse', 'IntelDirectSparse') (default 'FFEPlus')"),
            "large_displacement": (B, "Enable geometric non-linear large displacement formulation (default false)"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        [],
    ),

    # 10. Risultati, Sonde e Report di Calcolo
    "get_mode_shapes": (
        "get_mode_shapes",
        "Extract modal resonant frequencies in Hz and mode shape deformation vectors from a frequency study.",
        {
            "mode_number": (N, "Mode number 1-based index count (default 1)"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        [],
    ),
    "get_buckling_load_factor": (
        "get_buckling_load_factor",
        "Extract the critical buckling load factor (BLF) multiplier from a buckling study.",
        {
            "mode_number": (N, "Buckling mode 1-based index count (default 1)"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        [],
    ),
    "get_thermal_results": (
        "get_thermal_results",
        "Extract minimum and maximum nodal temperatures in Celsius and resultant thermal heat flux vectors.",
        {
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        [],
    ),
    "get_reaction_forces_detail": (
        "get_reaction_forces_detail",
        "Calculate total and component reaction forces (Fx, Fy, Fz, resultant) on restrained support faces.",
        {
            "face_point": PT3,
            "study_name": (S, "Study name (or active study if omitted)"),
            "unit": UNIT,
        },
        ["face_point"],
    ),
    "probe_simulation_results": (
        "probe_simulation_results",
        "Probe local stress, displacement and strain field values at specific spatial 3D coordinates (X, Y, Z).",
        {
            "x": (N, "X coordinate location in mm (`unit`)"),
            "y": (N, "Y coordinate location in mm (`unit`)"),
            "z": (N, "Z coordinate location in mm (`unit`)"),
            "study_name": (S, "Study name (or active study if omitted)"),
            "unit": UNIT,
        },
        ["x", "y", "z"],
    ),
    "export_simulation_report": (
        "export_simulation_report",
        "Generate a formal engineering simulation calculation report in HTML or Word document format.",
        {
            "filepath": (S, "Destination summary report file path (.html or .docx)"),
            "study_name": (S, "Study name (or active study if omitted)"),
            "overwrite": (B, "Overwrite existing report if present (default false)"),
        },
        ["filepath"],
    ),
}

OVERWRITE = {
    "export_simulation_report": "filepath",
}
