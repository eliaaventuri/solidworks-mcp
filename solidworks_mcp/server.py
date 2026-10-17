"""
Server MCP di SolidWorks: definizione dei tool base, smistamento di tutti i 196 tool e avvio (stdio).
I tool delle altre aree sono definiti in *_tools.py; la guardia di sovrascrittura e le annotazioni in safety.py.
"""

import io
import os
import sys
import json
import asyncio
import logging
import subprocess
import traceback
import concurrent.futures
from typing import Dict
from pathlib import Path
from logging.handlers import RotatingFileHandler

# MCP imports
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Local imports
from . import __version__
from .automation import SolidWorksAutomation
from .constants import SwErrors
from .config import get_config
from .utils import get_solidworks_info, set_default_unit
from .drawing_tools import DRAWING_TOOLS, DRAWING_DISPATCH
from .modeling_tools import MODELING_TOOLS, MODELING_DISPATCH
from .assembly_tools import ASSEMBLY_TOOLS, ASSEMBLY_DISPATCH
from .data_tools import DATA_TOOLS, DATA_DISPATCH
from .simulation_tools import SIMULATION_TOOLS, SIMULATION_DISPATCH
from .safety import decorate_tools, check_call

# Configure logging: %LOCALAPPDATA%\solidworks-mcp\ (o la cartella di Home fuori da Windows), 5 file da 5 MB
config = get_config()
LOG_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "solidworks-mcp"
LOG_FILE = Path(config.log_file) if Path(config.log_file).is_absolute() else LOG_DIR / config.log_file
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=config.get_log_level_int(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding='utf-8')]
)
logger = logging.getLogger("SolidWorksMCP")

# ============================================================================
# Global Instances
# ============================================================================

sw_automation = SolidWorksAutomation()
server = Server("solidworks-mcp-server")


