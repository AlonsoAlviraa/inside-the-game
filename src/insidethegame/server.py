"""FastAPI app: SSE stream of synthetic events + multi-agent commentary, and the static overlay."""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path

import time

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from fastapi.staticfiles import StaticFiles

from .room import localise
from .room import CARD_SCHEMA, CommentaryRoom, ViewerMemory, ViewerProfile

FLUSH = {"goal", "period_end", "match_end"}
from .generator import stream
from . import analyst, insights
from . import league, season, replay, tools_agent
from .teams import LEAGUE_DAYS, LEAGUE_NAME, _POOL, club_list, crest_svg, fixture_list
from . import guard
from .guard import LIMITER, LLM_ALLOWED, SPEND

WEB_DIR = Path(os.getenv("ITG_WEB_DIR", Path(__file__).resolve().parents[2] / "web"))
app = FastAPI(title="Inside the Game - Commentary Room", version="0.1.0")


ROOMS: dict[str, tuple[CommentaryRoom, float]] = {}   # live rooms by server-issued session id -> (room, started)
ROOM_TTL_S = 3 * 3600
VALID_SEEDS = frozenset(f["seed"] for f in fixture_list())
MODES, LANGS = ("fan", "neutral", "analyst"), ("en", "es", "fr")


def _purge_rooms(now: float | None = None) -> None:
    """TTL for live rooms (normally removed when the stream ends or the client disconnects)."""
    now = time.monotonic() if now is None else now
    for k in [k for k, (_, t0) in ROOMS.items() if now - t0 > ROOM_TTL_S]:
        ROOMS.pop(k, None)


def _bad(msg: str) -> JSONResponse:
    return JSONResponse({"error": msg}, status_code=422)


@app.middleware("http")
async def validate_params(request: Request, call_next):
    """Input validation for every API query string: only the published fixtures, personas and languages."""
    if request.url.path.startswith("/api/"):
        q = request.query_params
        if "seed" in q and (not q["seed"].lstrip("-").isdigit() or int(q["seed"]) not in VALID_SEEDS):
            return _bad("unknown match: use a seed from /api/matches")
        if q.get("mode") and q["mode"] not in MODES:
            return _bad(f"mode must be one of {MODES}")
        if q.get("lang") and q["lang"] not in LANGS:
            return _bad(f"lang must be one of {LANGS}")
        if q.get("club") and q["club"] not in _POOL:
            return _bad("unknown club")
        if any(len(q.get(k, "")) > 60 for k in ("player", "viewer", "a", "b", "token")):
            return _bad("parameter too long")
    return await call_next(request)


def _ip(request: Request) -> str:
    return guard.client_ip(request.headers, request.client.host if request.client else None)


def _gate(request: Request, kind: str) -> bool:
    """Per-IP limit for model-backed endpoints. Over the limit => this request runs without model calls."""
    ok = guard.has_demo_token(request.headers, request.query_params) or LIMITER.hit(kind, _ip(request))
    LLM_ALLOWED.set(ok)
    return ok


class _MatchParams(BaseModel):
    @field_validator("seed", check_fields=False)
    @classmethod
    def _seed(cls, v: int) -> int:
        if v not in VALID_SEEDS:
            raise ValueError("unknown match: use a seed from /api/matches")
        return v

    @field_validator("mode", check_fields=False)
    @classmethod
    def _mode(cls, v: str) -> str:
        if v not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        return v

    @field_validator("lang", check_fields=False)
    @classmethod
    def _lang(cls, v: str) -> str:
        if v not in LANGS:
            raise ValueError(f"lang must be one of {LANGS}")
        return v
AGENTS = ("ingest", "interpret", "salience", "explain", "render", "personalise")
_WARM = {"done": False}


@app.on_event("startup")
async def _warm() -> None:
    """Pre-compute the showcase matches and replay caches so the first visitor never waits on a cold start."""
    async def go():
        try:
            for s in replay.SHOWCASE:
                await asyncio.to_thread(insights.events, s)
            await asyncio.to_thread(replay.available)
            _WARM["done"] = True
        except Exception as e:  # never block startup
            _WARM["error"] = repr(e)
    asyncio.create_task(go())


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "warm": _WARM["done"], "llm_provider": os.getenv("ITG_LLM_PROVIDER", "mock"),
            "orchestrator": os.getenv("ITG_ORCHESTRATOR", "maf"), "replay_matches": len(replay.available()),
            "live_rooms": len(ROOMS)}


class ChaosReq(_MatchParams):
    agent: str = Field("explain", description="agent to break: " + ", ".join(AGENTS))
    severity: str = Field("transient", pattern="^(transient|hard)$")
    seed: int = 7
    minute: int = Field(30, ge=1, le=95)
    mode: str = "fan"
    lang: str = "en"
    sid: str | None = Field(None, max_length=40)


