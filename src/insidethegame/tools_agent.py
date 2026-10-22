"""Ask-with-tools: a planner turns a viewer question into tool calls over the synthetic event stream, the tools
run deterministically, and the answer plus *pitch highlights* and a visible tool-call trace go back to the UI.

Planner: with Azure enabled, gpt-4.1-mini picks the tools (one small JSON call, validated against the tool
schema; invalid plans are discarded). Offline, or if the plan is invalid, a rules planner does the same job.
Tools only read events up to `minute`, so there are no spoilers. Every number in the answer comes from a tool."""
from __future__ import annotations
import json
import re
import time
import unicodedata

from . import insights
from .room.llm import parse_json

TOOLS = {
    "find_shots": "Shots (and goals) by a player and/or team, optionally in one half. args: player?, team?, half?",
    "find_passes": "Passes by a player and/or team; filter hard (difficulty>=0.6) or forward (10 m+). args: player?, team?, half?, kind? (hard|forward|all)",
    "compare_teams": "Team stats side by side for the whole match or one half. args: half? (1|2)",
    "player_stats": "One player's match line. args: player",
    "find_events": "Cards, substitutions, fouls or turnovers. args: type (card|substitution|foul|turnover), team?, player?, half?",
    "key_moments": "The most important moments so far. args: none",
}
PLANNER = ("You plan tool calls for a football analytics assistant about a SYNTHETIC match. Reply with JSON only: "
           '{"calls":[{"tool":"<name>","args":{...}}]} using at most 2 calls. Tools: ' + json.dumps(TOOLS) +
           ". Use player and team names exactly as in the roster. half is 1 or 2. If nothing fits use key_moments.")


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


class Ctx:
    def __init__(self, seed: int, minute: int):
        self.seed, self.minute = seed, minute
        self.evs = insights._upto(seed, minute)
        self.meta = self.evs[0]["meta"]
        self.teams = {t["id"]: t for t in (self.meta["home"], self.meta["away"])}
        self.players = {p["id"]: (p, tid) for tid, t in self.teams.items() for p in t["players"]}

    def team_id(self, name: str | None) -> str | None:
        if not name:
            return None
        n = _norm(str(name))
        for tid, t in self.teams.items():
            if n in (_norm(t["name"]), _norm(t["short"]), tid) or _norm(t["name"]) in n or any(w in n.split() for w in _norm(t["name"]).split() if len(w) > 4):
                return tid
        return None

    def player_id(self, name: str | None) -> str | None:
        if not name:
            return None
        n = _norm(str(name))
        best = None
        for pid, (p, _) in self.players.items():
            full = _norm(p["name"])
            if full == n or full in n:
                return pid
            if best is None and any(len(w) > 3 and re.search(rf"\b{re.escape(w)}\b", n) for w in full.split()[1:]):
                best = pid
        return best

    def half(self, h) -> int | None:
        try:
            h = int(h)
        except (TypeError, ValueError):
            return None
        return h if h in (1, 2) else None

    def filt(self, types, team=None, player=None, half=None):
        return [e for e in self.evs if e["type"] in types and (not team or e.get("team") == team)
                and (not player or e.get("player_id") == player) and (not half or e["period"] == half)]


def _label(ctx: Ctx, args: dict) -> str:
    bits = []
    if args.get("player_id"):
        bits.append(ctx.players[args["player_id"]][0]["name"])
    if args.get("team_id"):
        bits.append(ctx.teams[args["team_id"]]["name"])
    if args.get("half"):
        bits.append(f"{'1st' if args['half'] == 1 else '2nd'} half")
    return ", ".join(bits) or "both teams"


