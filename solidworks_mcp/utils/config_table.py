"""
D1 - Tabella delle configurazioni (CSV / JSON) senza Excel: lettura, controllo e piano delle modifiche.

Parte PURA (nessuna chiamata a SolidWorks): la applica il tool `apply_configuration_table` (da collegare sul PC) usando
metodi gia' verificati: add_part_configuration, set_configuration_dimension, set_configuration_suppression,
set_custom_property(configuration=), assign_material(configuration=).

Intestazioni (stessa convenzione delle design table, cosi' la tabella si puo' riusare in Excel):
  prima colonna            nome della configurazione (intestazione libera: "Configurazione", "Nome", vuota...)
  D1@Schizzo1              quota (numero; mm o gradi come set_configuration_dimension)
  $STATO@Foro1             soppressione: S / soppresso / suppressed / 1 / si  -> soppressa
                                         R / A / attivo / riattivato / unsuppressed / 0 / no -> attiva
  $PRP@Codice              proprieta' personalizzata della configurazione (testo)
  $MATERIALE               materiale della configurazione (nome della libreria)
  $COMMENTO                commento della configurazione
Cella vuota = non cambiare quel valore in quella configurazione. Numeri anche con la virgola decimale ("12,5").
CSV: separatore ';' (Excel italiano), ',' o tabulazione, riconosciuto dall'intestazione.
JSON: lista di righe [{"Configurazione": "Lunga", "D1@Schizzo1": 60}, ...] oppure {"Lunga": {"D1@Schizzo1": 60}, ...}.
"""

import csv
import io
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

NAME_KEYS = ("configurazione", "configuration", "nome", "name", "config", "")
_SUPPRESSED = {"s", "soppresso", "soppressa", "suppressed", "1", "si", "sì", "true", "yes", "y"}
_ACTIVE = {"r", "a", "attivo", "attiva", "riattivato", "riattivata", "unsuppressed", "0", "no", "false", "n"}
_DIM_RE = re.compile(r"^[^$@\s][^@]*@[^@]+(@[^@]+)?$")        # D1@Schizzo1 (eventualmente @parte)


def classify_column(header: str) -> Tuple[str, Optional[str]]:
    """('dimension'|'suppression'|'property'|'material'|'comment'|'unknown', argomento)."""
    h = (header or "").strip()
    up = h.upper()
    for prefix in ("$STATO@", "$STATE@"):
        if up.startswith(prefix):
            return "suppression", h[len(prefix):].strip()
    for prefix in ("$PRP@", "$PROPRIETA@", "$PROPERTY@"):
        if up.startswith(prefix):
            return "property", h[len(prefix):].strip()
    if up in ("$MATERIALE", "$MATERIAL", "SW-MATERIAL", "$SW-MATERIAL"):
        return "material", None
    if up in ("$COMMENTO", "$COMMENT", "$DESCRIZIONE", "$DESCRIPTION"):
        return "comment", None
    if _DIM_RE.match(h):
        return "dimension", h
    return "unknown", h


