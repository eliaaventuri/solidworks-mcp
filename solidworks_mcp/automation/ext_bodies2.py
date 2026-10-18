"""
Lotto CORPI 2 (sposta/copia, dividi, interseca, scala corpi; ripetizioni guidate da curva/schizzo/tabella) (mixin).
Schemi in tools_ext/bodies2.py. I metodi usano gli helper di ModelingBase/ModelingOperations tramite self
(_part, _select_point, _select_points, _finish, _names, _new_features, _volume_m3, _mmu, _result...).
"""

import logging

logger = logging.getLogger(__name__)


class Bodies2Operations:
    """Mixin del lotto bodies2."""
