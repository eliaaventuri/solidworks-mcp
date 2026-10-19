"""
Test live del lotto FEATURE AVANZATE 2 (fillet_advanced, draft_advanced, dome, wrap_feature, thread_feature, flex_feature)
tramite il server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente non viene mai
toccata; alla fine si chiude solo il PID lanciato dal test.

  F1  fillet_advanced: arrotondamento completo (parete t=10), raccordo a facce, raggi multipli per spigolo, setback, errori
  F2  draft_advanced: sformo con linea di divisione (tronco di piramide calcolato a mano)
  F3  dome: calotta sferica, mezzo ellissoide, rientranza
  F4  wrap_feature: incisione, rilievo, tracciatura di un rettangolo su un cilindro
  F5  thread_feature: M10x1.5 (e M10x1) su albero, confronto con la stima ISO del volume dell'elica; Metric Tap su foro
  F6  flex_feature: flessione (volume conservato, inclinazione delle estremita'), allungamento, torsione, rastremazione

Uso:  .venv\\Scripts\\python.exe tests\\test_ext_features2_live.py [F1 F2 ...]
"""

import os
import sys
import math
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, PYTHON, SERVER, sw_pids, Client, cleanup

RESULTS = []         # (nome, PASS/FAIL, nota)
TOL = 0.002          # 0,2 % sui volumi


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:280])


def near(got, exp, tol=TOL, absolute=None):
    if absolute is not None:
        return abs(got - exp) <= absolute
    return abs(got - exp) <= tol * max(abs(exp), 1e-9)


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


async def wall(c):
    """Blocco x 0..10 (spessore t=10), y 0..60, z 0..40."""
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=0, x2=60, y2=40)
    ok, text, _ = await c.call("extrude_boss", depth=10)
    assert ok, text


async def bar(c, half=10, length=60):
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_rectangle", x1=-half, y1=-half, x2=half, y2=half)
    ok, text, _ = await c.call("extrude_boss", depth=length)
    assert ok, text


async def cylinder(c, r, h):
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_circle", x=0, y=0, radius=r)
    ok, text, _ = await c.call("extrude_boss", depth=h)
    assert ok, text


def dv(d):
    return d.get("volume_delta_mm3", 0.0)


K = 1 - math.pi / 4


