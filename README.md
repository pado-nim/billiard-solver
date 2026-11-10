# 당구 솔버 (Billiard Solver)

로블록스 캐롬 당구(4구 · 4구 마무리 3쿠션 · 3구 3쿠션)를 **혼자 연습할 때** 쓰는 Windows용 샷 계산 오버레이입니다.
F2를 누르면 게임 화면을 읽어서 득점 경로, 조준 각도, 추천 힘을 게임 화면 위에 그려 줍니다.

> 화면 캡처만 읽습니다. 게임 파일이나 메모리는 건드리지 않고, 대신 쳐 주지도 않습니다.
> 다른 사람과 하는 대전에서는 쓰지 마세요. 상대에게 불공정하고 게임 규칙에 어긋날 수 있습니다.
> 이 프로젝트는 Roblox Corporation 및 게임 제작자와 관계가 없습니다.

## 기능

- **득점 경로 계산**: 수구 경로를 쿠션 반사·공 충돌까지 따라가서 득점되는 각도와 힘을 찾습니다.
- **내 조준 시뮬레이션 (F5)**: 게임 조준선을 읽어서 *지금 조준대로 치면* 수구·목적구가 어떻게 갈지 그려 줍니다.
  득점되는 힘 범위, 안 되면 이유(쿠션 몇 개 부족, 2적구를 공 몇 개 차이로 놓침, 상대 공 맞음),
  조금만 돌리면 득점되는 가장 가까운 각도까지 알려 줍니다. **실시간** 버튼을 켜면 조준을 움직이는 대로 따라갑니다.
- **후보 3개 + 안정성 %**: 물리값을 조금씩 흔들어도 득점되는 샷을 위로 올립니다. 숫자가 높을수록 실수에 강합니다.
- **모드 3개**: 4구 / 4구 마무리(3쿠션) / 3구(3쿠션). 고른 모드 그대로만 계산합니다 (자동 전환 없음).
- **공 인식**: 태극 무늬 같은 마크가 있는 공, 조준선·고스트볼 링이 닿은 공, 붙어 있는 공도 인식합니다.
- **조작 패널**: 버튼으로 전부 조작할 수 있고, 눌러도 게임 창 포커스를 뺏지 않습니다. 화면 배율(125~200%)에 맞춰 커집니다.
- **기록 없음**: 설정 파일(`settings.json`, 모드·내 공 색) 하나만 저장합니다. 로그나 이미지는 남기지 않습니다.

## 설치

