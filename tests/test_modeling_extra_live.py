"""
Test live del GRUPPO B (limiti di modellazione e tool base) tramite il server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente
non viene mai toccata; alla fine si chiude solo il PID lanciato dal test.

  B1  fillet_variable_radius: volume asportato vs integrale di (1-pi/4) r(s)^2 ds
  B2  piano per 3 punti, piani inclinati/offset, sistema di coordinate: normali e origini lette dall'API
  B3  convert_entities, up_to_surface, revolve_cut, loft con guide, sweep di taglio: volumi calcolati a mano
  B4  Hole Wizard: ISO/ANSI metrico/ANSI pollici/DIN/BSI/JIS, fori su cilindri e piani inclinati, diametri e
      profondita' MISURATI sul modello (list_entities) e volume asportato vs formula
  B5  tool base: open/save/save-as/close, draw_line/rectangle/arc/polygon, cut_extrude, set_units, execute_python
  B6  close_document sicuro (rifiuta con modifiche, save/discard, documento per titolo o percorso) + protezioni
      (overwrite, delete_feature con confirm) + annotazioni dei tool distruttivi

Uso:  .venv\\Scripts\\python.exe tests\\test_modeling_extra_live.py
Output: test_output\\ (file b5_*, b6_*)
"""

import os
import sys
import math
import asyncio
import subprocess
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, EXPECTED_TOOLS
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


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def norm(a):
    return math.sqrt(dot(a, a))


def sub(a, b):
    return [x - y for x, y in zip(a, b)]


def close_vec(a, b, tol=1e-4):
    return norm(sub(a, b)) < tol


async def need(c, tool, label, **args):
    """Chiama un tool, registra PASS/FAIL e restituisce i dati (vuoti se fallito)."""
    ok, text, d = await c.call(tool, **args)
    record(label, ok, text.split("\n")[0][:150])
    return d if ok else {}


async def vol(c):
    ok, _, d = await c.call("get_mass_properties")
    return d.get("volume_mm3", 0.0) if ok else 0.0


async def veq(c, label, exp, tol=TOL):
    v = await vol(c)
    record(f"{label}: volume", rel(v, exp) < tol,
           f"misurato {v:.3f} mm3, atteso {exp:.3f} mm3, scarto {rel(v, exp) * 100:.4f} %")
    return v


async def new_part(c):
    ok, text, _ = await c.call("create_new_part")
    assert ok, text


async def sketch_close(c):
    await c.call("close_sketch")


async def discard_all(c):
    """Chiude (scartando) tutti i documenti aperti: i pezzi di prova non servono dopo la misura."""
    for _ in range(40):
        ok, _, d = await c.call("list_open_documents")
        docs = d.get("documents", []) if ok else []
        if not docs:
            return
        await c.call("close_document", discard=True, document=docs[0]["title"])


async def face_circle(c, face_pt, center_yz, r, label=None):
    """Schizzo sulla faccia piana x=const passante per face_pt e cerchio centrato nel punto MODELLO (y,z) dato
    (le coordinate dello schizzo sono ricavate dagli assi che il tool restituisce: modello = origine + u*x + v*y)."""
    ok, text, info = await c.call("create_sketch_on_face", x=face_pt[0], y=face_pt[1], z=face_pt[2])
    if label:
        record(label, ok, text.split("\n")[0][:120])
    if not ok:
        return False
    o, ux, uy = info["sketch_origin_mm"], info["sketch_x_axis"], info["sketch_y_axis"]
    P = [face_pt[0], center_yz[0], center_yz[1]]
    u, v = dot(sub(P, o), ux), dot(sub(P, o), uy)
    ok2, _, _ = await c.call("draw_circle", x=u, y=v, radius=r)
    return ok2


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
                tl = (await session.list_tools()).tools
                tools = [t.name for t in tl]
                print(f"{len(tools)} tool esposti")
                ok, text, data = await c.call("connect_solidworks")
                my_pid = data.get("pid")
                print(text[:200])
                if not ok or not my_pid or my_pid in elia_pids or my_pid not in sw_pids():
                    print("STOP: nessuna istanza separata ottenibile. Nulla e' stato toccato.")
                    return False
                print(f"Istanza dedicata PID {my_pid} (diversa da {sorted(elia_pids)})")
                record("PID dedicato diverso dall'istanza utente", my_pid not in elia_pids, str(my_pid))
                await scenario(c, tl)
    finally:
        cleanup(my_pid, elia_pids)
    return True


def cleanup(my_pid, elia_pids):
    if my_pid and my_pid in sw_pids():
        subprocess.run(["taskkill", "/PID", str(my_pid), "/F"], capture_output=True)
    import time
    time.sleep(3)
    left = sw_pids() - elia_pids
    record("nessun processo SolidWorks orfano; istanza utente intatta", not left and elia_pids <= sw_pids(),
           f"orfani {sorted(left)}")
    print(f"Processi SolidWorks orfani dopo il test: {sorted(left)}; istanza utente intatta: {elia_pids <= sw_pids()}")


async def scenario(c, tl):
    # opzionale: `test_modeling_extra_live.py B1 B4` esegue solo quelle sezioni (utile in sviluppo)
    only = {a.upper() for a in sys.argv[1:]}
    sezioni = [("B0", lambda: sicurezza_tool_list(c, tl)), ("B1", lambda: b1_fillet_variabile(c)),
               ("B2", lambda: b2_riferimenti(c)), ("B3", lambda: b3_feature(c)), ("B4", lambda: b4_fori(c)),
               ("B5", lambda: b5_tool_base(c)), ("B6", lambda: b6_sicurezza(c)), ("B7", lambda: b7_fori_grandi(c)),
               ("B8", lambda: b8_sposta_facce(c))]
    for nome, fn in sezioni:
        if not only or nome in only:
            await fn()
    await discard_all(c)


# ===================================================================================================== B6 (elenco)
async def sicurezza_tool_list(c, tl):
    print("\n== 0. Elenco tool e annotazioni")
    names = [t.name for t in tl]
    record(f"{EXPECTED_TOOLS} tool (con execute_python), nessun duplicato", len(names) == EXPECTED_TOOLS and len(set(names)) == EXPECTED_TOOLS,
           f"{len(names)} tool")
    by = {t.name: t for t in tl}
    destr = ["close_document", "save_document", "save_drawing", "export_drawing", "export_model", "export_model_image",
             "export_simulation_plot", "create_drawing", "delete_feature", "delete_view", "delete_component", "delete_mate",
             "replace_component", "delete_custom_property", "delete_global_variable", "delete_equation",
             "delete_part_configuration", "delete_explode_step", "delete_simulation_study", "delete_simulation_load",
             "execute_python"]
    miss = [n for n in destr if n not in by or not (by[n].annotations and by[n].annotations.destructiveHint)]
    record("tool distruttivi annotati destructiveHint=true", not miss, f"{len(destr)} tool; mancanti {miss}")
    miss = [n for n in destr if n in by and "DESTRUCTIVE" not in (by[n].description or "")]
    record("tool distruttivi: nota [DESTRUCTIVE] nella descrizione", not miss, f"mancanti {miss}")
    props = by["close_document"].inputSchema["properties"]
    record("close_document espone save, discard, document", {"save", "discard", "document"} <= set(props), str(sorted(props)))
    over = [n for n in ("save_document", "save_drawing", "export_drawing", "export_model", "export_model_image",
                        "export_simulation_plot", "create_drawing")
            if "overwrite" not in by[n].inputSchema["properties"]]
    record("tool che scrivono file: parametro overwrite", not over, f"mancanti {over}")
    record("delete_feature espone confirm", "confirm" in by["delete_feature"].inputSchema["properties"])
    record("create_hole espone standard, head, fit", {"standard", "head", "fit"} <= set(by["create_hole"].inputSchema["properties"]))


# ===================================================================================================== B1
async def b1_fillet_variabile(c):
    print("\n== B1. Raccordo a raggio variabile")

    async def box_and_fillet(r0, r1):
        await new_part(c)
        await c.call("create_sketch", plane="Front")
        await c.call("draw_rectangle", x1=0, y1=0, x2=40, y2=40)
        await c.call("extrude_boss", depth=20)                    # x 0..20, y 0..40, z 0..40: V = 32000
        v0 = await vol(c)
        d = await need(c, "fillet_variable_radius", f"B1 raccordo variabile R{r0}->R{r1} sullo spigolo (20,40,*) lungo 40 mm",
                       edge_point=[20, 40, 20], radius_start=r0, radius_end=r1)
        return v0, await vol(c), d

    L = 40.0
    for r0, r1 in ((2, 8), (8, 2), (3, 7), (5, 5)):
        v0, v1, d = await box_and_fillet(r0, r1)
        exp = (1 - PI / 4) * L * (r0 * r0 + r0 * r1 + r1 * r1) / 3          # integrale di (1-pi/4) r(s)^2 ds, r lineare
        got = v0 - v1
        record(f"B1 volume asportato R{r0}->R{r1}", rel(got, exp) < TOL,
               f"asportato {got:.3f} mm3, atteso {exp:.3f} mm3, scarto {rel(got, exp) * 100:.4f} %")
        if (r0, r1) == (2, 8):
            ok_s, _, _ = await c.call("select_at_point", kind="face", x=20, y=34, z=0.05)
            ok_e, _, _ = await c.call("select_at_point", kind="face", x=20, y=34, z=39.95)
            record("B1 raggio d'inizio all'estremo z=0 (R2: la faccia x=20 arriva fino a y=38; all'altro estremo R8 no)",
                   ok_s and not ok_e, f"faccia piana a z=0.05: {ok_s}; a z=39.95: {ok_e}")
            record("B1 il risultato del tool riporta il delta di volume", abs(d.get("volume_delta_mm3", 0) + exp) < exp * TOL,
                   f"{d.get('volume_delta_mm3')}")
    await discard_all(c)


