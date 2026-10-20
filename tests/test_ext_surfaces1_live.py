"""
Test live del lotto SUPERFICI 1 (creazione di superfici: estrusa, rivoluzione, sweep, loft, piana, boundary, rigata,
riempimento) tramite il server MCP (stdio). Ogni numero e' MISURATO (area dei corpi superficie, volume) e confrontato con un
valore calcolato a mano.

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated); alla fine si chiude solo il PID del test.

Coordinate del modello (template di questo PC): schizzo su "Front" -> normale +X, u=Y, v=Z; "Top" -> normale +Z, u=Y, v=-X;
"Right" -> normale +Y, u=-X, v=Z.

  E  extrude_surface (cieca, piano di mezzeria, due direzioni, sformo, cappe -> solido, fino alla superficie, passante)
  R  revolve_surface (360, 90, due direzioni, piano di mezzeria)
  W  sweep_surface (retto, con guida, torsione, profilo circolare, solo percorso)
  L  loft_surface (due linee, con guide, chiuso)
  P  planar_surface (da schizzo, da spigoli)
  B  boundary_feature (superficie, due direzioni, boss, taglio)
  U  ruled_surface (tangente, normale, perpendicolare al vettore, rastremata non supportata)
  F  fill_surface (patch, unito, chiude un buco -> solido, tangente)

Uso:  .venv\\Scripts\\python.exe tests\\test_ext_surfaces1_live.py [E R W L P B U F]
"""

import os
import sys
import math
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, PYTHON, SERVER, sw_pids, Client, cleanup

RESULTS = []


