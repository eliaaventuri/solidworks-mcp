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

                # 2. Views: rifiuto dei tool non implementati
                ok_nim, text_nim, _ = await c.call("add_relative_view", x=120.0, y=120.0)
                record("add_relative_view: rifiutato perche' non implementato", (not ok_nim) and "non e' implementato" in text_nim, text_nim[:80])

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

    finally:
        print("\nCleanup istanza dedicata...")
        cleanup(my_pid, elia_pids)

    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
