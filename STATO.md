# STATO — SolidWorks MCP

Ultimo aggiornamento: 2026-10-18. Dettagli, misure, trappole API e cronologia completa: `STATO_STORICO.md`.
Elenco dei limiti da risolvere: `LIMITI.md`. Piano dei prossimi gruppi: `PIANO_D_E.md`. Mappa dei file: `ATLANTE.md`.

## Ambiente di sviluppo
- Windows 11 **ARM64**, SolidWorks 2026 SP4.1 Student, interfaccia **italiana** (API 34.4.1).
- Python 3.12 **x64** (emulato) in `.venv` (Python ARM64 non va: `cryptography` non ha wheel win-arm64).
- Dipendenze: `mcp` 1.x (`mcp<2`: la 2.x ha tolto `@server.list_tools()`), `pywin32`, `python-dotenv`.
- Server registrato come `solidworks` in `~/.claude.json` e in `%APPDATA%\Claude\claude_desktop_config.json`.

## Cosa c'e'
203 tool MCP: 25 base, 51 modellazione, 38 disegni, 35 assiemi, 31 dati/export, 23 simulazione (statica, frequenze, buckling, termico).

| Area | Stato | Test live (ultima regressione, 2026-10-17/18) |
|---|---|---|
| Modellazione 3D (blocco 1, gruppo B) | completa (UNI assente dal database di SolidWorks) | `test_modeling_live` 175/175, `test_modeling_extra_live` 284/284 (2026-10-18, con B7 e B8) |
| Disegni (blocco 4, gruppo A) | completi, tavole presentabili | `test_drawings_live` 65/65, `test_drawing_quality_live` 139/139 |
| Assiemi (blocco 2, gruppo C) | completi; C3 `[~]` | `test_assembly_live` 113/113, `test_assembly_extra_live` 214/214 |
| Dati ed export (blocco 3, gruppo D) | completi; D2 `[~]` (AP242) | `test_data_live` 183/183, `test_data_extra_live` 110/110 |
| Simulazione (blocco 5, gruppo E) | statica lineare, frequenze, buckling, termico stazionario; contatti locali, carichi remoti e da cuscinetto, controllo mesh | `test_simulation_live` 120/120, `test_simulation_extra_live` (2026-10-18, per sezione) E3 42, E5 36, E1 53, E4 37, E2 25 |
| Senza SolidWorks | registro e smistamento dei tool, sicurezza, PNG, lettori export, `.sldmat`, configurazione | `test_offline` 148/148 (anche su GitHub Actions); `test_timeout_live` 18/18 |

## Regole di lavoro
- I test live girano SOLO su un'istanza dedicata e nascosta (`SW_MCP_INSTANCE=dedicated`): l'istanza di SolidWorks di Elia non
  va mai toccata; alla fine si chiude solo il PID lanciato dal test (0 processi orfani).
- Il worker di sviluppo (`scripts_tmp/`, non versionato) va fermato (file `scripts_tmp/cmd/QUIT`) prima delle regressioni.
- Le opzioni di export sono preferenze utente GLOBALI di SolidWorks: salvarle e ripristinarle sempre.
- Ogni voce di `LIMITI.md` si chiude con un numero misurato dal test (le tavole si guardano ANCHE a occhio).
- Prima di cercare un'API, leggere le trappole gia' note in `STATO_STORICO.md` e nei docstring dei moduli `automation/`.

## Aperto
- **Gruppo D** chiuso (fase 3, 2026-10-17): tutto `[x]` tranne D2 `[~]` (AP242 non scrivibile). **Gruppo E** chiuso (fase 4, 2026-10-18): tutto `[x]`.
- Simulazione: un contatto locale senza compenetrazione che si apre (pezzo tirato e tenuto solo dal contatto) puo' bloccare il solutore
  fino al timeout (una prova ha finito, una no): avviso nella descrizione di `add_simulation_contact`, caso facoltativo nel test (`SX_E1_TRAZIONE=1`).
