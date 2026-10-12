"""
SolidWorks MCP Server
---------------------
Main MCP server entry point with all tools.

Version: 4.0.0 (Fixed for SolidWorks 2025)
Author: Samsaam Ali Baig

Fixes v4.0.0:
- execute_python now captures stdout/stderr
- FeatureExtrusion2 with correct 23 params for SW 2025
- list_features: property access instead of method calls
- extrude_sketch: proper sketch close + select before extrude
- cut_extrude: proper sketch handling
- NEW: close_sketch tool
- NEW: get_sketch_status tool for diagnostics
"""

import io
import sys
import json
import logging
import traceback
from typing import Dict
from pathlib import Path

# MCP imports
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Local imports
from .automation import SolidWorksAutomation
from .constants import SwErrors
from .config import get_config, save_config
from .utils import get_solidworks_info, set_default_unit
from .drawing_tools import DRAWING_TOOLS, DRAWING_DISPATCH
from .modeling_tools import MODELING_TOOLS, MODELING_DISPATCH
from .assembly_tools import ASSEMBLY_TOOLS, ASSEMBLY_DISPATCH
from .data_tools import DATA_TOOLS, DATA_DISPATCH
from .simulation_tools import SIMULATION_TOOLS, SIMULATION_DISPATCH
from .safety import decorate_tools, check_call

# Configure logging
config = get_config()
LOG_FILE = Path(__file__).parent / config.log_file

