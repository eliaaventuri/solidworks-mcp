"""
Test live del lotto MOKA1 (estensioni di 5 tool esistenti) tramite il server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente non viene mai
toccata; alla fine si chiude solo il PID lanciato dal test.

  M1  create_reference_plane: mid_plane, line_point, normal_to_curve, parallel_point (normali e origini misurate)
  M2  revolve_boss / revolve_cut con asse di riferimento, spigolo del modello, linea di un altro schizzo (teorema di Pappo)
  M3  add_sketch_relation verso entita' esterne: pierce (spigolo, curva di un altro schizzo), coincident, parallel,
      perpendicular, collinear, tangent, equal, concentric
  M4  extrude_boss / extrude_cut con start_from (offset, surface, vertex): volumi calcolati
  M5  list_entities: tipo e parametri di facce (piano, cilindro, cono, sfera, toro) e spigoli (retta, cerchio)

Uso:  .venv\\Scripts\\python.exe tests\\test_ext_moka1_live.py [M1 M2 ...]
"""

import os
import sys
import math
import asyncio
import subprocess
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, PYTHON, SERVER, sw_pids, Client
PI = math.pi
TOL = 0.005          # 0,5 %

RESULTS = []         # (tool, PASS/FAIL, nota)


def record(tool, ok, note=""):
    RESULTS.append((tool, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {tool}  {note}"[:230])


def rel(got, exp):
    return abs(got - exp) / abs(exp) if exp else abs(got)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def sub(a, b):
    return [x - y for x, y in zip(a, b)]


def norm(a):
    return math.sqrt(dot(a, a))


def add(a, b):
    return [x + y for x, y in zip(a, b)]


def mul(a, k):
    return [x * k for x in a]


def r4(v):
    return [round(x, 4) for x in v]


async def need(c, tool, label, **args):
    """Chiama un tool, registra PASS/FAIL e restituisce i dati (vuoti se fallito)."""
    ok, text, d = await c.call(tool, **args)
    record(label, ok, text.split("\n")[0][:150])
    return d if ok else {}


async def vol(c):
    ok, _, d = await c.call("get_mass_properties")
    return d.get("volume_mm3", 0.0) if ok else 0.0


async def new_part(c):
    ok, text, _ = await c.call("create_new_part")
    assert ok, text


async def discard_all(c):
    for _ in range(40):
        ok, _, d = await c.call("list_open_documents")
        docs = d.get("documents", []) if ok else []
        if not docs:
            return
        await c.call("close_document", discard=True, document=docs[0]["title"])


async def block(c):
    """Blocco x 0..20, y 0..40, z 0..30 (rettangolo 40x30 sul piano frontale, estruso 20)."""
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=0, x2=40, y2=30)
    await c.call("close_sketch")
    await c.call("extrude_boss", depth=20)


async def plane_info(c, sketch=None):
    args = {"sketch": sketch} if sketch else {}
    ok, _, d = await c.call("get_sketch_plane_info", **args)
    return d if ok else {}


def to_uv(P, info):
    o = info["sketch_origin_mm"]
    return [dot(sub(P, o), info["sketch_x_axis"]), dot(sub(P, o), info["sketch_y_axis"])]


def to_model(uv, info):
    return add(add(info["sketch_origin_mm"], mul(info["sketch_x_axis"], uv[0])), mul(info["sketch_y_axis"], uv[1]))


# ===================================================================================================== run
async def run():
    elia_pids = sw_pids()
    print(f"Istanze SolidWorks gia' presenti (da non toccare): {sorted(elia_pids)}")
    env = dict(os.environ)
    env["SW_MCP_INSTANCE"] = "dedicated"
    params = StdioServerParameters(command=str(PYTHON), args=[str(SERVER)], env=env, cwd=str(ROOT))
    my_pid = None
    try:
        async with stdio_client(params) as (rd, wr):
            async with ClientSession(rd, wr, read_timeout_seconds=timedelta(seconds=600)) as session:
                await session.initialize()
                c = Client(session, auto_overwrite=False)
                ok, text, data = await c.call("connect_solidworks")
                my_pid = data.get("pid")
                print(text[:200])
                if not ok or not my_pid or my_pid in elia_pids or my_pid not in sw_pids():
                    print("STOP: nessuna istanza separata ottenibile. Nulla e' stato toccato.")
                    return False
                print(f"Istanza dedicata PID {my_pid} (diversa da {sorted(elia_pids)})")
                record("PID dedicato diverso dall'istanza utente", my_pid not in elia_pids, str(my_pid))
                await scenario(c)
    finally:
        cleanup(my_pid, elia_pids)
    return True


def cleanup(my_pid, elia_pids):
    if my_pid and my_pid in sw_pids():
        subprocess.run(["taskkill", "/PID", str(my_pid), "/F"], capture_output=True)
    import time
    for _ in range(15):
        time.sleep(1)
        if my_pid not in sw_pids():
            break
    left = sw_pids() - elia_pids
    mine = [p for p in left if p == my_pid]
    record("il PID lanciato dal test e' chiuso", not mine,
           f"altri processi non nostri {sorted(left)}")


async def scenario(c):
    only = {a.upper() for a in sys.argv[1:]}
    sezioni = [("M1", m1_piani), ("M2", m2_rivoluzioni), ("M3", m3_relazioni), ("M4", m4_partenza), ("M5", m5_entita)]
    for nome, fn in sezioni:
        if not only or nome in only:
            try:
                await fn(c)
            except Exception as e:           # un errore di una sezione non ferma le altre
                record(f"{nome}: eccezione", False, repr(e)[:180])
    await discard_all(c)


# ===================================================================================================== M1
async def m1_piani(c):
    print("\n== M1. Piani di riferimento: mid_plane, line_point, normal_to_curve, parallel_point")
    await block(c)                                    # x 0..20, y 0..40, z 0..30

    def dist(P, d):
        return dot(sub(P, d["plane_origin"]), d["plane_normal"])

    cases = [("x=0 e x=20", [{"face": [0, 20, 15]}, {"face": [20, 20, 15]}], 0, 10.0),
             ("y=40 e y=0", [{"face": [10, 40, 15]}, {"face": [10, 0, 15]}], 1, 20.0),
             ("z=0 e z=30", [{"face": [10, 20, 0]}, {"face": [10, 20, 30]}], 2, 15.0)]
    for lab, refs, ax, pos in cases:
        d = await need(c, "create_reference_plane", f"M1 mid_plane fra le facce {lab}", mode="mid_plane", refs=refs)
        if d:
            n, o = d["plane_normal"], d["plane_origin"]
            record(f"M1 mid_plane {lab}: normale lungo l'asse {'xyz'[ax]} e origine a {pos}",
                   abs(abs(n[ax]) - 1) < 1e-5 and abs(o[ax] - pos) < 1e-3,
                   f"normale {r4(n)}, origine {r4(o)}, atteso {'xyz'[ax]}={pos}")
    pl = (await need(c, "create_reference_plane", "M1 piano offset 30 dal piano frontale", mode="offset", base="front",
                     distance=30)).get("feature", "Piano1")
    d = await need(c, "create_reference_plane", "M1 mid_plane fra il piano frontale e il piano a 30", mode="mid_plane",
                   refs=["front", pl])
    if d:
        record("M1 mid_plane fra due piani: x=15", abs(d["plane_normal"][0]) > 0.99999 and abs(d["plane_origin"][0] - 15) < 1e-3,
               f"normale {r4(d['plane_normal'])}, origine {r4(d['plane_origin'])}")
        record("M1 mid_plane: riporta distanza fra i riferimenti (30) e offset (15)",
               abs(d.get("between_refs", 0) - 30) < 1e-3 and abs(d.get("offset_each", 0) - 15) < 1e-3,
               f"{d.get('between_refs')}, {d.get('offset_each')}")
    ok, text, _ = await c.call("create_reference_plane", mode="mid_plane", refs=[{"face": [0, 20, 15]}, {"face": [10, 0, 15]}])
    record("M1 mid_plane fra facce NON parallele: rifiutato", not ok, text.split("\n")[0][:120])
    ok, text, _ = await c.call("create_reference_plane", mode="mid_plane", refs=[{"face": [0, 20, 15]}])
    record("M1 mid_plane con un solo riferimento: rifiutato", not ok, text.split("\n")[0][:120])

    # linea + punto: spigolo lungo y (x=0,z=0) e vertice (20,0,30)
    E, V = [0, 20, 0], [20, 0, 30]
    d = await need(c, "create_reference_plane", "M1 line_point: spigolo y (x=0,z=0) + vertice (20,0,30)", mode="line_point",
                   line={"edge": E}, point={"vertex": V})
    if d:
        n = d["plane_normal"]
        n_exp = [30 / math.hypot(30, 20), 0, -20 / math.hypot(30, 20)]
        parallel = abs(abs(dot(n, n_exp)) - 1) < 1e-4
        record("M1 line_point: normale = (30,0,-20)/|..| (a meno del segno)", parallel, f"normale {r4(n)}, attesa {r4(n_exp)}")
        record("M1 line_point: il piano contiene il vertice e lo spigolo", abs(dist(V, d)) < 1e-3 and abs(dist(E, d)) < 1e-3 and
               abs(n[1]) < 1e-4, f"distanze vertice {dist(V, d):+.5f}, spigolo {dist(E, d):+.5f}")
    # linea + punto con un asse di riferimento
    ax = (await need(c, "create_reference_axis", "M1 asse X (piano superiore + piano destro)", mode="two_planes",
                     planes=["top", "right"])).get("feature", "Assi1")
    d = await need(c, "create_reference_plane", "M1 line_point: asse X + vertice (20,40,30)", mode="line_point",
                   line={"axis": ax}, point={"vertex": [20, 40, 30]})
    if d:
        n = d["plane_normal"]
        n_exp = [0, 30 / 50, -40 / 50]
        record("M1 line_point con asse: normale perp. X e contiene il vertice",
               abs(n[0]) < 1e-4 and abs(abs(dot(n, n_exp)) - 1) < 1e-4 and abs(dist([20, 40, 30], d)) < 1e-3,
               f"normale {r4(n)}, attesa {r4(n_exp)}")
    # normale alla curva
    d = await need(c, "create_reference_plane", "M1 normal_to_curve: spigolo y + vertice (0,40,0)", mode="normal_to_curve",
                   line={"edge": E}, point={"vertex": [0, 40, 0]})
    if d:
        record("M1 normal_to_curve: normale = ±Y e origine sul vertice (y=40)",
               abs(abs(d["plane_normal"][1]) - 1) < 1e-5 and abs(d["plane_origin"][1] - 40) < 1e-3 and
               abs(d["plane_origin"][0]) < 1e-3 and abs(d["plane_origin"][2]) < 1e-3,
               f"normale {r4(d['plane_normal'])}, origine {r4(d['plane_origin'])}")
    d = await need(c, "create_reference_plane", "M1 normal_to_curve: spigolo z (x=20,y=40) + vertice (20,40,0)",
                   mode="normal_to_curve", line={"edge": [20, 40, 15]}, point={"vertex": [20, 40, 0]})
    if d:
        record("M1 normal_to_curve (spigolo z): normale = ±Z e z=0",
               abs(abs(d["plane_normal"][2]) - 1) < 1e-5 and abs(d["plane_origin"][2]) < 1e-3,
               f"normale {r4(d['plane_normal'])}, origine {r4(d['plane_origin'])}")
    # parallelo per un punto
    d = await need(c, "create_reference_plane", "M1 parallel_point: faccia x=0 + vertice (20,40,30)", mode="parallel_point",
                   base={"face": [0, 20, 15]}, point={"vertex": [20, 40, 30]})
    if d:
        record("M1 parallel_point: normale = ±X e il piano passa per il vertice (x=20)",
               abs(abs(d["plane_normal"][0]) - 1) < 1e-5 and abs(dist([20, 40, 30], d)) < 1e-3,
               f"normale {r4(d['plane_normal'])}, distanza vertice {dist([20, 40, 30], d):+.5f}")
    d = await need(c, "create_reference_plane", "M1 parallel_point: piano superiore + vertice (0,40,30)", mode="parallel_point",
                   base="top", point={"vertex": [0, 40, 30]})
    if d:
        record("M1 parallel_point (piano di riferimento): normale = ±Z e z=30",
               abs(abs(d["plane_normal"][2]) - 1) < 1e-5 and abs(dist([0, 40, 30], d)) < 1e-3,
               f"normale {r4(d['plane_normal'])}, origine {r4(d['plane_origin'])}")
    ok, text, _ = await c.call("create_reference_plane", mode="parallel_point", base={"face": [0, 20, 15]})
    record("M1 parallel_point senza punto: rifiutato", not ok, text.split("\n")[0][:120])
    # i modi vecchi restano
    d = await need(c, "create_reference_plane", "M1 offset invariato: 7 dalla faccia z=30", mode="offset",
                   base={"face": [10, 20, 30]}, distance=7)
    if d:
        record("M1 offset invariato: z=37", abs(d["plane_origin"][2] - 37) < 1e-3, f"origine {r4(d['plane_origin'])}")


# ===================================================================================================== M2
async def m2_rivoluzioni(c):
    print("\n== M2. Rivoluzione attorno a un asse esterno allo schizzo (Pappo: V = 2*pi*r_baricentro*A)")
    V_RING = 2 * PI * 10 * 100         # rettangolo 10x10 con baricentro a 10 mm dall'asse
    # a) boss attorno a un asse di riferimento
    await new_part(c)
    ax = (await need(c, "create_reference_axis", "M2 asse di riferimento Y (piano superiore + frontale)", mode="two_planes",
                     planes=["top", "front"])).get("feature", "Assi1")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=20, y1=5, x2=30, y2=15)      # y 20..30, z 5..15: distanza dall'asse Y = z
    d = await need(c, "revolve_boss", "M2 revolve_boss attorno all'asse di riferimento (nome)", axis=ax, angle=360)
    v = d.get("volume_mm3", 0)
    record("M2 revolve_boss asse di riferimento: volume = Pappo", rel(v, V_RING) < TOL,
           f"misurato {v:.3f} mm3, atteso {V_RING:.3f}, scarto {rel(v, V_RING) * 100:.4f} %; axis_kind {d.get('axis_kind')}")
    # a2) lo stesso con {"axis": nome}
    await new_part(c)
    ax = (await need(c, "create_reference_axis", "M2 asse di riferimento Y", mode="two_planes",
                     planes=["top", "front"])).get("feature", "Assi1")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=20, y1=5, x2=30, y2=15)
    d = await need(c, "revolve_boss", "M2 revolve_boss con axis={'axis': nome}", axis={"axis": ax}, angle=360)
    v = d.get("volume_mm3", 0)
    record("M2 revolve_boss axis={'axis':nome}: volume = Pappo", rel(v, V_RING) < TOL,
           f"misurato {v:.3f}, atteso {V_RING:.3f}, scarto {rel(v, V_RING) * 100:.4f} %")
    # a3) mezzo giro: Pappo con angolo
    await new_part(c)
    ax = (await need(c, "create_reference_axis", "M2 asse di riferimento Y", mode="two_planes",
                     planes=["top", "front"])).get("feature", "Assi1")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=20, y1=5, x2=30, y2=15)
    d = await need(c, "revolve_boss", "M2 revolve_boss 90 gradi attorno all'asse di riferimento", axis=ax, angle=90)
    v = d.get("volume_mm3", 0)
    record("M2 revolve_boss 90 gradi: volume = Pappo/4", rel(v, V_RING / 4) < TOL,
           f"misurato {v:.3f}, atteso {V_RING / 4:.3f}, scarto {rel(v, V_RING / 4) * 100:.4f} %")
    # b) taglio attorno a un asse di riferimento, blocco x -20..20, y 0..60, z -20..20 (V=96000)
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=-20, x2=60, y2=20)
    await c.call("close_sketch")
    await c.call("extrude_boss", depth=40, end_condition="mid_plane")
    v0 = await vol(c)
    ax = (await need(c, "create_reference_axis", "M2 asse di riferimento Y", mode="two_planes",
                     planes=["top", "front"])).get("feature", "Assi1")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=20, y1=5, x2=30, y2=15)
    d = await need(c, "revolve_cut", "M2 revolve_cut attorno all'asse di riferimento", axis=ax, angle=360)
    v1 = await vol(c)
    record("M2 revolve_cut asse di riferimento: volume asportato = Pappo", rel(v0 - v1, V_RING) < TOL,
           f"blocco {v0:.1f} -> {v1:.1f}: asportato {v0 - v1:.3f}, atteso {V_RING:.3f}, scarto {rel(v0 - v1, V_RING) * 100:.4f} %")
    # c) taglio attorno a uno spigolo del modello: blocco y 0..60, z 0..30, x 0..40; spigolo y (x=0,z=0) -> un quarto di anello
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=0, x2=60, y2=30)
    await c.call("close_sketch")
    await c.call("extrude_boss", depth=40)
    v0 = await vol(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=20, y1=5, x2=30, y2=15)
    d = await need(c, "revolve_cut", "M2 revolve_cut attorno a uno spigolo del modello {'edge'}", axis={"edge": [0, 30, 0]}, angle=360)
    v1 = await vol(c)
    record("M2 revolve_cut spigolo: asportato = Pappo/4 (un quarto d'anello dentro il blocco)",
           rel(v0 - v1, V_RING / 4) < TOL,
           f"asportato {v0 - v1:.3f}, atteso {V_RING / 4:.3f}, scarto {rel(v0 - v1, V_RING / 4) * 100:.4f} %; axis_kind {d.get('axis_kind')}")
    # d) boss attorno a una linea di un ALTRO schizzo
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    ok, _, dl = await c.call("draw_line", x1=0, y1=0, x2=60, y2=0)
    lid = dl.get("entity_id", "S0-0-1")
    await c.call("close_sketch")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=20, y1=5, x2=30, y2=15)
    d = await need(c, "revolve_boss", "M2 revolve_boss attorno alla linea di un altro schizzo", axis={"sketch": "Schizzo1", "entity": lid},
                   angle=360)
    v = d.get("volume_mm3", 0)
    record("M2 revolve_boss asse = linea di un altro schizzo: volume = Pappo", rel(v, V_RING) < TOL,
           f"misurato {v:.3f}, atteso {V_RING:.3f}, scarto {rel(v, V_RING) * 100:.4f} %; axis_kind {d.get('axis_kind')}")
    # e) comportamento invariato: asse = linea di costruzione dello schizzo e id di un segmento
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=20, y1=5, x2=30, y2=15)
    await c.call("draw_centerline_axis", x1=0, y1=0, x2=60, y2=0)
    d = await need(c, "revolve_boss", "M2 revolve_boss invariato (linea d'asse nello schizzo)")
    record("M2 invariato: volume = Pappo", rel(d.get("volume_mm3", 0), V_RING) < TOL, f"{d.get('volume_mm3')}")
    ok, text, _ = await c.call("revolve_boss", sketch="Schizzo1", axis="Asse inesistente")
    record("M2 axis inesistente: errore chiaro", not ok, text.split("\n")[0][:140])


