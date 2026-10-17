"""
Blocco 5 - SOLIDWORKS Simulation: analisi statica lineare (mixin SimulationOperations)
-------------------------------------------------------------------------------------
Usa l'add-in SOLIDWORKS Simulation via COM (type library `Simulation\\cosworks.tlb`, API CosmosWorks).
Unita' dei tool: lunghezze mm, forze N, tensioni MPa (N/mm2), pressioni MPa, accelerazioni m/s2, coppie N*m.

Trappole scoperte (SW 2026 SP4.1, late binding, istanza dedicata e NASCOSTA: tutto funziona anche invisibile):
 - L'add-in non e' caricato in un'istanza nuova: `app.LoadAddIn(<...>\\Simulation\\cosworks.dll)` (non basta il GUID); poi
   `app.GetAddInObject("SldWorks.Simulation").CosmosWorks`. LoadAddIn NON modifica HKCU\\...\\AddInsStartup (verificato);
   per sicurezza il mixin salva e ripristina comunque quella chiave.
 - Gli array di oggetti COM devono essere `VARIANT(VT_ARRAY|VT_VARIANT, (obj,..))`; con VT_ARRAY|VT_DISPATCH il server solleva
   0x80010105 (e un ciclo di tentativi ha fatto morire il processo). Array di double vuoti: `VARIANT(VT_ARRAY|VT_R8, ())`.
 - `StudyManager.ActiveStudy` e' un INDICE (int, base 0): lo studio si prende con `GetStudy(i)`.
 - Membri senza argomenti sono proprieta' (`RunAnalysis`, `GetSolidBodyMaterial`, `ForceEndEdit`, `GetNodes`, `GetPlotNames`...).
 - Modifica di un carico gia' creato: `XxxBeginEdit` ... `Set...` ... `XxxEndEdit` (senza, i valori NON cambiano).
 - Frame dei componenti di una forza con riferimento = piano: dir1 = asse x dello schizzo del piano, dir2 = asse y, dir3 = normale
   (verificato misurando le reazioni). Con una FACCIA di riferimento il frame e' arbitrario e la normale e' RIVOLTA ALL'INTERNO.
   Il piano di riferimento si passa come oggetto Feature (GetSpecificFeature2 del RefPlane da' 'Memoria bloccata').
 - `Results.GetMinMaxStress(comp, byElement, step, plane, unit, err)` -> (id_min, min, id_max, max); byElement=0 = valori nodali
   (come la mappa a colori), 1 = elementali. Posizione: `Mesh.GetNodes` = (id,x,y,z)* in metri; `Mesh.GetElements` = 16 valori per
   elemento (id, 10 nodi, centroide xyz m, volume?, jacobiano/aspetto). `GetNodeLocation` non e' usabile in late binding.
 - `Results.GetReactionForcesAndMoments` restituisce una riga di 9 numeri per NODO (id, FX,FY,FZ,FRES, MX..MRES): il totale e' la somma.
 - `GetMinMaxFactorOfSafety2` -> (FOS min, FOS max) senza posizione.
 - Grafico: `Results.ActivatePlot(nome)` poi `Extension.SaveAs(png)` con vista iso: la mappa a colori e' nel PNG (anche nascosto).
 - Mesh: `Study.CreateMesh(unita(0=mm), dimensione, tolleranza)`; `Mesh.MesherType` 0 standard, 2 basata sulla curvatura; `Mesh.Quality` 0 bozza / 1 alta.
Gruppo E (altri studi, posizione del FOS, momenti, carichi e contatti locali, controllo mesh):
 - `CreateNewStudy2(nome, tipo)`: 0 statico, 1 frequenze, 2 buckling, 3 termico. Opzioni: `FrequencyStudyOptions.NoOfFrequencies`,
   `BucklingStudyOptions.BucklingModes`, `ThermalStudyOptions.SolutionType` (1 stazionario, 0 transitorio). Per gli studi non statici
   NON chiamare le funzioni solo statiche dei risultati: frequenze `GetResonantFrequencies` (gruppi di 4: modo, rad/s, Hz, s) e
   `GetMassParticipation` (modo, X, Y, Z); buckling `GetBucklingLoadFactors` (gruppi di 2); termico `GetMinMaxThermal(comp, step, nullo,
   unita, err)` con comp 0 temperatura (unita 2 = gradi C), 4 gradiente, 8 flusso, 5/6/7 flusso x/y/z (unita 0: con unita 2 il flusso e'
   in cal/s/cm2, non W/m2).
 - Temperatura: `AddTemperature(facce, err)`, poi `TemperatureBeginEdit(); Unit = 2 (Celsius); TemperatureValue; TemperatureEndEdit`.
 - Il FOS dell'API non ha posizione: si ricava dal VM nodale per corpo (`GetStressForEntities2` con il CORPO SolidWorks come entita'
   = coppie (nodo, valore) su tutti i nodi del corpo) e lo snervamento del materiale di simulazione.
 - Reazioni: momento attorno a un punto = somma di (p - q) x F sui nodi + momenti nodali MX..MZ (nodi in metri).
 - Carico remoto: `AddRemoteLoad(0 diretto, facce, 0 mm, x, y, z, err)`, poi `RemoteLoadBeginEdit; ConnectionType (0 rigido, 1 distribuito);
   SetForceOrTranslationValues / SetMomentOrRotationValues(True, ux, vx, uy, vy, uz, vz); RemoteLoadEndEdit` (rc 0 = ok).
 - Carico da cuscinetto: `AddBearingLoad(sistema di coordinate, VARIANT array [faccia], err)`: la faccia nuda fa MORIRE SolidWorks (RPC
   0x800706BE). Serve un sistema di coordinate con l'origine SULL'asse del cilindro e Z = asse (errore 6 altrimenti); lo si crea da uno
   schizzo 3D ausiliario (punto + due linee) selezionato con Mark 1 (origine), 2 (asse X), 8 (asse Z).
 - Contatti locali: `ContactManager.CreateContactSet(tipo, facce1, facce2, err)` con tipi DIVERSI dal globale: 0 senza compenetrazione,
   1 incollato, 2 accoppiamento forzato, 3 libero, 4 parete virtuale. Le facce dei due componenti coincidono: la seconda serie si cerca
   fra i componenti diversi dalla prima. Controllo mesh: `Mesh.ApplyMeshControl(facce, err)`, poi `MeshControlBeginEdit; Units = 0;
   ElementSize; Ratio; MeshControlEndEdit`; dopo si rifa la mesh.
"""

import os
import time
import logging
import threading
import traceback
from typing import Dict, Any, List, Optional

import pythoncom
from win32com.client import VARIANT

from ..constants import SwErrors
from ..utils.sw_lang import plot_candidates

logger = logging.getLogger(__name__)

_DLL_DEFAULT = r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\Simulation\cosworks.dll"
_RESTRAINTS = {"fixed": 0, "fisso": 0, "immovable": 1, "immobile": 1, "symmetry": 2, "simmetria": 2,
               "roller": 3, "slider": 3, "sliding": 3, "rullo": 3, "scorrevole": 3,
               "hinge": 4, "fixed_hinge": 4, "cerniera": 4, "cerniera_fissa": 4}
_COMPONENTS = {"vonmises": 9, "von_mises": 9, "sx": 0, "sy": 1, "sz": 2, "txy": 3, "txz": 4, "tyz": 5,
               "p1": 6, "p2": 7, "p3": 8, "intensity": 10}
_DISP = {"ux": 0, "uy": 1, "uz": 2, "ures": 3, "resultant": 3}
_STUDY_TYPES = {"static": 0, "statico": 0, "statica": 0, "frequency": 1, "frequencies": 1, "frequenze": 1, "frequenza": 1,
                "modal": 1, "buckling": 2, "instabilita": 2, "thermal": 3, "termico": 3, "termica": 3}
_STUDY_NAMES = {0: "static", 1: "frequency", 2: "buckling", 3: "thermal"}
_CONTACTS_LOCAL = {"no_penetration": 0, "senza_compenetrazione": 0, "bonded": 1, "incollato": 1, "shrink_fit": 2,
                   "accoppiamento_forzato": 2, "free": 3, "libero": 3, "virtual_wall": 4, "parete_virtuale": 4}
_ERR_RUN = {1: "usare mesh di qualita' alta", 13: "modulo elastico non definito", 14: "valore EX non valido",
            15: "coefficiente di Poisson non valido", 19: "materiale non definito", 20: "materiale mancante su componenti",
            21: "nessun corpo solido", 22: "autorizzazione/licenza Simulation fallita", 23: "mesh non trovata",
            24: "analisi fallita", 25: "studio inesistente", 30: "carichi/vincoli non validi"}


def _va(objs):
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_VARIANT, tuple(objs))


def _dbl(*vals):
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, tuple(float(v) for v in vals))


def _bi():
    return VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)


def _bb():
    return VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BOOL, False)


def _br():
    return VARIANT(pythoncom.VT_BYREF | pythoncom.VT_R8, 0.0)


def _nullv():
    return VARIANT(pythoncom.VT_DISPATCH, None)


