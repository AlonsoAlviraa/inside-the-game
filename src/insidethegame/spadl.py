"""Convert our synthetic event stream into a SPADL-compatible action table.

SPADL (Soccer Player Action Description Language) is the open, vendor-neutral action schema from
Decroos et al., "Actions Speak Louder than Goals" (KDD 2019) and the MIT-licensed `socceraction`
library (https://github.com/ML-KULeuven/socceraction). We re-implement only the *schema* (column
names, type/result/bodypart vocabularies and ids) so the output can be loaded straight into
socceraction / kloppy-based tooling; no code or data is copied.

Coordinates: SPADL uses a 105 x 68 m pitch with every action in the acting team's
left-to-right attacking frame - which is exactly our generator's frame, so no flipping is needed.
"""
from __future__ import annotations

# Vocabularies in socceraction.spadl.config order (ids = list index).
ACTION_TYPES = ["pass", "cross", "throw_in", "freekick_crossed", "freekick_short", "corner_crossed",
                "corner_short", "take_on", "foul", "tackle", "interception", "shot", "shot_penalty",
                "shot_freekick", "keeper_save", "keeper_claim", "keeper_punch", "keeper_pick_up",
                "clearance", "bad_touch", "non_action", "dribble", "goalkick"]
RESULTS = ["fail", "success", "offside", "owngoal", "yellow_card", "red_card"]
BODYPARTS = ["foot", "head", "other", "head/other", "foot_left", "foot_right"]
COLUMNS = ["game_id", "original_event_id", "action_id", "period_id", "time_seconds", "team_id",
           "player_id", "start_x", "start_y", "end_x", "end_y", "type_id", "type_name",
           "result_id", "result_name", "bodypart_id", "bodypart_name"]


def _is_cross(ev: dict) -> bool:
    return ev["x"] > 70 and (ev["y"] < 14 or ev["y"] > 54) and ev["end_x"] > 88 and 14 <= ev["end_y"] <= 54


def _row(ev: dict, game_id: int, tname: str, result: str, body: str, ex: float, ey: float) -> dict:
    return {"game_id": game_id, "original_event_id": ev["id"], "period_id": ev["period"],
            "time_seconds": ev["t"], "team_id": ev["team"], "player_id": ev.get("player_id"),
            "start_x": ev["x"], "start_y": ev["y"], "end_x": ex, "end_y": ey,
            "type_id": ACTION_TYPES.index(tname), "type_name": tname,
            "result_id": RESULTS.index(result), "result_name": result,
            "bodypart_id": BODYPARTS.index(body), "bodypart_name": body}


def to_spadl(events: list[dict], game_id: int = 0) -> list[dict]:
    """Return SPADL action rows (list of dicts with `COLUMNS`) for one synthetic match."""
    rows: list[dict] = []
    for i, ev in enumerate(events):
        t = ev["type"]
        if t == "pass":
            rows.append(_row(ev, game_id, "cross" if _is_cross(ev) else "pass",
                             "success" if ev["success"] else "fail", "foot", ev["end_x"], ev["end_y"]))
        elif t == "shot":
            res = "success" if ev["outcome"] == "goal" else "fail"
            rows.append(_row(ev, game_id, "shot", res, "head" if ev["header"] else "foot", 105.0, 34.0))
        elif t == "foul":
            nxt = events[i + 1] if i + 1 < len(events) else {}
            res = "fail"
            if nxt.get("type") == "card" and nxt.get("player_id") == ev["player_id"]:
                res = "yellow_card" if nxt["card"] == "yellow" else "red_card"
            # foul location is reported in the fouled team's frame; mirror into the fouler's frame
            mev = {**ev, "x": round(105 - ev["x"], 1), "y": round(68 - ev["y"], 1)}
            rows.append(_row(mev, game_id, "foul", res, "foot", mev["x"], mev["y"]))
    for n, r in enumerate(rows):
        r["action_id"] = n
    return rows
