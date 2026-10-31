"""
Test live delle correzioni nate da una sessione d'uso reale (rapporto bug/informazioni mancanti/strumenti nuovi) tramite il
server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente non viene mai
toccata; alla fine si chiude solo il PID lanciato dal test.

  T  piastra 100x40x10 con un'asola: get_feature_tree / get_rebuild_errors (membri COM come proprieta'), list_features senza
     cartelle di sistema, barra di rollback (get_document_info, list_model_features), export_model_image in una cartella che non
     esiste, get_feature_definition (ambito), try_on_copy (l'originale resta identico), ripetizione lineare con istanze fuori dal corpo
  U  riferimenti di fine di get_feature_definition: fino alla superficie, fino al vertice, offset dalla superficie (corpo, punto, area)
  O  disco con 6 asole radiali che partono dal centro dell'asse (istanze sovrapposte): ripetizione circolare accettata, volume
     = calcolo analitico (unione di 6 rettangoli)
  K  mozzo + anello + terzo corpo + razza sottile che unisce mozzo e anello (Merge=true, ambito = mozzo + anello): ripetizione di
     feature, edit_extrude_options (merge, ambito per nome/per punto), ripetizione di feature con seme a corpo separato RIFIUTATA
     con la procedura, poi la procedura (merge=false -> circular_pattern bodies -> combine_bodies): volume analitico, terzo corpo intatto
  Q  query_topology_by_criteria: nome del corpo di ogni entita'

Uso:  .venv\\Scripts\\python.exe tests\\test_report_fix_live.py [T U O K Q]
Output: test_output\\ (file report_fix_*)
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
TOL = 0.005          # 0,5 % sui volumi
PI = math.pi
SYSTEM_TYPES = {"CommentsFolder", "FavoriteFolder", "HistoryFolder", "SelectionSetFolder", "SensorFolder", "DocsFolder",
                "DetailCabinet", "SurfaceBodyFolder", "SolidBodyFolder", "EnvFolder", "InkMarkupFolder", "EqnFolder", "MaterialFolder"}


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:300])


def near(got, exp, tol=TOL, absolute=None):
    if absolute is not None:
        return abs(got - exp) <= absolute
    return abs(got - exp) <= tol * max(abs(exp), 1e-9)


async def vol(c):
    ok, _, d = await c.call("get_mass_properties")
    return d.get("volume_mm3", 0.0) if ok else 0.0


async def bodies(c):
    ok, _, d = await c.call("list_bodies")
    return d.get("bodies", []) if ok else []


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


async def step(c, tool, **args):
    ok, text, d = await c.call(tool, **args)
    if not ok:
        print(f"    !! {tool} {args}: {text[:200]}")
    return ok, text, d


def feature_count(d):
    return d.get("count", -1)


# ======================================================================================================= T
async def t_plate(c):
    print("\n== T. Piastra con asola: albero, rollback, esportazione, prova su copia")
    await discard_all(c)
    await new_part(c)
    await step(c, "create_sketch", plane="Front")
    await step(c, "draw_rectangle", x1=0, y1=0, x2=100, y2=40)
    ok, _, d = await step(c, "extrude_boss", depth=10)
    boss = d.get("feature")
    await step(c, "create_sketch_on_face", x=10, y=50, z=20)
    await step(c, "draw_rectangle", x1=8, y1=10, x2=14, y2=30)
    ok, _, d = await step(c, "extrude_cut", end_condition="through_all")
    cut = d.get("feature")
    v_plate = 100 * 40 * 10 - 6 * 20 * 10
    record("T0 piastra con asola: volume 38800 mm3", near(await vol(c), v_plate), f"{await vol(c):.2f}")

    # --- get_feature_tree / get_rebuild_errors su SolidWorks vero (bug 1)
    ok, text, d = await c.call("get_feature_tree")
    names = [f["name"] for f in d.get("features", [])]
    types = {f["name"]: f["type"] for f in d.get("features", [])}
    record("T1 get_feature_tree: successo e contiene le feature create",
           ok and boss in names and cut in names and types.get(boss) == "Extrusion" and d.get("error_count") == 0,
           f"{d.get('count')} feature: {names[-4:]}")
    ok, text, d = await c.call("get_rebuild_errors")
    record("T2 get_rebuild_errors: successo, ricostruzione ok, albero scandito",
           ok and d.get("rebuild_ok") is True and d.get("error_count") == 0 and d.get("features_scanned", 0) >= 8,
           f"scandite {d.get('features_scanned')} feature: {text[:70]}")

    # --- list_features compatto, senza cartelle di sistema (punto 8)
    ok, _, d = await c.call("list_features")
    rows = d.get("features", [])
    ok2, _, dd = await c.call("list_features", detail=True)
    detail = dd.get("features", [])
    ok3, _, da = await c.call("list_features", include_system=True)
    record("T3 list_features: nessuna cartella di sistema di default, una riga per feature",
           ok and ok2 and rows and all(isinstance(r, str) for r in rows) and not any(f["type"] in SYSTEM_TYPES for f in detail)
           and any(f["name"] == boss and f["type"] == "Extrusion" for f in detail) and d.get("system_folders_hidden", 0) >= 5,
           f"{len(rows)} righe, {d.get('system_folders_hidden')} cartelle nascoste: {rows[:2]}")
    record("T4 list_features include_system=true aggiunge le cartelle di sistema",
           ok3 and da.get("count", 0) == d.get("count", 0) + d.get("system_folders_hidden", 0), f"{da.get('count')}")

    # --- barra di rollback (punto 6)
    ok, _, d = await c.call("set_rollback_bar", target_feature=boss, position="after")
    ok2, text2, di = await c.call("get_document_info")
    rb = di.get("rollback", {})
    record("T5 get_document_info riporta il rollback dopo set_rollback_bar",
           ok and ok2 and rb.get("in_rollback") is True and rb.get("rollback_after") == boss and cut in rb.get("rolled_back_features", [])
           and "ROLLBACK" in text2, text2[:110])
    ok3, text3, dl = await c.call("list_model_features")
    rows = {f["name"]: f for f in dl.get("features", [])}
    record("T6 list_model_features marca la feature sotto la barra e riporta la posizione",
           ok3 and rows.get(cut, {}).get("rolled_back") is True and "rolled_back" not in rows.get(boss, {})
           and dl.get("rollback", {}).get("rollback_after") == boss, text3[:110])
    await c.call("set_rollback_bar", position="end")
    ok, _, di = await c.call("get_document_info")
    ok3, _, dl = await c.call("list_model_features")
    record("T7 barra a fine albero: nessun rollback e nessuna feature marcata",
           ok and di.get("rollback", {}).get("in_rollback") is False and not any(f.get("rolled_back") for f in dl.get("features", [])))
    record("T8 volume ripristinato dopo il rollback", near(await vol(c), v_plate), f"{await vol(c):.2f}")

    # --- export_model_image in una cartella che non esiste (punto 4)
    base = OUT / "report_fix_img"
    shutil.rmtree(base, ignore_errors=True)
    target = base / "non" / "esiste" / "piastra.png"
    ok, text, d = await c.call("export_model_image", filepath=str(target), view="isometric")
    record("T9 export_model_image in cartella inesistente: la crea e salva il file",
           ok and target.exists() and target.stat().st_size > 1000, f"{target.stat().st_size if target.exists() else 0} byte: {text[:80]}")

    # --- get_feature_definition: ambito e opzioni (punto 5)
    ok, _, d = await c.call("get_feature_definition", name=cut)
    df = d.get("definition", {})
    record("T10 get_feature_definition del taglio: ambito (corpi con nomi), merge, condizione di fine",
           ok and isinstance(df.get("scope_bodies"), list) and "merge" in df and "feature_scope" in df
           and df.get("direction1", {}).get("end_condition") == "through_all", str({k: df.get(k) for k in ("merge", "feature_scope", "scope_bodies")}))

    # --- try_on_copy: l'originale non cambia (punto 10)
    ok0, _, f0 = await c.call("list_model_features")
    n0, v0 = feature_count(f0), await vol(c)
    ok, text, d = await c.call("try_on_copy", steps=[
        {"tool": "create_sketch_on_face", "arguments": {"x": 10, "y": 50, "z": 20}},
        {"tool": "draw_circle", "arguments": {"x": 60, "y": 20, "radius": 5}},
        {"tool": "extrude_cut", "arguments": {"end_condition": "through_all"}}])
    ok1, _, f1 = await c.call("list_model_features")
    v1 = await vol(c)
    summ = d.get("summary", {})
    cut_vol = v_plate - PI * 25 * 10
    sb = [b.get("volume_mm3") for b in summ.get("bodies", [])]
    record("T11 try_on_copy: la modifica avviene sulla copia (volume 38800 - pi*25*10 = 38014,6)",
           ok and len(sb) == 1 and near(sb[0], cut_vol) and summ.get("rebuild", {}).get("ok") is True, f"copia {sb}: {text[:90]}")
    record("T12 try_on_copy: originale identico (volume e numero di feature) e copia chiusa/cancellata",
           ok1 and near(v1, v0, absolute=1e-6) and feature_count(f1) == n0 and d.get("original", {}).get("unchanged") is True
           and d.get("copy_closed") is True and d.get("temp_deleted") is True and d.get("original", {}).get("reactivated") is True,
           f"volume {v0:.3f}->{v1:.3f}, feature {n0}->{feature_count(f1)}")
    ok, _, dl = await c.call("list_open_documents")
    titles = [x["title"] for x in dl.get("documents", [])]
    record("T13 try_on_copy: nessun documento 'copia' rimasto aperto", ok and len(titles) == 1, str(titles))
    ok, text, d = await c.call("try_on_copy", steps=[{"tool": "set_dimension_value", "arguments": {"name": "D1@NonEsiste", "value": 5}},
                                                   {"tool": "get_mass_properties"}])
    record("T14 try_on_copy: passo che fallisce (quota inesistente) -> errore dichiarato, originale intatto",
           (not ok) and d.get("steps_success") is False and d.get("original", {}).get("unchanged") is True and near(await vol(c), v_plate),
           text[:100])
    ok, text, d = await c.call("try_on_copy", steps=[{"tool": "save_document", "arguments": {"filepath": "x.sldprt"}}])
    record("T15 try_on_copy: save_document vietato nei passi", not ok and "non ammesso" in text, text[:90])

    # --- ripetizione lineare: istanze fuori dal corpo rifiutate, nessuna feature rimasta (punto 3)
    ok, _, f0 = await c.call("list_model_features")
    n0 = feature_count(f0)
    ok, text, d = await c.call("linear_pattern", features=[cut], direction1={"edge": [10, 50, 0]}, count1=10, spacing1=12)
    ok1, _, f1 = await c.call("list_model_features")
    record("T16 linear_pattern con 2 istanze fuori dal corpo: rifiutata e ripetizione eliminata",
           (not ok) and "eliminata" in text and feature_count(f1) == n0 and near(await vol(c), v_plate), text[:110])
    ok, text, d = await c.call("linear_pattern", features=[cut], direction1={"edge": [10, 50, 0]}, count1=8, spacing1=12)
    record("T17 linear_pattern 8 asole entro il corpo: volume 38800 - 7*1200 = 30400",
           ok and near(await vol(c), v_plate - 7 * 1200), f"{await vol(c):.2f} {d.get('instances_check')}")
    await discard_all(c)


# ======================================================================================================= U
async def u_end_refs(c):
    print("\n== U. get_feature_definition: riferimenti delle condizioni di fine")
    await new_part(c)
    await step(c, "create_sketch", plane="Front")
    await step(c, "draw_rectangle", x1=-25, y1=-25, x2=25, y2=25)
    await step(c, "extrude_boss", depth=10)
    await step(c, "create_sketch", plane="Front")
    await step(c, "draw_rectangle", x1=30, y1=-10, x2=50, y2=10)
    ok, _, d = await step(c, "extrude_boss", depth=20, start_offset=30, merge=False)
    target = d.get("feature")
    await step(c, "create_sketch", plane="Front")
    await step(c, "draw_circle", x=40, y=0, radius=3)
    ok, _, d1 = await step(c, "extrude_boss", depth=10, end_condition="up_to_surface", up_to_face_point=[30, 40, 0], merge=False)
    await step(c, "create_sketch", plane="Front")
    await step(c, "draw_circle", x=40, y=5, radius=1)
    ok, _, d2 = await step(c, "extrude_boss", depth=10, end_condition="up_to_vertex", up_to_vertex_point=[50, 50, 10], merge=False)
    await step(c, "create_sketch", plane="Front")
    await step(c, "draw_circle", x=-15, y=15, radius=3)
    ok, _, d3 = await step(c, "extrude_boss", depth=10, end_condition="offset_from_surface", up_to_face_point=[30, 46, 0],
                           offset=2, merge=False)
    ok, _, g1 = await c.call("get_feature_definition", name=d1.get("feature"))
    ref = g1.get("definition", {}).get("direction1", {}).get("end_reference", {})
    record("U1 fino alla superficie: faccia piana x=30, area 400, corpo di appartenenza, punto",
           ref.get("readable") is True and ref.get("kind") == "face" and ref.get("surface") == "plane" and near(ref.get("area", 0), 400, absolute=0.5)
           and ref.get("body") == target and abs(ref.get("point", [0])[0] - 30) < 0.01 and abs(abs(ref["params"]["normal"][0]) - 1) < 1e-6,
           str(ref)[:200])
    ok, _, g2 = await c.call("get_feature_definition", name=d2.get("feature"))
    ref = g2.get("definition", {}).get("direction1", {}).get("end_reference", {})
    record("U2 fino al vertice: punto [50,50,10] e corpo di appartenenza",
           ref.get("readable") is True and ref.get("kind") == "vertex" and ref.get("point") == [50.0, 50.0, 10.0] and ref.get("body") == target,
           str(ref)[:200])
    ok, _, g3 = await c.call("get_feature_definition", name=d3.get("feature"))
    dr = g3.get("definition", {}).get("direction1", {})
    ref = dr.get("end_reference", {})
    record("U3 offset dalla superficie: faccia x=30, offset 2 mm, corpo",
           dr.get("end_condition") == "offset_from_surface" and near(dr.get("depth", 0), 2.0, absolute=1e-6) and ref.get("kind") == "face"
           and ref.get("body") == target and near(ref.get("area", 0), 400, absolute=0.5), str(dr)[:240])
    await discard_all(c)


# ======================================================================================================= O
def union_area_radial_slots(n=6, length=40.0, half_width=2.0, steps=400000):
    """Area dell'unione di n rettangoli [0,length] x [-hw,hw] ruotati di 2*pi/n attorno all'origine (stellati rispetto all'origine)."""
    total = 0.0
    for i in range(steps):
        phi = (i + 0.5) * 2 * PI / steps
        best = 0.0
        for k in range(n):
            a = (phi - k * 2 * PI / n + PI) % (2 * PI) - PI
            if math.cos(a) <= 1e-12:
                continue
            r = length / math.cos(a)
            if abs(math.sin(a)) > 1e-12:
                r = min(r, half_width / abs(math.sin(a)))
            best = max(best, r)
        total += 0.5 * best * best
    return total * 2 * PI / steps


async def o_overlap(c):
    print("\n== O. Ripetizione circolare con istanze sovrapposte al centro dell'asse")
    await new_part(c)
    await step(c, "create_sketch", plane="Front")
    await step(c, "draw_circle", x=0, y=0, radius=50)
    await step(c, "extrude_boss", depth=5)
    await step(c, "create_sketch_on_face", x=5, y=30, z=0)
    await step(c, "draw_rectangle", x1=0, y1=-2, x2=40, y2=2)
    ok, _, d = await step(c, "extrude_cut", end_condition="through_all")
    seed = d.get("feature")
    ok, text, d = await c.call("circular_pattern", features=[seed], axis={"face": [2.5, 0, 50]}, count=6)
    area = union_area_radial_slots()
    exp = (PI * 2500 - area) * 5
    v = await vol(c)
    record("O1 6 asole radiali sovrapposte al centro: ripetizione accettata (era respinta dal controllo del volume)",
           ok and d.get("feature_type") == "CirPattern" and d.get("pattern_effect_mm3", 0) < d.get("pattern_effect_no_overlap_mm3", 0),
           f"{text[:90]} | {d.get('instances_check')}: ultima istanza {d.get('last_instance_effect_mm3')} mm3")
    record("O2 volume = disco - unione analitica delle 6 asole", near(v, exp, 0.002), f"misurato {v:.3f}, atteso {exp:.3f} (unione {area:.3f} mm2)")
    await discard_all(c)


# ======================================================================================================= K
def spoke_outside_area(r_hub=10.0, r_ring_in=45.0, half_w=2.0, n=40000):
    """Area di una razza [8,47] x [-2,2] fuori dal mozzo (r<10) e dall'anello (r>45)."""
    h = 2 * half_w / n
    return sum((math.sqrt(r_ring_in ** 2 - t * t) - math.sqrt(r_hub ** 2 - t * t)) * h
               for t in (-half_w + (i + 0.5) * h for i in range(n)))


async def k_case11(c):
    print("\n== K. Estrusione che unisce piu' corpi: ripetizione di feature, edit_extrude_options, procedura sui corpi")
    await new_part(c)
    await step(c, "create_sketch", plane="Front")
    await step(c, "draw_circle", x=0, y=0, radius=10)
    await step(c, "extrude_boss", depth=5)
    await step(c, "create_sketch", plane="Front")
    await step(c, "draw_circle", x=0, y=0, radius=50)
    await step(c, "draw_circle", x=0, y=0, radius=45)
    ok, _, d = await step(c, "extrude_boss", depth=5, merge=False)
    ring = d.get("feature")
    await step(c, "create_sketch", plane="Front")
    await step(c, "draw_circle", x=0, y=0, radius=10)
    ok, _, d = await step(c, "extrude_boss", depth=5, start_offset=20, merge=False)
    third = d.get("feature")
    bl = await bodies(c)
    hub = [b["name"] for b in bl if b["name"] not in (ring, third)][0]
    v_hub, v_ring, v_third = PI * 100 * 5, PI * (2500 - 2025) * 5, PI * 100 * 5
    record("K0 tre corpi separati: mozzo, anello, terzo corpo", len(bl) == 3 and near(sum(b["volume_mm3"] for b in bl), v_hub + v_ring + v_third),
           f"{[(b['name'], round(b['volume_mm3'], 1)) for b in bl]}")

    # razza sottile (profilo aperto, spessore 4 a mezzeria) che unisce mozzo e anello: Merge=true, ambito = mozzo + anello
    await step(c, "create_sketch", plane="Front")
    await step(c, "draw_line", x1=8, y1=0, x2=47, y2=0)
    ok, _, d = await step(c, "extrude_boss", depth=5, thin_thickness=4, thin_type="mid_plane", merge=True)
    spoke = d.get("feature")
    area_out = spoke_outside_area()
    v_spoke_full = 39 * 4 * 5
    v_merged = v_hub + v_ring + 5 * area_out
    bl = await bodies(c)
    record("K1 la razza fonde mozzo e anello in un corpo; il terzo corpo resta separato",
           len(bl) == 2 and any(near(b["volume_mm3"], v_merged, 0.003) for b in bl) and any(near(b["volume_mm3"], v_third, 0.001) for b in bl),
           f"{[(b['name'], round(b['volume_mm3'], 1)) for b in bl]} atteso fuso {v_merged:.1f}")
    ok, _, g = await c.call("get_feature_definition", name=spoke)
    df = g.get("definition", {})
    record("K2 get_feature_definition: ambito = mozzo + anello (nomi), Merge e FeatureScope veri",
           ok and df.get("merge") is True and df.get("feature_scope") is True and sorted(df.get("scope_bodies", [])) == sorted([hub, ring]),
           str({k: df.get(k) for k in ("merge", "feature_scope", "auto_select_bodies", "scope_bodies")}))

    # caso verificato dall'utente: ripetizione di FEATURE su un seme che fonde piu' corpi
    v_before = await vol(c)
    ok, text, d = await c.call("circular_pattern", features=[spoke], axis={"face": [2.5, 0, 10]}, count=6)
    if not ok:
        record("K3 ripetizione di feature sul seme che fonde piu' corpi: fallisce e il messaggio propone la procedura",
               all(k in text for k in ("edit_extrude_options", "bodies", "combine_bodies", "merge=false")), text[:200])
    else:
        exp3 = v_before + 5 * (v_merged - v_hub - v_ring)
        record("K3 [misura] ripetizione di feature sul seme che fonde piu' corpi: con questo pezzo SolidWorks la CREA (non fallisce): "
               "volume corretto", near(await vol(c), exp3, 0.003), f"{await vol(c):.2f} atteso {exp3:.2f}; procedura non necessaria qui")
        await step(c, "delete_feature", name=d.get("feature"), confirm=True)
    record("K3b volume ripristinato prima di proseguire", near(await vol(c), v_before, 0.001), f"{await vol(c):.2f}")

    # edit_extrude_options: merge=false -> 4 corpi
    ok, text, d = await c.call("edit_extrude_options", feature=spoke, merge=False)
    bl = await bodies(c)
    record("K4 edit_extrude_options merge=false: riletto, 4 corpi (la razza e' un corpo separato di 780 mm3)",
           ok and d.get("mismatch") == {} and d.get("readback", {}).get("merge") is False and len(bl) == 4
           and any(near(b["volume_mm3"], v_spoke_full, 0.002) for b in bl), f"{text[:100]} corpi {len(bl)}")
    # ambito per punti (facce di mozzo e anello) con unione: 2 corpi di nuovo
    ok, text, d = await c.call("edit_extrude_options", feature=spoke, merge=True, scope_bodies=[[2.5, 0, 10], [2.5, 0, 50]])
    bl = await bodies(c)
    record("K5 edit_extrude_options merge=true + ambito per punti: riletto (ambito = mozzo + anello), 2 corpi",
           ok and sorted(d.get("readback", {}).get("scope_bodies", [])) == sorted([hub, ring]) and d.get("readback", {}).get("feature_scope") is True
           and d.get("readback", {}).get("auto_select_bodies") is False and len(bl) == 2 and d.get("mismatch") == {},
           f"{text[:110]}")
    ok, text, d = await c.call("edit_extrude_options", feature=spoke, scope_bodies=["CorpoInesistente"])
    record("K6 edit_extrude_options con un corpo dell'ambito inesistente: errore chiaro, nulla cambia",
           (not ok) and "non trovato" in text and len(await bodies(c)) == 2, text[:100])
    ok, text, d = await c.call("edit_extrude_options", feature=spoke, depth=8, end_condition="blind")
    ok2, _, g = await c.call("get_feature_definition", name=spoke)
    record("K7 edit_extrude_options profondita' 5 -> 8: riletta anche da get_feature_definition",
           ok and near(g.get("definition", {}).get("direction1", {}).get("depth", 0), 8.0, absolute=1e-6), text[:100])
    await c.call("edit_extrude_options", feature=spoke, depth=5)
    ok, text, d = await c.call("edit_extrude_options", feature=spoke, merge=False)
    record("K8 merge=false di nuovo (4 corpi) e profondita' ripristinata a 5", ok and len(await bodies(c)) == 4, text[:100])

    # seme a corpo separato: la ripetizione di FEATURE non viene creata, il messaggio dice perche' e propone la procedura
    nf0 = feature_count((await c.call("list_model_features"))[2])
    ok, text, d = await c.call("circular_pattern", features=[spoke], axis={"face": [2.5, 0, 10]}, count=6)
    nf1 = feature_count((await c.call("list_model_features"))[2])
    record("K9 seme con Merge=false: ripetizione di feature non creata, messaggio con causa e procedura",
           (not ok) and "nessuna feature" in text and "SEPARATO" in text and all(k in text for k in ("edit_extrude_options", "bodies", "combine_bodies"))
           and nf1 == nf0, text[:160])

    # procedura: ripetizione dei CORPI -> combine_bodies
    ok, text, d = await c.call("circular_pattern", bodies=[[5, 30, 0]], axis={"face": [2.5, 0, 10]}, count=6)
    bl = await bodies(c)
    record("K10 circular_pattern con bodies: 6 razze (4 -> 9 corpi)", ok and len(bl) == 9, f"{text[:90]} corpi {len(bl)}")
    hub_b = [b for b in bl if near(b["volume_mm3"], v_hub, 0.001) and b["centroid"][0] < 10]
    ring_b = [b for b in bl if near(b["volume_mm3"], v_ring, 0.001)]
    third_b = [b for b in bl if b["centroid"][0] > 15]
    spokes = [b for b in bl if near(b["volume_mm3"], v_spoke_full, 0.002)]
    ok_sel = len(hub_b) == 1 and len(ring_b) == 1 and len(third_b) == 1 and len(spokes) == 6
    record("K11 corpi riconosciuti: mozzo, anello, 6 razze, terzo corpo", ok_sel,
           f"{len(hub_b)} mozzo, {len(ring_b)} anello, {len(spokes)} razze, {len(third_b)} terzo")
    if ok_sel:
        main = hub_b[0]["face_point"]
        tools_ = [ring_b[0]["face_point"]] + [s["face_point"] for s in spokes]
        ok, text, d = await c.call("combine_bodies", main=main, tools=tools_, operation="add")
        bl = await bodies(c)
        merged = [b for b in bl if b["centroid"][0] < 10]
        third_b = [b for b in bl if b["centroid"][0] > 15]
        v_exp = v_hub + v_ring + 6 * 5 * area_out
        record("K12 combine_bodies (add): 2 corpi; volume = mozzo + anello + 6 razze (sovrapposizioni escluse, calcolo analitico)",
               ok and len(bl) == 2 and len(merged) == 1 and near(merged[0]["volume_mm3"], v_exp, 0.003),
               f"{text[:80]} misurato {merged[0]['volume_mm3']:.2f} atteso {v_exp:.2f}" if merged else text[:100])
        record("K13 il terzo corpo resta separato con volume e posizione invariati",
               len(third_b) == 1 and near(third_b[0]["volume_mm3"], v_third, 0.0005) and abs(third_b[0]["centroid"][0] - 22.5) < 0.01,
               f"{[(round(b['volume_mm3'], 2), b['centroid']) for b in third_b]}")
    ok, text, d = await c.call("get_rebuild_errors")
    record("K14 nessun errore di ricostruzione alla fine", ok and d.get("rebuild_ok") is True, text[:80])
    await discard_all(c)


# ======================================================================================================= Q
async def q_bodies(c):
    print("\n== Q. query_topology_by_criteria: nome del corpo")
    await new_part(c)
    await step(c, "create_sketch", plane="Front")
    await step(c, "draw_rectangle", x1=0, y1=0, x2=20, y2=20)
    await step(c, "extrude_boss", depth=10)
    await step(c, "create_sketch", plane="Front")
    await step(c, "draw_circle", x=-30, y=10, radius=5)
    await step(c, "extrude_boss", depth=10, merge=False)
    bl = await bodies(c)
    bnames = sorted(b["name"] for b in bl)
    ok, text, d = await c.call("query_topology_by_criteria", entity_type="face", surface_type="cylinder")
    ents = d.get("entities", [])
    record("Q1 faccia cilindrica: riporta il corpo di appartenenza",
           ok and len(ents) >= 1 and all("body" in e for e in ents) and {e["body"] for e in ents} <= set(bnames) and len(bl) == 2,
           f"{[(e['type'], e['body']) for e in ents]} corpi {bnames}")
    ok, text, d = await c.call("query_topology_by_criteria", entity_type="face", surface_type="plane")
    ents = d.get("entities", [])
    record("Q2 facce piane di due corpi: i nomi dei corpi coprono entrambi",
           ok and {e.get("body") for e in ents} == set(bnames), f"{len(ents)} facce, corpi {sorted({e.get('body') for e in ents})}")
    ok, _, d = await c.call("query_topology_by_criteria", entity_type="edge")
    record("Q3 spigoli e vertici: riportano il corpo", ok and all("body" in e for e in d.get("entities", [])) and
           all("body" in e for e in (await c.call("query_topology_by_criteria", entity_type="vertex"))[2].get("entities", [])))
    await discard_all(c)


# ===================================================================================================== principale
SECTIONS = (("T", t_plate), ("U", u_end_refs), ("O", o_overlap), ("K", k_case11), ("Q", q_bodies))


async def scenario(c):
    only = {a.upper() for a in sys.argv[1:]}
    for nome, fn in SECTIONS:
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
                record("tool nuovi esposti", all(t in tools for t in ("edit_extrude_options", "try_on_copy")), "")
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
        print(f"{res:5} {tool:80} {note}"[:300])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
