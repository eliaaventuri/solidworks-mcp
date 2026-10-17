"""
D7 - Proprieta' di massa rispetto a un sistema di coordinate utente (calcolo puro, senza SolidWorks).

Ingressi nel sistema del MODELLO (come li da' IMassProperty2): massa m, baricentro c, tensore d'inerzia I_c nel baricentro
(assi del modello). Sistema utente: origine o e matrice R le cui COLONNE sono gli assi X, Y, Z dell'utente espressi nel modello.
  baricentro nel sistema utente           c' = R^T (c - o)
  tensore nel baricentro, assi utente     I_c' = R^T I_c R
  tensore nell'origine utente, assi utente I_o' = I_c' + m (|d|^2 E - d d^T),  d = c'   (Huygens-Steiner)
Convenzione fuori diagonale (parametro `offdiag`):
  "tensor"   tensore vero: J_xy = -integrale(x*y dm)   -> Steiner aggiunge -m*dx*dy, la rotazione e' R^T J R
  "products" prodotti d'inerzia: P_xy = +integrale(x*y dm) (come nella finestra Proprieta' di massa di SolidWorks)
Internamente si lavora sempre col tensore vero; l'uscita usa la stessa convenzione dell'ingresso.
Quale convenzione usi `IMassProperty2.GetMomentOfInertia` non e' noto a priori (il test di B3 aveva prodotti nulli): la decide
a runtime `detect_offdiag_convention` (confronto fra tensore nel baricentro e all'origine, entrambi letti da SolidWorks).
Verifica sul PC (D7): blocco con baricentro in (15, 10, 0) mm -> all'origine il termine xy vale -m*0,015*0,010 (tensor)
oppure +m*0,015*0,010 (products).

Da SolidWorks: `doc.Extension.GetCoordinateSystemTransformByName(nome).ArrayData` -> 13 valori: [0:9] rotazione, [9:12]
traslazione (m), [12] scala. In B2 e' stato verificato che le tre RIGHE della rotazione sono gli assi X, Y, Z del sistema
utente nel modello: `frame_from_sw_transform` le mette come colonne di R.
"""

import math
from typing import Dict, List, Sequence, Tuple

Vec = List[float]
Mat = List[List[float]]


def mat_t(a: Mat) -> Mat:
    return [[a[j][i] for j in range(3)] for i in range(3)]


def mat_mul(a: Mat, b: Mat) -> Mat:
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def mat_vec(a: Mat, v: Sequence[float]) -> Vec:
    return [sum(a[i][k] * v[k] for k in range(3)) for i in range(3)]


def as_matrix(t: Sequence) -> Mat:
    """3x3 da una lista di 9 valori (per righe) o da una lista di 3 righe."""
    if len(t) == 9:
        return [[float(t[3 * i + j]) for j in range(3)] for i in range(3)]
    return [[float(x) for x in row] for row in t]


def frame_from_sw_transform(array_data: Sequence[float], unit_scale: float = 1.0) -> Tuple[Mat, Vec]:
    """(R con gli assi come colonne, origine) dai 13 valori di un MathTransform di un sistema di coordinate."""
    rows = [[float(array_data[3 * i + j]) for j in range(3)] for i in range(3)]
    origin = [float(array_data[9 + k]) * unit_scale for k in range(3)]
    return mat_t(rows), origin


def check_rotation(r: Mat, tol: float = 1e-6) -> List[str]:
    """Problemi della matrice (non ortonormale, sinistrorsa); lista vuota se va bene."""
    issues = []
    rtr = mat_mul(mat_t(r), r)
    err = max(abs(rtr[i][j] - (1.0 if i == j else 0.0)) for i in range(3) for j in range(3))
    if err > tol:
        issues.append(f"assi non ortonormali (scarto {err:.2e})")
    det = (r[0][0] * (r[1][1] * r[2][2] - r[1][2] * r[2][1]) - r[0][1] * (r[1][0] * r[2][2] - r[1][2] * r[2][0])
           + r[0][2] * (r[1][0] * r[2][1] - r[1][1] * r[2][0]))
    if det < 0:
        issues.append("sistema sinistrorso (determinante negativo)")
    return issues


def steiner(i_c: Mat, mass: float, d: Sequence[float]) -> Mat:
    """Tensore VERO spostato dal baricentro a un punto a distanza d (stessi assi)."""
    dd = sum(x * x for x in d)
    return [[i_c[i][j] + mass * ((dd if i == j else 0.0) - d[i] * d[j]) for j in range(3)] for i in range(3)]


