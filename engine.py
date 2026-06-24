#!/usr/bin/env python3
"""
Music Recommendation Engine (NetEase Cloud Music Edition)
- Reads taste profile from local data/taste.json
- Fetches real songs via local NetEase Cloud Music API (localhost:3000)
- Supports two modes: rap (personalized) + focus (lo-fi/ambient)
- Scores, deduplicates, and selects 50 daily picks
- Outputs to data/today.json (rap) or data/today_focus.json (focus)
Usage: python engine.py [--mode rap|focus|both]
"""
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import config
from api.ncm_client import ncm_get  # noqa: F401 — re-export for module consumers
from models.song import Song

# Fix Windows terminal mojibake — bash/MSYS2 supports UTF-8 natively
if sys.stdout and sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

NCM = config.NCM_API

HOME = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HOME, "data")
TASTE_FILE = os.path.join(DATA_DIR, "taste.json")
TODAY_FILE = os.path.join(DATA_DIR, "today.json")
TODAY_FOCUS_FILE = os.path.join(DATA_DIR, "today_focus.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
ARTIST_ID_FILE = os.path.join(DATA_DIR, "artist_ids.json")

DAILY_PICKS = 50
MAX_PER_ARTIST = 3
MIN_ARTISTS = 12

# ============================================================
# TASTE v2 — mode-partitioned format
# ============================================================

TASTE_V2_DEFAULT = {
    "version": 2,
    "modes": {
        "rap": {
            "seed_playlists": [],
            "top_artists": [],
            "artist_weights": {},
            "genre_weights": {
                "hip-hop": 0.6,
                "rock": 0.15,
                "chinese": 0.1,
                "pop": 0.1,
            },
        },
        "mixed": {
            "seed_playlists": [],
            "top_artists": [],
            "artist_weights": {},
            "genre_weights": {},
        },
        "focus": {
            "seed_playlists": [],
            "top_artists": [],
            "artist_weights": {},
            "genre_weights": {
                "ambient": 0.5,
                "lo-fi": 0.5,
                "jazz": 0.3,
                "classical": 0.3,
                "electronic": 0.2,
            },
        },
    },
    "claude_picks": {
        "playlist_id": None,
        "last_sync": None,
        "songs": [],
        "artist_counts": {},
    },
}


def load_taste():
    """Load taste profile, migrating from v1 if needed."""
    if not os.path.exists(TASTE_FILE):
        return dict(TASTE_V2_DEFAULT)  # shallow copy

    with open(TASTE_FILE, "r", encoding="utf-8") as f:
        t = json.load(f)

    if t.get("version") == 2:
        return t

    # Migrate v1 -> v2
    print("  [taste] Migrating from v1 to v2...")
    top_artists = t.get("top_artists", [])
    artist_weights = t.get("artist_weights", {})
    genre_weights = t.get("genre_weights", {})

    v2 = {
        "version": 2,
        "modes": {
            "rap": {
                "seed_playlists": [],
                "top_artists": list(top_artists),
                "artist_weights": dict(artist_weights),
                "genre_weights": dict(genre_weights) if genre_weights else {
                    "hip-hop": 0.6, "rock": 0.15, "chinese": 0.1, "pop": 0.1,
                },
            },
            "mixed": {
                "seed_playlists": [],
                "top_artists": list(top_artists),
                "artist_weights": dict(artist_weights),
                "genre_weights": {},
            },
        },
        "claude_picks": {
            "playlist_id": None,
            "last_sync": None,
            "songs": [],
            "artist_counts": {},
        },
    }
    save_taste(v2)
    return v2


def save_taste(taste):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TASTE_FILE, "w", encoding="utf-8") as f:
        json.dump(taste, f, ensure_ascii=False, indent=2)


def get_mode_taste(taste, mode):
    """Get mode-specific taste sub-profile."""
    return taste.get("modes", {}).get(mode, TASTE_V2_DEFAULT["modes"]["rap"])


def ingest_qq_seed(taste, mode):
    """
    Read qq_seed_{mode}.json and merge into taste.modes[mode].
    Updates top_artists ranking and artist_weights.
    """
    seed_file = os.path.join(DATA_DIR, f"qq_seed_{mode}.json")
    if not os.path.exists(seed_file):
        print(f"  [taste] No seed file for {mode}: {seed_file}")
        return taste

    with open(seed_file, "r", encoding="utf-8") as f:
        seed = json.load(f)

    mode_taste = taste.setdefault("modes", {}).setdefault(
        mode, TASTE_V2_DEFAULT["modes"]["rap"])

    seed_key = f"qq_seed_{mode}"
    if seed_key not in mode_taste.get("seed_playlists", []):
        mode_taste.setdefault("seed_playlists", []).append(seed_key)

    artist_count = {}
    for s in seed.get("songs", []):
        ncm = s.get("ncm", {})
        for singer in ncm.get("singer", []):
            name = singer.get("name", "")
            if name:
                artist_count[name] = artist_count.get(name, 0) + 1

    sorted_artists = sorted(artist_count.items(), key=lambda x: x[1], reverse=True)
    mode_taste["top_artists"] = [a for a, _ in sorted_artists[:50]]

    if sorted_artists:
        max_count = sorted_artists[0][1]
        for name, count in sorted_artists:
            mode_taste.setdefault("artist_weights", {})[name] = round(
                count / max_count * 0.8 + 0.1, 3)

    save_taste(taste)
    print(f"  [taste] Ingested {len(seed.get('songs',[]))} songs for {mode} mode")
    return taste


