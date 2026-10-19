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

## Fase 1: SolidWorks in inglese (G1, 2026-10-16/17)
- Lingua cambiata via API, senza toccare l'interfaccia: `SetUserPreferenceToggle(83, ...)` (swUseEnglishLanguage) e `(262, ...)`
  (swUseEnglishLanguageFeatureNames); valori originali entrambi False. Vale al riavvio: si imposta su un'istanza dedicata, la si chiude
  con ExitApp (salva le preferenze), la successiva parte in inglese (`GetCurrentLanguage` = english). Script `scripts_tmp/lingua.py en|it|leggi`.
- Regressione in inglese: modeling 175/175, modeling_extra 240/240, drawings 65/65, assembly_extra 213/213, simulation 120/120 al primo colpo;
  drawing_quality 139/139, data 159/159, assembly 113/113 dopo le correzioni sotto. Offline 83/83.
- Trappole trovate (tutte nei test tranne la prima):
  - nota "SMUSSI NON QUOTATI": la larghezza era STIMATA (3,5 mm x carattere); il carattere delle note del formato e' piu' grande
    (in inglese ~89 mm reali contro ~69 stimati) -> toccava la quota vicina. Ora la nota si inserisce, si misura con `GetExtent` e poi si
    cerca lo spazio libero (`_dq_chamfer_note`, ostacoli letti PRIMA dell'inserimento);
  - intestazioni della distinta (BOM) nella lingua del modello di tabella: cercare le colonne per contenuto ("num. parte"/"part n", "quantit"/"qty");
  - libreria materiali inglese: Acciaio -> Steel, Plastiche -> Plastics, "ABS generico" -> "ABS", "Lega 6061" -> "6061 Alloy";
    `set_material` cerca per sottostringa: "Bronzo" in italiano prende "Alluminio Bronzo", in inglese serve "Bronze" (-> "Aluminum Bronze", stessa densita');
  - feature: RipetizioneCircolare1 -> CirPattern1, RipetizioneLineare1 -> LPattern1; il titolo del documento d'assieme cambia: cercarlo con `type == "Assembly"`;
  - formato verticale inglese = `a3 - iso portrait en.slddrt`; cartiglio SIZE/WEIGHT al posto di FORMATO/PESO.
- Attenzione: il PC va in sospensione durante le regressioni lunghe (2026-10-16 16:47, il test riprendeva per pochi secondi ogni ~2,5 h).
  Tenere sveglio il PC; un sotto-agente che lancia run_all.py in background lo uccide quando chiude: lanciarlo dalla sessione principale.
- `insert_model_dimensions` sulla tavola verticale della staffa: 3 min 17 s il 2026-10-16, 5 min 25 s il 2026-10-17 (stesso codice).

## Fase 2: ripresa di B4, C5, C3 (2026-10-17)
- B4 `[x]`, fori Hole Wizard su facce cilindriche: HoleWizard5 mette il pick nello schizzo 3D come coordinate del Piano frontale (F)
  lette nel sistema dello schizzo (R): punto reale = R F p. Con il modello di parte di Elia F e R non sono l'identita' (Front normale X,
  Top Z, Right Y). Il server passa g = F^T R^T p (`_hw_on_curved`, `_hw_sketch_point`, `_hw_pick`, `_hw_front_frame`, `_rotations24`):
  R letta dallo schizzo del primo foro, o cercata fra le 24 rotazioni se il primo pick cade fuori dalla faccia; cache per F; ogni foro
  verificato (scarto <= 0,01 mm). Worker: 19 fori, 3 orientamenti, cilindro decentrato -> 0,00000 mm / 0,00000 gradi. Test B4 70/70
  (14 min): R30 asse del foro incidente all'asse del cilindro, distanza 0,00e+00 mm, x=30,000, volume 2049,337 contro 2049,807 (0,023 %).
- C5 `[x]`, ingranaggio/vite/blocco: SetTransformAndSolve2 non propaga questi accoppiamenti, ma un accoppiamento d'ANGOLO temporaneo
  si' (`_as_drive_rotation`, `_as_mech_mates`, `_as_signed_rot`; `move_component` lo usa quando il componente ha gear/screw/rack_pinion).
  `_as_dof_basis` ora rimette a posto TUTTI i componenti (prima la seconda ruota restava ruotata di 1,7188 gradi).
  Trappola: nella vite `RevolutionType` 0 = giri per lunghezza (2 mm/giro diventava 500 mm/giro), 1 = distanza per giro.
  Test C5 82/82: A +30 -> B -60,0000; vite 90 gradi -> 0,5000 mm; blocco: angolo di 50 gradi imposto, matrice invariata (0,00e+00).
  Ancora visibile: `_as_dof_basis` vede 3 rotazioni libere sul componente bloccato; SetTransformAndSolve2 dx=20 -> deriva 0,400 mm.
- C3 resta `[~]` (`scripts_tmp/c3p1..4.py`): scrivere `IExplodeStep.RotationAngle` dopo la creazione non ha effetto (riletto 0,0);
  `IExplodeStep.GetRotationAxis` e' un metodo, non una proprieta'. AddRadialExplodeStep accetta distanza 0: dopo una traslazione ruota il
  componente di `angle` attorno alla DIREZIONE RADIALE (asse -> componente), misurato 45,0000 gradi attorno a +Y, raggio invariato.
  Su un componente coassiale all'asse radiale AddRadialExplodeStep restituisce codice 1 (direzione radiale indefinita).
- Trappole di lavoro: con l'uscita su file Python scrive a blocchi, un test live sembra fermo (log a 0 byte, CPU quasi nulla) mentre lavora:
  usare `python -u`. Un `> file` di PowerShell scrive in UTF-16 (leggerlo con `iconv -f UTF-16`). Un secondo test sullo stesso log
  fallisce con "file in uso": controllare prima i processi `tests/*.py` gia' attivi.

## Fase 3: gruppo D (2026-10-17)
### D5 riferimenti dei componenti nelle immagini d'assieme
- I piani/assi dei componenti non stanno nell'albero dell'assieme (`FirstFeature` dell'assieme non li visita): per nasconderli si usa il
  toggle di DOCUMENTO `swViewDisplayHideAllTypes` = 198 (`doc.Extension.Get/SetUserPreferenceToggle(198, 0, ...)`), poi `GraphicsRedraw2`.
- TRAPPOLA: nel modello d'assieme `swDisplayPlanes` (5) del documento e' False (anche 4 assi e 6 origini): un piano visibile nel pezzo
  NON compare nell'assieme finche' non lo si accende. Il primo test D5 dava 0 pixel azzurri anche senza nascondere (controllo inutile).
- Costanti trovate in `swconst.tlb` (enum `swUserPreferenceToggle_e`): 4 assi, 5 piani, 6 origini, 13 sistemi di coordinate,
  19/219 punti di riferimento, 196 schizzi, 197 annotazioni, 198 nascondi tutti i tipi.
- Misura: piano del componente 1596 pixel azzurri senza `hide_reference`, 0 con, 1596 dopo (ripristino ok). Sonda: `scripts_tmp/d5probe.py`.

## D6 — assiemi: export, box, immagini (2026-10-17)
- Test live `test_data_live` sez. 12: 183/183 (esito dopo tre correzioni, log `test_output/`, `%TEMP%\claude\d6_run3.log`).
  Numeri: box dell'assieme = unione dei box traslati, scarto 0,0 mm (min -1,2e-05 / max 230, 160, 25 mm);
  STL in un file: box del file = box del modello (230,000012 x 200 x 50 mm, scarto 0,0); STEP: 3 PRODUCT_DEFINITION, 3 istanze;
  STEP reimportato: volume 135456,7664 mm3 contro 135456,8204 (blocco 116607,26 + 2 x 9424,78), scarto 4e-7 (< 0,01 %).
- Trappole trovate:
  - `GetComponents` e' un metodo con argomento (`GetComponents(TopLevelOnly)`): chiamato come proprieta' (`_com`) dava
    "Parametro non facoltativo" e il box dell'assieme risultava vuoto. Corretto con `doc.GetComponents(True)`.
  - `IComponent2.GetBox` non e' affidabile per il box del componente (sovrastimava X di 0,165 mm). Ora il box si calcola dal
    pezzo (`GetExtremePoint`) portato nel sistema dell'assieme con `Transform2.ArrayData` (rotazione per colonne, traslazione in m).
    La rotazione e' verificata solo per traslazioni: vale la convenzione standard di `ArrayData`, da provare con un componente ruotato.
  - `GetBodies2` sull'assieme non e' valido: l'import di uno STEP d'assieme ora elenca i componenti di primo livello.
  - Export STL "un file per componente": SolidWorks scrive `<nome> - <componente>.stl` accanto al nome indicato; il controllo
    di esistenza ora cerca questi file (nel risultato `files`). Cosmetico da sistemare: il messaggio mostra "0 byte" per il file base.
  - Il test leggeva "il blocco" dopo aver aperto il cilindro senza chiuderlo (`open_document` non cambia il documento attivo):
    misurava il cilindro due volte. Ora il cilindro viene chiuso dopo il salvataggio.
  - Il test per componente contava solo i file, ignorando `ok`: ora conta anche l'esito.

## Gruppo D, resto (D7 D8 D1 D10 D4 D9 D2 D3) — 2026-10-17
- Metodo: sotto-agenti in git worktree (codice + test offline + sezione live scritta), riporto su main con `git diff` + `git apply --3way`.
  Trappola: i worktree degli agenti partono dal commit di `origin` (vecchio), non da HEAD -> far fare `git reset --hard <sha>` come primo passo.
- D7: `GetMomentOfInertia(0/1)` restituisce i termini fuori diagonale come PRODOTTI d'inerzia (segno opposto al tensore): misurato con un
  prisma ruotato di 30 gradi e baricentro fuori dagli assi. `IMassProperty2.SetCoordinateSystem(transform)` + `Recalculate` funziona e
  coincide col calcolo in Python (3,8e-17). `GetCoordinateSystemTransformByName(...).ArrayData`: righe della rotazione = assi del sistema.
- D8: `swFileLocationsMaterialDatabases` = 28 e' una preferenza STRINGA (`GetUserPreferenceStringValue`); sul PC contiene gia' 4 cartelle
  (Materiali personalizzati, Custom Materials, ...). Un `.sldmat` minimo (UTF-16 con BOM, struttura copiata da un materiale vero) viene
  accettato da `SetMaterialPropertyName2`.
- D1: `InsertDesignTable` non esiste nella type library (solo `GetDesignTable`/`IDesignTable`); Excel non installato.
- D4: la cattura a schermo dell'istanza nascosta e' 2389 x 1662. Con `swTiffScreenOrPrintCapture` (int 6) = 1 il SaveAs PNG/JPG/TIF usa la
  stampa: carta `swTiffPrintPaperSize` (int 10) 0 = Letter orizzontale (3300 x 2550 a 300 DPI), 11 = A0 (14043 x 9933); le double 8/9
  (larghezza/altezza carta) non contano. Valori originali 9 = 1 DPI e 8/9 = 0,1 m NON riaccettati (ora 300 e Letter). SolidWorks non
  centra il modello nella cattura (centro a +12 % in X, -3 % in Y): ritaglio sul contenuto con soglia 40 per canale (i bordi quasi bianchi
  spostavano il centro). `AddPerspective`/`RemovePerspective`/`HasPerspective` su `ActiveView` funzionano; RealView non si attiva
  (`Extension.ViewDisplayRealView` resta False), occlusione ambientale toggle 485 = False. Sonda: `scripts_tmp/dprobe.py`.
- D2: `swStepAP` = 75 accetta 242 (riletto) ma il file e' `CONFIG_CONTROL_DESIGN` (AP203); `swStepExportPreference` = 142 a 0..2 non
  cambia nulla (3 rifiutato). AP214 funziona.
- D9: `swImportNeutralAssemblyStructureMapping` = 579: 0/1 assieme, 2 pezzo multicorpo (3 rifiutato). `swMultiCAD_Enable3DInterconnect` = 691
  True: assieme collegato allo STEP (1 componente di primo livello, 4 in tutto); False: convertito (3 componenti). Toggle 701 e 220 senza
  effetto su questo file. `IPartDoc.ImportDiagnosis(True, False, True, 0)` ripara uno STEP senza una faccia: da 1 superficie a 1 solido
  di 120000 mm3 (codice 1). Nei file STEP di SolidWorks la sintassi e' `#12 = ADVANCED_FACE ( ...` (spazi prima della parentesi).
- D3: `.eprt`/`.easm` sono ZIP (`eModel` HSF V20.90, `preview.jpg`, `materials.xml` con un `<Entity>` per CORPO DISTINTO: assieme con
  3 istanze di 2 pezzi -> 2). `EModelView.EModelViewApp` (in-process) resta non inizializzato anche dopo `Init(False)`: `OpenFile` E_FAIL e
  poi crash di Python; `eDrawings.exe <file>` mostra sempre il titolo "eDrawings". Verifica quindi strutturale.

## Fase 4: gruppo E, sonde dal vivo (2026-10-18, `scripts_tmp/eprobe.py E5 E3 E1 E4 E4B E2`)
Trappole e nomi verificati (SW 2026 SP4.1, istanza dedicata nascosta, late binding):
- **E5** `CreateNewStudy2(nome, tipo, err)`: 0 statico, 1 frequenze, 2 buckling, 3 termico. `st.FrequencyStudyOptions.NoOfFrequencies` (default 5),
  `st.BucklingStudyOptions.BucklingModes` (default 1), `st.ThermalStudyOptions.SolutionType` (1 stazionario, 0 transitorio; default 1).
  `Results.GetResonantFrequencies(err)` = gruppi di 4 (modo, rad/s, Hz, periodo); `GetMassParticipation(err)` = (modo, X, Y, Z);
  `GetBucklingLoadFactors(err)` = (modo, fattore). Termico: `AddTemperature(VARIANT array facce, err)` poi `TemperatureBeginEdit()`, `Unit = 2`
  (gradi C), `TemperatureValue`, `TemperatureEndEdit` (proprieta'). `GetMinMaxThermal(comp, step, NULL, unit, err)`: comp 0 T, 1-3 gradiente xyz,
  4 gradiente modulo, 5-7 flusso xyz, 8 flusso modulo. **Unita' 2 sul flusso NON e' W/m2** (0,5617 = cal/s/cm2 al posto di 23500 W/m2): per
  gradiente e flusso usare unit 0 (SI). Grafici delle frequenze: 'Ampiezza1..n' (piu' 'Qualità1').
  Misure (trave 200x20x10 AISI 1020, mesh 4 mm, 7522 nodi): f1 203,733 Hz (atteso 203,2: +0,26 %), f2 404,49 (406,4: -0,47 %), f3 1261,9, f4 2426,1;
  partecipazione di massa modo 1: Z 0,612; buckling con 1000 N: 20,620 (atteso 20,562: +0,28 %), modo 2 81,83; termico 100/0 gradi C:
  T 100,000 / 0,000, gradiente 500,00 K/m, flusso 23500,0 W/m2 (k = 47 dalla libreria: Q = 23500 x 2e-4 m2 = 4,70 W).
- **E3** `GetStressForEntities2(True, 9, step, NULL, VARIANT array [corpo SW], 3, err)` con il CORPO (non le facce) da' tutti i nodi del corpo
  (3439 su 6876): il VM massimo per corpo coincide con quello globale nel corpo giusto. Assieme AISI 1020 + Lega 6061 incollati: FOS API
  1,93399 = 55,1485 / 28,5154 (alluminio, nodo in [104,10,-5]); acciaio 351,57 / 59,957 = 5,86. NB: `GetMinMaxStress` NON ha un argomento per
  scegliere il corpo (l'ipotesi del piano era sbagliata).
- **E1** `ContactManager.CreateContactSet(tipo, VARIANT array sorgenti, VARIANT array destinazioni, err)`: i tipi sono quelli di
  `swsContactSetTypeStaticNonLinear_e` anche per lo statico lineare: **0 senza compenetrazione, 1 incollato**, 2 accoppiamento forzato, 3 libero,
  4 parete virtuale (il globale `SetGlobalContact` usa invece 0 incollato, 1 libero, 2 senza compenetrazione). Con il tipo 0 credendolo
  "incollato" il blocco scivola via (97960 mm). `cs.SuppressUnSuppress()` solleva un'eccezione e dopo l'istanza si e' bloccata alla mesh: non usarlo.
  Misure (due blocchi 100x20x10 di testa, mesh 4): globale libero + locale incollato -> 0,796407 mm (monolite 0,7964); compressione 100 N:
  incollato 0,00049900, senza compenetrazione 0,00049896 (F L/(E A) = 0,0005); trazione con senza compenetrazione: 25002 mm (si stacca).
- **E4** `AddRemoteLoad(0 diretto, VARIANT array facce, 0 mm, x, y, z, err)`, poi `RemoteLoadBeginEdit()`, `ConnectionType = 0` rigido,
  `SetForceOrTranslationValues(True, bx, fx, by, fy, bz, fz)`, `RemoteLoadEndEdit`: forze nel riferimento del modello. Trave, 100 N -Z in (250,0,0):
  reazione (0,0,100) N, momento delle reazioni nodali attorno all'origine (0,-25,0) N*m (i momenti nodali MX..MZ sono 0 nei solidi), freccia 1,0945 mm
  (Eulero 1,10). Cuscinetto: `AddBearingLoad(CS, VARIANT array [faccia], err)`; **con la faccia nuda (o VT_DISPATCH) SolidWorks muore**
  (RPC 0x800706BE); con `GetSpecificFeature2` del CS "tipi incompatibili". Errore 6 = asse Z del CS non COINCIDENTE con l'asse del cilindro
  (parallelo non basta): CS costruito da uno schizzo 3D (punto sull'asse da `CylinderParams`, linea lungo l'asse marcata 8, linea lungo il carico
  marcata 2, punto marcato 1, `InsertCoordinateSystem`). `BearingLoadUnit = 0`, `XDirectionValue = 1000`, `DistributionType = 0` sinusoidale.
  Piastra 40x100x5 foro D10, 1000 N +Z: reazione -1000,000 N; sz medio sul foro per settori di 30 gradi: 0 gradi -25,7, +-30 -24,4, +-60 -5,7 MPa.
- **E2** `Mesh.ApplyMeshControl(VARIANT array facce, err)` -> `MeshControlBeginEdit()`, `Units = 0` (mm), `ElementSize`, `Ratio`, `MeshControlEndEdit`.
  Piastra 40x100x5 foro D4, 2000 N, mesh standard 2 mm: nodi entro 2 mm dal foro 549 -> 4157, lontani (|z| > 30) 11697 -> 11756, nodi sulla
  faccia del foro 102 -> 1026, Kt 2,487 -> 2,725 (Peterson 2,721).
- Sonde: una chiamata `execute_python` per passo (se una si blocca, l'output delle altre resta); `SW_MCP_TOOL_TIMEOUT=120` per non aspettare 300 s.

- 2026-10-18, regressione di rilascio: rilancio dell'istanza dedicata dopo la morte del processo = 23 s (15 s nella fase 5): il tempo concesso al tool di ripresa ora include SW_MCP_STARTUP_TIMEOUT + 60 quando il processo dedicato risulta terminato (`Popen.poll()`, senza COM).

## Fori fino a M70 e move_faces (2026-10-18)
- Database Hole Wizard: `C:\SOLIDWORKS Data\lang\english\swbrowser.sldedb` e' SQLite (tabelle `<STD>_DATA_HW_ScrewClearances`,
  `_TapDrills`, `_TappedHole`...), leggibile in sola lettura. Sonda dal vivo (`create_hole` con le tabelle estese, ISO e DIN, M18..M64):
  semplici OK fino a M64 tranne M60 (le misure di passaggio saltano M60 e M68: M52, M56, M64, M72); filettati OK tranne M52 (c'e' solo
  'M52x5.0'); lamati sopra M20 solo M24, M30, M36, M42, M48, M56, M64 (socket/hex/hex_cap/hex_machine; cheese e pan nessuno); svasati
  nessuno sopra M20 (DIN socket: M24). M68 e M70 non esistono per nessun tipo. Con una misura assente HoleWizard5 restituisce None.
- Foro "legacy" (HoleWizard5 con GenericHoleType 5, FastenerType = swWzdHoleTypes_e 0 semplice, SSize ""): rispetta Diameter, EndType
  e Depth; cieco = fondo PIATTO (nessuna punta anche passando 118 gradi); i Value1..12 per lamato/svasato legacy sono ignorati (esce un
  foro semplice). GetDefinition del foro legacy restituisce tutti zeri.
- Filettatura cosmetica: `InsertCosmeticThread2(Type, Diameter, Length, Note)` con lo spigolo circolare d'ingresso selezionato;
  Type 0 = cieca per Length, 1 = passante, 2 = fino alla successiva. Diameter = Ø nominale (es. 0,068 m), Note = richiamo ("M68x6").
- `InsertMoveFace3(MoveType, ReverseDir, Angle, Distance, TranslationParams, RotationParams, EndConditionType, OffsetDistance)`:
  facce selezionate con mark 1 (con mark 0 nessuna feature, misurato dal vivo); offset = Distance (ReverseDir verso l'interno);
  traslazione = TranslationParams [dx,dy,dz] in metri (un vettore unitario (1,0,0) sposta di 1 m!); rotazione = RotationParams
  [origine x,y,z in metri, rotazioni attorno a X,Y,Z in radianti], il parametro Angle e' ignorato; regola della mano destra.
  Una faccia scelta su uno spigolo puo' prendere la faccia piana vicina: per un foro dare un punto a meta' profondita'.
- Con il server MCP di Claude aperto sullo stesso PC, i test live stampano "Logging error ... PermissionError" sul file di log comune
  (`%LOCALAPPDATA%\solidworks-mcp\solidworks_mcp.log`, rotazione bloccata dall'altro processo): rumore, i test non ne risentono.

## Lotti di tool nuovi (tools_ext, 2026-10-18/19): note dei sotto-agenti
Ogni lotto: schemi in `solidworks_mcp/tools_ext/<lotto>.py`, metodi in `automation/ext_<lotto>.py` (o nei moduli esistenti per le estensioni),
test in `tests/test_ext_<lotto>_live.py`. Prove fatte con il laboratorio `scripts_tmp/lab.py` (istanza dedicata, codice ricaricato a ogni script).

### Lotto moka1

Test: `tests/test_ext_moka1_live.py` (M1..M5, per sezione da argv). Nessun tool nuovo: cambia solo il numero di parametri.
File toccati: `automation/modeling.py`, `automation/modeling_base.py`, `automation/sketch_constraints.py`, `modeling_tools.py`.

#### Helper nuovi
- `ModelingBase._select_any(doc, spec, unit, append, mark)`: seleziona un riferimento generico (`[x,y,z]` spigolo, nome di piano/feature,
  `{"face"|"edge"|"vertex":[..]}`, `{"plane"|"axis"|"feature"|"point":nome}`, `{"sketch":nome,"entity":id}`). -> (ok, msg, descrizione).
- `ModelingBase._sketch_entity_obj(doc, schizzo, id)`: segmento/punto di uno schizzo qualunque senza aprirlo.
- `SketchConstraintOperations._frame_to_model(sk)`: trasformazioni schizzo<->modello di qualunque ISketch (anche non attivo).

#### 1. create_reference_plane: mid_plane, line_point, normal_to_curve, parallel_point  [x] (mid_plane con metodo diverso)
- line_point -> `doc.CreatePlaneThruLineAndPt(True)`; normal_to_curve -> `doc.CreatePlanePerCurveAndPassPoint3(True, True)`;
  parallel_point -> `doc.CreatePlaneThruPtParallelToPlane(True)`. Selezione: linea/curva prima, punto dopo (l'ordine non conta). Tutti
  creano il piano; `InsertRefPlane` con questi vincoli non e' stato necessario (le chiamate dedicate funzionano e restituiscono il piano).
- mid_plane `[~]`: `InsertRefPlane` col vincolo MidPlane (128) NON crea nulla in SW 2026. Provati: 128, 128|4, 128|1, 128|2, 264, 136,
  384, 640, 8320, coppie (c1,c2) con 128 in uno dei due, e tutti i valori 0..42 del primo vincolo (con 2 facce o 2 piani selezionati,
  Mark 0 e 1): sempre None e nessuna feature. `CreateDefinition(swFmRefPlane=59)` restituisce None; sul `RefPlaneFeatureData` di un
  piano esistente `Selections` si imposta (il piano si sposta) ma `Type` e `Constraint(i)` non cambiano (`Constraint` e' proprieta'
  indicizzata non scrivibile in late binding; `Type=` ignorato). Soluzione: offset di mezza distanza dal primo riferimento
  (InsertRefPlane 8) con rilettura del piano (la posa e' controllata: il punto medio sta sul piano, altrimenti si inverte il verso
  e si riprova). Riporta `between_refs`, `offset_each`, `method`. Il piano NON resta legato alla seconda faccia (non e' un vero
  piano di mezzeria associativo). Rifiuta facce non parallele, coincidenti, non piane.
- Misure (blocco 20x40x30): mid x=0/x=20 -> x=10; y=40/y=0 -> y=20; z=0/z=30 -> z=15; front/Piano a 30 -> x=15;
  line_point normale (0.832,0,-0.5547) contiene spigolo e vertice (distanze 0.00000); normal_to_curve normale +-Y origine y=40;
  parallel_point normale +-X, distanza del vertice 0.
- Trappola: in questo template il piano Top ha normale +Z e mappa (u,v) -> (y,-x); Front normale +X con (u,v) -> (y,z).
- Trappola: `ISketch.ModelToSketchTransform` funziona anche su schizzi non attivi; `RefPlaneFeatureData.GetSelectionsCount` e' "in sola
  scrittura" in late binding.

#### 2. revolve_boss / revolve_cut: axis esterno  [x]
- `axis` accetta: id di segmento dello schizzo (come prima), nome di un asse di riferimento (stringa o `{"axis":nome}`),
  `{"edge":[x,y,z]}` (spigolo lineare), `{"sketch":nome,"entity":id}` (linea di un altro schizzo). Selezione con Mark=4.
- Trappola: per la linea di un ALTRO schizzo `Select4(Mark 4)` e `SelectByID2(..,"EXTSKETCHSEGMENT")` vengono accettati ma
  FeatureRevolve2 non crea nulla; funziona `SelectByID2("Linea1@Schizzo1","SKETCHSEGMENT",0,0,0,True,4,...)` (restituisce False
  ma la selezione c'e': si controlla il conteggio delle selezioni).
- Misure (rettangolo 10x10 a 10 mm dall'asse: V = 2*pi*10*100 = 6283.185): boss asse di riferimento 6283.185; con `{"axis":nome}`
  idem; 90 gradi 1570.8 (Pappo/4); taglio con asse di riferimento 6283.185 asportati; taglio con spigolo del modello 1570.796
  (quarto d'anello nel blocco); boss con linea di altro schizzo 6283.185. Il risultato riporta `axis_kind`.

#### 3. add_sketch_relation verso entita' esterne  [x] con pierce verso altro schizzo `[~]`
- Entita' esterne: `{"edge"|"vertex":[x,y,z]}`, `{"axis":nome}`, `{"sketch":nome,"entity":id|"P0-1"|"pt@x,y"}`; relazioni nuove "pierce"
  (sgATPIERCE) e "on_line" (punto -> coincident, linea -> collinear). Il risultato riporta `relations_added`, le coordinate finali
  dei punti dello schizzo (`points`) e fallisce se SW non crea nessuna relazione con entita' esterne.
- Verso spigoli/vertici del modello tutto nativo: pierce (tipo 40, punto = intersezione esatta), coincident, parallel, perpendicular,
  collinear, tangent, equal, concentric (cerchio vs spigolo circolare): geometria riletta con scarto < 0.001 mm.
- Verso un altro schizzo: coincident (punto-punto: il punto va alla proiezione; punto-segmento: sul segmento proiettato) funziona.
  pierce `[~]`: `SketchAddConstraints("sgATPIERCE")` con un segmento di un altro schizzo non crea nessuna relazione. Provati: Select4
  (mark 0/1/2/4, ordine inverso), `SelectByID2` EXTSKETCHSEGMENT, selezione della feature schizzo, `IModelDoc.AddRelation`, punto
  dell'altro schizzo: sempre 0 relazioni. (Con spigoli/assi del modello la stessa chiamata funziona.) Aggiramento: si calcola il punto in cui
  linea/arco/cerchio dell'altro schizzo fora il piano dello schizzo attivo (scegliendo il candidato piu' vicino al punto), ci si sposta
  il punto e lo si lega con coincident alla curva proiettata. Geometria esatta (scarto 0.000000 mm), ma il punto resta libero di
  scorrere lungo la proiezione (schizzo sottodefinito) e la relazione elencata e' `coincident`. Chiave `pierce_method`.
  Spline/ellissi: non supportate dal calcolo (errore chiaro: usare spigolo/asse del modello).
- `list_sketch_relations`: mappa nomi estesa (vertical, tangent, parallel, perpendicular, concentric, midpoint, equal, fixed,
  collinear, pierce) ed entita' esterne mostrate come "external" invece di far fallire l'elenco.
- Misure: pierce linea di altro schizzo punto (23.33333, 0) = atteso; cerchio (51.33975, 0) = candidato piu' vicino; pierce nativo
  spigolo (-20, 0) = atteso; coincident vertice (-20, 30) = proiezione; equal 40.0 mm; tangent distanza 3.00000 = raggio.

#### 4. extrude_boss / extrude_cut: start_from  [x]
- `FeatureExtrusion3/FeatureCut4` parametro T0: 0 piano dello schizzo, 1 superficie, 2 vertice, 3 offset (swStartConditions_e).
  Superficie: la faccia si seleziona DOPO lo schizzo con **Mark=32**; vertice: **Mark=0**; con gli altri mark (1,2,4,8,16,64)
  la chiamata solleva un'eccezione COM o non crea nulla. Offset: T0=3 con StartOffset; il segno positivo e' lungo la normale dello
  schizzo (sia boss che cut); FlipStartOffset=True inverte.
- La partenza mantiene la direzione dell'estrusione (normale dello schizzo). Nota: per i TAGLI da un piano la direzione di default
  e' opposta alla normale (dal Top il taglio va verso -z); `reverse` nel taglio e' "Flip side to cut" (taglia l'esterno del
  profilo), non inverte la direzione.
- `start_offset` senza `start_from` ora usa T0=3 (prima T0=0): stesso risultato misurato (+141.372 mm3), quindi nessuna regressione.
- Trappola nelle prove: `DeleteSelection2(3)` di una feature cancella anche lo schizzo assorbito.
- Misure (cerchio r=3 su blocco alto 30, colonna alta 25 accanto): boss da faccia z=25, da vertice, da offset 25, start_offset=25:
  +141.372 mm3 (= pi*9*5); taglio da faccia, vertice, offset: -282.743 (= pi*9*10).

#### 5. list_entities: tipo e parametri  [x]
- Facce: `type` da `ISurface.Identity` (4001 plane, 4002 cylinder, 4003 cone, 4004 sphere, 4005 torus, 4006 bspline, 4007 blend, 4008 offset,
  4009 extrusion, 4010 revolution). Ordine dei valori MISURATO: PlaneParams = normale(3)+punto(3); CylinderParams = origine(3)+asse(3)+raggio;
  ConeParams = origine(3)+asse(3)+raggio nell'origine+semi-angolo (rad); SphereParams = centro+raggio; TorusParams = centro(3)+asse(3)+raggio
  maggiore+minore. Spigoli: `ICurve.Identity` (3001 line, 3002 circle, ...); LineParams = punto(3)+direzione(3); CircleParams = centro(3)+asse(3)+raggio.
- Piano: `normal` e' la normale USCENTE della faccia (Face.Normal), non quella di PlaneParams; `distance_from_origin` = n . p (con segno).
- Cono: l'origine non e' sempre l'apice (raggio 10 a z=20 in un caso, 0 in un altro): `apex` = origine + asse * r / tan(semi-angolo), verificato con
  due coni opposti (apice a z=22 con asse -z, apice a z=8 con asse +z).
- Parametro `include_params` (default true; false = righe compatte). Lunghezze in `unit`, direzioni adimensionali, angoli in gradi.
- Misure: cilindro r=10, cono semi-angolo 26.5651 (atteso 26.5651), apice (0,0,22), toro del raccordo 9/1 centro (0,0,1), sfera r=7 centro (0,0,15),
  toro 15/3 centro (0,0,10), spigolo circolare r=10 centro (0,0,30), unita' cm raggio 1.0.

#### RICHIESTE A OPUS
- Aggiornare i conteggi dei tool nel test offline (nessun tool nuovo da parte mia).
- Se serve un vero piano di mezzeria associativo (mid_plane nativo) servirebbe un'altra via API (non trovata); il tool lo dichiara.

### Lotto moka2

Codice: `solidworks_mcp/automation/ext_moka.py` (mixin `MokaOperations`), schemi `solidworks_mcp/tools_ext/moka.py` (7 tool nuovi,
`delete_body` in `DESTRUCTIVE`). Test: `tests/test_ext_moka2_live.py` (sezioni M1..M4). Prove: `scripts_tmp/moka2_*.py`.
File originali della moka COPIATI (mai toccati gli originali) in `test_output/moka2_src/` (non versionato) e letti con il laboratorio.

#### Tool

### add_cosmetic_thread  [x]
- API: `FeatureManager.InsertCosmeticThread3(8, "Machine Threads", size, Ø, end, depth, "")` con lo spigolo selezionato, POI `GetDefinition` ->
  `AccessSelections(doc, VARIANT nullo)` -> set `Standard=8` (ISO), `StandardType="Machine Threads"`, `Size`, `ThreadCallout` ->
  `ModifyDefinition`. Valori presi dai file originali della moka (Boiler M56, Valve M8, Knob M6).
- TRAPPOLE: (1) `InsertCosmeticThread3` IGNORA standard, tipo e misura (rilegge `Standard=-2`, `Size=''`): vanno scritti dopo con ModifyDefinition.
  (2) `CreateDefinition(swFmCosmeticThread=29)` restituisce None. (3) `DiameterType` (2 = maggiore, 3 = minore) lo decide SolidWorks
  dallo spigolo (foro -> 2, albero -> 3) ed e' di sola lettura; il `Diameter` passato e' preso cosi' com'e': per un albero va dato il diametro MINORE.
  (4) `Size` non e' validato (anche 'BOGUS' viene accettato). (5) Con "fino alla fine"/"fino al successivo" SolidWorks ricalcola `BlindDepth` =
  lunghezza reale. (6) `GetTypeName2` = `CosmeticThread`; non e' tra le feature di primo livello cercate da `_features` (sotto-feature del taglio).
  (7) Una seconda filettatura sullo stesso spigolo viene creata lo stesso (non controllato).
- Diametro minore esterno: misurato sui file della moka M8 = 6,619 e M56 = 49,971. Formula trovata: D1 ISO (D - 1,0825 P) meno lo scostamento
  6g (0,015 + 0,011 P mm): M8 6,6181, M56 49,97075 (scarto < 1 um). E' il valore che il tool usa. Interno: Ø maggiore = nominale (Knob M6 = 6,0).
- Interno/esterno dedotto da `FaceInSurfaceSense` della faccia cilindrica adiacente (True = foro). Avviso se `kind` contraddice la geometria.
- Test: vedi M1.

### fill_pattern  [x]
- API: `FeatureManager.FeatureFillPattern` e' OBSOLETO (restituisce sempre None, nessuna feature, provate 150 combinazioni di marche).
  Funziona: selezioni con le marche della doc di `IFillPatternFeatureData` (confine = faccia o schizzo **16384**, direzione **1**, punto seme
  (vertice / punto di schizzo) **3**, feature da ripetere **4**) -> `CreateDefinition(105)` -> set delle proprieta' -> `CreateFeature`.
- TRAPPOLE: (1) `PatternFillBoundaryArray`/`PatternFeatureArray` NON vanno impostati (basta la selezione con le marche). (2) La **direzione e'
  obbligatoria in pratica**: senza, con il seme "forma predefinita" CreateFeature restituisce None; il tool usa il primo lato rettilineo del
  confine (spigolo della faccia o segmento dello schizzo). (3) Alla creazione SolidWorks IGNORA le misure del seme (Diameter, Dimension,
  Diagonal, OuterRadius...) e usa 8 mm di default: il tool le corregge con `GetDefinition` + `ModifyDefinition` subito dopo. (4) Leggere
  `FeaturesToPatternType` da una definizione nuova (non ancora creata) da' errore COM; sulle definizioni lette da feature esistenti servono
  `AccessSelections(doc, VARIANT nullo)` e `ReleaseSelectionAccess`. (5) Il margine e' misurato dal BORDO dell'istanza al confine (verificato
  col conteggio a mano). (6) `PatternLayoutType`: 0 = concentrico, 1 = quadrato, 2 = poligono, 3 = perforazione. (7) Il seme e' al centro
  del confine; con feature esistente e' quella feature. (8) Un `create_sketch` + `FeatureFillPattern` con tanti fori (concentrico, passo 8)
  e' lentissimo (minuti): il laboratorio sembra appeso.
- Conteggio istanze: facce create / facce di una istanza (cerchio 1, quadrato/rombo 4, poligono n lati; per feature esistenti, facce create dal seme).
- Test: M2.

### list_bodies / delete_body / combine_bodies / insert_part  [x]
- `list_bodies`: `GetBodies2(-1, False)`; volume/area/baricentro da `Body2.GetMassProperties(1000)`, ingombro `GetBodyBox`, punto di faccia scelto lontano
  (> 0,1 mm) dalle facce degli altri corpi (un punto sul bordo comune identificherebbe due corpi).
- `delete_body`: corpi selezionati con `Body2.Select2(append, SelectData marca 0)` + `FeatureManager.InsertDeleteBody2(keep)`; feature `DeleteBody`.
- `combine_bodies`: `InsertCombineFeature` NON crea nulla con i valori di `swCombineBodiesOperationType_e` (0/1/2): servono quelli di
  **`swBodyOperationType_e`: intersect 15901, cut 15902, add 15903**. Add e common: corpo principale **nullo** e TUTTI i corpi nell'array;
  subtract: principale + strumenti. Feature `CombineBodies` ("Abbina1" in italiano).
- `insert_part`: `PartDoc.InsertPart3(path, opzioni, config)` con opzioni 1|2 (solidi+superfici) + 512 (rompi il collegamento). Il corpo inserito NON si
  fonde con quelli esistenti (anche se sovrapposto: volumi sommati, nome `<corpo>_<file>`). Posizione: `InsertMoveCopyBody2` con il corpo selezionato
  con **marca 1**; traslazione e rotazione non stanno nella stessa feature (si creano due feature: prima rotazione, poi traslazione).
  TRAPPOLA: i parametri `RotAngleX/Y/Z` ruotano attorno agli assi **Z/Y/X** (misurato su un blocco 10x20x30): il tool li inverte, cosi' `rotate=[rx,ry,rz]` e' attorno a X,Y,Z.
- Test: M3.

### get_feature_definition  [x]
- `feat.GetDefinition` + `AccessSelections`; il lettore e' scelto dal nome del tipo (`CosmeticThread`, `RefPlane`) o riconoscendo i membri dell'oggetto
  (`GetEndCondition` estrusione/taglio, `GetRevolutionAngle`, `FastenerSize` Hole Wizard, `D1Spacing` ripetizione lineare, `TotalInstances` circolare,
  `PatternLayoutType` riempimento, `DefaultRadius` raccordo, `EdgeChamferAngle` smusso, `Thickness` shell, `GetProfileCount` loft, `Profile` sweep).
  `GetTypeName2` delle estrusioni: `Extrusion`, ma nei file aperti da SW anche `ICE`: per questo il riconoscimento e' dai membri.
- Piano di riferimento: `GetSpecificFeature2` -> `Transform.ArrayData` (9 della rotazione, poi traslazione): gli assi sono le RIGHE (misurato: piano
  frontale spostato di 10 in X -> origine [10,0,0], normale [1,0,0]).
- Genitori/figlie con `GetParents`/`GetChildren`, quote con `_sketch_dimensions`. Tipi non gestiti: tipo + genitori + quote + nota.
- Letti dai file originali: `Filter_1` Fill Pattern1 (circolare, su feature Cut-Extrude1, quote 3/3 mm), `FilterPlate_1` Fill Pattern18 (circolare, seme
  cerchio Ø0,4, confine Sketch6), Cosmetic Thread Boiler M56/Valve M8/Knob M6 (vedi sopra). Hole Wizard legacy: tutto zero (gia' noto).
- Test: M4.

### Toolbox (vite ISO 7046-1 M5x12)  [~] NON FATTO
- Prove: `C:\SOLIDWORKS Data\browser\ISO\bolts and screws\cross-recessed head screws\countersunk flat head cross recess screw_iso.sldprt` esiste
  (Toolbox installato, 1885 file), ma e' il MODELLO con sole configurazioni `Default` e `PreviewCfg` guidato da quote/equazioni (`Length@BodySke`...),
  la misura vera viene dal database Toolbox. `toolboxapi.chm` documenta solo l'add-in di configurazione (nessuna API di inserimento);
  `app.GetAddInObject` con i ProgID plausibili restituisce None nell'istanza dedicata (add-in non caricato).
  Alternativa praticabile senza tool nuovo: `insert_part` del file Toolbox copiato + `set_dimension_value` sulle quote del modello, oppure ricostruire la vite
  con rivoluzione + taglio di loft + ripetizione circolare (come nel piano).

#### RICHIESTE A OPUS
- Aggiornare i conteggi dei tool (test offline: "N tool esposti" 210 -> 217 e i due di execute_python) e `EXPECTED_TOOLS` in `tests/live_common.py`.
- Aggiornare ATLANTE.md (ext_moka.py, tools_ext/moka.py, test_ext_moka2_live.py) e le voci di PIANO_MOKA.md 1, 2, 6, 8, 10.
- Niente modifiche necessarie ai file non miei.

#### Esito (2026-10-19)
- `tests/test_ext_moka2_live.py`: **49/49 PASS** (M1 10, M2 15, M3 17 con insert_part, M4 11, + esposizione tool e PID).
- Numeri chiave misurati: cosmetica M8 interna Ø8,0 prof. 12; M56 esterna Ø49,97075 (SW originale 49,971), M56x4 Ø51,611; fill_pattern quadrata su feature 45 istanze
  (volume 27172,57 = 30000 - 45 x 62,83), perforazione Ø4 43 istanze (27298,23), quadrato 4x4 45 (26400,00), rombo d=6 45 (25950,00), confine da schizzo 45;
  combine subtract/add/common 24000/56000/8000 mm3; insert_part con traslazione [20,5,0] ingombro [20,5,0,30,25,30], rotazione X 90 ingombro [0,-30,0,10,0,20].
- Offline: 145/148 (i 3 che falliscono sono i conteggi dei tool: 239 esposti, execute_python); pyflakes 0 sui 3 file miei + test.
- Laboratorio `moka2` chiuso (`labrun.py moka2 --quit` -> "chiuso"); PID del test chiuso.

### Lotto sketch2

File: `solidworks_mcp/automation/ext_sketch2.py` (mixin `Sketch2Operations`), `solidworks_mcp/tools_ext/sketch2.py` (schemi),
`tests/test_ext_sketch2_live.py` (50/50 PASS, istanza dedicata), prove in `scripts_tmp/sk2_*.py`.
Offline: 145/148 (i 3 falliti sono solo i conteggi dei tool: "210 tool esposti" e i due di execute_python). pyflakes 0.
Tool aggiunti: 16 (vedi sotto). Nessuna richiesta di modifica ad altri file.

#### Tool e stato

| Tool | API | Stato |
|---|---|---|
| `trim_sketch_entities` (power, closest, corner, two_entities, inside, outside) | `SketchManager.SketchTrim` | [x] power/closest/inside/outside misurati; corner e two_entities [~] (vedi trappole) |
| `extend_sketch_entity` | `SketchManager.SketchExtend` | [x] estremo misurato (40,0), anche dal lato sinistro |
| `sketch_chamfer` (distance_distance, distance_angle, equal, corner=[x,y]) | `SketchManager.CreateChamfer` | [x] lato 11.1803 (5x10), 5.6569 (4 uguale), 6.9282 (6 e 30 gradi), tagli misurati |
| `sketch_linear_pattern` | `ModelDoc.CreateLinearSketchStepAndRepeat` | [x] 4 cerchi -> ultimo (30,0); 3x2; a 30 gradi (17.3205, 10) |
| `sketch_circular_pattern` | `ModelDoc.CreateCircularSketchStepAndRepeat` (+ fallback RotateOrCopy) | [x] 4 cerchi attorno all'origine, linea 3x60 gradi, rettangolo 180 |
| `transform_sketch_entities` (move, rotate, scale + copy/copies) | `ModelDocExtension.MoveOrCopy/RotateOrCopy/ScaleOrCopy` | [x] coordinate riletta in tutti i casi, anche piano Top |
| `draw_center_rectangle`, `draw_3point_rectangle` (+center), `draw_parallelogram` | `CreateCenterRectangle`, `Create3PointCornerRectangle/CenterRectangle`, `CreateParallelogram` | [x] vertici riletti |
| `draw_tangent_arc` | `CreateTangentArc` (tipo 1) | [x] centro (20,15), R 10, scarto di tangenza 0 gradi |
| `draw_parabola` | `CreateParabola` | [x] lunghezza 22.9559 = 10*(sqrt2+asinh1) |
| `draw_equation_curve` (y=f(x) o parametrica) | `CreateEquationSpline2` | [x] estremi e punto medio verificati, anche con rotazione, offset e unit=inch |
| `create_3d_sketch`, `draw_3d_line`, `draw_3d_spline`, `draw_3d_point` | `Insert3DSketch`, `CreateLine`, `CreateSpline2`, `CreatePoint` | [x] estremi riletti; sweep d=4 lungo polilinea: 658.079 mm3 vs pi r^2 L = 657.984 (0.0145 %) |
| `close_3d_sketch` | - | non serve: `close_sketch` chiude lo schizzo 3D (verificato) |
| `draw_conic` | `CreateConic` | NON esposto, [~]: l'API crea una curva (tipo 5) ma i 4 punti non sono "fuoco, vertice, estremi" come per la parabola |
| `intersection_curve` | `SketchManager.IntersectCurves` | NON fatto, [~]: 3 approcci, nessuna curva creata |
| `silhouette_entities` | - | non provato (richiede viste/disegno) |

Solo `trim_sketch_entities` e' registrato come distruttivo (`DESTRUCTIVE` in `tools_ext/sketch2.py`).

#### Trappole misurate (il docstring in cima a `ext_sketch2.py` le riassume)

- **SketchTrim**: il ritorno non e' affidabile (False con lavoro fatto, True senza effetto). Serve SEMPRE una selezione.
  Misure su orizzontale 0..40 + verticale x=20, entita' selezionata con `Select4`:
  - codice 0 (Closest) = vero power trim: pick (30,0) -> resta 0..20; pick (5..10,0) -> resta 20..40; un'entita' senza
    intersezioni viene cancellata; funziona anche sui cerchi (toglie il quarto cliccato). Il tool lo usa per `power` e `closest`.
  - codice 3 (EntityPoint) NON e' un power trim: taglia l'entita' nel punto (30,0) e toglie il lato iniziale (resta 30..40).
  - codice 4 (Entities): toglie sempre 0..20 qualunque sia il pick. Non esposto.
  - codici 1 (Corner) e 2 (TwoEntities) IGNORANO il punto di pick (nemmeno `SelectData.X/Y/Z` e `SelectByID2` con coordinate lo
    registrano). Corner: ha tenuto sempre 0..20 e -10..0; TwoEntities dipende dall'ordine di selezione. Il lato che resta lo
    sceglie SolidWorks: il tool lo dichiara e restituisce `segments`. Per controllare il lato usare due power trim.
  - codici 5 (Outside) e 6 (Inside): selezionare i due confini e poi l'entita' (marchi 0, qualunque marcatura funziona).
  - `x,y` di SketchTrim sono nelle coordinate dello SCHIZZO (provato su Top e Right).
- **SketchExtend(x,y,0)** funziona con l'entita' selezionata e (x,y) vicino all'estremo; senza intersezione ritorna False e non cambia nulla.
- **CreateChamfer(tipo, Distance, AngleORdist)**: tipo 0 distanza-angolo (angolo in radianti), 1 distanza-distanza, 2 uguale
  (il terzo argomento non puo' essere 0 nemmeno per il tipo 2 -> eccezione COM). La PRIMA entita' selezionata riceve il TERZO
  argomento; per distanza-angolo la distanza va sulla SECONDA (l'angolo e' fra lo smusso e quella linea) -> il tool inverte
  l'ordine di selezione cosi' che `distance` sia sempre lungo entity1. Il ritorno e' il segmento dello smusso. Selezionando il
  solo vertice la distribuzione fra le due linee e' casuale: il tool risolve le due linee e le seleziona lui.
- **Ripetizione lineare**: angoli in radianti; `DeleteInstances` non ha avuto effetto con "2", "2,1", "3 1", "1;" (omesso, non
  esposto). Con count_y > 1 SolidWorks crea 2 linee di costruzione (listate in `construction_ids`).
- **Ripetizione circolare**: centro = centro del riquadro della selezione + R*(cos A, sin A), passo POSITIVO = ORARIO, con
  `PatternRotate=False` le istanze escono sbagliate (risolutore), con True giuste. Il tool calcola R e A dal `center` richiesto,
  passa il passo con il segno cambiato (antiorario positivo) e verifica le istanze; se non tornano le cancella e usa il
  fallback RotateOrCopy. In tutti i test e' bastato il metodo nativo.
- **MoveOrCopy/RotateOrCopy/ScaleOrCopy**: coordinate nello spazio dello SCHIZZO anche su Top/Right (verificato). `RotateOrCopy`
  ruota attorno all'ASSE base->dest (dest = base + (0,0,0.01) = normale dello schizzo), non attorno a un punto. Con base != origine
  lo schizzo diventa "soluzione non valida" e la geometria sparisce (misurato: 0 segmenti): il tool sposta il centro
  nell'origine, ruota e riporta. Con base=dest=origine nessun effetto. `KeepRelations=True` lascia le relazioni inferite
  (orizzontale, coincidente con l'origine) che deformano o bloccano il risultato: default False. Con `NumCopies=n` le copie
  sono cumulative (30, 60, 90 gradi). `ScaleOrCopy(copy=True)` NON copia: il tool copia sul posto con `MoveOrCopy` a spostamento
  nullo (duplica) e scala la copia (k-esima copia = scala^k). `SketchModifyRotate/Translate` non fanno nulla; `SketchModifyScale`
  scala tutto lo schizzo attorno all'origine (non usato).
- **Rettangoli**: `CreateCenterRectangle(cx,cy,..,x2,y2)` = centro + angolo, crea anche 2 diagonali di costruzione
  (nei `construction_ids`). `Create3PointCornerRectangle(p1,p2,p3)`: spigolo p1-p2, la larghezza e' la distanza di p3 dalla
  retta p1p2. `Create3PointCenterRectangle(c, p2, p3)`: c centro, p2 meta' di un lato, p3 un angolo. `CreateParallelogram`:
  quarto vertice p1 + p3 - p2.
- **CreateTangentArc**: tipo 1 (forward) e 3 (back) danno l'arco tangente (relazione inferita, scarto misurato 0 gradi), tipi 2 e 4
  danno un arco normale (centro sulla direzione della linea). Il punto di partenza deve essere un estremo di un'entita'.
- **Parabola/conica**: `CreateParabola` ok (tipo 5). `GetCurve.Evaluate2` sulla parabola da' valori assurdi: si verifica con
  `GetLength` e con gli estremi. `CreateConic`: con i punti della parabola ritorna None; con altri crea curve di tipo 5 senza
  `GetFocalPoint2/GetApexPoint2`; le lunghezze misurate (18.5964 per fuoco (6,0), vertice (10,0), estremi (0,+-8)) non coincidono
  ne' con la mezza ellisse a=10 b=8 (28.36) ne' con una conica razionale quadratica semplice: la dipendenza dal 1o punto e'
  forte, il 2o conta solo se vicino al 1o. Non esposto (3 approcci falliti).
- **CreateEquationSpline2(X,Y,Z,t0,t1, IsAngleRange, rot[rad], xOff[m], yOff[m], lock, lock)**: espressioni e intervalli
  nell'unita' di lunghezza del DOCUMENTO (mm) e stringhe; offset in METRI; rotazione in radianti; seno/coseno in radianti;
  espressione sbagliata -> None. L'oggetto spline NON ha GetStartPoint2: si legge con `GetCurve.GetEndParams` (VARIANT per
  riferimento) + `Evaluate2` (il parametro NON va da 0 a 1: leggerlo da GetEndParams). Il tool converte `unit` -> unita' del
  documento moltiplicando le espressioni, riscrive la variabile `x` in `t` per il caso esplicito, e verifica gli estremi
  valutando l'equazione in Python (solo funzioni ammesse, `eval` con namespace ristretto).
- **Schizzo 3D**: `Insert3DSketch(True)` apre, `close_sketch` (InsertSketch) chiude; il nome (`Schizzo3D1`, tipo
  `3DProfileFeature`) esiste gia' durante la modifica. `sweep` accetta il nome come `path_sketch` senza modifiche. Il solo
  `CreatePoint` va usato nello schizzo 3D: dopo un `doc.CreatePoint2` il punto restava a (0,0,0) o con Z=0.
  Sweep con spigolo: scarto 0.0145 % su pi r^2 L (sfera/tappo dello spigolo), ben sotto la tolleranza 0.5 % del test.
- `list_sketch_entities` classifica i cerchi come `arc` (start == end): nel test un cerchio e' un arco con inizio = fine.

#### RICHIESTE A OPUS
- Aggiornare i conteggi dei tool (+16: trim_sketch_entities, extend_sketch_entity, sketch_chamfer, sketch_linear_pattern,
  sketch_circular_pattern, transform_sketch_entities, draw_center_rectangle, draw_3point_rectangle, draw_parallelogram,
  draw_tangent_arc, draw_parabola, draw_equation_curve, create_3d_sketch, draw_3d_line, draw_3d_spline, draw_3d_point = 16).
- (facoltativo) `_active_sketch_name` in `sketch_constraints.py` cerca solo `ProfileFeature`: sugli schizzi 3D da' il nome sbagliato
  (l'ultimo schizzo 2D). Il mio modulo usa `_s2_name`, che li gestisce, ma `list_sketch_entities` & co. restano da correggere.
- `LIMITI.md` / `STATO.md`: copiare dallo stato sopra; `ATLANTE.md` gia' elencava il mixin?: aggiungere `ext_sketch2.py`.

### Lotto curves

Moduli: `solidworks_mcp/automation/ext_curves.py` (mixin `CurvesOperations`), `solidworks_mcp/tools_ext/curves.py` (6 tool, nessuno distruttivo).
Test: `tests/test_ext_curves_live.py` -> **89/89 PASS** (sezioni `H V P S C T`, circa 5 minuti). Offline: 145/148, i 3 che falliscono sono i
conteggi dei tool ("N tool esposti", execute_python nascosto / riattivato; ora 239 tool con gli altri lotti). pyflakes 0 sui miei file.

#### Come si misura una curva (nessun volume, nessuna faccia)
`feat.GetSpecificFeature2` -> `IReferenceCurve.GetSegments` (spigoli) -> `edge.GetCurve`, `edge.GetCurveParams2` (indici 6 e 7 =
parametri estremi) -> `ICurve.GetLength3(t0, t1)` = lunghezza; estremi dai vertici (`GetStartVertex.GetPoint`), se mancano `Evaluate2`.
**Trappola**: `ICurve.Evaluate2(t)` e' affidabile solo per l'elica; su rette/curve proiettate/BCurve restituisce punti sbagliati
(es. segmento da z=40 a z=10: Evaluate2 dava z=30..0). Per campionare una curva si usa `ICurve.GetTessPts(tol, tol, start, end)`
(`_curve_sample`), per la distanza di un punto `edge.GetClosestPointOn` (`_curve_distance`). Tutte le curve riportano nel risultato
`length`, `start_point`, `end_point`, `mid_point` (punto della tassellazione a meta'), `segments`.
Sweep lungo una curva: `sweep(path_sketch=<nome feature della curva>, circular_diameter=d)` funziona senza modifiche (elica, composita):
`_select_feature` seleziona qualunque feature con mark 4. Nessuna richiesta a Opus su `sweep`.

#### Tool
1. `create_helix` [x] - `InsertHelix(Reversed, Clockwised, Tapered, Outward, Helixdef, Height, Pitch, Revolution, TaperAngle, Startangle)`,
   void: l'esito si legge dalla feature nuova (tipo `Helix`); metri e radianti; si seleziona la FEATURE schizzo (Select2 mark 0).
   Definizioni 0 passo+giri, 1 altezza+giri, 2 altezza+passo, 3 spirale. Il risultato riporta passo/altezza/giri RISOLTI da SolidWorks
   (leggendo `IHelixFeatureData`), lunghezza misurata, lunghezza calcolata (integrale numerico) e scarto, `handedness`.
   Misure: R=10, passo 5, 8 giri: lunghezza 504.22658 vs 504.2439 (0.0034 %); molla = sweep di cerchio d=1: volume 395.938 vs pi r^2 L =
   396.032 (0.0237 %). Conica 10 gradi: raggio finale 17.0531 = R + h tan(10) esatto, lunghezza 0.0028 %. Spirale (passo radiale 5, 4 giri):
   raggio finale 30, lunghezza 0.0008 % vs forma chiusa di Archimede.
   Trappole: (a) per la spirale `Outward` non cambia nulla: l'interno si ottiene con `Reversed=True` (se il raggio diventerebbe negativo
   SolidWorks non crea nulla, il tool lo spiega); (b) `Clockwise=True` + `Reversed=False` da' un'elica SINISTRORSA rispetto alla direzione
   di avanzamento (misurato con la tassellazione: default left, clockwise=False right, reverse left->right invertito, entrambi left),
   `Reversed` porta l'elica dall'altra parte del piano dello schizzo (z finale -10); (c) il parametro `Height` passato viene ignorato con
   definizioni a passo+giri (e viceversa), il tool passa 0.
2. `create_variable_pitch_helix` [x] - `FeatureManager.InsertVariablePitchHelix(Reversed, Clockwise, Helixdef, Startangle)` +
   `AddVariablePitchHelixSegment(a, diametro, passo)` x N + `EndVariablePitchHelix`.
   Trappole: (a) `EndVariablePitchHelix` e' una PROPRIETA' in late binding (`fm.EndVariablePitchHelix`, chiamarla con `()` da' "NoneType
   not callable" e la feature NON si chiude); (b) `AddVariablePitchHelixFirstPitchAndDiameter` seguito dai segmenti fa fallire la chiusura
   (nessuna feature): la prima riga della tabella si da' come primo segmento con a=0; (c) il primo argomento di AddSegment e' CUMULATIVO:
   giri totali (Helixdef 0) o altezza totale in metri (Helixdef 2); Helixdef 1 non crea nulla; (d) il passo varia linearmente con
   l'angolo ma il diametro varia linearmente con l'ALTEZZA (misurato campionando la curva: z=11.2 -> r=12.66, lineare in z). Il tool
   accetta segmenti per-segmento (non cumulativi) e li somma. Misure: 2 giri a passo 4 + 1 giro 4->8 con diametro 20->30: altezza 14,
   raggio finale 15, lunghezza 203.09542 vs 203.1110 (0.0077 %), sweep d=1 volume 159.392 vs 159.511 (0.074 %); definizione altezza+passo:
   altezza 30, lunghezza 0.0126 %.
3. `project_curve` [x] - `InsertProjectedSketch2(Reverse)` con schizzo (mark 0) + facce (mark 0), oppure due schizzi (mark 0). Linea su
   cilindro R=20: estremi a raggio 20 (x=10, y=+17.3205), `reverse` -> y=-17.3205; schizzo su schizzo (cerchio R=10 x retta z=x+10):
   lunghezza 76.40396 = perimetro dell'ellisse (scarto 0.0000 %), punti iniziale e intermedio con raggio 10 e z=x+10.
   `both_directions` [~]: `IProjectionCurveFeatureData.Bidirectional = True` + `ModifyDefinition` solleva un'eccezione RPC
   (-2147417851) e `CreateDefinition(14)` + `CreateFeature` restituisce None (provati 3 approcci): il tool crea una SECONDA curva nel
   verso opposto (`other_direction_feature`), cioe' lo stesso risultato visivo di "bidirezionale" con due feature.
4. `split_line` projection [x] e silhouette [x], intersection [~] - `InsertSplitLineProject(IsDirectional, FlipDir)`, `InsertSplitLineSil()`,
   `IFeatureManager.InsertSplitLineIntersect(CompleteOption)`. SONO VOID/SILENZIOSE: se i mark sono sbagliati non fanno nulla e non
   danno errore (ritorno None, nessuna feature, nessun dialogo). **Mark misurati** (griglia di prove): proiezione = schizzo mark **4** +
   facce mark **1**, `IsDirectional=False` (proietta in entrambi i versi: lo schizzo anche sotto al blocco taglia la faccia; `FlipDir`
   non serve); silhouette = piano di direzione mark **2** + facce mark **1**. Con altri mark (0,1,2 per lo schizzo; 2 per le facce...)
   nulla. Misure: cerchio r=10 sulla faccia superiore di un blocco 80x80x20: facce 6 -> 7, aree 314.1593 (= pi*100) e 6085.8407
   (= 6400 - pi*100); silhouette di un cilindro R=20 h=50 rispetto al piano frontale: facce 3 -> 4, due meta' da 3141.5927 (= pi R h).
   Intersezione: provati strumento = piano di riferimento con mark 1/2/4/8, bersaglio = faccia o corpo con mark 1/2/4, `CompleteOption`
   0-3: mai una feature (in alcune combinazioni con mark 8/16 lo script si appende in attesa: evitare). Il tool restituisce errore con
   "Limite noto". Verifica automatica: numero di facce prima/dopo e aree delle facce nuove (`new_face_areas`).
   Attenzione: durante la ricerca dei mark il laboratorio si e' appeso piu' volte su combinazioni con mark 8/16 e `IsDirectional=True`.
5. `composite_curve` [x] - `doc.InsertCompositeCurve` e' una PROPRIETA' (late binding: leggerla esegue il comando; chiamarla con `()`
   da' "bool is not callable" dopo averla gia' eseguita). **Selezione con mark 1** (con mark 0 nessuna feature). Spigoli del modello via
   `_select_point(kind=edge, mark=1)`, entita' di schizzo via `seg.Select4(append, sd mark 1)` anche su schizzi chiusi. Misure: 8 spigoli
   superiori di un blocco con vertici raccordati r=10: lunghezza 302.83185 = 240 + 20 pi (esatta); retta 30 + arco r=10 (90 gradi) + retta 30
   da schizzo: 75.70796 = 60 + 5 pi, sweep d=2 volume 237.844 = pi r^2 L (scarto 0.0000 %). Per un sweep sullo STESSO blocco il tubo si
   fonde col blocco (volume aggiunto non confrontabile): per questo il test usa lo schizzo. Gli estremi `start_point/end_point` di una
   composita multi-spigolo sono quelli del primo e ultimo spigolo nell'ordine di SolidWorks (non necessariamente gli estremi del percorso).
6. `curve_through_points` [x] - `Begin/Point/End` NON funziona (`InsertCurveFilePoint` restituisce False, nessuna feature, provato aperta
   e chiusa). Funziona `InsertCurveFile(percorso)` con un file di testo "x y z" una riga per punto **nelle unita' del documento**
   (con file in metri su un documento in mm la curva e' 1000 volte piu' piccola: il tool legge `GetUserPreferenceInteger(47)` =
   swUnitsLinear e converte). File temporaneo cancellato sempre. Chiusa = si ripete il primo punto in fondo (inizio = fine, misurato).
   Misure: 5 punti (0,0,0)...(40,0,0): estremi esatti e `max_point_deviation` 0.0 mm (la spline passa per tutti i punti); 16 punti su un
   cerchio R=20 chiusa: lunghezza 125.65941 vs 2 pi R = 125.66371 (0.0034 %), punto opposto (-20,0,5); 9 punti su una semicirconferenza.
   Variante "per vertici": parametro `vertex_points` (coordinate di vertici esistenti, risolte con `_find_entity`) accodato a `points`,
   stessa spline. `FeatureReferenceCurve` / `CreateDefinition(61)` (curva per punti di riferimento): `CreateDefinition(61)` restituisce
   None, non implementata [~]: `vertex_points` copre il caso.

#### Altre trappole
- `CreateDefinition(i)` per i=0..259: solo 14 (swFmRefCurve = dati della curva proiettata, con FaceArray/Bidirectional) e 106 hanno
  membri utili; non c'e' alcun ID per la linea di divisione.
- Piani del modello di lab: "Front" e' il piano con normale X (non Z); "Top" ha normale Z (schizzo x = Y modello, y = -X). Nel test si usa
  "Top" per gli schizzi dove serve l'asse Z, e "Right" (normale Y; x schizzo = -X) per le rette di proiezione.
- Il laboratorio si e' appeso (script bloccato su una chiamata COM) 4 volte, sempre durante la ricerca dei mark della linea di divisione.
  Dopo `labrun --kill` e riavvio e' sempre ripartito.
- I test lasciano file in `test_output/` solo il log `crv_live.log`; i file temporanei delle curve per punti sono cancellati.

#### RICHIESTE A OPUS
- Aggiornare i conteggi dei tool (6 nuovi: create_helix, create_variable_pitch_helix, project_curve, split_line, composite_curve,
  curve_through_points) in test_offline / LIMITI / STATO.
- Nessuna modifica a `sweep` necessaria. Nessun tool distruttivo (solo feature nuove, niente `DESTRUCTIVE`).
- `LIMITI.md`: elica [x], passo variabile [x], proiezione [x] (bidirezionale come due curve), divisione per proiezione e silhouette [x],
  per intersezione [~], composita [x], per punti [x] (per punti di riferimento [~]).

### Lotto ext1 (estensioni dei tool esistenti)

Test: `tests/test_ext_ext1_live.py` (E1..E9, per sezione da argv). Nessun tool nuovo: cambiano solo i parametri (tutti facoltativi,
default invariati). File toccati: `automation/modeling.py`, `automation/modeling_base.py`, `automation/sketch_constraints.py`,
`modeling_tools.py`.

#### Helper nuovi
- `ModelingBase._last_sketch(doc)`, `_sketch_name_of(doc, sk)`, `SKETCH_TYPES` = ("ProfileFeature", "3DProfileFeature").
- `ModelingOperations._body_of_point`, `_select_bodies` (corpi scelti da un punto su una faccia; Mark 256), `_tangency`, `_thin_args`,
  `_readback(doc, feature, {chiave: proprieta'})` (rilettura dalla definizione della feature), `_cs_result`, costante `THIN_TYPES`.

#### 1. extrude_boss / extrude_cut: parete sottile, up_to_vertex, up_to_body  [x]
- `FeatureExtrusionThin2` / `FeatureCutThin2` (30 / 29 argomenti, stesso ordine dei normali + Thk1, Thk2, EndThk, RevThinDir, CapEnds, AddBends,
  BendRad). **RevThinDir = swThinWallType_e**: 0 verso l'esterno del profilo chiuso, 1 verso l'interno, 2 mezzeria, 3 due direzioni (Thk1 fuori +
  Thk2 dentro; con Thk2 = 0 la chiamata non crea nulla). **CapEnds**: qualunque valore diverso da 0 chiude ENTRAMBE le estremita' (0/1/2/3 danno
  lo stesso risultato); `EndThk` e' lo spessore del tappo (dentro il tubo: volume extra = 2 pi r_interno^2 * cap).
- Parametri: `thin_thickness`, `thin_type` (one_direction | opposite_direction | mid_plane | two_directions), `thin_thickness2`, `cap_ends`,
  `cap_thickness`. Il taglio sottile parte da z=30 con `start_offset` (per i tagli la direzione di default dal piano Top e' verso -z).
- `up_to_vertex` (T1=3): il vertice si seleziona DOPO lo schizzo con `up_to_vertex_point`; qualunque Mark funziona (provati 0,1,2,4,8).
- `up_to_body` (T1=7): il corpo si seleziona con `Body2.Select2(True, mark)` (qualunque Mark); per sceglierlo si usa `up_to_face_point` = punto
  su una faccia del corpo di arresto (`_body_of_point`). Misurato: il cilindro si ferma sotto la piastra (altezza 20).
- Misure (cerchio R=10, h=20, t=2): esterno 2764.602 (pi(144-100)20), interno 2261.95, mezzeria 2513.27, due direzioni (2+1) 3958.407,
  con tappi 1.5: 2764.6 + 942.5; taglio sottile (10 di profondita') 1130.973 / 1382.301 / 1256.637; up_to_vertex 1963.495 (pi 25 25), up_to_body
  1570.796 (pi 25 20), taglio fino a vertice 2356.194 (pi 25 30). Tutti entro 0.0001 % dal calcolato.

#### 2. sweep: guide, parete sottile, tangenza, merge, percorso = curva qualunque  [x]
- `InsertProtrusionSwept4` / `InsertCutSwept5`: Start/EndMatchingType = swTangencyType_e (0 none, 1 path_tangent/normal_to_profile, 3 all_faces),
  IsThinBody + Thickness1/2 + ThinType (stessa codifica THIN_TYPES), Merge. Guide: selezione con **Mark 2** dopo profilo (Mark 1) e percorso (Mark 4);
  con guide `TwistCtrlOption = 2` (segui percorso e prima guida: le guide scalano il profilo).
- Il percorso e' qualunque feature (elica, composita, 3D): `_select_feature(.., mark 4)` funziona (gia' misurato dal lotto curve).
- TRAPPOLA (mia, non di SW): per spazzare lungo un'elica un profilo DISEGNATO, il piano del profilo deve essere perpendicolare alla tangente di
  partenza dell'elica (tangente ~ asse Y per l'elica che parte in (R,0,0)): il piano Right (normale Y) con cerchio in u=-R (u = -x). Con un piano
  parallelo alla tangente (Front offset) lo sweep non crea nulla (provate 24 combinazioni di TwistCtrl/PathAlign/KeepTangency, CreateDefinition,
  SelectByID2 con REFERENCECURVES...: nessuna serve).
- Il risultato riporta `start_tangency_readback` / `end_tangency_readback` / `guide_count` letti da `ISweepFeatureData`.
- Misure: molla = cerchio d=2 lungo elica R=10 passo 5, 4 giri (L=252.1132): 791.888 vs pi r^2 L = 792.064 (0.022 %); con profilo disegnato 789.406
  (0.34 %, il profilo non e' esattamente perpendicolare: pi r^2 L cos(angolo elica) = 789.50); guida (tronco di cono r 5->10 su 40): 7330.121 vs
  7330.383 (0.004 %); sottile esterno 1382.301 / interno 1130.973 (pi(36-25)40 e pi(25-16)40, 0.0000 %); merge=true 49570.796 (blocco + pi 25 20),
  merge=false 51141.593 e 2 corpi; tangenza path_tangent riletta = 1 (volume invariato 3141.593).
- `all_faces` senza facce adiacenti non crea niente (valido solo con facce tangenti esistenti). `direction_vector` e' nella tabella ma per lo sweep
  non e' gestito (servirebbe un vettore): non documentato nel tool.

#### 3. loft: condizioni iniziale/finale, parete sottile, merge, curva centrale  [x] (formula esatta della tangente: [~])
- `InsertProtrusionBlend2(Closed, KeepTangency, ForceNonRational, Tess, StartMatchingType, EndMatchingType, StartTangentLength, EndTangentLength,
  StartTangentDir, EndTangentDir, IsThinBody, Thk1, Thk2, ThinType, Merge, UseFeatScope, UseAutoSelect, GuideCurveInfluence)`; taglio:
  `InsertCutBlend`. Condizioni swTangencyType_e: 0 none, 1 normal_to_profile, 2 direction_vector. Centerline = **Mark 4**; vettore di direzione:
  **Mark 8** (inizio) / **16** (fine). Il vecchio `start_tangency` (bool) resta come alias di `start_condition=normal_to_profile`.
- Nuovi: `start_condition`, `end_condition`, `start_direction`, `end_direction`, `start_tangent_length`, `end_tangent_length`, `start_reverse`,
  `end_reverse` (StartTangentDir/EndTangentDir = inversione), `thin_thickness` (+ thin_type, thin_thickness2), `merge`, `centerline_sketch`.
  Il risultato riporta `start_condition_readback`, `end_condition_readback`, `profile_count`, `guide_count`.
- Misure (quadrati 20 -> 10, altezza 30): semplice 7000.0 = tronco; normal_to_profile L=1: 6882.44, L=0.5: 6941.19 (volume sotto il tronco e
  monotono con la lunghezza della tangente; L=2 -> self-intersection, nessun solido); la formula esatta del volume con tangenti normali NON e'
  riprodotta dal modello Hermite (7114 per L=30 ecc.): SolidWorks usa un'altra scala della tangente. Il test controlla soltanto volume < tronco,
  > 3000, rilettura = 1 e monotonia `[~]`.
- Loft sottile (spessore 1 verso l'esterno): 1948.162 = tronco con semilato w + t/cos(a) (tan a = 5/30) meno il tronco: 1948.162 (0.0000 %).
- direction_vector con il piano Top (normale z): condizione 2 riletta; volume 5759.55 (diverso dal tronco, e dal normal_to_profile 6882: con il vettore
  di una faccia/asse la scala della tangente e il verso cambiano; `start_reverse=True` -> 8240.19). `[~]`: l'effetto e' provato, il valore no.
- centerline_sketch con retta lungo z: 7000.0 (= tronco).

#### 4. chamfer_at_points: smusso a vertice, equal_distance  [x]
- `InsertFeatureChamfer(0, 3, 0, 0, 0, d1, d2, d3)` con il vertice selezionato (Mark 0): volume tolto = d1 d2 d3 / 6 (3,4,5 -> 10.000; 4,4,4 ->
  10.667). Parametri `vertex_point` (punto SUL vertice), `vertex_distances` [d1,d2,d3] (se manca ma c'e' `distance`: tre volte `distance`).
- TRAPPOLA: `ChamferType 16` (EqualDistance) crea la feature ma NON scava (volume invariato, gia' scritto nel docstring del modulo). `equal_distance`
  usa quindi il tipo 2 (distanza-distanza) con d1 = d2: spigolo 40 con d=2 -> 80.000 asportati.
- `distance` ed `edge_points` ora sono facoltativi (obbligatori solo nel modo spigoli): errore chiaro se manca il modo.

#### 5. shell_body: multi_thickness  [x] con metodo di aggiramento (API nativa [~])
- API nativa NON utilizzabile: `CreateDefinition(swFmShell=8)` -> None; con `GetDefinition` + `AccessSelections(doc, null)` si puo' impostare
  `MultipleThicknessFaces` (conteggio 1) ma `SetMultipleThicknessAtIndex(i, t)` non ha effetto (indici 0/1/-1, VT_R8/VT_R4/BYREF, prima o dopo
  `ModifyDefinition`; `GetMultipleThicknessAtIndex` resta 0.0) e la parete sparisce (spessore 0: cavita' 38 invece di 33). `Thickness=` invece
  funziona. `IModelDoc2.InsertFeatureShellAddThickness(t)` (selezione prima/dopo, Mark 0/1/2/4) non cambia nulla o da' lo stesso spessore 0.
- Soluzione: shell uniforme a `thickness`, poi per ogni `{"face","thickness"}` (punto sulla faccia ESTERNA piana del corpo di partenza) si
  trova la faccia interna (punto - normale * t) e la si sposta di (t_faccia - t) con `move_faces` (InsertMoveFace3, offset lungo la propria
  normale). Solo facce piane, non con `outward`. Il risultato riporta `multi_thickness_applied` (variazione misurata e attesa = area interna
  * delta) e `method`.
- Misure (scatola 40x40x30, parete x=20 di 5, resto 2, faccia superiore aperta): volume 14736.0 = 48000 - 33*36*28 (esatto); due pareti (5 e 4):
  16752 = 48000 - 31*36*28 (esatto). Variazione della mossa 3024.0 = attesa.

#### 6. create_coordinate_system: modo numerico  [x]
- `CreateCoordinateSystemUsingNumericalValues(UseLocation, dx, dy, dz, UseRotation, ax, ay, az)` su FeatureManager (nessuna selezione).
  Parametri `origin` [x,y,z] (`unit`) e `rotation` [rx,ry,rz] gradi; non si combina con origin_point/*_edge_point. Riletti con
  `GetCoordinateSystemTransformByName` (origine in `unit`, assi).
- Misure: origine (10,20,30) e rotazione Z 90: assi x=(0,1,0) y=(-1,0,0) z=(0,0,1); rotazione X 30: y=(0,0.866,0.5), z=(0,-0.5,0.866); rotazione Y 90:
  x=(0,0,-1), z=(1,0,0); origine in cm (1,2,3) -> riletta (1,2,3) (cioe' 10,20,30 mm).

#### 7. draw_slot: asole ad arco  [x]
- `CreateSketchSlot(SlotCreationType, SlotLengthType, Width, X1..Z3, CenterArcDirection, AddDimension)`: **arc_center = 2**: P1 = centro dell'arco,
  P2 = inizio, P3 = fine, direzione 1 antioraria / -1 oraria; **arc_3point = 3**: P1 = inizio, P2 = fine, P3 = punto sull'arco centrale (ordine
  misurato; con l'ordine inizio-mezzo-fine esce un arco sbagliato). Parametri: `slot_type` arc_center | arc_3point, `cx`,`cy`,`radius`,`start_angle`,
  `end_angle`,`clockwise`,`x3`,`y3`; x1..y2 ora facoltativi (obbligatorio solo `width`). Il risultato riporta `centerline_length`.
- Misure (w=4, estrusione 10: volume/10 = area): 0..90 gradi raggio 20: 138.230 = 4*31.416 + 4 pi; 0..180 raggio 15; 270 gradi (orario); arc_3point
  quarto di cerchio; retta 30: tutti entro 0.002 %. Nota di prova: due asole nella stessa parte si sovrappongono ai cappucci (misura falsata): una per parte.

#### 8. mirror_feature / linear_pattern / circular_pattern con `bodies`  [x]
- I corpi si indicano con un punto SU una loro faccia (`_body_of_point`) e si selezionano con **Mark 256** (`Body2.Select2`): provati i Mark
  2,4,8,16,32,64,128,256,512,1024,2048,0,1 su `FeatureLinearPattern5`: solo 256 crea la ripetizione (con geometry_pattern vero o falso). Lo
  stesso Mark vale per `InsertMirrorFeature2(BMirrorBody=True)`. Per le ripetizioni `features` ora e' facoltativo (serve `features` o `bodies`).
- Il risultato riporta `bodies_before`, `bodies_after`, `bodies_expected_if_separate`.
- Misure: lineare 3 istanze passo 20 di un cubo da 1000: 3000.0 e 3 corpi; ripetizione di UNO dei due corpi: 3000; specchio rispetto al piano Right
  (y=0) di un cubo a y 10..20: 2000 e bounding box y -20..20; specchio di un solo corpo su due: 3000 e 3 corpi; circolare 4 istanze attorno all'asse Z:
  4000 e 4 corpi.

#### 9. Schizzi 3D negli helper di schizzo  [x]
- Difetto: `_active_sketch_name` (e gli helper simili) cercavano solo `ProfileFeature`, quindi con uno schizzo 3D attivo restituivano l'ultimo schizzo
  2D. Correzione: `ModelingBase._sketch_name_of(doc, sk)` confronta l'ISketch con le feature di entrambi i tipi (`SKETCH_TYPES`) e, come ripiego,
  sceglie l'ultimo schizzo 3D/2D secondo `ISketch.Is3D`. Corretti anche `_exit_sketch` (ripiego), `_resolve_sketch` (nome dell'ultimo schizzo di
  qualunque tipo, elenco degli schizzi con entrambi i tipi), `_sketch_entity_obj` (accetta anche 3D) e `get_sketch_definition_status` (ultimo schizzo).
  Sugli schizzi 2D il comportamento e' invariato (l'ultimo schizzo e' sempre lo stesso se non ci sono schizzi 3D dopo).
- Misure: schizzo 3D attivo e riaperto per nome: `list_sketch_entities` e `get_sketch_definition_status` riportano "Schizzo3D1" (prima: lo schizzo 2D
  precedente); sweep di un cerchio lungo la linea 3D con il profilo ancora aperto: 1130.973 = pi 9 40.

#### Test
- `tests/test_ext_ext1_live.py`: vedi il riepilogo in STATO (sezioni E1..E9, tutte PASS). Regressione: `test_modeling_extra_live.py B1 B2 B3` e
  `test_ext_moka1_live.py`.
- Trappola di rete: il laboratorio e il server possono essere lenti (la macchina e' condivisa con altri lotti): un prova puo' superare i 120 s.

#### RICHIESTE A OPUS
- Aggiornare i conteggi dei tool nel test offline (nessun tool nuovo da parte mia).
- `shell_body.multi_thickness` usa move_faces per via di `SetMultipleThicknessAtIndex` inefficace: se in futuro si trova un modo nativo, sostituire.