# ===================================================================================================== F1
async def f1_fillets(c):
    print("\n== F1. fillet_advanced")
    t = 10.0
    L = 60.0
    await wall(c)
    ok, text, d = await c.call("fillet_advanced", mode="full_round", side_face1=[0, 30, 20], center_face=[5, 30, 40],
                               side_face2=[10, 30, 20])
    exp = t * t * (4 - math.pi) / 8 * L
    record("F1 arrotondamento completo: volume tolto = t^2 (4-pi)/8 L", ok and near(-dv(d), exp),
           f"{-dv(d):.3f} vs {exp:.3f} (semicerchio r=t/2 al posto del rettangolo t x t/2)")
    record("F1 arrotondamento completo: tipo riportato", d.get("fillet_type") == "full_round", str(d.get("fillet_type")))

    await wall(c)
    r = 4.0
    ok, text, d = await c.call("fillet_advanced", mode="faces", face_set1=[[5, 30, 40]], face_set2=[[10, 30, 20]], radius=r)
    exp = K * r * r * L
    record("F1 raccordo a facce perpendicolari: (1-pi/4) r^2 L", ok and near(-dv(d), exp), f"{-dv(d):.3f} vs {exp:.3f}")

    # raggi multipli: spigolo lungo y (L=60, r=2) e spigolo lungo z (L=40, r=4), senza vertici in comune
    await wall(c)
    ok, text, d = await c.call("fillet_advanced", mode="edges", edge_points=[[10, 30, 40], [0, 0, 20]], radii=[2, 4])
    exp = K * (2 * 2 * 60 + 4 * 4 * 40)
    record("F1 raggi multipli (2 su L=60, 4 su L=40): (1-pi/4) sum r^2 L", ok and near(-dv(d), exp),
           f"{-dv(d):.3f} vs {exp:.3f} (scambiati sarebbe {K * (4 * 4 * 60 + 2 * 2 * 40):.3f})")
    record("F1 raggi multipli: tipo riportato", d.get("fillet_type") == "multiple_radius", str(d.get("fillet_type")))

    await wall(c)
    ok, text, d = await c.call("fillet_advanced", mode="edges", edge_points=[[10, 30, 40]], radius=3)
    exp = K * 9 * 60
    record("F1 spigolo singolo raggio costante: (1-pi/4) r^2 L", ok and near(-dv(d), exp), f"{-dv(d):.3f} vs {exp:.3f}")

    # setback: tre spigoli concorrenti nel vertice (10,0,40) con r=2; piu' setback, piu' materiale tolto
    pts = [[10, 30, 40], [10, 0, 20], [5, 0, 40]]
    await wall(c)
    ok0, _, d0 = await c.call("fillet_advanced", mode="edges", edge_points=pts, radius=2)
    await wall(c)
    ok1, text1, d1 = await c.call("fillet_advanced", mode="edges", edge_points=pts, radius=2,
                                  setback={"vertex": [10, 0, 40], "distances": [4, 4, 4]})
    await wall(c)
    ok2, text2, d2 = await c.call("fillet_advanced", mode="edges", edge_points=pts, radius=2,
                                  setback={"vertex": [10, 0, 40], "distances": [8, 8, 8]})
    record("F1 setback: creato e diverso dal raccordo senza setback", ok0 and ok1 and ok2 and d1.get("fillet_type") == "setback"
           and abs(dv(d1) - dv(d0)) > 1.0, f"senza {dv(d0):.2f}, setback 4: {dv(d1):.2f}, setback 8: {dv(d2):.2f}")
    record("F1 setback crescente toglie piu' materiale", ok2 and -dv(d2) > -dv(d1) > -dv(d0), f"{-dv(d0):.2f} < {-dv(d1):.2f} < {-dv(d2):.2f}")

    # errori (su un blocco nuovo)
    await wall(c)
    ok, text, d = await c.call("fillet_advanced", mode="faces", face_set1=[[5, 30, 40]], radius=2)
    record("F1 errore: face_set2 mancante rifiutato", not ok, text.split("\n")[0][:100])
    ok, text, d = await c.call("fillet_advanced", mode="edges", edge_points=[[1, 2, 3]], radius=2)
    record("F1 errore: punto non sullo spigolo rifiutato", not ok, text.split("\n")[0][:100])
    ok, text, d = await c.call("fillet_advanced", mode="edges", edge_points=[[10, 30, 40]], radii=[1, 2])
    record("F1 errore: radii di lunghezza sbagliata rifiutato", not ok, text.split("\n")[0][:100])
    ok, text, d = await c.call("fillet_advanced", mode="bogus")
    record("F1 errore: mode sconosciuto rifiutato", not ok, text.split("\n")[0][:100])
    await discard_all(c)


