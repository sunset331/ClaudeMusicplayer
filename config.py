#!/usr/bin/env python3
"""
Centralized configuration for the music player project.

All paths, constants, and theme values live here.
Import from this module instead of hardcoding values in app.py / engine.py.
"""

import os
import shutil

# ============================================================
# Paths
# ============================================================

HOME: str = os.path.dirname(os.path.abspath(__file__))

DATA_DIR: str = os.path.join(HOME, "data")
CACHE_DIR: str = os.path.join(HOME, "cache")
COVERS_DIR: str = os.path.join(DATA_DIR, "covers")

# ffplay auto-detection
_ffplay = shutil.which("ffplay") or shutil.which("ffplay.exe")
if _ffplay:
    FFPLAY: str = _ffplay
else:
    # Fallback to common Windows install locations
    _candidates = [
        r"C:\Users\27576\AppData\Local\Microsoft\WinGet\Links\ffplay.exe",
        r"C:\ffmpeg\bin\ffplay.exe",
        r"C:\Program Files\ffmpeg\bin\ffplay.exe",
    ]
    FFPLAY = next((p for p in _candidates if os.path.exists(p)), "ffplay")

# API endpoints
NCM_API: str = os.environ.get("NCM_API_URL", "http://localhost:3000")
DEEPSEEK_KEY: str = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_URL: str = "https://api.deepseek.com/v1/chat/completions"

# ============================================================
# Data file paths
# ============================================================

TODAY_FILE: str = os.path.join(DATA_DIR, "today.json")
TODAY_FOCUS_FILE: str = os.path.join(DATA_DIR, "today_focus.json")
TASTE_FILE: str = os.path.join(DATA_DIR, "taste.json")
HISTORY_FILE: str = os.path.join(DATA_DIR, "history.json")
SESSION_FILE: str = os.path.join(DATA_DIR, "session.json")
LOGIN_FILE: str = os.path.join(DATA_DIR, "ncm_cookie.json")
ARTIST_ID_FILE: str = os.path.join(DATA_DIR, "artist_ids.json")
CANDIDATE_DIR: str = os.path.join(DATA_DIR, "candidates")

# ============================================================
# Engine constants
# ============================================================

DAILY_PICKS: int = 50
MAX_PER_ARTIST: int = 3
MIN_ARTISTS: int = 12

# Epsilon-greedy bandit
EPSILON_DEFAULT: float = 0.15
EPSILON_MIN: float = 0.05
EPSILON_MAX: float = 0.50

SIMI_EXPAND_INTERVAL: int = 10
WORKER_THREADS: int = 3

# ============================================================
# History caps
# ============================================================

HISTORY_MAX: int = 500
HISTORY_TRIM: int = 300
RECOMMENDED_IDS_MAX: int = 5000

# ============================================================
# Playback constants
# ============================================================

VOLUME_MIN: int = 0
VOLUME_MAX: int = 150
VOLUME_DEFAULT: int = 100

PROGRESS_POLL_MS: int = 250
WATCHDOG_POLL_S: int = 2
FFPEEK_TIMEOUT: int = 3
API_TIMEOUT: int = 15
DEBOUNCE_VOLUME_MS: int = 350

# ============================================================
# UI / Theme — 萌系赛博朋克
# ============================================================

BG_MAIN: str = "#0A0A14"
BG_CARD: str = "#111122"
BG_INPUT: str = "#0D0D1A"

FG_PRIMARY: str = "#E0E0FF"
FG_SECONDARY: str = "#8080A0"
FG_ACCENT: str = "#50FFAF"

BTN_LIKE: str = "#4A4"
BTN_SKIP: str = "#A44"
BTN_PLAYLIST: str = "#48F"

# ============================================================
# Helpers
# ============================================================


def ensure_dirs() -> None:
    """Create all data directories if they don't exist."""
    for d in (DATA_DIR, CACHE_DIR, COVERS_DIR, CANDIDATE_DIR):
        os.makedirs(d, exist_ok=True)
