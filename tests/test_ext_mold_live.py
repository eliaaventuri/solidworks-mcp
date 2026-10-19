"""
Test live del lotto STAMPI (analisi dei sottosquadri) tramite il server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente non viene mai
toccata; alla fine si chiude solo il PID lanciato dal test.

  U1  undercut_analysis, blocco 40x30x20 (x 0..40, y -15..15, z 0..20) estratto lungo +Z -> 0 facce in sottosquadro
  U2  blocco con gola laterale (taglio 40 mm lungo X, y 5..15, z 8..12): volume 24000 -> 22400 (-1600 = 10x4x40, 0,5 %)
  U3  gola: 2 facce in sottosquadro (fondo z=8 e soffitto z=12), ciascuna di area 10x40 = 400 mm2 (1 %)
  U4  gola: stessa analisi lungo -Z -> 2 facce; lungo +Y (gola aperta su quel lato) -> 0 facce
  U5  direzione non valida ('diagonale') rifiutata (success=false)

Note: i tool di linea e superficie di divisione, chiusura e divisione maschio/matrice non sono esposti: le API Mold di
questa istanza non creano feature (vedi scripts_tmp/notes_mold.md).

Uso:  .venv\\Scripts\\python.exe tests\\test_ext_mold_live.py [U]
"""

import os
import sys
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, PYTHON, SERVER, sw_pids, Client, cleanup

RESULTS = []         # (nome, PASS/FAIL, nota)
TOL = 0.005          # 0,5 % sui volumi


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:260])


def near(got, exp, tol=TOL, absolute=None):
    if absolute is not None:
        return abs(got - exp) <= absolute
    return abs(got - exp) <= tol * max(abs(exp), 1e-9)


async def vol(c):
    ok, _, d = await c.call("get_mass_properties")
    return d.get("volume_mm3", 0.0) if ok else 0.0


async def discard_all(c):
    for _ in range(40):
        ok, _, d = await c.call("list_open_documents")
        docs = d.get("documents", []) if ok else []
        if not docs:
            return
        await c.call("close_document", discard=True, document=docs[0]["title"])


async def block_with_groove(c):
    """Blocco 40x30x20 (sketch Front 30 x 20 estruso 40 lungo X) con gola y 5..15, z 8..12 lungo tutto X."""
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-15, y1=0, x2=15, y2=20)
    await c.call("extrude_boss", depth=40)
    v_block = await vol(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=5, y1=8, x2=16, y2=12)
    await c.call("extrude_cut", depth=50, end_condition="blind", depth2=50, end_condition2="blind")
    return v_block, await vol(c)


async def u_undercut(c):
    await discard_all(c)
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-15, y1=0, x2=15, y2=20)
    await c.call("extrude_boss", depth=40)
    v_plain = await vol(c)
    ok, text, d = await c.call("undercut_analysis", direction="+Z")
    record("U1 blocco 40x30x20 lungo +Z: 0 facce in sottosquadro, volume 24000 mm3",
           ok and d.get("undercut_faces") == 0 and near(v_plain, 24000, absolute=0.5),
           f"{text[:90]} | volume {v_plain:.1f} mm3 | analizzate {d.get('faces_analyzed')}")
    await discard_all(c)

    v_block, v_groove = await block_with_groove(c)
    record("U2 gola 10x4x40 tolta: volume 24000 -> 22400 mm3 (0,5 %)",
           near(v_block, 24000) and near(v_groove, 22400),
           f"volume {v_block:.1f} -> {v_groove:.1f} mm3")

    ok, text, d = await c.call("undercut_analysis", direction="+Z")
    faces = d.get("faces", []) if ok else []
    zs = sorted(round(f["centre"][2], 3) for f in faces)
    areas_ok = all(near(f.get("area_mm2") or 0.0, 400.0, tol=0.01) for f in faces)
    record("U3 gola lungo +Z: 2 facce (fondo z=8 e soffitto z=12), area 400 mm2 ciascuna",
           ok and d.get("undercut_faces") == 2 and zs == [8.0, 12.0] and areas_ok,
           f"{text[:70]} | centri z {zs} | aree {[f.get('area_mm2') for f in faces]}")

    ok2, text2, d2 = await c.call("undercut_analysis", direction="-Z")
    record("U4a gola lungo -Z: 2 facce (stesso risultato, verso opposto)",
           ok2 and d2.get("undercut_faces") == 2, text2[:90])
    ok3, text3, d3 = await c.call("undercut_analysis", direction="+Y")
    record("U4b gola lungo +Y (gola aperta su quel lato): 0 facce",
           ok3 and d3.get("undercut_faces") == 0, text3[:90])

    ok4, text4, _ = await c.call("undercut_analysis", direction="diagonale")
    record("U5 direzione non valida rifiutata", not ok4, text4[:90])
    await discard_all(c)


# ===================================================================================================== principale
SECTIONS = (("U", u_undercut),)


async def scenario(c):
    only = {a.upper() for a in sys.argv[1:]}
    for nome, fn in SECTIONS:
        if not only or nome in only:
            await fn(c)
    await discard_all(c)


async def run():
    elia_pids = sw_pids()
    print(f"Istanze SolidWorks gia' presenti (da non toccare): {sorted(elia_pids)}")
    env = dict(os.environ)
    env["SW_MCP_INSTANCE"] = "dedicated"
    params = StdioServerParameters(command=str(PYTHON), args=[str(SERVER)], env=env, cwd=str(ROOT))
    my_pid = None
    try:
        async with stdio_client(params) as (rd, wr):
            async with ClientSession(rd, wr, read_timeout_seconds=timedelta(seconds=600)) as session:
                await session.initialize()
                c = Client(session)
                tools = [t.name for t in (await session.list_tools()).tools]
                print(f"{len(tools)} tool esposti")
                record("tool undercut_analysis esposto", "undercut_analysis" in tools, "")
                ok, text, data = await c.call("connect_solidworks")
                my_pid = data.get("pid")
                print(text[:200])
                if not ok or not my_pid or my_pid in elia_pids or my_pid not in sw_pids():
                    print("STOP: nessuna istanza separata ottenibile. Nulla e' stato toccato.")
                    return False
                print(f"Istanza dedicata PID {my_pid} (diversa da {sorted(elia_pids)})")
                await scenario(c)
    finally:
        _cleanup(my_pid, elia_pids)
    return True


def _cleanup(my_pid, elia_pids):
    cleanup(my_pid, elia_pids)
    # altri sotto-agenti aprono e chiudono istanze proprie in parallelo: si controlla solo il PROPRIO PID
    record("istanza dedicata del test chiusa (PID proprio)", my_pid is None or my_pid not in sw_pids(),
           f"PID proprio {my_pid} chiuso: {my_pid not in sw_pids()}")


if __name__ == "__main__":
    done = asyncio.run(run())
    print("\n==== RIEPILOGO ====")
    for tool, res, note in RESULTS:
        print(f"{res:5} {tool:80} {note}"[:260])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