# ===================================================================================================== F2
async def f2_draft(c):
    print("\n== F2. draft_advanced")
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_rectangle", x1=-30, y1=-30, x2=30, y2=30)
    await c.call("extrude_boss", depth=20)
    await c.call("create_sketch_on_face", x=0, y=0, z=20)
    await c.call("draw_rectangle", x1=-15, y1=-15, x2=15, y2=15)
    await c.call("extrude_boss", depth=20)
    ok, _, d0 = await c.call("get_mass_properties")
    v0 = d0.get("volume_mm3", 0.0)
    a = 5.0
    ok, text, d = await c.call("draft_advanced", direction={"face": [0, 0, 40]},
                               edge_points=[[15, 0, 20], [-15, 0, 20], [0, 15, 20], [0, -15, 20]], angle=a)
    s2 = 30 - 2 * 20 * math.tan(math.radians(a))
    frustum = 20 / 3 * (900 + s2 * s2 + 30 * s2)
    record("F2 sformo con linea di divisione: tronco di piramide 30 -> %.3f" % s2, ok and near(dv(d), frustum - 18000, 0.001),
           f"{dv(d):.3f} vs {frustum - 18000:.3f}")
    record("F2 volume finale = tronco + piastra", ok and near(d.get("volume_mm3", 0), 72000 + frustum, 0.001),
           f"{d.get('volume_mm3')} vs {72000 + frustum:.3f} (prima {v0:.1f})")
    ok, text, d = await c.call("draft_advanced", direction={"face": [0, 0, 40]}, edge_points=[[99, 0, 20]], angle=5)
    record("F2 errore: spigolo inesistente rifiutato", not ok, text.split("\n")[0][:100])
    ok, text, d = await c.call("draft_advanced", edge_points=[[15, 0, 20]])
    record("F2 errore: direction mancante rifiutato", not ok, text.split("\n")[0][:100])
    await discard_all(c)


# ===================================================================================================== F3
async def f3_dome(c):
    print("\n== F3. dome")
    r, h = 10.0, 5.0
    await cylinder(c, r, 20)
    ok, text, d = await c.call("dome", face_point=[0, 0, 20], height=h)
    R = (r * r + h * h) / (2 * h)
    cap = math.pi * h * h * (3 * R - h) / 3
    record("F3 cupola sferica: calotta pi h^2 (3R-h)/3", ok and near(dv(d), cap, 0.001), f"{dv(d):.3f} vs {cap:.3f} (R={R})")
    await cylinder(c, r, 20)
    ok, text, d = await c.call("dome", face_point=[0, 0, 20], height=h, elliptical=True)
    half = 2 / 3 * math.pi * r * r * h
    record("F3 cupola ellittica: mezzo ellissoide 2/3 pi r^2 h", ok and near(dv(d), half, 0.001), f"{dv(d):.3f} vs {half:.3f}")
    await cylinder(c, r, 20)
    ok, text, d = await c.call("dome", face_point=[0, 0, 20], height=h, reverse=True)
    record("F3 cupola rivolta all'interno (rientranza): -calotta", ok and near(dv(d), -cap, 0.001), f"{dv(d):.3f} vs {-cap:.3f}")
    ok, text, d = await c.call("dome", face_point=[0, 0, 0], height=0)
    record("F3 errore: altezza 0 rifiutata", not ok, text.split("\n")[0][:100])
    ok, text, d = await c.call("dome", face_point=[50, 50, 50], height=3)
    record("F3 errore: punto non su una faccia rifiutato", not ok, text.split("\n")[0][:100])
    await discard_all(c)


# ===================================================================================================== F4
async def wrap_scene(c, R=10.0):
    """Cilindro R, asse z, altezza 40; schizzo rettangolare (a=10 lungo y, b=8 lungo z) su un piano tangente x=R."""
    await cylinder(c, R, 40)
    ok, text, d = await c.call("create_reference_plane", mode="offset", base="front", distance=R)
    assert ok, text
    plane = d["feature"]
    ok, text, _ = await c.call("create_sketch", plane=plane)
    assert ok, text
    await c.call("draw_rectangle", x1=-5, y1=15, x2=5, y2=23)
    ok, text, d = await c.call("close_sketch")
    assert ok, text
    return None       # wrap_feature usa l'ultimo schizzo se `sketch` e' omesso


