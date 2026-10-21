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
PDF_LAYERS_OUT = OUT / "test_layers_live.pdf"

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
                # Setup: Model Part for Drawings
                # =============================================================
                if not PART.exists():
                    await c.call("create_new_part")
                    await c.call("create_sketch", plane="Front")
                    await c.call("draw_rectangle", x1=-50, y1=-30, x2=50, y2=30, unit="mm")
                    await c.call("extrude_sketch", depth=20, unit="mm")
                    await c.call("save_document", filepath=str(PART), overwrite=True)

                # =============================================================
                # Test Suite Drawings 2 Live
                # =============================================================
                print("\n--- Test Drawings 2 Tools Live ---")
                ok_drw, text_drw, _ = await c.call("create_drawing", model_path=str(PART), paper_size="A3", add_views=True)
                record("create_drawing", ok_drw, text_drw[:120])

                # 1. Sheet format editing & reload
                ok_ef, _, _ = await c.call("edit_sheet_format")
                record("edit_sheet_format", ok_ef)

                ok_xf, _, _ = await c.call("exit_sheet_format")
                record("exit_sheet_format", ok_xf)

                ok_rf, _, _ = await c.call("reload_sheet_format")
                record("reload_sheet_format", ok_rf)

                # 2. Views: Relative, Predefined, Aligned, Half Section
                ok_rv, _, _ = await c.call("add_relative_view", x=120.0, y=120.0)
                record("add_relative_view", ok_rv)

                ok_pv, _, _ = await c.call("add_predefined_view", view_name="Front", x=100.0, y=100.0, orientation="front")
                record("add_predefined_view", ok_pv)

                ok_as, _, _ = await c.call("add_aligned_section_view", x1=50.0, y1=50.0, x2=100.0, y2=100.0,
                                           x3=150.0, y3=100.0, view_x=220.0, view_y=160.0)
                record("add_aligned_section_view", ok_as)

                ok_hs, _, _ = await c.call("add_half_section_view", center_x=100.0, center_y=100.0, direction="right",
                                           view_x=220.0, view_y=160.0)
                record("add_half_section_view", ok_hs)

                # 3. Special Views: Flat pattern, Unfolded, Alternate position, Exploded
                ok_fp, _, _ = await c.call("add_flat_pattern_drawing_view", x=150.0, y=150.0)
                record("add_flat_pattern_drawing_view", ok_fp)

                ok_uv, _, _ = await c.call("add_unfolded_view", x=160.0, y=160.0)
                record("add_unfolded_view", ok_uv)

                ok_ap, _, _ = await c.call("add_alternate_position_view", view_name="Drawing View1")
                record("add_alternate_position_view", ok_ap)

                ok_ex, _, _ = await c.call("show_exploded_drawing_view", view_name="Drawing View1", exploded=True)
                record("show_exploded_drawing_view", ok_ex)

                # 4. View Operations: Rotate & Align
                ok_rot, _, _ = await c.call("rotate_drawing_view", view_name="Drawing View1", angle_deg=90.0)
                record("rotate_drawing_view", ok_rot)

                ok_alg, _, _ = await c.call("align_drawing_views", view_to_align="Drawing View1", base_view="Drawing View2", alignment="horizontal")
                record("align_drawing_views", ok_alg)

                # 5. Dimensions: Ordinate, Chamfer, Hide/Show
                ok_ord, _, _ = await c.call("add_ordinate_dimension", origin_point=[50, 50], dimension_points=[[60, 50], [80, 50]])
                record("add_ordinate_dimension", ok_ord)

                ok_chm, _, _ = await c.call("add_chamfer_dimension", point_on_chamfer=[70, 70])
                record("add_chamfer_dimension", ok_chm)

                ok_hsd, _, _ = await c.call("hide_show_dimension", dimension_name="D1@Drawing View1", visible=False)
                record("hide_show_dimension", ok_hsd)

                # 6. Symbols: Weld & Edge ISO 13715
                ok_wld, _, _ = await c.call("add_weld_symbol", point=[100, 100], weld_type="fillet", size=5.0)
                record("add_weld_symbol", ok_wld)

                ok_edg, _, _ = await c.call("add_edge_chamfer_symbol", point=[80, 80], symbol_type="undercut")
                record("add_edge_chamfer_symbol", ok_edg)

                # 7. Tables: Revision, Cut List, General Grid
                ok_rev, _, _ = await c.call("add_revision_table", x=380.0, y=260.0, revision="A", description="Initial Release")
                record("add_revision_table", ok_rev)

                ok_wct, _, _ = await c.call("add_weldment_cut_list_table", x=60.0, y=240.0)
                record("add_weldment_cut_list_table", ok_wct)

                ok_tbl, _, _ = await c.call("add_general_table", rows=3, columns=3, x=150.0, y=80.0, title="Lista Dati")
                record("add_general_table", ok_tbl)

                # 8. Centerlines, Layers, Blocks & Layered PDF Export
                ok_cln, _, _ = await c.call("add_centerlines")
                record("add_centerlines", ok_cln)

                ok_lyr, _, _ = await c.call("create_drawing_layer", layer_name="Quote", color_rgb=[0, 120, 215], line_weight=0.35)
                record("create_drawing_layer", ok_lyr)

                ok_sly, _, _ = await c.call("set_entity_layer", layer_name="Quote", entity_type="annotation")
                record("set_entity_layer", ok_sly)

                ok_blk, _, _ = await c.call("insert_drawing_block", block_name="Logo", x=350.0, y=30.0)
                record("insert_drawing_block", ok_blk)

                ok_pdf, _, _ = await c.call("export_pdf_layers", filepath=str(PDF_LAYERS_OUT), overwrite=True)
                record("export_pdf_layers", ok_pdf)

                # Chiudi tavola
                await c.call("close_document", discard=True)

    finally:
        print("\nCleanup istanza dedicata...")
        cleanup(my_pid, elia_pids)

    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
