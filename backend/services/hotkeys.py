#!/usr/bin/env python3
"""
Claude Music — Global Hotkeys Service
Registers Ctrl+Alt and media key shortcuts for playback control.
"""

import logging

log = logging.getLogger("claude-music")


def run_hotkeys():
    try:
        from pynput.keyboard import GlobalHotKeys, Key
    except ImportError:
        log.warning("pynput not installed, global hotkeys disabled")
        return

    def api_post(path):
        try:
            import requests as _r

            _r.post(f"http://localhost:8765{path}", timeout=1)
        except Exception:
            pass

    def on_play_pause():
        api_post("/api/toggle")

    def on_next():
        api_post("/api/next")

    def on_prev():
        api_post("/api/prev")

    def on_like():
        api_post("/api/like/0")  # current song

    def on_skip():
        api_post("/api/skip/0")

    hotkey_map = {
        "<ctrl>+<alt>+<space>": on_play_pause,
        "<ctrl>+<alt>+<right>": on_next,
        "<ctrl>+<alt>+<left>": on_prev,
        "<ctrl>+<alt>+l": on_like,
        "<ctrl>+<alt>+s": on_skip,
    }
    # Media keys
    try:
        hotkey_map["<media_play_pause>"] = on_play_pause
        hotkey_map["<media_next>"] = on_next
        hotkey_map["<media_previous>"] = on_prev
    except Exception:
        pass

    try:
        with GlobalHotKeys(hotkey_map) as h:
            h.join()
    except Exception as e:
        log.warning("Global hotkeys failed: %s", e)
