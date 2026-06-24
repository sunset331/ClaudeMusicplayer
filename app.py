#!/usr/bin/env python3
"""
Claude Music Player - NetEase Cloud Music Edition
- Auto-plays daily picks on startup
- Rate songs (like/skip) to improve future picks
- One-click add to NetEase playlist
- Dark theme, album art, desktop mascot
"""
import json
import os
import sys
import time
import threading
import subprocess
import atexit
import re
import random as _rnd
import signal
import tkinter as tk
from tkinter import ttk
from datetime import datetime

import requests

import chat
import engine as eng

from api.ncm_client import _session, load_cookie, ncm

from tray import SystemTray, TaskbarHelper, show_toast
try:
    from hotkeys import GlobalHotkeyListener
except ImportError:
    GlobalHotkeyListener = None
from mini_player import MiniPlayer, DesktopLyrics
from smart_dj import SmartDJ, MoodRadio, detect_mood
from report import handle_command, generate_monthly_report

HOME = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HOME, "data")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
SESSION_FILE = os.path.join(DATA_DIR, "session.json")
ART_DIR = os.path.join(DATA_DIR, "covers")
LOGIN_FILE = os.path.join(DATA_DIR, "ncm_cookie.json")

FFPLAY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin", "ffplay.exe")

os.makedirs(ART_DIR, exist_ok=True)

# ============================================================
# DESIGN SYSTEM v2 — Cyberpunk Dashboard (萌系赛博朋克)
# Three-layer token architecture: primitives → semantic → component
# Built with frontend-design + ui-ux-pro-max skill guidance
# ============================================================

# ── Spacing scale: 4px grid base (ui-ux-pro-max §5) ──
class Sp:
    XS = 2
    SM = 4
    MD = 8
    LG = 16

# ── Layer 1: Color primitives (never reference directly in components) ──
class _P:
    void = "#06060f"        # deepest blue-black bg
    abyss = "#0d0b1a"       # panel surface
    vault = "#100c1e"       # elevated card surface
    lavender = "#c084fc"    # primary accent (aurora purple)
    blush = "#f0a8c0"       # warm accent (soft pink)
    mint = "#4ecca3"        # status ok green
    wave = "#64b4ff"        # cool accent blue
    flame = "#ff8a80"       # danger/warning red
    white = "#ffffff"
    silk = "#e0d8f0"        # body text (off-white purple)
    vapor = "#a898c8"       # secondary text (AA 4.5:1 on void)
    wisp = "#8b7daf"        # muted text (AA 5.3:1 on void, ↑ from #605080)
    ash = "#181030"         # progress bar track
    ash_border = "#1a1030"  # subtle separators

# ── Layer 2: Semantic tokens — use these in ALL components ──
class C:
    # Background surfaces
    BG = _P.void
    BG_CARD = _P.vault
    # Text (contrast-verified on C.BG at AA 4.5:1+)
    TX = _P.silk               # body text       — ≈15:1
    TX_HI = _P.white           # primary text    — ≈21:1
    TX_MD = _P.vapor           # secondary text  — ≈4.5:1
    TX_LO = _P.wisp            # muted text      — ≈5.3:1
    # Accents
    AC = _P.lavender           # primary accent (selection, progress)
    AC_WARM = _P.blush         # warm accent (likes, 沧溟, feminine)
    AC_COOL = _P.wave          # cool accent (info, links)
    # Status
    OK = _P.mint               # success / green
    WARN = _P.flame            # warning / error / skip
    # Surfaces
    SURF_TRACK = _P.ash        # progress bar background
    SURF_BORDER = _P.ash_border  # subtle dividers

# ── Layer 3: Component tokens ──
class Cp:
    # Capsule action buttons
    BTN_LIKE_BG = _P.ash_border  # same tone as subtle border
    BTN_LIKE_HOVER = "#2a1848"
    BTN_SKIP_BG = "#1a1028"
    BTN_SKIP_HOVER = "#2a1838"
    BTN_PL_BG = "#101828"
    BTN_PL_HOVER = "#182838"
    # Nav buttons
    BTN_NAV_BG = _P.void
    BTN_NAV_HOVER = _P.vault
    BTN_NAV_FG = _P.blush
    # Bottom bar
    BAR_FG = _P.wisp
    BAR_BTN_HOVER_BG = _P.vault
    BAR_BTN_HOVER_FG = _P.blush

# ── Backwards-compatible aliases (deprecated, prefer C.* / Cp.*) ──
BG_MAIN = C.BG
BG_CARD = C.BG_CARD
BG_SEL = C.AC
FG = C.TX
FG_BRIGHT = C.TX_HI
FG2 = C.TX_MD
FG_DIM = C.TX_LO
FG_ACC = C.AC_WARM
FG_OK = C.OK
FG_BLUE = C.AC_COOL

load_cookie()


