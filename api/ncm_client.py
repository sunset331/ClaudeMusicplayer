"""
Unified NetEase Cloud Music API client.

Replaces duplicate ncm_get/ncm implementations across the project
with a single canonical version that includes session management,
login-cookie loading, and retry-with-jitter logic.

Cookie is passed as a query parameter (``cookie=...``) because the
NeteaseCloudMusicApiEnhanced Docker container reads it from the URL,
NOT from HTTP Cookie headers.
"""

import json
import os
import random
import time
import urllib.parse

import requests

import config

# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

_COOKIE_VALUE: str = ""


def load_cookie() -> bool:
    """Load NetEase login cookie from LOGIN_FILE for use as a URL query param."""
    global _COOKIE_VALUE
    if os.path.exists(config.LOGIN_FILE):
        try:
            with open(config.LOGIN_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            _COOKIE_VALUE = d.get("cookie", "")
            return bool(_COOKIE_VALUE)
        except Exception:
            pass
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _ncm_url(path: str, params: dict | None = None) -> str:
    """Build the full NetEase API URL, attaching cookie and query params."""
    base = f"{config.NCM_API}{path}"
    merged: dict[str, str] = {}
    if _COOKIE_VALUE:
        merged["cookie"] = _COOKIE_VALUE
    if params:
        merged.update({k: str(v) for k, v in params.items()})
    if not merged:
        return base
    return f"{base}?{urllib.parse.urlencode(merged)}"


def ncm_get(path: str, params: dict | None = None):
    """Call the local NetEase Cloud Music API with jitter and retries.

    The canonical version — retries up to 3 times with jitter and
    rate-limit-aware backoff.  Returns the parsed JSON body or *None*
    on failure.
    """
    url = _ncm_url(path, params)
    for attempt in range(3):
        time.sleep(random.uniform(0.1, 0.4))
        try:
            r = _session.get(url, timeout=20)
            r.raise_for_status()
            return r.json()
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else 0
            if code in (405, 429, 503) and attempt < 2:
                time.sleep(1.5 + random.uniform(0, 2.5))
                continue
            print(f"  [API ERR] {path}: {e}")
            return None
        except requests.RequestException as e:
            if attempt < 2:
                time.sleep(1.0 + random.uniform(0, 1.5))
                continue
            print(
                f"  [API ERR] {path}: "
                f"{'timeout' if 'timed out' in str(e).lower() else e}"
            )
            return None


def ncm(path: str, params: dict | None = None):
    """Thin alias for ``ncm_get`` — backward compatibility with ``app.py``."""
    return ncm_get(path, params)


# ---------------------------------------------------------------------------
# Auto-load cookie on import (matches app.py's module-level side-effect)
# ---------------------------------------------------------------------------
load_cookie()
