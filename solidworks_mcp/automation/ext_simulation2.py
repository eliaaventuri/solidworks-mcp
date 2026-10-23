"""
Lotto SIMULAZIONE 2: implementazione FEA avanzata (Simulation2Operations mixin).
Studi speciali (frequenze, buckling, termico, drop test, fatica, topologia, dinamico), vincoli e carichi avanzati,
connettori, condizioni termiche, contatti speciali, materiale ortotropo, shell/travi, solutore, sonde e report.

Regola: ogni tool restituisce successo SOLO se SolidWorks ha creato/modificato davvero l'oggetto; i valori nel risultato
sono RILETTI da SolidWorks dopo la modifica (mai l'eco dei parametri). Lunghezze dei tool in mm, come in simulation.py.

Trappole misurate (SW 2026 SP4.1, late binding, 2026-10-23; dettagli in STATO_STORICO.md):
 - `XxxBeginEdit()` e' un METODO senza ritorno: va chiamato con le parentesi (senza, pywin32 restituisce il metodo e NON lo
   esegue: le proprieta' impostate dopo vengono ignorate in silenzio). `XxxEndEdit` invece restituisce un codice: si legge
   come proprieta' (0 = ok).
 - `ShellManager.CreateShell` va forzato a metodo (`_FlagAsMethod`): restituisce un CODICE (2 = faccia di un solido, la
   mesh dello studio non e' a gusci), non l'oggetto shell.
 - Uno studio statico senza nessun CARICO non parte (RunAnalysis 30 "LBC non validi"), anche con soli vincoli.
 - Spostamento imposto non nullo: `AddPrescribedDisplacement(6 valori, unita', facce, piano, err)` crea il vincolo ma i
   valori riletti sono spazzatura e l'analisi li ignora; `SetTranslationComponentsValues` di un vincolo salva i flag ma
   lascia i valori a 0. Nessuna via API funzionante: il tool lo dichiara.
 - Supporto elastico: Unit 0 (SI), StiffnessType 0 = distribuita in N/m per m2 (= N/m3): misurato UX = F/(k*A) esatto.
 - Molla tra facce piane: StiffnessType 0 si comporta come rigidezza TOTALE (N/m), 1 come distribuita (misurato: con 1
   lo spostamento era F/(k*A)). Il contrario dell'enum swsStiffnessType_e.
 - Convezione/irraggiamento: Unit 0 = SI, temperature in KELVIN; irraggiamento richiede ViewFactor (EndEdit 7 se 0).
   Misurati: convezione e potenza termica entro 0,02 % dalla soluzione 1D, irraggiamento entro 0,001 C.
 - Temperatura in uno studio statico: va applicata al CORPO (sulle sole facce l'interno resta alla temperatura di
   riferimento); deformazione = alfa * (T - T0) con T0 = GetZeroStrainTemperature (298 K di default).
 - Centrifuga: una sola per studio (errore 4); asse = spigolo rettilineo o faccia cilindrica. Misurata: R = m w^2 r.
 - Bullone: testa e dado sono SPIGOLI CIRCOLARI (errore 6 se no). Gli spigoli di un foro tagliato 'through_all_both' sul
   piano di schizzo che coincide con una faccia diventano B-spline (Identity 3006): non servono come testa/dado.
 - Saldatura a punti: le posizioni devono essere VERTICI o punti di riferimento (errore 7); il RefPoint come feature
   fa sollevare un'eccezione al server: si usano vertici.
 - Parete virtuale: il bersaglio e' un PIANO (feature RefPlane), errore 5 con una faccia.
 - I corpi di simulazione (`GetSolidBodyAt`) restano validi solo tenendo vivi manager e componente (`_sim_bodies`).
 - `Results.GetStressComponentForAllStepsAtNode` / `GetDisplacementComponentForAllStepsAtNode` falliscono (err 4): per
   valori nodali si usano `GetStressForEntities2` / `GetDisplacementForEntities` sul corpo (coppie nodo, valore).
 - Topologia (tipo 13) non creabile con questa licenza (errore 3).
"""

import math
import html
import logging
import traceback
from typing import Dict, List, Optional
from pathlib import Path

import pythoncom
from win32com.client import VARIANT

from ..constants import SwErrors
from .simulation import _va, _bi, _br, _bb, _nullv, _dbl

logger = logging.getLogger(__name__)

_SIGMA = 5.670374419e-8
_K0 = 273.15

_STUDY_ERR = {1: "nessun corpo solido", 2: "nome gia' usato o non valido", 3: "tipo di studio non disponibile (licenza o modulo)"}
_BOLT_ERR = {4: "seleziona le entita'", 6: "testa e dado devono essere SPIGOLI CIRCOLARI", 9: "testa e dado non concentrici",
             13: "testa e dado sono la stessa entita'", 14: "serve un assieme", 19: "diametro troppo grande"}
_SPOT_ERR = {5: "serve un assieme", 6: "seleziona due facce", 7: "le posizioni devono essere vertici o punti di riferimento",
             8: "facce non parallele", 9: "facce a contatto", 10: "distanza tra le facce troppo grande"}
_CONTACT_ERR = {1: "array non valido", 2: "nessuna entita'", 3: "tipo non valido", 5: "serve UN piano bersaglio",
                6: "solo facce", 9: "le facce devono toccarsi", 11: "l'accoppiamento forzato richiede interferenza",
                12: "coppia di contatto non creabile"}
_RESTR_ERR = {1: "seleziona facce, spigoli o vertici", 2: "serve una faccia piana", 3: "serve una faccia cilindrica",
              9: "tipo di studio non valido", 14: "vincolo non applicabile"}
_CF_ERR = {1: "serve uno spigolo-asse o una faccia cilindrica", 2: "faccia non cilindrica", 3: "spigolo non rettilineo",
           4: "c'e' gia' un carico centrifugo in questo studio", 5: "tipo di studio non valido"}
_SHELL_ERR = {1: "gusci non ammessi in questo studio", 2: "la mesh dello studio e' solida: i gusci si definiscono su corpi "
              "superficie o lamiera, non sulle facce di un solido", 3: "array vuoto", 4: "array non valido",
              5: "solo facce", 6: "faccia gia' definita come guscio"}


def _pts(p) -> list:
    """Un punto [x,y,z] o una lista di punti -> lista di punti."""
    if isinstance(p, (list, tuple)) and p and not isinstance(p[0], (list, tuple)):
        return [p]
    return list(p or [])


