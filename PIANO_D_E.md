# PIANO DI LAVORO — dal punto attuale a un server MCP completamente funzionante

Aggiornato il 2026-10-13, scritto in una sessione cloud **senza SolidWorks**: niente di quanto segue e' stato provato dal vivo.
Le API marcate **(da verificare)** vengono dalla documentazione, non da prove: prima di scrivere codice controllarle nella type
library (`sldworks.tlb`, `cosworks.tlb`) o in `scripts_tmp/cosworks_dump.txt`, come nei blocchi precedenti.
Regole sempre valide (vedi `CLAUDE.md`): istanza dedicata, 0 orfani, preferenze salvate e ripristinate, ogni voce chiusa con un numero misurato.

## Cosa vuol dire "completamente funzionante"
Il lavoro e' finito quando sono vere TUTTE queste condizioni:
1. **Copertura**: ogni voce di `LIMITI.md` e' `[x]` (misurata) oppure `[~]` con la prova che il limite e' di SolidWorks e il tool lo
   dichiara nel risultato. Nessuna voce `[ ]`.
2. **Regressione verde** in un colpo solo con `tests\run_all.py`: tutti i test live + offline, 0 processi orfani, istanza di Elia intatta,
   **in italiano e in inglese** (G1).
3. **Robustezza** (fase 5): nessun tool puo' bloccare il server per sempre; un crash di SolidWorks produce un errore chiaro e il server
   si riprende; chiudendo il client non restano processi; nessuna preferenza globale cambiata dopo una sessione.
4. **Uso reale** (fase 6): gli scenari di prova eseguiti da Claude Desktop/Code partendo da una richiesta a parole arrivano al risultato
   senza interventi manuali, e i file prodotti passano i controlli (`inspect_export_file`, misure).
5. **Rilascio** (fase 7): installazione da zero seguendo il README su un PC pulito, versione taggata, note di rilascio.

## Riepilogo delle fasi
| Fase | Contenuto | Dove | Stima (sessioni sul PC) | Dipende da |
|---|---|---|---|---|
| 0 | Verifica di quanto fatto nel cloud (regressione in italiano) | PC | 1 | - |
| 1 | Prova in inglese (G1) | PC | 1 | 0 |
| 2 | Ripresa dei parziali B4, C5, C3 | PC | 2-3 | 0 |
| 3 | Gruppo D (dati ed export) | PC (+ parti offline) | 4-6 | 0 |
| 4 | Gruppo E (simulazione) | PC | 4-6 | 0 |
| 5 | Robustezza del server | cloud + PC | 2-3 | 0 |
| 6 | Prove d'uso reali con un client MCP | PC | 1-2 | 2, 3, 4, 5 |
| 7 | Rilascio | cloud + PC | 1 | 6 |

Le fasi 2, 3, 4 e 5 sono indipendenti fra loro dopo la fase 0: si possono alternare. Ordine consigliato: 0 -> 1 -> 5 (le parti offline
si possono fare anche subito nel cloud) -> 2 -> 3 -> 4 -> 6 -> 7. Una "sessione" = una sessione di Claude Code sul PC con una
regressione completa alla fine (`run_all.py` dura circa 1-2 ore).

---

## Fase 0 — Verifica di quanto fatto nel cloud (2026-10-12/13)
Obiettivo: confermare che le modifiche fatte senza SolidWorks non hanno rotto niente. Nessun lavoro nuovo prima che sia verde.
1. `git pull`, `python tests\test_offline.py` (atteso 83/83).
2. `.venv\Scripts\python.exe tests\run_all.py` (italiano). Atteso: stessi numeri della regressione del 2026-10-11
   (modeling 175, modeling_extra 240, drawings 65, drawing_quality 139, assembly 113, assembly_extra 213, data 159, simulation 120).
