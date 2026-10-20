"""Full fictional season (16 clubs x 30 matchdays = 240 matches) summarised from the synthetic engine.

Summaries are deterministic; `data/season.json` is a build-time cache (scripts/build_season.py) so the app starts fast
on a small container. If the cache is missing or stale the season is recomputed. All numbers come from match events.
"""
from __future__ import annotations
import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from . import xt
from .generator import MatchGenerator
from .insights import team_stats
from .teams import FIXTURES, LEAGUE_DAYS, club_list

CACHE = Path(__file__).with_name("data") / "season.json"
VERSION = 1


def day_of(seed: int) -> int:
    return (seed - 1000) // 10


def summarise(seed: int) -> dict:
    evs = list(MatchGenerator(seed).events())
    meta = evs[0]["meta"]
    H, A = meta["home"]["id"], meta["away"]["id"]
    ts = team_stats(evs, meta)
    players: dict[str, dict] = {}
    for t in (meta["home"], meta["away"]):
        for p in t["players"][:11]:
            players[p["id"]] = {"name": p["name"], "team": t["id"], "goals": 0, "assists": 0, "shots": 0, "xg": 0.0,
                                "xt": 0.0, "passes": 0, "apps": 1}
    goals, last_pass = [], {}
    for e in evs:
        ty = e["type"]
        if ty == "substitution":
            on = next((p for t in (meta["home"], meta["away"]) for p in t["players"] if p["name"] == e["player_on"]), None)
            if on and on["id"] not in players:
                players[on["id"]] = {"name": on["name"], "team": e["team"], "goals": 0, "assists": 0, "shots": 0,
                                     "xg": 0.0, "xt": 0.0, "passes": 0, "apps": 1}
        elif ty == "pass" and e["player_id"] in players:
            r = players[e["player_id"]]
            r["passes"] += 1
            r["xt"] += xt.added(e)
            last_pass = {"team": e["team"], "receiver_id": e.get("receiver_id"), "player_id": e["player_id"]} if e["success"] else {}
        elif ty in ("turnover", "possession_start"):
            last_pass = {}
        elif ty == "shot" and e["player_id"] in players:
            players[e["player_id"]]["shots"] += 1
            players[e["player_id"]]["xg"] += e["xg"]
        elif ty == "goal":
            ast = last_pass.get("player_id") if last_pass.get("receiver_id") == e["player_id"] and last_pass.get("team") == e["team"] else None
            if e["player_id"] in players:
                players[e["player_id"]]["goals"] += 1
            if ast and ast in players:
                players[ast]["assists"] += 1
            goals.append({"minute": e["minute"], "team": e["team"], "player_id": e["player_id"], "player": e["player"],
                          "assist_id": ast, "assist": players[ast]["name"] if ast in players else None})
    for r in players.values():
        r["xg"], r["xt"] = round(r["xg"], 3), round(r["xt"], 3)
    keep = ("goals", "shots", "on_target", "xg", "xt", "passes", "pass_completion_pct", "pass_share_pct", "fouls",
            "yellow_cards", "red_cards")
    return {"seed": seed, "day": day_of(seed), "home": H, "away": A, "score": evs[-1]["score"],
            "teams": {k: {m: v[m] for m in keep} for k, v in ts.items()}, "goals": goals, "players": players}


def _seeds() -> list[int]:
    return sorted(s for s in FIXTURES if s >= 1000)


@lru_cache(maxsize=1)
def season() -> dict:
    seeds = _seeds()
    if CACHE.exists():
        data = json.loads(CACHE.read_text())
        if data.get("version") == VERSION and [m["seed"] for m in data["matches"]] == seeds:
            return data
    return build()


def build() -> dict:
    return {"version": VERSION, "matches": [summarise(s) for s in _seeds()]}


def matches(up_to_day: int = LEAGUE_DAYS, team: str | None = None) -> list[dict]:
    return [m for m in season()["matches"] if m["day"] <= up_to_day and (team is None or team in (m["home"], m["away"]))]


def table(up_to_day: int = LEAGUE_DAYS) -> list[dict]:
    rows = {c["id"]: {"id": c["id"], "name": c["name"], "short": c["short"], "color": c["color"], "crest": c["crest"],
                      "played": 0, "won": 0, "drawn": 0, "lost": 0, "gf": 0, "ga": 0, "points": 0, "form": []}
            for c in club_list()}
    for m in matches(up_to_day):
        for t, o in ((m["home"], m["away"]), (m["away"], m["home"])):
            f, g = m["score"][t], m["score"][o]
            r = rows[t]
            r["played"] += 1
            r["gf"] += f
            r["ga"] += g
            res = "W" if f > g else "D" if f == g else "L"
            r[{"W": "won", "D": "drawn", "L": "lost"}[res]] += 1
            r["points"] += {"W": 3, "D": 1, "L": 0}[res]
            r["form"].append(res)
    out = sorted(rows.values(), key=lambda r: (-r["points"], -(r["gf"] - r["ga"]), -r["gf"], r["name"]))
    for i, r in enumerate(out, 1):
        r["position"], r["gd"], r["form"] = i, r["gf"] - r["ga"], r["form"][-5:]
    return out


