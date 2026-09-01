"""In-memory LRU cache for rendered HTML reports with ETag support."""

from __future__ import annotations

import threading
import gzip
from collections import OrderedDict

_MAX_ENTRIES = 32

_lock = threading.Lock()
_cache: OrderedDict[str, str] = OrderedDict()
_gzip_cache: OrderedDict[str, bytes] = OrderedDict()


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


def get_cached_gzip(username: str, data_hash: str) -> bytes | None:
    """Return cached gzip bytes, creating them once from cached HTML."""
    k = _key(username, data_hash)
    with _lock:
        compressed = _gzip_cache.get(k)
        if compressed is not None:
            _gzip_cache.move_to_end(k)
            return compressed
        html = _cache.get(k)
    if html is None:
        return None

    compressed = gzip.compress(html.encode("utf-8"), compresslevel=6)
    with _lock:
        # Avoid resurrecting compressed data after an invalidation raced us.
        if _cache.get(k) != html:
            return compressed
        _gzip_cache[k] = compressed
        _gzip_cache.move_to_end(k)
        while len(_gzip_cache) > _MAX_ENTRIES:
            _gzip_cache.popitem(last=False)
    return compressed


def put_cached_html(username: str, data_hash: str, html: str):
    """Store rendered HTML in cache, evicting oldest if over limit."""
    k = _key(username, data_hash)
    with _lock:
        _cache[k] = html
        _cache.move_to_end(k)
        _gzip_cache.pop(k, None)
        while len(_cache) > _MAX_ENTRIES:
            evicted, _ = _cache.popitem(last=False)
            _gzip_cache.pop(evicted, None)


def invalidate_user_html(username: str):
    """Remove all cached HTML entries for a given user."""
    prefix = f"{username}:"
    with _lock:
        keys_to_remove = [k for k in _cache if k.startswith(prefix)]
        for k in keys_to_remove:
            del _cache[k]
            _gzip_cache.pop(k, None)
