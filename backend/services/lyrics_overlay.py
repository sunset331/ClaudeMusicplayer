#!/usr/bin/env python3
"""
Claude Music — Desktop Lyrics Overlay Service
Starts the DesktopLyrics overlay window.
"""

import logging

log = logging.getLogger("claude-music")


def start_lyrics_overlay(state):
    try:
        from backend.desktop_lyrics import DesktopLyrics

        lyrics = DesktopLyrics(state.get_snapshot)
        lyrics.start()
        log.info("Desktop lyrics started")
        return lyrics
    except Exception as e:
        log.warning("Desktop lyrics failed: %s", e)
    return None
