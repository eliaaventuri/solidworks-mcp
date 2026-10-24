"""
Live test for Lotto DISEGNI 2 tools against dedicated hidden SolidWorks instance.
"""

import os
import sys
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup, EXPECTED_TOOLS

PART = OUT / "test_drawings2_part.SLDPRT"
SM_PART = OUT / "test_drawings2_sheetmetal.SLDPRT"
HOLE_PART = OUT / "test_drawings2_hole.SLDPRT"
CHAMFER_PART = OUT / "test_drawings2_smusso.SLDPRT"     # blocco 20x100x60 con smusso 5 mm (rifatto a ogni giro)
FLANGE_PART = OUT / "test_drawings2_flangia.SLDPRT"     # disco D100 x 20, foro D30, 3 fori D10 a 120 gradi su r=35
ASM = OUT / "test_drawings2_asm.SLDASM"
PDF_LAYERS_OUT = OUT / "test_layers_live.pdf"
EXPECT_BLUE = 120 * 256 + 215 * 65536  # COLORREF di RGB(0, 120, 215)

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
                # Setup: pezzi e assieme per le tavole (ogni caso ha il suo modello)
                # =============================================================
                if not PART.exists():
                    await c.call("create_new_part")
                    await c.call("create_sketch", plane="Front")
                    await c.call("draw_rectangle", x1=-50, y1=-30, x2=50, y2=30, unit="mm")
                    await c.call("extrude_sketch", depth=20, unit="mm")
                    await c.call("save_document", filepath=str(PART), overwrite=True)
                if not SM_PART.exists():
                    await c.call("create_new_part")
                    await c.call("create_sketch", plane="Front")
                    await c.call("draw_rectangle", x1=0, y1=0, x2=50, y2=30, unit="mm")
                    await c.call("sm_base_flange", thickness=2, bend_radius=2, k_factor=0.5)
                    await c.call("save_document", filepath=str(SM_PART), overwrite=True)
                if not HOLE_PART.exists():
                    await c.call("create_new_part")
                    await c.call("create_sketch", plane="Front")
                    await c.call("draw_rectangle", x1=-50, y1=-30, x2=50, y2=30, unit="mm")
                    await c.call("extrude_sketch", depth=10, unit="mm")
                    await c.call("create_sketch_on_face", x=20, y=10, z=10, unit="mm")
                    await c.call("draw_circle", x=0, y=0, radius=8, unit="mm")
                    await c.call("cut_extrude", depth=10, through_all=True, unit="mm")
                    await c.call("save_document", filepath=str(HOLE_PART), overwrite=True)
                await c.call("create_new_assembly")
                await c.call("insert_component", file_path=str(PART), x=0, y=0, z=0, fixed=True)
                await c.call("insert_component", file_path=str(PART), x=120, y=0, z=0)
                _, _, dasm = await c.call("list_components")
                comp_names = [x["name"] for x in dasm.get("components", [])]
                ok_ex_stp, _, _ = await c.call("create_exploded_view", steps=[{"components": [comp_names[-1]], "direction": "x", "distance": 60}])
                record("setup: assieme con vista esplosa", ok_ex_stp and len(comp_names) == 2, f"componenti {comp_names}")
                await c.call("save_document", filepath=str(ASM), overwrite=True)

                # =============================================================
                # Test Suite Drawings 2 Live
                # =============================================================
                print("\n--- Test Drawings 2 Tools Live ---")
                ok_drw, text_drw, _ = await c.call("create_drawing", model_path=str(PART), paper_size="A3", add_views=True)
                record("create_drawing", ok_drw, text_drw[:120])
                _, _, dv = await c.call("list_drawing_views")
                names = [x["name"] for x in dv.get("views", [])]
                record("setup: almeno due viste nel foglio", len(names) >= 2, f"viste {names}")

                # 1. Sheet format editing & reload
                ok_ef, _, _ = await c.call("edit_sheet_format")
                record("edit_sheet_format", ok_ef)

                ok_xf, _, _ = await c.call("exit_sheet_format")
                record("exit_sheet_format", ok_xf)

                ok_rf, _, _ = await c.call("reload_sheet_format")
                record("reload_sheet_format", ok_rf)

                # 4. View Operations: Rotate & Align (nomi letti da list_drawing_views)
                ok_rot, _, d_rot = await c.call("rotate_drawing_view", view_name=names[0], angle_deg=90.0)
                rot_read = d_rot.get("angle_read_deg", -1.0) if ok_rot else -1.0
                record("rotate_drawing_view", ok_rot and abs(rot_read - 90.0) < 0.01, f"angolo letto {rot_read} (atteso 90)")

                ok_alg, text_alg, _ = await c.call("align_drawing_views", view_to_align=names[2], base_view=names[0], alignment="horizontal")
                record("align_drawing_views: rifiutato perche' non implementato", (not ok_alg) and "non e' implementato" in text_alg, text_alg[:80])

                # 7. Tables: Revision, General Grid
                ok_rev, _, d_rev = await c.call("add_revision_table", x=380.0, y=260.0, revision="A", description="Initial Release")
                record("add_revision_table", ok_rev and d_rev.get("revision_row") == "A", f"riga letta {d_rev.get('revision_row')}")

                ok_tbl, _, _ = await c.call("add_general_table", rows=3, columns=3, x=150.0, y=80.0, title="Lista Dati")
                record("add_general_table", ok_tbl)

                # 8. Layers, Blocks & Layered PDF Export
                ok_lyr, _, d_lyr = await c.call("create_drawing_layer", layer_name="Quote", color_rgb=[0, 120, 215], line_weight=0.35)
                record("create_drawing_layer", ok_lyr and d_lyr.get("color_read") == EXPECT_BLUE, f"colore letto {d_lyr.get('color_read')} (atteso {EXPECT_BLUE})")

                # blocco 2D: nessun file .sldblk creabile con i tool attivi (save_sketch_block_to_file e' segnaposto)
                ok_blk, text_blk, _ = await c.call("insert_drawing_block", block_name="Logo", x=350.0, y=30.0)
                record("insert_drawing_block: rifiutato perche' non implementato", (not ok_blk) and "non e' implementato" in text_blk, text_blk[:80])

                ok_pdf, _, _ = await c.call("export_pdf_layers", filepath=str(PDF_LAYERS_OUT), overwrite=True)
                pdf_size = os.path.getsize(PDF_LAYERS_OUT) if PDF_LAYERS_OUT.exists() else 0
                record("export_pdf_layers", ok_pdf and pdf_size > 0, f"{pdf_size} byte")

                # Chiudi tavola
                await c.call("close_document", discard=True)

                # 3. Vista lamiera spianata: pezzo a lamiera salvato
                await c.call("create_drawing", model_path=str(SM_PART), paper_size="A3", add_views=True)
                _, _, dsm0 = await c.call("list_drawing_views")
                n_before = len(dsm0.get("views", []))
                ok_fp, _, _ = await c.call("add_flat_pattern_drawing_view", model_path=str(SM_PART), x=150.0, y=150.0)
                _, _, dsm1 = await c.call("list_drawing_views")
                n_after = len(dsm1.get("views", []))
                record("add_flat_pattern_drawing_view", ok_fp and n_after == n_before + 1, f"viste {n_before} -> {n_after}")
                await c.call("close_document", discard=True)

                # 3b. Vista esplosa dell'assieme
                await c.call("create_drawing", model_path=str(ASM), paper_size="A3", add_views=True)
                _, _, dea = await c.call("list_drawing_views")
                asm_names = [x["name"] for x in dea.get("views", [])]
                ok_ex, _, d_ex = await c.call("show_exploded_drawing_view", view_name=asm_names[0], exploded=True)
                record("show_exploded_drawing_view", ok_ex and d_ex.get("exploded") is True, f"esploso letto {d_ex.get('exploded')}")
                await c.call("close_document", discard=True)

                # 8b. Linee d'asse: tool da nascondere (AutoInsertCenterMarks risponde True, ma i segni inseriti
                # non si leggono con GetFirstCenterMark2 / GetFirstCenterLine: nessuna misura possibile)
                await c.call("create_drawing", model_path=str(HOLE_PART), paper_size="A3", add_views=True)
                ok_cln, text_cln, _ = await c.call("add_centerlines")
                record("add_centerlines: rifiutato perche' non implementato", (not ok_cln) and "non e' implementato" in text_cln, text_cln[:80])
                await c.call("close_document", discard=True)

                # 9. Quote ordinate, quota di smusso, quote nascoste, vista relativa (blocco con smusso).
                # Il piano Front del modello di questo SolidWorks e' il piano YZ: il blocco va da x 0..20, y -50..50, z -30..30;
                # nella vista frontale l'asse y del modello e' orizzontale e z verticale (punti in coordinate del modello).
                await c.call("create_new_part")
                await c.call("create_sketch", plane="Front")
                await c.call("draw_rectangle", x1=-50, y1=-30, x2=50, y2=30, unit="mm")
                await c.call("extrude_boss", depth=20)
                _, _, dbb = await c.call("get_bounding_box")
                ok_ch, text_ch, _ = await c.call("chamfer_edges", distance=5, edge_points=[[10, 50, 30]])
                record("setup: blocco 20x100x60 con smusso 5 mm", ok_ch and dbb.get("size") == [20.0, 100.0, 60.0],
                       f"ingombro {dbb.get('size')}; {text_ch[:50]}")
                await c.call("save_document", filepath=str(CHAMFER_PART), overwrite=True)
                await c.call("create_drawing", model_path=str(CHAMFER_PART), paper_size="A3", add_views=True)
                _, _, dvc = await c.call("list_drawing_views")
                v_front = dvc["views"][0]["name"]
                ok_or, text_or, d_or = await c.call("add_ordinate_dimension", origin_point=[20, -50, 0], dimension_points=[[20, 50, 0]],
                                                    view_name=v_front)
                vals = [o["value_mm"] for o in (d_or or {}).get("ordinates", [])]
                record("add_ordinate_dimension orizzontale: 0 e 100 mm (larghezza del blocco)", ok_or and vals == [0.0, 100.0],
                       str(vals) if ok_or else text_or[:80])
                ok_ov, text_ov, d_ov = await c.call("add_ordinate_dimension", origin_point=[20, 0, -30], dimension_points=[[20, 0, 30]],
                                                    view_name=v_front, direction="vertical")
                vals = [o["value_mm"] for o in (d_ov or {}).get("ordinates", [])]
                record("add_ordinate_dimension verticale: 0 e 60 mm (altezza del blocco)", ok_ov and vals == [0.0, 60.0],
                       str(vals) if ok_ov else text_ov[:80])
                ok_op, text_op, _ = await c.call("add_ordinate_dimension", origin_point=[20, -50, 0], dimension_points=[[20, 0, 30]],
                                                 view_name=v_front)
                record("add_ordinate_dimension: spigolo parallelo alla direzione rifiutato", not ok_op, text_op[:80])
                ok_cd, text_cd, d_cd = await c.call("add_chamfer_dimension", point_on_chamfer=[20, 47.5, 27.5], reference_point=[20, 0, 30],
                                                    view_name=v_front)
                ctext = (d_cd or {}).get("text", "")
                record("add_chamfer_dimension: testo letto 5,00 X 45", ok_cd and ctext.replace(",", ".").startswith("5.00") and "45" in ctext,
                       ctext if ok_cd else text_cd[:80])
                ok_cn, text_cn, _ = await c.call("add_chamfer_dimension", point_on_chamfer=[20, 0, -30], reference_point=[20, -50, 0],
                                                 view_name=v_front)
                record("add_chamfer_dimension: spigolo senza smusso rifiutato", not ok_cn, text_cn[:80])
                _, _, dl0 = await c.call("list_drawing_dimensions")
                n0 = len(dl0.get("dimensions", []))
                dname = dl0["dimensions"][0]["name"] if n0 else "?"
                ok_hd, text_hd, _ = await c.call("hide_show_dimension", dimension_name=dname, visible=False)
                _, _, dl1 = await c.call("list_drawing_dimensions")
                ok_sh, text_sh, _ = await c.call("hide_show_dimension", dimension_name=dname, visible=True)
                _, _, dl2 = await c.call("list_drawing_dimensions")
                n1, n2 = len(dl1.get("dimensions", [])), len(dl2.get("dimensions", []))
                record("hide_show_dimension: nascosta e rimostrata (quote elencate n -> n-1 -> n)",
                       ok_hd and ok_sh and n1 == n0 - 1 and n2 == n0, f"{dname}: {n0} -> {n1} -> {n2}")
                ok_hx, text_hx, _ = await c.call("hide_show_dimension", dimension_name="ZZ99", visible=False)
                record("hide_show_dimension: quota inesistente rifiutata", not ok_hx, text_hx[:80])
                ok_rv, text_rv, d_rv = await c.call("add_relative_view", front_face_point=[0, 10, 10], right_face_point=[10, 0, 30],
                                                    x=330, y=120)
                record("add_relative_view: faccia x=0 verso chi guarda, faccia z=30 a destra (normali proiettate)",
                       ok_rv and (d_rv or {}).get("front_normal_in_view") == [0.0, 0.0, 1.0]
                       and (d_rv or {}).get("right_normal_in_view") == [1.0, 0.0, 0.0],
                       f"{(d_rv or {}).get('front_normal_in_view')} {(d_rv or {}).get('right_normal_in_view')}" if ok_rv else text_rv[:80])
                ok_rc, text_rc, _ = await c.call("add_relative_view", front_face_point=[10, 47.5, 27.5], right_face_point=[10, 0, 30],
                                                 x=330, y=60)
                record("add_relative_view: facce non perpendicolari (smusso a 45 gradi) -> errore", not ok_rc, text_rc[:80])
                await c.call("close_document", discard=True)

                # 10. Sezione allineata su una flangia: il tratto inclinato (a 210 gradi) va RUOTATO nel piano di taglio, quindi
                # la sezione e' lunga 50 + 50 = 100 mm (una sezione solo proiettata sarebbe 50 + 50 sin 30 = 75 mm).
                await c.call("create_new_part")
                await c.call("create_sketch", plane="Front")
                await c.call("draw_circle", x=0, y=0, radius=50)
                await c.call("draw_circle", x=0, y=0, radius=15)
                for (hx, hy) in ((0, 35), (-30.311, -17.5), (30.311, -17.5)):
                    await c.call("draw_circle", x=hx, y=hy, radius=5)
                await c.call("extrude_boss", depth=20)
                await c.call("save_document", filepath=str(FLANGE_PART), overwrite=True)
                await c.call("create_drawing", model_path=str(FLANGE_PART), paper_size="A3", add_views=False)
                _, _, dmv = await c.call("add_model_view", orientation="front", x=120, y=180)
                ok_al, text_al, d_al = await c.call("add_aligned_section_view", x1=120, y1=240, x2=120, y2=180, x3=68, y3=150,
                                                    parent_view=dmv.get("name"), label="A")
                w, h = (d_al or {}).get("width_mm", 0), (d_al or {}).get("height_mm", 0)
                length = h - (w - 20.0)       # il contorno della vista ha lo stesso margine sui due lati (spessore 20)
                record("add_aligned_section_view: sezione lunga 100 mm (tratto inclinato ruotato)", ok_al and abs(length - 100.0) < 0.5,
                       f"{length:.2f} mm (contorno {w} x {h})" if ok_al else text_al[:80])
                ok_ab, text_ab, _ = await c.call("add_aligned_section_view", x1=180, y1=180, x2=120, y2=180, x3=120, y3=240,
                                                 parent_view=dmv.get("name"), label="B")
                record("add_aligned_section_view: tre punti senza tratto inclinato rifiutati", not ok_ab, text_ab[:80])
                await c.call("close_document", discard=True)

    finally:
        print("\nCleanup istanza dedicata...")
        cleanup(my_pid, elia_pids)

    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
