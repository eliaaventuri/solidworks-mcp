"""
Test live del GRUPPO C (assiemi, limiti C1-C7) tramite il server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente non viene mai toccata;
alla fine si chiude solo il PID lanciato dal test. Tutto si costruisce con i tool MCP; i file stanno in test_output/ (prefisso cx_).

  C1 selezione per coordinate dentro i sotto-assiemi a piu' livelli (accoppiamento primo livello <-> pezzo annidato 2 livelli,
     verifica con la trasformazione composta calcolata dal test)
  C2 specchiatura: nuovo pezzo speculare (volume, baricentro riflesso, orientamento), istanze con i 4 orientamenti, protezione overwrite
  C3 esplosione: vettore libero, direzione di un'entita' inclinata, radiale con rotazione (posizioni e angoli misurati)
  C4 esplosione automatica: nativa (AutoExplode) ed euristica dagli accoppiamenti (nessuna sovrapposizione dei box nello stato esploso)
  C5 accoppiamenti avanzati: limite distanza, limite angolo, larghezza, simmetrico, tangente, blocco, ingranaggio, vite
  C6 delete_mate: gradi di liberta' prima/dopo, anche per i componenti a catena
  C7 move_component su componente parzialmente vincolato (perno con solo il concentrico; asse inclinato)

Uso:  .venv\\Scripts\\python.exe tests\\test_assembly_extra_live.py [C1 C2 ...]      (CX_REUSE=1: non ricostruisce i pezzi)
"""

import os
import sys
import math
import asyncio
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup
PI = math.pi
TOL = 2e-3             # mm
RESULTS = []


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:240])


def F(name, ext="SLDPRT"):
    return str(OUT / f"{name}.{ext}")


def rm(*paths):
    for p in paths:
        try:
            Path(p).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


async def need(c, tool, label, **args):
    ok, text, d = await c.call(tool, **args)
    record(f"{tool}: {label}", ok, text.split("\n")[0][:150])
    return d if ok else {}


async def attempt(c, tool, **args):
    """Chiama un tool senza registrare (per le azioni di preparazione). -> (ok, testo, dati)"""
    return await c.call(tool, **args)


def close(a, b, tol=TOL):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def Rx(deg):
    a = math.radians(deg)
    return [[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]]


def mv(M, v):
    return [sum(M[i][k] * v[k] for k in range(3)) for i in range(3)]


def vadd(a, b):
    return [x + y for x, y in zip(a, b)]


def tf_to_M(t):
    """'transform' di list_components (9 righe = immagini degli assi + 3 traslazioni in m) -> (M colonna, t in mm)."""
    M = [[t[0], t[3], t[6]], [t[1], t[4], t[7]], [t[2], t[5], t[8]]]
    return M, [t[9] * 1000, t[10] * 1000, t[11] * 1000]


def rot_angle_deg(M):
    c = max(-1.0, min(1.0, (M[0][0] + M[1][1] + M[2][2] - 1) / 2))
    return math.degrees(math.acos(c))


def det3(M):
    return (M[0][0] * (M[1][1] * M[2][2] - M[1][2] * M[2][1]) - M[0][1] * (M[1][0] * M[2][2] - M[1][2] * M[2][0])
            + M[0][2] * (M[1][0] * M[2][1] - M[1][1] * M[2][0]))


class Asm:
    def __init__(self, c):
        self.c = c

    async def comps(self, top=True):
        ok, _, d = await self.c.call("list_components", top_level_only=top)
        return {x["name"]: x for x in d.get("components", [])} if ok else {}

    async def pos(self, name, top=True):
        x = (await self.comps(top)).get(name)
        return x["position_mm"] if x else None

    async def pose(self, name, top=True):
        x = (await self.comps(top)).get(name)
        return tf_to_M(x["transform"]) if x else (None, None)

    async def world(self, name, p, top=True):
        M, t = await self.pose(name, top)
        return vadd(mv(M, p), t)


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
                tools = (await session.list_tools()).tools
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
async def part(c, name, builder):
    """Costruisce e salva un pezzo con i tool MCP (cx_<name>.SLDPRT)."""
    path = F("cx_" + name)
    if os.environ.get("CX_REUSE") and os.path.exists(path):
        return
    rm(path)
    await c.call("create_new_part")
    await builder()
    ok, text, _ = await c.call("save_document", filepath=path)
    if not ok:
        record(f"pezzo cx_{name}", False, text.split("\n")[0][:150])
    await c.call("close_document", discard=True)


async def cyl(c, r, length):
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=r)
    await c.call("extrude_boss", depth=length)


async def rect(c, y1, z1, y2, z2, length):
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=y1, y1=z1, x2=y2, y2=z2)
    await c.call("extrude_boss", depth=length)


async def hole(c, y, z, r):
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=y, y=z, radius=r)
    await c.call("extrude_cut", end_condition="through_all_both")


async def build_parts(c):
    print("\n== 0. Pezzi (tool di modellazione)")
    # piano Front di questo template: normale +X, schizzo (u,v) = (Y,Z); le estrusioni vanno verso +X

    async def blocco():          # 40x20x15 (x 0..15) + sporgenza d6 x5 decentrata (y=10): pezzo CHIRALE
        await rect(c, -20, -10, 20, 10, 15)
        await c.call("create_sketch_on_face", x=15, y=0, z=0)
        await c.call("draw_circle", x=10, y=0, radius=3)
        await c.call("extrude_boss", depth=5)

    async def base():            # piastra 80x80x10 con foro d12
        await rect(c, -40, -40, 40, 40, 10)
        await hole(c, 0, 0, 6)

    async def base2():           # piastra con foro d20 e 4 fori d4 su r=30
        await rect(c, -40, -40, 40, 40, 10)
        await hole(c, 0, 0, 10)
        await c.call("create_sketch", plane="Front")
        for (y, z) in ((30, 0), (0, 30), (-30, 0), (0, -30)):
            await c.call("draw_circle", x=y, y=z, radius=2)
        await c.call("extrude_cut", end_condition="through_all_both")

    async def bush():            # flangia d28 x3 + tubo d20 x10 (x 3..13), foro d12
        await cyl(c, 14, 3)
        await c.call("create_sketch_on_face", x=3, y=0, z=0)
        await c.call("draw_circle", x=0, y=0, radius=10)
        await c.call("extrude_boss", depth=10)
        await hole(c, 0, 0, 6)

    async def pin():             # testa d16 x4 + gambo d10 x36
        await cyl(c, 8, 4)
        await c.call("create_sketch_on_face", x=4, y=0, z=0)
        await c.call("draw_circle", x=0, y=0, radius=5)
        await c.call("extrude_boss", depth=36)

    async def screw():           # testa d7 x3 + gambo d4 x12
        await cyl(c, 3.5, 3)
        await c.call("create_sketch_on_face", x=3, y=0, z=0)
        await c.call("draw_circle", x=0, y=0, radius=2)
        await c.call("extrude_boss", depth=12)

    async def flap():
        await rect(c, -30, -10, 30, 10, 5)
        await hole(c, -20, 0, 5)

    async def gear():
        await cyl(c, 20, 10)
        await hole(c, 0, 0, 5)

    async def gear_s():
        await cyl(c, 10, 10)
        await hole(c, 0, 0, 5)

    async def slot():            # piastra con finestra passante lungo X: y -10..20, z -10..10
        await rect(c, -40, -20, 40, 20, 30)
        await c.call("create_sketch", plane="Front")
        await c.call("draw_rectangle", x1=-10, y1=-10, x2=20, y2=10)
        await c.call("extrude_cut", end_condition="through_all_both")

    async def tab():
        await rect(c, -10, -5, 10, 5, 15)

    await part(c, "blocco", blocco)
    await part(c, "perno", lambda: cyl(c, 5, 40))
    await part(c, "base", base)
    await part(c, "base2", base2)
    await part(c, "bush", bush)
    await part(c, "pin", pin)
    await part(c, "screw", screw)
    await part(c, "flap", flap)
    await part(c, "gear", gear)
    await part(c, "gear_s", gear_s)
    await part(c, "slot", slot)
    await part(c, "tab", tab)
    # controllo dei volumi di partenza (misurati con get_mass_properties su ogni file)
    exp = {"blocco": 40 * 20 * 15 + PI * 9 * 5, "perno": PI * 25 * 40, "base": 6400 - PI * 36 * 10 + 0 - 0,
           "base2": 64000 - PI * 100 * 10 - 4 * PI * 4 * 10, "bush": PI * (196 - 36) * 3 + PI * (100 - 36) * 10,
           "pin": PI * (64 * 4 + 25 * 36), "screw": PI * (12.25 * 3 + 4 * 12), "flap": 60 * 20 * 5 - PI * 25 * 5,
           "gear": PI * (400 - 25) * 10, "gear_s": PI * (100 - 25) * 10, "slot": 80 * 40 * 30 - 30 * 20 * 30, "tab": 20 * 10 * 15}
    exp["base"] = 80 * 80 * 10 - PI * 36 * 10
    for n, v in exp.items():
        ok, _, _ = await c.call("open_document", filepath=F("cx_" + n))
        ok2, _, m = await c.call("get_mass_properties")
        vol = m.get("volume_mm3", 0)
        record(f"pezzo cx_{n}: volume = formula", ok and ok2 and abs(vol - v) < max(0.5, v * 5e-5), f"{vol:.3f} vs {v:.3f}")
        await c.call("close_document", discard=True)


