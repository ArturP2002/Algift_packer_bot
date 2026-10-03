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
        exclude = payload.get("exclude_names") or []
        if isinstance(exclude, str):
            exclude_list = [exclude]
        else:
            exclude_list = [str(item).strip().lower() for item in exclude if str(item).strip()]
        normalized = {
            "age": payload.get("age"),
            "gender": payload.get("gender"),
            "event": payload.get("event"),
            "relation": payload.get("relation"),
            "budget": payload.get("budget"),
            "budget_min": payload.get("budget_min"),
            "hobbies": (payload.get("hobbies") or "").strip().lower(),
            "mode": payload.get("mode", "extended"),
            "photo_insights": (payload.get("photo_insights") or "").strip().lower()[:500],
            "exclude_names": sorted(set(exclude_list)),
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
