"""
Prove dal vivo dei tool che nessun test usava (revisione 2026-11-19, 48 tool scoperti con scripts_tmp/copertura_live.py).
Ogni controllo confronta un numero riletto da SolidWorks con uno calcolato. Istanza dedicata e nascosta.
I tool ritirati (nessuna API funzionante: not_implemented.py) si controllano solo per l'errore che spiega perche'.
"""

import asyncio
import math
import os
import struct
import sys
import zlib
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup, EXPECTED_TOOLS

D = OUT / "copertura"
LIB = r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2026\design library"
RESULTS = []


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:200])


def near(a, b, tol=1e-3):
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def png(path, w=40, h=20):
    raw = b"".join(b"\x00" + bytes([200, 30, 30]) * w for _ in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def segs(data):
    return (data or {}).get("segments") or []


async def block(c, w=60, h=40, depth=20):
    """Pezzo nuovo con un blocco: schizzo Top (0,0)-(w,h) -> modello X -h..0, Y 0..w, Z 0..depth (misurato)."""
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Top")
    await c.call("draw_rectangle", x1=0, y1=0, x2=w, y2=h)
    await c.call("close_sketch")
    return await c.call("extrude_boss", depth=depth)


async def sketch2d(c):
    print("\n--- Schizzi 2D ---")
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    # conica: lunghezza della quadratica razionale (rho 0,3) calcolata a parte = 42,67843 mm
    ok, t, d = await c.call("draw_conic_curve", p_start=[0, 0], p_end=[40, 0], p_apex=[20, 20], rho=0.3)
    record("draw_conic_curve rho 0,3: lunghezza 42,6784 mm", ok and near(d.get("length"), 42.67843, 1e-3), t[:90])
    ok, t, d = await c.call("draw_conic_curve", p_start=[0, 0], p_end=[40, 0], p_apex=[20, 20], rho=0.95)
    record("draw_conic_curve rho 0,95: rifiutata con spiegazione", not ok and "rho" in t, t[:90])
    # curva per vertici di controllo: Bezier cubica, lunghezza calcolata 43,8086 mm
    ok, t, d = await c.call("draw_style_spline", points=[[0, -10], [10, -20], [30, -20], [40, -10]])
    record("draw_style_spline Bezier: lunghezza 43,8086 mm, scarto <= 0,001", ok and near(d.get("length_mm"), 43.8086, 2e-3)
           and d.get("max_deviation_mm", 1) <= 0.001, t[:90])
    ok, t, d = await c.call("draw_style_spline", points=[[50, 0], [60, 10], [70, 0], [60, -10]], closed=True)
    record("draw_style_spline chiusa: lunghezza = calcolata", ok and near(d.get("length_mm"), d.get("expected_length_mm"), 0.05),
           f"{d.get('length_mm')} / {d.get('expected_length_mm')}")
    await c.call("close_sketch")

    await c.call("create_sketch", plane="Top")
    await c.call("draw_line", x1=0, y1=0, x2=20, y2=0)
    await c.call("draw_arc", cx=20, cy=10, radius=10, start_angle=-90, end_angle=0)
    ok, t, d = await c.call("fit_spline", entities=["@10,0", "@27.0711,2.9289"], tolerance=0.01)
    record("fit_spline linea+arco: scarto <= 0,01 mm, lunghezza = catena (35,708)", ok and d.get("max_deviation_mm", 1) <= 0.01
           and near(d.get("spline_length_mm"), 35.70796, 0.01), t[:90])
    _ok, _t, ls = await c.call("list_sketch_entities")
    cons = [s for s in segs(ls) if s.get("construction")]
    record("fit_spline: gli originali diventano costruzione (2)", len(cons) == 2, str(len(cons)))
    await c.call("close_sketch")

    # costruzione, quote, punti, stiramento, cancellazione
    await c.call("create_sketch", plane="Right")
    await c.call("draw_rectangle", x1=0, y1=0, x2=40, y2=20)
    ok, t, d = await c.call("check_sketch_for_feature")
    record("check_sketch_for_feature: rettangolo = 1 contorno chiuso, valido", ok and d.get("closed_contours") == 1
           and d.get("valid") is True, t[:80])
    ok, t, d = await c.call("toggle_construction", entities=["@20,0"], construction=True)
    ok2, t2, d2 = await c.call("toggle_construction", entities=["@20,0"])
    record("toggle_construction con '@x,y': costruzione e poi di nuovo normale", ok and ok2
           and d["changed"][0]["construction"] is True and d2["changed"][0]["construction"] is False, t2[:80])
    ok, t, d = await c.call("add_sketch_dimension", entity1="@20,0", value=40, position=[20, -8])
    name = d.get("full_name")
    ok1, t1, d1 = await c.call("set_dimension_driven", name=name, driven=True)
    ok2, t2, d2 = await c.call("set_dimension_driven", name=name, driven=False)
    record("set_dimension_driven: di riferimento e poi guidante", ok1 and d1.get("driven") is True and ok2
           and d2.get("driven") is False, t2[:80])
    ok, t, d = await c.call("delete_dimension", name=name)
    record("delete_dimension: quota cancellata", ok and name in str(d.get("deleted")), t[:80])
    ok, t, d = await c.call("move_sketch_point", point="pt@40,20", x=45, y=25)
    record("move_sketch_point: punto riletto in (45, 25)", ok and d.get("after_mm") == [45.0, 25.0], str(d.get("after_mm")))
    await c.call("close_sketch")

    await c.call("create_sketch", plane="Right")
    for a in ((10, 10, 30, 10), (30, 10, 30, 30), (30, 30, 50, 30)):
        await c.call("draw_line", x1=a[0], y1=a[1], x2=a[2], y2=a[3])
    ok, t, d = await c.call("stretch_sketch_entities", entities=["@30,20"], dx=5, dy=0)
    _ok, _t, ls = await c.call("list_sketch_entities")
    first = next((s for s in segs(ls) if s.get("start_mm") == [10.0, 10.0]), {})
    record("stretch_sketch_entities: linea spostata di 5, la vicina si allunga a 25 mm", ok
           and near(first.get("length_mm"), 25.0), f"{first.get('length_mm')}")
    n0 = len(segs(ls))
    ok, t, d = await c.call("delete_sketch_entities", entities=["@40,30"])
    _ok, _t, ls = await c.call("list_sketch_entities")
    record("delete_sketch_entities: un segmento in meno", ok and len(segs(ls)) == n0 - 1, f"{n0} -> {len(segs(ls))}")
    await c.call("close_sketch")

    await c.call("create_sketch", plane="Right")
    await c.call("draw_line", x1=0, y1=0, x2=20, y2=0)
    ok, t, d = await c.call("align_sketch_entities", entities=["@10,0"], source_points=[[0, 0], [20, 0]],
                            target_points=[[10, 10], [10, 30]])
    _ok, _t, ls = await c.call("list_sketch_entities")
    s0 = (segs(ls) or [{}])[0]
    record("align_sketch_entities: linea portata da (0,0)-(20,0) a (10,10)-(10,30)", ok
           and s0.get("start_mm") == [10.0, 10.0] and s0.get("end_mm") == [10.0, 30.0], f"{s0.get('start_mm')} {s0.get('end_mm')}")
    await c.call("draw_line", x1=0, y1=40, x2=20, y2=40)
    await c.call("draw_arc", cx=0, cy=50, radius=10, start_angle=-90, end_angle=90)
    ok, t, d = await c.call("replace_sketch_entity", source_entity="@10,40", target_entity="@10,50")
    record("replace_sketch_entity: sorgente costruzione, destinazione presente", ok and d.get("source_now") == "costruzione"
           and d.get("target_present") is True, t[:80])
    await c.call("close_sketch")

    await c.call("create_sketch", plane="Front")
    await c.call("draw_construction_line", x1=50, y1=-20, x2=50, y2=20)
    ok, t, d = await c.call("set_dynamic_mirror_sketch", enable=True, centerline="@50,0")
    _ok, _t, l0 = await c.call("list_sketch_entities")
    await c.call("draw_line", x1=55, y1=0, x2=60, y2=10)
    _ok, _t, l1 = await c.call("list_sketch_entities")
    ok2, t2, d2 = await c.call("set_dynamic_mirror_sketch", enable=False)
    await c.call("draw_line", x1=55, y1=-10, x2=60, y2=-15)
    _ok, _t, l2 = await c.call("list_sketch_entities")
    record("set_dynamic_mirror_sketch: accesa una linea ne crea 2, spenta 1", ok and ok2
           and len(segs(l1)) - len(segs(l0)) == 2 and len(segs(l2)) - len(segs(l1)) == 1,
           f"+{len(segs(l1)) - len(segs(l0))} / +{len(segs(l2)) - len(segs(l1))}")
    await c.call("close_sketch")

    await c.call("create_sketch", plane="Top")
    await c.call("draw_line", x1=0, y1=0, x2=40, y2=0)
    await c.call("draw_line", x1=10, y1=-10, x2=10, y2=10)
    await c.call("draw_line", x1=30, y1=-10, x2=30, y2=10)
    ok, t, d = await c.call("trim_sketch_outside", entity="@20,0", boundaries=["@10,5", "@30,5"])
    record("trim_sketch_outside: resta il tratto 10-30 (20 mm)", ok and any(near(a.get("length_mm"), 20.0) for a in d.get("added", [])),
           t[:80])
    ok, t, d = await c.call("trim_sketch_closest", entity="@10,8", point=[10, 8])
    record("trim_sketch_closest: verticale accorciata a 10 mm", ok and any(near(a.get("length_mm"), 10.0) for a in d.get("added", [])),
           t[:80])
    await c.call("draw_line", x1=0, y1=30, x2=60, y2=30)
    await c.call("draw_line", x1=20, y1=20, x2=20, y2=40)
    await c.call("draw_line", x1=40, y1=20, x2=40, y2=40)
    ok, t, d = await c.call("trim_sketch_inside", entity="@5,30", boundaries=["@20,25", "@40,25"], point=[30, 30])
    record("trim_sketch_inside: restano 2 tratti da 20 mm", ok and sorted(round(a.get("length_mm", 0), 3) for a in d.get("added", []))
           == [20.0, 20.0], t[:80])
    await c.call("close_sketch")

    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=0, x2=30, y2=20)
    ok, t, d = await c.call("create_area_hatch", angle=45, scale=1)
    record("create_area_hatch: linee di tratteggio create nel rettangolo", ok and d.get("hatch_lines", 0) > 0, t[:80])
    await c.call("close_sketch")

    img = D / "immagine.png"
    png(img)
    await c.call("create_sketch", plane="Front")
    ok, t, d = await c.call("insert_sketch_picture", filepath=str(img), x=10, y=5, width=40, angle=15, transparency=0.5)
    record("insert_sketch_picture: origine (10,5), 40 x 20 (proporzioni), 15 gradi, trasparenza 0,5 riletti", ok
           and d.get("origin") == [10.0, 5.0] and near(d.get("width"), 40) and near(d.get("height"), 20)
           and near(d.get("angle_deg"), 15) and near(d.get("transparency"), 0.5, 0.003), t[:90])
    await c.call("close_sketch")


