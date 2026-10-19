"""Microsoft Agent Framework orchestration of the commentary room.

Each specialist becomes an `Executor` in a MAF `Workflow` graph:

    stats -> tactics -> narrator -> personaliser (yields output)

A `Turn` message carries the event, viewer profile and accumulated outputs along the edges; the shared
`MatchState` blackboard lives on the room. Enable with ITG_ORCHESTRATOR=maf (requires
`pip install agent-framework-core`). If the package is missing, `CommentaryRoom` keeps the plain
sequential pipeline, which produces identical results.
Docs: https://github.com/microsoft/agent-framework (MIT)
"""
from __future__ import annotations
from dataclasses import dataclass, field

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

from .base import AgentOutput, MatchState, ViewerProfile


@dataclass
class Turn:
    event: dict
    profile: ViewerProfile
    outputs: list[AgentOutput] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class SpecialistExecutor(Executor):
    def __init__(self, agent, state: MatchState):
        super().__init__(id=agent.name)
        self.agent, self.state = agent, state

    @handler
    async def run(self, turn: Turn, ctx: WorkflowContext[Turn]) -> None:
        try:
            turn.outputs += await self.agent.handle(turn.event, self.state)
        except Exception as e:  # failure isolation per agent
            turn.errors.append(f"{self.agent.name}: {e!r}")
        await ctx.send_message(turn)


class PersonaliserExecutor(Executor):
    def __init__(self, agent, state: MatchState):
        super().__init__(id=agent.name)
        self.agent, self.state = agent, state

    @handler
    async def run(self, turn: Turn, ctx: WorkflowContext[Turn, Turn]) -> None:
        final: list[AgentOutput] = []
        for o in turn.outputs:
            try:
                p = await self.agent.personalise(o, turn.profile, self.state)
            except Exception as e:
                turn.errors.append(f"personaliser: {e!r}")
                p = o
            if p is not None:
                final.append(p)
        turn.outputs = final
        await ctx.yield_output(turn)


def build_workflow(agents: list, personaliser, state: MatchState):
    execs = [SpecialistExecutor(a, state) for a in agents]
    last = PersonaliserExecutor(personaliser, state)
    return WorkflowBuilder(start_executor=execs[0], name="commentary-room").add_chain([*execs, last]).build()


async def run_turn(workflow, event: dict, profile: ViewerProfile) -> Turn:
    result = await workflow.run(Turn(event, profile))
    return result.get_outputs()[-1]
