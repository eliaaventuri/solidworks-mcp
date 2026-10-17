# S5 - Configurazioni da tabella CSV ed export STEP

## Richiesta

> Tre configurazioni da questa tabella CSV, esporta uno STEP per ciascuna.
>
> Tabella `test_output/s5_tabella.csv`: L150, L200, L250 della quota `D1@Estrusione-Estrusione1`.

## Sequenza dei tool

1. `save_document` `{"filepath":"<progetto>/test_output/s5_trave.SLDPRT","overwrite":true}`  
   -> [ERROR] il tool 'save_document' ha superato 300 s. L'istanza dedicata di SolidWorks (PID 5764) e' stata chiusa perche' bloccata; i documenti non salvati sono persi. Il prossimo tool la rilancia (SW_MCP_AUTORESTART=1).
2. `apply_configuration_table` `{"table":"<progetto>/test_output/s5_tabella.csv"}`  
   -> [ERROR] ATTENZIONE: l'istanza dedicata di SolidWorks (PID 5764) era persa ed e' stata rilanciata (nuovo PID 15600); i documenti aperti e non salvati in quella istanza sono persi. No document open. Use create_new_part first.
3. `open_document` `{"filepath":"<progetto>/test_output/s4_trave.SLDPRT"}`  
   -> [SUCCESS] Opened: s4_trave.SLDPRT
4. `save_document` `{"filepath":"<progetto>/test_output/s5_trave.SLDPRT","overwrite":true}`  
   -> [SUCCESS] Saved: <progetto>\test_output\s5_trave.SLDPRT [SaveAs]
5. `apply_configuration_table` `{"table":"<progetto>/test_output/s5_tabella.csv"}`  
   -> [SUCCESS] 6/6 azioni riuscite (attiva: Default)
6. `export_model` `{"filepath":"<progetto>/test_output/s5_trave_L150.step","configuration":"L150","overwrite":true}`  
   -> [SUCCESS] Esportato STEP (13428 byte): <progetto>\test_output\s5_trave_L150.step
7. `inspect_export_file` `{"filepath":"<progetto>/test_output/s5_trave_L150.step"}`  
   -> [SUCCESS] STEP: schema=AUTOMOTIVE_DESIGN, manifold_solid_brep=1
8. `export_model` `{"filepath":"<progetto>/test_output/s5_trave_L200.step","configuration":"L200","overwrite":true}`  
   -> [SUCCESS] Esportato STEP (13427 byte): <progetto>\test_output\s5_trave_L200.step
9. `inspect_export_file` `{"filepath":"<progetto>/test_output/s5_trave_L200.step"}`  
   -> [SUCCESS] STEP: schema=AUTOMOTIVE_DESIGN, manifold_solid_brep=1
10. `export_model` `{"filepath":"<progetto>/test_output/s5_trave_L250.step","configuration":"L250","overwrite":true}`  
   -> [SUCCESS] Esportato STEP (13418 byte): <progetto>\test_output\s5_trave_L250.step
11. `inspect_export_file` `{"filepath":"<progetto>/test_output/s5_trave_L250.step"}`  
   -> [SUCCESS] STEP: schema=AUTOMOTIVE_DESIGN, manifold_solid_brep=1
12. `list_part_configurations` `{"include_volume":true}`  
   -> [SUCCESS] 4 configurazioni (attiva: Default)

## Controllo

- Volumi 30000 / 40000 / 50000 mm3 = 20 x 10 x L.
- Tre file STEP con 1 solido ciascuno (MANIFOLD_SOLID_BREP).

## Note

- La prima volta il "salva con nome" del pezzo della S4 (con lo studio di simulazione appena calcolato) si e' bloccato oltre 300 s: l'istanza dedicata e' stata chiusa e rilanciata dal server (`SW_MCP_AUTORESTART`). La riga 1 qui sotto mostra l'errore; il modello ha riaperto il pezzo e rifatto il salvataggio. In 4 prove successive non si e' ripetuto.