async def blocks(c):
    print("\n--- Blocchi di schizzo ---")
    blk = D / "blocco.sldblk"
    if blk.exists():
        blk.unlink()
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=0, x2=10, y2=5)
    code = ("sm = doc.SketchManager\nsegs = list(sm.ActiveSketch.GetSketchSegments)\nautomation._s2_select(doc, segs)\n"
            "bd = sm.MakeSketchBlockFromSelected(automation._math_point([0.0, 0.0, 0.0]))\n"
            f"result = bool(bd.Save({str(blk)!r}))")
    ok, t, d = await c.call("execute_python", code=code)
    record("preparazione: blocco 10x5 salvato in .sldblk", ok and str(d.get("result")) == "True" and blk.exists(), t[:80])
    await c.call("close_sketch")
    await c.call("create_sketch", plane="Right")
    ok, t, d = await c.call("insert_sketch_block_from_file", filepath=str(blk), x=20, y=10, scale=2, angle=30)
    record("insert_sketch_block_from_file: posizione (20,10), scala 2, 30 gradi riletti", ok
           and d.get("insertion_point") == [20.0, 10.0] and near(d.get("scale"), 2) and near(d.get("angle_deg"), 30), t[:90])
    ok, t, d = await c.call("edit_sketch_block", block_name="blocco")
    await c.call("draw_line", x1=0, y1=0, x2=0, y2=3)
    ok2, t2, d2 = await c.call("edit_sketch_block", block_name="")
    record("edit_sketch_block: una linea in piu' nella definizione (4 -> 5)", ok and ok2
           and (d2.get("after") or {}).get("lines") == (d2.get("before") or {}).get("lines", -9) + 1, t2[:90])
    ok, t, d = await c.call("explode_sketch_block")
    record("explode_sketch_block: 5 entita' nello schizzo, nessuna istanza", ok and d.get("segments_after") == 5
           and d.get("instances_left") == [], t[:80])
    _ok, _t, ls = await c.call("list_sketch_entities")
    longest = max((s.get("length_mm") or 0) for s in segs(ls)) if segs(ls) else 0
    record("explode_sketch_block: il lato lungo vale 20 mm (10 x scala 2)", near(longest, 20.0), str(longest))
    await c.call("close_sketch")


