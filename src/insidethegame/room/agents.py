"""The five agents, one per challenge stage. Each has a deterministic core (always works, testable offline)
and, where language helps, a Microsoft Agent Framework `Agent` brain on Azure OpenAI."""
from __future__ import annotations
import json

from .. import xt
from ..metrics import ControlChaosIndex
from ..spadl import to_spadl
from . import factcheck, localise, safety, semantic
from .llm import Brain, parse_json
from .state import Batch, RoomState, ViewerMemory, validate_card

REQUIRED = {"pass": ("team", "player_id", "x", "y", "end_x", "end_y", "success"),
            "shot": ("team", "player_id", "x", "y", "xg", "outcome"),
            "goal": ("team", "player_id", "score"), "foul": ("team", "player_id", "x", "y"),
            "card": ("team", "player_id", "card"), "substitution": ("team", "player_on", "player_off")}


# =========================================================================== 1. INGEST
class IngestAgent:
    """Validates and normalises raw events, de-duplicates, flags anomalies, appends SPADL + updates state."""
    name = "ingest"

    def __init__(self, state: RoomState):
        self.st = state

    async def run(self, b: Batch, entry: dict | None = None) -> Batch:
        st, out, dups, anomalies = self.st, [], 0, []
        for ev in b.raw:
            if ev.get("type") == "match_start":
                st.meta = ev["meta"]
                st.score = {st.meta["home"]["id"]: 0, st.meta["away"]["id"]: 0}
            missing = [k for k in ("id", "t", "type", "minute", "period") if k not in ev]
            missing += [k for k in REQUIRED.get(ev.get("type"), ()) if k not in ev]
            if missing:
                anomalies.append({"id": ev.get("id"), "issue": f"missing {missing}"})
                continue
            fp = (ev["type"], ev["t"], ev.get("player_id"), ev.get("x"), ev.get("y"))
            if ev["id"] in st.seen_ids or (ev["type"] not in ("pressure",) and fp in st.fingerprints):
                dups += 1
                continue
            st.seen_ids.add(ev["id"])
            st.fingerprints.add(fp)
            if ev["t"] < st.last_t - 0.01:
                anomalies.append({"id": ev["id"], "issue": "time went backwards", "t": ev["t"]})
            if st.meta and ev.get("team") and ev["team"] not in st.score:
                anomalies.append({"id": ev["id"], "issue": f"unknown team {ev['team']}"})
                continue
            ev = dict(ev)
            for kx, ky in (("x", "y"), ("end_x", "end_y")):
                if kx in ev and ev[kx] is not None:
                    x, y = ev[kx], ev[ky]
                    if not (0 <= x <= 105 and 0 <= y <= 68):
                        anomalies.append({"id": ev["id"], "issue": f"{kx},{ky} off pitch -> clipped"})
                        ev[kx], ev[ky] = min(max(x, 0.0), 105.0), min(max(y, 0.0), 68.0)
            if ev["type"] == "goal" and not any(o["type"] == "shot" and o.get("player_id") == ev["player_id"]
                                                 for o in out[-3:]):
                anomalies.append({"id": ev["id"], "issue": "goal without preceding shot in batch"})
            st.last_t = max(st.last_t, ev["t"])
            st.minute, st.period = ev["minute"], ev["period"]
            if ev["type"] == "goal":
                st.score = dict(ev["score"])
            out.append(ev)
        rows = to_spadl(out, game_id=st.meta.get("seed", 0) if st.meta else 0)
        offset = len(st.spadl)
        for r in rows:
            r["action_id"] += offset
        st.spadl += rows
        st.anomalies += anomalies
        b.events = out
        b.report = {"received": len(b.raw), "accepted": len(out), "duplicates": dups,
                    "anomalies": anomalies[:5], "spadl_rows": len(rows)}
        return b


# =========================================================================== 2. INTERPRET
PHASES = {"siege": "is laying siege - camped in the final third",
          "high_press": "is pressing high and winning the ball back early",
          "chaos": "end-to-end chaos - turnovers everywhere",
          "control": "is controlling the ball and the tempo",
          "balanced": "a balanced spell - nobody dominating"}