def _number(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "")
    if re.fullmatch(r"[-+]?\d+,\d+", s):          # virgola decimale italiana
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _empty(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def _rows_from_csv(text: str) -> List[Dict[str, Any]]:
    text = text.lstrip("﻿")
    first = text.splitlines()[0] if text.strip() else ""
    delim = max((";", ",", "\t"), key=first.count) if first else ";"
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        return []
    header = [h.strip() for h in rows[0]]
    out = []
    for r in rows[1:]:
        r = r + [""] * (len(header) - len(r))
        out.append({"__name__": r[0].strip(), **{header[i]: r[i] for i in range(1, len(header))}, "__extra__": r[len(header):]})
    return out


def _rows_from_json(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict):
        return [{"__name__": str(k), **(v or {})} for k, v in data.items()]
    rows = []
    for item in data or []:
        item = dict(item)
        key = next((k for k in item if k.strip().lower() in NAME_KEYS), None)
        name = item.pop(key) if key is not None else ""
        rows.append({"__name__": str(name).strip() if name is not None else "", **item})
    return rows


def load_rows(source: Any) -> List[Dict[str, Any]]:
    """Righe grezze da: percorso .csv/.json, testo CSV/JSON, lista o dizionario gia' in memoria."""
    if isinstance(source, (list, dict)):
        return _rows_from_json(source)
    s = str(source)
    if os.path.isfile(s):
        with open(s, "r", encoding="utf-8-sig") as f:
            text = f.read()
        return _rows_from_json(json.loads(text)) if s.lower().endswith(".json") else _rows_from_csv(text)
    st = s.strip()
    if "\n" not in st and st.lower().endswith((".csv", ".json")):
        # un percorso sbagliato non e' una tabella CSV di una riga: dirlo invece di rispondere "tabella vuota"
        raise OSError(f"file non trovato: {s}")
    if st.startswith("[") or st.startswith("{"):
        return _rows_from_json(json.loads(st))
    return _rows_from_csv(s)


def parse_configuration_table(source: Any) -> Dict[str, Any]:
    """Legge e controlla la tabella. Restituisce {"configurations": [...], "columns": [...], "errors": [...], "warnings": [...]}.
    Ogni configurazione: {"name", "comment", "material", "dimensions": {quota: valore}, "suppression": {feature: bool},
    "properties": {nome: testo}}. Con errori la tabella NON va applicata."""
    errors: List[str] = []
    warnings: List[str] = []
    try:
        rows = load_rows(source)
    except (ValueError, OSError, csv.Error) as e:
        return {"configurations": [], "columns": [], "errors": [f"tabella illeggibile: {e}"], "warnings": []}
    if not rows:
        return {"configurations": [], "columns": [], "errors": ["tabella vuota"], "warnings": []}
    headers: List[str] = []
    for r in rows:
        for k in r:
            if k not in ("__name__", "__extra__") and k not in headers:
                headers.append(k)
    columns = []
    for h in headers:
        kind, arg = classify_column(h)
        columns.append({"header": h, "kind": kind, "target": arg})
        if kind == "unknown":
            errors.append(f"colonna '{h}' non riconosciuta (quota 'D1@Schizzo1', '$STATO@feature', '$PRP@nome', '$MATERIALE', '$COMMENTO')")
    kinds = {c["header"]: c for c in columns}
    seen = set()
    configs = []
    for i, r in enumerate(rows, start=2):
        name = r.get("__name__", "")
        if not name:
            errors.append(f"riga {i}: nome della configurazione vuoto")
            continue
        if name.lower() in seen:
            errors.append(f"riga {i}: configurazione '{name}' ripetuta")
            continue
        seen.add(name.lower())
        if any(not _empty(x) for x in r.get("__extra__", [])):
            errors.append(f"riga {i} ('{name}'): piu' celle che colonne nell'intestazione")
        cfg = {"name": name, "comment": None, "material": None, "dimensions": {}, "suppression": {}, "properties": {}}
        for h, v in r.items():
            if h in ("__name__", "__extra__") or _empty(v):
                continue
            c = kinds[h]
            if c["kind"] == "dimension":
                n = _number(v)
                if n is None:
                    errors.append(f"riga {i} ('{name}'), {h}: '{v}' non e' un numero")
                else:
                    cfg["dimensions"][c["target"]] = n
            elif c["kind"] == "suppression":
                t = str(v).strip().lower()
                if t in _SUPPRESSED:
                    cfg["suppression"][c["target"]] = True
                elif t in _ACTIVE:
                    cfg["suppression"][c["target"]] = False
                else:
                    errors.append(f"riga {i} ('{name}'), {h}: '{v}' non e' uno stato (S = soppressa, R = attiva)")
            elif c["kind"] == "property":
                cfg["properties"][c["target"]] = str(v).strip()
            elif c["kind"] == "material":
                cfg["material"] = str(v).strip()
            elif c["kind"] == "comment":
                cfg["comment"] = str(v).strip()
        if not (cfg["dimensions"] or cfg["suppression"] or cfg["properties"] or cfg["material"]):
            warnings.append(f"'{name}': nessun valore da impostare (verra' solo creata se manca)")
        configs.append(cfg)
    return {"configurations": configs, "columns": columns, "errors": errors, "warnings": warnings}


def plan_configuration_changes(table: Dict[str, Any], existing: List[str], create_missing: bool = True) -> Dict[str, Any]:
    """Azioni ordinate (per dry_run e per l'applicazione) date le configurazioni gia' presenti nel modello.
    Ogni azione: {"action": add_configuration|set_dimension|set_suppression|set_property|assign_material, ...}."""
    if table.get("errors"):
        return {"actions": [], "errors": list(table["errors"])}
    have = {e.lower(): e for e in existing}
    actions: List[Dict[str, Any]] = []
    errors: List[str] = []
    for cfg in table["configurations"]:
        name = have.get(cfg["name"].lower(), cfg["name"])
        if cfg["name"].lower() not in have:
            if not create_missing:
                errors.append(f"configurazione '{cfg['name']}' assente nel modello (create_missing=false)")
                continue
            actions.append({"action": "add_configuration", "configuration": name, "comment": cfg.get("comment") or ""})
        for dim, val in cfg["dimensions"].items():
            actions.append({"action": "set_dimension", "configuration": name, "dimension": dim, "value": val})
        for feat, sup in cfg["suppression"].items():
            actions.append({"action": "set_suppression", "configuration": name, "feature": feat, "suppressed": sup})
        for prop, txt in cfg["properties"].items():
            actions.append({"action": "set_property", "configuration": name, "name": prop, "value": txt})
        if cfg.get("material"):
            actions.append({"action": "assign_material", "configuration": name, "material": cfg["material"]})
    return {"actions": actions, "errors": errors}
