import math

import pytest

from billiard_solver.detector import detect
from tests import synth


def _scene(balls, ring=None):
    img, inner = synth.background()
    truth = []
    for color, (u, v), mark in balls:
        x, y = synth.table_pos(inner, u, v)
        synth.ball(img, x, y, color, mark)
        truth.append((color, x, y))
    if ring:
        synth.ghost_ring(img, *ring)
    return img, inner, truth


def _match(det, truth, tol=0.25):
    out = []
    for color, x, y in truth:
        d = [math.hypot(b["x"] - x, b["y"] - y) for b in det.balls if b["color"] == color]
        out.append(min(d) / det.radius if d else 9)
    return out


def test_table_found():
    img, inner, _ = _scene([("white", (0.5, 0.5), None)])
    det = detect(img)
    assert det is not None
    for a, b in zip(det.table.inner, inner):
        assert abs(a - b) <= 6


def test_four_plain_balls():
    img, _, truth = _scene([("white", (0.2, 0.3), None), ("yellow", (0.7, 0.6), None),
                            ("red", (0.4, 0.75), None), ("red", (0.85, 0.2), None)])
    det = detect(img)
    assert len(det.balls) == 4
    assert max(_match(det, truth)) < 0.1


@pytest.mark.parametrize("ang", [i * math.pi / 6 for i in range(12)])
@pytest.mark.parametrize("rho", [0.0, 0.5, 0.75, 1.0])
def test_taegeuk_mark_any_position(rho, ang):
    """태극 마크(천과 같은 파란색)가 공 어디에 있어도 빨간 공을 찾고 중심이 정확해야 한다."""
    img, _, truth = _scene([("white", (0.2, 0.3), None), ("yellow", (0.7, 0.6), None),
                            ("red", (0.4, 0.7), (rho, ang, 0.4)), ("red", (0.8, 0.25), (rho, ang + 1, 0.4))])
    det = detect(img)
    assert len(det.balls) == 4
    assert max(_match(det, truth)) < 0.15


def test_ghost_ring_is_not_a_ball():
    """조준선 끝의 속 빈 흰 원은 공이 아니다 (적구에 닿아 있어도)."""
    img, inner, _ = synth.background(), None, None
    img, inner = img
    x, y = synth.table_pos(inner, 0.5, 0.5)
    synth.ball(img, x, y, "red", (0.8, 2.0, 0.4))
    cx, cy = synth.table_pos(inner, 0.2, 0.3)
    synth.ball(img, cx, cy, "white")
    gx, gy = x - 2 * synth.R_PX, y
    synth.ghost_ring(img, gx, gy, to=(cx, cy))
    det = detect(img)
    colors = sorted(b["color"] for b in det.balls)
    assert colors == ["red", "white"]


def test_touching_balls_split():
    img, inner = synth.background()
    x, y = synth.table_pos(inner, 0.5, 0.5)
    synth.ball(img, x, y, "red")
    synth.ball(img, x + 2.02 * synth.R_PX, y, "red")
    wx, wy = synth.table_pos(inner, 0.2, 0.2)
    synth.ball(img, wx, wy, "white")
    det = detect(img)
    reds = [b for b in det.balls if b["color"] == "red"]
    assert len(reds) == 2
    assert len(det.balls) == 3
