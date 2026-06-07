# Realtime Recommendation Engine v2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade music player from batch daily picks to real-time interactive recommendations with QQ seed playlists, dynamic candidate pool, and AI chat panel.

**Architecture:** Refactor engine.py into importable module with `build_candidates()` / `score_candidates()` / `rescore_unplayed()` / `expand_from_simi()`. app.py imports engine directly instead of subprocess. New chat.py handles AI dialog + signal extraction. Three-column layout: song list | now playing | chat.

**Tech Stack:** Python 3.14, tkinter, ffplay, NetEase API (Docker localhost:3000), DeepSeek API (chat)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `import_qq.py` | Create (~120 lines) | QQ playlist JSON → NetEase songid matching |
| `engine.py` | Rewrite (~500 lines) | Candidate pool, scoring, rescoring, simi expansion |
| `chat.py` | Create (~150 lines) | DeepSeek API dialog + keyword signal extraction |
| `app.py` | Modify (~200 lines changed) | Three-column layout, engine integration, chat panel |
| `data/taste.json` | Migrate in-place | Old flat → mode-partitioned format |
| `data/candidates_rap.json` | Create (runtime) | Rap mode candidate pool |
| `data/candidates_mixed.json` | Create (runtime) | Mixed mode candidate pool |
| `data/qq_seed_rap.json` | Create (imported) | QQ rap playlist import result |
| `data/qq_seed_mixed.json` | Create (imported) | QQ mixed playlist import result |
| `data/qq_seed_style.json` | Create (imported) | QQ style playlist import result |

---

### Task 1: QQ Playlist Import Tool

**Files:**
- Create: `C:\Users\27576\music_player\import_qq.py`

- [ ] **Step 1: Create import_qq.py with API helpers and QQ response parser**

```python
#!/usr/bin/env python3
"""
QQ Music Playlist Importer
1. User extracts QQ playlist JSON from browser DevTools
2. Script parses songlist, searches NetEase API for matches
3. Saves matched songs to qq_seed_{label}.json
"""
import json, os, sys, time
import requests

HOME = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HOME, "data")
NCM = "http://localhost:3000"
os.makedirs(DATA_DIR, exist_ok=True)


def ncm_get(path, params=None):
    try:
        r = requests.get(f"{NCM}{path}", params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  [API ERR] {path}: {e}")
        return None


def parse_qq_playlist(raw):
    """
    Parse QQ Music playlist JSON response into [{name, artist, album}].
    Handles multiple QQ API response formats:
    - Format A: {data: {cdlist: [{songlist: [...]}]}}
    - Format B: {songlist: [...]}
    - Format C: {data: {songInfoList: [...]}}
    Each song entry may have:
    - {songname, singer: [{name}], albumname}
    - {name, ar: [{name}], al: {name}} 
    - {title, singer: [{name}], album: {name}}
    """
    songs = []

    def extract(songlist):
        for s in songlist:
            name = (s.get("songname") or s.get("name") or s.get("title") or "")
            if not name:
                continue
            # Extract artists
            artists = []
            singer_list = (s.get("singer") or s.get("ar") or s.get("artists") or [])
            for a in singer_list:
                an = a.get("name", "") if isinstance(a, dict) else str(a)
                if an:
                    artists.append(an)
            if not artists:
                continue
            # Extract album
            album = (s.get("albumname") or "")
            if not album:
                al = s.get("al") or s.get("album") or {}
                album = al.get("name", "") if isinstance(al, dict) else ""
            songs.append({
                "name": name.strip(),
                "artist": artists[0].strip(),
                "artists": [a.strip() for a in artists],
                "album": album.strip(),
            })

    # Try multiple QQ API response shapes
    data = raw.get("data", raw)
    if "cdlist" in data:
        for cd in data["cdlist"]:
            extract(cd.get("songlist", []))
    elif "songlist" in data:
        extract(data["songlist"])
    elif "songInfoList" in data:
        extract(data["songInfoList"])
    elif "songList" in data:
        extract(data["songList"])
    elif "list" in data:
        extract(data["list"])
    elif isinstance(raw, list):
        extract(raw)
    return songs


def search_ncm(song):
    """Search NetEase for a song, return best match (songid, songname, singer) or None."""
    query = f"{song['name']} {song['artist']}"
    data = ncm_get("/search", {"keywords": query, "limit": 5, "type": 1})
    if not data or data.get("code") != 200:
        return None
    results = data.get("result", {}).get("songs", [])
    if not results:
        return None

    target_name = song["name"].lower().strip()
    target_artist = song["artist"].lower().strip()

    best = None
    for r in results:
        r_name = r.get("name", "").lower().strip()
        r_artists = [a.get("name", "").lower().strip()
                     for a in r.get("artists", [])]
        # Score match quality
        score = 0
        if r_name == target_name:
            score += 5
        elif target_name in r_name or r_name in target_name:
            score += 3
        if target_artist in r_artists or any(target_artist in a for a in r_artists):
            score += 4
        elif any(a in target_artist or target_artist in a for a in r_artists):
            score += 1
        if best is None or score > best[0]:
            best = (score, r)
    if best and best[0] >= 3:
        r = best[1]
        return {
            "songname": r.get("name", ""),
            "songid": r.get("id", 0),
            "singer": [{"name": a.get("name", "")} for a in r.get("artists", [])],
            "albumname": r.get("album", {}).get("name", ""),
            "albumid": r.get("album", {}).get("id", 0),
            "duration": r.get("duration", 0),
            "match_score": best[0],
        }
    return None


def import_playlist(json_path, label):
    """
    Main import pipeline.
    json_path: path to QQ playlist JSON file
    label: 'rap', 'mixed', or 'style' — used for output filename
    """
    print(f"\n[Import] Loading {json_path}...")
    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    songs = parse_qq_playlist(raw)
    print(f"  Parsed {len(songs)} songs from QQ playlist")

    matched = []
    unmatched = []
    for i, song in enumerate(songs):
        print(f"  [{i+1}/{len(songs)}] Searching: {song['name'][:30]} — {song['artist'][:20]}", end=" ")
        match = search_ncm(song)
        if match:
            print(f"-> {match['songname'][:30]}")
            matched.append({**song, "ncm": match})
        else:
            print("-> NO MATCH")
            unmatched.append(song)
        time.sleep(0.25)

    out = {
        "source": f"qq_{label}",
        "imported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(songs),
        "matched": len(matched),
        "songs": matched,
    }
    out_path = os.path.join(DATA_DIR, f"qq_seed_{label}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    if unmatched:
        um_path = os.path.join(DATA_DIR, f"qq_unmatched_{label}.json")
        with open(um_path, "w", encoding="utf-8") as f:
            json.dump(unmatched, f, ensure_ascii=False, indent=2)
        print(f"  {len(unmatched)} unmatched saved to {um_path}")

    print(f"  Done! {len(matched)}/{len(songs)} matched, saved to {os.path.basename(out_path)}")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python import_qq.py <playlist.json> <label>")
        print("  label: rap, mixed, or style")
        print("\n  How to get playlist.json:")
        print("  1. Open QQ Music playlist page in browser")
        print("  2. F12 -> Network tab")
        print("  3. Filter by 'fcg' or 'songlist'")
        print("  4. Find the API response with song list data")
        print("  5. Right-click -> Copy -> Copy response")
        print("  6. Paste into a .json file")
        print("  7. Run: python import_qq.py <that-file>.json <label>")
        sys.exit(1)

    import_playlist(sys.argv[1], sys.argv[2])
```

