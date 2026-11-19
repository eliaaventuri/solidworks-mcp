"""
Test live dei falsi successi della revisione 2026-11-12, sezione 1 (punto 4 dell'ordine di lavoro): ogni controllo
confronta con SolidWorks un numero calcolato a mano. Scritti PRIMA delle correzioni: sul codice vecchio sono rossi.

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated); alla fine si chiude solo il PID
lanciato dal test.

  R1  schizzi: create_sketch_on_face con schizzo aperto, quote, split, relazioni rifiutate, arco per 3 punti,
      suddivisione su archi/cerchi, arco di ellisse ruotato, asole (aree), manubri delle spline, riparazione
  R2  feature        R3  tavole        R4  assiemi        R5  dati ed export        R6  simulazione

Uso:  .venv\\Scripts\\python.exe tests\\test_revisione_live.py [R1 R2 ...]
"""

import os
import sys
import math
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup

PI = math.pi
RESULTS = []


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:230])


def near(a, b, tol=1e-3):
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def pt_near(p, q, tol=1e-3):
    return p is not None and q is not None and all(abs(float(x) - float(y)) <= tol for x, y in zip(p, q))


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
    await discard_all(c)
    ok, text, _ = await c.call("create_new_part")
    assert ok, text


async def segments(c):
    ok, _, d = await c.call("list_sketch_entities")
    return d.get("segments", []) if ok else [], d.get("points", []) if ok else []


