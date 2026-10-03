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
_MAX_PER_CATEGORY = 2
_CANDIDATES_PER_IDEA = 8
_MAX_CHOSEN_OFFERS = 3
_CATALOG_RETRY_ROUNDS = 3
# Лимит сообщения Telegram 4096 символов; запас — на название идеи и подсказку под текстом.
_REASON_LIMIT = 3700

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
- Только физические товары, которые реально есть в нашем каталоге (см. блок «Ориентиры каталога»). Не предлагай бренды и типы товаров, которых там нет.
- Каждая идея должна находиться в каталоге по keywords. Если не уверен, что товар есть — выбери другую идею из ориентиров.
- price_min и price_max — реальная рыночная цена товара в рублях. Не подгоняй её под бюджет: если идея не помещается в бюджет, замени её другой.
- Разные бюджеты = разные классы товаров, а не та же модель дороже/дешевле:
  · 1–3 тыс. ₽ — мелкие полезные вещи, книги, уход, аксессуары начального уровня;
  · 3–5 тыс. ₽ — средний сегмент гаджетов/ухода/игр;
  · 5–10 тыс. ₽ — заметные гаджеты и наборы;
  · 10–20+ тыс. ₽ — премиальные или крупные вещи.
  Не предлагай «ту же колонку / те же наушники другого поколения» только из‑за другого бюджета.
- Состав подборки: 2-3 идеи по увлечениям получателя, 1 практичная вещь на каждый день, 1 «вау»-подарок (запоминающийся, немного неожиданный), 1 уютная или эмоциональная вещь. Не больше {_MAX_PER_CATEGORY} идей одной категории.
- category — одно-два слова: «аудио», «настольные игры», «уход за собой».
- name — конкретный товар, как в каталоге магазина: тип + бренд или модель, если уместно («Портативная колонка JBL Flip 6»), а не абстракция («Что-то для музыки»).
- keywords — 2 запроса для поиска по каталогу магазина, по 2-4 слова: тип товара + бренд/модель, без прилагательных-пояснений, назначения и получателя. Первый — точный, второй — общий («колонка jbl flip 6», затем «портативная колонка»).
- pitch — 1-2 предложения: чем идея цепляет именно этого человека, со ссылкой на его увлечения, возраст или повод.
  Хорошо: «Он каждые выходные в походах — колонка с защитой от воды переживет и дождь, и костер, а музыка у палатки станет традицией».
  Плохо: «Отличный подарок, который порадует любого человека и подойдет к празднику».
- Если есть наблюдения по фото — это сигналы о стиле и интересах. Не предлагай то, что у человека уже есть на фото (одежда, украшения, гаджеты, аксессуары); предлагай то, что дополнит его образ жизни.
- Если в профиле есть список «не предлагай снова» — избегай этих товаров, брендов и близких аналогов той же линейки."""

_SELECTION_INSTRUCTIONS = f"""Ты — эксперт по подаркам. Тебе дан профиль получателя и идеи подарков с товарами из каталога магазинов.

Для каждой идеи верни один объект с ее idea_index:
- offer_ids — до {_MAX_CHOSEN_OFFERS} товаров, которые действительно соответствуют идее и подходят получателю, от лучшего к худшему. Если ни один не подходит (другой тип товара, аксессуар вместо самого товара, детский вместо взрослого) — пустой список. Используй только id из списка товаров этой идеи.
- why_for_person — 2-3 предложения: почему это подойдет именно этому человеку, со ссылкой на его увлечения, возраст, стиль. Если товар выбран — пиши про конкретную модель и ее известные особенности; не выдумывай характеристики, в которых не уверен.
- occasion_fit — 1 предложение: почему подарок уместен к поводу и отношениям с получателем.
- practical_value — 1 предложение: как человек будет этим пользоваться.
- presentation_tip — 1 короткое предложение: как вручить или чем дополнить подарок.

Обращайся к дарителю на «вы», пиши живым языком, без канцелярита и общих фраз вроде «отличный выбор» или «подойдет каждому». Цену не упоминай."""


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
            ideas = self._limit_categories(ideas, already=linked)

            for item in ideas:
                name_key = item["name"].lower()
                if name_key in seen_names:
                    continue
                links = self._products.resolve_links(
                    item["keywords"], min_price=low, max_price=high, max_offers=_CANDIDATES_PER_IDEA
                )
                offers = (links[0].get("offers") if links else None) or []
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
            if choice is None:
                offers = item_candidates[:_MAX_CHOSEN_OFFERS]
            else:
                by_id = {f"i{index}o{position}": offer for position, offer in enumerate(item_candidates)}
                offers = [by_id[offer_id] for offer_id in choice["offer_ids"] if offer_id in by_id]
                # Пустой выбор модели при наличии кандидатов — берём топ из каталога, идею без ссылок не показываем.
                if not offers:
                    offers = item_candidates[:_MAX_CHOSEN_OFFERS]
            if not offers:
                self._logger.info("Отсеиваю вариант '%s': нет офферов после выбора", item.get("name", "gift"))
                continue
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
        ]
        if accepted:
            lines.append("Уже приняты (не повторяй и не предлагай близкие аналоги той же линейки):")
            lines.extend(f"- {item['name']}" for item in accepted)
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
            lines = [f"Идея {index}: {item['name']}", f"Зачем: {item['pitch']}"]
            if item["candidates"]:
                lines.append("Товары:")
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
        hobbies = c.hobbies.strip().rstrip(".")
        if hobbies:
            lines.append(f"Увлечения и пожелания: {hobbies}.")
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

    def _limit_categories(
        self, items: list[dict[str, Any]], *, already: list[dict[str, Any]] | None = None
    ) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for item in already or []:
            category = item.get("category") or ""
            if category:
                counts[category] = counts.get(category, 0) + 1
        kept: list[dict[str, Any]] = []
        for item in items:
            category = item.get("category") or ""
            if category and counts.get(category, 0) >= _MAX_PER_CATEGORY:
                self._logger.info("Отсеиваю вариант '%s': уже %s идеи категории «%s»", item["name"], _MAX_PER_CATEGORY, category)
                continue
            counts[category] = counts.get(category, 0) + 1
            kept.append(item)
        return kept

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
