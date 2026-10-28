"""A tiny in-memory TTL cache.

Nothing is stored permanently; this only keeps the API from calling the same
upstream source again and again while you click around.
"""

from __future__ import annotations

import functools
import threading
import time
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

_lock = threading.Lock()
_store: dict[tuple, tuple[float, Any]] = {}


def ttl_cache(seconds: int) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = (fn.__module__, fn.__qualname__, args, tuple(sorted(kwargs.items())))
            now = time.monotonic()
            with _lock:
                hit = _store.get(key)
                if hit and hit[0] > now:
                    return hit[1]
            value = fn(*args, **kwargs)
            with _lock:
                _store[key] = (now + seconds, value)
            return value

        return wrapper  # type: ignore[return-value]

    return decorator


def clear() -> None:
    with _lock:
        _store.clear()
