# STATO — SolidWorks MCP

Ultimo aggiornamento: 2026-10-17. Dettagli, misure, trappole API e cronologia completa: `STATO_STORICO.md`.
Elenco dei limiti da risolvere: `LIMITI.md`. Piano dei prossimi gruppi: `PIANO_D_E.md`. Mappa dei file: `ATLANTE.md`.

## Ambiente di sviluppo
- Windows 11 **ARM64**, SolidWorks 2026 SP4.1 Student, interfaccia **italiana** (API 34.4.1).
- Python 3.12 **x64** (emulato) in `.venv` (Python ARM64 non va: `cryptography` non ha wheel win-arm64).
- Dipendenze: `mcp` 1.x (`mcp<2`: la 2.x ha tolto `@server.list_tools()`), `pywin32`, `python-dotenv`.
- Server registrato come `solidworks` in `~/.claude.json` e in `%APPDATA%\Claude\claude_desktop_config.json`.

## Cosa c'e'
196 tool MCP: 25 base, 50 modellazione, 38 disegni, 35 assiemi, 30 dati/export, 18 simulazione statica.

| Area | Stato | Test live (ultima regressione, 2026-10-17) |
|---|---|---|
| Modellazione 3D (blocco 1, gruppo B) | completa (UNI assente dal database di SolidWorks) | `test_modeling_live` 175/175, `test_modeling_extra_live` 259/259 |
| Disegni (blocco 4, gruppo A) | completi, tavole presentabili | `test_drawings_live` 65/65, `test_drawing_quality_live` 139/139 |
| Assiemi (blocco 2, gruppo C) | completi; C3 `[~]` | `test_assembly_live` 113/113, `test_assembly_extra_live` 214/214 |
| Dati ed export (blocco 3) | funzionanti; gruppo D da fare | `test_data_live` 159/159 |
| Simulazione (blocco 5) | solo statica lineare; gruppo E da fare | `test_simulation_live` 120/120 |
| Senza SolidWorks | registro e smistamento dei tool, sicurezza, PNG, lettori export, `.sldmat`, configurazione | `test_offline` 83/83 (2026-10-17; anche su GitHub Actions) |

## Regole di lavoro
- I test live girano SOLO su un'istanza dedicata e nascosta (`SW_MCP_INSTANCE=dedicated`): l'istanza di SolidWorks di Elia non
  va mai toccata; alla fine si chiude solo il PID lanciato dal test (0 processi orfani).
- Il worker di sviluppo (`scripts_tmp/`, non versionato) va fermato (file `scripts_tmp/cmd/QUIT`) prima delle regressioni.
- Le opzioni di export sono preferenze utente GLOBALI di SolidWorks: salvarle e ripristinarle sempre.
- Ogni voce di `LIMITI.md` si chiude con un numero misurato dal test (le tavole si guardano ANCHE a occhio).
- Prima di cercare un'API, leggere le trappole gia' note in `STATO_STORICO.md` e nei docstring dei moduli `automation/`.

