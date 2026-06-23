#!/usr/bin/env python3
"""
Claude Music — Windows Taskbar Progress Service
Shows playback progress and pause state in the taskbar icon.
"""

import logging
import time

log = logging.getLogger("claude-music")


def run_taskbar(state):
    try:
        import pythoncom
        import win32gui
        import win32com.client
    except ImportError:
        return  # pywin32 not installed

    pythoncom.CoInitialize()
    try:
        taskbar = win32com.client.Dispatch("ITaskbarList3")
        taskbar.HrInit()
    except Exception:
        return

    def find_window():
        hwnd = None

        def callback(h, _):
            nonlocal hwnd
            if win32gui.IsWindowVisible(h) and "Claude Music" in win32gui.GetWindowText(h):
                hwnd = h
                return False
            return True

        win32gui.EnumWindows(callback, None)
        return hwnd

    while True:
        try:
            hwnd = find_window()
            if hwnd:
                with state.read() as st:
                    playing = st["playing"]
                    t = st.get("current_time", 0)
                if playing:
                    taskbar.SetProgressState(hwnd, 0x2)  # TBPF_NORMAL (green)
                    # Get duration from first song
                    song = state.current_song()
                    dur = (song.get("duration", 0) or 0) if song else 0
                    if dur > 0:
                        taskbar.SetProgressValue(hwnd, int(t * 1000), dur * 1000)
                else:
                    taskbar.SetProgressState(hwnd, 0x8)  # TBPF_PAUSED (yellow)
            time.sleep(0.5)
        except Exception:
            time.sleep(2)
