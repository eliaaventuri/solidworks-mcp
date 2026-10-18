"""
Test live del lotto MOKA 2 (strumenti per ricreare i pezzi della moka) tramite il server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente non viene mai
toccata; alla fine si chiude solo il PID lanciato dal test.

  M1  add_cosmetic_thread: foro interno M8, albero esterno M56 (diametro minore = valore di SolidWorks), M8x1, fino al successivo
  M2  fill_pattern: feature esistente quadrata (45), forme predefinite (cerchio a perforazione 43, quadrato 45, rombo 45),
      confine da schizzo (45): istanze e volumi asportati confrontati con il conteggio a mano
  M3  corpi: list_bodies, combine_bodies (add/subtract/common), delete_body (elimina/mantieni), insert_part (+ traslazione/rotazione)
  M4  get_feature_definition: estrusione 25+5, foro M8, ripetizione lineare 4x15, raccordo, piano, riempimento, filettatura cosmetica

Uso:  .venv\\Scripts\\python.exe tests\\test_ext_moka2_live.py [M1 M2 ...]
Output: test_output\\ (file moka2_*)
"""

import os
import sys
import math
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup

RESULTS = []         # (nome, PASS/FAIL, nota)
TOL = 0.002          # 0,2 % sui volumi


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:260])


def near(got, exp, tol=TOL, absolute=None):
    if absolute is not None:
        return abs(got - exp) <= absolute
    return abs(got - exp) <= tol * max(abs(exp), 1e-9)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def sub(a, b):
    return [x - y for x, y in zip(a, b)]


async def vol(c):
    ok, _, d = await c.call("get_mass_properties")
    return d.get("volume_mm3", 0.0) if ok else 0.0


async def discard_all(c):
    for _ in range(40):
        ok, _, d = await c.call("list_open_documents")
        docs = d.get("documents", []) if ok else []
        if not docs:
            return
        await c.call("close_document", discard=True, document=docs[0]["title"])


async def new_part(c):
    ok, text, _ = await c.call("create_new_part")
    assert ok, text


async def face_circle(c, face_pt, center_yz, r):
    """Schizzo sulla faccia x=const passante per face_pt e cerchio centrato nel punto MODELLO (y,z)."""
    ok, text, info = await c.call("create_sketch_on_face", x=face_pt[0], y=face_pt[1], z=face_pt[2])
    if not ok:
        return False
    o, ux, uy = info["sketch_origin_mm"], info["sketch_x_axis"], info["sketch_y_axis"]
    P = [face_pt[0], center_yz[0], center_yz[1]]
    u, v = dot(sub(P, o), ux), dot(sub(P, o), uy)
    ok2, _, _ = await c.call("draw_circle", x=u, y=v, radius=r)
    return ok2


async def block(c, y1, z1, y2, z2, depth, merge=True):
    """Parallelepipedo: schizzo sul piano frontale (coordinate y,z del modello), estruso lungo x da 0 a depth."""
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=y1, y1=z1, x2=y2, y2=z2)
    ok, text, d = await c.call("extrude_boss", depth=depth, merge=merge)
    assert ok, text
    return d.get("feature")


async def plate(c):
    await new_part(c)
    return await block(c, 0, 0, 100, 60, 5)


def cyl_count(ents):
    return len([e for e in ents if e.get("type") == "cylinder"])


async def count_cyl(c):
    ok, _, d = await c.call("list_entities", kind="face", limit=2000)
    return cyl_count(d.get("entities", [])) if ok else -1


