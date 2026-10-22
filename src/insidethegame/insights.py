"""Match insights computed purely from the synthetic event stream (no LLM): team & player stats, momentum
(xT per 5-minute bucket), key moments / highlight reel, and an exportable full-time report.
Grounded LLM features (recap, ask-the-analyst) live in `analyst.py` and only ever see these facts."""
from __future__ import annotations
from collections import defaultdict
from functools import lru_cache

from . import xt
from .generator import MatchGenerator


@lru_cache(maxsize=32)
def events(seed: int) -> tuple[dict, ...]:
    return tuple(MatchGenerator(seed).events())


def _upto(seed: int, minute: int) -> list[dict]:
    evs = events(seed)
    end = minute >= 200
    return [e for e in evs if e["type"] == "match_start" or (e["minute"] <= minute and (end or e["type"] != "match_end"))
            and not (e["period"] == 2 and minute < 46 and e["type"] != "match_start")]


def team_stats(evs: list[dict], meta: dict) -> dict:
    ids = [meta["home"]["id"], meta["away"]["id"]]
    t = {i: defaultdict(float) for i in ids}
    for e in evs:
        tm = e.get("team")
        if tm not in t:
            continue
        s = t[tm]
        if e["type"] == "pass":
            s["passes"] += 1
            s["completed"] += e["success"]
            s["xt"] += xt.added(e)
            s["progressive"] += 1 if e["success"] and e["end_x"] - e["x"] >= 10 else 0
        elif e["type"] == "shot":
            s["shots"] += 1
            s["on_target"] += e["outcome"] in ("goal", "saved")
            s["xg"] += e["xg"]
        elif e["type"] == "goal":
            s["goals"] += 1
        elif e["type"] == "foul":
            s["fouls"] += 1
        elif e["type"] == "card":
            s["yellow" if e["card"] == "yellow" else "red"] += 1
        elif e["type"] == "pressure":
            s["pressures"] += 1
        elif e["type"] == "turnover":
            s["recoveries"] += 1
    tot_p = sum(t[i]["passes"] for i in ids) or 1
    out = {}
    for i in ids:
        s = t[i]
        out[i] = {"goals": int(s["goals"]), "shots": int(s["shots"]), "on_target": int(s["on_target"]),
                  "xg": round(s["xg"], 2), "xt": round(s["xt"], 2), "passes": int(s["passes"]),
                  "pass_completion_pct": round(100 * s["completed"] / max(s["passes"], 1), 1),
                  "pass_share_pct": round(100 * s["passes"] / tot_p, 1), "progressive_passes": int(s["progressive"]),
                  "pressures": int(s["pressures"]), "recoveries": int(s["recoveries"]), "fouls": int(s["fouls"]),
                  "yellow_cards": int(s["yellow"]), "red_cards": int(s["red"])}
    return out


def player_stats(evs: list[dict], meta: dict) -> list[dict]:
    team_of = {p["id"]: t["id"] for t in (meta["home"], meta["away"]) for p in t["players"]}
    agg: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    for e in evs:
        pid = e.get("player_id")
        if not pid or e["type"] not in ("pass", "shot", "goal", "foul", "card"):
            continue
        a = agg[pid]
        a["name"], a["team"] = e["player"], e["team"]
        if e["type"] == "pass":
            a["passes"] += 1
            a["completed"] += e["success"]
            a["xt"] += xt.added(e)
            a["q"] += e["quality"]
        elif e["type"] == "shot":
            a["shots"] += 1
            a["xg"] += e["xg"]
        elif e["type"] == "goal":
            a["goals"] += 1
        elif e["type"] == "foul":
            a["fouls"] += 1
        elif e["type"] == "card":
            a["cards"] += 1
    rows = []
    for pid, a in agg.items():
        rows.append({"player_id": pid, "name": a["name"], "team": a["team"] or team_of.get(pid),
                     "goals": int(a["goals"]), "shots": int(a["shots"]), "xg": round(a["xg"], 2),
                     "xt": round(a["xt"], 3), "passes": int(a["passes"]),
                     "pass_completion_pct": round(100 * a["completed"] / a["passes"], 1) if a["passes"] else 0.0,
                     "pass_quality": round(a["q"] / a["passes"], 1) if a["passes"] else 0.0,
                     "fouls": int(a["fouls"]), "cards": int(a["cards"])})
    # simple, transparent impact rating: goals + xG + xT (no hidden weights)
    for r in rows:
        r["impact"] = round(r["goals"] + r["xg"] + r["xt"], 2)
    return sorted(rows, key=lambda r: -r["impact"])


