"""물리 파라미터와 수구 경로 계산 (레이 트레이싱).

단위: 길이 = 테이블 안쪽 긴 변(L) 길이, 시간 = 초.

- 공은 직선으로 굴러가며 감속한다 (휘지 않음, 당점은 정중앙).
- 쿠션: 법선 속도 cushion_e배, 접선 속도 cushion_f배로 반사한다.
- 공 충돌: 맞은 공은 중심선 방향으로 나가고, 수구는 접선 성분 + 약간의 밀림(follow)으로 나간다.

단순화: 맞은 목적구는 그 뒤 경로에서 빼고(키스 무시), 나머지 공은 멈춰 있다고 본다.
기본값은 실제 게임 화면 측정에서 정한 고정값이다.
"""
import math
from dataclasses import dataclass, field, fields

EPS = 1e-9


@dataclass
class Params:
    decel: float = 1.0              # 등감속 성분 (L/s^2)
    damping: float = 0.0            # 속도 비례 감쇠 (1/s)
    v0_max: float = 4.2             # 힘 100%의 초기 속도 (L/s)
    power_exponent: float = 1.0     # 초기속도 ∝ (힘%)^지수
    cushion_e: float = 0.70         # 쿠션 법선 속도 반발계수
    cushion_f: float = 0.60         # 쿠션 접선 속도 유지율 (게임 조준선 실측 반사비 0.80 × e)
    ball_loss: float = 0.97         # 공 충돌 추가 손실 (속도 배율)
    slide_decel: float = 0.70       # 미끄럼 마찰 가속도 (L/s^2). 클수록 금방 휘고 짧게 휨
    spin_k: float = 0.0             # 회전 비율 (속이 꽉 찬 공 = 2/7). 0이면 휘지 않음
    cushion_spin: float = 1.0       # 쿠션에 맞을 때 회전의 법선 성분이 남는 비율 (1=그대로, 0=없어짐)
    start_spin: float = 0.0         # 칠 때 게임이 주는 앞뒤 회전 (0=정중앙, 1=바로 구름, >1 밀어치기, <0 끌어치기)
    cushion_ratio_slope: float = 0.0  # 입사각에 따라 반사 비율이 바뀌는 정도 (조준선에서 학습). 비율 = f/e + 기울기×(입사각/45-1)
    follow: float = 0.15            # 공에 맞은 뒤 수구가 앞으로 밀리는 정도 (0=90도 법칙, 실측으로 학습)
    follow_n: float = 0.0           # 위 값을 잰 샘플 수 (적으면 추천할 때 불확실성을 크게 잡음)
    cushion_offset: float = 0.18    # 실제 쿠션 충돌선이 인식한 쿠션선보다 안쪽으로 들어온 정도 (공 반지름 단위, 조준선에서 학습)
    stop_speed: float = 0.005       # 이 속도(L/s) 아래면 정지

    @classmethod
    def from_dict(cls, d):
        names = {f.name for f in fields(cls)}
        return cls(**{k: float(v) for k, v in (d or {}).items() if k in names})

    def to_dict(self):
        return {f.name: getattr(self, f.name) for f in fields(self)}

    # ----- 속도 <-> 남은 거리 -----
    def budget(self, v):
        """속도 v(L/s)에서 멈출 때까지 굴러가는 거리(L)."""
        a, k, s = max(self.decel, 0.0), max(self.damping, 0.0), self.stop_speed
        if v <= s:
            return 0.0
        if k < 1e-6:
            return (v * v - s * s) / (2 * max(a, 1e-6))
        if a < 1e-9:
            return (v - s) / k
        return (v - s) / k - (a / (k * k)) * math.log((a + k * v) / (a + k * s))

    def speed_from_budget(self, d):
        if d <= 0:
            return self.stop_speed
        if max(self.damping, 0.0) < 1e-6:                  # 등감속만: 닫힌식 (빠름)
            return math.sqrt(2 * max(self.decel, 1e-6) * d + self.stop_speed ** 2)
        lo, hi = self.stop_speed, 1.0
        while self.budget(hi) < d and hi < 1e4:
            hi *= 2
        for _ in range(50):
            mid = (lo + hi) / 2
            if self.budget(mid) < d:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    def reflect_ratio(self, vn, vt):
        """쿠션 반사 후 접선/법선 기울기 비율 tan(반사)/tan(입사). 입사각에 따라 달라질 수 있다."""
        base = self.cushion_f / max(self.cushion_e, 1e-6)
        if self.cushion_ratio_slope:
            ang = math.degrees(math.atan2(abs(vt), max(abs(vn), 1e-9)))
            base += self.cushion_ratio_slope * (ang / 45.0 - 1.0)
        return min(max(base, 0.2), 1.8)

    def v0(self, power):
        return self.v0_max * (max(power, 0.0) / 100.0) ** self.power_exponent

    def power_for_v0(self, v):
        return 100.0 * (max(v, 0.0) / self.v0_max) ** (1.0 / self.power_exponent)