# ============================================================================================ C1
async def c1_sotto_assiemi(c):
    print("\n== C1. Selezione per coordinate dentro i sotto-assiemi")
    A = Asm(c)
    for n in ("cx_sub", "cx_sub2", "cx_top"):
        rm(F(n, "SLDASM"))
    # --- livello 0: sotto-assieme cx_sub = base (fissa) + perno (concentrico + testa sulla faccia posteriore)
    await need(c, "create_new_assembly", "cx_sub")
    await need(c, "insert_component", "base fissa", file_path=F("cx_base"), x=0, y=0, z=0, fixed=True)
    await need(c, "insert_component", "perno", file_path=F("cx_perno"), x=100, y=30, z=0)
    await need(c, "add_mate", "concentrico perno-foro", mate_type="concentric", entity1={"component": "cx_perno-1", "face": [120, 35, 0]},
               entity2={"component": "cx_base-1", "face": [5, 6, 0]})
    await need(c, "add_mate", "faccia terminale del perno coincidente con la faccia posteriore della base", mate_type="coincident",
               entity1={"component": "cx_perno-1", "face": [100, 2, 0]}, entity2={"component": "cx_base-1", "face": [10, 20, 0]},
               align="anti_aligned")
    p_in = await A.pos("cx_perno-1")
    record("sotto-assieme: perno a (10,0,0) dopo i vincoli", close(p_in, [10, 0, 0]), f"{p_in}")
    await need(c, "save_document", "salva cx_sub", filepath=F("cx_sub", "SLDASM"))
    await c.call("close_document", discard=True)
    # --- livello 1: cx_sub2 contiene cx_sub (traslato e ruotato di 30 gradi attorno a X)
    await need(c, "create_new_assembly", "cx_sub2")
    await need(c, "insert_component", "cx_sub in cx_sub2 (0,15,0) rot 30", file_path=F("cx_sub", "SLDASM"), x=0, y=15, z=0,
               rotation=[30, 0, 0], fixed=True)
    await need(c, "save_document", "salva cx_sub2", filepath=F("cx_sub2", "SLDASM"))
    await c.call("close_document", discard=True)
    # --- livello 2 (assieme principale): cx_sub2 traslato e ruotato di 60 gradi + un blocco di primo livello
    await need(c, "create_new_assembly", "cx_top")
    await need(c, "insert_component", "cx_sub2 in cx_top (200,50,20) rot 60", file_path=F("cx_sub2", "SLDASM"), x=200, y=50, z=20,
               rotation=[60, 0, 0], fixed=True)
    await need(c, "insert_component", "blocco di primo livello", file_path=F("cx_blocco"), x=400, y=0, z=0)
    # trasformazione composta calcolata QUI (indipendente dall'API): mondo = R60 ( R30 p_perno + (0,15,0) ) + (200,50,20)
    R30, R60, R90 = Rx(30), Rx(60), Rx(90)
    org = vadd(mv(R60, vadd(mv(R30, p_in), [0, 15, 0])), [200, 50, 20])
    nested = "cx_sub2-1/cx_sub-1/cx_perno-1"
    allc = await A.comps(top=False)
    record("list_components(top_level_only=false) elenca il perno annidato", nested in allc, f"{sorted(allc)}")
    got = allc.get(nested, {}).get("position_mm")
    record("perno annidato: origine = trasformazione composta calcolata (2 livelli)", got is not None and close(got, org), f"{got} vs {[round(v, 4) for v in org]}")
    Mg = tf_to_M(allc[nested]["transform"])[0] if nested in allc else None
    record("perno annidato: rotazione = R90 (composizione di 30 e 60 gradi)", Mg is not None and all(abs(Mg[i][j] - R90[i][j]) < 1e-6 for i in range(3) for j in range(3)))
    # --- accoppiamento 1: faccia x=0 del blocco (primo livello) coincidente con la faccia terminale del perno (2 livelli sotto)
    p_end = vadd(mv(R90, [40, 2, 0]), org)
    d = await need(c, "add_mate", "coincidente: blocco (primo livello) - faccia terminale del perno annidato", mate_type="coincident",
                   entity1={"component": "cx_blocco-1", "face": [400, 0, 5]}, entity2={"component": "cx_perno-1", "face": p_end},
                   align="anti_aligned")
    comps = d.get("components", [])
    record("il mate collega blocco e perno annidato", "cx_blocco-1" in comps and nested in comps, f"{comps}")
    pb = await A.pos("cx_blocco-1")
    record("blocco: origine X = faccia terminale del perno (210+40 = 250)", abs(pb[0] - (org[0] + 40)) < TOL, f"{pb}")
    # --- accoppiamento 2: sporgenza cilindrica del blocco concentrica con il perno annidato
    Mb, tb = await A.pose("cx_blocco-1")
    p_boss = vadd(mv(Mb, [17.5, 10, 3]), tb)
    p_cyl = vadd(mv(R90, [20, 5, 0]), org)
    d = await need(c, "add_mate", "concentrico: sporgenza del blocco - perno annidato", mate_type="concentric",
                   entity1={"component": "cx_blocco-1", "face": p_boss}, entity2={"component": "cx_perno-1", "face": p_cyl})
    pb = await A.pos("cx_blocco-1")
    Mb, tb = await A.pose("cx_blocco-1")
    axis_pt = vadd(mv(Mb, [0, 10, 0]), tb)       # punto dell'asse della sporgenza (locale y=10, z=0)
    record("asse della sporgenza = asse del perno annidato (Y e Z)", abs(axis_pt[1] - org[1]) < TOL and abs(axis_pt[2] - org[2]) < TOL,
           f"asse blocco ({axis_pt[1]:.4f},{axis_pt[2]:.4f}) vs perno ({org[1]:.4f},{org[2]:.4f})")
    record("origine del blocco = (250, y_perno-10, z_perno)", close(pb, [org[0] + 40, org[1] - 10, org[2]]), f"{pb}")
    record("blocco: nessuna rotazione (matrice identita')", all(abs(Mb[i][j] - (1 if i == j else 0)) < 1e-6 for i in range(3) for j in range(3)))
    # --- selezione di un'entita' di un pezzo annidato anche per check_clearance (stesso selettore)
    d = await need(c, "check_clearance", "gioco fra blocco e perno annidato (toccano la faccia: 0)", entity1="cx_blocco-1", entity2=nested)
    record("check_clearance: componente annidato selezionabile per nome", d.get("distance_mm", 99) < 1e-3, f"{d.get('distance_mm')}")
    await c.call("close_document", discard=True)


