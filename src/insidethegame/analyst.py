"""Grounded LLM features on top of `insights`: full-time recap and ask-the-analyst Q&A.

Every model answer goes through the same guards as the live room: the numbers check (`factcheck`), the
semantic claim check (`semantic`) plus a roster check (any player named must be in the facts). One repair
round is allowed; if it still fails, a deterministic answer built from the same facts is returned instead.
Offline (ITG_LLM_PROVIDER=mock) the deterministic path is used, so the feature works with no model at all."""
from __future__ import annotations
import json
import re

from . import insights
from .room import factcheck, injection, safety, semantic
from .room.llm import Brain, TokenBudget, UsageLedger, azure_enabled, make_chat_client

LANG = {"en": "English", "es": "Spanish", "fr": "French"}
QA_INSTRUCTIONS = ("You are the analyst desk of a football broadcast about a SYNTHETIC match between fictional teams. "
                   "Answer the viewer's question in at most 3 sentences using ONLY the JSON facts given. Never invent "
                   "numbers, players or events. Copy numbers exactly as written. xG = expected goals (chance quality), "
                   "xT = expected threat (danger added by passes); pass_share_pct is share of passes, NOT possession. "
                   "If the facts do not answer the question, say so briefly. Plain text, no markdown." + injection.HARDENING)
RECAP_INSTRUCTIONS = ("You write a 4-sentence match recap for a SYNTHETIC football match between fictional teams, using ONLY "
                      "the JSON facts. Mention the final score, who scored and when, which side created the better "
                      "chances (xG) and one standout performer. Copy numbers exactly. Never invent facts. Plain text.")

_ledger = UsageLedger()
_budget = TokenBudget()
_brains: dict[str, Brain] = {}


def usage() -> dict:
    return _ledger.totals()


def _brain(name: str, instr: str, max_tokens: int) -> Brain:
    if name not in _brains:
        client = make_chat_client() if azure_enabled() else None
        _brains[name] = Brain(name, instr, client, None, _budget, _ledger, max_tokens)
    return _brains[name]


def facts_for(seed: int, minute: int = 200) -> tuple[dict, dict]:
    """Compact, name-keyed facts for the model (and for the checks)."""
    r = insights.report(seed, minute)
    nm = {r["home"]["id"]: r["home"]["name"], r["away"]["id"]: r["away"]["name"]}
    facts = {"status": "full time" if r["finished"] else f"live, up to minute {r['minute']}",
             "score": {nm[k]: v for k, v in r["score"].items()},
             "teams": {nm[k]: v for k, v in r["teams"].items()},
             "key_moments": [{k: m[k] for k in ("minute", "kind", "player", "xg", "xt") if k in m} | {"team": nm[m["team"]]}
                             for m in r["key_moments"] if m["importance"] >= 3][:12],
             "top_players": [{k: p[k] for k in ("name", "goals", "shots", "xg", "xt", "pass_completion_pct", "impact")}
                             | {"team": nm.get(p["team"], p["team"])} for p in r["players"][:6]]}
    return facts, r


def _roster(r: dict) -> list[str]:
    evs = insights.events(r["seed"])
    meta = evs[0]["meta"]
    return [p["name"] for t in (meta["home"], meta["away"]) for p in t["players"]]


def verify(text: str, facts: dict, r: dict) -> list[str]:
    """All guards for a free-text answer. Empty list = grounded."""
    ok, bad = factcheck.check(text, facts)
    issues = [f"numbers: {b} not in facts" for b in bad] if not ok else []
    issues += semantic.check(text, {"teams": facts["teams"]}, None, None)
    blob = json.dumps(facts)
    issues += [f"attribution: {n} not in facts" for n in _roster(r) if n in text and n not in blob]
    issues += injection.check_output(text, list(facts["teams"]) + _roster(r))
    return issues


async def _safe(text: str) -> bool:
    """Azure AI Content Safety on the final model text when enabled (free tier); unsafe or error => rules text."""
    if not safety.enabled():
        return True
    return safety.safe((await safety.analyze([text]))[0])


# ------------------------------------------------------------------ deterministic answers
def _lead(facts: dict, metric: str) -> tuple[str, str]:
    (a, va), (b, vb) = [(k, v[metric]) for k, v in facts["teams"].items()]
    return (a, b) if va >= vb else (b, a)


