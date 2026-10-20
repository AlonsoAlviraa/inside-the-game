import json
from fastapi.testclient import TestClient
from insidethegame import league, season
from insidethegame.server import app
from insidethegame.teams import FIXTURES

c = TestClient(app)


def test_cache_matches_engine():
    cached = {m["seed"]: m for m in season.season()["matches"]}
    assert len(cached) == 240
    for s in (1010, 1157, 1307):
        assert json.loads(json.dumps(season.summarise(s))) == cached[s]


def test_double_round_robin_each_pair_home_and_away():
    pairs = [FIXTURES[m["seed"]][:2] for m in season.matches()]
    assert len(set(pairs)) == 240 and all((b, a) in set(pairs) for a, b in pairs)


def test_goals_and_assists_consistent():
    for m in season.matches()[:40]:
        assert sum(p["goals"] for p in m["players"].values()) == sum(m["score"].values()) == len(m["goals"])
        for g in m["goals"]:
            assert g["assist_id"] != g["player_id"]
    lead = season.leaders()
    assert lead["goals"][0]["goals"] >= lead["goals"][-1]["goals"]


def test_team_season_matches_table():
    t = {r["id"]: r for r in season.table(20)}
    for club in ("harbour", "vale"):
        ts = season.team_season(club, 20)
        assert ts["played"] == 20 and ts["totals"]["goals_for"] == t[club]["gf"]
        assert ts["totals"]["goals_against"] == t[club]["ga"]
        assert sum(p["goals"] for p in ts["squad"]) == t[club]["gf"]


def test_preview_uses_only_earlier_matches():
    seed = next(s for s in FIXTURES if s >= 1000 and season.day_of(s) == 20)
    p = league.preview(seed)
    assert p["standings_after_matchday"] == 19 and p["home"]["table"]["played"] == 19
    assert p["home"]["season"]["played"] == 19
    assert len(p["meetings"]) == 1 and p["meetings"][0]["matchday"] < 20  # first leg already played


def test_moves_and_endpoints():
    t = season.table_with_moves(10)
    assert sum(r["move"] for r in t) == 0
    j = c.get("/api/league?day=12").json()
    assert j["day"] == 12 and len(j["positions"]["harbour"]) == 12 and j["leaders"]["goals"]
    tp = c.get("/api/team/falcons?day=12").json()
    assert tp["season"]["played"] == 12 and len(tp["matches"]) == 30
    assert sum(1 for g in tp["matches"] if g["score"]) == 12
    assert c.get("/api/team/nope").status_code == 404
