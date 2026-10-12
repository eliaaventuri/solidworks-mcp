#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Avvio del server SolidWorks MCP (stdio).

Uso:
    python solidworks_mcp_server.py
Configurazione di Claude Desktop / Claude Code: vedi README.md.
"""

import sys
import os

# Add package to path
package_dir = os.path.dirname(os.path.abspath(__file__))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

# Import and run server
from solidworks_mcp.server import run

if __name__ == "__main__":
    run()
