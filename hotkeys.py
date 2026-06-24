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
import sys
import threading
import time

_PYNPUT_AVAILABLE = False
GlobalHotKeys = None

try:
    from pynput.keyboard import GlobalHotKeys
    _PYNPUT_AVAILABLE = True
except ImportError as e:
    print(f"[hotkeys] WARNING: pynput not installed, global hotkeys disabled: {e}",
          file=sys.stderr)


class GlobalHotkeyListener:
    """Global hotkey listener using pynput. Registers each hotkey individually
    so one unrecognized key name doesn't disable all others."""

    def __init__(self, app):
        self._app = app
        self._listeners = []  # multiple listeners, one per hotkey
        self._thread = None
        self._running = False

    def start(self):
        if not _PYNPUT_AVAILABLE:
            print("[hotkeys] Hotkey listener not started — pynput unavailable",
                  file=sys.stderr)
            return

        def _run():
            self._running = True
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
            registered = 0
            for key_combo, callback in bindings:
                try:
                    l = GlobalHotKeys({key_combo: lambda cb=callback: self._ui(cb)})
                    l.start()
                    self._listeners.append(l)
                    registered += 1
                except Exception as e:
                    print(f"[hotkeys] FAILED to register {key_combo}: {e}",
                          file=sys.stderr)
            print(f"[hotkeys] Registered {registered}/{len(bindings)} hotkeys",
                  file=sys.stderr)

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        # Watchdog: restart if hotkey thread dies unexpectedly
        threading.Thread(target=self._watchdog, daemon=True).start()

    def _watchdog(self):
        """Check every 30s if hotkey thread is alive; restart if dead."""
        while True:
            time.sleep(30)
            if self._thread and not self._thread.is_alive() and self._running:
                print("[hotkeys] WARNING: hotkey thread died, restarting...",
                      file=sys.stderr)
                try:
                    self.stop()
                    self.start()
                    print("[hotkeys] Restarted successfully", file=sys.stderr)
                except Exception as e:
                    print(f"[hotkeys] Restart failed: {e}", file=sys.stderr)
                    self._running = False

    def _ui(self, fn):
        try:
            self._app.root.after(0, fn)
        except Exception as e:
            print(f"[hotkeys] Error dispatching to UI: {e}", file=sys.stderr)

    def _vol_up(self):
        vol = int((getattr(self._app, '_volume', 1.0) + 0.05) * 100)
        self._app.root.after(0, lambda: self._app._set_volume(min(150, vol)))

    def _vol_down(self):
        vol = int((getattr(self._app, '_volume', 1.0) - 0.05) * 100)
        self._app.root.after(0, lambda: self._app._set_volume(max(0, vol)))

    def _mute_toggle(self):
        self._app.root.after(0, self._app._toggle_mute)

    def stop(self):
        self._running = False
        for l in self._listeners:
            try:
                l.stop()
            except Exception as e:
                print(f"[hotkeys] Error stopping listener: {e}", file=sys.stderr)