# ===================================================================================================== R1 schizzi
async def r1_schizzi(c):
    print("\n== R1. Schizzi")
    # -- create_sketch_on_face con uno schizzo gia' aperto: prima InsertSketch2 lo chiudeva e rispondeva successo
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-20, y1=-20, x2=20, y2=20)
    await c.call("extrude_boss", depth=10)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=30, y=30, radius=2)          # schizzo aperto, lasciato a meta'
    ok, text, _ = await c.call("create_sketch_on_face", x=10, y=0, z=0)     # faccia d'estremita' x=10 (estrusione lungo X)
    ok2, text2, _ = await c.call("draw_circle", x=0, y=0, radius=5)
    ok3, _, _ = await c.call("extrude_cut", end_condition="through_all")
    v = await vol(c)
    exp = 40 * 40 * 10 - PI * 25 * 10
    record("R1 create_sketch_on_face con schizzo aperto: schizzo nuovo sulla faccia (foro d10 passante)",
           ok and ok2 and ok3 and near(v, exp, 0.01), f"{text.split(chr(10))[0][:70]} | cerchio {ok2} | V {v:.3f} vs {exp:.3f}")

    # -- add_sketch_dimension: la quota nuova non tocca quella esistente
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    ok, _, l1 = await c.call("draw_line", x1=0, y1=0, x2=30, y2=0)
    ok, _, l2 = await c.call("draw_line", x1=0, y1=10, x2=25, y2=10)
    ok, _, d1 = await c.call("add_sketch_dimension", kind="length", entity1=l1.get("entity_id"), value=40)
    ok2, _, d2 = await c.call("add_sketch_dimension", kind="length", entity1=l2.get("entity_id"), value=33)
    segs, _ = await segments(c)
    lens = sorted(round(s.get("length_mm", 0), 3) for s in segs if s["type"] == "line")
    record("R1 add_sketch_dimension: due quote diverse, ognuna sulla sua linea (40 e 33 mm)",
           ok and ok2 and d1.get("dimension") != d2.get("dimension") and lens == [33.0, 40.0], f"{d1.get('dimension')} {d2.get('dimension')} {lens}")

    # -- split_sketch_entity: due linee 0..10 e 10..40, nessuna geometria persa
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    ok, _, ln = await c.call("draw_line", x1=0, y1=0, x2=40, y2=0)
    ok, text, d = await c.call("split_sketch_entity", entity=ln.get("entity_id"), x=10, y=0)
    segs, _ = await segments(c)
    got = sorted(sorted([tuple(s["start_mm"]), tuple(s["end_mm"])]) for s in segs if s["type"] == "line")
    record("R1 split_sketch_entity: linee (0,0)-(10,0) e (10,0)-(40,0)", ok and got == [[(0.0, 0.0), (10.0, 0.0)], [(10.0, 0.0), (40.0, 0.0)]],
           f"{got} nativa={d.get('native_split')}")

    # -- add_sketch_relation fra entita' dello schizzo: un rifiuto di SolidWorks era un successo
    ok, _, a = await c.call("draw_line", x1=0, y1=20, x2=30, y2=20)
    ok, _, b = await c.call("draw_line", x1=0, y1=30, x2=30, y2=45)
    ok, text, d = await c.call("add_sketch_relation", relation="concentric", entity1=a.get("entity_id"), entity2=b.get("entity_id"))
    record("R1 add_sketch_relation concentrica fra due linee: rifiutata (SolidWorks non la crea)", not ok, text.split("\n")[0][:120])
    ok, text, d = await c.call("add_sketch_relation", relation="parallel", entity1=a.get("entity_id"), entity2=b.get("entity_id"))
    segs, _ = await segments(c)
    bb = next((s for s in segs if s["id"] == b.get("entity_id")), None)
    record("R1 add_sketch_relation parallela: accettata e la seconda linea diventa orizzontale",
           ok and bb is not None and near(bb["start_mm"][1], bb["end_mm"][1], 1e-3), text.split("\n")[0][:100])

    # -- draw_arc_3point: estremi = punto 1 e punto 3, (x2,y2) sull'arco
    await c.call("close_sketch")
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    ok, _, d = await c.call("draw_arc_3point", x1=0, y1=0, x2=10, y2=10, x3=20, y3=0)
    segs, _ = await segments(c)
    arc = next((s for s in segs if s["type"] == "arc"), {})
    ends = sorted([tuple(arc.get("start_mm", [])), tuple(arc.get("end_mm", []))])
    record("R1 draw_arc_3point: estremi (0,0) e (20,0), centro (10,0), raggio 10",
           ok and ends == [(0.0, 0.0), (20.0, 0.0)] and pt_near(arc.get("center_mm"), [10, 0]) and near(arc.get("radius_mm"), 10),
           f"estremi {ends} centro {arc.get('center_mm')} r {arc.get('radius_mm')}")

    # -- segment_sketch_entity: punti SULL'arco (prima sulla corda) e linee divise in parti uguali
    ok, _, ar = await c.call("draw_arc", cx=0, cy=50, radius=20, start_angle=0, end_angle=90)
    if not ok:
        ok, _, ar = await c.call("draw_centerpoint_arc", cx=0, cy=50, radius=20, start_angle=0, end_angle=90)
    _, pts0 = await segments(c)
    ok, text, d = await c.call("segment_sketch_entity", entity=ar.get("entity_id"), count=3)
    _, pts1 = await segments(c)
    new = [p["mm"] for p in pts1 if p["id"] not in {q["id"] for q in pts0}]
    want = [[20 * math.cos(math.radians(a)), 50 + 20 * math.sin(math.radians(a))] for a in (30, 60)]
    record("R1 segment_sketch_entity arco 0-90 gradi in 3: punti a 30 e 60 gradi sull'arco",
           ok and len(new) == 2 and all(any(pt_near(n, w, 2e-3) for n in new) for w in want),
           f"{[[round(x, 3) for x in n] for n in new]} attesi {[[round(x, 3) for x in w] for w in want]}")
    ok, _, ln = await c.call("draw_line", x1=-60, y1=0, x2=-30, y2=0)
    s0, _ = await segments(c)
    ok, text, d = await c.call("segment_sketch_entity", entity=ln.get("entity_id"), count=3, is_segments=True)
    s1, _ = await segments(c)
    parts = sorted(round(s.get("length_mm", 0), 3) for s in s1 if s["type"] == "line" and s["start_mm"][1] == 0 and s["start_mm"][0] <= -30)
    record("R1 segment_sketch_entity linea 30 mm in 3 segmenti: 10 + 10 + 10", ok and len(s1) - len(s0) == 2 and parts == [10.0, 10.0, 10.0],
           f"{text.split(chr(10))[0][:80]} {parts}")
    ok, _, cc = await c.call("draw_circle", x=-50, y=60, radius=10)
    _, pts0 = await segments(c)
    ok, text, d = await c.call("segment_sketch_entity", entity=cc.get("entity_id"), count=4)
    _, pts1 = await segments(c)
    new = [p["mm"] for p in pts1 if p["id"] not in {q["id"] for q in pts0}]
    record("R1 segment_sketch_entity cerchio r10 in 4: 4 punti sul cerchio",
           ok and len(new) == 4 and all(near(math.hypot(n[0] + 50, n[1] - 60), 10, 2e-3) for n in new), str(new))

    # -- draw_elliptical_arc con asse maggiore inclinato a 45 gradi: estremi (10,10) e (-10,-10)
    await c.call("close_sketch")
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    ok, text, d = await c.call("draw_elliptical_arc", cx=0, cy=0, major_x=10, major_y=10, minor_r=5, start_angle=0, end_angle=180)
    segs, _ = await segments(c)
    el = next((s for s in segs if s["type"] == "ellipse"), {})
    ends = [el.get("start_mm"), el.get("end_mm")]
    record("R1 draw_elliptical_arc ruotato 45 gradi: estremi (10,10) e (-10,-10)",
           ok and any(pt_near(e, [10, 10], 2e-3) for e in ends) and any(pt_near(e, [-10, -10], 2e-3) for e in ends), f"{ends}")

    # -- asole: area misurata estrudendo 1 mm
    area_line, area_overall = 20 * 4 + PI * 4, 16 * 4 + PI * 4
    area_arc = 4 * (PI * 20 / 2) + PI * 4
    casi = [("draw_slot center_to_center 20 c-c", "draw_slot", dict(x1=-10, y1=0, x2=10, y2=0, width=4), area_line),
            ("draw_slot overall 20 totale", "draw_slot", dict(x1=-10, y1=0, x2=10, y2=0, width=4, slot_type="overall"), area_overall),
            ("draw_centerpoint_slot length 20", "draw_centerpoint_slot", dict(cx=0, cy=0, length=20, width=4), area_line),
            ("draw_arc_slot r20 0-90", "draw_arc_slot", dict(cx=0, cy=0, radius=20, width=4, start_angle=0, end_angle=90), area_arc),
            ("draw_3point_arc_slot r20 0-90", "draw_3point_arc_slot",
             dict(x1=20, y1=0, x2=0, y2=20, x3=20 * math.cos(PI / 4), y3=20 * math.sin(PI / 4), width=4), area_arc)]
    for label, tool, args, area in casi:
        await c.call("close_sketch")
        await new_part(c)
        await c.call("create_sketch", plane="Front")
        ok, text, _ = await c.call(tool, **args)
        ok2, _, _ = await c.call("extrude_boss", depth=1)
        v = await vol(c)
        record(f"R1 {label}: area {area:.3f} mm2", ok and ok2 and near(v, area, 0.01), f"V {v:.4f} | {text.split(chr(10))[0][:80]}")

    # -- edit_spline_handle: valore riletto
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    ok, _, sp = await c.call("draw_spline", points=[[0, 0], [20, 15], [40, 0], [60, 10]])
    ok, text, d = await c.call("edit_spline_handle", point_index=1, radial_angle_deg=30, spline_entity=sp.get("entity_id"))
    record("R1 edit_spline_handle: direzione radiale 30 gradi riletta dal manubrio",
           ok and near((d.get("read_back") or {}).get("radial_angle_deg"), 30, 0.01), text.split("\n")[0][:140])
    # misurato 2026-11-19: la magnitudine scritta (1,5) viene ricalcolata da SolidWorks (rilettura 0,546): deve essere un errore
    ok, text, d = await c.call("edit_spline_handle", point_index=1, magnitude=1.5, spline_entity=sp.get("entity_id"))
    record("R1 edit_spline_handle magnitudine: SolidWorks la ricalcola -> errore con il valore riletto (non un successo finto)",
           not ok and "magnitude" in text, text.split("\n")[0][:140])

    # -- testo lungo un arco (curva selezionata con Mark 1, come chiede la guida dell'API): altezza riletta + immagine da guardare
    await c.call("close_sketch")
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    ok, _, ar = await c.call("draw_arc", cx=0, cy=0, radius=30, start_angle=0, end_angle=180)
    ok, text, d = await c.call("draw_sketch_text_along_curve", text="SOLIDWORKS MCP", curve_entity=ar.get("entity_id"), height=6)
    record("R1 draw_sketch_text_along_curve su un arco: altezza 6 mm riletta", ok and near(d.get("height_mm"), 6, 1e-4),
           f"{text.split(chr(10))[0][:100]} | punto {d.get('insertion_point_mm')}")
    await c.call("close_sketch")
    # il testo estruso di 1 mm: se segue l'arco (r 30, da 0 a 180 gradi) l'ingombro e' alto ~30 mm e largo ~60; se fosse
    # dritto nell'origine sarebbe alto ~6 mm (l'altezza del carattere)
    ok_e, text_e, _ = await c.call("extrude_boss", depth=1)
    ok_b, _, bb = await c.call("get_bounding_box")
    size = bb.get("size") or [0, 0, 0]
    record("R1 testo lungo l'arco estruso: ingombro che segue l'arco (lato maggiore > 40 mm, altezza > 15 mm)",
           ok_e and ok_b and sorted(size)[-1] > 40 and sorted(size)[-2] > 15, f"ingombro {size} | {text_e.split(chr(10))[0][:70]}")

    # -- repair_sketch: fessura di 0,03 mm chiusa e linea doppia tolta -> contorno chiuso
    await c.call("close_sketch")
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    ok0, _, prev = await c.call("set_sketch_performance_mode", add_to_db=True, auto_solve=True, auto_inference=False)
    for (x1, y1, x2, y2) in ((0, 0, 20, 0), (20, 0, 20, 20), (20, 20, 0, 20), (0, 20, 0, 0.03), (20, 0, 20, 20)):
        await c.call("draw_line", x1=x1, y1=y1, x2=x2, y2=y2)
    old = (prev or {}).get("previous") or {}
    await c.call("set_sketch_performance_mode", add_to_db=old.get("add_to_db", False), auto_solve=old.get("auto_solve", True),
                 auto_inference=old.get("auto_inference", True))
    ok, text, d = await c.call("repair_sketch", gap_tolerance=0.05)
    record("R1 repair_sketch: fessura chiusa, doppione tolto, 1 contorno chiuso e 0 aperti",
           ok and d.get("gaps_closed", 0) >= 1 and d.get("duplicates_removed") == 1 and d.get("closed_contours") == 1
           and d.get("open_contours") == 0, text.split("\n")[0][:160])
    ok2, _, _ = await c.call("extrude_boss", depth=1)
    v = await vol(c)
    record("R1 repair_sketch: il profilo riparato si estrude (20 x 20 x 1, a meno di 20 x 0,03 mm2)", ok2 and near(v, 400, 0.65), f"V {v:.4f}")
    await c.call("close_sketch")
    await discard_all(c)