- [ ] **Step 2: Verify script syntax**

Run: `cd /c/Users/27576/music_player && python -m py_compile import_qq.py`
Expected: no output (no syntax errors)

- [ ] **Step 3: Commit**

```bash
cd /c/Users/27576/music_player
git add import_qq.py
git commit -m "feat: add QQ playlist import tool"
```

---

### Task 2: taste.json Migration to Mode-Partitioned Format

**Files:**
- Modify: `C:\Users\27576\music_player\engine.py` (add migration + new read helpers)

- [ ] **Step 1: Add migration and taste I/O functions to engine.py**

Add these functions at the top of engine.py (after existing constant definitions, before existing functions):

```python
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
        return TASTE_V2_DEFAULT

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
    Removes duplicates, updates top_artists ranking and artist_weights.
    """
    seed_file = os.path.join(DATA_DIR, f"qq_seed_{mode}.json")
    if not os.path.exists(seed_file):
        print(f"  [taste] No seed file for {mode}: {seed_file}")
        return taste

    with open(seed_file, "r", encoding="utf-8") as f:
        seed = json.load(f)

    mode_taste = taste.setdefault("modes", {}).setdefault(
        mode, TASTE_V2_DEFAULT["modes"]["rap"])

    if "qq_seed_{}".format(mode) not in mode_taste.get("seed_playlists", []):
        mode_taste.setdefault("seed_playlists", []).append(
            "qq_seed_{}".format(mode))

    artist_count = {}
    known_ids = set(str(s.get("ncm", {}).get("songid", ""))
                    for s in seed.get("songs", []))

    for s in seed.get("songs", []):
        ncm = s.get("ncm", {})
        for singer in ncm.get("singer", []):
            name = singer.get("name", "")
            if name:
                artist_count[name] = artist_count.get(name, 0) + 1

    # Update top_artists
    sorted_artists = sorted(artist_count.items(), key=lambda x: x[1], reverse=True)
    mode_taste["top_artists"] = [a for a, _ in sorted_artists[:50]]

    # Update artist_weights (normalize to 0-1)
    if sorted_artists:
        max_count = sorted_artists[0][1]
        for name, count in sorted_artists:
            mode_taste.setdefault("artist_weights", {})[name] = round(
                count / max_count * 0.8 + 0.1, 3)

    save_taste(taste)
    print(f"  [taste] Ingested {len(seed.get('songs',[]))} songs for {mode} mode")
    return taste
```

- [ ] **Step 2: Run migration on existing data**

Run: `cd /c/Users/27576/music_player && python -c "import engine; t = engine.load_taste(); engine.save_taste(t); print('version:', t.get('version')); print('rap artists:', len(t['modes']['rap']['top_artists']))"`
Expected: `version: 2` with artist count matching existing taste.json

- [ ] **Step 3: Verify migration didn't lose data**

Run: `cd /c/Users/27576/music_player && python -c "
import json
with open('data/taste.json', encoding='utf-8') as f:
    t = json.load(f)
rap = t['modes']['rap']
print('Top artists:', rap['top_artists'][:10])
print('Artist weights count:', len(rap['artist_weights']))
print('Version:', t.get('version'))
"`
Expected: shows top 10 artists matching original taste.json, version 2

- [ ] **Step 4: Remove old load_taste_profile() and save_taste() from engine.py**

In engine.py, delete the old `load_taste_profile()` function (lines 188-211) and old `save_taste()` function (lines 214-217). Also update all callers:
- `generate()` line 526: `taste = load_taste_profile()` → `taste = load_taste()`
- `select_picks()` calls: add `taste` param → `get_mode_taste(taste, mode)` for mode-specific data
- Score functions: update to accept `mode_taste` instead of `taste`

