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
