"""
Unified NetEase Cloud Music API client.

Replaces duplicate ncm_get/ncm implementations across the project
with a single canonical version that includes session management,
login-cookie loading, and retry-with-jitter logic.
"""

import json
import os
import random
import time

import requests

import config

# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})


def load_cookie() -> bool:
    """Load NetEase login cookie from LOGIN_FILE into the shared session."""
    if os.path.exists(config.LOGIN_FILE):
        try:
            with open(config.LOGIN_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            for item in d.get("cookie", "").split(";"):
                if "=" in item:
                    k, v = item.strip().split("=", 1)
                    _session.cookies.set(k.strip(), v.strip())
            return True
        except Exception:
            pass
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ncm_get(path: str, params: dict | None = None):
    """Call the local NetEase Cloud Music API with jitter and retries.

    The canonical version — retries up to 3 times with jitter and
    rate-limit-aware backoff.  Returns the parsed JSON body or *None*
    on failure.
    """
    for attempt in range(3):
        time.sleep(random.uniform(0.1, 0.4))
        try:
            r = _session.get(
                f"{config.NCM_API}{path}", params=params, timeout=20
            )
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