# ===================================================================================================== M3
async def m3_relazioni(c):
    print("\n== M3. Relazioni di schizzo verso entita' esterne")
    # ---- a) pierce verso la linea di un altro schizzo
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    ok, _, dl = await c.call("draw_line", x1=10, y1=5, x2=50, y2=35)
    lid = dl.get("entity_id", "S0-0-1")
    info1 = await plane_info(c)
    await c.call("close_sketch")
    A_ = to_model([10, 5], info1)
    B_ = to_model([50, 35], info1)
    pl = await need(c, "create_reference_plane", "M3 piano offset -15 dal piano frontale", mode="offset", base="front",
                    distance=15, flip=True)
    on, nn = pl["plane_origin"], pl["plane_normal"]
    t = dot(sub(on, A_), nn) / dot(sub(B_, A_), nn)
    P = add(A_, mul(sub(B_, A_), t))
    await c.call("create_sketch", plane=pl["feature"])
    info2 = await plane_info(c)
    uv_exp = to_uv(P, info2)
    await c.call("draw_point", x=5, y=5)
    d = await need(c, "add_sketch_relation", "M3 pierce: punto dello schizzo attivo fora la linea di un altro schizzo",
                   relation="pierce", entity1="pt@5,5", entity2={"sketch": "Schizzo1", "entity": lid})
    if d:
        pt = d["points"][0]
        err = math.hypot(pt["x"] - uv_exp[0], pt["y"] - uv_exp[1])
        record("M3 pierce (altro schizzo): coordinate del punto = punto di foratura calcolato (< 0,001 mm)", err < 1e-3,
               f"punto ({pt['x']:.5f}, {pt['y']:.5f}), atteso ({uv_exp[0]:.5f}, {uv_exp[1]:.5f}), scarto {err:.6f} mm; "
               f"metodo {d.get('pierce_method')}")
        ok, _, ls = await c.call("list_sketch_entities")
        pts = [p["mm"] for p in ls.get("points", [])]
        err2 = min([math.hypot(p[0] - uv_exp[0], p[1] - uv_exp[1]) for p in pts] or [1e9])
        record("M3 pierce: rilettura indipendente (list_sketch_entities)", err2 < 1e-3, f"scarto minimo {err2:.6f} mm su {len(pts)} punti")
        ok, _, lr = await c.call("list_sketch_relations")
        types = [r["type"] for r in lr.get("relations", [])]
        record("M3 pierce: list_sketch_relations mostra una relazione sulla curva esterna", len(types) >= 1, str(types))
    # coincident con un punto di un altro schizzo (estremo A della linea)
    await c.call("draw_point", x=40, y=40)
    d = await need(c, "add_sketch_relation", "M3 coincident: punto + punto di un altro schizzo (estremo iniziale della linea)",
                   relation="coincident", entity1="pt@40,40", entity2={"sketch": "Schizzo1", "entity": "P0-1"})
    if d:
        uv = to_uv(A_, info2)
        pt = d["points"][0]
        err = math.hypot(pt["x"] - uv[0], pt["y"] - uv[1])
        record("M3 coincident con punto di altro schizzo: coordinate = proiezione dell'estremo (< 0,001 mm)", err < 1e-3,
               f"punto ({pt['x']:.5f}, {pt['y']:.5f}), atteso ({uv[0]:.5f}, {uv[1]:.5f})")
    # pierce verso un cerchio di un altro schizzo
    await c.call("close_sketch")
    await c.call("create_sketch", plane="Top")
    ok, _, dc = await c.call("draw_circle", x=60, y=20, radius=10)
    cid = dc.get("entity_id", "S1-0-1")
    await c.call("close_sketch")
    await c.call("create_sketch", plane=pl["feature"])
    await c.call("draw_point", x=55, y=0)
    d = await need(c, "add_sketch_relation", "M3 pierce: punto fora un cerchio di un altro schizzo", relation="pierce",
                   entity1="pt@55,0", entity2={"sketch": "Schizzo3", "entity": cid})
    if d:
        # cerchio: centro (u=60,v=20) di Top -> modello; il piano x=-15 lo taglia in due punti; il punto va al piu' vicino (u=55)
        cen = to_model([60, 20], info1)
        dx = on[0] - cen[0]
        half = math.sqrt(100 - dx * dx)
        cands = [to_uv([on[0], cen[1] - half, 0], info2), to_uv([on[0], cen[1] + half, 0], info2)]
        pt = d["points"][0]
        err = min(math.hypot(pt["x"] - q[0], pt["y"] - q[1]) for q in cands)
        record("M3 pierce (cerchio): punto sull'intersezione cerchio/piano (< 0,001 mm)", err < 1e-3,
               f"punto ({pt['x']:.5f}, {pt['y']:.5f}), candidati {[r4(q) for q in cands]}")
    await c.call("close_sketch")

    # ---- b) pierce NATIVO verso uno spigolo del modello, coincident con un vertice
    await block(c)                                    # x 0..20, y 0..40, z 0..30
    pl = await need(c, "create_reference_plane", "M3 piano offset 10 dal piano destro (y=10)", mode="offset", base="right",
                    distance=10)
    await c.call("create_sketch", plane=pl["feature"])
    info = await plane_info(c)
    await c.call("draw_point", x=3, y=3)
    await c.call("draw_point", x=-7, y=9)
    P = [20, pl["plane_origin"][1], 0]                # spigolo y: x=20, z=0
    uv = to_uv(P, info)
    d = await need(c, "add_sketch_relation", "M3 pierce nativo: punto fora lo spigolo del modello (x=20,z=0)", relation="pierce",
                   entity1="pt@3,3", entity2={"edge": [20, 20, 0]})
    if d:
        pt = d["points"][0]
        err = math.hypot(pt["x"] - uv[0], pt["y"] - uv[1])
        record("M3 pierce (spigolo): coordinate = punto di foratura (< 0,001 mm), relazione nativa", err < 1e-3 and not d.get("pierce_method"),
               f"punto ({pt['x']:.5f}, {pt['y']:.5f}), atteso ({uv[0]:.5f}, {uv[1]:.5f}); relazioni aggiunte {d.get('relations_added')}")
        ok, _, lr = await c.call("list_sketch_relations")
        record("M3 pierce nativo: list_sketch_relations -> 'pierce'", any(r["type"] == "pierce" for r in lr.get("relations", [])),
               str([r["type"] for r in lr.get("relations", [])]))
    V = [20, 0, 30]
    uv = to_uv([V[0], pl["plane_origin"][1], V[2]], info)       # proiezione del vertice sul piano dello schizzo
    d = await need(c, "add_sketch_relation", "M3 coincident: punto + vertice del modello (20,0,30)", relation="coincident",
                   entity1="pt@-7,9", entity2={"vertex": V})
    if d:
        pt = d["points"][0]
        err = math.hypot(pt["x"] - uv[0], pt["y"] - uv[1])
        record("M3 coincident con vertice: coordinate = proiezione del vertice (< 0,001 mm)", err < 1e-3,
               f"punto ({pt['x']:.5f}, {pt['y']:.5f}), atteso ({uv[0]:.5f}, {uv[1]:.5f})")
    await c.call("close_sketch")

    # ---- c) parallel / perpendicular / collinear / tangent / equal verso spigoli del modello (schizzo sul piano superiore)
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_rectangle", x1=0, y1=0, x2=40, y2=30)
    await c.call("close_sketch")
    await c.call("extrude_boss", depth=20)            # z 0..20
    await c.call("create_sketch", plane="Top")
    info = await plane_info(c)
    E0 = [0, 20, 0]                                   # spigolo y su x=0, z=0, lungo 40
    p0 = [0, 0, 0]
    p1 = [0, 40, 0]
    e_uv0, e_uv1 = to_uv(p0, info), to_uv(p1, info)
    e_dir = sub(e_uv1, e_uv0)
    e_len = norm(e_dir)
    e_dir = [x / e_len for x in e_dir]

    async def line_pts(lid):
        ok, _, ls = await c.call("list_sketch_entities")
        for s in ls.get("segments", []):
            if s["id"] == lid:
                return s
        return {}

    ok, _, dl = await c.call("draw_line", x1=5, y1=5, x2=25, y2=12)
    l1 = dl["entity_id"]
    d = await need(c, "add_sketch_relation", "M3 parallel: linea || spigolo del modello", relation="parallel", entity1=l1, entity2={"edge": E0})
    s = await line_pts(l1)
    if s:
        v = sub(s["end_mm"], s["start_mm"])
        cr = (v[0] * e_dir[1] - v[1] * e_dir[0]) / norm(v)
        record("M3 parallel (spigolo): prodotto vettoriale direzione/spigolo = 0", abs(cr) < 1e-4 and d.get("relations_added") == 1, f"sin = {cr:.6f}")
    ok, _, dl = await c.call("draw_line", x1=8, y1=-6, x2=22, y2=-10)
    l2 = dl["entity_id"]
    d = await need(c, "add_sketch_relation", "M3 perpendicular: linea perp. spigolo del modello", relation="perpendicular", entity1=l2, entity2={"edge": E0})
    s = await line_pts(l2)
    if s:
        v = sub(s["end_mm"], s["start_mm"])
        cs = (v[0] * e_dir[0] + v[1] * e_dir[1]) / norm(v)
        record("M3 perpendicular (spigolo): prodotto scalare = 0", abs(cs) < 1e-4 and d.get("relations_added") == 1, f"cos = {cs:.6f}")
    ok, _, dl = await c.call("draw_line", x1=8, y1=-15, x2=22, y2=-18)
    l3 = dl["entity_id"]
    d = await need(c, "add_sketch_relation", "M3 collinear: linea sullo spigolo del modello (x=-30)", relation="collinear", entity1=l3,
                   entity2={"edge": [-30, 20, 0]})
    s = await line_pts(l3)
    if s:
        q0, q1 = to_uv([-30, 0, 0], info), to_uv([-30, 40, 0], info)
        dd = sub(q1, q0)
        dd = [x / norm(dd) for x in dd]
        dists = [abs((p[0] - q0[0]) * dd[1] - (p[1] - q0[1]) * dd[0]) for p in (s["start_mm"], s["end_mm"])]
        record("M3 collinear (spigolo): gli estremi stanno sulla retta dello spigolo (< 0,001 mm)", max(dists) < 1e-3,
               f"distanze {[round(x, 6) for x in dists]}")
    ok, _, dc = await c.call("draw_circle", x=15, y=-25, radius=3)
    c1 = dc["entity_id"]
    d = await need(c, "add_sketch_relation", "M3 tangent: cerchio tangente allo spigolo del modello (x=0)", relation="tangent", entity1=c1,
                   entity2={"edge": E0})
    s = await line_pts(c1)
    if s:
        cen = s["center_mm"]
        dist_c = abs((cen[0] - e_uv0[0]) * e_dir[1] - (cen[1] - e_uv0[1]) * e_dir[0])
        record("M3 tangent (spigolo): distanza centro-spigolo = raggio", abs(dist_c - 3) < 1e-3, f"distanza {dist_c:.5f}, raggio {s.get('radius_mm')}")
    ok, _, dl = await c.call("draw_line", x1=10, y1=-30, x2=30, y2=-36)
    l4 = dl["entity_id"]
    d = await need(c, "add_sketch_relation", "M3 equal: lunghezza uguale a quella dello spigolo del modello (40)", relation="equal", entity1=l4,
                   entity2={"edge": E0})
    s = await line_pts(l4)
    if s:
        record("M3 equal (spigolo): lunghezza = 40 mm", abs(s["length_mm"] - 40) < 1e-3, f"lunghezza {s['length_mm']}")
    await c.call("close_sketch")

    # ---- d) concentric verso uno spigolo circolare
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_circle", x=20, y=10, radius=10)
    info = await plane_info(c)
    await c.call("close_sketch")
    await c.call("extrude_boss", depth=15)
    on_edge = to_model([30, 10], info)               # punto sul cerchio (raggio 10)
    await c.call("create_sketch", plane="Top")
    ok, _, dc = await c.call("draw_circle", x=5, y=-20, radius=4)
    cid = dc["entity_id"]
    d = await need(c, "add_sketch_relation", "M3 concentric: cerchio concentrico allo spigolo circolare del modello", relation="concentric",
                   entity1=cid, entity2={"edge": on_edge})
    ok, _, ls = await c.call("list_sketch_entities")
    s = next((x for x in ls.get("segments", []) if x["id"] == cid), {})
    if s:
        err = math.hypot(s["center_mm"][0] - 20, s["center_mm"][1] - 10)
        record("M3 concentric (spigolo circolare): centro = centro dello spigolo (20,10), < 0,001 mm", err < 1e-3,
               f"centro {s['center_mm']}, scarto {err:.6f}; relazioni aggiunte {d.get('relations_added')}")
    await c.call("close_sketch")


