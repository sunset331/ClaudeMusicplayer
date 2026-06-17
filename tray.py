#!/usr/bin/env python3
"""
System tray + toast notifications + taskbar integration for Claude Music Player.

- System tray icon with right-click menu (pystray + PIL)
- Windows toast notifications on song change (winotify → PowerShell fallback)
- Taskbar progress bar + thumbnail buttons (pywin32 ITaskbarList3)
"""
import os
import threading

HOME = os.path.dirname(os.path.abspath(__file__))

# ── Icon generation ─────────────────────────────────────────────
def _make_icon_image(size=64):
    """Generate a purple→pink gradient rounded-square icon via PIL."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Gradient from top-left purple to bottom-right pink
    for y in range(size):
        for x in range(size):
            r = int(0xc0 + (0xf0 - 0xc0) * y / size)
            g = int(0x84 + (0xa8 - 0x84) * x / size)
            b = int(0xfc + (0xc0 - 0xfc) * (x + y) / (2 * size))
            # Rounded corners (radius = size/6)
            rdist = size // 6
            corners = [
                (x - rdist)**2 + (y - rdist)**2 < rdist**2 and x < rdist and y < rdist,
                (x - (size - rdist))**2 + (y - rdist)**2 < rdist**2 and x > size - rdist and y < rdist,
                (x - rdist)**2 + (y - (size - rdist))**2 < rdist**2 and x < rdist and y > size - rdist,
                (x - (size - rdist))**2 + (y - (size - rdist))**2 < rdist**2 and x > size - rdist and y > size - rdist,
            ]
            if any(corners):
                continue
            draw.point((x, y), fill=(r, g, b, 255))
    # Draw music note in center
    note_size = size // 3
    cx, cy = size // 2, size // 2
    draw.ellipse([cx - note_size // 2, cy - note_size // 2,
                  cx + note_size // 2, cy + note_size // 2],
                 fill=(255, 255, 255, 230))
    return img


# ── Toast notifications ─────────────────────────────────────────

def show_toast(title, body, icon_path=None, duration="short"):
    """Show a Windows toast notification. Falls back gracefully."""
    try:
        from winotify import Notification
        toast = Notification(app_id="Claude Music",
                             title=title,
                             msg=body,
                             duration=duration)
        if icon_path and os.path.exists(icon_path):
            toast.set_audio(src=None, loop=False)
            toast.add_actions(buttons=[])
        toast.show()
    except Exception:
        # PowerShell fallback (no winotify dependency needed)
        _ps_toast(title, body)


def _ps_toast(title, body):
    """Minimal toast via PowerShell. No dependency."""
    import subprocess
    # Escape PowerShell special chars: $ → `$, ` → ``, strip newlines
    def _escape(s):
        return s.replace('`', '``').replace('$', '`$').replace('\n', ' ').replace('\r', '')
    title_safe = _escape(title)
    body_safe = _escape(body)
    ps = f'''\
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
    [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$texts = $template.GetElementsByTagName("text")
$texts[0].AppendChild($template.CreateTextNode("{title_safe}")) > $null
$texts[1].AppendChild($template.CreateTextNode("{body_safe}")) > $null
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Claude Music").Show($toast)
'''
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=8,
                       creationflags=0x08000000)
    except Exception:
        pass


# ── Taskbar integration (Windows 7+) ─────────────────────────────

class TaskbarHelper:
    """Manage taskbar progress bar and thumbnail buttons via ITaskbarList3."""

    def __init__(self, root):
        self._root = root
        self._pITaskbarList3 = None
        self._hwnd = None
        self._initialized = False
        self._try_init()

    def _try_init(self):
        try:
            from win32com.client import Dispatch
            # ITaskbarList3 CLSID: {56FDF344-FD6D-11d0-958A-006097C9A090}
            self._pITaskbarList3 = Dispatch("{56FDF344-FD6D-11d0-958A-006097C9A090}")
            self._pITaskbarList3.HrInit()
        except Exception:
            self._pITaskbarList3 = None
            return
        # Try to get HWND — needs window to be mapped first
        self._root.update_idletasks()
        try:
            self._hwnd = self._root.frame()  # tk's HWND as integer
            if self._hwnd:
                self._initialized = True
        except Exception:
            pass

    def _ensure_hwnd(self):
        if not self._hwnd or not self._initialized:
            self._try_init()

    def set_progress(self, value_pct):
        """Set taskbar progress bar (0-100). """
        if not self._pITaskbarList3:
            return
        self._ensure_hwnd()
        try:
            completed = int(value_pct)
            total = 100
            # TBPF_NORMAL = 0x2, TBPF_NOPROGRESS = 0x0
            self._pITaskbarList3.SetProgressValue(self._hwnd, completed, total)
        except Exception:
            pass

    def set_playing_state(self):
        """Green progress bar (TBPF_NORMAL)."""
        if not self._pITaskbarList3:
            return
        self._ensure_hwnd()
        try:
            # TBPF_NORMAL = 0x2
            self._pITaskbarList3.SetProgressState(self._hwnd, 0x2)
        except Exception:
            pass

    def set_paused_state(self):
        """Yellow progress bar (TBPF_PAUSED = 0x8)."""
        if not self._pITaskbarList3:
            return
        self._ensure_hwnd()
        try:
            self._pITaskbarList3.SetProgressState(self._hwnd, 0x8)
        except Exception:
            pass

    def clear_progress(self):
        if not self._pITaskbarList3:
            return
        self._ensure_hwnd()
        try:
            self._pITaskbarList3.SetProgressState(self._hwnd, 0x0)  # TBPF_NOPROGRESS
        except Exception:
            pass


# ── System Tray ──────────────────────────────────────────────────

class SystemTray:
    """Manages the Windows system tray icon and menu."""

    def __init__(self, app):
        """
        app must expose:
          - app.root (tk.Tk)
          - app._toggle()
          - app._next()
          - app._prev()
          - app._on_close()
          - app._tray_quit() — custom quit handler
        """
        self._app = app
        self._icon = None
        self._thread = None
        self._visible = True

    def start(self):
        """Start system tray in background thread."""
        self._thread = threading.Thread(target=self._run_tray, daemon=True)
        self._thread.start()

    def _run_tray(self):
        import pystray

        icon_img = _make_icon_image(64)
        # pystray needs a method to generate icon data
        menu = pystray.Menu(
            pystray.MenuItem("▶ 播放/暂停", self._on_toggle, default=True),
            pystray.MenuItem("⏭ 下一首", self._on_next),
            pystray.MenuItem("⏮ 上一首", self._on_prev),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("👁 显示/隐藏", self._on_show_hide),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("✕ 退出", self._on_quit),
        )

        self._icon = pystray.Icon(
            "ClaudeMusic",
            icon_img,
            "Claude Music · 每日推荐",
            menu,
        )
        self._icon.run()

    def _run_on_ui(self, fn):
        """Schedule a function to run on the tkinter main thread."""
        try:
            self._app.root.after(0, fn)
        except Exception:
            pass

    def _on_toggle(self, icon=None, item=None):
        self._run_on_ui(self._app._toggle)

    def _on_next(self, icon=None, item=None):
        self._run_on_ui(self._app._next)

    def _on_prev(self, icon=None, item=None):
        self._run_on_ui(self._app._prev)

    def _on_show_hide(self, icon=None, item=None):
        def _fn():
            if self._visible:
                self._app.root.withdraw()
                self._visible = False
            else:
                self._app.root.deiconify()
                self._app.root.lift()
                self._app.root.focus_force()
                self._visible = True
        self._run_on_ui(_fn)

    def _on_quit(self, icon=None, item=None):
        if self._icon:
            self._icon.stop()
        self._run_on_ui(self._app._tray_quit)

    def is_visible(self):
        return self._visible

    def stop(self):
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
