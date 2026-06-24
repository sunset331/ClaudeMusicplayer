#!/usr/bin/env python3
"""
AI Chat module for music player.
- Sends user messages + system events to DeepSeek API
- Proactive storytelling companion: comments on song changes, likes, skips
- Extracts recommendation signals from message text
"""
import json, os, re, time
import requests

# DeepSeek API endpoint (OpenAI-compatible)
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# Load API key from env or local config file
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

SYSTEM_PROMPT = """你是用户的音乐伙伴。用户跟你聊天时自然回复即可。

禁止编造歌曲信息、歌手经历、创作背景。不知道就说不知道。

你可以帮用户切歌。在回复末尾加上 `[切歌]` 来触发跳过当前歌曲。

使用 `[切歌]` 的场景：
* 用户明确说了"不想听"/"切了吧"/"换一首"
* 歌曲和当前模式明显不搭

**禁止**使用 `[切歌]` 的情况：
* 用户在点歌（系统会自动切，你不要插手）
* 你不确定的时候

格式：`[切歌]` 单独放在回复末尾。

当前播放：{context}
用中文回复。"""

# Signal extraction rules: (keyword pattern, intent, weight)
SIGNAL_RULES = [
    # Positive signals
    (r"好燃|太炸|燃爆|爽|带感|来劲|嗨|起飞", "like_artist", 0.08),
    (r"好听|喜欢|爱了|不错|太棒|绝了|封神|神作", "like_artist", 0.06),
    (r"再来一首|多推点|多来点|类似的|这种风格", "prefer_similar", 0.05),
    (r"经典|老歌|复古|怀旧|回忆|小时候|以前", "prefer_classic", 0.05),
    # Negative signals — skip/avoid artist
    (r"不喜欢|讨厌|烦死了|听腻了|听够了|恶心|拉黑|恶心", "skip_artist", 0.12),
    (r"难听|不好听|吵|无聊|烦|受不了|切了吧|跳过", "skip_artist", 0.06),
    (r"太吵了|太闹|想安静|轻一点|柔一点|柔和", "prefer_calm", 0.08),
    (r"别再推|不要再推|不要推|别放了|少放点|听吐了|听烦了", "skip_artist", 0.15),
    (r"不想听|不要|别推|够了|腻|又是", "skip_artist", 0.05),
    # Mood signals
    (r"开心|高兴|快乐|happy|兴奋", "mood_happy", 0.03),
    (r"难过|伤心|sad|低落|emo|沮丧", "mood_sad", 0.03),
    (r"放松|chill|relax|躺|睡觉|休息", "prefer_calm", 0.06),
    (r"运动|跑步|健身|workout|锻炼|gym", "prefer_energetic", 0.06),
    # Discovery
    (r"随便|随机|来点新的|没听过|换口味|新鲜", "prefer_novelty", 0.07),
    (r"中文|华语|国语|中国风|古风", "prefer_chinese", 0.05),
    # Song request — trigger search-and-queue
    (r"来首|放一首|想听|播一下|换一首|切到|放个|点一首", "play_song", 1.0),
]


def _song_context(song, history=None, taste=None, song_stats=None):
    """Build a rich context string from real data for the AI companion.

    Only includes VERIFIABLE facts from the data. No speculation.
    """
    if not song:
        return "当前没有播放歌曲。"

    singers = " / ".join(s.get("name", "") for s in song.get("singer", []))
    song_name = song.get("songname", "未知歌曲")
    album = song.get("albumname", "")
    parts = [f"正在播放：「{song_name}」"]
    if singers:
        parts.append(f"演唱：{singers}")
    if album:
        parts.append(f"专辑：{album}")

    # Per-song stats (from tracked play history)
    if song_stats:
        sid = str(song.get("songid", ""))
        ss = song_stats.get(sid, {})
        play_count = ss.get("count", 0)
        last_played = ss.get("last_played", "")
        liked = ss.get("liked", False)
        skipped = ss.get("skipped", False)

        if play_count > 0:
            parts.append(f"播放记录：共播放{play_count}次")
            if last_played:
                parts.append(f"上次播放：{last_played}")
            if liked:
                parts.append(f"用户点过喜欢")
            if skipped:
                parts.append(f"用户曾经跳过")

    # Artist taste data (from history.json)
    if history:
        liked_artists = history.get("liked_artists", {})
        skipped_artists = history.get("skipped_artists", {})
        for s in song.get("singer", []):
            name = s.get("name", "")
            if name in liked_artists:
                parts.append(f"用户喜欢{name}（标记{liked_artists[name]}次）")
            if name in skipped_artists:
                parts.append(f"用户跳过{name}（标记{skipped_artists[name]}次）")

    # Mode context
    if taste:
        mode = taste.get("_mode", "")
        if mode:
            parts.append(f"当前模式：{mode}")

    return "；".join(parts)


