"""
Test live del lotto CURVE (elica, elica a passo variabile, curva proiettata, linea di divisione, curva composita, curva per
punti) tramite il server MCP (stdio).

Gira SOLO su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): l'istanza dell'utente non viene mai
toccata; alla fine si chiude solo il PID lanciato dal test.

  H   create_helix: lunghezza misurata vs formula (cilindrica, conica, spirale), punti finali, senso, molla = sweep (volume)
  V   create_variable_pitch_helix: altezza/raggio finali, lunghezza vs integrale calcolato qui, sweep (volume)
  P   project_curve: linea su cilindro (punti a raggio R), verso opposto, schizzo su schizzo (ellisse)
  S   split_line: proiezione (area della faccia = pi r^2), silhouette (2 meta' del cilindro), intersezione (limite dichiarato)
  C   composite_curve: spigoli (perimetro del rettangolo raccordato) e schizzo (percorso di sweep: volume = pi r^2 L)
  T   curve_through_points: estremi e punti riletti, cerchio per punti (lunghezza 2 pi R), vertici del modello

Uso:  .venv\\Scripts\\python.exe tests\\test_ext_curves_live.py [H V P S C T]
"""

import os
import sys
import math
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, PYTHON, SERVER, sw_pids, Client, cleanup

PI = math.pi
RESULTS = []         # (voce, PASS/FAIL, nota)


def record(tool, ok, note=""):
    RESULTS.append((tool, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {tool}  {note}"[:260])


def rel(got, exp):
    return abs(got - exp) / abs(exp) if exp else abs(got)


def close(a, b, tol=1e-3):
    return len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b))


def radius_xy(p):
    return math.hypot(p[0], p[1])


async def need(c, tool, label, **args):
    """Chiama un tool, registra PASS/FAIL e restituisce i dati (vuoti se fallito)."""
    ok, text, d = await c.call(tool, **args)
    record(label, ok, text.split("\n")[0][:150])
    return d if ok else {}


async def vol(c):
    ok, _, d = await c.call("get_mass_properties")
    return d.get("volume_mm3", 0.0) if ok else 0.0


async def new_part(c):
    ok, text, _ = await c.call("create_new_part")
    assert ok, text


async def circle_sketch(c, radius, plane="Top"):
    await c.call("create_sketch", plane=plane)
    await c.call("draw_circle", x=0, y=0, radius=radius)
    await c.call("close_sketch")


async def discard_all(c):
    for _ in range(40):
        ok, _, d = await c.call("list_open_documents")
        docs = d.get("documents", []) if ok else []
        if not docs:
            return
        await c.call("close_document", discard=True, document=docs[0]["title"])


def spiral_length(r0, r1, b):
    """Archimede r = r0 + b t, da r0 a r1: L = (1/2b) [r sqrt(r^2+b^2) + b^2 asinh(r/b)] (forma chiusa)."""
    def F(r):
        return r * math.sqrt(r * r + b * b) + b * b * math.asinh(r / b)
    return (F(r1) - F(r0)) / (2 * b)


def vp_length(rows, key):
    """Lunghezza di un'elica a passo variabile: passo lineare nell'angolo, raggio lineare nell'ALTEZZA, per segmento.
    rows = [(giri_o_altezza_cumulativi, diametro, passo)], integrazione numerica indipendente da quella del tool."""
    total = 0.0
    for (c0, d0, p0), (c1, d1, p1) in zip(rows[:-1], rows[1:]):
        rev = (c1 - c0) if key == "rev" else 2 * (c1 - c0) / (p0 + p1)
        tmax = 2 * PI * rev
        n = 20000
        zt = rev * (p0 + p1) / 2
        prev = None
        for i in range(n + 1):
            t = tmax * i / n
            zi = p0 * t / (2 * PI) + (p1 - p0) / tmax / (2 * PI) * t * t / 2       # z(t)
            r = d0 / 2 + (d1 - d0) / 2 * zi / zt
            xyz = (r * math.cos(t), r * math.sin(t), zi)
            if prev is not None:
                total += math.dist(prev, xyz)
            prev = xyz
    return total


