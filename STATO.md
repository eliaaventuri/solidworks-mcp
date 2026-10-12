# STATO — SolidWorks MCP

Ultimo aggiornamento: 2026-10-12. Dettagli, misure, trappole API e cronologia completa: `STATO_STORICO.md`.
Elenco dei limiti da risolvere: `LIMITI.md`. Piano dei prossimi gruppi: `PIANO_D_E.md`. Mappa dei file: `ATLANTE.md`.

## Ambiente di sviluppo
- Windows 11 **ARM64**, SolidWorks 2026 SP4.1 Student, interfaccia **italiana** (API 34.4.1).
- Python 3.12 **x64** (emulato) in `.venv` (Python ARM64 non va: `cryptography` non ha wheel win-arm64).
- Dipendenze: `mcp` 1.x (`mcp<2`: la 2.x ha tolto `@server.list_tools()`), `pywin32`, `python-dotenv`.
- Server registrato come `solidworks` in `~/.claude.json` e in `%APPDATA%\Claude\claude_desktop_config.json`.

## Cosa c'e'
196 tool MCP: 25 base, 50 modellazione, 38 disegni, 35 assiemi, 30 dati/export, 18 simulazione statica.

| Area | Stato | Test live (ultima regressione, 2026-10-11) |
|---|---|---|
| Modellazione 3D (blocco 1, gruppo B) | completa; Hole Wizard senza UNI (B4 `[~]`) | `test_modeling_live` 175/175, `test_modeling_extra_live` 240/240 |
| Disegni (blocco 4, gruppo A) | completi, tavole presentabili | `test_drawings_live` 65/65, `test_drawing_quality_live` 139/139 |
| Assiemi (blocco 2, gruppo C) | completi; C3, C5 `[~]` | `test_assembly_live` 113/113, `test_assembly_extra_live` 213/213 |
| Dati ed export (blocco 3) | funzionanti; gruppo D da fare | `test_data_live` 159/159 |
| Simulazione (blocco 5) | solo statica lineare; gruppo E da fare | `test_simulation_live` 120/120 |
| Senza SolidWorks | registro tool, sicurezza, PNG, lettori export, `.sldmat` | `test_offline` 36/36 (2026-10-12, Linux) |

## Regole di lavoro
- I test live girano SOLO su un'istanza dedicata e nascosta (`SW_MCP_INSTANCE=dedicated`): l'istanza di SolidWorks di Elia non
  va mai toccata; alla fine si chiude solo il PID lanciato dal test (0 processi orfani).
- Il worker di sviluppo (`scripts_tmp/`, non versionato) va fermato (file `scripts_tmp/cmd/QUIT`) prima delle regressioni.
- Le opzioni di export sono preferenze utente GLOBALI di SolidWorks: salvarle e ripristinarle sempre.
- Ogni voce di `LIMITI.md` si chiude con un numero misurato dal test (le tavole si guardano ANCHE a occhio).
- Prima di cercare un'API, leggere le trappole gia' note in `STATO_STORICO.md` e nei docstring dei moduli `automation/`.

## Aperto
- **Gruppo D** (dati ed export) e **gruppo E** (simulazione): tutto da fare, piano in `PIANO_D_E.md`.
- Parziali: B4 (UNI assente dal database; posizione angolare dei fori su facce cilindriche non controllabile), C3 (rotazione nei
  passi di traslazione dell'esploso), C5 (blocco/ingranaggio/vite non propagati dal solutore via API).
- Residuo visivo non bloccante: nella tavola del cuneo la vista ausiliaria non sta sulla perpendicolare allo spigolo.
- Preferenze di SolidWorks cambiate durante lo sviluppo di cui non si conosce il valore originale: qualita' STL (int 78 = 2 fine)
  e tipo di import STL (int 208 = 2 solido). Controllare in Opzioni > Esporta/Importa se si notano differenze.
- `_dx_inspect_step` ha due contatori nuovi (struttura d'assieme) non ancora provati su uno STEP scritto da SolidWorks:
  rieseguire `test_data_live.py`.
- Codice vecchio dell'autore originale (`backup_*`, `scripts/`, `solidworks_com.py`, `solidworks_simulation.py`): solo nella
  copia locale, non nel repository (F3).

## Prossimo passo
Sul PC con SolidWorks: `python tests/test_offline.py`, poi `test_data_live.py`, poi il gruppo D nell'ordine di `PIANO_D_E.md`
(D5, D6, D7, D8, D1 per primi).