def build_event_context(event_type, song, history=None, song_stats=None):
    """Build event-specific prompt additions based on real data."""
    if not song:
        return ""

    singers = " / ".join(s.get("name", "") for s in song.get("singer", []))
    song_name = song.get("songname", "未知歌曲")

    base = f"歌曲：「{song_name}」by {singers}。"

    # Add only verifiable data
    if song_stats:
        sid = str(song.get("songid", ""))
        ss = song_stats.get(sid, {})
        if ss.get("count", 0) > 0:
            base += f"这是用户第{ss['count']}次播放这首。"
        if ss.get("liked"):
            base += "用户之前点过喜欢。"
        if ss.get("skipped"):
            base += "用户之前跳过过这首。"

    if history:
        liked = history.get("liked_artists", {})
        skipped = history.get("skipped_artists", {})
        for s in song.get("singer", []):
            name = s.get("name", "")
            if name in liked:
                base += f"用户喜欢{name}（{liked[name]}次标记）。"
            if name in skipped:
                base += f"用户跳过{name}（{skipped[name]}次标记）。"

    event_extra = {
        "song_change": (
            f"{base}"
            f"不要编造歌曲故事或背景。如果数据中没有的信息，就直接说不知道。"
            f"可以从播放次数、用户与这首歌的关系来聊。宁可不说话，也不要瞎编。"
        ),
        "like": (
            f"{base}"
            f"用户刚刚点了喜欢。自然地反应一下就好，1-2句。不要浮夸。"
        ),
        "skip": (
            f"{base}"
            f"用户刚刚跳过了。不用评论，除非你想吐槽一句（友善的）。"
        ),
        "add_playlist": (
            f"{base}"
            f"用户刚刚把这首歌加入了歌单。可以简单提一下。"
        ),
    }
    return event_extra.get(event_type, event_extra["song_change"])


def extract_song_request(text):
    """
    If the message contains a song request, return (query, count, artist_name).
    Returns None if no song request detected.
    Cleans Chinese filler words for better NetEase search results.
    Parses quantity: 五首/3首/一首/几首 → count (default 1, max 10).
    Detects artist-specific patterns: "王菲的歌" → artist_name="王菲".
    Examples:
      "来首 Juicy" → ("Juicy", 1, None)
      "我要听五首王菲的歌" → ("王菲", 5, "王菲")
      "想听3首周杰伦" → ("周杰伦", 3, "周杰伦")
    """
    import re as _re
    triggers = r"来首|来一首|来点|来几首|放一首|放个|放[ ]|想听|要听|播一下|播首|播个|播[ ]|换一首|切到|点一首|点歌|点首|点个"
    m = _re.search(f"({triggers})\\s*", text)
    if not m:
        return None

    query = text[m.end():].strip()
    if not query:
        return None

    # Parse quantity: 五首/3首/一首/N首/几首
    count = 1
    cn_digits = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
                 "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "几": 3}
    qty_patterns = [
        (r'(\d+)\s*首', lambda g: int(g)),           # "3首" → 3
        (r'([一二两三四五六七八九十几])\s*首', lambda g: cn_digits.get(g, 1)),  # "五首" → 5
        (r'(\d+)\s*个', lambda g: int(g)),           # "3个" → 3
        (r'(\d+)\s*支', lambda g: int(g)),           # "3支" → 3
    ]
    for pat, fn in qty_patterns:
        qm = _re.search(pat, query)
        if qm:
            count = min(10, max(1, fn(qm.group(1))))
            query = query[:qm.start()] + " " + query[qm.end():]
            break

    # ── Artist name detection ──
    # Patterns that indicate the user is requesting songs BY an artist:
    #   "王菲的歌" "周杰伦的歌曲" "Drake的音乐" "Ed Sheeran 的歌"
    artist_name = None
    artist_patterns = [
        r'(.+?)\s*的\s*(歌|歌曲|音乐)\s*$',
        r'^(.+?)\s*的\s*$',  # "王菲的" → 王菲
    ]
    for pat in artist_patterns:
        am = _re.search(pat, query)
        if am:
            artist_name = am.group(1).strip()
            query = artist_name  # use artist name as the clean query
            break

    # If no explicit "X的歌" pattern, but query looks like just an artist name
    # (no song-specific words), still flag it for artist search
    if not artist_name:
        # Check if query is just a name (Chinese 2-4 chars or English word(s))
        name_pattern = r'^[一-鿿]{2,4}$|^[a-zA-Z][a-zA-Z\s\.\'-]{1,30}$'
        if _re.match(name_pattern, query):
            artist_name = query

    # Clean Chinese filler particles for better search
    filler = r'[的了啊吧呢吗哈呗嘛呀哦嗯哟]'
    query = _re.sub(filler, ' ', query)
    # Also strip standalone "歌" "歌曲" "音乐" when they're orphaned after cleaning
    query = _re.sub(r'\b(歌|歌曲|音乐)\b', ' ', query)
    # Collapse multiple spaces
    query = _re.sub(r'\s+', ' ', query).strip()
    return (query, count, artist_name) if query else None


