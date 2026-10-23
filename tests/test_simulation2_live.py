"""
Test live del lotto SIMULAZIONE 2 (32 tool) su istanza SolidWorks dedicata e nascosta.
Ogni tool e' controllato con un NUMERO: valori riletti da SolidWorks oppure risultati dell'analisi confrontati con la
soluzione analitica (trave 200x20x10 mm in AISI 1020: E 200 GPa, alfa 1,5e-5 /K, k 47 W/mK, rho 7900 kg/m3).
I tool che SolidWorks non permette devono FALLIRE con un messaggio chiaro (mai un successo finto).
"""

import os
import sys
import math
import time
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup, EXPECTED_TOOLS

TS = int(time.time())
BEAM = OUT / f"test_sim2_trave_{TS}.SLDPRT"
CONN = OUT / f"test_sim2_piastre_{TS}.SLDPRT"
SHRK = OUT / f"test_sim2_forzato_{TS}.SLDPRT"
RPT_OUT = OUT / f"test_sim2_report_{TS}.html"

E, ALPHA, KT, RHO = 200e9, 1.5e-5, 47.0, 7900.0      # AISI 1020 (libreria SolidWorks)
L, B, H = 0.200, 0.020, 0.010                         # trave [m]: X 0..200, Y -10..10, Z -5..5 (mm)
A = B * H
I_MIN = B * H ** 3 / 12

RESULTS = []


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:220], flush=True)


def near(value, expected, rel):
    try:
        return abs(float(value) - expected) <= rel * abs(expected)
    except (TypeError, ValueError):
        return False


async def run():
    elia_pids = sw_pids()
    print(f"Istanze SolidWorks pre-esistenti (da non toccare): {sorted(elia_pids)}", flush=True)
    env = dict(os.environ)
    env["SW_MCP_INSTANCE"] = "dedicated"
    env["SW_MCP_ALLOW_PYTHON"] = "1"
    params = StdioServerParameters(command=str(PYTHON), args=[str(SERVER)], env=env, cwd=str(ROOT))
    my_pid = None
    try:
        async with stdio_client(params) as (rd, wr):
            async with ClientSession(rd, wr, read_timeout_seconds=timedelta(seconds=600)) as session:
                await session.initialize()
                c = Client(session)
                tools = [t.name for t in (await session.list_tools()).tools]
                record("tools count", len(tools) == EXPECTED_TOOLS, f"{len(tools)} tools (expected {EXPECTED_TOOLS})")
                ok, text, data = await c.call("connect_solidworks")
                my_pid = data.get("pid")
                print(f"Istanza dedicata: PID {my_pid}", flush=True)
                if not ok or not my_pid or my_pid in elia_pids:
                    record("istanza dedicata separata", False, text[:120])
                    return
                await scenario(c)
                await c.call("close_document", discard=True)
    finally:
        cleanup(my_pid, elia_pids)
        time.sleep(10)
        left = sw_pids() - elia_pids
        record("nessun processo SolidWorks orfano (10 s dopo la chiusura)", not left, f"orfani {sorted(left)}")

    passed = sum(1 for _, ok, _ in RESULTS if ok == "PASS")
    print(f"\nRisultato test live Simulazione 2: {passed}/{len(RESULTS)} PASS")
    if passed != len(RESULTS):
        sys.exit(1)


async def mesh_run(c, study):
    ok_m, txt_m, _ = await c.call("create_simulation_mesh", study=study, element_size=5.0)
    ok_r, txt_r, _ = await c.call("run_simulation", study=study)
    if not (ok_m and ok_r):
        print(f"    mesh/run {study}: {txt_m[:80]} | {txt_r[:100]}", flush=True)
    return ok_m and ok_r


