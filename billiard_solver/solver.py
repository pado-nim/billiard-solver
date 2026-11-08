"""규칙 판정과 샷 탐색.

mode:
  '4ball'        : 4구. 수구로 빨간 공 2개를 모두 맞히고, 상대 공은 건드리지 않으면 득점
  '4ball_finish' : 4구 마무리(3쿠션). 빨간 공 2개를 맞히되 두 번째 빨간 공 전까지 쿠션 3번 이상,
                   상대 공 금지. config "finish_targets": "any2" 면 상대 공 포함 아무 공 2개
  '3cushion'     : 3쿠션(공 3개). 나머지 두 공을 맞히되 두 번째 공 전까지 쿠션 3번 이상
"""
from dataclasses import dataclass
import math

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
    robust: float = 1.0        # 물리값을 조금씩 틀리게 바꿔봐도 득점하는 비율 (안정성)


MODES = ("4ball", "4ball_finish", "3cushion")


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
                 power_pick=0.65):
        self.p = params or Params()
        self.finish_targets = finish_targets
        self.power_pick = power_pick      # 득점 힘 범위 중 어디를 추천할지 (0=최소, 0.5=가운데, 1=최대)
        self.mode = mode
        self.cue_color = cue_color
        self.angle_step = angle_step
        self.powers = powers

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
                          s["box"], s["r"], s["L"], self.p)

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

    def _perturbed(self):
        """학습한 물리값이 이 정도는 틀릴 수 있다고 보고 만든 '조금 다른 물리' 목록."""
        if getattr(self, "_pert", None) is not None:
            return self._pert
        base = self.p.to_dict()
        ratio = base["cushion_f"] / max(base["cushion_e"], 1e-6)
        out = []

        def mk(**ch):
            d = dict(base)
            d.update(ch)
            return Params.from_dict(d)
        for k in (0.92, 1.08):
            e = min(base["cushion_e"] * k, 1.0)
            out.append(mk(cushion_e=e, cushion_f=min(ratio * e, 1.05)))           # 쿠션 반발
            out.append(mk(cushion_f=min(base["cushion_f"] * k, 1.05)))              # 반사각
            out.append(mk(v0_max=base["v0_max"] * k))                               # 힘 (세기)
        for k in (0.7, 1.4):
            out.append(mk(decel=base["decel"] * k, damping=base["damping"] * k))    # 감속
        # 공 맞은 뒤 밀림: 3쿠션 성공률을 가장 크게 좌우한다. 아직 덜 배웠으면 넓게 흔들어 본다
        fs = 0.12 if base.get("follow_n", 0) >= 6 else 0.3
        for d in (-fs, -fs / 2, fs / 2, fs):
            out.append(mk(follow=base["follow"] + d))
        for d in (-0.1, 0.1):
            out.append(mk(cushion_offset=base["cushion_offset"] + d))              # 쿠션선 위치
        self._pert = out
        return out

    def _robust(self, s, ang, pw):
        ok = 0
        keep = self.p
        try:
            for q in self._perturbed():
                self.p = q
                ok += self._ok(s, ang, pw)
        finally:
            self.p = keep
        return ok / len(self._perturbed())

    def solve(self, det, top_n=3):
        self._pert = None
        s = self.setup(det)
        if s is None:
            return [], None
        n = int(round(360 / self.angle_step))
        angles = [i * self.angle_step for i in range(n)]

        # 1) 힘별로 전체 각도를 훑어 성공 구간(연속된 각도)을 찾는다
        candidates = []
        for pw in self.powers:
            ok = []
            for a in angles:
                tr = self.simulate(s, a, pw)
                good, _ = judge(tr, self.mode, s["targets"], s["forbidden"], s["need"])
                ok.append(good)
            for start, length in _runs(ok):
                center = (start + (length - 1) / 2.0) * self.angle_step % 360
                candidates.append((center, pw, length * self.angle_step))

        # 2) 후보 주변을 0.05도 간격으로 다시 훑어서 성공 폭을 정확히 재고 가운데를 잡는다
        # 3) 그 각도에서 힘을 5%씩 바꿔가며 득점되는 힘 범위를 재고, 힘은 그 범위 가운데로 고친다
        #    (힘이 조금 달라도 들어가는 샷 = 휘는 정도가 달라져도 버티는 샷)
        shots = []
        for center, pw, win in candidates:
            got = self._refine(s, center, pw, win / 2 + self.angle_step * 2)
            if got is None:
                continue
            ang, win = got
            lo, hi = self._power_range(s, ang, pw)
            # 범위 위쪽 힘을 추천: 세게 칠수록 덜 휘어서 예측이 잘 맞고, 힘이 조금 모자라도 들어간다
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
                continue
            prange = hi - lo
            pok = int(prange // 5)
            # 성공 각도 폭이 넓고, 힘 범위가 넓고, 쿠션이 적을수록 좋은 샷
            extra = cush if self.mode == "4ball" else max(0, cush - 3)
            if self.mode == "4ball" and cush >= 3:
                extra = cush * 0.6
            rob = self._robust(s, ang, pw)
            # 안정성(물리가 조금 틀려도 들어가나)을 가장 크게 본다
            score = (0.1 + rob) ** 2 * win * (1 + 0.04 * prange) * (0.9 + pw / 500.0) / (1 + 0.25 * extra)
            sh = Shot(ang, pw, win, pok, score, tr, cush)
            sh.pmin, sh.pmax = lo, hi
            sh.robust = rob
            sh.score_index = _score_event_index(tr, s["targets"], s["need"])
            shots.append(sh)

        shots.sort(key=lambda x: -x.score)
        picked = []
        for sh in shots:
            if not all(_angdiff(sh.angle, q.angle) > 3.0 for q in picked):
                continue
            picked.append(sh)
            if len(picked) >= top_n:
                break
        return picked, s


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
