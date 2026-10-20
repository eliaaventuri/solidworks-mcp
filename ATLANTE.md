# ATLANTE — mappa dei file

## Documentazione
```
CLAUDE.md                     istruzioni per Claude Code: cosa leggere, regole, test
README.md                     presentazione su GitHub, IN INGLESE: cos'e', funzioni, scenari, installazione, configurazione, limiti
docs/img/                     due immagini del README (tavola d'assieme, mappa di von Mises), ridotte a 1400 px
STATO.md                      stato attuale in breve: cosa funziona, esiti dei test, regole di lavoro, cosa e' aperto
STATO_STORICO.md              diario completo: esiti per blocco, misure, trappole API di SolidWorks, incidenti
LIMITI.md                     elenco di lavoro dei limiti noti per gruppo (A disegni, B modellazione, C assiemi, D dati, E simulazione, F sicurezza)
PIANO_D_E.md                  piano di lavoro completo a fasi fino al server finito + schede tecniche di D, E, B4/C5/C3 (non ancora provato dal vivo)
ATLANTE.md                    questo file
LICENSE                       MIT (copyright dell'autore originale e di Elia)
```

## Server
```
solidworks_mcp_server.py      avvio del server MCP (stdio)
requirements.txt              dipendenze: mcp<2, pywin32
solidworks_mcp/
  server.py                   25 tool base (connessione, documenti, schizzi, feature semplici, utilita'); smistamento di tutte le chiamate con tabelle (BASE_DISPATCH + *_DISPATCH, SPECIAL_HANDLERS), guardia di sovrascrittura
  modeling_tools.py           schemi dei 51 tool di modellazione -> automation/modeling.py, sketch_constraints.py
  drawing_tools.py            schemi dei 38 tool di disegno -> automation/drawings.py e mixin drawing_*
  assembly_tools.py           schemi dei 35 tool di assieme -> automation/assembly*.py
  data_tools.py               schemi dei 30 tool di dati ed export -> automation/data_export.py
  simulation_tools.py         schemi dei 23 tool di simulazione (statica, frequenze, buckling, termico, contatti locali, carichi remoti/cuscinetto, controllo mesh) -> automation/simulation.py
  tools_ext/                  tool aggiunti per lotti: un modulo per lotto (TOOLS, DESTRUCTIVE, OVERWRITE), uniti al gruppo modeling e a safety
    moka.py                   filettatura cosmetica, ripetizione di riempimento, corpi (elenca/elimina/combina/inserisci), lettura feature
    sketch2.py                trim/extend, smusso, ripetizioni e trasformazioni di schizzo, rettangoli, arco tangente, parabola, equazioni, schizzo 3D
    curves.py               lotto curve: elica, elica a passo variabile, curva proiettata, linea di divisione, curva composita, curva per punti
    features2.py            lotto feature avanzate: raccordo a facce/completo/setback, sformo con linea di divisione, cupola, avvolgi, filettatura modellata, flessione
    bodies2.py              lotto corpi 2: sposta/copia, dividi, interseca, scala; ripetizioni guidate da curva/schizzo/tabella
    analysis.py             lotto analisi: box di delimitazione, centro di massa, riferimento accoppiamento, sformo/spessore per faccia, sezione vista, schizzo definito
    manage.py               lotto gestione: verifica geometria, riordino, cartelle, aspetto (colore/trasparenza), modifica e cambio piano schizzo
    sheetmetal.py           lotto lamiera: flangia base, orlo, piega da schizzo, sviluppo, export DXF sviluppo, parametri; sm_edge_flange [~]
    weldments.py            lotto saldature: elenco profili, membro strutturale, taglia/estendi, tappo, distinta di taglio; gusset [~]
    mold.py                 lotto stampi: analisi sottosquadri; linea/superficie divisione e tooling split [~] (Mold Tools non disponibile in SW Student)
    surfaces1.py            lotto superfici 1 (8 tool): estrusione, offset, loft, superficie rigata, cuci, estendi, rifila
    surfaces2.py            lotto superfici 2 (7 tool): offset, rivoluzione, sweep, cuci/unisci, allunga, crea superficie da schizzo
    sketch3.py              lotto schizzo 3 (27 tool): trimming avanzato (corner/inside/outside/closest), entità 2D/3D (centerline, midpoint line, 3point arc, elliptical arc, conic curve, spline avanzate, blocchi)
    features3.py            lotto feature 3 (21 tool): feature avanzate 3D, feature sottili, tagli/sweep dedicati, librerie feature, defeature, rollback bar, scale_body alias
    sheetmetal2.py          lotto lamiera 2 (5 tool): flangia con sweep, taglio normale lamiera, forming tools, break corner / corner trim
    assembly2.py            lotto assiemi 2 (17 tool): ripetizioni componenti (lineari, circolari, guidate, catena), copia con accoppiamenti, mate controller, cinghie, allineamento fori, Pack and Go
    selection.py            lotto selezione e topologia (8 tool): select_by_id, select_by_ray, query_topology_by_criteria, clear_selection, get_active_selection, set_view_orientation, zoom_to_fit, export_labeled_viewport_image
  safety.py                   tool distruttivi (destructiveHint + nota [DESTRUCTIVE]), parametro overwrite e rifiuto della sovrascrittura
  config.py / config.json     configurazione: exe_path, timeout di avvio, unita', log (chiavi sconosciute ignorate con avviso)
  constants.py                costanti API SolidWorks (piani, errori, tipi)
  utils/sw_finder.py          trova SLDWORKS.exe e i template
  utils/units.py              conversione unita'
  utils/config_table.py       D1: lettura/controllo della tabella delle configurazioni (CSV/JSON) e piano delle modifiche (puro)
  utils/inertia.py            D7: baricentro e tensore d'inerzia in un sistema di coordinate utente (puro)
  utils/pdf3d.py              D10: lettura della struttura 3D di un PDF (stream PRC/U3D, viste), usata da inspect_export_file
  utils/matlib.py             D8: cartelle delle librerie dei materiali (preferenza 28), firma per la cache, duplicati, .sldmat minimo (puro)
  utils/edrawings.py          D3: verifica strutturale dei file eDrawings (ZIP, eModel HSF, corpi distinti, anteprima) (puro)
  utils/sw_lang.py            G1: tutto cio' che dipende dalla lingua di SolidWorks (piani standard, grafici, testi delle tavole, cartelle lang)
  automation/                 un mixin per area, riuniti in SolidWorksAutomation (__init__.py)
    base.py                   connessione COM (istanza dell'utente o dedicata con SW_MCP_INSTANCE=dedicated), helper _com, template, piani standard
    documents.py              nuovo/apri/salva/chiudi/elenca; close_document sicuro (save/discard/document), save_document con overwrite
    sketches.py               schizzi e primitive 2D
    features.py               estrusioni, tagli, raccordi, smussi, elenco feature
    modeling_base.py          selezione 3D per coordinate (facce/spigoli/vertici), volume, ricerca feature, elenco entita'
    sketch_constraints.py     quote, relazioni, stato dello schizzo, spline/asola/ellisse/offset/specchia/testo
    modeling.py               rivoluzione, sweep, loft, shell, nervatura, sformo, raccordi/smussi, ripetizioni, Hole Wizard (HOLE_STANDARDS, misure M3..M70, foro generico se manca dal database), move_faces, riferimenti, gestione feature
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
    ext_<lotto>.py            mixin dei lotti di tools_ext (ext_moka, ext_sketch2, ext_curves, ext_surfaces1, ...)
    simulation.py             SOLIDWORKS Simulation (CosmosWorks): studi statici, vincoli, carichi, mesh, esecuzione con timeout, risultati, PNG
formats/                      formati foglio ISO verticali A0-A3 (.slddrt, "... en" per SolidWorks inglese), versionati
```