def fallback_answer(question: str, facts: dict) -> str:
    q = question.lower()
    (h, sh), (a, sa) = facts["score"].items()
    T = facts["teams"]
    goals = [m for m in facts["key_moments"] if m["kind"] == "goal"]
    if re.search(r"xg|chance|ocasi|occasion|deserv|merec", q):
        lead, oth = _lead(facts, "xg")
        return f"{lead} created the better chances: xG {T[lead]['xg']} against {T[oth]['xg']} for {oth}."
    if re.search(r"threat|xt|amenaza|menace|danger|progress", q):
        lead, oth = _lead(facts, "xt")
        return f"{lead} added more threat with the ball: xT {T[lead]['xt']} against {T[oth]['xt']}."
    if re.search(r"best|top|mvp|star|mejor|meilleur|player|jugador|joueur", q) and facts["top_players"]:
        p = facts["top_players"][0]
        return (f"{p['name']} ({p['team']}) tops the impact table: goals {p['goals']}, xG {p['xg']} "
                f"and xT {p['xt']}.")
    if re.search(r"who scor|goal|gol|but|scorer", q):
        if not goals:
            return "No goals so far."
        return "Goals: " + "; ".join(f"{g['player']} ({g['team']}) in minute {g['minute']}" for g in goals) + "."
    if re.search(r"shot|tiro|disparo|tir", q):
        return (f"Shots: {h} {T[h]['shots']} ({T[h]['on_target']} on target), "
                f"{a} {T[a]['shots']} ({T[a]['on_target']} on target).")
    if re.search(r"card|tarjeta|carton|foul|falta|faute", q):
        return (f"Discipline: {h} {T[h]['fouls']} fouls, {T[h]['yellow_cards']} yellow, {T[h]['red_cards']} red; "
                f"{a} {T[a]['fouls']} fouls, {T[a]['yellow_cards']} yellow, {T[a]['red_cards']} red.")
    if re.search(r"pass|pase|passe|possession|posesi", q):
        return (f"Passing: {h} {T[h]['passes']} passes at {T[h]['pass_completion_pct']}% completion, "
                f"{a} {T[a]['passes']} at {T[a]['pass_completion_pct']}%.")
    return f"The score is {h} {sh} – {sa} {a} ({facts['status']}). Ask me about chances, threat, players, shots, cards or passing."


def fallback_recap(facts: dict) -> str:
    (h, sh), (a, sa) = facts["score"].items()
    lead, oth = _lead(facts, "xg")
    goals = [m for m in facts["key_moments"] if m["kind"] == "goal"]
    s = f"{h} {sh} – {sa} {a}. "
    s += ("Goals: " + "; ".join(f"{g['player']} ({g['minute']}')" for g in goals) + ". ") if goals else "No goals. "
    s += f"{lead} created the better chances (xG {facts['teams'][lead]['xg']} against {facts['teams'][oth]['xg']}). "
    if facts["top_players"]:
        p = facts["top_players"][0]
        s += f"Standout: {p['name']} ({p['team']}), impact {p['impact']}."
    return s


# ------------------------------------------------------------------ LLM with guards
async def _grounded(brain: Brain, prompt: str, facts: dict, r: dict, fallback: str) -> dict:
    trace: dict = {"agent": brain.name}
    text = await brain.ask(prompt, trace)
    issues: list[str] = []
    if text:
        issues = verify(text, facts, r)
        if issues:
            fixed = await brain.ask(prompt + "\nYour previous answer had these errors: " + "; ".join(issues)
                                    + "\nRewrite it correctly using only the facts.", {})
            if fixed and not verify(fixed, facts, r) and await _safe(fixed):
                return {"text": fixed, "source": "llm", "verified": True, "repaired": True, "issues": issues,
                        "trace": trace}
            return {"text": fallback, "source": "rules", "verified": True, "rejected": issues, "trace": trace}
        if not await _safe(text):
            return {"text": fallback, "source": "rules", "verified": True, "rejected": ["content safety"], "trace": trace}
        return {"text": text, "source": "llm", "verified": True, "issues": [], "trace": trace}
    return {"text": fallback, "source": "rules", "verified": True, "issues": [], "trace": trace}


async def ask(seed: int, question: str, minute: int = 200, lang: str = "en") -> dict:
    question = injection.sanitize(question)
    facts, r = facts_for(seed, minute)
    fb = fallback_answer(question, facts)
    flags = injection.detect(question)
    if flags:  # never sent to the model
        out = {"text": f"{injection.REFUSAL} {fb}", "source": "rules", "verified": True,
               "rejected": [f"input guard: {f}" for f in flags], "guard": {"blocked": True, "patterns": flags}, "trace": {"agent": "guard"}}
    else:
        prompt = (f"Answer in {LANG.get(lang, 'English')}.\nFACTS: {json.dumps(facts)}\nQUESTION: {injection.wrap(question)}")
        out = await _grounded(_brain("analyst", QA_INSTRUCTIONS, 160), prompt, facts, r, fb)
        out["guard"] = {"blocked": False}
    out["evidence"] = [m for m in r["key_moments"] if m["importance"] >= 4][:5]
    return out


async def recap(seed: int, minute: int = 200, lang: str = "en") -> dict:
    facts, r = facts_for(seed, minute)
    prompt = f"Write in {LANG.get(lang, 'English')}.\nFACTS: {json.dumps(facts)}"
    return await _grounded(_brain("recap", RECAP_INSTRUCTIONS, 220), prompt, facts, r, fallback_recap(facts))
