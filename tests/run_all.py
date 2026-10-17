"""
Regressione completa: esegue i test uno alla volta e scrive un riepilogo.

Ogni test live avvia la PROPRIA istanza dedicata e nascosta di SolidWorks e alla fine chiude solo quella.
Questo script non chiude mai processi: controlla soltanto che dopo ogni test non restino processi SolidWorks in piu'
rispetto a quelli presenti all'inizio (le istanze di Elia) e lo segnala.

Uso (su Windows con SolidWorks):
    .venv\\Scripts\\python.exe tests\\run_all.py                 tutti i test, nell'ordine di ORDER
    .venv\\Scripts\\python.exe tests\\run_all.py data simulation solo quelli indicati (nome senza test_ e _live)
    .venv\\Scripts\\python.exe tests\\run_all.py --stop          si ferma al primo test rosso
    .venv\\Scripts\\python.exe tests\\run_all.py --offline       solo test_offline (anche su Linux/macOS)
Riepilogo: test_output/regressione_<data-ora>.md; log di ogni test in test_output/run_<nome>.log, scritto mentre il test gira.
"""

import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
OUT = ROOT / "test_output"

# ordine della regressione: prima il test senza SolidWorks, poi dai tool base alle aree che li usano
ORDER = ["offline", "modeling", "modeling_extra", "drawings", "drawing_quality", "assembly", "assembly_extra", "data", "data_extra", "simulation",
         "timeout"]
PASS_RE = re.compile(r"(\d+)/(\d+) PASS")


def test_file(name):
    return TESTS / ("test_offline.py" if name == "offline" else f"test_{name}_live.py")


def python_exe():
    venv = ROOT / ".venv" / "Scripts" / "python.exe"
    return str(venv) if venv.exists() else sys.executable


def sw_pids():
    if os.name != "nt":
        return set()
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq SLDWORKS.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    pids = set()
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) > 1 and parts[0].strip('"').lower() == "sldworks.exe":
            pids.add(int(parts[1]))
    return pids


def stop_dev_worker():
    """Il worker di sviluppo (scripts_tmp/, non versionato) va fermato prima delle regressioni."""
    cmd = ROOT / "scripts_tmp" / "cmd"
    if cmd.is_dir():
        (cmd / "QUIT").write_text("regressione\n")
        time.sleep(5)
        return True
    return False


def parse_summary(text):
    """(passati, totale) dall'ultima riga 'N/M PASS' dell'output, oppure None."""
    found = PASS_RE.findall(text)
    return (int(found[-1][0]), int(found[-1][1])) if found else None


def fail_lines(text, limit=15):
    lines = [ln.strip() for ln in text.splitlines() if re.match(r"\s*(\[FAIL\]|FAIL\b)", ln)]
    seen, out = set(), []
    for ln in lines:
        if ln not in seen:
            seen.add(ln)
            out.append(ln[:220])
    return out[:limit]


def run_one(name, log_dir):
    path = test_file(name)
    if not path.exists():
        return {"name": name, "status": "MANCANTE", "seconds": 0, "summary": None, "fails": [], "code": None}
    t0 = time.time()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    log = log_dir / f"run_{name}.log"            # scritto mentre il test gira: si puo' seguire con  Get-Content -Wait
    with open(log, "w", encoding="utf-8", errors="replace") as f:
        proc = subprocess.run([python_exe(), "-u", str(path)], cwd=str(ROOT), env=env, stdout=f, stderr=subprocess.STDOUT)
    text = log.read_text(encoding="utf-8", errors="replace")
    summary = parse_summary(text)
    ok = proc.returncode == 0 and summary is not None and summary[0] == summary[1]
    return {"name": name, "status": "PASS" if ok else "FAIL", "seconds": round(time.time() - t0), "summary": summary,
            "fails": fail_lines(text), "code": proc.returncode}


def report(results, baseline, orphans_by_test, started):
    lines = [f"# Regressione {started:%Y-%m-%d %H:%M}", "",
             f"Processi SolidWorks presenti all'inizio (non toccati): {sorted(baseline) or 'nessuno'}", "",
             "| Test | Esito | Controlli | Tempo | Processi rimasti |", "|---|---|---|---|---|"]
    for r in results:
        s = f"{r['summary'][0]}/{r['summary'][1]}" if r["summary"] else "-"
        orphans = orphans_by_test.get(r["name"]) or []
        lines.append(f"| {test_file(r['name']).name} | {r['status']} | {s} | {r['seconds']} s | {orphans or 0} |")
    for r in results:
        if r["fails"] or (r["status"] != "PASS" and r["code"] not in (0, None)):
            lines += ["", f"## {test_file(r['name']).name}: {r['status']} (codice di uscita {r['code']})"]
            lines += [f"- {f}" for f in r["fails"]] or ["- nessuna riga FAIL: vedere il log (eccezione o test interrotto)"]
            lines.append(f"- log completo: test_output/run_{r['name']}.log")
    if any(r["name"] == "drawing_quality" for r in results):
        lines += ["", "Tavole da guardare anche a occhio: test_output/qual_*.png"]
    ok = all(r["status"] == "PASS" for r in results) and not any(orphans_by_test.values())
    lines += ["", "**TUTTO VERDE**" if ok else "**ROSSO: correggere prima di andare avanti**"]
    return "\n".join(lines) + "\n", ok


def main(argv):
    stop = "--stop" in argv
    names = [a for a in argv if not a.startswith("--")]
    if "--offline" in argv:
        names = ["offline"]
    names = names or ORDER
    unknown = [n for n in names if n not in ORDER]
    if unknown:
        print(f"Test sconosciuti: {unknown}. Disponibili: {ORDER}")
        return 2
    if os.name != "nt" and any(n != "offline" for n in names):
        print("I test live richiedono Windows con SolidWorks: qui si puo' eseguire solo --offline.")
        return 2
    OUT.mkdir(exist_ok=True)
    started = datetime.now()
    if any(n != "offline" for n in names) and stop_dev_worker():
        print("Worker di sviluppo fermato (scripts_tmp/cmd/QUIT).")
    baseline = sw_pids()
    results, orphans_by_test = [], {}
    for n in names:
        print(f"== {test_file(n).name} ...", flush=True)
        r = run_one(n, OUT)
        left = sorted(sw_pids() - baseline)
        if left:
            orphans_by_test[n] = left
        s = f"{r['summary'][0]}/{r['summary'][1]}" if r["summary"] else "nessun riepilogo"
        print(f"   {r['status']}  {s}  {r['seconds']} s" + (f"  PROCESSI RIMASTI {left}" if left else ""), flush=True)
        results.append(r)
        if stop and r["status"] != "PASS":
            print("   --stop: interrotto al primo rosso")
            break
    text, ok = report(results, baseline, orphans_by_test, started)
    path = OUT / f"regressione_{started:%Y%m%d_%H%M}.md"
    path.write_text(text, encoding="utf-8")
    print("\n" + text + f"\nRiepilogo salvato in {path}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
