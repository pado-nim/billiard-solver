"""규칙 판정과 샷 탐색.

mode:
  '4ball'        : 4구. 수구로 빨간 공 2개를 모두 맞히고, 상대 공은 건드리지 않으면 득점
  '4ball_finish' : 4구 마무리(3쿠션). 빨간 공 2개를 맞히되 두 번째 빨간 공 전까지 쿠션 3번 이상,
                   상대 공 금지. config "finish_targets": "any2" 면 상대 공 포함 아무 공 2개
  '3cushion'     : 3쿠션(공 3개). 나머지 두 공을 맞히되 두 번째 공 전까지 쿠션 3번 이상
"""
from dataclasses import dataclass
import math
import random

from .physics import Params, trace_ball


@dataclass
class Shot:
    angle: float          # 도 (화면 좌표, 0=오른쪽, 90=아래)
    power: float          # %
    window: float         # 같은 힘에서 성공하는 각도 폭 (도) - 클수록 실수에 강함
    power_ok: int         # 이 각도로 다른 힘에서도 성공한 개수
    score: float
    trace: object
    cushions: int
    score_index: int = -1
    pmin: float = 0.0          # 이 각도로 득점되는 힘 범위 (5% 단위)
    pmax: float = 0.0
    robust: float = 1.0        # 물리값·조준·힘·당점을 조금씩 틀리게 해 봐도 득점하는 비율 (안정성)
    english: tuple = (0.0, 0.0)  # 당점 (좌우 +오른쪽, 상하 +위), 1/3 = 1팁
    first_cushion: bool = False  # 첫 충돌이 쿠션인 샷 (부정확해서 순위를 크게 낮춤)
    length: float = 0.0        # 득점 순간까지 수구가 굴러간 거리 (테이블 긴 변 배수)


MODES = ("4ball", "4ball_finish", "3cushion")

T = 1.0 / 3.0
# 스핀 탐색에 쓰는 당점 (좌우, 상하). 1/3 = 1팁. 정중앙은 따로 먼저 탐색한다
MAX_TIP = 2 * T          # 게임 당점 화면의 초록 점선 원 = 공 반지름의 2/3 (2팁)까지만 칠 수 있다
_D = 2 ** 0.5
ENGLISH = [(x * T, y * T) for x in (-2, -1, 0, 1, 2) for y in (-2, -1, 0, 1, 2)
           if (x, y) != (0, 0) and x * x + y * y <= 4] + [(sx * _D * T, sy * _D * T) for sx in (-1, 1) for sy in (-1, 1)]


def clamp_tip(e):
    """당점을 게임 당점 원 안으로."""
    m = math.hypot(*e)
    if m <= MAX_TIP:
        return e
    return (e[0] * MAX_TIP / m, e[1] * MAX_TIP / m)


def _cushions_before(trace, targets, need):
    """need개의 목표 공을 맞힐 때까지 친 쿠션 수 (못 맞히면 None)."""
    cush, hit = 0, set()
    for e in trace.events:
        if e.kind == "cushion":
            cush += 1
        elif e.target in targets:
            hit.add(e.target)
            if len(hit) >= need:
                return cush
    return None


def judge(trace, mode, targets, forbidden, need=None):
    """득점이면 (True, 득점 순간까지 쿠션 수), 아니면 (False, None)."""
    need = need or len(targets)
    hit = [e.target for e in trace.events if e.kind == "ball"]
    if any(h in forbidden for h in hit):
        return False, None
    if len(set(hit) & set(targets)) < need:
        return False, None
    cush = _cushions_before(trace, set(targets), need)
    if mode in ("3cushion", "4ball_finish") and (cush is None or cush < 3):
        return False, None
    return True, cush


