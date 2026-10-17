"""
Librerie dei materiali (.sldmat): parti pure, senza SolidWorks (testabili offline).

SolidWorks tiene l'elenco delle cartelle dei database dei materiali in Opzioni > Percorsi dei file > Database dei materiali
(`GetUserPreferenceStringValue(swFileLocationsMaterialDatabases = 28)`): una stringa con le cartelle separate da `;`.
Puo' contenere cartelle inesistenti, voci vuote e doppioni: qui si ripulisce e si fonde con le cartelle standard.
"""

import ntpath
import os
from typing import Callable, Dict, Iterable, List, Optional, Tuple

# swUserPreferenceStringValue_e.swFileLocationsMaterialDatabases (verificato dalla type library)
SW_FILE_LOCATIONS_MATERIAL_DATABASES = 28


def split_path_list(value: Optional[str]) -> List[str]:
    """'C:\\a; C:\\b;;"C:\\c d"' -> ['C:\\a', 'C:\\b', 'C:\\c d'] (spazi e virgolette esterne tolti, voci vuote scartate).
    Le variabili d'ambiente (%VAR%) restano testo."""
    out = []
    for part in str(value or "").split(";"):
        p = part.strip().strip('"').strip()
        if p:
            out.append(p)
    return out


def norm_dir(path: str) -> str:
    """Chiave di confronto di una cartella: percorso normalizzato, senza maiuscole/separatore finale (Windows)."""
    return ntpath.normcase(ntpath.normpath(path))     # regole di Windows (SolidWorks gira solo li'), uguali su ogni sistema


def merge_material_dirs(preference: Optional[str], standard: Iterable[Optional[str]],
                        exists: Callable[[str], bool] = os.path.isdir) -> List[str]:
    """Elenco ordinato, senza doppioni, delle cartelle da leggere: prima quelle della preferenza (stringa separata da ';'),
    poi le standard se non gia' presenti. Solo cartelle che esistono (`exists`)."""
    out: List[str] = []
    seen = set()
    for p in split_path_list(preference) + [s for s in standard if s]:
        key = norm_dir(p)
        if key in seen:
            continue
        seen.add(key)
        if exists(p):
            out.append(os.path.normpath(p))
    return out


def list_sldmat_files(dirs: Iterable[str], standard_names: Iterable[str] = ()) -> List[Tuple[str, str]]:
    """[(cartella, nome_file)] di tutti i .sldmat, cartella per cartella; in ogni cartella prima i file standard
    (`standard_names`, senza distinguere le maiuscole), poi gli altri in ordine alfabetico."""
    std = [s.lower() for s in standard_names]
    out: List[Tuple[str, str]] = []
    for d in dirs:
        try:
            names = [f for f in os.listdir(d) if f.lower().endswith(".sldmat") and os.path.isfile(os.path.join(d, f))]
        except OSError:
            continue
        first = [f for s in std for f in names if f.lower() == s]
        rest = sorted((f for f in names if f not in first), key=str.lower)
        out.extend((d, f) for f in first + rest)
    return out


def libraries_signature(dirs: Iterable[str], files: Iterable[Tuple[str, str]]) -> tuple:
    """Firma delle librerie: (cartelle, ((percorso, mtime_ns, dimensione), ...)). Cambia se cambia l'elenco delle cartelle
    o se un .sldmat viene aggiunto, tolto, riscritto. Costa una stat per file."""
    items = []
    for d, f in files:
        p = os.path.join(d, f)
        try:
            st = os.stat(p)
            items.append((p, st.st_mtime_ns, st.st_size))
        except OSError:
            items.append((p, 0, -1))
    return (tuple(dirs), tuple(items))


def dedupe_materials(materials: Iterable[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Stesso nome (senza distinguere le maiuscole) in due librerie diverse (campo `database`): si tiene il primo, gli altri
    finiscono in `duplicates` come {name, kept_database, other_database}. Nella stessa libreria i nomi ripetuti restano
    (categorie diverse dello stesso file)."""
    kept: List[Dict] = []
    dups: List[Dict] = []
    first_db: Dict[str, str] = {}
    for m in materials:
        key = str(m.get("name") or "").lower()
        db = m.get("database")
        if key in first_db and norm_dir(first_db[key]) != norm_dir(db):
            dups.append({"name": m.get("name"), "kept_database": first_db[key], "other_database": db})
            continue
        first_db.setdefault(key, db)
        kept.append(m)
    return kept, dups


def build_sldmat(materials: Iterable[Dict], classification: str = "Personalizzati") -> bytes:
    """.sldmat minimo (XML UTF-16 con BOM, struttura copiata da un materiale vero di 'solidworks materials.sldmat') con i
    materiali {name, density [kg/m3], elastic_modulus [Pa], poisson, matid} in una sola classificazione. Serve ai test:
    la struttura segue 'ABS generico' (shaders, xhatch, physicalproperties EX/NUXY/GXY/DENS/KX/C/SIGXT/SIGYLD)."""
    from xml.sax.saxutils import quoteattr

    parts = ['<?xml version="1.0" encoding="utf-16"?>\n'
             '<mstns:materials xmlns:mstns="http://www.solidworks.com/sldmaterials" '
             'xmlns:msdata="urn:schemas-microsoft-com:xml-msdata" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
             'xmlns:sldcolorswatch="http://www.solidworks.com/sldcolorswatch" version="2008.03">\n'
             f'  <classification name={quoteattr(classification)}>\n']
    for i, m in enumerate(materials):
        dens = float(m["density"])
        ex = float(m.get("elastic_modulus", 2.0e9))
        nu = float(m.get("poisson", 0.3))
        parts.append(
            f'    <material name={quoteattr(str(m["name"]))} matid="{int(m.get("matid", 9001 + i))}" envdata="1" failurecriteria="4">\n'
            '      <shaders>\n        <cgshader2 name="PlasticPolystyrene" ignorescolor="false"/>\n      </shaders>\n'
            '      <xhatch name="ISO (Plastica)" angle="0.0" scale="1.0"/>\n'
            '      <physicalproperties>\n'
            f'        <EX displayname="Elastic modulus" value="{ex:.6f}"/>\n'
            f'        <NUXY displayname="Poisson ratio" value="{nu:.6f}"/>\n'
            f'        <GXY displayname="Shear modulus" value="{ex / (2 * (1 + nu)):.6f}"/>\n'
            f'        <DENS displayname="Mass density" value="{dens:.6f}"/>\n'
            '        <KX displayname="Thermal conductivity" value="0.200000"/>\n'
            '        <C displayname="Specific heat" value="1400.000000"/>\n'
            '        <SIGXT displayname="Tensile strength" value="30000000.000000"/>\n'
            '        <SIGYLD displayname="Yield strength" value="30000000.000000"/>\n'
            '      </physicalproperties>\n'
            '    </material>\n')
    parts.append('  </classification>\n</mstns:materials>\n')
    return "".join(parts).encode("utf-16")