async def scenario(c):
    # =============================================================== trave 200 x 20 x 10
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-10, y1=-5, x2=10, y2=5, unit="mm")
    await c.call("extrude_boss", depth=200, unit="mm")
    await c.call("assign_material", material="AISI 1020")
    ok, _, d = await c.call("get_bounding_box")
    ok_s, _, _ = await c.call("save_document", filepath=str(BEAM))
    record("trave: ingombro X 0..200, Y -10..10, Z -5..5", ok and ok_s and near(d.get("size", [0])[0], 200.0, 1e-6)
           and abs(d["min"][0]) < 1e-6 and near(d["max"][1], 10.0, 1e-6), str(d.get("size")))
    x0, x200 = [0.0, 0.0, 0.0], [200.0, 0.0, 0.0]

    # ---- 1. frequenze: f1 a sbalzo = 1.875^2/(2 pi) sqrt(E I / (rho A L^4))
    f1 = 1.875 ** 2 / (2 * math.pi) * math.sqrt(E * I_MIN / (RHO * A * L ** 4))
    ok, txt, d = await c.call("create_frequency_study", study_name="Freq_Live", num_frequencies=3)
    record("create_frequency_study: tipo 1, 3 modi riletti", ok and d.get("analysis_type") == 1 and d.get("num_frequencies") == 3, txt)
    await c.call("add_restraint", kind="fixed", faces=[x0], study="Freq_Live")
    solved = await mesh_run(c, "Freq_Live")
    ok, txt, d = await c.call("get_mode_shapes", mode_number=1, study_name="Freq_Live")
    record("get_mode_shapes: f1 = analitico +-3 %", solved and ok and near(d.get("frequency_hz"), f1, 0.03),
           f"{d.get('frequency_hz')} Hz vs {f1:.1f} Hz")
    record("get_mode_shapes: 3 modi crescenti", ok and len(d.get("all_modes", [])) == 3
           and all(d["all_modes"][i]["hz"] < d["all_modes"][i + 1]["hz"] for i in range(2)), "")
    ok, txt, d = await c.call("get_mode_shapes", mode_number=7, study_name="Freq_Live")
    record("get_mode_shapes: modo inesistente -> errore", not ok, txt[:90])
    ok, txt, d = await c.call("get_mesh_quality_metrics", study_name="Freq_Live")
    record("get_mesh_quality_metrics: nodi, elementi, aspetto >= 1", ok and d.get("nodes", 0) > 100 and d.get("elements", 0) > 50
           and d.get("max_aspect_ratio", 0) >= 1.0, txt)
    ok, txt, d = await c.call("probe_simulation_results", x=100.0, y=0.0, z=0.0, study_name="Freq_Live")
    record("probe_simulation_results su studio di frequenze -> errore", not ok, txt[:90])
    ok, txt, d = await c.call("export_simulation_report", filepath=str(RPT_OUT), study_name="Freq_Live", overwrite=True)
    body = RPT_OUT.read_text(encoding="utf-8") if RPT_OUT.exists() else ""
    record("export_simulation_report: studio, tipo, nodi e risultati letti", ok and "Freq_Live" in body and "Frequenze" in body
           and str((d.get("mesh") or {}).get("nodes", "x")) in body and "Hz" in body, txt)

    # ---- 2. buckling: Pcr = pi^2 E I / (4 L^2) con 1000 N di compressione -> BLF = Pcr/1000
    blf = math.pi ** 2 * E * I_MIN / (4 * L ** 2) / 1000.0
    ok, txt, d = await c.call("create_buckling_study", study_name="Buck_Live", num_modes=2)
    record("create_buckling_study: tipo 2, 2 modi riletti", ok and d.get("analysis_type") == 2 and d.get("num_modes") == 2, txt)
    await c.call("add_restraint", kind="fixed", faces=[x0], study="Buck_Live")
    await c.call("add_force", faces=[x200], value=1000.0, mode="direction", direction=[-1, 0, 0], study="Buck_Live")
    solved = await mesh_run(c, "Buck_Live")
    ok, txt, d = await c.call("get_buckling_load_factor", mode_number=1, study_name="Buck_Live")
    record("get_buckling_load_factor: BLF = analitico +-3 %", solved and ok and near(d.get("buckling_load_factor"), blf, 0.03),
           f"{d.get('buckling_load_factor')} vs {blf:.2f}")

    # ---- 3. termico: T fissa 120 C su X=0, convezione h=25 su X=200 (1D: R_k = L/(kA), R_h = 1/(hA))
    rk = L / (KT * A)
    t_conv = 20 + (120 - 20) * (1 / (25 * A)) / (rk + 1 / (25 * A))
    ok, txt, d = await c.call("create_thermal_study", study_name="Conv_Live", transient=False)
    record("create_thermal_study: tipo 3 stazionario", ok and d.get("analysis_type") == 3 and d.get("transient") is False, txt)
    await c.call("add_temperature", faces=[x0], value=120.0, study="Conv_Live")
    ok, txt, d = await c.call("add_convection_load", face_point=x200, convection_coefficient=25.0, ambient_temperature_c=20.0,
                              study_name="Conv_Live")
    record("add_convection_load: h e T ambiente riletti", ok and d.get("convection_coefficient") == 25.0
           and near(d.get("ambient_temperature_c"), 20.0, 1e-6), txt)
    solved = await mesh_run(c, "Conv_Live")
    ok, txt, d = await c.call("get_thermal_results", study_name="Conv_Live")
    record("convezione: T min = 1D +-0,5 C", solved and ok and abs(d.get("temperature_min_c", 0) - t_conv) < 0.5,
           f"{d.get('temperature_min_c')} vs {t_conv:.2f}")
    record("get_thermal_results: T max = 120 C imposti", ok and abs(d.get("temperature_max_c", 0) - 120.0) < 1e-3, str(d.get("temperature_max_c")))
    ok, txt, d = await c.call("add_convection_load", face_point=x200, convection_coefficient=25.0, study_name="Freq_Live")
    record("add_convection_load su studio non termico -> errore", not ok, txt[:90])

    # potenza termica: T fissa 20 C su X=0, 1 W su X=200 -> T max = 20 + P R_k
    await c.call("create_thermal_study", study_name="Pot_Live")
    await c.call("add_temperature", faces=[x0], value=20.0, study="Pot_Live")
    ok, txt, d = await c.call("add_heat_power_load", face_point=x200, heat_power_w=1.0, study_name="Pot_Live")
    record("add_heat_power_load: 1 W riletto", ok and d.get("heat_power_w") == 1.0, txt)
    solved = await mesh_run(c, "Pot_Live")
    ok, txt, d = await c.call("get_thermal_results", study_name="Pot_Live")
    record("potenza termica: T max = 20 + P L/(kA) +-0,3 C", solved and ok and abs(d.get("temperature_max_c", 0) - (20 + rk)) < 0.3,
           f"{d.get('temperature_max_c')} vs {20 + rk:.2f}")

    # irraggiamento: T fissa 120 C su X=0, eps 0.9 verso 20 C su X=200 (bilancio 1D risolto con Newton)
    t = 380.0
    for _ in range(60):
        g = (393.15 - t) / rk - 0.9 * 5.670374419e-8 * A * (t ** 4 - 293.15 ** 4)
        t -= g / (-1 / rk - 0.9 * 5.670374419e-8 * A * 4 * t ** 3)
    t_rad = t - 273.15
    await c.call("create_thermal_study", study_name="Rad_Live")
    await c.call("add_temperature", faces=[x0], value=120.0, study="Rad_Live")
    ok, txt, d = await c.call("add_radiation_load", face_point=x200, emissivity=0.9, ambient_temperature_c=20.0, study_name="Rad_Live")
    record("add_radiation_load: emissivita', T ambiente, fattore di vista riletti", ok and d.get("emissivity") == 0.9
           and near(d.get("ambient_temperature_c"), 20.0, 1e-6) and d.get("view_factor") == 1.0, txt)
    solved = await mesh_run(c, "Rad_Live")
    ok, txt, d = await c.call("get_thermal_results", study_name="Rad_Live")
    record("irraggiamento: T min = bilancio 1D +-0,3 C", solved and ok and abs(d.get("temperature_min_c", 0) - t_rad) < 0.3,
           f"{d.get('temperature_min_c')} vs {t_rad:.3f}")

    # ---- 4. statico: supporto elastico k = 1000 N/mm3 su X=0, 1000 N su X=200 -> UX(0) = F/(kA)
    await c.call("create_static_study", name="Elast_Live")
    ok, txt, d = await c.call("add_elastic_support", face_point=x0, stiffness=1000.0, study_name="Elast_Live")
    record("add_elastic_support: rigidezze rilette", ok and near(d.get("normal_stiffness_n_mm3"), 1000.0, 1e-9)
           and near(d.get("shear_stiffness_n_mm3"), 1000.0, 1e-9), txt)
    await c.call("add_force", faces=[x200], value=1000.0, mode="direction", direction=[1, 0, 0], study="Elast_Live")
    ok, txt, d = await c.call("set_solver_options", solver_type="DirectSparse", large_displacement=False, study_name="Elast_Live")
    record("set_solver_options: Direct Sparse riletto (1 o 7)", ok and d.get("solver_code") in (1, 7), txt)
    ok, txt, d = await c.call("set_solver_options", solver_type="FFEPlus", study_name="Elast_Live")
    record("set_solver_options: FFEPlus riletto (2)", ok and d.get("solver_code") == 2, txt)
    ok, txt, d = await c.call("set_solver_options", solver_type="FFEPlus", study_name="Conv_Live")
    record("set_solver_options su studio termico -> errore", not ok, txt[:90])
    solved = await mesh_run(c, "Elast_Live")
    u_spring = 1000.0 / (1000.0e9 * A) * 1000.0
    ok, txt, d = await c.call("probe_simulation_results", x=0.0, y=0.0, z=0.0, study_name="Elast_Live")
    record("supporto elastico: UX(0) = F/(kA) +-2 %", solved and ok and near(d.get("ux_mm"), u_spring, 0.02),
           f"{d.get('ux_mm')} vs {u_spring:.5f} mm")
    ok, txt, d = await c.call("probe_simulation_results", x=200.0, y=0.0, z=0.0, study_name="Elast_Live")
    u_end = u_spring + 1000.0 * L / (E * A) * 1000.0
    record("probe_simulation_results: UX(200) = F/(kA) + FL/(EA) +-2 %, nodo sul punto", ok and near(d.get("ux_mm"), u_end, 0.02)
           and d.get("distance_to_node_mm", 9) < 0.01, f"UX {d.get('ux_mm')} vs {u_end:.5f}; VM {d.get('von_mises_mpa')}")

    # ---- 5. centrifugo: 100 rad/s attorno allo spigolo X=0, Y=10 (parallelo a Z) -> R = m w^2 r
    m = RHO * A * L
    r_cg = math.hypot(0.100, 0.010)
    await c.call("create_static_study", name="Centr_Live")
    await c.call("add_restraint", kind="fixed", faces=[x0], study="Centr_Live")
    ok, txt, d = await c.call("add_centrifugal_load", angular_velocity_rad_s=100.0, axis_point=[0.0, 10.0, 0.0], study_name="Centr_Live")
    record("add_centrifugal_load: 100 rad/s riletti", ok and d.get("angular_velocity_rad_s") == 100.0, txt)
    ok2, txt2, _ = await c.call("add_centrifugal_load", angular_velocity_rad_s=50.0, axis_point=[0.0, 10.0, 0.0], study_name="Centr_Live")
    record("add_centrifugal_load: secondo carico nello stesso studio -> errore", not ok2, txt2[:90])
    solved = await mesh_run(c, "Centr_Live")
    ok, txt, d = await c.call("get_reaction_forces_detail", face_point=x0, study_name="Centr_Live")
    record("get_reaction_forces_detail: |R| = m w^2 r +-1 %", solved and ok and near(d.get("resultant_n"), m * 100.0 ** 2 * r_cg, 0.01),
           f"{d.get('resultant_n')} vs {m * 1e4 * r_cg:.2f} N")
    ok, txt, d = await c.call("get_reaction_forces_detail", face_point=x200, study_name="Centr_Live")
    record("get_reaction_forces_detail su faccia libera -> errore", not ok, txt[:90])

    # ---- 6. dilatazione termica: -40 C sul corpo, vincolo a X=0 -> UX(200) = alfa dT L
    await c.call("create_static_study", name="Shrink_Live")
    await c.call("add_restraint", kind="fixed", faces=[x0], study="Shrink_Live")
    ok, txt, d = await c.call("add_thermal_shrinkage_load", face_point=x200, delta_temperature_c=-40.0, study_name="Shrink_Live")
    record("add_thermal_shrinkage_load: delta -40 C riletto", ok and abs(d.get("delta_temperature_c", 0) + 40.0) < 1e-6, txt)
    solved = await mesh_run(c, "Shrink_Live")
    ok, txt, d = await c.call("probe_simulation_results", x=200.0, y=0.0, z=0.0, study_name="Shrink_Live")
    u_th = ALPHA * -40.0 * L * 1000.0
    record("dilatazione: UX(200) = alfa dT L +-2 %", solved and ok and near(d.get("ux_mm"), u_th, 0.02), f"{d.get('ux_mm')} vs {u_th:.4f} mm")

    # ---- 7. spostamento imposto: limite dichiarato
    ok, txt, d = await c.call("add_prescribed_displacement", face_point=x200, displacement_mm=1.5, study_name="Shrink_Live")
    record("add_prescribed_displacement non nullo -> errore dichiarato", not ok and "non realizzabile" in txt, txt[:90])

    # ---- 8. ortotropo: trazione assiale 1000 N, Ex 140 GPa -> UX = FL/(Ex A)
    await c.call("create_static_study", name="Orto_Live")
    ok, txt, d = await c.call("set_orthotropic_material", ex_mpa=140000.0, ey_mpa=11000.0, ez_mpa=11000.0, study_name="Orto_Live")
    record("set_orthotropic_material: tipo 1, Ex Ey Ez riletti", ok and d.get("model_type") == 1 and d.get("ex_mpa") == 140000.0
           and d.get("ey_mpa") == 11000.0 and d.get("ez_mpa") == 11000.0, txt)
    await c.call("add_restraint", kind="fixed", faces=[x0], study="Orto_Live")
    await c.call("add_force", faces=[x200], value=1000.0, mode="direction", direction=[1, 0, 0], study="Orto_Live")
    solved = await mesh_run(c, "Orto_Live")
    ok, txt, d = await c.call("probe_simulation_results", x=200.0, y=0.0, z=0.0, study_name="Orto_Live")
    u_or = 1000.0 * L / (140e9 * A) * 1000.0
    record("ortotropo: UX(200) = FL/(Ex A) +-3 % (assi del materiale = assi globali)", solved and ok and near(d.get("ux_mm"), u_or, 0.03),
           f"{d.get('ux_mm')} vs {u_or:.5f} mm")

    # ---- 9. shell e trave
    await c.call("create_static_study", name="Mesh_Live")
    ok, txt, d = await c.call("define_shell_mesh", face_point=[100.0, 10.0, 0.0], thickness=2.5, study_name="Mesh_Live")
    record("define_shell_mesh su faccia di un solido -> errore dichiarato (codice 2)", not ok and "codice 2" in txt, txt[:100])
    ok, txt, d = await c.call("define_beam_mesh", study_name="Mesh_Live")
    record("define_beam_mesh: travi nello studio 0 -> 1", ok and d.get("beams_before") == 0 and d.get("beams_after") == 1, txt)

    # ---- 10. altri studi
    ok, txt, d = await c.call("create_drop_test_study", study_name="Drop_Live", drop_height=1200.0)
    record("create_drop_test_study: tipo 6, altezza 1200 riletta", ok and d.get("analysis_type") == 6 and d.get("drop_height_mm") == 1200.0, txt)
    ok, txt, d = await c.call("create_fatigue_study", study_name="Fat_Live", event_cycles=75000, static_study="Elast_Live")
    record("create_fatigue_study: tipo 7, evento da 75000 cicli", ok and d.get("analysis_type") == 7 and d.get("events") == 1
           and d.get("cycles") == 75000.0, txt)
    ok, txt, d = await c.call("create_topology_study", study_name="Topo_Live", target_mass_percent=45.0)
    record("create_topology_study: tipo 13 oppure rifiuto esplicito della licenza", (ok and d.get("analysis_type") == 13)
           or (not ok and "errore 3" in txt), txt[:110])
    ok, txt, d = await c.call("create_linear_dynamic_study", study_name="Dyn_Live", dynamic_type="harmonic")
    record("create_linear_dynamic_study: tipo 8 armonico", ok and d.get("analysis_type") == 8 and d.get("subtype") == 1, txt)
    ok, txt, d = await c.call("create_linear_dynamic_study", study_name="Dyn_Bad", dynamic_type="boh")
    record("create_linear_dynamic_study: tipo sconosciuto -> errore", not ok, txt[:80])
    await c.call("save_document")
    await c.call("close_document", discard=True)

    # =============================================================== due piastre con foro (connettori)
    # A: X 0..10, B: X 15..25 (corpi separati), foro R5 a Y=20 passante
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-50, y1=-30, x2=50, y2=30, unit="mm")
    await c.call("extrude_boss", depth=10, unit="mm")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-50, y1=-30, x2=50, y2=30, unit="mm")
    await c.call("extrude_boss", depth=10, start_offset=15, merge=False, unit="mm")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=20, y=0, radius=5, unit="mm")
    await c.call("extrude_cut", end_condition="through_all_both", unit="mm")
    await c.call("assign_material", material="AISI 1020")
    ok, txt, d = await c.call("list_bodies")
    ok_s, _, _ = await c.call("save_document", filepath=str(CONN))
    record("piastre: 2 corpi salvati", ok and ok_s and len(d.get("bodies", [])) == 2, txt[:80])

    # molla 150 N/mm tra A(X=10) e B(X=15), A fissa a X=0, 100 N su B -> UX(B) = F/k
    await c.call("create_static_study", name="Molla_Live")
    await c.call("add_restraint", kind="fixed", faces=[[0.0, 0.0, 20.0]], study="Molla_Live")
    ok, txt, d = await c.call("add_spring_connector", point1=[10.0, 0.0, 20.0], point2=[15.0, 0.0, 20.0], stiffness_n_mm=150.0,
                              study_name="Molla_Live")
    record("add_spring_connector: 150 N/mm riletti", ok and d.get("stiffness_n_mm") == 150.0 and d.get("shear_stiffness_n_mm") == 150.0, txt)
    await c.call("add_force", faces=[[25.0, 0.0, 20.0]], value=100.0, mode="direction", direction=[1, 0, 0], study="Molla_Live")
    solved = await mesh_run(c, "Molla_Live")
    ok, txt, d = await c.call("probe_simulation_results", x=25.0, y=0.0, z=0.0, study_name="Molla_Live")
    record("molla: UX(B) = F/k +-3 %", solved and ok and near(d.get("ux_mm"), 100.0 / 150.0, 0.03), f"{d.get('ux_mm')} vs 0.6667 mm")

    await c.call("create_static_study", name="Conn_Live")
    ok, txt, d = await c.call("add_cylindrical_restraint", cylinder_face_point=[5.0, 20.0, 5.0], radial_free=False, axial_free=True,
                              circumferential_free=True, study_name="Conn_Live")
    record("add_cylindrical_restraint: flag riletti (radiale bloccato, assiale e circonferenziale liberi)", ok and d.get("radial_fixed") is True
           and d.get("axial_fixed") is False and d.get("circumferential_fixed") is False and d.get("restraint_type") == 7, txt)
    ok, txt, d = await c.call("add_cylindrical_restraint", cylinder_face_point=[0.0, 0.0, 20.0], study_name="Conn_Live")
    record("add_cylindrical_restraint su faccia piana -> errore", not ok, txt[:80])
    ok, txt, d = await c.call("add_pin_connector", face1_point=[5.0, 20.0, 5.0], face2_point=[20.0, 20.0, 5.0], study_name="Conn_Live")
    record("add_pin_connector: creato tra fori R5", ok and bool(d.get("name")) and near(d.get("radius1_mm"), 5.0, 1e-6)
           and near(d.get("radius2_mm"), 5.0, 1e-6), txt)
    ok, txt, d = await c.call("add_bolt_connector", head_edge_point=[25.0, 20.0, 5.0], nut_edge_point=[10.0, 20.0, 5.0],
                              bolt_diameter=10.0, preload_force_n=2500.0, study_name="Conn_Live")
    record("add_bolt_connector: diametro e precarico riletti, oppure rifiuto esplicito (pezzo)", (ok and d.get("bolt_diameter_mm") == 10.0
           and d.get("preload_force_n") == 2500.0) or (not ok and "codice 30" in txt), txt[:110])
    ok, txt, d = await c.call("add_bolt_connector", head_edge_point=[25.0, 0.0, 30.0], nut_edge_point=[10.0, 20.0, 5.0],
                              bolt_diameter=10.0, study_name="Conn_Live")
    record("add_bolt_connector con spigolo rettilineo -> errore", not ok, txt[:80])
    ok, txt, d = await c.call("add_spot_weld_connector", face1_point=[10.0, 0.0, 0.0], face2_point=[15.0, 0.0, 0.0],
                              location_points=[[10.0, 50.0, 30.0]], spot_diameter=6.0, study_name="Conn_Live")
    record("add_spot_weld_connector: diametro 6 riletto, 1 punto", ok and d.get("spot_diameter_mm") == 6.0 and d.get("locations") == 1, txt)
    ok, txt, d = await c.call("add_virtual_wall_contact", face_point=[0.0, 0.0, 20.0], wall_plane="front", rigid_wall=True,
                              study_name="Conn_Live")
    record("add_virtual_wall_contact: tipo 4, parete rigida", ok and d.get("contact_type") == 4 and d.get("rigid_wall") is True, txt)
    ok, txt, d = await c.call("add_virtual_wall_contact", face_point=[0.0, 0.0, 20.0], wall_plane="piano_inesistente", study_name="Conn_Live")
    record("add_virtual_wall_contact con piano inesistente -> errore", not ok, txt[:80])
    await c.call("save_document")
    await c.call("close_document", discard=True)

    # =============================================================== mozzo con foro R10 e albero R10.5 (accoppiamento forzato)
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-50, y1=-30, x2=50, y2=30, unit="mm")
    await c.call("extrude_boss", depth=10, unit="mm")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=-25, y=0, radius=10, unit="mm")
    await c.call("extrude_cut", end_condition="through_all_both", unit="mm")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=-25, y=0, radius=10.5, unit="mm")
    await c.call("extrude_boss", depth=10, merge=False, unit="mm")
    await c.call("assign_material", material="AISI 1020")
    ok_s, _, _ = await c.call("save_document", filepath=str(SHRK))
    await c.call("create_static_study", name="Forz_Live")
    ok, txt, d = await c.call("add_shrink_fit_contact", face_hub_point=[5.0, -15.0, 0.0], face_shaft_point=[5.0, -14.5, 0.0],
                              friction_coefficient=0.15, study_name="Forz_Live")
    record("add_shrink_fit_contact: tipo 2, interferenza 0,5 mm misurata, attrito 0,15", ok_s and ok and d.get("contact_type") == 2
           and near(d.get("radial_interference_mm"), 0.5, 1e-4) and d.get("friction") == 0.15, txt)
    ok, txt, d = await c.call("add_shrink_fit_contact", face_hub_point=[0.0, 0.0, 20.0], face_shaft_point=[5.0, -14.5, 0.0],
                              study_name="Forz_Live")
    record("add_shrink_fit_contact con faccia piana -> errore", not ok, txt[:80])


if __name__ == "__main__":
    asyncio.run(run())