class InterpretAgent:
    """Stats + xT + control-vs-chaos + tactical phase detection. LLM brain reads the game with MCP tools."""
    name = "interpret"
    instructions = ("You are the tactical analyst in a live football commentary room. Data is synthetic, teams "
                    "fictional. Call the tools to check live numbers (always pass the given seed and "
                    "up_to_minute = current minute). The control index (0-1) is NOT possession; never call it a percentage "
                    "of possession. Then answer with ONE sentence (max 30 words) on the "
                    "tactical story right now. Only use numbers returned by tools or given in the prompt.")

    def __init__(self, state: RoomState, brain: Brain, seed: int = 7, every_min: int = 15):
        self.st, self.brain, self.seed, self.every = state, brain, seed, every_min
        self.index: ControlChaosIndex | None = None
        self.last_llm_minute = -99
        self._window: list[dict] = []

    def _phase(self) -> tuple[str, str | None]:
        idx = self.st.index
        if not idx:
            return "balanced", None
        ctrl = idx["control"]
        lead = max(ctrl, key=ctrl.get)
        w = [e for e in self._window if e["t"] > self.st.last_t - 300]
        f3 = {t: sum(1 for e in w if e["type"] == "pass" and e["team"] == t and e.get("end_x", 0) > 70) for t in ctrl}
        press = {t: sum(1 for e in w if e["type"] == "pressure" and e["team"] == t) for t in ctrl}
        tot_f3 = sum(f3.values()) or 1
        if idx["chaos"] > 0.6:
            return "chaos", None
        if f3[lead] / tot_f3 > 0.68 and f3[lead] >= 12:
            return "siege", lead
        top_press = max(press, key=press.get)
        if press[top_press] >= 14 and press[top_press] > 1.6 * max(1, min(press.values())):
            return "high_press", top_press
        if ctrl[lead] > 0.56:
            return "control", lead
        return "balanced", None

    async def run(self, b: Batch, entry: dict | None = None) -> Batch:
        st = self.st
        if self.index is None and st.meta:
            self.index = ControlChaosIndex(st.meta["home"]["id"], st.meta["away"]["id"])
        for ev in b.events:
            ts = st.team_stats[ev.get("team")] if ev.get("team") else None
            if ev["type"] == "pass":
                ts["passes"] += 1
                ts["passes_ok"] += ev["success"]
                gain = xt.added(ev)
                ev["xt_added"] = gain
                ts["xt"] += gain
                ps = st.player_stats[ev["player_id"]]
                ps["xt"] += gain
                ps["passes"] += 1
            elif ev["type"] == "shot":
                ts["shots"] += 1
                ts["xg"] += ev["xg"]
                st.player_stats[ev["player_id"]]["xg"] += ev["xg"]
            elif ev["type"] == "goal":
                st.player_stats[ev["player_id"]]["goals"] += 1
            if self.index is not None and ev["type"] != "match_start":
                st.index = self.index.update(ev)
            self._window.append(ev)
        self._window = [e for e in self._window if e["t"] > st.last_t - 300]
        phase, team = self._phase()
        # hysteresis: a new phase must be detected in 2 consecutive batches before we switch
        pending = getattr(self, "_pending", None)
        self._pending = (phase, team)
        confirmed = (phase, team) == pending or st.phase == "kick-off"
        if confirmed and (phase != st.phase or team != st.phase_team):
            last_card = getattr(self, "_last_phase_card", -99)
            if st.minute >= 3 and st.minute - last_card >= 15:
                self._last_phase_card = st.minute
                b.insights.append({"kind": "phase", "phase": phase, "team": team, "minute": st.minute,
                                   "from": st.phase, "control": st.index.get("control"),
                                   "chaos": st.index.get("chaos")})
            st.phase, st.phase_team = phase, team
            st.phase_history.append((st.minute, phase, team))
        # LLM tactical read: on phase change or every N match minutes (keeps TPM low)
        due = st.minute - self.last_llm_minute >= self.every and st.minute >= 5
        if due and self.brain.online:
            self.last_llm_minute = st.minute
            snap = st.snapshot()
            prompt = (f"seed={self.seed}, current minute={st.minute}. Detected phase: {phase} "
                      f"({st.team_name(team) or 'no team'}). Live snapshot: {json.dumps(snap)}")
            text = await self.brain.ask(prompt, entry, est_extra=900)
            if text:
                from ..mcp_server import top_players
                from ..mcp_server import control_index
                facts = [snap, top_players(self.seed, "xt", 5, st.minute), top_players(self.seed, "xg", 5, st.minute),
                         control_index(self.seed, st.minute)]
                ok, bad = factcheck.check(text, *facts)
                sem = semantic.check(text, {"minute": st.minute, "teams": snap["teams"],
                                            "control": snap["control"]}, snap, st.meta, st.roster())
                ok = ok and not sem
                if entry is not None:
                    entry["factcheck"] = "pass" if ok else f"rejected {bad + sem}"
                if ok:
                    st.tactical_read = text
                    b.insights.append({"kind": "read", "text": text, "minute": st.minute})
        return b