logging.basicConfig(
    level=config.get_log_level_int(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8')]
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
    return decorate_tools(tools)


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

        refusal = check_call(name, arguments)          # salvataggio/esportazione su file esistente senza overwrite
        if refusal:
            result = sw_automation._result(False, refusal, SwErrors.swFileSaveError, {"refused": "file_exists"})
            return [TextContent(type="text", text=format_result(result))]
        
        # Connection Tools
        if name == "connect_solidworks":
            result = sw_automation.connect()
        
        elif name == "get_solidworks_info":
            info = get_solidworks_info()
            result = {
                "success": info["found"],
                "message": f"SolidWorks {'found' if info['found'] else 'not found'}",
                "error_code": 0 if info["found"] else 105,
                "error_name": "swSuccess" if info["found"] else "swSolidWorksNotFound",
                "data": info
            }
        
        # Document Tools
        elif name == "create_new_part":
            result = sw_automation.create_new_part()
        
        elif name == "create_new_assembly":
            result = sw_automation.create_new_assembly()
        
        elif name == "open_document":
            result = sw_automation.open_document(arguments.get("filepath", ""))
        
        elif name == "save_document":
            result = sw_automation.save_document(arguments.get("filepath"), bool(arguments.get("overwrite", False)))
        
        elif name == "close_document":
            result = sw_automation.close_document(bool(arguments.get("save", False)),
                                                  bool(arguments.get("discard", False)),
                                                  arguments.get("document"))
        
        elif name == "get_document_info":
            result = sw_automation.get_document_info()
        
        elif name == "list_open_documents":
            result = sw_automation.list_open_documents()
        
        # Sketch Tools
        elif name == "create_sketch":
            result = sw_automation.create_sketch(arguments.get("plane", "Front"))
        
        elif name == "create_sketch_on_face":
            result = sw_automation.create_sketch_on_face(
                arguments.get("x", 0),
                arguments.get("y", 0),
                arguments.get("z", 0),
                arguments.get("unit")
            )
        
        elif name == "draw_line":
            result = sw_automation.draw_line(
                arguments.get("x1", 0),
                arguments.get("y1", 0),
                arguments.get("x2", 100),
                arguments.get("y2", 0),
                arguments.get("unit")
            )
        
        elif name == "draw_circle":
            result = sw_automation.draw_circle(
                arguments.get("x", 0),
                arguments.get("y", 0),
                arguments.get("radius", 25),
                arguments.get("unit")
            )
        
        elif name == "draw_rectangle":
            result = sw_automation.draw_rectangle(
                arguments.get("x1", -50),
                arguments.get("y1", -25),
                arguments.get("x2", 50),
                arguments.get("y2", 25),
                arguments.get("unit")
            )
        
        elif name == "draw_arc":
            result = sw_automation.draw_arc_center(
                arguments.get("cx", 0),
                arguments.get("cy", 0),
                arguments.get("radius", 25),
                arguments.get("start_angle", 0),
                arguments.get("end_angle", 90),
                arguments.get("unit")
            )
        
        elif name == "draw_polygon":
            result = sw_automation.draw_polygon(
                arguments.get("cx", 0),
                arguments.get("cy", 0),
                arguments.get("radius", 25),
                arguments.get("sides", 6),
                arguments.get("unit")
            )
        
        # Feature Tools
        elif name == "extrude_sketch":
            result = sw_automation.extrude_sketch(
                arguments.get("depth", 10),
                arguments.get("both_directions", False),
                arguments.get("unit")
            )
        
        elif name == "cut_extrude":
            result = sw_automation.cut_extrude(
                arguments.get("depth", 10),
                arguments.get("through_all", False),
                arguments.get("both_directions", False),
                arguments.get("unit")
            )
        
        elif name == "fillet_edges":
            result = sw_automation.fillet_edges(
                arguments.get("radius", 2),
                arguments.get("unit"),
                arguments.get("edge_points")
            )
        
        elif name == "chamfer_edges":
            result = sw_automation.chamfer_edges(
                arguments.get("distance", 2),
                arguments.get("angle", 45),
                arguments.get("unit"),
                arguments.get("edge_points"),
                arguments.get("distance2")
            )
        
        elif name == "list_features":
            result = _list_features_fixed()
        
        # Sketch Management Tools
        elif name == "close_sketch":
            result = _close_sketch_handler()
        
        elif name == "get_sketch_status":
            result = _get_sketch_status_handler()
        
        # Utility Tools
        elif name == "set_units":
            unit = arguments.get("unit", "mm")
            set_default_unit(unit)
            sw_automation._units.default_unit = unit
            result = {
                "success": True,
                "message": f"Default unit set to: {unit}",
                "error_code": 0,
                "error_name": "swSuccess",
                "data": {"unit": unit}
            }
        
        elif name == "execute_python":
            code = arguments.get("code", "")
            if not code:
                result = sw_automation._result(False, "Code is required", SwErrors.swInvalidInput)
            else:
                result = _execute_python_fixed(code)
        
        elif name in MODELING_DISPATCH:
            method, allowed = MODELING_DISPATCH[name]
            kwargs = {k: v for k, v in arguments.items() if k in allowed}
            result = getattr(sw_automation, method)(**kwargs)

        elif name in SIMULATION_DISPATCH:
            method, allowed = SIMULATION_DISPATCH[name]
            kwargs = {k: v for k, v in arguments.items() if k in allowed}
            result = getattr(sw_automation, method)(**kwargs)

        elif name in DATA_DISPATCH:
            method, allowed = DATA_DISPATCH[name]
            kwargs = {k: v for k, v in arguments.items() if k in allowed}
            result = getattr(sw_automation, method)(**kwargs)

        elif name in ASSEMBLY_DISPATCH:
            method, allowed = ASSEMBLY_DISPATCH[name]
            kwargs = {k: v for k, v in arguments.items() if k in allowed}
            result = getattr(sw_automation, method)(**kwargs)

        elif name in DRAWING_DISPATCH:
            method, allowed = DRAWING_DISPATCH[name]
            kwargs = {k: v for k, v in arguments.items() if k in allowed}
            result = getattr(sw_automation, method)(**kwargs)

        else:
            result = sw_automation._result(False, f"Unknown tool: {name}", SwErrors.swUnknownError)
        
        logger.info(f"Result: success={result['success']}")
        return [TextContent(type="text", text=format_result(result))]
        
    except Exception as e:
        logger.error(f"Tool error: {e}\n{traceback.format_exc()}")
        return [TextContent(type="text", text=f"[ERROR] {e}")]


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
# Main Entry Point
# ============================================================================

async def main():
    """Main entry point for MCP server"""
    logger.info("Starting SolidWorks MCP Server v4.0.0 (Fixed)...")
    logger.info(f"Log file: {LOG_FILE}")
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def run():
    """Run the server"""
    import asyncio
    asyncio.run(main())


if __name__ == "__main__":
    run()
