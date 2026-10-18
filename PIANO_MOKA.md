# PIANO_MOKA — strumenti che servono per ricreare da zero i pezzi della moka

Analisi del 2026-10-18 dei 9 file in `\\Mac\Home\Downloads\Moka_Parts` (8 `.SLDPRT` + `Lid_1.STEP`), fatta **senza SolidWorks**
(c'era una regressione in corso). Ho letto l'albero delle feature direttamente dai file con `scripts_tmp/sldprt_albero.py`
(come funziona: nel suo docstring). Così si ricavano **tipo e ordine** delle lavorazioni, non quote e condizioni di fine.

## Albero delle feature per pezzo

| Pezzo | Lavorazioni in ordine (nomi originali, tipo interno fra parentesi quando serve) |
|---|---|
| Boiler_1 (caldaia) | Sketch1 cerchio → Plane1 sfalsato → Sketch2 → **Loft1** (da cerchio a ottagono) → Boss-Extrude1 (con condizione "Da" di partenza) → **Cosmetic Thread1 M56** esterna → Axis1 da spigolo → Cut-Revolve3, 4, 5 **attorno ad Axis1** → Cut-Extrude1, 2 → Cut-Revolve6 → **foro filettato M8** (Hole Wizard, filetto passante) → Fillet1, 2 |
| Kettle_1 (raccoglitore) | Loft1 cerchio→ottagono → Cut-Revolve1 attorno ad Axis1 → Plane2 (per un punto e una linea di schizzo) → **Loft2 con curve guida** (becco, spline; profili legati ad altri schizzi) → Cut-Extrude1 → Mirror1 → Shell1 → Boss-Extrude1 → Revolve1, 2 → Fillet1, 2 → Cut-Revolve2 → Cut-Extrude2, 3 → Mirror2 → **Move Face1, 4** → **foro filettato M56** (Hole Wizard) → Cut-Extrude4 → Fillet3 → Boss-Extrude2 → CirPattern1 → Plane3 → Boss-Extrude3, 4 → **Move Face5, 6** → Boss-Extrude5 → Fillet4 |
| FilterPlate_1 (piastrina filtro) | Revolve2 → Axis1 → Revolve3 (schizzo con vertice di silhouette) → Cut-Extrude3 (foro Ø piccolo) → Fillet2 → **Fill Pattern18** (fori distribuiti in un contorno di schizzo) |
| Filter_1 (imbuto) | Revolve1 → Fillet1 → Shell1 → Fillet2 → Chamfer1 → Plane1 → Boss-Extrude1 → Cut-Extrude1 (foro) → **Fill Pattern1** |
| Gasket_1 (guarnizione) | Boss-Extrude1 cerchio → Cut-Extrude1 cerchio → Fillet1 (creata nel contesto dell'assieme: accoppiamento InPlace) |
| Valve_1 (valvola) | Boss-Extrude1 → Cut-Revolve1 → **Plane1 di mezzeria** fra due facce → Mirror1 → Boss-Extrude2 + **Cosmetic Thread1 M8** → Boss-Extrude3 → Fillet1 → Boss-Extrude4 → Chamfer1 → Boss-Extrude5 → Fillet2 |
| Knob_1 (pomello) | creato **nel contesto** di `Moka.SLDASM` (riferimenti esterni a Lid_1) → Axis1 → Revolve1 → Fillet1 → **Cavity1** (impronta della vite ISO 7046 M5×12) → **Cosmetic Thread1 M6** → **Body-Delete/Keep1** → Move Face1 |
| countersunk … screw_iso (vite) | parte **Toolbox** ISO 7046-1 M5×12, 3 configurazioni: corpo di rivoluzione → Recess (**loft di taglio**, impronta a croce) → RecPat (ripetizione circolare) → RecessCore (taglio di rivoluzione) → ThreadSchematic (taglio di rivoluzione) → ThdSchPat (ripetizione lineare) |
| Lid_1.STEP (coperchio) | nessuno storico: 59 facce = 40 piane, 9 cilindriche, 2 coniche, 8 B-spline (raccordo ottagono→cerchio); un foro svasato per vite M5 (dal nome del corpo "CSK for M5 Countersunk Flat Head Screw") |

## Cosa c'è già nel server
Estrusioni e tagli con condizioni di fine, rivoluzioni e tagli di rivoluzione, loft (anche di taglio, con guide), shell,
raccordi, smussi, specchiature, ripetizioni lineari e circolari, Hole Wizard (filettati M8 e M56 compresi, svasato M5),
`move_faces`, piani sfalsati/inclinati/per 3 vertici, assi, spline, poligoni, quote verso spigoli del modello, configurazioni.

Confronto con la copia `C:\Users\elia\Downloads\solidworks-mcp-pulito` (2026-10-18): ha 202 tool, tutti presenti anche qui;
qui ce ne sono 8 in più (`move_faces`, `delete_dimension`, `delete_sketch_entities`, `list_sketch_relations`, `move_sketch_point`,
`set_dimension_driven`, `split_sketch_entity`, `toggle_construction`). Gli schemi di estrusione, rivoluzione, loft, piani,
relazioni ed entità sono identici. Nessuno dei 10 strumenti qui sotto c'è nella copia pulita, che in più non ha `move_faces`
(serve a Kettle e Knob).

Confronto con il server `solidworks` collegato a Claude (2026-10-18): espone 209 tool, cioè gli stessi 210 di questo repository
tranne `execute_python` (disattivato apposta); gli schemi di `revolve_cut`, `create_reference_plane`,
`add_sketch_relation`, `loft`, `list_entities` ed `extrude_boss` sono identici a quelli del codice. Nessuno dei 10 strumenti
qui sotto è presente. `execute_python` permetterebbe di aggirarli con codice libero, ma resta spento per sicurezza.

## Strumenti da creare (in ordine di priorità)

1. **`add_cosmetic_thread`**: filettatura cosmetica su uno spigolo circolare scelto per coordinate, esterna o interna,
   standard ISO, misura (M6, M8, M56…), profondità o "fino alla fine". Serve a Boiler (M56), Valve (M8), Knob (M6).
   Oggi `InsertCosmeticThread2` è usato solo dentro `create_hole` per i fori fuori database (`automation/modeling.py`).
2. **`fill_pattern`** (ripetizione di riempimento): confine = faccia piana o schizzo chiuso; elemento = feature esistente
   (es. il taglio del foro) o forma predefinita (cerchio, quadrato, poligono); disposizione perforazione / concentrica /
   quadrata / poligonale; passo, angolo di sfalsamento, margine dal bordo. Serve a FilterPlate e Filter (i fori del filtro).
3. **`create_reference_plane`, modalità nuove**: `mid_plane` (fra due facce o piani), `line_point` (per una linea/spigolo
   e un punto), `normal_to_curve` (normale a uno spigolo o una curva in un punto). Valve (mezzeria), Kettle (Plane2, Plane3).
4. **Asse delle rivoluzioni da asse di riferimento o spigolo**: `revolve_boss`/`revolve_cut` oggi accettano solo un
   segmento dello schizzo. Aggiungere `axis` = nome di un asse (`Axis1`) o `{"edge":[x,y,z]}`. Boiler e Kettle
   (aggirabile disegnando una linea d'asse nello schizzo, ma non è "uguale").
5. **Relazioni di schizzo verso entità esterne**: in `add_sketch_relation`, coincidente/su linea/**perforazione (pierce)**
   verso punti e linee di ALTRI schizzi o spigoli del modello. Servono per legare le curve guida del becco (Kettle Loft2)
   ai profili.
6. **Lavorare con i corpi**: `delete_body` (Elimina/Mantieni corpo), `insert_part` (inserisce un altro pezzo come corpo,
   con posizione) e `combine_bodies` (sottrai/unisci/interseca). Knob: l'impronta della vite si rifà così senza assieme.
   In alternativa, più grande: **`cavity`** e la modifica di un pezzo nel contesto dell'assieme (come era fatto l'originale).
7. **Estrusione con partenza "Da"**: verificare che `start_offset` copra il caso di Boiler; se l'originale parte da una
   superficie o da un vertice, aggiungere `start_from` = `sketch_plane | surface | vertex | offset`.
8. **Lettura completa di una feature esistente** (`get_feature_definition`): per estrusioni, tagli, loft, fori,
   ripetizioni, filettature restituisce condizioni di fine, profondità, riferimenti, profili, misure. Serve per copiare
   gli originali "uguali" invece di misurarli a mano; `list_model_features` dà solo tipo e quote.
9. **Facce con parametri** (per il coperchio STEP): estendere `list_entities` con il tipo di superficie e i parametri
   (piano: normale e distanza; cilindro e cono: asse, raggio, angolo; toro). Così il coperchio si ricostruisce misurato.
10. Facoltativo: **inserire un componente Toolbox** (vite ISO 7046-1 M5×12). Senza, la vite si modella con gli strumenti
    esistenti (rivoluzione, loft di taglio, ripetizioni).

## Stato degli strumenti (2026-10-19)
1 `add_cosmetic_thread` FATTO · 2 `fill_pattern` FATTO · 3 piani `line_point`, `normal_to_curve`, `parallel_point` FATTI, `mid_plane`
`[~]` (offset di meta' distanza, non associativo) · 4 asse di rivoluzione da asse/spigolo FATTO · 5 relazioni esterne FATTE (`pierce`
verso un altro schizzo `[~]`, punto calcolato) · 6 `delete_body`, `insert_part`, `combine_bodies` (+ `list_bodies`) FATTI ·
7 `start_from` FATTO · 8 `get_feature_definition` FATTO · 9 parametri delle facce in `list_entities` FATTO · 10 Toolbox `[~]`
(nessuna API d'inserimento). Dettagli e trappole: `STATO_STORICO.md`, "Lotti di tool nuovi".

## Come proseguire
- Fase 1: creare gli strumenti 1–6 (e 7 dopo la verifica), con un test dal vivo ciascuno e un numero misurato.
- Fase 2, a regressione ferma, su istanza dedicata: aprire ogni file (copiandolo prima, mai sovrascrivere gli originali di
  Elia), leggere quote e definizioni (`list_model_features` con quote, `list_sketch_entities`, strumento 8), salvarle.
- Fase 3: ricostruire ogni pezzo da zero con il server e confrontare volume, massa e ingombro con l'originale.
