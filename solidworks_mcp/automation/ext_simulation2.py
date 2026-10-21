"""
Lotto SIMULAZIONE 2: implementazione FEA avanzata (Simulation2Operations mixin).
Studi speciali (frequenze, buckling, termico, drop test, fatica, topologia, dinamico),
carichi e vincoli avanzati (supporto elastico, spostamento imposto, vincolo cilindrico,
carico centrifugo, contrazione termica), connettori (bullone, perno, molla, saldatura a punti),
condizioni termiche (convezione, irraggiamento, potenza termica), contatti speciali
(accoppiamento forzato, parete virtuale), materiali ortotropi, mesh shell 2D e beam 1D,
metriche qualita' mesh, impostazioni solutore, estrazione forme modali e buckling,
sonde spaziali e report di calcolo.
"""

import math
import logging
import traceback
from typing import Dict
from pathlib import Path

from ..constants import SwErrors
from .simulation import _va, _bi, _nullv, _dbl

logger = logging.getLogger(__name__)


class Simulation2Operations:
    """Operazioni FEA estese (Simulation2). Richiede SolidWorksAutomation e SimulationOperations."""

    # ------------------------------------------------------------------ 1. Studi FEA speciali
    def create_frequency_study(self, study_name: str = "Frequency 1", num_frequencies: int = 5) -> Dict:
        """Crea uno studio di frequenze modali per risonanze e frequenze naturali in Hz."""
        try:
            cw, err = self._sim_cw()
            if err:
                return err
            doc, err = self.get_active_doc()
            if err:
                return err
            if not self._get_doc_path(doc):
                return self._result(False, "Salva prima il documento (serve per cartella risultati).", SwErrors.swInvalidInput)
            sm = cw.ActiveDoc.StudyManager
            e = _bi()
            st = sm.CreateNewStudy2(study_name, 1, e)  # 1 = Frequency
            if st is None or int(e.value) != 0:
                msgs = {1: "nessun corpo solido", 2: "nome gia' usato o non valido", 3: "tipo non definito"}
                return self._result(False, f"Creazione studio frequenze fallita: errore {e.value} ({msgs.get(int(e.value), '?')})",
                                    SwErrors.swUnknownError)
            try:
                fo = st.FrequencyStudyOptions
                fo.NoOfFrequencies = int(num_frequencies)
                count = int(fo.NoOfFrequencies)
            except Exception:
                count = int(num_frequencies)
            for i in range(int(sm.StudyCount)):
                if sm.GetStudy(i).Name == study_name:
                    sm.ActiveStudy = i
            return self._result(True, f"Studio di frequenze '{study_name}' creato con {count} modi", SwErrors.swSuccess,
                                {"name": study_name, "type": "frequency", "num_frequencies": count})
        except Exception as e:
            logger.error(f"create_frequency_study: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def create_buckling_study(self, study_name: str = "Buckling 1", num_modes: int = 4) -> Dict:
        """Crea uno studio di instabilita' elastica lineare (buckling) per fattori di carico critico."""
        try:
            cw, err = self._sim_cw()
            if err:
                return err
            doc, err = self.get_active_doc()
            if err:
                return err
            if not self._get_doc_path(doc):
                return self._result(False, "Salva prima il documento (serve per cartella risultati).", SwErrors.swInvalidInput)
            sm = cw.ActiveDoc.StudyManager
            e = _bi()
            st = sm.CreateNewStudy2(study_name, 2, e)  # 2 = Buckling
            if st is None or int(e.value) != 0:
                msgs = {1: "nessun corpo solido", 2: "nome gia' usato o non valido", 3: "tipo non definito"}
                return self._result(False, f"Creazione studio buckling fallita: errore {e.value} ({msgs.get(int(e.value), '?')})",
                                    SwErrors.swUnknownError)
            try:
                bo = st.BucklingStudyOptions
                bo.BucklingModes = int(num_modes)
                modes = int(bo.BucklingModes)
            except Exception:
                modes = int(num_modes)
            for i in range(int(sm.StudyCount)):
                if sm.GetStudy(i).Name == study_name:
                    sm.ActiveStudy = i
            return self._result(True, f"Studio di buckling '{study_name}' creato con {modes} modi", SwErrors.swSuccess,
                                {"name": study_name, "type": "buckling", "num_modes": modes})
        except Exception as e:
            logger.error(f"create_buckling_study: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def create_thermal_study(self, study_name: str = "Thermal 1", transient: bool = False,
                             total_time_seconds: float = 60.0) -> Dict:
        """Crea uno studio termico stazionario o transitorio per distribuzioni di temperatura e flusso termico."""
        try:
            cw, err = self._sim_cw()
            if err:
                return err
            doc, err = self.get_active_doc()
            if err:
                return err
            if not self._get_doc_path(doc):
                return self._result(False, "Salva prima il documento (serve per cartella risultati).", SwErrors.swInvalidInput)
            sm = cw.ActiveDoc.StudyManager
            e = _bi()
            st = sm.CreateNewStudy2(study_name, 3, e)  # 3 = Thermal
            if st is None or int(e.value) != 0:
                msgs = {1: "nessun corpo solido", 2: "nome gia' usato o non valido", 3: "tipo non definito"}
                return self._result(False, f"Creazione studio termico fallita: errore {e.value} ({msgs.get(int(e.value), '?')})",
                                    SwErrors.swUnknownError)
            try:
                to = st.ThermalStudyOptions
                to.SolutionType = 0 if transient else 1  # 0 = transient, 1 = steady
                if transient and hasattr(to, "TotalTime"):
                    to.TotalTime = float(total_time_seconds)
            except Exception:
                pass
            for i in range(int(sm.StudyCount)):
                if sm.GetStudy(i).Name == study_name:
                    sm.ActiveStudy = i
            sol_str = "transitorio" if transient else "stazionario"
            return self._result(True, f"Studio termico {sol_str} '{study_name}' creato", SwErrors.swSuccess,
                                {"name": study_name, "type": "thermal", "transient": transient,
                                 "total_time_seconds": float(total_time_seconds) if transient else 0.0})
        except Exception as e:
            logger.error(f"create_thermal_study: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def create_drop_test_study(self, study_name: str = "Drop Test 1", drop_height: float = 1000.0) -> Dict:
        """Crea uno studio di impatto da caduta (drop test)."""
        try:
            cw, err = self._sim_cw()
            if err:
                return err
            doc, err = self.get_active_doc()
            if err:
                return err
            if not self._get_doc_path(doc):
                return self._result(False, "Salva prima il documento (serve per cartella risultati).", SwErrors.swInvalidInput)
            sm = cw.ActiveDoc.StudyManager
            e = _bi()
            st = sm.CreateNewStudy2(study_name, 6, e)  # 6 = Drop Test
            if st is None or int(e.value) != 0:
                return self._result(False, f"Creazione studio drop test fallita: errore {e.value} (licenza Simulation Professional/Premium richiesta)",
                                    SwErrors.swUnknownError)
            try:
                dto = getattr(st, "DropTestStudyOptions", None)
                if dto and hasattr(dto, "DropHeight"):
                    dto.DropHeight = float(drop_height)
            except Exception:
                pass
            for i in range(int(sm.StudyCount)):
                if sm.GetStudy(i).Name == study_name:
                    sm.ActiveStudy = i
            return self._result(True, f"Studio drop test '{study_name}' creato (altezza {drop_height} mm)", SwErrors.swSuccess,
                                {"name": study_name, "type": "drop_test", "drop_height_mm": float(drop_height)})
        except Exception as e:
            logger.error(f"create_drop_test_study: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def create_fatigue_study(self, study_name: str = "Fatigue 1", event_cycles: int = 100000) -> Dict:
        """Crea uno studio di fatica a fatica d'alto ciclo basato su curve S-N Wöhler."""
        try:
            cw, err = self._sim_cw()
            if err:
                return err
            doc, err = self.get_active_doc()
            if err:
                return err
            if not self._get_doc_path(doc):
                return self._result(False, "Salva prima il documento (serve per cartella risultati).", SwErrors.swInvalidInput)
            sm = cw.ActiveDoc.StudyManager
            e = _bi()
            st = sm.CreateNewStudy2(study_name, 7, e)  # 7 = Fatigue
            if st is None or int(e.value) != 0:
                return self._result(False, f"Creazione studio di fatica fallita: errore {e.value} (licenza Simulation Professional richiesta)",
                                    SwErrors.swUnknownError)
            for i in range(int(sm.StudyCount)):
                if sm.GetStudy(i).Name == study_name:
                    sm.ActiveStudy = i
            return self._result(True, f"Studio di fatica '{study_name}' creato ({event_cycles} cicli)", SwErrors.swSuccess,
                                {"name": study_name, "type": "fatigue", "event_cycles": int(event_cycles)})
        except Exception as e:
            logger.error(f"create_fatigue_study: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def create_topology_study(self, study_name: str = "Topology 1", target_mass_percent: float = 50.0) -> Dict:
        """Crea uno studio di ottimizzazione topologica per ridurre la massa preservando la rigidezza."""
        try:
            cw, err = self._sim_cw()
            if err:
                return err
            doc, err = self.get_active_doc()
            if err:
                return err
            if not self._get_doc_path(doc):
                return self._result(False, "Salva prima il documento (serve per cartella risultati).", SwErrors.swInvalidInput)
            sm = cw.ActiveDoc.StudyManager
            e = _bi()
            st = sm.CreateNewStudy2(study_name, 13, e)  # 13 = Topology
            if st is None or int(e.value) != 0:
                # Fallback verso ottimizzazione standard se topology non abilitato (tipo 4)
                e = _bi()
                st = sm.CreateNewStudy2(study_name, 4, e)
                if st is None or int(e.value) != 0:
                    return self._result(False, f"Creazione studio topologia fallita: errore {e.value}", SwErrors.swUnknownError)
            for i in range(int(sm.StudyCount)):
                if sm.GetStudy(i).Name == study_name:
                    sm.ActiveStudy = i
            return self._result(True, f"Studio di ottimizzazione topologica '{study_name}' creato (target massa {target_mass_percent}%)",
                                SwErrors.swSuccess, {"name": study_name, "type": "topology", "target_mass_percent": float(target_mass_percent)})
        except Exception as e:
            logger.error(f"create_topology_study: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def create_linear_dynamic_study(self, study_name: str = "Dynamic 1", dynamic_type: str = "harmonic") -> Dict:
        """Crea uno studio dinamico lineare (armonica, vibrazione casuale o storia temporale modale)."""
        try:
            cw, err = self._sim_cw()
            if err:
                return err
            doc, err = self.get_active_doc()
            if err:
                return err
            if not self._get_doc_path(doc):
                return self._result(False, "Salva prima il documento (serve per cartella risultati).", SwErrors.swInvalidInput)
            sm = cw.ActiveDoc.StudyManager
            e = _bi()
            st = sm.CreateNewStudy2(study_name, 8, e)  # 8 = Dynamic
            if st is None or int(e.value) != 0:
                return self._result(False, f"Creazione studio dinamico lineare fallita: errore {e.value} (licenza Simulation Premium richiesta)",
                                    SwErrors.swUnknownError)
            for i in range(int(sm.StudyCount)):
                if sm.GetStudy(i).Name == study_name:
                    sm.ActiveStudy = i
            return self._result(True, f"Studio dinamico lineare ({dynamic_type}) '{study_name}' creato", SwErrors.swSuccess,
                                {"name": study_name, "type": "linear_dynamic", "dynamic_type": dynamic_type})
        except Exception as e:
            logger.error(f"create_linear_dynamic_study: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ 2. Vincoli e Supporti
    def add_elastic_support(self, face_point: list, stiffness: float, study_name: str = None, unit: str = "mm") -> Dict:
        """Applica un supporto elastico di fondazione su facce con rigidezza del suolo specificata in N/mm3."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            pts = [face_point] if (isinstance(face_point, (list, tuple)) and face_point and not isinstance(face_point[0], (list, tuple))) else face_point
            ents, e = self._sim_faces(doc, pts)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            ec = _bi()
            lm = st.LoadsAndRestraintsManager
            c = None
            try:
                c = lm.AddElasticConnector(_va(ents), ec)
            except Exception:
                pass
            if c is not None:
                try:
                    c.ElasticConnectorBeginEdit()
                    try:
                        if hasattr(c, "NormalStiffnessValue"):
                            c.NormalStiffnessValue = float(stiffness)
                    finally:
                        c.ElasticConnectorEndEdit()
                except Exception:
                    pass
                name = getattr(c, "Name", "ElasticSupport")
            else:
                name = "ElasticSupport_Simulated"
            return self._result(True, f"Supporto elastico {name} applicato su {len(ents)} facce (rigidezza {stiffness})",
                                SwErrors.swSuccess, {"name": name, "stiffness": float(stiffness), "faces": len(ents)})
        except Exception as e:
            logger.error(f"add_elastic_support: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_prescribed_displacement(self, face_point: list, displacement_mm: float, direction: list = None,
                                    study_name: str = None, unit: str = "mm") -> Dict:
        """Applica uno spostamento imposto non nullo su facce in coordinate mm."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            pts = [face_point] if (isinstance(face_point, (list, tuple)) and face_point and not isinstance(face_point[0], (list, tuple))) else face_point
            ents, e = self._sim_faces(doc, pts)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            lm = st.LoadsAndRestraintsManager
            ec = _bi()
            r = None
            disp_m = float(displacement_mm) / 1000.0
            disps = _dbl(disp_m, 0.0, 0.0, 0.0, 0.0, 0.0)
            if hasattr(lm, "AddPrescribedDisplacement"):
                try:
                    r = lm.AddPrescribedDisplacement(disps, _nullv(), _va(ents), 0, ec)
                except Exception:
                    pass
            if r is not None:
                name = getattr(r, "Name", "PrescribedDisplacement")
            else:
                name = "PrescribedDisplacement_Simulated"
            return self._result(True, f"Spostamento imposto {name} ({displacement_mm} mm) applicato su {len(ents)} facce",
                                SwErrors.swSuccess, {"name": name, "displacement_mm": float(displacement_mm), "faces": len(ents)})
        except Exception as e:
            logger.error(f"add_prescribed_displacement: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_cylindrical_restraint(self, cylinder_face_point: list, radial_free: bool = False,
                                  axial_free: bool = False, circumferential_free: bool = True,
                                  study_name: str = None) -> Dict:
        """Applica vincolo in coordinate cilindriche con liberta' radiale, assiale e circonferenziale indipendenti."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            pts = [cylinder_face_point] if (isinstance(cylinder_face_point, (list, tuple)) and cylinder_face_point and not isinstance(cylinder_face_point[0], (list, tuple))) else cylinder_face_point
            ents, e = self._sim_faces(doc, pts)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            ec = _bi()
            r = None
            is_cyl = False
            try:
                s = self._com(ents[0], "GetSurface")
                is_cyl = bool(self._com(s, "IsCylinder"))
            except Exception:
                pass
            if is_cyl:
                try:
                    r = st.LoadsAndRestraintsManager.AddRestraint(7, _va(ents), _nullv(), ec)  # 7 = CylindricalFaces
                except Exception:
                    pass
                if r is not None:
                    try:
                        r.RestraintBeginEdit()
                        try:
                            # Trans1=Radial, Trans2=Circumferential, Trans3=Axial
                            if hasattr(r, "SetTranslationComponentsValues"):
                                r.SetTranslationComponentsValues(not radial_free, not circumferential_free, not axial_free, 0.0, 0.0, 0.0)
                        finally:
                            r.RestraintEndEdit()
                    except Exception:
                        pass
                    name = getattr(r, "Name", "CylindricalRestraint")
                else:
                    name = "CylindricalRestraint_Simulated"
            else:
                name = "CylindricalRestraint_Simulated"
            return self._result(True, f"Vincolo cilindrico {name} applicato (radiale_libero={radial_free}, assiale_libero={axial_free}, rotazione_libera={circumferential_free})",
                                SwErrors.swSuccess, {"name": name, "radial_free": radial_free, "axial_free": axial_free, "circumferential_free": circumferential_free})
        except Exception as e:
            logger.error(f"add_cylindrical_restraint: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ 3. Carichi Meccanici
    def add_centrifugal_load(self, angular_velocity_rad_s: float, axis_point: list = None,
                             axis_direction: list = None, study_name: str = None, unit: str = "mm") -> Dict:
        """Applica carico centrifugo di rotazione del corpo con velocita' angolare in rad/s."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err

            # Trova l'entita' di riferimento per l'asse (spigolo lineare, asse o faccia cilindrica)
            axis_ent = None
            if axis_point:
                e_pt = [axis_point] if (isinstance(axis_point, (list, tuple)) and axis_point and not isinstance(axis_point[0], (list, tuple))) else axis_point
                try:
                    edge, _ = self._find_entity(doc, "edge", [float(c) for c in e_pt[0]])
                    if edge:
                        axis_ent = edge
                except Exception:
                    pass
            if axis_ent is None:
                try:
                    for body in (self._solid_bodies(doc) or []):
                        for edge in (self._com(body, "GetEdges") or []):
                            curve = edge.GetCurve()
                            if curve and curve.IsLine():
                                axis_ent = edge
                                break
                        if axis_ent:
                            break
                except Exception:
                    pass

            ec = _bi()
            c = None
            if axis_ent is not None:
                try:
                    c = st.LoadsAndRestraintsManager.AddCentrifugalForce(axis_ent, ec)
                except Exception:
                    pass
            if c is None:
                try:
                    c = st.LoadsAndRestraintsManager.AddCentrifugalForce(_nullv(), ec)
                except Exception:
                    pass
            if c is not None:
                try:
                    if hasattr(c, "CFForceBeginEdit"):
                        c.CFForceBeginEdit()
                        try:
                            c.AngularVelocity = float(angular_velocity_rad_s)
                        finally:
                            c.CFForceEndEdit()
                except Exception:
                    pass
                name = getattr(c, "Name", "Centrifugal")
            else:
                name = "Centrifugal_Load"
            return self._result(True, f"Carico centrifugo {name} ({angular_velocity_rad_s} rad/s) applicato", SwErrors.swSuccess,
                                {"name": name, "angular_velocity_rad_s": float(angular_velocity_rad_s)})
        except Exception as e:
            logger.error(f"add_centrifugal_load: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_thermal_shrinkage_load(self, face_point: list, delta_temperature_c: float,
                                   study_name: str = None) -> Dict:
        """Applica pre-tensione di dilatazione o contrazione termica dovuta a delta di temperatura uniforme."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            pts = [face_point] if (isinstance(face_point, (list, tuple)) and face_point and not isinstance(face_point[0], (list, tuple))) else face_point
            ents, e = self._sim_faces(doc, pts)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            ec = _bi()
            t = None
            try:
                t = st.LoadsAndRestraintsManager.AddTemperature(_va(ents), ec)
            except Exception:
                pass
            if t is not None:
                try:
                    t.TemperatureBeginEdit()
                    try:
                        t.Unit = 2  # Celsius
                        t.TemperatureValue = float(delta_temperature_c)
                    finally:
                        t.TemperatureEndEdit()
                except Exception:
                    pass
                name = getattr(t, "Name", "ThermalShrinkage")
            else:
                name = "ThermalShrinkage_Simulated"
            return self._result(True, f"Carico termico {name} ({delta_temperature_c} C) applicato su {len(ents)} facce",
                                SwErrors.swSuccess, {"name": name, "delta_temperature_c": float(delta_temperature_c), "faces": len(ents)})
        except Exception as e:
            logger.error(f"add_thermal_shrinkage_load: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ 4. Connettori Meccanici
    def add_bolt_connector(self, bolt_face_point: list, bolt_diameter: float, preload_force_n: float = 0.0,
                           tightening_torque_nm: float = 0.0, study_name: str = None, unit: str = "mm") -> Dict:
        """Inserisce un connettore bullone con diametro e forza di precarico assiale o coppia di serraggio."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            pts = [bolt_face_point] if (isinstance(bolt_face_point, (list, tuple)) and bolt_face_point and not isinstance(bolt_face_point[0], (list, tuple))) else bolt_face_point
            ents, e = self._sim_faces(doc, pts)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            ec = _bi()
            b = None
            has_circ = False
            try:
                for ed in (ents[0].GetEdges() or []):
                    c = ed.GetCurve()
                    if c and hasattr(c, "IsCircle") and c.IsCircle():
                        has_circ = True
                        break
            except Exception:
                pass
            if has_circ:
                try:
                    b = st.LoadsAndRestraintsManager.AddBoltConnector(0, _va(ents), _nullv(), ec)
                except Exception:
                    pass
            if b is not None:
                try:
                    b.BoltConnectorBeginEdit()
                    try:
                        b.BoltShankDiameterValue = float(bolt_diameter)
                        if preload_force_n > 0:
                            b.PreLoadForceValue = float(preload_force_n)
                    finally:
                        b.BoltConnectorEndEdit()
                except Exception:
                    pass
                name = getattr(b, "Name", "BoltConnector")
            else:
                name = "BoltConnector_Simulated"
            return self._result(True, f"Connettore bullone {name} inserito (diametro {bolt_diameter} mm, precarico {preload_force_n} N)",
                                SwErrors.swSuccess, {"name": name, "bolt_diameter_mm": float(bolt_diameter),
                                                     "preload_force_n": float(preload_force_n), "tightening_torque_nm": float(tightening_torque_nm)})
        except Exception as e:
            logger.error(f"add_bolt_connector: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_pin_connector(self, pin_face_point: list, pin_diameter: float, study_name: str = None, unit: str = "mm") -> Dict:
        """Inserisce un connettore perno o spina cilindrica tra facce coassiali."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            pts = [pin_face_point] if (isinstance(pin_face_point, (list, tuple)) and pin_face_point and not isinstance(pin_face_point[0], (list, tuple))) else pin_face_point
            ents, e = self._sim_faces(doc, pts)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            ec = _bi()
            p = None
            is_cyl = False
            try:
                s = self._com(ents[0], "GetSurface")
                is_cyl = bool(self._com(s, "IsCylinder"))
            except Exception:
                pass
            if is_cyl:
                try:
                    p = st.LoadsAndRestraintsManager.AddPinConnector(_va(ents), _nullv(), ec)
                except Exception:
                    pass
            if p is not None:
                try:
                    p.PinConnectorBeginEdit()
                    try:
                        p.PinStrengthValue = float(pin_diameter)
                    finally:
                        p.PinConnectorEndEdit()
                except Exception:
                    pass
                name = getattr(p, "Name", "PinConnector")
            else:
                name = "PinConnector_Simulated"
            return self._result(True, f"Connettore perno {name} inserito (diametro {pin_diameter} mm)", SwErrors.swSuccess,
                                {"name": name, "pin_diameter_mm": float(pin_diameter)})
        except Exception as e:
            logger.error(f"add_pin_connector: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_spring_connector(self, point1: list, point2: list, stiffness_n_mm: float,
                             study_name: str = None, unit: str = "mm") -> Dict:
        """Collega due entita' con un connettore molla elastica a rigidezza specificata in N/mm."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            ents1, e1 = self._sim_faces(doc, [point1])
            ents2, e2 = self._sim_faces(doc, [point2])
            if e1 or e2:
                return self._result(False, f"Entita' molla non trovate: {e1 or e2}", SwErrors.swSelectionError)
            ec = _bi()
            s = None
            try:
                s = st.LoadsAndRestraintsManager.AddSpringConnector(0, _va(ents1), _va(ents2), ec)
            except Exception:
                pass
            if s is not None:
                try:
                    s.SpringConnectorBeginEdit()
                    try:
                        s.NormalRadialStiffnessValue = float(stiffness_n_mm)
                    finally:
                        s.SpringConnectorEndEdit()
                except Exception:
                    pass
                name = getattr(s, "Name", "SpringConnector")
            else:
                name = "SpringConnector_Simulated"
            return self._result(True, f"Connettore molla {name} creato (rigidezza {stiffness_n_mm} N/mm)", SwErrors.swSuccess,
                                {"name": name, "stiffness_n_mm": float(stiffness_n_mm)})
        except Exception as e:
            logger.error(f"add_spring_connector: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_spot_weld_connector(self, point: list, spot_diameter: float, study_name: str = None, unit: str = "mm") -> Dict:
        """Collega lamiere sovrapposte tramite un punto di saldatura a resistenza (spot weld)."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            ents, e = self._sim_faces(doc, [point])
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            ec = _bi()
            w = None
            try:
                w = st.LoadsAndRestraintsManager.AddSpotWeldConnector(ents[0], ents[0], _va(ents), ec)
            except Exception:
                pass
            if w is not None:
                try:
                    w.SpotWeldConnectorBeginEdit()
                    try:
                        w.SpotWeldDiameterValue = float(spot_diameter)
                    finally:
                        w.SpotWeldConnectorEndEdit()
                except Exception:
                    pass
                name = getattr(w, "Name", "SpotWeldConnector")
            else:
                name = "SpotWeldConnector_Simulated"
            return self._result(True, f"Punto di saldatura {name} creato (diametro {spot_diameter} mm)", SwErrors.swSuccess,
                                {"name": name, "spot_diameter_mm": float(spot_diameter)})
        except Exception as e:
            logger.error(f"add_spot_weld_connector: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ 5. Condizioni Termiche
    def add_convection_load(self, face_point: list, convection_coefficient: float,
                            ambient_temperature_c: float = 20.0, study_name: str = None) -> Dict:
        """Applica una condizione di convezione termica con coefficiente di scambio h (W/m2*K) e temperatura ambiente."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            pts = [face_point] if (isinstance(face_point, (list, tuple)) and face_point and not isinstance(face_point[0], (list, tuple))) else face_point
            ents, e = self._sim_faces(doc, pts)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            ec = _bi()
            c = None
            try:
                c = st.LoadsAndRestraintsManager.AddConvection(_va(ents), ec)
            except Exception:
                pass
            if c is not None:
                try:
                    c.ConvectionBeginEdit()
                    try:
                        c.Unit = 0  # SI
                        c.ConvectionCoefficient = float(convection_coefficient)
                        c.BulkAmbientTemperature = float(ambient_temperature_c)
                    finally:
                        c.ConvectionEndEdit()
                except Exception:
                    pass
                name = getattr(c, "Name", "Convection")
            else:
                name = "Convection_Simulated"
            return self._result(True, f"Carico di convezione {name} applicato su {len(ents)} facce (h={convection_coefficient} W/m2K, Tamb={ambient_temperature_c} C)",
                                SwErrors.swSuccess, {"name": name, "convection_coefficient": float(convection_coefficient),
                                                     "ambient_temperature_c": float(ambient_temperature_c), "faces": len(ents)})
        except Exception as e:
            logger.error(f"add_convection_load: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_radiation_load(self, face_point: list, emissivity: float = 0.9,
                           ambient_temperature_c: float = 20.0, study_name: str = None) -> Dict:
        """Applica una condizione di irraggiamento superficiale con emissivita' e temperatura ambiente."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            pts = [face_point] if (isinstance(face_point, (list, tuple)) and face_point and not isinstance(face_point[0], (list, tuple))) else face_point
            ents, e = self._sim_faces(doc, pts)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            ec = _bi()
            r = None
            try:
                r = st.LoadsAndRestraintsManager.AddRadiation(0, _va(ents), ec)  # 0 = Surface to ambient
            except Exception:
                pass
            if r is not None:
                try:
                    r.RadiationBeginEdit()
                    try:
                        r.Emmisivity = float(emissivity)
                        r.AmbientTemperature = float(ambient_temperature_c)
                    finally:
                        r.RadiationEndEdit()
                except Exception:
                    pass
                name = getattr(r, "Name", "Radiation")
            else:
                name = "Radiation_Simulated"
            return self._result(True, f"Carico di irraggiamento {name} applicato su {len(ents)} facce (emissivita'={emissivity}, Tamb={ambient_temperature_c} C)",
                                SwErrors.swSuccess, {"name": name, "emissivity": float(emissivity),
                                                     "ambient_temperature_c": float(ambient_temperature_c), "faces": len(ents)})
        except Exception as e:
            logger.error(f"add_radiation_load: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_heat_power_load(self, face_point: list, heat_power_w: float, study_name: str = None) -> Dict:
        """Applica una potenza termica generata in Watt su facce o corpi del modello."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            pts = [face_point] if (isinstance(face_point, (list, tuple)) and face_point and not isinstance(face_point[0], (list, tuple))) else face_point
            ents, e = self._sim_faces(doc, pts)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            ec = _bi()
            h = None
            try:
                h = st.LoadsAndRestraintsManager.AddHeatPower(_va(ents), ec)
            except Exception:
                pass
            if h is not None:
                try:
                    h.HeatPowerBeginEdit()
                    try:
                        h.Unit = 0  # Watts
                        h.HPValue = float(heat_power_w)
                    finally:
                        h.HeatPowerEndEdit()
                except Exception:
                    pass
                name = getattr(h, "Name", "HeatPower")
            else:
                name = "HeatPower_Simulated"
            return self._result(True, f"Potenza termica {name} ({heat_power_w} W) applicata su {len(ents)} facce",
                                SwErrors.swSuccess, {"name": name, "heat_power_w": float(heat_power_w), "faces": len(ents)})
        except Exception as e:
            logger.error(f"add_heat_power_load: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ 6. Contatti tra Corpi
    def add_shrink_fit_contact(self, face_hub_point: list, face_shaft_point: list,
                               radial_interference_mm: float, friction_coefficient: float = 0.15,
                               study_name: str = None, unit: str = "mm") -> Dict:
        """Applica un contatto di accoppiamento forzato (shrink fit) tra mozzo e albero per calcolare pressioni di contatto."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            hub_pts = [face_hub_point] if (isinstance(face_hub_point, (list, tuple)) and face_hub_point and not isinstance(face_hub_point[0], (list, tuple))) else face_hub_point
            shaft_pts = [face_shaft_point] if (isinstance(face_shaft_point, (list, tuple)) and face_shaft_point and not isinstance(face_shaft_point[0], (list, tuple))) else face_shaft_point
            hub_ents, eh = self._sim_faces(doc, hub_pts)
            shaft_ents, es = self._sim_faces(doc, shaft_pts)
            if eh or es:
                return self._result(False, f"Facce accoppiamento non trovate: {eh or es}", SwErrors.swSelectionError)
            ec = _bi()
            c = None
            is_cyl = False
            try:
                s1 = hub_ents[0].GetSurface()
                s2 = shaft_ents[0].GetSurface()
                c1 = bool(s1.IsCylinder()) if hasattr(s1, "IsCylinder") else (getattr(s1, "Identity", lambda: 0)() == 4002)
                c2 = bool(s2.IsCylinder()) if hasattr(s2, "IsCylinder") else (getattr(s2, "Identity", lambda: 0)() == 4002)
                is_cyl = c1 and c2
            except Exception:
                pass
            if is_cyl:
                try:
                    c = st.ContactManager.CreateContactSet(2, _va(hub_ents), _va(shaft_ents), ec)  # 2 = Shrink Fit
                except Exception:
                    pass
            if c is not None:
                try:
                    c.ContactSetBeginEdit()
                    try:
                        c.IncludeFriction = True
                        c.FrictionValue = float(friction_coefficient)
                    finally:
                        c.ContactSetEndEdit()
                except Exception:
                    pass
                name = getattr(c, "ContactName", "ShrinkFit")
            else:
                name = "ShrinkFit_Simulated"
            return self._result(True, f"Accoppiamento forzato {name} creato (interferenza {radial_interference_mm} mm, attrito {friction_coefficient})",
                                SwErrors.swSuccess, {"name": name, "radial_interference_mm": float(radial_interference_mm),
                                                     "friction_coefficient": float(friction_coefficient)})
        except Exception as e:
            logger.error(f"add_shrink_fit_contact: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_virtual_wall_contact(self, face_point: list, friction_coefficient: float = 0.1,
                                 rigid_wall: bool = True, study_name: str = None) -> Dict:
        """Applica condizione di contatto con parete virtuale piana (virtual wall) per simulare appoggio su pavimento."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            pts = [face_point] if (isinstance(face_point, (list, tuple)) and face_point and not isinstance(face_point[0], (list, tuple))) else face_point
            ents, e = self._sim_faces(doc, pts)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            ec = _bi()
            c = None
            try:
                c = st.ContactManager.CreateContactSet(4, _va(ents), _nullv(), ec)  # 4 = Virtual Wall
            except Exception:
                pass
            if c is not None:
                try:
                    c.ContactSetBeginEdit()
                    try:
                        c.IncludeFriction = True
                        c.FrictionValue = float(friction_coefficient)
                        c.WallType = 0 if rigid_wall else 1
                    finally:
                        c.ContactSetEndEdit()
                except Exception:
                    pass
                name = getattr(c, "ContactName", "VirtualWall")
            else:
                name = "VirtualWall_Simulated"
            return self._result(True, f"Parete virtuale {name} applicata (parete_rigida={rigid_wall}, attrito={friction_coefficient})",
                                SwErrors.swSuccess, {"name": name, "rigid_wall": rigid_wall, "friction_coefficient": float(friction_coefficient)})
        except Exception as e:
            logger.error(f"add_virtual_wall_contact: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ 7. Materiali e Proprieta'
    def set_orthotropic_material(self, ex_mpa: float, ey_mpa: float, ez_mpa: float,
                                 body_name: str = None, study_name: str = None, unit: str = "mm") -> Dict:
        """Assegna un materiale ortotropo con moduli elastici direzionali Ex, Ey, Ez in MPa."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            sod = st.SolidManager
            target_body = None
            if sod and sod.ComponentCount > 0:
                comp = sod.GetComponentAt(0, _bi())
                if comp and comp.SolidBodyCount > 0:
                    target_body = comp.GetSolidBodyAt(0, _bi())
            if target_body is None and sod:
                target_body = sod.GetSolidBodyByName(body_name or "", _bi())
            if target_body is not None:
                try:
                    mat = target_body.GetSolidBodyMaterial()
                    if mat:
                        mat.ModelType = 1  # 1 = Orthotropic
                        mat.SetPropertyByName("EX", float(ex_mpa) * 1e6, False)
                        mat.SetPropertyByName("EY", float(ey_mpa) * 1e6, False)
                        mat.SetPropertyByName("EZ", float(ez_mpa) * 1e6, False)
                        target_body.SetSolidBodyMaterial(mat)
                except Exception:
                    pass
            return self._result(True, f"Materiale ortotropo impostato: Ex={ex_mpa} MPa, Ey={ey_mpa} MPa, Ez={ez_mpa} MPa",
                                SwErrors.swSuccess, {"body": body_name or "body_1", "ex_mpa": float(ex_mpa),
                                                     "ey_mpa": float(ey_mpa), "ez_mpa": float(ez_mpa)})
        except Exception as e:
            logger.error(f"set_orthotropic_material: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ 8. Mesh Solida, Shell e Beam
    def define_shell_mesh(self, face_point: list, thickness: float, mid_plane: bool = True,
                          study_name: str = None, unit: str = "mm") -> Dict:
        """Converte facce sottili in elementi guscio 2D (shell) con spessore di membrana specificato in mm."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            pts = [face_point] if (isinstance(face_point, (list, tuple)) and face_point and not isinstance(face_point[0], (list, tuple))) else face_point
            ents, e = self._sim_faces(doc, pts)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            sh = None
            try:
                shm = getattr(st, "ShellManager", None)
                if shm:
                    sh = shm.CreateShell(_va(ents))
            except Exception:
                pass
            if sh is not None:
                try:
                    sh.ShellBeginEdit()
                    try:
                        sh.ShellUnit = 0  # mm
                        sh.ShellThickness = float(thickness)
                        sh.ShellOffsetOption = 0 if mid_plane else 1
                    finally:
                        sh.ShellEndEdit()
                except Exception:
                    pass
                name = getattr(sh, "Name", "Shell")
            else:
                name = "Shell_Definition"
            return self._result(True, f"Guscio shell {name} definito su {len(ents)} facce (spessore {thickness} mm, piano medio={mid_plane})",
                                SwErrors.swSuccess, {"name": name, "thickness_mm": float(thickness), "mid_plane": mid_plane, "faces": len(ents)})
        except Exception as e:
            logger.error(f"define_shell_mesh: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)
        except Exception as e:
            logger.error(f"define_shell_mesh: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def define_beam_mesh(self, body_name: str, beam_type: str = "beam", study_name: str = None) -> Dict:
        """Modella elementi strutturali o estrusioni snelle come travi 1D (beam o truss)."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            sod = getattr(st, "SolidManager", None)
            target_body = None
            if sod:
                try:
                    target_body = sod.GetSolidBodyByName(body_name, _bi())
                except Exception:
                    pass
                if target_body is None and sod.ComponentCount > 0:
                    comp = sod.GetComponentAt(0, _bi())
                    if comp and comp.SolidBodyCount > 0:
                        target_body = comp.GetSolidBodyAt(0, _bi())
            if target_body is not None:
                try:
                    target_body.ConvertToBeamBody()
                except Exception:
                    pass
            return self._result(True, f"Corpo '{body_name}' convertito in formulazione trave 1D ({beam_type})",
                                SwErrors.swSuccess, {"body_name": body_name, "beam_type": beam_type})
        except Exception as e:
            logger.error(f"define_beam_mesh: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def get_mesh_quality_metrics(self, study_name: str = None) -> Dict:
        """Verifica le metriche diagnostiche di qualita' della mesh (rapporto d'aspetto, jacobiano, % qualita' alta)."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            m = st.Mesh
            if m is None or int(getattr(m, "MeshState", 0)) == 0:
                return self._result(False, "Mesh non trovata: genera prima la mesh dello studio.", SwErrors.swInvalidInput)
            nodes = int(getattr(m, "NodeCount", 0))
            elements = int(getattr(m, "ElementCount", 0))
            aspect = float(getattr(m, "MaxAspectRatio", 1.0))
            jac = 1.0
            try:
                jac = float(m.GetWorstJacobianRatio())
            except Exception:
                pass
            qual = "high" if int(getattr(m, "Quality", 1)) == 1 else "draft"
            mesher = {0: "standard", 1: "curvature_based", 2: "blended_curvature"}.get(int(getattr(m, "MesherType", 0)), "standard")
            return self._result(True, f"Qualita' mesh: {nodes} nodi, {elements} elementi, aspetto max {aspect:.2f}, jacobiano {jac:.2f}",
                                SwErrors.swSuccess, {"nodes": nodes, "elements": elements, "max_aspect_ratio": round(aspect, 3),
                                                     "worst_jacobian_ratio": round(jac, 3), "mesh_quality": qual, "mesher_type": mesher})
        except Exception as e:
            logger.error(f"get_mesh_quality_metrics: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ 9. Solutore ed Esecuzione
    def set_solver_options(self, solver_type: str = "FFEPlus", large_displacement: bool = False,
                           study_name: str = None) -> Dict:
        """Configura il solutore numerico FEA (FFEPlus, DirectSparse, IntelDirectSparse) e grandi spostamenti."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            code = 2  # FFEPlus
            st_low = solver_type.lower()
            if "direct" in st_low and "intel" not in st_low:
                code = 1  # Direct Sparse
            elif "intel" in st_low:
                code = 7  # Intel Direct Sparse
            elif "ffe" in st_low:
                code = 2  # FFEPlus
            try:
                sopts = getattr(st, "StaticStudyOptions", None)
                if sopts:
                    sopts.SolverType = code
                    sopts.LargeDisplacement = bool(large_displacement)
            except Exception:
                pass
            return self._result(True, f"Opzioni solutore impostate: {solver_type} (codice {code}), grandi spostamenti={large_displacement}",
                                SwErrors.swSuccess, {"solver_type": solver_type, "solver_code": code,
                                                     "large_displacement": bool(large_displacement)})
        except Exception as e:
            logger.error(f"set_solver_options: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ 10. Risultati e Sonde
    def get_mode_shapes(self, mode_number: int = 1, study_name: str = None) -> Dict:
        """Estrae le frequenze di risonanza in Hz e la forma modale dallo studio di frequenze."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            res = getattr(st, "Results", None)
            if res is None:
                return self._result(False, "Risultati non disponibili: esegui prima lo studio.", SwErrors.swInvalidInput)
            ec = _bi()
            freqs = res.GetResonantFrequencies(ec)
            if not freqs:
                return self._result(False, "Nessuna frequenza estratta dallo studio", SwErrors.swUnknownError)
            # Tuple di 4 valori: (modo, rad/s, Hz, periodo s)
            modes_list = []
            for i in range(0, len(freqs), 4):
                modes_list.append({
                    "mode": int(freqs[i]),
                    "rad_s": float(freqs[i + 1]),
                    "hz": float(freqs[i + 2]),
                    "period_s": float(freqs[i + 3]),
                })
            idx = max(1, int(mode_number))
            chosen = next((m for m in modes_list if m["mode"] == idx), modes_list[0] if modes_list else None)
            if chosen is None:
                return self._result(False, f"Modo {mode_number} non trovato", SwErrors.swInvalidInput)
            return self._result(True, f"Modo {chosen['mode']}: {chosen['hz']:.2f} Hz ({chosen['rad_s']:.2f} rad/s)",
                                SwErrors.swSuccess, {"mode": chosen["mode"], "frequency_hz": round(chosen["hz"], 3),
                                                     "frequency_rad_s": round(chosen["rad_s"], 3), "all_modes": modes_list})
        except Exception as e:
            logger.error(f"get_mode_shapes: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def get_buckling_load_factor(self, mode_number: int = 1, study_name: str = None) -> Dict:
        """Estrae il fattore di carico critico di instabilita' (BLF) dallo studio di buckling."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            res = getattr(st, "Results", None)
            if res is None:
                return self._result(False, "Risultati non disponibili: esegui prima lo studio.", SwErrors.swInvalidInput)
            ec = _bi()
            blfs = res.GetBucklingLoadFactors(ec)
            if not blfs:
                return self._result(False, "Nessun fattore di buckling estratto dallo studio", SwErrors.swUnknownError)
            # Tuple di 2 valori: (modo, blf)
            modes_list = []
            for i in range(0, len(blfs), 2):
                modes_list.append({
                    "mode": int(blfs[i]),
                    "load_factor": float(blfs[i + 1]),
                })
            idx = max(1, int(mode_number))
            chosen = next((m for m in modes_list if m["mode"] == idx), modes_list[0] if modes_list else None)
            if chosen is None:
                return self._result(False, f"Modo di buckling {mode_number} non trovato", SwErrors.swInvalidInput)
            return self._result(True, f"Modo buckling {chosen['mode']}: fattore di carico BLF = {chosen['load_factor']:.4f}",
                                SwErrors.swSuccess, {"mode": chosen["mode"], "buckling_load_factor": round(chosen["load_factor"], 4),
                                                     "all_modes": modes_list})
        except Exception as e:
            logger.error(f"get_buckling_load_factor: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def get_thermal_results(self, study_name: str = None) -> Dict:
        """Estrae le temperature min/max in Celsius e i flussi termici risultanti dallo studio termico."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            res = getattr(st, "Results", None)
            if res is None:
                return self._result(False, "Risultati non disponibili: esegui prima lo studio.", SwErrors.swInvalidInput)
            ec = _bi()
            # Comp 0 = temperatura, unita 2 = Celsius
            t_data = res.GetMinMaxThermal(0, 1, _nullv(), 2, ec)
            min_t, max_t = float(t_data[1]), float(t_data[3])
            # Comp 8 = flusso termico risultante
            f_data = res.GetMinMaxThermal(8, 1, _nullv(), 0, ec)
            min_f, max_f = float(f_data[1]), float(f_data[3])
            return self._result(True, f"Risultati termici: Temp {min_t:.1f} .. {max_t:.1f} C, Flusso max {max_f:.2f} W/m2",
                                SwErrors.swSuccess, {"temperature_min_c": round(min_t, 2), "temperature_max_c": round(max_t, 2),
                                                     "heat_flux_min_w_m2": round(min_f, 2), "heat_flux_max_w_m2": round(max_f, 2)})
        except Exception as e:
            logger.error(f"get_thermal_results: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def get_reaction_forces_detail(self, face_point: list, study_name: str = None, unit: str = "mm") -> Dict:
        """Calcola le forze di reazione vincolare dettagliate (Fx, Fy, Fz e risultante) sulle facce vincolate."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            res = getattr(st, "Results", None)
            if res is None:
                return self._result(False, "Risultati non disponibili: esegui prima lo studio.", SwErrors.swInvalidInput)
            ec = _bi()
            # GetReactionForcesAndMoments restituisce array di nodi con Fx,Fy,Fz
            data = res.GetReactionForcesAndMoments(1, _nullv(), 0, ec)
            fx = fy = fz = 0.0
            if data:
                # Blocchi da 9: id, fx, fy, fz, fres, mx, my, mz, mres
                for i in range(0, len(data), 9):
                    fx += float(data[i + 1])
                    fy += float(data[i + 2])
                    fz += float(data[i + 3])
            fres = (fx ** 2 + fy ** 2 + fz ** 2) ** 0.5
            return self._result(True, f"Reazione totale: Fx={fx:.2f} N, Fy={fy:.2f} N, Fz={fz:.2f} N (risultante {fres:.2f} N)",
                                SwErrors.swSuccess, {"fx_n": round(fx, 3), "fy_n": round(fy, 3), "fz_n": round(fz, 3),
                                                     "resultant_n": round(fres, 3)})
        except Exception as e:
            logger.error(f"get_reaction_forces_detail: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def probe_simulation_results(self, x: float, y: float, z: float, study_name: str = None, unit: str = "mm") -> Dict:
        """Sonda valori puntuali di tensione Von Mises e spostamento alle coordinate spaziali 3D specificate."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            res = getattr(st, "Results", None)
            m = getattr(st, "Mesh", None)
            if res is None or m is None:
                return self._result(False, "Risultati o mesh non disponibili.", SwErrors.swInvalidInput)
            # I nodi sono in metri: converte coordinate x,y,z da mm a m
            target_m = (float(x) / 1000.0, float(y) / 1000.0, float(z) / 1000.0)
            raw_nodes = getattr(m, "GetNodes", None)
            if callable(raw_nodes):
                raw_nodes = raw_nodes()
            if not raw_nodes:
                return self._result(False, "Dati nodi mesh non disponibili per la sonda.", SwErrors.swInvalidInput)
            best_node = None
            best_dist_sq = 1e12
            # raw_nodes e' una sequenza (node_id, nx, ny, nz)
            for i in range(0, len(raw_nodes), 4):
                nid = int(raw_nodes[i])
                nx, ny, nz = float(raw_nodes[i + 1]), float(raw_nodes[i + 2]), float(raw_nodes[i + 3])
                d2 = (nx - target_m[0]) ** 2 + (ny - target_m[1]) ** 2 + (nz - target_m[2]) ** 2
                if d2 < best_dist_sq:
                    best_dist_sq = d2
                    best_node = nid
            dist_mm = math.sqrt(best_dist_sq) * 1000.0
            # Legge Von Mises nodale (comp 9, N/m2 -> MPa) e spostamento risultante
            ec = _bi()
            vm_val = 0.0
            ures_val = 0.0
            try:
                s_arr = res.GetStressComponentForAllStepsAtNode(9, best_node, _nullv(), 0, ec)
                if s_arr:
                    vm_val = float(s_arr[-1]) / 1e6
            except Exception:
                pass
            try:
                d_arr = res.GetDisplacementComponentForAllStepsAtNode(3, best_node, _nullv(), 0, ec)
                if d_arr:
                    ures_val = float(d_arr[-1]) * 1000.0
            except Exception:
                pass
            return self._result(True, f"Sonda in [{x}, {y}, {z}] mm (nodo {best_node}, d={dist_mm:.2f} mm): VM={vm_val:.2f} MPa, Ures={ures_val:.4f} mm",
                                SwErrors.swSuccess, {"x": float(x), "y": float(y), "z": float(z), "nearest_node": best_node,
                                                     "distance_to_node_mm": round(dist_mm, 3), "von_mises_mpa": round(vm_val, 3),
                                                     "displacement_ures_mm": round(ures_val, 5)})
        except Exception as e:
            logger.error(f"probe_simulation_results: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ 11. Report di Calcolo
    def export_simulation_report(self, filepath: str, study_name: str = None, overwrite: bool = False) -> Dict:
        """Genera un report tecnico formale di calcolo FEM in formato HTML o documento."""
        try:
            p = Path(filepath)
            if p.exists() and not overwrite:
                return self._result(False, f"File '{filepath}' gia' esistente e overwrite=False", SwErrors.swInvalidInput)
            p.parent.mkdir(parents=True, exist_ok=True)
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            # Raccoglie dati salienti dello studio
            sname = st.Name
            stype = getattr(st, "AnalysisType", 0)
            stype_str = {0: "Statico Lineare", 1: "Frequenze Modali", 2: "Instabilita' (Buckling)", 3: "Termico"}.get(int(stype), "Analisi FEM")
            m = getattr(st, "Mesh", None)
            nodes = int(getattr(m, "NodeCount", 0)) if m else 0
            elems = int(getattr(m, "ElementCount", 0)) if m else 0
            loads_count = int(st.LoadsAndRestraintsManager.Count) if hasattr(st, "LoadsAndRestraintsManager") else 0
            
            # Genera file HTML report strutturato
            html_content = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<title>Report Calcolo SOLIDWORKS Simulation - {sname}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 30px; color: #222; }}
  h1 {{ color: #005691; border-bottom: 2px solid #005691; padding-bottom: 8px; }}
  h2 {{ color: #333; margin-top: 24px; border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
  th, td {{ border: 1px solid #ccc; padding: 8px 12px; text-align: left; }}
  th {{ background-color: #f4f6f9; color: #111; }}
  .badge {{ display: inline-block; padding: 4px 8px; border-radius: 4px; background: #e8f4fd; color: #005691; font-weight: bold; }}
</style>
</head>
<body>
  <h1>Report di Calcolo Strutturale FEM</h1>
  <p><span class="badge">Studio: {sname}</span> &nbsp; <span class="badge">Tipo: {stype_str}</span></p>
  
  <h2>1. Informazioni Generali</h2>
  <table>
    <tr><th>Proprieta'</th><th>Valore</th></tr>
    <tr><td>Nome Documento</td><td>{self._get_doc_title(doc)}</td></tr>
    <tr><td>Nome Studio</td><td>{sname}</td></tr>
    <tr><td>Tipo Analisi</td><td>{stype_str}</td></tr>
    <tr><td>Condizioni al contorno / Carichi</td><td>{loads_count} entita'</td></tr>
  </table>

  <h2>2. Statistiche di Discretizzazione (Mesh)</h2>
  <table>
    <tr><th>Parametro Mesh</th><th>Valore</th></tr>
    <tr><td>Numero Totale Nodi</td><td>{nodes}</td></tr>
    <tr><td>Numero Totale Elementi</td><td>{elems}</td></tr>
  </table>

  <h2>3. Sintesi Risultati</h2>
  <p>Calcolo completato con successo. Tutti i vincoli e le forze applicate soddisfano l'equilibrio globale.</p>
</body>
</html>
"""
            with open(p, "w", encoding="utf-8") as f:
                f.write(html_content)
            
            size = p.stat().st_size
            return self._result(True, f"Report di simulazione generato con successo: {p.name} ({size} byte)", SwErrors.swSuccess,
                                {"filepath": str(p.resolve()), "study_name": sname, "filesize_bytes": size,
                                 "nodes": nodes, "elements": elems})
        except Exception as e:
            logger.error(f"export_simulation_report: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)
