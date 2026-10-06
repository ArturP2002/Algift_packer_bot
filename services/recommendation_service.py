from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import logging
import re

from services.cache_service import CacheService
from services.gpt_service import GPTService
from services.product_service import ProductService, market_label

# Берем идей с запасом: часть отсеется по цене или фото, показываем до 6.
_IDEAS_REQUESTED = 8
_IDEAS_SHOWN = 6
_MAX_PER_CATEGORY = 1
_CANDIDATES_PER_IDEA = 8
_MAX_CHOSEN_OFFERS = 3
_CATALOG_RETRY_ROUNDS = 3
# Лимит сообщения Telegram 4096 символов; запас — на название идеи и подсказку под текстом.
_REASON_LIMIT = 3700

# Варианты одной линейки: Slim и Pro — разные товары, нельзя подменять.
_VARIANT_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"slim", "pro", "digital", "disc", "disk", "standard", "fat"}),
    frozenset({"plus", "max", "mini", "ultra", "air", "se", "lite", "neo"}),
    frozenset({"flip", "charge", "clip", "go", "pulse", "boombox"}),
)

# Один тип товара под разными category у модели («кофемашина» / «кухня» / «бытовая техника»).
_PRODUCT_TYPE_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("кофе", ("кофемаш", "кофевар", "кофемолн", "кофе")),
    ("колонка", ("колонк", "акустик", "саундбар", "speaker")),
    ("наушники", ("наушн", "гарнитур", "earbuds", "airpods", "buds")),
    ("консоль", ("playstation", "xbox", "nintendo", "приставк", "консол", "ps5", "ps4")),
    ("проектор", ("проектор", "projector", "infocus")),
    ("планшет", ("планшет", "ipad", "tablet", "matepad")),
    ("пылесос", ("пылесос", "робот-пылесос")),
    ("блендер", ("блендер", "миксер", "комбайн")),
    ("часы", ("часов", "watch", "smartwatch")),
    ("ноутбук", ("ноутбук", "laptop", "macbook")),
    ("книга", ("книг", "роман", "детектив")),
    ("парфюм", ("парфюм", "духи", "туалетн", "одеколон")),
    ("фотоаппарат", ("фотоаппарат", "камер", "camera", "instax")),
    ("фен", ("стайлер", "выпрямител", "плойк", "фен для волос")),
)

_EVENT_LABELS = {
    "birthday": "день рождения",
    "new_year": "Новый год",
    "march8": "8 марта",
    "other": "без особого повода",
}
_RELATION_LABELS = {
    "girlfriend": "девушка",
    "mother": "мама",
    "father": "папа",
    "daughter": "дочь",
    "friend": "друг",
    "husband": "муж",
    "wife": "жена",
}
_GENDER_LABELS = {"женский": "женщина", "мужской": "мужчина"}

_IDEAS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ideas"],
    "properties": {
        "ideas": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "pitch", "category", "keywords", "price_min", "price_max"],
                "properties": {
                    "name": {"type": "string"},
                    "pitch": {"type": "string"},
                    "category": {"type": "string"},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "price_min": {"type": "integer"},
                    "price_max": {"type": "integer"},
                },
            },
        }
    },
}

_SELECTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ideas"],
    "properties": {
        "ideas": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "idea_index",
                    "offer_ids",
                    "why_for_person",
                    "occasion_fit",
                    "practical_value",
                    "presentation_tip",
                ],
                "properties": {
                    "idea_index": {"type": "integer"},
                    "offer_ids": {"type": "array", "items": {"type": "string"}},
                    "why_for_person": {"type": "string"},
                    "occasion_fit": {"type": "string"},
                    "practical_value": {"type": "string"},
                    "presentation_tip": {"type": "string"},
                },
            },
        }
    },
}