_SANDBOX: dict[tuple, dict] = {}


@app.post("/api/chaos")
async def chaos(req: ChaosReq, request: Request) -> dict:
    """Fault injection. With the `sid` of a live stream, arms a failure in that room's next batch (the trace
    arrives with the next cards). Otherwise runs a sandbox room in rules mode (no model calls, zero cost) up to
    `minute`, breaks `agent` on the last batch and returns that batch's trace so the recovery is visible."""
    if req.agent not in AGENTS:
        return {"error": f"unknown agent {req.agent}"}
    if not LIMITER.hit("chaos", _ip(request)):
        return JSONResponse({"error": "too many fault injections from this address; try again in a minute"}, status_code=429)
    _purge_rooms()
    # Live: only the session that owns the stream knows its id (server-issued, 144 random bits).
    live = ROOMS.get(req.sid or "")
    if live is not None:
        live[0].inject_fault(req.agent, req.severity)
        return {"armed": True, "live": True, "agent": req.agent, "severity": req.severity}
    key = (req.agent, req.severity, req.seed, req.minute, req.mode, req.lang)
    if key in _SANDBOX:  # same sandbox run already computed: no CPU spent
        return _SANDBOX[key] | {"cached": True}
    sandbox = CommentaryRoom(req.seed, online=False)
    profile = ViewerProfile(mode=req.mode, language=req.lang)
    evs = [e for e in insights.events(req.seed) if e.get("minute", 0) <= req.minute]
    hot = [i for i, e in enumerate(evs) if e["type"] in ("goal", "shot", "card")]
    if hot:  # end the sandbox on the latest notable moment so the broken batch has something to explain
        evs = evs[:hot[-1] + 1]
    batches, cur = [], []
    for ev in evs:
        cur.append(ev)
        if ev["t"] - cur[0]["t"] >= 300 or ev["type"] in FLUSH:
            batches.append(cur)
            cur = []
    if cur:
        batches.append(cur)
    b = None
    for i, batch in enumerate(batches):
        if i == len(batches) - 1:
            sandbox.inject_fault(req.agent, req.severity)
        b = await sandbox.process_batch(batch, profile)
    out = {"armed": True, "live": False, "agent": req.agent, "severity": req.severity, "minute": sandbox.state.minute,
           "orchestrator": sandbox.orchestrator, "trace": b.trace if b else [],
           "cards": localise.ensure(b.cards, req.lang, req.mode) if b else [], "errors": sandbox.errors[-3:]}
    if len(_SANDBOX) > 500:
        _SANDBOX.clear()
    _SANDBOX[key] = out
    return out


@app.get("/api/match")
async def match(seed: int = 7, meta_only: bool = False) -> dict:
    """Full synthetic match as JSON (for batch analysis / recaps); `meta_only` returns just the line-ups."""
    evs = insights.events(seed)
    return {"synthetic": True, "events": [evs[0]] if meta_only else list(evs)}


