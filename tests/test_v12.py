"""v12: ask-with-tools agent, three-viewer perspectives, highlight reel."""
import asyncio

from fastapi.testclient import TestClient

from insidethegame import tools_agent
from insidethegame.server import app

c = TestClient(app)


def test_agent_shots_by_player_highlights_on_pitch():
    r = asyncio.run(tools_agent.ask(58, "show me all shots by Rafe Vance", 200))
    tools = [t for t in r["trace"] if t["step"] == "tool"]
    assert tools and tools[0]["tool"] == "find_shots"
    assert r["highlights"] and all(h["kind"] == "shot" for h in r["highlights"])
    assert "Rafe Vance" in r["text"] and r["grounded"]


def test_agent_compare_second_half_and_time_cutoff():
    r = asyncio.run(tools_agent.ask(58, "compare teams in 2nd half", 200))
    assert r["trace"][1]["tool"] == "compare_teams"
    early = asyncio.run(tools_agent.ask(58, "any shots?", 10))
    assert all(h["minute"] <= 10 for h in early["highlights"])


def test_agent_endpoint():
    r = c.post("/api/agent", json={"seed": 58, "question": "any cards?", "minute": 200})
    assert r.status_code == 200 and r.json()["trace"][0]["step"] == "plan"


def test_perspectives_three_distinct_modes():
    j = c.get("/api/perspectives", params={"seed": 58, "minute": 200, "lang": "en"}).json()
    texts = {m: j["modes"][m]["text"] for m in ("fan", "neutral", "analyst")}
    assert j["event"]["type"] == "goal" and len(set(texts.values())) == 3


def test_reel_has_goals_with_buildup():
    j = c.get("/api/reel", params={"seed": 58, "mode": "fan", "lang": "en"}).json()
    goals = [k for k in j["clips"] if k["moment"]["kind"] == "goal"]
    assert len(goals) == sum(j["score"].values())
    assert all(k["events"] and k["caption"] for k in j["clips"])