def principal_moments(i: Mat) -> Vec:
    """Autovalori (crescenti) di un tensore simmetrico 3x3, formula chiusa (Smith)."""
    p1 = i[0][1] ** 2 + i[0][2] ** 2 + i[1][2] ** 2
    q = (i[0][0] + i[1][1] + i[2][2]) / 3.0
    if p1 < 1e-30 * max(1.0, q * q):
        return sorted([i[0][0], i[1][1], i[2][2]])
    p2 = sum((i[k][k] - q) ** 2 for k in range(3)) + 2 * p1
    p = math.sqrt(p2 / 6.0)
    b = [[(i[r][c] - (q if r == c else 0.0)) / p for c in range(3)] for r in range(3)]
    detb = (b[0][0] * (b[1][1] * b[2][2] - b[1][2] * b[2][1]) - b[0][1] * (b[1][0] * b[2][2] - b[1][2] * b[2][0])
            + b[0][2] * (b[1][0] * b[2][1] - b[1][1] * b[2][0]))
    phi = math.acos(max(-1.0, min(1.0, detb / 2.0))) / 3.0
    e1 = q + 2 * p * math.cos(phi)
    e3 = q + 2 * p * math.cos(phi + 2 * math.pi / 3)
    return sorted([e1, 3 * q - e1 - e3, e3])


def flip_offdiag(i: Mat) -> Mat:
    """Passa da tensore vero a prodotti d'inerzia e viceversa (cambia segno ai termini fuori diagonale)."""
    return [[i[r][c] if r == c else -i[r][c] for c in range(3)] for r in range(3)]


def detect_offdiag_convention(i_com: Sequence, mass: float, com: Sequence[float], i_origin: Sequence,
                              tol: float = 1e-4) -> str:
    """Decide a runtime la convenzione dei termini fuori diagonale di `GetMomentOfInertia`, confrontando il tensore
    all'origine letto da SolidWorks con Huygens-Steiner applicato a quello nel baricentro (entrambi nel sistema del modello,
    com in m). Nelle due convenzioni i termini fuori diagonale all'origine differiscono di 2*m*d_i*d_j:
      "tensor"        i_origin = steiner(i_com)                          (J_xy = -integrale(x*y dm))
      "products"      i_origin = flip_offdiag(steiner(flip_offdiag(i_com)))  (P_xy = +integrale(x*y dm))
      "indeterminate" segnale m*d_i*d_j troppo piccolo (baricentro su un asse o su un piano coordinato): non si distingue;
                      oppure nessuna delle due convenzioni riproduce i dati. Chi chiama usa "tensor" e lo dichiara.
    `tol`: soglia relativa (rispetto al massimo termine diagonale all'origine)."""
    j_c, j_o = as_matrix(i_com), as_matrix(i_origin)
    scale = max(abs(j_o[k][k]) for k in range(3)) or 1.0
    floor = tol * scale
    cand_t = steiner(j_c, mass, com)
    cand_p = flip_offdiag(steiner(flip_offdiag(j_c), mass, com))
    pairs = [(0, 1), (0, 2), (1, 2)]
    signal = max(abs(mass * com[a] * com[b]) for a, b in pairs)
    if signal < 4 * floor:
        return "indeterminate"
    err_t = max(abs(j_o[a][b] - cand_t[a][b]) for a, b in pairs)
    err_p = max(abs(j_o[a][b] - cand_p[a][b]) for a, b in pairs)
    if err_t <= floor + 0.25 * signal and err_t < err_p:
        return "tensor"
    if err_p <= floor + 0.25 * signal and err_p < err_t:
        return "products"
    return "indeterminate"


def mass_properties_in_frame(mass: float, com: Sequence[float], inertia_com: Sequence, r: Mat,
                             origin: Sequence[float], offdiag: str = "tensor") -> Dict[str, object]:
    """Baricentro e tensori nel sistema utente (stesse unita' degli ingressi: m e kg*m2 se vengono da SolidWorks).
    `offdiag`: "tensor" | "products", vedi il docstring del modulo."""
    if offdiag not in ("tensor", "products"):
        raise ValueError("offdiag: 'tensor' | 'products'")
    conv = flip_offdiag if offdiag == "products" else (lambda m: m)
    j_c = conv(as_matrix(inertia_com))
    rt = mat_t(r)
    c_user = mat_vec(rt, [com[k] - origin[k] for k in range(3)])
    j_c_user = mat_mul(mat_mul(rt, j_c), r)
    j_o_user = steiner(j_c_user, mass, c_user)
    return {"center_of_mass": c_user, "inertia_at_center_of_mass": conv(j_c_user), "inertia_at_origin": conv(j_o_user),
            "principal_moments": principal_moments(j_c_user), "frame_issues": check_rotation(r), "offdiag": offdiag}


def rotation_about(axis: str, degrees: float) -> Mat:
    """Rotazione attiva attorno a X, Y o Z (colonne = assi ruotati): utile per costruire sistemi utente di prova."""
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return {"x": [[1, 0, 0], [0, c, -s], [0, s, c]],
            "y": [[c, 0, s], [0, 1, 0], [-s, 0, c]],
            "z": [[c, -s, 0], [s, c, 0], [0, 0, 1]]}[axis.lower()]