# ============================================================
# RAP MODE — genre queries
# ============================================================
RAP_GENRE_QUERIES = [
    "hip-hop", "hardcore rap", "oldschool hip-hop", "west coast rap",
    "storytelling rap", "lyrical rap", "conscious hip-hop",
    "boom bap", "underground rap", "trap banger",
    "Aftermath hip-hop", "Shady Records", "G-Unit rap",
    "rap rock", "hip-hop guitar", "rap acoustic",
    "Chinese classic song", "Cantonese classic", "Chinese folk song",
    "80s Chinese pop", "90s Chinese pop",
    "rap workout", "hype rap", "motivation rap",
    "pop rock", "alternative rock", "indie pop",
    "folk pop", "acoustic pop",
]

MIXED_GENRE_QUERIES = [
    "pop rock", "alternative rock", "indie pop",
    "R&B soul", "neo soul", "contemporary R&B",
    "Chinese pop", "Chinese folk", "Cantonese classic",
    "Mandarin ballad", "90s Chinese pop", "Chinese indie",
    "acoustic pop", "singer-songwriter", "folk pop",
    "electronic pop", "synth pop", "dream pop",
    "classic rock", "soft rock", "pop punk",
    "funk", "disco classic", "Motown",
    "jazz vocal", "smooth jazz", "bossa nova",
    "world music", "Latin pop", "reggae pop",
    "orchestral pop", "film soundtrack", "musical theatre",
]

AFTERMATH_ARTISTS = [
    "Royce da 5'9", "Obie Trice", "D12", "Yelawolf",
    "Griselda", "Westside Gunn", "Benny the Butcher", "Conway the Machine",
    "Slaughterhouse", "JID", "Denzel Curry",
    "Run the Jewels", "Freddie Gibbs", "Pusha T", "Schoolboy Q",
    "Ab-Soul", "Jay Rock", "Danny Brown", "Earl Sweatshirt",
    "Tyler the Creator", "Vince Staples", "IDK", "Saba",
    "Anderson .Paak", "Token", "NF", "Hopsin",
    "Tech N9ne",
]

RAP_SCORE_KW = {
    "rap": ["rap", "freestyle", "cypher", "diss", "flow", "bars",
            "hip", "hop", "trap", "beat", "drill", "gang", "thug", "hustle",
            "explicit", "feat", "banger", "grim", "street",
            "story", "narrative", "real", "truth", "struggle", "grind",
            "lyric", "wordplay", "punchline", "metaphor",
            "shady", "aftermath", "g-unit", "westside"],
    "pop": ["love", "night", "dream", "heart", "summer",
            "pop", "radio", "chart", "hit",
            "acoustic", "piano", "voice", "ballad", "folk"],
    "rock": ["rock", "guitar", "punk", "metal", "band", "indie", "alternative",
             "hard", "heavy", "riff", "drum"],
    "chinese": ["classic", "folk", "Cantonese", "80s", "90s", "ballad",
                "nostalgia", "memory", "old song"],
}

# ============================================================
# FOCUS MODE — genre queries
# ============================================================
FOCUS_GENRE_QUERIES = [
    "lo-fi hip hop", "lofi beats", "chill study music",
    "ambient music", "ambient electronic", "atmospheric",
    "jazz instrumental", "smooth jazz", "piano jazz",
    "classical piano", "modern classical", "orchestral",
    "acoustic guitar", "fingerstyle guitar", "indie folk",
    "dream pop", "shoegaze", "post rock instrumental",
    "chill electronic", "downtempo", "trip hop",
    "meditation music", "nature sounds", "soundscape",
    "focus music", "coding music", "study beats",
    "minimal techno", "deep house chill",
    "R&B chill", "neo soul", "quiet storm",
    "film score", "soundtrack instrumental", "OST piano",
    "Japanese lo-fi", "Chinese ambient", "guqin",
]

FOCUS_SCORE_KW = {
    "positive": [
        "lo-fi", "lofi", "chill", "ambient", "instrumental", "piano",
        "acoustic", "jazz", "classical", "meditation", "focus", "study",
        "beat", "soundscape", "atmospheric", "downtempo", "smooth",
        "gentle", "soft", "calm", "peaceful", "relax", "sleep",
        "orchestral", "string", "guitar", "folk", "nature", "rain",
        "minimal", "deep", "quiet", "dream", "floating", "ether",
        "OST", "score", "soundtrack", "neo soul", "R&B",
    ],
    "negative": [
        "explicit", "rap", "hip-hop", "trap", "drill", "gang",
        "banger", "hardcore", "metal", "punk", "scream", "heavy",
        "dubstep", "EDM", "party", "club", "dance",
    ],
}


# ============================================================
# NetEase Cloud Music API helpers
# ============================================================

