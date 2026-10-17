"""
Live test of the drawing (messe in tavola) tools through the MCP server (stdio).

Runs against a DEDICATED, invisible SolidWorks instance (SW_MCP_INSTANCE=dedicated): the instance
of the user is never touched. The test stops if it cannot get a separate instance.

Usage:  .venv\\Scripts\\python.exe tests\\test_drawings_live.py
Output: C:\\Users\\elia\\Downloads\\solidworks-mcp\\test_output\\
"""

import os
import sys
import asyncio
import subprocess
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client
PART = OUT / "prova_disegno.SLDPRT"
PIN = OUT / "perno_prova.SLDPRT"
ASM = OUT / "prova_assieme.SLDASM"

MY_PID = None
RESULTS = []   # (tool, PASS/FAIL, note)


def record(tool, ok, note=""):
    RESULTS.append((tool, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {tool}  {note}"[:200])


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

                ok, text, data = await c.call("connect_solidworks")
                my_pid = data.get("pid")
                global MY_PID
                MY_PID = my_pid
                print(text[:200])
                if not ok or not my_pid or my_pid in elia_pids or my_pid not in sw_pids():
                    print("STOP: nessuna istanza separata ottenibile. Nulla e' stato toccato.")
                    return False
                print(f"Istanza dedicata PID {my_pid} (diversa da {sorted(elia_pids)})")

                await scenario(c)
    finally:
        cleanup(my_pid, elia_pids)
    return True


def cleanup(my_pid, elia_pids):
    """Close ONLY our instance (exact PID)."""
    if my_pid and my_pid in sw_pids():
        subprocess.run(["taskkill", "/PID", str(my_pid), "/F"], capture_output=True)
    import time
    time.sleep(3)
    left = sw_pids() - elia_pids
    print(f"Processi SolidWorks orfani dopo il test: {sorted(left)}; istanza utente intatta: "
          f"{elia_pids <= sw_pids()}")


def views_by_type(data):
    out = {}
    for v in data.get("views", []):
        out.setdefault(v["type_name"], []).append(v)
    return out


SHEET_W, SHEET_H = 420.0, 297.0
TITLE_RECT = (SHEET_W - 195.0, 0.0, SHEET_W, 80.0)        # mm, ISO sheet format title block
ISO_SCALES = {0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0}


def vrect(v):
    return tuple(v["outline_mm"])


def rects_overlap(a, b, tol=0.5):
    return not (a[2] <= b[0] + tol or b[2] <= a[0] + tol or a[3] <= b[1] + tol or b[3] <= a[1] + tol)


def layout_problems(views, extra=()):
    """Overlaps between views, with the title block / extra rects, and views outside the sheet frame."""
    probs = []
    rs = [(v["name"], vrect(v)) for v in views]
    for i in range(len(rs)):
        n, r = rs[i]
        if r[0] < 3 or r[1] < 3 or r[2] > SHEET_W - 3 or r[3] > SHEET_H - 3:
            probs.append(f"{n} fuori foglio")
        if rects_overlap(r, TITLE_RECT):
            probs.append(f"{n} sul cartiglio")
        for name, rect in extra:
            if rects_overlap(r, rect):
                probs.append(f"{n} su {name}")
        for j in range(i + 1, len(rs)):
            if rects_overlap(r, rs[j][1]):
                probs.append(f"{n} si sovrappone a {rs[j][0]}")
    return probs


def coverage(views):
    xs0 = min(vrect(v)[0] for v in views)
    ys0 = min(vrect(v)[1] for v in views)
    xs1 = max(vrect(v)[2] for v in views)
    ys1 = max(vrect(v)[3] for v in views)
    return (xs1 - xs0) * (ys1 - ys0) / ((SHEET_W - 60) * (SHEET_H - 120))


def dxf_text(path):
    return Path(path).read_text(encoding="latin-1", errors="ignore") if Path(path).exists() else ""


async def scenario(c: Client):
    # ------------------------------------------------------------------ 1. part
    print("\n== 1. Pezzo di prova")
    if PART.exists():
        PART.unlink()
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-50, y1=-30, x2=50, y2=30, unit="mm")
    await c.call("extrude_sketch", depth=10, unit="mm")
    await c.call("create_sketch_on_face", x=20, y=10, z=10, unit="mm")
    await c.call("draw_circle", x=0, y=0, radius=8, unit="mm")
    await c.call("cut_extrude", depth=10, through_all=True, unit="mm")
    await c.call("create_sketch_on_face", x=30, y=0, z=10, unit="mm")
    await c.call("draw_circle", x=-30, y=0, radius=15, unit="mm")
    await c.call("extrude_sketch", depth=20, unit="mm")
    ok, text, _ = await c.call("save_document", filepath=str(PART))
    record("setup: pezzo di prova", ok and PART.exists(), PART.name)

    # ------------------------------------------------------------------ 2. drawing
    print("\n== 2. Disegno A3 primo diedro")
    ok, text, _ = await c.call("list_drawing_views")
    record("guardia documento non-disegno", (not ok) and "non e' un disegno" in text, text[:80])

    drw1 = OUT / "prova_disegno.SLDDRW"
    if drw1.exists():
        drw1.unlink()
    ok, text, d = await c.call("create_drawing", model_path=str(PART), paper_size="A3",
                               orientation="landscape", projection="first", save_as=str(drw1))
    record("create_drawing", ok and d.get("projection") == "first_angle" and d.get("still_missing") == [],
           f"{d.get('title')} proprieta create {d.get('titleblock_properties_created')} mancanti {d.get('still_missing')}")

    ok, text, d = await c.call("add_standard_views", views=["front", "top", "right", "isometric"])
    n_, d_ = (d.get("scale", "1:1").split(":") + ["1"])[:2]
    sc_dec = float(n_) / float(d_)
    record("add_standard_views", ok and len(d.get("views", [])) == 4 and sc_dec in ISO_SCALES and d.get("layout_fits"),
           f"scala automatica {d.get('scale')} (serie ISO)")

    ok, text, lv = await c.call("list_drawing_views")
    vt = views_by_type(lv)
    record("list_drawing_views", ok and len(lv.get("views", [])) == 4, str({k: len(v) for k, v in vt.items()}))
    models = [v for v in lv["views"] if v["type_name"] == "model"]
    front = next(v for v in models if v["y_mm"] > 150 and v["x_mm"] < 300)   # front: model view in the ortho block
    iso = next(v for v in models if v is not front)
    fname, fx, fy = front["name"], front["x_mm"], front["y_mm"]
    sc = front["scale"]
    top_v = next(v for v in lv["views"] if v["type_name"] == "projected" and v["y_mm"] < fy - 20 and abs(v["x_mm"] - fx) < 5)

    ok, text, d = await c.call("add_projected_view", parent_view=top_v["name"], direction="right")
    record("add_projected_view", ok and d.get("type_name") == "projected", d.get("name", text[:80]))

    ok, text, d = await c.call("add_section_view", parent_view=fname, orientation="horizontal",
                               offset=0, label="A")
    record("add_section_view (posizione automatica)", ok and d.get("type_name") == "section", d.get("name", text[:100]))

    ok, text, d = await c.call("add_detail_view", parent_view=fname, center_x=-30, center_y=0,
                               radius=12, label="B")
    record("add_detail_view (posizione automatica)", ok and d.get("type_name") == "detail", d.get("name", text[:100]))

    ok, text, d = await c.call("insert_model_dimensions", all_views=True)
    record("insert_model_dimensions", ok, f"aggiunte {sum(d.get('added_per_view', {}).values())}, "
                                          f"saltate isometriche {d.get('skipped_pictorial')}")
    ok, text, d = await c.call("auto_dimension", view=fname)
    record("auto_dimension", ok and d.get("total", 0) > 0, f"quote vista frontale {d.get('total')}, duplicati rimossi {d.get('duplicates_removed')}")
    ok, text, d = await c.call("auto_dimension", view=iso["name"])
    record("auto_dimension rifiutata su isometrica", (not ok) and "isometric" in text, text[:70])
    ok, text, d = await c.call("add_center_marks", view=fname, mode="auto")
    record("add_center_marks", ok, text[:50])

    half_h, half_w = 30 * sc, 50 * sc
    ok, text, d = await c.call("add_surface_finish", x=fx - 35, y=fy - half_h - 16, roughness="3.2",
                               edge_x=fx - 30, edge_y=fy - half_h)
    record("add_surface_finish", ok, text[:50])
    ok, text, d = await c.call("add_datum", label="A", edge_x=fx + 25, edge_y=fy - half_h)
    record("add_datum", ok, str(d))
    ok, text, d = await c.call("add_geometric_tolerance", edge_x=fx - half_w, edge_y=fy - 12, tolerance="0.1",
                               datum_refs=["A"], x=fx - half_w - 22, y=fy - half_h - 14)
    record("add_geometric_tolerance", ok, "senza simbolo di caratteristica")
    ok, text, d = await c.call("add_hole_callout", edge_x=fx + 8 * sc, edge_y=fy, x=fx + 30 * sc, y=fy + 12 * sc)
    record("add_hole_callout (rimuove la quota duplicata)", ok and d.get("duplicate_diameters_removed", 0) >= 1, str(d))
    ok, text, d = await c.call("add_note", text="NOTA: spigoli vivi da rompere 0.5 mm", x=30, y=270, height=3.5)
    record("add_note", ok, d.get("text", text[:60]))

    ok, text, d = await c.call("set_drawing_properties", properties={
        "title": "Piastra con bossolo", "author": "Elia Venturi", "drawing_number": "TAV-001",
        "material": "AISI 304", "revision": "A", "date": "2026-10-09", "company": "Polimi D&E"})
    record("set_drawing_properties", ok and len(d.get("drawing", {})) >= 5, str(d.get("drawing", {}))[:90])

    # view management on a temporary view (free-space placement)
    ok, text, d = await c.call("add_model_view", orientation="back", scale="1:5")
    tmp = d.get("name")
    record("add_model_view (posizione automatica)", ok and tmp is not None, tmp or text[:80])
    ok, text, d = await c.call("set_view_properties", view=tmp, scale="1:10", display_style="hidden_visible",
                               show_tangent_edges=True)
    record("set_view_properties", ok and abs(d.get("scale", 0) - 0.1) < 1e-6, str(d.get("applied")))
    ok, text, d = await c.call("move_view", view=tmp, x=380, y=270)
    record("move_view", ok and abs(d.get("x_mm", 0) - 380) < 0.5, f"{d.get('x_mm')},{d.get('y_mm')}")
    ok, text, d = await c.call("delete_view", view=tmp)
    record("delete_view", ok, text[:80])

    # ---------------- quality checks on sheet 1
    ok, text, lv = await c.call("list_drawing_views")
    kinds = {k: len(v) for k, v in views_by_type(lv).items()}
    record("verifica viste foglio 1", all(k in kinds for k in ("model", "projected", "section", "detail")),
           f"{len(lv['views'])} viste {kinds}")
    probs = layout_problems(lv["views"])
    record("QUALITA: nessuna sovrapposizione viste/cartiglio/foglio", not probs, "; ".join(probs)[:150] or "ok")
    cov = coverage(lv["views"])
    record("QUALITA: viste occupano il foglio", cov >= 0.45, f"copertura {cov:.2f}")
    ok, text, dd = await c.call("list_drawing_dimensions")
    record("QUALITA: nessuna quota duplicata", ok and dd.get("duplicates") == 0, f"{len(dd.get('dimensions', []))} quote, duplicati {dd.get('duplicates')}")
    record("QUALITA: nessuna quota su viste isometriche", ok and dd.get("on_pictorial_views") == 0, str(dd.get("on_pictorial_views")))
    # dimension texts must stay outside the views they do not belong to
    dim_prob = []
    for row in dd.get("dimensions", []):
        for v in lv["views"]:
            if v["name"] != row["view"] and vrect(v)[0] + 2 < row["x_mm"] < vrect(v)[2] - 2 and vrect(v)[1] + 2 < row["y_mm"] < vrect(v)[3] - 2:
                dim_prob.append(f"{row['value_mm']} di {row['view']} dentro {v['name']}")
    record("QUALITA: quote non dentro altre viste", not dim_prob, "; ".join(dim_prob)[:140] or "ok")

    # exports of the clean drawing (before the break view exists)
    for ext in ("png", "pdf", "dxf", "dwg", "jpg"):
        p = OUT / f"prova_disegno.{ext}"
        if p.exists():
            p.unlink()
        ok, text, d = await c.call("export_drawing", filepath=str(p))
        record(f"export_drawing {ext}", ok and p.exists() and p.stat().st_size > 0,
               f"{p.stat().st_size if p.exists() else 0} B " + ("" if ok else text[:80]))
    txt = dxf_text(OUT / "prova_disegno.dxf")
    record("QUALITA: nessun 'ERRORE' nel cartiglio (testo DXF)", len(txt) > 1000 and "ERROR" not in txt,
           f"{txt.count('ERROR')} occorrenze")
    record("QUALITA: cartiglio con titolo, N. disegno e peso", "Piastra" in txt and "bossolo" in txt and "prova_disegno" in txt and "72.13" in txt,
           "titolo/numero/peso presenti" if "72.13" in txt else "peso mancante")
    record("QUALITA: tratteggio presente nella sezione (HATCH nel DXF)", txt.count("HATCH") >= 1, f"{txt.count('HATCH')} HATCH")

    # sheets
    ok, text, d = await c.call("add_sheet", name="Foglio2", paper_size="A4", orientation="portrait", scale="1:1")
    record("add_sheet", ok, str(d.get("sheets")))
    ok, text, d = await c.call("list_sheets")
    record("list_sheets", ok and len(d.get("sheets", [])) == 2, str([(s["name"], s["width_mm"], s["height_mm"]) for s in d.get("sheets", [])]))
    ok, text, d = await c.call("set_sheet_properties", scale="1:2", projection="first")
    record("set_sheet_properties", ok and d.get("scale") == "1:2", str(d))

    # advanced views on sheet 2
    ok, text, d = await c.call("add_model_view", orientation="front", x=100, y=200, scale="1:1")
    adv = d.get("name")
    record("add_model_view (foglio 2)", ok, adv or text[:80])
    ok, text, d = await c.call("add_broken_out_section", parent_view=adv, x1=-45, y1=-15, x2=-15, y2=15, depth=5)
    record("add_broken_out_section", ok, text[:80])
    ok, text, d = await c.call("add_crop_view", parent_view=adv, center_x=-20, center_y=0, radius=40)
    record("add_crop_view", ok, text[:80])
    ok, text, d = await c.call("add_model_view", orientation="front", x=100, y=100, scale="1:1")
    adv2 = d.get("name")
    ok, text, d = await c.call("add_break_view", parent_view=adv2, orientation="vertical", position1=-10, position2=10)
    record("add_break_view", ok, text[:80])
    ok, text, d = await c.call("add_model_view", orientation="front", x=100, y=30, scale="1:2")
    adv3 = d.get("name")
    ok, text, d = await c.call("add_auxiliary_view", parent_view=adv3, edge_x=100, edge_y=30 - 15)
    record("add_auxiliary_view", ok, text[:80])
    record("add_auxiliary_view: vista nominata + faccia di riferimento in vera grandezza (senza CreateAuxiliaryViewAt2)",
           ok and str(d.get("named_view", "")).startswith("AUX_") and (d.get("reference_face_true_size_ratio") or 0) > 0.999,
           f"{d.get('named_view')} ratio {d.get('reference_face_true_size_ratio')}")
    ok, text, lv2 = await c.call("list_drawing_views")
    record("verifica viste foglio 2", ok, str({k: len(v) for k, v in views_by_type(lv2).items()}))
    ok, text, d = await c.call("export_drawing", filepath=str(OUT / "prova_disegno_foglio2.png"))
    record("export_drawing png (foglio 2)", ok and (OUT / "prova_disegno_foglio2.png").exists(), "")

    ok, text, d = await c.call("activate_sheet", name="Foglio1")
    record("activate_sheet", ok, text[:60])

    p_drw = OUT / "prova_disegno.SLDDRW"
    ok, text, d = await c.call("save_drawing", filepath=str(p_drw))
    record("save_drawing", ok and p_drw.exists() and p_drw.stat().st_size > 0, f"{p_drw.stat().st_size if p_drw.exists() else 0} B")
    # DXF/DWG with a break view in the drawing must be refused (it crashes SolidWorks)
    ok, text, d = await c.call("export_drawing", filepath=str(OUT / "prova_disegno_break.dxf"))
    record("export_drawing dxf (guardia viste interrotte)", (not ok) and "interrott" in text, text[:90])

    # ------------------------------------------------------------------ 3. assembly
    print("\n== 3. Assieme con distinta base e palloncini")
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=6, unit="mm")
    await c.call("extrude_sketch", depth=40, unit="mm")
    if PIN.exists():
        PIN.unlink()
    ok, text, _ = await c.call("save_document", filepath=str(PIN))
    record("setup: perno", ok and PIN.exists(), PIN.name)
    await c.call("create_new_assembly")
    comps = add_components(str(PART), str(PIN))
    record("setup: componenti assieme (COM diretto)", comps >= 3, f"{comps} componenti")
    if ASM.exists():
        ASM.unlink()
    ok, text, _ = await c.call("save_document", filepath=str(ASM))
    record("setup: assieme", ok and ASM.exists(), ASM.name)

    drw2 = OUT / "prova_assieme.SLDDRW"
    if drw2.exists():
        drw2.unlink()
    ok, text, d = await c.call("create_drawing", model_path=str(ASM), paper_size="A3", save_as=str(drw2))
    record("create_drawing (assieme)", ok and d.get("still_missing") == [], d.get("title", text[:80]))
    ok, text, d = await c.call("add_standard_views", views=["front", "isometric"])
    record("add_standard_views (assieme)", ok, f"scala automatica {d.get('scale')}")
    ok, text, lv = await c.call("list_drawing_views")
    target = lv["views"][0]["name"] if ok and lv.get("views") else ""
    ok, text, d = await c.call("add_bom", view=target, bom_type="parts_only")
    record("add_bom", ok, f"{d.get('rows')} righe " + ("" if ok else text[:100]))
    rows = max(d.get("rows", 3), 2)
    bom_rect = (5.0, SHEET_H - 5.0 - (rows + 1) * 9.5, 215.0, SHEET_H - 5.0)
    ok, text, d = await c.call("add_balloons", view=target)
    record("add_balloons", ok and d.get("count", 0) >= 2, f"{d.get('count')} palloncini " + ("" if ok else text[:100]))
    ok, text, lv = await c.call("list_drawing_views")
    probs = layout_problems(lv["views"], extra=[("distinta", bom_rect)])
    record("QUALITA (assieme): nessuna sovrapposizione con viste/cartiglio/distinta", not probs, "; ".join(probs)[:150] or "ok")
    record("QUALITA (assieme): viste occupano il foglio", coverage(lv["views"]) >= 0.35, f"copertura {coverage(lv['views']):.2f}")
    ok, text, d = await c.call("save_drawing", filepath=str(drw2))
    record("save_drawing (assieme)", ok and drw2.exists(), "")
    for ext in ("pdf", "dxf", "dwg", "png"):
        p = OUT / f"prova_assieme.{ext}"
        if p.exists():
            p.unlink()
        ok, text, d = await c.call("export_drawing", filepath=str(p))
        record(f"export_drawing {ext} (assieme)", ok and p.exists() and p.stat().st_size > 0,
               f"{p.stat().st_size if p.exists() else 0} B")
    txt = dxf_text(OUT / "prova_assieme.dxf")
    record("QUALITA (assieme): nessun 'ERRORE' nel cartiglio", len(txt) > 1000 and "ERROR" not in txt, f"{txt.count('ERROR')} occorrenze")


def add_components(part_path, pin_path):
    """Direct COM on the dedicated instance (found through the ROT by PID)."""
    sys.path.insert(0, str(ROOT))
    from solidworks_mcp.automation.base import SolidWorksAutomation as A
    mine = A._find_instance_by_pid(MY_PID)   # ONLY the dedicated instance, by exact PID
    if mine is None or mine.ActiveDoc is None or int(mine.ActiveDoc.GetType) != 2:
        return 0
    asm = mine.ActiveDoc
    n = 0
    for path, x in ((part_path, 0.0), (part_path, 0.2), (pin_path, 0.1)):
        comp = asm.AddComponent5(path, 0, "", False, "", x, 0.0, 0.0)
        if comp is not None:
            n += 1
    return n


if __name__ == "__main__":
    done = asyncio.run(run())
    print("\n==== RIEPILOGO ====")
    for tool, res, note in RESULTS:
        print(f"{res:5} {tool:38} {note}"[:170])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
