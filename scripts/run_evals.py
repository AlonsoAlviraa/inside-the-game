"""Microsoft Foundry evaluations (azure-ai-evaluation SDK) on the precomputed AI commentary.

For a sample of AI-written lines from data/replay/ (all showcase matches, personas, languages) we score:
  * Groundedness (response vs the card's facts = the only context the agents had),
  * Relevance (does the line address the moment), Fluency,
with gpt-4.1-mini as the judge (1-5 scale, pass threshold 3), and run every line through Azure AI Content Safety.
Writes evals/results.json (per-line) and evals/summary.json.  Usage: python scripts/run_evals.py [n_per_file]"""
import asyncio, json, os, random, statistics, sys
from azure.ai.evaluation import AzureOpenAIModelConfiguration, FluencyEvaluator, GroundednessEvaluator, RelevanceEvaluator
from insidethegame import replay
from insidethegame.room import safety

N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
MODE_Q = {"fan": "a supporter", "neutral": "a casual neutral viewer", "analyst": "a tactics analyst"}
LANG = {"en": "English", "es": "Spanish", "fr": "French"}


def sample():
    rnd, rows = random.Random(7), []
    for a in replay.available():
        d = replay.load(a["seed"], a["mode"], a["lang"])
        cards = [c for b in d["batches"] for c in b["payload"]["cards"] if "llm" in str(c["source"]) or "personalised" in str(c["source"])]
        for c in rnd.sample(cards, min(N, len(cards))):
            facts = {k: v for k, v in c.get("facts", {}).items() if k != "teams"}
            rows.append({**a, "id": c["id"], "type": c["type"], "source": c["source"], "response": c["text"],
                         "context": json.dumps(facts, ensure_ascii=False),
                         "query": f"Write one live commentary line in {LANG[a['lang']]} for {MODE_Q[a['mode']]} "
                                  f"about this {c['type']} moment at minute {c['minute']}."})
    return rows


def main():
    cfg = AzureOpenAIModelConfiguration(azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"], api_key=os.environ["AZURE_OPENAI_API_KEY"],
                                        azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini"), api_version="2024-10-21")
    ev = {"groundedness": GroundednessEvaluator(cfg), "relevance": RelevanceEvaluator(cfg), "fluency": FluencyEvaluator(cfg)}
    rows = sample()
    saf = asyncio.run(safety.analyze([r["response"] for r in rows]))
    for r, s in zip(rows, saf):
        r["content_safety"] = s
        for k, e in ev.items():
            args = {"response": r["response"]}
            if k != "fluency":
                args["query"] = r["query"]
            if k == "groundedness":
                args["context"] = r["context"]
            try:
                out = e(**args)
                r[k], r[k + "_reason"] = out.get(k), out.get(k + "_reason")
            except Exception as x:
                r[k], r[k + "_reason"] = None, f"error: {x}"[:200]
        print(r["seed"], r["mode"], r["lang"], r["groundedness"], r["relevance"], r["fluency"], r["response"][:70], flush=True)
    summ = {"n": len(rows), "judge": "gpt-4.1-mini", "sdk": "azure-ai-evaluation", "scale": "1-5, pass >= 3"}
    for k in ev:
        v = [r[k] for r in rows if isinstance(r[k], (int, float))]
        summ[k] = {"mean": round(statistics.mean(v), 2), "pass_rate": round(sum(x >= 3 for x in v) / len(v), 3), "n": len(v)}
        for g in ("mode", "lang"):
            summ[k]["by_" + g] = {x: round(statistics.mean([r[k] for r in rows if r[g] == x and isinstance(r[k], (int, float))]), 2)
                                  for x in sorted({r[g] for r in rows})}
    cs = [r["content_safety"] for r in rows if r["content_safety"]]
    summ["content_safety"] = {"checked": len(cs), "max_severity": max((max(c.values()) for c in cs), default=None),
                              "flagged_severity_ge_2": sum(max(c.values()) >= 2 for c in cs)}
    os.makedirs("evals", exist_ok=True)
    json.dump(rows, open("evals/results.json", "w"), indent=1, ensure_ascii=False)
    json.dump(summ, open("evals/summary.json", "w"), indent=2)
    print(json.dumps(summ, indent=2))


if __name__ == "__main__":
    main()