async def f4_wrap(c):
    print("\n== F4. wrap_feature")
    a, b, depth, R = 10.0, 8.0, 1.0, 10.0
    await wrap_scene(c, R)
    ok, text, d = await c.call("wrap_feature", face_point=[R, 0, 20], mode="engrave", depth=depth)
    exp = a * b * depth * (1 - depth / (2 * R))
    record("F4 incisione: a b d (1 - d/2R) (correzione per la curvatura)", ok and near(-dv(d), exp, 0.002),
           f"{-dv(d):.3f} vs {exp:.3f} (piatto sarebbe {a * b * depth:.1f})")
    await wrap_scene(c, R)
    ok, text, d = await c.call("wrap_feature", face_point=[R, 0, 20], mode="emboss", depth=depth)
    exp = a * b * depth * (1 + depth / (2 * R))
    record("F4 rilievo: a b d (1 + d/2R)", ok and near(dv(d), exp, 0.002), f"{dv(d):.3f} vs {exp:.3f}")
    await wrap_scene(c, R)
    ok, text, d = await c.call("wrap_feature", face_point=[R, 0, 20], mode="scribe")
    record("F4 tracciatura: feature creata, volume invariato, faccia divisa", ok and abs(dv(d)) < 1e-6 and d.get("feature")
           and d.get("faces_after", 0) > d.get("faces_before", 0), f"{d.get('feature')} delta {dv(d)} facce {d.get('faces_before')} -> {d.get('faces_after')}")
    ok, text, d = await c.call("wrap_feature", face_point=[R, 0, 20], mode="bogus")
    record("F4 errore: mode sconosciuto rifiutato", not ok, text.split("\n")[0][:100])
    ok, text, d = await c.call("wrap_feature", sketch="NonEsiste", face_point=[R, 0, 20])
    record("F4 errore: schizzo inesistente rifiutato", not ok, text.split("\n")[0][:100])
    await discard_all(c)


# ===================================================================================================== F5
def thread_estimate(D, P, L):
    """Volume asportato da un filetto ISO esterno (profilo base): area del vano trapezoidale x lunghezza dell'elica
    (giri L/P x circonferenza al baricentro del vano)."""
    H = math.sqrt(3) / 2 * P
    h = 5 / 8 * H
    w_out = P - P / 8        # larghezza del vano alla cresta (diametro maggiore)
    w_in = P / 4             # larghezza sul fondo (diametro minore)
    area = (w_out + w_in) / 2 * h
    cg = h * (w_in + 2 * w_out) / (3 * (w_in + w_out))      # baricentro dal lato largo
    rc = D / 2 - cg
    return area * (L / P) * 2 * math.pi * rc


