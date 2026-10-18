# Changelog

Tutte le modifiche importanti a SolidWorks MCP sono scritte qui, dalla versione piu' recente.
Il formato segue [Keep a Changelog](https://keepachangelog.com/it-IT/1.1.0/). Dettagli, misure e trappole dell'API: `STATO_STORICO.md`.
Ogni numero citato e' stato misurato da un test sul PC di sviluppo (SolidWorks 2026 SP4.1 Student).

## [6.0.0] - 2026-10-18

Il server arriva a 202 tool (201 + `execute_python`, che e' disattivato di default).

### Aggiunto
- Gruppo D, dati ed export (D1-D10):
  - D1: tool `apply_configuration_table`, configurazioni da tabella CSV/JSON (Excel non c'e': la design table vera non e' possibile). Volumi Default/Lunga/Pieno 116607,26 / 233214,53 / 120000,00 mm3 contro 116607,08 / 233214,16 / 120000,00 calcolati.
  - D3: verifica strutturale dei file eDrawings (ZIP valido, corpi distinti, anteprima); aprirli con eDrawings non e' automatizzabile.
  - D4: immagini oltre 2000x1400 (4K: 3840x2160 esatti, centro del pezzo al centro dell'immagine) e vista in prospettiva.
  - D5: `hide_reference` nasconde anche i riferimenti dei componenti negli assiemi (1596 pixel azzurri senza, 0 con).
  - D6: assiemi esportabili in STL/STEP, con box e immagini. Box dell'assieme: scarto 0,0 mm. STEP reimportato: 135456,7664 contro 135456,8204 mm3.
  - D7: `get_part_mass_properties(coordinate_system=)`, proprieta' di massa in un sistema di coordinate utente (errore del baricentro 5,3e-7).
  - D8: materiali personalizzati da cartelle utente (`.sldmat` di prova da 1234 kg/m3: massa 0,14808 kg = 120000 mm3 x 1234).
  - D9: opzioni di import (`step_as`, `interconnect`, `diagnose`); uno STEP con una faccia mancante torna solido da 120000,0 mm3.
  - D10: lettura piu' a fondo del PDF 3D (flusso PRC, 1 annotazione 3D, vista 'Default').
- Gruppo E, simulazione (5 tool nuovi: `add_temperature`, `add_remote_load`, `add_bearing_load`, `add_simulation_contact`, `add_mesh_control`):
  - E5: studi di frequenze, buckling e termici stazionari. Frequenze proprie: 203,73 Hz contro 203,20 della teoria (+0,26 %); buckling: fattore 20,620 contro 20,562; termico: gradiente 500,00 K/m, flusso 23500,0 W/m2.
  - E1: contatti locali (senza compenetrazione, incollato, accoppiamento forzato, libero, parete virtuale). Compressione: 0,000499 mm contro 0,000500 della formula F L/(E A).
  - E4: carichi remoti e da cuscinetto. Trave con 100 N in (250,0,0): momento di reazione -25,0000 N*m, come atteso; cuscinetto da 1000 N: reazione -1000,0 N.
  - E2: controllo locale della mesh. Piastra con foro: nodi sulla faccia del foro da 102 a 1026, fattore di concentrazione 2,725 contro 2,721 della teoria (0,14 %).
  - E3: posizione del fattore di sicurezza minimo e corpo critico. Assieme acciaio + alluminio: minimo 1,93399 nel corpo di alluminio a [104,10,-5] mm.
  - `create_static_study(analysis, modes)` crea anche studi di frequenze, buckling e termici; `get_simulation_results` risponde secondo il tipo di studio.
- Fase 5, robustezza (gruppo H):
  - un solo thread per le chiamate COM e tempo massimo per ogni tool (`tool_timeout`, default 300 s, `SW_MCP_TOOL_TIMEOUT`); provato con un limite di 15 s: errore a 15,1 s, tool seguente subito libero.
  - `SW_MCP_AUTORESTART=1`: se l'istanza dedicata muore, il tool seguente la rilancia in circa 15 s e avverte dei documenti persi.
  - `SW_MCP_TOOLSETS`: sceglie i gruppi di tool da esporre (`base`, `modeling`, `drawings`, `assembly`, `data`, `simulation`).
  - log con rotazione (5 file da 5 MB) in `%LOCALAPPDATA%\solidworks-mcp\`.
  - controllo `pyflakes` nel CI: fallisce con qualunque avviso.
- Prova completa con SolidWorks in inglese (G1): il server funziona nelle due lingue; `connect_solidworks` riporta `ui_language`.
- Formati verticali ISO in inglese (`a3 - iso portrait en.slddrt`) e scritte delle tavole nella lingua di SolidWorks.
- `pyproject.toml` e comando `solidworks-mcp` per avviare il server.
- Test live nuovi: `test_data_extra_live.py`, `test_simulation_extra_live.py`, `test_timeout_live.py`. Test offline da 83 a 147.

### Cambiato
- `execute_python` e' disattivato di default: si attiva con `SW_MCP_ALLOW_PYTHON=1` (scelta confermata da Elia).
- Descrizioni dei tool e dei parametri in inglese, con unita' ed esempi; 213 descrizioni aggiunte. L'elenco dei tool passa da 102.413 a 112.862 caratteri (+10 %).
- Le note dei tool distruttivi sono ora "[DESTRUCTIVE: ...]".
- Il log non e' piu' scritto nella cartella del pacchetto.
- Le preferenze anti-finestre di SolidWorks si impostano all'inizio di ogni tool e si ripristinano alla fine.
- L'istanza dedicata si chiude da sola all'uscita del server (solo se non ci sono documenti non salvati).
- `export_model_image`: i valori delle preferenze di cattura TIFF/stampa sono ora 300 DPI e carta Letter.
- Versione del pacchetto 6.0.0.

### Corretto
- B4: fori Hole Wizard su facce cilindriche nella posizione indicata. Asse del foro sull'asse del cilindro (distanza 0,00e+00 mm); volume 2049,337 contro 2049,807 mm3 (0,023 %).
- C5: ingranaggio, vite e blocco ora si muovono davvero (accoppiamento d'angolo temporaneo). Ingranaggio 2:1: +30 gradi su A, -60,0000 su B; vite da 2 mm/giro: 0,5000 mm per 90 gradi. Era sbagliato anche il passo della vite (2 mm/giro diventava 500).
- La configurazione attiva torna quella di partenza anche se un tool fallisce a meta'; un nome di configurazione inesistente ora da' errore (prima si lavorava in silenzio su quella sbagliata).
- `export_model` e `export_drawing` non cancellano piu' un file esistente quando il nome cambia (`.iges` in `.igs`) senza `overwrite=true`.
- Lo schizzo temporaneo della simulazione cancellava a volte uno schizzo dell'utente: ora si cancella solo quello appena creato.
- Le feature soppresse per una misura tornano attive anche in caso di errore.
- La nota "smussi non quotati" non si sovrappone piu' a una quota (ora la sua larghezza e' misurata, non stimata).
- Il timeout scattava anche sull'avvio dell'istanza; `connect_solidworks` chiamato due volte rispondeva "non risponde piu'" con l'istanza viva.
- Nomi italiani fissi tolti dai test e dal server: regressione in inglese verde (G1). Peso del cartiglio d'assieme 563,51 g in italiano e in inglese.
- Box dell'assieme: ora calcolato dai pezzi (`GetBox` sovrastimava di 0,165 mm in X).
- Import non usati e variabili inutilizzate tolti dal pacchetto.
- Ripresa automatica (`SW_MCP_AUTORESTART=1`): se l'istanza dedicata era morta, il tool che la rilancia riceveva solo il tempo
  normale del tool e poteva scadere durante l'avvio (23 s contro 15 nel test); ora riceve anche il tempo di avvio.
- Descrizioni chiarite dopo le prove d'uso: `create_hole` (ogni punto dato, anche `face_point`, diventa un foro), `save_drawing`
  (`filepath` obbligatorio), `rebuild_model` (solo pezzi).

### Limiti noti
- C3: nei passi di traslazione dell'esploso la rotazione non si puo' impostare (`AddExplodeStep2` non la memorizza in SolidWorks 2026). Si ottiene solo con un passo radiale a distanza 0, attorno alla direzione radiale (45,0000 gradi misurati); il tool lo suggerisce in `rotation_note`.
- D2: lo STEP AP242 non si scrive con l'edizione Student: il file resta AP203 anche con la preferenza a 242. AP214 funziona; `export_model` lo dichiara in `warning`.
- Contatto locale senza compenetrazione in trazione: se il pezzo e' tenuto solo dal contatto e si stacca, il solutore puo' bloccarsi fino al timeout (una prova ha finito, una no). L'avviso e' nella descrizione di `add_simulation_contact`; il caso e' fuori dal test di default (`SX_E1_TRAZIONE=1`).
- In tavola la quota del cerchio dei fori (es. Ø90 di una flangia) non viene messa da `insert_model_dimensions`: si aggiunge con una nota.

Regressione completa in italiano del 2026-10-18 (`test_output/regressione_20261018_1148.md`): offline 147/147, modeling 175/175,
modeling_extra 259/259, drawings 65/65, drawing_quality 139/139, assembly 113/113, assembly_extra 214/214, data 183/183, data_extra 110/110,
simulation 120/120, simulation_extra 181/181; timeout 15/18, poi 18/18 due volte dopo la correzione della ripresa automatica. 0 processi rimasti.

## [5.0.0] - 2026-10-12

La riscrittura del progetto originale (lavoro dal 2026-10-09). Alla chiusura: 196 tool.

### Aggiunto
- Modellazione 3D: quote e relazioni di schizzo, rivoluzione, sweep, loft (anche con guide), shell, nervature, sformi, ripetizioni, specchiatura, piani e sistemi di coordinate. Volumi misurati contro il calcolo a mano, scarto sotto 0,01 % (albero 69704,09 mm3, flangia 99118,18 mm3).
- Hole Wizard con 6 standard (ISO, ANSI metrico, ANSI pollici, DIN, BSI, JIS) e molte teste (36 combinazioni misurate); UNI non esiste nel database di SolidWorks.
- Raccordo a raggio variabile, convert_entities, taglio fino a una superficie, rivoluzione di taglio, sweep di taglio: tutti verificati con volumi (scarti sotto 0,05 %; loft con guide curve -0,74 % dal modello ideale, dichiarato).
- Disegni ISO in primo diedro: viste standard, proiettate, sezioni (anche a gradini e allineate), dettagli, ausiliarie, interrotte e ritaglio (cerchio, rettangolo, poligono); quote automatiche in stile ISO 129, tolleranze, GD&T con 14 caratteristiche agganciate allo spigolo, rugosita', tabella fori, distinta, palloncini, linee di esplosione.
- Scelta automatica di foglio e scala (A4-A0), formati ISO verticali A3-A0 generati in `formats/`.
- Assiemi: inserimento, accoppiamenti (anche limiti, larghezza, simmetrico, tangente), ripetizioni, specchiatura con pezzo speculare, sostituzione, viste esplose (assi, direzioni libere, radiale, automatica nativa e per accoppiamenti), interferenze, gradi di liberta' misurati muovendo il componente. Massa dell'assieme 0,563505 kg = somma dei componenti.
- Dati ed export: materiali, massa e inerzie, proprieta' personalizzate, equazioni, configurazioni, export STL/3MF/STEP/IGES/Parasolid/PDF 3D/eDrawings con verifica del file, import (reimport con scarto del volume sotto 0,015 %), immagini, misure.
- Simulazione statica lineare (18 tool): vincoli, forze, coppie, pressioni, gravita', contatto globale, mesh, risultati e mappe a colori. Trave: spostamento 0,7970 mm contro 0,8000 della teoria; piastra con foro: fattore di concentrazione 2,657 contro 2,721.
- Sicurezza: tool distruttivi annotati (21), `overwrite` obbligatorio per sovrascrivere file, `close_document` che rifiuta di chiudere con modifiche non salvate, `delete_feature` con `confirm` e controllo delle feature dipendenti.
- Modalita' `SW_MCP_INSTANCE=dedicated`: istanza nascosta di SolidWorks propria, chiusa alla fine; l'istanza dell'utente non si tocca.
- Test live per area (client MCP reale, volumi e quote misurati) e test offline senza SolidWorks, anche su GitHub Actions a ogni push.
- Smistamento dei tool a tabelle (`BASE_DISPATCH`, `*_DISPATCH`), `README.md` nuovo.

### Cambiato
- Rifatto sulla base originale: tolti i file dell'autore non usati; la configurazione `config.json` e' ridotta alle chiavi lette davvero.
- Dipendenza `mcp<2` (la 2.x ha tolto l'API usata dal server).

### Corretto
- Template non trovati per nome italiano: ora si chiedono a SolidWorks.
- Membri COM senza argomenti letti come metodi (colpiva `get_document_info`, `list_features`, `list_open_documents`): helper `_com`.
- `save_document()` senza nome falliva sempre; `cut_extrude` con "fino in fondo" in due direzioni usava il tipo sbagliato.
- `delete_feature` senza `delete_children` cancellava lo stesso le feature dipendenti.
- Sezioni senza tratteggio, viste ammassate e sovrapposte, "ERRORE:" nel cartiglio.
- Chiave API di OpenRouter dell'autore originale tolta dal repository.

### Limiti noti
- B4: nei fori su facce cilindriche la posizione angolare non era quella indicata.
- C3: nessuna rotazione nei passi di traslazione dell'esploso.
- C5: ingranaggio, vite e blocco creati ma non fatti rispettare dal solutore via API.
- Simulazione: solo contatto globale, nessun studio non statico, mesh senza controllo locale.
- Excel non installato: design table vera non possibile. STEP AP242 non ottenibile (il file e' AP203).

## [4.x]

- Versione originale di [alisamsam/solidworks-mcp](https://github.com/alisamsam/solidworks-mcp): 22 tool di base. Non descritta in dettaglio qui.
