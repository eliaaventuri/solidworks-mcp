"""
Test live dei tool di ASSIEME (blocco 2) tramite il server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente non viene mai
toccata; alla fine si chiude solo il PID lanciato dal test. Costruisce SOLO tramite tool MCP:
  - pezzi: staffa (piastra con foro e 6 fori), boccola flangiata, perno, vite, perno largo (interferenza), piastra con ripetizione;
  - assieme perno-staffa-boccola-viti: accoppiamenti concentrico/coincidente/parallelo/distanza/angolo, 6 viti con ripetizione
    circolare, completamente vincolato; interferenze (0 nel corretto, >=1 in quello costruito apposta), massa, gioco;
  - vista esplosa a 3 passi; tavola A3 con isometrica esplosa, distinta, palloncini; export PDF/PNG;
  - strumenti su componenti sciolti, ripetizione lineare/guidata, specchiatura, configurazioni, spostamenti.

Uso:  .venv\\Scripts\\python.exe tests\\test_assembly_live.py       Output: test_output\\ (SLDPRT, SLDASM, SLDDRW, PNG, PDF)
"""

import os
import sys
import json
import math
import asyncio
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup
PI = math.pi
TOL_MM = 1e-3          # 1e-6 m

RESULTS = []


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:230])


async def T(c, tool, label=None, check=None, expect_fail=False, **args):
    """Chiama un tool MCP e registra PASS/FAIL (check = funzione sui dati restituiti)."""
    ok, text, d = await c.call(tool, **args)
    if expect_fail:
        good = not ok
    else:
        good = ok
        if ok and check is not None:
            try:
                good = bool(check(d))
            except Exception as e:
                good = False
                text += f" [check: {e}]"
    record(f"{tool}: {label}" if label else tool, good, text.split("\n")[0][:170])
    return d if (ok or expect_fail) else {}


def F(name, ext="SLDPRT"):
    return str(OUT / f"{name}.{ext}")


def rm(*names):
    for n in names:
        p = Path(n)
        if p.exists():
            p.unlink()


class Asm:
    """Helper di lettura pose per costruire punti sulle facce dei componenti."""

    def __init__(self, c):
        self.c = c

    async def comps(self):
        ok, _, d = await self.c.call("list_components")
        return {x["name"]: x for x in d.get("components", [])} if ok else {}

    async def pose(self, name):
        return (await self.comps()).get(name)

    async def loc2asm(self, name, p):
        t = (await self.pose(name))["transform"]          # 9 rot (righe = immagini degli assi) + 3 trasl [m]
        return [round(sum(p[i] * t[3 * i + j] for i in range(3)) + t[9 + j] * 1000.0, 4) for j in range(3)]


# ============================================================================================ avvio
async def run():
    elia_pids = sw_pids()
    print(f"Istanze SolidWorks gia' presenti (da non toccare): {sorted(elia_pids)}")
    env = dict(os.environ)
    env["SW_MCP_INSTANCE"] = "dedicated"
    params = StdioServerParameters(command=str(PYTHON), args=[str(SERVER)], env=env, cwd=str(ROOT))
    my_pid = None
    try:
        async with stdio_client(params) as (rd, wr):
            async with ClientSession(rd, wr, read_timeout_seconds=timedelta(seconds=900)) as session:
                await session.initialize()
                c = Client(session)
                tools = [t.name for t in (await session.list_tools()).tools]
                print(f"{len(tools)} tool esposti")
                ok, text, data = await c.call("connect_solidworks")
                my_pid = data.get("pid")
                print(text[:200])
                if not ok or not my_pid or my_pid in elia_pids or my_pid not in sw_pids():
                    print("STOP: nessuna istanza separata ottenibile. Nulla e' stato toccato.")
                    return False
                print(f"Istanza dedicata PID {my_pid} (diversa da {sorted(elia_pids)})")
                record("PID dedicato diverso dall'istanza utente", my_pid not in elia_pids, str(my_pid))
                await scenario(c, tools)
    finally:
        cleanup(my_pid, elia_pids)
    return True


