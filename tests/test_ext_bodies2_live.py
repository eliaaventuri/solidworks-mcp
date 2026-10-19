"""
Test live del lotto CORPI 2 (sposta/copia, dividi, interseca, scala corpi; ripetizioni guidate da curva/schizzo/tabella)
tramite il server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente non viene mai
toccata; alla fine si chiude solo il PID lanciato dal test.

  B1  move_copy_body: traslazione, da punto a punto, rotazione attorno a Z e a uno spigolo, copie (box e volumi misurati)
  B2  split_body: blocco 40x30x20 diviso da un piano a x=10 (6000 + 18000 mm3), salvataggio dei pezzi, faccia piana come strumento
  B3  intersect_bodies: regione comune di due blocchi (12000 mm3), tutte le regioni, scelta per indice, piano + corpo
  B4  scale_body: uniforme (x3,375), per assi 1x2x3 rispetto all'origine, un corpo solo, rispetto a un sistema di coordinate
  B5  ripetizioni guidate: da curva (distanza uguale e passo fisso, spigolo), da schizzo (punti), da tabella (coordinate) -
      istanze (cilindri) contate, volume = piastra + n * seme e baricentro confrontati con il calcolo a mano

Uso:  .venv\\Scripts\\python.exe tests\\test_ext_bodies2_live.py [B1 B2 ...]
Output: test_output\\ (file bd2_*)
"""

import os
import sys
import math
import shutil
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup

RESULTS = []         # (nome, PASS/FAIL, nota)
TOL = 0.002          # 0,2 % sui volumi
BOSS_V = math.pi * 2.5 ** 2 * 5      # volume del seme cilindrico (r 2,5 x h 5)
PLATE_V = 100 * 60 * 5


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


def box_ok(b, mn, mx, tol=0.01):
    return all(abs(a - e) <= tol for a, e in zip(list(b["box_min"]) + list(b["box_max"]), list(mn) + list(mx)))


def boxes_text(bs):
    return str([(b.get("name"), b["box_min"], b["box_max"]) for b in bs])[:200]


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


async def block(c, y1, z1, y2, z2, depth, merge=True):
    """Parallelepipedo: schizzo sul piano frontale (coordinate y,z del modello), estruso lungo x da 0 a depth."""
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=y1, y1=z1, x2=y2, y2=z2)
    ok, text, d = await c.call("extrude_boss", depth=depth, merge=merge)
    assert ok, text
    return d.get("feature")


async def bodies(c):
    ok, _, d = await c.call("list_bodies")
    return d.get("bodies", []) if ok else []


async def feature_names(c, kind):
    ok, _, d = await c.call("list_model_features")
    return [f["name"] for f in d.get("features", []) if f.get("type") == kind] if ok else []


async def sketch_on(c, face_pt):
    ok, text, info = await c.call("create_sketch_on_face", x=face_pt[0], y=face_pt[1], z=face_pt[2])
    assert ok, text
    return info


def uv(info, P):
    o, ux, uy = info["sketch_origin_mm"], info["sketch_x_axis"], info["sketch_y_axis"]
    return dot(sub(P, o), ux), dot(sub(P, o), uy)


async def plate_boss(c):
    """Piastra y 0..100, z 0..60, x 0..5 con un cilindro r 2,5 x h 5 centrato in (y 10, z 10) sulla faccia x=5.
    Ritorna (nome della feature del cilindro, punto della faccia)."""
    await new_part(c)
    await block(c, 0, 0, 100, 60, 5)
    fp = [5, 50, 30]
    info = await sketch_on(c, fp)
    u, v = uv(info, [5, 10, 10])
    await c.call("draw_circle", x=u, y=v, radius=2.5)
    ok, text, d = await c.call("extrude_boss", depth=5)
    assert ok, text
    return d["feature"], fp


async def count_cyl(c):
    ok, _, d = await c.call("list_entities", kind="face", limit=2000)
    return len([e for e in d.get("entities", []) if e.get("type") == "cylinder"]) if ok else -1


async def expected_com_y(c, ys_boss):
    """Baricentro Y atteso: piastra (y 50, x 2,5) + cilindri (centroide y indicati)."""
    m = PLATE_V + BOSS_V * len(ys_boss)
    return (PLATE_V * 50 + BOSS_V * sum(ys_boss)) / m


