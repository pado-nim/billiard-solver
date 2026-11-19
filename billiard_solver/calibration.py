"""물리 계수 표 (v2.2).

목표: 사용자가 보고 맞추는 **게임 안내선(조준선·링에서 나가는 선)과 같은 방향**으로 계산하는 것.
v2.1에서 영상 추적값(쿠션에서 더 넓게 튐, 공 맞은 뒤 더 앞으로 감)으로 바꿨더니 게임 안내선과 어긋나서
실제로 써 보니 나빠졌다. 그래서 방향을 정하는 값은 게임 안내선 기준(v2.0 값)으로 되돌렸다.

status:
  안내선   게임이 그리는 안내선을 화면에서 읽어 맞춘 값
  맞춤     예전 버전에서 쓰며 맞춘 값
  미확정   식별할 자료가 없음. value는 동작용 임시값
  가정     게임 UI·규칙에서 정한 값
"""

CAL = {
    "cushion_e": dict(value=0.70, status="맞춤", src="v2.0 값. 반사 방향은 f/e 비율로만 정해짐"),
    "cushion_f": dict(value=0.60, status="안내선",
                      src="반사 비율 f/e = 0.86. 게임 쿠션 안내선 읽기 0.80~0.9와 맞음. "
                          "(영상 목적구 추적 1.26은 안내선과 크게 달라 쓰지 않음)"),
    "cushion_offset": dict(value=0.18, status="안내선", src="조준선 링이 쿠션에 닿는 위치"),
    "decel": dict(value=1.0, status="맞춤", src="v2.0 값 (힘은 예상치)"),
    "v0_max": dict(value=4.2, status="맞춤", src="v2.0 값"),
    "power_exponent": dict(value=1.0, status="미확정", src="힘 %와 속도를 함께 잰 자료 부족"),
    "follow": dict(value=0.0, status="안내선",
                   src="공 맞은 뒤 수구 방향 = 게임 안내선처럼 접선(90도 법칙). 안내선 읽기 0.02"),
    "obj_transfer": dict(value=0.97, status="맞춤", src="v2.0 값"),
    "ball_loss": dict(value=0.97, status="미확정", src="분리 측정 안 됨"),
    "top_k": dict(value=0.60, status="미확정", src="자료 없음 → 스핀은 무스핀으로 안 될 때만 씀"),
    "side_k": dict(value=0.22, status="미확정", src="방향만 확인 (오른쪽 당점 → 오른쪽으로 튐)"),
    "side_decay": dict(value=0.60, status="미확정", src="자료 없음"),
    "max_tip": dict(value=2 / 3, status="가정", src="게임 당점 화면의 초록 점선 원 = 2팁"),
}


def value(name):
    return CAL[name]["value"]
