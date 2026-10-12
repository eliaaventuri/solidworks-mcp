# CLAUDE.md — istruzioni per lavorare su SolidWorks MCP

Server MCP (Python, COM via pywin32) che espone 196 tool per SolidWorks 2026 (interfaccia italiana o inglese). Si lavora in italiano.
Lo sviluppo vero avviene sul PC di Elia (Windows 11 ARM64, SolidWorks 2026 SP4.1 Student, Python x64 in `.venv`).

## Da leggere all'inizio di ogni sessione
1. `STATO.md`: stato attuale, cose aperte, **prossimo passo** (partire da li').
2. `LIMITI.md`: elenco di lavoro per gruppo (`[ ]` da fare, `[x]` fatto e misurato, `[~]` parziale con spiegazione).
3. `PIANO_D_E.md`: piano dei gruppi D/E e della ripresa di B4/C5/C3.
4. `ATLANTE.md`: dove sta cosa. `STATO_STORICO.md`: misure, cronologia e soprattutto le **trappole API gia' scoperte**
   (cercarle li' e nei docstring di `solidworks_mcp/automation/*.py` prima di indagare un'API).

## Regole che non si discutono
- **Mai toccare l'istanza di SolidWorks di Elia.** Prove e test solo su un'istanza dedicata e nascosta (`SW_MCP_INSTANCE=dedicated`,
  gia' impostata dai test live). Alla fine si chiude solo il PID lanciato da noi; 0 processi orfani. Mai `GetActiveObject` in prova.
- Le opzioni di export/import sono **preferenze globali** di SolidWorks: leggere il valore, impostare, ripristinare sempre (try/finally).
- Una voce di `LIMITI.md` si chiude `[x]` solo con un **numero misurato** dal test e confrontato con un valore calcolato
  (volume, massa, quota, posizione, reazione). Le tavole si guardano anche a occhio (`test_output/qual_*.png`).
- Se un limite e' di SolidWorks e non si aggira: `[~]` con la prova fatta e il risultato, e il tool lo dichiara nel risultato.
- Mai `while True` senza tetto negli script di prova; le chiamate COM bloccanti possono appendere il processo.
- Tool distruttivi o che scrivono file: registrarli in `solidworks_mcp/safety.py` (annotazione + `overwrite`).

## Test
- Senza SolidWorks (anche su Linux, e su GitHub Actions a ogni push): `python tests/test_offline.py`.
  Controlla registro e smistamento dei tool: un tool nuovo deve avere schema, voce in una tabella `*_DISPATCH` e metodo coerenti.
- Regressione completa (Windows + SolidWorks): `.venv\Scripts\python.exe tests\run_all.py` -> riepilogo in
  `test_output/regressione_*.md`. Un solo test: `tests\run_all.py data` oppure direttamente `tests\test_data_live.py`.
  Sezioni: `test_modeling_extra_live.py B1 B4`, `test_assembly_extra_live.py C1 C5` (`CX_REUSE=1`), `QUAL_ONLY=staffa test_drawing_quality_live.py`.
- Prima di una regressione fermare il worker di sviluppo (`scripts_tmp/cmd/QUIT`; `run_all.py` lo fa da solo).
- Dopo un lavoro: regressione completa, esiti in `STATO.md`, voce aggiornata in `LIMITI.md`, dettagli e trappole nuove in `STATO_STORICO.md`.

## Codice
- `solidworks_mcp/server.py`: tool base + smistamento (`BASE_DISPATCH`, `SPECIAL_HANDLERS`, `DISPATCH_TABLES`).
- `solidworks_mcp/*_tools.py`: schemi MCP per area + tabella `*_DISPATCH` (nome -> metodo, parametri ammessi).
- `solidworks_mcp/automation/`: un mixin per area, riuniti in `SolidWorksAutomation`. Risultati sempre con `self._result(...)`.
- Late binding pywin32: i membri senza argomenti sono PROPRIETA' (usare l'helper `_com`); array di oggetti COM come
  `VARIANT(VT_ARRAY|VT_DISPATCH/VT_VARIANT, ...)`; parametri per riferimento con `VARIANT(VT_BYREF|...)`.
- Lingua: il server deve funzionare con SolidWorks in italiano E in inglese. Mai nomi fissi in una lingua: piani standard e origine
  con `_std_ref_feature` (posizione/tipo), tipi di feature con `GetTypeName2` (uguali in ogni lingua), template chiesti a SolidWorks,
  cartelle `lang\<lingua>` con `lang_folders(self._ui_language())`. Quando un nome serve per forza (grafici, testi del cartiglio,
  scritte sulle tavole) va in `solidworks_mcp/utils/sw_lang.py` con entrambe le varianti.
- Test live: scritti con i nomi italiani; con SolidWorks in inglese `tests/live_common.py` traduce gli argomenti (`L()` per i controlli).
- Strumenti locali non versionati in `scripts_tmp/` (worker con istanza dedicata, esplorazione della type library).

## Git
- Messaggi di commit in italiano. Non committare `test_output/`, `scripts_tmp/`, `.venv/`.
