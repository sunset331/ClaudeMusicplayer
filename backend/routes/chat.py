#!/usr/bin/env python3
"""
Claude Music — Chat Route
AI companion chat with context-aware responses.
"""

import logging

from fastapi import APIRouter

from backend.state import get_state
from backend.helpers import _load_chat_context, _handle_chat_signals, _song_to_dict

log = logging.getLogger("claude-music")

router = APIRouter()
state = get_state()


@router.post("/api/chat/message")
async def chat_message(body: dict):
    """Send a message to AI companion with real context."""
    import chat as chat_mod

    text = body.get("text", "")
    if not text.strip():
        return {"reply": "", "signals": []}
    try:
        history, taste, song_stats, song = _load_chat_context(state)
        reply, signals = chat_mod.send_message(
            text, song, [], history, taste, song_stats,
        )
        should_skip = "[切歌]" in (reply or "")
        reply_clean = reply.replace("[切歌]", "").strip() if reply else ""

        # Handle song requests from chat signals
        inserted = _handle_chat_signals(signals, text, state)

        # Detect mood radio triggers
        mood = None
        try:
            import smart_dj

            mood = smart_dj.detect_mood(text)
        except Exception:
            pass

        return {
            "reply": reply_clean,
            "signals": signals,
            "shouldSkip": should_skip,
            "inserted": inserted,
            "mood": mood,
        }
    except Exception as e:
        log.warning("Chat error: %s", e)
        return {"reply": "沧溟正在休息，请稍后再试...", "signals": []}