# ===================================================================================================== M1
async def m1_cosmetic(c):
    print("\n== M1. add_cosmetic_thread")
    await new_part(c)
    await block(c, 0, 0, 60, 60, 20)
    await face_circle(c, [20, 30, 30], (30, 30), 3.4)        # foro Ø6,8 (punta M8)
    ok, _, d = await c.call("extrude_cut", depth=15)
    ok, text, d = await c.call("add_cosmetic_thread", edge_point=[20, 33.4, 30], size="M8", depth=12)
    record("M1 foro M8: filettatura creata (CosmeticThread, interna)", ok and d.get("feature_type") == "CosmeticThread"
           and d.get("kind") == "internal", text.split("\n")[0][:120])
    record("M1 foro M8: diametro riletto 8,0 (maggiore), profondita' 12", near(d.get("diameter", 0), 8.0, absolute=1e-4)
           and d.get("diameter_kind") == "major" and near(d.get("depth", 0), 12.0, absolute=1e-4),
           f"Ø{d.get('diameter')} {d.get('diameter_kind')}, prof. {d.get('depth')}")
    record("M1 foro M8: standard ISO (8), richiamo 'M8 Machine Threads'", d.get("standard") == 8 and d.get("size") == "M8"
           and d.get("callout") == "M8 Machine Threads", f"{d.get('standard')} {d.get('size')} {d.get('callout')}")
    ok, text, d2 = await c.call("add_cosmetic_thread", edge_point=[20, 33.4, 30], size="M8", end_condition="blind")
    record("M1 blind senza depth: rifiutato", not ok, text.split("\n")[0][:100])
    ok, text, d2 = await c.call("add_cosmetic_thread", edge_point=[0, 0, 0], size="M8", depth=5)
    record("M1 punto non su uno spigolo: rifiutato", not ok, text.split("\n")[0][:100])
    await discard_all(c)

    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=28)
    await c.call("extrude_boss", depth=30)
    ok, text, d = await c.call("add_cosmetic_thread", edge_point=[30, 0, 28], size="M56", end_condition="up_to_next", depth=10)
    p = 5.5
    exp = 56 - 1.0825 * p - (0.015 + 0.011 * p)
    record("M1 albero M56: esterna, diametro minore 49,971 (valore dei file della moka)",
           ok and d.get("kind") == "external" and d.get("diameter_kind") == "minor" and near(d.get("diameter", 0), 49.971, absolute=0.002)
           and near(d.get("diameter", 0), exp, absolute=1e-3), f"Ø{d.get('diameter')} formula {exp:.4f}")
    record("M1 albero M56 fino al successivo: profondita' ricalcolata = lunghezza 30", near(d.get("depth", 0), 30.0, absolute=1e-3)
           and d.get("end_condition") == "up_to_next", f"prof. {d.get('depth')}")
    ok, text, d = await c.call("add_cosmetic_thread", edge_point=[0, 0, 28], size="M56x4", end_condition="through")
    exp = 56 - 1.0825 * 4 - (0.015 + 0.011 * 4)
    record("M1 albero M56x4 passante: Ø minore da formula, richiamo con passo",
           ok and near(d.get("diameter", 0), exp, absolute=1e-3) and d.get("size") == "M56x4" and d.get("end_condition") == "through",
           f"Ø{d.get('diameter')} atteso {exp:.4f}, {d.get('size')}")
    ok, text, d = await c.call("add_cosmetic_thread", edge_point=[0, 28, 0], size="Q8", depth=3)
    record("M1 misura non valida 'Q8': rifiutata", not ok, text.split("\n")[0][:100])
    await discard_all(c)


