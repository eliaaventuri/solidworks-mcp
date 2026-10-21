"""
Live test for Lotto Sketch 4 tools against dedicated hidden SolidWorks instance.
"""

import os
import sys
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup, EXPECTED_TOOLS

PART_SK4 = OUT / "sketch4_test.SLDPRT"

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
                # Test Suite Sketch 4 Live
                # =============================================================
                print("\n--- Test Sketch 4 Tools ---")
                ok, _, _ = await c.call("create_new_part")
                record("create_new_part", ok)

                # 1. 3-Point Arc Slot
                await c.call("create_sketch", plane="Front")
                ok_slot, text_slot, data_slot = await c.call("draw_3point_arc_slot",
                    x1=0, y1=0, x2=40, y2=0, x3=20, y3=10, width=6
                )
                record("draw_3point_arc_slot", ok_slot, f"slot_created: {data_slot.get('slot_created')}")

                # 2. Curvature combs & analysis on spline
                await c.call("draw_spline", points=[[0, 20], [20, 35], [40, 20], [60, 40]])
                ok_curv, _, data_curv = await c.call("show_sketch_curvature", scale=15, density=30, visible=True)
                record("show_sketch_curvature", ok_curv, f"visible: {data_curv.get('visible')}")

                ok_ana, text_ana, data_ana = await c.call("get_spline_curvature_analysis")
                record("get_spline_curvature_analysis", ok_ana, f"min_radius: {data_ana.get('min_radius_mm')} text: {text_ana[:120]}")

                # 3. Text along curve & segment entity
                await c.call("draw_line", x1=0, y1=-20, x2=50, y2=-20)
                ok_seg, _, data_seg = await c.call("segment_sketch_entity", count=4, is_segments=False)
                record("segment_sketch_entity", ok_seg, f"count: {data_seg.get('count')}")

                ok_txt, _, _ = await c.call("draw_sketch_text_along_curve", text="SOLIDWORKS-MCP", height=4)
                record("draw_sketch_text_along_curve", ok_txt)

                # 4. Diagnose sketch relations
                ok_diag, _, data_diag = await c.call("diagnose_sketch_relations")
                record("diagnose_sketch_relations", ok_diag, f"status: {data_diag.get('sketch_status')}")

                # 5. Make sketch chain
                ok_chn, _, data_chn = await c.call("make_sketch_chain")
                record("make_sketch_chain", ok_chn)

                # Chiudi lo schizzo ed estrudi
                await c.call("close_sketch")
                await c.call("create_sketch", plane="Front")
                await c.call("draw_circle", x=0, y=0, radius=30)
                await c.call("extrude_boss", depth=60)
                await c.call("save_document", filepath=str(PART_SK4), overwrite=True)

                # 6. Intersection curve & silhouette
                # Apri schizzo su piano Top che taglia il cilindro a metà
                await c.call("create_sketch", plane="Top")
                ok_int, text_int, data_int = await c.call("insert_intersection_curve")
                record("insert_intersection_curve", ok_int, f"added: {data_int.get('added_segments_count')}")

                ok_sil, text_sil, data_sil = await c.call("insert_silhouette_entities")
                record("insert_silhouette_entities", ok_sil, f"added: {data_sil.get('added_segments_count')}")
                await c.call("close_sketch")

                # 7. 3D Parametric Equation Curve
                ok_eq3d, text_eq, data_eq = await c.call("draw_equation_curve_3d",
                    x_expression="15*cos(t)",
                    y_expression="15*sin(t)",
                    z_expression="2*t",
                    start=0.0,
                    end=12.566,
                    samples=40
                )
                record("draw_equation_curve_3d", ok_eq3d, f"samples: {data_eq.get('samples_count')}")
                await c.call("close_sketch")

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
