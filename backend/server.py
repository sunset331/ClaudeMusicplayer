#!/usr/bin/env python3
"""
Claude Music — Full-stack Server
Serves React frontend (desktop/dist/) + REST/WebSocket API.
Replaces tkinter frontend. Zero modification to engine.py/chat.py/etc.
"""
import sys
import os
import json
import logging
import time
import threading
import webbrowser
from contextlib import contextmanager, asynccontextmanager

# Add parent dir to path so we can import engine.py, chat.py, etc.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

import requests as http_requests

import engine as eng
import chat as chat_mod
from api.ncm_client import ncm

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")
log = logging.getLogger("claude-music")

# ── Paths ──
HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(HOME, "data")
ART_DIR = os.path.join(DATA_DIR, "covers")
DIST_DIR = os.path.join(HOME, "desktop", "dist")
ASSETS_DIR = os.path.join(DIST_DIR, "assets")

# ── Thread-safe global state ──
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
    _state_lock.acquire()
    try:
        yield _state
    finally:
        _state_lock.release()

# ── WebSocket clients ──
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

# ── Helpers ──
def _load_state():
    path = os.path.join(DATA_DIR, "session.json")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            s = json.load(f)
        with _read_state() as st:
            st["mode"] = s.get("mode", "rap")
            st["epsilon"] = s.get("epsilon", 0.15)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to load session: %s", e)

def _save_state():
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
    songs, idx = st["songs"], st["current_idx"]
    return songs[idx] if 0 <= idx < len(songs) else None

def _record_feedback(song_id: int, song: dict | None, action: str):
    """Record like/skip/add in history.json — mirrors app.py _track_play()."""
    path = os.path.join(DATA_DIR, "history.json")
    h = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                h = json.load(f)
        except Exception:
            pass
    sid = str(song_id)
    if "song_plays" not in h:
        h["song_plays"] = {}
    entry = h["song_plays"].get(sid, {
        "name": (song or {}).get("songname", str(song_id)),
        "artist": ", ".join(s.get("name", "") for s in (song or {}).get("singer", [])) if song else "",
        "count": 0,
    })
    if action == "like":
        entry["liked"] = True
        # Also update liked_artists
        if "liked_artists" not in h:
            h["liked_artists"] = {}
        if song:
            for s in song.get("singer", []):
                name = s.get("name", "") if isinstance(s, dict) else str(s)
                if name:
                    h["liked_artists"][name] = h["liked_artists"].get(name, 0) + 1
    elif action == "skip":
        entry["skipped"] = True
        if "skipped_artists" not in h:
            h["skipped_artists"] = {}
        if song:
            for s in song.get("singer", []):
                name = s.get("name", "") if isinstance(s, dict) else str(s)
                if name:
                    h["skipped_artists"][name] = h["skipped_artists"].get(name, 0) + 1
    h["song_plays"][sid] = entry
    if "recommended_ids" not in h:
        h["recommended_ids"] = []
    if sid not in h["recommended_ids"]:
        h["recommended_ids"].append(sid)
        h["recommended_ids"] = h["recommended_ids"][-5000:]
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(h, f, ensure_ascii=False, indent=2)
    except OSError as e:
        log.warning("Failed to write history: %s", e)


def _find_or_create_playlist(mode: str) -> int | None:
    """Find or create NetEase playlist. Mirrors app.py _find_playlist()."""
    try:
        d = ncm("/user/playlist", {"uid": 0})
        playlists = d.get("playlist", []) if d else []
        pid = None
        target = "Claude Rap" if mode == "rap" else "Claude Picks"
        for pl in playlists:
            if pl.get("name") == target:
                pid = pl.get("id")
                break
        if not pid:
            d2 = ncm("/playlist/create", {"name": target, "privacy": 0})
            if d2:
                pid = d2.get("id") or d2.get("playlist", {}).get("id")
        return pid
    except Exception as e:
        log.warning("Playlist find/create failed: %s", e)
        return None


def _song_to_dict(song):
    singer = song.get("singer", song.get("artist", ""))
    if isinstance(singer, list):
        singer = ", ".join(s.get("name", str(s)) if isinstance(s, dict) else str(s) for s in singer)
    return {
        "id": song.get("songid", song.get("id", 0)),
        "name": song.get("songname", song.get("name", "")),
        "artist": str(singer),
        "album": song.get("albumname", song.get("album", "")),
        "albumId": song.get("albumid", song.get("albumId", 0)),
        "duration": int((song.get("duration", 0) or 0) / 1000),  # ms → seconds
        "score": round(float(song.get("_score", 0)), 4),
        "sources": song.get("_sources", []),
        "played": bool(song.get("_played", False)),
        "scoreBreakdown": song.get("_score_breakdown", {}),
        "url": song.get("url"),
    }

