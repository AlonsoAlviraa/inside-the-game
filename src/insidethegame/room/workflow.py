"""Microsoft Agent Framework workflow graph for the five-agent room.

                ┌─> interpret ──┐
    ingest ─────┤               ├─> explain ─> render ─> personalise ─> (output)
                └─> salience ───┘
    fan-out                      fan-in

ITG_ORCHESTRATOR=maf (default) runs the graph with agent_framework.WorkflowBuilder; "sequential" (or a
missing package) runs the same agents in the same order in a plain loop.
"""
import os

from . import telemetry
from .agents import ExplainAgent, IngestAgent, InterpretAgent, PersonaliseAgent, RenderAgent, SalienceScout
from .llm import Brain, TokenBudget, UsageLedger, azure_enabled, make_chat_client
from .state import Batch, RoomState, ViewerMemory, ViewerProfile


def _interpret_tools(seed_getter):
    """MCP tools for the Interpret agent. Prefer the real insidethegame-mcp server over stdio
    (ITG_USE_MCP=1, default); fall back to the same functions exposed as in-process MAF tools."""
    from agent_framework import tool
    from .. import mcp_server as m

    @tool
    def top_players(seed: int, metric: str = "xt", n: int = 3, up_to_minute: int = 90) -> list[dict]:
        """Top players by 'xt', 'xg' or 'pass_quality' up to a match minute."""
        return m.top_players(seed, metric, n, up_to_minute)

    @tool
    def control_index(seed: int, minute: int) -> dict:
        """Control-vs-chaos snapshot at a match minute."""
        return m.control_index(seed, minute)
    return [top_players, control_index]


VERIFIER_INSTRUCTIONS = ("You verify football commentary against facts. For each item, ok=false only if the text "
                         "contradicts the facts (wrong leader, wrong player, wrong metric name, wrong minute/period, "
                         "control index called possession). Wording, style, tone and calling the control index 'control' are fine. Reply JSON {\"results\":[{\"id\":..,\"ok\":true|false,"
                         "\"issue\":\"...\"}]}")


class CommentaryRoom:
    def __init__(self, seed: int = 7, orchestrator: str | None = None, online: bool | None = None,
                 memory: ViewerMemory | None = None, budget: TokenBudget | None = None,
                 ledger: UsageLedger | None = None):
        telemetry.setup()
        self.seed = seed
        self.state = RoomState()
        self.ledger = ledger or UsageLedger()
        self.budget = budget or TokenBudget()
        self.memory = memory or ViewerMemory()
        online = azure_enabled() if online is None else online
        client = make_chat_client() if online else None
        self.mcp_tool = None
        tools = []
        if client is not None:
            if os.getenv("ITG_USE_MCP", "1") == "1":
                import sys
                from agent_framework import MCPStdioTool
                self.mcp_tool = MCPStdioTool(name="insidethegame", command=sys.executable,
                                             args=["-m", "insidethegame.mcp_server"],
                                             allowed_tools=["top_players", "control_index"], load_prompts=False)
                tools = [self.mcp_tool]
            else:
                tools = _interpret_tools(lambda: self.seed)
        mk = lambda cls, mt, t=None: Brain(cls.name, cls.instructions, client, t, self.budget, self.ledger, mt)
        st = self.state
        self.ingest = IngestAgent(st)
        self.interpret = InterpretAgent(st, mk(InterpretAgent, 120, tools), seed)
        self.salience = SalienceScout(st)
        verifier = None
        if client is not None and os.getenv("ITG_LLM_VERIFY", "0") == "1":
            verifier = Brain("verifier", VERIFIER_INSTRUCTIONS, client, None, self.budget, self.ledger, 150)
        self.explain = ExplainAgent(st, mk(ExplainAgent, 260), verifier=verifier)
        self.render = RenderAgent(st)
        self.personalise = PersonaliseAgent(st, mk(PersonaliseAgent, 320), self.memory)
        self.errors: list[str] = []
        self.orchestrator = "sequential"
        self._wf = None
        if (orchestrator or os.getenv("ITG_ORCHESTRATOR", "maf")).lower() == "maf":
            try:
                self._wf = self._build_maf()
                self.orchestrator = "maf"
            except ImportError:
                pass

    async def start(self) -> None:
        if self.mcp_tool is not None:
            try:
                await self.mcp_tool.connect()
            except Exception as e:  # MCP failure -> in-process tools
                self.errors.append(f"mcp connect: {e!r}")
                self.interpret.brain = Brain(InterpretAgent.name, InterpretAgent.instructions, make_chat_client(),
                                             _interpret_tools(lambda: self.seed), self.budget, self.ledger, 120)
                self.mcp_tool = None

    async def close(self) -> None:
        if self.mcp_tool is not None:
            try:
                await self.mcp_tool.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ steps
    async def _step(self, agent, b: Batch) -> Batch:
        with telemetry.span(agent.name, b.trace, minute=self.state.minute) as entry:
            try:
                await agent.run(b, entry)
            except Exception as e:  # failure isolation: the match keeps going
                self.errors.append(f"{agent.name}: {e!r}")
                entry["error"] = repr(e)
        return b

    def _build_maf(self):
        from agent_framework import WorkflowBuilder
        from ._maf import Join, Step
        ing, intp, sal = Step(self, self.ingest), Step(self, self.interpret), Step(self, self.salience)
        exp, ren, per = Join(self, self.explain), Step(self, self.render), Step(self, self.personalise, final=True)
        return (WorkflowBuilder(start_executor=ing, name="inside-the-game-room",
                                description="Ingest -> (Interpret || Salience) -> Explain -> Render -> Personalise")
                .add_fan_out_edges(ing, [intp, sal]).add_fan_in_edges([intp, sal], exp)
                .add_chain([exp, ren, per]).build())

    async def process_batch(self, raw: list[dict], profile: ViewerProfile) -> Batch:
        b = Batch(raw=raw, profile=profile)
        if self._wf is not None:
            with telemetry.span("workflow", None, events=len(raw)):
                res = await self._wf.run(b)
            outs = res.get_outputs()
            return outs[-1] if outs else b
        for agent in (self.ingest, self.interpret, self.salience, self.explain, self.render, self.personalise):
            await self._step(agent, b)
        return b