# =========================================================================== 2b. SALIENCE SCOUT (fan-out)
class SalienceScout:
    """Runs in parallel with Interpret: scores every event for how much it matters (part of Explain)."""
    name = "salience"

    def __init__(self, state: RoomState):
        self.st = state
        self.max_xg = 0.0

    async def run(self, b: Batch, entry: dict | None = None) -> Batch:
        st = self.st
        pass_taken = False  # at most one pass card per batch
        for ev in b.events:
            t, s = ev["type"], 0.0
            if t == "goal":
                s = 1.0
            elif t == "shot" and ev["outcome"] != "goal":
                s = min(0.85, 0.3 + 1.5 * ev["xg"])
                if ev["xg"] > self.max_xg:
                    s += 0.1
                self.max_xg = max(self.max_xg, ev["xg"])
            elif t == "card":
                s = 0.9 if ev["card"] != "yellow" else 0.5
            elif t == "substitution":
                s = 0.3
            elif t == "match_end" or (t == "period_end" and ev.get("period") == 1):
                s = 0.95  # (period 2 end == match end: one full-time card only)
            elif t == "pass" and ev["success"] and not pass_taken:
                g = xt.added(ev)
                if g >= 0.08 and ev.get("length_m", 0) >= 12:  # only genuinely progressive passes
                    s, pass_taken = 0.3 + 3 * g, True
            if s and st.minute >= 80:
                s += 0.1
            if s >= 0.35:
                b.candidates.append({"id": f"ev{ev['id']}", "kind": "event", "score": round(min(s, 1.0), 2),
                                     "event": ev})
        return b


