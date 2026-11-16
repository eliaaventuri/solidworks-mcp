"""
Valutazione di espressioni matematiche scritte dall'utente (curve da equazione), senza `eval`.

`eval(testo, {"__builtins__": {}}, nomi)` non e' un recinto: da un numero o da una tupla si risale a qualunque classe di
Python (`().__class__.__bases__...`). Qui l'espressione viene letta con `ast` e si accettano SOLO numeri, i nomi ammessi,
le quattro operazioni, potenza, modulo, segno e le chiamate alle funzioni ammesse. Tutto il resto solleva ValueError.
"""
import ast
import operator
from typing import Callable, Dict, Union

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv}
_UN = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_MAX_LEN = 500            # un'espressione piu' lunga non e' una formula di curva
_MAX_POW = 1e6            # esponente oltre il quale il calcolo puo' solo bloccare o traboccare


def safe_eval(expr: str, names: Dict[str, Union[float, Callable]]) -> float:
    """Valore di `expr` con le variabili e le funzioni di `names` (es. {"t": 0.5, "sin": math.sin, "pi": math.pi})."""
    if not isinstance(expr, str) or len(expr) > _MAX_LEN:
        raise ValueError("espressione non valida o troppo lunga")
    try:
        tree = ast.parse(expr.replace("^", "**").strip(), mode="eval")
    except SyntaxError as e:
        raise ValueError(f"espressione non valida: {e.msg}") from None

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in names and not callable(names[node.id]):
                return names[node.id]
            raise ValueError(f"nome non ammesso: {node.id}")
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > _MAX_POW:
                raise ValueError("esponente troppo grande")
            return _BIN[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UN:
            return _UN[type(node.op)](ev(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            fn = names.get(node.func.id)
            if callable(fn):
                return fn(*[ev(a) for a in node.args])
            raise ValueError(f"funzione non ammessa: {node.func.id}")
        raise ValueError(f"elemento non ammesso nell'espressione: {type(node).__name__}")

    return float(ev(tree))