- Parziale: C3 (rotazione nei passi di traslazione dell'esploso: solo attorno alla direzione radiale, con un passo radiale di distanza 0).
- Residuo visivo non bloccante: nella tavola del cuneo la vista ausiliaria non sta sulla perpendicolare allo spigolo.
- Preferenze di SolidWorks cambiate durante lo sviluppo di cui non si conosce il valore originale: qualita' STL (int 78 = 2 fine)
  e tipo di import STL (int 208 = 2 solido). Controllare in Opzioni > Esporta/Importa se si notano differenze.
- 2026-10-17 (sonda D4): le preferenze della cattura TIFF/stampa valevano DPI (int 9) = 1 e carta (double 8/9) = 0,1 m, valori che
  SolidWorks non riaccetta: ora sono 300 DPI e Letter (0,2794 x 0,2159 m). Contano solo per "Salva come TIFF/immagine" in modalita' stampa.
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
- Regressione completa `tests
un_all.py`, exit 0, tutto verde (`test_output/regressione_20261017_1604.md`, log `%TEMP%
egr_f2.log`):
  offline 83/83, modeling 175/175, modeling_extra 259/259, drawings 65/65, drawing_quality 139/139, assembly 113/113,
  assembly_extra 214/214, data 159/159, simulation 120/120. 0 processi SolidWorks rimasti.

## Fase 5 (2026-10-17) — CHIUSA
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
- **5.6 descrizioni (2026-10-17) FATTO**: tutte le descrizioni dei tool e dei parametri in inglese (5 sotto-agenti, un file
  ciascuno; solo testi, struttura invariata: test di registro verde). Aggiunte le 213 descrizioni mancanti; ogni parametro numerico
  dice l'unita'; esempi JSON nei tool complessi. Nota di `safety.py` ora "[DESTRUCTIVE: ...]" e descrizione di `overwrite` in inglese
  (test live aggiornati). Nuovo controllo offline `test_descriptions` (descrizione presente, niente parole italiane, unita' nei
  numeri): offline **103/103**. Caratteri dell'elenco dei tool: 102.413 -> 112.862 (+10 %, per le descrizioni aggiunte; con
  `SW_MCP_TOOLSETS` si riduce). Controllo per file: `scripts_tmp/desc_check.py <file>`.
  Dubbi dei sotto-agenti da verificare all'uso (fase 6): verso di `add_force mode=normal`, unita' delle coordinate di
  `add_detail_view`/`add_crop_view` (mm del modello), `sweep.keep_normal`, `select_at_point.tolerance`.
- **5.8 FATTO**: pyflakes a 0 avvisi su `solidworks_mcp` e `tests` (tolti anche gli import `win32com.client`/`pythoncom` doppioni:
  li importa gia' `base.py`; nei test le chiamate restano, solo senza assegnazione inutile). Il CI ora fallisce su qualunque avviso.
- Dopo 5.6/5.8 dal vivo: `run_all.py modeling_extra assembly_extra` 259/259 e 214/214 (controllano annotazioni e schemi), 0 orfani.
- **FASE 5 CHIUSA** (criterio del piano: 1-4 provati dal vivo, 5-9 coperti dal test offline). Rinviato, facoltativo: 5.10 risorse e
  prompt MCP (si puo' fare durante la fase 6, se le prove d'uso lo chiedono).

## Fase 3 (2026-10-17/18, gruppo D) — CHIUSA
- **D5 `[x]`**: `export_model_image(hide_reference=true)` sugli assiemi nasconde anche i riferimenti dei componenti (toggle di documento
  198, salvato e ripristinato). `test_data_live` 168/168 (sez. 11: 1596 / 0 / 1596 pixel azzurri). Trappola: nell'assieme la
  visualizzazione dei piani e' spenta di default (dettagli in `STATO_STORICO.md`).

- **D6 `[x]`** (assiemi: export STL/STEP, box, immagine): `test_data_live` sez. 12 183/183 dal vivo (tre giri di correzioni; trappole
  in `STATO_STORICO.md`). Il box dell'assieme ora si calcola dai pezzi con `Transform2` (non piu' `GetBox`); `GetComponents(True)`;
  export STL per componente riconosciuto dai file `<nome> - <componente>.stl`. Dettaglio: scarto box 0,0 mm, volume STEP reimportato
  135456,7664 contro 135456,8204 mm3. Da fare: il messaggio del per-componente mostra "0 byte" per il file base (cosmetico).
  Regressione completa non rifatta dopo queste modifiche: offline 103/103 (OK); `test_data_live` completo sì.

