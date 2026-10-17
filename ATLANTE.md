# ATLANTE — mappa dei file

## Documentazione
```
CLAUDE.md                     istruzioni per Claude Code: cosa leggere, regole, test
README.md                     cos'e' il progetto, installazione, tool, test
STATO.md                      stato attuale in breve: cosa funziona, esiti dei test, regole di lavoro, cosa e' aperto
STATO_STORICO.md              diario completo: esiti per blocco, misure, trappole API di SolidWorks, incidenti
LIMITI.md                     elenco di lavoro dei limiti noti per gruppo (A disegni, B modellazione, C assiemi, D dati, E simulazione, F sicurezza)
PIANO_D_E.md                  piano di lavoro completo a fasi fino al server finito + schede tecniche di D, E, B4/C5/C3 (non ancora provato dal vivo)
ATLANTE.md                    questo file
LICENSE                       MIT (copyright dell'autore del progetto originale)
```

## Server
```
solidworks_mcp_server.py      avvio del server MCP (stdio)
requirements.txt              dipendenze: mcp<2, pywin32
solidworks_mcp/
  server.py                   25 tool base (connessione, documenti, schizzi, feature semplici, utilita'); smistamento di tutte le chiamate con tabelle (BASE_DISPATCH + *_DISPATCH, SPECIAL_HANDLERS), guardia di sovrascrittura
  modeling_tools.py           schemi dei 50 tool di modellazione -> automation/modeling.py, sketch_constraints.py
  drawing_tools.py            schemi dei 38 tool di disegno -> automation/drawings.py e mixin drawing_*
  assembly_tools.py           schemi dei 35 tool di assieme -> automation/assembly*.py
  data_tools.py               schemi dei 30 tool di dati ed export -> automation/data_export.py
  simulation_tools.py         schemi dei 18 tool di simulazione -> automation/simulation.py
  safety.py                   tool distruttivi (destructiveHint + nota [DESTRUCTIVE]), parametro overwrite e rifiuto della sovrascrittura
  config.py / config.json     configurazione: exe_path, timeout di avvio, unita', log (chiavi sconosciute ignorate con avviso)
  constants.py                costanti API SolidWorks (piani, errori, tipi)
  utils/sw_finder.py          trova SLDWORKS.exe e i template
  utils/units.py              conversione unita'
  utils/config_table.py       D1: lettura/controllo della tabella delle configurazioni (CSV/JSON) e piano delle modifiche (puro)
  utils/inertia.py            D7: baricentro e tensore d'inerzia in un sistema di coordinate utente (puro)
  utils/pdf3d.py              D10: lettura della struttura 3D di un PDF (stream PRC/U3D, viste), usata da inspect_export_file
  utils/sw_lang.py            G1: tutto cio' che dipende dalla lingua di SolidWorks (piani standard, grafici, testi delle tavole, cartelle lang)
  automation/                 un mixin per area, riuniti in SolidWorksAutomation (__init__.py)
    base.py                   connessione COM (istanza dell'utente o dedicata con SW_MCP_INSTANCE=dedicated), helper _com, template, piani standard
    documents.py              nuovo/apri/salva/chiudi/elenca; close_document sicuro (save/discard/document), save_document con overwrite
    sketches.py               schizzi e primitive 2D
    features.py               estrusioni, tagli, raccordi, smussi, elenco feature
    modeling_base.py          selezione 3D per coordinate (facce/spigoli/vertici), volume, ricerca feature, elenco entita'
    sketch_constraints.py     quote, relazioni, stato dello schizzo, spline/asola/ellisse/offset/specchia/testo
    modeling.py               rivoluzione, sweep, loft, shell, nervatura, sformo, raccordi/smussi, ripetizioni, Hole Wizard (HOLE_STANDARDS), riferimenti, gestione feature
    drawings.py               messe in tavola: fogli, viste, sezioni, quote, annotazioni, BOM, export (rifiuta DXF/DWG con viste interrotte)
    drawing_layout.py         scala e layout automatici, spazio libero, proprieta' del cartiglio
    drawing_dims.py           lettura e pulizia delle quote, impilamento ISO 129, inventario del layout, tolleranze
    drawing_diam.py           quote Ø dei pezzi di rivoluzione, ingombri, diametri dei fori
    drawing_annot.py          tabella fori, rugosita' generale ISO 1302, nota smussi, aree libere
    drawing_pos.py            catene di quote di posizione dei fori, quote di profilo senza duplicati
    drawing_aux.py            vista ausiliaria senza CreateAuxiliaryViewAt2 (vista nominata AUX_n)
    drawing_formats.py        genera i formati ISO verticali A3-A0 in formats/
    assembly.py               componenti, ripetizioni, specchiatura, accoppiamenti, stato dei vincoli
    assembly_explode.py       viste esplose (vettore libero, entita', radiale), AutoExplode nativo
    assembly_motion.py        gradi di liberta' misurati, move_component, delete_mate con controllo dei DOF
    assembly_analysis.py      linee di esplosione, interferenze, giochi, massa, conteggi, configurazioni
    data_export.py            materiali (.sldmat), massa e inerzie, proprieta', equazioni, configurazioni, export/import, immagini, misure
    simulation.py             SOLIDWORKS Simulation (CosmosWorks): studi statici, vincoli, carichi, mesh, esecuzione con timeout, risultati, PNG
formats/                      formati foglio ISO verticali A0-A3 (.slddrt, "... en" per SolidWorks inglese), versionati
```