def record(tool, ok, note=""):
    RESULTS.append((tool, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {tool}  {note}"[:260])


def close(a, b, rel=0.002, ab=0.05):
    return a is not None and abs(a - b) <= max(ab, abs(b) * rel)


async def new_part(c):
    await c.call("close_document", discard=True)
    ok, text, _ = await c.call("create_new_part")
    assert ok, text


async def sketch(c, plane, *shapes):
    """Schizzo su `plane` con le forme [("line", x1,y1,x2,y2) | ("circle", x,y,r) | ("rect", x1,y1,x2,y2) | ("center", x1,y1,x2,y2)];
    -> nome dello schizzo."""
    ok, text, _ = await c.call("create_sketch", plane=plane)
    assert ok, text
    for s in shapes:
        if s[0] == "line":
            r = await c.call("draw_line", x1=s[1], y1=s[2], x2=s[3], y2=s[4])
        elif s[0] == "circle":
            r = await c.call("draw_circle", x=s[1], y=s[2], radius=s[3])
        elif s[0] == "rect":
            r = await c.call("draw_rectangle", x1=s[1], y1=s[2], x2=s[3], y2=s[4])
        else:
            r = await c.call("draw_centerline_axis", x1=s[1], y1=s[2], x2=s[3], y2=s[4])
        assert r[0], r[1]
    ok, text, d = await c.call("close_sketch")
    assert ok, text
    return d.get("sketch") or d.get("name") or d.get("sketch_name")


async def last_sketch(c):
    ok, _, d = await c.call("list_model_features")
    names = [f["name"] for f in d.get("features", []) if f.get("type") == "ProfileFeature"]
    return names[-1] if names else None


async def mk_sketch(c, plane, *shapes):
    n = await sketch(c, plane, *shapes)
    return n or await last_sketch(c)


async def offset_plane(c, dist):
    ok, text, d = await c.call("create_reference_plane", mode="offset", base="Front", distance=dist)
    assert ok, text
    return d["feature"]


async def tool(c, name, **args):
    ok, text, d = await c.call(name, **args)
    if not ok:
        print("    (" + name + ": " + text.splitlines()[0][:120] + " " + str(d)[:300] + ")")
    return ok, text, d


# ===================================================================================================== E
async def e_extrude(c):
    print("\n== E. extrude_surface")
    await new_part(c)
    s = await mk_sketch(c, "Front", ("line", 0, 0, 40, 0))
    ok, text, d = await tool(c, "extrude_surface", sketch=s, depth=20)
    record("E1 estrusa cieca: linea 40 per 20 mm -> 800 mm2", ok and close(d.get("surface_area_mm2"), 800) and d.get("surface_bodies") == 1,
           f"area {d.get('surface_area_mm2')}, corpi {d.get('surface_bodies')}, {d.get('feature_type')}")
    await new_part(c)
    s = await mk_sketch(c, "Front", ("line", 0, 0, 40, 0))
    ok, text, d = await tool(c, "extrude_surface", sketch=s, depth=20, end_condition="mid_plane")
    record("E2 piano di mezzeria 20 mm totali -> 800 mm2", ok and close(d.get("surface_area_mm2"), 800), f"area {d.get('surface_area_mm2')}")
    await new_part(c)
    s = await mk_sketch(c, "Front", ("line", 0, 0, 40, 0))
    ok, text, d = await tool(c, "extrude_surface", sketch=s, depth=20, depth2=10)
    record("E3 due direzioni 20 + 10 mm -> 1200 mm2", ok and close(d.get("surface_area_mm2"), 1200), f"area {d.get('surface_area_mm2')}")
    await new_part(c)
    s = await mk_sketch(c, "Front", ("line", 0, 0, 40, 0))
    ok, text, d = await tool(c, "extrude_surface", sketch=s, depth=20, draft_angle=10)
    exp = 40 * 20 / math.cos(math.radians(10))
    record("E4 sformo 10 gradi: 40*20/cos(10) = %.2f mm2" % exp, ok and close(d.get("surface_area_mm2"), exp, 0.001), f"area {d.get('surface_area_mm2')}")
    await new_part(c)
    s = await mk_sketch(c, "Front", ("line", 0, 0, 40, 0))
    ok, text, d = await tool(c, "extrude_surface", sketch=s, depth=20, start_offset=10)
    record("E5 partenza spostata di 10 mm: area invariata 800 mm2", ok and close(d.get("surface_area_mm2"), 800), f"area {d.get('surface_area_mm2')}")
    # chiusa + cappa: 2*(20+10)*30 + 20*10 = 2000
    await new_part(c)
    s = await mk_sketch(c, "Front", ("rect", 0, 0, 20, 10))
    ok, text, d = await tool(c, "extrude_surface", sketch=s, depth=30, cap_end=True)
    record("E6 profilo chiuso 20x10, 30 mm, cappa: 2*30*30 + 200 = 2000 mm2", ok and close(d.get("surface_area_mm2"), 2000) and d.get("solid_bodies") == 0,
           f"area {d.get('surface_area_mm2')}, solidi {d.get('solid_bodies')}")
    # due cappe -> solido 20*10*40 = 8000
    await new_part(c)
    s = await mk_sketch(c, "Front", ("rect", 0, 0, 20, 10))
    ok, text, d = await tool(c, "extrude_surface", sketch=s, depth=30, depth2=10, cap_end=True, cap_end2=True)
    record("E7 due cappe: la superficie chiusa diventa un SOLIDO di 20*10*40 = 8000 mm3", ok and d.get("solid_bodies") == 1 and close(d.get("volume_mm3"), 8000),
           f"solidi {d.get('solid_bodies')}, volume {d.get('volume_mm3')}")
    # fino alla superficie: scatola 50, linea 40 sulla faccia X=0, faccia di arresto X=50 -> 40*50 = 2000
    await new_part(c)
    b = await mk_sketch(c, "Front", ("rect", 0, 0, 50, 50))
    await c.call("extrude_boss", sketch=b, depth=50)
    s = await mk_sketch(c, "Front", ("line", 5, 10, 45, 10))
    ok, text, d = await tool(c, "extrude_surface", sketch=s, end_condition="up_to_surface", up_to_face_point=[50, 25, 25])
    record("E8 fino alla faccia X=50: 40*50 = 2000 mm2", ok and close(d.get("surface_area_mm2"), 2000), f"area {d.get('surface_area_mm2')}")
    ok, text, d = await tool(c, "extrude_surface", sketch=s, end_condition="up_to_surface")
    record("E9 up_to_surface senza punto: errore chiaro", not ok and "up_to_face_point" in text, text.splitlines()[0][:90])
    # passante in entrambe le direzioni dal piano X=20 dentro la scatola: 40*50 = 2000
    await new_part(c)
    b = await mk_sketch(c, "Front", ("rect", 0, 0, 50, 50))
    await c.call("extrude_boss", sketch=b, depth=50)
    pl = await offset_plane(c, 20)
    s = await mk_sketch(c, pl, ("line", 5, 10, 45, 10))
    ok, text, d = await tool(c, "extrude_surface", sketch=s, end_condition="through_all_both")
    record("E10 passante in entrambe le direzioni dentro la scatola 50: 40*50 = 2000 mm2", ok and close(d.get("surface_area_mm2"), 2000), f"area {d.get('surface_area_mm2')}")
    ok, text, d = await tool(c, "extrude_surface", sketch=s, end_condition="through_all")
    record("E11 passante in una direzione dal piano X=20: 40*30 = 1200 mm2", ok and close(d.get("surface_area_mm2"), 1200), f"area {d.get('surface_area_mm2')}")


# ===================================================================================================== R
async def r_revolve(c):
    print("\n== R. revolve_surface")

    async def prep():
        await new_part(c)
        return await mk_sketch(c, "Front", ("line", 10, 0, 10, 30), ("center", 0, 0, 0, 40))
    full = 2 * math.pi * 10 * 30
    s = await prep()
    ok, text, d = await tool(c, "revolve_surface", sketch=s, angle=360)
    record("R1 360 gradi: 2*pi*10*30 = %.1f mm2" % full, ok and close(d.get("surface_area_mm2"), full, 0.001) and d.get("axis_kind") == "sketch_centerline",
           f"area {d.get('surface_area_mm2')}, asse {d.get('axis_kind')}")
    s = await prep()
    ok, text, d = await tool(c, "revolve_surface", sketch=s, angle=90)
    record("R2 90 gradi: %.2f mm2" % (full / 4), ok and close(d.get("surface_area_mm2"), full / 4, 0.001), f"area {d.get('surface_area_mm2')}")
    s = await prep()
    ok, text, d = await tool(c, "revolve_surface", sketch=s, angle=90, direction="two_directions", angle2=60)
    record("R3 due direzioni 90 + 60 = 150 gradi: %.2f mm2" % (full * 150 / 360), ok and close(d.get("surface_area_mm2"), full * 150 / 360, 0.001), f"area {d.get('surface_area_mm2')}")
    s = await prep()
    ok, text, d = await tool(c, "revolve_surface", sketch=s, angle=90, direction="mid_plane")
    record("R4 piano di mezzeria 90 gradi totali: %.2f mm2" % (full / 4), ok and close(d.get("surface_area_mm2"), full / 4, 0.001), f"area {d.get('surface_area_mm2')}")
    # asse indicato con l'id del segmento (linea di costruzione)
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_line", x1=10, y1=0, x2=10, y2=30)
    ok2, t2, d2 = await c.call("draw_centerline_axis", x1=0, y1=0, x2=0, y2=40)
    ax = d2.get("entity_id")
    ok3, _, _ = await c.call("close_sketch")
    s = await last_sketch(c)
    ok, text, d = await tool(c, "revolve_surface", sketch=s, angle=180, axis=ax)
    record("R5 asse con l'id del segmento (%s), 180 gradi: %.2f mm2" % (ax, full / 2), ok and close(d.get("surface_area_mm2"), full / 2, 0.001) and d.get("axis_kind") == "sketch_segment",
           f"area {d.get('surface_area_mm2')}, asse {d.get('axis_kind')}")
    s = await prep()
    ok, text, d = await tool(c, "revolve_surface", sketch=s, direction="two_directions")
    record("R6 two_directions senza angle2: errore chiaro", not ok and "angle2" in text, text.splitlines()[0][:90])


# ===================================================================================================== W
async def w_sweep(c):
    print("\n== W. sweep_surface")

    async def prep(guide=False, circle=False):
        await new_part(c)
        prof = await mk_sketch(c, "Top", ("circle", 0, 0, 5) if circle else ("line", 0, 0, 10, 0))
        path = await mk_sketch(c, "Front", ("line", 0, 0, 0, 50))
        g = await mk_sketch(c, "Front", ("line", 10, 0, 10, 50)) if guide else None
        return prof, path, g
    prof, path, _ = await prep()
    ok, text, d = await tool(c, "sweep_surface", profile_sketch=prof, path_sketch=path)
    record("W1 linea 10 mm lungo un percorso retto di 50 mm -> 500 mm2", ok and close(d.get("surface_area_mm2"), 500), f"area {d.get('surface_area_mm2')}, {d.get('feature_type')}")
    prof, path, g = await prep(guide=True)
    ok, text, d = await tool(c, "sweep_surface", profile_sketch=prof, path_sketch=path, guide_sketches=[g])
    record("W2 con una curva guida parallela -> 500 mm2", ok and close(d.get("surface_area_mm2"), 500), f"area {d.get('surface_area_mm2')}")
    # torsione costante 90 gradi: 50 * integrale_0^10 sqrt(1 + k^2 r^2) dr, k = (pi/2)/50
    k = (math.pi / 2) / 50
    n = 2000
    h = 10.0 / n
    integ = sum((1 if i in (0, n) else 4 if i % 2 else 2) * math.sqrt(1 + (k * i * h) ** 2) for i in range(n + 1)) * h / 3
    exp = 50 * integ
    prof, path, _ = await prep()
    ok, text, d = await tool(c, "sweep_surface", profile_sketch=prof, path_sketch=path, twist_angle=90)
    record("W3 torsione 90 gradi lungo 50 mm: elicoide %.2f mm2" % exp, ok and close(d.get("surface_area_mm2"), exp, 0.001), f"area {d.get('surface_area_mm2')}, {d.get('twist_control')}")
    prof, path, _ = await prep(circle=True)
    ok, text, d = await tool(c, "sweep_surface", profile_sketch=prof, path_sketch=path)
    record("W4 cerchio r5 lungo 50 mm: 2*pi*5*50 = %.1f mm2" % (2 * math.pi * 250), ok and close(d.get("surface_area_mm2"), 2 * math.pi * 250, 0.001), f"area {d.get('surface_area_mm2')}")
    prof, path, _ = await prep()
    ok, text, d = await tool(c, "sweep_surface", path_sketch=path, circular_diameter=10)
    record("W5 solo percorso + circular_diameter 10: tubo %.1f mm2" % (2 * math.pi * 250), ok and close(d.get("surface_area_mm2"), 2 * math.pi * 250, 0.001), f"area {d.get('surface_area_mm2')}")
    ok, text, d = await tool(c, "sweep_surface", path_sketch="Inesistente", circular_diameter=10)
    record("W6 percorso inesistente: errore chiaro", not ok and "non trovato" in text, text.splitlines()[0][:90])


# ===================================================================================================== L
async def l_loft(c):
    print("\n== L. loft_surface")
    await new_part(c)
    s1 = await mk_sketch(c, "Front", ("line", 0, 0, 40, 0))
    pl = await offset_plane(c, 30)
    s2 = await mk_sketch(c, pl, ("line", 0, 0, 40, 0))
    ok, text, d = await tool(c, "loft_surface", profile_sketches=[s1, s2])
    record("L1 due linee parallele 40 mm a 30 mm -> 1200 mm2", ok and close(d.get("surface_area_mm2"), 1200), f"area {d.get('surface_area_mm2')}, {d.get('feature_type')}")
    await new_part(c)
    s1 = await mk_sketch(c, "Front", ("line", 0, 0, 40, 0))
    pl = await offset_plane(c, 30)
    s2 = await mk_sketch(c, pl, ("line", 0, 0, 40, 0))
    g1 = await mk_sketch(c, "Top", ("line", 0, 0, 0, -30))
    g2 = await mk_sketch(c, "Top", ("line", 40, 0, 40, -30))
    ok, text, d = await tool(c, "loft_surface", profile_sketches=[s1, s2], guide_sketches=[g1, g2])
    record("L2 con due guide rettilinee -> 1200 mm2", ok and close(d.get("surface_area_mm2"), 1200), f"area {d.get('surface_area_mm2')}")
    # chiuso: tre linee parallele (lunghe 40) ai vertici di un triangolo A(X0,Z0) B(X30,Z0) C(X15,Z26): la chiusura aggiunge la striscia C->A
    await new_part(c)
    a = await mk_sketch(c, "Front", ("line", 0, 0, 40, 0))
    p30 = await offset_plane(c, 30)
    b = await mk_sketch(c, p30, ("line", 0, 0, 40, 0))
    p15 = await offset_plane(c, 15)
    cc = await mk_sketch(c, p15, ("line", 0, 26, 40, 26))
    ok1, _, d1 = await tool(c, "loft_surface", profile_sketches=[a, b, cc])
    await new_part(c)
    a = await mk_sketch(c, "Front", ("line", 0, 0, 40, 0))
    p30 = await offset_plane(c, 30)
    b = await mk_sketch(c, p30, ("line", 0, 0, 40, 0))
    p15 = await offset_plane(c, 15)
    cc = await mk_sketch(c, p15, ("line", 0, 26, 40, 26))
    ok2, _, d2 = await tool(c, "loft_surface", profile_sketches=[a, b, cc], closed=True)
    a1, a2 = d1.get("surface_area_mm2") or 0, d2.get("surface_area_mm2") or 0
    record("L3 loft chiuso su tre linee: l'area chiusa supera quella aperta (aperta %.1f, chiusa %.1f; striscia C->A ~ 40*30 = 1200 mm2)" % (a1, a2),
           ok1 and ok2 and a2 > a1 + 800, f"aperta {a1}, chiusa {a2}")
    ok, text, d = await tool(c, "loft_surface", profile_sketches=["Schizzo1"])
    record("L4 un solo profilo: errore chiaro", not ok and "almeno 2" in text, text.splitlines()[0][:90])


# ===================================================================================================== P
async def p_planar(c):
    print("\n== P. planar_surface")
    await new_part(c)
    s = await mk_sketch(c, "Front", ("circle", 0, 0, 10))
    ok, text, d = await tool(c, "planar_surface", sketch=s)
    record("P1 da cerchio r=10: pi*100 = %.2f mm2" % (math.pi * 100), ok and close(d.get("surface_area_mm2"), math.pi * 100, 0.001), f"area {d.get('surface_area_mm2')}, {d.get('feature_type')}")
    # tubo aperto 20x10 lungo 30 (X 0..30) e piana sui 4 spigoli dell'estremita' X=30
    await new_part(c)
    s = await mk_sketch(c, "Front", ("rect", 0, 0, 20, 10))
    await tool(c, "extrude_surface", sketch=s, depth=30)
    loop = [[30, 10, 0], [30, 20, 5], [30, 10, 10], [30, 0, 5]]
    ok, text, d = await tool(c, "planar_surface", edge_points=loop)
    record("P2 da 4 spigoli chiusi (estremita' di un tubo 20x10): 200 mm2", ok and close(d.get("surface_area_mm2"), 200) and d.get("surface_bodies") == 2 and close(d.get("total_surface_area_mm2"), 1800 + 200),
           f"area {d.get('surface_area_mm2')}, corpi {d.get('surface_bodies')}, totale {d.get('total_surface_area_mm2')}")
    ok, text, d = await tool(c, "planar_surface", edge_points=[[99, 99, 99]])
    record("P3 punto non sullo spigolo: errore chiaro", not ok and "entro" in text, text.splitlines()[0][:100])


# ===================================================================================================== B
async def b_boundary(c):
    print("\n== B. boundary_feature")
    await new_part(c)
    s1 = await mk_sketch(c, "Front", ("line", 0, 0, 40, 0))
    pl = await offset_plane(c, 30)
    s2 = await mk_sketch(c, pl, ("line", 0, 0, 40, 0))
    ok, text, d = await tool(c, "boundary_feature", curves1=[s1, s2])
    record("B1 superficie fra due linee 40 mm a 30 mm -> 1200 mm2", ok and close(d.get("surface_area_mm2"), 1200) and d.get("surface_bodies") == 1, f"area {d.get('surface_area_mm2')}, {d.get('feature_type')}")
    await new_part(c)
    s1 = await mk_sketch(c, "Front", ("line", 0, 0, 40, 0))
    pl = await offset_plane(c, 30)
    s2 = await mk_sketch(c, pl, ("line", 0, 0, 40, 0))
    t1 = await mk_sketch(c, "Top", ("line", 0, 0, 0, -30))
    t2 = await mk_sketch(c, "Top", ("line", 40, 0, 40, -30))
    ok, text, d = await tool(c, "boundary_feature", curves1=[s1, s2], curves2=[t1, t2])
    record("B2 con curve in direzione 2: patch rettangolare 40x30 = 1200 mm2", ok and close(d.get("surface_area_mm2"), 1200), f"area {d.get('surface_area_mm2')}")
    await new_part(c)
    s1 = await mk_sketch(c, "Front", ("circle", 0, 0, 10))
    pl = await offset_plane(c, 30)
    s2 = await mk_sketch(c, pl, ("circle", 0, 0, 10))
    ok, text, d = await tool(c, "boundary_feature", curves1=[s1, s2])
    exp = 2 * math.pi * 10 * 30
    record("B3 superficie fra due cerchi r10 a 30 mm: %.1f mm2" % exp, ok and close(d.get("surface_area_mm2"), exp, 0.002), f"area {d.get('surface_area_mm2')}")
    await new_part(c)
    s1 = await mk_sketch(c, "Front", ("rect", 0, 0, 40, 20))
    pl = await offset_plane(c, 30)
    s2 = await mk_sketch(c, pl, ("rect", 0, 0, 40, 20))
    ok, text, d = await tool(c, "boundary_feature", curves1=[s1, s2], kind="boss")
    record("B4 boss fra due rettangoli 40x20 a 30 mm: volume 24000 mm3", ok and d.get("solid_bodies") == 1 and close(d.get("volume_mm3"), 24000, 0.001), f"volume {d.get('volume_mm3')}, {d.get('feature_type')}")
    await new_part(c)
    s1 = await mk_sketch(c, "Front", ("circle", 0, 0, 10))
    pl = await offset_plane(c, 30)
    s2 = await mk_sketch(c, pl, ("circle", 0, 0, 10))
    ok, text, d = await tool(c, "boundary_feature", curves1=[s1, s2], kind="boss")
    exp = math.pi * 100 * 30
    record("B5 boss fra due cerchi r10 a 30 mm: pi*100*30 = %.1f mm3" % exp, ok and close(d.get("volume_mm3"), exp, 0.002), f"volume {d.get('volume_mm3')}")
    # taglio: scatola X 0..40, Y 0..60, Z 0..60 (144000), cilindro boundary r10 fra X=10 e X=30 centrato in Y=30,Z=30
    await new_part(c)
    b = await mk_sketch(c, "Front", ("rect", 0, 0, 60, 60))
    await c.call("extrude_boss", sketch=b, depth=40)
    p10 = await offset_plane(c, 10)
    s1 = await mk_sketch(c, p10, ("circle", 30, 30, 10))
    p30 = await offset_plane(c, 30)
    s2 = await mk_sketch(c, p30, ("circle", 30, 30, 10))
    ok, text, d = await tool(c, "boundary_feature", curves1=[s1, s2], kind="cut")
    exp = -math.pi * 100 * 20
    record("B6 taglio boundary: volume %.1f mm3 (da 144000)" % exp, ok and close(d.get("volume_delta_mm3"), exp, 0.003) and close(d.get("volume_mm3"), 144000 + exp, 0.001),
           f"delta {d.get('volume_delta_mm3')}, volume {d.get('volume_mm3')}, {d.get('feature_type')}")
    ok, text, d = await tool(c, "boundary_feature", curves1=[s1])
    record("B7 una sola curva: errore chiaro", not ok and "almeno 2" in text, text.splitlines()[0][:90])
    await new_part(c)
    s1 = await mk_sketch(c, "Front", ("circle", 0, 0, 10))
    pl = await offset_plane(c, 30)
    s2 = await mk_sketch(c, pl, ("circle", 0, 0, 10))
    ok, text, d = await tool(c, "boundary_feature", curves1=[s1, s2], kind="cut")
    record("B8 taglio senza solido: errore chiaro", not ok and "solido" in text, text.splitlines()[0][:90])


# ===================================================================================================== U
async def u_ruled(c):
    print("\n== U. ruled_surface")

    async def box():
        await new_part(c)
        s = await mk_sketch(c, "Front", ("rect", 0, 0, 40, 30))
        await c.call("extrude_boss", sketch=s, depth=20)
    # scatola X 0..20, Y 0..40, Z 0..30: spigolo di 40 mm a (X=20,Z=30), punto [20,20,30]
    await box()
    ok, text, d = await tool(c, "ruled_surface", edge_points=[[20, 20, 30]], distance=5)
    record("U1 tangente, spigolo 40 mm, distanza 5 -> 200 mm2", ok and close(d.get("surface_area_mm2"), 200) and d.get("surface_bodies") == 1, f"area {d.get('surface_area_mm2')}, {d.get('feature_type')}")
    await box()
    ok, text, d = await tool(c, "ruled_surface", edge_points=[[20, 20, 30]], distance=5, reverse=True)
    record("U2 tangente con reverse -> 200 mm2", ok and close(d.get("surface_area_mm2"), 200), f"area {d.get('surface_area_mm2')}")
    await box()
    ok, text, d = await tool(c, "ruled_surface", edge_points=[[20, 20, 30]], ruled_type="perpendicular_to_vector", vector=[0, 0, 1], distance=5)
    record("U3 perpendicolare al vettore Z, distanza 5 -> 200 mm2", ok and close(d.get("surface_area_mm2"), 200), f"area {d.get('surface_area_mm2')}")
    # cilindro r10 lungo 20 (X 0..20): spigolo circolare in X=20, punto [20,10,0]
    await new_part(c)
    s = await mk_sketch(c, "Front", ("circle", 0, 0, 10))
    await c.call("extrude_boss", sketch=s, depth=20)
    ok, text, d = await tool(c, "ruled_surface", edge_points=[[20, 10, 0]], ruled_type="normal", distance=5)
    exp = math.pi * (15 ** 2 - 10 ** 2)
    record("U4 normale alla superficie su un bordo circolare r10, distanza 5: corona %.1f mm2" % exp, ok and close(d.get("surface_area_mm2"), exp, 0.002), f"area {d.get('surface_area_mm2')}")
    await new_part(c)
    s = await mk_sketch(c, "Front", ("circle", 0, 0, 10))
    await c.call("extrude_boss", sketch=s, depth=20)
    ok, text, d = await tool(c, "ruled_surface", edge_points=[[20, 10, 0]], ruled_type="tangent", distance=5)
    exp = 2 * math.pi * 10 * 5
    record("U5 tangente sul bordo circolare r10, distanza 5: %.1f mm2" % exp, ok and close(d.get("surface_area_mm2"), exp, 0.002), f"area {d.get('surface_area_mm2')}")
    ok, text, d = await tool(c, "ruled_surface", edge_points=[[20, 10, 0]], ruled_type="tapered_to_vector", vector=[1, 0, 0])
    record("U6 rastremata: dichiarata non supportata", not ok and "non e' supportato" in text, text.splitlines()[0][:90])
    ok, text, d = await tool(c, "ruled_surface", edge_points=[[20, 10, 0]], ruled_type="perpendicular_to_vector")
    record("U7 perpendicolare senza vettore: errore chiaro", not ok and "vector" in text, text.splitlines()[0][:90])


# ===================================================================================================== F
async def f_fill(c):
    print("\n== F. fill_surface")

    async def tube(cap):
        await new_part(c)
        s = await mk_sketch(c, "Front", ("rect", 0, 0, 20, 10))
        await tool(c, "extrude_surface", sketch=s, depth=30, cap_end=cap)
    loop30 = [[30, 10, 0], [30, 20, 5], [30, 10, 10], [30, 0, 5]]
    loop0 = [[0, 10, 0], [0, 20, 5], [0, 10, 10], [0, 0, 5]]
    side = [[15, 10, 0], [15, 20, 5], [15, 10, 10], [15, 0, 5]]
    await tube(False)
    ok, text, d = await tool(c, "fill_surface", edge_points=loop30)
    record("F1 patch sull'estremita' di un tubo 20x10: 200 mm2, corpo separato", ok and close(d.get("surface_area_mm2"), 200) and d.get("surface_bodies") == 2,
           f"area {d.get('surface_area_mm2')}, corpi {d.get('surface_bodies')}, {d.get('feature_type')}")
    await tube(True)
    ok, text, d = await tool(c, "fill_surface", edge_points=loop0, merge_result=True)
    record("F2 patch unita' al tubo (cappa gia' presente): un solo corpo da 2000 + 200 = 2200 mm2, nessun solido", ok and d.get("surface_bodies") == 1 and close(d.get("total_surface_area_mm2"), 2200) and d.get("solid_bodies") == 0,
           f"corpi {d.get('surface_bodies')}, totale {d.get('total_surface_area_mm2')}, solidi {d.get('solid_bodies')}")
    await tube(True)
    ok, text, d = await tool(c, "fill_surface", edge_points=loop0, merge_result=True, form_solid=True)
    record("F3 chiude il buco e forma il SOLIDO 20*10*30 = 6000 mm3 (patch 200 mm2)", ok and d.get("solid_bodies") == 1 and d.get("surface_bodies") == 0 and close(d.get("volume_mm3"), 6000) and close(d.get("surface_area_mm2"), 200),
           f"solidi {d.get('solid_bodies')}, volume {d.get('volume_mm3')}, patch {d.get('surface_area_mm2')}")
    await tube(True)
    ok, text, d = await tool(c, "fill_surface", edge_points=loop0, continuity="tangent", face_points=side, merge_result=True)
    record("F4 continuita' tangente con le facce adiacenti: patch piana 200 mm2, totale 2200 mm2", ok and close(d.get("total_surface_area_mm2"), 2200) and close(d.get("surface_area_mm2"), 200),
           f"area {d.get('surface_area_mm2')}, totale {d.get('total_surface_area_mm2')}, continuita' {d.get('continuity')}")
    ok, text, d = await tool(c, "fill_surface", edge_points=loop0, continuity="tangent")
    record("F5 tangente senza face_points: errore chiaro", not ok and "face_points" in text, text.splitlines()[0][:90])


# ===================================================================================================== run
async def scenario(c):
    only = {a.upper() for a in sys.argv[1:]}
    sezioni = [("E", e_extrude), ("R", r_revolve), ("W", w_sweep), ("L", l_loft), ("P", p_planar), ("B", b_boundary),
               ("U", u_ruled), ("F", f_fill)]
    for nome, fn in sezioni:
        if not only or nome in only:
            try:
                await fn(c)
            except Exception as e:                                          # un errore in una sezione non ferma le altre
                import traceback
                traceback.print_exc()
                record(f"{nome} eccezione nel test", False, repr(e)[:150])
            await c.call("close_document", discard=True)


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
                print(text[:160])
                if not ok or not my_pid or my_pid in elia_pids or my_pid not in sw_pids():
                    print("STOP: nessuna istanza separata ottenibile. Nulla e' stato toccato.")
                    return False
                record("PID dedicato diverso dall'istanza utente", my_pid not in elia_pids, str(my_pid))
                await scenario(c)
    finally:
        cleanup(my_pid, elia_pids)
    return True


if __name__ == "__main__":
    done = asyncio.run(run())
    print("\n==== RIEPILOGO ====")
    for tool_name, res, note in RESULTS:
        print(f"{res:5} {tool_name:70} {note}"[:230])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
