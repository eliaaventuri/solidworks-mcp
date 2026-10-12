"""
Test di QUALITA' delle tavole (blocco 4): quote ISO 129, scala/foglio automatici, tolleranze, sezioni, annotazioni.

Genera con i soli tool MCP le tavole di albero, staffa, flangia, un perno piccolo e l'assieme, poi controlla in automatico
(da get_drawing_layout):
  - nessuna sovrapposizione fra riquadri di annotazioni, quote, viste, cartiglio e distinta;
  - tutto dentro il foglio;
  - zero quote duplicate (stessi punti di riferimento nel modello, oppure stesso diametro due volte);
  - verso delle quote coerente (orizzontali sopra/sotto la vista col testo orizzontale, verticali a destra/sinistra
    col testo a 90 gradi, tutte FUORI dal contorno della vista);
  - simbolo della tolleranza geometrica presente (letto dal tool) e riquadro presente sul foglio;
  - foglio A4/A3 e scala della serie ISO scelti da soli (perno piccolo: scala di ingrandimento).
Gruppo A di LIMITI.md (A1-A15): linee di esplosione, tolleranze agganciate alle feature, quote di cave, richiami dei raggi, etichette
dei fori, scelta del formato, quote d'ingombro d'assieme + palloncini, N. DISEGNO lungo, tolleranza solo sul disegno, quota angolare
reale, ritaglio rettangolare/poligonale, vista interrotta, inversione della sezione, formato verticale A3, nuovo foglio automatico.
I PNG esportati (test_output/qual_*.png) vanno guardati a occhio: il test li elenca alla fine.

Gira su un'istanza SolidWorks DEDICATA e nascosta (SW_MCP_INSTANCE=dedicated): quella dell'utente non viene toccata,
alla fine si chiude SOLO il PID proprio. I pezzi mancanti (albero/staffa/flangia/assieme) si costruiscono con i test di
modellazione e di assieme (tool MCP).

Uso:  .venv\\Scripts\\python.exe tests\\test_drawing_quality_live.py
"""

import os
import sys
import json
import math
import asyncio
import subprocess
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
OUT = ROOT / "test_output"
OUT.mkdir(exist_ok=True)
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
SERVER = ROOT / "solidworks_mcp_server.py"

OVERWRITE_TOOLS = {"save_document", "save_drawing", "export_drawing", "export_model", "export_model_image", "export_simulation_plot", "create_drawing"}
RESULTS = []
ISO_SCALES = {0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0}
TOL = 0.3        # mm di tolleranza nei controlli di sovrapposizione (riquadri che si sfiorano non contano)
PNGS = []


def sw_pids():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq SLDWORKS.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    pids = set()
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) > 1 and parts[0].strip('"').lower() == "sldworks.exe":
            pids.add(int(parts[1]))
    return pids


class Client:
    def __init__(self, session):
        self.s = session

    async def call(self, tool_name, /, **args):
        if tool_name in OVERWRITE_TOOLS:       # gruppo B: i file di test_output vengono riscritti a ogni esecuzione
            args.setdefault("overwrite", True)
        r = await self.s.call_tool(tool_name, args)
        text = "".join(c.text for c in r.content if hasattr(c, "text"))
        ok = text.startswith("[SUCCESS]")
        data = {}
        if "Details: " in text:
            try:
                data = json.loads(text.split("Details: ", 1)[1])
            except Exception:
                data = {}
        return ok, text, data


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:260])


async def T(c, tool, descr=None, check=None, **args):
    ok, text, d = await c.call(tool, **args)
    good = ok
    if ok and check is not None:
        try:
            good = bool(check(d))
        except Exception as e:
            good = False
            text += f" [check: {e}]"
    record(f"{tool}: {descr}" if descr else tool, good, text.split("\n")[0][:190])
    return d if ok else {}


# ------------------------------------------------------------------------------------------ controlli geometrici
def inter(a, b, tol=TOL):
    """True se i riquadri (x0,y0,x1,y1) si sovrappongono per piu' di tol (mm) in entrambe le direzioni."""
    return min(a[2], b[2]) - max(a[0], b[0]) > tol and min(a[3], b[3]) - max(a[1], b[1]) > tol


def dim_box(a):
    """Riquadro di una quota ai fini dei controlli: per i diametri di cerchio il testo, altrimenti il corpo."""
    if a.get("dim_kind") in ("dia", "rad", "ang") and a.get("text_rect"):
        return a["text_rect"]
    return a["rect"]


def seg_hits(sg, r):
    """Il segmento (x0,y0,x1,y1) interseca il rettangolo r (Liang-Barsky)."""
    x0, y0, x1, y1 = sg
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p_, q_ in ((-dx, x0 - r[0]), (dx, r[2] - x0), (-dy, y0 - r[1]), (dy, r[3] - y0)):
        if abs(p_) < 1e-12:
            if q_ < 0:
                return False
        else:
            t = q_ / p_
            if p_ < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
    return t0 <= t1


def seg_dist(p, a, b):
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def check_a17(lay):
    """A17: (1) le linee delle quote non attraversano i fori (cerchi) a cui non sono ancorate; (2) nessuna linea di quota o di
    richiamo attraversa il testo di una nota/titolo di vista (SEZIONE A-A...); (3) ogni riquadro GD&T e' agganciato
    (linea di richiamo con freccia, oppure legato a una quota)."""
    probs = []
    anns = lay["annotations"]
    for v in lay["views"]:
        for h in v.get("holes", []):
            c = (h["cx"], h["cy"])
            for a in anns:
                if a["kind"] != "dimension" or a.get("dim_kind") != "lin" or a.get("view") != v["name"]:
                    continue
                for l in a.get("lines", []):
                    p0, p1 = (l[0], l[1]), (l[2], l[3])
                    if seg_dist(c, p0, p1) < h["r"] * 0.9:
                        own = min(math.hypot(p0[0] - c[0], p0[1] - c[1]), math.hypot(p1[0] - c[0], p1[1] - c[1])) < h["r"] * 1.3
                        if not own:
                            probs.append(f"linea della quota {a.get('text', '')} attraversa il foro in ({c[0]:.0f},{c[1]:.0f})")
    for n in anns:
        if n["kind"] != "note" or (not n.get("text", "").strip() and n.get("view") == "sheet"):
            continue
        r = n["rect"]
        rr = (r[0] + 0.3, r[1] + 0.3, r[2] - 0.3, r[3] - 0.3)
        if rr[2] <= rr[0] or rr[3] <= rr[1]:
            continue
        for a in anns:
            if a["kind"] != "dimension":
                continue
            for l in a.get("lines", []):
                if seg_hits(tuple(l), rr):
                    probs.append(f"una linea della quota {a.get('text', '')} attraversa la nota/titolo '{n.get('text', '').strip()[:20]}'")
                    break
    for g in anns:
        if g["kind"] != "gtol":
            continue
        touching = any(a["kind"] == "dimension" and inter(g["rect"], a["rect"], -1.2) for a in anns)
        if g.get("leaders", 0) < 1 and not touching:
            probs.append(f"riquadro GD&T in ({g['rect'][0]:.0f},{g['rect'][1]:.0f}) non agganciato (nessun richiamo, nessuna quota)")
    return probs


