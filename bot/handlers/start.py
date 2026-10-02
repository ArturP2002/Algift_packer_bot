from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    KeyboardButton,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    User,
)

from bot.keyboards.inline import (
    FEEDBACK_PREFIX,
    budget_keyboard,
    cabinet_keyboard,
    event_keyboard,
    feedback_given_keyboard,
    gender_keyboard,
    main_menu_keyboard,
    mode_keyboard,
    payment_choice_keyboard,
    product_links_keyboard,
    relation_keyboard,
    retry_recommendation_keyboard,
    yookassa_check_keyboard,
)
from bot.states.survey import SurveyStates
import texts
from services.budget_service import budget_floor, normalize_budget
from services.recommendation_service import (
    RecommendationContext,
    RecommendationUnavailable,
    event_label,
    relation_label,
)

router = Router()
logger = logging.getLogger("gift_bot.start")
PHOTO_STATE_LOCKS: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

GENDER_ALLOWED = {"мужской", "женский"}
HOBBIES_SKIP_WORDS = {"нет", "не знаю", "пропустить", "-", "—"}
PHOTO_REPLY_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Готово")]],
    resize_keyboard=True,
    one_time_keyboard=False,
)


def _build_telegram_file_url(bot_token: str, file_path: str) -> str:
    return f"https://api.telegram.org/file/bot{bot_token}/{file_path}"


async def _delete_user_input(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


def _payment_kind_from_marker(marker: str) -> str:
    return "subscription" if ":subscription:" in marker else "one_time"


def _price_label(kind: str) -> str:
    return "Подписка на месяц" if kind == "subscription" else "Разовый подбор"


def _has_survey_payload(data: dict) -> bool:
    required_fields = {"age", "gender", "event", "relation", "budget"}
    return required_fields.issubset(data.keys())


def _format_subscription_until(subscription) -> str:
    if not subscription or not subscription.expires_at:
        return "—"
    return subscription.expires_at.strftime("%d.%m.%Y %H:%M UTC")


def _build_cabinet_text(bot_message: Message, user_id: int, username: str | None) -> str:
    container = bot_message.bot.container
    payment_service = container.payment_service
    repository = container.repository
    user = repository.get_or_create_user(user_id, username)
    access = payment_service.get_access_state(user_id)
    paid_count = repository.count_paid_payments(user)
    access_label = "Активен ✅" if access.has_subscription or access.paid_requests_left > 0 else "Не активен"
    subscription = repository.get_active_subscription(user)
    return texts.CABINET_TEMPLATE.format(
        access=access_label,
        subscription_until=_format_subscription_until(subscription),
        left=access.paid_requests_left,
        paid=paid_count,
        one_time_rub=payment_service.get_one_time_price_rub(),
        subscription_rub=payment_service.get_subscription_price_rub(),
        one_time_stars=payment_service.get_one_time_price_stars(),
        subscription_stars=payment_service.get_subscription_price_stars(),
    )


async def _send_cabinet_as_new_message(message: Message, state: FSMContext, user_id: int, username: str | None) -> None:
    sent = await message.answer(_build_cabinet_text(message, user_id, username), reply_markup=cabinet_keyboard())
    await state.update_data(screen_message_id=sent.message_id)


async def _render_screen(
    *,
    state: FSMContext,
    source_message: Message,
    text: str,
    reply_markup=None,
) -> None:
    data = await state.get_data()
    screen_message_id = data.get("screen_message_id")
    bot = source_message.bot
    chat_id = source_message.chat.id
    if screen_message_id:
        try:
            await bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=screen_message_id,
                reply_markup=reply_markup,
            )
            return
        except TelegramBadRequest as exc:
            # Не создаем дублирующее сообщение, если текст не изменился.
            if "message is not modified" in str(exc).lower():
                return
            pass
    sent = await source_message.answer(text, reply_markup=reply_markup)
    await state.update_data(screen_message_id=sent.message_id)


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    container = message.bot.container
    repository = container.repository
    user = repository.get_or_create_user(message.from_user.id, message.from_user.username)

    if not repository.is_intro_seen(user):
        await message.answer(texts.INTRO_MESSAGE)
        repository.mark_intro_seen(user)
        await asyncio.sleep(5)

    await state.set_state(SurveyStates.choosing_mode)
    await _render_screen(state=state, source_message=message, text=texts.MAIN_MENU, reply_markup=main_menu_keyboard())


