"""
Test live del GRUPPO D (dati ed export, voci D7, D8, D1, D10, D4, D9, D2, D3) tramite il server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente non viene mai
toccata; alla fine si chiude solo il PID lanciato dal test. Ogni sezione costruisce i propri pezzi (file dxe_* in test_output).

Uso:  .venv\\Scripts\\python.exe tests\\test_data_extra_live.py            tutte le sezioni
      .venv\\Scripts\\python.exe tests\\test_data_extra_live.py D7 D1      solo quelle indicate
"""

import os
import sys
import math
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup, L
from test_data_live import RESULTS, record, T, F, rm, rel, A, B, C, V_BLOCK, V_HOLE  # aiuti comuni, stesso elenco dei risultati

PI = math.pi
TOOLS = []                                   # nomi dei tool esposti dal server (riempito in run)


# ============================================================================================ D7
async def sec_d7(c: Client):
    """D7: proprieta' di massa rispetto a un sistema di coordinate utente.

    Prisma 80x50x30 mm il cui profilo (rettangolo) e' ruotato di 30 gradi nel piano dello schizzo (Top, normale Z): ha spigoli
    inclinati, quindi un sistema di coordinate ruotato di 30 gradi e traslato (origine in un vertice, X e Y lungo due spigoli),
    e il baricentro non sta su nessun asse ne' piano coordinato del modello (termini fuori diagonale misurabili).
    Le attese si calcolano QUI con le formule del parallelepipedo (momenti m/12(l2^2+l3^2) lungo gli spigoli) e con
    R^T (I_c + m(|d|^2 E - d d^T)) R, senza usare utils/inertia.py."""
    print("\n== D7 proprieta' di massa in un sistema di coordinate utente")

    def dot(p, q):
        return sum(x * y for x, y in zip(p, q))

    def cross(p, q):
        return [p[1] * q[2] - p[2] * q[1], p[2] * q[0] - p[0] * q[2], p[0] * q[1] - p[1] * q[0]]

    def mm_(x, y):
        return [[sum(x[i][k] * y[k][j] for k in range(3)) for j in range(3)] for i in range(3)]

    def tr_(x):
        return [[x[j][i] for j in range(3)] for i in range(3)]

    def maxerr(got, exp):
        return max(abs(got[i][j] - exp[i][j]) for i in range(3) for j in range(3)) / max(abs(exp[i][j]) for i in range(3) for j in range(3))

    a, b, H, ang = 80.0, 50.0, 30.0, 30.0
    u0, v0 = 20.0, 10.0
    part = F("dxe_d7_prisma")
    rm(part)
    await c.call("create_new_part")
    try:
        ok, text, sk = await c.call("create_sketch", plane="Top")
        record("D7: schizzo sul piano Top, assi dello schizzo riportati", ok and "sketch_x_axis" in sk, text.split("\n")[0][:120])
        if not ok or "sketch_x_axis" not in sk:
            return
        so, sx, sy, sn = sk["sketch_origin_mm"], sk["sketch_x_axis"], sk["sketch_y_axis"], sk["sketch_normal"]
        e1 = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
        e2 = (-e1[1], e1[0])

        def uv(p, q):                                   # punto dello schizzo: spigolo (u0,v0) + p lungo e1 + q lungo e2
            return (u0 + p * e1[0] + q * e2[0], v0 + p * e1[1] + q * e2[1])

        def mdl(u, v):                                  # coordinate dello schizzo -> modello (mm)
            return [so[k] + u * sx[k] + v * sy[k] for k in range(3)]
        corners = [uv(0, 0), uv(a, 0), uv(a, b), uv(0, b)]
        for i in range(4):
            p, q = corners[i], corners[(i + 1) % 4]
            await c.call("draw_line", x1=p[0], y1=p[1], x2=q[0], y2=q[1])
        await T(c, "extrude_boss", "prisma 80x50x30 con profilo ruotato di 30 gradi", depth=H)
        await T(c, "assign_material", "AISI 304", material="AISI 304")
        E = [[e1[0] * sx[k] + e1[1] * sy[k] for k in range(3)], [e2[0] * sx[k] + e2[1] * sy[k] for k in range(3)], list(sn)]
        ok, _, ent = await c.call("list_entities", kind="vertex", limit=50)
        vx = [e["point"] for e in ent.get("entities", []) if "point" in e]
        record("D7: prisma con 8 vertici", ok and len(vx) == 8, f"{len(vx)}")
        if len(vx) != 8:
            return
        center = [sum(p[k] for p in vx) / 8 for k in range(3)]                 # baricentro del solido = centro del prisma [mm]

        ok, _, mp0 = await c.call("get_part_mass_properties")
        m = mp0.get("mass_kg", 0.0)
        record("D7: volume = 80 x 50 x 30 mm3 e senza la chiave in_coordinate_system se non richiesta",
               ok and rel(mp0.get("volume_mm3", 0), a * b * H) < 1e-5 and "in_coordinate_system" not in mp0,
               f"{mp0.get('volume_mm3')} mm3, massa {m:.6f} kg")

        # sistema di coordinate: origine nel vertice (u0,v0), X lungo lo spigolo e1, Y lungo lo spigolo e2
        W0 = mdl(*corners[0])
        cs = await T(c, "create_coordinate_system", "origine nel vertice del prisma, X e Y lungo due spigoli inclinati di 30 gradi",
                     origin_point=W0, x_edge_point=mdl(*uv(a / 2, 0)), y_edge_point=mdl(*uv(0, b / 2)))
        name = cs.get("feature")
        xa, ya, za = cs.get("x_axis", [1, 0, 0]), cs.get("y_axis", [0, 1, 0]), cs.get("z_axis", [0, 0, 1])
        s1 = 1.0 if dot(xa, E[0]) >= 0 else -1.0
        s2 = 1.0 if dot(ya, E[1]) >= 0 else -1.0
        record("D7: assi del sistema = spigoli del prisma (X//e1, Y//e2) e origine nel vertice scelto",
               abs(abs(dot(xa, E[0])) - 1) < 1e-5 and abs(abs(dot(ya, E[1])) - 1) < 1e-5
               and max(abs(x - y) for x, y in zip(cs.get("origin", [9e9] * 3), W0)) < 1e-3,
               f"X {xa} Y {ya} Z {za}, origine {cs.get('origin')} atteso {[round(x, 4) for x in W0]}")
        X = [s1 * x for x in E[0]]
        Y = [s2 * x for x in E[1]]
        Z = cross(X, Y)
        R = [[X[i], Y[i], Z[i]] for i in range(3)]                            # colonne = assi utente nel modello
        record("D7: terna destrorsa, Z = X x Y come riportato dall'API", max(abs(x - y) for x, y in zip(Z, za)) < 1e-5, f"{Z} / {za}")

        # attese (SI): momenti lungo gli spigoli, tensore nel baricentro nel modello, spostamento d (m) dall'origine utente
        l = [a * 1e-3, b * 1e-3, H * 1e-3]
        J = [m / 12 * (l[1] ** 2 + l[2] ** 2), m / 12 * (l[0] ** 2 + l[2] ** 2), m / 12 * (l[0] ** 2 + l[1] ** 2)]
        Ic = [[sum(J[k] * E[k][i] * E[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
        dm = [(center[k] - W0[k]) * 1e-3 for k in range(3)]                 # baricentro - origine, assi modello
        d = [dot([R[i][k] for i in range(3)], dm) for k in range(3)]        # R^T (c - o): nel sistema utente
        dd = dot(d, d)
        Ic_user = mm_(mm_(tr_(R), Ic), R)                                     # R^T I_c R
        exp_o = [[Ic_user[i][j] + m * ((dd if i == j else 0.0) - d[i] * d[j]) for j in range(3)] for i in range(3)]
        record("D7: il baricentro del modello e' fuori da tutti gli assi (misura sensibile al segno dei prodotti d'inerzia)",
               all(abs(x) > 1.0 for x in center), f"{[round(x, 3) for x in center]} mm")

        # chiamata con il sistema di coordinate
        ok, text, mp = await c.call("get_part_mass_properties", coordinate_system=name)
        ic = mp.get("in_coordinate_system", {})
        record("get_part_mass_properties: coordinate_system -> in_coordinate_system presente, chiavi esistenti invariate",
               ok and bool(ic) and mp.get("mass_kg") == m and "inertia_tensor_at_origin_kg_m2" in mp, text.split("\n")[0][:120])
        if not ic:
            return
        exp_c = [x * 1e3 for x in d]                                         # mm
        errc = max(abs(g - e) for g, e in zip(ic.get("center_of_mass", [9e9] * 3), exp_c)) / max(abs(x) for x in exp_c)
        record("D7: baricentro nel sistema utente = R^T (c - o) (< 0,01 %)", errc < 1e-4,
               f"{ic.get('center_of_mass')} / atteso {[round(x, 4) for x in exp_c]} mm, errore relativo {errc:.2e}")

        conv = ic.get("offdiag_convention")
        record("D7: convenzione dei termini fuori diagonale di GetMomentOfInertia (misura che la stabilisce)",
               conv in ("tensor", "products"), f"offdiag_convention = {conv}")

        def true_tensor(t):                                                  # dalla convenzione di SolidWorks al tensore vero
            if conv == "products":
                return [[t[i][j] if i == j else -t[i][j] for j in range(3)] for i in range(3)]
            return t
        got_o = true_tensor(ic.get("inertia_tensor_at_origin_kg_m2", [[9e9] * 3] * 3))
        erro = maxerr(got_o, exp_o)
        record("D7: tensore nell'origine utente, assi utente = R^T (I_c + m(|d|^2 E - d d^T)) R (< 0,01 % sul massimo)", erro < 1e-4,
               f"errore {erro:.2e}; misurato diag {[got_o[k][k] for k in range(3)]} / atteso {[exp_o[k][k] for k in range(3)]}")
        got_c = true_tensor(ic.get("inertia_tensor_at_center_of_mass_kg_m2", [[9e9] * 3] * 3))
        errk = maxerr(got_c, Ic_user)
        record("D7: tensore nel baricentro, assi utente = R^T I_c R (< 0,01 %)", errk < 1e-4, f"errore {errk:.2e}")
        g2 = ic.get("inertia_tensor_at_origin_kg_mm2", [[9e9] * 3] * 3)
        record("D7: stessa matrice in kg*mm2 (x 1e6)", max(abs(g2[i][j] - ic["inertia_tensor_at_origin_kg_m2"][i][j] * 1e6)
                                                         for i in range(3) for j in range(3)) < 1e-6 * max(abs(x) for r in g2 for x in r))
        record("D7: nessun problema segnalato sul sistema (ortonormale, destrorso)", not ic.get("frame_issues"), str(ic.get("frame_issues")))
        py_ok = errc < 1e-4 and erro < 1e-4 and errk < 1e-4

        api = ic.get("api_check", {})
        if "error" in api or not api:
            record("D7: controllo indipendente con IMassProperty2.SetCoordinateSystem (non riuscito: informativo)", py_ok, str(api)[:200])
        else:
            record("D7: IMassProperty2.SetCoordinateSystem + Recalculate = calcolo in Python (< 0,01 %)",
                   py_ok and api["max_rel_diff_inertia"] < 1e-4 and api["max_rel_diff_center_of_mass"] < 1e-4,
                   f"differenza baricentro {api['max_rel_diff_center_of_mass']:.2e}, inerzia {api['max_rel_diff_inertia']:.2e}; API {api['center_of_mass']}")

        ok, text, _ = await c.call("get_part_mass_properties", coordinate_system="SistemaInesistente")
        record("get_part_mass_properties: sistema di coordinate inesistente -> errore con l'elenco dei presenti",
               (not ok) and str(name) in text, text.split("\n")[0][:170])
        await T(c, "save_document", "salva il prisma", filepath=part)
    finally:
        await c.call("close_document", discard=True)
        rm(part)


# ============================================================================================ D8
async def sec_d8(c: Client):
    """D8: materiali da tutte le cartelle delle librerie configurate."""
    print("\n== D8 materiali da librerie personalizzate")
    from solidworks_mcp.utils.matlib import build_sldmat, SW_FILE_LOCATIONS_MATERIAL_DATABASES as PREF
    a_, b_, c_, dens = 30.0, 80.0, 50.0, 1234.0          # blocco come in test_data_live (senza foro), densita' del materiale di prova
    name = "DXE Prova 1234"
    libdir = OUT / "dxe_matlib"
    libdir.mkdir(exist_ok=True)
    (libdir / "dxe_prova.sldmat").write_bytes(build_sldmat([{"name": name, "density": dens}], classification="DXE Prova"))
    backup = OUT / "dxe_matlib_pref28_originale.txt"      # copia di sicurezza: se il test si interrompe, la preferenza si rimette a mano

    async def pref(value=None):
        """Preferenza 28 (cartelle dei database dei materiali) letta/scritta con execute_python sull'istanza dedicata
        (`sw` = ISldWorks collegato). Nessun tool dedicato: e' una preferenza GLOBALE, qui sempre ripristinata."""
        code = (f"result = sw.GetUserPreferenceStringValue({PREF}) or ''" if value is None
                else f"result = str(sw.SetUserPreferenceStringValue({PREF}, {value!r}))")
        ok, _text, d = await c.call("execute_python", code=code)
        return ok, d.get("result")

    ok, orig = await pref()
    record("D8 preferenza 28 (percorsi dei database materiali) leggibile con execute_python", ok and orig is not None, repr(orig)[:160])
    if not ok or orig is None:
        return
    backup.write_text(orig, encoding="utf-8")
    new = ";".join([str(libdir)] + ([orig] if orig else []))
    try:
        ok, r = await pref(new)
        ok2, now = await pref()
        record("D8 preferenza 28 impostata con la cartella di prova", ok and ok2 and str(libdir).lower() in (now or "").lower(),
               f"set={r}, ora={now!r}"[:200])

        d = await T(c, "list_materials", "libreria personalizzata: query 'DXE Prova'", query="DXE Prova")
        mm = [m for m in d.get("materials", []) if m["name"] == name]
        record("D8 list_materials trova il materiale di prova: library 'dxe_prova', densita' 1234",
               len(mm) == 1 and mm[0]["library"] == "dxe_prova" and abs(mm[0]["density_kg_m3"] - dens) < 1e-6, str(mm))
        folders = [f.lower() for f in d.get("libraries", {}).get("folders", [])]
        record("D8 list_materials: 'libraries' contiene la cartella di prova e quella standard (>= 2 cartelle), 'duplicates' presente",
               os.path.normpath(str(libdir)).lower() in folders and len(folders) >= 2 and isinstance(d.get("duplicates"), list),
               f"{len(folders)} cartelle, {len(d.get('duplicates', []))} duplicati")

        await c.call("create_new_part")
        try:
            await c.call("create_sketch", plane="Front")
            await c.call("draw_rectangle", x1=-b_ / 2, y1=-c_ / 2, x2=b_ / 2, y2=c_ / 2)
            await T(c, "extrude_boss", "blocco 80x50x30", depth=a_)
            d = await T(c, "assign_material", "materiale di prova", material=name, link_title_block=False,
                        check=lambda d: d["material"] == name and d["library"] == "dxe_prova")
            ok, _, mp = await c.call("get_part_mass_properties")
            vol = mp.get("volume_mm3", 0)
            exp = a_ * b_ * c_ * 1e-9 * dens
            record("D8 MASSA: blocco con 'DXE Prova 1234' = volume x 1234 kg/m3 (< 0,1 %)",
                   ok and rel(vol, a_ * b_ * c_) < 1e-6 and rel(mp.get("mass_kg", 0), exp) < 1e-3,
                   f"massa {mp.get('mass_kg')} kg, attesa {exp:.6f} (vol {vol} mm3 x {dens}); densita' usata {mp.get('density_kg_m3')}")
            ok, _, gm = await c.call("get_material")
            record("D8 get_material: nome del materiale di prova", ok and gm.get("material") == name,
                   f"{gm.get('material')} / libreria {gm.get('library')}")
        finally:
            await c.call("close_document", discard=True)
    finally:
        ok, r = await pref(orig)
        ok2, back = await pref()
        record("D8 preferenza 28 RIPRISTINATA al valore originale", ok and ok2 and back == orig, f"set={r}, ora={back!r}, originale={orig!r}"[:220])

    d = await T(c, "list_materials", "dopo il ripristino: 'DXE Prova' non c'e' piu' (cache invalidata)", query="DXE Prova",
                check=lambda d: d["matching"] == 0)
    record("D8 dopo il ripristino la cartella di prova non e' piu' fra le librerie",
           os.path.normpath(str(libdir)).lower() not in [f.lower() for f in d.get("libraries", {}).get("folders", [])],
           str(d.get("libraries", {}).get("folders")))


# ============================================================================================ D1
async def sec_d1(c: Client):
    print("\n== D1. apply_configuration_table")
    record("D1: tool apply_configuration_table esposto", "apply_configuration_table" in TOOLS, "")

    # blocco di test_data_live (sezioni 1 e 5): 30x80x50, X 0..30, Y +-40, Z +-25, foro d12 passante
    part = F("dxe_d1")
    rm(part)
    await c.call("create_new_part")
    await c.call("create_sketch", plane="Front")
    await c.call("draw_rectangle", x1=-B / 2, y1=-C / 2, x2=B / 2, y2=C / 2)
    await T(c, "extrude_boss", "blocco 80x50x30", depth=A)
    await c.call("create_sketch", plane="Front")
    await c.call("draw_circle", x=0, y=0, radius=6)
    await T(c, "extrude_cut", "foro d12 passante", end_condition="through_all_both")
    v_hole = V_BLOCK - V_HOLE
    ok, _, m = await c.call("get_mass_properties")
    record("D1: pezzo con foro: volume = blocco - pi*6^2*30", ok and rel(m["volume_mm3"], v_hole) < 1e-4,
           f"{m.get('volume_mm3')} atteso {v_hole:.2f}")
    await T(c, "save_document", "salva dxe_d1", filepath=part)

    # nomi di quota e feature in italiano: Client.call li traduce negli argomenti, ma NON nelle chiavi delle righe -> L() qui
    dim = "D1@Estrusione-Estrusione1"                  # profondita' del blocco
    cut = "Taglio-Estrusione1"                         # foro passante
    h_name, h_dim, h_state, h_prp = "Configurazione", L(dim), "$STATO@" + L(cut), "$PRP@Codice"
    rows = [
        {h_name: "Default", h_prp: "A-001"},                                   # geometria invariata
        {h_name: "Lunga", h_dim: 60, h_prp: "A-002"},                          # profondita' 60
        {h_name: "Pieno", h_state: "S", h_prp: "A-003"},                       # foro soppresso
    ]
    v_lunga = B * C * 60 - PI * 36 * 60
    v_pieno = B * C * A
    await T(c, "list_part_configurations", "una sola configurazione di partenza",
            check=lambda d: d["active"] == "Default" and len(d["configurations"]) == 1)

    # ---- dry_run: piano senza toccare il modello
    exp_actions = ["set_property", "add_configuration", "set_dimension", "set_property",
                   "add_configuration", "set_suppression", "set_property"]
    d = await T(c, "apply_configuration_table", "dry_run: piano atteso (7 azioni)", table=rows, dry_run=True,
                check=lambda d: [a["action"] for a in d["actions"]] == exp_actions and d.get("dry_run") is True)
    record("D1: dry_run riporta anche lo stato di Excel e la nota sulla design table",
           "excel_available" in d.get("design_table", {}) and "design_table" in d.get("design_table", {}),
           str(d.get("design_table", {}).get("excel_available")))
    await T(c, "list_part_configurations", "dry_run: numero di configurazioni invariato (1)",
            check=lambda d: len(d["configurations"]) == 1 and d["active"] == "Default")

    # ---- errori: nessuna modifica
    bad = [{h_name: "Xx", "Colonna ignota": 5}]
    await T(c, "apply_configuration_table", "colonna sconosciuta -> errore", table=bad, expect_fail=True)
    await T(c, "apply_configuration_table", "create_missing=false con configurazioni assenti -> errore",
            table=rows, create_missing=False, expect_fail=True)
    await T(c, "list_part_configurations", "errori: ancora 1 configurazione, nessuna modifica",
            check=lambda d: len(d["configurations"]) == 1 and d["active"] == "Default")

    # ---- esecuzione
    d = await T(c, "apply_configuration_table", "esecuzione: 7/7 azioni, attiva = Default", table=rows,
                check=lambda d: d["failed"] == 0 and len(d["results"]) == 7 and d["active"] == "Default"
                and all(r["ok"] for r in d["results"]))
    for r in d.get("results", []):
        if not r.get("ok"):
            print(f"    azione fallita: {r}")
    d = await T(c, "list_part_configurations", "volumi delle 3 configurazioni", include_volume=True,
                check=lambda d: len(d["configurations"]) == 3 and d["active"] == "Default")
    vols = {x["name"]: x.get("volume_mm3", 0) for x in d.get("configurations", [])}
    for n, vexp in (("Default", v_hole), ("Lunga", v_lunga), ("Pieno", v_pieno)):
        record(f"D1: volume {n} = {vexp:.2f} mm3 (< 0,01 %)", rel(vols.get(n, 0), vexp) < 1e-4,
               f"{vols.get(n)} atteso {vexp:.2f}")
    # proprieta' per configurazione
    for n, code in (("Default", "A-001"), ("Lunga", "A-002"), ("Pieno", "A-003")):
        await T(c, "get_custom_property", f"Codice in {n} = {code}", name="Codice", configuration=n,
                check=lambda d, code=code: d["value"] == code)
    # configurazione attiva alla fine = quella di partenza
    await T(c, "list_part_configurations", "configurazione attiva a fine tabella = Default (di partenza)",
            check=lambda d: d["active"] == "Default")

    # ---- seconda applicazione (idempotenza): nessuna configurazione da creare, stessi volumi
    rows2 = [{h_name: "lunga", h_dim: 60}]                  # nome con maiuscole diverse: stessa configurazione
    await T(c, "apply_configuration_table", "riapplicazione su configurazione esistente (nome case-insensitive)", table=rows2,
            check=lambda d: [a["action"] for a in d["actions"]] == ["set_dimension"] and d["failed"] == 0
            and len(d["configurations_in_model"]) == 3)
    await T(c, "save_document", "salva dxe_d1", filepath=part)
    ok, _, m = await c.call("get_mass_properties")
    record("D1: volume della configurazione attiva (Default) invariato dopo tutto", ok and rel(m["volume_mm3"], v_hole) < 1e-4,
           f"{m.get('volume_mm3')}")


# ============================================================================================ D10
async def sec_d10(c: Client):
    """D10: PDF 3D letto a fondo (pdf3d)."""
    print("\n== D10 PDF 3D")


# ============================================================================================ D4
async def sec_d4(c: Client):
    """D4: immagini oltre la risoluzione nativa, prospettiva."""
    print("\n== D4 immagini")


# ============================================================================================ D9
async def sec_d9(c: Client):
    """D9: opzioni di import."""
    print("\n== D9 import")


# ============================================================================================ D2
async def sec_d2(c: Client):
    """D2: STEP AP242."""
    print("\n== D2 STEP AP242")


# ============================================================================================ D3
async def sec_d3(c: Client):
    """D3: eDrawings verificato."""
    print("\n== D3 eDrawings")


SECTIONS = {"D7": sec_d7, "D8": sec_d8, "D1": sec_d1, "D10": sec_d10, "D4": sec_d4, "D9": sec_d9, "D2": sec_d2, "D3": sec_d3}


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
                TOOLS[:] = [t.name for t in (await session.list_tools()).tools]
                ok, text, data = await c.call("connect_solidworks")
                my_pid = data.get("pid")
                print(text[:200])
                if not ok or not my_pid or my_pid in elia_pids or my_pid not in sw_pids():
                    print("STOP: nessuna istanza separata ottenibile. Nulla e' stato toccato.")
                    return False
                record("PID dedicato diverso dall'istanza utente", my_pid not in elia_pids, str(my_pid))
                for n in names:
                    try:
                        await SECTIONS[n](c)
                    except Exception as e:
                        record(f"{n}: sezione interrotta da un'eccezione", False, repr(e)[:200])
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
        print(f"{res:5} {tool:90} {note}"[:250])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