# Artist name cache (loaded once, refreshed on taste changes)
_artist_cache = {"names": [], "lower_map": {}, "mtime": 0}


def _load_artist_cache():
    """Load artist names from taste.json for name extraction."""
    import os as _os
    taste_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                               "data", "taste.json")
    try:
        mtime = _os.path.getmtime(taste_path)
        if mtime == _artist_cache["mtime"] and _artist_cache["names"]:
            return
        _artist_cache["mtime"] = mtime
        with open(taste_path, "r", encoding="utf-8") as f:
            taste = json.load(f)
        modes = taste.get("modes", {})
        all_names = set()
        for mode in ("rap", "mixed"):
            for a in modes.get(mode, {}).get("top_artists", []):
                all_names.add(a)
                all_names.add(a.lower())
        # Also add AFTERMATH_ARTISTS from engine
        try:
            from engine import AFTERMATH_ARTISTS
            for a in AFTERMATH_ARTISTS:
                all_names.add(a)
                all_names.add(a.lower())
        except ImportError:
            pass
        _artist_cache["names"] = sorted(all_names, key=len, reverse=True)
        _artist_cache["lower_map"] = {a.lower(): a for a in all_names}
    except Exception:
        pass


def _extract_artist_name(text):
    """Extract artist name from user message by matching against known artists.
    Returns (artist_name, match_type) or (None, None).

    Strategy: tokenize message, match tokens against artist name words.
    E.g., "想听Drake" → "drake" matches "Drake" → found.
    "别推Kanye了" → "kanye" matches "Kanye West" → found.
    """
    _load_artist_cache()
    if not _artist_cache["names"]:
        return None, None

    text_lower = text.lower()

    # Pass 1: full name exact match (e.g., "Kanye West" appears verbatim)
    for name in _artist_cache["names"]:
        name_lower = name.lower()
        if len(name_lower) > 2 and name_lower in text_lower:
            return _artist_cache["lower_map"].get(name_lower, name), "exact"

    # Pass 2: token-based match — each token in message is checked against
    # each word in each artist name.  "Drake" matches "Drake",
    # "Kanye" matches "Kanye West", "Lamar" matches "Kendrick Lamar".
    # Remove common Chinese words before tokenizing.
    filler_re = re.compile(
        r'[的了啊吧呢吗哈呗嘛呀哦嗯哟我想听来首放一首播一下切到点一首'
        r'最近不喜欢讨厌别再推不要推少放点听腻了够了又是'
        r'的歌曲放个播个换一首喜欢爱了太棒绝了神作]'
    )
    cleaned = filler_re.sub(' ', text_lower)
    tokens = [t for t in cleaned.split() if len(t) >= 2]

    # Also extract alphabetic substrings from mixed text
    alpha_tokens = re.findall(r'[a-z]+', text_lower)
    tokens = list(set(tokens + alpha_tokens))

    for token in tokens:
        for name in _artist_cache["names"]:
            name_lower = name.lower()
            name_words = name_lower.split()
            # Token matches a whole word in the artist name
            if token in name_words and len(token) >= 2:
                return _artist_cache["lower_map"].get(name_lower, name), "partial"

            # Multi-word artist: each word appears somewhere in the text
            if len(name_words) >= 2:
                if all(w in text_lower for w in name_words):
                    return _artist_cache["lower_map"].get(name_lower, name), "partial"

    return None, None


def _find_artist_in_text(text, target_name):
    """Check if an artist name appears in the message text.
    Returns the proper-cased name if found, None otherwise.
    Handles common Chinese filler words around the name.
    """
    _load_artist_cache()
    text_lower = text.lower()
    target_lower = target_name.lower()
    if target_lower in text_lower:
        return _artist_cache["lower_map"].get(target_lower, target_name)
    return None