- **Fase 3, resto del gruppo D** (2026-10-17): nuovo file `tests/test_data_extra_live.py` (sezioni D7 D8 D1 D10 D4 D9 D2 D3, anche in
  `run_all.py` come `data_extra`). Codice scritto da sotto-agenti in worktree, riportato su main e provato dal vivo sezione per sezione:
  D7 (convenzione: GetMomentOfInertia da' i PRODOTTI d'inerzia), D8, D1 (nuovo tool `apply_configuration_table`: 197 tool), D10,
  D2 `[~]`, D3 (verifica strutturale; eDrawings non automatizzabile), D4 (cattura di stampa + ricentratura, prospettiva), D9
  (step_as/interconnect/diagnose). Numeri in `LIMITI.md`, trappole in `STATO_STORICO.md`. Offline 147/147.

- **Regressione completa di chiusura del gruppo D** (2026-10-17 22:41 -> 2026-10-18, italiano, `test_output/regressione_20261017_2241.md`):
  offline 147/147, modeling 175/175, drawings 65/65, drawing_quality 139/139, assembly 113/113, data 183/183, data_extra 110/110,
  simulation 120/120, timeout 18/18; modeling_extra 258/259 e assembly_extra 213/214 per il solo conteggio fisso dei tool (196 -> 197,
  corretto nei test), rilanciati: 259/259 e 214/214 (`regressione_20261018_0003.md`). 0 processi SolidWorks rimasti.

## Fase 4 (2026-10-18, gruppo E) — CHIUSA (regressione completa: alla fine del lavoro, fase 7)
- Sonde dal vivo in `scripts_tmp/eprobe.py` (nomi, argomenti e trappole in `STATO_STORICO.md`, "Fase 4"); codice e test scritti da due
  sotto-agenti in worktree, riportati su main e provati sezione per sezione con `tests/test_simulation_extra_live.py E3|E5|E1|E4|E2`.
- 5 tool nuovi (202): `add_temperature`, `add_remote_load`, `add_bearing_load`, `add_simulation_contact`, `add_mesh_control`;
  `create_static_study(analysis, modes)` crea anche studi di frequenze, buckling e termici; `get_simulation_results` risponde per tipo
  di studio, con posizione e corpo del FOS minimo (E3) e momento delle reazioni (E4). Numeri in `LIMITI.md`, gruppo E.
- Corretto dal vivo: le opzioni dello studio (`NoOfFrequencies`, `BucklingModes`) vanno lette da un oggetto tenuto in una variabile.
- Offline 147/147. I test live contano i tool da `tests/live_common.py` (`EXPECTED_TOOLS = 202`).

## Fase 6 (2026-10-18) — scenari S1-S7 FATTI
- Il server di questa chat non era in modalita' dedicata: prove fatte con `scripts_tmp/ponte.py` (sessione MCP con istanza dedicata) +
  `scripts_tmp/chiama.py TOOL '{json}'` (una chiamata per comando); trascrizioni in `test_output/fase6_S1.jsonl` e `fase6_S6.jsonl`.
  Aggiunto in `~/.claude.json` un server `solidworks` SOLO per questo progetto con `SW_MCP_INSTANCE=dedicated` e `SW_MCP_AUTORESTART=1`
  (copia di sicurezza `~/.claude.json.bak_20261018`): vale dalla prossima sessione.
- Esiti: S1 volume 153317,58 = calcolo, massa 1,22654 kg, PDF valido; S2 volume 30356,6 = calcolo; S3 2 gradi di liberta', distinta 3 righe,
  3 palloncini; S4 freccia 0,7964 (0,80), 30,05 MPa a meta' (30), 60,35 all'incastro, FOS 5,83; S5 volumi 30000/40000/50000, 3 STEP validi;
  S6 (inglese) stessi numeri, poi lingua rimessa in italiano (verificato: italian, 83 e 262 False); S7 rifiuto con spiegazione.
- Errori del modello -> descrizioni corrette: `create_hole` (face_point E positions diventano tutti fori), `save_drawing` (filepath
  obbligatorio), `rebuild_model` (solo pezzi). Aperti: quota Ø90 del cerchio dei fori non messa in tavola (si usa una nota); perno di S3
  "nessuna soluzione" nello stato dei vincoli senza accoppiamenti in errore; un "salva con nome" dopo la simulazione bloccato una volta
  oltre 300 s (non ripetuto in 4 prove, `scripts_tmp/eprobe.py SAVE`).
- `docs/esempi/` e sezione Esempi del README: in scrittura da un sotto-agente al momento dello stop (controllare `git status`).

