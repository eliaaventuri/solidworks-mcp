# LIMITI - elenco di lavoro (aperto il 2026-10-10)

Ogni limite noto, da risolvere uno per uno. Stato: `[ ]` da fare, `[x]` risolto e testato, `[~]` risolto in parte / alternativa (spiegare).
Chi lavora su un gruppo aggiorna questo file man mano. Esiti dettagliati e regressioni di ogni gruppo: `STATO_STORICO.md`.

## Gruppo A — Disegni
- [x] A1 Linee di esplosione nelle tavole d'assieme (InsertExplodeLineSketch + InsertRouteLine) -- add_explode_lines (perno-boccola-foro + una per vite) con InsertExplodeLineSketch; la vista esplosa del disegno le mostra. Test: linee presenti, PNG assieme.
- [x] A2 Tolleranze geometriche e riferimenti agganciati alla feature (freccia/leader sulla faccia o sulla quota), non riquadri flottanti -- add_geometric_tolerance/add_datum agganciati con model_point (freccia sullo spigolo) o on_dimension (legati alla quota); riquadro vicino al bersaglio; richiamo che non attraversa i testi delle quote. Test + PNG albero.
- [x] A3 Cave/linguette quotate (lunghezza, larghezza, profondità, posizione); in generale quote delle feature non cilindriche -- cave quotate in lunghezza, larghezza, posizione dalla testata (ruoli L/W/P). Test: 30 / 8 / 55 sull'albero.
- [x] A4 Richiami di raggi/diametri che attraversano il pezzo (es. R10 staffa, Ø30 flangia) -- richiami di R/Ø limitati al tratto fino al centro (R10 staffa < 22 mm dentro il contorno; flangia Ø110/Ø30 su direzioni diverse).
- [x] A5 Etichette dei fori (A1…) che toccano i simboli dei fori -- etichette dei fori fuori dai simboli (tags_clearance_mm >= 0), controllato nel test sulla staffa.
- [x] A6 Staffa: viste piccole in A3 1:2 → scelta automatica del formato (A2) o layout più compatto quando 1:1 non entra -- scelta automatica del formato (staffa: A2 in scala 1:1 invece di viste piccole in A3 1:2).
- [x] A7 Tavola d'assieme: quote d'ingombro; palloncini inclusi nel controllo sovrapposizioni -- quote d'ingombro 80x80 sull'assieme; palloncini nel controllo sovrapposizioni (non coprono le viste).
- [x] A8 "N. DISEGNO" del cartiglio che sfora con nomi lunghi -- N. DISEGNO ridotto di carattere finche' sta nella cella (nome da 43 caratteri verificato).
- [x] A9 `set_dimension_tolerance` modifica la quota del MODELLO: deve agire solo sul disegno (o dichiararlo e chiedere) -- set_dimension_tolerance agisce solo sul disegno (quota di riferimento al posto della quota pilota); apply_to_model=true dichiarato nel risultato.
- [x] A10 Quote angolari: caso di prova reale (non smusso) per `_dq_fix_angular` -- cuneo con quota angolare vera di 30 gradi ricostruita sugli spigoli (arco nel foglio, testo fuori dalla vista).
- [x] A11 Ritaglio vista non circolare (rettangolo/poligono) -- add_crop_view con shape=circle|rectangle|polygon; verificati rettangolo e poligono.
- [x] A12 Vista interrotta: verifica dell'aspetto -- add_break_view con linee curve ISO (stile 3 default): la vista si accorcia davvero; verificato sul PNG (qual_speciali).
- [x] A13 `flip` della sezione: verifica visiva -- sezione invertita: la matrice di vista cambia e le frecce si girano (PNG qual_speciali).
- [x] A14 Fogli A3–A0 verticali con cornice e cartiglio (formato ISO verticale generato) -- formati ISO verticali A3-A0 generati in formats/ (drawing_formats.py); A3 verticale 297 x 420 con cornice e cartiglio verificato.
- [x] A15 Layout: non presupporre l'isometrica nell'angolo; fogli affollati → nuovo foglio automatico -- layout senza isometrica nell'angolo; foglio pieno -> nuovo foglio dello stesso formato (new_sheet_if_full).
- [x] A16 `add_auxiliary_view` senza `CreateAuxiliaryViewAt2` -- vista nominata AUX_n (Orientation3 + NameView) + CreateDrawViewFromModelView3, freccia con lettera e titolo; cuneo a 30 gradi: faccia in vera grandezza (cos 1,00000, area 1209,3 = 30 x 40,31). test_drawings_live 65/65 per 3 volte di fila (64 + il nuovo controllo). Guardia DXF/DWG con viste interrotte estesa a save_document e _save_as.
- [x] A17 Difetti residui della staffa e della flangia -- GD&T agganciato con freccia, rugosita' generale ISO 1302 composta con misure vere, fori in catena sui due lati senza attraversare altri fori, quote di profilo su laterale/frontale senza duplicati, titolo SEZIONE A-A libero. Controlli automatici nuovi (check_a17) in test_drawing_quality_live (139/139). Dettagli in STATO_STORICO.md.