# ===================================================================================================== run
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
                c = Client(session, auto_overwrite=False)
                tl = (await session.list_tools()).tools
                print(f"{len(tl)} tool esposti")
                ok, text, data = await c.call("connect_solidworks")
                my_pid = data.get("pid")
                print(text[:200])
                if not ok or not my_pid or my_pid in elia_pids or my_pid not in sw_pids():
                    print("STOP: nessuna istanza separata ottenibile. Nulla e' stato toccato.")
                    return False
                print(f"Istanza dedicata PID {my_pid} (diversa da {sorted(elia_pids)})")
                record("PID dedicato diverso dall'istanza utente", my_pid not in elia_pids, str(my_pid))
                await scenario(c, tl)
    finally:
        left_ok = cleanup_check(my_pid, elia_pids)
        record("istanza del test chiusa (solo il suo PID)", left_ok)
    return True


def cleanup_check(my_pid, elia_pids):
    """Chiude il solo PID del test. Altri sotto-agenti possono avere istanze proprie: conta solo che la MIA sia sparita
    e che quelle preesistenti siano intatte."""
    cleanup(my_pid, elia_pids)
    gone = [p for p in elia_pids if p not in sw_pids()]
    if gone:
        print(f"Nota: istanze preesistenti chiuse da altri durante il test: {gone}")
    return my_pid not in sw_pids()


async def scenario(c, tl):
    only = {a.upper() for a in sys.argv[1:]}
    names = {t.name for t in tl}
    need_tools = {"create_helix", "create_variable_pitch_helix", "project_curve", "split_line", "composite_curve",
                  "curve_through_points"}
    record("i 6 tool del lotto sono esposti", need_tools <= names, f"mancanti {sorted(need_tools - names)}")
    destr = [t.name for t in tl if t.name in need_tools and t.annotations and t.annotations.destructiveHint]
    record("nessun tool del lotto e' distruttivo (creano solo feature)", not destr, str(destr))
    sezioni = [("H", lambda: h_helix(c)), ("V", lambda: v_variabile(c)), ("P", lambda: p_proiezione(c)),
               ("S", lambda: s_divisione(c)), ("C", lambda: c_composita(c)), ("T", lambda: t_punti(c))]
    for nome, fn in sezioni:
        if not only or nome in only:
            print(f"\n== {nome}")
            await fn()
    await discard_all(c)


