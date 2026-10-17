"""
Test live del GRUPPO E (simulazione avanzata, sezioni E3, E5, E1, E4, E2) tramite il server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente non viene mai
toccata; alla fine si chiude solo il PID lanciato dal test. Tutto si costruisce SOLO con tool MCP (mai execute_python). Unita': mm, N, MPa, N*m.
Ogni valore atteso si CALCOLA qui dalla formula (E, densita', snervamento e conducibilita' dalla libreria dei materiali) e si
stampa accanto al misurato. Pezzi e assiemi: test_output/sx_*.

  E3  fattore di sicurezza: nodo del minimo = nodo della VM massima, controllo incrociato, corpo critico di un assieme
  E5  frequenze (trave di Eulero), buckling (carico critico di Eulero), studio termico (conduzione 1D) e add_temperature
  E1  contatti locali (incollato / libero / senza penetrazione) in un assieme di due blocchi
  E4  carico remoto (forza con braccio, momento puro) e carico su cuscinetto (distribuzione sinusoidale)
  E2  controllo mesh locale sul foro di una piastra: nodi, Kt di Peterson

Uso:  .venv\\Scripts\\python.exe tests\\test_simulation_extra_live.py            tutte le sezioni (ordine E3 E5 E1 E4 E2)
      .venv\\Scripts\\python.exe tests\\test_simulation_extra_live.py E3 E1     solo quelle indicate
"""

import os
import sys
import math
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, PYTHON, SERVER, sw_pids, Client, cleanup
from test_simulation_live import RESULTS, record, T, F, rm, rel, BW, H, FORCE, I_BEAM   # aiuti comuni, stesso elenco dei risultati
from test_simulation_live import L as LB                                              # lunghezza della trave (200 mm)

PI = math.pi
A_BEAM = BW * H                      # 200 mm2
# piastra 40 x 100 x 5 (X 0..5 spessore, Y +-20 larghezza, Z +-50 lunghezza)
PW, PT, PL = 40.0, 5.0, 100.0


# ============================================================================================ aiuti
async def close_all(c: Client):
    """Chiude tutti i documenti aperti dal test (pezzi dell'assieme compresi), senza salvare. Tetto di 5 chiusure."""
    for _ in range(5):
        ok, _, _ = await c.call("close_document", discard=True)
        if not ok:
            break


async def lib_props(c: Client, name: str):
    """E (MPa), densita' (kg/m3), snervamento (MPa), conducibilita' (W/m K) del materiale dalla libreria di SolidWorks."""
    d = await T(c, "list_materials", f"proprieta' di {name} dalla libreria", query=name, include_properties=True,
                check=lambda d: any(m["name"] == name for m in d["materials"]))
    m = next((m for m in d.get("materials", []) if m["name"] == name), None)
    p = (m or {}).get("properties", {})
    out = {"E": p.get("elastic_modulus_Pa", 2.0e11) / 1e6, "rho": (m or {}).get("density_kg_m3", 7900.0) or 7900.0,
           "sy": p.get("yield_strength_Pa", 0.0) / 1e6, "k": p.get("thermal_conductivity", 0.0)}
    print(f"  {name} dalla libreria: E {out['E']:.0f} MPa, densita' {out['rho']:.0f} kg/m3, snervamento {out['sy']:.1f} MPa, k {out['k']:.1f} W/m K")
    return out


async def make_beam(c: Client, name: str, material: str = "AISI 1020"):
    """Trave X 0..200, Y +-10, Z +-5 (schizzo sul piano Front, estrusione di 200), salvata come test_output/<name>.SLDPRT."""
    part = F(name)
    rm(part)
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-BW / 2, y1=-H / 2, x2=BW / 2, y2=H / 2)
    await T(c, "extrude_boss", f"{name}: trave lunga 200", depth=LB)
    await T(c, "assign_material", f"{name}: {material}", material=material)
    await T(c, "save_document", f"salva {name}", filepath=part)
    return part


async def make_block(c: Client, name: str, material: str):
    """Blocco 100x20x10 (X 0..100, Y +-10, Z +-5), salvato e chiuso."""
    part = F(name)
    rm(part)
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-BW / 2, y1=-H / 2, x2=BW / 2, y2=H / 2)
    await T(c, "extrude_boss", f"{name}: blocco 100", depth=100)
    await T(c, "assign_material", f"{name}: {material}", material=material)
    await T(c, "save_document", f"salva {name}", filepath=part)
    await c.call("close_document", discard=True)
    return part


