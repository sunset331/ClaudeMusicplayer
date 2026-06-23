#!/usr/bin/env python3
"""
Claude Music — System Tray Service
Runs a pystray icon with play/pause, next, prev, and exit controls.
"""

import logging
import os

log = logging.getLogger("claude-music")

HOME = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(HOME, "data")


def run_tray():
    try:
        from PIL import Image, ImageDraw
        import pystray
        import requests as _req
    except ImportError:
        log.warning("pystray or PIL not installed, tray disabled")
        return

    icon_path = os.path.join(DATA_DIR, "icon.ico")
    if os.path.exists(icon_path):
        image = Image.open(icon_path)
    else:
        image = Image.new("RGB", (64, 64), "#1a1030")
        d = ImageDraw.Draw(image)
        d.ellipse([16, 16, 48, 48], fill="#C084FC")

    def on_show(icon, item):
        import webbrowser

        webbrowser.open("http://localhost:8765")

    def on_playpause(icon, item):
        try:
            _req.post("http://localhost:8765/api/toggle", timeout=2)
        except Exception:
            pass

    def on_next(icon, item):
        try:
            _req.post("http://localhost:8765/api/next", timeout=2)
        except Exception:
            pass

    def on_prev(icon, item):
        try:
            _req.post("http://localhost:8765/api/prev", timeout=2)
        except Exception:
            pass

    def on_exit(icon, item):
        icon.stop()
        import os as _os

        _os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("显示 Claude Music", on_show, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("播放/暂停", on_playpause),
        pystray.MenuItem("下一首", on_next),
        pystray.MenuItem("上一首", on_prev),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", on_exit),
    )
    icon = pystray.Icon("claude_music", image, "Claude Music", menu)
    icon.run()
