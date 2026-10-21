"""
Live test for Lotto ASSIEMI 3 tools against dedicated hidden SolidWorks instance.
"""

import os
import sys
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup, EXPECTED_TOOLS

PART_BOX = OUT / "asm3_box.sldprt"
PART_PIN = OUT / "asm3_pin.sldprt"
VIRTUAL_SAVED_PRT = OUT / "virtual_saved_live.sldprt"

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
                # Setup: Crea due parti reali per l'assieme
                # =============================================================
                print("\n--- Setup parti reali per test assieme ---")
                # Parte 1: Scatola 50x50x30 con foro passante
                await c.call("create_new_part")
                await c.call("create_sketch", plane="Front")
                await c.call("draw_rectangle", x1=-25, y1=-25, x2=25, y2=25)
                await c.call("draw_circle", x=0, y=0, radius=10)
                await c.call("extrude_boss", depth=30)
                await c.call("save_document", filepath=str(PART_BOX), overwrite=True)
                await c.call("close_document", discard=True)

                # Parte 2: Perno cilindrico Ø20 x 80
                await c.call("create_new_part")
                await c.call("create_sketch", plane="Front")
                await c.call("draw_circle", x=0, y=0, radius=10)
                await c.call("extrude_boss", depth=80)
                await c.call("save_document", filepath=str(PART_PIN), overwrite=True)
                await c.call("close_document", discard=True)

                # =============================================================
                # Test Suite Assembly 3 Live
                # =============================================================
                print("\n--- Test Assembly 3 Tools Live ---")
                ok_asm, _, _ = await c.call("create_new_assembly")
                record("create_new_assembly", ok_asm)

                # Inserisci i due componenti reali
                ok_i1, _, _ = await c.call("insert_component", file_path=str(PART_BOX), x=0, y=0, z=0, fixed=True)
                record("insert_component box", ok_i1)
                ok_i2, _, _ = await c.call("insert_component", file_path=str(PART_PIN), x=0, y=0, z=100, fixed=False)
                record("insert_component pin", ok_i2)

                # 1. Virtual Parts & Subassemblies
                ok_vp, text_vp, data_vp = await c.call("insert_new_virtual_part", plane_or_face="Front Plane", part_name="VirtPart1")
                record("insert_new_virtual_part", ok_vp, f"part: {data_vp.get('virtual_part')}" if ok_vp else text_vp[:60])

                ok_va, text_va, data_va = await c.call("insert_new_virtual_assembly", subassembly_name="VirtSub1")
                record("insert_new_virtual_assembly", ok_va, f"subassembly: {data_va.get('virtual_subassembly')}" if ok_va else text_va[:60])

                # 2. In-context editing and exit
                ok_ep, text_ep, _ = await c.call("edit_part_in_context", component_name="asm3_box-1")
                record("edit_part_in_context", ok_ep, "" if ok_ep else text_ep[:60])

                ok_xp, text_xp, _ = await c.call("exit_part_in_context")
                record("exit_part_in_context", ok_xp, "" if ok_xp else text_xp[:60])

                # 3. Save virtual component externally
                ok_sv, text_sv, _ = await c.call("save_virtual_component_external", component_name="VirtPart1",
                                           filepath=str(VIRTUAL_SAVED_PRT), overwrite=True)
                record("save_virtual_component_external", ok_sv, "" if ok_sv else text_sv[:60])

                # 4. Component Management: Transparency, Size Selection, Envelope, Independence, Reordering
                ok_trn, text_trn, _ = await c.call("set_component_transparency", component_name="asm3_box-1", transparent=True)
                record("set_component_transparency", ok_trn, "" if ok_trn else text_trn[:60])

                ok_siz, text_siz, data_siz = await c.call("select_components_by_size", percentage=15.0)
                record("select_components_by_size", ok_siz, f"selected: {data_siz.get('selected_count')}" if ok_siz else text_siz[:60])

                ok_env, text_env, _ = await c.call("set_envelope_component", component_name="asm3_pin-1", is_envelope=True)
                record("set_envelope_component", ok_env, "" if ok_env else text_env[:60])

                ok_ind, text_ind, _ = await c.call("make_component_independent", component_name="asm3_pin-1")
                record("make_component_independent", ok_ind, "" if ok_ind else text_ind[:60])

                ok_ord, text_ord, _ = await c.call("reorder_components", components=["asm3_pin-1"], target_component="asm3_box-1", position="after")
                record("reorder_components", ok_ord, "" if ok_ord else text_ord[:60])

                # 5. Flexibility and Hierarchy
                ok_flx, text_flx, _ = await c.call("set_subassembly_flexible", component_name="VirtSub1", flexible=True)
                record("set_subassembly_flexible", ok_flx, "" if ok_flx else text_flx[:60])

                ok_pro, text_pro, _ = await c.call("promote_subassembly_component", component_name="VirtSub1/SubPart")
                record("promote_subassembly_component", ok_pro, "" if ok_pro else text_pro[:60])

                ok_dem, text_dem, _ = await c.call("demote_subassembly_component", component_name="asm3_pin-1", target_subassembly="VirtSub1")
                record("demote_subassembly_component", ok_dem, "" if ok_dem else text_dem[:60])

                # 6. Inspection & Performance
                ok_iso, text_iso, _ = await c.call("isolate_components", components=["asm3_box-1"], transparent_others=True)
                record("isolate_components", ok_iso, "" if ok_iso else text_iso[:60])

                ok_xis, text_xis, _ = await c.call("exit_isolate")
                record("exit_isolate", ok_xis, "" if ok_xis else text_xis[:60])

                ok_rep, text_rep, _ = await c.call("auto_repair_mates")
                record("auto_repair_mates", ok_rep, "" if ok_rep else text_rep[:60])

                ok_chk, text_chk, _ = await c.call("check_mate_redundancy")
                record("check_mate_redundancy", ok_chk, "" if ok_chk else text_chk[:60])

                ok_spd, text_spd, _ = await c.call("create_speedpak", name="SpeedPak_Live", graphic_only=True)
                record("create_speedpak", ok_spd, "" if ok_spd else text_spd[:60])

                # 7. Specialized Features
                ok_dis, text_dis, _ = await c.call("dissolve_component_pattern", pattern_name="Pattern1")
                record("dissolve_component_pattern", ok_dis, "" if ok_dis else text_dis[:60])

                ok_exp, text_exp, _ = await c.call("edit_explode_step", step_index=0, distance=60.0)
                record("edit_explode_step", ok_exp, "" if ok_exp else text_exp[:60])

                ok_cav, text_cav, _ = await c.call("insert_cavity_feature", tooling_components=["asm3_pin-1"], scale_percentage=1.0)
                record("insert_cavity_feature", ok_cav, "" if ok_cav else text_cav[:60])

                ok_joi, text_joi, _ = await c.call("insert_join_feature", components=["asm3_box-1", "asm3_pin-1"])
                record("insert_join_feature", ok_joi, "" if ok_joi else text_joi[:60])

                ok_smt, text_smt, _ = await c.call("create_smart_component", component_name="asm3_box-1")
                record("create_smart_component", ok_smt, "" if ok_smt else text_smt[:60])

                # 8. Mechanical Mates & Concentric Operations
                ok_tol, text_tol, _ = await c.call("add_concentric_mate_with_tolerance", entity1="asm3_box-1", entity2="asm3_pin-1", tolerance=0.05)
                record("add_concentric_mate_with_tolerance", ok_tol, "" if ok_tol else text_tol[:60])

                ok_lck, text_lck, _ = await c.call("lock_mate_rotation", mate_name="Concentric1", locked=True)
                record("lock_mate_rotation", ok_lck, "" if ok_lck else text_lck[:60])

                ok_flp, text_flp, _ = await c.call("flip_mate_alignment", mate_name="Coincident1")
                record("flip_mate_alignment", ok_flp, "" if ok_flp else text_flp[:60])

                ok_gea, text_gea, _ = await c.call("add_gear_mate", entity1="asm3_box-1", entity2="asm3_pin-1", ratio_num=2.0, ratio_den=1.0)
                record("add_gear_mate", ok_gea, "" if ok_gea else text_gea[:60])

                ok_rck, text_rck, _ = await c.call("add_rack_pinion_mate", rack_entity="asm3_box-1", pinion_entity="asm3_pin-1", pitch_diameter=40.0)
                record("add_rack_pinion_mate", ok_rck, "" if ok_rck else text_rck[:60])

                ok_cam, text_cam, _ = await c.call("add_cam_mate", cam_faces=["asm3_box-1"], follower_face="asm3_pin-1")
                record("add_cam_mate", ok_cam, "" if ok_cam else text_cam[:60])

                ok_slt, text_slt, _ = await c.call("add_slot_mate", slot_entity="asm3_box-1", pin_entity="asm3_pin-1", constraint_type="center")
                record("add_slot_mate", ok_slt, "" if ok_slt else text_slt[:60])

                ok_hng, text_hng, _ = await c.call("add_hinge_mate", concentric_entity1="asm3_box-1", concentric_entity2="asm3_pin-1",
                                            coincident_face1="asm3_box-1", coincident_face2="asm3_pin-1", min_angle=0.0, max_angle=90.0)
                record("add_hinge_mate", ok_hng, "" if ok_hng else text_hng[:60])

                ok_scw, text_scw, _ = await c.call("add_screw_mate", axis_entity1="asm3_box-1", axis_entity2="asm3_pin-1", pitch=1.5)
                record("add_screw_mate", ok_scw, "" if ok_scw else text_scw[:60])

                ok_cpl, text_cpl, _ = await c.call("add_linear_coupler_mate", entity1="asm3_box-1", entity2="asm3_pin-1", ratio=1.5)
                record("add_linear_coupler_mate", ok_cpl, "" if ok_cpl else text_cpl[:60])

                ok_unj, text_unj, _ = await c.call("add_universal_joint_mate", shaft_entity1="asm3_box-1", shaft_entity2="asm3_pin-1")
                record("add_universal_joint_mate", ok_unj, "" if ok_unj else text_unj[:60])

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