3. Se qualcosa e' rosso, i sospettati in ordine di probabilita':
   - smistamento dei tool base (`server.py`, `BASE_DISPATCH`): un tool base che prima riceveva un default diverso;
   - preferenze anti-finestre (`_prepare_prefs` all'inizio di ogni tool, `_restore_prefs` alla fine): una finestra di dialogo che
     compare a meta' di un tool (sintomo: test appeso) -> controllare quale preferenza manca;
   - `tests/live_common.py` (Client comune, traduzione dei nomi: con SolidWorks italiano non deve cambiare nulla);
   - `data_export.py`: controllo dei nomi di configurazione (un test che passa un nome di configurazione scritto diverso),
     rifiuto del rinomina-e-sovrascrivi negli export, `pdf3d` nel risultato di `inspect_export_file`;
   - `simulation.py`: schizzo temporaneo del sistema di riferimento delle forze (ora si cancella solo quello nuovo);
   - lingua: `_std_ref_feature` al posto dei nomi italiani nei piani degli assiemi; testi delle tavole (devono restare italiani).
4. Controlli a mano (5 minuti):
   - nel proprio SolidWorks, dopo la regressione: Opzioni > Generale, "Immetti il valore della quota" deve essere com'era prima
     (le preferenze ora si ripristinano dopo ogni tool);
   - con `SW_MCP_INSTANCE=dedicated`, aprire e chiudere Claude Desktop: il processo SolidWorks nascosto deve sparire
     (chiusura all'uscita del server, solo se non ci sono documenti non salvati).
5. Dal vivo, le prime misure nuove: STEP d'assieme (`product_definitions`, `assembly_occurrences` sul file di `test_assembly_live`),
   `pdf3d.prc_ok` sul PDF 3D di `test_data_live` (aggiungere le due verifiche ai test).
6. Esiti in `STATO.md` (tabella), eventuali trappole nuove in `STATO_STORICO.md`.
**Fatto quando**: regressione verde + controlli a mano ok.

## Fase 1 — Prova in inglese (G1)
1. In SolidWorks: Strumenti > Opzioni > Generale, attivare "Usa lingua inglese" e i nomi di feature/file in inglese (nomi esatti
   delle opzioni da controllare), riavviare. Le preferenze sono globali: farlo quando non si lavora a mano.
2. `connect_solidworks` deve riportare `ui_language = english`.
3. `tests\run_all.py`. I test traducono i nomi italiani (`tests/live_common.py`, tabella `_IT_EN`).
4. Per ogni rosso: se e' un nome tradotto male -> correggere `_IT_EN`; se e' un nome che il server cerca -> spostarlo in
   `solidworks_mcp/utils/sw_lang.py` con entrambe le varianti (MAI nomi fissi nel codice, vedi `CLAUDE.md`).
5. Guardare a occhio le tavole (`test_output/qual_*.png`): scritte del cartiglio verticale, "VIEW A", nota degli smussi in inglese.
6. Rimettere l'italiano, rilanciare almeno `run_all.py drawings data` per conferma.
**Fatto quando**: regressione verde in inglese e in italiano -> G1 `[x]` in `LIMITI.md` (con i numeri).

## Fase 2 — Ripresa dei parziali (schede in fondo: B4, C5, C3)
- **B4** (posizione dei fori su facce cilindriche): provare il piano tangente; misura = asse del foro per il punto richiesto (< 0,01 gradi)
  su 4 posizioni angolari e 3 orientamenti del cilindro.
- **C5** (ingranaggio/vite/blocco): studio di movimento in istanza visibile minimizzata; misura = rapporto e passo entro 0,1 %.
- **C3** (rotazione nei passi di traslazione dell'esploso): priorita' bassa, una sessione al massimo; altrimenti resta `[~]`.
**Fatto quando**: ogni voce `[x]` con i numeri, oppure `[~]` con la prova fallita descritta e il tool che lo dichiara.

## Fase 3 — Gruppo D (schede tecniche in fondo)
Ordine e cosa resta da fare per ciascuna voce:
| Voce | Cosa fare sul PC | Parte gia' pronta | Misura che la chiude |
|---|---|---|---|
| D5 | `hide_reference` anche nei componenti (toggle "nascondi tutti i tipi" o per componente) | - | pixel azzurri 0 con, > 50 senza |
| D6 | test di export/box/immagini sugli assiemi | contatori STEP | n. prodotti/istanze, volume del reimport = somma |
| D7 | parametro `coordinate_system` in `get_part_mass_properties` | `utils/inertia.py` | formule < 0,01 %; segno dei prodotti d'inerzia stabilito |
| D8 | librerie dei materiali da tutte le cartelle configurate | lettura `.sldmat` | massa = volume x densita' del materiale di prova |
| D1 | tool `apply_configuration_table` (`dry_run`) | `utils/config_table.py` | volumi delle 3 configurazioni noti |
| D10 | verifica `pdf3d` sul PDF vero | `utils/pdf3d.py` | `prc_ok` e viste lette dal PDF di SolidWorks |
| D4 | immagini 4K (cattura di stampa), prospettiva | riduzione PNG | 3840x2160, contenuto centrato |
| D9 | opzioni di import (3D Interconnect, assieme/pezzo, diagnostica) | - | n. componenti/corpi, volume dopo riparazione |
| D2 | STEP AP242 | lettore STEP | `application_protocol == AP242` o `[~]` con la prova |
| D3 | eDrawings verificato | - | apertura riuscita o `[~]` |
Per ogni tool nuovo: schema in `data_tools.py` + voce in `DATA_DISPATCH` + metodo (il test offline controlla la coerenza),
annotazione in `safety.py` se scrive file, numero di tool aggiornato in `tests/test_offline.py` (`EXPECTED_TOOLS`) e in `test_data_live.py`.
**Fatto quando**: tutte le voci D `[x]` o `[~]` motivate, regressione verde.

## Fase 4 — Gruppo E (schede tecniche in fondo)
Ordine: **E3** (quasi pronto: posizione del FOS minimo = nodo del von Mises massimo con un solo materiale) -> **E5** (frequenze,
buckling, termico: valori attesi gia' calcolati, 203,2 Hz / 20562 N / 4,7 W) -> **E1** (contatti locali) -> **E4** (carichi remoti,
cuscinetto) -> **E2** (controllo locale della mesh).
Prima di ogni voce: cercare i nomi esatti in `scripts_tmp/cosworks_dump.txt` (rigenerarlo dalla type library se manca).
Nuovi tool in `simulation_tools.py`/`SIMULATION_DISPATCH`; aggiornare il conteggio dei tool.
**Fatto quando**: tutte le voci E `[x]` o `[~]` motivate, regressione verde.

## Fase 5 — Robustezza del server
**CHIUSA il 2026-10-17** (esiti e misure in `STATO.md`): 1, 2, 5, 6, 7, 8, 9 fatti; 3 e 4 verificati in fase 0; 10 rinviato (facoltativo).
Oggi le chiamate COM sono sincrone dentro il gestore MCP: se SolidWorks si blocca (finestra di dialogo, calcolo lungo), il server
non risponde piu'. Lavori, con la parte che si puo' fare nel cloud (C) o solo sul PC (PC):
1. **Timeout generale dei tool** (C + PC). Oggi solo `run_simulation` ha un watchdog. Generalizzarlo: per ogni tool un tempo
   massimo (default 300 s, configurabile in `config.json`); allo scadere, in modalita' dedicata si chiude il PID e si restituisce un
   errore chiaro; con l'istanza dell'utente si restituisce un errore che chiede di controllare SolidWorks (mai uccidere la sua istanza).
   Attenzione al modello a thread COM (STA): il watchdog osserva, non chiama SolidWorks da un altro thread.
2. **Ripresa dopo un crash** (PC). Oggi in modalita' dedicata, se SolidWorks muore, il server dice "riavvia il server". Aggiungere
   `SW_MCP_AUTORESTART=1`: al tool successivo si rilancia l'istanza e si avverte che i documenti aperti sono persi. Test: uccidere
   il PID a meta' test e verificare che il tool seguente riparta.
3. **Chiusura all'uscita** (FATTO nel cloud il 2026-10-13, da verificare in fase 0): il server chiude l'istanza dedicata quando il
   client si disconnette, ma solo se non ci sono documenti non salvati.
4. **Preferenze** (FATTO nel cloud il 2026-10-13, da verificare in fase 0): impostate all'inizio di ogni tool e ripristinate alla fine.
5. **Peso dei tool per il client** (C). I 196 tool costano circa 27.000 token di descrizioni a ogni conversazione (base 2.400,
   modellazione 6.800, disegni 6.300, assiemi 5.600, dati 3.100, simulazione 2.000). Aggiungere `SW_MCP_TOOLSETS`
   (es. `base,modeling,drawings`) per esporre solo i gruppi che servono; default: tutti. Test offline: con un sottoinsieme, tool esposti =
   tool smistabili, gli altri rispondono con un errore che dice quale gruppo attivare.
6. **Descrizioni dei tool** (C). Oggi sono un misto di italiano e inglese. Sceglierne una lingua (proposta: inglese per i client,
   che e' anche la lingua dei nomi dei parametri), unita' di misura in ogni parametro, un esempio per i tool complessi. Il test offline
   controlla che ogni parametro abbia una descrizione.
7. **`execute_python`** (decisione di Elia, C). Esegue codice arbitrario. Proposta: disattivato di default, attivabile con
   `SW_MCP_ALLOW_PYTHON=1`; nella descrizione resta l'avviso.
8. **Pulizia** (C). Una trentina di import non usati (pyflakes); poi il CI fallisce su qualunque avviso di pyflakes, non solo sui
   nomi non definiti.
9. **Log** (C). File di log nella cartella del pacchetto, senza rotazione: spostarlo in `%LOCALAPPDATA%\solidworks-mcp\` con rotazione
   (es. 5 file da 5 MB), percorso in `config.json`.
10. **Extra MCP** (facoltativo, C). Risorse (documento attivo, stato dell'istanza) e prompt pronti per i flussi lunghi (es. "pezzo +
    messa in tavola + PDF").
**Fatto quando**: punti 1-4 verificati dal vivo (test che fanno scattare timeout e crash), 5-9 coperti dal test offline.

## Fase 6 — Prove d'uso reali con un client MCP
I test live chiamano i tool uno per uno con argomenti scritti a mano. Qui si verifica che un modello, partendo da una richiesta a
parole, sappia usarli. Da Claude Desktop o Claude Code, con istanza dedicata, per ogni scenario: trascrizione salvata, file prodotti
controllati con `inspect_export_file`/misure, note su dove il modello ha sbagliato tool o parametri (-> migliorare le descrizioni, fase 5.6).
| Scenario | Richiesta | Controllo |
|---|---|---|
| S1 | "Flangia Ø120 x 15 con 6 fori M8 su Ø90, foro centrale Ø30, in AISI 304; messa in tavola A3 quotata; PDF" | volume e massa a mano; tavola a occhio; PDF valido |
| S2 | "Staffa a L 80x60x40 sp. 6 con due asole, raccordo R10, smusso 1x45 sugli spigoli esterni" | volume a mano; feature presenti |
| S3 | "Assieme perno-boccola-staffa con accoppiamenti, vista esplosa, distinta e palloncini" | gradi di liberta' attesi; BOM con 3 righe |
| S4 | "Trave 200x20x10 incastrata, 100 N in punta: freccia e tensione massima, fattore di sicurezza, mappa PNG" | 0,80 mm e 30/60 MPa (blocco 5) |
| S5 | "Tre configurazioni da questa tabella CSV, esporta uno STEP per ciascuna" | volumi e file STEP validi (D1) |
| S6 | gli stessi S1 e S4 con SolidWorks in inglese | come sopra |
| S7 | "Chiudi tutto" con un documento modificato | rifiuto con spiegazione (B6), nessun dato perso |
**Fatto quando**: tutti gli scenari arrivano al risultato senza correzioni manuali (sono ammessi tentativi del modello, non interventi
dell'utente). Le trascrizioni utili vanno in `docs/esempi/` come esempi per il README.

## Fase 7 — Rilascio
1. `pyproject.toml` con dipendenze e comando `solidworks-mcp`; versione presa da `solidworks_mcp/__init__.py`.
2. `CHANGELOG.md` dal 4.x dell'autore originale al 5.x/6.0 (blocchi 1-5, gruppi A-G).
3. Installazione da zero su un PC/VM pulito seguendo SOLO il README (Windows x64 e ARM64 con Python x64), con Claude Desktop e Code.
4. Tag `v6.0.0` su `main` con note di rilascio; README con gli esempi della fase 6.
**Fatto quando**: installazione pulita riuscita e scenario S1 eseguito sulla macchina pulita.

---

# SCHEDE TECNICHE

## Gruppo D

### D1 — Configurazioni da tabella (CSV/JSON), design table vera solo con Excel
- Nuovo tool `apply_configuration_table(table, create_missing=true, dry_run=false)`: `table` = percorso CSV/JSON o righe inline.
  Intestazioni con la stessa convenzione delle design table, cosi' la tabella si puo' riusare in Excel:
  `D1@Schizzo1` (quota, mm o gradi), `$STATO@Foro1` (`S`/`R` = soppressa/attiva), `$PRP@Codice` (proprieta' della configurazione),
  `$MATERIALE` (opzionale), prima colonna = nome della configurazione.
- **Parte pura FATTA (2026-10-12)**: `solidworks_mcp/utils/config_table.py` (`parse_configuration_table`, `plan_configuration_changes`),
  coperta da `test_offline.py`. Sul PC resta: il tool che esegue le azioni del piano e il test live.
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
- **Parte pura FATTA (2026-10-12)**: `solidworks_mcp/utils/inertia.py` (`mass_properties_in_frame`, `frame_from_sw_transform`),
  verificata offline contro il calcolo diretto su masse puntiformi. Da stabilire dal vivo la convenzione dei termini fuori
  diagonale di `GetMomentOfInertia` (`offdiag="tensor"` o `"products"`): blocco col baricentro in (15, 10, 0) mm, termine xy
  all'origine = -m*0,015*0,010 (tensor) o +m*0,015*0,010 (products).
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
- **FATTO offline (2026-10-12)**: `solidworks_mcp/utils/pdf3d.py`; `inspect_export_file` riporta `pdf3d` (stream PRC/U3D
  decompresso con magic, pagine, annotazioni 3D, viste), anche dentro object stream. Sul PC: confrontarlo col PDF di `test_data_live`
  e aggiungere al test la verifica `pdf3d.prc_ok`.
- Prima: presenza di `/3D` e `PRC`. Lettura completa in Python puro: trovare l'oggetto `/Subtype /PRC`, decomprimere lo stream
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

## Problemi noti ancora aperti nel codice
- ~~`import_model(merge_faces=...)`~~: tolto con D9 (2026-10-17).
- `create_static_study(analysis=...)`: parametro del metodo ignorato, non esposto nello schema; lo studio e' sempre statico (si sistema con E5).
- `_as_collapse` (assiemi) chiude la PRIMA vista esplosa della configurazione, non necessariamente quella attiva: con piu' viste
  esplose potrebbe non richiudere quella mostrata (da verificare quando capita; basso impatto).