def get_playlist_track_ids(playlist_id):
    """Fetch all song IDs from a NetEase playlist. Returns set of string IDs."""
    ids = set()
    if not playlist_id:
        return ids
    data = ncm_get("/playlist/detail", {"id": playlist_id})
    if not data or data.get("code") != 200:
        return ids
    for t in data.get("playlist", {}).get("tracks", []):
        sid = t.get("id", 0)
        if sid:
            ids.add(str(sid))
    return ids


def search_songs(query, limit=25):
    """Search songs via NetEase API."""
    data = ncm_get("/search", {"keywords": query, "limit": limit})
    if not data or data.get("code") != 200:
        return []
    return [Song.from_ncm_song(s) for s in data.get("result", {}).get("songs", [])]


def get_artist_top_songs(artist_id, num=25):
    """Fetch an artist's hot songs via /artist/songs (no remixes in official hot list).
    Songs are returned in descending order of popularity (hotness)."""
    data = ncm_get("/artist/songs", {"id": artist_id})
    if not data or data.get("code") != 200:
        return []
    return [Song.from_ncm_song(s) for s in data.get("data", {}).get("songs", [])[:num]]


def search_artist_hot_songs(artist_name, limit=25):
    """Search for an artist by name and return their top songs sorted by popularity.
    Combines _find_artist_id + get_artist_top_songs into one call.
    Returns list of Song objects, or empty list if artist not found."""
    artist_id = _find_artist_id(artist_name)
    if not artist_id:
        return []
    flush_artist_cache()  # persist newly discovered artist IDs
    return get_artist_top_songs(artist_id, limit)


def get_toplist(topid, num=30):
    """Fetch top chart songs from NetEase."""
    data = ncm_get("/top/list", {"id": topid})
    if not data or data.get("code") != 200:
        return []
    return [Song.from_ncm_song(s) for s in data.get("playlist", {}).get("tracks", [])[:num]]


def get_song_url(song_id):
    """Get playable URL for a song."""
    data = ncm_get("/song/url/v1", {"id": song_id, "level": "standard"})
    if not data or data.get("code") != 200:
        return None
    songs = data.get("data", [])
    if songs and songs[0].get("url"):
        return {
            "url": songs[0]["url"],
            "type": songs[0].get("type", "mp3"),
            "time": songs[0].get("time", 0),
        }
    return None


def _norm(name):
    """Normalize song name for fuzzy dedup."""
    return "".join(c.lower() for c in name if c.isalnum())


_REMIX_KEYWORDS = [
    "remix", "bootleg", "flip", "rework", "remake", "dub",
    "instrumental cover", "radio edit", "club edit", "extended mix",
    "vip mix", "mashup",
]


def _is_remix(song):
    """Check if a song is a remix/variant based on name and album."""
    name = song.get("songname", "").lower()
    album = song.get("albumname", "").lower()
    combined = f"{name} {album}"
    for kw in _REMIX_KEYWORDS:
        if kw in combined:
            return True
    return False


# (load_taste_profile / save_taste replaced by v2 versions at top of file)


# ============================================================
# CANDIDATE POOL
# ============================================================

CANDIDATE_DIR = os.path.join(DATA_DIR, "candidates")


def _candidate_path(mode):
    os.makedirs(CANDIDATE_DIR, exist_ok=True)
    return os.path.join(CANDIDATE_DIR, f"{mode}.json")


def load_candidates(mode):
    """Load cached candidate pool for mode. Returns Song objects."""
    path = _candidate_path(mode)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["songs"] = [Song.from_dict(s) for s in data.get("songs", [])]
    return data


def list_history_snapshots(mode=None):
    """List available date-stamped candidate snapshots. Returns list of (date, path, mode)."""
    try:
        os.makedirs(CANDIDATE_DIR, exist_ok=True)
    except OSError:
        return []
    try:
        files = os.listdir(CANDIDATE_DIR)
    except OSError:
        return []
    snaps = []
    for fn in files:
        if not fn.endswith(".json") or "_" not in fn:
            continue
        # Pattern: {mode}_{date}.json  e.g. rap_2026-06-07.json
        base = fn[:-5]  # strip .json
        parts = base.rsplit("_", 1)
        if len(parts) != 2:
            continue
        m, date_str = parts
        if mode and m != mode:
            continue
        if len(date_str) == 10 and date_str[4] == "-":
            snaps.append((date_str, os.path.join(CANDIDATE_DIR, fn), m))
    snaps.sort(key=lambda x: x[0], reverse=True)
    return snaps


