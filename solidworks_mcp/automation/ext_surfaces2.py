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
            v0 = self._volume_m3(doc)
            before = self._names(doc)
            # (revisione 2026-11-12) FeatureCutThicken ha 6 argomenti (spessore, direzione, faccia, riempi volume, ambito,
            # selezione automatica): prima ne riceveva 7, e il successo non controllava il volume
            feat = fm.FeatureCutThicken(t_m, int(direction), 0, False, False, False)
            doc.ClearSelection2(True)
            v1 = self._volume_m3(doc)
            data = {"thickness": thickness, "direction": int(direction), "volume_removed_mm3": round((v0 - v1) * 1e9, 4)}
            if feat is None and not self._new_features(doc, before):
                return self._result(False, "thicken_cut: taglio per ispessimento non creato da SolidWorks",
                                    SwErrors.swFeatureError, {"created": False, **data})
            if v0 - v1 <= 1e-12:
                self._delete_features(doc, [x["name"] for x in self._new_features(doc, before) if x["type"] != "ProfileFeature"])
                return self._result(False, "thicken_cut: il taglio non toglie materiale (la superficie non attraversa il solido "
                                    "dal lato scelto?): eliminato.", SwErrors.swFeatureError, data)
            return self._result(True, f"Taglio per ispessimento ({thickness} mm): tolti {data['volume_removed_mm3']} mm3.",
                                SwErrors.swSuccess, {"created": True, **data})
        except Exception as e:
            logger.error(f"thicken_cut: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)


    def _s2_surface_bodies(self, doc, surface_point, unit):
        """Corpi di superficie da controllare: tutti, oppure (surface_point) quello che ha una faccia nel punto (tolleranza 0,5 mm).
        (revisione 2026-11-12) prima surface_point e unit erano ignorati."""
        bodies = list(doc.GetBodies2(1, True) or [])      # 1 = corpi di superficie
        if surface_point is None:
            return bodies, None
        if len(surface_point) != 3:
            return None, "surface_point = [x,y,z]"
        ent, _d = self._find_entity(doc, "face", [self._mmu(float(c), unit) for c in surface_point], 0.0005)
        if ent is None:
            return None, f"Nessuna faccia entro 0,5 mm da {list(surface_point)}"
        body = ent.GetBody
        name = str(self._com(body, "Name"))
        if name not in [str(self._com(x, "Name")) for x in bodies]:
            return None, f"La faccia in {list(surface_point)} appartiene al corpo SOLIDO '{name}', non a una superficie"
        return [body], None

    def _s2_open_edges(self, bodies):
        out = []
        for b in bodies:
            for e in (self._com(b, "GetEdges") or []):
                faces = self._com(e, "GetTwoAdjacentFaces2")
                if not faces or len(faces) < 2 or any(f is None for f in faces):
                    row = {"body": str(self._com(b, "Name"))}
                    try:
                        row["start_mm"] = [round(float(c) * 1000, 4) for c in self._com(self._com(e, "GetStartVertex"), "GetPoint")]
                        row["end_mm"] = [round(float(c) * 1000, 4) for c in self._com(self._com(e, "GetEndVertex"), "GetPoint")]
                    except Exception:
                        pass                                   # bordo chiuso (cerchio): nessun vertice
                    out.append(row)
        return out

    def find_open_surface_edges(self, surface_point: list = None, unit: str = None) -> Dict:
        """Bordi aperti (con una sola faccia) dei corpi di superficie, o del solo corpo che passa per surface_point."""
        try:
            doc, err = self._part()
            if err:
                return err
            bodies, e = self._s2_surface_bodies(doc, surface_point, unit)
            if e:
                return self._result(False, f"find_open_surface_edges: {e}", SwErrors.swSelectionError)
            edges = self._s2_open_edges(bodies)
            return self._result(
                True, f"Controllo bordi aperti: {len(edges)} bordi aperti in {len(bodies)} corpi di superficie.",
                SwErrors.swSuccess, {"open_edges_count": len(edges), "surface_bodies": len(bodies), "open_edges": edges[:50]}
            )
        except Exception as e:
            logger.error(f"find_open_surface_edges: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def check_watertight_surface(self, surface_point: list = None, unit: str = None) -> Dict:
        """Una superficie e' a tenuta (chiude un volume) se nessun suo bordo e' aperto: tutti i corpi di superficie, o solo
        quello che passa per surface_point."""
        try:
            doc, err = self._part()
            if err:
                return err
            bodies, e = self._s2_surface_bodies(doc, surface_point, unit)
            if e:
                return self._result(False, f"check_watertight_surface: {e}", SwErrors.swSelectionError)
            edges = self._s2_open_edges(bodies)
            is_watertight = (not edges and len(bodies) > 0)
            return self._result(
                True, f"Verifica tenuta stagna: {'chiuso (watertight)' if is_watertight else 'aperto'} "
                      f"({len(edges)} bordi aperti, {len(bodies)} corpi di superficie).",
                SwErrors.swSuccess, {"watertight": is_watertight, "open_edges": len(edges), "bodies": len(bodies),
                                     "open_edges_list": edges[:50]}
            )
        except Exception as e:
            logger.error(f"check_watertight_surface: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swFeatureError)

    def zebra_stripes_display(self, enable: bool = True) -> Dict:
        """Attiva o disattiva le strisce zebrate della vista attiva (IModelView.DisplayZebraStripes, riletto).
        (revisione 2026-11-12) prima ViewDisplayZebrastripes COMMUTAVA la vista: enable=false poteva accenderle."""
        try:
            doc, err = self._part()
            if err:
                return err
            view = self._com(doc, "ActiveView")
            if view is None:
                return self._result(False, "zebra_stripes_display: il documento non ha una vista attiva.", SwErrors.swGenericError)
            before = bool(self._com(view, "DisplayZebraStripes"))
            view.DisplayZebraStripes = bool(enable)
            after = bool(self._com(view, "DisplayZebraStripes"))
            data = {"enabled": after, "before": before}
            if after != bool(enable):
                return self._result(False, f"zebra_stripes_display: SolidWorks riporta strisce {'accese' if after else 'spente'} "
                                    f"dopo la richiesta enable={bool(enable)}.", SwErrors.swGenericError, data)
            return self._result(True, f"Strisce zebrate {'accese' if after else 'spente'} (rilette dalla vista).",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"zebra_stripes_display: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swGenericError)

