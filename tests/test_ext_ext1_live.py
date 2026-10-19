"""
Test live del lotto EXT1 (estensioni di tool di modellazione esistenti) tramite il server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente non viene mai
toccata; alla fine si chiude solo il PID lanciato dal test.

  E1  extrude_boss / extrude_cut: parete sottile (tubo, due direzioni, mezzeria, tappi), up_to_vertex, up_to_body
  E2  sweep: lungo un'elica (molla), con curva guida (cono), parete sottile, tangenza (rilettura), merge
  E3  loft: condizioni di partenza/arrivo, parete sottile, curva centrale
  E4  chamfer_at_points: smusso a vertice (d1*d2*d3/6), equal_distance
  E5  shell_body: multi_thickness (pareti piane con spessore diverso)
  E6  create_coordinate_system: modo numerico (origine e rotazione riletti)
  E7  draw_slot: asole ad arco (arc_center, arc_3point): area misurata con l'estrusione
  E8  mirror_feature / linear_pattern / circular_pattern con `bodies`
  E9  schizzi 3D: nome corretto in list_sketch_entities / get_sketch_definition_status

Uso:  .venv\\Scripts\\python.exe tests\\test_ext_ext1_live.py [E1 E2 ...]
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
    print(f"  [{'PASS' if ok else 'FAIL'}] {tool}  {note}"[:260])


def rel(got, exp):
    return abs(got - exp) / abs(exp) if exp else abs(got)


def close(label, got, exp, tol=TOL):
    record(label, rel(got, exp) < tol, f"misurato {got:.4f}, atteso {exp:.4f}, scarto {rel(got, exp) * 100:.4f} %")


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


async def bodies_count(c):
    ok, _, d = await c.call("get_mass_properties")
    return d.get("bodies", 0) if ok else 0


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


async def sketch(c, plane, **circle_or_rect):
    """Schizzo su `plane` con un cerchio (x,y,radius) o un rettangolo (x1,y1,x2,y2); restituisce il nome."""
    await c.call("create_sketch", plane=plane)
    if "radius" in circle_or_rect:
        await c.call("draw_circle", **circle_or_rect)
    else:
        await c.call("draw_rectangle", **circle_or_rect)
    ok, _, d = await c.call("close_sketch")
    return d.get("sketch") or d.get("name")


async def last_sketch_name(c):
    ok, _, d = await c.call("list_model_features")
    names = [f["name"] for f in d.get("features", []) if f.get("type") in ("ProfileFeature", "3DProfileFeature")]
    return names[-1] if names else None


async def block40(c, h=30):
    """Blocco 40 x 40 x h centrato (x,y -20..20, z 0..h)."""
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_rectangle", x1=-20, y1=-20, x2=20, y2=20)
    await c.call("close_sketch")
    await c.call("extrude_boss", depth=h)


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
    record("il PID lanciato dal test e' chiuso", not mine, f"altri processi non nostri {sorted(left)}")


async def scenario(c):
    only = {a.upper() for a in sys.argv[1:]}
    sezioni = [("E1", e1_sottile), ("E2", e2_sweep), ("E3", e3_loft), ("E4", e4_smusso), ("E5", e5_shell),
               ("E6", e6_cs), ("E7", e7_asole), ("E8", e8_corpi), ("E9", e9_schizzo3d)]
    for nome, fn in sezioni:
        if not only or nome in only:
            try:
                await fn(c)
            except Exception as e:           # un errore di una sezione non ferma le altre
                record(f"{nome}: eccezione", False, repr(e)[:180])
    await discard_all(c)


# ===================================================================================================== E1
async def e1_sottile(c):
    print("\n== E1. Estrusione a parete sottile, up_to_vertex, up_to_body")
    R, H, T = 10.0, 20.0, 2.0

    async def tube(label, expected, **kw):
        await new_part(c)
        await c.call("create_sketch", plane="Top")
        await c.call("draw_circle", x=0, y=0, radius=R)
        await c.call("close_sketch")
        d = await need(c, "extrude_boss", label, depth=H, **kw)
        if d:
            close(label + ": volume", d["volume_delta_mm3"], expected)

    tube("E1 tubo (parete verso l'esterno 2)", PI * ((R + T) ** 2 - R ** 2) * H, thin_thickness=T)
    tube("E1 tubo (verso l'interno 2)", PI * (R ** 2 - (R - T) ** 2) * H, thin_thickness=T, thin_type="opposite_direction")
    tube("E1 tubo (mezzeria 2)", PI * ((R + T / 2) ** 2 - (R - T / 2) ** 2) * H, thin_thickness=T, thin_type="mid_plane")
    tube("E1 tubo (due direzioni 2 fuori + 1 dentro)", PI * ((R + T) ** 2 - (R - 1) ** 2) * H, thin_thickness=T,
         thin_type="two_directions", thin_thickness2=1.0)
    tube("E1 tubo con tappi (spessore 1,5)", PI * ((R + T) ** 2 - R ** 2) * H + 2 * PI * R ** 2 * 1.5, thin_thickness=T,
         cap_ends=True, cap_thickness=1.5)
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_circle", x=0, y=0, radius=R)
    await c.call("close_sketch")
    ok, text, _ = await c.call("extrude_boss", depth=H, thin_thickness=T, thin_type="due_direzioni")
    record("E1 thin_type sconosciuto: rifiutato", not ok, text.split("\n")[0][:100])
    ok, text, _ = await c.call("extrude_boss", depth=H, thin_thickness=T, thin_type="two_directions")
    record("E1 two_directions senza thin_thickness2: rifiutato", not ok, text.split("\n")[0][:100])

    # taglio sottile in un blocco (si parte dalla faccia superiore z=30 e si scende)
    for tt, exp, lab in (("opposite_direction", PI * (R ** 2 - (R - T) ** 2) * 10, "verso l'interno"),
                         ("one_direction", PI * ((R + T) ** 2 - R ** 2) * 10, "verso l'esterno"),
                         ("mid_plane", PI * ((R + T / 2) ** 2 - (R - T / 2) ** 2) * 10, "mezzeria")):
        await block40(c)
        await c.call("create_sketch", plane="Top")
        await c.call("draw_circle", x=0, y=0, radius=R)
        await c.call("close_sketch")
        d = await need(c, "extrude_cut", f"E1 taglio sottile {lab}", depth=10, start_offset=30, thin_thickness=T, thin_type=tt)
        if d:
            close(f"E1 taglio sottile {lab}: volume asportato", -d["volume_delta_mm3"], exp)

    # up_to_vertex / up_to_body: piastra 40x40 spessa 5 a z 20..25 (corpo separato), cilindro r=5 dal piano Top
    async def plate_and_circle():
        await new_part(c)
        await c.call("create_sketch", plane="Top")
        await c.call("draw_rectangle", x1=-20, y1=-20, x2=20, y2=20)
        await c.call("close_sketch")
        await c.call("extrude_boss", depth=5, start_offset=20, merge=False)
        await c.call("create_sketch", plane="Top")
        await c.call("draw_circle", x=0, y=0, radius=5)
        await c.call("close_sketch")

    await plate_and_circle()
    d = await need(c, "extrude_boss", "E1 up_to_vertex (vertice (20,20,25))", end_condition="up_to_vertex",
                   up_to_vertex_point=[20, 20, 25], merge=False)
    if d:
        close("E1 up_to_vertex: cilindro alto 25 (pi r^2 25)", d["volume_delta_mm3"], PI * 25 * 25)
    ok, text, _ = await c.call("extrude_boss", end_condition="up_to_vertex")
    record("E1 up_to_vertex senza punto: rifiutato", not ok, text.split("\n")[0][:100])
    await plate_and_circle()
    d = await need(c, "extrude_boss", "E1 up_to_body (corpo = piastra)", end_condition="up_to_body",
                   up_to_face_point=[0, 0, 25], merge=False)
    if d:
        close("E1 up_to_body: si ferma sotto la piastra (altezza 20)", d["volume_delta_mm3"], PI * 25 * 20)
    # taglio fino a un vertice: blocco alto 30, cerchio dal piano Top (z=0) verso l'alto non taglia: parte da z=30
    await block40(c)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_circle", x=0, y=0, radius=5)
    await c.call("close_sketch")
    d = await need(c, "extrude_cut", "E1 taglio up_to_vertex (da z=30 al vertice z=10 non esiste: usa il vertice (20,20,0))",
                   start_offset=30, end_condition="up_to_vertex", up_to_vertex_point=[20, 20, 0])
    if d:
        close("E1 taglio up_to_vertex: foro profondo 30 (pi r^2 30)", -d["volume_delta_mm3"], PI * 25 * 30)


# ===================================================================================================== E2
async def e2_sweep(c):
    print("\n== E2. Sweep: elica, guida, parete sottile, tangenza, merge")
    # molla: cerchio r=1 lungo un'elica R=10, passo 5, 4 giri (create_helix e' del lotto curve)
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_circle", x=0, y=0, radius=10)
    await c.call("close_sketch")
    h = await need(c, "create_helix", "E2 elica R=10 passo 5, 4 giri", pitch=5, revolutions=4)
    if not h:
        return
    L = 4 * math.sqrt((2 * PI * 10) ** 2 + 5 ** 2)
    helix = h["feature"]
    close("E2 lunghezza dell'elica", h["length"], L, 0.002)
    d = await need(c, "sweep", "E2 molla: sweep di cerchio d=2 lungo l'elica (path = feature curva)", path_sketch=helix,
                   circular_diameter=2)
    if d:
        close("E2 molla (circular_diameter): volume = pi r^2 L", d["volume_delta_mm3"], PI * 1 * L, 0.01)
    # stessa molla con il profilo disegnato: cerchio r=1 sul piano Right nel punto di partenza (10,0,0) -> u=-10
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_circle", x=0, y=0, radius=10)
    await c.call("close_sketch")
    h = await need(c, "create_helix", "E2 elica (seconda molla)", pitch=5, revolutions=4)
    if h:
        await c.call("create_sketch", plane="Right")
        await c.call("draw_circle", x=-10, y=0, radius=1)
        await c.call("close_sketch")
        prof = await last_sketch_name(c)
        d = await need(c, "sweep", "E2 molla con profilo disegnato lungo l'elica", profile_sketch=prof, path_sketch=h["feature"])
        if d:
            close("E2 molla con profilo disegnato: volume = pi r^2 L (cos elica 0,3 %)", d["volume_delta_mm3"], PI * L, 0.01)

    # percorso: retta di 40 lungo Y (piano Front: u -> y); profilo cerchio r=5 sul piano Right (normale Y)
    async def straight(profile_r=5.0, extra_path=None):
        await new_part(c)
        await c.call("create_sketch", plane="Front")
        await c.call("draw_line", x1=0, y1=0, x2=40, y2=0)
        await c.call("close_sketch")
        path = await last_sketch_name(c)
        await c.call("create_sketch", plane="Right")
        await c.call("draw_circle", x=0, y=0, radius=profile_r)
        await c.call("close_sketch")
        prof = await last_sketch_name(c)
        return path, prof

    # guida: cono (r 5 -> 10 su 40): V = pi h/3 (r1^2 + r1 r2 + r2^2)
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_line", x1=0, y1=0, x2=40, y2=0)
    await c.call("close_sketch")
    path = await last_sketch_name(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_line", x1=0, y1=5, x2=40, y2=10)
    await c.call("close_sketch")
    guide = await last_sketch_name(c)
    await c.call("create_sketch", plane="Right")
    await c.call("draw_circle", x=0, y=0, radius=5)
    await c.call("close_sketch")
    prof = await last_sketch_name(c)
    d = await need(c, "sweep", "E2 sweep con curva guida (tronco di cono)", profile_sketch=prof, path_sketch=path,
                   guide_sketches=[guide])
    if d:
        close("E2 guida: volume = tronco di cono pi h/3 (25+50+100)", d["volume_delta_mm3"], PI * 40 / 3 * (25 + 50 + 100), 0.002)
        record("E2 guida: la feature riporta 1 guida", d.get("guide_count") in (1, None) and d.get("guides") == [guide],
               f"guide {d.get('guides')}, guide_count {d.get('guide_count')}")
    # parete sottile
    for tt, exp, lab in (("one_direction", PI * (6 ** 2 - 5 ** 2) * 40, "verso l'esterno"),
                         ("opposite_direction", PI * (5 ** 2 - 4 ** 2) * 40, "verso l'interno")):
        path, prof = await straight()
        d = await need(c, "sweep", f"E2 sweep sottile {lab} (spessore 1)", profile_sketch=prof, path_sketch=path,
                       thin_thickness=1, thin_type=tt)
        if d:
            close(f"E2 sweep sottile {lab}: volume", d["volume_delta_mm3"], exp, 0.002)
    path, prof = await straight()
    d = await need(c, "sweep", "E2 tangenza iniziale/finale path_tangent", profile_sketch=prof, path_sketch=path,
                   start_tangency="path_tangent", end_tangency="path_tangent")
    if d:
        record("E2 tangenza: riletta dalla feature (1 = tangente al percorso)",
               d.get("start_tangency_readback") == 1 and d.get("end_tangency_readback") == 1,
               f"start {d.get('start_tangency_readback')}, end {d.get('end_tangency_readback')}")
        close("E2 sweep con tangenza: volume invariato (pi r^2 40)", d["volume_delta_mm3"], PI * 25 * 40, 0.002)
    path, prof = await straight()
    ok, text, _ = await c.call("sweep", profile_sketch=prof, path_sketch=path, start_tangency="inventata")
    record("E2 tangenza sconosciuta: rifiutata", not ok, text.split("\n")[0][:100])

    # merge: sweep dentro un blocco (x,y -20..20, z 0..30): tubo r=5 lungo Y da y=0 a 40 a z=10
    async def merge_case(merge):
        await block40(c)
        await c.call("create_sketch", plane="Front")
        await c.call("draw_line", x1=0, y1=10, x2=40, y2=10)
        await c.call("close_sketch")
        path = await last_sketch_name(c)
        await c.call("create_sketch", plane="Right")
        await c.call("draw_circle", x=0, y=10, radius=5)
        await c.call("close_sketch")
        prof = await last_sketch_name(c)
        r = await c.call("sweep", profile_sketch=prof, path_sketch=path, merge=merge)
        return r[0], await vol(c), await bodies_count(c)

    ok, v, nb = await merge_case(True)
    close("E2 merge=true: volume = blocco + parte del tubo fuori (y 20..40)", v, 48000 + PI * 25 * 20, 0.002)
    record("E2 merge=true: 1 corpo", nb == 1, f"{nb} corpi")
    ok, v, nb = await merge_case(False)
    close("E2 merge=false: volume = blocco + tubo intero (corpi separati)", v, 48000 + PI * 25 * 40, 0.002)
    record("E2 merge=false: 2 corpi", nb == 2, f"{nb} corpi")


# ===================================================================================================== E3
async def e3_loft(c):
    print("\n== E3. Loft: condizioni iniziale/finale, parete sottile, curva centrale")

    async def squares():
        await new_part(c)
        await sketch(c, "Top", x1=-10, y1=-10, x2=10, y2=10)
        a = await last_sketch_name(c)
        ok, _, d = await c.call("create_reference_plane", mode="offset", base="Top", distance=30)
        pl = d.get("feature")
        await c.call("create_sketch", plane=pl)
        await c.call("draw_rectangle", x1=-5, y1=-5, x2=5, y2=5)
        await c.call("close_sketch")
        b = await last_sketch_name(c)
        return a, b

    frustum = 30 / 3 * (400 + 100 + math.sqrt(400 * 100))
    a, b = await squares()
    d = await need(c, "loft", "E3 loft semplice fra due quadrati", profile_sketches=[a, b])
    v_plain = d.get("volume_delta_mm3", 0.0) if d else 0.0
    if d:
        close("E3 loft semplice: tronco di piramide h/3 (A1 + A2 + sqrt(A1 A2))", v_plain, frustum, 0.001)
    res = {}
    for L in (0.5, 1.0):
        a, b = await squares()
        d = await need(c, "loft", f"E3 loft con condizione normal_to_profile (lunghezza tangente {L})",
                       profile_sketches=[a, b], start_condition="normal_to_profile", end_condition="normal_to_profile",
                       start_tangent_length=L, end_tangent_length=L)
        if d:
            res[L] = d["volume_delta_mm3"]
            record(f"E3 condizione normale (L={L}): riletta dalla feature = 1", d.get("start_condition_readback") == 1
                   and d.get("end_condition_readback") == 1, f"{d.get('start_condition_readback')}, {d.get('end_condition_readback')}")
    if len(res) == 2:
        record("E3 condizione normale: volume diverso dal tronco e coerente (fra la piramide minima e il tronco)",
               3000 < res[1.0] < frustum * 0.999 and 3000 < res[0.5] < frustum * 0.9995,
               f"L=0.5 {res[0.5]:.1f}, L=1 {res[1.0]:.1f}, tronco {frustum:.1f}")
        record("E3 condizione normale: la lunghezza della tangente cambia il volume (monotona)", res[1.0] < res[0.5] < frustum,
               f"{res[1.0]:.1f} < {res[0.5]:.1f} < {frustum:.1f}")
    # parete sottile: la parete e' l'offset normale alle facce del tronco: semilato w + t/cos(a), tan(a) = 5/30
    a, b = await squares()
    d = await need(c, "loft", "E3 loft sottile (spessore 1)", profile_sketches=[a, b], thin_thickness=1)
    if d:
        sh = 1.0 / (30 / math.hypot(30, 5))
        w0, w1 = 10 + sh, 5 + sh
        A0, A1 = (2 * w0) ** 2, (2 * w1) ** 2
        exp = 30 / 3 * (A0 + A1 + math.sqrt(A0 * A1)) - frustum
        close("E3 loft sottile: offset normale alle facce (tronco piu' grande - tronco)", d["volume_delta_mm3"], exp, 0.002)
    # curva centrale: retta lungo z -> stesso volume del loft semplice
    a, b = await squares()
    await c.call("create_sketch", plane="Front")
    await c.call("draw_line", x1=0, y1=0, x2=0, y2=30)
    await c.call("close_sketch")
    cl = await last_sketch_name(c)
    d = await need(c, "loft", "E3 loft con curva centrale (retta lungo z)", profile_sketches=[a, b], centerline_sketch=cl)
    if d:
        close("E3 curva centrale rettilinea: stesso volume del tronco", d["volume_delta_mm3"], frustum, 0.001)
    # direction_vector
    a, b = await squares()
    d = await need(c, "loft", "E3 loft con direction_vector (normale del piano Top, tangente lungo z)", profile_sketches=[a, b],
                   start_condition="direction_vector", end_condition="direction_vector",
                   start_direction={"plane": "Top"}, end_direction={"plane": "Top"})
    if d:
        record("E3 direction_vector: condizione 2 riletta e volume diverso dal tronco",
               d.get("start_condition_readback") == 2 and abs(d["volume_delta_mm3"] - frustum) > 50,
               f"cond {d.get('start_condition_readback')}/{d.get('end_condition_readback')}, volume {d['volume_delta_mm3']:.1f} (tronco {frustum:.1f})")
    ok, text, _ = await c.call("loft", profile_sketches=[a, b], start_condition="inventata")
    record("E3 condizione sconosciuta: rifiutata", not ok, text.split("\n")[0][:100])


# ===================================================================================================== E4
async def e4_smusso(c):
    print("\n== E4. Smusso a vertice ed equal_distance")
    await block40(c)                                     # 40 x 40 x 30
    v0 = await vol(c)
    d = await need(c, "chamfer_at_points", "E4 smusso a vertice (3, 4, 5) sull'angolo (20,20,30)", vertex_point=[20, 20, 30],
                   vertex_distances=[3, 4, 5])
    if d:
        close("E4 smusso a vertice: volume tolto = d1 d2 d3 / 6 = 10", v0 - await vol(c), 3 * 4 * 5 / 6, 0.002)
    v0 = await vol(c)
    d = await need(c, "chamfer_at_points", "E4 smusso a vertice con distanza unica (4) su un altro angolo", vertex_point=[-20, -20, 30],
                   distance=4)
    if d:
        close("E4 smusso a vertice 4,4,4: volume tolto = 64/6", v0 - await vol(c), 64 / 6, 0.002)
    v0 = await vol(c)
    d = await need(c, "chamfer_at_points", "E4 equal_distance 2 sullo spigolo (-20,0,0)", distance=2, edge_points=[[-20, 0, 0]],
                   equal_distance=True)
    if d:
        close("E4 equal_distance: volume tolto = d^2/2 * lunghezza (40)", v0 - await vol(c), 2 * 2 / 2 * 40, 0.002)
        record("E4 equal_distance: modo riportato", d.get("mode") == "equal_distance", str(d.get("mode")))
    ok, text, _ = await c.call("chamfer_at_points", distance=2)
    record("E4 senza edge_points ne' vertex_point: rifiutato", not ok, text.split("\n")[0][:100])
    ok, text, _ = await c.call("chamfer_at_points", vertex_point=[20, 20, 30], vertex_distances=[1, 2])
    record("E4 vertex_distances con 2 valori: rifiutato", not ok, text.split("\n")[0][:100])


# ===================================================================================================== E5
async def e5_shell(c):
    print("\n== E5. Shell con spessori diversi")
    await block40(c)                                     # x,y -20..20, z 0..30
    d = await need(c, "shell_body", "E5 shell 2 mm, parete x=20 di 5 mm, faccia superiore aperta", thickness=2,
                   remove_faces=[[0, 0, 30]], multi_thickness=[{"face": [20, 0, 15], "thickness": 5}])
    if d:
        solid = 48000 - 33 * 36 * 28            # cavita': x -18..15, y -18..18, z 2..30
        close("E5 volume del solido: 48000 - cavita' 33 x 36 x 28", await vol(c), solid, 0.001)
        ap = d.get("multi_thickness_applied") or [{}]
        record("E5 variazione misurata = variazione attesa (area parete interna x 3)",
               abs(ap[0].get("volume_delta_mm3", 0) - ap[0].get("expected_delta_mm3", 1)) < 1.0, str(ap[0]))
    await block40(c)
    d = await need(c, "shell_body", "E5 due pareti diverse (x=20: 5 mm, x=-20: 4 mm)", thickness=2, remove_faces=[[0, 0, 30]],
                   multi_thickness=[{"face": [20, 0, 15], "thickness": 5}, {"face": [-20, 0, 15], "thickness": 4}])
    if d:
        close("E5 due pareti: 48000 - cavita' 31 x 36 x 28 (x -16..15)", await vol(c), 48000 - 31 * 36 * 28, 0.001)
    await block40(c)
    ok, text, _ = await c.call("shell_body", thickness=2, remove_faces=[[0, 0, 30]],
                               multi_thickness=[{"face": [20, 0, 15], "thickness": -1}])
    record("E5 spessore negativo: rifiutato", not ok, text.split("\n")[0][:100])
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_circle", x=0, y=0, radius=15)
    await c.call("close_sketch")
    await c.call("extrude_boss", depth=30)
    ok, text, _ = await c.call("shell_body", thickness=2, remove_faces=[[0, 0, 30]],
                               multi_thickness=[{"face": [15, 0, 15], "thickness": 4}])
    record("E5 parete cilindrica: rifiutata (solo facce piane)", not ok, text.split("\n")[0][:100])


# ===================================================================================================== E6
async def e6_cs(c):
    print("\n== E6. Sistema di coordinate numerico")
    await new_part(c)
    d = await need(c, "create_coordinate_system", "E6 origine (10,20,30) e rotazione 90 gradi attorno a Z", origin=[10, 20, 30],
                   rotation=[0, 0, 90])
    if d:
        record("E6 origine riletta = (10,20,30)", max(abs(a - b) for a, b in zip(d["origin"], [10, 20, 30])) < 1e-4, str(d["origin"]))
        record("E6 rotazione Z 90: x=(0,1,0), y=(-1,0,0), z=(0,0,1)",
               max(abs(a - b) for a, b in zip(d["x_axis"] + d["y_axis"] + d["z_axis"], [0, 1, 0, -1, 0, 0, 0, 0, 1])) < 1e-5,
               str(r4(d["x_axis"] + d["y_axis"] + d["z_axis"])))
    d = await need(c, "create_coordinate_system", "E6 rotazione 30 gradi attorno a X, origine in cm (1,2,3)", origin=[1, 2, 3],
                   rotation=[30, 0, 0], unit="cm")
    if d:
        record("E6 origine in cm riletta = (1,2,3)", max(abs(a - b) for a, b in zip(d["origin"], [1, 2, 3])) < 1e-4, str(d["origin"]))
        s, k = math.sin(math.radians(30)), math.cos(math.radians(30))
        exp = [1, 0, 0, 0, k, s, 0, -s, k]
        record("E6 rotazione X 30: y=(0,cos,sin), z=(0,-sin,cos)",
               max(abs(a - b) for a, b in zip(d["x_axis"] + d["y_axis"] + d["z_axis"], exp)) < 1e-5,
               str(r4(d["x_axis"] + d["y_axis"] + d["z_axis"])))
    d = await need(c, "create_coordinate_system", "E6 solo rotazione 90 gradi attorno a Y", rotation=[0, 90, 0])
    if d:
        record("E6 rotazione Y 90: x=(0,0,-1), z=(1,0,0), origine nell'origine",
               max(abs(a - b) for a, b in zip(d["x_axis"] + d["z_axis"], [0, 0, -1, 1, 0, 0])) < 1e-5 and max(abs(v) for v in d["origin"]) < 1e-6,
               str(r4(d["x_axis"] + d["z_axis"])))
    ok, text, _ = await c.call("create_coordinate_system", origin=[1, 2])
    record("E6 origine con 2 valori: rifiutata", not ok, text.split("\n")[0][:100])


# ===================================================================================================== E7
async def e7_asole(c):
    print("\n== E7. Asole ad arco")
    W, H = 4.0, 10.0

    async def slot(label, exp_area, **args):
        await new_part(c)
        await c.call("create_sketch", plane="Top")
        d = await need(c, "draw_slot", label, width=W, **args)
        await c.call("close_sketch")
        if d:
            e = await need(c, "extrude_boss", label + ": estrusione 10", depth=H)
            if e:
                got = e["volume_delta_mm3"]
                close(label + ": area = w L + pi (w/2)^2 (volume/10)", got / H, exp_area, 0.002)
        return d

    cap = PI * (W / 2) ** 2
    d = await slot("E7 arc_center 0..90 gradi, raggio 20", W * (PI / 2 * 20) + cap, slot_type="arc_center", cx=0, cy=0, radius=20,
                   start_angle=0, end_angle=90)
    if d:
        record("E7 lunghezza dell'arco centrale riportata (31,416)", abs(d.get("centerline_length", 0) - PI * 10) < 1e-3,
               str(d.get("centerline_length")))
    await slot("E7 arc_center 0..180 gradi, raggio 15", W * (PI * 15) + cap, slot_type="arc_center", cx=0, cy=0, radius=15,
               start_angle=0, end_angle=180)
    await slot("E7 arc_center 0..90 in senso orario (arco di 270 gradi)", W * (1.5 * PI * 20) + cap, slot_type="arc_center", cx=0,
               cy=0, radius=20, start_angle=0, end_angle=90, clockwise=True)
    await slot("E7 arc_3point (20,0) -> (0,20) per (14.142,14.142)", W * (PI / 2 * 20) + cap, slot_type="arc_3point", x1=20, y1=0,
               x2=0, y2=20, x3=20 * math.cos(PI / 4), y3=20 * math.sin(PI / 4))
    await slot("E7 asola retta invariata (center_to_center 30)", W * 30 + cap, x1=0, y1=0, x2=30, y2=0)
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    ok, text, _ = await c.call("draw_slot", width=W, slot_type="arc_center", cx=0, cy=0)
    record("E7 arc_center senza raggio/angoli: rifiutato", not ok, text.split("\n")[0][:100])
    await c.call("close_sketch")


# ===================================================================================================== E8
async def e8_corpi(c):
    print("\n== E8. Corpi scelti: linear_pattern, circular_pattern, mirror_feature")

    async def cube(y0, y1, x0=-5, x1=5, h=10):
        await c.call("create_sketch", plane="Top")                 # Top: (u,v) -> (y,-x)
        await c.call("draw_rectangle", x1=y0, y1=-x1, x2=y1, y2=-x0)
        await c.call("close_sketch")
        await c.call("extrude_boss", depth=h, merge=False)

    # ripetizione lineare di un corpo (cubo 10 centrato in x,y; spigolo lungo Y a x=5, z=0)
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_rectangle", x1=-5, y1=-5, x2=5, y2=5)
    await c.call("close_sketch")
    await c.call("extrude_boss", depth=10)
    d = await need(c, "linear_pattern", "E8 ripetizione lineare del corpo (3 istanze, passo 20)", bodies=[[5, 0, 5]],
                   direction1={"edge": [5, 0, 0]}, count1=3, spacing1=20)
    if d:
        close("E8 lineare: volume totale 3 x 1000", await vol(c), 3000, 0.001)
        record("E8 lineare: 3 corpi", await bodies_count(c) == 3, f"{await bodies_count(c)} corpi; {d.get('bodies_before')} -> {d.get('bodies_after')}")
    ok, text, _ = await c.call("linear_pattern", direction1={"edge": [5, 0, 0]}, count1=3, spacing1=20)
    record("E8 lineare senza features ne' bodies: rifiutata", not ok, text.split("\n")[0][:100])

    # solo UNO dei due corpi viene ripetuto
    await new_part(c)
    await cube(10, 20)                                  # A: y 10..20
    await cube(-40, -30)                                # B: y -40..-30 (non ripetuto)
    d = await need(c, "linear_pattern", "E8 ripetizione lineare di un solo corpo su due (A, 2 istanze passo 25 lungo X)",
                   bodies=[[0, 15, 10]], direction1={"edge": [0, 10, 0]}, count1=2, spacing1=25)
    if d:
        close("E8 solo A ripetuto: volume 3 x 1000", await vol(c), 3000, 0.001)

    # specchiatura di un corpo (cubo A a y 10..20) rispetto al piano Right (y=0)
    await new_part(c)
    await cube(10, 20)
    d = await need(c, "mirror_feature", "E8 specchiatura del corpo rispetto al piano Right", bodies=[[0, 15, 10]], plane="Right",
                   merge=False)
    if d:
        close("E8 specchio: volume 2 x 1000", await vol(c), 2000, 0.001)
        record("E8 specchio: 2 corpi", await bodies_count(c) == 2, f"{await bodies_count(c)} corpi")
        ok, _, bb = await c.call("get_bounding_box")
        if ok:
            record("E8 specchio: y da -20 a 20", abs(bb["min"][1] + 20) < 1e-3 and abs(bb["max"][1] - 20) < 1e-3, f"{bb['min']} {bb['max']}")
    # specchio di uno solo di due corpi
    await new_part(c)
    await cube(10, 20)
    await cube(-60, -50)
    d = await need(c, "mirror_feature", "E8 specchiatura di un solo corpo su due", bodies=[[0, 15, 10]], plane="Right", merge=False)
    if d:
        close("E8 specchio di un corpo su due: volume 3 x 1000", await vol(c), 3000, 0.001)
        record("E8 specchio di un corpo su due: 3 corpi", await bodies_count(c) == 3, f"{await bodies_count(c)} corpi")

    # ripetizione circolare del corpo attorno all'asse Z
    await new_part(c)
    await cube(10, 20)
    ok, _, ax = await c.call("create_reference_axis", mode="two_planes", planes=["front", "right"])
    axn = ax.get("feature") or "Axis1"
    d = await need(c, "circular_pattern", "E8 ripetizione circolare del corpo (4 istanze) attorno all'asse Z", bodies=[[0, 15, 10]],
                   axis={"axis": axn}, count=4)
    if d:
        close("E8 circolare: volume 4 x 1000", await vol(c), 4000, 0.001)
        record("E8 circolare: 4 corpi", await bodies_count(c) == 4, f"{await bodies_count(c)} corpi; attesi {d.get('bodies_expected_if_separate')}")
    ok, text, _ = await c.call("mirror_feature", bodies=[[100, 100, 100]], plane="Right")
    record("E8 punto non su un corpo: rifiutato", not ok, text.split("\n")[0][:100])


# ===================================================================================================== E9
async def e9_schizzo3d(c):
    print("\n== E9. Schizzi 3D: nome corretto negli helper")
    await new_part(c)
    await c.call("create_sketch", plane="Front")                        # uno schizzo 2D PRIMA di quello 3D
    await c.call("draw_circle", x=0, y=0, radius=3)
    await c.call("close_sketch")
    n2d = await last_sketch_name(c)
    await need(c, "create_3d_sketch", "E9 apre uno schizzo 3D")
    await need(c, "draw_3d_line", "E9 linea 3D (0,0,0)-(10,10,10)", x1=0, y1=0, z1=0, x2=10, y2=10, z2=10)
    ok, _, d = await c.call("list_model_features")
    n3d = next((f["name"] for f in d.get("features", []) if f.get("type") == "3DProfileFeature"), None)
    record("E9 la feature 3D esiste (3DProfileFeature)", n3d is not None and n3d != n2d, f"2D {n2d}, 3D {n3d}")
    d = await need(c, "list_sketch_entities", "E9 list_sketch_entities sullo schizzo 3D attivo")
    record("E9 list_sketch_entities (attivo): nome = schizzo 3D", d.get("sketch") == n3d, f"{d.get('sketch')} (atteso {n3d})")
    d = await need(c, "get_sketch_definition_status", "E9 get_sketch_definition_status sullo schizzo 3D attivo")
    record("E9 get_sketch_definition_status (attivo): nome = schizzo 3D", d.get("sketch") == n3d, f"{d.get('sketch')} (atteso {n3d})")
    await c.call("close_sketch")
    d = await need(c, "list_sketch_entities", "E9 list_sketch_entities per nome (3D, riaperto)", sketch=n3d)
    record("E9 list_sketch_entities per nome: schizzo 3D con 1 segmento", d.get("sketch") == n3d and len(d.get("segments", [])) == 1,
           f"{d.get('sketch')}, {len(d.get('segments', []))} segmenti")
    await c.call("close_sketch")
    d = await need(c, "get_sketch_definition_status", "E9 get_sketch_definition_status per nome (3D)", sketch=n3d)
    record("E9 stato per nome: schizzo 3D", d.get("sketch") == n3d, f"{d.get('sketch')} (atteso {n3d})")
    await c.call("close_sketch")
    # il comportamento sugli schizzi 2D non cambia
    await c.call("create_sketch", plane="Top")
    await c.call("draw_line", x1=0, y1=0, x2=10, y2=0)
    d = await need(c, "list_sketch_entities", "E9 list_sketch_entities su un nuovo schizzo 2D attivo")
    n2 = None
    await c.call("close_sketch")
    n2 = await last_sketch_name(c)
    record("E9 schizzo 2D: nome = ultimo schizzo", d.get("sketch") == n2 and n2 not in (n2d, n3d), f"{d.get('sketch')} (atteso {n2})")
    d = await need(c, "list_sketch_entities", "E9 list_sketch_entities del primo schizzo 2D per nome", sketch=n2d)
    record("E9 schizzo 2D per nome: nome corretto, 1 segmento (cerchio)", d.get("sketch") == n2d and len(d.get("segments", [])) == 1,
           f"{d.get('sketch')}, {len(d.get('segments', []))}")
    await c.call("close_sketch")
    # sweep lungo lo schizzo 3D: _resolve_sketch/_exit_sketch usano il nome giusto
    await new_part(c)
    await c.call("create_3d_sketch")
    await c.call("draw_3d_line", x1=0, y1=0, z1=0, x2=0, y2=40, z2=0)
    await c.call("close_sketch")
    n3 = await last_sketch_name(c)
    await c.call("create_sketch", plane="Right")
    await c.call("draw_circle", x=0, y=0, radius=3)
    # lo schizzo del profilo e' ancora aperto: lo sweep lo chiude da solo e deve trovare il nome giusto
    d = await need(c, "sweep", "E9 sweep lungo schizzo 3D con profilo ancora aperto", path_sketch=n3, profile_sketch=await last_sketch_name(c))
    if d:
        close("E9 sweep su schizzo 3D: pi r^2 L", d["volume_delta_mm3"], PI * 9 * 40, 0.01)


if __name__ == "__main__":
    done = asyncio.run(run())
    print("\n==== RIEPILOGO ====")
    for tool, res, note in RESULTS:
        print(f"{res:5} {tool:70} {note}"[:230])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
