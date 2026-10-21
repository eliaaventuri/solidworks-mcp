"""
Live test for Lotto Sketch 5 tools against dedicated hidden SolidWorks instance.
"""

import os
import sys
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup, EXPECTED_TOOLS

PART_SK5 = OUT / "sketch5_test.SLDPRT"
BLK_PATH = OUT / "test_block.sldblk"

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
                # Test Suite Sketch 5 Live
                # =============================================================
                print("\n--- Test Sketch 5 Tools ---")
                ok, _, _ = await c.call("create_new_part")
                record("create_new_part", ok)

                # 1. Performance mode
                ok_prf, _, data_prf = await c.call("set_sketch_performance_mode", add_to_db=False, auto_solve=True, auto_inference=True)
                record("set_sketch_performance_mode", ok_prf, f"auto_solve: {data_prf.get('auto_solve')}")

                # 2. Spline Operations: Create, Insert Point, Relax, Simplify, Edit Handle, Delete Point
                await c.call("create_sketch", plane="Front")
                await c.call("draw_spline", points=[[0, 0], [20, 15], [40, -10], [60, 20]])

                ok_ins, _, data_ins = await c.call("insert_spline_point", x=30, y=5)
                record("insert_spline_point", ok_ins)

                ok_rel, _, _ = await c.call("relax_sketch_spline")
                record("relax_sketch_spline", ok_rel)

                ok_smp, _, _ = await c.call("simplify_sketch_spline", tolerance=0.1)
                record("simplify_sketch_spline", ok_smp)

                ok_hnd, _, data_hnd = await c.call("edit_spline_handle", point_index=0, magnitude=1.5)
                record("edit_spline_handle", ok_hnd, f"edited: {data_hnd.get('edited')}")

                ok_del, _, _ = await c.call("delete_spline_point", point_index=1)
                record("delete_spline_point", ok_del)

                # 3. Pulley-Belt Feature & Allowed Relations
                await c.call("draw_circle", x=0, y=50, radius=10)
                await c.call("draw_circle", x=60, y=50, radius=15)

                ok_blt, _, data_blt = await c.call("create_sketch_belt", thickness=3.0)
                record("create_sketch_belt", ok_blt, f"pulleys: {data_blt.get('pulleys_count')}")

                ok_alw, _, data_alw = await c.call("get_allowed_relations")
                record("get_allowed_relations", ok_alw, f"allowed: {len(data_alw.get('allowed_relations', []))}")

                # 4. Relations: Suppress & Delete All
                ok_sup, _, data_sup = await c.call("suppress_sketch_relation", relation_index=0, suppress=True)
                record("suppress_sketch_relation", ok_sup, f"suppressed: {data_sup.get('suppressed')}")

                # 5. Sketch Regions & Merge Points
                # Disegna un rettangolo che interseca il cerchio per formare regioni multiple
                await c.call("draw_rectangle", x1=-5, y1=45, x2=25, y2=55)
                ok_reg, _, data_reg = await c.call("list_sketch_regions")
                record("list_sketch_regions", ok_reg, f"regions: {data_reg.get('regions_count')}")

                ok_mrg, _, _ = await c.call("merge_sketch_points", distance=0.01)
                record("merge_sketch_points", ok_mrg)

                # Delete all relations
                ok_dar, _, _ = await c.call("delete_all_sketch_relations")
                record("delete_all_sketch_relations", ok_dar)

                await c.call("close_sketch")

                # 6. 3D Sketch & Rotate/Copy 3D
                await c.call("create_3d_sketch")
                await c.call("draw_3d_line", x1=0, y1=0, z1=0, x2=50, y2=0, z2=0)
                ok_r3d, _, data_r3d = await c.call("rotate_copy_3d_sketch", angle_deg=45.0, copy=True, num_copies=2, vector_z=1.0)
                record("rotate_copy_3d_sketch", ok_r3d, f"copies: {data_r3d.get('num_copies')}")
                await c.call("close_sketch")

                # 7. Block Export
                ok_blk, _, _ = await c.call("save_sketch_block_to_file", block_name="Block1", filepath=str(BLK_PATH), overwrite=True)
                record("save_sketch_block_to_file", ok_blk)

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
