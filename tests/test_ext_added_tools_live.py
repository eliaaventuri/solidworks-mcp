"""
Test live per i tool aggiunti da 'Tool da aggiungere.rtf' (sketch3, features3, surfaces2, sheetmetal2, assembly2, selection).
Gira SOLO su istanza SolidWorks DEDICATA (SW_MCP_INSTANCE=dedicated).
Alla fine si chiude SOLO il PID dell'istanza del test, lasciando l'eventuale istanza dell'utente intatta.
"""

import os
import sys
import asyncio
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.live_common import PYTHON, SERVER, sw_pids, Client, cleanup

RESULTS = []


def record(tool, ok, note=""):
    RESULTS.append((tool, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {tool}  {note}"[:260])


async def run_tests():
    elia_pids = sw_pids()
    print(f"PID SolidWorks esistenti prima del test: {sorted(elia_pids)}")

    env = os.environ.copy()
    env["SW_MCP_INSTANCE"] = "dedicated"
    env["SW_MCP_ALLOW_PYTHON"] = "1"
    server_params = StdioServerParameters(
        command=str(PYTHON),
        args=[str(SERVER)],
        env=env,
    )

    my_pid = None
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=120)) as session:
            await session.initialize()
            c = Client(session)

            # 1. Connessione
            ok, text, data = await c.call("connect_solidworks")
            record("connect_solidworks", ok, text[:70])
            my_pid = data.get("pid")
            print(f"PID del test collegato: {my_pid}")

            # 2. SELECTION & VIEWPORT: zoom_to_fit, set_view_orientation
            ok, text, _ = await c.call("create_new_part")
            record("create_new_part", ok, text[:70])

            ok, text, _ = await c.call("set_view_orientation", orientation="front")
            record("set_view_orientation (front)", ok, text[:70])

            ok, text, _ = await c.call("zoom_to_fit")
            record("zoom_to_fit", ok, text[:70])

            # 3. SKETCH 3: disegno entita' nuove
            ok, text, _ = await c.call("create_sketch", plane="Front")
            record("create_sketch", ok, text[:70])

            ok, text, _ = await c.call("draw_centerline", x1=0, y1=0, x2=0, y2=100)
            record("draw_centerline", ok, text[:70])

            ok, text, _ = await c.call("draw_midpoint_line", cx=50, cy=0, length=40, angle=0)
            record("draw_midpoint_line", ok, text[:70])

            ok, text, _ = await c.call("draw_3point_arc", x1=0, y1=0, x2=20, y2=20, x3=10, y3=30)
            record("draw_3point_arc", ok, text[:70])

            ok, text, _ = await c.call("draw_elliptical_arc", cx=100, cy=50, major_x=40, major_y=0, minor_r=20, start_angle=0, end_angle=180)
            record("draw_elliptical_arc", ok, text[:70])

            # Chiudi schizzo senza estrudere
            await c.call("close_document", discard=True)

            # 4. SKETCH FILLET & TRIM & ESTREMI
            ok, text, _ = await c.call("create_new_part")
            ok, text, _ = await c.call("create_sketch", plane="Front")
            await c.call("draw_line", x1=0, y1=0, x2=50, y2=0)
            await c.call("draw_line", x1=50, y1=0, x2=50, y2=50)

            ok, text, _ = await c.call("sketch_fillet", corner=[50, 0], radius=10)
            record("sketch_fillet", ok, text[:70])

            l1 = await c.call("draw_line", x1=20, y1=-20, x2=20, y2=30)
            l2 = await c.call("draw_line", x1=10, y1=10, x2=40, y2=10)
            id1 = l1[2].get("entity_id", "@20,20")
            id2 = l2[2].get("entity_id", "@30,10")
            ok, text, _ = await c.call("trim_sketch_corner", entity1=id1, entity2=id2)
            record("trim_sketch_corner", ok, text[:70])

            await c.call("close_document", discard=True)

            # 5. MODELLAZIONE 3D, TOPOLOGY QUERY & LABELED VIEWPORT IMAGE
            ok, text, _ = await c.call("create_new_part")
            ok, text, _ = await c.call("create_sketch", plane="Front")
            await c.call("draw_rectangle", x1=0, y1=0, x2=60, y2=40)
            ok, text, _ = await c.call("extrude_sketch", depth=30)
            record("extrude_sketch", ok, text[:70])

            # Query topologia (6 facce del parallelepipedo)
            ok, text, data = await c.call("query_topology_by_criteria", entity_type="face", surface_type="plane")
            face_count = data.get("count", 0)
            record("query_topology_by_criteria (face)", ok and face_count >= 6, f"Trovate {face_count} facce")

            # Selection manager
            ok, text, data = await c.call("get_active_selection")
            record("get_active_selection", ok, f"Selezioni attive: {data.get('count', 0)}")

            ok, text, _ = await c.call("clear_selection")
            record("clear_selection", ok, text[:70])

            # Select by ID (Front Plane)
            ok, text, _ = await c.call("select_by_id", name="Front Plane", object_type="PLANE")
            record("select_by_id (Front Plane)", ok, text[:70])

            # Select by Ray (punta verso la faccia del blocco a z=30)
            ok, text, data = await c.call("select_by_ray", origin=[30, 20, 50], direction=[0, 0, -1], radius=5, type_wanted=2)
            record("select_by_ray", ok, f"Colpito: {data.get('hit')}, totale sel: {data.get('total_selected')}")

            # Labeled viewport image
            img_path = str(ROOT / "test_output" / "labeled_model_test.png")
            ok, text, data = await c.call("export_labeled_viewport_image", filepath=img_path, max_labels=10, overwrite=True)
            record("export_labeled_viewport_image", ok and os.path.exists(img_path), f"File generato: {os.path.exists(img_path)}, etichette: {data.get('label_count')}")

            # 6. FEATURE: scale_body
            ok, text, _ = await c.call("scale_body", factor=1.5)
            record("scale_body", ok, text[:70])

            await c.call("close_document", discard=True)

    print("\n--- PULIZIA ---")
    cleanup(my_pid, elia_pids)

    passed = sum(1 for _, res, _ in RESULTS if res == "PASS")
    total = len(RESULTS)
    print(f"\nRiepilogo test live aggiunti: {passed}/{total} PASS")
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