# ============================================================================================ C2
async def c2_specchiatura(c):
    print("\n== C2. Specchiatura con pezzo speculare")
    A = Asm(c)
    for s in ("_sx", "_sx2"):
        rm(F("cx_blocco" + s))
    vol = 40 * 20 * 15 + PI * 9 * 5
    com_loc = [(12000 * 7.5 + PI * 9 * 5 * 17.5) / vol, (PI * 9 * 5 * 10) / vol, 0.0]      # baricentro nel pezzo (formula)
    await need(c, "create_new_assembly", "specchiatura")
    await need(c, "insert_component", "blocco a y=60 (fisso)", file_path=F("cx_blocco"), x=0, y=60, z=0, fixed=True)
    # --- versione opposta
    d = await need(c, "mirror_components", "versione opposta rispetto al Piano destro", components=["cx_blocco-1"], plane="Piano destro",
                   opposite_hand=True, name_suffix="_sx")
    row = (d.get("mirrored") or [{}])[0]
    record("nuovo pezzo salvato in test_output (cx_blocco_sx.SLDPRT)", bool(row.get("file")) and os.path.exists(row["file"])
           and os.path.basename(row["file"]).lower() == "cx_blocco_sx.sldprt" and Path(row["file"]).resolve().parent == OUT.resolve(), f"{row.get('file')}")
    record("volume del pezzo speculare = volume dell'originale", abs(row.get("volume_mm3", 0) - vol) < 1e-2, f"{row.get('volume_mm3')} vs {vol:.4f}")
    # baricentro: originale nel mondo = (com_loc) + (0,60,0); speculare = riflesso rispetto al piano y=0
    exp_com = [com_loc[0], -(com_loc[1] + 60), com_loc[2]]
    record("baricentro del pezzo speculare = riflesso del baricentro originale (piano y=0)", close(row.get("center_of_mass_assembly_mm", [9e9] * 3), exp_com, 2e-3),
           f"{row.get('center_of_mass_assembly_mm')} vs {[round(v, 4) for v in exp_com]}")
    # il pezzo e' davvero speculare (non solo ruotato): baricentro nel SUO sistema con la X cambiata di segno, Y uguale
    cm = row.get("center_of_mass_part_mm", [0, 0, 0])
    record("geometria riflessa nel pezzo: baricentro locale (-x, +y, z) dell'originale", close(cm, [-com_loc[0], com_loc[1], com_loc[2]], 2e-3), f"{cm}")
    new = d.get("new_components", [None])[0]
    Mn, tn = await A.pose(new) if new else (None, None)
    if Mn is not None:
        cw = vadd(mv(Mn, cm), tn)
        record("baricentro riletto dalla posa finale (list_components) = riflesso", close(cw, exp_com, 2e-3), f"{[round(v, 4) for v in cw]}")
    record("posa del nuovo componente: rotazione propria (det=+1), origine y = -60", Mn is not None and abs(det3(Mn) - 1) < 1e-6 and abs(tn[1] + 60) < TOL,
           f"det={det3(Mn) if Mn else None}, t={tn}")
    pl = row.get("placement", {})
    record("posizionamento esatto: aligned=true (asse riflesso del pezzo = x)", pl.get("aligned") is True and pl.get("mirrored_part_axis") == "x",
           f"{ {k: pl.get(k) for k in ('aligned', 'mirrored_part_axis', 'feature_dissolved', 'initial_rotation_deg', 'rotation_deg')} }")
    # --- secondo piano di specchio (Piano frontale, normale X): il baricentro si riflette in X
    rm(F("cx_blocco_fx"))
    d3 = await need(c, "mirror_components", "versione opposta rispetto al Piano frontale (normale X)", components=["cx_blocco-1"], plane="Piano frontale",
                    opposite_hand=True, name_suffix="_fx")
    row3 = (d3.get("mirrored") or [{}])[0]
    exp3 = [-com_loc[0], com_loc[1] + 60, com_loc[2]]
    record("piano X: baricentro del pezzo speculare = riflesso in X", close(row3.get("center_of_mass_assembly_mm", [9e9] * 3), exp3, 2e-3),
           f"{row3.get('center_of_mass_assembly_mm')} vs {[round(v, 4) for v in exp3]}")
    record("piano X: volume uguale e posizionamento esatto", abs(row3.get("volume_mm3", 0) - vol) < 1e-2 and row3.get("placement", {}).get("aligned") is True,
           f"{row3.get('volume_mm3')} {row3.get('placement', {}).get('mirrored_part_axis')}")
    for n3 in d3.get("new_components", []):
        await c.call("delete_component", component=n3)
    # --- non sovrascrive senza overwrite
    ok, text, d2 = await c.call("mirror_components", components=["cx_blocco-1"], plane="Piano destro", opposite_hand=True, name_suffix="_sx")
    record("secondo specchio con lo stesso nome: rifiutato (file esiste)", (not ok) and d2.get("refused") == "file_exists", text.split("\n")[0][:120])
    ok, text, d2 = await c.call("mirror_components", components=["cx_blocco-1"], plane="Piano destro", opposite_hand=True, name_suffix="_sx", overwrite=True)
    record("overwrite=true ma il file e' gia' un componente aperto: rifiutato (file in uso)", (not ok) and d2.get("refused") == "file_in_use", text.split("\n")[0][:120])
    ok, text, d2 = await c.call("mirror_components", components=["cx_blocco-1"], plane="Piano destro", opposite_hand=True, name_suffix="_sx2")
    record("nome nuovo: crea un secondo pezzo speculare", ok, text.split("\n")[0][:100])
    for n in ((d2.get("new_components") or []) + [new]):
        if n:
            await c.call("delete_component", component=n)
    # --- orientamento delle ISTANZE (stesso file, nessun nuovo pezzo)
    table = {0: ([[1, 0, 0], [0, -1, 0], [0, 0, -1]], [0, -60, 0]), 1: ([[-1, 0, 0], [0, -1, 0], [0, 0, 1]], [20, -60, 0]),
             2: ([[1, 0, 0], [0, 1, 0], [0, 0, 1]], [0, -60, 0]), 3: ([[-1, 0, 0], [0, 1, 0], [0, 0, -1]], [20, -60, 0])}
    for o in range(4):
        d = await need(c, "mirror_components", f"istanza orientamento {o}", components=["cx_blocco-1"], plane="Piano destro", orientation=o)
        n = (d.get("new_components") or [None])[0]
        M, t = await A.pose(n) if n else (None, None)
        Me, te = table[o]
        ok = M is not None and all(abs(M[i][j] - Me[i][j]) < 1e-6 for i in range(3) for j in range(3)) and close(t, te)
        record(f"orientamento {o}: rotazione e origine come misurato (det=+1, y=-60)", ok and abs(det3(M) - 1) < 1e-6, f"t={t}, diag={[M[i][i] for i in range(3)] if M else None}")
        if M is not None:
            com_w = vadd(mv(M, com_loc), t)
            record(f"orientamento {o}: baricentro dell'istanza = R*com+t, y = {'riflessa' if o == 0 else 'comunque nel semispazio y<0'}",
                   (close(com_w, exp_com, 2e-3) if o == 0 else com_w[1] < 0), f"{[round(v, 4) for v in com_w]}")
        if n:
            await c.call("delete_component", component=n)
    # il solo orientamento 0 riflette esattamente il baricentro (blocco simmetrico in Z)
    await c.call("close_document", discard=True)


# ============================================================================================ C3 / C4
async def build_exp(c, name):
    """Assieme di prova: base (fissa, foro d20 + 4 fori d4), boccola, perno, 4 viti. Tutti gli accoppiamenti si creano con add_mate."""
    await need(c, "create_new_assembly", f"{name}")
    await c.call("insert_component", file_path=F("cx_base2"), x=0, y=0, z=0, fixed=True)
    await c.call("insert_component", file_path=F("cx_bush"), x=-3, y=0, z=0)
    await c.call("insert_component", file_path=F("cx_pin"), x=-7, y=0, z=0)
    sc = [(30, 0), (0, 30), (-30, 0), (0, -30)]
    for (y, z) in sc:
        await c.call("insert_component", file_path=F("cx_screw"), x=-3, y=y, z=z)
    n_ok = 0
    n_ok += (await c.call("add_mate", mate_type="concentric", entity1={"component": "cx_bush-1", "face": [5, 10, 0]},
                          entity2={"component": "cx_base2-1", "face": [5, 10, 0]}))[0]
    n_ok += (await c.call("add_mate", mate_type="coincident", entity1={"component": "cx_bush-1", "face": [0, 12, 0]},
                          entity2={"component": "cx_base2-1", "face": [0, 20, 0]}, align="anti_aligned"))[0]
    n_ok += (await c.call("add_mate", mate_type="concentric", entity1={"component": "cx_pin-1", "face": [10, 5, 0]},
                          entity2={"component": "cx_bush-1", "face": [5, 6, 0]}))[0]
    n_ok += (await c.call("add_mate", mate_type="coincident", entity1={"component": "cx_pin-1", "face": [-3, 6.5, 0]},
                          entity2={"component": "cx_bush-1", "face": [-3, 12, 0]}, align="anti_aligned"))[0]
    for i, (y, z) in enumerate(sc, 1):
        nm = f"cx_screw-{i}"
        n_ok += (await c.call("add_mate", mate_type="concentric", entity1={"component": nm, "face": [6, y + 2, z]},
                              entity2={"component": "cx_base2-1", "face": [5, y + 2, z]}))[0]
        n_ok += (await c.call("add_mate", mate_type="coincident", entity1={"component": nm, "face": [0, y + 3, z]},
                              entity2={"component": "cx_base2-1", "face": [0, 20, 20]}, align="anti_aligned"))[0]
    record(f"{name}: 12 accoppiamenti creati (boccola, perno, 4 viti)", n_ok == 12, f"{n_ok}/12")
    return {"screws": [f"cx_screw-{i}" for i in range(1, 5)]}


