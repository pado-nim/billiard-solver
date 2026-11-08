"""화면 인식: 스크린샷(BGR numpy 배열)에서 테이블과 공 위치를 찾는다.

좌표는 모두 스크린샷 픽셀 기준이다.
- table.inner : 쿠션 코(공이 튕기는 경계) 사각형 (x0, y0, x1, y1)
- balls       : [{'color': 'white'|'yellow'|'red', 'x':, 'y':, 'r':}, ...]
"""
from dataclasses import dataclass, field
import cv2
import numpy as np

# 색 범위 (OpenCV HSV: H 0~179). 게임 테마가 바뀌면 여기만 고치면 된다.
CLOTH_HSV = ((95, 120, 90), (115, 255, 255))   # 파란 당구대 천


@dataclass
class Table:
    outer: tuple   # 파란 쿠션 바깥쪽 (x0, y0, x1, y1)
    inner: tuple   # 쿠션 코 = 공이 튕기는 경계 (x0, y0, x1, y1)

    @property
    def width(self):
        return self.inner[2] - self.inner[0]

    @property
    def height(self):
        return self.inner[3] - self.inner[1]


@dataclass
class Detection:
    table: Table
    balls: list = field(default_factory=list)
    radius: float = 0.0

    def get(self, color):
        return [b for b in self.balls if b["color"] == color]


