import threading
from .constants import IS_WINDOWS

if not IS_WINDOWS:
    try:
        from gpiozero import LED, Button
    except ImportError:
        pass

class GPIOHandler:
    def __init__(self, config_manager):
        self.cm = config_manager
        self.led_ok = self.led_ng = self.btn_trigger = None
        self.triggered = False
        self.is_mock = False
        self.mock_states = {"ok": False, "ng": False, "trigger": False}
        
        if not IS_WINDOWS:
            try:
                self.led_ok = LED(self.cm.get("gpio_ok_pin", 27))
                self.led_ng = LED(self.cm.get("gpio_ng_pin", 22))
                self.btn_trigger = Button(self.cm.get("gpio_trigger_pin", 23), pull_up=True)
                self.btn_trigger.when_pressed = self._on_triggered
            except Exception as e:
                print(f"GPIO Init Error: {e}")
                self.is_mock = True
        else:
            self.is_mock = True

    def _on_triggered(self):
        self.triggered = True

    def mock_trigger(self):
        if self.is_mock:
            self.triggered = True
            self.mock_states["trigger"] = True
            # 視覚確認用に800ms点灯させる (polling latency考慮)
            threading.Timer(0.8, lambda: self.mock_states.update({"trigger": False})).start()

    def output_ok(self):
        duration = self.cm.get("ok_signal_duration", 2.0)
        if duration <= 0: return

        if self.is_mock:
            self.mock_states["ok"] = True
            threading.Timer(duration, lambda: self.mock_states.update({"ok": False})).start()
            return

        if self.led_ok:
            self.led_ok.on()
            threading.Timer(duration, self.led_ok.off).start()

    def output_ng(self):
        duration = self.cm.get("ng_signal_duration", 1.0)
        if duration <= 0: return

        if self.is_mock:
            self.mock_states["ng"] = True
            threading.Timer(duration, lambda: self.mock_states.update({"ng": False})).start()
            return

        if self.led_ng:
            self.led_ng.on()
            threading.Timer(duration, self.led_ng.off).start()

    def stop_outputs(self):
        """すべての出力信号を即座に停止する"""
        if self.is_mock:
            self.mock_states["ok"] = False
            self.mock_states["ng"] = False
            return

        if self.led_ok: self.led_ok.off()
        if self.led_ng: self.led_ng.off()

    def check_and_reset_trigger(self):
        if self.triggered:
            self.triggered = False
            return True
        return False

    def get_pin_status(self, pin_name):
        """ピンの現在の状態を返す (True=ON, False=OFF)"""
        if self.is_mock:
            if pin_name in self.mock_states:
                return self.mock_states[pin_name]
            return False
            
        target = None
        if pin_name == "trigger": target = self.btn_trigger
        elif pin_name == "ok": target = self.led_ok
        elif pin_name == "ng": target = self.led_ng
        
        if target:
            try: return target.is_active if hasattr(target, 'is_active') else target.value
            except: pass
        return False

    def get_states(self):
        """すべてのピンの状態を一括で返す"""
        return {
            "trigger": self.get_pin_status("trigger"),
            "ok": self.get_pin_status("ok"),
            "ng": self.get_pin_status("ng")
        }
