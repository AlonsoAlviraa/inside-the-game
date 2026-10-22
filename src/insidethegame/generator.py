"""Seeded synthetic match generator.

Modelling assumptions (all synthetic, chosen for plausibility, not calibrated to any real league):
* Ball-in-play is ~58% of the 90 minutes; dead-ball gaps of 2-25 s separate possessions.
* A possession is a chain of passes. Each pass takes 0.8-3.5 s of flight + 0.5-2.5 s on the ball.
* Pass success probability = 0.93 - 0.35*difficulty + 0.08*(passer skill - 0.5) + 0.04*(team strength - 0.5).
* Opponent pressure on the ball is sampled per action and rises in the final third.
* In the final third (x > 70) each action may become a shot (p = 0.015 + 0.09*((x-70)/35)^1.5).
* Goals are drawn from the xG model in `metrics.xg` scaled by finisher skill.
* Fouls ~ 2.5% of on-ball actions (~25 per match), ~18% lead to a yellow card; reds are rare (~2% of fouls).
* Each side makes up to 5 substitutions after minute 55.
Coordinates are in the attacking frame of the team in possession: x in [0,105] towards the
opponent goal, y in [0,68]. Every event carries `team` so a renderer can mirror the away side.
"""
from __future__ import annotations
import asyncio
import math
import random
from dataclasses import asdict
from typing import AsyncIterator, Iterator

from . import metrics
from .teams import Team, Player, teams_for_seed, STADIUM

HALF_S = 45 * 60


