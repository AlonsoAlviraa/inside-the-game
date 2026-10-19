"""Shared state, messages, overlay-card schema and viewer memory."""
from __future__ import annotations
import json
import os
import threading
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class ViewerProfile:
    mode: str = "fan"            # fan | analyst
    language: str = "en"         # en | es | fr
    club: str | None = None      # favourite team id
    player: str | None = None    # favourite player id
    viewer_id: str = "anonymous"


@dataclass
class RoomState:
    """Blackboard shared by all five agents (one per match/stream)."""
    meta: dict = field(default_factory=dict)
    score: dict = field(default_factory=dict)
    minute: int = 0
    period: int = 1
    last_t: float = -1.0
    seen_ids: set = field(default_factory=set)
    fingerprints: set = field(default_factory=set)
    spadl: list = field(default_factory=list)
    team_stats: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(float)))
    player_stats: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(float)))
    index: dict = field(default_factory=dict)
    phase: str = "kick-off"
    phase_team: str | None = None
    phase_history: list = field(default_factory=list)
    tactical_read: str = ""
    anomalies: list = field(default_factory=list)
    explained_ids: set = field(default_factory=set)

    def team_name(self, tid: str | None) -> str:
        for side in ("home", "away"):
            if self.meta.get(side, {}).get("id") == tid:
                return self.meta[side]["name"]
        return tid or ""

    def player_name(self, pid: str | None) -> str:
        for side in ("home", "away"):
            for p in self.meta.get(side, {}).get("players", []):
                if p["id"] == pid:
                    return p["name"]
        return pid or ""

    def score_line(self) -> str:
        if not self.meta or not self.score:
            return ""
        h, a = self.meta["home"], self.meta["away"]
        return f"{h['short']} {self.score.get(h['id'], 0)}-{self.score.get(a['id'], 0)} {a['short']}"

    def snapshot(self) -> dict:
        """Compact, LLM-friendly facts (the only numbers agents may cite)."""
        teams = {}
        for tid, s in self.team_stats.items():
            p = s.get("passes", 0)
            teams[self.team_name(tid)] = {"goals": self.score.get(tid, 0), "shots": int(s.get("shots", 0)),
                                          "xg": round(s.get("xg", 0), 2), "xt": round(s.get("xt", 0), 2),
                                          "passes": int(p),
                                          "pass_completion_pct": round(100 * s.get("passes_ok", 0) / p) if p else 0}
        return {"minute": self.minute, "score": self.score_line(), "phase": self.phase,
                "phase_team": self.team_name(self.phase_team) if self.phase_team else None,
                "control": {self.team_name(k): v for k, v in self.index.get("control", {}).items()},
                "chaos": self.index.get("chaos"), "teams": teams}


@dataclass
class Batch:
    """Message passed along the workflow graph: one window of raw events for one viewer."""
    raw: list[dict]
    profile: ViewerProfile
    events: list[dict] = field(default_factory=list)       # validated, normalised
    report: dict = field(default_factory=dict)             # ingest report
    insights: list[dict] = field(default_factory=list)     # interpret output (phase changes, tactical read)
    candidates: list[dict] = field(default_factory=list)   # salience-scored moments
    explained: list[dict] = field(default_factory=list)    # moments + grounded "why"
    cards: list[dict] = field(default_factory=list)        # render output
    trace: list[dict] = field(default_factory=list)        # per-agent trace for the UI


# --------------------------------------------------------------------------- overlay cards
CARD_TYPES = ["goal", "chance", "card", "phase", "insight", "stat", "substitution", "period"]
VIZ_KINDS = ["shot_marker", "pass_arrow", "control_gauge", "badge", "none"]
CARD_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "OverlayCard",
    "type": "object",
    "required": ["id", "type", "priority", "ttl_s", "minute", "title", "text", "viz", "verified"],
    "properties": {
        "id": {"type": "string"},
        "type": {"enum": CARD_TYPES},
        "priority": {"type": "integer", "minimum": 1, "maximum": 5},
        "ttl_s": {"type": "integer", "minimum": 3, "maximum": 30},
        "minute": {"type": "integer", "minimum": 0},
        "title": {"type": "string", "maxLength": 60},
        "text": {"type": "string", "maxLength": 400},
        "team": {"type": ["string", "null"]},
        "player_id": {"type": ["string", "null"]},
        "viz": {"type": "object", "required": ["kind"], "properties": {"kind": {"enum": VIZ_KINDS}}},
        "facts": {"type": "object"},
        "verified": {"type": "boolean"},
        "source": {"type": "string"},
    },
}


def validate_card(card: dict) -> list[str]:
    """Minimal validator for CARD_SCHEMA (no extra dependency). Returns a list of problems."""
    errs = [f"missing {k}" for k in CARD_SCHEMA["required"] if k not in card]
    if errs:
        return errs
    if card["type"] not in CARD_TYPES:
        errs.append("bad type")
    if not (isinstance(card["priority"], int) and 1 <= card["priority"] <= 5):
        errs.append("bad priority")
    if not (isinstance(card["ttl_s"], int) and 3 <= card["ttl_s"] <= 30):
        errs.append("bad ttl")
    if card["viz"].get("kind") not in VIZ_KINDS:
        errs.append("bad viz")
    if len(card["title"]) > 60 or len(card["text"]) > 400:
        errs.append("too long")
    return errs


# --------------------------------------------------------------------------- viewer memory
class ViewerMemory:
    """Remembers each viewer's preferences across sessions (JSON file; ITG_MEMORY_PATH)."""

    def __init__(self, path: str | None = None):
        self.path = Path(path or os.getenv("ITG_MEMORY_PATH", "/tmp/itg_viewer_memory.json"))
        self._lock = threading.Lock()
        try:
            self.data = json.loads(self.path.read_text())
        except Exception:
            self.data = {}

    def get(self, viewer_id: str) -> dict:
        return self.data.setdefault(viewer_id, {"profile": {}, "sessions": 0, "type_counts": {}, "recent": []})

    def remember_profile(self, profile: ViewerProfile) -> dict:
        m = self.get(profile.viewer_id)
        prev = m.get("profile") or {}
        m["profile"] = {k: v for k, v in asdict(profile).items() if k != "viewer_id"}
        m["sessions"] += 1
        if prev and prev.get("mode") != profile.mode:
            m["mode_switches"] = m.get("mode_switches", 0) + 1
        self.save()
        return m

    def fill_defaults(self, profile: ViewerProfile) -> ViewerProfile:
        """Unset fields fall back to what this viewer chose last time."""
        last = self.get(profile.viewer_id).get("profile") or {}
        for k in ("club", "player"):
            if getattr(profile, k) in (None, "") and last.get(k):
                setattr(profile, k, last[k])
        return profile

    def record_cards(self, viewer_id: str, cards: list[dict]) -> None:
        m = self.get(viewer_id)
        for c in cards:
            m["type_counts"][c["type"]] = m["type_counts"].get(c["type"], 0) + 1
            m["recent"] = (m["recent"] + [c["text"][:80]])[-6:]

    def summary(self, viewer_id: str) -> str:
        m = self.get(viewer_id)
        p = m.get("profile", {})
        return (f"sessions={m['sessions']}, mode={p.get('mode')}, language={p.get('language')}, "
                f"club={p.get('club')}, player={p.get('player')}, recently shown: {m['recent'][-3:]}")

    def save(self) -> None:
        with self._lock:
            try:
                self.path.write_text(json.dumps(self.data))
            except Exception:
                pass
