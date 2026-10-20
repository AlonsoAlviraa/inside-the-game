"""Fictional league, previews, win probability and tactical views — all computed from the synthetic engine.

Win probability is a transparent Poisson model: each team's remaining goals ~ Poisson(rate * minutes_left/90), where
rate blends a prior (from the fictional strength rating) with the xG rate observed so far (weight = minutes played/90).
"""
from __future__ import annotations
import math
from functools import lru_cache

from . import insights
from .generator import MatchGenerator
from .teams import FIXTURES, LEAGUE_DAYS, _POOL, club_list, make_team, teams_for_seed

FULL = 95  # nominal match length incl. stoppage, minutes


@lru_cache(maxsize=256)
def result(seed: int) -> dict:
    evs = insights.events(seed)
    meta, end = evs[0]["meta"], evs[-1]
    return {"seed": seed, "home": meta["home"]["id"], "away": meta["away"]["id"], "score": end["score"]}


def league_seeds(up_to_day: int = LEAGUE_DAYS) -> list[int]:
    return sorted(s for s in FIXTURES if s >= 1000 and (s - 1000) // 10 <= up_to_day)


@lru_cache(maxsize=16)
def table(up_to_day: int = LEAGUE_DAYS) -> list[dict]:
    rows = {c["id"]: {"id": c["id"], "name": c["name"], "short": c["short"], "color": c["color"], "crest": c["crest"],
                      "played": 0, "won": 0, "drawn": 0, "lost": 0, "gf": 0, "ga": 0, "points": 0, "form": []}
            for c in club_list()}
    for s in league_seeds(up_to_day):
        r = result(s)
        h, a = r["home"], r["away"]
        gh, ga = r["score"][h], r["score"][a]
        for t, f, g in ((h, gh, ga), (a, ga, gh)):
            row = rows[t]
            row["played"] += 1
            row["gf"] += f
            row["ga"] += g
            res = "W" if f > g else "D" if f == g else "L"
            row[{"W": "won", "D": "drawn", "L": "lost"}[res]] += 1
            row["points"] += {"W": 3, "D": 1, "L": 0}[res]
            row["form"].append(res)
    out = sorted(rows.values(), key=lambda r: (-r["points"], -(r["gf"] - r["ga"]), -r["gf"], r["name"]))
    for i, r in enumerate(out, 1):
        r["position"], r["gd"], r["form"] = i, r["gf"] - r["ga"], r["form"][-5:]
    return out


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
        out.append({"minute": m, "score": dict(score), **outcome_probs(score[H], score[A], rh * left, ra * left)})
    while i < len(evs):  # stoppage time
        if evs[i]["type"] == "goal":
            score = dict(evs[i]["score"])
        i += 1
    final = outcome_probs(score[H], score[A], 0, 0)
    out.append({"minute": max(91, last_minute), "score": score, **final, "final": True})
    return out


def _elapsed(e: dict) -> int:
    """Match minute on a 0..90 axis (first-half stoppage counts as 45, second-half stoppage as 90)."""
    if e["period"] == 1:
        return min(e["minute"], 45)
    return min(e["minute"], 90)


def head_to_head(seed: int, n: int = 5) -> list[dict]:
    """Synthetic archive: n previous meetings simulated with the same engine and squads (clearly labelled)."""
    h, a = teams_for_seed(seed)
    out = []
    for i in range(n):
        s = seed * 100 + i
        home, away = (h, a) if i % 2 == 0 else (a, h)
        evs = list(MatchGenerator(s, *_fresh(home.id, away.id, seed)).events())
        out.append({"archive_seed": s, "home": home.id, "away": away.id, "score": evs[-1]["score"],
                    "label": f"Archive meeting {i + 1}"})
    return out


def _fresh(hid: str, aid: str, seed: int):
    h, a = teams_for_seed(seed)
    by = {h.id: h, a.id: a}
    import copy
    return copy.deepcopy(by[hid]), copy.deepcopy(by[aid])


def preview(seed: int) -> dict:
    evs = insights.events(seed)
    meta = evs[0]["meta"]
    H, A = meta["home"]["id"], meta["away"]["id"]
    day = (seed - 1000) // 10 if seed >= 1000 else LEAGUE_DAYS + 1
    tbl = {r["id"]: r for r in table(max(0, day - 1))} if H in _POOL and A in _POOL else {}
    ph, pa = priors(seed)
    h2h = head_to_head(seed)
    rec = {"home_wins": 0, "draws": 0, "away_wins": 0}
    for m in h2h:
        gh, ga = m["score"][H], m["score"][A]
        rec["home_wins" if gh > ga else "away_wins" if ga > gh else "draws"] += 1
    h, a = teams_for_seed(seed)
    sq = lambda t: round(sum(p.skill for p in t.players) / len(t.players), 3)
    return {"synthetic": True, "seed": seed, "matchday": day if seed >= 1000 else None,
            "home": {"id": H, "name": meta["home"]["name"], "rating": h.strength, "squad_skill": sq(h),
                     "table": tbl.get(H)},
            "away": {"id": A, "name": meta["away"]["name"], "rating": a.strength, "squad_skill": sq(a),
                     "table": tbl.get(A)},
            "expected_goals_prior": {H: ph, A: pa}, "pre_match_probability": outcome_probs(0, 0, ph * FULL / 90, pa * FULL / 90),
            "head_to_head": h2h, "head_to_head_record": rec,
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
