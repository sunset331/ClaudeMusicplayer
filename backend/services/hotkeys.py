#!/usr/bin/env python3
"""
Claude Music — Global Hotkeys Service
Registers Ctrl+Alt and media key shortcuts for playback control.
"""

import logging
import sys

log = logging.getLogger("claude-music")


def run_hotkeys():
    try:
        from pynput.keyboard import GlobalHotKeys, Key
    except ImportError as e:
        log.warning("pynput not installed, global hotkeys disabled: %s", e)
        print(f"[backend hotkeys] pynput not installed: {e}", file=sys.stderr)
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
    # Media keys — individually try each, log failures
    for media_key, handler in [
        ("<media_play_pause>", on_play_pause),
        ("<media_next>", on_next),
        ("<media_previous>", on_prev),
    ]:
        try:
            hotkey_map[media_key] = handler
            log.info("Registered media key: %s", media_key)
        except Exception as e:
            log.warning("Media key %s unavailable: %s", media_key, e)

    try:
        log.info("Starting backend hotkey listener with %d bindings", len(hotkey_map))
        with GlobalHotKeys(hotkey_map) as h:
            h.join()
    except Exception as e:
        log.error("Global hotkeys failed: %s", e, exc_info=True)
        print(f"[backend hotkeys] FATAL: {e}", file=sys.stderr)