async def com(c):
    ok, _, d = await c.call("get_mass_properties")
    return d.get("center_of_mass_mm", [0, 0, 0]) if ok else [0, 0, 0]


# ===================================================================================================== B1
async def b1_move(c):
    print("\n== B1. move_copy_body")
    await new_part(c)
    await block(c, 0, 0, 30, 20, 40)             # x 0..40, y 0..30, z 0..20: 24000
    ok, text, d = await c.call("move_copy_body", bodies=[0], translate=[100, 0, 0])
    bs = await bodies(c)
    record("B1 traslazione [100,0,0]: box x 100..140, volume 24000", ok and len(bs) == 1 and box_ok(bs[0], [100, 0, 0], [140, 30, 20])
           and near(await vol(c), 24000), boxes_text(bs))
    ok, text, d = await c.call("move_copy_body", bodies=[0], from_point=[0, 0, 0], to_point=[0, 50, 0])
    bs = await bodies(c)
    record("B1 da punto a punto (0,0,0)->(0,50,0): y 50..80", ok and box_ok(bs[0], [100, 50, 0], [140, 80, 20]), boxes_text(bs))
    ok, text, d = await c.call("move_copy_body", bodies=[0], rotate_angle=90, rotate_axis="z", rotate_point=[100, 50, 0])
    bs = await bodies(c)
    record("B1 rotazione 90 gradi attorno a Z per (100,50): box x 70..100, y 50..90, volume 24000",
           ok and box_ok(bs[0], [70, 50, 0], [100, 90, 20]) and near(await vol(c), 24000), boxes_text(bs))
    ok, text, d = await c.call("move_copy_body", bodies=[0], translate=[0, 0, 50], copies=2)
    bs = sorted(await bodies(c), key=lambda b: b["box_min"][2])
    record("B1 2 copie con passo z 50: 3 corpi (z 0, 50, 100), volume 72000",
           ok and len(bs) == 3 and [b["box_min"][2] for b in bs] == [0, 50, 100] and near(await vol(c), 72000), boxes_text(bs))
    await discard_all(c)

    await new_part(c)
    await block(c, 0, 0, 30, 20, 40)
    ok, text, d = await c.call("move_copy_body", bodies=[[20, 0, 10]], rotate_angle=90, rotate_axis={"edge": [0, 0, 10]})
    bs = await bodies(c)
    record("B1 rotazione 90 gradi attorno a uno spigolo verticale in (0,0): box x -30..0, y 0..40",
           ok and box_ok(bs[0], [-30, 0, 0], [0, 40, 20]), (text.split("\n")[0][:80] + " " + boxes_text(bs)))
    ok, text, d = await c.call("move_copy_body", bodies=[0])
    record("B1 senza operazione: rifiutato", not ok, text.split("\n")[0][:100])
    ok, text, d = await c.call("move_copy_body", bodies=[7], translate=[1, 0, 0])
    record("B1 corpo inesistente: rifiutato", not ok, text.split("\n")[0][:100])
    await discard_all(c)