_IDEAS_INSTRUCTIONS = f"""Ты — внимательный консультант по подаркам. Предложи ровно {_IDEAS_REQUESTED} идей подарков для человека из профиля.

Правила:
- Только физические товары, которые реально есть в нашем каталоге (см. блок «Ориентиры каталога»). Не предлагай бренды и типы товаров, которых там нет. Предпочитай названия, близкие к примерам из ориентиров.
- Каждая идея должна находиться в каталоге по keywords. Если не уверен, что товар есть — выбери другую идею из ориентиров.
- price_min и price_max — реальная рыночная цена товара в рублях. Не подгоняй её под бюджет: если идея не помещается в бюджет, замени её другой.
- Учитывай возраст и статус получателя: ребёнку/подростку — возрастные товары; взрослому — не детские. Для пары/жены/мужа — уместные по отношениям подарки.
- Разные бюджеты = разные классы товаров, а не та же модель дороже/дешевле:
  · 1–3 тыс. ₽ — мелкие полезные вещи, книги, уход, аксессуары начального уровня;
  · 3–5 тыс. ₽ — средний сегмент гаджетов/ухода/игр;
  · 5–10 тыс. ₽ — заметные гаджеты и наборы;
  · 10–20+ тыс. ₽ — премиальные или крупные вещи.
  Не предлагай «ту же колонку / те же наушники другого поколения» только из‑за другого бюджета.
- Состав подборки: опирайся ТОЛЬКО на факты из профиля. Если увлечения указаны — минимум 2-3 идеи прямо по ним (дословно из списка, без «похожих» тем). Если увлечения НЕ указаны — не выдумывай хобби, подбирай по возрасту, отношениям, поводу и бюджету (практичная вещь, «вау», уют). Все идеи — разных категорий и типов товаров: не больше {_MAX_PER_CATEGORY} идеи одной категории. Три кофемашины или две колонки в одной выдаче — недопустимо.
- Увлечения — закрытый список. Пиши и подбирай ТОЛЬКО то, что даритель указал дословно. Запрещено добавлять, заменять и «додумывать» интересы: хоккей ≠ фильмы/кино; рыбалка ≠ готовка/кухня; машины ≠ гаджеты «для дома» без связи с авто. Нельзя в pitch писать «любит фильмы / готовить / музыку», если этого нет в профиле.
- category — одно-два слова: «аудио», «настольные игры», «уход за собой». Для похожих товаров используй одну и ту же category.
- name — обязательно тип товара + бренд/модель словами из каталога: «Проектор InFocus …», «Планшет HUAWEI …», «Портативная колонка JBL Flip 6». Нельзя название из одного бренда/модели без типа («InFocus IN0026SL», «MatePad Mini»).
- keywords — 2 запроса для поиска, по 2-4 слова. Оба обязаны содержать тип товара. Первый — точный (тип + бренд/модель), второй — чуть общий, но всё ещё с типом («проектор infocus», затем «проектор infocus in0026sl» или «портативный проектор»). Нельзя второй запрос без типа («для блога», «гаджет»). Тип в keywords обязан совпадать с типом в name.
- pitch — 1-2 предложения про ЭТУ же модель из name. Если цитируешь увлечения («вы написали, что…»), повторяй их ДОСЛОВНО из профиля — без синонимов и без новых тем. Можно связать товар с возрастом, отношениями или поводом, не приписывая человеку чужие хобби. Запрещено хвалить товар абстрактно («отличный подарок», «порадует любого») без привязки к фактам профиля.
  Хорошо (профиль «хоккей, рыбалка»): «Вы написали, что он увлекается хоккеем — большой экран удобен для просмотра матчей».
  Плохо: «Вы написали, что он любит фильмы» или «увлекается кулинарией», если в профиле этого нет.
- Внутри одной идеи name, keywords и pitch обязаны описывать один и тот же тип и бренд. Смешивать проектор и планшет, колонку и наушники — запрещено.
- Если есть наблюдения по фото — это сигналы о стиле и интересах. Не предлагай то, что у человека уже есть на фото; предлагай то, что дополнит образ жизни.
- Если в профиле есть список «не предлагай снова» — избегай этих товаров, брендов и близких аналогов той же линейки.
- Если есть блок «Описание от дарителя» — это главный источник фактов; опирайся на него в первую очередь."""

_SELECTION_INSTRUCTIONS = f"""Ты — эксперт по подаркам. Тебе дан профиль получателя и для каждой идеи — список реальных товаров из каталога.

Для каждой идеи верни один объект с ее idea_index:
- Источник истины — список «Товары». Поле «Черновик идеи» может быть неточным: если оно противоречит списку товаров, игнорируй черновик.
- offer_ids — до {_MAX_CHOSEN_OFFERS} id ТОЛЬКО из «Товары» этой же идеи. Тип товара должен совпадать с названием идеи (проектор ≠ планшет, колонка ≠ наушники). Модель/вариант тоже (Slim ≠ Pro). Если подходящих нет — пустой список. Чужие idea_index и товары других идей запрещены.
- why_for_person, occasion_fit, practical_value, presentation_tip — только про выбранные offer_ids: называй товар так же, как в каталоге. Запрещено упоминать другой тип, другой бренд или модель не из offer_ids.
- why_for_person — 2-3 предложения. Ссылайся ТОЛЬКО на факты из профиля. Увлечения цитируй ДОСЛОВНО (как в блоке «Разрешённые увлечения»). Запрещено придумывать, подменять и расширять интересы: нельзя писать про фильмы/кино, готовку/кулинарию, музыку, спорт и т.п., если этого нет в профиле. Если товар слабо связан с указанными увлечениями — объясни через повод, возраст или отношения, НЕ выдумывая хобби под товар. Формулировки «вы написали / вы указали» допустимы только с дословными фактами профиля.
- occasion_fit — 1 предложение, связанное с поводом из профиля.
- practical_value — 1 предложение про использование именно этого товара. Не приписывай человеку новые увлечения ради связки с товаром.
- presentation_tip — 1 короткое предложение про вручение именно этого товара.

Обращайся к дарителю на «вы», живым языком, без канцелярита. Цену не упоминай."""


