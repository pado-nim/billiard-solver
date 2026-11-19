"""오버레이에 그릴 것 목록을 만든다.

primitive:
  ('line',   [(x,y),...], color, width, dashed)
  ('circle', (x,y), r, color, width)
  ('text',   (x,y), str, color, size)
  ('dot',    (x,y), r, color)                    채운 원
"""
import math

COLORS = ["#39ff14", "#ffb000", "#00e5ff"]   # 1순위, 2순위, 3순위
KOR_MODE = {"4ball": "4구", "4ball_finish": "4구 마무리(3쿠션)", "3cushion": "3구(3쿠션)"}


def english_text(e):
    """당점을 사람 말로: '정중앙' / '12시 2팁 (밀어치기)' / '3시 1팁 (오른쪽)'"""
    tx, ty = e
    tips = int(round(math.hypot(tx, ty) * 3))
    if tips == 0:
        return "정중앙"
    deg = math.degrees(math.atan2(tx, ty)) % 360           # 12시에서 시계 방향
    clock = int(round(deg / 30)) % 12 or 12
    parts = []
    if ty > 0.15:
        parts.append("밀어치기")
    elif ty < -0.15:
        parts.append("끌어치기")
    if tx > 0.15:
        parts.append("오른쪽")
    elif tx < -0.15:
        parts.append("왼쪽")
    return f"{clock}시 {tips}팁 ({' '.join(parts)})"


def cue_diagram(cx, cy, R, e, col):
    """게임 당점 고르는 공처럼 생긴 작은 그림: 공 테두리, 1·2팁 원, 십자, 당점 점."""
    out = [("dot", (cx, cy), R, "#f2f2f2"),
           ("circle", (cx, cy), R, "#202020", 2),
           ("circle", (cx, cy), R * 2 / 3, "#b0b0b0", 1),
           ("circle", (cx, cy), R / 3, "#b0b0b0", 1),
           ("line", [(cx - R, cy), (cx + R, cy)], "#b0b0b0", 1, False),
           ("line", [(cx, cy - R), (cx, cy + R)], "#b0b0b0", 1, False)]
    tx, ty = e
    out.append(("dot", (cx + tx * R, cy - ty * R), max(3, R * 0.16), "#e00000"))
    out.append(("circle", (cx + tx * R, cy - ty * R), max(3, R * 0.16), col, 2))
    return out


def build(det, shots, setup, mode, cue_color, show_all=True, selected=0, scale=1.0):
    k = scale
    prims = []
    if det is None:
        return prims
    x0, y0, x1, y1 = det.table.inner
    prims.append(("line", [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)],
                  "#ffffff", 1, True))
    r = det.radius
    for b in det.balls:
        prims.append(("circle", (b["x"], b["y"]), r + 4, "#ffffff", 1))

    if setup and setup.get("mode"):
        mode = setup["mode"]
    head = f"[{KOR_MODE.get(mode, mode)} / 수구:{'흰공' if cue_color == 'white' else '노란공'}]"
    if not shots:
        prims.append(("text", (x0 + 10, y0 - 34 * k), head + "  득점 경로를 못 찾았어요", "#ff5050", 16 * k))
        return prims

    order = list(range(len(shots)))
    if not show_all:
        order = [selected % len(shots)]
    for rank in reversed(order):           # 1순위가 맨 위에 그려지게
        sh = shots[rank]
        col = COLORS[rank % len(COLORS)]
        w = 4 if rank == selected % len(shots) else 2
        pts = sh.trace.points
        ev = sh.trace.events[sh.score_index] if 0 <= sh.score_index < len(sh.trace.events) else None
        cut = ev.idx + 1 if ev is not None and ev.idx >= 0 else len(pts)
        prims.append(("line", pts[:cut], col, w, False))      # 득점 순간까지
        if cut < len(pts):
            prims.append(("line", pts[cut - 1:], col, 1, True))  # 그 뒤는 점선
        # 첫 접촉 지점의 고스트볼
        first = next((e for e in sh.trace.events if e.kind == "ball"), None)
        if first is not None:
            prims.append(("circle", (first.x, first.y), r, col, 2))
        for idx, opts in sh.trace.object_paths.items():
            prims.append(("line", opts, col, 1, True))

    lines = [head]
    for rank, sh in enumerate(shots):
        first = "  (쿠션 먼저: 덜 정확)" if getattr(sh, "first_cushion", False) else ""
        lines.append(f"#{rank + 1}  각도 {sh.angle:6.2f}°  힘 {sh.power:.0f}%  당점 {english_text(sh.english)}  "
                     f"쿠션 {sh.cushions}  안정성 {sh.robust:.0%}{first}")
    for i, t in enumerate(lines):
        col = "#ffffff" if i == 0 else COLORS[(i - 1) % len(COLORS)]
        prims.append(("text", (x0 + 10, y0 - (30 + 26 * (len(lines) - 1 - i)) * k), t, col, 15 * k))

    # 수구 옆에 1순위 힘 표시
    cue = setup["pos"][setup["cue"]]
    sel = shots[selected % len(shots)]
    scol = COLORS[selected % len(shots) % len(COLORS)]
    prims.append(("text", (cue[0] + r + 8 * k, cue[1] - r - 30 * k),
                  f"힘 {sel.power:.0f}%  ·  {english_text(sel.english)}", scol, 18 * k))
    # 수구 옆 당점 그림
    R = 26 * k
    dx = cue[0] - r - 12 * k - R if cue[0] + r + 300 * k > x1 else cue[0] - r - 12 * k - R
    prims += cue_diagram(dx, cue[1], R, sel.english, scol)
    return prims


