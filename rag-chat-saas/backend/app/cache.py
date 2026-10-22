from __future__ import annotations

import copy
import threading
import time
from collections.abc import Callable


class TtlCache:
    def __init__(self, ttl_seconds: float) -> None:
        self.ttl_seconds = max(0.0, ttl_seconds)
        self._lock = threading.Lock()
        self._values: dict[str, tuple[float, object]] = {}
        self._key_locks: dict[str, threading.Lock] = {}

    def get_or_load(self, key: str, loader: Callable[[], object]):
        now = time.monotonic()
        with self._lock:
            cached = self._values.get(key)
            if cached and cached[0] > now:
                return copy.deepcopy(cached[1])
            key_lock = self._key_locks.setdefault(key, threading.Lock())
        with key_lock:
            now = time.monotonic()
            with self._lock:
                cached = self._values.get(key)
                if cached and cached[0] > now:
                    return copy.deepcopy(cached[1])
            value = loader()
            with self._lock:
                self._values[key] = (time.monotonic() + self.ttl_seconds, copy.deepcopy(value))
            return value