def load_history_snapshot(path):
    """Load a specific snapshot file."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_candidates(candidates, mode):
    """Save candidate pool to disk, with a date-stamped snapshot for history."""
    serialized = [s.to_dict() if isinstance(s, Song) else s for s in candidates]
    data = {
        "mode": mode,
        "built_at": datetime.now().isoformat(),
        "count": len(candidates),
        "songs": serialized,
    }
    # Main cache file
    with open(_candidate_path(mode), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # Date-stamped snapshot for history browsing — always overwrite to keep fresh
    today = datetime.now().strftime("%Y-%m-%d")
    snap_path = os.path.join(CANDIDATE_DIR, f"{mode}_{today}.json")
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_seed_ids():
    """
    Load all song IDs and normalized names from seed playlists.
    Returns (id_set, name_set) to use as blocklist during candidate building.
    """
    seed_ids = set()
    seed_names = set()
    for label in ("rap", "mixed"):
        seed_file = os.path.join(DATA_DIR, f"qq_seed_{label}.json")
        if not os.path.exists(seed_file):
            continue
        try:
            with open(seed_file, "r", encoding="utf-8") as f:
                seed = json.load(f)
            for s in seed.get("songs", []):
                ncm = s.get("ncm", {})
                sid = str(ncm.get("songid", ""))
                if sid:
                    seed_ids.add(sid)
                name = ncm.get("songname", "")
                if name:
                    seed_names.add(_norm(name))
        except Exception:
            import traceback
            print(f"  [WARN] Failed to parse seed file {seed_file}: {traceback.format_exc()}")
            pass
    return seed_ids, seed_names


def build_candidates(mode="rap", extra_block_ids=None):
    """
    Build candidate pool for a mode. Returns list of song dicts with _sources.
    Uses parallel API calls to reduce build time from 60s → ~10-15s.
    extra_block_ids: optional set of song IDs to exclude (e.g. already in playlist).
    """
    taste = load_taste()
    history = load_history()
    mode_taste = get_mode_taste(taste, mode)

    # Blocklist: seed songs + previously recommended + playlist contents
    seed_ids, seed_names = _load_seed_ids()
    known_ids = set()
    known_ids |= set(str(x) for x in history.get("recommended_ids", []))
    known_ids |= seed_ids
    if extra_block_ids:
        known_ids |= set(str(x) for x in extra_block_ids)

    candidates = {}
    seen_names = set(seed_names)

    def add(iterable, source):
        for s in iterable:
            if _is_remix(s):
                continue
            sid = str(s.get("songid", ""))
            name = s.get("songname", "")
            name_norm = _norm(name)
            if sid and sid in known_ids:
                continue
            if sid and sid in candidates:
                candidates[sid]["_sources"].append(source)
                continue
            if name_norm in seen_names:
                continue
            if sid:
                s["_sources"] = [source]
                s["_score"] = 0
                s["_played"] = False
                s["_from_simi"] = False
                candidates[sid] = s
                seen_names.add(name_norm)

    top_artists = mode_taste.get("top_artists", [])
    use_top = top_artists[:20] if top_artists else []

    # ── Collect all search tasks ──
    # (query, limit, source_label)
    search_tasks = []

    if use_top:
        # Source 1: Direct keyword search per artist (avoids artist-ID rate limit)
        for artist in use_top:
            search_tasks.append((artist, 25, f"artist:{artist}"))

    # Source 2: Genre queries
    if mode == "rap":
        genre_queries = RAP_GENRE_QUERIES
    elif mode == "focus":
        genre_queries = FOCUS_GENRE_QUERIES
    else:
        genre_queries = MIXED_GENRE_QUERIES
    for query in genre_queries[:24]:
        search_tasks.append((query, 25, f"genre:{query}"))

    # ── Run all searches in parallel ──
    print(f"  [build {mode}] Running {len(search_tasks)} searches in parallel...")
    with ThreadPoolExecutor(max_workers=3) as ex:
        future_to_source = {
            ex.submit(search_songs, q, lim): src
            for q, lim, src in search_tasks
        }
        for future in as_completed(future_to_source):
            src = future_to_source[future]
            try:
                results = future.result()
                add(results, src)
            except Exception as e:
                print(f"  [build {mode}] Search failed for {src}: {e}")

    # Source 4: Charts (sequential — different API, few calls)
    print(f"  [build {mode}] Fetching charts...")
    if mode == "rap":
        chart_ids = [(19723756, "soaring"), (3779629, "new"), (3778678, "hot")]
    elif mode == "focus":
        # Focus mode: lighter, chill charts
        chart_ids = [(19723756, "soaring"), (71384707, "light"), (2884035, "original")]
    else:
        chart_ids = [(19723756, "soaring"), (3778678, "hot"),
                      (71384707, "light"), (2884035, "original")]
    for topid, label in chart_ids:
        results = get_toplist(topid, num=30)
        add(results, f"chart:{label}")

    print(f"  [build {mode}] Total: {len(candidates)} candidates")
    result = list(candidates.values())
    flush_artist_cache()
    save_candidates(result, mode)
    return result


_artist_id_cache: dict = {}
_cache_dirty = False

def _load_artist_cache():
    """Load persistent artist ID cache from disk."""
    if os.path.exists(ARTIST_ID_FILE):
        try:
            with open(ARTIST_ID_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            import traceback
            print(f"  [WARN] Failed to load artist-id cache from {ARTIST_ID_FILE}: {traceback.format_exc()}")
            pass
    return {}

def _save_artist_cache():
    """Mark artist cache dirty — flushed in batch by flush_artist_cache()."""
    global _cache_dirty
    _cache_dirty = True

def flush_artist_cache():
    """Persist artist ID cache to disk if dirty."""
    global _cache_dirty
    if _cache_dirty:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(ARTIST_ID_FILE, "w", encoding="utf-8") as f:
            json.dump(_artist_id_cache, f, ensure_ascii=False, indent=2)
        _cache_dirty = False

def _find_artist_id(name):
    """Search for an artist ID by name. Uses persistent cache to avoid
    repeated API calls (Netease rate-limits artist lookups aggressively)."""
    global _artist_id_cache
    if not _artist_id_cache:
        _artist_id_cache = _load_artist_cache()

    if name in _artist_id_cache:
        return _artist_id_cache[name]

    data = ncm_get("/search", {"keywords": name, "limit": 5})
    if data and data.get("code") == 200:
        songs = data.get("result", {}).get("songs", [])
        for s in songs:
            for a in s.get("artists", []):
                if a.get("name", "").lower() == name.lower():
                    _artist_id_cache[name] = a.get("id", 0)
                    _save_artist_cache()
                    return a.get("id", 0)
        # Fallback: use first artist from first result
        if songs:
            aid = songs[0].get("artists", [{}])[0].get("id", 0)
            if aid:
                _artist_id_cache[name] = aid
                _save_artist_cache()
                return aid
    return 0


# ============================================================
# HISTORY
# ============================================================

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            h = json.load(f)
            # Normalize old format
            if "recommended_mids" in h:
                h["recommended_ids"] = [str(x) for x in h.pop("recommended_mids")]
            if "recommended_ids" not in h:
                h["recommended_ids"] = []
            return h
    return {"recommended_ids": [], "liked_artists": {}, "skipped_artists": {}, "dates": []}


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def mark_judged_songs(candidates):
    """Mark songs that have been liked/skipped/neutral as _played=True.
    Call after loading cached candidates to prevent judged songs re-entering queue."""
    if not candidates:
        return candidates
    h = load_history()
    judged_ids = set()
    song_plays = h.get("song_plays", {})
    for sid, entry in song_plays.items():
        if entry.get("liked") or entry.get("skipped") or entry.get("neutral"):
            judged_ids.add(sid)
    # Also mark anything in recommended_ids (already recommended before)
    for sid in h.get("recommended_ids", []):
        judged_ids.add(str(sid))

    marked = 0
    for s in candidates:
        sid = str(s.get("songid", ""))
        if sid and sid in judged_ids:
            s["_played"] = True
            marked += 1
    if marked:
        print(f"  [mark_judged] Marked {marked} already-judged songs as _played")
    return candidates


# NOTE: Legacy fetch_candidates / _fetch_rap / _fetch_focus removed.
# Use build_candidates() instead — it has parallel search + dedup + v3 scoring.


# ============================================================
# SCORING v3 — track-level feedback + recency decay + tag matching
# ============================================================

def _days_ago(date_str):
    """Convert 'MM-DD HH:MM' or ISO date string to fractional days ago."""
    if not date_str:
        return 999
    try:
        now = datetime.now()
        if "T" in date_str:
            dt = datetime.fromisoformat(date_str)
        elif len(date_str) >= 10 and date_str[4] == "-":
            dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        else:
            dt = datetime.strptime(date_str, "%m-%d %H:%M")
            dt = dt.replace(year=now.year)
        # Future timestamps = right now (same day)
        if dt > now:
            return 0.0
        return max(0.0, (now - dt).total_seconds() / 86400)
    except Exception:
        import traceback
        print(f"  [WARN] days_ago failed for {date_str!r}: {traceback.format_exc()}")
        return 999


def _recency_weight(date_str, half_life=7):
    """0.5^(days/half_life). Recent = near 1.0, old = near 0."""
    return 0.5 ** (_days_ago(date_str) / half_life)


def _extract_tags(song):
    """Extract genre/style tags from song metadata (sources, singer names, etc.)."""
    tags = set()
    for src in song.get("_sources", []):
        # genre:hip-hop → hip-hop
        if src.startswith("genre:") or src.startswith("focus:"):
            tag = src.split(":", 1)[1].strip().lower()
            tags.add(tag)
        # artist:Eminem → eminem
        elif src.startswith("artist:"):
            tags.add(src.split(":", 1)[1].strip().lower())
    return tags


def _build_user_tags(history):
    """Build user taste tags from liked songs' metadata and played history."""
    tags = {}
    sp = history.get("song_plays", {})
    for sid, entry in sp.items():
        if entry.get("liked"):
            w = _recency_weight(entry.get("last_played", ""))
            # Tag by artist
            artist = entry.get("artist", "")
            if artist:
                for a in artist.split(" / "):
                    tags[a.strip().lower()] = tags.get(a.strip().lower(), 0) + w
        elif entry.get("skipped"):
            artist = entry.get("artist", "")
            if artist:
                for a in artist.split(" / "):
                    tags[a.strip().lower()] = tags.get(a.strip().lower(), 0) - 0.3
    # Normalize to [0, 1]
    if tags:
        mx = max(abs(v) for v in tags.values()) or 1
        tags = {k: v / mx for k, v in tags.items()}
    return tags


