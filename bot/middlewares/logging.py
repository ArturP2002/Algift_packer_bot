from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery, TelegramObject


class DetailedLoggingMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self._logger = logging.getLogger("gift_bot.flow")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            self._logger.info(
                "Шаг: входящее сообщение user_id=%s username=%s state=%s text=%s has_photo=%s successful_payment=%s",
                event.from_user.id if event.from_user else None,
                event.from_user.username if event.from_user else None,
                data.get("raw_state"),
                (event.text or "").strip(),
                bool(event.photo),
                bool(event.successful_payment),
            )
        elif isinstance(event, CallbackQuery):
            self._logger.info(
                "Шаг: callback user_id=%s username=%s state=%s data=%s",
                event.from_user.id if event.from_user else None,
                event.from_user.username if event.from_user else None,
                data.get("raw_state"),
                event.data,
            )
        elif isinstance(event, PreCheckoutQuery):
            self._logger.info(
                "Шаг: pre_checkout user_id=%s payload=%s amount=%s currency=%s",
                event.from_user.id if event.from_user else None,
                event.invoice_payload,
                event.total_amount,
                event.currency,
            )
        return await handler(event, data)