def check_layout(tag, lay, expect_paper=None, skip_angle=()):
    """Esegue tutti i controlli automatici su un get_drawing_layout. Restituisce il numero di problemi."""
    probs = []
    W, H = lay["sheet_mm"]
    views = lay["views"]
    anns = lay["annotations"]
    title = lay["title_block"]
    reserved = lay.get("reserved", [])
    # ---- tutto dentro il foglio (cornice a 12 mm)
    fx0, fy0, fx1, fy1 = 12.0, 12.0, W - 12.0, H - 12.0
    for v in views:
        r = v["core"]
        if r[0] < fx0 or r[1] < fy0 or r[2] > fx1 or r[3] > fy1:
            probs.append(f"vista {v['name']} fuori dal foglio {r}")
    for a in anns:
        r = dim_box(a) if a["kind"] == "dimension" else a["rect"]
        if r[0] < fx0 or r[1] < fy0 or r[2] > fx1 or r[3] > fy1:
            probs.append(f"{a['kind']} '{a.get('text', '')[:20]}' fuori dal foglio {r}")
        if a["kind"] == "dimension" and a.get("full_rect"):
            fr = a["full_rect"]
            if fr[0] < 0 or fr[1] < 0 or fr[2] > W or fr[3] > H:
                probs.append(f"linee della quota '{a.get('text', '')[:20]}' escono dal foglio {fr}")
    # ---- viste fra loro, con cartiglio e distinta
    for i, v in enumerate(views):
        for j in range(i + 1, len(views)):
            if inter(v["core"], views[j]["core"]):
                probs.append(f"viste sovrapposte: {v['name']} / {views[j]['name']}")
        if inter(v["core"], title):
            probs.append(f"vista {v['name']} sul cartiglio")
        for k, rr in enumerate(reserved):
            if inter(v["core"], rr):
                probs.append(f"vista {v['name']} sulla distinta")
    # ---- annotazioni: fra loro, con cartiglio/distinta, con le viste
    boxes = []
    for a in anns:
        r = dim_box(a) if a["kind"] == "dimension" else a["rect"]
        boxes.append((a, r))
    for i, (a, ra) in enumerate(boxes):
        label = f"{a['kind']}({a.get('text', '')[:14]})"
        if inter(ra, title):
            probs.append(f"{label} sul cartiglio")
        for rr in reserved:
            if inter(ra, rr):
                probs.append(f"{label} sulla distinta")
        for v in views:
            if a["kind"] == "dimension" and inter(ra, v["core"]):
                if not (a.get("dim_kind") == "lin" and a.get("callout")):
                    probs.append(f"quota {label} dentro il contorno di {v['name']}")
        for j in range(i + 1, len(boxes)):
            b, rb = boxes[j]
            if inter(ra, rb):
                # quote in catena sulla stessa riga: condividono la linea di estensione, le frecce sporgono ~1 mm: non e' sovrapposizione
                if a["kind"] == b["kind"] == "dimension" and a.get("axis") == b.get("axis") in ("H", "V")                         and a.get("dim_kind") == b.get("dim_kind") == "lin":
                    k = 0 if a["axis"] == "H" else 1
                    if min(ra[k + 2], rb[k + 2]) - max(ra[k], rb[k]) <= 1.6:
                        continue
                # quote della stessa riga e dello stesso asse con tratti che non si sovrappongono e testi separati: coda delle frecce
                # esterne (tratto corto) o testo spostato, non sono sovrapposizioni vere
                if a["kind"] == b["kind"] == "dimension" and a.get("axis") == b.get("axis") in ("H", "V")                         and a.get("dim_kind") == b.get("dim_kind") == "lin" and a.get("span") and b.get("span"):
                    if abs(a["rect"][1 if a["axis"] == "H" else 0] - b["rect"][1 if a["axis"] == "H" else 0]) < 0.6                             and min(a["span"][1], b["span"][1]) - max(a["span"][0], b["span"][0]) <= 0.2                             and not (a.get("text_rect") and b.get("text_rect") and inter(a["text_rect"], b["text_rect"], 0.0)):
                        continue
                # riquadro di tolleranza legato a una quota: SolidWorks lo appende sotto/sopra la linea di quota (prassi ISO 1101),
                # tocca la linea di quota per meno di 1 mm: non e' sovrapposizione
                if {a["kind"], b["kind"]} == {"gtol", "dimension"}:
                    ox = min(ra[2], rb[2]) - max(ra[0], rb[0])
                    oy = min(ra[3], rb[3]) - max(ra[1], rb[1])
                    if min(ox, oy) <= 1.0:
                        continue
                probs.append(f"sovrapposizione {label} / {b['kind']}({b.get('text', '')[:14]})")
    # ---- linee di richiamo oblique delle tolleranze geometriche: non devono attraversare il TESTO di una quota
    for a in anns:
        for sg in a.get("leader_segs", []):
            for b in anns:
                if b["kind"] == "dimension" and b.get("text_rect") and seg_hits(sg, b["text_rect"]):
                    probs.append(f"richiamo della tolleranza attraversa il testo della quota {b.get('text', '')[:14]}")
    # ---- palloncini (A7): il cerchio non deve coprire le viste, ne' sovrapporsi ad altro (gia' coperto sopra come annotazione)
    for a in anns:
        if a["kind"] == "balloon":
            for v in views:
                if inter(a["rect"], v["core"], 0.5):
                    probs.append(f"palloncino {a.get('text', '')} sopra la vista {v['name']}")
    # ---- duplicati
    seen = {}
    for a in anns:
        if a["kind"] != "dimension":
            continue
        if a.get("refpts"):
            key = (a["dim_kind"], round(a["value"], 3), a.get("axis"), tuple(sorted(tuple(p) for p in a["refpts"])))
        else:
            key = (a["dim_kind"], round(a["value"], 3), a["view"], a.get("axis"), round(a["rect"][0]), round(a["rect"][1]))
        seen.setdefault(key, []).append(a)
    for key, g in seen.items():
        if len(g) > 1:
            probs.append(f"quota duplicata {key[0]} {key[1]} ({len(g)} volte)")
    dia = {}
    for a in anns:
        if a["kind"] == "dimension" and ("<MOD-DIAM>" in (a.get("text", "")) or a.get("dim_kind") == "dia"):
            dia.setdefault(round(a["value"], 3), []).append(a)
    for val, g in dia.items():
        if len(g) > 1:
            probs.append(f"diametro {val} quotato {len(g)} volte")
    # ---- verso delle quote
    for a in anns:
        if a["kind"] != "dimension" or a.get("dim_kind") != "lin" or a.get("axis") not in ("H", "V"):
            continue
        ang = a.get("text_angle_deg", 0.0) % 180.0
        if any(sv in a.get("text", "") for sv in skip_angle):
            ang = 0.0 if a["axis"] == "H" else 90.0     # quota con riquadro di tolleranza agganciato: SW porta il testo in orizzontale
        if a["axis"] == "H" and not (ang < 1.0 or ang > 179.0):
            probs.append(f"quota orizzontale {a.get('text', '')} con testo a {ang} gradi")
        if a["axis"] == "V" and abs(ang - 90.0) > 1.0:
            probs.append(f"quota verticale {a.get('text', '')} con testo a {ang} gradi")
        if a.get("side") == "inside":
            probs.append(f"quota {a.get('text', '')} {a['axis']} dentro il contorno della vista {a['view']}")
        if a["axis"] == "H" and a.get("side") not in ("above", "below", "inside", None):
            probs.append(f"quota orizzontale con lato {a.get('side')}")
        if a["axis"] == "V" and a.get("side") not in ("left", "right", "inside", None):
            probs.append(f"quota verticale con lato {a.get('side')}")
        off = a.get("offset_mm", 0.0)
        if a.get("side") in ("above", "below", "left", "right") and off < 7.0:
            probs.append(f"quota {a.get('text', '')} a soli {off} mm dal contorno")
    probs += check_a17(lay)
    for p in probs[:12]:
        print(f"      - {p}")
    record(f"{tag}: layout senza sovrapposizioni, tutto nel foglio, nessun duplicato, versi coerenti",
           not probs, f"{len(probs)} problemi; {len(anns)} annotazioni, {len(views)} viste" +
           (f": {probs[0]}" if probs else ""))
    return len(probs)


