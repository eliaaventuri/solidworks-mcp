"""COM piu' leggero per gli oggetti restituiti da SolidWorks (ottimizzazione 2026-11-19, vedi OTTIMIZZAZIONE.md).

Misurato su questo PC (SolidWorks x64 emulato su Windows ARM64, server in un altro processo): ogni chiamata fra processi
costa ~3 ms. pywin32, per OGNI oggetto restituito (una feature, una faccia, uno spigolo...), chiede la descrizione del tipo
(GetTypeInfo e seguenti): ~11 ms in piu' per oggetto. Esempio misurato: body.GetFaces (6 facce) 70 ms -> 3 ms; leggere l'area
di 6 facce nuove 111 ms -> 37 ms. Inoltre rifa GetIDsOfNames (~3 ms) a ogni lettura di un membro, anche sullo stesso oggetto.

Qui (attivo di default, SW_MCP_COM_CACHE=0 lo spegne):
 1. gli oggetti restituiti si avvolgono SENZA descrizione del tipo (come DumbDispatch di pywin32);
 2. la lettura di un membro resta quella di pywin32 senza descrizione (DISPATCH_PROPERTYGET): misurato, era gia' cosi' per
    quasi tutti i membri di SolidWorks (40 risoluzioni dalla descrizione su ~2400 letture), quindi il comportamento non cambia;
    una chiamata di un membro senza descrizione resta DISPATCH_METHOD (come pywin32; se il server la rifiuta si riprova con
    METHOD|PROPERTYGET come VBA, poi con la descrizione del tipo);
 3. il dispid di ogni nome si tiene nell'oggetto: la seconda lettura dello stesso membro non rifa GetIDsOfNames;
 4. "vivaio" (pool, SW_MCP_COM_POOL=0 lo spegne): gli oggetti restituiti restano vivi fino a flush(), che il server chiama
    DOPO aver mandato la risposta del tool. Misurato 19/11 (probe_release.py): rilasciare l'ultimo riferimento a un oggetto
    costa una chiamata fra processi (~2,7 ms: 20 feature 55 ms), mentre SolidWorks restituisce lo STESSO oggetto COM per la
    stessa entita' (20 su 20 fra due GetFeatures). Con il vivaio: (a) lo stesso oggetto torna con lo stesso involucro, quindi
    i dispid gia' chiesti valgono ancora; (b) i rilasci avvengono mentre il modello legge la risposta, non dentro il tool.
    La chiave e' l'indirizzo dell'interfaccia (stabile finche' l'oggetto e' tenuto vivo: non puo' essere riusato).
"""

import os
import logging
from types import MethodType

try:                                    # su Linux/macOS (test offline) pywin32 non c'e': la cache semplicemente non si installa
    import pythoncom
    import win32com.client
    from win32com.client import dynamic, build
except ImportError:                     # pragma: no cover
    pythoncom = win32com = dynamic = build = None

logger = logging.getLogger(__name__)

_STATE = {"installed": False, "wrapped": 0, "id_hits": 0, "upgrades": 0}
_NEEDS_TYPE = set()          # nomi di metodi che hanno chiesto la descrizione del tipo (parametri di uscita): imparati
_LIGHT = {"cls": None}
_MISS = {}                   # GetIDsOfNames fatti davvero, per nome (diagnostica: stats()["gidn_top"])
_POOL = {"objs": {}, "hits": 0, "flushes": 0, "released": 0, "max": 5000}


def _ptr(dispatch):
    """Indirizzo dell'interfaccia COM dal repr di pywin32 ('<PyIDispatch at 0x.. with obj at 0x..>'); None se non c'e'."""
    try:
        r = repr(dispatch)
    except Exception:
        return None
    i = r.rfind("obj at 0x")
    return r[i + 7:-1] if i > 0 else None


def member_caller(name: str, method: bool = True):
    """Chiamata di UN membro su tanti oggetti della STESSA interfaccia (le facce di GetFaces, le feature di GetFeatures...):
    il numero del membro si chiede una volta sola e la chiamata va diretta (1 chiamata fra processi invece di 3: con pywin32
    un metodo letto la prima volta su un oggetto nuovo costa GetIDsOfNames + una lettura che fallisce + la chiamata vera,
    misurato 19/11). Solo per membri che restituiscono valori semplici (numeri, testi, elenchi di numeri): gli oggetti COM
    tornerebbero non avvolti. Se qualcosa non va, ripiega sulla via normale di pywin32."""
    box = {}

    real = win32com.client.CDispatch if win32com is not None else ()

    def call(obj, *args):
        try:
            if not isinstance(obj, real):            # oggetti finti dei test offline: via normale
                raise TypeError
            ole = obj._oleobj_
            did = box.get("id")
            if did is None:
                did = box["id"] = ole.GetIDsOfNames(name)
            return ole.Invoke(did, 0, pythoncom.DISPATCH_METHOD if method else pythoncom.DISPATCH_PROPERTYGET, True, *args)
        except Exception:
            m = getattr(obj, name)
            if args:
                return m(*args)
            if callable(m) and not isinstance(m, real):
                return m()
            return m
    return call


