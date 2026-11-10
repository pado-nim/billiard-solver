"""내 조준 시뮬레이션 (F5).

게임이 그려 주는 조준선(수구에서 나가는 흰 선), 그 끝의 고스트볼 링, 링에서 나가는 안내선을 읽어서
지금 조준대로 치면 수구가 어디로 가는지 끝까지 그린다.

- 첫 충돌 뒤 방향은 게임 안내선을 그대로 따른다 (공에 맞은 뒤 수구가 꺾이는 방향, 쿠션 반사각)
- 경로는 거리 제한 없이 이벤트 8개(쿠션·공)까지 그린다. 직선 물리라 경로 모양은 힘과 상관없고,
  힘은 "어디서 멈추는지"만 바꾼다 → 경로 위에 40/60/80/100% 예상 정지 위치를 표시
- 득점 판정은 경로(방향) 기준. 필요한 힘은 예상치로 따로 알려 준다
- 득점 경로가 아니면 왜 아닌지와, 조준을 조금 돌리면 득점되는 가장 가까운 각도를 알려 준다
"""
import math

import cv2
import numpy as np

from . import config
from .physics import Params, Trace, trace_ball
from .solver import _score_event_index, judge

POWERS = list(range(30, 101, 5))
MARK_POWERS = (40, 60, 80, 100)   # 경로 위에 예상 정지 위치를 찍을 힘
GEO_EVENTS = 8                    # 거리 제한 없이 그릴 이벤트(쿠션·공) 수
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
    guide = _read_guide(pts, ring, d, det, cue) if ring is not None else None
    return {"angle": angle, "ring": ring, "guide": guide}


def _read_guide(pts, ring, d_in, det, cue):
    """링에서 나가는 게임 안내선. 공에 맞는 조준이면 맞은 뒤 수구가 가는 방향,
    쿠션에 맞는 조준이면 반사된 방향을 돌려준다."""
    r = det.radius
    ring = np.array(ring)
    rel = pts - ring
    dist = np.hypot(rel[:, 0], rel[:, 1])
    sel = (dist > r * 1.3) & (dist < r * 6)
    if sel.sum() < 10:
        return None
    ang = np.degrees(np.arctan2(rel[sel, 1], rel[sel, 0])) % 360
    back = math.degrees(math.atan2(-d_in[1], -d_in[0])) % 360
    hist, edges = np.histogram(ang, bins=360, range=(0, 360))
    sm = np.convolve(np.r_[hist[-2:], hist, hist[:2]], np.ones(5), "valid")
    rays = []
    for _ in range(4):
        i = int(np.argmax(sm))
        if sm[i] < 8:
            break
        a = edges[i] + 0.5
        sm[max(0, i - 8):i + 9] = 0
        if abs((a - back + 180) % 360 - 180) < 8:        # 들어온 조준선 자신
            continue
        dd = np.array([math.cos(math.radians(a)), math.sin(math.radians(a))])
        v = pts - ring
        al = v @ dd
        pp = np.abs(v[:, 0] * dd[1] - v[:, 1] * dd[0])
        bp = pts[(al > r * 1.25) & (al < r * 12) & (pp < r * 0.3)]
        if len(bp) < 15:
            continue
        vx, vy, _, _ = cv2.fitLine(bp.astype(np.float32), cv2.DIST_HUBER, 0, 0.01, 0.01).flatten()
        u = np.array([vx, vy])
        if u @ dd < 0:
            u = -u
        rays.append({"dir": u, "n": len(bp)})
    if not rays:
        return None

    # 링이 어떤 공에 닿아 있나 (공 중심 거리 ≈ 2r)
    target = None
    for i, b in enumerate(det.balls):
        if b is cue:
            continue
        if abs(math.hypot(b["x"] - ring[0], b["y"] - ring[1]) - 2 * r) < 0.35 * r:
            target = i
    if target is not None:
        b = det.balls[target]
        nrm = np.array([b["x"] - ring[0], b["y"] - ring[1]])
        nrm /= np.linalg.norm(nrm)
        tang = d_in - float(d_in @ nrm) * nrm
        if np.linalg.norm(tang) < 0.05:
            return {"kind": "ball", "target": target, "cue_dir": None}     # 정면 충돌: 수구는 거의 멈춤
        tang /= np.linalg.norm(tang)
        cue_ray = max(rays, key=lambda q: float(q["dir"] @ tang))
        if float(cue_ray["dir"] @ tang) < 0.5:
            return {"kind": "ball", "target": target, "cue_dir": None}
        u = cue_ray["dir"]
        cut = math.acos(min(1.0, abs(float(nrm @ d_in))))
        dev = math.atan2(float(u @ nrm), float(u @ tang))     # 접선에서 진행 방향(앞)으로 꺾인 각
        # 우리 물리: 맞은 뒤 수구 = 접선 성분 + follow × 법선 성분.  게임 안내선 각도로 follow를 거꾸로 구한다
        follow = math.tan(dev) * math.tan(cut) if 3 < math.degrees(cut) < 87 else None
        return {"kind": "ball", "target": target, "cue_dir": u, "normal": nrm,
                "cut": math.degrees(cut), "follow": follow}

    # 쿠션에 닿은 링
    x0, y0, x1, y1 = det.table.inner
    gaps = {"L": ring[0] - x0 - r, "R": x1 - ring[0] - r, "T": ring[1] - y0 - r, "B": y1 - ring[1] - r}
    side = min(gaps, key=lambda k: abs(gaps[k]))
    if abs(gaps[side]) > 0.6 * r:
        return None
    n = np.array([1.0, 0.0]) if side in ("L", "R") else np.array([0.0, 1.0])
    t = np.array([-n[1], n[0]])
    ray = max(rays, key=lambda q: q["n"])
    d_out = ray["dir"]
    vn_i, vt_i = float(d_in @ n), float(d_in @ t)
    vn_o, vt_o = float(d_out @ n), float(d_out @ t)
    if vn_i * vn_o >= 0 or abs(vn_i) < 1e-3 or abs(vn_o) < 1e-3:
        return None
    ratio = None
    if abs(vt_i) > 0.02 and vt_i * vt_o > 0:
        ratio = (abs(vt_o) / abs(vn_o)) / (abs(vt_i) / abs(vn_i))
    return {"kind": "cushion", "side": side, "out_dir": d_out, "ratio": ratio}


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
def _params_from_guide(guide):
    """게임 안내선에 맞춘 물리값. 맞은 뒤 수구 방향·쿠션 반사각을 게임이 보여 주는 대로 쓴다."""
    p = Params()
    if not guide:
        return p, None
    if guide["kind"] == "ball" and guide.get("follow") is not None:
        p.follow = float(np.clip(guide["follow"], -1.0, 1.5))
        return p, "ball"
    if guide["kind"] == "cushion" and guide.get("ratio"):
        p.cushion_f = float(np.clip(guide["ratio"], 0.3, 1.8)) * p.cushion_e
        return p, "cushion"
    return p, None