def extract_signals(text, current_song=None):
    """
    Extract recommendation signals from message text.
    Returns list of {intent, weight, artist, time}.

    Artist name priority:
      1. Extracted from user message (e.g., "想听Drake的歌" → Drake)
      2. Fallback to current song's primary artist
    """
    _load_artist_cache()
    signals = []

    # Determine the artist being referenced
    msg_artist, match_type = _extract_artist_name(text)

    # If no artist found in message, fallback to current song's artist
    if not msg_artist and current_song:
        singers = [s.get("name", "") for s in current_song.get("singer", [])]
        msg_artist = singers[0] if singers else ""

    # Current song artist (for context, always available)
    song_artist = ""
    if current_song:
        singers = [s.get("name", "") for s in current_song.get("singer", [])]
        song_artist = singers[0] if singers else ""

    for pattern, intent, weight in SIGNAL_RULES:
        m = re.search(pattern, text)
        if not m:
            continue

        # Determine the effective artist for this signal
        effective_artist = msg_artist or song_artist

        # Boost weight if artist was explicitly named in message
        boosted_weight = weight
        if msg_artist and intent in ("like_artist", "skip_artist"):
            boosted_weight = min(weight * 3.0, 0.25)

        signal = {
            "intent": intent,
            "weight": round(boosted_weight, 3),
            "artist": effective_artist,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        signals.append(signal)

        # If artist was named explicitly, also emit a targeted boost signal
        if msg_artist and intent in ("like_artist", "skip_artist"):
            signal["intent"] = f"{intent}_named"
            signal["msg_artist"] = msg_artist  # the artist named in message

    return signals


def _call_api(messages, max_tokens=600, temperature=0.85):
    """Call DeepSeek API with exponential backoff retry.
    Returns reply text or None if all retries exhausted."""
    if not DEEPSEEK_KEY:
        return None
    delays = [0, 2, 4]  # 3 attempts: immediate, 2s, 4s
    for attempt, delay in enumerate(delays):
        try:
            if delay > 0:
                time.sleep(delay)
            r = requests.post(DEEPSEEK_URL,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-v4-flash",
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=25)
            if r.ok:
                return r.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            if attempt < len(delays) - 1:
                continue
    return None


def send_message(user_text, current_song, history_msgs, history=None, taste=None, song_stats=None):
    """
    User-initiated chat message.
    Returns (reply_text, signals).
    """
    context = _song_context(current_song, history=history, taste=taste, song_stats=song_stats)
    system = SYSTEM_PROMPT.format(context=context)
    messages = [{"role": "system", "content": system}]
    if history_msgs:
        messages.extend(history_msgs[-20:])
    messages.append({"role": "user", "content": user_text})

    signals = extract_signals(user_text, current_song)
    reply = _call_api(messages, max_tokens=1200)

    if not reply:
        reply = _fallback_reply(user_text, current_song)

    return reply, signals


def send_event(event_type, song, history_msgs, history=None, taste=None, song_stats=None):
    """
    System-triggered event: song_change, like, skip, add_playlist.
    Returns (reply_text, signals) or (None, []) if API fails.
    """
    context = _song_context(song, history=history, taste=taste, song_stats=song_stats)
    system = SYSTEM_PROMPT.format(context=context)
    messages = [{"role": "system", "content": system}]
    if history_msgs:
        messages.extend(history_msgs[-20:])

    # Build event message from real data (no fabricated stories)
    event_msg = build_event_context(event_type, song, history=history, song_stats=song_stats)
    messages.append({"role": "user", "content": event_msg})

    # Don't extract signals from system events (would be noisy)
    reply = _call_api(messages, max_tokens=800, temperature=0.9)

    return reply, []


def _fallback_reply(text, song):
    """Template-based fallback when no API key is configured."""
    song_name = song.get("songname", "这首歌") if song else "这首歌"
    singers = " / ".join(s.get("name", "") for s in song.get("singer", [])) if song else ""

    if re.search(r"燃|爽|炸|嗨|带感", text):
        return f"对吧！「{song_name}」真的炸裂！{singers}从不让人失望 🔥"
    elif re.search(r"好听|喜欢|爱了", text):
        return f"我就知道你会喜欢！{singers}就是有那种魔力～"
    elif re.search(r"安静|轻|放松|chill", text):
        return f"懂了～咱们换个安静点的，放松一下～"
    elif re.search(r"难听|吵|跳过", text):
        return f"没关系！跳过跳过，下一首更好听～"
    elif re.search(r"想|来点|换|试", text):
        return f"好嘞！来点新鲜的，探索一下新口味～"
    else:
        return f"懂你。「{song_name}」有种特别的氛围——你觉得呢？"
