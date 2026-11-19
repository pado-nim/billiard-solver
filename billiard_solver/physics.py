"""물리 파라미터와 수구 경로 계산 (레이 트레이싱).

단위: 길이 = 테이블 안쪽 긴 변(L) 길이, 시간 = 초.

- 공은 직선으로 굴러가며 감속한다 (휘지 않음).
- 쿠션: 법선 속도 cushion_e배로 반사하고, 반사각은 게임 안내선처럼 입사각이 클수록 넓어진다 (reflect_ratio).
- 공 충돌: 맞은 공은 중심선 방향으로 나가고, 수구는 접선 성분 + 밀림(follow)으로 나간다.
- 당점(english=(좌우, 상하), 각각 -1~+1, 1/3 = 1팁):
    상하: 위(밀어치기)면 공에 맞은 뒤 앞으로 더 밀리고, 아래(끌어치기)면 뒤로 끌린다 (follow에 더해짐)
    좌우: 쿠션에 맞을 때 회전 방향으로 옆으로 밀려 반사각이 바뀐다 (오른쪽 당점 → 쿠션에서 오른쪽으로),
          쿠션을 맞을 때마다 회전이 줄어든다
  회전 효과는 충돌 순간의 방향 변화로만 넣는다 (경로가 휘지 않음).

단순화: 맞은 목적구는 그 뒤 경로에서 빼고(키스 무시), 나머지 공은 멈춰 있다고 본다.
방향 계수는 게임 안내선(조준선·링에서 나가는 선)에 맞춘 값이다.
"""
import math
from dataclasses import dataclass, field, fields

EPS = 1e-9

from .calibration import value as _C


