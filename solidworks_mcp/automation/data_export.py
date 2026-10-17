"""
Dati ed export (blocco 3) — mixin DataExportOperations
------------------------------------------------------
Materiali, proprieta' di massa, proprieta' personalizzate, variabili globali/equazioni, configurazioni dei pezzi,
export (STL/3MF/STEP/IGES/Parasolid/PDF 3D/eDrawings), immagini del modello, import, misure.
Misure in mm (o `unit`), angoli in gradi, massa in kg, inerzie in kg*m2 (e kg*mm2).

Trappole API scoperte (SW 2026 italiano, late binding) — dettagli anche in STATO_STORICO.md:
 - Corpi: `Body2.SetMaterialProperty` e' IGNORATA (restituisce True) se il corpo non e' stato prima 'toccato' con `IMassProperty2.SelectedItems = [corpo]`
   (provato: ripetere la chiamata non serve, la selezione nella massa si'); dopo il set si ricostruisce e si ripesca il corpo.
   `Body2.SetMaterialProperty(cfg, db, nome)` / `GetMaterialPropertyName(cfg, ByRef db)` (i metodi `...PropertyName2` NON esistono su Body2;
   su Body2 `db` va dato SENZA percorso/estensione, 'solidworks materials': col percorso restituisce True ma non applica nulla; GetMaterialPropertyName ritorna (nome, db)).
 - Materiali: file `.sldmat` = XML UTF-16 in `lang\\<lingua di SolidWorks>\\sldmaterials` (`<classification name=categoria><material name=...>` con
   `<DENS value=kg/m3>`). Pezzo: `SetMaterialPropertyName2(config, path_db, nome)`; corpo: `Body2.SetMaterialProperty(...)`.
   `GetMaterialPropertyName2(cfg, ByRef db)` restituisce il nome e il db SENZA percorso/estensione.
   Cartiglio: la proprieta' Material del MODELLO deve essere l'espressione `"SW-Material@<file>"`.
 - Massa: `Extension.CreateMassProperty2` (IMassProperty2: Mass/Volume/Density/SurfaceArea/CenterOfMass,
   `PrincipalAxesOfInertia(i)`, `PrincipalMomentsOfInertia`, `GetMomentOfInertia(0=baricentro, 1=origine)` 9 valori [kg*m2]).
   Corpo singolo: `mp.SelectedItems = array di Body2`. Massa sovrascritta: solo con `Extension.CreateMassProperty` (v1):
   `SetAssignedMassProp(m,cx,cy,cz,1,nomi)` richiamato con `_oleobj_.Invoke`; si toglie con `OverrideMass = False`.
 - Proprieta' personalizzate: `Extension.CustomPropertyManager(cfg)`; `Get6(nome,False,ByRef val,ByRef risolto,ByRef,ByRef)` con VARIANT
   BYREF BSTR/BOOL. `Add3(nome,tipo,valore,2)` (30 testo, 3 numero, 5 double, 64 data, 11 si/no).
 - Equazioni: `doc.GetEquationMgr` (proprieta'); `Add2(-1,testo,True)` (-1 = rifiutata: quota/variabile inesistente); modifica con la
   proprieta' indicizzata `em.Equation(i, testo)` (SetEquationAndConfigurationOption restituisce -1 e non cambia nulla); `GlobalVariable(i)`.
   `em.Status` vale 1 anche a modello sano: non usarlo come errore.
 - Configurazioni: `ConfigurationManager.AddConfiguration2(...)` (la nuova diventa attiva); `doc.ShowConfiguration2` (e' del DOC);
   `DeleteConfiguration2`; quote: `dim.SetSystemValue3(v, 1 questa | 2 tutte | 3 specifiche, nomi)` (0 = ok); soppressione:
   `feature.SetSuppression2(0 sopprimi | 1 riattiva, 3, nomi)`. L'oggetto Feature resta legato alla config in cui e' stato trovato
   -> si cerca di nuovo la feature e si passano SEMPRE le configurazioni per nome. Dopo il cambio config serve `ForceRebuild3`.
 - Export: `Extension.SaveAs(path,0,1,exportData|NULL,err,warn)`; opzioni dalle preferenze utente (STL: int 78 qualita' 1/2/3,
   211 unita', toggle 69 binario, 71 non traslare in positivo, double 2/3 deviazione/angolo; STEP: int 75 = 203/214/242;
   IGES: int 83). PDF 3D: `GetExportFileData(1).ExportAs3D = True`. `.eprt/.easm` direttamente.
 - Immagini: `Extension.SaveAs(png)` da' sempre ~2389x1698 (la FrameWidth non conta) ed e' ben centrata; `doc.SaveBMP(path,w,h)` rispetta la
   dimensione ma centra male (contenuto spostato di +7,8% della larghezza, anche con Scale2): scartato -> si riduce il PNG nativo in Python.
   Piani/assi/schizzi si nascondono per feature: `Select2` + `BlankRefGeom` / `BlankSketch` (gli schizzi assorbiti stanno come
   sotto-feature); i toggle `swDisplayPlanes` ecc. dell'app NON hanno effetto sulla vista. Stato `Feature.Visible`: 1 nascosto, 2 mostrato.
   Sfondo bianco: int 305 = 0 (tinta unita) + int 99 = 0xFFFFFF. Stile: `ActiveView.DisplayMode` (1 filo, 2 linee nascoste rimosse,
   3 nascoste in grigio, 4 ombreggiato, 5 ombreggiato con spigoli).
 - Import: `GetImportFileData(path)` (None per STL/x_t) + `LoadFile4(path,"r",data|NULL,ByRef err)`; titolo del documento variabile (t.SLDPRT, t...).
 - Misure: `Extension.CreateMeasure`, `Calculate` e' PROPRIETA'; -1 = non applicabile; Angle in radianti; superfici: `face.GetSurface`
   (`IsCylinder`/`CylinderParams` = origine3+asse3+raggio, `PlaneParams` = normale3+punto3 sono proprieta').
 - Box: `Body2.GetBodyBox` e' approssimato (0,1 mm di errore su corpi curvi): si usa `GetExtremePoint(dir)` -> (ok,x,y,z).
"""

import os
import re
import glob
import math
import struct
import zipfile
import zlib
import logging
import traceback
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple, Any

import win32com.client
import pythoncom

from ..constants import SwErrors
from .modeling_base import null_variant
from ..utils.pdf3d import inspect_pdf3d
from ..utils.edrawings import inspect_edrawings
from ..utils.sw_lang import lang_folders
from ..utils.matlib import (SW_FILE_LOCATIONS_MATERIAL_DATABASES, merge_material_dirs, list_sldmat_files,
                            libraries_signature, dedupe_materials)
from ..utils import inertia as _inertia

logger = logging.getLogger(__name__)

MATERIAL_FILES = ("solidworks materials.sldmat", "SolidWorks DIN Materials.sldmat", "sustainability extras.sldmat")
PROP_TYPES = {"text": 30, "testo": 30, "number": 3, "numero": 3, "double": 5, "date": 64, "data": 64,
              "yesno": 11, "yes_no": 11, "si_no": 11}
PROP_TYPE_NAMES = {30: "text", 3: "number", 5: "double", 64: "date", 11: "yesno", 105: "equation", 0: "unknown"}
STYLES = {"wireframe": 1, "hidden_removed": 2, "hidden_lines": 2, "hidden_gray": 3, "hidden_greyed": 3,
          "shaded": 4, "shaded_edges": 5}
VIEW_IDS = {"front": 1, "back": 2, "left": 3, "right": 4, "top": 5, "bottom": 6, "isometric": 7,
            "trimetric": 8, "dimetric": 9}
EXPORT_FORMATS = {"stl": "stl", "3mf": "3mf", "step": "step", "stp": "step", "iges": "iges", "igs": "iges",
                  "x_t": "x_t", "x_b": "x_b", "sat": "sat", "pdf": "pdf3d", "pdf3d": "pdf3d", "eprt": "edrawings",
                  "easm": "edrawings", "edrawings": "edrawings"}
REF_TYPES = ("RefPlane", "RefAxis", "OriginProfileFeature", "CoordSys", "RefPoint", "RefCurve")
SKETCH_TYPES = ("ProfileFeature", "3DProfileFeature")


def _bstr_array(names):
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_BSTR, tuple(names))


def _byref_bstr():
    return win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BSTR, "")


def _byref_bool():
    return win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BOOL, False)


def _byref_i4():
    return win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)


