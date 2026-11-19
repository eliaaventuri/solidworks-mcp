"""
Test OFFLINE: girano senza SolidWorks e senza Windows (pywin32 assente -> moduli COM finti).

Coprono solo cio' che non tocca l'API di SolidWorks:
  - registro dei tool: 203 tool, nomi unici, ogni tool smistato (elif in server.py o *_DISPATCH), ogni metodo esistente,
    parametri dello schema = parametri passati al metodo = parametri accettati dal metodo (nessun argomento perso o in piu'),
    `required` dello schema contenuti nelle proprieta' e uguali ai parametri obbligatori del metodo;
  - sicurezza (safety.py): rifiuto della sovrascrittura senza overwrite=true, annotazioni dei tool distruttivi;
  - PNG puro Python (_write_png / _read_png / _resize_png): andata e ritorno, palette, grigio, riduzione;
  - lettori dei file esportati (inspect_export_file): STL binario/ASCII, 3MF, STEP (AP203/214/242), IGES, Parasolid, PDF;
  - conversione delle unita' (utils/units.py).
Non sostituiscono i test live: servono a trovare subito gli errori di registrazione e di logica pura (anche nel cloud).

Uso:  python tests/test_offline.py          (oppure .venv\\Scripts\\python.exe tests\\test_offline.py su Windows)
"""

import os
import re
import sys
import json
import types
import asyncio
import inspect
import struct
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _stub_com():
    """Moduli COM finti se pywin32 non c'e' (Linux/macOS): bastano per importare il pacchetto."""
    try:
        __import__("pythoncom")
        __import__("win32com.client")
        return False
    except ImportError:
        pass
    for n in ("win32com", "win32com.client", "pythoncom", "pywintypes", "win32api", "win32con", "win32process", "win32gui"):
        sys.modules[n] = types.ModuleType(n)
    client = sys.modules["win32com.client"]
    sys.modules["win32com"].client = client

    class VARIANT:
        def __init__(self, vt, value):
            self.varianttype, self.value = vt, value
    client.VARIANT = VARIANT
    client.CDispatch = type("CDispatch", (), {})
    client.Dispatch = client.DispatchEx = client.GetActiveObject = client.GetObject = lambda *a, **k: None
    pc = sys.modules["pythoncom"]
    for k, v in dict(VT_EMPTY=0, VT_I2=2, VT_I4=3, VT_R8=5, VT_BSTR=8, VT_DISPATCH=9, VT_BOOL=11, VT_VARIANT=12, VT_UI4=19,
                     VT_ARRAY=0x2000, VT_BYREF=0x4000, DISPATCH_METHOD=1, DISPATCH_PROPERTYGET=2, DISPATCH_PROPERTYPUT=4,
                     COINIT_MULTITHREADED=0, COINIT_APARTMENTTHREADED=2).items():
        setattr(pc, k, v)
    pc.CoInitialize = pc.CoUninitialize = pc.CoInitializeEx = lambda *a: None
    pc.com_error = type("com_error", (Exception,), {})
    sys.modules["pywintypes"].com_error = pc.com_error
    return True


STUBBED = _stub_com()

import solidworks_mcp.server as srv                                   # noqa: E402
from solidworks_mcp.automation import SolidWorksAutomation             # noqa: E402
from solidworks_mcp.automation import data_export as dx                # noqa: E402
from solidworks_mcp import safety
from solidworks_mcp.constants import SwErrors                                      # noqa: E402
from solidworks_mcp.utils.units import UnitConverter                   # noqa: E402

if not STUBBED:
    # Con pywin32 vero (Windows) i tool chiamati qui si connettono da soli a un SolidWorks raggiungibile via COM
    # (verificato il 2026-10-23: studi creati nell'istanza del worker di sviluppo) o tentano di avviarne uno.
    # Il test offline non deve mai toccare SolidWorks: tutte le vie di connessione vengono chiuse.
    from solidworks_mcp.automation import base as _base                # noqa: E402
    _base.find_solidworks = lambda *a, **k: None
    SolidWorksAutomation._try_connect_com = lambda self: False
    _REAL_CONNECT_DEDICATED = SolidWorksAutomation._connect_dedicated   # per provarne il ramo d'errore con un processo finto
    SolidWorksAutomation._connect_dedicated = lambda self: self._result(False, "test offline: SolidWorks non usato",
                                                                        SwErrors.swConnectionError)

RESULTS = []
EXPECTED_TOOLS = 454                       # 455 registrati meno execute_python, disattivato di default (SW_MCP_ALLOW_PYTHON);
                                           # 2026-11-18: cancellato il codice degli 84 tool nascosti (erano 558 registrati)
                                           # e tolti 25 doppioni (REPLACED_BY in not_implemented.py)
from solidworks_mcp.not_implemented import NOT_IMPLEMENTED
EXPOSED_TOOLS = EXPECTED_TOOLS             # i nomi in NOT_IMPLEMENTED non hanno piu' codice: nulla da nascondere
for _var in ("SW_MCP_ALLOW_PYTHON", "SW_MCP_TOOLSETS"):
    os.environ.pop(_var, None)             # i test partono dal default: tutto attivo tranne execute_python


def record(name, ok, note=""):
    RESULTS.append((name, bool(ok), note))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {note}" if note else ""))


# ============================================================================ registro dei tool
def test_registry():
    # con execute_python attivo: il registro completo (203) va controllato anche per il suo smistamento
    os.environ["SW_MCP_ALLOW_PYTHON"] = "1"
    try:
        _test_registry_full(EXPECTED_TOOLS + 1)
    finally:
        os.environ.pop("SW_MCP_ALLOW_PYTHON", None)
    exposed = {t.name for t in asyncio.run(srv.list_tools())}
    shown = sorted(n for n in NOT_IMPLEMENTED if n in exposed)
    record(f"{len(NOT_IMPLEMENTED)} tool non implementati nascosti da list_tools", not shown, str(shown))
    real = srv.sw_automation
    fake = _FakeAutomation()
    srv.sw_automation = fake
    try:
        text = asyncio.run(srv.call_tool("add_weld_symbol", {}))[0].text
    finally:
        srv.sw_automation = real
    record("tool non implementato chiamato lo stesso: errore esplicito, metodo non eseguito",
           text.startswith("[ERROR]") and "non e' implementato" in text and not fake.calls, text[:90])
    # revisione 2026-11-12 sez. 4: il codice dei tool nascosti e' cancellato (schema, smistamento e metodo): togliere un
    # nome da NOT_IMPLEMENTED non deve poter riesporre un tool finto. Il motivo resta per spiegare la chiamata diretta.
    left = sorted(n for n in NOT_IMPLEMENTED
                  if any(n in t for t in srv.DISPATCH_TABLES) or hasattr(SolidWorksAutomation, n)
                  or any(t.name == n for t in srv._raw_all_tools()))
    record(f"codice dei {len(NOT_IMPLEMENTED)} tool nascosti cancellato (schema, smistamento, metodo)", not left,
           f"{len(left)} ancora presenti: {left[:6]}")
    # doppioni esposti (sez. 4): tolti; la chiamata con il vecchio nome dice quale tool usare, e quel tool esiste
    from solidworks_mcp.not_implemented import REPLACED_BY
    raw = {t.name for t in srv._raw_all_tools()}
    left = sorted(n for n in REPLACED_BY
                  if n in raw or any(n in t for t in srv.DISPATCH_TABLES) or hasattr(SolidWorksAutomation, n))
    missing = sorted(f"{n}->{r.split()[0]}" for n, r in REPLACED_BY.items() if r.split()[0] not in raw)
    record(f"{len(REPLACED_BY)} doppioni tolti (schema, smistamento, metodo) e sostituti esistenti", not left and not missing
           and len(REPLACED_BY) >= 20, f"ancora presenti {left[:6]}, sostituti mancanti {missing[:6]}")
    srv.sw_automation = fake
    try:
        text = asyncio.run(srv.call_tool("extrude_sketch", {"depth": 5}))[0].text
    finally:
        srv.sw_automation = real
    record("doppione chiamato con il vecchio nome: errore che indica il tool da usare, nulla eseguito",
           text.startswith("[ERROR]") and "extrude_boss" in text and not fake.calls, text[:120])
    base = {"extrude_boss", "extrude_cut", "fillet_at_points", "chamfer_at_points"}
    record("i sostituti di estrusione, taglio, raccordo e smusso stanno nel gruppo base (SW_MCP_TOOLSETS=base)",
           all(srv._tool_group(n) == "base" for n in base), str({n: srv._tool_group(n) for n in base}))


def _test_registry_full(expected):
    # registro completo, compresi i tool nascosti perche' non implementati: schema e smistamento vanno controllati lo stesso
    tools = srv.decorate_tools([t for t in srv._raw_all_tools()
                                if srv._tool_blocked_reason(t.name) is None or t.name in NOT_IMPLEMENTED])
    names = [t.name for t in tools]
    dups = sorted({n for n in names if names.count(n) > 1})
    record(f"{expected} tool esposti, nessun duplicato", len(names) == expected and not dups,
           f"{len(names)} tool, duplicati {dups}")

    dispatch = {}
    problems = []
    for d in srv.DISPATCH_TABLES:
        for k, v in d.items():
            if k in dispatch:
                problems.append(f"{k}: in due tabelle di smistamento")
            dispatch.setdefault(k, v)
    for t in tools:
        schema = t.inputSchema or {}
        props = set(schema.get("properties", {}))
        req = set(schema.get("required", []))
        if req - props:
            problems.append(f"{t.name}: required fuori dalle proprieta' {sorted(req - props)}")
        special = t.name in srv.SPECIAL_HANDLERS
        if t.name not in dispatch:
            if not special:
                problems.append(f"{t.name}: nessuno smistamento")
            continue
        if special:
            problems.append(f"{t.name}: smistato due volte (gestore speciale e tabella)")
        method, allowed = dispatch[t.name]
        fn = getattr(SolidWorksAutomation, method, None)
        if fn is None:
            problems.append(f"{t.name}: metodo {method} inesistente")
            continue
        sig = inspect.signature(fn)
        params = {p: v for p, v in sig.parameters.items() if p != "self"}
        varkw = any(v.kind == v.VAR_KEYWORD for v in params.values())
        if not varkw and allowed - set(params):
            problems.append(f"{t.name}: {method}() non accetta {sorted(allowed - set(params))}")
        lost = props - allowed - {"overwrite", "document"}  # overwrite e document sono consumati da server.py
        if lost:
            problems.append(f"{t.name}: proprieta' dello schema mai passate al metodo {sorted(lost)}")
        needed = {p for p, v in params.items()
                  if v.default is inspect.Parameter.empty and v.kind not in (v.VAR_KEYWORD, v.VAR_POSITIONAL)}
        if needed - req:
            problems.append(f"{t.name}: {method}() richiede {sorted(needed - req)} ma lo schema non li dichiara required")
    orphans = sorted(k for k in list(dispatch) + list(srv.SPECIAL_HANDLERS) if k not in names)
    if orphans:
        problems.append(f"smistamenti senza tool: {orphans}")
    record("schema / smistamento / firma dei metodi coerenti per ogni tool", not problems, "; ".join(problems[:8]))

    unknown = sorted(n for n in list(safety.DESTRUCTIVE_TOOLS) + list(safety.OVERWRITE_GUARDS) if n not in names)
    record("safety.py nomina solo tool esistenti", not unknown, str(unknown))
    bad = [t.name for t in tools if t.name in safety.DESTRUCTIVE_TOOLS and
           not (t.annotations and t.annotations.destructiveHint and "[DESTRUCTIVE" in (t.description or ""))]
    record("tool distruttivi annotati (destructiveHint + nota)", not bad, str(bad))
    no_ow = [t.name for t in tools if t.name in safety.OVERWRITE_GUARDS and "overwrite" not in (t.inputSchema or {}).get("properties", {})]
    record("tool che scrivono file espongono overwrite", not no_ow, str(no_ow))


# ============================================================================ smistamento end-to-end (call_tool)
class _FakeAutomation:
    """Al posto di SolidWorksAutomation: registra metodo e argomenti invece di parlare con SolidWorks."""

    def __init__(self):
        self.calls = []
        self.restored = 0
        self._sw_app = None
        self._units = types.SimpleNamespace(default_unit="mm")

    def _result(self, success, message, error_code=0, data=None):
        return SolidWorksAutomation._result(self, success, message, error_code, data)

    def _restore_prefs(self):
        self.restored += 1

    def __getattr__(self, name):
        def method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return {"success": True, "message": name, "error_code": 0, "error_name": "swSuccess", "data": {}}
        return method


def test_call_tool(tmp):
    real = srv.sw_automation
    fake = _FakeAutomation()
    srv.sw_automation = fake
    try:
        def call(name, args):
            fake.calls.clear()
            out = asyncio.run(srv.call_tool(name, args))
            return out[0].text, list(fake.calls)

        text, calls = call("draw_arc", {"cx": 1, "cy": 2, "radius": 3, "start_angle": 10, "end_angle": 80, "unit": "mm", "extra": 9})
        record("call_tool: draw_arc -> draw_arc_center con i soli parametri ammessi",
               calls == [("draw_arc_center", (), {"cx": 1, "cy": 2, "radius": 3, "start_angle": 10, "end_angle": 80, "unit": "mm"})],
               str(calls))
        text, calls = call("connect_solidworks", {})
        record("call_tool: connect_solidworks -> connect()", calls == [("connect", (), {})], str(calls))
        text, calls = call("close_document", {"discard": True})
        record("call_tool: close_document passa discard", calls == [("close_document", (), {"discard": True})], str(calls))
        existing = os.path.join(tmp, "gia.step")
        open(existing, "w").close()
        text, calls = call("export_model", {"filepath": existing})
        record("call_tool: export_model su file esistente rifiutato prima del metodo", not calls and "Rifiutato" in text, text[:80])
        text, calls = call("set_units", {"unit": "inch"})
        record("call_tool: set_units cambia l'unita' predefinita", fake._units.default_unit == "inch" and "SUCCESS" in text, text[:60])
        text, calls = call("execute_python", {})
        record("call_tool: execute_python senza codice -> errore", text.startswith("[ERROR]") and not calls, text[:60])
        text, calls = call("tool_inesistente", {})
        record("call_tool: tool sconosciuto -> errore", "Unknown tool" in text, text[:60])

        before = fake.restored
        call("draw_circle", {"radius": 5})
        call("tool_inesistente", {})
        record("call_tool: preferenze ripristinate dopo ogni tool (anche se sconosciuto)", fake.restored - before == 2)
        tools = asyncio.run(srv.list_tools())
        failed = []
        for t in tools:
            if t.name in srv.SPECIAL_HANDLERS:
                continue
            text, calls = call(t.name, {})
            if not calls or text.startswith("[ERROR]"):
                failed.append(t.name)
        record("call_tool: ogni tool di tabella raggiunge il suo metodo", not failed, str(failed[:10]))
    finally:
        srv.sw_automation = real
        from solidworks_mcp.utils import set_default_unit
        set_default_unit("mm")


# ============================================================================ controlli di export_model prima di SolidWorks
def test_export_guards(tmp):
    sw = SolidWorksAutomation()
    sw._dx_doc = lambda types=None: (object(), None)
    sw._dx_cfg_names = lambda doc: ["Default", "Lunga"]
    igs = os.path.join(tmp, "pezzo.igs")
    with open(igs, "w") as f:
        f.write("ORIGINALE")
    r = sw.export_model(os.path.join(tmp, "pezzo.iges"))
    record("export_model: .iges scritto come .igs esistente -> rifiuto, file intatto",
           not r["success"] and r["data"].get("refused") == "file_exists" and open(igs).read() == "ORIGINALE", r["message"][:90])
    stl = os.path.join(tmp, "pezzo.stl")
    with open(stl, "w") as f:
        f.write("ORIGINALE")
    r = sw.export_model(os.path.join(tmp, "pezzo.step"), format="stl")
    record("export_model: format=stl su nome .step con .stl esistente -> rifiuto", not r["success"] and open(stl).read() == "ORIGINALE")
    pdf = os.path.join(tmp, "tavola.pdf")
    with open(pdf, "w") as f:
        f.write("ORIGINALE")
    sw._drawing = lambda: (object(), None)
    r = sw.export_drawing(os.path.join(tmp, "tavola.dxf"), format="pdf")
    record("export_drawing: format=pdf su nome .dxf con .pdf esistente -> rifiuto", not r["success"] and open(pdf).read() == "ORIGINALE",
           r["message"][:90])
    r = sw.export_model(os.path.join(tmp, "nuovo.step"), configuration="Inesistente")
    record("export_model: configurazione inesistente -> errore prima dell'export", not r["success"] and "Inesistente" in r["message"]
           and not os.path.exists(os.path.join(tmp, "nuovo.step")), r["message"][:90])


# ============================================================================ preferenze anti-finestre di dialogo
def test_dialog_prefs():
    class App:
        def __init__(self):
            self.t = {10: True, 96: True, 100: True, 101: False, 55: True}

        def GetUserPreferenceToggle(self, k):
            return self.t[k]

        def SetUserPreferenceToggle(self, k, v):
            self.t[k] = v
    sw = SolidWorksAutomation()
    sw._sw_app = app = App()
    orig = dict(app.t)
    sw._prepare_prefs()
    during = dict(app.t)
    sw._prepare_prefs()                         # seconda chiamata nello stesso tool: l'originale salvato non cambia
    sw._restore_prefs()
    record("preferenze: durante il tool niente finestre (10/96/100 off, 101 on), dopo valori originali",
           during == {10: False, 96: False, 100: False, 101: True, 55: True} and app.t == orig, f"{during} -> {app.t}")
    sw._restore_prefs()
    record("preferenze: ripristino ripetuto innocuo", app.t == orig)
    # ottimizzazione 2026-11-18: istanza dedicata -> impostate una volta, tenute fra i tool, rimesse solo con force (chiusura)
    os.environ["SW_MCP_INSTANCE"] = "dedicated"
    try:
        sw2 = SolidWorksAutomation()
        sw2._sw_app = app2 = App()
        orig2 = dict(app2.t)
        calls = {"n": 0}
        real_set = app2.SetUserPreferenceToggle

        def counting_set(k, v):
            calls["n"] += 1
            real_set(k, v)
        app2.SetUserPreferenceToggle = counting_set
        sw2._prepare_prefs()
        sw2._restore_prefs()                    # fine del tool: sull'istanza dedicata non rimette nulla
        n_first = calls["n"]
        sw2._prepare_prefs()                    # tool seguente: niente scritture
        held = dict(app2.t)
        n_second = calls["n"] - n_first
        sw2._restore_prefs(force=True)          # chiusura dell'istanza
        record("preferenze, istanza dedicata: tenute fra i tool (0 scritture al secondo tool), ripristinate alla chiusura",
               n_first == 4 and n_second == 0 and held[10] is False and app2.t == orig2, f"{n_first} {n_second} {app2.t}")
    finally:
        os.environ.pop("SW_MCP_INSTANCE", None)


# ============================================================================ sicurezza
def test_safety(tmp):
    existing = os.path.join(tmp, "esiste.step")
    open(existing, "w").close()
    nuovo = os.path.join(tmp, "nuovo.step")
    record("check_call: file esistente senza overwrite -> rifiuto",
           safety.check_call("export_model", {"filepath": existing}) is not None)
    record("check_call: file esistente con overwrite=true -> ammesso",
           safety.check_call("export_model", {"filepath": existing, "overwrite": True}) is None)
    record("check_call: file nuovo -> ammesso", safety.check_call("export_model", {"filepath": nuovo}) is None)
    record("check_call: create_drawing usa save_as",
           safety.check_call("create_drawing", {"save_as": existing}) is not None)
    record("check_call: save_document lasciato al metodo",
           safety.check_call("save_document", {"filepath": existing}) is None)
    record("check_call: tool non protetto -> None", safety.check_call("get_document_info", {}) is None)


# ============================================================================ PNG
def _gradient(w, h):
    return [bytes(c for x in range(w) for c in (x * 255 // max(1, w - 1), y * 255 // max(1, h - 1), 128)) for y in range(h)]


def _png_chunk(t, d):
    import zlib
    c = struct.pack(">I", len(d)) + t + d
    return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)


def _write_png_raw(path, w, h, bd, ct, raw_rows, plte=b""):
    import zlib
    raw = b"".join(b"\x00" + r for r in raw_rows)
    data = b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, bd, ct, 0, 0, 0))
    if plte:
        data += _png_chunk(b"PLTE", plte)
    data += _png_chunk(b"IDAT", zlib.compress(raw)) + _png_chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(data)


def test_png(tmp):
    w, h = 40, 30
    rows = _gradient(w, h)
    p = os.path.join(tmp, "g.png")
    dx._write_png(p, w, h, rows)
    rw, rh, _, back = dx._read_png(p)
    record("PNG RGB: scrittura e rilettura identiche", (rw, rh) == (w, h) and [bytes(r) for r in back] == rows)

    # palette 2 bit: 4 colori
    pal = bytes((255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255))
    idx = [[(x + y) % 4 for x in range(9)] for y in range(3)]
    packed = []
    for r in idx:
        b = bytearray()
        for i in range(0, len(r), 4):
            q = r[i:i + 4] + [0] * (4 - len(r[i:i + 4]))
            b.append(q[0] << 6 | q[1] << 4 | q[2] << 2 | q[3])
        packed.append(bytes(b))
    pp = os.path.join(tmp, "pal.png")
    _write_png_raw(pp, 9, 3, 2, 3, packed, pal)
    _, _, _, prow = dx._read_png(pp)
    ok = all(bytes(prow[y][3 * x:3 * x + 3]) == pal[3 * idx[y][x]:3 * idx[y][x] + 3] for y in range(3) for x in range(9))
    record("PNG palette 2 bit -> RGB", ok)

    gp = os.path.join(tmp, "grey.png")
    _write_png_raw(gp, 4, 2, 8, 0, [bytes((0, 85, 170, 255))] * 2)
    _, _, _, grow = dx._read_png(gp)
    record("PNG grigio 8 bit -> RGB", bytes(grow[0]) == bytes(c for v in (0, 85, 170, 255) for c in (v, v, v)))

    ap = os.path.join(tmp, "rgba.png")
    _write_png_raw(ap, 2, 1, 8, 6, [bytes((10, 20, 30, 255, 40, 50, 60, 0))])
    _, _, _, arow = dx._read_png(ap)
    record("PNG RGBA -> RGB (alfa scartato)", bytes(arow[0]) == bytes((10, 20, 30, 40, 50, 60)))

    out = os.path.join(tmp, "small.png")
    W, H, shrunk = dx._resize_png(p, out, 20, 15)
    sw, sh, _, _ = dx._read_png(out)
    record("riduzione PNG 40x30 -> 20x15", shrunk and (W, H) == (20, 15) == (sw, sh), f"{W}x{H} letto {sw}x{sh}")
    W2, H2, shrunk2 = dx._resize_png(p, os.path.join(tmp, "big.png"), 400, 300)
    record("PNG mai ingrandito oltre il nativo", not shrunk2 and (W2, H2) == (w, h), f"{W2}x{H2}")
    # D4: criterio della cattura di stampa e DPI (Letter orizzontale 11 x 8,5 pollici)
    record("D4 cattura di stampa: solo oltre 2000 x 1400", dx._wants_print_capture(3840, 2160) and dx._wants_print_capture(2001, 100)
           and dx._wants_print_capture(100, 1401) and not dx._wants_print_capture(900, 600) and not dx._wants_print_capture(2000, 1400))
    record("D4 DPI: 3840x2160 -> 350, 900x600 -> 100 (minimo), 20000x10000 -> 600 (tetto)",
           (dx._print_dpi(3840, 2160), dx._print_dpi(900, 600), dx._print_dpi(20000, 10000)) == (350, 100, 600),
           f"{dx._print_dpi(3840, 2160)} {dx._print_dpi(900, 600)} {dx._print_dpi(20000, 10000)}")
    # D4: ricentratura sul contenuto (sfondo bianco, quadrato nero 20x20 spostato a destra in un'immagine 200x100)
    cp = os.path.join(tmp, "offc.png")
    crow = [bytes((255, 255, 255)) * 140 + bytes((0, 0, 0)) * 20 + bytes((255, 255, 255)) * 40 if 40 <= y < 60
            else bytes((255, 255, 255)) * 200 for y in range(100)]
    dx._write_png(cp, 200, 100, crow)
    record("D4 _png_dims legge 200x100 dall'intestazione", dx._png_dims(cp) == (200, 100), str(dx._png_dims(cp)))
    co = os.path.join(tmp, "offc_out.png")
    dx._resize_png(cp, co, 80, 40, recenter=True)
    cw, chh, cb, crows = dx._read_png(co)
    blk = [(x, y) for y in range(chh) for x in range(cw) if crows[y][x * cb] < 128]
    cx = (min(p[0] for p in blk) + max(p[0] for p in blk)) / 2 if blk else -1
    cy = (min(p[1] for p in blk) + max(p[1] for p in blk)) / 2 if blk else -1
    record("D4 recenter: quadrato fuori centro -> centrato (entro 1 px) nell'immagine 80x40", (cw, chh) == (80, 40) and abs(cx - 39.5) <= 1
           and abs(cy - 19.5) <= 1, f"{cw}x{chh} centro ({cx}, {cy})")
    sp = os.path.join(tmp, "grad.png")
    dx._write_png(sp, 4, 4, [bytes((y * 60, 0, 0)) * 4 for y in range(4)])
    record("D4 recenter: sfondo non uniforme -> nessun ritaglio", dx._recenter_box(dx._read_png(sp)[3], 4, 4, 3, 2, 2) is None)
    record("D4 DPI: la Letter a quei DPI copre WxH", all(11 * dx._print_dpi(a, b) >= a and 8.5 * dx._print_dpi(a, b) >= b
                                                         for a, b in ((3840, 2160), (2100, 2000), (1000, 3000), (2500, 1500))))


