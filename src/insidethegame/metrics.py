"""Derived metrics. All formulas are simple, transparent heuristics (not fitted to real data).

Pitch coordinates: x in [0, 105] m toward the attacking goal, y in [0, 68] m. Goal centre (105, 34).
"""
from __future__ import annotations
import math
from collections import deque

GOAL_X, GOAL_Y, GOAL_WIDTH = 105.0, 34.0, 7.32


def distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def shot_geometry(x: float, y: float) -> tuple[float, float]:
    """Return (distance to goal centre in m, visible goal angle in radians)."""
    d = distance(x, y, GOAL_X, GOAL_Y)
    dx = max(GOAL_X - x, 0.01)
    a1 = math.atan2(GOAL_Y + GOAL_WIDTH / 2 - y, dx)
    a2 = math.atan2(GOAL_Y - GOAL_WIDTH / 2 - y, dx)
    return d, abs(a1 - a2)


def xg(x: float, y: float, pressure: float = 0.0, header: bool = False) -> float:
    """Simple logistic xG-like estimate.

    logit = -1.1 - 0.11*distance + 1.6*angle - 0.8*pressure - 0.6*header
    Coefficients are hand-picked so that a penalty-spot shot (~11 m, central) is ~0.2-0.3
    and a 25 m shot is ~0.03-0.05. It is an illustrative model, not a trained one.
    """
    d, ang = shot_geometry(x, y)
    logit = -1.1 - 0.11 * d + 1.6 * ang - 0.8 * pressure - 0.6 * (1 if header else 0)
    return round(1 / (1 + math.exp(-logit)), 3)


def ball_speed_kmh(dist_m: float, duration_s: float) -> float:
    """Average ball speed = distance / time, converted to km/h."""
    return round(dist_m / max(duration_s, 0.05) * 3.6, 1)


def pass_difficulty(dist_m: float, pressure: float, forward_m: float) -> float:
    """Difficulty in [0, 1]: 0.5*min(dist/40,1) + 0.3*pressure + 0.2*clip(forward/30, 0, 1)."""
    return round(0.5 * min(dist_m / 40, 1) + 0.3 * pressure + 0.2 * min(max(forward_m / 30, 0), 1), 3)


def pass_quality(dist_m: float, pressure: float, forward_m: float, success: bool) -> float:
    """Pass quality score 0-100.

    Completed: 50 + 50*difficulty (hard completions score highest).
    Failed:    30*(1 - difficulty) penalised less when the pass was hard.
    """
    d = pass_difficulty(dist_m, pressure, forward_m)
    return round(50 + 50 * d if success else 30 * d, 1)


class ControlChaosIndex:
    """Rolling index over the last `window_s` seconds of match time.

    control (per team, 0..1) = 0.5*possession_share + 0.3*pass_completion + 0.2*final_third_share
    chaos (0..1) = min(1, (turnovers + pressures*0.5 + fouls) / (window_minutes * 6))
    momentum (-1..1) = control_home - control_away
    """

    def __init__(self, home_id: str, away_id: str, window_s: float = 300.0):
        self.home, self.away, self.window = home_id, away_id, window_s
        self.events: deque[dict] = deque()

    def update(self, ev: dict) -> dict:
        self.events.append(ev)
        while self.events and ev["t"] - self.events[0]["t"] > self.window:
            self.events.popleft()
        return self.snapshot()

    def snapshot(self) -> dict:
        stats = {t: {"pass": 0, "ok": 0, "f3": 0} for t in (self.home, self.away)}
        turnovers = pressures = fouls = 0
        for e in self.events:
            team = e.get("team")
            if e["type"] == "pass" and team in stats:
                s = stats[team]
                s["pass"] += 1
                s["ok"] += 1 if e.get("success") else 0
                s["f3"] += 1 if e.get("end_x", 0) > 70 else 0
            elif e["type"] == "turnover":
                turnovers += 1
            elif e["type"] == "pressure":
                pressures += 1
            elif e["type"] in ("foul", "card"):
                fouls += 1
        total = sum(s["pass"] for s in stats.values()) or 1
        f3_total = sum(s["f3"] for s in stats.values()) or 1
        control = {}
        for t, s in stats.items():
            comp = s["ok"] / s["pass"] if s["pass"] else 0.0
            control[t] = round(0.5 * s["pass"] / total + 0.3 * comp + 0.2 * s["f3"] / f3_total, 3)
        minutes = self.window / 60
        chaos = round(min(1.0, (turnovers + 0.5 * pressures + fouls) / (minutes * 6)), 3)
        return {"control": control, "chaos": chaos,
                "momentum": round(control[self.home] - control[self.away], 3),
                "label": "chaos" if chaos > 0.6 else ("control" if max(control.values()) > 0.55 else "balanced")}
