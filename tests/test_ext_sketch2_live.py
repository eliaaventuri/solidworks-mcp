"""
Test live del lotto SCHIZZO 2 (tool di schizzo nuovi: taglia, estendi, smusso, ripetizioni, trasformazioni, entita' nuove,
schizzo 3D) tramite il server MCP (stdio). Ogni numero e' MISURATO (geometria riletta con list_sketch_entities, volume) e
confrontato con un valore calcolato a mano.

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated); alla fine si chiude solo il PID del test.

  S1  trim_sketch_entities (power, outside, inside, corner) + extend_sketch_entity
  S2  sketch_chamfer (distanza-distanza, uguale, distanza-angolo, vertice)
  S3  sketch_linear_pattern / sketch_circular_pattern
  S4  transform_sketch_entities (sposta, ruota, scala, copie)
  S5  entita' nuove: rettangoli, parallelogramma, arco tangente, parabola, curva da equazione
  S6  schizzo 3D: polilinea come percorso di uno sweep (volume), spline e punto 3D

Uso:  .venv\\Scripts\\python.exe tests\\test_ext_sketch2_live.py [S1 S4 ...]
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


def near(a, b, tol=0.01):
    return all(abs(x - y) <= tol for x, y in zip(a, b)) and len(a) == len(b)


async def new_sketch(c, plane="Front"):
    await c.call("close_document", discard=True)
    ok, text, _ = await c.call("create_new_part")
    assert ok, text
    ok, text, _ = await c.call("create_sketch", plane=plane)
    assert ok, text


async def segs(c):
    ok, _, d = await c.call("list_sketch_entities")
    return d.get("segments", []) if ok else []


def lines(ss):
    return sorted([tuple(round(v, 3) for v in (s["start_mm"] + s["end_mm"])) for s in ss if s["type"] == "line" and not s.get("construction")])


def key_line(a, b):
    """Linea come coppia di estremi senza ordine."""
    p, q = tuple(a), tuple(b)
    return tuple(sorted([p, q]))


def has_line(ss, a, b, tol=0.01):
    for s in ss:
        if s["type"] != "line":
            continue
        st, en = s["start_mm"], s["end_mm"]
        if (near(st, a, tol) and near(en, b, tol)) or (near(st, b, tol) and near(en, a, tol)):
            return True
    return False


# ===================================================================================================== S1
async def s1_trim_extend(c):
    print("\n== S1. trim_sketch_entities / extend_sketch_entity")
    # power trim: orizzontale 0..40 + verticale a x=20, clic su (30,0) -> resta 0..20
    await new_sketch(c)
    await c.call("draw_line", x1=0, y1=0, x2=40, y2=0)
    await c.call("draw_line", x1=20, y1=-10, x2=20, y2=10)
    ok, text, d = await c.call("trim_sketch_entities", mode="power", entity="@30,0", point=[30, 0])
    ss = await segs(c)
    record("S1 power trim: orizzontale 0..40 cliccata in (30,0) -> resta 0..20", ok and has_line(ss, [0, 0], [20, 0])
           and has_line(ss, [20, -10], [20, 10]) and len(ss) == 2,
           f"segmenti {lines(ss)}; {text.splitlines()[0][:70]}")
    # power trim sul lato sinistro del tratto che resta: nessun'altra intersezione a sinistra -> cancellato
    ok, text, d = await c.call("trim_sketch_entities", mode="power", entity="@5,0", point=[5, 0])
    ss = await segs(c)
    record("S1 power trim su un tratto con una sola intersezione: l'orizzontale scompare, la verticale resta",
           ok and len(ss) == 1 and has_line(ss, [20, -10], [20, 10]), f"segmenti {lines(ss)}")
    # rifiuto: punto che non cambia nulla (nessuna entita' vicina) -> errore chiaro
    ok, text, d = await c.call("trim_sketch_entities", mode="power", entity="S0-9-9", point=[0, 0])
    record("S1 trim su entita' inesistente: rifiutato con messaggio", not ok, text.splitlines()[0][:90])

    # outside / inside
    await new_sketch(c)
    await c.call("draw_line", x1=0, y1=0, x2=40, y2=0)
    await c.call("draw_line", x1=10, y1=-10, x2=10, y2=10)
    await c.call("draw_line", x1=30, y1=-10, x2=30, y2=10)
    ok, text, d = await c.call("trim_sketch_entities", mode="outside", entity="@20,0", boundaries=["@10,5", "@30,5"])
    ss = await segs(c)
    record("S1 trim outside: orizzontale 0..40 fra i confini x=10 e x=30 -> resta 10..30", ok and has_line(ss, [10, 0], [30, 0]) and len(ss) == 3,
           f"segmenti {lines(ss)}")
    await new_sketch(c)
    await c.call("draw_line", x1=0, y1=0, x2=40, y2=0)
    await c.call("draw_line", x1=10, y1=-10, x2=10, y2=10)
    await c.call("draw_line", x1=30, y1=-10, x2=30, y2=10)
    ok, text, d = await c.call("trim_sketch_entities", mode="inside", entity="@20,0", boundaries=["@10,5", "@30,5"])
    ss = await segs(c)
    record("S1 trim inside: restano 0..10 e 30..40", ok and has_line(ss, [0, 0], [10, 0]) and has_line(ss, [30, 0], [40, 0]) and len(ss) == 4,
           f"segmenti {lines(ss)}")
    # corner
    await new_sketch(c)
    await c.call("draw_line", x1=0, y1=0, x2=40, y2=0)
    await c.call("draw_line", x1=20, y1=-10, x2=20, y2=10)
    ok, text, d = await c.call("trim_sketch_entities", mode="corner", entity="@30,0", entity2="@20,5")
    ss = await segs(c)
    pts = [tuple(s["start_mm"]) for s in ss] + [tuple(s["end_mm"]) for s in ss]
    record("S1 trim corner: le due linee restano 2 e si incontrano nel punto (20,0)",
           ok and len(ss) == 2 and sum(1 for p in pts if near(p, (20, 0))) == 2, f"segmenti {lines(ss)}")
    # extend
    await new_sketch(c)
    await c.call("draw_line", x1=0, y1=0, x2=30, y2=0)
    await c.call("draw_line", x1=40, y1=-10, x2=40, y2=10)
    ok, text, d = await c.call("extend_sketch_entity", entity="@10,0", point=[28, 0])
    ss = await segs(c)
    record("S1 extend: orizzontale 0..30 fino alla verticale x=40 -> estremo misurato (40,0)", ok and has_line(ss, [0, 0], [40, 0]),
           f"segmenti {lines(ss)}")
    await new_sketch(c)
    await c.call("draw_line", x1=10, y1=0, x2=30, y2=0)
    await c.call("draw_line", x1=0, y1=-10, x2=0, y2=10)
    ok, text, d = await c.call("extend_sketch_entity", entity="@20,0", point=[12, 0])
    ss = await segs(c)
    record("S1 extend dal lato sinistro: 10..30 fino a x=0 -> 0..30", ok and has_line(ss, [0, 0], [30, 0]), f"segmenti {lines(ss)}")
    ok, text, d = await c.call("extend_sketch_entity", entity="@20,0", point=[28, 0])
    record("S1 extend senza nulla da raggiungere: rifiutato", not ok, text.splitlines()[0][:90])


# ===================================================================================================== S2
async def s2_chamfer(c):
    print("\n== S2. sketch_chamfer")

    async def corner_sketch():
        await new_sketch(c)
        await c.call("draw_line", x1=0, y1=0, x2=40, y2=0)
        await c.call("draw_line", x1=40, y1=0, x2=40, y2=30)

    await corner_sketch()
    ok, text, d = await c.call("sketch_chamfer", entity1="@20,0", entity2="@40,15", mode="distance_distance", distance=5, distance2=10)
    ss = await segs(c)
    record("S2 smusso 5 x 10: lato dello smusso = sqrt(125) = 11.1803 mm", ok and abs(d.get("chamfer_length_mm", 0) - math.sqrt(125)) < 0.001,
           f"misurato {d.get('chamfer_length_mm')} mm, tagli {d.get('legs_mm')}")
    record("S2 ...tagli 5 mm sulla prima linea e 10 mm sulla seconda; estremi (35,0)-(40,10)",
           ok and d.get("legs_mm") == [5.0, 10.0] and has_line(ss, [35, 0], [40, 10]) and has_line(ss, [0, 0], [35, 0]) and has_line(ss, [40, 10], [40, 30]),
           f"segmenti {lines(ss)}")
    await corner_sketch()
    ok, text, d = await c.call("sketch_chamfer", entity1="@20,0", entity2="@40,15", mode="equal", distance=4)
    record("S2 smusso uguale 4: lato 4*sqrt(2) = 5.6569 mm", ok and abs(d.get("chamfer_length_mm", 0) - 4 * math.sqrt(2)) < 0.001,
           f"misurato {d.get('chamfer_length_mm')} mm, tagli {d.get('legs_mm')}")
    await corner_sketch()
    ok, text, d = await c.call("sketch_chamfer", entity1="@20,0", entity2="@40,15", mode="distance_angle", distance=6, angle=30)
    exp = [6.0, 6 * math.tan(math.radians(30))]
    record("S2 smusso distanza 6 + angolo 30: tagli 6 e 6*tan30 = 3.4641, lato 6/cos30 = 6.9282 mm",
           ok and near(d.get("legs_mm", []), exp, 0.001) and abs(d.get("chamfer_length_mm", 0) - 6 / math.cos(math.radians(30))) < 0.001,
           f"misurato tagli {d.get('legs_mm')}, lato {d.get('chamfer_length_mm')}")
    await corner_sketch()
    ok, text, d = await c.call("sketch_chamfer", corner=[40, 0], distance=3)
    record("S2 smusso indicando il vertice [40,0]: 3 x 3 -> lato 4.2426 mm", ok and abs(d.get("chamfer_length_mm", 0) - 3 * math.sqrt(2)) < 0.001,
           f"misurato {d.get('chamfer_length_mm')} mm")
    ok, text, d = await c.call("sketch_chamfer", corner=[0, 0], distance=3)
    record("S2 vertice con una sola linea: rifiutato", not ok, text.splitlines()[0][:90])
    await c.call("close_document", discard=True)


# ===================================================================================================== S3
def is_circle(s):
    return s["type"] == "arc" and near(s["start_mm"], s["end_mm"], 1e-6)


def circles(ss):
    return sorted([tuple(round(v, 3) for v in s["center_mm"][:2]) for s in ss if is_circle(s)])


async def s3_patterns(c):
    print("\n== S3. sketch_linear_pattern / sketch_circular_pattern")
    await new_sketch(c)
    await c.call("draw_circle", x=0, y=0, radius=2)
    ok, text, d = await c.call("sketch_linear_pattern", entities=["@2,0"], count_x=4, spacing_x=10)
    cs = circles(await segs(c))
    record("S3 ripetizione lineare 4 cerchi passo 10: 4 cerchi, ultimo a (30,0)", ok and len(cs) == 4 and cs[-1] == (30.0, 0.0), f"cerchi {cs}")
    await new_sketch(c)
    await c.call("draw_circle", x=0, y=0, radius=2)
    ok, text, d = await c.call("sketch_linear_pattern", entities=["@2,0"], count_x=3, spacing_x=10, count_y=2, spacing_y=8)
    cs = circles(await segs(c))
    record("S3 ripetizione lineare 3x2 (passi 10 e 8): 6 cerchi, ultimo a (20,8)", ok and len(cs) == 6 and (20.0, 8.0) in cs and (0.0, 8.0) in cs,
           f"cerchi {cs}")
    await new_sketch(c)
    await c.call("draw_circle", x=0, y=0, radius=2)
    ok, text, d = await c.call("sketch_linear_pattern", entities=["@2,0"], count_x=3, spacing_x=10, angle_x=30)
    cs = circles(await segs(c))
    record("S3 ripetizione lineare a 30 gradi: ultimo cerchio a (17.3205, 10)", ok and len(cs) == 3 and near(cs[-1] if cs[-1][1] > 9 else cs[0], (17.321, 10.0), 0.01),
           f"cerchi {cs}")
    await new_sketch(c)
    await c.call("draw_circle", x=20, y=0, radius=3)
    ok, text, d = await c.call("sketch_circular_pattern", entities=["@23,0"], center=[0, 0], count=4)
    cs = circles(await segs(c))
    exp = {(20.0, 0.0), (0.0, 20.0), (-20.0, 0.0), (0.0, -20.0)}
    record("S3 ripetizione circolare 4 cerchi attorno all'origine: centri a 90 gradi, ultimo a (0,-20)",
           ok and len(cs) == 4 and all(any(near(p, q, 0.01) for q in cs) for p in exp), f"cerchi {cs}; metodo {d.get('method')}")
    await new_sketch(c)
    await c.call("draw_line", x1=20, y1=5, x2=30, y2=9)
    ok, text, d = await c.call("sketch_circular_pattern", entities=["@25,7"], center=[10, 10], count=3, spacing_angle=60)
    ss = await segs(c)
    # linea (20,5)-(30,9) ruotata di 60 e 120 gradi (antiorario) attorno a (10,10)
    def rot(p, a):
        x, y = p[0] - 10, p[1] - 10
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
        return [10 + x * ca - y * sa, 10 + x * sa + y * ca]
    okl = all(has_line(ss, rot((20, 5), a), rot((30, 9), a), 0.01) for a in (60, 120))
    record("S3 ripetizione circolare di una linea, 3 istanze a 60 gradi attorno a (10,10): estremi ruotati", ok and len(ss) == 3 and okl,
           f"segmenti {lines(ss)}")
    await new_sketch(c)
    await c.call("draw_rectangle", x1=10, y1=10, x2=20, y2=16)
    ok, text, d = await c.call("sketch_circular_pattern", entities=["@15,10", "@15,16", "@10,13", "@20,13"], center=[35, 13], count=2, spacing_angle=180)
    ss = await segs(c)
    record("S3 ripetizione circolare del rettangolo (180 gradi attorno a (35,13)): copia 50..60 x 10..16",
           ok and len(ss) == 8 and has_line(ss, [50, 10], [60, 10]) and has_line(ss, [50, 16], [60, 16]) and has_line(ss, [50, 10], [50, 16]),
           f"segmenti {len(ss)}")
    await c.call("close_document", discard=True)


# ===================================================================================================== S4
async def s4_transform(c):
    print("\n== S4. transform_sketch_entities")
    await new_sketch(c)
    await c.call("draw_line", x1=10, y1=10, x2=20, y2=10)
    ok, text, d = await c.call("transform_sketch_entities", operation="move", entities=["@15,10"], dx=5, dy=2)
    ss = await segs(c)
    record("S4 sposta di (5,2): linea 10..20 a y=10 -> (15,12)-(25,12)", ok and has_line(ss, [15, 12], [25, 12]) and len(ss) == 1, f"{lines(ss)}")
    ok, text, d = await c.call("transform_sketch_entities", operation="rotate", entities=["@20,12"], angle=90, center=[15, 12])
    ss = await segs(c)
    record("S4 ruota di 90 attorno a (15,12): (15,12)-(25,12) -> (15,12)-(15,22)", ok and has_line(ss, [15, 12], [15, 22]) and len(ss) == 1, f"{lines(ss)}")
    ok, text, d = await c.call("transform_sketch_entities", operation="scale", entities=["@15,17"], scale=2, center=[15, 12])
    ss = await segs(c)
    record("S4 scala 2 attorno a (15,12): lunghezza 10 -> 20, (15,12)-(15,32)", ok and has_line(ss, [15, 12], [15, 32]) and len(ss) == 1, f"{lines(ss)}")
    ok, text, d = await c.call("transform_sketch_entities", operation="move", entities=["@15,20"], dx=0, dy=10, copy=True, copies=2)
    ss = await segs(c)
    record("S4 sposta con 2 copie di (0,10): 3 linee, ultima (15,32)-(15,52)",
           ok and len(ss) == 3 and has_line(ss, [15, 22], [15, 42]) and has_line(ss, [15, 32], [15, 52]), f"{lines(ss)}")
    await new_sketch(c)
    await c.call("draw_line", x1=10, y1=0, x2=20, y2=0)
    ok, text, d = await c.call("transform_sketch_entities", operation="rotate", entities=["@15,0"], angle=30, center=[0, 0], copy=True, copies=3)
    ss = await segs(c)
    exp = [((10 * math.cos(math.radians(30 * k)), 10 * math.sin(math.radians(30 * k))),
            (20 * math.cos(math.radians(30 * k)), 20 * math.sin(math.radians(30 * k)))) for k in range(4)]
    record("S4 ruota con 3 copie di 30 gradi attorno all'origine: 4 linee, ultima a 90 gradi (0,10)-(0,20)",
           ok and len(ss) == 4 and all(has_line(ss, list(a), list(b), 0.01) for a, b in exp), f"{lines(ss)}")
    await new_sketch(c)
    await c.call("draw_line", x1=10, y1=5, x2=20, y2=5)
    ok, text, d = await c.call("transform_sketch_entities", operation="rotate", entities=["@15,5"], angle=45, center=[5, 5], copy=True, copies=2)
    ss = await segs(c)
    r2 = math.sqrt(0.5)
    record("S4 ruota con 2 copie di 45 gradi attorno a (5,5): la seconda copia e' (5,10)-(5,20)",
           ok and len(ss) == 3 and has_line(ss, [5, 10], [5, 20], 0.01) and has_line(ss, [5 + 5 * r2, 5 + 5 * r2], [5 + 15 * r2, 5 + 15 * r2], 0.01), f"{lines(ss)}")
    await new_sketch(c)
    await c.call("draw_circle", x=10, y=0, radius=2)
    ok, text, d = await c.call("transform_sketch_entities", operation="scale", entities=["@12,0"], scale=2, center=[0, 0], copy=True, copies=2)
    ss = await segs(c)
    got = sorted((round(s["center_mm"][0], 3), round(s["radius_mm"], 3)) for s in ss if is_circle(s))
    record("S4 scala con 2 copie (x2, x4) attorno all'origine: cerchi (10,r2), (20,r4), (40,r8)", ok and got == [(10.0, 2.0), (20.0, 4.0), (40.0, 8.0)], f"{got}")
    await new_sketch(c, "Top")
    await c.call("draw_line", x1=10, y1=5, x2=20, y2=9)
    ok, text, d = await c.call("transform_sketch_entities", operation="rotate", entities=["@15,7"], angle=90, center=[0, 0])
    ss = await segs(c)
    record("S4 rotazione su un piano diverso (Top): (10,5)-(20,9) -> (-5,10)-(-9,20)", ok and has_line(ss, [-5, 10], [-9, 20]), f"{lines(ss)}")
    await c.call("close_document", discard=True)


# ===================================================================================================== S5
def vset(d):
    return sorted((round(p[0], 3), round(p[1], 3)) for p in d.get("vertices_mm", []))


async def s5_entities(c):
    print("\n== S5. entita' nuove")
    await new_sketch(c)
    ok, text, d = await c.call("draw_center_rectangle", cx=5, cy=3, x2=25, y2=13)
    exp = sorted([(-15.0, -7.0), (25.0, -7.0), (-15.0, 13.0), (25.0, 13.0)])
    record("S5 rettangolo da centro (5,3) e angolo (25,13): vertici (-15,-7) (25,-7) (-15,13) (25,13)", ok and vset(d) == exp and len(d.get("entity_ids", [])) == 4,
           f"vertici {vset(d)}, id {d.get('entity_ids')}, costruzione {d.get('construction_ids')}")
    await new_sketch(c)
    ok, text, d = await c.call("draw_3point_rectangle", x1=0, y1=0, x2=20, y2=10, x3=10, y3=25)
    exp = sorted([(0.0, 0.0), (20.0, 10.0), (12.0, 26.0), (-8.0, 16.0)])
    record("S5 rettangolo inclinato da 3 punti: vertici (0,0) (20,10) (12,26) (-8,16)", ok and vset(d) == exp, f"vertici {vset(d)}")
    await new_sketch(c)
    ok, text, d = await c.call("draw_3point_rectangle", x1=0, y1=0, x2=20, y2=0, x3=20, y3=10, center=True)
    exp = sorted([(-20.0, -10.0), (20.0, -10.0), (-20.0, 10.0), (20.0, 10.0)])
    record("S5 rettangolo da 3 punti con centro (0,0), meta' lato (20,0), angolo (20,10): 40 x 20", ok and vset(d) == exp, f"vertici {vset(d)}")
    await new_sketch(c)
    ok, text, d = await c.call("draw_parallelogram", x1=0, y1=0, x2=20, y2=0, x3=30, y3=10)
    exp = sorted([(0.0, 0.0), (20.0, 0.0), (30.0, 10.0), (10.0, 10.0)])
    record("S5 parallelogramma da (0,0) (20,0) (30,10): quarto vertice (10,10)", ok and vset(d) == exp, f"vertici {vset(d)}")
    # arco tangente
    await new_sketch(c)
    await c.call("draw_line", x1=0, y1=5, x2=20, y2=5)
    ok, text, d = await c.call("draw_tangent_arc", x1=20, y1=5, x2=30, y2=15)
    record("S5 arco tangente a fine linea (20,5) fino a (30,15): centro (20,15), raggio 10, tangente (scarto 0)",
           ok and near(d.get("center_mm", [])[:2], (20, 15), 0.001) and abs(d.get("radius_mm", 0) - 10) < 0.001 and d.get("tangent") is True,
           f"centro {d.get('center_mm')}, R {d.get('radius_mm')}, scarto {d.get('tangent_deviation_deg')} gradi")
    ok, text, d = await c.call("draw_tangent_arc", x1=5, y1=5, x2=7, y2=9)
    record("S5 arco tangente da un punto che non e' un estremo: rifiutato o non tangente (nessun host)", (not ok) or d.get("tangent") is None, text.splitlines()[0][:100])
    # parabola
    await new_sketch(c)
    ok, text, d = await c.call("draw_parabola", focus=[0, 5], apex=[0, 0], start=[-10, 5], end=[10, 5])
    ss = await segs(c)
    par = [s for s in ss if s["type"] == "parabola"]
    exp_len = 10 * (math.sqrt(2) + math.asinh(1))                        # 2 * int_0^10 sqrt(1 + (x/10)^2) dx
    record("S5 parabola fuoco (0,5) vertice (0,0) estremi (+-10,5): lunghezza 22.9558 mm, estremi misurati",
           ok and len(par) == 1 and abs(par[0].get("length_mm", 0) - exp_len) < 0.01 and near(par[0]["start_mm"], [-10, 5], 0.001) and near(par[0]["end_mm"], [10, 5], 0.001),
           f"lunghezza {par[0].get('length_mm') if par else None}, atteso {exp_len:.4f}")
    # curve da equazione
    await new_sketch(c)
    ok, text, d = await c.call("draw_equation_curve", y_expression="x^2/20", start=0, end=20)
    p = d.get("points_mm", {})
    record("S5 curva y = x^2/20 con x da 0 a 20: a x=10 (meta' parametro) y = 5, estremo (20,20)",
           ok and near(p.get("mid", []), (10, 5), 0.001) and near(p.get("end", []), (20, 20), 0.001) and max(d.get("endpoint_error_mm", [9])) < 0.001,
           f"punti {p}, scarto estremi {d.get('endpoint_error_mm')}")
    await new_sketch(c)
    ok, text, d = await c.call("draw_equation_curve", x_expression="10*cos(t)", y_expression="10*sin(t)", start=0, end=math.pi)
    p = d.get("points_mm", {})
    record("S5 curva parametrica x=10cos t, y=10sin t, t da 0 a pi: t=0 (10,0), t=pi/2 (0,10), t=pi (-10,0)",
           ok and near(p.get("start", []), (10, 0), 0.001) and near(p.get("mid", []), (0, 10), 0.001) and near(p.get("end", []), (-10, 0), 0.001), f"punti {p}")
    await new_sketch(c)
    ok, text, d = await c.call("draw_equation_curve", y_expression="x^2", start=0, end=4, rotation=90, x_offset=5, y_offset=3)
    p = d.get("points_mm", {})
    record("S5 curva y=x^2, x da 0 a 4, ruotata 90 gradi e spostata di (5,3): inizio (5,3), fine (-11,7)",
           ok and near(p.get("start", []), (5, 3), 0.001) and near(p.get("end", []), (-11, 7), 0.001), f"punti {p}")
    await new_sketch(c)
    ok, text, d = await c.call("draw_equation_curve", y_expression="x", start=0, end=1, unit="inch")
    p = d.get("points_mm", {})
    record("S5 curva y=x con unit=inch, x da 0 a 1: fine a (25.4,25.4) mm", ok and near(p.get("end", []), (25.4, 25.4), 0.001), f"punti {p}")
    ok, text, d = await c.call("draw_equation_curve", y_expression="foo(x", start=0, end=4)
    record("S5 espressione non valida: rifiutata con messaggio", not ok, text.splitlines()[0][:100])
    await c.call("close_document", discard=True)


# ===================================================================================================== S6
async def s6_sketch3d(c):
    print("\n== S6. schizzo 3D")
    await c.call("close_document", discard=True)
    await c.call("create_new_part")
    ok, text, d = await c.call("draw_3d_line", x1=0, y1=0, z1=0, x2=1, y2=1, z2=1)
    record("S6 draw_3d_line senza schizzo 3D: rifiutato", not ok, text.splitlines()[0][:90])
    ok, text, d = await c.call("create_3d_sketch")
    name = d.get("sketch")
    record("S6 create_3d_sketch: schizzo 3D aperto con nome", ok and bool(name) and d.get("is_3d") is True, f"nome {name}")
    ok1, _, d1 = await c.call("draw_3d_line", x1=0, y1=0, z1=0, x2=30, y2=0, z2=0)
    ok2, _, d2 = await c.call("draw_3d_line", x1=30, y1=0, z1=0, x2=30, y2=20, z2=10)
    record("S6 polilinea 3D di 2 tratti: estremi riletti (0,0,0)-(30,0,0) e (30,0,0)-(30,20,10)",
           ok1 and ok2 and d1.get("end_mm") == [30.0, 0.0, 0.0] and d2.get("end_mm") == [30.0, 20.0, 10.0] and d2.get("start_mm") == [30.0, 0.0, 0.0],
           f"{d1.get('start_mm')}->{d1.get('end_mm')}, {d2.get('start_mm')}->{d2.get('end_mm')}; lunghezze {d1.get('length_mm')} {d2.get('length_mm')}")
    record("S6 lunghezza del secondo tratto = sqrt(20^2 + 10^2) = 22.3607 mm", abs(d2.get("length_mm", 0) - math.sqrt(500)) < 0.001, f"{d2.get('length_mm')}")
    ok, text, d = await c.call("close_sketch")
    record("S6 close_sketch chiude lo schizzo 3D (nessun tool nuovo necessario)", ok and d.get("had_active_sketch") is True, text.splitlines()[0][:80])
    ok, text, d = await c.call("sweep", path_sketch=name, circular_diameter=4)
    ok2, _, mp = await c.call("get_mass_properties")
    v = mp.get("volume_mm3", 0.0)
    exp = math.pi * 2 ** 2 * (30 + math.sqrt(500))
    record("S6 sweep di diametro 4 lungo la polilinea 3D: volume vicino a pi*r^2*L = %.3f mm3 (tolleranza 0.5%% per lo spigolo)" % exp,
           ok and abs(v - exp) / exp < 0.005, f"misurato {v:.3f} mm3, scarto {abs(v - exp) / exp * 100:.4f} %")
    await c.call("close_document", discard=True)
    # spline e punto
    await c.call("create_new_part")
    await c.call("create_3d_sketch")
    pts = [[0, 0, 0], [10, 10, 5], [20, 0, 10], [30, 10, 15]]
    ok, text, d = await c.call("draw_3d_spline", points=pts)
    record("S6 spline 3D per 4 punti: inizio (0,0,0), fine (30,10,15)", ok and near(d.get("start_mm", []), (0, 0, 0), 0.001) and near(d.get("end_mm", []), (30, 10, 15), 0.001),
           f"{d.get('start_mm')} -> {d.get('end_mm')}")
    ok, text, d = await c.call("draw_3d_point", x=5, y=6, z=7)
    record("S6 punto 3D (5,6,7)", ok and d.get("position_mm") == [5.0, 6.0, 7.0], f"{d.get('position_mm')}")
    await c.call("close_sketch")
    await c.call("close_document", discard=True)


# ===================================================================================================== run
async def scenario(c):
    only = {a.upper() for a in sys.argv[1:]}
    sezioni = [("S1", s1_trim_extend), ("S2", s2_chamfer), ("S3", s3_patterns), ("S4", s4_transform), ("S5", s5_entities), ("S6", s6_sketch3d)]
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
    for tool, res, note in RESULTS:
        print(f"{res:5} {tool:70} {note}"[:230])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