# =========================================================================== 3. EXPLAIN
class ExplainAgent:
    """Picks the moments that matter (salience) and writes WHY, grounded only in state; fact-checked."""
    name = "explain"
    instructions = ("You explain football moments to TV viewers. Data is synthetic, teams fictional. For each "
                    "moment write 1-2 sentences (max 40 words) saying WHAT happened and WHY it matters. "
                    "Use ONLY names and numbers present in that moment's facts; never invent statistics, "
                    "history or players. 'control' is a 0-1 control index, NOT possession - never turn it into a "
                    "possession percentage. Reply as JSON: {\"items\":[{\"id\":\"...\",\"why\":\"...\"}]}")

    def __init__(self, state: RoomState, brain: Brain, top_k: int = 3, verifier: Brain | None = None):
        self.st, self.brain, self.k, self.verifier = state, brain, top_k, verifier
        self.rejections = 0

    def facts_for(self, c: dict) -> dict:
        st = self.st
        snap = st.snapshot()
        if c["kind"] == "phase":
            i = c["insight"]
            return {"moment": "phase_change", "new_phase": i["phase"], "previous_phase": i["from"],
                    "team": st.team_name(i["team"]), "minute": i["minute"],
                    "control_index_0_to_1": snap["control"], "chaos_index_0_to_1": i["chaos"]}
        if c["kind"] == "read":
            return {"moment": "tactical_read", "analysis": c["insight"]["text"], "minute": st.minute}
        ev = c["event"]
        f = {"moment": ev["type"], "minute": ev["minute"], "team": st.team_name(ev.get("team")),
             "score": snap["score"], "phase": snap["phase"]}
        if ev.get("player_id"):
            f["player"] = ev.get("player")
            ps = st.player_stats.get(ev["player_id"], {})
            f["player_match_xg"] = round(ps.get("xg", 0), 2)
            f["player_match_xt"] = round(ps.get("xt", 0), 2)
        for k in ("period", "xg", "outcome", "distance_m", "speed_kmh", "header", "card", "player_on", "player_off",
                  "length_m"):
            if k in ev:
                f[k] = ev[k]
        if ev["type"] == "pass":
            f["xt_added"] = round(ev.get("xt_added", xt.added(ev)), 2)
        if ev["type"] == "goal" and st.meta:  # score at the moment of the goal, not at batch end
            h, a = st.meta["home"], st.meta["away"]
            f["score"] = f"{h['short']} {ev['score'].get(h['id'], 0)}-{ev['score'].get(a['id'], 0)} {a['short']}"
        if ev["type"] in ("goal", "period_end", "match_end"):
            f["teams"] = snap["teams"]
        return f

    def template(self, c: dict, f: dict) -> str:
        st = self.st
        m = f["moment"]
        if m == "phase_change":
            return (f"{f['team'] + ' ' if f['team'] else ''}{PHASES.get(f['new_phase'], f['new_phase'])}"
                    f" (chaos index {f['chaos_index_0_to_1']}).").strip()[:1].upper() + (f"{f['team'] + ' ' if f['team'] else ''}{PHASES.get(f['new_phase'], f['new_phase'])} (chaos index {f['chaos_index_0_to_1']}).").strip()[1:]
        if m == "tactical_read":
            return f["analysis"]
        if m == "goal":
            ev = c["event"]
            shot_xg = ev.get("xg", 0)
            extra = (" A low-probability finish." if shot_xg < 0.08 else
                     " A big chance, taken." if shot_xg > 0.3 else "")
            return f"GOAL! {f['player']} scores for {f['team']}: {f['score']}. The chance was worth {shot_xg} xG.{extra}"
        if m == "shot":
            verb = {"saved": "forces a save", "blocked": "is blocked", "off_target": "fires wide"}[f["outcome"]]
            return (f"{f['player']} {verb} from {round(f['distance_m'])} m ({f['xg']} xG). "
                    f"{f['team']} now have {f['player_match_xg']} xG through {f['player']}." if f["player_match_xg"] > f["xg"]
                    else f"{f['player']} {verb} from {round(f['distance_m'])} m ({f['xg']} xG).")
        if m == "card":
            return f"{f['card'].replace('_', ' ').capitalize()} card for {f['player']} ({f['team']})."
        if m == "substitution":
            return f"{f['team']} change: {f['player_on']} replaces {f['player_off']}."
        if m == "pass":
            return (f"{f['player']}'s pass added {f['xt_added']} xT, moving "
                    f"{f['team']} into a far more dangerous zone.")
        if m in ("period_end", "match_end"):
            label = "Half-time" if m == "period_end" and c["event"].get("period") == 1 else "Full-time"
            if m == "period_end" and c["event"].get("period") == 2:
                return ""
            xgs = " vs ".join(f"{n} {v['xg']} xG" for n, v in f.get("teams", {}).items())
            return f"{label}: {f['score']}. Chances created: {xgs}."
        return ""

    async def run(self, b: Batch, entry: dict | None = None) -> Batch:
        st = self.st
        cands = list(b.candidates)
        for i in b.insights:
            cands.append({"id": f"{i['kind']}{i['minute']}{len(cands)}", "kind": i["kind"],
                          "score": 0.6 if i["kind"] == "phase" else 0.55, "insight": i})
        cands = [c for c in cands if c["id"] not in st.explained_ids]
        always = [c for c in cands if c["score"] >= 0.95]
        rest = sorted([c for c in cands if c["score"] < 0.95], key=lambda c: -c["score"])[: max(0, self.k - len(always))]
        chosen = always + rest
        facts = {c["id"]: self.facts_for(c) for c in chosen}
        llm_items = {}
        to_llm = [c for c in chosen if c["kind"] != "read"]
        if to_llm and self.brain.online:
            prompt = "Moments:\n" + "\n".join(json.dumps({"id": c["id"], "facts": facts[c["id"]]}) for c in to_llm)
            data = parse_json(await self.brain.ask(prompt, entry))
            if isinstance(data, dict):
                llm_items = {i.get("id"): i.get("why", "") for i in data.get("items", []) if isinstance(i, dict)}
        rejected = []

        def problems(cid: str, why: str) -> list[str]:
            ok, bad = factcheck.check(why, facts[cid])
            return [f"unsupported number {n}" for n in bad] + semantic.check(
                why, facts[cid], st.snapshot(), st.meta, st.roster())

        issues = {cid: problems(cid, w) for cid, w in llm_items.items() if w and cid in facts}
        bad_ids = [cid for cid, i in issues.items() if i]
        if bad_ids and self.brain.online:  # one repair round with the concrete contradictions
            prompt = ("Fix these explanations. Each listed issue is a factual error against the facts; rewrite so "
                      "it is consistent, same JSON format.\n" + "\n".join(json.dumps(
                          {"id": cid, "facts": facts[cid], "draft": llm_items[cid], "issues": issues[cid]})
                          for cid in bad_ids))
            fixed = parse_json(await self.brain.ask(prompt, None))
            for i in (fixed or {}).get("items", []) if isinstance(fixed, dict) else []:
                if isinstance(i, dict) and i.get("id") in issues and i.get("why"):
                    if not problems(i["id"], i["why"]):
                        rejected.append({"id": i["id"], "repaired": True, "issues": issues[i["id"]]})
                        llm_items[i["id"]], issues[i["id"]] = i["why"], []
        if self.verifier is not None and self.verifier.online:  # optional cheap LLM verifier
            ok_ids = [cid for cid, w in llm_items.items() if w and cid in facts and not issues.get(cid)]
            if ok_ids:
                v = parse_json(await self.verifier.ask("\n".join(json.dumps(
                    {"id": cid, "facts": facts[cid], "text": llm_items[cid]}) for cid in ok_ids), None))
                for r in (v or {}).get("results", []) if isinstance(v, dict) else []:
                    if isinstance(r, dict) and r.get("ok") is False and r.get("id") in llm_items:
                        issues[r["id"]] = [f"verifier: {r.get('issue', 'contradiction')}"]
        for c in chosen:
            f = facts[c["id"]]
            why, source = llm_items.get(c["id"]), "explain-llm"
            if why and issues.get(c["id"]):
                rejected.append({"id": c["id"], "issues": issues[c["id"]], "text": why})
                self.rejections += 1
                why = None
            if not why:
                why = self.template(c, f)
                source = "interpret-llm" if c["kind"] == "read" else "template"
            if not why:
                continue
            st.explained_ids.add(c["id"])
            b.explained.append({**c, "facts": f, "why": why, "source": source})
        if entry is not None:
            entry.update({"chosen": [c["id"] for c in chosen], "candidates": len(cands),
                          "factcheck_rejected": rejected})
        return b