async def f5_thread(c):
    print("\n== F5. thread_feature")
    D, L = 10.0, 20.0
    await cylinder(c, D / 2, 30)
    ok, text, d = await c.call("thread_feature", edge_point=[D / 2, 0, 30], size="M10x1.5", length=L)
    est = thread_estimate(D, 1.5, L)
    got = -dv(d)
    record("F5 M10x1.5 L=20 su albero D10: feature SweepThread creata", ok and d.get("feature_type") == "SweepThread",
           f"{d.get('feature')} {d.get('feature_type')}")
    record("F5 M10x1.5: volume asportato vs stima ISO (tol. 6 %)", ok and near(got, est, 0.06), f"{got:.2f} vs {est:.2f} mm3 ({(got / est - 1) * 100:+.1f} %)")
    record("F5 profilo 'Metric Die' scelto in automatico (albero), passo 1.5 dal nome", d.get("profile") == "Metric Die"
           and d.get("kind") == "external" and near(d.get("pitch_mm", 0), 1.5, absolute=1e-9), f"{d.get('profile')} {d.get('kind')} P={d.get('pitch_mm')}")
    got15 = got
    await cylinder(c, D / 2, 30)
    ok, text, d = await c.call("thread_feature", edge_point=[D / 2, 0, 30], size="M10x1", length=L)
    est1 = thread_estimate(D, 1.0, L)
    got1 = -dv(d)
    record("F5 M10x1 (passo fine, nome normalizzato in M10x1.0): volume vs stima ISO (tol. 6 %)",
           ok and d.get("size_used") == "M10x1.0" and near(got1, est1, 0.06), f"{got1:.2f} vs {est1:.2f} mm3 ({(got1 / est1 - 1) * 100:+.1f} %)")
    record("F5 il passo cambia il volume come previsto (M10x1 / M10x1.5)", ok and near(got1 / got15, est1 / est, 0.05),
           f"rapporto misurato {got1 / got15:.3f}, stimato {est1 / est:.3f}")
    # filetto esterno su albero in alto, verso opposto (reverse): fuori dal corpo, nessun effetto atteso o errore chiaro
    ok, text, d = await c.call("thread_feature", edge_point=[1, 2, 3], size="M10x1.5", length=L)
    record("F5 errore: punto non su uno spigolo rifiutato", not ok, text.split("\n")[0][:100])
    ok, text, d = await c.call("thread_feature", edge_point=[D / 2, 0, 0], size="M99x9", length=L)
    record("F5 errore: misura inesistente nel profilo rifiutata", not ok, text.split("\n")[0][:120])
    ok, text, d = await c.call("thread_feature", edge_point=[D / 2, 0, 0], size="M10x1.5", length=0)
    record("F5 errore: length 0 rifiutata", not ok, text.split("\n")[0][:100])
    await discard_all(c)

    # foro: Metric Tap interno (foro tracciato al diametro di maschiatura di M10x1.5 = 8.5 mm)
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_rectangle", x1=-15, y1=-15, x2=15, y2=15)
    await c.call("extrude_boss", depth=30)
    await c.call("create_sketch_on_face", x=0, y=0, z=30)
    await c.call("draw_circle", x=0, y=0, radius=4.25)
    await c.call("extrude_cut", depth=30)
    ok, text, d = await c.call("thread_feature", edge_point=[4.25, 0, 30], size="M10x1.5", length=15)
    record("F5 foro: profilo 'Metric Tap' scelto in automatico, filettatura creata e materiale asportato",
           ok and d.get("profile") == "Metric Tap" and d.get("kind") == "internal" and -dv(d) > 20.0,
           f"{d.get('profile')} {d.get('kind')} dV={dv(d):.2f}")
    await discard_all(c)


# ===================================================================================================== F6
async def end_normals(c):
    ok, _, d = await c.call("list_entities", kind="face", limit=40)
    out = []
    for e in d.get("entities", []):
        n = e.get("normal")
        if e.get("type") == "plane" and n and abs(n[2]) > 0.5:
            out.append((e["point"][2], n))
    return sorted(out)