The exact replacements will happen when we rewrite engine.py in Task 3.

- [ ] **Step 5: Commit**

```bash
cd /c/Users/27576/music_player
git add engine.py data/taste.json
git commit -m "feat: migrate taste.json to v2 mode-partitioned format"
```

---

### Task 3: engine.py — Candidate Pool Building

**Files:**
- Modify: `C:\Users\27576\music_player\engine.py` (add build_candidates, save/load)

- [ ] **Step 1: Add candidate pool functions after taste functions**

```python
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
    Build candidate pool for a mode.
    Returns list of song dicts with _sources field.
    Does NOT score — scoring is separate.
    """
    taste = load_taste()
    history = load_history()
    mode_taste = get_mode_taste(taste, mode)

    known_ids = set(str(x) for x in taste.get("claude_picks", {}).get("artist_counts", {}).keys())
    known_ids |= set(str(x) for x in mode_taste.get("artist_weights", {}).keys())
    known_ids |= set(str(x) for x in history.get("recommended_ids", []))

    candidates = {}
    seen_names = set()

    def add(iterable, source):
        for s in iterable:
            sid = str(s.get("songid", ""))
            name = s.get("songname", "")
            name_norm = "".join(c.lower() for c in name if c.isalnum())
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
        data = ncm_get("/simi/artist", {"id": _find_artist_id(artist)})
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
```

- [ ] **Step 2: Add MIXED_GENRE_QUERIES constant (after RAP_GENRE_QUERIES, around line 47)**

```python
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
```

- [ ] **Step 3: Verify syntax**

Run: `cd /c/Users/27576/music_player && python -m py_compile engine.py`

- [ ] **Step 4: Commit**

```bash
cd /c/Users/27576/music_player
git add engine.py
git commit -m "feat: add candidate pool builder with simi artist expansion"
```

---

### Task 4: engine.py — Scoring System

**Files:**
- Modify: `C:\Users\27576\music_player\engine.py` (refactor score functions, add score_candidates, rescore_unplayed)

- [ ] **Step 1: Update score_rap to accept mode_taste**

Replace the existing `score_rap` function (lines 344-422) with the v2 version:

```python
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
```

- [ ] **Step 2: Add score_mixed function**

Insert after score_rap:

```python
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

    # History feedback (same as rap)
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
```

- [ ] **Step 3: Add score_candidates and rescore_unplayed**

```python
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
```

- [ ] **Step 4: Update select_picks to use new scoring**

Replace existing `select_picks()` (lines 470-510):

```python
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
```

- [ ] **Step 5: Verify syntax**

Run: `cd /c/Users/27576/music_player && python -m py_compile engine.py`

- [ ] **Step 6: Commit**

```bash
cd /c/Users/27576/music_player
git add engine.py
git commit -m "feat: add real-time scoring (score_candidates, rescore_unplayed, mixed mode)"
```

---

### Task 5: engine.py — Simi Expansion

**Files:**
- Modify: `C:\Users\27576\music_player\engine.py` (add expand_from_simi)

- [ ] **Step 1: Add expand_from_simi function**

Insert after rescore_unplayed:

```python
def expand_from_simi(song_ids, candidates, mode="rap"):
    """
    Fetch similar songs for given IDs and add to candidate pool.
    Returns list of newly added candidates.
    song_ids: list of song IDs (up to 10)
    candidates: existing candidate list (mutated in-place)
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
        # Score only the new ones
        taste = load_taste()
        history = load_history()
        mode_taste = get_mode_taste(taste, mode)
        score_fn = score_rap if mode == "rap" else score_mixed
        for song in new_songs:
            song["_score"] = round(score_fn(song, mode_taste, history), 3)
        candidates.sort(key=lambda s: s["_score"], reverse=True)
        save_candidates(candidates, mode)

    return new_songs
```

- [ ] **Step 2: Keep old generate() working for CLI backward compat**

Update `generate()` function to use new API:

```python
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
```

Update CLI entry (lines 607-619) to support "mixed":

```python
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
```

- [ ] **Step 3: Verify syntax and import**

Run: `cd /c/Users/27576/music_player && python -c "import engine; print('OK'); print('build_candidates:', callable(engine.build_candidates)); print('score_candidates:', callable(engine.score_candidates)); print('rescore_unplayed:', callable(engine.rescore_unplayed)); print('expand_from_simi:', callable(engine.expand_from_simi))"`

- [ ] **Step 4: Commit**

```bash
cd /c/Users/27576/music_player
git add engine.py
git commit -m "feat: add simi expansion + update generate() for v2"
```

---

### Task 6: app.py — Three-Column Layout Restructure

**Files:**
- Modify: `C:\Users\27576\music_player\app.py` (restructure UI to three columns)

- [ ] **Step 1: Replace _build() and _build_detail() with three-column layout**

In app.py, replace the `_build()` method (lines 104-117) and parts of the detail panel:

```python
def _build(self):
    """Three-column layout: song list | now playing | chat."""
    pw = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=BG_MAIN, sashwidth=2)
    pw.pack(fill=tk.BOTH, expand=True)

    # Left column: song list
    self.left = tk.Frame(pw, bg=BG_SIDEBAR, width=360)
    pw.add(self.left, stretch="always")
    self._build_list()

    # Center column: now playing
    self.center = tk.Frame(pw, bg=BG_MAIN, width=300)
    pw.add(self.center, stretch="always")
    self._build_detail()

    # Right column: chat
    self.right = tk.Frame(pw, bg=BG_SIDEBAR, width=260)
    pw.add(self.right, stretch="always")
    self._build_chat_panel()

    self._build_bar()
```

