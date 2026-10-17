# Esempi d'uso reali

Sette prove d'uso fatte da un modello (Claude) che pilota il server con i suoi tool, su un'istanza dedicata di SolidWorks 2026. Ogni file riporta la richiesta, la sequenza dei tool chiamati (con argomenti ed esito in una riga), il controllo con i numeri e le note. Le chiamate fallite sono lasciate: il modello le ha corrette da solo.

Convenzioni: `<progetto>` sta per la cartella del repository; nelle note dei disegni "Ø" e' il simbolo di diametro; le chiamate `__schema__` e `__list__` non sono riportate.

| Scenario | Cosa mostra |
|---|---|
| [S1](S1_flangia.md) | Flangia con 6 fori, messa in tavola A3 quotata e PDF (volume 153317,58 mm3, massa 1,22654 kg) |
| [S2](S2_staffa_L.md) | Staffa a L con asole, raccordo e smussi (volume 30356,593 mm3) |
| [S3](S3_assieme_perno_boccola.md) | Assieme con accoppiamenti, esploso, distinta e palloncini (2 gradi di liberta', 3 righe di distinta) |
| [S4](S4_mensola_simulazione.md) | Trave a mensola con simulazione statica (freccia 0,7964 mm contro 0,8000 teorici) |
| [S5](S5_configurazioni_csv.md) | Tre configurazioni da tabella CSV e tre STEP (30000 / 40000 / 50000 mm3) |
| [S6](S6_inglese.md) | S1 e S4 con SolidWorks in inglese (stessi numeri) |
| [S7](S7_chiudi_con_modifiche.md) | Chiusura con modifiche non salvate (rifiutata, nessun dato perso) |
