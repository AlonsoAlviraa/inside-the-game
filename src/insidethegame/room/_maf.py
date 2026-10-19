# No `from __future__ import annotations` here: MAF inspects handler annotations at class creation.
"""Agent Framework executors wrapping the five room agents."""
from agent_framework import Executor, WorkflowContext, handler

from .state import Batch


class Step(Executor):
    def __init__(self, room, agent, final: bool = False):
        super().__init__(id=agent.name)
        self.room, self.agent, self.final = room, agent, final

    @handler
    async def on_batch(self, b: Batch, ctx: WorkflowContext[Batch, Batch]) -> None:
        await self.room._step(self.agent, b)
        if self.final:
            await ctx.yield_output(b)
        else:
            await ctx.send_message(b)


class Join(Executor):
    """Fan-in: merges the Interpret and Salience branches, then runs Explain."""

    def __init__(self, room, agent):
        super().__init__(id=agent.name)
        self.room, self.agent = room, agent

    @handler
    async def on_batches(self, bs: list[Batch], ctx: WorkflowContext[Batch]) -> None:
        b = bs[0]
        for o in bs[1:]:
            if o is not b:  # merge parallel branches if the runtime copied the message
                b.insights += [i for i in o.insights if i not in b.insights]
                b.candidates += [c for c in o.candidates if c not in b.candidates]
                b.trace += [t for t in o.trace if t not in b.trace]
        await self.room._step(self.agent, b)
        await ctx.send_message(b)
