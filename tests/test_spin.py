import math
import random

from billiard_solver.detector import detect
from billiard_solver.physics import Params, trace_ball
from billiard_solver.render import english_text
from billiard_solver.solver import Solver, judge
from tests import synth

BOX = (0, 0, 1000, 500)


def _after_top_cushion(tx):
    t = trace_ball((500, 400), 270, 3.0, [], set(), BOX, 10, 1000, Params(bend_dist=0), max_events=2, english=(tx, 0))
    a, b = t.points[1], t.points[2]
    return b[0] - a[0]


def test_right_english_kicks_right_off_cushion():
    """위쪽 쿠션에 수직으로 보내면 오른쪽 당점은 오른쪽으로, 왼쪽 당점은 왼쪽으로 튄다."""
    assert _after_top_cushion(1.0) > 50
    assert _after_top_cushion(-1.0) < -50
    assert abs(_after_top_cushion(0.0)) < 1e-6


def test_side_spin_fades_each_cushion():
    t = trace_ball((500, 400), 270, 6.0, [], set(), BOX, 10, 1000, Params(bend_dist=0), max_events=3, english=(1.0, 0))
    p = t.points
    d1 = p[2][0] - p[1][0]
    d2 = p[3][0] - p[2][0]
    assert d1 > 0 and d2 > 0                       # 쿠션 두 번 다 오른쪽으로 감
    assert (d2 / abs(p[3][1] - p[2][1])) < (d1 / abs(p[2][1] - p[1][1])) + 1e-9   # 두 번째가 덜 꺾임 (회전 줄어듦)


def _after_ball(ty):
    t = trace_ball((100, 250), 0, 3.0, [(400, 265)], set(), BOX, 10, 1000, Params(top_k=0.6, bend_dist=0), max_events=2, english=(0, ty))
    e = t.events[0]
    nx, ny = t.points[e.idx + 1][0] - e.x, t.points[e.idx + 1][1] - e.y
    return math.degrees(math.atan2(ny, nx))


def test_top_and_draw_after_ball_contact():
    """(모델 동작 확인) top_k를 주면 밀어치기는 앞으로 더, 끌어치기는 더 꺾인다. 실측 기본값은 top_k=0."""
    follow, center, draw = _after_ball(1.0), _after_ball(0.0), _after_ball(-1.0)
    assert abs(follow) < abs(center) < abs(draw)


def test_no_curves_path_is_straight_between_events():
    t = trace_ball((100, 100), 30, 4.0, [], set(), BOX, 10, 1000, Params(bend_dist=0), max_events=4, english=(0.7, -0.7))
    assert len(t.points) == len(t.events) + 2 or len(t.points) == len(t.events) + 1


def test_cushion_bend_starts_on_guide_then_widens_like_real_ball():
    """실제 영상: 쿠션 직후엔 안내선 방향, 공 반지름 4개 뒤 더 넓게휜다."""
    p = Params()
    t = trace_ball((300, 300), 30, 1.5, [], set(), BOX, 10, 1000, p, max_events=2)
    c, k, f = t.points[1], t.points[2], t.points[3]
    assert abs(math.hypot(k[0] - c[0], k[1] - c[1]) - p.bend_dist * 10) < 1e-6        # 4r 지점에서 꺾임
    tin = math.tan(math.radians(60))                                                   # 아래 쿠션에 60° 입사
    g = abs(k[0] - c[0]) / abs(k[1] - c[1]) / tin                                      # 직후: 안내선 비율
    w = abs(f[0] - k[0]) / abs(f[1] - k[1]) / tin                                      # 휜 뒤
    assert abs(g - p.reflect_ratio(math.cos(math.radians(60)), math.sin(math.radians(60)))) < 0.01
    assert w > g


def test_english_text():
    assert english_text((0, 0)) == "정중앙"
    assert english_text((0, 2 / 3)) == "12시 2팁 (밀어치기)"
    assert english_text((1 / 3, 0)) == "3시 1팁 (오른쪽)"
    assert english_text((-2 / 3, -2 / 3)).startswith("8시 3팁") or english_text((-2 / 3, -2 / 3)).startswith("7시 3팁")


