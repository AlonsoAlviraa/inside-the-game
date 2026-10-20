"""Azure AI Content Safety (text:analyze) on AI-written lines. Enabled with ITG_CONTENT_SAFETY=1; uses the same
Azure AI Services resource as Azure OpenAI (AZURE_CONTENT_SAFETY_ENDPOINT/KEY override). A line whose Hate, SelfHarm,
Sexual or Violence severity reaches ITG_SAFETY_MAX (default 2) is replaced by the deterministic rules line.
Fails open to the rules line, never to unchecked AI text, when the service errors."""
from __future__ import annotations
import asyncio
import os

API = "2024-09-01"


def enabled() -> bool:
    return os.getenv("ITG_CONTENT_SAFETY", "0") == "1" and bool(_endpoint() and _key())


def _endpoint() -> str:
    return (os.getenv("AZURE_CONTENT_SAFETY_ENDPOINT") or os.getenv("AZURE_OPENAI_ENDPOINT") or "").rstrip("/")


def _key() -> str:
    return os.getenv("AZURE_CONTENT_SAFETY_KEY") or os.getenv("AZURE_OPENAI_API_KEY") or ""


async def analyze(texts: list[str]) -> list[dict | None]:
    """Per text: {category: severity} or None on error."""
    import httpx
    async with httpx.AsyncClient(timeout=10) as cl:
        async def one(t: str):
            try:
                r = await cl.post(f"{_endpoint()}/contentsafety/text:analyze?api-version={API}",
                                  headers={"Ocp-Apim-Subscription-Key": _key()}, json={"text": t[:1000]})
                r.raise_for_status()
                return {c["category"]: c["severity"] for c in r.json()["categoriesAnalysis"]}
            except Exception:
                return None
        return list(await asyncio.gather(*(one(t) for t in texts)))


def safe(result: dict | None) -> bool:
    return result is not None and max(result.values() or [0]) < int(os.getenv("ITG_SAFETY_MAX", "2"))
