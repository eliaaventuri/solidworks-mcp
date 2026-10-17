# S1 - Flangia con fori, messa in tavola e PDF

## Richiesta

> Flangia Ø120 x 15 con 6 fori M8 su Ø90, foro centrale Ø30, in AISI 304; messa in tavola A3 quotata; PDF.

## Sequenza dei tool

1. `connect_solidworks` `{}`  
   -> [SUCCESS] Connected to dedicated SolidWorks 34.4.1 (PID 5764)
2. `create_new_part` `{}`  
   -> [SUCCESS] Created part: Parte1
3. `create_sketch` `{"plane":"Front"}`  
   -> [SUCCESS] Sketch created on Front Plane
4. `draw_circle` `{"x":0,"y":0,"radius":60}`  
   -> [SUCCESS] Circle: r=60mm
5. `draw_circle` `{"x":0,"y":0,"radius":15}`  
   -> [SUCCESS] Circle: r=15mm
6. `extrude_boss` `{"depth":15}`  
   -> [SUCCESS] Estrusione: Estrusione-Estrusione1 (volume 159043.1 mm3, delta +159043.1)
7. `get_bounding_box` `{}`  
   -> [SUCCESS] Box 15.0 x 120.0 x 120.0 mm
8. `create_hole` `{"kind":"simple","size":"M8","face_point":[15,0,30],"positions":[[15,45,0],[15,22.5,38.9711],[15,-22.5,38.9711],[15,-45,0],[15,-22.5,-38.9711],[15,22.5,-38.9711]],"through":true}`  
   -> [SUCCESS] Foro semplice M8: 7 foro/i
9. `delete_feature` `{"name":"Foro per Vite M8-1","confirm":true}`  
   -> [SUCCESS] Feature Foro per Vite M8-1 eliminata
10. `assign_material` `{"material":"AISI 304"}`  
   -> [SUCCESS] Materiale 'AISI 304' assegnato (densita' 8000 kg/m3)
11. `get_mass_properties` `{}`  
   -> [SUCCESS] Volume 153317.58 mm3, massa 1.22654 kg
12. `save_document` `{"filepath":"<progetto>/test_output/s1_flangia.SLDPRT","overwrite":true}`  
   -> [SUCCESS] Saved: <progetto>\test_output\s1_flangia.SLDPRT [SaveAs]
13. `create_drawing` `{"paper_size":"A3","save_as":"<progetto>/test_output/s1_flangia.SLDDRW","overwrite":true}`  
   -> [SUCCESS] Disegno creato: s1_flangia - Foglio1 (A3 landscape, primo diedro)
14. `add_standard_views` `{"views":["front","right","top","isometric"]}`  
   -> [SUCCESS] 4 viste create in scala 1:1
15. `insert_model_dimensions` `{"all_views":true}`  
   -> [SUCCESS] Quote inserite: 1 (poi riordinate: 4 quote finali)
16. `save_drawing` `{"overwrite":true}`  
   -> Input validation error: 'filepath' is a required property
17. `export_drawing` `{"filepath":"<progetto>/test_output/s1_flangia.pdf","overwrite":true}`  
   -> [SUCCESS] Esportato: <progetto>\test_output\s1_flangia.pdf
18. `export_drawing` `{"filepath":"<progetto>/test_output/s1_flangia.png","overwrite":true}`  
   -> [SUCCESS] Esportato: <progetto>\test_output\s1_flangia.png
19. `save_drawing` `{"filepath":"<progetto>/test_output/s1_flangia.SLDDRW","overwrite":true}`  
   -> [SUCCESS] Disegno salvato: <progetto>\test_output\s1_flangia.SLDDRW
20. `add_note` `{"text":"6 FORI Ø9 PASSANTI EQUIDISTANTI SU Ø90","x":95,"y":105}`  
   -> [SUCCESS] Nota creata: 6 FORI Ø9 PASSANTI EQUIDISTANTI SU Ø90
21. `save_drawing` `{"filepath":"<progetto>/test_output/s1_flangia.SLDDRW","overwrite":true}`  
   -> [SUCCESS] Disegno salvato: <progetto>\test_output\s1_flangia.SLDDRW
22. `export_drawing` `{"filepath":"<progetto>/test_output/s1_flangia.pdf","overwrite":true}`  
   -> [SUCCESS] Esportato: <progetto>\test_output\s1_flangia.pdf
23. `export_drawing` `{"filepath":"<progetto>/test_output/s1_flangia.png","overwrite":true}`  
   -> [SUCCESS] Esportato: <progetto>\test_output\s1_flangia.png
24. `inspect_export_file` `{"filepath":"<progetto>/test_output/s1_flangia.pdf"}`  
   -> [SUCCESS] PDF: has_3d=False
25. `close_document` `{"discard":true}`  
   -> [SUCCESS] Closed: s1_flangia - Foglio1
26. `close_document` `{"discard":true}`  
   -> [SUCCESS] Closed: s1_flangia.SLDPRT

## Controllo

- Volume atteso: pi x 15 x (60^2 - 15^2) - 6 x pi x 4,5^2 x 15 = 153317,58 mm3; misurato 153317,58 mm3.
- Massa: 1,22654 kg (densita' 8000 kg/m3).
- PDF di 1 pagina (`inspect_export_file`).
- Tavola `test_output/s1_flangia.png` guardata a occhio: viste frontale, laterale, dall'alto e isometrica; quote Ø120, Ø30, 6x Ø9, 15; nota del cerchio dei fori.

## Note

1. Il modello ha passato `face_point` insieme a `positions` e `create_hole` ha fatto 7 fori (anche nel punto della faccia): l'eccesso e' stato tolto con `delete_feature`. La descrizione del tool e' stata corretta dopo la prova (ogni punto e' un centro foro).
2. `save_drawing` senza `filepath` e' rifiutato dallo schema; il modello ha ripetuto la chiamata con il percorso.
3. La quota del cerchio dei fori Ø90 non viene messa da `insert_model_dimensions`: e' stata aggiunta come nota con `add_note`.