async def finish_sheet(c, tag, drw, expect_dims=True, expect_paper=("A4", "A3"), skip_angle=()):
    """Esporta il PNG, legge il layout, controlla e chiude (salvando il disegno ma NON il modello)."""
    png = OUT / f"qual_{tag}.png"
    if png.exists():
        png.unlink()
    await T(c, "export_drawing", f"{tag}: PNG", filepath=str(png), format="png")
    PNGS.append(str(png))
    ok, text, lay = await c.call("get_drawing_layout")
    record(f"{tag}: get_drawing_layout", ok and bool(lay.get("views")), text.split("\n")[0][:120])
    if ok:
        check_layout(tag, lay, skip_angle=skip_angle)
        if expect_dims:
            n = sum(1 for a in lay["annotations"] if a["kind"] == "dimension")
            record(f"{tag}: quote presenti", n >= 3, f"{n} quote")
    await c.call("save_drawing", filepath=str(drw))
    await c.call("close_document", discard=True)
    return lay if ok else {}


async def make_drawing(c, tag, model, views, scale=None, exploded=False, paper="auto"):
    drw = OUT / f"qual_{tag}.SLDDRW"
    if drw.exists():
        drw.unlink()
    d = await T(c, "create_drawing", f"{tag}: foglio automatico", model_path=str(model), paper_size=paper,
                save_as=str(drw), add_views=False, save_model=False)
    kw = {"views": views}
    if scale:
        kw["scale"] = scale
    if exploded:
        kw["exploded"] = True
    d = await T(c, "add_standard_views", f"{tag}: viste e scala automatiche", **kw)
    paper_mm = d.get("paper_mm") or [420, 297]
    sc = d.get("scale", "1:1")
    n, dd = (sc.split(":") + ["1"])[:2]
    dec = float(n) / float(dd)
    return drw, paper_mm, dec, d


def paper_ok(paper_mm):
    w, h = sorted(paper_mm)
    return (abs(w - 210) < 1 and abs(h - 297) < 1) or (abs(w - 297) < 1 and abs(h - 420) < 1)


# ------------------------------------------------------------------------------------------ pezzi
async def ensure_parts(c):
    import test_modeling_live as TM
    for name, fn in (("albero", TM.albero), ("staffa", TM.staffa), ("flangia", TM.flangia)):
        p = OUT / f"{name}.SLDPRT"
        if not p.exists():
            print(f"\n(costruisco {name} con i tool di modellazione)")
            await fn(c)
        record(f"pezzo {name} disponibile", p.exists(), p.name)
    p = OUT / "qual_perno.SLDPRT"
    if p.exists():
        p.unlink()
    await T(c, "create_new_part", "perno piccolo")
    await T(c, "create_sketch", "perno: schizzo", plane="Front")
    await T(c, "draw_circle", "perno: cerchio", x=0, y=0, radius=3, unit="mm")
    await T(c, "extrude_boss", "perno: Ø6 x 14", depth=14, unit="mm")
    await T(c, "chamfer_at_points", "perno: smusso 0,5", distance=0.5, edge_points=[[14, 3, 0]])
    await T(c, "save_document", "perno: salva", filepath=str(p))
    await c.call("close_document", discard=True)
    # cuneo con faccia inclinata di 30 gradi (quota angolare VERA dello schizzo, non uno smusso): caso di prova per A10
    p2 = OUT / "cuneo.SLDPRT"
    if p2.exists():
        p2.unlink()
    await T(c, "create_new_part", "cuneo")
    await T(c, "create_sketch", "cuneo: schizzo", plane="Front")
    pts = [(0, 0), (60, 0), (60, 20), (25, 40), (0, 40)]
    ids = []
    for k in range(len(pts)):
        a_, b_ = pts[k], pts[(k + 1) % len(pts)]
        d_ = await T(c, "draw_line", f"cuneo: lato {k + 1}", x1=a_[0], y1=a_[1], x2=b_[0], y2=b_[1])
        ids.append(d_.get("entity_id"))
    await T(c, "add_sketch_dimension", "cuneo: quota angolare 30 gradi fra base e faccia inclinata", kind="angle", entity1=ids[0],
            entity2=ids[2], value=30)
    await T(c, "add_sketch_dimension", "cuneo: lunghezza 60", kind="length", entity1=ids[0], value=60)
    await T(c, "add_sketch_dimension", "cuneo: altezza 40", kind="length", entity1=ids[4], value=40)
    await T(c, "extrude_boss", "cuneo: spessore 30", depth=30, unit="mm")
    await T(c, "save_document", "cuneo: salva", filepath=str(p2))
    await c.call("close_document", discard=True)
    asm = OUT / "asm_main.SLDASM"
    if not asm.exists():
        import test_assembly_live as TA
        print("\n(costruisco l'assieme con i tool di assieme)")
        await TA.build_parts(c)
        await TA.main_assembly(c)
    record("assieme asm_main disponibile", asm.exists(), asm.name)


