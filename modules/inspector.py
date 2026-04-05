import os
import cv2
import shutil
import time
from datetime import datetime
from rapidocr_onnxruntime import RapidOCR
from .constants import LOG_DIR, RESULT_OK_DIR, RESULT_NG_DIR, BASE_DIR

class Inspector:
    def __init__(self, config_manager):
        self.conf = config_manager
        try:
            self.ocr = RapidOCR()
        except Exception as e:
            raise RuntimeError(f"OCR初期化失敗: {e}")

    def get_ocr(self, img, crop):
        """画像から指定範囲の文字を抽出。テキストと平均スコアを返す。
        crop: 相対比率 [rx1, ry1, rx2, ry2] (0.0~1.0)
        """
        if img is None: return "", 0.0
        try:
            # 相対比率をピクセル座標に変換
            h, w = img.shape[:2]
            rx1, ry1, rx2, ry2 = crop
            x1 = int(min(rx1, rx2) * w)
            y1 = int(min(ry1, ry2) * h)
            x2 = int(max(rx1, rx2) * w)
            y2 = int(max(ry1, ry2) * h)
            # クリップ
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            
            roi = img[y1:y2, x1:x2]
            if roi.size == 0: return "", 0.0
            
            res, _ = self.ocr(roi)
            if res:
                threshold = self.conf.get("ocr_threshold", 0.5)
                valid_texts = []
                scores = []
                for line in res:
                    text_line, score_line = line[1], line[2]
                    if float(score_line) >= threshold:
                        valid_texts.append(text_line)
                        scores.append(float(score_line))
                
                text = "".join(valid_texts).replace(" ", "")
                allowed = self.conf.get("allowed_chars", "")
                if allowed:
                    text = "".join([c for c in text if c in allowed])
                
                avg_score = sum(scores) / len(scores) if scores else 0.0
                return text, avg_score
            return "", 0.0
        except Exception as e:
            print(f"OCR Error: {e}")
            return "", 0.0

    def save_evidence(self, img_ref, img_insp, result, pattern, score=0.0):
        """判定結果の画像とCSVログを保存"""
        now = datetime.now()
        date_str = now.strftime("%Y%m%d")
        ts_full = now.strftime("%Y%m%d%H%M%S")
        
        # ディレクトリ準備
        results_base = self.conf.get("result_dir")
        if not results_base:
            results_base = os.path.join(BASE_DIR, "results")
            
        # 規約 (§8-3): 大文字のサブフォルダ名
        sub = "OK" if result == "OK" else ("SKIP" if result == "SKIP" else "NG")
        img_dir = os.path.join(results_base, "images", sub)
        os.makedirs(img_dir, exist_ok=True)
        
        # 画像保存
        # 規約 (§11-1): {判定}_{パターン}_{カメラ}_{日付時刻14桁}.jpg
        safe_pattern = "".join([c for c in (pattern if pattern else "None") if c not in '<>:"/\\|?*'])
        
        for img, cam_name in [(img_ref, "REF"), (img_insp, "INSP")]:
            if img is not None:
                res_key = "res_ok" if result == "OK" else "res_ng"
                res_str = self.conf.get(res_key, "640x480" if result == "OK" else "1280x720")
                
                if res_str == "none_save":
                    continue
                
                try:
                    target_w, target_h = map(int, res_str.split('x'))
                    resized = cv2.resize(img, (target_w, target_h))
                except Exception:
                    h, w = img.shape[:2]
                    target_w = 640 if result == "OK" else 1280
                    resized = cv2.resize(img, (target_w, int(h * (target_w / w))))
                
                fname = f"{result}_{safe_pattern}_{cam_name}_{ts_full}_{score:.2f}.jpg"
                cv2.imwrite(os.path.join(img_dir, fname), resized)
        
        # CSVログ保存
        # ユーザー要望により日本語ヘッダーを使用 (規約 §11-2 より優先)
        csv_dir = os.path.join(results_base, "csv")
        os.makedirs(csv_dir, exist_ok=True)
        csv_path = os.path.join(csv_dir, f"inspection_{date_str}.csv")
        
        headers = "日時,正解文字,トリガー,カメラ名,判定結果,信頼度,詳細内容\n"
        exists = os.path.exists(csv_path)
        
        # 項目を組み立て
        dt = now.strftime('%Y/%m/%d %H:%M:%S')
        trigger = "GPIO" if self.conf.get("mode_trigger") else "自動"
        details = f"OCR:{pattern}" if pattern else "OCR:なし"
        
        log_line = f"{dt},{safe_pattern},{trigger},代表カメラ,{result},{score:.2f},{details}\n"
        
        try:
            with open(csv_path, "a", encoding="cp932") as f:
                if not exists: f.write(headers)
                f.write(log_line)
        except Exception as e:
            print(f"CSV Save Error: {e}")
            
        self.check_and_cleanup_disk()

    def check_and_cleanup_disk(self):
        """ディスク容量を確認し、設定された上限(GB)を超えている場合に古いファイルを削除"""
        results_dir = self.conf.get("result_dir", os.path.join(BASE_DIR, "results"))
        if not os.path.exists(results_dir): return
        
        max_gb = self.conf.get("max_storage_gb", 10)
        max_bytes = max_gb * 1024 * 1024 * 1024
        
        # フォルダ全体のサイズを計算
        total_size = 0
        file_list = []
        # §Review提案: ログも含めるか設定可能にする（現状は画像優先）
        cleanup_logs = self.conf.get("cleanup_logs_enabled", False)
        
        for root, _, filenames in os.walk(results_dir):
            for f in filenames:
                # デフォルトでは .csv, .log は重要な証跡として保護する
                if not cleanup_logs and (f.endswith(".csv") or f.endswith(".log")):
                    continue
                p = os.path.join(root, f)
                try:
                    s = os.path.getsize(p)
                    total_size += s
                    file_list.append((p, os.path.getmtime(p), s))
                except: pass
        
        # 上限を超えている場合、古い順に削除
        if total_size > max_bytes:
            file_list.sort(key=lambda x: x[1]) # mtimeでソート
            for p, _, s in file_list:
                try:
                    os.remove(p)
                    total_size -= s
                    # 90%まで減ったら終了（余裕を持たせる）
                    if total_size < max_bytes * 0.9: 
                        break
                except: pass
