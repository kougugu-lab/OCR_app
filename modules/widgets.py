import tkinter as tk
from tkinter import ttk
from .constants import *

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self._after_id = None
        self._last_event = None
        self.widget.bind("<Enter>", self._schedule)
        self.widget.bind("<Leave>", self.hide_tip)
        self.widget.bind("<Motion>", self._update_pos)

    def _schedule(self, event=None):
        self._last_event = event
        if self._after_id:
            self.widget.after_cancel(self._after_id)
        self._after_id = self.widget.after(300, self._show)

    def _update_pos(self, event=None):
        self._last_event = event
        if self.tip_window:
            self._reposition(event)

    def _reposition(self, event=None):
        tw = self.tip_window
        if not tw: return
        tw.update_idletasks()
        w_tip, h_tip = tw.winfo_width(), tw.winfo_height()
        if event:
            cx, cy = event.x_root, event.y_root
        else:
            cx = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
            cy = self.widget.winfo_rooty() + self.widget.winfo_height()
        
        scr_w = self.widget.winfo_screenwidth()
        scr_h = self.widget.winfo_screenheight()
        
        x = min(cx + 16, scr_w - w_tip - 10)
        y = cy + 16 if cy + h_tip + 30 < scr_h else cy - h_tip - 10
        tw.wm_geometry(f"+{x}+{y}")

    def _show(self):
        if self.tip_window or not self.text:
            return
        ev = self._last_event
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#1e2a35", fg="#e0e8f0",
                         relief=tk.SOLID, borderwidth=1,
                         font=(FONT_NORMAL[0], 10), padx=8, pady=6)
        label.pack(ipadx=1)
        tw.update_idletasks()
        self._reposition(ev)

    def hide_tip(self, event=None):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        tw = self.tip_window
        self.tip_window = None
        if tw: tw.destroy()

class ScrollableFrame(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.canvas = tk.Canvas(self, bg=COLOR_BG_MAIN, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=COLOR_BG_MAIN)
        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        
    def _on_mousewheel(self, event):
        if not self.winfo_exists() or not self.canvas.winfo_ismapped(): return
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

class HybridSlider(tk.Frame):
    def __init__(self, parent, label, var, from_, to, resolution=1, on_change=None):
        super().__init__(parent, bg=parent["bg"])
        self.on_change = on_change
        self.var = var
        
        # コントロール部
        controls = tk.Frame(self, bg=COLOR_BG_INPUT, bd=1, relief=tk.SOLID, highlightbackground=COLOR_BORDER, highlightthickness=1)
        controls.pack(fill=tk.X)
        
        self.scale = tk.Scale(controls, from_=from_, to=to, resolution=resolution, variable=var, 
                                orient=tk.HORIZONTAL, bg=COLOR_BG_INPUT, fg="white", 
                                highlightthickness=0, troughcolor="#333333", 
                                activebackground=COLOR_ACCENT, showvalue=False,
                                command=self._on_scale, sliderrelief=tk.FLAT, sliderlength=20)
        self.scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        sep = tk.Frame(controls, width=1, bg=COLOR_BORDER); sep.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Spinbox
        self.spin = tk.Spinbox(controls, from_=from_, to=to, increment=resolution, textvariable=var,
                               width=6, font=FONT_SET_VAL, bg=COLOR_BG_INPUT, fg="white", 
                               buttonbackground="#78909C", bd=0, highlightthickness=0,
                               command=self._on_spin)
        self.spin.pack(side=tk.RIGHT, padx=5)
        
        self.var.trace_add("write", lambda *args: self._on_change())

    def _on_scale(self, val):
        self._on_change()

    def _on_spin(self):
        self._on_change()

    def _on_change(self):
        if self.on_change: self.on_change()

class LEDIndicator(tk.Frame):
    def __init__(self, parent, label):
        super().__init__(parent, bg=parent["bg"])
        self.canvas = tk.Canvas(self, width=16, height=16, bg=parent["bg"], highlightthickness=0)
        self.canvas.pack(side=tk.LEFT)
        self.led = self.canvas.create_oval(2, 2, 14, 14, fill=COLOR_LED_OFF, outline="#666666")
        tk.Label(self, text=label, font=FONT_NORMAL, bg=parent["bg"], fg=COLOR_TEXT_SUB).pack(side=tk.LEFT, padx=5)

    def set_state(self, is_on):
        color = COLOR_LED_ON if is_on else COLOR_LED_OFF
        self.canvas.itemconfig(self.led, fill=color)

class ToggleSwitch(tk.Canvas):
    def __init__(self, parent, variable, command=None, width=45, height=22):
        super().__init__(parent, width=width, height=height, bg=parent["bg"], highlightthickness=0, cursor="hand2")
        self.variable, self.command = variable, command
        self.width, self.height = width, height
        self.state = variable.get()
        self._draw()
        self.bind("<Button-1>", self._toggle)
        self.variable.trace_add("write", lambda *args: self._sync())

    def _draw(self):
        self.delete("all")
        r = self.height / 2
        bg_color = COLOR_TOGGLE_ON if self.state else COLOR_TOGGLE_OFF
        self.create_arc(0, 0, self.height, self.height, start=90, extent=180, fill=bg_color, outline=bg_color)
        self.create_rectangle(r, 0, self.width - r, self.height, fill=bg_color, outline=bg_color)
        self.create_arc(self.width - self.height, 0, self.width, self.height, start=270, extent=180, fill=bg_color, outline=bg_color)
        x = self.width - r - (r-2) if self.state else r - (r-2)
        self.create_oval(x, 2, x + (self.height-4), self.height - 2, fill=COLOR_TOGGLE_KNOB, outline=COLOR_TOGGLE_KNOB)

    def _toggle(self, event):
        self.variable.set(not self.state)
        if self.command: self.command()

    def _sync(self):
        new_state = self.variable.get()
        if self.state != new_state:
            self.state = new_state
            self._draw()

class HelpWindow(tk.Toplevel):
    def __init__(self, parent, title, help_data):
        super().__init__(parent)
        self.title(title)
        self.geometry("700x500")
        self.configure(bg=COLOR_BG_MAIN)
        self.transient(parent)
        scroll = ScrollableFrame(self)
        scroll.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        c = scroll.scrollable_frame
        for k, v in help_data.items():
            f = tk.Frame(c, bg=COLOR_BG_PANEL, bd=1, relief=tk.SOLID, highlightbackground=COLOR_BORDER, highlightthickness=1)
            f.pack(fill=tk.X, pady=(0, 15))
            h = tk.Frame(f, bg="#333333", padx=15, pady=8)
            h.pack(fill=tk.X)
            tk.Label(h, text=k, font=FONT_SET_LBL, bg="#333333", fg=COLOR_ACCENT).pack(side=tk.LEFT)
            
            tk.Label(f, text=v.strip(), font=FONT_NORMAL, bg=COLOR_BG_PANEL, 
                     fg=COLOR_TEXT_MAIN, justify=tk.LEFT, anchor=tk.W, wraplength=600
                    ).pack(fill=tk.X, padx=20, pady=15)

        tk.Button(self, text="閉じる", font=FONT_BOLD, bg="#546E7A", fg="white", 
                  relief=tk.FLAT, padx=30, pady=10, command=self.destroy).pack(pady=10)