# =========================================================================== 4. RENDER
class RenderAgent:
    """Turns explanations into schema-valid overlay cards (type, priority, ttl, text, viz hints)."""
    name = "render"

    def __init__(self, state: RoomState):
        self.st = state

    async def run(self, b: Batch, entry: dict | None = None) -> Batch:
        for e in b.explained:
            ev, f = e.get("event", {}), e["facts"]
            kind = {"goal": "goal", "shot": "chance", "card": "card", "substitution": "substitution",
                    "pass": "stat", "period_end": "period", "match_end": "period", "phase_change": "phase",
                    "tactical_read": "insight"}.get(f["moment"], "insight")
            viz = {"kind": "none"}
            if kind in ("goal", "chance"):
                shot = ev if ev.get("type") == "shot" else next(
                    (s for s in reversed(self.st.spadl) if s["type_name"] == "shot"), None)
                if shot:
                    viz = {"kind": "shot_marker", "x": shot.get("x", shot.get("start_x")),
                           "y": shot.get("y", shot.get("start_y")), "team": ev.get("team"),
                           "value": f.get("xg")}
            elif kind == "stat" and ev:
                viz = {"kind": "pass_arrow", "x": ev["x"], "y": ev["y"], "end_x": ev["end_x"], "end_y": ev["end_y"],
                       "team": ev["team"], "value": f.get("xt_added")}
            elif kind in ("phase", "insight"):
                viz = {"kind": "control_gauge", "value": self.st.index.get("chaos")}
            elif kind in ("card", "substitution", "period"):
                viz = {"kind": "badge", "value": f.get("card", kind)}
            priority = 1 + min(4, int(e["score"] * 5))
            title = card_title({"type": kind, "facts": f, "title": kind}, "en")
            card = {"id": e["id"], "type": kind, "priority": priority,
                    "ttl_s": {5: 20, 4: 14, 3: 10}.get(priority, 8), "minute": int(f.get("minute", self.st.minute)),
                    "title": title[:60], "text": e["why"][:400], "team": ev.get("team") or e.get("insight", {}).get("team"),
                    "player_id": ev.get("player_id"), "viz": viz, "facts": f,
                    "verified": True, "source": e["source"]}
            assert not validate_card(card), validate_card(card)
            b.cards.append(card)
        b.cards.sort(key=lambda c: -c["priority"])
        return b


