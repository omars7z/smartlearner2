"""Thread-safe snapshot of Groq API rate-limit headers for UI / response forwarding."""

from __future__ import annotations

import threading
import time
from typing import Any

_LOCK = threading.Lock()
_SNAPSHOT: dict[str, str] = {}
_UPDATED_AT: float | None = None

# Groq response header names (lowercase, HTTP convention)
GROQ_KEYS = (
    "x-ratelimit-limit-requests",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-reset-requests",
    "x-ratelimit-remaining-tokens",
)

# Safe names exposed to browser (CORS + custom)
OUT_HEADERS = {
    "x-ratelimit-limit-requests": "X-App-RateLimit-Limit-Requests",
    "x-ratelimit-remaining-requests": "X-App-RateLimit-Remaining-Requests",
    "x-ratelimit-reset-requests": "X-App-RateLimit-Reset-Requests",
    "x-ratelimit-remaining-tokens": "X-App-RateLimit-Remaining-Tokens",
}


def update_from_headers(headers: Any) -> None:
    """Extract Groq rate-limit headers (httpx.Headers is case-insensitive)."""
    global _UPDATED_AT
    if headers is None:
        return
    get = getattr(headers, "get", None)
    if not callable(get):
        return
    found: dict[str, str] = {}
    for key in GROQ_KEYS:
        try:
            val = get(key)
        except Exception:
            val = None
        if val is not None and str(val).strip() != "":
            found[key] = str(val).strip()
    if not found:
        return
    with _LOCK:
        _SNAPSHOT.update(found)
        _UPDATED_AT = time.time()


def snapshot_json() -> dict[str, Any]:
    with _LOCK:
        return {
            "limit_requests": _SNAPSHOT.get("x-ratelimit-limit-requests"),
            "remaining_requests": _SNAPSHOT.get("x-ratelimit-remaining-requests"),
            "reset_requests_seconds": _SNAPSHOT.get("x-ratelimit-reset-requests"),
            "remaining_tokens": _SNAPSHOT.get("x-ratelimit-remaining-tokens"),
            "updated_at": _UPDATED_AT,
        }


def response_header_pairs() -> list[tuple[str, str]]:
    """(out_header_name, value) for attaching to FastAPI responses."""
    with _LOCK:
        return [
            (OUT_HEADERS[k], _SNAPSHOT[k])
            for k in GROQ_KEYS
            if k in _SNAPSHOT and k in OUT_HEADERS
        ]
