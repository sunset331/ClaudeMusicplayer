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
            artists = []
            singer_list = (s.get("singer") or s.get("ar") or s.get("artists") or [])
            for a in singer_list:
                an = a.get("name", "") if isinstance(a, dict) else str(a)
                if an:
                    artists.append(an)
            if not artists:
                continue
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
