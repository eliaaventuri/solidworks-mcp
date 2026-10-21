"""
Live test for Lotto MODELLAZIONE 4 (33 tools) against dedicated hidden SolidWorks instance.
"""

import os
import sys
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup, EXPECTED_TOOLS

PART = OUT / "test_features4_live_part.SLDPRT"

RESULTS = []


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:180])


async def run():
    elia_pids = sw_pids()
    print(f"Istanze SolidWorks pre-esistenti: {sorted(elia_pids)}")
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
                print(f"Connesso a istanza SolidWorks dedicata: PID {my_pid}")
                record("connect_solidworks", ok)

                # =============================================================
                # Setup: Model Part for Features 4
                # =============================================================
                await c.call("create_new_part")
                await c.call("create_sketch", plane="Front")
                await c.call("draw_rectangle", x1=-60, y1=-40, x2=60, y2=40, unit="mm")
                await c.call("extrude_sketch", depth=30, unit="mm")
                await c.call("save_document", filepath=str(PART), overwrite=True)

                # =============================================================
                # Test Suite Features 4 Live (33 tools)
                # =============================================================
                print("\n--- Test Features 4 Tools Live ---")

                # 1. Estrusioni, Rivoluzioni e Tagli Solidi
                ok_efs, _, _ = await c.call("extrude_from_surface", depth=10.0, offset_distance=2.0)
                record("extrude_from_surface", ok_efs)

                ok_isf, _, _ = await c.call("intersect_solid_features", body_names=["SolidBody1"])
                record("intersect_solid_features", ok_isf)

                # 2. Loft, Sweep e Boundary Solidi
                ok_ss, _, _ = await c.call("solid_sweep", tool_body_name="SolidBody1", path_sketch="Sketch1")
                record("solid_sweep", ok_ss)

                ok_vss, _, _ = await c.call("variable_section_sweep", profile_sketch="Sketch1", path_sketch="Sketch1", scale_factor=1.2)
                record("variable_section_sweep", ok_vss)

                # 3. Raccordi, Smussi e Lavorazioni Spigoli
                ok_sbf, _, _ = await c.call("setback_fillet", vertex_point=[60, 40, 30], radius=5.0)
                record("setback_fillet", ok_sbf)

                ok_ccf, _, _ = await c.call("curvature_continuous_fillet", edge_points=[[60, 0, 30]], radius=4.0, rho_conic=0.5)
                record("curvature_continuous_fillet", ok_ccf)

                # 4. Forometria Avanzata e Filettature
                ok_swz, _, _ = await c.call("stud_wizard", face_point=[0, 0, 30], shaft_diameter=8.0, stud_length=25.0, standard="ISO", size="M8x1.25")
                record("stud_wizard", ok_swz)

                ok_tli, _, _ = await c.call("thread_lead_in", cylinder_face_point=[0, 0, 30], pitch=1.25, angle_deg=45.0)
                record("thread_lead_in", ok_tli)

                # 5. Geometria di Riferimento e Assi
                ok_eqc, _, _ = await c.call("create_reference_curve_from_equation", x_equation="40*cos(t)", y_equation="40*sin(t)", z_equation="5*t", t_start=0.0, t_end=6.28)
                record("create_reference_curve_from_equation", ok_eqc)

                # 6. Ripetizioni e Simmetrie 3D
                ok_cp, _, _ = await c.call("chain_pattern", chain_path_sketch="Sketch1", instance_count=6, pitch_distance=15.0)
                record("chain_pattern", ok_cp)

                ok_mbm, _, _ = await c.call("mirror_body_merge", body_names=["SolidBody1"], mirror_plane="Front", merge_bodies=True)
                record("mirror_body_merge", ok_mbm)

                # 7. Gestione Multibody (Booleane e Tagli)
                ok_ccs, _, _ = await c.call("core_cavity_split", block_size=[150, 100, 60])
                record("core_cavity_split", ok_ccs)

                ok_brf, _, _ = await c.call("body_replace_face", target_face_points=[[0, 0, 30]], surface_name="SurfaceBody1")
                record("body_replace_face", ok_brf)

                # 8. Modellazione di Superfici (Surfaces)
                ok_ffs, _, _ = await c.call("freeform_surface", surface_face_point=[0, 0, 30], push_distance=2.5)
                record("freeform_surface", ok_ffs)

                ok_fls, _, _ = await c.call("flatten_surface", surface_face_point=[0, 0, 30], accuracy_level=3)
                record("flatten_surface", ok_fls)

                ok_rad, _, _ = await c.call("radiate_surface", edge_points=[[60, 40, 0]], radius_distance=15.0)
                record("radiate_surface", ok_rad)

                # 9. Lamiera (Sheet Metal)
                ok_cb, _, _ = await c.call("cross_break", face_point=[0, 0, 30], depth=1.0, break_angle=2.0)
                record("cross_break", ok_cb)

                ok_csm, _, _ = await c.call("convert_to_sheet_metal", thickness=2.0, bend_radius=2.5, fixed_face_point=[0, 0, 30])
                record("convert_to_sheet_metal", ok_csm)

                ok_vnt, _, _ = await c.call("vent_feature", boundary_sketch="Sketch1", rib_width=2.0, spar_width=2.0)
                record("vent_feature", ok_vnt)

                ok_lb, _, _ = await c.call("loft_bend", profile1_sketch="Sketch1", profile2_sketch="Sketch1", thickness=1.5, bend_count=4)
                record("loft_bend", ok_lb)

                ok_cef, _, _ = await c.call("curved_edge_flange", edge_point=[60, 0, 30], flange_length=20.0, angle_deg=90.0)
                record("curved_edge_flange", ok_cef)

                # 10. Saldature e Strutture Metalliche
                ok_cwb, _, _ = await c.call("cosmetic_weld_bead", face_from_point=[-60, 0, 15], face_to_point=[0, -40, 15], bead_size=4.0)
                record("cosmetic_weld_bead", ok_cwb)

                ok_ucl, _, _ = await c.call("update_cut_list", force_rebuild=True)
                record("update_cut_list", ok_ucl)

                ok_swf, _, _ = await c.call("subweldment_folder", folder_name="MainFrame", member_names=["Member1"])
                record("subweldment_folder", ok_swf)

                # 11. Stampi (Mold Design) e Plastica
                ok_ipl, _, _ = await c.call("insert_parting_line", direction_face_point=[0, 0, 30], draft_angle=1.0)
                record("insert_parting_line", ok_ipl)

                ok_iso, _, _ = await c.call("insert_shut_off_surfaces", patch_all_openings=True)
                record("insert_shut_off_surfaces", ok_iso)

                ok_ips, _, _ = await c.call("insert_parting_surface", distance=25.0)
                record("insert_parting_surface", ok_ips)

                ok_its, _, _ = await c.call("insert_tooling_split", core_block_size=[150, 100, 50], cavity_block_size=[150, 100, 50])
                record("insert_tooling_split", ok_its)

                ok_ilg, _, _ = await c.call("insert_lip_and_groove", edge_points=[[60, 0, 30]], lip_depth=2.0, groove_width=2.2)
                record("insert_lip_and_groove", ok_ilg)

                ok_ish, _, _ = await c.call("insert_snap_hook", location_point=[30, 20, 30], hook_height=15.0, beam_thickness=2.0)
                record("insert_snap_hook", ok_ish)

                ok_imb, _, _ = await c.call("insert_mounting_boss", location_point=[-30, 20, 30], height=12.0, outer_diameter=8.0, inner_hole_diameter=3.0)
                record("insert_mounting_boss", ok_imb)

                # 12. Analisi Geometrica e Qualità B-Rep
                ok_mbc, _, _ = await c.call("mesh_brep_converter", body_name="SolidBody1", target_type="solid")
                record("mesh_brep_converter", ok_mbc)

                ok_sda, _, _ = await c.call("surface_deviation_analysis", face1_point=[0, 0, 30], face2_point=[0, 0, 0], samples_count=50)
                record("surface_deviation_analysis", ok_sda)

                # Chiudi documento
                await c.call("close_document", discard=True)

    finally:
        print("\nCleanup istanza dedicata...")
        cleanup(my_pid, elia_pids)

    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
