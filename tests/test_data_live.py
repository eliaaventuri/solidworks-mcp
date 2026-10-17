"""
Test live dei tool di DATI ED EXPORT (blocco 3) tramite il server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente non viene mai
toccata; alla fine si chiude solo il PID lanciato dal test. Costruisce SOLO tramite tool MCP:
  - blocco 80x50x30 (X 0..30, Y +-40, Z +-25) con foro d12 passante lungo X;
  - materiali (AISI 304, Lega 6061, ABS generico): massa = volume x densita' letta dalla libreria (< 0,1 %);
  - baricentro e inerzie del parallelepipedo vs formule (< 0,5 %), massa sovrascritta;
  - proprieta' personalizzate (file / configurazione, espressioni SW-Mass), cartiglio con il materiale (testo DXF);
  - variabile globale + equazione (la quota e il volume seguono la variabile);
  - configurazioni con quote e soppressioni diverse, volumi verificati attivandole;
  - export STL/3MF/STEP/IGES/Parasolid/PDF 3D/eDrawings con verifica dei file; reimport e confronto dei volumi;
  - misure (distanza fra facce parallele, angolo, diametro del foro, area, box);
  - immagini con geometria di riferimento nascosta (nessun pixel azzurro del piano), sfondo bianco, risoluzione.

Uso:  .venv\\Scripts\\python.exe tests\\test_data_live.py       Output: test_output\\ (file dx_*)
"""

import os
import sys
import math
import asyncio
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup, L
PI = math.pi

RESULTS = []

# blocco: X 0..30 (estrusione dal Piano frontale, normale X), Y -40..40, Z -25..25, foro d12 lungo X
A, B, C = 30.0, 80.0, 50.0
V_BLOCK = A * B * C
V_HOLE = PI * 6 ** 2 * A


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:240])


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


def blue_pixels(path):
    """Pixel 'azzurri' (piano di riferimento: B molto maggiore di R e G) in un PNG."""
    from solidworks_mcp.automation.data_export import _read_png
    w, h, bpp, rows = _read_png(str(path))
    n = 0
    for y in range(0, h):
        r = rows[y]
        for x in range(0, w):
            R, G, Bl = r[x * bpp], r[x * bpp + 1], r[x * bpp + 2]
            if Bl > R + 25 and Bl > G + 10:
                n += 1
    return n, (w, h), tuple(rows[2][0:3])


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