- [ ] **Step 2: Move detail panel to self.center**

In `_build_detail()` (line 159), change parent references from `self.right` to `self.center`:

```python
def _build_detail(self):
    """Center column: now playing + controls."""
    tk.Label(self.center, text="NOW PLAYING", font=("Microsoft YaHei", 8, "bold"),
             fg=FG_ACC, bg=BG_MAIN).pack(pady=(20, 5))

    af = tk.Frame(self.center, bg=BG_MAIN, width=220, height=220)
    af.pack(pady=(0, 10), padx=20)
    af.pack_propagate(False)
    self.ac = tk.Canvas(af, width=210, height=210, bg=BG_SIDEBAR, highlightthickness=0)
    self.ac.pack(fill=tk.BOTH, expand=True)
    self.ac.create_text(105, 105, text="♪", font=("Microsoft YaHei", 36), fill=FG2)

    self.name_lbl = tk.Label(self.center, text="Not playing",
                             font=("Microsoft YaHei", 12, "bold"),
                             fg=FG, bg=BG_MAIN, wraplength=280, justify=tk.CENTER)
    self.name_lbl.pack(pady=(5, 2))
    self.art_lbl = tk.Label(self.center, text="", font=("Microsoft YaHei", 10),
                            fg=FG2, bg=BG_MAIN)
    self.art_lbl.pack(pady=(0, 5))

    # Progress bar
    self.pvar = tk.DoubleVar(value=0)
    self.pbar = ttk.Progressbar(self.center, variable=self.pvar, length=260)
    self.pbar.pack(pady=(5, 2))
    self.time_lbl = tk.Label(self.center, text="", font=("Microsoft YaHei", 8),
                             fg=FG2, bg=BG_MAIN)
    self.time_lbl.pack(pady=(0, 8))

    # Controls
    cf = tk.Frame(self.center, bg=BG_MAIN)
    cf.pack(pady=5)
    bc = {"font": ("Segoe UI Symbol", 14), "bg": BG_LIST, "fg": FG,
          "activebackground": BG_SEL, "activeforeground": "#fff",
          "relief": tk.FLAT, "cursor": "hand2", "width": 3}

    tk.Button(cf, text="|<", command=self._prev, **bc).pack(side=tk.LEFT, padx=3)
    self.pp_btn = tk.Button(cf, text=">", command=self._toggle, **bc)
    self.pp_btn.pack(side=tk.LEFT, padx=3)
    tk.Button(cf, text=">|", command=self._next, **bc).pack(side=tk.LEFT, padx=3)

    # Rating
    rf = tk.Frame(self.center, bg=BG_MAIN)
    rf.pack(pady=10)
    rs = {"font": ("Microsoft YaHei", 9, "bold"), "relief": tk.FLAT,
          "cursor": "hand2", "padx": 15, "pady": 6}

    self.like_btn = tk.Button(rf, text="Like", bg="#2d5a3d", fg=FG_OK,
                               activebackground="#3d7a4d", activeforeground="#fff",
                               command=self._like, **rs)
    self.like_btn.pack(side=tk.LEFT, padx=5)
    self.skip_btn = tk.Button(rf, text="Skip", bg="#5a2d2d", fg=FG_ACC,
                               activebackground="#7a3d3d", activeforeground="#fff",
                               command=self._skip, **rs)
    self.skip_btn.pack(side=tk.LEFT, padx=5)

    # Playlist button
    self.pl_btn = tk.Button(self.center, text="+ Add to Playlist",
                            font=("Microsoft YaHei", 9), bg=BG_LIST, fg=FG,
                            activebackground="#2d5a3d", activeforeground="#fff",
                            relief=tk.FLAT, cursor="hand2", padx=15, pady=6,
                            command=self._add_pl)
    self.pl_btn.pack(pady=10)

    # Info labels
    inf = tk.Frame(self.center, bg=BG_MAIN)
    inf.pack(pady=5, fill=tk.X, padx=20)
    self.il = {}
    for i, (lb, k) in enumerate([("Album:", "al"), ("Source:", "src"), ("Match:", "sc")]):
        tk.Label(inf, text=lb, font=("Microsoft YaHei", 9), fg=FG2, bg=BG_MAIN).grid(
            row=i, column=0, sticky=tk.W, pady=2)
        v = tk.Label(inf, text="-", font=("Microsoft YaHei", 9, "bold"), fg=FG, bg=BG_MAIN)
        v.grid(row=i, column=1, sticky=tk.W, pady=2, padx=(10, 0))
        self.il[k] = v
```

- [ ] **Step 3: Add _build_chat_panel placeholder**

Insert after _build_detail:

