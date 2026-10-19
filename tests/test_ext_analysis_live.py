"""
Test live del lotto ANALYSIS (analisi e riferimenti) tramite il server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente non viene mai
toccata; alla fine si chiude solo il PID lanciato dal test.

  B1  insert_bounding_box: blocco 40x30x20 -> lati 40, 30, 20 (ordinati)
  B2  insert_bounding_box con best_fit=false: rifiutato (solo il box a migliore adattamento)
  C1  insert_center_of_mass: blocco 20(X) x 40(Y) x 30(Z) estruso da 0 a 20 lungo X e centrato su Y, Z -> baricentro (10, 0, 0) mm
  C2  insert_mate_reference: riferimento 'RifTop' sulla faccia superiore (z = 15) -> feature col nome dato e tipo letto
  C3  insert_mate_reference con punto lontano dalle facce: rifiutato
  D1  draft_analysis: tronco (quadrato 30x30 alto 20, sformo 5 gradi verso l'interno) -> 4 facce laterali +5,0; 2 piane 90
  D2  draft_analysis: cilindro estruso senza sformo -> faccia cilindrica 0,0
  D3  draft_analysis con direzione non valida: rifiutata
  T1  thickness_analysis: blocco pieno 40x30x20 -> minimo 20 mm (la dimensione piu' piccola)
  T2  thickness_analysis: guscio di blocco spessore 2 (shell_body) -> minimo 2,0 mm; massimo <= 2 * diagonale
  S1  section_view: con la sezione l'immagine esportata cambia (dimensione file diversa); volume invariato
  S2  section_view remove=true: sezione tolta, volume invariato
  F1  fully_define_sketch: rettangolo libero -> sottodefinito prima, completamente definito dopo, quote >= 2

Uso:  .venv\\Scripts\\python.exe tests\\test_ext_analysis_live.py [B C D T S F]
Output: test_output\\ (file ana_*)
"""

import os
import sys
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, PYTHON, SERVER, OUT, sw_pids, Client, cleanup

RESULTS = []         # (nome, PASS/FAIL, nota)
TOL = 0.005          # 0,5 % sui valori misurati, salvo dove dichiarato


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:260])


def near(got, exp, tol=TOL, absolute=None):
    if got is None:
        return False
    if absolute is not None:
        return abs(got - exp) <= absolute
    return abs(got - exp) <= tol * max(abs(exp), 1e-9)


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


async def block(c):
    """Blocco: schizzo sul piano Front -20..20 x -15..15, estruso di 20 (in questa installazione l'estrusione va lungo X:
    corpo 0..20 in X, -20..20 in Y, -15..15 in Z; misurato con GetBodyBox e BoundingBox)."""
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-20, y1=-15, x2=20, y2=15)
    ok, text, d = await c.call("extrude_boss", depth=20)
    assert ok, text


# ===================================================================================================== B
async def b_bbox(c):
    print("\n== B. insert_bounding_box")
    await new_part(c)
    await block(c)
    ok, text, d = await c.call("insert_bounding_box", best_fit=True, include_surfaces=False, unit="mm")
    sizes = d.get("sizes") or []
    exp = [40.0, 30.0, 20.0]
    record("B1 box di delimitazione 40x30x20 -> lati 40, 30, 20 (ordinati)",
           ok and len(sizes) == 3 and all(near(a, b, absolute=0.005 * b) for a, b in zip(sizes, exp)),
           f"letti {sizes} mm, feature {d.get('feature')} ({d.get('type')}): {text[:80]}")
    ok2, text2, d2 = await c.call("insert_bounding_box", best_fit=False, include_surfaces=False, unit="mm")
    record("B2 best_fit=false rifiutato (solo migliore adattamento)", not ok2, text2[:100])
    await discard_all(c)


# ===================================================================================================== C
async def c_com_mate(c):
    print("\n== C. insert_center_of_mass e insert_mate_reference")
    await new_part(c)
    await block(c)
    ok, text, d = await c.call("insert_center_of_mass", unit="mm")
    com = d.get("center_of_mass") or [None, None, None]
    exp = [10.0, 0.0, 0.0]          # calcolato: estrusione 0..20 in X (centro 10), Y e Z simmetrici (0)
    record("C1 baricentro del blocco = (10, 0, 0) mm",
           ok and all(near(a, b, absolute=0.01) for a, b in zip(com, exp)),
           f"letto {com} mm; feature {d.get('features')}: {text[:60]}")

    await new_part(c)
    await block(c)
    ok, text, d = await c.call("insert_mate_reference", name="RifTop", face_point=[10, 0, 15],
                               type="coincident", alignment="any", unit="mm")
    fname = d.get("feature") or ""
    record("C2 riferimento 'RifTop' sulla faccia superiore (z = 15 mm): feature col nome dato",
           ok and fname.startswith("RifTop"),
           f"feature '{fname}' tipo '{d.get('type')}' (letto con GetTypeName2): {text[:80]}")

    ok3, text3, _ = await c.call("insert_mate_reference", name="RifLontano", face_point=[10, 0, 50],
                                 type="coincident", alignment="any", unit="mm")
    record("C3 punto lontano da ogni faccia (z = 50 mm): rifiutato", not ok3, text3[:100])
    await discard_all(c)