async def make_asm(c: Client, name: str, part_a: str, part_b: str):
    """Assieme con i due blocchi di testa (A a x=0, B a x=100), entrambi fissi."""
    asm = F(name, "SLDASM")
    rm(asm)
    await T(c, "create_new_assembly", f"{name}: nuovo assieme")
    await T(c, "insert_component", f"{name}: blocco A a x=0 (fisso)", file_path=part_a, x=0, y=0, z=0, fixed=True)
    await T(c, "insert_component", f"{name}: blocco B a x=100 (fisso)", file_path=part_b, x=100, y=0, z=0, fixed=True)
    await T(c, "save_document", f"salva {name}", filepath=asm)
    return asm


async def cantilever_loads(c: Client, direction=(0, 0, -1), value=FORCE):
    """Incastro su x=0 e forza sull'estremo x=200 (studio gia' creato)."""
    await T(c, "add_restraint", "fisso su x=0", kind="fixed", faces=[[0, 0, 0]])
    await T(c, "add_force", f"{value:g} N lungo {list(direction)} su x=200", faces=[[LB, 0, 0]], value=value,
            mode="direction", direction=list(direction))


async def mesh_and_run(c: Client, label: str, size: float = 4.0):
    d = await T(c, "create_simulation_mesh", f"{label}: mesh {size} mm", element_size=size, mesher="standard",
                check=lambda d: d["nodes"] > 100)
    await T(c, "run_simulation", label, timeout=300)
    return d


async def make_plate(c: Client, name: str, hole_r: float, material: str = "AISI 1020"):
    """Piastra 40x100x5 con foro passante al centro (X 0..5, Y +-20, Z +-50)."""
    part = F(name)
    rm(part)
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-PW / 2, y1=-PL / 2, x2=PW / 2, y2=PL / 2)
    await c.call("draw_circle", x=0, y=0, radius=hole_r)
    await T(c, "extrude_boss", f"{name}: piastra spessore 5", depth=PT)
    await T(c, "assign_material", f"{name}: {material}", material=material)
    await T(c, "save_document", f"salva {name}", filepath=part)
    return part


# ============================================================================================ E3
async def sec_e3(c: Client):
    """E3: fattore di sicurezza. (a) trave: il minimo cade nel nodo della VM massima e vale snervamento / VM max;
    (b) assieme acciaio + alluminio: il corpo critico e' l'alluminio (snervamento piu' basso, tensione di flessione comparabile)."""
    print("\n== E3 fattore di sicurezza")
    props = await lib_props(c, "AISI 1020")
    try:
        # ---- (a) trave in acciaio
        await make_beam(c, "sx_e3_trave")
        await T(c, "create_static_study", "E3a studio statico", name="Fos")
        await cantilever_loads(c)
        await mesh_and_run(c, "E3a")
        r = await T(c, "get_simulation_results", "E3a risultati")
        if r:
            fos, vm = r["factor_of_safety"], r["von_mises_nodal_MPa"]
            fos_th = props["sy"] / vm["max"]
            print(f"    FOS min {fos.get('min')} (calcolato dall'API {fos.get('computed_min')}, check_rel {fos.get('check_rel')}) "
                  f"vs snervamento/VM max = {props['sy']:.1f}/{vm['max']:.2f} = {fos_th:.3f}; in {fos.get('min_at_mm')}, VM max in {vm['max_at_mm']}")
            print(f"    corpo critico: {fos.get('min_body')}")
            record("E3a: computed_min = snervamento / VM max (libreria) entro 1e-3", rel(fos["computed_min"], fos_th) < 1e-3,
                   f"{fos['computed_min']:.4f} vs {fos_th:.4f}")
            record("E3a: il minimo e' nello stesso nodo della VM massima",
                   all(abs(p - q) < 1e-3 for p, q in zip(fos["min_at_mm"], vm["max_at_mm"])),
                   f"FOS min in {fos['min_at_mm']}, VM max in {vm['max_at_mm']}")
            record("E3a: check_rel < 1e-3 (minimo dell'API = minimo ricalcolato)", fos["check_rel"] < 1e-3, f"{fos['check_rel']}")
            record("E3a: il minimo e' vicino all'incastro (x < 15 mm)", fos["min_at_mm"][0] < 15, str(fos["min_at_mm"]))
            record("E3a: min_body.yield_MPa = snervamento della libreria", rel(fos["min_body"]["yield_MPa"], props["sy"]) < 1e-3,
                   f"{fos['min_body']['yield_MPa']} vs {props['sy']:.1f} MPa")
        await close_all(c)

        # ---- (b) assieme acciaio + alluminio
        pa = await make_block(c, "sx_blk_a", "AISI 1020")
        pb = await make_block(c, "sx_blk_b", "Lega 6061")
        await make_asm(c, "sx_e3_assieme", pa, pb)
        await T(c, "create_static_study", "E3b studio d'assieme", name="FosAssieme")
        await T(c, "set_simulation_contact", "contatto globale incollato", contact="bonded")
        await cantilever_loads(c)
        await mesh_and_run(c, "E3b")
        r = await T(c, "get_simulation_results", "E3b risultati")
        if r:
            fos = r["factor_of_safety"]
            body = fos["min_body"]
            print(f"    FOS min {fos.get('min')} in {fos.get('min_at_mm')}, corpo critico {body}")
            print(f"    per_body: {fos.get('per_body')}")
            record("E3b: il corpo critico e' l'alluminio (materiale 6061)", "6061" in str(body["material"]), str(body["material"]))
            record("E3b: il corpo critico e' il componente sx_blk_b", "sx_blk_b" in str(body["component"]), str(body["component"]))
            record("E3b: il minimo e' nel blocco B (x >= 100)", fos["min_at_mm"][0] >= 99.99, str(fos["min_at_mm"]))
            record("E3b: check_rel < 1e-3", fos["check_rel"] < 1e-3, f"{fos['check_rel']}")
            record("E3b: per_body ha 2 righe (una per corpo)", len(fos["per_body"]) == 2, f"{len(fos['per_body'])} righe")
            fos_b = body["yield_MPa"] / body["von_mises_max_MPa"]
            record("E3b: FOS minimo = snervamento / VM max del corpo critico (1e-3)", rel(fos["min"], fos_b) < 1e-3,
                   f"{fos['min']:.4f} vs {body['yield_MPa']:.2f}/{body['von_mises_max_MPa']:.2f} = {fos_b:.4f}")
            sig_b = FORCE * 100.0 * (H / 2) / I_BEAM        # M c / I a x=100 (momento F*(200-100)), faccia superiore
            record("E3b: VM massima del corpo B entro 15 % di M c / I a x=100", rel(body["von_mises_max_MPa"], sig_b) < 0.15,
                   f"{body['von_mises_max_MPa']:.2f} vs {sig_b:.2f} MPa")
    finally:
        await close_all(c)