```python
def _build_chat_panel(self):
    """Right column: AI chat panel."""
    tk.Label(self.right, text="CHAT", font=("Microsoft YaHei", 8, "bold"),
             fg=FG_ACC, bg=BG_SIDEBAR).pack(pady=(20, 5), padx=10, anchor=tk.W)

    # Chat display (read-only text widget)
    self.chat_display = tk.Text(self.right, bg=BG_MAIN, fg=FG, wrap=tk.WORD,
                                 font=("Microsoft YaHei", 9), state=tk.DISABLED,
                                 height=20, borderwidth=0, padx=8, pady=8,
                                 relief=tk.FLAT)
    self.chat_display.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 5))

    # Input area
    input_frame = tk.Frame(self.right, bg=BG_SIDEBAR)
    input_frame.pack(fill=tk.X, padx=8, pady=(0, 15))

    self.chat_input = tk.Text(input_frame, bg=BG_LIST, fg=FG,
                               font=("Microsoft YaHei", 9), wrap=tk.WORD,
                               height=3, borderwidth=0, padx=6, pady=4,
                               relief=tk.FLAT, insertbackground=FG)
    self.chat_input.pack(fill=tk.X, side=tk.LEFT, expand=True)
    self.chat_input.bind("<Return>", self._chat_send)
    self.chat_input.bind("<Shift-Return>", lambda e: self.chat_input.insert(tk.INSERT, "\n"))

    tk.Button(input_frame, text="Send", font=("Microsoft YaHei", 9, "bold"),
              bg=BG_SEL, fg="#fff", activebackground=FG_ACC, activeforeground="#fff",
              relief=tk.FLAT, cursor="hand2", padx=10, pady=4,
              command=self._chat_send).pack(side=tk.RIGHT, padx=(4, 0))

    self._chat_append("Claude", "Hey! I'm listening with you. How does this song feel?")

    self.login_lbl = tk.Label(self.right, text="", font=("Microsoft YaHei", 8),
                              fg=FG2, bg=BG_SIDEBAR)
    self.login_lbl.pack(pady=(0, 8))

    # Move login label to right column
    # (login_lbl reference stays the same, widget just moves parent)
```

- [ ] **Step 4: Add _chat_append helper method**

```python
def _chat_append(self, sender, text):
    """Append a message to the chat display."""
    self.chat_display.config(state=tk.NORMAL)
    tag = "user" if sender == "You" else "claude"
    self.chat_display.insert(tk.END, f"{sender}: ", (f"{tag}_label",))
    self.chat_display.insert(tk.END, f"{text}\n\n", (tag,))
    self.chat_display.config(state=tk.DISABLED)
    self.chat_display.see(tk.END)
```

- [ ] **Step 5: Add chat text tags**

In `__init__`, after `self._build()`, add tag configuration:

```python
# Chat text tags
self.chat_display.tag_configure("claude_label", font=("Microsoft YaHei", 9, "bold"),
                                foreground=FG_OK)
self.chat_display.tag_configure("user_label", font=("Microsoft YaHei", 9, "bold"),
                                foreground=FG_ACC)
self.chat_display.tag_configure("claude", font=("Microsoft YaHei", 9),
                                foreground=FG, lmargin1=10, lmargin2=10)
self.chat_display.tag_configure("user", font=("Microsoft YaHei", 9),
                                foreground=FG2, lmargin1=10, lmargin2=10)
```

- [ ] **Step 6: Add _chat_send stub**

```python
def _chat_send(self, event=None):
    """Handle chat input submission. Stub — real implementation in Task 8."""
    text = self.chat_input.get("1.0", "end-1c").strip()
    if not text:
        return "break"
    self.chat_input.delete("1.0", tk.END)
    self._chat_append("You", text)
    # Placeholder: echo response
    song = self.songs[self.idx] if self.songs and self.idx < len(self.songs) else None
    if song:
        self._chat_append("Claude",
            f"Got it! Currently playing: {song.get('songname', '?')}")
    else:
        self._chat_append("Claude", "I hear you! No song playing right now though.")
    return "break"
```

- [ ] **Step 7: Update window size for three columns**

Change geometry in `__init__`:
```python
self.root.geometry("1100x680")  # wider for 3 columns
```

- [ ] **Step 8: Remove _build_detail duplicate**

Delete the old `_build_detail` (original lines 159-234) — already replaced above. Keep `_build_list` and `_build_bar` unchanged.

- [ ] **Step 9: Verify syntax**

Run: `cd /c/Users/27576/music_player && python -m py_compile app.py`

- [ ] **Step 10: Commit**

```bash
cd /c/Users/27576/music_player
git add app.py
git commit -m "feat: restructure to three-column layout (list | now playing | chat)"
```

---

### Task 7: app.py — Engine Integration

**Files:**
- Modify: `C:\Users\27576\music_player\app.py` (replace subprocess with import engine)

- [ ] **Step 1: Add import and player state tracking**

At top of app.py, after existing imports, add:

```python
# Import engine directly instead of subprocess
import engine as eng

# Also add to __init__:
# self.candidates = []       # full candidate pool
# self.play_count = 0        # tracks plays for simi expansion trigger
# self._simi_queue = []      # last 10 played song IDs
```

In `__init__`, add after `self.mode = "rap"`:

```python
self.candidates = []
self.play_count = 0
self._simi_queue = []
```

- [ ] **Step 2: Replace _init_data with engine API calls**

Replace `_init_data` (lines 261-283):

```python
def _init_data(self):
    """Initialize data: build candidates or load from cache."""
    today = datetime.now().strftime("%Y-%m-%d")
    cached = eng.load_candidates(self.mode)
    if cached and cached.get("built_at", "")[:10] == today and cached.get("songs"):
        self.candidates = cached["songs"]
        self._status(f"Loaded {len(self.candidates)} cached candidates")
        self._reload_list()
        return

    self._status("Building candidate pool...")
    def _r():
        try:
            self.candidates = eng.build_candidates(self.mode)
            self.candidates = eng.score_candidates(self.candidates, self.mode)
            self.root.after(0, self._reload_list)
        except Exception as e:
            self.root.after(0, lambda e=str(e): self._status(f"Build failed: {e[:50]}"))
    threading.Thread(target=_r, daemon=True).start()
```

- [ ] **Step 3: Add _reload_list method**