def table_with_moves(up_to_day: int = LEAGUE_DAYS) -> list[dict]:
    now = table(up_to_day)
    before = {r["id"]: r["position"] for r in table(up_to_day - 1)} if up_to_day > 1 else {}
    for r in now:
        r["move"] = (before[r["id"]] - r["position"]) if before else 0
    return now


def positions_over_time(up_to_day: int = LEAGUE_DAYS) -> dict:
    out = defaultdict(list)
    for d in range(1, up_to_day + 1):
        for r in table(d):
            out[r["id"]].append(r["position"])
    return dict(out)


def team_season(team: str, up_to_day: int = LEAGUE_DAYS) -> dict:
    """Per-match averages and totals for one club from league matches up to (and including) `up_to_day`."""
    ms = matches(up_to_day, team)
    n = len(ms) or 1
    agg = defaultdict(float)
    scorers: dict[str, dict] = {}
    for m in ms:
        o = m["away"] if m["home"] == team else m["home"]
        me, op = m["teams"][team], m["teams"][o]
        agg["gf"] += m["score"][team]
        agg["ga"] += m["score"][o]
        agg["xg_for"] += me["xg"]
        agg["xg_against"] += op["xg"]
        agg["shots"] += me["shots"]
        agg["shots_against"] += op["shots"]
        agg["on_target"] += me["on_target"]
        agg["pass_share"] += me["pass_share_pct"]
        agg["pass_completion"] += me["pass_completion_pct"]
        agg["clean_sheets"] += m["score"][o] == 0
        agg["cards"] += me["yellow_cards"] + me["red_cards"]
        for pid, p in m["players"].items():
            if p["team"] == team:
                s = scorers.setdefault(pid, {"player_id": pid, "name": p["name"], "apps": 0, "goals": 0, "assists": 0,
                                             "shots": 0, "xg": 0.0, "xt": 0.0, "passes": 0})
                for k in ("apps", "goals", "assists", "shots", "passes"):
                    s[k] += p[k]
                s["xg"] += p["xg"]
                s["xt"] += p["xt"]
    squad = sorted(({**s, "xg": round(s["xg"], 2), "xt": round(s["xt"], 2)} for s in scorers.values()),
                   key=lambda s: (-s["goals"], -s["assists"], -s["xg"]))
    per = lambda k: round(agg[k] / n, 2) if ms else 0.0
    return {"team": team, "played": len(ms),
            "totals": {"goals_for": int(agg["gf"]), "goals_against": int(agg["ga"]), "xg_for": round(agg["xg_for"], 2),
                       "xg_against": round(agg["xg_against"], 2), "shots": int(agg["shots"]),
                       "clean_sheets": int(agg["clean_sheets"]), "cards": int(agg["cards"])},
            "per_match": {"goals_for": per("gf"), "goals_against": per("ga"), "xg_for": per("xg_for"),
                          "xg_against": per("xg_against"), "shots": per("shots"), "shots_against": per("shots_against"),
                          "shots_on_target": per("on_target"), "possession_pass_share_pct": per("pass_share"),
                          "pass_completion_pct": per("pass_completion")},
            "top_scorer": squad[0] if squad and squad[0]["goals"] else None, "squad": squad}


def leaders(up_to_day: int = LEAGUE_DAYS, n: int = 10) -> dict:
    agg: dict[str, dict] = {}
    for m in matches(up_to_day):
        for pid, p in m["players"].items():
            s = agg.setdefault(pid, {"player_id": pid, "name": p["name"], "team": p["team"], "apps": 0, "goals": 0,
                                     "assists": 0, "xg": 0.0, "xt": 0.0})
            s["apps"] += p["apps"]
            s["goals"] += p["goals"]
            s["assists"] += p["assists"]
            s["xg"] += p["xg"]
            s["xt"] += p["xt"]
    rows = [{**s, "xg": round(s["xg"], 2), "xt": round(s["xt"], 2)} for s in agg.values()]
    top = lambda k: sorted(rows, key=lambda r: (-r[k], r["name"]))[:n]
    return {"goals": top("goals"), "assists": top("assists"), "xg": top("xg"), "xt": top("xt")}


def meetings(seed: int) -> list[dict]:
    """Earlier league meetings of the two clubs in this season (before this fixture's matchday)."""
    h, a = FIXTURES[seed][:2]
    d = day_of(seed) if seed >= 1000 else LEAGUE_DAYS + 1
    return [{"seed": m["seed"], "matchday": m["day"], "home": m["home"], "away": m["away"], "score": m["score"]}
            for m in matches(d - 1) if {m["home"], m["away"]} == {h, a}]
