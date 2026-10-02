from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import uuid

from integrations.telegram_stars import TelegramStarsIntegration
from integrations.yookassa import YooKassaIntegration
from database.repository import Repository


@dataclass
class AccessState:
    has_subscription: bool
    paid_requests_left: int


class PaymentService:
    def __init__(
        self,
        yookassa: YooKassaIntegration,
        stars: TelegramStarsIntegration,
        repository: Repository,
        one_time_request_price_rub: int,
        monthly_subscription_price_rub: int,
        one_time_request_price_stars: int,
        monthly_subscription_price_stars: int,
    ) -> None:
        self._yookassa = yookassa
        self._stars = stars
        self._repository = repository
        self._one_time_rub = one_time_request_price_rub
        self._subscription_rub = monthly_subscription_price_rub
        self._one_time_stars = one_time_request_price_stars
        self._subscription_stars = monthly_subscription_price_stars
        self._logger = logging.getLogger("gift_bot.payment")

    def check_access(self, user_id: int) -> bool:
        user = self._repository.get_or_create_user(user_id)
        has_subscription = self._repository.has_active_subscription(user)
        paid_requests_left = self._repository.get_paid_one_time_requests_left(user)
        result = has_subscription or paid_requests_left > 0
        self._logger.info(
            "Проверка доступа user_id=%s: subscription=%s, paid_requests_left=%s, access=%s",
            user_id,
            has_subscription,
            paid_requests_left,
            result,
        )
        return result

    def get_access_state(self, user_id: int) -> AccessState:
        user = self._repository.get_or_create_user(user_id)
        return AccessState(
            has_subscription=self._repository.has_active_subscription(user),
            paid_requests_left=self._repository.get_paid_one_time_requests_left(user),
        )

    def consume_request(self, user_id: int) -> None:
        user = self._repository.get_or_create_user(user_id)
        if self._repository.has_active_subscription(user):
            self._logger.info("Запрос не списан, активна подписка user_id=%s", user_id)
            return
        consumed = self._repository.consume_one_time_request(user)
        self._logger.info("Списание разового запроса user_id=%s, consumed=%s", user_id, consumed)

    def get_one_time_price_rub(self) -> int:
        return self._repository.get_price("one_time_request_price_rub", self._one_time_rub)

    def get_subscription_price_rub(self) -> int:
        return self._repository.get_price("subscription_month_price_rub", self._subscription_rub)

    def get_one_time_price_stars(self) -> int:
        return self._repository.get_price("one_time_request_price_stars", self._one_time_stars)

    def get_subscription_price_stars(self) -> int:
        return self._repository.get_price("subscription_month_price_stars", self._subscription_stars)

    def set_one_time_price_rub(self, value: int) -> None:
        self._repository.set_price("one_time_request_price_rub", value)

    def set_subscription_price_rub(self, value: int) -> None:
        self._repository.set_price("subscription_month_price_rub", value)

    def set_one_time_price_stars(self, value: int) -> None:
        self._repository.set_price("one_time_request_price_stars", value)

    def set_subscription_price_stars(self, value: int) -> None:
        self._repository.set_price("subscription_month_price_stars", value)

    def get_one_time_price(self, provider: str) -> int:
        if provider == "yookassa":
            return self.get_one_time_price_rub()
        return self.get_one_time_price_stars()

    def get_subscription_price(self, provider: str) -> int:
        if provider == "yookassa":
            return self.get_subscription_price_rub()
        return self.get_subscription_price_stars()

    async def create_one_time_payment(self, user_id: int, provider: str) -> dict[str, str]:
        price = self.get_one_time_price(provider)
        payment_id = f"{provider}:one_time:{user_id}:{uuid.uuid4().hex[:12]}"
        if provider == "yookassa":
            url = await self._yookassa.create_payment_link(price, "Разовый подбор подарка", user_id, payment_id)
            return {"provider_payment_id": payment_id, "url": url}
        payload = await self._stars.create_invoice_payload(user_id, price, "Разовый подбор подарка", payment_id)
        return payload

    async def create_subscription_payment(self, user_id: int, provider: str) -> dict[str, str]:
        price = self.get_subscription_price(provider)
        payment_id = f"{provider}:subscription:{user_id}:{uuid.uuid4().hex[:12]}"
        if provider == "yookassa":
            url = await self._yookassa.create_payment_link(price, "Подписка на месяц", user_id, payment_id)
            return {"provider_payment_id": payment_id, "url": url}
        payload = await self._stars.create_invoice_payload(user_id, price, "Подписка на месяц", payment_id)
        return payload

    def grant_one_time_request(self, user_id: int) -> None:
        self._logger.info("Разовый доступ подтвержден в БД user_id=%s", user_id)

    def grant_subscription(self, user_id: int) -> None:
        user = self._repository.get_or_create_user(user_id)
        expires_at = datetime.utcnow() + timedelta(days=30)
        self._repository.set_subscription(user, expires_at)
        self._logger.info("Подписка подтверждена user_id=%s expires_at=%s", user_id, expires_at.isoformat())

    def cleanup_stale_paid_requests(self, older_than_hours: int) -> int:
        cutoff = datetime.utcnow() - timedelta(hours=max(1, older_than_hours))
        cleaned = self._repository.cleanup_stale_paid_one_time(cutoff)
        self._logger.info(
            "Авто-очистка старых paid записей: cleaned=%s older_than_hours=%s cutoff=%s",
            cleaned,
            older_than_hours,
            cutoff.isoformat(),
        )
        return cleaned
