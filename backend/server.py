#!/usr/bin/env python3
"""
Claude Music — FastAPI Backend
Wraps existing engine.py / chat.py / smart_dj.py as REST + WebSocket API.
Zero modification to existing modules.
"""
import sys
import os
import json
import logging
import time
import threading
from contextlib import contextmanager, asynccontextmanager

# Add parent dir to path so we can import engine.py, chat.py, etc.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import engine as eng
from api.ncm_client import ncm

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")
log = logging.getLogger("claude-music")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup + shutdown lifecycle."""
    _load_state()
    with _read_state() as st:
        mode = st["mode"]
    try:
        candidates = eng.load_candidates(mode)
        if candidates:
            with _read_state() as st:
                st["candidates"] = candidates
                st["songs"] = [s for s in candidates if not s.get("_played")]
            log.info("Pre-loaded %d candidates at startup", len(candidates))
    except Exception as e:
        log.warning("Startup candidate load failed: %s", e)
    yield
    log.info("Shutting down")

app = FastAPI(title="Claude Music API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config
HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(HOME, "data")
ART_DIR = os.path.join(DATA_DIR, "covers")

# Mount album art as static files
if os.path.isdir(ART_DIR):
    app.mount("/api/covers", StaticFiles(directory=ART_DIR), name="covers")

# ── Thread-safe state ──
_state = {
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
}
_state_lock = threading.RLock()


@contextmanager
def _read_state():
    """Acquire read lock on state."""
    _state_lock.acquire()
    try:
        yield _state
    finally:
        _state_lock.release()


def _load_state():
    """Load persisted session from session.json."""
    path = os.path.join(DATA_DIR, "session.json")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            s = json.load(f)
        with _read_state() as st:
            st["mode"] = s.get("mode", "rap")
            st["epsilon"] = s.get("epsilon", 0.15)
        log.info("Session loaded: mode=%s epsilon=%.2f", st["mode"], st["epsilon"])
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to load session: %s", e)


def _save_state():
    """Persist current session."""
    try:
        with _read_state() as st:
            song = _current_song(st)
            payload = {
                "mode": st["mode"],
                "epsilon": st["epsilon"],
                "last_songid": song.get("songid") if song else None,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        with open(os.path.join(DATA_DIR, "session.json"), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError as e:
        log.warning("Failed to save session: %s", e)


def _current_song(st):
    songs = st["songs"]
    idx = st["current_idx"]
    if 0 <= idx < len(songs):
        return songs[idx]
    return None


def _song_to_dict(song):
    """Convert a song dict to API-safe format."""
    singer = song.get("singer", song.get("artist", ""))
    if isinstance(singer, list):
        singer = ", ".join(
            s.get("name", str(s)) if isinstance(s, dict) else str(s) for s in singer
        )
    return {
        "id": song.get("songid", song.get("id", 0)),
        "name": song.get("songname", song.get("name", "")),
        "artist": str(singer),
        "album": song.get("albumname", song.get("album", "")),
        "albumId": song.get("albumid", song.get("albumId", 0)),
        "duration": int(song.get("duration", 0) or 0),
        "score": round(float(song.get("_score", 0)), 4),
        "sources": song.get("_sources", []),
        "played": bool(song.get("_played", False)),
        "scoreBreakdown": song.get("_score_breakdown", {}),
        "url": song.get("url"),
    }


# ── WebSocket manager ──
_ws_clients: list[WebSocket] = []
_ws_lock = threading.Lock()


async def _ws_broadcast(msg: dict):
    with _ws_lock:
        clients = list(_ws_clients)
    stale = []
    for ws in clients:
        try:
            await ws.send_json(msg)
        except Exception:
            stale.append(ws)
    if stale:
        with _ws_lock:
            for ws in stale:
                if ws in _ws_clients:
                    _ws_clients.remove(ws)


# ── REST Routes ──

@app.get("/api/status")
async def get_status():
    with _read_state() as st:
        return {
            "ok": True,
            "mode": st["mode"],
            "epsilon": st["epsilon"],
            "songCount": len(st["songs"]),
        }


@app.get("/api/queue")
async def get_queue():
    with _read_state() as st:
        if not st["songs"]:
            # Try loading candidates from engine
            try:
                candidates = eng.load_candidates(st["mode"])
                if candidates:
                    st["candidates"] = candidates
                    st["songs"] = [s for s in candidates if not s.get("_played")]
                    log.info("Loaded %d candidates for mode=%s", len(st["songs"]), st["mode"])
            except Exception as e:
                log.warning("Failed to load candidates: %s", e)

        return {
            "songs": [_song_to_dict(s) for s in st["songs"]],
            "mode": st["mode"],
            "epsilon": st["epsilon"],
        }


@app.post("/api/play/{song_id}")
async def play_song(song_id: int):
    """Get playable URL for a song."""
    url = None
    try:
        data = ncm("/song/url/v1", {"id": song_id, "level": "standard"})
        if data and "data" in data:
            for u in data["data"]:
                if u.get("id") == song_id and u.get("url"):
                    url = u["url"]
                    break
    except Exception as e:
        log.warning("Failed to fetch URL for song %d: %s", song_id, e)

    with _read_state() as st:
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

    _save_state()
    return {"url": url, "song": song_data}


@app.post("/api/next")
async def next_song():
    with _read_state() as st:
        songs = st["songs"]
        if not songs:
            return {"nextIndex": -1, "song": None}
        next_idx = (st["current_idx"] + 1) % len(songs)
        st["current_idx"] = next_idx
        st["current_time"] = 0
        song = _song_to_dict(songs[next_idx])
    _save_state()
    return {"nextIndex": next_idx, "song": song}


@app.post("/api/like/{song_id}")
async def like_song(song_id: int):
    with _read_state() as st:
        st["play_count"] += 1
        st["epsilon"] = max(0.05, st["epsilon"] - 0.01)
        eps = st["epsilon"]
    _save_state()
    log.info("Like song=%d epsilon=%.2f", song_id, eps)
    return {"ok": True, "epsilon": eps}


@app.post("/api/skip/{song_id}")
async def skip_song(song_id: int):
    with _read_state() as st:
        st["play_count"] += 1
        st["epsilon"] = min(0.50, st["epsilon"] + 0.01)
    log.info("Skip song=%d", song_id)
    return await next_song()


@app.get("/api/lyrics/{song_id}")
async def get_lyrics(song_id: int):
    with _read_state() as st:
        if song_id in st["lyrics_cache"]:
            return {"lyrics": st["lyrics_cache"][song_id]}

    try:
        data = ncm("/lyric", {"id": song_id})
        lrc_text = ""
        if data and "lrc" in data and data["lrc"].get("lyric"):
            lrc_text = data["lrc"]["lyric"]

        import re
        lines = []
        for line in lrc_text.split("\n"):
            m = re.match(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)", line)
            if m:
                ms = int(m.group(1)) * 60000 + int(float(m.group(2)) * 1000)
                text = m.group(3).strip()
                if text:
                    lines.append({"time": ms, "text": text})
        lines.sort(key=lambda x: x["time"])

        with _read_state() as st:
            st["lyrics_cache"][song_id] = lines
        return {"lyrics": lines}
    except Exception as e:
        log.warning("Failed to fetch lyrics for song %d: %s", song_id, e)
        return {"lyrics": []}


@app.post("/api/rebuild")
async def rebuild():
    """Trigger async candidate pool rebuild."""
    def _do():
        try:
            with _read_state() as st:
                mode = st["mode"]
            candidates = eng.build_candidates(mode)
            if candidates:
                scored = eng.score_candidates(candidates, mode)
                with _read_state() as st:
                    st["candidates"] = scored
                    st["songs"] = [s for s in scored if not s.get("_played")]
                    st["current_idx"] = 0
                log.info("Rebuild complete: %d songs for mode=%s", len(scored), mode)
        except Exception as e:
            log.error("Rebuild failed: %s", e)

    threading.Thread(target=_do, daemon=True).start()
    return {"ok": True}


@app.get("/api/stats")
async def get_stats():
    with _read_state() as st:
        return {
            "playCount": st["play_count"],
            "mode": st["mode"],
            "epsilon": st["epsilon"],
        }


# ── WebSocket for real-time progress ──

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    with _ws_lock:
        _ws_clients.append(ws)
    log.info("WebSocket client connected (%d total)", len(_ws_clients))
    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "progress":
                with _read_state() as st:
                    st["current_time"] = data.get("currentTime", 0)
                await _ws_broadcast(data)
    except WebSocketDisconnect:
        log.info("WebSocket client disconnected")
    except Exception as e:
        log.warning("WebSocket error: %s", e)
    finally:
        with _ws_lock:
            if ws in _ws_clients:
                _ws_clients.remove(ws)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