class Solver:
    def __init__(self, params: Params = None, mode="4ball", cue_color="white",
                 angle_step=0.25, powers=(30, 40, 50, 60, 70, 80, 90, 100), finish_targets="reds",
                 power_pick=0.65, use_spin=True):
        self.p = params or Params()
        self.finish_targets = finish_targets
        self.power_pick = power_pick      # 득점 힘 범위 중 어디를 추천할지 (0=최소, 0.5=가운데, 1=최대)
        self.mode = mode
        self.cue_color = cue_color
        self.angle_step = angle_step
        self.powers = powers
        self.use_spin = use_spin
        self.english = (0.0, 0.0)         # simulate가 쓰는 현재 당점

    def setup(self, det):
        """검출 결과에서 수구, 목적구, 금지구 인덱스를 정한다."""
        balls = det.balls
        # 모드는 사용자가 고른 그대로 쓴다 (공 개수로 자동 전환하지 않음)
        self.auto_mode = None
        self.fail_reason = None
        pos = [(b["x"], b["y"]) for b in balls]
        cues = [i for i, b in enumerate(balls) if b["color"] == self.cue_color]
        if not cues:
            self.fail_reason = "no_cue"
            return None
        cue = cues[0]
        reds = [i for i, b in enumerate(balls) if b["color"] == "red"]
        others = [i for i in range(len(balls)) if i != cue]
        opp = [i for i in others if balls[i]["color"] in ("white", "yellow")]
        need = None
        if self.mode == "4ball":
            targets, forbidden = reds, opp
            if len(targets) < 2:
                self.fail_reason = "need_2_reds"
                return None
        elif self.mode == "4ball_finish":
            if self.finish_targets == "any2":
                targets, forbidden, need = others, [], 2
            else:
                targets, forbidden = reds, opp
            if len(targets) < 2:
                self.fail_reason = "need_2_reds"
                return None
        else:   # 3cushion
            if len(others) == 2:
                targets, forbidden = others, []
            elif len(reds) >= 2:              # 공이 4개 보이면 마무리 규칙과 같게
                targets, forbidden = reds, opp
            else:
                self.fail_reason = "need_3_balls"
                return None
        r = det.radius
        x0, y0, x1, y1 = det.table.inner
        box = (x0 + r, y0 + r, x1 - r, y1 - r)
        return dict(pos=pos, cue=cue, targets=targets, forbidden=forbidden, need=need,
                    box=box, r=r, L=det.table.width, mode=self.mode, auto=False)

    def simulate(self, s, angle, power):
        return self.simulate_speed(s, angle, self.p.v0(power))

    def simulate_speed(self, s, angle, speed):
        return trace_ball(s["pos"][s["cue"]], angle, speed, s["pos"], {s["cue"]},
                          s["box"], s["r"], s["L"], self.p, english=self.english)

    def _ok(self, s, ang, pw):
        return judge(self.simulate(s, ang, pw), self.mode, s["targets"], s["forbidden"], s["need"])[0]

    def _refine(self, s, center, pw, span, fine=0.05):
        """center 주변 ±span도를 fine 간격으로 훑어, 가운데에서 가장 가까운 성공 구간의 (중심, 폭)."""
        m = int(span / fine)
        ok = [self._ok(s, center + i * fine, pw) for i in range(-m, m + 1)]
        best = None
        i = 0
        while i < len(ok):
            if ok[i]:
                j = i
                while j < len(ok) and ok[j]:
                    j += 1
                c = (i + j - 1) / 2 - m
                if best is None or abs(c) < abs(best[0]):
                    best = (c, (j - i) * fine)
                i = j
            else:
                i += 1
        if best is None:
            return None
        return (center + best[0] * fine) % 360, best[1]

    def _power_range(self, s, ang, pw):
        lo = hi = pw
        while lo - 5 >= 5 and self._ok(s, ang, lo - 5):
            lo -= 5
        while hi + 5 <= 100 and self._ok(s, ang, hi + 5):
            hi += 5
        return lo, hi

    MC_N = 32
    MIN_ROBUST = 0.10      # 이보다 낮은 안정성은 '경로 없음'으로 본다

    def _mc_success(self, s, ang, pw, n=None):
        """실전 흉내: 조준·힘·당점 실수와 물리값 오차를 한꺼번에 무작위로 넣어 n번 쳐 본 득점률.

        조준 σ0.12°, 힘 σ7%, 당점 σ0.08(약 1/4팁), follow σ0.1, 감속 ±18%, 쿠션 반발 σ3%,
        반사각 σ2%, 쿠션선 σ0.07r, 당점 효과 세기 σ20%.  같은 후보는 항상 같은 결과가 나오게 시드 고정.
        """
        n = n or self.MC_N
        rng = random.Random(int(ang * 1000) * 131 + int(pw) * 7 + int((self.english[0] + 2) * 97 + (self.english[1] + 2) * 13))
        base = self.p
        keep_p, keep_e = self.p, self.english
        ex, ey = self.english
        ok = 0
        try:
            for _ in range(n):
                q = Params.from_dict(base.to_dict())
                q.follow = base.follow + rng.gauss(0, 0.08)
                q.decel = base.decel * math.exp(rng.gauss(0, 0.18))
                q.cushion_e = min(1.0, base.cushion_e * (1 + rng.gauss(0, 0.03)))
                q.cushion_f = min(1.05, q.cushion_e * (base.cushion_f / max(base.cushion_e, 1e-6)) * (1 + rng.gauss(0, 0.08)))  # f는 신뢰도 낮음
                q.cushion_offset = base.cushion_offset + rng.gauss(0, 0.07)
                ks = math.exp(rng.gauss(0, 0.2))
                q.top_k, q.side_k = base.top_k * ks, base.side_k * ks
                self.p = q
                if ex or ey:
                    self.english = clamp_tip((ex + rng.gauss(0, 0.08), ey + rng.gauss(0, 0.08)))
                ok += self._ok(s, ang + rng.gauss(0, 0.12), max(5.0, pw * (1 + rng.gauss(0, 0.07))))
        finally:
            self.p, self.english = keep_p, keep_e
        return ok / n

    def _scan(self, s, angles, powers):
        """현재 당점으로 각도×힘을 훑어 성공 구간 후보 (중심각, 힘, 폭)."""
        step = angles[1] - angles[0] if len(angles) > 1 else self.angle_step
        candidates = []
        for pw in powers:
            ok = []
            for a in angles:
                tr = self.simulate(s, a, pw)
                good, _ = judge(tr, self.mode, s["targets"], s["forbidden"], s["need"])
                ok.append(good)
            for start, length in _runs(ok):
                center = (start + (length - 1) / 2.0) * step % 360
                candidates.append((center, pw, length * step))
        return candidates

    def _finish(self, s, center, pw, win, step):
        """후보 하나를 다듬어 Shot으로 (안 되면 None)."""
        got = self._refine(s, center, pw, win / 2 + step * 2)
        if got is None:
            return None
        ang, win = got
        lo, hi = self._power_range(s, ang, pw)
        mid = round((lo + (hi - lo) * self.power_pick) / 5) * 5
        if mid != pw:
            got2 = self._refine(s, ang, mid, max(win, 0.5))
            if got2 is not None:
                ang, win = got2
                pw = mid
                lo, hi = self._power_range(s, ang, pw)
        tr = self.simulate(s, ang, pw)
        good, cush = judge(tr, self.mode, s["targets"], s["forbidden"], s["need"])
        if not good:
            return None
        k = _score_event_index(tr, s["targets"], s["need"])
        length = _path_len(tr, k) / s["L"]
        prange = hi - lo
        extra = cush if self.mode == "4ball" else max(0, cush - 3)
        if self.mode == "4ball" and cush >= 3:
            extra = cush * 0.6
        rob = self._mc_success(s, ang, pw)
        tip = math.hypot(*self.english) * 3            # 몇 팁인지
        # 첫 충돌이 쿠션이면 그 뒤 각도를 정확히 알 수 없다 (게임 물리를 완벽히 모름).
        # 공을 먼저 맞히면 게임이 링·안내선으로 첫 구간을 보여 줘서 정확하다 → 공 먼저 샷을 크게 우대
        first_cushion = bool(tr.events) and tr.events[0].kind == "cushion"
        # 수구에서 첫 공까지 거리가 멀수록 조준 실수가 커진다
        first_len = 0.0
        if tr.events:
            e0 = tr.events[0]
            c0 = s["pos"][s["cue"]]
            first_len = math.hypot(e0.x - c0[0], e0.y - c0[1]) / s["L"]
        # 실전 득점률(안정성)을 가장 크게 보고, 짧은 경로·적은 쿠션을 우대 (쿠션 먼저·스핀은 solve에서 단계로 거름)
        score = ((0.05 + rob) ** 2 * (1 + 0.02 * prange)
                 / (1 + 0.8 * length) / (1 + 0.15 * extra) / (1 + 0.05 * tip) / (1 + 0.6 * first_len))
        sh = Shot(ang, pw, win, int(prange // 5), score, tr, cush)
        sh.pmin, sh.pmax = lo, hi
        sh.robust = rob
        sh.score_index = k
        sh.english = self.english
        sh.length = length
        sh.first_cushion = first_cushion
        return sh

    def _search(self, s, english, step, powers):
        self.english = english
        n = int(round(360 / step))
        out = []
        for center, pw, win in self._scan(s, [i * step for i in range(n)], powers):
            sh = self._finish(s, center, pw, win, step)
            if sh:
                out.append(sh)
        return out

    def solve(self, det, top_n=3):
        """우선순위: ① 무스핀 + 공 먼저  ② 스핀 + 공 먼저  ③ 쿠션 먼저 (최후의 보루, 무스핀 → 스핀).
        앞 단계에서 샷이 나오면 뒤 단계는 계산하지 않는다."""
        s = self.setup(det)
        if s is None:
            return [], None
        try:
            center = self._search(s, (0.0, 0.0), self.angle_step, self.powers)
            spin = []
            tiers = [[x for x in center if not x.first_cushion]]
            if self.use_spin and not tiers[0]:
                spin = [x for e in ENGLISH for x in self._search(s, e, 0.5, (40, 60, 80, 100))]
                tiers.append([x for x in spin if not x.first_cushion])
            tiers.append([x for x in center if x.first_cushion])
            if self.use_spin and not any(tiers):
                spin = spin or [x for e in ENGLISH for x in self._search(s, e, 0.5, (40, 60, 80, 100))]
                tiers.append([x for x in spin if x.first_cushion])
        finally:
            self.english = (0.0, 0.0)

        picked = []
        tiers = [[x for x in t if x.robust >= self.MIN_ROBUST] for t in tiers]   # 거의 안 들어가는 샷은 안 보여 줌
        for tier in tiers:                       # 앞 단계 샷을 먼저 채우고, 모자라면 다음 단계에서
            for sh in sorted(tier, key=lambda x: -x.score):
                if len(picked) >= top_n:
                    break
                if all(_angdiff(sh.angle, q.angle) > 3.0 for q in picked):
                    picked.append(sh)
        return picked, s


def _path_len(trace, k):
    """득점 이벤트(k번째)까지 수구가 간 거리 (픽셀)."""
    pts = trace.points
    end = trace.events[k].idx if 0 <= k < len(trace.events) else len(pts) - 1
    return sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(end))


def _score_event_index(trace, targets, need=None):
    tset, hit = set(targets), set()
    need = need or len(tset)
    for k, e in enumerate(trace.events):
        if e.kind == "ball" and e.target in tset:
            hit.add(e.target)
            if len(hit) >= need:
                return k
    return len(trace.events) - 1


def _angdiff(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _runs(flags):
    """원형 배열에서 True가 연속된 구간 (시작 인덱스, 길이)."""
    n = len(flags)
    if all(flags):
        return [(0, n)]
    if not any(flags):
        return []
    k = flags.index(False)            # False 위치에서 시작하면 경계에서 안 끊긴다
    runs, i = [], 0
    while i < n:
        j = (k + i) % n
        if flags[j]:
            length = 0
            while i < n and flags[(k + i) % n]:
                length += 1
                i += 1
            runs.append(((k + i - length) % n, length))
        else:
            i += 1
    return runs
