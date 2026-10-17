"""
Test live del GRUPPO D (dati ed export, voci D7, D8, D1, D10, D4, D9, D2, D3) tramite il server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente non viene mai
toccata; alla fine si chiude solo il PID lanciato dal test. Ogni sezione costruisce i propri pezzi (file dxe_* in test_output).

Uso:  .venv\\Scripts\\python.exe tests\\test_data_extra_live.py            tutte le sezioni
      .venv\\Scripts\\python.exe tests\\test_data_extra_live.py D7 D1      solo quelle indicate
"""

import os
import sys
import math
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup, L
from test_data_live import RESULTS, record, T, F, rm, rel  # noqa: F401  (aiuti comuni, stesso elenco dei risultati)

PI = math.pi


# ============================================================================================ D7
async def sec_d7(c: Client):
    """D7: proprieta' di massa rispetto a un sistema di coordinate utente."""
    print("\n== D7 proprieta' di massa in un sistema di coordinate utente")


# ============================================================================================ D8
async def sec_d8(c: Client):
    """D8: materiali da tutte le cartelle delle librerie configurate."""
    print("\n== D8 materiali da librerie personalizzate")


# ============================================================================================ D1
async def sec_d1(c: Client):
    """D1: configurazioni da tabella (apply_configuration_table)."""
    print("\n== D1 configurazioni da tabella")


# ============================================================================================ D10
async def sec_d10(c: Client):
    """D10: PDF 3D letto a fondo (pdf3d)."""
    print("\n== D10 PDF 3D")


# ============================================================================================ D4
async def sec_d4(c: Client):
    """D4: immagini oltre la risoluzione nativa, prospettiva."""
    print("\n== D4 immagini")


# ============================================================================================ D9
async def sec_d9(c: Client):
    """D9: opzioni di import."""
    print("\n== D9 import")


# ============================================================================================ D2
async def sec_d2(c: Client):
    """D2: STEP AP242."""
    print("\n== D2 STEP AP242")


# ============================================================================================ D3
async def sec_d3(c: Client):
    """D3: eDrawings verificato."""
    print("\n== D3 eDrawings")


SECTIONS = {"D7": sec_d7, "D8": sec_d8, "D1": sec_d1, "D10": sec_d10, "D4": sec_d4, "D9": sec_d9, "D2": sec_d2, "D3": sec_d3}


# ============================================================================================ avvio
async def run(names):
    elia_pids = sw_pids()
    print(f"Istanze SolidWorks gia' presenti (da non toccare): {sorted(elia_pids)}")
    env = dict(os.environ)
    env["SW_MCP_INSTANCE"] = "dedicated"
    params = StdioServerParameters(command=str(PYTHON), args=[str(SERVER)], env=env, cwd=str(ROOT))
    my_pid = None
    try:
        async with stdio_client(params) as (rd, wr):
            async with ClientSession(rd, wr, read_timeout_seconds=timedelta(seconds=900)) as session:
                await session.initialize()
                c = Client(session)
                ok, text, data = await c.call("connect_solidworks")
                my_pid = data.get("pid")
                print(text[:200])
                if not ok or not my_pid or my_pid in elia_pids or my_pid not in sw_pids():
                    print("STOP: nessuna istanza separata ottenibile. Nulla e' stato toccato.")
                    return False
                record("PID dedicato diverso dall'istanza utente", my_pid not in elia_pids, str(my_pid))
                for n in names:
                    try:
                        await SECTIONS[n](c)
                    except Exception as e:
                        record(f"{n}: sezione interrotta da un'eccezione", False, repr(e)[:200])
    finally:
        cleanup(my_pid, elia_pids)
    return True


if __name__ == "__main__":
    names = [a.upper() for a in sys.argv[1:]] or list(SECTIONS)
    bad = [n for n in names if n not in SECTIONS]
    if bad:
        print(f"Sezioni sconosciute: {bad}. Disponibili: {list(SECTIONS)}")
        sys.exit(2)
    done = asyncio.run(run(names))
    print("\n==== RIEPILOGO ====")
    for tool, res, note in RESULTS:
        print(f"{res:5} {tool:90} {note}"[:250])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
