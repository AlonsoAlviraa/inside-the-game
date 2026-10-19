"""FastAPI app: SSE stream of synthetic events + multi-agent commentary, and the static overlay."""
from __future__ import annotations
import json
import os
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .agents import CommentaryRoom, ViewerProfile
from .generator import MatchGenerator, stream

WEB_DIR = Path(os.getenv("ITG_WEB_DIR", Path(__file__).resolve().parents[2] / "web"))
app = FastAPI(title="Inside the Game - Commentary Room", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "llm_provider": os.getenv("ITG_LLM_PROVIDER", "mock")}


@app.get("/api/match")
async def match(seed: int = 7) -> dict:
    """Full synthetic match as JSON (for batch analysis / recaps)."""
    return {"synthetic": True, "events": list(MatchGenerator(seed).events())}


@app.get("/api/stream")
async def sse(seed: int = 7, speed: float = Query(60.0, ge=0, le=5000), mode: str = "fan",
              lang: str = "en", club: str | None = None, player: str | None = None):
    profile = ViewerProfile(mode=mode, language=lang, club=club or None, player=player or None)
    room = CommentaryRoom()

    async def gen():
        async for ev in stream(seed, speed):
            commentary = await room.process(ev, profile)
            payload = {"event": ev, "commentary": commentary, "index": room.state.index,
                       "score": room.state.score}
            yield f"event: tick\ndata: {json.dumps(payload)}\n\n"
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html")


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
