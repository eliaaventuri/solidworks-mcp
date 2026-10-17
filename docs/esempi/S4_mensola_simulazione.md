# S4 - Trave a mensola: simulazione statica

## Richiesta

> Trave 200x20x10 incastrata, 100 N in punta: freccia e tensione massima, fattore di sicurezza, mappa PNG.

## Sequenza dei tool

1. `create_new_part` `{}`  
   -> [SUCCESS] Created part: Parte6
2. `create_sketch` `{"plane":"Front"}`  
   -> [SUCCESS] Sketch created on Front Plane
3. `draw_rectangle` `{"x1":-10,"y1":-5,"x2":10,"y2":5}`  
   -> [SUCCESS] Rectangle: 20x10mm
4. `extrude_boss` `{"depth":200}`  
   -> [SUCCESS] Estrusione: Estrusione-Estrusione1 (volume 40000.0 mm3, delta +40000.0)
5. `assign_material` `{"material":"AISI 1020"}`  
   -> [SUCCESS] Materiale 'AISI 1020' assegnato (densita' 7900 kg/m3)
6. `save_document` `{"filepath":"<progetto>/test_output/s4_trave.SLDPRT","overwrite":true}`  
   -> [SUCCESS] Saved: <progetto>\test_output\s4_trave.SLDPRT [SaveAs]
7. `get_bounding_box` `{}`  
   -> [SUCCESS] Box 200.0 x 20.0 x 10.0 mm
8. `create_static_study` `{"name":"Mensola"}`  
   -> [SUCCESS] Studio statico 'Mensola' creato
9. `add_restraint` `{"kind":"fixed","faces":[[0,0,0]]}`  
   -> [SUCCESS] Vincolo 'fixed' su 1 facce: Fisso-1
10. `add_force` `{"faces":[[200,0,0]],"value":100,"direction":[0,0,-1]}`  
   -> [SUCCESS] Forza 100 N lungo [0.0, 0.0, -1.0]: Forza-1
11. `create_simulation_mesh` `{"element_size":2.5}`  
   -> [SUCCESS] Mesh standard: 28150 nodi, 18039 elementi, AR max 3.564 (0.7 s)
12. `run_simulation` `{}`  
   -> [SUCCESS] Analisi completata in 2.9 s
13. `get_simulation_results` `{}`  
   -> [SUCCESS] VM max 60.345 MPa, spostamento max 0.79697 mm, FOS min 5.826005458831787
14. `get_simulation_stress_on_faces` `{"faces":[[100,0,5]],"box":[95,-10,5,105,10,5]}`  
   -> [SUCCESS] 127 nodi: 28.510..31.508 MPa
15. `export_simulation_plot` `{"filepath":"<progetto>/test_output/s4_trave_vonmises.png","overwrite":true}`  
   -> [SUCCESS] Grafico 'Sollecitazione1' esportato: <progetto>\test_output\s4_trave_vonmises.png (743204 byte)
16. `list_model_features` `{"include_dimensions":true}`  
   -> [SUCCESS] 5 feature

## Controllo

- Freccia (uz) 0,7964 mm contro F L^3 / (3 E I) = 0,8000 mm (scarto 0,45 %).
- Tensione a meta' trave sulla faccia superiore 30,05 MPa contro 30,0 MPa attesi.
- Massimo nodale all'incastro 60,35 MPa contro 60 MPa (singolarita' del vincolo).
- Fattore di sicurezza 5,83 all'incastro.
- Mappa `test_output/s4_trave_vonmises.png`.
