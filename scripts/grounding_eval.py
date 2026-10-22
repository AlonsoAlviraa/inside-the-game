"""Deterministic grounding evaluation against the raw event stream: LLM commentary vs the rules baseline.

Why: our Foundry evals used gpt-4.1-mini as judge, the same model that writes the commentary, and the
resource has no second model deployed (adding one would be a new paid deployment). So this metric uses no
model at all. For every event card (id evN) it compares the text with event N in the synthetic feed:
  * outcome: a goal card mentions the goal; a non-goal shot is never described as scored;
  * attribution: every roster player named is the event's player or appears in the card's facts;
  * scoreline: any "a–b" score in the text equals the real score at that moment;
  * minute: any minute stated is within ±1 of the event minute (or appears in the facts).
It is independent of the runtime guards (they compare text with the facts handed to the model, not with the
raw feed). Also reported: the same LLM cards after the event-consistency guard this eval motivated. Baseline: the same room in rules mode (no model) over the same batches and the same cards.
Limits: pattern-based (en/es/fr). It catches contradictions; it cannot judge style or insight, and it has no
human labels. Writes evals/grounding.json.  Usage: python scripts/grounding_eval.py"""
import asyncio
import json
import re
from collections import defaultdict
from pathlib import Path

from insidethegame import insights, replay
from insidethegame.room import CommentaryRoom, ViewerProfile, localise, semantic

SCORED = re.compile(r"\b(scores|scored|nets|netted|finds the net|puts it away|marca|anota|marc[óo]|en la red|marque|a marqué|au fond des filets)\b", re.I)
GOALW = re.compile(r"\b(goal|gol|golazo|but|scores|scored|nets|netted|equalis\w*|levels|marca|marc[óo]|anota|iguala|igualó|empata|empató|taking the lead|takes the lead|nails it|adelanta|marque|a marqué|ouvre le score|égalise|a égalisé|a ouvert le score|double la mise)\b", re.I)
NEAR = re.compile(r"\b(almost|nearly|so close|casi|por poco|presque|a failli|manque)\b", re.I)
SCORE = re.compile(r"(?<![\d.])(\d{1,2})\s*[-–:]\s*(\d{1,2})(?!\d|[.,]\d)")
MINUTE = re.compile(r"(\d{1,3})\s*(?:'|’|′| ?min\b|(?:st|nd|rd|th) minute|e minute|ª? minuto|ᵉ)", re.I)


def score_at(evs, eid):
    s = {evs[0]["meta"]["home"]["id"]: 0, evs[0]["meta"]["away"]["id"]: 0}
    for e in evs:
        if e["id"] > eid:
            break
        if e["type"] == "goal":
            s = dict(e["score"])
    return s


def judge(text, card, ev, evs, roster):
    out = {}
    if ev["type"] == "goal" or (ev["type"] == "shot" and ev.get("outcome") == "goal"):
        out["outcome"] = bool(GOALW.search(text))
    elif ev["type"] == "shot":
        out["outcome"] = not SCORED.search(NEAR.sub("", text)) or bool(NEAR.search(text))
    facts = json.dumps(card.get("facts") or {}, ensure_ascii=False)
    named = [n for n in roster if n in text]
    if named:
        out["attribution"] = all(n == ev.get("player") or n in facts for n in named)
    sc = SCORE.findall(text)
    if sc:
        real = sorted(score_at(evs, ev["id"]).values())
        out["scoreline"] = all(sorted((int(a), int(b))) == real for a, b in sc)
    mins = [int(m) for m in MINUTE.findall(text)]
    if mins:
        out["minute"] = all(abs(m - ev["minute"]) <= 1 or str(m) in facts for m in mins)
    return out


async def rules_cards(seed, mode, lang, cuts):
    room = CommentaryRoom(seed, online=False)
    prof = ViewerProfile(mode=mode, language=lang)
    out, batch = {}, []
    for e in insights.events(seed):
        batch.append(e)
        if e["id"] in cuts:
            for c in localise.ensure((await room.process_batch(batch, prof)).cards, lang, mode):
                out[c["id"]] = c
            batch = []
    return out


def main():
    agg = {k: defaultdict(lambda: [0, 0]) for k in ("llm", "llm_with_event_check", "rules")}
    per_lang = {k: defaultdict(lambda: [0, 0]) for k in agg}
    cards_n = {k: 0 for k in agg}
    rows = []
    for a in replay.available():
        d = replay.load(a["seed"], a["mode"], a["lang"])
        evs = list(insights.events(a["seed"]))
        by_id = {e["id"]: e for e in evs}
        meta = evs[0]["meta"]
        roster = [p["name"] for t in (meta["home"], meta["away"]) for p in t["players"]]
        cuts = {b["after_event"] for b in d["batches"]}
        base = asyncio.run(rules_cards(a["seed"], a["mode"], a["lang"], cuts))
        for b in d["batches"]:
            for c in b["payload"]["cards"]:
                m = re.match(r"ev(\d+)$", str(c.get("id")))
                if not m or not ("llm" in str(c.get("source")) or "personalised" in str(c.get("source"))):
                    continue
                ev = by_id[int(m.group(1))]
                if c["id"] not in base:
                    continue
                # what the runtime now ships: an LLM card failing the new event check falls back to the rules card
                guarded = base[c["id"]] if semantic.event_consistency(c["text"], base[c["id"]].get("facts") or {}) else c
                pairs = [("llm", c), ("llm_with_event_check", guarded), ("rules", base[c["id"]])]  # compare like with like: only cards both systems wrote
                for k, card in pairs:
                    cards_n[k] += 1
                    j = judge(card["text"], card, ev, evs, roster)
                    rows.append({"system": k, "seed": a["seed"], "mode": a["mode"], "lang": a["lang"], "card": c["id"],
                                 "response": card["text"], "checks": j})
                    for check, ok in j.items():
                        agg[k][check][0] += ok
                        agg[k][check][1] += 1
                        per_lang[k][a["lang"]][0] += ok
                        per_lang[k][a["lang"]][1] += 1
    res = {"method": __doc__.split("\n\n")[1].strip(), "cards_compared": cards_n, "metrics": {}}
    for k in agg:
        tot = [sum(v[0] for v in agg[k].values()), sum(v[1] for v in agg[k].values())]
        res["metrics"][k] = {"overall_pass_rate": round(tot[0] / tot[1], 4) if tot[1] else None, "checks": tot[1],
                             "by_check": {c: {"pass_rate": round(v[0] / v[1], 4), "n": v[1]} for c, v in sorted(agg[k].items())},
                             "by_lang": {lg: round(v[0] / v[1], 4) for lg, v in sorted(per_lang[k].items())}}
    res["limits"] = ("Deterministic, pattern-based (en/es/fr); measures contradictions with the event feed, not style or "
                     "insight. No human labels. Same synthetic matches the system was tuned on.")
    with open("evals/grounding_rows.jsonl", "w") as fh:
        fh.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    Path("evals/grounding.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(json.dumps(res["metrics"], indent=2), cards_n)


if __name__ == "__main__":
    main()