# ============================================================================
# Tool Definitions
# ============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available SolidWorks tools"""
    tools = [
        # Connection Tools
        Tool(
            name="connect_solidworks",
            description="Connect to SolidWorks. Launches if not running.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="get_solidworks_info",
            description="Get SolidWorks installation information.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        
        # Document Tools
        Tool(
            name="create_new_part",
            description="Create a new part document.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="create_new_assembly",
            description="Create a new assembly document.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="open_document",
            description="Open an existing SolidWorks document.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path to file"}
                },
                "required": ["filepath"]
            }
        ),
        Tool(
            name="save_document",
            description="Save the active document. Without filepath: normal Save. With filepath: Save As (an existing "
                        "different file is overwritten only with overwrite=true).",
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path to save (optional for Save As)"},
                    "overwrite": {"type": "boolean", "default": False,
                                  "description": "True = allow overwriting an already existing file (otherwise refused)"}
                },
                "required": []
            }
        ),
        Tool(
            name="close_document",
            description="Close a document SAFELY. If it has unsaved changes it refuses and explains: use save=true "
                        "(save, then close) or discard=true (close discarding the changes). Pass `document` (title or "
                        "full path) to be sure to close the right one; default is the active document.",
            inputSchema={
                "type": "object",
                "properties": {
                    "save": {"type": "boolean", "default": False, "description": "Save before closing"},
                    "discard": {"type": "boolean", "default": False,
                                "description": "Close discarding unsaved changes (declared in the result)"},
                    "document": {"type": "string", "description": "Title (e.g. 'Parte1', 'staffa.SLDPRT') or full path of the document to close (default: active)"}
                },
                "required": []
            }
        ),
        Tool(
            name="get_document_info",
            description="Get information about the active document.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="list_open_documents",
            description="List all open documents.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        
        # Sketch Tools
        Tool(
            name="create_sketch",
            description="Create a new sketch on a plane.",
            inputSchema={
                "type": "object",
                "properties": {
                    "plane": {
                        "type": "string",
                        "default": "Front",
                        "description": "Front | Top | Right (anche in minuscolo) oppure il nome di un piano di riferimento creato (es. 'Piano1'). Risponde con gli assi dello schizzo (modello = origine + u*x_axis + v*y_axis)"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="create_sketch_on_face",
            description="Create a new sketch on an existing body face (by 3D coordinates). Use for cut-extrude on faces instead of reference planes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "number", "default": 0, "description": "X coordinate on the face"},
                    "y": {"type": "number", "default": 0, "description": "Y coordinate on the face"},
                    "z": {"type": "number", "default": 0, "description": "Z coordinate on the face"},
                    "unit": {"type": "string", "description": "Unit (mm, inch, m)"}
                },
                "required": []
            }
        ),
        Tool(
            name="draw_line",
            description="Draw a line in the active sketch.",
            inputSchema={
                "type": "object",
                "properties": {
                    "x1": {"type": "number", "default": 0, "description": "Start X"},
                    "y1": {"type": "number", "default": 0, "description": "Start Y"},
                    "x2": {"type": "number", "default": 100, "description": "End X"},
                    "y2": {"type": "number", "default": 0, "description": "End Y"},
                    "unit": {"type": "string", "description": "Unit (mm, inch, m)"}
                },
                "required": []
            }
        ),
        Tool(
            name="draw_circle",
            description="Draw a circle in the active sketch.",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "number", "default": 0, "description": "Center X"},
                    "y": {"type": "number", "default": 0, "description": "Center Y"},
                    "radius": {"type": "number", "default": 25, "description": "Radius"},
                    "unit": {"type": "string", "description": "Unit (mm, inch, m)"}
                },
                "required": []
            }
        ),
        Tool(
            name="draw_rectangle",
            description="Draw a rectangle in the active sketch.",
            inputSchema={
                "type": "object",
                "properties": {
                    "x1": {"type": "number", "default": -50, "description": "First corner X"},
                    "y1": {"type": "number", "default": -25, "description": "First corner Y"},
                    "x2": {"type": "number", "default": 50, "description": "Second corner X"},
                    "y2": {"type": "number", "default": 25, "description": "Second corner Y"},
                    "unit": {"type": "string", "description": "Unit (mm, inch, m)"}
                },
                "required": []
            }
        ),
        Tool(
            name="draw_arc",
            description="Draw an arc by center and angles.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cx": {"type": "number", "default": 0, "description": "Center X"},
                    "cy": {"type": "number", "default": 0, "description": "Center Y"},
                    "radius": {"type": "number", "default": 25, "description": "Radius"},
                    "start_angle": {"type": "number", "default": 0, "description": "Start angle (degrees)"},
                    "end_angle": {"type": "number", "default": 90, "description": "End angle (degrees)"},
                    "unit": {"type": "string", "description": "Unit for radius"}
                },
                "required": []
            }
        ),
        Tool(
            name="draw_polygon",
            description="Draw a regular polygon.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cx": {"type": "number", "default": 0, "description": "Center X"},
                    "cy": {"type": "number", "default": 0, "description": "Center Y"},
                    "radius": {"type": "number", "default": 25, "description": "Radius"},
                    "sides": {"type": "integer", "default": 6, "description": "Number of sides (3-100)"},
                    "unit": {"type": "string", "description": "Unit"}
                },
                "required": []
            }
        ),
        
        # Feature Tools
        Tool(
            name="extrude_sketch",
            description="Extrude the active sketch (Boss-Extrude).",
            inputSchema={
                "type": "object",
                "properties": {
                    "depth": {"type": "number", "default": 10, "description": "Extrusion depth"},
                    "both_directions": {"type": "boolean", "default": False, "description": "Extrude in both directions"},
                    "unit": {"type": "string", "description": "Unit"}
                },
                "required": []
            }
        ),
        Tool(
            name="cut_extrude",
            description="Cut extrude to remove material.",
            inputSchema={
                "type": "object",
                "properties": {
                    "depth": {"type": "number", "default": 10, "description": "Cut depth"},
                    "through_all": {"type": "boolean", "default": False, "description": "Cut through all"},
                    "both_directions": {"type": "boolean", "default": False, "description": "Cut both directions"},
                    "unit": {"type": "string", "description": "Unit"}
                },
                "required": []
            }
        ),
        Tool(
            name="fillet_edges",
            description="Add fillet to selected edges.",
            inputSchema={
                "type": "object",
                "properties": {
                    "radius": {"type": "number", "default": 2, "description": "Fillet radius"},
                    "edge_points": {"type": "array", "items": {"type": "array", "items": {"type": "number"}},
                                    "description": "Punti [x,y,z] SUGLI spigoli da raccordare (selezione autonoma). Senza: spigoli gia selezionati"},
                    "unit": {"type": "string", "description": "Unit"}
                },
                "required": []
            }
        ),
        Tool(
            name="chamfer_edges",
            description="Add chamfer to selected edges.",
            inputSchema={
                "type": "object",
                "properties": {
                    "distance": {"type": "number", "default": 2, "description": "Chamfer distance"},
                    "angle": {"type": "number", "default": 45, "description": "Chamfer angle (degrees)"},
                    "distance2": {"type": "number", "description": "Seconda distanza (smusso distanza-distanza)"},
                    "edge_points": {"type": "array", "items": {"type": "array", "items": {"type": "number"}},
                                    "description": "Punti [x,y,z] SUGLI spigoli da smussare (selezione autonoma). Senza: spigoli gia selezionati"},
                    "unit": {"type": "string", "description": "Unit"}
                },
                "required": []
            }
        ),
        Tool(
            name="list_features",
            description="List all features in the model.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        
        # Sketch Management Tools
        Tool(
            name="close_sketch",
            description="Close/exit the active sketch. Call this before extrude if sketch is still open.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="get_sketch_status",
            description="Get diagnostic info: active sketch state, sketch count, sketch names in feature tree.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        
        # Utility Tools
        Tool(
            name="set_units",
            description="Set default unit for dimensions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "unit": {
                        "type": "string",
                        "enum": ["mm", "inch", "m", "cm"],
                        "description": "Default unit"
                    }
                },
                "required": ["unit"]
            }
        ),
        Tool(
            name="execute_python",
            description="Execute custom Python code with stdout capture. Access 'sw' (app), 'doc' (active document). Use print() for debug output. "
                        "WARNING: runs arbitrary code on the user's PC with full permissions; prefer the dedicated tools and use this only as a last resort.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute"}
                },
                "required": ["code"]
            }
        ),
    ] + DRAWING_TOOLS + MODELING_TOOLS + ASSEMBLY_TOOLS + DATA_TOOLS + SIMULATION_TOOLS
    return decorate_tools([t for t in tools if _tool_blocked_reason(t.name) is None])


