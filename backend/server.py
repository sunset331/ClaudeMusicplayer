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


# ── Playlist mapping per mode (multiple playlists supported) ──
MODE_PLAYLISTS = {
    "rap": ["Claude Rap", "rap not rape"],
    "mixed": ["Claude Picks"],
}


def _get_playlist_ids(mode: str) -> list[int]:
    """Get all playlist IDs for a mode (lookup only, no creation)."""
    ids = []
    try:
        d = ncm("/user/playlist", {"uid": 0})
        playlists = d.get("playlist", []) if d else []
        for pl in playlists:
            if pl.get("name") in MODE_PLAYLISTS.get(mode, []):
                ids.append(pl.get("id"))
    except Exception as e:
        log.warning("Playlist lookup failed: %s", e)
    return ids


def _ingest_playlist_seed(mode: str):
    """Pull songs from all mode playlists and update taste.json weights."""
    pids = _get_playlist_ids(mode)
    if not pids:
        log.warning("No playlists found for mode=%s (looking for: %s)", mode, MODE_PLAYLISTS.get(mode, []))
        return

    all_tracks = []
    for pid in pids:
        try:
            data = ncm("/playlist/detail", {"id": pid})
            tracks = []
            if data and "playlist" in data:
                tracks = data["playlist"].get("tracks", [])
            if tracks:
                all_tracks.extend(tracks)
                log.info("  + %d tracks from playlist id=%s", len(tracks), pid)
        except Exception as e:
            log.warning("Failed to fetch playlist %s: %s", pid, e)

    if not all_tracks:
        log.warning("All playlists empty for mode=%s", mode)
        return
    log.info("Ingesting %d total tracks from %d playlists for mode=%s", len(all_tracks), len(pids), mode)

    # Load taste.json
    taste_path = os.path.join(DATA_DIR, "taste.json")
    taste = {}
    if os.path.exists(taste_path):
        with open(taste_path, encoding="utf-8") as f:
            taste = json.load(f)
    if "modes" not in taste:
        taste["modes"] = {}
    if mode not in taste["modes"]:
        taste["modes"][mode] = {"artist_weights": {}, "genre_weights": {}, "top_artists": []}

    mt = taste["modes"][mode]
    if "artist_weights" not in mt:
        mt["artist_weights"] = {}
    if "genre_weights" not in mt:
        mt["genre_weights"] = {}

    # Count artist occurrences
    artist_count: dict[str, int] = {}
    genre_count: dict[str, int] = {}
    for t in all_tracks:
        if isinstance(t, dict):
            ar_list = t.get("ar", [])
            if isinstance(ar_list, list):
                for ar in ar_list:
                    name = ar.get("name", "") if isinstance(ar, dict) else str(ar)
                    if name:
                        artist_count[name] = artist_count.get(name, 0) + 1
            dt_list = t.get("dt", [])
            if isinstance(dt_list, list):
                for tag in dt_list:
                    if isinstance(tag, str):
                        genre_count[tag] = genre_count.get(tag, 0) + 1

    # Update weights (normalize to 0.1-1.0 range)
    if artist_count:
        max_c = max(artist_count.values())
        for name, c in artist_count.items():
            mt["artist_weights"][name] = max(0.1, min(1.0, (c / max_c)))
        mt["top_artists"] = sorted(artist_count, key=artist_count.get, reverse=True)[:30]
    if genre_count:
        max_g = max(genre_count.values())
        for tag, c in genre_count.items():
            mt["genre_weights"][tag] = max(0.05, min(0.7, (c / max_g) * 0.5))

    taste["modes"][mode] = mt
    with open(taste_path, "w", encoding="utf-8") as f:
        json.dump(taste, f, ensure_ascii=False, indent=2)
    log.info("Updated taste.json: %d artists, %d genres for mode=%s",
             len(mt["artist_weights"]), len(mt["genre_weights"]), mode)


def _daily_refresh(force: bool = False):
    """Check if candidates are stale and auto-rebuild if needed."""
    for mode in ("rap", "mixed"):
        cache_path = os.path.join(DATA_DIR, "candidates", f"{mode}.json")
        needs_rebuild = force
        if not force and os.path.exists(cache_path):
            try:
                with open(cache_path, encoding="utf-8") as f:
                    cached = json.load(f)
                built_at = cached.get("built_at", "")
                today = time.strftime("%Y-%m-%d")
                if not built_at.startswith(today):
                    needs_rebuild = True
            except Exception:
                needs_rebuild = True
        elif not os.path.exists(cache_path):
            needs_rebuild = True

        if needs_rebuild:
            try:
                # First ingest playlist seeds to update taste
                _ingest_playlist_seed(mode)
                # Then build and score candidates
                candidates = eng.build_candidates(mode)
                if candidates:
                    scored = eng.score_candidates(candidates, mode)
                    with _read_state() as st:
                        if st["mode"] == mode:
                            st["candidates"] = scored
                            st["songs"] = [s for s in scored if not s.get("_played")]
                            st["current_idx"] = 0
                    eng.save_candidates(scored, mode)
                    log.info("Daily refresh: %d songs for mode=%s", len(scored), mode)
            except Exception as e:
                log.error("Daily refresh failed for mode=%s: %s", mode, e)


