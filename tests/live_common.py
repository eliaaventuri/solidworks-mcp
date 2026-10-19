"""
Parti comuni dei test live (tests/test_*_live.py): percorsi, client MCP, processi SolidWorks.

I test live girano su Windows con SolidWorks, in un'istanza dedicata e nascosta: alla fine si chiude solo il PID del test.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("SW_MCP_ALLOW_PYTHON", "1")   # i test live contano EXPECTED_TOOLS tool, execute_python incluso

EXPECTED_TOOLS = 259    # numero di tool con execute_python attivo (+ 49 dei lotti tools_ext: moka 7, sketch2 16, curves 6, bodies2 7, features2 6, analysis 7; + list_sketch_relations, delete_sketch_entities; 197 + add_temperature, add_remote_load, add_bearing_load,
                        # add_simulation_contact, add_mesh_control del gruppo E; + move_faces)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "test_output"
OUT.mkdir(exist_ok=True)
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
SERVER = ROOT / "solidworks_mcp_server.py"

# tool che scrivono file: i file di test_output vengono riscritti a ogni esecuzione (gruppo B)
OVERWRITE_TOOLS = {"save_document", "save_drawing", "export_drawing", "export_model", "export_model_image", "export_simulation_plot", "create_drawing"}


# --------------------------------------------------------------------------- lingua di SolidWorks
# I test sono scritti con i nomi di SolidWorks ITALIANO. Con un'interfaccia in un'altra lingua (letta da connect_solidworks,
# campo ui_language) i nomi negli ARGOMENTI dei tool vengono tradotti in inglese; per i nomi nei CONTROLLI si usa L("...").
# I nomi inglesi vengono dalla documentazione di SolidWorks: da confermare alla prima esecuzione in inglese.
LANG = {"ui": "italian"}
_IT_EN = [
    (r"\bPiano frontale\b", "Front Plane"), (r"\bPiano superiore\b", "Top Plane"), (r"\bPiano destro\b", "Right Plane"),
    (r"\bTaglio-Estrusione(\d+)\b", r"Cut-Extrude\1"), (r"\bEstrusione-Estrusione(\d+)\b", r"Boss-Extrude\1"),
    (r"\bSchizzo(\d+)\b", r"Sketch\1"), (r"\bPiano(\d+)\b", r"Plane\1"), (r"\bAssi(\d+)\b", r"Axis\1"),
    (r"\bDistanzaLimite(\d+)\b", r"LimitDistance\1"), (r"\bDistanza(\d+)\b", r"Distance\1"), (r"\bOrigine\b", "Origin"),
    (r"\bLega 6061\b", "6061 Alloy"), (r"^alluminio$", "alumin"),
    (r"^Acciaio$", "Steel"), (r"^Plastiche$", "Plastics"), (r"\bABS generico\b", "ABS"),
    (r"^Bronzo$", "Bronze"),
    (r"\bRipetizioneCircolare(\d+)\b", r"CirPattern\1"), (r"\bRipetizioneLineare(\d+)\b", r"LPattern\1"),   # set_material cerca per sottostringa: primo bronzo della libreria in entrambe le lingue   # libreria inglese (dal .sldmat)
]


def italian() -> bool:
    return LANG["ui"] in ("", "italian")


def L(text):
    """Nome italiano -> nome nella lingua di SolidWorks (invariato con SolidWorks italiano). Funziona anche su liste e dizionari."""
    if italian():
        return text
    if isinstance(text, str):
        for pat, rep in _IT_EN:
            text = re.sub(pat, rep, text)
        return text
    if isinstance(text, list):
        return [L(x) for x in text]
    if isinstance(text, tuple):
        return tuple(L(x) for x in text)
    if isinstance(text, dict):
        return {k: L(v) for k, v in text.items()}
    return text


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
        args = {k: (v if k in ("filepath", "file_path", "save_as", "folder", "code") else L(v)) for k, v in args.items()}
        r = await self.s.call_tool(tool_name, args)
        text = "".join(c.text for c in r.content if hasattr(c, "text"))
        ok = text.startswith("[SUCCESS]")
        data = {}
        if "Details: " in text:
            try:
                data = json.loads(text.split("Details: ", 1)[1])
            except Exception:
                data = {}
        if tool_name == "connect_solidworks" and ok:
            LANG["ui"] = str(data.get("ui_language") or "italian").lower()
            print(f"Lingua di SolidWorks: {LANG['ui']}" + ("" if italian() else " (nomi italiani dei test tradotti in inglese)"))
        return ok, text, data


def cleanup(my_pid, elia_pids):
    import time
    if my_pid and my_pid in sw_pids():
        subprocess.run(["taskkill", "/PID", str(my_pid), "/F"], capture_output=True)
    time.sleep(3)
    left = sw_pids() - elia_pids
    print(f"Processi SolidWorks orfani dopo il test: {sorted(left)}; istanza utente intatta: {elia_pids <= sw_pids()}")
