import json
import tkinter as tk
from tkinter import ttk, messagebox
import cv2
import PIL.Image
import PIL.ImageTk
from .constants import *
from .widgets import HelpWindow, ToolTip, ScrollableFrame, HybridSlider, LEDIndicator, ToggleSwitch

class SettingsDialog:
    def __init__(self, parent, config_manager, gpio_handler=None, cameras=None, on_save_callback=None):
        self.sw = tk.Toplevel(parent)
        self.sw.title("詳細設定")
        self.sw.geometry("1400x900")
        self.sw.configure(bg=COLOR_BG_MAIN)
        self.sw.grab_set()
        self.cm, self.gpio, self.cameras, self.on_save = config_manager, gpio_handler, cameras, on_save_callback
        self.vars, self.leds, self.af_btns, self.has_changes, self.active_entry = {}, {}, {}, False, None
        
        # メイン画面の動作を一時停止 (§5-143)
        if hasattr(parent, "app_instance"):
            self.parent_app = parent.app_instance
            self.parent_app.is_paused = True
            self.sw.protocol("WM_DELETE_WINDOW", self._on_close)
        else:
            self.parent_app = None

        self.preview_canvases = {}
        self._preview_geom = {"ref": {}, "insp": {}}
        self._preview_photo = {"ref": None, "insp": None}
        self._drag_canvas = None
        self._roi_draft = {"crop_ref_text": None, "crop_insp_text": None}
        self._confirm_btns = {}

        style = ttk.Style()
        style.theme_use('default')
        style.configure("TNotebook", background=COLOR_BG_MAIN, borderwidth=0)
        style.configure("TNotebook.Tab", background=COLOR_BG_PANEL, foreground=COLOR_TEXT_SUB, 
                        padding=[20, 10], font=FONT_SET_TAB, borderwidth=1)
        style.map("TNotebook.Tab", 
                  background=[("selected", COLOR_ACCENT)], 
                  foreground=[("selected", "black")])
        
        self._setup_ui()
        self._check_gpio_status()

    def _setup_ui(self):
        # フッター (保存/キャンセル)
        footer = tk.Frame(self.sw, bg=COLOR_BG_MAIN, pady=25)
        footer.pack(side=tk.BOTTOM, fill=tk.X)
        
        btn_f = tk.Frame(footer, bg=COLOR_BG_MAIN)
        btn_f.pack(side=tk.RIGHT, padx=40)

        tk.Button(footer, text="ヘルプ", font=FONT_SET_LBL, bg=COLOR_BG_INPUT, fg=COLOR_ACCENT, relief=tk.FLAT, padx=20, pady=10, command=self.show_settings_help).pack(side=tk.LEFT, padx=40)

        tk.Button(btn_f, text="キャンセル", font=FONT_BTN_LARGE, bg="#78909C", fg="white", relief=tk.FLAT, padx=30, pady=10, command=self._on_close).pack(side=tk.LEFT, padx=10)
        self.btn_save = tk.Button(btn_f, text="保存して閉じる", font=FONT_BTN_LARGE, bg=COLOR_BG_INPUT, fg="white", relief=tk.FLAT, padx=40, pady=10, command=self._save)
        self.btn_save.pack(side=tk.LEFT, padx=10)

        # タブ
        self.nb = ttk.Notebook(self.sw)
        self.nb.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=25, pady=10)
        
        self.tab_contents = {}
        tabs = [("t_cam", "カメラ"), ("t_gpio", "GPIOピン"), ("t_res", "画素数"), ("t_sys", "システム")]
        for key, text in tabs:
            tab_frame = tk.Frame(self.nb, bg=COLOR_BG_MAIN)
            self.nb.add(tab_frame, text=text)
            scroll = ScrollableFrame(tab_frame)
            scroll.pack(fill=tk.BOTH, expand=True)
            self.tab_contents[key] = scroll.scrollable_frame

        self._build_cam_tab()
        self._build_gpio_tab()
        self._build_res_tab()
        self._build_sys_tab()
        self._update_indicators()

    def _create_section(self, parent, title):
        frame = tk.Frame(parent, bg=COLOR_BG_PANEL, bd=1, relief=tk.SOLID, highlightbackground=COLOR_BORDER, highlightthickness=1)
        frame.pack(fill=tk.X, pady=(0, 20), padx=5)
        header = tk.Frame(frame, bg="#333333", padx=15, pady=8)
        header.pack(fill=tk.X)
        tk.Label(header, text=title, font=FONT_SET_LBL, bg="#333333", fg=COLOR_ACCENT).pack(side=tk.LEFT)
        body = tk.Frame(frame, bg=COLOR_BG_PANEL, padx=25, pady=20)
        body.pack(fill=tk.X)
        return body

    def _add_row(self, parent, label, widget_func, tooltip=None, label_width=22):
        row = tk.Frame(parent, bg=parent["bg"], pady=10)
        row.pack(fill=tk.X)
        lbl = tk.Label(row, text=label, font=FONT_SET_VAL, bg=parent["bg"], fg=COLOR_TEXT_SUB, width=label_width, anchor=tk.W)
        lbl.pack(side=tk.LEFT)
        if tooltip: ToolTip(lbl, tooltip)
        widget_func(row).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _create_cam_settings_card(self, parent, title, cam_key, crop_key):
        """カード枠＋ヘッダー（タイトル左・テスト右）＋本文先頭にプレビュー用 Canvas。本文 Frame を返す。"""
        frame = tk.Frame(parent, bg=COLOR_BG_PANEL, bd=1, relief=tk.SOLID, highlightbackground=COLOR_BORDER, highlightthickness=1)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        header = tk.Frame(frame, bg="#333333", padx=15, pady=8)
        header.pack(fill=tk.X)
        tk.Label(header, text=title, font=FONT_SET_LBL, bg="#333333", fg=COLOR_ACCENT).pack(side=tk.LEFT)
        tk.Button(
            header, text="OCRテスト", font=FONT_BOLD, bg="#455A64", fg="white",
            activebackground=COLOR_ACCENT_STRONG, padx=10,
            command=lambda ck=crop_key: self._test_ocr(ck),
        ).pack(side=tk.RIGHT)
        body = tk.Frame(frame, bg=COLOR_BG_PANEL, padx=25, pady=20)
        body.pack(fill=tk.BOTH, expand=True)
        cv = tk.Canvas(body, bg="black", highlightthickness=0, height=260, cursor="crosshair")
        cv.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.preview_canvases[cam_key] = cv
        cv.bind("<Button-1>", lambda e, ck=cam_key: self._on_preview_mouse_down(e, ck))
        cv.bind("<B1-Motion>", lambda e, ck=cam_key: self._on_preview_mouse_move(e, ck))
        cv.bind("<ButtonRelease-1>", lambda e, ck=cam_key: self._on_preview_mouse_up(e, ck))
        return body

    def _build_cam_tab(self):
        c = tk.Frame(self.tab_contents["t_cam"], bg=COLOR_BG_MAIN, padx=10, pady=10); c.pack(fill=tk.BOTH)
        
        # 共通：カメラ検索
        row_search = tk.Frame(c, bg=COLOR_BG_PANEL, pady=5); row_search.pack(fill=tk.X, pady=(0, 10))
        btn_search = tk.Button(row_search, text="接続カメラを検索", font=FONT_BOLD, bg="#455A64", fg="white", activebackground=COLOR_ACCENT_STRONG, padx=15, 
                               command=self._search_cameras)
        btn_search.pack(side=tk.LEFT)
        ToolTip(btn_search, "接続されているUSBカメラをスキャンしてインデックスを特定します。\n※カメラを繋ぎ変えた場合には再実行してください。")

        # 左右2カラムのコンテナ
        cols = tk.Frame(c, bg=COLOR_BG_MAIN); cols.pack(fill=tk.BOTH, expand=True)
        col_l = tk.Frame(cols, bg=COLOR_BG_MAIN); col_l.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        col_r = tk.Frame(cols, bg=COLOR_BG_MAIN); col_r.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))

        # --- 左カラム：正解カメラ設定 ---
        sl = self._create_cam_settings_card(col_l, "正解カメラ設定", "ref", "crop_ref_text")
        self._add_row(sl, "インデックス", lambda p: self._create_spinbox(p, "camera_ref_id", 0, 10), "OCRの基準画像を撮影するカメラID")
        
        def _build_focus_ref_row(p):
            f = tk.Frame(p, bg=p["bg"])
            self._create_focus_spinbox(f, "focus_ref").pack(side=tk.LEFT, fill=tk.X, expand=True)
            btn = tk.Button(f, text="自動調整", font=FONT_BOLD, bg="#37474F", fg="white", activebackground=COLOR_ACCENT_STRONG, padx=10,
                            command=lambda: self._start_af("focus_ref"))
            btn.pack(side=tk.RIGHT)
            self.af_btns["focus_ref"] = btn
            return f
        self._add_row(sl, "フォーカス", _build_focus_ref_row, "0〜1023を直接入力・±で調整、「自動調整」で最適化します", label_width=12)

        def _build_ocr_ref_row(p):
            f = tk.Frame(p, bg=p["bg"])
            tk.Button(
                f, text="キャンセル", font=FONT_BOLD, bg="#78909C", fg="white",
                activebackground=COLOR_ACCENT_STRONG, padx=10,
                command=lambda: self._cancel_roi("crop_ref_text"),
            ).pack(side=tk.RIGHT, padx=(8, 0))
            b = tk.Button(
                f, text="範囲確定", font=FONT_BOLD, bg="#37474F", fg="white",
                activebackground=COLOR_ACCENT_STRONG, padx=12,
                command=lambda: self._confirm_roi("crop_ref_text"),
            )
            b.pack(side=tk.RIGHT)
            self._confirm_btns["crop_ref_text"] = b
            return f
        self._add_row(sl, "検出エリア", _build_ocr_ref_row, "正解（基準）画像を読み取る範囲をプレビュー上でドラッグして指定します。カメラ中央付近を推奨します。", label_width=12)
        self._update_confirm_btn_state("crop_ref_text")

        # --- 右カラム：検査カメラ設定 ---
        sr = self._create_cam_settings_card(col_r, "検査カメラ設定", "insp", "crop_insp_text")
        self._add_row(sr, "インデックス", lambda p: self._create_spinbox(p, "camera_insp_id", 0, 10), "検査画像を撮影するカメラID")

        def _build_focus_insp_row(p):
            f = tk.Frame(p, bg=p["bg"])
            self._create_focus_spinbox(f, "focus_insp").pack(side=tk.LEFT, fill=tk.X, expand=True)
            btn = tk.Button(f, text="自動調整", font=FONT_BOLD, bg="#37474F", fg="white", activebackground=COLOR_ACCENT_STRONG, padx=10,
                            command=lambda: self._start_af("focus_insp"))
            btn.pack(side=tk.RIGHT)
            self.af_btns["focus_insp"] = btn
            return f
        self._add_row(sr, "フォーカス", _build_focus_insp_row, "0〜1023を直接入力・±で調整、「自動調整」で最適化します", label_width=12)

        def _build_ocr_insp_row(p):
            f = tk.Frame(p, bg=p["bg"])
            tk.Button(
                f, text="キャンセル", font=FONT_BOLD, bg="#78909C", fg="white",
                activebackground=COLOR_ACCENT_STRONG, padx=10,
                command=lambda: self._cancel_roi("crop_insp_text"),
            ).pack(side=tk.RIGHT, padx=(8, 0))
            b = tk.Button(
                f, text="範囲確定", font=FONT_BOLD, bg="#37474F", fg="white",
                activebackground=COLOR_ACCENT_STRONG, padx=12,
                command=lambda: self._confirm_roi("crop_insp_text"),
            )
            b.pack(side=tk.RIGHT)
            self._confirm_btns["crop_insp_text"] = b
            return f
        self._add_row(sr, "検出エリア", _build_ocr_insp_row, "検査画像を読み取る範囲を指定します。正解カメラの検出エリアと物理的に同じ位置を映すように調整してください。", label_width=12)
        self._update_confirm_btn_state("crop_insp_text")

        self.sw.after(80, self._preview_loop)

    def _build_gpio_tab(self):
        c = tk.Frame(self.tab_contents["t_gpio"], bg=COLOR_BG_MAIN, padx=20, pady=10); c.pack(fill=tk.BOTH)
        
        main_f = tk.Frame(c, bg=COLOR_BG_MAIN); main_f.pack(fill=tk.X)
        col_left = tk.Frame(main_f, bg=COLOR_BG_MAIN); col_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        col_right = tk.Frame(main_f, bg=COLOR_BG_MAIN); col_right.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)
        
        s1 = self._create_section(col_left, "GPIOピン割り当て")
        for k, l, name, h in [
            ("gpio_trigger_pin", "トリガー入力", "trigger", "外部信号(PLC等)を受け取るピン(BCM)です。センサー信号等を接続してください。"), 
            ("gpio_ok_pin", "OK出力", "ok", "判定OK時にパルス信号を出力するピン(BCM)です。"),
            ("gpio_ng_pin", "NG出力", "ng", "判定NG時にパルス信号を出力するピン(BCM)です。")
        ]:
            self._add_row(s1, l, lambda p, k=k, name=name: self._create_spinbox(p, k, 2, 27, name=name), h)

        s1b = self._create_section(col_left, "出力時間設定")
        self._add_row(s1b, "OK信号出力時間 (秒)", lambda p: self._create_hybrid(p, "ok_signal_duration", 0, 10.0, 0.1), "OK判定時に出力ピンをONにする時間です。0sにすると「ブザー停止」まで保持します。")
        self._add_row(s1b, "NG信号出力時間 (秒)", lambda p: self._create_hybrid(p, "ng_signal_duration", 0, 10.0, 0.1), "NG判定時に出力ピンをONにする時間です。0sにすると「ブザー停止」まで保持します。")
        
        s2 = self._create_section(col_right, "Pi 40Pin Map")
        self.show_gpio_map(s2)

    def _build_res_tab(self):
        c = tk.Frame(self.tab_contents["t_res"], bg=COLOR_BG_MAIN, padx=20, pady=10); c.pack(fill=tk.BOTH)
        
        s_a = self._create_section(c, "撮影設定")
        self._add_row(s_a, "撮影解像度", lambda p: self._create_combo(p, "capture_res", RES_OPTIONS), "カメラ本体から取得する映像の解像度です（高いほど高精度・高負荷）")
        
        s_b = self._create_section(c, "表示設定")
        self._add_row(s_b, "プレビュー解像度", lambda p: self._create_combo(p, "preview_res", RES_OPTIONS_PREVIEW), "画面表示用の解像度です")
        self._add_row(s_b, "プレビューFPS", lambda p: self._create_combo(p, "preview_fps", [1, 5, 10, 15, 30]), "画面の更新頻度です。低くすると負荷が下がります。")
        
        s_c = self._create_section(c, "保存設定")
        self._add_row(s_c, "OK保存画像解像度", lambda p: self._create_combo(p, "res_ok", RES_OPTIONS_SAVE), "OK判定時に保存される画像の解像度です")
        self._add_row(s_c, "NG保存画像解像度", lambda p: self._create_combo(p, "res_ng", RES_OPTIONS_SAVE), "NG判定時に保存される画像の解像度です")

    def _build_sys_tab(self):
        c = tk.Frame(self.tab_contents["t_sys"], bg=COLOR_BG_MAIN, padx=20, pady=10); c.pack(fill=tk.BOTH)
        s1 = self._create_section(c, "一般設定")
        self._add_row(s1, "OK後待機 (s)", lambda p: self._create_hybrid(p, "wait_after_ok", 0, 30, 0.5), "トリガー無効（自動）モード時、OK判定後に次の読取を開始するまでの待機時間です。連写による誤動作を防ぎます。")
        self._add_row(s1, "結果表示時間 (s)", lambda p: self._create_hybrid(p, "result_display_duration", 0, 30, 0.5), "メイン画面のステータス表示（OK/NG等）を維持する時間（秒）です。")
        self._add_row(s1, "OCR検出閾値", lambda p: self._create_hybrid(p, "ocr_threshold", 0.0, 1.0, 0.05), "AIが文字として認識する自信度のしきい値です。高くすると誤検知が減りますが読み落としが増えます。")
        self._add_row(s1, "最大リトライ回数", lambda p: self._create_spinbox(p, "max_retries", 1, 20), "読み取り失敗時に、自動で再試行を行う最大回数を設定します。")
        self._add_row(s1, "許可文字フィルタ", lambda p: self._create_entry(p, "allowed_chars"), "OCR読取結果のうち、ここで指定した文字以外を無視します。（例: ABC012）")

        s1b = self._create_section(c, "判定ロジック設定")
        def _build_match_mode(p):
            f = tk.Frame(p, bg=p["bg"])
            v = tk.StringVar(value=self.cm.get("match_mode", "partial"))
            self.vars["match_mode"] = v
            rb1 = tk.Radiobutton(f, text="部分一致 (正解文字が含まれていればOK)", variable=v, value="partial", font=FONT_SET_VAL, bg=p["bg"], fg="white", selectcolor="#333", activebackground=p["bg"], activeforeground="white", command=self._mark_changed)
            rb2 = tk.Radiobutton(f, text="完全一致 (正解文字と完全に一致すればOK)", variable=v, value="exact", font=FONT_SET_VAL, bg=p["bg"], fg="white", selectcolor="#333", activebackground=p["bg"], activeforeground="white", command=self._mark_changed)
            rb1.pack(anchor=tk.W, pady=2)
            rb2.pack(anchor=tk.W, pady=2)
            return f
        self._add_row(s1b, "テキスト照合方式", _build_match_mode, "読み取った検査文字が、正解文字とどのように一致すればOKとするかを設定します。")
        
        def _build_skip_patterns(p):
            f = tk.Frame(p, bg=p["bg"])
            entry_var = tk.StringVar()
            entry = tk.Entry(f, font=FONT_SET_VAL, bg=COLOR_BG_INPUT, fg="white", textvariable=entry_var, bd=1, relief=tk.SOLID, width=20)
            entry.pack(side=tk.LEFT, padx=(0, 5))
            
            listbox = tk.Listbox(f, font=FONT_SET_VAL, bg=COLOR_BG_INPUT, fg="white", bd=1, relief=tk.SOLID, height=3, width=20)
            listbox.pack(side=tk.LEFT, padx=(5, 5))
            
            patterns = self.cm.get("skip_patterns", [])
            for pat in patterns:
                listbox.insert(tk.END, pat)
            self.vars["skip_patterns_listbox"] = listbox
            
            btn_f = tk.Frame(f, bg=p["bg"])
            btn_f.pack(side=tk.LEFT)
            def _add():
                val = entry_var.get().strip()
                if val and val not in listbox.get(0, tk.END):
                    listbox.insert(tk.END, val)
                    entry_var.set("")
                    self._mark_changed()
            def _remove():
                idx = listbox.curselection()
                if idx:
                    listbox.delete(idx)
                    self._mark_changed()
            tk.Button(btn_f, text="追加", font=FONT_BOLD, bg="#455A64", fg="white", padx=10, command=_add).pack(fill=tk.X, pady=(0, 2))
            tk.Button(btn_f, text="削除", font=FONT_BOLD, bg=COLOR_NG, fg="white", padx=10, command=_remove).pack(fill=tk.X, pady=(2, 0))
            return f
        self._add_row(s1b, "スキップパターン", _build_skip_patterns, "正解カメラで読み取った文字がこのリストの文字を含む場合、検査をスキップしてトリガー待機に戻ります。")

        s2 = self._create_section(c, "表示オプション")
        row_sw = tk.Frame(s2, bg=COLOR_BG_PANEL, pady=10); row_sw.pack(fill=tk.X)
        sw_items = [
            ("flip_insp_h", "左右反転", "検査カメラの映像を左右に反転して表示します"), 
            ("flip_insp_v", "上下反転", "検査カメラの映像を上下に反転して表示します"), 
            ("mode_trigger", "トリガー有効", "外部入力（GPIO）を待ってから検査を開始します")
        ]
        for k, l, h in sw_items:
            f = tk.Frame(row_sw, bg=COLOR_BG_PANEL); f.pack(side=tk.LEFT, expand=True)
            lbl = tk.Label(f, text=l, font=FONT_NORMAL, bg=COLOR_BG_PANEL, fg=COLOR_TEXT_SUB)
            lbl.pack()
            ToolTip(lbl, h)
            var = tk.BooleanVar(value=self.cm.get(k, False)); self.vars[k] = var
            ToggleSwitch(f, var, command=self._mark_changed).pack(pady=5)

        s3 = self._create_section(c, "ストレージ設定")
        self._add_row(s3, "結果保存フォルダ", lambda p: self._create_path_row(p, "result_dir"), "検査結果の画像とログを保存するフォルダを選択します")
        self._add_row(s3, "画像保存上限 (GB)", lambda p: self._create_spinbox(p, "max_storage_gb", 1, 1000), "保存フォルダの合計サイズがこの値を超えると、古い画像から削除されます")

    def _create_focus_spinbox(self, parent, key):
        """フォーカス値用 Spinbox（スライダーなし・手動入力と±1刻み）。"""
        box = tk.Frame(parent, bg=parent["bg"])
        raw_val = self.cm.get(key, 0)
        try:
            f_val = int(round(float(raw_val))) if str(raw_val).strip() != "" else 0
        except:
            f_val = 0
        v = tk.IntVar(value=f_val)
        self.vars[key] = v
        sb = tk.Spinbox(
            box, from_=0, to=1023, increment=1, textvariable=v, width=8,
            font=FONT_SET_VAL, bg=COLOR_BG_INPUT, fg="white", buttonbackground="#78909C",
            bd=1, relief=tk.SOLID,
        )
        sb.pack(side=tk.LEFT)
        v.trace_add("write", lambda *args: self._mark_changed())

        def make_focus_handler(e=sb, vv=v):
            return lambda ev: setattr(self, "active_entry", (e, vv))

        sb.bind("<FocusIn>", make_focus_handler())
        return box

    def _create_spinbox(self, parent, key, f, t, i=1, name=None):
        raw_val = self.cm.get(key, 0)
        try:
            v_val = int(raw_val) if str(raw_val).strip() != "" else 0
        except:
            v_val = 0
        v = tk.IntVar(value=v_val)
        self.vars[key] = v
        box = tk.Frame(parent, bg=parent["bg"])
        sb = tk.Spinbox(box, from_=f, to=t, increment=i, textvariable=v, font=FONT_SET_VAL, bg=COLOR_BG_INPUT, fg="white", buttonbackground="#78909C", bd=1, relief=tk.SOLID, command=self._mark_changed)
        sb.pack(side=tk.LEFT)

        def make_focus_handler(e=sb, v=self.vars[key]):
            return lambda ev: setattr(self, "active_entry", (e, v))
        sb.bind("<FocusIn>", make_focus_handler())

        if name in ["ok", "ng", "trigger"] and self.gpio:
            if name != "trigger":
                tk.Button(box, text="テスト出力", font=FONT_BOLD, bg="#455A64", fg="white", padx=10,
                          command=lambda n=name: getattr(self.gpio, f"output_{n}")()).pack(side=tk.LEFT, padx=(10, 0))
            led = LEDIndicator(box, ""); led.pack(side=tk.LEFT, padx=(20, 0))
            self.leds[name] = led
        return box

    def _update_indicators(self):
        if not self.sw.winfo_exists(): return
        if not self.gpio: return
        states = self.gpio.get_states()
        for name, led in self.leds.items():
            if name in states:
                led.set_state(states[name])
        self.sw.after(100, self._update_indicators)

    def _create_hybrid(self, parent, key, min_v, max_v, res):
        raw_val = self.cm.get(key, 0)
        try:
            v_val = float(raw_val) if str(raw_val).strip() != "" else 0.0
        except:
            v_val = 0.0
        v = tk.DoubleVar(value=v_val); self.vars[key] = v
        return HybridSlider(parent, "", v, min_v, max_v, res, on_change=self._mark_changed)

    def _create_entry(self, parent, key):
        v = tk.StringVar(value=self.cm.get(key, "")); self.vars[key] = v
        e = tk.Entry(parent, font=FONT_SET_VAL, bg=COLOR_BG_INPUT, fg="white", insertbackground="white", textvariable=v, bd=1, relief=tk.SOLID)
        v.trace_add("write", lambda *args: self._mark_changed()); return e

    def _create_path_row(self, parent, key):
        from tkinter import filedialog
        v = tk.StringVar(value=self.cm.get(key, "")); self.vars[key] = v
        f = tk.Frame(parent, bg=parent["bg"])
        e = tk.Entry(f, font=FONT_SET_VAL, bg=COLOR_BG_INPUT, fg="white", insertbackground="white", textvariable=v, bd=1, relief=tk.SOLID)
        e.pack(side=tk.LEFT, fill=tk.X, expand=True)
        def _pick():
            p = filedialog.askdirectory(title="フォルダを選択", parent=self.sw)
            if p: v.set(p)
        tk.Button(f, text="参照", font=FONT_NORMAL, bg="#455A64", fg="white", command=_pick).pack(side=tk.LEFT, padx=(5, 0))
        v.trace_add("write", lambda *args: self._mark_changed()); return f

    def _mark_changed(self, *args):
        if not self.has_changes: self.has_changes = True; self.btn_save.config(bg=COLOR_OK, text="変更を適用して保存")

    def _start_af(self, k):
        cam_key = "ref" if "ref" in k else "insp"
        cam = self.cameras.get(cam_key)
        btn = self.af_btns.get(k)
        if cam and btn:
            btn.config(state=tk.DISABLED, text="調整中", bg="#444")
            roi = self.cm.get(f"crop_{cam_key}_text")
            
            def _on_finish(fv, s):
                self.vars[f"focus_{cam_key}"].set(int(round(fv)))
                if s == -1:
                    btn.config(state=tk.NORMAL, text="自動", bg="#37474F")
                    messagebox.showinfo("フォーカス最適化完了", "最適化しました")
                elif s == 0:
                    btn.config(state=tk.NORMAL, text="自動", bg="#37474F")
                    messagebox.showwarning("フォーカス最適化失敗", "ピントの山が見つかりませんでした。")
            
            cam.auto_optimize_focus(roi, _on_finish)

    def _crop_key_for_cam(self, cam_key):
        return "crop_ref_text" if cam_key == "ref" else "crop_insp_text"

    def _confirm_roi(self, crop_key):
        d = self._roi_draft.get(crop_key)
        if not d:
            messagebox.showinfo("範囲未指定", "先にプレビュー上でドラッグして範囲を指定してください。", parent=self.sw)
            return
        self.cm.set(crop_key, list(d))
        self._roi_draft[crop_key] = None
        self._update_confirm_btn_state(crop_key)
        self._mark_changed()

    def _cancel_roi(self, crop_key):
        self._roi_draft[crop_key] = None
        self._update_confirm_btn_state(crop_key)

    def _update_confirm_btn_state(self, crop_key):
        btn = self._confirm_btns.get(crop_key)
        if not btn:
            return
        has = self._roi_draft.get(crop_key) is not None
        btn.config(state=tk.NORMAL if has else tk.DISABLED)

    def _preview_cam_dims(self, cam):
        if cam is None:
            return 1280, 720
        try:
            w = int(cam.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cam.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if w > 0 and h > 0:
                return w, h
        except Exception:
            pass
        fr = cam.get_frame()
        if fr is not None:
            return fr.shape[1], fr.shape[0]
        return 1280, 720

    def _draw_preview_canvas(self, cam_key):
        cv = self.preview_canvases.get(cam_key)
        if not cv:
            return
        cw, ch = cv.winfo_width(), cv.winfo_height()
        if cw < 10 or ch < 10:
            return
        cam = self.cameras.get(cam_key) if self.cameras else None
        frame = cam.get_frame() if cam else None
        cam_w, cam_h = self._preview_cam_dims(cam)
        crop_key = self._crop_key_for_cam(cam_key)
        draft = self._roi_draft.get(crop_key)
        saved_roi = self.cm.get(crop_key)

        cv.delete("all")

        if frame is None:
            cv.create_text(cw // 2, ch // 2, text="カメラ映像なし", fill="#888888", font=(FONT_NORMAL[0], 12))
            self._preview_geom[cam_key] = {}
            return

        scale = min(cw / cam_w, ch / cam_h)
        disp_w = max(1, int(cam_w * scale))
        disp_h = max(1, int(cam_h * scale))
        offset_x = (cw - disp_w) / 2
        offset_y = (ch - disp_h) / 2
        self._preview_geom[cam_key] = {
            "scale": scale,
            "offset_x": offset_x,
            "offset_y": offset_y,
            "cam_w": cam_w,
            "cam_h": cam_h,
        }

        try:
            resized = cv2.resize(frame, (disp_w, disp_h))
        except Exception:
            return

        img_rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        pil = PIL.Image.fromarray(img_rgb)
        self._preview_photo[cam_key] = PIL.ImageTk.PhotoImage(pil)
        cv.create_image(offset_x, offset_y, image=self._preview_photo[cam_key], anchor=tk.NW)

        if saved_roi and len(saved_roi) >= 4:
            rx1, ry1, rx2, ry2 = saved_roi
            cx1 = offset_x + min(rx1, rx2) * disp_w
            cy1 = offset_y + min(ry1, ry2) * disp_h
            cx2 = offset_x + max(rx1, rx2) * disp_w
            cy2 = offset_y + max(ry1, ry2) * disp_h
            cv.create_rectangle(cx1, cy1, cx2, cy2, outline="#ff2222", width=2)

        dragging = self._drag_canvas and self._drag_canvas[0] == cam_key
        if dragging:
            _, dx1, dy1, dx2, dy2 = self._drag_canvas
            cv.create_rectangle(dx1, dy1, dx2, dy2, outline="#ffeb3b", width=2)
        elif draft is not None and len(draft) >= 4:
            rx1, ry1, rx2, ry2 = draft
            cx1 = offset_x + min(rx1, rx2) * disp_w
            cy1 = offset_y + min(ry1, ry2) * disp_h
            cx2 = offset_x + max(rx1, rx2) * disp_w
            cy2 = offset_y + max(ry1, ry2) * disp_h
            cv.create_rectangle(cx1, cy1, cx2, cy2, outline="#ffeb3b", width=2)

    def _preview_loop(self):
        try:
            if not self.sw.winfo_exists():
                return
        except tk.TclError:
            return
        if not self.preview_canvases:
            self.sw.after(100, self._preview_loop)
            return
        for ck in ("ref", "insp"):
            self._draw_preview_canvas(ck)
        self.sw.after(30, self._preview_loop)

    def _canvas_xy_to_cam(self, x, y, cam_key):
        g = self._preview_geom.get(cam_key) or {}
        if not g:
            return None, None
        sx = (x - g["offset_x"]) / g["scale"]
        sy = (y - g["offset_y"]) / g["scale"]
        cx = int(max(0, min(round(sx), g["cam_w"] - 1)))
        cy = int(max(0, min(round(sy), g["cam_h"] - 1)))
        return cx, cy

    def _on_preview_mouse_down(self, event, cam_key):
        self._drag_canvas = (cam_key, event.x, event.y, event.x, event.y)

    def _on_preview_mouse_move(self, event, cam_key):
        if not self._drag_canvas or self._drag_canvas[0] != cam_key:
            return
        ck, x0, y0, _, _ = self._drag_canvas
        self._drag_canvas = (ck, x0, y0, event.x, event.y)

    def _on_preview_mouse_up(self, event, cam_key):
        if not self._drag_canvas or self._drag_canvas[0] != cam_key:
            return
        _, x0, y0, x1, y1 = self._drag_canvas
        self._drag_canvas = None
        crop_key = self._crop_key_for_cam(cam_key)
        g = self._preview_geom.get(cam_key) or {}
        if not g:
            return
        # キャンバス座標 -> 相対比率 (0.0~1.0) へ変換
        def _to_ratio(cx, cy):
            rx = max(0.0, min(1.0, (cx - g["offset_x"]) / (g["cam_w"] * g["scale"])))
            ry = max(0.0, min(1.0, (cy - g["offset_y"]) / (g["cam_h"] * g["scale"])))
            return rx, ry
        rx0, ry0 = _to_ratio(x0, y0)
        rx1, ry1 = _to_ratio(x1, y1)
        # 最小サイズ検証: 相対比率 1% 未満は無視
        if abs(rx1 - rx0) < 0.01 or abs(ry1 - ry0) < 0.01:
            return
        self._roi_draft[crop_key] = [
            min(rx0, rx1), min(ry0, ry1),
            max(rx0, rx1), max(ry0, ry1)
        ]
        self._update_confirm_btn_state(crop_key)

    def _test_ocr(self, k):
        cam_key = "ref" if "ref" in k else "insp"
        cam = self.cameras.get(cam_key)
        if not cam: return
        roi = self._roi_draft.get(k)
        if roi is None:
            roi = self.cm.get(k)
        if not roi or len(roi) < 4:
            messagebox.showerror("Error", "検出エリアがありません。プレビュー上でドラッグして「範囲確定」してください。", parent=self.sw)
            return
        frame = cam.get_frame()
        if frame is None:
            messagebox.showerror("Error", "カメラから画像を取得できません。")
            return
        # 相対比率をピクセル座標に変換
        h, w = frame.shape[:2]
        rx1, ry1, rx2, ry2 = roi
        xs = int(min(rx1, rx2) * w)
        ys = int(min(ry1, ry2) * h)
        xe = int(max(rx1, rx2) * w)
        ye = int(max(ry1, ry2) * h)
        xs, ys = max(0, xs), max(0, ys)
        xe, ye = min(w, xe), min(h, ye)
        
        crop = frame[ys:ye, xs:xe]
        if crop.size == 0:
            messagebox.showerror("Error", "無効なROIです。")
            return
        try:
            import re
            
            # メインアプリのエンジンを流用 (§Review対応)
            ocr_engine = None
            if self.parent_app and hasattr(self.parent_app, "inspector"):
                ocr_engine = self.parent_app.inspector.ocr
            
            if ocr_engine:
                res, _ = ocr_engine(crop)
            else:
                # 予備: スタンドアロン起動時などのフォールバック
                from rapidocr_onnxruntime import RapidOCR
                _temp_ocr = RapidOCR()
                res, _ = _temp_ocr(crop)

            if res:
                allowed_var = self.vars.get("allowed_chars")
                allowed = allowed_var.get() if allowed_var else self.cm.get("allowed_chars", "")
                
                texts = []
                for t in res:
                    text_str, score = t[1], t[2]
                    if allowed:
                        text_str = "".join([c for c in text_str if c in allowed])
                    if text_str:
                        texts.append(f"'{text_str}' (スコア: {score:.2f})")
                        
                if texts:
                    messagebox.showinfo("検出テスト成功", "検出結果:\n" + "\n".join(texts), parent=self.sw)
                else:
                    messagebox.showinfo("検出テスト完了", "フィルタ適用後、結果として残る文字がありませんでした。", parent=self.sw)
            else:
                messagebox.showinfo("検出テスト完了", "文字が検出されませんでした。", parent=self.sw)
        except Exception as e:
            messagebox.showerror("OCRエラー", str(e))

    def _check_gpio_status(self):
        """Deprecated: using _update_indicators for all LEDs including trigger"""
        pass

    def show_settings_help(self):
        help_data = {
            "1. カメラ設定": "【概要】使用するUSBカメラの接続とフォーカス調整、検出エリアの設定を行います。\n"
                           "・正解/検査カメラインデックス: カメラの認識番号を指定します。\n"
                           "・各カード内のプレビューに正解・検査それぞれのカメラ映像が表示されます。\n"
                           "・OCRテスト: OCRテストボタンを押すとOCRテストを行います。\n"
                           "・フォーカス調整: 自動調整ボタンを押すとピントを最適化します。\n"
                           "・検出エリア: 赤枠は保存済み範囲、黄枠は編集中の範囲。「範囲確定」で黄枠を保存し、「キャンセル」で編集を破棄します。",
            "2. GPIOピン設定": "【概要】Raspberry PiのGPIOピンへの配線設定です。\n"
                             "・トリガー: 検査を起動する入力ピンです。\n"
                             "・出力(OK/NG): 判定結果を外部装置へ送るピンです。\n"
                             "・Pi 40Pin Map: ピン名をクリックすると選択中の入力欄へ値がコピーされます。\n"
                             "・テスト出力: テスト出力ボタンを押すとテスト出力を行います。",
            "3. 画素数設定": "【概要】カメラからの取得画像の解像度を決定します。\n"
                         "・解像度を上げると精度向上の可能性がありますが、処理が重くなります。\n"
                         "・プレビューなし: プレビューを表示しません。\n"
                         "・保存しない: 検査結果を保存しません。\n"
                         "・プレビューFPS: 画面の更新頻度です。低くするとシステム負荷が下がります。",
            "4. 判定ロジック設定": "【概要】検査文字と正解文字の照合方法を設定します。\n"
                              "・テキスト照合方式: 部分一致（含まれていればOK）か、完全一致（完全に同じならOK）かを選択します。\n"
                              "・スキップパターン: 正解カメラで読み取った文字がこのリストの文字を含む場合、検査をスキップ（SKIP）して次のトリガー入力を待機します。",
            "5. システム最適化": "【概要】AIの挙動や出力の微調整です。\n"
                             "・OK後待機: トリガー無効時、OKと判定された後、次の検査を開始するまでの待機時間（秒）です。\n"
                             "・結果表示時間: 判定結果（OK/NG）のステータス表示を維持する時間です。\n"
                             "・OCR検出閾値: 検出した文字の信頼度がこの数値以上なら採用します。\n"
                             "・最大リトライ回数: 検査がNGの場合に再検査を行う最大回数です。\n"
                             "・許可文字フィルタ: (例) 0123456789ABCDEF と設定すると、それ以外の文字を結果から除外します。\n"
                             "・左右反転: 検査カメラの映像を左右に反転して表示します。\n"
                             "・上下反転: 検査カメラの映像を上下に反転して表示します。\n"
                             "・トリガー有効: 外部入力（GPIO）を待ってから検査を開始します。\n"
                             "・ストレージ容量: 検査結果を保存するディレクトリと最大容量を設定します。",

        }
        HelpWindow(self.sw, "詳細設定 操作ガイド", help_data)

    def _create_combo(self, parent, key, options):
        current_val = self.cm.get(key, options[0])
        disp_opts = [RES_MAP.get(opt, opt) for opt in options]
        current_disp = RES_MAP.get(current_val, current_val)
        
        if current_disp not in disp_opts:
            disp_opts.append(current_disp)
            
        self.vars[f"{key}_str"] = tk.StringVar(value=current_disp)
        self.vars[key] = tk.StringVar(value=current_val)
        
        def _on_change(*args):
            disp = self.vars[f"{key}_str"].get()
            for k_map, v_map in RES_MAP.items():
                if v_map == disp:
                    self.vars[key].set(k_map)
                    break
            self._update_resolution_constraints()
            self._mark_changed()
            
        self.vars[f"{key}_str"].trace_add("write", _on_change)
        
        cb = ttk.Combobox(parent, textvariable=self.vars[f"{key}_str"], values=disp_opts, state="readonly", font=FONT_SET_VAL, width=28)
        self.vars[f"{key}_cb"] = cb
        return cb

    def _update_resolution_constraints(self):
        """撮影解像度を超えないようにフィルタリングする（拡張用）"""
        pass

    def show_gpio_map(self, parent):
        f = tk.Frame(parent, bg=COLOR_BG_PANEL)
        f.pack(fill=tk.X, pady=10, padx=5)
        
        pins = [
            (1, "3.3V", None),   (2, "5V", None),
            (3, "GPIO 2", 2),    (4, "5V", None),
            (5, "GPIO 3", 3),    (6, "GND", None),
            (7, "GPIO 4", 4),    (8, "GPIO 14", 14),
            (9, "GND", None),    (10, "GPIO 15", 15),
            (11, "GPIO 17", 17), (12, "GPIO 18", 18),
            (13, "GPIO 27", 27), (14, "GND", None),
            (15, "GPIO 22", 22), (16, "GPIO 23", 23),
            (17, "3.3V", None),  (18, "GPIO 24", 24),
            (19, "GPIO 10", 10), (20, "GND", None),
            (21, "GPIO 9", 9),   (22, "GPIO 25", 25),
            (23, "GPIO 11", 11), (24, "GPIO 8", 8),
            (25, "GND", None),   (26, "GPIO 7", 7),
            (27, "ID_SD", None), (28, "ID_SC", None),
            (29, "GPIO 5", 5),   (30, "GND", None),
            (31, "GPIO 6", 6),   (32, "GPIO 12", 12),
            (33, "GPIO 13", 13), (34, "GND", None),
            (35, "GPIO 19", 19), (36, "GPIO 16", 16),
            (37, "GPIO 26", 26), (38, "GPIO 20", 20),
            (39, "GND", None),   (40, "GPIO 21", 21)
        ]
        
        def _on_pin_clicked(bcm_val):
            if hasattr(self, "active_entry") and self.active_entry:
                widget, var = self.active_entry
                if var and bcm_val is not None:
                    var.set(bcm_val)
                    widget.focus_set()
                    self._mark_changed()

        for i, (pno, name, bcm) in enumerate(pins):
            col_idx = 0 if i % 2 == 0 else 2
            row_idx = i // 2
            lbl_no = tk.Label(f, text=str(pno), font=(FONT_NORMAL[0], 10, "bold"), width=3, bg="#222", fg="white")
            lbl_color = "#444"
            if "V" in name: lbl_color = "#8D6E63"
            if "GND" in name: lbl_color = "#212121"
            lbl_name = tk.Label(f, text=name, font=(FONT_NORMAL[0], 10), width=12, bg=lbl_color, fg=COLOR_TEXT_MAIN, padx=5, pady=3, relief="flat")

            if i % 2 == 0:
                lbl_no.grid(row=row_idx, column=0, padx=2, pady=1)
                lbl_name.grid(row=row_idx, column=1, padx=(2, 10), pady=1, sticky="w")
            else:
                lbl_name.grid(row=row_idx, column=2, padx=(10, 2), pady=1, sticky="e")
                lbl_no.grid(row=row_idx, column=3, padx=2, pady=1)

            if bcm is not None:
                def make_handler(b=bcm): return lambda e: _on_pin_clicked(b)
                lbl_no.bind("<Button-1>", make_handler())
                lbl_name.bind("<Button-1>", make_handler())
                lbl_no.config(cursor="hand2")
                lbl_name.config(cursor="hand2")

    def _search_cameras(self):
        self.sw.config(cursor="wait")
        self.sw.update()
        import cv2
        available = []
        
        # 既に現在取得成功しているカメラ（gui_app側で掴んでいるもの）は先にリストに追加し、DSHOWエラーを回避する
        working_indices = []
        if getattr(self, "cameras", None):
            for cam_key in ["ref", "insp"]:
                cam = self.cameras.get(cam_key)
                if cam is not None and getattr(cam, "is_opened", lambda: True)():
                    try:
                        idx = int(self.cm.get(f"camera_{cam_key}_id", -1))
                        if idx >= 0 and idx not in working_indices: 
                            working_indices.append(idx)
                    except: pass
                    
        for i in range(10):
            if i in working_indices:
                available.append(str(i))
                continue
                
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW) if IS_WINDOWS else cv2.VideoCapture(i)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret: available.append(str(i))
                cap.release()
                
        self.sw.config(cursor="")
        if available:
            msg = f"検出されたカメラインデックス: {', '.join(available)}\n\n入力欄に自動反映しますか？\n(※既存の設定は上書きされます)"
            if messagebox.askyesno("カメラ検索結果", msg, parent=self.sw):
                if len(available) >= 1: self.vars["camera_ref_id"].set(int(available[0]))
                if len(available) >= 2: self.vars["camera_insp_id"].set(int(available[1]))
                self._mark_changed()
        else:
            messagebox.showwarning("検索結果", "カメラが見つかりませんでした。", parent=self.sw)

    def _on_close(self):
        """閉じる際（保存・キャンセル・右上の×）の共通処理: メインアプリを再開"""
        if self.parent_app:
            self.parent_app.is_paused = False
        self.sw.destroy()

    def _save(self):
        try:
            # 内部での設定値参照をすべて get() 経由に統一 (§Review対応)
            save_dict = {}
            for k, v in self.vars.items():
                if "_label" in k or str(k).endswith("_str") or str(k).endswith("_cb") or k == "skip_patterns_listbox":
                    continue
                val = v.get()
                if isinstance(val, str) and "[" in val:
                    try: save_dict[k] = json.loads(val)
                    except: save_dict[k] = val
                else:
                    save_dict[k] = val
            
            if "skip_patterns_listbox" in self.vars:
                lb = self.vars["skip_patterns_listbox"]
                save_dict["skip_patterns"] = list(lb.get(0, tk.END))
                
            # インデックス重複チェック
            if save_dict.get("camera_ref_id") == save_dict.get("camera_insp_id"):
                if not messagebox.askyesno("警告", "正解カメラと検査カメラのインデックスが同じです。\nこのまま保存しますか？", parent=self.sw):
                    return
            
            # --- GPIOピン重複チェック (§137) ---
            p_trig = save_dict.get("gpio_trigger_pin")
            p_ok = save_dict.get("gpio_ok_pin")
            p_ng = save_dict.get("gpio_ng_pin")
            # 有効なBCMピン(2-27)以外は除外(Spinboxで制限しているが念の為)
            active_pins = [p for p in [p_trig, p_ok, p_ng] if p is not None and 2 <= p <= 27]
            if len(active_pins) != len(set(active_pins)):
                messagebox.showerror("バリデーションエラー", "同じGPIOピンを複数の機能に割り当てることはできません。", parent=self.sw)
                return
            
            # 互換性: capture_resから width/height を抽出して設定
            res_val = save_dict.get("capture_res")
            if res_val and "x" in res_val:
                try:
                    w, h = res_val.split("x")
                    save_dict["resolution_width"] = int(w)
                    save_dict["resolution_height"] = int(h)
                except: pass
                
            self.cm.save_config(save_dict)
            if self.on_save: self.on_save()
            self._on_close()
        except Exception as e: messagebox.showerror("Error", str(e), parent=self.sw)
