"""
Lotto SUPERFICI 2 (modifica: cuci, taglia, offset, estendi, elimina/sostituisci faccia, taglio con superficie, ispessisci) (mixin).
Schemi in tools_ext/surfaces2.py. I metodi usano gli helper di ModelingBase/ModelingOperations tramite self
(_part, _select_point, _select_points, _finish, _names, _new_features, _volume_m3, _mmu, _result...).
"""

import logging

logger = logging.getLogger(__name__)


class Surfaces2Operations:
    """Mixin del lotto surfaces2."""
