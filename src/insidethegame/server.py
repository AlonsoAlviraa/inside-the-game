"""FastAPI app: SSE stream of synthetic events + multi-agent commentary, and the static overlay."""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .room import CARD_SCHEMA, CommentaryRoom, ViewerMemory, ViewerProfile

FLUSH = {"goal", "period_end", "match_end"}
from .generator import MatchGenerator, stream

WEB_DIR = Path(os.getenv("ITG_WEB_DIR", Path(__file__).resolve().parents[2] / "web"))
app = FastAPI(title="Inside the Game - Commentary Room", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "llm_provider": os.getenv("ITG_LLM_PROVIDER", "mock"),
            "orchestrator": os.getenv("ITG_ORCHESTRATOR", "maf")}


@app.get("/api/match")
async def match(seed: int = 7) -> dict:
    """Full synthetic match as JSON (for batch analysis / recaps)."""
    return {"synthetic": True, "events": list(MatchGenerator(seed).events())}


@app.get("/api/stream")
async def sse(seed: int = 7, speed: float = Query(60.0, ge=0, le=5000), mode: str = "fan",
              lang: str = "en", club: str | None = None, player: str | None = None, viewer: str = "anonymous",
              batch_s: float = Query(float(os.getenv("ITG_BATCH_S", "300")), ge=30, le=900)):
    """SSE: `tick` per raw event (pitch/score), `cards` per agent batch (overlay cards + agent trace + usage).
    Events are batched per `batch_s` match-seconds (flushed early on goals and period ends) so the room makes
    a handful of LLM calls per batch and stays under the deployment's tokens-per-minute quota."""
    memory = ViewerMemory()
    profile = memory.fill_defaults(ViewerProfile(mode=mode, language=lang, club=club or None,
                                                 player=player or None, viewer_id=viewer))
    memory.remember_profile(profile)
    room = CommentaryRoom(seed, memory=memory)

    async def gen():
        # Raw events keep flowing at match speed; batches are handed to a single background worker so LLM
        # latency never stalls the pitch. Cards are emitted (in order) as soon as each batch finishes.
        await room.start()
        q_in: asyncio.Queue = asyncio.Queue()
        q_out: asyncio.Queue = asyncio.Queue()

        async def worker():
            while (batch := await q_in.get()) is not None:
                b = await room.process_batch(batch, profile)
                await q_out.put({"cards": b.cards, "trace": b.trace, "report": b.report, "index": room.state.index,
                                 "phase": room.state.phase, "score": room.state.score, "minute": room.state.minute,
                                 "usage": room.ledger.totals(), "orchestrator": room.orchestrator})
            await q_out.put(None)

        task = asyncio.create_task(worker())

        def drain():
            out = []
            while not q_out.empty():
                out.append(q_out.get_nowait())
            return out
        try:
            batch: list[dict] = []
            async for ev in stream(seed, speed):
                batch.append(ev)
                tick = {"event": ev, "score": room.state.score or None, "index": room.state.index}
                yield f"event: tick\ndata: {json.dumps(tick)}\n\n"
                if ev["t"] - batch[0]["t"] >= batch_s or ev["type"] in FLUSH:
                    await q_in.put(batch)
                    batch = []
                for out in drain():
                    if out:
                        yield f"event: cards\ndata: {json.dumps(out, default=str)}\n\n"
            if batch:
                await q_in.put(batch)
            await q_in.put(None)
            while (out := await q_out.get()) is not None:
                yield f"event: cards\ndata: {json.dumps(out, default=str)}\n\n"
        finally:
            task.cancel()
            memory.save()
            await room.close()
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/card-schema")
async def card_schema() -> dict:
    return CARD_SCHEMA


@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html")


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