def box_sep_mm(a, b):
    """Distanza di separazione fra due box [x0,y0,z0,x1,y1,z1] (mm): massima separazione su un asse (negativa = si sovrappongono)."""
    return max(max(a[k] - b[k + 3], b[k] - a[k + 3]) for k in range(3))


async def c3_esplosione_libera(c):
    print("\n== C3. Esplosione: direzione libera, entita' inclinata, radiale con rotazione")
    A = Asm(c)
    await build_exp(c, "esplosione C3")
    await need(c, "insert_component", "perno di riferimento inclinato di 30 gradi attorno a Z", file_path=F("cx_perno"), x=200, y=0, z=0, rotation=[0, 0, 30])
    orig = await A.comps()
    P0 = {n: x["position_mm"] for n, x in orig.items()}
    a30 = math.radians(30)
    pt_cyl = [200 + 20 * math.cos(a30) - 5 * math.sin(a30), 20 * math.sin(a30) + 5 * math.cos(a30), 0]
    axis = [math.cos(a30), math.sin(a30), 0]
    steps = [
        {"components": ["cx_screw-1"], "direction": [1, 1, 0], "distance": 50},
        {"components": ["cx_bush-1"], "direction": {"component": "cx_perno-1", "face": pt_cyl}, "distance": 40},
        {"components": ["cx_screw-2", "cx_screw-3", "cx_screw-4"], "radial_axis": {"component": "cx_base2-1", "face": [5, 10, 0]},
         "distance": 30, "angle": 30},
        {"components": ["cx_pin-1"], "direction": "-x", "distance": 20, "rotate_angle": 45, "rotate_axis": "x"},
    ]
    d = await need(c, "create_exploded_view", "4 passi: vettore libero, entita' inclinata, radiale con rotazione, traslazione con rotazione", steps=steps)
    poses = d.get("poses", {})
    sts = d.get("steps", [])
    record("vettore libero [1,1,0]: scomposto in 2 passi (X e Y) di 35,355 mm", sum(1 for s in sts if s["components"] == ["cx_screw-1"]) == 2
           and all(abs(s["distance_mm"] - 50 / math.sqrt(2)) < 1e-3 for s in sts if s["components"] == ["cx_screw-1"]), f"{[(s['axis'], s['distance_mm']) for s in sts[:2]]}")
    s1 = poses.get("cx_screw-1", {}).get("position_mm", [9e9] * 3)
    e1 = [P0["cx_screw-1"][i] + [50 / math.sqrt(2), 50 / math.sqrt(2), 0][i] for i in range(3)]
    record("vite 1: spostata di 50 mm lungo (1,1,0)/sqrt2", close(s1, e1), f"{s1} vs {[round(v, 4) for v in e1]}")
    dv = [s1[i] - P0["cx_screw-1"][i] for i in range(3)]
    record("vite 1: modulo dello spostamento 50 mm", abs(math.sqrt(sum(v * v for v in dv)) - 50) < TOL, f"{math.sqrt(sum(v * v for v in dv)):.4f}")
    record("vite 1: nessuna rotazione", all(abs(a) < 1e-6 for a in poses.get("cx_screw-1", {}).get("rotation_deg", [9, 9, 9])))
    # entita' inclinata: spostamento parallelo all'asse del perno di riferimento
    b = poses.get("cx_bush-1", {}).get("position_mm", [9e9] * 3)
    db = [b[i] - P0["cx_bush-1"][i] for i in range(3)]
    nb = math.sqrt(sum(v * v for v in db))
    cr = [db[1] * axis[2] - db[2] * axis[1], db[2] * axis[0] - db[0] * axis[2], db[0] * axis[1] - db[1] * axis[0]]
    record("boccola: spostamento di 40 mm", abs(nb - 40) < TOL, f"{nb:.4f}")
    record("boccola: direzione parallela all'asse inclinato di 30 gradi (sinΘ < 1e-5)", math.sqrt(sum(v * v for v in cr)) / max(nb, 1e-9) < 1e-5,
           f"d={[round(v, 4) for v in db]}")
    # radiale: distanza dall'asse X da 30 a 60 mm, rotazione di 30 gradi
    for nm in ("cx_screw-2", "cx_screw-3", "cx_screw-4"):
        p = poses.get(nm, {})
        pos = p.get("position_mm", [9e9] * 3)
        rho0 = math.hypot(P0[nm][1], P0[nm][2])
        # la posizione dell'ORIGINE si sposta per la rotazione attorno al centro del box: si controlla il centro del box
        bx = p.get("box_mm", [0] * 6)
        cen = [(bx[1] + bx[4]) / 2, (bx[2] + bx[5]) / 2]
        record(f"{nm}: raggio del centro del box da 30 a 60 mm (radiale, distanza 30)", abs(math.hypot(*cen) - (rho0 + 30)) < 0.3, f"{math.hypot(*cen):.3f}")
        ang = rot_angle_deg(p["matrix"]) if "matrix" in p else None
        record(f"{nm}: ruotata di 30 gradi (angolo della matrice)", ang is not None and abs(ang - 30) < 1e-3, f"{ang}")
    radial = [s for s in sts if s.get("type") == "radial"]
    record("passo radiale riporta distanza 30 mm e angolo 30 gradi", len(radial) == 1 and abs(radial[0]["distance_mm"] - 30) < 1e-6 and abs(radial[0]["angle_deg"] - 30) < 1e-6, f"{radial}")
    # traslazione + rotazione: traslazione ok, rotazione NON memorizzata da SolidWorks (limite dichiarato)
    pp = poses.get("cx_pin-1", {}).get("position_mm", [9e9] * 3)
    record("perno: traslato di 20 mm in -X", close(pp, [P0["cx_pin-1"][0] - 20, P0["cx_pin-1"][1], P0["cx_pin-1"][2]]), f"{pp}")
    tr = [s for s in sts if s["components"] == ["cx_pin-1"]]
    record("traslazione con rotazione: l'API riporta rotation_applied=false (SolidWorks 2026 ignora ExplAng)", len(tr) == 1 and tr[0].get("rotation_applied") is False and "rotation_note" in tr[0], f"{tr}")
    d2 = await need(c, "list_exploded_views", "stesse pose da list_exploded_views")
    record("list_exploded_views: stesse pose esplose", d2.get("exploded") and close(d2.get("poses", {}).get("cx_screw-1", {}).get("position_mm", [9e9] * 3), s1))
    # posizioni reali (compresso) invariate
    ok, _, dsh = await c.call("show_exploded", exploded=False)
    pc = await A.pos("cx_screw-1")
    record("assieme compresso: la vite 1 torna dov'era", close(pc, P0["cx_screw-1"]), f"{pc}")
    await c.call("close_document", discard=True)