async def sketch3d(c):
    print("\n--- Schizzi 3D ---")
    await block(c)
    await c.call("create_3d_sketch")
    ok, t, d = await c.call("draw_3d_arc", p1=[0, 0, 0], p2=[10, 10, 5], p3=[20, 0, 10])
    # cerchio per i 3 punti: centro (10, -1,25, 5), raggio 11,25 (calcolato)
    record("draw_3d_arc: raggio 11,25 e centro (10,-1,25,5)", ok and near(d.get("radius"), 11.25)
           and d.get("center") == [10.0, -1.25, 5.0], t[:80])
    await c.call("draw_3d_line", x1=0, y1=0, z1=0, x2=0, y2=30, z2=40)
    ok, t, d = await c.call("add_3d_sketch_axis_dimension", entity="@0,15,20", axis="z", x=0, y=20, z=20)
    ok2, t2, d2 = await c.call("add_3d_sketch_axis_dimension", entity="@0,15,20", axis="y", x=0, y=20, z=20)
    record("add_3d_sketch_axis_dimension: Z 40 e Y 30", ok and near(d.get("value"), 40) and ok2 and near(d2.get("value"), 30),
           f"{d.get('value')} / {d2.get('value')}")
    ok, t, d = await c.call("create_3d_sketch_plane", ref1="Front")
    record("create_3d_sketch_plane coincidente con Front: 1 relazione nuova", ok and d.get("sketch_relations_added") == 1, t[:80])
    ok, t, d = await c.call("create_3d_sketch_plane", ref1="Front", relation1=1)
    record("create_3d_sketch_plane con codice non adatto: rifiutato", not ok, t[:80])
    await c.call("close_sketch")
    ok, t, d = await c.call("sketch_offset_on_surface", edges=[[-20, 0, 20]], distance=5)
    ok2, t2, d2 = await c.call("sketch_offset_on_surface", edges=[[-20, 0, 20]], distance=3, reverse=True)
    c1 = (d.get("curves") or [{}])[0]
    c2 = (d2.get("curves") or [{}])[0]
    record("sketch_offset_on_surface: curve a 5 e 3 mm dallo spigolo, lunghe 40", ok and ok2
           and near(c1.get("distance_from_edge"), 5) and near(c2.get("distance_from_edge"), 3) and near(c1.get("length"), 40),
           f"{c1} {c2}")
    await c.call("close_sketch")


