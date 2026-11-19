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

                # 3. Text along curve & segment entity
                ok_line, _, data_line = await c.call("draw_line", x1=0, y1=-20, x2=50, y2=-20)
                line_id = data_line.get("entity_id")
                ok_seg, _, data_seg = await c.call("segment_sketch_entity", entity=line_id, count=4, is_segments=False)
                record("segment_sketch_entity: 4 parti = 3 punti interni (revisione 2026-11-12)", ok_seg and data_seg.get("created_points_count") == 3,
                       f"count: {data_seg.get('count')}, punti creati: {data_seg.get('created_points_count')}")

                ok_txt, text_txt, d_txt = await c.call("draw_sketch_text_along_curve", text="SOLIDWORKS-MCP", height=4,
                                                       curve_entity=line_id)
                record("draw_sketch_text_along_curve: altezza 4 mm riletta", ok_txt and abs(((d_txt or {}).get("height_mm") or 0) - 4) < 1e-4
                       and (d_txt or {}).get("height_mm") is not None, text_txt[:100])

                # 4. Diagnose sketch relations
                ok_nim, text_nim, _ = await c.call("diagnose_sketch_relations")
                record("diagnose_sketch_relations: rifiutato perche' non implementato", (not ok_nim) and "non e' implementato" in text_nim, text_nim[:80])

                # 5. Make sketch chain
                ok_l2, _, data_l2 = await c.call("draw_line", x1=50, y1=-20, x2=50, y2=-40)
                ok_chn, _, data_chn = await c.call("make_sketch_chain", entities=[line_id, data_l2.get("entity_id")])
                record("make_sketch_chain", ok_l2 and ok_chn and data_chn.get("chain_created") is True and data_chn.get("segment_count") == 2,
                       f"segment_count: {data_chn.get('segment_count')}")

                # Chiudi lo schizzo ed estrudi
                await c.call("close_sketch")
                await c.call("create_sketch", plane="Front")
                await c.call("draw_circle", x=0, y=0, radius=30)
                await c.call("extrude_boss", depth=60)
                await c.call("save_document", filepath=str(PART_SK4), overwrite=True)

                # 6. Intersection curve & silhouette
                # Apri schizzo su piano Top che taglia il cilindro a metà
                await c.call("create_sketch", plane="Top")
                ok_int, text_int, _ = await c.call("insert_intersection_curve")
                record("insert_intersection_curve: rifiutato perche' non implementato", (not ok_int) and "non e' implementato" in text_int, text_int[:80])

                ok_sil, text_sil, _ = await c.call("insert_silhouette_entities")
                record("insert_silhouette_entities: rifiutato perche' non implementato", (not ok_sil) and "non e' implementato" in text_sil, text_sil[:80])
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
