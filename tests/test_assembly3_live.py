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


def mid_point(bb):
    return [(bb["min"][i] + bb["max"][i]) / 2 for i in range(3)]


def pt_on(base, ax, along, p1, p2):
    """Punto con coordinata 'along' sull'asse ax (asse del cilindro), p1 e p2 sulle due altre coordinate."""
    q = list(base)
    q[ax] = along
    q[(ax + 1) % 3] = p1
    q[(ax + 2) % 3] = p2
    return q


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
                ok_bb1, _, bb_box = await c.call("get_bounding_box")
                record("ingombro scatola 50x50x30", ok_bb1 and sorted(bb_box.get("size", [])) == [30, 50, 50],
                       f"size {bb_box.get('size')}")
                await c.call("save_document", filepath=str(PART_BOX), overwrite=True)
                await c.call("close_document", discard=True)

                # Parte 2: Perno cilindrico Ø20 x 80
                await c.call("create_new_part")
                await c.call("create_sketch", plane="Front")
                await c.call("draw_circle", x=0, y=0, radius=10)
                await c.call("extrude_boss", depth=80)
                ok_bb2, _, bb_pin = await c.call("get_bounding_box")
                record("ingombro perno 20x20x80", ok_bb2 and sorted(bb_pin.get("size", [])) == [20, 20, 80],
                       f"size {bb_pin.get('size')}")
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
                record("insert_new_virtual_part: rifiutato perche' non implementato", (not ok_vp) and "non e' implementato" in text_vp,
                       text_vp[:80])

                ok_va, text_va, data_va = await c.call("insert_new_virtual_assembly", subassembly_name="VirtSub1")
                record("insert_new_virtual_assembly", ok_va, f"subassembly: {data_va.get('virtual_subassembly')}" if ok_va else text_va[:60])

                # 2. In-context editing and exit
                ok_ep, text_ep, _ = await c.call("edit_part_in_context", component_name="asm3_box-1")
                record("edit_part_in_context", ok_ep, "" if ok_ep else text_ep[:60])

                ok_xp, text_xp, _ = await c.call("exit_part_in_context")
                record("exit_part_in_context", ok_xp, "" if ok_xp else text_xp[:60])

                # 3. Save virtual component externally
                ok_sv, text_sv, _ = await c.call("save_virtual_component_external", component_name=(data_va or {}).get("virtual_subassembly"),
                                           filepath=str(VIRTUAL_SAVED_PRT), overwrite=True)
                record("save_virtual_component_external: rifiutato perche' non implementato", (not ok_sv) and "non e' implementato" in text_sv, text_sv[:80])

                # 4. Component Management: Transparency, Size Selection, Envelope, Independence, Reordering
                ok_trn, text_trn, _ = await c.call("set_component_transparency", component_name="asm3_box-1", transparent=True)
                record("set_component_transparency", ok_trn, "" if ok_trn else text_trn[:60])

                ok_siz, text_siz, data_siz = await c.call("select_components_by_size", percentage=15.0)
                record("select_components_by_size", ok_siz, f"selected: {data_siz.get('selected_count')}" if ok_siz else text_siz[:60])

                ok_nev, text_nev, _ = await c.call("set_envelope_component", component_name="asm3_pin-1", is_envelope=True)
                record("set_envelope_component: rifiutato perche' non implementato", (not ok_nev) and "non e' implementato" in text_nev, text_nev[:80])

                ok_ind, text_ind, data_ind = await c.call("make_component_independent", component_name="asm3_pin-1",
                                                          new_filepath=str(OUT / "asm3_pin_indip.sldprt"))
                record("make_component_independent", ok_ind and (data_ind or {}).get("independent") is True,
                       "" if ok_ind else text_ind[:60])

                ok_ord, text_ord, _ = await c.call("reorder_components", components=["asm3_pin_indip-1"], target_component="asm3_box-1", position="after")
                record("reorder_components", ok_ord, "" if ok_ord else text_ord[:60])

                # 5. Flexibility and Hierarchy
                ok_flx, text_flx, _ = await c.call("set_subassembly_flexible", component_name=(data_va or {}).get("virtual_subassembly"), flexible=True)
                record("set_subassembly_flexible", ok_flx, "" if ok_flx else text_flx[:60])

                ok_nim, text_nim, _ = await c.call("promote_subassembly_component", component_name="VirtSub1/SubPart")
                record("promote_subassembly_component: rifiutato perche' non implementato", (not ok_nim) and "non e' implementato" in text_nim, text_nim[:80])

                # 6. Inspection & Performance
                ok_iso, text_iso, _ = await c.call("isolate_components", components=["asm3_box-1"], transparent_others=True)
                record("isolate_components", ok_iso, "" if ok_iso else text_iso[:60])

                ok_xis, text_xis, _ = await c.call("exit_isolate")
                record("exit_isolate", ok_xis, "" if ok_xis else text_xis[:60])

                ok_rep, text_rep, _ = await c.call("auto_repair_mates")
                record("auto_repair_mates", ok_rep, "" if ok_rep else text_rep[:60])

                ok_spd, text_spd, _ = await c.call("create_speedpak", name="SpeedPak_Live", graphic_only=True)
                record("create_speedpak", ok_spd, "" if ok_spd else text_spd[:60])

                # 7. Specialized Features
                AX_BOX = max(range(3), key=lambda i: -abs(bb_box["size"][i] - 30.0))   # asse di estrusione della scatola
                ok_pat,text_pat, data_pat = await c.call("linear_component_pattern", seed_component="asm3_pin_indip-1",
                                                          direction1={"component": "asm3_box-1", "edge": pt_on(mid_point(bb_box), AX_BOX, mid_point(bb_box)[AX_BOX], 25, 25)},
                                                          count1=3, spacing1=30.0)
                record("linear_component_pattern (prep)", ok_pat and (data_pat or {}).get("total_instances") == 3,
                       f"istanze {(data_pat or {}).get('total_instances')}" if ok_pat else text_pat[:60])
                ok_dis, text_dis, data_dis = await c.call("dissolve_component_pattern", pattern_name=(data_pat or {}).get("feature"))
                record("dissolve_component_pattern", ok_dis, "" if ok_dis else text_dis[:60])

                ok_cav, text_cav, _ = await c.call("insert_cavity_feature", tooling_components=["asm3_pin_indip-1"], scale_percentage=1.0)
                record("insert_cavity_feature", ok_cav, "" if ok_cav else text_cav[:60])

                ok_joi, text_joi, _ = await c.call("insert_join_feature", components=["asm3_box-1", "asm3_pin_indip-1"])
                record("insert_join_feature", ok_joi, "" if ok_joi else text_joi[:60])

                # 8. Accoppiamenti: ogni gruppo su un assieme nuovo (scatola fissa + perno), entita' = facce reali
                # (cilindro del foro, cilindro del perno, faccia piana della scatola e fondo del perno).
                # Quote dai box letti da SolidWorks: il perno e' inserito a z=100.
                # Asse del foro/perno = la direzione di estrusione (ingombro 30 per la scatola, 80 per il perno).
                # Il perno e' a z=100: il centro del suo cilindro e' (y=0, z=100).
                ax = max(range(3), key=lambda i: -abs(bb_box["size"][i] - 30.0))
                bmax = bb_box["max"]
                pmax = bb_pin["max"]
                mb, mp = mid_point(bb_box), mid_point(bb_pin)
                F_HOLE_B = {"component": "asm3_box-1", "face": pt_on(mb, ax, mb[ax], 10, 0)}
                F_TOP_B = {"component": "asm3_box-1", "face": pt_on(mb, ax, bmax[ax], 20, 0)}
                F_SIDE_B = {"component": "asm3_box-1", "face": pt_on(mb, ax, mb[ax], 25, 0)}
                F_CYL_P = {"component": "asm3_pin-1", "face": pt_on(mp, ax, mp[ax], 10, 100)}
                F_END_P = {"component": "asm3_pin-1", "face": pt_on(mp, ax, pmax[ax], 0, 100)}

                async def fresh_pair() -> bool:
                    await c.call("close_document", discard=True)
                    await c.call("create_new_assembly")
                    ok_a, _, _ = await c.call("insert_component", file_path=str(PART_BOX), x=0, y=0, z=0, fixed=True)
                    ok_b, _, _ = await c.call("insert_component", file_path=str(PART_PIN), x=0, y=0, z=100, fixed=False)
                    return bool(ok_a and ok_b)

                await fresh_pair()
                ok_tol, text_tol, data_tol = await c.call("add_concentric_mate_with_tolerance", entity1=F_HOLE_B, entity2=F_CYL_P, tolerance=0.05)
                record("add_concentric_mate_with_tolerance", ok_tol and (data_tol or {}).get("type") == "concentric",
                       f"tipo {(data_tol or {}).get('type')}" if ok_tol else text_tol[:60])
                name_conc = (data_tol or {}).get("name")

                ok_lck, text_lck, _ = await c.call("lock_mate_rotation", mate_name=name_conc, locked=True)
                record("lock_mate_rotation: rifiutato perche' non implementato", (not ok_lck) and "non e' implementato" in text_lck,
                       text_lck[:80])

                await fresh_pair()
                ok_cof, text_cof, data_cof = await c.call("add_mate", mate_type="coincident", entity1=F_TOP_B, entity2=F_END_P)
                name_cof = (data_cof or {}).get("name")
                ok_flp, text_flp, data_flp = await c.call("flip_mate_alignment", mate_name=name_cof)
                record("flip_mate_alignment: rifiutato perche' non implementato", (not ok_flp) and "non e' implementato" in text_flp, text_flp[:80])

                await fresh_pair()
                ok_gea, text_gea, _ = await c.call("add_gear_mate", entity1=F_HOLE_B, entity2=F_CYL_P, ratio_num=2.0, ratio_den=1.0)
                record("add_gear_mate", ok_gea, "" if ok_gea else text_gea[:60])

                await fresh_pair()
                ok_rck, text_rck, _ = await c.call("add_rack_pinion_mate", rack_entity=F_SIDE_B, pinion_entity=F_CYL_P, pitch_diameter=40.0)
                record("add_rack_pinion_mate: rifiutato perche' non implementato", (not ok_rck) and "non e' implementato" in text_rck, text_rck[:80])

                await fresh_pair()
                ok_slt, text_slt, _ = await c.call("add_slot_mate", slot_entity=F_HOLE_B, pin_entity=F_CYL_P, constraint_type="center")
                record("add_slot_mate: rifiutato perche' non implementato", (not ok_slt) and "non e' implementato" in text_slt, text_slt[:80])

                await fresh_pair()
                ok_hng, text_hng, _ = await c.call("add_hinge_mate", concentric_entity1=F_HOLE_B, concentric_entity2=F_CYL_P,
                                            coincident_face1=F_TOP_B, coincident_face2={"component": "asm3_pin-1", "face": pt_on(mp, ax, pmax[ax], 0, 0)},
                min_angle=0.0, max_angle=90.0)
                record("add_hinge_mate", ok_hng, "" if ok_hng else text_hng[:60])

                await fresh_pair()
                ok_scw, text_scw, _ = await c.call("add_screw_mate", axis_entity1=F_HOLE_B, axis_entity2=F_CYL_P, pitch=1.5)
                record("add_screw_mate", ok_scw, "" if ok_scw else text_scw[:60])

                await fresh_pair()
                ok_cpl, text_cpl, _ = await c.call("add_linear_coupler_mate", entity1=F_SIDE_B, entity2=F_END_P, ratio=1.5)
                record("add_linear_coupler_mate", ok_cpl, "" if ok_cpl else text_cpl[:60])

                await fresh_pair()
                ok_unj, text_unj, _ = await c.call("add_universal_joint_mate", shaft_entity1=F_CYL_P, shaft_entity2=F_HOLE_B)
                record("add_universal_joint_mate", ok_unj, "" if ok_unj else text_unj[:60])

                # add_cam_mate per ultimo: con la versione attuale SolidWorks si chiude durante la chiamata (RPC non disponibile)
                await fresh_pair()
                ok_cam, text_cam, _ = await c.call("add_cam_mate", cam_faces=[F_SIDE_B], follower_face=F_CYL_P)
                record("add_cam_mate: rifiutato perche' non implementato", (not ok_cam) and "non e' implementato" in text_cam,
                       text_cam[:80])

                # 9. Esploso: edit_explode_step (distanza e verso riletti da SolidWorks, posa esplosa del perno misurata)
                await fresh_pair()
                ok_es, text_es, _ = await c.call("add_explode_step", components=["asm3_pin-1"], direction="x", distance=30)
                record("add_explode_step (prep): perno 30 mm lungo x", ok_es, "" if ok_es else text_es[:60])
                ok_ed, text_ed, d_ed = await c.call("edit_explode_step", step_index=0, distance=75)
                pos = ((d_ed or {}).get("exploded_positions") or {}).get("asm3_pin-1") or {}
                dx = pos["after_mm"][0] - pos["before_mm"][0] if pos.get("after_mm") and pos.get("before_mm") else None
                record("edit_explode_step: 30 -> 75 mm, il perno esploso avanza di 45 mm in x",
                       ok_ed and dx is not None and abs(dx - 45.0) < 1e-3, f"dx {dx}" if ok_ed else text_ed[:80])
                ok_ev, text_ev, d_ev = await c.call("edit_explode_step", step_index=0, reverse=True)
                pos = ((d_ev or {}).get("exploded_positions") or {}).get("asm3_pin-1") or {}
                xb, xa = (pos.get("before_mm") or [None])[0], (pos.get("after_mm") or [None])[0]
                record("edit_explode_step: verso invertito, x esploso del perno da +75 a -75 mm (inserito a x=0)",
                       ok_ev and xb is not None and abs(xb - 75.0) < 1e-3 and abs(xa + 75.0) < 1e-3, f"{xb} -> {xa}")
                ok_lv, _, d_lv = await c.call("list_exploded_views")
                st0 = ((d_lv or {}).get("steps") or [{}])[0]
                record("list_exploded_views rilegge 75 mm e verso invertito", ok_lv and st0.get("distance_mm") == 75.0 and st0.get("reverse") is True,
                       f"{st0.get('distance_mm')} mm, reverse {st0.get('reverse')}")
                ok_bad, text_bad, _ = await c.call("edit_explode_step", step_index=5, distance=10)
                record("edit_explode_step: indice inesistente rifiutato", not ok_bad, text_bad[:80])
                ok_z, text_z, _ = await c.call("edit_explode_step", step_index=0, distance=0)
                record("edit_explode_step: distanza 0 rifiutata", not ok_z, text_z[:80])

                # 10. check_mate_redundancy: perno coassiale (inserito a 0,0,0), concentrico + coincidente + coincidente uguale.
                # Attesi (misurati sopprimendo un accoppiamento alla volta): i due coincidenti ridondanti, il concentrico no;
                # perno con 1 grado di liberta' (rotazione attorno all'asse), 3 senza il concentrico.
                await c.call("close_document", discard=True)
                await c.call("create_new_assembly")
                await c.call("insert_component", file_path=str(PART_BOX), x=0, y=0, z=0, fixed=True)
                await c.call("insert_component", file_path=str(PART_PIN), x=0, y=0, z=0, fixed=False)
                F_CYL0 = {"component": "asm3_pin-1", "face": pt_on(mp, ax, mp[ax], 10, 0)}
                F_PEND0 = {"component": "asm3_pin-1", "face": pt_on(mp, ax, bb_pin["min"][ax], 0, 0)}
                F_PEND1 = {"component": "asm3_pin-1", "face": pt_on(mp, ax, bmax[ax], 0, 0)}   # dopo il coincidente
                _, _, d_m1 = await c.call("add_mate", mate_type="concentric", entity1=F_HOLE_B, entity2=F_CYL0)
                _, _, d_m2 = await c.call("add_mate", mate_type="coincident", entity1=F_TOP_B, entity2=F_PEND0)
                ok_m3, text_m3, d_m3 = await c.call("add_mate", mate_type="coincident", entity1=F_TOP_B, entity2=F_PEND1)
                record("add_mate (prep): coincidente ripetuto accettato da SolidWorks senza errori", ok_m3, text_m3[:80])
                n_conc, n_c1, n_c2 = ((d or {}).get("name") for d in (d_m1, d_m2, d_m3))
                ok_rd, text_rd, d_rd = await c.call("check_mate_redundancy")
                red = set((d_rd or {}).get("redundant_mates") or [])
                record("check_mate_redundancy: ridondanti = i due coincidenti, non il concentrico",
                       ok_rd and red == {n_c1, n_c2} and n_conc not in red, f"{sorted(red)} (attesi {n_c1}, {n_c2})" if ok_rd else text_rd[:80])
                gained = {t["name"]: t["dof_gained_when_suppressed"] for t in (d_rd or {}).get("tested", [])}
                record("check_mate_redundancy: perno 1 grado di liberta', 3 senza il concentrico",
                       ((d_rd or {}).get("base_dof") or {}).get("asm3_pin-1") == 1 and gained.get(n_conc, {}).get("asm3_pin-1") == [1, 3],
                       f"base {((d_rd or {}).get('base_dof') or {})}, senza concentrico {gained.get(n_conc)}")
                record("check_mate_redundancy: pose e accoppiamenti ripristinati",
                       (d_rd or {}).get("poses_restored") is True and not (d_rd or {}).get("still_suppressed"),
                       f"spostati {(d_rd or {}).get('moved_mm')}")
                ok_ds, text_ds, _ = await c.call("add_mate", mate_type="distance", entity1=F_TOP_B, entity2=F_PEND1, distance=5)
                record("add_mate: distanza 5 mm in conflitto con il coincidente segnalata in errore", not ok_ds, text_ds[:90])
                ok_r2, text_r2, d_r2 = await c.call("check_mate_redundancy")
                conf = (d_r2 or {}).get("conflicting_mates") or []
                record("check_mate_redundancy: 1 accoppiamento in conflitto (distanza, codice 47)",
                       ok_r2 and len(conf) == 1 and conf[0].get("type") == "distance" and conf[0].get("error_code") == 47, str(conf)[:100])

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