# ===================================================================================================== B2
async def b2_split(c):
    print("\n== B2. split_body")
    await new_part(c)
    await block(c, 0, 0, 30, 20, 40)             # blocco 40 x 30 x 20 (x,y,z)
    ok, _, dp = await c.call("create_reference_plane", mode="offset", base="front", distance=10)
    plane = dp.get("feature")
    out = os.path.join(OUT, "bd2_split")
    shutil.rmtree(out, ignore_errors=True)
    path = os.path.join(out, "blocco.sldprt")
    ok, text, d = await c.call("split_body", tools=[plane], save_path=path)
    bs = sorted(await bodies(c), key=lambda b: b["box_min"][0])
    record("B2 piano a x=10: due corpi 6000 (x 0..10) e 18000 mm3 (x 10..40)",
           ok and len(bs) == 2 and near(bs[0]["volume_mm3"], 6000) and near(bs[1]["volume_mm3"], 18000)
           and box_ok(bs[0], [0, 0, 0], [10, 30, 20]) and box_ok(bs[1], [10, 0, 0], [40, 30, 20]), f"{[b['volume_mm3'] for b in bs]}")
    record("B2 volume totale conservato (24000)", near(await vol(c), 24000), f"{await vol(c)}")
    files = d.get("saved_files", []) if ok else []
    f1, f2 = os.path.join(out, "blocco_1.sldprt"), os.path.join(out, "blocco_2.sldprt")
    record("B2 salvataggio: due file .sldprt non vuoti", ok and len(files) == 2 and os.path.isfile(f1) and os.path.isfile(f2)
           and os.path.getsize(f1) > 1000 and os.path.getsize(f2) > 1000, f"{[os.path.basename(f['path']) for f in files]}")
    ok2, _, dl = await c.call("list_open_documents")
    titles = [x["title"] for x in dl.get("documents", [])]
    record("B2 nessun documento temporaneo rimasto aperto (solo la parte)", ok2 and len(titles) == 1, f"{titles}")
    # i file salvati hanno i volumi giusti
    vols = []
    for f in (f1, f2):
        okd, _, dd = await c.call("open_document", filepath=f)
        okm, _, dm = await c.call("get_mass_properties")
        vols.append(dm.get("volume_mm3", 0) if okm else 0)
        await c.call("close_document", discard=True, document=os.path.basename(f))
    record("B2 file salvati: volumi 6000 e 18000", near(vols[0], 6000) and near(vols[1], 18000), f"{vols}")
    ok, text, d = await c.call("split_body", tools=["Plane that does not exist"])
    record("B2 strumento inesistente: rifiutato", not ok and "non trovata" in text, text.split("\n")[0][:100])
    await discard_all(c)

    # faccia piana come strumento: la faccia x=20 del secondo blocco divide anche il primo
    await new_part(c)
    await block(c, 0, 0, 30, 20, 40)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=10, y1=-10, x2=20, y2=30)
    await c.call("extrude_boss", depth=20, merge=False)
    ok, text, d = await c.call("split_body", tools=[{"face": [20, 15, 5]}])
    bs = sorted([b["volume_mm3"] for b in await bodies(c)])
    record("B2 faccia piana x=20 come strumento: 3 corpi 8000 + 12000 + 12000", ok and len(bs) == 3 and near(bs[0], 8000)
           and near(bs[1], 12000) and near(bs[2], 12000) and near(await vol(c), 32000), f"{bs}")
    await discard_all(c)


# ===================================================================================================== B3
async def two_overlap(c):
    await new_part(c)
    await block(c, 0, 0, 30, 20, 40)             # A: x 0..40, y 0..30, z 0..20 (24000)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=10, y1=5, x2=50, y2=25)
    ok, text, d = await c.call("extrude_boss", depth=40, merge=False)       # B: x 0..40, y 10..50, z 5..25 (32000)
    assert ok, text