# ------------------------------------------------------------------------------------------ tavole
async def sheet_albero(c):
    print("\n== Tavola albero")
    drw, paper, sc, d = await make_drawing(c, "albero", OUT / "albero.SLDPRT", ["front", "top", "right", "isometric"])
    record("albero: foglio A4/A3 e scala ISO scelti da soli", paper_ok(paper) and sc in ISO_SCALES, f"{paper} scala {d.get('scale')}")
    r = await T(c, "insert_model_dimensions", "albero: quote importate e disposte (ISO 129)", all_views=True,
                check=lambda d: d.get("arranged") and d.get("diameter_dims_added", 0) >= 3 and d.get("pocket_dims_added", 0) >= 3)
    ok, text, lay = await c.call("get_drawing_layout")
    anns = lay.get("annotations", [])
    # i diametri degli alberi sono quote lineari con Ø; non restano quote radiali importate
    dia_vals = sorted(round(a["value"], 2) for a in anns if a["kind"] == "dimension" and "<MOD-DIAM>" in a.get("text", ""))
    record("albero: diametri come quote lineari con Ø (20, 25, 30)", {20.0, 25.0, 30.0} <= set(dia_vals), str(dia_vals))
    vs = [v for v in lay.get("views", []) if not v["pictorial"]]
    front = vs[0]["name"] if vs else None
    # A3: cava quotata (lunghezza, larghezza, posizione dalla testata)
    roles = {p_["role"]: p_["value"] for p_ in (r.get("pocket_dims") or [])}
    record("albero: cava quotata in lunghezza 30, larghezza 8, posizione 55 dalla testata (A3)",
           abs(roles.get("L", 0) - 30) < 0.01 and abs(roles.get("W", 0) - 8) < 0.01 and abs(roles.get("P", 0) - 55) < 0.01, str(roles))
    # A9: la tolleranza resta SOLO sul disegno (quota di riferimento del disegno al posto della quota pilota del modello)
    await T(c, "set_dimension_tolerance", "simmetrica 40 +-0,1 (solo disegno)", dimension="40,00", tolerance_type="symmetric", upper=0.1,
            check=lambda d: "0,10" in d.get("text", "") and d.get("drawing_only") is True and d.get("applied_to_model") is False
            and "@" in d.get("dimension", "") and d["dimension"].startswith("RD"))
    await T(c, "set_dimension_tolerance", "classe ISO H7/g6 sul Ø25", dimension="25", tolerance_type="fit", hole_fit="H7",
            shaft_fit="g6", check=lambda d: "g6" in d.get("text", ""))
    await T(c, "set_dimension_tolerance", "albero g6 sul Ø20 + precisione", dimension="20", tolerance_type="fit", shaft_fit="g6",
            precision=2, check=lambda d: "g6" in d.get("text", ""))
    await T(c, "set_dimension_tolerance", "limiti sul 70", dimension="70", tolerance_type="limit", upper=0.05, lower=0.05,
            check=lambda d: "70,05" in d.get("text", "") and "69,95" in d.get("text", ""))
    # una quota del modello che non si puo' copiare (nome inesistente) o con apply_to_model dichiarato
    await T(c, "set_dimension_tolerance", "apply_to_model=true: dichiarato nel risultato", dimension="4", tolerance_type="symmetric",
            upper=0.05, apply_to_model=True, check=lambda d: d.get("applied_to_model") is True and d.get("scope") == "model")
    await c.call("set_dimension_tolerance", dimension="4", tolerance_type="none", apply_to_model=True)    # ripristino del modello
    await T(c, "arrange_drawing_dimensions", "riordino delle quote dopo le tolleranze (testi piu' larghi)")
    # tolleranze geometriche AGGANCIATE alla feature (A2): freccia sullo spigolo, legame con una quota, riferimento A
    d = await T(c, "add_geometric_tolerance", "cilindricita' con freccia sulla silhouette del Ø25", characteristic="cylindricity",
                tolerance="0.02", view=front, model_point=[0, 125, 12.5],
                check=lambda d: d["frames"][0]["symbol"] == "<GTOL-CYL>" and d["attached_to"] == "edge" and d["leaders"] >= 1)
    d = await T(c, "add_datum", "riferimento A agganciato allo spigolo della testata", label="A", view=front, model_point=[0, 0, 0],
                check=lambda d: d["attached_to"] == "edge" and d["placed_near_target"] is True)
    d = await T(c, "add_geometric_tolerance", "perpendicolarita' (A) con freccia sullo spigolo di testa", characteristic="perpendicularity",
                tolerance="0.05", datum_refs=["A"], view=front, model_point=[0, 140, 0],
                check=lambda d: d["attached_to"] == "edge" and d["leaders"] >= 1 and d["placed_near_target"] is True)
    dist = math.hypot(d["position_mm"][0] - d["target_mm"][0], d["position_mm"][1] - d["target_mm"][1]) if d else 999
    record("albero: riquadro vicino al bersaglio (< 60 mm dalla freccia) (A2)", dist < 60.0, f"{dist:.1f} mm")
    d = await T(c, "add_geometric_tolerance", "parallelismo (A) legato alla quota 140 (agganciato alla quota)", characteristic="parallelism",
                tolerance="0.05", datum_refs=["A"], on_dimension="140", view=front,
                check=lambda d: d["attached_to"] == "dimension" and d["frames"][0]["symbol"] == "<GTOL-PARA>")
    d = await T(c, "add_geometric_tolerance", "posizione Ø con (M) + perpendicolarita' (2 riquadri) sulla silhouette del Ø30",
                characteristic="position", tolerance="0.1", datum_refs=["A"], view=front, model_point=[0, 75, 15], diameter=True,
                material_condition="M", extra_frames=[{"characteristic": "perpendicularity", "tolerance": "0.05", "datum_refs": ["A", "B"]}],
                check=lambda d: d["frame_count"] == 2 and d["frames"][0]["symbol"] == "<GTOL-POSI>" and d["attached_to"] == "edge")
    await T(c, "add_general_roughness", "Ra 3,2 generale", value="3.2")
    lay = await finish_sheet(c, "albero", drw)
    anns = lay.get("annotations", [])
    record("albero: riquadri di tolleranza geometrica presenti sul foglio", sum(1 for a in anns if a["kind"] == "gtol") >= 2,
           f"{sum(1 for a in anns if a['kind'] == 'gtol')} riquadri")


