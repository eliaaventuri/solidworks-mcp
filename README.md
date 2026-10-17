# SolidWorks MCP

Server [MCP](https://modelcontextprotocol.io/) che permette a Claude (Claude Code, Claude Desktop) di usare **SolidWorks**:
modellare pezzi, montare assiemi, fare messe in tavola ISO, esportare e lanciare simulazioni statiche, descrivendo il lavoro a parole.

Il progetto e' partito da [alisamsam/solidworks-mcp](https://github.com/alisamsam/solidworks-mcp) (22 tool di base) ed e' stato
riscritto ed esteso fino a **197 tool**, ognuno verificato su SolidWorks con test che misurano il risultato
(volumi, masse, quote, posizioni, reazioni) e lo confrontano con il valore calcolato a mano.

## Cosa sa fare

| Area | Tool | Esempi |
|---|---|---|
| Base | 25 | connessione, nuovo/apri/salva/chiudi, schizzi semplici, estrusione, taglio, raccordi, smussi |
| Modellazione | 50 | quote e relazioni di schizzo, rivoluzione, sweep, loft, shell, nervature, sformi, ripetizioni, Hole Wizard (ISO, ANSI, DIN, BSI, JIS), piani e sistemi di coordinate |
| Disegni | 38 | tavole ISO in primo diedro, viste standard/proiettate/sezioni/dettagli/ausiliarie/interrotte, quote automatiche pulite, tolleranze, GD&T, rugosita', tabella fori, distinta, palloncini, export PDF/DXF/DWG |
| Assiemi | 35 | inserimento e accoppiamenti (anche avanzati e limiti), ripetizioni, specchiatura con pezzo speculare, viste esplose, interferenze, gradi di liberta' misurati |
| Dati ed export | 30 | materiali, massa e inerzie, proprieta' personalizzate, equazioni, configurazioni, export STL/3MF/STEP/IGES/Parasolid/PDF 3D/eDrawings con verifica del file, import, immagini, misure |
| Simulazione | 18 | studio statico lineare: vincoli, forze, coppie, pressioni, gravita', contatto, mesh, esecuzione, risultati e mappe a colori |

Esempi di richieste:
- *"Crea una flangia Ø120 spessore 15 con 6 fori M8 su un diametro di 90 e fanne la messa in tavola A3"*
- *"Monta il perno nella boccola e dimmi quanti gradi di liberta' restano"*
- *"Assegna AISI 304 e dimmi massa e baricentro"*
- *"Incastra la faccia sinistra, metti 100 N sulla destra e dammi la freccia massima"*

## Sicurezza
- I tool che cancellano o sovrascrivono sono marcati come distruttivi (il client chiede conferma).
- Salvataggi ed esportazioni rifiutano di sovrascrivere un file esistente senza `overwrite=true`.
- `close_document` rifiuta di chiudere un documento con modifiche non salvate senza `save=true` o `discard=true`.
- `execute_python` esegue codice Python arbitrario sul PC: usarlo solo se serve.

## Requisiti
- Windows 10/11 con SolidWorks installato e con licenza. Sviluppato e testato su **SolidWorks 2026 SP4.1** con interfaccia
  **italiana**. Il server funziona anche con SolidWorks in **inglese**: piani standard e origine si trovano per posizione nell'albero,
  template e librerie si prendono dalla lingua attuale di SolidWorks, le scritte sulle tavole seguono la lingua (italiano o inglese).
  La prova completa in inglese non e' ancora stata fatta (vedi `STATO.md`); altre versioni non sono state provate.
- Python 3.10+ **x64** (anche su Windows ARM64: Python x64 emulato).
- Per la simulazione: l'add-in SOLIDWORKS Simulation.

## Installazione

```bash
git clone https://github.com/elo-savage/solidworks-mcp.git
cd solidworks-mcp
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

**Claude Code:**
```bash
claude mcp add solidworks -- C:\percorso\solidworks-mcp\.venv\Scripts\python.exe C:\percorso\solidworks-mcp\solidworks_mcp_server.py
```

**Claude Desktop** (`%APPDATA%\Claude\claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "solidworks": {
      "command": "C:\\percorso\\solidworks-mcp\\.venv\\Scripts\\python.exe",
      "args": ["C:\\percorso\\solidworks-mcp\\solidworks_mcp_server.py"]
    }
  }
}
```

Avviare SolidWorks, riavviare il client e chiedere *"collegati a SolidWorks"*.

## Configurazione
- `solidworks_mcp/config.json`: percorso di `SLDWORKS.exe` (`auto` = ricerca automatica), timeout di avvio, tempo massimo di un tool
  (`tool_timeout`, default 300 s), unita' predefinita, livello e file di log (in `%LOCALAPPDATA%\solidworks-mcp\`, 5 file da 5 MB).
  I template di pezzo/assieme/disegno sono quelli predefiniti di SolidWorks (Opzioni > Modelli predefiniti).
- Variabili d'ambiente:
  - `SW_MCP_INSTANCE=dedicated`: invece di usare il SolidWorks aperto dall'utente, il server avvia una **propria istanza nascosta** e
    alla fine chiude solo quella (e' la modalita' dei test).
  - `SW_MCP_EXE`, `SW_MCP_ARGS` (default `/r`), `SW_MCP_STARTUP_TIMEOUT` (default 240 s): avvio dell'istanza dedicata.
  - `SW_MCP_TOOL_TIMEOUT`: tempo massimo di un tool in secondi (sostituisce `tool_timeout`). Allo scadere il server risponde con un
    errore; con l'istanza dedicata la chiude, con quella dell'utente non la tocca.
  - `SW_MCP_AUTORESTART=1`: se l'istanza dedicata muore o viene chiusa per timeout, il tool seguente la rilancia e avverte che i
    documenti aperti sono persi (senza: errore che chiede di riavviare il server).
  - `SW_MCP_TOOLSETS`: gruppi di tool esposti al client, es. `base,modeling,drawings` (gruppi: `base` sempre attivo, `modeling`,
    `drawings`, `assembly`, `data`, `simulation`; default tutti). Riduce le descrizioni inviate al modello.
  - `SW_MCP_ALLOW_PYTHON=1`: attiva `execute_python` (esegue codice arbitrario; disattivato di default).

## Test
```bash
python tests/test_offline.py                         # senza SolidWorks, anche su Linux: registro dei tool, sicurezza, lettori dei file
.venv\Scripts\python.exe tests\test_modeling_live.py  # con SolidWorks (istanza dedicata): uno script per area, vedi ATLANTE.md
```
I test live costruiscono i pezzi solo tramite i tool MCP e confrontano i numeri con i valori attesi; esiti in `STATO.md`.
Il test offline gira anche su GitHub a ogni push (`.github/workflows/test-offline.yml`).

## Documentazione
- `STATO.md`: stato attuale ed esiti dei test. `STATO_STORICO.md`: diario completo e trappole dell'API di SolidWorks.
- `LIMITI.md`: limiti noti e avanzamento. `PIANO_D_E.md`: prossimi lavori (dati/export e simulazione).
- `ATLANTE.md`: a cosa serve ogni file.

## Licenza
MIT, vedi [LICENSE](LICENSE). Il progetto originale e' di Samsaam Ali Baig ([alisamsam/solidworks-mcp](https://github.com/alisamsam/solidworks-mcp)).