async def features(c):
    print("\n--- Superfici e feature ---")
    await block(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_line", x1=-10, y1=10, x2=70, y2=10)
    await c.call("close_sketch")
    await c.call("extrude_surface", depth=100, reverse=True)
    ok, t, d = await c.call("find_open_surface_edges", surface_point=[-20, 30, 10])
    record("find_open_surface_edges: superficie piana con 4 bordi aperti", ok and d.get("open_edges_count") == 4, t[:80])
    ok, t, d = await c.call("check_watertight_surface", surface_point=[-20, 30, 10])
    record("check_watertight_surface: superficie aperta -> non a tenuta", ok and d.get("watertight") is False, t[:80])
    ok, t, d = await c.call("thicken_cut", face_point=[-20, 30, 10], thickness=2, direction=0)
    record("thicken_cut 2 mm: tolti 4800 mm3 (40 x 60 x 2)", ok and near(d.get("volume_removed_mm3"), 4800.0, 0.01), t[:80])

    await block(c)
    slot = os.path.join(LIB, "features", "metric", "slots", "straight slot.sldlfp")
    ok, t, d = await c.call("insert_library_feature", feature_file=slot, placement_plane={"face": [-20, 30, 20]})
    record("insert_library_feature senza riferimenti: rifiutato, chiede 2 spigoli", not ok
           and len(d.get("references_needed") or []) == 2, t[:90])
    _ok, _t, m0 = await c.call("get_mass_properties")
    ok, t, d = await c.call("insert_library_feature", feature_file=slot, placement_plane={"face": [-20, 30, 20]},
                            references=[[-20, 0, 20], [0, 30, 20]])
    _ok, _t, m1 = await c.call("get_mass_properties")
    record("insert_library_feature asola: delta del tool = delta di massa rilevato a parte, < 0", ok
           and d.get("volume_delta_mm3", 0) < 0 and near(d.get("volume_delta_mm3"), m1["volume_mm3"] - m0["volume_mm3"], 0.01),
           t[:90])


async def sheetmetal(c):
    print("\n--- Lamiera ---")
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Top")
    await c.call("draw_rectangle", x1=0, y1=0, x2=60, y2=40)
    await c.call("close_sketch")
    await c.call("sm_base_flange", sketch="Schizzo1", thickness=2)
    ok, t, d = await c.call("sm_break_corner", edges=[[0, 0, -1]], distance=5, break_type="chamfer")
    record("sm_break_corner smusso 5: tolti 25 mm3 (5*5/2*2)", ok and near(d.get("volume_delta_mm3"), -25.0, 0.01), t[:80])
    exp = 2 * (25 - math.pi * 25 / 4)
    ok, t, d = await c.call("sm_break_corner", edges=[[-40, 60, -1]], distance=5, break_type="fillet")
    record(f"sm_break_corner raccordo 5: tolti {exp:.4f} mm3", ok and near(d.get("volume_delta_mm3"), -exp, 0.01), t[:80])
    tool = os.path.join(LIB, "forming tools", "embosses", "dimple.sldftp")
    ok, t, d = await c.call("sm_forming_tool", tool_file=tool, face_point=[-20, 30, 0])
    record("sm_forming_tool dimple: feature creata e volume cambiato", ok and abs(d.get("volume_delta_mm3", 0)) > 1, t[:80])

    await c.call("create_new_part")
    await c.call("create_sketch", plane="Top")
    await c.call("draw_rectangle", x1=0, y1=0, x2=60, y2=40)
    await c.call("close_sketch")
    await c.call("sm_base_flange", sketch="Schizzo1", thickness=2)
    ok, t, d = await c.call("sm_edge_flange", edge_points=[[-20, 0, 0], [-20, 60, 0]], length=15)
    fl = d.get("flanges") or []
    record("sm_edge_flange su 2 spigoli: 2 flange uguali, totale = somma", ok and len(fl) == 2
           and near(fl[0].get("volume_delta_mm3"), fl[1].get("volume_delta_mm3"), 0.01)
           and near(d.get("volume_delta_mm3"), sum(f.get("volume_delta_mm3") or 0 for f in fl), 0.01), t[:80])
    ok, t, d = await c.call("get_bounding_box")
    record("sm_edge_flange su 2 spigoli: ingombro alto 17 (2 + 15)", ok and near(d.get("size", [0, 0, 0])[2], 17.0), str(d.get("size")))


async def assembly(c):
    print("\n--- Assiemi ---")
    paths = {}
    for name, (w, h, dd) in (("cp_a", (40, 30, 10)), ("cp_b", (20, 20, 20))):
        await block(c, w, h, dd)
        p = str(D / f"{name}.SLDPRT")
        await c.call("save_document", filepath=p, overwrite=True)
        paths[name] = p
    await c.call("add_part_configuration", name="Corta")
    await c.call("activate_part_configuration", name="Default")
    await c.call("save_document")
    await c.call("create_new_assembly")
    ins = [await c.call("insert_component", file_path=paths[n], x=x, y=0, z=0)
           for n, x in (("cp_a", 0), ("cp_b", 100), ("cp_b", 200))]
    record("preparazione: 3 componenti inseriti", all(r[0] for r in ins), " | ".join(r[1][:60] for r in ins if not r[0]))
    asm = str(D / "cp_asm.SLDASM")
    ok, t, d = await c.call("save_document", filepath=asm, overwrite=True)
    record("preparazione: assieme salvato", ok, t[:80])
    # tutto chiuso (anche i documenti non salvati delle sezioni prima): un pezzo rimasto aperto nella sua finestra non si
    # puo' alleggerire nell'assieme. Prima un ciclo di CloseDoc si fermava al primo documento che dava errore.
    ok, t, d = await c.call("execute_python", code="sw.CloseAllDocuments(True)\nresult = int(sw.GetDocumentCount)")
    record("preparazione: tutti i documenti chiusi", ok and str(d.get("result")) == "0", t[:80])
    ok, t, d = await c.call("open_document", filepath=asm)
    record("open_document: l'assieme riaperto e' il documento attivo", ok and d.get("active") is True, t[:80])
    ok, t, d = await c.call("list_components")
    record("assieme riaperto: 3 componenti", ok and d.get("count") == 3, t[:120])
    ok, t, d = await c.call("set_component_suppression_state", name="cp_b-1", state="lightweight")
    record("set_component_suppression_state leggero: riletto 1 o 4", ok and d.get("state_code") in (1, 4), t[:80])
    ok, t, d = await c.call("set_component_suppression_state", name="cp_b-1", state="resolved")
    record("set_component_suppression_state risolto: riletto 2 o 3", ok and d.get("state_code") in (2, 3), t[:80])
    ok, t, d = await c.call("set_component_suppression_state", name="cp_b-2", state="suppressed")
    ok2, t2, d2 = await c.call("set_component_suppression_state", name="cp_b-2", state="resolved")
    record("set_component_suppression_state soppresso e di nuovo risolto", ok and d.get("state_code") == 0 and ok2, t2[:80])
    ok, t, d = await c.call("set_component_configuration", component="cp_b-1", configuration="Corta")
    record("set_component_configuration: Corta riletta", ok and d.get("configuration") == "Corta", t[:80])
    ok, t, d = await c.call("set_component_configuration", component="cp_b-1", configuration="NonEsiste")
    record("set_component_configuration inesistente: rifiutata, resta Corta", not ok and d.get("configuration") == "Corta", t[:80])
    await c.call("set_component_configuration", component="cp_b-1", configuration="Default")
    ok, t, d = await c.call("form_new_subassembly", components=["cp_b-1", "cp_b-2"], subassembly_name="gruppo")
    record("form_new_subassembly: sottoassieme con cp_b-1 e cp_b-2", ok and d.get("children") == ["cp_b-1", "cp_b-2"], t[:90])
    ok, t, d = await c.call("dissolve_subassembly", component_name=d.get("subassembly") or "gruppo")
    record("dissolve_subassembly: 3 componenti al primo livello, sottoassieme sparito", ok and len(d.get("top_level_now") or []) == 3,
           t[:90])
    ok, t, d = await c.call("open_document", filepath=paths["cp_a"])
    await c.call("assign_material", material="AISI 1020")
    ok, t, d = await c.call("link_material_to_title_block")
    record("link_material_to_title_block: Material risolto = AISI 1020", ok and d.get("resolved") == "AISI 1020", t[:80])


async def meta(c):
    print("\n--- Server ---")
    ok, t, d = await c.call("get_solidworks_info")
    record("get_solidworks_info: installazione trovata con versione", ok and d.get("found") is True and bool(d.get("version")), t[:80])
    ok, t, d = await c.call("search_tools", names=["draw_circle", "extrude_boss"], detail=True)
    record("search_tools names+detail: 2 tool con i parametri", ok and len(d.get("tools") or []) == 2
           and isinstance(d["tools"][0].get("parameters"), dict), t[:80])
    ok, t, d = await c.call("search_tools", query="fillet", limit=3)
    record("search_tools query: al massimo 3 risultati, tutti con 'fillet'", ok and 0 < len(d.get("tools") or []) <= 3
           and all("fillet" in (x["name"] + x.get("description", "")).lower() for x in d["tools"]), t[:80])
    steps = [{"tool": "create_new_part"}, {"tool": "create_sketch", "arguments": {"plane": "Top"}},
             {"tool": "draw_rectangle", "arguments": {"x1": 0, "y1": 0, "x2": 30, "y2": 20}},
             {"tool": "close_sketch"}, {"tool": "extrude_boss", "arguments": {"depth": 10}},
             {"tool": "rename_feature", "arguments": {"name": "$5.feature", "new_name": "Piastra"}},
             {"tool": "get_mass_properties"}]
    ok, t, d = await c.call("execute_tool_sequence", steps=steps)
    last = ((d.get("results") or [{}])[-1].get("data") or {})
    record("execute_tool_sequence con $5.feature: 7 passi, volume 6000 mm3", ok and near(last.get("volume_mm3"), 6000.0, 0.01),
           t[:90])
    for name in ("pack_and_go", "boundary_boss", "close_sketch_to_model"):
        ok, t, d = await c.call(name)
        record(f"{name} ritirato: errore che spiega perche'", not ok and len(t) > 40, t[:90])


async def run():
    D.mkdir(parents=True, exist_ok=True)
    elia_pids = sw_pids()
    print(f"Istanze SolidWorks pre-esistenti: {sorted(elia_pids)}")
    env = dict(os.environ)
    env["SW_MCP_INSTANCE"] = "dedicated"
    env["SW_MCP_ALLOW_PYTHON"] = "1"
    params = StdioServerParameters(command=str(PYTHON), args=[str(SERVER)], env=env, cwd=str(ROOT))
    my_pid = None
    try:
        async with stdio_client(params) as (rd, wr):
            async with ClientSession(rd, wr, read_timeout_seconds=timedelta(seconds=600)) as session:
                await session.initialize()
                c = Client(session)
                tools = [t.name for t in (await session.list_tools()).tools]
                record("tools count", len(tools) == EXPECTED_TOOLS, f"{len(tools)} (attesi {EXPECTED_TOOLS})")
                ok, text, data = await c.call("connect_solidworks")
                my_pid = data.get("pid")
                record("connect_solidworks", ok)
                only = set(sys.argv[1:])
                for part in (sketch2d, blocks, sketch3d, features, sheetmetal, assembly, meta):
                    if only and part.__name__ not in only:
                        continue
                    try:
                        await part(c)
                    except Exception as e:
                        record(f"{part.__name__}: eccezione nel test", False, repr(e)[:150])
    finally:
        cleanup(my_pid, elia_pids)
    passed = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{passed}/{len(RESULTS)} PASS")


if __name__ == "__main__":
    asyncio.run(run())
