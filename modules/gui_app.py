import logging
import tkinter as tk
from tkinter import messagebox, ttk
import cv2
import PIL.Image, PIL.ImageTk
import threading
import time
from datetime import datetime
from .constants import *
from .camera_manager import CameraStream
from .gpio_handler import GPIOHandler
from .inspector import Inspector
from .widgets import ToolTip, HelpWindow
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)

class GUIApp:
    def __init__(self, root, config_manager):
        self.root = root
        self.root.app_instance = self
        self.cm = config_manager
        logger.info("Initializing Inspector and GPIOHandler...")
        self.inspector = Inspector(config_manager)
        self.gpio = GPIOHandler(config_manager)
        
        self.cam_ref: Optional[CameraStream] = None
        self.cam_insp: Optional[CameraStream] = None
        self.is_running = True
        self.is_paused = False
        
        # UI Elements initialization (for type linting)
        self.header: Optional[tk.Frame] = None
        self.header_right: Optional[tk.Frame] = None
        self.lbl_status: Optional[tk.Label] = None
        self.lbl_clock: Optional[tk.Label] = None
        self.mock_root: Optional[tk.Toplevel] = None
        self.mock_indicators: Dict = {}
        self.lbl_pattern: Optional[tk.Label] = None 
        self.btn_help: Optional[tk.Button] = None
        
        self.ng_history: List[Tuple[str, str]] = [] # [(message, image_path), ...]
        self.canvas_images: Dict[int, tk.Canvas] = {} # canvas_id -> image_id
        self.tk_images: Dict[int, PIL.ImageTk.PhotoImage] = {} # canvas_id -> current_image
        
        self._init_cameras()
        self._setup_ui()
        if self.gpio.is_mock:
            self.root.after(500, self._setup_mock_ui)
        
        # プレビュー更新
        self._update_preview()
        # 検査ループ開始
        logger.info("Starting inspection loop thread...")
        threading.Thread(target=self._inspection_loop, daemon=True).start()
        # 時計更新
        self._update_clock()

    def _init_cameras(self):
        res_str = self.cm.get("capture_res", "1920x1080")
        try:
            w, h = map(int, res_str.split('x'))
        except Exception as e:
            logger.warning(f"Invalid capture_res format '{res_str}': {e}. Using default 1920x1080.")
            w, h = 1920, 1080
            
        logger.info(f"Initializing cameras with resolution {w}x{h}...")
        self.cam_ref = CameraStream(self.cm.get("camera_ref_id"), w, h, self.cm.get("focus_ref"))
        self.cam_insp = CameraStream(self.cm.get("camera_insp_id"), w, h, self.cm.get("focus_insp"))
        
        # 接続確認 (§Review提案)
        if not self.cam_ref.is_opened():
            logger.error("Failed to open Reference Camera (index: %s)", self.cm.get("camera_ref_id"))
            messagebox.showwarning("カメラ警告", f"正解カメラ（ID:{self.cm.get('camera_ref_id')}）の起動に失敗しました。\n設定を確認してください。")
            
        if not self.cam_insp.is_opened():
            logger.error("Failed to open Inspection Camera (index: %s)", self.cm.get("camera_insp_id"))
            messagebox.showwarning("カメラ警告", f"検査カメラ（ID:{self.cm.get('camera_insp_id')}）の起動に失敗しました。\n設定を確認してください。")

    def _setup_ui(self):
        self.root.title("OCR 照合システム")
        self.root.geometry("1400x900")
        self.root.configure(bg=COLOR_BG_MAIN)
        
        # 全画面表示設定
        if IS_WINDOWS:
            self.root.state("zoomed")
        else:
            try: self.root.attributes('-zoomed', True)
            except: pass

        # --- ヘッダー (高さ 80px) ---
        self.header = tk.Frame(self.root, bg=COLOR_BG_PANEL, height=80)
        self.header.pack(fill=tk.X, side=tk.TOP)
        self.header.pack_propagate(False)

        self.lbl_status = tk.Label(self.header, text="システム待機中", font=FONT_LARGE, bg=COLOR_BG_PANEL, fg=COLOR_ACCENT)
        self.lbl_status.pack(side=tk.LEFT, padx=30, pady=15)

        # 時計
        self.lbl_clock = tk.Label(self.header, text="", font=FONT_LARGE, bg=COLOR_BG_PANEL, fg=COLOR_TEXT_MAIN)
        self.lbl_clock.pack(side=tk.RIGHT, padx=30)

        # バージョン表示 (規約 §10-352)
        ver_lbl = tk.Label(self.header, text=f"v{VERSION} ({BUILD_DATE})", font=(FONT_FAMILY, 10), 
                           bg=COLOR_BG_PANEL, fg=COLOR_TEXT_SUB)
        ver_lbl.pack(side=tk.RIGHT, padx=5)

        # ヘルプボタン
        self.btn_help = tk.Button(self.header, text="？", font=FONT_BOLD, bg=COLOR_BG_INPUT, fg=COLOR_ACCENT, 
                                  relief=tk.FLAT, width=3, command=self._show_help)
        self.btn_help.pack(side=tk.RIGHT, padx=10)

        # --- メインコンテンツエリア ---
        main_container = tk.Frame(self.root, bg=COLOR_BG_MAIN)
        main_container.pack(fill=tk.BOTH, expand=True)

        # 操作パネル (右側, 固定幅 420px)
        side_panel = tk.Frame(main_container, bg=COLOR_BG_PANEL, width=420)
        side_panel.pack(side=tk.RIGHT, fill=tk.Y)
        side_panel.pack_propagate(False)

        self._build_side_panel(side_panel)

        # カメラプレビューエリア (左側, expand)
        preview_container = tk.Frame(main_container, bg=COLOR_BG_MAIN)
        preview_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=20, pady=20)

        self.canvas_ref = self._create_camera_frame(preview_container, "【正解カメラ】", 0, 0)
        self.canvas_insp = self._create_camera_frame(preview_container, "【検査カメラ】", 0, 1)
        preview_container.grid_columnconfigure(0, weight=1)
        preview_container.grid_columnconfigure(1, weight=1)
        preview_container.grid_rowconfigure(0, weight=1)

    def _create_camera_frame(self, parent, title, r, c):
        f = tk.LabelFrame(parent, text=title, font=FONT_BOLD, bg=COLOR_BG_PANEL, fg=COLOR_TEXT_MAIN, labelanchor="nw")
        f.grid(row=r, column=c, sticky="nsew", padx=10, pady=10)
        canvas = tk.Canvas(f, bg="black", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        return canvas

    def _setup_mock_ui(self):
        """モックモード時の仮想GPIO操作パネル (Windowsデバッグ用)"""
        try:
            self.mock_root = tk.Toplevel(self.root)
            self.mock_root.title("仮想GPIOパネル")
            self.mock_root.geometry("300x350")
            self.mock_root.configure(bg=COLOR_BG_MAIN)
            self.mock_root.attributes("-topmost", True)
            self.mock_root.resizable(False, False)

            container = tk.Frame(self.mock_root, bg=COLOR_BG_MAIN, padx=20, pady=20)
            container.pack(fill=tk.BOTH, expand=True)

            # --- 入力 (トリガー) ---
            f_trig = tk.LabelFrame(container, text="仮想入力", bg=COLOR_BG_PANEL, fg=COLOR_TEXT_MAIN, font=FONT_NORMAL)
            f_trig.pack(fill=tk.X, pady=(0, 15))

            btn = tk.Button(f_trig, text=f"トリガー入力 (Pin {self.cm.get('gpio_trigger_pin')})",
                            font=FONT_NORMAL, bg=COLOR_BG_INPUT, fg=COLOR_TEXT_MAIN,
                            activebackground=COLOR_ACCENT, activeforeground="black",
                            relief="flat", cursor="hand2",
                            command=self.gpio.mock_trigger)
            btn.pack(fill=tk.X, padx=10, pady=10)

            # --- 出力 (ステータス) ---
            f_out = tk.LabelFrame(container, text="仮想出力", bg=COLOR_BG_PANEL, fg=COLOR_TEXT_MAIN, font=FONT_NORMAL)
            f_out.pack(fill=tk.X)

            self.mock_indicators = {}
            for name, pin_key, color in [("OK出力", "ok", COLOR_OK), ("NG出力", "ng", COLOR_NG)]:
                f = tk.Frame(f_out, bg=COLOR_BG_PANEL)
                f.pack(fill=tk.X, pady=8, padx=10)
                
                lbl = tk.Label(f, text=name, font=FONT_NORMAL, bg=COLOR_BG_PANEL, fg=COLOR_TEXT_MAIN, width=12, anchor="w")
                lbl.pack(side=tk.LEFT)
                
                outer_ind = tk.Frame(f, width=24, height=24, bg=COLOR_BG_INPUT, padx=2, pady=2)
                outer_ind.pack(side=tk.RIGHT)
                outer_ind.pack_propagate(False)

                ind = tk.Frame(outer_ind, bg="#444")
                ind.pack(fill=tk.BOTH, expand=True)
                self.mock_indicators[pin_key] = (ind, color)

            self._update_mock_ui()
        except Exception as e:
            print(f"仮想GPIOパネル初期化エラー: {e}")

    def _update_mock_ui(self):
        """出力状態を周期的に確認してUIを更新"""
        try:
            if getattr(self, "mock_indicators", None) is None or not self.mock_root.winfo_exists():
                return
            
            for pin_key, ind_data in self.mock_indicators.items():
                ind, color = ind_data
                state = self.gpio.get_pin_status(pin_key)
                ind.configure(bg=color if state else "#444")
            
            self.mock_root.after(200, self._update_mock_ui)
        except Exception:
            pass

    def _build_side_panel(self, parent):
        p = tk.Frame(parent, bg=COLOR_BG_PANEL, padx=15, pady=15)
        p.pack(fill=tk.BOTH, expand=True)

        # 1. 運用ステータス (ダッシュボード風)
        status_f = tk.LabelFrame(p, text=" 稼働ステータス ", font=FONT_BOLD, bg=COLOR_BG_PANEL, fg=COLOR_ACCENT, padx=10, pady=10)
        status_f.pack(fill=tk.X, pady=(0, 15))
        
        # 状態表示行
        self.lbl_mode = tk.Label(status_f, text="● 待機中", font=FONT_BOLD, bg=COLOR_BG_PANEL, fg=COLOR_TEXT_SUB, anchor="w")
        self.lbl_mode.pack(fill=tk.X)
        
        # CPU/FPS メーター (簡易表示)
        self.lbl_perf = tk.Label(status_f, text="FPS: -- | CPU: --", font=(FONT_FAMILY, 10), bg=COLOR_BG_PANEL, fg=COLOR_TEXT_SUB, anchor="w")
        self.lbl_perf.pack(fill=tk.X, pady=(5, 0))
        
        # GPIO インジケータ
        gpio_f = tk.Frame(status_f, bg=COLOR_BG_PANEL)
        gpio_f.pack(fill=tk.X, pady=(5, 0))
        self.led_gpio = tk.Canvas(gpio_f, width=12, height=12, bg=COLOR_BG_PANEL, highlightthickness=0)
        self.led_gpio.pack(side=tk.LEFT)
        self.led_gpio_circ = self.led_gpio.create_oval(2, 2, 10, 10, fill=COLOR_OK if not self.gpio.is_mock else COLOR_WARNING)
        tk.Label(gpio_f, text="GPIO 接続中" if not self.gpio.is_mock else "GPIO モック動作中", font=(FONT_FAMILY, 10), bg=COLOR_BG_PANEL, fg=COLOR_TEXT_SUB).pack(side=tk.LEFT, padx=5)

        # 2. 照合文字表示 (カード)
        pat_f = tk.LabelFrame(p, text=" 照合基準文字 ", font=FONT_BOLD, bg=COLOR_BG_PANEL, fg=COLOR_ACCENT, padx=10, pady=10)
        pat_f.pack(fill=tk.X, pady=(0, 15))
        self.lbl_pattern = tk.Label(pat_f, text="---", font=FONT_HUGE, bg=COLOR_BG_INPUT, fg=COLOR_ACCENT_STRONG, pady=10)
        self.lbl_pattern.pack(fill=tk.X)

        # 3. NG履歴リスト (スクロール付きカード)
        hist_f = tk.LabelFrame(p, text=" 不一致(NG)履歴 ", font=FONT_BOLD, bg=COLOR_BG_PANEL, fg=COLOR_ACCENT, padx=10, pady=10)
        hist_f.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        history_inner = tk.Frame(hist_f, bg=COLOR_BG_PANEL)
        history_inner.pack(fill=tk.BOTH, expand=True)
        
        self.lst_history = tk.Listbox(history_inner, font=FONT_NORMAL, bg=COLOR_BG_INPUT, fg="white", bd=0, highlightthickness=0, selectbackground=COLOR_ACCENT)
        self.lst_history.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(history_inner, orient="vertical", command=self.lst_history.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.lst_history.config(yscrollcommand=sb.set)
        self.lst_history.bind("<Double-Button-1>", self._on_history_click)

        # 4. 操作ボタン (機能別にセクション化)
        btn_container = tk.Frame(p, bg=COLOR_BG_PANEL)
        btn_container.pack(fill=tk.X, side=tk.BOTTOM)

        # 【運用・緊急】
        tk.Label(btn_container, text="運用操作", font=(FONT_FAMILY, 11, "bold"), bg=COLOR_BG_PANEL, fg=COLOR_TEXT_SUB).pack(anchor="w", pady=(0, 5))
        btn_buzzer_stop = tk.Button(btn_container, text="アラーム・ブザー停止", font=FONT_BOLD, bg=COLOR_NG, fg="white", relief=tk.FLAT, height=2, command=self._stop_buzzer)
        btn_buzzer_stop.pack(fill=tk.X, pady=(0, 15))
        ToolTip(btn_buzzer_stop, "OK/NG信号およびブザー出力を強制停止します")

        # 【メンテナンス】
        tk.Label(btn_container, text="管理・設定", font=(FONT_FAMILY, 11, "bold"), bg=COLOR_BG_PANEL, fg=COLOR_TEXT_SUB).pack(anchor="w", pady=(0, 5))
        maint_f = tk.Frame(btn_container, bg=COLOR_BG_PANEL)
        maint_f.pack(fill=tk.X)
        maint_f.columnconfigure(0, weight=1)
        maint_f.columnconfigure(1, weight=1)

        btn_history_reset = tk.Button(maint_f, text="履歴クリア", font=FONT_BOLD, bg="#546E7A", fg="white", relief=tk.FLAT, height=2, command=self._reset_history)
        btn_history_reset.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        ToolTip(btn_history_reset, "NG履歴リストを全て消去します")

        btn_settings = tk.Button(maint_f, text="詳細設定", font=FONT_BOLD, bg="#455A64", fg="white", relief=tk.FLAT, height=2, command=self._open_settings)
        btn_settings.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        ToolTip(btn_settings, "カメラ設定やIO割り当てなどの詳細画面を開きます")

    def _update_clock(self):
        if self.is_running:
            now = datetime.now()
            self.lbl_clock.config(text=now.strftime("%Y/%m/%d %H:%M:%S"))
            
            # FPS計算とパフォーマンス表示
            try:
                import psutil
                cpu = psutil.cpu_percent()
                self.lbl_perf.config(text=f"CPU: {cpu}% | RAM: {psutil.virtual_memory().percent}%")
            except:
                pass
            
            self.root.after(1000, self._update_clock)

    def _show_help(self):
        help_data = {
            "1. 基本的な使い方": (
                "【概要】検査システムの基本操作です。\n"
                "1. 設定画面から「正解カメラ」と「検査カメラ」を適切に設定します。\n"
                "2. 正解カメラの下に検査の基準となる対象物を置き、文字を読み取らせます。\n"
                "3. 検査エリアに対象物が来ると、検査カメラが文字を読み取り、正解文字と比較します。"
            ).replace("\n ", "\n"),
            "2. 判定ロジック（部分/完全一致）": (
                "【概要】文字の照合方法についてです。\n"
                "・部分一致: 検査カメラで読み取った文字の中に、正解文字が「含まれていれば」OKと判定します。\n"
                "・完全一致: 正解文字と検査文字が「完全に一致」した場合のみOKと判定します。\n"
                "※設定画面の「判定ロジック設定」から切り替え可能です。"
            ).replace("\n ", "\n"),
            "3. スキップパターン機能": (
                "【概要】特定の文字を読み取った際に検査をスキップする機能です。\n"
                "・正解カメラが「スキップパターン」に登録された文字を読み取ると、その回の検査をスキップし、次のトリガー入力を待ちます。\n"
                "・治具や空パレットなど、検査不要な流動物の識別に利用します。"
            ).replace("\n ", "\n"),
            "4. トリガーモード": (
                "【概要】検査の開始タイミングの設定です。\n"
                "・トリガー有効: PLC等の外部機器からの信号を受けて検査を開始します。\n"
                "・トリガー無効: 外部信号を待たず、カメラの映像から連続して判定を行います。\n"
                "※設定画面の「システム」タブから切り替えできます。"
            ).replace("\n ", "\n"),
            "5. 詳細設定の開き方": (
                "【概要】各種設定を行う画面の開き方です。\n"
                "・メイン画面右下の「詳細設定」ボタンをクリックして開きます。\n"
                "・カメラの切り替え、閾値の変更、保存先フォルダの指定などが行えます。"
            ).replace("\n ", "\n"),
            "6. NG履歴の確認": (
                "【概要】過去のNG判定の記録です。\n"
                "・メイン画面右側のリストに、最新のNG履歴が表示されます。\n"
                "・「履歴リセット」ボタンでリストをクリアできます。"
            ).replace("\n ", "\n")
        }
        HelpWindow(self.root, "OCR 照合システム 操作ガイド", help_data)
    def _reset_history(self):
        if messagebox.askyesno("確認", "履歴をリセットしますか？"):
            self.lst_history.delete(0, tk.END)
            self.ng_history.clear()

    def _stop_buzzer(self):
        """ブザー（NG信号・OK信号）を停止"""
        self.gpio.stop_outputs()

    def _on_history_click(self, event):
        idx_tuple = self.lst_history.curselection()
        if not idx_tuple: return
        idx = idx_tuple[0]
        if idx < len(self.ng_history):
            msg, img_path = self.ng_history[idx]
            if img_path and os.path.exists(img_path):
                self._show_ng_image(msg, img_path)
            else:
                messagebox.showinfo("情報", "該当する画像ファイルが見つかりません。")

    def _show_ng_image(self, title, path):
        win = tk.Toplevel(self.root)
        win.title(f"NG詳細: {os.path.basename(path)}")
        win.geometry("800x650")
        win.configure(bg=COLOR_BG_MAIN)
        win.transient(self.root)
        
        lbl_info = tk.Label(win, text=title, font=FONT_BOLD, bg=COLOR_BG_MAIN, fg=COLOR_NG, pady=10)
        lbl_info.pack()
        
        canvas = tk.Canvas(win, bg="black", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # 画像読み込み表示
        def _load():
            try:
                img = cv2.imread(path)
                if img is None: return
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                
                win.update_idletasks()
                cw, ch = canvas.winfo_width(), canvas.winfo_height()
                if cw < 10: cw, ch = 760, 500
                
                pil_img = PIL.Image.fromarray(img)
                pil_img.thumbnail((cw, ch), PIL.Image.LANCZOS)
                img_tk = PIL.ImageTk.PhotoImage(pil_img)
                canvas.image = img_tk
                canvas.create_image(cw//2, ch//2, image=img_tk, anchor=tk.CENTER)
            except Exception as e:
                logger.error(f"Failed to load NG image: {e}")
        
        win.after(100, _load)
        tk.Button(win, text="閉じる", font=FONT_BOLD, bg="#546E7A", fg="white", 
                  relief=tk.FLAT, padx=30, command=win.destroy).pack(pady=10)

    # --- プレビュー表示 ---
    def _update_preview(self):
        if not self.is_running or self.is_paused:
            # 停止中、または一時停止中（設定画面表示中など）は更新をスキップ
            if self.is_running:
                self.root.after(200, self._update_preview)
            return
        
        # プレビュー解像度取得
        prev_res = self.cm.get("preview_res", "640x480")
        if prev_res == "none_preview":
            self.root.after(200, self._update_preview)
            return

        try:
            pw, ph = map(int, prev_res.split('x'))
        except:
            pw, ph = 640, 480
            
        for cam, canvas, key in [(self.cam_ref, self.canvas_ref, "crop_ref_text"), (self.cam_insp, self.canvas_insp, "crop_insp_text")]:
            if cam:
                frame = cam.get_frame()
                if frame is not None:
                    # 早めにリサイズして以降の処理負荷を軽減 (4K等の高解像度対策)
                    frame = cv2.resize(frame, (pw, ph))
                    
                    # 反転処理 (検査カメラのみ)
                    if "insp" in key:
                        h, v = self.cm.get("flip_insp_h"), self.cm.get("flip_insp_v")
                        if h and v: frame = cv2.flip(frame, -1)
                        elif h: frame = cv2.flip(frame, 1)
                        elif v: frame = cv2.flip(frame, 0)
                    
                    # ROI枠描画
                    roi = self.cm.get(key)
                    if roi and len(roi) == 4:
                        fh, fw = frame.shape[:2]
                        rx1, ry1, rx2, ry2 = roi
                        px1 = int(min(rx1, rx2) * fw)
                        py1 = int(min(ry1, ry2) * fh)
                        px2 = int(max(rx1, rx2) * fw)
                        py2 = int(max(ry1, ry2) * fh)
                        
                        # 状態に応じたROI色 (待機:黄, 検査中:青, OK/NG後:暫くそのまま)
                        roi_col = (0, 255, 255) # Yellow
                        cv2.rectangle(frame, (px1, py1), (px2, py2), roi_col, 2)
                    
                    self._display_image(canvas, frame)
        
        try:
            fps = int(self.cm.get("preview_fps", 30))
            if fps <= 0: fps = 30
        except:
            fps = 30
        delay = max(1, int(1000 / fps))
        self.root.after(delay, self._update_preview)

    def _display_image(self, canvas, frame):
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        if cw < 50: return
        
        # 既にcv2.resize済みだがキャンバスサイズに微調整
        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img_pil = PIL.Image.fromarray(img_rgb)
        img_pil.thumbnail((cw, ch), PIL.Image.NEAREST) # 高速なリサンプリング
        img_tk = PIL.ImageTk.PhotoImage(img_pil)
        
        c_id = id(canvas)
        self.tk_images[c_id] = img_tk # 参照保持
        
        if c_id in self.canvas_images:
            canvas.itemconfig(self.canvas_images[c_id], image=img_tk)
        else:
            self.canvas_images[c_id] = canvas.create_image(cw//2, ch//2, image=img_tk, anchor=tk.CENTER)

    def _inspection_loop(self):
        logger.info("Inspection loop started.")
        while self.is_running:
            try:
                if self.is_paused:
                    time.sleep(0.5)
                    continue

                if self.cm.get("mode_trigger"):
                    # --- トリガー有効モード ---
                    self._update_ui_state("待機", "トリガー入力待ち", COLOR_ACCENT)
                    self.root.after(0, lambda: self.lbl_pattern.config(text="---", fg=COLOR_TEXT_MAIN))
                    
                    trigger_detected = False
                    while self.is_running and self.cm.get("mode_trigger") and not self.is_paused:
                        if self.gpio.check_and_reset_trigger():
                            trigger_detected = True
                            break
                        time.sleep(0.05)
                    
                    if not self.is_running or not trigger_detected:
                        continue
                    
                    self._update_ui_state("検査中", "画像取得およびOCR判定中", COLOR_ACCENT)
                    img_ref = self.cam_ref.get_frame() if self.cam_ref else None
                    img_insp = self.cam_insp.get_frame() if self.cam_insp else None
                    
                    ref_text, ref_score = self.inspector.get_ocr(img_ref, self.cm.get("crop_ref_text")) if img_ref is not None else ("", 0.0)
                    
                    if ref_text:
                        skip_patterns = self.cm.get("skip_patterns", [])
                        is_skip = any(p in ref_text for p in skip_patterns) if skip_patterns else False
                        if is_skip:
                            logger.info(f"SKIP detected: {ref_text}")
                            self._update_ui_state("SKIP", f"スキップ対象: {ref_text}", COLOR_WARNING)
                            self.inspector.save_evidence(img_ref, None, "SKIP", ref_text, ref_score)
                            time.sleep(self.cm.get("result_display_duration", 3.0))
                            continue
                    
                    if img_insp is not None:
                        h, v = self.cm.get("flip_insp_h"), self.cm.get("flip_insp_v")
                        if h and v: img_insp = cv2.flip(img_insp, -1)
                        elif h: img_insp = cv2.flip(img_insp, 1)
                        elif v: img_insp = cv2.flip(img_insp, 0)
                    
                    insp_text, insp_score = self.inspector.get_ocr(img_insp, self.cm.get("crop_insp_text")) if img_insp is not None else ("", 0.0)
                    
                    display_ref = ref_text if ref_text else "読取不可"
                    self.root.after(0, lambda t=display_ref: self.lbl_pattern.config(text=t, fg=COLOR_ACCENT_STRONG))
                    
                    match_mode = self.cm.get("match_mode", "partial")
                    is_match = False
                    if ref_text and insp_text:
                        if match_mode == "exact":
                            is_match = (ref_text == insp_text)
                        else:
                            is_match = (ref_text in insp_text)
                    
                    if is_match:
                        logger.info(f"Match OK: Ref='{ref_text}' Insp='{insp_text}'")
                        self._update_ui_state("OK", f"一致: {ref_text}", COLOR_OK)
                        self.inspector.save_evidence(img_ref, img_insp, "OK", ref_text, insp_score)
                        self.gpio.output_ok()
                    else:
                        logger.info(f"Match NG: Ref='{ref_text}' Insp='{insp_text}'")
                        self._update_ui_state("NG", f"NG: 正解[{display_ref}] / 検出[{insp_text}]", COLOR_NG)
                        path = self.inspector.save_evidence(img_ref, img_insp, "NG", ref_text, insp_score)
                        self.gpio.output_ng()
                        msg = f"{datetime.now().strftime('%H:%M:%S')} NG: [{display_ref}] / [{insp_text}]"
                        self._add_to_history(msg, path)
                    
                    time.sleep(self.cm.get("result_display_duration", 3.0))
                    
                else:
                    # --- トリガー無効モード (自動モード) ---
                    img_ref = self.cam_ref.get_frame() if self.cam_ref else None
                    ref_text, ref_score = self.inspector.get_ocr(img_ref, self.cm.get("crop_ref_text")) if img_ref is not None else ("", 0.0)
                    
                    if not ref_text:
                        self._update_ui_state("システム待機中", "正解文字読み取り中", COLOR_ACCENT)
                        self.root.after(0, lambda: self.lbl_pattern.config(text="---", fg=COLOR_TEXT_MAIN))
                        time.sleep(0.5)
                        continue
                    
                    skip_patterns = self.cm.get("skip_patterns", [])
                    is_skip = any(p in ref_text for p in skip_patterns) if skip_patterns else False
                    if is_skip:
                        logger.info(f"SKIP detected: {ref_text}")
                        self._update_ui_state("SKIP", f"スキップ対象: {ref_text}", COLOR_WARNING)
                        self.inspector.save_evidence(img_ref, None, "SKIP", ref_text, ref_score)
                        time.sleep(self.cm.get("result_display_duration", 3.0))
                        continue
                    
                    self.root.after(0, lambda t=ref_text: self.lbl_pattern.config(text=t, fg=COLOR_ACCENT_STRONG))
                    match_mode = self.cm.get("match_mode", "partial")
                    
                    retry_count = 0
                    max_retries = self.cm.get("max_retries", 3)
                    
                    while self.is_running and not self.cm.get("mode_trigger") and not self.is_paused:
                        self._update_ui_state("検査中", f"正解:[{ref_text}] 照合中", COLOR_ACCENT)
                        img_insp = self.cam_insp.get_frame() if self.cam_insp else None
                        if img_insp is not None:
                            h, v = self.cm.get("flip_insp_h"), self.cm.get("flip_insp_v")
                            if h and v: img_insp = cv2.flip(img_insp, -1)
                            elif h: img_insp = cv2.flip(img_insp, 1)
                            elif v: img_insp = cv2.flip(img_insp, 0)
                            
                            insp_text, insp_score = self.inspector.get_ocr(img_insp, self.cm.get("crop_insp_text"))
                            is_match = False
                            if insp_text and ref_text:
                                if match_mode == "exact":
                                    is_match = (ref_text == insp_text)
                                else:
                                    is_match = (ref_text in insp_text)
                                    
                            if is_match:
                                logger.info(f"Match OK: Ref='{ref_text}' Insp='{insp_text}'")
                                self._update_ui_state("OK", f"一致: {ref_text}", COLOR_OK)
                                self.inspector.save_evidence(img_ref, img_insp, "OK", ref_text, insp_score)
                                self.gpio.output_ok()
                                time.sleep(self.cm.get("wait_after_ok", 2.0))
                                break 
                            else:
                                if retry_count < max_retries:
                                    retry_count += 1
                                    logger.info(f"Mismatch. Retrying ({retry_count}/{max_retries})...")
                                    time.sleep(0.1)
                                    continue
                                
                                logger.info(f"Match NG: Ref='{ref_text}' Insp='{insp_text}'")
                                # NG時は一度抜けて再度正解文字読み取りから直すか、あるいは一定時間表示して継続
                                self._update_ui_state("NG", f"NG: 正解[{ref_text}] / 検出[{insp_text}]", COLOR_NG)
                                path = self.inspector.save_evidence(img_ref, img_insp, "NG", ref_text, insp_score)
                                self.gpio.output_ng()
                                msg = f"{datetime.now().strftime('%H:%M:%S')} NG: [{ref_text}] / [{insp_text}]"
                                self._add_to_history(msg, path)
                                time.sleep(self.cm.get("result_display_duration", 3.0))
                                break
                        time.sleep(0.1)

            except Exception as e:
                logger.error(f"Error in inspection loop: {e}", exc_info=True)
                time.sleep(1.0)

    def _update_ui_state(self, status, message, color):
        def _apply():
            # パルス（点滅）効果のための状態更新
            mode_prefix = "●" if color == COLOR_ACCENT else "■"
            self.lbl_mode.config(text=f"{mode_prefix} {status}", fg=color if color != COLOR_BG_PANEL else COLOR_TEXT_SUB)

            if color == COLOR_OK:
                bg_col, fg_col = COLOR_OK, "black"
            elif color == COLOR_NG:
                bg_col, fg_col = COLOR_NG, "white"
            elif color == COLOR_WARNING:
                bg_col, fg_col = COLOR_WARNING, "black"
            elif color == COLOR_ACCENT:
                bg_col, fg_col = COLOR_ACCENT, "black"
            else:
                bg_col, fg_col = COLOR_BG_PANEL, COLOR_ACCENT

            self.lbl_status.config(text=f"{status} {message}", fg=fg_col, bg=bg_col)
            self.header.config(bg=bg_col)
            self.lbl_clock.config(bg=bg_col)
            # 子要素の更新
            for w in self.header.winfo_children():
                try:
                    if not isinstance(w, tk.Button):
                        w.config(bg=bg_col)
                        if bg_col == COLOR_BG_PANEL:
                            if w == self.lbl_status: w.config(fg=COLOR_ACCENT)
                        else:
                            w.config(fg=fg_col)
                except: pass

        self.root.after(0, _apply)

    def _add_to_history(self, msg, img_path=None):
        def _apply():
            self.lst_history.insert(0, msg)
            self.ng_history.insert(0, (msg, img_path))
            # 履歴が多くなりすぎないよう制限
            if self.lst_history.size() > 100:
                self.lst_history.delete(100, tk.END)
                self.ng_history = self.ng_history[:100]
        self.root.after(0, _apply)

    def _open_settings(self):
        cameras = {'ref': self.cam_ref, 'insp': self.cam_insp}
        SettingsDialog(self.root, self.cm, self.gpio, cameras, on_save_callback=self._on_settings_saved)

    def _on_settings_saved(self):
        # 解像度が変更された可能性があるため、カメラを再初期化
        if self.cam_ref: self.cam_ref.release()
        if self.cam_insp: self.cam_insp.release()
        self._init_cameras()

    def close(self):
        self.is_running = False
        if self.cam_ref: self.cam_ref.release()
        if self.cam_insp: self.cam_insp.release()