@dataclass
class Event:
    kind: str          # 'cushion' | 'ball'
    x: float
    y: float
    side: str = ""     # cushion: 'L','R','T','B'
    target: int = -1   # ball: 공 인덱스
    idx: int = -1      # Trace.points 안에서 이 이벤트 지점의 인덱스


@dataclass
class Trace:
    points: list = field(default_factory=list)   # 수구 중심 경로 [(x,y), ...] (픽셀)
    events: list = field(default_factory=list)
    object_paths: dict = field(default_factory=dict)  # 맞은 목적구 인덱스 -> 경로


def _ray_circle(px, py, dx, dy, cx, cy, R):
    fx, fy = px - cx, py - cy
    b = fx * dx + fy * dy
    c = fx * fx + fy * fy - R * R
    disc = b * b - c
    if disc < 0:
        return None
    s = -b - math.sqrt(disc)
    if s < EPS:
        if c < 0 and b < 0:
            return 0.0
        return None
    return s


def _ray_box(px, py, dx, dy, box):
    x0, y0, x1, y1 = box
    best, side = math.inf, ""
    if dx > EPS:
        t = (x1 - px) / dx
        if t < best: best, side = t, "R"
    elif dx < -EPS:
        t = (x0 - px) / dx
        if t < best: best, side = t, "L"
    if dy > EPS:
        t = (y1 - py) / dy
        if t < best: best, side = t, "B"
    elif dy < -EPS:
        t = (y0 - py) / dy
        if t < best: best, side = t, "T"
    return max(best, 0.0), side


def _hit_along(px, py, dx, dy, length, box, balls, gone, R2):
    """직선 구간에서 가장 먼저 닿는 것: (거리, 'wall'|'ball', side|index) 또는 None"""
    wall_t, side = _ray_box(px, py, dx, dy, box)
    best = (wall_t, "wall", side)
    for i, (bx, by) in enumerate(balls):
        if i in gone:
            continue
        t = _ray_circle(px, py, dx, dy, bx, by, R2)
        if t is not None and t < best[0]:
            best = (t, "ball", i)
    return best if best[0] <= length else None


