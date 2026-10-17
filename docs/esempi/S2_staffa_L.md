# S2 - Staffa a L con asole, raccordo e smussi

## Richiesta

> Staffa a L 80x60x40 sp. 6 con due asole, raccordo R10, smusso 1x45 sugli spigoli esterni.
>
> Interpretazione dichiarata dal modello: base 80, altezza 60, larghezza 40, spessore 6; raccordo R10 sullo spigolo interno della piega; due asole 25 mm (interasse) x 7 nella base; smussi sui 5 spigoli esterni lunghi.

## Sequenza dei tool

1. `create_new_part` `{}`  
   -> [SUCCESS] Created part: Parte2
2. `create_sketch` `{"plane":"Front"}`  
   -> [SUCCESS] Sketch created on Front Plane
3. `draw_line` `{"x1":0,"y1":0,"x2":80,"y2":0}`  
   -> [SUCCESS] Line: 80.00mm
4. `draw_line` `{"x1":80,"y1":0,"x2":80,"y2":6}`  
   -> [SUCCESS] Line: 6.00mm
5. `draw_line` `{"x1":80,"y1":6,"x2":6,"y2":6}`  
   -> [SUCCESS] Line: 74.00mm
6. `draw_line` `{"x1":6,"y1":6,"x2":6,"y2":60}`  
   -> [SUCCESS] Line: 54.00mm
7. `draw_line` `{"x1":6,"y1":60,"x2":0,"y2":60}`  
   -> [SUCCESS] Line: 6.00mm
8. `draw_line` `{"x1":0,"y1":60,"x2":0,"y2":0}`  
   -> [SUCCESS] Line: 60.00mm
9. `extrude_boss` `{"depth":40}`  
   -> [SUCCESS] Estrusione: Estrusione-Estrusione1 (volume 32160.0 mm3, delta +32160.0)
10. `get_bounding_box` `{}`  
   -> [SUCCESS] Box 40.0 x 80.0 x 60.0 mm
11. `fillet_edges` `{"radius":10,"edge_points":[[20,6,6]]}`  
   -> [SUCCESS] Raccordo: Raccordo1 (volume 33018.4 mm3, delta +858.4)
12. `create_sketch_on_face` `{"x":20,"y":50,"z":6}`  
   -> [SUCCESS] Sketch created on face at (20, 50, 6) mm
13. `draw_slot` `{"x1":-35,"y1":12,"x2":-60,"y2":12,"width":7}`  
   -> [SUCCESS] Asola creata
14. `draw_slot` `{"x1":-35,"y1":28,"x2":-60,"y2":28,"width":7}`  
   -> [SUCCESS] Asola creata
15. `extrude_cut` `{"end_condition":"through_all"}`  
   -> [SUCCESS] Taglio estruso: Taglio-Estrusione1 (volume 30456.6 mm3, delta -2561.8)
16. `chamfer_edges` `{"distance":1,"angle":45,"edge_points":[[20,80,6],[20,80,0],[20,0,60],[20,6,60],[20,0,0]]}`  
   -> [SUCCESS] Smusso: Smusso1 (volume 30356.6 mm3, delta -100.0)
17. `list_features` `{}`  
   -> [SUCCESS] 23 features found
18. `save_document` `{"filepath":"<progetto>/test_output/s2_staffa.SLDPRT","overwrite":true}`  
   -> [SUCCESS] Saved: <progetto>\test_output\s2_staffa.SLDPRT [SaveAs]
19. `close_document` `{"discard":true}`  
   -> [SUCCESS] Closed: s2_staffa.SLDPRT

## Controllo

- Volume atteso: 32160 + 858,4 (raccordo: (100 - 25 pi) x 40) - 2561,8 (asole: (25x7 + pi x 3,5^2) x 6 x 2) - 100 (smussi: 0,5 x 40 x 5) = 30356,6 mm3; misurato 30356,593 mm3.

## Note

Nessun errore del modello in questo scenario.
