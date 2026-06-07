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
import signal
import tkinter as tk
from tkinter import ttk
from datetime import datetime

import requests

HOME = os.path.dirname(os.path.abspath(__file__))
NCM = "http://localhost:3000"
DATA_DIR = os.path.join(HOME, "data")
TODAY_FILE = os.path.join(DATA_DIR, "today.json")
TODAY_FOCUS_FILE = os.path.join(DATA_DIR, "today_focus.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
ART_DIR = os.path.join(DATA_DIR, "covers")
LOGIN_FILE = os.path.join(DATA_DIR, "ncm_cookie.json")

FFPLAY = r"C:\Users\27576\AppData\Local\Microsoft\WinGet\Links\ffplay.exe"

os.makedirs(ART_DIR, exist_ok=True)

# ============================================================
# DARK THEME
# ============================================================
BG_MAIN = "#1a1a2e"
BG_SIDEBAR = "#16213e"
BG_LIST = "#0f3460"
BG_SEL = "#e94560"
FG = "#eaeaea"
FG2 = "#a0a0b0"
FG_ACC = "#e94560"
FG_OK = "#4ecca3"

# NCM session with login cookie
_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})


def load_cookie():
    if os.path.exists(LOGIN_FILE):
        try:
            with open(LOGIN_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            for item in d.get("cookie", "").split(";"):
                if "=" in item:
                    k, v = item.strip().split("=", 1)
                    _session.cookies.set(k.strip(), v.strip())
            return True
        except Exception:
            pass
    return False


def ncm(path, params=None):
    try:
        r = _session.get(f"{NCM}{path}", params=params, timeout=15)
        return r.json() if r.ok else None
    except Exception:
        return None


load_cookie()


class MusicPlayer:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Claude Music - Daily Picks")
        self.root.geometry("960x680")
        self.root.minsize(800, 500)
        self.root.configure(bg=BG_MAIN)

        self.songs = []
        self.idx = 0
        self.mode = "rap"
        self.ffplay = None          # current ffplay process
        self.mascot = None
        self.playlist_id = None

        self._build()
        self.root.after(100, self._init_data)
        self.root.after(1500, self._launch_mascot)
        self.root.after(500, self._check_login)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._watch_playback()

    # ============================================================
    # UI
    # ============================================================

    def _build(self):
        pw = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=BG_MAIN, sashwidth=2)
        pw.pack(fill=tk.BOTH, expand=True)

        self.left = tk.Frame(pw, bg=BG_SIDEBAR)
        pw.add(self.left, stretch="always")
        self._build_list()

        self.right = tk.Frame(pw, bg=BG_MAIN)
        pw.add(self.right, stretch="always")
        self._build_detail()

        self._build_bar()

    def _build_list(self):
        h = tk.Frame(self.left, bg=BG_SIDEBAR, height=36)
        h.pack(fill=tk.X, padx=10, pady=(10, 5))
        h.pack_propagate(False)
        self.date_lbl = tk.Label(h, text="Today's Picks",
                                 font=("Microsoft YaHei", 12, "bold"), fg=FG, bg=BG_SIDEBAR)
        self.date_lbl.pack(side=tk.LEFT)
        self.cnt_lbl = tk.Label(h, text="", font=("Microsoft YaHei", 9), fg=FG2, bg=BG_SIDEBAR)
        self.cnt_lbl.pack(side=tk.RIGHT)

        st = ttk.Style()
        st.theme_use("clam")
        st.configure("Treeview", background=BG_LIST, foreground=FG,
                     fieldbackground=BG_LIST, borderwidth=0,
                     font=("Microsoft YaHei", 9))
        st.configure("Treeview.Heading", background=BG_SIDEBAR, foreground=FG2,
                     font=("Microsoft YaHei", 9, "bold"), borderwidth=0)
        st.map("Treeview", background=[("selected", BG_SEL)],
               foreground=[("selected", "#fff")])

        cols = ("rank", "name", "artist", "score")
        self.tree = ttk.Treeview(self.left, columns=cols, show="headings",
                                  selectmode="browse", height=24)
        self.tree.heading("rank", text="#")
        self.tree.heading("name", text="Song")
        self.tree.heading("artist", text="Artist")
        self.tree.heading("score", text="Match")
        self.tree.column("rank", width=30, anchor=tk.CENTER, stretch=False)
        self.tree.column("name", width=220, anchor=tk.W, stretch=True)
        self.tree.column("artist", width=160, anchor=tk.W, stretch=True)
        self.tree.column("score", width=45, anchor=tk.CENTER, stretch=False)

        sb = ttk.Scrollbar(self.left, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=(0, 10))
        sb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=(0, 10))

        self.tree.bind("<<TreeviewSelect>>", self._sel)
        self.tree.bind("<Double-1>", self._dbl)
        self.tree.bind("<Return>", self._dbl)

    def _build_detail(self):
        tk.Label(self.right, text="NOW PLAYING", font=("Microsoft YaHei", 8, "bold"),
                 fg=FG_ACC, bg=BG_MAIN).pack(pady=(20, 5))

        af = tk.Frame(self.right, bg=BG_MAIN, width=220, height=220)
        af.pack(pady=(0, 10), padx=20)
        af.pack_propagate(False)
        self.ac = tk.Canvas(af, width=210, height=210, bg=BG_SIDEBAR, highlightthickness=0)
        self.ac.pack(fill=tk.BOTH, expand=True)
        self.ac.create_text(105, 105, text="♪", font=("Microsoft YaHei", 36), fill=FG2)

        self.name_lbl = tk.Label(self.right, text="Not playing",
                                 font=("Microsoft YaHei", 12, "bold"),
                                 fg=FG, bg=BG_MAIN, wraplength=340, justify=tk.CENTER)
        self.name_lbl.pack(pady=(5, 2))
        self.art_lbl = tk.Label(self.right, text="", font=("Microsoft YaHei", 10),
                                fg=FG2, bg=BG_MAIN)
        self.art_lbl.pack(pady=(0, 5))

        # Progress bar
        self.pvar = tk.DoubleVar(value=0)
        self.pbar = ttk.Progressbar(self.right, variable=self.pvar, length=280)
        self.pbar.pack(pady=(5, 2))
        self.time_lbl = tk.Label(self.right, text="", font=("Microsoft YaHei", 8),
                                 fg=FG2, bg=BG_MAIN)
        self.time_lbl.pack(pady=(0, 8))

        # Controls
        cf = tk.Frame(self.right, bg=BG_MAIN)
        cf.pack(pady=5)
        bc = {"font": ("Segoe UI Symbol", 14), "bg": BG_LIST, "fg": FG,
              "activebackground": BG_SEL, "activeforeground": "#fff",
              "relief": tk.FLAT, "cursor": "hand2", "width": 3}

        tk.Button(cf, text="|<", command=self._prev, **bc).pack(side=tk.LEFT, padx=3)
        self.pp_btn = tk.Button(cf, text=">", command=self._toggle, **bc)
        self.pp_btn.pack(side=tk.LEFT, padx=3)
        tk.Button(cf, text=">|", command=self._next, **bc).pack(side=tk.LEFT, padx=3)

        # Rating
        rf = tk.Frame(self.right, bg=BG_MAIN)
        rf.pack(pady=10)
        rs = {"font": ("Microsoft YaHei", 9, "bold"), "relief": tk.FLAT,
              "cursor": "hand2", "padx": 15, "pady": 6}

        self.like_btn = tk.Button(rf, text="Like", bg="#2d5a3d", fg=FG_OK,
                                   activebackground="#3d7a4d", activeforeground="#fff",
                                   command=self._like, **rs)
        self.like_btn.pack(side=tk.LEFT, padx=5)
        self.skip_btn = tk.Button(rf, text="Skip", bg="#5a2d2d", fg=FG_ACC,
                                   activebackground="#7a3d3d", activeforeground="#fff",
                                   command=self._skip, **rs)
        self.skip_btn.pack(side=tk.LEFT, padx=5)

        # Playlist
        self.pl_btn = tk.Button(self.right, text="+ Add to Playlist",
                                font=("Microsoft YaHei", 9), bg=BG_LIST, fg=FG,
                                activebackground="#2d5a3d", activeforeground="#fff",
                                relief=tk.FLAT, cursor="hand2", padx=15, pady=6,
                                command=self._add_pl)
        self.pl_btn.pack(pady=10)

        self.login_lbl = tk.Label(self.right, text="", font=("Microsoft YaHei", 8),
                                  fg=FG2, bg=BG_MAIN)
        self.login_lbl.pack(pady=(0, 8))

        inf = tk.Frame(self.right, bg=BG_MAIN)
        inf.pack(pady=5, fill=tk.X, padx=30)
        self.il = {}
        for i, (lb, k) in enumerate([("Album:", "al"), ("Source:", "src"), ("Match:", "sc")]):
            tk.Label(inf, text=lb, font=("Microsoft YaHei", 9), fg=FG2, bg=BG_MAIN).grid(
                row=i, column=0, sticky=tk.W, pady=2)
            v = tk.Label(inf, text="-", font=("Microsoft YaHei", 9, "bold"), fg=FG, bg=BG_MAIN)
            v.grid(row=i, column=1, sticky=tk.W, pady=2, padx=(10, 0))
            self.il[k] = v

    def _build_bar(self):
        bar = tk.Frame(self.root, bg=BG_SIDEBAR, height=32)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)
        bs = {"font": ("Microsoft YaHei", 9), "bg": BG_LIST, "fg": FG,
              "activebackground": BG_SEL, "activeforeground": "#fff",
              "relief": tk.FLAT, "cursor": "hand2", "padx": 10, "pady": 3}

        self.mode_btn = tk.Button(bar, text="Rap Mode", command=self._tgl_mode, **bs)
        self.mode_btn.pack(side=tk.LEFT, padx=(8, 2), pady=2)
        tk.Button(bar, text="Refresh", command=self._refresh, **bs).pack(
            side=tk.LEFT, padx=2, pady=2)
        tk.Button(bar, text="Login (QR)", command=self._login, **bs).pack(
            side=tk.LEFT, padx=2, pady=2)
        tk.Button(bar, text="Open NetEase", command=self._open_ne, **bs).pack(
            side=tk.LEFT, padx=2, pady=2)
        self.mascot_btn = tk.Button(bar, text="Mascot", command=self._launch_mascot, **bs)
        self.mascot_btn.pack(side=tk.RIGHT, padx=(2, 8), pady=2)
        self.st_lbl = tk.Label(bar, text="Ready", font=("Microsoft YaHei", 8),
                               fg=FG2, bg=BG_SIDEBAR)
        self.st_lbl.pack(side=tk.RIGHT, padx=15, pady=2)

    # ============================================================
    # DATA
    # ============================================================

    def _init_data(self):
        today = datetime.now().strftime("%Y-%m-%d")
        need = False
        for fn in [TODAY_FILE, TODAY_FOCUS_FILE]:
            if os.path.exists(fn):
                try:
                    with open(fn, encoding="utf-8") as f:
                        if json.load(f).get("date") != today:
                            need = True
                except Exception:
                    need = True
            else:
                need = True
        if need:
            self._status("Generating picks...")
            def _r():
                subprocess.run([sys.executable, os.path.join(HOME, "engine.py"), "--mode", "both"],
                               cwd=HOME, capture_output=True, timeout=180)
                self.root.after(0, self._load)
            threading.Thread(target=_r, daemon=True).start()
        else:
            self._load()

    def _load(self):
        fn = TODAY_FILE if self.mode == "rap" else TODAY_FOCUS_FILE
        lb = "Rap/Vibe" if self.mode == "rap" else "Focus/Chill"
        if not os.path.exists(fn):
            self._status(f"No {lb} data")
            return
        with open(fn, encoding="utf-8") as f:
            data = json.load(f)
        self.songs = data.get("songs", [])
        self.tree.delete(*self.tree.get_children())
        for s in self.songs:
            singers = " / ".join(x.get("name", "") for x in s.get("singer", []))
            self.tree.insert("", tk.END,
                             values=(s.get("rank", ""), s.get("songname", ""),
                                     singers, f"{s.get('score', 0):.2f}"))
        self.date_lbl.config(text=f"{lb} - {data.get('date', '?')}")
        self.cnt_lbl.config(text=f"{len(self.songs)} songs")
        self._status(f"{lb}: {len(self.songs)} songs")
        if self.songs and not self._is_playing():
            self.idx = 0
            self._play(0)

    # ============================================================
    # PLAYBACK (ffplay)
    # ============================================================

    def _is_playing(self):
        return self.ffplay is not None and self.ffplay.poll() is None

    def _play(self, index):
        if index < 0 or index >= len(self.songs):
            return
        self.idx = index
        # Select in tree
        kids = self.tree.get_children()
        if index < len(kids):
            self.tree.selection_set(kids[index])
            self.tree.see(kids[index])
        self._play_current()

    def _play_current(self):
        self._stop_ffplay()
        song = self.songs[self.idx]
        sid = song["songid"]
        idx = self.idx  # capture current index

        self._status(f"Fetching: {song['songname'][:30]}...")
        def _f():
            data = ncm("/song/url/v1", {"id": sid, "level": "standard"})
            u = data.get("data", [{}])[0].get("url") if data else None
            # Only play if user hasn't moved on
            if u and self.idx == idx:
                song["url"] = {"url": u, "type": "mp3"}
                self.root.after(0, lambda: self._start_ffplay(u, song))
            elif self.idx == idx:
                self.root.after(0, lambda: self._status(
                    f"No URL (VIP?): {song['songname'][:30]}"))
        threading.Thread(target=_f, daemon=True).start()

    def _start_ffplay(self, url, song):
        self._stop_ffplay()
        self._status(f"Playing: {song['songname'][:40]}...")
        try:
            self.ffplay = subprocess.Popen(
                [FFPLAY, "-nodisp", "-autoexit", "-loglevel", "quiet", url],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000)  # CREATE_NO_WINDOW
            self.pp_btn.config(text="||")
            self._show_info(song)
            self._update_progress()
        except Exception as err:
            self._status(f"Playback error: {err}")

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

    def _toggle(self):
        if self._is_playing():
            self._stop_ffplay()
            self.pp_btn.config(text=">")
            self._status("Stopped")
        else:
            self._play_current()

    def _next(self):
        if self.songs:
            self._play((self.idx + 1) % len(self.songs))

    def _prev(self):
        if self.songs:
            self._play((self.idx - 1) % len(self.songs))

    def _update_progress(self):
        if not self._is_playing():
            return
        song = self.songs[self.idx]
        dur_ms = song.get("duration", 300000) or 300000
        # ffplay doesn't give us position easily, use elapsed time
        # Simple: increment by 1 second each tick
        elapsed = getattr(self, '_elapsed', 0) + 1
        self._elapsed = elapsed
        pct = min(elapsed * 1000 / dur_ms * 100, 100)
        self.pvar.set(pct)
        self.time_lbl.config(
            text=f"{elapsed // 60}:{elapsed % 60:02d} / {dur_ms // 60000}:{(dur_ms // 1000) % 60:02d}")
        if pct < 100:
            self.root.after(1000, self._update_progress)

    def _watch_playback(self):
        """Auto-play next when ffplay exits."""
        if self.ffplay and self.ffplay.poll() is not None:
            # ffplay finished
            self.ffplay = None
            self.pp_btn.config(text=">")
            self._elapsed = 0
            self._next()
        self.root.after(2000, self._watch_playback)

    def _show_info(self, song):
        self.name_lbl.config(text=song.get("songname", ""))
        self.art_lbl.config(text=" / ".join(s.get("name", "") for s in song.get("singer", [])))
        self.il["al"].config(text=song.get("albumname", "?"))
        self.il["src"].config(text=(song.get("sources", ["?"]) or ["?"])[0][:40])
        self.il["sc"].config(text=f"{song.get('score', 0):.2f}")
        self._elapsed = 0
        # Album art
        aid = song.get("albumid", 0)
        if aid:
            self._load_art(aid)

    # ============================================================
    # RATING
    # ============================================================

    def _like(self):
        if self.idx >= len(self.songs):
            return
        song = self.songs[self.idx]
        self._update_hist(song, "like")
        s = " / ".join(x.get("name", "") for x in song.get("singer", []))
        self._status(f"Liked! {s[:50]}")
        self.like_btn.config(bg=FG_OK, text="Liked!")
        self.root.after(800, lambda: self.like_btn.config(bg="#2d5a3d", text="Like"))
        self.root.after(800, self._next)

    def _skip(self):
        if self.idx >= len(self.songs):
            return
        song = self.songs[self.idx]
        self._update_hist(song, "skip")
        s = " / ".join(x.get("name", "") for x in song.get("singer", []))
        self._status(f"Skipped: {s[:50]}")
        self.skip_btn.config(bg=FG_ACC, text="Skipped!")
        self.root.after(800, lambda: self.skip_btn.config(bg="#5a2d2d", text="Skip"))
        self._stop_ffplay()
        self.root.after(600, self._next)

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

    # ============================================================
    # LOGIN & PLAYLIST
    # ============================================================

    def _check_login(self):
        d = ncm("/login/status")
        if d and d.get("data", {}).get("account"):
            nick = d["data"].get("profile", {}).get("nickname", "User")
            self.login_lbl.config(text=f"Logged in: {nick}", fg=FG_OK)
            self._find_playlist()
        else:
            self.login_lbl.config(text="Not logged in -> 'Login (QR)'", fg=FG2)

    def _login(self):
        d = ncm("/login/qr/key")
        if not d:
            self._status("API not reachable")
            return
        uk = d.get("data", {}).get("unikey")
        if not uk:
            self._status("QR key failed")
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
            self._status("Download QR failed")
            return

        qw = tk.Toplevel(self.root)
        qw.title("Scan with NetEase App")
        qw.geometry("320x380")
        qw.configure(bg=BG_MAIN)
        qw.transient(self.root)
        qw.grab_set()

        tk.Label(qw, text="Scan QR Code with NetEase App",
                font=("Microsoft YaHei", 10, "bold"), fg=FG, bg=BG_MAIN).pack(pady=(15, 5))

        qp = os.path.join(DATA_DIR, "_qr.png")
        with open(qp, "wb") as f:
            f.write(qr_bytes)
        img = tk.PhotoImage(file=qp)
        tk.Label(qw, image=img, bg=BG_MAIN).pack(pady=10)
        qw.image = img

        sl = tk.Label(qw, text="Waiting for scan...", font=("Microsoft YaHei", 9),
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
                    qw.after(0, lambda: sl.config(text="QR expired!", fg=FG_ACC))
                    return
                elif c == 802:
                    qw.after(0, lambda: sl.config(text="Scanned! Confirm on phone...", fg=FG_OK))
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
            qw.after(0, lambda: sl.config(text="Timeout!", fg=FG_ACC))
        threading.Thread(target=_poll, daemon=True).start()

    def _find_playlist(self):
        d = ncm("/user/playlist", {"uid": 0})
        if not d:
            return
        for pl in d.get("playlist", []):
            if pl.get("name") == "Claude Picks":
                self.playlist_id = pl.get("id")
                return
        d2 = ncm("/playlist/create", {"name": "Claude Picks", "privacy": 0})
        if d2:
            self.playlist_id = d2.get("id") or d2.get("playlist", {}).get("id")

    def _add_pl(self):
        if self.idx >= len(self.songs):
            return
        sid = self.songs[self.idx].get("songid", 0)
        if not sid:
            return
        if not self.playlist_id:
            self._status("Login first!")
            return
        d = ncm("/playlist/tracks", {"op": "add", "pid": self.playlist_id, "tracks": sid})
        if d and d.get("code") == 200:
            self._status(f"Added to Claude Picks!")
            self.pl_btn.config(text="Added!", fg=FG_OK)
            self.root.after(3000, lambda: self.pl_btn.config(text="+ Add to Playlist", fg=FG))
        else:
            self._status("Failed - login required")

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
                d = ncm("/album/detail", {"id": aid})
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
        try:
            img = tk.PhotoImage(file=path)
            w, h = img.width(), img.height()
            s = min(210 / w, 210 / h)
            if s < 1.0:
                img = img.subsample(max(1, int(1 / s)))
            self.ac.delete("all")
            self.ac.create_image(105, 105, image=img, anchor=tk.CENTER)
            self.ac.image = img
        except Exception:
            pass

    # ============================================================
    # EVENTS
    # ============================================================

    def _sel(self, e):
        sel = self.tree.selection()
        if not sel:
            return
        i = self.tree.index(sel[0])
        if 0 <= i < len(self.songs):
            s = self.songs[i]
            self.name_lbl.config(text=s.get("songname", ""))
            self.art_lbl.config(text=" / ".join(x.get("name", "") for x in s.get("singer", [])))
            self.il["al"].config(text=s.get("albumname", "?"))
            self.il["sc"].config(text=f"{s.get('score', 0):.2f}")

    def _dbl(self, e):
        sel = self.tree.selection()
        if sel:
            i = self.tree.index(sel[0])
            if 0 <= i < len(self.songs):
                self._play(i)

    def _tgl_mode(self):
        self.mode = "focus" if self.mode == "rap" else "rap"
        self.mode_btn.config(text="Focus Mode" if self.mode == "focus" else "Rap Mode")
        self._load()

    def _refresh(self):
        self._status("Refreshing...")
        def _r():
            subprocess.run([sys.executable, os.path.join(HOME, "engine.py"),
                           "--mode", self.mode], cwd=HOME, capture_output=True, timeout=120)
            self.root.after(0, self._load)
        threading.Thread(target=_r, daemon=True).start()

    def _open_ne(self):
        import webbrowser
        webbrowser.open("https://music.163.com")

    def _launch_mascot(self):
        if self.mascot and self.mascot.poll() is None:
            return
        mp = os.path.join(HOME, "mascot.py")
        if os.path.exists(mp):
            self.mascot = subprocess.Popen([sys.executable, mp], cwd=HOME)

    def _on_close(self):
        self._stop_ffplay()
        if self.mascot and self.mascot.poll() is None:
            try:
                self.mascot.terminate()
            except Exception:
                pass
        self.root.destroy()

    def _status(self, t):
        try:
            self.st_lbl.config(text=t[:70])
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


def main():
    app = MusicPlayer()
    app.run()


if __name__ == "__main__":
    main()