def trace_ball(start, angle_deg, speed, balls, skip, box, r, table_len, p: Params,
               max_events=30, follow_objects=True, spin=(0.0, 0.0)):
    """start에서 angle 방향(화면 좌표, 0도=오른쪽, 90도=아래)으로 초기속도 speed(L/s)로 친다.

    balls: [(x,y), ...] 픽셀   skip: 경로에서 제외할 공 인덱스(수구 자신 포함)
    box  : 공 중심이 움직일 수 있는 사각형 (쿠션 코에서 r만큼 안쪽, 픽셀)
    spin : 처음 회전 속도 w (L/s, 화면 좌표). 정중앙 타격이면 0.
    반환 Trace.points는 휘는 구간을 잘게 나눈 꺾은선이다.
    """
    L = float(table_len)
    if p.cushion_offset:
        o = p.cushion_offset * r
        box = (box[0] + o, box[1] + o, box[2] - o, box[3] - o)
    px, py = start
    a = math.radians(angle_deg)
    vx, vy = speed * math.cos(a), speed * math.sin(a)       # L/s
    wx, wy = spin
    if spin == (0.0, 0.0) and p.start_spin:
        wx, wy = vx * p.start_spin, vy * p.start_spin    # 게임 기본 당점
    tr = Trace(points=[(px, py)])
    gone = set(skip)
    R2 = 2 * r
    k = min(max(p.spin_k, 0.0), 0.95)
    a_s = max(p.slide_decel, 1e-3)
    events = 0
    guard = 0

    while events < max_events and guard < 400:
        guard += 1
        sx, sy = vx - wx, vy - wy
        slip = math.hypot(sx, sy)
        hit = None
        if k > 1e-4 and slip > 0.01:
            # ---- 미끄러지는 중: 가속도 A = -a_s * (slip 방향), 포물선 ----
            ux, uy = sx / slip, sy / slip
            ax, ay = -a_s * ux, -a_s * uy
            t_r = k * slip / a_s
            sp = math.hypot(vx, vy)
            n = int(min(30, max(3, (sp * t_r * L) / (1.5 * r) + 1)))
            t_prev = 0.0
            qx, qy = px, py
            for j in range(1, n + 1):
                t = t_r * j / n
                nx_ = px + (vx * t + 0.5 * ax * t * t) * L
                ny_ = py + (vy * t + 0.5 * ay * t * t) * L
                cdx, cdy = nx_ - qx, ny_ - qy
                cl = math.hypot(cdx, cdy)
                if cl > 1e-6:
                    h = _hit_along(qx, qy, cdx / cl, cdy / cl, cl, box, balls, gone, R2)
                    if h is not None:
                        te = t_prev + (t - t_prev) * (h[0] / cl)
                        px, py = qx + cdx / cl * h[0], qy + cdy / cl * h[0]
                        vx, vy = vx + ax * te, vy + ay * te
                        g = (1 - k) / k
                        wx, wy = wx - g * ax * te, wy - g * ay * te
                        hit = h
                        break
                tr.points.append((nx_, ny_))
                qx, qy, t_prev = nx_, ny_, t
            if hit is None:
                px, py = qx, qy
                vx, vy = vx + ax * t_r, vy + ay * t_r
                wx, wy = vx, vy                       # 이제 구른다
                continue
        else:
            # ---- 굴러가는 중: 직선, 구름 마찰 ----
            sp = math.hypot(vx, vy)
            if sp <= p.stop_speed:
                break
            dx, dy = vx / sp, vy / sp
            dist = p.budget(sp) * L
            if dist <= 0.5:
                break
            h = _hit_along(px, py, dx, dy, dist, box, balls, gone, R2)
            if h is None:
                px, py = px + dx * dist, py + dy * dist
                tr.points.append((px, py))
                break
            px, py = px + dx * h[0], py + dy * h[0]
            v_now = p.speed_from_budget((dist - h[0]) / L)
            vx, vy = dx * v_now, dy * v_now
            wx, wy = vx, vy
            hit = h

        # ---- 이벤트 처리 ----
        tr.points.append((px, py))
        events += 1
        if hit[1] == "wall":
            side = hit[2]
            tr.events.append(Event("cushion", px, py, side=side, idx=len(tr.points) - 1))
            if side in ("L", "R"):
                q = p.reflect_ratio(vx, vy) * p.cushion_e
                vx, vy = -vx * p.cushion_e, vy * q
                wx = wx * p.cushion_spin
            else:
                q = p.reflect_ratio(vy, vx) * p.cushion_e
                vx, vy = vx * q, -vy * p.cushion_e
                wy = wy * p.cushion_spin
        else:
            i = hit[2]
            bx, by = balls[i]
            nx, ny = (bx - px) / R2, (by - py) / R2
            vn = vx * nx + vy * ny
            tr.events.append(Event("ball", px, py, target=i, idx=len(tr.points) - 1))
            gone.add(i)
            if follow_objects:
                ov = abs(vn) * p.ball_loss
                oang = math.degrees(math.atan2(ny, nx))
                others = [j for j in range(len(balls)) if j != i]
                sub = trace_ball((bx, by), oang, ov, balls, set(others), box, r,
                                 table_len, p, max_events=3, follow_objects=False, spin=(1e-12, 0.0))
                tr.object_paths[i] = sub.points
            fol = p.follow * max(vn, 0.0)
            vx, vy = (vx - vn * nx + fol * nx) * p.ball_loss, (vy - vn * ny + fol * ny) * p.ball_loss
            # 회전(w)은 그대로 → 앞으로 휘어 나간다
        if math.hypot(vx, vy) <= p.stop_speed and math.hypot(vx - wx, vy - wy) <= 0.01:
            break
    return tr
