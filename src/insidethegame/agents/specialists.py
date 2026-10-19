"""Specialist agents: Stats, Tactics (control vs chaos), Narrator, Personaliser."""
from __future__ import annotations
from collections import defaultdict

from ..metrics import ControlChaosIndex
from .base import AgentOutput, MatchState, ViewerProfile
from .llm import LLMClient


class StatsAgent:
    name = "stats"
    instructions = "Deterministic aggregation of synthetic events into team and player statistics."

    def __init__(self) -> None:
        self.index: ControlChaosIndex | None = None

    async def handle(self, ev: dict, st: MatchState) -> list[AgentOutput]:
        if ev["type"] == "match_start":
            st.meta = ev["meta"]
            h, a = st.meta["home"]["id"], st.meta["away"]["id"]
            st.score = {h: 0, a: 0}
            st.team_stats = {t: defaultdict(float) for t in (h, a)}
            st.player_stats = defaultdict(lambda: defaultdict(float))
            self.index = ControlChaosIndex(h, a)
            return []
        st.minute = ev["minute"]
        out: list[AgentOutput] = []
        team, ts = ev.get("team"), st.team_stats.get(ev.get("team"))
        if ev["type"] == "pass" and ts is not None:
            ts["passes"] += 1
            ts["passes_ok"] += ev["success"]
            ps = st.player_stats[ev["player_id"]]
            ps["passes"] += 1
            ps["quality_sum"] += ev["quality"]
            if ev["speed_kmh"] > 90 and ev["success"]:
                out.append(AgentOutput(self.name, "stat", f"{ev['player']} zips a {ev['length_m']:.0f} m pass at "
                                       f"{ev['speed_kmh']:.0f} km/h", 0.3, {"player_id": ev["player_id"]}))
        elif ev["type"] == "shot" and ts is not None:
            ts["shots"] += 1
            ts["xg"] += ev["xg"]
            ts["on_target"] += ev["outcome"] in ("goal", "saved")
            st.player_stats[ev["player_id"]]["shots"] += 1
            st.player_stats[ev["player_id"]]["xg"] += ev["xg"]
            out.append(AgentOutput(self.name, "stat", f"Shot {ev['speed_kmh']:.0f} km/h from {ev['distance_m']:.0f} m, "
                                   f"xG {ev['xg']:.2f}", 0.6, {"player_id": ev["player_id"], "xg": ev["xg"]}))
        elif ev["type"] == "goal":
            st.score = dict(ev["score"])
            st.player_stats[ev["player_id"]]["goals"] += 1
        elif ev["type"] == "card" and ts is not None:
            ts["cards"] += 1
        if self.index is not None:
            st.index = self.index.update(ev)
        return out


class TacticsAgent:
    name = "tactics"
    instructions = ("You are a tactical analyst. Explain in one sentence WHY the current phase matters, "
                    "using the control-vs-chaos index. Never invent facts beyond the provided numbers.")

    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.last_minute = -10

    async def handle(self, ev: dict, st: MatchState) -> list[AgentOutput]:
        if not st.index or ev["type"] in ("match_start",):
            return []
        label = st.index["label"]
        changed = label != st.last_label
        if not changed or st.minute - self.last_minute < 3:
            return []
        st.last_label, self.last_minute = label, st.minute
        ctrl = st.index["control"]
        lead = max(ctrl, key=ctrl.get)
        name = st.team_name(lead)
        if label == "chaos":
            tmpl = (f"Chaos phase (index {st.index['chaos']:.2f}): turnovers and pressing are breaking up play - "
                    f"transitions now matter more than build-up.")
        elif label == "control":
            tmpl = (f"{name} take control ({ctrl[lead]:.2f}): more of the ball and more entries into the final third, "
                    f"so the opponent is being pinned back.")
        else:
            tmpl = "The game settles into balance - neither side is dictating territory right now."
        text = await self.llm.complete(self.instructions, f"Index: {st.index}. Minute {st.minute}.", fallback=tmpl)
        st.notes.append(f"{st.minute}': {label}")
        return [AgentOutput(self.name, "tactic", text, 0.7, {"index": st.index, "label": label})]