@router.message(F.text == "/menu")
async def menu(message: Message, state: FSMContext) -> None:
    await state.set_state(SurveyStates.choosing_mode)
    await _render_screen(state=state, source_message=message, text=texts.MAIN_MENU, reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "menu:home")
async def menu_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SurveyStates.choosing_mode)
    await _render_screen(
        state=state,
        source_message=callback.message,
        text=texts.MAIN_MENU,
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:cabinet")
async def menu_cabinet(callback: CallbackQuery, state: FSMContext) -> None:
    text = _build_cabinet_text(callback.message, callback.from_user.id, callback.from_user.username)
    await _render_screen(state=state, source_message=callback.message, text=text, reply_markup=cabinet_keyboard())
    await callback.answer()


@router.callback_query(F.data == "buy:one_time")
async def buy_one_time_from_cabinet(callback: CallbackQuery, state: FSMContext) -> None:
    await _render_screen(
        state=state,
        source_message=callback.message,
        text=texts.PAYMENT_CHOICE_ONE_TIME,
        reply_markup=payment_choice_keyboard("one_time"),
    )
    await callback.answer()


@router.callback_query(F.data == "buy:subscription")
async def buy_subscription_from_cabinet(callback: CallbackQuery, state: FSMContext) -> None:
    await _render_screen(
        state=state,
        source_message=callback.message,
        text=texts.PAYMENT_CHOICE_SUBSCRIPTION,
        reply_markup=payment_choice_keyboard("subscription"),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:start")
async def menu_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SurveyStates.choosing_mode)
    await _render_screen(state=state, source_message=callback.message, text=texts.START_PICK_MODE, reply_markup=mode_keyboard())
    await callback.answer()


@router.callback_query(SurveyStates.choosing_mode, F.data.startswith("mode:"))
async def choose_mode(callback: CallbackQuery, state: FSMContext) -> None:
    mode = callback.data.split(":")[1]
    await state.update_data(mode=mode)
    await state.set_state(SurveyStates.age)
    hint = texts.QUICK_MODE_HINT if mode == "quick" else texts.SMART_MODE_HINT
    await _render_screen(state=state, source_message=callback.message, text=f"{hint}\n\n{texts.ASK_AGE}")
    await callback.answer()


@router.message(SurveyStates.age)
async def input_age(message: Message, state: FSMContext) -> None:
    if not message.text or not message.text.isdigit():
        await _render_screen(state=state, source_message=message, text=texts.AGE_ERROR)
        await _delete_user_input(message)
        return
    await state.update_data(age=int(message.text))
    await state.set_state(SurveyStates.gender)
    await _render_screen(state=state, source_message=message, text=texts.ASK_GENDER, reply_markup=gender_keyboard())
    await _delete_user_input(message)


@router.callback_query(SurveyStates.gender, F.data.startswith("gender:"))
async def input_gender(callback: CallbackQuery, state: FSMContext) -> None:
    gender = callback.data.split(":", 1)[1]
    if gender not in GENDER_ALLOWED:
        await _render_screen(state=state, source_message=callback.message, text=texts.COMMON_ERROR)
        await callback.answer()
        return
    await state.update_data(gender=gender)
    await state.set_state(SurveyStates.event)
    await _render_screen(state=state, source_message=callback.message, text=texts.ASK_EVENT, reply_markup=event_keyboard())
    await callback.answer()


@router.callback_query(SurveyStates.event, F.data.startswith("event:"))
async def input_event(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(event=callback.data.split(":")[1])
    await state.set_state(SurveyStates.relation)
    await _render_screen(state=state, source_message=callback.message, text=texts.ASK_RELATION, reply_markup=relation_keyboard())
    await callback.answer()


@router.callback_query(SurveyStates.relation, F.data.startswith("relation:"))
async def input_relation(callback: CallbackQuery, state: FSMContext) -> None:
    relation_value = callback.data.split(":")[1]
    if relation_value == "other":
        await state.set_state(SurveyStates.custom_relation)
        await _render_screen(state=state, source_message=callback.message, text=texts.ASK_CUSTOM_RELATION)
        await callback.answer()
        return
    await state.update_data(relation=relation_value)
    await state.set_state(SurveyStates.budget)
    await _render_screen(state=state, source_message=callback.message, text=texts.ASK_BUDGET, reply_markup=budget_keyboard())
    await callback.answer()


@router.message(SurveyStates.custom_relation)
async def custom_relation(message: Message, state: FSMContext) -> None:
    relation_text = (message.text or "").strip()
    if not relation_text:
        await _render_screen(state=state, source_message=message, text=texts.COMMON_ERROR)
        await _delete_user_input(message)
        return
    await state.update_data(relation=relation_text)
    await state.set_state(SurveyStates.budget)
    await _render_screen(state=state, source_message=message, text=texts.ASK_BUDGET, reply_markup=budget_keyboard())
    await _delete_user_input(message)


@router.callback_query(SurveyStates.budget, F.data.startswith("budget:"))
async def budget(callback: CallbackQuery, state: FSMContext) -> None:
    budget_value = callback.data.split(":")[1]
    if budget_value == "custom":
        await state.set_state(SurveyStates.custom_budget)
        await _render_screen(state=state, source_message=callback.message, text=texts.ASK_CUSTOM_BUDGET)
    else:
        await state.update_data(budget=normalize_budget(budget_value), budget_min=budget_floor(budget_value))
        await _ask_after_budget(callback.message, state)
    await callback.answer()


@router.message(SurveyStates.custom_budget)
async def custom_budget(message: Message, state: FSMContext) -> None:
    if not message.text or not message.text.isdigit():
        await _render_screen(state=state, source_message=message, text=texts.CUSTOM_BUDGET_ERROR)
        await _delete_user_input(message)
        return
    await state.update_data(budget=normalize_budget(message.text), budget_min=budget_floor(message.text))
    await _ask_after_budget(message, state)
    await _delete_user_input(message)


async def _ask_after_budget(source_message: Message, state: FSMContext) -> None:
    """Быстрый подбор — без фото, сразу к увлечениям; умный — сначала фото."""
    data = await state.get_data()
    if data.get("mode") == "quick":
        await state.set_state(SurveyStates.hobbies)
        await _render_screen(state=state, source_message=source_message, text=texts.ASK_HOBBIES)
        return
    await state.set_state(SurveyStates.photos)
    await _render_screen(state=state, source_message=source_message, text=texts.ASK_PHOTOS)
    await source_message.answer(texts.PHOTO_KEYBOARD_HINT, reply_markup=PHOTO_REPLY_KEYBOARD)


async def _replace_photo_status(message: Message, state: FSMContext, text: str) -> None:
    # Новое сообщение под фото вместо правки старого: иначе «Фото сохранено» оказывается выше самого фото.
    data = await state.get_data()
    previous = data.get("photo_status_message_id")
    if previous:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=previous)
        except TelegramBadRequest:
            pass
    sent = await message.answer(text)
    await state.update_data(photo_status_message_id=sent.message_id)


@router.message(SurveyStates.photos)
async def collect_photos(message: Message, state: FSMContext) -> None:
    async with PHOTO_STATE_LOCKS[message.from_user.id]:
        data = await state.get_data()
        photos_count = int(data.get("photos_count", 0))
        photo_urls = data.get("photo_urls", [])
        if not isinstance(photo_urls, list):
            photo_urls = []

        if message.photo:
            if photos_count >= 6:
                await _replace_photo_status(message, state, texts.PHOTO_LIMIT)
                return
            photos_count += 1
            try:
                best_photo = message.photo[-1]
                tg_file = await message.bot.get_file(best_photo.file_id)
                if tg_file.file_path:
                    photo_url = _build_telegram_file_url(message.bot.token, tg_file.file_path)
                    if photo_url not in photo_urls and len(photo_urls) < 6:
                        photo_urls.append(photo_url)
            except Exception as exc:
                logger.warning("Не удалось получить путь к фото user_id=%s err=%s", message.from_user.id, exc)
            await state.update_data(photos_count=photos_count, photo_urls=photo_urls)
            await _replace_photo_status(message, state, texts.PHOTO_ADDED.format(count=photos_count))
            return

        if (message.text or "").strip().lower() not in {"пропустить", "готово"}:
            await _render_screen(state=state, source_message=message, text=texts.PHOTO_ERROR)
            await _delete_user_input(message)
            return

        await _delete_user_input(message)
        if not photos_count:
            await message.answer(texts.PHOTO_SKIPPED)
        await state.set_state(SurveyStates.hobbies)
        await message.answer(texts.ASK_HOBBIES, reply_markup=ReplyKeyboardRemove())


@router.message(SurveyStates.hobbies)
async def hobbies(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("pending_reco"):
        logger.info("Игнор сообщения о хобби до оплаты user_id=%s", message.from_user.id)
        await _delete_user_input(message)
        await message.answer("Ожидаю оплату. После успешного платежа сразу продолжу подбор.")
        return
    raw_hobbies = (message.text or "").strip()
    hobbies_value = "" if raw_hobbies.lower().strip(".!") in HOBBIES_SKIP_WORDS else raw_hobbies
    if not hobbies_value:
        await message.answer(texts.HOBBIES_SKIPPED)
    await state.update_data(hobbies=hobbies_value)
    await _delete_user_input(message)
    await _emit_recommendations(message, state)


@router.message(
    SurveyStates.choosing_mode,
    SurveyStates.gender,
    SurveyStates.event,
    SurveyStates.relation,
    SurveyStates.budget,
)
async def drop_text_during_inline_steps(message: Message, state: FSMContext) -> None:
    await _delete_user_input(message)
    data = await state.get_data()
    if data.get("screen_message_id"):
        return
    await _render_screen(
        state=state,
        source_message=message,
        text=texts.COMMON_ERROR,
    )


async def _emit_recommendations(message: Message, state: FSMContext, user: User | None = None) -> None:
    # После нажатия inline-кнопки message — сообщение бота, его from_user — сам бот.
    user = user or message.from_user
    data = await state.get_data()
    container = message.bot.container
    payment_service = container.payment_service
    repository = container.repository
    user_id = user.id
    logger.info("Запуск подбора user_id=%s", user_id)
    if not _has_survey_payload(data):
        logger.warning("Потеряны данные анкеты user_id=%s data=%s", user_id, data)
        await message.answer("Активной анкеты нет — открыл личный кабинет. Начните новый подбор.")
        await state.set_state(SurveyStates.choosing_mode)
        await _render_screen(
            state=state,
            source_message=message,
            text=_build_cabinet_text(message, user_id, user.username),
            reply_markup=cabinet_keyboard(),
        )
        return
    access_state = payment_service.get_access_state(user_id)
    paid_for_current_request = bool(data.get("paid_for_current_request"))
    has_stored_one_time = access_state.paid_requests_left > 0
    # Доступ открывается, если активна подписка, есть оплаченный текущий платеж
    # или в БД уже есть неиспользованный разовый запрос.
    if not access_state.has_subscription and not paid_for_current_request and not has_stored_one_time:
        await state.set_state(SurveyStates.hobbies)
        await message.answer(texts.PAYWALL, reply_markup=payment_choice_keyboard("one_time"))
        await state.update_data(pending_reco=True, paid_for_current_request=False)
        repository.get_or_create_user(user_id, user.username)
        logger.info("Показан paywall user_id=%s", user_id)
        return

    recommendation_service = container.recommendation_service
    gpt_service = container.gpt_service
    photo_insights = ""
    photo_urls = data.get("photo_urls", [])
    if isinstance(photo_urls, list) and photo_urls:
        try:
            photo_insights = await gpt_service.analyze_photos(
                [str(url) for url in photo_urls if str(url).strip()],
                context_note=(
                    f"Возраст: {data['age']}, повод: {event_label(data['event'])}, "
                    f"кто это для дарителя: {relation_label(data['relation'])}"
                ),
            )
            logger.info("Готов анализ фото user_id=%s len=%s", user_id, len(photo_insights))
        except Exception as exc:
            logger.warning("Анализ фото не удался user_id=%s err=%s", user_id, exc)
    context = RecommendationContext(
        mode=data.get("mode", "extended"),
        age=int(data["age"]),
        gender=data["gender"],
        event=data["event"],
        relation=data["relation"],
        budget=int(data["budget"]),
        budget_min=int(data.get("budget_min") or 0),
        hobbies=data.get("hobbies", ""),
        photos_count=int(data.get("photos_count", 0)),
        photo_insights=photo_insights,
    )
    await message.answer(texts.GENERATING)
    try:
        items = await recommendation_service.get_recommendations(context)
    except RecommendationUnavailable:
        await message.answer(texts.RECO_UNAVAILABLE, reply_markup=retry_recommendation_keyboard())
        return
    if not items:
        await message.answer(
            "Не удалось собрать идеи подарков в этом бюджете. Запрос не списан.",
            reply_markup=retry_recommendation_keyboard(),
        )
        return
    item_ids = _save_recommendations(repository, user, context, items)
    if len(items) < 6:
        await message.answer(
            "Нашел меньше вариантов, чем обычно: показываю только идеи, которые попали в ваш бюджет."
        )
    await message.answer("🎯 Основная идея подарка:")
    await _send_item(message, items[0], item_ids[0])
    if len(items) > 1:
        await message.answer("✨ Еще идеи:")
        await message.answer(texts.BUDGET_NOTE)
    for item, item_id in list(zip(items, item_ids))[1:6]:
        await _send_item(message, item, item_id)
    if data.get("mode") == "quick":
        await message.answer(texts.UPSELL_QUICK)
    await message.answer(texts.RESULT_TRIGGER)
    payment_service.consume_request(user_id)
    logger.info("Подбор завершен user_id=%s items=%s", user_id, len(items))
    await state.clear()


def _save_recommendations(repository, user: User, context: RecommendationContext, items: list[dict]) -> list[int | None]:
    """Сохраняем выдачу, чтобы у идей были id для оценки. Ошибка БД не должна ломать показ идей."""
    try:
        db_user = repository.get_or_create_user(user.id, user.username)
        request = repository.create_request(
            db_user,
            {
                "mode": context.mode,
                "age": context.age,
                "gender": context.gender,
                "event": context.event,
                "relation": context.relation,
                "budget": context.budget,
                "hobbies": context.hobbies,
                "photos_count": context.photos_count,
            },
        )
        return [saved.id for saved in repository.save_items(request, items)]
    except Exception as exc:
        logger.warning("Не удалось сохранить выдачу user_id=%s err=%s", user.id, exc)
        return [None] * len(items)


async def _send_item(message: Message, item: dict, item_id: int | None = None) -> None:
    links = item.get("links") or []
    markup = product_links_keyboard(links[0] if links else None, item_id)
    text = texts.ITEM_TEMPLATE.format(
        name=item.get("name", "Подарок"),
        reason=item.get("reason", "Подходит по вашему запросу."),
    )
    text += texts.ITEM_LINKS_HINT if links and markup else texts.ITEM_NO_LINKS_HINT
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith(FEEDBACK_PREFIX))
async def item_feedback(callback: CallbackQuery) -> None:
    payload = callback.data[len(FEEDBACK_PREFIX) :]
    if payload == "done":
        await callback.answer(texts.FEEDBACK_ALREADY)
        return
    item_id, _, vote_name = payload.partition(":")
    if not item_id.isdigit() or vote_name not in ("up", "down"):
        await callback.answer()
        return
    vote = 1 if vote_name == "up" else -1
    repository = callback.bot.container.repository
    if not repository.set_feedback(int(item_id), callback.from_user.id, vote):
        await callback.answer(texts.FEEDBACK_EXPIRED)
        return
    logger.info("Оценка идеи item_id=%s user_id=%s vote=%s", item_id, callback.from_user.id, vote)
    await callback.answer(texts.FEEDBACK_THANKS)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=feedback_given_keyboard(callback.message.reply_markup, vote)
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "reco:retry")
async def retry_recommendation(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _emit_recommendations(callback.message, state, callback.from_user)


@router.callback_query(F.data.startswith("pay:stars:"))
async def pay_stars(callback: CallbackQuery, state: FSMContext) -> None:
    container = callback.message.bot.container
    payment_service = container.payment_service
    repository = container.repository
    user = repository.get_or_create_user(callback.from_user.id, callback.from_user.username)
    kind = callback.data.split(":")[2]
    logger.info("Создание инвойса Stars user_id=%s", callback.from_user.id)
    if kind == "subscription":
        invoice = await payment_service.create_subscription_payment(callback.from_user.id, "stars")
    else:
        invoice = await payment_service.create_one_time_payment(callback.from_user.id, "stars")
    repository.create_or_get_payment(
        user=user,
        provider="stars",
        kind=kind,
        amount_rub=payment_service.get_subscription_price("stars") if kind == "subscription" else payment_service.get_one_time_price("stars"),
        provider_payment_id=invoice["payload"],
        idempotency_key=invoice["payload"],
    )
    await _render_screen(state=state, source_message=callback.message, text="Открываю оплату через Telegram Stars...")
    await callback.message.answer_invoice(
        title=invoice["title"],
        description=invoice["description"],
        payload=invoice["payload"],
        currency=invoice["currency"],
        prices=[LabeledPrice(label=_price_label(kind), amount=int(invoice["amount"]))],
        provider_token=invoice["provider_token"],
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery) -> None:
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, state: FSMContext) -> None:
    container = message.bot.container
    payment_service = container.payment_service
    repository = container.repository
    payload = message.successful_payment.invoice_payload
    kind = _payment_kind_from_marker(payload)
    logger.info("Получен successful_payment user_id=%s payload=%s", message.from_user.id, payload)
    repository.mark_payment_paid(payload)
    if kind == "subscription":
        payment_service.grant_subscription(message.from_user.id)
        await state.update_data(paid_for_current_request=False)
        await message.answer(texts.PAYMENT_SUCCESS_SUBSCRIPTION)
    else:
        payment_service.grant_one_time_request(message.from_user.id)
        await state.update_data(paid_for_current_request=True)
        await message.answer(texts.PAYMENT_SUCCESS_ONE_TIME)
    await asyncio.sleep(0.5)
    await _resume_after_payment(message, state, message.from_user)


