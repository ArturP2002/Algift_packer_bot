from __future__ import annotations

import json
from datetime import datetime, timedelta

from database.models import (
    AppSetting,
    CacheEntry,
    ItemFeedback,
    Payment,
    RecommendationItem,
    RecommendationRequest,
    Subscription,
    User,
)


class Repository:
    def get_or_create_user(self, telegram_id: int, username: str | None = None) -> User:
        user, _ = User.get_or_create(telegram_id=telegram_id, defaults={"username": username})
        if username and user.username != username:
            user.username = username
            user.save()
        return user

    def create_request(self, user: User, payload: dict) -> RecommendationRequest:
        return RecommendationRequest.create(user=user, **payload)

    def save_items(self, request: RecommendationRequest, items: list[dict]) -> list[RecommendationItem]:
        saved: list[RecommendationItem] = []
        for item in items:
            links = item.get("links") or []
            offers = links[0].get("offers", []) if links else []
            saved.append(
                RecommendationItem.create(
                    request=request,
                    name=item.get("name", "Gift"),
                    reason=item.get("reason", ""),
                    keywords_json=json.dumps(item.get("keywords", []), ensure_ascii=False),
                    price_level=item.get("price_level", "medium"),
                    fits_budget=bool(item.get("fits_budget", True)),
                    offers_json=json.dumps(
                        [{"title": o.get("title"), "price": o.get("price"), "url": o.get("url")} for o in offers],
                        ensure_ascii=False,
                    ),
                )
            )
        return saved

    def set_feedback(self, item_id: int, telegram_id: int, vote: int) -> bool:
        """Повторная оценка той же идеи перезаписывает предыдущую. False — идеи нет в БД."""
        if not RecommendationItem.select().where(RecommendationItem.id == item_id).exists():
            return False
        ItemFeedback.insert(item=item_id, telegram_id=telegram_id, vote=vote).on_conflict(
            conflict_target=[ItemFeedback.item, ItemFeedback.telegram_id],
            update={ItemFeedback.vote: vote, ItemFeedback.created_at: datetime.utcnow()},
        ).execute()
        return True

    def feedback_stats(self, *, recent_limit: int = 10) -> dict:
        now = datetime.utcnow()

        def votes_since(days: int) -> tuple[int, int]:
            rows = ItemFeedback.select(ItemFeedback.vote).where(ItemFeedback.created_at >= now - timedelta(days=days))
            votes = [row.vote for row in rows]
            return sum(1 for vote in votes if vote > 0), sum(1 for vote in votes if vote < 0)

        recent_down = (
            ItemFeedback.select(ItemFeedback, RecommendationItem, RecommendationRequest)
            .join(RecommendationItem)
            .join(RecommendationRequest)
            .where(ItemFeedback.vote < 0)
            .order_by(ItemFeedback.created_at.desc())
            .limit(recent_limit)
        )
        return {
            "week": votes_since(7),
            "month": votes_since(30),
            "recent_down": [
                {
                    "name": row.item.name,
                    "event": row.item.request.event,
                    "budget": row.item.request.budget,
                }
                for row in recent_down
            ],
        }

    def create_or_get_payment(
        self,
        user: User,
        provider: str,
        kind: str,
        amount_rub: int,
        provider_payment_id: str,
        idempotency_key: str | None,
    ) -> Payment:
        payment, _ = Payment.get_or_create(
            provider_payment_id=provider_payment_id,
            defaults={
                "user": user,
                "provider": provider,
                "kind": kind,
                "amount_rub": amount_rub,
                "idempotency_key": idempotency_key,
            },
        )
        return payment

    def mark_payment_paid(self, provider_payment_id: str) -> None:
        Payment.update(status="paid").where(Payment.provider_payment_id == provider_payment_id).execute()

    def has_active_subscription(self, user: User) -> bool:
        now = datetime.utcnow()
        return (
            Subscription.select()
            .where(
                (Subscription.user == user)
                & (Subscription.is_active == True)  # noqa: E712
                & ((Subscription.expires_at.is_null(True)) | (Subscription.expires_at > now))
            )
            .exists()
        )

    def get_active_subscription(self, user: User) -> Subscription | None:
        now = datetime.utcnow()
        return (
            Subscription.select()
            .where(
                (Subscription.user == user)
                & (Subscription.is_active == True)  # noqa: E712
                & ((Subscription.expires_at.is_null(True)) | (Subscription.expires_at > now))
            )
            .order_by(Subscription.created_at.desc())
            .first()
        )

    def get_paid_one_time_requests_left(self, user: User) -> int:
        return (
            Payment.select()
            .where((Payment.user == user) & (Payment.kind == "one_time") & (Payment.status == "paid"))
            .count()
        )

    def consume_one_time_request(self, user: User) -> bool:
        payment = (
            Payment.select()
            .where((Payment.user == user) & (Payment.kind == "one_time") & (Payment.status == "paid"))
            .order_by(Payment.created_at.asc())
            .first()
        )
        if not payment:
            return False
        payment.status = "consumed"
        payment.save()
        return True

    def cleanup_stale_paid_one_time(self, older_than_dt: datetime) -> int:
        return (
            Payment.update(status="consumed")
            .where(
                (Payment.kind == "one_time")
                & (Payment.status == "paid")
                & (Payment.created_at < older_than_dt)
            )
            .execute()
        )

    def set_subscription(self, user: User, expires_at: datetime) -> Subscription:
        Subscription.update(is_active=False).where(Subscription.user == user).execute()
        return Subscription.create(user=user, is_active=True, expires_at=expires_at)

    def put_cache(self, key: str, value_json: str, expires_at: datetime) -> None:
        CacheEntry.insert(cache_key=key, value_json=value_json, expires_at=expires_at).on_conflict(
            conflict_target=[CacheEntry.cache_key],
            update={CacheEntry.value_json: value_json, CacheEntry.expires_at: expires_at},
        ).execute()

    def get_price(self, key: str, default_value: int) -> int:
        setting = AppSetting.get_or_none(AppSetting.key == key)
        if not setting:
            return default_value
        if setting.value.isdigit():
            return int(setting.value)
        return default_value

    def set_price(self, key: str, value: int) -> None:
        AppSetting.insert(key=key, value=str(value)).on_conflict(
            conflict_target=[AppSetting.key],
            update={AppSetting.value: str(value), AppSetting.updated_at: datetime.utcnow()},
        ).execute()

    def count_paid_payments(self, user: User) -> int:
        return Payment.select().where((Payment.user == user) & (Payment.status == "paid")).count()

    def get_open_payment(self, user: User, provider: str, kind: str) -> Payment | None:
        """Незавершённый платёж того же провайдера и типа — чтобы не плодить ссылки."""
        return (
            Payment.select()
            .where(
                (Payment.user == user)
                & (Payment.provider == provider)
                & (Payment.kind == kind)
                & (Payment.status == "created")
            )
            .order_by(Payment.created_at.desc())
            .first()
        )

    def recent_recommendation_names(self, user: User, *, limit: int = 24) -> list[str]:
        rows = (
            RecommendationItem.select(RecommendationItem.name)
            .join(RecommendationRequest)
            .where(RecommendationRequest.user == user)
            .order_by(RecommendationItem.created_at.desc())
            .limit(limit)
        )
        names: list[str] = []
        seen: set[str] = set()
        for row in rows:
            name = (row.name or "").strip()
            key = name.lower()
            if not name or key in seen:
                continue
            seen.add(key)
            names.append(name)
        return names

    def recent_downvoted_names(self, user: User, *, limit: int = 12) -> list[str]:
        rows = (
            ItemFeedback.select(ItemFeedback, RecommendationItem)
            .join(RecommendationItem)
            .join(RecommendationRequest)
            .where((ItemFeedback.telegram_id == user.telegram_id) & (ItemFeedback.vote < 0))
            .order_by(ItemFeedback.created_at.desc())
            .limit(limit)
        )
        names: list[str] = []
        seen: set[str] = set()
        for row in rows:
            name = (row.item.name or "").strip()
            key = name.lower()
            if not name or key in seen:
                continue
            seen.add(key)
            names.append(name)
        return names

    def is_intro_seen(self, user: User) -> bool:
        return bool(user.intro_seen)

    def mark_intro_seen(self, user: User) -> None:
        user.intro_seen = True
        user.save()