def pool_enabled() -> bool:
    return os.environ.get("SW_MCP_COM_POOL", "1").strip().lower() not in ("0", "false", "no", "off")


def flush() -> int:
    """Lascia andare gli oggetti tenuti vivi (i rilasci fra processi avvengono qui). Da chiamare sul thread COM, quando
    nessun tool e' in corso. Restituisce quanti erano."""
    objs = _POOL["objs"]
    if not objs:
        return 0
    _POOL["objs"] = {}
    n = len(objs)
    objs.clear()
    _POOL["flushes"] += 1
    _POOL["released"] += n
    return n


def _light_class():
    """Classe degli oggetti leggeri, creata al primo uso (serve pywin32). Se una chiamata fallisce per i parametri (tipico dei
    metodi con parametri di USCITA, che pywin32 gestisce solo con la descrizione del tipo: misurato su GetExtremePoint),
    l'oggetto si 'promuove' (descrizione del tipo chiesta allora) e la chiamata si ripete; il nome si ricorda e i prossimi
    oggetti si promuovono prima di usarlo."""
    if _LIGHT["cls"] is not None:
        return _LIGHT["cls"]
    retry = {-2147352562, -2147352561, -2147352571}     # DISP_E_BADPARAMCOUNT, DISP_E_PARAMNOTOPTIONAL, DISP_E_TYPEMISMATCH
    retry_get = retry | {-2147352573}                    # + DISP_E_MEMBERNOTFOUND

    class LightDispatch(win32com.client.CDispatch):
        def _mcp_upgrade(self):
            d = self.__dict__
            if d.get("_mcp_full"):
                return False
            d["_mcp_full"] = True
            try:
                ti = d["_oleobj_"].GetTypeInfo()
            except pythoncom.com_error:
                return False
            lazy = None
            try:
                lazy = (ti, ti.GetTypeComp())
            except pythoncom.com_error:
                pass
            d["_olerepr_"] = dynamic.MakeOleRepr(d["_oleobj_"], ti, lazy)
            d["_lazydata_"] = lazy
            d["_builtMethods_"] = {}
            d["_mapCachedItems_"] = {}
            _STATE["upgrades"] += 1
            return True

        def __getattr__(self, attr):
            if attr in _NEEDS_TYPE and not self.__dict__.get("_mcp_full"):
                self._mcp_upgrade()
            return win32com.client.CDispatch.__getattr__(self, attr)

        def _make_method_(self, name):
            m = win32com.client.CDispatch._make_method_(self, name)
            if m is None or self.__dict__.get("_mcp_full"):
                return m
            # pywin32 tiene la funzione costruita in _builtMethods_ e dalla seconda lettura usa QUELLA: il controllo va messo
            # li' (prima valeva solo alla prima chiamata dello stesso membro sullo stesso oggetto)
            built = self.__dict__["_builtMethods_"]
            key = next((k for k, v in built.items() if v is getattr(m, "__func__", None)), None)
            raw = getattr(m, "__func__", None)
            if raw is None:
                return m

            def fn(obj, *args):
                try:
                    return raw(obj, *args)
                except pythoncom.com_error as e:
                    if obj.__dict__.get("_mcp_full"):
                        raise
                    entry = obj._olerepr_.mapFuncs.get(name)
                    if e.hresult in retry_get and args and entry is not None and not entry.desc:
                        # pywin32 senza descrizione chiama con DISPATCH_METHOD (giusto per SolidWorks, anche per scrivere
                        # una proprieta' con indice come em.Equation(i, testo): misurato); altri server (Scripting.Dictionary
                        # .Item) vogliono anche PROPERTYGET, come fa VBA
                        try:
                            r = obj._oleobj_.Invoke(entry.dispid, 0, pythoncom.DISPATCH_METHOD | pythoncom.DISPATCH_PROPERTYGET,
                                                    1, *args)
                            return obj._get_good_object_(r, name)
                        except pythoncom.com_error:
                            pass
                    if e.hresult in retry and obj._mcp_upgrade():
                        _NEEDS_TYPE.add(name)
                        return getattr(obj, name)(*args)
                    raise
            if key is not None:
                built[key] = fn
            return MethodType(fn, self)

    _LIGHT["cls"] = LightDispatch
    return LightDispatch


