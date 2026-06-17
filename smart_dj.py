#!/usr/bin/env python3
"""
Smart DJ + Mood Radio for Claude Music Player.

Smart DJ: AI-driven real-time playlist curation. Every 5 songs, the AI
evaluates the session context and decides what to play next — not just
scoring numbers, but vibe, arc, and emotional trajectory.

Mood Radio: Chat-triggered thematic radio stations. User says "我失恋了"
→ AI creates a healing station. Lasts 10 songs or 30 minutes, then
naturally transitions back to normal mode.
"""
import json
import os
import time
import re
from datetime import datetime

HOME = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HOME, "data")

# ── Mood detection ───────────────────────────────────────────────

MOOD_PATTERNS = {
    "healing": {
        "triggers": [
            r"失恋|分手|难过|伤心|哭了|emo|崩了|心碎|受伤|疗伤|治愈",
            r"不开心|低落|sad|沮丧|没劲|颓",
        ],
        "label": "💔 疗愈电台",
        "genre_boost": {"pop": 0.3, "r&b": 0.2},
        "mood_tag": "calm",
        "energy": "low",
        "description": "一切都会好起来的。让我陪你慢慢愈合。",
    },
    "celebration": {
        "triggers": [
            r"开心|快乐|高兴|爽|庆祝|嗨|起飞|太棒|happy|兴奋",
            r"炸了|起飞了|绝了|封神",
        ],
        "label": "🎉 庆祝模式",
        "genre_boost": {"hip-hop": 0.3, "rock": 0.2},
        "mood_tag": "energetic",
        "energy": "high",
        "description": "就是这种感觉！High起来！",
    },
    "focus": {
        "triggers": [
            r"学习|写作业|工作|加班|赶due|ddl|专注|focus|集中|认真",
            r"看书|读书|码代码|coding|写代码|编程",
        ],
        "label": "📚 专注模式",
        "genre_boost": {"ambient": 0.3, "electronic": 0.2},
        "mood_tag": "focus",
        "energy": "medium",
        "description": "专注时间到。纯音乐陪你码代码。",
    },
    "sleep": {
        "triggers": [
            r"睡觉|睡|困|累|躺|休息|放松|chill|relax|安眠|催眠",
            r"晚安|想睡|好累|太困",
        ],
        "label": "🌙 助眠模式",
        "genre_boost": {"ambient": 0.4, "classical": 0.2},
        "mood_tag": "calm",
        "energy": "low",
        "description": "闭上眼睛，放下一切。晚安 🌙",
    },
    "workout": {
        "triggers": [
            r"运动|跑步|健身|workout|gym|锻炼|练|游泳|打球|跳",
        ],
        "label": "💪 运动模式",
        "genre_boost": {"hip-hop": 0.3, "rock": 0.3},
        "mood_tag": "energetic",
        "energy": "high",
        "description": "燃起来！每一下都有节奏！",
    },
    "chinese": {
        "triggers": [
            r"中国风|古风|华语|中文|国风|民谣|怀旧|经典|老歌",
        ],
        "label": "🏮 华语经典",
        "genre_boost": {"chinese": 0.5, "pop": 0.2},
        "mood_tag": "classic",
        "energy": "medium",
        "description": "还是中文歌有味道。",
    },
}


def detect_mood(text):
    """Detect mood from user message. Returns mood profile or None."""
    for mood_key, mood_def in MOOD_PATTERNS.items():
        for pattern_group in mood_def["triggers"]:
            if isinstance(pattern_group, str):
                pattern_group = [pattern_group]
            for pattern in pattern_group:
                if re.search(pattern, text):
                    result = dict(mood_def)
                    result["mood_key"] = mood_key
                    result["activated_at"] = datetime.now().isoformat()
                    result["songs_remaining"] = 10
                    return result
    return None


# ── Smart DJ ─────────────────────────────────────────────────────

