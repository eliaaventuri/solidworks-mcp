# STATO STORICO — diario completo dello sviluppo (fino al 2026-10-12)

Qui c'e' tutto il dettaglio tolto da `STATO.md`: esiti per blocco, misure, trappole API scoperte, incidenti.
Le sezioni sono in ordine cronologico; i numeri dei test in alto possono essere superati da quelli delle sezioni successive.
Per lo stato attuale leggere `STATO.md`.


## Ambiente
- PC Windows 11 **ARM64**; SolidWorks 2026 SP4.1 Student, interfaccia **italiana** (API 34.4.1).
- Python 3.12.10 **x64** (emulato) in `.venv`. Python ARM64 scartato: `cryptography` (dipendenza di `mcp`)
  non ha wheel win-arm64 → serve compilarlo con Rust + MSVC (`link.exe` mancante).
- Dipendenze: `mcp 1.30.0`, `pywin32 312`, `python-dotenv 1.2.4`. `asyncio-compat` tolto (non importato da nessuno).
- Registrato come server `solidworks` in `~/.claude.json` e `%APPDATA%\Claude\claude_desktop_config.json`
  (backup `*.bak-solidworks`).

## Bug trovati e corretti
1. `mcp` 2.x → `AttributeError: 'Server' object has no attribute 'list_tools'`. Fix: `mcp<2`.
2. Template non trovati (nomi italiani `Parte.PRTDOT`, `Assieme.ASMDOT`) → `create_new_part` falliva.
   Fix: `_default_template()` chiede a SolidWorks `GetUserPreferenceStringValue(8/9/10)`.
3. Late binding pywin32: i membri senza argomenti sono proprietà, e un oggetto COM (`CDispatch`) è
   sempre `callable` → chiamarlo dà "Impossibile trovare membro". Fix: helper `_com()` in `base.py`.
   Colpiva `get_document_info`, `list_features` (solo 1 feature), `list_open_documents`.
4. `GetFirstDocument` non esposto in late binding → `list_open_documents` usa `GetDocuments`.
5. `create_sketch` cercava "Front Plane" → in italiano è "Piano frontale". Fix: fallback
   `_select_std_plane()` che prende il 1°/2°/3° `RefPlane` dell'albero.
- Anche `Extension.CreateMassProperty` va letto come proprietà (senza parentesi).

## Test eseguito (client MCP via stdio)
connect, info, list_open_documents, create_new_part, get_document_info, create_sketch(Front),
draw_circle r=30 mm, extrude 15 mm, list_features: tutti SUCCESS.
Volume misurato del cilindro: **42411.5 mm³ = atteso π·30²·15**.

## Non testati / attenzioni
- Non testati: assembly, open/save/close, line/rect/arc/polygon, cut_extrude, fillet, chamfer, set_units, execute_python.
- `close_document` chiude il documento **attivo senza salvare**: rischio di perdere modifiche.
- `execute_python` esegue codice Python arbitrario sul PC.
- `.env` del repo originale contiene una chiave OpenRouter dell'autore (non usata dal server).
- Cartelle `backup_*` e `scripts/history` sono codice vecchio dell'autore, non usato.

## Tool per le messe in tavola (aggiunti 2026-10-09) — 31 tool, totale 56
Codice: `solidworks_mcp/automation/drawings.py` (mixin `DrawingOperations`); definizioni e smistamento in
`solidworks_mcp/drawing_tools.py` (importato da `server.py`). Test: `tests/test_drawings_live.py`
(client MCP stdio) -> **51/51 PASS**, output in `test_output/` (PDF, DXF, DWG, JPG, PNG, .SLDDRW).

### Modalita' istanza dedicata (obbligatoria per i test)
- `SW_MCP_INSTANCE=dedicated` (in `base.py`): lancia un NUOVO `SLDWORKS.exe /r` (SW_MCP_EXE/SW_MCP_ARGS per
  cambiare), recupera l'oggetto COM dalla ROT col moniker `SolidWorks_PID_<pid>`, `Visible=False`.
  Mai `GetActiveObject`/`Dispatch` in questa modalita'. Se l'istanza muore NON si rilancia (errore chiaro).
  `shutdown_dedicated()` = ExitApp + kill del PID esatto. Default invariato (istanza dell'utente).
- Il test verifica PID diverso da quello di Elia, e alla fine uccide solo il proprio PID (0 orfani).
- `Visible` torna True da solo: `_keep_hidden()` lo rimette a False a ogni `get_active_doc`. All'avvio la finestra
  appare brevemente (lancio con SW_SHOWMINNOACTIVATE). PNG/PDF/DXF/DWG/JPG funzionano anche con l'istanza invisibile.
- Incidente iniziale: nei primi probe ho lavorato sull'istanza di Elia (creati/chiusi solo documenti miei:
  Disegno2..6, Parte3->prova_disegno). Un `SaveAs3` finito per errore sul disegno di Elia e' fallito (err 256,
  nessun file scritto). A fine lavoro l'istanza di Elia (PID 12100) non era piu' in esecuzione: nessun evento
  di crash a suo nome nel registro eventi, probabilmente chiusa da lui. I crash 0xc0000374 loggati sono i miei
  (istanze dedicate).

### Esito per tool (tutti PASS nel test live salvo note)
create_drawing, add_standard_views, add_model_view, add_projected_view, add_section_view, add_detail_view,
add_broken_out_section, add_break_view, add_auxiliary_view, add_crop_view, insert_model_dimensions (0 quote:
il pezzo di prova non ha quote nel modello, tool eseguito OK), auto_dimension (7 quote), add_center_marks,
add_note, add_surface_finish, add_datum, add_geometric_tolerance (parziale), add_hole_callout,
set_drawing_properties, list_sheets, add_sheet, activate_sheet, set_sheet_properties, list_drawing_views,
set_view_properties, move_view, delete_view, add_bom (3 righe), add_balloons (2), export_drawing
(pdf/dxf/dwg/jpg/png), save_drawing.

### Trappole API scoperte (SW 2026, late binding)
- `ActiveDoc` cambia se l'utente usa SW: mai `SaveAs` senza verificare il tipo/titolo (i tool controllano tipo 3).
- Foglio: `NewDocument(tpl, 12, w, h)` con formato personalizzato; `Sheet.SetProperties2` ha **8** argomenti
  (paper, template, scale1, scale2, firstAngle, w, h, sameCustom). Cornice/cartiglio ISO: `SetTemplateName(
  lang\italian\sheetformat\a3 - iso.slddrt)` + `ReloadTemplate(True)` (portrait solo per A4; per A3..A0 verticale
  nessun formato). Il template di default e' in terzo diedro: `FirstAngle=True` serve per primo diedro.
