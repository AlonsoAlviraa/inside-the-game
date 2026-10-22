"""Impact numbers measured on our own artefacts (no market statistics): AI cost per match, agent latency per
batch, coverage (languages, personas) and how often the guards replaced AI text. Source: the precomputed
replay caches (real gpt-4.1-mini runs) in src/insidethegame/data/replay/. Writes evals/impact_metrics.json.
Usage: python scripts/measure_impact.py"""
import json
import statistics
from pathlib import Path

from insidethegame import replay


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))] if xs else None


def main():
    runs = replay.available()
    usd, calls, batch_ms, cards, ai_cards, langs, modes = [], [], [], 0, 0, set(), set()
    for a in runs:
        d = replay.load(a["seed"], a["mode"], a["lang"])
        langs.add(a["lang"])
        modes.add(a["mode"])
        usd.append(d["usage"]["usd"])
        calls.append(d["usage"]["calls"])
        for b in d["batches"]:
            batch_ms.append(sum(t.get("ms") or 0 for t in b["payload"]["trace"]))
            for c in b["payload"]["cards"]:
                cards += 1
                ai_cards += "llm" in str(c.get("source")) or "personalised" in str(c.get("source"))
    out = {
        "source": f"{len(runs)} precomputed full-match AI runs (replay caches, gpt-4.1-mini on Azure OpenAI)",
        "matches_measured": len(runs),
        "ai_cost_usd_per_match": {"mean": round(statistics.mean(usd), 4), "max": round(max(usd), 4)},
        "model_calls_per_match": {"mean": round(statistics.mean(calls), 1), "max": max(calls)},
        "agent_latency_ms_per_batch": {"p50": round(pct(batch_ms, .5)), "p95": round(pct(batch_ms, .95)), "n": len(batch_ms)},
        "cards_per_match": round(cards / len(runs), 1),
        "share_of_cards_with_ai_text": round(ai_cards / cards, 3),
        "languages": sorted(langs), "personas": sorted(modes),
        "batch_match_seconds": sorted({replay.load(a["seed"], a["mode"], a["lang"])["batch_s"] for a in runs}),
        "note": "Latency is model + agent time per batch of match events; the instant data caption is shown first, so the viewer never waits on it.",
    }
    Path("evals/impact_metrics.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
