import asyncio
from fastapi.testclient import TestClient
from insidethegame import analyst, insights
from insidethegame.generator import MatchGenerator
from insidethegame.server import app
from insidethegame.teams import FIXTURES, fixture_list

c = TestClient(app)


def test_fixtures_are_distinct_fictional_matches():
    names = set()
    for s in FIXTURES:
        meta = next(MatchGenerator(s).events())["meta"]
        names.add((meta["home"]["name"], meta["away"]["name"]))
    assert len(names) == len(FIXTURES) and len(fixture_list()) == len(FIXTURES)


def test_report_matches_event_stream():
    evs = list(MatchGenerator(11).events())
    r = insights.report(11)
    assert r["finished"] and r["score"] == evs[-1]["score"]
    for tid, t in r["teams"].items():
        assert t["goals"] == r["score"][tid]
        assert t["shots"] == sum(1 for e in evs if e["type"] == "shot" and e["team"] == tid)
    assert sum(p["goals"] for p in r["players"]) == sum(r["score"].values())
    assert len([m for m in r["key_moments"] if m["kind"] == "goal"]) == sum(r["score"].values())
    assert r["momentum"] and all(set(r["teams"]) <= set(m) for m in r["momentum"])


def test_report_is_live_safe():
    r = insights.report(7, 30)
    assert not r["finished"] and r["minute"] <= 30
    assert all(m["minute"] <= 30 for m in r["key_moments"])


def test_markdown_export():
    md = insights.report_markdown(insights.report(7), "Recap text.")
    assert md.startswith("# ") and "## Key moments" in md and "Recap text." in md


def test_fallback_answers_are_grounded():
    facts, r = analyst.facts_for(23)
    for q in ["who scored?", "who had better chances", "best player?", "shots", "cards", "passing", "hello"]:
        assert analyst.verify(analyst.fallback_answer(q, facts), facts, r) == []
    assert analyst.verify(analyst.fallback_recap(facts), facts, r) == []


def test_verify_catches_invented_claims():
    facts, r = analyst.facts_for(7)
    (lead, _), (other, _) = sorted(facts["teams"].items(), key=lambda kv: -kv[1]["xg"])
    bad = f"{other} had the higher xG and 71% possession, xG 9.99."
    issues = analyst.verify(bad, facts, r)
    assert any(i.startswith("numbers") for i in issues)
    assert any(i.startswith("leader:xg") for i in issues)
    assert any("possession" in i for i in issues)


def test_llm_answer_rejected_falls_back(monkeypatch):
    class Fake:
        name = "analyst"
        async def ask(self, prompt, entry=None, est_extra=0):
            return "Everyone scored 7777 goals."
    monkeypatch.setattr(analyst, "_brain", lambda *a: Fake())
    out = asyncio.run(analyst.ask(7, "who scored?"))
    assert out["source"] == "rules" and out["rejected"]


def test_api_endpoints():
    assert len(c.get("/api/matches").json()["matches"]) == len(FIXTURES)
    j = c.get("/api/report?seed=42&recap=true").json()
    assert j["recap"]["text"] and j["players"]
    md = c.get("/api/report?seed=42&format=md")
    assert md.headers["content-type"].startswith("text/markdown") and "attachment" in md.headers["content-disposition"]
    a = c.post("/api/ask", json={"seed": 42, "question": "who scored?", "minute": 60}).json()
    assert a["text"] and a["verified"]
    assert c.post("/api/ask", json={"seed": 42, "question": ""}).status_code == 422
    assert "analyst_desk" in c.get("/api/usage").json()


def test_meta_only_and_ui_features():
    j = c.get("/api/match?seed=11&meta_only=true").json()
    assert len(j["events"]) == 1 and j["events"][0]["meta"]["home"]["name"] == "Northgate Falcons"
    html = c.get("/").text
    for needle in ['id="pitch"', 'id="mom"', 'id="timeline"', "/api/ask", "/api/report", "speechSynthesis",
                   'data-v="neutral"', 'id="pipe"', "format=md"]:
        assert needle in html


def test_neutral_persona_stream():
    with c.stream("GET", "/api/stream?seed=23&speed=0&mode=neutral&lang=en") as r:
        data = [l for l in r.iter_lines() if l.startswith("data: {\"cards")]
    assert data