# ===================================================================================================== H
async def h_helix(c):
    await new_part(c)
    R, P, REV = 10.0, 5.0, 8.0
    await circle_sketch(c, R)
    L = REV * math.sqrt((2 * PI * R) ** 2 + P ** 2)
    sk = "Schizzo1"
    # H1 passo + giri
    d1 = await need(c, "create_helix", "H1 elica passo 5 x 8 giri", sketch=sk, definition="pitch_revolutions", pitch=P, revolutions=REV)
    record("H1 lunghezza misurata vs 8*sqrt((2 pi R)^2 + p^2)", rel(d1.get("length", 0), L) < 1e-3,
           f"misurata {d1.get('length')} mm, calcolata {L:.4f} mm, scarto {rel(d1.get('length', 0), L) * 100:.4f} % (tolleranza 0,1 %)")
    record("H1 punto iniziale (R,0,0) e finale (R,0,altezza 40)", close(d1.get("start_point", []), [R, 0, 0], 1e-3)
           and close(d1.get("end_point", []), [R, 0, REV * P], 1e-3), f"{d1.get('start_point')} -> {d1.get('end_point')}")
    # molla: sweep di un cerchio d=1 lungo l'elica, volume vs pi r^2 L
    dd = 1.0
    v0 = await vol(c)
    await need(c, "sweep", "H1 molla: sweep di un cerchio d=1 lungo l'elica", path_sketch=d1.get("feature", "?"), circular_diameter=dd)
    v = (await vol(c)) - v0
    exp = PI * (dd / 2) ** 2 * L
    record("H1 molla: volume vs pi r^2 L", rel(v, exp) < 0.01, f"misurato {v:.3f} mm3, atteso {exp:.3f} mm3, scarto {rel(v, exp) * 100:.4f} % (tolleranza 1 %)")
    # H2 le altre definizioni danno la stessa elica
    d2 = await need(c, "create_helix", "H2 altezza 40 + 8 giri", sketch=sk, definition="height_revolutions", height=40, revolutions=REV)
    record("H2 stesso passo (5) e stessa lunghezza", abs(d2.get("pitch", 0) - P) < 1e-6 and rel(d2.get("length", 0), L) < 1e-3,
           f"passo {d2.get('pitch')}, lunghezza {d2.get('length')}")
    d3 = await need(c, "create_helix", "H2 altezza 40 + passo 5", sketch=sk, definition="height_pitch", height=40, pitch=P)
    record("H2 giri risolti = 8 e stessa lunghezza", abs(d3.get("revolutions", 0) - REV) < 1e-6 and rel(d3.get("length", 0), L) < 1e-3,
           f"giri {d3.get('revolutions')}, lunghezza {d3.get('length')}")
    # H3 senso e inversione (misurati: l'avvolgimento cambia con clockwise e con reverse_direction)
    hand = {}
    for label, kw in (("default", {}), ("ccw", {"clockwise": False}), ("rev", {"reverse_direction": True}),
                      ("ccw+rev", {"clockwise": False, "reverse_direction": True})):
        d = await need(c, "create_helix", f"H3 elica {label}", sketch=sk, pitch=P, revolutions=2, **kw)
        hand[label] = (d.get("handedness"), (d.get("end_point") or [0, 0, 0])[2])
    record("H3 clockwise=false inverte l'avvolgimento", hand["default"][0] != hand["ccw"][0] and None not in (hand["default"][0], hand["ccw"][0]), str(hand))
    record("H3 reverse_direction=true porta l'elica dall'altra parte del piano (z finale -10) e inverte l'avvolgimento",
           abs(hand["rev"][1] + 2 * P) < 1e-3 and hand["rev"][0] != hand["default"][0], str(hand))
    # H4 angolo di partenza: il punto iniziale ruota
    d = await need(c, "create_helix", "H4 angolo di partenza 90", sketch=sk, pitch=P, revolutions=2, start_angle=90)
    record("H4 punto iniziale ruotato di 90 gradi", close(d.get("start_point", []), [0, R, 0], 1e-3) or close(d.get("start_point", []), [0, -R, 0], 1e-3),
           str(d.get("start_point")))
    # H5 conica
    k = math.tan(math.radians(10))
    d = await need(c, "create_helix", "H5 conica 10 gradi verso l'esterno", sketch=sk, pitch=P, revolutions=REV, taper_angle=10)
    r_end = radius_xy(d.get("end_point", [0, 0, 0]))
    record("H5 raggio finale = R + h tan(10 gradi)", abs(r_end - (R + 40 * k)) < 1e-3, f"misurato {r_end:.4f}, atteso {R + 40 * k:.4f}")
    b = P / (2 * PI)
    cc = math.sqrt((k * k + 1)) * b
    # lunghezza esatta: r = R + k b t, ds^2 = (r^2 + (k^2+1) b^2) dt^2 -> (1/(k b)) * integral sqrt(r^2 + c^2) dr
    Lc = cc * spiral_length(R, R + 40 * k, cc) / (k * b)
    record("H5 lunghezza conica vs integrale in forma chiusa", rel(d.get("length", 0), Lc) < 1e-3,
           f"misurata {d.get('length')} mm, calcolata {Lc:.4f} mm, scarto {rel(d.get('length', 0), Lc) * 100:.4f} %")
    d = await need(c, "create_helix", "H5 conica verso l'interno", sketch=sk, pitch=P, revolutions=REV, taper_angle=10, taper_outward=False)
    r_end = radius_xy(d.get("end_point", [0, 0, 0]))
    record("H5 raggio finale interno = R - h tan(10 gradi)", abs(r_end - (R - 40 * k)) < 1e-3, f"misurato {r_end:.4f}, atteso {R - 40 * k:.4f}")
    # H6 spirale
    d = await need(c, "create_helix", "H6 spirale passo radiale 5, 4 giri", sketch=sk, definition="spiral", pitch=P, revolutions=4)
    Ls = spiral_length(R, R + 4 * P, P / (2 * PI))
    record("H6 raggio finale = R + 4*5 = 30 e punto finale nel piano z=0", abs(radius_xy(d.get("end_point", [0, 0, 1])) - 30) < 1e-3
           and abs(d.get("end_point", [0, 0, 1])[2]) < 1e-6, str(d.get("end_point")))
    record("H6 lunghezza spirale vs forma chiusa di Archimede", rel(d.get("length", 0), Ls) < 1e-3,
           f"misurata {d.get('length')} mm, calcolata {Ls:.4f} mm, scarto {rel(d.get('length', 0), Ls) * 100:.4f} %")
    d = await need(c, "create_helix", "H6 spirale verso l'interno (reverse_direction)", sketch=sk, definition="spiral", pitch=2, revolutions=3, reverse_direction=True)
    Ls = spiral_length(R - 6, R, 2 / (2 * PI))
    record("H6 spirale interna: raggio finale 10 - 2*3 = 4 e lunghezza", abs(radius_xy(d.get("end_point", [0, 0, 1])) - 4) < 1e-3 and rel(d.get("length", 0), Ls) < 1e-3,
           f"raggio finale {radius_xy(d.get('end_point', [0, 0, 0])):.4f}, lunghezza {d.get('length')} vs {Ls:.4f}")
    # H7 errori chiari
    ok, text, _ = await c.call("create_helix", sketch=sk, definition="pitch_revolutions", pitch=5)
    record("H7 parametro mancante: errore che dice cosa serve", (not ok) and "revolutions" in text, text.split("\n")[0][:120])
    ok, text, _ = await c.call("create_helix", sketch=sk, definition="spiral", pitch=5, revolutions=4, taper_angle=5)
    record("H7 conicita' su spirale: rifiutata", not ok, text.split("\n")[0][:120])
    ok, text, _ = await c.call("create_helix", sketch=sk, definition="spiral", pitch=5, revolutions=4, reverse_direction=True)
    record("H7 spirale interna con raggio negativo: errore chiaro", (not ok) and "raggio" in text.lower(), text.split("\n")[0][:140])
    await discard_all(c)