def _table(seed):
    rr = random.Random(seed)
    img, inner = synth.background()
    pts = []
    while len(pts) < 4:
        p = (rr.uniform(0.08, 0.92), rr.uniform(0.12, 0.88))
        if all(abs(p[0] - q[0]) > 0.08 or abs(p[1] - q[1]) > 0.15 for q in pts):
            pts.append(p)
    for c, p in zip(["white", "yellow", "red", "red"], pts):
        synth.ball(img, *synth.table_pos(inner, *p), c)
    return detect(img)


def test_spin_shot_actually_scores_with_its_english():
    for seed in range(6):
        det = _table(seed)
        sv = Solver(Params(), "4ball_finish", "white", use_spin=True)
        shots, s = sv.solve(det, 3)
        for sh in shots:
            t = trace_ball(s["pos"][s["cue"]], sh.angle, sv.p.v0(sh.power), s["pos"], {s["cue"]}, s["box"],
                           s["r"], s["L"], sv.p, english=sh.english)
            assert judge(t, "4ball_finish", s["targets"], s["forbidden"], s["need"])[0]
            assert 0.0 <= sh.robust <= 1.0


def test_spin_finds_at_least_as_many_finish_routes():
    with_spin = without = 0
    for seed in range(8):
        det = _table(seed)
        without += bool(Solver(Params(), "4ball_finish", "white", use_spin=False).solve(det, 1)[0])
        with_spin += bool(Solver(Params(), "4ball_finish", "white", use_spin=True).solve(det, 1)[0])
    assert with_spin >= without


def test_stability_is_deterministic():
    det = _table(3)
    a = Solver(Params(), "4ball", "white").solve(det, 3)[0]
    b = Solver(Params(), "4ball", "white").solve(det, 3)[0]
    assert [(x.angle, x.power, x.robust, x.english) for x in a] == [(x.angle, x.power, x.robust, x.english) for x in b]


def test_tips_stay_inside_game_circle():
    """게임 당점 화면의 초록 원(2팁) 밖은 칠 수 없으니 추천도 그 안에서만."""
    from billiard_solver.solver import ENGLISH, MAX_TIP
    assert all(math.hypot(*e) <= MAX_TIP + 1e-9 for e in ENGLISH)
    for seed in range(4):
        det = _table(seed)
        shots, _ = Solver(Params(), "4ball_finish", "white").solve(det, 3)
        assert all(math.hypot(*sh.english) <= MAX_TIP + 1e-9 for sh in shots)


def test_prefers_ball_first_shots():
    """첫 충돌이 쿠션인 샷은 덜 정확해서, 공 먼저 샷이 있으면 그걸 1순위로."""
    n_ball_first = n = 0
    for seed in range(8):
        det = _table(seed)
        shots, _ = Solver(Params(), "4ball", "white").solve(det, 1)
        if shots:
            n += 1
            n_ball_first += not shots[0].first_cushion
    assert n_ball_first >= n - 1


def test_no_spin_is_default_and_cushion_first_is_last_resort():
    """무스핀 + 공 먼저 샷이 있으면 스핀·쿠션 먼저 샷은 1순위가 되지 않는다."""
    for seed in range(8):
        det = _table(seed)
        shots, _ = Solver(Params(), "4ball", "white").solve(det, 3)
        if shots and any(not x.first_cushion and x.english == (0.0, 0.0) for x in shots):
            assert shots[0].english == (0.0, 0.0) and not shots[0].first_cushion


def test_cushion_reflection_widens_at_glancing_angles_like_game_guide():
    """게임 안내선: 45° 이하 반사 비율 0.85, 비스듬할수록 넓어져 70° 이상에선 1.0 넘음."""
    p = Params()
    r = lambda deg: p.reflect_ratio(math.cos(math.radians(deg)), math.sin(math.radians(deg)))
    assert abs(r(20) - 0.857) < 0.01 and abs(r(40) - 0.857) < 0.01
    assert r(20) < r(55) < r(65) < r(75)
    assert 0.98 < r(65) < 1.03 and r(75) > 1.0


def test_weak_shots_are_not_recommended():
    for seed in range(6):
        shots, _ = Solver(Params(), "4ball_finish", "white").solve(_table(seed), 3)
        assert all(sh.robust >= Solver.MIN_ROBUST for sh in shots)