# ===================================================================================================== R2 feature
async def box(c, x1=-20, y1=-20, x2=20, y2=20, depth=10):
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=x1, y1=y1, x2=x2, y2=y2)
    ok, text, _ = await c.call("extrude_boss", depth=depth)
    assert ok, text


async def r2_feature(c):
    print("\n== R2. Feature")
    # -- ripetizione lineare di CORPI: numero di corpi esatto (prima bastava che aumentassero)
    await box(c, -5, -5, 5, 5, 10)                       # x 0..10, y e z -5..5
    ok, text, d = await c.call("linear_pattern", bodies=[[10, 0, 0]], direction1={"edge": [5, 5, 5]}, count1=3, spacing1=20)
    ok2, _, lb = await c.call("list_bodies", unit="mm")
    nb = len(lb.get("bodies", [])) if ok2 else -1
    v = await vol(c)
    record("R2 linear_pattern di corpi x3: 3 corpi, volume 3 x 1000", ok and nb == 3 and near(v, 3000, 0.01),
           f"corpi {nb}, V {v:.3f} | {text.split(chr(10))[0][:90]}")

    # -- _safe_select: un punto a 10 mm dalla faccia NON deve selezionarla (prima tolleranza 50 mm)
    await box(c, -20, -20, 20, 20, 10)
    ok, text, _ = await c.call("cross_break", face_point=[20, 0, 0], depth=1.0, break_angle=2.0)   # faccia x=10, punto a x=20
    record("R2 cross_break con punto a 10 mm dalla faccia: rifiutato", not ok, text.split("\n")[0][:120])
    await box(c, -60, -40, 60, 40, 30)
    ok, text, d = await c.call("convert_to_sheet_metal", thickness=2.0, bend_radius=2.5, fixed_face_point=[15, 0, 40])
    v = await vol(c)
    record("R2 convert_to_sheet_metal, punto ESATTO sulla faccia 120x30 (z=40): volume 120 x 30 x 2", ok and near(v, 7200, 1.0),
           f"V {v:.2f} | {text.split(chr(10))[0][:100]}")

    # -- thread_feature: misura e lunghezza rilette e confrontate
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=5)
    await c.call("extrude_boss", depth=30)
    ok, text, d = await c.call("thread_feature", edge_point=[30, 5, 0], size="M10x1.5", length=15)
    record("R2 thread_feature M10x1.5 lunga 15: misura e lunghezza rilette uguali",
           ok and str(d.get("size", "")).lower() == "m10x1.5" and near(d.get("depth"), 15, 1e-3), text.split("\n")[0][:140])

    # -- lamiera: K non tenuto da SolidWorks -> rifiuto; sm_parameters riletto; taglio normale senza depth = passante
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-50, y1=-30, x2=50, y2=30)
    ok, text, d = await c.call("sm_base_flange", thickness=2, bend_radius=2, k_factor=0.4)
    nf = 0
    ok_l, _, lf = await c.call("list_features", detail=True)
    if ok_l:
        nf = sum(1 for f in lf.get("features", []) if str(f.get("type")) in ("SMBaseFlange", "SheetMetal"))
    record("R2 sm_base_flange k_factor 0.4: rifiutata (SolidWorks tiene 0.5) e nessuna flangia rimasta", not ok and nf == 0,
           f"{text.split(chr(10))[0][:120]} | feature lamiera {nf}")
    await c.call("close_sketch")
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-50, y1=-30, x2=50, y2=30)
    ok, text, d = await c.call("sm_base_flange", thickness=2, bend_radius=2)
    record("R2 sm_base_flange 100x60x2: volume 12000", ok and near(await vol(c), 12000, 0.5), text.split("\n")[0][:100])
    ok, text, d = await c.call("sm_parameters", thickness=3)
    record("R2 sm_parameters spessore 3: riletto 3 e volume 18000", ok and near(d.get("thickness_mm"), 3, 1e-4) and near(await vol(c), 18000, 0.5),
           text.split("\n")[0][:120])
    ok_f, text_f, _ = await c.call("create_sketch_on_face", x=0, y=0, z=0)
    await c.call("draw_circle", x=0, y=0, radius=5)
    v0 = await vol(c)
    ok, text, d = await c.call("sm_normal_cut")
    v1 = await vol(c)
    record("R2 sm_normal_cut senza depth: foro d10 passante nello spessore 3 (pi x 25 x 3)", ok and near(v0 - v1, PI * 25 * 3, 0.05),
           f"tolti {v0 - v1:.3f} | {text.split(chr(10))[0][:100]} | faccia {ok_f}")

    # -- weldment_cut_list: due tubi 40x40 con spessori diversi e stesso ingombro = 2 voci
    await new_part(c)
    pairs = None
    sq = []
    ok, _, lp = await c.call("list_weldment_profiles", standard="iso", profile="square tube")
    sq = [z for st in (lp.get("standards", []) if ok else []) for pr in st.get("profiles", []) for z in pr.get("sizes", [])]
    ok, _, la = await c.call("list_weldment_profiles", standard="iso", profile="angle iron")
    an = [z for st in (la.get("standards", []) if ok else []) for pr in st.get("profiles", []) for z in pr.get("sizes", [])]
    for z in sq:
        pre = str(z).rsplit("x", 1)[0].strip()                 # "40 x 40"
        match = next((w for w in an if str(w).rsplit("x", 1)[0].strip() == pre), None)
        if match:
            pairs = (z, match)
            break
    if pairs:
        await c.call("create_sketch", plane="Front")
        ok, _, a_ = await c.call("draw_line", x1=0, y1=0, x2=300, y2=0)
        ok, _, b_ = await c.call("draw_line", x1=0, y1=200, x2=300, y2=200)
        await c.call("close_sketch")
        await c.call("structural_member", segments=[a_.get("entity_id")], standard="iso", profile="square tube", size=pairs[0])
        await c.call("structural_member", segments=[b_.get("entity_id")], standard="iso", profile="angle iron", size=pairs[1])
        ok, text, d = await c.call("weldment_cut_list", update=True)
        items = d.get("items", []) if ok else []
        record(f"R2 weldment_cut_list tubo {pairs[0]} + angolare {pairs[1]} (stesso ingombro): 2 voci da 1",
               ok and len(items) == 2 and sorted(i["quantity"] for i in items) == [1, 1], f"{text.split(chr(10))[0][:120]}")
    else:
        record("R2 weldment_cut_list: tubo quadro e angolare con lo stesso ingombro nella libreria ISO", False, f"{sq} / {an}")

    # -- get_rebuild_errors con ricostruzione forzata
    await box(c)
    ok, text, d = await c.call("get_rebuild_errors", force_rebuild=True)
    record("R2 get_rebuild_errors force_rebuild: ricostruzione riuscita e nessun errore",
           ok and d.get("rebuild_ok") is True and d.get("force_rebuild_result") is True, text.split("\n")[0][:120])

    # -- zebra_stripes_display: stato impostato e riletto (prima COMMUTAVA)
    ok1, t1, d1 = await c.call("zebra_stripes_display", enable=True)
    ok2, t2, d2 = await c.call("zebra_stripes_display", enable=True)
    ok3, t3, d3 = await c.call("zebra_stripes_display", enable=False)
    record("R2 zebra_stripes_display: on, on, off -> riletto acceso, acceso, spento",
           ok1 and ok2 and ok3 and d1.get("enabled") is True and d2.get("enabled") is True and d3.get("enabled") is False,
           f"{d1.get('enabled')} {d2.get('enabled')} {d3.get('enabled')} | {t3.split(chr(10))[0][:60]}")
    await discard_all(c)