async def _resume_after_payment(message: Message, state: FSMContext, user: User) -> None:
    """Если оплату показали посреди подбора — продолжаем его с уже заполненной анкетой."""
    data = await state.get_data()
    await state.update_data(pending_reco=False)
    if data.get("pending_reco") and _has_survey_payload(data):
        logger.info("Продолжаю подбор после оплаты user_id=%s", user.id)
        await _emit_recommendations(message, state, user)
        return
    await state.set_state(SurveyStates.choosing_mode)
    await _send_cabinet_as_new_message(message, state, user.id, user.username)


@router.callback_query(
    (F.data == "pay:yookassa:one_time") | (F.data == "pay:yookassa:subscription")
)
async def pay_yookassa(callback: CallbackQuery, state: FSMContext) -> None:
    container = callback.message.bot.container
    payment_service = container.payment_service
    repository = container.repository
    user = repository.get_or_create_user(callback.from_user.id, callback.from_user.username)
    kind = callback.data.split(":")[2]
    logger.info("Создание оплаты YooKassa user_id=%s", callback.from_user.id)
    if kind == "subscription":
        payment = await payment_service.create_subscription_payment(callback.from_user.id, "yookassa")
    else:
        payment = await payment_service.create_one_time_payment(callback.from_user.id, "yookassa")
    payment_id = payment["provider_payment_id"]
    repository.create_or_get_payment(
        user=user,
        provider="yookassa",
        kind=kind,
        amount_rub=payment_service.get_subscription_price("yookassa") if kind == "subscription" else payment_service.get_one_time_price("yookassa"),
        provider_payment_id=payment_id,
        idempotency_key=payment_id,
    )
    await callback.message.answer(
        texts.YOOKASSA_READY,
        reply_markup=yookassa_check_keyboard(payment_id, payment["url"]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("paycheck:"))
async def check_yookassa(callback: CallbackQuery, state: FSMContext) -> None:
    container = callback.message.bot.container
    payment_service = container.payment_service
    repository = container.repository
    payment_id = callback.data.split(":", 1)[1]
    kind = _payment_kind_from_marker(payment_id)
    logger.info("Проверка платежа YooKassa user_id=%s payment_id=%s", callback.from_user.id, payment_id)
    repository.mark_payment_paid(payment_id)
    if kind == "subscription":
        payment_service.grant_subscription(callback.from_user.id)
        await state.update_data(paid_for_current_request=False)
        await callback.message.answer(texts.PAYMENT_SUCCESS_SUBSCRIPTION)
    else:
        payment_service.grant_one_time_request(callback.from_user.id)
        await state.update_data(paid_for_current_request=True)
        await callback.message.answer(texts.PAYMENT_SUCCESS_ONE_TIME)
    await callback.answer()
    await asyncio.sleep(0.5)
    await _resume_after_payment(callback.message, state, callback.from_user)
