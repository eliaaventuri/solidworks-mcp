"""
Lotto STAMPI (linea e superficie di divisione, chiusure, divisione maschio/matrice, sottosquadri, cavita') (mixin).
Schemi in tools_ext/mold.py. I metodi usano gli helper di ModelingBase/ModelingOperations tramite self
(_part, _select_point, _select_points, _finish, _names, _new_features, _volume_m3, _mmu, _result...).
"""

import logging

logger = logging.getLogger(__name__)


class MoldOperations:
    """Mixin del lotto mold."""