# ── Lifespan ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_state()
    try:
        with _read_state() as st:
            mode = st["mode"]
        data = eng.load_candidates(mode)
        if data:
            songs = data.get("songs", data) if isinstance(data, dict) else data
            if isinstance(songs, list) and songs:
                with _read_state() as st:
                    st["candidates"] = songs
                    st["songs"] = [s for s in songs if not s.get("_played")]
                log.info("Pre-loaded %d candidates", len(songs))
    except Exception as e:
        log.warning("Startup candidate load: %s", e)
    yield
    log.info("Shutting down")

app = FastAPI(title="Claude Music", version="3.0.0", lifespan=lifespan)

# ── API Routes (must be defined BEFORE static file mounts) ──

@app.get("/api/status")
async def get_status():
    with _read_state() as st:
        return {"ok": True, "mode": st["mode"], "epsilon": st["epsilon"],
                "songCount": len(st["songs"])}

@app.get("/api/queue")
async def get_queue():
    with _read_state() as st:
        if not st["songs"]:
            try:
                data = eng.load_candidates(st["mode"])
                if data:
                    songs = data.get("songs", data) if isinstance(data, dict) else data
                    if isinstance(songs, list):
                        st["candidates"] = songs
                        st["songs"] = [s for s in songs if not s.get("_played")]
                        log.info("Loaded %d candidates for mode=%s", len(st["songs"]), st["mode"])
            except Exception as e:
                log.warning("Failed to load candidates: %s", e)
        return {"songs": [_song_to_dict(s) for s in st["songs"]],
                "mode": st["mode"], "epsilon": st["epsilon"]}

def _resolve_song_url(song_id: int) -> str | None:
    """Fetch a playable URL from NetEase API. Shared by play + stream endpoints."""
    try:
        data = ncm("/song/url/v1", {"id": song_id, "level": "standard"})
        if data and "data" in data:
            for u in data["data"]:
                if u.get("id") == song_id and u.get("url"):
                    return u["url"]
    except Exception as e:
        log.warning("URL fetch for song %d: %s", song_id, e)
    return None


@app.get("/api/play/{song_id}")
async def play_song(song_id: int):
    url = _resolve_song_url(song_id)
    with _read_state() as st:
        for i, s in enumerate(st["songs"]):
            if s.get("songid") == song_id or s.get("id") == song_id:
                st["current_idx"] = i; s["url"] = url
                st["playing"] = True; st["current_time"] = 0
                song_data = _song_to_dict(s); break
        else:
            song_data = None
    _save_state()
    return {"url": url, "song": song_data}

@app.post("/api/next")
async def next_song():
    with _read_state() as st:
        if not st["songs"]:
            return {"nextIndex": -1, "song": None}
        next_idx = (st["current_idx"] + 1) % len(st["songs"])
        st["current_idx"] = next_idx; st["current_time"] = 0
        song = _song_to_dict(st["songs"][next_idx])
    _save_state()
    return {"nextIndex": next_idx, "song": song}

@app.post("/api/like/{song_id}")
async def like_song(song_id: int):
    with _read_state() as st:
        st["play_count"] += 1
        st["epsilon"] = max(0.05, st["epsilon"] - 0.01)
        eps = st["epsilon"]
        sid = str(song_id)
        song = next((s for s in st["candidates"] if str(s.get("songid")) == sid), None)
        if not song:
            song = next((s for s in st["songs"] if str(s.get("songid")) == sid), None)
    _save_state()
    _record_feedback(song_id, song, "like")
    log.info("Like song=%d epsilon=%.2f", song_id, eps)
    return {"ok": True, "epsilon": eps}

@app.post("/api/skip/{song_id}")
async def skip_song(song_id: int):
    with _read_state() as st:
        st["play_count"] += 1
        st["epsilon"] = min(0.50, st["epsilon"] + 0.01)
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
                if text: lines.append({"time": ms, "text": text})
        lines.sort(key=lambda x: x["time"])
        with _read_state() as st:
            st["lyrics_cache"][song_id] = lines
        return {"lyrics": lines}
    except Exception as e:
        log.warning("Lyrics for song %d: %s", song_id, e)
        return {"lyrics": []}

@app.post("/api/rebuild")
async def rebuild():
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
                log.info("Rebuild: %d songs for mode=%s", len(scored), mode)
        except Exception as e:
            log.error("Rebuild failed: %s", e)
    threading.Thread(target=_do, daemon=True).start()
    return {"ok": True}