@app.get("/api/stream")
async def sse(seed: int = 7, speed: float = Query(60.0, ge=0, le=5000), mode: str = "fan",
              lang: str = "en", club: str | None = None, player: str | None = None, viewer: str = "anonymous",
              batch_s: float = Query(float(os.getenv("ITG_BATCH_S", "300")), ge=30, le=900), replay_mode: bool = Query(False, alias="replay"),
              request: Request = None):
    """SSE: `tick` per raw event (pitch/score), `cards` per agent batch (overlay cards + agent trace + usage).
    Events are batched per `batch_s` match-seconds (flushed early on goals and period ends) so the room makes
    a handful of LLM calls per batch and stays under the deployment's tokens-per-minute quota.

    Live (non-replay) model rooms are the expensive path: at most ITG_MAX_LIVE_ROOMS at once and 2 per hour per
    IP (a demo token bypasses the per-IP limit). Over the limit the viewer gets the cached replay when one
    exists, otherwise the same room in rules mode (no model calls), and a `notice` event says why."""
    notice = None
    _purge_rooms()
    if not (replay_mode and replay.load(seed, mode, lang)):
        busy = len(ROOMS) >= guard.MAX_LIVE_ROOMS
        if busy or not _gate(request, "live"):
            notice = ("All live AI rooms are busy" if busy else "Live AI limit for your address reached (2 per hour)")
            LLM_ALLOWED.set(False)
            if replay.load(seed, mode, lang):
                replay_mode, notice = True, notice + ": showing the precomputed AI commentary instead."
            else:
                notice += ": commentary runs in rules mode (no model calls)."
    cached = replay.load(seed, mode, lang) if replay_mode else None
    if cached:
        return StreamingResponse(_replay_gen(cached, seed, speed, club or None, player or None, notice), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    online = LLM_ALLOWED.get() and None  # None = Azure if configured; False = rules mode
    sid = guard.new_session_id()
    memory = ViewerMemory()
    profile = memory.fill_defaults(ViewerProfile(mode=mode, language=lang, club=club or None,
                                                 player=player or None, viewer_id=viewer))
    memory.remember_profile(profile)
    room = CommentaryRoom(seed, memory=memory, online=online)
    if online is None:
        ROOMS[sid] = (room, time.monotonic())

    async def gen():
        yield f"event: session\ndata: {json.dumps({'sid': sid if online is None else None, 'live_ai': online is None, 'notice': notice})}\n\n"
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
                await q_out.put({"cards": localise.ensure(b.cards, profile.language, profile.mode), "trace": b.trace, "report": b.report, "index": room.state.index,
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
            task.cancel()  # also runs on client disconnect (generator closed)
            ROOMS.pop(sid, None)
            memory.save()
            await room.close()
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def _replay_gen(cached: dict, seed: int, speed: float, club: str | None, player: str | None, notice: str | None = None):
    """Replay: same event clock as live, cached AI batches released right after the event that closed them."""
    yield f"event: session\ndata: {json.dumps({'sid': None, 'live_ai': False, 'replay': True, 'notice': notice})}\n\n"
    by_ev = {b["after_event"]: b["payload"] for b in cached["batches"]}
    score: dict = {}
    async for ev in stream(seed, speed):
        if ev["type"] == "goal" and ev.get("score"):
            score = ev["score"]
        yield f"event: tick\ndata: {json.dumps({'event': ev, 'score': score or None, 'index': None})}\n\n"
        if ev["id"] in by_ev:
            yield f"event: cards\ndata: {json.dumps(replay.personalise(by_ev[ev['id']], club, player), default=str)}\n\n"
    yield "event: end\ndata: {}\n\n"


@app.get("/api/replay")
async def replay_index() -> dict:
    """Which (match, persona, language) combinations have precomputed AI commentary."""
    return {"showcase": list(replay.SHOWCASE), "available": replay.available()}


@app.get("/api/matches")
async def matches() -> dict:
    """Selectable synthetic fixtures (fictional clubs)."""
    return {"synthetic": True, "matches": fixture_list()}


@app.get("/api/report")
async def report(seed: int = 7, minute: int = Query(200, ge=0, le=200), format: str = "json", recap: bool = False,
                 lang: str = "en", request: Request = None):
    """Team/player stats, momentum, key moments; `format=md` returns an exportable Markdown report.
    `recap=true` adds a grounded LLM recap (checked by numbers + semantic guards, rules fallback)."""
    r = insights.report(seed, minute)
    if recap:
        _gate(request, "ask")
    rc = await analyst.recap(seed, minute, lang) if recap else None
    if format == "md":
        return PlainTextResponse(insights.report_markdown(r, rc["text"] if rc else None), media_type="text/markdown",
                                 headers={"Content-Disposition": f'attachment; filename="match-{seed}-report.md"'})
    return {**r, "recap": rc}


class Question(_MatchParams):
    seed: int = 7
    question: str = Field(min_length=1, max_length=300)
    minute: int = Field(200, ge=0, le=200)
    lang: str = "en"


@app.post("/api/ask")
async def ask(q: Question, request: Request) -> dict:
    """Ask-the-analyst: grounded Q&A over the match so far (only facts up to `minute`, so no spoilers).
    Rate limited per IP; over the limit (or over the daily AI spend cap) the answer comes from the rules path."""
    limited = not _gate(request, "ask")
    return await analyst.ask(q.seed, q.question, q.minute, q.lang) | ({"limited": "rate limit: rules answer"} if limited else {})


class AgentQ(_MatchParams):
    seed: int = 7
    question: str = Field(min_length=1, max_length=300)
    minute: int = Field(200, ge=0, le=200)


@app.post("/api/agent")
async def agent_ask(q: AgentQ, request: Request) -> dict:
    """Ask with tools: planner -> critic -> tool calls -> critic -> answer + pitch highlights + full trace."""
    limited = not _gate(request, "ask")
    return await tools_agent.ask(q.seed, q.question, q.minute) | ({"limited": "rate limit: rules planner"} if limited else {})


def _cached_card(seed: int, mode: str, lang: str, card_id: str) -> dict | None:
    c = replay.load(seed, mode, lang)
    if not c:
        return None
    for b in c["batches"]:
        for card in b["payload"]["cards"]:
            if card.get("id") == card_id:
                return card
    return None


@app.get("/api/perspectives")
async def perspectives(seed: int = 7, minute: int = Query(200, ge=1, le=200), lang: str = "en") -> dict:
    """Same moment, three viewers: the Personalise agent's output for fan, neutral and analyst side by side.
    Showcase matches use the precomputed (real model) commentary; other matches run a rules-mode sandbox room (no cost)."""
    evs = insights.events(seed)
    key = [e for e in evs if e["type"] in ("goal", "card", "shot") and e["minute"] <= minute and (e["type"] != "shot" or e["xg"] >= 0.15)]
    key = [e for e in key if e["type"] == "goal"] or key
    if not key:
        return {"event": None, "modes": {}}
    ev = key[-1]
    cid = f"ev{ev['id']}"
    out = {}
    for mode in replay.MODES:
        card, source = _cached_card(seed, mode, lang, cid), "precomputed AI (replay cache)"
        if card is None:
            room = CommentaryRoom(seed, online=False)
            profile = ViewerProfile(mode=mode, language=lang)
            batch, cards = [], []
            for e in evs:
                if e["id"] > ev["id"]:
                    break
                batch.append(e)
                if e["t"] - batch[0]["t"] >= 300 or e["type"] in FLUSH or e["id"] == ev["id"]:
                    cards += (await room.process_batch(batch, profile)).cards
                    batch = []
            cards = localise.ensure(cards, lang, mode)
            card = next((c for c in cards if c.get("id") == cid), cards[0] if cards else None)
            source = "rules-mode sandbox room"
        if card:
            out[mode] = {"title": card.get("title"), "text": card.get("text"), "priority": card.get("priority"),
                         "source": source + (" · LLM" if "llm" in str(card.get("source")) else ""), "facts": {k: v for k, v in (card.get("facts") or {}).items() if k in ("xg", "phase", "score", "player_match_xg")}}
    return {"event": {k: ev.get(k) for k in ("id", "type", "minute", "player", "team", "xg", "outcome", "card")}, "modes": out}


@app.get("/api/reel")
async def reel(seed: int = 7, mode: str = "fan", lang: str = "en", limit: int = Query(8, ge=1, le=12)) -> dict:
    """Condensed match: the key moments with their build-up (last passes before each), plus caption text from the
    commentary cache when available. The client animates it on the pitch in about 60 seconds."""
    evs = insights.events(seed)
    meta = evs[0]["meta"]
    km = insights.key_moments(list(evs), meta)
    goals = [m for m in km if m["kind"] == "goal"]
    big = sorted([m for m in km if m["kind"] != "goal" and m["importance"] >= 4], key=lambda m: -(m.get("xg") or 0.5))
    tp = sorted([m for m in km if m["kind"] == "threat_pass"], key=lambda m: -m["xt"])[:2]
    pick = sorted((goals + big + tp)[:limit], key=lambda m: m["event_id"])
    by_id = {e["id"]: i for i, e in enumerate(evs)}
    clips = []
    for m in pick:
        i = by_id[m["event_id"]]
        j, build = i, []
        while j > 0 and len(build) < 6:
            e = evs[j]
            if e["type"] in ("pass", "shot", "goal", "foul") or e["id"] == m["event_id"]:
                build.append(e)
            if e["type"] in ("possession_start", "turnover", "period_start") and e["id"] != m["event_id"]:
                break
            j -= 1
        cid = f"ev{m['event_id']}"
        card = _cached_card(seed, mode, lang, cid) if seed in replay.SHOWCASE else None
        clips.append({"moment": m, "events": [{k: v for k, v in e.items() if k != "meta"} for e in reversed(build)],
                      "caption": card["text"] if card else m["label"], "title": card["title"] if card else m["label"],
                      "ai": bool(card and "llm" in str(card.get("source")))})
    end = next((e for e in reversed(evs) if e["type"] == "match_end"), None)
    return {"seed": seed, "home": {k: meta["home"][k] for k in ("id", "name", "short", "color")},
            "away": {k: meta["away"][k] for k in ("id", "name", "short", "color")}, "score": end["score"] if end else {}, "clips": clips}


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
    """Aggregated only (no per-agent or per-user detail): today's AI spend against the daily cap."""
    u = analyst.usage()
    return {"ai_spend": SPEND.status(), "analyst_desk": {"calls": u["calls"], "usd": u["usd"]},
            "limits_per_ip": {k: [f"{n}/{w}s" for n, w in v] for k, v in guard.LIMITS.items()}, "max_live_rooms": guard.MAX_LIVE_ROOMS}


@app.get("/api/card-schema")
async def card_schema() -> dict:
    return CARD_SCHEMA


@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html")


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
