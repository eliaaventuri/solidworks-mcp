"""
Test live delle correzioni della revisione 2026-11-12 (sezione 1, falsi successi confermati [V], e sezione 2) tramite il server
MCP (stdio). Ogni controllo confronta un numero misurato da SolidWorks con un valore calcolato.

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente non viene mai
toccata; alla fine si chiude solo il PID lanciato dal test.

  S  sweep: torsione di 90 gradi di un rettangolo 20x10 lungo 50 mm (ingombro 22,36 x 22,36 x 50, volume 10000) e
     keep_normal=false lungo un arco di 60 gradi R30 (volume pi*9*25,98 = 734,6 contro pi*9*31,42 = 888,3 seguendo il percorso)
  P  create_sketch su un piano di riferimento per nome (normale = quella del piano frontale), piano inesistente rifiutato,
     schizzo gia' aperto chiuso prima (non alternato)
  Q  suppress/unsuppress con stato riletto (volume del foro), close_sketch riletto
  E  add_equation: equazione sana (raccordo r=3: volume 16000 - 0,8584*9*40) e equazione che manda in errore il raccordo
     (r=30 su un blocco alto 10): rimossa, volume invariato
  M  assign_material con materiale riletto
  C  create_drawing: modello con modifiche non salvate NON salvato (data del file invariata); save_as impossibile -> errore;
     set_dimension_tolerance: quota '40' ambigua rifiutata, poi +-0,1 riletta
  X  auto_explode axis='-x' senza componenti fissi: il componente all'estremo -x si allontana verso -x (posa esplosa -30 mm)
  K  set_sketch_performance_mode: valori precedenti riportati e ripristinabili

Uso:  .venv\\Scripts\\python.exe tests\\test_review_v_live.py [S P Q E M C X K]
Output: test_output\\ (file rv_*)
"""

import os
import sys
import math
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup

RESULTS = []
PI = math.pi


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:300])


def rel(got, exp):
    return abs(got - exp) / max(abs(exp), 1e-9)


def close(label, got, exp, tol=0.002):
    got = float(got if got is not None else float("nan"))
    record(label, rel(got, exp) < tol, f"misurato {got:.4f}, atteso {exp:.4f}, scarto {rel(got, exp) * 100:.4f} %")


async def vol(c):
    ok, _, d = await c.call("get_mass_properties")
    return d.get("volume_mm3", 0.0) if ok else 0.0


async def box_sizes(c):
    ok, _, d = await c.call("get_bounding_box")
    s = d.get("size") or d.get("size_mm") or []
    if isinstance(s, dict):
        s = [s.get(k) for k in ("x", "y", "z")]
    return sorted(float(v) for v in s) if ok and s else []


async def discard_all(c):
    for _ in range(40):
        ok, _, d = await c.call("list_open_documents")
        docs = d.get("documents", []) if ok else []
        if not docs:
            return
        await c.call("close_document", discard=True, document=docs[0]["title"])


async def new_part(c):
    await discard_all(c)
    ok, text, _ = await c.call("create_new_part")
    assert ok, text


async def last_sketch_name(c):
    ok, _, d = await c.call("list_model_features")
    names = [f["name"] for f in d.get("features", []) if f.get("type") in ("ProfileFeature", "3DProfileFeature")]
    return names[-1] if names else None


async def block(c, w=40, h=10):
    """Blocco w x w x h (Top: x,y -w/2..w/2, z 0..h)."""
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_rectangle", x1=-w / 2, y1=-w / 2, x2=w / 2, y2=w / 2)
    await c.call("close_sketch")
    ok, text, d = await c.call("extrude_boss", depth=h)
    assert ok, text
    return d


