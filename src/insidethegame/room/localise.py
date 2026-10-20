"""Deterministic, human-written fallback lines per language and persona.

Used whenever the Personalise agent's rewrite is unavailable (no LLM, budget skip) or rejected by the checks, so a
viewer who picked Spanish or French never sees an English card. Only facts already in the card are used."""
from __future__ import annotations

T = {
    "en": {
        "goal": "{player} scores for {team}! {score}.",
        "shot": {"saved": "{player} forces a save for {team}.", "blocked": "{player}'s shot is blocked.",
                 "off_target": "{player} shoots wide for {team}.", "goal": "{player} scores for {team}!"},
        "yellow": "Yellow card for {player} ({team}).", "red": "Red card: {player} ({team}) is sent off.",
        "second_yellow": "Second yellow: {player} ({team}) is sent off.",
        "substitution": "{team} change: {player_on} on, {player_off} off.",
        "pass": "{player} plays a dangerous pass for {team}.",
        "half": "Half-time: {score}.", "full": "Full-time: {score}.",
        "phase": {"siege": "{team} are camped in the final third.", "high_press": "{team} are pressing high.",
                  "chaos": "End-to-end spell: the ball keeps changing hands.",
                  "control": "{team} are controlling the ball and the tempo.",
                  "balanced": "A balanced spell, nobody dominating."},
        "tactical_read": "The balance of the game is shifting.",
    },
    "es": {
        "goal": "¡Gol de {player} para {team}! {score}.",
        "shot": {"saved": "{player} obliga al portero a intervenir.", "blocked": "Bloquean el disparo de {player}.",
                 "off_target": "{player} dispara fuera ({team}).", "goal": "¡Gol de {player}!"},
        "yellow": "Tarjeta amarilla para {player} ({team}).", "red": "Roja directa: {player} ({team}) expulsado.",
        "second_yellow": "Segunda amarilla: {player} ({team}) expulsado.",
        "substitution": "Cambio en {team}: entra {player_on}, sale {player_off}.",
        "pass": "Pase peligroso de {player} para {team}.",
        "half": "Descanso: {score}.", "full": "Final del partido: {score}.",
        "phase": {"siege": "{team} encierra a su rival en su área.", "high_press": "{team} presiona muy arriba.",
                  "chaos": "Partido de ida y vuelta: el balón cambia de dueño sin parar.",
                  "control": "{team} controla el balón y el ritmo.",
                  "balanced": "Fase equilibrada, nadie domina."},
        "tactical_read": "El equilibrio del partido está cambiando.",
    },
    "fr": {
        "goal": "But de {player} pour {team} ! {score}.",
        "shot": {"saved": "{player} oblige le gardien à s'interposer.", "blocked": "La frappe de {player} est contrée.",
                 "off_target": "{player} tire à côté ({team}).", "goal": "But de {player} !"},
        "yellow": "Carton jaune pour {player} ({team}).", "red": "Carton rouge : {player} ({team}) est expulsé.",
        "second_yellow": "Deuxième jaune : {player} ({team}) est expulsé.",
        "substitution": "Changement pour {team} : {player_on} entre, {player_off} sort.",
        "pass": "Passe dangereuse de {player} pour {team}.",
        "half": "Mi-temps : {score}.", "full": "Fin du match : {score}.",
        "phase": {"siege": "{team} campe dans le dernier tiers.", "high_press": "{team} presse très haut.",
                  "chaos": "Séquence décousue : le ballon change sans cesse de camp.",
                  "control": "{team} contrôle le ballon et le rythme.",
                  "balanced": "Phase équilibrée, personne ne domine."},
        "tactical_read": "L'équilibre du match évolue.",
    },
}


class _D(dict):
    def __missing__(self, k):
        return ""


def rule_text(card: dict, lang: str) -> str | None:
    """Localised line for a card from its facts, or None if no template fits."""
    t = T.get(lang)
    if not t:
        return None
    f = card.get("facts", {})
    m = f.get("moment")
    if m == "goal":
        tpl = t["goal"]
    elif m == "shot":
        tpl = t["shot"].get(f.get("outcome"), t["shot"]["off_target"])
    elif m == "card":
        tpl = t.get(f.get("card", "yellow"), t["yellow"])
    elif m in ("substitution", "pass", "tactical_read"):
        tpl = t[m]
    elif m == "period_end":
        tpl = t["half"]
    elif m == "match_end":
        tpl = t["full"]
    elif m == "phase_change":
        tpl = t["phase"].get(f.get("new_phase"), t["phase"]["balanced"])
    else:
        return None
    return tpl.format_map(_D(f)).replace(" ()", "").strip()


def ensure(cards: list[dict], lang: str, mode: str) -> list[dict]:
    """Last-line guard after the whole room: any card not in the viewer's language (e.g. an agent failed and the
    workflow passed its input through) gets the localised rules line. Fan cards get it too if they are not personalised."""
    out = []
    for c in cards:
        c = dict(c)
        wrong = c.get("lang", "en" if "+personalised" not in str(c.get("source")) else lang) != lang
        raw_fan = mode == "fan" and not any(k in str(c.get("source")) for k in ("+personalised", "+localised"))
        if wrong or raw_fan or "lang" not in c:
            t = rule_text(c, lang)
            if t and (wrong or raw_fan or lang != "en"):
                c["text"], c["source"] = t[:400], str(c.get("source")) + "+localised"
            c["lang"] = lang if t or lang == "en" else c.get("lang", "en")
        out.append(c)
    return out