# ============================================================================
# Result Formatter
# ============================================================================

def format_result(r: Dict) -> str:
    """Format result dictionary as readable text"""
    status = "SUCCESS" if r["success"] else "ERROR"
    lines = [f"[{status}] {r['message']}"]
    
    if not r["success"]:
        lines.append(f"Error Code: {r['error_code']} ({r['error_name']})")
    
    if r.get("data"):
        lines.append("Details: " + json.dumps(r["data"], indent=2))
    
    return "\n".join(lines)


# ============================================================================
# Tool Handlers
# ============================================================================

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle MCP tool calls"""
    try:
        logger.info(f"Tool: {name}, Args: {arguments}")

        blocked = _tool_blocked_reason(name)            # tool disattivato (execute_python) o gruppo non scelto in SW_MCP_TOOLSETS
        if blocked:
            return [TextContent(type="text", text=f"[ERROR] {blocked}")]

        refusal = check_call(name, arguments)          # salvataggio/esportazione su file esistente senza overwrite
        if refusal:
            result = sw_automation._result(False, refusal, SwErrors.swFileSaveError, {"refused": "file_exists"})
            return [TextContent(type="text", text=format_result(result))]

        global _active_job
        if _active_job is not None and not _active_job.done():
            return [TextContent(type="text", text="[ERROR] SolidWorks sta ancora eseguendo un tool precedente (scaduto o bloccato): "
                                                  "controllare la finestra di SolidWorks e riprovare piu' tardi.")]
        _active_job = _SW_EXECUTOR.submit(_dispatch_tool, name, arguments or {})
        timeout = _tool_timeout()
        if sw_automation._sw_app is None:               # il tool dovra' prima avviare/collegare SolidWorks: si aggiunge il tempo di avvio
            timeout += _startup_allowance()
        try:
            result = await asyncio.wait_for(asyncio.wrap_future(_active_job), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(f"Tool {name}: oltre {timeout} s")
            return [TextContent(type="text", text=f"[ERROR] {_timeout_message(name, timeout)}")]

        logger.info(f"Result: success={result['success']}")
        return [TextContent(type="text", text=format_result(result))]
        
    except Exception as e:
        logger.error(f"Tool error: {e}\n{traceback.format_exc()}")
        return [TextContent(type="text", text=f"[ERROR] {e}")]


# ============================================================================
# Thread COM e timeout: SolidWorks (STA) va chiamato sempre dallo stesso thread; il server risponde anche se SolidWorks si blocca
# ============================================================================

def _com_worker_init():
    import pythoncom
    pythoncom.CoInitialize()


# un solo thread per tutte le chiamate COM (incluse preferenze, connessione e chiusura dell'istanza)
_SW_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="sw-com",
                                                     initializer=_com_worker_init)
_active_job = None      # future del tool in corso sul thread COM; None o concluso = libero


def _tool_timeout() -> float:
    """Secondi massimi per un tool: SW_MCP_TOOL_TIMEOUT se impostata, altrimenti config.json (tool_timeout)."""
    try:
        return float(os.environ.get("SW_MCP_TOOL_TIMEOUT") or config.tool_timeout)
    except ValueError:
        return float(config.tool_timeout)


def _startup_allowance() -> float:
    """Secondi in piu' quando SolidWorks non e' ancora collegato (avvio dell'istanza dedicata: SW_MCP_STARTUP_TIMEOUT + 60)."""
    try:
        return float(os.environ.get("SW_MCP_STARTUP_TIMEOUT", "240")) + 60
    except ValueError:
        return 300.0


def _timeout_message(name: str, timeout: float) -> str:
    if sw_automation.is_dedicated_mode() and sw_automation._dedicated_pid:
        pid = sw_automation._dedicated_pid
        killed = subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True).returncode == 0
        if killed:
            sw_automation._sw_app = None
            sw_automation._connected = False
            return (f"il tool '{name}' ha superato {timeout:.0f} s. L'istanza dedicata di SolidWorks (PID {pid}) e' stata chiusa "
                    "perche' bloccata; i documenti non salvati sono persi. "
                    + ("Il prossimo tool la rilancia (SW_MCP_AUTORESTART=1)." if sw_automation.autorestart_enabled()
                       else "Per riprendere: riavviare il server MCP, oppure impostare SW_MCP_AUTORESTART=1."))
        return (f"il tool '{name}' ha superato {timeout:.0f} s e l'istanza dedicata (PID {pid}) non si e' chiusa: "
                "terminarla da Gestione attivita'.")
    return (f"il tool '{name}' ha superato {timeout:.0f} s. SolidWorks potrebbe essere bloccato da una finestra di dialogo: "
            "controllare SolidWorks. Il server non chiude l'istanza dell'utente.")


