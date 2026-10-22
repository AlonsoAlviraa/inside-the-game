"""LLM access for the five agents: Microsoft Agent Framework `Agent`s on Azure OpenAI (gpt-4.1-mini).

* One MAF Agent per role (own instructions, own tools).
* `TokenBudget` keeps the room under the deployment's tokens-per-minute quota (ITG_TPM_LIMIT, default 9000
  for a 10K TPM deployment): if a call would exceed it, the agent uses its deterministic fallback instead.
* `UsageLedger` accumulates real token usage per agent for cost reporting.
"""
from __future__ import annotations
import asyncio
import json
import os
import re
import time
from collections import deque, defaultdict

# Azure OpenAI gpt-4.1-mini list price (USD per 1M tokens, global standard). Override via env if it changes.
PRICE_IN = float(os.getenv("ITG_PRICE_IN_PER_M", "0.40"))
PRICE_OUT = float(os.getenv("ITG_PRICE_OUT_PER_M", "1.60"))


class TokenBudget:
    """Client-side rate limiter mirroring Azure's quota enforcement: Azure counts prompt + max_tokens and
    evaluates TPM over short (~10 s) windows, so we cap both the 60 s total (tpm) and each 10 s slice (default tpm/4, ITG_TPM_SLICE)."""

    def __init__(self, tpm: int | None = None, max_wait_s: float = 9.0):
        self.tpm = tpm or int(os.getenv("ITG_TPM_LIMIT", "9000"))
        self.short = int(os.getenv("ITG_TPM_SLICE", self.tpm // 4))
        self.max_wait = max_wait_s
        self.window: deque[tuple[float, int]] = deque()

    def _used(self, horizon: float) -> int:
        now = time.monotonic()
        while self.window and now - self.window[0][0] > 60:
            self.window.popleft()
        return sum(n for t, n in self.window if now - t <= horizon)

    def used(self) -> int:
        return self._used(60)

    def allow(self, est: int) -> bool:
        return self._used(60) + est <= self.tpm and (self._used(10) + est <= self.short or self._used(10) == 0)

    async def acquire(self, est: int) -> bool:
        """Wait (up to max_wait) for room in the window; False => caller should fall back."""
        waited = 0.0
        while not self.allow(est):
            if waited >= self.max_wait:
                return False
            await asyncio.sleep(0.5)
            waited += 0.5
        self.add(est)  # reserve now; reconciled after the call
        return True

    def add(self, n: int) -> None:
        self.window.append((time.monotonic(), n))

    def reconcile(self, reserved: int, actual: int) -> None:
        for i in range(len(self.window) - 1, -1, -1):
            if self.window[i][1] == reserved:
                self.window[i] = (self.window[i][0], max(actual, 1))
                break


class UsageLedger:
    def __init__(self):
        self.by_agent = defaultdict(lambda: {"calls": 0, "input": 0, "output": 0, "skipped_budget": 0,
                                             "errors": 0, "tool_calls": 0})

    def totals(self) -> dict:
        i = sum(a["input"] for a in self.by_agent.values())
        o = sum(a["output"] for a in self.by_agent.values())
        return {"input_tokens": i, "output_tokens": o, "calls": sum(a["calls"] for a in self.by_agent.values()),
                "usd": round(i / 1e6 * PRICE_IN + o / 1e6 * PRICE_OUT, 5), "by_agent": dict(self.by_agent)}


def azure_enabled() -> bool:
    return os.getenv("ITG_LLM_PROVIDER", "mock").lower() == "azure" and bool(os.getenv("AZURE_OPENAI_ENDPOINT"))


def make_chat_client():
    from agent_framework.openai import OpenAIChatCompletionClient
    kw = dict(model=os.environ["AZURE_OPENAI_DEPLOYMENT"], azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
              api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"))
    if os.getenv("AZURE_OPENAI_API_KEY"):
        kw["api_key"] = os.environ["AZURE_OPENAI_API_KEY"]
    else:
        from azure.identity import DefaultAzureCredential
        kw["credential"] = DefaultAzureCredential()
    return OpenAIChatCompletionClient(**kw)


class Brain:
    """A role-specific MAF Agent plus budget/usage/timeout handling. `agent=None` => offline mode."""

    def __init__(self, name: str, instructions: str, client=None, tools=None, budget: TokenBudget | None = None,
                 ledger: UsageLedger | None = None, max_tokens: int = 300, timeout_s: float = 25.0):
        self.name, self.instructions = name, instructions
        self.budget, self.ledger = budget or TokenBudget(), ledger or UsageLedger()
        self.max_tokens, self.timeout = max_tokens, timeout_s
        self.agent = None
        if client is not None:
            from agent_framework import Agent
            self.agent = Agent(client, instructions, name=name, tools=tools or None,
                               default_options={"temperature": 0.4, "max_tokens": max_tokens})

    @property
    def online(self) -> bool:
        return self.agent is not None

    async def ask(self, prompt: str, entry: dict | None = None, est_extra: int = 0) -> str | None:
        """Return model text, or None when offline / over budget / failed (caller falls back)."""
        if self.agent is None:
            return None
        from ..guard import LLM_ALLOWED, SPEND
        stats = self.ledger.by_agent[self.name]
        est = (len(self.instructions) + len(prompt)) // 3 + self.max_tokens + est_extra
        if not LLM_ALLOWED.get():
            stats["skipped_limit"] = stats.get("skipped_limit", 0) + 1
            if entry is not None:
                entry["llm"] = "skipped (rate limit: rules fallback)"
            return None
        if not SPEND.allow(est / 1e6 * PRICE_OUT):
            stats["skipped_cap"] = stats.get("skipped_cap", 0) + 1
            if entry is not None:
                entry["llm"] = "skipped (daily AI spend cap: rules fallback)"
            return None
        if not await self.budget.acquire(est):
            stats["skipped_budget"] += 1
            if entry is not None:
                entry["llm"] = "skipped (TPM budget)"
            return None
        try:
            r = await asyncio.wait_for(self.agent.run(prompt), self.timeout)
        except Exception as e:
            stats["errors"] += 1
            if entry is not None:
                entry["llm"] = f"error: {type(e).__name__}"
            return None
        u = getattr(r, "usage_details", None) or {}
        ti, to = int(u.get("input_token_count") or 0), int(u.get("output_token_count") or 0)
        tools = sum(1 for m in r.messages for c in m.contents if getattr(c, "type", "") == "function_call")
        SPEND.add(ti / 1e6 * PRICE_IN + to / 1e6 * PRICE_OUT if ti else est / 1e6 * PRICE_OUT)
        stats["calls"] += 1
        stats["input"] += ti
        stats["output"] += to
        stats["tool_calls"] += tools
        self.budget.reconcile(est, ti + self.max_tokens if ti else est)
        if entry is not None:
            entry.update({"llm": "azure", "tokens_in": ti, "tokens_out": to, "tool_calls": tools})
        return (r.text or "").strip() or None


def parse_json(text: str | None):
    if not text:
        return None
    m = re.search(r"\{.*\}|\[.*\]", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None
