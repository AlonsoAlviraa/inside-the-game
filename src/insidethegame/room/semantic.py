"""Semantic claim check: deterministic extraction of comparative / attribution claims from generated text,
verified against match state. Catches errors a numbers-only check misses, e.g.
  * "despite Harbour's higher xG"        when the other team leads xG       (leader claims: xG, shots, control)
  * "0.093 de amenaza esperada"           when 0.093 is an xG value          (metric naming xG vs xT)
  * "Kian Juniper scores"                 when someone else scored           (attribution: player names)
  * "at minute 31"                        when the moment is minute 37       (minute claims)
  * "end of the 48th minute" / wrong half (period labels)
  * "82% possession"                      from a 0-1 control index           (control != possession)
Supports English, Spanish and French phrasing. Returns a list of issues (empty = consistent).
"""
from __future__ import annotations
import re

METRICS = {
    "xg": r"(xg\b|expected goals?|goles esperados|buts attendus|calidad de (?:las )?ocasiones)",
    "xt": r"(xt\b|expected threat|amenaza esperada|menace attendue|amenaza)",
    "shots": r"(shots?\b|disparos?|tiros?|remates?|tirs?\b|frappes?)",
    "control": r"(control(?: index)?\b|índice de control|indice de contrôle|contrôle|dominio)",
}
COMPARATIVE = r"(higher|more|most|greater|leads?|leading|ahead|better|superior|más|mayor|mejor|lidera|domina\w*|plus de|supérieur\w*|meilleur\w*|devant)"
NEG_COMP = r"(fewer|lower|less|menos|inferior|moins)"
POSSESSION = r"(possession|posesi[oó]n)"
HALF = r"(half[- ]time|descanso|medio tiempo|mi-temps|first half|primera parte|première période)"
FULL = r"(full[- ]time|final del partido|pitido final|fin du match|final whistle|ganaron|won\b|victory|victoria|victoire)"
_NUM = r"\d+(?:[.,]\d+)?"


def _f(x: str) -> float:
    return float(x.replace(",", "."))


def _leaders(facts: dict, snap: dict | None) -> dict:
    teams = (facts.get("teams") or (snap or {}).get("teams") or {})
    ctrl = facts.get("control_index_0_to_1") or facts.get("control") or (snap or {}).get("control") or {}
    out = {}
    for m in ("xg", "shots"):
        vals = {t: v.get(m, 0) for t, v in teams.items() if isinstance(v, dict)}
        if len(vals) == 2 and len(set(vals.values())) == 2:
            out[m] = max(vals, key=vals.get)
    if isinstance(ctrl, dict) and len(ctrl) == 2 and len(set(ctrl.values())) == 2:
        out["control"] = max(ctrl, key=ctrl.get)
    return out


def _team_aliases(snap: dict | None, facts: dict, meta: dict | None) -> dict:
    """Map lower-case alias -> canonical team name (full name, short code, distinctive last word)."""
    al = {}
    names = set((facts.get("teams") or {}).keys()) | set(((snap or {}).get("teams") or {}).keys())
    for side in ("home", "away"):
        if meta and side in meta:
            t = meta[side]
            names.add(t["name"])
            al[t["short"].lower()] = t["name"]
    for n in names:
        al[n.lower()] = n
        al[n.split()[-1].lower()] = n  # "Mariners", "Rovers"
    return al


def _clauses(text: str) -> list[str]:
    return [c for c in re.split(r"[.;!?]|,\s*(?:but|while|pero|mientras|mais|alors que)\b|\bdespite\b|\bpese a\b|\bmalgré\b",
                                text, flags=re.I) if c.strip()]


