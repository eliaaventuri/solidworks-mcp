# S7 - "Chiudi tutto" con un documento modificato

## Richiesta

> Chiudi tutto.
>
> Contesto: il pezzo `s5_trave` e' aperto e modificato (`set_dimension_value`, D1 da 200 a 180) e non salvato.

## Sequenza dei tool

1. `set_dimension_value` `{"name":"D1@Estrusione-Estrusione1","value":180}`  
   -> [SUCCESS] D1@Estrusione-Estrusione1: 200.0 -> 180.0; volume 40000.0 -> 36000.0 mm3
2. `list_open_documents` `{}`  
   -> [SUCCESS] 1 document(s) open
3. `close_document` `{}`  
   -> [ERROR] Rifiutato: 's5_trave.SLDPRT' ha modifiche non salvate. Chiuderlo ora farebbe PERDERE il lavoro. Usa save=true (salva e chiudi) oppure discard=true (chiudi scartando).
4. `close_document` `{"discard":true}`  
   -> [SUCCESS] Closed: s5_trave.SLDPRT (modifiche NON salvate SCARTATE: modifiche non salvate)

## Controllo

- `close_document` senza opzioni rifiuta di chiudere e spiega le due vie (`save=true` oppure `discard=true`): nessun dato perso.
- Con `discard=true` il documento si chiude scartando le modifiche.