# ============================================================================================ pezzi
async def build_parts(c):
    print("\n== 0. Pezzi (tool di modellazione)")
    for n in ("staffa", "boccola", "perno", "vite", "pernolargo", "piastra"):
        rm(F("asm_" + n))

    async def save(n):
        await T(c, "save_document", f"salva asm_{n}", filepath=F("asm_" + n))
        await c.call("close_document", discard=True)

    # staffa: piastra 80x80x10 (x 0..10), foro centrale d20, 6 fori d5,5 su diametro 60
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-40, y1=-40, x2=40, y2=40)
    await T(c, "extrude_boss", "staffa 80x80x10", depth=10)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=10)
    await T(c, "extrude_cut", "foro centrale d20", end_condition="through_all_both")
    await c.call("create_sketch", plane="Front")
    for k in range(6):
        a = math.radians(30 + 60 * k)
        await c.call("draw_circle", x=30 * math.cos(a), y=30 * math.sin(a), radius=2.75)
    await T(c, "extrude_cut", "6 fori d5,5", end_condition="through_all_both")
    await c.call("set_material", material="AISI 1020")
    await T(c, "create_reference_axis", "asse del foro centrale", mode="cylinder", face_point=[5, 10, 0])
    ok, _, m = await c.call("get_mass_properties")
    record("staffa: volume = 80x80x10 - foro - 6 fori", ok and abs(m["volume_mm3"] - (64000 - PI * 100 * 10 - 6 * PI * 2.75 ** 2 * 10)) < 1.0,
           f"{m.get('volume_mm3')}")
    await save("staffa")
    # boccola flangiata: flangia d28 x3 (x 0..3), tubo d20 x10 (x 3..13), foro d12,5
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=14)
    await c.call("extrude_boss", depth=3)
    await c.call("create_sketch_on_face", x=3, y=0, z=0)
    await c.call("draw_circle", x=0, y=0, radius=10)
    await c.call("extrude_boss", depth=10)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=6.25)
    await T(c, "extrude_cut", "foro boccola d12,5", end_condition="through_all_both")
    await c.call("set_material", material="Bronzo")
    await c.call("create_reference_axis", mode="cylinder", face_point=[8, 10, 0])
    await save("boccola")
    # perno: testa d18 x4 (x 0..4), gambo d12 x40 (x 4..44)
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=9)
    await c.call("extrude_boss", depth=4)
    await c.call("create_sketch_on_face", x=4, y=0, z=0)
    await c.call("draw_circle", x=0, y=0, radius=6)
    await c.call("extrude_boss", depth=40)
    await c.call("set_material", material="AISI 1020")
    await c.call("create_reference_axis", mode="cylinder", face_point=[20, 6, 0])
    await save("perno")
    # vite: testa d9 x4, gambo d5 x14
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=4.5)
    await c.call("extrude_boss", depth=4)
    await c.call("create_sketch_on_face", x=4, y=0, z=0)
    await c.call("draw_circle", x=0, y=0, radius=2.5)
    await c.call("extrude_boss", depth=14)
    await c.call("set_material", material="AISI 1020")
    await c.call("create_reference_axis", mode="cylinder", face_point=[10, 2.5, 0])
    await save("vite")
    # perno largo d24 x30 (interferenza con il foro d20)
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=12)
    await c.call("extrude_boss", depth=30)
    await c.call("set_material", material="AISI 1020")
    await save("pernolargo")
    # piastra con foro d5,5 ripetuto 4 volte (feature di ripetizione per la ripetizione guidata)
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-40, y1=-40, x2=40, y2=40)
    await c.call("extrude_boss", depth=10)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=10)
    await c.call("extrude_cut", end_condition="through_all_both")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=30, y=0, radius=2.75)
    r = await c.call("extrude_cut", end_condition="through_all_both")
    await c.call("create_reference_axis", mode="cylinder", face_point=[5, 10, 0])
    await T(c, "circular_pattern", "ripetizione fori (per la guidata)", features=[r[2]["feature"]], axis={"face": [5, 10, 0]}, count=4)
    await save("piastra")


# ============================================================================================ scenario
async def scenario(c, tools):
    need = ["insert_component", "add_mate", "component_circular_pattern", "create_exploded_view", "check_interference",
            "get_assembly_status", "list_bom"]
    record("tool di assieme esposti", all(n in tools for n in need), f"{len(tools)} tool totali")
    await build_parts(c)
    await main_assembly(c)
    await scratch_assembly(c)
    await interference_case(c)