## Test
```
tests/test_offline.py              SENZA SolidWorks (anche su Linux): registro e smistamento dei tool (call_tool con SolidWorks finto), sicurezza, PNG, lettori dei file esportati, .sldmat, configurazione, unita'
tests/run_all.py                   regressione completa (un test alla volta) con riepilogo in test_output/regressione_*.md
tests/live_common.py               parti comuni dei test live: percorsi, Client MCP (auto_overwrite), sw_pids, cleanup
tests/test_modeling_live.py        modellazione 3D con volumi calcolati a mano
tests/test_modeling_extra_live.py  gruppo B (raccordo variabile, riferimenti, Hole Wizard, tool base, chiusura sicura); B7 fori grandi fino a M70, B8 move_faces; argomenti B1 B4 ... per sezioni
tests/test_drawings_live.py        tool di disegno
tests/test_drawing_quality_live.py qualita' delle tavole (sovrapposizioni, duplicati, versi, tolleranze); QUAL_ONLY=staffa,cuneo per una sola tavola
tests/test_assembly_live.py        assiemi (perno-staffa-boccola-viti, esploso, tavola, interferenze)
tests/test_assembly_extra_live.py  gruppo C (sotto-assiemi, specchiatura, esplosi, accoppiamenti avanzati, DOF); argomenti C1 C5 ..., CX_REUSE=1
tests/test_data_live.py            dati ed export (materiali, massa, equazioni, configurazioni, export/import, misure, immagini)
tests/test_data_extra_live.py      gruppo D (D7 D8 D1 D10 D4 D9 D2 D3), argomenti per sezione: test_data_extra_live.py D7 D1
tests/test_simulation_live.py      simulazione statica (trave, piastra con foro, assieme incollato, torsione)
tests/test_simulation_extra_live.py gruppo E (E3 FOS minimo, E5 frequenze/buckling/termico, E1 contatti locali, E4 carichi remoti/cuscinetto, E2 controllo mesh), argomenti per sezione
tests/test_ext_<lotto>_live.py     un test live per lotto di tools_ext (moka1/moka2, sketch2, curves, ext1, bodies2, features2, analysis, manage, sheetmetal, weldments, mold, surfaces1); argomenti per sezione
tests/test_timeout_live.py         fase 5.1: timeout dei tool col thread COM unico (due istanze dedicate, PID chiuso allo scadere)
```
I test `*_live.py` girano solo su Windows con SolidWorks, in un'istanza dedicata e nascosta; l'output va in `test_output/`.
`.github/workflows/test-offline.yml`: GitHub Actions esegue `test_offline.py` e pyflakes (qualunque avviso fa fallire) a ogni push.

## Non versionati (`.gitignore`)
```
.venv/          ambiente Python
test_output/    file generati dai test
scripts_tmp/    strumenti di sviluppo locali: laboratorio lab.py + labrun.py (istanze dedicate con nome, codice ricaricato a ogni script), api_ref/ (enum swconst, firme dei metodi, catalogo RICERCA_MODELLAZIONE.md), BRIEF_LOTTI.md + notes_<lotto>.md (esiti e trappole di ogni lotto), prove (c3p*.py, sm_probe*.py, ana_p*.py, ecc.), lingua.py (it/en), pngtool.py
```
