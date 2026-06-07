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
from datetime import datetime

import requests

NCM = "http://localhost:3000"

HOME = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HOME, "data")
TASTE_FILE = os.path.join(DATA_DIR, "taste.json")
TODAY_FILE = os.path.join(DATA_DIR, "today.json")
TODAY_FOCUS_FILE = os.path.join(DATA_DIR, "today_focus.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")

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
    "rap": ["rap", "freestyle", "cypher", "diss", "flow", "bars", "remix",
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

def ncm_get(path, params=None):
    """Call local NetEase Cloud Music API."""
    try:
        r = requests.get(f"{NCM}{path}", params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  [API ERR] {path}: {e}")
        return None


def search_songs(query, limit=25):
    """Search songs via NetEase API."""
    data = ncm_get("/search", {"keywords": query, "limit": limit})
    if not data or data.get("code") != 200:
        return []
    songs = []
    for s in data.get("result", {}).get("songs", []):
        songs.append({
            "songname": s.get("name", ""),
            "songid": s.get("id", 0),
            "duration": s.get("duration", 0),  # ms
            "singer": [{"name": a.get("name", "")} for a in s.get("artists", [])],
            "albumname": s.get("album", {}).get("name", ""),
            "albumid": s.get("album", {}).get("id", 0),
        })
    return songs


def get_toplist(topid, num=30):
    """Fetch top chart songs from NetEase."""
    data = ncm_get("/top/list", {"id": topid})
    if not data or data.get("code") != 200:
        return []
    songs = []
    for s in data.get("playlist", {}).get("tracks", [])[:num]:
        songs.append({
            "songname": s.get("name", ""),
            "songid": s.get("id", 0),
            "duration": s.get("dt", 0),  # ms
            "singer": [{"name": a.get("name", "")} for a in s.get("ar", [])],
            "albumname": s.get("al", {}).get("name", ""),
            "albumid": s.get("al", {}).get("id", 0),
        })
    return songs


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


# (load_taste_profile / save_taste replaced by v2 versions at top of file)


# ============================================================
# CANDIDATE POOL
# ============================================================

CANDIDATE_DIR = os.path.join(DATA_DIR, "candidates")


def _candidate_path(mode):
    os.makedirs(CANDIDATE_DIR, exist_ok=True)
    return os.path.join(CANDIDATE_DIR, f"{mode}.json")


def load_candidates(mode):
    """Load cached candidate pool for mode."""
    path = _candidate_path(mode)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_candidates(candidates, mode):
    """Save candidate pool to disk."""
    data = {
        "mode": mode,
        "built_at": datetime.now().isoformat(),
        "count": len(candidates),
        "songs": candidates,
    }
    with open(_candidate_path(mode), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_candidates(mode="rap"):
    """
    Build candidate pool for a mode. Returns list of song dicts with _sources.
    Does NOT score — scoring is separate via score_candidates().
    """
    taste = load_taste()
    history = load_history()
    mode_taste = get_mode_taste(taste, mode)

    known_ids = set()
    known_ids |= set(str(x) for x in history.get("recommended_ids", []))

    candidates = {}
    seen_names = set()

    def add(iterable, source):
        for s in iterable:
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

    # Source 1: Top seed artists
    if use_top:
        print(f"  [build {mode}] Searching {len(use_top)} top artists...")
        for artist in use_top:
            results = search_songs(artist, limit=25)
            add(results, f"artist:{artist}")
            time.sleep(0.3)

    # Source 2: Similar artists via NetEase
    similar_artists = set()
    for artist in use_top[:8]:
        aid = _find_artist_id(artist)
        if aid:
            data = ncm_get("/simi/artist", {"id": aid})
            if data and data.get("code") == 200:
                for a in data.get("artists", [])[:3]:
                    similar_artists.add(a.get("name", ""))
            time.sleep(0.2)
    print(f"  [build {mode}] Searching {min(len(similar_artists), 16)} similar artists...")
    for artist in list(similar_artists)[:16]:
        results = search_songs(artist, limit=15)
        add(results, f"similar:{artist}")
        time.sleep(0.3)

    # Source 3: Genre queries
    if mode == "rap":
        genre_queries = RAP_GENRE_QUERIES
    else:
        genre_queries = MIXED_GENRE_QUERIES
    print(f"  [build {mode}] Searching {min(len(genre_queries), 24)} genres...")
    for query in genre_queries[:24]:
        results = search_songs(query, limit=25)
        add(results, f"genre:{query}")
        time.sleep(0.3)

    # Source 4: Charts
    print(f"  [build {mode}] Fetching charts...")
    if mode == "rap":
        chart_ids = [(19723756, "soaring"), (3779629, "new"), (3778678, "hot")]
    else:
        chart_ids = [(19723756, "soaring"), (3778678, "hot"),
                      (71384707, "light"), (2884035, "original")]
    for topid, label in chart_ids:
        results = get_toplist(topid, num=30)
        add(results, f"chart:{label}")
        time.sleep(0.2)

    print(f"  [build {mode}] Total: {len(candidates)} candidates")
    result = list(candidates.values())
    save_candidates(result, mode)
    return result


def _find_artist_id(name):
    """Search for an artist ID by name. Returns first match ID or 0."""
    data = ncm_get("/search", {"keywords": name, "type": 100, "limit": 1})
    if data and data.get("code") == 200:
        artists = data.get("result", {}).get("artists", [])
        if artists:
            return artists[0].get("id", 0)
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


# ============================================================
# CANDIDATE FETCHING
# ============================================================

def fetch_candidates(taste, history, mode="rap"):
    """Fetch candidates from NetEase API."""
    candidates = {}
    known = set(str(x) for x in taste.get("known_ids", []))
    known |= set(str(x) for x in history.get("recommended_ids", []))
    known_names = set(taste.get("known_names", []))
    seen_names = set(known_names)

    def add(iterable, source):
        for s in iterable:
            sid = str(s.get("songid", ""))
            name_norm = _norm(s.get("songname", ""))
            if sid and sid in known:
                continue
            if sid and sid in candidates:
                candidates[sid]["_sources"].append(source)
                continue
            if name_norm in seen_names:
                continue
            if sid:
                s["_sources"] = [source]
                candidates[sid] = s
                seen_names.add(name_norm)

    if mode == "rap":
        _fetch_rap(taste, add)
    elif mode == "focus":
        _fetch_focus(add)

    print(f"  Total candidates: {len(candidates)}")
    return list(candidates.values())


def _fetch_rap(taste, add):
    """Fetch rap mode candidates."""
    top_artists = taste.get("top_artists", [])
    n_top = 20 if top_artists else 0

    # Source 1: top personal artists
    if n_top:
        print(f"  [Source 1] Searching {n_top} top artists...")
        for artist in top_artists[:n_top]:
            results = search_songs(artist, limit=25)
            add(results, f"artist:{artist}")
            time.sleep(0.3)

    # Source 1b: Aftermath ecosystem
    print(f"  [Source 1b] Searching {min(len(AFTERMATH_ARTISTS), 12)} ecosystem artists...")
    for artist in AFTERMATH_ARTISTS[:12]:
        results = search_songs(artist, limit=15)
        add(results, f"ecosystem:{artist}")
        time.sleep(0.3)

    # Source 2: genre queries
    print(f"  [Source 2] Searching genres...")
    queries = RAP_GENRE_QUERIES
    weights = taste.get("genre_weights", {})
    if weights.get("hip-hop", 0) > 0.3:
        queries += ["storytelling rap classics", "boom bap instrumentals"]
    if weights.get("rock", 0) > 0.1:
        queries += ["rap rock crossover", "alternative rock"]
    if weights.get("chinese", 0) > 0.1:
        queries += ["Chinese folk song", "Cantonese old song", "Chinese ballad classic"]

    for query in queries[:20]:
        results = search_songs(query, limit=25)
        add(results, f"genre:{query}")
        time.sleep(0.3)

    # Source 3: NetEase charts
    print(f"  [Source 3] Fetching charts...")
    # NetEase chart IDs: 3778678=热歌榜, 3779629=新歌榜, 19723756=飙升榜, 2884035=原创榜
    for topid, label in [(19723756, "soaring"), (3779629, "new"), (3778678, "hot")]:
        results = get_toplist(topid, num=30)
        add(results, f"chart:{label}")
        time.sleep(0.2)


def _fetch_focus(add):
    """Fetch focus mode candidates."""
    print(f"  [Focus 1] Searching {len(FOCUS_GENRE_QUERIES)} focus genres...")
    for query in FOCUS_GENRE_QUERIES[:24]:
        results = search_songs(query, limit=25)
        add(results, f"focus:{query}")
        time.sleep(0.3)

    print(f"  [Focus 2] Fetching chill charts...")
    # 71384707=轻音乐, 19723756=飙升榜(new music)
    for topid, label in [(71384707, "light"), (19723756, "soaring")]:
        results = get_toplist(topid, num=30)
        add(results, f"chart:{label}")
        time.sleep(0.2)


# ============================================================
# SCORING
# ============================================================

def score_rap(song, mode_taste, history):
    """Score a song for rap mode using mode-specific taste."""
    score = 0.0
    singers = [s.get("name", "") for s in song.get("singer", [])]
    singer_str = " ".join(singers).lower()
    text = f"{song.get('songname','')} {song.get('albumname','')} {singer_str}".lower()
    artist_weights = mode_taste.get("artist_weights", {})
    genre_weights = mode_taste.get("genre_weights", {})

    # Artist match (from mode-specific weights)
    for name in singers:
        w = artist_weights.get(name, 0)
        score += w * 0.3
    score = min(score, 0.35)

    # Genre keyword scoring
    gw = {
        "rap": genre_weights.get("hip-hop", 0.4),
        "pop": genre_weights.get("pop", 0.1) * 0.5,
        "rock": genre_weights.get("rock", 0.1),
        "chinese": genre_weights.get("chinese", 0.1),
    }
    for cat, kwlist in RAP_SCORE_KW.items():
        hits = sum(1 for kw in kwlist if kw in text)
        score += hits * gw.get(cat, 0.02) * 0.02

    # Storytelling boost
    story_kw = ["story", "narrative", "letter", "dear", "memory",
                "dream", "life", "death", "real", "truth", "struggle"]
    score += sum(1 for kw in story_kw if kw in text) * 0.025

    # Collaboration bonus
    if len(singers) > 1:
        score += 0.05
    if len(singers) > 2:
        score += 0.03

    # Duration: prefer 2-5 min
    dur = (song.get("duration", 0) or 0) / 1000
    if 120 < dur < 320:
        score += 0.04

    # Source quality
    for src in song.get("_sources", []):
        if src.startswith("artist:"):
            score += 0.08
            break
    for src in song.get("_sources", []):
        if src.startswith("similar:"):
            score += 0.05
            break

    # History feedback
    liked = history.get("liked_artists", {})
    skipped = history.get("skipped_artists", {})
    for name in singers:
        if name in liked:
            score += 0.05 * min(liked.get(name, 0) / 3, 1.0)
        if name in skipped:
            score -= 0.03 * min(skipped.get(name, 0) / 3, 1.0)

    # Claude Picks boost
    cp_artists = history.get("claude_picks_artists", {})
    for name in singers:
        if name in cp_artists:
            score += 0.1
            break

    # Novelty: not in seed artists
    if not any(s in artist_weights for s in singers):
        score += 0.05

    return max(0, score)


def score_mixed(song, mode_taste, history):
    """Score a song for mixed mode — no genre bias, equal exploration."""
    score = 0.0
    singers = [s.get("name", "") for s in song.get("singer", [])]
    singer_str = " ".join(singers).lower()
    text = f"{song.get('songname','')} {song.get('albumname','')} {singer_str}".lower()
    artist_weights = mode_taste.get("artist_weights", {})

    # Artist match
    for name in singers:
        w = artist_weights.get(name, 0)
        score += w * 0.3
    score = min(score, 0.35)

    # Genre keyword — pure counting, no weights
    genre_kw = [
        "pop", "rock", "R&B", "soul", "jazz", "funk", "disco",
        "indie", "alternative", "folk", "acoustic", "ballad",
        "electronic", "synth", "ambient", "chill", "dream",
        "Chinese", "Mandarin", "Cantonese", "classic",
        "orchestral", "soundtrack", "OST", "piano", "guitar",
        "world", "Latin", "reggae", "bossa",
    ]
    hits = sum(1 for kw in genre_kw if kw.lower() in text)
    score += hits * 0.015

    # Collaboration
    if len(singers) > 1:
        score += 0.04

    # Duration: prefer 2-6 min
    dur = (song.get("duration", 0) or 0) / 1000
    if 120 < dur < 360:
        score += 0.05

    # History feedback
    liked = history.get("liked_artists", {})
    skipped = history.get("skipped_artists", {})
    for name in singers:
        if name in liked:
            score += 0.05 * min(liked.get(name, 0) / 3, 1.0)
        if name in skipped:
            score -= 0.03 * min(skipped.get(name, 0) / 3, 1.0)

    # Claude Picks
    cp_artists = history.get("claude_picks_artists", {})
    for name in singers:
        if name in cp_artists:
            score += 0.1
            break

    # Novelty boost (higher for mixed)
    if not any(s in artist_weights for s in singers):
        score += 0.08

    # Chat signals
    chat_signals = history.get("chat_signals", [])
    for sig in chat_signals[-5:]:
        intent = sig.get("intent", "")
        if intent == "like_artist":
            for name in singers:
                if sig.get("artist", "").lower() in name.lower():
                    score += 0.05 * sig.get("weight", 0.5)
        elif intent == "skip_artist":
            for name in singers:
                if sig.get("artist", "").lower() in name.lower():
                    score -= 0.03 * sig.get("weight", 0.5)

    return max(0, score)


def score_candidates(candidates, mode="rap"):
    """Score all candidates in a pool. Modifies _score in-place. Returns sorted list."""
    taste = load_taste()
    history = load_history()
    mode_taste = get_mode_taste(taste, mode)
    score_fn = score_rap if mode == "rap" else score_mixed

    for song in candidates:
        song["_score"] = round(score_fn(song, mode_taste, history), 3)

    candidates.sort(key=lambda s: s["_score"], reverse=True)
    save_candidates(candidates, mode)
    return candidates


def rescore_unplayed(candidates, mode="rap"):
    """Re-score only unplayed songs. Much faster than full score_candidates."""
    taste = load_taste()
    history = load_history()
    mode_taste = get_mode_taste(taste, mode)
    score_fn = score_rap if mode == "rap" else score_mixed

    for song in candidates:
        if not song.get("_played", False):
            song["_score"] = round(score_fn(song, mode_taste, history), 3)

    candidates.sort(key=lambda s: s["_score"], reverse=True)
    save_candidates(candidates, mode)
    return candidates


def expand_from_simi(song_ids, candidates, mode="rap"):
    """
    Fetch similar songs for given IDs and add to candidate pool.
    Returns list of newly added candidates.
    """
    existing_ids = {str(s["songid"]) for s in candidates}
    new_songs = []

    for sid in song_ids[:10]:
        data = ncm_get("/simi/song", {"id": sid})
        if not data or data.get("code") != 200:
            continue
        for s in data.get("songs", [])[:5]:
            nid = str(s.get("id", ""))
            if nid in existing_ids:
                continue
            song = {
                "songname": s.get("name", ""),
                "songid": s.get("id", 0),
                "duration": s.get("duration", 0),
                "singer": [{"name": a.get("name", "")} for a in s.get("artists", [])],
                "albumname": s.get("album", {}).get("name", ""),
                "albumid": s.get("album", {}).get("id", 0),
                "_sources": [f"simi:{sid}"],
                "_score": 0,
                "_played": False,
                "_from_simi": True,
            }
            candidates.append(song)
            existing_ids.add(nid)
            new_songs.append(song)
        time.sleep(0.2)

    if new_songs:
        print(f"  [expand] Added {len(new_songs)} similar songs")
        taste = load_taste()
        history = load_history()
        mode_taste = get_mode_taste(taste, mode)
        score_fn = score_rap if mode == "rap" else score_mixed
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
        print(f"  {has_url} {song['rank']:2d}. {song['songname'][:35]:35s} — {singers[:40]} [{song['score']:.2f}]")

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