# ===================================================================================================== V
async def v_variabile(c):
    await new_part(c)
    await circle_sketch(c, 10)
    segs = [{"revolutions": 2, "pitch": 4}, {"revolutions": 1, "pitch": 8, "diameter": 30}]
    rows = [(0, 20, 4), (2, 20, 4), (3, 30, 8)]
    d = await need(c, "create_variable_pitch_helix", "V1 passo variabile: 2 giri a passo 4 + 1 giro 4->8 con diametro 20->30", segments=segs)
    Lv = vp_length(rows, "rev")
    record("V1 altezza finale = 2*4 + 1*(4+8)/2 = 14 e raggio finale 15", abs(d.get("end_point", [0, 0, 0])[2] - 14) < 1e-3
           and abs(radius_xy(d.get("end_point", [0, 0, 0])) - 15) < 1e-3, str(d.get("end_point")))
    record("V1 lunghezza misurata vs integrale numerico indipendente", rel(d.get("length", 0), Lv) < 2e-3,
           f"misurata {d.get('length')} mm, calcolata {Lv:.4f} mm, scarto {rel(d.get('length', 0), Lv) * 100:.4f} % (tolleranza 0,2 %)")
    dd = 1.0
    v0 = await vol(c)
    await need(c, "sweep", "V1 molla a passo variabile: sweep di un cerchio d=1", path_sketch=d.get("feature", "?"), circular_diameter=dd)
    v = (await vol(c)) - v0
    exp = PI * (dd / 2) ** 2 * d.get("length", 0)
    record("V1 volume dello sweep vs pi r^2 L (L misurata)", rel(v, exp) < 0.01, f"misurato {v:.3f} mm3, atteso {exp:.3f} mm3, scarto {rel(v, exp) * 100:.4f} % (tolleranza 1 %)")
    # definizione altezza + passo
    segs = [{"height": 10, "pitch": 4}, {"height": 20, "pitch": 8, "diameter": 30}]
    d = await need(c, "create_variable_pitch_helix", "V2 altezza+passo: 10 mm a passo 4, poi 20 mm 4->8 con diametro 30",
                   definition="height_pitch", segments=segs)
    rows = [(0, 20, 4), (10, 20, 4), (30, 30, 8)]
    Lv = vp_length(rows, "h")
    record("V2 altezza finale 30 e raggio finale 15", abs(d.get("end_point", [0, 0, 0])[2] - 30) < 1e-3
           and abs(radius_xy(d.get("end_point", [0, 0, 0])) - 15) < 1e-3, str(d.get("end_point")))
    record("V2 lunghezza vs integrale numerico", rel(d.get("length", 0), Lv) < 2e-3,
           f"misurata {d.get('length')} mm, calcolata {Lv:.4f} mm, scarto {rel(d.get('length', 0), Lv) * 100:.4f} %")
    ok, text, _ = await c.call("create_variable_pitch_helix", segments=[{"revolutions": 2}])
    record("V3 segmento senza passo: errore chiaro", (not ok) and "pitch" in text, text.split("\n")[0][:120])
    await discard_all(c)


