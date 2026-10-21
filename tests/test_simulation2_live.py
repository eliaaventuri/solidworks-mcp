"""
Live test for Lotto SIMULAZIONE 2 (32 tools) against dedicated hidden SolidWorks instance.
"""

import os
import sys
import time
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup, EXPECTED_TOOLS

TS = int(time.time())
PART = OUT / f"test_sim2_live_{TS}.SLDPRT"
RPT_OUT = OUT / f"test_sim2_report_{TS}.html"

RESULTS = []


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:180], flush=True)


async def run():
    elia_pids = sw_pids()
    print(f"Istanze SolidWorks pre-esistenti: {sorted(elia_pids)}", flush=True)
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
                print(f"Connesso a istanza SolidWorks dedicata: PID {my_pid}", flush=True)
                record("connect_solidworks", ok)

                # =============================================================
                # Setup: Model Part for Simulation 2
                # =============================================================
                await c.call("create_new_part")
                await c.call("create_sketch", plane="Front")
                await c.call("draw_rectangle", x1=-10, y1=-5, x2=10, y2=5, unit="mm")
                await c.call("extrude_boss", depth=200, unit="mm")
                await c.call("assign_material", material="AISI 1020")

                ok_bb, txt_bb, d_bb = await c.call("get_bounding_box")
                print(f"Bounding box trave: {d_bb}", flush=True)

                # Punti esatti delle facce della trave 200 x 20 x 10 mm
                # BBox: X [0, 200], Y [-10, 10], Z [-5, 5]
                p_front = [0.0, 0.0, 0.0]
                p_back = [200.0, 0.0, 0.0]
                p_top = [100.0, 10.0, 0.0]
                p_bot = [100.0, -10.0, 0.0]
                p_side1 = [100.0, 0.0, 5.0]
                p_side2 = [100.0, 0.0, -5.0]
                print(f"Punti facce: front={p_front}, back={p_back}, top={p_top}, bot={p_bot}, s1={p_side1}, s2={p_side2}", flush=True)

                if PART.exists():
                    try:
                        PART.unlink()
                    except Exception:
                        pass
                ok, _, _ = await c.call("save_document", filepath=str(PART))
                record("setup model part for simulation", ok)

                # =============================================================
                # 1. Studio Frequenze Modali
                # =============================================================
                ok_frq, txt_frq, d_frq = await c.call("create_frequency_study", study_name="Freq_Live", num_frequencies=3)
                record("create_frequency_study", ok_frq and d_frq.get("num_frequencies") == 3, txt_frq)

                ok_fix, txt_fix, _ = await c.call("add_restraint", kind="fixed", faces=[p_front], study="Freq_Live")
                record("add_restraint on frequency study", ok_fix, txt_fix)

                ok_msh, txt_msh, _ = await c.call("create_simulation_mesh", study="Freq_Live", element_size=20.0)
                record("create_simulation_mesh frequency", ok_msh, txt_msh)

                ok_run, txt_run, _ = await c.call("run_simulation", study="Freq_Live")
                record("run_simulation frequency", ok_run, txt_run)

                ok_mds, txt_mds, d_mds = await c.call("get_mode_shapes", mode_number=1, study_name="Freq_Live")
                record("get_mode_shapes", ok_mds and d_mds.get("frequency_hz", 0) > 0, txt_mds)

                ok_mqm, txt_mqm, d_mqm = await c.call("get_mesh_quality_metrics", study_name="Freq_Live")
                record("get_mesh_quality_metrics", ok_mqm and d_mqm.get("nodes", 0) > 0, txt_mqm)

                ok_prb, txt_prb, d_prb = await c.call("probe_simulation_results", x=100.0, y=0.0, z=0.0, study_name="Freq_Live")
                record("probe_simulation_results", ok_prb and d_prb.get("nearest_node") is not None, txt_prb)

                ok_rct, txt_rct, d_rct = await c.call("get_reaction_forces_detail", face_point=p_front, study_name="Freq_Live")
                record("get_reaction_forces_detail", ok_rct and "resultant_n" in d_rct, txt_rct)

                if RPT_OUT.exists():
                    try:
                        RPT_OUT.unlink()
                    except Exception:
                        pass
                ok_rpt, txt_rpt, d_rpt = await c.call("export_simulation_report", filepath=str(RPT_OUT), study_name="Freq_Live", overwrite=True)
                record("export_simulation_report", ok_rpt and RPT_OUT.exists() and RPT_OUT.stat().st_size > 0, txt_rpt)

                # =============================================================
                # 2. Studio Instabilita' (Buckling)
                # =============================================================
                ok_bck, txt_bck, d_bck = await c.call("create_buckling_study", study_name="Buckling_Live", num_modes=2)
                record("create_buckling_study", ok_bck and d_bck.get("num_modes") == 2, txt_bck)

                await c.call("add_restraint", kind="fixed", faces=[p_front], study="Buckling_Live")
                await c.call("add_force", faces=[p_back], value=1000.0, mode="direction", direction=[-1, 0, 0], study="Buckling_Live")
                await c.call("create_simulation_mesh", study="Buckling_Live", element_size=20.0)
                ok_brn, txt_brn, _ = await c.call("run_simulation", study="Buckling_Live")
                record("run buckling study", ok_brn, txt_brn)

                ok_blf, txt_blf, d_blf = await c.call("get_buckling_load_factor", mode_number=1, study_name="Buckling_Live")
                record("get_buckling_load_factor", ok_blf and "buckling_load_factor" in d_blf, txt_blf)

                # =============================================================
                # 3. Studio Termico e Carichi Termici
                # =============================================================
                ok_thm, txt_thm, d_thm = await c.call("create_thermal_study", study_name="Thermal_Live", transient=False)
                record("create_thermal_study", ok_thm and d_thm.get("type") == "thermal", txt_thm)

                ok_tmp, txt_tmp, _ = await c.call("add_temperature", faces=[p_front], value=120.0, study="Thermal_Live")
                record("add_temperature thermal", ok_tmp, txt_tmp)

                ok_cnv, txt_cnv, _ = await c.call("add_convection_load", face_point=p_back, convection_coefficient=25.0,
                                                  ambient_temperature_c=20.0, study_name="Thermal_Live")
                record("add_convection_load", ok_cnv, txt_cnv)

                await c.call("create_simulation_mesh", study="Thermal_Live", element_size=20.0)
                ok_trn, txt_trn, _ = await c.call("run_simulation", study="Thermal_Live")
                record("run thermal study", ok_trn, txt_trn)

                ok_trs, txt_trs, d_trs = await c.call("get_thermal_results", study_name="Thermal_Live")
                record("get_thermal_results", ok_trs and "temperature_max_c" in d_trs, txt_trs)

                ok_rad, txt_rad, _ = await c.call("add_radiation_load", face_point=p_top, emissivity=0.85,
                                                  ambient_temperature_c=20.0, study_name="Thermal_Live")
                record("add_radiation_load", ok_rad, txt_rad)

                ok_hpw, txt_hpw, _ = await c.call("add_heat_power_load", face_point=p_bot, heat_power_w=80.0,
                                                  study_name="Thermal_Live")
                record("add_heat_power_load", ok_hpw, txt_hpw)

                # =============================================================
                # 4. Vincoli Avanzati e Carichi Meccanici (Studio Static_Restraints)
                # =============================================================
                ok_stc, _, _ = await c.call("create_static_study", name="Static_Restraints")
                record("create_static_study for ext tools", ok_stc)

                ok_esp, txt_esp, _ = await c.call("add_elastic_support", face_point=p_front, stiffness=100.0, study_name="Static_Restraints")
                record("add_elastic_support", ok_esp, txt_esp)

                ok_pds, txt_pds, _ = await c.call("add_prescribed_displacement", face_point=p_back, displacement_mm=1.5, study_name="Static_Restraints")
                record("add_prescribed_displacement", ok_pds, txt_pds)

                ok_cyl, txt_cyl, _ = await c.call("add_cylindrical_restraint", cylinder_face_point=p_top,
                                                  radial_free=False, axial_free=False, circumferential_free=True, study_name="Static_Restraints")
                record("add_cylindrical_restraint", ok_cyl, txt_cyl)

                ok_cen, txt_cen, _ = await c.call("add_centrifugal_load", angular_velocity_rad_s=120.0, study_name="Static_Restraints")
                record("add_centrifugal_load", ok_cen, txt_cen)

                ok_tsh, txt_tsh, _ = await c.call("add_thermal_shrinkage_load", face_point=p_bot, delta_temperature_c=-40.0, study_name="Static_Restraints")
                record("add_thermal_shrinkage_load", ok_tsh, txt_tsh)

                # =============================================================
                # 5. Connettori Meccanici (Studio Static_Connectors)
                # =============================================================
                await c.call("create_static_study", name="Static_Connectors")

                ok_blt, txt_blt, _ = await c.call("add_bolt_connector", bolt_face_point=p_top, bolt_diameter=10.0,
                                                  preload_force_n=2500.0, study_name="Static_Connectors")
                record("add_bolt_connector", ok_blt, txt_blt)

                ok_pin, txt_pin, _ = await c.call("add_pin_connector", pin_face_point=p_bot, pin_diameter=8.0, study_name="Static_Connectors")
                record("add_pin_connector", ok_pin, txt_pin)

                ok_spg, txt_spg, _ = await c.call("add_spring_connector", point1=p_front, point2=p_back,
                                                  stiffness_n_mm=150.0, study_name="Static_Connectors")
                record("add_spring_connector", ok_spg, txt_spg)

                ok_wld, txt_wld, _ = await c.call("add_spot_weld_connector", point=p_side1, spot_diameter=6.0, study_name="Static_Connectors")
                record("add_spot_weld_connector", ok_wld, txt_wld)

                # =============================================================
                # 6. Contatti, Materiali, Mesh Speciali e Solutore (Studio Static_Mesh)
                # =============================================================
                await c.call("create_static_study", name="Static_Mesh")

                ok_shk, txt_shk, _ = await c.call("add_shrink_fit_contact", face_hub_point=p_top, face_shaft_point=p_bot,
                                                  radial_interference_mm=0.015, study_name="Static_Mesh")
                record("add_shrink_fit_contact", ok_shk, txt_shk)

                ok_vwl, txt_vwl, _ = await c.call("add_virtual_wall_contact", face_point=p_side2, friction_coefficient=0.2,
                                                  rigid_wall=True, study_name="Static_Mesh")
                record("add_virtual_wall_contact", ok_vwl, txt_vwl)

                ok_ort, txt_ort, _ = await c.call("set_orthotropic_material", ex_mpa=140000.0, ey_mpa=11000.0, ez_mpa=11000.0, study_name="Static_Mesh")
                record("set_orthotropic_material", ok_ort, txt_ort)

                ok_shl, txt_shl, _ = await c.call("define_shell_mesh", face_point=p_top, thickness=2.5, mid_plane=True, study_name="Static_Mesh")
                record("define_shell_mesh", ok_shl, txt_shl)

                ok_bem, txt_bem, _ = await c.call("define_beam_mesh", body_name="Boss-Extrude1", beam_type="beam", study_name="Static_Mesh")
                record("define_beam_mesh", ok_bem, txt_bem)

                ok_slv, txt_slv, _ = await c.call("set_solver_options", solver_type="FFEPlus", large_displacement=False, study_name="Static_Mesh")
                record("set_solver_options", ok_slv, txt_slv)

                # =============================================================
                # 7. Altri Studi FEA Speciali (Drop Test, Fatica, Topologia, Dinamico)
                # =============================================================
                ok_drp, txt_drp, _ = await c.call("create_drop_test_study", study_name="Drop_Live", drop_height=1200.0)
                record("create_drop_test_study", ok_drp, txt_drp)

                ok_fat, txt_fat, _ = await c.call("create_fatigue_study", study_name="Fatigue_Live", event_cycles=75000)
                record("create_fatigue_study", ok_fat, txt_fat)

                ok_top, txt_top, _ = await c.call("create_topology_study", study_name="Topology_Live", target_mass_percent=45.0)
                record("create_topology_study", ok_top, txt_top)

                ok_dyn, txt_dyn, _ = await c.call("create_linear_dynamic_study", study_name="Dynamic_Live", dynamic_type="harmonic")
                record("create_linear_dynamic_study", ok_dyn, txt_dyn)

                # Chiude documento senza salvare per pulizia
                await c.call("close_document", discard=True)

    finally:
        cleanup(my_pid, elia_pids)

    passed = sum(1 for _, ok, _ in RESULTS if ok == "PASS")
    total = len(RESULTS)
    print(f"\nRisultato test live Simulazione 2: {passed}/{total} PASS")
    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run())
