"""내 조준 시뮬레이션 (F5).

게임이 그려 주는 조준선(수구에서 나가는 흰 선)과 그 끝의 고스트볼 링을 읽어서
지금 조준 방향을 알아내고, 그 방향 그대로 쳤을 때 수구·목적구가 어떻게 갈지 계산한다.

- 힘 30~100%(5% 간격)로 전부 쳐 보고 득점되는 힘 범위를 찾는다
- 득점이 안 되면 왜 안 되는지(쿠션 부족, 2적구를 공 몇 개 차이로 놓침, 상대 공 맞음 등)를 말해 준다
- 조준을 조금만 돌리면 득점되는 각도가 있으면 가장 가까운 것을 같이 보여 준다
"""
import math

import cv2
import numpy as np

from . import config
from .solver import judge

POWERS = list(range(30, 101, 5))
FIX_RANGE = 3.0      # 근처 득점 각도를 찾는 범위 (±도)
FIX_STEP = 0.05


# ---------------------------------------------------------------- 조준선 읽기
def _thin_white_mask(img, det):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    white = cv2.inRange(hsv, (0, 0, 190), (179, 70, 255))
    x0, y0, x1, y1 = det.table.inner
    keep = np.zeros_like(white)
    keep[y0:y1, x0:x1] = 255
    white &= keep
    r = det.radius
    for b in det.balls:                       # 공은 지운다 (흰 공 안의 선도 같이)
        cv2.circle(white, (int(b["x"]), int(b["y"])), int(r * 1.12), 0, -1)
    k = max(3, int(r * 0.45)) | 1             # 굵은 것(큐대)은 빼고 얇은 선만
    thick = cv2.morphologyEx(white, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    thick = cv2.dilate(thick, np.ones((7, 7), np.uint8))
    return cv2.bitwise_and(white, cv2.bitwise_not(thick))


def _ring_score(mask, c, rr):
    h, w = mask.shape
    hit = n = 0
    for a in np.linspace(0, 2 * np.pi, 72, endpoint=False):
        x, y = int(round(c[0] + rr * math.cos(a))), int(round(c[1] + rr * math.sin(a)))
        if 0 <= x < w and 0 <= y < h:
            n += 1
            hit += mask[y, x] > 0
    return hit / max(n, 1)


def read_aim(img, det, cue_color):
    """지금 게임 조준 방향. 반환: {"angle": 도, "ring": (x,y) 또는 None} / 못 읽으면 None.

    각도는 화면 좌표 기준 (0도=오른쪽, 90도=아래, 커지면 시계 방향).
    고스트볼 링이 보이면 수구 중심→링 중심 방향을 쓴다 (선 끝까지 길게 재서 더 정확).
    """
    cue = next((b for b in det.balls if b["color"] == cue_color), None)
    if cue is None:
        return None
    r = det.radius
    mask = _thin_white_mask(img, det)
    ys, xs = np.nonzero(mask)
    if len(xs) < 50:
        return None
    pts = np.stack([xs, ys], 1).astype(float)
    cpos = np.array([cue["x"], cue["y"]])

    # 1) 수구 둘레 근처 흰 픽셀들의 방향 히스토그램 → 선이 나가는 방향
    rel = pts - cpos
    dist = np.hypot(rel[:, 0], rel[:, 1])
    near = (dist > r * 1.1) & (dist < r * 4.0)
    if near.sum() < 10:
        return None
    ang = np.degrees(np.arctan2(rel[near, 1], rel[near, 0])) % 360
    hist, edges = np.histogram(ang, bins=360, range=(0, 360))
    hist = np.convolve(np.r_[hist[-2:], hist, hist[:2]], np.ones(5), "valid")
    a0 = math.radians(edges[int(np.argmax(hist))] + 0.5)
    d0 = np.array([math.cos(a0), math.sin(a0)])

    # 2) 그 방향 띠 안의 픽셀로 직선 맞춤 (수구 중심을 지나야 함), 선이 끊긴 곳까지만
    along = rel @ d0
    perp = np.abs(rel[:, 0] * d0[1] - rel[:, 1] * d0[0])
    sel = (along > 0) & (perp < r * 0.35)
    band, al = pts[sel], along[sel]
    if len(band) < 20:
        return None
    order = np.argsort(al)
    band, al = band[order], al[order]
    cut = np.where(np.diff(al) > r * 0.8)[0]
    if len(cut):
        band, al = band[:cut[0] + 1], al[:cut[0] + 1]
    fit = np.vstack([band, cpos[None, :]]).astype(np.float32)
    vx, vy, _, _ = cv2.fitLine(fit, cv2.DIST_HUBER, 0, 0.01, 0.01).flatten()
    d = np.array([vx, vy], float)
    if d @ d0 < 0:
        d = -d
    angle = math.degrees(math.atan2(d[1], d[0])) % 360
    L_end = float(al.max())

    # 3) 선 끝의 고스트볼 링: 선 위에서 대략 찾고, 링 픽셀에 원을 2차원으로 맞춰 정확한 중심을 구한다
    dil = cv2.dilate(mask, np.ones((3, 3), np.uint8))
    best = (0.0, None, None)
    for t in np.linspace(L_end - r * 1.2, L_end + r * 1.2, 49):
        c = cpos + d * t
        for rr in np.linspace(0.9 * r, 1.2 * r, 7):
            sc = _ring_score(dil, c, rr)
            if sc > best[0]:
                best = (sc, c, rr)
    ring = None
    if best[0] >= 0.45:
        c0, rr0 = best[1], best[2]
        rel_r = pts - c0
        dd = np.hypot(rel_r[:, 0], rel_r[:, 1])
        ann = (dd > rr0 * 0.7) & (dd < rr0 * 1.35)
        # 링으로 들어오는 조준선 픽셀은 뺀다 (링 중심에서 수구 쪽 방향의 띠)
        to_cue = -d
        al2 = rel_r @ to_cue
        pp2 = np.abs(rel_r[:, 0] * to_cue[1] - rel_r[:, 1] * to_cue[0])
        ann &= ~((al2 > 0) & (pp2 < r * 0.3))
        rp = pts[ann]
        if len(rp) >= 30:
            c = c0.astype(float)
            R = rr0
            for _ in range(20):                       # 이상치를 빼 가며 원 맞춤 (중심·반지름)
                v = rp - c
                dist = np.hypot(v[:, 0], v[:, 1]) + 1e-9
                res = dist - R
                ok = np.abs(res) < max(1.5, 0.12 * R)
                if ok.sum() < 20:
                    break
                R = float(dist[ok].mean())
                step = (res[ok, None] * v[ok] / dist[ok, None]).mean(0)
                c = c + step
                if np.hypot(*step) < 0.01:
                    break
            if np.hypot(*(c - c0)) < 0.5 * r:
                c0 = c
        ring = (float(c0[0]), float(c0[1]))
        ra = math.degrees(math.atan2(ring[1] - cpos[1], ring[0] - cpos[0])) % 360
        # 링 근처 픽셀을 뺀 순수한 선으로 다시 맞춘 각도
        t_ring = float((c0 - cpos) @ d)
        line_only = band[((band - cpos) @ d) < t_ring - 1.15 * r]
        if len(line_only) >= 20:
            fit2 = np.vstack([line_only, cpos[None, :]]).astype(np.float32)
            vx2, vy2, _, _ = cv2.fitLine(fit2, cv2.DIST_HUBER, 0, 0.01, 0.01).flatten()
            d2 = np.array([vx2, vy2])
            if d2 @ d < 0:
                d2 = -d2
            angle = math.degrees(math.atan2(d2[1], d2[0])) % 360
        if abs((ra - angle + 180) % 360 - 180) < 2.0:
            # 수구 중심→링 중심은 기준선이 길어서 더 정확하다. 선 각도와 평균내되 링 쪽에 무게
            w = 0.7
            angle = math.degrees(math.atan2(w * math.sin(math.radians(ra)) + (1 - w) * math.sin(math.radians(angle)),
                                            w * math.cos(math.radians(ra)) + (1 - w) * math.cos(math.radians(angle)))) % 360
    return {"angle": angle, "ring": ring}


# ---------------------------------------------------------------- 결과 설명
def ball_names(det):
    names, n_red = {}, 0
    for i, b in enumerate(det.balls):
        if b["color"] == "red":
            n_red += 1
            names[i] = f"빨{n_red}"
        else:
            names[i] = "흰공" if b["color"] == "white" else "노란공"
    return names


def _eul(name):
    """목적격 조사: 빨1을 / 빨2를 / 흰공을"""
    last = name[-1]
    if last.isdigit():
        return name + ("을" if last in "136780" else "를")
    code = ord(last) - 0xAC00
    if 0 <= code < 11172:
        return name + ("을" if code % 28 else "를")
    return name + "을"


def _seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def _sequence(trace, names):
    out, cush = [], 0
    for e in trace.events:
        if e.kind == "cushion":
            cush += 1
        else:
            if cush:
                out.append(f"쿠션{cush}")
                cush = 0
            out.append(names.get(e.target, "?"))
    if cush:
        out.append(f"쿠션{cush}")
    return " → ".join(out) if out else "아무것도 안 맞음"


def describe(trace, s, mode, names):
    """(득점?, 한 줄 설명)"""
    ok, cush = judge(trace, mode, s["targets"], s["forbidden"], s["need"])
    if ok:
        return True, "득점!"
    r = s["r"]
    hits = [e for e in trace.events if e.kind == "ball"]
    bad = next((e for e in hits if e.target in s["forbidden"]), None)
    tset = set(s["targets"])
    need = s["need"] or len(tset)
    got = []
    for e in hits:
        if e.target in tset and e.target not in got:
            got.append(e.target)
    if bad is not None:
        return False, f"{names[bad.target]}(상대 공)에 맞음 → 파울"
    if not got:
        return False, "목적구를 하나도 못 맞힘"
    if len(got) < need:
        first = next(e for e in hits if e.target == got[0])
        rest = [t for t in tset if t not in got]
        pts = trace.points[first.idx:] if first.idx >= 0 else trace.points
        best = None
        for t in rest:
            c = s["pos"][t]
            d = min((_seg_dist(c, pts[i], pts[i + 1]) for i in range(len(pts) - 1)), default=1e9)
            if best is None or d < best[1]:
                best = (t, d)
        miss = max(0.0, (best[1] - 2 * r) / (2 * r))
        extra = ""
        if mode in ("4ball_finish", "3cushion"):
            n_c = sum(1 for e in trace.events[trace.events.index(first):] if e.kind == "cushion")
            extra = f", 1적구 뒤 쿠션 {n_c}개"
        return False, f"{_eul(names[best[0]])} 공 {miss:.1f}개 차이로 놓침{extra}"
    # 목적구는 다 맞았는데 쿠션이 모자람
    c = 0
    seen = set()
    for e in trace.events:
        if e.kind == "cushion":
            c += 1
        elif e.target in tset:
            seen.add(e.target)
            if len(seen) >= need:
                break
    return False, f"두 번째 공 전에 쿠션 {c}개 (3개 필요, {3 - c}개 부족)"


def _runs(vals):
    runs, cur = [], []
    for p in POWERS:
        if p in vals:
            cur.append(p)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return runs


# ---------------------------------------------------------------- 계산
def analyze(det, aim, cfg):
    """조준 각도로 친 결과. 반환 dict (오류면 {"error": 이유})."""
    sv = config.make_solver(cfg)
    s = sv.setup(det)
    if s is None:
        return {"error": sv.fail_reason or "setup"}
    mode = cfg["mode"]
    names = ball_names(det)
    angle = aim["angle"]

    traces = {p: sv.simulate(s, angle, p) for p in POWERS}
    ok_powers = [p for p in POWERS if judge(traces[p], mode, s["targets"], s["forbidden"], s["need"])[0]]
    runs = _runs(set(ok_powers))
    if runs:
        best = max(runs, key=len)
        show = best[len(best) // 2]
    else:
        show = 70
    tr = traces[show]
    scored, why = describe(tr, s, mode, names)

    # 조준을 조금 돌리면 득점되는 가장 가까운 각도 (지금 조준이 이미 득점이면 생략)
    fix = None
    if not ok_powers:
        steps = int(FIX_RANGE / FIX_STEP)
        for k in range(1, steps + 1):
            for sign in (1, -1):
                a = (angle + sign * k * FIX_STEP) % 360
                good = [p for p in range(40, 101, 10) if sv._ok(s, a, p)]
                if good:
                    pw = good[len(good) // 2]
                    fix = {"delta": sign * k * FIX_STEP, "angle": a, "power": pw,
                           "trace": sv.simulate(s, a, pw)}
                    break
            if fix:
                break

    # 게임 조준선의 첫 충돌 위치(링)와 우리 계산의 첫 충돌 위치 비교 (참고용)
    first = next((e for e in tr.events), None)
    ring_gap = None
    if aim.get("ring") and first is not None:
        ring_gap = math.hypot(first.x - aim["ring"][0], first.y - aim["ring"][1]) / s["r"]

    return {"angle": angle, "power": show, "trace": tr, "scored": scored, "why": why,
            "sequence": _sequence(tr, names), "ok_powers": ok_powers, "runs": runs,
            "fix": fix, "setup": s, "mode": mode, "ring": aim.get("ring"), "ring_gap": ring_gap}