async def sheet_staffa(c):
    print("\n== Tavola staffa")
    drw, paper, sc, d = await make_drawing(c, "staffa", OUT / "staffa.SLDPRT", ["front", "top", "right", "isometric"])
    # A6: 1:1 non entra in A3 (cartiglio 195x80): prima di scendere a 1:2 si sceglie il formato A2 in scala 1:1
    record("staffa: scala 1:1 (formato A2 scelto da solo, non viste piccole in A3 1:2) (A6)",
           sc >= 1.0 and sc in ISO_SCALES and sorted(paper) == [420.0, 594.0], f"{paper} scala {d.get('scale')}")
    await T(c, "insert_model_dimensions", "staffa: quote importate e disposte", all_views=True, check=lambda d: d.get("arranged"))
    ok, text, lay = await c.call("get_drawing_layout")
    vs = [v for v in lay.get("views", []) if not v["pictorial"]]
    # la vista dall'alto (quella coi fori): ultima ortogonale in ordine di foglio
    topv = vs[1]["name"] if len(vs) > 1 else None
    d = await T(c, "add_hole_table", "tabella fori + etichette", view=topv,
                check=lambda d: d.get("tags_placed") == 8 and d.get("tags_clearance_mm") is not None and d["tags_clearance_mm"] >= 0)
    record("staffa: etichette dei fori fuori dai simboli di foro (distanza >= 0) (A5)", bool(d) and d.get("tags_clearance_mm", -1) >= 0,
           f"{d.get('tags_clearance_mm')} mm")
    ok, text, lay = await c.call("get_drawing_layout")
    rads = [a for a in lay.get("annotations", []) if a["kind"] == "dimension" and a.get("dim_kind") == "rad"]
    record("staffa: richiamo di R10 con meno di 22 mm dentro il contorno (solo il tratto fino al centro; prima 40 mm di richiamo attraversavano il pezzo) (A4)",
           bool(rads) and all(a.get("leader_in_core_mm", 99) <= 22.0 for a in rads),
           str([(a["text"], a.get("leader_in_core_mm")) for a in rads]))
    # A17: quote utili e pulite sulle tre viste (nessun duplicato: lo controlla check_layout), poi GD&T agganciato e rugosita' ISO 1302
    ok, text, lay = await c.call("get_drawing_layout")
    anns = lay.get("annotations", [])
    by_view = {}
    for a in anns:
        if a["kind"] == "dimension" and a.get("dim_kind") == "lin":
            by_view.setdefault(a["view"], []).append((a["axis"], round(a["value"], 2)))
    side, plan, elev = (vs[0]["name"], vs[1]["name"], vs[2]["name"]) if len(vs) >= 3 else (None, None, None)
    vals_side = sorted(v_ for _, v_ in by_view.get(side, []))
    vals_elev = sorted(v_ for _, v_ in by_view.get(elev, []))
    record("staffa A17: vista laterale con altezza totale 40, spessore delle ali 6 (piastra e parete), gambe della nervatura 30",
           vals_side.count(6.0) >= 2 and 40.0 in vals_side and 30.0 in vals_side, str(vals_side))
    record("staffa A17: vista frontale con la nervatura (spessore 5, posizione 22,5, interasse 65)",
           5.0 in vals_elev and 22.5 in vals_elev and 65.0 in vals_elev, str(vals_elev))
    plan_v = sorted(v_ for ax, v_ in by_view.get(plan, []) if ax == "V")
    plan_h = sorted(v_ for ax, v_ in by_view.get(plan, []) if ax == "H")
    record("staffa A17: fori in catena sui due lati: righe 12,5-25-45-25 (a destra) + 120; colonne 24-24-12 (sotto)",
           plan_v == [12.5, 25.0, 25.0, 45.0, 120.0] and plan_h == [12.0, 24.0, 24.0], f"V {plan_v} H {plan_h}")
    d = await T(c, "add_geometric_tolerance", "planarita' 0,05 con freccia sulla faccia superiore della piastra (spigolo visto di taglio)",
                characteristic="flatness", tolerance="0.05", view=elev, model_point=[60, 60, 6],
                check=lambda d: d.get("attached_to") == "edge" and d.get("leaders", 0) >= 1)
    r = await T(c, "add_general_roughness", "Ra 6,3 generale (simbolo + parentesi con simbolo base, ISO 1302)", value="6.3")
    rc = r.get("rects_mm", {})
    cy = r.get("symbol_center_y_mm", 0)
    if rc.get("paren_open") and rc.get("paren_close") and rc.get("basic_symbol"):
        po, pc_, bs = rc["paren_open"], rc["paren_close"], rc["basic_symbol"]
        okc = abs((po[1] + po[3]) / 2 - cy) < 1.5 and abs((pc_[1] + pc_[3]) / 2 - cy) < 1.5             and 0.5 <= bs[0] - po[2] <= 3.5 and 0.5 <= pc_[0] - bs[2] <= 3.5
        record("staffa A17: rugosita' generale: simbolo base centrato fra le parentesi (centri a < 1,5 mm, distanze 0,5-3,5 mm)", okc,
               f"parentesi {po}/{pc_}, simbolo {bs}, centro {cy}")
    else:
        record("staffa A17: rugosita' generale composta", False, str(rc))
    await finish_sheet(c, "staffa", drw)