# ===================================================================================================== R3 tavole
async def r3_drawing(c, part, name, note=None):
    drw = OUT / f"{name}.SLDDRW"
    if drw.exists():
        drw.unlink()
    ok, text, _ = await c.call("create_drawing", model_path=str(part), paper_size="A3", save_as=str(drw), add_views=False)
    await c.call("add_standard_views", views=["front", "top", "right"])
    if note:
        await c.call("add_note", text=note, x=40, y=40, height=3.5)
    await c.call("insert_model_dimensions", all_views=True)
    return ok


async def r3_tavole(c):
    print("\n== R3. Tavole")
    part = OUT / "rev_r3_pezzo.SLDPRT"
    await box(c, -40, -25, 40, 25, 20)                   # x 0..20, y -40..40, z -25..25
    ok_ch, text_ch, _ = await c.call("chamfer_at_points", distance=2, edge_points=[[20, 0, 25]])
    if part.exists():
        part.unlink()
    await c.call("save_document", filepath=str(part))
    record("R3 setup: blocco 80x50x20 con smusso 2 mm", ok_ch and part.exists(), text_ch.split("\n")[0][:100])

    # -- list_drawing_dimensions: i valori sono in mm (prima x1000: 80 mm -> 80000). Le quote di smusso (tolte solo a nota
    #    fatta) non vengono importate su questo pezzo: quel percorso lo prova test_drawing_quality (nota degli smussi).
    await r3_drawing(c, part, "rev_r3_a")
    ok, text, ld = await c.call("list_drawing_dimensions")
    vals = sorted({round(x.get("value_mm", 0), 3) for x in ld.get("dimensions", [])}) if ok else []
    record("R3 list_drawing_dimensions: valori in mm (le misure del blocco 80/50/20, non x1000)",
           ok and vals and max(vals) <= 100 and any(near(v_, 80, 1e-3) for v_ in vals), str(vals))
    ok, text, d = await c.call("arrange_drawing_dimensions")
    record("R3 arrange_drawing_dimensions: riordino riuscito", ok, text.split("\n")[0][:120])

    # -- set_sheet_properties: scala non riconosciuta = errore (prima ignorata con successo)
    ok, text, d = await c.call("set_sheet_properties", scale="abc")
    record("R3 set_sheet_properties scale='abc': rifiutata", not ok, text.split("\n")[0][:100])
    ok, text, d = await c.call("set_sheet_properties", scale="1:5")
    record("R3 set_sheet_properties scala 1:5: riletta", ok and d.get("scale") == "1:5", text.split("\n")[0][:100])

    # -- audit_drawing: sola lettura, foglio attivo ripristinato, formato riconosciuto dal file del formato
    ok, _, ls = await c.call("list_sheets")
    first = ls["sheets"][0]["name"] if ok and ls.get("sheets") else None
    await c.call("add_sheet", name="Foglio2", paper_size="A4", orientation="portrait", scale="1:1")
    await c.call("activate_sheet", name=first)
    ok, text, d = await c.call("audit_drawing", sheet="Foglio2")
    ok2, _, ls = await c.call("list_sheets")
    active = next((s["name"] for s in ls.get("sheets", []) if s.get("active")), None)
    record("R3 audit_drawing di Foglio2 con attivo il primo foglio: il foglio attivo resta il primo",
           ok and active == first, f"attivo dopo l'audit: {active} (atteso {first})")
    ok, text, d = await c.call("audit_drawing")
    tb = ((d.get("checks") or {}).get("title_block") or {}) if ok else {}
    record("R3 audit_drawing: formato riconosciuto dal file del formato del foglio", ok and tb.get("has_format") is True
           and str(tb.get("format_file") or "").lower().endswith(".slddrt"), f"{tb}")
    await discard_all(c)