# ===================================================================================================== B2
async def b2_riferimenti(c):
    print("\n== B2. Piani di riferimento e sistema di coordinate")
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=0, x2=40, y2=30)
    await c.call("extrude_boss", depth=20)                        # x 0..20, y 0..40, z 0..30

    # --- piano per 3 vertici
    A, B, C = [0, 0, 0], [20, 40, 0], [0, 0, 30]
    d = await need(c, "create_reference_plane", "B2 piano per 3 vertici", mode="three_points", points=[A, B, C])
    n_exp = cross(sub(B, A), sub(C, A))
    n_exp = [x / norm(n_exp) for x in n_exp]
    n, o = d.get("plane_normal", [0, 0, 0]), d.get("plane_origin", [0, 0, 0])
    record("B2 piano 3 punti: normale = (B-A)x(C-A) normalizzato", close_vec(n, n_exp, 1e-5),
           f"letta {n}, attesa {[round(x, 6) for x in n_exp]}")
    on_plane = max(abs(dot(n, sub(P, o))) for P in (A, B, C))
    record("B2 piano 3 punti: i 3 vertici giacciono sul piano e l'origine e' sul piano", on_plane < 1e-3 and abs(dot(n, sub(A, o))) < 1e-3,
           f"scarto massimo {on_plane:.2e} mm; origine {o}")
    info = await need(c, "create_sketch", "B2 schizzo sul piano per 3 punti", plane=d.get("feature", "Piano1"))
    sn = info.get("sketch_normal", [0, 0, 0])
    record("B2 piano 3 punti: normale dello schizzo = normale del piano (secondo canale API)",
           abs(abs(dot(sn, n_exp)) - 1) < 1e-4, f"normale schizzo {sn}")
    await sketch_close(c)
    await c.call("rollback_to_feature", position="end")

    # --- piani offset
    d = await need(c, "create_reference_plane", "B2 piano offset 15 dal piano superiore", mode="offset", base="top", distance=15)
    record("B2 offset da 'top': normale (0,0,1), origine z=15", close_vec(d.get("plane_normal", []), [0, 0, 1], 1e-6) and
           abs(d.get("plane_origin", [0, 0, 0])[2] - 15) < 1e-4, f"{d.get('plane_normal')} {d.get('plane_origin')}")
    d = await need(c, "create_reference_plane", "B2 piano offset 7 dalla faccia z=30", mode="offset", base={"face": [10, 20, 30]}, distance=7)
    record("B2 offset da faccia: z = 37", abs(d.get("plane_origin", [0, 0, 0])[2] - 37) < 1e-4 and
           close_vec(d.get("plane_normal", []), [0, 0, 1], 1e-6), f"{d.get('plane_origin')} {d.get('plane_normal')}")
    d = await need(c, "create_reference_plane", "B2 piano offset 7 dalla faccia z=30, invertito", mode="offset",
                   base={"face": [10, 20, 30]}, distance=7, flip=True)
    record("B2 offset invertito: z = 23", abs(d.get("plane_origin", [0, 0, 0])[2] - 23) < 1e-4, f"{d.get('plane_origin')}")

    # --- piani inclinati attorno allo spigolo (0,*,30)
    for ang, flip in ((45, False), (45, True), (30, False)):
        d = await need(c, "create_reference_plane", f"B2 piano inclinato {ang} gradi attorno allo spigolo superiore (flip={flip})",
                       mode="angle", base={"face": [10, 20, 30]}, edge_point=[0, 20, 30], angle=ang, flip=flip)
        n, o = d.get("plane_normal", [0, 0, 0]), d.get("plane_origin", [0, 0, 0])
        ang_meas = math.degrees(math.acos(max(-1, min(1, dot(n, [0, 0, 1])))))
        contains_edge = abs(dot(n, sub([0, 5, 30], o))) < 1e-3 and abs(dot(n, sub([0, 35, 30], o))) < 1e-3
        record(f"B2 inclinato {ang} (flip={flip}): angolo con la faccia superiore", abs(ang_meas - ang) < 1e-3,
               f"misurato {ang_meas:.4f} gradi, normale {n}")
        record(f"B2 inclinato {ang} (flip={flip}): contiene lo spigolo (0,y,30)", contains_edge, f"origine {o}")
        if ang == 45:
            record(f"B2 inclinato 45 (flip={flip}): verso del piano", (n[0] > 0) == flip, f"componente x della normale {n[0]:+.4f}")

    # --- sistema di coordinate
    d = await need(c, "create_coordinate_system", "B2 sistema di coordinate: origine (20,40,30), X lungo lo spigolo y=40, Y lungo lo spigolo x=20",
                   origin_point=[20, 40, 30], x_edge_point=[10, 40, 30], y_edge_point=[20, 20, 30])
    ox, xa, ya, za = d.get("origin", []), d.get("x_axis", []), d.get("y_axis", []), d.get("z_axis", [])
    record("B2 CS: origine = vertice scelto", close_vec(ox, [20, 40, 30], 1e-3), f"{ox}")
    record("B2 CS: X parallelo allo spigolo scelto (asse X del modello)", abs(abs(dot(xa, [1, 0, 0])) - 1) < 1e-6, f"{xa}")
    record("B2 CS: Y parallelo allo spigolo scelto (asse Y del modello)", abs(abs(dot(ya, [0, 1, 0])) - 1) < 1e-6, f"{ya}")
    record("B2 CS: terna destrorsa ortonormale (Z = X x Y)", close_vec(cross(xa, ya), za, 1e-5) and abs(norm(za) - 1) < 1e-6, f"Z {za}")
    d2 = await need(c, "create_coordinate_system", "B2 sistema di coordinate con X invertito", origin_point=[20, 40, 30],
                    x_edge_point=[10, 40, 30], y_edge_point=[20, 20, 30], x_flip=True)
    record("B2 CS: x_flip inverte X e Z, lascia Y", close_vec(d2.get("x_axis", []), [-v for v in xa], 1e-6) and
           close_vec(d2.get("y_axis", []), ya, 1e-6) and close_vec(d2.get("z_axis", []), [-v for v in za], 1e-6),
           f"X {d2.get('x_axis')} Y {d2.get('y_axis')} Z {d2.get('z_axis')}")
    d3 = await need(c, "create_coordinate_system", "B2 sistema di coordinate sull'origine del vertice (0,0,0)", origin_point=[0, 0, 0],
                    x_edge_point=[10, 0, 0], z_edge_point=[0, 0, 15])
    xa3, za3 = d3.get("x_axis", []), d3.get("z_axis", [])
    record("B2 CS (X e Z da spigoli): origine (0,0,0), X//X, Z//Z, perpendicolari",
           close_vec(d3.get("origin", []), [0, 0, 0], 1e-3) and abs(abs(dot(xa3, [1, 0, 0])) - 1) < 1e-6 and
           abs(abs(dot(za3, [0, 0, 1])) - 1) < 1e-6 and abs(dot(xa3, za3)) < 1e-9, f"X {xa3} Z {za3}")
    await discard_all(c)