def _geo(sv, s, angle):
    """거리 제한 없는 경로 (감속 0). 직선 물리라 모양은 힘과 상관없다."""
    q = Params.from_dict(sv.p.to_dict())
    q.decel, q.damping = 1e-6, 0.0
    return trace_ball(s["pos"][s["cue"]], angle, q.v0(100), s["pos"], {s["cue"]}, s["box"], s["r"], s["L"], q,
                      max_events=GEO_EVENTS)


def _cut_at_score(tr, s):
    """득점 순간까지만 남긴 경로 (그 뒤에 다른 공을 맞는 건 판정에서 뺀다)."""
    k = _score_event_index(tr, s["targets"], s["need"])
    hit = {e.target for e in tr.events[:k + 1] if e.kind == "ball"} & set(s["targets"])
    if len(hit) < (s["need"] or len(set(s["targets"]))):
        return tr, None
    e = tr.events[k]
    return Trace(points=tr.points[:e.idx + 1], events=tr.events[:k + 1], object_paths=tr.object_paths), k


def _geo_ok(sv, s, angle, mode):
    tr = _geo(sv, s, angle)
    cut, k = _cut_at_score(tr, s)
    return k is not None and judge(cut, mode, s["targets"], s["forbidden"], s["need"])[0], tr


def analyze(det, aim, cfg):
    """조준 각도로 친 결과. 반환 dict (오류면 {"error": 이유})."""
    sv = config.make_solver(cfg)
    s = sv.setup(det)
    if s is None:
        return {"error": sv.fail_reason or "setup"}
    sv.p, matched = _params_from_guide(aim.get("guide"))
    mode = cfg["mode"]
    names = ball_names(det)
    angle = aim["angle"]

    # 1) 방향 기준 경로 (거리 무제한)
    scored, geo = _geo_ok(sv, s, angle, mode)
    cut, k = _cut_at_score(geo, s)
    judged = cut if k is not None else geo
    if scored:
        why = "득점 경로!"
    else:
        _, why = describe(judged, s, mode, names)

    # 2) 힘: 실제 감속을 넣고 30~100% 전부 (예상치)
    real = {p: sv.simulate(s, angle, p) for p in POWERS}
    ok_powers = [p for p in POWERS if judge(real[p], mode, s["targets"], s["forbidden"], s["need"])[0]]
    marks = []
    for p in MARK_POWERS:
        tr = real[p]
        if len(tr.events) < GEO_EVENTS:
            marks.append((p, tr.points[-1]))

    # 3) 득점 경로가 아니면 조준을 조금 돌려서 되는 가장 가까운 각도
    fix = None
    if not scored:
        steps = int(FIX_RANGE / FIX_STEP)
        for kk in range(1, steps + 1):
            for sign in (1, -1):
                a = (angle + sign * kk * FIX_STEP) % 360
                ok, tr = _geo_ok(sv, s, a, mode)
                if ok:
                    pw = [p for p in POWERS if sv._ok(s, a, p)]
                    fix = {"delta": sign * kk * FIX_STEP, "angle": a, "trace": _cut_at_score(tr, s)[0],
                           "power": pw[0] if pw else None}
                    break
            if fix:
                break

    first = next((e for e in geo.events), None)
    ring_gap = None
    if aim.get("ring") and first is not None:
        ring_gap = math.hypot(first.x - aim["ring"][0], first.y - aim["ring"][1]) / s["r"]

    seq_tr = cut if k is not None else Trace(points=geo.points, events=geo.events[:6])
    return {"angle": angle, "geo": geo, "score_k": k, "scored": scored, "why": why,
            "sequence": _sequence(seq_tr, names), "ok_powers": ok_powers, "runs": _runs(set(ok_powers)),
            "min_power": ok_powers[0] if ok_powers else None, "marks": marks, "fix": fix, "setup": s,
            "mode": mode, "ring": aim.get("ring"), "ring_gap": ring_gap, "matched": matched,
            "follow": sv.p.follow}