async def sheet_flangia(c):
    print("\n== Tavola flangia")
    # frontale + isometrica; la vista laterale e' sostituita dalla sezione allineata (come in una vera tavola di flangia)
    drw, paper, sc, d = await make_drawing(c, "flangia", OUT / "flangia.SLDPRT", ["front", "isometric"])
    record("flangia: foglio A4/A3 e scala ISO scelti da soli", paper_ok(paper) and sc in ISO_SCALES, f"{paper} scala {d.get('scale')}")
    ok, text, lay = await c.call("get_drawing_layout")
    vs = [v for v in lay.get("views", []) if not v["pictorial"]]
    front = vs[0]["name"]
    # tabella fori e rugosita' PRIMA delle viste nuove: queste si collocano evitando le annotazioni gia' presenti
    d = await T(c, "add_hole_table", "tabella fori + etichette", view=front,
                check=lambda d: d.get("tags_clearance_mm") is not None and d["tags_clearance_mm"] >= 0)
    await T(c, "add_general_roughness", "Ra 6,3 generale", value="6.3")
    # sezione allineata (poligonale con tratto inclinato) e dettaglio con cerchio visibile sulla vista madre
    d = await T(c, "add_section_view", "sezione allineata A-A (poligonale)", parent_view=front, orientation="aligned",
                points=[0, 60, 0, 0, 46, -33], label="A", check=lambda d: d.get("placed_in_free_space") is not False)
    d2 = await T(c, "add_detail_view", "dettaglio B 2:1 con cerchio sulla madre", parent_view=front, center_x=40, center_y=0,
                 radius=10, label="B", scale="2:1", check=lambda d: d.get("placed_in_free_space") is not False)
    ok, text, lv = await c.call("list_drawing_views")
    names = [v["name"] for v in lv.get("views", [])]
    record("flangia: viste sezione e dettaglio create", any("sezione" in n.lower() or "section" in n.lower() for n in names)
           and any("dettagli" in n.lower() or "detail" in n.lower() for n in names), str(names))
    await T(c, "insert_model_dimensions", "flangia: quote importate e disposte (fronte + sezione)", all_views=True,
            check=lambda d: d.get("arranged"))
    ok, text, lay = await c.call("get_drawing_layout")
    dias = [a for a in lay.get("annotations", []) if a["kind"] == "dimension" and a.get("dim_kind") == "dia" and a.get("value", 0) > 20]
    # i Ø di cerchi concentrici (Ø110, Ø30) hanno richiami distinti (non collineari: non sembrano un'unica linea attraverso il pezzo)
    texts = [(a["text"], a["rect"]) for a in dias]
    record("flangia: Ø110 e Ø30 presenti con richiami su direzioni diverse (A4)", len(dias) >= 2, str([t[0] for t in texts]))
    await finish_sheet(c, "flangia", drw)


async def sheet_perno(c):
    print("\n== Tavola perno piccolo (scala di ingrandimento automatica)")
    drw, paper, sc, d = await make_drawing(c, "perno", OUT / "qual_perno.SLDPRT", ["front", "right", "isometric"])
    record("perno piccolo: scala di ingrandimento (>= 2:1) e foglio A4/A3", paper_ok(paper) and sc >= 2.0 and sc in ISO_SCALES,
           f"{paper} scala {d.get('scale')}")
    await T(c, "insert_model_dimensions", "perno: quote", all_views=True, check=lambda d: d.get("arranged"))
    await finish_sheet(c, "perno", drw, expect_dims=False)


async def sheet_assieme(c):
    print("\n== Tavola d'assieme")
    asm = OUT / "asm_main.SLDASM"
    # A1: linee di esplosione nell'assieme (perno-boccola-foro + una per vite), poi salvataggio: la vista esplosa del disegno le mostra
    await T(c, "open_document", "assieme: apri", filepath=str(asm))
    d = await T(c, "add_explode_lines", "linee di esplosione automatiche (assi comuni)",
                check=lambda d: d["lines"] == 7 and not d["failed"] and d["segments"] >= 7 and d["direction"] == "x")
    names_ = sorted(tuple(g) for g in (d.get("connected") or []))
    record("assieme: 7 linee (perno-boccola-staffa + 6 viti con il loro foro)",
           len(names_) == 7 and any(len(g) == 3 for g in names_) and sum(1 for g in names_ if len(g) == 2 and any("vite" in n for n in g)) == 6,
           str(names_)[:200])
    await T(c, "save_document", "assieme: salva con le linee di esplosione", filepath=str(asm))
    await c.call("close_document", discard=True)
    drw, paper, sc, d = await make_drawing(c, "assieme", asm, ["front", "isometric"], exploded=True)
    record("assieme: foglio e scala ISO scelti da soli", sc in ISO_SCALES, f"{paper} scala {d.get('scale')}")
    ok, _, lv = await c.call("list_drawing_views")
    exp = [v for v in lv.get("views", []) if v.get("exploded")]
    nm = exp[0]["name"] if exp else None
    await T(c, "add_bom", "distinta", view=nm, bom_type="parts_only")
    await T(c, "add_balloons", "palloncini", view=nm)
    # A7: quote d'ingombro nella vista frontale dell'assieme (80 x 80: la piastra)
    await T(c, "insert_model_dimensions", "assieme: quote d'ingombro (larghezza e altezza)", all_views=True,
            check=lambda d: d.get("overall_dims_added", 0) >= 2)
    ok, text, lay = await c.call("get_drawing_layout")
    lins = [a for a in lay.get("annotations", []) if a["kind"] == "dimension" and a.get("dim_kind") == "lin"]
    record("assieme: ingombri 80,00 x 80,00 presenti", len(lins) >= 2 and all(abs(a["value"] - 80.0) < 0.5 for a in lins),
           str([round(a["value"], 2) for a in lins]))
    nb = sum(1 for a in lay.get("annotations", []) if a["kind"] == "balloon")
    record("assieme: palloncini nell'inventario (controllati nelle sovrapposizioni)", nb == 4, f"{nb} palloncini")
    await finish_sheet(c, "assieme", drw, expect_dims=False)


