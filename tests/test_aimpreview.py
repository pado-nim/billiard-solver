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
    sv = Solver(Params(), mode, "white", use_spin=False)   # F5는 정중앙 당점 기준
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
    # 경로 판정은 정확한 각도·공 위치로 (쿠션 여러 번 도는 샷은 0.01도·1픽셀 차이로도 길이 바뀐다)
    exact = dict(aim, angle=best.angle)
    pv = aimpreview.analyze(det, exact, dict(config.DEFAULT, mode="4ball"))
    assert pv["scored"], pv["why"]                       # 솔버가 추천한 각도로 조준하면 득점 경로로 나와야 한다
    assert pv["ok_powers"]                               # 그 힘들 중 일부는 실제 감속을 넣어도 득점
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
    if pv["scored"]:
        return                                           # 틀린 각도도 우연히 득점 경로면 통과
    assert pv["why"]
    fx = pv["fix"]
    assert fx is not None
    sv2 = Solver(Params(), "4ball", "white")
    s2 = sv2.setup(det2)
    ok, _ = aimpreview._geo_ok(sv2, s2, fx["angle"], "4ball")
    assert ok                                            # 알려준 보정 각도로 치면 실제로 득점 경로


def test_no_aim_line_returns_none():
    img = _table(0)
    det = detect(img)
    assert aimpreview.read_aim(img, det, "white") is None


def test_korean_particle():
    assert aimpreview._eul("빨1") == "빨1을"
    assert aimpreview._eul("빨2") == "빨2를"
    assert aimpreview._eul("노란공") == "노란공을"


@pytest.mark.parametrize("follow", [0.0, 0.3])
def test_follows_game_guide_after_first_contact(follow):
    """게임이 링에서 그리는 '맞은 뒤 수구 방향' 안내선을 읽어서, F5 경로도 그 방향 그대로 이어 그린다."""
    for seed in range(8):
        img, det, sv, s, shots = _setup(seed, "4ball")
        if not shots:
            continue
        ang = shots[0].angle
        q = Params(follow=follow)
        tr = Solver(q, "4ball", "white")
        tr.p = q
        t = tr.simulate(s, ang, 100)
        if not t.events or t.events[0].kind != "ball" or len(t.points) < 3:
            continue
        e = t.events[0]
        nx, ny = t.points[e.idx + 1][0] - e.x, t.points[e.idx + 1][1] - e.y
        n = math.hypot(nx, ny)
        if n < 6 * det.radius:
            continue
        ux, uy = nx / n, ny / n
        _draw_aim(img, det, ang, sv, s)
        r = det.radius
        synth.ghost_ring(img, e.x + ux * 5 * r, e.y + uy * 5 * r, r=0.01, to=(e.x + ux * 1.3 * r, e.y + uy * 1.3 * r))
        det2 = detect(img)
        aim = aimpreview.read_aim(img, det2, "white")
        g = aim["guide"]
        assert g is not None and g["kind"] == "ball"
        assert abs(g["follow"] - follow) < 0.15                  # 안내선은 제대로 읽는다
        pv = aimpreview.analyze(det2, aim, dict(config.DEFAULT, mode="4ball"))
        assert pv["matched"] == "ball"
        assert abs(pv["follow"] - follow) < 0.15                 # 경로도 안내선 방향
        return
    pytest.skip("no suitable layout")


def test_target_ring_helper():
    """F2 추천 샷이 있으면 지금 조준과의 각도 차이·방향·일치 여부를 알려 준다."""
    img, det, sv, s, shots = _setup(0, "4ball")
    best = shots[0]
    _draw_aim(img, det, best.angle, sv, s)
    det2 = detect(img)
    aim = aimpreview.read_aim(img, det2, "white")
    cfg = dict(config.DEFAULT, mode="4ball")
    pv = aimpreview.analyze(det2, aim, cfg, target=best)
    assert pv["target"]["ok"]                                 # 링을 정확히 겹쳤으면 일치
    off = dict(aim, angle=best.angle - 0.5)                   # 반시계로 0.5도 덜 돌림
    pv2 = aimpreview.analyze(det2, off, cfg, target=best)
    assert not pv2["target"]["ok"]
    assert abs(pv2["target"]["delta"] - 0.5) < 1e-6            # 시계 방향으로 0.5도 더 돌리라고 해야 함
    assert pv2["target"]["ghost"] is not None


def test_geometric_path_is_not_distance_limited():
    """경로는 힘(거리)과 상관없이 이벤트 여러 개까지 이어져야 한다."""
    img, det, sv, s, shots = _setup(0, "4ball")
    _draw_aim(img, det, shots[0].angle, sv, s)
    det2 = detect(img)
    aim = aimpreview.read_aim(img, det2, "white")
    pv = aimpreview.analyze(det2, aim, dict(config.DEFAULT, mode="4ball"))
    assert len(pv["geo"].events) == aimpreview.GEO_EVENTS
    assert all(len(pv["geo"].points) >= 2 for _ in [0])