async def c4_esplosione_automatica(c):
    print("\n== C4. Esplosione automatica: nativa ed euristica dagli accoppiamenti")
    A = Asm(c)
    # --- nativa
    await build_exp(c, "esplosione nativa")
    P0 = {n: x["position_mm"] for n, x in (await A.comps()).items()}
    d = await need(c, "auto_explode", "mode=native (AutoExplode di SolidWorks)", mode="native")
    record("nativa: metodo native, almeno 1 passo", d.get("method") == "native" and len(d.get("steps", [])) >= 1, f"{[(s['name'], s.get('type')) for s in d.get('steps', [])]}")
    poses = d.get("poses", {})
    moved = [n for n, p in poses.items() if math.dist(p["position_mm"], P0[n]) > 1.0]
    record("nativa: la maggior parte dei componenti si sposta (>1 mm)", len(moved) >= 5, f"{len(moved)}/7: {sorted(moved)}")
    ov = d.get("bbox_overlaps", None)
    record("nativa: sovrapposizioni dei box riportate (numero misurato, non richiesto 0)", isinstance(ov, list), f"{len(ov) if ov is not None else None}: {ov}")
    await c.call("close_document", discard=True)
    # --- euristica
    await build_exp(c, "esplosione per accoppiamenti")
    P0 = {n: x["position_mm"] for n, x in (await A.comps()).items()}
    d = await need(c, "auto_explode", "mode=mates gap=15", mode="mates", gap=15)
    order = d.get("disassembly_order", [])
    record("ordine di smontaggio: il perno prima della boccola, la boccola prima della base (assente: fissa)", "cx_pin-1" in order and "cx_bush-1" in order
           and order.index("cx_pin-1") < order.index("cx_bush-1") and "cx_base2-1" not in order, f"{order}")
    dirs = d.get("directions", {})
    record("direzione = asse del concentrico (X) col verso della testa (-X) per tutti", all(close(v, [-1, 0, 0], 1e-6) for v in dirs.values()) and len(dirs) == 6, f"{dirs}")
    poses = d.get("poses", {})
    dist = d.get("distances_mm", {})
    for n, dd in dist.items():
        px = poses[n]["position_mm"]
        record(f"{n}: spostata di {dd} mm in -X (posa esplosa = originale - distanza)", close(px, [P0[n][0] - dd, P0[n][1], P0[n][2]], 2e-3), f"{px}")
    record("nessuna sovrapposizione dei box nello stato esploso (riportata dal tool)", d.get("bbox_overlaps") == [], f"{d.get('bbox_overlaps')}")
    names = sorted(poses)
    seps = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            seps.append((box_sep_mm(poses[names[i]]["box_mm"], poses[names[j]]["box_mm"]), names[i], names[j]))
    worst = min(seps)
    record("test indipendente: distanza minima fra i box di ogni coppia >= 14 mm (gap 15 meno margine dei box)", worst[0] >= 14.0, f"minimo {worst[0]:.3f} mm ({worst[1]}, {worst[2]})")
    record("le viti si spostano insieme (stessa distanza) e meno della boccola", abs(dist["cx_screw-1"] - dist["cx_screw-2"]) < 0.01 and dist["cx_screw-1"] < dist["cx_bush-1"] < dist["cx_pin-1"], f"{dist}")
    # nello stato compresso le posizioni sono quelle vere
    await c.call("show_exploded", exploded=False)
    pc = await A.comps()
    record("assieme compresso: posizioni originali ripristinate", all(close(pc[n]["position_mm"], P0[n]) for n in P0))
    # --- C6 sullo stesso assieme (catena boccola -> perno)
    await c6_delete_mate(c, P0)
    await c.call("close_document", discard=True)


# ============================================================================================ C5
async def pos_of(c, name):
    ok, _, d = await c.call("list_components")
    for x in d.get("components", []):
        if x["name"] == name:
            return x["position_mm"], x["rotation_deg"], x["transform"]
    return None, None, None


