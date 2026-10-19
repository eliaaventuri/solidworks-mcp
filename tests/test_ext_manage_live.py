"""
Test live del lotto MANAGE (analisi e gestione del modello) tramite il server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente non viene mai
toccata; alla fine si chiude solo il PID lanciato dal test.

  G1  check_geometry: blocco 20x20x10 sano -> 0 difetti, 0 errori, ok=true
  G2  check_geometry: taglio cilindrico portato fuori dal blocco -> errore vero di SW (codice 71), ok=false
  R1  reorder_feature: due estrusioni indipendenti, B spostata prima di A -> indice di B < indice di A; volume invariato
  R2  reorder_feature: feature inesistente e posizione non valida rifiutate
  F1  create_feature_folder: cartella 'Corpo' di tipo FtrFolder, feature dentro, volume invariato (20x20x10 = 4000 mm3)
  A1  set_appearance pezzo rosso [255,0,0] -> R letto 1,0
  A2  set_appearance faccia blu (punto su x=10) -> B letto 1,0
  A3  set_appearance pezzo trasparenza 0,5 -> letta 0,5
  A4  set_appearance feature verde con trasparenza 0,25 -> G 1,0 e trasparenza 0,25
  A5  set_appearance corpo (indice 0) blu -> B letto 1,0
  E1  edit_sketch Schizzo1 + cerchio r=5 + close_sketch + rebuild: volume -pi*25*10 = 785,398 mm3 (0,5 %)
  P1  change_sketch_plane Schizzo1 su Top: normale da Front a Top (perpendicolari, uguale a uno schizzo nuovo su Top), volume invariato

Uso:  .venv\\Scripts\\python.exe tests\\test_ext_manage_live.py [G R F A E P]
Output: test_output\\ (file manage_*)
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
TOL = 0.005          # 0,5 % sui volumi


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:260])


def near(got, exp, tol=TOL, absolute=None):
    if absolute is not None:
        return abs(got - exp) <= absolute
    return abs(got - exp) <= tol * max(abs(exp), 1e-9)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


async def vol(c):
    ok, _, d = await c.call("get_mass_properties")
    return d.get("volume_mm3", 0.0) if ok else 0.0


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


async def block(c, depth=10):
    """Blocco 20x20x10: schizzo sul piano frontale 0..20 estruso di depth."""
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=0, y1=0, x2=20, y2=20)
    ok, text, d = await c.call("extrude_boss", depth=depth)
    assert ok, text


# ===================================================================================================== G
async def g_geometry(c):
    print("\n== G. check_geometry")
    await new_part(c)
    await block(c)
    ok, text, d = await c.call("check_geometry")
    record("G1 blocco sano: 0 difetti, 0 errori, ok=true", ok and d.get("ok") is True and len(d.get("bodies_with_defects", [])) == 0
           and len(d.get("features_with_errors", [])) == 0 and d["bodies"][0]["defects"] == 0,
           f"{text[:90]}")
    await discard_all(c)

    # G2: errore vero di ricostruzione. Cerchio r=5 sulla faccia x=10, centro a 3 mm dall'origine dello schizzo
    # (quota orizzontale centro-punto origine, SW rifiuta la quota a 0), taglio 5 mm verso l'interno (senza reverse).
    # Quota portata a 100 mm: il cerchio esce dal blocco, il taglio non interseca piu' il corpo -> errore SolidWorks.
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-20, y1=-20, x2=20, y2=20)
    await c.call("extrude_boss", depth=10)                  # blocco 40x40x10 centrato, faccia x=10
    v0 = await vol(c)
    await c.call("create_sketch_on_face", x=10, y=0, z=0)
    ok1, _, dc = await c.call("draw_circle", x=3, y=0, radius=5)
    ok2, _, dp = await c.call("draw_point", x=0, y=0)
    ok3, _, dd = await c.call("add_sketch_dimension", kind="horizontal", entity1=dc.get("center_point_id"),
                              entity2=dp.get("point_id"), value=3, name="posx")
    await c.call("close_sketch")
    ok4, _, dcut = await c.call("extrude_cut", sketch="Schizzo2", depth=5)
    await c.call("rebuild_model")
    v1 = await vol(c)
    ok5, text5, _ = await c.call("set_dimension_value", name="posx@Schizzo2", value=100, unit="mm")
    await c.call("rebuild_model")
    ok6, _, cg = await c.call("check_geometry")
    errs = cg.get("features_with_errors", []) if ok6 else []
    cut_err = [e for e in errs if str(e.get("name", "")).startswith("Taglio")]
    code = cut_err[0].get("error_code", 0) if cut_err else 0
    record("G2 taglio fuori dal blocco: check_geometry riporta la feature con codice errore != 0 e ok=false",
           ok1 and ok2 and ok3 and ok4 and near(v0 - v1, 392.699, absolute=0.5) and ok5 and ok6
           and cg.get("ok") is False and bool(cut_err) and code != 0,
           f"volume taglio dentro {v0 - v1:.3f} (atteso 392,699); feature {[e.get('name') for e in errs]} codice {code}; ok={cg.get('ok')}")
    await discard_all(c)


# ===================================================================================================== R
async def r_reorder(c):
    print("\n== R. reorder_feature")
    await new_part(c)
    await block(c)                                                # Estrusione-Estrusione1 (4000 mm3)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_rectangle", x1=30, y1=0, x2=40, y2=10)
    await c.call("extrude_boss", depth=5)                         # Estrusione-Estrusione2 (500 mm3)
    v0 = await vol(c)
    ok, text, d = await c.call("reorder_feature", name="Estrusione-Estrusione2", target="Estrusione-Estrusione1",
                               position="before")
    order = d.get("order_after", []) if ok else []
    ib = order.index("Estrusione-Estrusione2") if "Estrusione-Estrusione2" in order else 999
    ia = order.index("Estrusione-Estrusione1") if "Estrusione-Estrusione1" in order else -1
    v1 = await vol(c)
    record("R1 B prima di A: indice B < indice A, volume invariato (4500 mm3)",
           ok and ib < ia and near(v0, 4500) and near(v1, 4500),
           f"indice B {ib} < indice A {ia}; volume {v0:.1f} -> {v1:.1f} mm3; {text[:70]}")
    ok2, text2, _ = await c.call("reorder_feature", name="NonEsiste", position="end")
    record("R2a feature inesistente: rifiutata", not ok2, text2.split("\n")[0][:100])
    ok3, text3, _ = await c.call("reorder_feature", name="Estrusione-Estrusione2", position="sopra")
    record("R2b posizione non valida: rifiutata", not ok3, text3.split("\n")[0][:100])
    await discard_all(c)


# ===================================================================================================== F
async def f_folder(c):
    print("\n== F. create_feature_folder")
    await new_part(c)
    await block(c)
    v0 = await vol(c)
    ok, text, d = await c.call("create_feature_folder", features=["Estrusione-Estrusione1"], name="Corpo")
    v1 = await vol(c)
    ok2, _, lf = await c.call("list_model_features")
    names = [f.get("name") for f in lf.get("features", [])] if ok2 else []
    tipo = d.get("folder_type") if ok else None
    print(f"    tipo letto con GetTypeName2: {tipo}")
    record("F1 cartella 'Corpo' (tipo {}) con la feature dentro, volume invariato 4000 mm3".format(tipo),
           ok and tipo == "FtrFolder" and "Corpo" in names and near(v0, 4000) and near(v1, 4000),
           f"volume {v0:.1f} -> {v1:.1f} mm3; {text[:80]}")
    await discard_all(c)


# ===================================================================================================== A
def _rgb_ok(rd, exp, tr=None, tr_exp=None):
    rgb = d_rgb(rd)
    good = rgb is not None and all(abs(a - b) <= 0.001 for a, b in zip(rgb, exp))
    if tr is not None and tr_exp is not None:
        good = good and abs(rd.get("transparency_read", -1) - tr_exp) <= 0.001
    return good


def d_rgb(d):
    return d.get("rgb_read_0_1") if isinstance(d, dict) else None


async def a_appearance(c):
    print("\n== A. set_appearance")
    await new_part(c)
    await block(c)
    ok, text, d = await c.call("set_appearance", target="part", color=[255, 0, 0])
    record("A1 pezzo rosso [255,0,0]: R letto 1,0", ok and _rgb_ok(d, [1.0, 0.0, 0.0]),
           f"RGB letto {d.get('rgb_read_0_1')}")
    ok, text, d = await c.call("set_appearance", target="face", color=[0, 0, 255], face_point=[10, 10, 10])
    record("A2 faccia blu (x=10): B letto 1,0", ok and _rgb_ok(d, [0.0, 0.0, 1.0]), f"RGB letto {d.get('rgb_read_0_1')} {text[:60] if not ok else ''}")
    ok, text, d = await c.call("set_appearance", target="part", color=[255, 0, 0], transparency=0.5)
    record("A3 trasparenza 0,5: letta 0,5", ok and abs(d.get("transparency_read", -1) - 0.5) <= 0.001,
           f"trasparenza letta {d.get('transparency_read')}")
    ok, text, d = await c.call("set_appearance", target="feature", feature="Estrusione-Estrusione1", color=[0, 255, 0],
                               transparency=0.25)
    record("A4 feature verde con trasparenza 0,25: G 1,0 e trasparenza 0,25",
           ok and _rgb_ok(d, [0.0, 1.0, 0.0]) and abs(d.get("transparency_read", -1) - 0.25) <= 0.001,
           f"RGB {d.get('rgb_read_0_1')} trasparenza {d.get('transparency_read')}")
    ok, text, d = await c.call("set_appearance", target="body", body=0, color=[0, 0, 255])
    record("A5 corpo (indice 0) blu: B letto 1,0", ok and _rgb_ok(d, [0.0, 0.0, 1.0]), f"RGB {d.get('rgb_read_0_1')}")
    await discard_all(c)


# ===================================================================================================== E
async def e_edit(c):
    print("\n== E. edit_sketch")
    await new_part(c)
    await block(c)
    v0 = await vol(c)
    ok, text, d = await c.call("edit_sketch", sketch="Schizzo1")
    ok2, text2, _ = await c.call("draw_circle", x=10, y=10, radius=5)
    ok3, _, _ = await c.call("close_sketch")
    ok4, _, _ = await c.call("rebuild_model")
    v1 = await vol(c)
    exp = v0 - math.pi * 25 * 10
    record("E1 foro r=5 in Schizzo1 riaperto: volume -pi*25*10 = 785,398 mm3 (0,5 %)",
           ok and ok2 and ok3 and ok4 and near(v0 - v1, math.pi * 25 * 10) and near(v1, exp),
           f"volume {v0:.3f} -> {v1:.3f} mm3, differenza {v0 - v1:.3f} (atteso {math.pi * 25 * 10:.3f}); {text[:60]}")
    await discard_all(c)


# ===================================================================================================== P
async def p_plane(c):
    print("\n== P. change_sketch_plane")
    await new_part(c)
    await block(c)
    v0 = await vol(c)
    ok0, _, i0 = await c.call("get_sketch_plane_info", sketch="Schizzo1")
    await c.call("close_sketch")
    n0 = i0.get("sketch_normal", [0, 0, 0]) if ok0 else [0, 0, 0]
    ok, text, d = await c.call("change_sketch_plane", sketch="Schizzo1", plane="Top")
    v1 = await vol(c)
    n1 = d.get("plane_after", {}).get("sketch_normal", [0, 0, 0]) if ok else [0, 0, 0]
    # riferimento: normale di uno schizzo nuovo sul piano Top
    await c.call("create_sketch", plane="Top")
    okr, _, ir = await c.call("get_sketch_plane_info")
    await c.call("close_sketch")
    nref = ir.get("sketch_normal", [0, 0, 0]) if okr else [0, 0, 0]
    perp = abs(dot(n0, n1)) <= 1e-6
    same = all(abs(a - b) <= 1e-6 for a, b in zip(n1, nref))
    record("P1 normale Front -> Top (perpendicolari, uguale a uno schizzo nuovo su Top), volume invariato 4000 mm3",
           ok and perp and same and near(v0, 4000) and near(v1, 4000),
           f"normale prima {n0} dopo {n1} riferimento Top {nref}; volume {v0:.1f} -> {v1:.1f} mm3")
    await discard_all(c)


# ===================================================================================================== principale
SECTIONS = (("G", g_geometry), ("R", r_reorder), ("F", f_folder), ("A", a_appearance), ("E", e_edit), ("P", p_plane))


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
                record("tool nuovi esposti", all(t in tools for t in (
                    "check_geometry", "reorder_feature", "create_feature_folder", "set_appearance", "edit_sketch",
                    "change_sketch_plane")), "")
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
