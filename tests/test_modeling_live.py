"""
Test live dei tool di MODELLAZIONE 3D (blocco 1) tramite il server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente
non viene mai toccata; alla fine si chiude solo il PID lanciato dal test.

Costruisce SOLO tramite tool MCP: albero a gradini, staffa a L, flangia, loft, sweep, blocchi di prova.
Per ogni pezzo: volume (CreateMassProperty) confrontato con il calcolo a mano (< 0,5 %), feature, stato dello
schizzo, modifica di una quota + ricostruzione, disegno con quote del modello importate.

Uso:  .venv\\Scripts\\python.exe tests\\test_modeling_live.py
Output: test_output\\ (SLDPRT, SLDDRW, PNG)
"""

import os
import sys
import json
import math
import asyncio
import subprocess
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "test_output"
OUT.mkdir(exist_ok=True)
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
SERVER = ROOT / "solidworks_mcp_server.py"
PI = math.pi
TOL = 0.005          # 0,5 %

OVERWRITE_TOOLS = {"save_document", "save_drawing", "export_drawing", "export_model", "export_model_image", "export_simulation_plot", "create_drawing"}
RESULTS = []         # (tool, PASS/FAIL, nota)


def sw_pids():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq SLDWORKS.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    pids = set()
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) > 1 and parts[0].strip('"').lower() == "sldworks.exe":
            pids.add(int(parts[1]))
    return pids


class Client:
    def __init__(self, session):
        self.s = session

    async def call(self, tool_name, /, **args):
        if tool_name in OVERWRITE_TOOLS:       # gruppo B: i file di test_output vengono riscritti a ogni esecuzione
            args.setdefault("overwrite", True)
        r = await self.s.call_tool(tool_name, args)
        text = "".join(c.text for c in r.content if hasattr(c, "text"))
        ok = text.startswith("[SUCCESS]")
        data = {}
        if "Details: " in text:
            try:
                data = json.loads(text.split("Details: ", 1)[1])
            except Exception:
                data = {}
        return ok, text, data


