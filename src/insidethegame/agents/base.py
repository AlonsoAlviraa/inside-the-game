"""Agent contract. Designed to map 1:1 onto Microsoft Agent Framework executors / Foundry agents:
each agent has a name, a role (system instructions), reads shared `MatchState` and emits `AgentOutput`."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ViewerProfile:
    mode: str = "fan"          # "fan" | "analyst"
    language: str = "en"       # "en" | "es" | "fr"
    club: str | None = None    # favourite team id
    player: str | None = None  # favourite player id (player-focus mode)


@dataclass
class MatchState:
    """Shared blackboard all agents read/write (the 'commentary room')."""
    meta: dict = field(default_factory=dict)
    score: dict = field(default_factory=dict)
    minute: int = 0
    team_stats: dict = field(default_factory=dict)
    player_stats: dict = field(default_factory=dict)
    index: dict = field(default_factory=dict)
    last_label: str = "balanced"
    notes: list[str] = field(default_factory=list)  # handoff notes between agents

    def team_name(self, tid: str | None) -> str:
        for side in ("home", "away"):
            if self.meta.get(side, {}).get("id") == tid:
                return self.meta[side]["name"]
        return tid or ""


@dataclass
class AgentOutput:
    agent: str
    kind: str        # "stat" | "tactic" | "narration" | "personalised"
    text: str
    importance: float = 0.5  # 0..1, used by the overlay to prioritise
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"agent": self.agent, "kind": self.kind, "text": self.text,
                "importance": self.importance, "data": self.data}


class Agent(Protocol):
    name: str
    instructions: str

    async def handle(self, event: dict, state: MatchState) -> list[AgentOutput]: ...
