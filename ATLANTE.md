# ATLANTE

```
solidworks_mcp_server.py      avvio del server MCP (stdio)
requirements.txt              dipendenze (mcp<2, pywin32, python-dotenv)
solidworks_mcp/
  server.py                   definizione dei 25 tool base (+31 di disegno) e smistamento delle chiamate
  drawing_tools.py            definizioni MCP dei 37 tool disegno + smistamento verso drawings.py
  modeling_tools.py           definizioni MCP dei 50 tool di modellazione (export_model_image e' ora in data_tools) + smistamento verso modeling.py/sketch_constraints.py
  assembly_tools.py           definizioni MCP dei 35 tool di assieme + smistamento verso assembly.py/assembly_analysis.py/assembly_explode.py/assembly_motion.py
  data_tools.py               definizioni MCP dei 30 tool di dati ed export (materiali, massa, proprieta', equazioni, configurazioni, export, import, immagini, misure) + smistamento verso data_export.py
  simulation_tools.py         definizioni MCP dei 18 tool di simulazione statica lineare (blocco 5) + smistamento verso automation/simulation.py
  safety.py                   gruppo B (B6): annotazioni MCP destructiveHint, guardia `overwrite` su salvataggi/esportazioni, nota [DISTRUTTIVO] nelle descrizioni
  config.py / config.json     configurazione (unità, percorsi)
  constants.py                costanti API SolidWorks (piani, errori, tipi)
  automation/
    base.py                   connessione COM, helper _com, template e piani standard
    documents.py              nuovo/apri/salva/chiudi/elenca documenti; close_document SICURO (rifiuta con modifiche non salvate, save/discard/document), save_document con overwrite
    sketches.py               schizzi e primitive 2D
    features.py               estrusioni, tagli, raccordi, smussi, elenco feature
    drawing_layout.py         scala/layout automatici, spazio libero, ordine quote, proprieta' cartiglio
    modeling_base.py          selezione 3D per coordinate (facce/spigoli/vertici), volume, ricerca feature, elenco entita'
    sketch_constraints.py     quote vere, relazioni, stato schizzo, spline/slot/ellisse/offset/specchia/testo
    modeling.py               rivoluzione, sweep, loft, shell, nervatura, sformo, raccordi/smussi, ripetizioni, fori (Hole Wizard: tabella HOLE_STANDARDS iso/ansi_metric/ansi_inch/din/bsi/jis), riferimenti (pose lette dall'API), gestione feature (delete_feature con confirm)
    drawing_dims.py           blocco 4: lettura geometria quote, pulizia (duplicati, smussi->nota), impilamento ISO 129, inventario annotazioni/layout, tolleranze dimensionali
    drawing_diam.py           blocco 4: quote Ø dei pezzi di rivoluzione (da cilindri del modello), ingombri, diametri dei fori, testo dei cerchi fuori dal contorno
    drawing_annot.py          blocco 4: tabella fori con etichette, rugosita' generale, nota smussi, aree libere per annotazioni
    drawing_formats.py        gruppo A (A14): genera i formati ISO verticali A3-A0 (cornice + cartiglio) in formats/ con IDrawingDoc.EditTemplate/SaveFormat
    drawing_aux.py            A16: add_auxiliary_view SENZA CreateAuxiliaryViewAt2 (vista nominata AUX_n + CreateDrawViewFromModelView3, freccia e titolo)
    drawing_pos.py            A17: catene di quote di posizione dei fori (griglie), quote di profilo (spessori, nervature, spigoli inclinati) senza duplicati
    drawings.py               messe in tavola: fogli, viste (anche esplose), sezioni, quote, annotazioni, BOM (+list_bom), export
    assembly.py               assiemi: componenti (selezione per coordinate a tutti i livelli), ripetizioni, specchiatura (istanze o pezzo speculare nuovo), accoppiamenti (larghezza/vite via CreateMateData, limiti), stato vincoli
    assembly_explode.py       gruppo C (C3/C4): vista esplosa (vettore libero, entita', radiale con rotazione), esplosione nativa AutoExplode e euristica dagli accoppiamenti
    assembly_motion.py        gruppo C (C6/C7): gradi di liberta' MISURATI, move_component ridotto ai soli moti consentiti, delete_mate con confronto dei DOF anche a catena
    assembly_analysis.py      assiemi: linee di esplosione, interferenze, giochi, massa, conteggi, configurazioni
    data_export.py            blocco 3: materiali (.sldmat), massa/inerzie, proprieta' personalizzate, equazioni, configurazioni pezzo, export STL/3MF/STEP/IGES/x_t/PDF 3D/eDrawings, immagini, import, misure
    simulation.py             blocco 5: SOLIDWORKS Simulation via CosmosWorks (studi, materiale, vincoli, carichi, mesh, run con timeout, risultati, PNG, contatti)
  utils/sw_finder.py          trova SLDWORKS.exe e template su disco
  utils/units.py              conversione unità
tests/test_modeling_live.py   test live MCP della modellazione 3D (albero, staffa, flangia, loft, sweep...) con volumi calcolati a mano
tests/test_data_live.py       test live MCP del blocco 3 (blocco con foro: materiali, massa, inerzie, equazioni, configurazioni, export/import, misure, cartiglio, immagini); output dx_* in test_output/
tests/test_simulation_live.py   test live MCP del blocco 5 (trave a sbalzo, piastra con foro, assieme incollato, albero in torsione, immagini); output sim_* in test_output/
tests/test_assembly_live.py   test live MCP degli assiemi (perno-staffa-boccola-viti, esploso, tavola A3, interferenze); output in test_output/
tests/test_modeling_extra_live.py  gruppo B: raccordo variabile, piani/CS, convert/up_to/revolve_cut/loft guide/sweep taglio, Hole Wizard (standard, cilindri, piani inclinati), tool base, close_document sicuro; `... B1 B4` esegue solo le sezioni indicate
tests/test_assembly_extra_live.py  gruppo C: sotto-assiemi a 2 livelli, specchiatura con pezzo nuovo, esploso libero/radiale, esplosione automatica, accoppiamenti avanzati, delete_mate, move_component su DOF parziali (213 controlli); `... C1 C5` esegue solo le sezioni indicate, CX_REUSE=1 non ricostruisce i pezzi cx_*
tests/test_drawings_live.py   test live MCP (istanza SW dedicata) dei tool disegno; output in test_output/
tests/test_drawing_quality_live.py  test live di QUALITA' delle tavole (albero, staffa, flangia, perno piccolo, assieme): sovrapposizioni, duplicati, versi, tolleranze; PNG qual_*.png
formats/                      formati foglio ISO verticali A0-A3 (.slddrt) generati da drawing_formats.py (versionati)
test_output/                  file di prova generati dal test (ignorata da git)
scripts_tmp/                  strumenti di sviluppo: tlb.py/tlbgrep.py/swenum.py (esplorano la type library sldworks.tlb), worker.py+run.sh (istanza dedicata persistente), pngtool.py (lettura PNG)
```