필요한 것: Windows 10 (2004 이상) 또는 11, [Python 3.9 이상](https://www.python.org/downloads/)
(설치할 때 **Add python.exe to PATH** 체크)

1. 이 저장소를 내려받습니다 (Code → Download ZIP 후 압축 풀기, 또는 `git clone`).
2. `install.bat`을 더블클릭합니다. 가상환경(`.venv`)을 만들고 패키지를 설치한 뒤 바탕화면에 **당구 솔버** 바로가기를 만듭니다.
3. 바로가기(또는 `run.bat`)로 실행합니다.

## 사용법

1. 게임에서 내 차례가 되면 **F2** (또는 패널의 큰 버튼).
2. 화면에 1순위 경로(초록), 2·3순위(주황·하늘)가 그려집니다. 실선은 득점 순간까지, 점선은 그 뒤 경로입니다.
   원은 첫 번째 공에 맞는 순간 수구가 있을 자리(고스트볼)입니다.
3. 게임 조준선을 실선에 맞추고, 수구 옆에 표시된 힘으로 칩니다.

**내 조준 시뮬레이션** (4구 마무리처럼 F2로 경로가 잘 안 나올 때 직접 길을 찾아보기)

1. 게임에서 원하는 방향으로 조준합니다 (흰 조준선과 고스트볼 링이 보이는 상태).
2. **F5** (또는 패널의 보라색 버튼). 지금 조준대로 친 경로가 분홍색으로 그려집니다 (득점이면 초록색).
3. 화면 위 글씨로 결과를 봅니다.
   - `힘 70%로 치면: 빨1 → 쿠션2 → 빨2 → 두 번째 공 전에 쿠션 2개 (3개 필요, 1개 부족)`
   - `이 조준으로 득점되는 힘: 55~75%`
   - `가장 가까운 득점: 조준을 시계 방향으로 0.30° 돌리고 힘 90% (초록 점선)`
4. 패널의 **실시간** 버튼을 켜면 F5를 계속 누르지 않아도 조준을 움직이는 대로 경로가 따라옵니다 (초당 2~3번).

| 키 | 동작 |
|---|---|
| F2 | 분석 (다시 누르면 다시 분석) |
| F3 | 선 지우기 |
| F4 | 내 공 색 (흰공 / 노란공) |
| F5 | 내 조준 시뮬레이션 (지금 조준대로 치면 어떻게 되나) |
| F6 | 모드 바꾸기: 4구 → 4구 마무리(3쿠션) → 3구(3쿠션) |
| F7 | 다음 후보 강조 |
| F8 | 후보 전부 / 하나만 |
| Ctrl+Shift+Q | 종료 |

패널의 "인식: 흰 1 · 노랑 1 · 빨강 2" 줄로 공을 다 찾았는지 바로 확인할 수 있습니다. 모자라면 주황색으로 표시됩니다.

## 동작 원리

1. **화면 인식** (`detector.py`): 파란 천 색으로 테이블과 쿠션 안쪽 경계를 찾고, 천이 아닌 덩어리 중 공 모양인 것을 색으로 분류합니다.
   마크 구멍을 메우고, 공의 바깥 테두리에 원을 맞춰 중심을 정합니다 (튀어나온 조준선·들어간 마크 부분은 제외).
2. **경로 계산** (`physics.py`): 직선 + 쿠션 반사(법선·접선 반발) + 공 충돌 뒤 수구 방향으로 수구 경로를 따라갑니다.
3. **샷 탐색** (`solver.py`): 각도 0.25° 간격 × 힘 30~100%로 훑고, 득점되는 각도는 0.05°까지 좁힙니다.
   쿠션 반발·감속·밀림을 바꿔 가며 다시 계산해 안정성을 매기고 순위를 정합니다.
4. **내 조준 읽기** (`aimpreview.py`): 수구에서 나가는 흰 조준선에 직선을 맞추고, 끝의 고스트볼 링에 원을 맞춰
   수구 중심→링 중심 방향으로 조준 각도를 잽니다 (테스트 기준 오차 0.03° 이내). 그 각도로 힘 30~100%를 전부 쳐 봅니다.
5. **오버레이** (`app.py`, `panel.py`): 클릭이 통과하는 투명 창에 그리고, 그 창은 화면 캡처에서 빠지게 해서 다음 분석에 섞이지 않게 합니다.

물리값은 실제 게임 화면 측정으로 정한 고정값입니다. 회전(당점)은 다루지 않습니다.

## 한계

- 당점(회전)은 계산하지 않습니다. 항상 정중앙 타격 기준입니다.
- 3쿠션 경로는 힘과 조준 오차에 민감합니다. 안정성 %가 높은 후보를 고르세요.
- 게임 테마(천 색 등)가 바뀌면 `detector.py` 위쪽 색 범위를 고쳐야 할 수 있습니다.
- 녹화 프로그램(OBS 등)에는 오버레이 선이 안 찍힐 수 있습니다 (캡처 제외 설정 때문).

## 개발

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
pytest
```

테스트는 게임 이미지 없이 가짜 테이블을 그려서 돌립니다 (`tests/synth.py`). 태극 마크 위치 48가지, 고스트볼 링, 붙은 공, 모드별 경로 탐색,
조준선 각도 읽기와 "조금 돌리면 득점" 제안이 실제로 득점하는지를 확인합니다.

```
billiard_solver/
  app.py        오버레이, 단축키, 분석 실행
  panel.py      조작 패널 (버튼 창)
  detector.py   테이블·공 인식
  physics.py    경로 계산
  solver.py     규칙 판정과 샷 탐색
  aimpreview.py 내 조준 읽기와 시뮬레이션 (F5)
  render.py     그릴 것 목록
  config.py     설정 (settings.json)
tests/          pytest 테스트
```

## English summary

A Windows overlay for **solo practice** in Roblox carom billiards (4-ball, 4-ball 3-cushion finish, 3-ball 3-cushion).
Press F5 to read your current in-game aim line and see where that exact shot goes, which powers score, why it misses, and the nearest scoring correction (live-follow mode available).
Press F2: it reads a screenshot, detects the table and balls (including balls with a blue taegeuk mark), ray-traces the cue ball through cushions and ball contacts, and draws the top 3 scoring shots with angle, power and a robustness score.
It only reads the screen, never touches game files or memory, and does not shoot for you. Please don't use it in matches against other players.
Not affiliated with Roblox Corporation. Install with `install.bat`, run with `run.bat`. Tests: `pytest`.

## 라이선스

[MIT](LICENSE)
