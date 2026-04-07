import cv2
import threading
import time

class CameraStream:
    def __init__(self, src, width, height, focus=None):
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
