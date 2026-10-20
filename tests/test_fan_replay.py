import asyncio
from insidethegame import replay
from insidethegame.room import CommentaryRoom, ViewerMemory, ViewerProfile, localise, semantic
from insidethegame.generator import stream


def _run(lang, mode, player=None):
    async def go():
        room = CommentaryRoom(7, memory=ViewerMemory()); await room.start()
        p = ViewerProfile(mode=mode, language=lang, player=player, viewer_id="t")
        out, batch = [], []
        async for ev in stream(7, 0):
            batch.append(ev)
            if ev["t"] - batch[0]["t"] >= 150 or ev["type"] in replay.FLUSH:
                out += (await room.process_batch(batch, p)).cards; batch = []
        await room.close()
        return out
    return asyncio.run(go())


def test_no_english_fallback_without_llm(monkeypatch):
    monkeypatch.setenv("ITG_LLM_PROVIDER", "mock")
    for lang in ("es", "fr"):
        cards = _run(lang, "fan")
        assert cards and all(c["lang"] == lang for c in cards)
    es = _run("es", "neutral")
    assert any("Gol de" in c["text"] for c in es if c["type"] == "goal")


def test_fan_rules_lines_pass_fan_checks(monkeypatch):
    monkeypatch.setenv("ITG_LLM_PROVIDER", "mock")
    for c in _run("en", "fan"):
        assert not semantic.fan_violations(c["text"], c["facts"]), c


def test_bias_checks():
    assert semantic.fan_violations("Pathetic defending from the visitors", {})
    assert semantic.fan_violations("We are all over them", {})
    assert not semantic.fan_violations("Lovely move by Hugo Northam", {})


def test_localise_all_moments():
    for lang in ("en", "es", "fr"):
        assert "Ana" in localise.rule_text({"facts": {"moment": "goal", "player": "Ana", "team": "X", "score": "1-0"}}, lang)
        assert localise.rule_text({"facts": {"moment": "phase_change", "new_phase": "chaos"}}, lang)


def test_replay_personalise_marks_favourite():
    p = {"cards": [{"id": "a", "priority": 2, "title": "Chance", "team": "h", "player_id": "p1"},
                   {"id": "b", "priority": 3, "title": "x", "team": "a", "player_id": "p2"}]}
    out = replay.personalise(p, None, "p1")
    assert out["replay"] and out["cards"][0]["fav"] == "player" and out["cards"][0]["title"].startswith("★")