# ===================================================================================================== R4 assiemi
async def r4_assiemi(c):
    print("\n== R4. Assiemi")
    blk = OUT / "rev_r4_blocco.SLDPRT"
    cyl = OUT / "rev_r4_cil.SLDPRT"
    await box(c, -20, -20, 20, 20, 10)                   # x 0..10, y e z -20..20
    for p in (blk, cyl):
        if p.exists():
            p.unlink()
    await c.call("save_document", filepath=str(blk))
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=5)
    await c.call("extrude_boss", depth=40)
    await c.call("save_document", filepath=str(cyl))
    await discard_all(c)

    # -- accoppiamento in conflitto: errore E nessun accoppiamento rimasto nel modello
    await c.call("create_new_assembly")
    await c.call("insert_component", file_path=str(blk), x=0, y=0, z=0, fixed=True)
    await c.call("insert_component", file_path=str(blk), x=30, y=0, z=0)
    _, _, lc = await c.call("list_components")
    names = [x.get("name") for x in lc.get("components", [])]
    b1, b2 = (names + [None, None])[:2]
    ok, text, _ = await c.call("add_mate", mate_type="coincident", entity1={"component": b1, "face": [10, 0, 0]},
                               entity2={"component": b2, "face": [30, 0, 0]}, align="anti_aligned")
    record("R4 setup: coincidente fra i due blocchi", ok, text.split("\n")[0][:100])
    _, _, lm0 = await c.call("list_mates")
    ok, text, d = await c.call("add_mate", mate_type="distance", entity1={"component": b1, "face": [10, 0, 0]},
                               entity2={"component": b2, "face": [10, 0, 0]}, distance=5)
    _, _, lm1 = await c.call("list_mates")
    record("R4 add_mate distanza in conflitto: errore e accoppiamento eliminato (conteggio invariato)",
           not ok and lm1.get("count") == lm0.get("count") and not lm1.get("in_error"),
           f"{text.split(chr(10))[0][:110]} | {lm0.get('count')} -> {lm1.get('count')}")
    await discard_all(c)

    # -- vite: passo riletto dal modello
    await c.call("create_new_assembly")
    await c.call("insert_component", file_path=str(cyl), x=0, y=0, z=0, fixed=True)
    await c.call("insert_component", file_path=str(cyl), x=0, y=30, z=0)
    _, _, lc = await c.call("list_components")
    names = [x.get("name") for x in lc.get("components", [])]
    c1, c2 = (names + [None, None])[:2]
    await c.call("add_mate", mate_type="concentric", entity1={"component": c1, "face": [20, 5, 0]},
                 entity2={"component": c2, "face": [20, 35, 0]})
    ok, text, d = await c.call("add_mate", mate_type="screw", entity1={"component": c1, "face": [20, 5, 0]},
                               entity2={"component": c2, "face": [20, 5, 0]}, pitch=2)
    record("R4 add_mate vite passo 2 mm/giro: passo riletto 2", ok and near(d.get("pitch_mm_per_rev"), 2, 1e-6),
           text.split("\n")[0][:120])
    await discard_all(c)


