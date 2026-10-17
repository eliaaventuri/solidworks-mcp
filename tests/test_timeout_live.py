"""
Fase 5.1 dal vivo: timeout dei tool con il thread COM unico, SOLO su istanze dedicate e nascoste.

Due sessioni del server, ognuna con la sua istanza dedicata (SW_MCP_TOOL_TIMEOUT=15 s):
  A. tool occupato in chiamate COM: execute_python chiama SolidWorks in un ciclo di 120 s. (Un messaggio modale, SendMsgToUser2,
     NON blocca un'istanza nascosta: ritorna subito, provato il 2026-10-17.)
     Atteso: errore di timeout dopo ~15 s, PID dedicato chiuso; la chiamata COM seguente del ciclo fallisce e libera il thread COM,
     quindi il tool dopo NON e' rifiutato come "ancora in corso" e spiega che l'istanza e' persa.
  B. blocco fuori da COM: execute_python con time.sleep(40).
     Atteso: errore dopo ~15 s; un tool chiamato subito dopo viene rifiutato (tool precedente ancora in corso) senza aspettare;
     finito lo sleep il server risponde di nuovo.
  C. ripresa (5.2, SW_MCP_AUTORESTART=1): connect chiamato due volte con l'istanza viva -> successo; PID dedicato ucciso a meta'
     -> il tool seguente rilancia l'istanza (PID nuovo) e avverte che i documenti sono persi; il lavoro riprende.
L'istanza di SolidWorks dell'utente non viene toccata; alla fine 0 processi orfani.
"""

import subprocess

import os
import sys
import time
import asyncio
from datetime import timedelta

from live_common import ROOT, PYTHON, SERVER, Client, sw_pids, cleanup   # noqa: E402
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

TIMEOUT_S = 15
RESULTS = []


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {note}" if note else ""))


async def session_run(label, scenario, elia_pids, extra_env=None):
    env = dict(os.environ)
    env["SW_MCP_INSTANCE"] = "dedicated"
    env["SW_MCP_TOOL_TIMEOUT"] = str(TIMEOUT_S)
    env["SW_MCP_ALLOW_PYTHON"] = "1"
    env.pop("SW_MCP_AUTORESTART", None)
    env.update(extra_env or {})
    params = StdioServerParameters(command=str(PYTHON), args=[str(SERVER)], env=env, cwd=str(ROOT))
    my_pid = None
    extra_pids = []
    try:
        async with stdio_client(params) as (rd, wr):
            async with ClientSession(rd, wr, read_timeout_seconds=timedelta(seconds=600)) as session:
                await session.initialize()
                c = Client(session)
                ok, text, data = await c.call("connect_solidworks")
                my_pid = data.get("pid")
                if not ok or not my_pid or my_pid in elia_pids or my_pid not in sw_pids():
                    print(f"{label}: STOP, nessuna istanza separata. {text[:150]}")
                    record(f"{label}: istanza dedicata avviata", False, text[:150])
                    return
                record(f"{label}: istanza dedicata avviata", True, f"PID {my_pid}")
                extra_pids = await scenario(c, my_pid, elia_pids) or []
    finally:
        for pid in extra_pids:                            # istanze rilanciate dal server durante il test (mai quelle dell'utente)
            if pid and pid not in elia_pids and pid in sw_pids():
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        cleanup(my_pid, elia_pids)