async def b3_intersect(c):
    print("\n== B3. intersect_bodies")
    await two_overlap(c)
    ok, text, d = await c.call("intersect_bodies", bodies=[0, 1])
    bs = await bodies(c)
    record("B3 regione comune (default): un corpo da 12000 mm3, box [0,10,5]-[40,30,20]",
           ok and len(bs) == 1 and near(bs[0]["volume_mm3"], 12000) and box_ok(bs[0], [0, 10, 5], [40, 30, 20]),
           f"{[b['volume_mm3'] for b in bs]} {boxes_text(bs)}")
    regs = d.get("regions", []) if ok else []
    record("B3 regioni elencate: 3 (12000, 20000, 12000), tenuta solo quella dentro a entrambi",
           sorted(r["volume_mm3"] for r in regs) == [12000, 12000, 20000] and sum(1 for r in regs if r["kept"]) == 1, f"{regs}"[:160])
    await discard_all(c)
    await two_overlap(c)
    ok, text, d = await c.call("intersect_bodies", bodies=[0, 1], regions="all")
    vs = sorted(b["volume_mm3"] for b in await bodies(c))
    record("B3 regions=all: 3 corpi 12000 + 12000 + 20000 (volume 44000)", ok and len(vs) == 3 and near(vs[0], 12000) and near(vs[2], 20000)
           and near(await vol(c), 44000), f"{vs}")
    await discard_all(c)
    await two_overlap(c)
    ok, text, d = await c.call("intersect_bodies", bodies=[0, 1], regions=[1])
    regs = d.get("regions", []) if ok else []
    idx = [r["index"] for r in regs if r["kept"]]
    bs = await bodies(c)
    record("B3 regions=[1]: tenuta la regione di indice 1", ok and idx == [1] and len(bs) == 1 and near(bs[0]["volume_mm3"], regs[1]["volume_mm3"]),
           f"{idx} {[b['volume_mm3'] for b in bs]}")
    await discard_all(c)
    # corpo + piano: due regioni
    await new_part(c)
    await block(c, 0, 0, 30, 20, 40)
    ok, _, dp = await c.call("create_reference_plane", mode="offset", base="front", distance=10)
    ok, text, d = await c.call("intersect_bodies", bodies=[0], tools=[dp.get("feature")], regions="all")
    vs = sorted(b["volume_mm3"] for b in await bodies(c))
    record("B3 corpo + piano a x=10 (regions=all): 6000 + 18000 mm3", ok and len(vs) == 2 and near(vs[0], 6000) and near(vs[1], 18000), f"{vs}")
    await discard_all(c)
    await two_overlap(c)
    ok, text, d = await c.call("intersect_bodies", bodies=[0])
    record("B3 un solo oggetto: rifiutato", not ok, text.split("\n")[0][:100])
    await discard_all(c)
    # corpi che non si toccano: nessuna regione comune -> annullato, il pezzo resta intatto
    await new_part(c)
    await block(c, 0, 0, 30, 20, 40)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=100, y1=0, x2=120, y2=20)
    await c.call("extrude_boss", depth=20, merge=False)
    ok, text, d = await c.call("intersect_bodies", bodies=[0, 1])
    record("B3 corpi disgiunti: rifiutato e volume invariato (32000)", not ok and near(await vol(c), 32000), f"{text.split(chr(10))[0][:90]} vol {await vol(c)}")
    await discard_all(c)


# ===================================================================================================== B4
async def b4_scale(c):
    print("\n== B4. scale_body")
    await new_part(c)
    await block(c, 10, 10, 40, 30, 40)            # x 0..40, y 10..40, z 10..30 (24000)
    ok, text, d = await c.call("scale_body", factor=1.5)
    bs = await bodies(c)
    record("B4 scala uniforme 1,5 (baricentro): volume 24000*3,375 = 81000, box x -10..50, y 2,5..47,5, z 5..35",
           ok and near(await vol(c), 81000) and box_ok(bs[0], [-10, 2.5, 5], [50, 47.5, 35]), f"{await vol(c)} {boxes_text(bs)}")
    await discard_all(c)
    await new_part(c)
    await block(c, 10, 10, 40, 30, 40)
    ok, text, d = await c.call("scale_body", factor_x=1, factor_y=2, factor_z=3, about="origin")
    bs = await bodies(c)
    record("B4 per assi 1x2x3 rispetto all'origine: volume 144000, box x 0..40, y 20..80, z 30..90",
           ok and near(await vol(c), 144000) and box_ok(bs[0], [0, 20, 30], [40, 80, 90]), f"{await vol(c)} {boxes_text(bs)}")
    ok, text, d = await c.call("scale_body", factor=0)
    record("B4 fattore 0: rifiutato", not ok, text.split("\n")[0][:100])
    ok, text, d = await c.call("scale_body", factor=2, factor_x=1)
    record("B4 factor + factor_x insieme: rifiutato", not ok, text.split("\n")[0][:100])
    await discard_all(c)
    # un corpo solo
    await new_part(c)
    await block(c, 0, 0, 30, 20, 40)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=100, y1=0, x2=120, y2=20)
    await c.call("extrude_boss", depth=20, merge=False)
    ok, text, d = await c.call("scale_body", factor=2, bodies=[[20, 0, 10]])
    bs = sorted(await bodies(c), key=lambda b: b["box_min"][1])
    record("B4 solo il corpo grande x2: volumi 192000 + 8000", ok and len(bs) == 2 and near(bs[0]["volume_mm3"], 192000)
           and near(bs[1]["volume_mm3"], 8000), f"{[b['volume_mm3'] for b in bs]}")
    await discard_all(c)
    # sistema di coordinate
    await new_part(c)
    await block(c, 10, 10, 40, 30, 40)
    okc, _, dc = await c.call("create_coordinate_system", origin=[100, 0, 0], rotation=[0, 0, 0])
    ok, text, d = await c.call("scale_body", factor=0.5, about="coordinate_system", coordinate_system=dc.get("feature"))
    bs = await bodies(c)
    record("B4 rispetto a un sistema di coordinate in (100,0,0), fattore 0,5: volume 3000, box x 50..70, y 5..20, z 5..15",
           ok and near(await vol(c), 3000) and box_ok(bs[0], [50, 5, 5], [70, 20, 15]), f"{await vol(c)} {boxes_text(bs)}")
    await discard_all(c)