def _dispatch_tool(name: str, arguments: dict) -> Dict:
    """Esegue un tool sul thread COM. Le preferenze anti-finestre valgono per ogni tool."""
    try:
        if sw_automation._sw_app is not None:
            sw_automation._prepare_prefs()      # niente finestre di dialogo durante QUALUNQUE tool (anche disegni/assiemi)
        result = None
        if name in SPECIAL_HANDLERS:
            result = SPECIAL_HANDLERS[name](arguments)
        else:
            for table in DISPATCH_TABLES:
                if name in table:
                    method, allowed = table[name]
                    kwargs = {k: v for k, v in arguments.items() if k in allowed}
                    result = getattr(sw_automation, method)(**kwargs)
                    break
            else:
                result = sw_automation._result(False, f"Unknown tool: {name}", SwErrors.swUnknownError)
        notice = sw_automation.__dict__.pop("_restart_notice", None)    # istanza dedicata rilanciata durante questo tool
        if notice and isinstance(result, dict):
            result["message"] = f"{notice} {result.get('message', '')}"
            result.setdefault("data", {})["instance_restarted"] = True
        return result
    finally:
        try:
            sw_automation._restore_prefs()      # preferenze anti-finestre di dialogo: valori originali dopo ogni tool
        except Exception as e:
            logger.warning(f"ripristino preferenze: {e}")


