"""Log the deterministic grounding eval (evals/grounding_rows.jsonl) as an evaluation run in the Foundry
project, using a code-only evaluator (no model calls, no cost). Needs `az login`; makes no config changes.
Usage: python scripts/upload_grounding_foundry.py"""
import json
import os

from azure.ai.evaluation import evaluate
from azure.identity import AzureCliCredential

EP = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "https://ais-insidethegame-alv.services.ai.azure.com/api/projects/insidethegame")


class EventGrounding:
    """Pass rate of the deterministic event-consistency checks for one card (precomputed, see grounding_eval.py)."""

    def __call__(self, *, checks, system):
        c = json.loads(checks) if isinstance(checks, str) else checks
        vals = list(c.values())
        return {"pass_rate": (sum(vals) / len(vals)) if vals else 1.0, "contradiction": int(not all(vals)),
                "is_llm": int(system == "llm")}


def main():
    res = evaluate(data="evals/grounding_rows.jsonl", evaluators={"event_grounding": EventGrounding()},
                   evaluation_name="itg-event-grounding-llm-vs-rules", azure_ai_project=EP,
                   credential=AzureCliCredential(), output_path="evals/grounding_foundry_run.json")
    print(res.get("studio_url"), res.get("metrics"))


if __name__ == "__main__":
    main()