# ===================================================================================================== R5 dati ed export
async def r5_dati(c):
    print("\n== R5. Dati ed export")
    await box(c)
    p3 = OUT / "rev_r5.3mf"
    if p3.exists():
        p3.unlink()
    ok, text, d = await c.call("export_model", filepath=str(p3), units="cm")
    record("R5 export_model 3MF con units='cm': rifiutato (le unita' del 3MF non si impostano via API)", not ok and not p3.exists(),
           text.split("\n")[0][:120])
    ok, text, d = await c.call("export_model", filepath=str(p3))
    record("R5 export_model 3MF senza opzioni: file scritto e verificato", ok and p3.exists(), text.split("\n")[0][:100])
    ps = OUT / "rev_r5.stl"
    if ps.exists():
        ps.unlink()
    ok, text, d = await c.call("export_model", filepath=str(ps), quality="custom", deviation=0.05, angle=5)
    record("R5 export_model STL personalizzato: preferenze globali rilette e ripristinate", ok and not d.get("preferences_not_restored"),
           text.split("\n")[0][:100])
    await discard_all(c)


# ===================================================================================================== R6 simulazione
async def r6_simulazione(c):
    print("\n== R6. Simulazione")
    ok, text, d = await c.call("simulation_status")
    if not ok:
        record("R6 Simulation disponibile", False, text[:100])
        return
    await box(c, -5, -5, 5, 5, 100)                       # trave x 0..100, sezione 10 x 10
    await c.call("assign_material", material="AISI 1020")
    trave = OUT / "rev_r6_trave.SLDPRT"                   # Simulation lavora solo su documenti salvati
    if trave.exists():
        trave.unlink()
    await c.call("save_document", filepath=str(trave))
    ok, text, _ = await c.call("create_static_study", name="Rev6")
    record("R6 setup: studio statico creato sulla trave salvata", ok, text.split("\n")[0][:100])
    await c.call("add_restraint", kind="fixed", faces=[[0, 0, 0]])
    await c.call("add_force", faces=[[100, 0, 0]], value=1000, mode="direction", direction=[0, 0, -1])
    ok, text, d = await c.call("add_gravity", direction=[0, 0, -1])
    rb = d.get("read_back") if ok else None
    record("R6 add_gravity: accelerazione riletta dallo studio (modulo 9.80665, nel riferimento del piano)",
           ok and rb is not None and near(sum(x * x for x in rb) ** 0.5, 9.80665, 1e-4), str(rb))
    await c.call("create_simulation_mesh", element_size=5, mesher="standard")
    ok, text, d = await c.call("run_simulation", timeout=300)
    record("R6 run_simulation: completata, risultati presenti e messaggi finali letti", ok and d.get("steps", 0) >= 1 and "dialogs" in d,
           text.split("\n")[0][:100])
    ok, text, d = await c.call("get_simulation_results")
    rf = (d.get("reaction_force_N") or {}) if ok else {}
    w = 7900 * 1e-5 * 9.80665
    record("R6 reazioni lette: Rz = 1000 N + peso (%.3f N)" % w, ok and near(rf.get("z"), 1000 + w, 2.0),
           f"{rf} | {d.get('reaction_error', '')}")
    ok, text, d = await c.call("get_reaction_forces_detail", face_point=[[0, 0, 0]], step=1)
    record("R6 get_reaction_forces_detail sulla faccia vincolata (step 1): Fz = reazione totale",
           ok and near(d.get("fz_n"), rf.get("z"), 0.5), text.split("\n")[0][:110])
    ok, text, d = await c.call("probe_simulation_results", x=50, y=0, z=5, step=2)
    record("R6 probe_simulation_results con step 2 su uno studio statico (1 passo): rifiutato", not ok and "non disponibile" in text,
           text.split("\n")[0][:100])
    await discard_all(c)


