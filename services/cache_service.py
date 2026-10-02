from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0


class CacheService:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}
        self._stats = CacheStats()

    def make_key(self, payload: dict[str, Any]) -> str:
        normalized = {
            "age": payload.get("age"),
            "gender": payload.get("gender"),
            "event": payload.get("event"),
            "relation": payload.get("relation"),
            "budget": payload.get("budget"),
            "hobbies": (payload.get("hobbies") or "").strip().lower(),
            "mode": payload.get("mode", "extended"),
        }
        raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if not item:
            self._stats.misses += 1
            return None
        expires_at, value = item
        if time.time() >= expires_at:
            self._store.pop(key, None)
            self._stats.misses += 1
            return None
        self._stats.hits += 1
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.time() + self._ttl_seconds, value)

    def stats(self) -> CacheStats:
        return self._stats