# =========================================================================================================== S
async def s_sweep(c):
    print("\n== S. sweep: torsione e orientamento del profilo")

    async def straight():
        await new_part(c)
        await c.call("create_sketch", plane="Front")
        await c.call("draw_line", x1=0, y1=0, x2=50, y2=0)
        await c.call("close_sketch")
        path = await last_sketch_name(c)
        await c.call("create_sketch", plane="Right")
        await c.call("draw_rectangle", x1=-10, y1=-5, x2=10, y2=5)
        await c.call("close_sketch")
        return path, await last_sketch_name(c)

    path, prof = await straight()
    ok, text, d = await c.call("sweep", profile_sketch=prof, path_sketch=path)
    record("S1 sweep senza torsione: riuscito, controllo 0 (segue il percorso)", ok and d.get("twist_control_readback") == 0,
           text[:120])
    sz = await box_sizes(c)
    record("S1 ingombro senza torsione 10 x 20 x 50", len(sz) == 3 and all(rel(a, b) < 0.002 for a, b in zip(sz, [10, 20, 50])), str(sz))

    path, prof = await straight()
    ok, text, d = await c.call("sweep", profile_sketch=prof, path_sketch=path, twist_angle=90)
    record("S2 sweep con twist_angle=90: riuscito, controllo riletto 8 (torsione costante)",
           ok and d.get("twist_control_readback") == 8, f"{text[:100]} | letto {d.get('twist_control_readback')}")
    if d.get("twist_angle_readback_rad") is not None:
        close("S2 angolo di torsione riletto (gradi)", math.degrees(float(d["twist_angle_readback_rad"])), 90.0, 1e-6)
    close("S2 volume della torsione = 20*10*50 (sezioni uguali)", await vol(c), 10000.0)
    sz = await box_sizes(c)
    lato = 2 * math.sqrt(10 ** 2 + 5 ** 2)
    record(f"S2 ingombro con torsione {lato:.4f} x {lato:.4f} x 50 (il rettangolo ruota di 90 gradi)",
           len(sz) == 3 and all(rel(a, b) < 0.003 for a, b in zip(sz, [lato, lato, 50])), str([round(v, 4) for v in sz]))

    ok, text, _ = await c.call("sweep", profile_sketch=prof, path_sketch=path, twist_angle=45, keep_normal=False)
    record("S3 torsione con keep_normal=false: rifiutata con spiegazione", not ok and "keep_normal" in text, text[:110])

    async def arc():
        await new_part(c)
        await c.call("create_sketch", plane="Front")
        await c.call("draw_arc", cx=0, cy=30, radius=30, start_angle=-90, end_angle=-30)
        await c.call("close_sketch")
        path = await last_sketch_name(c)
        await c.call("create_sketch", plane="Right")
        await c.call("draw_circle", x=0, y=0, radius=3)
        await c.call("close_sketch")
        return path, await last_sketch_name(c)

    path, prof = await arc()
    ok, text, d = await c.call("sweep", profile_sketch=prof, path_sketch=path)
    record("S4 arco di 60 gradi, profilo che segue il percorso: controllo 0", ok and d.get("twist_control_readback") == 0, text[:100])
    close("S4 volume = pi r^2 * lunghezza dell'arco (Pappo)", await vol(c), PI * 9 * 30 * PI / 3)
    path, prof = await arc()
    ok, text, d = await c.call("sweep", profile_sketch=prof, path_sketch=path, keep_normal=False)
    record("S5 keep_normal=false: controllo riletto 1 (normale costante)", ok and d.get("twist_control_readback") == 1,
           f"{text[:100]} | letto {d.get('twist_control_readback')}")
    close("S5 volume = pi r^2 * spostamento lungo la normale (30 cos 30)", await vol(c), PI * 9 * 30 * math.cos(math.radians(30)))
    await discard_all(c)


# =========================================================================================================== P
async def p_planes(c):
    print("\n== P. create_sketch: piano per nome, piano inesistente, schizzo gia' aperto")
    await block(c)
    ok, _, df = await c.call("create_sketch", plane="Front")
    n_front = df.get("sketch_normal")
    await c.call("close_sketch")
    ok, text, dp = await c.call("create_reference_plane", mode="offset", base="front", distance=15)
    pname = dp.get("feature") or dp.get("plane") or dp.get("name")
    record("P0 piano di riferimento a 15 mm dal frontale", ok and bool(pname), f"{pname}: {text[:80]}")
    ok, text, d = await c.call("create_sketch", plane=pname)
    n = d.get("sketch_normal")
    dot = abs(sum(a * b for a, b in zip(n or [0, 0, 0], n_front or [0, 0, 0])))
    record("P1 schizzo sul piano per nome: riuscito, su quel piano, normale parallela al frontale",
           ok and d.get("plane_feature") == pname and abs(dot - 1) < 1e-6, f"{text[:80]} | normale {n} vs {n_front}")
    org = d.get("sketch_origin_mm") or [0, 0, 0]
    o_front = df.get("sketch_origin_mm") or [0, 0, 0]
    off = abs(sum((a - b) * nn for a, b, nn in zip(org, o_front, n_front or [0, 0, 0])))
    close("P2 origine dello schizzo a 15 mm dal piano frontale (lungo la normale)", off, 15.0, 1e-6)
    ok2, _, ds = await c.call("create_sketch", plane="Top")
    record("P3 create_sketch con uno schizzo gia' aperto: il nuovo schizzo e' aperto sul piano superiore",
           ok2 and ds.get("sketch_normal") is not None and abs(abs(sum(a * b for a, b in zip(ds["sketch_normal"], n))) - 0) < 1e-6,
           f"normale nuova {ds.get('sketch_normal')}")
    await c.call("close_sketch")
    ok, text, _ = await c.call("create_sketch", plane="PianoCheNonEsiste")
    record("P4 piano inesistente: errore (nessuno schizzo sul piano frontale)", not ok and "non trovato" in text, text[:100])
    ok, _, st = await c.call("get_sketch_status")
    record("P5 dopo il rifiuto nessuno schizzo aperto", ok and st.get("has_active_sketch") is False, str(st)[:100])
    await discard_all(c)