def record(tool, ok, note=""):
    RESULTS.append((tool, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {tool}  {note}"[:210])


def rel(got, exp):
    return abs(got - exp) / abs(exp) if exp else abs(got)


class Part:
    """Helper per costruire un pezzo: ogni chiamata e' un tool MCP, esito registrato come PASS/FAIL."""

    def __init__(self, c, label):
        self.c, self.label = c, label

    async def t(self, tool, label=None, check=None, **args):
        ok, text, d = await self.c.call(tool, **args)
        good = ok and (check(d) if check else True)
        record(f"{self.label}: {label or tool}", good, (text.split('\n')[0] if ok else text)[:150])
        return d if ok else {}

    async def vol(self):
        ok, _, d = await self.c.call("get_mass_properties")
        return d.get("volume_mm3", 0.0) if ok else 0.0

    async def veq(self, label, exp, tol=TOL):
        v = await self.vol()
        record(f"{self.label}: volume {label}", rel(v, exp) < tol,
               f"misurato {v:.2f} mm3, atteso {exp:.2f} mm3, scarto {rel(v, exp) * 100:.4f} %")
        return v

    async def features(self):
        ok, _, d = await self.c.call("list_model_features")
        return [(f["name"], f["type"]) for f in d.get("features", []) if f["type"] not in ("RefPlane",)]

    async def types_include(self, expected):
        feats = await self.features()
        have = {}
        for _, t in feats:
            have[t] = have.get(t, 0) + 1
        ok = all(have.get(t, 0) >= n for t, n in expected.items())
        record(f"{self.label}: numero e tipo feature", ok, f"attese {expected}, presenti {have}")
        return feats

    async def drawing(self, tag, min_dims=1):
        """Salva il pezzo, crea un disegno A3, importa le quote del modello, esporta PNG e chiude il disegno."""
        path = OUT / f"{tag}.SLDPRT"
        drw = OUT / f"{tag}.SLDDRW"
        for p in (path, drw):
            if p.exists():
                p.unlink()
        await self.t("save_document", "salva pezzo", filepath=str(path))
        d = await self.t("create_drawing", "create_drawing", model_path=str(path), paper_size="A3",
                         save_as=str(drw), add_views=True)
        ok, text, d = await self.c.call("insert_model_dimensions", all_views=True)
        n = sum((d.get("added_per_view") or {}).values())
        record(f"{self.label}: disegno con quote del modello importate", ok and n >= min_dims,
               f"{n} quote importate dal modello")
        png = OUT / f"{tag}_disegno.png"
        await self.t("export_drawing", "esporta disegno PNG", filepath=str(png), format="png")
        await self.c.call("save_drawing", filepath=str(drw))
        await self.c.call("close_document", discard=True)


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


def cleanup(my_pid, elia_pids):
    if my_pid and my_pid in sw_pids():
        subprocess.run(["taskkill", "/PID", str(my_pid), "/F"], capture_output=True)
    import time
    time.sleep(3)
    left = sw_pids() - elia_pids
    print(f"Processi SolidWorks orfani dopo il test: {sorted(left)}; istanza utente intatta: {elia_pids <= sw_pids()}")


async def new_part(c):
    ok, text, _ = await c.call("create_new_part")
    assert ok, text


# ============================================================================================ scenario
async def scenario(c, tools):
    need = ["add_sketch_dimension", "add_sketch_relation", "revolve_boss", "loft", "sweep", "shell_body", "rib",
            "linear_pattern", "circular_pattern", "mirror_feature", "create_hole", "set_dimension_value"]
    record("tool di modellazione esposti", all(n in tools for n in need), f"{len(tools)} tool totali")

    await albero(c)
    await staffa(c)
    await flangia(c)
    await loft_sweep(c)
    await blocchi(c)
    await varie(c)


# ---------------------------------------------------------------------------------------- 1. albero
async def albero(c):
    print("\n== 1. Albero a gradini")
    P = Part(c, "albero")
    await new_part(c)
    d = await P.t("create_sketch", plane="Front")
    record("albero: piano Front = (u->Y, v->Z, normale X)", d.get("sketch_x_axis") == [0, 1, 0] and
           d.get("sketch_y_axis") == [0, 0, 1], f"assi {d.get('sketch_x_axis')} {d.get('sketch_y_axis')}")
    pts = [(0, 0), (0, 10), (40, 10), (40, 15), (100, 15), (100, 12.5), (130, 12.5), (130, 0), (0, 0)]
    ids = []
    for a, b in zip(pts[:-1], pts[1:]):
        r = await P.t("draw_line", "draw_line (id entita')", check=lambda d: bool(d.get("entity_id")),
                      x1=a[0], y1=a[1], x2=b[0], y2=b[1])
        ids.append(r.get("entity_id"))
    ax = await P.t("draw_centerline_axis", x1=-10, y1=0, x2=140, y2=0)
    for i, e in enumerate(ids[:-1]):
        await P.t("add_sketch_relation", f"relazione {'verticale' if i % 2 == 0 else 'orizzontale'}",
                  relation="vertical" if i % 2 == 0 else "horizontal", entity1=e)
    await P.t("add_sketch_relation", "relazione orizzontale (asse in basso)", relation="horizontal", entity1=ids[-1])
    await P.t("add_sketch_relation", "relazione coincidente (origine)", relation="coincident",
              entity1=ids[0] + ":start", entity2="origin")
    for e, v in zip(ids[:6], (10, 40, 5, 60, 2.5, 30)):
        await P.t("add_sketch_dimension", "quota (lunghezza)", kind="length", entity1=e, value=v)
    await P.t("add_sketch_relation", "relazione coincidente (asse - origine)", relation="coincident",
              entity1="origin", entity2=ax["entity_id"])
    await P.t("add_sketch_relation", "relazione orizzontale (asse di mezzeria)", relation="horizontal",
              entity1=ax["entity_id"])
    d = await P.t("get_sketch_definition_status", "schizzo completamente definito", sketch="Schizzo1",
                  check=lambda d: d.get("fully_defined") is True and not d.get("over_defined"))
    d = await P.t("revolve_boss", sketch="Schizzo1", angle=360)
    base = PI * (100 * 40 + 225 * 60 + 156.25 * 30)
    await P.veq("rivoluzione", base)
    await P.t("chamfer_edges", "chamfer_edges autonomo (spigoli per coordinate)", distance=1, angle=45,
              edge_points=[[10, 0, 0]])
    c1 = 2 * PI * (10 - 1 / 3) * 0.5
    await P.veq("dopo smusso 1", base - c1)
    await P.t("chamfer_at_points", "smusso 1,5", distance=1.5, edge_points=[[12.5, 130, 0]])
    c2 = 2 * PI * (12.5 - 0.5) * 0.5 * 2.25
    await P.veq("dopo smusso 2", base - c1 - c2)
    # cava per linguetta: piano a offset 15 dal piano superiore (normale Z), rettangolo 30x8, profondita' 4
    d = await P.t("create_reference_plane", "piano a offset", mode="offset", base="top", distance=15)
    pl = d.get("feature")
    await P.t("create_sketch", "schizzo sul piano di riferimento", plane=pl)
    await P.t("draw_rectangle", x1=55, y1=-4, x2=85, y2=4)
    await P.t("extrude_cut", "taglio estruso (cava)", depth=4)

    def seg(z, r=15.0):
        return 0.5 * (z * math.sqrt(r * r - z * z) + r * r * math.asin(z / r))
    key = 30 * ((seg(4) - seg(-4)) - 11 * 8)
    await P.veq("dopo cava linguetta", base - c1 - c2 - key)
    # foro filettato M8 in testa, cieco 16 (zona filettata a Ø nominale per 12,8 mm, poi Ø punta 6,8, punta 118)
    d = await P.t("create_hole", "foro filettato M8 cieco", kind="tapped", size="M8", positions=[[0, 130, 0]], depth=16)
    cone = (1 / 3) * PI * 3.4 ** 2 * (3.4 / math.tan(math.radians(59)))
    hole = PI * 16 * 12.8 + PI * 3.4 ** 2 * 3.2 + cone
    vtot = base - c1 - c2 - key - hole
    await P.veq("dopo foro filettato", vtot)
    await P.types_include({"Revolution": 1, "Chamfer": 2, "ICE": 1, "HoleWzd": 1})
    # modifica quota: D4 (tratto Ø30) 60 -> 70: il volume cresce di pi*15^2*10
    ok, text, d = await c.call("set_dimension_value", name="D4@Schizzo1", value=70)
    record("albero: modifica quota D4@Schizzo1 + ricostruzione", ok and rel(d["volume_mm3"] - d["volume_before_mm3"],
           PI * 225 * 10) < TOL, f"{d.get('volume_before_mm3')} -> {d.get('volume_mm3')}")
    await P.veq("dopo modifica D4", vtot + PI * 225 * 10)
    await P.t("rebuild_model", check=lambda d: not d.get("errors"))
    await P.t("export_model_image", "immagine (da guardare)", filepath=str(OUT / "albero.png"), view="isometric")
    await P.drawing("albero", min_dims=3)


# ----------------------------------------------------------------------------------------- 2. staffa
async def staffa(c):
    print("\n== 2. Staffa a L")
    P = Part(c, "staffa")
    await new_part(c)
    await P.t("create_sketch", plane="Front")
    pts = [(0, 0), (60, 0), (60, 6), (6, 6), (6, 40), (0, 40), (0, 0)]
    for a, b in zip(pts[:-1], pts[1:]):
        await P.t("draw_line", x1=a[0], y1=a[1], x2=b[0], y2=b[1])
    await P.t("extrude_boss", "estrusione 50 (profilo L)", depth=50)
    await P.veq("profilo L", 564 * 50)
    d = await P.t("create_reference_plane", "piano di mezzeria", mode="offset", base="front", distance=25)
    await P.t("create_sketch", plane=d.get("feature"))
    await P.t("draw_line", x1=36, y1=6, x2=6, y2=36)
    await P.t("rib", "nervatura 5 mm", thickness=5)
    await P.veq("con nervatura", 564 * 50 + 450 * 5)
    d = await P.t("create_hole", "foro lamato M4 passante", kind="counterbore", size="M4",
                  positions=[[12.5, 24, 6]], through=True)
    hole = d["features"][0]
    dims = d["dimensions_mm"][0]
    one = PI * (dims["ThruHoleDiameter"] / 2) ** 2 * (6 - dims["CounterBoreDepth"]) + \
        PI * (dims["CounterBoreDiameter"] / 2) ** 2 * dims["CounterBoreDepth"]
    await P.veq("con 1 foro lamato", 564 * 50 + 2250 - one, tol=TOL)
    await P.t("linear_pattern", "ripetizione lineare 2x2 (2 direzioni)", features=[hole],
              direction1={"edge": [0, 30, 6]}, count1=2, spacing1=24,
              direction2={"edge": [10, 60, 6]}, count2=2, spacing2=25)
    await P.veq("con 4 fori lamati", 564 * 50 + 2250 - 4 * one)
    await P.t("fillet_edges", "fillet_edges autonomo R10 spigolo esterno", radius=10, edge_points=[[25, 0, 0]])
    fil = 100 * (1 - PI / 4) * 50
    await P.veq("dopo raccordo", 564 * 50 + 2250 - 4 * one - fil)
    ok, text, d = await c.call("set_dimension_value", name="D1@Estrusione-Estrusione1", value=60)
    # larghezza 50 -> 60: profilo L (564) meno il raccordo, per 10 mm in piu'
    exp = 564 * 60 + 2250 - 4 * one - 100 * (1 - PI / 4) * 60
    record("staffa: modifica quota larghezza 50->60 + ricostruzione", ok and rel(d["volume_mm3"], exp) < TOL,
           f"{d.get('volume_before_mm3')} -> {d.get('volume_mm3')} atteso {exp:.1f}")
    await P.t("mirror_feature", "specchiatura del corpo rispetto alla faccia", plane={"face": [60, 30, 3]},
              mirror_body=True)
    await P.veq("dopo specchiatura corpo (doppio)", 2 * exp)
    await P.types_include({"Extrusion": 1, "Rib": 1, "HoleWzd": 1, "LPattern": 1, "Fillet": 1})
    await P.t("export_model_image", "immagine (da guardare)", filepath=str(OUT / "staffa.png"), view="isometric")
    await P.drawing("staffa", min_dims=1)


# ---------------------------------------------------------------------------------------- 3. flangia
async def flangia(c):
    print("\n== 3. Flangia")
    P = Part(c, "flangia")
    await new_part(c)
    await P.t("create_sketch", plane="Front")
    r = await P.t("draw_circle", x=0, y=0, radius=50, check=lambda d: bool(d.get("entity_id")))
    d = await P.t("add_sketch_dimension", "quota diametro", kind="diameter", entity1=r["entity_id"], value=100)
    await P.t("get_sketch_definition_status", "schizzo completamente definito",
              check=lambda d: d.get("fully_defined") is True, sketch="Schizzo1")
    await P.t("extrude_boss", "disco 12 mm", depth=12)
    await P.veq("disco", PI * 2500 * 12)
    await P.t("create_sketch_on_face", x=12, y=0, z=40)
    await P.t("draw_circle", x=0, y=0, radius=25)
    await P.t("extrude_boss", "mozzo con sformo 3 gradi", depth=15, draft_angle=3)
    r1, r2 = 25.0, 25 - 15 * math.tan(math.radians(3))
    hub = PI * 15 / 3 * (r1 * r1 + r1 * r2 + r2 * r2)
    await P.veq("con mozzo sformato", PI * 2500 * 12 + hub)
    await P.t("create_sketch_on_face", x=27, y=0, z=0)
    await P.t("draw_circle", x=0, y=0, radius=15)
    await P.t("extrude_cut", "foro centrale passante (through_all)", end_condition="through_all")
    await P.t("create_sketch_on_face", x=12, y=40, z=0)
    await P.t("draw_circle", x=35, y=0, radius=4.5)
    d = await P.t("extrude_cut", "foro Ø9 su PCD 70", end_condition="through_all")
    hole = d.get("feature")
    await P.t("circular_pattern", "ripetizione circolare 6 fori", features=[hole],
              axis={"face": [13.5, 0, -15]}, count=6)
    exp = PI * 2500 * 12 + hub - PI * 225 * 27 - 6 * PI * 4.5 ** 2 * 12
    await P.veq("flangia con 6 fori", exp)
    await P.types_include({"Extrusion": 1, "ICE": 3, "CirPattern": 1})
    ok, text, d = await c.call("set_dimension_value", name="D1@Schizzo1", value=110)
    e2 = exp + PI / 4 * (110 ** 2 - 100 ** 2) * 12
    record("flangia: modifica quota Ø100->110 + ricostruzione", ok and rel(d["volume_mm3"], e2) < TOL,
           f"{d.get('volume_before_mm3')} -> {d.get('volume_mm3')} atteso {e2:.1f}")
    await P.t("export_model_image", "immagine (da guardare)", filepath=str(OUT / "flangia.png"), view="isometric")
    await P.drawing("flangia", min_dims=1)


# ----------------------------------------------------------------------------------- 4. loft e sweep
async def loft_sweep(c):
    print("\n== 4. Loft e sweep")
    P = Part(c, "loft")
    await new_part(c)
    await P.t("create_sketch", plane="Front")
    await P.t("draw_circle", x=0, y=0, radius=20)
    await c.call("close_sketch")
    d = await P.t("create_reference_plane", "piano a offset 30", mode="offset", base="front", distance=30)
    await P.t("create_sketch", plane=d["feature"])
    await P.t("draw_circle", x=0, y=0, radius=10)
    await c.call("close_sketch")
    await P.t("loft", "loft fra due cerchi", profile_sketches=["Schizzo1", "Schizzo2"])
    await P.veq("tronco di cono", PI * 30 / 3 * (400 + 200 + 100))
    await P.t("export_model_image", "immagine (da guardare)", filepath=str(OUT / "loft.png"), view="isometric")

    P = Part(c, "sweep")
    await new_part(c)
    await P.t("create_sketch", plane="Front")
    await P.t("draw_line", x1=0, y1=0, x2=40, y2=0)
    k = 20 * math.sin(math.pi / 4)
    await P.t("draw_arc_3point", x1=40, y1=0, x2=40 + k, y2=20 - 20 * math.cos(math.pi / 4), x3=60, y3=20)
    await P.t("draw_line", x1=60, y1=20, x2=60, y2=50)
    await c.call("close_sketch")
    await P.t("create_sketch", plane="right")
    await P.t("draw_circle", x=0, y=0, radius=5)
    await c.call("close_sketch")
    await P.t("sweep", "sweep profilo circolare lungo percorso", profile_sketch="Schizzo2", path_sketch="Schizzo1")
    await P.veq("tubo (Pappus)", PI * 25 * (40 + PI / 2 * 20 + 30))
    await P.t("export_model_image", "immagine (da guardare)", filepath=str(OUT / "sweep.png"), view="isometric")


# ------------------------------------------------------------------------------------ 5. sformo/shell
async def blocchi(c):
    print("\n== 5. Sformo e shell su blocchi")
    P = Part(c, "sformo")
    await new_part(c)
    await P.t("create_sketch", plane="Front")
    await P.t("draw_rectangle", x1=0, y1=0, x2=40, y2=30)
    await P.t("extrude_boss", depth=20)
    await P.t("draft_faces", "sformo 5 gradi su 4 facce", angle=5,
              faces=[[10, 0, 15], [10, 40, 15], [10, 20, 0], [10, 20, 30]], neutral_face_point=[0, 20, 15])
    t = math.tan(math.radians(5)) * 20
    wide = 20 / 6 * (1200 + 4 * (40 + t) * (30 + t) + (40 + 2 * t) * (30 + 2 * t))
    await P.veq("blocco sformato (prismatoide)", wide)

    P = Part(c, "shell")
    await new_part(c)
    await P.t("create_sketch", plane="Front")
    await P.t("draw_rectangle", x1=0, y1=0, x2=40, y2=30)
    await P.t("extrude_boss", depth=20)
    await P.t("shell_body", "shell 2 mm, faccia superiore rimossa", thickness=2, remove_faces=[[20, 20, 15]])
    await P.veq("guscio", 24000 - 36 * 26 * 18)


# -------------------------------------------------------------------------------------- 6. varie
async def varie(c):
    print("\n== 6. Schizzi vari, condizioni finali, riferimenti, gestione feature")
    P = Part(c, "varie")
    await new_part(c)
    await P.t("create_sketch", plane="Front")
    await P.t("draw_construction_line", x1=0, y1=0, x2=50, y2=0)
    await P.t("draw_point", x=5, y=5)
    await P.t("draw_spline", points=[[0, 20], [10, 25], [20, 22], [30, 30]])
    await P.t("draw_ellipse", cx=30, cy=40, semi_major=10, semi_minor=5)
    await P.t("draw_slot", x1=10, y1=45, x2=25, y2=45, width=6)
    await P.t("add_sketch_text", text="AB", x=40, y=10, height=5)
    a = await P.t("draw_line", x1=60, y1=0, x2=60, y2=20)
    b = await P.t("draw_line", x1=60, y1=20, x2=80, y2=20)
    await P.t("sketch_fillet", radius=4, entity1=a["entity_id"], entity2=b["entity_id"])
    await P.t("offset_entities", entities=["@60,10"], offset=3)
    await P.t("mirror_sketch_entities", entities=["@80,20"], axis="@25,0")
    await P.t("get_sketch_definition_status", "schizzo sottodefinito", check=lambda d: d.get("status") == "sottodefinito")
    await c.call("close_sketch")
    # schizzo sovradefinito
    await P.t("create_sketch", plane="Front")
    l = await P.t("draw_line", x1=0, y1=0, x2=30, y2=10)
    await P.t("add_sketch_relation", relation="horizontal", entity1=l["entity_id"])
    await P.t("add_sketch_relation", relation="vertical", entity1=l["entity_id"])
    await P.t("get_sketch_definition_status", "schizzo sovradefinito", check=lambda d: d.get("over_defined") is True)
    await c.call("close_sketch")

    P = Part(c, "condizioni")
    await new_part(c)
    await P.t("create_sketch", plane="Front")
    await P.t("draw_rectangle", x1=-20, y1=-15, x2=20, y2=15)
    await P.t("extrude_boss", "estrusione piano medio", depth=20, end_condition="mid_plane")
    await P.veq("piano medio", 24000)
    d = await P.t("set_material", material="AISI 1020")
    ok, _, m = await c.call("get_mass_properties")
    record("condizioni: massa = volume x densita'", ok and rel(m["mass_kg"], 24000e-9 * d["density_kg_m3"]) < TOL,
           f"{m.get('mass_kg')} kg")
    await P.t("create_sketch_on_face", x=10, y=0, z=0)
    await P.t("draw_circle", x=0, y=0, radius=5)
    await P.t("extrude_cut", "taglio through_all_both", end_condition="through_all_both")
    await P.veq("dopo taglio passante", 24000 - PI * 25 * 20)
    d = await P.t("create_hole", "foro semplice M6 passante", kind="simple", size="M6", positions=[[10, 10, 5]], through=True)
    d = await P.t("create_hole", "foro svasato M6", kind="countersink", size="M6", positions=[[10, -10, -5]], depth=8)
    await P.t("create_reference_axis", "asse da faccia cilindrica", mode="cylinder", face_point=[0, 0, 5])
    await P.t("create_reference_point", "punto al centro faccia", mode="face_center", face_point=[10, -14, 14])
    v0 = await P.vol()
    feats = await P.features()
    hole = [n for n, t in feats if t == "HoleWzd"][0]
    ok, _, d = await c.call("suppress_feature", name=hole)
    record("condizioni: sopprimi feature (volume aumenta)", ok and d["volume_delta_mm3"] > 0, str(d.get("volume_delta_mm3")))
    ok, _, d = await c.call("unsuppress_feature", name=hole)
    record("condizioni: riattiva feature (volume torna)", ok and abs(rel(d["volume_mm3"], v0 / 1.0) ) < 1e-6, str(d.get("volume_mm3")))
    ok, _, d = await c.call("rename_feature", name=hole, new_name="ForoPrincipale")
    record("condizioni: rinomina feature", ok and d.get("new_name") == "ForoPrincipale")
    ok, _, d = await c.call("rollback_to_feature", name="ForoPrincipale", position="before")
    record("condizioni: rollback prima della feature", ok and d["volume_mm3"] > v0, str(d.get("volume_mm3")))
    ok, _, d = await c.call("rollback_to_feature", position="end")
    record("condizioni: rollback alla fine", ok and rel(d["volume_mm3"], v0) < 1e-6)
    ok, _, d = await c.call("delete_feature", name="ForoPrincipale", confirm=True)
    record("condizioni: elimina feature", ok and d["volume_delta_mm3"] > 0)
    ok, _, d = await c.call("rebuild_model", force=True)
    record("condizioni: ricostruisci", ok)
    ok, _, d = await c.call("select_at_point", kind="face", x=10, y=-10, z=14)
    record("condizioni: select_at_point (faccia)", ok, str(d.get("area_mm2")))
    ok, _, d = await c.call("list_entities", kind="face")
    record("condizioni: list_entities", ok and d.get("count", 0) > 5, f"{d.get('count')} facce")


if __name__ == "__main__":
    done = asyncio.run(run())
    print("\n==== RIEPILOGO ====")
    for tool, res, note in RESULTS:
        print(f"{res:5} {tool:62} {note}"[:200])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
