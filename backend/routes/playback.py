#!/usr/bin/env python3
"""
Claude Music — Playback Routes
Play, next, prev, skip, like, smart-insert, toggle, and WebSocket.
"""

import logging
import threading

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.state import get_state
from backend.helpers import (
    _song_to_dict,
    _resolve_song_url,
    _record_feedback,
    _refresh_mode,
    _save_state,
    _load_candidates_into_state,
)

log = logging.getLogger("claude-music")

router = APIRouter()
state = get_state()

# ── WebSocket clients (only playback.py needs this) ──
_ws_clients: list[WebSocket] = []
_ws_lock = threading.Lock()


async def _ws_broadcast(msg: dict):
    with _ws_lock:
        clients = list(_ws_clients)
    for ws in clients:
        try:
            await ws.send_json(msg)
        except Exception:
            pass


@router.get("/api/play/{song_id}")
async def play_song(song_id: int):
    url = _resolve_song_url(song_id)
    with state.read() as st:
        for i, s in enumerate(st["songs"]):
            if s.get("songid") == song_id or s.get("id") == song_id:
                st["current_idx"] = i
                s["url"] = url
                st["playing"] = True
                st["current_time"] = 0
                song_data = _song_to_dict(s)
                break
        else:
            song_data = None
    _save_state(state)
    return {"url": url, "song": song_data}


@router.post("/api/next")
async def next_song():
    with state.read() as st:
        if not st["songs"]:
            return {"nextIndex": -1, "song": None}
        next_idx = (st["current_idx"] + 1) % len(st["songs"])
        st["current_idx"] = next_idx
        st["current_time"] = 0
        song = _song_to_dict(st["songs"][next_idx])
    _save_state(state)
    return {"nextIndex": next_idx, "song": song}


@router.post("/api/prev")
async def prev_song():
    with state.read() as st:
        if not st["songs"]:
            return {"prevIndex": -1, "song": None}
        prev_idx = (st["current_idx"] - 1) % len(st["songs"])
        st["current_idx"] = prev_idx
        st["current_time"] = 0
        song = _song_to_dict(st["songs"][prev_idx])
    _save_state(state)
    return {"prevIndex": prev_idx, "song": song}


@router.post("/api/like/{song_id}")
async def like_song(song_id: int):
    from api.ncm_client import ncm

    with state.read() as st:
        st["play_count"] += 1
        st["epsilon"] = max(0.05, st["epsilon"] - 0.01)
        eps = st["epsilon"]
        sid = str(song_id)
        song = next((s for s in st["candidates"] if str(s.get("songid")) == sid), None)
        if not song:
            song = next((s for s in st["songs"] if str(s.get("songid")) == sid), None)
    _save_state(state)
    _record_feedback(song_id, song, "like")
    # Sync to NetEase Cloud Music
    try:
        ncm("/like", {"id": song_id, "like": True})
        log.info("Like song=%d synced to NetEase", song_id)
    except Exception as e:
        log.warning("NetEase like sync failed for %d: %s", song_id, e)
    log.info("Like song=%d epsilon=%.2f", song_id, eps)
    return {"ok": True, "epsilon": eps}


@router.post("/api/skip/{song_id}")
async def skip_song(song_id: int):
    with state.read() as st:
        st["play_count"] += 1
        st["epsilon"] = min(0.50, st["epsilon"] + 0.01)
    return await next_song()


@router.post("/api/toggle")
async def toggle_playback():
    with state.read() as st:
        st["playing"] = not st["playing"]
        return {"ok": True, "playing": st["playing"]}


@router.post("/api/smart-insert")
async def smart_insert(body: dict):
    """Behavior-based smart insertion: skip/dwell triggers 2-3 song insert."""
    from api.ncm_client import ncm
    from models.song import Song

    trigger = body.get("trigger", "skip")  # "skip" | "dwell" | "like"
    with state.read() as st:
        song = state.current_song()
        if not song:
            return {"inserted": []}
        sid = str(song.get("songid", ""))
        songs_list = list(st["songs"])
        idx = st["current_idx"]

    inserted = []
    try:
        if trigger == "skip":
            # Find opposite style songs (different from skipped artist)
            skip_artist = ""
            singer = song.get("singer", [])
            if singer:
                skip_artist = singer[0].get("name", "") if isinstance(singer[0], dict) else str(singer[0])
            # Search for songs NOT by this artist
            if skip_artist:
                data = ncm("/search", {"keywords": skip_artist, "limit": 10, "type": 1})
                if data and "result" in data:
                    # Get similar songs from NetEase's simi endpoint
                    simi = ncm("/simi/song", {"id": song.get("songid")})
                    alt_songs = []
                    if simi and "songs" in simi:
                        for s in simi["songs"][:5]:
                            ar_name = s.get("artists", [{}])[0].get("name", "") if s.get("artists") else ""
                            if ar_name != skip_artist:
                                new_song = Song.from_ncm_song(s, "smart_skip", duration_seconds=True)
                                new_song._score = 0.85
                                if ar_name:
                                    new_song.singer = [{"name": ar_name}]
                                alt_songs.append(new_song)
                    # Insert 2 alternative songs
                    for s in alt_songs[:2]:
                        with state.read() as st:
                            st["songs"].insert(st["current_idx"] + 1, s)
                        inserted.append(_song_to_dict(s))

        elif trigger == "dwell":
            # User listened through — find more from same artist
            singer = song.get("singer", [])
            artist_name = singer[0].get("name", "") if singer and isinstance(singer[0], dict) else ""
            if artist_name:
                data = ncm("/search", {"keywords": artist_name, "limit": 8, "type": 1})
                if data and "result" in data:
                    for s in data["result"].get("songs", [])[:3]:
                        if s.get("id") != song.get("songid"):
                            new_song = Song.from_ncm_song(s, "smart_dwell")
                            new_song._score = 0.88
                            with state.read() as st:
                                st["songs"].insert(st["current_idx"] + 1, new_song)
                            inserted.append(_song_to_dict(new_song))
                            if len(inserted) >= 3:
                                break

        elif trigger == "like":
            # User liked — find similar songs, boost artist weight
            _record_feedback(song.get("songid"), song, "like")
            simi = ncm("/simi/song", {"id": song.get("songid")})
            if simi and "songs" in simi:
                for s in simi["songs"][:2]:
                    ar_name = s.get("artists", [{}])[0].get("name", "") if s.get("artists") else ""
                    new_song = Song.from_ncm_song(s, "smart_like", duration_seconds=True)
                    new_song._score = 0.92
                    if ar_name:
                        new_song.singer = [{"name": ar_name}]
                    with state.read() as st:
                        st["songs"].insert(st["current_idx"] + 1, new_song)
                    inserted.append(_song_to_dict(new_song))

        if inserted:
            log.info("Smart insert (%s): %d songs after current", trigger, len(inserted))
    except Exception as e:
        log.warning("Smart insert failed: %s", e)

    return {"inserted": inserted}


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    with _ws_lock:
        _ws_clients.append(ws)
    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "progress":
                with state.read() as st:
                    st["current_time"] = data.get("currentTime", 0)
                await _ws_broadcast(data)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.warning("WebSocket: %s", e)
    finally:
        with _ws_lock:
            if ws in _ws_clients:
                _ws_clients.remove(ws)