- Prima vista creata -> resetta la scala del foglio a 1:1: chiamare `Sheet.SetScale(int,int,True,True)` DOPO la
  prima vista. Viste indipendenti (iso) vanno con `UseSheetScale=True`. `ScaleRatio` e `Position` richiedono
  `VARIANT(VT_ARRAY|VT_R8, (a,b))` (una tupla normale e' letta male).
- Nomi vista del modello: `GetModelViewNames` (0 normal, 1 anteriore, 2 post., 3 sx, 4 dx, 5 sup., 6 inf.,
  7 iso, 8 trimetrica, 9 dimetrica). Tipi vista osservati: 2 sezione, 3 dettaglio, 4 proiettata, 5 ausiliaria, 7 modello.
- Schizzi in vista: `SelectByID2(nome,"DRAWINGVIEW",0,0,0,False,0,NULL,0)` + `ActivateView`; coordinate in spazio
  foglio con origine al CENTRO della vista (`view.Position`), non all'origine del modello. Poi `InsertSketch(True)`.
- `CreateSectionViewAt5(x,y,0,"A",0,NULL,0)`; `CreateDetailViewAt4` 12 arg; `CreateAuxiliaryViewAt2` 7 arg;
  `CreateBreakoutSection(profondita)` con rettangolo selezionato; `view.InsertBreak(0,p1,p2,stile)`; ritaglio:
  `view.Crop` (metodo, con cerchio selezionato); proiettata: `CreateUnfoldedViewAt3(x,y,0,False)` con vista madre
  selezionata (la direzione dipende dalla posizione). `AutoDimension` 5 arg; `AutoInsertCenterMarks` 9 arg
  (1,0,True x7); `InsertGtol`, `InsertDatumTag2`, `GetFirstDisplayDimension5`, `CreateAutoBalloonOptions` sono PROPRIETA'.
- BOM: `view.InsertBomTable4(True,x,y,1,tipo,"Default",template,False,0,False)` con tipo 0 top-level, 1 solo parti,
  2 indentata; template `lang\italian\bom-standard.sldbomtbt` sta in `C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS`,
  non in ProgramData. Il cartiglio italiano legge Description, DrawnBy, DrawnDate, CompanyName, Material, Revision...
  dalle proprieta' del MODELLO (set_drawing_properties scrive su disegno e modello).
- **Crash di SolidWorks**: export DXF/DWG con una vista interrotta in QUALSIASI foglio fa morire SW (RPC 0x800706BE,
  0xc0000374), a volte subito, a volte no. `export_drawing` rifiuta DXF/DWG se trova viste interrotte.
- `Extension.SaveAs(path,0,1,NULL,err,warn)` esporta PDF/DXF/DWG/JPG/PNG dal tipo di estensione.

### Non fatto / limiti
- Sezione allineata o a gradini: non implementata (solo linea retta, orizzontale/verticale/due punti).
- add_geometric_tolerance: il simbolo di caratteristica (posizione, planarita'...) NON viene impostato: i codici di
  `SetFrameSymbols2` non sono stati decifrati (lettere a-z non producono simboli; "<MOD-DIAM>" da' solo il Ø).
  Cornice con valore e riferimenti: OK.
- add_crop_view: solo ritaglio circolare. add_break_view: verificata la creazione (BreakLine), non l'aspetto.
- `flip` della sezione: opzione 1 passata a `CreateSectionViewAt5`, non verificata visivamente.
- Formato verticale per A3..A0: foglio senza cornice (nessun formato ISO portrait fornito da SW).

## Giro 2: qualita' del disegno (2026-10-09) — test 64/64 PASS, 32 tool disegno
Codice nuovo: `solidworks_mcp/automation/drawing_layout.py` (layout, spazio libero, quote, proprieta' cartiglio) +
tool `list_drawing_dimensions`. Immagini di controllo guardate: `test_output/prova_disegno.jpg`, `prova_assieme.png`,
`prova_disegno_foglio2.png`.

| Difetto | Causa trovata | Fix |
|---|---|---|
| Sezione senza tratteggio | le coordinate degli schizzi DENTRO una vista sono in unita' MODELLO (non foglio): a scala != 1:1 la linea era troppo corta e non attraversava il pezzo. (Anche `InsertSketch(True)` dopo la sezione la lascia in modifica.) | linea = estensione vista / scala; niente toggle dello schizzo; test: HATCH presente nel DXF |
| Viste piccole/ammassate | scala fissa e stime dal box del modello (`GetPartBox` ha assi non affidabili) | tutte le viste create a 1:1, misurate con `GetOutline`, scala dalla serie ISO (la maggiore che sta), layout con spazi per le quote (35/40 mm), iso nell'angolo libero in alto a destra, riposizionamento finale dai contorni reali; cartiglio escluso |
| Viste aggiunte che si sovrappongono | posizione fissa | `_free_spot`: ricerca su griglia 5 mm del posto libero piu' vicino (viste, cartiglio, zona distinta); sezione scivola lungo l'asse, se non c'e' posto `RemoveAlignment` + posto libero; dettaglio riduce la scala; se proprio non c'e' spazio il messaggio dice ATTENZIONE |
| Quote sovrapposte/duplicate/su iso | AutoDimension senza ordine; callout foro + quota Ø | mai quote su viste isometriche (errore chiaro); duplicati rimossi (`SelectByID2(FullName,"DIMENSION")`+`DeleteSelection2`; `Select3` non funziona); quote lineari riposizionate in righe fuori dal contorno (passo 7,5 mm); Ø non spostati |
| "ERRORE:xxx" nel cartiglio | proprieta' referenziate dal formato mancanti | `create_drawing` crea le 16 proprieta' sul disegno e sul modello (salva il modello) e fa un export DXF temporaneo per scovare altri `ERRORE:<nome>`; Weight = `SW-Mass@<file>` solo sul modello (il formato lo mostra 2 volte) |
| N. disegno "Disegno1" | il formato legge il nome file | `create_drawing(save_as=...)`: il nome file diventa il N. disegno |

Nuovi controlli nel test: sovrapposizioni fra contorni viste / cartiglio / zona distinta / bordo foglio, copertura del foglio,
quote duplicate, quote su isometriche, quote dentro altre viste, assenza di "ERRORE", titolo/numero/peso e tratteggio
letti dal DXF esportato (il DXF e' testo ASCII: e' il modo per leggere il cartiglio senza librerie PDF).
Trappole: `View.Position` non e' il centro del contorno (dettaglio): `_set_pos` compensa; `GetOutline` include ~6 mm di margine
per lato; il titolo nel DXF e' spezzato su piu' righe; i Ø di AutoDimension attraversano la vista (lasciati cosi'); orientamento
delle quote lineari non deducibile dall'API (si usa posizione+valore). Limiti: il layout presuppone un'iso nell'angolo; con
molte viste aggiunte il foglio puo' riempirsi (poi i tool avvisano).

## Blocco 1 — modellazione 3D (2026-10-09)
Codice: `automation/modeling_base.py` (selezione per coordinate, volume, feature), `automation/sketch_constraints.py` (quote, relazioni,
stato schizzo, entita' extra), `automation/modeling.py` (feature, ripetizioni, fori, riferimenti, gestione), `solidworks_mcp/modeling_tools.py`
(51 tool MCP + smistamento, agganciato in `server.py`). I `draw_*` restituiscono `entity_id` (+ id dei punti). `fillet_edges`/`chamfer_edges`
accettano `edge_points=[[x,y,z],..]` e selezionano da soli. Test: `tests/test_modeling_live.py` (istanza dedicata, 0 processi orfani).

### Esito (vedi riepilogo in fondo al log `test_output/modeling_run.log`)
Volumi misurati (CreateMassProperty) vs calcolo a mano, tutti sotto 0,01 % salvo loft (0,004 %): albero rivoluzione 69704.09 (atteso 69704.09),
cava 916.87 (916.87), staffa 28200 -> +nervatura 30450 -> 4 fori lamati 29463.54 -> raccordo 28390.53 -> larghezza 60: 33815.93 -> specchiato 67631.86,
flangia 99118.18 (99118.18), tronco di cono loft 21990.4 (21991.1), tubo sweep 7965.19 (7965.19), blocco sformato 26531.33 (prismoide 26531.33).
Schizzo albero "completamente definito"; modifica quote (D4@Schizzo1 60->70, larghezza staffa, Ø flangia) con variazione di volume attesa;
per albero/staffa/flangia disegno A3 con quote del modello importate; immagini guardate: albero, staffa, flangia, sweep.

### Trappole API scoperte (SW 2026, late binding)
- **Piani standard di QUESTO template**: "Piano frontale" = 1o RefPlane ha normale X (u->Y, v->Z), "superiore" normale Z, "destro" normale Y.
  Non fidarsi dei nomi: `create_sketch` restituisce `sketch_x_axis/sketch_y_axis/sketch_normal` (modello = origine + u*x + v*y).
- Collisione di nomi fra mixin: `DrawingOperations._mm` e `_m` esistono gia' (firma diversa): i miei helper sono `_mmu`. Controllare sempre i nomi.
- `CreateMassProperty` da' 0 dopo aprire/chiudere uno schizzo vuoto finche' non si ricostruisce: `_volume_m3` ricostruisce e rilegge.
- Specchia CORPO: `InsertMirrorFeature2(True,...)` restituisce None se il corpo e' selezionato con Mark 1: serve **Mark 256** (piano Mark 2, feature Mark 1).
- Ripetizione lineare: se un'istanza cade fuori dal corpo SW la salta SENZA errore: il tool confronta il volume con (n-1) x effetto della feature
  seme (`_seed_effect`) e riprova con direzioni invertite.
- Punto su uno spigolo fra due facce (es. (60,30,6)) e' ambiguo per le facce: scegliere punti interni alla faccia.
- Foro guidato: `HoleWizard5` posiziona nel punto di pick; filettato cieco = zona filettata a Ø nominale per thread_depth poi Ø punta + cono 118
  (volume 784.34 mm3 per M8 prof. 16); filettato passante = solo Ø punta.
- Quote: se lo schizzo e' gia' definito la nuova quota diventa "guidata" (riferimento) col valore attuale: il tool ora lo segnala come errore.
- `insert_model_dimensions` importava 0 quote: le quote degli schizzi assorbiti dalle feature sono "nascoste", serve
  `HiddenFeatureDims=True` (ora default). Con quote importate il layout resta disordinato (smusso 45 gradi molto grande nell'albero).
- `create_sketch` aveva `enum` Front/Top/Right nello schema MCP: tolto (accetta anche "Piano1").
- `export_model_image`: viste standard con `ShowNamedView2("", id)` (7 = isometrica); il nome italiano non funzionava.

### Non fatto / limiti
- Hole Wizard: (risolto nel gruppo B, vedi "Limiti gruppo B": 6 standard, cilindri e piani inclinati; resta la posizione angolare sulle facce cilindriche).
- (risolto nel gruppo B: fillet_variable_radius, create_coordinate_system, piano per 3 punti/inclinato, convert_entities, up_to_surface, revolve_cut, loft con guide e sweep di taglio sono ora verificati con volumi.)
- Sketch fully-defined verificato su albero e flangia; centerline e' conteggiata come definita dopo relazioni orizzontale+coincidente.

Esito finale blocco 1: tests/test_modeling_live.py **175/175 PASS**; tests/test_drawings_live.py **64/64 PASS** (nessuna regressione); 0 processi SLDWORKS orfani.

## Blocco 2 — assiemi (2026-10-09)
Codice: `automation/assembly.py` (componenti, ripetizioni, specchiatura, accoppiamenti, stato vincoli, spostamento), `automation/assembly_analysis.py`
(vista esplosa, interferenze, giochi, massa, conteggi, configurazioni), `solidworks_mcp/assembly_tools.py` (34 tool + smistamento, agganciato in `server.py`).
Disegni: `exploded=True` in `add_model_view` / `add_standard_views` (solo viste pittoriche) e in `set_view_properties`; nuovo tool `list_bom`
(legge righe e quantita' della distinta). `export_model_image` ora accetta anche assiemi. Totale tool: **143** (108 + 34 + list_bom).
Test: `tests/test_assembly_live.py` (client MCP stdio, istanza dedicata, solo PID proprio chiuso); output in `test_output/` (asm_*.SLDPRT/SLDASM,
asm_main.SLDDRW, asm_main_tavola.pdf/png/dxf, asm_main.png, asm_main_esploso.png, log `assembly_run.log`). Il test dura ~15 minuti (ogni chiamata MCP e' lenta).

### Esito (numeri misurati dal test)
- Assieme perno-staffa-boccola-viti: 4 file, 9 istanze, 9 accoppiamenti (concentrico x2, coincidente x4 incl. assi, parallelo x2, distanza, angolo) ->
  `get_assembly_status`: completamente vincolato. Boccola a (-3,0,0) mm, perno a (-12,0,0) mm con asse sull'asse del foro (scarto < 1e-6 m),
  6 viti a r=30,000 mm passo 60 gradi (ripetizione circolare di componenti). Modifica distanza 5->8 mm: perno a -15 mm; poi 5 mm.
- Massa assieme 0,563505 kg = somma dei componenti (scarto 3e-16); staffa 0,46952 + boccola 0,02511 + perno 0,04378 + 6 x 0,004182 kg.
- Interferenze: 0 nell'assieme corretto; 1 nel caso apposta (perno d24 nel foro d20, 10 mm): 1382,47 mm3 contro 1382,30 atteso (0,01 %).
- Gioco perno-staffa 4,000 mm (foro d20, gambo d12).
- Vista esplosa a 3 passi (perno -60 mm X, boccola -30 mm X, 6 viti +40 mm X); compressione riporta il perno a -12 mm.
- Tavola A3: frontale + isometrica ESPLOSA, distinta 4 righe (staffa 1, boccola 1, perno 1, vite 6), 4 palloncini = 4 componenti distinti,
  cartiglio senza "ERRORE" (peso 563.51), PDF 51 KB, PNG 47 KB, DXF. Immagini guardate: asm_main.png, asm_main_esploso.png, asm_main_tavola.png.
- Ripetizione lineare (2 istanze), ripetizione guidata da ripetizione di feature (3 istanze su 4 fori), specchiatura (istanza), sostituzione,
  soppressione, nascondi/mostra, elimina, apri componente + activate_document, configurazioni, auto-esplosione: nel test.

### Trappole API scoperte (SW 2026, late binding) — dettagli anche nei docstring dei moduli
- `AddComponent5` da' None se il file non e' caricato: prima `OpenDoc6` silenzioso, poi `ActivateDoc3` sull'assieme. X,Y,Z = centro del BOX, non origine:
  poi si imposta `Component2.Transform2`. `IMathUtility.CreateTransform` solo via `_oleobj_.Invoke(dispid,0,DISPATCH_METHOD,True,array)`.
  Array 16 double: righe 3x3 = immagini degli assi (p' = p*R + t).
- `AddMate5`: errore 1 = nessun errore (0 = sconosciuto). Concentrico fra due assi di riferimento (datum) FALLISCE -> si usa il coincidente.
  Facce cilindriche, piani (`FeatureByName(...).Select2`) funzionano. Punti delle facce: coordinate dell'assieme, ma `GetBodies2` da' lo spazio del PEZZO
  (si usa l'inversa della trasformazione). I punti vanno ricalcolati dopo ogni accoppiamento (il componente si sposta).
- `GetRemainingDOFs` da' sempre "non disponibile": i gradi di liberta' sono MISURATI muovendo il componente con `SetTransformAndSolve2` (0,5 mm / 3 gradi) e ripristinando.
- Ripetizione di componenti: `FeatureCircularPattern5` con seme Mark 1 e asse Mark 2 (NON 4/1); lineare seme Mark 1, direzione Mark 2; Number2 >= 1.
  Ripetizione guidata: `FeatureManager.InsertDerivedPattern()` (non restituisce la feature), seme Mark 2 + ripetizione Mark 4.
  Specchiatura: `MirrorComponents3` con componenti "da istanziare" (restituisce tupla vuota, si controllano i nuovi componenti).
- Esploso: `AssemblyDoc.CreateExplodedView` e' una PROPRIETA'; `Configuration.AddExplodeStep2(...)` vuole i componenti con Mark 1 (Mark 0 -> errore 3 e passo vuoto);
  direzione solo X/Y/Z dell'assieme (+ inverti). Con l'esploso attivo `Transform2`/`GetBox` sono quelli esplosi: `GetSpecificTransform(True)` o richiudere.
  Nel disegno: `IView.ShowExploded(True)` dopo la creazione della vista, PRIMA di misurarla; l'assieme va salvato dopo aver creato l'esploso.
- Interferenze: `doc.InterferenceDetectionManager` (proprieta'), `GetInterferences` proprieta', `Interference.Volume` in m3, `Done()` a fine uso.
  Gioco: `Extension.CreateMeasure`, `Calculate` e' proprieta' (la lettura calcola), distanza -1 = contatto/sovrapposizione.
- Sostituzione di un componente con `replace_all=False` sostituisce comunque anche le istanze di una ripetizione (seguono il seme).
- `GetModelDoc2`, `GetErrorCode2`, `GetFirstSubFeature`... sono proprieta': usare `_com`. Distinta: `BomFeat` -> `GetSpecificFeature2.GetTableAnnotations[0].Text2(r,c,False)`.
- Lanciare il test due volte in parallelo (anche con `&` in shell) apre due istanze SW e si pesta i piedi: un solo run alla volta.

### Non fatto / limiti
- Linee di esplosione (route lines): non implementate. `auto_explode` e' un'euristica propria (un passo per componente lungo un asse), non l'AutoExplode nativo.
- Esplosione solo lungo X/Y/Z dell'assieme (niente direzioni libere, radiale, solo rotazione non testata).
- Accoppiamenti avanzati (limite distanza/angolo, ingranaggio, vite, larghezza, simmetrico, tangente, blocco): implementati ma NON verificati dal test.
- Sotto-assiemi: le entita' per coordinate cercano solo nei componenti di primo livello.
- Specchiatura: solo istanze (nessun pezzo speculare nuovo); orientamento `orientation` da provare (0 default).
- `move_component` con vincoli: verificato su componente completamente vincolato (non si muove) e su componente libero; trascinamento con rotazione solo su libero.

Esito finale blocco 2: `tests/test_assembly_live.py` **113/113 PASS**; `tests/test_drawings_live.py` **64/64 PASS**; `tests/test_modeling_live.py` **175/175 PASS**; 0 processi SLDWORKS orfani.

## Blocco 3 — dati ed export (2026-10-09)
Codice: `automation/data_export.py` (mixin `DataExportOperations`, messo PRIMA degli altri nella MRO), `solidworks_mcp/data_tools.py` (30 tool + smistamento, agganciato in `server.py`).
`export_model_image` e' stato spostato da `modeling.py`/`modeling_tools.py` in `data_export.py` (stessa firma + `style`, `width`, `height`, `hide_reference`, `white_background`, `zoom_to_fit`).
Totale tool: **172** (143 - 1 spostato + 30). Test: `tests/test_data_live.py` (client MCP stdio, istanza dedicata, solo PID proprio chiuso, 0 orfani) -> **159/159 PASS**, ~13 minuti; log `test_output/data_run.log`, file `test_output/dx_*`.

### Tool (30)
Materiali: `list_materials`, `assign_material`, `get_material`, `link_material_to_title_block`. Massa: `get_part_mass_properties`, `set_mass_override`.
Proprieta': `list_/get_/set_/delete_custom_property`. Equazioni: `list_equations`, `set_global_variable`, `delete_global_variable`, `add_equation`, `update_equation`,
`delete_equation`, `evaluate_equations`. Configurazioni: `list_/add_/activate_/delete_part_configuration`, `set_configuration_dimension`, `set_configuration_suppression`.
Export/import: `export_model`, `inspect_export_file`, `import_model`, `export_model_image`. Misure: `measure_entities`, `measure_face`, `get_bounding_box`.
`get_mass_properties` e `set_material` (blocco 1) restano com'erano.

### Esito (numeri misurati)
- Blocco 80x50x30 (120000 mm3). AISI 304: massa 0,960000 kg = 120000 mm3 x 8000 kg/m3 (densita' letta dal .sldmat). Lega 6061 -> rapporto 0,33750 (atteso 0,33750); ABS generico -> 0,12750 (atteso 0,12750). Materiale solo su un corpo: 0,96 kg.
- Baricentro (15,0,0) mm; inerzie al baricentro 7,12e-4 / 2,72e-4 / 5,84e-4 kg*m2 = formule m/12(b2+c2) (scarto < 0,01 %); all'origine = Huygens-Steiner; assi principali ortonormali.
- Variabile "lunghezza" + equazione `"D1@Estrusione-Estrusione1" = "lunghezza" * 2`: 15 -> 30 mm, 20 -> 40 mm; volume 160000 mm3, massa 1,28 kg. Equazioni con variabile/quota inesistente vengono rifiutate.
- Configurazioni: Default 116607,26 mm3, Lunga (60 mm) 233214,53, Pieno (foro soppresso solo li') 120000,00 - verificati attivandole una a una.
- STL 160 triangoli (fine) / 80 (coarse) / 304 (custom 0,02 mm, 5 gradi), box 30,000012 x 80 x 50 mm (scarto 0 dal box del modello); 3MF unita' millimetre; STEP AP214 e AP203 con MANIFOLD_SOLID_BREP; IGES, Parasolid x_t/x_b, PDF 3D (PRC), eDrawings .eprt.
- Reimport: STEP 0,00005 %, x_t 0,00000 %, IGES 0,00009 %, STL 0,0146 % di scarto sul volume; box 30x80x50.
- Misure: distanza facce parallele 30,000 mm, angolo 90,000, distanza 80,000, foro Ø12,000 (`measure_entities` e `measure_face`), area faccia 80x50-pi*36 = 3886,9 mm2, diagonale 99,0 mm.
- Cartiglio: Material = `"SW-Material@dx_blocco.SLDPRT"` -> nel DXF compare "AISI 304"; dopo il cambio "Lega 6061" e nessun "ERRORE".
- Immagini guardate: `dx_img_iso_nascosta.png`, `dx_img_ref_visibile.png` (controllo: con i riferimenti visibili il Piano1 si vede bene), `dx_img_s1.png`; nelle immagini con `hide_reference` 0 pixel azzurri (5 immagini: iso, front linee nascoste, top filo, iso ombreggiata) e poi i piani tornano visibili.

### Trappole API scoperte (SW 2026, late binding) — dettagli nei docstring del modulo
- **Materiali**: `.sldmat` = XML UTF-16 in `lang\italian\sldmaterials` (3 file, 474 materiali, 29 categorie; "PLA" NON c'e'; "ABS" e' ambiguo: `ABS generico` / `ABS PC`). Pezzo: `SetMaterialPropertyName2(cfg, percorso_db, nome)`.
  Corpo: `Body2.SetMaterialProperty(cfg, "solidworks materials" (senza percorso!), nome)` restituisce True ma NON fa nulla se il corpo non e' stato "toccato" prima con `CreateMassProperty2().SelectedItems=[corpo]`
  (ripetere la chiamata non serve; i metodi `...PropertyName2` non esistono su Body2). Con un materiale sul solo corpo la massa del PEZZO intero resta quella del materiale del pezzo: usare la massa del corpo.
- Dopo una ricostruzione i puntatori ai corpi (`GetBodies2`) sono vecchi (`Name` = ""): ripescarli. Anche `SelectedItems` lascia `Name` vuoto.
- **Massa**: `IMassProperty2` ha `PrincipalAxesOfInertia(i)`, `GetMomentOfInertia(0 baricentro | 1 origine)` (9 valori, kg*m2); NON ha AddBodies/OverrideMass. La sovrascrittura vive su `CreateMassProperty` (v1): `SetAssignedMassProp` via `_oleobj_.Invoke`, si toglie con `OverrideMass = False`.
- **Proprieta'**: `Get6` con VARIANT BYREF BSTR/BOOL (valore/espressione e risolto; SW-Mass risolto e' in grammi). `GetAll3` non e' usabile in late binding.
- **Equazioni**: modificare con la proprieta' indicizzata `em.Equation(i, testo)`: `SetEquationAndConfigurationOption` restituisce -1 e non cambia nulla. `Add2` restituisce -1 se quota/variabile non esistono. `em.Status` vale 1 anche a modello sano.
- **Configurazioni**: `ShowConfiguration2` e' del DOC; `Feature` resta legata alla config in cui e' stata trovata (ripescarla e passare sempre i nomi); `SetSystemValue3` 0 = ok (fallisce su quote guidate da equazione). `IsSuppressed2` va letto con la config attiva.
- **Export**: le opzioni sono PREFERENZE UTENTE globali (registro di SolidWorks: restano anche all'utente): `export_model` le imposta e le RIPRISTINA. STL: int 78 (1/2/3), 211 unita', toggle 69 binario, 71 non traslare, double 2/3 deviazione/angolo (rad). STEP: int 75 = 203/214; **242 viene accettato ma il file e' AP203**.
  IGES: l'estensione `.iges` non e' riconosciuta (si scrive `.igs`). PDF 3D: `GetExportFileData(1).ExportAs3D=True` (il PDF normale non e' 3D). Con la preferenza 142 (swStepExportPreference) = 2 lo STEP contiene solo curve (wireframe): lasciarla a 0.
- **Immagini**: `Extension.SaveAs(png)` da' sempre 2389x1698 ed e' ben centrata. `doc.SaveBMP(path,w,h)` rispetta la dimensione ma centra male (+7,8 % in x): scartata. La risoluzione si ottiene riducendo il PNG nativo in Python puro (decodifica ~5 s + box filter; solo riduzione, mai ingrandimento; bande col colore d'angolo se le proporzioni differiscono).
  I toggle `swDisplayPlanes/Axes/Origins/Sketches` dell'app NON agiscono sulla vista: si nascondono le feature (`Select2` + `BlankRefGeom`/`BlankSketch`, schizzi assorbiti = sotto-feature via `GetFirstSubFeature`) e si ripristinano quelle che erano visibili (`Feature.Visible`: 1 nascosto, 2 mostrato).
  Sfondo bianco: int 305 = 0 + int 99 = 0xFFFFFF (ripristinati). Stile: `ActiveView.DisplayMode` 1 filo, 2 linee nascoste, 3 nascoste in grigio, 4 ombreggiato, 5 con spigoli. I PNG di wireframe/linee nascoste sono palette/grigio: `_read_png` li converte.
- **Import**: `GetImportFileData` e' None per STL/x_t (si passa NULL); titolo del documento importato imprevedibile (`dx_ap214.SLDPRT`, `dx_b1`...): si usa l'oggetto restituito da `LoadFile4`; preferenze STL 208 (tipo: 0 grafica, 1 superficie, 2 solido), 210 (unita').
- **Misure**: `CreateMeasure().Calculate` e' PROPRIETA'; -1 = n.a.; `Angle` in radianti; `Body2.GetBodyBox` e' approssimato (0,1 mm), `GetExtremePoint(dir)` e' esatto.
- **Preferenze dell'utente toccate durante lo sviluppo**: le sperimentazioni (istanze dedicate chiuse con ExitApp) hanno scritto nel registro STL qualita' (78 = 2 fine), tipo import STL (208 = 2 solido), STEP 142/75, IGES 83, sfondo (305/99) e toggle piani/assi/origini/schizzi.
  75/142/83/305/99 sono stati riportati ai valori letti all'inizio (203, 0, 0, 3, 0xD2C8C3); di 78 e 208 non si conoscono gli originali (probabile coarse e superficie/grafica): da controllare in Opzioni > Esporta/Importa se Elia nota differenze.

### Non fatto / limiti
- **Design table (tabella dati in Excel)**: NON fatta. Excel non e' installato (nessun `Excel.Application` nel registro) e design table / family table passano da Excel: non sarebbe verificabile. Alternativa robusta e testata: `add_part_configuration` + `set_configuration_dimension` + `set_configuration_suppression`.
- AP242 non ottenibile (il file scritto e' AP203); eDrawings `.eprt` scritto ma non aperto/verificato (solo dimensione > 0); PDF 3D verificato solo come presenza di PRC/3D nel PDF.
- Immagini: nessun rendering PhotoView/Visualize; risoluzione massima = nativa 2389x1698; `hide_reference` agisce sul documento attivo (nei componenti di un assieme restano i riferimenti dei pezzi eventualmente visibili); assieme: export STL/STEP, `get_bounding_box` e immagini previsti ma NON testati.
- `get_part_mass_properties`: tensore solo nel sistema di coordinate del modello (niente sistemi di coordinate utente).
- Materiali personalizzati (.sldmat dell'utente fuori dalla cartella standard) non letti; i 3 file standard si'.
- Import: opzioni avanzate (riparazione, unione facce) non esposte.

Esito finale blocco 3: `tests/test_data_live.py` **159/159 PASS**; `tests/test_drawings_live.py` **64/64 PASS**; `tests/test_modeling_live.py` **175/175 PASS**; `tests/test_assembly_live.py` **113/113 PASS**; 0 processi SLDWORKS orfani (resta solo `sldworks_fs.exe` dell'utente, non toccato).

## Blocco 4 — rifiniture disegni (2026-10-10)

Obiettivo: tavole presentabili (ISO/UNI, primo diedro, quote ISO 129). Tool totali: **177** (172 + 5 nuovi: `arrange_drawing_dimensions`,
`get_drawing_layout`, `set_dimension_tolerance`, `add_hole_table`, `add_general_roughness`). Nuovi file: `automation/drawing_dims.py`,
`automation/drawing_diam.py`, `automation/drawing_annot.py`, `tests/test_drawing_quality_live.py`.

### Esito (numeri)
- `tests/test_drawing_quality_live.py`: **68/68 PASS** (albero, staffa, flangia, perno piccolo, assieme; log `test_output/quality_run.log`,
  immagini `test_output/qual_*.png`, prima/dopo con `albero_disegno.png`, `staffa_disegno.png`, `flangia_disegno.png`). Controlli automatici su
  `get_drawing_layout`: 0 sovrapposizioni fra riquadri (quote, note, tolleranze, tabelle, viste, cartiglio, distinta), tutto nel foglio, 0 duplicati
  (stessi punti di riferimento, o stesso diametro due volte), verso delle quote (orizzontali con testo a 0 gradi, verticali a 90 gradi, tutte FUORI dal
  contorno, ad almeno 7 mm), simboli delle tolleranze geometriche letti dal tool, foglio A4/A3 e scala ISO scelti da soli.
- Regressioni (da `test_output/*_run.log`): `test_drawings_live.py` **64/64 PASS**, `test_modeling_live.py` **175/175 PASS**, `test_assembly_live.py` **113/113 PASS**, `test_data_live.py` **159/159 PASS**; 0 processi SLDWORKS orfani, istanza dell'utente intatta. Un controllo esistente e' stato cambiato: in `test_data_live.py` il numero esatto dei tool passa da 172 a 177 (+5 tool di tavola). Alla prima esecuzione `test_drawings_live.py` dava 63/64 ('quote non dentro altre viste'): `auto_dimension` usava ancora il vecchio riordino; ora usa lo stesso motore ISO 129 e il controllo e' tornato verde senza modificarlo.

### Cosa fa ora (per punto del compito)
1. **Quote**: `insert_model_dimensions` (arrange=True di default) e `arrange_drawing_dimensions`: lettura della geometria vera di ogni quota
   (`GetDisplayData`), toglie duplicati (anche fra viste) e quote di smusso (diventano la nota "SMUSSI NON QUOTATI: 1x45, ..."), **sostituisce le quote
   radiali importate degli alberi con quote lineari Ø** (cilindri del modello proiettati con `ModelToViewTransform`, selezione delle due silhouette),
   aggiunge ingombri (larghezza/altezza, senza duplicare un valore gia' quotato in un'altra vista) e diametri dei fori ("6x Ø9"), impila: orizzontali sopra/sotto,
   verticali a destra/sinistra, passo 8 mm, prima riga a 10 mm dal contorno, dalla piu' corta alla piu' lunga, senza incroci fra richiami e linee di quota;
   le quote Ø/R dei cerchi hanno il testo FUORI dal contorno lungo raggi liberi (linea di quota radiale con freccia sul cerchio); la nota smussi e' in area libera.
2. **Scala/foglio automatici** (`paper_size="auto"` + `add_standard_views`): A4 poi A3 in scala >= 1:1 (anche 2:1, 5:1: perno Ø6 = 5:1 su A4), poi A4/A3 fino a 1:2,
   poi A2..A0; massimo 10:1; le viste pittoriche scendono al massimo di UN gradino ISO sotto la scala del foglio.
3. **Tolleranza geometrica completa** (`add_geometric_tolerance`): 14 caratteristiche (planarita', rettilineita', circolarita', cilindricita', parallelismo,
   perpendicolarita', inclinazione, posizione, concentricita', simmetria, oscillazione circolare/totale, profilo di linea/superficie), Ø, modificatori M/L/S/P,
   fino a 3 riferimenti, riquadri composti (extra_frames), aggancio con richiamo allo spigolo oppure posizione in area libera. Verificato guardando il rendering.
4. **Sezioni**: `add_section_view` con `orientation="stepped"|"aligned"` (poligonale in `points`); vista allineata alla madre se c'e' posto; i dettagli
   ora rispettano davvero la scala richiesta e il cerchio e' visibile sulla vista madre; le viste nuove si collocano evitando le annotazioni gia' presenti.
5. **Linee di esplosione**: NON fatte (vedi sotto).
6. **Annotazioni**: `add_hole_table` (tabella TAG/X/Y/Ø con etichette A1.. sui fori, orizzontale o verticale a seconda dello spazio), `add_general_roughness`
   (Ra con simbolo fra parentesi), `set_dimension_tolerance` (simmetrica, bilaterale, limiti, min/max, classi ISO H7/g6, precisione).

### Trappole scoperte (SW 2026) — non ricercarle di nuovo
- Cancellare una quota di disegno: `SelectByID2(dd.GetNameForSelection, "DIMENSION")` (NON FullName). `IDimension.Value` e' nell'unita' del documento (mm), non in metri.
- Silhouette dei cilindri: `SelectByID2("", "SILEDGE", x, y)` e tipo selezione 46 (non "EDGE"); la zona sensibile e' spostata di 0,1-0,5 mm VERSO L'ESTERNO
  del raggio geometrico (provare scarti 0,15-0,5 mm); la prima selezione dopo una pausa puo' fallire (si ripete). Selezionare con tipo sbagliato restituisce True
  ma seleziona vista (12) o faccia (2): controllare `GetSelectedObjectType3`.
- `AddDimension2` con due silhouette parallele da' il diametro; `dd.SetText(1, "6x <MOD-DIAM>")` = prefisso (Ø automatico anche per i cerchi); colore nero: `GetAnnotation.Color = 0`.
- Posizione di una quota: `SetPosition2` sposta il TESTO; la linea di quota ci passa attraverso e si allunga fino al testo, quindi bisogna spostare anche la coordinata LUNGO
  l'asse (testo al centro dell'intervallo, o fuori a destra/sopra se non ci sta). Il testo e' centrato sul punto dopo la rilettura (iterare 2-4 volte).
- Tolleranza geometrica: `IGtol.SetFrameSymbols2(frame, "<GTOL-FLAT>", dia, "<MOD-MMC>", False, "", "", "", "")` — i nomi sono quelli di `lang/english/gtol97.sym`
  nel formato `<GTOL-NOME>` (FLAT, STRAIGHT, CIRC, CYL, PARA, PERP, ANGULAR, POSI, CONC, SYMMETRY, SRUN, TRUN, LPROF, SPROF); caratteri singoli, "FLAT", "<FLAT>" NON
  producono il simbolo. Modificatori: `<MOD-MMC>`, `<MOD-LMC>`, `<MOD-FMC>`, `<MOD-PTZ>`. Quelli sui riferimenti (DatumMC) non vengono mostrati. `GetSymName/GetSymDesc` restano
  vuoti (non servono). La geometria letta (`GetLineAtIndex`) NON si aggiorna dopo creazione/spostamento nella stessa chiamata: per il posizionamento si usa una misura analitica
  (7 mm per riquadro; la posizione = angolo in alto a sinistra).
- `IView.GetPolylines7` e `GetVisibleEntities2` con argomenti per riferimento BLOCCANO il worker (ucciso per PID). Tabelle: `Extension.InsertGeneralTableAnnotation(False, x, y, 1, "", righe, colonne)`;
  testo cella solo con `t._oleobj_.Invoke(131108, 0, DISPATCH_PROPERTYPUT, 0, riga, colonna, testo)`; larghezze con `SetColumnWidth(i, w, 0)`.
- `IView.ScaleRatio` e' ignorata nelle viste di dettaglio: usare `ScaleDecimal`. `InsertSurfaceFinishSymbol3` senza richiamo ignora X,Y: serve `GetAnnotation.SetPosition2`.
- Il formato ISO A4 di SolidWorks (`a4 - iso.slddrt`) e' VERTICALE (210x297): `_pick_paper`/`_apply_paper` ora pianificano l'A4 in verticale (prima il layout veniva calcolato in orizzontale e poi
  il foglio diventava verticale: viste sul cartiglio).
- Scansione delle annotazioni del foglio: ~30 ms per annotazione (il formato ha 64 note): `_dq_annotations` scarta per posizione le note del cartiglio e mette in cache per numero di annotazioni
  (`_sheet_ann_cache`); senza cache un solo `add_*` impiegava 6-10 s e una catena di chiamate superava i 2 minuti del worker.
- `FaceInSurfaceSense()`: True per fori/alesaggi, False per perni (per scegliere i fori concavi).
- Testo delle tabelle: 5 mm di default; le colonne vanno larghe 18-21 mm per numeri tipo "-107.50" (altrimenti il testo va a capo).

### Cose NON fatte / limiti dichiarati (onesti)
- **Linee di esplosione** nelle tavole d'assieme: non implementate. Strada individuata ma non percorsa: `ISketchManager.InsertExplodeLineSketch` + selezione di due entita' circolari delle componenti
  (in coordinate dello stato ESPLOSO) + `ISketch.InsertRouteLine`; la disposizione esplosa si legge dal modello e la selezione per coordinate in stato esploso non e' stata verificata.
- Quote degli elementi non cilindrici/non importati dal modello (cave, linguette): restano quelle dello schizzo; nell'albero la cava e' quotata solo in profondita' (4) e non in lunghezza/larghezza.
- Le quote di raggio (R10 della staffa) hanno la linea di richiamo che attraversa il pezzo; le etichette dei fori (A1...) possono toccare i simboli dei fori; sulla staffa le viste sono in 1:2 (A3):
  l'A3 non permette 1:1 con il cartiglio da 195x80 mm a destra.
- `set_dimension_tolerance` scrive sulla quota del MODELLO (non solo del disegno) per le quote importate: il modello non viene salvato dai test, ma e' modificato in memoria.
- Quote angolari: il codice contiene un correttore dell'arco (`_dq_fix_angular`) usato solo se compaiono quote angolari non di smusso; non c'e' un caso di prova nei test (le angolari dei test sono smussi, tolte).
- Tavola d'assieme: nessuna quota (solo viste, distinta, palloncini); i palloncini non sono controllati dal test di sovrapposizione (non sono nell'inventario); "N. DISEGNO" del cartiglio sfora con nomi lunghi.
- Giudizio visivo: albero, flangia, perno e assieme sono presentabili; la staffa lo e' con riserve (viste piccole, richiami che attraversano il pezzo, etichette che toccano i fori).

### Strumenti di sviluppo (non committare)
`scripts_tmp/restart_worker.sh` (worker con istanza dedicata, PID in `scripts_tmp/pid.txt`), `scripts_tmp/run.sh script.py` (esegue nel worker), `scripts_tmp/rl.py` (ricarica i moduli senza riavviare,
ma NON copia gli attributi dati dei mixin se non elencati: `_dm_side`, `_GTOL*`, `_TOL*`), `scripts_tmp/crop.py` (ritaglio PNG). Mai `while True` senza tetto negli script. Il worker va fermato (file `scripts_tmp/cmd/QUIT`)
prima dei test di regressione.

## Blocco 5 — simulazione statica lineare (2026-10-10)
Esito: `tests/test_simulation_live.py` **120/120 PASS** (istanza dedicata, 0 orfani, istanza utente intatta). 18 tool (totale server 195).
Codice: `automation/simulation.py` (mixin SimulationOperations), `solidworks_mcp/simulation_tools.py`. Prototipi in scripts_tmp/ (lib.py, t*.py, d*.py, cosworks_dump.txt).
Tool: simulation_status, create_static_study, list_simulation_studies, delete_simulation_study, set_study_material, add_restraint (fixed/symmetry/roller/hinge),
add_force (direction/normal), add_torque, add_pressure, add_gravity, list_simulation_loads, delete_simulation_load, set_simulation_contact,
create_simulation_mesh (standard/curvatura), run_simulation (timeout con kill del PID dedicato), get_simulation_results, get_simulation_stress_on_faces, export_simulation_plot.
Misure (acciaio AISI 1020, E=200000 MPa):
- Trave 200x20x10, 100 N: delta teorico 0.8000 mm; mesh 8/4/2.5 mm -> 0.7946 / 0.7965 / 0.7970 mm (errore 0.67 / 0.44 / 0.38 %), curvatura 0.7964.
  Cresce verso il teorico da sotto (il vincolo impedisce la contrazione di Poisson). Sigma a meta' trave (nodi faccia sup., x 95..105) 30.05 MPa vs 30.00; max nodale all'incastro 60.35 vs 60.00 (singolarita' ma entro 1 %). Reazione 100.02 N. FOS min = snervamento/VM max.
- Piastra con foro: Kt = 2.657 (Peterson 2.721, -2.3 %), invariato su 2 mesh. Reazione 2000 N.
- Assieme di 2 blocchi, contatto incollato: delta 0.7964 mm come il monolite; reazione 100 N.
- PNG (von Mises, spostamento): mappa a colori visibile, anche con istanza nascosta (controllati a occhio).
- Coppia (albero r=10, 10 N*m, asse = faccia CILINDRICA): spostamento 0.00847 vs 0.00821 mm teorico (+3 %), VM 11.2 vs 11.0 MPa.
- Pressione: reazione = p*A; gravita': reazione = m*g (entro 1 %).
Trappole (dettaglio nel docstring di simulation.py): LoadAddIn(cosworks.dll) serve in ogni istanza nuova (non tocca AddInsStartup, la chiave e' comunque ripristinata);
array di oggetti COM = VT_ARRAY|VT_VARIANT; ActiveStudy e' un indice; carichi modificabili solo con BeginEdit/EndEdit; frame dei componenti forza = schizzo del piano;
add_torque: il riferimento deve essere una FACCIA CILINDRICA (o asse): con uno spigolo errore 4, con faccia piana errore 10;
RESTRAINT 'immovable' da' errore 15 sui SOLIDI (vale per gusci/travi) -> nel test si usa 'symmetry';
**nuova**: in un assieme i corpi di comp.GetBodies2 sono nello spazio del PEZZO: il punto va portato nel riferimento del componente (Transform2.ArrayData) altrimenti il 2o blocco non si trova (corretto in _sim_find_asm_face; convenzione rotazione verificata solo con sola traslazione).
Il "sed in maiuscolo" lasciato dal sotto-agente precedente: nessuna riga alterata trovata (tutti i nomi API verificati contro cosworks_dump.txt, test verde).
Non fatto: contatti locali (solo globale bonded/free; no_penetration non lineare), studi non statici, mesh di controllo locale, posizione del FOS minimo (l'API non la da'), carichi remoti/cuscinetto.

Regressioni dopo il blocco 5: drawings 64/64, modeling 175/175, assembly 113/113, data 159/159 (controllo tool aggiornato a 195 = 177 + 18), drawing_quality 68 PASS/0 FAIL.

## Limiti gruppo A: disegni (2026-10-10/11)
Esito: A1-A15 `[x]` in `LIMITI.md`. `tests/test_drawing_quality_live.py` **132/132 PASS** (tavole albero, staffa, flangia, perno, assieme, cuneo, speciali, verticale; PNG `test_output/qual_*.png` controllati a occhio).
Codice: nuovo `automation/drawing_formats.py` (formati ISO verticali A3-A0 in `formats/`, mai nella cartella di SolidWorks); nuovo tool `add_explode_lines` (totale server 196, controllo aggiornato in `test_data_live.py`); modifiche in drawings.py, drawing_layout/dims/diam/annot.py, assembly_analysis.py.
Novita' in questa ripresa: (1) `_dq_gtol_rect` ora misura solo il riquadro (linee parallele agli assi); le linee di richiamo oblique sono segmenti a parte (`leader_segs` in `get_drawing_layout`) e il test verifica che non attraversino il TESTO di una quota; (2) `_an_place_near` scarta i posti il cui richiamo attraverserebbe un testo di quota (se non c'e' alternativa usa il primo); (3) test: quote in catena sulla stessa riga condividono la linea di estensione (sporgenza di ~1 mm = non e' sovrapposizione) e un riquadro legato a una quota tocca la linea di quota per meno di 1 mm (prassi ISO 1101).
`set_dimension_tolerance` (A9) verificato completo: quota del modello -> sostituita da una quota di riferimento del disegno identica (stessi spigoli/valore/posizione), `apply_to_model=true` dichiarato nel risultato; solo quote lineari H/V, altrimenti non modifica nulla e lo dice.
Trappole: `SetPosition2` su un riquadro agganciato a una QUOTA e' ignorato (SolidWorks lo appende sotto la linea di quota); allargare il rettangolo bersaglio con la linea di quota (patch in `add_geometric_tolerance`) non ha cambiato la posizione: il test tollera <1 mm.
Residui visivi (non bloccanti): "SEZIONE A-A" della flangia sfiora la linea di estensione di una quota; il simbolo di rugosita' generale "Ra x ( ... )" ha il simbolo spostato rispetto alle parentesi.
**PROBLEMA APERTO (non del gruppo A)**: `tests/test_drawings_live.py` fallisce a `add_auxiliary_view` (RPC 0x800706BE, l'istanza SolidWorks muore dentro `CreateAuxiliaryViewAt2`, nessun evento WER). Riprodotto anche su HEAD (worktree pulito) e da processo Python autonomo, quindi NON causato dal gruppo A. Il crash e' casuale (~75% con il foglio 1 pieno di sezione/dettaglio/quote, 0% in tavole minime). Ipotesi scartate con misure: stile della vista interrotta, crop view, vista interrotta presente, posizione della vista ausiliaria (sovrapposta o no alla madre), pausa 2,5-8 s con ForceRebuild3/GraphicsRedraw2/PumpWaitingMessages, ActivateSheet prima della selezione (peggiora). Non si conosce la causa. Nel worker di sviluppo la stessa sequenza e' passata (selezione n=2 [vista, spigolo], vista attiva = la madre).
Regressioni finali: modeling 175/175, assembly 113/113, data 159/159 (196 tool), simulation 120/120, drawing_quality 132/132; drawings 64: rosso solo per il crash di cui sopra (i passi prima di `add_auxiliary_view` passano).


## A16 e A17 (2026-10-11)
**A16 - vista ausiliaria senza `CreateAuxiliaryViewAt2`** (`automation/drawing_aux.py`, mixin `DrawingAuxMixin`; il vecchio metodo e' stato tolto da drawings.py).
Metodo: (1) lo spigolo si sceglie fra gli spigoli rettilinei VISIBILI della vista madre (`IView.GetVisibleEntities2(NULL, 1)`, niente `SelectByID2` sul foglio); (2) direzione di vista n = Z_vista x e (e = spigolo proiettato nel piano della vista), rivolta all'esterno del pezzo; il sistema di assi della madre e' ruotato di 90 gradi attorno allo spigolo (come la piegatura di una vista ausiliaria); (3) vista nominata `AUX_n` nel modello: `IModelView.Orientation3 = MathTransform` (creata con `_oleobj_.Invoke(CreateTransform)`, come in assembly.py) + `IModelDoc2.NameView`; si ripristina l'orientamento, si riattiva il disegno, e se il modello era pulito lo si salva con la vista nominata; (4) `IDrawingDoc.CreateDrawViewFromModelView3`, scala della madre, posta sulla perpendicolare allo spigolo (primo posto libero; se non c'e', nel posto libero piu' vicino; `AlignWithView` solo se la perpendicolare e' orizzontale/verticale); (5) freccia = nota con richiamo agganciato allo spigolo (`InsertNote` con spigolo preselezionato), lettera messa nel primo punto libero da linee di quota; titolo "VISTA x" sotto la vista.
Convenzione della matrice (verificata): colonne di R = assi X,Y,Z della vista nel modello; `ModelToViewTransform` e `Orientation3` hanno lo stesso array a 16 valori. Cuneo con faccia a 30 gradi: nella vista A la normale della faccia e' parallela alla direzione di vista (cos = 1,00000), area della faccia 1209,3 mm2 = 30 x 40,31 attesi, letta dalla matrice REALE della vista creata.
Il risultato di `add_auxiliary_view` riporta `named_view`, `reference_face_true_size_ratio`, `reference_face_area_mm2`, `on_projection_line`, `arrow_note`.
Nessun crash in: 3 esecuzioni consecutive di `test_drawings_live.py` + corse del test qualita' (cuneo piu' volte). Il vecchio crash non si e' piu' presentato (non si chiama piu' quella API).
Altri crash raggiungibili: l'unico altro noto era DXF/DWG con viste interrotte. Era bloccato solo in `export_drawing`; era RAGGIUNGIBILE da `save_document(filepath="x.dxf")` e da `_save_as`. Ora `_export_guard` (drawings.py) rifiuta in tutti e tre i punti. `export_model` lavora solo su pezzi/assiemi (non disegni), `export_model_image` su modelli: non esposti.

**A17 - difetti residui delle tavole** (`automation/drawing_pos.py`, `drawing_annot.py`, `drawing_dims.py`):
- GD&T agganciato: `add_geometric_tolerance(view=, model_point=)` era gia' supportato; ora la staffa lo usa (planarita' 0,05 con freccia sullo spigolo della faccia superiore visto di taglio). Il test verifica `attached_to == "edge"` e `leaders >= 1`, e per ogni riquadro del foglio (`check_a17`) che abbia un richiamo o sia legato a una quota.
- Rugosita' generale ISO 1302: simbolo principale con "Ra x" (testo nello slot 2 di `ISFSymbol.SetText`, sopra la barra: lo slot 5 = `MaxRoughness` NON viene disegnato) + "(" + simbolo base + ")". Le parentesi sono note da 8 mm di altezza centrate in verticale sul simbolo misurando `INote.GetExtent` (la posizione di una nota e' l'angolo in ALTO a sinistra); simbolo: punta in (x,y), box -2,95..+5,9 x 0..10 mm. Il test controlla centri (< 1,5 mm) e distanze (0,5-3,5 mm).
- Quote dei fori: nelle viste con i fori su griglia rettangolare (righe x colonne = numero fori) le quote importate che ancorano un foro (punto di riferimento sull'asse del foro) si tolgono e si rifanno in catena dal bordo del pezzo: righe (verticali) a destra, colonne (orizzontali) sotto; la linea di richiamo parte sempre dal foro piu' vicino alla linea di quota; ultimo tratto omesso se c'e' l'ingombro. Staffa: 12,5-25-45-25 + 120 a destra, 24-24-12 sotto. Fori su circonferenza (flangia) NON si quotano a catena (non e' una griglia).
- Quote importate che dal lato scelto attraverserebbero il pezzo per piu' di 8 mm (nervatura 5/25, meta' estrusione 60 nella pianta) si tolgono; le misure tornano nelle altre viste.
- Viste frontale e laterale: catene fra le ordinate degli spigoli assiali visibili (spessori, nervatura) e quote H/V degli spigoli inclinati, una sola volta per valore (stesso valore gia' quotato in un'altra vista o sullo stesso asse = saltato). Staffa: laterale 6, 6, 30, 30, 40, 60; frontale 22,5, 5, 65. Cuneo: 34,91 e 20,16 sullo spigolo a 30 gradi.
- `ArrowSide = 0` (frecce dentro) quando il testo ci sta: in modalita' 'smart' SolidWorks metteva le frecce fuori sotto ~30 mm e allungava la linea di quota di 6 mm per lato (sovrapposizioni fra quote in catena).
- `_dq_assign_rows`: due quote che condividono un'ancora (stessa linea di richiamo) o si toccano stanno sulla stessa riga; prima il margine DQ_CLEAR le separava e l'ingombro finiva 5 righe piu' in la' (fuori dal foglio nella tavola verticale).
- Titolo di vista (SEZIONE A-A, DETTAGLIO B): le sue note sono ostacoli per le quote della stessa vista (`_dq_label_rects`), cosi' le quote vanno dall'altro lato e non sfiorano il titolo. Le viste con quote di cerchi (Ø, callout) si dispongono per ultime.
- Note con richiamo: `GetExtent` include la linea di richiamo; per le note con richiamo il riquadro e' solo il testo (`_dq_note_rect`).
- Nuovi controlli in `check_layout` (`check_a17`): nessuna linea di quota attraversa un foro a cui non e' ancorata; nessuna linea di quota/richiamo attraversa una nota/titolo di vista; ogni GD&T agganciato. Il duplicato ora distingue l'asse (H e V dello stesso spigolo inclinato). Quote della stessa riga con tratti disgiunti e testi separati non sono sovrapposizioni.
- `get_drawing_layout` ora espone `lines` di ogni quota e `holes` di ogni vista.
- Prestazioni: `_dq_read` costa ~0,5 s a quota (GetDisplayData); le nuove funzioni usano `_dp_info` (solo frecce). `insert_model_dimensions` sulla staffa: ~225 s.
Per sviluppare una sola tavola: `QUAL_ONLY=staffa,cuneo python tests/test_drawing_quality_live.py`.
Trappole API nuove: `AddHorizontalDimension2/AddVerticalDimension2` con due cerchi selezionati misurano fra i CENTRI; con bordo+cerchio, dal bordo al centro. `IView.GetVisibleEntities2` vuole `VARIANT(VT_DISPATCH, None)` come primo argomento. `IMathUtility.CreateTransform` solo via `_oleobj_.Invoke`. `IModelView.Orientation3` e' scrivibile.
Regressioni finali A16/A17 (sequenza, istanza dedicata, 0 orfani): test_drawings_live 65/65 per 3 esecuzioni consecutive (64 + 1 controllo nuovo sulla vista ausiliaria), drawing_quality 139/139, modeling 175/175, assembly 113/113, data 159/159 (nessun tool nuovo: 196), simulation 120/120. Il "PROBLEMA APERTO" del crash di `CreateAuxiliaryViewAt2` (sezione "Limiti gruppo A") e' risolto: la chiamata non esiste piu'.
Giudizio sulle tavole (`test_output/qual_*.png`): staffa, flangia, albero, assieme, perno, tavola verticale sono presentabili (quote pulite, nessun richiamo attraversa fori, GD&T con freccia, rugosita' ISO). Limiti onesti: nella tavola del cuneo la vista ausiliaria sta in un posto libero ma non sulla perpendicolare allo spigolo (li' non c'e' posto) e non e' allineata; i richiami dei Ø della flangia restano lunghe diagonali (prassi accettabile ma non elegante); l'etichetta A1 della staffa sta vicina all'asse del foro; le tavole d'assieme restano senza quote di posizione.
Ultimo aggiornamento: 2026-10-11


## Limiti gruppo B: modellazione e tool base (2026-10-11)
Esito: B1, B2, B3, B5, B6 `[x]`; B4 `[~]` (vedi sotto) in `LIMITI.md`. Test: `tests/test_modeling_extra_live.py` (nuovo, istanza dedicata, 0 orfani; `python tests/test_modeling_extra_live.py B1 B4` esegue solo le sezioni indicate). Numero di tool invariato (196).
Codice: `automation/documents.py` (close_document sicuro, save_document con overwrite, Save in-place riparato), nuovo `solidworks_mcp/safety.py` (annotazioni distruttive + guardia overwrite), `automation/modeling.py` (piano per 3 punti, piano inclinato, pose lette dall'API, sistema di coordinate con flip, Hole Wizard multi-standard, delete_feature con confirm), `automation/features.py` (cut_extrude through_all + both_directions), `modeling_tools.py` e `server.py` (schemi).

**B1 raccordo variabile** - nessuna modifica al codice, solo test. Spigolo retto di 40 mm fra due facce a 90 gradi, raggio lineare r0->r1: asportato = (1-pi/4) L (r0^2+r0 r1+r1^2)/3. Misurato/atteso: R2->R8 240.450/240.354 (0,040 %), R8->R2 240.450 (simmetrico), R3->R7 226.143/226.047 (0,042 %), R5->R5 214.700/214.602 (0,046 %). `radius_start` e' il raggio dell'estremo a z minore (verificato selezionando la faccia piana a z=0.05 e z=39.95).
**B2 riferimenti** - letti dall'API: `feature.GetSpecificFeature2.Transform.ArrayData` = [0:3] asse u, [3:6] asse v, [6:9] NORMALE, [9:12] origine (m), [12] scala; per i sistemi di coordinate `doc.Extension.GetCoordinateSystemTransformByName(nome).ArrayData` (X,Y,Z nelle tre righe). `create_reference_plane` e `create_coordinate_system` ora riportano `plane_origin/plane_normal/plane_u/plane_v` e `origin/x_axis/y_axis/z_axis`. Misure: piano per A(0,0,0) B(20,40,0) C(0,0,30): normale (0.894427,-0.447214,0) = (B-A)x(C-A) normalizzato (errore < 1e-6), 3 vertici sul piano a 2e-5 mm; la normale dello schizzo sul piano (secondo canale) coincide. Offset da 'top' 15: z=15, normale +Z; da faccia z=30 di 7: z=37 (flip: 23). Inclinato 45 gradi attorno allo spigolo (0,y,30): angolo con la faccia 45.0000, contiene lo spigolo, origine (-15,0,15) (flip: (15,0,15)); 30 gradi: normale (-0.5,0,0.866). Sistema di coordinate con origine (20,40,30): origine esatta, X//spigolo X, Y//spigolo Y, Z = X x Y, `x_flip` inverte X e Z.
 Trappole: `InsertRefPlane(4,0,4,0,4,0)` (3 vertici) e `InsertRefPlane(4,0,16,ang,0,0)` (spigolo+faccia+angolo) restituiscono None; funzionano `doc.CreatePlaneThru3Points3(True)` e `doc.CreatePlaneAtAngle3(rad, flip, True)` (con spigolo e faccia selezionati, in qualunque ordine). Costanti: Coincident=4, Perpendicular=2, Distance=8, Angle=16. Il verso degli assi del sistema di coordinate e' quello parametrico dello spigolo (non "uscente dall'origine").
**B3** (tutti sotto 0,01 % tranne il loft curvo): convert_entities face_point -> 4 segmenti, estruso 5 = +6000.000 (atteso 6000); convert_entities di uno spigolo circolare -> 1 segmento, +339.292 (pi r^2 3); up_to_surface su cuneo con faccia z=20+y/3: +2356.196 (pi 25 (60-30)); revolve_cut 360 gradi -2092.3 (pi(400-289)6), 180 gradi -697.4 (meta'); loft con 2 guide rettilinee 18000.000 (trapezio) e `GetGuideCurvesCount`=2 letto dall'API; loft con 2 guide ad arco (sporgenza 5): 27879.7 contro 28087.5 del modello ideale a sezioni rettangolari (-0,74 %: SW interpola le superfici fra le guide) e contro 24000 senza guide; sweep di taglio -7965.188 (pi r^2 L, Pappus). Nessuna modifica al codice.
**B4 Hole Wizard** - `create_hole(kind, size, standard, head, fit)`. Standard (tabella `HOLE_STANDARDS` in modeling.py): iso, ansi_metric, ansi_inch, din, bsi, jis. **UNI non esiste** ne' in `swWzdHoleStandards_e` ne' nel Toolbox (cartelle AS, Ansi Inch/Metric, BSI, CISC, DIN, GB, IS, ISO, JIS, KS, MIL, PEM, SKF...): il tool lo rifiuta con messaggio. Teste: lamato socket/cheese/pan/button/hex/hex_cap/hex_machine, svasato socket/flat/raised/oval, filettato (+ bottoming), semplice. `fit` close/normal/loose = Ø di passaggio ISO 273 (M6: 6.4/6.6/7.0; default normal = comportamento di prima), `database` = valore del DB.
 Per ogni caso (36 combinazioni) il test misura sul modello (list_entities) raggio e altezza dei cilindri, area dei coni e quota dei fondi, e confronta: Ø misurato = atteso (tabella normativa/DB, 0,02 mm), definizione del foglio = modello, volume asportato = formula dalla geometria misurata (scarto < 0,001 % ovunque). Esempi M6: ISO lamato socket Ø11 x 6.4, cheese Ø11 x 3.9, pan Ø13 x 4.6, hex Ø14.547 x 4.0, svasato socket Ø13.44, flat Ø12.6, filettato punta 5.0; ANSI pollici 1/4: Ø passaggio 6.7564, lamato 11.1125 x 6.35, esagonale 19.05 x 4.7752, svasato 12.8778, filettato 1/4-20 punta #7 5.105 (cieco 15/12: zona Ø6.35 x 12 + Ø5.105 x 3 + cono 118).
 Piano inclinato (18,43 gradi, punto (30,30,30)): asse del foro = normale della faccia (0,-0.3162,0.9487), passante asportato 1081.745 vs pi r^2 z0/cos 1081.877 (0,012 %); cieco prof. 12 misurata 12.0000 lungo l'asse, volume 433.156 = cilindro + punta 118 gradi (0,000 %). Le facce piane di qualunque orientamento (+/-X, +/-Y, +/-Z) posizionano il foro esattamente nel punto indicato (sonda, non nel test).
 **Faccia cilindrica**: il foro e' radiale (asse incidente all'asse del cilindro, distanza 0), Ø 6.6 misurato, volume 2049.337 vs integrale delle corde 2049.807 (0,023 %). LIMITE APERTO: la posizione angolare NON e' quella indicata (cilindro R30 asse X centrato: il foro cade 90 gradi piu' in la', pick a 45 -> foro a -45; con cilindri decentrati o altri assi lo scarto cambia): e' un comportamento di `HoleWizard5` (anche con `SelectByID2`), non riesco a correggerlo in modo generale. Va verificata la posizione con list_entities. Per questo B4 e' `[~]`.
 Trappole: size per ANSI metrico/BSI/JIS filettati = 'M6x1.0' (aggiunto il passo grosso); ANSI pollici: foro semplice/lamato/svasato '1/4' o '#10', filettato '1/4-20'; con `Diameter=0` il filettato ANSI pollici usa un Ø punta di **25.4 mm** (asporta 60800 mm3 da una piastra!) -> tabella UNC `TAP_DRILL_INCH_MM`. In ISO un Diameter esplicito prevale sul DB (DB = fit close 6.4). `HoleWizard5` su ANSI pollici non accetta '0.25' ne' '1/4 - 20'.
**B5 tool base** - tutti verificati con volumi: draw_rectangle 20x10 estruso 5 = 1000; draw_line lunghezza 50.0; draw_arc 0-180 + corda 785.398 (pi r^2/2 5), 0-90 392.699, 90-270 con centro fuori origine 502.655, in pollici (r=0.5 in) 1266.769; draw_polygon: il raggio e' quello CIRCOSCRITTO (vertici sul cerchio): esagono 1299.038, pentagono 1188.821, ottagono 1414.214; rifiuta 2 lati. cut_extrude: cieco 37.70, through_all 35.34, both_directions con depth = piano medio (3 mm TOTALI, 150.796). set_units('inch'): 1x1 in x 0.5 in = 8193.532 mm3, ripristino mm. execute_python: stdout/result catturati, `doc` = documento attivo, `automation` legge il volume, eccezione e SyntaxError segnalati. open_document: titolo/percorso, file inesistente = errore, gia' aperto = nessun duplicato; save_document: Save As, Salva senza nome, riapertura con stesso volume (926.958), il file originale resta com'era dopo un Salva con nome.
 **Bug trovati e corretti**: (1) `save_document()` senza nome falliva sempre: `Save3(0,0,0)` da "Incompatibilita' tra tipi", servono Errors/Warnings BYREF (`VT_BYREF|VT_I4`) e `Options=1`; (2) `cut_extrude(through_all, both_directions)` passava T1=2 (fino al successivo): ora Sd=False, T1=T2=1 (125.664 = pi r^2 10 su blocco da 10).
**B6 sicurezza** - `close_document(save, discard, document)`: rifiuta se `GetSaveFlag`, schizzo in modifica o (assiemi) componenti modificati (`refused: unsaved_changes`, messaggio che spiega save=true/discard=true); save=true su documento mai salvato rifiuta (`never_saved`); save e discard insieme = errore; `document` = titolo ('Parte1', 'staffa.SLDPRT') o percorso, il documento attivo non viene toccato (test con due documenti aperti); discard dichiara "modifiche NON salvate SCARTATE"; il file su disco resta invariato dopo discard; save=true salva davvero (volume riaperto 984.292). Documento pulito: chiude senza parametri (`closed_clean`).
 Altri tool a rischio (`safety.py`): (a) **sovrascrittura**: `save_document`, `save_drawing`, `export_drawing`, `export_model`, `export_model_image`, `export_simulation_plot`, `create_drawing(save_as)` rifiutano un file ESISTENTE senza `overwrite=true` (guardia unica prima dello smistamento; `save_document` sul proprio file o senza nome resta un normale Salva); (b) **delete_feature** richiede `confirm=true` e, se altre feature ne dipendono, rifiuta e le elenca salvo `delete_children=true` (BUG corretto: prima senza delete_children cancellava lo stesso le dipendenti, es. la ripetizione, senza dirlo; l'enum `swDeleteSelectionOptions_e` e' Children=1, Absorbed=2); riporta `deleted_features`; (c) annotazioni MCP `destructiveHint=true` + nota "[DISTRUTTIVO ...]" sui 21 tool: close_document, save_document, save_drawing, export_drawing, export_model, export_model_image, export_simulation_plot, create_drawing, delete_feature, delete_view, delete_component, delete_mate, replace_component, delete_custom_property, delete_global_variable, delete_equation, delete_part_configuration, delete_explode_step, delete_simulation_study, delete_simulation_load, execute_python (senza parametro extra: sono operazioni di editing normali).
 **Test esistenti adeguati**: tutti i `close_document(save=False)` (e `close_document` senza parametri in test_simulation) ora usano `discard=True`, perche' chiudevano pezzi/disegni di prova modificati e il nuovo comportamento li rifiuta; `Client.call` dei sei test aggiunge `overwrite=True` ai tool che scrivono file (i file di test_output esistono dalla corsa precedente); `delete_feature` in test_modeling ha `confirm=True`.
 Regressioni finali (sequenza, istanza dedicata, worker di sviluppo fermo, 0 orfani, istanza utente intatta): test_modeling_extra_live **240/240**, test_drawings_live 65/65, test_modeling_live 175/175, test_assembly_live 113/113, test_data_live 159/159 (196 tool), test_drawing_quality_live 139/139, test_simulation_live 120/120.


## Limiti gruppo C: assiemi (2026-10-11)
Esito: C1, C2, C4, C6, C7 `[x]`; C3 e C5 `[~]` (vedi sotto) in `LIMITI.md`. Test: `tests/test_assembly_extra_live.py` (nuovo, istanza dedicata, 0 orfani, **213/213 PASS**; `python tests/test_assembly_extra_live.py C1 C5` esegue solo le sezioni indicate, `CX_REUSE=1` salta la ricostruzione dei 12 pezzi cx_*; C6 gira dentro C4). Numero di tool invariato (196): solo parametri nuovi.
Codice: nuovo `automation/assembly_explode.py` (C3/C4), nuovo `automation/assembly_motion.py` (C6/C7), `assembly.py` (C1, C2, C5), `assembly_analysis.py` (tolti i metodi spostati), `assembly_tools.py` (schemi), `safety.py` (`mirror_components` marcato distruttivo: con `opposite_hand` scrive file, rifiuta se esistono senza `overwrite=true`; se il file e' gia' un componente aperto rifiuta sempre).

**C1** - `_as_find_geom` cercava solo nei componenti di primo livello (`GetComponents(True)`); ora `GetComponents(False)`. `Component2.Transform2` di un componente annidato E' GIA' la trasformazione composta (misurato: cx_sub2 60 gradi + cx_sub 30 gradi con traslazioni -> perno a (210; 57,5; 32,9904) = R60(R30 p + (0,15,0)) + (200,50,20) calcolato dal test), quindi `_as_to_part` vale a ogni profondita'. Select4 di una faccia di un componente annidato funziona senza altro. Test: coincidente blocco(primo livello)-faccia terminale del perno a 2 livelli (blocco a x=250), concentrico sporgenza-perno annidato (asse blocco = asse perno entro 0,001 mm), `check_clearance` per nome annidato.
**C2** - `MirrorComponents3` per il pezzo NUOVO: `ComponentsToMirror`=componenti, `ComponentsToInstance` e `ComponentOrientations` VUOTI (con orientamenti non vuoti non fa nulla), `NameModifierType`=1 (suffisso), `NameModifier`, cartella, `ImportOptions` 0x1FFFF. Il nome del file e' <nome><suffisso>.SLDPRT. Il nuovo componente e' governato dalla feature di specchiatura, e la sua posa **cambia fra sessioni** (stessa geometria, R = diag(-1,-1,1) oppure diag(1,-1,-1)): quindi `align_exact=True` (default) ricava l'asse riflesso dal baricentro e dal tensore d'inerzia, calcola la posa esatta R' = Refl R F, t' = Refl(t) e, se SolidWorks non l'ha data, DISSOLVE la feature (`IAssemblyDoc.DissolveComponentPattern`, proprieta': leggerla la esegue) e imposta la posa (altrimenti la ricostruzione rimette quella sbagliata; `PreserveZAxis` via ModifyDefinition non e' persistente). Misure: volume 12141,3717 mm3 = originale, baricentro locale (-7,6164; 0,1164; 0) (X riflessa), baricentro nel mondo (7,6164; -60,1164; 0) = riflesso rispetto a y=0; stesso per il Piano frontale (X riflessa, -7,6164). Istanze (`orientation` 0..3) misurate sul blocco chirale: 0 = 180 gradi attorno a X, 1 = 180 attorno a Z e origine x+20, 2 = nessuna rotazione, 3 = 180 attorno a Y e origine x+20 (rispettivamente det=+1; solo l'orientamento 0 riflette il baricentro).
**C3** - Passi: `AddExplodeStep2` ammette solo X/Y/Z dell'assieme -> un vettore libero e' scomposto in 1-3 passi (spostamento totale = distanza x versore, misurato 50,0000 mm). Direzione da un'entita' (spigolo, faccia cilindrica con componente): passo a indice 0 + `IExplodeStep.SetExplodeDirection(oggetto, 0)` (verso = quello dell'entita'; la faccia cilindrica del perno inclinato di 30 gradi ha dato 40,0000 mm parallelo all'asse). Radiale: `IConfiguration.AddRadialExplodeStep(dist, angolo, divergente, err)` con componenti Mark 1 e asse (faccia cilindrica) Mark 2: raggio 30->60 mm e ogni vite ruota di 30 gradi attorno alla propria direzione radiale (angolo della matrice 30,00005; la rotazione e' attorno alla retta radiale per il CENTRO DEL BOX del componente). **Rotazione nei passi di traslazione impossibile**: `AddExplodeStep2(.., ExplAng, RotAxisIndex, .., RotateAboutOrigin, ..)` non memorizza l'angolo con nessuna combinazione (dirIdx -1/0/1, rotIdx -1..2, origine si/no, distanza 0 o no): `RotationAngle` resta 0, `SetRotationAxis`/`RotationAngle` come proprieta' non hanno effetto sui passi di traslazione (funzionano sui radiali). Trappola: dopo aver aggiunto passi `Transform2`/`GetBox` restano le pose vecchie finche' non si commuta `ShowExploded2(False)`/`(True)` (ora `_ex_refresh`). `list_exploded_views` e `create_exploded_view` riportano le pose esplose.
**C4** - `IAssemblyDoc.AutoExplode` esiste (PROPRIETA'): su assiemi senza vista esplosa la crea con un passo "Catena" che sposta quasi tutti i componenti lungo una direzione scelta da SolidWorks (Z nell'esempio: base +323 mm, boccola +163, perno +98, viti +30..+176); su un assieme che ha gia' una vista non crea passi. Nel nostro assieme di prova lascia 1 coppia di box sovrapposta (boccola-vite 4,23 mm). Euristica `auto_explode(mode="mates")`: grafo degli accoppiamenti fra componenti di primo livello -> profondita' dal componente base (fisso) = ordine di smontaggio (i piu' interni per primi); direzione = asse delle facce cilindriche coassiali della coppia concentrica; verso = lato della TESTA (faccia cilindrica coassiale di raggio maggiore di quella impegnata), altrimenti opposto al componente accoppiato; distanze da relaxation sui bounding box (ogni componente si allontana finche' il suo box dista >= gap da tutti gli altri, ordine dal piu' interno) con controllo finale sugli `GetBox` reali dello stato esploso. Misure: perno -106,408 mm, boccola -55,243, viti -27,243 (X), 0 sovrapposizioni, distanza minima fra i box 15,000 mm. `mode`: axis (default storico) | native | mates | auto. I box di `GetBox` includono ~0,2 mm di margine per lato.
**C5** - Verificati con misure (muovendo = cambiando il valore o `move_component`): *limite distanza* 10 mm [5,20]: i limiti si leggono da `Mate2.MaximumVariation/MinimumVariation` (relativi al valore) e il componente NON si muove con `SetTransformAndSolve2`/Transform2+rebuild (torna sempre al nominale): si pilota la quota D1 del mate (`edit_mate(value)`): nel limite il blocco va a x=10+valore, fuori limite il valore e' rifiutato (D1 resta com'era); limiti modificabili con `GetDefinition` (`IsAdvancedMate`, `MaximumDistance/MinimumDistance`) + `ModifyDefinition` (poi RILEGGERE feature e quota: gli oggetti sono vecchi). *Limite angolo* -20..45: |rotazione attorno a X| = |D1| (misurato: 30->-30, 44->-44, -10->-10), 50 e -25 rifiutati. *Larghezza*: `AddMate5(11, ..)` da SEMPRE "errore sconosciuto" (provate 256 combinazioni di Mark e tutti gli allineamenti); funziona `CreateMateData(11)` + `WidthSelection`/`TabSelection` (array VT_DISPATCH) + `ConstraintType` + `CreateMate`: linguetta centrata a y=5, Y vietato, X e Z liberi, rotazione libera attorno a Y. *Simmetrico*: entity3 = piano dell'assieme ('Piano destro'; ora `_as_select_entity` accetta anche nomi di feature dell'assieme): origine y=-100 = riflesso. *Tangente*: asse a z=10+5=15, non penetra, libero X,Y e rotazioni X,Z. *Blocco* (lock), *ingranaggio* (gear), *vite* (screw): creati e letti dal modello, ma SolidWorks non li fa rispettare via API: il lock trattiene le traslazioni (deriva <= 0,4 mm) ma lascia libere le tre rotazioni; ruotando la ruota A di 30 gradi la B non segue (ne' con `SetTransformAndSolve2` ne' con `IDragOperator` in tutti i modi/TransformType); ruotando la chiocciola di 90 gradi non avanza. Uno studio di movimento (`Extension.GetMotionStudyManager`, tipo 2, `CreateDefinition(78)` motore rotativo con `DirectionReference`=faccia) crea il motore ma `Calculate` non produce moto nell'istanza nascosta (risultati tutti 0). Rapporto ingranaggio: la definizione letta e' SEMPRE scambiata rispetto a quella passata (num=2,den=1 -> 1,2; anche con `CreateMateData`). Vite: `AddMate5` e `CreateMateData(17).RevolutionVal` NON impostano il passo (resta 1 m/giro); si imposta con la quota `D1@mate` (m/giro) e poi `GetDefinition().RevolutionVal` lo conferma (`ModifyDefinition` lo riporta a 1). Nota: il primo componente inserito in un assieme e' gia' fisso.
**C6** - Riprodotto con la base fissa + boccola + perno: eliminando il coincidente boccola-base la boccola passa da 1 a 2 gradi di liberta' (compare la traslazione X) e anche il perno da 1 a 2 (segue la boccola per catena), le posizioni non cambiano, e il tool prima non lo diceva. `SetTransformAndSolve2` su un componente NON trascina i componenti che lo seguono, quindi i DOF di un componente vanno misurati anche osservando chi si muove con lui durante le prove degli altri (`_as_dof_snapshot` con `on_probe`, ripristinando tutte le pose con Transform2). `delete_mate(check_dof=True)` riporta `dof_before/after`, `freed_components`, `freed_not_in_mate`, `warning`. `GetConstrainedStatus` vale 5 ("nessuna soluzione") con l'assieme esploso: i DOF misurati ricompattano prima.
**C7** - `Component2.SetTransformAndSolve2` con una posa non raggiungibile da' un compromesso del solutore (rotazione di 45 gradi attorno a Y su un perno col solo concentrico: scivola di 11,7 mm lungo l'asse; traslazione fuori asse: ignorata). Ora `move_component(respect_mates=True)` MISURA i gradi di liberta' (`_as_dof_basis`: prove di 0,5 mm / 3 gradi lungo/attorno a X,Y,Z; la direzione ottenuta si verifica provando proprio lungo di essa, quindi funziona anche con assi inclinati; per le rotazioni si ricava anche il punto dell'asse dallo spostamento dell'origine) e passa al solutore solo la parte consentita (traslazione proiettata sulle direzioni libere, angolo = componente del vettore di rotazione lungo gli assi liberi). Risultato: `free_translation_directions`, `free_rotation_axes`, `requested`, `applied`, `ignored`. Numeri: rotate_by X 30 -> 30,000 gradi; dx=15 -> 115; rotate_by Y 45, Z 20, dy=10, dz=-7 -> 0 mm di moto, scartati; combinato dx=-5 dz=8 rotX=20 -> -5 mm e 20 gradi; rotate_by [15,25,0] -> 14,7607 gradi attorno a X; asse inclinato 30 gradi, dx=10 -> (7,5; 4,3301; 0) = 10 cos30 lungo l'asse, scartati 5 mm, distanza dall'asse 0,00015 mm. `get_assembly_status` usa la stessa misura (etichette tipo '(0.866,0.500,0.000)' per direzioni non assiali). Bug trovati: `edit_mate(suppress)` falliva (`EditSuppress2` e' proprieta' sull'assieme: usare `_com`); `doc.EditRebuild3()` in add_mate falliva in silenzio (proprieta').
Strumenti di sviluppo: `scripts_tmp/rla.py` (ricarica i mixin degli assiemi nel worker), `cx_lib.py` (pezzi di prova), c*.py/m*.py (prove).
Regressioni finali (sequenza, istanza dedicata, worker di sviluppo fermo, 0 orfani, istanza utente intatta): test_assembly_extra_live **213/213**, test_drawings_live 65/65, test_modeling_live 175/175, test_modeling_extra_live 240/240, test_assembly_live 113/113, test_data_live 159/159 (196 tool), test_drawing_quality_live 139/139, test_simulation_live 120/120.
Ultimo aggiornamento: 2026-10-11


## Sessione cloud senza SolidWorks (2026-10-12)
Container Linux: nessun test live eseguibile. Fatto solo cio' che si verifica senza SolidWorks:
- `tests/test_offline.py` (nuovo): **36/36 PASS** con COM simulato (gira anche su Windows con pywin32, senza usare SolidWorks).
  Registro dei 196 tool coerente (schema = parametri passati = firma del metodo; nessun tool senza smistamento), `safety.py`,
  PNG puro Python, lettori dei file esportati, libreria `.sldmat`, unita'. Uso: `python tests/test_offline.py`.
- `_dx_inspect_step`: nuovi contatori `product_definitions` e `assembly_occurrences` (struttura d'assieme dello STEP, per D6). NON ancora provato su uno STEP vero di SolidWorks.
- `PIANO_D_E.md` (nuovo): piano per D1-D10 ed E1-E5 con API candidate (marcate "da verificare"), test e numeri attesi
  (es. mensola 200x20x10 AISI 1020: f1 = 203,2 Hz, Pcr = 20562 N).
Prossimo passo, sul PC con SolidWorks: seguire l'ordine indicato in `PIANO_D_E.md`, dopo aver rieseguito `test_data_live.py` (controlla il nuovo inspector STEP).


## Avanzamento dei gruppi A, B, C (note spostate da LIMITI.md il 2026-10-12)

### Avanzamento gruppo C (2026-10-11)
- C1-C7 chiusi: C1, C2, C4, C6, C7 `[x]`; C3 e C5 `[~]` (rotazione nei passi di traslazione dell'esploso; blocco/ingranaggio/vite non propagati dal solutore via API). Test: `tests/test_assembly_extra_live.py` 213/213. Regressioni in sequenza: drawings 65/65, modeling 175/175, modeling_extra 240/240, assembly 113/113, data 159/159, drawing_quality 139/139, simulation 120/120. Nessun tool nuovo (196). Dettagli in STATO.md, sezione "Limiti gruppo C".

### Avanzamento gruppo A
- A1-A15 risolti e coperti da `tests/test_drawing_quality_live.py` (132/132 PASS) + PNG controllati a occhio. Dettagli in STATO.md, sezione "Limiti gruppo A".
- Aperto, non del gruppo A: `tests/test_drawings_live.py` fallisce a `add_auxiliary_view` per un crash casuale di SolidWorks (vedi STATO.md); riproducibile anche su HEAD.
- A16 e A17 chiusi (2026-10-11). Regressioni: drawings 65/65 x3, drawing_quality 139/139, modeling 175/175, assembly 113/113, data 159/159, simulation 120/120. Il rosso 'aperto, non del gruppo A' di test_drawings_live e' risolto con la nuova vista ausiliaria.

### Avanzamento gruppo B (2026-10-11)
- B1-B6 chiusi (2026-10-11): B1, B2, B3, B5, B6 `[x]`, B4 `[~]` (UNI assente dal database; posizione angolare del foro sulle facce cilindriche non controllabile). Test: `tests/test_modeling_extra_live.py` 240/240. Regressioni in sequenza: drawings 65/65, modeling 175/175, assembly 113/113, data 159/159, drawing_quality 139/139, simulation 120/120. Dettagli in STATO.md, sezione "Limiti gruppo B".
