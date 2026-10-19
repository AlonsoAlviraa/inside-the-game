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