## Fase 7 (2026-10-18) — pronta per il rilascio
- `docs/esempi/` (S1-S7) e sezione Esempi del README committati.
- Regressione completa in italiano (`test_output/regressione_20261018_1148.md`, log `%TEMP%\regr_f7.log`): offline 147/147, modeling 175/175,
  modeling_extra 259/259, drawings 65/65, drawing_quality 139/139, assembly 113/113, assembly_extra 214/214, data 183/183,
  data_extra 110/110, simulation 120/120, simulation_extra 181/181, timeout 15/18; 0 processi SolidWorks rimasti.
  Un primo tentativo (09:32) si era interrotto: l'istanza dedicata e' morta durante drawing_quality fra la tavola della flangia e quella
  del perno (non ripetuto nel secondo giro, 139/139).
- Rosso del timeout, sezione C (istanza uccisa da fuori, il tool seguente la rilancia): il rilancio ha impiegato 23 s e il tool aveva solo
  i 15 s del test, perche' il tempo di avvio si aggiungeva solo con `_sw_app` vuoto. Corretto in `server.py` (`_dedicated_lost`: processo
  dedicato morto + AUTORESTART -> tempo di avvio in piu'). Dopo: `run_all.py timeout` 18/18 due volte, offline 147/147, pyflakes 0.

## Installazione pulita e scenari (2026-10-18)
- Licenza: aggiunta la riga di copyright di Elia sotto quella dell'autore originale (MIT).
- Clone in `C:\Users\elia\Downloads\solidworks-mcp-pulito` (remote GitHub), venv nuovo con Python x64, `pip install -e .` come da README:
  `solidworks-mcp.exe` creato, `test_offline` 147/147, il server espone 201 tool (202 meno `execute_python`, nascosto senza `SW_MCP_ALLOW_PYTHON=1`).
- Scenari rifatti sull'installazione pulita con il ponte (istanza dedicata, copia del ponte nello scratchpad che lancia `solidworks-mcp.exe`):
  S1 153317,58 mm3 / 1,22654 kg, PDF 1 pagina; S2 30356,6; S3 2 gradi di liberta', distinta 3 righe, 3 palloncini; S4 0,79697 mm,
  30,049 MPa a meta', 60,345 all'incastro, FOS 5,826; S5 30000/40000/50000, 3 STEP validi; S7 rifiuto con spiegazione;
  S6 in inglese: stessi numeri, 37 chiamate 0 errori, poi lingua rimessa in italiano (verificato al riavvio: italian, 83 e 262 False).
  0 processi SolidWorks rimasti. Tempi: `save_document` dopo la simulazione (S5) 230 s, riuscito (lento ma senza blocco);
  `insert_model_dimensions` ~88 s.
- Trovati e corretti: (1) README, controllo del Python x64: `platform.machine()` dice `ARM64` anche con il Python x64 emulato su ARM64
  -> ora `sysconfig.get_platform()` = `win-amd64`; (2) `apply_configuration_table` con un percorso .csv/.json inesistente rispondeva
  "tabella vuota" (lo leggeva come testo CSV): ora "file non trovato" (`utils/config_table.py`, test offline 148/148).
- Il push e' bloccato dall'hook per l'agente: lo fa Elia.
- README riscritto in inglese (scelta di Elia: solo inglese) con badge, due immagini in `docs/img/` (tavola d'assieme da
  `qual_assieme.png`, von Mises di S6), tabelle funzioni/scenari/variabili, sicurezza, lingue, limiti noti. Residuo visivo visto
  nelle tavole di S1/S6: sotto la nota dei fori c'e' un rettangolo vuoto (cornice della nota?), non indagato.

- 2026-10-18, GitHub Actions rosso dalla run #11 (commit 6fdf2d2, ma la causa e' in 1b23e96): test offline 147/148 su Linux,
  "timeout: errore dopo il limite" -> `[Errno 2] No such file or directory: 'taskkill'` (`_timeout_message` in `server.py` lancia
  `taskkill`, che su Linux non esiste). Corretto: OSError -> istanza "non chiusa". Riprodotto su Windows togliendo `taskkill` con un
  `sitecustomize.py` nello scratchpad: senza correzione 147/148, con correzione 148/148; pyflakes 0.