def _track_feedback(song, history):
    """Score based on per-song play history with recency decay. Returns (-0.25, +0.35)."""
    sid = str(song.get("songid", ""))
    sp = history.get("song_plays", {}).get(sid, {})
    if not sp:
        return 0.0

    last = sp.get("last_played", "")
    w = _recency_weight(last) if last else 1.0

    if sp.get("liked"):
        # Strong positive, decays over time but stays positive
        return 0.30 * max(w, 0.3)
    elif sp.get("skipped"):
        # Strong negative, also decays (hate fades)
        return -0.20 * max(w, 0.3)
    elif sp.get("neutral") or sp.get("count", 0) > 0:
        # Heard it, didn't love or hate — weak positive
        return 0.05 * w
    return 0.0


def _tag_match_score(song, user_tags):
    """How well song tags match user taste (0.0 - 0.20)."""
    song_tags = _extract_tags(song)
    if not song_tags or not user_tags:
        return 0.0
    hits = 0
    weight = 0.0
    for tag in song_tags:
        if tag in user_tags:
            w = user_tags[tag]
            if w > 0:
                hits += 1
                weight += w
    if hits == 0:
        return 0.0
    # Normalize: hits/len(song_tags) × avg_weight
    tag_ratio = min(hits / len(song_tags), 1.0)
    avg_w = min(weight / hits, 1.0)
    return round(tag_ratio * avg_w * 0.20, 3)


