"""
Parti comuni dei test live (tests/test_*_live.py): percorsi, client MCP, processi SolidWorks.

I test live girano su Windows con SolidWorks, in un'istanza dedicata e nascosta: alla fine si chiude solo il PID del test.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "test_output"
OUT.mkdir(exist_ok=True)
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
SERVER = ROOT / "solidworks_mcp_server.py"

# tool che scrivono file: i file di test_output vengono riscritti a ogni esecuzione (gruppo B)
OVERWRITE_TOOLS = {"save_document", "save_drawing", "export_drawing", "export_model", "export_model_image", "export_simulation_plot", "create_drawing"}


def sw_pids():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq SLDWORKS.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    pids = set()
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) > 1 and parts[0].strip('"').lower() == "sldworks.exe":
            pids.add(int(parts[1]))
    return pids


class Client:
    """Chiama un tool MCP e restituisce (ok, testo, dati). Con auto_overwrite i tool che scrivono file ricevono overwrite=true
    (False solo dove si prova proprio il rifiuto della sovrascrittura)."""

    def __init__(self, session, auto_overwrite=True):
        self.s = session
        self.auto_overwrite = auto_overwrite

    async def call(self, tool_name, /, **args):
        if self.auto_overwrite and tool_name in OVERWRITE_TOOLS:
            args.setdefault("overwrite", True)
        r = await self.s.call_tool(tool_name, args)
        text = "".join(c.text for c in r.content if hasattr(c, "text"))
        ok = text.startswith("[SUCCESS]")
        data = {}
        if "Details: " in text:
            try:
                data = json.loads(text.split("Details: ", 1)[1])
            except Exception:
                data = {}
        return ok, text, data


def cleanup(my_pid, elia_pids):
    import time
    if my_pid and my_pid in sw_pids():
        subprocess.run(["taskkill", "/PID", str(my_pid), "/F"], capture_output=True)
    time.sleep(3)
    left = sw_pids() - elia_pids
    print(f"Processi SolidWorks orfani dopo il test: {sorted(left)}; istanza utente intatta: {elia_pids <= sw_pids()}")
