#!/usr/bin/env python3
"""
Claude Desk Mascot — Floating interactive icon + AI DJ Voice
- Always-on-top, borderless window
- Drawn with Canvas (Claude-style face)
- Draggable, right-click menu, speech bubbles + TTS announcements
- Shows daily music recommendations
"""
import json
import os
import sys
import random
import re
import subprocess
import threading
import tkinter as tk
from datetime import datetime

HOME = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HOME, "data")
TODAY_FILE = os.path.join(DATA_DIR, "today.json")
TODAY_FOCUS_FILE = os.path.join(DATA_DIR, "today_focus.json")
NCM_API = "http://localhost:3000"

# ============================================================
# COLORS
# ============================================================
CLAUDE_BG = "#e8a850"      # Warm amber/orange (Claude theme)
CLAUDE_DARK = "#c07830"
CLAUDE_EYE = "#2d1810"
CLAUDE_WHITE = "#fff8f0"
BUBBLE_BG = "#2d2d44"
BUBBLE_TEXT = "#f0f0f0"
SHADOW = "#000000"


class ClaudeMascot:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Claude")

        # Window setup: borderless, always on top, transparent color
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "#abc123")

        # Position: bottom-right corner
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.size = 120
        x = screen_w - self.size - 40
        y = screen_h - self.size - 80
        self.root.geometry(f"{self.size}x{self.size}+{x}+{y}")

        # Canvas
        self.canvas = tk.Canvas(self.root, width=self.size, height=self.size,
                                 bg="#abc123", highlightthickness=0)
        self.canvas.pack()

        # State
        self.drag_x = 0
        self.drag_y = 0
        self.state = "idle"
        self.anim_id = None
        self.bubble_win = None
        self.songs = []
        self.voice_enabled = True  # TTS toggle
        self.is_speaking = False
        self.speaking_lock = threading.Lock()

        # Load songs
        self._load_songs()

        # Draw initial face
        self._draw_idle()

        # Bind events
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<Button-3>", self._on_right_click)
        self.canvas.bind("<Enter>", self._on_hover)
        self.canvas.bind("<Leave>", self._on_leave)

        # Start idle animation
        self._animate_idle()

        # Periodic recommendation popup
        self._schedule_bubble()

        # DJ intro on startup
        self.root.after(3000, self._dj_greeting)

    # ============================================================
    # DRAWING
    # ============================================================

    def _draw_idle(self):
        """Draw Claude face - idle state."""
        c = self.canvas
        c.delete("all")
        s = self.size
        m = 6  # margin

        # Shadow
        c.create_oval(m + 3, m + 3, s - m + 3, s - m + 3,
                      fill=SHADOW, stipple="gray50", outline="")

        # Main face circle
        c.create_oval(m, m, s - m, s - m, fill=CLAUDE_BG, outline=CLAUDE_DARK, width=2)

        # Inner lighter circle (face detail)
        inner_m = 18
        c.create_oval(inner_m, inner_m, s - inner_m, s - inner_m,
                      fill="", outline=CLAUDE_DARK, width=1)

        # Eyes
        eye_y = 38
        left_eye_x = 38
        right_eye_x = 80
        eye_r = 10

        # Left eye
        c.create_oval(left_eye_x - eye_r, eye_y - eye_r,
                      left_eye_x + eye_r, eye_y + eye_r,
                      fill=CLAUDE_WHITE, outline=CLAUDE_EYE, width=2)
        c.create_oval(left_eye_x - 4, eye_y - 4,
                      left_eye_x + 4, eye_y + 4,
                      fill=CLAUDE_EYE, outline="")

        # Right eye
        c.create_oval(right_eye_x - eye_r, eye_y - eye_r,
                      right_eye_x + eye_r, eye_y + eye_r,
                      fill=CLAUDE_WHITE, outline=CLAUDE_EYE, width=2)
        c.create_oval(right_eye_x - 4, eye_y - 4,
                      right_eye_x + 4, eye_y + 4,
                      fill=CLAUDE_EYE, outline="")

        # Smile
        smile_y = 65
        c.create_arc(35, smile_y, 83, smile_y + 28, start=0, extent=-180,
                     style=tk.ARC, outline=CLAUDE_EYE, width=2)

        # Cheek blush
        blush_color = "#e88870"
        c.create_oval(18, 55, 32, 65, fill=blush_color, outline="", stipple="gray50")
        c.create_oval(86, 55, 100, 65, fill=blush_color, outline="", stipple="gray50")

    def _draw_wink(self):
        """Draw winking face."""
        self._draw_idle()
        c = self.canvas
        # Overwrite left eye with wink
        eye_y = 38
        left_eye_x = 38
        c.create_line(left_eye_x - 10, eye_y, left_eye_x + 10, eye_y,
                      fill=CLAUDE_EYE, width=3)
        c.create_oval(left_eye_x - 5, eye_y - 5, left_eye_x + 5, eye_y + 5,
                      fill="", outline=CLAUDE_EYE, width=1)  # erase pupil

    def _draw_thinking(self):
        """Draw thinking face (looking up)."""
        self._draw_idle()
        c = self.canvas
        # Shift pupils up
        eye_y = 34
        c.create_oval(34, eye_y - 4, 42, eye_y + 4, fill=CLAUDE_EYE, outline="")
        c.create_oval(76, eye_y - 4, 84, eye_y + 4, fill=CLAUDE_EYE, outline="")

        # Thought lines
        for i, offset in enumerate([(50, 0), (65, -8), (80, -16)]):
            ox, oy = offset
            r = 3 - i * 0.5
            c.create_oval(ox - r, oy - r, ox + r, oy + r,
                          fill=CLAUDE_DARK, outline="")

    # ============================================================
    # ANIMATION
    # ============================================================

    def _animate_idle(self):
        """Subtle idle bobbing animation."""
        if self.state != "idle":
            self.anim_id = self.root.after(2000, self._animate_idle)
            return

        # Random micro-movement
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        dx = random.choice([-1, 0, 1, 1, 0, -1, 0, 0])
        dy = random.choice([-1, 0, 0, 1, 0, 0, 0, 0])
        self.root.geometry(f"+{x + dx}+{y + dy}")

        # Occasional blink
        if random.random() < 0.15:
            self._draw_wink()
            self.root.after(200, lambda: self._draw_idle() if self.state == "idle" else None)

        self.anim_id = self.root.after(1500, self._animate_idle)

    # ============================================================
    # SPEECH BUBBLE
    # ============================================================

    def _show_bubble(self, text, duration=8000):
        """Show a speech bubble with text."""
        if self.bubble_win:
            try:
                self.bubble_win.destroy()
            except Exception:
                pass

        bubble = tk.Toplevel(self.root)
        bubble.overrideredirect(True)
        bubble.attributes("-topmost", True)
        bubble.configure(bg="#abc123")
        bubble.attributes("-transparentcolor", "#abc123")

        # Position: above the mascot
        mx = self.root.winfo_x()
        my = self.root.winfo_y()

        # Calculate bubble width based on text
        font_size = 10
        max_chars = 35
        text_display = text[:max_chars] + ("..." if len(text) > max_chars else "")
        char_width = 7
        bubble_w = max(140, min(300, len(text_display) * char_width + 40))
        bubble_h = 50

        bubble.geometry(f"{bubble_w}x{bubble_h}+{mx - 90}+{my - 55}")

        # Bubble canvas
        bc = tk.Canvas(bubble, width=bubble_w, height=bubble_h,
                       bg="#abc123", highlightthickness=0)
        bc.pack()

        # Draw rounded bubble
        r = 10
        bc.create_rounded = lambda x1, y1, x2, y2, r, **kw: bc.create_polygon(
            x1 + r, y1, x2 - r, y1, x2, y1 + r, x2, y2 - r,
            x2 - r, y2, x1 + r, y2, x1, y2 - r, x1, y1 + r,
            smooth=True, **kw)

        bc.create_rounded(2, 2, bubble_w - 2, bubble_h - 12, r,
                          fill=BUBBLE_BG, outline=BUBBLE_BG)

        # Draw triangle pointer
        tri_x = bubble_w // 2
        bc.create_polygon(tri_x - 8, bubble_h - 14, tri_x + 8, bubble_h - 14,
                          tri_x, bubble_h, fill=BUBBLE_BG, outline="")

        # Text
        bc.create_text(bubble_w // 2, (bubble_h - 14) // 2,
                       text=text_display, font=("Microsoft YaHei", font_size),
                       fill=BUBBLE_TEXT, width=bubble_w - 20)

        self.bubble_win = bubble

        # Auto-dismiss
        def dismiss():
            try:
                bubble.destroy()
            except Exception:
                pass
            if self.bubble_win == bubble:
                self.bubble_win = None

        bubble.after(duration, dismiss)

    def _schedule_bubble(self):
        """Periodically show recommendation bubbles."""
        if self.songs:
            song = random.choice(self.songs)
            singers = " / ".join(s.get("name", "") for s in song.get("singer", []))
            text = f"🎵 Try: {song['songname'][:25]} — {singers[:20]}"
            self._show_bubble(text, duration=10000)

        # Schedule next bubble: 25-45 seconds
        delay = random.randint(25000, 45000)
        self.root.after(delay, self._schedule_bubble)

    # ============================================================
    # INTERACTION
    # ============================================================

    def _on_click(self, event):
        """Left click: show recommendation summary."""
        if self.songs:
            count = len(self.songs)
            # Pick top 3
            top = self.songs[:3]
            lines = [f"Today's Top {count} Picks:"]
            for i, s in enumerate(top, 1):
                singers = " / ".join(x.get("name", "") for x in s.get("singer", []))
                lines.append(f"  {i}. {s['songname'][:20]} — {singers[:15]}")
            self._show_bubble("\n".join(lines), duration=10000)
        else:
            self._show_bubble("No recommendations yet!\nClick Refresh in the player.", duration=5000)

    def _on_drag(self, event):
        """Drag to move mascot."""
        x = self.root.winfo_x() + event.x - self.drag_x
        y = self.root.winfo_y() + event.y - self.drag_y
        self.root.geometry(f"+{x}+{y}")

    def _on_right_click(self, event):
        """Right click: context menu."""
        menu = tk.Menu(self.root, tearoff=0, bg="#2d2d44", fg="#f0f0f0",
                       activebackground="#e94560", activeforeground="#ffffff",
                       font=("Microsoft YaHei", 9))

        if self.songs:
            # Show top 5 in menu
            for song in self.songs[:5]:
                singers = " / ".join(s.get("name", "") for s in song.get("singer", []))
                label = f"♪ {song['songname'][:25]} — {singers[:15]}"
                songid = str(song.get("songid", ""))
                menu.add_command(label=label,
                                 command=lambda s=songid: self._play_song(s))

        menu.add_separator()
        voice_label = "🔊 Voice: ON" if self.voice_enabled else "🔇 Voice: OFF"
        menu.add_command(label=voice_label, command=self.toggle_voice)
        menu.add_command(label="🔄 Refresh Recommendations", command=self._refresh_recs)
        menu.add_command(label="🎵 Open Player", command=self._open_player)
        menu.add_separator()
        menu.add_command(label="💤 Hide Mascot", command=self.root.withdraw)
        menu.add_command(label="✖ Exit", command=self._exit_all)

        menu.post(event.x_root, event.y_root)

    def _on_hover(self, event):
        """Mouse enter: slight scale up effect."""
        self.canvas.configure(cursor="hand2")

    def _on_leave(self, event):
        """Mouse leave."""
        self.canvas.configure(cursor="")

    # ============================================================
    # ACTIONS
    # ============================================================

    def _play_song(self, songid):
        """Play song via local NetEase API URL."""
        import webbrowser
        import requests
        try:
            r = requests.get(f"{NCM_API}/song/url/v1", params={"id": songid, "level": "standard"}, timeout=10)
            data = r.json().get("data", [{}])
            url = data[0].get("url") if data else None
            if url:
                webbrowser.open(url)
            else:
                # Fallback: search on NetEase web
                song_obj = next((s for s in self.songs if str(s.get("songid")) == str(songid)), None)
                name = song_obj.get("songname", "") if song_obj else ""
                webbrowser.open(f"https://music.163.com/#/search/m/?s={name}")
        except Exception:
            webbrowser.open(f"https://music.163.com")

    def _refresh_recs(self):
        """Trigger recommendation refresh via engine."""
        self._show_bubble("Generating fresh picks... 🤔", duration=5000)
        self.state = "thinking"
        self._draw_thinking()

        def run():
            import subprocess
            engine_path = os.path.join(HOME, "engine.py")
            try:
                subprocess.run([sys.executable, engine_path],
                               cwd=HOME, capture_output=True, text=True, timeout=120)
                self.root.after(0, self._refresh_done)
            except Exception as e:
                self.root.after(0, lambda: self._refresh_error(str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _refresh_done(self):
        self._load_songs()
        self.state = "idle"
        self._draw_idle()
        self._show_bubble(f"Done! {len(self.songs)} fresh picks ready! 🎉", duration=6000)

    def _refresh_error(self, msg):
        self.state = "idle"
        self._draw_idle()
        self._show_bubble(f"Oops! Refresh failed: {msg[:30]}...", duration=5000)

    def _open_player(self):
        """Bring the main music player to front, or launch if not running."""
        # Try to find and activate existing player window
        try:
            ps = '''
                Add-Type @\"
                    using System;
                    using System.Runtime.InteropServices;
                    public class Win32 {
                        [DllImport(\"user32.dll\")]
                        public static extern bool SetForegroundWindow(IntPtr hWnd);
                        [DllImport(\"user32.dll\")]
                        public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
                    }
\"@
                $proc = Get-Process python | Where-Object {$_.MainWindowTitle -like \"*Claude Music*\"} | Select -First 1
                if ($proc) {
                    [Win32]::ShowWindow($proc.MainWindowHandle, 9)
                    [Win32]::SetForegroundWindow($proc.MainWindowHandle)
                }
            '''
            result = subprocess.run(['powershell', '-Command', ps],
                                     capture_output=True, text=True, timeout=8)
            if result.returncode == 0:
                return  # Successfully brought to front
        except Exception:
            pass
        # Fallback: launch new player
        app_path = os.path.join(HOME, "app.py")
        subprocess.Popen([sys.executable, app_path], cwd=HOME)

    def _exit_all(self):
        """Close mascot and player."""
        if self.anim_id:
            self.root.after_cancel(self.anim_id)
        self.root.destroy()
        sys.exit(0)

    # ============================================================
    # DATA
    # ============================================================

    def _load_songs(self):
        """Load today's songs for bubble recommendations."""
        self.songs = []
        # Load both modes for richer DJ content
        for fname in ["today.json", "today_focus.json"]:
            fpath = os.path.join(DATA_DIR, fname)
            if os.path.exists(fpath):
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.songs.extend(data.get("songs", []))

    # ============================================================
    # DJ VOICE (TTS)
    # ============================================================

    @staticmethod
    def _sanitize_tts(text):
        """Escape text for PowerShell TTS string."""
        return text.replace('"', "'").replace('$', ' ').replace('`', ' ').replace('\n', ' ')[:200]

    def _tts_speak(self, text, rate=-1):
        """Speak text using Windows TTS in background thread."""
        if not self.voice_enabled:
            return
        safe = self._sanitize_tts(text)
        # Choose voice: Zira for English, Huihui for Chinese
        has_chinese = bool(re.search(r'[一-鿿]', safe))
        voice = "Microsoft Huihui Desktop" if has_chinese else "Microsoft Zira Desktop"

        def _speak():
            with self.speaking_lock:
                self.is_speaking = True
            try:
                ps = f'''
                    Add-Type -AssemblyName System.Speech
                    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
                    $synth.SelectVoice("{voice}")
                    $synth.Rate = {rate}
                    $synth.Speak("{safe}")
                '''
                self.root.after(0, lambda: self._draw_speaking(True))
                subprocess.run(['powershell', '-Command', ps],
                               capture_output=True, timeout=30)
            except Exception:
                pass
            finally:
                with self.speaking_lock:
                    self.is_speaking = False
                self.root.after(0, lambda: self._draw_speaking(False))

        threading.Thread(target=_speak, daemon=True).start()

    def _announce_song(self, song):
        """DJ announcement for a song."""
        name = song.get("songname", "this track")
        singers = " and ".join(s.get("name", "") for s in song.get("singer", [])[:2])
        scripts = [
            f"Now spinning: {name} by {singers}.",
            f"Up next: {name} from {singers}. Enjoy.",
            f"Let's get into {name} by {singers}.",
            f"Here's a pick for you: {name} by {singers}.",
        ]
        text = random.choice(scripts)
        self._show_bubble(f"🎙 {text}", duration=5000)
        self._tts_speak(text)

    def _dj_greeting(self):
        """Startup DJ greeting."""
        greetings = [
            "Hey there! I'm Claude, your AI DJ. I've got fresh picks ready for you today.",
            "Welcome back! Claude here. Let me queue up some music for you.",
            "Good to see you! Ready to discover some new music?",
        ]
        text = random.choice(greetings)
        self._show_bubble(f"👋 {text[:60]}...", duration=6000)
        self._tts_speak(text)

    def _dj_interlude(self):
        """Random DJ commentary between songs."""
        if not self.songs:
            return
        song = random.choice(self.songs)
        name = song.get("songname", "this one")
        singers = ", ".join(s.get("name", "") for s in song.get("singer", [])[:2])
        comments = [
            f"By the way, have you heard {name} by {singers}? It's in your recommendations today.",
            f"Fun fact: {singers} has a track called {name} that you might like.",
            f"Just saying — {name} is fire. Check out {singers}.",
            f"Here's a thought: {name} by {singers} would sound great right now.",
        ]
        text = random.choice(comments)
        self._show_bubble(f"💬 {text[:70]}", duration=6000)
        self._tts_speak(text, rate=-2)

    def _draw_speaking(self, active):
        """Animate mouth when speaking."""
        if active:
            self.state = "speaking"
            # Draw open mouth
            c = self.canvas
            c.delete("mouth")
            c.create_oval(40, 60, 80, 80, fill=CLAUDE_EYE, outline="", tags="mouth")
            c.create_oval(50, 65, 70, 75, fill=CLAUDE_WHITE, outline="", tags="mouth")
        else:
            self.state = "idle"
            self.canvas.delete("mouth")
            self._draw_idle()

    def toggle_voice(self):
        """Toggle TTS voice on/off."""
        self.voice_enabled = not self.voice_enabled
        state = "ON" if self.voice_enabled else "OFF"
        self._show_bubble(f"DJ Voice: {state}", duration=3000)
        if self.voice_enabled:
            self._tts_speak("Voice enabled. I'll keep you company.")

    def run(self):
        self.root.mainloop()


def main():
    mascot = ClaudeMascot()
    mascot.run()


if __name__ == "__main__":
    main()
