# PIANO — Gruppi D (dati ed export) ed E (simulazione), ripresa dei parziali B4 / C5 / C3

Scritto il 2026-10-12 in una sessione cloud **senza SolidWorks**: niente di questo piano e' stato provato dal vivo.
I nomi di API marcati **(da verificare)** vengono dalla documentazione e dalla memoria, non da prove: prima di scrivere
codice controllarli nel type library (`sldworks.tlb`, `cosworks.tlb`) o in `scripts_tmp/cosworks_dump.txt`, come nei blocchi precedenti.
Regole che restano valide: istanza dedicata, 0 orfani, preferenze utente salvate e ripristinate, ogni voce chiusa con un numero misurato.

Fatto in questa sessione (verificabile senza SolidWorks):
- `tests/test_offline.py` (36/36 PASS su Linux con COM simulato): registro dei 196 tool (schema = parametri passati = firma del
  metodo, `required` = parametri obbligatori), `safety.py`, PNG puro Python, lettori STL/3MF/STEP/IGES/x_t/PDF, libreria `.sldmat`, unita'.
- `_dx_inspect_step` conta anche `product_definitions` e `assembly_occurrences` (struttura d'assieme dello STEP, serve a D6).

Prima di tutto: regressione completa dei 9 test (vedi `STATO.md`, "Prossimo passo").
Ordine consigliato: B4 e C5 (ripresa, sezione in fondo) -> D5, D6, D7, D8, D1 (tool composti da metodi gia' verificati, rischio basso) -> E3, E5, E1, E4, E2 -> D4, D9, D10 -> D2, D3 (probabili limiti dell'edizione).

---

## Gruppo D

### D1 — Configurazioni da tabella (CSV/JSON), design table vera solo con Excel
- Nuovo tool `apply_configuration_table(table, create_missing=true, dry_run=false)`: `table` = percorso CSV/JSON o righe inline.
  Intestazioni con la stessa convenzione delle design table, cosi' la tabella si puo' riusare in Excel:
  `D1@Schizzo1` (quota, mm o gradi), `$STATO@Foro1` (`S`/`R` = soppressa/attiva), `$PRP@Codice` (proprieta' della configurazione),
  `$MATERIALE` (opzionale), prima colonna = nome della configurazione.
- Implementazione: SOLO composizione di metodi gia' verificati (`add_part_configuration`, `set_configuration_dimension`,
  `set_configuration_suppression`, `set_custom_property(configuration=)`, `assign_material(configuration=)`). Parsing e validazione
  (colonne sconosciute, valori non numerici, nomi duplicati) in una funzione pura -> test offline.
- `dry_run=true`: restituisce il piano delle modifiche senza toccare il modello.
- Design table vera: solo se `Excel.Application` e' registrato (`HKCR\Excel.Application`): `InsertDesignTable` **(da verificare)**.
  Altrimenti il risultato lo dice esplicitamente.
- Test live: il blocco di `test_data_live` con 3 righe (Default / Lunga 60 / Pieno con foro soppresso): volumi attesi gia' noti
  (116607,26 / 233214,53 / 120000,00 mm3); poi rilettura con `list_part_configurations(include_volume=true)`.

### D2 — STEP AP242 reale
- Stato: `int 75 = 242` accettato ma il file e' AP203.
- Prove, in ordine: (1) elencare dal type library tutte le costanti `swUserPreference*` con "Step" nel nome e i valori ammessi;
  (2) leggere nel registro (`HKCU\Software\SolidWorks\SOLIDWORKS 2026\...`) cosa cambia quando si sceglie AP242 a mano in
  Opzioni > Esporta (diff del registro prima/dopo); (3) `Extension.SaveAs3` con `AdvancedSaveAsOptions` **(da verificare)**.
- Verifica: `inspect_export_file` -> `application_protocol == "AP242"` e `valid_solid`, reimport con scarto di volume < 0,001 %.
- Se l'edizione Student non lo consente: `[~]` con la prova (valore del registro scritto e file risultante).

### D3 — eDrawings `.eprt` verificato
- Oggi: solo dimensione > 0. Passi: (1) firma del file (primi byte) confrontata con un `.eprt` salvato a mano;
  (2) apertura con l'API di eDrawings (`EModelView.EModelViewControl`, controllo ActiveX: serve una finestra contenitore,
  `win32ui`/`AtlAxWin`) **(da verificare)**: `OpenDoc` + evento di apertura completata + numero di configurazioni/componenti;
  (3) se l'ActiveX non e' utilizzabile: avvio di `eDrawings.exe <file>` con controllo che il processo resti vivo e senza finestra di errore, poi chiusura del PID.
