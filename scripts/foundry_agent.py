"""Host the Analyst Desk as a Microsoft Foundry Agent Service agent and run it on a showcase match.

Creates (or reuses, by name) agent `itg-analyst-desk` in Foundry project `insidethegame` on the
ais-insidethegame-alv AI Services account (model gpt-4.1-mini), then asks it grounded questions. Each answer is run
through the same verifier as the app (analyst.verify: numbers, names, claims). Auth: Entra ID via the Azure CLI
(`az account get-access-token --resource https://ai.azure.com`); needs the "Azure AI User" role on the account.
Writes evals/foundry_agent_run.json.  Usage: python scripts/foundry_agent.py [seed]"""
import json, os, subprocess, sys, time, urllib.request
from insidethegame import analyst

EP = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "https://ais-insidethegame-alv.services.ai.azure.com/api/projects/insidethegame")
V = "api-version=v1"
NAME = "itg-analyst-desk"


def token() -> str:
    return subprocess.check_output(["az", "account", "get-access-token", "--resource", "https://ai.azure.com",
                                    "--query", "accessToken", "-o", "tsv"], text=True).strip()


def call(method, path, body=None, tok=None):
    req = urllib.request.Request(f"{EP}{path}{'&' if '?' in path else '?'}{V}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def main(seed=42):
    tok = token()
    agents = call("GET", "/assistants?limit=100", tok=tok)["data"]
    ag = next((a for a in agents if a.get("name") == NAME), None)
    if not ag:
        ag = call("POST", "/assistants", {"name": NAME, "model": os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini"),
                                           "instructions": analyst.QA_INSTRUCTIONS, "temperature": 0.2,
                                           "metadata": {"app": "inside-the-game", "role": "analyst desk"}}, tok)
    facts, r = analyst.facts_for(seed)
    out = {"agent_id": ag["id"], "agent_name": NAME, "model": ag["model"], "project_endpoint": EP, "seed": seed, "runs": []}
    for q in ["Who deserved to win on chances?", "Who was the best player?", "Compare the shots of both teams."]:
        th = call("POST", "/threads", {"messages": [{"role": "user", "content":
                  f"Facts (JSON, the only source of truth):\n{json.dumps(facts)}\n\nQuestion: {q}"}]}, tok)
        run = call("POST", f"/threads/{th['id']}/runs", {"assistant_id": ag["id"]}, tok)
        while run["status"] in ("queued", "in_progress"):
            time.sleep(1.5)
            run = call("GET", f"/threads/{th['id']}/runs/{run['id']}", tok=tok)
        msgs = call("GET", f"/threads/{th['id']}/messages?order=desc&limit=1", tok=tok)["data"]
        ans = msgs[0]["content"][0]["text"]["value"] if run["status"] == "completed" else None
        out["runs"].append({"question": q, "status": run["status"], "answer": ans, "usage": run.get("usage"), "error": run.get("last_error"),
                            "verifier_issues": analyst.verify(ans, facts, r) if ans else None})
        print(q, "->", run["status"], ans, run.get("last_error"))
    os.makedirs("evals", exist_ok=True)
    json.dump(out, open("evals/foundry_agent_run.json", "w"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 42)
