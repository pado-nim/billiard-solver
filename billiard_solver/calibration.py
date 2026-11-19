"""물리 계수 캘리브레이션 표 (v2.1).

목표는 현실 당구가 아니라 원본 로블록스 게임의 실제 공 움직임을 따라 하는 것.
각 계수에 출처와 신뢰도를 붙여 둔다. physics.Params 기본값은 이 표의 value를 쓴다.

status:
  실측        영상에서 직접 잰 값 (표본 수·구간 있음)
  맞춤추정    여러 샷을 다시 쳐 보며 오차가 가장 작아지게 맞춘 값 (데이터에 노이즈·미지 변수가 섞여 신뢰도 낮음)
  미확정      식별할 자료가 없음. value는 동작용 임시값이며 실측값이 아니다
  가정        게임 UI·규칙에서 정한 값

자료:
  V1 = bandicam_2026-11-20_00-01-01-097.mp4 (252초, 2800×1964, 60fps, 원본 전 프레임 추적, 13샷)
       샷별 당점·힘은 영상에 없음 (AI 상대 샷 포함) → 스핀 섞임 가능
  V2 = bandicam 2026-11-20 00-22-33-242.mp4 (362초) — 원본 영상 미제공.
       spin_coordinates.csv(당점 팝업 좌표 25개), detections2fps.csv(2fps)만 있음 → 충돌 단위 측정 불가
"""

CAL = {
    "cushion_e": dict(value=0.61, status="실측", conf="높음", n=10, ci=(0.60, 0.62),
                      src="V1 목적구(당점 없음) 쿠션 반사 10회, 법선 속도비 중앙값. 수구 포함 33회도 0.62"),
    "cushion_f": dict(value=0.77, status="맞춤추정", conf="낮음~중간", n=15, ci=(0.70, 0.85),
                      src="V1 목적구 반사각 15회에 맞춤 (tan비 1.26 = 실측 중앙값과 일치). 접선 속도비 직접 측정은 산포가 커서(0.45~0.82) 반사각으로 맞춤"),
    "cushion_offset": dict(value=0.03, status="실측", conf="중간", n=58, ci=(-0.2, 0.3),
                           src="V1 쿠션 접점이 인식한 쿠션선에서 떨어진 거리 중앙값 ≈ 1px (공 반지름 30px)"),
    "decel": dict(value=0.05, status="맞춤추정", conf="중간", n=101, ci=(0.02, 0.10),
                  src="V1 직선 구간 감속 표본 101개 + 11샷 재현 맞춤: 감속 ≈ 0.05 + 0.10×속도 (L/s²)"),
    "damping": dict(value=0.10, status="맞춤추정", conf="중간", n=101, ci=(0.05, 0.35),
                    src="위와 같음"),
    "roll_factor": dict(value=0.70, status="맞춤추정", conf="중간", n=11, ci=(0.60, 0.80),
                        src="V1 친 직후 미끄럼 구간 속도 감소 (예: 1.11→0.82 L/s) + 재현 맞춤. 이론값 5/7"),
    "v0_max": dict(value=2.2, status="맞춤추정", conf="낮음", n=1, ci=(1.8, 2.8),
                   src="V1 56.3초 게이지 100% 확인 샷의 첫 속도 1.8 L/s 한 점 + 빠른 샷 2.4~2.8. 샷 순간 게이지 값이 안 보여 힘-속도 곡선 미확정"),
    "power_exponent": dict(value=1.0, status="미확정", conf="-", n=0, ci=None,
                           src="힘 % 와 첫 속도를 함께 잰 샷이 1개뿐"),
    "follow": dict(value=0.55, status="맞춤추정", conf="낮음", n=3, ci=(0.35, 0.75),
                   src="V1 깨끗한 공-공 충돌 3건: 수구가 맞은 뒤 앞으로 가는 비율 0.53~0.74. 샷별 당점 미상"),
    "obj_transfer": dict(value=0.60, status="맞춤추정", conf="낮음", n=5, ci=(0.33, 0.70),
                         src="V1 충돌 직후 목적구 속도 / 수구 법선 속도"),
    "ball_loss": dict(value=0.97, status="미확정", conf="-", n=0, ci=None, src="분리 측정 안 됨"),
    "top_k": dict(value=0.60, status="미확정", conf="-", n=0, ci=None,
                  src="같은 충돌 조건에서 위·아래 당점만 바꾼 샷이 필요 (V2 원본 60fps 영상이 있으면 측정 가능)"),
    "side_k": dict(value=0.22, status="미확정", conf="-", n=1, ci=None,
                   src="V1 246.5초 오른쪽 위 당점 샷에서 쿠션 반사 tan비 3.4 (중앙 ≈1.3) — 방향(오른쪽 당점 → 오른쪽으로 튐)만 확인, 크기 미확정"),
    "side_decay": dict(value=0.60, status="미확정", conf="-", n=0, ci=None, src="자료 없음"),
    "spin_k": dict(value=0.0, status="미확정", conf="-", n=0, ci=None,
                   src="V1에서 공 충돌 뒤 휘어 보이는 샷 3건 있으나 당점 미상이라 곡률 계수 식별 불가 → 끔 (휘지 않는 모델)"),
    "max_tip": dict(value=2 / 3, status="가정", conf="높음", n=None, ci=None,
                    src="게임 당점 화면의 초록 점선 원 = 공 반지름의 2/3. V2 팝업 좌표 25개도 모두 반지름 ≤0.8 (읽기 오차 ±0.1)"),
}


def value(name):
    return CAL[name]["value"]


def table_rows():
    """README·리포트용 행 목록."""
    out = []
    for k, c in CAL.items():
        ci = f"{c['ci'][0]}~{c['ci'][1]}" if c.get("ci") else "-"
        out.append((k, c["value"], c["status"], c["conf"], c.get("n"), ci, c["src"]))
    return out