# ============================================================================
# FIXED: Execute Python with stdout capture
# ============================================================================

def _execute_python_fixed(code: str) -> Dict:
    """
    Execute custom Python code with access to SolidWorks.
    FIXED: Now captures stdout, stderr, and 'result' variable.
    """
    try:
        if not sw_automation.is_connected:
            r = sw_automation.connect()
            if not r["success"]:
                return r
        
        import win32com.client
        import pythoncom
        import math
        import os as os_module
        
        # Prepare execution context with many useful objects
        exec_globals = {
            # SolidWorks objects
            'sw': sw_automation.app,
            'doc': sw_automation.app.ActiveDoc if sw_automation.app else None,
            'automation': sw_automation,
            
            # COM libraries
            'win32com': win32com,
            'pythoncom': pythoncom,
            
            # Standard libraries
            'math': math,
            'os': os_module,
            'json': json,
            
            # Result placeholder
            'result': None,
        }
        
        # Capture stdout and stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        captured_stdout = io.StringIO()
        captured_stderr = io.StringIO()
        
        try:
            sys.stdout = captured_stdout
            sys.stderr = captured_stderr
            
            # Execute the code
            exec(code, exec_globals)
            
        finally:
            # Always restore stdout/stderr
            sys.stdout = old_stdout
            sys.stderr = old_stderr
        
        # Get captured output
        stdout_text = captured_stdout.getvalue()
        stderr_text = captured_stderr.getvalue()
        result_val = exec_globals.get('result')
        
        # Build response message
        message_parts = []
        
        if stdout_text:
            message_parts.append(f"=== Output ===\n{stdout_text.rstrip()}")
        
        if stderr_text:
            message_parts.append(f"=== Stderr ===\n{stderr_text.rstrip()}")
        
        if result_val is not None:
            message_parts.append(f"=== Result ===\n{result_val}")
        
        if not message_parts:
            message_parts.append("Code executed successfully (no output)")
        
        return {
            "success": True,
            "message": "\n\n".join(message_parts),
            "error_code": 0,
            "error_name": "swSuccess",
            "data": {
                "stdout": stdout_text,
                "stderr": stderr_text,
                "result": str(result_val) if result_val is not None else None
            }
        }
        
    except SyntaxError as e:
        return {
            "success": False,
            "message": f"Syntax error: {e}",
            "error_code": 999,
            "error_name": "swUnknownError",
            "data": {"error_type": "SyntaxError", "details": str(e)}
        }
        
    except Exception as e:
        tb = traceback.format_exc()
        return {
            "success": False,
            "message": f"Execution error: {e}\n\nTraceback:\n{tb}",
            "error_code": 999,
            "error_name": "swUnknownError",
            "data": {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": tb
            }
        }


# ============================================================================
# FIXED: list_features
# ============================================================================