def _exploration_bonus(song, mode_taste):
    """Bonus for novelty — new artists, unplayed songs (0.0 - 0.10)."""
    bonus = 0.0
    artist_weights = mode_taste.get("artist_weights", {})
    singers = [s.get("name", "") for s in song.get("singer", [])]
    if not any(name in artist_weights for name in singers):
        bonus += 0.06
    if not song.get("_played", False) and song.get("_score", 0) < 0.1:
        bonus += 0.04
    return min(bonus, 0.10)


# ============================================================
# SCORING — mode-specific base + v3 feedback
# ============================================================

def _artist_score(song, mode_taste):
    """v3: Artist baseline match (0.0 - 0.15), capped."""
    singers = [s.get("name", "") for s in song.get("singer", [])]
    aw = mode_taste.get("artist_weights", {})
    s = sum(aw.get(name, 0) for name in singers) * 0.3
    return min(s, 0.15)


def _source_score(song):
    """v3: Source quality bonus (0.0 - 0.05)."""
    for src in song.get("_sources", []):
        if src.startswith("artist:"):
            return 0.05
    for src in song.get("_sources", []):
        if src.startswith("similar:"):
            return 0.03
    return 0.01


def _duration_score(song):
    """v3: Prefer 2-6 min songs."""
    dur = (song.get("duration", 0) or 0) / 1000
    if 120 < dur < 360:
        return 0.02
    return 0.0


def _chat_signal_score(song, history):
    """
    Score a song based on recent chat signals stored in history.json.
    Signals decay over time — only the latest 50 signals are considered.
    Returns a float in [-0.15, 0.15] range.
    """
    signals = history.get("chat_signals", [])
    if not signals:
        return 0.0

    singers = [s.get("name", "").lower() for s in song.get("singer", [])]
    song_name = (song.get("songname", "") or "").lower()
    # Crude genre detection from song tags
    song_tags = " ".join([
        song.get("genre", "") or "",
        " ".join(song.get("tags", []) or []),
    ]).lower()

    score = 0.0
    recent = signals[-30:]  # recent 30 signals only (decay window)
    for sig in recent:
        artist = (sig.get("artist", "") or "").lower()
        msg_artist = (sig.get("msg_artist", "") or "").lower()
        intent = sig.get("intent", "")
        w = sig.get("weight", 0.05) * 0.5  # halve signal weight for scoring

        # Artist-specific signals
        if artist or msg_artist:
            artist_hit = any(
                a in artist or a in msg_artist or artist in a or msg_artist in a
                for a in singers
            )
            if artist_hit:
                if "like" in intent:
                    score += w * 1.5
                elif "skip" in intent:
                    score -= w * 1.5
                continue  # artist signals don't spill to genre

        # Genre/mood signals (apply broadly to tag-matching songs)
        if intent in ("prefer_calm",):
            calm_kw = ("ballad", "抒情", "安静", "慢", "柔和", "acoustic", "轻音乐")
            if any(kw in song_tags for kw in calm_kw):
                score += w
        elif intent in ("prefer_energetic",):
            energy_kw = ("rock", "摇滚", "电子", "electro", "dance", "舞曲", "hip", "rap")
            if any(kw in song_tags for kw in energy_kw):
                score += w
        elif intent in ("prefer_classic",):
            # Songs with earlier release years get a boost
            year = song.get("year", 2024) or 2024
            if year < 2010:
                score += w
        elif intent in ("prefer_chinese",):
            cn_kw = ("mandarin", "华语", "国语", "中国风", "古风", "民谣")
            if any(kw in song_tags for kw in cn_kw):
                score += w
        elif intent in ("prefer_novelty",):
            # Exploration gets a bonus — handled by _exploration_bonus already,
            # but we add a smaller bonus for less-played songs
            play_count = history.get("song_plays", {}).get(str(song.get("songid", "")), {}).get("count", 0)
            if play_count <= 1:
                score += w * 0.5
        elif intent == "prefer_similar":
            # Slight boost for anything matching current taste tags
            score += w * 0.3

    return max(-0.15, min(0.15, round(score, 4)))


