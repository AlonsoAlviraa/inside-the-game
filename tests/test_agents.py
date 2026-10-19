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


def test_spanish_translation():
    _, out = run_match(ViewerProfile(mode="fan", language="es"))
    assert any("Final" in o["text"] or "¡GOL!" in o["text"] for o in out)


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
