"""Expected Threat (xT), derived from OUR synthetic matches - no third-party grid is used.

Method: Karun Singh, "Introducing Expected Threat (xT)" (2018, https://karun.in/blog/expected-threat.html),
as also implemented in socceraction (MIT). The published 12x8 grid from that post carries no explicit
licence, so we do not ship it; instead we solve the same Markov value iteration on synthetic data:

    xT(z) = s(z) * g(z) + m(z) * sum_z' T(z -> z') * xT(z')

s = P(shot | action in z), g = P(goal | shot in z), m = P(move | action in z),
T = P(successful move ends in z' | move from z)  (failed moves contribute 0).
"""
from __future__ import annotations
from functools import lru_cache

L, W = 16, 12          # grid columns (length) x rows (width)
PITCH_X, PITCH_Y = 105.0, 68.0


def cell(x: float, y: float) -> int:
    cx = min(L - 1, max(0, int(x / PITCH_X * L)))
    cy = min(W - 1, max(0, int(y / PITCH_Y * W)))
    return cy * L + cx


def fit(actions: list[dict], iterations: int = 30) -> list[float]:
    """Fit an xT grid from SPADL action rows (pass/cross/shot). Returns a flat list (row-major, W x L)."""
    n = L * W
    shots, goals, moves = [0] * n, [0] * n, [0] * n
    trans = [dict() for _ in range(n)]
    for a in actions:
        z = cell(a["start_x"], a["start_y"])
        if a["type_name"] == "shot":
            shots[z] += 1
            goals[z] += a["result_name"] == "success"
        elif a["type_name"] in ("pass", "cross"):
            moves[z] += 1
            if a["result_name"] == "success":
                z2 = cell(a["end_x"], a["end_y"])
                trans[z][z2] = trans[z].get(z2, 0) + 1
    xt = [0.0] * n
    for _ in range(iterations):
        new = []
        for z in range(n):
            tot = shots[z] + moves[z]
            if not tot:
                new.append(0.0)
                continue
            s, m = shots[z] / tot, moves[z] / tot
            g = goals[z] / shots[z] if shots[z] else 0.0
            cont = sum(c * xt[z2] for z2, c in trans[z].items()) / moves[z] if moves[z] else 0.0
            new.append(s * g + m * cont)
        xt = new
    return [round(v, 5) for v in xt]


@lru_cache(maxsize=1)
def default_grid(seeds: tuple[int, ...] = tuple(range(1, 41))) -> tuple[float, ...]:
    """Grid fitted on 40 synthetic matches (deterministic, computed once per process)."""
    from .generator import MatchGenerator
    from .spadl import to_spadl
    acts: list[dict] = []
    for s in seeds:
        acts += to_spadl(list(MatchGenerator(s).events()), game_id=s)
    return tuple(fit(acts))


def value(x: float, y: float, grid: tuple[float, ...] | None = None) -> float:
    g = grid or default_grid()
    return g[cell(x, y)]


def added(action: dict, grid: tuple[float, ...] | None = None) -> float:
    """xT added by a successful pass/cross (end value - start value); 0 otherwise."""
    if action.get("type_name", action.get("type")) not in ("pass", "cross"):
        return 0.0
    if not action.get("result_name") == "success" and not action.get("success"):
        return 0.0
    sx, sy = action.get("start_x", action.get("x")), action.get("start_y", action.get("y"))
    return round(value(action["end_x"], action["end_y"], grid) - value(sx, sy, grid), 4)
