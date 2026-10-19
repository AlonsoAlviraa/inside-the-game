"""Exact failure cases observed in the real Azure runs of 2026-10-19 (runs/SAMPLE_RUNS.md)."""
from insidethegame.room.semantic import check, fan_violations

TEAMS = {"Harbour City Mariners": {"xg": 0.56, "shots": 9, "goals": 0},
         "Ironridge Rovers": {"xg": 1.47, "shots": 5, "goals": 1}}
META = {"home": {"name": "Harbour City Mariners", "short": "HCM"}, "away": {"name": "Ironridge Rovers", "short": "IRR"}}
ROSTER = ["Yuri Greywick", "Kian Juniper", "Hugo Northam", "Zeno Northam"]
GOAL = {"moment": "goal", "minute": 37, "player": "Yuri Greywick", "team": "Ironridge Rovers", "xg": 0.898,
        "score": "HCM 0-1 IRR", "teams": TEAMS}


def test_wrong_xg_leader_in_goal_card():
    txt = ("Yuri Greywick scored for Ironridge Rovers at minute 37, converting a high-quality chance (xG 0.898) "
           "during a chaotic phase, giving IRR a 1-0 lead despite Harbour City Mariners' higher shot count and xG.")
    issues = check(txt, GOAL, meta=META, roster=ROSTER)
    assert any(i.startswith("leader:xg") for i in issues)
    assert not any(i.startswith("leader:shots") for i in issues)   # HCM really had more shots


def test_correct_goal_card_passes():
    txt = ("Yuri Greywick scored for Ironridge Rovers at minute 37 (xG 0.898), giving IRR a 1-0 lead; "
           "Ironridge Rovers also lead on xG while Harbour City Mariners have more shots.")
    assert check(txt, GOAL, meta=META, roster=ROSTER) == []


def test_xg_value_called_expected_threat_spanish():
    facts = {"moment": "shot", "minute": 6, "player": "Kian Juniper", "xg": 0.093, "player_match_xt": 0.16,
             "player_match_xg": 0.09}
    txt = "Kian Juniper disparó a 106.5 km/h desde 8m con 0.093 de amenaza esperada, pero falló el tiro."
    assert any(i.startswith("metric") for i in check(txt, facts, roster=ROSTER))
    assert check("Kian Juniper disparó desde 8m con 0.093 xG, pero falló.", facts, roster=ROSTER) == []


def test_half_time_as_end_of_48th_minute():
    facts = {"moment": "period_end", "period": 1, "minute": 48, "score": "HCM 0-1 IRR", "teams": TEAMS}
    txt = "At the end of the 48th minute, Ironridge Rovers lead 1-0 against Harbour City Mariners."
    assert any(i.startswith("period") for i in check(txt, facts, meta=META))
    assert any(i.startswith("period") for i in check("Full-time: Ironridge Rovers won 1-0.", facts, meta=META))


def test_control_index_as_possession():
    facts = {"moment": "phase_change", "minute": 6, "control_index_0_to_1": {"Ironridge Rovers": 0.82,
                                                                          "Harbour City Mariners": 0.4}}
    txt = "¡Vaya lío en el minuto 6, Ironridge Rovers manda con un 82% de posesión!"
    assert "control index described as possession" in check(txt, facts, meta=META)


def test_wrong_control_leader_and_minute():
    facts = {"moment": "phase_change", "minute": 16,
             "control_index_0_to_1": {"Ironridge Rovers": 0.65, "Harbour City Mariners": 0.40}}
    issues = check("At minute 21, Harbour City Mariners dominate control.", facts, meta=META)
    assert any(i.startswith("leader:control") for i in issues) and any(i.startswith("minute") for i in issues)


def test_goal_credited_to_wrong_player():
    issues = check("Kian Juniper scores for Ironridge Rovers!", GOAL, meta=META, roster=ROSTER)
    assert any(i.startswith("attribution") for i in issues)


def test_fan_rule_violations_from_spanish_run():
    shot = {"moment": "shot", "player": "Kian Juniper"}
    v = fan_violations("Kian Juniper disparó a 106.5 km/h desde 8m con 0.093 de amenaza esperada.", shot)
    assert {"fan: decimal number", "fan: speed/distance", "fan: jargon"} <= set(v)
    v = fan_violations("¡No puede ser! Ironridge Rovers marca con eficacia mientras Harbour City Mariners dominan sin gol.", GOAL)
    assert "fan: goal card must name the scorer" in v
    assert fan_violations("¡Golazo de Yuri Greywick! Ironridge Rovers se pone 0-1.", GOAL) == []