# ============================================================================================ E5
async def sec_e5(c: Client):
    """E5: frequenze proprie e buckling della trave a mensola (Eulero-Bernoulli) e studio termico 1D."""
    print("\n== E5 frequenze, buckling, termico")
    props = await lib_props(c, "AISI 1020")
    E, rho, k = props["E"] * 1e6, props["rho"], props["k"]          # Pa, kg/m3, W/m K
    Lm, Am = LB * 1e-3, A_BEAM * 1e-6
    try:
        await make_beam(c, "sx_e5_trave")

        # ---- frequenze
        print("  -- frequenze")
        await T(c, "create_static_study", "E5 studio di frequenza (4 modi)", name="Frequenze", analysis="frequency", modes=4,
                check=lambda d: d["name"] == "Frequenze" and d["modes"] == 4)
        await T(c, "add_restraint", "fisso su x=0", kind="fixed", faces=[[0, 0, 0]])
        await mesh_and_run(c, "frequenze")
        r = await T(c, "get_simulation_results", "frequenze", check=lambda d: len(d["modes"]) >= 2)
        if r:
            modes = r["modes"]
            for m in modes:
                print(f"    modo {m['mode']}: {m['frequency_Hz']:.2f} Hz (omega {m['angular_rad_s']:.1f} rad/s, T {m['period_s'] * 1000:.3f} ms), "
                      f"partecipazione {m['mass_participation']}")
            coef = 1.8751 ** 2 / (2 * PI)
            f_z = coef * math.sqrt(E * (BW * H ** 3 / 12 * 1e-12) / (rho * Am * Lm ** 4))     # flessione lungo z (spessore 10)
            f_y = coef * math.sqrt(E * (H * BW ** 3 / 12 * 1e-12) / (rho * Am * Lm ** 4))     # flessione lungo y (larghezza 20)
            record("FREQUENZE: modo 1 = flessione in z, f = 1,8751^2/(2 pi) sqrt(E I/(rho A L^4)) entro 2 %",
                   rel(modes[0]["frequency_Hz"], f_z) < 0.02, f"{modes[0]['frequency_Hz']:.2f} vs {f_z:.2f} Hz")
            record("FREQUENZE: modo 2 = flessione in y, entro 2 %", rel(modes[1]["frequency_Hz"], f_y) < 0.02,
                   f"{modes[1]['frequency_Hz']:.2f} vs {f_y:.2f} Hz")
            record("FREQUENZE: partecipazione di massa del modo 1 dominante in z (> 0,5)", modes[0]["mass_participation"]["z"] > 0.5,
                   str(modes[0]["mass_participation"]))

        # ---- buckling
        print("  -- buckling")
        await T(c, "create_static_study", "E5 studio di buckling (2 modi)", name="Instabilita", analysis="buckling", modes=2,
                check=lambda d: d["name"] == "Instabilita" and d["modes"] == 2)
        await T(c, "add_restraint", "fisso su x=0", kind="fixed", faces=[[0, 0, 0]])
        await T(c, "add_force", "1000 N lungo -X su x=200 (compressione)", faces=[[LB, 0, 0]], value=1000.0, mode="direction",
                direction=[-1, 0, 0])
        await mesh_and_run(c, "buckling")
        r = await T(c, "get_simulation_results", "buckling", check=lambda d: len(d["buckling_load_factors"]) >= 2)
        if r:
            lf = r["buckling_load_factors"]
            lf_th = PI ** 2 * E * (BW * H ** 3 / 12 * 1e-12) / (4 * Lm ** 2) / 1000.0           # P_cr / 1000 N
            print(f"    fattori di carico: {lf}; Eulero (mensola) pi^2 E I_min/(4 L^2)/1000 N = {lf_th:.3f}")
            record("BUCKLING: fattore del modo 1 = pi^2 E I_min / (4 L^2) / 1000 N entro 2 %",
                   rel(lf[0]["load_factor"], lf_th) < 0.02, f"{lf[0]['load_factor']:.3f} vs {lf_th:.3f}")
            record("BUCKLING: il modo 2 ha fattore maggiore del modo 1", lf[1]["load_factor"] > lf[0]["load_factor"],
                   f"{lf[1]['load_factor']:.3f} > {lf[0]['load_factor']:.3f}")

        # ---- termico
        print("  -- termico")
        await T(c, "create_static_study", "E5 studio statico (per il rifiuto)", name="Statico")
        await T(c, "add_temperature", "temperatura in uno studio statico rifiutata", faces=[[0, 0, 0]], value=100.0, expect_fail=True)
        await T(c, "create_static_study", "E5 studio termico", name="Termico", analysis="thermal",
                check=lambda d: d["name"] == "Termico")
        await T(c, "add_temperature", "100 C su x=0", faces=[[0, 0, 0]], value=100.0)
        await T(c, "add_temperature", "0 C su x=200", faces=[[LB, 0, 0]], value=0.0)
        await mesh_and_run(c, "termico")
        r = await T(c, "get_simulation_results", "termico")
        if r:
            t, g, q = r["temperature_C"], r["temperature_gradient_K_m"], r["heat_flux_W_m2"]
            print(f"    T {t}; gradiente {g}; flusso {q}; componenti {r.get('heat_flux_components_W_m2')}")
            grad_th = 100.0 / Lm                      # dT/L = 500 K/m
            flux_th = k * grad_th                     # k dT/L
            q_th = flux_th * Am
            record("TERMICO: T max = 100 C e T min = 0 C (+-0,01)", abs(t["max"] - 100.0) < 0.01 and abs(t["min"]) < 0.01,
                   f"max {t['max']:.4f}, min {t['min']:.4f}")
            record("TERMICO: T max in x=0 e T min in x=200 (+-0,5 mm)",
                   abs(t["max_at_mm"][0]) < 0.5 and abs(t["min_at_mm"][0] - LB) < 0.5, f"max in {t['max_at_mm']}, min in {t['min_at_mm']}")
            gmax = max(abs(g["min"]), abs(g["max"]))
            record("TERMICO: gradiente = dT/L = 500 K/m entro 1 %", rel(gmax, grad_th) < 0.01, f"{gmax:.2f} vs {grad_th:.2f} K/m")
            record("TERMICO: flusso di calore = k dT/L (k dalla libreria) entro 1 %", rel(q["max"], flux_th) < 0.01,
                   f"{q['max']:.1f} vs {k:.1f} * {grad_th:.0f} = {flux_th:.1f} W/m2")
            record("TERMICO: potenza Q = flusso * A (A = 2e-4 m2) entro 1 %", rel(q["max"] * Am, q_th) < 0.01,
                   f"{q['max'] * Am:.4f} vs {q_th:.4f} W")
    finally:
        await close_all(c)


