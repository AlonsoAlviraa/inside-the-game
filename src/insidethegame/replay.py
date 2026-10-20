"""Replay mode: AI commentary for the showcase matches is precomputed once (scripts/build_replay.py, real Azure
OpenAI calls through the same five-agent room and checks) and stored in data/replay/. Streaming a cached match makes
zero LLM calls: no quota risk, no warm-up pause, identical output for every judge."""
from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path

DIR = Path(__file__).resolve().parent / "data" / "replay"
SHOWCASE = (7, 11, 23, 42, 58)
MODES = ("fan", "neutral", "analyst")
LANGS = ("en", "es", "fr")
FLUSH = {"goal", "period_end", "match_end"}


def path(seed: int, mode: str, lang: str) -> Path:
    return DIR / f"{seed}-{mode}-{lang}.json"


@lru_cache(maxsize=64)
def load(seed: int, mode: str, lang: str) -> dict | None:
    p = path(seed, mode, lang)
    return json.loads(p.read_text()) if p.exists() else None


def available() -> list[dict]:
    return [{"seed": s, "mode": m, "lang": l} for s in SHOWCASE for m in MODES for l in LANGS if path(s, m, l).exists()]


def personalise(payload: dict, club: str | None, player: str | None) -> dict:
    """Apply the viewer's favourite club/player on top of a cached batch (deterministic, no LLM)."""
    out = dict(payload)
    cards = []
    for c in payload["cards"]:
        c = dict(c)
        if club and c.get("team") == club:
            c["priority"], c["fav"] = min(5, c["priority"] + 1), "club"
        if player and c.get("player_id") == player:
            c["priority"], c["fav"] = 5, "player"
            c["title"] = ("★ " + c["title"])[:60]
        cards.append(c)
    out["cards"] = sorted(cards, key=lambda c: -c["priority"])
    out["replay"] = True
    return out


async def record(seed: int, mode: str, lang: str, batch_s: float = 150) -> dict:
    """Run the full room once (no sleeping) and keep each batch's output keyed by the event that closed it."""
    from .generator import stream
    from .room import CommentaryRoom, ViewerMemory, ViewerProfile
    room = CommentaryRoom(seed, memory=ViewerMemory())
    profile = ViewerProfile(mode=mode, language=lang, viewer_id="replay")
    await room.start()
    batches, batch = [], []
    try:
        async for ev in stream(seed, 0):
            batch.append(ev)
            if ev["t"] - batch[0]["t"] >= batch_s or ev["type"] in FLUSH:
                b = await room.process_batch(batch, profile)
                batches.append({"after_event": ev["id"], "payload": {
                    "cards": b.cards, "trace": b.trace, "report": b.report, "index": room.state.index,
                    "phase": room.state.phase, "score": room.state.score, "minute": room.state.minute,
                    "usage": room.ledger.totals(), "orchestrator": room.orchestrator}})
                batch = []
    finally:
        await room.close()
    return {"seed": seed, "mode": mode, "lang": lang, "batch_s": batch_s, "usage": room.ledger.totals(),
            "batches": batches}