async def main_assembly(c):
    print("\n== 1. Assieme perno-staffa-boccola-viti")
    A = Asm(c)
    S, B, PN = "asm_staffa-1", "asm_boccola-1", "asm_perno-1"
    asm_path = F("asm_main", "SLDASM")
    rm(asm_path)
    await T(c, "create_new_assembly")
    await T(c, "insert_component", "staffa fissa all'origine", file_path=F("asm_staffa"), x=0, y=0, z=0, fixed=True,
            check=lambda d: d["fixed"] and d["position_mm"] == [0, 0, 0])
    await T(c, "insert_component", "boccola fuori posto", file_path=F("asm_boccola"), x=-30, y=15, z=5,
            check=lambda d: d["position_mm"] == [-30, 15, 5])
    await T(c, "insert_component", "perno ruotato di 30 gradi", file_path=F("asm_perno"), x=-60, y=-20, z=10, rotation=[30, 0, 0],
            check=lambda d: abs(d["rotation_deg"][0] - 30) < 1e-3)
    await T(c, "list_components", "3 componenti, staffa fissa, altri mobili",
            check=lambda d: d["count"] == 3 and [x["fixed"] for x in d["components"]].count(True) == 1)
    # boccola: concentrico (tubo d20 con foro d20), coincidente (spalla con faccia), parallelo (blocca la rotazione)
    await T(c, "add_mate", "concentrico boccola-foro (facce cilindriche)", mate_type="concentric",
            entity1={"component": B, "face": [-22, 25, 5]}, entity2={"component": S, "face": [5, 10, 0]},
            check=lambda d: d["type"] == "concentric" and not d["in_error"])
    p = await A.pose(B)
    record("boccola: dopo il concentrico asse sull'asse del foro (y=z=0)", abs(p["position_mm"][1]) < TOL_MM and abs(p["position_mm"][2]) < TOL_MM,
           f"{p['position_mm']}")
    await T(c, "add_mate", "coincidente spalla boccola-faccia staffa", mate_type="coincident",
            entity1={"component": B, "face": [-27, 12, 0]}, entity2={"component": S, "face": [0, 35, 0]}, align="anti_aligned",
            check=lambda d: d["type"] == "coincident")
    await T(c, "add_mate", "parallelo piani superiori (blocca rotazione)", mate_type="parallel",
            entity1=f"Piano superiore@{B}", entity2=f"Piano superiore@{S}", check=lambda d: d["type"] == "parallel")
    p = await A.pose(B)
    record("boccola: origine a (-3, 0, 0) mm entro 1e-6 m", all(abs(a - b) < TOL_MM for a, b in zip(p["position_mm"], [-3, 0, 0])),
           f"{p['position_mm']}")
    # perno: assi coincidenti, distanza 5 mm fra sotto-testa e spalla, angolo 90 gradi
    await T(c, "add_mate", "concentrico perno-boccola (assi di riferimento -> coincidente)", mate_type="concentric",
            entity1=f"Assi1@{PN}", entity2=f"Assi1@{B}", check=lambda d: not d["in_error"])
    under = await A.loc2asm(PN, [4, 7.5, 0])
    await T(c, "add_mate", "distanza 5 mm sotto-testa perno / spalla boccola", mate_type="distance",
            entity1={"component": PN, "face": under}, entity2={"component": B, "face": [-3, 12, 0]}, distance=5, align="anti_aligned",
            check=lambda d: d["value"] == 5.0)
    await T(c, "add_mate", "angolo 90 gradi fra piano superiore perno e piano destro staffa", mate_type="angle",
            entity1=f"Piano superiore@{PN}", entity2=f"Piano destro@{S}", angle=90, check=lambda d: d["value"] == 90.0)
    p = await A.pose(PN)
    t = p["transform"]
    record("perno: origine (-12,0,0) e asse X coincidente con l'asse del foro entro 1e-6 m",
           all(abs(a - b) < TOL_MM for a, b in zip(p["position_mm"], [-12, 0, 0])) and abs(abs(t[0]) - 1) < 1e-6
           and abs(t[1]) < 1e-6 and abs(t[2]) < 1e-6, f"{p['position_mm']} asse {t[:3]}")
    # vite seme + 3 accoppiamenti, poi ripetizione circolare
    d = await T(c, "insert_component", "vite seme (ruotata 180 gradi)", file_path=F("asm_vite"), x=40, y=45, z=30, rotation=[0, 180, 0])
    V = d.get("name", "asm_vite-1")
    await T(c, "add_mate", "concentrico vite-foro", mate_type="concentric",
            entity1={"component": V, "face": await A.loc2asm(V, [10, 2.5, 0])},
            entity2={"component": S, "face": [5, 25.98 + 2.75, 15]}, check=lambda d: not d["in_error"])
    await T(c, "add_mate", "coincidente sotto-testa vite / faccia posteriore staffa", mate_type="coincident",
            entity1={"component": V, "face": await A.loc2asm(V, [4, 3.5, 0])}, entity2={"component": S, "face": [10, -35, 0]},
            align="anti_aligned", check=lambda d: not d["in_error"])
    await T(c, "add_mate", "parallelo piani superiori vite/staffa", mate_type="parallel",
            entity1=f"Piano superiore@{V}", entity2=f"Piano superiore@{S}", check=lambda d: not d["in_error"])
    pv = await A.pose(V)
    record("vite seme: sotto-testa sul piano x=10 e asse sul foro (r=30 a 30 gradi)",
           abs(pv["position_mm"][0] - 14) < TOL_MM and abs(math.hypot(pv["position_mm"][1], pv["position_mm"][2]) - 30) < TOL_MM,
           f"{pv['position_mm']}")
    await T(c, "component_circular_pattern", "6 viti sulla flangia", components=[V], axis=f"Assi1@{S}", count=6,
            check=lambda d: d["total_instances"] == 6 and len(d["new_components"]) == 5)
    comps = await A.comps()
    vit = {n: x for n, x in comps.items() if "vite" in n}
    radii = [math.hypot(x["position_mm"][1], x["position_mm"][2]) for x in vit.values()]
    angs = sorted(round(math.degrees(math.atan2(x["position_mm"][2], x["position_mm"][1])) % 360, 2) for x in vit.values())
    record("6 viti a r=30 mm e passo 60 gradi", len(vit) == 6 and all(abs(r - 30) < TOL_MM for r in radii)
           and all(abs(a - (30 + 60 * k)) < 0.01 for k, a in enumerate(angs)), f"{len(vit)} viti, r={set(round(r, 4) for r in radii)}, angoli {angs}")
    record("viti: istanze della ripetizione marcate", sum(1 for x in vit.values() if x.get("pattern_instance")) == 5)
    # stato, accoppiamenti
    await T(c, "get_assembly_status", "completamente vincolato", check=lambda d: d["fully_constrained"] and not d["mates_in_error"])
    d = await T(c, "list_mates", "9 accoppiamenti (4 coincidenti/concentrici + ...)", check=lambda d: d["count"] == 9 and not d["in_error"])
    kinds = sorted(m["type"] for m in d.get("mates", []))
    record("list_mates: tipi presenti (concentric, coincident, parallel, distance, angle)",
           {"concentric", "coincident", "parallel", "distance", "angle"} <= set(kinds), str(kinds))
    await T(c, "edit_mate", "distanza 5 -> 8 mm", name="Distanza1", value=8, check=lambda d: d["value"] == 8.0)
    p = await A.pose(PN)
    record("perno: dopo la modifica della distanza l'origine e' a -15 mm", abs(p["position_mm"][0] + 15) < TOL_MM, f"{p['position_mm']}")
    await T(c, "edit_mate", "distanza 8 -> 5 mm", name="Distanza1", value=5, check=lambda d: d["value"] == 5.0)
    await T(c, "move_component", "componente vincolato non si sposta (rispetta i vincoli)", component=PN, dx=20,
            check=lambda d: d["moved_mm"] < TOL_MM)
    await T(c, "move_component", "componente fisso rifiutato", component=S, dx=20, expect_fail=True)
    # analisi
    await T(c, "check_interference", "assieme corretto: 0 interferenze", check=lambda d: d["count"] == 0)
    d = await T(c, "get_assembly_mass_properties", "massa totale = somma masse componenti",
                check=lambda d: abs(d["mass_kg"] - d["sum_of_components_kg"]) < 1e-9 and len(d["files"]) == 4)
    if d:
        record("massa: 4 file (staffa 1, boccola 1, perno 1, vite 6) e massa assieme", {f["file"]: f["count"] for f in d["files"]} ==
               {"asm_staffa.SLDPRT": 1, "asm_boccola.SLDPRT": 1, "asm_perno.SLDPRT": 1, "asm_vite.SLDPRT": 6},
               f"{d['mass_kg']:.6f} kg = somma {d['sum_of_components_kg']:.6f} kg")
    await T(c, "count_components", "9 componenti in 4 file", check=lambda d: d["total"] == 9 and d["distinct_files"] == 4)
    await T(c, "check_clearance", "gioco perno-staffa = 4,0 mm (foro d20, gambo d12)", entity1=PN, entity2=S,
            check=lambda d: abs(d["distance_mm"] - 4.0) < 1e-3)
    # vista esplosa
    vs = [f"asm_vite-{i}" for i in range(1, 7)]
    steps = [{"components": [PN], "direction": "-x", "distance": 60}, {"components": [B], "direction": "-x", "distance": 30},
             {"components": vs, "direction": "x", "distance": 40}]
    await T(c, "create_exploded_view", "3 passi", steps=steps, check=lambda d: len(d["steps"]) == 3 and d["exploded"])
    await T(c, "list_exploded_views", "1 vista, 3 passi", check=lambda d: len(d["views"]) == 1 and len(d["steps"]) == 3)
    await T(c, "export_model_image", "assieme esploso (isometrica)", filepath=str(OUT / "asm_main_esploso.png"), view="isometric")
    await T(c, "show_exploded", "comprimi", exploded=False, check=lambda d: d["exploded"] is False)
    p = await A.pose(PN)
    record("dopo la compressione il perno e' tornato a -12 mm", abs(p["position_mm"][0] + 12) < TOL_MM, f"{p['position_mm']}")
    await T(c, "export_model_image", "assieme compresso (isometrica)", filepath=str(OUT / "asm_main.png"), view="isometric")
    await T(c, "save_document", "salva assieme", filepath=asm_path)
    await T(c, "add_assembly_configuration", "configurazione Alt", name="Alt", check=lambda d: "Alt" in d["configurations"])
    await T(c, "list_assembly_configurations", "2 configurazioni", check=lambda d: len(d["configurations"]) == 2)
    await T(c, "activate_assembly_configuration", "riattiva Default", name="Default", check=lambda d: d["active"] == "Default")
    await T(c, "save_document", "salva assieme (con configurazione)", filepath=asm_path)

    # ---- tavola d'assieme
    print("\n== 2. Tavola d'assieme A3 con vista esplosa")
    drw = F("asm_main", "SLDDRW")
    rm(drw, F("asm_main_tavola", "png"), F("asm_main_tavola", "pdf"), F("asm_main_tavola", "dxf"))
    d = await T(c, "create_drawing", "A3 dall'assieme", model_path=asm_path, paper_size="A3", save_as=drw, add_views=False,
                check=lambda d: d.get("still_missing") in ([], ["Weight"]))
    d = await T(c, "add_standard_views", "isometrica ESPLOSA (+ frontale di riferimento)", views=["front", "isometric"], exploded=True,
                check=lambda d: any(v["exploded"] for v in d["views"]) and "exploded_failed" not in d)
    ok, _, lv = await c.call("list_drawing_views")
    viste = lv.get("views", [])
    exploded = [v for v in viste if v["exploded"]]
    record("viste: l'isometrica e' esplosa, la frontale no", len(exploded) == 1 and len(viste) == 2 and exploded[0]["width_mm"] > 100,
           f"{[(v['name'], v['exploded']) for v in viste]}")
    nm = exploded[0]["name"] if exploded else None
    d = await T(c, "add_bom", "distinta sulla vista esplosa", view=nm, bom_type="parts_only", check=lambda d: d["rows"] == 5)
    d = await T(c, "list_bom", "righe e quantita' corrette")
    hdr = [str(h) for h in (d.get("header") or [])] if d else []      # intestazioni del modello di distinta: cambiano con la lingua
    c_part = next((h for h in hdr if "num. parte" in h.lower() or "part n" in h.lower()), None)
    c_qty = next((h for h in hdr if "quantit" in h.lower() or "qty" in h.lower()), None)
    rows = {r[c_part]: int(r[c_qty]) for r in d.get("rows", [])} if d and c_part and c_qty else {}
    record("distinta: staffa 1, boccola 1, perno 1, vite 6 (4 righe)", rows == {"asm_staffa": 1, "asm_boccola": 1, "asm_perno": 1, "asm_vite": 6},
           str(rows))
    d = await T(c, "add_balloons", "palloncini sulla vista esplosa", view=nm)
    record("palloncini = componenti distinti (4)", d.get("count") == len(rows) == 4, f"{d.get('count')} palloncini, {len(rows)} righe")
    await T(c, "save_drawing", "salva tavola", filepath=drw)
    for ext in ("png", "pdf", "dxf"):
        p = Path(F("asm_main_tavola", ext))
        await T(c, "export_drawing", f"esporta {ext}", filepath=str(p), format=ext)
        record(f"export {ext}: file > 0 byte", p.exists() and p.stat().st_size > 0, f"{p.stat().st_size if p.exists() else 0} B")
    txt = Path(F("asm_main_tavola", "dxf")).read_text(encoding="latin-1", errors="ignore") if Path(F("asm_main_tavola", "dxf")).exists() else ""
    record("cartiglio senza 'ERRORE'", len(txt) > 1000 and "ERROR" not in txt, f"{txt.count('ERROR')} occorrenze")
    record("cartiglio: titolo e peso presenti nel DXF", "asm_main" in txt and "563.5" in txt.replace(",", "."), "")
    await c.call("close_document", discard=True)       # tavola
    await c.call("close_document", discard=True)       # assieme


