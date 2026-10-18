"""
Lotto SALDATURE (membri strutturali, taglia/estendi, tappi, fazzoletti, distinta di taglio, cordoni) (mixin).
Schemi in tools_ext/weldments.py. I metodi usano gli helper di ModelingBase/ModelingOperations tramite self
(_part, _select_point, _select_points, _finish, _names, _new_features, _volume_m3, _mmu, _result...).
"""

import logging

logger = logging.getLogger(__name__)


class WeldmentsOperations:
    """Mixin del lotto weldments."""