- Rischio: alto (dipende dall'installazione di eDrawings).

### D4 — Immagini oltre la risoluzione nativa, resa migliore
- Risoluzione: le opzioni "Salva come immagine" di SolidWorks hanno la modalita' "cattura di stampa" con DPI e formato carta:
  preferenze `swTiffScreenOrPrintCapture`, `swTiffPrintDPI`, `swTiffPrintPaperSize`, `swTiffPrintDrawingPaperWidth/Height`
  **(da verificare se valgono anche per PNG/JPG dei modelli)**. Obiettivo: 3840x2160 con contenuto centrato (riusare il controllo
  di centratura gia' usato per scartare `SaveBMP`). Salvare e ripristinare le preferenze.
- Resa: prospettiva (`IModelView.AddPerspective` / `RemovePerspective` **(da verificare)**), RealView e occlusione ambientale
  (proprieta' di `IModelView` **(da verificare)**; RealView richiede una scheda grafica certificata: su ARM64 emulato probabilmente no -> dichiararlo).
- Visualize/PhotoView 360: PhotoView non c'e' piu' dalle versioni recenti; Visualize e' un prodotto separato: verificare solo se e' installato, altrimenti `[~]`.
- Verifica: dimensione del PNG letto con `_read_png`, centratura del contenuto (bbox dei pixel non di sfondo), confronto a occhio.

### D5 — `hide_reference` anche nei componenti degli assiemi
- Opzione semplice: toggle di documento "Nascondi tutti i tipi" `Extension.SetUserPreferenceToggle(swViewDisplayHideAllTypes, 0, True)`
  **(da verificare)**, salvato e ripristinato. Agisce su tutto l'albero, componenti compresi.
- Alternativa: per ogni componente, `Component2.FirstFeature` e `Select2` nel contesto dell'assieme + `BlankRefGeom` (come oggi nel pezzo).
- Verifica: `blue_pixels()` di `test_data_live.py` su un assieme con un pezzo che ha un piano visibile: > 0 senza, 0 con `hide_reference`,
  e piano di nuovo visibile dopo.

### D6 — Assiemi: export STL/STEP, bounding box, immagini
- Solo test (il codice accetta gia' gli assiemi). Assieme di prova: i pezzi `cx_*` di `test_assembly_extra_live.py`.
- STEP: `product_definitions` = pezzi distinti + assiemi, `assembly_occurrences` = istanze (contatori aggiunti oggi a `_dx_inspect_step`);
  reimport -> volume totale = somma dei volumi dei componenti.
- STL: un file (`one_file=true`) con box = box dell'assieme; `one_file=false` -> un file per componente (contarli).
- `get_bounding_box`: confronto con il box calcolato dai box dei componenti e dalle loro `Transform2`.
- Immagine: PNG non vuoto, componenti visibili.

### D7 — Proprieta' di massa rispetto a un sistema di coordinate utente
- Calcolo in Python, indipendente dall'API: con R (colonne = assi del sistema utente nel modello) e origine o, letti con
  `GetCoordinateSystemTransformByName` (gia' verificato in B2):
  baricentro' = R^T (c - o); tensore nell'origine utente, assi utente: R^T (I_c + m(|d|^2 E - d d^T)) R con d = c - o.
- Se esiste, confrontare con `IMassProperty2` dopo la scelta del sistema di coordinate (`SetCoordinateSystem` **(da verificare)**).
- Nuovo parametro `coordinate_system` in `get_part_mass_properties`. Test: parallelepipedo e sistema ruotato di 30 gradi
  attorno a Z e traslato: confronto con le formule (< 0,01 %). La funzione di trasformazione e' pura -> test offline.

### D8 — Materiali personalizzati fuori dalla cartella standard
- Cartelle delle librerie da Opzioni > Percorsi dei file > Database dei materiali:
  `GetUserPreferenceStringValue(swFileLocationsMaterialDatabases)` **(da verificare la costante)**, elenco separato da `;`.
  `_dx_load_materials` legge tutti i `.sldmat` di tutte le cartelle (la decodifica UTF-16 e' gia' coperta da `test_offline.py`),
  segnala i duplicati (stesso nome in due librerie) e azzera la cache quando l'elenco cambia.
- Test live: scrivere un `.sldmat` di prova (densita' 1234 kg/m3) in una cartella temporanea, aggiungerla al percorso (salvato e
  ripristinato), `assign_material` -> massa = volume x 1234.

### D9 — Import: opzioni avanzate
- Opzioni da esporre: 3D Interconnect si'/no (preferenza **(da verificare)**), STEP come assieme o come pezzo multicorpo,
  unione delle facce (gia' parametro `merge_faces`, oggi NON usato nel codice), diagnostica di importazione / riparazione
  (`IPartDoc.ImportDiagnosis` **(da verificare)**).
- Nota: il metodo `import_model` ha un parametro `merge_faces` che non usa (e che lo schema del tool non espone): collegarlo a una preferenza o toglierlo.
- Test: STEP d'assieme di D6 importato come assieme (n componenti) e come pezzo (n corpi); file con una faccia rovinata (STEP modificato
  a mano togliendo un `ADVANCED_FACE`) -> la diagnostica la trova e la ripara (volume finale vicino all'originale).

### D10 — PDF 3D verificato a fondo
- Oggi: presenza di `/3D` e `PRC`. Lettura completa in Python puro: trovare l'oggetto `/Subtype /PRC`, decomprimere lo stream
  (`/FlateDecode` con zlib), controllare il magic `PRC` all'inizio e la lunghezza; leggere l'annotazione `/3D` con la vista
  predefinita (`/3DV`). Tutto testabile offline con un PDF sintetico; dal vivo si confronta con il PDF di `test_data_live`.
- Facoltativo: estrarre dal PRC il numero di corpi/tessellazioni (il formato e' documentato, ISO 14739-1) se servono numeri.

---

## Gruppo E

### E1 — Contatti locali (coppie di facce)
- API: `ContactManager.CreateContactSet(tipo, entita1, entita2, err)` **(da verificare in `cosworks_dump.txt`)**; entita' come
  `VARIANT(VT_ARRAY|VT_VARIANT)` (trappola gia' nota); tipi incollato / libero / senza compenetrazione.
- Tool: `add_simulation_contact(faces1, faces2, contact)`, elenco/eliminazione nei tool dei carichi.
- Test: due blocchi sovrapposti (assieme del blocco 5). Globale libero + locale incollato sulla faccia di contatto ->
  freccia 0,7964 mm come il monolite; senza compenetrazione con carico che COMPRIME il contatto -> stessa freccia (entro 1 %);
  con carico che lo apre -> il blocco superiore si stacca (spostamento molto maggiore o errore di instabilita', da documentare).

### E2 — Controllo locale della mesh
- API: `Mesh.AddMeshControl...` **(da verificare il nome esatto e gli argomenti)** su facce/spigoli con dimensione e rapporto.
- Test: piastra con foro (Kt): controllo sul foro a 1/4 della dimensione globale -> elementi in piu' vicino al foro (contare i nodi
  entro 2 mm dal bordo del foro con `GetNodes`), Kt piu' vicino a Peterson 2,721 rispetto ai 2,657 attuali, elementi lontani invariati.

### E3 — Posizione del fattore di sicurezza minimo
- Un solo materiale e criterio von Mises: FOS = snervamento / VM nodale -> il minimo e' nel NODO del VM massimo (gia' restituito
  in `max_at_mm`). Riportarlo come `factor_of_safety.min_at_mm` con la spiegazione, e controllare che snervamento/VM_max = FOS min dell'API (< 0,1 %).
- Piu' materiali: minimo per corpo (`GetMinMaxStress` con selezione del corpo invece di NULL) diviso per lo snervamento del corpo;
  il minimo globale e' il minore fra i corpi.
- Test: trave del blocco 5 (FOS min all'incastro) e assieme con due materiali diversi (acciaio + alluminio): il minimo cade nel corpo giusto.

### E4 — Carichi remoti e carico da cuscinetto
- API: carico remoto (forza/momento in un punto, collegamento rigido o distribuito) e carico da cuscinetto su faccia cilindrica
  **(da verificare in `cosworks_dump.txt`)**.
- Test: (1) trave incastrata, forza remota 100 N applicata 50 mm oltre l'estremo libero -> reazione 100 N e momento all'incastro
  100 N x 0,25 m = 25 N*m (somma dei momenti delle reazioni nodali); (2) carico da cuscinetto 1000 N su foro -> reazione 1000 N,
  distribuzione sinusoidale (pressione massima al centro del semicilindro caricato).

### E5 — Studi non statici: frequenze proprie, buckling, termico stazionario
- `CreateNewStudy2(nome, tipo, err)`: il tipo oggi e' sempre 0; `create_static_study(analysis=...)` ha gia' il parametro ma lo
  ignora (e lo schema del tool non lo espone) -> collegarlo (tipi: frequenze, buckling, termico **(da verificare i valori)**). Opzioni: numero di modi (frequenze/buckling).
- Risultati: frequenze (Hz) e fattori di carico critico per modo; temperature e flusso termico per il termico.
- Test con soluzione chiusa (trave 200x20x10, AISI 1020: E = 200000 MPa, rho = 7900 kg/m3 letti dalla libreria):
  - frequenze, mensola: f1 = (1,8751^2 / 2 pi) sqrt(E I / (rho A L^4)) = **203,2 Hz** (flessione sullo spessore 10 mm) e
    **406,4 Hz** sull'altro asse; atteso entro 1-2 % (il modello 3D e' un po' piu' rigido della trave di Eulero).
  - buckling, mensola compressa: Pcr = pi^2 E I / (4 L^2) = **20562 N**; con 1000 N il fattore di carico atteso e' **20,56**.
  - termico: barra con T = 100 gradi C e 0 gradi C alle estremita' -> profilo lineare lungo la barra; flusso = k A dT / L
    (k letto dalla libreria; con k = 47 W/mK: 4,7 W).

---

## Ripresa dei parziali (riaperti il 2026-10-12)

### B4 — posizione angolare del foro su facce cilindriche
- Oggi: foro radiale con Ø e volume giusti, ma `HoleWizard5` lo mette in un'altra posizione angolare (R30 asse X: pick a 45 gradi ->
  foro a -45; lo scarto cambia con assi e cilindri decentrati). Sulle facce PIANE di qualunque orientamento invece il punto e' esatto.
- Idea 1 (preferita): piano tangente. Costruire un piano di riferimento tangente al cilindro nel punto richiesto (normale = direzione
  radiale dal punto sull'asse al punto, calcolata da `CylinderParams`), creare il foro sul piano (posizionamento esatto gia' verificato
  sui piani) con condizione finale riferita alla faccia cilindrica o profondita' misurata dalla linea di contatto; nascondere il piano.
  Da verificare: che il piano tangente sia accettato da `HoleWizard5` come faccia di posizionamento (altrimenti piano con offset di 0,01 mm).
- Idea 2: dopo la creazione, leggere il punto dello schizzo di posizione del foro (sotto-feature), confrontarlo con il punto richiesto e
  spostarlo (`EditSketch` + coordinate del punto, poi ricostruzione); serve se lo schizzo di posizione e' un 3D sketch modificabile.
- Verifica (test esistente in `test_modeling_extra_live.py`, sezione B4): per pick a 0, 45, 90, 180 gradi e cilindri decentrati /
  con asse Y o Z, l'asse del foro misurato con `list_entities` passa per il punto richiesto (scarto angolare < 0,01 gradi), Ø e volume
  come oggi. Se nessuna idea funziona: restare `[~]` con il risultato delle prove.

### C5 — ingranaggio, vite e blocco che il solutore non propaga
- Oggi: creati e letti dal modello (rapporto 2:1, passo 2 mm/giro), ma `SetTransformAndSolve2` e `IDragOperator` non muovono la seconda
  ruota / la chiocciola; lo studio di movimento con motore rotativo non ha prodotto moto nell'istanza NASCOSTA.
- Prova 1: stesso studio di movimento (Animazione, motore rotativo 1 giro, `Calculate`) in un'istanza dedicata VISIBILE (minimizzata),
  poi lettura della posa dei componenti a fine studio (`MotionStudy` -> tempo finale -> `Transform2`). Atteso: seconda ruota -0,5 giri,
  chiocciola +2 mm per giro.
- Prova 2: `IDragOperator` in istanza visibile con `DynamicClearance`/`CollisionDetection` disattivati e passi piccoli (es. 10 x 36 gradi):
  il solutore di trascinamento risolve gli accoppiamenti meccanici, il `SetTransformAndSolve2` diretto no.
- Prova 3 (blocco): dopo un `ForceRebuild3`, leggere i gradi di liberta' con `_as_dof_basis` (C7) invece di muovere: un blocco
  corretto lascia 0 DOF; se l'API ne vede 3 di rotazione, documentarlo.
- Verifica: rapporto misurato = rapporto impostato entro 0,1 %, avanzamento della vite = passo x giri entro 0,01 mm.
  Se funziona solo con l'istanza visibile, dichiararlo nel risultato del tool.

### C3 — rotazione nei passi di traslazione dell'esploso (priorita' bassa)
- Oggi: `AddExplodeStep2` non memorizza l'angolo nei passi di traslazione (nei passi radiali si'). Prove: `IExplodeStep` dopo la
  creazione (proprieta' di rotazione scrivibili? `BeginEdit/EndEdit` come per i carichi della simulazione), oppure un passo di
  traslazione + un passo di sola rotazione sullo stesso componente. Verifica: angolo letto dalla matrice esplosa (come per il radiale).

## Problemi notati rileggendo il codice (senza SolidWorks)
- `import_model(merge_faces=...)`: parametro del metodo mai usato, non esposto nello schema (vedi D9).
- `create_static_study(analysis=...)`: parametro del metodo ignorato, non esposto nello schema; lo studio e' sempre statico (vedi E5).
- `get_part_mass_properties(configuration=...)`: se la ricerca del corpo dopo il cambio di configurazione fallisce, la funzione esce
  senza riattivare la configurazione di partenza (il ripristino avviene solo sul percorso normale).
