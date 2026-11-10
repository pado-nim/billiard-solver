import math
import random

import pytest

from billiard_solver import aimpreview, config
from billiard_solver.detector import detect
from billiard_solver.physics import Params
from billiard_solver.solver import Solver
from tests import synth


def _table(seed):
    rnd = random.Random(seed)
    img, inner = synth.background()
    pts = []
    while len(pts) < 4:
        p = (rnd.uniform(0.08, 0.92), rnd.uniform(0.12, 0.88))
        if all(abs(p[0] - q[0]) > 0.08 or abs(p[1] - q[1]) > 0.15 for q in pts):
            pts.append(p)
    for c, p in zip(["white", "yellow", "red", "red"], pts):
        synth.ball(img, *synth.table_pos(inner, *p), c)
    return img


def _draw_aim(img, det, angle, sv, s):
    """게임처럼 수구에서 첫 충돌 지점까지 흰 조준선 + 그 끝의 고스트볼 링을 그린다."""
    cue = s["pos"][s["cue"]]
    tr = sv.simulate(s, angle, 60)
    e = tr.events[0]
    synth.ghost_ring(img, e.x, e.y, r=det.radius, to=(cue[0] + 1.3 * det.radius * math.cos(math.radians(angle)),
                                                       cue[1] + 1.3 * det.radius * math.sin(math.radians(angle))))


def _setup(seed, mode):
    img = _table(seed)
    det = detect(img)
    sv = Solver(Params(), mode, "white")
    shots, s = sv.solve(det, 1)
    return img, det, sv, s, shots


@pytest.mark.parametrize("seed", range(6))
def test_reads_aim_angle_and_agrees_with_solver(seed):
    img, det, sv, s, shots = _setup(seed, "4ball")
    if not shots:
        pytest.skip("no scoring shot on this layout")
    best = shots[0]
    _draw_aim(img, det, best.angle, sv, s)
    det2 = detect(img)                                   # 조준선이 그려진 화면에서도 공 4개
    assert len(det2.balls) == 4
    aim = aimpreview.read_aim(img, det2, "white")
    assert aim is not None
    assert abs((aim["angle"] - best.angle + 180) % 360 - 180) < 0.08
    pv = aimpreview.analyze(det2, aim, dict(config.DEFAULT, mode="4ball"))
    assert pv["ok_powers"], pv["why"]                    # 솔버가 추천한 각도로 조준하면 득점으로 나와야 한다
    assert pv["ring_gap"] is not None and pv["ring_gap"] < 0.3


@pytest.mark.parametrize("seed", range(4))
def test_near_miss_gives_working_fix(seed):
    img, det, sv, s, shots = _setup(seed, "4ball")
    if not shots:
        pytest.skip("no scoring shot on this layout")
    off = shots[0].angle + 1.2                           # 일부러 1.2도 틀리게 조준
    _draw_aim(img, det, off, sv, s)
    det2 = detect(img)
    aim = aimpreview.read_aim(img, det2, "white")
    pv = aimpreview.analyze(det2, aim, dict(config.DEFAULT, mode="4ball"))
    if pv["ok_powers"]:
        return                                           # 틀린 각도도 우연히 득점이면 통과
    assert pv["why"] and not pv["scored"]
    fx = pv["fix"]
    assert fx is not None
    s2 = Solver(Params(), "4ball", "white").setup(det2)
    assert sv._ok(s2, fx["angle"], fx["power"])          # 알려준 보정 각도·힘으로 치면 실제로 득점


def test_no_aim_line_returns_none():
    img = _table(0)
    det = detect(img)
    assert aimpreview.read_aim(img, det, "white") is None


def test_korean_particle():
    assert aimpreview._eul("빨1") == "빨1을"
    assert aimpreview._eul("빨2") == "빨2를"
    assert aimpreview._eul("노란공") == "노란공을"
