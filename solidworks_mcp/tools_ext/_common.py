"""Costanti comuni degli schemi dei tool aggiunti per lotti (stesse convenzioni di modeling_tools.py)."""

S, N, B, A, O = "string", "number", "boolean", "array", "object"
UNIT = (S, "Length unit (default mm)")
SK = (S, "Sketch name (default: active/last)")
ENT = (None, "Sketch entity: draw_* id, '@x,y' (segment), 'pt@x,y' (point), 'origin'")
PT3 = (A, "Point [x,y,z] (`unit`) ON the entity")
PTS3 = (A, "Points [[x,y,z],...] (`unit`), one ON each entity")
DIR = (None, "{\"edge\":[x,y,z]} | {\"face\":[x,y,z]} | {\"plane\":name} | {\"axis\":name} | name")