# =========================================================================================================== Q
async def q_suppress(c):
    print("\n== Q. soppressione riletta e chiusura dello schizzo riletta")
    await block(c)
    await c.call("create_sketch_on_face", x=5, y=5, z=10)            # faccia superiore (z = 10)
    await c.call("draw_circle", x=0, y=0, radius=5)
    ok, text, d = await c.call("extrude_cut", end_condition="through_all")
    hole = d.get("feature")
    record("Q0 foro passante d=10 creato", ok and bool(hole), text[:90])
    v_hole = 40 * 40 * 10 - PI * 25 * 10
    close("Q0 blocco forato: volume", await vol(c), v_hole)
    ok, text, d = await c.call("suppress_feature", name=hole)
    record("Q1 suppress_feature: stato riletto soppresso", ok and d.get("suppressed") is True, text[:90])
    close("Q1 volume senza foro", await vol(c), 16000.0)
    ok, text, d = await c.call("unsuppress_feature", name=hole)
    record("Q2 unsuppress_feature: stato riletto attivo", ok and d.get("suppressed") is False, text[:90])
    close("Q2 volume con il foro", await vol(c), v_hole)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_line", x1=0, y1=0, x2=10, y2=10)
    ok, text, d = await c.call("close_sketch")
    ok2, _, st = await c.call("get_sketch_status")
    record("Q3 close_sketch: riuscito e nessuno schizzo aperto dopo", ok and d.get("action") == "closed" and ok2
           and st.get("has_active_sketch") is False, f"{text[:60]} | {str(st)[:80]}")
    await discard_all(c)


# =========================================================================================================== E
async def e_equations(c):
    print("\n== E. equazioni: GetErrorCode2 letto davvero")
    # blocco 40x40x10 dal frontale (faccia x = 10) con un foro cieco r=5 prof. 5 posizionato dalla quota "posx" (come G2 di
    # test_ext_manage: con posx = 100 il taglio esce dal blocco e SolidWorks da' un errore vero alla feature, codice 71)
    await new_part(c)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-20, y1=-20, x2=20, y2=20)
    await c.call("extrude_boss", depth=10)
    v0 = await vol(c)
    await c.call("create_sketch_on_face", x=10, y=0, z=0)
    ok1, _, dc = await c.call("draw_circle", x=3, y=0, radius=5)
    ok2, _, dp = await c.call("draw_point", x=0, y=0)
    ok3, _, _ = await c.call("add_sketch_dimension", kind="horizontal", entity1=dc.get("center_point_id"),
                             entity2=dp.get("point_id"), value=3, name="posx")
    await c.call("close_sketch")
    sk = await last_sketch_name(c)
    ok4, _, dcut = await c.call("extrude_cut", sketch=sk, depth=5)
    v_cut = v0 - PI * 25 * 5
    close("E0 foro cieco r=5 prof. 5: volume", await vol(c), v_cut)
    ok, text, d = await c.call("add_equation", equation=f'"posx@{sk}" = 6')
    record("E1 equazione sana (posx = 6, foro ancora dentro il blocco): resta", ok, text[:100])
    close("E1 volume invariato (stesso foro spostato)", await vol(c), v_cut)
    await c.call("delete_equation", index=0)
    ok, text, d = await c.call("add_equation", equation=f'"posx@{sk}" = 100')
    record("E2 equazione che porta il foro fuori dal blocco: rimossa, l'errore nomina la feature",
           not ok and "errore" in text and str(dcut.get("feature")) in text, text[:160])
    ok, _, dl = await c.call("list_equations")
    record("E3 nessuna equazione rimasta", ok and len(dl.get("equations", [])) == 0,
           str(dl.get("equations"))[:100])
    close("E4 volume invariato dopo la rimozione", await vol(c), v_cut, 1e-6)
    ok, text, d = await c.call("rebuild_model", force=True)
    record("E5 rebuild_model: nessun errore sul modello sano", ok and not d.get("errors"), text[:90])
    ok, text, _ = await c.call("set_dimension_value", name=f"posx@{sk}", value=100, unit="mm")
    ok, text, d = await c.call("rebuild_model", force=True)
    codes = [e.get("error_code") for e in d.get("errors", [])]
    record("E6 rebuild_model con il foro fuori dal blocco: errore riportato con il suo codice (prima: mai)",
           not ok and codes and all(cd for cd in codes), f"{text[:90]} | codici {codes}")
    await discard_all(c)


