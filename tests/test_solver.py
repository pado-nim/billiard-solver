import random

import pytest

from billiard_solver import config
from billiard_solver.detector import detect
from billiard_solver.solver import Solver
from billiard_solver.physics import Params
from tests import synth


def _random_table(seed, colors):
    rnd = random.Random(seed)
    img, inner = synth.background()
    pts = []
    while len(pts) < len(colors):
        p = (rnd.uniform(0.08, 0.92), rnd.uniform(0.12, 0.88))
        if all(abs(p[0] - q[0]) > 0.08 or abs(p[1] - q[1]) > 0.15 for q in pts):
            pts.append(p)
    for c, p in zip(colors, pts):
        synth.ball(img, *synth.table_pos(inner, *p), c)
    return detect(img)


@pytest.mark.parametrize("mode", ["4ball", "4ball_finish"])
def test_four_ball_modes_find_paths(mode):
    found = 0
    for seed in range(8):
        det = _random_table(seed, ["white", "yellow", "red", "red"])
        shots, setup = Solver(Params(), mode, "white").solve(det, 3)
        assert setup["mode"] == mode
        found += bool(shots)
    assert found >= 6


def test_three_ball_mode():
    found = 0
    for seed in range(8):
        det = _random_table(seed, ["white", "yellow", "red"])
        shots, setup = Solver(Params(), "3cushion", "white").solve(det, 3)
        assert setup["mode"] == "3cushion"
        found += bool(shots)
    assert found >= 5


def test_mode_is_never_switched_automatically():
    """4구 모드에서 공이 3개만 보이면 3구로 바꾸지 않고, 이유를 알려준다."""
    det = _random_table(1, ["white", "yellow", "red"])
    sv = Solver(Params(), "4ball", "white")
    shots, setup = sv.solve(det, 3)
    assert shots == [] and setup is None
    assert sv.fail_reason == "need_2_reds"


def test_settings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PATH", str(tmp_path / "settings.json"))
    cfg = config.load()
    cfg["mode"] = "3cushion"
    cfg["junk"] = 1
    config.save(cfg)
    again = config.load()
    assert again["mode"] == "3cushion" and "junk" not in again