# ===================================================================================================== M2
async def m2_fill(c):
    print("\n== M2. fill_pattern")
    V0 = 100 * 60 * 5
    seed_vol = math.pi * 2 ** 2 * 5
    # a) feature esistente, quadrata, margine 5: seme a (10,10), passo 10 -> y=10..90 (9) x z=10..50 (5)
    await plate(c)
    await face_circle(c, [5, 50, 30], (10, 10), 2)
    ok, _, d = await c.call("extrude_cut", end_condition="through_all")
    cut = d.get("feature")
    ok, text, d = await c.call("fill_pattern", face_point=[5, 50, 30], features=[cut], layout="square", spacing=10, margin=5,
                               direction={"edge": [5, 50, 0]})
    record("M2 a) feature quadrata: 45 istanze contate", ok and d.get("instances") == 45, f"{d.get('instances')} (atteso 9x5=45)")
    v = await vol(c)
    record("M2 a) volume = piastra - 45 fori", near(v, V0 - 45 * seed_vol), f"{v:.2f} atteso {V0 - 45 * seed_vol:.2f}")
    n = await count_cyl(c)
    record("M2 a) facce cilindriche dei fori = 45", n == 45, str(n))
    ok, text, d = await c.call("get_feature_definition", name=d.get("feature", ""))
    df = d.get("definition", {})
    record("M2 a) definizione riletta: quadrata, passo 10, margine 5, su feature",
           ok and df.get("layout") == "square" and near(df.get("instance_spacing", 0), 10, absolute=1e-4)
           and near(df.get("margin", -1), 5, absolute=1e-4) and df.get("pattern_of") == "features",
           f"{df.get('layout')} {df.get('instance_spacing')} {df.get('margin')} {df.get('pattern_of')}")
    await discard_all(c)

    # b) cerchio Ø4, perforazione 60 gradi, direzione lungo y, margine 5 dal bordo del foro: 43 istanze
    # (seme al centro (50,30); righe z=30+8,66m con |8,66m|<=23: m=-2..2; righe pari y=50+10k (9), dispari y=45+10k (8))
    await plate(c)
    ok, text, d = await c.call("fill_pattern", face_point=[5, 50, 30], shape="circle", size=4, layout="perforation", spacing=10,
                               stagger_angle=60, margin=5, direction={"edge": [5, 50, 0]})
    record("M2 b) cerchio a perforazione: 43 istanze (calcolo a mano)", ok and d.get("instances") == 43, f"{d.get('instances')} atteso 43")
    v = await vol(c)
    record("M2 b) volume = piastra - 43 fori Ø4", near(v, V0 - 43 * seed_vol), f"{v:.2f} atteso {V0 - 43 * seed_vol:.2f}")
    n = await count_cyl(c)
    record("M2 b) facce cilindriche = 43", n == 43, str(n))
    await discard_all(c)

    # c) quadrato lato 4, layout quadrato, margine 5: 45 istanze, area 16 mm2 x 5 mm
    await plate(c)
    ok, text, d = await c.call("fill_pattern", face_point=[5, 50, 30], shape="square", size=4, layout="square", spacing=10, margin=5)
    v = await vol(c)
    record("M2 c) quadrato 4x4: 45 istanze e volume asportato 45x16x5", ok and d.get("instances") == 45 and near(v, V0 - 45 * 80),
           f"{d.get('instances')} istanze, volume {v:.2f} atteso {V0 - 3600:.2f}")
    await discard_all(c)

    # d) rombo di diagonale 6 (area 18): 45 x 18 x 5
    await plate(c)
    ok, text, d = await c.call("fill_pattern", face_point=[5, 50, 30], shape="diamond", size=6, layout="square", spacing=10, margin=5)
    v = await vol(c)
    record("M2 d) rombo diagonale 6: 45 istanze e volume asportato 45x18x5", ok and d.get("instances") == 45 and near(v, V0 - 45 * 90),
           f"{d.get('instances')} istanze, volume {v:.2f} atteso {V0 - 4050:.2f}")
    await discard_all(c)

    # e) confine da schizzo chiuso 5..95 x 5..55, cerchio Ø4, quadrata, margine 0: y=50+10k (|10k|+2<=45 -> 9) x z=30+10m (|10m|+2<=25 -> 5)
    await plate(c)
    ok, _, info = await c.call("create_sketch_on_face", x=5, y=50, z=30)
    o, ux, uy = info["sketch_origin_mm"], info["sketch_x_axis"], info["sketch_y_axis"]
    p1 = [dot(sub([5, 5, 5], o), ux), dot(sub([5, 5, 5], o), uy)]
    p2 = [dot(sub([5, 95, 55], o), ux), dot(sub([5, 95, 55], o), uy)]
    await c.call("draw_rectangle", x1=p1[0], y1=p1[1], x2=p2[0], y2=p2[1])
    ok, _, dd = await c.call("close_sketch")
    ok, _, lst = await c.call("list_model_features")
    sk = [f["name"] for f in lst.get("features", []) if f["type"] == "ProfileFeature"][-1]
    ok, text, d = await c.call("fill_pattern", boundary_sketch=sk, shape="circle", size=4, layout="square", spacing=10, margin=0)
    v = await vol(c)
    record("M2 e) confine da schizzo: 45 istanze e volume", ok and d.get("instances") == 45 and near(v, V0 - 45 * seed_vol),
           f"{d.get('instances')} istanze, volume {v:.2f} atteso {V0 - 45 * seed_vol:.2f}")
    ok, text, dd = await c.call("get_feature_definition", name=d.get("feature", "")) if d.get("feature") else (False, "", {})
    df = dd.get("definition", {})
    record("M2 e) definizione riletta: seme cerchio Ø4, confine = schizzo",
           ok and df.get("pattern_of") == "seed_cut" and near(df.get("seed_cut", {}).get("diameter", 0), 4.0, absolute=1e-4)
           and any(b.get("name") == sk for b in df.get("boundary", [])),
           f"{df.get('seed_cut')} {df.get('boundary')}")
    await discard_all(c)
    # f) errori
    await plate(c)
    ok, text, _ = await c.call("fill_pattern", face_point=[5, 50, 30], layout="square")
    record("M2 f) senza features ne' shape: rifiutato", not ok, text.split("\n")[0][:100])
    ok, text, _ = await c.call("fill_pattern", face_point=[5, 50, 30], shape="circle", layout="square")
    record("M2 f) shape senza size: rifiutato", not ok, text.split("\n")[0][:100])
    await discard_all(c)