async def c5_accoppiamenti_avanzati(c):
    print("\n== C5. Accoppiamenti avanzati")
    A = Asm(c)
    # ---------------------------------------------------------------- limite distanza
    await need(c, "create_new_assembly", "limite distanza")
    await c.call("insert_component", file_path=F("cx_base"), x=0, y=0, z=0, fixed=True)
    await c.call("insert_component", file_path=F("cx_blocco"), x=40, y=0, z=0)
    d = await need(c, "add_mate", "distanza 10 con limiti 5..20", mate_type="distance", entity1={"component": "cx_base-1", "face": [10, 20, 20]},
                   entity2={"component": "cx_blocco-1", "face": [40, 0, 5]}, distance=10, min_value=5, max_value=20, align="anti_aligned")
    name = d.get("name", "DistanzaLimite1")
    record("accoppiamento di tipo 'limite distanza' con intervallo 5..20 mm letto dal modello", d.get("limits") == {"min": 5.0, "max": 20.0} and d.get("value") == 10.0, f"{d.get('feature_type')} {d.get('limits')}")
    p, _, _ = await pos_of(c, "cx_blocco-1")
    record("posizione nominale: faccia del blocco a 10 mm dalla piastra (origine x = 20)", abs(p[0] - 20) < TOL, f"{p}")
    prev = None                       # ultimo valore accettato (i primi casi sono nel limite)
    for v, exp_ok in ((15, True), (19.9, True), (5.5, True), (25, False), (3, False)):
        ok, text, dd = await c.call("edit_mate", name=name, value=v)
        p, _, _ = await pos_of(c, "cx_blocco-1")
        if exp_ok:
            record(f"limite distanza: valore {v} mm (nel limite) -> blocco a {10 + v} mm di origine X", ok and abs(p[0] - (10 + v)) < TOL, f"x={p[0]}")
        else:
            record(f"limite distanza: valore {v} mm (fuori limite) rifiutato, il blocco non si muove", (not ok) and "limiti" in text and abs(p[0] - (10 + prev)) < TOL, f"x={p[0]}; {text.split(chr(10))[0][:110]}")
        if exp_ok:
            prev = v
    d = await need(c, "edit_mate", "limiti 5..30", name=name, min_value=5, max_value=30)
    record("limiti aggiornati a 5..30", d.get("limits") == {"min": 5.0, "max": 30.0}, f"{d.get('limits')}")
    ok, text, dd = await c.call("edit_mate", name=name, value=28)
    p, _, _ = await pos_of(c, "cx_blocco-1")
    record("dopo l'ampliamento, 28 mm e' accettato", ok and abs(p[0] - 38) < TOL, f"x={p[0]}")
    ok, text, dd = await c.call("edit_mate", name=name, value=31)
    record("31 mm (oltre il nuovo massimo) rifiutato", not ok)
    await c.call("close_document", discard=True)
    # ---------------------------------------------------------------- limite angolo
    await need(c, "create_new_assembly", "limite angolo")
    await c.call("insert_component", file_path=F("cx_perno"), x=0, y=0, z=0, fixed=True)
    await c.call("insert_component", file_path=F("cx_flap"), x=10, y=20, z=0)
    await need(c, "add_mate", "cerniera: foro della piastrina concentrico col perno", mate_type="concentric",
               entity1={"component": "cx_flap-1", "face": [12.5, 0, 5]}, entity2={"component": "cx_perno-1", "face": [20, 5, 0]})
    d = await need(c, "add_mate", "angolo 0 con limiti -20..45 fra la faccia della piastrina e il Piano superiore", mate_type="angle",
                   entity1={"component": "cx_flap-1", "face": [12.5, 30, 10]}, entity2="Piano superiore", angle=0, min_value=-20, max_value=45)
    name = d.get("name", "AngoloLimite1")
    record("accoppiamento 'limite angolo' con intervallo -20..45 gradi letto dal modello", d.get("limits") == {"min": -20.0, "max": 45.0}, f"{d.get('feature_type')} {d.get('limits')}")
    prev = 0.0
    for v, exp_ok in ((30, True), (44, True), (50, False), (-10, True), (-25, False), (0, True)):
        ok, text, dd = await c.call("edit_mate", name=name, value=v)
        _, rot, _ = await pos_of(c, "cx_flap-1")
        if exp_ok:
            record(f"limite angolo: {v} gradi (nel limite) -> la piastrina ruota di {abs(v)} gradi attorno a X (misurato: |rotazione| = |D1|)", ok and abs(abs(rot[0]) - abs(v)) < 1e-3, f"rot_x={rot[0]}")
            prev = v
        else:
            record(f"limite angolo: {v} gradi (fuori limite) rifiutato, resta a {abs(prev)}", (not ok) and abs(abs(rot[0]) - abs(prev)) < 1e-3, f"rot_x={rot[0]}")
    await c.call("close_document", discard=True)
    # ---------------------------------------------------------------- larghezza
    await need(c, "create_new_assembly", "larghezza")
    await c.call("insert_component", file_path=F("cx_slot"), x=0, y=0, z=0, fixed=True)
    await c.call("insert_component", file_path=F("cx_tab"), x=10, y=2, z=0)
    d = await need(c, "add_mate", "larghezza centrata: linguetta nella finestra (y -10..20)", mate_type="width",
                   entity1={"component": "cx_slot-1", "face": [15, -10, 0]}, entity2={"component": "cx_slot-1", "face": [15, 20, 0]},
                   tab_entities=[{"component": "cx_tab-1", "face": [17, -8, 0]}, {"component": "cx_tab-1", "face": [17, 12, 0]}])
    record("tipo 'width' (MateWidth)", d.get("type") == "width", f"{d.get('feature_type')}")
    p, _, _ = await pos_of(c, "cx_tab-1")
    record("linguetta centrata nella finestra: y = 5 (centro di -10..20)", abs(p[1] - 5) < TOL, f"{p}")
    d = await need(c, "move_component", "dy=30 (vietato dalla larghezza)", component="cx_tab-1", dy=30)
    p2, _, _ = await pos_of(c, "cx_tab-1")
    record("larghezza: la linguetta non si sposta in Y", abs(p2[1] - 5) < TOL and abs(d.get("ignored", {}).get("translation_mm", 0) - 30) < 1e-3, f"{p2}, scartato {d.get('ignored')}")
    d = await need(c, "move_component", "dx=4 (lungo la finestra: libero)", component="cx_tab-1", dx=4)
    p3, _, _ = await pos_of(c, "cx_tab-1")
    record("larghezza: scorre in X di 4 mm", abs(p3[0] - p2[0] - 4) < TOL and abs(p3[1] - 5) < TOL, f"{p3}")
    record("larghezza: traslazioni libere X e Z, rotazione libera attorno a Y", d.get("free_translation_directions") == ["x", "z"] and d.get("free_rotation_axes") == ["y"],
           f"{d.get('free_translation_directions')} {d.get('free_rotation_axes')}")
    await c.call("close_document", discard=True)
    # ---------------------------------------------------------------- simmetrico
    await need(c, "create_new_assembly", "simmetrico")
    await c.call("insert_component", file_path=F("cx_blocco"), x=0, y=60, z=0, fixed=True)
    await c.call("insert_component", file_path=F("cx_blocco"), x=0, y=-30, z=0)
    d = await need(c, "add_mate", "simmetrici rispetto al Piano destro", mate_type="symmetric", entity1={"component": "cx_blocco-1", "face": [5, 80, 0]},
                   entity2={"component": "cx_blocco-2", "face": [5, -10, 0]}, entity3="Piano destro")
    record("tipo 'symmetric'", d.get("type") == "symmetric", f"{d.get('feature_type')}")
    p, _, _ = await pos_of(c, "cx_blocco-2")
    record("facce simmetriche: faccia y=80 dell'originale <-> y=-80; origine del secondo a y=-100", abs(p[1] + 100) < TOL and abs(p[0]) < TOL and abs(p[2]) < TOL, f"{p}")
    d = await need(c, "move_component", "dy=15 (vietato)", component="cx_blocco-2", dy=15)
    p2, _, _ = await pos_of(c, "cx_blocco-2")
    record("simmetrico: il secondo blocco non si sposta in Y", abs(p2[1] + 100) < TOL, f"{p2}")
    await c.call("close_document", discard=True)
    # ---------------------------------------------------------------- tangente
    await need(c, "create_new_assembly", "tangente")
    await c.call("insert_component", file_path=F("cx_blocco"), x=0, y=0, z=0, fixed=True)
    await c.call("insert_component", file_path=F("cx_perno"), x=0, y=0, z=40)
    d = await need(c, "add_mate", "perno tangente alla faccia superiore del blocco", mate_type="tangent",
                   entity1={"component": "cx_perno-1", "face": [20, 0, 45]}, entity2={"component": "cx_blocco-1", "face": [5, 0, 10]})
    p, _, _ = await pos_of(c, "cx_perno-1")
    record("tangente: asse del perno a z = 10 + r(5) = 15", abs(p[2] - 15) < TOL, f"{p}")
    d = await need(c, "move_component", "dz=-50 (verso il blocco: vietato)", component="cx_perno-1", dz=-50)
    p2, _, _ = await pos_of(c, "cx_perno-1")
    record("tangente: il perno non penetra nel blocco (z resta 15)", abs(p2[2] - 15) < TOL, f"{p2}")
    d = await need(c, "move_component", "dx=7 dy=12 (sul piano: libero)", component="cx_perno-1", dx=7, dy=12)
    p3, _, _ = await pos_of(c, "cx_perno-1")
    record("tangente: scorre di (7,12) sulla faccia", close(p3, [7, 12, 15]), f"{p3}")
    record("tangente: traslazioni libere X,Y; rotazioni libere X (proprio asse) e Z", d.get("free_translation_directions") == ["x", "y"] and d.get("free_rotation_axes") == ["x", "z"],
           f"{d.get('free_translation_directions')} {d.get('free_rotation_axes')}")
    await c.call("close_document", discard=True)
    # ---------------------------------------------------------------- blocco (lock)
    await need(c, "create_new_assembly", "blocco")
    await c.call("insert_component", file_path=F("cx_blocco"), x=0, y=0, z=0, fixed=True)
    await c.call("insert_component", file_path=F("cx_perno"), x=30, y=20, z=25, rotation=[0, 0, 20])
    _, _, tf0 = await pos_of(c, "cx_perno-1")
    d = await need(c, "add_mate", "blocco fra blocco e perno", mate_type="lock", entity1="cx_blocco-1", entity2="cx_perno-1")
    record("tipo 'lock' (MateLock)", d.get("type") == "lock", f"{d.get('feature_type')}")
    _, _, tf1 = await pos_of(c, "cx_perno-1")
    record("il blocco non sposta il componente alla creazione", all(abs(a - b) < 1e-9 for a, b in zip(tf0, tf1)))
    ok, _, st = await c.call("get_assembly_status")
    row = [r for r in st.get("components", []) if r["name"] == "cx_perno-1"][0]
    record("stato dei vincoli: perno 'completamente vincolato' dopo il blocco", row["status_code"] == 3, f"{row['constrained']}")
    d = await need(c, "move_component", "dx=20 sul componente bloccato", component="cx_perno-1", dx=20)
    p, _, _ = await pos_of(c, "cx_perno-1")
    drift = math.dist(p, [30, 20, 25])
    record("blocco: dx=20 sul componente bloccato -> deriva < 0,5 mm (SetTransformAndSolve2)", drift < 0.5,
           f"deriva {drift:.3f} mm con dx=20; traslazioni libere {d.get('free_translation_directions')}, rotazioni libere {d.get('free_rotation_axes')}")
    # il solutore completo (accoppiamento d'angolo che chiede 50 gradi) non ruota il componente bloccato
    _, _, tf2 = await pos_of(c, "cx_perno-1")
    ok_a, _, _ = await c.call("add_mate", mate_type="angle", entity1={"component": "cx_perno-1", "plane": "Top"}, entity2="Top", angle=50)
    _, _, tf3 = await pos_of(c, "cx_perno-1")
    dmax = max(abs(a - b) for a, b in zip(tf2, tf3))
    record("blocco: un angolo di 50 gradi imposto dal solutore NON ruota il componente bloccato (C5)", ok_a and dmax < 1e-9,
           f"variazione massima della matrice {dmax:.2e}")
    await c.call("close_document", discard=True)
    # ---------------------------------------------------------------- ingranaggio
    await need(c, "create_new_assembly", "ingranaggio")
    await c.call("insert_component", file_path=F("cx_perno"), x=0, y=0, z=0, fixed=True)
    await c.call("insert_component", file_path=F("cx_perno"), x=0, y=50, z=0, fixed=True)
    await c.call("insert_component", file_path=F("cx_gear"), x=10, y=0, z=0)
    await c.call("insert_component", file_path=F("cx_gear_s"), x=10, y=50, z=0)
    n_ok = 0
    for g, pn, y in (("cx_gear-1", "cx_perno-1", 0), ("cx_gear_s-1", "cx_perno-2", 50)):
        n_ok += (await c.call("add_mate", mate_type="concentric", entity1={"component": g, "face": [15, y + 5, 0]}, entity2={"component": pn, "face": [20, y + 5, 0]}))[0]
        n_ok += (await c.call("add_mate", mate_type="coincident", entity1={"component": g, "face": [10, y + (15 if y == 0 else 7), 0]},
                              entity2={"component": pn, "face": [0, y + 2, 0]}, align="aligned"))[0]
    record("ruote su perni fissi: 4 accoppiamenti", n_ok == 4, f"{n_ok}/4")
    d = await need(c, "add_mate", "ingranaggio rapporto 2:1 fra i due alesaggi", mate_type="gear", entity1={"component": "cx_gear-1", "face": [5, 5, 0]},
                   entity2={"component": "cx_gear_s-1", "face": [5, 55, 0]}, gear_ratio=[2, 1])
    gr = d.get("gear_ratio_in_model")
    record("tipo 'gear' (MateGearDim) e rapporto 2:1 letto dal modello (SolidWorks lo restituisce scambiato)", d.get("type") == "gear" and gr is not None and sorted(gr) == [1.0, 2.0], f"{d.get('feature_type')} {gr}")
    _, ra0, _ = await pos_of(c, "cx_gear-1")
    _, rb0, _ = await pos_of(c, "cx_gear_s-1")
    ok, _, d = await c.call("move_component", component="cx_gear-1", rotate_by=[30, 0, 0])
    _, ra1, _ = await pos_of(c, "cx_gear-1")
    _, rb1, _ = await pos_of(c, "cx_gear_s-1")
    record("ruota A ruotata di 30 gradi attorno al proprio asse (libera)", abs((ra1[0] - ra0[0]) - 30) < 1e-3, f"{ra1[0] - ra0[0]}")
    record("ingranaggio: la ruota B segue nel rapporto 2:1 (A +30 -> B -60, entro 0,1 %) (C5)", abs((rb1[0] - rb0[0]) + 60) < 0.06,
           f"rotazione di B {rb1[0] - rb0[0]:.4f} gradi, pilotaggio {d.get('mechanical_drive')}")
    await c.call("close_document", discard=True)
    # ---------------------------------------------------------------- vite
    await need(c, "create_new_assembly", "vite")
    await c.call("insert_component", file_path=F("cx_perno"), x=0, y=0, z=0, fixed=True)
    await c.call("insert_component", file_path=F("cx_gear_s"), x=10, y=0, z=0)
    await need(c, "add_mate", "chiocciola concentrica con l'asta", mate_type="concentric", entity1={"component": "cx_gear_s-1", "face": [15, 5, 0]},
               entity2={"component": "cx_perno-1", "face": [20, 5, 0]})
    d = await need(c, "add_mate", "vite con passo 2 mm/giro", mate_type="screw", entity1={"component": "cx_gear_s-1", "face": [15, 5, 0]},
                   entity2={"component": "cx_perno-1", "face": [20, 5, 0]}, pitch=2.0)
    record("tipo 'screw' (MateScrew) e passo 2 mm/giro letto dal modello", d.get("type") == "screw" and abs(d.get("pitch_mm_per_rev", 0) - 2.0) < 1e-6, f"{d.get('feature_type')} {d.get('pitch_mm_per_rev')}")
    p0, r0, _ = await pos_of(c, "cx_gear_s-1")
    await c.call("move_component", component="cx_gear_s-1", rotate_by=[90, 0, 0])
    p1, r1, _ = await pos_of(c, "cx_gear_s-1")
    record("chiocciola ruotata di 90 gradi attorno all'asse (libera)", abs((r1[0] - r0[0]) - 90) < 1e-3, f"{r1[0] - r0[0]}")
    record("vite: 90 gradi -> avanzamento 0,5 mm = passo 2 x 1/4 di giro (entro 0,01 mm) (C5)", abs(abs(p1[0] - p0[0]) - 0.5) < 0.01,
           f"avanzamento {p1[0] - p0[0]:.4f} mm")
    await c.call("close_document", discard=True)


