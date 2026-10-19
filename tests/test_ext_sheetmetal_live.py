"""
Test live del lotto LAMIERA (sheet metal) tramite il server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente non viene mai
toccata; alla fine si chiude solo il PID lanciato dal test.

  S1  sm_base_flange: lamiera chiusa 50x30 t=2 (3000 mm3); profilo aperto 40 estruso 20 t=2 (1600 mm3, box 20x40x2)
  S2  sm_hem: orlo chiuso su spigolo (volume aumenta; sviluppo: stesso aumento di volume / (t*larghezza)); aperto, arrotolato
  S3  sm_sketched_bend: 60x30 t=2 piegata 90 gradi sulla linea a 30 mm: volume conservato, ingombro calcolato a mano,
      sviluppo = 60 mm (sm_flatten) e ritorno piegato
  S4  sm_parameters: lettura, spessore 2 -> 3 (volume 4500 mm3)
  S5  sm_export_flat_pattern: pezzo non salvato rifiutato; pezzo salvato -> DXF con ENTITIES

Valori calcolati a mano (K = 0,5, R = 2, t = 2, linea di piega a 30 mm, lunghezza 60 mm):
  BA = pi/2 * (R + K t) = 4,71239;  arretramento = R + t = 4;  tratto A = 30 - 4 = 26;  tratto B = 60 - 26 - BA = 29,28761
  ingombro X = R + tratto B = 31,28761;  ingombro Y = 30 (linea di piega + arretramento al lato esterno)

Uso:  .venv\\Scripts\\python.exe tests\\test_ext_sheetmetal_live.py [S1 S2 ...]
"""

import os
import sys
import math
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup

RESULTS = []         # (nome, PASS/FAIL, nota)
TOL = 0.002          # 0,2 % sui volumi
TOL_BEND = 0.005     # 0,5 % sulla piega (volume conservato)


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:260])


def near(got, exp, tol=TOL, absolute=None):
    if absolute is not None:
        return abs(got - exp) <= absolute
    return abs(got - exp) <= tol * max(abs(exp), 1e-9)


async def box(c):
    ok, _, d = await c.call("get_bounding_box", unit="mm")
    return (d.get("min"), d.get("max")) if ok else (None, None)


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


async def rect_sketch(c, x2, y2):
    ok, text, _ = await c.call("create_sketch", plane="Front")
    assert ok, text
    ok, text, _ = await c.call("draw_rectangle", x1=0, y1=0, x2=x2, y2=y2, unit="mm")
    assert ok, text


# ===================================================================================================== S1 flangia base
async def s1_base(c):
    print("\nS1 sm_base_flange")
    await discard_all(c)
    await new_part(c)
    await rect_sketch(c, 50, 30)
    ok, text, d = await c.call("sm_base_flange", thickness=2, bend_radius=2, k_factor=0.5)
    v = d.get("volume_mm3", 0.0) if ok else 0.0
    record("S1 lamiera chiusa 50x30 t=2 -> 3000 mm3", ok and near(v, 3000.0),
           f"{ok} {text[:80]} volume {v} (calcolato 3000)")
    await discard_all(c)

    await new_part(c)
    ok, text, _ = await c.call("create_sketch", plane="Front")
    ok2, _, _ = await c.call("draw_line", x1=0, y1=0, x2=40, y2=0, unit="mm")
    ok, text, d = await c.call("sm_base_flange", thickness=2, bend_radius=2, depth=20, k_factor=0.5)
    v = d.get("volume_mm3", 0.0) if ok else 0.0
    mn, mx = await box(c)
    size_x = (mx[0] - mn[0]) if mn and mx else None
    record("S1 profilo aperto L40 estruso 20 t=2 -> 1600 mm3", ok and near(v, 1600.0),
           f"{ok} volume {v} (calcolato 1600), box X {size_x} (calcolato 20)")
    record("S1 ingombro del profilo aperto 20 x 40 x 2", size_x is not None and near(size_x, 20.0, absolute=0.01)
           and mx and near(mx[1] - mn[1], 40.0, absolute=0.01) and near(mx[2] - mn[2], 2.0, absolute=0.01),
           f"box min {mn} max {mx}")
    await discard_all(c)