# ===================================================================================================== M3
async def two_boxes(c):
    await new_part(c)
    await block(c, 0, 0, 40, 40, 20)
    await block(c, 20, 20, 60, 60, 20, merge=False)


async def bodies(c):
    ok, _, d = await c.call("list_bodies")
    return d.get("bodies", []) if ok else []


async def m3_bodies(c):
    print("\n== M3. corpi")
    await two_boxes(c)
    bs = await bodies(c)
    record("M3 list_bodies: 2 corpi solidi da 32000 mm3", len(bs) == 2 and all(near(b.get("volume_mm3", 0), 32000) for b in bs)
           and all(b.get("type") == "solid" for b in bs), f"{[(b.get('name'), b.get('volume_mm3')) for b in bs]}")
    boxes = sorted([tuple(b["box_min"] + b["box_max"]) for b in bs])
    record("M3 list_bodies: ingombri [0,0,0,20,40,40] e [0,20,20,20,60,60]",
           boxes == [(0, 0, 0, 20, 40, 40), (0, 20, 20, 20, 60, 60)], str(boxes))
    record("M3 list_bodies: un punto di faccia per corpo, distinti", all(len(b.get("face_point", [])) == 3 for b in bs)
           and bs[0].get("face_point") != bs[1].get("face_point"), str([b.get("face_point") for b in bs]))
    for op, exp_v, exp_n in (("subtract", 24000, 1), ("add", 56000, 1), ("common", 8000, 1)):
        await two_boxes(c)
        bs = await bodies(c)
        main = next(b for b in bs if b["box_min"][1] == 0)
        tool = next(b for b in bs if b["box_min"][1] == 20)
        ok, text, d = await c.call("combine_bodies", main=main["face_point"], tools=[tool["face_point"]], operation=op)
        v = await vol(c)
        nb = len(await bodies(c))
        record(f"M3 combine_bodies {op}: volume {exp_v} e {exp_n} corpo", ok and near(v, exp_v) and nb == exp_n,
               f"{v:.2f} mm3 (atteso {exp_v}), corpi {nb}; feature {d.get('feature_type')}")
    # per nome
    await two_boxes(c)
    bs = await bodies(c)
    ok, text, d = await c.call("combine_bodies", main=bs[0]["name"], tools=[bs[1]["name"]], operation="subtract")
    v = await vol(c)
    ok2 = ok and (near(v, 24000) or near(v, 24000))
    record("M3 combine_bodies per nome (subtract)", ok2, f"{v:.2f}")
    ok, text, d = await c.call("combine_bodies", main="Inesistente", tools=[0], operation="add")
    record("M3 combine_bodies con nome inesistente: rifiutato", not ok, text.split("\n")[0][:100])
    # delete_body
    await two_boxes(c)
    bs = await bodies(c)
    tgt = next(b for b in bs if b["box_min"][1] == 20)
    ok, text, d = await c.call("delete_body", bodies=[tgt["face_point"]])
    v = await vol(c)
    left = await bodies(c)
    record("M3 delete_body: elimina il corpo scelto (volume 32000, 1 corpo, resta quello a y=0)",
           ok and near(v, 32000) and len(left) == 1 and left[0]["box_min"][1] == 0, f"{v:.2f}, {len(left)} corpi; {d.get('feature_type')}")
    await two_boxes(c)
    bs = await bodies(c)
    tgt = next(b for b in bs if b["box_min"][1] == 20)
    ok, text, d = await c.call("delete_body", bodies=[tgt["face_point"]], keep=True)
    v = await vol(c)
    left = await bodies(c)
    record("M3 delete_body keep=true: resta solo il corpo scelto (a y=20)", ok and near(v, 32000) and len(left) == 1
           and left[0]["box_min"][1] == 20, f"{v:.2f}, {len(left)} corpi")
    await two_boxes(c)
    ok, text, d = await c.call("delete_body", bodies=[0, 1])
    record("M3 delete_body di tutti i corpi: rifiutato", not ok, text.split("\n")[0][:100])
    await discard_all(c)

    # insert_part: blocco 10x20x30 (x 0..10, y 0..20, z 0..30) salvato in test_output
    f1 = str(OUT / "moka2_ins.sldprt")
    await new_part(c)
    await block(c, 0, 0, 20, 30, 10)
    ok, text, _ = await c.call("save_document", filepath=f1)
    record("M3 salvataggio del pezzo da inserire", ok, text.split("\n")[0][:100])
    await discard_all(c)
    await new_part(c)
    ok, text, d = await c.call("insert_part", filepath=f1, translate=[20, 5, 0])
    bs = await bodies(c)
    box = bs[0]["box_min"] + bs[0]["box_max"] if bs else []
    record("M3 insert_part + traslazione [20,5,0]: volume 6000 e ingombro [20,5,0,30,25,30]",
           ok and near(await vol(c), 6000) and len(bs) == 1 and all(near(a, b, absolute=1e-3) for a, b in zip(box, [20, 5, 0, 30, 25, 30])),
           f"vol {await vol(c):.2f}, box {box}")
    await discard_all(c)
    await new_part(c)
    ok, text, d = await c.call("insert_part", filepath=f1, rotate=[90, 0, 0])
    bs = await bodies(c)
    box = bs[0]["box_min"] + bs[0]["box_max"] if bs else []
    record("M3 insert_part + rotazione 90 gradi attorno a X: ingombro [0,-30,0,10,0,20]",
           ok and len(bs) == 1 and all(near(a, b, absolute=1e-3) for a, b in zip(box, [0, -30, 0, 10, 0, 20])), f"box {box}")
    await discard_all(c)
    await new_part(c)
    await block(c, 0, 0, 40, 40, 20)
    ok, text, d = await c.call("insert_part", filepath=f1)
    bs = await bodies(c)
    record("M3 insert_part su pezzo con corpo sovrapposto: 2 corpi distinti, volume 32000+6000",
           ok and len(bs) == 2 and near(await vol(c), 38000), f"{len(bs)} corpi, vol {await vol(c):.2f}")
    ok, text, d = await c.call("insert_part", filepath=str(OUT / "inesistente.sldprt"))
    record("M3 insert_part con file inesistente: rifiutato", not ok, text.split("\n")[0][:100])
    await discard_all(c)