class NarratorAgent:
    name = "narrator"
    instructions = ("You are a live football commentator. One vivid, factual English sentence about the event, "
                    "using only the provided data. Mention the tactical context note if given.")

    KEY = {"goal", "shot", "card", "substitution", "period_end", "match_end", "period_start"}

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def handle(self, ev: dict, st: MatchState) -> list[AgentOutput]:
        t = ev["type"]
        if t not in self.KEY:
            return []
        tn = st.team_name(ev.get("team"))
        sc = st.score
        names = [st.meta.get("home", {}).get("short", "H"), st.meta.get("away", {}).get("short", "A")]
        score_txt = f"{names[0]} {list(sc.values())[0]}-{list(sc.values())[1]} {names[1]}" if sc else ""
        if t == "goal":
            tmpl, imp = f"GOAL! {ev['player']} scores for {tn} (xG {ev['xg']:.2f}). {score_txt}.", 1.0
            if ev["xg"] < 0.08:
                tmpl += " A low-probability finish - that one came from almost nothing."
        elif t == "shot":
            if ev["outcome"] == "goal":
                return []
            verb = {"saved": "forces a save", "blocked": "is blocked", "off_target": "fires wide"}[ev["outcome"]]
            tmpl, imp = f"{ev['player']} ({tn}) {verb} from {ev['distance_m']:.0f} m.", 0.6
        elif t == "card":
            tmpl, imp = f"{ev['card'].replace('_', ' ').title()} card for {ev['player']} of {tn}.", 0.7
        elif t == "substitution":
            tmpl, imp = f"{tn} change: {ev['player_on']} on for {ev['player_off']}.", 0.4
        elif t == "period_start":
            tmpl, imp = "The second half is under way.", 0.5
        else:
            label = "Half-time" if t == "period_end" and ev.get("period") == 1 else "Full-time"
            tmpl, imp = f"{label}: {score_txt}.", 0.9
        ctx = st.notes[-1] if st.notes else ""
        text = await self.llm.complete(self.instructions, f"Event: {ev}. Context: {ctx}", fallback=tmpl)
        return [AgentOutput(self.name, "narration", text, imp,
                            {"event_type": t, "team": ev.get("team"), "player_id": ev.get("player_id")})]


_TR = {
    "es": {"GOAL!": "¡GOL!", "scores for": "marca para", "Half-time": "Descanso", "Full-time": "Final",
           "forces a save": "obliga al portero a intervenir", "is blocked": "ve su disparo bloqueado",
           "fires wide": "dispara fuera", "from": "desde", "card for": "tarjeta para", "of": "de",
           "Yellow": "Amarilla", "Red": "Roja", "change:": "cambio:", "on for": "entra por",
           "The second half is under way.": "Arranca la segunda parte.", "Shot": "Disparo"},
    "fr": {"GOAL!": "BUT !", "scores for": "marque pour", "Half-time": "Mi-temps", "Full-time": "Fin du match",
           "forces a save": "oblige le gardien à s'employer", "is blocked": "est contré",
           "fires wide": "tire à côté", "from": "à", "card for": "carton pour", "of": "de",
           "Yellow": "Jaune", "Red": "Rouge", "change:": "changement :", "on for": "remplace",
           "The second half is under way.": "La seconde période est lancée.", "Shot": "Tir"},
}


_LANG_NAMES = {"en": "English", "es": "Spanish (Spain)", "fr": "French"}


class PersonaliserAgent:
    name = "personaliser"
    instructions = ("Rewrite the commentary for the viewer profile: 'fan' = short, emotional, no jargon; "
                    "'analyst' = keep numbers, add metric context. Translate to the target language. "
                    "Boost items about the favourite club or player.")

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def _mock_translate(self, text: str, lang: str) -> str:
        for k, v in sorted(_TR.get(lang, {}).items(), key=lambda kv: -len(kv[0])):
            text = text.replace(k, v)
        return text

    async def personalise(self, item: AgentOutput, profile: ViewerProfile, st: MatchState) -> AgentOutput | None:
        imp = item.importance
        d = item.data
        if profile.club and d.get("team") == profile.club:
            imp = min(1.0, imp + 0.2)
        if profile.player and d.get("player_id") == profile.player:
            imp = min(1.0, imp + 0.4)
        if profile.mode == "fan":
            if item.kind == "stat" and imp < 0.7:
                return None  # fans don't need every speed reading
            text = item.text.split(" (xG")[0] + ("." if " (xG" in item.text else "")
            if item.kind == "tactic":
                text = text.split(":")[0] + "!" if ":" in text else text
        else:
            text = item.text
            if item.kind == "tactic" and st.index:
                text += f" [control {st.index['control']}, chaos {st.index['chaos']}]"
        fallback = self._mock_translate(text, profile.language) if profile.language != "en" else text
        if profile.language != "en" or profile.mode == "fan":
            lang_name = _LANG_NAMES.get(profile.language, profile.language)
            prompt = (f"Viewer mode: {profile.mode}. Favourite club: {profile.club or 'none'}. "
                      f"Favourite player: {profile.player or 'none'}. Target language: {lang_name}.\n"
                      f"Source commentary (English): {text}\n"
                      f"Reply with only the rewritten commentary, entirely in {lang_name}, max 2 sentences. "
                      "Keep player and team names unchanged.")
            text = await self.llm.complete(self.instructions, prompt, fallback=fallback)
        return AgentOutput(self.name, item.kind, text, round(imp, 2), {**d, "source_agent": item.agent})
