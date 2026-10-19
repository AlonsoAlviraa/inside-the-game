"""MCP server exposing synthetic match data and metrics to any MCP client (Foundry agents, VS Code, ...).

Run:  python -m insidethegame.mcp_server            (stdio)
      python -m insidethegame.mcp_server --http      (streamable HTTP)
Built on the official MCP Python SDK v2 (MIT): https://github.com/modelcontextprotocol/python-sdk
"""
from __future__ import annotations
import sys
from collections import defaultdict
from functools import lru_cache

from mcp.server.mcpserver import MCPServer

from . import xt
from .generator import MatchGenerator
from .metrics import ControlChaosIndex
from .spadl import to_spadl

mcp = MCPServer("inside-the-game", instructions=(
    "Synthetic football match data (fictional teams/players). Tools return SPADL actions, xG, "
    "expected threat (xT) and the control-vs-chaos index for a seeded match."))


@lru_cache(maxsize=32)
def _events(seed: int) -> tuple[dict, ...]:
    return tuple(MatchGenerator(seed).events())


@mcp.tool()
def match_summary(seed: int = 7) -> dict:
    """Final score, teams and per-team totals (passes, completion, shots, xG, xT) for a synthetic match."""
    evs = _events(seed)
    meta = evs[0]["meta"]
    t = {s["id"]: defaultdict(float) for s in (meta["home"], meta["away"])}
    for e in evs:
        if e["type"] == "pass":
            t[e["team"]]["passes"] += 1
            t[e["team"]]["completed"] += e["success"]
            t[e["team"]]["xt"] += xt.added(e)
        elif e["type"] == "shot":
            t[e["team"]]["shots"] += 1
            t[e["team"]]["xg"] += e["xg"]
    out = {k: {"passes": int(v["passes"]), "completion": round(v["completed"] / max(v["passes"], 1), 3),
               "shots": int(v["shots"]), "xg": round(v["xg"], 2), "xt": round(v["xt"], 2)} for k, v in t.items()}
    return {"synthetic": True, "seed": seed, "home": meta["home"]["name"], "away": meta["away"]["name"],
            "score": evs[-1]["score"], "teams": out}


@mcp.tool()
def spadl_actions(seed: int = 7, from_minute: int = 0, to_minute: int = 120, limit: int = 200) -> list[dict]:
    """SPADL-compatible actions (socceraction schema) within a minute range."""
    mins = {e["id"]: e["minute"] for e in _events(seed)}
    rows = [r for r in to_spadl(list(_events(seed)), game_id=seed)
            if from_minute <= mins[r["original_event_id"]] <= to_minute]
    return rows[:limit]


@mcp.tool()
def top_players(seed: int = 7, metric: str = "xt", n: int = 5) -> list[dict]:
    """Top players by 'xt' (expected threat added), 'xg', or 'pass_quality' (avg 0-100)."""
    agg: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    for e in _events(seed):
        if e["type"] == "pass":
            a = agg[e["player_id"]]
            a["name"], a["team"] = e["player"], e["team"]
            a["xt"] += xt.added(e)
            a["q"] += e["quality"]
            a["passes"] += 1
        elif e["type"] == "shot":
            a = agg[e["player_id"]]
            a["name"], a["team"] = e["player"], e["team"]
            a["xg"] += e["xg"]
    rows = [{"player_id": k, "name": v["name"], "team": v["team"], "xt": round(v["xt"], 3),
             "xg": round(v["xg"], 3), "pass_quality": round(v["q"] / v["passes"], 1) if v["passes"] else 0.0}
            for k, v in agg.items()]
    key = metric if metric in ("xt", "xg", "pass_quality") else "xt"
    return sorted(rows, key=lambda r: -r[key])[:n]


@mcp.tool()
def control_index(seed: int = 7, minute: int = 45) -> dict:
    """Control-vs-chaos snapshot (rolling 5-min window) at a given match minute."""
    evs = _events(seed)
    meta = evs[0]["meta"]
    idx = ControlChaosIndex(meta["home"]["id"], meta["away"]["id"])
    snap = idx.snapshot()
    for e in evs[1:]:
        if e["minute"] > minute:
            break
        snap = idx.update(e)
    return {"minute": minute, **snap}


@mcp.tool()
def xt_grid() -> dict:
    """The 16x12 expected-threat grid fitted on 40 synthetic matches (row-major, attacking left to right)."""
    g = xt.default_grid()
    return {"columns": xt.L, "rows": xt.W, "pitch_m": [105, 68],
            "grid": [list(g[r * xt.L:(r + 1) * xt.L]) for r in range(xt.W)]}


def main() -> None:
    if "--http" in sys.argv:
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
