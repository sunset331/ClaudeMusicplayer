#!/usr/bin/env python3
"""
Batch import QQ playlists from text files.
Reads "Song Name - Artist1 / Artist2" format, searches NetEase, creates seed data.
Usage: python import_txt.py  (requires ncm-api Docker running)
"""
import json, os, re, sys, time
import requests

# Work around Windows GBK encoding
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

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


def parse_txt(path):
    """Parse 'Song - Artist1 / Artist2' lines into [{name, artist, artists}]."""
    songs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Split on " - " (first occurrence)
            parts = line.split(" - ", 1)
            if len(parts) != 2:
                print(f"  [SKIP] Can't parse: {line[:50]}")
                continue
            name = parts[0].strip()
            artist_str = parts[1].strip()
            # Split artists on " / " or " feat. " patterns
            artists = re.split(r"\s*/\s*|\s+feat\.\s+", artist_str)
            artists = [a.strip() for a in artists if a.strip()]
            if not name or not artists:
                print(f"  [SKIP] Empty name/artist: {line[:50]}")
                continue
            songs.append({
                "name": name,
                "artist": artists[0],
                "artists": artists,
                "album": "",
            })
    return songs


def search_ncm(song):
    """Search NetEase for a song, return best match or None."""
    query = f"{song['name']} {song['artist']}"
    data = ncm_get("/search", {"keywords": query, "limit": 5, "type": 1})
    if not data or data.get("code") != 200:
        return None
    results = data.get("result", {}).get("songs", [])
    if not results:
        return None

    target_name = song["name"].lower().strip()
    # Remove parenthetical content for looser matching
    target_name_clean = re.sub(r"\(.*?\)", "", target_name).strip()
    target_artist = song["artist"].lower().strip()

    best = None
    for r in results:
        r_name = r.get("name", "").lower().strip()
        r_name_clean = re.sub(r"\(.*?\)", "", r_name).strip()
        r_artists = [a.get("name", "").lower().strip()
                     for a in r.get("artists", [])]
        score = 0
        # Exact match
        if r_name == target_name or r_name_clean == target_name_clean:
            score += 5
        elif target_name_clean and (target_name_clean in r_name_clean or r_name_clean in target_name_clean):
            score += 3
        # Artist match
        if target_artist in r_artists or any(target_artist in a for a in r_artists):
            score += 4
        elif any(a in target_artist or target_artist in a for a in r_artists):
            score += 2
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


def import_txt(txt_path, label):
    """Main import: txt -> NetEase search -> qq_seed_{label}.json."""
    print(f"\n[Import] Parsing {txt_path}...")
    songs = parse_txt(txt_path)
    print(f"  Parsed {len(songs)} songs")

    # Check API
    if not ncm_get("/login/status"):
        print("  [FATAL] NetEase API not reachable. Start Docker: docker start ncm-api")
        sys.exit(1)

    matched = []
    unmatched = []
    for i, song in enumerate(songs):
        name_short = song["name"][:30]
        artist_short = song["artist"][:20]
        print(f"  [{i+1}/{len(songs)}] {name_short} | {artist_short}", end=" ")
        match = search_ncm(song)
        if match:
            print(f"-> {match['songname'][:30]}")
            matched.append({**song, "ncm": match})
        else:
            print("-> NO MATCH")
            unmatched.append({"name": song["name"], "artist": song["artist"]})
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
        print(f"  {len(unmatched)} unmatched -> {um_path}")

    print(f"  Done! {len(matched)}/{len(songs)} matched -> {os.path.basename(out_path)}")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python import_txt.py [rap|mixed|both]")
        print("  Reads data/qq_raw_{mode}.txt, outputs data/qq_seed_{mode}.json")
        print("  Requires: docker start ncm-api (NetEase API on localhost:3000)")
        sys.exit(1)

    mode = sys.argv[1].lower()
    if mode in ("rap", "both"):
        rap_txt = os.path.join(DATA_DIR, "qq_raw_rap.txt")
        if os.path.exists(rap_txt):
            result = import_txt(rap_txt, "rap")
            # Also ingest into taste.json
            import engine
            taste = engine.load_taste()
            engine.ingest_qq_seed(taste, "rap")
        else:
            print(f"Not found: {rap_txt}")

    if mode in ("mixed", "both"):
        mixed_txt = os.path.join(DATA_DIR, "qq_raw_mixed.txt")
        if os.path.exists(mixed_txt):
            result = import_txt(mixed_txt, "mixed")
            import engine
            taste = engine.load_taste()
            engine.ingest_qq_seed(taste, "mixed")
        else:
            print(f"Not found: {mixed_txt}")
