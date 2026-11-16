"""
Export con overwrite=true senza perdere il file che c'era gia'.

Prima il file esistente veniva cancellato e poi si esportava: se l'export falliva, il file vecchio era perso.
Ora il file viene MESSO DA PARTE (rinominato accanto all'originale) e, a tool finito:
  - se il file nuovo c'e' e non e' vuoto            -> la copia messa da parte viene eliminata;
  - se il tool dichiara successo senza quel file    -> idem (es. STL di un assieme scritto un file per componente);
  - in ogni altro caso (errore, eccezione, 0 byte)  -> il file vecchio torna al suo posto.

Uso:  @keeps_old_file sul metodo pubblico del tool, e `set_aside(self, percorso)` al posto di `os.remove(percorso)`.
Modulo senza COM: provato dal test offline.
"""
import functools
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)
_SUFFIX = ".swmcp_prev"


def set_aside(owner, path: str) -> Optional[str]:
    """Mette da parte `path` se esiste e lo annota su `owner` (l'istanza del tool). -> percorso della copia, o None."""
    if not path or not os.path.exists(path):
        return None
    aside = path + _SUFFIX
    if os.path.exists(aside):
        os.remove(aside)                       # resto di una chiamata interrotta: vale il file corrente
    os.replace(path, aside)
    owner.__dict__.setdefault("_asides", []).append((aside, path))
    return aside


def settle(owner, tool_ok: bool) -> None:
    """A tool finito: elimina le copie messe da parte oppure rimette i file vecchi al loro posto (vedi sopra)."""
    pending = owner.__dict__.pop("_asides", [])
    for aside, path in pending:
        try:
            if not os.path.exists(aside):
                continue
            new_ok = os.path.exists(path) and os.path.getsize(path) > 0
            if new_ok or (tool_ok and not os.path.exists(path)):
                os.remove(aside)
            else:
                if os.path.exists(path):
                    os.remove(path)            # file nuovo vuoto
                os.replace(aside, path)
                logger.warning(f"export non riuscito: ripristinato il file precedente {path}")
        except OSError as e:
            logger.warning(f"file precedente non sistemato ({aside} -> {path}): {e}")


def keeps_old_file(fn):
    """Decoratore per i tool che esportano: sistema i file messi da parte con `set_aside`, anche in caso di eccezione."""
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        ok = False
        try:
            result = fn(self, *args, **kwargs)
            ok = bool(isinstance(result, dict) and result.get("success"))
            return result
        finally:
            settle(self, ok)
    return wrapper