def score_v3(song, mode_taste, history, user_tags=None):
    """
    Unified v3 scoring: track feedback (0.30) + tag match (0.18)
    + artist baseline (0.12) + chat signals (0.10) + exploration (0.08)
    + source (0.04) + duration (0.02).
    Total ceiling ~0.84 before normalization.

    Stores a score breakdown on song._score_breakdown for UI use.
    """
    if user_tags is None:
        user_tags = _build_user_tags(history)

    singers = [s.get("name", "") for s in song.get("singer", [])]

    # Compute each component
    track_fb = _track_feedback(song, history) * 0.30
    tag_match = _tag_match_score(song, user_tags) * 0.18
    artist_base = _artist_score(song, mode_taste) * 0.12
    exploration = _exploration_bonus(song, mode_taste) * 0.08
    source = _source_score(song) * 0.04
    duration = _duration_score(song) * 0.02
    collab = 0.02 if len(singers) > 1 else 0.0
    chat_sig = _chat_signal_score(song, history) * 0.10

    total = max(0, round(track_fb + tag_match + artist_base + exploration
                         + source + duration + collab + chat_sig, 3))

    # Store breakdown for explainable recommendations UI
    song["_score_breakdown"] = {
        "track_feedback": round(track_fb, 3),
        "tag_match": round(tag_match, 3),
        "artist_baseline": round(artist_base, 3),
        "exploration": round(exploration, 3),
        "source_quality": round(source, 3),
        "duration": round(duration, 3),
        "chat_signal": round(chat_sig, 3),
        "total": total,
    }
    return total


def score_candidates(candidates, mode="rap"):
    """Score all candidates in a pool (v3). Modifies _score in-place."""
    taste = load_taste()
    history = load_history()
    mode_taste = get_mode_taste(taste, mode)
    user_tags = _build_user_tags(history)

    for song in candidates:
        song["_score"] = score_v3(song, mode_taste, history, user_tags)

    candidates.sort(key=lambda s: s["_score"], reverse=True)
    # NOTE: save_candidates deferred to caller — avoids excessive disk writes
    return candidates


def rescore_unplayed(candidates, mode="rap"):
    """Re-score only unplayed songs (v3)."""
    taste = load_taste()
    history = load_history()
    mode_taste = get_mode_taste(taste, mode)
    user_tags = _build_user_tags(history)

    for song in candidates:
        if not song.get("_played", False):
            song["_score"] = score_v3(song, mode_taste, history, user_tags)

    # Don't sort here — caller decides when to reorder.
    # _reload_list controls sort to avoid disrupting playback order mid-session.
    # NOTE: save_candidates deferred to caller — avoids excessive disk writes
    return candidates


# ============================================================
# ε-GREEDY BANDIT
# ============================================================

def select_bandit_pick(songs, epsilon=None):
    """
    ε-greedy selection: with probability ε, pick from unexplored songs.
    Otherwise pick the top-scored song.
    Returns (index, is_explore) — is_explore=True means this was an exploration pick.
    epsilon: if None, defaults to 0.15. Clamped to [0.05, 0.25].
    """
    import random as _random
    eps = epsilon if epsilon is not None else 0.15
    eps = max(0.05, min(0.25, eps))

    if not songs:
        return 0, False

    if _random.random() < eps:
        # Explore: pick from songs with no play history
        unexplored = [i for i, s in enumerate(songs) if not s.get("_played", False)]
        if unexplored:
            return _random.choice(unexplored), True

    # Exploit: pick top scored
    return 0, False  # songs are already sorted by score desc


def update_epsilon(epsilon, action):
    """
    Adjust epsilon based on user action.
    - like on exploration → epsilon drops (taste confirmed)
    - skip on exploration → epsilon stays or rises
    - skip on exploitation → epsilon rises (taste may be stale)
    Returns new epsilon.
    """
    if action == "like_explore":
        return max(0.05, epsilon - 0.01)
    elif action == "skip_exploit":
        return min(0.25, epsilon + 0.02)
    elif action == "skip_explore":
        return min(0.25, epsilon + 0.01)
    return epsilon


def expand_from_simi(song_ids, candidates, mode="rap"):
    """
    Fetch similar songs for given IDs and add to candidate pool (parallelized).
    Returns list of newly added candidates.
    """
    existing_ids = {str(s["songid"]) for s in candidates}
    seed_ids, seed_names = _load_seed_ids()
    existing_ids |= seed_ids
    existing_names = {_norm(s.get("songname", "")) for s in candidates}
    existing_names |= seed_names
    new_songs = []

    # Fetch simi data in parallel
    def _fetch_simi(sid):
        data = ncm_get("/simi/song", {"id": sid})
        return sid, data if data and data.get("code") == 200 else None

    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = [ex.submit(_fetch_simi, sid) for sid in song_ids[:10]]
        for f in as_completed(futures):
            sid, data = f.result()
            if not data:
                continue
            for s in data.get("songs", [])[:5]:
                nid = str(s.get("id", ""))
                nname = _norm(s.get("name", ""))
                if nid in existing_ids or nname in existing_names:
                    continue
                song = Song.from_ncm_song(s, f"simi:{sid}")
                song._from_simi = True
                candidates.append(song)
                existing_ids.add(nid)
                existing_names.add(nname)
                new_songs.append(song)

    if new_songs:
        print(f"  [expand] Added {len(new_songs)} similar songs")
        taste = load_taste()
        history = load_history()
        mode_taste = get_mode_taste(taste, mode)
        score_fn = score_v3
        for song in new_songs:
            song["_score"] = round(score_fn(song, mode_taste, history), 3)
        candidates.sort(key=lambda s: s["_score"], reverse=True)
        save_candidates(candidates, mode)

    return new_songs


