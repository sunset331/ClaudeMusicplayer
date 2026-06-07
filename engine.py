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


# ============================================================
# TASTE PROFILE
# ============================================================

def load_taste_profile():
    """Load or build taste profile."""
    if os.path.exists(TASTE_FILE):
        with open(TASTE_FILE, "r", encoding="utf-8") as f:
            profile = json.load(f)
            # Normalize old format (songmid → songid)
            if "known_mids" in profile:
                profile["known_ids"] = profile.pop("known_mids")
            if "known_ids" not in profile:
                profile["known_ids"] = []
            if "known_names" not in profile:
                profile["known_names"] = []
            return profile

    # No taste file yet — start fresh
    return {
        "total_songs": 0,
        "total_artists": 0,
        "top_artists": [],
        "artist_weights": {},
        "known_ids": [],
        "known_names": [],
        "genre_weights": {},
    }


def save_taste(profile):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TASTE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


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

def score_rap(song, taste, history):
    """Score for rap mode."""
    score = 0.0
    singers = [s.get("name", "") for s in song.get("singer", [])]
    singer_str = " ".join(singers).lower()
    song_name = song.get("songname", "")
    album = song.get("albumname", "")
    text = f"{song_name} {album} {singer_str}".lower()
    genre_weights = taste.get("genre_weights", {})

    # Artist match
    for name in singers:
        w = taste.get("artist_weights", {}).get(name, 0)
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

    # Collaboration
    if len(singers) > 1:
        score += 0.05
    if len(singers) > 2:
        score += 0.03

    # Rap+rock crossover
    if any(kw in text for kw in ["rock", "guitar", "band"]) and \
       any(kw in text for kw in ["rap", "hip-hop", "feat"]):
        score += 0.06

    # Duration: prefer 2-5 min (duration in ms)
    dur = (song.get("duration", 0) or 0) / 1000
    if 120 < dur < 320:
        score += 0.04
    elif dur > 320 and any(kw in text for kw in ["story", "narrative"]):
        score += 0.02

    # Source quality
    for src in song.get("_sources", []):
        if src.startswith("artist:"):
            score += 0.08
            break
    for src in song.get("_sources", []):
        if src.startswith("ecosystem:"):
            score += 0.06
            break
    for src in song.get("_sources", []):
        if src.startswith("genre:"):
            score += 0.03
            break

    # History feedback
    liked = history.get("liked_artists", {})
    skipped = history.get("skipped_artists", {})
    for name in singers:
        if name in liked:
            score += 0.05 * min(liked.get(name, 0) / 3, 1.0)
        if name in skipped:
            score -= 0.03 * min(skipped.get(name, 0) / 3, 1.0)

    # Novelty
    seen_count = sum(1 for s in singers if s in taste.get("artist_weights", {}))
    if seen_count == 0:
        score += 0.1

    return max(0, score)


def score_focus(song, taste, history):
    """Score for focus mode."""
    score = 0.2
    singers = [s.get("name", "") for s in song.get("singer", [])]
    singer_str = " ".join(singers).lower()
    song_name = song.get("songname", "")
    album = song.get("albumname", "")
    text = f"{song_name} {album} {singer_str}".lower()

    pos_hits = sum(1 for kw in FOCUS_SCORE_KW["positive"] if kw in text)
    score += pos_hits * 0.04

    neg_hits = sum(1 for kw in FOCUS_SCORE_KW["negative"] if kw in text)
    score -= neg_hits * 0.06

    instrumental_kw = ["instrumental", "piano", "orchestral", "soundtrack", "OST",
                       "acoustic", "classical", "meditation", "pure music", "纯音乐"]
    if any(kw in text for kw in instrumental_kw):
        score += 0.15

    dur = (song.get("duration", 0) or 0) / 1000
    if 120 < dur < 360:
        score += 0.05

    for src in song.get("_sources", []):
        if src.startswith("focus:"):
            score += 0.06

    if len(singers) > 2:
        score -= 0.05
    if len(singers) == 1:
        score += 0.03

    for name in singers:
        if name in taste.get("artist_weights", {}):
            score += 0.02
            break

    return max(0, score)


# ============================================================
# SELECTION
# ============================================================

def select_picks(candidates, taste, history, mode="rap"):
    """Score, rank, and select picks."""
    scored = []
    score_fn = score_rap if mode == "rap" else score_focus

    for song in candidates:
        s = score_fn(song, taste, history)
        song["_score"] = round(s, 3)
        scored.append(song)

    scored.sort(key=lambda x: x["_score"], reverse=True)

    picks = []
    artist_counts = Counter()
    primary_artists = set()

    for song in scored:
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
        remaining = [s for s in scored if s not in picks]
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
    """Generate recommendations for the given mode."""
    label = {"rap": "Rap/Vibe", "focus": "Focus/Chill"}[mode]
    print("=" * 60)
    print(f"  Music Recommendation Engine — {label}")
    print(f"  Source: NetEase Cloud Music API @ {NCM}")
    print("=" * 60)

    print("\n[1/4] Loading taste profile...")
    taste = load_taste_profile()
    print(f"  {taste['total_songs']} known songs, {taste['total_artists']} artists")

    print("\n[2/4] Loading history...")
    history = load_history()

    print(f"\n[3/4] Fetching candidates ({mode} mode)...")
    candidates = fetch_candidates(taste, history, mode)

    print(f"\n[4/4] Scoring and selecting {DAILY_PICKS} picks...")
    picks = select_picks(candidates, taste, history, mode)

    # Fetch playable URLs for top 20 picks (to avoid excessive API calls)
    print(f"\n  Fetching playable URLs for top picks...")
    song_urls = {}
    for song in picks[:20]:
        url_info = get_song_url(song["songid"])
        if url_info:
            song_urls[str(song["songid"])] = url_info
        status = "OK" if url_info else "NO (maybe VIP needed)"
        print(f"    [{len(song_urls)}/20] {song['songname'][:30]:30s} -> {status}")
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
        sid = str(song["songid"])
        entry = {
            "rank": i + 1,
            "songname": song["songname"],
            "songid": song["songid"],
            "singer": [{"name": s.get("name", "")} for s in song.get("singer", [])],
            "albumname": song.get("albumname", ""),
            "albumid": song.get("albumid", 0),
            "duration": song.get("duration", 0),
            "score": song["_score"],
            "sources": song.get("_sources", []),
        }
        # Attach URL if we fetched it
        if sid in song_urls:
            entry["url"] = song_urls[sid]
        output["songs"].append(entry)

    out_file = TODAY_FILE if mode == "rap" else TODAY_FOCUS_FILE
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Update history
    history["recommended_ids"].extend(str(s["songid"]) for s in output["songs"])
    history["recommended_ids"] = history["recommended_ids"][-5000:]
    history["dates"].append(today_str)
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
    f = generate("focus")
    return {"rap": r, "focus": f}


if __name__ == "__main__":
    mode = "both"
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("--mode", "-m"):
            mode = sys.argv[2].lower() if len(sys.argv) > 2 else "both"
        elif arg in ("rap", "focus", "both"):
            mode = arg

    if mode == "both":
        generate_both()
    else:
        generate(mode)