- 2026-10-18, repository reso PUBBLICO. Prima: email personale tolta da tutti i commit (filter-branch, autore/committer ->
  `276014981+elo-savage@users.noreply.github.com`, anche `user.email` locale del repo), copia di sicurezza
  `C:\Users\elia\Downloads\solidworks-mcp-backup-20261018.bundle`; push forzato e cancellazione dei rami remoti
  `claude/exciting-gauss-3bao28` e `fase-0-verifica-offline` fatti da Elia; esecuzioni Actions 1-13 cancellate. Verificato da anonimo:
  API dei commit con sole email noreply, README/immagini/badge raggiungibili, badge "passing". RESTA: i commit vecchi sono ancora
  raggiungibili da chi conosce il loro codice (es. `/commit/c0c0252.patch` mostra l'email) finche' GitHub non li elimina; per toglierli
  subito serve una richiesta al supporto GitHub (rimozione di dati sensibili / viste in cache).

## Fori fino a M70 e move_faces (2026-10-18) — FATTO
- `create_hole`: misure metriche M3..M70 (tabelle in `modeling.py`, `_METRIC`). Il database Hole Wizard non ha tutte le misure grandi
  (M60 di passaggio, M52 filettato senza passo, M68 e M70 per nessun tipo, lamati solo M24/M30/M36/M42/M48/M56/M64, svasati nessuno
  sopra M20): il tool prova la misura, poi col passo grosso, poi per semplici e filettati fa un foro generico col diametro calcolato
  piu' una filettatura cosmetica (risultato: `method`, `database_size`, `cosmetic_threads`). Lamati e svasati inesistenti: rifiuto
  con le misure disponibili. M70: valori di passaggio interpolati (non normati), dichiarato nel risultato.
- Nuovo tool `move_faces` (203 tool): offset, traslazione, rotazione attorno a un asse parallelo a X/Y/Z.
- Test: B7 15/15 e B8 12/12 (numeri in `LIMITI.md`, trappole in `STATO_STORICO.md`); `test_modeling_extra_live` 284/284,
  `test_modeling_live` 175/175, offline 148/148, pyflakes 0; 0 processi SolidWorks lasciati (l'istanza di Elia non e' stata toccata).
  Regressione completa non rifatta: cambiati solo `modeling.py`, `modeling_tools.py` e i conteggi dei tool nei test.
- Barre di avanzamento per le attese: `scripts_tmp/avanzamento_log.py` (non versionato), si lancia in una scheda del terminale.

## Strumenti di schizzo: difetti (2026-10-18, sessione in corso)
- **B `[x]` provato dal vivo** (2026-10-18, `scripts_tmp/probe_bc.py`, istanza dedicata PID 1568, 0 orfani): `set_dimension_value`
  decideva "angolo" solo con il tipo COM (GetType == 3); ora anche `unit="deg"` indica un angolo. Prove: 30 -> 30, 30 -> 45, 45 -> 30 gradi,
  tutte con `SUCCESS` e unita' `deg`.
- **C `[x]` provato dal vivo**: `create_sketch(plane="Top")` risponde "Sketch created on Top".
- **A riprodotto dal vivo, NON corretto**: una linea a +30 gradi (punto finale (40; 23,094)) diventa a -30 gradi (punto (40; -23,094))
  appena `add_sketch_dimension(kind="angle", value=30)` applica il valore; poi 45 gradi la porta a (32,66; -32,66). Il valore e'
  corretto in modulo, il quadrante no: la quota angolare di SolidWorks misura nel verso opposto. Idea da provare: dopo aver applicato
  il valore, leggere il punto finale della seconda linea e, se il quadrante e' rovesciato, riapplicare con il valore col segno opposto.
  **Provato dal vivo, NON funziona** (2026-10-18, `scripts_tmp/probe_bc.py`): (1) riapplicare con `SystemValue = -valore` lascia la linea
  a -23,094; (2) spostare il testo della quota sotto l'asse (30, -12) non cambia nulla; (3) invertire l'ordine delle due linee
  (l2, l1) rovescia comunque il verso. Il valore dell'angolo e' non orientato: il quadrante non si controlla con il segno.
  Codice tentato ripristinato (nessuna modifica in `sketch_constraints.py`). **Scelta di Elia (2026-10-18): accettato il quadrante
  di SolidWorks e documentato** nella descrizione del parametro `value` (`modeling_tools.py`); offline 148/148.
- **E, prova dal vivo (2026-10-18, `scripts_tmp/probe_e.py`)**: su un blocco 40x30x10 la `select_at_point` di una faccia piana
  funziona in 4 punti (distanza 0, area 1200 mm2). Il rifiuto "Select4 ha rifiutato il face" NON si riproduce su faccia piana:
  resta da provare la faccia con foro al centro e la selezione con un altro documento aperto (legato a F).
- **E su faccia forata (2026-10-18, `scripts_tmp/probe_e2.py`)**: foro M8 al centro, `select_at_point` nel centro dà il rifiuto
  giusto ("nessuna faccia entro 0,05 mm, piu' vicino a 4,5 mm"); su faccia forata a 6 mm dal centro e nei punti lontani la selezione
  riesce. Il messaggio "Select4 ha rifiutato" NON si riproduce. E resta aperto.
- **F `[x]` in parte, provato dal vivo** (2026-10-18, `scripts_tmp/probe_f.py`): nuovo parametro comune `document` (titolo di un
  documento aperto), gestito in `server._dispatch_tool` e aggiunto allo schema di tutti i tool in `safety.decorate_tools`.
  Prova: con Parte2 attiva, `create_sketch(plane="Top", document="Parte1")` crea lo schizzo su Parte1 e Parte1 diventa attiva.
  **Non provato dal vivo**: l'avviso "il documento attivo e' cambiato" tra due chiamate (serve un cambio fatto fuori dal server).
  Offline 148/148 (il test di coerenza degli schemi ammette `document`), pyflakes 0.
- **Nuovi strumenti 1 e 2 (2026-10-18), provati dal vivo** (`scripts_tmp/probe_list.py`, `probe_del.py`, `probe_dim.py`):
  - `list_sketch_relations(sketch)`: legge `sk.RelationManager.GetRelations(0)`; ogni relazione ha `GetRelationType` (intero) e
    `GetEntities` (id). Provato: linea orizzontale -> [0] coincident (P2-3, P0-1), [1] horizontal (S0-0-1). **Codici di tipo
    dedotti da questo solo caso**: 4 = horizontal, 9 = coincident. Gli altri restano "tipo N" finche' non vengono verificati.
  - `delete_sketch_entities(entities, dimensions, relations, sketch)`: relazione per indice -> `RelationManager.DeleteRelation`
    (provato: 2 -> 1 relazioni); entita' per id -> selezione + `DeleteSelection2` (provato: 0 segmenti, 0 punti);
    quota per nome -> `SelectByID2` + `DeleteSelection2` (provato: da "completamente definito" a "sottodefinito", quote 0).
  - **Anomalia**: in una sola esecuzione `GetRelations(0)` ha dato 0 relazioni con lo stesso schizzo (le altre 4 volte: 2).
    Non capita piu' finora: da tenere d'occhio. Non c'e' ancora la cancellazione per "tipo + entita'" (spec 2 del brief).
  - Conteggi tool: 205 (204 senza `execute_python`), `EXPECTED_TOOLS` aggiornati in `test_offline.py` e `live_common.py`.
  - Registrati come distruttivi in `safety.py` (`delete_sketch_entities`). Offline 148/148, pyflakes 0.
- **Tool 4 `split_sketch_entity` (2026-10-18), provato dal vivo** (`scripts_tmp/probe_split2.py`, `probe_split3.py`): solo linee.
  La linea viene cancellata e ricostruita come due linee; quote e relazioni dell'originale vanno perse (dichiarato nel messaggio).
  Prova: linea 0..40 divisa in (20,0) -> due segmenti che condividono il punto P1-5 (3 punti in tutto: il giunto e' vero, non solo
  geometrico). Punto fuori linea (9 mm) e punto all'estremo: rifiutati con messaggio. Distruttivo, registrato in `safety.py`.
  Conteggi tool: 206 (205 senza `execute_python`).
- **Tool 3 `trim_sketch_entities` NON fatto** (2026-10-18, prove dal vivo `scripts_tmp/probe_trim.py`, `probe_trim2.py`,
  `probe_trim3.py`). Documentazione (`ISketchManager.SketchTrim`, enum `swSketchTrimChoice_e`): Closest, Corner, Entities,
  EntityPoint (power trim: un segmento selezionato, un punto con X, Y, Z NON nulli), Inside, Outside. I valori numerici NON si
  leggono dalla libreria locale (`tlbenum.py` non trova enum) e la pagina non li riporta nello snippet.
  Risultati misurati (scena: orizzontale 0..40 + verticale a x=20, clic/punto (30,0)):
  - senza selezione: 0-6 tutti `False`; il codice 3 agiva sull'ULTIMA linea disegnata (ancora selezionata), non sul punto;
  - con l'orizzontale selezionata: codice 0 -> orizzontale 0..20 ma `False` (il valore di ritorno NON e' affidabile);
    codice 3 -> `True`, orizzontale 30..40; codice 4 -> `True`, orizzontale 20..40; 1, 2, 5, 6 -> `False`, nessun cambio.
  Conclusione: nessun codice dimostrato come power trim; il successo va verificato sulla geometria, non sul ritorno.
  Da decidere con Elia: confermare i valori numerici dell'enum (pagina della documentazione o prova controllata) prima
  di scrivere `trim_sketch_entities`.