# ===================================================================================================== R7 superfici 3 (sez. 5)
async def tube_with_caps(c):
    """Tubo superficie 20x10 lungo 30 (X 0..30, Y 0..20, Z 0..10) chiuso alle due estremita' con due superfici piane."""
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=0, x2=20, y2=10)
    await c.call("close_sketch")
    ok1, t1, _ = await c.call("extrude_surface", depth=30)
    ok2, t2, _ = await c.call("planar_surface", edge_points=[[30, 10, 0], [30, 20, 5], [30, 10, 10], [30, 0, 5]])
    ok3, t3, _ = await c.call("planar_surface", edge_points=[[0, 10, 0], [0, 20, 5], [0, 10, 10], [0, 0, 5]])
    return ok1 and ok2 and ok3, " | ".join(x.split("\n")[0][:50] for x in (t1, t2, t3))


async def r7_superfici(c):
    print("\n== R7. Superfici 3 (cuci, ispessisci, offset, elimina faccia)")
    ok0, t0 = await tube_with_caps(c)
    record("R7 setup: tubo superficie 20x10x30 chiuso da due piane", ok0, t0)
    ok, text, d = await c.call("knit_surfaces", form_solid=True)
    v = await vol(c)
    record("R7 knit_surfaces form_solid: un solido di 20 x 10 x 30 = 6000 mm3", ok and d.get("solid_bodies") == 1 and near(v, 6000, 0.5),
           f"V {v:.3f} | {text.split(chr(10))[0][:100]}")
    ok0, _ = await tube_with_caps(c)
    ok, text, d = await c.call("knit_surfaces")
    record("R7 knit_surfaces senza solido: 3 corpi superficie -> 1", ok and d.get("surface_bodies_before") == 3 and d.get("surface_bodies") == 1,
           text.split("\n")[0][:120])

    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=0, x2=20, y2=10)
    await c.call("close_sketch")
    okp, tp, _ = await c.call("planar_surface")
    record("R7 setup: superficie piana 20x10", okp, tp.split("\n")[0][:80])
    ok, text, d = await c.call("thicken_surface", face_point=[0, 10, 5], thickness=3)
    v = await vol(c)
    record("R7 thicken_surface 20x10 di 3 mm: volume 600", ok and near(v, 600, 0.05), f"V {v:.3f} | {text.split(chr(10))[0][:100]}")

    await box(c, -10, -5, 10, 5, 30)                     # x 0..30, y -10..10, z -5..5
    ok, text, d = await c.call("offset_surface", face_points=[[30, 0, 0]], distance=5)
    record("R7 offset_surface della faccia 20x10 a 5 mm: nuova superficie di 200 mm2",
           ok and near(d.get("new_surface_area_mm2"), 200, 0.01), text.split("\n")[0][:120])

    await box(c, -20, -20, 20, 20, 10)                   # x 0..10
    await c.call("create_sketch_on_face", x=10, y=0, z=0)
    await c.call("draw_circle", x=0, y=0, radius=3)
    await c.call("extrude_cut", end_condition="through_all")
    v0 = await vol(c)
    ok, text, d = await c.call("delete_face", face_points=[[5, 3, 0]], mode="patch")
    v1 = await vol(c)
    record("R7 delete_face patch sul foro d6: foro richiuso, volume 40 x 40 x 10 = 16000",
           ok and near(v0, 16000 - PI * 9 * 10, 0.05) and near(v1, 16000, 0.05), f"{v0:.3f} -> {v1:.3f} | {text.split(chr(10))[0][:90]}")
    ok, text, d = await c.call("undo", steps=1)
    v2 = await vol(c)
    record("R7 undo: l'eliminazione della faccia e' annullata (di nuovo il foro)", ok and near(v2, v0, 0.05),
           f"{v2:.3f} | {text.split(chr(10))[0][:90]}")
    await discard_all(c)