# =========================================================================================================== M
async def m_material(c):
    print("\n== M. assign_material con rilettura")
    await block(c)
    ok, text, d = await c.call("assign_material", material="AISI 304", link_title_block=False)
    rb = d.get("read_back", {})
    record("M1 assign_material: materiale riletto uguale", ok and rb and all(v == d.get("material") for v in rb.values()),
           f"{text[:80]} | {rb}")
    ok, _, dm = await c.call("get_mass_properties")
    if ok and dm.get("mass_kg") is not None:
        close("M2 massa = 16000 mm3 * densita' AISI 304 (8000 kg/m3)", dm["mass_kg"], 16000e-9 * 8000, 0.002)
    await discard_all(c)


# =========================================================================================================== C
async def c_drawing(c):
    print("\n== C. create_drawing e set_dimension_tolerance")
    part = OUT / "rv_blocco.SLDPRT"
    await block(c, w=40, h=40)                                      # cubo 40: larghezza e altezza della vista sono due quote 40
    ok, text, _ = await c.call("save_document", filepath=str(part), overwrite=True)
    record("C0 cubo salvato", ok, text[:80])
    t0 = os.path.getmtime(part)
    await asyncio.sleep(1.5)
    # modifica geometrica NON salvata (una proprieta' personalizzata scritta via API non accende il flag "da salvare")
    await c.call("create_sketch_on_face", x=5, y=5, z=40)
    await c.call("draw_circle", x=0, y=0, radius=5)
    await c.call("extrude_boss", depth=5)
    ok, _, di = await c.call("get_document_info")
    ok, text, d = await c.call("create_drawing", model_path=str(part), paper_size="A3")
    record("C1 create_drawing con il modello modificato e non salvato: tavola creata, modello NON salvato",
           ok and d.get("model_saved") is False and "modifiche non salvate" in text and os.path.getmtime(part) == t0,
           f"{text[:160]} | data del file invariata={os.path.getmtime(part) == t0} | info={str(di)[:80]}")
    drw = d.get("title")
    await c.call("add_standard_views", views=["front", "top", "right"])
    await c.call("insert_model_dimensions", all_views=True)
    ok, _, dl = await c.call("list_drawing_dimensions")
    print(f"    quote: {str(dl.get('dimensions', dl))[:300]}")
    ok, text, d = await c.call("set_dimension_tolerance", dimension="40", tolerance_type="symmetric", upper=0.1)
    cands = d.get("candidates", [])
    record("C2 quota '40' ambigua (lati del cubo): rifiutata con l'elenco", not ok and len(cands) >= 2, f"{text[:160]}")
    if cands:
        ok, text, d = await c.call("set_dimension_tolerance", dimension=cands[0], tolerance_type="symmetric", upper=0.1,
                                   apply_to_model=True)
        ap = d.get("applied", {})
        record("C3 tolleranza +-0,1 sulla prima: riletta max +0,1 / min -0,1",
               ok and abs(ap.get("max", 0) - 0.1) < 1e-6 and abs(ap.get("min", 0) + 0.1) < 1e-6, f"{text[:80]} | {ap}")
    await c.call("close_document", discard=True, document=drw) if drw else None
    bad = str(OUT / "rv_tavola<non valida>.SLDDRW")
    ok, text, d = await c.call("create_drawing", model_path=str(part), paper_size="A3", save_as=bad)
    record("C4 save_as impossibile: errore che lo dice, tavola lasciata aperta",
           not ok and "NON salvato" in text and not d.get("saved_as"), text[:140])
    await discard_all(c)