async def sheet_cuneo(c):
    print("\n== Tavola cuneo (quota angolare vera, A10)")
    drw, paper, sc, d = await make_drawing(c, "cuneo", OUT / "cuneo.SLDPRT", ["front", "top", "right", "isometric"])
    await T(c, "insert_model_dimensions", "cuneo: quote importate e disposte", all_views=True, check=lambda d: d.get("arranged"))
    ok, text, lay = await c.call("get_drawing_layout")
    angs = [a for a in lay.get("annotations", []) if a["kind"] == "dimension" and a.get("dim_kind") == "ang"]
    W, H = lay["sheet_mm"]
    okang = len(angs) == 1 and "30" in angs[0]["text"] and all(
        0 < t < W for t in (angs[0]["full_rect"][0], angs[0]["full_rect"][2])) and 0 < angs[0]["full_rect"][1] and angs[0]["full_rect"][3] < H
    record("cuneo: quota angolare 30 gradi ricostruita sugli spigoli (arco nel foglio, testo fuori dalla vista) (A10)", okang,
           str([(a["text"], a["full_rect"]) for a in angs]))
    # A16: vista ausiliaria normale alla faccia inclinata di 30 gradi, senza CreateAuxiliaryViewAt2 (vista nominata + vista del disegno)
    vs_ = [v for v in lay.get("views", []) if not v["pictorial"]]
    if vs_:
        core, scl = vs_[0]["core"], vs_[0]["scale"]
        mx, my = core[0] + 42.45 * scl, core[1] + 30.08 * scl        # punto sulla faccia inclinata (60,20)-(25.09,40) vista di taglio
        d = await T(c, "add_auxiliary_view", "cuneo: vista ausiliaria A normale alla faccia inclinata di 30 gradi", parent_view=vs_[0]["name"],
                    edge_x=mx, edge_y=my,
                    check=lambda d: str(d.get("named_view", "")).startswith("AUX_") and d.get("placed_in_free_space") is True
                    and abs(d.get("edge_direction_deg", 0) - 150.0) < 0.5)
        record("cuneo: nella vista ausiliaria la faccia inclinata e' in VERA GRANDEZZA (normale della faccia // direzione di vista)",
               (d.get("reference_face_true_size_ratio") or 0) > 0.9995 and abs((d.get("reference_face_area_mm2") or 0) - 30 * 40.31) < 1.5,
               f"cos {d.get('reference_face_true_size_ratio')}, area faccia {d.get('reference_face_area_mm2')} mm2 (attesa {30 * 40.31:.1f})")
        record("cuneo: la vista ausiliaria ha freccia con lettera e titolo", bool(d.get("arrow_note", {}).get("arrow")) and bool(d.get("arrow_note", {}).get("title")),
               str(d.get("arrow_note")))
    await finish_sheet(c, "cuneo", drw)


async def sheet_viste_speciali(c):
    """A11 ritaglio rettangolare e poligonale, A12 vista interrotta, A13 inversione della sezione: tutto sull'albero, 1:2."""
    print("\n== Viste speciali: ritaglio, interruzione, sezione invertita")
    drw, paper, sc, d = await make_drawing(c, "speciali", OUT / "albero.SLDPRT", ["front", "top"], scale="1:2", paper="A3")
    ok, text, lay = await c.call("get_drawing_layout")
    vs = [v for v in lay.get("views", []) if not v["pictorial"]]
    front, top = vs[0]["name"], vs[1]["name"]
    # A13: due sezioni della vista dall'alto, normale e invertita: la matrice della vista cambia e le frecce si girano
    a = await T(c, "add_section_view", "sezione A-A normale", parent_view=top, orientation="horizontal", offset=0, label="A", flip=False,
                check=lambda d: d.get("reversed_cut_direction") in (None, False))
    b = await T(c, "add_section_view", "sezione B-B invertita (flip)", parent_view=top, orientation="horizontal", offset=0, label="B",
                flip=True, check=lambda d: d.get("reversed_cut_direction") is True)
    ra, rb = a.get("view_rotation"), b.get("view_rotation")
    record("sezione invertita: la matrice di vista e' diversa da quella della sezione normale (A13)",
           bool(ra) and bool(rb) and any(abs(x - y) > 0.5 for x, y in zip(ra, rb)), f"{ra} / {rb}")
    # A11: ritaglio rettangolare e poligonale
    r1 = await T(c, "add_crop_view", "ritaglio rettangolare (50 x 35) della vista dall'alto", parent_view=top, shape="rectangle",
                 center_x=15, center_y=0, width=50, height=35, check=lambda d: d.get("cropped") is True and d.get("shape") == "rectangle")
    r2 = await T(c, "add_crop_view", "ritaglio poligonale (trapezio) della vista frontale", parent_view=front, shape="polygon",
                 points=[-60, 10, 20, 10, 60, -10, -60, -10], check=lambda d: d.get("cropped") is True and d.get("shape") == "polygon")
    # A12: vista interrotta con linee curve (ISO) su una copia della vista frontale
    v3 = await T(c, "add_model_view", "copia della vista frontale per l'interruzione", orientation="front", scale="1:2",
                 check=lambda d: True)
    nm = v3.get("name")
    r3 = await T(c, "add_break_view", "vista interrotta (linee curve, 20 mm)", parent_view=nm, orientation="vertical", position1=-10,
                 position2=10, style=3, check=lambda d: d.get("shortened_mm", 0) > 5.0)
    record("vista interrotta: la vista si accorcia davvero (A12)", r3.get("shortened_mm", 0) > 5.0, f"-{r3.get('shortened_mm')} mm")
    png = OUT / "qual_speciali.png"
    if png.exists():
        png.unlink()
    await T(c, "export_drawing", "speciali: PNG", filepath=str(png), format="png")
    PNGS.append(str(png))
    await c.call("save_drawing", filepath=str(drw))
    await c.call("close_document", discard=True)