# ============================================================================================ E1
async def sec_e1(c: Client):
    """E1: contatti locali in un assieme di due blocchi AISI 1020 di testa. Cinque studi: l'incollato locale (con globale libero) deve
    dare la stessa freccia del globale incollato; il locale senza penetrazione tiene in compressione e si stacca in trazione."""
    print("\n== E1 contatti locali")
    props = await lib_props(c, "AISI 1020")
    E = props["E"]
    delta_th = FORCE * LB ** 3 / (3 * E * I_BEAM)
    ux_th = FORCE * LB / (E * A_BEAM)
    print(f"  attesi: freccia F L^3/(3 E I) = {delta_th:.5f} mm, accorciamento F L/(E A) = {ux_th:.6f} mm")
    pa = await make_block(c, "sx_c_a", "AISI 1020")
    pb = await make_block(c, "sx_c_b", "AISI 1020")
    try:
        await make_asm(c, "sx_e1_assieme", pa, pb)

        async def study(name, glob, local, direction):
            await T(c, "create_static_study", f"E1 {name}", name=name)
            await T(c, "set_simulation_contact", f"{name}: contatto globale {glob}", contact=glob)
            if local:
                await T(c, "add_simulation_contact", f"{name}: contatto locale {local} sulla faccia x=100", faces1=[[100, 0, 0]],
                        faces2=[[100, 0, 0]], contact=local)
            await cantilever_loads(c, direction=direction)
            await T(c, "create_simulation_mesh", f"{name}: mesh 4 mm", element_size=4.0, mesher="standard",
                    check=lambda d: d["nodes"] > 500)

        async def solve(name):
            await T(c, "run_simulation", name, timeout=300)
            return await T(c, "get_simulation_results", f"{name} risultati")

        # (1) globale libero + locale incollato, flessione
        await study("Locale_incollato", "free", "bonded", (0, 0, -1))
        await T(c, "list_simulation_loads", "il contatto locale e' elencato (tipo contatto)",
                check=lambda d: any(i["type"] == "contatto" for i in d["items"]))
        r1 = await solve("Locale_incollato")
        # (2) globale incollato, flessione
        await study("Globale_incollato", "bonded", None, (0, 0, -1))
        r2 = await solve("Globale_incollato")
        if r1 and r2:
            d1, d2 = r1["displacement_mm"]["max"], r2["displacement_mm"]["max"]
            print(f"    freccia: locale incollato {d1:.5f}, globale incollato {d2:.5f}, teorica {delta_th:.5f} mm")
            record("E1 (1): freccia con globale libero + locale incollato entro 10 % di F L^3/(3 E I)", rel(d1, delta_th) < 0.10,
                   f"{d1:.5f} vs {delta_th:.5f} mm ({rel(d1, delta_th) * 100:.2f} %)")
            record("E1 (1)=(2): locale incollato = globale incollato entro 1 %", rel(d1, d2) < 0.01,
                   f"{d1:.5f} vs {d2:.5f} mm ({rel(d1, d2) * 100:.3f} %)")
        # (3) globale incollato, compressione lungo -X
        await study("Compressione_incollato", "bonded", None, (-1, 0, 0))
        r3 = await solve("Compressione_incollato")
        d3 = None
        if r3:
            ux3 = r3["displacement_components_mm"]["ux"]["min"]
            d3 = r3["displacement_mm"]["max"]
            print(f"    compressione incollata: ux {ux3:.6f} mm, |u| max {d3:.6f} mm (teorico {ux_th:.6f})")
            record("E1 (3): accorciamento in compressione entro 5 % di F L/(E A)", rel(abs(ux3), ux_th) < 0.05,
                   f"{abs(ux3):.6f} vs {ux_th:.6f} mm ({rel(abs(ux3), ux_th) * 100:.2f} %)")
        # (4) globale libero + locale senza penetrazione, compressione
        await study("Compressione_nopen", "free", "no_penetration", (-1, 0, 0))
        r4 = await solve("Compressione_nopen")
        if r4 and d3:
            d4 = r4["displacement_mm"]["max"]
            record("E1 (4): senza penetrazione in compressione = incollato entro 1 %", rel(d4, d3) < 0.01,
                   f"{d4:.6f} vs {d3:.6f} mm ({rel(d4, d3) * 100:.3f} %)")
        # (5) globale libero + locale senza penetrazione, trazione: il blocco B si stacca
        await study("Trazione_nopen", "free", "no_penetration", (1, 0, 0))
        ok, text, _ = await c.call("run_simulation", timeout=300)
        if not ok:
            record("E1 (5): trazione con contatto senza penetrazione: il blocco si stacca (run_simulation fallisce)", True, text.split("\n")[0][:160])
        else:
            r5 = (await c.call("get_simulation_results"))[2]
            d5 = r5["displacement_mm"]["max"] if r5 else 0.0
            record("E1 (5): trazione con contatto senza penetrazione: il blocco si stacca (spostamento > 100 volte lo studio 3)",
                   bool(d3) and d5 > 100 * d3, f"{d5:.6f} mm vs {d3} mm (x{d5 / d3 if d3 else 0:.0f})")
        # contatto non valido e cancellazione
        await T(c, "add_simulation_contact", "tipo di contatto sconosciuto rifiutato", faces1=[[100, 0, 0]], faces2=[[100, 0, 0]],
                contact="boh", expect_fail=True)
        d = await T(c, "list_simulation_loads", "elenco con il contatto locale",
                    check=lambda d: any(i["type"] == "contatto" for i in d["items"]))
        cont = next((i for i in d.get("items", []) if i["type"] == "contatto"), None)
        if cont:
            await T(c, "delete_simulation_load", f"cancella il contatto locale {cont['name']}", name=cont["name"])
            await T(c, "list_simulation_loads", "il contatto non c'e' piu'",
                    check=lambda d: not any(i["type"] == "contatto" for i in d["items"]))
    finally:
        await close_all(c)


