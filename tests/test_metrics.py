from insidethegame import metrics as m


def test_xg_monotonic():
    assert m.xg(94, 34) > m.xg(80, 34) > m.xg(70, 34)
    assert m.xg(94, 34) > m.xg(94, 5)
    assert 0.15 < m.xg(94, 34) < 0.4
    assert m.xg(94, 34, pressure=1) < m.xg(94, 34)


def test_speed_and_pass_quality():
    assert m.ball_speed_kmh(20, 1) == 72.0
    assert m.pass_quality(40, 1, 30, True) == 100.0
    assert m.pass_quality(5, 0, 0, True) > m.pass_quality(5, 0, 0, False)
    assert 0 <= m.pass_difficulty(100, 1, 100) <= 1


def test_control_chaos_index():
    idx = m.ControlChaosIndex("h", "a")
    for i in range(20):
        idx.update({"t": i, "type": "pass", "team": "h", "success": True, "end_x": 80})
    s = idx.snapshot()
    assert s["control"]["h"] > s["control"]["a"] and s["momentum"] > 0 and s["label"] == "control"
    for i in range(40):
        idx.update({"t": 20 + i, "type": "turnover", "team": "a"})
    assert idx.snapshot()["label"] == "chaos"