def find_table(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    blue = cv2.inRange(hsv, *CLOTH_HSV)
    n, lab, st, _ = cv2.connectedComponentsWithStats(blue)
    if n < 2:
        return None
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    x, y, w, h = st[i, :4]
    if w * h < img.shape[0] * img.shape[1] * 0.1:
        return None
    x0, y0, x1, y1 = int(x), int(y), int(x + w - 1), int(y + h - 1)

    v = hsv[:, :, 2].astype(np.int32)

    # 쿠션은 밝고, 쿠션 코 바로 안쪽은 그림자 때문에 어둡다.
    # 바깥에서 안쪽으로 훑으면서 밝기가 크게 떨어지는 지점을 쿠션 코로 본다.
    def scan(lines, start, step, horizontal):
        hits = []
        limit = int((w if horizontal else h) * 0.15)
        for ln in lines:
            prof = v[ln, :] if horizontal else v[:, ln]
            ref = np.median(prof[start + step * 6: start + step * 16: step]) if step > 0 else \
                np.median(prof[start + step * 16: start + step * 6][::-1])
            p = start + step * 6
            for _ in range(limit):
                if prof[p] < ref * 0.75:
                    hits.append(p)
                    break
                p += step
        return int(np.median(hits)) if hits else None

    rows = np.linspace(y0 + h * 0.25, y0 + h * 0.75, 9).astype(int)
    cols = np.linspace(x0 + w * 0.25, x0 + w * 0.75, 9).astype(int)
    left = scan(rows, x0, 1, True)
    right = scan(rows, x1, -1, True)
    top = scan(cols, y0, 1, False)
    bottom = scan(cols, y1, -1, False)

    # 못 찾으면 쿠션 폭을 테이블 길이의 2.4%로 가정
    cw = int(w * 0.024)
    inner = (
        left if left is not None else x0 + cw,
        top if top is not None else y0 + cw,
        right if right is not None else x1 - cw,
        bottom if bottom is not None else y1 - cw,
    )
    # 네 변 쿠션 폭이 비슷해야 정상. 하나만 튀면 나머지 평균으로 맞춘다.
    widths = np.array([inner[0] - x0, inner[1] - y0, x1 - inner[2], y1 - inner[3]])
    med = np.median(widths)
    widths = np.where(np.abs(widths - med) > med * 0.3, med, widths).astype(int)
    inner = tuple(int(t) for t in (x0 + widths[0], y0 + widths[1], x1 - widths[2], y1 - widths[3]))
    return Table(outer=(x0, y0, x1, y1), inner=inner)


def classify(hsv_pixels, min_count=None):
    """공 안쪽 픽셀들의 HSV로 색을 정한다. 마크(태극 무늬 등)·하이라이트가 섞여도 되게 비율로 본다."""
    h = hsv_pixels[:, 0].astype(int)
    s = hsv_pixels[:, 1].astype(int)
    v = hsv_pixels[:, 2].astype(int)
    colored = (s > 90) & (v > 70)
    n = len(h)
    if n == 0:
        return None
    red = np.sum(colored & ((h <= 8) | (h >= 168)))
    yellow = np.sum(colored & (h >= 16) & (h <= 40))
    white = np.sum((s < 75) & (v > 125))
    scores = {"red": red, "yellow": yellow, "white": white}
    best = max(scores, key=scores.get)
    if scores[best] < n * 0.25:
        return None
    if min_count is not None and red + yellow + white < min_count:
        return None             # 공 색(어느 색이든) 픽셀이 원 안을 충분히 채워야 진짜 공
    return best


def _fill_small_holes(mask, r_ref):
    """공 안의 구멍(천과 같은 파란색 마크, 어두운 테두리)을 메운다.

    태극 마크 같은 구멍은 공 면적의 일부(약 20%)이고 주변이 공 색으로 꽉 차 있다.
    반면 게임의 고스트볼 링(속이 빈 흰 원)은 안쪽이 넓고 주변은 얇은 선뿐이다.
    링을 메우면 흰 공으로 오인하므로, 구멍 주변(공 1.5개 반지름 안)의 물체 면적과 비교해 작은 것만 메운다.
    """
    cs, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return mask
    out = mask.copy()
    R = max(3, int(r_ref * 1.5))
    yy, xx = np.mgrid[-R:R + 1, -R:R + 1]
    disk = (xx * xx + yy * yy) <= R * R
    H, W = mask.shape
    for c, hh in zip(cs, hier[0]):
        if hh[3] < 0:
            continue                                            # 부모가 있는 윤곽 = 구멍
        a = cv2.contourArea(c)
        if a <= 0 or a > np.pi * (0.8 * r_ref) ** 2:
            continue
        m = cv2.moments(c)
        cx, cy = int(m["m10"] / m["m00"]), int(m["m01"] / m["m00"])
        x0, y0, x1, y1 = cx - R, cy - R, cx + R + 1, cy + R + 1
        sub = mask[max(0, y0):min(H, y1), max(0, x0):min(W, x1)]
        dk = disk[max(0, y0) - y0:max(0, y0) - y0 + sub.shape[0], max(0, x0) - x0:max(0, x0) - x0 + sub.shape[1]]
        around = float(np.count_nonzero(sub[dk]))
        if a < 0.45 * around:
            cv2.drawContours(out, [c], -1, 255, -1)
    return out


def _fit_fixed_r(pts, c, r, iters=15):
    """반지름을 고정하고 윤곽점에 원을 맞춘다. 마크가 테두리를 파먹은 부분(안쪽으로 들어간 점)은 이상치로 빠진다."""
    c = np.array(c, float)
    for _ in range(iters):
        d = pts - c
        dist = np.hypot(d[:, 0], d[:, 1]) + 1e-9
        res = dist - r
        ok = np.abs(res) < max(1.0, 0.12 * r)
        if ok.sum() < 8:
            break
        step = (res[ok, None] * d[ok] / dist[ok, None]).mean(0)
        c += step
        if np.hypot(*step) < 0.01:
            break
    return c


def _fit_free(pts, c, r, iters=20):
    """중심과 반지름을 같이 맞춘다. 원에서 튀어나온 점(조준선·큐대 그루터기)과
    들어간 점(마크가 파먹은 곳)은 이상치로 빼고 남은 테두리로만 맞춘다."""
    c = np.array(c, float)
    r = float(r)
    for _ in range(iters):
        d = pts - c
        dist = np.hypot(d[:, 0], d[:, 1]) + 1e-9
        res = dist - r
        tol = max(1.0, 0.1 * r)
        ok = np.abs(res) < tol
        if ok.sum() < max(8, len(pts) * 0.3):
            break
        r_new = float(dist[ok].mean())
        step = (res[ok, None] * d[ok] / dist[ok, None]).mean(0)
        c += step
        if np.hypot(*step) < 0.01 and abs(r_new - r) < 0.01:
            r = r_new
            break
        r = r_new
    return c, r


def _blob_balls(roi, mask, r_ref, known, raw=None):
    """한 덩어리에서 공(들)을 뽑는다. 반환: [(cx, cy, r, color, 깨끗한_단독공인지)]"""
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cs:
        return []
    c = max(cs, key=cv2.contourArea)
    pts = c.reshape(-1, 2).astype(float)
    hull = cv2.convexHull(c)
    harea = cv2.contourArea(hull)
    (hx, hy), hr = cv2.minEnclosingCircle(hull)
    hcirc = harea / (np.pi * hr * hr + 1e-9)
    out = []

    def color_at(cx, cy, rr):
        disk = np.zeros(mask.shape, np.uint8)
        cv2.circle(disk, (int(round(cx)), int(round(cy))), max(1, int(rr * 0.8)), 255, -1)
        sel = (disk > 0) & (mask > 0)
        if sel.sum() < 4:
            return None
        # 진짜 공은 안쪽 원의 대부분이 공 색이다 (마크가 있어도 ~70%).
        # 고스트볼 링이나 선이 엉킨 곳은 안쪽이 천이라 이 비율이 낮다.
        return classify(roi[sel], min_count=0.5 * float(np.count_nonzero(disk)))

    # 공 하나 크기 덩어리면, 마크가 테두리를 크게 파먹어 모양이 찌그러졌어도 한 개로 본다
    one_size = harea <= 1.35 * np.pi * r_ref ** 2 and hr <= 1.25 * r_ref
    single = (hcirc >= 0.78 and (not known or hr <= 1.3 * r_ref)) or (known and one_size and hcirc >= 0.45) \
        or (not known and hcirc >= 0.62)
    if single:
        # 마크가 테두리를 조금 파먹어도 바깥 껍질(볼록 껍질)의 외접원은 그대로다
        cx, cy, rr = hx, hy, hr
        if known:
            cx, cy = _fit_fixed_r(pts, (cx, cy), r_ref)
            rr = r_ref
        else:
            (fx, fy), fr = _fit_free(pts, (cx, cy), hr)
            # 작은 공(몇 픽셀)에선 맞춤이 흔들릴 수 있다 → 너무 벗어나면 외접원 그대로 쓴다
            if 0.75 * hr <= fr <= 1.05 * hr and np.hypot(fx - cx, fy - cy) <= 0.35 * hr:
                cx, cy, rr = fx, fy, fr
        col = color_at(cx, cy, rr)
        if col:
            out.append((cx, cy, rr, col, True))
        return out

    # 찌그러진 덩어리: 큐대가 붙었거나, 공 두 개가 붙어 있다 → 거리변환 봉우리마다 공 하나
    dt = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    r0 = r_ref
    work = dt.copy()
    for _ in range(4):
        m = float(work.max())
        if m < 0.6 * r0:
            break
        # 가장 깊은 점 하나를 잡고, 그 근처(0.5r 안)의 평탄한 꼭대기만 평균낸다.
        # (붙은 공 두 개의 꼭대기를 한꺼번에 평균내면 두 공 사이 접점에 중심이 잡힌다)
        py, px = np.unravel_index(int(np.argmax(work)), work.shape)
        ys, xs = np.where(work >= m - 0.75)
        near = (xs - px) ** 2 + (ys - py) ** 2 <= (0.5 * r0) ** 2
        cx, cy = float(xs[near].mean()), float(ys[near].mean())
        cv2.circle(work, (int(cx), int(cy)), int(1.6 * r0), 0, -1)
        rr = r0 if known else m
        if known:
            near = pts[np.abs(np.hypot(pts[:, 0] - cx, pts[:, 1] - cy) - r0) < 0.35 * r0]
            if len(near) >= 8:
                cx, cy = _fit_fixed_r(near, (cx, cy), r0)
        col = color_at(cx, cy, rr)
        if col:
            out.append((cx, cy, rr, col, False))
    return out


def find_balls(img, table, r_known=None):
    """r_known: 이미 아는 공 반지름(픽셀). 주면 그 크기 기준으로 거르고 중심을 정밀하게 맞춘다 (분석 2차·샷 추적)."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    x0, y0, x1, y1 = table.inner
    # 표준 캐롬 테이블: 공 지름 61.5mm / 내부 길이 2540mm
    r_expect = r_known if r_known else table.width * 61.5 / 2540 / 2

    pad = 2
    roi = hsv[y0 + pad:y1 - pad, x0 + pad:x1 - pad]
    cloth = cv2.inRange(roi, (90, 100, 60), (120, 255, 255))
    # 조준선·고스트볼 링의 검은 테두리도 배경으로 본다. 테두리까지 물체로 보면 선이 굵어져서
    # 열림 연산으로 안 지워지고 공에 들러붙는다. (공 안의 검은 마크 테두리는 아래 구멍 메우기로 다시 채워진다)
    dark = cv2.inRange(roi, (0, 0, 0), (179, 255, 70))
    obj = cv2.bitwise_not(cv2.bitwise_or(cloth, dark))

    # 1) 공 안의 마크(천과 같은 파란색) 구멍부터 메운다. 안 메우면 마크가 테두리 근처에 있을 때
    #    아래 열림 연산이 얇게 남은 빨간 띠를 지워서 공이 초승달로 쪼개진다.
    obj = _fill_small_holes(obj, r_expect)
    # 2) 조준선, 큐대 같은 얇은 것은 열림 연산으로 지운다
    k = max(3, int(r_expect * 0.6)) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    obj = cv2.morphologyEx(obj, cv2.MORPH_OPEN, kernel)
    # 열림 뒤 테두리에 걸쳐 생긴 작은 홈도 메운다
    obj = _fill_small_holes(obj, r_expect)

    n, lab, st, _ = cv2.connectedComponentsWithStats(obj)
    area_expect = np.pi * r_expect ** 2
    lo, hi = (0.35, 4.5) if r_known else (0.25, 16)
    found = []
    for i in range(1, n):
        area = st[i, cv2.CC_STAT_AREA]
        if area < area_expect * lo or area > area_expect * hi:
            continue
        x, y, w, h = st[i, :4]
        m = 3
        xa, ya = max(0, x - m), max(0, y - m)
        xb, yb = min(obj.shape[1], x + w + m), min(obj.shape[0], y + h + m)
        mask = (lab[ya:yb, xa:xb] == i).astype(np.uint8) * 255
        for cx, cy, rr, col, clean in _blob_balls(roi[ya:yb, xa:xb], mask, r_expect, bool(r_known)):
            found.append({"color": col, "x": cx + xa + x0 + pad, "y": cy + ya + y0 + pad, "r": rr, "clean": clean})

    balls = found
    if r_known:
        balls = [b for b in balls if 0.6 * r_known <= b["r"] <= 1.4 * r_known]
        radius = r_known
    elif balls:
        # 게임 공은 실제 비율보다 크게 그려지는 경우가 많아서, 검출된 공들의 중앙값을 기준으로
        # 크기가 너무 다른 것(UI 요소, 알림창 조각 등)은 버린다.
        # 크기는 깨끗한 단독 공으로만 잰다 (붙어 있는 공·큐대 붙은 공은 크기가 틀리게 나와서 기준을 망친다)
        clean = [b["r"] for b in balls if b.get("clean")] or [b["r"] for b in balls]
        radius = float(np.median(clean))
        balls = [b for b in balls if 0.72 * radius <= b["r"] <= 1.35 * radius]
        clean = [b["r"] for b in balls if b.get("clean")]
        if clean:
            radius = float(np.median(clean))
    else:
        radius = r_expect
    # 같은 공이 두 번 잡히면 하나만
    uniq = []
    for b in sorted(balls, key=lambda q: -q["r"]):
        if all(np.hypot(b["x"] - u["x"], b["y"] - u["y"]) > 1.2 * radius for u in uniq):
            uniq.append(b)
    for b in uniq:
        b.pop("clean", None)
        b["x"], b["y"], b["r"] = float(b["x"]), float(b["y"]), float(b["r"])
    return uniq, radius


def detect(img):
    table = find_table(img)
    if table is None:
        return None
    balls, radius = find_balls(img, table)
    if balls:
        # 공 크기를 알았으니 그 크기 기준으로 한 번 더 찾는다.
        # (조준할 때 큐대가 공에 붙어 있으면 첫 번째에서 놓칠 수 있어서)
        # 이때 중심도 고정 반지름으로 다시 맞춰서 마크 때문에 생기는 중심 치우침을 없앤다.
        balls2, _ = find_balls(img, table, r_known=radius)
        if len(balls2) >= len(balls):
            balls = balls2
    return Detection(table=table, balls=balls, radius=radius)