def run_tool(ctx: Ctx, tool: str, args: dict) -> dict:
    a = {"team_id": ctx.team_id(args.get("team")), "player_id": ctx.player_id(args.get("player")), "half": ctx.half(args.get("half"))}
    if a["player_id"] and not a["team_id"]:
        a["team_id"] = ctx.players[a["player_id"]][1]
    hl: list[dict] = []
    if tool == "find_shots":
        sh = ctx.filt(("shot",), a["team_id"], a["player_id"], a["half"])
        goals = sum(e["outcome"] == "goal" for e in sh)
        on = sum(e["outcome"] in ("goal", "saved") for e in sh)
        xg = round(sum(e["xg"] for e in sh), 2)
        hl = [{"kind": "shot", "team": e["team"], "x": e["x"], "y": e["y"], "minute": e["minute"], "goal": e["outcome"] == "goal",
               "xg": e["xg"], "label": f"{e['minute']}' {e['player'].split()[-1]} {e['outcome'].replace('_', ' ')}"} for e in sh]
        res = {"shots": len(sh), "on_target": on, "goals": goals, "xg": xg}
        text = (f"{_label(ctx, a)}: {len(sh)} shots, {on} on target, {goals} goal{'s' if goals != 1 else ''}, xG {xg}."
                if sh else f"No shots found for {_label(ctx, a)} so far.")
        if sh:
            b = max(sh, key=lambda e: e["xg"])
            text += f" Best chance: {b['player']} in minute {b['minute']} (xG {b['xg']})."
    elif tool == "find_passes":
        kind = args.get("kind") or "all"
        ps = ctx.filt(("pass",), a["team_id"], a["player_id"], a["half"])
        if kind == "hard":
            ps = [e for e in ps if e.get("difficulty", 0) >= 0.6]
        elif kind == "forward":
            ps = [e for e in ps if e["end_x"] - e["x"] >= 10]
        ok = sum(e["success"] for e in ps)
        pct = round(100 * ok / len(ps), 1) if ps else 0
        hl = [{"kind": "pass", "team": e["team"], "x": e["x"], "y": e["y"], "end_x": e["end_x"], "end_y": e["end_y"], "ok": e["success"],
               "minute": e["minute"]} for e in sorted(ps, key=lambda e: -e.get("difficulty", 0))[:40]]
        res = {"passes": len(ps), "completed": ok, "completion_pct": pct, "kind": kind}
        text = f"{_label(ctx, a)}: {len(ps)} {'' if kind == 'all' else kind + ' '}passes, {ok} completed ({pct}%)."
    elif tool == "compare_teams":
        evs = [e for e in ctx.evs if not a["half"] or e["period"] == a["half"] or e["type"] == "match_start"]
        st = insights.team_stats(evs, ctx.meta)
        h, w = ctx.meta["home"], ctx.meta["away"]
        keys = ("goals", "shots", "on_target", "xg", "xt", "passes", "pass_completion_pct", "pressures", "fouls")
        res = {"half": a["half"], h["name"]: {k: st[h["id"]][k] for k in keys}, w["name"]: {k: st[w["id"]][k] for k in keys}}
        sh, sw = st[h["id"]], st[w["id"]]
        when = f"In the {'1st' if a['half'] == 1 else '2nd'} half" if a["half"] else "Over the match so far"
        lead = h if sh["xg"] >= sw["xg"] else w
        text = (f"{when}: {h['short']} {sh['goals']} goals, {sh['shots']} shots, xG {sh['xg']}, passing {sh['pass_completion_pct']}%; "
                f"{w['short']} {sw['goals']} goals, {sw['shots']} shots, xG {sw['xg']}, passing {sw['pass_completion_pct']}%. "
                f"{lead['name']} created the better chances.")
        hl = [{"kind": "shot", "team": e["team"], "x": e["x"], "y": e["y"], "minute": e["minute"], "goal": e["outcome"] == "goal", "xg": e["xg"]}
              for e in evs if e["type"] == "shot"]
    elif tool == "player_stats":
        if not a["player_id"]:
            return {"tool": tool, "args": args, "result": {"error": "player not found"}, "text": "I could not find that player in this match.", "highlights": []}
        row = next((p for p in insights.player_stats(ctx.evs, ctx.meta) if p["player_id"] == a["player_id"]), None)
        name = ctx.players[a["player_id"]][0]["name"]
        res = row or {}
        text = (f"{name}: {row['goals']} goal{'s' if row['goals'] != 1 else ''}, {row['shots']} shot{'s' if row['shots'] != 1 else ''}, xG {row['xg']}, xT {row['xt']}, {row['passes']} passes at {row['pass_completion_pct']}%."
                if row else f"{name} has not been involved yet.")
        hl = [{"kind": "shot" if e["type"] == "shot" else "pass", "team": e["team"], "x": e["x"], "y": e["y"], "end_x": e.get("end_x"), "end_y": e.get("end_y"),
               "ok": e.get("success", True), "goal": e.get("outcome") == "goal", "xg": e.get("xg", 0), "minute": e["minute"]}
              for e in ctx.filt(("shot", "pass"), None, a["player_id"], a["half"])][-40:]
    elif tool == "find_events":
        typ = args.get("type") if args.get("type") in ("card", "substitution", "foul", "turnover") else "card"
        ev = ctx.filt((typ,), a["team_id"], a["player_id"] if typ != "substitution" else None, a["half"])
        res = {"type": typ, "count": len(ev)}
        def d(e):
            if typ == "card":
                return f"{e['minute']}' {e['player']} ({e['card']})"
            if typ == "substitution":
                return f"{e['minute']}' {e['player_on']} on for {e['player_off']}"
            return f"{e['minute']}' {e.get('player') or ctx.teams[e['team']]['short']}"
        text = f"{len(ev)} {typ}{'s' if len(ev) != 1 else ''} for {_label(ctx, a)}" + (": " + "; ".join(d(e) for e in ev[:8]) + "." if ev else ".")
        pos = {(f["t"], f.get("player_id")): f for f in ctx.evs if f["type"] == "foul"}
        hl = []
        for e in ev:
            src = e if e.get("x") is not None else pos.get((e["t"], e.get("player_id")))
            if src:
                hl.append({"kind": "mark", "team": e["team"], "x": src["x"], "y": src["y"], "minute": e["minute"], "label": d(e)})
    else:
        tool = "key_moments"
        km = [m for m in insights.key_moments(ctx.evs, ctx.meta) if m["importance"] >= 4]
        res = {"moments": len(km)}
        text = ("Key moments: " + "; ".join(f"{m['minute']}' {m['label']}" for m in km[:6]) + ".") if km else "No key moments yet."
        hl = [{"kind": "mark", "team": m["team"], "x": m["x"], "y": m["y"], "minute": m["minute"]} for m in km if m.get("x") is not None]
    resolved = {k: v for k, v in (("team", a["team_id"] and ctx.teams[a["team_id"]]["name"]),
                                  ("player", a["player_id"] and ctx.players[a["player_id"]][0]["name"]), ("half", a["half"])) if v}
    return {"tool": tool, "args": resolved | ({"kind": args["kind"]} if args.get("kind") else {}) | ({"type": args["type"]} if args.get("type") else {}),
            "result": res, "text": text, "highlights": hl}