async def sheet_verticale(c):
    print("\n== Foglio A3 verticale con cornice e cartiglio ISO (A14) e nome lungo (A8)")
    tag = "verticale_nome_molto_lungo_della_tavola_staffa"      # 43 caratteri nel N. DISEGNO (A8)
    drw = OUT / f"qual_{tag}.SLDDRW"
    if drw.exists():
        drw.unlink()
    d = await T(c, "create_drawing", "A3 verticale", model_path=str(OUT / "staffa.SLDPRT"), paper_size="A3", orientation="portrait",
                save_as=str(drw), add_views=False, save_model=False,
                check=lambda d: d.get("sheet_format") == "a3 - iso portrait.slddrt" and abs(d["width_mm"] - 297) < 0.5
                and abs(d["height_mm"] - 420) < 0.5)
    tn = d.get("title_number") or {}
    record("N. DISEGNO lungo: carattere ridotto, sta nella cella (A8)", tn.get("fits") is True and 0 < tn.get("height_mm", 9) < 6.0,
           str(tn))
    await T(c, "add_standard_views", "staffa nel foglio verticale", views=["front", "top", "right", "isometric"],
            check=lambda d: d.get("layout_fits") is True and d["scale"] in ("1:1", "2:1", "1:2"))
    await T(c, "insert_model_dimensions", "quote", all_views=True, check=lambda d: d.get("arranged"))
    png = OUT / "qual_verticale.png"
    if png.exists():
        png.unlink()
    await T(c, "export_drawing", "verticale: PNG", filepath=str(png), format="png")
    PNGS.append(str(png))
    ok, text, lay = await c.call("get_drawing_layout")
    W, H = lay["sheet_mm"]
    record("foglio verticale A3 297 x 420 con cartiglio in basso a destra", abs(W - 297) < 0.5 and abs(H - 420) < 0.5, str(lay["sheet_mm"]))
    if ok:
        check_layout("verticale", lay)
    # il cartiglio non deve avere "ERRORE:..." (proprieta' mancanti) e deve riportare nome file e scala: dal DXF
    dxf = OUT / "qual_verticale.dxf"
    if dxf.exists():
        dxf.unlink()
    okx, _, _ = await c.call("export_drawing", filepath=str(dxf), format="dxf")
    txt = dxf.read_text(encoding="latin-1", errors="ignore") if dxf.exists() else ""
    record("formato verticale: nessun 'ERRORE:' nel cartiglio (DXF)", okx and "ERRORE" not in txt and "SCALA" in txt and "TITOLO" in txt,
           f"{len(txt)} byte")
    record("formato verticale: cartiglio con ISO 'FORMATO' e 'PESO' e nome file nel DXF", "FORMATO" in txt and "PESO" in txt and "verticale_nome" in txt)
    await c.call("save_drawing", filepath=str(drw))
    await c.call("close_document", discard=True)


async def sheet_layout(c):
    print("\n== Layout: senza isometrica nell'angolo e foglio pieno -> nuovo foglio (A15)")
    drw, paper, sc, d = await make_drawing(c, "layout", OUT / "albero.SLDPRT", ["front", "top"], scale="1:1", paper="A3")
    record("layout senza isometrica: nessuna vista pittorica e layout valido", d.get("layout_fits") is True
           and all(not v["orientation"] in ("isometric",) for v in d.get("views", [])), f"{d.get('scale')} {paper}")
    # l'isometrica si aggiunge dopo, nel posto libero piu' vicino (non nell'angolo presupposto)
    v = await T(c, "add_model_view", "isometrica aggiunta dopo, dove c'e' posto", orientation="isometric", scale="1:2",
                check=lambda d: d.get("new_sheet") is None)
    ok, text, lay = await c.call("get_drawing_layout")
    if ok:
        check_layout("layout", lay)
    await c.call("save_drawing", filepath=str(drw))
    await c.call("close_document", discard=True)
    # foglio pieno: si aggiungono viste 1:1 su un A4 fino a quando non c'e' piu' posto
    drw2 = OUT / "qual_pieno.SLDDRW"
    if drw2.exists():
        drw2.unlink()
    await T(c, "create_drawing", "A4 per il test del foglio pieno", model_path=str(OUT / "albero.SLDPRT"), paper_size="A4",
            save_as=str(drw2), add_views=False, save_model=False)
    newsheet = None
    for k in range(8):
        ok, text, dd = await c.call("add_model_view", orientation="front", scale="1:1")
        if ok and dd.get("new_sheet"):
            newsheet = dd["new_sheet"]
            break
    ok, text, sh = await c.call("list_sheets")
    record("foglio pieno: la vista che non entra va su un NUOVO foglio dello stesso formato", bool(newsheet) and len(sh.get("sheets", [])) == 2,
           f"{newsheet} {[s_['name'] for s_ in sh.get('sheets', [])]}")
    await c.call("save_drawing", filepath=str(drw2))
    await c.call("close_document", discard=True)


# ------------------------------------------------------------------------------------------ avvio
async def scenario(c):
    """QUAL_ONLY=staffa,cuneo limita le tavole (solo per lo sviluppo; le regressioni girano tutte)."""
    await ensure_parts(c)
    only = [x for x in os.environ.get("QUAL_ONLY", "").split(",") if x]
    for name, fn in (("albero", sheet_albero), ("staffa", sheet_staffa), ("flangia", sheet_flangia), ("perno", sheet_perno),
                     ("assieme", sheet_assieme), ("cuneo", sheet_cuneo), ("speciali", sheet_viste_speciali),
                     ("verticale", sheet_verticale), ("layout", sheet_layout)):
        if not only or name in only:
            await fn(c)


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
                need = ["arrange_drawing_dimensions", "get_drawing_layout", "set_dimension_tolerance", "add_hole_table",
                        "add_general_roughness", "add_explode_lines"]
                record("nuovi tool di tavola esposti", all(n in tools for n in need), f"{len(tools)} tool totali")
                await scenario(c)
    finally:
        cleanup(my_pid, elia_pids)
    return True


def cleanup(my_pid, elia_pids):
    import time
    if my_pid and my_pid in sw_pids():
        subprocess.run(["taskkill", "/PID", str(my_pid), "/F"], capture_output=True)
    time.sleep(3)
    left = sw_pids() - elia_pids
    print(f"Processi SolidWorks orfani dopo il test: {sorted(left)}; istanza utente intatta: {elia_pids <= sw_pids()}")


if __name__ == "__main__":
    started = asyncio.run(run())
    npass = sum(1 for r in RESULTS if r[1] == "PASS")
    print("\n" + "=" * 70)
    for name, res, note in RESULTS:
        if res == "FAIL":
            print(f"FAIL  {name}  {note}"[:260])
    print(f"RIEPILOGO: {npass}/{len(RESULTS)} PASS")
    print("PNG da guardare:")
    for p in PNGS:
        print("  ", p)
    print("PASS" if started and npass == len(RESULTS) else "FAIL")
    sys.exit(0 if started and npass == len(RESULTS) else 1)