# ===================================================================================================== R8 tavole 3 (sez. 5)
async def r8_tavole3(c):
    print("\n== R8. Tavole 3 (quota libera, elimina foglio)")
    part = OUT / "rev_r8_blocco.SLDPRT"
    await box(c, -40, -25, 40, 25, 20)                   # 80 x 50 x 20
    if part.exists():
        part.unlink()
    await c.call("save_document", filepath=str(part))
    drw = OUT / "rev_r8.SLDDRW"
    if drw.exists():
        drw.unlink()
    await c.call("create_drawing", model_path=str(part), paper_size="A3", save_as=str(drw), add_views=False)
    ok, text, d = await c.call("add_model_view", orientation="front", x=150, y=150, scale="1:1")
    ok_l, _, lv = await c.call("list_drawing_views")
    v = (lv.get("views") or [{}])[0] if ok_l else {}
    xc, yc = v.get("x_mm", 150), v.get("y_mm", 150)
    # il contorno della vista ha un margine: gli spigoli verticali sono a xc +- L/2 (scala 1:1) con L = una delle misure
    got, used = None, None
    for size_ in (80.0, 50.0, 20.0):
        e1, e2 = [xc - size_ / 2, yc], [xc + size_ / 2, yc]
        ok, text, d = await c.call("add_drawing_dimension", edge1=e1, edge2=e2, kind="horizontal", expected=size_)
        if ok:
            got, used = d.get("value_mm"), (e1, e2, size_)
            break
    record("R8 add_drawing_dimension fra i due spigoli verticali della vista: misura riletta = larghezza del blocco",
           got is not None and near(got, used[2], 1e-3), f"{got} mm (vista in {xc}, {yc}) | {text.split(chr(10))[0][:80]}")
    if got is not None:
        ok, text, d = await c.call("add_drawing_dimension", edge1=used[0], edge2=used[1], kind="horizontal", expected=got + 7)
        record("R8 add_drawing_dimension con expected sbagliato: quota cancellata e errore", not ok and "cancellata" in text,
               text.split("\n")[0][:100])
    await c.call("add_sheet", name="FoglioR8", paper_size="A4", orientation="portrait", scale="1:1")
    ok, text, d = await c.call("delete_sheet", name="FoglioR8")
    ok2, _, ls = await c.call("list_sheets")
    names = [s_["name"] for s_ in ls.get("sheets", [])]
    record("R8 delete_sheet: il foglio aggiunto sparisce", ok and "FoglioR8" not in names and len(names) == 1, f"{names} | {text[:80]}")
    ok, text, d = await c.call("delete_sheet", name=names[0] if names else "x")
    record("R8 delete_sheet sull'unico foglio: rifiutato", not ok, text.split("\n")[0][:80])
    await discard_all(c)


# ===================================================================================================== run
SEZIONI = [("R1", r1_schizzi), ("R2", r2_feature), ("R3", r3_tavole), ("R4", r4_assiemi), ("R5", r5_dati),
           ("R6", r6_simulazione), ("R7", r7_superfici), ("R8", r8_tavole3)]


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
                ok, text, data = await c.call("connect_solidworks")
                my_pid = data.get("pid")
                if not ok or not my_pid or my_pid in elia_pids or my_pid not in sw_pids():
                    print("STOP: nessuna istanza separata ottenibile. Nulla e' stato toccato.")
                    return False
                print(f"Istanza dedicata PID {my_pid}")
                only = {a.upper() for a in sys.argv[1:]}
                for nome, fn in SEZIONI:
                    if not only or nome in only:
                        try:
                            await fn(c)
                        except Exception as e:
                            record(f"{nome}: eccezione nel test", False, repr(e)[:200])
                await discard_all(c)
    finally:
        cleanup(my_pid, elia_pids)
        left = sw_pids() - elia_pids
        record("nessun processo SolidWorks orfano; istanza utente intatta", not left and elia_pids <= sw_pids(), f"orfani {sorted(left)}")
    return True


if __name__ == "__main__":
    done = asyncio.run(run())
    print("\n==== RIEPILOGO ====")
    for tool, res, note in RESULTS:
        print(f"{res:5} {tool:70} {note}"[:230])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