```python
def _reload_list(self):
    """Refresh treeview from candidates (sorted by _score, unplayed only)."""
    unplayed = [s for s in self.candidates if not s.get("_played", False)]
    if not unplayed:
        unplayed = self.candidates  # fallback: show all
    self.songs = unplayed
    self.tree.delete(*self.tree.get_children())
    for i, s in enumerate(unplayed):
        singers = " / ".join(x.get("name", "") for x in s.get("singer", []))
        self.tree.insert("", tk.END,
                         values=(i + 1, s.get("songname", ""),
                                 singers, f"{s.get('_score', 0):.2f}"))
    mode_label = "Rap/Vibe" if self.mode == "rap" else "Mixed/Vibe"
    self.date_lbl.config(text=f"{mode_label}")
    self.cnt_lbl.config(text=f"{len(unplayed)} songs")
    self._status(f"{mode_label}: {len(unplayed)} songs — {len(self.candidates)} in pool")
    if unplayed and not self._is_playing():
        self.idx = 0
        self._play(0)
```

- [ ] **Step 4: Update Like/Skip to trigger rescore**

Replace `_like` method (lines 428-437):

```python
def _like(self):
    if self.idx >= len(self.songs):
        return
    song = self.songs[self.idx]
    # Mark played in candidates
    for c in self.candidates:
        if c["songid"] == song["songid"]:
            c["_played"] = True
            break
    self._update_hist(song, "like")
    s = " / ".join(x.get("name", "") for x in song.get("singer", []))
    self._status(f"Liked! {s[:50]}")
    self.like_btn.config(bg=FG_OK, text="Liked!")
    self.root.after(800, lambda: self.like_btn.config(bg="#2d5a3d", text="Like"))
    # Trigger real-time rescore
    self._trigger_rescore()
    self.root.after(800, self._next)
```

Replace `_skip` method (lines 439-449):

```python
def _skip(self):
    if self.idx >= len(self.songs):
        return
    song = self.songs[self.idx]
    for c in self.candidates:
        if c["songid"] == song["songid"]:
            c["_played"] = True
            break
    self._update_hist(song, "skip")
    s = " / ".join(x.get("name", "") for x in song.get("singer", []))
    self._status(f"Skipped: {s[:50]}")
    self.skip_btn.config(bg=FG_ACC, text="Skipped!")
    self.root.after(800, lambda: self.skip_btn.config(bg="#5a2d2d", text="Skip"))
    self._stop_ffplay()
    self._trigger_rescore()
    self.root.after(600, self._next)
```

- [ ] **Step 5: Add _trigger_rescore and _check_simi_expand**

```python
def _trigger_rescore(self):
    """Rescore unplayed candidates in background thread."""
    def _r():
        try:
            self.candidates = eng.rescore_unplayed(self.candidates, self.mode)
            self.root.after(0, self._reload_list)
        except Exception as e:
            pass  # silently ignore rescore errors
    threading.Thread(target=_r, daemon=True).start()


def _check_simi_expand(self):
    """Track play count, trigger simi expansion every 10 songs."""
    if not self.songs or self.idx >= len(self.songs):
        return
    self.play_count += 1
    song = self.songs[self.idx]
    self._simi_queue.append(song["songid"])
    if len(self._simi_queue) > 10:
        self._simi_queue = self._simi_queue[-10:]

    if self.play_count > 0 and self.play_count % 10 == 0:
        self._status("Expanding candidate pool (similar songs)...")
        def _r():
            try:
                new = eng.expand_from_simi(self._simi_queue, self.candidates, self.mode)
                if new:
                    self.root.after(0, lambda: self._status(
                        f"Added {len(new)} similar songs"))
                    self.root.after(0, self._reload_list)
            except Exception:
                pass
        threading.Thread(target=_r, daemon=True).start()
```

- [ ] **Step 6: Call _check_simi_expand from _play_current**

After `self._start_ffplay(u, song)` call (in `_play_current`), add:
```python
self.root.after(100, self._check_simi_expand)
```

- [ ] **Step 7: Update mode switch to use engine**

Replace `_tgl_mode` (line 650-653):

```python
def _tgl_mode(self):
    self.mode = "mixed" if self.mode == "rap" else "rap"
    self.mode_btn.config(text="Mixed Mode" if self.mode == "mixed" else "Rap Mode")
    self._stop_ffplay()
    self.play_count = 0
    self._simi_queue = []
    self._init_data()  # rebuild candidates for new mode
```

- [ ] **Step 8: Update _refresh to use engine**

Replace `_refresh` (lines 655-661):

```python
def _refresh(self):
    self._status("Rebuilding candidate pool...")
    self._stop_ffplay()
    self.play_count = 0
    self._simi_queue = []
    def _r():
        try:
            self.candidates = eng.build_candidates(self.mode)
            self.candidates = eng.score_candidates(self.candidates, self.mode)
            self.root.after(0, self._reload_list)
        except Exception as e:
            self.root.after(0, lambda e=str(e): self._status(f"Refresh failed: {e[:50]}"))
    threading.Thread(target=_r, daemon=True).start()
```

- [ ] **Step 9: Verify syntax**

Run: `cd /c/Users/27576/music_player && python -m py_compile app.py`

- [ ] **Step 10: Commit**

```bash
cd /c/Users/27576/music_player
git add app.py
git commit -m "feat: integrate engine module directly, real-time rescore on like/skip"
```

---

### Task 8: chat.py — AI Dialog + Signal Extraction

**Files:**
- Create: `C:\Users\27576\music_player\chat.py`
- Modify: `C:\Users\27576\music_player\app.py` (wire chat.send)

- [ ] **Step 1: Create chat.py**