# ============================================================================================ C6
async def c6_delete_mate(c, P0):
    print("\n== C6. delete_mate e gradi di liberta' dei componenti a catena")
    A = Asm(c)
    ok, _, m = await c.call("list_mates")
    names = [x["name"] for x in m.get("mates", [])]
    flange = [x["name"] for x in m.get("mates", []) if x["type"] == "coincident" and set(x["components"]) == {"cx_bush-1", "cx_base2-1"}]
    record("accoppiamento coincidente boccola-base trovato", len(flange) == 1, f"{flange} fra {names}")
    d = await need(c, "delete_mate", "elimina il coincidente della flangia (la boccola scivola; il perno la segue)", name=flange[0])
    bef, aft = d.get("dof_before", {}), d.get("dof_after", {})
    record("boccola: gradi di liberta' 1 -> 2 (compare la traslazione lungo X)", bef.get("cx_bush-1") == 1 and aft.get("cx_bush-1") == 2, f"{bef.get('cx_bush-1')}->{aft.get('cx_bush-1')}")
    record("perno (NON nell'accoppiamento eliminato) 1 -> 2: segue la boccola nella catena", bef.get("cx_pin-1") == 1 and aft.get("cx_pin-1") == 2
           and "cx_pin-1" in d.get("freed_not_in_mate", []), f"{bef.get('cx_pin-1')}->{aft.get('cx_pin-1')}; fuori dal mate {d.get('freed_not_in_mate')}")
    record("viti e base invariate (viti 1 DOF, base 0)", all(aft.get(f"cx_screw-{i}") == 1 for i in range(1, 5)) and aft.get("cx_base2-1") == 0, f"{aft}")
    fr = {f["component"]: f for f in d.get("freed_components", [])}
    record("traslazione liberata = X, per entrambi", fr.get("cx_bush-1", {}).get("free_translations_after") == ["x"] and fr.get("cx_pin-1", {}).get("free_translations_after") == ["x"], f"{fr.get('cx_pin-1')}")
    record("avviso 'componenti sottovincolati dopo l'eliminazione' presente", d.get("warning") is not None, f"{d.get('warning')}")
    pc = await A.comps()
    record("le posizioni non cambiano con l'eliminazione", all(close(pc[n]["position_mm"], P0[n], 1e-6) for n in P0))
    # coerenza: ora il perno e la boccola si muovono davvero lungo X insieme?
    d = await need(c, "move_component", "boccola: dx=-12 (ora libera lungo X)", component="cx_bush-1", dx=-12)
    pb = await A.pos("cx_bush-1")
    record("boccola scivola di -12 mm in X dopo l'eliminazione", abs(pb[0] - (P0["cx_bush-1"][0] - 12)) < TOL, f"{pb}")


