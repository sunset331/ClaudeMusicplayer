#!/usr/bin/env python3
"""
Claude Music — Queue & Mode Routes
Queue listing, mode switching, rebuild, status, and stats.
"""

import logging
import threading

from fastapi import APIRouter

from backend.state import get_state
from backend.helpers import (
    _song_to_dict,
    _daily_refresh,
    _refresh_mode,
    _save_state,
    _load_candidates_into_state,
)

log = logging.getLogger("claude-music")

router = APIRouter()
state = get_state()


@router.get("/api/queue")
async def get_queue():
    with state.read() as st:
        if not st["songs"]:
            _load_candidates_into_state(st, st["mode"])
        return {
            "songs": [_song_to_dict(s) for s in st["songs"]],
            "mode": st["mode"],
            "epsilon": st["epsilon"],
        }


@router.get("/api/status")
async def get_status():
    with state.read() as st:
        return {
            "ok": True,
            "mode": st["mode"],
            "epsilon": st["epsilon"],
            "songCount": len(st["songs"]),
        }


@router.get("/api/stats")
async def get_stats():
    with state.read() as st:
        return {"playCount": st["play_count"], "mode": st["mode"], "epsilon": st["epsilon"]}


@router.post("/api/mode")
async def switch_mode(body: dict):
    """Switch between rap/mixed mode."""
    new_mode = body.get("mode", "rap")
    if new_mode not in ("rap", "mixed"):
        return {"ok": False, "error": "Invalid mode"}
    with state.read() as st:
        st["mode"] = new_mode
        st["songs"] = []
        st["current_idx"] = 0
    _save_state(state)
    # Ingest playlist seed + build candidates for new mode
    threading.Thread(target=lambda: _daily_refresh(force=False, state=state), daemon=True).start()
    try:
        with state.read() as st:
            _load_candidates_into_state(st, new_mode)
    except Exception as e:
        log.warning("Mode switch load failed: %s", e)
    return {"ok": True, "mode": new_mode}


@router.post("/api/rebuild")
async def rebuild():
    def _do():
        try:
            with state.read() as st:
                mode = st["mode"]
            scored = _refresh_mode(mode, force=True)
            if scored:
                with state.read() as st:
                    if st["mode"] == mode:
                        st["candidates"] = scored
                        st["songs"] = [s for s in scored if not s.get("_played")]
                        st["current_idx"] = 0
                log.info("Rebuild: %d songs for mode=%s", len(scored), mode)
        except Exception as e:
            log.error("Rebuild failed: %s", e)
    threading.Thread(target=_do, daemon=True).start()
    return {"ok": True}