class SimulationOperations:
    """Simulazione statica lineare. Richiede SolidWorksAutomation (get_active_doc, _com, _result, _find_entity...)."""

    _sim_reg_snapshot = None
    _sim_frames: Dict[str, Any] = {}
    _sim_run_info: Dict[str, Any] = {}

    # ------------------------------------------------------------------ add-in
    @staticmethod
    def _sim_reg_read() -> Dict[str, Any]:
        import winreg
        out = {}
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\SolidWorks\AddInsStartup") as k:
                i = 0
                while True:
                    try:
                        sub = winreg.EnumKey(k, i)
                    except OSError:
                        break
                    i += 1
                    try:
                        with winreg.OpenKey(k, sub) as sk:
                            out[sub] = winreg.QueryValueEx(sk, "")[0]
                    except OSError:
                        out[sub] = None
        except OSError:
            pass
        return out

    def _sim_reg_restore(self) -> List[str]:
        """Riporta HKCU\\Software\\SolidWorks\\AddInsStartup allo stato salvato prima del caricamento dell'add-in."""
        import winreg
        changed: List[str] = []
        snap = self._sim_reg_snapshot
        if snap is None:
            return changed
        now = self._sim_reg_read()
        for guid, val in snap.items():
            if now.get(guid) != val:
                try:
                    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\SolidWorks\AddInsStartup\\" + guid) as sk:
                        winreg.SetValueEx(sk, "", 0, winreg.REG_SZ if isinstance(val, str) else winreg.REG_DWORD,
                                          val if val is not None else "")
                    changed.append(guid)
                except OSError as e:
                    logger.warning(f"ripristino {guid}: {e}")
        for guid in set(now) - set(snap):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\SolidWorks\AddInsStartup\\" + guid)
                changed.append("-" + guid)
            except OSError:
                pass
        return changed

    def _sim_dll(self) -> str:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"SldWorks.Simulation\CLSID") as k:
                clsid = winreg.QueryValueEx(k, "")[0]
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"CLSID\{clsid}\InprocServer32") as k:
                p = winreg.QueryValueEx(k, "")[0]
            if os.path.exists(p):
                return p
        except OSError:
            pass
        return _DLL_DEFAULT

    def _sim_addin(self):
        """-> (oggetto CosmosWorks | None, info). Carica l'add-in nell'istanza se serve."""
        if not self.is_connected:
            r = self.connect()
            if not r["success"]:
                return None, r["message"]
        app = self._sw_app
        if self._sim_reg_snapshot is None:
            SimulationOperations._sim_reg_snapshot = self._sim_reg_read()
        add = None
        try:
            add = app.GetAddInObject("SldWorks.Simulation")
        except Exception:
            add = None
        loaded_now = False
        if add is None:
            dll = self._sim_dll()
            try:
                rc = app.LoadAddIn(dll)
            except Exception as e:
                return None, f"LoadAddIn({dll}) fallito: {e}"
            loaded_now = True
            try:
                add = app.GetAddInObject("SldWorks.Simulation")
            except Exception:
                add = None
            if add is None:
                return None, f"LoadAddIn({dll}) = {rc} ma GetAddInObject restituisce None: add-in non caricabile/licenza assente"
        if loaded_now:
            self._sim_reg_restore()
        try:
            cw = add.CosmosWorks
        except Exception as e:
            return None, f"CosmosWorks non disponibile: {e}"
        return cw, None

    def _sim_cw(self):
        cw, msg = self._sim_addin()
        if cw is None:
            return None, self._result(False, f"SOLIDWORKS Simulation non disponibile: {msg}", SwErrors.swUnknownError)
        return cw, None

    def _sim_study(self, study: str = None):
        """-> (study, doc, studymanager, errore). `study` = nome (default quello attivo)."""
        cw, err = self._sim_cw()
        if err:
            return None, None, None, err
        doc, err = self.get_active_doc()
        if err:
            return None, None, None, err
        try:
            cwdoc = cw.ActiveDoc
            sm = cwdoc.StudyManager
            n = int(sm.StudyCount)
            if n == 0:
                return None, doc, sm, self._result(False, "Nessuno studio: usa create_static_study.", SwErrors.swInvalidInput)
            if study:
                for i in range(n):
                    s = sm.GetStudy(i)
                    if s.Name == study:
                        try:
                            sm.ActiveStudy = i
                        except Exception:
                            pass
                        return s, doc, sm, None
                return None, doc, sm, self._result(False, f"Studio '{study}' non trovato: {[sm.GetStudy(i).Name for i in range(n)]}",
                                                   SwErrors.swInvalidInput)
            return sm.GetStudy(int(sm.ActiveStudy)), doc, sm, None
        except Exception as e:
            return None, doc, None, self._result(False, f"Studio non accessibile: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ stato / studi
    def simulation_status(self) -> Dict:
        """Disponibilita' di SOLIDWORKS Simulation: add-in caricabile, versione, licenza, studi del documento attivo."""
        try:
            data: Dict[str, Any] = {"dll": self._sim_dll(), "dll_exists": os.path.exists(self._sim_dll())}
            cw, msg = self._sim_addin()
            if cw is None:
                data["available"] = False
                data["error"] = msg
                return self._result(False, f"Simulation NON disponibile: {msg}", SwErrors.swUnknownError, data)
            data["available"] = True
            try:
                data["simulation_version_number"] = int(cw.VersionNumber)
            except Exception:
                pass
            data["registry_addins_startup_restored"] = self._sim_reg_restore()
            doc, err = self.get_active_doc()
            if not err:
                try:
                    sm = cw.ActiveDoc.StudyManager
                    data["studies"] = [sm.GetStudy(i).Name for i in range(int(sm.StudyCount))]
                except Exception as e:
                    data["studies_error"] = str(e)
            data["license_note"] = ("la licenza (Student Design Premium) si verifica davvero solo con run_simulation: "
                                    "errore 22 = autorizzazione fallita")
            return self._result(True, "SOLIDWORKS Simulation disponibile (add-in caricato nell'istanza)", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"simulation_status: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def create_static_study(self, name: str = "Statico 1", analysis: str = "static", modes: int = None) -> Dict:
        """Crea uno studio sul documento attivo (pezzo o assieme) e lo rende attivo. analysis: static (default) | frequency |
        buckling | thermal (stazionario). `modes` = numero di modi (solo frequency/buckling; default di SW: 5 e 1)."""
        try:
            t = _STUDY_TYPES.get(str(analysis).lower())
            if t is None:
                return self._result(False, f"Tipo di studio sconosciuto '{analysis}': {sorted(_STUDY_TYPES)}", SwErrors.swInvalidInput)
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
            st = sm.CreateNewStudy2(name, t, e)
            if st is None or int(e.value) != 0:
                msgs = {1: "nessun corpo solido", 2: "nome gia' usato o non valido", 3: "tipo non definito"}
                return self._result(False, f"Creazione studio fallita: errore {e.value} ({msgs.get(int(e.value), '?')})",
                                    SwErrors.swUnknownError)
            kind = _STUDY_NAMES[t]
            data: Dict[str, Any] = {"name": name, "type": kind}
            try:
                # le opzioni si leggono da un oggetto tenuto in una variabile (come nelle sonde)
                if t == 1:
                    fo = st.FrequencyStudyOptions
                    if modes is not None:
                        fo.NoOfFrequencies = int(modes)
                    data["modes"] = int(fo.NoOfFrequencies)
                elif t == 2:
                    bo = st.BucklingStudyOptions
                    if modes is not None:
                        bo.BucklingModes = int(modes)
                    data["modes"] = int(bo.BucklingModes)
                elif t == 3:
                    st.ThermalStudyOptions.SolutionType = 1        # stazionario (0 = transitorio)
                    data["solution"] = "steady" if int(st.ThermalStudyOptions.SolutionType) == 1 else "transient"
            except Exception as ex:
                data["options_error"] = str(ex)
            n = int(sm.StudyCount)
            for i in range(n):
                if sm.GetStudy(i).Name == name:
                    sm.ActiveStudy = i
            data["count"] = n
            label = {"static": "statico", "frequency": "di frequenze", "buckling": "di buckling", "thermal": "termico stazionario"}[kind]
            extra = f" ({data['modes']} modi)" if "modes" in data else ""
            return self._result(True, f"Studio {label} '{name}' creato{extra}", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"create_static_study: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def list_simulation_studies(self) -> Dict:
        """Studi del documento attivo: nome, tipo, stato della mesh, carichi/vincoli, attivo."""
        try:
            cw, err = self._sim_cw()
            if err:
                return err
            sm = cw.ActiveDoc.StudyManager
            n = int(sm.StudyCount)
            act = int(sm.ActiveStudy) if n else -1
            out = []
            states = {0: "nessuna", 1: "aggiornata", 2: "non aggiornata", 3: "fallita", 4: "interrotta"}
            for i in range(n):
                s = sm.GetStudy(i)
                row = {"index": i, "name": s.Name, "analysis_type": int(s.AnalysisType), "active": i == act}
                try:
                    row["mesh_state"] = states.get(int(s.Mesh.MeshState), "?")
                    row["loads_restraints"] = int(s.LoadsAndRestraintsManager.Count)
                except Exception:
                    pass
                out.append(row)
            return self._result(True, f"{n} studi", SwErrors.swSuccess, {"studies": out})
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def delete_simulation_study(self, name: str) -> Dict:
        """Elimina uno studio per nome."""
        try:
            st, doc, sm, err = self._sim_study(name)
            if err:
                return err
            rc = sm.DeleteStudy(name)
            left = [sm.GetStudy(i).Name for i in range(int(sm.StudyCount))]
            ok = name not in left
            return self._result(ok, f"Studio '{name}' {'eliminato' if ok else 'NON eliminato'} (rc={rc})",
                                SwErrors.swSuccess if ok else SwErrors.swUnknownError, {"remaining": left})
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ materiale
    def _sim_bodies(self, st):
        # i corpi COM restano validi solo finche' vivono manager e componente padre: si conservano in self._sim_keep
        out = []
        sol = st.SolidManager
        keep = [st, sol]
        for i in range(int(sol.ComponentCount)):
            comp = sol.GetComponentAt(i, _bi())
            keep.append(comp)
            for j in range(int(comp.SolidBodyCount)):
                out.append((comp.ComponentName, comp.GetSolidBodyAt(j, _bi())))
        self._sim_keep = keep
        return out

    def _sim_mat_props(self, mat) -> Dict:
        d: Dict[str, Any] = {}
        try:
            d["name"] = mat.MaterialName
            d["category"] = mat.Category
        except Exception:
            pass
        for key, label in (("EX", "E_MPa"), ("NUXY", "poisson"), ("DENS", "density_kg_m3"), ("SIGYLD", "yield_MPa")):
            try:
                v = mat.GetPropertyByName2(0, key, _bb())
                if isinstance(v, tuple):
                    v = v[0]
                v = float(v)
                d[label] = v / 1e6 if label in ("E_MPa", "yield_MPa") else v
            except Exception:
                pass
        return d

    def set_study_material(self, material: str = None, category: str = None, study: str = None) -> Dict:
        """Materiale dello studio. Senza `material`: usa quello del pezzo (default) e lo riporta; con `material`: assegna
        un materiale della libreria SOLIDWORKS allo studio (tutti i corpi). Restituisce E, nu, densita', snervamento."""
        try:
            st, doc, sm, err = self._sim_study(study)
            if err:
                return err
            bodies = self._sim_bodies(st)
            if not bodies:
                return self._result(False, "Nessun corpo solido nello studio", SwErrors.swInvalidInput)
            note = "materiale del pezzo"
            if material:
                mat, e = self._dx_find_material(material, category)
                if mat is None:
                    return self._result(False, e, SwErrors.swInvalidInput)
                for cname, body in bodies:
                    ok = body.SetLibraryMaterial2(mat["database"], mat["name"])
                    if ok is False:
                        return self._result(False, f"SetLibraryMaterial2 rifiutato per {mat['name']}", SwErrors.swUnknownError)
                note = f"assegnato allo studio: {mat['name']}"
            info = [self._sim_mat_props(body.GetSolidBodyMaterial) for _, body in bodies]
            return self._result(True, f"Materiale studio: {info[0].get('name')} ({note})", SwErrors.swSuccess,
                                {"source": note, "bodies": [{"component": c, "body": b.SolidBodyName, **i}
                                                            for (c, b), i in zip(bodies, info)]})
        except Exception as e:
            logger.error(f"set_study_material: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ selezione facce
    def _sim_faces(self, doc, points) -> (list, Optional[str]):
        if not points:
            return [], "Servono le coordinate (mm) di almeno una faccia: faces=[[x,y,z],...] (punto SULLA faccia)"
        faces = []
        is_asm = False
        try:
            is_asm = int(doc.GetType) == 2
        except Exception:
            pass
        for p in points:
            pm = [float(c) / 1000.0 for c in p]
            if is_asm:
                ent, d = self._sim_find_asm_face(doc, pm, 1e-4)
            else:
                ent, d = self._find_entity(doc, "face", pm, 1e-4)
            if ent is None:
                return [], f"Nessuna faccia entro 0,1 mm dal punto {list(p)} (il punto deve stare SULLA faccia)"
            faces.append(ent)
        return faces, None

    def _sim_find_asm_face(self, doc, p, tol_m, exclude_components=None, want_comp=False):
        """Faccia piu' vicina al punto p (m, coordinate d'assieme) fra i corpi di tutti i componenti (esclusi quelli i cui nomi
        sono in `exclude_components`). Restituisce (faccia, distanza); con want_comp=True (faccia, distanza, nome del componente)."""
        best, bd, bcomp = None, 1e9, None
        keep = []
        comps = doc.GetComponents(False) or []
        for comp in comps:
            if exclude_components:
                try:
                    if comp.Name2 in exclude_components:
                        continue
                except Exception:
                    pass
            try:
                bodies = comp.GetBodies2(0)
            except Exception:
                bodies = None
            # i corpi sono nello spazio del PEZZO (non trasformati): il punto d'assieme va portato nel riferimento del componente
            # (ArrayData: 9 rotazione, 3 traslazione, scala; x' = r0 x + r3 y + r6 z + t => inversa x = r0 x' + r1 y' + r2 z')
            try:
                a = list(comp.Transform2.ArrayData)
                sc = a[12] or 1.0
                d = [(p[i] - a[9 + i]) / sc for i in range(3)]
                pl = [a[0] * d[0] + a[1] * d[1] + a[2] * d[2], a[3] * d[0] + a[4] * d[1] + a[5] * d[2],
                      a[6] * d[0] + a[7] * d[1] + a[8] * d[2]]
            except Exception:
                pl = p
            for body in (bodies or []):
                keep.append(body)
                try:
                    faces = self._com(body, "GetFaces")
                except Exception:
                    faces = None
                for f in (faces or []):
                    try:
                        d = self._closest(f, "face", pl)
                    except Exception:
                        continue
                    if d < bd:
                        best, bd = f, d
                        try:
                            bcomp = comp.Name2
                        except Exception:
                            bcomp = None
        self._sim_keep_asm = keep + list(comps)
        ok = best is not None and bd <= tol_m
        if want_comp:
            return (best if ok else None), bd, bcomp
        if ok:
            return best, bd
        return None, bd

    def _sim_plane_frame(self, doc):
        """Frame (dir1, dir2, normale) in coordinate modello del 1o piano di riferimento = quello dei componenti delle forze.
        Si ricava da uno schizzo temporaneo sul piano (poi eliminato)."""
        key = self._get_doc_title(doc)
        plane = self._std_plane_feature(doc, "front")
        if plane is None:
            return None, None
        if key in self._sim_frames:
            return plane, self._sim_frames[key]
        try:
            is_asm = int(doc.GetType) == 2
        except Exception:
            is_asm = False
        if is_asm and "__last__" in self._sim_frames:      # i piani standard hanno la stessa orientazione in ogni documento
            return plane, self._sim_frames["__last__"]
        self._exit_sketch(doc)                      # uno schizzo aperto farebbe chiudere QUELLO alla prima InsertSketch
        before = set(self._feature_names(doc, "ProfileFeature"))
        doc.ClearSelection2(True)
        plane.Select2(False, 0)
        doc.SketchManager.InsertSketch(True)
        try:
            info = self._sketch_plane_info(doc)
        finally:
            doc.SketchManager.InsertSketch(True)
            # si elimina SOLO lo schizzo temporaneo appena creato (prima si cancellava l'ultimo schizzo dell'albero,
            # che poteva essere dell'utente se quello temporaneo non era stato creato)
            for sk in [n for n in self._feature_names(doc, "ProfileFeature") if n not in before]:
                doc.ClearSelection2(True)
                self._select_feature(doc, sk)
                doc.Extension.DeleteSelection2(0)
            doc.ClearSelection2(True)
        fr = (info["sketch_x_axis"], info["sketch_y_axis"], info["sketch_normal"])
        self._sim_frames[key] = fr
        self._sim_frames["__last__"] = fr
        return plane, fr

    def _sim_comps(self, doc, vec):
        plane, fr = self._sim_plane_frame(doc)
        if plane is None:
            return None, None, "Nessun piano di riferimento nel documento"
        comps = [sum(vec[i] * ax[i] for i in range(3)) for ax in fr]
        return plane, comps, None

    # ------------------------------------------------------------------ vincoli e carichi
    def add_restraint(self, kind: str = "fixed", faces: list = None, study: str = None) -> Dict:
        """Vincolo su facce scelte per coordinate (mm): fixed (fisso) | immovable | symmetry | roller (rullo/scorrevole su faccia
        piana) | hinge (cerniera fissa su faccia cilindrica)."""
        try:
            t = _RESTRAINTS.get(str(kind).lower())
            if t is None:
                return self._result(False, f"Tipo vincolo sconosciuto '{kind}': {sorted(set(_RESTRAINTS))}", SwErrors.swInvalidInput)
            st, doc, sm, err = self._sim_study(study)
            if err:
                return err
            ents, e = self._sim_faces(doc, faces)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            ec = _bi()
            r = st.LoadsAndRestraintsManager.AddRestraint(t, _va(ents), _nullv(), ec)
            if r is None:
                hint = " ('immovable' vale solo per gusci/travi, non per solidi)" if t == 1 else ""
                return self._result(False, f"AddRestraint fallito (errore {ec.value}){hint}", SwErrors.swFeatureError)
            return self._result(True, f"Vincolo '{kind}' su {len(ents)} facce: {r.Name}", SwErrors.swSuccess,
                                {"name": r.Name, "kind": kind, "faces": len(ents)})
        except Exception as e:
            logger.error(f"add_restraint: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_force(self, faces: list, value: float, mode: str = "direction", direction: list = None,
                  study: str = None) -> Dict:
        """Forza (N) su facce per coordinate (mm). mode: 'normal' (normale alla faccia, valore>0 = verso l'interno... vedi nota),
        'direction' (vettore `direction` [dx,dy,dz] in coordinate modello, non serve normalizzarlo) o 'total' (= direction).
        Con piu' facce la forza e' applicata a OGNI faccia."""
        try:
            st, doc, sm, err = self._sim_study(study)
            if err:
                return err
            ents, e = self._sim_faces(doc, faces)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            lr = st.LoadsAndRestraintsManager
            ec = _bi()
            m = str(mode).lower()
            if m == "normal":
                f = lr.AddForce3(1, 0, -1, 0, 0, 0, _dbl(), _dbl(), False, False, 0, 0, 0, float(value), _dbl(1, 1, 1, 1, 1, 1),
                                 False, False, _va(ents), _nullv(), False, ec)
                desc = f"normale {value} N"
            else:
                if not direction or len(direction) != 3:
                    return self._result(False, "Serve direction=[dx,dy,dz]", SwErrors.swInvalidInput)
                nrm = sum(c * c for c in direction) ** 0.5
                if nrm == 0:
                    return self._result(False, "direction nulla", SwErrors.swInvalidInput)
                vec = [float(value) * c / nrm for c in direction]
                plane, comps, e = self._sim_comps(doc, vec)
                if e:
                    return self._result(False, e, SwErrors.swUnknownError)
                f = lr.AddForce3(0, 0, 2, 0, 0, 0, _dbl(), _dbl(), False, False, 0, 0, 7, 0.0, _dbl(*comps), False, False,
                                 _va(ents), plane, False, ec)
                desc = f"{value} N lungo {[round(c / nrm, 4) for c in direction]}"
            if f is None:
                return self._result(False, f"AddForce3 fallito (errore {ec.value})", SwErrors.swFeatureError)
            return self._result(True, f"Forza {desc}: {f.Name}", SwErrors.swSuccess,
                                {"name": f.Name, "mode": m, "value_N": value, "faces": len(ents)})
        except Exception as e:
            logger.error(f"add_force: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_torque(self, faces: list, value: float, axis_face: list, study: str = None) -> Dict:
        """Coppia (N*m) su facce, attorno all'asse di una FACCIA CILINDRICA di riferimento (punto `axis_face` [x,y,z] mm SULLA
        faccia cilindrica; un albero: coppia sulla faccia di estremita', asse = superficie dell'albero). Uno spigolo NON e' accettato (errore 4)."""
        try:
            st, doc, sm, err = self._sim_study(study)
            if err:
                return err
            ents, e = self._sim_faces(doc, faces)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            ref, e = self._sim_faces(doc, [axis_face])
            if e:
                return self._result(False, "asse: " + e, SwErrors.swSelectionError)
            ec = _bi()
            f = st.LoadsAndRestraintsManager.AddForce3(2, 0, 0, 0, 0, 0, _dbl(), _dbl(), False, False, 0, 0, 0, float(value),
                                                       _dbl(1, 1, 1, 1, 1, 1), False, False, _va(ents), ref[0], False, ec)
            if f is None:
                return self._result(False, f"Coppia non creata (errore {ec.value}; 10 = il riferimento deve essere una faccia "
                                           f"cilindrica o un asse)", SwErrors.swFeatureError)
            return self._result(True, f"Coppia {value} N*m: {f.Name}", SwErrors.swSuccess, {"name": f.Name})
        except Exception as e:
            logger.error(f"add_torque: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_pressure(self, faces: list, value: float, study: str = None) -> Dict:
        """Pressione normale (MPa = N/mm2) su facce per coordinate (mm). Valore positivo = verso l'interno della faccia."""
        try:
            st, doc, sm, err = self._sim_study(study)
            if err:
                return err
            ents, e = self._sim_faces(doc, faces)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            ec = _bi()
            p = st.LoadsAndRestraintsManager.AddPressure(0, _va(ents), _nullv(), ec)
            if p is None:
                return self._result(False, f"AddPressure fallito (errore {ec.value})", SwErrors.swFeatureError)
            p.PressureBeginEdit()
            p.Value = float(value) * 1e6    # unita' SI dell'oggetto: N/m2 (la proprieta' Unit non accetta N/mm2)
            rc = p.PressureEndEdit
            return self._result(True, f"Pressione {value} MPa: {p.Name}", SwErrors.swSuccess,
                                {"name": p.Name, "value_MPa": float(p.Value) / 1e6, "end_edit": rc})
        except Exception as e:
            logger.error(f"add_pressure: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_gravity(self, direction: list = None, acceleration: float = 9.80665, study: str = None) -> Dict:
        """Gravita': accelerazione (m/s2, default 9.80665) lungo `direction` [dx,dy,dz] in coordinate modello (default [0,0,-1])."""
        try:
            st, doc, sm, err = self._sim_study(study)
            if err:
                return err
            vec = direction or [0, 0, -1]
            nrm = sum(c * c for c in vec) ** 0.5
            plane, comps, e = self._sim_comps(doc, [acceleration * c / nrm for c in vec])
            if e:
                return self._result(False, e, SwErrors.swUnknownError)
            ec = _bi()
            g = st.LoadsAndRestraintsManager.AddGravity(plane, ec)
            if g is None:
                return self._result(False, f"AddGravity fallito (errore {ec.value})", SwErrors.swFeatureError)
            g.GravityBeginEdit()
            g.SetGravitationalAcclerationValues(float(comps[0]), float(comps[1]), float(comps[2]))
            rc = g.GravityEndEdit
            return self._result(True, f"Gravita' {acceleration} m/s2 lungo {vec}: {g.Name}", SwErrors.swSuccess,
                                {"name": g.Name, "end_edit": rc})
        except Exception as e:
            logger.error(f"add_gravity: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_temperature(self, faces: list, value: float, study: str = None) -> Dict:
        """Temperatura (gradi C) su facce per coordinate (mm). Solo studi termici."""
        try:
            st, doc, sm, err = self._sim_study(study)
            if err:
                return err
            if int(st.AnalysisType) != 3:
                return self._result(False, "add_temperature vale solo per studi termici (create_static_study analysis='thermal')",
                                    SwErrors.swInvalidInput)
            ents, e = self._sim_faces(doc, faces)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            ec = _bi()
            t = st.LoadsAndRestraintsManager.AddTemperature(_va(ents), ec)
            if t is None:
                return self._result(False, f"AddTemperature fallito (errore {ec.value})", SwErrors.swFeatureError)
            t.TemperatureBeginEdit()
            t.Unit = 2                      # Celsius
            t.TemperatureValue = float(value)
            rc = t.TemperatureEndEdit
            val = float(t.TemperatureValue)
            return self._result(True, f"Temperatura {val} gradi C su {len(ents)} facce: {t.Name}", SwErrors.swSuccess,
                                {"name": t.Name, "value_C": val, "end_edit": rc, "faces": len(ents)})
        except Exception as e:
            logger.error(f"add_temperature: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_remote_load(self, faces: list, point: list, force: list = None, moment: list = None, connection: str = "rigid",
                        study: str = None) -> Dict:
        """Carico remoto: forza (N) e/o momento (N*m) applicati nel punto `point` (mm, coordinate modello) e trasmessi alle facce con
        connessione rigida o distribuita. La forza e' nel riferimento globale del modello (verificato); il momento da verificare."""
        try:
            if not point or len(point) != 3:
                return self._result(False, "point = [x,y,z] in mm", SwErrors.swInvalidInput)
            for nm, v in (("force", force), ("moment", moment)):
                if v is not None and len(v) != 3:
                    return self._result(False, f"{nm} = [x,y,z]", SwErrors.swInvalidInput)
            if force is None and moment is None:
                return self._result(False, "Serve almeno uno fra force [fx,fy,fz] N e moment [mx,my,mz] N*m", SwErrors.swInvalidInput)
            ct = {"rigid": 0, "rigido": 0, "distributed": 1, "distribuito": 1}.get(str(connection).lower())
            if ct is None:
                return self._result(False, "connection: rigid | distributed", SwErrors.swInvalidInput)
            st, doc, sm, err = self._sim_study(study)
            if err:
                return err
            ents, e = self._sim_faces(doc, faces)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            ec = _bi()
            lr = st.LoadsAndRestraintsManager
            rl = lr.AddRemoteLoad(0, _va(ents), 0, float(point[0]), float(point[1]), float(point[2]), ec)
            if rl is None:
                return self._result(False, f"AddRemoteLoad fallito (errore {ec.value})", SwErrors.swFeatureError)
            rl.RemoteLoadBeginEdit()
            rl.ConnectionType = ct
            if force is not None:
                fx, fy, fz = (float(c) for c in force)
                rl.SetForceOrTranslationValues(True, fx != 0, fx, fy != 0, fy, fz != 0, fz)
            if moment is not None:
                mx, my, mz = (float(c) for c in moment)
                rl.SetMomentOrRotationValues(True, mx != 0, mx, my != 0, my, mz != 0, mz)
            rc = int(rl.RemoteLoadEndEdit)
            if rc != 0:
                msgs = {1: "seleziona faccia/spigolo/vertice", 2: "sistema di coordinate", 3: "tipo di carico", 4: "tipo di studio",
                        5: "array non valido", 6: "array vuoto", 7: "entita' gia' aggiunta", 8: "unita'"}
                return self._result(False, f"RemoteLoadEndEdit fallito: errore {rc} ({msgs.get(rc, '?')})", SwErrors.swFeatureError,
                                    {"name": rl.Name, "end_edit": rc})
            return self._result(True, f"Carico remoto {rl.Name} in {list(point)} mm: forza {force} N, momento {moment} N*m "
                                      f"(forza nel riferimento globale; momento da verificare)", SwErrors.swSuccess,
                                {"name": rl.Name, "point_mm": [float(c) for c in point], "force_N": force, "moment_Nm": moment,
                                 "connection": "rigid" if ct == 0 else "distributed", "end_edit": rc, "faces": len(ents)})
        except Exception as e:
            logger.error(f"add_remote_load: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_bearing_load(self, face: list, value: float, direction: list, distribution: str = "sinusoidal",
                         study: str = None) -> Dict:
        """Carico da cuscinetto (N) su una faccia CILINDRICA di un pezzo (punto `face` [x,y,z] mm sulla faccia), nella direzione
        `direction` (la componente lungo l'asse viene tolta). Crea uno schizzo 3D ausiliario e un sistema di coordinate (origine
        sull'asse del cilindro) che servono al carico e non vanno cancellati. distribution: sinusoidal | parabolic."""
        try:
            dist = {"sinusoidal": 0, "sinusoidale": 0, "parabolic": 1, "parabolica": 1}.get(str(distribution).lower())
            if dist is None:
                return self._result(False, "distribution: sinusoidal | parabolic", SwErrors.swInvalidInput)
            if not direction or len(direction) != 3:
                return self._result(False, "direction = [dx,dy,dz]", SwErrors.swInvalidInput)
            if face and isinstance(face[0], (list, tuple)):
                face = face[0]
            if not face or len(face) != 3:
                return self._result(False, "face = [x,y,z] in mm (UN punto sulla faccia cilindrica)", SwErrors.swInvalidInput)
            st, doc, sm, err = self._sim_study(study)
            if err:
                return err
            if int(doc.GetType) == 2:
                return self._result(False, "add_bearing_load: per ora solo nei pezzi", SwErrors.swInvalidInput)
            ents, e = self._sim_faces(doc, [face])
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            fc = ents[0]
            surf = fc.GetSurface
            if not surf.IsCylinder:
                return self._result(False, "La faccia non e' cilindrica", SwErrors.swInvalidInput)
            cp = [float(c) for c in surf.CylinderParams]
            o, ax = cp[0:3], cp[3:6]
            na = sum(c * c for c in ax) ** 0.5
            ax = [c / na for c in ax]
            d = [float(c) for c in direction]
            dot = sum(d[i] * ax[i] for i in range(3))
            xd = [d[i] - dot * ax[i] for i in range(3)]
            nx = sum(c * c for c in xd) ** 0.5
            if nx < 1e-9:
                return self._result(False, "direction e' parallela all'asse del cilindro: componente radiale nulla",
                                    SwErrors.swInvalidInput)
            xd = [c / nx for c in xd]
            self._exit_sketch(doc)
            before = set(self._feature_names(doc, "3DProfileFeature"))
            doc.ClearSelection2(True)
            skm = doc.SketchManager
            skm.Insert3DSketch(True)
            pt = skm.CreatePoint(*o)
            lz = skm.CreateLine(*o, *[o[i] + ax[i] * 0.01 for i in range(3)])
            lx = skm.CreateLine(*o, *[o[i] + xd[i] * 0.01 for i in range(3)])
            skm.Insert3DSketch(True)
            helper = [n for n in self._feature_names(doc, "3DProfileFeature") if n not in before]
            doc.ClearSelection2(True)
            smg = doc.SelectionManager
            for obj, mk, app in ((pt, 1, False), (lx, 2, True), (lz, 8, True)):
                sd = smg.CreateSelectData
                sd.Mark = mk
                obj.Select4(app, sd)
            csf = doc.FeatureManager.InsertCoordinateSystem(False, False, False)
            doc.ClearSelection2(True)
            if csf is None:
                return self._result(False, "Sistema di coordinate non creato (schizzo ausiliario: %s)" % helper, SwErrors.swFeatureError,
                                    {"helper_sketch": helper})
            ec = _bi()
            bl = st.LoadsAndRestraintsManager.AddBearingLoad(csf, _va([fc]), ec)
            if bl is None:
                msgs = {1: "array non valido", 2: "nessun oggetto per la faccia", 3: "sistema di coordinate vuoto",
                        4: "seleziona una faccia", 5: "seleziona il sistema di coordinate",
                        6: "asse Z del sistema di coordinate non coincidente con l'asse del cilindro", 7: "mesh non valida",
                        8: "studio non valido", 9: "corpo escluso"}
                return self._result(False, f"AddBearingLoad fallito (errore {ec.value}: {msgs.get(int(ec.value), '?')}); "
                                          f"creati comunque {csf.Name} e lo schizzo {helper}", SwErrors.swFeatureError,
                                    {"coordinate_system": csf.Name, "helper_sketch": helper})
            bl.BearingLoadBeginEdit()
            bl.BearingLoadUnit = 0
            bl.XDirectionValue = float(value)
            bl.DistributionType = dist
            rc = bl.BearingLoadEndEdit
            return self._result(True, f"Carico da cuscinetto {value} N ({distribution}): {bl.Name}", SwErrors.swSuccess,
                                {"name": bl.Name, "coordinate_system": csf.Name, "helper_sketch": helper,
                                 "axis": [round(c, 6) for c in ax], "direction_used": [round(c, 6) for c in xd],
                                 "end_edit": rc, "note": "lo schizzo 3D e il sistema di coordinate servono al carico: non cancellarli"})
        except Exception as e:
            logger.error(f"add_bearing_load: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_simulation_contact(self, faces1: list, faces2: list, contact: str = "bonded", study: str = None) -> Dict:
        """Contatto locale fra facce di componenti diversi di un assieme (sostituisce il globale su quelle facce).
        contact: no_penetration | bonded | shrink_fit | free | virtual_wall. faces1/faces2 = punti sulle facce (che coincidono):
        faces1 = facce piu' vicine, faces2 = facce piu' vicine fra i componenti DIVERSI da quelli di faces1."""
        try:
            t = _CONTACTS_LOCAL.get(str(contact).lower())
            if t is None:
                return self._result(False, f"contact: {sorted(set(_CONTACTS_LOCAL))}", SwErrors.swInvalidInput)
            if not faces1 or not faces2:
                return self._result(False, "Servono faces1 e faces2 ([[x,y,z],...] in mm)", SwErrors.swInvalidInput)
            st, doc, sm, err = self._sim_study(study)
            if err:
                return err
            if int(doc.GetType) != 2:
                return self._result(False, "I contatti locali valgono solo per gli assiemi", SwErrors.swInvalidInput)
            keep = []
            ents1, comps1 = [], set()
            for p in faces1:
                ent, d, cn = self._sim_find_asm_face(doc, [float(c) / 1000.0 for c in p], 1e-4, want_comp=True)
                keep.append(self._sim_keep_asm)
                if ent is None:
                    return self._result(False, f"Nessuna faccia entro 0,1 mm dal punto {list(p)} (faces1)", SwErrors.swSelectionError)
                ents1.append(ent)
                comps1.add(cn)
            ents2, comps2 = [], set()
            for p in faces2:
                ent, d, cn = self._sim_find_asm_face(doc, [float(c) / 1000.0 for c in p], 1e-4, exclude_components=comps1,
                                                     want_comp=True)
                keep.append(self._sim_keep_asm)
                if ent is None:
                    return self._result(False, f"Nessuna faccia entro 0,1 mm dal punto {list(p)} fra i componenti diversi da "
                                               f"{sorted(c for c in comps1 if c)} (faces2)", SwErrors.swSelectionError)
                ents2.append(ent)
                comps2.add(cn)
            self._sim_keep_contact = keep
            ec = _bi()
            cs = st.ContactManager.CreateContactSet(t, _va(ents1), _va(ents2), ec)
            if cs is None:
                return self._result(False, f"CreateContactSet fallito (errore {ec.value})", SwErrors.swFeatureError)
            return self._result(True, f"Contatto locale '{contact}': {cs.ContactName}", SwErrors.swSuccess,
                                {"name": cs.ContactName, "contact": contact, "type_code": t, "sources": int(cs.SourceEntityCount),
                                 "targets": int(cs.TargetEntityCount), "components1": sorted(c for c in comps1 if c),
                                 "components2": sorted(c for c in comps2 if c)})
        except Exception as e:
            logger.error(f"add_simulation_contact: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def add_mesh_control(self, faces: list, element_size: float, ratio: float = 1.5, study: str = None) -> Dict:
        """Controllo locale della mesh sulle facce (mm): elementi piu' piccoli vicino a fori e raccordi; poi rifare la mesh."""
        try:
            st, doc, sm, err = self._sim_study(study)
            if err:
                return err
            ents, e = self._sim_faces(doc, faces)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            ec = _bi()
            mc = st.Mesh.ApplyMeshControl(_va(ents), ec)
            if mc is None:
                return self._result(False, f"ApplyMeshControl fallito (errore {ec.value})", SwErrors.swFeatureError)
            mc.MeshControlBeginEdit()
            mc.Units = 0
            mc.ElementSize = float(element_size)
            mc.Ratio = float(ratio)
            rc = mc.MeshControlEndEdit
            return self._result(True, f"Controllo mesh {mc.Name}: {float(mc.ElementSize)} mm, rapporto {float(mc.Ratio)} su "
                                      f"{len(ents)} facce (rifai create_simulation_mesh)", SwErrors.swSuccess,
                                {"name": mc.Name, "element_size_mm": float(mc.ElementSize), "ratio": float(mc.Ratio),
                                 "end_edit": rc, "faces": len(ents), "note": "rifai create_simulation_mesh perche' il controllo abbia effetto"})
        except Exception as e:
            logger.error(f"add_mesh_control: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def list_simulation_loads(self, study: str = None) -> Dict:
        """Vincoli e carichi dello studio, piu' contatti locali e controlli mesh."""
        try:
            st, doc, sm, err = self._sim_study(study)
            if err:
                return err
            lr = st.LoadsAndRestraintsManager
            kinds = {1: "pressione", 2: "vincolo", 3: "forza", 4: "gravita'", 5: "centrifuga", 12: "connettore"}
            rows = []
            for i in range(int(lr.Count)):
                x = lr.GetLoadsAndRestraints(i, _bi())
                rows.append({"name": x.Name, "type": kinds.get(int(x.Type), int(x.Type)), "entities": int(x.EntityCount)})
            try:
                cm = st.ContactManager
                for i in range(int(cm.ContactSetCount)):
                    rows.append({"name": cm.GetContactSetAt(i).ContactName, "type": "contatto"})
            except Exception as ex:
                logger.debug(f"contatti locali non elencati: {ex}")
            try:
                for i in range(int(st.Mesh.MeshControlCount)):
                    rows.append({"name": st.Mesh.GetMeshControlAt(i).Name, "type": "controllo mesh"})
            except Exception as ex:
                logger.debug(f"controlli mesh non elencati: {ex}")
            return self._result(True, f"{len(rows)} tra carichi, vincoli, contatti locali e controlli mesh", SwErrors.swSuccess,
                                {"items": rows})
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def delete_simulation_load(self, name: str, study: str = None) -> Dict:
        """Elimina un carico, vincolo, contatto locale o controllo mesh per nome."""
        try:
            st, doc, sm, err = self._sim_study(study)
            if err:
                return err
            lr = st.LoadsAndRestraintsManager
            n0 = int(lr.Count)
            lr.DeleteLoadsAndRestraints(name)
            n1 = int(lr.Count)
            if n1 >= n0:
                try:
                    cm = st.ContactManager
                    c0 = int(cm.ContactSetCount)
                    cm.DeleteContactSet(name)
                    if int(cm.ContactSetCount) < c0:
                        return self._result(True, f"Contatto locale '{name}' eliminato", SwErrors.swSuccess,
                                            {"remaining": int(cm.ContactSetCount), "kind": "contatto"})
                except Exception as ex:
                    logger.debug(f"DeleteContactSet: {ex}")
                try:
                    m0 = int(st.Mesh.MeshControlCount)
                    st.Mesh.DeleteMeshControl(name)
                    if int(st.Mesh.MeshControlCount) < m0:
                        return self._result(True, f"Controllo mesh '{name}' eliminato", SwErrors.swSuccess,
                                            {"remaining": int(st.Mesh.MeshControlCount), "kind": "controllo mesh"})
                except Exception as ex:
                    logger.debug(f"DeleteMeshControl: {ex}")
            return self._result(n1 < n0, f"'{name}' {'eliminato' if n1 < n0 else 'non trovato'}",
                                SwErrors.swSuccess if n1 < n0 else SwErrors.swInvalidInput, {"remaining": n1})
        except Exception as e:
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def set_simulation_contact(self, contact: str = "bonded", study: str = None) -> Dict:
        """Contatto globale dello studio (assiemi): 'bonded' (incollato), 'free' (libero/penetrazione consentita),
        'no_penetration' (solo studi non lineari)."""
        try:
            st, doc, sm, err = self._sim_study(study)
            if err:
                return err
            t = {"bonded": 0, "incollato": 0, "free": 1, "libero": 1, "no_penetration": 2}.get(str(contact).lower())
            if t is None:
                return self._result(False, "contact: bonded | free | no_penetration", SwErrors.swInvalidInput)
            cm = st.ContactManager
            rc = cm.SetGlobalContact(t, 0)
            return self._result(True, f"Contatto globale '{contact}' impostato (rc={rc})", SwErrors.swSuccess, {"rc": rc})
        except Exception as e:
            logger.error(f"set_simulation_contact: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ mesh
    def _sim_nodes(self, st) -> Dict[int, tuple]:
        a = st.Mesh.GetNodes
        return {int(a[i]): (a[i + 1], a[i + 2], a[i + 3]) for i in range(0, len(a), 4)}

    def _sim_mesh_info(self, st) -> Dict:
        m = st.Mesh
        info: Dict[str, Any] = {"mesh_state": int(m.MeshState), "nodes": int(m.NodeCount), "elements": int(m.ElementCount),
                                "max_aspect_ratio": round(float(m.MaxAspectRatio), 3)}
        try:
            info["worst_jacobian_ratio"] = round(float(m.GetWorstJacobianRatio), 4)
        except Exception:
            pass
        try:
            els = m.GetElements
            ars = [els[i + 14] for i in range(0, len(els), 16)]
            n = len(ars)
            info["aspect_ratio"] = {"mean": round(sum(ars) / n, 3), "max": round(max(ars), 3),
                                    "pct_over_3": round(100 * sum(1 for a in ars if a > 3) / n, 2),
                                    "pct_over_10": round(100 * sum(1 for a in ars if a > 10) / n, 2)}
        except Exception:
            pass
        info["quality_ok"] = info["mesh_state"] == 1 and info["max_aspect_ratio"] < 50
        return info

    def create_simulation_mesh(self, element_size: float = None, tolerance: float = None, mesher: str = "standard",
                               quality: str = "high", min_element_size: float = None, growth_ratio: float = None,
                               min_elements_in_circle: int = None, study: str = None) -> Dict:
        """Crea la mesh solida (tetraedri). mesher: 'standard' | 'curvature' (basata sulla curvatura). element_size in mm
        (default = quello globale proposto da SW; con 'curvature' e' la dimensione MASSIMA e min_element_size la minima);
        tolerance mm (default 5 % della dimensione). Restituisce nodi, elementi e controllo qualita'."""
        try:
            st, doc, sm, err = self._sim_study(study)
            if err:
                return err
            mesh = st.Mesh
            mt = {"standard": 0, "curvature": 2, "curvature_based": 2, "curvatura": 2}.get(str(mesher).lower())
            if mt is None:
                return self._result(False, "mesher: standard | curvature", SwErrors.swInvalidInput)
            es, tol = _br(), _br()
            mesh.GetDefaultElementSizeAndTolerance(0, es, tol)
            size = float(element_size) if element_size else float(es.value)
            tl = float(tolerance) if tolerance else (size * 0.05 if element_size else float(tol.value))
            mesh.MesherType = mt
            mesh.Quality = 1 if str(quality).lower() in ("high", "alta") else 0
            if mt == 2:
                try:
                    mesh.Unit = 0
                    mesh.MaxElementSize = size
                    mesh.MinElementSize = float(min_element_size) if min_element_size else size / 3.0
                    if growth_ratio:
                        mesh.GrowthRatio = float(growth_ratio)
                    if min_elements_in_circle:
                        mesh.MinElementsInCircle = int(min_elements_in_circle)
                except Exception as e:
                    logger.warning(f"parametri mesh curvatura: {e}")
            t0 = time.time()
            rc = st.CreateMesh(0, size, tl)
            dt = time.time() - t0
            info = self._sim_mesh_info(st)
            info.update({"element_size_mm": round(size, 4), "tolerance_mm": round(tl, 4), "mesher": mesher,
                         "seconds": round(dt, 2), "rc": int(rc)})
            ok = int(rc) == 0 and info["mesh_state"] == 1
            return self._result(ok, f"Mesh {mesher}: {info['nodes']} nodi, {info['elements']} elementi, AR max "
                                    f"{info['max_aspect_ratio']} ({dt:.1f} s)" if ok else f"Mesh fallita (rc={rc})",
                                SwErrors.swSuccess if ok else SwErrors.swFeatureError, info)
        except Exception as e:
            logger.error(f"create_simulation_mesh: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ esecuzione
    def run_simulation(self, timeout: float = 300, study: str = None) -> Dict:
        """Esegue lo studio (la mesh va creata prima). `timeout` in secondi: la chiamata COM e' bloccante e non interrompibile; allo
        scadere, in modalita' ISTANZA DEDICATA il processo SolidWorks viene chiuso (kill del PID esatto) e si restituisce errore;
        sull'istanza dell'utente NON si uccide nulla (il tool restituisce comunque il risultato, con timeout_exceeded=true)."""
        try:
            st, doc, sm, err = self._sim_study(study)
            if err:
                return err
            if int(st.Mesh.MeshState) != 1:
                return self._result(False, "Mesh assente o non aggiornata: usa create_simulation_mesh", SwErrors.swInvalidInput)
            flag = {"done": False, "killed": False}
            pid = self._dedicated_pid

            def watchdog():
                end = time.time() + float(timeout)
                while time.time() < end:
                    if flag["done"]:
                        return
                    time.sleep(0.5)
                if not flag["done"] and pid and self.is_dedicated_mode():
                    import subprocess
                    flag["killed"] = True
                    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
            th = threading.Thread(target=watchdog, daemon=True)
            th.start()
            t0 = time.time()
            try:
                rc = int(st.RunAnalysis)
            except Exception as e:
                flag["done"] = True
                if flag["killed"]:
                    self._connected = False
                    self._sw_app = None
                    return self._result(False, f"Timeout di {timeout} s: istanza dedicata (PID {pid}) terminata", SwErrors.swUnknownError)
                raise e
            flag["done"] = True
            dt = time.time() - t0
            exceeded = dt > float(timeout)
            if rc != 0:
                return self._result(False, f"Analisi fallita: errore {rc} ({_ERR_RUN.get(rc, '?')})", SwErrors.swUnknownError,
                                    {"rc": rc})
            return self._result(True, f"Analisi completata in {dt:.1f} s", SwErrors.swSuccess,
                                {"seconds": round(dt, 2), "timeout_exceeded": exceeded,
                                 "steps": int(st.Results.GetMaximumAvailableSteps)})
        except Exception as e:
            logger.error(f"run_simulation: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    # ------------------------------------------------------------------ risultati
    @staticmethod
    def _sim_mm(p):
        return [round(c * 1000, 4) for c in p]

    def _sim_results_frequency(self, st, res) -> Dict:
        data: Dict[str, Any] = {"mesh": self._sim_mesh_info(st)}
        f = list(res.GetResonantFrequencies(_bi()) or [])
        mp = list(res.GetMassParticipation(_bi()) or [])
        part = {int(mp[i]): (mp[i + 1], mp[i + 2], mp[i + 3]) for i in range(0, len(mp) - 3, 4)}
        modes = []
        for i in range(0, len(f) - 3, 4):
            k = int(f[i])
            row = {"mode": k, "frequency_Hz": f[i + 2], "angular_rad_s": f[i + 1], "period_s": f[i + 3]}
            if k in part:
                row["mass_participation"] = {"x": part[k][0], "y": part[k][1], "z": part[k][2]}
            modes.append(row)
        data["modes"] = modes
        data["plots"] = list(res.GetPlotNames)
        if not modes:
            return self._result(False, "Nessuna frequenza restituita (analisi eseguita?)", SwErrors.swInvalidInput, data)
        return self._result(True, f"{len(modes)} modi, f1 = {modes[0]['frequency_Hz']:.3f} Hz", SwErrors.swSuccess, data)

    def _sim_results_buckling(self, st, res) -> Dict:
        data: Dict[str, Any] = {"mesh": self._sim_mesh_info(st)}
        b = list(res.GetBucklingLoadFactors(_bi()) or [])
        rows = [{"mode": int(b[i]), "load_factor": b[i + 1]} for i in range(0, len(b) - 1, 2)]
        data["buckling_load_factors"] = rows
        data["note"] = "carico critico = fattore x carichi applicati"
        data["plots"] = list(res.GetPlotNames)
        if not rows:
            return self._result(False, "Nessun fattore di carico restituito (analisi eseguita?)", SwErrors.swInvalidInput, data)
        return self._result(True, f"{len(rows)} modi, fattore di carico del 1o modo {rows[0]['load_factor']:.4f}",
                            SwErrors.swSuccess, data)

    def _sim_results_thermal(self, st, res, step) -> Dict:
        nodes = self._sim_nodes(st)
        data: Dict[str, Any] = {"mesh": self._sim_mesh_info(st)}

        def mm(comp, unit):
            return res.GetMinMaxThermal(comp, step, _nullv(), unit, _bi())      # (id_min, min, id_max, max)

        a = mm(0, 2)
        data["temperature_C"] = {"min": a[1], "max": a[3], "min_at_mm": self._sim_mm(nodes[int(a[0])]),
                                 "max_at_mm": self._sim_mm(nodes[int(a[2])])}
        a = mm(4, 0)
        data["temperature_gradient_K_m"] = {"min": a[1], "max": a[3]}
        a = mm(8, 0)
        data["heat_flux_W_m2"] = {"min": a[1], "max": a[3], "max_at_mm": self._sim_mm(nodes[int(a[2])])}
        comp = {}
        for nm, c in (("x", 5), ("y", 6), ("z", 7)):
            a = mm(c, 0)
            comp[nm] = {"min": a[1], "max": a[3]}
        data["heat_flux_components_W_m2"] = comp
        data["plots"] = list(res.GetPlotNames)
        t = data["temperature_C"]
        return self._result(True, f"Temperatura {t['min']:.3f}..{t['max']:.3f} gradi C, flusso max "
                                  f"{data['heat_flux_W_m2']['max']:.4g} W/m2", SwErrors.swSuccess, data)

    def _sim_sw_bodies(self, doc):
        """[(nome del componente | None, corpo SolidWorks)] in ordine (pezzo: GetBodies2; assieme: corpi dei componenti)."""
        out, keep = [], []
        if int(doc.GetType) == 2:
            for comp in doc.GetComponents(False) or []:
                keep.append(comp)
                for b in (comp.GetBodies2(0) or []):
                    out.append((comp.Name2, b))
        else:
            for b in (doc.GetBodies2(0, True) or []):
                out.append((None, b))
        self._sim_keep_swb = keep + [b for _, b in out]
        return out

    def _sim_match_bodies(self, sim_bodies, sw_bodies):
        """Abbina i corpi di simulazione [(nome componente, corpo)] ai corpi SolidWorks [(nome componente, corpo)]:
        per nome del componente e poi per ordine dei corpi; se i nomi non corrispondono, per ordine globale se i conteggi sono uguali."""
        def norm(n):
            return (n or "").split("/")[-1].lower()
        by_name: Dict[str, list] = {}
        for cn, b in sw_bodies:
            by_name.setdefault(norm(cn), []).append(b)
        pairs, used = [], {}
        for cn, sb in sim_bodies:
            key = norm(cn)
            lst = by_name.get(key)
            if lst is None and len(by_name) == 1 and None in [c for c, _ in sw_bodies]:
                lst = next(iter(by_name.values()))      # pezzo: un solo gruppo, per ordine
            k = used.get(key, 0)
            if lst is None or k >= len(lst):
                pairs = None
                break
            used[key] = k + 1
            pairs.append((cn, sb, lst[k]))
        if pairs is None and len(sim_bodies) == len(sw_bodies):
            pairs = [(cn, sb, sw[1]) for (cn, sb), sw in zip(sim_bodies, sw_bodies)]
        return pairs

    def _sim_fos_location(self, st, doc, res, step, api_min, nodes, vm_global) -> Dict:
        """Posizione del FOS minimo (criterio von Mises: FOS = snervamento / VM nodale massimo del corpo)."""
        sim_bodies = self._sim_bodies(st)
        pairs = None
        try:
            pairs = self._sim_match_bodies(sim_bodies, self._sim_sw_bodies(doc))
        except Exception as ex:
            logger.debug(f"abbinamento corpi: {ex}")
        per_body = []
        if pairs:
            for cn, sb, swb in pairs:
                a = res.GetStressForEntities2(True, 9, step, _nullv(), _va([swb]), 3, _bi())
                best_v, best_n = -1.0, None
                for i in range(0, len(a) - 1, 2):
                    if float(a[i + 1]) > best_v:
                        best_v, best_n = float(a[i + 1]), int(a[i])
                per_body.append((cn, sb, best_v, best_n))
        else:
            # abbinamento non riuscito: con un solo materiale il minimo e' nel nodo del VM massimo globale
            mats = {self._sim_mat_props(sb.GetSolidBodyMaterial).get("name") for _, sb in sim_bodies}
            if not sim_bodies or len(mats) != 1:
                return {"location_error": "abbinamento corpo SolidWorks <-> corpo di simulazione non riuscito (materiali diversi)"}
            cn, sb = sim_bodies[0]
            per_body.append((cn, sb, float(vm_global["max"]), int(vm_global["max_node"])))
        rows = []
        for cn, sb, vmax, node in per_body:
            mat = self._sim_mat_props(sb.GetSolidBodyMaterial)
            y = mat.get("yield_MPa")
            if not y or vmax <= 0 or node is None:
                continue
            rows.append({"component": cn, "body": sb.SolidBodyName, "material": mat.get("name"), "yield_MPa": y,
                         "von_mises_max_MPa": vmax, "fos": y / vmax, "node": node})
        if not rows:
            return {"location_error": "nessun corpo con snervamento e tensione valida"}
        worst = min(rows, key=lambda r: r["fos"])
        out = {"min_at_mm": self._sim_mm(nodes[worst["node"]]), "min_node": worst["node"],
               "min_body": {k: worst[k] for k in ("component", "body", "material", "yield_MPa", "von_mises_max_MPa")},
               "per_body": [{k: r[k] for k in ("component", "body", "material", "yield_MPa", "von_mises_max_MPa", "fos")}
                            for r in rows],
               "computed_min": worst["fos"], "note": "criterio von Mises: FOS = snervamento / VM nodale"}
        if api_min:
            out["check_rel"] = abs(worst["fos"] - api_min) / abs(api_min)
        return out

    def get_simulation_results(self, study: str = None, step: int = 1, moment_point: list = None) -> Dict:
        """Risultati dello studio, secondo il tipo. Statico: von Mises max/min (MPa) con posizione (mm; nodale come la mappa e
        elementale), spostamento risultante max (mm) con posizione, spostamenti per componente, fattore di sicurezza minimo/massimo
        con posizione e corpo, forze e momenti di reazione totali (somma sui nodi vincolati, N e N*m; momento attorno a
        `moment_point` [x,y,z] mm, default origine), nodi/elementi della mesh. Frequenze: frequenze proprie e partecipazione di
        massa. Buckling: fattori di carico. Termico: temperatura, gradiente, flusso."""
        try:
            st, doc, sm, err = self._sim_study(study)
            if err:
                return err
            res = st.Results
            if int(res.GetMaximumAvailableSteps) < 1:
                return self._result(False, "Nessun risultato: esegui run_simulation", SwErrors.swInvalidInput)
            atype = int(st.AnalysisType)
            if atype == 1:
                return self._sim_results_frequency(st, res)
            if atype == 2:
                return self._sim_results_buckling(st, res)
            if atype == 3:
                return self._sim_results_thermal(st, res, step)
            if atype != 0:
                return self._result(False, f"Tipo di studio {atype} non supportato da get_simulation_results", SwErrors.swInvalidInput)
            if moment_point is not None and len(moment_point) != 3:
                return self._result(False, "moment_point = [x,y,z] in mm", SwErrors.swInvalidInput)
            q = [float(c) / 1000.0 for c in (moment_point or [0, 0, 0])]
            nodes = self._sim_nodes(st)
            els = st.Mesh.GetElements
            cen = {int(els[i]): (els[i + 11], els[i + 12], els[i + 13]) for i in range(0, len(els), 16)}
            data: Dict[str, Any] = {"mesh": self._sim_mesh_info(st)}
            e = _bi()
            a = res.GetMinMaxStress(9, 0, step, _nullv(), 3, e)
            data["von_mises_nodal_MPa"] = {"min": a[1], "min_node": int(a[0]), "min_at_mm": self._sim_mm(nodes[int(a[0])]),
                                           "max": a[3], "max_node": int(a[2]), "max_at_mm": self._sim_mm(nodes[int(a[2])])}
            a = res.GetMinMaxStress(9, 1, step, _nullv(), 3, _bi())
            data["von_mises_element_MPa"] = {"min": a[1], "min_element": int(a[0]), "min_at_mm": self._sim_mm(cen[int(a[0])]),
                                             "max": a[3], "max_element": int(a[2]), "max_at_mm": self._sim_mm(cen[int(a[2])])}
            a = res.GetMinMaxDisplacement(3, step, _nullv(), 0, _bi())
            data["displacement_mm"] = {"max": a[3], "max_node": int(a[2]), "max_at_mm": self._sim_mm(nodes[int(a[2])]),
                                       "min": a[1]}
            comp = {}
            for nm, c in (("ux", 0), ("uy", 1), ("uz", 2)):
                a = res.GetMinMaxDisplacement(c, step, _nullv(), 0, _bi())
                comp[nm] = {"min": a[1], "max": a[3]}
            data["displacement_components_mm"] = comp
            try:
                a = res.GetMinMaxFactorOfSafety2(True, _nullv(), 0, 0, step, _bi())
                data["factor_of_safety"] = {"min": a[0], "max": a[1], "note": "criterio von Mises max; l'API non da' la posizione"}
                try:
                    data["factor_of_safety"].update(self._sim_fos_location(st, doc, res, step, a[0], nodes,
                                                                           data["von_mises_nodal_MPa"]))
                except Exception as ex:
                    data["factor_of_safety"]["location_error"] = str(ex)
            except Exception as ex:
                data["factor_of_safety"] = {"error": str(ex)}
            r = res.GetReactionForcesAndMoments(step, _nullv(), 0, _bi())
            n = len(r) // 9
            tot = [sum(r[i * 9 + k] for i in range(n)) for k in (1, 2, 3)]
            data["reaction_force_N"] = {"x": round(tot[0], 4), "y": round(tot[1], 4), "z": round(tot[2], 4),
                                        "resultant": round(sum(c * c for c in tot) ** 0.5, 4)}
            mom = [0.0, 0.0, 0.0]
            for i in range(n):
                p = nodes.get(int(r[i * 9]))
                if p is None:
                    continue
                d = [p[0] - q[0], p[1] - q[1], p[2] - q[2]]
                f = (r[i * 9 + 1], r[i * 9 + 2], r[i * 9 + 3])
                mom[0] += d[1] * f[2] - d[2] * f[1] + r[i * 9 + 5]
                mom[1] += d[2] * f[0] - d[0] * f[2] + r[i * 9 + 6]
                mom[2] += d[0] * f[1] - d[1] * f[0] + r[i * 9 + 7]
            data["reaction_moment_Nm"] = {"x": round(mom[0], 4), "y": round(mom[1], 4), "z": round(mom[2], 4),
                                          "resultant": round(sum(c * c for c in mom) ** 0.5, 4)}
            data["reaction_moment_point_mm"] = [round(c * 1000, 4) for c in q]
            data["plots"] = list(res.GetPlotNames)
            vm = data["von_mises_nodal_MPa"]["max"]
            return self._result(True, f"VM max {vm:.3f} MPa, spostamento max {data['displacement_mm']['max']:.5f} mm, "
                                      f"FOS min {data['factor_of_safety'].get('min')}", SwErrors.swSuccess, data)
        except Exception as e:
            logger.error(f"get_simulation_results: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def get_simulation_stress_on_faces(self, faces: list, box: list = None, component: str = "vonmises", study: str = None,
                                       step: int = 1) -> Dict:
        """Tensione nodale (MPa) sui nodi delle facce indicate (coordinate mm), opzionalmente solo nei nodi dentro il box
        [xmin,ymin,zmin,xmax,ymax,zmax] (mm). Serve a misurare LONTANO dalle singolarita' (es. a meta' trave).
        Restituisce min/max/media, numero di nodi e il nodo del massimo."""
        try:
            st, doc, sm, err = self._sim_study(study)
            if err:
                return err
            c = _COMPONENTS.get(str(component).lower())
            if c is None:
                return self._result(False, f"component: {sorted(_COMPONENTS)}", SwErrors.swInvalidInput)
            if box is not None and len(box) != 6:
                return self._result(False, "box = [xmin,ymin,zmin,xmax,ymax,zmax] in mm", SwErrors.swInvalidInput)
            ents, e = self._sim_faces(doc, faces)
            if e:
                return self._result(False, e, SwErrors.swSelectionError)
            nodes = self._sim_nodes(st)
            a = st.Results.GetStressForEntities2(True, c, step, _nullv(), _va(ents), 3, _bi())
            if not a:
                return self._result(False, "Nessun valore restituito (risultati assenti?)", SwErrors.swInvalidInput)
            vals = []
            for i in range(0, len(a), 2):
                nid = int(a[i])
                p = nodes.get(nid)
                if p is None:
                    continue
                if box is not None and not all(box[k] - 1e-6 <= p[k] * 1000 <= box[k + 3] + 1e-6 for k in range(3)):
                    continue
                vals.append((float(a[i + 1]), nid, p))
            if not vals:
                return self._result(False, "Nessun nodo nel box sulle facce indicate", SwErrors.swInvalidInput)
            v = [x[0] for x in vals]
            top = max(vals)
            return self._result(True, f"{len(vals)} nodi: {min(v):.3f}..{max(v):.3f} MPa", SwErrors.swSuccess,
                                {"nodes": len(vals), "min_MPa": min(v), "max_MPa": max(v), "mean_MPa": sum(v) / len(v),
                                 "max_node": top[1], "max_at_mm": self._sim_mm(top[2]), "component": component})
        except Exception as e:
            logger.error(f"get_simulation_stress_on_faces: {e} {traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)

    def export_simulation_plot(self, filepath: str, result: str = "von_mises", view: str = "isometric",
                               study: str = None) -> Dict:
        """Esporta in PNG la mappa a colori dei risultati. result: von_mises | displacement | strain | un nome di grafico esistente."""
        try:
            st, doc, sm, err = self._sim_study(study)
            if err:
                return err
            res = st.Results
            names = list(res.GetPlotNames)
            cands = plot_candidates(result, names)          # Stress1 / Sollecitazione1 ... in ogni lingua
            name = cands[0] if cands else None
            if name is None:
                return self._result(False, f"Grafico '{result}' non trovato: {names}", SwErrors.swInvalidInput)
            if not res.ActivatePlot(name):
                return self._result(False, f"ActivatePlot('{name}') fallito", SwErrors.swUnknownError)
            vid = {"isometric": 7, "front": 1, "back": 2, "left": 3, "right": 4, "top": 5, "bottom": 6}.get(str(view).lower(), 7)
            doc.ShowNamedView2("", vid)
            doc.ViewZoomtofit2()
            fp = os.path.abspath(filepath)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            if os.path.exists(fp):
                os.remove(fp)
            ok = doc.Extension.SaveAs(fp, 0, 1, _nullv(), _bi(), _bi())
            size = os.path.getsize(fp) if os.path.exists(fp) else 0
            if not ok or size == 0:
                return self._result(False, "Esportazione PNG fallita", SwErrors.swUnknownError)
            return self._result(True, f"Grafico '{name}' esportato: {fp} ({size} byte)", SwErrors.swSuccess,
                                {"filepath": fp, "plot": name, "bytes": size})
        except Exception as e:
            logger.error(f"export_simulation_plot: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Errore: {e}", SwErrors.swUnknownError)
