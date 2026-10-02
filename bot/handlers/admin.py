from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
import texts
from services.recommendation_service import event_label

router = Router()


def _is_admin(message: Message) -> bool:
    container = message.bot.container
    return message.from_user.id in set(container.settings.admin_ids)


@router.message(Command("admin_prices"))
async def admin_prices(message: Message) -> None:
    if not _is_admin(message):
        await message.answer(texts.NO_RIGHTS)
        return
    payment_service = message.bot.container.payment_service
    await message.answer(
        texts.ADMIN_PRICES.format(
            one_time_rub=payment_service.get_one_time_price_rub(),
            subscription_rub=payment_service.get_subscription_price_rub(),
            one_time_stars=payment_service.get_one_time_price_stars(),
            subscription_stars=payment_service.get_subscription_price_stars(),
        )
    )


@router.message(Command("set_one_time_price"))
async def set_one_time_price(message: Message) -> None:
    if not _is_admin(message):
        await message.answer(texts.NO_RIGHTS)
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer(texts.ADMIN_PRICE_FORMAT_ONE)
        return
    value = int(parts[1])
    message.bot.container.payment_service.set_one_time_price_stars(value)
    await message.answer(texts.ADMIN_ONE_UPDATED.format(value=value))


@router.message(Command("set_subscription_price"))
async def set_subscription_price(message: Message) -> None:
    if not _is_admin(message):
        await message.answer(texts.NO_RIGHTS)
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer(texts.ADMIN_PRICE_FORMAT_SUB)
        return
    value = int(parts[1])
    message.bot.container.payment_service.set_subscription_price_stars(value)
    await message.answer(texts.ADMIN_SUB_UPDATED.format(value=value))


@router.message(Command("set_one_time_price_rub"))
async def set_one_time_price_rub(message: Message) -> None:
    if not _is_admin(message):
        await message.answer(texts.NO_RIGHTS)
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer(texts.ADMIN_PRICE_FORMAT_ONE_RUB)
        return
    value = int(parts[1])
    message.bot.container.payment_service.set_one_time_price_rub(value)
    await message.answer(texts.ADMIN_ONE_RUB_UPDATED.format(value=value))


@router.message(Command("set_subscription_price_rub"))
async def set_subscription_price_rub(message: Message) -> None:
    if not _is_admin(message):
        await message.answer(texts.NO_RIGHTS)
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer(texts.ADMIN_PRICE_FORMAT_SUB_RUB)
        return
    value = int(parts[1])
    message.bot.container.payment_service.set_subscription_price_rub(value)
    await message.answer(texts.ADMIN_SUB_RUB_UPDATED.format(value=value))


@router.message(Command("catalog_stats"))
async def catalog_stats(message: Message) -> None:
    if not _is_admin(message):
        await message.answer(texts.NO_RIGHTS)
        return
    total = message.bot.container.product_service.catalog_size()
    await message.answer(texts.ADMIN_CATALOG_STATS.format(total=total))


@router.message(Command("feedback_stats"))
async def feedback_stats(message: Message) -> None:
    if not _is_admin(message):
        await message.answer(texts.NO_RIGHTS)
        return
    stats = message.bot.container.repository.feedback_stats()
    recent = "\n".join(
        f"- {row['name']} ({event_label(row['event'])}, бюджет {row['budget']} ₽)" for row in stats["recent_down"]
    )
    await message.answer(
        texts.ADMIN_FEEDBACK_STATS.format(
            week_up=stats["week"][0],
            week_down=stats["week"][1],
            month_up=stats["month"][0],
            month_down=stats["month"][1],
            recent=recent or texts.ADMIN_FEEDBACK_EMPTY,
        )
    )