- **Tool 5 `move_sketch_point` e tool 6 `toggle_construction` (2026-10-18), provati dal vivo** (`scripts_tmp/probe_mv.py`):
  - spostamento: il punto si imposta con `X`/`Y` (proprieta' scrivibili, nessun metodo dedicato trovato). Provato: `pt@40,0` ->
    (45, 0), geometria riletta (`S0-0-1` 0..45). Con una relazione "fissa" sul punto lo spostamento viene RIFIUTATO e il punto
    resta dov'era (messaggio con la posizione reale): la verifica sulla posizione rilegge il valore, non fida del silenzio.
  - costruzione: `ConstructionGeometry` scrivibile. Provato: normale -> costruzione (`construction: true` in list) -> normale.
    Con la linea di costruzione lo schizzo risulta "completamente definito" (SolidWorks conta la linea), da tenere presente.
  - Conteggi tool: 208 (207 senza `execute_python`). Offline 148/148, pyflakes 0. Non sono distruttivi.
- **Tool 7 `convert_entities(construction=true)` e tool 8 (quote verso spigoli del modello), provati dal vivo**
  (`scripts_tmp/probe_model.py`, blocco x 0..10, y -20..20, z -15..15, schizzo sul piano x=0):
  - convert con `construction=true`: lo spigolo a (0,10,15) diventa `S0-2-3` di costruzione (list: `construction: true`).
  - quota verso lo spigolo del modello: `add_sketch_dimension(kind="distance", entity1=<linea a z=5>, entity2={"edge":[0,10,15]})`
    -> 10,0000 mm (distanza reale 15-5). Il riferimento del modello e' `{"edge"|"vertex"|"face": [x,y,z]}` (coordinate del modello,
    `unit`); la selezione usa `_select_point` sul modello. La descrizione di `entity1` nello schema lo dice.
  - Nessun tool nuovo: 208 tool (207 senza `execute_python`), offline 148/148, pyflakes 0.