# ============================================================================================ C7
async def c7_movimento_parziale(c):
    print("\n== C7. move_component su componente parzialmente vincolato")
    A = Asm(c)
    await need(c, "create_new_assembly", "perno con il solo concentrico")
    await c.call("insert_component", file_path=F("cx_base"), x=0, y=0, z=0, fixed=True)
    await c.call("insert_component", file_path=F("cx_perno"), x=100, y=30, z=0)
    await need(c, "add_mate", "solo concentrico perno-foro", mate_type="concentric", entity1={"component": "cx_perno-1", "face": [120, 35, 0]},
               entity2={"component": "cx_base-1", "face": [5, 6, 0]})
    ok, _, st = await c.call("get_assembly_status")
    row = [r for r in st.get("components", []) if r["name"] == "cx_perno-1"][0]
    record("gradi di liberta' misurati: scorre lungo X e ruota attorno a X (2)", row.get("free_translations") == ["x"] and row.get("free_rotations") == ["x"] and row.get("dof_count") == 2, f"{row}")
    p0, r0, _ = await pos_of(c, "cx_perno-1")
    record("posa iniziale: sull'asse del foro (y=z=0), x=100", close(p0, [100, 0, 0]), f"{p0}")

    async def mv_(label, expect_pos, expect_rot, **args):
        ok, text, d = await c.call("move_component", component="cx_perno-1", **args)
        p, r, _ = await pos_of(c, "cx_perno-1")
        good = ok and close(p, expect_pos, TOL) and all(abs(a - b) < 1e-3 for a, b in zip(r, expect_rot))
        record(f"move_component {label}", good, f"pos {p}, rot {r}; applicato {d.get('applied')}; scartato {d.get('ignored')}")
        return d

    d = await mv_("rotate_by X 30: ruota attorno all'asse", [100, 0, 0], [30, 0, 0], rotate_by=[30, 0, 0])
    record("   applicato 30 gradi, scartato 0", abs(d["applied"]["rotation_deg_about_free_axes"][0] - 30) < 1e-3 and d["ignored"]["rotation_deg"] < 1e-3)
    d = await mv_("dx=+15: scorre lungo l'asse", [115, 0, 0], [30, 0, 0], dx=15)
    record("   spostamento misurato 15 mm", abs(d["moved_mm"] - 15) < TOL)
    d = await mv_("rotate_by Y 45: vietato (inclinerebbe l'asse)", [115, 0, 0], [30, 0, 0], rotate_by=[0, 45, 0])
    record("   scartati 45 gradi, nessuno spostamento", abs(d["ignored"]["rotation_deg"] - 45) < 1e-3 and d["moved_mm"] < TOL)
    d = await mv_("rotate_by Z 20: vietato", [115, 0, 0], [30, 0, 0], rotate_by=[0, 0, 20])
    d = await mv_("dy=+10: vietato (uscirebbe dall'asse)", [115, 0, 0], [30, 0, 0], dy=10)
    record("   scartati 10 mm", abs(d["ignored"]["translation_mm"] - 10) < 1e-3)
    d = await mv_("dz=-7: vietato", [115, 0, 0], [30, 0, 0], dz=-7)
    d = await mv_("combinato dx=-5 dz=8 rotate_by X 20: applica solo -5 e 20", [110, 0, 0], [50, 0, 0], dx=-5, dz=8, rotate_by=[20, 0, 0])
    record("   applicato (-5,0,0) e 20 gradi; scartati 8 mm", d["applied"]["translation_mm"] == [-5.0, 0.0, 0.0] and abs(d["ignored"]["translation_mm"] - 8) < 1e-3, f"{d['applied']} {d['ignored']}")
    d = await mv_("assoluto position=[130,50,50]: solo X conta", [130, 0, 0], [50, 0, 0], position=[130, 50, 50])
    # rotazione composta Ry(25) Rx(15): il vettore di rotazione ha una componente lungo X (calcolata qui) che e' l'unica ammessa
    ca, sa, cb, sb = math.cos(math.radians(15)), math.sin(math.radians(15)), math.cos(math.radians(25)), math.sin(math.radians(25))
    Rq = [[cb, sb * sa, sb * ca], [0, ca, -sa], [-sb, cb * sa, cb * ca]]
    ang = math.acos((Rq[0][0] + Rq[1][1] + Rq[2][2] - 1) / 2)
    wx = (Rq[2][1] - Rq[1][2]) / (2 * math.sin(ang))
    th_x = math.degrees(ang * wx)
    d = await mv_(f"rotazione combinata X15+Y25: solo la componente attorno a X ({th_x:.4f} gradi)", [130, 0, 0], [50 + th_x, 0, 0], rotate_by=[15, 25, 0])
    # asse e orientamento dell'asse invariati
    M, t = await A.pose("cx_perno-1")
    ax = [M[0][0], M[1][0], M[2][0]]
    record("l'asse del perno resta parallelo a X e passa per il centro del foro", close(ax, [1, 0, 0], 1e-6) and abs(t[1]) < TOL and abs(t[2]) < TOL, f"asse {ax}, origine {t}")
    # respect_mates=false: posa imposta senza risolvere
    await c.call("close_document", discard=True)
    # ---- asse inclinato: la base e' ruotata di 30 gradi attorno a Z, il perno scorre lungo (cos30, sin30, 0)
    await need(c, "create_new_assembly", "asse inclinato")
    await c.call("insert_component", file_path=F("cx_base"), x=0, y=0, z=0, rotation=[0, 0, 30], fixed=True)
    await c.call("insert_component", file_path=F("cx_perno"), x=100, y=30, z=0)
    a30 = math.radians(30)
    u = [math.cos(a30), math.sin(a30), 0]
    # punto sul foro (r=6) della base ruotata: locale (5,6,0) -> mondo R30z*(5,6,0)
    Rz = [[math.cos(a30), -math.sin(a30), 0], [math.sin(a30), math.cos(a30), 0], [0, 0, 1]]
    hole_pt = mv(Rz, [5, 6, 0])
    # il perno (non ruotato) ha l'asse lungo X: prima lo si ruota di 30 gradi attorno a Z come la base (movimento libero), poi si accoppia
    await c.call("move_component", component="cx_perno-1", position=[100, 30, 0], rotation=[0, 0, 30])
    pp = mv(Rz, [20, 5, 0])
    d = await need(c, "add_mate", "concentrico con il foro inclinato", mate_type="concentric",
                   entity1={"component": "cx_perno-1", "face": vadd([100, 30, 0], pp)}, entity2={"component": "cx_base-1", "face": hole_pt})
    ok, _, st = await c.call("get_assembly_status")
    row = [r for r in st.get("components", []) if r["name"] == "cx_perno-1"][0]
    ft = row.get("free_translations", [])
    record("asse inclinato: 2 gradi di liberta' lungo/attorno all'asse inclinato (direzione non e' un asse del mondo)", row.get("dof_count") == 2
           and len(ft) == 1 and ft[0].startswith("(") and ft[0].replace("-", "") == "(0.866,0.500,0.000)", f"{ft} {row.get('free_rotations')}")
    p0, _, _ = await pos_of(c, "cx_perno-1")
    d = await need(c, "move_component", "dx=10 lungo X del mondo", component="cx_perno-1", dx=10, dy=0, dz=0)
    p1, _, _ = await pos_of(c, "cx_perno-1")
    dv = [p1[i] - p0[i] for i in range(3)]
    exp = [10 * math.cos(a30) * math.cos(a30), 10 * math.cos(a30) * math.sin(a30), 0]
    record("asse inclinato: dx=10 -> spostamento 10 cos30 lungo l'asse = (7.5, 4.33, 0)", close(dv, exp, 2e-3), f"{[round(v, 4) for v in dv]} vs {[round(v, 4) for v in exp]}")
    record("   scartata la componente perpendicolare (10 sin30 = 5 mm)", abs(d["ignored"]["translation_mm"] - 5) < 2e-3, f"{d['ignored']}")
    M, t = await A.pose("cx_perno-1")
    ax = [M[0][0], M[1][0], M[2][0]]
    # distanza dell'origine dall'asse del foro (retta per l'origine con direzione u)
    cr = [t[1] * u[2] - t[2] * u[1], t[2] * u[0] - t[0] * u[2], t[0] * u[1] - t[1] * u[0]]
    record("l'asse del perno resta sull'asse inclinato del foro (distanza < 2e-3 mm, parallelo)", math.sqrt(sum(v * v for v in cr)) < 2e-3 and close(ax, u, 1e-6),
           f"distanza {math.sqrt(sum(v * v for v in cr)):.6f}, asse {[round(v, 6) for v in ax]}")
    await c.call("close_document", discard=True)


# ============================================================================================ main
def tool_checks(tl):
    print("\n== 0. Tool e schemi")
    names = [x.name for x in tl]
    by = {x.name: x for x in tl}
    record("196 tool, nessun duplicato (il gruppo C non aggiunge tool, solo parametri)", len(names) == 196 and len(set(names)) == 196, f"{len(names)} tool")
    m = by["mirror_components"]
    record("mirror_components: destructiveHint, nota [DISTRUTTIVO], parametri opposite_hand/name_suffix/folder/overwrite/align_exact",
           bool(m.annotations and m.annotations.destructiveHint) and "DISTRUTTIVO" in (m.description or "")
           and {"opposite_hand", "name_suffix", "folder", "overwrite", "align_exact"} <= set(m.inputSchema["properties"]), "")
    record("delete_mate (distruttivo) espone check_dof; auto_explode espone mode; add_explode_step radial_axis/angle",
           "check_dof" in by["delete_mate"].inputSchema["properties"] and by["delete_mate"].annotations.destructiveHint
           and "mode" in by["auto_explode"].inputSchema["properties"] and {"radial_axis", "angle", "diverge"} <= set(by["add_explode_step"].inputSchema["properties"]), "")


async def scenario(c, tl):
    only = {a.upper() for a in sys.argv[1:]}
    tool_checks(tl)
    await build_parts(c)
    steps = [("C1", c1_sotto_assiemi), ("C2", c2_specchiatura), ("C3", c3_esplosione_libera), ("C4", c4_esplosione_automatica),
             ("C5", c5_accoppiamenti_avanzati), ("C7", c7_movimento_parziale)]
    for tag, fn in steps:
        if only and tag not in only and not (tag == "C4" and "C6" in only):
            continue
        try:
            await fn(c)
        except Exception as e:
            import traceback
            record(f"{tag}: eccezione", False, f"{type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                await c.call("close_document", discard=True)
            except Exception:
                pass


if __name__ == "__main__":
    done = asyncio.run(run())
    print("\n==== RIEPILOGO ====")
    for tool, res, note in RESULTS:
        print(f"{res:5} {tool:100} {note}"[:260])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