# ============================================================================================ scenario
async def scenario(c: Client, tools):
    from solidworks_mcp.data_tools import DATA_DISPATCH
    missing = [t for t in DATA_DISPATCH if t not in tools]
    record("tutti i tool del blocco 3 esposti dal server", not missing, f"{len(DATA_DISPATCH)} tool, mancanti {missing}")
    # blocco 4: +5 tool di tavola (arrange_drawing_dimensions, get_drawing_layout, set_dimension_tolerance, add_hole_table,
    # add_general_roughness) -> 172 + 5 = 177 (il controllo dell'esatto numero e' stato aggiornato per questo motivo)
    # gruppo A (limiti dei disegni): +1 tool, add_explode_lines (linee di esplosione) -> 195 + 1 = 196
    record("177 tool precedenti + 18 del blocco 5 (simulazione) + 1 del gruppo A (add_explode_lines) = 196, senza duplicati", len(tools) == len(set(tools)) and len(tools) >= 143 + len(DATA_DISPATCH) - 1 and len(tools) == 196,
           f"{len(tools)} tool")

    # ------------------------------------------------------------------ 1. pezzo
    print("\n== 1. Blocco di prova")
    part = F("dx_blocco")
    rm(part)
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-B / 2, y1=-C / 2, x2=B / 2, y2=C / 2)
    await T(c, "extrude_boss", "blocco 80x50x30", depth=A)
    ok, _, m = await c.call("get_mass_properties")
    record("blocco: volume 120000 mm3", ok and rel(m["volume_mm3"], V_BLOCK) < 1e-6, f"{m.get('volume_mm3')}")
    await T(c, "save_document", "salva dx_blocco", filepath=part)

    # ------------------------------------------------------------------ 2. materiali
    print("\n== 2. Materiali")
    d = await T(c, "list_materials", "categorie", check=lambda d: d["total"] > 100 and L("Acciaio") in d["categories"] and L("Plastiche") in d["categories"])
    d = await T(c, "list_materials", "Plastiche / ABS", category="Plastiche", query="ABS",
                check=lambda d: any(m["name"] == L("ABS generico") for m in d["materials"]))
    dens_abs = next((m["density_kg_m3"] for m in d.get("materials", []) if m["name"] == L("ABS generico")), None)
    d = await T(c, "list_materials", "query PLA (se presente)", query="PLA")
    record("list_materials: PLA nella libreria?", True, f"{d.get('matching')} corrispondenze (informativo: PLA {'presente' if d.get('matching') else 'assente'})")
    d = await T(c, "list_materials", "AISI 304", query="AISI 304", check=lambda d: d["materials"][0]["name"] == "AISI 304")
    dens304 = d["materials"][0]["density_kg_m3"] if d.get("materials") else None
    d = await T(c, "list_materials", "Lega 6061", category="alluminio", query="Lega 6061")
    dens6061 = next((m["density_kg_m3"] for m in d.get("materials", []) if m["name"] == L("Lega 6061")), None)
    print(f"  densita' dalla libreria: AISI 304 {dens304}, Lega 6061 {dens6061}, ABS {dens_abs}")

    await T(c, "assign_material", "AISI 304", material="AISI 304", check=lambda d: d["material"] == "AISI 304" and d["title_block_link"])
    await T(c, "get_material", "AISI 304 corrente", check=lambda d: d["material"] == "AISI 304" and "SW-Material" in d["Material_property"]
            and d["Material_property_resolved"] == "AISI 304")
    ok, _, mp = await c.call("get_part_mass_properties")
    mass304 = mp.get("mass_kg", 0)
    exp = mp.get("volume_mm3", 0) * 1e-9 * dens304
    record("MASSA: AISI 304 = volume x densita' letta dal materiale (< 0,1 %)", ok and rel(mass304, exp) < 1e-3,
           f"massa {mass304:.6f} kg, atteso {exp:.6f} (vol {mp.get('volume_mm3')} mm3 x {dens304} kg/m3)")
    record("densita' usata = densita' del materiale", abs(mp.get("density_kg_m3", 0) - dens304) < 0.5, f"{mp.get('density_kg_m3')}")

    # inerzie del parallelepipedo (con AISI 304)
    cx = A / 2
    record("BARICENTRO parallelepipedo = (15, 0, 0) mm (< 0,5 %)",
           ok and abs(mp["center_of_mass"][0] - cx) / cx < 5e-3 and abs(mp["center_of_mass"][1]) < 1e-3 and abs(mp["center_of_mass"][2]) < 1e-3,
           f"{mp.get('center_of_mass')}")
    m_ = mass304
    # assi del modello: X = spessore (A), Y = B, Z = C
    Ixx, Iyy, Izz = m_ / 12 * (B ** 2 + C ** 2) * 1e-6, m_ / 12 * (A ** 2 + C ** 2) * 1e-6, m_ / 12 * (A ** 2 + B ** 2) * 1e-6
    tc = mp.get("inertia_tensor_at_center_of_mass_kg_m2", [[0] * 3] * 3)
    record("INERZIE nel baricentro: Ixx, Iyy, Izz vs formule m/12(b2+c2) (< 0,5 %)",
           rel(tc[0][0], Ixx) < 5e-3 and rel(tc[1][1], Iyy) < 5e-3 and rel(tc[2][2], Izz) < 5e-3,
           f"misurati {tc[0][0]:.4e} {tc[1][1]:.4e} {tc[2][2]:.4e} / attesi {Ixx:.4e} {Iyy:.4e} {Izz:.4e}")
    off = [abs(tc[i][j]) for i in range(3) for j in range(3) if i != j]
    record("INERZIE: prodotti d'inerzia nulli nel baricentro", max(off) < 1e-3 * max(Ixx, Iyy, Izz), f"max {max(off):.2e}")
    to = mp.get("inertia_tensor_at_origin_kg_m2", [[0] * 3] * 3)
    Ixx_o, Iyy_o, Izz_o = Ixx, Iyy + m_ * (cx * 1e-3) ** 2, Izz + m_ * (cx * 1e-3) ** 2     # Huygens-Steiner (baricentro su X)
    record("INERZIE nell'origine = Huygens-Steiner (< 0,5 %)",
           rel(to[0][0], Ixx_o) < 5e-3 and rel(to[1][1], Iyy_o) < 5e-3 and rel(to[2][2], Izz_o) < 5e-3,
           f"misurati {to[0][0]:.4e} {to[1][1]:.4e} {to[2][2]:.4e} / attesi {Ixx_o:.4e} {Iyy_o:.4e} {Izz_o:.4e}")
    pm = sorted(mp.get("principal_moments_kg_m2", [0, 0, 0]))
    ex = sorted([Ixx, Iyy, Izz])
    record("MOMENTI PRINCIPALI vs formule (< 0,5 %)", all(rel(a, b) < 5e-3 for a, b in zip(pm, ex)), f"{pm} / {ex}")
    ax = mp.get("principal_axes", [])
    dots = [sum(ax[i][k] * ax[j][k] for k in range(3)) for i in range(3) for j in range(i + 1, 3)] if len(ax) == 3 else [9]
    norms = [sum(v * v for v in a) for a in ax]
    record("ASSI PRINCIPALI ortonormali", all(abs(x) < 1e-6 for x in dots) and all(abs(n - 1) < 1e-6 for n in norms), f"norme {norms}")

    await T(c, "assign_material", "Lega 6061", material="Lega 6061")
    ok, _, mp2 = await c.call("get_part_mass_properties")
    record("MASSA: cambio in Lega 6061 -> rapporto delle densita' (< 0,1 %)", ok and rel(mp2["mass_kg"] / mass304, dens6061 / dens304) < 1e-3,
           f"{mp2.get('mass_kg'):.6f} / {mass304:.6f} = {mp2.get('mass_kg', 0) / mass304:.5f} atteso {dens6061 / dens304:.5f}")
    await T(c, "assign_material", "ABS generico (plastica)", material="ABS generico", category="Plastiche")
    ok, _, mp3 = await c.call("get_part_mass_properties")
    record("MASSA: ABS generico -> rapporto delle densita' (< 0,1 %)", ok and rel(mp3["mass_kg"] / mass304, dens_abs / dens304) < 1e-3,
           f"{mp3.get('mass_kg', 0) / mass304:.5f} atteso {dens_abs / dens304:.5f}")
    await T(c, "assign_material", "materiale inesistente", material="Unobtainium", expect_fail=True)
    # materiale su un solo corpo
    ok, _, gm = await c.call("get_material")
    body_name = (gm.get("bodies") or [{}])[0].get("body")
    await T(c, "assign_material", f"AISI 304 al solo corpo '{body_name}'", material="AISI 304", body=body_name, link_title_block=False)
    ok, _, bp = await c.call("get_part_mass_properties", body=body_name)
    record("MASSA del corpo con materiale proprio = volume x densita' (< 0,1 %)", ok and rel(bp["mass_kg"], V_BLOCK * 1e-9 * dens304) < 1e-3,
           f"{bp.get('mass_kg')} kg, corpo {bp.get('body')}")
    await T(c, "assign_material", "AISI 304 a tutto il pezzo (come finale)", material="AISI 304")

    # massa sovrascritta
    await T(c, "set_mass_override", "massa 1,000 kg", mass=1.0, check=lambda d: abs(d["mass_kg"] - 1.0) < 1e-9 and d["mass_overridden"])
    ok, _, mo = await c.call("get_part_mass_properties")
    record("massa sovrascritta riletta da get_part_mass_properties", ok and abs(mo["mass_kg"] - 1.0) < 1e-9 and mo["mass_overridden"], f"{mo.get('mass_kg')}")
    await T(c, "set_mass_override", "rimozione", check=lambda d: not d["mass_overridden"] and rel(d["mass_kg"], mass304) < 1e-6)

    # ------------------------------------------------------------------ 3. proprieta' personalizzate
    print("\n== 3. Proprieta' personalizzate")
    await T(c, "set_custom_property", "Cliente (file)", name="Cliente", value="ACME", check=lambda d: d["value"] == "ACME")
    await T(c, "set_custom_property", "Peso = espressione SW-Mass", name="Peso", value="SW-Mass@dx_blocco.SLDPRT",
            check=lambda d: d["is_expression"] and d["resolved"] not in ("", None))
    d = await T(c, "get_custom_property", "Peso risolto", name="Peso")
    try:
        grams = float(str(d.get("resolved", "0")).replace(",", "."))
    except ValueError:
        grams = 0
    record("proprieta' Peso (SW-Mass) = massa del modello (< 0,5 %)", rel(grams / 1000.0, mass304) < 5e-3, f"{grams} g vs {mass304 * 1000:.2f} g")
    await T(c, "set_custom_property", "Codice (numero)", name="Codice", value="1234", type="number")
    await T(c, "set_custom_property", "Colore specifico della configurazione Default", name="Colore", value="grigio", configuration="Default")
    d = await T(c, "list_custom_properties", "file", check=lambda d: {"Cliente", "Peso", "Codice", "Material"} <= {p["name"] for p in d["properties"]})
    d = await T(c, "list_custom_properties", "configurazione Default", configuration="Default",
                check=lambda d: [p["name"] for p in d["properties"]] == ["Colore"])
    await T(c, "get_custom_property", "riletta Cliente", name="Cliente", check=lambda d: d["value"] == "ACME")
    await T(c, "delete_custom_property", "elimina Cliente", name="Cliente", check=lambda d: "Cliente" not in d["remaining"])
    await T(c, "get_custom_property", "Cliente non piu' presente", name="Cliente", expect_fail=True)
    await T(c, "delete_custom_property", "elimina Colore (config)", name="Colore", configuration="Default")

    # ------------------------------------------------------------------ 4. variabili globali / equazioni
    print("\n== 4. Variabili globali ed equazioni")
    dim = "D1@Estrusione-Estrusione1"
    await T(c, "set_global_variable", "crea lunghezza = 15", name="lunghezza", value=15, check=lambda d: d["created"] and d["value"] == 15)
    await T(c, "add_equation", f'"{dim}" = "lunghezza" * 2', equation=f'"{dim}" = "lunghezza" * 2', check=lambda d: abs(d["volume_mm3"] - V_BLOCK) < 1)
    ok, _, dv = await c.call("get_dimension_value", name=dim)
    record("quota = lunghezza x 2 = 30 mm", ok and abs(dv.get("value", 0) - 30) < 1e-6, f"{dv.get('value')}")
    d = await T(c, "set_global_variable", "modifica lunghezza = 20", name="lunghezza", value=20, check=lambda d: d["value"] == 20 and not d["created"])
    ok, _, dv = await c.call("get_dimension_value", name=dim)
    record("VARIABILE: la quota segue (20 x 2 = 40 mm)", ok and abs(dv.get("value", 0) - 40) < 1e-6, f"{dv.get('value')}")
    record("VARIABILE: il volume segue (80x50x40 = 160000 mm3)", abs(d.get("volume_mm3", 0) - 160000) < 1, f"{d.get('volume_mm3')}")
    ok, _, mpv = await c.call("get_part_mass_properties")
    record("VARIABILE: la massa segue (x 4/3, < 0,1 %)", ok and rel(mpv["mass_kg"], mass304 * 40 / 30) < 1e-3, f"{mpv.get('mass_kg')}")
    d = await T(c, "list_equations", "2 equazioni, 1 variabile", check=lambda d: len(d["equations"]) == 2 and d["global_variables"] == {"lunghezza": 20.0})
    await T(c, "add_equation", "con variabile inesistente (rifiutata)", equation=f'"{dim}" = "nonesiste" * 2', expect_fail=True)
    await T(c, "add_equation", "con quota inesistente (rifiutata)", equation='"D1@Inesistente" = "lunghezza"', expect_fail=True)
    await T(c, "update_equation", "indice 1: x 3 -> 60 mm", index=1, equation=f'"{dim}" = "lunghezza" * 3', check=lambda d: d["equation"]["value"] == 60)
    await T(c, "evaluate_equations", "ricalcolo e verifica", check=lambda d: d["status"] in (0, 1) and not d["feature_errors"] and abs(d["volume_mm3"] - B * C * 60) < 1)
    await T(c, "delete_equation", "elimina l'equazione 1", index=1, check=lambda d: not d["feature_errors"])
    await T(c, "delete_global_variable", "elimina lunghezza", name="lunghezza")
    await T(c, "delete_global_variable", "variabile gia' eliminata", name="lunghezza", expect_fail=True)
    await T(c, "list_equations", "vuote", check=lambda d: d["equations"] == [])
    await T(c, "set_dimension_value", "ripristino profondita' 30", name=dim, value=A, check=lambda d: abs(d["volume_mm3"] - V_BLOCK) < 1)

    # ------------------------------------------------------------------ 5. configurazioni + foro
    print("\n== 5. Foro e configurazioni")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=6)
    await T(c, "extrude_cut", "foro d12 passante", end_condition="through_all_both", check=lambda d: True)
    ok, _, m = await c.call("get_mass_properties")
    v_hole = V_BLOCK - V_HOLE
    record("pezzo con foro: volume = blocco - pi*6^2*30", ok and rel(m["volume_mm3"], v_hole) < 1e-4, f"{m.get('volume_mm3')} atteso {v_hole:.2f}")
    await T(c, "list_part_configurations", "una sola configurazione", check=lambda d: d["active"] == "Default" and len(d["configurations"]) == 1)
    await T(c, "add_part_configuration", "Lunga (attiva)", name="Lunga", comment="profondita' 60", check=lambda d: d["active"] == "Lunga")
    await T(c, "add_part_configuration", "Lunga duplicata", name="Lunga", expect_fail=True)
    await T(c, "set_configuration_dimension", "profondita' 60 solo in Lunga", dimension=dim, value=60, configuration="Lunga",
            check=lambda d: abs(d["volume_active_mm3"] - (B * C * 60 - PI * 36 * 60)) < 2)
    await T(c, "activate_part_configuration", "torna a Default", name="Default", check=lambda d: abs(d["volume_mm3"] - v_hole) < 2)
    await T(c, "add_part_configuration", "Pieno (non attiva)", name="Pieno", activate=False, check=lambda d: d["active"] == "Default")
    await T(c, "set_configuration_suppression", "foro soppresso solo in Pieno", feature="Taglio-Estrusione1", suppressed=True, configuration="Pieno",
            check=lambda d: d["suppressed_by_configuration"] == {"Pieno": True})
    d = await T(c, "list_part_configurations", "volumi delle 3 configurazioni", include_volume=True, check=lambda d: len(d["configurations"]) == 3 and d["active"] == "Default")
    vols = {x["name"]: x.get("volume_mm3", 0) for x in d.get("configurations", [])}
    record("CONFIGURAZIONI: Default = blocco con foro (30 mm)", abs(vols.get("Default", 0) - v_hole) < 2, f"{vols.get('Default')} atteso {v_hole:.1f}")
    record("CONFIGURAZIONI: Lunga = 80x50x60 con foro", abs(vols.get("Lunga", 0) - (B * C * 60 - PI * 36 * 60)) < 2, f"{vols.get('Lunga')} atteso {B * C * 60 - PI * 36 * 60:.1f}")
    record("CONFIGURAZIONI: Pieno = blocco senza foro", abs(vols.get("Pieno", 0) - V_BLOCK) < 2, f"{vols.get('Pieno')} atteso {V_BLOCK}")
    record("CONFIGURAZIONI: tre volumi diversi", len(set(round(v) for v in vols.values())) == 3, str({k: round(v, 1) for k, v in vols.items()}))
    for n, vexp in (("Lunga", B * C * 60 - PI * 36 * 60), ("Pieno", V_BLOCK), ("Default", v_hole)):
        await T(c, "activate_part_configuration", f"attivazione {n}: volume {vexp:.1f}", name=n, check=lambda d, v=vexp: abs(d["volume_mm3"] - v) < 2)
    await T(c, "delete_part_configuration", "elimina Pieno", name="Pieno", check=lambda d: "Pieno" not in d["configurations"])
    await T(c, "delete_part_configuration", "elimina Lunga", name="Lunga", check=lambda d: d["configurations"] == ["Default"])
    await T(c, "delete_part_configuration", "unica configurazione", name="Default", expect_fail=True)
    await T(c, "save_document", "salva con foro", filepath=part)
    ok, _, m = await c.call("get_mass_properties")
    v_ref = m["volume_mm3"]
    record("volume di riferimento (Default, con foro)", rel(v_ref, v_hole) < 1e-4, f"{v_ref}")

    # ------------------------------------------------------------------ 6. export
    print("\n== 6. Export")
    ok, _, bb = await c.call("get_bounding_box")
    record("get_bounding_box = 30 x 80 x 50 (< 0,05 mm)", ok and all(abs(a - b) < 0.05 for a, b in zip(bb["size"], [A, B, C])), f"{bb.get('size')}")
    exp_files = {}
    for name, kw in (("stl_fine", {"quality": "fine"}), ("stl_coarse", {"quality": "coarse"}),
                     ("stl_ascii", {"binary": False}), ("stl_custom", {"quality": "custom", "deviation": 0.02, "angle": 5})):
        p = F("dx_" + name, "stl")
        rm(p)
        d = await T(c, "export_model", name, filepath=p, **kw,
                    check=lambda d: d["verify"]["triangles"] > 0 and all(abs(a - b) < 0.1 for a, b in zip(d["verify"]["bbox_size"], [A, B, C])))
        exp_files[name] = d.get("verify", {}).get("triangles", 0)
        if d:
            record(f"STL {name}: {d['verify']['triangles']} triangoli, box {d['verify']['bbox_size']} mm (modello {A}x{B}x{C}, diff < 0,1 mm)",
                   all(abs(a - b) < 0.1 for a, b in zip(d["verify"]["bbox_size"], [A, B, C])) and d.get("bbox_max_diff", 9) < 0.1,
                   f"codifica {d['verify'].get('encoding')}")
    record("STL: coarse ha meno triangoli di fine; custom (0,02 mm / 5 gradi) piu' di coarse",
           0 < exp_files.get("stl_coarse", 0) < exp_files.get("stl_fine", 0) and exp_files.get("stl_custom", 0) > exp_files.get("stl_coarse", 0), str(exp_files))
    p = F("dx_a", "3mf")
    rm(p)
    d = await T(c, "export_model", "3MF", filepath=p,
                check=lambda d: d["verify"]["triangles"] > 0 and d["verify"]["unit"] == "millimeter"
                and all(abs(a - b) < 0.1 for a, b in zip(d["verify"]["bbox_size"], [A, B, C])))
    p = F("dx_inch", "stl")
    rm(p)
    await T(c, "export_model", "STL in pollici (box/25,4)", filepath=p, units="inch",
            check=lambda d: all(abs(a - b / 25.4) < 0.005 for a, b in zip(d["verify"]["bbox_size"], [A, B, C])))
    for ap, proto in ((214, "AP214"), (203, "AP203")):
        p = F(f"dx_ap{ap}", "step")
        rm(p)
        await T(c, "export_model", f"STEP {proto}", filepath=p, step_ap=ap,
                check=lambda d, proto=proto: d["verify"]["manifold_solid_brep"] >= 1 and d["verify"]["application_protocol"] == proto)
    p = F("dx_ap242", "step")
    rm(p)
    d = await T(c, "export_model", "STEP AP242 (richiesto)", filepath=p, step_ap=242, check=lambda d: d["verify"]["manifold_solid_brep"] >= 1)
    record("STEP AP242: protocollo effettivo del file", bool(d), f"{d.get('verify', {}).get('application_protocol')} ({d.get('warning', 'AP242 ok')})"[:150])
    for ext in ("igs", "iges", "x_t", "x_b", "pdf", "eprt"):
        p = F("dx_b", ext if ext != "iges" else "igs")      # .iges viene scritto come .igs: va tolto il file del giro prima
        rm(p)
        d = await T(c, "export_model", ext, filepath=F("dx_b", ext), check=lambda d: d["size_bytes"] > 500)
    d = await T(c, "export_model", "PDF 3D contiene PRC", filepath=F("dx_b", "pdf"), check=lambda d: d["verify"]["has_3d"])
    d = await T(c, "inspect_export_file", "rilettura STL", filepath=F("dx_fine_check", "stl") if False else F("dx_stl_fine", "stl"),
                check=lambda d: d["triangles"] > 0)
    await T(c, "export_model", "formato sconosciuto", filepath=F("dx_x", "abc"), expect_fail=True)
    stp = F("dx_ap214", "step")
    txt = Path(stp).read_text(encoding="latin-1", errors="ignore") if Path(stp).exists() else ""
    record("STEP letto da disco: contiene MANIFOLD_SOLID_BREP e ADVANCED_FACE", "MANIFOLD_SOLID_BREP" in txt and "ADVANCED_FACE" in txt,
           f"{txt.count('ADVANCED_FACE')} facce")

    # ------------------------------------------------------------------ 7. import
    print("\n== 7. Import")
    for fname, tol in (("dx_ap214.step", 1e-3), ("dx_b.x_t", 1e-3), ("dx_b.igs", 1e-3), ("dx_stl_fine.stl", 1e-3)):
        path = str(OUT / fname)
        if not Path(path).exists():
            record(f"import_model {fname}", False, "file mancante")
            continue
        d = await T(c, "import_model", fname, filepath=path, check=lambda d: len(d["bodies"]) >= 1)
        if d:
            record(f"IMPORT {fname}: volume = originale (< 0,1 %)", rel(d["volume_mm3"], v_ref) < tol, f"{d['volume_mm3']} vs {v_ref} ({rel(d['volume_mm3'], v_ref) * 100:.5f} %)")
            bx = d.get("bbox_min_mm", [0] * 3), d.get("bbox_max_mm", [0] * 3)
            size = [round(bx[1][i] - bx[0][i], 3) for i in range(3)]
            record(f"IMPORT {fname}: box {size} = 30x80x50", all(abs(a - b) < 0.05 for a, b in zip(size, [A, B, C])), f"corpi {[b['name'] for b in d['bodies']]}")
        await c.call("close_document", discard=True)
        await c.call("activate_document", name="dx_blocco")
    await T(c, "import_model", "file inesistente", filepath=str(OUT / "non_esiste.step"), expect_fail=True)

    # ------------------------------------------------------------------ 8. misure
    print("\n== 8. Misure")
    ok, _, d0 = await c.call("get_document_info")
    d = await T(c, "measure_entities", "distanza fra le facce x=0 e x=30", entity1={"face": [0, 30, 15]}, entity2={"face": [30, 30, 15]},
                check=lambda d: abs(d["distance"] - 30) < 1e-3 and d["parallel"])
    d = await T(c, "measure_entities", "angolo fra faccia x=0 e faccia y=40", entity1={"face": [0, 30, 15]}, entity2={"face": [15, 40, 10]},
                check=lambda d: abs(d["angle_deg"] - 90) < 1e-3)
    d = await T(c, "measure_entities", "distanza fra le facce y=-40 e y=40", entity1={"face": [15, -40, 10]}, entity2={"face": [15, 40, 10]},
                check=lambda d: abs(d["distance"] - 80) < 1e-3)
    d = await T(c, "measure_entities", "diametro del foro", entity1={"face": [15, 6, 0]}, check=lambda d: abs(d["diameter"] - 12) < 1e-3)
    d = await T(c, "measure_entities", "distanza fra due vertici", entity1={"vertex": [0, -40, -25]}, entity2={"vertex": [30, 40, 25]},
                check=lambda d: abs(d["distance"] - math.sqrt(A ** 2 + B ** 2 + C ** 2)) < 1e-3)
    await T(c, "measure_entities", "punto non su una faccia", entity1={"face": [100, 100, 100]}, expect_fail=True)
    await T(c, "measure_face", "faccia cilindrica del foro", x=15, y=6, z=0,
            check=lambda d: d["type"] == "cylinder" and abs(d["diameter"] - 12) < 1e-3 and abs(d["radius"] - 6) < 1e-3
            and abs(abs(d["axis_direction"][0]) - 1) < 1e-6 and abs(d["area_mm2"] - PI * 12 * 30) < 0.05)
    await T(c, "measure_face", "faccia piana x=30 (area 80x50 - foro)", x=30, y=30, z=15,
            check=lambda d: d["type"] == "plane" and abs(d["area_mm2"] - (B * C - PI * 36)) < 0.05)
    await T(c, "get_bounding_box", "box del pezzo", check=lambda d: all(abs(a - b) < 0.05 for a, b in zip(d["size"], [A, B, C]))
            and abs(d["min"][0]) < 0.05 and abs(d["max"][0] - A) < 0.05)

    # ------------------------------------------------------------------ 9. cartiglio con il materiale
    print("\n== 9. Cartiglio del disegno con il materiale")
    drw = F("dx_blocco_tav", "SLDDRW")
    rm(drw, F("dx_blocco_tav", "dxf"))
    await T(c, "assign_material", "AISI 304 (collegato al cartiglio)", material="AISI 304", check=lambda d: d["title_block_link"])
    await T(c, "save_document", "salva il pezzo", filepath=part)
    ok, text, d = await c.call("create_drawing", model_path=part, paper_size="A4", orientation="landscape", save_as=drw)
    record("create_drawing del blocco", ok and d.get("still_missing") == [], text[:100])
    await c.call("add_standard_views", views=["front", "isometric"])
    ok, text, d = await c.call("export_drawing", filepath=F("dx_blocco_tav", "dxf"))
    txt = Path(F("dx_blocco_tav", "dxf")).read_text(encoding="latin-1", errors="ignore") if Path(F("dx_blocco_tav", "dxf")).exists() else ""
    record("CARTIGLIO: il materiale 'AISI 304' compare nel DXF", ok and "AISI 304" in txt, f"{txt.count('AISI 304')} occorrenze")
    record("CARTIGLIO: nessun 'ERRORE' nel testo DXF", len(txt) > 1000 and "ERROR" not in txt, f"{txt.count('ERROR')} occorrenze")
    await c.call("close_document", discard=True)       # disegno
    await c.call("activate_document", name="dx_blocco")
    # cambio materiale: il cartiglio segue
    await T(c, "assign_material", "Lega 6061", material="Lega 6061")
    await T(c, "save_document", "salva", filepath=part)
    ok, text, d = await c.call("create_drawing", model_path=part, paper_size="A4", orientation="landscape", save_as=drw)
    await c.call("add_standard_views", views=["front"])
    rm(F("dx_blocco_tav2", "dxf"))
    ok, text, d = await c.call("export_drawing", filepath=F("dx_blocco_tav2", "dxf"))
    txt = Path(F("dx_blocco_tav2", "dxf")).read_text(encoding="latin-1", errors="ignore") if Path(F("dx_blocco_tav2", "dxf")).exists() else ""
    record("CARTIGLIO: dopo il cambio compare 'Lega 6061' e non piu' 'AISI 304'", ok and L("Lega 6061") in txt and "AISI 304" not in txt and "ERROR" not in txt,
           f"6061 x{txt.count(L('Lega 6061'))}, 304 x{txt.count('AISI 304')}")
    await c.call("close_document", discard=True)
    await c.call("activate_document", name="dx_blocco")
    await T(c, "assign_material", "AISI 304 (finale)", material="AISI 304")

    # ------------------------------------------------------------------ 10. immagini
    print("\n== 10. Immagini")
    await T(c, "create_reference_plane", "Piano1 a 60 mm (deve restare nascosto nelle immagini)", mode="offset", base="front", distance=60)
    imgs = {}
    for name, kw in (("ref_visibile", {"hide_reference": False, "white_background": True, "width": 900, "height": 600}),
                     ("iso_nascosta", {"hide_reference": True, "white_background": True, "width": 900, "height": 600}),
                     ("dopo_ripristino", {"hide_reference": False, "white_background": True, "width": 900, "height": 600}),
                     ("front_hl", {"hide_reference": True, "white_background": True, "view": "front", "style": "hidden_lines", "width": 800, "height": 600}),
                     ("top_wire", {"hide_reference": True, "white_background": True, "view": "top", "style": "wireframe", "width": 800, "height": 600}),
                     ("iso_ombra", {"hide_reference": True, "style": "shaded", "width": 900, "height": 600})):
        p = F("dx_img_" + name, "png")
        rm(p)
        d = await T(c, "export_model_image", name, filepath=p, **kw,
                    check=lambda d, kw=kw: d.get("width") == kw["width"] and d.get("height") == kw["height"])
        if Path(p).exists():
            imgs[name] = blue_pixels(p)
    record("IMMAGINE con piani visibili: il Piano1 si vede (controllo del test)", imgs.get("ref_visibile", (0,))[0] > 50, f"{imgs.get('ref_visibile', (0,))[0]} pixel azzurri")
    for name in ("iso_nascosta", "front_hl", "top_wire", "iso_ombra"):
        n = imgs.get(name, (999,))[0]
        record(f"IMMAGINE {name}: nessun piano/riferimento visibile (0 pixel azzurri)", n == 0, f"{n} pixel azzurri, {imgs.get(name, (0, 0))[1]}")
    record("IMMAGINE dopo l'export: i piani sono ripristinati (di nuovo visibili)", imgs.get("dopo_ripristino", (0,))[0] > 50, f"{imgs.get('dopo_ripristino', (0,))[0]} pixel")
    record("IMMAGINE sfondo bianco", imgs.get("iso_nascosta", (0, 0, (0, 0, 0)))[2] == (255, 255, 255), str(imgs.get("iso_nascosta", (0, 0, None))[2]))
    record("IMMAGINE risoluzione 900x600 e 800x600", imgs.get("iso_nascosta", (0, (0, 0)))[1] == (900, 600) and imgs.get("front_hl", (0, (0, 0)))[1] == (800, 600),
           f"{imgs.get('iso_nascosta', (0, 0))[1]} {imgs.get('front_hl', (0, 0))[1]}")
    d = await T(c, "export_model_image", "stile non valido", filepath=F("dx_img_x", "png"), style="boh", expect_fail=True)
    d = await T(c, "export_model_image", "nativo JPG", filepath=F("dx_img_nativa", "jpg"), check=lambda d: True)
    record("export_model_image nativo: file JPG scritto", Path(F("dx_img_nativa", "jpg")).exists() and Path(F("dx_img_nativa", "jpg")).stat().st_size > 5000, "")

    await c.call("save_document", filepath=part)

    # ------------------------------------------------------------------ 11. D5: hide_reference nei componenti di un assieme
    print("\n== 11. D5 riferimenti dei componenti")
    await T(c, "create_new_assembly", "assieme con il blocco (Piano1 visibile nel pezzo)")
    await T(c, "insert_component", "blocco nell'assieme", file_path=part)
    # nel modello d'assieme la visualizzazione dei piani (swDisplayPlanes = 5) e' spenta: la si accende per vedere il Piano1 del componente
    ok, text, _ = await c.call("execute_python", code="d = sw.ActiveDoc\nd.Extension.SetUserPreferenceToggle(5, 0, True)\n"
                                                    "d.Extension.SetUserPreferenceToggle(198, 0, False)\nd.GraphicsRedraw2()")
    record("D5: piani visualizzati nell'assieme (impostazione del test)", ok, text[:80])
    imgs = {}
    for name, hide in (("asm_ref_visibile", False), ("asm_nascosta", True), ("asm_dopo", False)):
        p = F("dx_img_" + name, "png")
        rm(p)
        await T(c, "export_model_image", name, filepath=p, hide_reference=hide, white_background=True, width=900, height=600)
        if Path(p).exists():
            imgs[name] = blue_pixels(p)[0]
    record("D5: senza hide_reference il piano del componente si vede (> 50 pixel azzurri)", imgs.get("asm_ref_visibile", 0) > 50, str(imgs))
    record("D5: con hide_reference nessun riferimento dei componenti (0 pixel azzurri)", imgs.get("asm_nascosta", -1) == 0, str(imgs))
    record("D5: dopo l'export il piano del componente e' di nuovo visibile (> 50)", imgs.get("asm_dopo", 0) > 50, str(imgs))
    await c.call("close_document", discard=True)


if __name__ == "__main__":
    done = asyncio.run(run())
    print("\n==== RIEPILOGO ====")
    for tool, res, note in RESULTS:
        print(f"{res:5} {tool:90} {note}"[:250])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
