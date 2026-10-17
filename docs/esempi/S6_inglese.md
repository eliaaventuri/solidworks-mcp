# S6 - S1 e S4 con SolidWorks in inglese

## Richiesta

> Le richieste di S1 (flangia con messa in tavola) e S4 (trave a mensola con simulazione), rifatte con SolidWorks in inglese.

## Sequenza dei tool

1. `connect_solidworks` `{}`  
   -> [SUCCESS] Connected to dedicated SolidWorks 34.4.1 (PID 4316)
2. `create_new_part` `{}`  
   -> [SUCCESS] Created part: Part1
3. `create_sketch` `{"plane":"Front"}`  
   -> [SUCCESS] Sketch created on Front Plane
4. `draw_circle` `{"x":0,"y":0,"radius":60}`  
   -> [SUCCESS] Circle: r=60mm
5. `draw_circle` `{"x":0,"y":0,"radius":15}`  
   -> [SUCCESS] Circle: r=15mm
6. `extrude_boss` `{"depth":15}`  
   -> [SUCCESS] Estrusione: Boss-Extrude1 (volume 159043.1 mm3, delta +159043.1)
7. `create_hole` `{"kind":"simple","size":"M8","positions":[[15,45,0],[15,22.5,38.9711],[15,-22.5,38.9711],[15,-45,0],[15,-22.5,-38.9711],[15,22.5,-38.9711]],"through":true}`  
   -> [SUCCESS] Foro semplice M8: 6 foro/i
8. `assign_material` `{"material":"AISI 304"}`  
   -> [SUCCESS] Materiale 'AISI 304' assegnato (densita' 8000 kg/m3)
9. `get_mass_properties` `{}`  
   -> [SUCCESS] Volume 153317.58 mm3, massa 1.22654 kg
10. `save_document` `{"filepath":"<progetto>/test_output/s6_flangia.SLDPRT","overwrite":true}`  
   -> [SUCCESS] Saved: <progetto>\test_output\s6_flangia.SLDPRT [SaveAs]
11. `create_drawing` `{"paper_size":"A3","save_as":"<progetto>/test_output/s6_flangia.SLDDRW","overwrite":true}`  
   -> [SUCCESS] Disegno creato: s6_flangia - Foglio1 (A3 landscape, primo diedro)
12. `add_standard_views` `{"views":["front","right","top","isometric"]}`  
   -> [SUCCESS] 4 viste create in scala 1:1
13. `insert_model_dimensions` `{"all_views":true}`  
   -> [SUCCESS] Quote inserite: 1 (poi riordinate: 4 quote finali)
14. `add_note` `{"text":"6 HOLES Ø9 THROUGH EQUALLY SPACED ON Ø90","x":95,"y":105}`  
   -> [SUCCESS] Nota creata: 6 HOLES Ø9 THROUGH EQUALLY SPACED ON Ø90
15. `save_drawing` `{"filepath":"<progetto>/test_output/s6_flangia.SLDDRW","overwrite":true}`  
   -> [SUCCESS] Disegno salvato: <progetto>\test_output\s6_flangia.SLDDRW
16. `export_drawing` `{"filepath":"<progetto>/test_output/s6_flangia.pdf","overwrite":true}`  
   -> [SUCCESS] Esportato: <progetto>\test_output\s6_flangia.pdf
17. `export_drawing` `{"filepath":"<progetto>/test_output/s6_flangia.png","overwrite":true}`  
   -> [SUCCESS] Esportato: <progetto>\test_output\s6_flangia.png
18. `close_document` `{"discard":true}`  
   -> [SUCCESS] Closed: s6_flangia - Foglio1
19. `close_document` `{"discard":true}`  
   -> [SUCCESS] Closed: s6_flangia.SLDPRT
20. `create_new_part` `{}`  
   -> [SUCCESS] Created part: Part2
21. `create_sketch` `{"plane":"Front"}`  
   -> [SUCCESS] Sketch created on Front Plane
22. `draw_rectangle` `{"x1":-10,"y1":-5,"x2":10,"y2":5}`  
   -> [SUCCESS] Rectangle: 20x10mm
23. `extrude_boss` `{"depth":200}`  
   -> [SUCCESS] Estrusione: Boss-Extrude1 (volume 40000.0 mm3, delta +40000.0)
24. `assign_material` `{"material":"AISI 1020"}`  
   -> [SUCCESS] Materiale 'AISI 1020' assegnato (densita' 7900 kg/m3)
25. `save_document` `{"filepath":"<progetto>/test_output/s6_trave.SLDPRT","overwrite":true}`  
   -> [SUCCESS] Saved: <progetto>\test_output\s6_trave.SLDPRT [SaveAs]
26. `create_static_study` `{"name":"Cantilever"}`  
   -> [SUCCESS] Studio statico 'Cantilever' creato
27. `add_restraint` `{"kind":"fixed","faces":[[0,0,0]]}`  
   -> [SUCCESS] Vincolo 'fixed' su 1 facce: Fixed-1
28. `add_force` `{"faces":[[200,0,0]],"value":100,"direction":[0,0,-1]}`  
   -> [SUCCESS] Forza 100 N lungo [0.0, 0.0, -1.0]: Force-1
29. `create_simulation_mesh` `{"element_size":2.5}`  
   -> [SUCCESS] Mesh standard: 28150 nodi, 18039 elementi, AR max 3.564 (0.7 s)
30. `run_simulation` `{}`  
   -> [SUCCESS] Analisi completata in 2.8 s
31. `get_simulation_results` `{}`  
   -> [SUCCESS] VM max 60.345 MPa, spostamento max 0.79697 mm, FOS min 5.826005458831787
32. `get_simulation_stress_on_faces` `{"faces":[[100,0,5]],"box":[95,-10,5,105,10,5]}`  
   -> [SUCCESS] 127 nodi: 28.510..31.508 MPa
33. `export_simulation_plot` `{"filepath":"<progetto>/test_output/s6_trave_vonmises.png","overwrite":true}`  
   -> [SUCCESS] Grafico 'Stress1' esportato: <progetto>\test_output\s6_trave_vonmises.png (741421 byte)
34. `close_document` `{"save":true}`  
   -> [SUCCESS] Closed: s6_trave.SLDPRT (salvato prima di chiudere)

## Controllo

- Stessi numeri delle prove in italiano: volume 153317,58 mm3, massa 1,22654 kg; freccia 0,79697 mm (massimo), 30,05 MPa a meta' trave, 60,35 MPa all'incastro.
- Cartiglio in inglese; feature con nomi inglesi (Boss-Extrude1, HoleWzd1); grafico `Stress1`.