# ===================================================================================================== D
async def d_draft(c):
    print("\n== D. draft_analysis")
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-15, y1=-15, x2=15, y2=15)
    ok0, t0, _ = await c.call("extrude_boss", depth=20)
    # tronco: sformo 5 gradi verso l'interno (la sezione si restringe andando lungo X)
    ok1, t1, _ = await c.call("draft_faces", angle=5, faces=[[10, 15, 0], [10, -15, 0], [10, 0, 15], [10, 0, -15]],
                              neutral_face_point=[0, 0, 0], flip=True, unit="mm")
    ok, text, d = await c.call("draft_analysis", direction="x", min_angle=1.0)
    faces = d.get("faces", [])
    side = [f["sformo_deg"] for f in faces if f.get("class") not in ("flat", "not_applicable")]
    flat = [f["sformo_deg"] for f in faces if f.get("class") == "flat"]
    record("D1 tronco 30x30 alto 20 con sformo 5 gradi: 4 facce laterali +5,0 (entro 0,01), 2 piane 90",
           ok0 and ok1 and ok and len(side) == 4 and all(near(s, 5.0, absolute=0.01) for s in side)
           and len(flat) == 2 and all(near(f, 90.0, absolute=0.01) for f in flat),
           f"laterali {side}, piane {flat}; draft_faces: {t1[:60]}")

    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=5, unit="mm")
    ok2, t2, _ = await c.call("extrude_boss", depth=20)
    ok, text, d = await c.call("draft_analysis", direction="x", min_angle=1.0)
    cyl = [f["sformo_deg"] for f in d.get("faces", []) if f.get("type") == "cylinder"]
    record("D2 cilindro estruso senza sformo: faccia cilindrica 0,0 (entro 0,01)",
           ok2 and ok and len(cyl) == 1 and near(cyl[0], 0.0, absolute=0.01), f"cilindrica {cyl}")

    ok3, text3, _ = await c.call("draft_analysis", direction="w", min_angle=1.0)
    record("D3 direzione non valida ('w') rifiutata", not ok3, text3[:100])
    await discard_all(c)


# ===================================================================================================== T
async def t_thickness(c):
    print("\n== T. thickness_analysis")
    await new_part(c)
    await block(c)
    ok, text, d = await c.call("thickness_analysis", samples=400, unit="mm")
    record("T1 blocco pieno 40x30x20 -> minimo 20 mm (la dimensione piu' piccola, entro 0,1 mm)",
           ok and near(d.get("min"), 20.0, absolute=0.1),
           f"minimo {d.get('min')}, massimo {d.get('max')}, raggi {d.get('valid')}/{d.get('rays')}: {text[:60]}")

    okS, textS, _ = await c.call("shell_body", thickness=2, remove_faces=[[20, 0, 0]], unit="mm")
    ok2, text2, d2 = await c.call("thickness_analysis", samples=400, unit="mm")
    diag = (40.0 ** 2 + 30.0 ** 2 + 20.0 ** 2) ** 0.5
    mx = d2.get("max") or 0.0
    record("T2 guscio spessore 2 (shell_body): minimo 2,0 mm (entro 0,01), massimo <= 2 x diagonale",
           okS and ok2 and near(d2.get("min"), 2.0, absolute=0.01) and mx <= 2 * diag,
           f"minimo {d2.get('min')}, massimo {mx} (2 x diagonale {2 * diag:.2f}), raggi {d2.get('valid')}/{d2.get('rays')}")
    await discard_all(c)


# ===================================================================================================== S
async def s_section(c):
    print("\n== S. section_view")
    await new_part(c)
    await block(c)
    v0 = await vol(c)
    img0 = str(OUT / "ana_sez_0.png")
    img1 = str(OUT / "ana_sez.png")
    ok0, t0, _ = await c.call("export_model_image", filepath=img0, view="isometric", width=800, height=600)
    ok1, t1, _ = await c.call("section_view", plane="Front", offset=10, unit="mm")
    ok2, t2, _ = await c.call("export_model_image", filepath=img1, view="isometric", width=800, height=600)
    s0 = os.path.getsize(img0) if os.path.exists(img0) else -1
    s1 = os.path.getsize(img1) if os.path.exists(img1) else -1
    v1 = await vol(c)
    record("S1 sezione attiva: immagine diversa (dimensione file) e volume invariato",
           ok0 and ok1 and ok2 and s0 > 0 and s1 > 0 and s0 != s1 and near(v1, v0),
           f"file senza sezione {s0} B, con sezione {s1} B, volume {v0:.1f} -> {v1:.1f} mm3")

    ok3, t3, d3 = await c.call("section_view", remove=True)
    v2 = await vol(c)
    record("S2 section_view remove=true: sezione tolta, volume invariato",
           ok3 and d3.get("removed") is True and near(v2, v0),
           f"tolta {d3.get('removed')}, volume {v2:.1f} mm3 (prima {v0:.1f})")
    await discard_all(c)


# ===================================================================================================== F
async def f_fully(c):
    print("\n== F. fully_define_sketch")
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_rectangle", x1=0, y1=0, x2=30, y2=20)
    ok0, t0, d0 = await c.call("get_sketch_definition_status")
    before = d0.get("status") if ok0 else None
    ok, text, d = await c.call("fully_define_sketch", use_dimensions=True, use_relations=True)
    ok1, text1, d1 = await c.call("get_sketch_definition_status")
    dims = d1.get("dimensions", []) if ok1 else []
    record("F1 rettangolo libero -> sottodefinito, poi completamente definito con quote >= 2",
           ok0 and before == "sottodefinito" and ok and ok1 and d1.get("fully_defined") is True and len(dims) >= 2,
           f"prima '{before}', dopo '{d1.get('status')}', quote {len(dims)}: {[x.get('value') for x in dims]}")
    await discard_all(c)


SECTIONS = [("B", b_bbox), ("C", c_com_mate), ("D", d_draft), ("T", t_thickness), ("S", s_section), ("F", f_fully)]


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
                    "insert_bounding_box", "insert_center_of_mass", "insert_mate_reference", "draft_analysis",
                    "thickness_analysis", "section_view", "fully_define_sketch")), "")
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
