"""Fictional teams and players. Any resemblance to real clubs or people is unintended."""
from __future__ import annotations
from dataclasses import dataclass, field

POSITIONS = ["GK", "RB", "CB", "CB", "LB", "DM", "CM", "CM", "RW", "ST", "LW"]
BENCH_POS = ["GK", "CB", "CM", "CM", "RW", "ST", "LB"]


@dataclass
class Player:
    id: str
    name: str
    number: int
    position: str
    skill: float  # 0..1 passing/finishing quality (fictional rating)


@dataclass
class Team:
    id: str
    name: str
    short: str
    color: str
    strength: float  # 0..1 fictional rating
    players: list[Player] = field(default_factory=list)
    bench: list[Player] = field(default_factory=list)


_FIRST = ["Ari", "Bram", "Cael", "Dario", "Eno", "Faro", "Gael", "Hugo", "Ivo", "Joss", "Kian",
          "Leno", "Milo", "Nilo", "Oren", "Pax", "Quin", "Rafe", "Soren", "Tavi", "Ulric", "Vero",
          "Wren", "Xan", "Yuri", "Zeno", "Arlo", "Bento", "Cyro", "Davo", "Emil", "Fenn", "Gus",
          "Hale", "Ilan", "Jaro"]
_LAST = ["Ashgrove", "Brightwater", "Coldbeck", "Dunmere", "Elmsworth", "Fairholt", "Greywick",
         "Hollins", "Ivesby", "Jarrow-Lake", "Kestrel", "Larkfield", "Mossley", "Northam", "Oakhurst",
         "Pellam", "Quarry", "Redfern", "Stonebridge", "Thornby", "Underhill", "Vance", "Westmoor",
         "Yarrow", "Zellick", "Amberley", "Birchall", "Calder", "Dovecote", "Emberton", "Foxley",
         "Gorsefield", "Hartwell", "Ingleby", "Juniper", "Kilnsey"]


def _squad(prefix: str, offset: int, base: float) -> tuple[list[Player], list[Player]]:
    xi, bench = [], []
    for i, pos in enumerate(POSITIONS + BENCH_POS):
        k = (i + offset) % len(_FIRST)
        p = Player(id=f"{prefix}{i + 1}", name=f"{_FIRST[k]} {_LAST[(k * 7 + offset) % len(_LAST)]}",
                   number=i + 1 if i < 11 else 12 + i - 11, position=pos,
                   skill=round(min(0.95, base + ((i * 37 + offset) % 11) / 50), 2))
        (xi if i < 11 else bench).append(p)
    return xi, bench


def default_teams() -> tuple[Team, Team]:
    h_xi, h_b = _squad("H", 0, 0.55)
    a_xi, a_b = _squad("A", 18, 0.50)
    home = Team("harbour", "Harbour City Mariners", "HCM", "#1f6feb", 0.58, h_xi, h_b)
    away = Team("ridge", "Ironridge Rovers", "IRR", "#d4380d", 0.52, a_xi, a_b)
    return home, away


# Extra fictional clubs for the match selector (synthetic; names invented, colours arbitrary).
_POOL = {
    "harbour": ("Harbour City Mariners", "HCM", "#1f6feb", 0.58),
    "ridge": ("Ironridge Rovers", "IRR", "#d4380d", 0.52),
    "falcons": ("Northgate Falcons", "NGF", "#8957e5", 0.60),
    "lowmoor": ("Lowmoor Athletic", "LMA", "#2ea043", 0.49),
    "vale": ("Silverdale Vale", "SDV", "#e3b341", 0.55),
    "quarry": ("Quarrytown United", "QTU", "#db61a2", 0.54),
    "kestrel": ("Kestrel Bay Wanderers", "KBW", "#0ea5a4", 0.53),
    "thorn": ("Thornbury Forge", "TBF", "#a16207", 0.51),
    "aurora": ("Aurora Heights", "AUH", "#ec4899", 0.57),
    "millbrook": ("Millbrook Town", "MBT", "#64748b", 0.47),
    "eastmere": ("Eastmere Ravens", "EMR", "#111827", 0.56),
    "copper": ("Coppervale Miners", "CVM", "#c2410c", 0.50),
    "highmoor": ("Highmoor Stags", "HMS", "#15803d", 0.53),
    "saltmarsh": ("Saltmarsh Herons", "SMH", "#0284c7", 0.48),
    "granite": ("Granite Point FC", "GPF", "#6b7280", 0.55),
    "wyvern": ("Wyvern Lane Athletic", "WLA", "#7c3aed", 0.52),
}
SECONDARY = {"harbour": "#ffffff", "ridge": "#111827", "falcons": "#f5d90a", "lowmoor": "#ffffff", "vale": "#1e3a8a",
             "quarry": "#111827", "kestrel": "#fde68a", "thorn": "#1f2937", "aurora": "#fef3c7", "millbrook": "#f59e0b",
             "eastmere": "#e5e7eb", "copper": "#fde68a", "highmoor": "#fef9c3", "saltmarsh": "#ffffff",
             "granite": "#dc2626", "wyvern": "#a7f3d0"}