# ===================================================================================================== M4
async def m4_partenza(c):
    print("\n== M4. Estrusione con partenza 'Da': offset, superficie, vertice")
    A_ = PI * 3 * 3 * 5                                # cerchio r=3 per 5 mm sopra il blocco (z 30..35)
    CUT = PI * 3 * 3 * 10                              # taglio di 10 mm verso il basso da z=25 (z 15..25)

    async def setup():
        await block(c)                                 # A: x 0..20, y 0..40, z 0..30
        await c.call("create_sketch", plane="Front")   # colonna B: y 60..70, z 0..25, x 0..10 (cima a z=25)
        await c.call("draw_rectangle", x1=60, y1=0, x2=70, y2=25)
        await c.call("close_sketch")
        await c.call("extrude_boss", depth=10)
        await c.call("create_sketch", plane="Top")     # cerchio r=3 sopra A, sul piano z=0 (Top: u=y, v=-x)
        await c.call("draw_circle", x=20, y=-10, radius=3)
        return await vol(c)

    FACE_B, VERT_B = [5, 65, 25], [0, 60, 25]
    cases = [("extrude_boss", "partenza da superficie (faccia z=25 della colonna)", dict(start_from="surface", start_ref={"face": FACE_B}), A_),
             ("extrude_boss", "partenza da vertice (0,60,25)", dict(start_from="vertex", start_ref={"vertex": VERT_B}), A_),
             ("extrude_boss", "partenza da offset 25", dict(start_from="offset", start_offset=25), A_),
             ("extrude_boss", "start_offset=25 senza start_from (compatibilita')", dict(start_offset=25), A_),
             ("extrude_cut", "partenza da superficie (faccia z=25 della colonna)", dict(start_from="surface", start_ref={"face": FACE_B}), -CUT),
             ("extrude_cut", "partenza da vertice (0,60,25)", dict(start_from="vertex", start_ref={"vertex": VERT_B}), -CUT),
             ("extrude_cut", "partenza da offset 25", dict(start_from="offset", start_offset=25), -CUT)]
    for tool, lab, args, exp in cases:
        v0 = await setup()
        ok, text, d = await c.call(tool, depth=10, **args)
        v1 = await vol(c)
        got = v1 - v0
        record(f"M4 {tool} {lab}: variazione di volume", ok and abs(got - exp) < max(0.5, abs(exp) * TOL),
               f"misurata {got:+.3f} mm3, attesa {exp:+.3f}; start_from {d.get('start_from')}")
    # errori
    await setup()
    ok, text, _ = await c.call("extrude_boss", depth=10, start_from="surface")
    record("M4 start_from=surface senza start_ref: rifiutato", not ok, text.split("\n")[0][:120])
    ok, text, _ = await c.call("extrude_boss", depth=10, start_from="boh")
    record("M4 start_from sconosciuto: rifiutato", not ok, text.split("\n")[0][:120])
    ok, text, _ = await c.call("extrude_boss", depth=10, start_from="vertex", start_ref={"vertex": [1, 2, 3]})
    record("M4 start_ref non sul modello: rifiutato", not ok, text.split("\n")[0][:120])