def _write_png(path: str, width: int, height: int, rows_rgb: List[bytes]):
    raw = b"".join(b"\x00" + r for r in rows_rgb)

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def _read_png(path: str):
    """PNG non interlacciato (grigio / RGB / palette / grigio+alfa / RGBA, 1-8 bit) -> (w, h, 3, [righe RGB bytearray])."""
    b = open(path, "rb").read()
    pos, idat, plte = 8, b"", b""
    w = h = 0
    while pos < len(b):
        ln, = struct.unpack(">I", b[pos:pos + 4])
        t, d = b[pos + 4:pos + 8], b[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if t == b"IHDR":
            w, h, bd, ct, _, _, il = struct.unpack(">IIBBBBB", d)
            if il != 0 or ct not in (0, 2, 3, 4, 6) or bd not in (1, 2, 4, 8):
                raise ValueError(f"PNG non supportato (tipo colore {ct}, {bd} bit, interlacciato {il})")
        elif t == b"PLTE":
            plte = d
        elif t == b"IDAT":
            idat += d
    chans = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    bpp = max(1, chans * bd // 8)                       # byte per pixel (per i filtri)
    stride = (w * chans * bd + 7) // 8
    raw = zlib.decompress(idat)
    rows, prev, p = [], bytearray(stride), 0
    for _ in range(h):
        f = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        if f == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                up = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                pa, pb, pc = abs(up - c), abs(a - c), abs(a + up - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (up if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        prev = line
        rows.append(line)
    if ct == 2:
        return w, h, 3, rows
    out = []
    pal = [tuple(plte[3 * i:3 * i + 3]) for i in range(len(plte) // 3)]
    for line in rows:
        if bd < 8:                                       # sotto-byte -> un indice per pixel
            idx = []
            mask = (1 << bd) - 1
            for byte in line:
                for sh in range(8 - bd, -1, -bd):
                    idx.append((byte >> sh) & mask)
            idx = idx[:w]
        elif ct == 4:
            idx = line[0::2]
        elif ct == 6:
            r3 = bytearray(3 * w)
            r3[0::3], r3[1::3], r3[2::3] = line[0::4], line[1::4], line[2::4]
            out.append(r3)
            continue
        else:
            idx = line[:w]
        r3 = bytearray(3 * w)
        if ct == 3:
            for x, v in enumerate(idx):
                r3[3 * x:3 * x + 3] = bytes(pal[v]) if v < len(pal) else bytes(3)
        else:
            sc = 255 // ((1 << bd) - 1) if bd < 8 else 1
            g = bytes(min(255, v * sc) for v in idx) if sc != 1 else bytes(idx)
            r3[0::3], r3[1::3], r3[2::3] = g, g, g
        out.append(r3)
    return w, h, 3, out


def _expand32(b: bytes) -> int:
    e = bytearray(4 * len(b))
    e[0::4] = b
    return int.from_bytes(e, "little")


# D4: cattura di stampa (SaveAs usa la "cattura di stampa" con le preferenze 6 = 1, 10 = carta, 9 = DPI)
_SCREEN_MAX_W, _SCREEN_MAX_H = 2000, 1400      # oltre queste dimensioni richieste non si usa la cattura a schermo (nativa ~2389x1662)
_PRINT_DPI_MIN, _PRINT_DPI_MAX = 100, 600
_PRINT_PAPER_IN = (11.0, 8.5)                  # carta Letter orizzontale (preferenza 10 = 0)


def _wants_print_capture(W, H) -> bool:
    """True se l'immagine richiesta e' piu' grande di quanto la cattura a schermo (finestra) puo' dare in modo affidabile."""
    return int(W) > _SCREEN_MAX_W or int(H) > _SCREEN_MAX_H


def _print_dpi(W, H) -> int:
    """DPI della cattura di stampa (Letter orizzontale 11 x 8,5 pollici) perche' l'immagine copra W x H: ceil(max(W/11, H/8.5)),
    limitato a 100..600 (a 600 DPI: 6600 x 5100 px)."""
    d = math.ceil(max(int(W) / _PRINT_PAPER_IN[0], int(H) / _PRINT_PAPER_IN[1]))
    return max(_PRINT_DPI_MIN, min(_PRINT_DPI_MAX, d))


def _png_dims(path: str) -> Tuple[int, int]:
    """Larghezza e altezza di un PNG lette dall'intestazione IHDR (senza decodificare l'immagine)."""
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def _recenter_box(rows, sw: int, sh: int, bpp: int, W: int, H: int, margin: float = 0.04):
    """Ritaglio centrato sul contenuto: SolidWorks non centra il modello nella sua cattura (misurato: centro a +12 % in X a
    3840x2160). Solo con sfondo uniforme (4 angoli uguali). Il riquadro (contenuto + margine) ha le proporzioni W:H ed e' sempre
    un po' piu' grande di W x H (cosi' si riduce e non si ingrandisce). None se lo sfondo non e' uniforme o l'immagine e' vuota."""
    bg = bytes(rows[0][0:bpp])
    corners = (rows[0][(sw - 1) * bpp:sw * bpp], rows[sh - 1][0:bpp], rows[sh - 1][(sw - 1) * bpp:sw * bpp])
    if any(bytes(c) != bg for c in corners):
        return None
    # pixel "di contenuto" = almeno un canale a piu' di `tol` dallo sfondo (i bordi sfumati e quasi bianchi non spostano il centro);
    # per ogni riga: translate (tabella 0/1 per canale) + find/rfind, tutto in C
    tol = 40
    tabs = [bytes(1 if abs(v - bg[c]) > tol else 0 for v in range(256)) for c in range(3)]
    y0 = y1 = None
    x0, x1 = sw, -1
    for y in range(sh):
        r = bytes(rows[y])
        left, right = sw, -1
        for c in range(3):
            fl = r[c::bpp][:sw].translate(tabs[c])
            i = fl.find(1)
            if i >= 0:
                left, right = min(left, i), max(right, fl.rfind(1))
        if right < 0:
            continue
        x0, x1 = min(x0, left), max(x1, right)
        y0 = y if y0 is None else y0
        y1 = y
    if y0 is None:
        return None
    m = int(margin * max(x1 - x0 + 1, y1 - y0 + 1))
    cw, ch = x1 - x0 + 1 + 2 * m, y1 - y0 + 1 + 2 * m
    if cw / ch < W / H:
        cw = ch * W / H
    else:
        ch = cw * H / W
    s = max(1.0, W * 1.002 / cw, H * 1.002 / ch)
    cw, ch = int(math.ceil(cw * s)), int(math.ceil(ch * s))
    bx0 = int(round((x0 + x1) / 2 - cw / 2))
    by0 = int(round((y0 + y1) / 2 - ch / 2))
    out = []
    for y in range(by0, by0 + ch):
        if y < 0 or y >= sh:
            out.append(bg * cw)
            continue
        r = rows[y]
        a, b = max(0, bx0), min(sw, bx0 + cw)
        out.append(bg * (a - bx0) + bytes(r[a * bpp:b * bpp]) + bg * (bx0 + cw - b))
    return cw, ch, out


def _resize_png(src: str, dst: str, W: int, H: int, recenter: bool = False) -> Tuple[int, int, bool]:
    """Riduce un PNG a W x H (box filter intero + campionamento; bande con il colore d'angolo se le proporzioni differiscono).
    Mai ingrandisce oltre l'originale: restituisce (W, H, ridotto?) effettivi. `recenter`: con sfondo uniforme ritaglia prima
    attorno al contenuto (vedi `_recenter_box`), cosi' il modello risulta centrato."""
    sw, sh, bpp, rows = _read_png(src)
    W, H = int(W), int(H)
    if recenter:
        box = _recenter_box(rows, sw, sh, bpp, W, H)
        if box:
            sw, sh, rows = box
    k = min(W / sw, H / sh)
    if k >= 1.0:                       # nessun ingrandimento: copia l'originale
        import shutil
        shutil.copyfile(src, dst)
        return sw, sh, False
    f = max(1, min(15, int(1.0 / k)))  # fattore di riduzione intero (box f x f)
    dw1, dh1 = sw // f, sh // f
    mult = round(65536 / (f * f))
    out1 = []
    for y in range(dh1):
        chans = []
        for c in range(3):
            acc = 0
            for i in range(f):
                ch = rows[y * f + i][c::bpp]
                for kx in range(f):
                    acc += _expand32(bytes(ch[kx::f][:dw1]))
            chans.append((acc * mult).to_bytes(4 * dw1 + 4, "little")[2:4 * dw1:4])
        line = bytearray(3 * dw1)
        for c in range(3):
            line[c::3] = chans[c][:dw1]
        out1.append(bytes(line))
    # stadio 2: campionamento esatto verso la dimensione di destinazione (rapporto < 2)
    scale = min(W / dw1, H / dh1)
    tw, th = max(1, round(dw1 * scale)), max(1, round(dh1 * scale))
    xs = [min(dw1 - 1, int(i / scale)) for i in range(tw)]
    ys = [min(dh1 - 1, int(j / scale)) for j in range(th)]
    bg = bytes(rows[0][0:3])
    padl = (W - tw) // 2
    padt = (H - th) // 2
    res = []
    from operator import itemgetter
    for _ in range(padt):
        res.append(bg * W)
    getc = [itemgetter(*[3 * x + c for x in xs]) if tw > 1 else (lambda r, c=c, x=xs[0]: (r[3 * x + c],)) for c in range(3)]
    for y in ys:
        r = out1[y]
        line = bytearray(3 * tw)
        for c in range(3):
            line[c::3] = bytes(getc[c](r))
        res.append(bg * padl + bytes(line) + bg * (W - tw - padl))
    while len(res) < H:
        res.append(bg * W)
    _write_png(dst, W, H, res[:H])
    return W, H, True


class DataExportOperations:
    """Materiali, massa, proprieta', equazioni, configurazioni, export, immagini, import, misure."""

    # ====================================================================== helper
    def _dx_fail(self, what: str, e: Exception, code=SwErrors.swUnknownError) -> Dict:
        logger.error(f"{what}: {e}\n{traceback.format_exc()}")
        return self._result(False, f"Errore: {e}", code)

    def _dx_doc(self, kinds=(1, 2, 3)):
        """(doc, errore): documento attivo di tipo pezzo/assieme/disegno ammesso."""
        doc, err = self.get_active_doc()
        if err:
            return None, err
        try:
            t = int(doc.GetType)
        except Exception:
            t = 0
        if t not in kinds:
            names = {1: "un pezzo", 2: "un assieme", 3: "un disegno"}
            return None, self._result(False, "Serve " + " o ".join(names[k] for k in kinds) + " attivo.",
                                      SwErrors.swInvalidInput)
        if t in (1, 2):
            try:
                self._exit_sketch(doc)
            except Exception:
                pass
        return doc, None

    def _dx_cfg_name(self, doc) -> str:
        try:
            return str(self._com(self._com(doc.ConfigurationManager, "ActiveConfiguration"), "Name"))
        except Exception:
            return "Default"

    def _dx_cfg_names(self, doc) -> List[str]:
        try:
            return [str(n) for n in (doc.GetConfigurationNames or ())]
        except Exception:
            return []

    def _dx_cfg_list(self, doc, configuration) -> List[str]:
        """None -> attiva; 'all'/'*' -> tutte; nome o lista."""
        if configuration is None or configuration == "":
            return [self._dx_cfg_name(doc)]
        if isinstance(configuration, (list, tuple)):
            return [str(c) for c in configuration]
        if str(configuration).lower() in ("all", "*", "tutte"):
            return self._dx_cfg_names(doc)
        return [str(configuration)]

    def _dx_bad_cfgs(self, doc, names) -> Optional[Dict]:
        """Errore se una delle configurazioni richieste non esiste (prima ShowConfiguration2 falliva in silenzio)."""
        have = self._dx_cfg_names(doc)
        missing = [n for n in names if have and n not in have]
        if missing:
            return self._result(False, f"Configurazione/i {missing} non trovata/e. Presenti: {have}", SwErrors.swSelectionError)
        return None

    def _dx_rebuild(self, doc):
        try:
            doc.ForceRebuild3(False)
        except Exception:
            try:
                doc.EditRebuild3
            except Exception:
                pass

    def _dx_model_file(self, doc) -> str:
        """Nome file (con estensione) usato dalle espressioni SW-Mass@ / SW-Material@."""
        p = self._get_doc_path(doc)
        if p:
            return os.path.basename(p)
        t = self._get_doc_title(doc)
        if "." not in t:
            t += {1: ".SLDPRT", 2: ".SLDASM", 3: ".SLDDRW"}.get(int(doc.GetType), "")
        return t

    def _dx_body(self, doc, body: Optional[str]):
        """Corpo solido per nome (anche parziale) o indice; None se non indicato."""
        if body in (None, ""):
            return None, None
        bodies = self._bodies(doc)
        for b in bodies:
            if str(b.Name).lower() == str(body).lower():
                return b, None
        for b in bodies:
            if str(body).lower() in str(b.Name).lower():
                return b, None
        if str(body).isdigit() and int(body) < len(bodies):
            return bodies[int(body)], None
        return None, self._result(False, f"Corpo '{body}' non trovato. Corpi: {[str(b.Name) for b in bodies]}",
                                  SwErrors.swSelectionError)

    def _dx_box_m(self, doc, body=None):
        """Box esatto (xmin,ymin,zmin,xmax,ymax,zmax) in m. Pezzo: GetExtremePoint dei corpi; assieme: box dei componenti."""
        bodies = [body] if body is not None else self._bodies(doc)
        lo = [1e9, 1e9, 1e9]
        hi = [-1e9, -1e9, -1e9]
        if int(doc.GetType) == 2 and body is None:
            comps = doc.GetComponents(True)  # solo componenti di primo livello (metodo con argomento: non e' una proprieta')
            tmp = self._dx_asm_box(doc, comps)
            return tmp
        for b in bodies:
            for ax in range(3):
                for sign in (-1, 1):
                    d = [0, 0, 0]
                    d[ax] = sign
                    r = b.GetExtremePoint(*d)
                    v = r[1 + ax]
                    if sign < 0:
                        lo[ax] = min(lo[ax], v)
                    else:
                        hi[ax] = max(hi[ax], v)
        if lo[0] > 1e8:
            return None
        return lo + hi

    def _dx_asm_box(self, doc, comps):
        """Box dell'assieme: per ogni componente attivo, box esatto del suo pezzo (GetExtremePoint) portato nel sistema
        dell'assieme con Transform2 (rotazione = ArrayData[0:9] per colonne, traslazione = ArrayData[9:12], in m)."""
        lo = [1e9, 1e9, 1e9]
        hi = [-1e9, -1e9, -1e9]
        for c in (comps or ()):
            try:
                if c.IsSuppressed():
                    continue
            except Exception:
                pass
            try:
                pbox = self._dx_box_m(self._com(c, "GetModelDoc2"))
                t = list(self._com(self._com(c, "Transform2"), "ArrayData"))
            except Exception:
                continue
            if not pbox:
                continue
            R, T = t[0:9], t[9:12]
            for k in range(8):
                x, y, z = (pbox[0] if k & 1 == 0 else pbox[3]), (pbox[1] if k & 2 == 0 else pbox[4]), (pbox[2] if k & 4 == 0 else pbox[5])
                p = [R[i] * x + R[3 + i] * y + R[6 + i] * z + T[i] for i in range(3)]
                for i in range(3):
                    lo[i] = min(lo[i], p[i])
                    hi[i] = max(hi[i], p[i])
        return None if lo[0] > 1e8 else lo + hi

    # ====================================================================== materiali
    def _dx_material_dir(self) -> Optional[str]:
        try:
            base = self._com(self._sw_app, "GetExecutablePath")
            if base.lower().endswith(".exe"):
                base = os.path.dirname(base)
        except Exception:
            base = r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS"
        for sub in [os.path.join("lang", lg, "sldmaterials") for lg in lang_folders(self._ui_language())] + ["sldmaterials"]:
            p = os.path.join(base, sub)
            if os.path.isdir(p):
                return p
        return None

    def _dx_material_pref(self) -> str:
        """Cartelle dei database dei materiali configurate in SolidWorks (Opzioni > Percorsi dei file), separate da ';'."""
        try:
            return str(self._sw_app.GetUserPreferenceStringValue(SW_FILE_LOCATIONS_MATERIAL_DATABASES) or "")
        except Exception as e:
            logger.debug(f"Percorsi dei database materiali non leggibili: {e}")
            return ""

    def _dx_material_dirs(self) -> List[str]:
        """Cartelle delle librerie da leggere: prima quelle configurate in SolidWorks (preferenza 28), poi la standard;
        senza doppioni, solo cartelle esistenti."""
        std = None
        try:
            std = self._dx_material_dir()
        except Exception:
            pass
        return merge_material_dirs(self._dx_material_pref(), [std])

    def _dx_load_materials(self) -> List[Dict]:
        """[{name, category, density, database(path), file, props}] da tutti i .sldmat di tutte le librerie configurate.
        `database` = percorso del .sldmat (come lo vuole SetMaterialPropertyName2), `file` = nome senza estensione (come lo vuole
        Body2.SetMaterialProperty e il cartiglio). Stesso nome in due librerie: vale la prima (le altre in `_dx_mat_duplicates`).
        La cache vale finche' non cambia la firma (cartelle + percorso/data/dimensione di ogni .sldmat)."""
        dirs = self._dx_material_dirs()
        files = list_sldmat_files(dirs, MATERIAL_FILES)
        sig = libraries_signature(dirs, files)
        cache = getattr(self, "_dx_mat_cache", None)
        if cache is not None and cache[0] == sig:
            return cache[1]
        out = []
        for d, fn in files:
            path = os.path.join(d, fn)
            try:
                with open(path, "rb") as fh:
                    txt = fh.read().decode("utf-16", errors="ignore")
                txt = re.sub(r"^<\?xml[^>]*\?>", "", txt.lstrip("\ufeff").strip())
                root = ET.fromstring(txt)
            except Exception as e:
                logger.warning(f"sldmat {fn}: {e}")
                continue
            for cl in root.iter():
                if not cl.tag.endswith("classification"):
                    continue
                for m in cl:
                    if not m.tag.endswith("material"):
                        continue
                    props = {}
                    for pp in m.iter():
                        if pp.tag == "DENS":
                            props["density_kg_m3"] = float(pp.get("value", "0") or 0)
                        elif pp.tag == "EX":
                            props["elastic_modulus_Pa"] = float(pp.get("value", "0") or 0)
                        elif pp.tag == "NUXY":
                            props["poisson"] = float(pp.get("value", "0") or 0)
                        elif pp.tag == "SIGYLD":
                            props["yield_strength_Pa"] = float(pp.get("value", "0") or 0)
                        elif pp.tag == "SIGXT":
                            props["tensile_strength_Pa"] = float(pp.get("value", "0") or 0)
                        elif pp.tag == "KX":
                            props["thermal_conductivity"] = float(pp.get("value", "0") or 0)
                    out.append({"name": m.get("name"), "category": cl.get("name"),
                                "density": props.get("density_kg_m3", 0.0), "database": path,
                                "file": os.path.splitext(fn)[0], "props": props})
        out, self._dx_mat_duplicates = dedupe_materials(out)
        self._dx_mat_libraries = {"folders": list(dirs), "files": [os.path.join(d, f) for d, f in files]}
        self._dx_mat_cache = (sig, out)
        return out

    def _dx_find_material(self, material: str, category: str = None):
        mats = self._dx_load_materials()
        if category:
            cat = category.lower()
            mats = [m for m in mats if cat in m["category"].lower()]
        low = material.lower().strip()
        exact = [m for m in mats if m["name"].lower() == low]
        if exact:
            return exact[0], None
        part = [m for m in mats if low in m["name"].lower()]
        if len(part) == 1:
            return part[0], None
        starts = [m for m in part if m["name"].lower().startswith(low)]
        if len(starts) == 1:
            return starts[0], None
        if part:
            return None, f"Nome ambiguo '{material}': {[m['name'] for m in part[:12]]}"
        return None, f"Materiale '{material}' non trovato nella libreria ({len(mats)} materiali)."

    def list_materials(self, category: str = None, query: str = None, include_properties: bool = False,
                       limit: int = 400) -> Dict:
        """Elenco dei materiali delle librerie SolidWorks (file .sldmat) per categoria: nome, densita' kg/m3. Sono incluse le
        librerie personalizzate configurate in SolidWorks (Opzioni > Percorsi dei file > Database dei materiali), non solo quella
        standard. Senza `category` restituisce l'elenco delle categorie con il numero di materiali; `libraries` elenca cartelle e
        file letti, `duplicates` i nomi presenti in piu' librerie (vale il primo)."""
        try:
            mats = self._dx_load_materials()
            if not mats:
                return self._result(False, "Libreria materiali non trovata", SwErrors.swUnknownError)
            cats: Dict[str, int] = {}
            for m in mats:
                cats[m["category"]] = cats.get(m["category"], 0) + 1
            sel = mats
            if category:
                sel = [m for m in sel if category.lower() in m["category"].lower()]
            if query:
                sel = [m for m in sel if query.lower() in m["name"].lower()]
            data: Dict[str, Any] = {"categories": cats, "total": len(mats), "matching": len(sel),
                                    "libraries": dict(getattr(self, "_dx_mat_libraries", {})),
                                    "duplicates": list(getattr(self, "_dx_mat_duplicates", []))}
            if category or query:
                items = []
                for m in sel[:int(limit)]:
                    it = {"name": m["name"], "category": m["category"], "density_kg_m3": m["density"], "library": m["file"]}
                    if include_properties:
                        it["properties"] = m["props"]
                    items.append(it)
                data["materials"] = items
            return self._result(True, f"{len(sel)} materiali" + (f" in '{category}'" if category else "")
                                + f" ({len(cats)} categorie, {len(mats)} totali)", SwErrors.swSuccess, data)
        except Exception as e:
            return self._dx_fail("list_materials", e)

    def assign_material(self, material: str, category: str = None, body: str = None, configuration: str = None,
                        link_title_block: bool = True) -> Dict:
        """Assegna un materiale delle librerie (anche quelle personalizzate configurate in SolidWorks; nome italiano, es.
        'AISI 304', 'Lega 6061', 'ABS generico') al pezzo o a un corpo (`body`). `configuration`: nome | 'all' (default l'attiva). Con link_title_block (solo pezzo intero) imposta la
        proprieta' personalizzata Material = "SW-Material@file" cosi' il cartiglio dei disegni mostra il materiale."""
        try:
            doc, err = self._dx_doc((1,))
            if err:
                return err
            mat, e = self._dx_find_material(material, category)
            if mat is None:
                return self._result(False, e, SwErrors.swInvalidInput)
            if body:
                self._dx_rebuild(doc)       # un corpo appena creato ignora il materiale finche' non e' stato ricostruito
            bd, err = self._dx_body(doc, body)
            if err:
                return err
            cfgs = self._dx_cfg_list(doc, configuration)
            body_name = str(bd.Name) if bd is not None else None      # dopo la ricostruzione il puntatore al corpo non e' piu' valido
            tries = 0
            for c in cfgs:
                if bd is not None:
                    # Body2.SetMaterialProperty restituisce True ma non fa nulla se il corpo non e' stato "toccato" prima da un
                    # IMassProperty2.SelectedItems: si tocca il corpo, si imposta, si verifica (con un nuovo tentativo se serve)
                    for tries in range(1, 4):
                        mp = self._com(doc.Extension, "CreateMassProperty2")
                        mp.SelectedItems = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (bd,))
                        mp.Density
                        bd.SetMaterialProperty(c, mat["file"], mat["name"])
                        self._dx_rebuild(doc)
                        bd, _e = self._dx_body(doc, body_name)
                        r = bd.GetMaterialPropertyName(c, _byref_bstr())
                        if (r[0] if isinstance(r, tuple) else r) == mat["name"]:
                            break
                else:
                    doc.SetMaterialPropertyName2(c, mat["database"], mat["name"])
            self._dx_rebuild(doc)
            data = {"material": mat["name"], "category": mat["category"], "library": mat["file"],
                    "density_table_kg_m3": mat["density"], "configurations": cfgs, "body": body_name, "attempts": tries or None}
            if bd is None and link_title_block:
                lr = self.link_material_to_title_block()
                data["title_block_link"] = lr["success"]
                if lr["success"]:
                    data["Material_property"] = lr["data"]["value"]
            mp = self._mass_props(doc)
            if mp is not None and bd is None:
                data["density_used_kg_m3"] = round(float(self._com(mp, "Density")), 3)
                data["mass_kg"] = float(self._com(mp, "Mass"))
            return self._result(True, f"Materiale '{mat['name']}' assegnato" + (f" al corpo {body_name}" if bd is not None else "")
                                + f" (densita' {mat['density']:.0f} kg/m3)", SwErrors.swSuccess, data)
        except Exception as e:
            return self._dx_fail("assign_material", e)

    def get_material(self, body: str = None, configuration: str = None) -> Dict:
        """Materiale corrente del pezzo (o di un corpo / di tutti i corpi) con densita' usata."""
        try:
            doc, err = self._dx_doc((1,))
            if err:
                return err
            cfg = self._dx_cfg_list(doc, configuration)[0]
            db = _byref_bstr()
            name = doc.GetMaterialPropertyName2(cfg, db)
            data: Dict[str, Any] = {"configuration": cfg, "material": name or None, "library": db.value or None}
            mat = None
            if name:
                mat, _ = self._dx_find_material(name)
                if mat is not None:
                    data["category"] = mat["category"]
                    data["density_table_kg_m3"] = mat["density"]
            bodies = self._bodies(doc)
            infos = []
            for b in bodies:
                nm = str(b.Name)
                try:
                    r = b.GetMaterialPropertyName(cfg, _byref_bstr())
                    bn = (r[0] if isinstance(r, tuple) else r) or None
                except Exception:
                    bn = None
                infos.append({"body": nm, "material": bn})
            data["bodies"] = infos
            if body:
                b, err = self._dx_body(doc, body)
                if err:
                    return err
                data["bodies"] = [i for i in infos if i["body"] == str(b.Name)]
            mp = self._mass_props(doc)
            if mp is not None:
                data["density_used_kg_m3"] = round(float(self._com(mp, "Density")), 3)
            try:
                cpm = doc.Extension.CustomPropertyManager("")
                v = _byref_bstr(); r = _byref_bstr()
                cpm.Get6("Material", False, v, r, _byref_bool(), _byref_bool())
                data["Material_property"] = v.value
                data["Material_property_resolved"] = r.value
            except Exception:
                pass
            return self._result(True, f"Materiale: {name or 'non specificato'}", SwErrors.swSuccess, data)
        except Exception as e:
            return self._dx_fail("get_material", e)

    def link_material_to_title_block(self) -> Dict:
        """Imposta la proprieta' personalizzata del modello Material = "SW-Material@<file>": il cartiglio dei disegni
        (che legge Material dal modello) mostra il materiale assegnato. Il pezzo va salvato prima dell'export del disegno."""
        try:
            doc, err = self._dx_doc((1,))
            if err:
                return err
            expr = f'"SW-Material@{self._dx_model_file(doc)}"'
            cpm = doc.Extension.CustomPropertyManager("")
            cpm.Add3("Material", 30, expr, 2)
            v = _byref_bstr(); r = _byref_bstr()
            cpm.Get6("Material", False, v, r, _byref_bool(), _byref_bool())
            return self._result(True, f"Material = {v.value} -> '{r.value}'", SwErrors.swSuccess,
                                {"value": v.value, "resolved": r.value})
        except Exception as e:
            return self._dx_fail("link_material_to_title_block", e)

    # ====================================================================== massa
    def get_part_mass_properties(self, body: str = None, configuration: str = None, unit: str = None,
                                 coordinate_system: str = None) -> Dict:
        """Proprieta' di massa complete di pezzo (o di un corpo): massa, volume, area, densita' usata, baricentro,
        momenti principali + assi principali, tensore d'inerzia nel baricentro e nell'origine [kg*m2 e kg*mm2].
        `coordinate_system` (nome di una feature sistema di coordinate): in piu' `in_coordinate_system` con baricentro e
        tensori nell'origine e negli assi di quel sistema (D7, calcolo in Python + controllo con IMassProperty2.SetCoordinateSystem)."""
        try:
            doc, err = self._dx_doc((1,))
            if err:
                return err
            bd, err = self._dx_body(doc, body)
            if err:
                return err
            body_name = str(bd.Name) if bd is not None else None
            if configuration:
                bad = self._dx_bad_cfgs(doc, [configuration])
                if bad:
                    return bad
            prev = None
            if configuration and configuration != self._dx_cfg_name(doc):
                prev = self._dx_cfg_name(doc)
                doc.ShowConfiguration2(configuration)
            try:
                return self._dx_mass_props_body(doc, bd, body_name, unit, coordinate_system)
            finally:
                if prev:                            # la configurazione di partenza torna attiva anche in caso di errore
                    doc.ShowConfiguration2(prev)
        except Exception as e:
            return self._dx_fail("get_part_mass_properties", e)

    def _dx_mass_props_body(self, doc, bd, body_name, unit, coordinate_system=None) -> Dict:
        """Corpo di get_part_mass_properties con la configurazione richiesta gia' attiva."""
        self._dx_rebuild(doc)
        if bd is not None:                      # dopo la ricostruzione i puntatori ai corpi sono vecchi: si cerca di nuovo
            bd, err = self._dx_body(doc, body_name)
            if err:
                return err
        tf = None
        if coordinate_system:
            tf, err = self._dx_cs_transform(doc, coordinate_system)
            if err:
                return err
        mp = self._com(doc.Extension, "CreateMassProperty2")
        if mp is None:
            return self._result(False, "CreateMassProperty2 non disponibile", SwErrors.swUnknownError)
        if bd is not None:
            mp.SelectedItems = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (bd,))
        u = self._unit_name(unit)
        vol = float(self._com(mp, "Volume"))
        mass = float(self._com(mp, "Mass"))
        area = float(self._com(mp, "SurfaceArea"))
        com = [float(c) for c in self._com(mp, "CenterOfMass")]
        dens = float(self._com(mp, "Density"))
        pm = [float(x) for x in self._com(mp, "PrincipalMomentsOfInertia")]
        axes = [[float(x) for x in mp.PrincipalAxesOfInertia(i)] for i in range(3)]
        Ic = [float(x) for x in mp.GetMomentOfInertia(0)]
        Io = [float(x) for x in mp.GetMomentOfInertia(1)]
        ov = False
        try:
            ov = bool(self._com(self._com(doc.Extension, "CreateMassProperty"), "OverrideMass"))
        except Exception:
            pass
        mm2 = 1e6

        def t(v, k=1.0):
            return [[round(v[3 * i + j] * k, 12) for j in range(3)] for i in range(3)]
        data = {
            "body": body_name, "configuration": self._dx_cfg_name(doc),
            "mass_kg": mass, "volume_mm3": round(vol * 1e9, 6), "surface_area_mm2": round(area * 1e6, 6),
            "density_kg_m3": round(dens, 6), "mass_overridden": ov,
            "center_of_mass": [round(self._from_m(c, u), 6) for c in com], "unit": u,
            "principal_moments_kg_m2": pm, "principal_moments_kg_mm2": [x * mm2 for x in pm],
            "principal_axes": axes,
            "inertia_tensor_at_center_of_mass_kg_m2": t(Ic), "inertia_tensor_at_center_of_mass_kg_mm2": t(Ic, mm2),
            "inertia_tensor_at_origin_kg_m2": t(Io), "inertia_tensor_at_origin_kg_mm2": t(Io, mm2),
            "bodies": len(self._bodies(doc)),
        }
        try:
            cfg = self._dx_cfg_name(doc)
            data["material"] = doc.GetMaterialPropertyName2(cfg, _byref_bstr()) or None
        except Exception:
            pass
        if tf is not None:
            data["in_coordinate_system"] = self._dx_in_coordinate_system(
                doc, bd, tf, coordinate_system, mass, com, Ic, Io, u)
        return self._result(True, f"Massa {mass:.6f} kg, volume {vol * 1e9:.3f} mm3, densita' {dens:.1f} kg/m3",
                            SwErrors.swSuccess, data)

    def _dx_cs_names(self, doc) -> List[str]:
        """Nomi dei sistemi di coordinate (feature di tipo CoordSys) del pezzo."""
        return [n for n, t, _f in self._features(doc) if t == "CoordSys"]

    def _dx_cs_transform(self, doc, name):
        """(MathTransform del sistema di coordinate `name`, errore). Errore con l'elenco dei sistemi presenti."""
        names = self._dx_cs_names(doc)
        elenco = f"Sistemi di coordinate presenti: {names}" if names else "Il pezzo non ha sistemi di coordinate (create_coordinate_system)"
        tf = None
        try:
            tf = doc.Extension.GetCoordinateSystemTransformByName(name)
        except Exception:
            pass
        if tf is None:
            return None, self._result(False, f"Sistema di coordinate '{name}' non trovato. {elenco}", SwErrors.swInvalidInput,
                                      {"coordinate_systems": names})
        return tf, None

    def _dx_in_coordinate_system(self, doc, bd, tf, name, mass, com, Ic, Io, u) -> Dict:
        """Baricentro e tensori d'inerzia nel sistema di coordinate utente (D7).
        Calcolo in Python (utils/inertia.py) da massa, baricentro e tensore nel baricentro letti nel sistema del modello;
        la convenzione dei termini fuori diagonale e' decisa a runtime. `api_check`: stessi valori da un SECONDO oggetto
        IMassProperty2 con SetCoordinateSystem (controllo indipendente, mai bloccante)."""
        arr = [float(v) for v in tf.ArrayData]
        r, o = _inertia.frame_from_sw_transform(arr, 1.0)
        conv = _inertia.detect_offdiag_convention(Ic, mass, com, Io)
        used = "products" if conv == "products" else "tensor"
        res = _inertia.mass_properties_in_frame(mass, com, Ic, r, o, offdiag=used)
        issues = list(res["frame_issues"])
        if len(arr) > 12 and arr[12] and abs(arr[12] - 1.0) > 1e-9:
            issues.append(f"scala del sistema di coordinate {arr[12]} (ignorata)")
        if conv == "indeterminate":
            jc = _inertia.as_matrix(Ic)
            if max(abs(jc[a][b]) for a in range(3) for b in range(3) if a != b) > 1e-9 * max(abs(jc[k][k]) for k in range(3)):
                issues.append("convenzione dei termini fuori diagonale non determinabile (baricentro su un asse o piano "
                              "del modello): assunto 'tensor', il segno dei termini fuori diagonale puo' essere opposto")
        mm2 = 1e6

        def t(m, k=1.0):
            return [[round(m[i][j] * k, 12) for j in range(3)] for i in range(3)]
        out = {
            "name": name, "unit": u,
            "center_of_mass": [round(self._from_m(c, u), 6) for c in res["center_of_mass"]],
            "origin": [round(self._from_m(c, u), 6) for c in o],
            "axes_in_model": {"x": [round(r[i][0], 9) for i in range(3)], "y": [round(r[i][1], 9) for i in range(3)],
                              "z": [round(r[i][2], 9) for i in range(3)]},
            "inertia_tensor_at_center_of_mass_kg_m2": t(res["inertia_at_center_of_mass"]),
            "inertia_tensor_at_center_of_mass_kg_mm2": t(res["inertia_at_center_of_mass"], mm2),
            "inertia_tensor_at_origin_kg_m2": t(res["inertia_at_origin"]),
            "inertia_tensor_at_origin_kg_mm2": t(res["inertia_at_origin"], mm2),
            "principal_moments_kg_m2": res["principal_moments"],
            "frame_issues": issues, "offdiag_convention": conv,
        }
        try:
            mp2 = self._com(doc.Extension, "CreateMassProperty2")
            if bd is not None:
                mp2.SelectedItems = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (bd,))
            try:
                mp2.SetCoordinateSystem(tf)
            except Exception:
                mp2.SetCoordinateSystem(win32com.client.VARIANT(pythoncom.VT_DISPATCH, tf))
            try:
                self._com(mp2, "Recalculate")
            except Exception:
                pass
            c2 = [float(x) for x in self._com(mp2, "CenterOfMass")]
            i2 = [float(x) for x in mp2.GetMomentOfInertia(1)]
            exp_c = res["center_of_mass"]
            exp_i = _inertia.as_matrix([x for row in res["inertia_at_origin"] for x in row])
            got_i = _inertia.as_matrix(i2)
            dc = max(abs(c2[k] - exp_c[k]) for k in range(3))
            di = max(abs(got_i[a][b] - exp_i[a][b]) for a in range(3) for b in range(3))
            sc_i = max(abs(exp_i[a][b]) for a in range(3) for b in range(3)) or 1.0
            sc_c = max(abs(x) for x in exp_c) or 1.0
            out["api_check"] = {
                "center_of_mass": [round(self._from_m(x, u), 6) for x in c2],
                "inertia_at_origin_kg_m2": [[round(x, 12) for x in row] for row in got_i],
                "max_diff_center_of_mass": round(self._from_m(dc, u), 9),
                "max_rel_diff_center_of_mass": dc / sc_c,
                "max_diff_inertia_kg_m2": di, "max_rel_diff_inertia": di / sc_i,
            }
        except Exception as e:
            out["api_check"] = {"error": str(e)[:300]}
        return out

    def set_mass_override(self, mass: float = None, center_of_mass: List[float] = None, unit: str = None,
                          configuration: str = None) -> Dict:
        """Massa sovrascritta (kg) con baricentro opzionale ([x,y,z] in `unit`, default quello calcolato).
        Senza `mass` (o mass=None) la sovrascrittura viene rimossa."""
        try:
            doc, err = self._dx_doc((1,))
            if err:
                return err
            mp1 = self._com(doc.Extension, "CreateMassProperty")
            if mass is None:
                mp1.OverrideMass = False
                self._dx_rebuild(doc)
                m = float(self._com(self._com(doc.Extension, "CreateMassProperty2"), "Mass"))
                return self._result(True, f"Sovrascrittura rimossa: massa calcolata {m:.6f} kg", SwErrors.swSuccess,
                                    {"mass_kg": m, "mass_overridden": False})
            com = [float(c) for c in self._com(self._com(doc.Extension, "CreateMassProperty2"), "CenterOfMass")]
            if center_of_mass:
                com = [self._mmu(c, unit) for c in center_of_mass]
            cfgs = self._dx_cfg_list(doc, configuration)
            did = mp1._oleobj_.GetIDsOfNames("SetAssignedMassProp")
            ok = mp1._oleobj_.Invoke(did, 0, pythoncom.DISPATCH_METHOD, True, float(mass), com[0], com[1], com[2],
                                     3 if configuration else 1, _bstr_array(cfgs))
            self._dx_rebuild(doc)
            mp2 = self._com(doc.Extension, "CreateMassProperty2")
            got = float(self._com(mp2, "Mass"))
            return self._result(bool(ok) and abs(got - mass) < 1e-9 + 1e-6 * abs(mass),
                                f"Massa sovrascritta: {got:.6f} kg", SwErrors.swSuccess,
                                {"mass_kg": got, "mass_overridden": True,
                                 "center_of_mass": [round(self._from_m(c, unit), 6) for c in self._com(mp2, "CenterOfMass")]})
        except Exception as e:
            return self._dx_fail("set_mass_override", e)

    # ====================================================================== proprieta' personalizzate
    def _dx_cpm(self, doc, configuration):
        return doc.Extension.CustomPropertyManager(configuration or "")

    def _dx_read_prop(self, cpm, name):
        v, r = _byref_bstr(), _byref_bstr()
        cpm.Get6(name, False, v, r, _byref_bool(), _byref_bool())
        try:
            tp = PROP_TYPE_NAMES.get(int(cpm.GetType2(name)), "unknown")
        except Exception:
            tp = "unknown"
        return {"name": name, "type": tp, "value": v.value, "resolved": r.value, "is_expression": str(v.value) != str(r.value)
                or str(v.value).startswith('"SW-') or str(v.value).startswith("$")}

    def list_custom_properties(self, configuration: str = None) -> Dict:
        """Elenca le proprieta' personalizzate del documento attivo (pezzo/assieme/disegno). `configuration`
        vuoto = proprieta' del file; nome = proprieta' specifiche di quella configurazione."""
        try:
            doc, err = self._dx_doc()
            if err:
                return err
            cpm = self._dx_cpm(doc, configuration)
            names = list(cpm.GetNames or ())
            props = [self._dx_read_prop(cpm, n) for n in names]
            return self._result(True, f"{len(props)} proprieta'" + (f" (configurazione {configuration})" if configuration else " (file)"),
                                SwErrors.swSuccess, {"configuration": configuration or None, "properties": props})
        except Exception as e:
            return self._dx_fail("list_custom_properties", e)

    def get_custom_property(self, name: str, configuration: str = None) -> Dict:
        """Legge una proprieta' (valore/espressione e valore risolto, es. SW-Mass)."""
        try:
            doc, err = self._dx_doc()
            if err:
                return err
            cpm = self._dx_cpm(doc, configuration)
            if name not in list(cpm.GetNames or ()):
                return self._result(False, f"Proprieta' '{name}' non trovata", SwErrors.swSelectionError)
            p = self._dx_read_prop(cpm, name)
            return self._result(True, f"{name} = {p['value']} -> '{p['resolved']}'", SwErrors.swSuccess, p)
        except Exception as e:
            return self._dx_fail("get_custom_property", e)

    def set_custom_property(self, name: str, value: str, configuration: str = None, type: str = "text") -> Dict:
        """Scrive (crea o sostituisce) una proprieta'. type: text | number | double | date | yesno. Il valore puo' essere
        un'espressione: 'SW-Mass@pezzo.SLDPRT' (le virgolette vengono aggiunte da sole), '$PRP:"Description"'."""
        try:
            doc, err = self._dx_doc()
            if err:
                return err
            tp = PROP_TYPES.get(str(type).lower())
            if tp is None:
                return self._result(False, f"Tipo '{type}' sconosciuto ({list(PROP_TYPES)})", SwErrors.swInvalidInput)
            val = str(value)
            if re.match(r"^SW-[A-Za-z ]+@", val):
                val = f'"{val}"'
            cpm = self._dx_cpm(doc, configuration)
            r = cpm.Add3(name, tp, val, 2)
            p = self._dx_read_prop(cpm, name)
            return self._result(r in (0, 1, True) and name in list(cpm.GetNames or ()),
                                f"{name} = {p['value']} -> '{p['resolved']}'", SwErrors.swSuccess, p)
        except Exception as e:
            return self._dx_fail("set_custom_property", e)

    def delete_custom_property(self, name: str, configuration: str = None) -> Dict:
        try:
            doc, err = self._dx_doc()
            if err:
                return err
            cpm = self._dx_cpm(doc, configuration)
            if name not in list(cpm.GetNames or ()):
                return self._result(False, f"Proprieta' '{name}' non trovata", SwErrors.swSelectionError)
            cpm.Delete2(name)
            left = list(cpm.GetNames or ())
            return self._result(name not in left, f"Proprieta' '{name}' eliminata", SwErrors.swSuccess, {"remaining": left})
        except Exception as e:
            return self._dx_fail("delete_custom_property", e)

    # ====================================================================== variabili globali / equazioni
    def _dx_eqs(self, doc):
        em = doc.GetEquationMgr
        out = []
        for i in range(int(em.GetCount)):
            eq = str(em.Equation(i))
            try:
                val = em.Value(i)
            except Exception:
                val = None
            try:
                gv = bool(em.GlobalVariable(i))
            except Exception:
                gv = False
            out.append({"index": i, "equation": eq, "value": val, "global_variable": gv})
        return em, out

    def _dx_check_model(self, doc) -> Dict:
        """Ricostruisce e riporta feature con errori + volume (pezzi)."""
        self._dx_rebuild(doc)
        info: Dict[str, Any] = {}
        if int(doc.GetType) == 1:
            bad = []
            for n, t, f in self._features(doc):
                try:
                    if int(self._com(f, "GetErrorCode2")) not in (0,):
                        bad.append(n)
                except Exception:
                    pass
            info["feature_errors"] = bad
            info["volume_mm3"] = round(self._volume_m3(doc) * 1e9, 4)
        return info

    def list_equations(self) -> Dict:
        """Elenca equazioni e variabili globali (valori nelle unita' del documento) e lo stato del gestore."""
        try:
            doc, err = self._dx_doc((1, 2))
            if err:
                return err
            em, eqs = self._dx_eqs(doc)
            gl = [e for e in eqs if e["global_variable"]]
            return self._result(True, f"{len(eqs)} equazioni, {len(gl)} variabili globali", SwErrors.swSuccess,
                                {"equations": eqs, "global_variables": {re.match(r'"([^"]+)"', e["equation"]).group(1): e["value"]
                                                                        for e in gl if re.match(r'"([^"]+)"', e["equation"])}})
        except Exception as e:
            return self._dx_fail("list_equations", e)

    def _dx_set_eq(self, doc, em, index: int, text: str):
        """Modifica l'equazione: la PROPRIETA' indicizzata `Equation(i) = testo` (SetEquationAndConfigurationOption restituisce -1)."""
        em.Equation(index, text)

    def set_global_variable(self, name: str, value: Any) -> Dict:
        """Crea o modifica una variabile globale ("nome" = valore). Il valore e' un numero (unita' del documento, mm) o
        un'espressione ("altra"*2). Ricostruisce e riporta errori e volume."""
        try:
            doc, err = self._dx_doc((1, 2))
            if err:
                return err
            em, eqs = self._dx_eqs(doc)
            text = f'"{name}"={value}'
            idx = next((e["index"] for e in eqs if e["global_variable"]
                        and re.match(rf'^"{re.escape(name)}"\s*=', e["equation"])), None)
            if idx is None:
                r = em.Add2(-1, text, True)
                created = True
                if int(r) < 0:
                    return self._result(False, f"Equazione rifiutata: {text}", SwErrors.swInvalidInput)
            else:
                self._dx_set_eq(doc, em, idx, text)
                created = False
            info = self._dx_check_model(doc)
            em, eqs = self._dx_eqs(doc)
            cur = next((e for e in eqs if re.match(rf'^"{re.escape(name)}"\s*=', e["equation"])), None)
            return self._result(cur is not None and not info.get("feature_errors"),
                                f"Variabile '{name}' {'creata' if created else 'modificata'} = {cur['value'] if cur else '?'}",
                                SwErrors.swSuccess, {"name": name, "value": cur["value"] if cur else None,
                                                     "equation": cur["equation"] if cur else text, "created": created, **info})
        except Exception as e:
            return self._dx_fail("set_global_variable", e)

    def delete_global_variable(self, name: str) -> Dict:
        try:
            doc, err = self._dx_doc((1, 2))
            if err:
                return err
            em, eqs = self._dx_eqs(doc)
            idx = next((e["index"] for e in eqs if e["global_variable"]
                        and re.match(rf'^"{re.escape(name)}"\s*=', e["equation"])), None)
            if idx is None:
                return self._result(False, f"Variabile globale '{name}' non trovata", SwErrors.swSelectionError)
            em.Delete(idx)
            info = self._dx_check_model(doc)
            return self._result(True, f"Variabile '{name}' eliminata", SwErrors.swSuccess, info)
        except Exception as e:
            return self._dx_fail("delete_global_variable", e)

    def add_equation(self, equation: str) -> Dict:
        """Aggiunge un'equazione, es. '"D1@Schizzo1" = "lunghezza" * 2' (quota guidata da una variabile). Ricostruisce
        e verifica: se la quota non esiste o l'espressione e' errata, l'equazione viene RIMOSSA e il tool fallisce."""
        try:
            doc, err = self._dx_doc((1, 2))
            if err:
                return err
            em = doc.GetEquationMgr
            n0 = int(em.GetCount)
            r = em.Add2(-1, equation, True)
            if int(r) < 0 or int(em.GetCount) != n0 + 1:
                return self._result(False, f"Equazione rifiutata (quota o variabile inesistente?): {equation}",
                                    SwErrors.swInvalidInput)
            em, eqs = self._dx_eqs(doc)
            info = self._dx_check_model(doc)
            cur = eqs[-1]
            if info.get("feature_errors"):
                em.Delete(n0)
                self._dx_rebuild(doc)
                return self._result(False, f"Equazione con errori, rimossa: {equation}", SwErrors.swInvalidInput, info)
            return self._result(True, f"Equazione {cur['index']}: {cur['equation']} = {cur['value']}", SwErrors.swSuccess,
                                {"index": cur["index"], "value": cur["value"], **info})
        except Exception as e:
            return self._dx_fail("add_equation", e)

    def update_equation(self, index: int, equation: str) -> Dict:
        """Modifica l'equazione `index` (vedi list_equations)."""
        try:
            doc, err = self._dx_doc((1, 2))
            if err:
                return err
            em, eqs = self._dx_eqs(doc)
            if not (0 <= int(index) < len(eqs)):
                return self._result(False, f"Indice {index} fuori intervallo (0..{len(eqs) - 1})", SwErrors.swInvalidInput)
            self._dx_set_eq(doc, em, int(index), equation)
            info = self._dx_check_model(doc)
            em, eqs = self._dx_eqs(doc)
            return self._result(not info.get("feature_errors"), f"Equazione {index}: {eqs[int(index)]['equation']} = {eqs[int(index)]['value']}",
                                SwErrors.swSuccess, {"equation": eqs[int(index)], **info})
        except Exception as e:
            return self._dx_fail("update_equation", e)

    def delete_equation(self, index: int) -> Dict:
        try:
            doc, err = self._dx_doc((1, 2))
            if err:
                return err
            em, eqs = self._dx_eqs(doc)
            if not (0 <= int(index) < len(eqs)):
                return self._result(False, f"Indice {index} fuori intervallo (0..{len(eqs) - 1})", SwErrors.swInvalidInput)
            gone = eqs[int(index)]["equation"]
            em.Delete(int(index))
            info = self._dx_check_model(doc)
            return self._result(True, f"Equazione eliminata: {gone}", SwErrors.swSuccess, info)
        except Exception as e:
            return self._dx_fail("delete_equation", e)

    def evaluate_equations(self) -> Dict:
        """Ricalcola tutte le equazioni, ricostruisce e verifica (errori delle feature, volume, valori)."""
        try:
            doc, err = self._dx_doc((1, 2))
            if err:
                return err
            em = doc.GetEquationMgr
            try:
                em.EvaluateAll
            except Exception:
                pass
            info = self._dx_check_model(doc)
            em, eqs = self._dx_eqs(doc)
            try:
                status = int(em.Status)
            except Exception:
                status = 0
            return self._result(not info.get("feature_errors"),
                                f"{len(eqs)} equazioni valutate (stato {status})", SwErrors.swSuccess,
                                {"equations": eqs, "status": status, **info})
        except Exception as e:
            return self._dx_fail("evaluate_equations", e)

    # ====================================================================== configurazioni del pezzo
    def list_part_configurations(self, include_volume: bool = False) -> Dict:
        """Configurazioni del pezzo/assieme, quella attiva e (opz.) volume di ciascuna (le attiva una a una)."""
        try:
            doc, err = self._dx_doc((1, 2))
            if err:
                return err
            active = self._dx_cfg_name(doc)
            items = []
            try:
                for n in self._dx_cfg_names(doc):
                    it = {"name": n, "active": n == active}
                    try:
                        it["comment"] = str(doc.GetConfigurationByName(n).Comment)
                    except Exception:
                        pass
                    if include_volume and int(doc.GetType) == 1:
                        doc.ShowConfiguration2(n)
                        self._dx_rebuild(doc)
                        it["volume_mm3"] = round(self._volume_m3(doc) * 1e9, 4)
                    items.append(it)
            finally:                                # la configurazione attiva torna quella di partenza anche in caso di errore
                if include_volume and self._dx_cfg_name(doc) != active:
                    doc.ShowConfiguration2(active)
                    self._dx_rebuild(doc)
            return self._result(True, f"{len(items)} configurazioni (attiva: {active})", SwErrors.swSuccess,
                                {"active": active, "configurations": items})
        except Exception as e:
            return self._dx_fail("list_part_configurations", e)

    def add_part_configuration(self, name: str, comment: str = "", activate: bool = True) -> Dict:
        try:
            doc, err = self._dx_doc((1, 2))
            if err:
                return err
            if name in self._dx_cfg_names(doc):
                return self._result(False, f"Configurazione '{name}' esiste gia'", SwErrors.swInvalidInput)
            prev = self._dx_cfg_name(doc)
            c = doc.ConfigurationManager.AddConfiguration2(name, comment or "", "", 0, "", "", False)
            if c is None:
                return self._result(False, f"AddConfiguration2 ha rifiutato '{name}'", SwErrors.swFeatureError)
            if not activate:
                doc.ShowConfiguration2(prev)
            self._dx_rebuild(doc)
            return self._result(True, f"Configurazione '{name}' aggiunta (attiva: {self._dx_cfg_name(doc)})", SwErrors.swSuccess,
                                {"name": name, "active": self._dx_cfg_name(doc), "configurations": self._dx_cfg_names(doc)})
        except Exception as e:
            return self._dx_fail("add_part_configuration", e)

    def activate_part_configuration(self, name: str) -> Dict:
        try:
            doc, err = self._dx_doc((1, 2))
            if err:
                return err
            if name not in self._dx_cfg_names(doc):
                return self._result(False, f"Configurazione '{name}' non trovata: {self._dx_cfg_names(doc)}", SwErrors.swSelectionError)
            ok = doc.ShowConfiguration2(name)
            self._dx_rebuild(doc)
            data = {"active": self._dx_cfg_name(doc)}
            if int(doc.GetType) == 1:
                data["volume_mm3"] = round(self._volume_m3(doc) * 1e9, 4)
            return self._result(bool(ok) and data["active"] == name, f"Configurazione attiva: {data['active']}", SwErrors.swSuccess, data)
        except Exception as e:
            return self._dx_fail("activate_part_configuration", e)

    def delete_part_configuration(self, name: str) -> Dict:
        try:
            doc, err = self._dx_doc((1, 2))
            if err:
                return err
            names = self._dx_cfg_names(doc)
            if name not in names:
                return self._result(False, f"Configurazione '{name}' non trovata: {names}", SwErrors.swSelectionError)
            if len(names) < 2:
                return self._result(False, "Non si puo' eliminare l'unica configurazione", SwErrors.swInvalidInput)
            if self._dx_cfg_name(doc) == name:
                doc.ShowConfiguration2(next(n for n in names if n != name))
            ok = doc.DeleteConfiguration2(name)
            return self._result(bool(ok) and name not in self._dx_cfg_names(doc), f"Configurazione '{name}' eliminata",
                                SwErrors.swSuccess, {"configurations": self._dx_cfg_names(doc), "active": self._dx_cfg_name(doc)})
        except Exception as e:
            return self._dx_fail("delete_part_configuration", e)

    def set_configuration_dimension(self, dimension: str, value: float, configuration: str = None, unit: str = None) -> Dict:
        """Imposta una quota ('D1@Schizzo1') solo in una configurazione (nome | lista | 'all'; default l'attiva).
        Gli angoli in gradi. Fallisce se la quota e' guidata da un'equazione."""
        try:
            doc, err = self._dx_doc((1,))
            if err:
                return err
            d = doc.Parameter(dimension)
            if d is None:
                return self._result(False, f"Quota '{dimension}' non trovata (formato D1@Schizzo1)", SwErrors.swSelectionError)
            try:
                angular = int(self._com(d, "GetType")) == 3
            except Exception:
                angular = False
            si = math.radians(value) if angular else self._mmu(value, unit)
            cfgs = self._dx_cfg_list(doc, configuration)
            bad = self._dx_bad_cfgs(doc, cfgs)
            if bad:
                return bad
            st = d.SetSystemValue3(si, 3, _bstr_array(cfgs))
            if int(st) != 0:
                return self._result(False, f"SetSystemValue3 ha restituito {st} (quota guidata da equazione o di riferimento?)",
                                    SwErrors.swFeatureError)
            self._dx_rebuild(doc)
            return self._result(True, f"{dimension} = {value} nelle configurazioni {cfgs}", SwErrors.swSuccess,
                                {"dimension": dimension, "value": value, "configurations": cfgs,
                                 "volume_active_mm3": round(self._volume_m3(doc) * 1e9, 4)})
        except Exception as e:
            return self._dx_fail("set_configuration_dimension", e)

    def set_configuration_suppression(self, feature: str, suppressed: bool = True, configuration: str = None) -> Dict:
        """Sopprime/riattiva una feature solo in certe configurazioni (nome | lista | 'all'; default l'attiva)."""
        try:
            doc, err = self._dx_doc((1,))
            if err:
                return err
            cfgs = self._dx_cfg_list(doc, configuration)
            bad = self._dx_bad_cfgs(doc, cfgs)
            if bad:
                return bad
            f = self._find_feature(doc, feature)
            if f is None:
                return self._result(False, f"Feature '{feature}' non trovata", SwErrors.swSelectionError)
            ok = f.SetSuppression2(0 if suppressed else 1, 3, _bstr_array(cfgs))
            self._dx_rebuild(doc)
            states = {}
            active = self._dx_cfg_name(doc)
            try:
                for c in cfgs:
                    if c != self._dx_cfg_name(doc):
                        doc.ShowConfiguration2(c)
                        self._dx_rebuild(doc)
                    ff = self._find_feature(doc, feature)
                    states[c] = bool(ff.IsSuppressed2(1, _bstr_array([c]))[0]) if ff is not None else None
            finally:                                # la configurazione attiva torna quella di partenza anche in caso di errore
                if self._dx_cfg_name(doc) != active:
                    doc.ShowConfiguration2(active)
                    self._dx_rebuild(doc)
            return self._result(bool(ok), f"'{feature}' {'soppressa' if suppressed else 'attiva'} in {cfgs}", SwErrors.swSuccess,
                                {"feature": feature, "suppressed_by_configuration": states,
                                 "volume_active_mm3": round(self._volume_m3(doc) * 1e9, 4)})
        except Exception as e:
            return self._dx_fail("set_configuration_suppression", e)

    def apply_configuration_table(self, table: Any, create_missing: bool = True, dry_run: bool = False, unit: str = None) -> Dict:
        """D1: crea/aggiorna le configurazioni di un PEZZO da una tabella (percorso CSV/JSON, testo CSV/JSON o righe inline) con le
        stesse intestazioni delle design table: 'D1@Schizzo1' (quota), '$STATO@Foro1' (S/R), '$PRP@Codice', '$MATERIALE', '$COMMENTO'.
        dry_run=true restituisce il piano senza toccare il modello. Le azioni sono la composizione di metodi gia' verificati; dopo
        un errore si continua e `success` e' true solo se tutte riescono. La configurazione attiva di partenza torna attiva alla fine.
        Una design table vera (Excel) NON viene creata: InsertDesignTable non esiste nella type library di questa versione."""
        from ..utils.config_table import parse_configuration_table, plan_configuration_changes
        try:
            doc, err = self._dx_doc((1,))
            if err:
                return err
            parsed = parse_configuration_table(table)
            if parsed["errors"]:
                return self._result(False, "Tabella non valida: " + " | ".join(parsed["errors"]), SwErrors.swInvalidInput,
                                    {"errors": parsed["errors"], "warnings": parsed["warnings"]})
            existing = self._dx_cfg_names(doc)
            plan = plan_configuration_changes(parsed, existing, create_missing)
            if plan["errors"]:
                return self._result(False, "Piano non applicabile: " + " | ".join(plan["errors"]), SwErrors.swInvalidInput,
                                    {"errors": plan["errors"], "warnings": parsed["warnings"]})
            excel = False
            try:
                import winreg
                winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "Excel.Application"))
                excel = True
            except Exception:
                excel = False
            info = {"excel_available": excel,
                    "design_table": "La design table vera non viene creata (InsertDesignTable non esiste nella type library di questa "
                                    "versione di SolidWorks); le configurazioni sono applicate con le API di SolidWorks. La tabella usa "
                                    "le stesse intestazioni delle design table, quindi si puo' riusare in Excel."}
            data = {"actions": plan["actions"], "warnings": parsed["warnings"], "design_table": info,
                    "configurations": [c["name"] for c in parsed["configurations"]]}
            if dry_run:
                data["dry_run"] = True
                return self._result(True, f"Piano: {len(plan['actions'])} azioni su {len(parsed['configurations'])} configurazioni "
                                          f"(dry_run, modello invariato)", SwErrors.swSuccess, data)
            start = self._dx_cfg_name(doc)
            results = []
            try:
                for a in plan["actions"]:
                    kind = a["action"]
                    cfg = a["configuration"]
                    if kind == "add_configuration":
                        r = self.add_part_configuration(cfg, a.get("comment") or "", activate=False)
                    elif kind == "set_dimension":
                        r = self.set_configuration_dimension(a["dimension"], a["value"], configuration=cfg, unit=unit)
                    elif kind == "set_suppression":
                        r = self.set_configuration_suppression(a["feature"], a["suppressed"], configuration=cfg)
                    elif kind == "set_property":
                        r = self.set_custom_property(a["name"], a["value"], configuration=cfg)
                    elif kind == "assign_material":
                        r = self.assign_material(a["material"], configuration=cfg)
                    else:
                        r = self._result(False, f"azione sconosciuta '{kind}'", SwErrors.swInvalidInput)
                    results.append({**a, "ok": bool(r.get("success")), "message": r.get("message")})
            finally:                                # la configurazione attiva di partenza torna attiva anche in caso di errore
                try:
                    if self._dx_cfg_name(doc) != start:
                        doc.ShowConfiguration2(start)
                        self._dx_rebuild(doc)
                except Exception as e:
                    logger.error(f"apply_configuration_table: ripristino configurazione '{start}' fallito: {e}")
            failed = [r for r in results if not r["ok"]]
            data.update({"results": results, "failed": len(failed), "active": self._dx_cfg_name(doc),
                         "configurations_in_model": self._dx_cfg_names(doc)})
            return self._result(not failed, f"{len(results) - len(failed)}/{len(results)} azioni riuscite (attiva: {data['active']})",
                                SwErrors.swSuccess if not failed else SwErrors.swFeatureError, data)
        except Exception as e:
            return self._dx_fail("apply_configuration_table", e)

    # ====================================================================== export
    def _dx_inspect_stl(self, path: str) -> Dict:
        b = open(path, "rb").read()
        info: Dict[str, Any] = {"format": "stl", "size_bytes": len(b)}
        n = struct.unpack("<I", b[80:84])[0] if len(b) >= 84 else -1
        if len(b) >= 84 and len(b) == 84 + 50 * n:
            info["encoding"] = "binary"
            info["triangles"] = n
            if n:
                lo = [1e30] * 3
                hi = [-1e30] * 3
                for i in range(n):
                    vals = struct.unpack_from("<12f", b, 84 + 50 * i)
                    for v in range(1, 4):
                        for k in range(3):
                            x = vals[3 * v + k]
                            if x < lo[k]:
                                lo[k] = x
                            if x > hi[k]:
                                hi[k] = x
                info["bbox_min"], info["bbox_max"] = [round(x, 6) for x in lo], [round(x, 6) for x in hi]
        else:
            info["encoding"] = "ascii"
            txt = b.decode("latin-1")
            pts = re.findall(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", txt)
            info["triangles"] = len(pts) // 3
            if pts:
                arr = [[float(p[k]) for p in pts] for k in range(3)]
                info["bbox_min"], info["bbox_max"] = [min(a) for a in arr], [max(a) for a in arr]
        if "bbox_min" in info:
            info["bbox_size"] = [round(info["bbox_max"][k] - info["bbox_min"][k], 6) for k in range(3)]
        return info

    def _dx_inspect_3mf(self, path: str) -> Dict:
        info: Dict[str, Any] = {"format": "3mf", "size_bytes": os.path.getsize(path)}
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".model"))
            root = ET.fromstring(z.read(name))
        info["unit"] = root.get("unit")
        verts, tris = [], 0
        for el in root.iter():
            tag = el.tag.split("}")[-1]
            if tag == "vertex":
                verts.append((float(el.get("x")), float(el.get("y")), float(el.get("z"))))
            elif tag == "triangle":
                tris += 1
        info["vertices"], info["triangles"] = len(verts), tris
        if verts:
            lo = [min(v[k] for v in verts) for k in range(3)]
            hi = [max(v[k] for v in verts) for k in range(3)]
            info["bbox_min"], info["bbox_max"] = lo, hi
            info["bbox_size"] = [round(hi[k] - lo[k], 6) for k in range(3)]
        return info

    def _dx_inspect_step(self, path: str) -> Dict:
        txt = open(path, "r", encoding="latin-1", errors="ignore").read()
        info: Dict[str, Any] = {"format": "step", "size_bytes": len(txt)}
        m = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']*)'", txt)
        info["schema"] = m.group(1) if m else None
        sch = (info["schema"] or "").upper()
        info["application_protocol"] = ("AP242" if "242" in sch or "MANAGED_MODEL_BASED" in sch else
                                        "AP214" if "AUTOMOTIVE_DESIGN" in sch else
                                        "AP203" if "CONFIG_CONTROL" in sch else None)
        info["manifold_solid_brep"] = len(re.findall(r"\bMANIFOLD_SOLID_BREP\b", txt))
        info["advanced_brep"] = len(re.findall(r"\bADVANCED_BREP_SHAPE_REPRESENTATION\b", txt))
        info["advanced_faces"] = len(re.findall(r"\bADVANCED_FACE\b", txt))
        # struttura d'assieme: un PRODUCT_DEFINITION per pezzo/sottoassieme, un NAUO per ogni istanza di componente
        info["product_definitions"] = len(re.findall(r"\bPRODUCT_DEFINITION\s*\(", txt))
        info["assembly_occurrences"] = len(re.findall(r"\bNEXT_ASSEMBLY_USAGE_OCCURRENCE\b", txt))
        info["valid_solid"] = (info["manifold_solid_brep"] + info["advanced_brep"]) > 0 and "END-ISO-10303-21" in txt
        return info

    def inspect_export_file(self, filepath: str) -> Dict:
        """Legge un file esportato e lo verifica: STL (triangoli, bounding box), 3MF (unita', vertici, triangoli, box),
        STEP (schema AP, MANIFOLD_SOLID_BREP), IGES/Parasolid (intestazione, dimensione), PDF (presenza 3D/PRC)."""
        try:
            if not os.path.exists(filepath):
                return self._result(False, f"File non trovato: {filepath}", SwErrors.swInvalidInput)
            ext = os.path.splitext(filepath)[1].lower().lstrip(".")
            if ext == "stl":
                info = self._dx_inspect_stl(filepath)
            elif ext == "3mf":
                info = self._dx_inspect_3mf(filepath)
            elif ext in ("step", "stp"):
                info = self._dx_inspect_step(filepath)
            elif ext in ("igs", "iges"):
                txt = open(filepath, "r", encoding="latin-1", errors="ignore").read()
                lines = txt.splitlines()
                info = {"format": "iges", "size_bytes": len(txt), "lines": len(lines),
                        "terminate_line": bool(lines and lines[-1][72:73] == "T")}
            elif ext in ("x_t", "x_b"):
                head = open(filepath, "rb").read(200)
                info = {"format": ext, "size_bytes": os.path.getsize(filepath), "parasolid_header": b"PARASOLID" in head}
            elif ext == "pdf":
                b = open(filepath, "rb").read()
                info = {"format": "pdf", "size_bytes": len(b), "has_3d": b"/3D" in b and b"PRC" in b}
                try:                        # D10: lettura della struttura 3D (stream PRC decompresso, viste); non cambia has_3d
                    info["pdf3d"] = inspect_pdf3d(b)
                except Exception as e:
                    info["pdf3d"] = {"parsed": False, "notes": [f"errore di lettura: {e}"]}
            elif ext in ("eprt", "easm", "edrw"):
                b = open(filepath, "rb").read()
                info = {"format": ext, "size_bytes": len(b)}
                try:                        # D3: verifica strutturale (ZIP + eModel HSF); l'automazione di eDrawings non e' usabile
                    info["edrawings"] = inspect_edrawings(b)
                except Exception as e:
                    info["edrawings"] = {"valid": False, "notes": [f"errore di lettura: {e}"]}
                info["valid"] = bool(info["edrawings"].get("valid"))
            else:
                info = {"format": ext, "size_bytes": os.path.getsize(filepath)}
            return self._result(True, f"{ext.upper()}: " + ", ".join(f"{k}={v}" for k, v in info.items() if k in
                                ("triangles", "bbox_size", "schema", "manifold_solid_brep", "has_3d", "unit")), SwErrors.swSuccess, info)
        except Exception as e:
            return self._dx_fail("inspect_export_file", e)

    def export_model(self, filepath: str, format: str = None, configuration: str = None, quality: str = "fine",
                     deviation: float = None, angle: float = None, binary: bool = True, step_ap: int = 214,
                     units: str = "mm", iges_representation: str = "surfaces", one_file: bool = True,
                     verify: bool = True) -> Dict:
        """Esporta il pezzo/assieme attivo: stl | 3mf | step | iges | x_t | x_b | sat | pdf (PDF 3D) | eprt/easm (eDrawings).
        Il formato si deduce dall'estensione. STL/3MF: quality coarse|fine|custom (custom: deviation mm, angle gradi), binary, units
        mm|cm|m|inch; STEP: step_ap 203|214|242; IGES: iges_representation surfaces|brep|curves. Verifica il file (STL: triangoli e box
        confrontato col modello, STEP: MANIFOLD_SOLID_BREP)."""
        try:
            doc, err = self._dx_doc((1, 2))
            if err:
                return err
            ext = os.path.splitext(filepath)[1].lower().lstrip(".")
            fmt = EXPORT_FORMATS.get((format or ext).lower())
            if fmt is None:
                return self._result(False, f"Formato '{format or ext}' non supportato ({sorted(set(EXPORT_FORMATS))})", SwErrors.swInvalidInput)
            if configuration:
                bad = self._dx_bad_cfgs(doc, [configuration])
                if bad:
                    return bad
            filepath = asked = os.path.abspath(filepath)
            if fmt == "iges" and ext == "iges":
                filepath = filepath[:-5] + ".igs"            # SW non conosce l'estensione .iges
            if fmt == "stl" and ext != "stl":
                filepath = os.path.splitext(filepath)[0] + ".stl"
            if filepath != asked and os.path.exists(filepath):
                # la guardia di sovrascrittura (safety.py) ha controllato il nome richiesto, non questo
                return self._result(False, f"Rifiutato: il file viene scritto come {filepath}, che esiste gia' e verrebbe "
                                    f"sovrascritto. Usa direttamente quel nome (con overwrite=true se voluto).",
                                    SwErrors.swFileSaveError, {"refused": "file_exists", "filepath": filepath})
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            if os.path.exists(filepath):
                os.remove(filepath)
            app = self._sw_app
            prev_cfg = None
            unit_ids = {"mm": 0, "cm": 1, "m": 2, "inch": 3, "in": 3, "ft": 4}
            saved = {}

            def setint(k, v):
                saved[("i", k)] = app.GetUserPreferenceIntegerValue(k)
                app.SetUserPreferenceIntegerValue(k, v)

            def settog(k, v):
                saved[("t", k)] = app.GetUserPreferenceToggle(k)
                app.SetUserPreferenceToggle(k, v)

            def setdbl(k, v):
                saved[("d", k)] = app.GetUserPreferenceDoubleValue(k)
                app.SetUserPreferenceDoubleValue(k, v)
            export_data = win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)
            opts = {"format": fmt}
            try:
                if configuration and configuration != self._dx_cfg_name(doc):
                    prev_cfg = self._dx_cfg_name(doc)
                    doc.ShowConfiguration2(configuration)
                self._dx_rebuild(doc)
                if fmt in ("stl", "3mf"):
                    q = {"coarse": 1, "fine": 2, "custom": 3}.get(str(quality).lower())
                    if q is None:
                        return self._result(False, "quality: coarse | fine | custom", SwErrors.swInvalidInput)
                    if deviation is not None or angle is not None:
                        q = 3
                    if fmt == "stl":
                        setint(78, q)
                        settog(69, bool(binary))
                        settog(71, True)                      # non traslare nel quadrante positivo: coordinate del modello
                        settog(72, bool(one_file))
                        setint(211, unit_ids.get(units.lower(), 0))
                        if q == 3:
                            if deviation is not None:
                                setdbl(2, float(deviation) / 1000.0)
                            if angle is not None:
                                setdbl(3, math.radians(float(angle)))
                    opts.update({"quality": q, "units": units})
                elif fmt == "step":
                    if int(step_ap) not in (203, 214, 242):
                        return self._result(False, "step_ap: 203 | 214 | 242", SwErrors.swInvalidInput)
                    setint(75, int(step_ap))
                    opts["step_ap"] = int(step_ap)
                elif fmt == "iges":
                    rep = {"surfaces": 0, "curves": 1, "surfaces_curves": 2, "brep": 3, "bounded": 4}.get(iges_representation.lower(), 0)
                    setint(83, rep)
                elif fmt == "pdf3d":
                    export_data = app.GetExportFileData(1)
                    export_data.ExportAs3D = True
                e, w = _byref_i4(), _byref_i4()
                ok = doc.Extension.SaveAs(filepath, 0, 1, export_data, e, w)
                model_box = self._dx_box_m(doc) if fmt in ("stl", "3mf") else None   # box della configurazione ESPORTATA
            finally:
                for (k, key), v in saved.items():
                    try:
                        {"i": app.SetUserPreferenceIntegerValue, "t": app.SetUserPreferenceToggle,
                         "d": app.SetUserPreferenceDoubleValue}[k](key, v)
                    except Exception:
                        pass
                if prev_cfg:
                    doc.ShowConfiguration2(prev_cfg)
            exists = os.path.exists(filepath) and os.path.getsize(filepath) > 0
            per_comp = []
            if not exists and fmt == "stl" and not one_file:
                # assieme con un file per componente: SolidWorks scrive "<nome> - <componente>.stl" accanto al nome indicato
                base, ext = os.path.splitext(filepath)
                per_comp = sorted(p for p in glob.glob(glob.escape(base) + " - *" + ext) if os.path.getsize(p) > 0)
                exists = bool(per_comp)
            data = {"filepath": filepath, "size_bytes": os.path.getsize(filepath) if os.path.exists(filepath) else 0,
                    "api_ok": bool(ok), "errors": int(e.value), "warnings": int(w.value), "options": opts}
            if per_comp:
                data["files"] = per_comp
            if not exists:
                return self._result(False, f"Export NON riuscito (errori {int(e.value)})", SwErrors.swExportError, data)
            good = True
            if verify and fmt in ("stl", "3mf", "step", "pdf3d", "iges", "x_t", "x_b", "edrawings") and not per_comp:
                chk = self.inspect_export_file(filepath)
                data["verify"] = chk.get("data", {})
                v = data["verify"]
                if fmt in ("stl", "3mf"):
                    good = v.get("triangles", 0) > 0
                    box = model_box
                    if box and "bbox_size" in v:
                        k = {"mm": 1.0, "cm": 0.1, "m": 0.001, "inch": 1 / 25.4, "in": 1 / 25.4, "ft": 1 / 304.8}.get(units.lower(), 1.0)
                        model = [round((box[3 + i] - box[i]) * 1000.0 * k, 6) for i in range(3)]
                        data["model_bbox_size"] = model
                        data["bbox_max_diff"] = round(max(abs(a - b) for a, b in zip(model, v["bbox_size"])), 6)
                elif fmt == "step":
                    good = bool(v.get("valid_solid"))
                    if v.get("application_protocol") != f"AP{int(step_ap)}":
                        data["warning"] = (f"AP{int(step_ap)} richiesto ma il file e' {v.get('application_protocol')} "
                                           f"({v.get('schema')}): questa edizione di SolidWorks non scrive AP242 via API"
                                           if int(step_ap) == 242 else
                                           f"AP{int(step_ap)} richiesto ma il file e' {v.get('application_protocol')}")
                elif fmt == "pdf3d":
                    good = bool(v.get("has_3d"))
                elif fmt == "edrawings":
                    good = bool(v.get("edrawings", {}).get("valid"))
            return self._result(good, f"Esportato {fmt.upper()} ({data['size_bytes']} byte): {filepath}"
                                + (f" ATTENZIONE: {data['warning']}" if data.get("warning") else ""),
                                SwErrors.swSuccess if good else SwErrors.swExportError, data)
        except Exception as e:
            return self._dx_fail("export_model", e, SwErrors.swExportError)

    # ====================================================================== immagini
    def _dx_collect_ref(self, doc):
        """[(feature, 'ref'|'sketch', visibile)] di piani, assi, origini, punti, sistemi di coordinate e schizzi (anche assorbiti)."""
        out = []

        def visit(f, depth=0):
            while f is not None:
                try:
                    t = str(self._com(f, "GetTypeName2"))
                except Exception:
                    t = ""
                kind = "ref" if t in REF_TYPES else ("sketch" if t in SKETCH_TYPES else None)
                if kind:
                    try:
                        vis = int(f.Visible) == 2
                    except Exception:
                        vis = False
                    out.append((f, kind, vis))
                sub = self._com(f, "GetFirstSubFeature")
                if sub is not None and depth < 3:
                    visit(sub, depth + 1)
                f = self._com(f, "GetNextSubFeature") if depth else self._com(f, "GetNextFeature")
        visit(self._com(doc, "FirstFeature"))
        return out

    def _dx_blank(self, doc, items, show: bool):
        for f, kind, vis in items:
            if show and not vis:
                continue
            try:
                doc.ClearSelection2(True)
                if f.Select2(False, 0):
                    if kind == "sketch":
                        (doc.UnblankSketch() if show else doc.BlankSketch())
                    else:
                        (doc.UnBlankRefGeom() if show else doc.BlankRefGeom())
            except Exception:
                pass
        doc.ClearSelection2(True)

    def export_model_image(self, filepath: str, view: str = "isometric", style: str = "shaded_edges", width: int = None,
                           height: int = None, hide_reference: bool = True, white_background: bool = False,
                           zoom_to_fit: bool = True, perspective: bool = False) -> Dict:
        """Immagine PNG/JPG/BMP del pezzo o assieme attivo. view: isometric|front|back|left|right|top|bottom|trimetric|dimetric;
        style: shaded_edges | shaded | hidden_lines | hidden_gray | wireframe; hide_reference=true nasconde piani, assi, origini, punti e schizzi (poi li ripristina);
        white_background=true sfondo bianco; perspective=true scatta in prospettiva (se la vista non lo e' gia': la aggiunge e la toglie dopo).
        width/height in pixel (solo PNG, entrambi). Criterio della cattura: se width > 2000 o height > 1400 si usa la "cattura di stampa"
        di SolidWorks (preferenze 6 = 1, carta Letter orizzontale, DPI = ceil(max(W/11, H/8.5)) tra 100 e 600), che non dipende dalla
        finestra (fino a 6600x5100 px) e poi si porta al formato esatto WxH con bordi del colore di sfondo; sotto quelle soglie si usa la
        cattura a schermo (~2389x1662 nella finestra nascosta) e, se risulta piu' piccola del richiesto, si rifa' con la cattura di stampa.
        JPG/BMP: risoluzione nativa (a schermo). RealView e occlusione ambientale non sono impostabili via API su questa installazione.
        Le preferenze 6/9/10 vengono rimesse come prima e rilette; SolidWorks rifiuta di rimettere alcuni valori (DPI 1): se non tornano
        lo dice in notes. Lo stato della vista viene ripristinato."""
        try:
            doc, err = self.get_active_doc()
            if err:
                return err
            if int(doc.GetType) not in (1, 2):
                return self._result(False, "Serve un pezzo o un assieme attivo.", SwErrors.swInvalidInput)
            if int(doc.GetType) == 1:
                self._exit_sketch(doc)
            sty = STYLES.get(str(style).lower())
            if sty is None:
                return self._result(False, f"style: {sorted(STYLES)}", SwErrors.swInvalidInput)
            ext = os.path.splitext(filepath)[1].lower()
            if ext not in (".png", ".jpg", ".jpeg", ".bmp"):
                return self._result(False, "Estensione: .png | .jpg | .bmp", SwErrors.swInvalidInput)
            filepath = os.path.abspath(filepath)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            if os.path.exists(filepath):
                os.remove(filepath)
            app = self._sw_app
            mv = doc.ActiveView
            notes = []
            old_mode = None
            try:
                old_mode = int(mv.DisplayMode)
            except Exception:
                pass
            items = self._dx_collect_ref(doc) if hide_reference else []
            saved_prefs = {}
            print_orig = {}                    # D4: valori originali delle preferenze della cattura di stampa (6, 10, 9)
            capture, capture_dpi = "screen", None
            persp_added = persp_on = False
            # D5: nell'assieme i riferimenti DEI COMPONENTI non stanno nel suo albero: toggle di documento "Nascondi tutti i tipi"
            # (swViewDisplayHideAllTypes = 198), salvato e rimesso com'era
            hide_all_old = None
            if hide_reference and int(doc.GetType) == 2:
                try:
                    hide_all_old = bool(doc.Extension.GetUserPreferenceToggle(198, 0))
                    doc.Extension.SetUserPreferenceToggle(198, 0, True)
                    doc.GraphicsRedraw2()
                except Exception as e:
                    hide_all_old = None
                    notes.append(f"riferimenti dei componenti non nascosti: {e}")
            try:
                vid = VIEW_IDS.get(str(view).lower())
                try:
                    doc.ShowNamedView2("" if vid else view, vid if vid else -1)
                except Exception:
                    notes.append("vista non applicata")
                try:
                    mv.DisplayMode = sty
                except Exception:
                    {1: doc.ViewDisplayWireframe, 2: doc.ViewDisplayHiddenremoved, 3: doc.ViewDisplayHiddengreyed,
                     4: doc.ViewDisplayShaded, 5: doc.ViewDisplayShaded}[sty]()
                if items:
                    self._dx_blank(doc, items, show=False)
                if white_background:
                    for k, v in ((305, 0), (99, 0xFFFFFF)):
                        saved_prefs[k] = app.GetUserPreferenceIntegerValue(k)
                        app.SetUserPreferenceIntegerValue(k, v)
                persp_was = False
                try:
                    persp_was = bool(self._com(mv, "HasPerspective"))
                except Exception:
                    pass
                if perspective and not persp_was:
                    try:
                        mv.AddPerspective()
                        persp_added = True
                    except Exception as ex:
                        notes.append(f"prospettiva non applicata: {ex}")
                persp_on = persp_was or persp_added
                if zoom_to_fit:
                    doc.ViewZoomtofit2()
                size = None
                sized = bool(width and height) and ext == ".png"
                if (width or height) and not sized:
                    notes.append("width e height insieme servono (solo PNG): ignorati" if ext == ".png" else
                                 "width/height solo per PNG (JPG/BMP: risoluzione nativa)")
                e, w = _byref_i4(), _byref_i4()
                target = os.path.join(os.path.dirname(filepath), "_native_" + os.path.basename(filepath)) if sized else filepath

                def shoot(use_print):
                    """Cattura in target: a schermo o di stampa (preferenze 6, 10, 9 salvate in print_orig alla prima volta)."""
                    nonlocal capture, capture_dpi
                    if os.path.exists(target):
                        os.remove(target)
                    if use_print:
                        capture_dpi = _print_dpi(width, height)
                        if max(int(width) / _PRINT_PAPER_IN[0], int(height) / _PRINT_PAPER_IN[1]) > _PRINT_DPI_MAX:
                            notes.append(f"risoluzione richiesta oltre il limite della cattura di stampa ({_PRINT_DPI_MAX} DPI)")
                        for k in (6, 10, 9):
                            if k not in print_orig:
                                print_orig[k] = app.GetUserPreferenceIntegerValue(k)
                        for k, v in ((6, 1), (10, 0), (9, capture_dpi)):
                            app.SetUserPreferenceIntegerValue(k, v)
                        capture = "print"
                    doc.Extension.SaveAs(target, 0, 1, null_variant(), e, w)

                use_print = sized and _wants_print_capture(width, height)
                shoot(use_print)
                if sized and os.path.exists(target):
                    nw, nh = _png_dims(target)
                    if not use_print and (nw < int(width) or nh < int(height)):   # finestra piu' piccola del richiesto: ricatturo di stampa
                        shoot(True)
                    ww, hh, shrunk = _resize_png(target, filepath, int(width), int(height), recenter=True)
                    os.remove(target)
                    size = (ww, hh)
                    if not shrunk:
                        notes.append(f"risoluzione richiesta > nativa: salvata a {ww}x{hh}")
            finally:
                if items:
                    self._dx_blank(doc, items, show=True)
                if hide_all_old is not None:
                    try:
                        doc.Extension.SetUserPreferenceToggle(198, 0, hide_all_old)
                        doc.GraphicsRedraw2()
                    except Exception:
                        pass
                for k, v in saved_prefs.items():
                    try:
                        app.SetUserPreferenceIntegerValue(k, v)
                    except Exception:
                        pass
                if persp_added:
                    try:
                        mv.RemovePerspective()
                    except Exception as ex:
                        notes.append(f"prospettiva non rimossa: {ex}")
                for k in (6, 10, 9):                 # D4: ripristino, rilettura e dichiarazione di cio' che SolidWorks non rimette
                    if k in print_orig:
                        try:
                            app.SetUserPreferenceIntegerValue(k, print_orig[k])
                            now = app.GetUserPreferenceIntegerValue(k)
                            if now != print_orig[k]:
                                notes.append(f"preferenza {k}: ripristinata a {print_orig[k]} ma SolidWorks la rilegge {now}")
                        except Exception as ex:
                            notes.append(f"preferenza {k} non ripristinata: {ex}")
                if old_mode:
                    try:
                        mv.DisplayMode = old_mode
                    except Exception:
                        pass
            exists = os.path.exists(filepath) and os.path.getsize(filepath) > 0
            data = {"filepath": filepath, "view": view, "style": style, "hide_reference": hide_reference,
                    "hidden_items": len([1 for i in items if i[2]]), "white_background": white_background,
                    "perspective": persp_on, "capture": capture, "capture_dpi": capture_dpi}
            if size:
                data["width"], data["height"] = size
            if notes:
                data["notes"] = notes
            return self._result(exists, f"Immagine {'salvata' if exists else 'NON salvata'}: {filepath}",
                                SwErrors.swSuccess if exists else SwErrors.swExportError, data)
        except Exception as e:
            return self._dx_fail("export_model_image", e, SwErrors.swExportError)

    # ====================================================================== import
    _NEUTRAL_EXT = ("step", "stp", "iges", "igs", "x_t", "x_b", "xmt_txt", "xmt_bin")

    def _import_part_stats(self, doc) -> Dict:
        """Corpi solidi/superficie, facce e volume (mm3) di un pezzo importato."""
        st = {"solid_bodies": 0, "surface_bodies": 0, "faces": 0, "volume_mm3": 0.0}
        for kind, key in ((0, "solid_bodies"), (1, "surface_bodies")):
            try:
                for b in (doc.GetBodies2(kind, False) or ()):
                    st[key] += 1
                    try:
                        st["faces"] += int(b.GetFaceCount)
                    except Exception:
                        pass
            except Exception:
                pass
        try:
            st["volume_mm3"] = round(self._volume_m3(doc) * 1e9, 4)
        except Exception:
            pass
        return st

    def _import_part_bodies(self, doc) -> List[Dict]:
        """Elenco dei corpi (solidi e superfici) di un pezzo: nome, tipo, volume (mm3), facce."""
        out = []
        for kind, label in ((0, "solid"), (1, "surface")):
            for b in (doc.GetBodies2(kind, False) or ()):
                info = {"name": str(b.Name), "type": label}
                try:
                    mpv = b.GetMassProperties(1.0)
                    info["volume_mm3"] = round(float(mpv[3]) * 1e9, 4)
                except Exception:
                    pass
                try:
                    info["faces"] = int(b.GetFaceCount)
                except Exception:
                    pass
                out.append(info)
        return out

    def import_model(self, filepath: str, import_as: str = "solid", units: str = "mm", step_as: str = None,
                     interconnect: bool = None, diagnose: bool = False) -> Dict:
        """Apre STEP/IGES/Parasolid/STL (anche SAT, 3MF se supportato) e restituisce i corpi (o i componenti) importati con volume e box.
        import_as (solo STL/VRML): solid | surface | graphics; units (STL): mm|cm|m|inch.
        step_as (STEP/IGES/Parasolid): None = preferenza attuale | "assembly" (preferenza 579 = 0) | "part" (579 = 2, pezzo multicorpo).
        interconnect: None = lascia | True/False -> toggle 691 (3D Interconnect: l'assieme resta collegato al file sorgente / viene convertito).
        diagnose: per i pezzi importati, IPartDoc.ImportDiagnosis(CloseAllGaps=True, RemoveFaces=False, FixFaces=True, Options=0).
        Le preferenze (globali) toccate vengono lette, impostate e ripristinate in un finally; il risultato riporta options_used e,
        in notes, ogni valore che dopo il ripristino non coincide con l'originale."""
        try:
            step_key = None if step_as is None else str(step_as).strip().lower()
            if step_key not in (None, "assembly", "part"):
                return self._result(False, "step_as deve essere 'assembly' o 'part'", SwErrors.swInvalidInput)
            if interconnect is not None and not isinstance(interconnect, bool):
                return self._result(False, "interconnect deve essere true o false", SwErrors.swInvalidInput)
            if not self.is_connected:
                r = self.connect()
                if not r["success"]:
                    return r
            filepath = os.path.abspath(filepath)
            if not os.path.exists(filepath):
                return self._result(False, f"File non trovato: {filepath}", SwErrors.swInvalidInput)
            app = self._sw_app
            ext = os.path.splitext(filepath)[1].lower().lstrip(".")
            notes: List[str] = []
            options_used: Dict[str, Any] = {}
            wanted_int: Dict[int, int] = {}
            wanted_tog: Dict[int, bool] = {}
            if ext in ("stl", "wrl", "obj", "3mf"):
                wanted_int[208] = {"graphics": 0, "surface": 1, "solid": 2}.get(import_as.lower(), 2)
                wanted_int[210] = {"mm": 0, "cm": 1, "m": 2, "inch": 3, "in": 3}.get(units.lower(), 0)
                options_used["import_as"] = import_as.lower()
                options_used["units"] = units.lower()
            if step_key is not None:
                if ext in self._NEUTRAL_EXT:
                    wanted_int[579] = 0 if step_key == "assembly" else 2
                    options_used["step_as"] = step_key
                else:
                    notes.append(f"step_as ignorato: vale solo per STEP/IGES/Parasolid (file .{ext})")
            if interconnect is not None:
                wanted_tog[691] = interconnect
                options_used["interconnect"] = interconnect
            saved_int: Dict[int, int] = {}
            saved_tog: Dict[int, bool] = {}
            doc = None
            e = _byref_i4()
            try:
                for k, v in wanted_int.items():
                    saved_int[k] = int(app.GetUserPreferenceIntegerValue(k))
                    app.SetUserPreferenceIntegerValue(k, v)
                    got = int(app.GetUserPreferenceIntegerValue(k))
                    if k == 579:
                        options_used["pref_579_applied"] = got
                    if got != v:
                        notes.append(f"preferenza {k}: impostato {v}, riletto {got}")
                for k, v in wanted_tog.items():
                    saved_tog[k] = bool(app.GetUserPreferenceToggle(k))
                    app.SetUserPreferenceToggle(k, v)
                    got = bool(app.GetUserPreferenceToggle(k))
                    options_used["pref_691_applied"] = got
                    if got != v:
                        notes.append(f"preferenza {k}: impostato {v}, riletto {got}")
                idat = None
                try:
                    idat = app.GetImportFileData(filepath)
                except Exception:
                    idat = None
                if idat is not None:
                    try:
                        idat.MapConfigurationData = False
                    except Exception:
                        pass
                doc = app.LoadFile4(filepath, "r", idat if idat is not None else null_variant(), e)
            finally:
                for k, v in saved_int.items():
                    try:
                        app.SetUserPreferenceIntegerValue(k, v)
                    except Exception:
                        pass
                for k, v in saved_tog.items():
                    try:
                        app.SetUserPreferenceToggle(k, v)
                    except Exception:
                        pass
            prefs_after: Dict[str, Any] = {}
            for k, v in saved_int.items():
                try:
                    now = int(app.GetUserPreferenceIntegerValue(k))
                    prefs_after[str(k)] = now
                    if now != v:
                        notes.append(f"preferenza {k} NON ripristinata: originale {v}, ora {now}")
                except Exception:
                    pass
            for k, v in saved_tog.items():
                try:
                    now = bool(app.GetUserPreferenceToggle(k))
                    prefs_after[str(k)] = now
                    if now != v:
                        notes.append(f"preferenza {k} NON ripristinata: originale {v}, ora {now}")
                except Exception:
                    pass
            if doc is None:
                return self._result(False, f"Import fallito (errore {int(e.value)})", SwErrors.swUnknownError)
            title = self._get_doc_title(doc)
            try:
                app.ActivateDoc3(title, False, 0, _byref_i4())
            except Exception:
                pass
            doc_type = int(doc.GetType)
            bodies = []
            comps_top = comps_all = None
            if doc_type == 2:
                # assieme: niente corpi diretti, si elencano i componenti di primo livello (il volume e' la somma)
                top = doc.GetComponents(True) or ()
                comps_top = len(top)
                try:
                    comps_all = len(doc.GetComponents(False) or ())
                except Exception:
                    pass
                for c in top:
                    try:
                        bodies.append({"name": str(c.Name2), "type": "component"})
                    except Exception:
                        pass
            else:
                bodies = self._import_part_bodies(doc)
            diagnosis = None
            if diagnose:
                if doc_type != 1:
                    diagnosis = {"skipped": "la diagnosi vale solo per i pezzi (il documento importato e' un assieme)"}
                else:
                    before = self._import_part_stats(doc)
                    diagnosis = {"bodies_before": {"solid": before["solid_bodies"], "surface": before["surface_bodies"]},
                                 "faces_before": before["faces"], "volume_before_mm3": before["volume_mm3"]}
                    try:
                        diagnosis["return_code"] = int(doc.ImportDiagnosis(True, False, True, 0))
                    except Exception as ex:
                        diagnosis["error"] = str(ex)[:300]
                    after = self._import_part_stats(doc)
                    diagnosis["bodies_after"] = {"solid": after["solid_bodies"], "surface": after["surface_bodies"]}
                    diagnosis["faces_after"] = after["faces"]
                    diagnosis["volume_after_mm3"] = after["volume_mm3"]
                    bodies = self._import_part_bodies(doc)
            box = self._dx_box_m(doc)
            vol = self._volume_m3(doc) * 1e9
            data = {"title": title, "document_type": doc_type, "bodies": bodies, "volume_mm3": round(vol, 4),
                    "source": filepath, "options_used": options_used}
            if prefs_after:
                data["preferences_after_restore"] = prefs_after
            if comps_top is not None:
                data["components_top"] = comps_top
                data["components_all"] = comps_all
            if interconnect is not None:
                data["interconnect_note"] = (
                    "3D Interconnect attivo: il documento resta collegato al file sorgente (titolo senza estensione SolidWorks)"
                    if interconnect else
                    "3D Interconnect spento: il file e' stato convertito in documenti SolidWorks (.SLDPRT/.SLDASM), senza collegamento alla sorgente")
            if diagnosis is not None:
                data["diagnosis"] = diagnosis
            if notes:
                data["notes"] = notes
            if box:
                data["bbox_min_mm"] = [round(v * 1000, 4) for v in box[:3]]
                data["bbox_max_mm"] = [round(v * 1000, 4) for v in box[3:]]
            return self._result(len(bodies) > 0, f"Importato '{title}': {len(bodies)} corpi, volume {vol:.3f} mm3",
                                SwErrors.swSuccess, data)
        except Exception as e:
            return self._dx_fail("import_model", e)

    # ====================================================================== misure
    def get_bounding_box(self, body: str = None, unit: str = None) -> Dict:
        """Bounding box allineato agli assi (coordinate del modello/assieme): min, max, dimensioni, centro. Pezzo: esatto
        (punti estremi dei corpi); assieme: unione dei box dei componenti attivi."""
        try:
            doc, err = self._dx_doc((1, 2))
            if err:
                return err
            bd, err = self._dx_body(doc, body)
            if err:
                return err
            bname = str(bd.Name) if bd is not None else None
            box = self._dx_box_m(doc, bd)
            if not box:
                return self._result(False, "Nessuna geometria", SwErrors.swUnknownError)
            u = self._unit_name(unit)
            f = lambda v: round(self._from_m(v, u), 6)
            mn, mx = [f(v) for v in box[:3]], [f(v) for v in box[3:]]
            size = [round(mx[i] - mn[i], 6) for i in range(3)]
            return self._result(True, f"Box {size[0]} x {size[1]} x {size[2]} {u}", SwErrors.swSuccess,
                                {"min": mn, "max": mx, "size": size, "center": [round((mn[i] + mx[i]) / 2, 6) for i in range(3)],
                                 "unit": u, "body": bname})
        except Exception as e:
            return self._dx_fail("get_bounding_box", e)

    def _dx_sel_spec(self, doc, spec, unit, append):
        if not isinstance(spec, dict) or len(spec) != 1:
            return None, "Entita' attesa come {\"face\":[x,y,z]} | {\"edge\":[x,y,z]} | {\"vertex\":[x,y,z]}"
        kind, pt = next(iter(spec.items()))
        ok, info = self._select_point(doc, kind, pt, unit, append=append, mark=0, tol_mm=0.05)
        if not ok:
            return None, info.get("error", "selezione fallita")
        return info, None

    def measure_entities(self, entity1: dict, entity2: dict = None, unit: str = None) -> Dict:
        """Misura (Extension.CreateMeasure) fra due entita' scelte per coordinate ({"face":[x,y,z]}, {"edge":..}, {"vertex":..}) o
        su una sola: distanza minima, distanza normale, delta X/Y/Z, angolo (gradi), parallele/perpendicolari; raggio/diametro/area/
        lunghezza dove applicabile."""
        try:
            doc, err = self._part()
            if err:
                return err
            doc.ClearSelection2(True)
            infos = []
            for i, spec in enumerate([entity1] + ([entity2] if entity2 else [])):
                info, e = self._dx_sel_spec(doc, spec, unit, i > 0)
                if e:
                    doc.ClearSelection2(True)
                    return self._result(False, f"Entita' {i + 1}: {e}", SwErrors.swSelectionError)
                infos.append(info)
            m = self._com(doc.Extension, "CreateMeasure")
            ok = m.Calculate
            if not ok:
                doc.ClearSelection2(True)
                return self._result(False, "Misura non riuscita (selezione non misurabile)", SwErrors.swFeatureError)
            u = self._unit_name(unit)

            def L(n):
                try:
                    v = float(getattr(m, n))
                    return None if v < 0 else round(self._from_m(v, u), 6)
                except Exception:
                    return None
            data: Dict[str, Any] = {"unit": u, "entities": infos}
            for key, n in (("distance", "Distance"), ("normal_distance", "NormalDistance"), ("radius", "Radius"),
                           ("diameter", "Diameter"), ("length", "Length"), ("area", None), ("center_distance", "CenterDistance"),
                           ("perimeter", "Perimeter")):
                if n:
                    v = L(n)
                    if v is not None:
                        data[key] = v
            try:
                a = float(m.Area)
                if a >= 0:
                    data["area_mm2"] = round(a * 1e6, 6)
            except Exception:
                pass
            try:
                ang = float(m.Angle)
                if ang >= 0:
                    data["angle_deg"] = round(math.degrees(ang), 6)
            except Exception:
                pass
            if "distance" in data:
                for ax in ("X", "Y", "Z"):
                    try:
                        data["delta_" + ax.lower()] = round(self._from_m(float(getattr(m, "Delta" + ax)), u), 6)
                    except Exception:
                        pass
            for key, n in (("parallel", "IsParallel"), ("perpendicular", "IsPerpendicular")):
                try:
                    data[key] = bool(getattr(m, n))
                except Exception:
                    pass
            doc.ClearSelection2(True)
            txt = ", ".join(f"{k}={data[k]}" for k in ("distance", "angle_deg", "diameter", "radius", "area_mm2", "length") if k in data)
            return self._result(True, f"Misura: {txt}", SwErrors.swSuccess, data)
        except Exception as e:
            return self._dx_fail("measure_entities", e)

    def measure_face(self, x: float, y: float, z: float, unit: str = None) -> Dict:
        """Proprieta' della faccia che contiene il punto (x,y,z): tipo (piana/cilindrica/conica/sferica/toroidale/altra), area, e
        per le cilindriche raggio, diametro, asse e punto dell'asse; per le piane normale."""
        try:
            doc, err = self._part()
            if err:
                return err
            u = self._unit_name(unit)
            face, d = self._find_entity(doc, "face", [self._mmu(c, unit) for c in (x, y, z)], 0.05 / 1000.0)
            if face is None:
                return self._result(False, f"Nessuna faccia entro 0,05 mm dal punto ({x},{y},{z})", SwErrors.swSelectionError)
            s = self._com(face, "GetSurface")
            data: Dict[str, Any] = {"unit": u, "area_mm2": round(float(self._com(face, "GetArea")) * 1e6, 6)}
            if self._com(s, "IsCylinder"):
                p = [float(v) for v in self._com(s, "CylinderParams")]
                data.update({"type": "cylinder", "radius": round(self._from_m(p[6], u), 6), "diameter": round(self._from_m(2 * p[6], u), 6),
                             "axis_direction": [round(v, 6) for v in p[3:6]],
                             "axis_point": [round(self._from_m(v, u), 6) for v in p[0:3]]})
            elif self._com(s, "IsPlane"):
                p = [float(v) for v in self._com(s, "PlaneParams")]
                data.update({"type": "plane", "normal": [round(v, 6) for v in p[0:3]],
                             "point": [round(self._from_m(v, u), 6) for v in p[3:6]]})
            elif self._com(s, "IsSphere"):
                p = [float(v) for v in self._com(s, "SphereParams")]
                data.update({"type": "sphere", "center": [round(self._from_m(v, u), 6) for v in p[0:3]],
                             "radius": round(self._from_m(p[3], u), 6), "diameter": round(self._from_m(2 * p[3], u), 6)})
            elif self._com(s, "IsCone"):
                p = [float(v) for v in self._com(s, "ConeParams")]
                data.update({"type": "cone", "origin": [round(self._from_m(v, u), 6) for v in p[0:3]],
                             "axis_direction": [round(v, 6) for v in p[3:6]], "radius_at_origin": round(self._from_m(p[6], u), 6),
                             "half_angle_deg": round(math.degrees(p[7]), 6)})
            elif self._com(s, "IsTorus"):
                p = [float(v) for v in self._com(s, "TorusParams")]
                data.update({"type": "torus", "major_radius": round(self._from_m(p[6], u), 6), "minor_radius": round(self._from_m(p[7], u), 6)})
            else:
                data["type"] = "other"
            txt = {"cylinder": f"cilindro Ø{data.get('diameter')} {u}", "plane": "piana"}.get(data["type"], data["type"])
            return self._result(True, f"Faccia {txt}, area {data['area_mm2']} mm2", SwErrors.swSuccess, data)
        except Exception as e:
            return self._dx_fail("measure_face", e)
