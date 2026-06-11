"""In-memory LRU cache for rendered HTML reports with ETag support."""

from __future__ import annotations

import threading
from collections import OrderedDict

_MAX_ENTRIES = 32

_lock = threading.Lock()
_cache: OrderedDict[str, str] = OrderedDict()


def _key(username: str, data_hash: str) -> str:
    return f"{username}:{data_hash}"


def get_cached_html(username: str, data_hash: str) -> str | None:
    """Return cached HTML for user+hash, or None if not cached."""
    k = _key(username, data_hash)
    with _lock:
        if k in _cache:
            _cache.move_to_end(k)
            return _cache[k]
    return None


def put_cached_html(username: str, data_hash: str, html: str):
    """Store rendered HTML in cache, evicting oldest if over limit."""
    k = _key(username, data_hash)
    with _lock:
        _cache[k] = html
        _cache.move_to_end(k)
        while len(_cache) > _MAX_ENTRIES:
            _cache.popitem(last=False)


def invalidate_user_html(username: str):
    """Remove all cached HTML entries for a given user."""
    prefix = f"{username}:"
    with _lock:
        keys_to_remove = [k for k in _cache if k.startswith(prefix)]
        for k in keys_to_remove:
            del _cache[k]
