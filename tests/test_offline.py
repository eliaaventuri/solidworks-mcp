"""
Test OFFLINE: girano senza SolidWorks e senza Windows (pywin32 assente -> moduli COM finti).

Coprono solo cio' che non tocca l'API di SolidWorks:
  - registro dei tool: 202 tool, nomi unici, ogni tool smistato (elif in server.py o *_DISPATCH), ogni metodo esistente,
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
from solidworks_mcp import safety                                      # noqa: E402
from solidworks_mcp.utils.units import UnitConverter                   # noqa: E402

RESULTS = []
EXPECTED_TOOLS = 201                       # 202 meno execute_python, disattivato di default (SW_MCP_ALLOW_PYTHON)
for _var in ("SW_MCP_ALLOW_PYTHON", "SW_MCP_TOOLSETS"):
    os.environ.pop(_var, None)             # i test partono dal default: tutto attivo tranne execute_python


def record(name, ok, note=""):
    RESULTS.append((name, bool(ok), note))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {note}" if note else ""))


# ============================================================================ registro dei tool
def test_registry():
    # con execute_python attivo: il registro completo (202) va controllato anche per il suo smistamento
    os.environ["SW_MCP_ALLOW_PYTHON"] = "1"
    try:
        _test_registry_full(EXPECTED_TOOLS + 1)
    finally:
        os.environ.pop("SW_MCP_ALLOW_PYTHON", None)


def _test_registry_full(expected):
    tools = asyncio.run(srv.list_tools())
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
        lost = props - allowed - {"overwrite"}             # overwrite e' consumato dalla guardia in server.py
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
    bad = parse_configuration_table("Configurazione,D1@Schizzo1,$STATO@Foro1,Lunghezza\nA,dieci,forse,1\nA,1,S,2\n,3,S,4\n")
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
        record(f"lingua: _select_std_plane('Piano frontale') seleziona il 1° piano ({lang})",
               sw._select_std_plane(doc, "Piano frontale") and feats[2].selected)


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
        record("execute_python nascosto di default", "execute_python" not in names and len(names) == EXPECTED_TOOLS)
        text, calls = call("execute_python", {"code": "print(1)"})
        record("execute_python rifiutato di default, nessun codice eseguito",
               text.startswith("[ERROR]") and "SW_MCP_ALLOW_PYTHON" in text and not calls, text[:80])

        os.environ["SW_MCP_ALLOW_PYTHON"] = "1"
        try:
            record("SW_MCP_ALLOW_PYTHON=1 riattiva execute_python", "execute_python" in _names() and len(_names()) == EXPECTED_TOOLS + 1)
        finally:
            os.environ.pop("SW_MCP_ALLOW_PYTHON", None)

        os.environ["SW_MCP_TOOLSETS"] = "base,drawings"
        try:
            names = _names()
            groups_ok = all(n in names for n in srv.BASE_DISPATCH) and all(n in names for n in srv.DRAWING_DISPATCH)
            none_other = not (set(srv.MODELING_DISPATCH) | set(srv.DATA_DISPATCH)) & names
            record("SW_MCP_TOOLSETS=base,drawings: solo base e disegni esposti", groups_ok and none_other,
                   f"{len(names)} tool")
            text, calls = call("create_sketch", {"plane": "Front"})
            record("tool base attivo con il gruppo scelto", not text.startswith("[ERROR]") or "gruppo" not in text, text[:60])
            mod = next(n for n in srv.MODELING_DISPATCH)
            text, calls = call(mod, {})
            record("tool di un gruppo non scelto: errore che nomina il gruppo, nessuna chiamata",
                   text.startswith("[ERROR]") and "'modeling'" in text and not calls, text[:120])
            text, calls = call("tool_inesistente", {})
            record("tool sconosciuto con gruppi limitati -> 'Unknown tool'", "Unknown tool" in text, text[:60])
        finally:
            os.environ.pop("SW_MCP_TOOLSETS", None)

        os.environ["SW_MCP_TOOLSETS"] = "bogus"
        try:
            base = (set(srv.BASE_DISPATCH) | set(srv.SPECIAL_HANDLERS)) - {"execute_python"}
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
                         ("ripresa", test_autorestart), ("descrizioni", test_descriptions)):
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
