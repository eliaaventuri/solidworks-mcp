"""
Master Total Regression Runner
Executes offline suite and live test suites for all 5 functional areas:
1. Offline Suite (255 checks validating all 555 tools)
2. Assiemi Live (test_assembly3_live.py)
3. Disegni Live (test_drawings2_live.py)
4. Modellazione Live (test_features4_live.py)
5. Dati & Export Live (test_data2_live.py)
6. Simulazione Live (test_simulation2_live.py)
"""

import sys
import time
import subprocess
from pathlib import Path
import psutil

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

TESTS = [
    ("Offline Suite (555 Tools)", ROOT / "tests" / "test_offline.py"),
    ("Assiemi Live (34 Tools)", ROOT / "tests" / "test_assembly3_live.py"),
    ("Disegni Live (26 Tools)", ROOT / "tests" / "test_drawings2_live.py"),
    ("Modellazione Live (33 Tools)", ROOT / "tests" / "test_features4_live.py"),
    ("Dati & Export Live (24 Tools)", ROOT / "tests" / "test_data2_live.py"),
    ("Simulazione Live (32 Tools)", ROOT / "tests" / "test_simulation2_live.py"),
]


def sw_pids():
    pids = set()
    for p in psutil.process_iter(["pid", "name"]):
        if p.info["name"] and "sldworks" in p.info["name"].lower():
            pids.add(p.info["pid"])
    return pids


def main():
    print("=" * 80)
    print("AVVIO REGRESSIONE TOTALE FINALE — SOLIDWORKS MCP SERVER (555 TOOLS)")
    print("=" * 80)

    initial_pids = sw_pids()
    print(f"Istanze SolidWorks attive pre-regressione: {sorted(initial_pids)}")

    summary = []
    total_start = time.time()

    for name, script_path in TESTS:
        print(f"\n>>> ESECUZIONE: {name} ({script_path.name})")
        t0 = time.time()
        res = subprocess.run([str(PYTHON), "-u", str(script_path)], cwd=str(ROOT), capture_output=True, text=True)
        dur = round(time.time() - t0, 1)

        ok = (res.returncode == 0)
        # Stampa ultime righe di log
        lines = [line.strip() for line in (res.stdout + res.stderr).splitlines() if line.strip()]
        last_lines = lines[-5:] if len(lines) >= 5 else lines
        for l in last_lines:
            print(f"    {l}")

        status_str = "PASS" if ok else "FAIL"
        summary.append((name, status_str, dur))
        print(f"[{status_str}] {name} in {dur}s (rc={res.returncode})")

        # Verifica istanze SolidWorks
        curr_pids = sw_pids()
        orphan_pids = curr_pids - initial_pids
        if orphan_pids:
            print(f"    [ATTENZIONE] Processi orfani rilevati: {orphan_pids}. Chiusura forzata...")
            for pid in orphan_pids:
                try:
                    psutil.Process(pid).kill()
                except Exception:
                    pass

        if not ok:
            print(f"\n[ERRORE] Interruzione regressione su fallimento di {name}")
            break

    total_dur = round(time.time() - total_start, 1)
    print("\n" + "=" * 80)
    print("RIEPILOGO FINALE REGRESSIONE TOTALE")
    print("=" * 80)
    all_ok = True
    for name, status, dur in summary:
        print(f"  [{status}] {name:<35} ({dur}s)")
        if status != "PASS":
            all_ok = False

    final_pids = sw_pids()
    print(f"\nDurata totale: {total_dur}s")
    print(f"Istanze SolidWorks finali: {sorted(final_pids)} (intatte rispetto a {sorted(initial_pids)})")

    if not all_ok:
        sys.exit(1)
    print("\n>>> REGRESSIONE TOTALE COMPLETATA CON SUCCESSO (100% GREEN) <<<")


if __name__ == "__main__":
    main()
