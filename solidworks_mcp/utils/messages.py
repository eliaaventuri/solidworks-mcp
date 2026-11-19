"""Lingua dei messaggi dei risultati (revisione sez. 5, 2026-11-19).

Il codice scrive i messaggi in italiano; in uscita il server li traduce in inglese (SW_MCP_LANG=en, predefinito, per chi
scarica il server da GitHub) con la tabella `messages_en.json`: frammento fisso italiano -> inglese, estratti dal codice
con scripts_tmp/estrai_messaggi.py. I valori dentro i messaggi (nomi, numeri) restano come sono; i dati (`Details`) non si
toccano. SW_MCP_LANG=it lascia l'italiano (i test dal vivo lo usano: controllano frasi italiane).
"""
import json
import os
import re
from pathlib import Path

_MAP_FILE = Path(__file__).with_name("messages_en.json")
_STATE = {"rx": None, "map": None}


def lang() -> str:
    return (os.environ.get("SW_MCP_LANG") or "en").strip().lower()[:2]


def _load():
    if _STATE["map"] is None:
        try:
            m = json.loads(_MAP_FILE.read_text(encoding="utf-8"))
        except Exception:
            m = {}
        m = {k: v for k, v in m.items() if isinstance(k, str) and isinstance(v, str) and k and v and k != v}
        pats = []
        for k in sorted(m, key=len, reverse=True):          # il frammento piu' lungo vince
            p = re.escape(k)
            if k[0].isalnum():
                p = r"(?<![A-Za-z0-9_])" + p
            if k[-1].isalnum():
                p += r"(?![A-Za-z0-9_])"
            pats.append(p)
        _STATE["map"] = m
        _STATE["rx"] = re.compile("|".join(pats)) if pats else None
    return _STATE


def tr(text):
    """Messaggio nella lingua scelta (in inglese solo se SW_MCP_LANG non e' 'it')."""
    if not isinstance(text, str) or not text or lang() != "en":
        return text
    st = _load()
    if st["rx"] is None:
        return text
    return st["rx"].sub(lambda mo: st["map"].get(mo.group(0), mo.group(0)), text)