# ============================================================================================ E4
async def sec_e4(c: Client):
    """E4: carichi remoti (forza con braccio, momento puro) e carico su cuscinetto."""
    print("\n== E4 carichi remoti e cuscinetto")
    props = await lib_props(c, "AISI 1020")
    E = props["E"]
    try:
        # ---- (a) forza remota con braccio
        await make_beam(c, "sx_e4_trave")
        await T(c, "create_static_study", "E4a studio", name="Remoto")
        await T(c, "add_restraint", "fisso su x=0", kind="fixed", faces=[[0, 0, 0]])
        px, fz, arm = 250.0, -100.0, 50.0
        await T(c, "add_remote_load", "100 N lungo -Z applicati nel punto (250,0,0)", faces=[[LB, 0, 0]], point=[px, 0, 0], force=[0, 0, fz])
        await mesh_and_run(c, "E4a")
        r = await T(c, "get_simulation_results", "E4a risultati")
        if r:
            my_th = px * fz * 1e-3                                     # reazione = -(r x F)_y = -(rz Fx - rx Fz) = rx Fz, N*m
            delta_th = abs(fz) * LB ** 3 / (3 * E * I_BEAM) + abs(fz) * arm * LB ** 2 / (2 * E * I_BEAM)
            uz = abs(r["displacement_components_mm"]["uz"]["min"])
            print(f"    reazione {r['reaction_force_N']}, momento di reazione {r['reaction_moment_Nm']}, uz {uz:.5f} mm")
            record("E4a: reazione z = 100 N (+-0,5)", abs(r["reaction_force_N"]["z"] - abs(fz)) < 0.5, str(r["reaction_force_N"]))
            record("E4a: momento di reazione y = -F x 0,25 m = -25 N*m (attorno all'origine) entro 1 %",
                   rel(r["reaction_moment_Nm"]["y"], my_th) < 0.01, f"{r['reaction_moment_Nm']['y']:.4f} vs {my_th:.4f} N*m")
            record("E4a: freccia entro 10 % di F L^3/(3EI) + (F a) L^2/(2EI)", rel(uz, delta_th) < 0.10,
                   f"{uz:.5f} vs {delta_th:.5f} mm ({rel(uz, delta_th) * 100:.2f} %)")

        # ---- (b) solo momento
        await T(c, "create_static_study", "E4b studio (solo momento)", name="Momento")
        await T(c, "add_restraint", "fisso su x=0", kind="fixed", faces=[[0, 0, 0]])
        await T(c, "add_remote_load", "momento 10 N*m attorno a y nel punto (200,0,0)", faces=[[LB, 0, 0]], point=[LB, 0, 0],
                moment=[0, 10.0, 0])
        await mesh_and_run(c, "E4b")
        r = await T(c, "get_simulation_results", "E4b risultati")
        if r:
            f = r["reaction_force_N"]
            fres = math.sqrt(f["x"] ** 2 + f["y"] ** 2 + f["z"] ** 2)
            u_th = 10.0 * 1e3 * LB ** 2 / (2 * E * I_BEAM)           # M L^2/(2EI) in mm
            print(f"    momento di reazione {r['reaction_moment_Nm']}, reazione {f} (risultante {fres:.4f} N), "
                  f"|u| max {r['displacement_mm']['max']:.5f} mm (M L^2/(2EI) = {u_th:.5f})")
            record("E4b: |momento di reazione y| = 10 N*m entro 2 %", rel(abs(r["reaction_moment_Nm"]["y"]), 10.0) < 0.02,
                   f"{r['reaction_moment_Nm']['y']:.4f} N*m")
            record("E4b: reazione risultante < 0,5 N (momento puro)", fres < 0.5, f"{fres:.4f} N")
        await close_all(c)

        # ---- (c) cuscinetto
        print("  -- cuscinetto")
        await make_plate(c, "sx_e4_piastra", hole_r=5.0)
        await T(c, "create_static_study", "E4c studio cuscinetto", name="Cuscinetto")
        await T(c, "add_restraint", "fisso su z=-50", kind="fixed", faces=[[PT / 2, 0, -PL / 2]])
        await T(c, "add_bearing_load", "1000 N lungo +Z sul foro, distribuzione sinusoidale", face=[PT / 2, 0, 5.0], value=1000.0,
                direction=[0, 0, 1], distribution="sinusoidal")
        await mesh_and_run(c, "E4c", size=2.0)
        r = await T(c, "get_simulation_results", "E4c risultati")
        if r:
            print(f"    reazione {r['reaction_force_N']}")
            record("E4c: reazione z = -1000 N (+-1)", abs(r["reaction_force_N"]["z"] + 1000.0) < 1.0, str(r["reaction_force_N"]))
        dc = await T(c, "get_simulation_stress_on_faces", "sz sul foro, al centro del semicilindro caricato", faces=[[PT / 2, 0, 5.0]],
                     component="sz", box=[0, -1.3, 4.8, 5, 1.3, 5.1], check=lambda d: d["nodes"] > 0)
        ds = await T(c, "get_simulation_stress_on_faces", "sz sul foro, sul fianco", faces=[[PT / 2, 0, 5.0]],
                     component="sz", box=[0, 3.4, 2.0, 5, 4.7, 3.6], check=lambda d: d["nodes"] > 0)
        if dc and ds:
            print(f"    sz medio al centro {dc['mean_MPa']:.2f} MPa ({dc['nodes']} nodi), sul fianco {ds['mean_MPa']:.2f} MPa ({ds['nodes']} nodi)")
            record("E4c: distribuzione sinusoidale: al centro sz < 0 e piu' compresso che sul fianco",
                   dc["mean_MPa"] < 0 and dc["mean_MPa"] < ds["mean_MPa"], f"centro {dc['mean_MPa']:.2f} vs fianco {ds['mean_MPa']:.2f} MPa")
    finally:
        await close_all(c)


