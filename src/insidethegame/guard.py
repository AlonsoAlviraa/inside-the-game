"""Abuse and cost protection for the public demo.

* `RateLimiter`: in-memory sliding windows per client IP (one replica, so in-process state is enough).
* `SpendCap`: a global daily USD cap on Azure OpenAI usage (ITG_DAILY_USD, default 3.00). Every `Brain` call
  checks it; once hit, agents fall back to their deterministic rules path, so the demo keeps working.
* `LLM_ALLOWED`: a per-request context flag. When a client is over its rate limit the request still succeeds,
  but with model calls switched off (rules answers / replay cache), never with an error page.
* Optional `ITG_DEMO_TOKEN`: if set, a request carrying it (header X-Demo-Token or ?token=) bypasses the per-IP
  limits (not the spend cap). Not set in the public deployment; documented for operators."""
from __future__ import annotations
import contextvars
import datetime as dt
import os
import secrets
import time
from collections import defaultdict, deque

LLM_ALLOWED: contextvars.ContextVar[bool] = contextvars.ContextVar("LLM_ALLOWED", default=True)

LIMITS = {  # name: [(max requests, window seconds), ...] per client IP
    "ask": [(10, 60), (60, 3600)],         # /api/ask, /api/agent, /api/report?recap=true
    "live": [(2, 3600)],                   # non-replay /api/stream (live model room)
    "chaos": [(6, 60), (30, 3600)],        # /api/chaos sandbox (CPU only)
}
MAX_LIVE_ROOMS = int(os.getenv("ITG_MAX_LIVE_ROOMS", "2"))


class RateLimiter:
    def __init__(self, limits: dict | None = None):
        self.limits = limits or LIMITS
        self.hits: dict[tuple[str, str], deque] = defaultdict(deque)

    def hit(self, kind: str, key: str, now: float | None = None) -> bool:
        """Record a request; True if within all windows for `kind`."""
        now = time.monotonic() if now is None else now
        q = self.hits[(kind, key)]
        longest = max(w for _, w in self.limits[kind])
        while q and now - q[0] > longest:
            q.popleft()
        for n, w in self.limits[kind]:
            if sum(1 for t in q if now - t <= w) >= n:
                return False
        q.append(now)
        if len(self.hits) > 20000:  # bound memory: drop idle keys
            for k in [k for k, v in self.hits.items() if not v][:5000]:
                del self.hits[k]
        return True


class SpendCap:
    def __init__(self, usd: float | None = None):
        self.cap = float(os.getenv("ITG_DAILY_USD", "3.0")) if usd is None else usd
        self.day = dt.date.today()
        self.spent = 0.0
        self.blocked = 0

    def _roll(self) -> None:
        if dt.date.today() != self.day:
            self.day, self.spent, self.blocked = dt.date.today(), 0.0, 0

    def allow(self, est_usd: float) -> bool:
        self._roll()
        ok = self.spent + est_usd <= self.cap
        if not ok:
            self.blocked += 1
        return ok

    def add(self, usd: float) -> None:
        self._roll()
        self.spent += usd

    def status(self) -> dict:
        self._roll()
        return {"daily_cap_usd": self.cap, "spent_today_usd": round(self.spent, 4),
                "remaining_pct": round(max(0.0, 1 - self.spent / self.cap) * 100, 1) if self.cap else 0.0,
                "calls_blocked_by_cap_today": self.blocked}


LIMITER = RateLimiter()
SPEND = SpendCap()


def client_ip(headers, peer: str | None) -> str:
    """First hop of X-Forwarded-For (set by the Container Apps ingress), else the socket peer."""
    xff = headers.get("x-forwarded-for", "")
    return (xff.split(",")[0].strip() or peer or "unknown")[:64]


def has_demo_token(headers, query) -> bool:
    tok = os.getenv("ITG_DEMO_TOKEN", "")
    given = headers.get("x-demo-token") or query.get("token") or ""
    return bool(tok) and secrets.compare_digest(tok, given)


def new_session_id() -> str:
    return secrets.token_urlsafe(18)
