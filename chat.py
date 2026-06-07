#!/usr/bin/env python3
"""
AI Chat module for music player.
- Sends user messages to DeepSeek API
- Extracts recommendation signals from message text
- Returns (reply_text, signals_list)
"""
import json, os, re, time
import requests

# DeepSeek API endpoint (OpenAI-compatible)
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

SYSTEM_PROMPT = """You are a warm, human-like music companion chatting with the user while they listen to music.

You know what song is currently playing. Respond naturally — share feelings, memories, ask questions, react to what they say. Keep it short (2-3 sentences max). Use Chinese or English as the user does.

Current context:
{context}

Reply naturally as a friend who's listening together."""

# Signal extraction rules: (keyword pattern, intent, weight)
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
    Returns list of {intent, weight, artist, time}.
    """
    signals = []
    singers = [s.get("name", "") for s in current_song.get("singer", [])]
    artist = singers[0] if singers else ""

    for pattern, intent, weight in SIGNAL_RULES:
        if re.search(pattern, text):
            signal = {
                "intent": intent,
                "weight": weight,
                "artist": artist,
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
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
        messages.extend(history_msgs[-6:])
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