# ===================================================================================================== B5
async def line_sketch(c, fp, p1, p2):
    info = await sketch_on(c, fp)
    u1, v1 = uv(info, [fp[0], p1[0], p1[1]])
    u2, v2 = uv(info, [fp[0], p2[0], p2[1]])
    await c.call("draw_line", x1=u1, y1=v1, x2=u2, y2=v2)
    await c.call("close_sketch")
    names = await feature_names(c, "ProfileFeature")
    return names[-1]


async def b5_patterns(c):
    print("\n== B5. ripetizioni guidate")
    # --- da curva: 5 istanze a distanza uguale lungo una linea 80 mm (passo 20)
    seed, fp = await plate_boss(c)
    sk = await line_sketch(c, fp, (10, 10), (90, 10))
    ok, text, d = await c.call("curve_driven_pattern", features=[seed], curve=sk, count=5)
    v = await vol(c)
    ys = [10, 30, 50, 70, 90]
    cm = await com(c)
    record("B5 curva, 5 istanze a distanza uguale: volume piastra + 5 semi, 5 cilindri",
           ok and near(v, PLATE_V + 5 * BOSS_V, absolute=0.01) and await count_cyl(c) == 5, f"vol {v:.3f} atteso {PLATE_V + 5 * BOSS_V:.3f}, cilindri {await count_cyl(c)}")
    record("B5 curva: posizioni y 10,30,50,70,90 (baricentro Y)", near(cm[1], await expected_com_y(c, ys), absolute=0.01),
           f"{cm[1]:.4f} atteso {await expected_com_y(c, ys):.4f}")
    record("B5 curva: allineamento tangente (0) riletto dalla feature", ok and d.get("definition", {}).get("D1AlignmentMethod") == 0,
           f"{d.get('definition')}")
    await discard_all(c)
    # --- passo fisso 15, 4 istanze, come l'originale
    seed, fp = await plate_boss(c)
    sk = await line_sketch(c, fp, (10, 10), (90, 10))
    ok, text, d = await c.call("curve_driven_pattern", features=[seed], curve=sk, count=4, equal_spacing=False, spacing=15, align="seed")
    cm = await com(c)
    ys = [10, 25, 40, 55]
    record("B5 curva, passo 15 x 4 istanze, allineamento al seme: volume + baricentro Y",
           ok and near(await vol(c), PLATE_V + 4 * BOSS_V, absolute=0.01) and near(cm[1], await expected_com_y(c, ys), absolute=0.01)
           and d.get("definition", {}).get("D1AlignmentMethod") == 1, f"vol {await vol(c):.3f}, y {cm[1]:.4f} atteso {await expected_com_y(c, ys):.4f}")
    ok, text, d = await c.call("curve_driven_pattern", features=[seed], curve=sk, count=1)
    record("B5 curva: count 1 rifiutato", not ok, text.split("\n")[0][:100])
    await discard_all(c)
    # --- curva = spigolo del modello (bordo inferiore della faccia x=5, y 0..100 a z=0): passo 30 -> istanze a y 40 e 70
    seed, fp = await plate_boss(c)
    res = None
    for rev in (False, True):
        ok, text, d = await c.call("curve_driven_pattern", features=[seed], curve={"edge": [5, 50, 0]}, count=3,
                                   equal_spacing=False, spacing=30, reverse=rev, align="seed")
        if ok:
            res = rev
            break
        await c.call("rebuild_model")
    cm = await com(c)
    record("B5 curva = spigolo del modello (passo 30): istanze a y 10, 40, 70", ok and near(await vol(c), PLATE_V + 3 * BOSS_V, absolute=0.01)
           and near(cm[1], await expected_com_y(c, [10, 40, 70]), absolute=0.01), f"reverse={res} y {cm[1]:.4f} atteso {await expected_com_y(c, [10, 40, 70]):.4f}")
    await discard_all(c)
    # --- da schizzo: 3 punti
    seed, fp = await plate_boss(c)
    info = await sketch_on(c, fp)
    for (y, z) in [(30, 10), (50, 30), (70, 40)]:
        u, v = uv(info, [5, y, z])
        await c.call("draw_point", x=u, y=v)
    await c.call("close_sketch")
    sk = (await feature_names(c, "ProfileFeature"))[-1]
    ok, text, d = await c.call("sketch_driven_pattern", features=[seed], sketch=sk)
    cm = await com(c)
    m = PLATE_V + 4 * BOSS_V
    exp_y = (PLATE_V * 50 + BOSS_V * (10 + 30 + 50 + 70)) / m
    exp_z = (PLATE_V * 30 + BOSS_V * (10 + 10 + 30 + 40)) / m
    record("B5 schizzo, 3 punti: 4 cilindri, volume piastra + 4 semi, baricentro (y, z)",
           ok and await count_cyl(c) == 4 and near(await vol(c), PLATE_V + 4 * BOSS_V, absolute=0.01) and near(cm[1], exp_y, absolute=0.01)
           and near(cm[2], exp_z, absolute=0.01), f"cil {await count_cyl(c)} vol {await vol(c):.3f} y {cm[1]:.4f}/{exp_y:.4f} z {cm[2]:.4f}/{exp_z:.4f}")
    ok, text, d = await c.call("sketch_driven_pattern", features=[seed], sketch="Schizzo che non esiste")
    record("B5 schizzo inesistente: rifiutato", not ok, text.split("\n")[0][:100])
    await discard_all(c)
    # --- da tabella: sistema di coordinate con Z = X del modello (x_cs = -z, y_cs = y): punti (-10,30), (-30,50) -> (y30,z10), (y50,z30)
    seed, fp = await plate_boss(c)
    okc, _, dc = await c.call("create_coordinate_system", origin=[0, 0, 0], rotation=[0, 90, 0])
    cs = dc.get("feature")
    ok, text, d = await c.call("table_driven_pattern", features=[seed], points=[[-10, 30], [-30, 50]], coordinate_system=cs)
    cm = await com(c)
    m = PLATE_V + 3 * BOSS_V
    exp_y = (PLATE_V * 50 + BOSS_V * (10 + 30 + 50)) / m
    exp_z = (PLATE_V * 30 + BOSS_V * (10 + 10 + 30)) / m
    record("B5 tabella, 2 punti nel sistema di coordinate: 3 cilindri, volume, baricentro (y, z)",
           ok and await count_cyl(c) == 3 and near(await vol(c), PLATE_V + 3 * BOSS_V, absolute=0.01) and near(cm[1], exp_y, absolute=0.01)
           and near(cm[2], exp_z, absolute=0.01), f"cil {await count_cyl(c)} vol {await vol(c):.3f} y {cm[1]:.4f}/{exp_y:.4f} z {cm[2]:.4f}/{exp_z:.4f}")
    ok, text, d = await c.call("table_driven_pattern", features=[seed], points=[[1000, 1000]], coordinate_system=cs)
    record("B5 tabella: punto fuori dal corpo: rifiutato", not ok, text.split("\n")[0][:110])
    ok, text, d = await c.call("table_driven_pattern", features=[seed], points=[[1, 2, 3]], coordinate_system=cs)
    record("B5 tabella: punto con 3 coordinate: rifiutato", not ok, text.split("\n")[0][:100])
    await discard_all(c)


# ===================================================================================================== principale
async def scenario(c):
    only = {a.upper() for a in sys.argv[1:]}
    for nome, fn in (("B1", b1_move), ("B2", b2_split), ("B3", b3_intersect), ("B4", b4_scale), ("B5", b5_patterns)):
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
                    "move_copy_body", "split_body", "intersect_bodies", "scale_body", "curve_driven_pattern",
                    "sketch_driven_pattern", "table_driven_pattern")), "")
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
