#!/usr/bin/env python3
"""
Claude Music — Playlist & Sleep Routes
Add to playlist, sleep timer.
"""

import logging
import threading
import time

from fastapi import APIRouter

from backend.state import get_state
from backend.helpers import _find_or_create_playlist

log = logging.getLogger("claude-music")

router = APIRouter()
state = get_state()


@router.post("/api/playlist/add/{song_id}")
async def add_to_playlist(song_id: int):
    """Add song to NetEase playlist. Auto-creates playlist if needed."""
    from api.ncm_client import ncm

    try:
        with state.read() as st:
            mode = st["mode"]
        pid = _find_or_create_playlist(mode)
        if not pid:
            return {"ok": False, "error": "Cannot find or create playlist. Login first."}
        ncm("/playlist/tracks", {"op": "add", "pid": pid, "tracks": str(song_id)})
        return {"ok": True}
    except Exception as e:
        log.warning("Add to playlist failed: %s", e)
        return {"ok": False, "error": str(e)}


@router.post("/api/sleep/{minutes}")
async def sleep_timer(minutes: int):
    """Set a sleep timer — stop playback after N minutes."""
    if minutes < 1 or minutes > 120:
        return {"ok": False, "error": "1-120 minutes only"}

    def _sleep():
        time.sleep(minutes * 60)
        log.info("Sleep timer fired after %d min", minutes)
        with state.read() as st:
            st["playing"] = False

    threading.Thread(target=_sleep, daemon=True).start()
    log.info("Sleep timer set: %d minutes", minutes)
    return {"ok": True, "minutes": minutes}