# ===================================================================================================== P
async def p_proiezione(c):
    await new_part(c)
    await circle_sketch(c, 20)
    await need(c, "extrude_boss", "P0 cilindro R=20 h=50", depth=50)
    await c.call("create_sketch", plane="Right")
    await c.call("draw_line", x1=-10, y1=10, x2=-10, y2=40)      # piano Right: x schizzo = -X modello -> linea a X=+10, z da 10 a 40
    await c.call("close_sketch")
    sk = "Schizzo2"
    d = await need(c, "project_curve", "P1 linea proiettata sul cilindro", sketch=sk, face_points=[[20, 0, 25]])
    s, e = d.get("start_point", [0, 0, 0]), d.get("end_point", [0, 0, 0])
    record("P1 estremi sul cilindro (raggio 20) a X=10, Y=+17.3205", abs(radius_xy(s) - 20) < 1e-3 and abs(radius_xy(e) - 20) < 1e-3
           and abs(s[0] - 10) < 1e-3 and s[1] > 0, f"{s} -> {e}")
    record("P1 lunghezza 30 (z da 10 a 40)", abs(d.get("length", 0) - 30) < 1e-3 and {round(s[2]), round(e[2])} == {10, 40}, f"{d.get('length')} mm")
    d = await need(c, "project_curve", "P2 verso opposto (reverse)", sketch=sk, face_points=[[20, 0, 25]], reverse=True)
    s = d.get("start_point", [0, 0, 0])
    record("P2 il punto proiettato passa a Y=-17.3205 (raggio 20)", abs(radius_xy(s) - 20) < 1e-3 and s[1] < 0, str(s))
    d = await need(c, "project_curve", "P3 entrambi i versi", sketch=sk, face_points=[[20, 0, 25]], both_directions=True)
    other = d.get("other_direction", {})
    record("P3 due curve: Y=+17.3205 e Y=-17.3205", d.get("start_point", [0, 0, 0])[1] * other.get("start_point", [0, 0, 0])[1] < 0
           and abs(radius_xy(other.get("start_point", [0, 0, 0])) - 20) < 1e-3, f"{d.get('start_point')} / {other.get('start_point')}")
    # schizzo su schizzo: cilindro R=10 (asse Z) e retta z = x + 10 nel piano Right
    await discard_all(c)
    await new_part(c)
    await circle_sketch(c, 10)
    await c.call("create_sketch", plane="Right")
    await c.call("draw_line", x1=15, y1=-5, x2=-15, y2=25)       # x schizzo = -X: da (X=-15,z=-5) a (X=15,z=25), z = X + 10
    await c.call("close_sketch")
    d = await need(c, "project_curve", "P4 schizzo su schizzo: cerchio x piano inclinato", sketch="Schizzo1", target_sketch="Schizzo2")
    ellisse = 0.0
    a_, b_ = 10 * math.sqrt(2), 10.0
    n = 200000
    for i in range(n):
        t = 2 * PI * (i + 0.5) / n
        ellisse += math.sqrt((a_ * math.sin(t)) ** 2 + (b_ * math.cos(t)) ** 2) * 2 * PI / n
    record("P4 lunghezza = perimetro dell'ellisse (a=10 sqrt2, b=10)", rel(d.get("length", 0), ellisse) < 1e-3,
           f"misurata {d.get('length')} mm, calcolata {ellisse:.4f} mm, scarto {rel(d.get('length', 0), ellisse) * 100:.4f} %")
    s, m = d.get("start_point", [0, 0, 0]), d.get("mid_point", [0, 0, 0])
    record("P4 punti della curva: raggio 10 e z = x + 10 (iniziale e intermedio)", all(abs(radius_xy(p) - 10) < 1e-3 and abs(p[2] - p[0] - 10) < 1e-3 for p in (s, m)),
           f"{s}, {m}")
    ok, text, _ = await c.call("project_curve", sketch="Schizzo1")
    record("P5 senza facce ne' secondo schizzo: errore", not ok, text.split("\n")[0][:120])
    await discard_all(c)