# ===================================================================================================== B3
async def b3_feature(c):
    print("\n== B3. convert_entities, up_to_surface, revolve_cut, loft con guide, sweep di taglio")

    # ---- convert_entities: bordo di una faccia e spigolo circolare
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=0, x2=40, y2=30)
    await c.call("extrude_boss", depth=10)                                         # x 0..10: V = 12000
    await need(c, "create_sketch_on_face", "B3 schizzo sulla faccia x=10", x=10, y=20, z=15)
    d = await need(c, "convert_entities", "B3 convert_entities: bordo della faccia (4 segmenti)", face_point=[10, 20, 15])
    record("B3 convert_entities: 4 segmenti proiettati", d.get("new_segments") == 4, str(d.get("new_segments")))
    await need(c, "extrude_boss", "B3 estrusione 5 mm del profilo convertito", depth=5)
    await veq(c, "B3 profilo convertito x 5 mm", 12000 + 40 * 30 * 5)
    await face_circle(c, [15, 3, 3], (20, 15), 6, "B3 schizzo sulla faccia x=15 con cerchio r=6 al centro (y=20,z=15)")
    await need(c, "extrude_cut", "B3 foro passante r=6", end_condition="through_all")
    v_hole = await vol(c)
    ok, _, d = await c.call("list_entities", kind="edge", limit=100)
    circ = [e for e in d.get("entities", []) if e.get("type") == "circle" and abs(e["point"][0] - 15) < 0.01]
    record("B3 spigolo circolare del foro sulla faccia x=15", len(circ) == 1 and abs(circ[0]["radius"] - 6) < 1e-3,
           f"{len(circ)} spigoli, r={circ[0]['radius'] if circ else None}")
    if circ:
        await need(c, "create_sketch_on_face", "B3 schizzo sulla faccia x=15 (angolo)", x=15, y=3, z=3)
        d = await need(c, "convert_entities", "B3 convert_entities: spigolo circolare (1 segmento)", edge_points=[circ[0]["point"]])
        record("B3 convert_entities: 1 segmento (il cerchio)", d.get("new_segments") == 1, str(d.get("new_segments")))
        await need(c, "extrude_boss", "B3 estrusione 3 mm del cerchio convertito", depth=3)
        await veq(c, "B3 cerchio convertito x 3 mm", v_hole + PI * 36 * 3)
    await discard_all(c)

    # ---- up_to_surface: cuneo con faccia superiore inclinata z = 20 + y/3
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    for a, b in (((0, 0), (60, 0)), ((60, 0), (60, 40)), ((60, 40), (0, 20)), ((0, 20), (0, 0))):
        await c.call("draw_line", x1=a[0], y1=a[1], x2=b[0], y2=b[1])
    await c.call("extrude_boss", depth=60)
    await veq(c, "B3 cuneo (trapezio 60x30 x 60)", 60 * 60 * 30)
    d = await need(c, "create_reference_plane", "B3 piano a z=60", mode="offset", base="top", distance=60)
    await c.call("create_sketch", plane=d.get("feature", "Piano1"))
    await c.call("draw_circle", x=30, y=-30, radius=5)                            # sketch (u,v)->(y,-x): centro y=30, x=30
    await need(c, "extrude_boss", "B3 extrude_boss up_to_surface fino alla faccia inclinata", end_condition="up_to_surface",
               up_to_face_point=[30, 30, 30], reverse=True)
    await veq(c, "B3 up_to_surface: pi r^2 (60 - z(y=30)) = pi*25*30", 60 * 60 * 30 + PI * 25 * (60 - 30))
    await discard_all(c)

    # ---- revolve_cut: gole a 360 e a 180 gradi
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=0, x2=80, y2=20)
    await c.call("draw_centerline_axis", x1=-10, y1=0, x2=90, y2=0)
    await need(c, "revolve_boss", "B3 albero cilindrico r=20 L=80", angle=360)
    await veq(c, "B3 cilindro", PI * 400 * 80)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=27, y1=17, x2=33, y2=21)
    await c.call("draw_centerline_axis", x1=-10, y1=0, x2=90, y2=0)
    await need(c, "revolve_cut", "B3 revolve_cut gola 360 gradi (larga 6, fondo r=17)", angle=360)
    await veq(c, "B3 gola 360", PI * 400 * 80 - PI * (400 - 289) * 6)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=45, y1=17, x2=49, y2=21)
    await c.call("draw_centerline_axis", x1=-10, y1=0, x2=90, y2=0)
    await need(c, "revolve_cut", "B3 revolve_cut gola 180 gradi (larga 4)", angle=180)
    await veq(c, "B3 gola 180", PI * 400 * 80 - PI * (400 - 289) * 6 - 0.5 * PI * (400 - 289) * 4)
    await discard_all(c)

    # ---- loft con guide
    async def two_profiles(w2):
        await new_part(c)
        await c.call("create_sketch", plane="top")
        await c.call("draw_rectangle", x1=-20, y1=-10, x2=20, y2=10)
        await sketch_close(c)
        d = await c.call("create_reference_plane", mode="offset", base="top", distance=30)
        await c.call("create_sketch", plane=d[2].get("feature", "Piano1"))
        await c.call("draw_rectangle", x1=-w2, y1=-10, x2=w2, y2=10)
        await sketch_close(c)

    await two_profiles(20)                       # senza guide: due rettangoli uguali = prisma 40x20x30
    await need(c, "loft", "B3 loft senza guide", profile_sketches=["Schizzo1", "Schizzo2"])
    await veq(c, "B3 loft senza guide (prisma)", 40 * 20 * 30)
    v_noguide = await vol(c)
    await discard_all(c)

    await two_profiles(10)                       # profilo 2 piu' stretto: guide rettilinee (20,0)->(10,30) e simmetrica
    await c.call("create_sketch", plane="Front")
    await c.call("draw_line", x1=20, y1=0, x2=10, y2=30)
    await sketch_close(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_line", x1=-20, y1=0, x2=-10, y2=30)
    await sketch_close(c)
    d = await need(c, "loft", "B3 loft con 2 guide rettilinee", profile_sketches=["Schizzo1", "Schizzo2"], guide_sketches=["Schizzo3", "Schizzo4"])
    ok, text, ep = await c.call("execute_python", code=f"result = doc.FeatureByName('{d.get('feature')}').GetDefinition.GetGuideCurvesCount")
    record("B3 loft: le 2 guide sono nella definizione della feature (letto dall'API)", ok and ep.get("result") == "2", str(ep.get("result")))
    await veq(c, "B3 loft guidato (trapezio (40+20)/2 x 30 x 20)", (40 + 20) / 2 * 30 * 20)
    await discard_all(c)

    await two_profiles(20)                       # guide curve (archi che sporgono di 5 mm): il volume DEVE superare il prisma
    await c.call("create_sketch", plane="Front")
    await c.call("draw_arc_3point", x1=20, y1=0, x2=25, y2=15, x3=20, y3=30)
    await sketch_close(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_arc_3point", x1=-20, y1=0, x2=-25, y2=15, x3=-20, y3=30)
    await sketch_close(c)
    await need(c, "loft", "B3 loft con 2 guide ad arco", profile_sketches=["Schizzo1", "Schizzo2"], guide_sketches=["Schizzo3", "Schizzo4"])
    # modello ideale: sezioni rettangolari 20 x 2w(z), w(z)=sqrt(25^2-(z-15)^2): V = 40 * integral
    ideal = 20 * 2 * (15 * 20 + 625 * math.asin(0.6))
    v = await vol(c)
    record("B3 loft con guide curve: volume vicino al modello ideale (sezioni rettangolari)", rel(v, ideal) < 0.015,
           f"misurato {v:.1f}, ideale {ideal:.1f}, scarto {rel(v, ideal) * 100:.3f} % (SW interpola le superfici fra le guide)")
    record("B3 loft con guide curve: le guide agiscono (volume > loft senza guide)", v > v_noguide * 1.10,
           f"{v:.1f} contro {v_noguide:.1f} senza guide")
    await discard_all(c)

    # ---- sweep di taglio
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-10, y1=-10, x2=70, y2=60)
    await c.call("extrude_boss", depth=20, end_condition="mid_plane")
    v0 = await vol(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_line", x1=0, y1=0, x2=40, y2=0)
    k = 20 * math.sin(PI / 4)
    await c.call("draw_arc_3point", x1=40, y1=0, x2=40 + k, y2=20 - 20 * math.cos(PI / 4), x3=60, y3=20)
    await c.call("draw_line", x1=60, y1=20, x2=60, y2=50)
    await sketch_close(c)
    await c.call("create_sketch", plane="right")
    await c.call("draw_circle", x=0, y=0, radius=5)
    await sketch_close(c)
    await need(c, "sweep", "B3 sweep di taglio (profilo r=5 lungo il percorso)", profile_sketch="Schizzo3", path_sketch="Schizzo2", cut=True)
    L = 40 + PI / 2 * 20 + 30
    got = v0 - await vol(c)
    record("B3 sweep di taglio: volume asportato = pi r^2 L (Pappus)", rel(got, PI * 25 * L) < TOL,
           f"asportato {got:.3f}, atteso {PI * 25 * L:.3f}, scarto {rel(got, PI * 25 * L) * 100:.4f} %")
    await discard_all(c)


# ===================================================================================================== B4
HOLE_T = 30.0
HOLE_POS = (40.0, 40.0)


async def plate(c):
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=0, x2=80, y2=80)
    await c.call("extrude_boss", depth=HOLE_T)                      # x 0..30, faccia superiore x=30


async def measure_hole(c, y0, z0, x_top=HOLE_T):
    """Cilindri/coni/piani che appartengono al foro con asse parallelo a X in (y0,z0), MISURATI sul modello."""
    ok, _, d = await c.call("list_entities", kind="face", limit=400)
    cyl, cones, floors = {}, [], []
    for e in d.get("entities", []):
        if e.get("type") == "cylinder":
            ao, ad = e["axis_origin"], e["axis_dir"]
            if abs(abs(ad[0]) - 1) < 1e-3 and abs(ao[1] - y0) < 0.02 and abs(ao[2] - z0) < 0.02:
                r = round(e["radius"], 4)
                cyl[r] = cyl.get(r, 0.0) + e["area"] / (2 * PI * r)
        elif e.get("type") == "cone":
            cones.append(e["area"])
        elif e.get("type") == "plane" and abs(abs(e["normal"][0]) - 1) < 1e-3 and 0.01 < e["point"][0] < x_top - 0.01:
            floors.append(e["point"][0])
    return cyl, cones, floors


def hole_volume(cyl, cones, thru_r, blind_tip_r=None, csk=None):
    """Volume asportato calcolato dalla geometria MISURATA: cilindri impilati + cono di svasatura + punta a 118 gradi."""
    v = sum(PI * r * r * h for r, h in cyl.items())
    if csk:
        r1, r2 = csk
        h = r1 - r2                                                  # svasatura a 90 gradi: semiangolo 45
        v += PI * h / 3 * (r1 * r1 + r1 * r2 + r2 * r2)
    if blind_tip_r:
        v += PI * blind_tip_r ** 3 / (3 * math.tan(math.radians(59)))
    return v


async def hole_case(c, label, expect, **args):
    """Piastra 80x80x30, foro al centro della faccia x=30: diametri/profondita' MISURATI e volume vs formula."""
    await plate(c)
    v0 = await vol(c)
    ok, text, d = await c.call("create_hole", face_point=[HOLE_T, HOLE_POS[0], HOLE_POS[1]], **args)
    if not ok:
        record(f"B4 {label}", False, text[:160])
        await discard_all(c)
        return
    v1 = await vol(c)
    cyl, cones, floors = await measure_hole(c, *HOLE_POS)
    removed = v0 - v1
    blind = not args.get("through", False)
    rs = sorted(cyl)
    notes, good = [], True
    # diametro di passaggio / punta
    if "thru" in expect:
        r_thru = min(rs) if rs else 0
        okd = abs(2 * r_thru - expect["thru"]) < 0.02
        good &= okd
        notes.append(f"Ø passaggio misurato {2 * r_thru:.4f} (atteso {expect['thru']})")
    csk_pair = None
    if "cb" in expect:
        dcb, hcb = expect["cb"]
        r_cb = max(rs) if rs else 0
        okd = abs(2 * r_cb - dcb) < 0.02 and abs(cyl.get(r_cb, 0) - hcb) < 0.02
        good &= okd
        notes.append(f"lamatura Ø{2 * r_cb:.3f} prof {cyl.get(r_cb, 0):.3f} (attesi {dcb} x {hcb})")
        okf = bool(floors) and abs((HOLE_T - hcb) - floors[0]) < 0.02
        good &= okf
        notes.append(f"fondo lamatura a x={floors[0] if floors else None}")
    if "csk" in expect:
        r2 = min(rs)
        area = sum(cones)
        r1 = math.sqrt(area / (math.sqrt(2) * PI) + r2 * r2)
        okd = abs(2 * r1 - expect["csk"]) < 0.02
        good &= okd
        csk_pair = (r1, r2)
        notes.append(f"svasatura Ø{2 * r1:.3f} (attesa {expect['csk']})")
    if "zones" in expect:      # filettato cieco: [(raggio, altezza), ...] zona filettata + zona punta
        for (rr, hh) in expect["zones"]:
            okz = abs(cyl.get(round(rr, 4), -1) - hh) < 0.02 if round(rr, 4) in cyl else any(
                abs(r - rr) < 0.005 and abs(h - hh) < 0.02 for r, h in cyl.items())
            good &= okz
        notes.append(f"zone {sorted(cyl.items(), reverse=True)}")
    tip = min(rs) if (blind and rs) else None
    exp_v = hole_volume(cyl, cones, None, blind_tip_r=tip, csk=csk_pair)
    okv = rel(removed, exp_v) < TOL
    good &= okv
    # la definizione riportata dal tool coincide col modello
    dims = (d.get("dimensions_mm") or [{}])[0]
    td = dims.get("ThruHoleDiameter") or dims.get("ThruTapDrillDiameter")
    if td and rs:
        good &= abs(td - 2 * min(rs)) < 0.02
        notes.append(f"definizione Ø{td}")
    record(f"B4 {label}", good, "; ".join(notes) + f"; asportato {removed:.2f} mm3, formula {exp_v:.2f} ({rel(removed, exp_v) * 100:.3f} %)")
    await discard_all(c)


async def b4_fori(c):
    print("\n== B4. Hole Wizard: standard, forme, facce cilindriche e inclinate")
    T = dict(through=True)
    # ---------- ISO
    await hole_case(c, "ISO M6 foro semplice passante (ISO 273 media: 6.6)", {"thru": 6.6}, kind="simple", size="M6", **T)
    await hole_case(c, "ISO M6 foro semplice, fit=close (6.4)", {"thru": 6.4}, kind="simple", size="M6", fit="close", **T)
    await hole_case(c, "ISO M6 foro semplice, fit=loose (7.0)", {"thru": 7.0}, kind="simple", size="M6", fit="loose", **T)
    await hole_case(c, "ISO M6 foro semplice, fit=database (6.4)", {"thru": 6.4}, kind="simple", size="M6", fit="database", **T)
    await hole_case(c, "ISO M10 foro semplice (11.0)", {"thru": 11.0}, kind="simple", size="M10", **T)
    await hole_case(c, "ISO M6 lamato per vite a testa cilindrica ISO 4762 (Ø11 x 6.4)", {"thru": 6.6, "cb": (11.0, 6.4)},
                    kind="counterbore", size="M6", head="socket", **T)
    await hole_case(c, "ISO M6 lamato testa cilindrica bombata ISO 1207 'cheese' (Ø11 x 3.9)", {"thru": 6.6, "cb": (11.0, 3.9)},
                    kind="counterbore", size="M6", head="cheese", **T)
    await hole_case(c, "ISO M6 lamato testa pan (Ø13 x 4.6)", {"thru": 6.6, "cb": (13.0, 4.6)}, kind="counterbore", size="M6", head="pan", **T)
    for hd in ("hex", "hex_cap", "hex_machine"):
        await hole_case(c, f"ISO M6 lamato testa esagonale ({hd}: Ø14.547 x 4.0)", {"thru": 6.6, "cb": (14.547, 4.0)},
                        kind="counterbore", size="M6", head=hd, **T)
    await hole_case(c, "ISO M6 svasato testa svasata ISO 10642 (Ø13.44)", {"thru": 6.6, "csk": 13.44}, kind="countersink", size="M6", head="socket", **T)
    await hole_case(c, "ISO M6 svasato testa piana ISO 7046 (Ø12.6)", {"thru": 6.6, "csk": 12.6}, kind="countersink", size="M6", head="flat", **T)
    await hole_case(c, "ISO M6 svasato testa goccia (raised: Ø12.6)", {"thru": 6.6, "csk": 12.6}, kind="countersink", size="M6", head="raised", **T)
    await hole_case(c, "ISO M6 filettato passante (punta Ø5.0)", {"thru": 5.0}, kind="tapped", size="M6", **T)
    await hole_case(c, "ISO M6 filettato cieco prof. 15 / filetto 12 (zona Ø6.0 x 12 + punta Ø5.0 x 3 + cono 118)",
                    {"zones": [(3.0, 12.0), (2.5, 3.0)]}, kind="tapped", size="M6", depth=15, thread_depth=12)
    # ---------- ANSI metrico
    await hole_case(c, "ANSI metrico M6 foro semplice (6.6)", {"thru": 6.6}, kind="simple", size="M6", standard="ansi_metric", **T)
    await hole_case(c, "ANSI metrico M6 lamato testa cilindrica (Ø11 x 6.0)", {"thru": 6.6, "cb": (11.0, 6.0)},
                    kind="counterbore", size="M6", standard="ansi_metric", head="socket", **T)
    await hole_case(c, "ANSI metrico M6 lamato esagonale hex_cap (Ø14.55 x 4.15)", {"thru": 6.6, "cb": (14.55, 4.15)},
                    kind="counterbore", size="M6", standard="ansi_metric", head="hex_cap", **T)
    await hole_case(c, "ANSI metrico M6 lamato button (Ø11.5 x 3.3)", {"thru": 6.6, "cb": (11.5, 3.3)},
                    kind="counterbore", size="M6", standard="ansi_metric", head="button", **T)
    await hole_case(c, "ANSI metrico M6 svasato flat (Ø12.6)", {"thru": 6.6, "csk": 12.6}, kind="countersink", size="M6",
                    standard="ansi_metric", head="flat", **T)
    await hole_case(c, "ANSI metrico M6 filettato (passo aggiunto: M6x1.0, punta 5.0)", {"thru": 5.0}, kind="tapped", size="M6",
                    standard="ansi_metric", **T)
    # ---------- ANSI pollici
    await hole_case(c, "ANSI pollici 1/4 foro semplice (Ø0.266 in = 6.7564)", {"thru": 6.7564}, kind="simple", size="1/4",
                    standard="ansi_inch", **T)
    await hole_case(c, "ANSI pollici #10 foro semplice (Ø0.206 in = 5.2324)", {"thru": 5.2324}, kind="simple", size="#10",
                    standard="ansi_inch", **T)
    await hole_case(c, "ANSI pollici 1/4 lamato socket (Ø7/16 in = 11.1125 x 0.25 in = 6.35)", {"thru": 6.7564, "cb": (11.1125, 6.35)},
                    kind="counterbore", size="1/4", standard="ansi_inch", head="socket", **T)
    await hole_case(c, "ANSI pollici 1/4 lamato esagonale (Ø19.05 x 4.7752)", {"thru": 6.7564, "cb": (19.05, 4.7752)},
                    kind="counterbore", size="1/4", standard="ansi_inch", head="hex", **T)
    await hole_case(c, "ANSI pollici 1/4 svasato flat (Ø12.8778)", {"thru": 6.7564, "csk": 12.8778}, kind="countersink", size="1/4",
                    standard="ansi_inch", head="flat", **T)
    await hole_case(c, "ANSI pollici 1/4-20 filettato passante (punta #7 = 5.105)", {"thru": 5.105}, kind="tapped", size="1/4-20",
                    standard="ansi_inch", **T)
    await hole_case(c, "ANSI pollici 1/4 (UNC 20 sottinteso) filettato cieco 15/12 (zona Ø6.35 x 12 + punta Ø5.105 x 3)",
                    {"zones": [(3.175, 12.0), (2.5525, 3.0)]}, kind="tapped", size="1/4", standard="ansi_inch", depth=15, thread_depth=12)
    # ---------- DIN, BSI, JIS
    await hole_case(c, "DIN M6 lamato testa cilindrica (Ø11 x 6.4)", {"thru": 6.6, "cb": (11.0, 6.4)}, kind="counterbore", size="M6",
                    standard="din", head="socket", **T)
    await hole_case(c, "DIN M6 svasato (Ø13.71)", {"thru": 6.6, "csk": 13.71}, kind="countersink", size="M6", standard="din", head="socket", **T)
    await hole_case(c, "DIN M6 filettato (5.0)", {"thru": 5.0}, kind="tapped", size="M6", standard="din", **T)
    await hole_case(c, "BSI M6 lamato (Ø11 x 6.0)", {"thru": 6.6, "cb": (11.0, 6.0)}, kind="counterbore", size="M6", standard="bsi", **T)
    await hole_case(c, "BSI M6 filettato (5.0)", {"thru": 5.0}, kind="tapped", size="M6", standard="bsi", **T)
    await hole_case(c, "JIS M6 lamato (Ø11 x 6.0)", {"thru": 6.6, "cb": (11.0, 6.0)}, kind="counterbore", size="M6", standard="jis", **T)
    await hole_case(c, "JIS M6 filettato (5.0)", {"thru": 5.0}, kind="tapped", size="M6", standard="jis", **T)

    # ---------- facce cilindriche: foro radiale nel punto richiesto (scarto < 0,01 gradi)
    def vunit(v):
        n = norm(v)
        return [x / n for x in v]

    def vbasis(a):
        ref = [1, 0, 0] if abs(a[0]) < 0.9 else [0, 1, 0]
        e1 = vunit(cross(a, ref))
        return e1, cross(a, e1)

    async def big_cylinder():
        ok, _, d = await c.call("list_entities", kind="face", limit=400)
        for e in (d.get("entities", []) if ok else []):
            if e.get("type") == "cylinder" and abs(e.get("radius", 0) - 30) < 1e-3:
                return e["axis_origin"], vunit(e["axis_dir"])
        return None, None

    async def hole_axes():
        ok, _, d = await c.call("list_entities", kind="face", limit=400)
        return [(e["axis_origin"], vunit(e["axis_dir"])) for e in (d.get("entities", []) if ok else [])
                if e.get("type") == "cylinder" and abs(e.get("radius", 0) - 3.3) < 0.05]

    def radial_point(c0, a, e1, e2, t, ang):
        ar = math.radians(ang)
        rad = [math.cos(ar) * e1[i] + math.sin(ar) * e2[i] for i in range(3)]
        p = [c0[i] + t * a[i] + 30 * rad[i] for i in range(3)]
        return p, rad

    def check_radial(label, p, rad, axes, ok, text, hd):
        hd = hd or {}
        if not ok or not axes:
            record(label, False, (text or "nessun foro").split("\n")[0][:150])
            return
        o, dd = min(axes, key=lambda ax: norm(cross(sub(p, ax[0]), ax[1])))
        dist = norm(cross(sub(p, o), dd))
        dang = math.degrees(math.acos(min(1.0, abs(dot(dd, rad)))))
        record(label, dist < 0.01 and dang < 0.01,
               f"distanza {dist:.4f} mm, scarto {dang:.4f} gradi, corretto={hd.get('curved_face_pick_corrected')}")

    casi = [("Right", 0, 0, [0, 45, 90, 180]), ("Top", 0, 0, [0, 45, 90, 180]), ("Front", 0, 0, [0, 45, 90, 180]),
            ("Right", 12, -7, [30, 135, 250])]
    for PIANO, CX, CY, ANGS in casi:
        await new_part(c)
        await c.call("create_sketch", plane=PIANO)
        await c.call("draw_circle", x=CX, y=CY, radius=30)
        await c.call("extrude_boss", depth=60)
        c0, a = await big_cylinder()
        if c0 is None:
            record(f"B4 cilindro {PIANO} centro ({CX},{CY}): cilindro R30 trovato", False, "nessuna faccia cilindrica R30")
            await discard_all(c)
            continue
        e1, e2 = vbasis(a)
        made = []
        for k, ang in enumerate(ANGS):
            p, rad = radial_point(c0, a, e1, e2, 10 + 12 * k, ang)
            ok, text, hd = await c.call("create_hole", kind="simple", size="M6", face_point=p, depth=10)
            made.append((ang, p, rad, ok, text, hd))
        axes = await hole_axes()
        for ang, p, rad, ok, text, hd in made:
            check_radial(f"B4 cilindro {PIANO} centro ({CX},{CY}) a={ang}: foro nel punto, radiale",
                         p, rad, axes, ok, text, hd)
        await discard_all(c)

    # caso multiplo: piu' fori in una sola chiamata (positions) su cilindro R30, piano Top
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_circle", x=0, y=0, radius=30)
    await c.call("extrude_boss", depth=60)
    c0, a = await big_cylinder()
    if c0 is None:
        record("B4 cilindro multipla: cilindro R30 trovato", False, "nessuna faccia cilindrica R30")
    else:
        e1, e2 = vbasis(a)
        pts = []
        for k, ang in enumerate([10, 100, 200, 300]):
            p, rad = radial_point(c0, a, e1, e2, 10 + 12 * k, ang)
            pts.append((ang, p, rad))
        ok, text, hd = await c.call("create_hole", kind="simple", size="M6", positions=[p for _, p, _ in pts], depth=10)
        axes = await hole_axes()
        for ang, p, rad in pts:
            check_radial(f"B4 cilindro Top centro (0,0) a={ang}: foro multipla nel punto, radiale",
                         p, rad, axes, ok, text, hd)
    await discard_all(c)

    # ---------- errori chiari
    await plate(c)
    ok, text, _ = await c.call("create_hole", kind="simple", size="M6", through=True, face_point=[30, 40, 40], standard="uni")
    record("B4 standard UNI: rifiutato con messaggio (assente dal database SolidWorks)", (not ok) and "UNI" in text and "database" in text, text.split("\n")[0][:140])
    ok, text, _ = await c.call("create_hole", kind="counterbore", size="M6", through=True, face_point=[30, 40, 40], head="foo")
    record("B4 head sconosciuto: rifiutato con l'elenco dei validi", (not ok) and "socket" in text, text.split("\n")[0][:140])
    ok, text, _ = await c.call("create_hole", kind="simple", size="M7", through=True, face_point=[30, 40, 40])
    record("B4 misura sconosciuta: rifiutata", not ok, text.split("\n")[0][:120])
    await discard_all(c)

    # ---------- piano inclinato
    wedge = [((0, 0), (60, 0)), ((60, 0), (60, 40)), ((60, 40), (0, 20)), ((0, 20), (0, 0))]

    async def new_wedge():
        await new_part(c)
        await c.call("create_sketch", plane="Front")
        for a, b in wedge:
            await c.call("draw_line", x1=a[0], y1=a[1], x2=b[0], y2=b[1])
        await c.call("extrude_boss", depth=60)

    th = math.atan(1 / 3)
    n_face = [0.0, -math.sin(th), math.cos(th)]
    await new_wedge()
    v0 = await vol(c)
    await need(c, "create_hole", "B4 foro passante M6 su piano inclinato (18.43 gradi), punto (30,30,30)", kind="simple", size="M6",
                   through=True, face_point=[30, 30, 30])
    removed = v0 - await vol(c)
    exp = PI * 3.3 ** 2 * 30 / math.cos(th)
    record("B4 piano inclinato passante: volume = pi r^2 z0/cos(angolo)", rel(removed, exp) < TOL,
           f"asportato {removed:.3f}, atteso {exp:.3f}, scarto {rel(removed, exp) * 100:.4f} %")
    ok, _, e = await c.call("list_entities", kind="face", limit=100)
    cy = [x for x in e.get("entities", []) if x.get("type") == "cylinder"]
    record("B4 piano inclinato: asse del foro = normale della faccia", len(cy) == 1 and close_vec(cy[0]["axis_dir"], n_face, 2e-3)
           and close_vec(cy[0]["axis_origin"], [30, 30, 30], 1e-2), f"asse {cy[0]['axis_dir'] if cy else None} da {cy[0]['axis_origin'] if cy else None}")
    record("B4 piano inclinato: Ø misurato 6.6", bool(cy) and abs(2 * cy[0]["radius"] - 6.6) < 0.01, f"{2 * cy[0]['radius'] if cy else None}")
    await discard_all(c)

    await new_wedge()
    v0 = await vol(c)
    await need(c, "create_hole", "B4 foro CIECO M6 prof. 12 su piano inclinato", kind="simple", size="M6", depth=12, face_point=[30, 30, 30])
    removed = v0 - await vol(c)
    ok, _, e = await c.call("list_entities", kind="face", limit=100)
    cy = [x for x in e.get("entities", []) if x.get("type") == "cylinder"]
    h = cy[0]["area"] / (2 * PI * cy[0]["radius"]) if cy else 0
    record("B4 piano inclinato cieco: profondita' misurata sul modello = 12 (lungo l'asse)", abs(h - 12) < 0.02, f"{h:.4f}")
    exp = PI * 3.3 ** 2 * 12 + PI * 3.3 ** 3 / (3 * math.tan(math.radians(59)))
    record("B4 piano inclinato cieco: volume = cilindro + punta 118 gradi", rel(removed, exp) < TOL,
           f"asportato {removed:.3f}, atteso {exp:.3f}, scarto {rel(removed, exp) * 100:.4f} %")
    await discard_all(c)

    # ---------- faccia cilindrica (cilindro R30, asse X, lungo 60): il foro e' RADIALE, volume = integrale di Steinmetz
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=30)
    await c.call("extrude_boss", depth=60)
    v0 = await vol(c)
    pc = 30 / math.sqrt(2)
    await need(c, "create_hole", "B4 foro passante M6 su faccia cilindrica R30", kind="simple", size="M6", through=True,
                   face_point=[30, pc, pc])
    removed = v0 - await vol(c)
    a, R, n = 3.3, 30.0, 400
    s = 0.0
    for i in range(n):
        for j in range(n):
            x = -a + 2 * a * (i + .5) / n
            z = -a + 2 * a * (j + .5) / n
            if x * x + z * z <= a * a:
                s += 2 * math.sqrt(R * R - z * z) * (2 * a / n) ** 2
    record("B4 cilindro: volume asportato = integrale (corde del cilindro sotto il disco del foro)", rel(removed, s) < 0.002,
           f"asportato {removed:.3f}, integrale {s:.3f}, scarto {rel(removed, s) * 100:.4f} %")
    ok, _, e = await c.call("list_entities", kind="face", limit=100)
    cy = [x for x in e.get("entities", []) if x.get("type") == "cylinder" and x["radius"] < 10]
    if cy:
        ao, hd = cy[0]["axis_origin"], cy[0]["axis_dir"]
        # distanza fra la retta del foro e l'asse del cilindro (retta Y=Z=0 lungo X): 0 = incidenti = foro RADIALE
        cx = cross(hd, [1, 0, 0])
        dist = abs(dot([ao[0], ao[1], ao[2]], cx)) / norm(cx) if norm(cx) > 1e-9 else 0.0
        record("B4 cilindro: Ø misurato 6.6 e asse del foro incidente all'asse del cilindro (radiale, normale alla superficie)",
               abs(2 * cy[0]["radius"] - 6.6) < 0.01 and abs(hd[0]) < 1e-6 and dist < 1e-3,
               f"Ø {2 * cy[0]['radius']:.4f}, distanza fra gli assi {dist:.2e} mm, quota assiale x={ao[0]:.3f}")
        ang_pick = math.degrees(math.atan2(pc, pc))
        ang_hole = math.degrees(math.atan2(ao[2], ao[1]))
        print(f"      (nota: punto indicato a {ang_pick:.1f} gradi, foro a {ang_hole:.1f} gradi attorno all'asse: SolidWorks "
              f"ruota la posizione angolare sulle facce cilindriche)")
    else:
        record("B4 cilindro: foro presente", False, "nessun cilindro piccolo")
    await discard_all(c)


