#!/usr/bin/env python3
"""
Mini Player mode + Desktop Lyrics overlay for Claude Music Player.

- Mini Player: compact 300×80 floating window (always-on-top)
- Desktop Lyrics: transparent overlay showing current lyric line
  with karaoke-style progress coloring.
"""
import tkinter as tk
import time
import os

HOME = os.path.dirname(os.path.abspath(__file__))


# ── Mini Player ──────────────────────────────────────────────────

class MiniPlayer:
    """A compact, always-on-top mini player window."""

    def __init__(self, app):
        """
        app must expose:
          - app.root (tk.Tk)
          - app._toggle(), app._next(), app._like(), app._is_playing()
          - app.songs, app.idx
          - song info: songname, singer names, album art path
        """
        self._app = app
        self._win = None
        self._active = False
        self._drag_start_x = 0
        self._drag_start_y = 0

        # Widgets
        self._cover_lbl = None
        self._name_lbl = None
        self._artist_lbl = None
        self._pp_btn = None
        self._cover_img = None

    def toggle(self):
        """Toggle between full UI and mini player."""
        if self._active:
            self._hide()
        else:
            self._show()

    def _show(self):
        """Hide main window, show mini player."""
        if self._win is not None:
            return

        # Remember main window position
        self._main_geo = self._app.root.geometry()
        self._app.root.withdraw()

        self._win = tk.Toplevel(self._app.root)
        self._win.title("Claude Music · Mini")
        self._win.geometry("340x72")
        self._win.overrideredirect(True)  # no title bar
        self._win.attributes('-topmost', True)
        self._win.attributes('-alpha', 0.93)
        self._win.configure(bg="#0d0b1a")

        # Rounded border simulation via Canvas
        self._canvas = tk.Canvas(self._win, bg="#0d0b1a", highlightthickness=0,
                                 width=340, height=72)
        self._canvas.pack(fill=tk.BOTH, expand=True)
        # Outer border
        self._canvas.create_rectangle(0, 0, 340, 72,
                                       outline="#c084fc", width=1)

        # Cover placeholder
        self._cover_lbl = tk.Label(self._win, bg="#0d0b1a", fg="#a898c8",
                                   font=("Segoe UI Symbol", 16), text="♪",
                                   width=4, height=1)
        self._cover_lbl.place(x=6, y=6, width=48, height=60)

        # Song name (marquee-style static for now)
        self._name_lbl = tk.Label(self._win, text="暂停中",
                                  font=("Microsoft YaHei", 11, "bold"),
                                  fg="#e0d8f0", bg="#0d0b1a",
                                  anchor=tk.W, wraplength=180)
        self._name_lbl.place(x=60, y=6, width=180, height=22)
        self._artist_lbl = tk.Label(self._win, text="",
                                    font=("Microsoft YaHei", 9),
                                    fg="#f0a8c0", bg="#0d0b1a",
                                    anchor=tk.W, wraplength=180)
        self._artist_lbl.place(x=60, y=30, width=180, height=18)

        # Control buttons
        btn_bg = "#0d0b1a"
        btn_fg = "#c084fc"
        btn_font = ("Segoe UI Symbol", 14)
        tk.Button(self._win, text="◂◂", bg=btn_bg, fg=btn_fg,
                  font=btn_font, relief=tk.FLAT, cursor="hand2", bd=0,
                  activebackground="#100c1e", activeforeground="#ffffff",
                  command=self._app._prev).place(x=246, y=8, width=28, height=26)

        self._pp_btn = tk.Button(self._win, text="▶", bg=btn_bg, fg=btn_fg,
                                 font=btn_font, relief=tk.FLAT, cursor="hand2", bd=0,
                                 activebackground="#100c1e", activeforeground="#ffffff",
                                 command=self._app._toggle)
        self._pp_btn.place(x=278, y=8, width=28, height=26)

        tk.Button(self._win, text="▸▸", bg=btn_bg, fg=btn_fg,
                  font=btn_font, relief=tk.FLAT, cursor="hand2", bd=0,
                  activebackground="#100c1e", activeforeground="#ffffff",
                  command=self._app._next).place(x=310, y=8, width=28, height=26)

        tk.Button(self._win, text="♥", bg=btn_bg, fg="#f0a8c0",
                  font=btn_font, relief=tk.FLAT, cursor="hand2", bd=0,
                  activebackground="#100c1e", activeforeground="#ffffff",
                  command=self._app._like).place(x=278, y=38, width=28, height=26)

        # Restore button
        tk.Button(self._win, text="□", bg=btn_bg, fg="#8b7daf",
                  font=("Segoe UI", 12), relief=tk.FLAT, cursor="hand2", bd=0,
                  activebackground="#100c1e", activeforeground="#ffffff",
                  command=self.toggle).place(x=310, y=38, width=28, height=26)

        # Draggable: bind to canvas and labels
        for w in [self._win, self._canvas, self._cover_lbl,
                  self._name_lbl, self._artist_lbl]:
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

        # Right-click menu for restore/quit
        self._win.bind("<Button-3>", self._right_click)

        self._active = True
        self._refresh()
        self._start_sync()

    def _right_click(self, event):
        """Show right-click context menu."""
        menu = tk.Menu(self._win, tearoff=0, bg="#100c1e", fg="#e0d8f0",
                       font=("Microsoft YaHei", 10))
        menu.add_command(label="返回完整模式", command=self.toggle)
        menu.add_separator()
        menu.add_command(label="退出", command=self._app._tray_quit)
        menu.tk_popup(event.x_root, event.y_root)

    def _hide(self):
        """Hide mini player, show main window."""
        if self._win:
            self._win.destroy()
            self._win = None
        self._active = False
        self._app.root.deiconify()
        if hasattr(self, '_main_geo'):
            try:
                self._app.root.geometry(self._main_geo)
            except Exception:
                pass
        self._app.root.lift()
        self._app.root.focus_force()

    def _drag_start(self, event):
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root

    def _drag_move(self, event):
        if self._win is None:
            return
        dx = event.x_root - self._drag_start_x
        dy = event.y_root - self._drag_start_y
        x = self._win.winfo_x() + dx
        y = self._win.winfo_y() + dy
        self._win.geometry(f"+{x}+{y}")
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root

    def _refresh(self):
        """Update mini player display with current song info."""
        if not self._active or self._win is None:
            return
        try:
            if self._app.songs and self._app.idx < len(self._app.songs):
                song = self._app.songs[self._app.idx]
                name = song.get("songname", "")[:30]
                singers = " / ".join(s.get("name", "") for s in song.get("singer", []))[:30]
                self._name_lbl.config(text=name)
                self._artist_lbl.config(text=singers)
                # Update play/pause button
                is_playing = self._app._is_playing()
                self._pp_btn.config(text="⏸" if is_playing else "▶")

                # Try to show album cover (cached by albumid)
                aid = song.get("albumid", 0)
                if aid and aid != getattr(self, '_last_cover_aid', None):
                    self._last_cover_aid = aid
                    art_dir = self._app.ART_DIR if hasattr(self._app, 'ART_DIR') else os.path.join(HOME, "data", "covers")
                    cp = os.path.join(art_dir, f"ne_{aid}.jpg")
                    if os.path.exists(cp):
                        try:
                            from PIL import Image, ImageTk
                            img = Image.open(cp)
                            img = img.resize((48, 48), Image.LANCZOS)
                            self._cover_img = ImageTk.PhotoImage(img)
                            self._cover_lbl.config(image=self._cover_img, text="")
                        except Exception:
                            self._cover_lbl.config(text="♪", image="")
            else:
                self._name_lbl.config(text="等待播放")
                self._artist_lbl.config(text="")
                self._pp_btn.config(text="▶")
        except Exception:
            pass

    def _start_sync(self):
        """Periodic sync with main app state."""
        if not self._active:
            return
        self._refresh()
        # Schedule next sync via main app's root
        try:
            self._app.root.after(2000, self._start_sync)
        except Exception:
            pass

    @property
    def active(self):
        return self._active


