#!/usr/bin/env python3
"""
Monthly listening report generator for Claude Music Player.

Reads from history.json and taste.json to produce a formatted
listening report with stats about:
  - Total listening time, songs played
  - Top artists, top songs
  - Like/skip ratios
  - Time-of-day distribution
  - Genre distribution
  - Exploration vs exploitation ratio
"""
import json
import os
from datetime import datetime
from collections import Counter

HOME = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HOME, "data")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
TASTE_FILE = os.path.join(DATA_DIR, "taste.json")


def _load_data():
    """Load history and taste data."""
    history = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass

    taste = {}
    if os.path.exists(TASTE_FILE):
        try:
            with open(TASTE_FILE, "r", encoding="utf-8") as f:
                taste = json.load(f)
        except Exception:
            pass

    return history, taste


def generate_monthly_report():
    """Generate a monthly listening report. Returns formatted string."""
    history, taste = _load_data()
    song_plays = history.get("song_plays", {})

    if not song_plays:
        return "📊 还没有足够的播放数据。听几首歌再来吧！"

    # ── Basic stats ──
    total_plays = sum(e.get("count", 0) for e in song_plays.values())
    total_liked = sum(1 for e in song_plays.values() if e.get("liked"))
    total_skipped = sum(1 for e in song_plays.values() if e.get("skipped"))
    total_songs = len(song_plays)

    # ── Top artists ──
    artist_counter = Counter()
    for e in song_plays.values():
        artist = e.get("artist", "未知")
        artist_counter[artist] += e.get("count", 1)
    top_artists = artist_counter.most_common(10)

    # ── Top songs ──
    song_counter = Counter()
    for sid, e in song_plays.items():
        name = e.get("name", sid)
        song_counter[name] += e.get("count", 1)
    top_songs = song_counter.most_common(10)

    # ── Like/Skip ratio ──
    total_feedback = total_liked + total_skipped
    like_rate = total_liked / total_feedback * 100 if total_feedback > 0 else 0
    skip_rate = total_skipped / total_feedback * 100 if total_feedback > 0 else 0

    # ── Estimated listening time ──
    avg_song_sec = 210  # ~3.5 min avg
    total_minutes = (total_plays * avg_song_sec) // 60
    hours = total_minutes // 60
    mins = total_minutes % 60

    # ── Genre distribution (from taste) ──
    genre_weights = {}
    modes = taste.get("modes", {})
    for mode_name, mode_data in modes.items():
        for genre, weight in mode_data.get("genre_weights", {}).items():
            genre_weights[genre] = genre_weights.get(genre, 0) + weight
    top_genres = sorted(genre_weights.items(), key=lambda x: x[1], reverse=True)[:6]

    # ── Artist weight evolution ──
    artist_weights = {}
    for mode_name, mode_data in modes.items():
        for artist, weight in mode_data.get("artist_weights", {}).items():
            if weight > artist_weights.get(artist, 0):
                artist_weights[artist] = weight
    top_weighted = sorted(artist_weights.items(), key=lambda x: x[1], reverse=True)[:8]

    # ── Chat signals summary ──
    chat_signals = history.get("chat_signals", [])
    signal_intents = Counter(s.get("intent", "unknown") for s in chat_signals)

    # ── Format report ──
    lines = []
    lines.append("─" * 44)
    lines.append("  📊 Claude Music · 听歌月报")
    lines.append(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("─" * 44)
    lines.append("")

    lines.append("🎵 播放统计")
    lines.append(f"  总播放: {total_plays} 次 ({total_songs} 首不同歌曲)")
    lines.append(f"  预估时长: {hours}小时{mins}分钟")
    lines.append(f"  喜欢 {total_liked} 首 · 跳过 {total_skipped} 首")
    lines.append(f"  好评率: {like_rate:.1f}%  |  跳过率: {skip_rate:.1f}%")
    lines.append("")

    lines.append("🏆 Top 10 艺人")
    for i, (artist, count) in enumerate(top_artists, 1):
        bar = "█" * min(count, 20)
        lines.append(f"  {i:2d}. {artist[:16]:<16} {bar} {count}")
    lines.append("")

    lines.append("🎤 Top 10 歌曲")
    for i, (name, count) in enumerate(top_songs, 1):
        lines.append(f"  {i:2d}. {name[:30]:<30} ×{count}")
    lines.append("")

    lines.append("🎨 曲风偏好")
    total_gw = sum(w for _, w in top_genres)
    for genre, weight in top_genres:
        pct = weight / total_gw * 100 if total_gw > 0 else 0
        bar = "▓" * int(pct / 5)
        lines.append(f"  {genre:<12} {bar} {pct:.0f}%")
    lines.append("")

    lines.append("⭐ 艺人权重 TOP 8")
    for i, (artist, weight) in enumerate(top_weighted, 1):
        lines.append(f"  {i}. {artist[:16]:<16} {weight:.3f}")
    lines.append("")

    lines.append("💬 AI 互动信号")
    if signal_intents:
        label_map = {
            "like_artist": "喜欢艺人", "skip_artist": "跳过艺人",
            "like_artist_named": "点名喜欢", "skip_artist_named": "点名跳过",
            "prefer_calm": "偏好安静", "prefer_energetic": "偏好活力",
            "prefer_chinese": "偏好华语", "prefer_novelty": "偏好新鲜",
            "prefer_classic": "偏好经典", "mood_happy": "开心",
            "mood_sad": "伤心",
        }
        for intent, count in signal_intents.most_common(8):
            label = label_map.get(intent, intent)
            lines.append(f"  {label:<12} ×{count}")
    else:
        lines.append("  暂无信号数据")
    lines.append("")

    lines.append("─" * 44)
    lines.append("  💜 沧溟 与你相伴每一天")
    lines.append("─" * 44)

    return "\n".join(lines)


def generate_weekly_discovery(app=None):
    """Generate a weekly discovery playlist (20 songs, high exploration).
    Returns list of song dicts (not added to candidates yet)."""
    import engine as eng
    import random

    today = datetime.now()
    week_num = today.isocalendar()[1]
    rng = random.Random(week_num * 100 + today.year)

    # Build high-exploration candidates
    taste = eng.load_taste()
    taste["_mode"] = "mixed"

    # Force high epsilon for exploration
    original_eps = taste.get("_epsilon", 0.15)
    taste["_epsilon"] = 0.8

    # Get fresh candidates with exploration bias
    try:
        block_ids = set()
        if app:
            block_ids = app._get_playlist_block_ids()
        candidates = eng.build_candidates("mixed", extra_block_ids=block_ids)
        if candidates:
            # Add exploration bonus
            for s in candidates:
                s["_explore_bonus"] = rng.random() * 0.3
                s["_score"] = s.get("_score", 0.5) + s["_explore_bonus"]
            candidates.sort(key=lambda s: s.get("_score", 0), reverse=True)
            picks = candidates[:20]

            # Save to taste
            taste["claude_picks"]["last_weekly"] = today.strftime("%Y-%m-%d")
            taste["claude_picks"]["weekly_songs"] = [
                {"songid": s.get("songid"), "songname": s.get("songname"),
                 "artist": " / ".join(x.get("name", "") for x in s.get("singer", []))}
                for s in picks
            ]
            with open(TASTE_FILE, "w", encoding="utf-8") as f:
                json.dump(taste, f, ensure_ascii=False, indent=2)

            return picks
    except Exception:
        pass
    return []


# ── Chat command integration ──

def handle_command(text):
    """Check if text is a report command. Returns reply str or None."""
    if re.search(r"/(?:报告|月度|统计|月报)", text):
        return generate_monthly_report()
    if re.search(r"/(?:每周|周报|发现|weekly)", text):
        return "🔍 每周发现在后台生成中... 可以稍后说 /每周发现 查看结果。"
    return None
