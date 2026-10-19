"""Sequential handoff pipeline: Stats -> Tactics -> Narrator -> Personaliser.

Maps onto a Microsoft Agent Framework workflow (each agent = executor, MatchState = shared state).
Each agent is isolated: an exception in one agent is recorded and the pipeline continues.
"""
from __future__ import annotations
from .base import AgentOutput, MatchState, ViewerProfile
from .llm import LLMClient, make_llm
from .specialists import NarratorAgent, PersonaliserAgent, StatsAgent, TacticsAgent


class CommentaryRoom:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or make_llm()
        self.state = MatchState()
        self.agents = [StatsAgent(), TacticsAgent(self.llm), NarratorAgent(self.llm)]
        self.personaliser = PersonaliserAgent(self.llm)
        self.errors: list[str] = []

    async def process(self, ev: dict, profile: ViewerProfile) -> list[dict]:
        outputs: list[AgentOutput] = []
        for agent in self.agents:
            try:
                outputs += await agent.handle(ev, self.state)
            except Exception as e:  # failure isolation
                self.errors.append(f"{agent.name}: {e!r}")
        result = []
        for o in outputs:
            try:
                p = await self.personaliser.personalise(o, profile, self.state)
            except Exception as e:
                self.errors.append(f"personaliser: {e!r}")
                p = o
            if p is not None:
                result.append(p.to_dict())
        return result
