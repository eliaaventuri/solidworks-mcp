"""
Test live del lotto SALDATURE (membri strutturali, taglia/estendi, tappo, distinta di taglio) tramite il server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente non viene mai
toccata; alla fine si chiude solo il PID lanciato dal test.

  W1  list_weldment_profiles: norma iso, profilo 'square tube' con le sue misure
  W2  structural_member: telaio quadrato 200 (4 corpi, volume = 4 x area x 200), linea 300 (volume = area x 300, area
      misurata sulla faccia d'estremita'), un solo segmento (id)
  W3  weldment_trim_extend: T (membro B taglia A) -> volume di B = area x 130; estensione di un membro corto (100 -> 130)
  W4  weldment_end_cap: tappo di spessore 10 mm: +1 corpo, volume = 32 x 32 x 10
  W5  weldment_cut_list: telaio 200: 1 voce con quantita' 4 e ingombro 240 mm (200 + 40 del mitra)

Uso:  .venv\\Scripts\\python.exe tests\\test_ext_weldments_live.py [W1 W2 ...]
"""

import os
import sys
import math
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, PYTHON, SERVER, sw_pids, Client, cleanup

RESULTS = []         # (nome, PASS/FAIL, nota)
TOL = 0.005          # 0,5 % (valori calcolati a mano, salvo dichiarato)

# profilo ISO 'square tube' 40 x 40 x 4: spigoli esterni R = 2 t = 8 mm, interni r = t = 4 mm (verificato dal test W2)
SIDE, WALL = 40.0, 4.0
R_OUT, R_IN = 2 * WALL, WALL
A_SHARP = SIDE ** 2 - (SIDE - 2 * WALL) ** 2                                   # 576 mm2 (spigoli vivi)
A_CALC = A_SHARP - (4 - math.pi) * R_OUT ** 2 + (4 - math.pi) * R_IN ** 2      # 534.796 mm2 (con gli arrotondamenti)
INNER_SHARP = (SIDE - 2 * WALL) ** 2                                           # 1024 mm2


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:260])


def near(got, exp, tol=TOL):
    return abs(got - exp) <= tol * max(abs(exp), 1e-9)


def fmt(x):
    return f"{x:.4f}"


async def new_part(c):
    ok, text, _ = await c.call("create_new_part")
    assert ok, text


async def discard_all(c):
    for _ in range(40):
        ok, _, d = await c.call("list_open_documents")
        docs = d.get("documents", []) if ok else []
        if not docs:
            return
        await c.call("close_document", discard=True, document=docs[0]["title"])


async def vol(c):
    ok, _, d = await c.call("get_mass_properties")
    return d.get("volume_mm3", 0.0) if ok else 0.0


async def sketch_square(c, side=200.0):
    h = side / 2
    await c.call("create_sketch", plane="Front")
    for a, b, cc, dd in [(-h, -h, h, -h), (h, -h, h, h), (h, h, -h, h), (-h, h, -h, -h)]:
        await c.call("draw_line", x1=a, y1=b, x2=cc, y2=dd)
    ok, _, d = await c.call("list_sketch_entities")
    return [s["id"] for s in d["segments"]] if ok else []


async def bodies(c):
    ok, _, d = await c.call("list_bodies", unit="mm")
    return d.get("bodies", []) if ok else []


async def w1_profiles(c):
    ok, text, d = await c.call("list_weldment_profiles", standard="iso", profile="square tube")
    stds = d.get("standards", []) if ok else []
    profs = stds[0]["profiles"] if stds else []
    sizes = profs[0].get("sizes", []) if profs else []
    record("W1 norma iso contiene 'square tube' con misure", ok and bool(profs) and len(sizes) >= 1,
           f"{len(sizes)} misure, es. {sizes[:3]}")
    record("W1 la misura '40 x 40 x 4' e' nell'elenco", "40 x 40 x 4" in sizes, f"count={profs[0].get('count') if profs else None}")