# ===================================================================================================== B7
BIG_T = 100.0         # piastra 200 x 200 x 100 (il lamato M64 e' profondo 68): x 0..100, faccia dei fori x = 100, centro (y, z) = (100, 100)


async def big_plate(c):
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=0, x2=200, y2=200)
    await c.call("extrude_boss", depth=BIG_T)


async def big_case(c, label, d_exp, method, extra=None, **args):
    """Foro grande al centro della piastra: Ø MISURATO sul modello, volume asportato contro la formula, metodo usato."""
    await big_plate(c)
    v0 = await vol(c)
    ok, text, d = await c.call("create_hole", face_point=[BIG_T, 100, 100], **args)
    if not ok:
        record(f"B7 {label}", False, text[:200])
        await discard_all(c)
        return {}
    removed = v0 - await vol(c)
    cyl, cones, floors = await measure_hole(c, 100, 100, x_top=BIG_T)
    rs = sorted(cyl)
    r_min = rs[0] if rs else 0.0
    good = abs(2 * r_min - d_exp) < 0.02 and d.get("method") == method
    notes = [f"Ø misurato {2 * r_min:.4f} (atteso {d_exp})", f"metodo {d.get('method')} (atteso {method})"]
    if args.get("through"):
        exp_v = hole_volume(cyl, cones, None) if len(rs) > 1 else PI * (d_exp / 2) ** 2 * BIG_T
    else:
        tip = r_min if method == "hole_wizard" else None          # foro generico: fondo piatto
        exp_v = hole_volume(cyl, cones, None, blind_tip_r=tip)
        if method == "generic_hole":
            exp_v = PI * (d_exp / 2) ** 2 * args["depth"]
    okv = rel(removed, exp_v) < TOL
    good &= okv
    notes.append(f"asportato {removed:.2f} mm3, formula {exp_v:.2f} ({rel(removed, exp_v) * 100:.4f} %)")
    for k, v in (extra or {}).items():
        got = d.get(k)
        okk = (bool(got) and all(got)) if v == "present" else got == v
        good &= okk
        notes.append(f"{k}={got}")
    record(f"B7 {label}", good, "; ".join(notes))
    await discard_all(c)
    return d


