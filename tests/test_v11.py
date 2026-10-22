"""v11: fault injection + recovery, ball/pass metrics, semantic regression."""
import asyncio

from fastapi.testclient import TestClient

from insidethegame import insights
from insidethegame.room import CommentaryRoom
from insidethegame.room.semantic import check
from insidethegame.server import app

c = TestClient(app)


def _chaos(agent, severity):
    r = c.post("/api/chaos", json={"agent": agent, "severity": severity, "seed": 7, "minute": 40})
    assert r.status_code == 200
    return r.json()


def test_transient_fault_is_retried_and_batch_still_delivers():
    r = _chaos("explain", "transient")
    t = {x["agent"]: x for x in r["trace"]}
    assert t["explain"]["recovery"] == "retry" and t["explain"]["attempts"] == 2
    assert "error" not in t["explain"] and r["cards"]
    assert t["personalise"].get("out", {}).get("cards", 0) >= 1


def test_hard_fault_degrades_to_rules_fallback():
    r = _chaos("personalise", "hard")
    t = {x["agent"]: x for x in r["trace"]}
    assert t["personalise"]["recovery"] == "fallback:rules" and t["personalise"]["attempts"] == 3
    assert r["cards"]


def test_unknown_agent_rejected():
    assert "error" in c.post("/api/chaos", json={"agent": "nope"}).json()


def test_fault_is_one_shot():
    async def go():
        room = CommentaryRoom(7, online=False)
        evs = list(insights.events(7))[:120]
        from insidethegame.room import ViewerProfile
        room.inject_fault("render", "transient")
        b1 = await room.process_batch(evs[:60], ViewerProfile())
        b2 = await room.process_batch(evs[60:], ViewerProfile())
        return b1, b2
    b1, b2 = asyncio.run(go())
    assert any(t.get("recovery") == "retry" for t in b1.trace)
    assert not any(t.get("recovery") for t in b2.trace)


def test_ball_metrics_in_report():
    b = c.get("/api/report?seed=7").json()["ball"]
    for tm in b["teams"].values():
        assert 0 < tm["avg_pass_difficulty"] < 1
        assert 20 < tm["avg_pass_speed_kmh"] < 140
        assert tm["avg_shot_speed_kmh"] > 30
    assert b["fastest_shot"]["value"] >= max(t["avg_shot_speed_kmh"] for t in b["teams"].values())


def test_health_reports_replay_and_warm_state():
    h = c.get("/health").json()
    assert h["status"] == "ok" and h["replay_matches"] >= 5 and "warm" in h


def test_semantic_check_survives_first_person_text():
    # regression: a stray fan rule inside check() raised NameError on words like "our"
    out = check("Our view: Harbour keep control in the 20th minute.", {"minute": 20, "moment": "insight"})
    assert isinstance(out, list)
