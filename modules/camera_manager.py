import cv2
import threading
import time
import os
import sys
import subprocess


def detect_available_cameras():
    """OSが認識しているカメラデバイスを自動探索し、
    [(index_int, display_label_str, by_path_str), ...] のリストを返す。
    Linux環境では /dev/v4l/by-path を走査して物理USBポートに永続的に紐付くパスも取得・照合する。
    ※ UIフリーズやブロッキング、警告ログ多発を防ぐため VideoCapture による同期的接続テストは行わない。
    """
    devices = []

    if sys.platform.startswith("linux"):
        v4l_dir = "/sys/class/video4linux"
        by_path_dir = "/dev/v4l/by-path"

        by_path_map = {}
        if os.path.exists(by_path_dir):
            try:
                for fname in sorted(os.listdir(by_path_dir)):
                    full_p = os.path.join(by_path_dir, fname)
                    try:
                        real_p = os.path.realpath(full_p)
                        if "index0" in fname or real_p not in by_path_map:
                            by_path_map[real_p] = full_p
                    except Exception:
                        pass
            except Exception:
                pass

        if os.path.exists(v4l_dir):
            ignore_keywords = ["codec", "rpivid", "vc4", "media-controller", "bcm2835-isp", "h264", "hevc", "vp8"]
            for entry in sorted(os.listdir(v4l_dir), key=lambda x: int(x.replace("video", "")) if x.replace("video", "").isdigit() else 999):
                if entry.startswith("video"):
                    try:
                        idx = int(entry.replace("video", ""))
                        dev_node = f"/dev/video{idx}"
                        by_path = by_path_map.get(dev_node, "")

                        name_file = os.path.join(v4l_dir, entry, "name")
                        cam_name = f"カメラ {idx}"
                        if os.path.exists(name_file):
                            with open(name_file, "r", encoding="utf-8", errors="ignore") as f:
                                name_text = f.read().strip()
                                if name_text:
                                    cam_name = name_text

                        if any(k in cam_name.lower() for k in ignore_keywords):
                            continue

                        port_info = ""
                        if by_path:
                            bname = os.path.basename(by_path)
                            if "usb-" in bname:
                                u_part = bname.split("usb-")[-1].split(":")[0]
                                port_info = f" (Port {u_part})"

                        devices.append((idx, f"[{idx}] {cam_name}{port_info}", by_path))
                    except Exception:
                        pass
    elif sys.platform.startswith("win"):
        names_from_ps = []
        try:
            ps_cmd = 'Get-CimInstance Win32_PnPEntity | Where-Object {$_.PNPClass -eq "Camera" -or $_.PNPClass -eq "Image"} | Select-Object -ExpandProperty Name'
            res = subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and res.stdout:
                names_from_ps = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        except Exception:
            pass

        if names_from_ps:
            for idx, d_name in enumerate(names_from_ps):
                devices.append((idx, f"[{idx}] {d_name}", ""))

    existing_indices = {d[0] for d in devices}
    for idx in range(4):
        if idx not in existing_indices:
            devices.append((idx, f"[{idx}] カメラ (インデックス {idx})", ""))

    devices.sort(key=lambda x: x[0])
    return devices


def resolve_camera_index_by_path(by_path_str):
    """Linux環境で物理USBポートパス(by_path)から現在の実 /dev/videoX インデックスを動的解決する"""
    if sys.platform.startswith("linux") and by_path_str and os.path.exists(by_path_str):
        try:
            real_p = os.path.realpath(by_path_str)
            bname = os.path.basename(real_p)
            if bname.startswith("video") and bname[5:].isdigit():
                return int(bname[5:])
        except Exception:
            pass
    return None


class CameraStream:
    def __init__(self, src, width, height, focus=None):
        if sys.platform.startswith("linux"):
            self.cap = cv2.VideoCapture(src, cv2.CAP_V4L2)
        elif sys.platform.startswith("win"):
            self.cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
        else:
            self.cap = cv2.VideoCapture(src)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # バッファを取り除き遅延を最小化
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        
        if focus is not None and str(focus).strip() != "":
            try:
                f_val = int(float(focus)) # スライダー対応でfloatも許容
                self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 0) 
                self.cap.set(cv2.CAP_PROP_FOCUS, f_val)
            except: pass
        else:
            self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)

        self.frame = None
        self.frame_id = 0
        self.running = True
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self.update, daemon=True)
        self.thread.start()

    def is_opened(self):
        return self.cap.isOpened()

    def update(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.frame = frame
                    self.frame_id += 1
            else:
                time.sleep(0.01)

    def get_frame(self):
        """戻り値: (フレーム画像, フレームID)"""
        with self.lock:
            return (self.frame.copy() if self.frame is not None else None), self.frame_id

    def release(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self.cap.release()

    def set_focus(self, focus_val):
        try:
            f_val = int(float(focus_val))
            self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 0) 
            self.cap.set(cv2.CAP_PROP_FOCUS, f_val)
        except: pass

    def auto_optimize_focus(self, roi=None, callback=None):
        """
        オートフォーカス最適化
        roi: [x1, y1, x2, y2]
        callback: 進行状況通知用 (focus_val, score)
        """
        def run_af():
            self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
            max_score, best_f = -1, 0
            
            # 粗スキャン (Coarse)
            for f in range(0, 1024, 40):
                if not self.running: return
                self.cap.set(cv2.CAP_PROP_FOCUS, f)
                time.sleep(0.15)
                # フレーム読み捨て
                for _ in range(3): self.cap.grab()
                ret, frame = self.cap.read()
                if ret:
                    score = self._calculate_focus_score(frame, roi)
                    if callback: callback(f, score)
                    if score > max_score:
                        max_score, best_f = score, f
            
            # 精密スキャン (Fine)
            start_f = max(0, best_f - 40)
            end_f = min(1023, best_f + 40)
            for f in range(start_f, end_f + 1, 4):
                if not self.running: return
                self.cap.set(cv2.CAP_PROP_FOCUS, f)
                time.sleep(0.1)
                for _ in range(2): self.cap.grab()
                ret, frame = self.cap.read()
                if ret:
                    score = self._calculate_focus_score(frame, roi)
                    if callback: callback(f, score)
                    if score > max_score:
                        max_score, best_f = score, f
            
            self.cap.set(cv2.CAP_PROP_FOCUS, best_f)
            if callback: callback(best_f, -1) # 完了通知

        threading.Thread(target=run_af, daemon=True).start()

    def _calculate_focus_score(self, frame, roi):
        if roi:
            x1, y1, x2, y2 = roi
            # 安全策として座標を正規化
            h, w = frame.shape[:2]
            y_min, y_max = max(0, min(y1, y2)), min(h, max(y1, y2))
            x_min, x_max = max(0, min(x1, x2)), min(w, max(x1, x2))
            if (x_max - x_min) > 10 and (y_max - y_min) > 10:
                frame = frame[y_min:y_max, x_min:x_max]
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.Laplacian(gray, cv2.CV_64F).var()