# Fixed, human-checked card titles per language (the LLM never writes titles).
TITLES = {
    "en": {"goal": "GOAL · {score}", "chance": "Chance · {player}", "yellow": "Yellow card", "red": "Red card",
           "second_yellow": "Second yellow", "substitution": "Substitution", "stat": "Threat-adding pass",
           "half": "Half-time · {score}", "full": "Full-time · {score}", "phase": "Phase shift",
           "insight": "Tactical read"},
    "es": {"goal": "GOL · {score}", "chance": "Ocasión · {player}", "yellow": "Tarjeta amarilla",
           "red": "Tarjeta roja", "second_yellow": "Segunda amarilla", "substitution": "Cambio",
           "stat": "Pase peligroso", "half": "Descanso · {score}", "full": "Final · {score}",
           "phase": "Cambio de fase", "insight": "Lectura táctica"},
    "fr": {"goal": "BUT · {score}", "chance": "Occasion · {player}", "yellow": "Carton jaune",
           "red": "Carton rouge", "second_yellow": "Deuxième jaune", "substitution": "Remplacement",
           "stat": "Passe dangereuse", "half": "Mi-temps · {score}", "full": "Fin du match · {score}",
           "phase": "Changement de phase", "insight": "Lecture tactique"},
}


def card_title(card: dict, lang: str) -> str:
    f = card.get("facts", {})
    key = card["type"]
    if key == "card":
        key = f.get("card", "yellow")
    elif key == "period":
        key = "half" if f.get("moment") == "period_end" and f.get("period") == 1 else "full"
    t = TITLES.get(lang, TITLES["en"]).get(key, TITLES["en"].get(key, card["title"]))
    return t.format(score=f.get("score", ""), player=f.get("player", ""))[:60]


# =========================================================================== 5. PERSONALISE
LANGS = {"en": "English", "es": "Spanish (Spain)", "fr": "French"}