# ===================================================================================================== M5
def ents_by(ents, typ):
    return [e for e in ents if e.get("type") == typ]


async def m5_entita(c):
    print("\n== M5. list_entities: tipo e parametri di facce e spigoli")
    # cilindro r=10 h=30 sull'asse z, forato con un cono (r=4 in alto, apice a z=22) e raccordato in basso (r=1)
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_circle", x=0, y=0, radius=10)
    await c.call("close_sketch")
    await c.call("extrude_boss", depth=30)             # z 0..30
    await c.call("create_sketch", plane="Front")
    await c.call("draw_line", x1=0, y1=30, x2=4, y2=30)
    await c.call("draw_line", x1=4, y1=30, x2=0, y2=22)
    ok, _, dl = await c.call("draw_line", x1=0, y1=22, x2=0, y2=30)
    await c.call("revolve_cut", axis=dl.get("entity_id"), angle=360)
    await c.call("fillet_at_points", radius=1, edge_points=[[10, 0, 0]])
    ok, text, d = await c.call("list_entities", kind="face")
    ents = d.get("entities", [])
    record("M5 list_entities(face) riuscito", ok and len(ents) >= 5, f"{len(ents)} facce")
    types = sorted(e.get("type") for e in ents)
    record("M5 tipi presenti: piano, cilindro, cono, toro", {"plane", "cylinder", "cone", "torus"} <= set(types), str(types))
    # piani
    pls = ents_by(ents, "plane")
    top = next((e for e in pls if abs(e.get("distance_from_origin", 0) - 30) < 1e-3), None)
    bot = next((e for e in pls if abs(e.get("distance_from_origin", 99)) < 1e-3), None)
    record("M5 piano superiore: normale +Z e distanza dall'origine 30 mm",
           top is not None and norm(sub(top["normal"], [0, 0, 1])) < 1e-4, str(top and (top["normal"], top["distance_from_origin"])))
    record("M5 piano inferiore: normale -Z e distanza 0", bot is not None and norm(sub(bot["normal"], [0, 0, -1])) < 1e-4,
           str(bot and (bot["normal"], bot["distance_from_origin"])))
    record("M5 piano: point_on_plane sta sul piano (n.(p-p0) = 0)",
           top is not None and abs(dot(top["normal"], top["point_on_plane"]) - top["distance_from_origin"]) < 1e-3, "")
    # cilindro
    cyl = next(iter(ents_by(ents, "cylinder")), None)
    if cyl:
        ao, ad = cyl["axis_origin"], cyl["axis_dir"]
        # distanza dell'asse dall'asse z (0,0): componenti x,y dell'origine trasversali alla direzione
        off = math.hypot(ao[0], ao[1])
        record("M5 cilindro: raggio 10, asse z passante per l'origine",
               abs(cyl["radius"] - 10) < 1e-3 and abs(abs(ad[2]) - 1) < 1e-4 and off < 1e-3,
               f"raggio {cyl['radius']}, asse origine {ao}, direzione {ad}")
    else:
        record("M5 cilindro presente", False, "")
    # cono
    cone = next(iter(ents_by(ents, "cone")), None)
    if cone:
        half = math.degrees(math.atan(4 / 8))
        ad = cone["axis_dir"]
        ap = cone.get("apex", [9, 9, 9])
        record("M5 cono: semi-angolo = atan(4/8) = 26,565 gradi", abs(cone["half_angle_deg"] - half) < 1e-3,
               f"misurato {cone['half_angle_deg']}, atteso {half:.4f}")
        record("M5 cono: asse z e apice in (0,0,22)", abs(abs(ad[2]) - 1) < 1e-4 and norm(sub(ap, [0, 0, 22])) < 1e-3,
               f"direzione {ad}, apice {ap}, origine {cone['origin']}, raggio all'origine {cone['radius_at_origin']}")
        r0, o = cone["radius_at_origin"], cone["origin"]
        record("M5 cono: raggio all'origine coerente (r = 4 * (z-22)/8)", abs(r0 - 4 * (o[2] - 22) / 8) < 1e-3, f"r {r0} a z={o[2]}")
    else:
        record("M5 cono presente", False, "")
    # toro (raccordo): raggio maggiore 9, minore 1, centro (0,0,1)
    tor = [e for e in ents_by(ents, "torus") if abs(e.get("minor_radius", 0) - 1) < 1e-3]
    if tor:
        t = tor[0]
        record("M5 toro del raccordo: raggio maggiore 9, minore 1, centro (0,0,1), asse z",
               abs(t["major_radius"] - 9) < 1e-3 and norm(sub(t["center"], [0, 0, 1])) < 1e-3 and abs(abs(t["axis_dir"][2]) - 1) < 1e-4,
               f"{t['major_radius']}, {t['minor_radius']}, {t['center']}, {t['axis_dir']}")
    else:
        record("M5 toro del raccordo presente", False, str(types))
    # spigoli
    ok, _, d = await c.call("list_entities", kind="edge")
    ed = d.get("entities", [])
    circ = ents_by(ed, "circle")
    top_c = next((e for e in circ if abs(e.get("radius", 0) - 10) < 1e-3 and abs(e["center"][2] - 30) < 1e-3), None)
    record("M5 spigolo circolare superiore: raggio 10, centro (0,0,30), asse z",
           top_c is not None and norm(sub(top_c["center"], [0, 0, 30])) < 1e-3 and abs(abs(top_c["axis_dir"][2]) - 1) < 1e-4,
           str(top_c and (top_c["radius"], top_c["center"], top_c["axis_dir"])))
    small = next((e for e in circ if abs(e.get("radius", 0) - 4) < 1e-3), None)
    record("M5 spigolo circolare del cono: raggio 4, z=30", small is not None and abs(small["center"][2] - 30) < 1e-3,
           str(small and (small["radius"], small["center"])))
    record("M5 spigoli: tipo 'circle' per tutti i cerchi", all(e.get("type") in ("circle", "line", "other") for e in ed), str(sorted(set(e.get("type") for e in ed))))
    # unita': cm
    ok, _, d = await c.call("list_entities", kind="face", unit="cm")
    cy = next(iter(ents_by(d.get("entities", []), "cylinder")), None)
    record("M5 unita' cm: raggio del cilindro 1,0 e distanza del piano 3,0", cy is not None and abs(cy["radius"] - 1.0) < 1e-4 and
           any(abs(e.get("distance_from_origin", 0) - 3.0) < 1e-4 for e in ents_by(d.get("entities", []), "plane")),
           str(cy and cy["radius"]))
    ok, _, d = await c.call("list_entities", kind="face", include_params=False)
    cy = next(iter(ents_by(d.get("entities", []), "cylinder")), None)
    record("M5 include_params=false: righe compatte senza parametri", cy is not None and "radius" not in cy and "type" in cy, str(cy))

    # retta: spigolo di un blocco
    await block(c)
    ok, _, d = await c.call("list_entities", kind="edge")
    lines = ents_by(d.get("entities", []), "line")
    ye = next((e for e in lines if abs(e["start"][0]) < 1e-6 and abs(e["start"][2]) < 1e-6 and abs(e["end"][0]) < 1e-6
               and abs(e["end"][2]) < 1e-6 and abs(abs(e["end"][1] - e["start"][1]) - 40) < 1e-6), None)
    record("M5 spigolo rettilineo lungo y (x=0,z=0): direzione ±Y e punto sulla retta",
           ye is not None and abs(abs(ye["direction"][1]) - 1) < 1e-4 and abs(ye["line_point"][0]) < 1e-4 and abs(ye["line_point"][2]) < 1e-4,
           str(ye and (ye["line_point"], ye["direction"])))
    # sfera e toro costruiti: rivoluzione
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_arc_3point", x1=0, y1=22, x2=7, y2=15, x3=0, y3=8)
    ok, _, dl = await c.call("draw_line", x1=0, y1=8, x2=0, y2=22)
    await c.call("revolve_boss", axis=dl.get("entity_id"), angle=360)
    ok, _, d = await c.call("list_entities", kind="face")
    f = d.get("entities", [])
    sph = next(iter(ents_by(f, "sphere")), None)
    tor0 = next((e for e in ents_by(f, "torus") if e.get("major_radius", 1) < 1e-3), None)
    if sph:
        record("M5 sfera r=7 centro (0,0,15)", abs(sph["radius"] - 7) < 1e-3 and norm(sub(sph["center"], [0, 0, 15])) < 1e-3, f"{sph['radius']}, {sph['center']}")
    elif tor0:
        record("M5 sfera riportata da SolidWorks come toro degenere: raggio minore 7, centro (0,0,15)",
               abs(tor0["minor_radius"] - 7) < 1e-3 and norm(sub(tor0["center"], [0, 0, 15])) < 1e-3, f"{tor0}")
    else:
        record("M5 sfera presente", False, str([(e.get('type'), e.get('major_radius'), e.get('minor_radius')) for e in f]))
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=15, y=10, radius=3)
    await c.call("draw_centerline_axis", x1=0, y1=0, x2=0, y2=30)
    await c.call("revolve_boss", angle=360)
    ok, _, d = await c.call("list_entities", kind="face")
    tors = ents_by(d.get("entities", []), "torus")
    t = tors[0] if tors else None
    record("M5 toro (cerchio r=3 a 15 dall'asse): raggio maggiore 15, minore 3, centro (0,0,10), asse z",
           t is not None and abs(t["major_radius"] - 15) < 1e-3 and abs(t["minor_radius"] - 3) < 1e-3 and norm(sub(t["center"], [0, 0, 10])) < 1e-3
           and abs(abs(t["axis_dir"][2]) - 1) < 1e-4, str(t and (t["major_radius"], t["minor_radius"], t["center"], t["axis_dir"])))
    # cono con l'apice verso +z (opposto al primo) per verificare il segno dell'apice
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_circle", x=0, y=0, radius=10)
    await c.call("close_sketch")
    await c.call("extrude_boss", depth=30)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_line", x1=0, y1=0, x2=4, y2=0)
    await c.call("draw_line", x1=4, y1=0, x2=0, y2=8)
    ok, _, dl = await c.call("draw_line", x1=0, y1=8, x2=0, y2=0)
    await c.call("revolve_cut", axis=dl.get("entity_id"), angle=360)
    ok, _, d = await c.call("list_entities", kind="face")
    cone = next(iter(ents_by(d.get("entities", []), "cone")), None)
    record("M5 cono con apice verso +z: apice (0,0,8), semi-angolo 26,565",
           cone is not None and norm(sub(cone.get("apex", [9, 9, 9]), [0, 0, 8])) < 1e-3 and abs(cone["half_angle_deg"] - math.degrees(math.atan(0.5))) < 1e-3,
           str(cone and (cone.get("apex"), cone["half_angle_deg"], cone["axis_dir"])))


if __name__ == "__main__":
    done = asyncio.run(run())
    print("\n==== RIEPILOGO ====")
    for tool, res, note in RESULTS:
        print(f"{res:5} {tool:70} {note}"[:230])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
