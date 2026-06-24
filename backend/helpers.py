#!/usr/bin/env python3
"""
Claude Music — Shared Helper Functions
Pulled from the monolithic server.py for reuse across route modules.
"""

import json
import logging
import os
import time
import threading

import engine as eng
from api.ncm_client import ncm
from models.song import Song

log = logging.getLogger("claude-music")

# ── Paths ──
HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(HOME, "data")
TASTE_FILE = os.path.join(DATA_DIR, "taste.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
SESSION_FILE = os.path.join(DATA_DIR, "session.json")
CANDIDATE_DIR = os.path.join(DATA_DIR, "candidates")

# ── Playlist mapping per mode (multiple playlists supported) ──
MODE_PLAYLISTS = {
    "rap": ["Claude Rap", "rap not rape"],
    "mixed": ["Claude Picks"],
}


def _load_candidates_into_state(st, mode):
    data = eng.load_candidates(mode)
    if data:
        songs = data.get("songs", data) if isinstance(data, dict) else data
        if isinstance(songs, list) and songs:
            st["candidates"] = songs
            st["songs"] = [s for s in songs if not s.get("_played")]
            st["current_idx"] = 0
            # Restore position from saved session
            try:
                if os.path.exists(SESSION_FILE):
                    with open(SESSION_FILE, "r", encoding="utf-8") as f:
                        sess = json.load(f)
                    last_id = sess.get("last_songid")
                    if last_id is not None:
                        for i, s in enumerate(st["songs"]):
                            if s.get("songid") == last_id or s.get("id") == last_id:
                                st["current_idx"] = i
                                break
            except Exception:
                pass
            return True
    return False


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


def _record_feedback(song_id: int, song: dict | None, action: str):
    """Record like/skip/add in history.json."""
    path = HISTORY_FILE
    h = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                h = json.load(f)
        except Exception:
            import traceback
            log.warning("Failed to read history.json for feedback: %s", traceback.format_exc())
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


def _resolve_song_url(song_id: int) -> str | None:
    """Fetch a playable URL from NetEase API."""
    try:
        data = ncm("/song/url/v1", {"id": song_id, "level": "standard"})
        if data and "data" in data:
            for u in data["data"]:
                if u.get("id") == song_id and u.get("url"):
                    return u["url"]
    except Exception as e:
        log.warning("URL fetch for song %d: %s", song_id, e)
    return None


def _load_chat_context(state):
    """Load history, taste, song_stats for AI chat context."""
    history = {}
    taste = {}
    try:
        hp = HISTORY_FILE
        if os.path.exists(hp):
            with open(hp, encoding="utf-8") as f:
                history = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to load history.json: %s", e)
    try:
        tp = TASTE_FILE
        if os.path.exists(tp):
            with open(tp, encoding="utf-8") as f:
                taste = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to load taste.json: %s", e)
    # Build song_stats for current song
    song_stats = {}
    song = state.current_song()
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


def _handle_chat_signals(signals: list, text: str, state):
    """Process chat signals: handle song requests, insert songs into queue."""
    inserted = []
    # Check for song requests (e.g., "来三首周杰伦的歌")
    try:
        import chat as chat_mod
        req = chat_mod.extract_song_request(text)
        if req:
            query, count, artist = req
            count = min(count or 5, 10)  # default 5, max 10
            log.info("Song request: query=%s count=%d artist=%s", query, count, artist)
            results = eng.search_songs(query, count + 5) if hasattr(eng, 'search_songs') else []
            if not results:
                # Fallback: search via ncm
                data = ncm("/search", {"keywords": query, "limit": count + 5, "type": 1})
                results = []
                if data and "result" in data:
                    for s in data["result"].get("songs", [])[:count + 5]:
                        results.append(Song.from_ncm_song(s, "chat_request"))
            if results:
                with state.read() as st:
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
    taste_path = TASTE_FILE
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
            dt_list = []
            dt_val = t.get("dt", 0)
            # dt is song duration in ms — iterate sequentially to extract artist names only
            if isinstance(ar_list, list):
                for ar in ar_list:
                    name = ar.get("name", "") if isinstance(ar, dict) else str(ar)
                    if name:
                        artist_count[name] = artist_count.get(name, 0) + 1

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


def _refresh_mode(mode, force=False):
    cache_path = os.path.join(CANDIDATE_DIR, f"{mode}.json")
    needs_rebuild = force
    if not force and os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                cached = json.load(f)
            built_at = cached.get("built_at", "")
            if not built_at.startswith(time.strftime("%Y-%m-%d")):
                needs_rebuild = True
        except Exception:
            needs_rebuild = True
    elif not os.path.exists(cache_path):
        needs_rebuild = True
    if needs_rebuild:
        _ingest_playlist_seed(mode)
        candidates = eng.build_candidates(mode)
        if candidates:
            scored = eng.score_candidates(candidates, mode)
            eng.save_candidates(scored, mode)
            return scored
    return []


def _daily_refresh(force: bool = False, state=None):
    """Check if candidates are stale and auto-rebuild if needed."""
    for mode in ("rap", "mixed"):
        scored = _refresh_mode(mode, force)
        if scored and state is not None:
            with state.read() as st:
                if st["mode"] == mode:
                    st["candidates"] = scored
                    st["songs"] = [s for s in scored if not s.get("_played")]
                    st["current_idx"] = 0
            log.info("Daily refresh: %d songs for mode=%s", len(scored), mode)


def _load_state(state):
    """Load session.json into the state manager."""
    path = SESSION_FILE
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            s = json.load(f)
        with state.read() as st:
            st["mode"] = s.get("mode", "rap")
            st["epsilon"] = s.get("epsilon", 0.15)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to load session: %s", e)


def _save_state(state):
    """Persist current state to session.json."""
    try:
        with state.read() as st:
            song = state.current_song()
            payload = {
                "mode": st["mode"],
                "epsilon": st["epsilon"],
                "last_songid": song.get("songid") if song else None,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError as e:
        log.warning("Failed to save session: %s", e)