async def b7_fori_grandi(c):
    print("\n== B7. Fori grandi fino a M70 (database Hole Wizard e foro generico)")
    T = dict(through=True)
    await big_case(c, "ISO M24 semplice passante (ISO 273 media 26)", 26.0, "hole_wizard", kind="simple", size="M24", **T)
    await big_case(c, "ISO M45 semplice fit=loose (52)", 52.0, "hole_wizard", kind="simple", size="M45", fit="loose", **T)
    await big_case(c, "ISO M36 filettato passante (punta 32)", 32.0, "hole_wizard", kind="tapped", size="M36", **T)
    await big_case(c, "ISO M52 filettato passante: nel database solo 'M52x5.0' (punta 47)", 47.0, "hole_wizard",
                   {"database_size": "M52x5.0"}, kind="tapped", size="M52", **T)
    await big_case(c, "ISO M64 lamato testa cilindrica (passaggio 70)", 70.0, "hole_wizard", kind="counterbore", size="M64",
                   head="socket", **T)
    await big_case(c, "ISO M60 semplice: assente dal database -> foro generico Ø66", 66.0, "generic_hole",
                   kind="simple", size="M60", **T)
    await big_case(c, "ISO M68 semplice fit=close -> foro generico Ø70", 70.0, "generic_hole",
                   kind="simple", size="M68", fit="close", **T)
    await big_case(c, "ISO M68 filettato passante -> foro generico Ø62 + filettatura cosmetica", 62.0, "generic_hole",
                   {"cosmetic_threads": "present"}, kind="tapped", size="M68", **T)
    d = await big_case(c, "ISO M70 filettato passante -> Ø64 + filettatura cosmetica", 64.0, "generic_hole",
                       {"cosmetic_threads": "present"}, kind="tapped", size="M70", **T)
    record("B7 M70: nota sui valori non normati", "interpolati" in str(d.get("size_note")), str(d.get("size_note"))[:120])
    await big_case(c, "ISO M70 filettato cieco prof. 40, filetto 30 -> Ø64 x 40 fondo piatto", 64.0, "generic_hole",
                   {"cosmetic_threads": "present"}, kind="tapped", size="M70", depth=40, thread_depth=30)
    await big_case(c, "DIN M48 lamato (passaggio 52)", 52.0, "hole_wizard", kind="counterbore", size="M48",
                   standard="din", head="socket", **T)
    # rifiuti chiari
    await big_plate(c)
    ok, text, _ = await c.call("create_hole", kind="countersink", size="M30", face_point=[BIG_T, 100, 100], **T)
    record("B7 svasato M30: rifiutato con le misure disponibili", not ok and "nessuna" in text,
           text[:200])
    ok, text, _ = await c.call("create_hole", kind="counterbore", size="M27", face_point=[BIG_T, 100, 100], head="socket", **T)
    record("B7 lamato M27: rifiutato, indica M24/M30", not ok and "M24, M30" in text, text[:200])
    ok, text, _ = await c.call("create_hole", kind="simple", size="M72", face_point=[BIG_T, 100, 100], **T)
    record("B7 M72: misura non supportata", not ok and "M70" in text, text[:160])
    await discard_all(c)


