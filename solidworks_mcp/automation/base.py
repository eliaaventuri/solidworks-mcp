"""
SolidWorks Automation Base
--------------------------
Core automation class with connection management and utility methods.
"""

import os
import time
import logging
import datetime
import traceback
import subprocess
from typing import Optional, Dict, Any, Tuple

# COM imports
import win32com.client
import pythoncom

from ..constants import SwErrors
from ..config import get_config
from ..utils import UnitConverter, find_solidworks
from ..utils.sw_lang import std_plane_index, is_origin_name

logger = logging.getLogger(__name__)

# HRESULT di un server COM che non c'e' piu' (processo uscito, oggetto scollegato): l'istanza e' persa
_COM_GONE = {-2147023174,    # RPC_S_SERVER_UNAVAILABLE 0x800706BA
             -2147023170,    # RPC_S_CALL_FAILED 0x800706BE
             -2147417848,    # RPC_E_DISCONNECTED 0x80010108
             -2147220995}    # CO_E_OBJNOTCONNECTED 0x800401FD
# HRESULT di un'istanza viva ma occupata (finestra modale, ricostruzione in corso): si riprova, non e' persa
_COM_BUSY = {-2147418111,    # RPC_E_CALL_REJECTED 0x80010001
             -2147417846}    # RPC_E_SERVERCALL_RETRYLATER 0x8001010A


def _hresult(e) -> Optional[int]:
    """HRESULT di un'eccezione COM (pywintypes.com_error: attributo hresult o primo argomento), None se non c'e'."""
    hr = getattr(e, "hresult", None)
    if hr is None and getattr(e, "args", None):
        hr = e.args[0]
    try:
        return int(hr)
    except (TypeError, ValueError):
        return None