# ===================================================================================================== S2 orlo
async def s2_hem(c):
    print("\nS2 sm_hem")
    await discard_all(c)
    await new_part(c)
    await rect_sketch(c, 50, 30)
    ok, text, d = await c.call("sm_base_flange", thickness=2, bend_radius=2, k_factor=0.5)
    v0 = d.get("volume_mm3", 0.0) if ok else 0.0
    ok, text, d = await c.call("sm_hem", edge_point=[0, 50, 15], type="closed", length=5, gap=0.5, bend_radius=0.5, unit="mm")
    dv = d.get("volume_delta_mm3", 0.0) if ok else 0.0
    record("S2 orlo chiuso: volume aumenta", ok and dv > 0, f"{ok} {text[:90]} delta volume {dv} mm3 (base {v0})")
    if ok:
        okf, _, fd = await c.call("sm_flatten", flat=True)
        size = fd.get("box_size_mm") if okf else None
        dl = (size[1] - 50.0) if size else None
        expected_dv = dl * 2 * 30 if dl is not None else None
        record("S2 sviluppo dell'orlo: allungamento = volume aggiunto / (t x larghezza)",
               okf and expected_dv is not None and near(expected_dv, dv, tol=0.005),
               f"sviluppo Y {size[1] if size else None} mm -> +{dl} mm; {expected_dv} vs volume {dv} "
               f"(BA di riferimento pi*(R+K t) = {math.pi * (0.5 + 0.5 * 2):.4f}, misurato ~ {dl})")
        await c.call("sm_flatten", flat=False)
    for kind in ("open", "rolled"):
        await discard_all(c)
        await new_part(c)
        await rect_sketch(c, 50, 30)
        await c.call("sm_base_flange", thickness=2, bend_radius=2, k_factor=0.5)
        ok, text, d = await c.call("sm_hem", edge_point=[0, 50, 15], type=kind, length=5, gap=0.5, bend_radius=0.5, unit="mm")
        dv = d.get("volume_delta_mm3", 0.0) if ok else 0.0
        record(f"S2 orlo {kind}: volume aumenta", ok and dv > 0, f"{ok} {text[:90]} delta {dv} mm3")
        if ok:
            okf, _, fd = await c.call("sm_flatten", flat=True)
            size = fd.get("box_size_mm") if okf else None
            dl = (size[1] - 50.0) if size else None
            record(f"S2 orlo {kind}: sviluppo allungato come il volume aggiunto / (t x larghezza)",
                   okf and dl is not None and near(dl * 2 * 30, dv, tol=0.005),
                   f"sviluppo Y {size[1] if size else None} mm -> +{dl} mm; {dl * 60 if dl is not None else None} vs {dv}")
            await c.call("sm_flatten", flat=False)
    await discard_all(c)


# ===================================================================================================== S3 piega da schizzo
async def s3_bend(c):
    print("\nS3 sm_sketched_bend + sm_flatten")
    await discard_all(c)
    await new_part(c)
    await rect_sketch(c, 60, 30)
    ok, text, d = await c.call("sm_base_flange", thickness=2, bend_radius=2, k_factor=0.5)
    v0 = d.get("volume_mm3", 0.0) if ok else 0.0
    record("S3 base 60x30 t=2 -> 3600 mm3", ok and near(v0, 3600.0), f"volume {v0}")
    ok, text, info = await c.call("create_sketch_on_face", x=0.0, y=30.0, z=15.0, unit="mm")
    if not ok:
        record("S3 schizzo sulla faccia", False, text[:120])
        await discard_all(c)
        return
    o, ux, uy = info["sketch_origin_mm"], info["sketch_x_axis"], info["sketch_y_axis"]

    def uv(P):
        dd = [P[i] - o[i] for i in range(3)]
        return sum(dd[i] * ux[i] for i in range(3)), sum(dd[i] * uy[i] for i in range(3))
    a, b = uv([0.0, 30.0, -1.0]), uv([0.0, 30.0, 31.0])
    await c.call("draw_line", x1=a[0], y1=a[1], x2=b[0], y2=b[1], unit="mm")
    ok, text, d = await c.call("sm_sketched_bend", angle=90, bend_radius=2, position="material_inside")
    v1 = d.get("volume_mm3", 0.0) if ok else 0.0
    record("S3 piega 90 gradi: volume conservato (0,5 %)", ok and near(v1, v0, tol=TOL_BEND),
           f"{ok} {text[:80]} volume {v1} (prima {v0})")
    mn, mx = await box(c)
    ba = math.pi / 2 * (2 + 0.5 * 2)
    tratto_b = 60 - (30 - 4) - ba
    x_calc = 2 + tratto_b
    record("S3 ingombro X dopo la piega = 31,28761 (calcolato)", mx is not None and near(mx[0], x_calc, absolute=0.01),
           f"X max {mx[0] if mx else None} (calcolato {x_calc:.5f}; BA {ba:.5f}, tratto B {tratto_b:.5f})")
    record("S3 ingombro Y dopo la piega = 30 mm", mx is not None and near(mx[1], 30.0, absolute=0.01),
           f"Y max {mx[1] if mx else None}")
    okf, tf, fd = await c.call("sm_flatten", flat=True)
    size = fd.get("box_size_mm") if okf else None
    record("S3 sviluppo = 60 mm (lunghezza della lamiera piana)", okf and size is not None and near(size[1], 60.0, tol=0.003)
           and near(size[0], 2.0, absolute=0.01), f"{okf} box flat {size} (calcolato Y 60, X 2)")
    okb, tb, bd = await c.call("sm_flatten", flat=False)
    sup = bd.get("suppressed") if okb else None
    record("S3 ripiegata: sviluppo soppresso", okb and sup is not None and all(sup.values()), f"{okb} {sup}")
    await discard_all(c)