async def scratch_assembly(c):
    print("\n== 3. Strumenti su componenti, ripetizioni, specchiatura (assieme di servizio)")
    A = Asm(c)
    await T(c, "create_new_assembly")
    await T(c, "insert_component", "piastra fissa", file_path=F("asm_piastra"), fixed=True)
    d = await T(c, "insert_components", "3 viti sciolte (start + step)", file_path=F("asm_vite"), count=3, start=[100, 10, 0], step=[0, 20, 0],
                check=lambda d: len(d["components"]) == 3)
    loose = d.get("components", [])
    comps = await A.comps()
    record("insert_components: posizioni a passo 20 mm", all(abs(comps[n]["position_mm"][1] - (10 + 20 * i)) < TOL_MM for i, n in enumerate(loose)) if loose else False,
           f"{[comps[n]['position_mm'] for n in loose]}" if loose else "")
    v1 = loose[0]
    await T(c, "move_component", "sposta componente mobile di +10 mm in X", component=v1, dx=10,
            check=lambda d: abs(d["moved_mm"] - 10) < 1e-3 and abs(d["position_mm"][0] - 110) < TOL_MM)
    await T(c, "move_component", "ruota componente mobile di 90 gradi attorno a Z", component=v1, rotate_by=[0, 0, 90],
            check=lambda d: abs(d["rotation_deg"][2] - 90) < 1e-3)
    await T(c, "set_component_fixed", "fissa", component=v1, check=lambda d: d["fixed"])
    await T(c, "move_component", "fisso non si muove", component=v1, dx=5, expect_fail=True)
    await T(c, "set_component_fixed", "rende mobile", component=v1, fixed=False, check=lambda d: not d["fixed"])
    await T(c, "suppress_component", "sopprimi", component=loose[1], check=lambda d: d["suppressed"])
    await T(c, "suppress_component", "riattiva", component=loose[1], suppressed=False, check=lambda d: not d["suppressed"])
    await T(c, "set_component_visibility", "nascondi", component=loose[1], visible=False, check=lambda d: d["hidden"])
    await T(c, "set_component_visibility", "mostra", component=loose[1], visible=True, check=lambda d: not d["hidden"])
    await T(c, "replace_component", "sostituisce una vite con il perno", component=loose[2], new_file=F("asm_perno"),
            check=lambda d: any("perno" in n for n in d["new_components"]))
    ok, _, d = await c.call("count_components")
    record("count_components dopo la sostituzione: 1 piastra, 2 viti, 1 perno", ok and {f["file"]: f["count"] for f in d["files"]} ==
           {"asm_piastra.SLDPRT": 1, "asm_vite.SLDPRT": 2, "asm_perno.SLDPRT": 1}, str({f["file"]: f["count"] for f in d.get("files", [])}))
    await T(c, "open_component", "apre il pezzo del componente", component=loose[0], check=lambda d: "asm_vite" in d["title"])
    ok, _, d = await c.call("get_document_info")
    record("open_component: il documento attivo e' il pezzo", ok and "asm_vite" in json.dumps(d), "")
    ok, _, lo = await c.call("list_open_documents")
    asm_title = next((x.get("name") or x.get("title") for x in (lo.get("documents") or lo.get("data", {}).get("documents", [])) if x.get("type") == "Assembly"), "Assieme")      # dal tipo: il titolo cambia con la lingua
    await T(c, "activate_document", "torna all'assieme", name=asm_title)
    # mate eliminato
    await T(c, "add_mate", "mate di servizio (parallelo piani frontali)", mate_type="parallel", entity1=f"Piano frontale@{loose[0]}",
            entity2="Piano frontale@asm_piastra-1")
    ok, _, d = await c.call("list_mates")
    name = d["mates"][-1]["name"] if ok and d.get("mates") else "Parallelo1"
    await T(c, "delete_mate", "elimina mate", name=name, check=lambda d: d["remaining"] == 0)
    await T(c, "delete_component", "elimina componente", component=loose[1], check=lambda d: d["deleted"] == loose[1])
    # ripetizioni
    d = await T(c, "component_linear_pattern", "lineare lungo lo spigolo Y della piastra (2 istanze, passo 5)", components=[loose[0]],
                direction1={"edge": [0, 40, 0]}, count1=2, spacing1=5, check=lambda d: d["total_instances"] == 2)
    d = await T(c, "component_derived_pattern", "guidata dalla ripetizione di fori della piastra", components=[loose[0]],
                pattern_feature="RipetizioneCircolare1", pattern_component="asm_piastra-1", check=lambda d: len(d["new_components"]) == 3)
    before = await A.comps()
    d = await T(c, "mirror_components", "specchia la vite rispetto al Piano destro", components=[loose[0]], plane="Piano destro",
                check=lambda d: len(d["new_components"]) == 1)
    if d.get("new_components"):
        now = await A.comps()
        nn = d["new_components"][0]
        p0, p1 = before[loose[0]]["position_mm"], now[nn]["position_mm"]
        record("mirror_components: istanza speculare nella posizione attesa (y -> -y)", abs(p1[1] + p0[1]) < 0.01 and abs(p1[0] - p0[0]) < 0.01,
               f"origine {p0} -> {p1}")
    # auto esplosione in un assieme semplice
    pn = next((n for n in (await A.comps()) if "perno" in n), "asm_perno-1")
    await T(c, "delete_component", "pulizia per l'esplosione automatica", component=pn)
    await T(c, "auto_explode", "esplosione automatica lungo Y", axis="y", gap=25, check=lambda d: len(d["steps"]) >= 2)
    await c.call("close_document", discard=True)