# ===================================================================================================== B8
async def mf_block(c):
    """Blocco x 0..40, y 0..100, z 0..60: V = 240000 mm3."""
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=0, x2=100, y2=60)
    await c.call("extrude_boss", depth=40)


async def xmax(c):
    ok, _, d = await c.call("get_bounding_box")
    return d.get("max", [None])[0] if ok else None


async def hole_axis(c):
    ok, _, d = await c.call("list_entities", kind="face", limit=100)
    for e in d.get("entities", []):
        if e.get("type") == "cylinder":
            return e["axis_origin"], e["radius"]
    return None, None


async def b8_sposta_facce(c):
    print("\n== B8. move_faces: offset, traslazione, rotazione")
    F = [[40, 50, 30]]
    for dist, exp in ((5, 270000.0), (-5, 210000.0)):
        await mf_block(c)
        ok, text, _ = await c.call("move_faces", faces=F, mode="offset", distance=dist)
        v, x = await vol(c), await xmax(c)
        record(f"B8 offset {dist:+} mm della faccia x=40", ok and rel(v, exp) < 1e-6 and abs(x - (40 + dist)) < 1e-6,
               f"V {v:.3f} (atteso {exp:.3f}), x max {x} (atteso {40 + dist}); {text[:80]}")
        await discard_all(c)
    # traslazione del foro: il cilindro si sposta, il volume resta
    a_hole = PI * 5.5 ** 2 * 40
    for label, args, exp_c in (("vector [0,10,0]", {"vector": [0, 10, 0]}, (60.0, 30.0)),
                               ("direction [0,0,2] + distance 5", {"direction": [0, 0, 2], "distance": 5}, (50.0, 35.0))):
        await mf_block(c)
        await c.call("create_hole", kind="simple", size="M10", face_point=[40, 50, 30], through=True)
        ok, text, _ = await c.call("move_faces", faces=[[20, 50 + 5.5, 30]], mode="translate", **args)
        ao, r = await hole_axis(c)
        v = await vol(c)
        good = ok and ao is not None and abs(ao[1] - exp_c[0]) < 1e-4 and abs(ao[2] - exp_c[1]) < 1e-4 and \
            abs(r - 5.5) < 1e-4 and rel(v, 240000 - a_hole) < 1e-6
        record(f"B8 translate {label}: asse del foro in (y,z) = {exp_c}", good,
               f"asse {ao}, r {r}, V {v:.3f} (atteso {240000 - a_hole:.3f}); {text[:80]}")
        await discard_all(c)
    # rotazione della faccia x=40 attorno all'asse Y per (40, *, 0): cuneo 100 * 60^2 * tan(a) / 2
    for ang in (5, -5):
        await mf_block(c)
        ok, text, _ = await c.call("move_faces", faces=F, mode="rotate", axis="y", axis_point=[40, 0, 0], angle=ang)
        v, x = await vol(c), await xmax(c)
        t = math.tan(math.radians(ang))
        exp_v = 240000 + 100 * 60 * 60 * t / 2
        exp_x = 40 + max(0.0, 60 * t)
        record(f"B8 rotate {ang:+} gradi attorno a Y per (40,0,0)", ok and rel(v, exp_v) < 1e-6 and abs(x - exp_x) < 1e-4,
               f"V {v:.3f} (atteso {exp_v:.3f}), x max {x:.5f} (atteso {exp_x:.5f}); {text[:80]}")
        await discard_all(c)
    await mf_block(c)
    ok, text, _ = await c.call("move_faces", faces=F, mode="rotate", angle=5)
    record("B8 rotate senza asse: rifiutato", not ok and "axis" in text, text[:120])
    ok, text, _ = await c.call("move_faces", faces=F, mode="scale", distance=5)
    record("B8 mode sconosciuto: rifiutato", not ok, text[:120])
    ok, text, _ = await c.call("move_faces", faces=[[500, 500, 500]], mode="offset", distance=5)
    record("B8 faccia inesistente: rifiutato", not ok, text[:120])
    record("B8 volume invariato dopo i rifiuti", rel(await vol(c), 240000.0) < 1e-9)
    await discard_all(c)