class Simulation2Operations:
    """Operazioni FEA estese (Simulation2). Richiede SolidWorksAutomation e SimulationOperations."""

    # ------------------------------------------------------------------ helper
    def _s2_err(self, msg: str, code=SwErrors.swFeatureError, data: Dict = None) -> Dict:
        return self._result(False, msg, code, data)

    def _s2_last_name(self, lm, before: int) -> Optional[str]:
        """Nome dell'ultimo carico/vincolo/connettore aggiunto (alcuni oggetti connettore non espongono Name)."""
        try:
            n = int(lm.Count)
            if n > before:
                return lm.GetLoadsAndRestraints(n - 1, _bi()).Name
        except Exception:
            pass
        return None

    def _s2_edges(self, doc, points) -> (list, Optional[str]):
        out = []
        for p in _pts(points):
            e, _d = self._find_entity(doc, "edge", [float(c) / 1000.0 for c in p], 1e-4)
            if e is None:
                return [], f"Nessuno spigolo entro 0,1 mm dal punto {list(p)} (il punto deve stare SULLO spigolo)"
            out.append(e)
        return out, None

    def _s2_plane(self, doc, plane: str):
        """Piano standard (front/top/right in ogni lingua) o feature piano per nome."""
        f = self._std_ref_feature(doc, plane)
        if f is None:
            try:
                f = doc.FeatureByName(plane)
            except Exception:
                f = None
        return f

    def _s2_is_cyl(self, face) -> bool:
        try:
            return bool(self._com(self._com(face, "GetSurface"), "IsCylinder"))
        except Exception:
            return False

    def _s2_cyl_radius_mm(self, face) -> Optional[float]:
        try:
            p = self._com(self._com(face, "GetSurface"), "CylinderParams")
            return float(p[6]) * 1000.0
        except Exception:
            return None

    def _s2_create_study(self, name: str, atype: int, label: str, subtype: int = None):
        """-> (studio, studymanager, None) oppure (None, None, errore)."""
        cw, err = self._sim_cw()
        if err:
            return None, None, err
        doc, err = self.get_active_doc()
        if err:
            return None, None, err
        if not self._get_doc_path(doc):
            return None, None, self._s2_err("Salva prima il documento (serve per la cartella dei risultati).", SwErrors.swInvalidInput)
        sm = cw.ActiveDoc.StudyManager
        e = _bi()
        st = sm.CreateNewStudy3(name, atype, subtype, e) if subtype is not None else sm.CreateNewStudy2(name, atype, e)
        if st is None or int(e.value) != 0:
            return None, None, self._s2_err(f"Creazione studio {label} '{name}' fallita: errore {e.value} "
                                            f"({_STUDY_ERR.get(int(e.value), '?')})", SwErrors.swUnknownError)
        if int(st.AnalysisType) != atype:
            return None, None, self._s2_err(f"Studio '{name}' creato con tipo {st.AnalysisType} invece di {atype}", SwErrors.swUnknownError)
        for i in range(int(sm.StudyCount)):
            if sm.GetStudy(i).Name == name:
                sm.ActiveStudy = i
        return st, sm, None

    # ------------------------------------------------------------------ 1. Studi FEA speciali
    def create_frequency_study(self, study_name: str = "Frequency 1", num_frequencies: int = 5) -> Dict:
        """Crea uno studio di frequenze modali; il numero di modi e' riletto da SolidWorks."""
        try:
            st, sm, err = self._s2_create_study(study_name, 1, "frequenze")
            if err:
                return err
            fo = st.FrequencyStudyOptions
            fo.NoOfFrequencies = int(num_frequencies)
            count = int(fo.NoOfFrequencies)
            if count != int(num_frequencies):
                return self._s2_err(f"Studio '{study_name}' creato ma il numero di modi resta {count}", SwErrors.swUnknownError)
            return self._result(True, f"Studio di frequenze '{study_name}' creato con {count} modi", SwErrors.swSuccess,
                                {"name": study_name, "type": "frequency", "analysis_type": int(st.AnalysisType),
                                 "num_frequencies": count})
        except Exception as e:
            logger.error(f"create_frequency_study: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def create_buckling_study(self, study_name: str = "Buckling 1", num_modes: int = 4) -> Dict:
        """Crea uno studio di instabilita' lineare (buckling); il numero di modi e' riletto da SolidWorks."""
        try:
            st, sm, err = self._s2_create_study(study_name, 2, "buckling")
            if err:
                return err
            bo = st.BucklingStudyOptions
            bo.BucklingModes = int(num_modes)
            modes = int(bo.BucklingModes)
            if modes != int(num_modes):
                return self._s2_err(f"Studio '{study_name}' creato ma il numero di modi resta {modes}", SwErrors.swUnknownError)
            return self._result(True, f"Studio di buckling '{study_name}' creato con {modes} modi", SwErrors.swSuccess,
                                {"name": study_name, "type": "buckling", "analysis_type": int(st.AnalysisType), "num_modes": modes})
        except Exception as e:
            logger.error(f"create_buckling_study: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def create_thermal_study(self, study_name: str = "Thermal 1", transient: bool = False,
                             total_time_seconds: float = 60.0) -> Dict:
        """Crea uno studio termico stazionario o transitorio (tipo di soluzione e durata riletti da SolidWorks)."""
        try:
            st, sm, err = self._s2_create_study(study_name, 3, "termico")
            if err:
                return err
            to = st.ThermalStudyOptions
            to.SolutionType = 0 if transient else 1      # 0 transitorio, 1 stazionario
            sol = int(to.SolutionType)
            data = {"name": study_name, "type": "thermal", "analysis_type": int(st.AnalysisType), "transient": sol == 0}
            if transient:
                to.TotalTime = float(total_time_seconds)
                data["total_time_seconds"] = float(to.TotalTime)
            if (sol == 0) != bool(transient):
                return self._s2_err(f"Studio '{study_name}' creato ma il tipo di soluzione resta {sol}", SwErrors.swUnknownError, data)
            return self._result(True, f"Studio termico {'transitorio' if transient else 'stazionario'} '{study_name}' creato",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"create_thermal_study: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def create_drop_test_study(self, study_name: str = "Drop Test 1", drop_height: float = 1000.0,
                               gravity_plane: str = "top") -> Dict:
        """Crea uno studio di caduta: altezza (mm, dal punto piu' basso) e gravita' normale a `gravity_plane`."""
        try:
            st, sm, err = self._s2_create_study(study_name, 6, "drop test")
            if err:
                return err
            doc, _ = self.get_active_doc()
            plane = self._s2_plane(doc, gravity_plane)
            if plane is None:
                return self._s2_err(f"Studio creato, ma piano di gravita' '{gravity_plane}' non trovato", SwErrors.swInvalidInput)
            ds = st.DropTestSetup
            ds.DropTestSetupBeginEdit()
            ds.DropType = 0                 # altezza di caduta
            ds.DropHeightType = 1           # dal punto piu' basso
            ds.DropHeightUnit = 0           # mm
            ds.DropHeight = float(drop_height)
            ds.SetEntityForGravityDirection(plane)
            rc = int(ds.DropTestSetupEndEdit)
            h = float(ds.DropHeight)
            data = {"name": study_name, "type": "drop_test", "analysis_type": int(st.AnalysisType),
                    "drop_height_mm": h, "end_edit": rc}
            if rc != 0 or abs(h - float(drop_height)) > 1e-6:
                return self._s2_err(f"Studio '{study_name}' creato ma impostazione caduta rifiutata (codice {rc}, altezza {h})",
                                    SwErrors.swUnknownError, data)
            return self._result(True, f"Studio drop test '{study_name}' creato (altezza {h} mm)", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"create_drop_test_study: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def create_fatigue_study(self, study_name: str = "Fatigue 1", event_cycles: int = 100000,
                             static_study: str = None) -> Dict:
        """Crea uno studio di fatica. Con `static_study` aggiunge l'evento ad ampiezza costante (event_cycles cicli)
        legato a quello studio statico; senza, lo studio resta senza eventi (va detto all'utente)."""
        try:
            st, sm, err = self._s2_create_study(study_name, 7, "fatica", 0)      # 0 = ampiezza costante
            if err:
                return err
            data = {"name": study_name, "type": "fatigue", "analysis_type": int(st.AnalysisType), "events": 0}
            if not static_study:
                return self._result(True, f"Studio di fatica '{study_name}' creato SENZA eventi (nessuno studio statico indicato)",
                                    SwErrors.swSuccess, data)
            fo = st.FatigueStudyOptions
            ec = _bi()
            ev = fo.AddFatigueEventForConstantAmplitude(static_study, 1.0, 1, ec)
            if ev is None:
                return self._s2_err(f"Studio creato, evento di fatica rifiutato (errore {ec.value}; lo studio statico "
                                    f"'{static_study}' esiste?)", SwErrors.swFeatureError, data)
            ev.FatigueEventBeginEdit()
            ev.Cycles = float(event_cycles)
            rc = int(ev.FatigueEventEndEdit)
            data.update({"events": int(fo.LoadingEventCount), "event_name": ev.Name, "cycles": float(ev.Cycles), "end_edit": rc})
            if rc != 0 or abs(data["cycles"] - float(event_cycles)) > 0.5:
                return self._s2_err(f"Evento di fatica creato ma cicli non impostati (codice {rc}, cicli {data['cycles']})",
                                    SwErrors.swFeatureError, data)
            return self._result(True, f"Studio di fatica '{study_name}' con evento {ev.Name}: {data['cycles']:.0f} cicli da '{static_study}'",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"create_fatigue_study: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def create_topology_study(self, study_name: str = "Topology 1", target_mass_percent: float = 50.0) -> Dict:
        """Crea uno studio di ottimizzazione topologica (tipo 13). Richiede la licenza adatta: se SolidWorks lo rifiuta
        il tool fallisce (nessun ripiego su altri tipi di studio). L'obiettivo di massa non e' impostabile via API."""
        try:
            st, sm, err = self._s2_create_study(study_name, 13, "topologia")
            if err:
                return err
            return self._result(True, f"Studio di ottimizzazione topologica '{study_name}' creato (obiettivo di massa da "
                                       f"impostare in SolidWorks: l'API non lo espone)", SwErrors.swSuccess,
                                {"name": study_name, "type": "topology", "analysis_type": int(st.AnalysisType),
                                 "target_mass_percent_set": False})
        except Exception as e:
            logger.error(f"create_topology_study: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def create_linear_dynamic_study(self, study_name: str = "Dynamic 1", dynamic_type: str = "harmonic") -> Dict:
        """Crea uno studio dinamico lineare: harmonic | random_vibration | time_history (modale) | response_spectrum."""
        try:
            sub = {"time_history": 0, "modal_time_history": 0, "transient": 0, "harmonic": 1, "armonica": 1,
                   "random_vibration": 2, "random": 2, "response_spectrum": 3}.get(str(dynamic_type).lower())
            if sub is None:
                return self._s2_err("dynamic_type: harmonic | random_vibration | time_history | response_spectrum", SwErrors.swInvalidInput)
            st, sm, err = self._s2_create_study(study_name, 8, "dinamico lineare", sub)
            if err:
                return err
            return self._result(True, f"Studio dinamico lineare ({dynamic_type}) '{study_name}' creato", SwErrors.swSuccess,
                                {"name": study_name, "type": "linear_dynamic", "analysis_type": int(st.AnalysisType),
                                 "dynamic_type": dynamic_type, "subtype": sub})
        except Exception as e:
            logger.error(f"create_linear_dynamic_study: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ 2. Vincoli e supporti
    def add_elastic_support(self, face_point: list, stiffness: float, shear_stiffness: float = None,
                            study_name: str = None) -> Dict:
        """Supporto elastico (fondazione) su facce: rigidezza normale distribuita in N/mm3 (= N/mm per mm2 di faccia);
        `shear_stiffness` tangenziale, default uguale alla normale."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            ents, e = self._sim_faces(doc, _pts(face_point))
            if e:
                return self._s2_err(e, SwErrors.swSelectionError)
            lm = st.LoadsAndRestraintsManager
            n0 = int(lm.Count)
            ec = _bi()
            c = lm.AddElasticConnector(_va(ents), ec)
            if c is None:
                return self._s2_err(f"AddElasticConnector fallito (errore {ec.value})")
            kn = float(stiffness) * 1e9                       # N/mm3 -> N/m3
            ks = float(stiffness if shear_stiffness is None else shear_stiffness) * 1e9
            c.ElasticConnectorBeginEdit()
            c.Unit = 0
            c.StiffnessType = 0                               # distribuita
            c.NormalStiffnessValue = kn
            c.ShearStiffnessValue = ks
            rc = int(c.ElasticConnectorEndEdit)
            rn, rs = float(c.NormalStiffnessValue) / 1e9, float(c.ShearStiffnessValue) / 1e9
            data = {"name": self._s2_last_name(lm, n0), "normal_stiffness_n_mm3": rn, "shear_stiffness_n_mm3": rs,
                    "faces": len(ents), "end_edit": rc}
            if rc != 0 or abs(rn * 1e9 - kn) > 1e-6 * kn:
                return self._s2_err(f"Supporto elastico creato ma rigidezza rifiutata (codice {rc})", data=data)
            return self._result(True, f"Supporto elastico {data['name']} su {len(ents)} facce: k normale {rn} N/mm3, "
                                      f"tangenziale {rs} N/mm3", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"add_elastic_support: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_prescribed_displacement(self, face_point: list, displacement_mm: float, study_name: str = None) -> Dict:
        """Spostamento imposto NON NULLO: non realizzabile via API (SolidWorks crea il vincolo ma ignora i valori, misurato).
        Con displacement_mm = 0 crea un vincolo fisso sulle facce. Per spostamenti non nulli: impostarli a mano in SolidWorks."""
        try:
            if abs(float(displacement_mm)) > 0:
                return self._s2_err("Spostamento imposto non nullo non realizzabile via API di SolidWorks Simulation: "
                                    "il vincolo viene creato ma i valori sono ignorati dall'analisi (misurato). "
                                    "Impostarlo a mano in SolidWorks (Vincolo > Usa geometria di riferimento).",
                                    SwErrors.swInvalidInput, {"limitation": "prescribed_displacement_values_ignored"})
            return self.add_restraint(kind="fixed", faces=_pts(face_point), study=study_name)
        except Exception as e:
            logger.error(f"add_prescribed_displacement: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_cylindrical_restraint(self, cylinder_face_point: list, radial_free: bool = False,
                                  axial_free: bool = False, circumferential_free: bool = True,
                                  study_name: str = None) -> Dict:
        """Vincolo su faccia cilindrica con radiale, circonferenziale e assiale bloccati o liberi (flag riletti)."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            ents, e = self._sim_faces(doc, _pts(cylinder_face_point))
            if e:
                return self._s2_err(e, SwErrors.swSelectionError)
            if not all(self._s2_is_cyl(f) for f in ents):
                return self._s2_err("Il punto deve stare su una faccia CILINDRICA", SwErrors.swInvalidInput)
            if radial_free and axial_free and circumferential_free:
                return self._s2_err("Tutte le direzioni libere: nessun vincolo da applicare", SwErrors.swInvalidInput)
            lm = st.LoadsAndRestraintsManager
            ec = _bi()
            r = lm.AddRestraint(7, _va(ents), _nullv(), ec)            # 7 = facce cilindriche
            if r is None:
                return self._s2_err(f"AddRestraint (cilindrico) fallito: errore {ec.value} ({_RESTR_ERR.get(int(ec.value), '?')})")
            want = (not radial_free, not circumferential_free, not axial_free)   # dir1 radiale, dir2 circonf., dir3 assiale
            r.RestraintBeginEdit()
            r.SetTranslationComponentsValues(*want, 0.0, 0.0, 0.0)
            rc = int(r.RestraintEndEdit)
            bb =[VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BOOL, False) for _ in range(3)]
            dd = [_br() for _ in range(3)]
            r.GetTranslationComponentsValues(*bb, *dd)
            got = tuple(bool(b.value) for b in bb)
            data = {"name": r.Name, "restraint_type": int(r.RestraintType), "radial_fixed": got[0],
                    "circumferential_fixed": got[1], "axial_fixed": got[2], "end_edit": rc}
            if rc != 0 or got != want:
                return self._s2_err(f"Vincolo cilindrico creato ma direzioni non impostate (codice {rc}, letti {got})", data=data)
            return self._result(True, f"Vincolo cilindrico {r.Name}: radiale {'bloccato' if got[0] else 'libero'}, "
                                      f"circonferenziale {'bloccato' if got[1] else 'libero'}, assiale {'bloccato' if got[2] else 'libero'}",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"add_cylindrical_restraint: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ 3. Carichi meccanici
    def add_centrifugal_load(self, angular_velocity_rad_s: float, axis_point: list = None, study_name: str = None) -> Dict:
        """Carico centrifugo (rad/s) attorno a un asse: `axis_point` su uno spigolo RETTILINEO o su una faccia cilindrica (mm)."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            if not axis_point:
                return self._s2_err("Serve axis_point: un punto su uno spigolo rettilineo o su una faccia cilindrica (asse)", SwErrors.swInvalidInput)
            pm = [float(c) / 1000.0 for c in _pts(axis_point)[0]]
            ent, _d = self._find_entity(doc, "edge", pm, 1e-4)
            if ent is not None and not bool(ent.GetCurve.IsLine):
                ent = None
            if ent is None:
                f, _d = self._find_entity(doc, "face", pm, 1e-4)
                ent = f if (f is not None and self._s2_is_cyl(f)) else None
            if ent is None:
                return self._s2_err(f"Nessuno spigolo rettilineo o faccia cilindrica nel punto {axis_point}", SwErrors.swSelectionError)
            lm = st.LoadsAndRestraintsManager
            n0 = int(lm.Count)
            ec = _bi()
            c = lm.AddCentrifugalForce(ent, ec)
            if c is None:
                return self._s2_err(f"AddCentrifugalForce fallito: errore {ec.value} ({_CF_ERR.get(int(ec.value), '?')})")
            c.CFForceBeginEdit()
            c.Unit = 0                                                # rad/s
            c.AngularVelocity = float(angular_velocity_rad_s)
            rc = int(c.CFForceEndEdit)
            w = float(c.AngularVelocity)
            data = {"name": self._s2_last_name(lm, n0), "angular_velocity_rad_s": w, "end_edit": rc}
            if rc != 0 or abs(w - float(angular_velocity_rad_s)) > 1e-9:
                return self._s2_err(f"Carico centrifugo creato ma velocita' non impostata (codice {rc}, letta {w})", data=data)
            return self._result(True, f"Carico centrifugo {data['name']}: {w} rad/s", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"add_centrifugal_load: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_thermal_shrinkage_load(self, face_point: list, delta_temperature_c: float, study_name: str = None) -> Dict:
        """Dilatazione/contrazione termica in uno studio statico: porta il CORPO che contiene la faccia indicata a
        T0 + delta (T0 = temperatura di deformazione nulla dello studio, riletta). Deformazione libera = alfa * delta."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            if int(st.AnalysisType) != 0:
                return self._s2_err("Serve uno studio statico", SwErrors.swInvalidInput)
            ents, e = self._sim_faces(doc, _pts(face_point))
            if e:
                return self._s2_err(e, SwErrors.swSelectionError)
            bodies = []
            for f in ents:
                b = f.GetBody
                if all(b is not x for x in bodies):
                    bodies.append(b)
            t0, u0 = _br(), _bi()
            st.StaticStudyOptions.GetZeroStrainTemperature(t0, u0)
            t0c = {0: float(t0.value) - _K0, 2: float(t0.value), 1: (float(t0.value) - 32.0) * 5.0 / 9.0}.get(int(u0.value))
            if t0c is None:
                return self._s2_err(f"Unita' della temperatura di riferimento sconosciuta ({u0.value})", SwErrors.swUnknownError)
            lm = st.LoadsAndRestraintsManager
            ec = _bi()
            t = lm.AddTemperature(_va(bodies), ec)
            if t is None:
                return self._s2_err(f"AddTemperature sul corpo fallito (errore {ec.value})")
            target = t0c + float(delta_temperature_c)
            t.TemperatureBeginEdit()
            t.Unit = 2                                                # gradi C
            t.TemperatureValue = target
            rc = int(t.TemperatureEndEdit)
            val = float(t.TemperatureValue)
            data = {"name": t.Name, "bodies": len(bodies), "zero_strain_temperature_c": round(t0c, 3),
                    "temperature_c": val, "delta_temperature_c": round(val - t0c, 6), "end_edit": rc}
            if rc != 0 or abs(val - target) > 1e-6:
                return self._s2_err(f"Temperatura creata ma valore non impostato (codice {rc}, letto {val})", data=data)
            return self._result(True, f"Carico termico {t.Name}: corpo a {val:.2f} C (delta {data['delta_temperature_c']:+.2f} C "
                                      f"rispetto a {t0c:.2f} C)", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"add_thermal_shrinkage_load: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ 4. Connettori
    def add_bolt_connector(self, head_edge_point: list, nut_edge_point: list, bolt_diameter: float,
                           preload_force_n: float = 0.0, study_name: str = None) -> Dict:
        """Connettore bullone con dado: testa e dado sono SPIGOLI CIRCOLARI concentrici (punti in mm sugli spigoli).
        Diametro gambo in mm e precarico assiale in N, riletti da SolidWorks."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            heads, e1 = self._s2_edges(doc, head_edge_point)
            nuts, e2 = self._s2_edges(doc, nut_edge_point)
            if e1 or e2:
                return self._s2_err(e1 or e2, SwErrors.swSelectionError)
            for nm, ed in (("testa", heads[0]), ("dado", nuts[0])):
                if not bool(ed.GetCurve.IsCircle):
                    return self._s2_err(f"Lo spigolo della {nm} non e' circolare", SwErrors.swInvalidInput)
            lm = st.LoadsAndRestraintsManager
            n0 = int(lm.Count)
            ec = _bi()
            b = lm.AddBoltConnector(0, _va(heads), _va(nuts), ec)
            if b is None:
                return self._s2_err(f"AddBoltConnector fallito: errore {ec.value} ({_BOLT_ERR.get(int(ec.value), '?')})")
            b.BoltConnectorBeginEdit()
            b.BoltUnit = 0
            b.BoltShankDiameterValue = float(bolt_diameter)
            if preload_force_n:
                b.PreLoadForceType = 0
                b.PreLoadForceValue = float(preload_force_n)
            rc = int(b.BoltConnectorEndEdit)
            d, p = float(b.BoltShankDiameterValue), float(b.PreLoadForceValue)
            data = {"name": self._s2_last_name(lm, n0), "bolt_diameter_mm": d, "preload_force_n": p, "end_edit": rc}
            if rc != 0 or abs(d - float(bolt_diameter)) > 1e-9 or abs(p - float(preload_force_n or 0)) > 1e-6:
                if data["name"]:
                    try:
                        lm.DeleteLoadsAndRestraints(data["name"])
                    except Exception:
                        pass
                return self._s2_err(f"Bullone rifiutato alla chiusura della modifica (codice {rc}; 30 = serve un assieme) "
                                    f"o valori non impostati (diametro {d}, precarico {p})", data=data)
            return self._result(True, f"Connettore bullone {data['name']}: gambo {d} mm, precarico {p} N", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"add_bolt_connector: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_pin_connector(self, face1_point: list, face2_point: list, study_name: str = None) -> Dict:
        """Connettore perno tra due facce cilindriche coassiali di corpi/componenti diversi (punti in mm sulle facce)."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            f1, e1 = self._sim_faces(doc, _pts(face1_point))
            f2, e2 = self._sim_faces(doc, _pts(face2_point))
            if e1 or e2:
                return self._s2_err(e1 or e2, SwErrors.swSelectionError)
            if not all(self._s2_is_cyl(f) for f in f1 + f2):
                return self._s2_err("Entrambi i punti devono stare su facce CILINDRICHE", SwErrors.swInvalidInput)
            lm = st.LoadsAndRestraintsManager
            n0 = int(lm.Count)
            ec = _bi()
            p = lm.AddPinConnector(_va(f1), _va(f2), ec)
            if p is None:
                return self._s2_err(f"AddPinConnector fallito (errore {ec.value})")
            p.PinConnectorBeginEdit()
            rc = int(p.PinConnectorEndEdit)
            name = self._s2_last_name(lm, n0)
            data = {"name": name, "radius1_mm": self._s2_cyl_radius_mm(f1[0]), "radius2_mm": self._s2_cyl_radius_mm(f2[0]), "end_edit": rc}
            if rc != 0 or not name:
                return self._s2_err(f"Perno rifiutato (codice {rc}: 6 = facce non coassiali, 7 = raggi diversi)", data=data)
            return self._result(True, f"Connettore perno {name} tra facce di raggio {data['radius1_mm']:.3f} e {data['radius2_mm']:.3f} mm",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"add_pin_connector: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_spring_connector(self, point1: list, point2: list, stiffness_n_mm: float, shear_stiffness_n_mm: float = None,
                             study_name: str = None) -> Dict:
        """Molla tra due facce PIANE parallele (punti in mm): rigidezza TOTALE normale e tangenziale in N/mm."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            f1, e1 = self._sim_faces(doc, _pts(point1))
            f2, e2 = self._sim_faces(doc, _pts(point2))
            if e1 or e2:
                return self._s2_err(e1 or e2, SwErrors.swSelectionError)
            lm = st.LoadsAndRestraintsManager
            n0 = int(lm.Count)
            ec = _bi()
            s = lm.AddSpringConnector(0, _va(f1), _va(f2), ec)            # 0 = facce piane parallele
            if s is None:
                return self._s2_err(f"AddSpringConnector fallito (errore {ec.value}; servono facce piane parallele)")
            kn = float(stiffness_n_mm) * 1000.0
            ks = float(stiffness_n_mm if shear_stiffness_n_mm is None else shear_stiffness_n_mm) * 1000.0
            s.SpringConnectorBeginEdit()
            s.Unit = 0
            s.StiffnessType = 0            # misurato: 0 = rigidezza totale per questo connettore
            s.NormalRadialStiffnessValue = kn
            s.TangentialOrShearStiffnessValue = ks
            rc = int(s.SpringConnectorEndEdit)
            rn, rs = float(s.NormalRadialStiffnessValue) / 1000.0, float(s.TangentialOrShearStiffnessValue) / 1000.0
            data = {"name": self._s2_last_name(lm, n0), "stiffness_n_mm": rn, "shear_stiffness_n_mm": rs, "end_edit": rc}
            if rc != 0 or abs(rn * 1000.0 - kn) > 1e-6 * kn:
                return self._s2_err(f"Molla creata ma rigidezza rifiutata (codice {rc})", data=data)
            return self._result(True, f"Connettore molla {data['name']}: k normale {rn} N/mm, tangenziale {rs} N/mm",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"add_spring_connector: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_spot_weld_connector(self, face1_point: list, face2_point: list, location_points: list,
                                spot_diameter: float, study_name: str = None) -> Dict:
        """Saldatura a punti tra due facce parallele (punti in mm); `location_points` = VERTICI del modello (mm)."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            f1, e1 = self._sim_faces(doc, _pts(face1_point))
            f2, e2 = self._sim_faces(doc, _pts(face2_point))
            if e1 or e2:
                return self._s2_err(e1 or e2, SwErrors.swSelectionError)
            locs = []
            for p in _pts(location_points):
                v, _d = self._find_entity(doc, "vertex", [float(c) / 1000.0 for c in p], 1e-4)
                if v is None:
                    return self._s2_err(f"Nessun vertice entro 0,1 mm da {list(p)} (le posizioni devono essere vertici)",
                                        SwErrors.swSelectionError)
                locs.append(v)
            lm = st.LoadsAndRestraintsManager
            n0 = int(lm.Count)
            ec = _bi()
            w = lm.AddSpotWeldConnector(f1[0], f2[0], _va(locs), ec)
            if w is None:
                return self._s2_err(f"AddSpotWeldConnector fallito: errore {ec.value} ({_SPOT_ERR.get(int(ec.value), '?')})")
            w.SpotWeldConnectorBeginEdit()
            w.SpotWeldDiameterUnit = 0
            w.SpotWeldDiameterValue = float(spot_diameter)
            rc = int(w.SpotWeldConnectorEndEdit)
            d = float(w.SpotWeldDiameterValue)
            data = {"name": self._s2_last_name(lm, n0), "spot_diameter_mm": d, "locations": len(locs), "end_edit": rc}
            if rc != 0 or abs(d - float(spot_diameter)) > 1e-9:
                return self._s2_err(f"Saldatura creata ma diametro non impostato (codice {rc}, letto {d})", data=data)
            return self._result(True, f"Saldatura a punti {data['name']}: {len(locs)} punti, diametro {d} mm", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"add_spot_weld_connector: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ 5. Condizioni termiche
    def _s2_thermal_study(self, study_name):
        st, doc, sm, err = self._sim_study(study_name)
        if err:
            return None, None, err
        if int(st.AnalysisType) != 3:
            return None, None, self._s2_err("Serve uno studio termico (create_thermal_study)", SwErrors.swInvalidInput)
        return st, doc, None

    def add_convection_load(self, face_point: list, convection_coefficient: float,
                            ambient_temperature_c: float = 20.0, study_name: str = None) -> Dict:
        """Convezione su facce: coefficiente h in W/(m2 K) e temperatura ambiente in C (riletti da SolidWorks)."""
        try:
            st, doc, err = self._s2_thermal_study(study_name)
            if err:
                return err
            ents, e = self._sim_faces(doc, _pts(face_point))
            if e:
                return self._s2_err(e, SwErrors.swSelectionError)
            lm = st.LoadsAndRestraintsManager
            n0 = int(lm.Count)
            ec = _bi()
            c = lm.AddConvection(_va(ents), ec)
            if c is None:
                return self._s2_err(f"AddConvection fallito (errore {ec.value})")
            c.ConvectionBeginEdit()
            c.Unit = 0                                                # SI: W/m2K, Kelvin
            c.ConvectionCoefficient = float(convection_coefficient)
            c.BulkAmbientTemperature = float(ambient_temperature_c) + _K0
            rc = int(c.ConvectionEndEdit)
            h, ta = float(c.ConvectionCoefficient), float(c.BulkAmbientTemperature) - _K0
            data = {"name": self._s2_last_name(lm, n0), "convection_coefficient": h, "ambient_temperature_c": round(ta, 6),
                    "faces": len(ents), "end_edit": rc}
            if rc != 0 or abs(h - float(convection_coefficient)) > 1e-9 or abs(ta - float(ambient_temperature_c)) > 1e-6:
                return self._s2_err(f"Convezione creata ma valori non impostati (codice {rc})", data=data)
            return self._result(True, f"Convezione {data['name']} su {len(ents)} facce: h = {h} W/m2K, T amb = {ta:.2f} C",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"add_convection_load: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_radiation_load(self, face_point: list, emissivity: float = 0.9, ambient_temperature_c: float = 20.0,
                           view_factor: float = 1.0, study_name: str = None) -> Dict:
        """Irraggiamento superficie-ambiente: emissivita', temperatura ambiente (C) e fattore di vista (riletti)."""
        try:
            st, doc, err = self._s2_thermal_study(study_name)
            if err:
                return err
            ents, e = self._sim_faces(doc, _pts(face_point))
            if e:
                return self._s2_err(e, SwErrors.swSelectionError)
            lm = st.LoadsAndRestraintsManager
            n0 = int(lm.Count)
            ec = _bi()
            r = lm.AddRadiation(0, _va(ents), ec)                      # 0 = superficie verso ambiente
            if r is None:
                return self._s2_err(f"AddRadiation fallito (errore {ec.value})")
            r.RadiationBeginEdit()
            r.Unit = 0
            r.Emmisivity = float(emissivity)
            r.AmbientTemperature = float(ambient_temperature_c) + _K0
            r.ViewFactor = float(view_factor)
            rc = int(r.RadiationEndEdit)
            em, ta, vf = float(r.Emmisivity), float(r.AmbientTemperature) - _K0, float(r.ViewFactor)
            data = {"name": self._s2_last_name(lm, n0), "emissivity": em, "ambient_temperature_c": round(ta, 6),
                    "view_factor": vf, "faces": len(ents), "end_edit": rc}
            if rc != 0 or abs(em - float(emissivity)) > 1e-9 or abs(ta - float(ambient_temperature_c)) > 1e-6:
                return self._s2_err(f"Irraggiamento creato ma valori rifiutati (codice {rc}: 6 = emissivita', 7 = fattore di vista)", data=data)
            return self._result(True, f"Irraggiamento {data['name']} su {len(ents)} facce: emissivita' {em}, T amb {ta:.2f} C, "
                                      f"fattore di vista {vf}", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"add_radiation_load: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_heat_power_load(self, face_point: list, heat_power_w: float, study_name: str = None) -> Dict:
        """Potenza termica totale (W) applicata alle facce indicate (riletta)."""
        try:
            st, doc, err = self._s2_thermal_study(study_name)
            if err:
                return err
            ents, e = self._sim_faces(doc, _pts(face_point))
            if e:
                return self._s2_err(e, SwErrors.swSelectionError)
            lm = st.LoadsAndRestraintsManager
            n0 = int(lm.Count)
            ec = _bi()
            h = lm.AddHeatPower(_va(ents), ec)
            if h is None:
                return self._s2_err(f"AddHeatPower fallito (errore {ec.value})")
            h.HeatPowerBeginEdit()
            h.Unit = 0                                                # W
            h.HPValue = float(heat_power_w)
            rc = int(h.HeatPowerEndEdit)
            v = float(h.HPValue)
            data = {"name": self._s2_last_name(lm, n0), "heat_power_w": v, "faces": len(ents), "end_edit": rc}
            if rc != 0 or abs(v - float(heat_power_w)) > 1e-9:
                return self._s2_err(f"Potenza termica creata ma valore non impostato (codice {rc}, letto {v})", data=data)
            return self._result(True, f"Potenza termica {data['name']}: {v} W su {len(ents)} facce", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"add_heat_power_load: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ 6. Contatti
    def add_shrink_fit_contact(self, face_hub_point: list, face_shaft_point: list, friction_coefficient: float = None,
                               study_name: str = None) -> Dict:
        """Accoppiamento forzato tra foro (mozzo) e albero cilindrici: l'interferenza e' quella della GEOMETRIA
        (raggio albero - raggio foro, riportata). Attrito opzionale (riletto)."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            hub, eh = self._sim_faces(doc, _pts(face_hub_point))
            shaft, es = self._sim_faces(doc, _pts(face_shaft_point))
            if eh or es:
                return self._s2_err(eh or es, SwErrors.swSelectionError)
            if not (self._s2_is_cyl(hub[0]) and self._s2_is_cyl(shaft[0])):
                return self._s2_err("Mozzo e albero devono essere facce CILINDRICHE", SwErrors.swInvalidInput)
            rh, rs = self._s2_cyl_radius_mm(hub[0]), self._s2_cyl_radius_mm(shaft[0])
            ec = _bi()
            c = st.ContactManager.CreateContactSet(2, _va(hub), _va(shaft), ec)      # 2 = accoppiamento forzato
            if c is None:
                return self._s2_err(f"CreateContactSet (forzato) fallito: errore {ec.value} ({_CONTACT_ERR.get(int(ec.value), '?')})")
            rc = 0
            if friction_coefficient is not None:
                c.ContactSetBeginEdit()
                c.IncludeFriction = True
                c.FrictionValue = float(friction_coefficient)
                rc = int(c.ContactSetEndEdit)
            data = {"name": c.ContactName, "contact_type": int(c.ContactSetType), "hub_radius_mm": rh, "shaft_radius_mm": rs,
                    "radial_interference_mm": round(rs - rh, 6) if (rh and rs) else None,
                    "friction": float(c.FrictionValue) if bool(c.IncludeFriction) else None, "end_edit": rc}
            if rc != 0 or data["contact_type"] != 2 or (friction_coefficient is not None and
                                                         abs((data["friction"] or -1) - float(friction_coefficient)) > 1e-9):
                return self._s2_err(f"Accoppiamento forzato creato ma impostazioni rifiutate (codice {rc})", data=data)
            return self._result(True, f"Accoppiamento forzato {data['name']}: interferenza radiale {data['radial_interference_mm']} mm",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"add_shrink_fit_contact: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_virtual_wall_contact(self, face_point: list, wall_plane: str, friction_coefficient: float = None,
                                 rigid_wall: bool = True, study_name: str = None) -> Dict:
        """Parete virtuale: le facce indicate non possono attraversare il piano `wall_plane` (front/top/right o nome di un
        piano). Parete rigida o flessibile, attrito opzionale (riletti)."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            ents, e = self._sim_faces(doc, _pts(face_point))
            if e:
                return self._s2_err(e, SwErrors.swSelectionError)
            plane = self._s2_plane(doc, wall_plane)
            if plane is None:
                return self._s2_err(f"Piano '{wall_plane}' non trovato", SwErrors.swInvalidInput)
            ec = _bi()
            c = st.ContactManager.CreateContactSet(4, _va(ents), _va([plane]), ec)   # 4 = parete virtuale
            if c is None:
                return self._s2_err(f"CreateContactSet (parete virtuale) fallito: errore {ec.value} ({_CONTACT_ERR.get(int(ec.value), '?')})")
            c.ContactSetBeginEdit()
            c.WallType = 0 if rigid_wall else 1
            if friction_coefficient is not None:
                c.IncludeFriction = True
                c.FrictionValue = float(friction_coefficient)
            rc = int(c.ContactSetEndEdit)
            fr = float(c.FrictionValue) if bool(c.IncludeFriction) else None
            data = {"name": c.ContactName, "contact_type": int(c.ContactSetType), "rigid_wall": int(c.WallType) == 0,
                    "friction": fr, "end_edit": rc}
            if rc != 0 or data["contact_type"] != 4 or data["rigid_wall"] != bool(rigid_wall):
                return self._s2_err(f"Parete virtuale creata ma impostazioni rifiutate (codice {rc})", data=data)
            note = "" if friction_coefficient is None or (fr is not None and abs(fr - float(friction_coefficient)) < 1e-9) \
                else f" (attrito richiesto {friction_coefficient} non accettato da SolidWorks: letto {fr})"
            data["friction_set"] = not note
            return self._result(True, f"Parete virtuale {data['name']} sul piano '{wall_plane}' "
                                      f"({'rigida' if data['rigid_wall'] else 'flessibile'}){note}", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"add_virtual_wall_contact: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ 7. Materiale ortotropo
    def set_orthotropic_material(self, ex_mpa: float, ey_mpa: float, ez_mpa: float, body_name: str = None,
                                 study_name: str = None) -> Dict:
        """Rende ortotropo il materiale di simulazione di un corpo (Ex, Ey, Ez in MPa, riletti). Gli altri parametri restano
        quelli del materiale di partenza. `body_name`: parte del nome del corpo di simulazione (default il primo)."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            bodies = self._sim_bodies(st)
            if not bodies:
                return self._s2_err("Nessun corpo solido nello studio", SwErrors.swInvalidInput)
            sel = [b for _, b in bodies if not body_name or str(body_name) in str(b.SolidBodyName)]
            if not sel:
                return self._s2_err(f"Corpo '{body_name}' non trovato: {[b.SolidBodyName for _, b in bodies]}", SwErrors.swInvalidInput)
            sb = sel[0]
            m = sb.GetSolidBodyMaterial
            m.ModelType = 1                                           # ortotropo
            for k, v in (("EX", ex_mpa), ("EY", ey_mpa), ("EZ", ez_mpa)):
                m.SetPropertyByName(k, float(v) * 1e6, 0)
            rc = int(sb.SetSolidBodyMaterial(m))
            m2 = sb.GetSolidBodyMaterial
            got = [float(m2.GetPropertyByName2(0, k, _bb())) / 1e6 for k in ("EX", "EY", "EZ")]
            data = {"body": sb.SolidBodyName, "model_type": int(m2.ModelType), "ex_mpa": got[0], "ey_mpa": got[1],
                    "ez_mpa": got[2], "rc": rc}
            want = [float(ex_mpa), float(ey_mpa), float(ez_mpa)]
            if rc != 0 or data["model_type"] != 1 or any(abs(g - w) > 1e-6 * w for g, w in zip(got, want)):
                return self._s2_err(f"Materiale ortotropo non applicato (codice {rc}, letti {got})", data=data)
            return self._result(True, f"Materiale ortotropo su {sb.SolidBodyName}: Ex {got[0]}, Ey {got[1]}, Ez {got[2]} MPa",
                                SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"set_orthotropic_material: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ 8. Shell e travi
    def define_shell_mesh(self, face_point: list, thickness: float, study_name: str = None) -> Dict:
        """Definisce un guscio (spessore mm) su facce di un corpo superficie/lamiera. Sulle facce di un SOLIDO SolidWorks
        rifiuta (codice 2): il tool lo riporta."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            ents, e = self._sim_faces(doc, _pts(face_point))
            if e:
                return self._s2_err(e, SwErrors.swSelectionError)
            shm = st.ShellManager
            shm._FlagAsMethod("CreateShell")
            n0 = int(shm.ShellCount)
            rc = shm.CreateShell(_va(ents))
            if not isinstance(rc, int):
                rc = 0 if rc is not None else -1
            if rc != 0 or int(shm.ShellCount) <= n0:
                return self._s2_err(f"Guscio non creato: codice {rc} ({_SHELL_ERR.get(rc, '?')})", data={"code": rc})
            sh = shm.GetShellAt(int(shm.ShellCount) - 1, _bi())
            sh.ShellBeginEdit()
            sh.ShellUnit = 0
            sh.ShellThickness = float(thickness)
            rc2 = int(sh.ShellEndEdit)
            t = float(sh.ShellThickness)
            data = {"name": sh.Name, "thickness_mm": t, "faces": len(ents), "end_edit": rc2}
            if rc2 != 0 or abs(t - float(thickness)) > 1e-9:
                return self._s2_err(f"Guscio creato ma spessore non impostato (codice {rc2}, letto {t})", data=data)
            return self._result(True, f"Guscio {sh.Name}: spessore {t} mm su {len(ents)} facce", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"define_shell_mesh: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def define_beam_mesh(self, body_name: str = None, study_name: str = None) -> Dict:
        """Tratta un corpo come trave 1D (ConvertToBeamBody): esito verificato dal numero di travi dello studio.
        `body_name`: parte del nome del corpo di simulazione (default il primo)."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            bodies = self._sim_bodies(st)
            sel = [b for _, b in bodies if not body_name or str(body_name) in str(b.SolidBodyName)]
            if not sel:
                return self._s2_err(f"Corpo '{body_name}' non trovato: {[b.SolidBodyName for _, b in bodies]}", SwErrors.swInvalidInput)
            bm = st.BeamManager
            n0 = int(bm.BeamCount)
            name = sel[0].SolidBodyName
            rc = int(sel[0].ConvertToBeamBody)
            n1 = int(st.BeamManager.BeamCount)
            data = {"body": name, "beams_before": n0, "beams_after": n1, "rc": rc}
            if rc != 0 or n1 <= n0:
                return self._s2_err(f"Corpo '{name}' non convertito in trave (codice {rc}, travi {n0} -> {n1})", data=data)
            return self._result(True, f"Corpo '{name}' trattato come trave 1D (travi nello studio: {n1})", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"define_beam_mesh: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def get_mesh_quality_metrics(self, study_name: str = None) -> Dict:
        """Metriche della mesh dello studio: nodi, elementi, rapporto d'aspetto (max, medio, % > 3 e > 10), jacobiano peggiore."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            if int(st.Mesh.MeshState) != 1:
                return self._s2_err("Mesh assente o non aggiornata: usa create_simulation_mesh", SwErrors.swInvalidInput)
            info = self._sim_mesh_info(st)
            m = st.Mesh
            info["mesh_quality"] = "high" if int(m.Quality) == 1 else "draft"
            info["mesher_type"] = {0: "standard", 2: "curvature_based"}.get(int(m.MesherType), str(m.MesherType))
            jac = info.get("worst_jacobian_ratio")
            return self._result(True, f"Mesh: {info['nodes']} nodi, {info['elements']} elementi, aspetto max {info['max_aspect_ratio']}"
                                      + (f", jacobiano peggiore {jac}" if jac is not None else ", jacobiano non disponibile"),
                                SwErrors.swSuccess, info)
        except Exception as e:
            logger.error(f"get_mesh_quality_metrics: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ 9. Solutore
    def set_solver_options(self, solver_type: str = "FFEPlus", large_displacement: bool = False, study_name: str = None) -> Dict:
        """Solutore di uno studio STATICO: automatic | FFEPlus | DirectSparse | IntelDirectSparse, grandi spostamenti.
        Restituisce il solutore riletto (SolidWorks puo' sostituire Direct Sparse con Intel Direct Sparse)."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            if int(st.AnalysisType) != 0:
                return self._s2_err("Opzioni del solutore disponibili qui solo per studi statici", SwErrors.swInvalidInput)
            low = str(solver_type).lower().replace(" ", "").replace("_", "")
            code = {"automatic": 0, "auto": 0, "directsparse": 1, "ffeplus": 2, "inteldirectsparse": 7, "intel": 7}.get(low)
            if code is None:
                return self._s2_err("solver_type: automatic | FFEPlus | DirectSparse | IntelDirectSparse", SwErrors.swInvalidInput)
            so = st.StaticStudyOptions
            so.SolverType = code
            so.LargeDisplacement = bool(large_displacement)
            got, ld = int(so.SolverType), bool(so.LargeDisplacement)
            names = {0: "automatic", 1: "DirectSparse", 2: "FFEPlus", 7: "IntelDirectSparse"}
            data = {"requested_code": code, "solver_code": got, "solver": names.get(got, str(got)), "large_displacement": ld}
            ok = (got == code or (code == 1 and got == 7)) and ld == bool(large_displacement)
            if not ok:
                return self._s2_err(f"Solutore non impostato: letto {data['solver']} (codice {got}), grandi spostamenti {ld}", data=data)
            return self._result(True, f"Solutore: {data['solver']}, grandi spostamenti {'si' if ld else 'no'}", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"set_solver_options: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ 10. Risultati e sonde
    def get_mode_shapes(self, mode_number: int = 1, study_name: str = None) -> Dict:
        """Frequenza (Hz, rad/s) del modo richiesto e tabella di tutti i modi di uno studio di frequenze eseguito."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            if int(st.AnalysisType) != 1:
                return self._s2_err("Serve uno studio di frequenze", SwErrors.swInvalidInput)
            res = st.Results
            if res is None:
                return self._s2_err("Risultati non disponibili: esegui prima lo studio.", SwErrors.swInvalidInput)
            f = list(res.GetResonantFrequencies(_bi()) or [])
            modes = [{"mode": int(f[i]), "rad_s": float(f[i + 1]), "hz": float(f[i + 2]), "period_s": float(f[i + 3])}
                     for i in range(0, len(f) - 3, 4)]
            chosen = next((m for m in modes if m["mode"] == int(mode_number)), None)
            if chosen is None:
                return self._s2_err(f"Modo {mode_number} non trovato (modi calcolati: {len(modes)})", SwErrors.swInvalidInput)
            return self._result(True, f"Modo {chosen['mode']}: {chosen['hz']:.3f} Hz ({chosen['rad_s']:.3f} rad/s)", SwErrors.swSuccess,
                                {"mode": chosen["mode"], "frequency_hz": chosen["hz"], "frequency_rad_s": chosen["rad_s"],
                                 "all_modes": modes})
        except Exception as e:
            logger.error(f"get_mode_shapes: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def get_buckling_load_factor(self, mode_number: int = 1, study_name: str = None) -> Dict:
        """Fattore di carico critico (BLF) del modo richiesto di uno studio di buckling eseguito."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            if int(st.AnalysisType) != 2:
                return self._s2_err("Serve uno studio di buckling", SwErrors.swInvalidInput)
            res = st.Results
            if res is None:
                return self._s2_err("Risultati non disponibili: esegui prima lo studio.", SwErrors.swInvalidInput)
            b = list(res.GetBucklingLoadFactors(_bi()) or [])
            modes = [{"mode": int(b[i]), "load_factor": float(b[i + 1])} for i in range(0, len(b) - 1, 2)]
            chosen = next((m for m in modes if m["mode"] == int(mode_number)), None)
            if chosen is None:
                return self._s2_err(f"Modo di buckling {mode_number} non trovato (modi calcolati: {len(modes)})", SwErrors.swInvalidInput)
            return self._result(True, f"Modo di buckling {chosen['mode']}: BLF = {chosen['load_factor']:.4f}", SwErrors.swSuccess,
                                {"mode": chosen["mode"], "buckling_load_factor": chosen["load_factor"], "all_modes": modes})
        except Exception as e:
            logger.error(f"get_buckling_load_factor: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def get_thermal_results(self, study_name: str = None) -> Dict:
        """Temperatura min/max (C, con posizione) e flusso termico min/max (W/m2) di uno studio termico eseguito."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            if int(st.AnalysisType) != 3:
                return self._s2_err("Serve uno studio termico", SwErrors.swInvalidInput)
            res = st.Results
            if res is None:
                return self._s2_err("Risultati non disponibili: esegui prima lo studio.", SwErrors.swInvalidInput)
            r = self._sim_results_thermal(st, res, 1)
            if r.get("success"):
                d = r["data"]
                d.update({"temperature_min_c": d["temperature_C"]["min"], "temperature_max_c": d["temperature_C"]["max"],
                          "heat_flux_min_w_m2": d["heat_flux_W_m2"]["min"], "heat_flux_max_w_m2": d["heat_flux_W_m2"]["max"]})
            return r
        except Exception as e:
            logger.error(f"get_thermal_results: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def get_reaction_forces_detail(self, face_point: list, study_name: str = None) -> Dict:
        """Reazione vincolare (N) sui nodi delle facce indicate (punti in mm) di uno studio statico eseguito, e il totale del
        modello per confronto."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            if int(st.AnalysisType) != 0:
                return self._s2_err("Reazioni vincolari disponibili per studi statici", SwErrors.swInvalidInput)
            res = st.Results
            if res is None:
                return self._s2_err("Risultati non disponibili: esegui prima lo studio.", SwErrors.swInvalidInput)
            ents, e = self._sim_faces(doc, _pts(face_point))
            if e:
                return self._s2_err(e, SwErrors.swSelectionError)
            nodes = self._sim_nodes(st)
            a = list(res.GetReactionForcesAndMoments(1, _nullv(), 0, _bi()) or [])
            tot, sel, cnt = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], 0
            for i in range(0, len(a) - 8, 9):
                f = (a[i + 1], a[i + 2], a[i + 3])
                for k in range(3):
                    tot[k] += f[k]
                p = nodes.get(int(a[i]))
                if max(abs(v) for v in f) > 0 and p is not None and any(self._closest(fc, "face", list(p)) < 1e-6 for fc in ents):
                    cnt += 1
                    for k in range(3):
                        sel[k] += f[k]
            if cnt == 0:
                return self._s2_err("Nessun nodo con reazione non nulla sulle facce indicate (sono vincolate?)", SwErrors.swInvalidInput,
                                    {"model_total_n": [round(v, 4) for v in tot]})
            res_n = math.sqrt(sum(v * v for v in sel))
            return self._result(True, f"Reazione sulle facce: Fx={sel[0]:.3f} N, Fy={sel[1]:.3f} N, Fz={sel[2]:.3f} N "
                                      f"(risultante {res_n:.3f} N, {cnt} nodi)", SwErrors.swSuccess,
                                {"fx_n": sel[0], "fy_n": sel[1], "fz_n": sel[2], "resultant_n": res_n, "nodes": cnt,
                                 "model_total_n": [round(v, 6) for v in tot]})
        except Exception as e:
            logger.error(f"get_reaction_forces_detail: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def probe_simulation_results(self, x: float, y: float, z: float, study_name: str = None) -> Dict:
        """Valori nel NODO della mesh piu' vicino al punto (mm) di uno studio statico eseguito: Von Mises (MPa) e spostamenti
        UX, UY, UZ, URES (mm), con la distanza punto-nodo."""
        try:
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            if int(st.AnalysisType) != 0:
                return self._s2_err("Sonda disponibile per studi statici (per il termico usa get_thermal_results)", SwErrors.swInvalidInput)
            res = st.Results
            if res is None:
                return self._s2_err("Risultati non disponibili: esegui prima lo studio.", SwErrors.swInvalidInput)
            target = (float(x) / 1000.0, float(y) / 1000.0, float(z) / 1000.0)
            nodes = self._sim_nodes(st)
            node, d2 = min(((n, sum((p[k] - target[k]) ** 2 for k in range(3))) for n, p in nodes.items()), key=lambda t: t[1])
            bodies = [b for _, b in self._sim_sw_bodies(doc)]
            out = {}
            ec = _bi()
            a = list(res.GetStressForEntities2(True, 9, 1, _nullv(), _va(bodies), 3, ec) or [])
            vm = {int(a[i]): float(a[i + 1]) for i in range(0, len(a) - 1, 2)}
            if node not in vm:
                return self._s2_err(f"Von Mises non disponibile nel nodo {node} (errore {ec.value})", SwErrors.swUnknownError)
            out["von_mises_mpa"] = vm[node]
            for comp, key in ((0, "ux_mm"), (1, "uy_mm"), (2, "uz_mm"), (3, "ures_mm")):
                ec = _bi()
                a = list(res.GetDisplacementForEntities(comp, 1, _nullv(), _va(bodies), 0, ec) or [])
                vals = {int(a[i]): float(a[i + 1]) for i in range(0, len(a) - 1, 2)}
                if node not in vals:
                    return self._s2_err(f"Spostamento {key} non disponibile nel nodo {node} (errore {ec.value})", SwErrors.swUnknownError)
                out[key] = vals[node]
            dist = math.sqrt(d2) * 1000.0
            out.update({"x": float(x), "y": float(y), "z": float(z), "nearest_node": node, "distance_to_node_mm": round(dist, 4),
                        "node_mm": self._sim_mm(nodes[node])})
            return self._result(True, f"Nodo {node} a {dist:.2f} mm da [{x}, {y}, {z}]: VM {out['von_mises_mpa']:.3f} MPa, "
                                      f"UX {out['ux_mm']:.5f} mm, URES {out['ures_mm']:.5f} mm", SwErrors.swSuccess, out)
        except Exception as e:
            logger.error(f"probe_simulation_results: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ 11. Report
    def export_simulation_report(self, filepath: str, study_name: str = None, overwrite: bool = False) -> Dict:
        """Report HTML dello studio con i dati letti da SolidWorks: tipo, carichi/vincoli, mesh e (se eseguito) risultati
        principali. Non contiene giudizi: riporta solo numeri letti."""
        try:
            p = Path(filepath)
            if p.exists() and not overwrite:
                return self._result(False, f"File '{filepath}' gia' esistente e overwrite=False", SwErrors.swInvalidInput)
            st, doc, sm, err = self._sim_study(study_name)
            if err:
                return err
            sname = st.Name
            atype = int(st.AnalysisType)
            tname = {0: "Statico lineare", 1: "Frequenze", 2: "Buckling", 3: "Termico", 6: "Drop test", 7: "Fatica",
                     8: "Dinamico lineare"}.get(atype, f"tipo {atype}")
            lm = st.LoadsAndRestraintsManager
            lbc = []
            for i in range(int(lm.Count)):
                try:
                    lbc.append(str(lm.GetLoadsAndRestraints(i, _bi()).Name))
                except Exception:
                    lbc.append("?")
            rows = [("Documento", self._get_doc_title(doc)), ("Studio", sname), ("Tipo di analisi", tname),
                    ("Carichi, vincoli e connettori", ", ".join(lbc) or "nessuno")]
            m = st.Mesh
            mesh = None
            if int(m.MeshState) == 1:
                mesh = self._sim_mesh_info(st)
                rows += [("Nodi", mesh["nodes"]), ("Elementi", mesh["elements"]), ("Rapporto d'aspetto max", mesh["max_aspect_ratio"])]
            else:
                rows.append(("Mesh", "non presente"))
            results = None
            if st.Results is not None:
                r = self.get_simulation_results(study=sname)
                if r.get("success"):
                    results = r["message"]
                    rows.append(("Risultati (letti da SolidWorks)", results))
            if results is None:
                rows.append(("Risultati", "studio non eseguito o risultati non leggibili"))
            body = "\n".join(f"    <tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>" for k, v in rows)
            content = (f"<!DOCTYPE html>\n<html lang=\"it\">\n<head>\n<meta charset=\"utf-8\">\n"
                       f"<title>Report simulazione - {html.escape(sname)}</title>\n<style>body{{font-family:Segoe UI,Arial,sans-serif;"
                       f"margin:30px}} table{{border-collapse:collapse}} td{{border:1px solid #ccc;padding:6px 10px}}</style>\n"
                       f"</head>\n<body>\n  <h1>Report simulazione: {html.escape(sname)}</h1>\n  <table>\n{body}\n  </table>\n</body>\n</html>\n")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            size = p.stat().st_size
            return self._result(True, f"Report di simulazione scritto: {p.name} ({size} byte)", SwErrors.swSuccess,
                                {"filepath": str(p.resolve()), "study_name": sname, "analysis_type": atype, "filesize_bytes": size,
                                 "loads_restraints": lbc, "mesh": mesh, "results": results})
        except Exception as e:
            logger.error(f"export_simulation_report: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)