def _list_features_fixed() -> Dict:
    """
    List all features in the active document.
    FIXED v4.1: Property access for SW 2025 (FirstFeature, GetNextFeature, GetTypeName2).
    """
    try:
        doc, err = sw_automation.get_active_doc()
        if err:
            return err
        
        features = []
        
        # FIXED: FirstFeature is a property in SW 2025 COM, not a method
        try:
            feat = doc.FirstFeature
        except AttributeError:
            feat = doc.FirstFeature()
        
        while feat is not None:
            try:
                name = ""
                feat_type = ""
                suppressed = False
                
                try:
                    name = feat.Name
                except:
                    name = "<unknown>"
                
                # FIXED: GetTypeName2 is a property in SW 2025 COM
                try:
                    feat_type = sw_automation._com(feat, "GetTypeName2")
                except:
                    try:
                        feat_type = feat.GetTypeName()
                    except:
                        feat_type = "<unknown>"
                
                try:
                    suppressed = feat.IsSuppressed()
                except:
                    suppressed = False
                
                features.append({
                    "name": name,
                    "type": feat_type,
                    "suppressed": bool(suppressed)
                })
                
            except Exception as e:
                features.append({
                    "name": "<error>",
                    "type": str(e),
                    "suppressed": False
                })
            
            # FIXED: GetNextFeature is a property in SW 2025 COM
            try:
                feat = sw_automation._com(feat, "GetNextFeature")
            except:
                break
        
        return {
            "success": True,
            "message": f"{len(features)} features found",
            "error_code": 0,
            "error_name": "swSuccess",
            "data": {"features": features, "count": len(features)}
        }
        
    except Exception as e:
        logger.error(f"List features error: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "message": f"Error: {e}",
            "error_code": 999,
            "error_name": "swUnknownError",
            "data": {}
        }

# ============================================================================
# NEW: close_sketch handler
# ============================================================================

def _close_sketch_handler() -> Dict:
    """
    Close the active sketch if one is open.
    Returns sketch status info.
    """
    try:
        doc, err = sw_automation.get_active_doc()
        if err:
            return err
        
        # Check if sketch is active
        had_active = False
        try:
            active_sketch = doc.SketchManager.ActiveSketch
            had_active = active_sketch is not None
        except:
            pass
        
        if had_active:
            try:
                doc.SketchManager.InsertSketch(True)
            except:
                try:
                    doc.InsertSketch2(True)
                except:
                    pass
            
            return {
                "success": True,
                "message": "Sketch closed successfully",
                "error_code": 0,
                "error_name": "swSuccess",
                "data": {"had_active_sketch": True, "action": "closed"}
            }
        else:
            return {
                "success": True,
                "message": "No active sketch to close",
                "error_code": 0,
                "error_name": "swSuccess",
                "data": {"had_active_sketch": False, "action": "none"}
            }
        
    except Exception as e:
        logger.error(f"Close sketch error: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "message": f"Error: {e}",
            "error_code": 999,
            "error_name": "swUnknownError",
            "data": {"traceback": traceback.format_exc()}
        }


# ============================================================================
# NEW: get_sketch_status handler
# ============================================================================

def _get_sketch_status_handler() -> Dict:
    """
    Get diagnostic info about the current sketch state.
    Useful for debugging sketch/extrude issues.
    """
    try:
        doc, err = sw_automation.get_active_doc()
        if err:
            return err
        
        info = {
            "has_active_sketch": False,
            "active_sketch_name": None,
            "sketch_count": 0,
            "sketch_names": [],
            "feature_count": 0,
            "extrusion_count": 0,
        }
        
        # Check active sketch
        try:
            active_sketch = doc.SketchManager.ActiveSketch
            if active_sketch is not None:
                info["has_active_sketch"] = True
                try:
                    info["active_sketch_name"] = active_sketch.Name
                except:
                    info["active_sketch_name"] = "<unknown>"
        except:
            pass
        
        # Walk feature tree (using PROPERTIES not methods)
        try:
            feat = doc.FirstFeature
            while feat is not None:
                try:
                    feat_type = feat.GetTypeName2
                    info["feature_count"] += 1
                    
                    if feat_type == "ProfileFeature":
                        info["sketch_count"] += 1
                        info["sketch_names"].append(feat.Name)
                    elif feat_type == "Extrusion":
                        info["extrusion_count"] += 1
                except:
                    pass
                try:
                    feat = feat.GetNextFeature
                except:
                    break
        except:
            pass
        
        # Build readable message
        status = "OPEN" if info["has_active_sketch"] else "CLOSED"
        msg = (f"Sketch status: {status}. "
               f"Sketches: {info['sketch_count']} {info['sketch_names']}. "
               f"Extrusions: {info['extrusion_count']}. "
               f"Total features: {info['feature_count']}")
        
        return {
            "success": True,
            "message": msg,
            "error_code": 0,
            "error_name": "swSuccess",
            "data": info
        }
        
    except Exception as e:
        logger.error(f"Sketch status error: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "message": f"Error: {e}",
            "error_code": 999,
            "error_name": "swUnknownError",
            "data": {"traceback": traceback.format_exc()}
        }


