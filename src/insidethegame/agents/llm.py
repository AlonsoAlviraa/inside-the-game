"""LLM client abstraction: Azure AI Foundry (OpenAI-compatible) or a deterministic local mock.

Config (env vars, never committed):
  ITG_LLM_PROVIDER = mock | azure          (default: mock)
  AZURE_OPENAI_ENDPOINT                    e.g. https://<resource>.openai.azure.com/
  AZURE_OPENAI_DEPLOYMENT                  model deployment name, e.g. gpt-4.1-mini
  AZURE_OPENAI_API_VERSION                 default 2024-10-21
  AZURE_OPENAI_API_KEY                     optional; if absent, DefaultAzureCredential (managed identity) is used
"""
from __future__ import annotations
import os
from typing import Protocol


class LLMClient(Protocol):
    name: str

    async def complete(self, system: str, user: str, *, fallback: str = "") -> str: ...


class MockLLM:
    """Offline fallback: returns the deterministic template text the agent supplies."""
    name = "mock"

    async def complete(self, system: str, user: str, *, fallback: str = "") -> str:
        return fallback or user


class AzureFoundryLLM:
    name = "azure"

    def __init__(self) -> None:
        from openai import AsyncAzureOpenAI  # optional dependency: pip install .[azure]
        endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
        self.deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]
        version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
        key = os.getenv("AZURE_OPENAI_API_KEY")
        if key:
            self.client = AsyncAzureOpenAI(azure_endpoint=endpoint, api_key=key, api_version=version)
        else:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider
            tp = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")
            self.client = AsyncAzureOpenAI(azure_endpoint=endpoint, azure_ad_token_provider=tp, api_version=version)

    async def complete(self, system: str, user: str, *, fallback: str = "") -> str:
        r = await self.client.chat.completions.create(
            model=self.deployment, temperature=0.6, max_tokens=120,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return (r.choices[0].message.content or fallback).strip()


class ResilientLLM:
    """Wraps a primary client; on any error/timeout falls back to the mock (failure recovery)."""

    def __init__(self, primary: LLMClient, timeout_s: float = 4.0):
        self.primary, self.fallback_client, self.timeout = primary, MockLLM(), timeout_s
        self.name = f"{primary.name}+fallback"
        self.failures = 0

    async def complete(self, system: str, user: str, *, fallback: str = "") -> str:
        import asyncio
        try:
            return await asyncio.wait_for(self.primary.complete(system, user, fallback=fallback), self.timeout)
        except Exception:
            self.failures += 1
            return await self.fallback_client.complete(system, user, fallback=fallback)


def make_llm() -> LLMClient:
    if os.getenv("ITG_LLM_PROVIDER", "mock").lower() == "azure":
        try:
            return ResilientLLM(AzureFoundryLLM())
        except Exception:
            return MockLLM()
    return MockLLM()