async def w2_members(c):
    await new_part(c)
    ids = await sketch_square(c, 200.0)
    ok, text, d = await c.call("structural_member", standard="iso", profile="square tube", size="40 x 40 x 4")
    v = await vol(c)
    nb = len(await bodies(c))
    exp_v = 4 * A_CALC * 200.0
    record("W2 telaio 200: 4 corpi", ok and nb == 4, f"corpi {nb}, ok={ok}")
    record("W2 telaio 200: volume = 4 x A x 200 (A con arrotondamenti)", near(v, exp_v),
           f"misurato {fmt(v)} mm3, calcolato {fmt(exp_v)} (scarto {100 * (v - exp_v) / exp_v:+.4f} %)")
    record("W2 scarto con spigoli vivi (576 mm2), solo informativo", True,
           f"con spigoli vivi {fmt(4 * A_SHARP * 200)} mm3: scarto {100 * (v - 4 * A_SHARP * 200) / (4 * A_SHARP * 200):+.2f} % "
           "(il profilo ha gli arrotondamenti)")

    await new_part(c)
    await sketch_square(c, 200.0)
    ok2, _, d2 = await c.call("structural_member", segments=[ids[0]], standard="iso", profile="square tube",
                              size="40 x 40 x 4")
    v2 = await vol(c)
    nb2 = len(await bodies(c))
    record("W2 un solo segmento (id): 1 corpo, volume = A x 200", ok2 and nb2 == 1 and near(v2, A_CALC * 200.0),
           f"corpi {nb2}, misurato {fmt(v2)}, calcolato {fmt(A_CALC * 200.0)}")

    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_line", x1=0, y1=0, x2=300, y2=0)
    ok3, _, d3 = await c.call("structural_member", standard="iso", profile="square tube", size="40 x 40 x 4")
    v3 = await vol(c)
    okf, _, df = await c.call("measure_face", x=0, y=0, z=18, unit="mm")
    area = df.get("area_mm2", 0.0) if okf else 0.0
    record("W2 linea 300: volume = area x 300 (area dalla faccia d'estremita')",
           ok3 and okf and near(v3 / 300.0, area, 0.005),
           f"volume {fmt(v3)} / 300 = {fmt(v3 / 300)} mm2, faccia {fmt(area)} mm2, calcolata {fmt(A_CALC)} mm2")
    record("W2 area della faccia = calcolo con arrotondamenti (R 8, r 4)", near(area, A_CALC, 0.001),
           f"faccia {fmt(area)}, calcolata {fmt(A_CALC)}")


async def w3_trim(c):
    # T: A lungo 300, B lungo 150 che arriva al centro di A: B si taglia sulla superficie di A (resta 130 mm)
    async def setup(y_end):
        await new_part(c)
        await c.call("create_sketch", plane="Front")
        await c.call("draw_line", x1=0, y1=0, x2=300, y2=0)
        await c.call("draw_line", x1=150, y1=-150, x2=150, y2=y_end)
        ok, _, d = await c.call("list_sketch_entities")
        ids = [s["id"] for s in d["segments"]]
        await c.call("structural_member", segments=[ids[0]], standard="iso", profile="square tube", size="40 x 40 x 4")
        await c.call("structural_member", segments=[ids[1]], standard="iso", profile="square tube", size="40 x 40 x 4")
        lb = await bodies(c)
        ia = [b["index"] for b in lb if abs(b["volume_mm3"] - A_CALC * 300) < 1.0][0]
        ib = [b["index"] for b in lb if b["index"] != ia][0]     # il membro B (150 o 100 mm secondo y_end)
        return ia, ib

    ia, ib = await setup(0)
    v_b0 = A_CALC * 150.0
    ok, text, d = await c.call("weldment_trim_extend", bodies_to_trim=[ib], trim_boundary=ia)
    lb = await bodies(c)
    vols = sorted(b["volume_mm3"] for b in lb)
    exp = A_CALC * 130.0
    got_b = min(vols) if vols else 0.0
    record("W3 taglio T: membro B da 150 a 130 mm (volume = A x 130)", ok and near(got_b, exp),
           f"misurato {fmt(got_b)} mm3, calcolato {fmt(exp)} mm3; sottratto {fmt(v_b0 - got_b)} "
           f"(atteso {fmt(A_CALC * 20)})")
    i_trim = [b["index"] for b in lb if abs(b["volume_mm3"] - exp) < 1.0][0]
    i_long = [b["index"] for b in lb if abs(b["volume_mm3"] - A_CALC * 300) < 1.0][0]
    okc, _, dc = await c.call("combine_bodies", main=i_long, tools=[i_trim], operation="common")
    record("W3 nessuna interferenza: intersezione membro tagliato / limite non crea volume",
           not okc, f"combine common: {'nessun corpo' if not okc else 'corpo creato'} ({dc.get('message', '')[:80] if isinstance(dc, dict) else ''})")

    ia, ib = await setup(-50)
    ok2, _, d2 = await c.call("weldment_trim_extend", bodies_to_trim=[ib], trim_boundary=ia, end_condition="extend")
    lb2 = await bodies(c)
    got2 = min(b["volume_mm3"] for b in lb2) if lb2 else 0.0
    record("W3 estensione: membro da 100 mm allungato a 130 mm (volume A x 130)", ok2 and near(got2, A_CALC * 130.0),
           f"misurato {fmt(got2)} mm3, calcolato {fmt(A_CALC * 130.0)} mm3")