# ============================================================================
# Smistamento dei tool base
# ============================================================================

def _solidworks_info_handler(arguments: dict) -> Dict:
    info = get_solidworks_info()
    return {
        "success": info["found"],
        "message": f"SolidWorks {'found' if info['found'] else 'not found'}",
        "error_code": 0 if info["found"] else 105,
        "error_name": "swSuccess" if info["found"] else "swSolidWorksNotFound",
        "data": info
    }


def _set_units_handler(arguments: dict) -> Dict:
    unit = arguments.get("unit", "mm")
    set_default_unit(unit)
    sw_automation._units.default_unit = unit
    return {
        "success": True,
        "message": f"Default unit set to: {unit}",
        "error_code": 0,
        "error_name": "swSuccess",
        "data": {"unit": unit}
    }


def _execute_python_handler(arguments: dict) -> Dict:
    code = arguments.get("code", "")
    if not code:
        return sw_automation._result(False, "Code is required", SwErrors.swInvalidInput)
    return _execute_python_fixed(code)


# tool base che chiamano un metodo di SolidWorksAutomation: nome -> (metodo, parametri ammessi); i default sono quelli del metodo
BASE_DISPATCH = {
    "connect_solidworks": ("connect", set()),
    "create_new_part": ("create_new_part", set()),
    "create_new_assembly": ("create_new_assembly", set()),
    "open_document": ("open_document", {"filepath"}),
    "save_document": ("save_document", {"filepath", "overwrite"}),
    "close_document": ("close_document", {"save", "discard", "document"}),
    "get_document_info": ("get_document_info", set()),
    "list_open_documents": ("list_open_documents", set()),
    "create_sketch": ("create_sketch", {"plane"}),
    "create_sketch_on_face": ("create_sketch_on_face", {"x", "y", "z", "unit"}),
    "draw_line": ("draw_line", {"x1", "y1", "x2", "y2", "unit"}),
    "draw_circle": ("draw_circle", {"x", "y", "radius", "unit"}),
    "draw_rectangle": ("draw_rectangle", {"x1", "y1", "x2", "y2", "unit"}),
    "draw_arc": ("draw_arc_center", {"cx", "cy", "radius", "start_angle", "end_angle", "unit"}),
    "draw_polygon": ("draw_polygon", {"cx", "cy", "radius", "sides", "unit"}),
    "extrude_sketch": ("extrude_sketch", {"depth", "both_directions", "unit"}),
    "cut_extrude": ("cut_extrude", {"depth", "through_all", "both_directions", "unit"}),
    "fillet_edges": ("fillet_edges", {"radius", "unit", "edge_points"}),
    "chamfer_edges": ("chamfer_edges", {"distance", "angle", "unit", "edge_points", "distance2"}),
}

# tool base con un gestore proprio: nome -> funzione(arguments)
SPECIAL_HANDLERS = {
    "get_solidworks_info": _solidworks_info_handler,
    "list_features": lambda arguments: _list_features_fixed(),
    "close_sketch": lambda arguments: _close_sketch_handler(),
    "get_sketch_status": lambda arguments: _get_sketch_status_handler(),
    "set_units": _set_units_handler,
    "execute_python": _execute_python_handler,
}

# ordine di ricerca (come la vecchia catena di elif)
DISPATCH_TABLES = (BASE_DISPATCH, MODELING_DISPATCH, SIMULATION_DISPATCH, DATA_DISPATCH, ASSEMBLY_DISPATCH, DRAWING_DISPATCH)

