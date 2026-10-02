from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from aiogram.exceptions import DataNotDictLikeError
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, DefaultKeyBuilder, KeyBuilder, StateType, StorageKey

from database.models import FsmRecord


class SqliteStorage(BaseStorage):
    """FSM-хранилище в основной SQLite-базе: анкета не теряется при перезапуске бота."""

    def __init__(self, key_builder: KeyBuilder | None = None) -> None:
        self._key_builder = key_builder or DefaultKeyBuilder(with_bot_id=True)

    def _key(self, key: StorageKey) -> str:
        return self._key_builder.build(key)

    def _save(self, key: StorageKey, **fields: Any) -> None:
        record = FsmRecord.get_or_none(FsmRecord.key == self._key(key))
        if record is None:
            record = FsmRecord(key=self._key(key))
        for name, value in fields.items():
            setattr(record, name, value)
        if record.state is None and record.data_json == "{}":
            if record.id is not None:
                record.delete_instance()
            return
        record.updated_at = datetime.utcnow()
        record.save()

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        self._save(key, state=state.state if isinstance(state, State) else state)

    async def get_state(self, key: StorageKey) -> str | None:
        record = FsmRecord.get_or_none(FsmRecord.key == self._key(key))
        return record.state if record else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        if not isinstance(data, dict):
            msg = f"Data must be a dict or dict-like object, got {type(data).__name__}"
            raise DataNotDictLikeError(msg)
        self._save(key, data_json=json.dumps(data, ensure_ascii=False))

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        record = FsmRecord.get_or_none(FsmRecord.key == self._key(key))
        return json.loads(record.data_json) if record else {}

    async def close(self) -> None:
        pass