class MusicPlayer:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Claude Music · 每日推荐")
        self.root.geometry("1200x780")
        self.root.minsize(1000, 600)
        self.root.configure(bg=BG_MAIN)

        self.songs = []
        self.idx = 0
        self.mode = "rap"
        # Restore previous session mode if available
        prev = self._load_session()
        if prev:
            self.mode = prev.get("mode", "rap")
            self._epsilon = prev.get("epsilon", 0.15)
        self.ffplay = None
        global _cleanup_ffplay
        _cleanup_ffplay = self._stop_ffplay
        self.playlist_rap = None
        self.playlist_mixed = None
        self.playlist_focus = None
        self.candidates = []
        self._candidates_lock = threading.Lock()
        self.play_count = 0
        self._simi_queue = []
        self._simi_queue_lock = threading.Lock()
        self._volume = 1.0  # 0.0 - 1.5
        self._muted = False
        self._prev_volume = 1.0
        self._epsilon = 0.15  # bandit exploration rate
        self._chat_history = []
        self._song_request_in_flight = False  # guard: prevent [切歌] race during song search
        self._chat_history_lock = threading.Lock()
        self._reload_pending = False  # anti-reentry guard for _reload_list

        # ── New modules (Phase 1-3) ──
        self.ART_DIR = ART_DIR
        self._mini_player = MiniPlayer(self)
        self._desktop_lyrics = DesktopLyrics(self)
        self._smart_dj = SmartDJ(self)
        self._mood_radio = MoodRadio(self)

        self._build()

        # Keyboard shortcuts
        self.root.bind("<space>",
                       lambda e: self._toggle() if self.root.focus_get() != self.chat_input else None)
        self.root.bind("<Control-Left>", lambda e: self._prev())
        self.root.bind("<Control-Right>", lambda e: self._next())
        self.root.bind("<Control-l>", lambda e: self._like())
        self.root.bind("<Control-s>", lambda e: self._skip())
        self.root.bind("<Control-f>", lambda e: self.chat_input.focus_set())
        self.root.bind("<Control-a>", lambda e: self._add_pl())
        # Volume: +/- keys (scale slider value = volume * 100)
        self.root.bind("<plus>",
                       lambda e: self._set_volume(min(150, int((self._volume + 0.05) * 100))))
        self.root.bind("<minus>",
                       lambda e: self._set_volume(max(0, int((self._volume - 0.05) * 100))))
        self.root.bind("<equal>",
                       lambda e: self._set_volume(min(150, int((self._volume + 0.05) * 100))))
        # Seek: left/right arrows
        self.root.bind("<Left>", lambda e: self._key_seek(-0.05))
        self.root.bind("<Right>", lambda e: self._key_seek(0.05))
        # Mini player / desktop lyrics toggle
        self.root.bind("<Control-m>", lambda e: self._mini_player.toggle())
        self.root.bind("<Control-d>", lambda e: self._desktop_lyrics.toggle())

        # ── System tray + global hotkeys + taskbar ──
        self._taskbar = None  # initialized after window maps
        self.tray = SystemTray(self)
        self.tray.start()
        self.root.after(500, self._init_taskbar)
        if GlobalHotkeyListener is not None:
            self.hotkey_listener = GlobalHotkeyListener(self)
            self.hotkey_listener.start()
        else:
            self.hotkey_listener = None

        self.root.after(100, self._init_data)
        self.root.after(200, lambda: self.mode_btn.config(
            text={"rap": "RAP 模式", "mixed": "混合模式", "focus": "专注模式"}.get(self.mode, self.mode)))
        self.root.after(300, self._restore_mood_radio)  # restore after init_data
        self.root.after(500, self._check_login)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._watch_playback()

    # ============================================================
    # UI
    # ============================================================

    def _build(self):
        """Asymmetric cyberpunk dashboard with resizable lyrics/chat split."""
        # ── Top light bar (2px gradient: purple → pink → blue) ──
        top_bar = tk.Canvas(self.root, bg=BG_MAIN, height=2, highlightthickness=0)
        top_bar.pack(fill=tk.X, side=tk.TOP)
        top_bar.create_rectangle(0, 0, 400, 2, fill=BG_SEL, outline="")
        top_bar.create_rectangle(400, 0, 800, 2, fill=FG_ACC, outline="")
        top_bar.create_rectangle(800, 0, 1200, 2, fill=FG_BLUE, outline="")

        pw = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=BG_MAIN, sashwidth=2)
        pw.pack(fill=tk.BOTH, expand=True)

        self.left = tk.Frame(pw, bg=BG_MAIN, width=200)
        pw.add(self.left, stretch="never")
        self._build_left()

        # Center+Right splitter: lyrics area ↔ chat area (user-draggable)
        split = tk.PanedWindow(pw, orient=tk.HORIZONTAL, bg=BG_MAIN, sashwidth=3)
        pw.add(split, stretch="always")

        self.center = tk.Frame(split, bg=BG_MAIN, width=500)
        split.add(self.center, stretch="always")
        self._build_center()

        self.right = tk.Frame(split, bg=BG_MAIN, width=250)
        split.add(self.right, stretch="never")
        self._build_right()

        self._build_bar()

    def _card(self, parent, **kw):
        """Helper: frame with card styling — prefer this over inline tk.Frame(bg=BG_CARD)."""
        return tk.Frame(parent, bg=C.BG_CARD, **kw)

    def _build_left(self):
        """Left column: song info + taste radar + session stats + queue."""
        # Header
        tk.Label(self.left, text="CLAUDE//MUSIC", font=("Consolas", 14, "bold"),
                 fg=FG_BRIGHT, bg=BG_MAIN).pack(pady=(12, 2), padx=10, anchor=tk.W)
        tk.Label(self.left, text="赛博朋克版", font=("Microsoft YaHei", 10),
                 fg=FG_BLUE, bg=BG_MAIN).pack(pady=(0, 8), padx=10, anchor=tk.W)

        # Song info — fixed-height container to prevent layout shift on click
        info_frame = tk.Frame(self.left, bg=BG_MAIN, height=72)
        info_frame.pack(fill=tk.X, pady=(4, 0), padx=8)
        info_frame.pack_propagate(False)
        self.name_lbl = tk.Label(info_frame, text="等待播放",
                                 font=("Microsoft YaHei", 14, "bold"),
                                 fg=FG_BRIGHT, bg=BG_MAIN, wraplength=180,
                                 justify=tk.CENTER)
        self.name_lbl.pack(anchor=tk.S, pady=(4, 0))
        self.art_lbl = tk.Label(info_frame, text="",
                                font=("Microsoft YaHei", 12),
                                fg=FG_ACC, bg=BG_MAIN)
        self.art_lbl.pack(anchor=tk.N, pady=(0, 2))

        # Tags row
        self.tag_frame = tk.Frame(self.left, bg=BG_MAIN)
        self.tag_frame.pack(pady=(2, 6))
        self.tag_genre = tk.Label(self.tag_frame, text="", font=("Microsoft YaHei", 10),
                                  fg=FG_ACC, bg=BG_CARD, padx=6, pady=2)
        self.tag_genre.pack(side=tk.LEFT, padx=2)
        self.tag_year = tk.Label(self.tag_frame, text="", font=("Microsoft YaHei", 10),
                                 fg=FG_BLUE, bg=BG_CARD, padx=6, pady=2)
        self.tag_year.pack(side=tk.LEFT, padx=2)

        # Score breakdown (explainable recommendations)
        tk.Label(self.left, text="▸ 推荐理由", font=("Microsoft YaHei", 10),
                 fg=FG_ACC, bg=BG_MAIN).pack(pady=(Sp.MD, Sp.XS), padx=Sp.LG, anchor=tk.W)
        self._score_breakdown_frame = tk.Frame(self.left, bg=BG_MAIN)
        self._score_breakdown_frame.pack(fill=tk.X, padx=12, pady=(1, 4))
        self._score_bars = {}  # label → canvas
        self._score_labels = {}  # label → value label
        self._build_score_breakdown()

        # Taste radar
        tk.Label(self.left, text="▸ 音乐品味", font=("Microsoft YaHei", 10),
                 fg=FG_ACC, bg=BG_MAIN).pack(pady=(Sp.MD, 3), padx=Sp.LG, anchor=tk.W)
        self._taste_bars = tk.Frame(self.left, bg=BG_MAIN)
        self._taste_bars.pack(fill=tk.X, padx=12, pady=(0, 6))
        self._build_taste_bars()

        # Session stats
        sf = tk.Frame(self.left, bg=BG_CARD)
        sf.pack(fill=tk.X, padx=10, pady=(2, 4))
        self.stat_played = tk.Label(sf, text="0", font=("Consolas", 26, "bold"), fg=FG_ACC, bg=BG_CARD)
        self.stat_played.pack(side=tk.LEFT, expand=True)
        tk.Label(sf, text="已播", font=("Microsoft YaHei", 10), fg=FG_DIM, bg=BG_CARD).pack(side=tk.LEFT, expand=True)
        self.stat_liked = tk.Label(sf, text="0", font=("Consolas", 26, "bold"), fg=FG_OK, bg=BG_CARD)
        self.stat_liked.pack(side=tk.LEFT, expand=True)
        tk.Label(sf, text="喜欢", font=("Microsoft YaHei", 10), fg=FG_DIM, bg=BG_CARD).pack(side=tk.LEFT, expand=True)
        self.stat_skip = tk.Label(sf, text="0", font=("Consolas", 26, "bold"), fg=C.WARN, bg=BG_CARD)
        self.stat_skip.pack(side=tk.LEFT, expand=True)
        tk.Label(sf, text="跳过", font=("Microsoft YaHei", 10), fg=FG_DIM, bg=BG_CARD).pack(side=tk.LEFT, expand=True)

        # Mini queue list
        qh = tk.Frame(self.left, bg=BG_MAIN)
        qh.pack(fill=tk.X, padx=12, pady=(6, 2))
        tk.Label(qh, text="▸ 播放队列", font=("Microsoft YaHei", 10),
                 fg=FG_ACC, bg=BG_MAIN).pack(side=tk.LEFT)
        self._show_played = True
        self._show_played_btn = tk.Label(qh, text="隐藏已播", font=("Microsoft YaHei", 9),
                                          fg=FG_DIM, bg=BG_MAIN, cursor="hand2")
        self._show_played_btn.pack(side=tk.RIGHT)
        self._show_played_btn.bind("<Button-1>", self._toggle_show_played)
        self._show_played_btn.bind("<Enter>", lambda e: self._show_played_btn.config(fg=FG_ACC))
        self._show_played_btn.bind("<Leave>", lambda e: self._show_played_btn.config(fg=FG_DIM))
        st = ttk.Style()
        st.theme_use("clam")
        st.configure("Treeview", background=BG_CARD, foreground=FG,
                     fieldbackground=BG_CARD, borderwidth=0,
                     font=("Microsoft YaHei", 12))
        st.configure("Treeview.Heading", background=BG_MAIN, foreground=FG_DIM,
                     font=("Microsoft YaHei", 10), borderwidth=0)
        st.map("Treeview", background=[("selected", BG_SEL)],
               foreground=[("selected", "#fff")])
        # Tag for played rows: dimmed
        st.configure("played", foreground=FG_DIM)

        # Tree + scrollbar container
        tree_frame = tk.Frame(self.left, bg=BG_MAIN)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 4))

        cols = ("rank", "name", "artist", "score")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                  selectmode="browse", height=8)
        self.tree.heading("rank", text="#")
        self.tree.heading("name", text="歌名")
        self.tree.heading("artist", text="艺人")
        self.tree.heading("score", text="★")
        self.tree.column("rank", width=28, anchor=tk.CENTER, stretch=False)
        self.tree.column("name", width=130, anchor=tk.W, stretch=True)
        self.tree.column("artist", width=90, anchor=tk.W, stretch=True)
        self.tree.column("score", width=36, anchor=tk.CENTER, stretch=False)
        self.tree.tag_configure("played_row", foreground=FG_DIM)
        self.tree.tag_configure("now_playing", background=BG_SEL, foreground="#fff")

        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._sel)
        self.tree.bind("<Double-1>", self._dbl)
        self.tree.bind("<Return>", self._dbl)

        # ── Play History Drawer (collapsible) ──
        self._hist_open = False
        self._hist_btn = tk.Label(self.left, text="▸ 播放历史 ▸", font=("Microsoft YaHei", 9),
                                   fg=FG_DIM, bg=BG_MAIN, cursor="hand2")
        self._hist_btn.pack(pady=(2, 2), padx=12, anchor=tk.W)
        self._hist_btn.bind("<Button-1>", self._toggle_history)
        self._hist_btn.bind("<Enter>", lambda e: self._hist_btn.config(fg=FG_ACC))
        self._hist_btn.bind("<Leave>", lambda e: self._hist_btn.config(
            fg=FG_ACC if self._hist_open else FG_DIM))

        # History treeview (initially hidden)
        hcols = ("h_name", "h_artist", "h_status")
        self.hist_tree = ttk.Treeview(self.left, columns=hcols, show="headings",
                                       selectmode="browse", height=4)
        self.hist_tree.heading("h_name", text="歌名")
        self.hist_tree.heading("h_artist", text="艺人")
        self.hist_tree.heading("h_status", text="")
        self.hist_tree.column("h_name", width=120, anchor=tk.W, stretch=True)
        self.hist_tree.column("h_artist", width=80, anchor=tk.W, stretch=True)
        self.hist_tree.column("h_status", width=30, anchor=tk.CENTER, stretch=False)
        self.hist_tree.bind("<Double-1>", self._replay_from_history)

    def _toggle_show_played(self, event=None):
        """Toggle show/hide played songs in the queue."""
        self._show_played = not self._show_played
        self._show_played_btn.config(text="隐藏已播" if self._show_played else "显示已播")
        self._reload_list(resort=False)

    def _toggle_history(self, event=None):
        """Toggle play history drawer visibility."""
        self._hist_open = not self._hist_open
        if self._hist_open:
            self.hist_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 4))
            self._hist_btn.config(text="▸ 播放历史 ▾")
            self._refresh_history()
        else:
            self.hist_tree.pack_forget()
            self._hist_btn.config(text="▸ 播放历史 ▸")

    def _add_to_history(self, song, action):
        """Add a song to the play history treeview."""
        singers = " / ".join(s.get("name", "") for s in song.get("singer", []))
        if action == "like":
            status = "♥"
        elif action == "skip":
            status = "»"
        else:
            status = ""  # neutral played
        self.hist_tree.insert("", 0, values=(song.get("songname", ""), singers, status))
        # Keep last 50 items
        kids = self.hist_tree.get_children()
        for kid in kids[50:]:
            self.hist_tree.delete(kid)

    def _refresh_history(self):
        """Reload history from history.json song_plays."""
        self.hist_tree.delete(*self.hist_tree.get_children())
        h = {}
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, encoding="utf-8") as f:
                    h = json.load(f)
            except Exception:
                pass
        for sid, entry in sorted(
            h.get("song_plays", {}).items(),
            key=lambda x: x[1].get("last_played", ""), reverse=True):
            status = ""
            if entry.get("liked"):
                status = "♥"
            elif entry.get("skipped"):
                status = "»"
            name = entry.get("name", sid)[:30]
            artist = entry.get("artist", "")[:20]
            self.hist_tree.insert("", tk.END, values=(name, artist, status))

    def _replay_from_history(self, event=None):
        """Double-click a history item to jump to it in the queue."""
        sel = self.hist_tree.selection()
        if not sel:
            return
        vals = self.hist_tree.item(sel[0], "values")
        if vals:
            song_name = vals[0]
            for i, s in enumerate(self.songs):
                if s.get("songname", "") == song_name:
                    self._play(i)
                    return

    def _build_taste_bars(self):
        """Placeholder taste bars (updated in _update_stats)."""
        for w in self._taste_bars.winfo_children():
            w.destroy()
        for i, (name, val) in enumerate([("—", 0.0), ("—", 0.0), ("—", 0.0)]):
            row = tk.Frame(self._taste_bars, bg=BG_MAIN)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=name[:10], font=("Microsoft YaHei", 10),
                     fg=FG2, bg=BG_MAIN, width=8, anchor=tk.W).pack(side=tk.LEFT)
            bar = tk.Canvas(row, bg=BG_MAIN, height=10, highlightthickness=0, width=80)
            bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
            bar.create_rectangle(0, 0, int(val * 80), 10, fill=BG_SEL, outline="")
            tk.Label(row, text=f"{val:.2f}", font=("Consolas", 10),
                     fg=FG_DIM, bg=BG_MAIN).pack(side=tk.RIGHT)

    def _build_score_breakdown(self):
        """Build the score breakdown panel (explainable recommendations)."""
        for w in self._score_breakdown_frame.winfo_children():
            w.destroy()
        self._score_bars.clear()
        self._score_labels.clear()
        # Show placeholder bars for 6 components
        components = [
            ("历史反馈", "track_feedback", FG_OK),
            ("标签匹配", "tag_match", FG_BLUE),
            ("艺人匹配", "artist_baseline", BG_SEL),
            ("AI 信号", "chat_signal", FG_ACC),
            ("探索奖励", "exploration", FG_ACC),
            ("来源质量", "source_quality", FG_BLUE),
            ("时长偏好", "duration", FG2),
        ]
        for label, key, color in components:
            row = tk.Frame(self._score_breakdown_frame, bg=BG_MAIN)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label, font=("Microsoft YaHei", 9),
                     fg=FG2, bg=BG_MAIN, width=8, anchor=tk.W).pack(side=tk.LEFT)
            bar = tk.Canvas(row, bg=BG_MAIN, height=8, highlightthickness=0, width=60)
            bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)
            bar.create_rectangle(0, 0, 0, 8, fill=color, outline="", tags="fill")
            self._score_bars[key] = bar
            val_lbl = tk.Label(row, text="—", font=("Consolas", 8),
                               fg=FG_DIM, bg=BG_MAIN, width=6, anchor=tk.E)
            val_lbl.pack(side=tk.RIGHT)
            self._score_labels[key] = val_lbl

    def _update_score_breakdown(self, song):
        """Update the score breakdown bars from song._score_breakdown."""
        bd = song.get("_score_breakdown") if song else None
        if not bd:
            for bar in self._score_bars.values():
                bar.coords("fill", 0, 0, 0, 8)
            for lbl in self._score_labels.values():
                lbl.config(text="—")
            return
        bar_width = 60
        # Scale: max component weight ~0.35, map to bar_width
        max_w = 0.35
        for key, bar in self._score_bars.items():
            val = bd.get(key, 0)
            w = max(0, int(val / max_w * bar_width))
            bar.coords("fill", 0, 0, w, 8)
        for key, lbl in self._score_labels.items():
            lbl.config(text=f"{bd.get(key, 0):.2f}")

    def _build_center(self):
        """Center column: album-art blur bg + lyrics overlay + controls."""
        # ── Background Canvas (album art + dark overlay + corner glows) ──
        self.bg_canvas = tk.Canvas(self.center, bg=BG_MAIN, highlightthickness=0)
        self.bg_canvas.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        # Dark placeholder until album art loads
        self.bg_canvas.create_rectangle(0, 0, 600, 400, fill=BG_MAIN, outline="", tags="overlay")
        self.bg_canvas.create_text(300, 160, text="♪", font=("Microsoft YaHei", 48),
                                    fill=FG2, tags="placeholder")

        # Corner glows (subtle radial-ish circles)
        for cx, cy, r, clr in [
            (0, 0, 120, "#c084fc"), (0, 0, 80, "#f0a8c0"),   # top-left
            (600, 0, 120, "#c084fc"), (600, 0, 80, "#64b4ff"), # top-right
            (0, 400, 100, "#c084fc"), (600, 400, 100, "#f0a8c0"), # bottom corners
        ]:
            self.bg_canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                        fill=clr, outline="", stipple="gray12", tags="glow")

        # Dot texture (scattered tiny dots)
        _rnd.seed(42)
        for _ in range(60):
            x, y = _rnd.randint(0, 600), _rnd.randint(0, 420)
            self.bg_canvas.create_oval(x, y, x + 2, y + 2, fill=FG_DIM, outline="", tags="dots")

        # ── Lyrics text items on the Canvas ──
        self._lyric_current_id = self.bg_canvas.create_text(
            300, 160, text="", font=("Microsoft YaHei", 32, "bold"),
            fill=FG_BRIGHT, justify=tk.CENTER, width=460, tags="lyric_cur")
        self._lyric_next_id = self.bg_canvas.create_text(
            300, 210, text="", font=("Microsoft YaHei", 20),
            fill=FG2, justify=tk.CENTER, width=460, tags="lyric_next")
        self.lyrics = []
        self._lyric_idx = -1

        # ── Progress + time ──
        pf = tk.Frame(self.center, bg=BG_MAIN)
        pf.pack(fill=tk.X, padx=20, pady=(4, 2))
        self.time_lbl = tk.Label(pf, text="00:00", font=("Consolas", 14),
                                 fg=FG_ACC, bg=BG_MAIN)
        self.time_lbl.pack(side=tk.LEFT)
        self.time_end = tk.Label(pf, text="/ 00:00", font=("Consolas", 14),
                                 fg=FG_DIM, bg=BG_MAIN)
        self.time_end.pack(side=tk.RIGHT)
        self.pbar_canvas = tk.Canvas(pf, bg=BG_MAIN, height=10, highlightthickness=0)
        self.pbar_canvas.pack(fill=tk.X, expand=True, padx=10)
        self.pbar_canvas.bind("<Button-1>", self._seek_press)
        self.pbar_canvas.bind("<B1-Motion>", self._seek_drag)
        self.pbar_canvas.bind("<ButtonRelease-1>", self._seek_release)
        self._seek_time = None  # target seek position in seconds
        self._draw_progress_bar(0)

        # ── Controls ──
        cf = tk.Frame(self.center, bg=BG_MAIN)
        cf.pack(pady=(12, 8))
        nav_style = {"font": ("Segoe UI Symbol", 20), "bg": Cp.BTN_NAV_BG, "fg": Cp.BTN_NAV_FG,
                     "activebackground": Cp.BTN_NAV_HOVER, "activeforeground": FG_BRIGHT,
                     "relief": tk.FLAT, "cursor": "hand2", "bd": 0}
        tk.Button(cf, text="◂◂", command=self._prev, **nav_style).pack(side=tk.LEFT, padx=Sp.SM)
        self.pp_btn = tk.Button(cf, text="▶", command=self._toggle, **nav_style)
        self.pp_btn.pack(side=tk.LEFT, padx=Sp.SM)
        tk.Button(cf, text="▸▸", command=self._next, **nav_style).pack(side=tk.LEFT, padx=Sp.SM)

        # ── Capsule action buttons ──
        rf = tk.Frame(self.center, bg=BG_MAIN)
        rf.pack(pady=(4, 8))
        cap = {"font": ("Microsoft YaHei", 14), "relief": tk.FLAT,
               "cursor": "hand2", "padx": 20, "pady": 12, "bd": 0}

        self.like_btn = tk.Button(rf, text="♥ 喜欢", bg=Cp.BTN_LIKE_BG, fg=FG_ACC,
                                   activebackground=Cp.BTN_LIKE_HOVER, activeforeground=FG_BRIGHT,
                                   command=self._like, **cap)
        self.like_btn.pack(side=tk.LEFT, padx=Sp.SM)
        self.skip_btn = tk.Button(rf, text="» 跳过", bg=Cp.BTN_SKIP_BG, fg=FG2,
                                   activebackground=Cp.BTN_SKIP_HOVER, activeforeground=FG_BRIGHT,
                                   command=self._skip, **cap)
        self.skip_btn.pack(side=tk.LEFT, padx=Sp.SM)
        self.pl_btn = tk.Button(rf, text="+ 加入歌单", bg=Cp.BTN_PL_BG, fg=FG_BLUE,
                                activebackground=Cp.BTN_PL_HOVER, activeforeground=FG_BRIGHT,
                                command=self._add_pl, **cap)
        self.pl_btn.pack(side=tk.LEFT, padx=Sp.SM)

        # ── Song info line ──
        self.il = {}
        inf = tk.Frame(self.center, bg=BG_MAIN)
        inf.pack(pady=(2, 6))
        for k in ("al", "src", "sc"):
            v = tk.Label(inf, text="-", font=("Consolas", 12), fg=FG_DIM, bg=BG_MAIN)
            v.pack(side=tk.LEFT, padx=10)
            self.il[k] = v

    def _draw_progress_bar(self, pct):
        """Draw custom progress bar on Canvas."""
        c = self.pbar_canvas
        c.delete("all")
        w = c.winfo_width() or 300
        if w < 10:
            w = 300
        h = 10
        c.create_rectangle(0, 0, w, h, fill=C.SURF_TRACK, outline="")
        fill_w = int(w * pct / 100)
        if fill_w > 0:
            c.create_rectangle(0, 0, fill_w, h, fill=C.AC, outline="")
        if fill_w > 4 and pct < 100:
            c.create_oval(fill_w - 5, 0, fill_w + 5, h, fill=C.TX_HI, outline="")

    def _build_right(self):
        """Right column: 沧溟 avatar + chat."""
        # 沧溟 header
        mf = tk.Frame(self.right, bg=BG_MAIN)
        mf.pack(fill=tk.X, padx=12, pady=(12, 4))
        self._mochi_canvas = tk.Canvas(mf, bg=BG_MAIN, width=48, height=48, highlightthickness=0)
        self._mochi_canvas.pack(side=tk.LEFT, padx=(0, 8))
        self._draw_mochi()
        tk.Label(mf, text="沧溟", font=("Microsoft YaHei", 16, "bold"),
                 fg=FG_ACC, bg=BG_MAIN).pack(side=tk.LEFT)
        tk.Label(mf, text="你的音乐伙伴", font=("Microsoft YaHei", 11),
                 fg=FG_DIM, bg=BG_MAIN).pack(side=tk.LEFT, padx=(6, 0))

        # Chat display
        self.chat_display = tk.Text(self.right, bg=BG_CARD, fg=FG, wrap=tk.WORD,
                                     font=("Microsoft YaHei", 13), state=tk.DISABLED,
                                     height=16, borderwidth=0, padx=10, pady=10,
                                     relief=tk.FLAT)
        self.chat_display.pack(fill=tk.BOTH, expand=True, padx=10, pady=(6, 4))

        self.chat_display.tag_configure("claude_label", font=("Microsoft YaHei", 13, "bold"),
                                        foreground=FG_ACC)
        self.chat_display.tag_configure("user_label", font=("Microsoft YaHei", 13, "bold"),
                                        foreground=FG_BLUE)
        self.chat_display.tag_configure("claude", font=("Microsoft YaHei", 13),
                                        foreground=FG, lmargin1=10, lmargin2=10)
        self.chat_display.tag_configure("user", font=("Microsoft YaHei", 13),
                                        foreground=FG_BLUE, lmargin1=10, lmargin2=10)
        self.chat_display.tag_configure("system", font=("Microsoft YaHei", 11, "italic"),
                                        foreground=FG_DIM, justify=tk.CENTER)

        # Chat input
        inf = tk.Frame(self.right, bg=BG_MAIN)
        inf.pack(fill=tk.X, padx=10, pady=(0, 12))
        self.chat_input = tk.Text(inf, bg=BG_CARD, fg=FG,
                                   font=("Microsoft YaHei", 13), wrap=tk.WORD,
                                   height=2, borderwidth=0, padx=8, pady=6,
                                   relief=tk.FLAT, insertbackground=FG)
        self.chat_input.pack(fill=tk.X, side=tk.LEFT, expand=True)
        self.chat_input.bind("<Return>", self._chat_send)
        self.chat_input.bind("<Shift-Return>", lambda e: self.chat_input.insert(tk.INSERT, "\n"))
        tk.Button(inf, text="→", font=("Microsoft YaHei", 16, "bold"),
                  bg=BG_SEL, fg="#fff", activebackground=FG_ACC, activeforeground="#fff",
                  relief=tk.FLAT, cursor="hand2", padx=10, pady=6,
                  command=self._chat_send).pack(side=tk.RIGHT, padx=(4, 0))

        self.login_lbl = tk.Label(self.right, text="", font=("Microsoft YaHei", 10),
                                  fg=FG_DIM, bg=BG_MAIN)
        self.login_lbl.pack(pady=(0, 8))



    def _draw_mochi(self):
        """Draw 沧溟 bunny on the canvas."""
        c = self._mochi_canvas
        c.delete("all")
        # Body circle
        c.create_oval(4, 4, 44, 44, fill=BG_SEL, outline="", width=0)
        # Ears
        c.create_oval(10, -2, 18, 10, fill=BG_SEL, outline="")
        c.create_oval(28, -2, 36, 10, fill=BG_SEL, outline="")
        # Face
        c.create_text(24, 26, text="🐰", font=("Segoe UI Emoji", 22), anchor=tk.CENTER)

    def _build_bar(self):
        """Bottom status bar with mode switch, and system status."""
        bar = tk.Frame(self.root, bg=BG_MAIN, height=36)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)
        sep = tk.Canvas(bar, bg=BG_MAIN, height=1, highlightthickness=0)
        sep.pack(fill=tk.X)
        sep.create_line(0, 0, 1200, 0, fill=C.SURF_BORDER)

        bs = {"font": ("Microsoft YaHei", 11), "bg": C.BG, "fg": Cp.BAR_FG,
              "activebackground": Cp.BAR_BTN_HOVER_BG, "activeforeground": Cp.BAR_BTN_HOVER_FG,
              "relief": tk.FLAT, "cursor": "hand2", "bd": 0, "padx": Sp.MD, "pady": Sp.SM}

        # Mochi status
        tk.Label(bar, text="◇ 沧溟", font=("Microsoft YaHei", 11, "bold"),
                 fg=FG_ACC, bg=BG_MAIN).pack(side=tk.LEFT, padx=(Sp.MD, Sp.XS), pady=Sp.SM)
        tk.Label(bar, text="在陪你听歌", font=("Microsoft YaHei", 11),
                 fg=FG_DIM, bg=BG_MAIN).pack(side=tk.LEFT, pady=Sp.SM)
        tk.Label(bar, text="|", font=("Consolas", 11),
                 fg=C.SURF_BORDER, bg=BG_MAIN).pack(side=tk.LEFT, padx=Sp.SM)

        # Mode switch
        self.mode_btn = tk.Button(bar, text="RAP 模式", command=self._tgl_mode, **bs)
        self.mode_btn.pack(side=tk.LEFT, pady=Sp.SM)
        tk.Label(bar, text="|", font=("Consolas", 11),
                 fg=C.SURF_BORDER, bg=BG_MAIN).pack(side=tk.LEFT, padx=Sp.SM)

        # Volume slider
        tk.Label(bar, text="♪", font=("Segoe UI Symbol", 12),
                 fg=C.TX_MD, bg=BG_MAIN).pack(side=tk.LEFT, padx=(Sp.LG, Sp.XS), pady=Sp.SM)
        self.vol_scale = tk.Scale(bar, from_=0, to=150, orient=tk.HORIZONTAL,
                                   bg=BG_MAIN, fg=FG2, troughcolor=BG_CARD,
                                   highlightthickness=0, bd=0, length=100,
                                   command=self._set_volume)
        self.vol_scale.set(100)  # 100%
        self.vol_scale.pack(side=tk.LEFT, pady=Sp.SM)
        self.vol_lbl = tk.Label(bar, text="100%", font=("Consolas", 10),
                                fg=FG_DIM, bg=BG_MAIN, width=4)
        self.vol_lbl.pack(side=tk.LEFT, padx=(Sp.XS, 0), pady=Sp.SM)
        tk.Label(bar, text="|", font=("Consolas", 11),
                 fg=C.SURF_BORDER, bg=BG_MAIN).pack(side=tk.LEFT, padx=Sp.SM)

        # Other buttons
        tk.Button(bar, text="刷新", command=self._refresh, **bs).pack(side=tk.LEFT, pady=Sp.SM)
        tk.Button(bar, text="🌙 定时", command=self._sleep_timer_popup, **bs).pack(side=tk.LEFT, pady=Sp.SM)
        tk.Button(bar, text="登录", command=self._login, **bs).pack(side=tk.LEFT, pady=Sp.SM)
        tk.Button(bar, text="网页", command=self._open_ne, **bs).pack(side=tk.LEFT, pady=Sp.SM)
        tk.Button(bar, text="导入歌单", command=self._import_playlist, **bs).pack(side=tk.LEFT, pady=Sp.SM)
        tk.Button(bar, text="历史回溯", command=self._browse_history, **bs).pack(side=tk.LEFT, pady=Sp.SM)
        tk.Label(bar, text="|", font=("Consolas", 11),
                 fg=C.SURF_BORDER, bg=BG_MAIN).pack(side=tk.LEFT, padx=Sp.SM)
        tk.Button(bar, text="Mini", command=self._mini_player.toggle, **bs).pack(side=tk.LEFT, pady=Sp.SM)
        tk.Button(bar, text="歌词", command=self._desktop_lyrics.toggle, **bs).pack(side=tk.LEFT, pady=Sp.SM)

        # Mood radio status
        self._mood_status_lbl = tk.Label(bar, text="", font=("Microsoft YaHei", 11),
                                         fg=C.AC_WARM, bg=BG_MAIN)
        self._mood_status_lbl.pack(side=tk.LEFT, padx=Sp.MD, pady=Sp.SM)

        # System status
        self._sys_light = tk.Canvas(bar, bg=BG_MAIN, width=10, height=10, highlightthickness=0)
        self._sys_light.pack(side=tk.RIGHT, padx=(0, Sp.XS), pady=Sp.SM)
        self._sys_light.create_oval(0, 0, 10, 10, fill=FG_OK, outline="")
        tk.Label(bar, text="系统 OK", font=("Microsoft YaHei", 11),
                 fg=FG_OK, bg=BG_MAIN).pack(side=tk.RIGHT, padx=(0, Sp.XS), pady=Sp.SM)
        self.st_lbl = tk.Label(bar, text="就绪", font=("Microsoft YaHei", 11),
                               fg=FG_DIM, bg=BG_MAIN)
        self.st_lbl.pack(side=tk.RIGHT, padx=Sp.MD, pady=Sp.SM)

    def _chat_append(self, sender, text):
        """Append a message to the chat display."""
        self.chat_display.config(state=tk.NORMAL)
        if sender == "系统":
            self.chat_display.insert(tk.END, f"{text}\n", ("system",))
        else:
            tag_prefix = "user" if sender == "你" else "claude"
            label = f"◇ {sender}: " if sender == "沧溟" else f"{sender}: "
            self.chat_display.insert(tk.END, label, (f"{tag_prefix}_label",))
            self.chat_display.insert(tk.END, f"{text}\n\n", (tag_prefix,))
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)

    def _chat_event(self, event_type):
        """Send a system event (song_change/like/skip/add_playlist) to AI."""
        song = None
        with self._candidates_lock:
            song = self.songs[self.idx] if self.songs and self.idx < len(self.songs) else {}

        extra = self._load_chat_context()

        def _r():
            try:
                with self._chat_history_lock:
                    history_snapshot = self._chat_history[:]
                reply, _ = chat.send_event(
                    event_type, song,
                    history_snapshot,
                    history=extra["history"],
                    taste=extra["taste"],
                    song_stats=extra["song_stats"],
                    session_stats=extra.get("session_stats"))
                if reply:
                    with self._chat_history_lock:
                        self._chat_history.append({"role": "user",
                            "content": f"[System event: {event_type}]"})
                        self._chat_history.append({"role": "assistant", "content": reply})
                        self._chat_history = self._chat_history[-20:]
                    clean_reply, should_skip = self._check_ai_actions(reply)
                    self.root.after(0, lambda: self._chat_append("沧溟", clean_reply))
                    if should_skip:
                        self.root.after(1500, self._skip)
            except Exception:
                pass
        threading.Thread(target=_r, daemon=True).start()

    def _check_ai_actions(self, reply):
        """Parse AI action tags from reply. Returns (clean_reply, should_skip)."""
        should_skip = False
        clean = reply
        # Match [切歌] at end, with optional trailing Chinese punctuation
        m = re.search(r'\[切歌\][。，！？…\s]*$', clean)
        if m:
            # Don't auto-skip during song request — it would race with _handle_song_request
            if getattr(self, '_skip_in_progress', False) or getattr(self, '_song_request_in_flight', False):
                clean = clean[:m.start()].rstrip()
            else:
                should_skip = True
                clean = clean[:m.start()].rstrip()
        return clean, should_skip

    def _chat_send(self, event=None):
        """Handle chat input submission."""
        text = self.chat_input.get("1.0", "end-1c").strip()
        if not text:
            return "break"
        self.chat_input.delete("1.0", tk.END)
        self._chat_append("你", text)

        # Check for song request BEFORE the AI call — instant search
        song_req = chat.extract_song_request(text)
        if song_req:
            query, count, artist_name = song_req if len(song_req) == 3 else (song_req[0], song_req[1], None)
            self._song_request_in_flight = True
            threading.Thread(target=lambda: self._handle_song_request(query, count, artist_name),
                           daemon=True).start()

        # Check for report commands (/报告 /月度 /统计 /每周)
        report_reply = handle_command(text)
        if report_reply:
            self._chat_append("沧溟", report_reply)
            self.chat_input.delete("1.0", tk.END)
            return "break"

        # Check for mood radio activation
        mood = detect_mood(text)
        if mood and not self._mood_radio.active:
            self._mood_radio.activate(mood)
            self._chat_append("系统", f"🎵 {mood['label']} 已启动。{mood['description']}")
            self._mood_status_lbl.config(text=self._mood_radio.status_text())
            # Trigger rescore to apply mood boosts
            self._trigger_rescore()

        with self._candidates_lock:
            song = self.songs[self.idx] if self.songs and self.idx < len(self.songs) else {}
        extra = self._load_chat_context()

        def _r():
            try:
                with self._chat_history_lock:
                    history_snapshot = self._chat_history[:]
                reply, signals = chat.send_message(
                    text, song,
                    history_snapshot,
                    history=extra["history"],
                    taste=extra["taste"],
                    song_stats=extra["song_stats"],
                    session_stats=extra.get("session_stats"))
                with self._chat_history_lock:
                    self._chat_history.append({"role": "user", "content": text})
                    self._chat_history.append({"role": "assistant", "content": reply})
                    self._chat_history = self._chat_history[-20:]

                clean_reply, should_skip = self._check_ai_actions(reply)
                self.root.after(0, lambda: self._chat_append("沧溟", clean_reply))
                if should_skip:
                    self.root.after(1500, self._skip)
                if signals:
                    self._apply_chat_signals(signals)
            except Exception:
                self.root.after(0, lambda: self._chat_append("沧溟", "啊，我卡了一下……你刚说什么？"))
        threading.Thread(target=_r, daemon=True).start()
        return "break"

    def _apply_chat_signals(self, signals):
        """Store chat signals in history.json and trigger rescore."""
        h = {}
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, encoding="utf-8") as f:
                h = json.load(f)
        if "chat_signals" not in h:
            h["chat_signals"] = []
        h["chat_signals"].extend(signals)
        h["chat_signals"] = h["chat_signals"][-50:]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(h, f, ensure_ascii=False, indent=2)
        self._trigger_rescore()

    # ============================================================
    # DATA
    # ============================================================

    def _save_session(self):
        """Save current playback state so we can resume later.
        Also serves as the state bridge for the Web console (FastAPI reads this)."""
        songid = None
        songname = None
        singers = None
        if self.songs and self.idx < len(self.songs):
            song = self.songs[self.idx]
            songid = song.get("songid")
            songname = song.get("songname", "")
            singers = " / ".join(x.get("name", "") for x in song.get("singer", []))
        # Build a rich-enough snapshot so the Web console can display "now playing"
        queue_preview = []
        with self._candidates_lock:
            unplayed = [s for s in self.candidates if not s.get("_played", False)]
            for s in unplayed[:5]:
                queue_preview.append({
                    "songid": s.get("songid"),
                    "songname": s.get("songname", ""),
                    "artist": " / ".join(a.get("name", "") for a in s.get("singer", [])),
                })
        state = {
            "mode": self.mode,
            "last_songid": songid,
            "epsilon": getattr(self, '_epsilon', 0.15),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            # ── Web console bridge ──
            "current_song": {"songid": songid, "songname": songname, "singers": singers} if songid else None,
            "is_playing": self._is_playing(),
            "volume": round(self._volume, 2),
            "mood_radio": {
                "active": self._mood_radio.active,
                "mood_key": getattr(self._mood_radio, 'mood_key', None),
                "songs_played": getattr(self._mood_radio, 'songs_played', 0),
            } if self._mood_radio.active else None,
            "queue_preview": queue_preview,
        }
        try:
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_session(self):
        """Return saved session state or None."""
        if not os.path.exists(SESSION_FILE):
            return None
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _restore_mood_radio(self):
        """Restore Mood Radio state from session after init_data."""
        prev = self._load_session()
        if not prev:
            return
        mr = prev.get("mood_radio")
        if mr and mr.get("active") and mr.get("mood_key"):
            # Only restore if within the 10-song limit
            played = mr.get("songs_played", 0)
            if played < 10:
                self._mood_radio.active = True
                self._mood_radio.mood_key = mr["mood_key"]
                self._mood_radio.songs_played = played
                mood_label = mr["mood_key"]
                self._mood_status_lbl.config(text=self._mood_radio.status_text())
                self._chat_append("系统", f"🎵 已恢复上次的情绪电台")

    def _load_chat_context(self):
        """Load history + taste + per-song stats for AI context."""
        h = {}
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, encoding="utf-8") as f:
                    h = json.load(f)
            except Exception:
                pass

        taste = {}
        try:
            taste = eng.load_taste()
        except Exception:
            pass
        taste["_mode"] = self.mode

        song_stats = h.get("song_plays", {})
        # Session-level aggregates for AI awareness
        session_stats = {
            "total_played": self.play_count,
            "mode": self.mode,
            "mood_radio_active": self._mood_radio.active,
            "mood_radio_label": self._mood_radio.label if self._mood_radio.active else "",
            "queue_remaining": len([s for s in self.songs[self.idx:]
                                    if not s.get("_played", False)]) if self.songs else 0,
        }
        # Smart DJ observations (song arc + feedback stats)
        dj_ctx = self._smart_dj.get_dj_context()
        if dj_ctx and dj_ctx.get("recent_history"):
            session_stats["dj_context"] = dj_ctx
        return {"history": h, "taste": taste, "song_stats": song_stats,
                "session_stats": session_stats}

    def _track_play(self, song, action=None):
        """Record per-song play event in history.json for AI context.
        Only increments count for actual plays (action=None), not like/skip."""
        sid = str(song.get("songid", ""))
        if not sid:
            return
        h = {}
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, encoding="utf-8") as f:
                    h = json.load(f)
            except Exception:
                pass
        if "song_plays" not in h:
            h["song_plays"] = {}
        entry = h["song_plays"].get(sid, {
            "name": song.get("songname", ""),
            "artist": " / ".join(s.get("name", "") for s in song.get("singer", [])),
            "count": 0,
        })
        now_ts = datetime.now().strftime("%m-%d %H:%M")
        if action is None:
            # Normal play — only then increment count
            entry["count"] = entry.get("count", 0) + 1
            entry["last_played"] = now_ts
        if action == "like":
            entry["liked"] = True
        elif action == "skip":
            entry["skipped"] = True
        elif action == "neutral":
            entry["neutral"] = True
        h["song_plays"][sid] = entry
        # Block this song from future candidate builds
        if "recommended_ids" not in h:
            h["recommended_ids"] = []
        if sid not in h["recommended_ids"]:
            h["recommended_ids"].append(sid)
            h["recommended_ids"] = h["recommended_ids"][-5000:]
        # Keep last 500 songs tracked
        if len(h["song_plays"]) > 500:
            h["song_plays"] = dict(sorted(
                h["song_plays"].items(),
                key=lambda x: x[1].get("count", 0), reverse=True)[:300])
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(h, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _restore_position(self):
        """After loading candidates, jump to last-played song if possible.
        Skips songs marked _played to avoid restoring to a skipped song."""
        session = self._load_session()
        if not session:
            return False
        last_id = session.get("last_songid")
        if not last_id:
            return False
        for i, s in enumerate(self.songs):
            if s.get("songid") == last_id:
                if s.get("_played", False):
                    return False  # don't restore to an already-played/skipped song
                self.idx = i
                self._play(i)
                return True
        return False

    def _init_data(self, force_rebuild=False):
        """Initialize data: build candidates or load from cache.
        Set force_rebuild=True to skip cache (mode switch, manual refresh)."""
        today = datetime.now().strftime("%Y-%m-%d")
        if not force_rebuild:
            cached = eng.load_candidates(self.mode)
            if cached and cached.get("built_at", "")[:10] == today and cached.get("songs"):
                with self._candidates_lock:
                    self.candidates = cached["songs"]
                # Mark already-judged songs so they don't re-enter the queue
                with self._candidates_lock:
                    eng.mark_judged_songs(self.candidates)
                self._status(f"已加载 {len(self.candidates)} 首缓存歌曲")
                self._reload_list()
                return

        self._status("正在构建候选池...")
        def _r():
            try:
                block_ids = self._get_playlist_block_ids()
                result = eng.build_candidates(self.mode, extra_block_ids=block_ids)
                result = eng.score_candidates(result, self.mode)
                with self._candidates_lock:
                    self.candidates = result
                self.root.after(0, self._reload_list)
            except Exception as e:
                self.root.after(0, lambda e=str(e): self._status(f"构建失败: {e[:50]}"))
        threading.Thread(target=_r, daemon=True).start()

    def _reload_list(self, resort=True):
        """Refresh treeview from candidates, dimming played songs.
        If resort=False, keep current ordering (used during rescore to avoid
        shuffling the queue and skipping songs while playing).

        Anti-reentry: if a reload is already scheduled, skip this call.
        The pending reload will pick up the latest candidates state."""
        if self._reload_pending:
            return
        self._reload_pending = True
        self.root.after(0, lambda: self._do_reload_list(resort))

    def _do_reload_list(self, resort):
        self._reload_pending = False
        with self._candidates_lock:
            all_songs = self.candidates[:]
        if not all_songs:
            self.songs = []
            return
        # Mood radio: adjust scores before sorting
        if self._mood_radio.active:
            unplayed_adj = self._mood_radio.adjust_candidate_scores(
                [s for s in all_songs if not s.get("_played", False)])
            played_adj = [s for s in all_songs if s.get("_played", False)]
            # adjust_candidate_scores returns sorted list, but we want unplayed/played split preserved
            unplayed_scores = {str(s.get("songid", i)): s.get("_score", 0)
                             for i, s in enumerate(unplayed_adj)}
            for s in all_songs:
                sid = str(s.get("songid", ""))
                if sid in unplayed_scores and not s.get("_played", False):
                    s["_score"] = unplayed_scores[sid]

        # Sort: unplayed first (by _score), played last
        unplayed = [s for s in all_songs if not s.get("_played", False)]
        played = [s for s in all_songs if s.get("_played", False)]
        if resort:
            unplayed.sort(key=lambda s: s.get("_score", 0), reverse=True)
        played.sort(key=lambda s: s.get("_score", 0), reverse=True)
        self.songs = unplayed + played

        self.tree.delete(*self.tree.get_children())
        show_played = self._show_played
        unplayed_count = 0
        for i, s in enumerate(self.songs):
            is_played = s.get("_played", False)
            if is_played and not show_played:
                continue
            singers = " / ".join(x.get("name", "") for x in s.get("singer", []))
            if is_played:
                marker = "✓"
            else:
                unplayed_count += 1
                marker = str(unplayed_count)
            tags = ("played_row",) if is_played else ()
            sid = str(s.get("songid", i))
            self.tree.insert("", tk.END, iid=sid,
                             values=(marker, s.get("songname", ""),
                                     singers, f"{s.get('_score', 0):.2f}"),
                             tags=tags)
        mode_labels = {"rap": "RAP 模式", "mixed": "混合模式", "focus": "专注模式"}
        mode_label = mode_labels.get(self.mode, self.mode)
        self._status(f"{mode_label}: {len(unplayed)} 首待播 — 池中 {len(self.songs)} 首")

        if unplayed and not self._is_playing() and not getattr(self, '_skip_in_progress', False):
            if not self._restore_position():
                # ε-greedy bandit: sometimes explore instead of playing top-scored
                eps = getattr(self, '_epsilon', 0.15)
                pick, is_explore = eng.select_bandit_pick(self.songs, eps)
                self._last_pick_explore = is_explore
                self.idx = pick
                self._play(pick)
        else:
            # Ensure the current song stays highlighted after rescore
            self._highlight_current()

    def _highlight_current(self):
        """Highlight the currently playing song in the queue and scroll to it."""
        if not self.songs or self.idx >= len(self.songs):
            return
        sid = str(self.songs[self.idx].get("songid", ""))
        if not sid:
            return
        # Remove old highlights
        for item in self.tree.get_children():
            if "now_playing" in self.tree.item(item, "tags"):
                current_tags = list(self.tree.item(item, "tags"))
                current_tags.remove("now_playing")
                self.tree.item(item, tags=tuple(current_tags))
        # Highlight current
        kids = self.tree.get_children()
        if sid in kids:
            self.tree.selection_set(sid)
            self.tree.see(sid)
            # Add now_playing tag on top of existing tags
            existing = list(self.tree.item(sid, "tags"))
            existing.append("now_playing")
            self.tree.item(sid, tags=tuple(existing))

    def _trigger_rescore(self):
        """Rescore unplayed candidates in background thread.
        Does NOT re-sort the list — keeps current playback order stable.
        Scores are still updated for display and future session rebuilds."""
        def _r():
            try:
                with self._candidates_lock:
                    self.candidates = eng.rescore_unplayed(self.candidates, self.mode)
                self.root.after(0, lambda: self._reload_list(resort=False))
            except Exception:
                pass
        threading.Thread(target=_r, daemon=True).start()

    def _check_simi_expand(self):
        """Track play count, trigger simi expansion every 10 songs."""
        if not self.songs or self.idx >= len(self.songs):
            return
        self.play_count += 1
        song = self.songs[self.idx]
        with self._simi_queue_lock:
            self._simi_queue.append(song["songid"])
            if len(self._simi_queue) > 10:
                self._simi_queue = self._simi_queue[-10:]

        if self.play_count > 0 and self.play_count % 10 == 0:
            self._status("正在扩展候选池 (相似歌曲)...")
            def _r():
                try:
                    with self._candidates_lock:
                        with self._simi_queue_lock:
                            queue_copy = self._simi_queue[:]
                        new = eng.expand_from_simi(queue_copy, self.candidates, self.mode)
                    if new:
                        self.root.after(0, lambda: self._status(
                            f"已添加 {len(new)} 首相似歌曲"))
                        self.root.after(0, lambda: self._reload_list(resort=False))
                except Exception:
                    pass
            threading.Thread(target=_r, daemon=True).start()

    # (_load replaced by _reload_list which reads from self.candidates)

    # ============================================================
    # PLAYBACK (ffplay)
    # ============================================================

    def _is_playing(self):
        return self.ffplay is not None and self.ffplay.poll() is None

    def _song_by_id(self, sid):
        """Find a song in self.songs by its songid (string)."""
        for s in self.songs:
            if str(s.get("songid", "")) == str(sid):
                return s
        return None

    def _play_song(self, song):
        """Play a specific song object from self.songs."""
        try:
            idx = self.songs.index(song)
        except ValueError:
            idx = 0
        self.idx = idx
        sid = str(song.get("songid", ""))
        # Select in tree by item ID
        kids = self.tree.get_children()
        if sid in kids:
            self.tree.selection_set(sid)
            self.tree.see(sid)
        self._play_current()

    def _play(self, index):
        if index < 0 or index >= len(self.songs):
            return
        self._last_pick_explore = False  # default: user-directed choice
        self.idx = index
        song = self.songs[index]
        sid = str(song.get("songid", ""))
        # Select in tree by item ID
        kids = self.tree.get_children()
        if sid in kids:
            self.tree.selection_set(sid)
            self.tree.see(sid)
        self._play_current()

    def _play_current(self):
        self._stop_ffplay()
        song = self.songs[self.idx]
        sid = song["songid"]
        idx = self.idx  # capture current index
        self._current_song_id = sid  # set IMMEDIATELY for reliable skip (before async URL fetch)

        self._status(f"获取中: {song['songname'][:30]}...")
        def _f():
            data = ncm("/song/url/v1", {"id": sid, "level": "standard"})
            u = data.get("data", [{}])[0].get("url") if data else None
            # Only play if user hasn't moved on
            if u and self.idx == idx:
                song["url"] = {"url": u, "type": "mp3"}
                self.root.after(0, lambda: self._start_ffplay(u, song))
            elif self.idx == idx:
                self._skip_in_progress = False  # clear guard: song can't play, let engine move on
                self.root.after(0, lambda: self._status(
                    f"无播放链接(VIP?): {song['songname'][:30]}"))
        threading.Thread(target=_f, daemon=True).start()

    def _start_ffplay(self, url, song):
        self._stop_ffplay()
        self._skip_in_progress = False  # clear skip guard — song is now playing
        vol = getattr(self, '_volume', 1.0)
        seek_sec = getattr(self, '_seek_time', None)
        self._seek_time = None  # consume once
        cmd = [FFPLAY, "-nodisp", "-autoexit", "-loglevel", "quiet"]
        if seek_sec and seek_sec > 1:
            cmd += ["-ss", str(int(seek_sec))]
        cmd += ["-af", f"volume={vol:.2f}", url]
        self._status(f"播放中: {song['songname'][:40]}..." +
                     (f" (从 {int(seek_sec)}s)" if seek_sec and seek_sec > 1 else ""))
        try:
            self.ffplay = subprocess.Popen(
                cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000)  # CREATE_NO_WINDOW
            self.pp_btn.config(text="⏸")
            # ── Taskbar: set playing state ──
            if self._taskbar:
                self._taskbar.set_playing_state()
            if seek_sec and seek_sec > 1:
                # Adjust wall-clock anchor so progress bar reflects seek position
                self._play_start = time.time() - seek_sec
                self._paused_elapsed = 0
            else:
                self._play_start = time.time()
                self._paused_elapsed = 0
            self._show_info(song)
            self._update_progress()
            self.root.after(100, self._check_simi_expand)
            # ── Toast notification on song change ──
            if not (seek_sec and seek_sec > 1):  # skip toast for seeks
                singers = " / ".join(s.get("name", "") for s in song.get("singer", []))
                threading.Thread(target=lambda: show_toast(
                    song.get("songname", "")[:40],
                    singers[:60],
                ), daemon=True).start()
        except Exception as err:
            self._skip_in_progress = False  # clear even on error
            self._status(f"播放错误: {err}")

    def _stop_ffplay(self):
        if self.ffplay and self.ffplay.poll() is None:
            try:
                self.ffplay.terminate()
                self.ffplay.wait(timeout=3)
            except Exception:
                try:
                    self.ffplay.kill()
                except Exception:
                    pass
        self.ffplay = None

    def _set_volume(self, val):
        """Volume slider callback (0-150 → 0.0-1.5 multiplier). Debounced.  """
        vol = int(val) / 100.0
        self._volume = vol
        self.vol_lbl.config(text=f"{int(val)}%")
        # Debounce: cancel any pending restart, only apply after drag stops
        if hasattr(self, '_vol_debounce_id'):
            self.root.after_cancel(self._vol_debounce_id)
        self._vol_debounce_id = self.root.after(350, self._apply_volume_change)

    def _apply_volume_change(self):
        """Actually restart ffplay with the new volume (only called after slider settles)."""
        if not self._is_playing():
            return
        elapsed = time.time() - getattr(self, '_play_start', time.time()) + getattr(self, '_paused_elapsed', 0)
        self._seek_time = max(0, elapsed)
        self._skip_track = True  # not a new play — just adjusting playback
        self._play_current()

    def _toggle_mute(self):
        """Toggle mute: save current volume, set to 0, restore on unmute."""
        if getattr(self, '_muted', False):
            restore = getattr(self, '_prev_volume', 1.0)
            self._set_volume(int(restore * 100))
            self._muted = False
            self._status(f"已取消静音 ({int(restore * 100)}%)")
        else:
            self._prev_volume = self._volume
            self._set_volume(0)
            self._muted = True
            self._status("已静音")

    def _key_seek(self, delta):
        """Seek by a fraction delta (-0.05 back, +0.05 forward)."""
        if not self.songs or self.idx >= len(self.songs):
            return
        song = self.songs[self.idx]
        dur_ms = song.get("duration", 300000) or 300000
        dur_sec = dur_ms / 1000
        if dur_sec < 5:
            return
        # Compute current elapsed from wall clock (or paused state)
        if self._is_playing():
            elapsed = time.time() - self._play_start + getattr(self, '_paused_elapsed', 0)
        else:
            elapsed = getattr(self, '_paused_elapsed', 0)
        # Apply delta as fraction of total duration
        new_sec = max(0, min(dur_sec, elapsed + delta * dur_sec))
        self._seek_time = new_sec
        pct = new_sec / dur_sec * 100
        self._draw_progress_bar(pct)
        if self._is_playing() or self._paused_elapsed > 0:
            self._paused_elapsed = 0
            self._skip_track = True
            self._play_current()

    def _seek_pct(self, event):
        """Convert a mouse x position on the progress bar to a seek percentage (0-100)."""
        w = self.pbar_canvas.winfo_width() or 300
        pct = max(0, min(100, event.x / w * 100))
        return pct

    def _seek_press(self, event):
        """Mouse down on progress bar → preview seek position, don't seek yet."""
        if not self.songs or self.idx >= len(self.songs):
            return
        song = self.songs[self.idx]
        dur_ms = song.get("duration", 300000) or 300000
        dur_sec = dur_ms / 1000
        if dur_sec < 5:
            return
        pct = self._seek_pct(event)
        self._seek_time = dur_sec * pct / 100
        self._draw_progress_bar(pct)

    def _seek_drag(self, event):
        """Drag on progress bar → preview position."""
        if not self.songs or self.idx >= len(self.songs):
            return
        song = self.songs[self.idx]
        dur_ms = song.get("duration", 300000) or 300000
        dur_sec = dur_ms / 1000
        if dur_sec < 5:
            return
        pct = self._seek_pct(event)
        self._seek_time = dur_sec * pct / 100
        self._draw_progress_bar(pct)

    def _seek_release(self, event):
        """Mouse release → perform the seek if seek_time is set."""
        if self._seek_time is None:
            return
        if self._is_playing() or getattr(self, '_paused_elapsed', 0) > 0:
            self._paused_elapsed = 0
            self._skip_track = True  # seeking — not a new play
            self._play_current()

    def _init_taskbar(self):
        """Initialize taskbar integration after window is mapped."""
        try:
            self._taskbar = TaskbarHelper(self.root)
        except Exception:
            self._taskbar = None

    def _toggle(self):
        if self._is_playing():
            # Pause: save accumulated elapsed
            self._paused_elapsed += time.time() - getattr(self, '_play_start', time.time())
            self._stop_ffplay()
            self.pp_btn.config(text="▶")
            self._status("已暂停")
            if self._taskbar:
                self._taskbar.set_paused_state()
        else:
            # Resume: reset wall-clock anchor
            self._play_start = time.time()
            self._play_current()
            if self._taskbar:
                self._taskbar.set_playing_state()

    def _next(self):
        if not self.songs:
            return
        cur_id = getattr(self, '_current_song_id', None)
        # Mark as played + add to history + record neutral signal
        if cur_id:
            found = None
            with self._candidates_lock:
                for c in self.candidates:
                    if c.get("songid") == cur_id and not c.get("_played", False):
                        c["_played"] = True
                        found = c
                        break
            if found:
                self._track_play(found, "neutral")  # heard it, no strong opinion
                self._add_to_history(found, "played")
        # Smart DJ feedback: neutral (heard full song, no rating)
        self._smart_dj.record_feedback("neutral")
        # Smart DJ interjection on natural song end (not on seek/skip)
        if self._smart_dj.should_interject():
            threading.Thread(target=self._smart_dj_interject, daemon=True).start()
        self._next_from(cur_id)

    def _next_from(self, song_id):
        """Advance to the song after the given song_id (handles re-sorted list)."""
        if not self.songs:
            return
        pos = 0
        if song_id:
            for i, s in enumerate(self.songs):
                if s.get("songid") == song_id:
                    pos = i
                    break
        self._play((pos + 1) % len(self.songs))

    def _prev(self):
        if self.songs:
            self._play((self.idx - 1) % len(self.songs))

    def _update_progress(self):
        if not self._is_playing():
            return
        song = self.songs[self.idx]
        dur_ms = song.get("duration", 300000) or 300000
        # Use wall-clock time for accurate sync with ffplay
        elapsed = time.time() - getattr(self, '_play_start', time.time()) + getattr(self, '_paused_elapsed', 0)
        pct = min(elapsed * 1000 / dur_ms * 100, 100)
        self._draw_progress_bar(pct)
        es = int(elapsed)
        total_s = dur_ms // 1000
        self.time_lbl.config(text=f"{es // 60:02d}:{es % 60:02d}")
        self.time_end.config(text=f"/ {total_s // 60:02d}:{total_s % 60:02d}")
        # Update lyric highlight
        self._update_lyric_highlight(int(elapsed * 1000))
        # ── Taskbar progress ──
        if hasattr(self, '_taskbar') and self._taskbar:
            self._taskbar.set_progress(pct)
        if pct < 100:
            self.root.after(250, self._update_progress)

    def _watch_playback(self):
        """Auto-play next when ffplay exits."""
        if self.ffplay and self.ffplay.poll() is not None:
            # ffplay finished
            self.ffplay = None
            self.pp_btn.config(text="▶")
            self._next()
        self.root.after(2000, self._watch_playback)

    def _show_info(self, song):
        if not getattr(self, '_skip_track', False):
            sid = str(song.get("songid", ""))
            last_sid = getattr(self, '_last_tracked_sid', '')
            last_ts = getattr(self, '_last_tracked_ts', 0)
            now = time.time()
            # Don't re-count the same song within 10 seconds (covers seek, volume restart, etc.)
            if sid != last_sid or (now - last_ts) > 10:
                self._track_play(song)
                self._last_tracked_sid = sid
                self._last_tracked_ts = now
        self._skip_track = False
        # Left column: song name + artist
        self.name_lbl.config(text=song.get("songname", ""))
        singers = " / ".join(s.get("name", "") for s in song.get("singer", []))
        self.art_lbl.config(text=singers)

        # Tags: genre from source, year placeholder
        sources = song.get("_sources", []) or song.get("sources", [])
        src_str = sources[0] if sources else ""
        self.tag_genre.config(text=src_str[:16] if src_str else "—")
        self.tag_year.config(text=f"★ {song.get('_score', song.get('score', 0)):.2f}")
        self._update_score_breakdown(song)

        # Center: info line
        self.il["al"].config(text=song.get("albumname", "?")[:20] if song.get("albumname") else "?")
        self.il["src"].config(text=(src_str[:20]) if src_str else "—")
        self.il["sc"].config(text=f"匹配 {song.get('_score', song.get('score', 0)):.2f}")

        self.lyrics = []
        self._lyric_idx = -1
        self._show_lyrics()
        self._save_session()  # remember where we are
        # Album art
        aid = song.get("albumid", 0)
        if aid:
            self._load_art(aid)
        # Fetch lyrics in background
        sid = song.get("songid", 0)
        if sid:
            threading.Thread(target=lambda: self._fetch_lyrics(sid), daemon=True).start()
        # Highlight current song in queue
        self.root.after(100, self._highlight_current)

        # ── Smart DJ: record play ──
        if not getattr(self, '_skip_track', False):
            singers = " / ".join(s.get("name", "") for s in song.get("singer", []))
            self._smart_dj.record_play(song.get("songname", ""), singers)

        # ── Mood Radio: count played song ──
        if self._mood_radio.active:
            finished = self._mood_radio.on_song_played()
            if finished:
                self.root.after(0, lambda: self._chat_append("系统",
                    f"🎵 {self._mood_radio.label} 已结束，回到普通模式。"))
                self._mood_radio.deactivate()
                self._mood_status_lbl.config(text="")
            else:
                self._mood_status_lbl.config(text=self._mood_radio.status_text())

    # ============================================================
    # LYRICS
    # ============================================================

    def _fetch_lyrics(self, songid):
        """Fetch and parse LRC lyrics from NetEase API."""
        data = ncm("/lyric", {"id": songid})
        if not data or data.get("code") != 200:
            return
        lrc = data.get("lrc", {})
        raw = lrc.get("lyric", "")
        if not raw:
            return
        # Parse LRC: [mm:ss.xx]text or [mm:ss]text
        parsed = []
        for line in raw.split("\n"):
            m = re.match(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)", line.strip())
            if m:
                ms = int(m.group(1)) * 60000 + int(float(m.group(2)) * 1000)
                text = m.group(3).strip()
                if text:
                    parsed.append((ms, text))
        parsed.sort(key=lambda x: x[0])
        if parsed:
            self.lyrics = parsed
            self.root.after(0, self._show_lyrics)

    def _show_lyrics(self):
        """Render lyrics on Canvas: current line (32pt bold) + next line (20pt dim)."""
        c = self.bg_canvas
        w = c.winfo_width() or 500
        cy = c.winfo_height() // 2 if c.winfo_height() > 10 else 160

        cur_text = ""
        next_text = ""
        if self.lyrics:
            if 0 <= self._lyric_idx < len(self.lyrics):
                cur_text = self.lyrics[self._lyric_idx][1]
            if self._lyric_idx + 1 < len(self.lyrics):
                next_text = self.lyrics[self._lyric_idx + 1][1]

        if not cur_text and not next_text:
            cur_text = "♪  暂无歌词  ♪" if not self.lyrics else "♪  ···  ♪"

        c.itemconfig(self._lyric_current_id, text=cur_text)
        c.itemconfig(self._lyric_next_id, text=next_text)
        # Center vertically — wider gap to prevent overlap on wrapped long lines
        c.coords(self._lyric_current_id, w // 2, cy - 50)
        c.coords(self._lyric_next_id, w // 2, cy + 55)

    def _update_lyric_highlight(self, elapsed_ms):
        """Find lyric line matching elapsed time. Only redraw on change."""
        if not self.lyrics:
            return
        new_idx = -1
        for i, (ms, text) in enumerate(self.lyrics):
            if ms <= elapsed_ms:
                new_idx = i
            else:
                break
        if new_idx != self._lyric_idx:
            self._lyric_idx = new_idx
            self._show_lyrics()

    # ============================================================
    # RATING
    # ============================================================

    def _like(self):
        if self.idx >= len(self.songs):
            return
        song = self.songs[self.idx]
        # Don't mark _played — let user finish listening.
        self._track_play(song, "like")
        self._update_hist(song, "like")
        s = " / ".join(x.get("name", "") for x in song.get("singer", []))
        self._status(f"已喜欢! {s[:50]}")
        self.like_btn.config(fg=FG_BRIGHT, text="♥ 已喜欢!")
        self.root.after(800, lambda: self.like_btn.config(fg=FG_ACC, text="♥ 喜欢"))
        # Reduce exploration only if this was an exploration pick (confirmed open-minded)
        if getattr(self, '_last_pick_explore', False):
            self._epsilon = eng.update_epsilon(self._epsilon, "like_explore")
        # Smart DJ feedback
        self._smart_dj.record_feedback("like")
        # Don't rescore — just record signal. Rescore happens on skip/refresh.

    def _skip(self):
        # Find current song by the tracked ID
        song_id = getattr(self, '_current_song_id', None)
        if not song_id or not self.songs:
            return
        pos, song = 0, None
        for i, s in enumerate(self.songs):
            if s.get("songid") == song_id:
                pos, song = i, s
                break
        if not song:
            return
        # Stop + mark
        self._stop_ffplay()
        song["_played"] = True
        self._track_play(song, "skip")
        self._update_hist(song, "skip")
        self._add_to_history(song, "skip")
        self._status(f"已跳过: {' / '.join(x.get('name','') for x in song.get('singer',[]))[:50]}")
        self.skip_btn.config(fg=C.WARN, text="» 已跳过")
        self.root.after(800, lambda: self.skip_btn.config(fg=FG2, text="» 跳过"))
        # Play next directly (no waiting for rescore)
        next_song = self.songs[(pos + 1) % len(self.songs)]
        # CRITICAL: save session with next song BEFORE async play + rescore,
        # otherwise _reload_list → _restore_position will jump back to the skipped song.
        # Smart DJ feedback
        self._smart_dj.record_feedback("skip")

        self._skip_in_progress = True
        try:
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump({"mode": self.mode, "last_songid": next_song.get("songid"),
                           "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                          f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        self._play_song(next_song)
        # Adjust bandit: skipping an exploration pick means explore didn't pay off,
        # skipping an exploitation pick means taste may be stale
        if getattr(self, '_last_pick_explore', False):
            self._epsilon = eng.update_epsilon(self._epsilon, "skip_explore")
        else:
            self._epsilon = eng.update_epsilon(self._epsilon, "skip_exploit")
        self._trigger_rescore()

    def _update_hist(self, song, action):
        h = {}
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, encoding="utf-8") as f:
                h = json.load(f)
        k = "liked_artists" if action == "like" else "skipped_artists"
        if k not in h:
            h[k] = {}
        for s in song.get("singer", []):
            n = s.get("name", "")
            if n:
                h[k][n] = h[k].get(n, 0) + 1
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(h, f, ensure_ascii=False, indent=2)
        self._update_stats(action)

    def _update_stats(self, action=None):
        """Update session stat counters and taste bars."""
        h = {}
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, encoding="utf-8") as f:
                h = json.load(f)
        liked = sum(h.get("liked_artists", {}).values())
        skipped = sum(h.get("skipped_artists", {}).values())
        played = liked + skipped or self.play_count or 1
        try:
            self.stat_played.config(text=str(played))
            self.stat_liked.config(text=str(liked))
            self.stat_skip.config(text=str(skipped))
        except Exception:
            pass

        # Update taste bars from engine's mode taste
        try:
            taste = eng.load_taste()
            mt = eng.get_mode_taste(taste, self.mode)
            aw = mt.get("artist_weights", {})
            top3 = sorted(aw.items(), key=lambda x: x[1], reverse=True)[:3]
            for w in self._taste_bars.winfo_children():
                w.destroy()
            for name, val in top3:
                row = tk.Frame(self._taste_bars, bg=BG_MAIN)
                row.pack(fill=tk.X, pady=2)
                tk.Label(row, text=name[:10], font=("Microsoft YaHei", 10),
                         fg=FG2, bg=BG_MAIN, width=8, anchor=tk.W).pack(side=tk.LEFT)
                bar = tk.Canvas(row, bg=BG_MAIN, height=10, highlightthickness=0, width=80)
                bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
                w_px = int(val * 80)
                bar.create_rectangle(0, 0, w_px, 10, fill=BG_SEL, outline="")
                tk.Label(row, text=f"{val:.2f}", font=("Consolas", 10),
                         fg=FG_DIM, bg=BG_MAIN).pack(side=tk.RIGHT)
        except Exception:
            pass

    # ============================================================
    # LOGIN & PLAYLIST
    # ============================================================

    def _check_login(self):
        d = ncm("/login/status")
        if d and d.get("data", {}).get("account"):
            nick = d["data"].get("profile", {}).get("nickname", "User")
            self.login_lbl.config(text=f"已登录: {nick}", fg=FG_OK)
            self._find_playlist()
        else:
            self.login_lbl.config(text="未登录 -> 点'登录'扫码", fg=FG2)

    def _login(self):
        d = ncm("/login/qr/key")
        if not d:
            self._status("API 不可达")
            return
        uk = d.get("data", {}).get("unikey")
        if not uk:
            self._status("二维码密钥获取失败")
            return
        d2 = ncm("/login/qr/create", {"key": uk, "qrimg": "true"})
        if not d2:
            return
        qurl = d2.get("data", {}).get("qrimg", "")
        if not qurl:
            return

        import base64
        try:
            if qurl.startswith("data:"):
                # data:image/png;base64,xxxx
                b64 = qurl.split(",", 1)[1]
                qr_bytes = base64.b64decode(b64)
            else:
                r = requests.get(qurl, timeout=10, headers={
                    "Referer": "https://music.163.com",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                })
                qr_bytes = r.content
        except Exception:
            self._status("二维码下载失败")
            return

        qw = tk.Toplevel(self.root)
        qw.title("扫码登录网易云")
        qw.geometry("320x380")
        qw.configure(bg=BG_MAIN)
        qw.transient(self.root)
        qw.grab_set()

        tk.Label(qw, text="用网易云音乐App扫描二维码",
                font=("Microsoft YaHei", 10, "bold"), fg=FG, bg=BG_MAIN).pack(pady=(15, 5))

        qp = os.path.join(DATA_DIR, "_qr.png")
        with open(qp, "wb") as f:
            f.write(qr_bytes)
        img = tk.PhotoImage(file=qp)
        tk.Label(qw, image=img, bg=BG_MAIN).pack(pady=10)
        qw.image = img

        sl = tk.Label(qw, text="等待扫码...", font=("Microsoft YaHei", 14),
                      fg=FG2, bg=BG_MAIN)
        sl.pack(pady=10)

        def _poll():
            for _ in range(180):
                time.sleep(1)
                d3 = ncm("/login/qr/check", {"key": uk})
                if not d3:
                    continue
                c = d3.get("code")
                if c == 800:
                    qw.after(0, lambda: sl.config(text="二维码已过期!", fg=FG_ACC))
                    return
                elif c == 802:
                    qw.after(0, lambda: sl.config(text="已扫描! 请在手机上确认...", fg=FG_OK))
                elif c == 803:
                    cookie = d3.get("cookie", "")
                    with open(LOGIN_FILE, "w") as f:
                        json.dump({"cookie": cookie, "time": time.time()}, f)
                    for item in cookie.split(";"):
                        if "=" in item:
                            k, v = item.strip().split("=", 1)
                            _session.cookies.set(k.strip(), v.strip())
                    qw.after(0, qw.destroy)
                    self.root.after(500, self._check_login)
                    return
            qw.after(0, lambda: sl.config(text="超时!", fg=FG_ACC))
        threading.Thread(target=_poll, daemon=True).start()

    def _find_playlist(self):
        """Find or create mode-specific playlists: Claude Rap + Claude Picks.
        Returns True if playlists were found/created successfully."""
        # Retry up to 3 times — Docker may be slow to start
        d = None
        for attempt in range(3):
            d = ncm("/user/playlist", {"uid": 0})
            if d is not None and d.get("code") == 200:
                break
            if attempt < 2:
                self.root.after(0, lambda a=attempt:
                    self._status(f"获取歌单列表失败，重试中 ({a+2}/3)..."))
                time.sleep(2.0)
        if not d or d.get("code") != 200:
            self.root.after(0, lambda: self._status("⚠ 无法获取歌单列表 — Docker 在运行吗？"))
            return False

        playlists = d.get("playlist", [])
        names = {pl.get("name"): pl.get("id") for pl in playlists}

        # Rap playlist
        if "Claude Rap" in names:
            self.playlist_rap = names["Claude Rap"]
        else:
            d2 = ncm("/playlist/create", {"name": "Claude Rap", "privacy": 0})
            if d2 and (d2.get("code") == 200 or d2.get("id")):
                self.playlist_rap = d2.get("id") or d2.get("playlist", {}).get("id")
                self.root.after(0, lambda: self._status("已创建歌单「Claude Rap」"))

        # Mixed playlist
        if "Claude Picks" in names:
            self.playlist_mixed = names["Claude Picks"]
        else:
            d2 = ncm("/playlist/create", {"name": "Claude Picks", "privacy": 0})
            if d2 and (d2.get("code") == 200 or d2.get("id")):
                self.playlist_mixed = d2.get("id") or d2.get("playlist", {}).get("id")
                self.root.after(0, lambda: self._status("已创建歌单「Claude Picks」"))

        # Focus playlist
        if "Claude Focus" in names:
            self.playlist_focus = names["Claude Focus"]
        else:
            d2 = ncm("/playlist/create", {"name": "Claude Focus", "privacy": 0})
            if d2 and (d2.get("code") == 200 or d2.get("id")):
                self.playlist_focus = d2.get("id") or d2.get("playlist", {}).get("id")
                self.root.after(0, lambda: self._status("已创建歌单「Claude Focus」"))

        # Cache playlist track IDs for dedup
        self._block_ids_rap = None
        self._block_ids_mixed = None
        self._block_ids_focus = None
        if self.playlist_rap:
            self._block_ids_rap = eng.get_playlist_track_ids(self.playlist_rap)
        if self.playlist_mixed:
            self._block_ids_mixed = eng.get_playlist_track_ids(self.playlist_mixed)
        if self.playlist_focus:
            self._block_ids_focus = eng.get_playlist_track_ids(self.playlist_focus)
        return True

    def _get_playlist_block_ids(self, mode=None):
        """Return cached playlist track IDs for given mode (isolated per mode).
        Refreshes from API if cache is empty."""
        if mode is None:
            mode = self.mode
        cache_attr = f'_block_ids_{mode}'
        cached = getattr(self, cache_attr, None)
        if cached is not None:
            return cached
        pid_map = {"rap": self.playlist_rap, "mixed": self.playlist_mixed, "focus": self.playlist_focus}
        pid = pid_map.get(mode)
        ids = eng.get_playlist_track_ids(pid) if pid else set()
        setattr(self, cache_attr, ids)
        return ids

    def _import_playlist(self):
        """Import songs from a NetEase playlist into the candidate pool."""
        # Fetch user's playlists
        d = ncm("/user/playlist", {"uid": 0})
        if not d:
            self._status("获取歌单失败 - 请先登录")
            return
        playlists = d.get("playlist", [])
        if not playlists:
            self._status("没有找到歌单")
            return

        # Filter out our auto-created playlists and empty ones
        pl_list = [(p.get("name", "?"), p.get("id"), p.get("trackCount", 0))
                   for p in playlists if p.get("trackCount", 0) > 0
                   and p.get("name") not in ("Claude Rap", "Claude Picks")]

        if not pl_list:
            self._status("没有可导入的歌单")
            return

        # Show selection dialog
        dlg = tk.Toplevel(self.root)
        dlg.title("导入网易云歌单")
        dlg.geometry("400x420")
        dlg.configure(bg=BG_MAIN)
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(dlg, text="选择要导入的歌单", font=("Microsoft YaHei", 12, "bold"),
                 fg=FG_BRIGHT, bg=BG_MAIN).pack(pady=(12, 6))

        # Listbox with scrollbar
        lf = tk.Frame(dlg, bg=BG_MAIN)
        lf.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
        lb = tk.Listbox(lf, bg=BG_CARD, fg=FG, font=("Microsoft YaHei", 12),
                        selectbackground=BG_SEL, selectforeground="#fff",
                        borderwidth=0, highlightthickness=0)
        lbs = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=lb.yview)
        lb.configure(yscrollcommand=lbs.set)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        lbs.pack(side=tk.RIGHT, fill=tk.Y)

        for i, (name, pid, count) in enumerate(pl_list):
            lb.insert(tk.END, f"{name}  ({count}首)")

        status_lbl = tk.Label(dlg, text="", font=("Microsoft YaHei", 10),
                              fg=FG_DIM, bg=BG_MAIN)
        status_lbl.pack(pady=(4, 2))

        def _do_import():
            sel = lb.curselection()
            if not sel:
                status_lbl.config(text="请选择一个歌单", fg=FG_ACC)
                return
            idx = sel[0]
            name, pid, count = pl_list[idx]
            status_lbl.config(text=f"正在导入「{name}」...", fg=FG2)
            dlg.update()

            def _fetch():
                try:
                    data = ncm("/playlist/detail", {"id": pid})
                    if not data or data.get("code") != 200:
                        dlg.after(0, lambda: status_lbl.config(text="获取歌单详情失败", fg=FG_ACC))
                        return
                    tracks = data.get("playlist", {}).get("tracks", [])
                    # Convert to candidate format
                    with self._candidates_lock:
                        existing_ids = {str(s["songid"]) for s in self.candidates}
                        existing_names = {eng._norm(s.get("songname", "")) for s in self.candidates}
                    block_ids = self._get_playlist_block_ids()
                    new_songs = []
                    for t in tracks:
                        sid = str(t.get("id", ""))
                        name = t.get("name", "")
                        if not sid:
                            continue
                        if sid in existing_ids or sid in block_ids:
                            continue
                        if eng._norm(name) in existing_names:
                            continue
                        song = {
                            "songname": name,
                            "songid": t.get("id", 0),
                            "duration": t.get("dt", 0),
                            "singer": [{"name": a.get("name", "")} for a in t.get("ar", [])],
                            "albumname": t.get("al", {}).get("name", ""),
                            "albumid": t.get("al", {}).get("id", 0),
                            "_sources": [f"import:{name}"],
                            "_score": 0,
                            "_played": False,
                            "_from_simi": False,
                        }
                        with self._candidates_lock:
                            self.candidates.append(song)
                        existing_ids.add(sid)
                        existing_names.add(eng._norm(name))
                        new_songs.append(song)
                    if new_songs:
                        with self._candidates_lock:
                            self.candidates = eng.score_candidates(self.candidates, self.mode)
                            eng.save_candidates(self.candidates, self.mode)
                    dlg.after(0, lambda: self._on_import_done(dlg, len(new_songs), name))
                except Exception as e:
                    dlg.after(0, lambda e=str(e): status_lbl.config(text=f"导入失败: {e[:40]}", fg=FG_ACC))
            threading.Thread(target=_fetch, daemon=True).start()

        tk.Button(dlg, text="导入", font=("Microsoft YaHei", 12),
                  bg=BG_SEL, fg="#fff", relief=tk.FLAT, cursor="hand2",
                  padx=20, pady=6, command=_do_import).pack(pady=(4, 8))

    def _on_import_done(self, dlg, count, name):
        """Callback after playlist import completes."""
        dlg.destroy()
        if count > 0:
            self._reload_list()
            self._status(f"已从「{name}」导入 {count} 首到播放队列")
        else:
            self._status(f"「{name}」中没有新歌曲（可能已存在）")

    def _handle_song_request(self, query, count=1, artist_name=None):
        """Search NetEase for a song request and add songs to queue / play immediately.

        When artist_name is set (user said "想听XX的歌"), fetches the artist's
        TOP/HOT songs sorted by popularity instead of keyword search results.
        Falls back to keyword search if artist lookup fails.
        """
        try:
            self.root.after(0, lambda: self._status(f"正在搜索「{query}」..."))

            # ── Artist mode: fetch top songs by popularity ──
            artist_songs = None
            search_artist = artist_name or query

            if search_artist and search_artist.strip():
                try:
                    artist_songs = eng.search_artist_hot_songs(search_artist, limit=30)
                except Exception:
                    artist_songs = None

            if artist_songs:
                # Use artist's hot songs (already sorted by popularity)
                results = []
                for s in artist_songs:
                    results.append({
                        "songname": s.get("songname", ""),
                        "songid": s.get("songid", 0),
                        "duration": s.get("duration", 0),
                        "singer": [{"name": a.get("name", "")} for a in s.get("singer", [])],
                        "albumname": s.get("albumname", ""),
                        "albumid": s.get("albumid", 0),
                    })
                self.root.after(0, lambda: self._status(
                    f"🎤 找到「{search_artist}」{len(results)} 首热门歌曲（按热度排序）"))
            else:
                # ── Fallback: keyword search ──
                try:
                    limit = max(10, count * 3)  # fetch extra for filtering
                    data = ncm("/search", {"keywords": query, "limit": limit})
                    if not data or data.get("code") != 200:
                        self.root.after(0, lambda: self._status(f"搜索失败，网易云 API 不可达"))
                        return
                    raw = data.get("result", {}).get("songs", [])
                    if not raw:
                        self.root.after(0, lambda: self._status(f"没搜到「{query}」"))
                        return

                    results = []
                    for s in raw:
                        results.append({
                            "songname": s.get("name", ""),
                            "songid": s.get("id", 0),
                            "duration": s.get("duration", 0),
                            "singer": [{"name": a.get("name", "")} for a in s.get("artists", [])],
                            "albumname": s.get("album", {}).get("name", ""),
                            "albumid": s.get("album", {}).get("id", 0),
                        })
                except Exception as e:
                    self.root.after(0, lambda e=str(e): self._status(f"搜索异常: {e[:50]}"))
                    return

                self.root.after(0, lambda: self._status(f"搜到 {len(results)} 首，匹配中..."))

            # Queue up to `count` songs
            q_words = [w.strip().lower() for w in query.split() if len(w.strip()) > 1]
            queued = 0
            boosted_artists = set()

            for song in results:
                if queued >= count:
                    break
                top_name = song.get("songname", "")
                top_artists = " ".join(s.get("name", "") for s in song.get("singer", [])).lower()
                top_text = f"{top_name} {top_artists}".lower()

                if artist_songs:
                    # Artist mode: songs are already top/hot — accept all
                    is_first = (queued == 0)  # capture BEFORE incrementing
                    self.root.after(0, lambda s=song, q=query, p=is_first:
                        self._queue_and_play_song_request(s, q, play=p))
                    queued += 1
                    for a in song.get("singer", []):
                        boosted_artists.add(a.get("name", ""))
                elif q_words:
                    hits = sum(1 for w in q_words if w in top_text)
                    if hits >= len(q_words) * 0.3:
                        is_first = (queued == 0)
                        self.root.after(0, lambda s=song, q=query, p=is_first:
                            self._queue_and_play_song_request(s, q, play=p))
                        queued += 1
                        for a in song.get("singer", []):
                            boosted_artists.add(a.get("name", ""))
                elif query.lower() in top_text:
                    is_first = (queued == 0)
                    self.root.after(0, lambda s=song, q=query, p=is_first:
                        self._queue_and_play_song_request(s, q, play=p))
                    queued += 1
                    for a in song.get("singer", []):
                        boosted_artists.add(a.get("name", ""))

            # If nothing matched precisely, fall back to top result
            if queued == 0 and results:
                # 🆕 If multiple results and no artist specified, show picker
                if len(results) >= 3 and not artist_name:
                    self.root.after(0, lambda: self._show_song_picker(results, query))
                    return
                top = results[0]
                self.root.after(0, lambda: self._queue_and_play_song_request(top, query, play=True))
                for a in top.get("singer", []):
                    boosted_artists.add(a.get("name", ""))

            # Boost artist weights in taste.json
            if boosted_artists:
                self._boost_artist_weights(boosted_artists)

            self.root.after(0, lambda: self._status(
                f"已添加 {queued or 1} 首歌到队列" + (f"，上调 {len(boosted_artists)} 位艺人权重" if boosted_artists else "")))
        finally:
            self._song_request_in_flight = False

    def _boost_artist_weights(self, artists, boost=0.15):
        """Increase weight for requested artists in taste.json (capped at 1.5)."""
        try:
            taste = {}
            taste_path = os.path.join(DATA_DIR, "taste.json")
            if os.path.exists(taste_path):
                with open(taste_path, "r", encoding="utf-8") as f:
                    taste = json.load(f)
            mode_taste = taste.setdefault("modes", {}).setdefault(self.mode, {})
            weights = mode_taste.setdefault("artist_weights", {})
            for name in artists:
                old = float(weights.get(name, 0.5))
                weights[name] = round(min(1.5, old + boost), 3)
            with open(taste_path, "w", encoding="utf-8") as f:
                json.dump(taste, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _queue_and_play_song_request(self, song, query, play=True):
        """Add a requested song right after the current position and optionally play it."""
        sid = str(song.get("songid", ""))
        if not sid:
            self._status("歌曲无 ID，无法加入队列")
            return

        # Stop current playback only for the first queued song
        if play:
            self._stop_ffplay()

        # Check if already in candidates
        with self._candidates_lock:
            existing_ids = {str(s["songid"]) for s in self.candidates}
            if sid not in existing_ids:
                song["_sources"] = [f"request:{query}"]
                song["_score"] = 9.99  # always top
                song["_played"] = False
                song["_from_simi"] = False
                self.candidates.insert(0, song)  # put at front
            else:
                # Already in candidates — unmark played so it becomes playable again
                for s in self.candidates:
                    if str(s.get("songid", "")) == sid:
                        s["_played"] = False
                        s["_score"] = 9.99
                        break

            # Rebuild self.songs directly instead of going through _reload_list
            # (avoids _reload_list auto-play race)
            all_songs = self.candidates[:]
        unplayed = [s for s in all_songs if not s.get("_played", False)]
        played = [s for s in all_songs if s.get("_played", False)]
        unplayed.sort(key=lambda s: s.get("_score", 0), reverse=True)
        played.sort(key=lambda s: s.get("_score", 0), reverse=True)
        self.songs = unplayed + played

        # Find the requested song
        target_idx = None
        for i, s in enumerate(self.songs):
            if str(s.get("songid", "")) == sid:
                target_idx = i
                break

        if target_idx is not None:
            if play:
                self.idx = target_idx
                self._current_song_id = sid
                self._play_current()
                singers = " / ".join(x.get("name", "") for x in song.get("singer", []))
                self._status(f"已点歌: {song.get('songname','')} — {singers}")
            # 🆕 Refresh tree with resort=True so the 9.99-scored song appears at top
            # Use after_idle instead of hardcoded 500ms for reliable scheduling
            self.root.after_idle(lambda: self._reload_list(resort=True))
        else:
            self._status(f"点歌失败: 歌曲未找到")

    def _show_song_picker(self, results, query):
        """Show a dialog to pick from multiple search results."""
        dlg = tk.Toplevel(self.root)
        dlg.title(f"搜索: {query}")
        dlg.geometry("420x360")
        dlg.configure(bg=BG_MAIN)
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(dlg, text=f"「{query}」的搜索结果", font=("Microsoft YaHei", 12, "bold"),
                 fg=FG_BRIGHT, bg=BG_MAIN).pack(pady=(12, 6))

        lb = tk.Listbox(dlg, bg=BG_CARD, fg=FG, font=("Microsoft YaHei", 13),
                        selectbackground=BG_SEL, selectforeground="#fff",
                        borderwidth=0, highlightthickness=0, height=6)
        lb.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
        for s in results[:5]:
            singers = " / ".join(x.get("name", "") for x in s.get("singer", []))
            lb.insert(tk.END, f"{s.get('songname','?')}  —  {singers}")

        def _pick():
            sel = lb.curselection()
            if not sel:
                return
            song = results[sel[0]]
            dlg.destroy()
            self._queue_and_play_song_request(song, query)

        tk.Button(dlg, text="播放选中", font=("Microsoft YaHei", 12),
                  bg=BG_SEL, fg="#fff", relief=tk.FLAT, cursor="hand2",
                  padx=20, pady=6, command=_pick).pack(pady=(4, 8))
        # Double-click to pick
        lb.bind("<Double-1>", lambda e: _pick())

    def _browse_history(self):
        """Browse past candidate pools by date."""
        snaps = eng.list_history_snapshots()
        if not snaps:
            self._status("暂无历史记录（明天再来就有了）")
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("历史回溯")
        dlg.geometry("500x420")
        dlg.configure(bg=BG_MAIN)
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(dlg, text="选择日期浏览历史推荐", font=("Microsoft YaHei", 12, "bold"),
                 fg=FG_BRIGHT, bg=BG_MAIN).pack(pady=(12, 6))

        lf = tk.Frame(dlg, bg=BG_MAIN)
        lf.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
        lb = tk.Listbox(lf, bg=BG_CARD, fg=FG, font=("Microsoft YaHei", 12),
                        selectbackground=BG_SEL, selectforeground="#fff",
                        borderwidth=0, highlightthickness=0)
        lbs = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=lb.yview)
        lb.configure(yscrollcommand=lbs.set)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        lbs.pack(side=tk.RIGHT, fill=tk.Y)

        mode_labels = {"rap": "RAP 模式", "mixed": "混合模式"}
        for date_str, path, m in snaps:
            lb.insert(tk.END, f"{date_str}  [{mode_labels.get(m, m)}]")

        status_lbl = tk.Label(dlg, text=f"共 {len(snaps)} 天历史", font=("Microsoft YaHei", 10),
                              fg=FG_DIM, bg=BG_MAIN)
        status_lbl.pack(pady=(4, 2))

        def _do_view():
            sel = lb.curselection()
            if not sel:
                return
            idx = sel[0]
            date_str, path, m = snaps[idx]
            data = eng.load_history_snapshot(path)
            if not data:
                status_lbl.config(text="加载失败", fg=FG_ACC)
                return
            songs = data.get("songs", [])
            # Show summary in a scrollable text widget
            dlg2 = tk.Toplevel(dlg)
            dlg2.title(f"历史: {date_str} [{mode_labels.get(m, m)}]")
            dlg2.geometry("550x500")
            dlg2.configure(bg=BG_MAIN)
            dlg2.transient(dlg)
            txt = tk.Text(dlg2, bg=BG_CARD, fg=FG, font=("Microsoft YaHei", 12),
                          wrap=tk.WORD, borderwidth=0, padx=12, pady=12)
            txt.pack(fill=tk.BOTH, expand=True)
            txt.insert(tk.END, f"📅 {date_str}  {mode_labels.get(m, m)}\n")
            txt.insert(tk.END, f"共 {len(songs)} 首\n")
            txt.insert(tk.END, "─" * 40 + "\n\n")
            for i, s in enumerate(songs):
                singers = " / ".join(x.get("name", "") for x in s.get("singer", []))
                score = s.get("_score", s.get("score", 0))
                status = "✓" if s.get("_played", False) else "  "
                txt.insert(tk.END, f"{status} {i+1:2d}. {s.get('songname','?')[:30]} — {singers[:25]}  [{score:.2f}]\n")
            txt.config(state=tk.DISABLED)

        tk.Button(dlg, text="查看", font=("Microsoft YaHei", 12),
                  bg=BG_SEL, fg="#fff", relief=tk.FLAT, cursor="hand2",
                  padx=20, pady=6, command=_do_view).pack(pady=(4, 8))

    def _add_pl(self):
        if self.idx >= len(self.songs):
            return
        sid = self.songs[self.idx].get("songid", 0)
        if not sid:
            return
        PL_MAP = {"rap": (self.playlist_rap, "Claude Rap"), "mixed": (self.playlist_mixed, "Claude Picks"), "focus": (self.playlist_focus, "Claude Focus")}
        pl_id, pl_name = PL_MAP.get(self.mode, (None, None))
        if not pl_id:
            # Try to re-fetch playlists — user may have logged in since last check
            self._find_playlist()
            pl_id, pl_name = PL_MAP.get(self.mode, (None, None))
            if not pl_id:
                self._status("请先登录网易云!")
                return
        d = ncm("/playlist/tracks", {"op": "add", "pid": pl_id, "tracks": sid})
        if d and d.get("code") == 200:
            # Invalidate cache so next _get_playlist_block_ids refreshes from API
            cache_attr = f'_block_ids_{self.mode}'
            cached = getattr(self, cache_attr, set())
            cached.add(str(sid))
            setattr(self, cache_attr, cached)
            self._status(f"已加入「{pl_name}」歌单!")
            self.pl_btn.config(text="✓ 已加入!", fg=FG_OK)
            self.root.after(3000, lambda: self.pl_btn.config(text="+ 加入歌单", fg=FG_BLUE))
        elif d and d.get("code") == 502:
            self._status("歌曲已存在歌单中")
        else:
            self._status(f"添加失败 (API code={d.get('code') if d else '无响应'})")

    # ============================================================
    # ALBUM ART
    # ============================================================

    def _load_art(self, aid):
        if not aid:
            return
        cp = os.path.join(ART_DIR, f"ne_{aid}.jpg")
        if os.path.exists(cp):
            self._show_art(cp)
            return

        def _f():
            try:
                d = ncm("/album", {"id": aid})
                if d:
                    pu = (d.get("album", {}).get("picUrl") or
                          d.get("songs", [{}])[0].get("al", {}).get("picUrl"))
                    if pu:
                        r = requests.get(pu, timeout=15)
                        with open(cp, "wb") as fw:
                            fw.write(r.content)
                        self.root.after(0, lambda: self._show_art(cp))
            except Exception:
                pass
        threading.Thread(target=_f, daemon=True).start()

    def _show_art(self, path):
        """Draw album art as dimmed background on center Canvas."""
        try:
            from PIL import Image, ImageTk, ImageEnhance
            pil_img = Image.open(path)
            c = self.bg_canvas
            c.update_idletasks()
            cw = c.winfo_width() or 500
            ch = c.winfo_height() or 400
            # Scale to fill canvas (cover-style)
            iw, ih = pil_img.size
            scale = max(cw / iw, ch / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            pil_img = pil_img.resize((nw, nh), Image.LANCZOS)
            # Dim image so lyrics remain readable
            enhancer = ImageEnhance.Brightness(pil_img)
            pil_img = enhancer.enhance(0.25)
            img = ImageTk.PhotoImage(pil_img)
            # Remove old art, overlay, placeholder
            c.delete("art", "overlay", "placeholder")
            c.create_image(cw // 2, ch // 2, image=img, anchor=tk.CENTER, tags="art")
            c.image = img  # keep ref
            # Light overlay for extra readability
            c.create_rectangle(0, 0, cw, ch, fill=BG_MAIN, stipple="gray12",
                               outline="", tags="overlay")
            # Ensure lyrics text stays on top
            c.tag_raise("lyric_cur")
            c.tag_raise("lyric_next")
            self._show_lyrics()
        except Exception as e:
            # Fallback: tkinter native (PNG only)
            try:
                img = tk.PhotoImage(file=path)
                c = self.bg_canvas
                c.update_idletasks()
                cw = c.winfo_width() or 500
                ch = c.winfo_height() or 400
                iw, ih = img.width(), img.height()
                scale = max(cw / iw, ch / ih)
                if scale > 1.0:
                    img = img.zoom(max(1, int(scale)), max(1, int(scale)))
                elif scale < 0.3:
                    img = img.subsample(max(1, int(1 / scale)))
                c.delete("art", "overlay", "placeholder")
                c.create_image(cw // 2, ch // 2, image=img, anchor=tk.CENTER, tags="art")
                c.image = img
                c.create_rectangle(0, 0, cw, ch, fill=BG_MAIN, stipple="gray12",
                                   outline="", tags="overlay")
                c.tag_raise("lyric_cur")
                c.tag_raise("lyric_next")
                self._show_lyrics()
            except Exception:
                pass

    # ============================================================
    # EVENTS
    # ============================================================

    def _sel(self, e):
        sel = self.tree.selection()
        if not sel:
            return
        sid = sel[0]
        s = self._song_by_id(sid)
        if s:
            self.name_lbl.config(text=s.get("songname", ""))
            self.art_lbl.config(text=" / ".join(x.get("name", "") for x in s.get("singer", [])))
            self.il["al"].config(text=s.get("albumname", "?"))
            self.il["sc"].config(text=f"{s.get('_score', s.get('score', 0)):.2f}")

    def _dbl(self, e):
        sel = self.tree.selection()
        if sel:
            sid = sel[0]
            s = self._song_by_id(sid)
            if s:
                self._play_song(s)

    def _tgl_mode(self):
        """Cycle rap → mixed → focus → rap, forcing a full candidate rebuild each time."""
        MODES = ["rap", "mixed", "focus"]
        MODE_LABELS = {"rap": "RAP 模式", "mixed": "混合模式", "focus": "专注模式"}
        idx = MODES.index(self.mode) if self.mode in MODES else 0
        self.mode = MODES[(idx + 1) % 3]
        self._save_session()
        self.mode_btn.config(text=MODE_LABELS.get(self.mode, self.mode))
        self._stop_ffplay()
        self.play_count = 0
        self._simi_queue = []
        # Clear block-id caches so the new mode fetches fresh playlist data
        self._block_ids_rap = None
        self._block_ids_mixed = None
        self._block_ids_focus = None
        # force_rebuild=True: skip today's cache, always build fresh candidates
        self._init_data(force_rebuild=True)

    def _refresh(self):
        self._status("正在重建候选池...")
        self._stop_ffplay()
        self.play_count = 0
        with self._simi_queue_lock:
            self._simi_queue = []
        # 🆕 Force-refresh block lists so we don't re-add songs already in playlists
        self._block_ids_rap = None
        self._block_ids_mixed = None
        def _r():
            try:
                block_ids = self._get_playlist_block_ids()
                result = eng.build_candidates(self.mode, extra_block_ids=block_ids)
                result = eng.score_candidates(result, self.mode)
                with self._candidates_lock:
                    self.candidates = result
                self.root.after(0, self._reload_list)
            except Exception as e:
                self.root.after(0, lambda e=str(e): self._status(f"刷新失败: {e[:50]}"))
        threading.Thread(target=_r, daemon=True).start()

    def _open_ne(self):
        import webbrowser
        webbrowser.open("https://music.163.com")

    def _on_close(self):
        """Minimize to system tray; second close or tray failure → full quit."""
        if getattr(self, '_closing', False):
            self._tray_quit()
            return
        self._closing = True
        self._save_session()
        self._stop_ffplay()
        self.root.withdraw()
        # If tray is not running, show a minified window so user can still interact
        if not getattr(self.tray, '_icon', None):
            self.root.deiconify()

    def _tray_quit(self):
        """Full shutdown from tray quit menu."""
        self._save_session()
        self._stop_ffplay()
        if hasattr(self, 'hotkey_listener'):
            self.hotkey_listener.stop()
        if hasattr(self, 'tray'):
            self.tray.stop()
        self.root.destroy()

    def _smart_dj_interject(self):
        """Run Smart DJ interjection in background and show in chat.
        If DJ suggests a genre, search and insert relevant songs into the queue."""
        try:
            msg, action = self._smart_dj.ask_dj()
            if msg:
                self.root.after(0, lambda: self._chat_append("沧溟", f"🎧 {msg}"))
                if action:
                    genre = action.get("suggest_genre", "")
                    mood = action.get("suggest_mood", "")
                    if genre:
                        self.root.after(0, lambda: self._status(
                            f"DJ 推荐: {genre}/{mood}" if mood else f"DJ 推荐: {genre}"))
                        # 🆕 DJ 主动推送: 搜索该 genre 的歌曲插入队列
                        threading.Thread(
                            target=lambda: self._dj_push_songs(genre, mood),
                            daemon=True).start()
        except Exception:
            pass

    def _dj_push_songs(self, genre, mood=None):
        """Search for 3 top songs in the DJ-recommended genre and insert into queue."""
        try:
            query = f"{genre} {mood}" if mood else genre
            data = ncm("/search", {"keywords": query, "limit": 5})
            if not data or data.get("code") != 200:
                return
            raw = data.get("result", {}).get("songs", [])
            if not raw:
                return
            pushed = 0
            for s in raw[:5]:
                if pushed >= 3:
                    break
                song = {
                    "songname": s.get("name", ""),
                    "songid": s.get("id", 0),
                    "duration": s.get("duration", 0),
                    "singer": [{"name": a.get("name", "")} for a in s.get("artists", [])],
                    "albumname": s.get("album", {}).get("name", ""),
                    "albumid": s.get("album", {}).get("id", 0),
                    "_sources": [f"dj:{genre}"],
                    "_score": 8.5,
                    "_played": False,
                    "_from_simi": False,
                }
                with self._candidates_lock:
                    sid = str(song["songid"])
                    if sid not in {str(c["songid"]) for c in self.candidates}:
                        # Insert after current position
                        insert_pos = min(self.idx + 1 + pushed, len(self.candidates))
                        self.candidates.insert(insert_pos, song)
                        pushed += 1
            if pushed > 0:
                self.root.after(0, lambda: self._chat_append(
                    "沧溟", f"🎧 为你准备了 {pushed} 首 {genre} 风格的歌曲～"))
                self.root.after(0, lambda: self._reload_list(resort=False))
        except Exception:
            pass

    def _sleep_timer_popup(self):
        """Show sleep timer options popup."""
        self._sleep_timer = getattr(self, '_sleep_timer', 0)  # remaining seconds
        dlg = tk.Toplevel(self.root)
        dlg.title("睡眠定时器")
        dlg.geometry("300x320")
        dlg.configure(bg=BG_MAIN)
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(dlg, text="🌙 定时停止播放", font=("Microsoft YaHei", 13, "bold"),
                 fg=FG_BRIGHT, bg=BG_MAIN).pack(pady=(14, 8))

        status_text = f"当前: {self._sleep_timer // 60} 分钟后停止" if self._sleep_timer > 0 else "未设置"
        status_lbl = tk.Label(dlg, text=status_text, font=("Microsoft YaHei", 11),
                              fg=FG_DIM, bg=BG_MAIN)
        status_lbl.pack(pady=(0, 10))

        bs = {"font": ("Microsoft YaHei", 12), "bg": BG_CARD, "fg": FG,
              "activebackground": BG_SEL, "activeforeground": "#fff",
              "relief": tk.FLAT, "cursor": "hand2", "bd": 0,
              "width": 20, "height": 1}

        def _set_and_close(mins):
            self._sleep_timer = mins * 60
            self.root.after(1000, self._tick_sleep_timer)
            self._status(f"🌙 睡眠定时: {mins} 分钟后停止")
            show_toast("定时器", f"{mins} 分钟后停止播放")
            dlg.destroy()

        def _cancel():
            self._sleep_timer = 0
            self._status("睡眠定时器已取消")
            dlg.destroy()

        for mins in [15, 30, 45, 60]:
            tk.Button(dlg, text=f"{mins} 分钟", command=lambda m=mins: _set_and_close(m), **bs
                     ).pack(pady=3)

        tk.Label(dlg, text="", bg=BG_MAIN, height=1).pack()
        tk.Button(dlg, text="取消定时", command=_cancel, font=("Microsoft YaHei", 12),
                  bg="#1a1028", fg=C.WARN, relief=tk.FLAT, cursor="hand2",
                  bd=0, padx=20, pady=6).pack(pady=(4, 8))

    def _tick_sleep_timer(self):
        """Countdown sleep timer. Called every second while active."""
        if self._sleep_timer <= 0:
            return
        self._sleep_timer -= 1
        mins_rem = self._sleep_timer // 60
        secs_rem = self._sleep_timer % 60

        if self._sleep_timer <= 3:
            # Last 3 seconds: fade out
            fade_vol = max(0, int(self._volume * 100 * (self._sleep_timer / 3)))
            self._set_volume(fade_vol)
            self._status(f"🌙 即将停止... ({secs_rem}s)")

        if self._sleep_timer <= 0:
            self._stop_ffplay()
            self._set_volume(100)  # restore volume for next play
            self._status("🌙 睡眠定时结束，播放已停止")
            show_toast("睡眠定时器", "播放已停止，晚安 🌙")
            return

        # Update status every 10s
        if self._sleep_timer % 10 == 0:
            self._status(f"🌙 {mins_rem}:{secs_rem:02d} 后停止")

        self.root.after(1000, self._tick_sleep_timer)

    def _status(self, t):
        try:
            self.st_lbl.config(text=t[:70])
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


_cleanup_ffplay = None

def _on_exit():
    if _cleanup_ffplay is not None:
        try:
            _cleanup_ffplay()
        except Exception:
            pass

atexit.register(_on_exit)
signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))


def main():
    app = MusicPlayer()
    app.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Try to stop ffplay first
        try:
            if _cleanup_ffplay is not None:
                _cleanup_ffplay()
        except Exception:
            pass
        import traceback
        log_path = os.path.join(HOME, "crash.log")
        with open(log_path, "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        raise
