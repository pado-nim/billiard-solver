"""오버레이에 그릴 것 목록을 만든다.

primitive:
  ('line',   [(x,y),...], color, width, dashed)
  ('circle', (x,y), r, color, width)
  ('text',   (x,y), str, color, size)
"""
COLORS = ["#39ff14", "#ffb000", "#00e5ff"]   # 1순위, 2순위, 3순위
KOR_MODE = {"4ball": "4구", "4ball_finish": "4구 마무리(3쿠션)", "3cushion": "3구(3쿠션)"}


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
        lines.append(f"#{rank + 1}  각도 {sh.angle:6.2f}°  힘 {sh.power:.0f}% ({sh.pmin:.0f}~{sh.pmax:.0f} OK)  "
                     f"여유 ±{sh.window / 2:.2f}°  쿠션 {sh.cushions}  안정성 {sh.robust:.0%}")
    for i, t in enumerate(lines):
        col = "#ffffff" if i == 0 else COLORS[(i - 1) % len(COLORS)]
        prims.append(("text", (x0 + 10, y0 - (30 + 26 * (len(lines) - 1 - i)) * k), t, col, 15 * k))

    # 수구 옆에 1순위 힘 표시
    cue = setup["pos"][setup["cue"]]
    sel = shots[selected % len(shots)]
    prims.append(("text", (cue[0] + r + 8 * k, cue[1] - r - 30 * k),
                  f"힘 {sel.power:.0f}%  ({sel.pmin:.0f}~{sel.pmax:.0f})", COLORS[selected % len(shots) % len(COLORS)], 18 * k))
    return prims


PREVIEW = "#ff4fd8"      # 내 조준 경로
FIX = "#39ff14"          # 조금 돌리면 득점되는 경로


def build_preview(det, pv, cue_color, scale=1.0):
    """내 조준 시뮬레이션(F5) 결과 그리기."""
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
    if fx:                                           # 근처 득점 경로 (초록 점선)
        prims.append(("line", fx["trace"].points, FIX, 3, True))

    tr = pv["trace"]
    pts = tr.points
    col = FIX if pv["scored"] else PREVIEW
    prims.append(("line", pts, col, 4, False))
    first = next((e for e in tr.events if e.kind == "ball"), None)
    if first is not None:
        prims.append(("circle", (first.x, first.y), r, col, 2))
    for _, opts in tr.object_paths.items():
        prims.append(("line", opts, col, 2, True))

    kor = KOR_MODE.get(pv["mode"], pv["mode"])
    lines = [(f"[내 조준 · {kor}]  각도 {pv['angle']:.2f}°", "#ffffff")]
    verdict_col = FIX if pv["scored"] else "#ffb000"
    lines.append((f"힘 {pv['power']}%로 치면: {pv['sequence']}  →  {pv['why']}", verdict_col))
    if pv["runs"]:
        rng = ", ".join(f"{r_[0]}~{r_[-1]}%" if len(r_) > 1 else f"{r_[0]}%" for r_ in pv["runs"])
        lines.append((f"이 조준으로 득점되는 힘: {rng}", FIX))
    else:
        lines.append(("이 조준으로는 어떤 힘으로도 득점 안 됨", "#ff5050"))
        if fx:
            way = "시계 방향" if fx["delta"] > 0 else "반시계 방향"
            lines.append((f"가장 가까운 득점: 조준을 {way}으로 {abs(fx['delta']):.2f}° 돌리고 힘 {fx['power']}% (초록 점선)", FIX))
        else:
            lines.append(("±3° 안에는 득점 각도가 없어요. F2로 전체 탐색", "#ffffff"))
    for i, (t, c) in enumerate(lines):
        prims.append(("text", (x0 + 10, y0 - (30 + 26 * (len(lines) - 1 - i)) * k), t, c, 15 * k))

    cue = s["pos"][s["cue"]]
    prims.append(("text", (cue[0] + r + 8 * k, cue[1] - r - 30 * k), f"힘 {pv['power']}%", col, 18 * k))
    return prims