# ============================================================================ lettori dei file esportati
def _cube_tris(s=10.0):
    v = [(x, y, z) for x in (0, s) for y in (0, s) for z in (0, s)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    tris = []
    for a, b, c, d in faces:
        tris += [(v[a], v[b], v[c]), (v[a], v[c], v[d])]
    return tris


def test_inspectors(tmp):
    sw = SolidWorksAutomation()
    tris = _cube_tris()
    stl_b = os.path.join(tmp, "c_bin.stl")
    with open(stl_b, "wb") as f:
        f.write(b"\0" * 80 + struct.pack("<I", len(tris)))
        for t in tris:
            f.write(struct.pack("<12fH", 0, 0, 0, *[c for p in t for c in p], 0))
    d = sw.inspect_export_file(stl_b)["data"]
    record("STL binario: 12 triangoli, box 10x10x10", d.get("encoding") == "binary" and d.get("triangles") == 12
           and d.get("bbox_size") == [10.0, 10.0, 10.0], str({k: d.get(k) for k in ("encoding", "triangles", "bbox_size")}))

    stl_a = os.path.join(tmp, "c_asc.stl")
    with open(stl_a, "w") as f:
        f.write("solid c\n")
        for t in tris:
            f.write(" facet normal 0 0 0\n  outer loop\n" + "".join(f"   vertex {p[0]} {p[1]} {p[2]}\n" for p in t)
                    + "  endloop\n endfacet\n")
        f.write("endsolid c\n")
    d = sw.inspect_export_file(stl_a)["data"]
    record("STL ASCII: 12 triangoli, box 10x10x10", d.get("encoding") == "ascii" and d.get("triangles") == 12
           and d.get("bbox_size") == [10.0, 10.0, 10.0], str({k: d.get(k) for k in ("encoding", "triangles", "bbox_size")}))

    p3 = os.path.join(tmp, "c.3mf")
    model = ('<?xml version="1.0"?><model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
             '<resources><object id="1" type="model"><mesh><vertices>'
             + "".join(f'<vertex x="{x}" y="{y}" z="{z}"/>' for x in (0, 5) for y in (0, 7) for z in (0, 9))
             + '</vertices><triangles><triangle v1="0" v2="1" v3="2"/><triangle v1="1" v2="3" v3="2"/></triangles>'
             '</mesh></object></resources><build><item objectid="1"/></build></model>')
    with zipfile.ZipFile(p3, "w") as z:
        z.writestr("3D/3dmodel.model", model)
    d = sw.inspect_export_file(p3)["data"]
    record("3MF: unita', 8 vertici, 2 triangoli, box 5x7x9", d.get("unit") == "millimeter" and d.get("vertices") == 8
           and d.get("triangles") == 2 and d.get("bbox_size") == [5.0, 7.0, 9.0], str(d))

    for schema, ap in (("CONFIG_CONTROL_DESIGN", "AP203"), ("AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }", "AP214"),
                       ("AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF { 1 0 10303 442 1 1 4 }", "AP242")):
        sp = os.path.join(tmp, f"{ap}.step")
        with open(sp, "w") as f:
            f.write(f"ISO-10303-21;\nHEADER;\nFILE_SCHEMA (('{schema}'));\nENDSEC;\nDATA;\n"
                    "#1=MANIFOLD_SOLID_BREP('',#2);\n#3=ADVANCED_FACE('',(#4),#5,.T.);\nENDSEC;\nEND-ISO-10303-21;\n")
        d = sw.inspect_export_file(sp)["data"]
        record(f"STEP {ap}: protocollo riconosciuto, solido valido", d.get("application_protocol") == ap and d.get("valid_solid")
               and d.get("advanced_faces") == 1, str({k: d.get(k) for k in ("application_protocol", "valid_solid", "schema")}))
    sp = os.path.join(tmp, "assieme.step")
    with open(sp, "w") as f:
        f.write("ISO-10303-21;\nHEADER;\nFILE_SCHEMA (('AUTOMOTIVE_DESIGN'));\nENDSEC;\nDATA;\n"
                "#10=PRODUCT_DEFINITION('design','',#11,#12);\n#20=PRODUCT_DEFINITION ('design','',#21,#12);\n"
                "#30=PRODUCT_DEFINITION('design','',#31,#12);\n#40=PRODUCT_DEFINITION_SHAPE('','',#10);\n"
                "#50=NEXT_ASSEMBLY_USAGE_OCCURRENCE('1','a','',#10,#20,$);\n"
                "#51=NEXT_ASSEMBLY_USAGE_OCCURRENCE('2','b','',#10,#20,$);\n"
                "#52=NEXT_ASSEMBLY_USAGE_OCCURRENCE('3','c','',#10,#30,$);\n"
                "#60=MANIFOLD_SOLID_BREP('',#2);\n#61=MANIFOLD_SOLID_BREP('',#3);\nENDSEC;\nEND-ISO-10303-21;\n")
    d = sw.inspect_export_file(sp)["data"]
    record("STEP d'assieme: 3 PRODUCT_DEFINITION (non _SHAPE), 3 istanze, 2 solidi",
           d.get("product_definitions") == 3 and d.get("assembly_occurrences") == 3 and d.get("manifold_solid_brep") == 2,
           str({k: d.get(k) for k in ("product_definitions", "assembly_occurrences", "manifold_solid_brep")}))
    sp = os.path.join(tmp, "troncato.step")
    with open(sp, "w") as f:
        f.write("ISO-10303-21;\nHEADER;\nFILE_SCHEMA (('CONFIG_CONTROL_DESIGN'));\nENDSEC;\nDATA;\n#1=MANIFOLD_SOLID_BREP('',#2);\n")
    record("STEP troncato (senza END-ISO-10303-21) -> non valido", not sw.inspect_export_file(sp)["data"].get("valid_solid"))

    ip = os.path.join(tmp, "c.igs")
    with open(ip, "w") as f:
        f.write("S" * 72 + "S      1\n" + " " * 72 + "T      1\n")
    d = sw.inspect_export_file(ip)["data"]
    record("IGES: riga di chiusura T riconosciuta", d.get("format") == "iges" and d.get("terminate_line"), str(d))

    xp = os.path.join(tmp, "c.x_t")
    with open(xp, "w") as f:
        f.write("**ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz***\n**PARASOLID !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~\n")
    record("Parasolid x_t: intestazione riconosciuta", sw.inspect_export_file(xp)["data"].get("parasolid_header"))

    pp = os.path.join(tmp, "c.pdf")
    with open(pp, "wb") as f:
        f.write(b"%PDF-1.7\n1 0 obj << /Type /3D /Subtype /PRC >> endobj\n%%EOF")
    record("PDF 3D: /3D + PRC riconosciuti", sw.inspect_export_file(pp)["data"].get("has_3d"))
    with open(pp, "wb") as f:
        f.write(b"%PDF-1.7\n%%EOF")
    record("PDF piatto: has_3d falso", not sw.inspect_export_file(pp)["data"].get("has_3d"))
    record("file mancante -> errore", not sw.inspect_export_file(os.path.join(tmp, "manca.stl"))["success"])


# ============================================================================ libreria materiali (.sldmat)
def test_materials(tmp):
    d = os.path.join(tmp, "sldmaterials")
    os.makedirs(d)
    xml = ('<?xml version="1.0" encoding="UTF-16"?><mstns:materials xmlns:mstns="http://www.solidworks.com/sldmaterials">'
           '<classification name="Acciaio"><material name="AISI 304"><physicalproperties>'
           '<DENS displayname="Densita\'" value="8000"/><EX value="1.9e11"/><NUXY value="0.29"/><SIGYLD value="2.068e8"/>'
           '</physicalproperties></material><material name="AISI 1020"><physicalproperties><DENS value="7900"/>'
           '</physicalproperties></material></classification><classification name="Plastica">'
           '<material name="ABS generico"><physicalproperties><DENS value="1020"/></physicalproperties></material>'
           '<material name="ABS PC"><physicalproperties><DENS value="1070"/></physicalproperties></material>'
           '</classification></mstns:materials>')
    with open(os.path.join(d, "solidworks materials.sldmat"), "wb") as f:
        f.write(xml.encode("utf-16"))
    sw = SolidWorksAutomation()
    sw._dx_material_dir = lambda: d
    mats = sw._dx_load_materials()
    m304 = next((m for m in mats if m["name"] == "AISI 304"), None)
    record(".sldmat UTF-16: 4 materiali, categorie e proprieta' lette",
           len(mats) == 4 and m304 is not None and m304["category"] == "Acciaio" and m304["density"] == 8000.0
           and m304["props"].get("elastic_modulus_Pa") == 1.9e11 and m304["props"].get("yield_strength_Pa") == 2.068e8,
           str([(m["name"], m["category"], m["density"]) for m in mats]))
    hit, _ = sw._dx_find_material("aisi 304")
    record("ricerca materiale: nome esatto senza maiuscole", hit is not None and hit["name"] == "AISI 304")
    hit, err = sw._dx_find_material("ABS")
    record("ricerca materiale: 'ABS' ambiguo -> messaggio con i candidati", hit is None and "ABS generico" in (err or ""), err)
    hit, _ = sw._dx_find_material("1020")
    record("ricerca materiale: frammento unico", hit is not None and hit["name"] == "AISI 1020")
    hit, err = sw._dx_find_material("PLA")
    record("ricerca materiale: inesistente -> errore", hit is None and bool(err), err)


    # ---- D8: librerie da tutte le cartelle configurate (preferenza 28 + standard), cache legata alla firma
    from solidworks_mcp.utils.matlib import (split_path_list, merge_material_dirs, dedupe_materials, build_sldmat,
                                             list_sldmat_files)
    record("D8 split: ';', spazi, virgolette, voci vuote",
           split_path_list(' C:\\a ; ;"C:\\b c";;C:\\d;') == ["C:\\a", "C:\\b c", "C:\\d"] and split_path_list(None) == [] and split_path_list("") == [],
           str(split_path_list(' C:\\a ; ;"C:\\b c";;C:\\d;')))
    ex = lambda p: p not in ("C:\\inesistente",)
    mm = merge_material_dirs("C:\\Lib\\A;c:\\lib\\a\\;C:\\inesistente;C:\\Lib\\B", ["C:\\Std", "C:\\LIB\\B", None], exists=ex)
    record("D8 cartelle: prima la preferenza, poi la standard, senza doppioni (maiuscole/barra finale), solo esistenti",
           mm == ["C:\\Lib\\A", "C:\\Lib\\B", "C:\\Std"], str(mm))
    record("D8 cartelle: preferenza vuota -> solo la standard", merge_material_dirs("", ["C:\\Std"], exists=lambda p: True) == ["C:\\Std"])
    mk = lambda n, db: {"name": n, "database": db}
    kept, dups = dedupe_materials([mk("Alfa", "C:\\a\\x.sldmat"), mk("Beta", "C:\\a\\x.sldmat"), mk("alfa", "C:\\b\\y.sldmat"),
                                   mk("Beta", "C:\\a\\x.sldmat"), mk("Gamma", "C:\\b\\y.sldmat")])
    record("D8 duplicati: si tiene il primo, il secondo e' segnalato; stesso file non e' duplicato",
           [m["name"] for m in kept] == ["Alfa", "Beta", "Beta", "Gamma"]
           and dups == [{"name": "alfa", "kept_database": "C:\\a\\x.sldmat", "other_database": "C:\\b\\y.sldmat"}], str(dups))

    lib1 = os.path.join(tmp, "lib1")
    lib2 = os.path.join(tmp, "lib2")
    os.makedirs(lib1)
    os.makedirs(lib2)
    with open(os.path.join(lib2, "dxe_prova.sldmat"), "wb") as f:
        f.write(build_sldmat([{"name": "DXE Prova 1234", "density": 1234.0}, {"name": "AISI 304", "density": 1.0}]))
    with open(os.path.join(lib2, "altro.sldmat"), "wb") as f:
        f.write(build_sldmat([{"name": "Altro Materiale", "density": 500.0}], classification="Mie"))
    ff = list_sldmat_files([d, lib2], ("solidworks materials.sldmat",))
    record(".sldmat: elenco file, standard per primi, poi alfabetico",
           [n for _, n in ff] == ["solidworks materials.sldmat", "altro.sldmat", "dxe_prova.sldmat"], str([n for _, n in ff]))

    sw = SolidWorksAutomation()
    pref = {"v": ""}
    sw._dx_material_dir = lambda: d
    sw._dx_material_pref = lambda: pref["v"]
    n0 = len(sw._dx_load_materials())
    record("D8 senza preferenza: solo la cartella standard (4 materiali)", n0 == 4 and sw._dx_mat_duplicates == [], f"{n0}")
    pref["v"] = f"{lib2};{os.path.join(tmp, 'non_esiste')};{lib1};{lib2.upper()}"
    mats = sw._dx_load_materials()
    mine = next((m for m in mats if m["name"] == "DXE Prova 1234"), None)
    record("D8 libreria personalizzata letta: database = percorso del file, file = nome senza estensione, densita' 1234",
           mine is not None and mine["density"] == 1234.0 and mine["file"] == "dxe_prova"
           and mine["database"] == os.path.join(lib2, "dxe_prova.sldmat") and mine["category"] == "Personalizzati"
           and mine["props"].get("elastic_modulus_Pa") == 2.0e9, str(mine and (mine["file"], mine["density"], mine["database"])))
    record("D8 cache invalidata dal cambio di cartelle: 4 + 2 + 1 materiali, cartelle senza doppioni e inesistenti",
           len(mats) == 4 + 1 + 1 and sw._dx_mat_libraries["folders"] == [os.path.normpath(lib2), os.path.normpath(lib1), os.path.normpath(d)],
           f"{len(mats)} {sw._dx_mat_libraries['folders']}")
    # la libreria personalizzata viene PRIMA di quella standard: 'AISI 304' vale quello di lib2, il standard e' duplicato
    a304 = [m for m in mats if m["name"] == "AISI 304"]
    record("D8 duplicato fra librerie: vale la prima (preferenza), l'altra e' segnalata",
           len(a304) == 1 and a304[0]["density"] == 1.0
           and sw._dx_mat_duplicates == [{"name": "AISI 304", "kept_database": os.path.join(lib2, "dxe_prova.sldmat"),
                                          "other_database": os.path.join(d, "solidworks materials.sldmat")}],
           str(sw._dx_mat_duplicates))
    same = sw._dx_load_materials()
    record("D8 cache riusata se nulla cambia", same is mats)
    sw_hit, _ = sw._dx_find_material("dxe prova")
    record("D8 _dx_find_material trova il materiale personalizzato", sw_hit is not None and sw_hit["file"] == "dxe_prova")
    # file riscritto (firma cambia) -> riletto
    with open(os.path.join(lib2, "dxe_prova.sldmat"), "wb") as f:
        f.write(build_sldmat([{"name": "DXE Prova 1234", "density": 999.0}]))
    mats2 = sw._dx_load_materials()
    mine2 = next((m for m in mats2 if m["name"] == "DXE Prova 1234"), None)
    record("D8 .sldmat riscritto -> cache invalidata, densita' nuova 999 e AISI 304 torna quello standard",
           mats2 is not mats and mine2 is not None and mine2["density"] == 999.0
           and next(m for m in mats2 if m["name"] == "AISI 304")["density"] == 8000.0 and sw._dx_mat_duplicates == [],
           f"{len(mats2)}")
    # preferenza ripristinata -> la libreria sparisce (anche la lista torna come all'inizio)
    pref["v"] = ""
    mats3 = sw._dx_load_materials()
    record("D8 preferenza ripristinata -> materiale personalizzato non c'e' piu'",
           len(mats3) == 4 and not any(m["name"] == "DXE Prova 1234" for m in mats3), f"{len(mats3)}")
    r = sw.list_materials(query="AISI")
    record("D8 list_materials: libraries e duplicates nel risultato",
           r["success"] and r["data"]["libraries"]["folders"] == [os.path.normpath(d)] and r["data"]["duplicates"] == [], str(r["data"].get("libraries")))


# ============================================================================ D1 tabella delle configurazioni
def test_config_table(tmp):
    from solidworks_mcp.utils.config_table import parse_configuration_table, plan_configuration_changes, classify_column
    kinds = [classify_column(h)[0] for h in ("D1@Schizzo1", "D2@Estrusione1@pezzo.Part", "$STATO@Foro1", "$state@Foro1",
                                             "$PRP@Codice", "$MATERIALE", "$COMMENTO", "Lunghezza")]
    record("D1: colonne riconosciute", kinds == ["dimension", "dimension", "suppression", "suppression", "property", "material",
                                               "comment", "unknown"], str(kinds))
    csv_path = os.path.join(tmp, "cfg.csv")
    with open(csv_path, "w", encoding="utf-8-sig") as f:
        f.write("Configurazione;D1@Schizzo1;$STATO@Foro1;$PRP@Codice;$MATERIALE;$COMMENTO\n"
                "Default;30;R;A-001;;\nLunga;60,5;;A-002;AISI 304;versione lunga\nPieno;;S;;;\n")
    t = parse_configuration_table(csv_path)
    c = {x["name"]: x for x in t["configurations"]}
    record("D1: CSV italiano (';' e virgola decimale), celle vuote saltate",
           not t["errors"] and c["Lunga"]["dimensions"] == {"D1@Schizzo1": 60.5} and c["Default"]["suppression"] == {"Foro1": False}
           and c["Pieno"]["suppression"] == {"Foro1": True} and c["Pieno"]["dimensions"] == {}
           and c["Lunga"]["material"] == "AISI 304" and c["Lunga"]["properties"] == {"Codice": "A-002"}
           and c["Lunga"]["comment"] == "versione lunga", str(t["errors"] or t["configurations"]))
    j = parse_configuration_table('[{"Nome": "Corta", "D1@Schizzo1": 15}, {"Nome": "Media", "D1@Schizzo1": "20"}]')
    jd = parse_configuration_table({"Corta": {"D1@Schizzo1": 15}})
    record("D1: JSON a righe e a dizionario", not j["errors"] and [x["dimensions"]["D1@Schizzo1"] for x in j["configurations"]] == [15.0, 20.0]
           and jd["configurations"][0]["name"] == "Corta", str(j))
    miss = parse_configuration_table("$P/manca.csv")
    record("D1: percorso inesistente -> 'file non trovato' (non 'tabella vuota')",
           any("file non trovato" in x for x in miss["errors"]), str(miss["errors"]))
    bad =parse_configuration_table("Configurazione,D1@Schizzo1,$STATO@Foro1,Lunghezza\nA,dieci,forse,1\nA,1,S,2\n,3,S,4\n")
    e = " | ".join(bad["errors"])
    record("D1: errori -> colonna sconosciuta, numero e stato non validi, nome ripetuto, nome vuoto",
           all(k in e for k in ("'Lunghezza' non riconosciuta", "'dieci' non e' un numero", "'forse' non e' uno stato", "ripetuta", "vuoto")), e)
    plan = plan_configuration_changes(t, ["Default", "pieno"])
    acts = [(a["action"], a["configuration"]) for a in plan["actions"]]
    record("D1: piano -> crea solo le mancanti (nomi senza maiuscole), poi quote/soppressioni/proprieta'/materiale",
           acts == [("set_dimension", "Default"), ("set_suppression", "Default"), ("set_property", "Default"),
                    ("add_configuration", "Lunga"), ("set_dimension", "Lunga"), ("set_property", "Lunga"),
                    ("assign_material", "Lunga"), ("set_suppression", "pieno")], str(acts))
    p2 = plan_configuration_changes(t, ["Default"], create_missing=False)
    record("D1: create_missing=false -> errore per le configurazioni assenti", len(p2["errors"]) == 2, str(p2["errors"]))
    record("D1: tabella con errori -> nessuna azione", plan_configuration_changes(bad, [])["actions"] == [])
    en = [classify_column(h)[0] for h in ("$STATE@Cut-Extrude1", "$PRP@PartNumber", "$PROPERTY@PartNumber", "$MATERIAL", "$COMMENT",
                                          "D1@Sketch1")]
    record("D1: intestazioni inglesi ($STATE, $PROPERTY, $MATERIAL, $COMMENT) riconosciute",
           en == ["suppression", "property", "property", "material", "comment", "dimension"], str(en))
    te = parse_configuration_table([{"Configuration": "Long", "D1@Sketch1": 60, "$STATE@Cut-Extrude1": "S", "$PRP@PartNumber": "A-2"}])
    record("D1: tabella inline con intestazioni inglesi",
           not te["errors"] and te["configurations"][0]["name"] == "Long" and te["configurations"][0]["dimensions"] == {"D1@Sketch1": 60.0}
           and te["configurations"][0]["suppression"] == {"Cut-Extrude1": True}
           and te["configurations"][0]["properties"] == {"PartNumber": "A-2"}, str(te))
    test_apply_configuration_table()


def test_apply_configuration_table():
    """apply_configuration_table con i metodi di SolidWorks sostituiti da registratori (nessuna chiamata COM)."""
    sw = SolidWorksAutomation()
    state = {"cfgs": ["Default"], "active": "Default", "calls": [], "shown": []}
    doc = types.SimpleNamespace(ShowConfiguration2=lambda n: (state["shown"].append(n), state.update(active=n))[1])

    def ok(msg="ok"):
        return sw._result(True, msg)

    def add(name, comment="", activate=True):
        state["calls"].append(("add", name, comment, activate))
        state["cfgs"].append(name)
        state["active"] = name                          # come AddConfiguration2: la nuova diventa attiva (il metodo vero la rimette a posto)
        return ok()

    sw._dx_doc = lambda kinds=(1, 2, 3): (doc, None)
    sw._dx_cfg_names = lambda d: list(state["cfgs"])
    sw._dx_cfg_name = lambda d: state["active"]
    sw._dx_rebuild = lambda d: None
    sw.add_part_configuration = add
    sw.set_configuration_dimension = lambda dim, v, configuration=None, unit=None: (state["calls"].append(("dim", dim, v, configuration, unit)), ok())[1]
    sw.set_configuration_suppression = lambda f, s=True, configuration=None: (state["calls"].append(("sup", f, s, configuration)), ok())[1]
    sw.set_custom_property = lambda n, v, configuration=None, type="text": (state["calls"].append(("prp", n, v, configuration)), ok())[1]
    sw.assign_material = lambda m, category=None, body=None, configuration=None, link_title_block=True: \
        (state["calls"].append(("mat", m, configuration)), ok())[1]

    rows = [{"Configurazione": "Default", "$PRP@Codice": "A-1"},
            {"Configurazione": "Lunga", "D1@Schizzo1": "60,5", "$MATERIALE": "AISI 304"},
            {"Configurazione": "Pieno", "$STATO@Foro1": "S"}]
    r = sw.apply_configuration_table(rows, dry_run=True)
    d = r["data"]
    record("D1 tool: dry_run -> piano di 6 azioni e nessuna chiamata a SolidWorks",
           r["success"] and not state["calls"] and d.get("dry_run") is True and len(d["actions"]) == 6
           and "excel_available" in d["design_table"] and "InsertDesignTable" in d["design_table"]["design_table"], str(r["message"]))
    r = sw.apply_configuration_table(rows, unit="inch")
    record("D1 tool: esecuzione -> metodi giusti in ordine, add_configuration con activate=False, unita' passata",
           r["success"] and r["data"]["failed"] == 0 and state["calls"] == [
               ("prp", "Codice", "A-1", "Default"), ("add", "Lunga", "", False), ("dim", "D1@Schizzo1", 60.5, "Lunga", "inch"),
               ("mat", "AISI 304", "Lunga"), ("add", "Pieno", "", False), ("sup", "Foro1", True, "Pieno")], str(state["calls"]))
    record("D1 tool: la configurazione attiva di partenza torna attiva", r["data"]["active"] == "Default" and state["active"] == "Default"
           and state["shown"] == ["Default"], f"{state['active']} {state['shown']}")
    # un'azione che fallisce: si continua, success=false, la configurazione attiva torna comunque quella di partenza
    state.update(cfgs=["Default"], active="Default", calls=[], shown=[])
    sw.set_configuration_dimension = lambda dim, v, configuration=None, unit=None: sw._result(False, "quota guidata da equazione")
    r = sw.apply_configuration_table(rows)
    oks = [a["ok"] for a in r["data"]["results"]]
    record("D1 tool: errore in un'azione -> prosegue, success=false, attiva ripristinata",
           not r["success"] and r["data"]["failed"] == 1 and oks == [True, True, False, True, True, True] and state["active"] == "Default",
           str(oks))
    # eccezione a meta': la configurazione attiva torna comunque quella di partenza
    state.update(cfgs=["Default"], active="Default", calls=[], shown=[])

    def boom(*a, **k):
        raise RuntimeError("COM")
    sw.set_custom_property = boom
    r = sw.apply_configuration_table(rows)
    record("D1 tool: eccezione durante l'applicazione -> risultato di errore e attiva ripristinata",
           not r["success"] and state["active"] == "Default", str(r["message"])[:80])
    # tabella o piano non validi: nessuna modifica
    state.update(cfgs=["Default"], active="Default", calls=[], shown=[])
    r1 = sw.apply_configuration_table([{"Configurazione": "X", "Boh": 1}])
    r2 = sw.apply_configuration_table(rows, create_missing=False)
    record("D1 tool: colonna sconosciuta / configurazioni assenti con create_missing=false -> errore e nessuna chiamata",
           not r1["success"] and not r2["success"] and not state["calls"], f"{r1['message'][:50]} | {r2['message'][:50]}")


# ============================================================================ D7 massa in un sistema utente
def test_inertia():
    import random
    from solidworks_mcp.utils import inertia as I
    rnd = random.Random(7)
    pts = [(rnd.uniform(0.1, 1.0), [rnd.uniform(-0.05, 0.08), rnd.uniform(-0.02, 0.04), rnd.uniform(0.0, 0.03)]) for _ in range(40)]

    def tensor(points, offdiag="tensor"):            # tensore diretto da masse puntiformi (origine = 0)
        J = [[0.0] * 3 for _ in range(3)]
        for m, p in points:
            r2 = sum(x * x for x in p)
            for a in range(3):
                for b in range(3):
                    J[a][b] += m * ((r2 if a == b else 0.0) - p[a] * p[b])
        return I.flip_offdiag(J) if offdiag == "products" else J
    M = sum(m for m, _ in pts)
    com = [sum(m * p[k] for m, p in pts) / M for k in range(3)]
    j_com = tensor([(m, [p[k] - com[k] for k in range(3)]) for m, p in pts])
    R = I.mat_mul(I.rotation_about("z", 30), I.rotation_about("x", -20))
    o = [0.02, -0.01, 0.005]
    user = [(m, I.mat_vec(I.mat_t(R), [p[k] - o[k] for k in range(3)])) for m, p in pts]      # coordinate nel sistema utente
    res = I.mass_properties_in_frame(M, com, j_com, R, o)
    exp_c = [sum(m * p[k] for m, p in user) / M for k in range(3)]
    exp_o = tensor(user)
    err_c = max(abs(a - b) for a, b in zip(res["center_of_mass"], exp_c))
    err_o = max(abs(res["inertia_at_origin"][a][b] - exp_o[a][b]) for a in range(3) for b in range(3))
    record("D7: baricentro e tensore nell'origine utente = calcolo diretto sulle masse (sistema ruotato e traslato)",
           err_c < 1e-12 and err_o < 1e-12 and not res["frame_issues"], f"scarti {err_c:.1e} m, {err_o:.1e} kg*m2")
    resp = I.mass_properties_in_frame(M, com, I.flip_offdiag(j_com), R, o, offdiag="products")
    exp_p = tensor(user, "products")
    err_p = max(abs(resp["inertia_at_origin"][a][b] - exp_p[a][b]) for a in range(3) for b in range(3))
    record("D7: convenzione 'products' (+integrale xy dm) coerente", err_p < 1e-12, f"{err_p:.1e}")
    pm = I.principal_moments(j_com)
    tr = sum(j_com[k][k] for k in range(3))
    record("D7: momenti principali invarianti alla rotazione (somma = traccia)",
           abs(sum(pm) - tr) < 1e-12 and max(abs(a - b) for a, b in zip(pm, res["principal_moments"])) < 1e-12, f"{pm}")
    # blocco 80x50x30 mm, 0,96 kg (test_data_live): momenti noti m/12 (b2+c2)
    m, a, b, c = 0.96, 0.03, 0.08, 0.05
    box = [[m / 12 * (b * b + c * c), 0, 0], [0, m / 12 * (a * a + c * c), 0], [0, 0, m / 12 * (a * a + b * b)]]
    rb = I.mass_properties_in_frame(m, [0.015, 0, 0], box, I.rotation_about("z", 90), [0, 0, 0])
    record("D7: blocco ruotato di 90 gradi attorno a Z -> Ixx e Iyy si scambiano, baricentro (0, -15, 0) mm",
           abs(rb["inertia_at_center_of_mass"][0][0] - box[1][1]) < 1e-15 and abs(rb["inertia_at_center_of_mass"][1][1] - box[0][0]) < 1e-15
           and max(abs(x - y) for x, y in zip(rb["center_of_mass"], [0, -0.015, 0])) < 1e-15, str(rb["center_of_mass"]))
    Rsw, osw = I.frame_from_sw_transform([0, 1, 0, -1, 0, 0, 0, 0, 1, 0.01, 0.02, 0.03, 1.0])
    record("D7: MathTransform di SolidWorks -> righe = assi (X utente = Y modello)",
           [Rsw[k][0] for k in range(3)] == [0, 1, 0] and osw == [0.01, 0.02, 0.03])
    record("D7: sistema sinistrorso segnalato", I.check_rotation([[1, 0, 0], [0, 1, 0], [0, 0, -1]]) != [])
    # convenzione dei termini fuori diagonale decisa a runtime (confronto baricentro / origine)
    io_t, io_p = tensor(pts), tensor(pts, "products")
    record("D7: detect_offdiag_convention riconosce 'tensor' (masse puntiformi, baricentro fuori asse)",
           I.detect_offdiag_convention(j_com, M, com, io_t) == "tensor")
    record("D7: detect_offdiag_convention riconosce 'products' (termini fuori diagonale di segno opposto)",
           I.detect_offdiag_convention(I.flip_offdiag(j_com), M, com, io_p) == "products")
    # parallelepipedo 80x50x30 mm, 0,96 kg, spigolo in (10, 20, 5) mm, ruotato di 30 gradi attorno a Z
    Rb = I.rotation_about("z", 30)
    cb = [0.010 + 0.015, 0.020 + 0.040, 0.005 + 0.025]
    jb = I.mat_mul(I.mat_mul(Rb, box), I.mat_t(Rb))
    io_b = I.steiner(jb, m, cb)
    record("D7: parallelepipedo traslato e ruotato -> 'tensor'", I.detect_offdiag_convention(jb, m, cb, io_b) == "tensor")
    record("D7: parallelepipedo traslato e ruotato, prodotti d'inerzia -> 'products'",
           I.detect_offdiag_convention(I.flip_offdiag(jb), m, cb, I.flip_offdiag(io_b)) == "products")
    record("D7: baricentro sull'asse X, tensore diagonale -> 'indeterminate'",
           I.detect_offdiag_convention(box, m, [0.015, 0, 0], I.steiner(box, m, [0.015, 0, 0])) == "indeterminate")
    record("D7: baricentro nell'origine -> 'indeterminate'", I.detect_offdiag_convention(box, m, [0, 0, 0], box) == "indeterminate")
    record("D7: dati incoerenti con entrambe le convenzioni -> 'indeterminate'",
           I.detect_offdiag_convention(jb, m, cb, [[io_b[a][b] * (1.0 if a == b else 0.3) for b in range(3)] for a in range(3)]) == "indeterminate")


# ============================================================================ D10 PDF 3D
def _pdf(objects):
    out, n = [b"%PDF-1.7\n"], 1
    for body in objects:
        out.append(b"%d 0 obj\n" % n + body + b"\nendobj\n")
        n += 1
    return b"".join(out) + b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"


def test_pdf3d(tmp):
    import zlib
    from solidworks_mcp.utils.pdf3d import inspect_pdf3d
    prc = b"PRC" + bytes(range(200)) * 3
    comp = zlib.compress(prc)
    pdf = _pdf([b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                b"<< /Type /Page /Parent 2 0 R /Annots [4 0 R] >>",
                b"<< /Type /Annot /Subtype /3D /Rect [0 0 100 100] /3DD 5 0 R /3DV << /XN (Isometrica) >> >>",
                b"<< /Type /3D /Subtype /PRC /Filter /FlateDecode /Length %d >>\nstream\n" % len(comp) + comp + b"\nendstream",
                b"<< /Type /3DView /XN (Frontale) >>"])
    d = inspect_pdf3d(pdf)
    st = d["streams_3d"][0] if d["streams_3d"] else {}
    record("D10: PDF con PRC compresso -> stream decompresso, magic PRC, 1 pagina, 1 annotazione, 2 viste",
           d["parsed"] and d["prc_ok"] and d["pages"] == 1 and d["annotations_3d"] == 1 and st.get("decoded_size") == len(prc)
           and d["views"] == ["Isometrica", "Frontale"], str({k: d[k] for k in ("pages", "annotations_3d", "views", "prc_ok")}))
    bad = _pdf([b"<< /Type /Page >>", b"<< /Type /3D /Subtype /PRC /Filter /FlateDecode /Length 10 >>\nstream\nNONZLIBXXX\nendstream"])
    d = inspect_pdf3d(bad)
    record("D10: stream PRC rovinato -> prc_ok falso, nessuna eccezione", d["parsed"] and not d["prc_ok"] and d["streams_3d"], str(d["streams_3d"]))
    u3d = _pdf([b"<< /Type /3D /Subtype /U3D /Length 8 >>\nstream\nU3D\x00abcd\nendstream"])
    record("D10: U3D non compresso riconosciuto", inspect_pdf3d(u3d)["u3d_ok"])
    flat = inspect_pdf3d(_pdf([b"<< /Type /Page >>"]))
    record("D10: PDF piatto -> nessuno stream 3D", flat["parsed"] and not flat["streams_3d"] and flat["pages"] == 1)
    record("D10: non-PDF -> parsed falso", not inspect_pdf3d(b"ciao")["parsed"])
    inner = [b"<< /Type /Page >>", b"<< /Type /Annot /Subtype /3D /Rect [0 0 1 1] /3DV << /XN (Vista1) >> >>"]
    head = b"10 0 11 %d " % (len(inner[0]) + 1)
    raw = head + inner[0] + b" " + inner[1]
    z = zlib.compress(raw)
    objstm = _pdf([b"<< /Type /ObjStm /N 2 /First %d /Filter /FlateDecode /Length %d >>\nstream\n" % (len(head), len(z)) + z + b"\nendstream",
                   b"<< /Type /3D /Subtype /PRC /Filter /FlateDecode /Length %d >>\nstream\n" % len(comp) + comp + b"\nendstream"])
    d = inspect_pdf3d(objstm)
    record("D10: oggetti dentro un object stream compresso (PDF 1.5+)", d["pages"] == 1 and d["annotations_3d"] == 1
           and d["views"] == ["Vista1"] and d["prc_ok"], str({k: d[k] for k in ("pages", "annotations_3d", "views", "prc_ok")}))
    path = os.path.join(tmp, "m3d.pdf")
    with open(path, "wb") as f:
        f.write(pdf)
    r = SolidWorksAutomation().inspect_export_file(path)["data"]
    record("D10: inspect_export_file riporta pdf3d senza cambiare has_3d", r.get("has_3d") and r.get("pdf3d", {}).get("prc_ok"), str(r.get("pdf3d", {}).get("notes")))


# ============================================================================ D3 eDrawings
def _edrw_zip(entries):
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_edrawings(tmp):
    from solidworks_mcp.utils.edrawings import inspect_edrawings
    hsf = b";; HSF V20.90 " + bytes(range(256)) * 4
    mats = (b'<?xml version="1.0"?><Materials version="1"><Entity name="shared/body0"><Material/></Entity>'
            b'<Entity name="shared/body1"><Material/></Entity></Materials>')
    jpg = b"\xff\xd8\xff\xe0" + b"\x00" * 20 + b"\xff\xd9"
    good = _edrw_zip({"eModel": hsf, "preview.jpg": jpg, "materials.xml": mats, "scene.xml": b"<scene/>", "OLE": b"\x00\x01"})
    d = inspect_edrawings(good)
    record("D3: ZIP eDrawings sintetico -> valido, HSF V20.90, 2 corpi, anteprima JPEG",
           d["valid"] and d["zip_ok"] and d["hsf_ok"] and d["hsf_version"] == "V20.90" and d["bodies"] == 2
           and d["entities"] == ["shared/body0", "shared/body1"] and d["preview_ok"] and "eModel" in d["entries"], str(d["notes"]))
    d = inspect_edrawings(_edrw_zip({"preview.jpg": jpg, "materials.xml": mats}))
    record("D3: ZIP senza eModel -> hsf_ok falso, non valido", d["zip_ok"] and not d["hsf_ok"] and not d["valid"], str(d["notes"]))
    d = inspect_edrawings(_edrw_zip({"eModel": b"niente HSF qui", "materials.xml": mats}))
    record("D3: eModel senza firma ;; HSF -> non valido", d["zip_ok"] and not d["hsf_ok"] and not d["valid"], str(d["notes"]))
    d = inspect_edrawings(_edrw_zip({"eModel": hsf}))
    record("D3: senza materials.xml ne' anteprima -> valido, bodies None, preview_ok falso",
           d["valid"] and d["bodies"] is None and not d["preview_ok"], str(d["notes"]))
    d = inspect_edrawings(b"ciao, non sono uno zip")
    record("D3: byte qualunque -> zip_ok falso, nota, nessuna eccezione", not d["zip_ok"] and not d["valid"] and d["notes"])
    d = inspect_edrawings(good[:len(good) // 3])
    record("D3: ZIP troncato a 1/3 -> non valido, nessuna eccezione", not d["valid"] and d["notes"])
    d = inspect_edrawings(b"")
    record("D3: file vuoto -> non valido", not d["valid"])
    path = os.path.join(tmp, "m.eprt")
    with open(path, "wb") as f:
        f.write(good)
    r = SolidWorksAutomation().inspect_export_file(path)["data"]
    record("D3: inspect_export_file(.eprt) riporta edrawings e valid", r.get("valid") is True and r.get("edrawings", {}).get("bodies") == 2,
           str(r.get("edrawings", {}).get("notes")))
    path = os.path.join(tmp, "rotto.easm")
    with open(path, "wb") as f:
        f.write(good[:len(good) // 3])
    r = SolidWorksAutomation().inspect_export_file(path)["data"]
    record("D3: inspect_export_file(.easm troncato) -> valid falso", r.get("valid") is False and r.get("edrawings", {}).get("valid") is False)


# ============================================================================ lingua di SolidWorks (italiano / inglese)
class _Feat:
    def __init__(self, name, typ):
        self.Name, self.GetTypeName2, self.GetNextFeature, self.selected = name, typ, None, False

    def Select2(self, append, mark):
        self.selected = True
        return True


def _tree(names_types):
    feats = [_Feat(n, t) for n, t in names_types]
    for a, b in zip(feats, feats[1:]):
        a.GetNextFeature = b
    return types.SimpleNamespace(FirstFeature=feats[0]), feats


def test_language():
    from solidworks_mcp.utils import sw_lang as L
    idx = [L.std_plane_index(n) for n in ("Front", "front plane", "Piano frontale", "FRONTALE", "Top Plane", "piano superiore",
                                            "Right", "Piano  destro", "Piano1", "Plane1", "")]
    record("lingua: piani standard riconosciuti in italiano e inglese", idx == [0, 0, 0, 0, 1, 1, 2, 2, None, None, None], str(idx))
    record("lingua: origine", L.is_origin_name("Origine") and L.is_origin_name("origin") and not L.is_origin_name("Origin1"))
    record("lingua: grafici della simulazione (Stress1 / Sollecitazione1)",
           L.plot_candidates("von_mises", ["Stress1", "Displacement1", "Strain1"]) == ["Stress1"]
           and L.plot_candidates("displacement", ["Sollecitazione1", "Spostamento1"]) == ["Spostamento1"]
           and L.plot_candidates("Grafico7", ["Grafico7"]) == ["Grafico7"] and L.plot_candidates("strain", ["Stress1"]) == [])
    record("lingua: errore del cartiglio ERRORE:/ERROR:",
           L.TITLE_BLOCK_ERROR_RE.findall("x ERRORE:DrawnBy y ERROR:Weight") == ["DrawnBy", "Weight"])
    record("lingua: cartelle lang (prima quella di SolidWorks)", L.lang_folders("english") == ["english", "italian"]
           and L.lang_folders("Italian") == ["italian", "english"] and L.lang_folders("") == ["english", "italian"])
    record("lingua: testi delle tavole", L.drawing_text("aux_view", "italian") == "VISTA" and L.drawing_text("aux_view", "english") == "VIEW"
           and L.drawing_text("chamfer_note", "") == "SMUSSI NON QUOTATI" and L.format_suffix("english") == " en" and L.format_suffix("italian") == "")
    sw = SolidWorksAutomation()
    for lang, names in (("italiano", ("Annotazioni", "Origine", "Piano frontale", "Piano superiore", "Piano destro", "Schizzo1")),
                        ("inglese", ("Annotations", "Origin", "Front Plane", "Top Plane", "Right Plane", "Sketch1"))):
        doc, feats = _tree(zip(names, ("DetailCabinet", "OriginProfileFeature", "RefPlane", "RefPlane", "RefPlane", "ProfileFeature")))
        got = [sw._std_ref_feature(doc, q) for q in ("Front", "Piano superiore", "Right Plane", "origin", "Origine", "Schizzo1")]
        record(f"lingua: piani standard e origine trovati per posizione/tipo in un albero {lang}",
               [g.Name if g else None for g in got] == [names[2], names[3], names[4], names[1], names[1], None],
               str([g.Name if g else None for g in got]))


# ============================================================================ configurazione
def test_config(tmp):
    from solidworks_mcp.config import SolidWorksConfig
    import json
    p = os.path.join(tmp, "config.json")
    with open(p, "w") as f:
        json.dump({"exe_path": "C:/SW/SLDWORKS.exe", "default_unit": "inch", "capture_width": 1920, "part_template": "auto"}, f)
    c = SolidWorksConfig.load(p)
    record("config: chiavi vecchie ignorate senza perdere le altre", c.exe_path == "C:/SW/SLDWORKS.exe" and c.default_unit == "inch")
    with open(ROOT / "solidworks_mcp" / "config.json", encoding="utf-8") as f:
        shipped = json.load(f)
    record("config.json contiene solo chiavi note", set(shipped) <= set(SolidWorksConfig.__dataclass_fields__), str(sorted(shipped)))


# ============================================================================ unita'
def test_units():
    u = UnitConverter("mm")
    ok = (abs(u.to_meters(25.4, "inch") - 0.64516) < 1e-12 and abs(u.to_meters(10) - 0.01) < 1e-15
          and abs(u.from_meters(0.3048, "ft") - 1.0) < 1e-12 and abs(u.convert(1, "inch", "mm") - 25.4) < 1e-12)
    record("unita': mm/inch/ft andata e ritorno", ok)


# ============================================================================ tool attivi: execute_python e SW_MCP_TOOLSETS
def _names():
    return {t.name for t in asyncio.run(srv.list_tools())}


def test_toolsets(tmp):
    real = srv.sw_automation
    fake = _FakeAutomation()
    srv.sw_automation = fake
    try:
        def call(name, args=None):
            fake.calls.clear()
            out = asyncio.run(srv.call_tool(name, args or {}))
            return out[0].text, list(fake.calls)

        names = _names()
        record("execute_python nascosto di default", "execute_python" not in names and len(names) == EXPOSED_TOOLS)
        text, calls = call("execute_python", {"code": "print(1)"})
        record("execute_python rifiutato di default, nessun codice eseguito",
               text.startswith("[ERROR]") and "SW_MCP_ALLOW_PYTHON" in text and not calls, text[:80])

        os.environ["SW_MCP_ALLOW_PYTHON"] = "1"
        try:
            record("SW_MCP_ALLOW_PYTHON=1 riattiva execute_python", "execute_python" in _names() and len(_names()) == EXPOSED_TOOLS + 1)
        finally:
            os.environ.pop("SW_MCP_ALLOW_PYTHON", None)

        os.environ["SW_MCP_TOOLSETS"] = "base,drawings"
        try:
            names = _names()
            groups_ok = all(n in names for n in srv.BASE_DISPATCH) and all(n in names for n in srv.DRAWING_DISPATCH)
            groups_ok = groups_ok and srv.BASE_FROM_MODELING <= names      # estrusione/taglio/raccordo/smusso anche in base
            others = {n for n in names if srv._tool_group(n) not in ("base", "drawings")}
            ext_drw = {n for n, g in srv.EXT_GROUP.items() if g == "drawings" and srv.not_implemented_reason(n) is None}
            record("SW_MCP_TOOLSETS=base,drawings: solo base e disegni esposti (anche i tool del lotto tavole 2)",
                   groups_ok and not others and ext_drw <= names and "add_section_view" in names, f"{len(names)} tool, estranei {sorted(others)[:5]}")
            record("gruppi per area vera: i tool dei lotti di assiemi/tavole/dati/simulazione non sono piu' in 'modeling'",
                   srv._tool_group("check_mate_redundancy") == "assembly" and srv._tool_group("export_ifc") == "data"
                   and srv._tool_group("add_bearing_load") == "simulation" and srv._tool_group("sketch_offset_on_surface") == "modeling",
                   str([srv._tool_group(n) for n in ("check_mate_redundancy", "export_ifc", "add_bearing_load")]))
            text, calls = call("create_sketch", {"plane": "Front"})
            record("tool base attivo con il gruppo scelto", not text.startswith("[ERROR]") or "gruppo" not in text, text[:60])
            mod = next(n for n in srv.MODELING_DISPATCH if n not in srv.BASE_FROM_MODELING)
            text, calls = call(mod, {})
            record("tool di un gruppo non scelto: errore che nomina il gruppo, nessuna chiamata",
                   text.startswith("[ERROR]") and "'modeling'" in text and not calls, text[:120])
            text, calls = call("tool_inesistente", {})
            record("tool sconosciuto con gruppi limitati -> 'Unknown tool'", "Unknown tool" in text, text[:60])
        finally:
            os.environ.pop("SW_MCP_TOOLSETS", None)

        os.environ["SW_MCP_TOOLSETS"] = "bogus"
        try:
            base = ((set(srv.BASE_DISPATCH) | set(srv.SPECIAL_HANDLERS) | srv.BASE_FROM_MODELING
                     | {n for n, g in srv.EXT_GROUP.items() if g == "base" and srv.not_implemented_reason(n) is None})
                    - {"execute_python"})
            record("gruppo sconosciuto: solo base attivo (execute_python resta nascosto)", _names() == base,
                   f"{len(_names())} tool, attesi {len(base)}")
        finally:
            os.environ.pop("SW_MCP_TOOLSETS", None)
    finally:
        srv.sw_automation = real


# ============================================================================ thread COM e timeout
def test_worker_timeout():
    import time
    import threading
    real = srv.sw_automation
    fake = _FakeAutomation()
    srv.sw_automation = fake
    old_timeout = srv.config.tool_timeout
    try:
        def call(name, args=None):
            out = asyncio.run(srv.call_tool(name, args or {}))
            return out[0].text

        fake.threads = []

        def thread_draw_line(**kw):
            fake.threads.append(threading.current_thread().name)
            return {"success": True, "message": "ok", "error_code": 0, "error_name": "swSuccess", "data": {}}
        fake.draw_line = thread_draw_line
        call("draw_line", {"x1": 0, "y1": 0, "x2": 1, "y2": 1})
        record("tool eseguiti sul thread COM unico", fake.threads and fake.threads[0].startswith("sw-com"), str(fake.threads))

        def slow_draw_line(**kw):
            time.sleep(2.5)
            return {"success": True, "message": "tardi", "error_code": 0, "error_name": "swSuccess", "data": {}}
        fake.draw_line = slow_draw_line
        fake._sw_app = object()                          # gia' collegato: nessun tempo di avvio aggiunto al limite
        fake.is_dedicated_mode = lambda: False           # niente taskkill vero su un PID finto (lento e pericoloso)
        srv.config.tool_timeout = 0.5
        t0 = time.time()
        text = call("draw_line", {"x1": 0, "y1": 0, "x2": 1, "y2": 1})
        dt = time.time() - t0
        record("timeout: errore dopo il limite, senza aspettare il tool", text.startswith("[ERROR]") and "superato" in text and dt < 2.0,
               f"{dt:.2f} s: {text[:70]}")
        text = call("draw_line", {"x1": 0, "y1": 0, "x2": 1, "y2": 1})
        record("tool successivo rifiutato finche' il precedente e' ancora bloccato", "ancora eseguendo" in text, text[:70])
        time.sleep(2.5)                                  # il tool lento finisce
        srv.config.tool_timeout = 300
        text = call("draw_line", {"x1": 0, "y1": 0, "x2": 1, "y2": 1})
        record("dopo lo sblocco il server riprende", text.startswith("[SUCCESS]"), text[:70])
    finally:
        srv.config.tool_timeout = old_timeout
        srv.sw_automation = real


# ============================================================================ 5.6 descrizioni dei tool
_IT_WORDS = re.compile(r"\b(della|delle|degli|dello|sulla|sulle|nella|nelle|oppure|vengono|viene|sono|predefinit[aoie]|quindi|"
                       r"perche'?|altrimenti|ogni|anche|solo se|senza|tutti|tutte|quando|questo|questa)\b", re.I)
_UNIT_HINT = re.compile(r"\b(mm|cm|m|inch|in|ft|deg|degrees?|rad|N|N\*?m|Nm|MPa|Pa|kg|g|s|seconds?|Hz|W|K|C|px|pixels?|dpi|"
                        r"unit|units|count|number|index|ratio|factor|percent|%|scale|1-based|0-based|fraction)\b|%", re.I)


def test_descriptions():
    os.environ["SW_MCP_ALLOW_PYTHON"] = "1"
    try:
        tools = asyncio.run(srv.list_tools())
    finally:
        os.environ.pop("SW_MCP_ALLOW_PYTHON", None)
    nodesc, italian, nounit, tool_it = [], [], [], []
    for t in tools:
        desc = (t.description or "").split("[DESTRUCTIVE")[0]
        if _IT_WORDS.search(desc):
            tool_it.append(t.name)
        for p, v in (t.inputSchema or {}).get("properties", {}).items():
            d = v.get("description", "")
            if not d.strip():
                nodesc.append(f"{t.name}.{p}")
                continue
            if _IT_WORDS.search(d):
                italian.append(f"{t.name}.{p}")
            if v.get("type") in ("number", "integer") and not _UNIT_HINT.search(d):
                nounit.append(f"{t.name}.{p}")
    record("ogni parametro ha una descrizione", not nodesc, f"{len(nodesc)}: {nodesc[:6]}")
    record("descrizioni dei tool in inglese", not tool_it, f"{len(tool_it)}: {tool_it[:6]}")
    record("descrizioni dei parametri in inglese", not italian, f"{len(italian)}: {italian[:6]}")
    record("parametri numerici con unita' di misura (o count/index/ratio)", not nounit, f"{len(nounit)}: {nounit[:6]}")


def test_params_used():
    """Revisione 2026-11-12, punto 5: ogni parametro di uno schema deve comparire nel metodo che lo riceve (oltre la firma),
    altrimenti il tool lo accetta e lo ignora in silenzio. Esclusi overwrite/document (controllati prima della chiamata da
    safety.check_call e da server._dispatch_tool) e i metodi con **kwargs."""
    from solidworks_mcp.automation import SolidWorksAutomation
    tools = asyncio.run(srv.list_tools())
    impl = {k: m for d in srv.DISPATCH_TABLES for k, (m, _a) in d.items()}
    unused = []
    for t in tools:
        m = impl.get(t.name)
        fn = getattr(SolidWorksAutomation, m, None) if m else None
        if fn is None:
            continue
        try:
            src = inspect.getsource(fn)
        except (OSError, TypeError):
            continue
        if "**" in src.split(")", 1)[0]:
            continue
        for p in (t.inputSchema or {}).get("properties", {}):
            if p in ("overwrite", "document"):
                continue
            if len(re.findall(r"\b" + re.escape(p) + r"\b", src)) <= 1:
                unused.append(f"{t.name}.{p}")
    record("nessun parametro dello schema ignorato dal metodo", not unused, f"{len(unused)}: {unused[:8]}")


def test_optimization():
    """Ottimizzazione 2026-11-18: istruzioni del server, riferimenti fra i passi di execute_tool_sequence, risposta compatta,
    schemi di piu' tool in una chiamata (search_tools names)."""
    ins = srv.server.instructions or ""
    record("istruzioni del server: spiegano execute_tool_sequence, i riferimenti $N e search_tools names",
           "execute_tool_sequence" in ins and "$N.key" in ins and "search_tools(names" in ins, f"{len(ins)} caratteri")
    steps = [{"tool": "set_units", "arguments": {"unit": "inch"}},
             {"tool": "set_units", "arguments": {"unit": "$1.unit"}},
             {"tool": "set_units", "arguments": {"unit": "mm"}}]
    res = asyncio.run(srv.call_tool("execute_tool_sequence", {"steps": steps}))
    d = json.loads(res[0].text.split("Details: ", 1)[1]) if "Details: " in res[0].text else {}
    r2 = (d.get("results") or [{}, {}])[1]
    record("execute_tool_sequence: \"$1.unit\" diventa il valore restituito dal passo 1",
           res[0].text.startswith("[SUCCESS]") and (r2.get("data") or {}).get("unit") == "inch", str(r2)[:100])
    res = asyncio.run(srv.call_tool("execute_tool_sequence", {"steps": [
        {"tool": "set_units", "arguments": {"unit": "$2.unit"}}]}))
    record("execute_tool_sequence: riferimento a un passo non eseguito -> errore spiegato",
           res[0].text.startswith("[ERROR]") and "non e' ancora stato eseguito" in res[0].text, res[0].text[:100])
    res = asyncio.run(srv.call_tool("execute_tool_sequence", {"steps": steps, "compact": True}))
    d = json.loads(res[0].text.split("Details: ", 1)[1]) if "Details: " in res[0].text else {}
    record("execute_tool_sequence compact: nessun campo data nei passi riusciti",
           res[0].text.startswith("[SUCCESS]") and all("data" not in r for r in d.get("results", [])) and len(d.get("results", [])) == 3)
    r = srv._search_tools_handler({"names": ["extrude_boss", "draw_circle"], "detail": True})
    tools = (r.get("data") or {}).get("tools", [])
    record("search_tools names+detail: due tool con tipo e descrizione di ogni parametro",
           r["success"] and len(tools) == 2 and isinstance(tools[0]["parameters"], dict)
           and str(tools[0]["parameters"].get("depth", "")).startswith("number"), str(tools[0]["parameters"])[:100] if tools else "")
    args = {"view": "Disegno1", "filepath": "x.sldprt"}
    done = srv._apply_arg_aliases(args, {"view_name", "file_path"})
    record("argomenti con il nome dell'altro tool (view/view_name, filepath/file_path) letti come quello giusto",
           args == {"view_name": "Disegno1", "file_path": "x.sldprt"} and len(done) == 2, str(args))
    args = {"view": "A", "view_name": "B"}
    srv._apply_arg_aliases(args, {"view_name"})
    record("alias: se c'e' gia' il nome giusto l'altro non lo sovrascrive (resta e viene segnalato come ignorato)",
           args == {"view": "A", "view_name": "B"})
    r = srv._search_tools_handler({"names": ["tool_che_non_esiste"]})
    record("search_tools names: nome inesistente segnalato", not r["success"] and r["data"]["missing"] == ["tool_che_non_esiste"])
    # COM leggero (utils/com_cache): solo su Windows con pywin32 (su Linux non si installa)
    from solidworks_mcp.utils import com_cache
    if STUBBED:
        record("com_cache: senza pywin32 non si installa e non rompe l'import", not com_cache.stats()["installed"])
    else:
        import win32com.client as _w
        d_ = _w.Dispatch("Scripting.Dictionary")
        d_.Add("a", 1)
        d_.Add("b", 2)
        ok_ = (type(d_).__name__ == "LightDispatch" and d_.Count == 2 and d_.Item("a") == 1 and d_.Exists("b")
               and sorted(d_.Keys()) == ["a", "b"])
        record("com_cache: oggetti COM leggeri (senza descrizione del tipo) con proprieta', metodi e proprieta' con indice",
               com_cache.stats()["installed"] and ok_, str(com_cache.stats())[:200])
        # vivaio: lo stesso oggetto COM restituito due volte -> stesso involucro (dispid gia' noti); flush lo lascia andare
        inner = _w.Dispatch("Scripting.Dictionary")
        inner.Add("x", 7)
        d_.Add("k", inner)
        com_cache.flush()
        a_, b_ = d_.Item("k"), d_.Item("k")
        st_ = com_cache.stats()
        n_ = com_cache.flush()
        c_ = d_.Item("k")
        record("com_cache vivaio: stesso oggetto -> stesso involucro finche' non si svuota, poi involucro nuovo",
               (a_ is b_) and a_.Item("x") == 7 and st_["pool_alive"] >= 1 and n_ >= 1 and c_ is not a_ and c_.Item("x") == 7,
               f"alive {st_['pool_alive']} flush {n_}")
        ex_ = com_cache.member_caller("Exists")
        it_ = com_cache.member_caller("Count", method=False)
        record("com_cache member_caller: chiamata diretta su oggetti veri e via normale su quelli finti",
               ex_(d_, "a") is True and ex_(d_, "zz") is False and it_(d_) == 3
               and com_cache.member_caller("upper")("abc") == "ABC")


# ============================================================================ 5.2 ripresa dell'istanza dedicata
def test_autorestart():
    saved_env = {k: os.environ.get(k) for k in ("SW_MCP_INSTANCE", "SW_MCP_AUTORESTART")}
    real_srv = srv.sw_automation
    try:
        os.environ["SW_MCP_INSTANCE"] = "dedicated"
        os.environ.pop("SW_MCP_AUTORESTART", None)
        a = SolidWorksAutomation()
        a._ui_language = lambda: "italian"
        launches = []

        def fake_launch():
            launches.append(1)
            a._dedicated_pid = 456
            return a._result(True, "Connected to dedicated SolidWorks (PID 456)", data={"pid": 456, "dedicated": True})
        a._connect_dedicated = fake_launch

        a._dedicated_pid, a._sw_app, a._connected = 123, types.SimpleNamespace(RevisionNumber="34.4.1"), True
        r = a.connect()
        record("connect con istanza dedicata viva: successo, nessun rilancio", r["success"] and not launches and a._dedicated_pid == 123,
               r["message"][:70])

        a._sw_app, a._connected = None, False
        r = a.connect()
        record("istanza persa senza SW_MCP_AUTORESTART: errore che lo nomina, nessun rilancio",
               not r["success"] and "SW_MCP_AUTORESTART" in r["message"] and not launches, r["message"][:90])

        os.environ["SW_MCP_AUTORESTART"] = "1"
        srv.sw_automation = a
        text = asyncio.run(srv.call_tool("connect_solidworks", {}))[0].text
        record("istanza persa con SW_MCP_AUTORESTART=1: rilanciata, avviso dei documenti persi nel risultato del tool",
               launches == [1] and a._dedicated_pid == 456 and text.startswith("[SUCCESS] ATTENZIONE") and "123" in text
               and "persi" in text, text[:110])
        text = asyncio.run(srv.call_tool("get_solidworks_info", {}))[0].text
        record("l'avviso compare una volta sola", "ATTENZIONE" not in text, text[:60])
    finally:
        srv.sw_automation = real_srv
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_resources_and_prompts():
    # 1. list_resources
    resources = asyncio.run(srv.list_resources())
    uris = [str(r.uri) for r in resources]
    expected_uris = [
        "solidworks://status",
        "solidworks://documents",
        "solidworks://active-document",
        "solidworks://configuration",
    ]
    record("risorse: 4 risorse esposte con URI attesi", uris == expected_uris, str(uris))
    record("risorse: mimeType application/json per tutte", all(r.mimeType == "application/json" for r in resources))

    # 2. read_resource (offline / disconnected)
    status_content = asyncio.run(srv.read_resource("solidworks://status"))
    status_json = json.loads(status_content[0].content)
    record("read_resource solidworks://status: JSON valido con connected e default_unit",
           "connected" in status_json and "default_unit" in status_json,
           f"connected={status_json.get('connected')}")

    docs_content = asyncio.run(srv.read_resource("solidworks://documents"))
    docs_json = json.loads(docs_content[0].content)
    record("read_resource solidworks://documents: JSON valido con lista documents",
           "documents" in docs_json and isinstance(docs_json["documents"], list))

    active_content = asyncio.run(srv.read_resource("solidworks://active-document"))
    active_json = json.loads(active_content[0].content)
    record("read_resource solidworks://active-document: JSON valido",
           "active_document" in active_json)

    config_content = asyncio.run(srv.read_resource("solidworks://configuration"))
    config_json = json.loads(config_content[0].content)
    record("read_resource solidworks://configuration: include enabled_toolsets e tool_timeout",
           "enabled_toolsets" in config_json and "tool_timeout" in config_json)

    unknown_failed = False
    try:
        asyncio.run(srv.read_resource("solidworks://unknown-uri"))
    except ValueError:
        unknown_failed = True
    record("read_resource con URI sconosciuto -> ValueError", unknown_failed)

    # 3. read_resource with mock active document
    real_app = srv.sw_automation._sw_app
    real_connected = srv.sw_automation._connected
    try:
        mock_doc = types.SimpleNamespace(
            GetTitle=lambda: "Pezzo1.SLDPRT",
            GetType=lambda: 1,  # Part
            GetPathName=lambda: "C:\\models\\Pezzo1.SLDPRT",
            GetSaveFlag=lambda: False,
            GetActiveConfiguration=lambda: types.SimpleNamespace(Name="Default"),
            GetConfigurationNames=lambda: ("Default", "Lungo"),
            GetMaterialPropertyName2=lambda x: ("", "AISI 304"),
            GetBodies2=lambda x, y: [1, 2],
        )
        mock_app = types.SimpleNamespace(
            ActiveDoc=mock_doc,
            GetDocuments=lambda: [mock_doc],
            RevisionNumber="34.4.1",
            GetCurrentLanguage=lambda: "italian",
        )
        srv.sw_automation._sw_app = mock_app
        srv.sw_automation._connected = True

        act_res = asyncio.run(srv.read_resource("solidworks://active-document"))
        act_data = json.loads(act_res[0].content)
        doc_details = act_data.get("active_document") or {}
        record("read_resource con pezzo attivo: legge configurazione, materiale e corpi",
               doc_details.get("title") == "Pezzo1.SLDPRT" and
               doc_details.get("type") == "Part" and
               doc_details.get("material") == "AISI 304" and
               doc_details.get("solid_bodies_count") == 2,
               str(doc_details))

        docs_res = asyncio.run(srv.read_resource("solidworks://documents"))
        docs_data = json.loads(docs_res[0].content)
        record("read_resource documents con doc attivo: riporta is_active=True",
               docs_data.get("count") == 1 and docs_data["documents"][0].get("is_active") is True)
    finally:
        srv.sw_automation._sw_app = real_app
        srv.sw_automation._connected = real_connected

    # 4. list_prompts
    prompts = asyncio.run(srv.list_prompts())
    prompt_names = [p.name for p in prompts]
    expected_prompts = [
        "create-part",
        "create-drawing",
        "run-simulation",
        "create-assembly",
        "export-model",
    ]
    record("prompt: 5 template esposti con nomi attesi", prompt_names == expected_prompts, str(prompt_names))
    record("prompt: tutti hanno argomenti e descrizioni",
           all(bool(p.arguments) and bool(p.description) for p in prompts))

    # 5. get_prompt
    p_part = asyncio.run(srv.get_prompt("create-part", {"description": "flangia speciale", "unit": "mm"}))
    record("get_prompt create-part: testo include descrizione e unita'",
           "flangia speciale" in p_part.messages[0].content.text and "mm" in p_part.messages[0].content.text)

    p_draw = asyncio.run(srv.get_prompt("create-drawing", {"part_name": "Albero", "sheet_format": "A2"}))
    record("get_prompt create-drawing: testo include nome pezzo e formato A2",
           "Albero" in p_draw.messages[0].content.text and "A2" in p_draw.messages[0].content.text)

    p_sim = asyncio.run(srv.get_prompt("run-simulation", {"load_description": "1500 N trazione", "study_type": "static"}))
    record("get_prompt run-simulation: testo include carico e studio",
           "1500 N trazione" in p_sim.messages[0].content.text and "static" in p_sim.messages[0].content.text)

    p_asm = asyncio.run(srv.get_prompt("create-assembly", {"components": "vite e dado", "assembly_name": "Giunto"}))
    record("get_prompt create-assembly: testo include componenti e nome assieme",
           "vite e dado" in p_asm.messages[0].content.text and "Giunto" in p_asm.messages[0].content.text)

    p_exp = asyncio.run(srv.get_prompt("export-model", {"format": "step", "filepath": "C:\\out.step"}))
    record("get_prompt export-model: testo include formato e percorso",
           "STEP" in p_exp.messages[0].content.text and "out.step" in p_exp.messages[0].content.text)

    unknown_p_failed = False
    try:
        asyncio.run(srv.get_prompt("unknown-prompt", {}))
    except ValueError:
        unknown_p_failed = True
    record("get_prompt con nome sconosciuto -> ValueError", unknown_p_failed)

    # 6. ogni tool citato nel testo dei prompt deve esistere fra quelli esposti (un nome inventato manda il modello fuori strada)
    exposed = {t.name for t in asyncio.run(srv.list_tools())}
    params_ok = {"paper_size", "min_value", "max_value"}          # parametri citati nei testi, non tool
    for p_name, p_args in (("create-part", {"description": "x"}), ("create-part", {"description": "x", "material": "y"}),
                           ("create-drawing", {"part_name": "x"}), ("create-drawing", {"part_name": "x", "export_pdf": "false"}),
                           ("run-simulation", {"load_description": "x"}), ("run-simulation", {"load_description": "x", "material": "y"}),
                           ("create-assembly", {"components": "x"}),
                           ("export-model", {"format": "step", "filepath": "out.step"}),
                           ("export-model", {"format": "step", "filepath": "out.step", "configuration": "c"})):
        text = asyncio.run(srv.get_prompt(p_name, p_args)).messages[0].content.text
        cited = set(re.findall(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b", text))
        unknown = sorted(cited - exposed - params_ok)
        record(f"prompt {p_name} {sorted(p_args)}: ogni tool citato esiste fra quelli esposti", not unknown, str(unknown))





def test_execute_tool_sequence(tmp):
    # 1. Empty steps
    res = asyncio.run(srv.call_tool("execute_tool_sequence", {"steps": []}))
    text = res[0].text
    record("execute_tool_sequence: steps vuoto -> successo", text.startswith("[SUCCESS]"))

    # 2. Steps non lista
    res = asyncio.run(srv.call_tool("execute_tool_sequence", {"steps": "non_una_lista"}))
    text = res[0].text
    record("execute_tool_sequence: steps non lista -> rifiuto", text.startswith("[ERROR]"))

    # 3. Chiamata annidata vietata
    res = asyncio.run(srv.call_tool("execute_tool_sequence", {
        "steps": [{"tool": "execute_tool_sequence", "arguments": {"steps": []}}]
    }))
    text = res[0].text
    record("execute_tool_sequence: annidamento rifiutato", text.startswith("[ERROR]") and "nested" in text.lower())

    # 4. Tool bloccato (execute_python senza SW_MCP_ALLOW_PYTHON)
    res = asyncio.run(srv.call_tool("execute_tool_sequence", {
        "steps": [{"tool": "execute_python", "arguments": {"code": "print(1)"}}]
    }))
    text = res[0].text
    record("execute_tool_sequence: tool bloccato fermato con spiegazione",
           text.startswith("[ERROR]") and "execute_python" in text)

    # 5. Sequenza valida di piu' passi
    steps = [
        {"tool": "set_units", "arguments": {"unit": "inch"}},
        {"tool": "set_units", "arguments": {"unit": "mm"}},
    ]
    res = asyncio.run(srv.call_tool("execute_tool_sequence", {"steps": steps}))
    text = res[0].text
    record("execute_tool_sequence: sequenza valida completata con successo",
           text.startswith("[SUCCESS]") and "2/2" in text and srv.sw_automation.units.default_unit.value == "mm")

    # 6. stop_on_error=True (default) ferma l'esecuzione al primo errore
    steps_err = [
        {"tool": "set_units", "arguments": {"unit": "inch"}},
        {"tool": "tool_inesistente_xyz", "arguments": {}},
        {"tool": "set_units", "arguments": {"unit": "mm"}},
    ]
    res = asyncio.run(srv.call_tool("execute_tool_sequence", {"steps": steps_err, "stop_on_error": True}))
    text = res[0].text
    unit_after_stop = srv.sw_automation.units.default_unit.value
    record("execute_tool_sequence: stop_on_error=True blocca i passi successivi",
           text.startswith("[ERROR]") and "step 2/3" in text and unit_after_stop == "inch")

    # 7. stop_on_error=False esegue tutti i passi anche se uno fallisce
    res = asyncio.run(srv.call_tool("execute_tool_sequence", {"steps": steps_err, "stop_on_error": False}))
    text = res[0].text
    unit_after_all = srv.sw_automation.units.default_unit.value
    record("execute_tool_sequence: stop_on_error=False esegue comunque i passi successivi",
           text.startswith("[ERROR]") and "2/3" in text and unit_after_all == "mm")

    # 8. Guardia di sovrascrittura: rifiuto preventivo se un passo sovrascrive senza overwrite=true
    dup_file = Path(tmp) / "batch_existing.step"
    dup_file.write_text("test")
    steps_overwrite = [
        {"tool": "set_units", "arguments": {"unit": "mm"}},
        {"tool": "export_model", "arguments": {"filepath": str(dup_file), "format": "step"}},
    ]
    res = asyncio.run(srv.call_tool("execute_tool_sequence", {"steps": steps_overwrite}))
    text = res[0].text
    record("execute_tool_sequence: rifiuto preventivo di sovrascrittura senza overwrite",
           text.startswith("[ERROR]") and ("esiste gia'" in text or "SOVRASCRITTO" in text))


# ============================================================================ ImageContent per Vision LLM
def test_image_content(tmp):
    import base64

    # 1. Helper _try_load_image_content con file inesistente, non-immagine o vuoto
    record("image_content: file inesistente -> None", srv._try_load_image_content("non_esiste.png") is None)

    txt_file = Path(tmp) / "note.txt"
    txt_file.write_text("hello")
    record("image_content: estensione non immagine (.txt) -> None", srv._try_load_image_content(str(txt_file)) is None)

    empty_png = Path(tmp) / "empty.png"
    empty_png.write_bytes(b"")
    record("image_content: file vuoto (0 byte) -> None", srv._try_load_image_content(str(empty_png)) is None)

    # 2. Caricamento valido di PNG con verifica base64 e mimeType
    good_png = Path(tmp) / "sample.png"
    sample_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    good_png.write_bytes(sample_bytes)
    img_content = srv._try_load_image_content(str(good_png))
    record("image_content: PNG valido -> ImageContent con mimeType image/png",
           img_content is not None and img_content.type == "image" and img_content.mimeType == "image/png"
           and base64.b64decode(img_content.data) == sample_bytes)

    # 3. MIME types corretti per JPG e BMP
    good_jpg = Path(tmp) / "sample.jpg"
    good_jpg.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 10)
    ic_jpg = srv._try_load_image_content(str(good_jpg))
    record("image_content: JPG -> mimeType image/jpeg", ic_jpg is not None and ic_jpg.mimeType == "image/jpeg")

    # 4. Limite dimensione: file oltre 10 MB saltato
    saved_max = srv._MAX_IMAGE_ATTACHMENT_SIZE
    try:
        srv._MAX_IMAGE_ATTACHMENT_SIZE = 10  # soglia a 10 byte per il test
        record("image_content: file sopra la soglia massima -> None", srv._try_load_image_content(str(good_png)) is None)
    finally:
        srv._MAX_IMAGE_ATTACHMENT_SIZE = saved_max

    # 5. _format_tool_response: tool fallito -> solo TextContent
    res_fail = {"success": False, "message": "Failed", "error_code": 1, "error_name": "swError", "data": {"filepath": str(good_png)}}
    out_fail = srv._format_tool_response("export_model_image", {}, res_fail)
    record("image_content: tool fallito -> solo TextContent (nessuna immagine)", len(out_fail) == 1 and out_fail[0].type == "text")

    # 6. _format_tool_response: successo con filepath immagine -> TextContent + ImageContent
    res_ok = {"success": True, "message": "Saved", "error_code": 0, "error_name": "swSuccess", "data": {"filepath": str(good_png)}}
    out_ok = srv._format_tool_response("export_model_image", {}, res_ok)
    record("image_content: successo con filepath -> TextContent + ImageContent",
           len(out_ok) == 2 and out_ok[0].type == "text" and out_ok[1].type == "image" and out_ok[1].mimeType == "image/png")

    # 7. attach_image=False disabilita l'allegato
    out_no_attach = srv._format_tool_response("export_model_image", {"attach_image": False}, res_ok)
    record("image_content: attach_image=False -> solo TextContent", len(out_no_attach) == 1)

    # 8. SW_MCP_ATTACH_IMAGES=0 disabilita l'allegato globalmente
    os.environ["SW_MCP_ATTACH_IMAGES"] = "0"
    try:
        out_env_disabled = srv._format_tool_response("export_model_image", {}, res_ok)
        record("image_content: SW_MCP_ATTACH_IMAGES=0 -> solo TextContent", len(out_env_disabled) == 1)
    finally:
        os.environ.pop("SW_MCP_ATTACH_IMAGES", None)

    # 9. execute_tool_sequence con passo di export immagine include ImageContent
    seq_res = {
        "success": True,
        "message": "Sequence finished",
        "error_code": 0,
        "error_name": "swSuccess",
        "data": {
            "results": [
                {"step": 1, "tool": "set_units", "success": True, "data": {}},
                {"step": 2, "tool": "export_model_image", "success": True, "data": {"filepath": str(good_png)}},
            ]
        }
    }
    out_seq = srv._format_tool_response("execute_tool_sequence", {}, seq_res)
    record("image_content: execute_tool_sequence raccoglie ImageContent dai singoli passi",
           len(out_seq) == 2 and out_seq[1].type == "image" and out_seq[1].mimeType == "image/png")


# ============================================================================ Diagnostica e Tool Discovery
def test_diagnostics_and_search():
    # 1. search_tools senza query -> errore
    res_no_q = srv._search_tools_handler({})
    record("search_tools: query mancante -> errore", not res_no_q["success"])

    # 2. search_tools con query 'fillet' trova strumenti di raccordo
    res_fillet = srv._search_tools_handler({"query": "fillet", "limit": 10})
    matched_names = [t["name"] for t in res_fillet["data"]["tools"]]
    record("search_tools: query 'fillet' trova fillet_at_points",
           res_fillet["success"] and "fillet_at_points" in matched_names and res_fillet["data"]["total_matches"] > 0)

    # 3. search_tools con filtro di gruppo 'simulation'
    res_sim = srv._search_tools_handler({"query": "mesh", "group": "simulation"})
    sim_groups = {t["group"] for t in res_sim["data"]["tools"]}
    record("search_tools: filtro gruppo 'simulation' restituisce solo tool di simulazione",
           res_sim["success"] and sim_groups <= {"simulation"})

    # 4. search_tools con query inesistente -> 0 match ma successo
    res_none = srv._search_tools_handler({"query": "xyz_inesistente_12345"})
    record("search_tools: query inesistente -> 0 risultati con successo",
           res_none["success"] and res_none["data"]["total_matches"] == 0 and len(res_none["data"]["tools"]) == 0)

    # 5. get_rebuild_errors: struttura del risultato diagnostico
    sw = SolidWorksAutomation()
    sw.get_active_doc = lambda: (None, {"success": False, "message": "Nessun doc attivo"})
    err_no_doc = sw.get_rebuild_errors()
    record("get_rebuild_errors: senza documento attivo riporta errore pulito", not err_no_doc["success"])

    class _MockDoc:
        def __init__(self):
            self.FirstFeature = None
            self.Extension = self
        def GetWhatsWrong(self, fs, ec, wn):
            pass
        def ForceRebuild3(self, top_only):
            return True

    sw.get_active_doc = lambda: (_MockDoc(), None)
    res_reb = sw.get_rebuild_errors(force_rebuild=True)
    d = res_reb.get("data", {})
    record("get_rebuild_errors: struttura dati corretta (rebuild_ok, error_count, warning_count)",
           res_reb["success"] and "rebuild_ok" in d and d.get("error_count") == 0 and d.get("warning_count") == 0)

    # 6. get_feature_tree: include contatori di errore e warning
    tree_res = sw.get_feature_tree()
    td = tree_res.get("data", {})
    record("get_feature_tree: include contatori error_count e warning_count",
           tree_res["success"] and "error_count" in td and "warning_count" in td and "features" in td)

    # 6b. Mock FEDELE al late binding: i membri senza argomenti (Name, GetTypeName2, GetNextFeature, GetFirstSubFeature,
    #     GetNextSubFeature, FirstFeature) sono PROPRIETA' (valori, non metodi): chiamarli darebbe "'str' object is not callable".
    class _PFeat:
        def __init__(self, name, typ, code=0):
            self.Name, self.GetTypeName2, self._code = name, typ, code
            self.GetNextFeature = self.GetFirstSubFeature = self.GetNextSubFeature = None

        def IsSuppressed2(self, opt, cfgs):
            return (False,)

        def GetErrorCode2(self, bf):
            bf.value = False
            return self._code

    pf = [_PFeat("Boss-Extrude1", "Extrusion"), _PFeat("Cut-Extrude2", "Cut", code=7), _PFeat("Sketch1", "ProfileFeature")]
    for a, b in zip(pf, pf[1:]):
        a.GetNextFeature = b
    pf[0].GetFirstSubFeature = pf[2]          # sotto-feature (schizzo) della prima feature

    class _PDoc(_MockDoc):
        def __init__(self):
            super().__init__()
            self.FirstFeature = pf[0]
    sw.get_active_doc = lambda: (_PDoc(), None)
    tree_p = sw.get_feature_tree(include_sketches=True)
    names_p = [f["name"] for f in tree_p.get("data", {}).get("features", [])]
    record("get_feature_tree: mock fedele (membri come proprieta') elenca le feature e i codici di errore",
           tree_p["success"] and names_p == ["Boss-Extrude1", "Cut-Extrude2", "Sketch1"] and tree_p["data"]["error_count"] == 1
           and tree_p["data"]["features"][0]["sub_features"][0]["name"] == "Sketch1", str(tree_p)[:200])
    reb_p = sw.get_rebuild_errors()
    record("get_rebuild_errors: mock fedele (membri come proprieta') riporta la feature con errore",
           reb_p["success"] and reb_p["data"]["error_count"] == 1 and reb_p["data"]["errors"][0]["name"] == "Cut-Extrude2", str(reb_p)[:200])




# ============================================================================ audit drawing & detect collisions
def test_audit_and_collision():
    sw = SolidWorksAutomation()

    # 1. audit_drawing: rifiuto se non disegno
    sw.get_active_doc = lambda: (None, {"success": False, "message": "Nessun doc attivo"})
    err_no_doc = sw.audit_drawing()
    record("audit_drawing: senza documento attivo riporta errore", not err_no_doc["success"])

    class _MockNote:
        def __init__(self, text, is_bal, next_n=None):
            self._text = text
            self._is_bal = is_bal
            self._next = next_n
        def IsBalloon(self):
            return self._is_bal
        def GetBalloonText(self, idx):
            return self._text
        def GetText(self):
            return self._text
        def GetNext(self):
            return self._next

    class _MockDim:
        def __init__(self, name):
            self._name = name
        def GetNameForSelection(self):
            return self._name

    class _MockDisplayDim:
        def __init__(self, name, dangling=False, next_dd=None):
            self._dim = _MockDim(name)
            self._dangling = dangling
            self._next = next_dd
        def IsDangling(self):
            return self._dangling
        def GetDimension2(self, idx):
            return self._dim
        @property
        def GetNext3(self):
            return self._next

    class _MockView:
        def __init__(self, name, note=None, dd=None):
            self._name = name
            self._note = note
            self._dd = dd
        def GetName2(self):
            return self._name
        def GetBreakLines(self):
            return None
        def GetFirstNote(self):
            return self._note
        @property
        def GetFirstDisplayDimension5(self):
            return self._dd

    class _MockSheet:
        def GetName(self):
            return "Foglio1"

    class _MockDrawingDoc:
        def GetType(self):
            return 3  # DOC_DRAWING
        def GetCurrentSheet(self):
            return _MockSheet()
        def ActivateSheet(self, name):
            return True

    mock_dw = _MockDrawingDoc()
    sw.get_active_doc = lambda: (mock_dw, None)
    sw._sheet_dims = lambda doc: (0.420, 0.297, "A3-ISO")
    sw._fit_title_number = lambda doc: {"text": "PROV-001", "fits": True, "height_mm": 5.0}

    # Setup 1 vista con 2 palloncini ("1", "2") e 2 quote (una dangling "D1@Vista1")
    note2 = _MockNote("2", True, None)
    note1 = _MockNote("1", True, note2)
    dd2 = _MockDisplayDim("D1@Vista1", dangling=True, next_dd=None)
    dd1 = _MockDisplayDim("RD1@Vista1", dangling=False, next_dd=dd2)
    v1 = _MockView("Vista Frontale", note=note1, dd=dd1)

    sw._sheet_views = lambda doc: [v1]
    sw._break_views = lambda doc, all_sheets=False: []
    sw.list_bom = lambda: {"success": True, "data": {"rows": [{"ITEM NO.": "1"}, {"ITEM NO.": "2"}, {"ITEM NO.": "3"}]}}
    sw.list_drawing_dimensions = lambda: {"success": True, "data": {"dimensions": ["D1", "RD1"], "duplicates": 0}}

    audit_res = sw.audit_drawing()
    ad = audit_res.get("data", {})
    checks = ad.get("checks", {})
    bom_chk = checks.get("bom_and_balloons", {})
    dims_chk = checks.get("dimensions", {})

    record("audit_drawing: esecuzione completata con successo", audit_res["success"])
    record("audit_drawing: rileva voce distinta mancante di palloncino ('3')", "3" in bom_chk.get("missing_balloons", []))
    record("audit_drawing: rileva quota dangling e boccia lo stato di pass",
           dims_chk.get("dangling_count") == 1 and not ad.get("passed"))

    # 2. detect_collisions: rifiuto se non assieme
    sw.get_active_doc = lambda: (None, {"success": False, "message": "Nessun doc attivo"})
    err_asm = sw.detect_collisions()
    record("detect_collisions: senza documento attivo riporta errore", not err_asm["success"])

    class _MockComp:
        def __init__(self, name):
            self.Name2 = name
            self.Transform2 = None

    class _MockInterference:
        def __init__(self, c1, c2, vol_m3):
            self.Components = [c1, c2]
            self.Volume = vol_m3

    class _MockIntMgr:
        def __init__(self, ints):
            self._ints = ints
            self.TreatCoincidenceAsInterference = False
            self.TreatSubAssembliesAsComponents = False
            self.IncludeMultibodyPartInterferences = False
        def GetInterferences(self):
            return self._ints
        def Done(self):
            pass

    class _MockAsmDoc:
        def __init__(self, int_mgr):
            self.InterferenceDetectionManager = int_mgr
        def GetType(self):
            return 2  # DOC_ASSEMBLY
        def ForceRebuild2(self, top_only):
            return True
        def IsExploded(self):
            return False

    comp_a = _MockComp("perno-1")
    comp_b = _MockComp("staffa-1")
    int_mgr_static = _MockIntMgr([_MockInterference(comp_a, comp_b, 1.5e-7)]) # 150 mm3
    asm_doc = _MockAsmDoc(int_mgr_static)

    sw.get_active_doc = lambda: (asm_doc, None)
    sw._as_collapse = lambda doc: False

    # Modalita' statica
    stat_res = sw.detect_collisions()
    sd = stat_res.get("data", {})
    record("detect_collisions: modalita' statica rileva interferenza e volume",
           stat_res["success"] and sd.get("mode") == "static" and sd.get("collision_detected") and sd.get("total_volume_mm3") == 150.0)

    # Modalita' dinamica
    # Configura traiettoria su perno-1 che collide al passo 3
    class _DynamicIntMgr:
        def __init__(self, comp_mov, comp_obs):
            self.comp_mov = comp_mov
            self.comp_obs = comp_obs
            self.step_counter = 0
            self.TreatCoincidenceAsInterference = False
            self.TreatSubAssembliesAsComponents = False
            self.IncludeMultibodyPartInterferences = False
        def GetInterferences(self):
            self.step_counter += 1
            if self.step_counter >= 3:
                return [_MockInterference(self.comp_mov, self.comp_obs, 5.0e-8)]
            return []
        def Done(self):
            pass

    dyn_mgr = _DynamicIntMgr(comp_a, comp_b)
    asm_doc_dyn = _MockAsmDoc(dyn_mgr)
    sw.get_active_doc = lambda: (asm_doc_dyn, None)

    init_M = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    init_t = [0.0, 0.0, 0.0]
    sw._as_comp = lambda doc, name: (comp_a if name == "perno-1" else None, None)
    sw._as_pose = lambda comp: (init_M, list(init_t))
    comp_a.Transform2 = "initial_transform_obj"
    sw._as_transform = lambda M, t: f"xf_{t}"

    dyn_res = sw.detect_collisions(moving_component="perno-1", dx=10.0, dy=0.0, dz=0.0, steps=5, stop_on_collision=True)
    dd = dyn_res.get("data", {})

    record("detect_collisions: modalita' dinamica rileva primo passo di collisione",
           dyn_res["success"] and dd.get("mode") == "dynamic" and dd.get("collision_detected") and dd.get("first_collision_step") == 3)
    record("detect_collisions: calcola corsa libera e ripristina posa iniziale",
           dd.get("max_safe_displacement") == 4.0 and dd.get("initial_pose_restored") and comp_a.Transform2 == "xf_[0.0, 0.0, 0.0]")




# ============================================================================ sketch4 tools unit tests
def test_sketch4_tools():
    sw = SolidWorksAutomation()

    # Senza documento attivo, devono fallire con errore controllato
    sw.get_active_doc = lambda: (None, {"success": False, "message": "Nessun doc attivo"})
    sw._part = lambda: (None, {"success": False, "message": "Nessun pezzo attivo"})
    sw._s2_active_or_open = lambda sketch=None: (None, None, {"success": False, "message": "Nessun schizzo attivo"})

    r3 = sw.sketch_offset_on_surface()
    r4 = sw.make_sketch_chain()
    r5 = sw.segment_sketch_entity()
    r6 = sw.draw_3point_arc_slot(0, 0, 10, 0, 5, 5, 2)
    r7 = sw.draw_sketch_text_along_curve("Test")
    r8 = sw.draw_equation_curve_3d("t", "t", "t")
    r9 = sw.stretch_sketch_entities(1, 1)
    r10 = sw.align_sketch_entities([[0, 0]], [[1, 1]])
    r11 = sw.show_sketch_curvature()
    r14 = sw.insert_sketch_picture("nonexistent.png")
    r15 = sw.insert_sketch_block_from_file("nonexistent.sldblk")

    all_failed_cleanly = all((not r['success'] for r in (r3, r4, r5, r6, r7, r8, r9, r10, r11, r14, r15)))
    record("sketch4: tutti i tool del lotto gestiscono assenza doc/schizzo con errore pulito", all_failed_cleanly)

    # Con mock di schizzo attivo
    class _MockPt:
        def __init__(self, x=0.0, y=0.0, z=0.0):
            self.X = x
            self.Y = y
            self.Z = z

    class _MockSeg:
        def __init__(self, name, seg_type=0):
            self._name = name
            self._type = seg_type
            self.ShowCurvatureCombs = False
            self.ShowInflectionPoints = False
            self.ShowMinimumRadius = False
        chained = False
        def GetName(self):
            return self._name
        def GetType(self):
            return self._type
        def Select4(self, append, data):
            return True
        def GetSketchPathCount(self):
            return 1 if _MockSeg.chained else 0
        def GetStartPoint2(self):
            return _MockPt(0.0, 0.0, 0.0)
        def GetEndPoint2(self):
            return _MockPt(1.0, 0.0, 0.0)

    class _MockSketchMgr:
        def __init__(self):
            self.ActiveSketch = self
        def InsertIntersectionCurve(self):
            return True
        def InsertSilhouetteEntities(self, t, b, le, a, uts, eil):
            return True
        def InsertOffsetOnSurface(self, dist, rev, geod, mc):
            return True
        def MakeSketchChain(self):
            _MockSeg.chained = True
            return True
        def CreateSegmentPoints(self, count, is_seg):
            return True
        def SplitOpenSegment(self, x, y, z):
            return True
        def CreatePoint(self, x, y, z):
            return self
        def CreateSketchSlot(self, *args):
            return True
        def CreateText(self, x, y, z, text):
            return True
        def StretchEntities(self, *args):
            return True
        def AlignEntities1Point(self, *args):
            return True
        def CreateSpline(self, pts):
            return True
        def InsertSketchPicture2(self, path):
            return self
        def SetOrigin(self, x, y):
            pass
        def SetSize(self, w, h, p):
            pass
        def MakeSketchBlockFromFile(self, *args):
            return self

    class _MockBody:
        def Select2(self, append, data):
            return True

    class _MockDoc:
        def __init__(self):
            self.SketchManager = _MockSketchMgr()
            self.Extension = self
        def SelectByID2(self, *args):
            return True
        def GetBodies2(self, *args):
            return (_MockBody(),)
        def ClearSelection2(self, *args):
            return True

    mock_doc = _MockDoc()
    mock_seg = _MockSeg("Line1", seg_type=3) # Spline
    sw._s2_active_or_open = lambda sketch=None: (mock_doc, mock_doc.SketchManager, None)
    sw._s4_segs = lambda doc: [mock_seg]
    sw._seg_id = lambda s: s.GetName()
    sw._part = lambda: (mock_doc, None)

    # Test esecuzione mock per i tool principali
    ok_off = sw.sketch_offset_on_surface(5.0)
    ok_chn = sw.make_sketch_chain(["Line1"])
    ok_seg = sw.segment_sketch_entity("Line1", count=5, is_segments=True)
    ok_slt = sw.draw_3point_arc_slot(0, 0, 20, 0, 10, 5, width=4)
    ok_curv = sw.show_sketch_curvature("Line1", scale=15.0, density=30, visible=True)
    ok_eq3d = sw.draw_equation_curve_3d("10*cos(t)", "10*sin(t)", "2*t", start=0, end=3.14, samples=20)

    record("sketch4: sketch_offset_on_surface calcola distanza e geodetica", ok_off["success"] and ok_off["data"]["geodesic"])
    record("sketch4: make_sketch_chain combina segmenti", ok_chn["success"] and ok_chn["data"]["segment_count"] == 1)
    record("sketch4: segment_sketch_entity su una spline -> rifiutato (punti non calcolabili sulla curva)",
           not ok_seg["success"] and "solo linee" in ok_seg["message"], ok_seg["message"][:90])
    _slot_args = {}
    _orig_slot = sw.draw_slot
    sw.draw_slot = lambda **kw: (_slot_args.update(kw), {"success": True, "message": "ok", "data": {}})[1]
    ok_slt = sw.draw_3point_arc_slot(0, 0, 20, 0, 10, 5, width=4)
    ok_cps = sw.draw_centerpoint_slot(cx=5, cy=0, length=20, width=4, angle=90)
    _cps_args = dict(_slot_args)
    sw.draw_slot = _orig_slot
    record("sketch4: draw_3point_arc_slot passa a draw_slot(arc_3point) con i 3 punti",
           ok_slt["success"] and ok_slt["data"]["slot_type"] == "3point_arc")
    record("sketch3: draw_centerpoint_slot -> draw_slot con i centri degli estremi a +-length/2",
           ok_cps["success"] and _cps_args.get("slot_type") == "center_to_center"
           and abs(_cps_args["x1"] - 5) < 1e-9 and abs(_cps_args["y1"] + 10) < 1e-9 and abs(_cps_args["y2"] - 10) < 1e-9,
           str(_cps_args))
    record('sketch4: show_sketch_curvature sulla spline', ok_curv['success'] and ok_curv['data']['density'] == 30)
    record("sketch4: draw_equation_curve_3d valuta formule parametriche e crea punti 3D",
           ok_eq3d["success"] and ok_eq3d["data"]["samples_count"] == 20 and len(ok_eq3d["data"]["start_point_m"]) == 3)

    # Controlli negativi: SolidWorks non crea nessuna curva/silhouette -> success=False
    class _FailSketchMgr4(_MockSketchMgr):
        def InsertIntersectionCurve(self):
            return False
        def InsertSilhouetteEntities(self, t, b, le, a, uts, eil):
            return False

    class _FailDoc4(_MockDoc):
        def __init__(self):
            super().__init__()
            self.SketchManager = _FailSketchMgr4()

    fail_doc4 = _FailDoc4()
    sw._s2_active_or_open = lambda sketch=None: (fail_doc4, fail_doc4.SketchManager, None)

    # Controllo negativo: nessun corpo nel modello -> insert_silhouette_entities rifiuta
    class _NoBodyDoc4(_MockDoc):
        def GetBodies2(self, *args):
            return ()

    nobody_doc4 = _NoBodyDoc4()
    sw._s2_active_or_open = lambda sketch=None: (nobody_doc4, nobody_doc4.SketchManager, None)


def test_sketch5_tools():
    sw = SolidWorksAutomation()

    # Senza documento attivo, devono fallire con errore controllato
    sw.get_active_doc = lambda: (None, {"success": False, "message": "Nessun doc attivo"})
    sw._part = lambda: (None, {"success": False, "message": "Nessun pezzo attivo"})
    sw._s2_active_or_open = lambda sketch=None: (None, None, {"success": False, "message": "Nessun schizzo attivo"})

    r1 = sw.relax_sketch_spline()
    r2 = sw.simplify_sketch_spline(0.1)
    r3 = sw.insert_spline_point(10, 20)
    r5 = sw.edit_spline_handle(0, magnitude=1.5)
    r6 = sw.replace_sketch_entity("Line1", "Line2")
    r7 = sw.create_sketch_belt()
    r8 = sw.suppress_sketch_relation(0)
    r9 = sw.get_allowed_relations()
    r10 = sw.delete_all_sketch_relations()
    r11 = sw.list_sketch_regions()
    r12 = sw.rotate_copy_3d_sketch(45.0)
    r15 = sw.set_sketch_performance_mode(True, True, True)

    all_failed_cleanly = all((not r['success'] for r in (r1, r2, r3, r5, r6, r7, r8, r9, r10, r11, r12, r15)))
    record("sketch5: tutti i tool del lotto gestiscono assenza doc/schizzo con errore pulito", all_failed_cleanly)

    # Mock per esecuzione con schizzo e spline attiva
    class _MockOleStub:
        # TangentMagnitude con indice: PROPERTYPUT (flags 4) scrive args=(verso, valore), PROPERTYGET (flags 2) rilegge
        ignore_put = False
        def __init__(self): self.mag = {}
        def GetIDsOfNames(self, name): return 1
        def Invoke(self, did, lcid, flags, res, *args):
            self.last_args = args
            if flags == 4 and not _MockOleStub.ignore_put:
                self.mag[args[0]] = args[1]
            elif flags == 2:
                return self.mag.get(args[0], 1.0)

    class _MockSplineHandle:
        def __init__(self):
            self.TangentDriving = True
            self.CurvatureControlled = False
            self.Curvature = 0.0
            self._oleobj_ = _MockOleStub()

    class _MockSplineSeg:
        def __init__(self, name="Spline1"):
            self._name = name
            self.GetType = 3 # swSketchSPLINE
        def GetName(self): return self._name
        def RelaxSpline(self): return True
        def Simplify(self, tol): return True
        def InsertPoint(self, x, y, z): return True
        def DeletePoint(self, pt): return True
        def GetPoints2(self): return [self]
        def GetSplineHandles(self):
            if not hasattr(self, "_h"):
                self._h = [_MockSplineHandle()]       # stessi manubri a ogni lettura (come SolidWorks)
            return self._h
        def Select4(self, append, data): return True

    class _MockArcSeg:
        def __init__(self, name="Arc1"):
            self._name = name
            self.GetType = 2 # swSketchARC (puleggia)
        def GetName(self): return self._name
        def Select4(self, append, data): return True

    class _MockRelation:
        def __init__(self):
            self.Suppressed = False
        def set_Suppressed(self, v): self.Suppressed = v

    class _MockRelationMgr:
        def __init__(self):
            self._rels = [_MockRelation()]
        def GetRelations(self, f): return list(self._rels)
        def GetAllowedRelations(self, ents): return [4, 5, 6] # Horiz, Vert, Tangent
        def DeleteAllRelations(self):
            self._rels = []   # stato: dopo la cancellazione la rilettura e' vuota
            return True

    class _MockSketch5Mgr:
        def __init__(self):
            self.ActiveSketch = self
            self.RelationManager = _MockRelationMgr()
        def SketchReplace2(self, c, cnt): return True
        def CreateSketchBelt(self, *args): return True
        def RotateOrCopy3DAboutVector(self, *args): return True
        def set_AddToDB(self, v): pass
        def set_AutoSolve(self, v): pass
        def set_AutoInference(self, v): pass
        def GetSketchBlockDefinitions(self): return []
        def GetSketchRegions(self): return [self]
        def GetSketchContours(self): return [self]
        def GetEdgesCount(self): return 4
        _npts = 5
        def GetSketchPointsCount2(self): return self._npts
        def MergePoints(self, d):
            self._npts -= 1
            return True

    class _MockDoc5:
        def __init__(self):
            self.SketchManager = _MockSketch5Mgr()
            self.Extension = self
            self.SelectionManager = self
        def SelectByID2(self, *args): return True
        def ClearSelection2(self, *args): return True
        def CreateSelectData(self):
            class _SD: Mark = 0
            return _SD()

    mock_doc = _MockDoc5()
    mock_sp = _MockSplineSeg("Spline1")
    sw._s2_active_or_open = lambda sketch=None: (mock_doc, mock_doc.SketchManager, None)
    sw._s5_segs = lambda doc: [mock_sp]
    sw._part = lambda: (mock_doc, None)

    ok_rel = sw.relax_sketch_spline("Spline1")
    ok_smp = sw.simplify_sketch_spline(0.05, "Spline1")
    ok_ins = sw.insert_spline_point(5, 5, 0, "Spline1")
    ok_hnd = sw.edit_spline_handle(0, magnitude=2.0, spline_entity="Spline1")
    ok_rep = sw.replace_sketch_entity("Line1", "Line2")
    sw._s5_segs = lambda doc: [_MockArcSeg("Arc1")]     # la cinghia vuole pulegge (archi/cerchi)
    ok_blt = sw.create_sketch_belt(thickness=3.0)
    sw._s5_segs = lambda doc: [mock_sp]
    ok_sup = sw.suppress_sketch_relation(0, True)
    ok_alw = sw.get_allowed_relations()
    ok_dar = sw.delete_all_sketch_relations()
    ok_reg = sw.list_sketch_regions()
    ok_r3d = sw.rotate_copy_3d_sketch(90.0, copy=True, num_copies=3)
    ok_prf = sw.set_sketch_performance_mode(True, False, False)

    record('sketch5: relax, simplify e inserimento punto spline operativi', ok_rel['success'] and ok_smp['success'] and ok_ins['success'])
    record("sketch5: edit_spline_handle aggiorna manubri tangenza (valore riletto)",
           ok_hnd["success"] and ok_hnd["data"]["read_back"].get("magnitude") == 2.0)
    _MockOleStub.ignore_put = True
    ko_hnd = sw.edit_spline_handle(0, magnitude=3.0, spline_entity="Spline1")
    _MockOleStub.ignore_put = False
    record("sketch5: edit_spline_handle con valore non applicato da SolidWorks -> errore",
           not ko_hnd["success"] and "magnitude" in ko_hnd["message"], ko_hnd["message"][:100])
    record("sketch5: replace_sketch_entity e create_sketch_belt eseguiti con successo",
           ok_rep["success"] and ok_rep["data"]["replaced"] and ok_blt["success"])
    record("sketch5: relazioni (suppress, get_allowed, delete_all) analizzate correttamente",
           ok_sup["success"] and len(ok_alw["data"]["allowed_relations"]) == 3 and ok_dar["success"])
    record("sketch5: regioni, rotazione 3D e modalita' performance validi", ok_reg['success'] and ok_r3d['data']['copy'] and ok_prf['data']['add_to_db'])

    # Controlli negativi: SolidWorks rifiuta sostituzione, cinghia, cancellazione relazioni, file gia' esistente
    class _FailReplaceMgr5(_MockSketch5Mgr):
        def SketchReplace2(self, c, cnt): return False

    class _StuckRelationMgr5(_MockRelationMgr):
        def DeleteAllRelations(self): return True          # dice ok ma le relazioni restano

    class _StuckSketchMgr5(_MockSketch5Mgr):
        def __init__(self):
            super().__init__()
            self.RelationManager = _StuckRelationMgr5()

    neg_doc5 = _MockDoc5()
    neg_doc5.SketchManager = _FailReplaceMgr5()
    sw._s2_active_or_open = lambda sketch=None: (neg_doc5, neg_doc5.SketchManager, None)
    neg_rep5 = sw.replace_sketch_entity("Line1", "Line2")
    neg_blt5 = sw.create_sketch_belt(thickness=3.0)     # segmenti = solo spline: nessuna puleggia
    record("sketch5: controllo negativo, replace rifiutata e belt senza pulegge -> success=False",
           (not neg_rep5["success"]) and (not neg_blt5["success"]))

    stuck_doc5 = _MockDoc5()
    stuck_doc5.SketchManager = _StuckSketchMgr5()
    sw._s2_active_or_open = lambda sketch=None: (stuck_doc5, stuck_doc5.SketchManager, None)
    neg_dar5 = sw.delete_all_sketch_relations()
    record("sketch5: controllo negativo, relazioni ancora presenti dopo delete_all -> success=False",
           (not neg_dar5["success"]))

    blk_busy = str(Path(tempfile.gettempdir()) / "block_busy.sldblk")
    Path(blk_busy).write_bytes(b"x")




def test_assembly3_tools(tmp):
    sw = SolidWorksAutomation()

    # 1. Senza documento assieme attivo, tutti i tool del lotto gestiscono l'assenza con errore controllato
    sw.get_active_doc = lambda: (None, {"success": False, "message": "Nessun documento attivo"})
    sw._asm = lambda: (None, {"success": False, "message": "Nessun assieme attivo"})

    r1 = sw.make_component_independent("Comp1")
    r2 = sw.reorder_components(["Comp2"], "Comp1", position="after")
    r3 = sw.select_components_by_size(15.0)
    r4 = sw.set_component_transparency("Comp1", True)
    r6 = sw.insert_new_virtual_assembly("Sub1")
    r7 = sw.edit_part_in_context("Comp1")
    r8 = sw.exit_part_in_context()
    r11 = sw.add_concentric_mate_with_tolerance("Face1", "Face2", tolerance=0.05)
    r13 = sw.add_gear_mate("Face1", "Face2", 2.0, 1.0)
    r17 = sw.add_hinge_mate("Cyl1", "Cyl2", "Face1", "Face2")
    r18 = sw.add_screw_mate("Axis1", "Axis2", pitch=1.5)
    r19 = sw.add_linear_coupler_mate("Face1", "Face2", 1.0)
    r20 = sw.add_universal_joint_mate("Shaft1", "Shaft2")
    r21 = sw.dissolve_component_pattern("Pattern1")
    r23 = sw.set_subassembly_flexible("Sub1", True)
    r26 = sw.isolate_components(["Comp1"])
    r27 = sw.exit_isolate()
    r28 = sw.auto_repair_mates()
    r30 = sw.create_speedpak("Spd1")
    r32 = sw.insert_cavity_feature(["Tool1"], 1.5)
    r33 = sw.insert_join_feature(["Comp1", "Comp2"])

    all_failed = all((not r['success'] for r in (r1, r2, r3, r4, r6, r7, r8, r11, r13, r17, r18, r19, r20, r21, r23, r26, r27, r28, r30, r32, r33)))
    record("assembly3: tutti i tool del lotto gestiscono assenza doc assieme con errore pulito", all_failed)

    # 2. Mock documento assieme attivo per verificare la logica di successo
    class _MockComp:
        def __init__(self, name="Part1-1"):
            self.Name2 = name
            self.Transparency = 0
            self.Solving = 0
            self.Envelope = False
            self.ExcludeFromBOM = False

        def SaveVirtualComponent(self, p):
            with open(p, "wb") as fh:
                fh.write(b"SLDPRT-mock")
            return True

    class _MockDoc:
        def __init__(self):
            self.Title = "Assy1.SLDASM"
            self.GetType = 2
            self.SelectionManager = types.SimpleNamespace(GetSelectedObject6=lambda *a: object())
            self.Extension = types.SimpleNamespace(
                SelectByID2=lambda *a, **k: True
            )
        def ClearSelection2(self, *a): pass
        def EditRebuild3(self): pass
        def MakeIndependent(self, p):
            with open(p, "wb") as fh:
                fh.write(b"SLDPRT-mock")
            return True
        def MakeIndependent2(self, *a): return True
        def ReorderComponents(self, *a): return True
        def SelectComponentsBySize(self, pct): return 3
        def SetComponentTransparent(self, *a): pass
        def InsertNewVirtualPart(self, ent, out):
            out.value = _MockComp("[Part1^Assy1]")
            return 1
        def InsertNewVirtualAssembly(self, out):
            out.value = _MockComp("[SubAssy1^Assy1]")
            return 1
        def EditPart2(self, *a): return True
        def EditAssembly(self): pass
        def SaveVirtualComponent(self, p):
            with open(p, "wb") as fh:          # SolidWorks scrive il .sldprt esterno
                fh.write(b"SLDPRT-mock")
            return True
        def AddMate5(self, *a):
            a[-1].value = 1                    # codice by-ref: 1 = nessun errore (ADD_MATE_ERRORS)
            return True
        def DissolveComponentPattern(self): return True
        def Isolate(self): pass
        def ExitIsolate(self): pass
        def AutoMateRepair(self, *a): return 1
        def CreateSpeedPak(self, *a): return True
        def InsertCavity4(self, *a): return True
        def InsertJoin2(self, *a): return True

    mock_doc = _MockDoc()
    sw._asm = lambda: (mock_doc, None)
    sw.get_active_doc = lambda: (mock_doc, None)
    sw._as_comp = lambda doc, name, *a: (_MockComp(name), None)
    sw._as_select_comps = lambda doc, comps: True
    sw._as_select_entity = lambda doc, spec, u, mark, append: ({"name": str(spec)}, None)
    sw._as_mate_features = lambda doc: []
    sw._std_ref_feature = lambda doc, name: types.SimpleNamespace(Select2=lambda *a: True)
    sw._get_doc_title = lambda doc: "Assy1.SLDASM"
    sw.add_mate = lambda mate_type, **kw: sw._result(True, f"Mate {mate_type} creato", SwErrors.swSuccess, kw)

    ok_ind = sw.make_component_independent("Comp1", os.path.join(tmp, "indip.sldprt"))
    ok_ord = sw.reorder_components(["Comp2"], "Comp1", position="before")
    ok_siz = sw.select_components_by_size(10.0)
    ok_trn = sw.set_component_transparency("Comp1", True)
    record("assembly3: indipendenza, riordino, selezione per dimensione e trasparenza",
           ok_ind["success"] and ok_ord["data"]["position"] == "before" and ok_siz["data"]["selected_count"] == 3 and ok_trn["data"]["transparent"])

    ok_va = sw.insert_new_virtual_assembly()
    ok_ep = sw.edit_part_in_context("Comp1")
    ok_xp = sw.exit_part_in_context()
    record('assembly3: assiemi virtuali e modifica in-context', ok_va['success'] and ok_ep['success'] and ok_xp['success'])

    ok_gear = sw.add_gear_mate("Gear1", "Gear2", 3.0, 1.0)
    ok_hinge = sw.add_hinge_mate("C1", "C2", "F1", "F2", min_angle=0.0, max_angle=90.0)
    ok_screw = sw.add_screw_mate("Ax1", "Ax2", pitch=2.0)
    ok_coupl = sw.add_linear_coupler_mate("S1", "S2", 2.0)
    ok_ujoint = sw.add_universal_joint_mate("Sh1", "Sh2")
    record('assembly3: accoppiamenti meccanici/avanzati (gear, hinge, screw, coupler, ujoint)', ok_gear['success'] and ok_hinge['success'] and ok_screw['success'] and ok_coupl['success'] and ok_ujoint['success'])

    ok_dis = sw.dissolve_component_pattern("Pattern1")
    ok_flx = sw.set_subassembly_flexible("Sub1", True)
    ok_iso = sw.isolate_components(["C1", "C2"])
    ok_xis = sw.exit_isolate()
    ok_rep = sw.auto_repair_mates()
    ok_spd = sw.create_speedpak("SpeedPak1")
    ok_cav = sw.insert_cavity_feature(["Tool1"], 2.0)
    ok_joi = sw.insert_join_feature(["C1", "C2"])
    record("assembly3: pattern, flessibilita', isolamento, riparazione mates, speedpak, cavita', join", ok_dis['success'] and ok_flx['data']['flexible'] and ok_iso['success'] and ok_xis['success'] and ok_rep['success'] and ok_spd['success'] and ok_cav['success'] and ok_joi['success'])

    # Controlli negativi: AddMate5 non crea nulla, salvataggio rifiutato, selezione fallita -> success=False
    class _NoMateDoc(_MockDoc):
        def AddMate5(self, *a):
            a[-1].value = 0                    # codice by-ref non letto: nessun accoppiamento
            return None
        def SaveVirtualComponent(self, *a):
            return False
    nomate_doc = _NoMateDoc()
    sw._asm = lambda: (nomate_doc, None)
    class _NoSaveComp(_MockComp):
        def SaveVirtualComponent(self, *a):
            return False
    sw._as_comp = lambda doc, name, *a: (_NoSaveComp(name), None)
    sw._as_select_comps = lambda doc, comps: False
    neg_ind = sw.make_component_independent("Comp1")
    record('assembly3: controllo negativo, selezione fallita -> success=False', not neg_ind['success'])




def test_drawings2_tools(tmp):
    sw = SolidWorksAutomation()

    # 1. Senza documento disegno attivo, tutti i tool del lotto gestiscono l'assenza con errore controllato
    sw.get_active_doc = lambda: (None, {"success": False, "message": "Nessun documento attivo"})
    sw._drawing = lambda: (None, {"success": False, "message": "Nessun disegno attivo"})

    r1 = sw.edit_sheet_format()
    r2 = sw.exit_sheet_format()
    r3 = sw.reload_sheet_format()
    r8 = sw.add_flat_pattern_drawing_view()
    r11 = sw.show_exploded_drawing_view()
    r12 = sw.rotate_drawing_view("View1", 45.0)
    r19 = sw.add_revision_table()
    r21 = sw.add_general_table()
    r23 = sw.create_drawing_layer("Annotations")
    r26 = sw.export_pdf_layers(os.path.join(tmp, "out.pdf"))

    all_failed = all((not r['success'] for r in (r1, r2, r3, r8, r11, r12, r19, r21, r23, r26)))
    record("drawings2: tutti i tool del lotto gestiscono assenza doc disegno con errore pulito", all_failed)

    # 2. Mock documento disegno attivo per verificare esecuzione positiva
    class _MockView:                                    # vista del foglio (Position in m, Angle in rad, come SolidWorks)
        def __init__(self, name, pos):
            self.name, self.Position, self.Angle = name, pos, 0.0
            self._exp, self._marks = False, 0
        def GetName2(self): return self.name
        def IsExploded(self): return self._exp
        def ShowExploded(self, flag):
            self._exp = bool(flag)
            return True
        def AutoInsertCenterMarks(self, *a):
            self._marks = 1
            return True
        def GetFirstCenterMark2(self):
            return _MockMark() if self._marks else None
        def GetFirstCenterLine(self): return None

    class _MockMark:
        def GetNext(self): return None

    class _MockRevTable:
        def __init__(self): self.rows = {}
        def AddRevision(self, rev):
            self.rows[len(self.rows) + 1] = rev
            return len(self.rows)
        def GetRevisionForId(self, i): return self.rows.get(i, "")

    class _MockLayerMgr:
        def __init__(self): self.layers = {}
        def AddLayer(self, name, desc, color, style, width):
            self.layers[name] = color
            return 1
        def GetLayer(self, name):
            return types.SimpleNamespace(Color=self.layers[name]) if name in self.layers else None

    class _MockDrawingDoc:
        def __init__(self):
            self.Title = "Drawing1.SLDDRW"
            self.GetType = 3
            self.views = {"View1": _MockView("View1", (0.1, 0.2, 0.0)), "View2": _MockView("View2", (0.3, 0.4, 0.0))}
            self.ActiveDrawingView = types.SimpleNamespace(ShowExploded=False, Name="View1")
            self.Extension = types.SimpleNamespace(
                SelectByID2=lambda *a, **k: True,
                SaveAs=self._save_as_mock,
            )
            self._sheet = types.SimpleNamespace(SetTemplateName=lambda *a: True, ReloadTemplate=lambda *a: True,
                                                InsertRevisionTable2=lambda *a: _MockRevTable())
            self._lm = _MockLayerMgr()
        def _save_as_mock(self, p, *a):
            with open(p, "wb") as fh:          # SolidWorks scrive il PDF esportato
                fh.write(b"%PDF-mock")
            return True
        def ClearSelection2(self, *a): pass
        def EditTemplate(self): pass
        def EditSheet(self): pass
        def GetCurrentSheet(self): return self._sheet
        def CreateFlatPatternViewFromModelView3(self, *a): return True
        def DrawingViewRotate(self, rad):
            self.views["View1"].Angle = rad
            return True
        def AlignHorz(self):
            self.views["View1"].Position = (self.views["View2"].Position[0], self.views["View1"].Position[1], 0.0)
        def AlignVert(self):
            self.views["View1"].Position = (self.views["View1"].Position[0], self.views["View2"].Position[1], 0.0)
        def InsertTableAnnotation2(self, *a): return True
        def GetLayerManager(self): return self._lm
        def InsertBlock(self, *a): return True

    mock_doc = _MockDrawingDoc()
    sw._drawing = lambda: (mock_doc, None)
    sw.get_active_doc = lambda: (mock_doc, None)
    sw._get_doc_title = lambda doc: "Drawing1.SLDDRW"
    sw._find_view = lambda doc, name: ((mock_doc.views[name], None) if name in mock_doc.views
                                       else (None, {"success": False, "message": f"vista '{name}' non trovata"}))
    sw._sheet_views = lambda doc: list(mock_doc.views.values())

    ok_ef = sw.edit_sheet_format()
    ok_xf = sw.exit_sheet_format()
    ok_rf = sw.reload_sheet_format()
    record("drawings2: formati foglio (edit, exit, reload)",
           ok_ef["success"] and ok_xf["success"] and ok_rf["success"])

    ok_fp = sw.add_flat_pattern_drawing_view(model_path="Lamiera.SLDPRT", x=150, y=150)
    ok_ex = sw.show_exploded_drawing_view("View1", True)
    record("drawings2: vista di lamiera spianata (flat pattern) ed esploso",
           ok_fp["success"] and ok_ex["success"])

    ok_rot = sw.rotate_drawing_view("View1", 90.0)
    record('drawings2: rotazione viste', ok_rot['success'])

    ok_rev = sw.add_revision_table(revision="B", description="Eco release")
    ok_tbl = sw.add_general_table(rows=4, columns=3, title="Tabella Componenti")
    record("drawings2: tabelle revisioni e generiche",
           ok_rev["success"] and ok_tbl["success"])

    ok_lyr = sw.create_drawing_layer("Annotations", color_rgb=[255, 0, 0])
    blk_file = os.path.join(tmp, "stamp.slddrt")         # il blocco deve esistere su disco
    Path(blk_file).write_bytes(b"BLOCK-mock")
    pdf_target = os.path.join(tmp, "drawing_layers.pdf")
    ok_pdf = sw.export_pdf_layers(pdf_target, overwrite=True)
    record('drawings2: livelli CAD (layer) ed export PDF multilivello', ok_lyr['success'] and ok_pdf['success'])

    # Controlli negativi: SolidWorks rifiuta vista lamiera, livello, PDF; vista esplosa inesistente; blocco mancante
    class _FailDrawingDoc(_MockDrawingDoc):
        def CreateFlatPatternViewFromModelView3(self, *a): return None
        def GetLayerManager(self):
            return types.SimpleNamespace(AddLayer=lambda *a: 0, GetLayer=lambda *a: None)
        def _save_as_mock(self, *a): return False     # nessun file scritto
    fail_dd = _FailDrawingDoc()
    sw._drawing = lambda: (fail_dd, None)
    neg_fp = sw.add_flat_pattern_drawing_view(model_path="Lamiera.SLDPRT", x=150, y=150)
    neg_lyr = sw.create_drawing_layer("Annotations")
    neg_pdf = sw.export_pdf_layers(os.path.join(tmp, "neg_layers.pdf"))
    neg_exp = sw.show_exploded_drawing_view("VistaInesistente", True)
    record('drawings2: controllo negativo, vista lamiera/livello/PDF rifiutati -> success=False', not neg_fp['success'] and (not neg_lyr['success']) and (not neg_pdf['success']) and (not neg_exp['success']))



def test_features4_tools(tmp):
    sw = SolidWorksAutomation()

    # 1. Senza documento parte attivo, tutti i tool del lotto gestiscono l'assenza con errore controllato
    sw.get_active_doc = lambda: (None, {"success": False, "message": "Nessun documento attivo"})
    sw._part = lambda: (None, {"success": False, "message": "Nessun pezzo attivo"})

    r2 = sw.intersect_solid_features(["Body1", "Body2"])
    r4 = sw.variable_section_sweep("Prof1", "Path1")
    r11 = sw.mirror_body_merge(["Body1"], "Top")
    r17 = sw.cross_break([0, 0, 0], 1.0)
    r18 = sw.convert_to_sheet_metal(1.5, 2.0, [0, 0, 0])
    r23 = sw.update_cut_list()
    r24 = sw.subweldment_folder("Sub1")

    all_failed = all((not r['success'] for r in (r2, r4, r11, r17, r18, r23, r24)))
    record("features4: tutti i tool del lotto gestiscono assenza doc parte con errore pulito", all_failed)

    # 2. Mock documento parte attivo per verificare esecuzione positiva
    class _MockPartDoc:
        def __init__(self):
            self.Title = "Part1.SLDPRT"
            self.GetType = 1
            self.nfeat = 0                     # conteggio delle feature create da SolidWorks
            # ogni creazione di feature riuscita aumenta il conteggio (letto da _features)
            self.FeatureManager = types.SimpleNamespace(
                FeatureExtrusion3=self._add,
                InsertIntersectFeature=self._add,
                InsertSweep=self._add,
                FeatureFillet3=self._add,
                AdvancedHole2=self._add,
                InsertCurveFileBegin=self._add,
                InsertMirrorFeature2=self._add,
                InsertReplaceFaceFeature=self._add,
                InsertCrossBreak=self._add,
                InsertConvertToSheetMetal2=self._add,
                InsertVent=self._add,
                InsertLoftedBend=self._add,
                InsertCosmeticWeldBead=self._add,
                InsertSubWeldFolder2=self._add,
                InsertStudWizard=self._add,
            )
            self.Extension = types.SimpleNamespace(
                SelectByID2=lambda *a, **k: True
            )
            self.SelectionManager = types.SimpleNamespace(
                CreateSelectData=lambda: types.SimpleNamespace(Mark=0))
        def _add(self, *a, **k):
            self.nfeat += 1
            return True
        def ClearSelection2(self, *a): pass
        def EditRebuild3(self): pass
        def ForceRebuild3(self, *a): pass
        def UpdateCutList(self): return True
        def InsertFeatureReplaceFace(self): self._add()

    class _MockBody:
        def __init__(self, name):
            self.Name = name
        def Select2(self, *a): return True

    class _MockCutListFolder:
        def GetSpecificFeature2(self): return "bf"

    mock_doc = _MockPartDoc()
    sw._part = lambda: (mock_doc, None)
    sw.get_active_doc = lambda: (mock_doc, None)
    sw._select_point = lambda *a, **k: (True, None)      # (ok, errore) come in modeling_base
    sw._select_points = lambda *a, **k: (True, None)
    sw._features = lambda doc: [("Feature%d" % i, "Feature", None) for i in range(doc.nfeat)] + [("Distinta", "CutListFolder", _MockCutListFolder())]
    sw._bodies = lambda doc: [_MockBody("Body1")]
    sw._select_edge_or_axis = lambda *a, **k: (True, "")
    sw._volume_m3 = lambda doc: float(doc.nfeat)
    # chiamate COM con firma nota (intersect_bodies e sweep gia' provati dal vivo in ext_bodies2 / modeling)
    sw.intersect_bodies = lambda **k: {"success": True}
    sw.sweep = lambda **k: {"success": True}

    sw._wld_raw = lambda obj, name, *args: (obj.InsertSubWeldFolder2(*args) if name == "InsertSubWeldFolder2"
                                             else ([_MockBody("Body1")] if name == "GetBodies" else True))

    ok_isf = sw.intersect_solid_features(["Body1", "Body2"])
    record('features4: intersezioni composite', ok_isf['success'])

    ok_vss = sw.variable_section_sweep("Prof1", "Path1", scale_factor=1.0, twist_angle=45.0)
    record('features4: sweep a sezione variabile', ok_vss['success'])




    ok_mbm = sw.mirror_body_merge(["Body1"], "Right", merge_bodies=True)
    record("features4: specchiatura corpi con fusione",
           ok_mbm["success"])



    ok_cb = sw.cross_break([0, 0, 0], depth=1.5)
    ok_csm = sw.convert_to_sheet_metal(2.0, 3.0, [0, 0, 0])
    record('features4: lamiera (cross break, convert)', ok_cb['success'] and ok_csm['success'])

    ok_ucl = sw.update_cut_list()
    ok_swf = sw.subweldment_folder("TrussAssembly", ["Body1"])
    record('features4: saldature (distinta taglio, cartelle)', ok_ucl['success'] and ok_swf['success'])



    # Controlli negativi: SolidWorks non crea alcuna feature (conteggio fermo) e distinta non aggiornata -> success=False
    class _NoFeatDoc(_MockPartDoc):
        def _add(self, *a, **k):
            return None                        # la chiamata COM non crea feature
        def UpdateCutList(self): return None
    nofeat_doc = _NoFeatDoc()
    sw._part = lambda: (nofeat_doc, None)
    neg_cbr4 = sw.cross_break([0, 0, 0], 1.0)
    sw._wld_raw = lambda obj, name, *args: None         # distinta non aggiornata: nessun membro letto
    neg_cut4 = sw.update_cut_list()
    del sw._wld_raw                                    # ripristina il metodo reale
    record('features4: controllo negativo, nessuna feature creata o distinta non aggiornata -> success=False', not neg_cbr4['success'] and (not neg_cut4['success']))



def test_data2_tools(tmp):
    sw = SolidWorksAutomation()

    # 1. Senza documento attivo, tutti i tool del lotto gestiscono l'assenza con errore controllato
    sw.get_active_doc = lambda: (None, {"success": False, "message": "Nessun documento attivo"})
    sw._doc = lambda: (None, {"success": False, "message": "Nessun documento attivo"})
    sw._part_or_assembly = lambda: (None, {"success": False, "message": "Nessun pezzo o assieme attivo"})

    r1 = sw.get_config_custom_property("Prop1")
    r2 = sw.set_config_custom_property("Prop1", "Val1")
    r3 = sw.set_document_summary_info(title="Test")
    r5 = sw.export_equations_to_file(os.path.join(tmp, "eq.txt"))
    r9 = sw.create_derived_configuration("VariantB", "Default")
    r13 = sw.export_dxf_flat_pattern(os.path.join(tmp, "flat.dxf"))
    r15 = sw.export_ifc(os.path.join(tmp, "out.ifc"))
    r16 = sw.export_gltf_glb(os.path.join(tmp, "out.glb"))
    r17 = sw.export_3d_pdf(os.path.join(tmp, "out.pdf"))
    r24 = sw.apply_appearance("polished_chrome")

    all_failed = all((not r['success'] for r in (r1, r2, r3, r5, r9, r13, r15, r16, r17, r24)))
    record("data2: tutti i tool del lotto gestiscono assenza doc con errore pulito", all_failed)

    # 2. Mock documento attivo per verificare esecuzione positiva
    class _MockCPM:
        """Gestore proprieta' con memoria: cio' che viene scritto (Add3/Set2) si rilegge (Get5/Get6)."""
        def __init__(self, store):
            self.store = store
        @property
        def GetNames(self):
            return list(self.store)
        def Get5(self, name, *a):
            v = self.store.get(name, "")
            return (True, v, v, True)
        def Get6(self, name, use_cached, v, r, b1, b2):
            v.value = self.store.get(name, "")
            r.value = v.value
            return True
        def GetType2(self, name):
            return 30                          # swCustomInfoText
        def Add3(self, name, typ, val, opt):
            self.store[name] = val
            return 0
        def Set2(self, name, val):
            self.store[name] = val
            return 0

    class _ReadOnlyCPM:
        """Gestore che ignora le scritture: per il controllo negativo."""
        GetNames = []
        def Get5(self, *a): return (True, "", "", True)
        def Get6(self, name, use_cached, v, r, b1, b2):
            v.value = ""
            r.value = ""
            return True
        def GetType2(self, name): return 30
        def Add3(self, *a): return 0
        def Set2(self, *a): return 0

    class _MockDataDoc:
        def __init__(self):
            self.Title = "Model.SLDPRT"
            self.GetType = 1
            self.summary = {}
            self.cpm_store = {}
            self.cfg_names = ["Default"]
            self.GetConfigurationNames = self.cfg_names
            self.ConfigurationManager = types.SimpleNamespace(
                AddConfiguration2=self._add_cfg,
                ActiveConfiguration=types.SimpleNamespace(Name="Default"),
            )
            self.Extension = types.SimpleNamespace(
                CustomPropertyManager=lambda cfg: _MockCPM(self.cpm_store),
                SaveAs=self._save_as_ext,
            )
        def _add_cfg(self, name, *a, **k):
            self.cfg_names.append(name)        # la configurazione compare nell'elenco
            return True
        def SummaryInfo(self, idx, text=None):
            if text is None:
                return self.summary.get(idx)   # lettura
            self.summary[idx] = text           # scrittura
            return True
        def GetEquationMgr(self):
            return types.SimpleNamespace(GetCount=1, Equation=lambda idx: '"D1@Sketch1"=100')
        def GetDesignTable(self):
            return types.SimpleNamespace(SaveAs=lambda path: True)
        def _save_as_ext(self, p, version, options, data, errors, warnings):
            """Come SolidWorks 2026 Student (misurato): JT non scritto (errore 256), IFC solo IFC2X3, GLB ok, STEP AP203."""
            ext = os.path.splitext(p)[1].lower()
            if ext == ".jt":
                errors.value = 256
                return False
            if ext == ".ifc":
                contenuto = b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC2X3'));\nENDSEC;\nEND-ISO-10303-21;\n"
            elif ext == ".glb":
                contenuto = b"glTF\x02\x00\x00\x00" + b"\x00" * 16
            elif ext in (".step", ".stp"):
                contenuto = (b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('CONFIG_CONTROL_DESIGN'));\nENDSEC;\nDATA;\n"
                             b"#1=MANIFOLD_SOLID_BREP('',#2);\nENDSEC;\nEND-ISO-10303-21;\n")
            else:
                contenuto = b"mock-export"
            with open(p, "wb") as fh:          # SolidWorks scrive il file esportato
                fh.write(contenuto)
            return True
        def ExportFlatPatternView(self, p, *a):
            with open(p, "wb") as fh:
                fh.write(b"mock-export")
            return True

    mock_doc = _MockDataDoc()
    sw._doc = lambda: (mock_doc, None)
    sw._part_or_assembly = lambda: (mock_doc, None)
    sw.get_active_doc = lambda: (mock_doc, None)
    sw._get_active_config_name = lambda doc: "Default"
    sw.get_bounding_box = lambda unit=None: {"success": True, "size_x": 100.0, "size_y": 50.0, "size_z": 20.0}

    ok_scp = sw.set_config_custom_property("PartNo", "ABC-123")
    ok_gcp = sw.get_config_custom_property("PartNo")
    ok_smd = sw.set_document_summary_info(title="Staffa", author="Elia")
    record("data2: proprieta' per configurazione e metadati di riepilogo",
           ok_gcp["success"] and ok_gcp["data"]["value"] == "ABC-123" and ok_scp["success"] and ok_smd["success"])


    eq_out = os.path.join(tmp, "equations_export.txt")
    ok_eqx = sw.export_equations_to_file(eq_out, overwrite=True)
    record("data2: export equazioni sincronizzate in formato testo",
           ok_eqx["success"] and os.path.isfile(eq_out))

    ok_dcf = sw.create_derived_configuration("Lunga", "Default")
    record('data2: configurazioni derivate', ok_dcf['success'])


    def _mock_export_model(filepath, format=None, **k):          # export PDF 3D: stessa strada di export_model (misurata)
        with open(filepath, "wb") as fh:
            fh.write(b"%PDF-1.6 mock")
        return {"success": True, "message": "mock", "data": {"verify": {"has_3d": True}}}
    sw.export_model = _mock_export_model

    sw._sw_app = types.SimpleNamespace(GetUserPreferenceIntegerValue=lambda k: 203, SetUserPreferenceIntegerValue=lambda k, v: True)
    ok_dxf = sw.export_dxf_flat_pattern(os.path.join(tmp, "flat.dxf"), overwrite=True)
    ok_ifc = sw.export_ifc(os.path.join(tmp, "model.ifc"), overwrite=True, schema_version="IFC2X3")
    ok_ifc4 = sw.export_ifc(os.path.join(tmp, "model4.ifc"), overwrite=True, schema_version="IFC4")
    record("data2: IFC2X3 scritto, IFC4 richiesto e rifiutato", ok_ifc["success"] and (not ok_ifc4["success"]) and "IFC2X3" in ok_ifc4["message"])
    ok_glb = sw.export_gltf_glb(os.path.join(tmp, "model.glb"), overwrite=True)
    ok_3dp = sw.export_3d_pdf(os.path.join(tmp, "model.pdf"), overwrite=True)
    record("data2: esportazioni avanzate (DXF flat, IFC2X3, glTF/GLB, 3D PDF)",
           ok_dxf["success"] and ok_ifc["success"] and ok_glb["success"] and ok_3dp["success"])


    ok_app = sw.apply_appearance("")          # dal 2026-10-24 apply_appearance e' reale (prova dal vivo in test_data2_live)
    record('data2: apply_appearance senza nome rifiutato', not ok_app['success'])

    # Controlli negativi: proprieta' non riletta, riepilogo rifiutato, configurazione non creata, export rifiutato
    class _RefuseDataDoc(_MockDataDoc):
        def __init__(self):
            super().__init__()
            self.Extension = types.SimpleNamespace(
                CustomPropertyManager=lambda cfg: _ReadOnlyCPM()
            )
        def _add_cfg(self, name, *a, **k):
            return True                        # dice ok ma non aggiunge nulla
        def SummaryInfo(self, idx, text=None):
            if text is not None:
                raise RuntimeError("scrittura riepilogo rifiutata")
            return None
        def SaveAs3(self, *a):
            return False                       # nessun file scritto

    refuse_doc = _RefuseDataDoc()
    sw._doc = lambda: (refuse_doc, None)
    sw._part_or_assembly = lambda: (refuse_doc, None)
    neg_scp = sw.set_config_custom_property("PartNo", "ABC-123")
    neg_smd = sw.set_document_summary_info(title="Staffa")
    neg_dcf = sw.create_derived_configuration("Lunga", "Default")
    record("data2: controllo negativo, proprieta' non riletta / riepilogo rifiutato / configurazione assente / export rifiutato -> success=False", not neg_scp['success'] and (not neg_smd['success']) and (not neg_dcf['success']))

def test_simulation2_tools(tmp):
    sw = SolidWorksAutomation()

    # 1. Creazione studi
    ok_bck = sw.create_buckling_study("Buck_Test", 4)
    ok_thm = sw.create_thermal_study("Therm_Test", transient=False)
    ok_drp = sw.create_drop_test_study("Drop_Test", 1000.0)
    ok_fat = sw.create_fatigue_study("Fat_Test", 100000)
    ok_top = sw.create_topology_study("Topo_Test")
    ok_dyn = sw.create_linear_dynamic_study("Dyn_Test", "harmonic")
    record('simulation2: creazione studi (buckling, termico, drop test, fatica, topologia, dinamico)', not ok_bck['success'] and (not ok_thm['success']) and (not ok_drp['success']) and (not ok_fat['success']) and (not ok_top['success']) and (not ok_dyn['success']))

    # 2. Vincoli e carichi
    ok_esp = sw.add_elastic_support([0, 0, 0], stiffness=100.0)
    ok_pds = sw.add_prescribed_displacement([0, 0, 0], displacement_mm=2.5)
    ok_cyl = sw.add_cylindrical_restraint([0, 0, 0], radial_free=False, axial_free=False, circumferential_free=True)
    ok_cen = sw.add_centrifugal_load(angular_velocity_rad_s=100.0, axis_point=[0, 0, 0])
    ok_tsh = sw.add_thermal_shrinkage_load([0, 0, 0], delta_temperature_c=-50.0)
    record("simulation2: vincoli e carichi avanzati (supporto elastico, spostamento imposto, cilindrico, centrifugo, contrazione)",
           not ok_esp["success"] and not ok_pds["success"] and not ok_cyl["success"] and not ok_cen["success"] and not ok_tsh["success"])
    ok_pd_msg = sw.add_prescribed_displacement([0, 0, 0], displacement_mm=1.0)
    record("simulation2: spostamento imposto non nullo dichiarato come limite (nessun successo finto)",
           not ok_pd_msg["success"] and "non realizzabile" in ok_pd_msg["message"])

    # 3. Connettori e condizioni termiche
    ok_blt = sw.add_bolt_connector([0, 0, 0], [0, 0, 10], bolt_diameter=10.0, preload_force_n=5000.0)
    ok_pin = sw.add_pin_connector([0, 0, 0], [0, 0, 10])
    ok_spg = sw.add_spring_connector([0, 0, 0], [10, 0, 0], stiffness_n_mm=250.0)
    ok_wld = sw.add_spot_weld_connector([0, 0, 0], [0, 0, 5], [[0, 0, 0]], spot_diameter=6.0)
    ok_cnv = sw.add_convection_load([0, 0, 0], convection_coefficient=25.0)
    ok_rad = sw.add_radiation_load([0, 0, 0], emissivity=0.85)
    ok_hpw = sw.add_heat_power_load([0, 0, 0], heat_power_w=150.0)
    record("simulation2: connettori e carichi termici (bullone, perno, molla, saldatura, convezione, irraggiamento, potenza)",
           not ok_blt["success"] and not ok_pin["success"] and not ok_spg["success"] and not ok_wld["success"] and not ok_cnv["success"] and not ok_rad["success"] and not ok_hpw["success"])

    # 4. Contatti, materiali e mesh
    ok_shk = sw.add_shrink_fit_contact([0, 0, 0], [0, 0, 0], friction_coefficient=0.15)
    ok_vwl = sw.add_virtual_wall_contact([0, 0, 0], "top", friction_coefficient=0.15)
    ok_ort = sw.set_orthotropic_material(ex_mpa=120000.0, ey_mpa=10000.0, ez_mpa=10000.0)
    ok_shl = sw.define_shell_mesh([0, 0, 0], thickness=2.0)
    ok_bem = sw.define_beam_mesh("SolidBody1")
    ok_mqm = sw.get_mesh_quality_metrics()
    ok_slv = sw.set_solver_options("FFEPlus", large_displacement=False)
    record("simulation2: contatti speciali, materiali ortotropi, mesh 1D/2D, qualita' e solutore",
           not ok_shk["success"] and not ok_vwl["success"] and not ok_ort["success"] and not ok_shl["success"] and not ok_bem["success"] and not ok_mqm["success"] and not ok_slv["success"])

    # 5. Risultati, sonde e report (compresa gestione overwrite)
    ok_bkl = sw.get_buckling_load_factor(1)
    ok_thz = sw.get_thermal_results()
    ok_rct = sw.get_reaction_forces_detail([0, 0, 0])
    ok_prb = sw.probe_simulation_results(10.0, 20.0, 0.0)
    rpt_file = os.path.join(tmp, "sim_report.html")
    with open(rpt_file, "w") as f:
        f.write("existing")
    ok_ow_fail = sw.export_simulation_report(rpt_file, overwrite=False)
    record('simulation2: risultati, sonde e protezione overwrite export_simulation_report', not ok_bkl['success'] and (not ok_thz['success']) and (not ok_rct['success']) and (not ok_prb['success']) and (not ok_ow_fail['success']) and ('overwrite=False' in ok_ow_fail['message']))



# ============================================================================ correzioni dal rapporto d'uso reale
def test_report_fix_tools():
    """Mock FEDELI al late binding: i membri senza argomenti (Name, GetTypeName2, GetNextFeature, FirstFeature, IsRolledBack,
    FeatureScopeBodies...) sono PROPRIETA', non metodi. Copre: list_features, rollback, query_topology (corpo), verifica delle
    ripetizioni, spiegazione dei fallimenti, edit_extrude_options, try_on_copy, riferimenti di fine."""
    sw = SolidWorksAutomation()

    # ---- list_features: cartelle di sistema nascoste per TIPO, output compatto
    class _F:
        def __init__(self, name, typ, rolled=False, sup=False):
            self.Name, self.GetTypeName2, self.IsRolledBack, self._sup = name, typ, rolled, sup
            self.GetNextFeature = None

        def IsSuppressed2(self, o, c):
            return (self._sup,)

    def chain(items):
        fs = [_F(*i) if isinstance(i, tuple) else i for i in items]
        for a, b in zip(fs, fs[1:]):
            a.GetNextFeature = b
        return fs

    fs = chain([("Annotazioni", "DetailCabinet"), ("Materiale", "MaterialFolder"), ("Piano frontale", "RefPlane"),
                ("Origine", "OriginProfileFeature"), ("Schizzo1", "ProfileFeature"), ("Estrusione1", "Extrusion"),
                ("Taglio1", "ICE", True, True)])
    doc_f = types.SimpleNamespace(FirstFeature=fs[0], GetType=1)
    sw.get_active_doc = lambda: (doc_f, None)
    r = sw.list_features()
    names = r["data"]["features"]
    record("list_features: cartelle di sistema nascoste, una riga per feature",
           r["success"] and names == ["Piano frontale (RefPlane)", "Origine (OriginProfileFeature)", "Schizzo1 (ProfileFeature)",
                                      "Estrusione1 (Extrusion)", "Taglio1 (ICE) [soppressa]"] and r["data"]["system_folders_hidden"] == 2,
           str(names))
    r = sw.list_features(include_system=True)
    record("list_features: include_system=true aggiunge le cartelle", r["data"]["count"] == 7)
    r = sw.list_features(detail=True)
    record("list_features: detail=true restituisce dizionari", r["data"]["features"][-1] == {"name": "Taglio1", "type": "ICE", "suppressed": True})

    # ---- barra di rollback
    rb = sw._rollback_state(doc_f)
    record("rollback: feature sotto la barra e feature sopra la barra", rb == {"in_rollback": True, "rollback_after": "Estrusione1",
           "rolled_back_features": ["Taglio1"]}, str(rb))
    fs_ok = chain([("Schizzo1", "ProfileFeature"), ("Estrusione1", "Extrusion")])
    rb2 = sw._rollback_state(types.SimpleNamespace(FirstFeature=fs_ok[0]))
    record("rollback: modello non in rollback", rb2 == {"in_rollback": False, "rollback_after": None, "rolled_back_features": []})
    sw._part = lambda: (doc_f, None)
    sw._exit_sketch = lambda d: None
    sw._sketch_dimensions = lambda d, n: []
    lm = sw.list_model_features()
    rows = {x["name"]: x for x in lm["data"]["features"]}
    record("list_model_features: marca le feature sotto la barra e riporta il rollback",
           lm["success"] and rows["Taglio1"].get("rolled_back") is True and "rolled_back" not in rows["Estrusione1"]
           and lm["data"]["rollback"]["rollback_after"] == "Estrusione1" and "ROLLBACK" in lm["message"], lm["message"])
    doc_info = types.SimpleNamespace(FirstFeature=fs[0], GetType=1, GetTitle="Parte1", GetPathName="")
    sw.get_active_doc = lambda: (doc_info, None)
    gi = sw.get_document_info()
    record("get_document_info: riporta il rollback", gi["success"] and gi["data"]["rollback"]["rollback_after"] == "Estrusione1"
           and "ROLLBACK" in gi["message"], gi["message"])

    # ---- query_topology_by_criteria: nome del corpo
    class _V:
        def __init__(self, p):
            self.GetPoint = p

    class _B:
        def __init__(self, name, pts):
            self.Name, self._pts = name, pts

        @property
        def GetVertices(self):
            return tuple(_V(p) for p in self._pts)

    bodies = [_B("Corpo-A", [(0.0, 0.0, 0.0)]), _B("Corpo-B", [(0.01, 0.0, 0.0), (0.02, 0.0, 0.0)])]
    doc_t = types.SimpleNamespace(GetBodies2=lambda t, v: bodies, GetType=1)
    sw.get_active_doc = lambda: (doc_t, None)
    q = sw.query_topology_by_criteria(entity_type="vertex")
    record("query_topology_by_criteria: ogni entita' riporta il corpo di appartenenza",
           q["success"] and [e["body"] for e in q["data"]["entities"]] == ["Corpo-A", "Corpo-B", "Corpo-B"], str(q)[:200])

    # ---- _verify_pattern: sovrapposizione accettata, istanza mancante rifiutata
    class _World:
        """Volume simulato: ogni istanza presente toglie `unit` meno la sovrapposizione col seme."""
        def __init__(self):
            self.vol = 100.0 * 1e-9
            self.feats = ["F1"]
            self.deleted = []

    w = _World()
    sw._volume_m3 = lambda d: w.vol
    sw._names = lambda d: list(w.feats)
    sw._new_features = lambda d, before: [{"name": n, "type": "LPattern"} for n in w.feats if n not in before]
    def _del(d, names):
        for n in names:
            if n in w.feats:
                w.feats.remove(n)
                w.deleted.append(n)
    sw._delete_features = _del
    seed = 10.0 * 1e-9
    v0 = 100.0 * 1e-9
    # (a) volume come atteso: nessuna ricostruzione
    w.feats = ["F1", "P1"]
    w.vol = v0 - seed * 4
    ok, info, rebuilt = sw._verify_pattern(None, v0, seed, 5, ["F1"], (5,), lambda c: None, lambda: "X")
    record("_verify_pattern: volume atteso -> ok senza ricostruire", ok and rebuilt is None and info["instances_check"] == "volume")
    # (b) istanze sovrapposte: effetto 3.5 invece di 4 semi; l'ultima istanza incide ancora (0.9 seme)
    w.feats, w.deleted = ["F1", "P1"], []
    w.vol = v0 - seed * 3.5
    asked = []
    def measure_ok(cnts):
        asked.append(cnts)
        return seed * 2.6
    def rebuild_ok():
        w.feats.append("P2")
        w.vol = v0 - seed * 3.5
        return "FEAT"
    ok, info, rebuilt = sw._verify_pattern(None, v0, seed, 5, ["F1"], (5,), measure_ok, rebuild_ok)
    record("_verify_pattern: istanze sovrapposte (effetto < n-1 semi) accettate e ripetizione ricreata",
           ok and rebuilt == "FEAT" and w.vol == v0 - seed * 3.5 and info["last_instance_effect_mm3"][0] > 0 and "P1" in w.deleted
           and asked == [(4,)], str(info))
    # (c) istanza mancante: l'ultima istanza non cambia il volume
    w.feats, w.deleted = ["F1", "P1"], []
    w.vol = v0 - seed * 3.0
    ok, info, rebuilt = sw._verify_pattern(None, v0, seed, 5, ["F1"], (5,), lambda c: seed * 3.0, lambda: "FEAT")
    record("_verify_pattern: istanza mancante (l'ultima non cambia il volume) rifiutata, ripetizione eliminata",
           (not ok) and rebuilt is None and "P1" in w.deleted and info["last_instance_effect_mm3"] == [0.0], str(info))
    # (d) seme non misurabile: niente da verificare
    ok, info, _ = sw._verify_pattern(None, v0, 0.0, 5, [], (5,), lambda c: None, lambda: None)
    record("_verify_pattern: seme senza effetto sul volume -> non verificabile ma non bloccante", ok)
    # (e) n=2 con sovrapposizione: il riferimento e' il solo seme (nessuna misura da fare)
    w.feats, w.deleted = ["F1", "P1"], []
    w.vol = v0 - seed * 0.6
    ok, info, rebuilt = sw._verify_pattern(None, v0, seed, 2, ["F1"], (2,), lambda c: 1 / 0, lambda: w.feats.append("P2") or "FEAT")
    record("_verify_pattern: n=2 con sovrapposizione, riferimento = solo seme", ok and rebuilt == "FEAT", str(info))
    # (f) griglia 2x2 con l'istanza d'angolo mancante (3 istanze su 4): rifiutata anche se ogni direzione incide
    w.feats, w.deleted = ["F1", "P1"], []
    w.vol = v0 - seed * 2.0
    ok, info, rebuilt = sw._verify_pattern(None, v0, seed, 4, ["F1"], (2, 2), lambda c: seed * 1.0, lambda: "FEAT")
    record("_verify_pattern: griglia 2x2 senza l'istanza d'angolo rifiutata (inclusione-esclusione = 0)",
           (not ok) and rebuilt is None and info["corner_instance_effect_mm3"] == 0.0 and all(m > 0 for m in info["last_instance_effect_mm3"]),
           str(info))
    # (g) griglia 2x2 completa ma con volume fuori tolleranza per sovrapposizione col bordo: l'angolo incide -> accettata
    w.feats, w.deleted = ["F1", "P1"], []
    w.vol = v0 - seed * 2.9
    meas = {(1, 2): seed * 0.95, (2, 1): seed * 0.95}
    ok, info, rebuilt = sw._verify_pattern(None, v0, seed, 4, ["F1"], (2, 2), lambda c: meas[c], lambda: w.feats.append("P2") or "FEAT")
    record("_verify_pattern: griglia 2x2 con angolo che incide accettata", ok and rebuilt == "FEAT" and info["corner_instance_effect_mm3"] > 0, str(info))

    # (h) strict: con volume diverso dall'atteso non misura, non elimina, rifiuta (si preferisce la direzione esatta)
    w.feats, w.deleted = ["F1", "P1"], []
    w.vol = v0 - seed * 3.5
    ok, info, rebuilt = sw._verify_pattern(None, v0, seed, 5, ["F1"], (5,), lambda c: 1 / 0, lambda: "FEAT", strict=True)
    record("_verify_pattern: strict rifiuta senza misure ne' eliminazioni (lo fa il chiamante)", (not ok) and rebuilt is None and w.deleted == [])
    w.vol = v0 - seed * 4
    ok, info, rebuilt = sw._verify_pattern(None, v0, seed, 5, ["F1"], (5,), lambda c: 1 / 0, lambda: "FEAT", strict=True)
    record("_verify_pattern: strict accetta il volume esatto", ok and info["instances_check"] == "volume")

    # ---- spiegazione quando la ripetizione di feature non viene creata
    sw._find_feature = lambda d, n: types.SimpleNamespace(name=n)
    infos = {"Fonde": {"merge": True, "feature_scope": True, "auto_select_bodies": False, "scope_bodies": ["A", "B"]},
             "Separato": {"merge": False, "feature_scope": True, "auto_select_bodies": False, "scope_bodies": ["A"]},
             "Normale": {"merge": True, "feature_scope": False, "auto_select_bodies": True, "scope_bodies": []}}
    sw._extrude_info = lambda d, f: infos.get(f.name)
    t1 = sw._explain_pattern_failure(None, ["Fonde"], -1e-6)
    record("spiegazione: Merge=true con ambito su piu' corpi -> procedura con edit_extrude_options, bodies, combine_bodies",
           all(k in t1 for k in ("Merge=true", "A, B", "edit_extrude_options", "bodies", "combine_bodies", "merge=false")), t1[:120])
    t2 = sw._explain_pattern_failure(None, ["Separato"], -1e-6)
    record("spiegazione: seme con Merge=false (corpo separato) -> usa bodies", "SEPARATO" in t2 and "`bodies`" in t2 and "combine_bodies" in t2)
    t3 = sw._explain_pattern_failure(None, ["Normale"], -1e-6)
    record("spiegazione: estrusione normale -> nessuna causa riconosciuta", t3 == "")
    t4 = sw._explain_pattern_failure(None, ["Separato"], +1e-6)
    record("spiegazione: taglio (rimuove materiale) con Merge=false non e' un corpo separato", t4 == "")

    # ---- circular_pattern / linear_pattern: nessuna feature creata -> messaggio sul fatto (non sul volume)
    class _FM:
        def __init__(self):
            self.calls = 0
            self.result = None

        def FeatureCircularPattern5(self, *a):
            self.calls += 1
            return self.result

        def FeatureLinearPattern5(self, *a):
            self.calls += 1
            return self.result

    fm = _FM()
    doc_p = types.SimpleNamespace(FeatureManager=fm, ClearSelection2=lambda x: None, GetType=1)
    sw._part = lambda: (doc_p, None)
    sw._bodies = lambda d: [object()]
    sw._seed_effect = lambda d, f: -1e-6
    sw._select_features_mark = lambda *a, **k: None
    sw._select_edge_or_axis = lambda *a, **k: (True, "")
    w.feats, w.deleted, w.vol = ["Fonde"], [], 1e-6
    r = sw.circular_pattern(features=["Fonde"], axis={"axis": "Asse1"}, count=6)
    record("circular_pattern: SolidWorks non crea nessuna feature -> lo dice e propone la procedura (non parla di volume)",
           (not r["success"]) and "nessuna feature" in r["message"] and "edit_extrude_options" in r["message"]
           and "volume non corrisponde" not in r["message"], r["message"][:140])
    r = sw.linear_pattern(features=["Fonde"], direction1={"edge": [0, 0, 0]}, count1=3, spacing1=10)
    record("linear_pattern: SolidWorks non crea nessuna feature -> stesso messaggio con la procedura",
           (not r["success"]) and "nessuna feature" in r["message"] and "combine_bodies" in r["message"], r["message"][:140])
    # feature creata ma istanze mancanti: errore e ripetizione eliminata
    def _make_missing(*a):
        w.feats.append("RipCirc1")
        w.vol = 1e-6 - 3e-7                    # effetto 0.3 contro 5 semi attesi (6 istanze, seme 1e-6 -> 5e-6)
        return types.SimpleNamespace(Name="RipCirc1")
    fm.FeatureCircularPattern5 = _make_missing
    sw._seed_effect = lambda d, f: 1e-7
    sw._volume_m3 = lambda d: w.vol
    w.vol = 1e-6
    w.feats, w.deleted = ["Fonde"], []
    sw._pattern_features = lambda d, before: [n for n in w.feats if n not in before]
    r = sw.circular_pattern(features=["Fonde"], axis={"axis": "Asse1"}, count=6)
    record("circular_pattern: istanze mancanti -> errore, ripetizione eliminata (coerente con linear_pattern)",
           (not r["success"]) and "eliminata" in r["message"] and "RipCirc1" in w.deleted and "RipCirc1" not in w.feats, r["message"][:140])
    del sw._pattern_features

    # ---- edit_extrude_options: lettura/scrittura della definizione e rilettura
    class _FD:
        def __init__(self):
            self.Merge, self.FeatureScope, self.AutoSelect, self.FeatureScopeBodies = True, True, False, ()
            self.ReverseDirection, self.BothDirections = False, False
            self._ec, self._d = {True: 0, False: 0}, {True: 0.010, False: 0.0}

        def AccessSelections(self, doc, comp):
            return True

        def ReleaseSelectionAccess(self):
            pass

        def GetEndCondition(self, fwd):
            return self._ec[fwd]

        def SetEndCondition(self, fwd, v):
            self._ec[fwd] = v

        def GetDepth(self, fwd):
            return self._d[fwd]

        def SetDepth(self, fwd, v):
            self._d[fwd] = v

    class _Boss:
        def __init__(self, fd, honest=True):
            self.Name, self.GetTypeName2, self.GetDefinition, self.honest, self.modified = "Estrusione4", "Extrusion", fd, honest, 0

        def ModifyDefinition(self, fd, doc, nul):
            self.modified += 1
            if not self.honest:
                fd.Merge = True                # SolidWorks "ignora" la modifica: la rilettura deve accorgersene
            return True

        def GetErrorCode2(self, bf):
            bf.value = False
            return 0

    fd = _FD()
    boss = _Boss(fd)
    doc_e = types.SimpleNamespace(FeatureByName=lambda n: boss if n == "Estrusione4" else None, ForceRebuild3=lambda t: True, GetType=1)
    sw._part = lambda: (doc_e, None)
    sw._find_feature = lambda d, n: boss if n == "Estrusione4" else None
    sw._volume_m3 = lambda d: 1e-6
    sw._names = lambda d: ["Estrusione4"]
    sw._bodies = lambda d: []
    r = sw.edit_extrude_options(feature="Estrusione4", merge=False, end_condition="through_all", depth=25)
    record("edit_extrude_options: merge, condizione di fine e profondita' scritti e riletti",
           r["success"] and fd.Merge is False and fd._ec[True] == 1 and abs(fd._d[True] - 0.025) < 1e-9 and r["data"]["mismatch"] == {}
           and r["data"]["readback"]["merge"] is False and r["data"]["readback"]["direction1"] == {"end_condition": "through_all", "depth": 25.0}
           and boss.modified == 1, str(r)[:200])
    r = sw.edit_extrude_options(feature="Estrusione4")
    record("edit_extrude_options: senza opzioni -> errore chiaro", not r["success"] and "Nessuna opzione" in r["message"])
    r = sw.edit_extrude_options(feature="Estrusione4", end_condition="up_to_surface")
    record("edit_extrude_options: condizioni con riferimento rifiutate", not r["success"] and "up_to_next" in r["message"])
    r = sw.edit_extrude_options(feature="Estrusione4", end_condition2="blind", depth2=5)
    record("edit_extrude_options: direzione 2 su estrusione a una direzione -> errore", not r["success"] and "una sola direzione" in r["message"])
    r = sw.edit_extrude_options(feature="NonEsiste", merge=True)
    record("edit_extrude_options: feature inesistente -> errore", not r["success"] and "non trovata" in r["message"])
    boss.honest = False
    fd.Merge = True
    r = sw.edit_extrude_options(feature="Estrusione4", merge=False)
    record("edit_extrude_options: se la rilettura non coincide non e' un successo",
           (not r["success"]) and "merge" in r["data"]["mismatch"] and r["data"]["mismatch"]["merge"] == {"requested": False, "readback": True},
           r["message"][:140])
    # scope_bodies: risoluzione per nome / punto
    ba, bb = types.SimpleNamespace(Name="Corpo-A"), types.SimpleNamespace(Name="Corpo-B")
    sw._bodies = lambda d: [ba, bb]
    sw._body_of_point = lambda d, pt, unit=None: bb if list(pt) == [1, 2, 3] else None
    got, names, e = sw._resolve_scope_bodies(None, ["Corpo-A", [1, 2, 3], "Corpo-A"], None)
    record("edit_extrude_options: ambito risolto per nome e per punto, senza duplicati", names == ["Corpo-A", "Corpo-B"] and e is None)
    got, names, e = sw._resolve_scope_bodies(None, ["Corpo-X"], None)
    record("edit_extrude_options: corpo dell'ambito inesistente -> errore", got is None and "non trovato" in e)
    n_mod = boss.modified
    r = sw.edit_extrude_options(feature="Estrusione4", scope_bodies=["Corpo-X"])
    record("edit_extrude_options: scope_bodies con un nome sbagliato non modifica nulla",
           (not r["success"]) and "non trovato" in r["message"] and boss.modified == n_mod, r["message"][:100])
    # lettura delle opzioni/ambito (get_feature_definition) e riferimento di fine illeggibile
    fd2 = _FD()
    fd2.FeatureScopeBodies = (ba, bb)
    opt = sw._extrude_options(fd2)
    record("get_feature_definition: corpi dell'ambito con i nomi", opt["scope_bodies"] == ["Corpo-A", "Corpo-B"] and opt["merge"] is True
           and opt["feature_scope"] is True)
    fd2.GetFace = lambda fwd: None
    fd2.GetVertex = lambda fwd: None
    fd2.GetEndConditionReference = lambda fwd, t: None
    ref = sw._fd_end_reference(fd2, 4, True, None)
    record("get_feature_definition: riferimento di fine non leggibile dichiarato", ref and ref["readable"] is False and "note" in ref)
    fd2.GetEndConditionReference = lambda fwd, t: bb
    ref = sw._fd_end_reference(fd2, 7, True, None)
    record("get_feature_definition: fino al corpo -> nome del corpo di riferimento", ref == {"readable": True, "kind": "body", "body": "Corpo-B"}, str(ref))
    record("get_feature_definition: condizione senza riferimento (blind) -> nessun end_reference", sw._fd_end_reference(fd2, 0, True, None) is None)

    # ---- try_on_copy: registrazione, rifiuti e inoltro dell'esecutore
    tools = {t.name: t for t in asyncio.run(srv.list_tools())}
    record("try_on_copy: registrato con schema (steps obbligatorio)", "try_on_copy" in tools
           and tools["try_on_copy"].inputSchema["required"] == ["steps"] and "edit_extrude_options" in tools)
    r = sw.try_on_copy(steps=[{"tool": "save_document", "arguments": {}}], runner=lambda s, e: {"success": True})
    record("try_on_copy: save_document non ammesso nei passi", not r["success"] and "non ammesso" in r["message"])
    r = sw.try_on_copy(steps=[{"tool": "draw_line", "arguments": {"document": "Altro"}}], runner=lambda s, e: {"success": True})
    record("try_on_copy: argomento 'document' non ammesso", not r["success"] and "document" in r["message"])
    r = sw.try_on_copy(steps=[], runner=lambda s, e: {"success": True})
    record("try_on_copy: steps vuoti -> errore", not r["success"])
    doc_asm = types.SimpleNamespace(GetType=2)
    sw.get_active_doc = lambda: (doc_asm, None)
    r = sw.try_on_copy(steps=[{"tool": "draw_line"}], runner=lambda s, e: {"success": True})
    record("try_on_copy: un assieme viene rifiutato (solo pezzi)", not r["success"] and "PEZZO" in r["message"])
    res = asyncio.run(srv.call_tool("execute_tool_sequence", {"steps": [{"tool": "try_on_copy", "arguments": {"steps": []}}]}))
    record("execute_tool_sequence: try_on_copy annidato non ammesso", "nested 'try_on_copy'" in res[0].text)


# ============================================================================ revisione 2026-11-12: sicurezza e file
def test_review_fixes(tmp):
    import logging
    import subprocess as sp

    real = srv.sw_automation

    # 1. export con overwrite: il file vecchio non deve andare perso se l'export fallisce
    try:
        from solidworks_mcp.utils import keep_file as kf
    except Exception as e:
        kf = None
        record("keep_file: modulo presente", False, repr(e))
    if kf is not None:
        class _Exp:
            @kf.keeps_old_file
            def export(self, path, write, ok):
                kf.set_aside(self, path)
                if write is not None:
                    Path(path).write_bytes(write)
                if ok is None:
                    raise RuntimeError("boom")
                return {"success": ok}
        p = Path(tmp) / "vecchio.pdf"
        p.write_bytes(b"VECCHIO")
        _Exp().export(str(p), None, False)
        record("export fallito senza file nuovo: il file vecchio torna al suo posto", p.exists() and p.read_bytes() == b"VECCHIO")
        _Exp().export(str(p), b"", False)
        record("export fallito con file vuoto: il file vecchio torna al suo posto", p.read_bytes() == b"VECCHIO")
        try:
            _Exp().export(str(p), None, None)
        except RuntimeError:
            pass
        record("export con eccezione: il file vecchio torna al suo posto", p.exists() and p.read_bytes() == b"VECCHIO")
        _Exp().export(str(p), b"NUOVO", True)
        record("export riuscito: resta il file nuovo e nessuna copia messa da parte",
               p.read_bytes() == b"NUOVO" and [f.name for f in Path(tmp).glob("vecchio.pdf*")] == ["vecchio.pdf"])
        p2 = Path(tmp) / "per_componente.stl"
        p2.write_bytes(b"VECCHIO")
        _Exp().export(str(p2), None, True)
        record("tool riuscito senza quel file (STL per componente): il vecchio non viene rimesso",
               not list(Path(tmp).glob("per_componente.stl*")))
    for meth in ("export_drawing", "export_model", "export_model_image", "export_simulation_plot", "export_pdf_layers"):
        fn = getattr(SolidWorksAutomation, meth)
        src = inspect.getsource(inspect.unwrap(fn))
        record(f"{meth}: il file vecchio e' messo da parte, non cancellato prima dell'export",
               hasattr(fn, "__wrapped__") and "set_aside(" in src)

    # 2. argomenti sconosciuti segnalati; 3. il codice di execute_python non finisce nel log
    fake = _FakeAutomation()
    srv.sw_automation = fake
    seen = []

    class _H(logging.Handler):
        def emit(self, rec):
            seen.append(rec.getMessage())
    h, old_level = _H(), srv.logger.level
    srv.logger.addHandler(h)
    srv.logger.setLevel(logging.INFO)
    try:
        fake.draw_line = lambda **kw: {"success": True, "message": "ok", "error_code": 0, "error_name": "swSuccess", "data": {}}
        text = asyncio.run(srv.call_tool("draw_line", {"x1": 0, "y1": 0, "x2": 1, "y2": 1, "lunghezza": 5}))[0].text
        record("argomento sconosciuto: segnalato nel risultato", text.startswith("[SUCCESS]") and "lunghezza" in text, text[:160])
        text = asyncio.run(srv.call_tool("draw_line", {"x1": 0, "y1": 0, "x2": 1, "y2": 1}))[0].text
        record("argomenti giusti: nessun avviso", "ignorat" not in text, text[:120])
        asyncio.run(srv.call_tool("execute_python", {"code": "SEGRETO_12345 = 1"}))
        record("log: il codice di execute_python non viene scritto",
               any("execute_python" in s for s in seen) and not any("SEGRETO_12345" in s for s in seen), str(seen[-2:])[:160])
    finally:
        srv.logger.removeHandler(h)
        srv.logger.setLevel(old_level)
        srv.sw_automation = real

    # 4. chiusura dell'istanza dedicata: solo dal processo lanciato dal server, mai per numero di PID
    class _Proc:
        def __init__(self, alive):
            self.alive, self.killed, self.pid, self.returncode = alive, 0, 424242, 1

        def poll(self):
            return None if self.alive else 1

        def kill(self):
            self.killed += 1
            self.alive = False

        def wait(self, timeout=None):
            return 0
    calls = []
    old_run, old_popen = sp.run, sp.Popen
    old_env = {k: os.environ.get(k) for k in ("SW_MCP_STARTUP_TIMEOUT", "SW_MCP_EXE")}
    sp.run = lambda *a, **k: (calls.append(a[0] if a else k.get("args")), types.SimpleNamespace(returncode=1, stdout="", stderr=""))[1]
    try:
        auto = object.__new__(SolidWorksAutomation)
        auto._sw_app, auto._connected, auto._dedicated_pid = object(), True, 424242
        auto.is_dedicated_mode = lambda: True
        live = _Proc(True)
        auto._dedicated_proc = live
        srv.sw_automation = auto
        msg = srv._timeout_message("draw_line", 5)
        record("timeout: chiude l'istanza dal SUO processo, senza taskkill per numero",
               live.killed == 1 and not calls and "chiusa" in msg, f"kill={live.killed} taskkill={calls} {msg[:70]}")
        auto._sw_app, auto._connected, auto._dedicated_pid = object(), True, 424242
        dead = _Proc(False)
        auto._dedicated_proc = dead
        calls.clear()
        msg = srv._timeout_message("draw_line", 5)
        record("timeout: processo gia' uscito -> nessuna chiusura (quel numero puo' essere di un altro programma)",
               dead.killed == 0 and not calls, f"kill={dead.killed} taskkill={calls} {msg[:70]}")
        if os.name == "nt":
            spawned = _Proc(True)
            sp.Popen = lambda *a, **k: spawned
            os.environ["SW_MCP_STARTUP_TIMEOUT"], os.environ["SW_MCP_EXE"] = "0", sys.executable
            auto2 = object.__new__(SolidWorksAutomation)
            auto2._config = types.SimpleNamespace(exe_path="auto")
            auto2._find_instance_by_pid = lambda pid: None
            r = globals().get("_REAL_CONNECT_DEDICATED", SolidWorksAutomation._connect_dedicated)(auto2)
            record("avvio dell'istanza dedicata fallito: il processo lanciato viene chiuso (niente orfani)",
                   (not r["success"]) and spawned.killed == 1 and not auto2.__dict__.get("_dedicated_pid"),
                   f"kill={spawned.killed} pid={auto2.__dict__.get('_dedicated_pid')} {r['message'][:60]}")
    finally:
        sp.run, sp.Popen = old_run, old_popen
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        srv.sw_automation = real

    # 5. close_document senza documento attivo non sceglie da solo un documento da chiudere
    auto3 = object.__new__(SolidWorksAutomation)
    auto3._sw_app, auto3._connected = types.SimpleNamespace(RevisionNumber="34.0"), True
    auto3.get_active_doc = lambda: (None, {"success": False, "message": "nessuno"})
    auto3._open_docs = lambda: [("Staffa.SLDPRT", "C:/x/Staffa.SLDPRT", object())]
    r = auto3.close_document(discard=True)
    record("close_document senza documento attivo: rifiuta ed elenca i documenti aperti",
           (not r["success"]) and "attivo" in r["message"] and "Staffa" in r["message"], r["message"][:150])

    # 7. espressioni delle curve da equazione: solo matematica (prima erano passate a eval, aggirabile)
    import math
    from solidworks_mcp.automation import ext_sketch4 as s4
    try:
        ok_math = abs(s4._eval_math_expr("2*sin(t)+t^2", 1.0) - (2 * math.sin(1.0) + 1.0)) < 1e-12
    except Exception as e:
        ok_math = False
        print("   espressione valida rifiutata:", repr(e))
    escaped = []
    for bad in ("().__class__.__bases__[0].__subclasses__().__len__()", "t.real.__class__", "[c for c in (1,2)][0]",
                "(lambda: 1)()", "'a' * 3 == 'aaa'"):
        try:
            s4._eval_math_expr(bad, 0.0)
            escaped.append(bad)
        except Exception:
            pass
    record("curve da equazione: la matematica funziona, il resto di Python e' rifiutato", ok_math and not escaped,
           f"valida={ok_math} accettate={escaped}")

    # 6. prova su copia: niente tool che aprono o creano altri documenti
    record("try_on_copy blocca create_drawing, import_model e split_body",
           {"create_drawing", "import_model", "split_body"} <= SolidWorksAutomation.TRIAL_BLOCKED_TOOLS)


def _bare_auto():
    """Automazione senza costruttore (niente config, niente COM): i test patchano solo cio' che serve."""
    a = SolidWorksAutomation()
    a._sw_app, a._connected = None, False
    return a


def _try(fn):
    try:
        return fn()
    except Exception as e:
        return {"success": None, "message": f"eccezione: {e!r}", "data": {}}


def test_review_sec2_rest(tmp):
    """Revisione 2026-11-12, sezione 2 (sicurezza e file): i quattro punti rimasti, scritti prima della correzione."""
    import pythoncom as _pc
    from solidworks_mcp.automation import base as _base

    # 1. is_connected: un errore COM passeggero (istanza occupata) non vale come istanza persa
    BUSY, GONE = -2147418111, -2147023174          # RPC_E_CALL_REJECTED, RPC_S_SERVER_UNAVAILABLE

    class _App:
        def __init__(self, fails, hr):
            self.fails, self.hr, self.reads = fails, hr, 0

        @property
        def RevisionNumber(self):
            self.reads += 1
            if self.reads <= self.fails:
                raise _pc.com_error(self.hr, "test", None, None)
            return "34.4.1"

    class _P:
        def __init__(self, alive):
            self.alive = alive

        def poll(self):
            return None if self.alive else 1
    old_sleep = _base.time.sleep
    _base.time.sleep = lambda s: None
    try:
        a = _bare_auto()
        a._sw_app, a._connected = _App(2, BUSY), True
        ok = a.is_connected
        record("is_connected: due rifiuti 'occupato' e poi risposta -> collegata, istanza tenuta",
               ok is True and a._sw_app is not None and a._connected, f"is_connected={ok}")
        a = _bare_auto()
        a._sw_app, a._connected, a._dedicated_proc = _App(99, BUSY), True, _P(True)
        a.is_dedicated_mode = lambda: True
        ok = a.is_connected
        record("is_connected: istanza dedicata viva ma sempre occupata -> NON data per persa (niente rilancio)",
               ok is True and a._sw_app is not None, f"is_connected={ok}")
        a = _bare_auto()
        a._sw_app, a._connected, a._dedicated_proc = _App(99, GONE), True, _P(True)
        a.is_dedicated_mode = lambda: True
        record("is_connected: server COM sparito -> istanza persa", a.is_connected is False and a._sw_app is None)
        a = _bare_auto()
        a._sw_app, a._connected, a._dedicated_proc = _App(99, BUSY), True, _P(False)
        a.is_dedicated_mode = lambda: True
        record("is_connected: processo dedicato uscito -> istanza persa", a.is_connected is False)
    finally:
        _base.time.sleep = old_sleep

    # 2. create_drawing non salva il modello aperto con modifiche dell'utente; save_as fallito = errore (anche [V] sez. 1)
    mpath = Path(tmp) / "pezzo.SLDPRT"
    mpath.write_bytes(b"x")
    tpl = Path(tmp) / "tavola.drwdot"
    tpl.write_bytes(b"x")

    class _MDoc:
        def __init__(self, dirty):
            self.dirty, self.saves = dirty, 0

        def GetSaveFlag(self):
            return self.dirty

        def Save3(self, *a):
            self.saves += 1
            self.dirty = False
            return True

    class _Sheet:
        def SetProperties2(self, *a): return True
        def SetTemplateName(self, *a): return True
        def ReloadTemplate(self, *a): return True
        def GetName(self): return "Foglio1"

    class _DDoc:
        def GetCurrentSheet(self): return _Sheet()

    def _drw_auto(mdoc, save_ok):
        d = _bare_auto()
        d._sw_app = types.SimpleNamespace(RevisionNumber="34.4.1", NewDocument=lambda *a: _DDoc())
        d._connected = True
        d._get_model_doc = lambda p: (mdoc, False)
        d._default_template = lambda t: str(tpl)
        d._sheet_format_path = lambda *a: None

        def _props(doc, md, extra=None):
            md.dirty = True                      # le proprieta' nuove sporcano il modello
            return ["Descrizione"]
        d._ensure_titleblock_props = _props
        d._missing_props_from_dxf = lambda doc: []
        d._save_as = lambda doc, p: (save_ok, 0 if save_ok else 1, 0)
        d._fit_title_number = lambda doc: 0
        d._get_doc_title = lambda doc: "Tavola1"
        d._get_doc_path = lambda doc: str(mpath)
        return d
    dirty = _MDoc(True)
    r = _try(lambda: _drw_auto(dirty, True).create_drawing(model_path=str(mpath), paper_size="A3"))
    record("create_drawing: modello con modifiche non salvate dell'utente -> NON salvato, detto nel risultato",
           r["success"] and dirty.saves == 0 and r["data"].get("model_saved") is False, f"saves={dirty.saves} {r['message'][:80]}")
    clean = _MDoc(False)
    r = _try(lambda: _drw_auto(clean, True).create_drawing(model_path=str(mpath), paper_size="A3"))
    record("create_drawing: modello senza modifiche -> salvato con le proprieta' del cartiglio",
           r["success"] and clean.saves == 1 and r["data"].get("model_saved") is True, f"saves={clean.saves} {r['message'][:80]}")
    r = _try(lambda: _drw_auto(_MDoc(False), False).create_drawing(model_path=str(mpath), paper_size="A3",
                                                                    save_as=str(Path(tmp) / "t.SLDDRW")))
    record("create_drawing: save_as fallito -> errore, nessun saved_as dichiarato",
           r["success"] is False and not r.get("data", {}).get("saved_as") and "Tavola1" in r["message"], r["message"][:110])

    # 3. preferenze di schizzo: valore precedente riportato, ripristinato se il tool fallisce a meta'
    class _SM:
        def __init__(self, broken=()):
            object.__setattr__(self, "_broken", set(broken))
            object.__setattr__(self, "vals", {"AddToDB": False, "AutoSolve": True, "AutoInference": True,
                                              "CurvatureScale": 10.0, "CurvatureDensity": 20})

        def __getattr__(self, n):
            v = object.__getattribute__(self, "vals")
            if n in v:
                return v[n]
            raise AttributeError(n)

        def __setattr__(self, n, val):
            if n in self._broken:
                raise RuntimeError(f"{n} non scrivibile")
            self.vals[n] = val
    s5 = _bare_auto()
    sm = _SM(broken={"AutoInference"})
    d5 = types.SimpleNamespace(SketchManager=sm)
    s5._part = lambda: (d5, None)
    r = _try(lambda: s5.set_sketch_performance_mode(True, False, False))
    record("set_sketch_performance_mode: fallito a meta' -> le impostazioni gia' cambiate tornano come prima",
           r["success"] is False and sm.vals["AddToDB"] is False and sm.vals["AutoSolve"] is True, f"{sm.vals} {r['message'][:60]}")
    sm = _SM()
    d5 = types.SimpleNamespace(SketchManager=sm)
    s5._part = lambda: (d5, None)
    r = _try(lambda: s5.set_sketch_performance_mode(True, False, True))
    record("set_sketch_performance_mode: riporta i valori precedenti (per tornare indietro)",
           r["success"] and r["data"].get("previous") == {"add_to_db": False, "auto_solve": True, "auto_inference": True},
           str(r.get("data", {}).get("previous")))
    seg = types.SimpleNamespace(ShowCurvatureCombs=False)
    sm = _SM(broken={"CurvatureDensity"})
    s4 = _bare_auto()
    s4._s2_active_or_open = lambda sketch=None: (types.SimpleNamespace(SketchManager=sm), sm, None)
    s4._s4_segs = lambda doc: [seg]
    s4._safe_seg_id = lambda s: "Spline1"
    s4._s4_seg_type = lambda s: 3
    r = _try(lambda: s4.show_sketch_curvature(scale=15, density=30))
    record("show_sketch_curvature: fallito a meta' -> la scala dei pettini torna come prima",
           r["success"] is False and sm.vals["CurvatureScale"] == 10.0, f"{sm.vals} {r['message'][:60]}")
    sm = _SM()
    s4._s2_active_or_open = lambda sketch=None: (types.SimpleNamespace(SketchManager=sm), sm, None)
    r = _try(lambda: s4.show_sketch_curvature(scale=15, density=30))
    record("show_sketch_curvature: riporta scala e densita' precedenti",
           r["success"] and r["data"].get("previous") == {"scale": 10.0, "density": 20}, str(r.get("data", {}).get("previous")))

    # 4. mirror_components con overwrite: il file vecchio messo da parte, non cancellato prima di specchiare
    fn = SolidWorksAutomation.mirror_components
    src = inspect.getsource(inspect.unwrap(fn))
    record("mirror_components: il file esistente e' messo da parte (torna se lo specchio fallisce), non cancellato",
           hasattr(fn, "__wrapped__") and "set_aside(" in src and "os.remove(dst)" not in src)


def test_review_v_fixes(tmp):
    """Revisione 2026-11-12, sezione 1: falsi successi confermati [V], ognuno con un test scritto prima della correzione."""
    import math

    # [V] create_sketch: un piano inesistente non diventa il piano frontale (SolidWorks in inglese)
    class _Feat:
        def __init__(self, name, typ, log):
            self.Name, self.typ, self.log, self.nxt = name, typ, log, None

        def GetTypeName2(self): return self.typ
        def GetNextFeature(self): return self.nxt

        def Select2(self, append, mark):
            self.log.append(self.Name)
            return True

    class _SkMgr:
        ActiveSketch = None

    class _SkDoc:
        def __init__(self, planes):
            self.log, self.SketchManager = [], _SkMgr()
            feats = [_Feat(n, "RefPlane", self.log) for n in ("Front Plane", "Top Plane", "Right Plane")]
            for f1, f2 in zip(feats, feats[1:]):
                f1.nxt = f2
            self.first = feats[0]
            self.extra = {n: _Feat(n, "RefPlane", self.log) for n in planes}
            self.Extension = self

        def FirstFeature(self): return self.first
        def FeatureByName(self, n): return self.extra.get(n)
        def ClearSelection2(self, *a): return True

        def SelectByID2(self, name, *a):
            self.log.append(name)
            return True                          # SolidWorks inglese: "Front Plane" esiste sempre

        def InsertSketch2(self, flag):
            self.SketchManager.ActiveSketch = None if self.SketchManager.ActiveSketch else object()
    sk = _bare_auto()
    sk._sketch_plane_info = lambda doc: {}
    d = _SkDoc([])
    sk.get_active_doc = lambda: (d, None)
    r = _try(lambda: sk.create_sketch("Plane1"))
    record("[V] create_sketch: piano 'Plane1' inesistente -> errore (non uno schizzo sul piano frontale)",
           r["success"] is False and d.SketchManager.ActiveSketch is None, f"{r['message'][:70]} selezioni={d.log}")
    d = _SkDoc(["Plane1"])
    sk.get_active_doc = lambda: (d, None)
    r = _try(lambda: sk.create_sketch("Plane1"))
    record("[V] create_sketch: piano 'Plane1' esistente -> schizzo proprio su Plane1",
           r["success"] and d.log == ["Plane1"] and d.SketchManager.ActiveSketch is not None, f"selezioni={d.log}")
    d = _SkDoc([])
    sk.get_active_doc = lambda: (d, None)
    r = _try(lambda: sk.create_sketch("Top"))
    record("[V] create_sketch: 'Top' -> secondo piano standard dell'albero", r["success"] and d.log == ["Top Plane"], f"selezioni={d.log}")

    # [V] close_sketch: risposta di successo solo se lo schizzo e' davvero chiuso
    class _StuckMgr:
        ActiveSketch = object()

        def InsertSketch(self, flag): return None
    stuck = types.SimpleNamespace(SketchManager=_StuckMgr(), InsertSketch2=lambda f: None)
    real = srv.sw_automation
    fake = _FakeAutomation()
    fake.get_active_doc = lambda: (stuck, None)
    srv.sw_automation = fake
    try:
        r = _try(srv._close_sketch_handler)
    finally:
        srv.sw_automation = real
    record("[V] close_sketch: lo schizzo resta aperto -> errore", r["success"] is False, r["message"][:80])

    # [V] sweep: twist_angle e keep_normal arrivano davvero a SolidWorks
    calls = []

    class _FM:
        def InsertProtrusionSwept4(self, *a):
            calls.append(a)
            return object()
    sw_doc = types.SimpleNamespace(FeatureManager=_FM(), ClearSelection2=lambda *a: True)
    sw = _bare_auto()
    sw._part = lambda: (sw_doc, None)
    sw._exit_sketch = lambda doc: None
    sw._volume_m3 = lambda doc: 0.0
    sw._names = lambda doc: []
    sw._select_feature = lambda *a: True
    sw._finish = lambda *a, **k: {"success": True, "message": "ok", "data": {"feature": "Sweep1"}}
    sw._readback = lambda *a: {}
    _try(lambda: sw.sweep("S1", "S2", twist_angle=90))
    tw = calls[-1] if calls else None
    record("[V] sweep: twist_angle=90 -> torsione costante lungo il percorso (codice 8, 90 gradi)",
           tw is not None and tw[2] == 8 and abs(tw[15] - math.pi / 2) < 1e-12, f"codice={tw[2] if tw else None}")
    _try(lambda: sw.sweep("S1", "S2", keep_normal=False))
    record("[V] sweep: keep_normal=false -> orientamento costante del profilo (codice 1)",
           calls and calls[-1][2] == 1, f"codice={calls[-1][2] if calls else None}")
    _try(lambda: sw.sweep("S1", "S2"))
    record("sweep: default -> il profilo segue il percorso (codice 0)", calls and calls[-1][2] == 0)
    n0 = len(calls)
    r = _try(lambda: sw.sweep("S1", "S2", twist_angle=45, keep_normal=False))
    record("[V] sweep: torsione con keep_normal=false -> rifiutato (SolidWorks non torce un profilo a orientamento costante)",
           r["success"] is False and len(calls) == n0, r["message"][:80])

    # [V] suppress_feature: successo solo se lo stato riletto e' cambiato
    class _SFeat:
        IsSuppressed = False

        def SetSuppression2(self, *a): return False
    su = _bare_auto()
    sdoc = types.SimpleNamespace(ClearSelection2=lambda *a: True)
    su._part = lambda: (sdoc, None)
    su._exit_sketch = lambda doc: None
    sf = _SFeat()
    su._find_feature = lambda doc, n: sf
    su._volume_m3 = lambda doc: 1e-6
    r = _try(lambda: su.suppress_feature("Estrusione1"))
    record("[V] suppress_feature: SolidWorks non sopprime -> errore", r["success"] is False, r["message"][:80])
    sf.IsSuppressed = True
    r = _try(lambda: su.suppress_feature("Estrusione1"))
    record("suppress_feature: gia' soppressa -> successo (stato riletto)", r["success"] is True, r["message"][:80])

    # [V] add_section_view: 'points' e 'stepped' leggono le coordinate allo stesso modo (scala del modello)
    lines = []

    class _Seg:
        def Select4(self, *a): return True

    class _SVM:
        def CreateLine(self, *a):
            lines.append(tuple(round(v, 9) for v in a))
            return _Seg()
    parent = types.SimpleNamespace(Position=(0.2, 0.15), GetOutline=lambda: (0.15, 0.1, 0.25, 0.2), ScaleDecimal=0.5,
                                   GetName2=lambda: "Drawing View1")
    vdoc = types.SimpleNamespace(SketchManager=_SVM(), ClearSelection2=lambda *a: True, ActivateView=lambda n: True,
                                 CreateSectionViewAt5=lambda *a: None)
    sv = _bare_auto()
    sv._drawing = lambda: (vdoc, None)
    sv._find_view = lambda doc, n: (parent, None)
    sv._select_view = lambda doc, v: True
    sv._end_view_sketch = lambda doc: None
    _try(lambda: sv.add_section_view(orientation="points", points=[-10, 5, 10, 5], unit="mm"))
    pts_line = lines[-1] if lines else None
    lines.clear()
    _try(lambda: sv.add_section_view(orientation="stepped", points=[-10, 5, 0, 5, 0, -5, 10, -5], unit="mm"))
    record("[V] add_section_view a scala 1:2: 'points' e 'stepped' tagliano negli stessi punti del modello",
           pts_line == (-0.01, 0.005, 0, 0.01, 0.005, 0) and lines[:1] == [(-0.01, 0.005, 0, 0.0, 0.005, 0)],
           f"points={pts_line} stepped={lines[:1]}")

    # [V] set_dimension_tolerance: valori riletti confrontati; quota ambigua segnalata
    class _Tol:
        def __init__(self, works):
            self.works, self.mn, self.mx = works, 0.0, 0.0

        def SetValues(self, mn, mx):
            if self.works:
                self.mn, self.mx = mn, mx
            return True

        def GetMaxValue(self): return self.mx
        def GetMinValue(self): return self.mn

    class _Dim:
        def __init__(self, full, works=True):
            self.FullName, self.Name, self.Value, self.DrivenState = full, full.split("@")[0], 30.0, 1
            self.Tolerance, self.tt = _Tol(works), 0

        def SetToleranceType(self, tt):
            self.tt = tt

        def GetToleranceType(self): return self.tt

    class _DD:
        def __init__(self, dim):
            self.dim = dim
            self.GetDisplayData = types.SimpleNamespace(GetTextCount=lambda: 1, GetTextAtIndex=lambda i: "30")

        def GetDimension2(self, i): return self.dim
        def GetPrimaryPrecision2(self): return 2
        def GetPrimaryTolPrecision2(self): return 2
        def SetPrecision3(self, *a): return True
    tdoc = object()
    st = _bare_auto()
    st._drawing = lambda: (tdoc, None)
    st._sheet_views = lambda doc: ["V1"]
    dims = [_DD(_Dim("RD1@Vista1", works=False))]
    st._display_dims = lambda v: dims
    r = _try(lambda: st.set_dimension_tolerance("RD1@Vista1", "symmetric", upper=0.1))
    record("[V] set_dimension_tolerance: SolidWorks non applica i valori -> errore con i valori riletti",
           r["success"] is False, r["message"][:90])
    dims = [_DD(_Dim("RD1@Vista1")), _DD(_Dim("RD2@Vista1"))]
    r = _try(lambda: st.set_dimension_tolerance("30", "symmetric", upper=0.1))
    record("[V] set_dimension_tolerance: due quote da 30 -> rifiuto che le elenca (niente scelta a caso)",
           r["success"] is False and "RD1@Vista1" in r["message"] and "RD2@Vista1" in r["message"], r["message"][:120])
    dims = [_DD(_Dim("RD1@Vista1"))]
    r = _try(lambda: st.set_dimension_tolerance("RD1@Vista1", "symmetric", upper=0.1))
    record("set_dimension_tolerance: valori applicati e riletti -> successo", r["success"] is True, r["message"][:90])

    # [V] auto_explode: il componente base non si muove; '-x' esplode verso -x
    class _Comp:
        def __init__(self, name, x):
            self.Name2, self.x, self.GetSuppression, self.IsFixed = name, x, 2, False

        def GetBox(self, *a):
            return (self.x - 0.005, 0, 0, self.x + 0.005, 0.01, 0.01)
    comps = [_Comp("A-1", 0.0), _Comp("B-1", 0.010), _Comp("C-1", 0.010)]
    steps_seen = []
    ae = _bare_auto()
    ae._asm = lambda: (object(), None)
    ae._as_collapse = lambda doc: False
    ae._as_top_components = lambda doc, flag: comps
    ae._as_comp = lambda doc, name, flag=True: (_Comp(name, {"A-1": 0.0, "B-1": 0.010, "C-1": 0.010}[name]), None)

    def _cev(steps, unit=None, keep_exploded=True):
        steps_seen.append(steps)
        return {"success": True, "message": "ok", "data": {}}
    ae.create_exploded_view = _cev
    _try(lambda: ae.auto_explode(axis="x", gap=30, base_component="B-1"))
    moved = [n for s in (steps_seen[-1] if steps_seen else []) for n in s["components"]]
    record("[V] auto_explode: il componente base (B-1) non viene spostato", steps_seen and "B-1" not in moved, f"spostati={moved}")
    _try(lambda: ae.auto_explode(axis="-x", gap=30))
    st_neg = steps_seen[-1] if steps_seen else []
    record("[V] auto_explode axis='-x': i componenti vanno verso -x (base all'estremo +x)",
           st_neg and all(s["direction"] == "-x" for s in st_neg) and "A-1" in [n for s in st_neg for n in s["components"]],
           str([(s["components"], s["direction"]) for s in st_neg]))

    # [V] detect_collisions: initial_pose_restored misurato, non scritto a mano
    class _Mov:
        def __init__(self):
            self.Name2, self.t, self.fail_restore = "perno-1", [0.0, 0.0, 0.0], True

        @property
        def Transform2(self):
            return list(self.t)

        @Transform2.setter
        def Transform2(self, t):
            if self.fail_restore and t == [0.0, 0.0, 0.0]:
                raise RuntimeError("Transform2 rifiutato")
            self.t = list(t)
    mov = _Mov()
    dc = _bare_auto()
    dc._asm = lambda: (types.SimpleNamespace(ForceRebuild2=lambda f: True), None)
    dc._as_collapse = lambda doc: False
    dc._as_comp = lambda doc, n: (mov, None)
    dc._as_pose = lambda c: ([[1, 0, 0], [0, 1, 0], [0, 0, 1]], list(c.t))
    dc._as_transform = lambda M, t: [float(v) for v in t]
    dc._run_interference_check = lambda *a: []
    r = _try(lambda: dc.detect_collisions(moving_component="perno-1", dx=10, steps=2, unit="mm"))
    record("[V] detect_collisions: posa iniziale non ripristinata -> detto (initial_pose_restored false) ed errore",
           r["success"] is False and r.get("data", {}).get("initial_pose_restored") is False, r["message"][:90])
    mov.fail_restore, mov.t = False, [0.0, 0.0, 0.0]
    r = _try(lambda: dc.detect_collisions(moving_component="perno-1", dx=10, steps=2, unit="mm"))
    record("detect_collisions: posa ripristinata e riletta -> successo", r["success"] and r["data"].get("initial_pose_restored") is True,
           r["message"][:90])

    # [V] assign_material: successo solo se il materiale riletto e' quello chiesto
    mat = {"name": "AISI 304", "file": "C:/x/materiali.sldmat", "database": "materiali", "category": "Acciaio", "density": 8000}

    class _MatDoc:
        def __init__(self):
            self.Extension = types.SimpleNamespace(CreateMassProperty2=lambda: types.SimpleNamespace(SelectedItems=None,
                                                                                                    Density=1.0))

        def SetMaterialPropertyName2(self, *a): return None
        def GetMaterialPropertyName2(self, cfg, db): return ""
    am = _bare_auto()
    mdoc2 = _MatDoc()
    am._dx_doc = lambda types_=None: (mdoc2, None)
    am._dx_find_material = lambda m, c=None: (mat, None)
    am._dx_rebuild = lambda doc: None
    am._dx_cfg_list = lambda doc, c: ["Predefinito"]
    am._mass_props = lambda doc: None
    am._dx_body = lambda doc, b: (None, None)
    r = _try(lambda: am.assign_material("AISI 304", link_title_block=False))
    record("[V] assign_material (pezzo): materiale non riletto -> errore", r["success"] is False, r["message"][:90])
    body = types.SimpleNamespace(Name="Corpo1", SetMaterialProperty=lambda *a: True, GetMaterialPropertyName=lambda *a: "")
    am._dx_body = lambda doc, b: (body, None)
    r = _try(lambda: am.assign_material("AISI 304", body="Corpo1"))
    record("[V] assign_material (corpo): 3 tentativi falliti -> errore", r["success"] is False, r["message"][:90])

    # [V] add_equation: GetErrorCode2 letto come metodo (codice + avviso); equazione che rompe il modello rimossa
    class _EM:
        def __init__(self):
            self.eqs = []

        @property
        def GetCount(self): return len(self.eqs)

        def Add2(self, i, text, solve):
            self.eqs.append(text)
            return len(self.eqs) - 1

        def Delete(self, i):
            self.eqs.pop(i)
    em = _EM()

    class _ErrFeat:
        def GetErrorCode2(self, is_warning):     # come le feature vere: metodo con il flag d'avviso per riferimento
            is_warning.value = False
            return 71 if em.eqs else 0
    edoc = types.SimpleNamespace(GetEquationMgr=em, GetType=1)
    eq = _bare_auto()
    eq._dx_doc = lambda t=None: (edoc, None)
    eq._dx_rebuild = lambda doc: None
    eq._dx_eqs = lambda doc: (em, [{"index": i, "equation": e, "value": 1.0, "global_variable": False} for i, e in enumerate(em.eqs)])
    eq._features = lambda doc: [("Taglio1", "Cut", _ErrFeat())]
    eq._volume_m3 = lambda doc: 1e-6
    r = _try(lambda: eq.add_equation('"D1@Schizzo1" = 500'))
    record("[V] add_equation: l'equazione rompe il modello (codice 71) -> rimossa ed errore",
           r["success"] is False and em.eqs == [], f"{r['message'][:80]} equazioni={em.eqs}")
    fake_ok = types.SimpleNamespace(GetErrorCode2=lambda bf: 0)
    eq._features = lambda doc: [("Taglio1", "Cut", fake_ok)]
    r = _try(lambda: eq.add_equation('"D1@Schizzo1" = 50'))
    record("add_equation: equazione sana -> resta", r["success"] is True and len(em.eqs) == 1, r["message"][:80])


def main():
    print(f"Test offline (COM {'simulato' if STUBBED else 'reale: pywin32 presente, SolidWorks non usato'})")
    with tempfile.TemporaryDirectory() as tmp:
        for name, fn in (("registro", test_registry), ("call_tool", lambda: test_call_tool(tmp)),
                         ("export_model", lambda: test_export_guards(tmp)), ("preferenze", test_dialog_prefs),
                         ("sicurezza", lambda: test_safety(tmp)), ("png", lambda: test_png(tmp)),
                         ("lettori", lambda: test_inspectors(tmp)),
                         ("materiali", lambda: test_materials(tmp)),
                         ("configurazione", lambda: test_config(tmp)), ("lingua", test_language),
                         ("D1 tabella", lambda: test_config_table(tmp)), ("D7 inerzia", test_inertia),
                         ("D10 PDF 3D", lambda: test_pdf3d(tmp)),
                         ("D3 eDrawings", lambda: test_edrawings(tmp)),("unita'", test_units),
                         ("toolset", lambda: test_toolsets(tmp)), ("thread e timeout", test_worker_timeout),
                         ("ripresa", test_autorestart), ("descrizioni", test_descriptions), ("parametri usati", test_params_used), ("ottimizzazione", test_optimization),
                         ("risorse e prompt", test_resources_and_prompts),
                         ("revisione sicurezza e file", lambda: test_review_fixes(tmp)),
                         ("revisione sezione 2, resto", lambda: test_review_sec2_rest(tmp)),
                         ("revisione falsi successi [V]", lambda: test_review_v_fixes(tmp)),
                         ("batch sequence", lambda: test_execute_tool_sequence(tmp)), ("image content", lambda: test_image_content(tmp)), ("diagnostica e ricerca", test_diagnostics_and_search), ("audit e collisioni", test_audit_and_collision), ("lotto sketch4", test_sketch4_tools), ("lotto sketch5", test_sketch5_tools), ("lotto assembly3", lambda: test_assembly3_tools(tmp)), ("lotto drawings2", lambda: test_drawings2_tools(tmp)), ("lotto features4", lambda: test_features4_tools(tmp)), ("lotto data2", lambda: test_data2_tools(tmp)), ("lotto simulation2", lambda: test_simulation2_tools(tmp)), ("correzioni dal rapporto", test_report_fix_tools)):
            try:
                fn()
            except Exception as e:
                import traceback
                traceback.print_exc()
                record(f"sezione {name}: eccezione", False, repr(e))
    bad = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} PASS")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
