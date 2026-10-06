from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 подобрать подарок", callback_data="menu:start")],
            [InlineKeyboardButton(text="ℹ️ как это работает", callback_data="menu:how")],
        ]
    )


def how_it_works_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 подобрать подарок", callback_data="menu:start")],
            [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="menu:cabinet")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:home")],
        ]
    )


def cabinet_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 Купить подписку", callback_data="buy:subscription")],
            [InlineKeyboardButton(text="⚡ Купить разовый запрос", callback_data="buy:one_time")],
            [InlineKeyboardButton(text="🎯 Новый подбор", callback_data="pick:again")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:home")],
        ]
    )


def mode_keyboard(*, free_quick_available: bool = True, photo_price_label: str = "") -> InlineKeyboardMarkup:
    if free_quick_available:
        quick_label = "⚡ Быстрый подбор (первый бесплатно)"
    else:
        quick_label = "⚡ Быстрый подбор"
    photo_label = "🔍 Умный подбор (с фото)"
    if photo_price_label:
        photo_label = f"{photo_label} — {photo_price_label}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=quick_label, callback_data="mode:quick")],
            [InlineKeyboardButton(text=photo_label, callback_data="mode:extended")],
        ]
    )


def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👩 Женский", callback_data="gender:женский")],
            [InlineKeyboardButton(text="👨 Мужской", callback_data="gender:мужской")],
        ]
    )


def event_keyboard() -> InlineKeyboardMarkup:
    items = [("🎂 День рождения", "birthday"), ("🎄 Новый год", "new_year"), ("🌸 8 марта", "march8"), ("🎁 Другое", "other")]
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=title, callback_data=f"event:{value}")] for title, value in items]
    )


def relation_keyboard() -> InlineKeyboardMarkup:
    items = [
        ("❤️ Девушка", "girlfriend"),
        ("👩 Мама", "mother"),
        ("👨 Папа", "father"),
        ("👧 Дочь", "daughter"),
        ("🧑 Друг", "friend"),
        ("🤵 Муж", "husband"),
        ("👰 Жена", "wife"),
        ("✏️ Другое", "other"),
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=title, callback_data=f"relation:{value}")] for title, value in items]
    )


def budget_keyboard() -> InlineKeyboardMarkup:
    items = [("💸 1 000 - 3 000", "1000-3000"), ("💸 3 000 - 5 000", "3000-5000"), ("💸 5 000 - 10 000", "5000-10000"), ("💸 10 000 - 20 000", "10000-20000"), ("💰 Ввести свой", "custom")]
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=title, callback_data=f"budget:{value}")] for title, value in items]
    )


FEEDBACK_PREFIX = "fb:"
CAROUSEL_PREFIX = "car:"


def product_links_keyboard(link_group: dict[str, Any] | None, item_id: int | None = None) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    offers = (link_group or {}).get("offers")
    if isinstance(offers, list):
        for offer in offers:
            if not isinstance(offer, dict):
                continue
            url = str(offer.get("url") or "").strip()
            label = str(offer.get("label") or offer.get("marketplace") or "Купить").strip()
            if not url:
                continue
            # В подписи название модели, поэтому по одной кнопке в строке — иначе Telegram обрежет текст.
            rows.append([InlineKeyboardButton(text=label[:64], url=url)])
    if item_id is not None:
        rows.append(
            [
                InlineKeyboardButton(text="👍 Подходит", callback_data=f"{FEEDBACK_PREFIX}{item_id}:up"),
                InlineKeyboardButton(text="👎 Мимо", callback_data=f"{FEEDBACK_PREFIX}{item_id}:down"),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def carousel_keyboard(
    *,
    index: int,
    total: int,
    link_group: dict[str, Any] | None,
    item_id: int | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    rows.append(
        [
            InlineKeyboardButton(text="⬅️", callback_data=f"{CAROUSEL_PREFIX}prev"),
            InlineKeyboardButton(text=f"({index + 1}/{total})", callback_data=f"{CAROUSEL_PREFIX}noop"),
            InlineKeyboardButton(text="➡️", callback_data=f"{CAROUSEL_PREFIX}next"),
        ]
    )
    offers = (link_group or {}).get("offers")
    if isinstance(offers, list):
        for offer in offers:
            if not isinstance(offer, dict):
                continue
            url = str(offer.get("url") or "").strip()
            label = str(offer.get("label") or offer.get("marketplace") or "Купить").strip()
            if not url:
                continue
            rows.append([InlineKeyboardButton(text=label[:64], url=url)])
    if item_id is not None:
        rows.append(
            [
                InlineKeyboardButton(text="👍 Подходит", callback_data=f"{FEEDBACK_PREFIX}{item_id}:up"),
                InlineKeyboardButton(text="👎 Мимо", callback_data=f"{FEEDBACK_PREFIX}{item_id}:down"),
            ]
        )
    rows.append([InlineKeyboardButton(text="🔄 подобрать ещё", callback_data=f"{CAROUSEL_PREFIX}more")])
    rows.append([InlineKeyboardButton(text="✏️ Изменить условия", callback_data=f"{CAROUSEL_PREFIX}edit")])
    rows.append([InlineKeyboardButton(text="🔎 найти похожие", callback_data=f"{CAROUSEL_PREFIX}similar")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def feedback_given_keyboard(markup: InlineKeyboardMarkup | None, vote: int) -> InlineKeyboardMarkup:
    """Кнопки товаров остаются, ряд оценки заменяется отметкой о выбранной оценке."""
    rows = [
        row
        for row in (markup.inline_keyboard if markup else [])
        if not any((button.callback_data or "").startswith(FEEDBACK_PREFIX) for button in row)
    ]
    label = "✅ Оценка учтена: подходит" if vote > 0 else "✅ Оценка учтена: мимо"
    rows.append([InlineKeyboardButton(text=label, callback_data=f"{FEEDBACK_PREFIX}done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def retry_recommendation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔁 Повторить подбор", callback_data="reco:retry")]]
    )


def after_results_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🎯 Новый подбор", callback_data="pick:again")]]
    )


def reuse_survey_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Продолжить с ранее заполненными данными", callback_data="pick:reuse")],
            [InlineKeyboardButton(text="✏️ Продолжить с новыми данными", callback_data="pick:fresh")],
        ]
    )


def photo_upsell_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔍 Подбор с фото", callback_data="upsell:photo")]]
    )


def access_paywall_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Разовый подбор", callback_data="buy:one_time")],
            [InlineKeyboardButton(text="💎 Подписка на месяц", callback_data="buy:subscription")],
        ]
    )


def payment_choice_keyboard(kind: str = "one_time") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Telegram Stars", callback_data=f"pay:stars:{kind}")],
            [InlineKeyboardButton(text="💳 YooKassa", callback_data=f"pay:yookassa:{kind}")],
        ]
    )


def yookassa_check_keyboard(payment_id: str, payment_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть YooKassa", url=payment_url)],
            [InlineKeyboardButton(text="Проверить платеж", callback_data=f"paycheck:{payment_id}")],
        ]
    )