## Gruppo B — Modellazione e tool base
- [x] B1 Test di `fillet_variable_radius` con confronto numerico -> FATTO: volume asportato vs (1-pi/4) L (r0^2+r0r1+r1^2)/3, scarto 0,04 % su 4 coppie di raggi (`test_modeling_extra_live.py`).
- [x] B2 Test di sistema di coordinate, piano per 3 punti, piano inclinato -> FATTO: normali e origini lette dall'API (Transform.ArrayData); corretti piano per 3 punti e piano inclinato (InsertRefPlane dava None, ora CreatePlaneThru3Points3 / CreatePlaneAtAngle3); CS con x/y/z_flip.
- [x] B3 Test di `convert_entities`, `up_to_surface`, `revolve_cut`, loft con guide, sweep di taglio -> FATTO: tutti entro 0,01 % (loft con guide curve -0,74 % dal modello ideale, dichiarato nel test).
- [~] B4 Hole Wizard: altri standard (UNI/ISO completi, ANSI), fori su facce cilindriche e piani inclinati -> ISO/ANSI metrico/ANSI pollici/DIN/BSI/JIS con teste cilindrica, svasata, esagonale ecc. (36 combinazioni misurate: Ø, profondita', volume), piani inclinati OK. UNI non esiste nel database di SolidWorks. LIMITE: su facce cilindriche il foro e' radiale con Ø/volume giusti ma la posizione angolare e' ruotata rispetto al punto indicato (comportamento di HoleWizard5, non correggibile in generale): da verificare con list_entities. RIAPERTO 2026-10-12: piano di ripresa (piano tangente) in `PIANO_D_E.md`.
- [x] B5 Tool base mai testati: open/save/close, draw_line/rect/arc/polygon, cut_extrude, set_units, execute_python -> FATTO: tutti testati con volumi; corretti save_document senza nome (Save3 byref) e cut_extrude through_all+both_directions.
- [x] B6 `close_document` chiude senza salvare: renderlo sicuro (rifiuta se ci sono modifiche, salvo `save=true` o `discard=true` esplicito) -> FATTO: close_document(save/discard/document) + guardia overwrite su salvataggi/esportazioni + delete_feature con confirm e controllo dipendenti + annotazioni destructiveHint (`safety.py`).

## Gruppo C — Assiemi
- [x] C1 Selezione per coordinate dentro sotto-assiemi (non solo primo livello) -- `_as_find_geom` cerca a tutti i livelli (Transform2 di un componente annidato e' gia' la trasformazione composta). Test: blocco di primo livello accoppiato a un perno a 2 livelli di sotto-assiemi ruotati di 30 e 60 gradi: origine del perno = composizione calcolata dal test (210; 57,5; 32,9904), blocco a x=250, asse della sporgenza = asse del perno entro 0,001 mm (38/38).
- [x] C2 Specchiatura con versione speculare (pezzo opposto nuovo) e test dell'orientamento -- `mirror_components(opposite_hand=True)` crea cx_blocco_sx.SLDPRT: volume 12141,3717 = originale, baricentro (7,6164; -60,1164; 0) = riflesso, baricentro locale con X cambiata di segno (geometria riflessa, non solo ruotata); posa esatta forzata (SolidWorks sceglie l'orientamento da una preferenza che varia fra sessioni: dissolve della feature + posa); piano X; overwrite protetto; i 4 orientamenti delle istanze misurati (41/41).
- [~] C3 Esplosione in direzione libera, radiale, con rotazione -- vettore libero (scomposto in passi X/Y/Z: 50 mm lungo (1,1,0)/radice 2 misurati 50,0000), direzione di un'entita' inclinata (40,0000 mm parallelo all'asse a 30 gradi), passo radiale (raggio 30->60 e rotazione 30,00005 gradi misurata dalla matrice). NON possibile: rotazione nei passi di traslazione (AddExplodeStep2 non memorizza ExplAng/RotationAngle in SolidWorks 2026 con nessuna combinazione); l'API lo dichiara con `rotation_applied=false`. La rotazione funziona nei passi radiali. Prove ulteriori (priorita' bassa) in `PIANO_D_E.md`.
- [x] C4 Esplosione automatica nativa (o euristica migliore e dichiarata) -- nativa: `IAssemblyDoc.AutoExplode` (proprieta') crea un passo "Catena" lungo una direzione scelta da SolidWorks (6/7 componenti si spostano, 1 coppia di box si sovrappone di 4,23 mm: dichiarato, non funziona se esiste gia' una vista); euristica `mode="mates"`: ordine di smontaggio dalla profondita' degli accoppiamenti, asse del concentrico, verso dal lato della testa, distanze dai bounding box: perno 106,4 mm, boccola 55,2, viti 27,2 in -X, 0 sovrapposizioni dei box nello stato esploso reale, distanza minima fra i box 15,000 mm (gap richiesto 15).
- [~] C5 Test degli accoppiamenti avanzati: limite distanza/angolo, ingranaggio, vite, larghezza, simmetrico, tangente, blocco -- VERIFICATI muovendo e misurando: limite distanza 5..20 (valori nel limite portano il blocco a x=10+valore, fuori limite rifiutati; limiti modificabili), limite angolo -20..45 (|rotazione|=|valore|, fuori limite rifiutato), larghezza (linguetta centrata a y=5, Y vietato, X/Z liberi; AddMate5 la rifiutava: serve CreateMateData), simmetrico (origine -100 = riflesso), tangente (asse a z=15, non penetra). Creati e letti dal modello ma NON verificabili dinamicamente: blocco (le traslazioni restano ma le tre rotazioni sono libere), ingranaggio (rapporto 2:1 letto dal modello, scambiato; la seconda ruota non segue), vite (passo 2 mm/giro letto dal modello via quota D1; la chiocciola non avanza): SetTransformAndSolve2 e IDragOperator non propagano questi accoppiamenti; uno studio di movimento (motore rotativo) non ha prodotto moto nell'istanza nascosta. RIAPERTO 2026-10-12: prove con istanza visibile in `PIANO_D_E.md`.
- [x] C6 `delete_mate` che lascia altri componenti sottovincolati: indagare e correggere -- riprodotto: eliminando il coincidente boccola-base la boccola passa da 1 a 2 gradi di liberta' e il PERNO (che non e' in quell'accoppiamento) da 1 a 2 per catena, ma il tool non diceva nulla. Ora `delete_mate` misura i gradi di liberta' prima/dopo (anche per effetto di catene) e riporta `freed_components`/`freed_not_in_mate` e un avviso; le posizioni restano invariate (misurato).
- [x] C7 `move_component` con rotazione su componente parzialmente vincolato -- gradi di liberta' MISURATI (anche su assi inclinati) e movimento ridotto a quelli: perno col solo concentrico: rotazione di 30, 20, 14,76 gradi e scorrimento di 15 e -5 mm applicati, Y/Z e rotazioni attorno a Y/Z scartate (prima una rotazione attorno a Y faceva scivolare il perno di 11,7 mm); asse inclinato di 30 gradi: dx=10 -> 8,66 mm lungo l'asse (7,5; 4,33; 0).

## Gruppo D — Dati ed export
Piano dettagliato (API candidate, test, numeri attesi) per i gruppi D ed E: `PIANO_D_E.md` (2026-10-12, non ancora provato dal vivo).
- [ ] D1 Tabella dati (design table): Excel non installato → alternativa: configurazioni generate da tabella CSV/JSON (stessa funzione), più design table vera se Excel presente
- [ ] D2 STEP AP242 reale
- [ ] D3 eDrawings `.eprt` verificato (apertura/lettura)
- [ ] D4 Immagini oltre la risoluzione nativa (es. 4K) e resa migliore (RealView/ambient occlusion/prospettiva); rendering fotorealistico se Visualize è automatizzabile
- [ ] D5 `hide_reference` anche dentro i componenti degli assiemi
- [ ] D6 Assiemi: test di export STL/STEP, bounding box, immagini
- [ ] D7 Proprietà di massa rispetto a un sistema di coordinate utente
- [ ] D8 Materiali personalizzati fuori dalla cartella standard (librerie utente)
- [ ] D9 Import: opzioni avanzate (riparazione, unione facce, import come assieme/pezzo)
- [ ] D10 PDF 3D verificato più a fondo

## Gruppo E — Simulazione
- [ ] E1 Contatti locali (coppie di facce: incollato, libero, senza compenetrazione)
- [ ] E2 Controllo locale della mesh
- [ ] E3 Posizione del fattore di sicurezza minimo (calcolata dai risultati nodali)
- [ ] E4 Carichi remoti e carico da cuscinetto
- [ ] E5 Studi non statici: frequenze proprie, buckling, termico stazionario

## Gruppo G — Lingua di SolidWorks
- [~] G1 Server indipendente dalla lingua (italiano / inglese) -- FATTO nel codice (2026-10-12, `utils/sw_lang.py`): piani standard e
  origine per posizione/tipo, cartelle lang della lingua attuale, grafici Stress1/Sollecitazione1, ERRORE:/ERROR: del cartiglio,
  punto origine, scritte delle tavole e formati verticali nella lingua di SolidWorks, `ui_language` in connect_solidworks. Test offline
  80/80. DA FARE: regressione completa con SolidWorks in inglese (i test traducono i nomi italiani; tabella in `tests/live_common.py`).

## Gruppo F — Sicurezza e pulizia (decide Elia)
- [x] F1 `.env` dell'autore con una chiave API OpenRouter esposta: togliere dal repository (resta in .gitignore)
- [x] F2 `execute_python` esegue codice arbitrario: lasciarlo con avviso nella descrizione del tool
- [x] F3 Codice morto dell'autore (`backup_*`, `scripts/`, `solidworks_com.py`, `solidworks_simulation.py`): segnalato, non rimosso