- **Tool 9 `delete_dimension` e `set_dimension_driven`, provati dal vivo** (`scripts_tmp/probe_driven2.py`):
  - `delete_dimension(name)`: stessa operazione di `delete_sketch_entities(dimensions=[..])`. Provato: schizzo da
    completamente definito a sottodefinito, quote 0.
  - `set_dimension_driven(name, driven)`: `Dimension.DrivenState` e' scrivibile (guidata = 2, di riferimento = 1, letti dal vivo).
    **Trappola**: senza una ricostruzione il solutore NON applica il cambio (la quota restava vincolante e il punto era bloccato).
    Il tool chiude lo schizzo, fa `EditRebuild3` e lo riapre per leggere lo stato. Provato: di riferimento -> sottodefinito, il punto
    si sposta a 50 mm e la geometria segue; rimessa guidata -> completamente definito.
  - Conteggi tool: 210 (209 senza `execute_python`). Offline 148/148, pyflakes 0. `delete_dimension` e' distruttivo (`safety.py`).
- **Ancora da fare**: trim (3, vedi sopra), sketch_offset/mirror/fillet (10, solo se Elia li vuole).
- **Regressione 2026-10-18 sera INTERROTTA da Elia** (log `%TEMP%\regr_h2.log`): offline 148/148; modeling FAIL "nessun riepilogo"
  (istanza dedicata "non risponde piu'" durante `flangia`, piu' PermissionError sulla rotazione di
  `%LOCALAPPDATA%\solidworks-mcp\solidworks_mcp.log`); modeling_extra FAIL 281/284 (3 rossi da leggere in
  `test_output/run_modeling_extra.log`, processo 12748 rimasto); drawings PASS 65/65; drawing_quality FAIL "nessun riepilogo";
  assembly interrotto a 8/113. Processi rimasti a fine sezione: 12748 e 14820 (poi chiusi). Sospetto: ~8 server MCP di altre sessioni aperti insieme scrivono lo stesso log
  e la rotazione fallisce. Da indagare prima di rifare la regressione. Chiusi solo i processi dei test; istanza di Elia (3976) intatta.
  Il quadrante dell'angolo (A) resta com'e' (documentato). E (faccia forata) non riprodotto.
