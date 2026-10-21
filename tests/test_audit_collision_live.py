"""
Live test for audit_drawing and detect_collisions tools.
Runs on dedicated hidden SolidWorks instance.
"""

import os
import sys
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup, EXPECTED_TOOLS

PART_BOX = OUT / "box_part.SLDPRT"
PART_PIN = OUT / "pin_part.SLDPRT"
ASM_TEST = OUT / "collision_test.SLDASM"

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
                # Test 1: audit_drawing
                # =============================================================
                print("\n--- Test audit_drawing ---")
                # 1.1 Crea parte box
                ok, _, _ = await c.call("create_new_part")
                await c.call("create_sketch", plane="Front")
                await c.call("draw_circle", x=0, y=0, radius=25)
                await c.call("extrude_boss", depth=50)
                await c.call("save_document", filepath=str(PART_BOX), overwrite=True)

                # 1.2 Crea disegno dalla parte
                ok_drw, text_drw, drw_data = await c.call("create_drawing", model_path=str(PART_BOX), paper_size="A3", add_views=True, overwrite=True)
                record("create_drawing", ok_drw, text_drw[:120])

                # 1.3 Esegui audit_drawing sul foglio attivo
                ok_audit, text_audit, audit_data = await c.call("audit_drawing")
                record("audit_drawing: execution", ok_audit, f"Status: {audit_data.get('status')} score {audit_data.get('score')}")
                checks = audit_data.get("checks", {})
                record("audit_drawing: title block check", "title_block" in checks and checks["title_block"].get("has_format") is not None)
                record("audit_drawing: views count", checks.get("views", {}).get("count", 0) > 0, f"Views: {checks.get('views', {}).get('count')}")
                record("audit_drawing: dimensions check", "dimensions" in checks)

                await c.call("close_document", discard=True)
                await c.call("close_document", discard=True)

                # =============================================================
                # Test 2: detect_collisions
                # =============================================================
                print("\n--- Test detect_collisions ---")
                # 2.1 Crea la seconda parte (perno)
                ok, _, _ = await c.call("create_new_part")
                await c.call("create_sketch", plane="Front")
                await c.call("draw_circle", x=0, y=0, radius=10)
                await c.call("extrude_boss", depth=80)
                await c.call("save_document", filepath=str(PART_PIN), overwrite=True)
                await c.call("close_document", discard=True)

                # 2.2 Crea un assieme
                ok_asm, _, _ = await c.call("create_new_assembly")
                record("create_new_assembly", ok_asm)

                # Inserisci box_part fisso a (0, 0, 0)
                ok_ins1, _, _ = await c.call("insert_component", file_path=str(PART_BOX), x=0, y=0, z=0, fixed=True)
                record("insert_component box", ok_ins1)

                # Inserisci pin_part mobile a (0, 0, 100) (non interferente inizialmente)
                ok_ins2, _, _ = await c.call("insert_component", file_path=str(PART_PIN), x=0, y=0, z=100, fixed=False)
                record("insert_component pin", ok_ins2)

                # Salva l'assieme prima di testare interferenze
                await c.call("save_document", filepath=str(ASM_TEST), overwrite=True)

                # 2.3 Collisione Statica (a z=100 non c'e' collisione)
                ok_stat1, text_s, data_stat1 = await c.call("detect_collisions")
                record("detect_collisions (static, no collision)", ok_stat1 and not data_stat1.get("collision_detected"), text_s[:100])

                # 2.4 Collisione Dinamica: muovi pin_part lungo Z verso l'origine (dz = -100 mm)
                # Al termine della corsa deve compenetrare il box_part!
                pin_comp_name = "pin_part-1"
                ok_dyn, text_dyn, data_dyn = await c.call("detect_collisions",
                    moving_component=pin_comp_name,
                    dx=0, dy=0, dz=-100,
                    steps=10,
                    stop_on_collision=True
                )
                record("detect_collisions (dynamic trajectory)", ok_dyn and data_dyn.get("mode") == "dynamic",
                       f"Collision detected: {data_dyn.get('collision_detected')}, step: {data_dyn.get('first_collision_step')}")
                record("detect_collisions: initial pose restored", data_dyn.get("initial_pose_restored") is True)

                # Chiudi assieme
                await c.call("close_document", discard=True)

    finally:
        print("\nCleanup istanza dedicata...")
        cleanup(my_pid, elia_pids)

    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} PASS")
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