# ===================================================================================================== S
async def s_divisione(c):
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_rectangle", x1=-40, y1=-40, x2=40, y2=40)
    await c.call("close_sketch")
    await need(c, "extrude_boss", "S0 blocco 80x80x20", depth=20)
    ok, _, p = await c.call("create_reference_plane", mode="offset", base="top", distance=40)
    pl = p.get("feature")
    await c.call("create_sketch", plane=pl)
    await c.call("draw_circle", x=0, y=0, radius=10)
    await c.call("close_sketch")
    d = await need(c, "split_line", "S1 proiezione del cerchio r=10 sulla faccia superiore", mode="projection", sketch="Schizzo2", face_points=[[30, 30, 20]])
    areas = d.get("new_face_areas", [])
    record("S1 facce 6 -> 7", d.get("faces_before") == 6 and d.get("faces_after") == 7, f"{d.get('faces_before')} -> {d.get('faces_after')}")
    record("S1 area del cerchio = pi*100 = 314.159 mm2 e del resto = 6400 - pi*100",
           len(areas) == 2 and rel(areas[0], PI * 100) < 1e-4 and rel(areas[1], 6400 - PI * 100) < 1e-4, str(areas))
    await discard_all(c)
    await new_part(c)
    await circle_sketch(c, 20)
    await need(c, "extrude_boss", "S2 cilindro R=20 h=50", depth=50)
    d = await need(c, "split_line", "S2 silhouette rispetto al piano frontale", mode="silhouette", direction={"plane": "front"}, face_points=[[20, 0, 25]])
    areas = d.get("new_face_areas", [])
    half = PI * 20 * 50
    record("S2 facce 3 -> 4 e le due meta' della superficie laterale: pi*R*h = 3141.59 mm2 ciascuna",
           d.get("faces_before") == 3 and d.get("faces_after") == 4 and len(areas) == 2 and all(rel(a, half) < 1e-4 for a in areas), str(areas))
    ok, text, dat = await c.call("split_line", mode="intersection", cutter={"plane": "top"}, face_points=[[20, 0, 25]])
    record("S3 intersezione: limite SolidWorks dichiarato nel risultato (nessuna feature, nessun crash)", (not ok) and "Limite noto" in text,
           text.split("\n")[0][:170])
    ok, text, _ = await c.call("split_line", mode="projection", face_points=[[20, 0, 25]], sketch="Schizzo1")
    record("S4 schizzo che non proietta sulla faccia scelta: errore chiaro", not ok, text.split("\n")[0][:140])
    await discard_all(c)