# ===================================================================================================== B5
async def b5_tool_base(c):
    print("\n== B5. Tool base: open/save/close, draw_*, cut_extrude, set_units, execute_python")
    A, B = OUT / "b5_a.SLDPRT", OUT / "b5_b.SLDPRT"
    for p in (A, B):
        if p.exists():
            p.unlink()

    # ---- disegno con draw_rectangle e estrusione; salva
    await new_part(c)
    await need(c, "create_sketch", "B5 create_sketch", plane="Front")
    d = await need(c, "draw_rectangle", "B5 draw_rectangle 20x10", x1=0, y1=0, x2=20, y2=10)
    record("B5 draw_rectangle: restituisce gli id delle entita'", len(d.get("entity_ids", [])) >= 4, str(list(d)[:6]))
    await need(c, "extrude_sketch", "B5 extrude_sketch 5", depth=5)
    await veq(c, "B5 rettangolo 20x10 estruso 5", 1000)
    d = await need(c, "save_document", "B5 save_document con nome (Save As)", filepath=str(A))
    record("B5 save_document: file creato su disco", A.exists() and A.stat().st_size > 1000, f"{A.stat().st_size if A.exists() else 0} byte")
    ok, _, info = await c.call("get_document_info")
    record("B5 get_document_info dopo il salvataggio: titolo e percorso", ok and info.get("title", "").lower().startswith("b5_a") and
           os.path.normcase(info.get("path", "")) == os.path.normcase(str(A)), f"{info.get('title')} {info.get('path')}")
    ok, text, d = await c.call("close_document")
    record("B5 close_document su documento appena salvato (nulla da perdere): chiude senza parametri", ok and d.get("action") == "closed_clean", text.split("\n")[0][:110])
    ok, _, d = await c.call("list_open_documents")
    record("B5 list_open_documents: b5_a non e' piu' aperto", not any("b5_a" in x["title"].lower() for x in d.get("documents", [])), str(d.get("documents")))

    # ---- open_document
    d = await need(c, "open_document", "B5 open_document", filepath=str(A))
    record("B5 open_document: titolo e percorso", "b5_a" in str(d.get("name", "")).lower() and os.path.normcase(d.get("path", "")) == os.path.normcase(str(A)), str(d))
    await veq(c, "B5 file riaperto: stesso volume", 1000)
    ok, text, _ = await c.call("open_document", filepath=str(OUT / "non_esiste.SLDPRT"))
    record("B5 open_document su file inesistente: errore chiaro", not ok and "not found" in text.lower(), text.split("\n")[0][:100])
    ok, _, d = await c.call("open_document", filepath=str(A))
    ok2, _, l = await c.call("list_open_documents")
    n_a = sum(1 for x in l.get("documents", []) if "b5_a" in x["title"].lower())
    record("B5 open_document su file gia' aperto: nessun duplicato", ok and n_a == 1, f"{n_a} copie aperte")

    # ---- cut_extrude: cieco, passante (blocco 20x10, spessore 5, faccia x=5)
    await face_circle(c, [5, 10, 5], (5, 5), 2, "B5 schizzo sulla faccia x=5 con cerchio r=2")
    v_prima = await vol(c)
    await need(c, "cut_extrude", "B5 cut_extrude cieco 3 mm (r=2)", depth=3)
    got = v_prima - await vol(c)
    record("B5 cut_extrude cieco: volume asportato = pi r^2 3 = 37.70", abs(got - PI * 4 * 3) < PI * 4 * 3 * TOL, f"asportato {got:.3f}")
    await face_circle(c, [5, 10, 8], (15, 5), 1.5, "B5 secondo cerchio r=1.5 sulla faccia x=5")
    v_prima = await vol(c)
    await need(c, "cut_extrude", "B5 cut_extrude through_all (r=1.5, spessore 5)", through_all=True)
    got = v_prima - await vol(c)
    record("B5 cut_extrude passante: volume asportato = pi r^2 5 = 35.34", abs(got - PI * 2.25 * 5) < PI * 2.25 * 5 * TOL, f"asportato {got:.3f}")
    d = await need(c, "save_document", "B5 save_document senza nome (Salva sul file del documento)")
    record("B5 save_document senza nome: salva sul file del documento", d.get("path", "").lower().endswith("b5_a.sldprt"), str(d.get("path")))
    ok, text, _ = await c.call("close_document")
    record("B5 close_document dopo Salva: nulla da perdere, chiude", ok, text.split("\n")[0][:100])
    await need(c, "open_document", "B5 riapertura: le modifiche salvate ci sono", filepath=str(A))
    await veq(c, "B5 volume riaperto dopo Salva", 1000 - PI * 4 * 3 - PI * 2.25 * 5)
    v_a = await vol(c)

    # ---- salva con nome: A resta com'era, B e' nuovo
    await face_circle(c, [5, 10, 8], (10, 8.5), 1, "B5 schizzo sulla faccia x=5 (per il Salva con nome)")
    await need(c, "cut_extrude", "B5 altro taglio (r=1, passante)", through_all=True)
    v_b = await vol(c)
    await need(c, "save_document", "B5 Salva con nome B", filepath=str(B))
    ok, text, d = await c.call("save_document", filepath=str(A))
    record("B5 Salva con nome su un file ESISTENTE: rifiutato senza overwrite", (not ok) and d.get("refused") == "file_exists", text.split("\n")[0][:130])
    await c.call("close_document")
    await need(c, "open_document", "B5 riapri A", filepath=str(A))
    await veq(c, "B5 A su disco e' rimasto com'era prima del Salva con nome", v_a)
    await c.call("close_document")
    await need(c, "open_document", "B5 riapri B", filepath=str(B))
    await veq(c, "B5 B contiene il taglio in piu'", v_b)
    await c.call("close_document")

    # ---- draw_line, draw_arc, draw_polygon
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await need(c, "draw_line", "B5 draw_line (0,0)-(30,40)", x1=0, y1=0, x2=30, y2=40)
    ok, _, d = await c.call("list_sketch_entities")
    segs = d.get("segments", [])
    ln = [s for s in segs if s.get("type") == "line"]
    lg = ln[0] if ln else {}
    length = lg.get("length_mm")
    record("B5 draw_line: lunghezza letta dallo schizzo = 50 mm", length is not None and abs(length - 50) < 1e-3, f"{length} ({lg})"[:120])
    await sketch_close(c)
    await discard_all(c)

    async def profile_volume(label, builder, exp, depth=5, tol=TOL):
        await new_part(c)
        await c.call("create_sketch", plane="Front")
        await builder()
        await need(c, "extrude_sketch", f"{label}: estrusione", depth=depth)
        await veq(c, label, exp, tol)
        await discard_all(c)

    async def semicircle():
        await need(c, "draw_arc", "B5 draw_arc 0->180 gradi, r=10", cx=0, cy=0, radius=10, start_angle=0, end_angle=180)
        await need(c, "draw_line", "B5 draw_line di chiusura del semicerchio", x1=-10, y1=0, x2=10, y2=0)
    await profile_volume("B5 semicerchio (draw_arc 0-180 + corda)", semicircle, PI * 100 / 2 * 5)

    async def quarter():
        await need(c, "draw_arc", "B5 draw_arc 0->90 gradi, r=10", cx=0, cy=0, radius=10, start_angle=0, end_angle=90)
        await c.call("draw_line", x1=0, y1=0, x2=10, y2=0)
        await c.call("draw_line", x1=0, y1=0, x2=0, y2=10)
    await profile_volume("B5 quarto di cerchio (draw_arc 0-90 + due raggi)", quarter, PI * 100 / 4 * 5)

    async def arc_off():
        await need(c, "draw_arc", "B5 draw_arc centro (20,5), 90->270 gradi, r=8", cx=20, cy=5, radius=8, start_angle=90, end_angle=270)
        await c.call("draw_line", x1=20, y1=13, x2=20, y2=-3)
    await profile_volume("B5 semicerchio sinistro con centro fuori origine (90-270)", arc_off, PI * 64 / 2 * 5)

    async def arc_inch():
        await need(c, "draw_arc", "B5 draw_arc con unit=inch (r=0.5 in)", cx=0, cy=0, radius=0.5, start_angle=0, end_angle=180, unit="inch")
        await c.call("draw_line", x1=-12.7, y1=0, x2=12.7, y2=0)
    await profile_volume("B5 semicerchio r=0.5 in = 12.7 mm", arc_inch, PI * 12.7 ** 2 / 2 * 5)

    for sides in (6, 5, 8):
        async def poly(s=sides):
            await need(c, "draw_polygon", f"B5 draw_polygon {s} lati, raggio 10", cx=0, cy=0, radius=10, sides=s)
        # poligono regolare con i vertici sulla circonferenza di raggio 10: area = s/2 r^2 sin(2pi/s)
        await profile_volume(f"B5 poligono {sides} lati (vertici sul cerchio r=10)", poly, sides / 2 * 100 * math.sin(2 * PI / sides) * 5)
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    ok, text, _ = await c.call("draw_polygon", cx=0, cy=0, radius=10, sides=2)
    record("B5 draw_polygon con 2 lati: rifiutato", not ok, text.split("\n")[0][:100])
    await discard_all(c)

    # ---- cut_extrude: both_directions su blocco centrato sul piano Front
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-20, y1=-20, x2=20, y2=20)
    await c.call("extrude_boss", depth=10, end_condition="mid_plane")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=4)
    v_prima = await vol(c)
    await need(c, "cut_extrude", "B5 cut_extrude both_directions con depth=3 (piano medio: 3 mm TOTALI)", depth=3, both_directions=True)
    got = v_prima - await vol(c)
    record("B5 cut_extrude both_directions + depth: piano medio, asportato pi r^2 3 = 150.80", abs(got - PI * 16 * 3) < PI * 16 * 3 * TOL, f"asportato {got:.3f}")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=10, y=10, radius=2)
    v_prima = await vol(c)
    await need(c, "cut_extrude", "B5 cut_extrude through_all da un lato solo (blocco x -5..5, schizzo su x=0)", through_all=True)
    got1 = v_prima - await vol(c)
    record("B5 cut_extrude through_all (una direzione): asportato pi r^2 5 = 62.83", abs(got1 - PI * 4 * 5) < PI * 4 * 5 * TOL, f"asportato {got1:.3f}")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=-10, y=-10, radius=2)
    v_prima = await vol(c)
    await need(c, "cut_extrude", "B5 cut_extrude through_all + both_directions", through_all=True, both_directions=True)
    got2 = v_prima - await vol(c)
    record("B5 cut_extrude through_all + both_directions: asportato pi r^2 10 = 125.66",
           abs(got2 - PI * 4 * 10) < PI * 4 * 10 * TOL, f"asportato {got2:.3f}")
    await discard_all(c)

    # ---- set_units
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    d = await need(c, "set_units", "B5 set_units inch", unit="inch")
    await c.call("draw_rectangle", x1=0, y1=0, x2=1, y2=1)
    await c.call("extrude_sketch", depth=0.5)
    await veq(c, "B5 set_units inch: 1x1 in estruso 0.5 in = 25.4x25.4x12.7 mm", 25.4 * 25.4 * 12.7)
    await need(c, "set_units", "B5 set_units mm (ripristino)", unit="mm")
    await discard_all(c)
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=0, x2=10, y2=10)
    await c.call("extrude_sketch", depth=2)
    await veq(c, "B5 set_units mm ripristinato: 10x10x2", 200)
    await discard_all(c)

    # ---- execute_python
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=0, x2=10, y2=10)
    await c.call("extrude_sketch", depth=3)
    ok, text, d = await c.call("execute_python", code="print(6*7)\nresult = math.sqrt(144)")
    record("B5 execute_python: stdout e result catturati", ok and d.get("stdout", "").strip() == "42" and d.get("result") == "12.0", str(d)[:100])
    ok, text, d = await c.call("execute_python", code="result = doc.GetType")
    record("B5 execute_python: 'doc' e' il documento attivo (pezzo = tipo 1)", ok and d.get("result") == "1", str(d.get("result")))
    ok, text, d = await c.call("execute_python", code="result = automation.get_mass_properties()['data']['volume_mm3']")
    record("B5 execute_python: 'automation' legge il volume (300 mm3)", ok and abs(float(d.get("result", 0)) - 300) < 1e-6, str(d.get("result")))
    ok, text, d = await c.call("execute_python", code="raise ValueError('prova')")
    record("B5 execute_python: eccezione -> errore con traceback", (not ok) and "ValueError" in text, text.split("\n")[0][:100])
    ok, text, d = await c.call("execute_python", code="def (:")
    record("B5 execute_python: errore di sintassi segnalato", (not ok) and "Syntax" in text, text.split("\n")[0][:100])
    ok, text, d = await c.call("execute_python", code="")
    record("B5 execute_python: codice vuoto rifiutato", not ok, text.split("\n")[0][:100])
    await discard_all(c)