def momentum(evs: list[dict], meta: dict, bucket: int = 5) -> list[dict]:
    """xT added + xG per team per `bucket` minutes (by elapsed time, so stoppage is not merged)."""
    ids = [meta["home"]["id"], meta["away"]["id"]]
    b: dict[int, dict] = {}
    for e in evs:
        if e["type"] not in ("pass", "shot") or e.get("team") not in ids:
            continue
        k = int(e["t"] // (bucket * 60))
        row = b.setdefault(k, {"from_minute": k * bucket, ids[0]: 0.0, ids[1]: 0.0})
        row[e["team"]] += xt.added(e) if e["type"] == "pass" else e["xg"]
    return [{**v, ids[0]: round(v[ids[0]], 3), ids[1]: round(v[ids[1]], 3)} for _, v in sorted(b.items())]


def key_moments(evs: list[dict], meta: dict, limit: int = 25) -> list[dict]:
    names = {meta["home"]["id"]: meta["home"]["name"], meta["away"]["id"]: meta["away"]["name"]}
    out = []
    for e in evs:
        ty = e["type"]
        if ty == "goal":
            out.append({"minute": e["minute"], "kind": "goal", "importance": 5, "team": e["team"],
                        "player": e["player"], "xg": e["xg"], "score": e["score"], "event_id": e["id"],
                        "label": f"GOAL — {e['player']} ({names[e['team']]}), xG {e['xg']}"})
        elif ty == "shot" and e["outcome"] != "goal" and e["xg"] >= 0.2:
            out.append({"minute": e["minute"], "kind": "big_chance", "importance": 4, "team": e["team"],
                        "player": e["player"], "xg": e["xg"], "event_id": e["id"], "x": e["x"], "y": e["y"],
                        "label": f"Big chance — {e['player']} ({e['outcome'].replace('_', ' ')}), xG {e['xg']}"})
        elif ty == "card":
            out.append({"minute": e["minute"], "kind": f"{e['card']}_card", "importance": 4 if e["card"] != "yellow" else 2,
                        "team": e["team"], "player": e["player"], "event_id": e["id"],
                        "label": f"{e['card'].replace('_', ' ').title()} card — {e['player']}"})
        elif ty == "pass" and e["success"] and xt.added(e) >= 0.06:
            out.append({"minute": e["minute"], "kind": "threat_pass", "importance": 3, "team": e["team"],
                        "player": e["player"], "xt": round(xt.added(e), 3), "event_id": e["id"],
                        "x": e["x"], "y": e["y"], "end_x": e["end_x"], "end_y": e["end_y"],
                        "label": f"Line-breaking pass — {e['player']} to {e['receiver']}, +{round(xt.added(e), 3)} xT"})
    out.sort(key=lambda m: (-m["importance"], m["event_id"]))
    return sorted(out[:limit], key=lambda m: m["event_id"])


def ball_metrics(evs: list[dict], meta: dict) -> dict:
    """Challenge metrics from synthetic coordinates and timestamps: pass difficulty (distance, pressure,
    forward progress), ball speed of passes (length / flight time) and shot speed, per team, plus records."""
    def rec(e, key):
        return {"player": e.get("player"), "team": e.get("team"), "minute": e["minute"], "value": e.get(key),
                "success": e.get("success"), "length_m": e.get("length_m"), "distance_m": e.get("distance_m")}
    out = {}
    passes_all = [e for e in evs if e["type"] == "pass" and e.get("speed_kmh") is not None]
    shots_all = [e for e in evs if e["type"] in ("shot", "goal") and e.get("speed_kmh") is not None]
    for side in ("home", "away"):
        tid = meta[side]["id"]
        ps = [e for e in passes_all if e["team"] == tid]
        sh = [e for e in shots_all if e["team"] == tid]
        done = [e for e in ps if e.get("success")]
        hard = [e for e in ps if e.get("difficulty", 0) >= 0.6]
        out[tid] = {
            "avg_pass_difficulty": round(sum(e["difficulty"] for e in ps) / len(ps), 2) if ps else 0,
            "hard_passes": len(hard), "hard_pass_completion_pct": round(100 * sum(1 for e in hard if e.get("success")) / len(hard)) if hard else 0,
            "avg_pass_speed_kmh": round(sum(e["speed_kmh"] for e in ps) / len(ps), 1) if ps else 0,
            "avg_shot_speed_kmh": round(sum(e["speed_kmh"] for e in sh) / len(sh), 1) if sh else 0,
            "ball_travel_km": round(sum(e.get("length_m", 0) for e in ps) / 1000, 2),
            "hardest_completed_pass": rec(max(done, key=lambda e: e["difficulty"]), "difficulty") if done else None,
        }
    return {"teams": out,
            "fastest_shot": rec(max(shots_all, key=lambda e: e["speed_kmh"]), "speed_kmh") if shots_all else None,
            "fastest_pass": rec(max(passes_all, key=lambda e: e["speed_kmh"]), "speed_kmh") if passes_all else None,
            "method": "difficulty = f(distance, pressure, forward metres) in [0,1]; speed = distance / flight time (km/h)"}


def report(seed: int, up_to_minute: int = 200) -> dict:
    evs = _upto(seed, up_to_minute)
    meta = evs[0]["meta"]
    score = {meta["home"]["id"]: 0, meta["away"]["id"]: 0}
    for e in evs:
        if e["type"] == "goal":
            score = dict(e["score"])
    last = max((e["minute"] for e in evs[1:]), default=0)
    finished = any(e["type"] == "match_end" for e in evs)
    return {"synthetic": True, "seed": seed, "finished": finished, "minute": last,
            "home": {k: meta["home"][k] for k in ("id", "name", "short", "color")},
            "away": {k: meta["away"][k] for k in ("id", "name", "short", "color")},
            "score": score, "teams": team_stats(evs, meta), "players": player_stats(evs, meta),
            "momentum": momentum(evs, meta), "key_moments": key_moments(evs, meta),
            "ball": ball_metrics(evs, meta)}


def report_markdown(r: dict, recap: str | None = None) -> str:
    h, a = r["home"], r["away"]
    th, ta = r["teams"][h["id"]], r["teams"][a["id"]]
    status = "Full time" if r["finished"] else f"Live, minute {r['minute']}"
    lines = [f"# {h['name']} {r['score'][h['id']]} – {r['score'][a['id']]} {a['name']}",
             f"_{status} · synthetic match (seed {r['seed']}) · generated by Inside the Game_", ""]
    if recap:
        lines += ["## Recap", recap, ""]
    lines += ["## Team stats", f"| Metric | {h['short']} | {a['short']} |", "|---|---:|---:|"]
    for k in th:
        lines.append(f"| {k.replace('_', ' ')} | {th[k]} | {ta[k]} |")
    lines += ["", "## Key moments"] + [f"- **{m['minute']}'** {m['label']}" for m in r["key_moments"]]
    lines += ["", "## Top performers (impact = goals + xG + xT)", "| Player | Team | Goals | xG | xT | Pass % |",
              "|---|---|---:|---:|---:|---:|"]
    names = {h["id"]: h["short"], a["id"]: a["short"]}
    for p in r["players"][:8]:
        lines.append(f"| {p['name']} | {names.get(p['team'], p['team'])} | {p['goals']} | {p['xg']} | {p['xt']} | "
                     f"{p['pass_completion_pct']} |")
    return "\n".join(lines) + "\n"
