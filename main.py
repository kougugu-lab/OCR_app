import sys
import os
import tkinter as tk
import logging
from datetime import datetime
from modules.config_manager import ConfigManager
from modules.gui_app import GUIApp
from modules.constants import BASE_DIR

def setup_logging():
    log_dir = os.path.join(BASE_DIR, "results", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"app_{datetime.now().strftime('%Y%m%d')}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger("Main")

def main():
    logger = setup_logging()
    logger.info("Application starting...")
    
    # 1. 設定管理の初期化
    cm = ConfigManager()
    
    # 2. Tkinter ルートの作成
    root = tk.Tk()
    
    # 3. アプリケーションの初期化
    try:
        app = GUIApp(root, cm)
    except Exception as e:
        logger.error(f"Failed to initialize GUIApp: {e}", exc_info=True)
        tk.messagebox.showerror("起動エラー", f"アプリケーションの初期化に失敗しました:\n{e}")
        sys.exit(1)
    
    # 4. 終了処理の定義
    def on_closing():
        if tk.messagebox.askokcancel("終了", "アプリケーションを終了しますか？"):
            logger.info("Application closing...")
            app.close()
            root.destroy()
            sys.exit(0)

    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    # 5. メインループ開始
    try:
        root.mainloop()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received.")
        app.close()
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Unhandled exception in main loop: {e}", exc_info=True)

if __name__ == "__main__":
    main()