PREVIEW = "#ff4fd8"      # 내 조준 경로
GOLD = "#ffd166"         # 추천 샷 목표 링
FIX = "#39ff14"          # 조금 돌리면 득점되는 경로


def build_preview(det, pv, cue_color, scale=1.0):
    """내 조준 시뮬레이션(F5) 결과 그리기. 경로는 거리 제한 없이, 힘은 예상 정지 위치로 표시."""
    k = scale
    prims = []
    if det is None or pv is None:
        return prims
    x0, y0, x1, y1 = det.table.inner
    r = det.radius
    s = pv["setup"]
    for b in det.balls:
        prims.append(("circle", (b["x"], b["y"]), r + 4, "#ffffff", 1))

    fx = pv.get("fix")
    if fx:                                           # 조금 돌리면 득점되는 경로 (초록 점선)
        prims.append(("line", fx["trace"].points, FIX, 3, True))

    geo = pv["geo"]
    col = FIX if pv["scored"] else PREVIEW
    pts = geo.points
    kk = pv.get("score_k")
    if kk is not None:                               # 득점 순간까지 굵게, 그 뒤는 가늘게
        cut = geo.events[kk].idx + 1
        prims.append(("line", pts[:cut], col, 5, False))
        if cut < len(pts):                          # 득점 뒤는 다음 한 구간만 짧게
            (ax, ay), (bx, by) = pts[cut - 1], pts[cut]
            d = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
            if d > 1e-6:
                L = min(d, 6 * r)
                prims.append(("line", [(ax, ay), (ax + (bx - ax) / d * L, ay + (by - ay) / d * L)], col, 2, True))
    else:
        prims.append(("line", pts, col, 4, False))
    first = next((e for e in geo.events if e.kind == "ball"), None)
    if first is not None:
        prims.append(("circle", (first.x, first.y), r, col, 2))
    for _, opts in geo.object_paths.items():         # 맞은 공은 나가는 방향만 짧게 (게임 안내선처럼)
        if len(opts) >= 2:
            (ax, ay), (bx, by) = opts[0], opts[1]
            d = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
            if d > 1e-6:
                L = min(d, 8 * r)
                prims.append(("line", [(ax, ay), (ax + (bx - ax) / d * L, ay + (by - ay) / d * L)], col, 2, True))

    # 힘별 예상 정지 위치 (경로 위의 점)
    for p, (mx, my) in pv["marks"]:
        prims.append(("circle", (mx, my), max(4, r * 0.3), "#ffffff", 3))
        prims.append(("text", (mx + r * 0.4, my - r * 0.9), f"{p}%", "#ffffff", 12 * k))

    kor = KOR_MODE.get(pv["mode"], pv["mode"])
    tg = pv.get("target")
    if tg and tg.get("ghost"):                       # 추천 샷의 목표 링: 게임 링을 여기에 겹치면 된다
        gx, gy = tg["ghost"]
        gcol = FIX if tg["ok"] else GOLD
        prims.append(("circle", (gx, gy), r, gcol, 4))
        prims.append(("circle", (gx, gy), r * 0.15, gcol, 3))
        prims.append(("text", (gx + r * 1.2, gy - r * 1.4), "목표" if not tg["ok"] else "✓ 일치", gcol, 14 * k))
    lines = [(f"[내 조준 · {kor}]  각도 {pv['angle']:.2f}°", "#ffffff")]
    if tg:
        if tg["ok"]:
            lines.append((f"✓ 추천 각도와 일치 (±0.05°) → 힘 {tg['power']:.0f}% · 당점 {english_text(tg['english'])}", FIX))
        else:
            way = "시계 방향" if tg["delta"] > 0 else "반시계 방향"
            lines.append((f"추천 샷까지: {way}으로 {abs(tg['delta']):.2f}° 더 (게임 링을 금색 목표 원에 겹치기) · "
                          f"힘 {tg['power']:.0f}% · 당점 {english_text(tg['english'])}", GOLD))
    verdict_col = FIX if pv["scored"] else "#ffb000"
    lines.append((f"이 방향: {pv['sequence']}  →  {pv['why']}", verdict_col))
    if pv["scored"]:
        if pv["min_power"] is not None:
            lines.append((f"필요한 힘(예상): {pv['min_power']}% 이상  ·  흰 점 = 힘별 예상 정지 위치", FIX))
        else:
            lines.append(("예상으론 힘 100%로도 거리가 모자라요 (게임에선 더 나갈 수 있음) · 세게 치세요", "#ffb000"))
    elif fx:
        way = "시계 방향" if fx["delta"] > 0 else "반시계 방향"
        pw = f", 힘 {fx['power']}% 이상(예상)" if fx["power"] else ""
        lines.append((f"가장 가까운 득점: 조준을 {way}으로 {abs(fx['delta']):.2f}° 돌리기{pw} (초록 점선)", FIX))
    else:
        lines.append(("±3° 안에는 득점 방향이 없어요. F2로 전체 탐색", "#ffffff"))
    for i, (t, c) in enumerate(lines):
        prims.append(("text", (x0 + 10, y0 - (30 + 26 * (len(lines) - 1 - i)) * k), t, c, 15 * k))
    return prims
