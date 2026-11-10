"""당구 솔버 오버레이.

F2를 누르면 화면을 한 장 찍어서 테이블과 공을 찾고, 득점 경로·각도·힘을 게임 화면 위에 그린다.
조작은 조작 패널(버튼 창)이나 단축키로 한다.

  F2  분석 (다시 누르면 다시 분석)        F3  선 지우기
  F4  내 공 색 (흰공/노란공)               F5  내 조준 시뮬레이션 (지금 조준대로 치면 어떻게 되나)
  F6  모드: 4구 → 4구 마무리(3쿠션) → 3구(3쿠션)
  F7  다음 후보                            F8  후보 전부 / 하나만
  Ctrl+Shift+Q  종료

파일은 settings.json(모드·공 색) 하나만 쓴다. 기록·로그는 남기지 않는다.
"""
import ctypes
import queue
import sys
import threading
import time
import tkinter as tk

import numpy as np

from . import aimpreview, config, render
from .detector import detect
from .solver import MODES

TRANSPARENT = "#010101"
user32 = ctypes.windll.user32 if sys.platform == "win32" else None

VK = {"F2": 0x71, "F3": 0x72, "F4": 0x73, "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
      "CTRL": 0x11, "SHIFT": 0x10, "Q": 0x51}


def set_dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


