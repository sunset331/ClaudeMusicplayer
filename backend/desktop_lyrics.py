"""
Desktop lyrics overlay — transparent always-on-top tkinter window.
Runs in a background thread, syncs with server state.
"""
import tkinter as tk
import threading
import time
import re
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


class DesktopLyrics:
    def __init__(self, get_state):
        self._get_state = get_state  # callable that returns server state dict
        self._win = None
        self._active = False
        self._font_size = 28
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._running = False
        if self._win:
            try:
                self._win.after(0, self._win.destroy)
            except Exception:
                pass
        self._win = None
        self._active = False

    def _run(self):
        self._win = tk.Tk()
        self._win.overrideredirect(True)
        self._win.attributes('-topmost', True)
        self._win.attributes('-alpha', 0.88)

        # Transparent color trick
        transp = "#010203"
        self._win.configure(bg=transp)
        self._win.attributes('-transparentcolor', transp)

        self._canvas = tk.Canvas(self._win, bg=transp, highlightthickness=0, width=720, height=100)
        self._canvas.pack()

        # Current line
        self._cur_id = self._canvas.create_text(
            360, 34, text="♪ Claude Music",
            font=("Microsoft YaHei", self._font_size, "bold"),
            fill="#ffffff", anchor=tk.CENTER, justify=tk.CENTER)
        # Next line
        self._next_id = self._canvas.create_text(
            360, 70, text="",
            font=("Microsoft YaHei", max(14, self._font_size - 6)),
            fill="#a898c8", anchor=tk.CENTER, justify=tk.CENTER)

        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        self._win.geometry(f"720x100+{(sw-720)//2}+{sh-160}")

        # Draggable
        drag = [0, 0]
        def on_down(e):
            drag[0], drag[1] = e.x_root, e.y_root
        def on_move(e):
            dx, dy = e.x_root - drag[0], e.y_root - drag[1]
            self._win.geometry(f"+{self._win.winfo_x()+dx}+{self._win.winfo_y()+dy}")
            drag[0], drag[1] = e.x_root, e.y_root
        for w in [self._win, self._canvas]:
            w.bind("<Button-1>", on_down)
            w.bind("<B1-Motion>", on_move)

        # Scroll font size
        def on_scroll(e):
            delta = 2 if e.delta > 0 else -2
            self._font_size = max(14, min(48, self._font_size + delta))
            self._canvas.itemconfig(self._cur_id, font=("Microsoft YaHei", self._font_size, "bold"))
            self._canvas.itemconfig(self._next_id, font=("Microsoft YaHei", max(14, self._font_size - 6)))
        self._win.bind("<MouseWheel>", on_scroll)

        self._active = True
        self._sync_loop()

    def _sync_loop(self):
        if not self._running or not self._win:
            return
        try:
            st = self._get_state()
            lyrics = st.get("_current_lyrics", [])
            if lyrics:
                cur_time = st.get("current_time", 0) * 1000  # seconds → ms
                cur_idx = -1
                for i, line in enumerate(lyrics):
                    if line["time"] <= cur_time:
                        cur_idx = i
                    else:
                        break

                cur_text = lyrics[cur_idx]["text"] if cur_idx >= 0 else ""
                next_text = lyrics[cur_idx + 1]["text"] if cur_idx + 1 < len(lyrics) else ""

                # Karaoke color: compute progress within current line
                if cur_idx >= 0 and cur_idx + 1 < len(lyrics):
                    start_ms = lyrics[cur_idx]["time"]
                    end_ms = lyrics[cur_idx + 1]["time"]
                    progress = min(1, max(0, (cur_time - start_ms) / max(1, end_ms - start_ms)))
                else:
                    progress = 0

                # Color gradient: purple (#c084fc) → pink (#f0a8c0) with progress
                r = int(192 + (240 - 192) * progress)
                g = int(132 + (168 - 132) * progress)
                b = int(252 + (192 - 252) * progress)
                karaoke_color = f"#{r:02x}{g:02x}{b:02x}"

                self._canvas.itemconfig(self._cur_id, text=cur_text or "♪", fill=karaoke_color)
                self._canvas.itemconfig(self._next_id, text=next_text)
        except Exception:
            pass
        self._win.after(300, self._sync_loop)
