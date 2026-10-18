# SolidWorks MCP

Server [MCP](https://modelcontextprotocol.io/) che permette a Claude (Claude Code, Claude Desktop) di usare **SolidWorks**:
modellare pezzi, montare assiemi, fare messe in tavola ISO, esportare e lanciare simulazioni, descrivendo il lavoro a parole.

Il progetto e' partito da [alisamsam/solidworks-mcp](https://github.com/alisamsam/solidworks-mcp) (22 tool di base) ed e' stato
riscritto ed esteso fino a **202 tool** (versione 6.0.0), ognuno verificato su SolidWorks con test che misurano il risultato
(volumi, masse, quote, posizioni, reazioni) e lo confrontano con il valore calcolato a mano.

## Cosa sa fare

| Area | Tool | Esempi |
|---|---|---|
| Base | 25 | connessione, nuovo/apri/salva/chiudi, schizzi semplici, estrusione, taglio, raccordi, smussi |
| Modellazione | 50 | quote e relazioni di schizzo, rivoluzione, sweep, loft, shell, nervature, sformi, ripetizioni, Hole Wizard (ISO, ANSI, DIN, BSI, JIS), piani e sistemi di coordinate |
| Disegni | 38 | tavole ISO in primo diedro, viste standard/proiettate/sezioni/dettagli/ausiliarie/interrotte, quote automatiche pulite, tolleranze, GD&T, rugosita', tabella fori, distinta, palloncini, export PDF/DXF/DWG |
| Assiemi | 35 | inserimento e accoppiamenti (anche avanzati e limiti), ripetizioni, specchiatura con pezzo speculare, viste esplose, interferenze, gradi di liberta' misurati |
| Dati ed export | 31 | materiali (anche librerie personali), massa e inerzie (anche in un sistema di coordinate), proprieta' personalizzate, equazioni, configurazioni (anche da tabella CSV/JSON), export STL/3MF/STEP/IGES/Parasolid/PDF 3D/eDrawings con verifica del file, import, immagini ad alta risoluzione, misure |
| Simulazione | 23 | studi statici, di frequenze proprie, di buckling e termici stazionari; vincoli, forze, coppie, pressioni, gravita', temperature, carichi remoti e da cuscinetto; contatto globale e locale, mesh con controlli locali; risultati (anche posizione del fattore di sicurezza minimo e momenti di reazione) e mappe a colori |

Esempi di richieste:
- *"Crea una flangia Ø120 spessore 15 con 6 fori M8 su un diametro di 90 e fanne la messa in tavola A3"*
- *"Monta il perno nella boccola e dimmi quanti gradi di liberta' restano"*
- *"Assegna AISI 304 e dimmi massa e baricentro"*
- *"Incastra la faccia sinistra, metti 100 N sulla destra e dammi la freccia massima"*

## Esempi
Sette prove d'uso reali (richiesta, sequenza dei tool con esiti, numeri misurati) sono in [`docs/esempi/`](docs/esempi/README.md):

| Scenario | Cosa verifica |
|---|---|
| S1 flangia con fori, tavola A3, PDF | volume 153317,58 mm3 e massa 1,22654 kg (AISI 304) come da calcolo |
| S2 staffa a L | volume 30356,593 mm3 contro 30356,6 atteso (raccordo, asole, smussi) |
| S3 assieme perno-boccola | 2 gradi di liberta', distinta 3 righe, peso 208,61 g |
| S4 mensola in simulazione | freccia 0,7964 mm contro 0,8000 teorici; 30,05 MPa a meta' trave; FOS 5,83 |
| S5 configurazioni da CSV | volumi 30000 / 40000 / 50000 mm3 e tre STEP |
| S6 SolidWorks in inglese | stessi numeri di S1 e S4 |
| S7 chiusura con modifiche | `close_document` rifiuta senza `save` o `discard` |

## Sicurezza
- I tool che cancellano o sovrascrivono sono marcati come distruttivi (il client chiede conferma).
- Salvataggi ed esportazioni rifiutano di sovrascrivere un file esistente senza `overwrite=true`.
- `close_document` rifiuta di chiudere un documento con modifiche non salvate senza `save=true` o `discard=true`.
- `execute_python` esegue codice Python arbitrario sul PC: usarlo solo se serve.

## Requisiti
- Windows 10/11 con SolidWorks installato e con licenza. Sviluppato e testato su **SolidWorks 2026 SP4.1** con interfaccia
  **italiana**. Il server funziona anche con SolidWorks in **inglese**: piani standard e origine si trovano per posizione nell'albero,
  template e librerie si prendono dalla lingua attuale di SolidWorks, le scritte sulle tavole seguono la lingua (italiano o inglese).
  Tutti i test sono stati ripetuti anche con SolidWorks in inglese; altre versioni di SolidWorks non sono state provate.
- Python 3.10+ **x64** (anche su Windows ARM64: Python x64 emulato).
- Per la simulazione: l'add-in SOLIDWORKS Simulation.

## Installazione

```bash
git clone https://github.com/elo-savage/solidworks-mcp.git
cd solidworks-mcp
python -m venv .venv
.venv\Scripts\pip install -e .
```
Il venv deve essere di un Python **x64** (`python -c "import sysconfig; print(sysconfig.get_platform())"` deve dire `win-amd64`; `platform.machine()` non basta: su ARM64 dice `ARM64` anche per il Python x64 emulato; su un PC
ARM64 installare il Python x64 da python.org). `pip install -e .` installa le dipendenze e il comando
`.venv\Scripts\solidworks-mcp.exe`; in alternativa `pip install -r requirements.txt` e si avvia `solidworks_mcp_server.py`.
L'installazione "modificabile" (`-e`) serve perche' il server scrive i formati dei fogli verticali nella cartella `formats/` del progetto.

**Claude Code:**
```bash
claude mcp add solidworks -- C:\percorso\solidworks-mcp\.venv\Scripts\solidworks-mcp.exe
```

**Claude Desktop** (`%APPDATA%\Claude\claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "solidworks": {
      "command": "C:\\percorso\\solidworks-mcp\\.venv\\Scripts\\solidworks-mcp.exe"
    }
  }
}
```
Per lavorare con un'istanza di SolidWorks nascosta e separata da quella aperta a mano, aggiungere `"env": {"SW_MCP_INSTANCE": "dedicated"}`
(vedi Configurazione).

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
.venv\Scripts\python.exe tests\run_all.py            # regressione completa (circa 1 h 40), riepilogo in test_output\regressione_*.md
```
I test live costruiscono i pezzi solo tramite i tool MCP e confrontano i numeri con i valori attesi; esiti in `STATO.md`.
Il test offline gira anche su GitHub a ogni push (`.github/workflows/test-offline.yml`).

## Documentazione
- `STATO.md`: stato attuale ed esiti dei test. `STATO_STORICO.md`: diario completo e trappole dell'API di SolidWorks.
- `LIMITI.md`: limiti noti e avanzamento. `PIANO_D_E.md`: piano di lavoro a fasi. `CHANGELOG.md`: cosa e' cambiato per versione.
- `ATLANTE.md`: a cosa serve ogni file.

## Licenza
MIT, vedi [LICENSE](LICENSE). Il progetto originale e' di Samsaam Ali Baig ([alisamsam/solidworks-mcp](https://github.com/alisamsam/solidworks-mcp)).