class App:
    def __init__(self):
        import mss
        self.cfg = config.load()
        self.sct = mss.mss()
        mon_i = self.cfg.get("monitor", 1)
        if mon_i >= len(self.sct.monitors):
            mon_i = 1
        self.mon = dict(self.sct.monitors[mon_i], index=mon_i)
        self.scale = self.mon["width"] / 1920

        # 화면 전체를 덮는 투명·클릭 통과 오버레이
        self.root = tk.Tk()
        self.root.title("Billiard Solver Overlay")
        self.root.overrideredirect(True)
        self.root.geometry(f"{self.mon['width']}x{self.mon['height']}+{self.mon['left']}+{self.mon['top']}")
        self.root.attributes("-topmost", True)
        self.root.config(bg=TRANSPARENT)
        self.root.attributes("-transparentcolor", TRANSPARENT)
        self.canvas = tk.Canvas(self.root, bg=TRANSPARENT, highlightthickness=0,
                                width=self.mon["width"], height=self.mon["height"])
        self.canvas.pack(fill="both", expand=True)
        self.root.update_idletasks()
        self.excluded = self._make_click_through()

        self.show_all = True
        self.selected = 0
        self.busy = False
        self.last = None              # (det, shots, setup)   F2 분석 결과
        self.preview = None           # (det, 결과)            F5 내 조준 시뮬레이션 결과
        self.live = False             # 실시간 따라가기 (조준을 움직이면 계속 다시 계산)
        self._live_det = None         # 실시간 모드에선 공 위치를 잠깐 재사용 (조준선만 다시 읽음)
        self._live_det_t = 0.0
        self.results = queue.Queue()
        self.keys = {}
        self.msg = "F2: 분석  ·  F5: 내 조준 시뮬레이션"
        self._last_status = None
        from .panel import Panel
        self.panel = Panel(self)
        self.root.after(30, self.tick)

    # ---------- Windows 창 설정 ----------
    def _make_click_through(self):
        """오버레이를 클릭 통과로 만들고, 화면 캡처에서 빼서 우리가 찍는 화면에 우리 선이 안 섞이게 한다."""
        try:
            from ctypes import wintypes
            user32.GetParent.restype = wintypes.HWND
            user32.GetParent.argtypes = [wintypes.HWND]
            user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
            hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            style = user32.GetWindowLongW(hwnd, -20)
            style |= 0x80000 | 0x20 | 0x80 | 0x8000000   # LAYERED | TRANSPARENT | TOOLWINDOW | NOACTIVATE
            user32.SetWindowLongW(hwnd, -20, style)
            return bool(user32.SetWindowDisplayAffinity(hwnd, 0x11))   # WDA_EXCLUDEFROMCAPTURE (Win10 2004+)
        except Exception:
            return False

    # ---------- 상태 ----------
    def phase(self):
        if self.live:
            return "live"
        if self.busy:
            return "busy"
        if self.preview is not None:
            return "preview"
        return "shown" if self.last is not None else "idle"

    # ---------- 메인 루프 ----------
    def tick(self):
        try:
            self.poll_keys()
            while not self.results.empty():
                self.handle(self.results.get_nowait())
            self._draw_status()
        except SystemExit:
            raise
        except Exception as e:
            self.busy = False
            self.msg = f"오류가 나서 초기화했어요 ({e}). F2로 다시"
        self.root.after(30, self.tick)

    def handle(self, item):
        kind = item[0]
        self.busy = False
        if kind == "solved":
            det, shots, setup, reason = item[1]
            self.last = (det, shots, setup) if det is not None else None
            self.selected = 0
            kor = render.KOR_MODE.get(self.cfg["mode"], self.cfg["mode"])
            if det is None:
                self.msg = "당구대를 못 찾았어요. 게임 화면이 보일 때 F2"
            elif not any(b["color"] == self.cfg["cue_color"] for b in det.balls):
                self.msg = "내 공을 못 찾았어요 (내 공 색 확인 · F4)"
            elif reason == "need_2_reds":
                n_red = sum(1 for b in det.balls if b["color"] == "red")
                self.msg = f"{kor} 모드인데 빨간 공이 {n_red}개 보여요. 3구면 모드를 '3구(3쿠션)'으로 바꾸세요"
            elif reason == "need_3_balls":
                self.msg = f"{kor} 모드: 공이 {len(det.balls)}개만 보여요 (공이 가려졌는지 확인)"
            elif shots:
                sh = shots[0]
                self.msg = f"[{kor}] 1순위: 각도 {sh.angle:.2f}° · 힘 {sh.power:.0f}% · 안정성 {sh.robust:.0%}"
            else:
                self.msg = f"[{kor}] 득점 경로를 못 찾았어요"
        elif kind == "preview":
            det, pv, err = item[1]
            if pv is not None:
                self.preview = (det, pv)
                self.last = None
                self.msg = self._preview_msg(pv)
            elif not (self.live and self.preview is not None):    # 실시간 중엔 한 번 못 읽어도 이전 것 유지
                self.preview = None
                self.msg = err
            if self.live:
                self.root.after(250, self._live_next)
        elif kind == "error":
            self.msg = item[1]
        self.redraw()

    def _preview_msg(self, pv):
        if pv["scored"]:
            need = f", 필요한 힘 {pv['min_power']}% 이상(예상)" if pv["min_power"] else ", 세게 치세요"
            return f"내 조준 {pv['angle']:.2f}°: 득점 경로{need}"
        if pv["fix"]:
            way = "시계" if pv["fix"]["delta"] > 0 else "반시계"
            return f"내 조준 {pv['angle']:.2f}°: {pv['why']}. {way} 방향 {abs(pv['fix']['delta']):.2f}° 돌리면 득점"
        return f"내 조준 {pv['angle']:.2f}°: {pv['why']}"

    def pressed(self, name, combo=False):
        down = key_down(VK[name])
        if combo:
            down = down and key_down(VK["CTRL"]) and key_down(VK["SHIFT"])
        k = name + ("+" if combo else "")
        was = self.keys.get(k, False)
        self.keys[k] = down
        return down and not was

    def poll_keys(self):
        if self.pressed("Q", combo=True):
            self.quit()
        if self.pressed("F2"):
            self.on_f2()
        if self.pressed("F3"):
            self.clear()
        if self.pressed("F4"):
            self.set_cue("yellow" if self.cfg["cue_color"] == "white" else "white")
        if self.pressed("F5"):
            self.aim_preview()
        if self.pressed("F6"):
            cur = self.cfg["mode"] if self.cfg["mode"] in MODES else "4ball"
            self.set_mode(MODES[(MODES.index(cur) + 1) % len(MODES)])
        if self.pressed("F7"):
            self.next_candidate()
        if self.pressed("F8"):
            self.toggle_all()

    # ---------- 동작 ----------
    def on_f2(self):
        self.live = False
        if not self.busy:
            self.solve()

    def clear(self):
        self.live = False
        if self.busy:
            return
        self.last = None
        self.preview = None
        self.msg = "F2: 분석  ·  F5: 내 조준 시뮬레이션"
        self.redraw()

    # ---------- 내 조준 시뮬레이션 (F5) ----------
    def aim_preview(self):
        if self.busy:
            return
        self.busy = True
        if not self.live:
            self.msg = "내 조준 읽는 중..."
        self.redraw()
        img = self.grab()
        cfg = dict(self.cfg)
        reuse = self._live_det if (self.live and time.time() - self._live_det_t < 2.0) else None

        def work():
            try:
                det = reuse or detect(img)
                if det is None:
                    self.results.put(("preview", (None, None, "당구대를 못 찾았어요. 게임 화면이 보일 때 F5")))
                    return
                if reuse is None:
                    self._live_det, self._live_det_t = det, time.time()
                aim = aimpreview.read_aim(img, det, cfg["cue_color"])
                if aim is None:
                    self.results.put(("preview", (det, None,
                                                  "조준선이 안 보여요. 게임에서 조준 중일 때(흰 조준선이 보일 때) F5")))
                    return
                pv = aimpreview.analyze(det, aim, cfg)
                if "error" in pv:
                    kor = render.KOR_MODE.get(cfg["mode"], cfg["mode"])
                    why = {"need_2_reds": f"{kor} 모드인데 빨간 공이 2개가 아니에요 (모드 확인)",
                           "need_3_balls": f"{kor} 모드: 공이 모자라요",
                           "no_cue": "내 공을 못 찾았어요 (내 공 색 확인 · F4)"}.get(pv["error"], "계산할 수 없어요")
                    self.results.put(("preview", (det, None, why)))
                    return
                self.results.put(("preview", (det, pv, "")))
            except Exception as e:
                self.results.put(("preview", (None, None, f"조준 시뮬레이션 오류: {e}")))
        threading.Thread(target=work, daemon=True).start()

    def toggle_live(self):
        self.live = not self.live
        if self.live:
            self._live_det = None
            self.msg = "실시간: 게임에서 조준을 움직이면 경로가 따라가요"
            self.aim_preview()
        else:
            self.msg = "실시간 끔"
        self.redraw()

    def _live_next(self):
        if self.live and not self.busy:
            self.aim_preview()

    def set_mode(self, mode):
        if mode not in MODES:
            return
        changed = mode != self.cfg.get("mode")
        self._set_cfg("mode", mode)
        kor = render.KOR_MODE[mode]
        if self.busy:
            self.msg = f"모드: {kor} (다음 분석부터 적용)"
        elif changed and self.preview is not None and not self.live:
            self.msg = f"모드: {kor} → 내 조준 다시 계산"
            self.aim_preview()
            return
        elif changed and self.last is not None:
            self.msg = f"모드: {kor} → 다시 분석"
            self.solve()                     # 분석해 둔 화면이 있으면 새 모드로 바로 다시 계산
            return
        else:
            self.msg = f"모드: {kor}. F2: 분석"
        self.redraw()

    def set_cue(self, color):
        changed = color != self.cfg.get("cue_color")
        self._set_cfg("cue_color", color)
        name = "노란공" if color == "yellow" else "흰공"
        if changed and self.preview is not None and not self.busy and not self.live:
            self.msg = f"내 공: {name} → 내 조준 다시 계산"
            self.aim_preview()
            return
        if changed and self.last is not None and not self.busy:
            self.msg = f"내 공: {name} → 다시 분석"
            self.solve()
            return
        self.msg = f"내 공: {name}. F2: 분석"
        self.redraw()

    def next_candidate(self):
        self.selected += 1
        self.redraw()

    def toggle_all(self):
        self.show_all = not self.show_all
        self.redraw()

    def quit(self):
        try:
            self.root.destroy()
        finally:
            sys.exit(0)

    def _set_cfg(self, key, value):
        self.cfg[key] = value
        config.save(self.cfg)

    # ---------- 분석 ----------
    def grab(self):
        if not self.excluded:             # 캡처 제외가 안 되는 Windows면 잠깐 숨기고 찍는다
            self.root.withdraw()
            self.panel.win.withdraw()
            self.root.update()
            time.sleep(0.05)
        shot = self.sct.grab(self.mon)
        if not self.excluded:
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            self.panel.win.deiconify()
        return np.asarray(shot)[:, :, :3].copy()

    def solve(self):
        self.busy = True
        self.last = None
        self.preview = None
        self.msg = "분석 중..."
        self.redraw()
        img = self.grab()
        cfg = dict(self.cfg)

        def work():
            try:
                det = detect(img)
                if det is None:
                    self.results.put(("solved", (None, [], None, None)))
                    return
                sv = config.make_solver(cfg)
                shots, setup = sv.solve(det, cfg["top_n"])
                self.results.put(("solved", (det, shots, setup, getattr(sv, "fail_reason", None))))
            except Exception as e:
                self.results.put(("error", f"분석 오류: {e}. F2로 다시"))
        threading.Thread(target=work, daemon=True).start()

    # ---------- 그리기 ----------
    def redraw(self):
        self.canvas.delete("all")
        k = self.scale
        if self.preview is not None:
            det, pv = self.preview
            for p in render.build_preview(det, pv, self.cfg["cue_color"], scale=k):
                self._draw(p)
        elif self.last is not None:
            det, shots, setup = self.last
            for p in render.build(det, shots, setup, self.cfg["mode"], self.cfg["cue_color"],
                                  show_all=self.show_all, selected=self.selected, scale=k):
                self._draw(p)
        self._last_status = None
        self._draw_status()

    def _draw_status(self):
        ph = self.phase()
        self.panel.refresh(ph, self.msg)
        kor = render.KOR_MODE.get(self.cfg.get("mode"), "")
        st = f"[{kor}]  {self.msg}"
        if st == self._last_status:
            return
        self._last_status = st
        self.canvas.delete("status")
        k = self.scale
        self._text(12, self.mon["height"] - 40 * k, st, "#ffffff", 13 * k, tag="status")

    def _draw(self, p):
        c = self.canvas
        if p[0] == "line":
            _, pts, col, w, dashed = p
            if len(pts) < 2:
                return
            flat = [v for xy in pts for v in xy]
            w = max(1, int(w * self.scale))
            c.create_line(*flat, fill="#000000", width=w + 2, dash=(8, 6) if dashed else None)
            c.create_line(*flat, fill=col, width=w, dash=(8, 6) if dashed else None)
        elif p[0] == "circle":
            _, (x, y), r, col, w = p
            c.create_oval(x - r, y - r, x + r, y + r, outline=col, width=max(1, int(w * self.scale)))
        elif p[0] == "text":
            _, (x, y), t, col, size = p
            self._text(x, y, t, col, size)

    def _text(self, x, y, t, col, size, tag=None):
        f = ("Malgun Gothic", -max(8, int(size * 1.3)), "bold")
        tags = (tag,) if tag else ()
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            self.canvas.create_text(x + dx, y + dy, text=t, fill="#000000", font=f, anchor="nw", tags=tags)
        self.canvas.create_text(x, y, text=t, fill=col, font=f, anchor="nw", tags=tags)

    def run(self):
        self.root.mainloop()


def _already_running():
    k32 = ctypes.windll.kernel32
    _already_running.handle = k32.CreateMutexW(None, False, "BilliardSolver_single_instance")
    return k32.GetLastError() == 183          # ERROR_ALREADY_EXISTS


def _message(text):
    try:
        user32.MessageBoxW(None, text, "당구 솔버", 0x40)
    except Exception:
        pass


def main():
    if sys.platform != "win32":
        print("Billiard Solver는 Windows에서만 동작해요.")
        return 1
    if _already_running():
        _message("당구 솔버가 이미 실행 중이에요.")
        return 0
    set_dpi_aware()
    try:
        App().run()
    except SystemExit:
        raise
    except Exception as e:
        _message("실행 중 오류가 났어요.\n\n" + str(e))
        return 1
    return 0