# ===================================================================================================== M4
async def m4_definition(c):
    print("\n== M4. get_feature_definition")
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=0, x2=60, y2=40)
    ok, _, d = await c.call("extrude_boss", depth=25, depth2=5)
    ext = d.get("feature")
    ok, text, d = await c.call("get_feature_definition", name=ext)
    df = d.get("definition", {})
    d1, d2 = df.get("direction1", {}), df.get("direction2", {})
    record("M4 estrusione: direzione 1 blind 25, direzione 2 blind 5, entrambe le direzioni",
           ok and df.get("kind") == "extrude" and d1.get("end_condition") == "blind" and near(d1.get("depth", 0), 25, absolute=1e-4)
           and d2.get("end_condition") == "blind" and near(d2.get("depth", 0), 5, absolute=1e-4) and df.get("both_directions") is True,
           f"{d1} {d2}")
    record("M4 estrusione: schizzo usato, quote D1=25 D2=5, figlie vuote", len(d.get("sketches", [])) == 1
           and sorted(round(x["value"], 3) for x in d.get("dimensions", [])) == [5.0, 25.0], f"{d.get('sketches')} {d.get('dimensions')}")
    ok, _, e = await c.call("list_entities", kind="face", limit=20)
    top = [x for x in e["entities"] if x["type"] == "plane" and x["normal"][0] > 0.9][0]["point"]
    ok, text, d = await c.call("create_hole", kind="tapped", size="M8", face_point=[top[0], 8, 20], depth=12, thread_depth=10)
    hole = [n for n in [f["name"] for f in (await c.call("list_model_features"))[2]["features"]] if "M8" in n][0]
    ok, text, d = await c.call("get_feature_definition", name=hole)
    df = d.get("definition", {})
    record("M4 foro M8: standard ISO, misura M8, profondita' punta 12, filetto 10",
           ok and df.get("kind") == "hole_wizard" and df.get("size") == "M8" and near(df.get("tap_drill_depth", 0), 12, absolute=1e-3)
           and near(df.get("thread_depth", 0), 10, absolute=1e-3) and near(df.get("tap_drill_diameter", 0), 6.8, absolute=1e-3),
           f"{df.get('standard')} {df.get('size')} punta {df.get('tap_drill_diameter')}x{df.get('tap_drill_depth')} filetto {df.get('thread_depth')}")
    ok, text, d = await c.call("linear_pattern", features=[hole], direction1={"edge": [top[0], 30, 0]}, count1=4, spacing1=15)
    lp = d.get("feature")
    ok, text, d = await c.call("get_feature_definition", name=lp)
    df = d.get("definition", {})
    record("M4 ripetizione lineare: 4 istanze, passo 15, feature ripetuta = foro",
           ok and df.get("kind") == "linear_pattern" and df.get("direction1", {}).get("instances") == 4
           and near(df["direction1"].get("spacing", 0), 15, absolute=1e-4)
           and [f["name"] for f in df.get("patterned_features", [])] == [hole], f"{df.get('direction1')} {df.get('patterned_features')}")
    ok, text, d = await c.call("fillet_edges", radius=2, edge_points=[[top[0], 30, 40]])
    fil = d.get("feature")
    ok, text, d = await c.call("get_feature_definition", name=fil)
    df = d.get("definition", {})
    record("M4 raccordo: raggio 2, 1 spigolo", ok and df.get("kind") == "fillet" and near(df.get("radius", 0), 2, absolute=1e-4)
           and df.get("edges") == 1, f"{df.get('radius')} {df.get('edges')}")
    ok, text, d = await c.call("create_reference_plane", mode="offset", base="front", distance=10)
    pl = d.get("feature")
    ok, text, d = await c.call("get_feature_definition", name=pl)
    df = d.get("definition", {})
    record("M4 piano a distanza 10 dal frontale: origine x=10, normale +X, distanza 10",
           ok and df.get("kind") == "reference_plane" and near(df.get("distance", 0), 10, absolute=1e-4)
           and near(df.get("origin", [0])[0], 10, absolute=1e-3) and near(abs(df.get("normal", [0])[0]), 1, absolute=1e-4),
           f"{df.get('origin')} {df.get('normal')}")
    sk = ext and (await c.call("get_feature_definition", name=ext))[2].get("sketches", [""])[0]
    ok, text, d = await c.call("get_feature_definition", name=sk)
    record("M4 tipo non gestito (schizzo): tipo + genitori + quote + nota, senza errore",
           ok and d.get("type") == "ProfileFeature" and "definition" not in d and "note" in d and "parents" in d and "dimensions" in d,
           f"{d.get('type')} {d.get('note')} {len(d.get('dimensions', []))} quote")
    ok, text, d = await c.call("get_feature_definition", name="NonEsiste")
    record("M4 feature inesistente: rifiutata", not ok, text.split("\n")[0][:100])
    await discard_all(c)

    # filettatura cosmetica riletta
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=28)
    await c.call("extrude_boss", depth=30)
    ok, text, d = await c.call("add_cosmetic_thread", edge_point=[30, 0, 28], size="M56", end_condition="up_to_next", depth=10)
    ok, text, d2 = await c.call("get_feature_definition", name=d.get("feature", ""))
    df = d2.get("definition", {})
    record("M4 filettatura cosmetica: M56, minore 49,971, ISO, richiamo", ok and df.get("kind") == "cosmetic_thread"
           and df.get("size") == "M56" and df.get("diameter_kind") == "minor" and near(df.get("diameter", 0), 49.971, absolute=0.002)
           and df.get("callout") == "M56 Machine Threads", f"{df.get('size')} {df.get('diameter')} {df.get('callout')}")
    await discard_all(c)