@dataclass
class Params:
    # 기본값은 calibration.py 표에서 온다 (출처·신뢰도 포함)
    decel: float = _C("decel")                     # 굴러가는 감속 (L/s^2)
    v0_max: float = _C("v0_max")                   # 힘 100%의 초기 속도 (L/s)
    power_exponent: float = _C("power_exponent")   # 초기속도 ∝ (힘%)^지수
    cushion_e: float = _C("cushion_e")             # 쿠션 법선 속도 반발계수
    cushion_f: float = _C("cushion_f")             # 쿠션 접선 속도 유지율. 반사 비율 f/e = 게임 안내선 0.86
    ball_loss: float = _C("ball_loss")             # 공 충돌 뒤 수구 속도 배율
    obj_transfer: float = _C("obj_transfer")       # 맞은 공이 받는 속도 (법선 속도 대비)
    follow: float = _C("follow")                   # 공에 맞은 뒤 수구가 앞으로 밀리는 정도 (0 = 90도 법칙)
    cushion_offset: float = _C("cushion_offset")   # 쿠션 충돌선이 인식한 쿠션선보다 안쪽인 정도 (공 반지름 단위)
    stop_speed: float = 0.005                      # 이 속도(L/s) 아래면 정지
    top_k: float = _C("top_k")                     # 상하 당점 1(3팁)일 때 follow에 더해지는 양
    side_k: float = _C("side_k")                   # 좌우 당점 1(3팁)일 때 쿠션에서 옆으로 밀리는 속도 (법선 속도 대비)
    side_decay: float = _C("side_decay")           # 쿠션 한 번 맞을 때마다 남는 좌우 회전 비율
    bend_ratio: float = _C("bend_ratio")           # 쿠션 뒤 휘고 나서의 반사 비율 tan(반사)/tan(입사) (실제 공)
    bend_dist: float = _C("bend_dist")             # 쿠션 뒤 휘어서 각도가 바뀌기까지 거리 (공 반지름 단위)

    @classmethod
    def from_dict(cls, d):
        names = {f.name for f in fields(cls)}
        return cls(**{k: float(v) for k, v in (d or {}).items() if k in names})

    def to_dict(self):
        return {f.name: getattr(self, f.name) for f in fields(self)}

    # ----- 속도 <-> 남은 거리 (등감속) -----
    def budget(self, v):
        """속도 v(L/s)에서 멈출 때까지 굴러가는 거리(L)."""
        s = self.stop_speed
        return 0.0 if v <= s else (v * v - s * s) / (2 * max(self.decel, 1e-6))

    def speed_from_budget(self, d):
        return math.sqrt(2 * max(self.decel, 1e-6) * max(d, 0.0) + self.stop_speed ** 2)

    def reflect_ratio(self, vn, vt):
        """쿠션 반사 tan(반사각)/tan(입사각). 게임 안내선처럼 비스듬히 들어갈수록 넓게 튄다.
        45° 이하는 f/e, 그 위는 안내선 표의 비율만큼 늘어난다."""
        ang = math.degrees(math.atan2(abs(vt), max(abs(vn), 1e-12)))
        base = self.cushion_f / max(self.cushion_e, 1e-6)
        tbl = _C("cushion_ratio_by_angle")
        for (a0, r0), (a1, r1) in zip(tbl, tbl[1:]):
            if ang <= a1:
                r = r0 + (r1 - r0) * (ang - a0) / (a1 - a0)
                break
        else:
            r = tbl[-1][1]
        return min(max(base * r / tbl[0][1], 0.2), 1.8)

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
               max_events=30, follow_objects=True, english=(0.0, 0.0)):
    """start에서 angle 방향(화면 좌표, 0도=오른쪽, 90도=아래)으로 초기속도 speed(L/s)로 친다.

    balls: [(x,y), ...] 픽셀   skip: 경로에서 제외할 공 인덱스(수구 자신 포함)
    box  : 공 중심이 움직일 수 있는 사각형 (쿠션 코에서 r만큼 안쪽, 픽셀)
    english: 당점 (좌우 +오른쪽, 상하 +위), 각각 -1~1. 1/3 = 1팁.
    """
    L = float(table_len)
    if p.cushion_offset:
        o = p.cushion_offset * r
        box = (box[0] + o, box[1] + o, box[2] - o, box[3] - o)
    px, py = start
    a = math.radians(angle_deg)
    vx, vy = speed * math.cos(a), speed * math.sin(a)       # L/s
    tr = Trace(points=[(px, py)])
    gone = set(skip)
    R2 = 2 * r
    side = float(english[0])                  # 남아 있는 좌우 회전
    top = float(english[1])                   # 공에 처음 맞을 때 쓰이는 상하 회전

    bend = None                               # 쿠션 뒤 휘기 전까지 남은 거리(px)와 휜 뒤 방향
    events = guard = 0
    while events < max_events and guard < 4 * max_events + 8:
        guard += 1
        sp = math.hypot(vx, vy)
        if sp <= p.stop_speed:
            break
        dx, dy = vx / sp, vy / sp
        dist = p.budget(sp) * L
        if dist <= 0.5:
            break
        reach = min(dist, bend[0]) if bend else dist
        hit = _hit_along(px, py, dx, dy, reach, box, balls, gone, R2)
        if hit is None:
            px, py = px + dx * reach, py + dy * reach
            tr.points.append((px, py))
            if bend and reach < dist:            # 휘는 지점: 방향만 바꾸고 계속 (이벤트 아님)
                v_now = p.speed_from_budget((dist - reach) / L)
                vx, vy = bend[1] * v_now, bend[2] * v_now
                bend = None
                continue
            break
        if bend:
            bend = (bend[0] - hit[0], bend[1], bend[2])
        px, py = px + dx * hit[0], py + dy * hit[0]
        v_now = p.speed_from_budget((dist - hit[0]) / L)
        vx, vy = dx * v_now, dy * v_now
        tr.points.append((px, py))
        events += 1
        bend = None

        if hit[1] == "wall":
            wall = hit[2]
            tr.events.append(Event("cushion", px, py, side=wall, idx=len(tr.points) - 1))
            onx, ony = {"L": (-1.0, 0.0), "R": (1.0, 0.0), "T": (0.0, -1.0), "B": (0.0, 1.0)}[wall]
            vn_in = abs(vx * onx + vy * ony)
            g = p.reflect_ratio(vx, vy) if wall in ("L", "R") else p.reflect_ratio(vy, vx)   # 게임 안내선 반사 비율
            if wall in ("L", "R"):
                vx, vy = -vx * p.cushion_e, vy * g * p.cushion_e
            else:
                vx, vy = vx * g * p.cushion_e, -vy * p.cushion_e
            if abs(side) > 1e-6:
                # 좌우 회전: 오른쪽 당점으로 위쪽 쿠션에 맞으면 오른쪽으로 튄다
                kick = p.side_k * side * vn_in
                vx, vy = vx - kick * ony, vy + kick * onx
                side *= p.side_decay
            # 실제 공: 쿠션 직후엔 게임 안내선 방향으로 나가다가 bend_dist 뒤 더 넓은 각도로 휜다
            if p.bend_dist > 0:
                if wall in ("L", "R"):
                    fx, fy = vx, vy * p.bend_ratio / max(g, 1e-6)
                else:
                    fx, fy = vx * p.bend_ratio / max(g, 1e-6), vy
                fn = math.hypot(fx, fy)
                if fn > 1e-9:
                    bend = (p.bend_dist * r, fx / fn, fy / fn)
        else:
            i = hit[2]
            bx, by = balls[i]
            nx, ny = (bx - px) / R2, (by - py) / R2
            vn = vx * nx + vy * ny
            tr.events.append(Event("ball", px, py, target=i, idx=len(tr.points) - 1))
            gone.add(i)
            if follow_objects:
                others = [j for j in range(len(balls)) if j != i]
                sub = trace_ball((bx, by), math.degrees(math.atan2(ny, nx)), abs(vn) * p.obj_transfer,
                                 balls, set(others), box, r, table_len, p, max_events=3, follow_objects=False)
                tr.object_paths[i] = sub.points
            fol = (p.follow + p.top_k * top) * max(vn, 0.0)
            top = 0.0                              # 상하 회전은 첫 충돌에서 쓰인다
            side *= 0.8
            vx, vy = (vx - vn * nx + fol * nx) * p.ball_loss, (vy - vn * ny + fol * ny) * p.ball_loss
    return tr
