import asyncio
import pytest
from insidethegame.generator import MatchGenerator
from insidethegame.room import CommentaryRoom, ViewerMemory, ViewerProfile, validate_card
from insidethegame.room import factcheck
from insidethegame.room.llm import TokenBudget


def play(profile=None, orch="maf", seed=7, raw_hook=None, tmp="/tmp/itg_room_test.json"):
    room = CommentaryRoom(seed, orch, online=False, memory=ViewerMemory(tmp))
    profile = profile or ViewerProfile(mode="analyst")

    async def go():
        cards, batch, last = [], [], None
        evs = list(MatchGenerator(seed).events())
        if raw_hook:
            evs = raw_hook(evs)
        for ev in evs:
            batch.append(ev)
            if ev["t"] - batch[0]["t"] >= 300 or ev["type"] in ("goal", "match_end"):
                last = await room.process_batch(batch, profile)
                cards += last.cards
                batch = []
        return cards, last
    cards, last = asyncio.run(go())
    return room, cards, last


def test_five_agents_in_trace_and_maf_default():
    room, cards, last = play()
    assert room.orchestrator == "maf" and not room.errors
    assert [t["agent"] for t in last.trace][:1] == ["ingest"]
    assert {"ingest", "interpret", "salience", "explain", "render", "personalise"} == {t["agent"] for t in last.trace}


def test_maf_equals_sequential():
    _, a, _ = play(orch="maf")
    _, b, _ = play(orch="sequential")
    assert [c["text"] for c in a] == [c["text"] for c in b]


def test_cards_valid_and_cover_goals():
    room, cards, _ = play()
    assert cards and all(not validate_card(c) for c in cards)
    goals = sum(room.state.score.values())
    assert sum(c["type"] == "goal" for c in cards) == goals
    assert any(c["type"] == "period" and "Full-time" in c["text"] for c in cards)
    assert {"phase", "chance"} <= {c["type"] for c in cards}


def test_ingest_dedupes_and_flags_anomalies():
    def inject(evs):
        evs = list(evs)
        evs.insert(50, dict(evs[49]))                       # exact duplicate
        bad = dict(evs[60]); bad["id"] = 99999; bad["t"] = 1.0; bad["x"] = 150.0
        evs.insert(61, bad)                                  # time travel + off-pitch
        broken = {"id": 99998, "t": evs[70]["t"], "type": "pass", "minute": 3, "period": 1}
        evs.insert(71, broken)                               # missing fields
        return evs
    room, _, _ = play(raw_hook=inject)
    issues = " ".join(a["issue"] for a in room.state.anomalies)
    assert "time went backwards" in issues and "off pitch" in issues and "missing" in issues
    assert len(room.state.spadl) > 500


def test_factcheck_rejects_invented_numbers():
    facts = {"xg": 0.31, "minute": 23, "score": "HCM 1-0 IRR", "distance_m": 11.4}
    assert factcheck.check("A 0.31 xG chance from 11 m in minute 23 makes it 1-0.", facts)[0]
    ok, bad = factcheck.check("His 7th goal of the season, 0.31 xG.", facts)
    assert not ok and "7" in bad


def test_fan_mode_strips_metrics_and_boosts_favourites():
    room, ana, _ = play(ViewerProfile(mode="analyst"))
    gp = next(c["player_id"] for c in ana if c["type"] == "goal")
    _, fan, _ = play(ViewerProfile(mode="fan", player=gp))
    assert len(fan) < len(ana)
    assert not any("xG" in c["text"] for c in fan if c["type"] == "goal")
    assert all(c["priority"] == 5 and c["title"].startswith("★") for c in fan if c["player_id"] == gp)


def test_non_english_offline_stays_in_chosen_language():
    _, cards, _ = play(ViewerProfile(mode="analyst", language="es"))
    assert cards and all(c["lang"] == "es" for c in cards)


def test_viewer_memory_persists(tmp_path):
    path = str(tmp_path / "m.json")
    m = ViewerMemory(path)
    m.remember_profile(ViewerProfile(mode="fan", language="fr", club="ridge", viewer_id="v1"))
    m2 = ViewerMemory(path)
    p = m2.fill_defaults(ViewerProfile(mode="analyst", viewer_id="v1"))
    assert p.club == "ridge" and m2.get("v1")["sessions"] == 1


def test_token_budget_caps_short_window():
    b = TokenBudget(tpm=6000, max_wait_s=0)
    assert b.short == 1500
    assert asyncio.run(b.acquire(900))
    assert not asyncio.run(b.acquire(900))   # 10 s slice = 1500 tokens
    assert b.used() == 900


def test_templates_pass_semantic_check_and_flicker_is_low():
    from collections import Counter
    from insidethegame.room import semantic
    room, cards, _ = play()
    for c in cards:
        assert semantic.check(c["text"], c["facts"], room.state.snapshot(), room.state.meta,
                              room.state.roster()) == [], c
    n = Counter(c["type"] for c in cards)
    assert n["phase"] <= 6 and n["stat"] <= 8


def test_fixed_per_language_titles():
    _, es, _ = play(ViewerProfile(mode="analyst", language="es"))
    titles = {c["type"]: c["title"] for c in es}
    assert titles["goal"].startswith("GOL ·") and titles["phase"] == "Cambio de fase"
    assert any(c["title"].startswith("Final ·") for c in es if c["type"] == "period")
    _, fr, _ = play(ViewerProfile(mode="analyst", language="fr"))
    assert any(c["title"].startswith("BUT ·") for c in fr)


def test_goal_card_shows_score_at_time_of_goal():
    room, cards, _ = play(seed=11)
    goals = [c for c in cards if c["type"] == "goal"]
    assert len({c["title"] for c in goals}) == len(goals)  # each goal has its own scoreline
