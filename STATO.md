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
| Senza SolidWorks | registro e smistamento dei tool, sicurezza, PNG, lettori export, `.sldmat`, configurazione | `test_offline` 83/83 (2026-10-13, Linux; anche su GitHub Actions) |

## Regole di lavoro
- I test live girano SOLO su un'istanza dedicata e nascosta (`SW_MCP_INSTANCE=dedicated`): l'istanza di SolidWorks di Elia non
  va mai toccata; alla fine si chiude solo il PID lanciato dal test (0 processi orfani).
- Il worker di sviluppo (`scripts_tmp/`, non versionato) va fermato (file `scripts_tmp/cmd/QUIT`) prima delle regressioni.
- Le opzioni di export sono preferenze utente GLOBALI di SolidWorks: salvarle e ripristinarle sempre.
- Ogni voce di `LIMITI.md` si chiude con un numero misurato dal test (le tavole si guardano ANCHE a occhio).
- Prima di cercare un'API, leggere le trappole gia' note in `STATO_STORICO.md` e nei docstring dei moduli `automation/`.

## Aperto
- **Gruppo D** (dati ed export) e **gruppo E** (simulazione): tutto da fare, piano in `PIANO_D_E.md`.
- Parziali (B4 e C5 riaperti, piano in `PIANO_D_E.md`): B4 (UNI assente dal database; posizione angolare dei fori su facce cilindriche non controllabile), C3 (rotazione nei
  passi di traslazione dell'esploso), C5 (blocco/ingranaggio/vite non propagati dal solutore via API).
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

## Lingua inglese (G1, 2026-10-12, non ancora provato dal vivo)
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

## Prossimo passo
Piano completo fino al server finito, a fasi, in `PIANO_D_E.md`. Fase 0 chiusa. Fase 1 (inglese) in corso: regressione
completa con SolidWorks in inglese, esiti da aggiungere qui.
Poi fase 1 (inglese), fase 5 (robustezza), fase 2 (B4/C5/C3), fasi 3-4 (gruppi D ed E), fase 6 (prove d'uso reali), fase 7 (rilascio).