- **D**: le misure M3..M70 sono gia' in `modeling.py` (fatto con il commit c59b918): da verificare dal vivo con M56.
- **A, E, F, e i 9 strumenti nuovi**: non ancora iniziati. Quota angolare: il ribaltamento avviene quando SolidWorks applica il valore
  (`SystemValue`), la causa esatta si vede solo dal vivo. Offline: 148/148, pyflakes 0.

## Lotti di tool nuovi (2026-10-18/19, in corso) — obiettivo di Elia: server completo, soprattutto per la modellazione
- Infrastruttura: tool nuovi per lotti in `solidworks_mcp/tools_ext/<lotto>.py` (schemi, gruppo `modeling`) + mixin
  `automation/ext_<lotto>.py`; `DESTRUCTIVE`/`OVERWRITE` dei lotti uniti a `safety.py`. Laboratorio di sviluppo `scripts_tmp/lab.py NOME`
  + `labrun.py` (piu' istanze dedicate insieme, codice ricaricato a ogni script, chiusura da sola dopo 45 min). Riferimento API dalle
  DLL di interop: `scripts_tmp/api_ref/` (enum swconst, firme dei metodi, catalogo `RICERCA_MODELLAZIONE.md` di 240 comandi).
- Log condiviso: la rotazione del file comune ai server MCP di piu' sessioni falliva con PermissionError (sospetto della regressione
  interrotta): ora `_SharedRotatingFileHandler` salta la rotazione per 10 minuti e continua a scrivere.
- Fatti e provati dal vivo (trappole in `STATO_STORICO.md`, "Lotti di tool nuovi"):
  - moka1 (estensioni): piani `mid_plane` `[~]` (offset di meta' distanza, non associativo: il vincolo MidPlane non crea nulla),
    `line_point`, `normal_to_curve`, `parallel_point`; asse di rivoluzione da asse/spigolo/altro schizzo; relazioni verso il modello e
    altri schizzi (`pierce` verso la curva di un altro schizzo `[~]`: punto calcolato + coincidente sulla proiezione); estrusione
    `start_from` (superficie Mark 32, vertice, offset T0=3); `list_entities` con tipo e parametri di superficie/curva. Test 50+29+31 PASS.
  - moka2 (7 tool): `add_cosmetic_thread`, `fill_pattern`, `list_bodies`, `delete_body`, `combine_bodies`, `insert_part`,
    `get_feature_definition`. Test 49/49. Toolbox `[~]` (nessuna API d'inserimento, add-in non caricato).
  - sketch2 (16 tool): trim (6 modi), extend, smusso, ripetizioni lineare/circolare, sposta/ruota/scala/copia, rettangoli da centro e
    3 punti, parallelogramma, arco tangente, parabola, curva da equazione, schizzo 3D (linea, spline, punto). Test 50/50.
    Non fatti: conica (i 4 punti non hanno il significato atteso), curva di intersezione (`IntersectCurves` non crea nulla).
  - curves (6 tool): `create_helix` (passo/giri/altezza, spirale, conica), `create_variable_pitch_helix`, `project_curve`,
    `split_line` (proiezione e silhouette; intersezione `[~]`), `composite_curve`, `curve_through_points` (file di punti). Test 89/89:
    molla con sweep sull'elica 0,024 % dal calcolo. `sweep` accetta gia' il nome di una curva come percorso.
- Conteggio: 239 tool con `execute_python` (238 senza). In lavorazione: superfici 1, estensioni ext1, feature avanzate; poi feature avanzate,
  corpi 2, gestione, lamiera, superfici 2, saldature, stampi. Regressione completa solo alla fine.

## Prossimo passo
Passi di Elia (fase 7): tag `v6.0.0`, push, installazione su un PC pulito seguendo il README e scenario S1 su quella macchina.
Fase 6: il server `solidworks` di Claude Code (in `~/.claude.json`) NON ha `SW_MCP_INSTANCE=dedicated`: i suoi tool userebbero l'istanza
di Elia. Per le prove d'uso serve un server con l'istanza dedicata (vedi la sezione Fase 6 quando c'e').
