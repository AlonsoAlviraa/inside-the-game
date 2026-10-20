"""FastAPI app: SSE stream of synthetic events + multi-agent commentary, and the static overlay."""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles

from .room import CARD_SCHEMA, CommentaryRoom, ViewerMemory, ViewerProfile

FLUSH = {"goal", "period_end", "match_end"}
from .generator import MatchGenerator, stream
from . import analyst, insights
from . import league, season
from .teams import LEAGUE_DAYS, LEAGUE_NAME, _POOL, club_list, crest_svg, fixture_list

WEB_DIR = Path(os.getenv("ITG_WEB_DIR", Path(__file__).resolve().parents[2] / "web"))
app = FastAPI(title="Inside the Game - Commentary Room", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "llm_provider": os.getenv("ITG_LLM_PROVIDER", "mock"),
            "orchestrator": os.getenv("ITG_ORCHESTRATOR", "maf")}


@app.get("/api/match")
async def match(seed: int = 7, meta_only: bool = False) -> dict:
    """Full synthetic match as JSON (for batch analysis / recaps); `meta_only` returns just the line-ups."""
    evs = insights.events(seed)
    return {"synthetic": True, "events": [evs[0]] if meta_only else list(evs)}


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
            done = False
            while not done and (batch := await q_in.get()) is not None:
                # backpressure: if the model fell behind, merge queued batches into one (fewer LLM calls)
                while not q_in.empty():
                    nxt = q_in.get_nowait()
                    if nxt is None:
                        done = True
                        break
                    batch = batch + nxt
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


@app.get("/api/matches")
async def matches() -> dict:
    """Selectable synthetic fixtures (fictional clubs)."""
    return {"synthetic": True, "matches": fixture_list()}


@app.get("/api/report")
async def report(seed: int = 7, minute: int = Query(200, ge=0, le=200), format: str = "json", recap: bool = False,
                 lang: str = "en"):
    """Team/player stats, momentum, key moments; `format=md` returns an exportable Markdown report.
    `recap=true` adds a grounded LLM recap (checked by numbers + semantic guards, rules fallback)."""
    r = insights.report(seed, minute)
    rc = await analyst.recap(seed, minute, lang) if recap else None
    if format == "md":
        return PlainTextResponse(insights.report_markdown(r, rc["text"] if rc else None), media_type="text/markdown",
                                 headers={"Content-Disposition": f'attachment; filename="match-{seed}-report.md"'})
    return {**r, "recap": rc}


class Question(BaseModel):
    seed: int = 7
    question: str = Field(min_length=1, max_length=300)
    minute: int = Field(200, ge=0, le=200)
    lang: str = "en"


@app.post("/api/ask")
async def ask(q: Question) -> dict:
    """Ask-the-analyst: grounded Q&A over the match so far (only facts up to `minute`, so no spoilers)."""
    return await analyst.ask(q.seed, q.question, q.minute, q.lang)


@app.get("/api/league")
async def league_view(day: int = Query(LEAGUE_DAYS, ge=1, le=LEAGUE_DAYS)) -> dict:
    """Fictional league: clubs, table after `day` (with position moves), leaders, positions over time, fixtures."""
    fx = fixture_list()
    for f in fx:
        if f["seed"] >= 1000:
            f["score"] = league.result(f["seed"])["score"]
    return {"synthetic": True, "name": LEAGUE_NAME, "day": day, "days": LEAGUE_DAYS, "clubs": club_list(),
            "table": season.table_with_moves(day), "leaders": season.leaders(day),
            "positions": season.positions_over_time(day), "fixtures": fx}


@app.get("/api/team/{club}")
async def team_page(club: str, day: int = Query(LEAGUE_DAYS, ge=1, le=LEAGUE_DAYS)) -> dict:
    """Club page: season stats, squad stats, results and fixtures (league matches up to `day`)."""
    if club not in _POOL:
        return PlainTextResponse("unknown club", status_code=404)
    info = next(c for c in club_list() if c["id"] == club)
    pos = next(r for r in season.table(day) if r["id"] == club)
    games = [{"seed": f["seed"], "matchday": f["matchday"], "home": f["home_id"], "away": f["away_id"],
              "score": league.result(f["seed"])["score"] if f["matchday"] <= day else None}
             for f in fixture_list() if f["seed"] >= 1000 and club in (f["home_id"], f["away_id"])]
    return {"synthetic": True, "club": info, "standing": pos, "season": season.team_season(club, day),
            "matches": sorted(games, key=lambda g: g["matchday"])}


@app.get("/api/crest/{club}.svg")
async def crest(club: str):
    if club not in _POOL:
        return PlainTextResponse("unknown club", status_code=404)
    return Response(crest_svg(club), media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/preview")
async def preview(seed: int = 7) -> dict:
    """Pre-match preview: table position & form, synthetic head-to-head archive, line-ups, pre-match probabilities."""
    return league.preview(seed)


@app.get("/api/winprob")
async def winprob(seed: int = 7) -> dict:
    """Live win probability per minute (Poisson on prior + observed xG rate; each point uses only past events)."""
    return {"model": "poisson(prior+xG rate)", "series": league.win_probability(seed)}


@app.get("/api/formation")
async def formation(seed: int = 7, minute: int = Query(200, ge=0, le=200)) -> dict:
    return league.formation(seed, minute)


@app.get("/api/compare")
async def compare(seed: int, a: str, b: str, minute: int = Query(200, ge=0, le=200)) -> dict:
    return league.compare(seed, a, b, minute)


@app.get("/api/usage")
async def usage() -> dict:
    return {"analyst_desk": analyst.usage()}


@app.get("/api/card-schema")
async def card_schema() -> dict:
    return CARD_SCHEMA


@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html")


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