# ===================================================================================================== principale
async def scenario(c):
    only = {a.upper() for a in sys.argv[1:]}
    for nome, fn in (("M1", m1_cosmetic), ("M2", m2_fill), ("M3", m3_bodies), ("M4", m4_definition)):
        if not only or nome in only:
            await fn(c)
    await discard_all(c)


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
                c = Client(session)
                tools = [t.name for t in (await session.list_tools()).tools]
                print(f"{len(tools)} tool esposti")
                record("tool nuovi esposti", all(t in tools for t in (
                    "add_cosmetic_thread", "fill_pattern", "list_bodies", "delete_body", "combine_bodies", "insert_part",
                    "get_feature_definition")), "")
                ok, text, data = await c.call("connect_solidworks")
                my_pid = data.get("pid")
                print(text[:200])
                if not ok or not my_pid or my_pid in elia_pids or my_pid not in sw_pids():
                    print("STOP: nessuna istanza separata ottenibile. Nulla e' stato toccato.")
                    return False
                print(f"Istanza dedicata PID {my_pid} (diversa da {sorted(elia_pids)})")
                await scenario(c)
    finally:
        _cleanup(my_pid, elia_pids)
    return True


def _cleanup(my_pid, elia_pids):
    cleanup(my_pid, elia_pids)
    # altri sotto-agenti aprono e chiudono istanze proprie in parallelo: si controlla solo il PROPRIO PID
    record("istanza dedicata del test chiusa (PID proprio)", my_pid is None or my_pid not in sw_pids(),
           f"PID proprio {my_pid} chiuso: {my_pid not in sw_pids()}")


if __name__ == "__main__":
    done = asyncio.run(run())
    print("\n==== RIEPILOGO ====")
    for tool, res, note in RESULTS:
        print(f"{res:5} {tool:80} {note}"[:260])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