async def w4_cap(c):
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_line", x1=0, y1=0, x2=300, y2=0)
    await c.call("structural_member", standard="iso", profile="square tube", size="40 x 40 x 4")
    v0 = await vol(c)
    nb0 = len(await bodies(c))
    ok, text, d = await c.call("weldment_end_cap", face_point=[0, 0, 18], thickness=10)
    v1 = await vol(c)
    nb1 = len(await bodies(c))
    exp = INNER_SHARP * 10.0
    record("W4 tappo: +1 corpo", ok and nb1 == nb0 + 1, f"corpi {nb0} -> {nb1}")
    record("W4 tappo: volume = 32 x 32 x 10 (sezione interna a spigoli vivi)", ok and near(v1 - v0, exp),
           f"delta {fmt(v1 - v0)} mm3, calcolato {fmt(exp)} mm3; con l'arrotondamento interno si avrebbe "
           f"{fmt((INNER_SHARP - (4 - math.pi) * R_IN ** 2) * 10)} (scarto {100 * (v1 - v0 - (INNER_SHARP - (4 - math.pi) * R_IN ** 2) * 10) / ((INNER_SHARP - (4 - math.pi) * R_IN ** 2) * 10):+.2f} %)")


async def w5_cut_list(c):
    await new_part(c)
    await sketch_square(c, 200.0)
    await c.call("structural_member", standard="iso", profile="square tube", size="40 x 40 x 4")
    ok, text, d = await c.call("weldment_cut_list", update=True)
    items = d.get("items", []) if ok else []
    one = len(items) == 1
    q = items[0]["quantity"] if one else None
    box = items[0]["box_size_mm"] if one else [0, 0, 0]
    record("W5 distinta: 1 voce con quantita' 4", ok and one and q == 4, f"voci {len(items)}, quantita' {[i['quantity'] for i in items]}")
    record("W5 ingombro del membro: 240 mm (200 + 40 del mitra)", ok and one and abs(max(box) - 240.0) < 0.5,
           f"ingombro {box} mm, atteso 240 (200 + 2 x 20)")


async def scenario(c):
    only = {a.upper() for a in sys.argv[1:]}
    for nome, fn in (("W1", w1_profiles), ("W2", w2_members), ("W3", w3_trim), ("W4", w4_cap), ("W5", w5_cut_list)):
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
                record("tool nuovi esposti", all(t in tools for t in (
                    "list_weldment_profiles", "structural_member", "weldment_trim_extend", "weldment_end_cap",
                    "weldment_cut_list")), "")
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
        print(f"{res:5} {tool:80} {note}"[:260])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