# ===================================================================================================== B6
async def b6_sicurezza(c):
    print("\n== B6. close_document sicuro e protezioni")
    A = OUT / "b6_a.SLDPRT"
    PNG = OUT / "b6_img.png"
    for p in (A, PNG):
        if p.exists():
            p.unlink()

    async def titles():
        ok, _, d = await c.call("list_open_documents")
        return [x["title"] for x in d.get("documents", [])]

    async def active_title():
        ok, _, d = await c.call("get_document_info")
        return d.get("title")

    # 1. documento nuovo e modificato, mai salvato
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=0, x2=20, y2=10)
    await c.call("extrude_boss", depth=5)
    X = await active_title()
    ok, text, d = await c.call("close_document")
    record("B6 documento modificato: close_document senza parametri RIFIUTA e spiega", (not ok) and d.get("refused") == "unsaved_changes" and
           "PERDERE" in text and "save=true" in text and "discard=true" in text, text.split("\n")[0][:150])
    record("B6 ...e il documento resta aperto", X in await titles(), f"aperti {await titles()}")
    ok, text, d = await c.call("close_document", save=True)
    record("B6 save=true su documento mai salvato: rifiuta (non sa dove scrivere), resta aperto", (not ok) and d.get("refused") == "never_saved" and X in await titles(), text.split("\n")[0][:150])
    ok, text, d = await c.call("close_document", save=True, discard=True)
    record("B6 save=true e discard=true insieme: errore", not ok and "contraddizione" in text, text.split("\n")[0][:100])
    ok, text, d = await c.call("close_document", document="NonEsiste99")
    record("B6 documento inesistente: errore con l'elenco degli aperti", (not ok) and X in str(d.get("open_documents")), text.split("\n")[0][:150])

    # 2. salvato -> pulito; poi modificato -> sporco
    await need(c, "save_document", "B6 salva il documento", filepath=str(A))
    await face_circle(c, [5, 10, 5], (10, 5), 1)
    await c.call("cut_extrude", through_all=True)
    v_dirty = await vol(c)
    ok, text, d = await c.call("close_document")
    record("B6 documento salvato e poi modificato: rifiuta", (not ok) and d.get("refused") == "unsaved_changes", text.split("\n")[0][:120])

    # 3. un secondo documento sporco diventa attivo: chiudere A per titolo non deve toccare il documento attivo
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=3)
    await c.call("extrude_boss", depth=2)
    Y = await active_title()
    A_title = "b6_a.SLDPRT"
    ok, text, d = await c.call("close_document", document=A_title)
    record("B6 close_document(document=titolo) di un documento NON attivo e modificato: rifiuta", (not ok) and d.get("document", "").lower() == A_title.lower(), text.split("\n")[0][:130])
    record("B6 ...il documento attivo non e' stato toccato", await active_title() == Y and A_title.lower() in [t.lower() for t in await titles()], f"attivo {await active_title()}, aperti {await titles()}")
    ok, text, d = await c.call("close_document", document=str(A), save=True)
    record("B6 close_document(document=percorso, save=true): salva e chiude SOLO quello", ok and d.get("action") == "saved_and_closed" and
           A_title.lower() not in [t.lower() for t in await titles()] and await active_title() == Y, text.split("\n")[0][:130])
    await need(c, "open_document", "B6 riapri il salvato", filepath=str(A))
    await veq(c, "B6 save=true ha davvero salvato (volume con il taglio)", v_dirty)
    await c.call("close_document", document=str(A))                      # pulito: chiude senza parametri speciali

    # 4. discard sul documento attivo Y (nuovo, mai salvato)
    ok, text, d = await c.call("close_document", document=Y, discard=True)
    record("B6 discard=true: chiude scartando e lo DICHIARA", ok and d.get("action") == "discarded" and "SCARTATE" in text and Y not in await titles(), text.split("\n")[0][:150])

    # 5. discard: le modifiche non finiscono su disco
    await need(c, "open_document", "B6 riapri A", filepath=str(A))
    await face_circle(c, [5, 10, 5], (4, 5), 1)
    await c.call("cut_extrude", through_all=True)
    ok, text, d = await c.call("close_document", discard=True)
    record("B6 discard=true su documento salvato e modificato", ok and d.get("action") == "discarded", text.split("\n")[0][:120])
    await need(c, "open_document", "B6 riapri A dopo discard", filepath=str(A))
    await veq(c, "B6 dopo discard il file su disco e' invariato", v_dirty)

    # 6. schizzo in modifica = lavoro non salvato
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=2)
    ok, text, d = await c.call("close_document")
    record("B6 schizzo aperto in un documento: rifiuta", (not ok) and d.get("refused") == "unsaved_changes", text.split("\n")[0][:150])
    await c.call("close_document", discard=True)

    # 7. pulito: chiude senza parametri
    await c.call("open_document", filepath=str(A))
    ok, text, d = await c.call("close_document")
    record("B6 documento pulito: close_document senza parametri chiude (closed_clean)", ok and d.get("action") == "closed_clean" and d.get("was_modified") is False, text.split("\n")[0][:120])

    # 8. senza documenti
    ok, text, d = await c.call("close_document")
    record("B6 nessun documento aperto: nessun errore", ok, text.split("\n")[0][:100])

    # 9. sovrascrittura
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=0, x2=5, y2=5)
    await c.call("extrude_boss", depth=1)
    ok, text, d = await c.call("save_document", filepath=str(A))
    record("B6 save_document su file esistente (altro documento): rifiutato", (not ok) and d.get("refused") == "file_exists", text.split("\n")[0][:120])
    ok, text, d = await c.call("save_document", filepath=str(A), overwrite=True)
    record("B6 save_document overwrite=true: sovrascrive e lo dichiara", ok and d.get("overwritten") is True, text.split("\n")[0][:120])
    ok, text, d = await c.call("export_model_image", filepath=str(PNG), view="isometric")
    record("B6 export_model_image su file nuovo", ok and PNG.exists(), text.split("\n")[0][:100])
    ok, text, d = await c.call("export_model_image", filepath=str(PNG), view="isometric")
    record("B6 export_model_image su file esistente: rifiutato senza overwrite", (not ok) and d.get("refused") == "file_exists", text.split("\n")[0][:120])
    ok, text, d = await c.call("export_model_image", filepath=str(PNG), view="isometric", overwrite=True)
    record("B6 export_model_image overwrite=true", ok, text.split("\n")[0][:100])
    await discard_all(c)

    # 10. delete_feature: confirm, dipendenti
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=0, x2=60, y2=60)
    await c.call("extrude_boss", depth=20)
    await face_circle(c, [20, 10, 10], (10, 10), 2)
    cut = (await need(c, "extrude_cut", "B6 foro da eliminare", end_condition="through_all")).get("feature")
    ok, _, e = await c.call("list_entities", kind="edge", limit=60)
    ey = [x for x in e.get("entities", []) if x.get("type") == "line" and abs(x["start"][1] - x["end"][1]) > 10][0]
    pat = (await need(c, "linear_pattern", "B6 ripetizione del foro (dipendente)", features=[cut], direction1={"edge": ey["point"]}, count1=3, spacing1=15)).get("feature")
    v_pat = await vol(c)
    ok, text, d = await c.call("delete_feature", name=cut)
    record("B6 delete_feature senza confirm: rifiutato", (not ok) and d.get("refused") == "confirm_required" and cut in str(d.get("feature")), text.split("\n")[0][:150])
    ok, text, d = await c.call("delete_feature", name=cut, confirm=True)
    record("B6 delete_feature con dipendenti (ripetizione): rifiutato e le elenca", (not ok) and d.get("refused") == "has_dependents" and pat in d.get("dependents", []), text.split("\n")[0][:150])
    record("B6 ...nulla e' stato eliminato (volume invariato)", abs(await vol(c) - v_pat) < 1e-6)
    ok, text, d = await c.call("delete_feature", name=cut, confirm=True, delete_children=True)
    record("B6 delete_feature confirm + delete_children: elimina e riporta l'elenco", ok and cut in d.get("deleted_features", []) and pat in d.get("deleted_features", []), text.split("\n")[0][:170])
    await veq(c, "B6 dopo l'eliminazione il blocco e' pieno", 60 * 60 * 20)
    await face_circle(c, [20, 30, 30], (30, 30), 3)
    cut2 = (await c.call("extrude_cut", end_condition="through_all"))[2].get("feature")
    ok, text, d = await c.call("delete_feature", name=cut2, confirm=True)
    record("B6 delete_feature senza dipendenti: con confirm elimina", ok and d.get("volume_delta_mm3", 0) > 0, text.split("\n")[0][:120])
    await discard_all(c)


if __name__ == "__main__":
    done = asyncio.run(run())
    print("\n==== RIEPILOGO ====")
    for tool, res, note in RESULTS:
        print(f"{res:5} {tool:70} {note}"[:230])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