def check(text: str, facts: dict, snap: dict | None = None, meta: dict | None = None,
          roster: list[str] | None = None) -> list[str]:
    issues: list[str] = []
    low = text.lower()
    leaders = _leaders(facts, snap)
    aliases = _team_aliases(snap, facts, meta)

    # 1) leader claims ("TEAM ... higher xG", "despite TEAM's higher shot count")
    for clause in _clauses(text):
        cl = clause.lower()
        for metric, pat in METRICS.items():
            if metric not in leaders:
                continue
            for mm in re.finditer(pat, cl):
                window = cl[max(0, mm.start() - 70): mm.end() + 25]
                if not re.search(COMPARATIVE, window) or re.search(NEG_COMP, window):
                    continue
                if re.search(r"\b(vs|versus|frente a|contra|than|que)\b", window) and len(
                        {aliases[a] for a in aliases if a in window}) > 1:
                    continue  # explicit comparison of two values - numbers check covers it
                hits = [(cl.rfind(a, 0, mm.start() + 1), aliases[a]) for a in aliases if a in cl[:mm.start() + 1]]
                hits = [h for h in hits if h[0] >= 0]
                if not hits:
                    continue
                subject = max(hits)[1]
                if subject != leaders[metric]:
                    issues.append(f"leader:{metric}: text credits {subject}, state says {leaders[metric]}")

    # 2) metric naming: a number labelled xT must be an xT value (and vice versa)
    vals = {"xg": set(), "xt": set()}
    for k, v in facts.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            for fam in ("xg", "xt"):
                if fam in k.lower():
                    vals[fam].add(round(float(v), 2))
    for fam, other in (("xg", "xt"), ("xt", "xg")):
        for mm in re.finditer(rf"({_NUM})\s*(?:de |of |d')?{METRICS[fam]}|{METRICS[fam]}\s*(?:of|de|:|=)?\s*({_NUM})", low):
            num = mm.group(1) or mm.group(mm.lastindex)
            try:
                v = round(_f(num), 2)
            except ValueError:
                continue
            if v in vals[other] and v not in vals[fam]:
                issues.append(f"metric: {num} is {other.upper()}, text calls it {fam.upper()}")

    # 3) control index presented as possession
    if re.search(POSSESSION, low) and "possession" not in str(facts).lower():
        issues.append("control index described as possession")

    # 4) attribution: any roster player named must be one of the moment's players
    allowed = {str(facts.get(k)) for k in ("player", "player_on", "player_off", "scorer") if facts.get(k)}
    allowed |= set(re.findall(r"[A-Z][a-z]+ [A-Z][a-z]+", str(facts.get("analysis", ""))))
    for name in roster or []:
        if name in text and name not in allowed and allowed:
            issues.append(f"attribution: {name} is not part of this moment")
    if facts.get("moment") == "goal" and facts.get("player") and facts["player"] not in text:
        if re.search(r"(scor|goal|gol|marca|but\b)", low) and any(n in text for n in roster or []):
            issues.append("attribution: goal credited to the wrong player")

    # 5) minute claims
    fm = facts.get("minute")
    if isinstance(fm, int):
        for mm in re.finditer(rf"(?:minute|minuto|min\.?|minutes?)\s*({_NUM})|({_NUM})(?:st|nd|rd|th|º|e|ème)?\s*(?:minute|minuto|min\b|')", low):
            n = mm.group(1) or mm.group(2)
            if n and abs(_f(n) - fm) > 1:
                issues.append(f"minute: text says {n}, moment is {fm}")

    # 6) period labels
    mom, per = facts.get("moment"), facts.get("period")
    if mom == "period_end" and per == 1 and re.search(FULL, low):
        issues.append("period: half-time described as full-time")
    if mom == "match_end" and re.search(HALF, low):
        issues.append("period: full-time described as half-time")
    if mom in ("period_end", "match_end") and re.search(r"end of the \d+\w* minute", low):
        issues.append("period: use Half-time/Full-time, not 'end of the Nth minute'")
    return issues


# ------------------------------------------------------------------ fan-mode style rules (deterministic)
def fan_violations(text: str, facts: dict) -> list[str]:
    out = []
    low = text.lower()
    if re.search(r"\d+[.,]\d+", text):
        out.append("fan: decimal number")
    if re.search(r"km/h|\d+\s*(m|metros|mètres|meters|metres)\b", low):
        out.append("fan: speed/distance")
    if re.search(r"\bx[gt]\b|expected|esperad|attendu|índice|index|indice", low):
        out.append("fan: jargon")
    if len(text.split()) > 24:
        out.append("fan: too long")
    if text.count("!") + text.count("¡") > 2:
        out.append("fan: too many exclamation marks")
    if facts.get("moment") == "goal" and facts.get("player") and facts["player"] not in text:
        out.append("fan: goal card must name the scorer")
    return out