class SmartDJ:
    """AI DJ that curates the listening session in real-time."""

    def __init__(self, app):
        self._app = app
        self._active = False
        self._session_arc = []  # list of dicts: {time, song_name, artist, feedback}
        self._last_dj_time = 0
        self._interval = 5  # DJ interjects every N songs

    def record_play(self, song_name, artist):
        """Record a song play in the DJ's session arc."""
        self._session_arc.append({
            "time": datetime.now().strftime("%H:%M"),
            "song_name": song_name,
            "artist": artist,
            "feedback": None,
        })
        if len(self._session_arc) > 50:
            self._session_arc = self._session_arc[-50:]

    def record_feedback(self, action):
        """Record like/skip on the most recent song."""
        if self._session_arc:
            self._session_arc[-1]["feedback"] = action

    def should_interject(self):
        """Should the DJ speak now? (every N songs)."""
        return len(self._session_arc) > 0 and \
               len(self._session_arc) % self._interval == 0 and \
               time.time() - self._last_dj_time > 60

    def get_dj_context(self):
        """Build context string for DJ AI prompt."""
        recent = self._session_arc[-10:]
        lines = []
        for entry in recent:
            fb = entry.get("feedback", "")
            fb_str = f" [{fb}]" if fb else ""
            lines.append(f"  {entry['time']} {entry['song_name']} — {entry['artist']}{fb_str}")

        liked = sum(1 for e in recent if e.get("feedback") == "like")
        skipped = sum(1 for e in recent if e.get("feedback") == "skip")
        neutral = len(recent) - liked - skipped

        hour = datetime.now().hour
        if 5 <= hour < 8:
            time_vibe = "清晨"
        elif 8 <= hour < 12:
            time_vibe = "上午"
        elif 12 <= hour < 14:
            time_vibe = "午间"
        elif 14 <= hour < 18:
            time_vibe = "下午"
        elif 18 <= hour < 22:
            time_vibe = "晚上"
        else:
            time_vibe = "深夜"

        return {
            "recent_history": "\n".join(lines),
            "liked": liked,
            "skipped": skipped,
            "neutral": neutral,
            "time_vibe": time_vibe,
            "mode": self._app.mode if hasattr(self._app, 'mode') else "mixed",
            "total_played": len(self._session_arc),
        }

    def ask_dj(self):
        """Ask the AI DJ for a recommendation. Returns (message, action_dict)."""
        # Prevent concurrent DJ calls stacking up
        if getattr(self, '_inflight', False):
            return None, None
        self._inflight = True
        # Always update last DJ time to prevent thread accumulation on failure
        self._last_dj_time = time.time()

        try:
            ctx = self.get_dj_context()
            if not ctx["recent_history"]:
                return None, None

            prompt = f"""你是 Smart DJ，正在实时为用户策展音乐。

当前时间：{ctx['time_vibe']}
模式：{ctx['mode']}
本次已播：{ctx['total_played']} 首

最近 10 首：
{ctx['recent_history']}

用户反馈：喜欢 {ctx['liked']} / 跳过 {ctx['skipped']} / 中性 {ctx['neutral']}

请简短点评一下当前的听歌状态（1-2句话，中文），然后建议下一首的方向。
用自然的朋友语气，不要机械。

如果用户明显在某个情绪里（一直喜欢燃曲、一直跳过慢歌等），可以建议切换。
最后给出一个 JSON action（可选）：{{"suggest_genre":"xxx","suggest_mood":"xxx"}}"""

            import chat as _chat
            reply = _chat._call_api(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=1.2,
            )
            if reply:
                # Extract JSON action if present
                action = {}
                m = re.search(r'\{[^}]+\}', reply)
                if m:
                    try:
                        action = json.loads(m.group())
                    except Exception:
                        pass
                    reply = reply[:m.start()].strip()
                return reply, action
        except Exception:
            pass
        finally:
            self._inflight = False
        return None, None


# ── Mood Radio ───────────────────────────────────────────────────

class MoodRadio:
    """Chat-triggered mood-based radio station."""

    def __init__(self, app):
        self._app = app
        self._active = False
        self._mood_profile = None
        self._start_time = 0
        self._song_count = 0

    def activate(self, mood_profile):
        """Activate a mood radio station."""
        self._active = True
        self._mood_profile = mood_profile
        self._start_time = time.time()
        self._song_count = 0

    def deactivate(self):
        """End the mood radio session."""
        self._active = False
        self._mood_profile = None
        self._start_time = 0
        self._song_count = 0

    @property
    def active(self):
        return self._active

    @property
    def label(self):
        if self._mood_profile:
            return self._mood_profile.get("label", "📻 电台")
        return ""

    def status_text(self):
        """Get current status for UI display."""
        if not self._active or not self._mood_profile:
            return ""
        remaining = self._mood_profile.get("songs_remaining", 0)
        elapsed = int(time.time() - self._start_time) // 60
        return f"{self.label} · 剩余 {remaining} 首 · {elapsed}min"

    def on_song_played(self):
        """Called when a song finishes playing in mood radio mode."""
        if not self._active:
            return
        self._song_count += 1
        if self._mood_profile:
            self._mood_profile["songs_remaining"] = max(0,
                self._mood_profile.get("songs_remaining", 10) - 1)
            if self._mood_profile["songs_remaining"] <= 0:
                self.deactivate()
                return True  # signal that radio is over
        return False

    def adjust_candidate_scores(self, candidates):
        """Boost scores for songs matching the current mood."""
        if not self._active or not self._mood_profile:
            return candidates
        genre_boost = self._mood_profile.get("genre_boost", {})
        for song in candidates:
            boost = 0.0
            sources = song.get("_sources", []) or song.get("sources", [])
            tags = " ".join(sources).lower()
            for genre, weight in genre_boost.items():
                if genre in tags:
                    boost = max(boost, weight)
            if boost > 0:
                song["_score"] = song.get("_score", 0) + boost
                song["_mood_boost"] = boost
        return sorted(candidates, key=lambda s: s.get("_score", 0), reverse=True)
