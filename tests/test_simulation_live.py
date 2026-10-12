"""
Test live dei tool di SIMULAZIONE (blocco 5) tramite il server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente non viene toccata;
alla fine si chiude solo il PID lanciato dal test. Costruisce tutto SOLO tramite tool MCP:
  1. TRAVE A SBALZO in acciaio (AISI 1020, E letto dal materiale), 200 x 20 x 10 mm, incastro a x=0, 100 N trasversali (asse z, lato 10 mm)
     all'altra estremita': delta = F L^3 / (3 E I) (+-10 %), sigma = M c / I a meta' trave sulla faccia superiore (+-10 %, lontano
     dall'incastro) e massimo nodale vs 60 MPa all'incastro (+-15 %: li' c'e' una singolarita' per il vincolo che impedisce la
     contrazione di Poisson); convergenza di delta raffinando la mesh (3 dimensioni) e con la mesh basata sulla curvatura;
  2. altri carichi sulla stessa trave: forza normale, pressione (reazione = p*A), gravita' (reazione = m*g), vincolo rullo/simmetria (immovable e' solo per gusci/travi: errore 15 sui solidi);
  3. PIASTRA CON FORO in trazione: fattore di concentrazione Kt = sigma_max / sigma_netta vs formula di Peterson (e banda 2,2-3);
  4. IMMAGINI dei risultati (von Mises, spostamento): PNG con la mappa a colori (verificata contando i pixel colorati);
  5. ASSIEME di due blocchi con contatto globale incollato: spostamento come la trave monolitica.

Uso:  .venv\\Scripts\\python.exe tests\\test_simulation_live.py       Output: test_output\\ (file sim_*)
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
sys.path.insert(0, str(ROOT))
OUT = ROOT / "test_output"
OUT.mkdir(exist_ok=True)
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
SERVER = ROOT / "solidworks_mcp_server.py"

OVERWRITE_TOOLS = {"save_document", "save_drawing", "export_drawing", "export_model", "export_model_image", "export_simulation_plot", "create_drawing"}
RESULTS = []

# trave: X 0..200, Y +-10, Z +-5 (estrusione dal Piano frontale, normale X)
L, BW, H = 200.0, 20.0, 10.0
FORCE = 100.0
I_BEAM = BW * H ** 3 / 12.0          # 1666.67 mm4 (flessione attorno a y, carico lungo z)


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


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:260])


async def T(c, tool, label=None, check=None, expect_fail=False, **args):
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
    record(f"{tool}: {label}" if label else tool, good, text.split("\n")[0][:190])
    return d if (ok or expect_fail) else {}


def F(name, ext="SLDPRT"):
    return str(OUT / f"{name}.{ext}")


def rm(*paths):
    for n in paths:
        p = Path(n)
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass


def rel(a, b):
    return abs(a - b) / abs(b) if b else abs(a)


def color_stats(path):
    """Pixel colorati (saturazione alta) e quanti rossi / blu: serve a dire che c'e' una mappa a colori sul pezzo."""
    from solidworks_mcp.automation.data_export import _read_png
    w, h, bpp, rows = _read_png(str(path))
    sat = red = blue = 0
    for y in range(0, h, 2):
        r = rows[y]
        for x in range(0, w, 2):
            R, G, B = r[x * bpp], r[x * bpp + 1], r[x * bpp + 2]
            mx, mn = max(R, G, B), min(R, G, B)
            if mx - mn > 120:
                sat += 1
                if R > 200 and G < 120 and B < 120:
                    red += 1
                if B > 200 and R < 80 and G < 120:
                    blue += 1
    return {"size": (w, h), "saturated": sat, "red": red, "blue": blue}


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


def cleanup(my_pid, elia_pids):
    import time
    if my_pid and my_pid in sw_pids():
        subprocess.run(["taskkill", "/PID", str(my_pid), "/F"], capture_output=True)
    time.sleep(3)
    left = sw_pids() - elia_pids
    print(f"Processi SolidWorks orfani dopo il test: {sorted(left)}; istanza utente intatta: {elia_pids <= sw_pids()}")


async def delete_loads(c, keep_restraints=True):
    d = (await c.call("list_simulation_loads"))[2]
    for it in d.get("items", []):
        if it["type"] == "vincolo" and keep_restraints:
            continue
        await c.call("delete_simulation_load", name=it["name"])


# ============================================================================================ scenario
async def scenario(c: Client, tools):
    from solidworks_mcp.simulation_tools import SIMULATION_DISPATCH
    missing = [t for t in SIMULATION_DISPATCH if t not in tools]
    record("tutti i tool del blocco 5 esposti dal server", not missing, f"{len(SIMULATION_DISPATCH)} tool, mancanti {missing}")
    record("nessun nome di tool duplicato", len(tools) == len(set(tools)), f"{len(tools)} tool")

    d = await T(c, "simulation_status", "add-in disponibile", check=lambda d: d["available"])
    print("  versione Simulation:", d.get("simulation_version_number"))

    # ------------------------------------------------------------------ 1. trave a sbalzo
    print("\n== 1. Trave a sbalzo 200x20x10 in acciaio")
    part = F("sim_trave")
    rm(part)
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-BW / 2, y1=-H / 2, x2=BW / 2, y2=H / 2)
    await T(c, "extrude_boss", "trave lunga 200", depth=L)
    await T(c, "assign_material", "AISI 1020", material="AISI 1020")
    d = await T(c, "list_materials", "E del materiale", query="AISI 1020", include_properties=True,
                check=lambda d: d["materials"][0]["name"] == "AISI 1020")
    lib_E = d["materials"][0]["properties"]["elastic_modulus_Pa"] / 1e6 if d.get("materials") else 200000.0
    lib_sy = d["materials"][0]["properties"]["yield_strength_Pa"] / 1e6 if d.get("materials") else 0
    E_th = lib_E
    delta_th = FORCE * L ** 3 / (3 * E_th * I_BEAM)
    sigma_mid_th = FORCE * (L - 100.0) * (H / 2) / I_BEAM          # a x = 100, superficie superiore
    sigma_root_th = FORCE * L * (H / 2) / I_BEAM
    print(f"  E libreria {lib_E:.0f} MPa, I {I_BEAM:.2f} mm4 -> delta teorico {delta_th:.5f} mm, sigma meta' {sigma_mid_th:.2f} MPa, incastro {sigma_root_th:.2f} MPa")
    await T(c, "save_document", "salva trave", filepath=part)

    await T(c, "create_static_study", "studio statico", name="Flessione", check=lambda d: d["name"] == "Flessione")
    await T(c, "create_static_study", "nome duplicato rifiutato", name="Flessione", expect_fail=True)
    await T(c, "list_simulation_studies", "elenco", check=lambda d: [s["name"] for s in d["studies"]] == ["Flessione"])
    d = await T(c, "set_study_material", "materiale preso dal pezzo",
                check=lambda d: d["bodies"][0]["name"] == "AISI 1020" and rel(d["bodies"][0]["E_MPa"], lib_E) < 1e-3)
    d = await T(c, "set_study_material", "assegnato: AISI 304", material="AISI 304",
                check=lambda d: d["bodies"][0]["name"] == "AISI 304" and abs(d["bodies"][0]["E_MPa"] - 190000) < 100)
    d = await T(c, "set_study_material", "ripristinato AISI 1020", material="AISI 1020",
                check=lambda d: rel(d["bodies"][0]["E_MPa"], lib_E) < 1e-3)

    await T(c, "add_restraint", "fisso su x=0", kind="fixed", faces=[[0, 0, 0]])
    await T(c, "add_restraint", "faccia inesistente", kind="fixed", faces=[[50, 50, 50]], expect_fail=True)
    await T(c, "add_restraint", "tipo sconosciuto", kind="boh", faces=[[0, 0, 0]], expect_fail=True)
    await T(c, "add_force", "100 N lungo -Z su x=200", faces=[[L, 0, 0]], value=FORCE, mode="direction", direction=[0, 0, -1])
    await T(c, "list_simulation_loads", "vincolo + forza", check=lambda d: sorted(i["type"] for i in d["items"]) == ["forza", "vincolo"])

    await T(c, "run_simulation", "senza mesh rifiutata", expect_fail=True)
    deltas = {}
    for size in (8.0, 4.0, 2.5):
        d = await T(c, "create_simulation_mesh", f"standard {size} mm", element_size=size, mesher="standard",
                    check=lambda d: d["nodes"] > 100 and d["elements"] > 50 and d["quality_ok"])
        print(f"    mesh: {d.get('nodes')} nodi, {d.get('elements')} elementi, AR max {d.get('max_aspect_ratio')}, "
              f"AR medio {d.get('aspect_ratio', {}).get('mean')}, jacobiano {d.get('worst_jacobian_ratio')}")
        await T(c, "run_simulation", f"mesh {size}", timeout=300, check=lambda d: d["steps"] >= 1)
        r = await T(c, "get_simulation_results", f"mesh {size}")
        if r:
            deltas[size] = r["displacement_mm"]["max"]
            print(f"    delta {deltas[size]:.5f} mm (teorico {delta_th:.5f}), VM nodale max {r['von_mises_nodal_MPa']['max']:.2f} MPa "
                  f"in {r['von_mises_nodal_MPa']['max_at_mm']}, FOS min {r['factor_of_safety'].get('min')}")
            last = r
    errs = {s: rel(v, delta_th) for s, v in deltas.items()}
    record("SPOSTAMENTO: mesh finissima entro +-10 % di F L^3/(3 E I)", errs.get(2.5, 1) < 0.10,
           f"{deltas.get(2.5):.5f} vs {delta_th:.5f} mm ({errs.get(2.5, 1) * 100:.2f} %)")
    record("SPOSTAMENTO: tutte le mesh entro +-10 %", all(e < 0.10 for e in errs.values()),
           ", ".join(f"{s}: {e * 100:.2f} %" for s, e in errs.items()))
    record("CONVERGENZA: l'errore diminuisce raffinando (8 -> 4 -> 2,5 mm)",
           errs.get(8.0, 0) > errs.get(4.0, 0) > errs.get(2.5, 0) or (errs.get(2.5, 1) < errs.get(8.0, 0)),
           f"errori {errs}")
    record("CONVERGENZA: delta cresce monotono verso il teorico (da sotto: la FEM e' piu' rigida, il vincolo impedisce la contrazione di Poisson)",
           deltas.get(8.0, 0) <= deltas.get(4.0, 0) <= deltas.get(2.5, 0) <= delta_th * 1.001, f"{deltas}")
    r = last
    record("REAZIONE vincolare = 100 N (+Z)", abs(r["reaction_force_N"]["z"] - FORCE) < 0.5 and abs(r["reaction_force_N"]["x"]) < 0.5,
           str(r["reaction_force_N"]))
    record("SPOSTAMENTO: verso -Z (direzione della forza)", r["displacement_components_mm"]["uz"]["min"] < -0.9 * delta_th and
           abs(r["displacement_components_mm"]["uy"]["max"]) < 0.05 * delta_th, str(r["displacement_components_mm"]["uz"]))
    vm = r["von_mises_nodal_MPa"]
    record("TENSIONE all'incastro: massimo nodale entro +-15 % di M c / I (singolarita' del vincolo)",
           rel(vm["max"], sigma_root_th) < 0.15, f"{vm['max']:.2f} vs {sigma_root_th:.2f} MPa ({rel(vm['max'], sigma_root_th) * 100:.1f} %), "
                                                  f"a {vm['max_at_mm']} mm (vicino all'incastro x=0)")
    record("TENSIONE: il massimo e' vicino all'incastro (x < 15 mm)", vm["max_at_mm"][0] < 15, str(vm["max_at_mm"]))
    d = await T(c, "get_simulation_stress_on_faces", "meta' trave, faccia superiore, x 95..105", faces=[[100, 0, H / 2]],
                box=[95, -BW / 2, H / 2, 105, BW / 2, H / 2], check=lambda d: d["nodes"] > 5)
    if d:
        record("TENSIONE a meta' trave (lontano dall'incastro): entro +-10 % di M c / I",
               rel(d["mean_MPa"], sigma_mid_th) < 0.10 and rel(d["max_MPa"], sigma_mid_th) < 0.15,
               f"media {d['mean_MPa']:.2f} max {d['max_MPa']:.2f} vs {sigma_mid_th:.2f} MPa ({rel(d['mean_MPa'], sigma_mid_th) * 100:.1f} %)")
    fos_th = lib_sy / r["von_mises_nodal_MPa"]["max"]
    record("FATTORE DI SICUREZZA minimo = snervamento / VM max (+-10 %)", rel(r["factor_of_safety"]["min"], fos_th) < 0.10,
           f"{r['factor_of_safety']['min']:.2f} vs {fos_th:.2f} (snervamento {lib_sy:.1f} MPa)")

    # mesh basata sulla curvatura
    d = await T(c, "create_simulation_mesh", "basata sulla curvatura", element_size=4.0, mesher="curvature",
                check=lambda d: d["nodes"] > 100 and d["mesher"] == "curvature")
    await T(c, "run_simulation", "mesh curvatura")
    rc = await T(c, "get_simulation_results", "mesh curvatura")
    if rc:
        record("SPOSTAMENTO con mesh a curvatura entro +-10 %", rel(rc["displacement_mm"]["max"], delta_th) < 0.10,
               f"{rc['displacement_mm']['max']:.5f} vs {delta_th:.5f} mm")
    await T(c, "create_simulation_mesh", "mesher non valido", mesher="boh", expect_fail=True)

    # ------------------------------------------------------------------ immagini
    print("\n== 2. Immagini dei risultati")
    imgs = {}
    for res_name in ("von_mises", "displacement"):
        p = F(f"sim_trave_{res_name}", "png")
        rm(p)
        d = await T(c, "export_simulation_plot", res_name, filepath=p, result=res_name, check=lambda d: d["bytes"] > 50000)
        if Path(p).exists():
            imgs[res_name] = color_stats(p)
            print("   ", res_name, imgs[res_name])
            record(f"IMMAGINE {res_name}: mappa a colori sul pezzo (pixel saturati, rossi e blu)",
                   imgs[res_name]["saturated"] > 3000 and imgs[res_name]["red"] > 20 and imgs[res_name]["blue"] > 200,
                   str(imgs[res_name]))
    await T(c, "export_simulation_plot", "grafico inesistente", filepath=F("sim_x", "png"), result="boh", expect_fail=True)

    # ------------------------------------------------------------------ altri carichi
    print("\n== 3. Altri carichi sulla stessa trave (mesh 4 mm)")
    await T(c, "create_simulation_mesh", "mesh 4 mm", element_size=4.0, mesher="standard")
    await delete_loads(c)
    await T(c, "add_force", "forza normale 100 N su x=200", faces=[[L, 0, 0]], value=FORCE, mode="normal")
    await T(c, "run_simulation", "forza normale")
    r = await T(c, "get_simulation_results", "forza normale")
    if r:
        dx = r["displacement_components_mm"]["ux"]["min"]
        record("FORZA NORMALE: compressione assiale (reazione +X = 100 N, spostamento ux = -F L / (E A))",
               abs(r["reaction_force_N"]["x"] - FORCE) < 0.5 and rel(abs(dx), FORCE * L / (E_th * BW * H)) < 0.05,
               f"reazione {r['reaction_force_N']}, ux {dx:.6f} vs {-FORCE * L / (E_th * BW * H):.6f} mm")
    await delete_loads(c)
    await T(c, "add_pressure", "1 MPa su x=200", faces=[[L, 0, 0]], value=1.0)
    await T(c, "run_simulation", "pressione")
    r = await T(c, "get_simulation_results", "pressione")
    if r:
        record("PRESSIONE: reazione = p * A = 1 MPa * 200 mm2 = 200 N", abs(r["reaction_force_N"]["x"] - 200.0) < 1.0,
               str(r["reaction_force_N"]))
    await delete_loads(c)
    await T(c, "add_gravity", "9,80665 m/s2 lungo -Z", direction=[0, 0, -1])
    await T(c, "run_simulation", "gravita'")
    r = await T(c, "get_simulation_results", "gravita'")
    if r:
        dens = 7900.0
        weight = L * BW * H * 1e-9 * dens * 9.80665
        record("GRAVITA': reazione = m g (peso della trave)", abs(r["reaction_force_N"]["z"] - weight) / weight < 0.01,
               f"{r['reaction_force_N']['z']:.4f} vs {weight:.4f} N")
    await delete_loads(c, keep_restraints=False)
    await T(c, "list_simulation_loads", "tutto eliminato", check=lambda d: len(d["items"]) == 0)
    await T(c, "add_restraint", "simmetria su x=0", kind="symmetry", faces=[[0, 0, 0]])
    await T(c, "add_restraint", "rullo/scorrevole su faccia piana", kind="roller", faces=[[L, 0, 0]])
    await T(c, "list_simulation_loads", "due vincoli", check=lambda d: len(d["items"]) == 2)
    await T(c, "create_static_study", "secondo studio", name="Studio B")
    await T(c, "delete_simulation_study", "elimina Studio B", name="Studio B")
    await T(c, "delete_simulation_study", "studio inesistente", name="Boh", expect_fail=True)
    await T(c, "list_simulation_studies", "resta solo Flessione", check=lambda d: [s["name"] for s in d["studies"]] == ["Flessione"])
    await T(c, "save_document", "salva trave", filepath=part)

    # ------------------------------------------------------------------ piastra con foro
    print("\n== 4. Piastra con foro in trazione")
    PW, PT, PL, DH = 40.0, 5.0, 100.0, 4.0     # larghezza, spessore, lunghezza, foro
    plate = F("sim_piastra")
    rm(plate)
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-PW / 2, y1=-PL / 2, x2=PW / 2, y2=PL / 2)
    await c.call("draw_circle", x=0, y=0, radius=DH / 2)
    d = await T(c, "extrude_boss", "piastra spessore 5", depth=PT)
    await T(c, "assign_material", "AISI 1020", material="AISI 1020")
    ok, _, mp = await c.call("get_mass_properties")
    v_th = (PW * PL - math.pi * (DH / 2) ** 2) * PT
    record("piastra: volume = (b h - pi r^2) t (foro passante)", ok and rel(mp.get("volume_mm3", 0), v_th) < 1e-4,
           f"{mp.get('volume_mm3')} vs {v_th:.2f}")
    await T(c, "save_document", "salva piastra", filepath=plate)
    await T(c, "create_static_study", "trazione", name="Trazione")
    # piastra: Y +-20 (larghezza), Z +-50 (lunghezza, direzione del carico), X 0..5 (spessore)
    await T(c, "add_restraint", "fisso su z=-50", kind="fixed", faces=[[PT / 2, 0, -PL / 2]])
    FT = 2000.0
    await T(c, "add_force", "2000 N lungo +Z su z=+50", faces=[[PT / 2, 0, PL / 2]], value=FT, mode="direction", direction=[0, 0, 1])
    sig_net = FT / ((PW - DH) * PT)
    lam = DH / PW
    kt_peterson = 3.0 - 3.14 * lam + 3.667 * lam ** 2 - 1.527 * lam ** 3
    print(f"  sigma netta {sig_net:.2f} MPa, lambda {lam:.3f}, Kt (Peterson, su sezione netta) {kt_peterson:.3f}")
    kts = {}
    for size, mn in ((3.0, 0.5), (2.0, 0.25)):
        d = await T(c, "create_simulation_mesh", f"curvatura max {size} min {mn}", element_size=size, mesher="curvature",
                    min_element_size=mn, min_elements_in_circle=16, check=lambda d: d["nodes"] > 500)
        await T(c, "run_simulation", f"piastra {size}", timeout=300)
        r = await T(c, "get_simulation_results", f"piastra {size}")
        dh = await T(c, "get_simulation_stress_on_faces", "nodi sulla superficie del foro", faces=[[PT / 2, 0, DH / 2]],
                     check=lambda d: d["nodes"] > 20)
        if dh:
            kts[size] = dh["max_MPa"] / sig_net
            print(f"    mesh {d.get('nodes')} nodi: VM max sul foro {dh['max_MPa']:.2f} MPa -> Kt {kts[size]:.3f}, "
                  f"punto {dh['max_at_mm']}, reazione {r['reaction_force_N']}")
    kt = kts.get(2.0)
    record("PIASTRA: reazione = 2000 N", abs(r["reaction_force_N"]["z"] + FT) < 2.0 or abs(abs(r["reaction_force_N"]["z"]) - FT) < 2.0,
           str(r["reaction_force_N"]))
    record("PIASTRA: Kt plausibile 2,2-3 (foro piccolo)", kt is not None and 2.2 <= kt <= 3.0, f"Kt = {kt}")
    record("PIASTRA: Kt entro 10 % della formula di Peterson", kt is not None and rel(kt, kt_peterson) < 0.10,
           f"{kt} vs {kt_peterson:.3f}")
    record("PIASTRA: raffinando la mesh Kt si avvicina a Peterson", len(kts) == 2 and rel(kts[2.0], kt_peterson) <= rel(kts[3.0], kt_peterson) + 0.01,
           str(kts))
    p = F("sim_piastra_von_mises", "png")
    rm(p)
    await T(c, "export_simulation_plot", "piastra von Mises", filepath=p, result="von_mises", view="front", check=lambda d: d["bytes"] > 50000)
    if Path(p).exists():
        cs = color_stats(p)
        record("IMMAGINE piastra: mappa a colori", cs["saturated"] > 3000 and cs["red"] > 20, str(cs))
    await T(c, "save_document", "salva piastra", filepath=plate)

    # ------------------------------------------------------------------ assieme
    print("\n== 5. Assieme: due blocchi con contatto globale incollato")
    await assembly_scenario(c, delta_th, E_th)
    print("\n== 6. Albero cilindrico in torsione")
    await torque_scenario(c, E_th)


async def torque_scenario(c: Client, E_th):
    """Albero r=10, lungo 100, incastrato a x=0, 10 N*m sull'estremita': theta = T L / (G J), spostamento della superficie = theta r."""
    await c.call("close_document", discard=True)
    shaft = F("sim_albero")
    rm(shaft)
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=10)
    await c.call("extrude_boss", depth=100)
    await c.call("assign_material", material="AISI 1020")
    await T(c, "save_document", "salva albero", filepath=shaft)
    await T(c, "create_static_study", "studio torsione", name="Torsione")
    await T(c, "add_restraint", "fisso su x=0", kind="fixed", faces=[[0, 0, 0]])
    await T(c, "add_torque", "asse = faccia cilindrica", faces=[[100, 0, 0]], value=10.0, axis_face=[50, 10, 0])
    await T(c, "add_torque", "riferimento non cilindrico rifiutato", faces=[[100, 0, 0]], value=10.0, axis_face=[100, 0, 0], expect_fail=True)
    await T(c, "create_simulation_mesh", "mesh 3 mm", element_size=3.0)
    await T(c, "run_simulation", "torsione")
    r = await T(c, "get_simulation_results", "torsione")
    if r:
        G = E_th / (2 * 1.29)
        u_th = 10000.0 * 100.0 / (G * math.pi * 10 ** 4 / 2) * 10.0
        u = r["displacement_mm"]["max"]
        tau_th = 10000.0 * 10.0 / (math.pi * 10 ** 4 / 2)
        record("COPPIA: spostamento della superficie = theta r (+-10 %)", rel(u, u_th) < 0.10, f"{u:.5f} vs {u_th:.5f} mm")
        record("COPPIA: von Mises ~ sqrt(3) tau (+-15 %)", rel(r["von_mises_element_MPa"]["max"], math.sqrt(3) * tau_th) < 0.15 or
               rel(r["von_mises_nodal_MPa"]["max"], math.sqrt(3) * tau_th) < 0.15,
               f"{r['von_mises_nodal_MPa']['max']:.2f} / {r['von_mises_element_MPa']['max']:.2f} vs {math.sqrt(3) * tau_th:.2f} MPa")


async def assembly_scenario(c: Client, delta_th, E_th):
    """Due blocchi 100x20x10 messi di testa (x 0..100 e 100..200) = trave monolitica da 200 mm se il contatto e' incollato."""
    blk = F("sim_blocco")
    rm(blk)
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-BW / 2, y1=-H / 2, x2=BW / 2, y2=H / 2)
    await c.call("extrude_boss", depth=100)
    await c.call("assign_material", material="AISI 1020")
    await T(c, "save_document", "salva blocco", filepath=blk)
    await c.call("close_document", discard=True)
    asm = F("sim_assieme", "SLDASM")
    rm(asm)
    await T(c, "create_new_assembly")
    await T(c, "insert_component", "blocco 1 a x=0 (fisso)", file_path=blk, x=0, y=0, z=0, fixed=True)
    await T(c, "insert_component", "blocco 2 a x=100", file_path=blk, x=100, y=0, z=0, fixed=False)
    await T(c, "save_document", "salva assieme", filepath=asm)
    await T(c, "create_static_study", "studio d'assieme", name="Assieme")
    await T(c, "set_simulation_contact", "contatto globale incollato", contact="bonded")
    await T(c, "add_restraint", "fisso su x=0 (blocco 1)", kind="fixed", faces=[[0, 0, 0]])
    await T(c, "add_force", "100 N lungo -Z su x=200 (blocco 2)", faces=[[200, 0, 0]], value=FORCE, mode="direction", direction=[0, 0, -1])
    d = await T(c, "create_simulation_mesh", "mesh 4 mm assieme", element_size=4.0, mesher="standard", check=lambda d: d["nodes"] > 500)
    await T(c, "run_simulation", "assieme", timeout=300)
    r = await T(c, "get_simulation_results", "assieme")
    if r:
        record("ASSIEME incollato: spostamento come la trave monolitica (+-10 %)", rel(r["displacement_mm"]["max"], delta_th) < 0.10,
               f"{r['displacement_mm']['max']:.5f} vs {delta_th:.5f} mm; reazione {r['reaction_force_N']}")
        record("ASSIEME: reazione = 100 N", abs(r["reaction_force_N"]["z"] - FORCE) < 0.5, str(r["reaction_force_N"]))
    await T(c, "set_simulation_contact", "contatto libero: il blocco 2 non e' piu' tenuto", contact="free")
    await T(c, "set_simulation_contact", "tipo non valido", contact="boh", expect_fail=True)


if __name__ == "__main__":
    done = asyncio.run(run())
    print("\n==== RIEPILOGO ====")
    for tool, res, note in RESULTS:
        print(f"{res:5} {tool:90} {note}"[:260])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
