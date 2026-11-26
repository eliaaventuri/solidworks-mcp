# SolidWorks MCP

**Let Claude drive SOLIDWORKS.** Describe a part, an assembly, a drawing or a simulation in plain words, and the model builds it in SOLIDWORKS for you, then checks the result with real numbers.

[![offline tests](https://github.com/elo-savage/solidworks-mcp/actions/workflows/test-offline.yml/badge.svg)](https://github.com/elo-savage/solidworks-mcp/actions/workflows/test-offline.yml)
![version](https://img.shields.io/badge/version-8.5.0-blue)
![tools](https://img.shields.io/badge/MCP%20tools-445-green)
![SOLIDWORKS](https://img.shields.io/badge/SOLIDWORKS-2026-red)
![Python](https://img.shields.io/badge/python-3.10%2B%20x64-yellow)
[![license](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

> *"Make a Ø120 × 15 mm flange with six M8 holes on a Ø90 circle and a Ø30 bore, in AISI 304. Put it on an A3 drawing with dimensions and export a PDF."*
>
> The server creates the part, checks that the volume is 153 317.58 mm³ and the mass 1.22654 kg (matching the hand calculation), lays out an ISO drawing with dimensions and exports the PDF.

<p align="center">
  <img src="docs/img/assembly_drawing.png" width="49%" alt="Assembly drawing with BOM and balloons, made by the server">
  <img src="docs/img/cantilever_von_mises.jpg" width="49%" alt="Von Mises stress plot of a cantilever beam, made by the server">
</p>
<p align="center"><sub>Left: assembly drawing with BOM and balloons. Right: static study of a cantilever beam. Both were produced only through MCP tool calls.</sub></p>

---

## What is this?

An [MCP](https://modelcontextprotocol.io/) server, written in Python, that connects AI clients such as **Claude Code** and **Claude Desktop** to **SOLIDWORKS** on Windows. It talks to SOLIDWORKS through the official COM API and gives the model **445 tools** (446 with `execute_python` enabled). With them it can sketch, model, assemble, make drawings, export, and run FEA studies.

The live tests build real parts and compare **measured numbers** (volumes, masses, dimensions, positions, reaction forces, stresses) with values calculated by hand. Every one of the 445 tools is exercised by at least one live test. Tools whose SOLIDWORKS API turned out not to work were removed; each one is listed, with the measured reason, in `solidworks_mcp/not_implemented.py`.

85 more tools were tried and **removed**, because SOLIDWORKS does not allow them through its API or because they did not pass a live test: each one keeps its measured reason in `solidworks_mcp/not_implemented.py` (for example half section views, cam/slot/rack-and-pinion mates, snap hooks, STEP AP242 with PMI on the Student edition), and calling it returns that reason. 25 duplicate tools (two names for the same operation, such as `extrude_sketch` and `extrude_boss`) were also removed: the old name returns an error that names the tool to use.

## Features

| Area | What it can do |
|---|---|
| 🧱 **Core & Documents** | Connect to the user's or a dedicated hidden instance; batch tool sequences; try a sequence on a temporary copy; tool search; new/open/save/close; units; basic sketches; primitive extrusions, cuts, fillets and chamfers |
| ✏️ **2D & 3D Sketching** | Lines, centerlines, circles, 3-point/centerpoint/tangent arcs, slots, rectangles, parallelograms, ellipses, parabolas, conics, polygons; splines and equation-driven curves, curvature combs; geometric relations and dimensions; offset, mirror, trim, extend, sketch fillets and chamfers; linear and circular sketch patterns; blocks (make, insert, explode); sketch text; 3D sketches |
| 🏗️ **3D Feature Modeling** | Boss/cut extrusions and revolves (thin feature, two directions, draft, start and end conditions); sweeps with guide curves and twist; lofts (boss and cut) with guides and centerline; boundary features; ribs, domes, wraps, flex; cosmetic and modeled threads; Hole Wizard holes M3–M70; constant, variable and face fillets; distance-angle and vertex chamfers; shells with multiple thickness; multibody combine, split, intersect, move, scale; linear, circular, curve, sketch, table and fill patterns; mirrors; move faces |
| 🌀 **Curves & Surfaces** | Constant and variable-pitch helices, projected and composite curves, curves through points, split lines; planar, extruded, revolved, swept, lofted, ruled, boundary and fill surfaces; thicken |
| 📄 **Drawings** | ISO sheets A4–A0 portrait/landscape, first or third angle; sheet format editing; automatic layout and scale; standard, projected, section (also stepped and aligned), detail, auxiliary, broken, broken-out, crop and relative views; sheet-metal flat pattern views; model dimensions tidied per ISO 129; ordinate and chamfer dimensions, tolerances, GD&T, datums, surface finish; hole tables, BOM, revision and general tables, balloons; drawing audit; PDF (also layered), DXF, DWG, PNG export |
| ⚙️ **Assemblies** | Component insertion (fixed/floating); standard, advanced and limit mates; gear, screw, hinge, linear coupler and universal joint mates; mate redundancy check; component patterns and mirrors; exploded views (linear, entity-aligned, radial) with explode lines; measured degrees of freedom; interference, clearance and collision detection; configurations; sub-assemblies; isolation; SpeedPak; cavity and join |
| 🏭 **Sheet Metal & Weldments** | Base and edge flanges, hems, sketched bends, conversion to sheet metal, flat pattern and 1:1 DXF export; structural members, weldment profiles, trim/extend, end caps, cut lists |
| 🔍 **Selection & Inspection** | Selection by point, by ID and by ray; B-Rep topology queries by geometric criteria; measurements; bounding boxes, center of mass, mate references; draft, thickness and undercut analysis; geometry check; rebuild errors; labeled viewport images |
| 📦 **Data & Export** | Library materials and appearances; mass properties and inertia tensors (origin, center of mass or user coordinate system); custom properties per configuration; equations and global variables; configurations from CSV/JSON tables; STEP (AP203/214), IGES, Parasolid, SAT, STL, 3MF, glTF, IFC, 3D PDF, eDrawings exports, each re-read and verified |
| 🔬 **Simulation (FEA)** | Static, frequency, buckling, steady-state thermal, drop test, fatigue and linear dynamic studies; fixtures, elastic supports, cylindrical restraints; forces, pressure, torque, gravity, remote, bearing and centrifugal loads, temperatures, convection, radiation, heat power; bolt, pin, spring and spot-weld connectors; bonded, no-penetration, shrink-fit and virtual-wall contacts; orthotropic materials, shell and beam formulations; curvature-based meshing with local controls and quality metrics; results with location of the extremes, stresses on chosen faces, reaction forces and moments, plots and HTML reports |

### Things you can ask

- *"Mate the pin into the bushing and tell me how many degrees of freedom are left."*
- *"Assign AISI 304 and give me the mass and the center of gravity."*
- *"Fix the left face, put 100 N on the right face and tell me the maximum deflection."*
- *"Create three configurations, 150, 200 and 250 mm long, and export each one as STEP."*
- *"Make an exploded view of the assembly and put it on a drawing with a BOM."*

### Vision LLMs & Native ImageContent

When capturing screenshots, rendered views, simulation plots, or labeled viewport images (`export_model_image`, `export_simulation_plot`, `export_labeled_viewport_image`, and `export_drawing` to PNG/JPG), the server returns both structured JSON metadata in `TextContent` and the image as native MCP `ImageContent` (base64-encoded).

Multimodal Vision LLMs (e.g. Claude 3.5/3.7 Sonnet) receive the rendered CAD geometry directly in their context window for immediate visual verification and geometric feedback. Image attachment also works seamlessly inside batch workflows (`execute_tool_sequence`).

### MCP Resources & Prompts

The server implements full standard MCP resource and prompt protocols:

- **Resources:**
  - `solidworks://status`: Live connection state, SolidWorks version, PID, mode, UI language, and default unit.
  - `solidworks://documents`: List of open documents, file paths, modified flags, and active document marker.
  - `solidworks://active-document`: Deep inspection of the active document (configurations, assigned material, solid bodies count, sheets).
  - `solidworks://configuration`: Server parameters, timeouts, active toolset groups, and logging paths.
- **Prompts:**
  - `create-part`: Guided workflow for parametric 3D modeling with sketches, features, and mass property verification.
  - `create-drawing`: Guided workflow to generate an ISO drawing sheet with standard views, dimensions, and PDF export.
  - `run-simulation`: Guided workflow for FEA studies (static, frequency, buckling, thermal) with load setup and FOS review.
  - `create-assembly`: Guided workflow for multi-component assemblies, mating kinematics, and exploded views.
  - `export-model`: Guided workflow for CAD model exchange (STEP, STL, 3MF, etc.) with format integrity checks.

## Tested scenarios

Seven real end-to-end runs are documented step by step in [`docs/esempi/`](docs/esempi/README.md): the request, every tool call with its result, and the measured numbers. They were last re-run on a clean install on 2026-10-18. The scenario files are written in Italian; the tool calls and numbers can be read in any language.

| # | Scenario | Measured result |
|---|---|---|
| S1 | Flange with holes, A3 drawing, PDF | Volume 153 317.58 mm³, mass 1.22654 kg, same as the hand calculation |
| S2 | L-bracket with fillet, slots and chamfers | Volume 30 356.6 mm³, as calculated |
| S3 | Pin and bushing assembly | 2 degrees of freedom; BOM with 3 rows; 3 balloons |
| S4 | Cantilever beam, static study | Deflection 0.797 mm (theory 0.800); 30.05 MPa at mid-span (theory 30); FOS 5.83 |
| S5 | Configurations from a CSV table | Volumes 30 000 / 40 000 / 50 000 mm³; three valid STEP files |
| S6 | S1 and S4 with SOLIDWORKS in English | Same numbers as in Italian |
| S7 | Closing a document with unsaved changes | Refused, with an explanation, unless you pass `save` or `discard` |

## Requirements

- **Windows 10/11** with a licensed **SOLIDWORKS** installation. Developed and tested on **SOLIDWORKS 2026 SP4.1**; other versions have not been tested.
- **Python 3.10+, x64 build.** On Windows on ARM, use the x64 Python from python.org: it runs emulated, and the ARM64 build does not work because some dependencies have no ARM64 wheels.
- The **SOLIDWORKS Simulation** add-in, only for the simulation tools.

## Installation

```bash
git clone https://github.com/elo-savage/solidworks-mcp.git
cd solidworks-mcp
python -m venv .venv
.venv\Scripts\pip install -e .
```

This installs the dependencies and the command `.venv\Scripts\solidworks-mcp.exe`. The editable install (`-e`) is needed because the server writes portrait sheet formats into the project's `formats/` folder.

To check that the Python is x64, run `python -c "import sysconfig; print(sysconfig.get_platform())"`: it must print `win-amd64`. Do not rely on `platform.machine()`: on ARM64 PCs it prints `ARM64` even for the emulated x64 Python.

### Connect it to your client

**Claude Code**
```bash
claude mcp add solidworks -- C:\path\to\solidworks-mcp\.venv\Scripts\solidworks-mcp.exe
```

**Claude Desktop**: edit `%APPDATA%\Claude\claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "solidworks": {
      "command": "C:\\path\\to\\solidworks-mcp\\.venv\\Scripts\\solidworks-mcp.exe"
    }
  }
}
```

Start SOLIDWORKS, restart the client and ask *"connect to SolidWorks"*.

> **Tip:** to keep your own SOLIDWORKS window untouched, add `"env": {"SW_MCP_INSTANCE": "dedicated"}`. The server then starts its own hidden SOLIDWORKS instance and closes only that one at the end.

## Configuration

**`solidworks_mcp/config.json`** sets:
- the path of `SLDWORKS.exe` (`auto` finds it automatically);
- the startup timeout and the maximum time per tool (`tool_timeout`, default 300 s);
- the default unit;
- the log level and log file. Logs go to `%LOCALAPPDATA%\solidworks-mcp\`, rotating over 5 files of 5 MB.

Part, assembly and drawing templates are the SOLIDWORKS defaults (*Options › Default Templates*).

**Environment variables**

| Variable | Effect |
|---|---|
| `SW_MCP_INSTANCE=dedicated` | Use a private, hidden SOLIDWORKS instance instead of the one you have open |
| `SW_MCP_AUTORESTART=1` | If the dedicated instance dies or times out, the next tool restarts it and warns that open documents were lost |
| `SW_MCP_TOOL_TIMEOUT` | Maximum seconds per tool (overrides `tool_timeout`). On timeout, the server returns an error; it closes a dedicated instance, but never touches yours |
| `SW_MCP_TOOLSETS` | Expose only some tool groups, e.g. `base,modeling,drawings` (groups: `base` - 35 tools, always on - `modeling` 204, `drawings` 56, `assembly` 65, `data` 41, `simulation` 53). Fewer tools means shorter descriptions sent to the model |
| `SW_MCP_EXE`, `SW_MCP_ARGS`, `SW_MCP_STARTUP_TIMEOUT` | How the dedicated instance is launched (defaults: auto, `/r`, 240 s) |
| `SW_MCP_ALLOW_PYTHON=1` | Enable `execute_python`, which runs arbitrary Python on your PC. Off by default; with it off, the client sees 445 tools |
| `SW_MCP_ATTACH_IMAGES=0` | Disable inline `ImageContent` attachments for image exports (default `1`, enabled) |
| `SW_MCP_COM_CACHE=0` | Disable the light COM wrappers (default on: no type description is fetched for each object SOLIDWORKS returns) |
| `SW_MCP_COM_POOL=0` | Disable the COM object pool (default on: returned objects are released after the answer is sent, not during the tool) |
| `SW_MCP_PREWARM=0` | Do not start the dedicated instance when the server starts (default on: it starts in the background right away) |
| `SW_MCP_LANG=it` | Result messages in Italian (default `en`: the code writes them in Italian and the server translates them on the way out; data fields are never translated) |
| `SW_MCP_FREEZE_UI=1` | Experimental: suspend graphics and FeatureManager tree updates of the active document during each tool |
| `SW_MCP_FAST_COM=0` | Do not set SOLIDWORKS `CommandInProgress` while a tool runs (default on: without it SOLIDWORKS does ~5 ms of idle work after every call from the server; with it a call costs ~0.2 ms; it is always switched off at the end of the tool) |
| `SW_MCP_FAST_VIEW=0` | Keep the view rotation animation during tools (default: animation speed 0 while a tool runs, restored afterwards) |

### Speed

Most of the time of a session is spent in model turns, not in SOLIDWORKS: every tool call is one turn of the model. So:

- **Batch the steps.** `execute_tool_sequence` runs many tools in one call. A step can reuse a value returned by an
  earlier step: the string `"$3.feature"` (step 3, key `feature`) or `"$prev.entity_id"` is replaced by that value.
  `compact=true` keeps the answer short. The server sends these instructions to the client when it connects.
- **Load schemas in bulk.** `search_tools` with `names=[...]` and `detail=true` returns the parameters of several tools in
  one call, so a sequence can be written without loading each tool first.
- **Expose fewer tools** with `SW_MCP_TOOLSETS` when you only need one area (groups follow the real area of each tool).
- The server side was profiled on a typical 18-tool session (block, holes, fillet, chamfer, mass, feature list): from
  18.0 s to 6.7 s. Every call between the server and SOLIDWORKS crosses processes (~3 ms each on the test PC), so the
  server makes fewer of them: light COM wrappers, the feature tree read in one call, member ids asked once per list of
  objects, returned objects released after the answer instead of during the tool, the dedicated instance started early
  and its no-dialog preferences kept between tools (restored when it closes). Each tool's time is written in the server log.
- Since 26/11/2026 the server also sets `CommandInProgress` while a tool runs (SOLIDWORKS otherwise spends ~5 ms after every
  external call) and turns off the view animation: the same session takes 1.9 s instead of 10.4 s, with identical results.
  Drawing views are brought up to date before picking edges on the sheet, because SOLIDWORKS does not do it with the flag on.

## Safety

- Tools that delete or overwrite are marked **destructive**, so the client asks for confirmation.
- Save and export **never overwrite** an existing file unless you pass `overwrite=true`.
- `close_document` **refuses to throw away unsaved work** unless you pass `save=true` or `discard=true`.
- Export/import options are global SOLIDWORKS preferences: the server reads them, changes them for the export, and **always restores** them.
- `execute_python` is disabled unless you enable it on purpose.

## Language support

The server works with SOLIDWORKS in **Italian or English** with no setup: it detects the interface language at each connection. It never relies on names written in one language. It finds standard planes and the origin by their position in the feature tree and feature types by their internal type names, and it asks SOLIDWORKS for templates and libraries in the current language. The full test suite has been run in both languages.

The texts written on drawings and in plots follow the SOLIDWORKS language. The **server's own messages are in Italian**; MCP clients handle that without problems. Other SOLIDWORKS languages have not been tested.

## Known limitations

Each of these limitations has been tested, and the affected tool reports it in its result:

- **STEP AP242** cannot be written through the API on the Student edition, where the file comes out as AP203. AP214 works.
- **Exploded views:** SOLIDWORKS 2026 does not store a rotation inside a translation step. Rotation works in radial steps, and the tool suggests that workaround.
- **UNI** hole standards are missing from the SOLIDWORKS Hole Wizard database. Above M20 the database also lacks some sizes (M60 clearance, M68, M70; counterbores only M24-M64 in steps, no countersinks): simple and tapped holes of those sizes are made as a generic hole with the computed diameter (flat bottom if blind) plus a cosmetic thread.
- A local no-penetration contact that opens under load (a part held only by the contact) can make the solver run until the timeout.
- Saving a part right after a simulation can take a few minutes.

Any edge case or limitation encountered during automation is reported directly in the tool execution results with guidance on workarounds.

## Tests

```bash
python tests/test_offline.py                            # no SOLIDWORKS needed (runs on Linux and in CI on every push)
.venv\Scripts\python.exe tests\run_all.py               # full live regression: 35 test files on a dedicated hidden instance
```

The live tests build parts **only through the MCP tools** and compare the measured numbers with expected values. The last full regression (2026-10-31) passed 2782/2782 checks in 35 files, with zero orphan SOLIDWORKS processes.

## Credits and license

The project started from [alisamsam/solidworks-mcp](https://github.com/alisamsam/solidworks-mcp) by Samsaam Ali Baig, which had 22 basic tools. It was then rewritten and extended to 454 working tools by Elia Venturi ([@elo-savage](https://github.com/elo-savage)).

Released under the [MIT License](LICENSE). SOLIDWORKS is a trademark of Dassault Systèmes; this project is not affiliated with or endorsed by Dassault Systèmes.
