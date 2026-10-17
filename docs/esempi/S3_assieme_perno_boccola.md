# S3 - Assieme perno-boccola-staffa con esploso, distinta e palloncini

## Richiesta

> Assieme perno-boccola-staffa con accoppiamenti, vista esplosa, distinta e palloncini.

## Sequenza dei tool

1. `create_new_part` `{}`  
   -> [SUCCESS] Created part: Parte3
2. `create_sketch` `{"plane":"Front"}`  
   -> [SUCCESS] Sketch created on Front Plane
3. `draw_rectangle` `{"x1":-30,"y1":-20,"x2":30,"y2":20}`  
   -> [SUCCESS] Rectangle: 60x40mm
4. `draw_circle` `{"x":0,"y":0,"radius":10}`  
   -> [SUCCESS] Circle: r=10mm
5. `extrude_boss` `{"depth":10}`  
   -> [SUCCESS] Estrusione: Estrusione-Estrusione1 (volume 20858.4 mm3, delta +20858.4)
6. `assign_material` `{"material":"AISI 1020"}`  
   -> [SUCCESS] Materiale 'AISI 1020' assegnato (densita' 7900 kg/m3)
7. `save_document` `{"filepath":"<progetto>/test_output/s3_staffa.SLDPRT","overwrite":true}`  
   -> [SUCCESS] Saved: <progetto>\test_output\s3_staffa.SLDPRT [SaveAs]
8. `close_document` `{"discard":true}`  
   -> [SUCCESS] Closed: s3_staffa.SLDPRT
9. `create_new_part` `{}`  
   -> [SUCCESS] Created part: Parte4
10. `create_sketch` `{"plane":"Front"}`  
   -> [SUCCESS] Sketch created on Front Plane
11. `draw_circle` `{"x":0,"y":0,"radius":10}`  
   -> [SUCCESS] Circle: r=10mm
12. `draw_circle` `{"x":0,"y":0,"radius":6}`  
   -> [SUCCESS] Circle: r=6mm
13. `extrude_boss` `{"depth":10}`  
   -> [SUCCESS] Estrusione: Estrusione-Estrusione1 (volume 2010.6 mm3, delta +2010.6)
14. `assign_material` `{"material":"Bronzo"}`  
   -> [ERROR] Nome ambiguo 'Bronzo': ['Alluminio Bronzo', 'Bronzo commerciale, UNS C22000 (Bronzo 90-10)', 'Bronzo al piombo', 'Bronzo al manganese', 'Bronzo al fosforo 10% D, UNS C52400', 'Bronzo per cuscinetti']
15. `save_document` `{"filepath":"<progetto>/test_output/s3_boccola.SLDPRT","overwrite":true}`  
   -> [SUCCESS] Saved: <progetto>\test_output\s3_boccola.SLDPRT [SaveAs]
16. `close_document` `{"discard":true}`  
   -> [SUCCESS] Closed: s3_boccola.SLDPRT
17. `create_new_part` `{}`  
   -> [SUCCESS] Created part: Parte5
18. `create_sketch` `{"plane":"Front"}`  
   -> [SUCCESS] Sketch created on Front Plane
19. `draw_circle` `{"x":0,"y":0,"radius":6}`  
   -> [SUCCESS] Circle: r=6mm
20. `extrude_boss` `{"depth":30}`  
   -> [SUCCESS] Estrusione: Estrusione-Estrusione1 (volume 3392.9 mm3, delta +3392.9)
21. `assign_material` `{"material":"AISI 304"}`  
   -> [SUCCESS] Materiale 'AISI 304' assegnato (densita' 8000 kg/m3)
22. `save_document` `{"filepath":"<progetto>/test_output/s3_perno.SLDPRT","overwrite":true}`  
   -> [SUCCESS] Saved: <progetto>\test_output\s3_perno.SLDPRT [SaveAs]
23. `close_document` `{"discard":true}`  
   -> [SUCCESS] Closed: s3_perno.SLDPRT
24. `open_document` `{"file_path":"<progetto>/test_output/s3_boccola.SLDPRT"}`  
   -> Input validation error: 'filepath' is a required property
25. `assign_material` `{"material":"Bronzo"}`  
   -> [ERROR] No document open. Use create_new_part first.
26. `open_document` `{"filepath":"<progetto>/test_output/s3_boccola.SLDPRT"}`  
   -> [SUCCESS] Opened: s3_boccola.SLDPRT
27. `assign_material` `{"material":"Bronzo"}`  
   -> [ERROR] Nome ambiguo 'Bronzo': ['Alluminio Bronzo', 'Bronzo commerciale, UNS C22000 (Bronzo 90-10)', 'Bronzo al piombo', 'Bronzo al manganese', 'Bronzo al fosforo 10% D, UNS C52400', 'Bronzo per cuscinetti']
28. `assign_material` `{"material":"Bronzo per cuscinetti"}`  
   -> [SUCCESS] Materiale 'Bronzo per cuscinetti' assegnato (densita' 8300 kg/m3)
29. `save_document` `{"filepath":"<progetto>/test_output/s3_boccola.SLDPRT","overwrite":true}`  
   -> [SUCCESS] Saved: <progetto>\test_output\s3_boccola.SLDPRT [SaveAs]
30. `close_document` `{"discard":true}`  
   -> [SUCCESS] Closed: s3_boccola.SLDPRT
31. `create_new_assembly` `{}`  
   -> [SUCCESS] Created assembly: Assieme1
32. `insert_component` `{"file_path":"<progetto>/test_output/s3_staffa.SLDPRT","x":0,"y":0,"z":0,"fixed":true}`  
   -> [SUCCESS] Componente inserito: s3_staffa-1
33. `insert_component` `{"file_path":"<progetto>/test_output/s3_boccola.SLDPRT","x":-30,"y":0,"z":0}`  
   -> [SUCCESS] Componente inserito: s3_boccola-1
34. `insert_component` `{"file_path":"<progetto>/test_output/s3_perno.SLDPRT","x":-80,"y":0,"z":0}`  
   -> [SUCCESS] Componente inserito: s3_perno-1
35. `add_mate` `{"mate_type":"concentric","entity1":{"face":[-25,10,0]},"entity2":{"face":[5,10,0]}}`  
   -> [SUCCESS] Accoppiamento Concentrico1 creato
36. `add_mate` `{"mate_type":"coincident","entity1":{"face":[-30,0,8]},"entity2":{"face":[0,25,0]}}`  
   -> [SUCCESS] Accoppiamento Coincidente1 creato
37. `list_components` `{}`  
   -> [SUCCESS] 3 componenti
38. `list_components` `{}`  
   -> [SUCCESS] 3 componenti
39. `list_components` `{}`  
   -> [SUCCESS] 3 componenti
40. `add_mate` `{"mate_type":"concentric","entity1":{"face":[-65,6,0]},"entity2":{"face":[5,6,0]}}`  
   -> [SUCCESS] Accoppiamento Concentrico2 creato
41. `add_mate` `{"mate_type":"coincident","entity1":{"face":[-80,0,3]},"entity2":{"face":[0,0,8]}}`  
   -> [SUCCESS] Accoppiamento Coincidente2 creato
42. `get_assembly_status` `{}`  
   -> [SUCCESS] Assieme NON completamente vincolato: 2 sottovincolati, 0 sovravincolati, 0 accoppiamenti in errore
43. `list_components` `{}`  
   -> [SUCCESS] 3 componenti
44. `rebuild_model` `{"force":true}`  
   -> [ERROR] Il documento attivo non e' un pezzo (.SLDPRT).
45. `get_assembly_status` `{"measure_dof":false}`  
   -> [SUCCESS] Assieme NON completamente vincolato: 2 sottovincolati, 0 sovravincolati, 0 accoppiamenti in errore
46. `save_document` `{"filepath":"<progetto>/test_output/s3_assieme.SLDASM","overwrite":true}`  
   -> [SUCCESS] Saved: <progetto>\test_output\s3_assieme.SLDASM [SaveAs]
47. `auto_explode` `{"mode":"mates"}`  
   -> [SUCCESS] Esplosione per accoppiamenti: 2 gruppi, 0 sovrapposizioni dei box
48. `save_document` `{"filepath":"<progetto>/test_output/s3_assieme.SLDASM","overwrite":true}`  
   -> [SUCCESS] Saved: <progetto>\test_output\s3_assieme.SLDASM [SaveAs]
49. `create_drawing` `{"paper_size":"A3","save_as":"<progetto>/test_output/s3_assieme.SLDDRW","overwrite":true}`  
   -> [SUCCESS] Disegno creato: s3_assieme - Foglio1 (A3 landscape, primo diedro)
50. `add_standard_views` `{"views":["front","top","isometric"],"exploded":true}`  
   -> [SUCCESS] 3 viste create in scala 1:1
51. `list_drawing_views` `{}`  
   -> [SUCCESS] 3 viste nel foglio Foglio1
52. `add_bom` `{"view":"Vista del disegno3"}`  
   -> [SUCCESS] Distinta creata (4 righe)
53. `add_balloons` `{"view":"Vista del disegno3"}`  
   -> [SUCCESS] 3 palloncini creati
54. `list_bom` `{}`  
   -> [SUCCESS] Distinta: 3 righe
55. `save_drawing` `{"filepath":"<progetto>/test_output/s3_assieme.SLDDRW","overwrite":true}`  
   -> [SUCCESS] Disegno salvato: <progetto>\test_output\s3_assieme.SLDDRW
56. `export_drawing` `{"filepath":"<progetto>/test_output/s3_assieme.png","overwrite":true}`  
   -> [SUCCESS] Esportato: <progetto>\test_output\s3_assieme.png
57. `close_document` `{"discard":true}`  
   -> [SUCCESS] Closed: s3_assieme - Foglio1
58. `close_document` `{"discard":true}`  
   -> [SUCCESS] Closed: s3_assieme.SLDASM

## Controllo

- Gradi di liberta': 2, cioe' la rotazione della boccola e quella del perno attorno all'asse (misurati da `get_assembly_status`).
- Distinta: 3 righe. Palloncini: 3.
- Peso in cartiglio 208,61 g = 164,8 + 16,7 + 27,1 g (staffa + boccola + perno).
- Tavola `test_output/s3_assieme.png`.

## Note

1. "Bronzo" e' ambiguo: il tool elenca 6 bronzi e rifiuta; il modello ha scelto "Bronzo per cuscinetti".
2. `open_document` vuole `filepath` (mentre `insert_component` usa `file_path`): il modello ha sbagliato il nome una volta e ha corretto da solo.
3. Nello stato dei vincoli il perno risulta "nessuna soluzione" pur senza accoppiamenti in errore: da indagare.
