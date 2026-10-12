"""
Lingua dell'interfaccia di SolidWorks: tutto cio' che cambia fra un SolidWorks italiano e uno inglese, in un posto solo.

Regola del progetto: mai cercare per nome cio' che si puo' trovare per TIPO o POSIZIONE.
  - piani standard: 1°/2°/3° RefPlane dell'albero (frontale/superiore/destro in qualunque lingua);
  - origine: feature di tipo OriginProfileFeature;
  - tipi di feature (GetTypeName2: "RefPlane", "ProfileFeature", "MateGroup"...) sono gli stessi in ogni lingua.
Quando serve un nome (grafici della simulazione, testo di errore del cartiglio, cartelle lang\\<lingua>), qui ci sono le varianti.
Verificato dal vivo solo l'italiano; i nomi inglesi vengono dalla documentazione di SolidWorks (da confermare con
Strumenti > Opzioni > Generale > "Usa lingua inglese", vedi STATO.md).
"""

import re
from typing import List, Optional

# piani standard -> posizione fra i RefPlane dell'albero (0 frontale, 1 superiore, 2 destro)
_STD_PLANES = {
    0: ("front", "front plane", "frontale", "piano frontale"),
    1: ("top", "top plane", "superiore", "piano superiore"),
    2: ("right", "right plane", "destro", "piano destro"),
}
_ORIGIN = ("origin", "origine")

# prefissi dei nomi dei grafici creati da Simulation (Stress1 / Sollecitazione1 ...)
_PLOT_PREFIXES = {
    "von_mises": ("stress", "sollecitazione"),
    "displacement": ("displacement", "spostamento"),
    "strain": ("strain", "deformazione"),
}

# testo del cartiglio quando una proprieta' manca: "ERRORE:<nome>" (it), "ERROR:<nome>" (en)
TITLE_BLOCK_ERROR_RE = re.compile(r"(?:ERRORE|ERROR):([A-Za-z0-9_]+)")


def std_plane_index(name: str) -> Optional[int]:
    """0/1/2 se `name` indica un piano standard (in italiano o inglese, con o senza 'piano'/'plane'), altrimenti None."""
    low = " ".join(str(name or "").lower().split())
    for idx, names in _STD_PLANES.items():
        if low in names:
            return idx
    return None


def is_origin_name(name: str) -> bool:
    return " ".join(str(name or "").lower().split()) in _ORIGIN


def plot_candidates(result: str, names: List[str]) -> List[str]:
    """Nomi di grafici esistenti che corrispondono a `result` (von_mises | displacement | strain | nome esatto), in ordine."""
    want = str(result or "").lower()
    out = [n for n in names if n == result]
    for prefix in _PLOT_PREFIXES.get(want, ()):
        out += [n for n in names if n.lower().startswith(prefix) and n not in out]
    return out


def lang_folders(current: Optional[str]) -> List[str]:
    """Cartelle lang\\<lingua> da provare: prima la lingua attuale di SolidWorks, poi inglese e italiano."""
    out = []
    for lang in (current, "english", "italian"):
        lang = str(lang or "").strip().lower()
        if lang and lang not in out:
            out.append(lang)
    return out


# testi che il server SCRIVE sulle tavole: in italiano con SolidWorks italiano, in inglese con ogni altra lingua
DRAWING_TEXTS = {
    "aux_view": ("VISTA", "VIEW"),
    "chamfer_note": ("SMUSSI NON QUOTATI", "UNDIMENSIONED CHAMFERS"),
    "scale": ("SCALA", "SCALE"),
    "size": ("FORMATO", "SIZE"),
    "sheet": ("FOGLIO", "SHEET"),
    "material": ("MATERIALE", "MATERIAL"),
    "dwg_no": ("N. DISEGNO", "DWG. NO."),
    "title": ("TITOLO", "TITLE"),
    "company": ("AZIENDA", "COMPANY"),
    "rev": ("REV.", "REV."),
    "drawn": ("DISEGNATO", "DRAWN"),
    "date": ("DATA", "DATE"),
    "checked": ("VERIFICATO", "CHECKED"),
    "approved": ("APPROVATO", "APPROVED"),
    "weight": ("PESO [kg]", "WEIGHT [kg]"),
    "units_note": ("SE NON SPECIFICATO: QUOTE IN MILLIMETRI", "UNLESS OTHERWISE SPECIFIED: DIMENSIONS IN MILLIMETERS"),
    "projection_note": ("SPIGOLI NETTI - PRIMO DIEDRO (ISO 5456-2)", "SHARP EDGES - FIRST ANGLE PROJECTION (ISO 5456-2)"),
}


def drawing_text(key: str, language: Optional[str]) -> str:
    """Testo per la tavola nella lingua di SolidWorks: italiano se 'italian' (o lingua non leggibile), altrimenti inglese."""
    it, en = DRAWING_TEXTS[key]
    return it if str(language or "").lower() in ("", "italian") else en


def all_drawing_texts(key: str) -> tuple:
    """Tutte le varianti di un testo (per riconoscere una nota gia' scritta in qualunque lingua)."""
    return DRAWING_TEXTS[key]


def format_suffix(language: Optional[str]) -> str:
    """Suffisso del file dei formati verticali generati: '' per l'italiano (file storici in formats/), ' en' altrimenti."""
    return "" if str(language or "").lower() in ("", "italian") else " en"