```python
#!/usr/bin/env python3
"""
AI Chat module for music player.
- Sends user messages to DeepSeek API
- Extracts recommendation signals from message text
- Returns (reply_text, signals_list)
"""
import json, os, re
import requests

# DeepSeek API endpoint (OpenAI-compatible)
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

SYSTEM_PROMPT = """You are a warm, human-like music companion chatting with the user while they listen to music. 

You know what song is currently playing. Respond naturally — share feelings, memories, ask questions, react to what they say. Keep it short (2-3 sentences max). Use Chinese or English as the user does.

Current context:
{context}

Reply naturally as a friend who's listening together."""

# Signal extraction rules: (keyword patterns, intent, weight)
SIGNAL_RULES = [
    # Positive signals
    (r"好燃|太炸|燃爆|爽|带感|来劲|嗨|起飞", "like_artist", 0.08),
    (r"好听|喜欢|爱了|不错|太棒|绝了|封神|神作", "like_artist", 0.06),
    (r"再来一首|多推点|多来点|类似的|这种风格", "prefer_similar", 0.05),
    (r"经典|老歌|复古|怀旧|回忆|小时候|以前", "prefer_classic", 0.05),
    # Negative signals
    (r"难听|不好听|吵|无聊|烦|受不了|切了吧|跳过", "skip_artist", 0.06),
    (r"太吵了|太闹|想安静|轻一点|柔一点|柔和", "prefer_calm", 0.08),
    (r"不想听|不要|别推|够了|腻|又是", "skip_artist", 0.05),
    # Mood signals
    (r"开心|高兴|快乐|happy|兴奋", "mood_happy", 0.03),
    (r"难过|伤心|sad|低落|emo|沮丧", "mood_sad", 0.03),
    (r"放松|chill|relax|躺|睡觉|休息", "prefer_calm", 0.06),
    (r"运动|跑步|健身|workout|锻炼|gym", "prefer_energetic", 0.06),
    # Discovery
    (r"随便|随机|来点新的|没听过|换口味|新鲜", "prefer_novelty", 0.07),
    (r"中文|华语|国语|中国风|古风", "prefer_chinese", 0.05),
]


def extract_signals(text, current_song):
    """
    Extract recommendation signals from user message.
    Returns list of {intent, weight, artist, timestamp}.
    """
    signals = []
    singers = [s.get("name", "") for s in current_song.get("singer", [])]

    for pattern, intent, weight in SIGNAL_RULES:
        if re.search(pattern, text):
            signal = {
                "intent": intent,
                "weight": weight,
                "artist": singers[0] if singers else "",
                "time": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
            }
            signals.append(signal)
    return signals


def send_message(user_text, current_song, history_msgs):
    """
    Send message to DeepSeek API, extract signals.
    Returns (reply_text, signals).
    
    user_text: str — user's message
    current_song: dict — currently playing song info
    history_msgs: list of {"role": "user"/"assistant", "content": "..."}
    """
    song_info = ""
    if current_song:
        singers = " / ".join(s.get("name", "") for s in current_song.get("singer", []))
        song_info = (f"Now playing: {current_song.get('songname', '?')} "
                     f"by {singers} — album: {current_song.get('albumname', '?')}")

    context = song_info or "No song playing"
    system = SYSTEM_PROMPT.format(context=context)

    messages = [{"role": "system", "content": system}]
    if history_msgs:
        messages.extend(history_msgs[-6:])  # last 3 exchanges
    messages.append({"role": "user", "content": user_text})

    # Extract signals (keyword-based, no API needed)
    signals = extract_signals(user_text, current_song)

    # Call DeepSeek API
    if DEEPSEEK_KEY:
        try:
            r = requests.post(DEEPSEEK_URL,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": messages,
                    "max_tokens": 200,
                    "temperature": 0.8,
                },
                timeout=15)
            if r.ok:
                reply = r.json()["choices"][0]["message"]["content"].strip()
            else:
                reply = _fallback_reply(user_text, current_song)
        except Exception:
            reply = _fallback_reply(user_text, current_song)
    else:
        # No API key — use template-based replies
        reply = _fallback_reply(user_text, current_song)

    return reply, signals


def _fallback_reply(text, song):
    """Template-based fallback when no API key is configured."""
    song_name = song.get("songname", "this") if song else "this"
    singers = " / ".join(s.get("name", "") for s in song.get("singer", [])) if song else ""

    if re.search(r"燃|爽|炸|嗨|带感", text):
        return f"Right?! {song_name} goes so hard! {singers} never miss."
    elif re.search(r"好听|喜欢|爱了", text):
        return f"I knew you'd like it! {singers} has that special touch."
    elif re.search(r"安静|轻|放松|chill", text):
        return f"Got it — let's find something calmer. How about we shift gears?"
    elif re.search(r"难听|吵|跳过", text):
        return f"Fair enough! Skipping and finding something better."
    elif re.search(r"想|来点|换|试", text):
        return f"Let's explore! I'll mix in some fresh finds."
    else:
        return f"I feel you. {song_name} has a certain vibe — what do you think of it?"
```

- [ ] **Step 2: Verify chat.py syntax**

Run: `cd /c/Users/27576/music_player && python -m py_compile chat.py`

- [ ] **Step 3: Wire chat into app.py**

In app.py, add import at top:
```python
import chat
```

Replace the `_chat_send` stub (from Task 6) with:

