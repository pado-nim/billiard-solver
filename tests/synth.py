"""테스트용 가짜 당구 화면 (게임 이미지 없이 테이블·공·태극 마크·조준선을 그린다)."""
import math

import cv2
import numpy as np

SCREEN = (1080, 1920)
OUTER = (218, 219, 1701, 978)
CUSH = 37
R_PX = 24.4
CLOTH = (240, 143, 34)
COLORS = {"white": (238, 238, 242), "yellow": (40, 215, 250), "red": (40, 35, 225)}


def background():
    img = np.full(SCREEN + (3,), (40, 45, 50), np.uint8)
    x0, y0, x1, y1 = OUTER
    cv2.rectangle(img, (x0 - 40, y0 - 40), (x1 + 40, y1 + 40), (20, 50, 120), -1)    # 나무 테두리
    cv2.rectangle(img, (x0, y0), (x1, y1), (245, 151, 41), -1)                        # 쿠션
    ix0, iy0, ix1, iy1 = x0 + CUSH, y0 + CUSH, x1 - CUSH, y1 - CUSH
    cv2.rectangle(img, (ix0, iy0), (ix1, iy1), CLOTH, -1)
    for k in range(18):                                                               # 쿠션 그림자
        a = 0.38 * (1 - k / 18)
        cv2.rectangle(img, (ix0 + k, iy0 + k), (ix1 - k, iy1 - k), tuple(int(c * (1 - a)) for c in CLOTH), 1)
    cv2.rectangle(img, (ix0 + 18, iy0 + 18), (ix1 - 18, iy1 - 18), CLOTH, -1)
    return img, (ix0, iy0, ix1, iy1)


def ball(img, x, y, color, mark=None, r=R_PX):
    """mark=(rho, angle, size): 태극 마크 위치(공 반지름 비율)·각도·크기. 천과 같은 파란색이 섞여 있다."""
    cv2.circle(img, (int(round(x * 16)), int(round(y * 16))), int(r * 16), COLORS[color], -1, cv2.LINE_AA, shift=4)
    if mark:
        rho, ang, size = mark
        mx, my = x + rho * r * math.cos(ang), y + rho * r * math.sin(ang)
        layer = img.copy()
        cv2.circle(layer, (int(mx), int(my)), int(size * r), (181, 71, 12), -1)
        cv2.ellipse(layer, (int(mx), int(my)), (int(size * r), int(size * r)), math.degrees(ang), 0, 180, (40, 30, 200), -1)
        cv2.circle(layer, (int(mx), int(my)), int(size * r), (60, 20, 20), 1)
        inside = np.zeros(img.shape[:2], np.uint8)
        cv2.circle(inside, (int(round(x)), int(round(y))), int(r), 255, -1)
        img[inside > 0] = layer[inside > 0]
    cv2.circle(img, (int(x - r * 0.3), int(y - r * 0.35)), 3, (255, 255, 255), -1, cv2.LINE_AA)


def ghost_ring(img, x, y, r=R_PX, to=None):
    """게임 조준선 끝의 속 빈 흰 원(고스트볼 링)과 거기로 들어오는 선. 검은 테두리 포함."""
    S = 16                                          # 소수점 좌표로 그리기 (shift=4)
    for col, t in (((30, 30, 30), 7), ((240, 240, 240), 4)):
        cv2.circle(img, (int(round(x * S)), int(round(y * S))), int(round(r * S)), col, t, cv2.LINE_AA, shift=4)
        if to is not None:
            dx, dy = to[0] - x, to[1] - y
            n = math.hypot(dx, dy) or 1.0
            sx, sy = x + dx / n * r, y + dy / n * r       # 링 테두리에서 시작
            cv2.line(img, (int(round(sx * S)), int(round(sy * S))), (int(round(to[0] * S)), int(round(to[1] * S))),
                     col, t, cv2.LINE_AA, shift=4)


def table_pos(inner, u, v):
    ix0, iy0, ix1, iy1 = inner
    return ix0 + u * (ix1 - ix0), iy0 + v * (iy1 - iy0)
