"""
Lotto FEATURE AVANZATE (raccordi avanzati, cupola, avvolgi, filettatura modellata, guscio multispessore, sformi avanzati) (mixin).
Schemi in tools_ext/features2.py. I metodi usano gli helper di ModelingBase/ModelingOperations tramite self
(_part, _select_point, _select_points, _finish, _names, _new_features, _volume_m3, _mmu, _result...).
"""

import logging

logger = logging.getLogger(__name__)


class Features2Operations:
    """Mixin del lotto features2."""
