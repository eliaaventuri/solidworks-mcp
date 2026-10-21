"""
MCP Resources for SolidWorks
----------------------------
Defines the standard resources exposed by the MCP server:
- solidworks://status: Connection status, version, PID, mode, language, units
- solidworks://documents: List of currently open documents
- solidworks://active-document: Detailed info about the active document
- solidworks://configuration: Server configuration and active settings
"""

import json
import asyncio
from datetime import datetime
from typing import Dict, Any, List
from mcp.types import Resource
from mcp.server.lowlevel.helper_types import ReadResourceContents

RESOURCES: List[Resource] = [
    Resource(
        uri="solidworks://status",
        name="SolidWorks Status",
        description="Current connection status, SolidWorks version, PID, mode, UI language, and default unit.",
        mimeType="application/json",
    ),
    Resource(
        uri="solidworks://documents",
        name="Open Documents",
        description="List of currently open documents in SolidWorks (title, type, path, dirty state).",
        mimeType="application/json",
    ),
    Resource(
        uri="solidworks://active-document",
        name="Active Document Details",
        description="Detailed inspection of the active document (title, type, path, configurations, material, bodies).",
        mimeType="application/json",
    ),
    Resource(
        uri="solidworks://configuration",
        name="Server Configuration",
        description="MCP server configuration settings, toolsets enabled, timeout parameters, and logging.",
        mimeType="application/json",
    ),
]


def get_status_data(sw_automation) -> Dict[str, Any]:
    connected = sw_automation.is_connected
    version = None
    ui_lang = None
    if connected and sw_automation._sw_app is not None:
        try:
            version = str(sw_automation._com(sw_automation._sw_app, "RevisionNumber"))
        except Exception:
            pass
        try:
            ui_lang = sw_automation._ui_language()
        except Exception:
            pass
    return {
        "connected": connected,
        "dedicated_mode": sw_automation.is_dedicated_mode(),
        "dedicated_pid": sw_automation._dedicated_pid,
        "version": version,
        "ui_language": ui_lang or "unknown",
        "default_unit": getattr(sw_automation.units.default_unit, "value", str(sw_automation.units.default_unit)),
        "autorestart": sw_automation.autorestart_enabled(),
        "timestamp": datetime.now().isoformat(),
    }


def get_documents_data(sw_automation) -> Dict[str, Any]:
    if not sw_automation.is_connected or sw_automation._sw_app is None:
        return {"connected": False, "count": 0, "documents": []}
    docs = []
    type_names = {1: "Part", 2: "Assembly", 3: "Drawing"}
    try:
        all_docs = sw_automation._com(sw_automation._sw_app, "GetDocuments") or ()
        active_doc = sw_automation._com(sw_automation._sw_app, "ActiveDoc")
        active_title = sw_automation._get_doc_title(active_doc) if active_doc is not None else None
        for doc in all_docs:
            try:
                title = sw_automation._get_doc_title(doc)
                doc_type = sw_automation._com(doc, "GetType")
                path = sw_automation._get_doc_path(doc)
                dirty = bool(sw_automation._com(doc, "GetSaveFlag"))
                docs.append({
                    "title": title,
                    "type": type_names.get(doc_type, "Unknown"),
                    "path": path if path else None,
                    "modified": dirty,
                    "is_active": (title == active_title) if active_title else False,
                })
            except Exception:
                pass
    except Exception as e:
        return {"connected": True, "error": str(e), "count": 0, "documents": []}
    return {"connected": True, "count": len(docs), "documents": docs}


def get_active_document_data(sw_automation) -> Dict[str, Any]:
    if not sw_automation.is_connected or sw_automation._sw_app is None:
        return {"connected": False, "active_document": None}
    try:
        doc = sw_automation._com(sw_automation._sw_app, "ActiveDoc")
        if doc is None:
            return {"connected": True, "active_document": None}
        title = sw_automation._get_doc_title(doc)
        doc_type = sw_automation._com(doc, "GetType")
        type_names = {1: "Part", 2: "Assembly", 3: "Drawing"}
        type_str = type_names.get(doc_type, "Unknown")
        path = sw_automation._get_doc_path(doc)
        dirty = bool(sw_automation._com(doc, "GetSaveFlag"))

        details: Dict[str, Any] = {
            "title": title,
            "type": type_str,
            "path": path if path else None,
            "modified": dirty,
        }

        if type_str in ("Part", "Assembly"):
            try:
                cfg = sw_automation._com(doc, "GetActiveConfiguration")
                if cfg is not None:
                    details["active_configuration"] = sw_automation._com(cfg, "Name")
            except Exception:
                pass
            try:
                cfg_names = sw_automation._com(doc, "GetConfigurationNames")
                if cfg_names:
                    details["configurations"] = list(cfg_names)
            except Exception:
                pass

        if type_str == "Part":
            try:
                part_mat = doc.GetMaterialPropertyName2("")
                if part_mat and isinstance(part_mat, (tuple, list)) and len(part_mat) > 1:
                    details["material"] = part_mat[1]
                elif isinstance(part_mat, str) and part_mat:
                    details["material"] = part_mat
            except Exception:
                pass
            try:
                bodies = doc.GetBodies2(0, True)  # 0 = swSolidBody
                if bodies:
                    details["solid_bodies_count"] = len(bodies)
            except Exception:
                pass
        elif type_str == "Assembly":
            try:
                comps = doc.GetComponents(True)  # True = top level only
                if comps:
                    details["top_level_components_count"] = len(comps)
            except Exception:
                pass
        elif type_str == "Drawing":
            try:
                sheet = doc.GetCurrentSheet
                if callable(sheet):
                    sheet = sheet()
                if sheet is not None:
                    details["current_sheet"] = sw_automation._com(sheet, "GetName")
            except Exception:
                pass

        return {"connected": True, "active_document": details}
    except Exception as e:
        return {"connected": True, "error": str(e), "active_document": None}


def get_configuration_data(config, sw_automation, tool_timeout: float, enabled_toolsets: set, python_enabled: bool) -> Dict[str, Any]:
    return {
        "default_unit": getattr(config.default_unit, "value", str(config.default_unit)),
        "startup_timeout": config.startup_timeout,
        "tool_timeout": tool_timeout,
        "log_level": config.log_level,
        "log_file": str(config.log_file),
        "enabled_toolsets": sorted(list(enabled_toolsets)),
        "allow_python": python_enabled,
        "dedicated_mode": sw_automation.is_dedicated_mode(),
        "autorestart": sw_automation.autorestart_enabled(),
    }


async def read_resource_content(
    uri_str: str,
    sw_automation,
    config,
    executor,
    tool_timeout: float,
    enabled_toolsets: set,
    python_enabled: bool,
) -> List[ReadResourceContents]:
    clean_uri = uri_str.rstrip("/")
    if clean_uri == "solidworks://status":
        fut = executor.submit(get_status_data, sw_automation)
        data = await asyncio.wrap_future(fut)
    elif clean_uri == "solidworks://documents":
        fut = executor.submit(get_documents_data, sw_automation)
        data = await asyncio.wrap_future(fut)
    elif clean_uri == "solidworks://active-document":
        fut = executor.submit(get_active_document_data, sw_automation)
        data = await asyncio.wrap_future(fut)
    elif clean_uri == "solidworks://configuration":
        data = get_configuration_data(config, sw_automation, tool_timeout, enabled_toolsets, python_enabled)
    else:
        raise ValueError(f"Unknown resource URI: {uri_str}")

    return [ReadResourceContents(content=json.dumps(data, indent=2), mime_type="application/json")]