# ===================================================================================================== C
async def c_composita(c):
    await new_part(c)
    await c.call("create_sketch", plane="Top")
    await c.call("draw_rectangle", x1=-40, y1=-40, x2=40, y2=40)
    await c.call("close_sketch")
    await need(c, "extrude_boss", "C0 blocco 80x80x20", depth=20)
    await need(c, "fillet_edges", "C0 spigoli verticali raccordati r=10", radius=10, edge_points=[[40, 40, 10], [-40, 40, 10], [40, -40, 10], [-40, -40, 10]])
    cc = 30 + 10 * math.cos(math.radians(45))
    eds = [[0, -40, 20], [40, 0, 20], [0, 40, 20], [-40, 0, 20], [cc, cc, 20], [-cc, cc, 20], [cc, -cc, 20], [-cc, -cc, 20]]
    d = await need(c, "composite_curve", "C1 composita degli 8 spigoli superiori (4 rette + 4 archi)", edge_points=eds)
    per = 4 * 60 + 2 * PI * 10
    record("C1 lunghezza = perimetro 4*60 + 2 pi 10 = 302.832 mm", rel(d.get("length", 0), per) < 1e-5 and d.get("entities") == 8,
           f"misurata {d.get('length')} mm, calcolata {per:.5f} mm")
    ok, text, _ = await c.call("composite_curve", edge_points=[[0, -40, 20], [0, 40, 20]])
    record("C2 due spigoli non contigui: errore chiaro", not ok, text.split("\n")[0][:140])
    await discard_all(c)
    # da schizzo: retta + arco tangente + retta, percorso di sweep
    await new_part(c)
    s45 = math.sin(math.radians(45))
    await c.call("create_sketch", plane="Top")
    await c.call("draw_line", x1=0, y1=0, x2=30, y2=0)
    await c.call("draw_arc_3point", x1=30, y1=0, x2=30 + 10 * s45, y2=10 - 10 * s45, x3=40, y3=10)
    await c.call("draw_line", x1=40, y1=10, x2=40, y2=40)
    await c.call("close_sketch")
    ents = [{"sketch": "Schizzo1", "entity": "@15,0"}, {"sketch": "Schizzo1", "entity": "@%g,%g" % (30 + 10 * s45, 10 - 10 * s45)},
            {"sketch": "Schizzo1", "entity": "@40,25"}]
    d = await need(c, "composite_curve", "C3 composita da schizzo: retta 30 + arco r=10 (90 gradi) + retta 30", sketch_entities=ents)
    Lp = 60 + 5 * PI
    record("C3 lunghezza = 60 + 5 pi = 75.708 mm", rel(d.get("length", 0), Lp) < 1e-5 and d.get("entities") == 3,
           f"misurata {d.get('length')} mm, calcolata {Lp:.5f} mm")
    v0 = await vol(c)
    await need(c, "sweep", "C3 sweep di un cerchio d=2 lungo la composita", path_sketch=d.get("feature", "?"), circular_diameter=2)
    v = (await vol(c)) - v0
    exp = PI * 1.0 * Lp
    record("C3 volume dello sweep vs pi r^2 L", rel(v, exp) < 5e-3, f"misurato {v:.3f} mm3, atteso {exp:.3f} mm3, scarto {rel(v, exp) * 100:.4f} % (tolleranza 0,5 %)")
    ok, text, _ = await c.call("composite_curve")
    record("C4 senza entita': errore", not ok, text.split("\n")[0][:100])
    await discard_all(c)


