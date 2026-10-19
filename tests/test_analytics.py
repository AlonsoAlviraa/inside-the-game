import asyncio
import pytest
from insidethegame import spadl, xt
from insidethegame.generator import MatchGenerator


def acts(seed=4):
    return spadl.to_spadl(list(MatchGenerator(seed).events()), game_id=seed)


def test_spadl_schema_and_vocab():
    rows = acts()
    assert rows and all(set(spadl.COLUMNS) == set(r) for r in rows)
    for r in rows:
        assert spadl.ACTION_TYPES[r["type_id"]] == r["type_name"]
        assert spadl.RESULTS[r["result_id"]] == r["result_name"]
        assert 0 <= r["start_x"] <= 105 and 0 <= r["start_y"] <= 68
    assert [r["action_id"] for r in rows] == list(range(len(rows)))
    names = {r["type_name"] for r in rows}
    assert {"pass", "shot", "foul"} <= names


def test_spadl_goals_match_score():
    evs = list(MatchGenerator(4).events())
    goals = sum(r["type_name"] == "shot" and r["result_name"] == "success" for r in spadl.to_spadl(evs))
    assert goals == sum(evs[-1]["score"].values())


def test_xt_grid_increases_towards_goal():
    g = xt.default_grid()
    assert len(g) == xt.L * xt.W
    centre = xt.W // 2
    assert xt.value(100, 34) > xt.value(52, 34) > xt.value(5, 34)
    assert max(g) < 0.5 and min(g) >= 0


def test_mcp_tools():
    pytest.importorskip("mcp")
    from insidethegame import mcp_server as m
    s = m.match_summary(4)
    assert s["synthetic"] and set(s["teams"]) == set(s["score"])
    assert m.spadl_actions(4, 10, 20, limit=50)
    assert len(m.top_players(4, "xg", 3)) == 3
    assert 0 <= m.control_index(4, 30)["chaos"] <= 1
    tools = asyncio.run(m.mcp.list_tools())
    assert {"match_summary", "spadl_actions", "top_players", "control_index", "xt_grid"} <= {t.name for t in tools}