# ============================================================================================ E2
async def sec_e2(c: Client):
    """E2: controllo mesh locale sul foro di una piastra in trazione. Con la mesh standard da 2 mm il foro ha pochi nodi e Kt e' sottostimato;
    con un controllo da 0,5 mm sul foro i nodi del foro si moltiplicano e Kt si avvicina a Peterson, mentre lontano dal foro la mesh non cambia."""
    print("\n== E2 controllo mesh")
    dh, ft = 4.0, 2000.0
    sig_net = ft / ((PW - dh) * PT)
    lam = dh / PW
    kt_p = 3.0 - 3.14 * lam + 3.667 * lam ** 2 - 1.527 * lam ** 3
    print(f"  sigma netta {sig_net:.2f} MPa, lambda {lam:.3f}, Kt di Peterson {kt_p:.3f}")
    try:
        await make_plate(c, "sx_e2_piastra", hole_r=dh / 2)
        await T(c, "create_static_study", "E2 studio trazione", name="Controllo")
        await T(c, "add_restraint", "fisso su z=-50", kind="fixed", faces=[[PT / 2, 0, -PL / 2]])
        await T(c, "add_force", "2000 N lungo +Z su z=+50", faces=[[PT / 2, 0, PL / 2]], value=ft, mode="direction", direction=[0, 0, 1])

        async def measure(label):
            hole = await T(c, "get_simulation_stress_on_faces", f"{label}: nodi e tensione sul foro", faces=[[PT / 2, 0, dh / 2]],
                           check=lambda d: d["nodes"] > 10)
            far = await T(c, "get_simulation_stress_on_faces", f"{label}: nodi sulla faccia lontana", faces=[[PT / 2, 0, PL / 2]],
                          check=lambda d: d["nodes"] > 10)
            return hole, far

        m0 = await T(c, "create_simulation_mesh", "mesh standard 2 mm", element_size=2.0, mesher="standard", check=lambda d: d["nodes"] > 500)
        await T(c, "run_simulation", "senza controllo", timeout=300)
        h1, f1 = await measure("senza controllo")
        kt1 = h1["max_MPa"] / sig_net if h1 else None
        if h1 and f1:
            print(f"    mesh {m0.get('nodes')} nodi: sul foro {h1['nodes']} nodi, VM max {h1['max_MPa']:.2f} MPa -> Kt {kt1:.3f}; faccia lontana {f1['nodes']} nodi")

        await T(c, "add_mesh_control", "0,5 mm sul foro", faces=[[PT / 2, 0, dh / 2]], element_size=0.5, ratio=1.5)
        d = await T(c, "list_simulation_loads", "il controllo mesh e' elencato", check=lambda d: any(i["type"] == "controllo mesh" for i in d["items"]))
        m1 = await T(c, "create_simulation_mesh", "nuova mesh standard 2 mm con il controllo", element_size=2.0, mesher="standard",
                     check=lambda d: d["nodes"] > 500)
        await T(c, "run_simulation", "con controllo", timeout=300)
        h2, f2 = await measure("con controllo")
        if h1 and f1 and h2 and f2:
            kt2 = h2["max_MPa"] / sig_net
            print(f"    mesh {m1.get('nodes')} nodi: sul foro {h2['nodes']} nodi, VM max {h2['max_MPa']:.2f} MPa -> Kt {kt2:.3f}; faccia lontana {f2['nodes']} nodi")
            record("E2: nodi sul foro almeno 4 volte con il controllo", h2["nodes"] >= 4 * h1["nodes"], f"{h2['nodes']} vs {h1['nodes']} nodi")
            record("E2: Kt con il controllo entro 3 % da Peterson", rel(kt2, kt_p) < 0.03, f"{kt2:.3f} vs {kt_p:.3f} ({rel(kt2, kt_p) * 100:.2f} %)")
            record("E2: Kt con il controllo piu' vicino a Peterson di quello senza", rel(kt2, kt_p) < rel(kt1, kt_p),
                   f"{kt2:.3f} ({rel(kt2, kt_p) * 100:.2f} %) contro {kt1:.3f} ({rel(kt1, kt_p) * 100:.2f} %)")
            record("E2: nodi sulla faccia lontana invariati entro +-15 %", rel(f2["nodes"], f1["nodes"]) <= 0.15,
                   f"{f2['nodes']} vs {f1['nodes']} nodi")
        ctrl = next((i for i in d.get("items", []) if i["type"] == "controllo mesh"), None)
        if ctrl:
            await T(c, "delete_simulation_load", f"cancella il controllo mesh {ctrl['name']}", name=ctrl["name"])
            await T(c, "list_simulation_loads", "il controllo mesh non c'e' piu'",
                    check=lambda d: not any(i["type"] == "controllo mesh" for i in d["items"]))
    finally:
        await close_all(c)