# ============================================================
# SELECTION
# ============================================================

def select_picks(candidates, mode="rap"):
    """
    Select diverse top picks from scored candidates.
    Max 3 per artist, min 12 unique artists.
    """
    if not candidates:
        return []
    if not any(s.get("_score", 0) > 0 for s in candidates):
        score_candidates(candidates, mode)

    picks = []
    artist_counts = Counter()
    primary_artists = set()

    for song in candidates:
        singers = [s.get("name", "") for s in song.get("singer", [])]
        if any(artist_counts[s] >= MAX_PER_ARTIST for s in singers):
            continue
        picks.append(song)
        for s in singers:
            artist_counts[s] += 1
        if singers:
            primary_artists.add(singers[0])
        if len(picks) >= DAILY_PICKS:
            break

    # Ensure minimum diversity
    if len(primary_artists) < MIN_ARTISTS:
        remaining = [s for s in candidates if s not in picks]
        for song in remaining:
            singers = [s.get("name", "") for s in song.get("singer", [])]
            if singers and singers[0] not in primary_artists:
                picks.append(song)
                if singers:
                    primary_artists.add(singers[0])
            if len(primary_artists) >= MIN_ARTISTS:
                break

    return picks[:DAILY_PICKS]


# ============================================================
# MAIN
# ============================================================

def generate(mode="rap"):
    """CLI entry point — build candidates, score, and output today.json."""
    label = {"rap": "Rap/Vibe", "mixed": "Mixed/Vibe"}[mode]
    print("=" * 60)
    print(f"  Music Recommendation Engine v2 — {label}")
    print(f"  Source: NetEase Cloud Music API @ {NCM}")
    print("=" * 60)

    print("\n[1/3] Building candidate pool...")
    candidates = build_candidates(mode)

    print(f"\n[2/3] Scoring {len(candidates)} candidates...")
    candidates = score_candidates(candidates, mode)

    print(f"\n[3/3] Selecting {DAILY_PICKS} picks...")
    picks = select_picks(candidates, mode)

    # Fetch playable URLs for top picks
    print(f"\n  Fetching playable URLs for top picks...")
    for song in picks[:20]:
        url_info = get_song_url(song["songid"])
        if url_info:
            song["url"] = url_info
        time.sleep(0.15)

    today_str = datetime.now().strftime("%Y-%m-%d")
    output = {
        "date": today_str,
        "generated_at": datetime.now().isoformat(),
        "mode": mode,
        "count": len(picks),
        "songs": [],
    }
    for i, song in enumerate(picks):
        entry = {
            "rank": i + 1,
            "songname": song["songname"],
            "songid": song["songid"],
            "singer": song.get("singer", []),
            "albumname": song.get("albumname", ""),
            "albumid": song.get("albumid", 0),
            "duration": song.get("duration", 0),
            "score": song["_score"],
            "sources": song.get("_sources", []),
        }
        if "url" in song:
            entry["url"] = song["url"]
        output["songs"].append(entry)

    out_file = TODAY_FILE if mode == "rap" else TODAY_FOCUS_FILE
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Update history
    history = load_history()
    history.setdefault("recommended_ids", []).extend(
        str(s["songid"]) for s in output["songs"])
    history["recommended_ids"] = history["recommended_ids"][-5000:]
    history.setdefault("dates", []).append(today_str)
    save_history(history)

    print(f"\n{'='*60}")
    print(f"  Done! {len(picks)} songs saved to {os.path.basename(out_file)}")
    print(f"{'='*60}")

    print(f"\n--- {label} Top 10 ---")
    for song in output["songs"][:10]:
        singers = " / ".join(s["name"] for s in song["singer"])
        has_url = "[>]" if "url" in song else "[ ]"
        try:
            print(f"  {has_url} {song['rank']:2d}. {song['songname'][:35]:35s} — {singers[:40]} [{song['score']:.2f}]")
        except UnicodeEncodeError:
            print(f"  {has_url} {song['rank']:2d}. {song['songname'][:35]:35s} -- {singers[:40]} [{song['score']:.2f}]".encode('ascii', errors='replace').decode())

    return output


def generate_both():
    r = generate("rap")
    print("\n")
    m = generate("mixed")
    return {"rap": r, "mixed": m}


if __name__ == "__main__":
    mode = "both"
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("--mode", "-m"):
            mode = sys.argv[2].lower() if len(sys.argv) > 2 else "both"
        elif arg in ("rap", "mixed", "both"):
            mode = arg

    if mode == "both":
        generate_both()
    else:
        generate(mode)