async def scenario_restart(c, pid, elia_pids):
    ok, text, data = await c.call("connect_solidworks")
    record("C: connect una seconda volta con l'istanza viva -> successo, stesso PID", ok and data.get("pid") == pid, text[:100])
    ok, text, _ = await c.call("create_new_part")
    record("C: pezzo creato prima del crash", ok, text[:60])
    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    time.sleep(3)
    record("C: PID dedicato ucciso a meta' test", pid not in sw_pids(), f"PID {pid}")
    before = sw_pids()
    t0 = time.time()
    ok, text, _ = await c.call("create_new_part")
    dt = time.time() - t0
    new = sorted(sw_pids() - before - elia_pids)
    record("C: il tool seguente rilancia l'istanza e riesce", ok and len(new) == 1 and new[0] != pid, f"{dt:.0f} s, nuovi PID {new}: {text[:80]}")
    record("C: il risultato avverte del rilancio e dei documenti persi",
           "ATTENZIONE" in text and str(pid) in text and "persi" in text, text[:160])
    ok2, text2, _ = await c.call("create_sketch", plane="Piano frontale")
    record("C: il lavoro riprende sulla nuova istanza (schizzo creato), avviso non ripetuto", ok2 and "ATTENZIONE" not in text2, text2[:80])
    return new


async def scenario_com_block(c, pid, elia_pids):
    ok, text, _ = await c.call("create_new_part")
    record("A: tool normale eseguito sul thread COM", ok, text[:80])
    t0 = time.time()
    code = "import time\nt0 = time.time()\nn = 0\nwhile time.time() - t0 < 120:\n    sw.RevisionNumber\n    n += 1\nprint(n)"
    ok, text, _ = await c.call("execute_python", code=code)
    dt = time.time() - t0
    record(f"A: errore di timeout fra {TIMEOUT_S} e {TIMEOUT_S + 15} s", (not ok) and "superato" in text and TIMEOUT_S <= dt < TIMEOUT_S + 15,
           f"{dt:.1f} s: {text[:160]}")
    time.sleep(3)
    record("A: PID dedicato chiuso dopo il timeout", pid not in sw_pids(), f"PID {pid}")
    t0 = time.time()
    ok, text, _ = await c.call("get_document_info")
    dt = time.time() - t0
    record("A: thread COM liberato dalla chiusura (tool seguente non 'ancora in corso', risposta immediata)",
           (not ok) and dt < 10 and "ancora eseguendo" not in text, f"{dt:.1f} s: {text[:160]}")
    ok, text, _ = await c.call("connect_solidworks")
    record("A: connect spiega che l'istanza e' persa e il server va riavviato", (not ok) and "riavvia" in text.lower(), text[:160])


async def scenario_sleep(c, pid, elia_pids):
    t0 = time.time()
    ok, text, _ = await c.call("execute_python", code="import time\ntime.sleep(40)\nprint('fine')")
    dt = time.time() - t0
    record(f"B: errore di timeout dopo ~{TIMEOUT_S} s senza aspettare i 40 s", (not ok) and "superato" in text and dt < 30,
           f"{dt:.1f} s: {text[:160]}")
    t0 = time.time()
    ok, text, _ = await c.call("get_document_info")
    dt = time.time() - t0
    record("B: tool successivo rifiutato subito mentre il precedente e' in corso", (not ok) and "ancora eseguendo" in text and dt < 5,
           f"{dt:.1f} s: {text[:120]}")
    time.sleep(max(0.0, 45 - TIMEOUT_S))                  # lo sleep finisce
    ok, text, _ = await c.call("list_open_documents")
    record("B: dopo lo sblocco il server esegue di nuovo i tool", "ancora eseguendo" not in text, text[:120])


async def run():
    elia_pids = sw_pids()
    print(f"Istanze SolidWorks gia' presenti (da non toccare): {sorted(elia_pids)}")
    await session_run("A", scenario_com_block, elia_pids)
    await session_run("B", scenario_sleep, elia_pids)
    await session_run("C", scenario_restart, elia_pids, {"SW_MCP_AUTORESTART": "1"})
    left = sw_pids() - elia_pids
    record("0 processi SolidWorks orfani, istanza utente intatta", not left and elia_pids <= sw_pids(), f"orfani {sorted(left)}")


if __name__ == "__main__":
    asyncio.run(run())
    print("\n==== RIEPILOGO ====")
    for name, res, note in RESULTS:
        print(f"{res:5} {name:75} {note}"[:250])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if npass == len(RESULTS) else 1)
