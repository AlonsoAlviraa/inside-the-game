import json
from fastapi.testclient import TestClient
from insidethegame.server import app

c = TestClient(app)


def test_health_and_index():
    assert c.get("/health").json()["status"] == "ok"
    assert "Commentary Room" in c.get("/").text


def test_sse_stream():
    with c.stream("GET", "/api/stream?seed=1&speed=0&mode=analyst") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        lines = list(r.iter_lines())
    ev_types = [l[7:] for l in lines if l.startswith("event: ")]
    data = [json.loads(l[6:]) for l in lines if l.startswith("data: ") and l != "data: {}"]
    ticks = [d for d in data if "event" in d]
    batches = [d for d in data if "cards" in d]
    assert ticks[0]["event"]["type"] == "match_start"
    assert batches and any(b["cards"] for b in batches)
    assert {t["agent"] for t in batches[-1]["trace"]} >= {"ingest", "interpret", "salience", "explain",
                                                          "render", "personalise"}
    assert ev_types[-1] == "end"


def test_card_schema_endpoint():
    assert c.get("/api/card-schema").json()["title"] == "OverlayCard"