# ===================================================================================================== S4 parametri
async def s4_params(c):
    print("\nS4 sm_parameters")
    await discard_all(c)
    await new_part(c)
    await rect_sketch(c, 50, 30)
    await c.call("sm_base_flange", thickness=2, bend_radius=2, k_factor=0.5)
    ok, text, d = await c.call("sm_parameters")
    record("S4 lettura: 2 mm, raggio 2 mm, K 0,5", ok and near(d.get("thickness_mm", 0), 2.0, absolute=1e-6)
           and near(d.get("bend_radius_mm", 0), 2.0, absolute=1e-6) and near(d.get("k_factor", 0), 0.5, absolute=1e-6),
           f"{ok} {d}")
    ok, text, d = await c.call("sm_parameters", thickness=3)
    v = d.get("volume_mm3", 0.0) if ok else 0.0
    record("S4 spessore 2 -> 3: volume 4500 mm3", ok and near(v, 4500.0) and near(d.get("thickness_mm", 0), 3.0, absolute=1e-6),
           f"{ok} volume {v} (calcolato 4500) spessore {d.get('thickness_mm')} flange {d.get('updated_base_flanges')}")
    await discard_all(c)



# ===================================================================================================== S5 export DXF
async def s5_export(c):
    print("\nS5 sm_export_flat_pattern")
    await discard_all(c)
    await new_part(c)
    ok, text, d = await c.call("sm_export_flat_pattern", filepath=os.path.join(OUT, "sm_flat_nosave.dxf"))
    record("S5 pezzo non salvato: rifiutato con richiesta di salvataggio", (not ok) and "salvalo" in text.lower(), text[:120])
    await discard_all(c)
    await new_part(c)
    await rect_sketch(c, 50, 30)
    await c.call("sm_base_flange", thickness=2, bend_radius=2, k_factor=0.5)
    src = os.path.join(OUT, "sm_flat_src.sldprt")
    okS, textS, _ = await c.call("save_document", filepath=src, overwrite=True)
    dxf = os.path.join(OUT, "sm_flat.dxf")
    ok, text, d = await c.call("sm_export_flat_pattern", filepath=dxf, overwrite=True)
    content = b""
    if os.path.exists(dxf):
        with open(dxf, "rb") as fh:
            content = fh.read()
    record("S5 export DXF: file > 0 byte e contiene ENTITIES", okS and ok and len(content) > 0 and b"ENTITIES" in content,
           f"salvataggio {okS} export {ok} {text[:80]} byte {len(content)}")
    await discard_all(c)

# ===================================================================================================== principale
# ===================================================================================================== S6 flangia sul bordo
async def s6_edge(c):
    print("\nS6 sm_edge_flange")
    await discard_all(c)
    await new_part(c)
    await rect_sketch(c, 50, 30)
    ok, text, _ = await c.call("sm_base_flange", thickness=2, bend_radius=2, k_factor=0.5)
    ok, text, d = await c.call("sm_edge_flange", edge_point=[0, 50, 15], length=20, angle=90, bend_radius=2, unit="mm")
    v = d.get("volume_mm3", 0.0) if ok else 0.0
    exp = 2 * 30 * ((50 - 4) + (22 - 4) + math.pi / 2 * (2 + 1))
    record("S6 flangia 90 gradi, profilo 20 su lamiera 50x30x2 r2 K0,5: volume calcolato", ok and near(v, exp),
           f"{ok} {text[:80]} volume {v} (calcolato {exp:.3f})")
    mn, mx = await box(c)
    record("S6 ingombro X della flangia = 20 (profilo dalla faccia x=0)", mx is not None and near(mx[0], 20.0, absolute=0.01),
           f"box min {mn} max {mx}")
    okf, _, _ = await c.call("sm_flatten", flat=True)
    mn, mx = await box(c)
    flat = 46 + 18 + math.pi / 2 * (2 + 0.5 * 2)
    record("S6 sviluppo = 46 + 18 + pi/2*(r+K*t) = 68,712", okf and mx is not None and near(mx[1] - mn[1], flat, absolute=0.01),
           f"box min {mn} max {mx} (calcolato {flat:.4f})")
    await c.call("sm_flatten", flat=False)
    ok, text, d = await c.call("sm_edge_flange", edge_point=[-2, 0, 15], length=15, angle=45, unit="mm")
    record("S6 seconda flangia a 45 gradi sull'altro bordo: volume aumenta", ok and d.get("volume_delta_mm3", 0) > 0,
           f"{ok} {text[:100]}")
    ok, text, _ = await c.call("sm_edge_flange", edge_point=[-1, 25, 30.5], length=10, unit="mm")
    record("S6 punto non su uno spigolo: rifiutato", not ok, text[:100])
    await discard_all(c)


async def scenario(c):
    only = {a.upper() for a in sys.argv[1:]}
    for nome, fn in (("S1", s1_base), ("S2", s2_hem), ("S3", s3_bend), ("S4", s4_params), ("S5", s5_export), ("S6", s6_edge)):
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
                record("tool lamiera esposti", all(t in tools for t in (
                    "sm_base_flange", "sm_hem", "sm_sketched_bend", "sm_flatten", "sm_parameters",
                    "sm_export_flat_pattern")), "")
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