class SolidWorksAutomation:
    """
    Core SolidWorks automation class
    
    Handles connection management, document operations, and provides
    utility methods for all automation tasks.
    """
    
    def __init__(self):
        """Initialize automation instance"""
        self._sw_app = None
        self._connected = False
        self._config = get_config()
        self._units = UnitConverter(self._config.default_unit)
        self._sw_exe_path = None
        self._dedicated_pid = None      # PID of the private SolidWorks instance (dedicated mode)
        self._dedicated_proc = None
        
        logger.info("SolidWorksAutomation initialized")
    
    # ========================================================================
    # Properties
    # ========================================================================
    
    @property
    def is_connected(self) -> bool:
        """SolidWorks risponde? Un errore COM PASSEGGERO non vale come istanza persa (revisione 2026-11-12): prima ogni errore
        azzerava la connessione e, con SW_MCP_AUTORESTART=1, `connect` uccideva e rilanciava l'istanza dedicata (documenti
        persi) anche quando era solo occupata. Ora:
          - istanza occupata (chiamata rifiutata / riprova piu' tardi): fino a 3 letture a 0,5 s; se resta occupata ma il
            processo e' vivo la connessione resta (il tool riportera' il suo errore; un blocco vero lo ferma il timeout);
          - istanza persa solo se il server COM non c'e' piu' (HRESULT in _COM_GONE) o il processo dedicato e' uscito;
          - altri errori: come prima per l'istanza dell'utente; con l'istanza dedicata viva la connessione resta."""
        if not self._connected or self._sw_app is None:
            return False
        err = None
        for attempt in range(3):
            try:
                _ = self._sw_app.RevisionNumber
                return True
            except Exception as e:
                err = e
            if _hresult(err) not in _COM_BUSY:
                break
            if attempt < 2:
                time.sleep(0.5)
        hr = _hresult(err)
        proc = self.__dict__.get("_dedicated_proc")
        try:
            dedicated = bool(self.is_dedicated_mode())
        except Exception:
            dedicated = False
        proc_alive = proc is not None and proc.poll() is None
        if hr not in _COM_GONE and (hr in _COM_BUSY and (proc is None or proc_alive) or dedicated and proc_alive):
            logger.warning(f"SolidWorks non risponde ora ({err!r}) ma l'istanza e' viva: connessione mantenuta")
            return True
        self._connected = False
        self._sw_app = None
        return False
    
    @property
    def units(self) -> UnitConverter:
        """Get unit converter"""
        return self._units
    
    @property
    def app(self):
        """Get SolidWorks application object"""
        return self._sw_app
    
    # ========================================================================
    # Result Helper
    # ========================================================================
    
    def _result(self, success: bool, message: str,
                error_code: SwErrors = SwErrors.swSuccess,
                data: Optional[Dict] = None) -> Dict:
        """
        Create standardized result dictionary
        
        Args:
            success: Operation success status
            message: Human-readable message
            error_code: Error code enum
            data: Optional additional data
        
        Returns:
            Standardized result dictionary
        """
        result = {
            "success": success,
            "message": message,
            "error_code": int(error_code),
            "error_name": error_code.name,
            "timestamp": datetime.datetime.now().isoformat()
        }
        if data:
            result["data"] = data
        return result
    
    # ========================================================================
    # Dedicated instance (SW_MCP_INSTANCE=dedicated)
    # ========================================================================

    @staticmethod
    def is_dedicated_mode() -> bool:
        """True when SW_MCP_INSTANCE=dedicated: use a private, invisible SolidWorks process"""
        return os.environ.get("SW_MCP_INSTANCE", "").strip().lower() == "dedicated"

    @staticmethod
    def _find_instance_by_pid(pid: int):
        """Get the COM object of the SolidWorks process `pid` from the Running Object Table
        (moniker SolidWorks_PID_<pid>). Never attaches to other instances."""
        pythoncom.CoInitialize()
        rot = pythoncom.GetRunningObjectTable()
        ctx = pythoncom.CreateBindCtx(0)
        wanted = f"SolidWorks_PID_{pid}".lower()
        for moniker in rot.EnumRunning():
            try:
                name = moniker.GetDisplayName(ctx, None)
            except Exception:
                continue
            if name.lower() == wanted:
                obj = rot.GetObject(moniker)
                disp = obj.QueryInterface(pythoncom.IID_IDispatch)
                return win32com.client.Dispatch(disp)
        return None

    def _connect_dedicated(self) -> Dict:
        """Launch a NEW SolidWorks process and attach to it through the ROT (by PID)."""
        from ..utils import com_cache
        com_cache.clear()           # le descrizioni COM in cache appartengono al processo precedente
        exe = self._config.exe_path
        if not exe or exe == "auto" or not os.path.exists(exe):
            exe = os.environ.get("SW_MCP_EXE") or r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\SLDWORKS.exe"
        if not os.path.exists(exe):
            return self._result(False, f"SLDWORKS.exe not found: {exe}", SwErrors.swSolidWorksNotFound)
        args = [a for a in os.environ.get("SW_MCP_ARGS", "/r").split() if a]
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 7  # SW_SHOWMINNOACTIVATE: do not steal focus
        proc = subprocess.Popen([exe] + args, startupinfo=si)
        self._dedicated_proc = proc
        self._dedicated_pid = proc.pid
        logger.info(f"Dedicated SolidWorks launched, PID {proc.pid}")
        timeout = float(os.environ.get("SW_MCP_STARTUP_TIMEOUT", "240"))
        start = time.time()
        app = None
        while time.time() - start < timeout:
            time.sleep(3)
            if proc.poll() is not None:
                self._dedicated_proc = None
                self._dedicated_pid = None
                return self._result(False, f"Dedicated SolidWorks exited early (code {proc.returncode})",
                                    SwErrors.swConnectionError)
            try:
                app = self._find_instance_by_pid(proc.pid)
            except Exception as e:
                logger.debug(f"ROT lookup failed: {e}")
                app = None
            if app is not None:
                break
        if app is None:
            # il processo lanciato non deve restare acceso senza nessuno che lo guidi (ogni nuovo tentativo ne aprirebbe un altro)
            state = self.kill_dedicated()
            if state != "failed":                    # nessuna istanza da ricordare: il prossimo connect ne lancia una nuova
                self._dedicated_proc = None
                self._dedicated_pid = None
            return self._result(False, f"Dedicated SolidWorks PID {proc.pid} not in ROT after {timeout:.0f}s "
                                f"(processo lanciato: {state})", SwErrors.swConnectionError)
        self._sw_app = app
        for attr, val in (("Visible", False), ("UserControl", False)):
            try:
                setattr(app, attr, val)
            except Exception as e:
                logger.debug(f"Set {attr} failed: {e}")
        self._connected = True
        version = self._com(app, "RevisionNumber")
        return self._result(True, f"Connected to dedicated SolidWorks {version} (PID {proc.pid})",
                            SwErrors.swSuccess,
                            {"version": str(version), "launched": True, "pid": proc.pid, "dedicated": True,
                             "ui_language": self._ui_language()})

    def kill_dedicated(self) -> str:
        """Chiude di forza l'istanza dedicata, e SOLO quella: passa dal processo lanciato da questo server (Popen), mai da
        `taskkill /PID numero` (se il processo e' gia' uscito, quel numero puo' essere stato riusato da un altro programma).
        -> 'killed' | 'already_exited' | 'failed' | 'none'. Quando l'istanza non c'e' piu' azzera la connessione; PID e
        processo restano annotati: servono a `connect` per riconoscere l'istanza persa (rilancio solo con SW_MCP_AUTORESTART=1)."""
        proc = self.__dict__.get("_dedicated_proc")
        if proc is None:
            return "none"
        state = "already_exited"
        if proc.poll() is None:
            try:
                proc.kill()
                proc.wait(timeout=30)
                state = "killed"
            except Exception as e:
                logger.warning(f"chiusura dell'istanza dedicata (PID {getattr(proc, 'pid', '?')}) non riuscita: {e}")
                state = "killed" if proc.poll() is not None else "failed"
        if state != "failed":
            self._sw_app = None
            self._connected = False
        return state

    def _keep_hidden(self):
        """In dedicated mode SolidWorks tends to re-show itself: hide it again (cheap)."""
        if self._dedicated_pid and self._sw_app is not None:
            try:
                if self._sw_app.Visible:
                    self._sw_app.Visible = False
            except Exception:
                pass

    @staticmethod
    def autorestart_enabled() -> bool:
        """SW_MCP_AUTORESTART=1: se l'istanza dedicata e' persa, il tool seguente la rilancia (documenti aperti persi)."""
        return os.environ.get("SW_MCP_AUTORESTART", "").strip() == "1"

    def _restart_dedicated(self, lost_pid: int) -> Dict:
        """Rilancia l'istanza dedicata persa. Chiude prima il SUO processo se e' ancora vivo (mai altri PID).
        L'avviso resta in `_restart_notice`: il server lo aggiunge al risultato del tool che ha causato il rilancio."""
        proc = self._dedicated_proc
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
                proc.wait(timeout=30)
            except Exception as e:
                logger.warning(f"chiusura dell'istanza dedicata persa (PID {lost_pid}): {e}")
        self._sw_app = None
        self._connected = False
        self._dedicated_pid = None
        self._dedicated_proc = None
        self.__dict__.pop("_saved_prefs", None)
        logger.warning(f"istanza dedicata PID {lost_pid} persa: rilancio (SW_MCP_AUTORESTART=1)")
        r = self._connect_dedicated()
        if r["success"]:
            notice = (f"ATTENZIONE: l'istanza dedicata di SolidWorks (PID {lost_pid}) era persa ed e' stata rilanciata "
                      f"(nuovo PID {self._dedicated_pid}); i documenti aperti e non salvati in quella istanza sono persi.")
            self._restart_notice = notice
            r.setdefault("data", {})["restarted_after_loss_of_pid"] = lost_pid
        return r

    def shutdown_dedicated(self) -> Dict:
        """Close ONLY the dedicated instance (ExitApp, then kill of its exact PID if needed)."""
        pid = self._dedicated_pid
        if not pid:
            return self._result(False, "No dedicated instance")
        restore = getattr(self, "_restore_prefs", None)
        if restore is not None:
            restore(force=True)                       # alla chiusura SolidWorks scrive le preferenze nel registro
        from ..utils import com_cache
        com_cache.flush()                             # oggetti tenuti vivi (vivaio COM) rilasciati prima di chiudere
        try:
            if self._sw_app is not None:
                self._sw_app.ExitApp()
        except Exception as e:
            logger.debug(f"ExitApp failed: {e}")
        proc = self._dedicated_proc
        try:
            if proc is not None:
                proc.wait(timeout=60)
        except Exception:
            if self.kill_dedicated() == "failed":
                return self._result(False, f"Dedicated instance PID {pid} did not close", SwErrors.swConnectionError)
        self._sw_app = None
        self._connected = False
        self._dedicated_pid = None
        self._dedicated_proc = None
        return self._result(True, f"Dedicated instance PID {pid} closed")

    # ========================================================================
    # Connection Methods
    # ========================================================================
    
    def _try_connect_com(self) -> bool:
        """
        Try multiple COM connection methods
        
        Returns:
            True if connection successful
        """
        methods = [
            # Method 1: GetObject (running instance)
            lambda: win32com.client.GetObject(Class="SldWorks.Application"),
            # Method 2: Dispatch (creates or gets existing)
            lambda: win32com.client.Dispatch("SldWorks.Application"),
            # Method 3: Dynamic Dispatch
            lambda: win32com.client.dynamic.Dispatch("SldWorks.Application"),
            # Method 4: GetActiveObject
            lambda: win32com.client.GetActiveObject("SldWorks.Application"),
        ]
        
        for i, method in enumerate(methods):
            try:
                logger.debug(f"Trying connection method {i+1}...")
                pythoncom.CoInitialize()
                self._sw_app = method()
                
                if self._sw_app is not None:
                    self._sw_app.Visible = True
                    
                    # Get version (property or method)
                    try:
                        version = self._sw_app.RevisionNumber
                    except:
                        version = self._sw_app.RevisionNumber()
                    
                    logger.info(f"Connected via method {i+1}: {version}")
                    self._connected = True
                    return True
                    
            except Exception as e:
                logger.debug(f"Method {i+1} failed: {e}")
                continue
        
        return False
    
    def connect(self) -> Dict:
        """
        Connect to SolidWorks - launches if not running
        
        Returns:
            Result dictionary with connection status
        """
        try:
            logger.info("=== Connecting to SolidWorks ===")
            
            if self.is_dedicated_mode():
                if self._dedicated_pid:
                    pid = self._dedicated_pid
                    if self.is_connected:           # istanza viva: niente rilancio
                        version = self._com(self._sw_app, "RevisionNumber")
                        return self._result(True, f"Already connected to dedicated SolidWorks {version} (PID {pid})",
                                            SwErrors.swSuccess,
                                            {"version": str(version), "launched": False, "pid": pid, "dedicated": True,
                                             "ui_language": self._ui_language()})
                    if not self.autorestart_enabled():
                        # mai rilanciare senza permesso: l'istanza privata e' persa (crash, chiusa o bloccata)
                        return self._result(False,
                            f"L'istanza dedicata SolidWorks (PID {pid}) non risponde piu': riavvia il server MCP "
                            "(oppure imposta SW_MCP_AUTORESTART=1 per rilanciarla da sola).", SwErrors.swConnectionError)
                    return self._restart_dedicated(pid)
                return self._connect_dedicated()
            
            # Step 1: Try connecting to running instance
            if self._try_connect_com():
                try:
                    version = self._sw_app.RevisionNumber
                except:
                    version = self._sw_app.RevisionNumber()
                
                return self._result(True, f"Connected to SolidWorks {version}",
                                  SwErrors.swSuccess,
                                  {"version": str(version), "launched": False, "ui_language": self._ui_language()})
            
            # Step 2: Find SolidWorks executable
            if self._sw_exe_path is None:
                if self._config.exe_path != "auto":
                    self._sw_exe_path = self._config.exe_path
                else:
                    self._sw_exe_path = find_solidworks()
            
            if not self._sw_exe_path or not os.path.exists(self._sw_exe_path):
                return self._result(False,
                    "SolidWorks not found. Set exe_path in config or install SolidWorks.",
                    SwErrors.swSolidWorksNotFound)
            
            # Step 3: Launch SolidWorks
            logger.info(f"Launching SolidWorks: {self._sw_exe_path}")
            os.startfile(self._sw_exe_path)
            
            # Step 4: Wait for SolidWorks to start
            logger.info("Waiting for SolidWorks startup...")
            max_wait = self._config.startup_timeout
            retry_interval = self._config.connection_retry_interval
            start_time = time.time()
            
            while time.time() - start_time < max_wait:
                time.sleep(retry_interval)
                elapsed = int(time.time() - start_time)
                logger.debug(f"Connection attempt at {elapsed}s...")
                
                if self._try_connect_com():
                    try:
                        version = self._sw_app.RevisionNumber
                    except:
                        version = self._sw_app.RevisionNumber()
                    
                    logger.info(f"Connected after {elapsed}s")
                    return self._result(True,
                        f"Launched and connected to SolidWorks {version} (took {elapsed}s)",
                        SwErrors.swSuccess,
                        {"version": str(version), "launched": True, "startup_time": elapsed,
                         "ui_language": self._ui_language()})
            
            return self._result(False,
                f"Timeout after {max_wait}s. Close any dialogs and try again.",
                SwErrors.swConnectionError)
            
        except Exception as e:
            logger.error(f"Connection error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Connection error: {e}",
                              SwErrors.swConnectionError)
    
    
    # ========================================================================
    # Document Methods
    # ========================================================================
    
    def get_active_doc(self) -> Tuple[Any, Optional[Dict]]:
        """
        Get active document with auto-connect
        
        Returns:
            Tuple of (document, error_result)
            - If successful: (document, None)
            - If failed: (None, error_dict)
        """
        if not self.is_connected:
            result = self.connect()
            if not result["success"]:
                return None, result
        
        self._keep_hidden()
        doc = self._sw_app.ActiveDoc
        if doc is None:
            return None, self._result(False,
                "No document open. Use create_new_part first.",
                SwErrors.swNoActiveDocument)
        
        return doc, None
    
    def _get_doc_title(self, doc) -> str:
        """Get document title (handles property/method difference)"""
        try:
            title = doc.GetTitle
            if callable(title):
                return title()
            return title
        except:
            return "Unknown"
    
    @staticmethod
    def _com(obj, name: str):
        """Read a no-arg COM member (late binding exposes some methods as properties).
        COM objects (CDispatch) are themselves callable, so they must not be called."""
        value = getattr(obj, name)
        if callable(value) and not isinstance(value, win32com.client.CDispatch):
            return value()
        return value

    @staticmethod
    def _feat_error(feat) -> Tuple[Optional[int], bool]:
        """Errore di ricostruzione di una feature -> (codice, e' solo un avviso); (None, False) se non si legge.
        UNICO modo di leggere IFeature.GetErrorCode2 (revisione 2026-11-12: nel codice ce n'erano 4). In late binding arriva
        come METODO che vuole il flag d'avviso per riferimento: letto come proprieta' (int(...), codice[0]) dava un'eccezione
        ingoiata, quindi nessuna feature risultava mai in errore (misurato sugli accoppiamenti il 2026-10-24: codice 47)."""
        try:
            m = feat.GetErrorCode2
            if callable(m) and not isinstance(m, win32com.client.CDispatch):
                bf = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BOOL, False)
                code = m(bf)
                if isinstance(code, tuple):          # early binding: (codice, avviso)
                    return int(code[0] or 0), bool(code[1]) if len(code) > 1 else False
                return int(code or 0), bool(bf.value)
            if isinstance(m, tuple):
                return int(m[0] or 0), bool(m[1]) if len(m) > 1 else False
            return int(m or 0), False
        except Exception as e:
            logger.debug(f"GetErrorCode2 non letto: {e}")
            return None, False


    def _std_ref_feature(self, owner, name: str):
        """Piano standard (front/top/right, 'Piano frontale', 'Front Plane'...) o origine di un documento o di un componente,
        trovati per POSIZIONE e TIPO nell'albero: funziona con SolidWorks in qualunque lingua. None se `name` non e' uno di questi."""
        index = std_plane_index(name)
        want = "RefPlane" if index is not None else ("OriginProfileFeature" if is_origin_name(name) else None)
        if want is None:
            return None
        index = index or 0
        feat = self._com(owner, "FirstFeature")
        while feat is not None:
            if self._com(feat, "GetTypeName2") == want:
                if index == 0:
                    return feat
                index -= 1
            feat = self._com(feat, "GetNextFeature")
        return None

    def _ui_language(self) -> str:
        """Lingua dell'interfaccia di SolidWorks ('italian', 'english'...), '' se non leggibile."""
        try:
            return str(self._com(self._sw_app, "GetCurrentLanguage") or "").lower()
        except Exception:
            return ""

    def _default_template(self, template_type: str) -> str:
        """Ask SolidWorks for its default template (works with localized names)"""
        pref = {"part": 8, "assembly": 9, "drawing": 10}[template_type]  # swDefaultTemplate*
        try:
            return self._sw_app.GetUserPreferenceStringValue(pref) or ""
        except Exception as e:
            logger.debug(f"Default template lookup failed: {e}")
            return ""

    def _get_doc_path(self, doc) -> str:
        """Get document path (handles property/method difference)"""
        try:
            path = doc.GetPathName
            if callable(path):
                return path()
            return path
        except:
            return ""