# gruppi di tool scelti con SW_MCP_TOOLSETS (es. "base,modeling,drawings"); "base" e' sempre attivo, default: tutti
TOOLSET_TABLES = {
    "modeling": MODELING_DISPATCH,
    "drawings": DRAWING_DISPATCH,
    "assembly": ASSEMBLY_DISPATCH,
    "data": DATA_DISPATCH,
    "simulation": SIMULATION_DISPATCH,
}
TOOLSET_NAMES = ("base",) + tuple(TOOLSET_TABLES)


def _python_enabled() -> bool:
    """execute_python esegue codice arbitrario: attivo solo con SW_MCP_ALLOW_PYTHON=1 (letto a ogni chiamata)."""
    return os.environ.get("SW_MCP_ALLOW_PYTHON", "").strip() == "1"


def _enabled_toolsets() -> set:
    """Gruppi attivi da SW_MCP_TOOLSETS; vuoto o 'all' = tutti. Nomi sconosciuti: avviso nel log e ignorati."""
    raw = os.environ.get("SW_MCP_TOOLSETS", "").strip().lower()
    if not raw or raw == "all":
        return set(TOOLSET_NAMES)
    wanted = {x.strip() for x in raw.split(",") if x.strip()}
    unknown = sorted(wanted - set(TOOLSET_NAMES))
    if unknown:
        logger.warning(f"SW_MCP_TOOLSETS: gruppi sconosciuti {unknown} (validi: {', '.join(TOOLSET_NAMES)})")
    return (wanted & set(TOOLSET_NAMES)) | {"base"}


def _tool_group(name: str):
    """Gruppo di un tool, o None se il tool non esiste."""
    if name in BASE_DISPATCH or name in SPECIAL_HANDLERS or name == "execute_python":
        return "base"
    for group, table in TOOLSET_TABLES.items():
        if name in table:
            return group
    return None


def _tool_blocked_reason(name: str):
    """Motivo per cui il tool non va esposto ne' eseguito, o None se e' attivo. Tool sconosciuti: None (errore 'Unknown tool')."""
    if name == "execute_python":
        if _python_enabled():
            return None
        return ("execute_python e' disattivato: esegue codice arbitrario sul PC. Per attivarlo impostare SW_MCP_ALLOW_PYTHON=1 "
                "nella configurazione del server MCP e riavviare il client.")
    group = _tool_group(name)
    if group is None or group in _enabled_toolsets():
        return None
    return (f"il tool '{name}' appartiene al gruppo '{group}', che non e' attivo. Aggiungere '{group}' a SW_MCP_TOOLSETS "
            f"(es. base,{group}) nella configurazione del server MCP e riavviare il client.")


# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    """Main entry point for MCP server"""
    logger.info(f"Starting SolidWorks MCP Server v{__version__}...")
    logger.info(f"Log file: {LOG_FILE}")
    
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        # client disconnesso: l'istanza dedicata e nascosta non deve restare accesa (chiude SOLO il suo PID)
        # le chiamate COM vanno sul thread COM, non su quello di asyncio
        try:
            await asyncio.wait_for(asyncio.wrap_future(_SW_EXECUTOR.submit(_close_dedicated_on_exit)), timeout=60)
        except Exception as e:
            logger.warning(f"chiusura dell'istanza dedicata: {e}")
        _SW_EXECUTOR.shutdown(wait=False)


def _close_dedicated_on_exit():
    if sw_automation.is_dedicated_mode() and sw_automation._dedicated_pid:
        if _dedicated_has_unsaved():
            logger.warning(f"istanza dedicata (PID {sw_automation._dedicated_pid}) lasciata aperta: "
                           "ci sono documenti con modifiche non salvate")
        else:
            sw_automation.shutdown_dedicated()


def _dedicated_has_unsaved() -> bool:
    """True se un documento aperto nell'istanza dedicata ha modifiche non salvate (o se non si riesce a saperlo)."""
    try:
        docs = sw_automation._com(sw_automation._sw_app, "GetDocuments") or ()
        return any(bool(sw_automation._com(d, "GetSaveFlag")) for d in docs)
    except Exception:
        return True


def run():
    """Run the server"""
    import asyncio
    asyncio.run(main())


if __name__ == "__main__":
    run()