# ===================================================================================================== T
async def t_punti(c):
    await new_part(c)
    pts = [[0, 0, 0], [10, 0, 5], [20, 10, 0], [30, 10, -5], [40, 0, 0]]
    d = await need(c, "curve_through_points", "T1 curva aperta per 5 punti", points=pts)
    chord = sum(math.dist(a, b) for a, b in zip(pts[:-1], pts[1:]))
    record("T1 estremi uguali ai punti dati", close(d.get("start_point", []), pts[0], 1e-4) and close(d.get("end_point", []), pts[-1], 1e-4),
           f"{d.get('start_point')} -> {d.get('end_point')}")
    record("T1 la curva passa per tutti i punti (distanza massima < 1e-4 mm)", d.get("max_point_deviation", 1) < 1e-4, f"{d.get('max_point_deviation')} mm")
    record("T1 lunghezza fra la spezzata dei punti e +10 %", chord <= d.get("length", 0) <= chord * 1.10, f"spezzata {chord:.3f}, curva {d.get('length')}")
    d = await need(c, "curve_through_points", "T2 curva chiusa per gli stessi punti", points=pts, closed=True)
    record("T2 chiusa: inizio = fine = primo punto", close(d.get("start_point", []), pts[0], 1e-4) and close(d.get("end_point", []), pts[0], 1e-4)
           and d.get("max_point_deviation", 1) < 1e-4, f"{d.get('start_point')} -> {d.get('end_point')}, dev {d.get('max_point_deviation')}")
    n, R = 16, 20.0
    circ = [[R * math.cos(2 * PI * i / n), R * math.sin(2 * PI * i / n), 5] for i in range(n)]
    d = await need(c, "curve_through_points", "T3 16 punti su un cerchio R=20 (z=5), chiusa", points=circ, closed=True)
    record("T3 lunghezza ~ 2 pi R = 125.664 mm", rel(d.get("length", 0), 2 * PI * R) < 2e-3,
           f"misurata {d.get('length')} mm, calcolata {2 * PI * R:.4f} mm, scarto {rel(d.get('length', 0), 2 * PI * R) * 100:.4f} % (tolleranza 0,2 %)")
    m = d.get("mid_point", [0, 0, 0])
    record("T3 punto intermedio diametralmente opposto (-20,0,5)", close(m, [-R, 0, 5], 0.05), str(m))
    semi = [[R * math.cos(PI * i / 8), R * math.sin(PI * i / 8), 0] for i in range(9)]
    d = await need(c, "curve_through_points", "T4 9 punti su una semicirconferenza R=20, aperta", points=semi)
    record("T4 lunghezza ~ pi R = 62.832 mm", rel(d.get("length", 0), PI * R) < 2e-3,
           f"misurata {d.get('length')} mm, calcolata {PI * R:.4f} mm, scarto {rel(d.get('length', 0), PI * R) * 100:.4f} %")
    # vertici del modello
    await c.call("create_sketch", plane="Top")
    await c.call("draw_rectangle", x1=-40, y1=-40, x2=40, y2=40)
    await c.call("close_sketch")
    await need(c, "extrude_boss", "T5 blocco 80x80x20", depth=20)
    verts = [[40, 40, 20], [-40, 40, 20], [-40, -40, 20], [40, -40, 20]]
    d = await need(c, "curve_through_points", "T5 curva chiusa per 4 vertici del blocco", vertex_points=verts, closed=True)
    record("T5 inizio = fine = primo vertice e passa per tutti", close(d.get("start_point", []), verts[0], 1e-4) and d.get("max_point_deviation", 1) < 1e-4,
           f"{d.get('start_point')}, dev {d.get('max_point_deviation')}")
    ok, text, _ = await c.call("curve_through_points", points=[[0, 0, 0]])
    record("T6 un solo punto: errore chiaro", not ok, text.split("\n")[0][:100])
    await discard_all(c)


if __name__ == "__main__":
    done = asyncio.run(run())
    print("\n==== RIEPILOGO ====")
    for tool, res, note in RESULTS:
        print(f"{res:5} {tool:70} {note}"[:230])
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print(f"\n{npass}/{len(RESULTS)} PASS")
    sys.exit(0 if done and npass == len(RESULTS) else 1)
