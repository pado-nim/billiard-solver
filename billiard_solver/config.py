"""설정 (모드·내 공 색 등). 프로그램 폴더의 settings.json 하나에만 저장한다."""
import json
import os

from .physics import Params

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "settings.json")

DEFAULT = {
    "mode": "4ball",          # 4ball | 4ball_finish(4구 마무리 3쿠션) | 3cushion(3구)
    "cue_color": "white",     # white | yellow  (내 공 색)
    "angle_step": 0.25,       # 각도 탐색 간격 (도)
    "powers": [30, 40, 50, 60, 70, 80, 90, 100],
    "power_pick": 0.65,       # 득점되는 힘 범위 중 추천할 위치 (0.5=가운데, 높을수록 세게)
    "finish_targets": "reds", # 4구 마무리: reds=빨간 공 2개 / any2=상대 공 포함 아무 공 2개
    "top_n": 3,               # 보여줄 후보 수
    "monitor": 1,             # 모니터 번호 (1 = 주 모니터)
}


def load():
    cfg = dict(DEFAULT)
    try:
        with open(PATH, encoding="utf-8") as f:
            user = json.load(f)
        cfg.update({k: v for k, v in user.items() if k in DEFAULT})
    except (OSError, ValueError):
        pass
    return cfg


def save(cfg):
    try:
        with open(PATH, "w", encoding="utf-8") as f:
            json.dump({k: cfg[k] for k in DEFAULT}, f, ensure_ascii=False, indent=2)
    except OSError:
        pass                  # 저장 못 해도 이번 실행엔 지장 없음


def make_solver(cfg):
    from .solver import Solver
    return Solver(Params(), cfg["mode"], cfg["cue_color"], cfg["angle_step"], cfg["powers"],
                  finish_targets=cfg.get("finish_targets", "reds"), power_pick=cfg.get("power_pick", 0.65))
