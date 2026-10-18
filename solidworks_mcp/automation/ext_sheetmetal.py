"""
Lotto LAMIERA (flange, orli, pieghe, sviluppo, conversione, parametri) (mixin).
Schemi in tools_ext/sheetmetal.py. I metodi usano gli helper di ModelingBase/ModelingOperations tramite self
(_part, _select_point, _select_points, _finish, _names, _new_features, _volume_m3, _mmu, _result...).
"""

import logging

logger = logging.getLogger(__name__)


class SheetMetalOperations:
    """Mixin del lotto sheetmetal."""
