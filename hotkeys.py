#!/usr/bin/env python3
"""
Global hotkey listener for Claude Music Player.

Uses pynput to listen for media keys and custom hotkeys globally,
dispatching UI actions to the main tkinter thread via root.after().

Supported keys:
  - Media keys: Play/Pause, Next Track, Previous Track
  - Ctrl+Alt+Right → next, Ctrl+Alt+Left → prev, Ctrl+Alt+Space → toggle
  - Ctrl+Alt+L → like, Ctrl+Alt+S → skip
  - Ctrl+Alt+Up → vol+, Ctrl+Alt+Down → vol-, Ctrl+Alt+M → mute
  - Ctrl+Alt+T → toggle mini player
  - Ctrl+Alt+D → toggle desktop lyrics
"""
import threading

from pynput.keyboard import GlobalHotKeys


class GlobalHotkeyListener:
    """Global hotkey listener using pynput. Registers each hotkey individually
    so one unrecognized key name doesn't disable all others."""

    def __init__(self, app):
        self._app = app
        self._listeners = []  # multiple listeners, one per hotkey

    def start(self):
        def _run():
            # Each hotkey gets its own GlobalHotKeys + try/except so one
            # failure (e.g. <media_play_pause> on an unsupported platform)
            # doesn't disable all the others.
            bindings = [
                # Media keys (may fail on some platforms)
                ("<media_play_pause>", self._app._toggle),
                ("<media_next>", self._app._next),
                ("<media_previous>", self._app._prev),
                # Ctrl+Alt combos (standard — reliable everywhere pynput works)
                ("<ctrl>+<alt>+<right>", self._app._next),
                ("<ctrl>+<alt>+<left>", self._app._prev),
                ("<ctrl>+<alt>+<space>", self._app._toggle),
                ("<ctrl>+<alt>+l", self._app._like),
                ("<ctrl>+<alt>+s", self._app._skip),
                ("<ctrl>+<alt>+<up>", self._vol_up),
                ("<ctrl>+<alt>+<down>", self._vol_down),
                ("<ctrl>+<alt>+m", self._mute_toggle),
            ]
            for key_combo, callback in bindings:
                try:
                    l = GlobalHotKeys({key_combo: lambda cb=callback: self._ui(cb)})
                    l.start()
                    self._listeners.append(l)
                except Exception:
                    pass  # this specific hotkey is unsupported, skip it

        t = threading.Thread(target=_run, daemon=True)
        t.start()

    def _ui(self, fn):
        try:
            self._app.root.after(0, fn)
        except Exception:
            pass

    def _vol_up(self):
        vol = int((getattr(self._app, '_volume', 1.0) + 0.05) * 100)
        self._app.root.after(0, lambda: self._app._set_volume(min(150, vol)))

    def _vol_down(self):
        vol = int((getattr(self._app, '_volume', 1.0) - 0.05) * 100)
        self._app.root.after(0, lambda: self._app._set_volume(max(0, vol)))

    def _mute_toggle(self):
        self._app.root.after(0, self._app._toggle_mute)

    def stop(self):
        for l in self._listeners:
            try:
                l.stop()
            except Exception:
                pass