def _find_or_create_playlist(mode: str) -> int | None:
    """Find or create the PRIMARY playlist for a mode (first in MODE_PLAYLISTS list)."""
    try:
        targets = MODE_PLAYLISTS.get(mode, [])
        if not targets:
            return None
        primary = targets[0]  # Only auto-create the primary playlist
        d = ncm("/user/playlist", {"uid": 0})
        playlists = d.get("playlist", []) if d else []
        pid = None
        for pl in playlists:
            if pl.get("name") == primary:
                pid = pl.get("id")
                break
        if not pid:
            d2 = ncm("/playlist/create", {"name": primary, "privacy": 0})
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
    # Daily auto-refresh in background (can take 15-60s, don't block startup)
    threading.Thread(target=_daily_refresh, kwargs={"force": False}, daemon=True).start()
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
    # Sync to NetEase Cloud Music
    try:
        ncm("/like", {"id": song_id, "like": True})
        log.info("Like song=%d synced to NetEase", song_id)
    except Exception as e:
        log.warning("NetEase like sync failed for %d: %s", song_id, e)
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
            _ingest_playlist_seed(mode)  # Update taste before building
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

def _load_chat_context():
    """Load history, taste, song_stats for AI chat context."""
    history = {}
    taste = {}
    try:
        hp = os.path.join(DATA_DIR, "history.json")
        if os.path.exists(hp):
            with open(hp, encoding="utf-8") as f:
                history = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to load history.json: %s", e)
    try:
        tp = os.path.join(DATA_DIR, "taste.json")
        if os.path.exists(tp):
            with open(tp, encoding="utf-8") as f:
                taste = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to load taste.json: %s", e)
    # Build song_stats for current song
    song_stats = {}
    with _read_state() as st:
        song = _current_song(st)
        if song:
            sid = str(song.get("songid", ""))
            plays = history.get("song_plays", {}).get(sid, {})
            song_stats = {
                "playCount": plays.get("count", 0),
                "lastPlayed": plays.get("last_played", "never"),
                "liked": plays.get("liked", False),
                "skipped": plays.get("skipped", False),
            }
    return history, taste, song_stats, song


@app.post("/api/chat/message")
async def chat_message(body: dict):
    """Send a message to AI companion with real context."""
    text = body.get("text", "")
    if not text.strip():
        return {"reply": "", "signals": []}
    try:
        history, taste, song_stats, song = _load_chat_context()
        reply, signals = chat_mod.send_message(
            text, song, [], history, taste, song_stats,
        )
        should_skip = "[切歌]" in (reply or "")
        reply_clean = reply.replace("[切歌]", "").strip() if reply else ""

        # Handle song requests from chat signals
        inserted = _handle_chat_signals(signals, text)

        # Detect mood radio triggers
        mood = None
        try:
            import smart_dj
            mood = smart_dj.detect_mood(text)
        except Exception:
            pass

        return {
            "reply": reply_clean,
            "signals": signals,
            "shouldSkip": should_skip,
            "inserted": inserted,
            "mood": mood,
        }
    except Exception as e:
        log.warning("Chat error: %s", e)
        return {"reply": "沧溟正在休息，请稍后再试...", "signals": []}


def _ncm_song_to_internal(s: dict, source: str, score: float) -> dict:
    """Convert NetEase API song result to internal song dict. Shared helper."""
    return {
        "songid": s.get("id"),
        "songname": s.get("name", ""),
        "singer": s.get("ar", s.get("artists", [])),
        "albumname": s.get("al", {}).get("name", "") if isinstance(s.get("al"), dict) else "",
        "albumid": s.get("al", {}).get("id", 0) if isinstance(s.get("al"), dict) else 0,
        "duration": s.get("dt", s.get("duration", 0)),
        "_score": score,
        "_sources": [source],
        "_played": False,
    }


def _handle_chat_signals(signals: list, text: str) -> list:
    """Process chat signals: handle song requests, insert songs into queue."""
    inserted = []
    # Check for song requests (e.g., "来三首周杰伦的歌")
    try:
        req = chat_mod.extract_song_request(text)
        if req:
            query, count, artist = req
            count = min(count or 3, 5)
            log.info("Song request: query=%s count=%d artist=%s", query, count, artist)
            results = eng.search_songs(query, count + 5) if hasattr(eng, 'search_songs') else []
            if not results:
                # Fallback: search via ncm
                data = ncm("/search", {"keywords": query, "limit": count + 5, "type": 1})
                results = []
                if data and "result" in data:
                    for s in data["result"].get("songs", [])[:count + 5]:
                        results.append(_ncm_song_to_internal(s, "chat_request", 0.99))
            if results:
                with _read_state() as st:
                    songs = list(st["songs"])
                    idx = st["current_idx"]
                    # Score and insert after current song
                    for r in results[:count]:
                        r["_score"] = 0.99
                        r["_sources"] = ["chat_request"]
                        r["_played"] = False
                        songs.insert(idx + 1, r)
                        inserted.append(_song_to_dict(r))
                        idx += 1
                    st["songs"] = songs
                log.info("Inserted %d songs from chat request", len(inserted))
    except Exception as e:
        log.warning("Song request handling failed: %s", e)
    return inserted


