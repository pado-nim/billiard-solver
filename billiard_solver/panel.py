"""조작 패널 (버튼 창).

오버레이(화면 위 선)와 별개로 작은 창을 띄워서 마우스로 전부 조작할 수 있게 한다.
- 버튼을 눌러도 게임 창의 포커스를 뺏지 않는다 (WS_EX_NOACTIVATE)
- 화면 캡처에는 안 찍힌다 (패널이 당구대 위에 있어도 분석에 영향 없음)
- 크기는 Windows 화면 배율(DPI)에 맞춰 커진다
"""
import tkinter as tk

BG = "#1e2227"
BG2 = "#2a2f36"
FG = "#e8eaed"
SUB = "#9aa0a6"
ACC = "#f5c542"
ON = "#3b82f6"
RED = "#e05252"
FONT = "Malgun Gothic"

MODE_BTNS = [("4ball", "4구"), ("4ball_finish", "4구 마무리\n(3쿠션)"), ("3cushion", "3구\n(3쿠션)")]
CUE_BTNS = [("white", "흰공"), ("yellow", "노란공")]


class Panel:
    BASE_W = 370          # 100% 배율 기준 폭. 실제 폭은 화면 배율(DPI)에 맞춰 커진다

    def __init__(self, app):
        self.app = app
        w = self.win = tk.Toplevel(app.root)
        w.title("당구 솔버")
        w.configure(bg=BG)
        w.attributes("-topmost", True)
        w.protocol("WM_DELETE_WINDOW", app.quit)

        # 프로그램이 DPI 인식 모드라서, 125~200% 배율 화면에선 글자만 커지고 픽셀 크기는 그대로다.
        # 모든 픽셀 크기를 화면 배율로 키운다.
        try:
            sc = float(w.winfo_fpixels("1i")) / 96.0
        except Exception:
            sc = 1.0
        sc = min(max(sc, 1.0), 3.0)
        self.sc = sc
        P = self.P = lambda v: max(1, int(round(v * sc)))
        self.width = P(self.BASE_W)
        sw = app.mon["width"]
        w.geometry(f"{self.width}x{P(560)}+{app.mon['left'] + sw - self.width - P(24)}+{app.mon['top'] + P(70)}")
        w.minsize(P(330), P(400))
        w.resizable(True, True)

        def label(parent, text, size=10, fg=FG, bold=False, **kw):
            return tk.Label(parent, text=text, bg=parent["bg"], fg=fg,
                            font=(FONT, size, "bold" if bold else "normal"), **kw)

        def button(parent, text, cmd, bg=BG2, fg=FG, size=11, bold=False, ipady=7, **kw):
            b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, activebackground=ON,
                          activeforeground="#ffffff", relief="flat", bd=0, cursor="hand2",
                          font=(FONT, size, "bold" if bold else "normal"), pady=P(ipady),
                          disabledforeground=SUB, **kw)
            return b

        def section(title):
            label(body, title, 9, fg=SUB, bold=True).pack(anchor="w", pady=(P(10), P(4)))
            f = tk.Frame(body, bg=BG)
            f.pack(fill="x")
            return f

        self.label, self.button = label, button
        body = tk.Frame(w, bg=BG)
        body.pack(fill="both", expand=True, padx=P(16), pady=(P(12), P(14)))
        self.body = body

        top = tk.Frame(body, bg=BG)
        top.pack(fill="x")
        label(top, "당구 솔버", 15, bold=True).pack(side="left")
        self.phase_lbl = label(top, "대기", 10, fg=ACC, bold=True)
        self.phase_lbl.pack(side="right")

        # 모드
        mf = section("모드  (고른 그대로 계산 · F6)")
        self.mode_btns = {}
        for i, (key, txt) in enumerate(MODE_BTNS):
            b = button(mf, txt, lambda k=key: app.set_mode(k), size=11, bold=True, ipady=9, width=1)
            b.grid(row=0, column=i, padx=(0 if i == 0 else P(6), 0), sticky="nsew")
            mf.columnconfigure(i, weight=1, uniform="m")
            self.mode_btns[key] = b

        # 내 공
        cf = section("내 공  (F4)")
        self.cue_btns = {}
        for i, (key, txt) in enumerate(CUE_BTNS):
            b = button(cf, txt, lambda k=key: app.set_cue(k), size=11, width=1)
            b.grid(row=0, column=i, padx=(0 if i == 0 else P(6), 0), sticky="nsew")
            cf.columnconfigure(i, weight=1, uniform="c")
            self.cue_btns[key] = b

        # 메인 버튼
        tk.Frame(body, bg=BG, height=P(14)).pack(fill="x")
        self.main_btn = button(body, "분석  (F2)", app.on_f2, bg=ACC, fg="#1b1b1b", size=15, bold=True, ipady=14)
        self.main_btn.pack(fill="x")

        # 인식 결과 한 줄 (공을 몇 개 찾았는지 바로 보이게)
        self.det_lbl = label(body, "", 10, fg=SUB, anchor="w", justify="left")
        self.det_lbl.pack(fill="x", pady=(P(8), 0))

        # 보조 버튼
        self.sub_frame = tk.Frame(body, bg=BG)
        sf = self.sub_frame
        sf.pack(fill="x", pady=(P(10), 0))
        self.undo_btn = button(sf, "선 지우기  (F3)", app.clear)
        self.undo_btn.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, P(6)))
        button(sf, "다음 후보  (F7)", app.next_candidate, width=1).grid(row=1, column=0, sticky="nsew", padx=(0, P(3)))
        self.all_btn = button(sf, "후보 전부  (F8)", app.toggle_all, width=1)
        self.all_btn.grid(row=1, column=1, sticky="nsew", padx=(P(3), 0))
        sf.columnconfigure(0, weight=1, uniform="s")
        sf.columnconfigure(1, weight=1, uniform="s")

        # 상태 메시지
        self.msg_box = tk.Frame(body, bg=BG2)
        self.msg_box.pack(fill="both", expand=True, pady=(P(12), P(10)))
        self.msg_lbl = label(self.msg_box, "", 11, justify="left", anchor="nw")
        self.msg_lbl.pack(fill="both", expand=True, padx=P(12), pady=P(10))
        self.msg_box.bind("<Configure>", lambda e: self.msg_lbl.configure(wraplength=max(P(200), e.width - P(28))))

        bf = tk.Frame(body, bg=BG)
        bf.pack(fill="x", side="bottom")
        label(bf, "Ctrl+Shift+Q 로도 종료", 9, fg=SUB).pack(side="left")
        button(bf, "종료", app.quit, bg=RED, fg="#ffffff", size=10, ipady=5, width=8).pack(side="right")

        w.update_idletasks()
        self._no_activate()
        self._last = None

    def _det_text(self):
        last = getattr(self.app, "last", None)
        if not last or last[0] is None:
            return ""
        det = last[0]
        n = {c: sum(1 for b in det.balls if b["color"] == c) for c in ("white", "yellow", "red")}
        need = {"4ball": 4, "4ball_finish": 4, "3cushion": 3}.get(self.app.cfg.get("mode"), 4)
        tot = sum(n.values())
        mark = "✓" if tot >= need else "⚠"
        return f"{mark} 인식: 흰 {n['white']} · 노랑 {n['yellow']} · 빨강 {n['red']}  (공 {tot}개 / 필요 {need})"

    def _no_activate(self):
        """버튼을 눌러도 게임 창 포커스를 안 뺏고, 캡처에도 안 찍히게."""
        try:
            import ctypes
            from ctypes import wintypes
            u = ctypes.windll.user32
            u.GetParent.restype = wintypes.HWND
            u.GetParent.argtypes = [wintypes.HWND]
            hwnd = u.GetParent(self.win.winfo_id()) or self.win.winfo_id()
            style = u.GetWindowLongW(hwnd, -20)
            u.SetWindowLongW(hwnd, -20, style | 0x8000000)          # WS_EX_NOACTIVATE
            u.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
            u.SetWindowDisplayAffinity(hwnd, 0x11)
        except Exception:
            pass

    def refresh(self, phase, msg):
        a = self.app
        mode, cue = a.cfg.get("mode"), a.cfg.get("cue_color")
        det_txt = self._det_text()
        key = (phase, msg, mode, cue, a.show_all, det_txt)
        if key == self._last:
            return
        self._last = key
        for k, b in self.mode_btns.items():
            b.configure(bg=ON if k == mode else BG2, fg="#ffffff" if k == mode else FG)
        for k, b in self.cue_btns.items():
            sel = k == cue
            b.configure(bg=(("#f0f0f0" if k == "white" else "#f2c230") if sel else BG2),
                        fg=("#1b1b1b" if sel else FG))
        self.all_btn.configure(text="후보 하나만  (F8)" if a.show_all else "후보 전부  (F8)")

        names = {"idle": "대기", "busy": "계산 중…", "shown": "분석 완료"}
        self.phase_lbl.configure(text=names.get(phase, phase))
        # 창 높이를 내용에 맞춘다 (사용자가 늘린 폭은 유지)
        self.win.after_idle(self._fit_height)
        main = {"idle": ("분석  (F2)", ACC, "normal"),
                "shown": ("다시 분석  (F2)", ACC, "normal"),
                "busy": ("계산 중…", BG2, "disabled")}[phase]
        self.main_btn.configure(text=main[0], bg=main[1], state=main[2],
                                fg="#1b1b1b" if main[2] == "normal" else SUB)

        self.msg_lbl.configure(text=msg)
        self.det_lbl.configure(text=det_txt, fg=(SUB if det_txt.startswith("✓") else "#f59e0b"))

    def _fit_height(self):
        try:
            w = self.win
            w.update_idletasks()
            need = self.body.winfo_reqheight() + self.P(26)
            if abs(w.winfo_height() - need) > 4:
                w.geometry(f"{w.winfo_width()}x{need}")
        except Exception:
            pass