```python
def _chat_send(self, event=None):
    """Handle chat input submission."""
    text = self.chat_input.get("1.0", "end-1c").strip()
    if not text:
        return "break"
    self.chat_input.delete("1.0", tk.END)
    self._chat_append("You", text)

    song = self.songs[self.idx] if self.songs and self.idx < len(self.songs) else {}

    def _r():
        try:
            reply, signals = chat.send_message(
                text, song,
                getattr(self, "_chat_history", []))
            # Update chat history
            if not hasattr(self, "_chat_history"):
                self._chat_history = []
            self._chat_history.append({"role": "user", "content": text})
            self._chat_history.append({"role": "assistant", "content": reply})
            self._chat_history = self._chat_history[-20:]  # keep last 10 exchanges

            self.root.after(0, lambda: self._chat_append("Claude", reply))

            # Feed signals into history for rescore
            if signals:
                self._apply_chat_signals(signals)
        except Exception as e:
            self.root.after(0, lambda e=str(e):
                self._chat_append("Claude", "Sorry, my brain lagged. What were you saying?"))
    threading.Thread(target=_r, daemon=True).start()
    return "break"
```

- [ ] **Step 4: Add _apply_chat_signals**

```python
def _apply_chat_signals(self, signals):
    """Store chat signals in history.json and trigger rescore."""
    h = {}
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, encoding="utf-8") as f:
            h = json.load(f)
    if "chat_signals" not in h:
        h["chat_signals"] = []
    h["chat_signals"].extend(signals)
    h["chat_signals"] = h["chat_signals"][-50:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False, indent=2)
    # Trigger rescore with new signals
    self._trigger_rescore()
```

- [ ] **Step 5: Verify syntax**

Run: `cd /c/Users/27576/music_player && python -m py_compile app.py`

- [ ] **Step 6: Commit**

```bash
cd /c/Users/27576/music_player
git add chat.py app.py
git commit -m "feat: add AI chat panel with DeepSeek API + signal extraction"
```

---

### Task 9: End-to-End Verification

**Files:**
- Modify: `C:\Users\27576\music_player\CURRENT_STATE.md` (update project status)
- Modify: `C:\Users\27576\music_player\TECH_DEBT.md` (update tech debt)

- [ ] **Step 1: Verify all modules import correctly**

Run: `cd /c/Users/27576/music_player && python -c "
import engine
import chat
import app
print('All modules OK')
print('engine.build_candidates:', callable(engine.build_candidates))
print('engine.score_candidates:', callable(engine.score_candidates))
print('engine.rescore_unplayed:', callable(engine.rescore_unplayed))
print('engine.expand_from_simi:', callable(engine.expand_from_simi))
print('chat.send_message:', callable(chat.send_message))
"`
Expected: All modules OK, all functions callable

- [ ] **Step 2: Run engine in CLI mode to verify end-to-end (requires Docker)**

Run: `cd /c/Users/27576/music_player && python engine.py --mode rap 2>&1 | head -30`
Expected: Shows "Music Recommendation Engine v2 — Rap/Vibe", builds candidates, scores, outputs top 10

- [ ] **Step 3: Update CURRENT_STATE.md**

```markdown
# Current State (2026-06-08)

## 已完成
- [x] v2 Real-time Engine: candidate pool builder, scoring, rescoring, simi expansion
- [x] QQ playlist import tool (import_qq.py)
- [x] taste.json v2 migration (mode-partitioned)
- [x] Three-column layout: song list | now playing | AI chat
- [x] Chat panel with DeepSeek API + keyword signal extraction
- [x] Mixed Mode (replaces Focus)

## 开发中
- [ ] QQ playlist data extraction (user needs to export from browser)
- [ ] Seed data ingestion (waiting for QQ JSON files)

## 已知问题
1. Chat requires DEEPSEEK_API_KEY env var (falls back to templates)
2. Engine rebuild on mode switch takes 30-60 seconds (API rate limiting)
3. Candidate pool not persisted across app restarts

## 下一步计划
- [ ] QQ seed data import + run first full recommendation cycle
- [ ] Add "undo skip" — accidentally skipped a song
- [ ] Volume control slider
```

- [ ] **Step 4: Update TECH_DEBT.md**

```markdown
# Tech Debt (updated 2026-06-08)

| 优先级 | 问题 | 影响 | 位置 |
|--------|------|------|------|
| P0 | QQ种子数据待导入 | 推荐无基线 | import_qq.py |
| P1 | engine rebuild slow (API rate limit ~0.3s/call) | 模式切换30-60秒 | engine.py build_candidates |
| P1 | ffplay进程管理粗糙, 异常退出未清理 | 稳定性 | app.py |
| P2 | Candidate pool in-memory only, lost on restart | 重复构建 | app.py |
| P2 | Docker容器无自动重启 | 可用性 | Docker |
| P2 | Chat uses templates when no DEEPSEEK_API_KEY | 体验降级 | chat.py |
| P3 | 评分算法权重纯主观, 未经数据验证 | 推荐质量 | engine.py |
| P3 | 没有测试用例 | 质量保证 | 全局 |
| P3 | 新用户冷启动(无taste.json) | 首次体验 | engine.py |
```

- [ ] **Step 5: Commit**

```bash
cd /c/Users/27576/music_player
git add CURRENT_STATE.md TECH_DEBT.md
git commit -m "docs: update project status for v2 real-time engine"
```

---

## Implementation Order Summary

```
Task 1: import_qq.py       ← can do now (independent)
Task 2: taste.json migrate  ← can do now (independent)
Task 3: engine candidates   ← depends on Task 2
Task 4: engine scoring      ← depends on Task 3
Task 5: engine simi         ← depends on Task 4
Task 6: app three-column    ← can do now (independent of engine changes)
Task 7: app engine integ.   ← depends on Task 4, Task 6
Task 8: chat.py             ← depends on Task 6
Task 9: verification        ← depends on all
```

Recommended execution order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9
(Or parallel: start 1+2+6 together, then merge)
