#!/usr/bin/env python3
"""
Claude Music — Thread-safe State Manager
Central state storage with read/write context managers.
"""

import threading
from contextlib import contextmanager


class StateManager:
    """Thread-safe shared state for the music player server."""

    def __init__(self):
        self._state = {
            "mode": "rap",
            "songs": [],
            "candidates": [],
            "current_idx": 0,
            "playing": False,
            "current_time": 0.0,
            "volume": 1.0,
            "epsilon": 0.15,
            "play_count": 0,
            "lyrics_cache": {},
            "_current_lyrics": [],
        }
        self._lock = threading.RLock()

    @contextmanager
    def read(self):
        self._lock.acquire()
        try:
            yield self._state
        finally:
            self._lock.release()

    @contextmanager
    def write(self):
        with self.read() as st:
            yield st

    def current_song(self):
        with self.read() as st:
            songs, idx = st["songs"], st["current_idx"]
            return songs[idx] if 0 <= idx < len(songs) else None

    def get_mode(self):
        with self.read() as st:
            return st["mode"]

    def get_snapshot(self):
        with self.read() as st:
            return {
                "_current_lyrics": list(st.get("_current_lyrics", [])),
                "current_time": st.get("current_time", 0),
                "playing": st.get("playing", False),
            }


# Singleton accessor — all modules get the same instance
_state_manager = StateManager()


def get_state() -> StateManager:
    return _state_manager