## Test
```
tests/test_offline.py              SENZA SolidWorks (anche su Linux): registro e smistamento dei tool (call_tool con SolidWorks finto), sicurezza, PNG, lettori dei file esportati, .sldmat, configurazione, unita'
tests/run_all.py                   regressione completa (un test alla volta) con riepilogo in test_output/regressione_*.md
tests/live_common.py               parti comuni dei test live: percorsi, Client MCP (auto_overwrite), sw_pids, cleanup
tests/test_modeling_live.py        modellazione 3D con volumi calcolati a mano
tests/test_modeling_extra_live.py  gruppo B (raccordo variabile, riferimenti, Hole Wizard, tool base, chiusura sicura); argomenti B1 B4 ... per sezioni
tests/test_drawings_live.py        tool di disegno
tests/test_drawing_quality_live.py qualita' delle tavole (sovrapposizioni, duplicati, versi, tolleranze); QUAL_ONLY=staffa,cuneo per una sola tavola
tests/test_assembly_live.py        assiemi (perno-staffa-boccola-viti, esploso, tavola, interferenze)
tests/test_assembly_extra_live.py  gruppo C (sotto-assiemi, specchiatura, esplosi, accoppiamenti avanzati, DOF); argomenti C1 C5 ..., CX_REUSE=1
tests/test_data_live.py            dati ed export (materiali, massa, equazioni, configurazioni, export/import, misure, immagini)
tests/test_simulation_live.py      simulazione statica (trave, piastra con foro, assieme incollato, torsione)
tests/test_timeout_live.py         fase 5.1: timeout dei tool col thread COM unico (due istanze dedicate, PID chiuso allo scadere)
```
I test `*_live.py` girano solo su Windows con SolidWorks, in un'istanza dedicata e nascosta; l'output va in `test_output/`.
`.github/workflows/test-offline.yml`: GitHub Actions esegue `test_offline.py` e pyflakes (qualunque avviso fa fallire) a ogni push.

## Non versionati (`.gitignore`)
```
.venv/          ambiente Python
test_output/    file generati dai test
scripts_tmp/    strumenti di sviluppo locali: esplorazione della type library (tlb.py, tlbgrep.py, swenum.py), worker con istanza dedicata (worker.py + run.sh + restart_worker.sh), pngtool.py, lingua.py (it/en), contatore di fase (fase2.ps1 + fase2.json), prove (c3p*.py)
```
