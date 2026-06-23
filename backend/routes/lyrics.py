#!/usr/bin/env python3
"""
Claude Music — Lyrics & Stream Routes
Lyrics fetching, audio streaming proxy.
"""

import logging
import re

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, StreamingResponse

import requests as http_requests

from backend.state import get_state
from backend.helpers import _resolve_song_url

log = logging.getLogger("claude-music")

router = APIRouter()
state = get_state()


@router.get("/api/lyrics/{song_id}")
async def get_lyrics(song_id: int):
    from api.ncm_client import ncm

    with state.read() as st:
        if song_id in st["lyrics_cache"]:
            return {"lyrics": st["lyrics_cache"][song_id]}
    try:
        data = ncm("/lyric", {"id": song_id})
        lrc_text = ""
        if data and "lrc" in data and data["lrc"].get("lyric"):
            lrc_text = data["lrc"]["lyric"]
        lines = []
        for line in lrc_text.split("\n"):
            m = re.match(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)", line)
            if m:
                ms = int(m.group(1)) * 60000 + int(float(m.group(2)) * 1000)
                text = m.group(3).strip()
                if text:
                    lines.append({"time": ms, "text": text})
        lines.sort(key=lambda x: x["time"])
        with state.read() as st:
            st["lyrics_cache"][song_id] = lines
            st["_current_lyrics"] = lines
        return {"lyrics": lines}
    except Exception as e:
        log.warning("Lyrics for song %d: %s", song_id, e)
        return {"lyrics": []}


@router.get("/api/stream/{song_id}")
async def stream_audio(song_id: int):
    """Proxy audio stream — NetEase URLs require Referer header."""
    url = _resolve_song_url(song_id)
    if not url:
        return HTMLResponse(status_code=404)

    def generate():
        try:
            resp = http_requests.get(
                url,
                headers={
                    "Referer": "https://music.163.com/",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                },
                stream=True,
                timeout=30,
            )
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    yield chunk
        except Exception as e:
            log.warning("Stream error for %d: %s", song_id, e)

    return StreamingResponse(generate(), media_type="audio/mpeg")
