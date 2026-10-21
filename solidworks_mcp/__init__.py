"""
SolidWorks MCP Package
----------------------
Server Model Context Protocol per usare SolidWorks da Claude (390 tool, 391 con execute_python).
Derivato da alisamsam/solidworks-mcp (Samsaam Ali Baig, licenza MIT) e riscritto da Elia (elo-savage).
"""

__version__ = "8.0.0"
__author__ = "Elia (elo-savage)"

from .automation import SolidWorksAutomation
from .config import get_config, reload_config, save_config, SolidWorksConfig
from .constants import SwErrors, SwPlanes, SwDocumentTypes, SwViews
from .utils import (
    UnitConverter, 
    mm, cm, inch, ft,
    find_solidworks,
    find_template,
    get_solidworks_info
)

__all__ = [
    # Version
    "__version__",
    "__author__",
    
    # Main class
    "SolidWorksAutomation",
    
    # Config
    "get_config",
    "reload_config", 
    "save_config",
    "SolidWorksConfig",
    
    # Constants
    "SwErrors",
    "SwPlanes",
    "SwDocumentTypes",
    "SwViews",
    
    # Utils
    "UnitConverter",
    "mm", "cm", "inch", "ft",
    "find_solidworks",
    "find_template",
    "get_solidworks_info",
]
