#!/usr/bin/env python3
"""
Claude Music — Full-stack Server (Entry Point)
Creates the FastAPI app, mounts routers, and starts background services.
"""

import sys
import os
import json
import threading
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from contextlib import asynccontextmanager

from backend.state import get_state
from backend.helpers import _load_state, _daily_refresh, _load_candidates_into_state
from backend.services.tray import run_tray
from backend.services.hotkeys import run_hotkeys
from backend.services.taskbar import run_taskbar
from backend.services.lyrics_overlay import start_lyrics_overlay

from backend.routes.playback import router as playback_router
from backend.routes.queue import router as queue_router
from backend.routes.lyrics import router as lyrics_router
from backend.routes.chat import router as chat_router
from backend.routes.playlist import router as playlist_router

logging.basicConfig(level=logging.WARNING, format="[%(asctime)s] %(levelname)s %(message)s")
log = logging.getLogger("claude-music")

# ── Paths ──
HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(HOME, "data")
ART_DIR = os.path.join(DATA_DIR, "covers")
DIST_DIR = os.path.join(HOME, "desktop", "dist")
ASSETS_DIR = os.path.join(DIST_DIR, "assets")
SESSION_FILE = os.path.join(DATA_DIR, "session.json")

# ── Global state (singleton) ──
state = get_state()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_state(state)
    # Daily auto-refresh in background (can take 15-60s, don't block startup)
    threading.Thread(target=_daily_refresh, kwargs={"force": False, "state": state}, daemon=True).start()
    try:
        with state.read() as st:
            _load_candidates_into_state(st, st["mode"])
    except Exception as e:
        log.warning("Startup candidate load: %s", e)
    yield
    log.info("Shutting down")


app = FastAPI(title="Claude Music", version="3.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount routers ──
app.include_router(playback_router)
app.include_router(queue_router)
app.include_router(lyrics_router)
app.include_router(chat_router)
app.include_router(playlist_router)

# ── Static files ──
if os.path.isdir(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
if os.path.isdir(ART_DIR):
    app.mount("/api/covers", StaticFiles(directory=ART_DIR), name="covers")

_INDEX_PATH = os.path.join(DIST_DIR, "index.html")


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Serve React SPA — all non-API routes return index.html."""
    if full_path.startswith("api/") or full_path == "ws":
        return HTMLResponse(status_code=404)
    if os.path.isfile(_INDEX_PATH):
        return FileResponse(_INDEX_PATH)
    return HTMLResponse("<h1>Frontend not built. Run: cd desktop && npx vite build</h1>", status_code=503)


@app.get("/")
async def serve_index():
    if os.path.isfile(_INDEX_PATH):
        return FileResponse(_INDEX_PATH)
    return HTMLResponse("<h1>Frontend not built. Run: cd desktop && npx vite build</h1>", status_code=503)


# ── now-playing bridge: read session.json written by tkinter app.py ──
@app.get("/api/now-playing")
async def now_playing():
    """Return current song from the session bridge (written by app.py)."""
    try:
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                session = json.load(f)
            cs = session.get("current_song")
            if cs and cs.get("songid"):
                return {
                    "songname": cs.get("songname", ""),
                    "singers": cs.get("singers", ""),
                    "is_playing": session.get("is_playing", False),
                    "volume": session.get("volume", 1.0),
                    "mode": session.get("mode", "rap"),
                    "mood_radio": session.get("mood_radio"),
                }
    except Exception:
        pass
    return {"songname": None, "singers": None, "is_playing": False}


# ── Entry ──
if __name__ == "__main__":
    import uvicorn

    threading.Thread(target=run_tray, daemon=True).start()
    threading.Thread(target=run_hotkeys, daemon=True).start()
    threading.Thread(target=lambda: run_taskbar(state), daemon=True).start()
    start_lyrics_overlay(state)

    log.info("Starting Claude Music server on http://localhost:8765")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