def enabled() -> bool:
    return os.environ.get("SW_MCP_COM_CACHE", "1").strip().lower() not in ("0", "false", "no", "off")


def clear():
    """Nuova connessione: gli oggetti tenuti vivi appartengono al processo precedente."""
    flush()


def stats() -> dict:
    return {"installed": _STATE["installed"], "objects_wrapped_light": _STATE["wrapped"], "dispid_hits": _STATE["id_hits"],
            "upgrades": _STATE["upgrades"], "names_needing_typeinfo": sorted(_NEEDS_TYPE),
            "pool_on": _STATE.get("pool", False), "pool_hits": _POOL["hits"], "pool_alive": len(_POOL["objs"]),
            "pool_flushes": _POOL["flushes"], "pool_released": _POOL["released"],
            "gidn_top": sorted(_MISS.items(), key=lambda kv: -kv[1])[:25]}


def install() -> bool:
    """Installa le tre modifiche (idempotente). Gli oggetti creati esplicitamente con Dispatch/DispatchEx (l'applicazione)
    restano con la descrizione del tipo: solo quelli RESTITUITI dalle chiamate diventano leggeri."""
    if _STATE["installed"] or not enabled():
        return _STATE["installed"]
    if dynamic is None or not hasattr(pythoncom, "CLSCTX_SERVER"):
        return False
    mod = win32com.client
    # gli oggetti restituiti passano da win32com.client.Dispatch -> __WrapDispatch (misurato: e' li' che si chiede la
    # descrizione del tipo); il metodo _wrap_dispatch_ delle classi non basta
    orig_wrap = mod.__dict__.get("__WrapDispatch")
    orig_attr = dynamic.CDispatch.__dict__.get("__AttrToID__")
    orig_flags = dynamic.__dict__.get("_GetDescInvokeType")
    if orig_wrap is None or orig_attr is None or orig_flags is None:
        logger.warning("com_cache: pywin32 diverso dal previsto: nessuna modifica")
        return False

    use_pool = pool_enabled()
    _STATE["pool"] = use_pool

    def wrap_light(dispatch, userName=None, resultCLSID=None, typeinfo=None, clsctx=pythoncom.CLSCTX_SERVER,
                   WrapperClass=None):
        if resultCLSID is not None or WrapperClass not in (None, mod.CDispatch):
            return orig_wrap(dispatch, userName, resultCLSID, typeinfo, clsctx, WrapperClass)
        key = _ptr(dispatch) if use_pool else None
        if key is not None:
            w = _POOL["objs"].get(key)
            if w is not None:
                _POOL["hits"] += 1
                return w
        _STATE["wrapped"] += 1
        w = _light_class()(dispatch, build.DispatchItem(), userName)
        if key is not None:
            if len(_POOL["objs"]) >= _POOL["max"]:      # tetto: una sequenza lunghissima non tiene vivo tutto
                flush()
            _POOL["objs"][key] = w
        return w

    def attr_to_id(self, attr):
        rep = self.__dict__.get("_olerepr_")
        ids = getattr(rep, "_mcp_ids", None) if rep is not None else None
        if ids is None and rep is not None:
            try:
                ids = rep._mcp_ids = {}
            except Exception:
                ids = None
        if ids is not None and attr in ids:
            _STATE["id_hits"] += 1
            return ids[attr]
        _MISS[attr] = _MISS.get(attr, 0) + 1
        did = orig_attr(self, attr)
        if ids is not None:
            ids[attr] = did
        return did

    # NB: le chiamate senza descrizione restano DISPATCH_METHOD come in pywin32 (la versione del 18/11 usava METHOD|GET:
    # SolidWorks rifiutava em.Equation(i, testo) e doc.SummaryInfo(i, testo) con "Numero di parametri non valido",
    # misurato con scripts_tmp/ottimizzazione/probe_put.py); METHOD|GET resta solo come seconda prova (LightDispatch)
    mod.__dict__["__WrapDispatch"] = wrap_light
    dynamic.CDispatch.__AttrToID__ = attr_to_id
    _STATE.update(installed=True, orig_wrap=orig_wrap, orig_attr=orig_attr, orig_flags=orig_flags)
    return True


def uninstall():
    if not _STATE["installed"]:
        return
    win32com.client.__dict__["__WrapDispatch"] = _STATE.pop("orig_wrap")
    dynamic.CDispatch.__AttrToID__ = _STATE.pop("orig_attr")
    dynamic._GetDescInvokeType = _STATE.pop("orig_flags")
    _STATE["installed"] = False