STADIUM = {k: v[0].split()[0] + " " + ("Park", "Ground", "Arena", "Road", "Stadium")[i % 5] for i, (k, v) in enumerate(_POOL.items())}

# seed -> (home, away, label). Seeds not listed use the default Harbour v Ironridge pairing.
FIXTURES = {
    7: ("harbour", "ridge", "Showcase · Harbour Bowl"),
    11: ("falcons", "lowmoor", "Showcase · Northgate Park"),
    23: ("vale", "quarry", "Showcase · Silverdale Ground"),
    42: ("quarry", "harbour", "Showcase · Quarry Lane"),
    58: ("ridge", "falcons", "Showcase · Ironridge Works"),
}


def make_team(key: str, offset: int) -> Team:
    name, short, color, strength = _POOL[key]
    xi, bench = _squad(short, offset, strength - 0.03)
    return Team(key, name, short, color, strength, xi, bench)


def teams_for_seed(seed: int) -> tuple[Team, Team]:
    if seed not in FIXTURES or (seed < 1000 and FIXTURES[seed][:2] == ("harbour", "ridge")):
        return default_teams()
    h, a, _ = FIXTURES[seed]
    keys = list(_POOL)
    return make_team(h, keys.index(h) * 5), make_team(a, keys.index(a) * 5)  # same squad home and away


# ------------------------------------------------------------------ fictional league: 16 clubs, round robin
LEAGUE_NAME = "Coastal League (fictional)"
LEAGUE_DAYS = 30  # full double round robin for 16 clubs


def _round_robin(keys: list[str]) -> list[list[tuple[str, str]]]:
    n, ks, rounds = len(keys), list(keys), []
    for d in range(n - 1):
        pairs = [(ks[i], ks[n - 1 - i]) for i in range(n // 2)]
        rounds.append([(a, b) if (d + i) % 2 == 0 else (b, a) for i, (a, b) in enumerate(pairs)])
        ks = [ks[0]] + [ks[-1]] + ks[1:-1]
    return rounds


_RR = _round_robin(list(_POOL))
_RR = _RR + [[(b, a) for a, b in rnd] for rnd in _RR]  # second half of the season: reverse fixtures
for _d, _rnd in enumerate(_RR[:LEAGUE_DAYS], start=1):
    for _k, (_h, _a) in enumerate(_rnd):
        FIXTURES[1000 + _d * 10 + _k] = (_h, _a, f"Matchday {_d} · {STADIUM[_h]}")


def club_list() -> list[dict]:
    return [{"id": k, "name": v[0], "short": v[1], "color": v[2], "secondary": SECONDARY[k], "rating": v[3],
             "stadium": STADIUM[k], "crest": f"/api/crest/{k}.svg"} for k, v in _POOL.items()]


def crest_svg(key: str) -> str:
    """Generated crest: shield in club colours + short code. No real marks."""
    name, short, c1, _ = _POOL[key]
    c2 = SECONDARY[key]
    style = sum(map(ord, key)) % 3
    deco = [f'<path d="M50 6 V112" stroke="{c2}" stroke-width="16"/>',
            f'<path d="M8 40 L92 40 L92 58 L8 58 Z" fill="{c2}"/>',
            f'<path d="M8 8 L92 92" stroke="{c2}" stroke-width="14"/>'][style]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 120" role="img" aria-label="{name} crest">'
            f'<defs><clipPath id="s"><path d="M8 6 H92 V60 C92 90 70 108 50 116 C30 108 8 90 8 60 Z"/></clipPath></defs>'
            f'<g clip-path="url(#s)"><rect width="100" height="120" fill="{c1}"/>{deco}</g>'
            f'<path d="M8 6 H92 V60 C92 90 70 108 50 116 C30 108 8 90 8 60 Z" fill="none" stroke="#fff" stroke-width="4"/>'
            f'<rect x="20" y="68" width="60" height="24" rx="5" fill="#0b1120cc"/>'
            f'<text x="50" y="86" font-family="Arial,sans-serif" font-weight="700" font-size="17" fill="#fff" '
            f'text-anchor="middle">{short}</text></svg>')


def fixture_list() -> list[dict]:
    return [{"seed": s, "home_id": h, "away_id": a, "matchday": int(lbl.split()[1]) if lbl.startswith("Matchday") and s >= 1000 else 0,
             "competition": LEAGUE_NAME if s >= 1000 else "Showcase friendly", "home": _POOL[h][0], "away": _POOL[a][0], "home_short": _POOL[h][1],
             "away_short": _POOL[a][1], "home_color": _POOL[h][2], "away_color": _POOL[a][2], "label": lbl}
            for s, (h, a, lbl) in FIXTURES.items()]