## Aperto
- **Gruppo D** (dati ed export) e **gruppo E** (simulazione): tutto da fare, piano in `PIANO_D_E.md`.
- Parziale: C3 (rotazione nei passi di traslazione dell'esploso: solo attorno alla direzione radiale, con un passo radiale di distanza 0).
- Residuo visivo non bloccante: nella tavola del cuneo la vista ausiliaria non sta sulla perpendicolare allo spigolo.
- Preferenze di SolidWorks cambiate durante lo sviluppo di cui non si conosce il valore originale: qualita' STL (int 78 = 2 fine)
  e tipo di import STL (int 208 = 2 solido). Controllare in Opzioni > Esporta/Importa se si notano differenze.
- `_dx_inspect_step` ha due contatori nuovi (struttura d'assieme) non ancora provati su uno STEP scritto da SolidWorks:
  rieseguire `test_data_live.py`.
- Preferenze anti-finestre di dialogo (toggle 10, 96, 100, 101): fino al 2026-10-12 restavano cambiate per sempre (anche sull'istanza
  di Elia). CORRETTO nel codice il 2026-10-13, da verificare (piano, fase 0): impostate all'inizio di ogni tool e rimesse ai valori
  originali alla fine. Se in SolidWorks le quote non chiedono piu' il valore, rimettere a mano l'opzione una volta (Opzioni > Generale).
- Codice vecchio dell'autore originale (`backup_*`, `scripts/`, `solidworks_com.py`, `solidworks_simulation.py`): solo nella
  copia locale, non nel repository (F3).

## Ultime modifiche non ancora provate dal vivo (2026-10-12)
- `server.py`: la catena di `elif` dei 25 tool base e' diventata una tabella (`BASE_DISPATCH` + `SPECIAL_HANDLERS`); stessi metodi e
  stessi default (verificato offline con un SolidWorks finto).
- `config.json` ridotto alle chiavi lette davvero; chiavi sconosciute in una config locale vengono ignorate (prima facevano perdere tutta la config).
- Test live: percorsi, `Client`, `sw_pids`, `cleanup` spostati in `tests/live_common.py` (solo le copie identiche;
  `test_modeling_extra_live` usa `Client(session, auto_overwrite=False)` come prima).
- Versione del pacchetto 5.0.0.
- Parti pure del gruppo D in `solidworks_mcp/utils/` (D1 tabella configurazioni, D7 inerzia in sistema utente, D10 lettura PDF 3D),
  coperte dal test offline; D10 e' gia' usato da `inspect_export_file` (chiave `pdf3d`, `has_3d` invariato).
- Revisione del codice (`data_export.py`, `drawings.py`):
  - `get_part_mass_properties`, `list_part_configurations(include_volume)`, `set_configuration_suppression`, `export_model`:
    la configurazione attiva di partenza torna attiva anche se c'e' un errore a meta' (prima restava cambiata);
  - `configuration=` con un nome inesistente ora da' errore (prima `ShowConfiguration2` falliva in silenzio e si lavorava
    sulla configurazione attiva: export e proprieta' di massa della configurazione sbagliata con esito positivo);
  - `export_model` con `configuration=`: il box del modello per il controllo dell'STL ora e' quello della configurazione esportata
    (prima era quello della configurazione di partenza);
  - `export_model` / `export_drawing`: se il nome del file viene cambiato (`.iges` -> `.igs`, `format` diverso dall'estensione)
    e il file col nome nuovo esiste, rifiuto (prima veniva cancellato e riscritto senza `overwrite`);
  - `tests/test_data_live.py`: refuso `dx_a` -> `dx_b` nella pulizia prima degli export IGES/x_t/x_b/PDF/eDrawings.
- 2026-10-13:
  - preferenze anti-finestre impostate all'inizio di ogni tool e ripristinate alla fine (`server.call_tool`, `_restore_prefs`);
  - all'uscita del server (client disconnesso) l'istanza dedicata viene chiusa, solo se non ci sono documenti non salvati;
  - `simulation.py`: lo schizzo temporaneo per il sistema di riferimento delle forze era cancellato come "ultimo schizzo dell'albero"
    (poteva essere uno schizzo dell'utente): ora si cancella solo quello appena creato, dopo aver chiuso uno schizzo eventualmente aperto;
  - `modeling.py` (`_seed_effect`, controllo delle ripetizioni): le feature soppresse per la misura tornano attive anche in caso di errore.

## Lingua inglese (G1, 2026-10-12; provato dal vivo il 2026-10-17, vedi Fase 1)
Il server non usa piu' nomi italiani fissi (dettagli in `LIMITI.md`, G1, e in `solidworks_mcp/utils/sw_lang.py`); `connect_solidworks`
riporta `ui_language`. Le scritte che il server mette sulle tavole (cartiglio dei formati verticali, "VISTA A", nota degli smussi) sono in
italiano con SolidWorks italiano e in inglese altrimenti; i formati verticali inglesi si generano come `formats/a3 - iso portrait en.slddrt`.
Come provarlo sul PC: in SolidWorks Strumenti > Opzioni > Generale attivare "Usa lingua inglese" e anche l'opzione dei nomi di feature
e file in inglese (i nomi delle opzioni sono da controllare; serve riavviare SolidWorks), poi `tests\run_all.py`: i test traducono da soli
i nomi italiani (`tests/live_common.py`, tabella `_IT_EN`). Un rosso dovuto a un nome inglese diverso si corregge in quella tabella o in
`sw_lang.py`. Alla fine rimettere le opzioni in italiano. Le preferenze sono globali: farlo quando non si lavora a mano.

## Fase 0 (2026-10-16, PC, italiano)
Regressione completa `tests\run_all.py`, exit 0, tutto verde (riepilogo `test_output/regressione_20261016_1020.md`):
modeling 175/175, modeling_extra 240/240, drawings 65/65, drawing_quality 139/139, assembly 113/113,
assembly_extra 213/213, data 159/159, simulation 120/120; offline 83/83. Stessi numeri del 2026-10-11.
Controlli a mano confermati da Elia (2026-10-16): tavole a occhio, quota in Opzioni > Generale, chiusura dell'istanza
nascosta all'uscita di Claude Desktop.

## Fase 1 (2026-10-16/17, PC, inglese) — CHIUSA
SolidWorks messo in inglese via API (`scripts_tmp/lingua.py en|it|leggi`, toggle 83 e 262, originali False) e poi rimesso in italiano
(verificato: `italian`, 83 e 262 False). Regressione in inglese verde: modeling 175/175, modeling_extra 240/240, drawings 65/65,
drawing_quality 139/139, assembly 113/113, assembly_extra 213/213, data 159/159, simulation 120/120, offline 83/83.
Rossi trovati e corretti: nota "smussi non quotati" sovrapposta a una quota (server: ora misurata con `GetExtent`), e nei test nomi
italiani (formato verticale `... en.slddrt`, SIZE/WEIGHT, colonne della distinta, materiali Steel/Plastics/ABS/Bronze, CirPattern, titolo
dell'assieme). Conferma in italiano dopo le correzioni (`regressione_20261017_1242.md`): drawings 65/65, drawing_quality 139/139,
assembly 113/113, data 159/159. G1 `[x]`. Dettagli in `STATO_STORICO.md`.
Da guardare a occhio (Elia): `test_output/qual_*.png` dopo la conferma in italiano.

## Fase 2 (2026-10-17, PC, italiano) — CHIUSA
- **B4 `[x]`** (fori su facce cilindriche): pick passato come g = F^T R^T p (dettagli e trappola in `STATO_STORICO.md`). Test B4 70/70:
  asse del foro per l'asse del cilindro (0,00e+00 mm), volume 0,023 % dall'integrale.
- **C5 `[x]`** (ingranaggio, vite, blocco): rotazione pilotata con un accoppiamento d'angolo temporaneo; corretto `RevolutionType` della vite.
  Test C5 82/82: B/A = -2,0000, vite 0,5000 mm per 90 gradi, blocco fermo sotto un angolo imposto.
- **C3 resta `[~]`**: `RotationAngle` non scrivibile; un passo radiale con distanza 0 ruota di 45,0000 gradi ma solo attorno alla direzione
  radiale (il `rotation_note` del tool ora lo suggerisce). Prove in `scripts_tmp/c3p1..4.py`.
- Regressione completa `testsun_all.py`, exit 0, tutto verde (`test_output/regressione_20261017_1604.md`, log `%TEMP%egr_f2.log`):
  offline 83/83, modeling 175/175, modeling_extra 259/259, drawings 65/65, drawing_quality 139/139, assembly 113/113,
  assembly_extra 214/214, data 159/159, simulation 120/120. 0 processi SolidWorks rimasti.

## Fase 5 (2026-10-17, parziale, offline) — IN CORSO
- **5.7 `execute_python`**: disattivato di default; si attiva con `SW_MCP_ALLOW_PYTHON=1` (letto a ogni chiamata). Non esposto nell'elenco
  e rifiutato con messaggio che spiega come attivarlo. I test live lo attivano da soli (`tests/live_common.py`), quindi contano 196 tool.
  Offline: 195 tool di default. Confermato da Elia (2026-10-17): resta disattivato di default.
- **5.5 `SW_MCP_TOOLSETS`**: gruppi `base` (sempre attivo), `modeling`, `drawings`, `assembly`, `data`, `simulation`; default tutti.
  Un tool di un gruppo non scelto risponde con errore che nomina il gruppo da aggiungere.
- **5.9 log**: in `%LOCALAPPDATA%\solidworks-mcp\` con rotazione (5 file da 5 MB). `log_file` in config.json puo' essere un percorso assoluto.
  Il vecchio `solidworks_mcp.log` nella cartella del pacchetto non viene piu' scritto (si puo' cancellare).
- **5.8 pyflakes**: tolti 46 import non usati e 1 f-string senza segnaposto nel pacchetto (verificato a mano: `git diff --stat`, py_compile).
  Poi le 21 variabili "assegnata ma mai usata" sono sparite (9 file; 13 chiamate COM tenute come espressione nuda, 4 pure ancora
  da togliere, `assembly.py` `comp, _ =`). Restano nel pacchetto solo 5 import di `win32com.client`/`pythoncom` (side-effect, da
  verificare dal vivo prima di togliere) e nei test 17 avvisi. Il CI NON e' ancora cambiato: controlla ancora solo i nomi non definiti.
- Test offline **91/91** (con `.venv`), nuovi controlli: gating di execute_python, gruppi di SW_MCP_TOOLSETS, gruppo sconosciuto.
- **5.1 timeout (2026-10-17, scelta di Elia: thread di lavoro)**: tutte le chiamate COM passano da un thread unico (`_SW_EXECUTOR`,
  `CoInitialize` nel thread); il server risponde anche se SolidWorks si blocca. `tool_timeout` in config.json (default 300 s).
  Allo scadere: in modalita' dedicata il PID viene chiuso con taskkill (documenti non salvati persi, il server va riavviato);
  con l'istanza dell'utente non viene toccata, si riceve un errore che chiede di controllare SolidWorks. Mentre il tool precedente
  e' ancora bloccato i tool successivi rispondono subito con un errore. La chiusura all'uscita passa anche dal thread COM.
  Offline: 95/95 (thread unico, timeout, blocco dei tool successivi, ripresa).
  **Dal vivo `tests/test_timeout_live.py` 11/11** (SW_MCP_TOOL_TIMEOUT=15, due istanze dedicate): ciclo di chiamate COM -> errore a 15,1 s,
  PID chiuso, thread COM liberato subito (tool seguente risponde in 0,0 s); sleep Python 40 s -> errore a 15,2 s, tool seguente
  rifiutato in 0,0 s come "ancora in corso"; 0 processi orfani. `SW_MCP_TOOL_TIMEOUT` (env) ha la precedenza su config.json.
  Trovati dal vivo: (1) il timeout scattava sull'AVVIO dell'istanza (connect): ora, se SolidWorks non e' collegato, al limite si
  aggiungono SW_MCP_STARTUP_TIMEOUT + 60 s; (2) `SendMsgToUser2` NON blocca un'istanza nascosta (ritorna subito);
  (3) `connect_solidworks` chiamato una seconda volta in modalita' dedicata risponde "non risponde piu', riavvia" anche con l'istanza
  viva (`base.py`, `connect`: controlla `_dedicated_pid` prima di `_connected`) -> da sistemare con 5.2.
  **Regressione completa con il thread COM (2026-10-17, italiano), exit 0, tutto verde** (`test_output/regressione_20261017_1811.md`,
  log `%TEMP%\regr_f5.log`): offline 95/95, modeling 175/175, modeling_extra 259/259, drawings 65/65, drawing_quality 139/139,
  assembly 113/113, assembly_extra 214/214, data 159/159, simulation 120/120, timeout 11/11. 0 processi SolidWorks rimasti.
  Barra di avanzamento della regressione: `scripts_tmp/regr.ps1` (non versionato). 5.1 FATTO.
- **5.2 ripresa (2026-10-17) FATTO**: `SW_MCP_AUTORESTART=1` -> se l'istanza dedicata e' persa (crash, chiusa, uccisa dal timeout)
  il tool seguente la rilancia (`base._restart_dedicated`: chiude solo il SUO processo se ancora vivo) e il risultato di quel tool
  comincia con "ATTENZIONE: ... rilanciata (nuovo PID ...); i documenti aperti ... sono persi" (una volta sola). Senza la variabile:
  errore che la nomina. Corretto anche il bug di `connect_solidworks` chiamato due volte con l'istanza viva (ora successo, stesso PID).
  Offline 99/99; dal vivo `test_timeout_live.py` **18/18** (C: PID ucciso, tool seguente riparte in 15 s con PID nuovo, schizzo creato
  sulla nuova istanza, 0 orfani); `run_all.py data` 159/159. Regressione completa non rifatta: il percorso di connessione dei test
  (primo `connect`) non e' cambiato. README: variabili d'ambiente nuove documentate.
- **Non ancora fatti**: 5.6 descrizioni in inglese, CI pyflakes stretto, 5.10 risorse/prompt MCP (facoltativo).

## Prossimo passo
Piano completo fino al server finito, a fasi, in `PIANO_D_E.md`. Fasi 0, 1 e 2 chiuse. Fase 5 parziale (vedi sopra): prossimo passo
5.6 (descrizioni in inglese) e CI pyflakes. Poi fasi 3-4 (gruppi D ed E), 6 (prove d'uso reali), 7 (rilascio).