async def interference_case(c):
    print("\n== 4. Interferenza costruita apposta")
    A = Asm(c)
    path = F("asm_interf", "SLDASM")
    rm(path)
    await T(c, "create_new_assembly")
    await T(c, "insert_component", file_path=F("asm_staffa"), fixed=True)
    await T(c, "insert_component", "perno d24 attraverso il foro d20", file_path=F("asm_pernolargo"), x=0, y=0, z=0)
    expected = PI / 4 * (24 ** 2 - 20 ** 2) * 10
    d = await T(c, "check_interference", "almeno 1 interferenza", check=lambda d: d["count"] >= 1)
    v = d.get("total_volume_mm3", 0)
    record("interferenza: volume = pi/4(24^2-20^2)x10 = %.1f mm3 (entro 0,5%%)" % expected, abs(v - expected) / expected < 0.005,
           f"misurato {v}")
    if d.get("interferences"):
        record("interferenza: coppia staffa / perno largo", sorted(d["interferences"][0]["components"]) == ["asm_pernolargo-1", "asm_staffa-1"],
               str(d["interferences"][0]["components"]))
    await T(c, "check_clearance", "gioco con interferenza = contatto", entity1="asm_staffa-1", entity2="asm_pernolargo-1",
            check=lambda d: d["distance_mm"] == 0.0)
    await T(c, "save_document", filepath=path)
    await c.call("close_document", discard=True)


if __name__ == "__main__":
    done = asyncio.run(run())
    print("\n==== RIEPILOGO ====")
    for tool, res, note in RESULTS:
        print(f"{res:5} {tool:80} {note}"[:230])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
