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
}

# seed -> (home, away, label). Seeds not listed use the default Harbour v Ironridge pairing.
FIXTURES = {
    7: ("harbour", "ridge", "Matchday 1 · Harbour Bowl"),
    11: ("falcons", "lowmoor", "Matchday 2 · Northgate Park"),
    23: ("vale", "quarry", "Matchday 3 · Silverdale Ground"),
    42: ("quarry", "harbour", "Matchday 4 · Quarry Lane"),
    58: ("ridge", "falcons", "Matchday 5 · Ironridge Works"),
}


def make_team(key: str, offset: int) -> Team:
    name, short, color, strength = _POOL[key]
    xi, bench = _squad(short[0] + short[-1], offset, strength - 0.03)
    return Team(key, name, short, color, strength, xi, bench)


def teams_for_seed(seed: int) -> tuple[Team, Team]:
    if seed not in FIXTURES or FIXTURES[seed][:2] == ("harbour", "ridge"):
        return default_teams()
    h, a, _ = FIXTURES[seed]
    keys = list(_POOL)
    return make_team(h, keys.index(h) * 5), make_team(a, keys.index(a) * 5 + 3)


def fixture_list() -> list[dict]:
    return [{"seed": s, "home": _POOL[h][0], "away": _POOL[a][0], "home_short": _POOL[h][1],
             "away_short": _POOL[a][1], "home_color": _POOL[h][2], "away_color": _POOL[a][2], "label": lbl}
            for s, (h, a, lbl) in FIXTURES.items()]