# =========================================================================================================== X
async def x_explode(c):
    print("\n== X. auto_explode axis='-x'")
    box, pin = OUT / "rv_box.SLDPRT", OUT / "rv_pin.SLDPRT"
    for path, r, depth in ((box, 25, 50), (pin, 10, 80)):
        await new_part(c)
        await c.call("create_sketch", plane="Front")
        await c.call("draw_circle", x=0, y=0, radius=r)
        await c.call("extrude_boss", depth=depth)
        await c.call("save_document", filepath=str(path), overwrite=True)
    await discard_all(c)
    await c.call("create_new_assembly")
    await c.call("insert_component", file_path=str(box), x=0, y=0, z=0, fixed=False)
    await c.call("insert_component", file_path=str(pin), x=100, y=0, z=0, fixed=False)
    ok, _, dc = await c.call("list_components")
    comps = dc.get("components", [])
    names = {x.get("name", "") for x in comps}
    bname = next((n for n in names if n.lower().startswith("rv_box")), "rv_box-1")
    pname = next((n for n in names if n.lower().startswith("rv_pin")), "rv_pin-1")
    for n in (bname, pname):                                        # SolidWorks fissa da solo il primo componente inserito
        await c.call("set_component_fixed", component=n, fixed=False)
    ok, _, dc = await c.call("list_components")
    fixed = [x.get("name") for x in dc.get("components", []) if x.get("fixed")]
    ok, _, dl = await c.call("list_exploded_views")
    ok, text, d = await c.call("auto_explode", axis="-x", gap=30)
    poses = (await c.call("list_exploded_views"))[2].get("poses", {})
    bx = (poses.get(bname, {}).get("position_mm") or [None])[0]
    px = (poses.get(pname, {}).get("position_mm") or [None])[0]
    if fixed:
        record("X1 auto_explode '-x': componenti fissi presenti, controllo non applicabile", False, f"fissi {fixed}")
    else:
        record("X1 auto_explode '-x' senza fissi: base = componente all'estremo +x (perno)",
               ok and d.get("base_component") == pname, f"{text[:90]} | base {d.get('base_component')}")
        record("X2 il cilindro si allontana verso -x di 30 mm, il perno (base) resta a +100",
               bx is not None and abs(bx + 30) < 1e-3 and px is not None and abs(px - 100) < 1e-3, f"cilindro x={bx}, perno x={px}")
    await discard_all(c)


# =========================================================================================================== K
async def k_prefs(c):
    print("\n== K. set_sketch_performance_mode: valori precedenti")
    await block(c)
    # su un pezzo senza schizzo aperto AutoSolve si rilegge False anche dopo averlo scritto True (misurato 2026-11-16):
    # il tool deve fallire e rimettere le impostazioni gia' cambiate
    ok, text, d = await c.call("set_sketch_performance_mode", add_to_db=True, auto_solve=True, auto_inference=False)
    p0 = d.get("previous", {})
    record("K0 AutoSolve=true non tenuto da SolidWorks: errore con i valori di partenza", not ok and set(p0) ==
           {"add_to_db", "auto_solve", "auto_inference"}, f"{p0} | {text[:120]}")
    ok, text, d = await c.call("set_sketch_performance_mode", add_to_db=True, auto_solve=False, auto_inference=False)
    prev = d.get("previous", {})
    record("K1 dopo il fallimento le impostazioni erano tornate quelle di partenza; valori precedenti riportati",
           ok and prev == p0, f"{prev} | {text[:120]}")
    ok2, _, d2 = await c.call("set_sketch_performance_mode", **{k: bool(v) for k, v in prev.items() if v is not None})
    record("K2 ripristino con i valori precedenti: riletti uguali",
           ok2 and all(d2.get(k) == bool(v) for k, v in prev.items() if v is not None) and d2.get("previous", {}).get("add_to_db") is True,
           str(d2.get("previous")))
    await discard_all(c)


SECTIONS = (("S", s_sweep), ("P", p_planes), ("Q", q_suppress), ("E", e_equations), ("M", m_material), ("C", c_drawing),
            ("X", x_explode), ("K", k_prefs))


async def scenario(c):
    only = {a.upper() for a in sys.argv[1:]}
    for nome, fn in SECTIONS:
        if not only or nome in only:
            try:
                await fn(c)
            except Exception as e:
                record(f"sezione {nome}: eccezione", False, repr(e)[:200])
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
                ok, text, data = await c.call("connect_solidworks")
                my_pid = data.get("pid")
                print(text[:200])
                if not ok or not my_pid or my_pid in elia_pids or my_pid not in sw_pids():
                    print("STOP: nessuna istanza separata ottenibile. Nulla e' stato toccato.")
                    return False
                print(f"Istanza dedicata PID {my_pid} (diversa da {sorted(elia_pids)})")
                await scenario(c)
    finally:
        cleanup(my_pid, elia_pids)
        record("istanza dedicata del test chiusa (PID proprio)", my_pid is None or my_pid not in sw_pids(), f"PID {my_pid}")
    return True


if __name__ == "__main__":
    done = asyncio.run(run())
    print("\n==== RIEPILOGO ====")
    for tool, res, note in RESULTS:
        print(f"{res:5} {tool:80} {note}"[:300])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