class PersonaliseAgent:
    """Analyst vs fan, language, favourite club/player, with persistent viewer memory."""
    name = "personalise"
    instructions = ("You personalise live football overlay cards for one viewer. Keep every player and team name "
                    "exactly as written and never add facts or numbers that are not in the card. "
                    "FAN mode: one punchy sentence (max 20 words) a supporter would say; keep the scorer's name on goals; "
                    "no numbers except the score, no decimals, speeds or distances, no "
                    "jargon (no xG, xT, index), at most one exclamation mark. Be warm but fair: credit good play by EITHER team, "
                    "never mock, insult or belittle the opponent or the referee, no 'we/us/our'. Add a little extra warmth only when "
                    "the viewer's favourite club or player is involved, and name the favourite player when they are in the card. ANALYST mode: max 2 sentences, keep all numbers. "
                    "NEUTRAL mode: max 2 plain sentences for a casual viewer, no club bias, keep numbers but name metrics in plain words. "
                    "A control index is not possession. Return EVERY card you receive, same ids. Write in the target language. Reply as JSON: {\"cards\":[{\"id\":\"...\",\"text\":\"...\"}]}")

    def __init__(self, state: RoomState, brain: Brain, memory: ViewerMemory):
        self.st, self.brain, self.memory = state, brain, memory

    @staticmethod
    def fan_trim(text: str) -> str:
        import re
        text = re.sub(r"\s*\([^)]*(xG|xT|index)[^)]*\)", "", text)
        text = re.sub(r"\s*The chance was worth [\d.]+ xG\.", "", text)
        return text.strip()

    async def run(self, b: Batch, entry: dict | None = None) -> Batch:
        p = b.profile
        out = []
        for c in b.cards:
            c = dict(c)
            if p.club and c.get("team") == p.club:
                c["priority"] = min(5, c["priority"] + 1)
            c["title"] = card_title(c, p.language)
            if p.club and c.get("team") == p.club:
                c["fav"] = "club"
            if p.player and c.get("player_id") == p.player:
                c["priority"] = 5
                c["fav"] = "player"
                c["title"] = ("★ " + c["title"])[:60]
            if p.mode == "fan" and c["type"] == "stat" and c["priority"] < 4:
                continue  # fans skip routine metric cards
            if p.mode == "fan":
                c["text"] = self.fan_trim(c["text"])
            out.append(c)
        if out and (p.mode in ("fan", "neutral") or p.language != "en") and self.brain.online:
            club = self.st.team_name(p.club) if p.club else "none"
            player = self.st.player_name(p.player) if p.player else "none"
            prompt = (f"Viewer: mode={p.mode.upper()}, language={LANGS.get(p.language, p.language)}, "
                      f"favourite club={club}, favourite player={player}. Memory: {self.memory.summary(p.viewer_id)}\n"
                      "Cards:\n" + "\n".join(json.dumps({"id": c["id"], "text": c["text"]},
                                                        ensure_ascii=False) for c in out))
            data = parse_json(await self.brain.ask(prompt, entry))
            rewritten = {i.get("id"): i for i in (data or {}).get("cards", []) if isinstance(i, dict)} if isinstance(data, dict) else {}
            def problems(c: dict, r: dict) -> list[str]:
                txt = r["text"] + " " + r.get("title", "")
                ok, bad = factcheck.check(txt, c["text"], c["title"], c.get("facts", {}))
                f = c.get("facts", {})
                iss = [f"unsupported number {n}" for n in bad]
                iss += semantic.check(r["text"], f, self.st.snapshot(), self.st.meta, self.st.roster())
                if p.mode == "fan":
                    iss += semantic.fan_violations(r["text"], f)
                return iss

            todo = {c["id"]: c for c in out}
            issues = {cid: problems(todo[cid], r) for cid, r in rewritten.items()
                      if cid in todo and isinstance(r, dict) and r.get("text")}
            missing = [cid for cid in todo if cid not in issues]
            bad = [cid for cid, i in issues.items() if i]
            if (bad or missing) and self.brain.online:  # one repair round: rule violations + omitted cards
                prompt = (f"Fix these cards for a {p.mode.upper()} viewer in {LANGS.get(p.language, p.language)}. "
                          "Resolve every listed issue; same JSON format.\n" + "\n".join(json.dumps(
                              {"id": cid, "title": todo[cid]["title"], "source_text": todo[cid]["text"],
                               "draft": rewritten.get(cid, {}).get("text"), "issues": issues.get(cid, ["missing"])},
                              ensure_ascii=False) for cid in bad + missing))
                fixed = parse_json(await self.brain.ask(prompt, None))
                for r in (fixed or {}).get("cards", []) if isinstance(fixed, dict) else []:
                    if isinstance(r, dict) and r.get("id") in todo and r.get("text"):
                        iss = problems(todo[r["id"]], r)
                        if not iss:
                            rewritten[r["id"]], issues[r["id"]] = r, []
            rejected = []
            for c in out:
                r = rewritten.get(c["id"])
                if not r or not r.get("text") or issues.get(c["id"], ["missing"]):
                    if r and issues.get(c["id"]):
                        rejected.append({"id": c["id"], "issues": issues[c["id"]], "text": r.get("text")})
                    continue
                c["text"] = r["text"][:400]  # title stays the fixed per-language one
                c["source"] += "+personalised"
            if safety.enabled():  # Azure AI Content Safety on every AI-rewritten line
                ai = [c for c in out if "+personalised" in c["source"]]
                res = await safety.analyze([c["text"] for c in ai]) if ai else []
                for c, r in zip(ai, res):
                    c["safety"] = r
                    if not safety.safe(r):
                        c["source"] = c["source"].replace("+personalised", "")
                        c["text"] = localise.rule_text(c, "en") or c["text"]
                        rejected.append({"id": c["id"], "issues": ["content safety"], "text": None})
            if entry is not None:
                entry["factcheck_rejected"] = rejected
        for c in out:
            if "+personalised" not in c["source"] and (p.language != "en" or p.mode == "fan"):
                t = localise.rule_text(c, p.language)  # never fall back to English when another language is chosen
                if t:
                    c["text"], c["source"] = t[:400], c["source"] + "+localised"
            c["lang"] = p.language if ("+personalised" in c["source"] or "+localised" in c["source"]
                                       or p.language == "en") else "en"
            assert not validate_card(c)
        self.memory.record_cards(p.viewer_id, out)
        b.cards = out
        return b
