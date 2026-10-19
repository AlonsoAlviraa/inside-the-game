import asyncio
from insidethegame.agents import CommentaryRoom, ViewerProfile
from insidethegame.agents.llm import MockLLM, ResilientLLM
from insidethegame.generator import MatchGenerator


def run_match(profile, llm=None, seed=5):
    room = CommentaryRoom(llm or MockLLM())

    async def go():
        out = []
        for ev in MatchGenerator(seed).events():
            out += await room.process(ev, profile)
        return out
    return room, asyncio.run(go())


def test_pipeline_produces_all_agent_kinds_analyst():
    room, out = run_match(ViewerProfile(mode="analyst"))
    kinds = {o["kind"] for o in out}
    assert {"stat", "tactic", "narration"} <= kinds
    assert not room.errors
    assert any("Full-time" in o["text"] for o in out)


def test_fan_vs_analyst_differ():
    _, fan = run_match(ViewerProfile(mode="fan"))
    _, ana = run_match(ViewerProfile(mode="analyst"))
    assert len(fan) < len(ana)


def test_non_english_fallback_is_clean_english():
    # Without an LLM, non-English viewers get the plain English line, never a half-translated mix.
    _, out = run_match(ViewerProfile(mode="fan", language="es"))
    assert any("Full-time" in o["text"] for o in out)
    assert not any("¡GOL!" in o["text"] or " desde " in o["text"] for o in out)


class Recorder:
    name = "rec"

    def __init__(self):
        self.prompts = []

    async def complete(self, system, user, *, fallback=""):
        self.prompts.append(user)
        return fallback


def test_fan_prompt_is_tight_and_targets_language():
    rec = Recorder()
    run_match(ViewerProfile(mode="fan", language="es", club="harbour"), llm=rec)
    fan = [p for p in rec.prompts if p.startswith("Fan mode")]
    assert fan and all("max 20 words" in p and "Spanish" in p for p in fan)


def test_player_focus_boosts_importance():
    ev_player = next(e["player_id"] for e in MatchGenerator(5).events() if e["type"] == "goal")
    _, base = run_match(ViewerProfile(mode="analyst"))
    _, foc = run_match(ViewerProfile(mode="analyst", player=ev_player))
    pick = lambda xs: max(o["importance"] for o in xs if o["data"].get("player_id") == ev_player and o["kind"] == "stat")
    assert pick(foc) > pick(base)


class Broken:
    name = "broken"

    async def complete(self, system, user, *, fallback=""):
        raise RuntimeError("azure down")


def test_llm_failure_recovers_to_mock():
    llm = ResilientLLM(Broken())
    room, out = run_match(ViewerProfile(mode="fan"), llm=llm)
    assert out and llm.failures > 0 and not room.errors


def test_maf_workflow_matches_sequential():
    import pytest
    pytest.importorskip("agent_framework")
    prof = ViewerProfile(mode="analyst")
    seq_room = CommentaryRoom(MockLLM(), orchestrator="sequential")
    maf_room = CommentaryRoom(MockLLM(), orchestrator="maf")
    assert maf_room.orchestrator == "maf"
    evs = list(MatchGenerator(3).events())[:600]

    async def go(room):
        out = []
        for ev in evs:
            out += await room.process(ev, prof)
        return out
    assert asyncio.run(go(seq_room)) == asyncio.run(go(maf_room))
    assert not maf_room.errors
