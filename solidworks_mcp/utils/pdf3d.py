"""
D10 - Lettura di un PDF 3D in Python puro: trova l'annotazione 3D, lo stream 3D (PRC o U3D), lo decomprime e lo controlla.

Oggi `inspect_export_file` cercava solo i testi "/3D" e "PRC" nel file. Qui:
  - oggetti `N G obj ... endobj` (non compressi; gli object stream /ObjStm vengono aperti se ci sono);
  - stream con /Subtype /PRC o /U3D -> decompressione /FlateDecode (zlib) -> magic "PRC" (ISO 14739-1) o "U3D\\0";
  - annotazioni /Subtype /3D, viste /3DV (nomi /XN), numero di pagine.
Il formato del PDF scritto da SolidWorks non e' ancora stato confrontato con questo lettore: da provare sul PDF di
test_data_live (D10). In caso di struttura non riconosciuta il risultato lo dice (`parsed=False`), senza eccezioni.
"""

import re
import zlib
from typing import Any, Dict, Optional, Tuple

_OBJ_RE = re.compile(rb"(\d+)\s+(\d+)\s+obj\b(.*?)\bendobj", re.S)
_STREAM_RE = re.compile(rb"stream\r?\n")


def _split_stream(body: bytes) -> Tuple[bytes, Optional[bytes]]:
    """(dizionario, dati dello stream o None)."""
    m = _STREAM_RE.search(body)
    if not m:
        return body, None
    head = body[:m.start()]
    data = body[m.end():]
    end = data.rfind(b"endstream")
    if end >= 0:
        data = data[:end]
    lm = re.search(rb"/Length\s+(\d+)(?!\s+\d+\s+R)", head)
    if lm and int(lm.group(1)) <= len(data):
        data = data[:int(lm.group(1))]
    else:
        data = data.rstrip(b"\r\n")
    return head, data


def _decode(head: bytes, data: bytes) -> Tuple[Optional[bytes], str]:
    if re.search(rb"/(FlateDecode|Fl)\b", head):
        try:
            return zlib.decompress(data), "flate"
        except zlib.error:
            try:
                return zlib.decompressobj().decompress(data), "flate (parziale)"
            except zlib.error as e:
                return None, f"flate fallito: {e}"
    if re.search(rb"/Filter\s*/", head) or re.search(rb"/Filter\s*\[", head):
        return None, "filtro non supportato"
    return data, "nessun filtro"


def _objects(pdf: bytes) -> Dict[int, Tuple[bytes, Optional[bytes]]]:
    objs: Dict[int, Tuple[bytes, Optional[bytes]]] = {}
    for m in _OBJ_RE.finditer(pdf):
        objs[int(m.group(1))] = _split_stream(m.group(3))
    # object stream: oggetti compressi dentro /Type /ObjStm
    for num, (head, data) in list(objs.items()):
        if data is None or b"/ObjStm" not in head:
            continue
        raw, _ = _decode(head, data)
        n = re.search(rb"/N\s+(\d+)", head)
        first = re.search(rb"/First\s+(\d+)", head)
        if raw is None or not n or not first:
            continue
        nums = [int(x) for x in raw[:int(first.group(1))].split()]
        pairs = list(zip(nums[0::2], nums[1::2]))[:int(n.group(1))]
        for k, (onum, off) in enumerate(pairs):
            start = int(first.group(1)) + off
            end = int(first.group(1)) + pairs[k + 1][1] if k + 1 < len(pairs) else len(raw)
            objs.setdefault(onum, (raw[start:end], None))
    return objs


def inspect_pdf3d(pdf: bytes) -> Dict[str, Any]:
    """Struttura 3D di un PDF. Chiavi: parsed, pages, annotations_3d, streams_3d [{object, subtype, filter, size, decoded_size,
    magic_ok}], views [nomi], prc_ok (almeno uno stream PRC decompresso con magic 'PRC'), u3d_ok, notes."""
    info: Dict[str, Any] = {"parsed": False, "pages": 0, "annotations_3d": 0, "streams_3d": [], "views": [],
                            "prc_ok": False, "u3d_ok": False, "notes": []}
    if not pdf.startswith(b"%PDF"):
        info["notes"].append("non e' un PDF (manca %PDF)")
        return info
    objs = _objects(pdf)
    if not objs:
        info["notes"].append("nessun oggetto leggibile (PDF con struttura non supportata)")
        return info
    info["parsed"] = True
    for num, (head, data) in sorted(objs.items()):
        if re.search(rb"/Type\s*/Page(?!s)\b", head):
            info["pages"] += 1
        if re.search(rb"/Subtype\s*/3D\b", head) and re.search(rb"/Annot\b|/Rect\b", head):
            info["annotations_3d"] += 1
        for xn in re.findall(rb"/XN\s*\(([^)]*)\)", head):
            name = xn.decode("latin-1")
            if name not in info["views"]:
                info["views"].append(name)
        st = re.search(rb"/Subtype\s*/(PRC|U3D)\b", head)
        if st and data is not None:
            raw, how = _decode(head, data)
            kind = st.group(1).decode()
            ok = raw is not None and (raw[:3] == b"PRC" if kind == "PRC" else raw[:4] == b"U3D\x00")
            info["streams_3d"].append({"object": num, "subtype": kind, "filter": how, "size": len(data),
                                       "decoded_size": len(raw) if raw is not None else None, "magic_ok": ok})
            if ok:
                info["prc_ok" if kind == "PRC" else "u3d_ok"] = True
    if not info["streams_3d"]:
        info["notes"].append("nessuno stream /PRC o /U3D")
    return info
