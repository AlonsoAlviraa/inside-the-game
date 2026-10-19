from collections import Counter
import asyncio
from insidethegame.generator import MatchGenerator, stream


def test_deterministic():
    assert list(MatchGenerator(3).events()) == list(MatchGenerator(3).events())
    assert list(MatchGenerator(3).events()) != list(MatchGenerator(4).events())


def test_plausible_rates_over_many_matches():
    tot = Counter()
    n = 20
    for s in range(n):
        evs = list(MatchGenerator(s).events())
        assert evs[0]["type"] == "match_start" and evs[-1]["type"] == "match_end"
        assert all(a["t"] <= b["t"] for a, b in zip(evs, evs[1:]))
        assert 90 <= evs[-1]["minute"] <= 100
        tot += Counter(e["type"] for e in evs)
    avg = {k: v / n for k, v in tot.items()}
    assert 700 < avg["pass"] < 1300
    assert 15 < avg["shot"] < 40
    assert 1.0 < avg["goal"] < 4.5
    assert avg["card"] < 8 and avg["substitution"] <= 10


def test_events_within_pitch_and_valid():
    for e in MatchGenerator(1).events():
        if e["type"] == "pass":
            assert 0 <= e["end_x"] <= 105 and 0 <= e["end_y"] <= 68
            assert 0 <= e["quality"] <= 100 and e["speed_kmh"] > 0
        if e["type"] == "shot":
            assert 0 < e["xg"] < 1


def test_goal_events_match_final_score():
    evs = list(MatchGenerator(5).events())
    goals = Counter(e["team"] for e in evs if e["type"] == "goal")
    assert dict(goals) == {k: v for k, v in evs[-1]["score"].items() if v}


def test_stream_no_wait():
    async def run():
        return [e async for e in stream(2, speed=0)]
    assert len(asyncio.run(run())) == len(list(MatchGenerator(2).events()))