async def f6_flex(c):
    print("\n== F6. flex_feature")
    # flessione 30 gradi: volume conservato entro 0.5 %, le due estremita' si inclinano di 15 gradi ciascuna
    await bar(c)
    ok, text, d = await c.call("flex_feature", mode="bending", amount=30, axis=[0, 0, 1], bend_axis=[1, 0, 0])
    ratio = d.get("volume_ratio", 0)
    record("F6 flessione 30 gradi: volume conservato entro 0,5 %", ok and abs(ratio - 1) < 0.005, f"rapporto volume {ratio:.5f} (delta {dv(d):.2f} mm3)")
    ends = await end_normals(c)
    tilts = [math.degrees(math.acos(min(1.0, abs(n[2])))) for z, n in ends]
    record("F6 flessione: le due estremita' inclinate di 15 gradi", len(tilts) == 2 and all(near(t, 15.0, absolute=0.3) for t in tilts),
           f"{[round(t, 3) for t in tilts]}")
    bb0, bb1 = d.get("bbox_before"), d.get("bbox_after")
    record("F6 flessione: ingombro cambiato, altezza lungo z oltre il corpo diritto", bb0 and bb1 and bb1[5] - bb1[2] > 60.0 + 3.0,
           f"{bb0} -> {bb1}")
    # allungamento: fattore 1.25 della zona (tutto il corpo) -> volume x 1.25, lunghezza 75
    await bar(c)
    ok, text, d = await c.call("flex_feature", mode="stretching", amount=1.25)
    bb1 = d.get("bbox_after") or [0] * 6
    record("F6 allungamento x1.25: volume x1.25", ok and near(d.get("volume_ratio", 0), 1.25, 0.002), f"{d.get('volume_ratio')} (V={d.get('volume_mm3')})")
    record("F6 allungamento x1.25: lunghezza 60 -> 75, sezione invariata", near(bb1[5] - bb1[2], 75.0, absolute=0.05)
           and near(bb1[3] - bb1[0], 20.0, absolute=0.01), f"{bb1}")
    # allungamento di una sola zona: pivot a z=30 e zona 10 + 10 mm (fattore 1.5 -> +10 mm di lunghezza) sul corpo da 60
    await bar(c)
    ok, text, d = await c.call("flex_feature", mode="stretching", amount=1.5, pivot=[0, 0, 30], trim_before=10, trim_after=10)
    bb1 = d.get("bbox_after") or [0] * 6
    record("F6 allungamento di una zona 20 mm x1.5: +10 mm di lunghezza", ok and near(bb1[5] - bb1[2], 70.0, absolute=0.05), f"{bb1[5] - bb1[2]:.3f}")
    # torsione 40 gradi: le estremita' ruotano di +-20 gradi (ingombro in pianta = 10 sqrt2 sin(65))
    await bar(c)
    ok, text, d = await c.call("flex_feature", mode="twisting", amount=40)
    bb1 = d.get("bbox_after") or [0] * 6
    exp = 10 * math.sqrt(2) * math.sin(math.radians(65))
    record("F6 torsione 40 gradi: ingombro in pianta = 10 sqrt2 sin 65", ok and near(bb1[3], exp, absolute=0.01), f"{bb1[3]:.4f} vs {exp:.4f}")
    record("F6 torsione: volume conservato entro 0,5 %", ok and abs(d.get("volume_ratio", 0) - 1) < 0.005, f"{d.get('volume_ratio')}")
    # rastremazione 0.5: estremita' scalate 1.25 e 0.75 -> volume x media(s^2) = 1.0208333
    await bar(c)
    ok, text, d = await c.call("flex_feature", mode="tapering", amount=0.5)
    bb1 = d.get("bbox_after") or [0] * 6
    exp_ratio = (0.75 ** 2 + 0.75 * 1.25 + 1.25 ** 2) / 3
    record("F6 rastremazione 0.5: estremita' scalate 1.25 (ingombro 12.5)", ok and near(bb1[3], 12.5, absolute=0.01), f"{bb1[3]:.4f}")
    record("F6 rastremazione 0.5: volume x (0.75^2 + 0.75 1.25 + 1.25^2)/3", ok and near(d.get("volume_ratio", 0), exp_ratio, 0.002),
           f"{d.get('volume_ratio')} vs {exp_ratio:.6f}")
    ok, text, d = await c.call("flex_feature", mode="bogus")
    record("F6 errore: mode sconosciuto rifiutato", not ok, text.split("\n")[0][:100])
    ok, text, d = await c.call("flex_feature", mode="bending", axis=[0, 0, 1], bend_axis=[0, 0, 1])
    record("F6 errore: axis e bend_axis paralleli rifiutati", not ok, text.split("\n")[0][:100])
    ok, text, d = await c.call("flex_feature", mode="stretching", amount=0)
    record("F6 errore: fattore di allungamento 0 rifiutato", not ok, text.split("\n")[0][:100])
    await discard_all(c)


# ===================================================================================================== principale
async def scenario(c):
    only = {a.upper() for a in sys.argv[1:]}
    for nome, fn in (("F1", f1_fillets), ("F2", f2_draft), ("F3", f3_dome), ("F4", f4_wrap), ("F5", f5_thread), ("F6", f6_flex)):
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
                    "fillet_advanced", "draft_advanced", "dome", "wrap_feature", "thread_feature", "flex_feature")), "")
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
        print(f"{res:5} {tool:80} {note}"[:280])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
