"""
D3 - Verifica strutturale dei file eDrawings (.eprt, .easm, .edrw) in Python puro.

L'automazione di eDrawings non e' utilizzabile (misurato 2026-10-17: `EModelView.EModelViewApp` risponde IsAppInitialized = 0 anche
dopo Init(False), OpenFile da' E_FAIL; `eDrawings.exe <file>` mostra sempre il titolo "eDrawings", anche con il file rotto).
La verifica e' quindi sul contenitore. Un `.eprt` scritto da SolidWorks 2026 e' un archivio ZIP con le voci:
  - `eModel`      HOOPS Stream File: inizia con ";; HSF V20.90 " e poi dati compressi (versione = `hsf_version`);
  - `preview.jpg` anteprima JPEG;
  - `materials.xml` con un `<Entity name="shared/body0">` per corpo dentro `<Materials ...>`;
  - `scene.xml`, `OLE`.
`bodies` conta gli `<Entity` di materials.xml. Per i pezzi vale il numero dei corpi solidi; per gli assiemi (.easm) non e' stato
ancora osservato un file vero: si accetta qualunque nome di Entity e il numero (corpi di tutti i componenti? uno per componente?)
va confrontato dal vivo (test_data_extra_live, D3). `valid` = ZIP integro + voce eModel con firma HSF.
Nessuna eccezione verso l'esterno: un file non ZIP da' `zip_ok=False` con una nota.
"""

import io
import re
import zipfile
from typing import Any, Dict

_ENTITY_RE = re.compile(r"<Entity\b([^>]*)>", re.I)
_NAME_RE = re.compile(r"""\bname\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
_HSF_RE = re.compile(rb"^;;\s*HSF\s+(V[0-9][0-9.]*)")


def inspect_edrawings(data: bytes) -> Dict[str, Any]:
    info: Dict[str, Any] = {"zip_ok": False, "entries": [], "hsf_ok": False, "hsf_version": None, "bodies": None,
                            "entities": [], "preview_ok": False, "valid": False, "notes": []}
    notes = info["notes"]
    try:
        if not data or not data.startswith(b"PK\x03\x04"):
            notes.append("non e' un archivio ZIP (firma PK mancante): file non eDrawings o danneggiato")
            return info
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as e:
            notes.append(f"archivio ZIP illeggibile (troncato?): {e}")
            return info
        with z:
            info["entries"] = z.namelist()
            bad = z.testzip()
            if bad is not None:
                notes.append(f"voce danneggiata nello ZIP: {bad}")
                return info
            info["zip_ok"] = True
            names = set(info["entries"])
            if "eModel" in names:
                head = z.open("eModel").read(64)
                m = _HSF_RE.match(head)
                if m:
                    info["hsf_ok"] = True
                    info["hsf_version"] = m.group(1).decode("ascii")
                else:
                    notes.append("voce eModel presente ma senza firma ';; HSF'")
            else:
                notes.append("voce eModel mancante")
            if "materials.xml" in names:
                txt = z.read("materials.xml").decode("utf-8", errors="ignore")
                ents = []
                for m in _ENTITY_RE.finditer(txt):
                    nm = _NAME_RE.search(m.group(1))
                    ents.append((nm.group(1) or nm.group(2) or "") if nm else "")
                info["entities"] = ents
                info["bodies"] = len(ents)
            else:
                notes.append("materials.xml mancante: numero di corpi non determinabile")
            if "preview.jpg" in names:
                jpg = z.read("preview.jpg")
                info["preview_ok"] = len(jpg) > 4 and jpg[:2] == b"\xff\xd8" and jpg[-2:] == b"\xff\xd9"
                if not info["preview_ok"]:
                    notes.append("preview.jpg non e' un JPEG completo")
            else:
                notes.append("preview.jpg mancante")
        info["valid"] = bool(info["zip_ok"] and info["hsf_ok"])
    except Exception as e:                                  # mai eccezioni verso l'esterno
        info["valid"] = False
        notes.append(f"errore di lettura: {e}")
    return info
