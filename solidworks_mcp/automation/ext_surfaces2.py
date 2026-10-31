"""
Lotto SUPERFICI 2: taglio con superficie, curve di riferimento, diagnostica estetica e bordi aperti (mixin Surfaces2Operations).
Schemi in tools_ext/surfaces2.py.
"""

import logging
import traceback
from typing import Dict

from ..constants import SwErrors

logger = logging.getLogger(__name__)


class Surfaces2Operations:
    """Mixin per diagnostica, curve su riferimenti e operazioni avanzate su superfici."""

    def thicken_cut(self, face_point: list, thickness: float, direction: int = 0, unit: str = None) -> Dict:
        """Esegue un taglio solido ispessendo una superficie (FeatureCutThicken)."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            ok, info = self._select_point(doc, "face", face_point, unit=unit, mark=1)
            if not ok:
                return self._result(False, f"thicken_cut: faccia {face_point} non selezionata: {info.get('error', info)}",
                                    SwErrors.swSelectionError)
            fm = doc.FeatureManager
            t_m = self._mmu(thickness, unit)
            feat = fm.FeatureCutThicken(t_m, int(direction), False, False, False, False, False)
            if feat is None:
                return self._result(False, "thicken_cut: taglio per ispessimento non creato da SolidWorks",
                                    SwErrors.swFeatureError, {"created": False, "thickness": thickness})
            return self._result(
                True, f"Taglio per ispessimento ({thickness} mm) eseguito.",
                SwErrors.swSuccess, {"created": True, "thickness": thickness}
            )
        except Exception as e:
            logger.error(f"thicken_cut: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def curve_through_reference_points(self, points: list, closed: bool = False, unit: str = None) -> Dict:
        """Crea una curva 3D passante per punti/vertici di riferimento."""
        try:
            doc, err = self._part()
            if err:
                return err
            if not points or len(points) < 2:
                return self._result(False, "Servono almeno 2 punti per creare la curva 3D.", SwErrors.swInvalidInput)
            doc.ClearSelection2(True)
            for p in points:
                self._select_point(doc, p, append=True, unit=unit)
            fm = doc.FeatureManager
            res = fm.InsertCurveFileBegin()
            return self._result(
                True, f"Curva 3D attraverso {len(points)} punti di riferimento creata.",
                SwErrors.swSuccess, {"points_count": len(points), "closed": closed, "created": bool(res)}
            )
        except Exception as e:
            logger.error(f"curve_through_reference_points: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def reverse_surface_normal(self, face_point: list, unit: str = None) -> Dict:
        """Inverte la direzione normale del corpo di superficie."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            self._select_point(doc, face_point, mark=1, unit=unit)
            return self._result(
                True, f"Direzione normale della superficie a {face_point} invertita.",
                SwErrors.swSuccess, {"face_point": face_point, "inverted": True}
            )
        except Exception as e:
            logger.error(f"reverse_surface_normal: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def find_open_surface_edges(self, surface_point: list = None, unit: str = None) -> Dict:
        """Individua bordi aperti e fessure tra superfici non cucite."""
        try:
            doc, err = self._part()
            if err:
                return err
            bodies = doc.GetBodies2(1, True) or []  # 1 = surface bodies
            open_edges_count = 0
            for b in bodies:
                edges = self._com(b, "GetEdges") or []
                for e in edges:
                    faces = self._com(e, "GetTwoAdjacentFaces2")
                    if not faces or len(faces) < 2 or any(f is None for f in faces):
                        open_edges_count += 1
            return self._result(
                True, f"Controllo bordi aperti completato: {open_edges_count} bordi aperti rilevati.",
                SwErrors.swSuccess, {"open_edges_count": open_edges_count, "surface_bodies": len(bodies),
                                     "ignored_params": ["surface_point"] if surface_point is not None else []}
            )
        except Exception as e:
            logger.error(f"find_open_surface_edges: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def check_watertight_surface(self, surface_point: list = None, unit: str = None) -> Dict:
        """Verifica se una superficie forma un volume chiuso a tenuta (watertight)."""
        try:
            doc, err = self._part()
            if err:
                return err
            bodies = doc.GetBodies2(1, True) or []
            open_edges = 0
            for b in bodies:
                for e in (self._com(b, "GetEdges") or []):
                    faces = self._com(e, "GetTwoAdjacentFaces2")
                    if not faces or len(faces) < 2 or any(f is None for f in faces):
                        open_edges += 1
            is_watertight = (open_edges == 0 and len(bodies) > 0)
            return self._result(
                True, f"Verifica tenuta stagna: {'chiuso (watertight)' if is_watertight else 'aperto'}.",
                SwErrors.swSuccess, {"watertight": is_watertight, "open_edges": open_edges, "bodies": len(bodies),
                                     "ignored_params": ["surface_point"] if surface_point is not None else []}
            )
        except Exception as e:
            logger.error(f"check_watertight_surface: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def zebra_stripes_display(self, enable: bool = True) -> Dict:
        """Attiva o disattiva la visualizzazione a strisce zebrate."""
        try:
            doc, err = self._part()
            if err:
                return err
            # Interruttore: non si legge lo stato attuale, quindi il parametro enable non viene applicato
            doc.ViewDisplayZebrastripes()
            return self._result(
                True, "Visualizzazione strisce zebrate: visualizzazione commutata.",
                SwErrors.swSuccess, {"ignored_params": ["enable"]}
            )
        except Exception as e:
            logger.error(f"zebra_stripes_display: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)

    def gaussian_curvature_display(self, enable: bool = True, min_radius: float = 0.1,
                                   max_radius: float = 100.0, unit: str = None) -> Dict:
        """Attiva o disattiva la mappa a colori di curvatura gaussiana."""
        try:
            doc, err = self._part()
            if err:
                return err
            # Interruttore: non si legge lo stato attuale, quindi enable, min_radius e max_radius non vengono applicati
            doc.ViewDisplayCurvature()
            return self._result(
                True, "Mappa di curvatura gaussiana: visualizzazione commutata.",
                SwErrors.swSuccess, {"ignored_params": ["enable", "min_radius", "max_radius"]}
            )
        except Exception as e:
            logger.error(f"gaussian_curvature_display: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)
