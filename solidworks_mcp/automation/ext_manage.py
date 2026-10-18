"""
Lotto ANALISI E GESTIONE (verifica geometria, modifica definizione, riordino, cartelle, aspetto, analisi sformo/spessore, schizzi esistenti, riferimenti speciali) (mixin).
Schemi in tools_ext/manage.py. I metodi usano gli helper di ModelingBase/ModelingOperations tramite self
(_part, _select_point, _select_points, _finish, _names, _new_features, _volume_m3, _mmu, _result...).
"""

import logging

logger = logging.getLogger(__name__)


class ManageOperations:
    """Mixin del lotto manage."""