# ── Desktop Lyrics Overlay ───────────────────────────────────────

class DesktopLyrics:
    """Transparent, always-on-top lyrics overlay window."""

    def __init__(self, app):
        self._app = app
        self._win = None
        self._active = False
        self._font_size = 28
        self._drag_x = 0
        self._drag_y = 0

    def toggle(self):
        if self._active:
            self._hide()
        else:
            self._show()

    def _show(self):
        if self._win is not None:
            return
        self._win = tk.Toplevel(self._app.root)
        self._win.overrideredirect(True)
        self._win.attributes('-topmost', True)
        self._win.attributes('-alpha', 0.85)

        # Transparent color trick: set a unique bg color and make it transparent
        self._transp_color = "#010203"
        self._win.configure(bg=self._transp_color)
        self._win.attributes('-transparentcolor', self._transp_color)

        # Canvas for lyrics
        self._canvas = tk.Canvas(self._win, bg=self._transp_color,
                                 highlightthickness=0, width=700, height=80)
        self._canvas.pack(fill=tk.BOTH, expand=True)

        # Current line text (bold, white)
        self._cur_text_id = self._canvas.create_text(
            350, 30, text="♪", font=("Microsoft YaHei", self._font_size, "bold"),
            fill="#ffffff", anchor=tk.CENTER, justify=tk.CENTER)
        # Next line text (dim)
        self._next_text_id = self._canvas.create_text(
            350, 62, text="", font=("Microsoft YaHei", self._font_size - 6),
            fill="#a898c8", anchor=tk.CENTER, justify=tk.CENTER)

        # Position: bottom-center of screen
        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        self._win.geometry(f"700x80+{(sw - 700) // 2}+{sh - 150}")

        # Draggable
        for w in [self._win, self._canvas]:
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

        # Scroll wheel to change font size
        self._win.bind("<MouseWheel>", self._on_scroll)

        # Right-click menu
        self._win.bind("<Button-3>", self._right_click)

        self._active = True
        self._sync_loop()

    def _hide(self):
        if self._win:
            self._win.destroy()
            self._win = None
        self._active = False

    def _drag_start(self, event):
        self._drag_x = event.x_root
        self._drag_y = event.y_root

    def _drag_move(self, event):
        if self._win is None:
            return
        dx = event.x_root - self._drag_x
        dy = event.y_root - self._drag_y
        x = self._win.winfo_x() + dx
        y = self._win.winfo_y() + dy
        self._win.geometry(f"+{x}+{y}")
        self._drag_x = event.x_root
        self._drag_y = event.y_root

    def _on_scroll(self, event):
        delta = 2 if event.delta > 0 else -2
        self._font_size = max(16, min(48, self._font_size + delta))
        self._update_font()

    def _update_font(self):
        if self._canvas:
            self._canvas.itemconfig(self._cur_text_id,
                                    font=("Microsoft YaHei", self._font_size, "bold"))
            self._canvas.itemconfig(self._next_text_id,
                                    font=("Microsoft YaHei", self._font_size - 6))

    def _right_click(self, event):
        menu = tk.Menu(self._win, tearoff=0, bg="#100c1e", fg="#e0d8f0",
                       font=("Microsoft YaHei", 10))
        menu.add_command(label=f"字号: {self._font_size}pt",
                         command=lambda: None)  # display only
        menu.add_command(label="放大 (滚轮↑)", command=lambda: self._change_size(2))
        menu.add_command(label="缩小 (滚轮↓)", command=lambda: self._change_size(-2))
        menu.add_separator()
        menu.add_command(label="关闭桌面歌词", command=self._hide)
        menu.tk_popup(event.x_root, event.y_root)

    def _change_size(self, delta):
        self._font_size = max(16, min(48, self._font_size + delta))
        self._update_font()

    def _sync_loop(self):
        """Update lyric text from app's current lyric state."""
        if not self._active or self._win is None:
            return
        try:
            app = self._app
            cur_text = ""
            next_text = ""
            if hasattr(app, 'lyrics') and app.lyrics:
                idx = getattr(app, '_lyric_idx', -1)
                if 0 <= idx < len(app.lyrics):
                    cur_text = app.lyrics[idx][1]
                if idx + 1 < len(app.lyrics):
                    next_text = app.lyrics[idx + 1][1]

            if not cur_text:
                if app.songs and app.idx < len(app.songs):
                    cur_text = app.songs[app.idx].get("songname", "♪")
                else:
                    cur_text = "♪"

            self._canvas.itemconfig(self._cur_text_id, text=cur_text)
            self._canvas.itemconfig(self._next_text_id, text=next_text)

            # Karaoke progress coloring: compute progress pct of current line
            self._draw_karaoke(cur_text, next_text)
        except Exception:
            pass
        try:
            self._app.root.after(400, self._sync_loop)
        except Exception:
            pass

    def _draw_karaoke(self, cur_text, next_text):
        """Draw current line with karaoke progress gradient."""
        if not self._canvas or not cur_text:
            return
        # Estimate progress within current lyric line
        try:
            app = self._app
            if not app.songs or app.idx >= len(app.songs):
                return
            if not app.lyrics or app._lyric_idx < 0:
                return

            dur_ms = app.songs[app.idx].get("duration", 300000) or 300000
            if app._is_playing():
                elapsed = time.time() - getattr(app, '_play_start', time.time()) + \
                          getattr(app, '_paused_elapsed', 0)
            else:
                elapsed = getattr(app, '_paused_elapsed', 0)
            elapsed_ms = int(elapsed * 1000)

            # Find current and next line timestamps
            cur_ms = app.lyrics[app._lyric_idx][0] if app._lyric_idx < len(app.lyrics) else 0
            if app._lyric_idx + 1 < len(app.lyrics):
                next_ms = app.lyrics[app._lyric_idx + 1][0]
            else:
                next_ms = dur_ms
            if next_ms > cur_ms:
                pct = min(1.0, max(0.0, (elapsed_ms - cur_ms) / (next_ms - cur_ms)))
            else:
                pct = 0.5

            # Draw filled portion (purple) + unfilled portion (white)
            c = self._canvas
            w = c.winfo_width() or 700
            cx = w // 2
            cy = 30
            # We can't split a single text string by color in tk Canvas.
            # Workaround: overlay two identical texts with a clipping rectangle.
            c.delete("karaoke")
            if pct > 0.01:
                # Estimate pixel width of the text
                text_width = len(cur_text) * self._font_size * 0.6  # rough CJK estimate
                filled_w = int(text_width * pct)
                clip_left = cx - text_width // 2
                # Draw colored overlay text with clip region
                # tk Canvas can't clip text... alternative:
                # Just color the whole text differently based on progress
                # Phase 1: simple brightness pulsing
                r = int(0xc0 + 0x3f * pct)
                g = int(0x84 + 0x3b * (1 - pct))
                b = int(0xfc + 0x03 * (1 - pct))
                color = f"#{r:02x}{g:02x}{b:02x}"
                c.itemconfig(self._cur_text_id, fill=color)
            else:
                c.itemconfig(self._cur_text_id, fill="#ffffff")
        except Exception:
            pass

    @property
    def active(self):
        return self._active
