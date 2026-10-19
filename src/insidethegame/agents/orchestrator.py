"""Handoff pipeline: Stats -> Tactics -> Narrator -> Personaliser.

Orchestrated by a Microsoft Agent Framework workflow when ITG_ORCHESTRATOR=maf (see maf_workflow.py),
otherwise by the equivalent plain sequential loop below.
Each agent is isolated: an exception in one agent is recorded and the pipeline continues.
"""
from __future__ import annotations
import os
from .base import AgentOutput, MatchState, ViewerProfile
from .llm import LLMClient, make_llm
from .specialists import NarratorAgent, PersonaliserAgent, StatsAgent, TacticsAgent


class CommentaryRoom:
    def __init__(self, llm: LLMClient | None = None, orchestrator: str | None = None):
        self.llm = llm or make_llm()
        self.state = MatchState()
        self.agents = [StatsAgent(), TacticsAgent(self.llm), NarratorAgent(self.llm)]
        self.personaliser = PersonaliserAgent(self.llm)
        self.errors: list[str] = []
        self.orchestrator = "sequential"
        self._wf = None
        if (orchestrator or os.getenv("ITG_ORCHESTRATOR", "sequential")).lower() == "maf":
            try:
                from .maf_workflow import build_workflow
                self._wf = build_workflow(self.agents, self.personaliser, self.state)
                self.orchestrator = "maf"
            except ImportError:
                pass

    async def process(self, ev: dict, profile: ViewerProfile) -> list[dict]:
        if self._wf is not None:
            from .maf_workflow import run_turn
            turn = await run_turn(self._wf, ev, profile)
            self.errors += turn.errors
            return [o.to_dict() for o in turn.outputs]
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
