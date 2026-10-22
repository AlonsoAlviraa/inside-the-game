"""Fictional league, previews, win probability and tactical views — all computed from the synthetic engine.

Win probability is a transparent Poisson model: each team's remaining goals ~ Poisson(rate * minutes_left/90), where
rate blends a prior (from the fictional strength rating) with the xG rate observed so far (weight = minutes played/90).
"""
from __future__ import annotations
import math

from . import insights, season
from .teams import LEAGUE_DAYS, teams_for_seed

FULL = 95  # nominal match length incl. stoppage, minutes


def result(seed: int) -> dict:
    m = next(x for x in season.season()["matches"] if x["seed"] == seed)
    return {"seed": seed, "home": m["home"], "away": m["away"], "score": m["score"]}


def league_seeds(up_to_day: int = LEAGUE_DAYS) -> list[int]:
    return [m["seed"] for m in season.matches(up_to_day)]


def table(up_to_day: int = LEAGUE_DAYS) -> list[dict]:
    return season.table(up_to_day)


def _pois(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def outcome_probs(score_h: int, score_a: int, lam_h: float, lam_a: float) -> dict:
    ph = pd = pa = 0.0
    for i in range(11):
        for j in range(11):
            p = _pois(i, lam_h) * _pois(j, lam_a)
            fh, fa = score_h + i, score_a + j
            if fh > fa:
                ph += p
            elif fh == fa:
                pd += p
            else:
                pa += p
    tot = ph + pd + pa
    return {"home": round(ph / tot, 3), "draw": round(pd / tot, 3), "away": round(pa / tot, 3)}


def priors(seed: int) -> tuple[float, float]:
    h, a = teams_for_seed(seed)
    base = 1.35
    return (round(base * (1 + 2 * (h.strength - a.strength)) + 0.15, 3),  # small home advantage
            round(base * (1 + 2 * (a.strength - h.strength)), 3))


def win_probability(seed: int, step: int = 1) -> list[dict]:
    """Win/draw/loss probability per match minute (live-safe: each point only uses events up to that minute)."""
    evs = insights.events(seed)
    meta = evs[0]["meta"]
    H, A = meta["home"]["id"], meta["away"]["id"]
    ph, pa = priors(seed)
    xg = {H: 0.0, A: 0.0}
    score = {H: 0, A: 0}
    out, i, played = [], 1, 0
    last_minute = evs[-1]["minute"]
    for m in range(0, 91 + step, step):
        # consume events up to elapsed minute m (both halves on one 0..90 axis)
        while i < len(evs) and _elapsed(evs[i]) <= m:
            e = evs[i]
            # Goals are counted through their shot: the generator emits every goal as a `shot` (outcome
            # "goal") followed by a `goal` event carrying the same xG, so adding the goal too would double count.
            if e["type"] == "shot":
                xg[e["team"]] += e["xg"]
            elif e["type"] == "goal":
                score = dict(e["score"])
            i += 1
        played = min(m, 90)
        w = played / 90
        left = max(0.0, (FULL - played)) / 90 if m < 90 else 0.0
        rh = (1 - w) * ph + w * (xg[H] / max(played, 1) * 90)
        ra = (1 - w) * pa + w * (xg[A] / max(played, 1) * 90)
        out.append({"minute": m, "score": dict(score), "xg": {k: round(v, 2) for k, v in xg.items()}, **outcome_probs(score[H], score[A], rh * left, ra * left)})
    while i < len(evs):  # stoppage time
        if evs[i]["type"] == "shot":
            xg[evs[i]["team"]] += evs[i]["xg"]
        if evs[i]["type"] == "goal":
            score = dict(evs[i]["score"])
        i += 1
    final = outcome_probs(score[H], score[A], 0, 0)
    out.append({"minute": max(91, last_minute), "score": score, "xg": {k: round(v, 2) for k, v in xg.items()}, **final, "final": True})
    return out


def _elapsed(e: dict) -> int:
    """Match minute on a 0..90 axis (first-half stoppage counts as 45, second-half stoppage as 90)."""
    if e["period"] == 1:
        return min(e["minute"], 45)
    return min(e["minute"], 90)


def preview(seed: int) -> dict:
    """Pre-match comparison from league matches played BEFORE this fixture, plus earlier meetings this season."""
    evs = insights.events(seed)
    meta = evs[0]["meta"]
    H, A = meta["home"]["id"], meta["away"]["id"]
    day = season.day_of(seed) if seed >= 1000 else LEAGUE_DAYS + 1
    before = day - 1
    tbl = {r["id"]: r for r in season.table(before)} if before > 0 else {}
    ph, pa = priors(seed)
    h, a = teams_for_seed(seed)

    def side(t, team):
        ss = season.team_season(t, before) if before > 0 else None
        return {"id": t, "name": meta[team]["name"], "rating": (h if team == "home" else a).strength,
                "table": tbl.get(t) if tbl and tbl[t]["played"] else None,
                "season": {k: ss[k] for k in ("played", "totals", "per_match", "top_scorer")} if ss and ss["played"] else None}
    return {"synthetic": True, "seed": seed, "matchday": day if seed >= 1000 else None, "standings_after_matchday": max(before, 0),
            "home": side(H, "home"), "away": side(A, "away"),
            "expected_goals_prior": {H: ph, A: pa}, "pre_match_probability": outcome_probs(0, 0, ph * FULL / 90, pa * FULL / 90),
            "meetings": season.meetings(seed),
            "lineups": {t["id"]: [{"name": p["name"], "number": p["number"], "position": p["position"]}
                                  for p in t["players"][:11]] for t in (meta["home"], meta["away"])}}


SLOTS = {"GK": (5, 34), "RB": (25, 60), "CB": (20, 42), "LB": (25, 8), "DM": (38, 34), "CM": (50, 34),
         "RW": (75, 58), "ST": (85, 34), "LW": (75, 10)}


def formation(seed: int, up_to_minute: int = 200) -> dict:
    """Nominal 4-3-3 shape plus each starter's average action position (own attacking direction, 0-105 x 0-68)."""
    evs = insights.events(seed)
    meta = evs[0]["meta"]
    acc: dict[str, list] = {}
    for e in evs:
        if e["type"] == "pass" and e["minute"] <= up_to_minute:
            acc.setdefault(e["player_id"], []).append((e["x"], e["y"]))
    teams = {}
    for t in (meta["home"], meta["away"]):
        rows = []
        cb = cm = 0
        for p in t["players"][:11]:
            sx, sy = SLOTS[p["position"]]
            if p["position"] == "CB":
                sy, cb = (42 if cb == 0 else 26), cb + 1
            if p["position"] == "CM":
                sy, cm = (50 if cm == 0 else 18), cm + 1
                sx = 52
            pts = acc.get(p["id"], [])
            rows.append({"id": p["id"], "name": p["name"], "number": p["number"], "position": p["position"],
                         "slot": [sx, sy], "touches": len(pts),
                         "avg": [round(sum(x for x, _ in pts) / len(pts), 1), round(sum(y for _, y in pts) / len(pts), 1)] if pts else None})
        teams[t["id"]] = {"shape": "4-3-3", "players": rows}
    return {"synthetic": True, "seed": seed, "teams": teams}


def compare(seed: int, a: str, b: str, up_to_minute: int = 200) -> dict:
    rows = {p["player_id"]: p for p in insights.report(seed, up_to_minute)["players"]}
    return {"a": rows.get(a), "b": rows.get(b)}