def rules_plan(ctx: Ctx, q: str) -> list[dict]:
    n = _norm(q)
    pid = ctx.player_id(n)
    tid = ctx.team_id(n)
    half = 2 if re.search(r"2nd|second|segunda|seconde|after (the )?break", n) else 1 if re.search(r"1st|first|primera|premiere", n) else None
    base = {k: v for k, v in (("player", pid and ctx.players[pid][0]["name"]), ("team", tid and ctx.teams[tid]["name"]), ("half", half)) if v}
    if re.search(r"compar|versus|\bvs\b|both teams|comparar|compare", n) and not pid:
        return [{"tool": "compare_teams", "args": {"half": half} if half else {}}]
    if re.search(r"shot|shoot|tiro|disparo|\btir|chance|goal|gol|\bbut", n):
        return [{"tool": "find_shots", "args": base}]
    if re.search(r"pass|pase|passe", n):
        kind = "hard" if re.search(r"hard|difficult|dificil|difficile", n) else "forward" if re.search(r"forward|progress|vertical|adelante", n) else "all"
        return [{"tool": "find_passes", "args": base | {"kind": kind}}]
    for typ, pat in (("card", r"card|book|tarjeta|carton"), ("substitution", r"sub|change|cambio|remplac"), ("foul", r"foul|falta|faute"), ("turnover", r"turnover|lost the ball|perdida|recover")):
        if re.search(pat, n):
            return [{"tool": "find_events", "args": base | {"type": typ}}]
    if pid:
        return [{"tool": "player_stats", "args": base}]
    if half or tid:
        return [{"tool": "compare_teams", "args": {"half": half} if half else {}}]
    return [{"tool": "key_moments", "args": {}}]


def _valid(plan) -> list[dict] | None:
    if not isinstance(plan, dict) or not isinstance(plan.get("calls"), list):
        return None
    calls = [c for c in plan["calls"][:2] if isinstance(c, dict) and c.get("tool") in TOOLS and isinstance(c.get("args", {}), dict)]
    return calls or None


async def ask(seed: int, question: str, minute: int = 200) -> dict:
    from .analyst import _brain
    ctx = Ctx(seed, minute)
    t0 = time.perf_counter()
    trace = []
    calls, planner = None, "rules"
    brain = _brain("planner", PLANNER, 120)
    if brain.online:
        roster = {t["name"]: [p["name"] for p in t["players"]] for t in ctx.teams.values()}
        entry: dict = {}
        calls = _valid(parse_json(await brain.ask(f"ROSTER: {json.dumps(roster)}\nQUESTION: {question[:300]}", entry)))
        trace.append({"step": "plan", "by": "llm" if calls else "llm → invalid, rules", "tokens_in": entry.get("tokens_in"), "tokens_out": entry.get("tokens_out")})
        planner = "llm" if calls else "rules"
    if not calls:
        calls = rules_plan(ctx, question)
        if not trace:
            trace.append({"step": "plan", "by": "rules"})
    outs = []
    for c in calls:
        t1 = time.perf_counter()
        o = run_tool(ctx, c["tool"], c.get("args") or {})
        o["ms"] = round((time.perf_counter() - t1) * 1000, 1)
        outs.append(o)
        trace.append({"step": "tool", "tool": o["tool"], "args": o["args"], "result": o["result"], "ms": o["ms"], "highlights": len(o["highlights"])})
    return {"text": " ".join(o["text"] for o in outs), "planner": planner, "trace": trace,
            "highlights": [h for o in outs for h in o["highlights"]][:80], "minute": minute,
            "ms": round((time.perf_counter() - t0) * 1000, 1), "grounded": "every number comes from a tool result"}