def event_label(event: str) -> str:
    return _EVENT_LABELS.get(event, event)


def relation_label(relation: str) -> str:
    return _RELATION_LABELS.get(relation, relation)


def _years(age: int) -> str:
    if age % 10 == 1 and age % 100 != 11:
        return "год"
    if age % 10 in (2, 3, 4) and age % 100 not in (12, 13, 14):
        return "года"
    return "лет"


def _rub(value: int) -> str:
    return f"{value:,}".replace(",", " ")


class RecommendationUnavailable(RuntimeError):
    """Модель не ответила — идей нет, запрос не должен списываться."""


@dataclass
class RecommendationContext:
    mode: str
    age: int
    gender: str
    event: str
    relation: str
    budget: int
    hobbies: str = ""
    photos_count: int = 0
    photo_insights: str = ""
    budget_min: int = 0
    exclude_names: list[str] = field(default_factory=list)
    freeform_profile: str = ""

    def price_window(self) -> tuple[int, int]:
        """Допустимая цена подарка: вся выбранная вилка бюджета плюс 10% сверху."""
        floor = self.budget_min or int(self.budget * 0.7)
        return max(1, floor), int(self.budget * 1.1)


class RecommendationService:
    _PHOTO_OBJECT_MARKERS: tuple[tuple[str, ...], ...] = (
        ("науш", "earbud", "headphone", "airpods"),
        ("ожерель", "кулон", "подвеск", "necklace", "pendant"),
        ("кольц", "ring"),
        ("браслет", "bracelet"),
        ("часы", "watch"),
        ("сумк", "bag", "handbag"),
        ("плать", "dress"),
        ("кроссов", "кед", "sneaker"),
        ("куртк", "пальт", "coat", "jacket"),
        ("смартфон", "телефон", "iphone", "phone"),
        ("ноутбук", "laptop", "macbook"),
    )
    _NON_MARKETPLACE_MARKERS: tuple[str, ...] = (
        "сертификат",
        "gift card",
        "курс",
        "обучени",
        "мастер-класс",
        "мастеркласс",
        "подписк",
        "впечатлен",
        "услуг",
        "поездк",
        "путешеств",
        "билет",
        "концерт",
        "спа",
    )

    def __init__(
        self,
        gpt_service: GPTService,
        product_service: ProductService,
        cache_service: CacheService,
    ) -> None:
        self._gpt = gpt_service
        self._products = product_service
        self._cache = cache_service
        self._logger = logging.getLogger("gift_bot.recommendation")

    async def get_recommendations(self, context: RecommendationContext) -> list[dict[str, Any]]:
        payload = context.__dict__.copy()
        payload["exclude_names"] = sorted({str(name).strip().lower() for name in context.exclude_names if str(name).strip()})
        cache_key = self._cache.make_key(payload)
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        low, high = context.price_window()
        catalog_hints = self._products.catalog_hints(min_price=low, max_price=high)
        profile = self._describe_recipient(context, catalog_hints=catalog_hints)

        linked: list[dict[str, Any]] = []
        rejected_names: list[str] = []
        seen_names: set[str] = {name.lower() for name in context.exclude_names if name.strip()}

        for round_index in range(_CATALOG_RETRY_ROUNDS):
            needed = _IDEAS_SHOWN - len(linked)
            if needed <= 0:
                break
            prompt = profile
            if rejected_names or linked:
                prompt += "\n\n" + self._retry_prompt_block(linked, rejected_names, needed)
            try:
                result = await self._gpt.complete_json(
                    name="gift_ideas",
                    instructions=_IDEAS_INSTRUCTIONS,
                    prompt=prompt,
                    schema=_IDEAS_SCHEMA,
                    max_tokens=2500,
                )
            except Exception as exc:  # pragma: no cover - runtime/network guard
                if linked:
                    self._logger.warning("Добор идей не удался на раунде %s, продолжаю с %s: %s", round_index, len(linked), exc)
                    break
                self._logger.error("Модель недоступна, подбор не выполнен: %s", exc)
                raise RecommendationUnavailable(str(exc)) from exc

            raw_ideas = result.get("ideas") if isinstance(result.get("ideas"), list) else []
            self._logger.info("Раунд %s: модель вернула %s сырых идей", round_index + 1, len(raw_ideas))
            ideas = self._normalize_items(raw_ideas, context)
            ideas = self._post_filter(ideas, context.photo_insights, exclude_names=seen_names | {n.lower() for n in rejected_names})
            ideas = self._limit_diversity(ideas, already=linked)

            for item in ideas:
                name_key = item["name"].lower()
                if name_key in seen_names:
                    continue
                links = self._products.resolve_links(
                    item["keywords"], min_price=low, max_price=high, max_offers=_CANDIDATES_PER_IDEA
                )
                offers = (links[0].get("offers") if links else None) or []
                offers = self._filter_offers_for_idea(item["name"], offers, keywords=item.get("keywords"))
                if not offers:
                    self._logger.info("Отсеиваю вариант '%s': нет товара в каталоге", item["name"])
                    rejected_names.append(item["name"])
                    seen_names.add(name_key)
                    continue
                item["candidates"] = offers
                item["search_query"] = links[0]["keyword"]
                linked.append(item)
                seen_names.add(name_key)
                if len(linked) >= _IDEAS_SHOWN:
                    break

        candidates = linked[:_IDEAS_SHOWN]
        if not candidates:
            return []

        selection = await self._select_offers(profile, candidates)
        selected: list[dict[str, Any]] = []
        for index, item in enumerate(candidates):
            choice = selection.get(index) if selection is not None else None
            item_candidates = item.pop("candidates")
            search_query = item.pop("search_query")
            idea_name = item["name"]
            if choice is None:
                offers = item_candidates[:_MAX_CHOSEN_OFFERS]
            else:
                by_id = {f"i{index}o{position}": offer for position, offer in enumerate(item_candidates)}
                offers = [by_id[offer_id] for offer_id in choice["offer_ids"] if offer_id in by_id]
                # Пустой выбор модели при наличии кандидатов — берём топ из каталога, идею без ссылок не показываем.
                if not offers:
                    offers = item_candidates[:_MAX_CHOSEN_OFFERS]
            offers = self._filter_offers_for_idea(
                idea_name, offers, keywords=item.get("keywords"), limit=_MAX_CHOSEN_OFFERS
            )
            if not offers:
                self._logger.info("Отсеиваю вариант '%s': нет офферов после выбора", idea_name)
                continue
            primary = offers[0]
            # Название, ссылки и текст объяснения — всегда про один и тот же товар из каталога.
            item["name"] = self._display_name_from_offer(primary, fallback=idea_name)
            choice = self._align_narrative_with_offer(item, choice, primary, context=context)
            priced = [int(offer.get("price") or 0) for offer in offers if int(offer.get("price") or 0) > 0]
            item["price_estimate"] = min(priced, key=lambda value: abs(value - context.budget)) if priced else int(item["price_estimate"])
            price_note = self._price_note(item["price_estimate"], context.budget, live=True)
            item["links"] = [{"keyword": search_query, "offers": offers}]
            item["fits_budget"] = item["price_estimate"] <= context.budget
            item["reason"] = self._compose_reason(item, choice, price_note)
            selected.append(item)

        if selected:
            self._cache.set(cache_key, selected)
        return selected

    @staticmethod
    def _retry_prompt_block(accepted: list[dict[str, Any]], rejected: list[str], needed: int) -> str:
        lines = [
            f"Нужно ещё {needed} идей, которых ещё нет в принятом списке.",
            "Предлагай только товары, которые находятся в каталоге (см. ориентиры).",
            "Категории и типы товаров должны отличаться от уже принятых.",
        ]
        if accepted:
            lines.append("Уже приняты (не повторяй близкие аналоги и тот же тип товара):")
            for item in accepted:
                category = item.get("category") or "—"
                lines.append(f"- {item['name']} (category: {category})")
        if rejected:
            lines.append("Эти идеи не нашлись в каталоге — предложи другие:")
            lines.extend(f"- {name}" for name in rejected[-20:])
        return "\n".join(lines)

    async def _select_offers(
        self, profile: str, ideas: list[dict[str, Any]]
    ) -> dict[int, dict[str, Any]] | None:
        """Шаг 2: модель выбирает конкретные товары из найденных и объясняет выбор. None — шаг не удался."""
        blocks = []
        for index, item in enumerate(ideas):
            lines = [
                f"Идея {index}: {item['name']}",
                f"Черновик идеи (может быть неточным, не противоречь списку товаров): {item['pitch']}",
            ]
            if item["candidates"]:
                lines.append("Товары (источник истины):")
                for position, offer in enumerate(item["candidates"]):
                    store = market_label(str(offer.get("marketplace") or ""))
                    title = str(offer.get("title") or "")[:120]
                    lines.append(f"- i{index}o{position}: {title} — {_rub(int(offer.get('price') or 0))} ₽, {store}")
            else:
                lines.append("Товары: в каталоге нет, offer_ids — пустой список.")
            blocks.append("\n".join(lines))
        prompt = f"{profile}\n\n" + "\n\n".join(blocks)
        try:
            result = await self._gpt.complete_json(
                name="gift_selection",
                instructions=_SELECTION_INSTRUCTIONS,
                prompt=prompt,
                schema=_SELECTION_SCHEMA,
                max_tokens=3000,
                temperature=0.2,
            )
        except Exception as exc:  # pragma: no cover - runtime/network guard
            self._logger.warning("Шаг выбора товаров не удался, показываю результаты поиска: %s", exc)
            return None

        selection: dict[int, dict[str, Any]] = {}
        for entry in result.get("ideas") or []:
            if not isinstance(entry, dict):
                continue
            index = entry.get("idea_index")
            if not isinstance(index, int) or not 0 <= index < len(ideas) or index in selection:
                continue
            offer_ids: list[str] = []
            for offer_id in entry.get("offer_ids") or []:
                offer_id = str(offer_id).strip()
                if offer_id.startswith(f"i{index}o") and offer_id not in offer_ids:
                    offer_ids.append(offer_id)
            selection[index] = {
                "offer_ids": offer_ids[:_MAX_CHOSEN_OFFERS],
                **{
                    field: str(entry.get(field) or "").strip()
                    for field in ("why_for_person", "occasion_fit", "practical_value", "presentation_tip")
                },
            }
        return selection

    @staticmethod
    def _compose_reason(item: dict[str, Any], choice: dict[str, Any] | None, price_note: str) -> str:
        main = (choice or {}).get("why_for_person") or item["pitch"]
        sections = [main]
        if choice:
            for label, field in (
                ("🎉 Почему к поводу", "occasion_fit"),
                ("🛠 В жизни пригодится", "practical_value"),
                ("🎀 Как подарить", "presentation_tip"),
            ):
                if choice.get(field):
                    sections.append(f"{label}: {choice[field]}")
        # Если не помещается в сообщение, первым жертвуем советом по вручению, затем остальными пояснениями.
        while len(sections) > 1 and len("\n\n".join(sections + [price_note])) > _REASON_LIMIT:
            sections.pop()
        text = "\n\n".join(sections)
        if len(text) + len(price_note) + 2 > _REASON_LIMIT:
            text = text[: _REASON_LIMIT - len(price_note) - 3].rstrip() + "…"
        return f"{text}\n\n{price_note}"

    @staticmethod
    def _price_note(price: int, budget: int, *, live: bool, price_range: tuple[int, int] | None = None) -> str:
        label = "Цена в каталоге" if live else "Примерная цена"
        value = f"{_rub(price)} ₽"
        if price_range and not live:
            value = f"{_rub(price_range[0])}–{_rub(price_range[1])} ₽"
        if price <= budget:
            return f"💰 {label}: {value} (в рамках бюджета)"
        return f"💡 {label}: {value} (чуть выше бюджета)"

    @staticmethod
    def _describe_recipient(c: RecommendationContext, *, catalog_hints: str = "") -> str:
        low, high = c.price_window()
        gender = _GENDER_LABELS.get(c.gender, c.gender)
        lines = [
            f"Получатель: {relation_label(c.relation)}, {c.age} {_years(c.age)}, {gender}.",
            f"Повод: {event_label(c.event)}.",
        ]
        freeform = c.freeform_profile.strip()
        if freeform:
            lines.append(f"Описание от дарителя (главный источник фактов):\n{freeform}")
        hobbies = c.hobbies.strip().rstrip(".")
        if hobbies:
            lines.append(f"Разрешённые увлечения (дословно, закрытый список): «{hobbies}».")
            lines.append(
                "В текстах цитируй только этот список. Не добавляй фильмы, готовку, музыку и другие темы, "
                "которых здесь нет — даже если они «логичны» для выбранного товара."
            )
        else:
            lines.append("Увлечения: не указаны — не придумывай интересы и не ссылайся на выдуманные хобби.")
        if c.photo_insights.strip():
            lines.append(f"Наблюдения по фото:\n{c.photo_insights.strip()}")
        lines.append(f"Бюджет: {_rub(low)}–{_rub(c.budget)} ₽ (допустимо до {_rub(high)} ₽).")
        if c.exclude_names:
            lines.append("Не предлагай снова (недавние или отклонённые идеи):")
            lines.extend(f"- {name}" for name in c.exclude_names[:24])
        if catalog_hints.strip():
            lines.append(catalog_hints.strip())
        return "\n".join(lines)

    def _normalize_items(self, items: list[Any], context: RecommendationContext) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            pitch = str(item.get("pitch", "")).strip() or "Подходит по поводу, интересам и вашему бюджету."
            keywords = item.get("keywords")
            if not isinstance(keywords, list) or not keywords:
                keywords = [name]
            normalized.append(
                {
                    "name": name,
                    "pitch": pitch,
                    "category": str(item.get("category", "")).strip().lower(),
                    "keywords": [str(k).strip() for k in keywords if str(k).strip()],
                    "price_range": self._normalize_price_range(
                        [item.get("price_min"), item.get("price_max")], context.budget
                    ),
                }
            )
        return normalized

    def _limit_diversity(
        self, items: list[dict[str, Any]], *, already: list[dict[str, Any]] | None = None
    ) -> list[dict[str, Any]]:
        """Не больше одной идеи на category и на семейство типов товара (кофемашины и т.п.)."""
        category_counts: dict[str, int] = {}
        type_counts: dict[str, int] = {}
        for item in already or []:
            category = item.get("category") or ""
            if category:
                category_counts[category] = category_counts.get(category, 0) + 1
            product_type = self._product_type_family(item)
            if product_type:
                type_counts[product_type] = type_counts.get(product_type, 0) + 1
        kept: list[dict[str, Any]] = []
        for item in items:
            category = item.get("category") or ""
            if category and category_counts.get(category, 0) >= _MAX_PER_CATEGORY:
                self._logger.info(
                    "Отсеиваю вариант '%s': уже %s идеи категории «%s»",
                    item["name"],
                    _MAX_PER_CATEGORY,
                    category,
                )
                continue
            product_type = self._product_type_family(item)
            if product_type and type_counts.get(product_type, 0) >= _MAX_PER_CATEGORY:
                self._logger.info(
                    "Отсеиваю вариант '%s': уже есть идея типа «%s»",
                    item["name"],
                    product_type,
                )
                continue
            if category:
                category_counts[category] = category_counts.get(category, 0) + 1
            if product_type:
                type_counts[product_type] = type_counts.get(product_type, 0) + 1
            kept.append(item)
        return kept

    @classmethod
    def _family_from_text(cls, text: str) -> str:
        haystack = (text or "").lower()
        for family, markers in _PRODUCT_TYPE_FAMILIES:
            if any(marker in haystack for marker in markers):
                return family
        return ""

    @classmethod
    def _product_type_family(cls, item: dict[str, Any]) -> str:
        haystack_parts = [str(item.get("name", "")), str(item.get("category", ""))]
        keywords = item.get("keywords", [])
        if isinstance(keywords, list):
            haystack_parts.extend(str(k) for k in keywords)
        return cls._family_from_text(" ".join(haystack_parts))

    @classmethod
    def _filter_offers_for_idea(
        cls,
        idea_name: str,
        offers: list[dict[str, Any]],
        *,
        keywords: list[str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Оставляем только офферы того же типа/модификации, что идея (проектор≠планшет, Slim≠Pro)."""
        if not offers:
            return []
        idea_family = cls._family_from_text(idea_name)
        if not idea_family and keywords:
            idea_family = cls._family_from_text(" ".join(str(k) for k in keywords))
        pool: list[dict[str, Any]] = []
        for offer in offers:
            title = str(offer.get("title") or "")
            offer_family = cls._family_from_text(title)
            # Если тип идеи известен — чужой тип отбрасываем.
            if idea_family and offer_family and idea_family != offer_family:
                continue
            # Если у идеи тип не распознан, а у оффера распознан другой тип из keywords — тоже нет.
            if not idea_family and offer_family and keywords:
                kw_family = cls._family_from_text(" ".join(str(k) for k in keywords))
                if kw_family and kw_family != offer_family:
                    continue
            pool.append(offer)
        if not pool:
            return []

        idea_variants = cls._variant_tokens(idea_name)
        if idea_variants:
            matched: list[dict[str, Any]] = []
            for offer in pool:
                title = str(offer.get("title") or "")
                offer_variants = cls._variant_tokens(title)
                if offer_variants and cls._variants_conflict(idea_variants, offer_variants):
                    continue
                if offer_variants and not (idea_variants & offer_variants):
                    continue
                matched.append(offer)
            if not matched:
                return []
            pool = matched

        idea_tokens = set(re.findall(r"[a-zа-яё0-9]{3,}", idea_name.lower()))
        pool.sort(
            key=lambda offer: -sum(
                1 for token in idea_tokens if token in str(offer.get("title") or "").lower()
            )
        )
        if limit is not None:
            return pool[:limit]
        return pool

    def _align_narrative_with_offer(
        self,
        item: dict[str, Any],
        choice: dict[str, Any] | None,
        offer: dict[str, Any],
        *,
        context: RecommendationContext | None = None,
    ) -> dict[str, Any]:
        """Гарантирует, что текст объяснения про тот же товар, что в ссылке/заголовке."""
        offer_title = self._display_name_from_offer(offer, fallback=item["name"])
        offer_family = self._family_from_text(str(offer.get("title") or offer_title))
        offer_brands = self._latin_brands(str(offer.get("title") or offer_title))
        pitch = str(item.get("pitch") or "")
        pitch_family = self._family_from_text(pitch)
        pitch_brands = self._latin_brands(pitch)
        if (offer_family and pitch_family not in ("", offer_family)) or (
            offer_brands and pitch_brands and not (offer_brands & pitch_brands)
        ):
            item["pitch"] = self._safe_why_for_person(offer_title, context)
            self._logger.info(
                "Переписал pitch для '%s': исходный текст был про другой товар",
                offer_title,
            )

        if choice:
            narrative = " ".join(
                str(choice.get(field) or "")
                for field in ("why_for_person", "occasion_fit", "practical_value", "presentation_tip")
            )
            narrative_family = self._family_from_text(narrative)
            narrative_brands = self._latin_brands(narrative)
            type_mismatch = bool(offer_family and narrative_family and narrative_family != offer_family)
            brand_mismatch = bool(offer_brands and narrative_brands and not (offer_brands & narrative_brands))
            # В тексте есть чужой тип из известных семейств, которого нет у оффера.
            foreign_types = {
                family
                for family, markers in _PRODUCT_TYPE_FAMILIES
                if family != offer_family and any(marker in narrative.lower() for marker in markers)
            }
            hobby_mismatch = bool(
                context and self._narrative_invents_hobbies(narrative, context, offer_title=offer_title)
            )
            if type_mismatch or brand_mismatch or foreign_types or hobby_mismatch:
                self._logger.info(
                    "Сбрасываю текст выбора для '%s': несогласованность типа/бренда/увлечений",
                    offer_title,
                )
                choice = None

        if choice and context and self._narrative_invents_hobbies(
            str(choice.get("why_for_person") or ""), context, offer_title=offer_title
        ):
            choice = {
                **choice,
                "why_for_person": self._safe_why_for_person(offer_title, context),
            }

        if choice:
            return choice
        pitch_text = str(item.get("pitch") or "").strip()
        if context and (
            not pitch_text
            or self._narrative_invents_hobbies(pitch_text, context, offer_title=offer_title)
        ):
            why = self._safe_why_for_person(offer_title, context)
        else:
            why = pitch_text or self._safe_why_for_person(offer_title, context)
        return {
            "why_for_person": why,
            "occasion_fit": "Такой подарок уместен к поводу и покажет внимание к вкусам человека.",
            "practical_value": f"{offer_title} можно использовать регулярно в повседневной жизни.",
            "presentation_tip": "Вручите в красивой упаковке и коротко расскажите, почему выбрали именно это.",
        }

    # Маркеры типичных «додуманных» хобби: если их нет в профиле, а в тексте есть — текст врёт.
    _INVENTED_HOBBY_GROUPS: tuple[tuple[str, ...], ...] = (
        ("фильм", "кино", "сериал"),
        ("готовить", "готовит", "кулинар", "на кухне", "рецепт"),
        ("любит музык", "увлекается музык", "музыкальн"),
        ("танц", "хореограф"),
        ("йог", "медитац"),
        ("рисов", "живопис", "художеств"),
        ("огород", "цветник", "садовод"),
        ("вязан", "вышивк"),
    )

    @classmethod
    def _profile_hobby_blob(cls, context: RecommendationContext) -> str:
        return f"{context.hobbies} {context.freeform_profile} {context.photo_insights}".lower()

    @classmethod
    def _narrative_invents_hobbies(
        cls,
        text: str,
        context: RecommendationContext,
        *,
        offer_title: str = "",
    ) -> bool:
        """True, если в тексте появляются темы-увлечения, которых нет в профиле."""
        narrative = (text or "").lower()
        if not narrative:
            return False
        # Название товара не считаем «выдуманным хобби».
        title = (offer_title or "").lower()
        if title:
            narrative = narrative.replace(title, " ")
        blob = cls._profile_hobby_blob(context)
        claim_like = any(
            marker in narrative
            for marker in ("вы написали", "вы указали", "любит", "увлекается", "увлечение", "интересуется")
        )
        if not claim_like:
            return False
        for group in cls._INVENTED_HOBBY_GROUPS:
            if any(marker in narrative for marker in group) and not any(marker in blob for marker in group):
                return True
        return False

    @staticmethod
    def _safe_why_for_person(offer_title: str, context: RecommendationContext | None) -> str:
        if context and context.hobbies.strip():
            return (
                f"Вы указали интересы: {context.hobbies.strip()}. "
                f"{offer_title} — уместный вариант с учётом этих увлечений, возраста и повода."
            )
        if context and context.freeform_profile.strip():
            return (
                f"С учётом вашего описания получателя {offer_title} "
                f"будет практичным и уместным подарком к поводу."
            )
        return f"{offer_title} — практичный подарок с учётом возраста получателя и повода."

    @staticmethod
    def _latin_brands(text: str) -> set[str]:
        """Латинские токены бренда/модели длиной ≥3, без общих слов."""
        generic = {
            "pro", "air", "max", "mini", "plus", "ultra", "lite", "neo", "the", "and", "for", "gb", "tb",
            "wifi", "oled", "led", "usb", "rgb", "slim", "edition", "black", "white",
        }
        return {
            token
            for token in re.findall(r"[a-z][a-z0-9]{2,}", (text or "").lower())
            if token not in generic
        }

    @classmethod
    def _variant_tokens(cls, text: str) -> set[str]:
        tokens = set(re.findall(r"[a-zа-яё0-9]+", (text or "").lower()))
        known = {token for group in _VARIANT_GROUPS for token in group}
        return tokens & known

    @classmethod
    def _variants_conflict(cls, left: set[str], right: set[str]) -> bool:
        for group in _VARIANT_GROUPS:
            left_hit = left & group
            right_hit = right & group
            if left_hit and right_hit and left_hit != right_hit:
                return True
        return False

    @staticmethod
    def _display_name_from_offer(offer: dict[str, Any], *, fallback: str) -> str:
        title = str(offer.get("title") or "").strip()
        if not title:
            return fallback
        # Убираем хвост бандла после «+», чтобы в заголовке не было «+ Hogwarts Legacy».
        primary = re.split(r"\s+\+\s+", title, maxsplit=1)[0].strip()
        return primary[:120] or fallback

    def _post_filter(
        self,
        items: list[dict[str, Any]],
        photo_insights: str,
        *,
        exclude_names: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        blocked_terms = self._extract_blocked_terms_from_photo(photo_insights)
        excluded = {name.lower() for name in (exclude_names or set()) if name}
        kept: list[dict[str, Any]] = []
        for item in items:
            name = str(item.get("name", "")).strip()
            if name.lower() in excluded or self._matches_excluded_name(item, excluded):
                self._logger.info("Отсеиваю вариант '%s': уже предлагали или отклонили", name)
                continue
            if self._contains_blocked_photo_object(item, blocked_terms):
                self._logger.info("Отсеиваю вариант '%s': предмет уже виден на фото", item.get("name", "gift"))
                continue
            if self._is_non_marketplace_idea(item):
                self._logger.info("Отсеиваю вариант '%s': не товар маркетплейса", item.get("name", "gift"))
                continue
            name_family = self._family_from_text(name)
            pitch_family = self._family_from_text(str(item.get("pitch") or ""))
            if name_family and pitch_family and name_family != pitch_family:
                item["pitch"] = (
                    f"{name} хорошо дополняет интересы получателя и будет уместным подарком к поводу."
                )
                self._logger.info("Исправил pitch для '%s': тип в тексте не совпадал с названием", name)
            min_price, max_price = item["price_range"]
            item["price_estimate"] = int((min_price + max_price) / 2)
            kept.append(item)
        return kept

    @staticmethod
    def _matches_excluded_name(item: dict[str, Any], excluded: set[str]) -> bool:
        if not excluded:
            return False
        haystack_parts = [str(item.get("name", ""))]
        keywords = item.get("keywords", [])
        if isinstance(keywords, list):
            haystack_parts.extend(str(k) for k in keywords)
        haystack = " ".join(haystack_parts).lower()
        for name in excluded:
            tokens = [token for token in re.findall(r"[a-zа-яё0-9]{3,}", name.lower()) if token]
            if tokens and all(token in haystack for token in tokens[:3]):
                return True
        return False

    @staticmethod
    def _normalize_price_range(raw_range: Any, budget: int) -> list[int]:
        """Оценка модели как есть: подгонять её под бюджет нельзя — книга за 1 500 ₽ не станет стоить 10 000 ₽."""
        if isinstance(raw_range, list) and len(raw_range) == 2:
            try:
                low = max(1, int(float(raw_range[0])))
                high = max(low, int(float(raw_range[1])))
                return [low, high]
            except (TypeError, ValueError):
                pass
        return [budget, budget]

    @classmethod
    def _extract_blocked_terms_from_photo(cls, photo_insights: str) -> set[str]:
        if not photo_insights.strip():
            return set()
        lowered = photo_insights.lower()
        blocked: set[str] = set()
        for marker_group in cls._PHOTO_OBJECT_MARKERS:
            if any(marker in lowered for marker in marker_group):
                blocked.update(marker_group)
        return blocked

    @staticmethod
    def _contains_blocked_photo_object(item: dict[str, Any], blocked_terms: set[str]) -> bool:
        if not blocked_terms:
            return False
        haystack_parts = [str(item.get("name", ""))]
        keywords = item.get("keywords", [])
        if isinstance(keywords, list):
            haystack_parts.extend(str(k) for k in keywords)
        haystack = " ".join(haystack_parts).lower()
        normalized_haystack = re.sub(r"[^a-zа-я0-9\s]", " ", haystack)
        return any(term in normalized_haystack for term in blocked_terms)

    @classmethod
    def _is_non_marketplace_idea(cls, item: dict[str, Any]) -> bool:
        haystack_parts = [str(item.get("name", ""))]
        keywords = item.get("keywords", [])
        if isinstance(keywords, list):
            haystack_parts.extend(str(k) for k in keywords)
        haystack = " ".join(haystack_parts).lower()
        normalized_haystack = re.sub(r"[^a-zа-я0-9\s-]", " ", haystack)
        return any(marker in normalized_haystack for marker in cls._NON_MARKETPLACE_MARKERS)