class MatchGenerator:
    def __init__(self, seed: int = 7, home: Team | None = None, away: Team | None = None):
        self.seed = seed
        self.rng = random.Random(seed)
        if home is None or away is None:
            home, away = teams_for_seed(seed)
        self.home, self.away = home, away
        self.score = {home.id: 0, away.id: 0}
        self.on_pitch = {home.id: list(home.players), away.id: list(away.players)}
        self.bench = {home.id: list(home.bench), away.id: list(away.bench)}
        self.subs_made = {home.id: 0, away.id: 0}
        self.yellows: set[str] = set()
        self._seq = 0
        self._period, self._offset = 1, 0.0

    # ------------------------------------------------------------------ helpers
    def _ev(self, t: float, etype: str, **kw) -> dict:
        self._seq += 1
        # t = elapsed seconds since kick-off (monotonic, includes half-1 stoppage);
        # minute = match clock (second half restarts at 45:00, so stoppage reads e.g. 47 in half 1).
        clock = t - self._offset
        return {"id": self._seq, "t": round(t, 1), "minute": int(clock // 60) + 1, "period": self._period,
                "type": etype, **kw}

    def _team(self, tid: str) -> Team:
        return self.home if tid == self.home.id else self.away

    def _other(self, tid: str) -> str:
        return self.away.id if tid == self.home.id else self.home.id

    def _pick(self, tid: str, x: float, exclude: str | None = None) -> Player:
        pool = [p for p in self.on_pitch[tid] if p.position != "GK" and p.id != exclude] or self.on_pitch[tid]
        if x > 70:
            pool = [p for p in pool if p.position in ("ST", "LW", "RW", "CM")] or pool
        elif x < 35:
            pool = [p for p in pool if p.position in ("CB", "RB", "LB", "DM")] or pool
        return self.rng.choice(pool)

    def _clip(self, x: float, y: float) -> tuple[float, float]:
        return round(min(max(x, 0.5), 104.5), 1), round(min(max(y, 0.5), 67.5), 1)

    # ------------------------------------------------------------------ simulation
    def events(self) -> Iterator[dict]:
        r = self.rng
        yield self._ev(0, "match_start", meta={
            "home": {"id": self.home.id, "name": self.home.name, "short": self.home.short, "color": self.home.color,
                     "players": [asdict(p) for p in self.home.players + self.home.bench]},
            "away": {"id": self.away.id, "name": self.away.name, "short": self.away.short, "color": self.away.color,
                     "players": [asdict(p) for p in self.away.players + self.away.bench]},
            "venue": STADIUM.get(self.home.id, "Saltmarsh Park") + " (fictional)", "seed": self.seed, "synthetic": True})
        t = 0.0
        for period, (start, end) in enumerate([(0, HALF_S), (HALF_S, 2 * HALF_S)], start=1):
            if period == 2:
                self._period, self._offset = 2, max(0.0, t - HALF_S + 900)  # 15-min half-time interval
                t = HALF_S + self._offset
                start, end = t, t + HALF_S
            else:
                t = float(start)
            stoppage = r.uniform(60, 240 if period == 1 else 360)
            team = self.home.id if period == 1 else self.away.id
            if period == 2:
                yield self._ev(t, "period_start", period=2)
            x, y = 52.5, 34.0
            while t < end + stoppage:
                for ev in self._maybe_subs(t, period):
                    yield ev
                chain, t, team, x, y = self._possession(t, team, x, y)
                yield from chain
                t += r.uniform(2, 16)  # dead ball / restart time
            yield self._ev(t, "period_end", period=period, score=dict(self.score))
        yield self._ev(t, "match_end", score=dict(self.score))

    def _maybe_subs(self, t: float, period: int) -> list[dict]:
        out = []
        if period != 2 or t < 55 * 60:
            return out
        for tid in (self.home.id, self.away.id):
            if self.subs_made[tid] < 5 and self.bench[tid] and self.rng.random() < 0.05:
                outfield = [p for p in self.on_pitch[tid] if p.position != "GK"]
                off = self.rng.choice(outfield)
                on = next((b for b in self.bench[tid] if b.position != "GK"), None)
                if on is None:
                    continue
                self.bench[tid].remove(on)
                self.on_pitch[tid][self.on_pitch[tid].index(off)] = on
                self.subs_made[tid] += 1
                out.append(self._ev(t, "substitution", team=tid, player_off=off.name, player_on=on.name,
                                    player_off_id=off.id, player_on_id=on.id))
        return out

    def _possession(self, t: float, team: str, x: float, y: float):
        r = self.rng
        evs: list[dict] = []
        tm = self._team(team)
        evs.append(self._ev(t, "possession_start", team=team, x=round(x, 1), y=round(y, 1)))
        carrier = self._pick(team, x)
        for _ in range(40):
            pressure = min(1.0, max(0.0, r.gauss(0.25 + 0.35 * (x / 105), 0.18)))
            if pressure > 0.6:
                evs.append(self._ev(t, "pressure", team=self._other(team), on_player=carrier.name,
                                    on_player_id=carrier.id, x=round(105 - x, 1), y=round(68 - y, 1),
                                    intensity=round(pressure, 2)))
            # foul?
            if r.random() < 0.025:
                fouler = self._pick(self._other(team), 105 - x)
                evs.append(self._ev(t, "foul", team=self._other(team), player=fouler.name, player_id=fouler.id,
                                    on_player=carrier.name, x=round(x, 1), y=round(y, 1)))
                u = r.random()
                if u < 0.02 or (u < 0.2 and fouler.id in self.yellows):
                    evs.append(self._ev(t, "card", team=self._other(team), player=fouler.name, player_id=fouler.id,
                                        card="red" if u < 0.02 else "second_yellow"))
                    if fouler in self.on_pitch[self._other(team)]:
                        self.on_pitch[self._other(team)].remove(fouler)
                elif u < 0.2:
                    self.yellows.add(fouler.id)
                    evs.append(self._ev(t, "card", team=self._other(team), player=fouler.name,
                                        player_id=fouler.id, card="yellow"))
                return evs, t + r.uniform(15, 40), team, x, y  # free kick keeps possession
            # shot?
            shot_p = 0.0 if x < 70 else 0.015 + 0.09 * max(0, (x - 70) / 35) ** 1.5
            if r.random() < shot_p:
                return self._shot(evs, t, team, carrier, x, y, pressure)
            # pass
            dist = max(3.0, r.lognormvariate(2.6, 0.5))
            ang = r.gauss(0.25, 1.0)
            ex, ey = self._clip(x + dist * math.cos(ang), y + dist * math.sin(ang))
            if metrics.distance(x, y, ex, ey) < 2:  # clipped into a corner: play it back instead
                ex, ey = self._clip(x - dist, y)
            dist = max(1.0, metrics.distance(x, y, ex, ey))
            diff = metrics.pass_difficulty(dist, pressure, ex - x)
            p_ok = 0.93 - 0.35 * diff + 0.08 * (carrier.skill - 0.5) + 0.04 * (tm.strength - 0.5)
            ok = r.random() < p_ok
            flight = max(0.4, dist / r.uniform(12, 22))
            receiver = self._pick(team, ex, exclude=carrier.id)
            evs.append(self._ev(t, "pass", team=team, player=carrier.name, player_id=carrier.id,
                                receiver=receiver.name if ok else None, receiver_id=receiver.id if ok else None,
                                x=round(x, 1), y=round(y, 1), end_x=ex, end_y=ey, success=ok,
                                length_m=round(dist, 1), pressure=round(pressure, 2),
                                duration_s=round(flight, 2), speed_kmh=metrics.ball_speed_kmh(dist, flight),
                                difficulty=diff, quality=metrics.pass_quality(dist, pressure, ex - x, ok)))
            t += flight + r.uniform(0.5, 2.5)
            if not ok:
                opp = self._other(team)
                evs.append(self._ev(t, "turnover", team=opp, from_team=team, x=round(105 - ex, 1),
                                    y=round(68 - ey, 1)))
                return evs, t, opp, 105 - ex, 68 - ey
            carrier, x, y = receiver, ex, ey
        return evs, t, self._other(team), 105 - x, 68 - y

    def _shot(self, evs, t, team, shooter, x, y, pressure):
        r = self.rng
        header = r.random() < 0.15 and x > 90
        val = metrics.xg(x, y, pressure, header)
        p_goal = min(0.95, val * (0.8 + 0.4 * shooter.skill))
        u = r.random()
        speed = round(r.uniform(45, 70) if header else r.gauss(95, 15), 1)
        if u < p_goal:
            outcome = "goal"
        elif u < p_goal + 0.30:
            outcome = "saved"
        elif u < p_goal + 0.55:
            outcome = "blocked"
        else:
            outcome = "off_target"
        d, ang = metrics.shot_geometry(x, y)
        evs.append(self._ev(t, "shot", team=team, player=shooter.name, player_id=shooter.id,
                            x=round(x, 1), y=round(y, 1), xg=val, outcome=outcome, header=header,
                            speed_kmh=max(30.0, speed), distance_m=round(d, 1), pressure=round(pressure, 2)))
        opp = self._other(team)
        if outcome == "goal":
            self.score[team] += 1
            evs.append(self._ev(t, "goal", team=team, player=shooter.name, player_id=shooter.id,
                                score=dict(self.score), xg=val))
            return evs, t + r.uniform(40, 70), opp, 52.5, 34.0
        return evs, t + r.uniform(3, 10), opp, 8.0, 34.0


async def stream(seed: int = 7, speed: float = 60.0) -> AsyncIterator[dict]:
    """Replay a match in (accelerated) real time. speed=60 -> 1 match minute per second.
    speed<=0 means no waiting at all."""
    last_t = 0.0
    for ev in MatchGenerator(seed).events():
        if speed > 0 and ev["type"] != "period_start":  # skip the half-time interval
            await asyncio.sleep(max(0.0, (ev["t"] - last_t) / speed))
        last_t = ev["t"]
        yield ev
