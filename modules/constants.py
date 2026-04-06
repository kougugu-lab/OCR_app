import os
import platform

# --- バージョン定義 ---
VERSION = "1.3.0"
BUILD_DATE = "2026-04-06"

# --- ディレクトリ定義 ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "results", "logs")
RESULT_OK_DIR = os.path.join(BASE_DIR, "results", "images", "OK")
RESULT_NG_DIR = os.path.join(BASE_DIR, "results", "images", "NG")
RESULT_SKIP_DIR = os.path.join(BASE_DIR, "results", "images", "SKIP")
RESULT_REC_DIR = os.path.join(BASE_DIR, "results", "images", "REC")
CSV_DIR = os.path.join(BASE_DIR, "results", "csv")

for d in [LOG_DIR, RESULT_OK_DIR, RESULT_NG_DIR, RESULT_SKIP_DIR, RESULT_REC_DIR, CSV_DIR]:
    os.makedirs(d, exist_ok=True)

# --- カラーパレット (Dark Gray Theme) ---
COLOR_BG_MAIN = "#2b2b2b"      # ウィンドウ・フレームの基底背景
COLOR_BG_PANEL = "#3c3f41"     # カード・LabelFrame の背景
COLOR_BG_INPUT = "#45494a"     # Entry・Listbox・ラベル値欄の背景
COLOR_TEXT_MAIN = "#FFFFFF"    # 通常の文字色
COLOR_TEXT_SUB = "#B0BEC5"     # ラベル・説明文等の補助文字色
COLOR_ACCENT = "#4FC3F7"       # ハイライト・ボタン・強調表示
COLOR_ACCENT_STRONG = "#00E5FF" # より鮮やかなアクセント色
COLOR_ACCENT_HOVER = "#81D4FA" # ホバー時
COLOR_OK = "#66BB6A"           # 合格判定・成功メッセージ
COLOR_NG = "#FF5252"           # 不合格判定・エラーメッセージ
COLOR_WARNING = "#FFB74D"      # 注意・SKIP・中間状態
COLOR_BORDER = "#505050"       # フレームの境界線

# 後方互換性(既存コード用)
COLOR_BG = COLOR_BG_MAIN
COLOR_CARD = COLOR_BG_PANEL
COLOR_CARD_DARK = COLOR_BG_INPUT
COLOR_CARD_HEADER = "#333333"
COLOR_ENTRY_BG = COLOR_BG_INPUT
COLOR_ACCENT_BLUE = COLOR_ACCENT
COLOR_ACCENT_LIGHT_BLUE = COLOR_ACCENT_HOVER
COLOR_ACCENT_GREEN = COLOR_OK
COLOR_ACCENT_RED = COLOR_NG
COLOR_LED_ON = "#00ff00"
COLOR_LED_OFF = "#444444"
COLOR_TOGGLE_ON = COLOR_ACCENT
COLOR_TOGGLE_OFF = "#555555"
COLOR_TOGGLE_KNOB = "#FFFFFF"

# --- フォント定義 ---
FONT_FAMILY = "Meiryo UI"
FONT_NORMAL = (FONT_FAMILY, 14)
FONT_BOLD = (FONT_FAMILY, 16, "bold")
FONT_LARGE = (FONT_FAMILY, 24, "bold")
FONT_HUGE = (FONT_FAMILY, 48, "bold")
FONT_SET_TAB = (FONT_FAMILY, 18, "bold")
FONT_SET_LBL = (FONT_FAMILY, 16, "bold")
FONT_SET_VAL = (FONT_FAMILY, 16)
FONT_BTN_LARGE = (FONT_FAMILY, 16, "bold")

# 後方互換性(既存コード用)
FONT_S = FONT_SET_VAL
FONT_M = FONT_SET_TAB
FONT_L = FONT_LARGE
FONT_STATUS = FONT_HUGE
FONT_SPIN = FONT_SET_VAL

# --- 解像度オプション ---
RES_MAP = {
    "320x240": "320x240 (QVGA)",
    "640x480": "640x480 (VGA)",
    "1280x720": "1280x720 (HD)",
    "1920x1080": "1920x1080 (Full HD)",
    "3840x2160": "3840x2160 (4K)",
    "none_preview": "プレビューなし",
    "none_save": "保存しない"
}

RES_OPTIONS = ["320x240", "640x480", "1280x720", "1920x1080", "3840x2160"]
RES_OPTIONS_PREVIEW = ["none_preview", "320x240", "640x480", "1280x720"]
RES_OPTIONS_SAVE = RES_OPTIONS + ["none_save"]

IS_WINDOWS = platform.system() == 'Windows'

# --- デフォルト設定 ---
DEFAULT_CONFIG = {
    "camera_ref_id": 0, 
    "camera_insp_id": 1,
    "focus_ref": "", 
    "focus_insp": "",
    "capture_res": "1920x1080",
    "preview_res": "640x480",
    "res_ok": "320x240",
    "res_ng": "1920x1080",
    "crop_ref_text": [0.2, 0.2, 0.8, 0.8],  # 相対比率 [rx1, ry1, rx2, ry2] (0.0~1.0)
    "crop_insp_text": [0.2, 0.2, 0.8, 0.8], # 相対比率 [rx1, ry1, rx2, ry2] (0.0~1.0)
    "wait_after_ok": 5.0, 
    "ok_signal_duration": 2.0,
    "ng_signal_duration": 2.0,
    "gpio_ok_pin": 27, 
    "gpio_ng_pin": 22, 
    "gpio_trigger_pin": 23,
    "max_storage_gb": 10,
    "flip_insp_v": False, 
    "flip_insp_h": False,
    "mode_trigger": True,
    "max_retries": 3,
    "allowed_chars": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "ocr_threshold": 0.5,
    "result_display_duration": 7.0,
    "result_dir": "", # 空の場合は BASE_DIR 内の results を使用
    "match_mode": "partial",  # "partial" or "exact"
    "skip_patterns": [],      # List of strings to skip inspection
    "preview_fps": 2,        # Preview refresh rate in fps
    # --- 共通UI要件用設定 ---
    "ng_history": []          # NG履歴 (画像パスなど)
}