@app.get("/api/stats")
async def get_stats():
    with _read_state() as st:
        return {"playCount": st["play_count"], "mode": st["mode"], "epsilon": st["epsilon"]}

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    with _ws_lock:
        _ws_clients.append(ws)
    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "progress":
                with _read_state() as st:
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

@app.get("/api/stream/{song_id}")
async def stream_audio(song_id: int):
    """Proxy audio stream — NetEase URLs require Referer header."""
    url = _resolve_song_url(song_id)
    if not url:
        return HTMLResponse(status_code=404)

    def generate():
        try:
            resp = http_requests.get(url, headers={
                "Referer": "https://music.163.com/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }, stream=True, timeout=30)
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    yield chunk
        except Exception as e:
            log.warning("Stream error for %d: %s", song_id, e)

    return StreamingResponse(generate(), media_type="audio/mpeg")

# ── Chat ──

@app.post("/api/chat/message")
async def chat_message(body: dict):
    """Send a message to AI companion. Returns {reply, signals}."""
    text = body.get("text", "")
    if not text.strip():
        return {"reply": "", "signals": []}
    try:
        with _read_state() as st:
            song = _current_song(st)
        reply, signals = chat_mod.send_message(
            text,
            song,
            [],  # history managed by client for simplicity
            {},
            {},
            {},
        )
        # Check for skip command
        should_skip = "[切歌]" in (reply or "")
        reply_clean = reply.replace("[切歌]", "").strip() if reply else ""
        return {"reply": reply_clean, "signals": signals, "shouldSkip": should_skip}
    except Exception as e:
        log.warning("Chat error: %s", e)
        return {"reply": "沧溟正在休息，请稍后再试...", "signals": []}


@app.post("/api/mode")
async def switch_mode(body: dict):
    """Switch between rap/mixed mode."""
    new_mode = body.get("mode", "rap")
    if new_mode not in ("rap", "mixed"):
        return {"ok": False, "error": "Invalid mode"}
    with _read_state() as st:
        st["mode"] = new_mode
        st["songs"] = []
        st["current_idx"] = 0
    _save_state()
    # Load candidates for new mode
    try:
        data = eng.load_candidates(new_mode)
        if data:
            songs = data.get("songs", data) if isinstance(data, dict) else data
            if isinstance(songs, list):
                with _read_state() as st:
                    st["candidates"] = songs
                    st["songs"] = [s for s in songs if not s.get("_played")]
    except Exception as e:
        log.warning("Mode switch load failed: %s", e)
    return {"ok": True, "mode": new_mode}


@app.post("/api/playlist/add/{song_id}")
async def add_to_playlist(song_id: int):
    """Add song to NetEase playlist. Auto-creates playlist if needed."""
    try:
        with _read_state() as st:
            mode = st["mode"]
        pid = _find_or_create_playlist(mode)
        if not pid:
            return {"ok": False, "error": "Cannot find or create playlist. Login first."}
        ncm("/playlist/tracks", {"op": "add", "pid": pid, "tracks": str(song_id)})
        return {"ok": True}
    except Exception as e:
        log.warning("Add to playlist failed: %s", e)
        return {"ok": False, "error": str(e)}

# ── Serve React build as SPA ──
# Mount assets directory
if os.path.isdir(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

# Mount album art
if os.path.isdir(ART_DIR):
    app.mount("/api/covers", StaticFiles(directory=ART_DIR), name="covers")

# Serve index.html as SPA fallback
_INDEX_PATH = os.path.join(DIST_DIR, "index.html")

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Serve React SPA — all non-API routes return index.html."""
    # Skip API/WS routes that weren't matched above
    if full_path.startswith("api/") or full_path == "ws":
        return HTMLResponse(status_code=404)
    if os.path.isfile(_INDEX_PATH):
        return FileResponse(_INDEX_PATH)
    return HTMLResponse("<h1>Frontend not built. Run: cd desktop && npx vite build</h1>", status_code=503)

@app.get("/")
async def serve_index():
    if os.path.isfile(_INDEX_PATH):
        return FileResponse(_INDEX_PATH)
    return HTMLResponse("<h1>Frontend not built. Run: cd desktop && npx vite build</h1>", status_code=503)

# ── Entry ──
if __name__ == "__main__":
    import uvicorn
    import webbrowser as _wb

    # Auto-open browser in app mode (no URL bar)
    def _open_browser():
        time.sleep(2)
        url = "http://localhost:8765"
        # Try Chrome app mode first, then Edge, then default browser
        for browser in [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]:
            if os.path.exists(browser):
                import subprocess
                subprocess.Popen([browser, f"--app={url}", "--window-size=1200,800"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
        _wb.open(url)

    threading.Thread(target=_open_browser, daemon=True).start()

    log.info("Starting Claude Music server on http://localhost:8765")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
