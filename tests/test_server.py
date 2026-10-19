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
        ticks = [json.loads(l[6:]) for l in r.iter_lines() if l.startswith("data: ") and l != "data: {}"]
    assert ticks[0]["event"]["type"] == "match_start"
    assert any(t["commentary"] for t in ticks)
