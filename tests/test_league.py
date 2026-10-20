from fastapi.testclient import TestClient
from insidethegame import league
from insidethegame.server import app
from insidethegame.teams import FIXTURES, LEAGUE_DAYS, club_list, crest_svg

c = TestClient(app)


def test_league_has_16_fictional_clubs_and_round_robin():
    clubs = club_list()
    assert len(clubs) == 16 and len({x["short"] for x in clubs}) == 16
    seeds = league.league_seeds()
    assert len(seeds) == 8 * LEAGUE_DAYS
    for d in range(1, LEAGUE_DAYS + 1):  # every club plays once per matchday
        ids = [x for s in seeds if (s - 1000) // 10 == d for x in FIXTURES[s][:2]]
        assert sorted(ids) == sorted(x["id"] for x in clubs)


def test_table_consistent_with_results():
    t = league.table()
    assert sum(r["gf"] for r in t) == sum(r["ga"] for r in t)
    assert all(r["played"] == LEAGUE_DAYS and r["points"] == 3 * r["won"] + r["drawn"] for r in t)
    assert [r["position"] for r in t] == list(range(1, 17))
    assert all(t[i]["points"] >= t[i + 1]["points"] for i in range(15))


def test_win_probability_sane_and_resolves():
    for seed in (7, 1011):
        w = league.win_probability(seed)
        assert all(abs(p["home"] + p["draw"] + p["away"] - 1) < 0.01 for p in w)
        final = w[-1]
        sc = list(final["score"].values())
        expect = "home" if sc[0] > sc[1] else "away" if sc[1] > sc[0] else "draw"
        assert final[expect] == 1.0


def test_preview_formation_crest():
    p = league.preview(1023)
    assert len(p["head_to_head"]) == 5 and sum(p["head_to_head_record"].values()) == 5
    assert all(len(v) == 11 for v in p["lineups"].values())
    f = league.formation(7)
    assert all(len(t["players"]) == 11 for t in f["teams"].values())
    assert crest_svg("falcons").startswith("<svg") and "NGF" in crest_svg("falcons")


def test_league_endpoints():
    j = c.get("/api/league").json()
    assert len(j["table"]) == 16 and any("score" in f for f in j["fixtures"])
    assert c.get("/api/crest/aurora.svg").headers["content-type"].startswith("image/svg")
    assert c.get("/api/crest/nope.svg").status_code == 404
    assert c.get("/api/preview?seed=1011").json()["pre_match_probability"]
    assert len(c.get("/api/winprob?seed=7").json()["series"]) > 90
    r = c.get("/api/report?seed=7").json()["players"]
    cmp = c.get(f"/api/compare?seed=7&a={r[0]['player_id']}&b={r[1]['player_id']}").json()
    assert cmp["a"]["name"] == r[0]["name"]
