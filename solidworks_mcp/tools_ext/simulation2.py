"""Lotto SIMULAZIONE 2: schemi dei tool estesi FEA (studi speciali, carichi avanzati, connettori, termica, mesh shell/beam, sonde e report) -> automation/ext_simulation2.py (Simulation2Operations)."""

from ._common import S, N, B, A, PT3

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
            "total_time_seconds": (N, "Total transient duration in seconds (default 60.0)"),
        },
        [],
    ),
    "create_drop_test_study": (
        "create_drop_test_study",
        "Create an explicit dynamic drop test impact study onto a rigid target floor.",
        {
            "study_name": (S, "Name of the drop test study (default 'Drop Test 1')"),
            "drop_height": (N, "Drop height in mm from the lowest point (default 1000.0)"),
            "gravity_plane": (S, "Plane whose normal is the gravity direction: front|top|right or plane name (default top)"),
        },
        [],
    ),
    "create_fatigue_study": (
        "create_fatigue_study",
        "Create an alternating stress fatigue life study based on S-N Wöhler material curves.",
        {
            "study_name": (S, "Name of the fatigue life study (default 'Fatigue 1')"),
            "event_cycles": (N, "Cycles count of the constant-amplitude event (default 100000)"),
            "static_study": (S, "Existing static study the fatigue event is based on (without it the study has no events)"),
        },
        [],
    ),
    "create_topology_study": (
        "create_topology_study",
        "Create a topology optimization study (needs the matching license; fails if SolidWorks refuses). The mass target is not settable via API.",
        {
            "study_name": (S, "Name of the topology optimization study (default 'Topology 1')"),
            "target_mass_percent": (N, "Desired mass target percent (NOT applied: reported for the user to set in SolidWorks)"),
        },
        [],
    ),
    "create_linear_dynamic_study": (
        "create_linear_dynamic_study",
        "Create a linear dynamic structural study for modal harmonic or random vibration response.",
        {
            "study_name": (S, "Name of the linear dynamic study (default 'Dynamic 1')"),
            "dynamic_type": (S, "harmonic | random_vibration | time_history | response_spectrum (default harmonic)"),
        },
        [],
    ),

    # 2. Vincoli, Fissaggi e Supporti
    "add_elastic_support": (
        "add_elastic_support",
        "Apply an elastic foundation support on faces (distributed stiffness, values read back from SolidWorks).",
        {
            "face_point": PT3,
            "stiffness": (N, "Normal distributed stiffness in N/mm3 (N/mm per mm2 of face)"),
            "shear_stiffness": (N, "Tangential distributed stiffness in N/mm3 (default = normal)"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["face_point", "stiffness"],
    ),
    "add_prescribed_displacement": (
        "add_prescribed_displacement",
        "Prescribed displacement. LIMIT: nonzero values are ignored by the SolidWorks Simulation API (measured), so a nonzero value returns an error; 0 creates a fixed restraint.",
        {
            "face_point": PT3,
            "displacement_mm": (N, "Displacement in mm (only 0 is supported, see description)"),
            "study_name": (S, "Study name (or active study if omitted)"),
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
        "Apply a centrifugal load (one per study) with angular velocity around an axis given by a straight edge or a cylindrical face.",
        {
            "angular_velocity_rad_s": (N, "Angular velocity in rad/s"),
            "axis_point": (A, "Point [x,y,z] mm ON a straight edge or cylindrical face that defines the axis"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["angular_velocity_rad_s", "axis_point"],
    ),
    "add_thermal_shrinkage_load": (
        "add_thermal_shrinkage_load",
        "Static study: bring the WHOLE body containing the face to zero-strain temperature + delta (thermal expansion/shrinkage).",
        {
            "face_point": PT3,
            "delta_temperature_c": (N, "Temperature change in C relative to the study zero-strain temperature"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["face_point", "delta_temperature_c"],
    ),

    # 4. Connettori Meccanici (Bulloni, Perni, Molle)
    "add_bolt_connector": (
        "add_bolt_connector",
        "Insert a bolt-with-nut connector: head and nut are concentric CIRCULAR EDGES; shank diameter and axial preload read back.",
        {
            "head_edge_point": (A, "Point [x,y,z] mm ON the circular edge under the bolt head"),
            "nut_edge_point": (A, "Point [x,y,z] mm ON the circular edge under the nut"),
            "bolt_diameter": (N, "Shank diameter in mm"),
            "preload_force_n": (N, "Axial preload in N (default 0)"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["head_edge_point", "nut_edge_point", "bolt_diameter"],
    ),
    "add_pin_connector": (
        "add_pin_connector",
        "Insert a pin connector between two coaxial cylindrical faces of different bodies/components.",
        {
            "face1_point": (A, "Point [x,y,z] mm ON the first cylindrical face"),
            "face2_point": (A, "Point [x,y,z] mm ON the second cylindrical face"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["face1_point", "face2_point"],
    ),
    "add_spring_connector": (
        "add_spring_connector",
        "Connect two parallel PLANAR faces with a spring of given TOTAL stiffness (values read back).",
        {
            "point1": (A, "Point [x,y,z] mm ON the first planar face"),
            "point2": (A, "Point [x,y,z] mm ON the second planar face"),
            "stiffness_n_mm": (N, "Total normal stiffness in N/mm"),
            "shear_stiffness_n_mm": (N, "Total tangential stiffness in N/mm (default = normal)"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["point1", "point2", "stiffness_n_mm"],
    ),
    "add_spot_weld_connector": (
        "add_spot_weld_connector",
        "Spot weld between two parallel faces; weld locations are model VERTICES.",
        {
            "face1_point": (A, "Point [x,y,z] mm ON the first face"),
            "face2_point": (A, "Point [x,y,z] mm ON the second face"),
            "location_points": (A, "Weld locations: [[x,y,z],...] mm, each ON a vertex"),
            "spot_diameter": (N, "Spot weld diameter in mm"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["face1_point", "face2_point", "location_points", "spot_diameter"],
    ),

    # 5. Condizioni Termiche (Convezione, Irraggiamento)
    "add_convection_load": (
        "add_convection_load",
        "Apply a surface film convection cooling/heating condition with film coefficient and ambient temperature.",
        {
            "face_point": PT3,
            "convection_coefficient": (N, "Film coefficient h in W/(m2 K)"),
            "ambient_temperature_c": (N, "Bulk ambient temperature in C (default 20)"),
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
            "ambient_temperature_c": (N, "Ambient temperature in C (default 20)"),
            "view_factor": (N, "View factor 0..1 (default 1)"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["face_point"],
    ),
    "add_heat_power_load": (
        "add_heat_power_load",
        "Apply a thermal heat source power load in Watts on solid bodies or surfaces.",
        {
            "face_point": PT3,
            "heat_power_w": (N, "Total heat power in W"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["face_point", "heat_power_w"],
    ),

    # 6. Contatti tra Corpi e Giunzioni
    "add_shrink_fit_contact": (
        "add_shrink_fit_contact",
        "Shrink-fit contact between a hub hole and a shaft (cylindrical faces); the interference comes from the GEOMETRY and is reported.",
        {
            "face_hub_point": (A, "Point [x,y,z] mm ON the hub (hole) cylindrical face"),
            "face_shaft_point": (A, "Point [x,y,z] mm ON the shaft cylindrical face"),
            "friction_coefficient": (N, "Friction coefficient ratio (optional)"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["face_hub_point", "face_shaft_point"],
    ),
    "add_virtual_wall_contact": (
        "add_virtual_wall_contact",
        "Apply a virtual wall boundary condition to simulate planar floor/wall contact without modeling the fixture.",
        {
            "face_point": PT3,
            "wall_plane": (S, "Wall plane: front|top|right or a reference plane name"),
            "friction_coefficient": (N, "Friction coefficient ratio (optional; reported if SolidWorks does not accept it)"),
            "rigid_wall": (B, "Rigid wall (default true) or flexible"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["face_point", "wall_plane"],
    ),

    # 7. Materiali e Proprietà di Calcolo
    "set_orthotropic_material": (
        "set_orthotropic_material",
        "Assign an orthotropic or composite material with direction-dependent stiffness moduli Ex, Ey, Ez.",
        {
            "body_name": (S, "Part of the simulation body name (default first body)"),
            "ex_mpa": (N, "Young modulus Ex in MPa"),
            "ey_mpa": (N, "Young modulus Ey in MPa"),
            "ez_mpa": (N, "Young modulus Ez in MPa"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["ex_mpa", "ey_mpa", "ez_mpa"],
    ),

    # 8. Mesh Solida, Shell e Beam (1D/2D/3D)
    "define_shell_mesh": (
        "define_shell_mesh",
        "Define a shell (thickness in mm) on faces of a surface/sheet body. SolidWorks refuses faces of a solid body: reported as error.",
        {
            "face_point": PT3,
            "thickness": (N, "Shell thickness in mm"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["face_point", "thickness"],
    ),
    "define_beam_mesh": (
        "define_beam_mesh",
        "Treat a body as a 1D beam (checked through the study beam count).",
        {
            "body_name": (S, "Part of the simulation body name (default first body)"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        [],
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
            "solver_type": (S, "automatic | FFEPlus | DirectSparse | IntelDirectSparse (default FFEPlus); static studies only"),
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
        "Reaction force (Fx, Fy, Fz, resultant in N) on the nodes of the given restrained faces of a solved static study.",
        {
            "face_point": (A, "Point [x,y,z] mm ON a restrained face, or a list of points"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["face_point"],
    ),
    "probe_simulation_results": (
        "probe_simulation_results",
        "Von Mises stress (MPa) and displacements UX/UY/UZ/URES (mm) at the mesh node nearest to (x, y, z) of a solved static study.",
        {
            "x": (N, "X in mm"),
            "y": (N, "Y in mm"),
            "z": (N, "Z in mm"),
            "study_name": (S, "Study name (or active study if omitted)"),
        },
        ["x", "y", "z"],
    ),
    "export_simulation_report": (
        "export_simulation_report",
        "Write an HTML report of the study with data read from SolidWorks (type, loads, mesh, results if solved).",
        {
            "filepath": (S, "Destination .html file path"),
            "study_name": (S, "Study name (or active study if omitted)"),
            "overwrite": (B, "Overwrite existing report if present (default false)"),
        },
        ["filepath"],
    ),
}

OVERWRITE = {
    "export_simulation_report": "filepath",
}