SECTIONS = {"E3": sec_e3, "E5": sec_e5, "E1": sec_e1, "E4": sec_e4, "E2": sec_e2}


# ============================================================================================ avvio
async def run(names):
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
                ok, text, data = await c.call("connect_solidworks")
                my_pid = data.get("pid")
                print(text[:200])
                if not ok or not my_pid or my_pid in elia_pids or my_pid not in sw_pids():
                    print("STOP: nessuna istanza separata ottenibile. Nulla e' stato toccato.")
                    return False
                record("PID dedicato diverso dall'istanza utente", my_pid not in elia_pids, str(my_pid))
                new = ["create_static_study", "add_temperature", "add_remote_load", "add_bearing_load", "add_simulation_contact", "add_mesh_control"]
                record("i tool del gruppo E sono esposti dal server", all(t in tools for t in new), f"mancanti {[t for t in new if t not in tools]}")
                await T(c, "simulation_status", "add-in disponibile", check=lambda d: d["available"])
                for n in names:
                    try:
                        await SECTIONS[n](c)
                    except Exception as e:
                        record(f"{n}: sezione interrotta da un'eccezione", False, repr(e)[:200])
                        await close_all(c)
    finally:
        cleanup(my_pid, elia_pids)
    return True


if __name__ == "__main__":
    names = [a.upper() for a in sys.argv[1:]] or list(SECTIONS)
    bad = [n for n in names if n not in SECTIONS]
    if bad:
        print(f"Sezioni sconosciute: {bad}. Disponibili: {list(SECTIONS)}")
        sys.exit(2)
    done = asyncio.run(run(names))
    print("\n==== RIEPILOGO ====")
    for tool, res, note in RESULTS:
        print(f"{res:5} {tool:90} {note}"[:260])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