@app.post("/api/smart-insert")
async def smart_insert(body: dict):
    """Behavior-based smart insertion: skip/dwell triggers 2-3 song insert."""
    trigger = body.get("trigger", "skip")  # "skip" | "dwell" | "like"
    with _read_state() as st:
        song = _current_song(st)
        if not song:
            return {"inserted": []}
        sid = str(song.get("songid", ""))
        songs = list(st["songs"])
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
                                song = _ncm_song_to_internal(s, "smart_skip", 0.85)
                                song["singer"] = [{"name": ar_name}]
                                song["duration"] = s.get("duration", 0) * 1000  # simi gives seconds
                                alt_songs.append(song)
                    # Insert 2 alternative songs
                    for s in alt_songs[:2]:
                        with _read_state() as st:
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
                            new_song = _ncm_song_to_internal(s, "smart_dwell", 0.88)
                            with _read_state() as st:
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
                    new_song = _ncm_song_to_internal(s, "smart_like", 0.92)
                    new_song["singer"] = [{"name": ar_name}]
                    new_song["duration"] = s.get("duration", 0) * 1000
                    with _read_state() as st:
                        st["songs"].insert(st["current_idx"] + 1, new_song)
                    inserted.append(_song_to_dict(new_song))

        if inserted:
            log.info("Smart insert (%s): %d songs after current", trigger, len(inserted))
    except Exception as e:
        log.warning("Smart insert failed: %s", e)

    return {"inserted": inserted}


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
    # Ingest playlist seed + build candidates for new mode
    threading.Thread(target=lambda: _daily_refresh(force=False), daemon=True).start()
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

# ── Sleep timer ──
@app.post("/api/sleep/{minutes}")
async def sleep_timer(minutes: int):
    """Set a sleep timer — stop playback after N minutes."""
    if minutes < 1 or minutes > 120:
        return {"ok": False, "error": "1-120 minutes only"}
    def _sleep():
        time.sleep(minutes * 60)
        log.info("Sleep timer fired after %d min", minutes)
        with _read_state() as st:
            st["playing"] = False
    threading.Thread(target=_sleep, daemon=True).start()
    log.info("Sleep timer set: %d minutes", minutes)
    return {"ok": True, "minutes": minutes}

# ── System tray toggle ──
@app.post("/api/toggle")
async def toggle_playback():
    return {"ok": True}

# ── System tray (pystray) ──
def _run_tray():
    try:
        from PIL import Image, ImageDraw
        import pystray
        import requests as _req
    except ImportError:
        log.warning("pystray or PIL not installed, tray disabled")
        return

    icon_path = os.path.join(DATA_DIR, "icon.ico")
    if os.path.exists(icon_path):
        image = Image.open(icon_path)
    else:
        image = Image.new("RGB", (64, 64), "#1a1030")
        d = ImageDraw.Draw(image)
        d.ellipse([16, 16, 48, 48], fill="#C084FC")

    def on_show(icon, item):
        import webbrowser; webbrowser.open("http://localhost:8765")

    def on_playpause(icon, item):
        try: _req.post("http://localhost:8765/api/toggle", timeout=2)
        except Exception: pass

    def on_next(icon, item):
        try: _req.post("http://localhost:8765/api/next", timeout=2)
        except Exception: pass

    def on_prev(icon, item):
        try: _req.post("http://localhost:8765/api/prev", timeout=2)
        except Exception: pass

    def on_exit(icon, item):
        icon.stop()
        import os as _os; _os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("显示 Claude Music", on_show, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("播放/暂停", on_playpause),
        pystray.MenuItem("下一首", on_next),
        pystray.MenuItem("上一首", on_prev),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", on_exit),
    )
    icon = pystray.Icon("claude_music", image, "Claude Music", menu)
    icon.run()

# ── Global hotkeys (pynput) ──
def _run_hotkeys():
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
        with _read_state() as st: pass  # toggle via API
        api_post("/api/toggle")

    def on_next(): api_post("/api/next")
    def on_prev(): api_post("/api/prev")

    try:
        with GlobalHotKeys({
            '<ctrl>+<alt>+<space>': on_play_pause,
            '<ctrl>+<alt>+<right>': on_next,
            '<ctrl>+<alt>+<left>': on_prev,
        }) as h:
            # Also register media keys if available
            try:
                h._handler.Listener._listen_kwargs['suppress'] = False
            except Exception:
                pass
            h.join()
    except Exception as e:
        log.warning("Global hotkeys failed: %s", e)

# ── Entry ──
if __name__ == "__main__":
    import uvicorn
    import threading as _thr

    _thr.Thread(target=_run_tray, daemon=True).start()
    _thr.Thread(target=_run_hotkeys, daemon=True).start()

    log.info("Starting Claude Music server on http://localhost:8765")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
