from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import Any

from database.models import AffiliateProduct
from services.catalog_import import normalize_title


logger = logging.getLogger("gift_bot.product")

_TOKEN_RE = re.compile(r"[a-zа-яё0-9]{2,}", re.IGNORECASE)
# Одиночная цифра — часть модели: JBL Flip 6 и Flip 7 — разные товары, а не дубли.
_MODEL_TOKEN_RE = re.compile(r"[a-zа-яё0-9]{2,}|\d", re.IGNORECASE)
_PARENS_RE = re.compile(r"\([^)]*\)")
_LATIN_RE = re.compile(r"[a-z]", re.IGNORECASE)

# Цвета и «маркетинговые» названия расцветок: товары, отличающиеся только ими, считаем одной моделью.
_COLOR_WORDS = {
    "black", "white", "silver", "gray", "grey", "blue", "green", "red", "pink", "gold", "rose",
    "purple", "violet", "orange", "yellow", "beige", "brown", "teal", "sage", "midnight", "starlight",
    "graphite", "titanium", "natural", "desert", "cosmic", "space", "sky", "mist", "deep", "dark", "light",
    "lake", "cyan", "mint", "lavender", "burgundy", "navy", "cream", "ice", "jade", "coral", "lime",
    "blush", "abyss", "ocean", "oak", "lotus", "crystal", "breathing", "mulberry", "marble", "pistachio",
    "blueberry",
    "черный", "чёрный", "белый", "серый", "серебристый", "серебряный", "синий", "голубой", "зеленый",
    "зелёный", "красный", "розовый", "золотой", "золотистый", "фиолетовый", "сиреневый", "оранжевый",
    "желтый", "жёлтый", "бежевый", "коричневый", "бирюзовый", "графитовый", "титановый", "мятный",
    "лавандовый", "темно", "тёмно", "светло", "вишневый", "фисташковый", "голубика", "графит",
    "лиловый", "салатовый", "малиновый", "бордовый", "песочный", "кремовый", "туманно", "небесно",
    "сияющая", "звезда", "полночь",
}
_SAME_PRICE_SIMILARITY = 0.6
# Латинские слова из линеек разных брендов — не считаем их брендом/моделью.
_GENERIC_LATIN = {
    "pro", "air", "max", "mini", "plus", "ultra", "lite", "se", "neo", "fe", "go", "slim", "new", "edition",
    "gaming", "smart", "wireless", "bluetooth", "wifi", "usb", "ssd", "ram", "ips", "oled", "gb", "tb",
    "hd", "fhd", "uhd", "tv", "watch", "band", "buds", "book", "pad", "note", "phone", "black", "white",
}
_DUPLICATE_SIMILARITY = 0.8
_MIN_RELEVANCE = 0.55
# Насколько совпадение может уступать лучшему, чтобы считаться «таким же хорошим».
_DIVERSE_SCORE_RATIO = 0.85
# Как GPT называет товар → как он может называться в магазине (основы слов после _stem).
_SYNONYMS = {
    "умн": ("смарт", "smart"),
    "смарт": ("умн", "smart"),
    "капучинатор": ("вспенивател",),
    "вспенивател": ("капучинатор",),
    # Пол у ароматов указан в категории («мужские ароматы»), а GPT пишет «для мужчин».
    "мужчин": ("мужск",),
    "мужск": ("мужчин",),
    "женщин": ("женск",),
    "женск": ("женщин",),
    "духи": ("парфюм", "туалетн", "одеколон"),
    "парфюм": ("духи", "туалетн", "одеколон"),
    "уходов": ("уход",),
    # Книжные разделы называются «Книги для детей и подростков».
    "детск": ("детей",),
    "детей": ("детск",),
    "ребенк": ("детск", "детей"),
    "ребёнк": ("детск", "детей"),
    "ночник": ("светильник",),
    # Четырёхбуквенные слова _stem не режет: «небо» не совпало бы с «проекторы звездного неба».
    "небо": ("неба", "небе"),
}
# Основа совпадает с началом другого слова: «манг(а)» — не «манго».
_STEM_NOT_FOLLOWED_BY = {"манг": "о"}
# Слова, которые сами по себе не задают тип товара.
_WEAK_TOKEN_WEIGHT = 0.25
_WEAK_TOKENS = {"набор", "комплект", "подарочн", "подарочный", "коллекц", "мини", "больш", "маленьк", "нов", "лучш"}
# Для кого подарок: уточняет, но не определяет товар («планшет для ребенка» — это планшет).
_AUDIENCE_TOKENS = {
    "ребенк", "ребёнк", "детей", "детск", "малыш", "девочк", "мальчик", "подростк", "школьник", "студент",
    "мужчин", "мужск", "женщин", "женск", "взросл", "взрослых", "мама", "маме", "папа", "папе", "мужу", "жене",
    "бабушк", "дедушк", "подруг", "друг", "коллег",
}
_QUALIFIER_TOKENS = _WEAK_TOKENS | _AUDIENCE_TOKENS
_HYPHEN_COMPOUND_RE = re.compile(r"([а-яё]{3,})-([а-яё]{3,})")
_LEADING_NOISE = {
    "led", "qled", "q-led", "oled", "hqled", "miniled", "mini-led", "lcd", "ips", "tv", "smart", "4k", "uhd", "fhd", "hd",
}
_SHORT_TITLE_LIMIT = 34

_MARKET_LABELS = {
    "ozon": "Ozon",
    "wildberries": "Wildberries",
    "aliexpress": "AliExpress",
    "avito": "Avito",
    "mvideo": "М.Видео",
    "goldapple": "Золотое яблоко",
    "detmir": "Детский мир",
    "chitaigorod": "Читай-город",
}
# Здесь латиница — часть названия («Кулинарная книга Atomic Heart»), а не бренд после типа товара.
_NAMED_TITLE_MARKETS = {"chitaigorod"}


def market_label(marketplace: str) -> str:
    return _MARKET_LABELS.get(marketplace, marketplace.title() or "Магазин")


def short_title(title: str, *, strip_type: bool = True) -> str:
    """«Смартфон Apple iPhone 17 256GB Sage (без RuStore)» → «Apple iPhone 17 256GB»."""
    # Скобки без цифр — «(без RuStore)», «(фисташковый)»; скобки с характеристиками оставляем.
    without_notes = _PARENS_RE.sub(lambda match: match.group(0) if re.search(r"\d", match.group(0)) else " ", title)
    text = re.sub(r"\s+([,;:])", r"\1", re.sub(r"\s+", " ", without_notes)).strip(" ,")
    words = [word for word in text.split(" ") if word]
    # Цвет — только в конце названия: «iPhone 17 256GB Sage», но не «Assassin's Creed Black Flag».
    while len(words) > 1 and _is_color_word(words[-1]):
        words.pop()
    # «Apple Смартфон Apple iPhone» → оставляем последнее вхождение повторяющегося названия.
    words = [
        word
        for index, word in enumerate(words)
        if len(word) < 4 or word.lower() not in {w.lower() for w in words[index + 1 :]}
    ]
    # Убираем тип товара и диагональ перед брендом: «11 " Планшет HONOR Pad X8a» → «HONOR Pad X8a».
    first_latin = next((index for index, word in enumerate(words) if _LATIN_RE.search(word)), None)
    # Только если латиница близко к началу: в «Умная колонка Яндекс Станция … на YaGPT» бренд русский.
    if strip_type and first_latin is not None and first_latin <= 3:
        stripped = list(words)
        while stripped and not _LATIN_RE.search(stripped[0]):
            stripped.pop(0)
        # «LED Xiaomi Mi TV», «QLED TCL 55P7L» — технология перед брендом.
        while len(stripped) > 2 and stripped[0].lower().strip(".,:") in _LEADING_NOISE:
            stripped.pop(0)
        # «…для пк 26000 dpi» — латиница только в единицах измерения, бренда нет;
        # «Мини-проектор 4K ULTRA HD» — только характеристики.
        has_brand = any(
            _LATIN_RE.search(word) and word.lower().strip(".,:") not in _GENERIC_LATIN | _LEADING_NOISE
            for word in stripped
        )
        if len(stripped) >= 2 and has_brand:
            words = stripped
    result = ""
    for word in words:
        candidate = f"{result} {word}".strip()
        if len(candidate) > _SHORT_TITLE_LIMIT:
            return f"{result.rstrip(' ,;:-')}…" if result else word[:_SHORT_TITLE_LIMIT]
        result = candidate
    return result.rstrip(" ,;:-") or title[:_SHORT_TITLE_LIMIT]


def _is_color_word(word: str) -> bool:
    parts = [part for part in re.split(r"[-+/,]", word.lower().strip(".,")) if part]
    return bool(parts) and all(part in _COLOR_WORDS for part in parts)


def _model_tokens(title: str) -> frozenset[str]:
    text = re.sub(r"(\d)\s*гб", r"\1gb", title.lower())
    text = re.sub(r"(\d)\s*тб", r"\1tb", text)
    return frozenset(token for token in _MODEL_TOKEN_RE.findall(text) if token not in _COLOR_WORDS)


_RU_ENDINGS = (
    "иями", "ями", "ами", "его", "ого", "ему", "ому", "ыми", "ими", "ая", "яя", "ое", "ее", "ые", "ие",
    "ый", "ий", "ой", "ом", "ем", "ам", "ям", "ах", "ях", "ов", "ев", "ую", "юю", "а", "я", "о", "е",
    "ы", "и", "у", "ю", "ь",
)


def _stem(token: str) -> str:
    """Грубая основа русского слова: «игровой» → «игров», «учебы» → «учеб», «мышь» → «мыш»."""
    if not re.search(r"[а-яё]", token) or len(token) <= 3:
        return token
    # Короткие слова не режем: «часы» → «час» совпало бы с «до 95 часов работы».
    if len(token) == 4:
        return token[:-1] if token.endswith("ь") else token
    for ending in _RU_ENDINGS:
        if token.endswith(ending) and len(token) - len(ending) >= 3:
            return token[: -len(ending)]
    return token


_ADJECTIVE_RE = re.compile(r"(?:ая|яя|ое|ее|ые|ие|ый|ий|ой)$")
_NOUN_SUFFIX_RE = re.compile(r"(?:ение|ание|тие)$")


def _product_type_token(text: str) -> str | None:
    """Тип товара — первое русское существительное: «игровая мышь razer» → «мыш».

    Прилагательные («игровая», «настольная») идут первыми, но решают не они:
    иначе на «настольную игру» найдётся настольный блендер.
    """
    for word in re.findall(r"[a-zа-яё0-9-]+", text.lower()):
        parts = [part for part in word.split("-") if part]
        # «веб-камера» → «камера», «робот-пылесос» → «пылесос».
        word = parts[-1] if parts else word
        if not re.fullmatch(r"[а-яё]{3,}", word) or word in {"для", "или"}:
            continue
        if _ADJECTIVE_RE.search(word) and not _NOUN_SUFFIX_RE.search(word):
            continue
        token = _stem(word)
        if token in _QUALIFIER_TOKENS:
            continue
        return token
    return None


def _variants(token: str) -> list[str]:
    return [token, *_SYNONYMS.get(token, ())]


def _token_pattern(token: str) -> re.Pattern[str]:
    # Латиница и цифры — целым словом («pro» не должен совпадать с «probook»),
    # русские слова — по началу слова, чтобы учитывать окончания.
    parts = []
    for variant in _variants(token):
        if re.search(r"[а-яё]", variant):
            blocked = _STEM_NOT_FOLLOWED_BY.get(variant)
            parts.append(rf"(?<![a-zа-яё0-9]){re.escape(variant)}" + (f"(?!{blocked})" if blocked else ""))
        else:
            parts.append(rf"(?<![a-zа-яё0-9]){re.escape(variant)}(?![a-zа-яё0-9])")
    return re.compile("|".join(parts), re.IGNORECASE)


def _similarity(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


@dataclass(frozen=True)
class ProductOffer:
    marketplace: str
    title: str
    price: int
    url: str
    image_url: str = ""
    source: str = ""

    def as_dict(self, *, with_market: bool = False) -> dict[str, Any]:
        parts = [short_title(self.title, strip_type=self.marketplace not in _NAMED_TITLE_MARKETS)]
        if self.price > 0:
            parts.append(f"{self.price:,} ₽".replace(",", " "))
        if with_market:
            parts.append(market_label(self.marketplace))
        return {
            "marketplace": self.marketplace,
            "label": " · ".join(parts),
            "title": self.title,
            "price": self.price,
            "url": self.url,
            "image_url": self.image_url,
            "source": self.source,
        }


class ProductService:
    """Поиск реальных товаров в локальном каталоге, собранном сборщиками из tools/collectors."""

    def __init__(self, *, preferred_marketplaces: tuple[str, ...] = ()) -> None:
        self._preferred_marketplaces = preferred_marketplaces

    def catalog_size(self) -> int:
        return int(AffiliateProduct.select().count())

    def find_offers(
        self,
        keywords: list[str],
        *,
        min_price: int | None = None,
        max_price: int | None = None,
        limit_per_market: int = 3,
        max_offers: int = 3,
    ) -> list[dict[str, Any]]:
        tokens = self._extract_tokens(keywords)
        if not tokens:
            return []

        price_min = max(0, int(min_price or 0))
        price_max = max(0, int(max_price or 0))
        query = AffiliateProduct.select().where(AffiliateProduct.tracking_link.is_null(False))
        if price_max > 0:
            query = query.where(AffiliateProduct.price >= price_min, AffiliateProduct.price <= price_max)

        # Все токены через AND слишком жёстко для шумных названий: берём OR в SQL,
        # а точное совпадение и ранжирование делаем локально.
        token_filter = None
        for token in tokens[:8]:
            for variant in _variants(token):
                condition = AffiliateProduct.title_norm.contains(variant)
                token_filter = condition if token_filter is None else (token_filter | condition)
        if token_filter is not None:
            query = query.where(token_filter)

        candidates = list(query.limit(5000))
        patterns = {token: _token_pattern(token) for token in tokens[:8]}
        matches: list[tuple[AffiliateProduct, set[str]]] = []
        for product in candidates:
            # Категория уточняет тип товара: «Игровые наушники Logitech» не должны совпасть с «мышь logitech».
            haystack = f"{product.title_norm or normalize_title(product.title)} {(product.category or '').lower()}"
            matched = {token for token, pattern in patterns.items() if pattern.search(haystack)}
            if matched:
                matches.append((product, matched))
        # Бренд/модель латиницей, которые есть в каталоге (в любой цене), обязательны:
        # иначе вместо «ноутбук lenovo» вне бюджета покажем ноутбук без бренда.
        brand_tokens = {
            token
            for token in patterns
            if re.fullmatch(r"[a-z][a-z0-9]*", token)
            and token not in _GENERIC_LATIN
            and AffiliateProduct.select().where(AffiliateProduct.title_norm.contains(token)).exists()
        }
        if brand_tokens:
            matches = [(product, matched) for product, matched in matches if matched & brand_tokens]
        product_type = _product_type_token(" ".join(str(k) for k in keywords))
        if product_type in patterns:
            matches = [(product, matched) for product, matched in matches if product_type in matched]
        if not matches:
            logger.info("Product search empty tokens=%s price=%s-%s", tokens, price_min, price_max)
            return []

        # Редкие слова («lenovo», «macbook») важнее частых («ноутбук»): вес как в IDF.
        # Слова, которых нет ни в одном товаре каталога («для ребенка»), не учитываем вовсе.
        known = [
            token
            for token in patterns
            if any(token in matched for _, matched in matches)
            or AffiliateProduct.select().where(AffiliateProduct.title_norm.contains(token)).exists()
        ]
        # Бренд/модель латиницей, которой нет в каталоге вовсе («instax»): похожий товар другого бренда не подставляем.
        if any(
            re.fullmatch(r"[a-z][a-z0-9]*", token) and token not in _GENERIC_LATIN and token not in known
            for token in patterns
        ):
            logger.info("Product search: brand not in catalog tokens=%s", tokens)
            return []
        # Первое слово — тип товара («серьги серебро»): если такого типа в каталоге нет, похожее не подбираем.
        head = product_type if product_type in patterns else next(
            (token for token in tokens if token not in _QUALIFIER_TOKENS), tokens[0]
        )
        if head not in known:
            logger.info("Product search: product type not in catalog tokens=%s", tokens)
            return []
        # «Робот-пылесос» без пылесосов в каталоге — это не детский робот.
        for compound in _HYPHEN_COMPOUND_RE.finditer(" ".join(keywords).lower()):
            if any(_stem(part) in patterns and _stem(part) not in known for part in compound.groups()):
                logger.info("Product search: compound %s not in catalog", compound.group(0))
                return []
        # «набор для рисования» без «рисования» в каталоге — это не запрос про любой набор.
        core_known = [token for token in known if token not in _QUALIFIER_TOKENS]
        if not core_known:
            logger.info("Product search: only generic words known tokens=%s", tokens)
            return []
        # «робот пылесос»: половина сути запроса в каталоге не встречается — по одному слову не подбираем.
        core_unknown = [token for token in patterns if token not in _QUALIFIER_TOKENS and token not in known]
        if len(core_known) + len(core_unknown) > 1 and len(core_unknown) >= len(core_known):
            logger.info("Product search: too many unknown words tokens=%s", tokens)
            return []
        total = len(matches)
        weights = {
            token: math.log(1 + total / max(1, sum(1 for _, matched in matches if token in matched)))
            for token in core_known
        }
        # «Большая», «набор», «для ребенка» уточняют запрос, но не должны решать, найдётся ли товар.
        qualifier_weight = _WEAK_TOKEN_WEIGHT * sum(weights.values()) / len(weights)
        weights.update({token: qualifier_weight for token in known if token in _QUALIFIER_TOKENS})
        weight_sum = sum(weights.values()) or 1.0
        scored: list[tuple[float, AffiliateProduct]] = []
        for product, matched in matches:
            score = sum(weights.get(token, 0.0) for token in matched) / weight_sum
            # Совпадение по одному случайному слову («часов» у мыши на запрос «умные часы») — не результат.
            if score >= _MIN_RELEVANCE:
                scored.append((score, product))
        if not scored:
            logger.info("Product search: nothing relevant tokens=%s price=%s-%s", tokens, price_min, price_max)
            return []
        target = (price_min + price_max) / 2 if price_max else 0
        scored.sort(key=lambda pair: (-pair[0], abs((pair[1].price or 0) - target)))

        by_market: dict[str, list[tuple[float, AffiliateProduct]]] = {}
        for pair in scored:
            by_market.setdefault((pair[1].marketplace or "unknown").lower(), []).append(pair)
        # Магазин без хорошего совпадения не добавляем ради разнообразия: на «мужской парфюм» не нужна бритва.
        top_score = scored[0][0]
        by_market = {
            market: pairs for market, pairs in by_market.items() if pairs[0][0] >= top_score * _DIVERSE_SCORE_RATIO
        }

        market_order = [market for market in self._preferred_marketplaces if market in by_market]
        market_order += [market for market in by_market if market not in market_order]
        picks = {market: self._pick_diverse(by_market[market], limit_per_market) for market in market_order}

        # По очереди из каждого магазина, чтобы при нескольких магазинах были представлены все.
        ordered: list[AffiliateProduct] = []
        depth = 0
        while len(ordered) < max_offers and any(depth < len(items) for items in picks.values()):
            for market in market_order:
                if depth < len(picks[market]) and len(ordered) < max_offers:
                    ordered.append(picks[market][depth])
            depth += 1

        with_market = len({(product.marketplace or "").lower() for product in ordered}) > 1
        return [
            ProductOffer(
                marketplace=(product.marketplace or "unknown").lower(),
                title=product.title,
                price=int(product.price or 0),
                url=product.tracking_link,
                image_url=product.image_url or "",
                source=product.source,
            ).as_dict(with_market=with_market)
            for product in ordered
        ]

    @staticmethod
    def _pick_diverse(scored: list[tuple[float, AffiliateProduct]], limit: int) -> list[AffiliateProduct]:
        """Лучшее совпадение + самый дешёвый и самый дорогой из близких по релевантности, без дублей по модели."""
        unique: list[tuple[float, AffiliateProduct, frozenset[str]]] = []
        for score, product in scored:
            model = _model_tokens(product.title)
            if any(
                _similarity(model, other) >= _DUPLICATE_SIMILARITY
                or (other_product.price == product.price and _similarity(model, other) >= _SAME_PRICE_SIMILARITY)
                for _, other_product, other in unique
            ):
                continue
            unique.append((score, product, model))
            if len(unique) >= 15:
                break
        if not unique:
            return []

        top_score = unique[0][0]
        pool = [product for score, product, _ in unique if score >= top_score * _DIVERSE_SCORE_RATIO]
        best, rest = pool[0], pool[1:]
        picks = [best]
        cheaper = [product for product in rest if (product.price or 0) < (best.price or 0)]
        pricier = [product for product in rest if (product.price or 0) > (best.price or 0)]
        if cheaper and len(picks) < limit:
            picks.append(min(cheaper, key=lambda product: product.price or 0))
        if pricier and len(picks) < limit:
            picks.append(max(pricier, key=lambda product: product.price or 0))
        for product in rest:
            if len(picks) >= limit:
                break
            if product not in picks:
                picks.append(product)
        return sorted(picks[:limit], key=lambda product: product.price or 0)

    def resolve_links(
        self,
        keywords: list[str],
        *,
        min_price: int | None = None,
        max_price: int | None = None,
        max_offers: int = 3,
    ) -> list[dict[str, Any]]:
        """Совместимый с handlers формат: список групп офферов на keyword.

        Запросы пробуем по очереди (первый — самый точный). Пустой запрос укорачиваем с конца:
        пояснения вроде «для дома» мешают поиску, а тип товара и бренд обычно идут первыми.
        """
        tried: set[tuple[str, ...]] = set()
        for keyword in keywords:
            words = str(keyword).split()
            for size in range(len(words), 0, -1):
                query = " ".join(words[:size])
                tokens = tuple(self._extract_tokens([query]))
                if len(tokens) < min(2, len(self._extract_tokens([keyword]))) or not tokens or tokens in tried:
                    continue
                tried.add(tokens)
                offers = self.find_offers(
                    [query],
                    min_price=min_price,
                    max_price=max_price,
                    limit_per_market=max_offers,
                    max_offers=max_offers,
                )
                if offers:
                    return [{"keyword": query, "offers": offers}]
        return []

    def catalog_hints(self, *, min_price: int, max_price: int, max_categories: int = 12, per_category: int = 3) -> str:
        """Краткий обзор каталога в окне бюджета — чтобы модель предлагала только существующие типы товаров."""
        price_min = max(0, int(min_price or 0))
        price_max = max(price_min, int(max_price or 0))
        query = AffiliateProduct.select().where(
            AffiliateProduct.tracking_link.is_null(False),
            AffiliateProduct.price >= price_min,
            AffiliateProduct.price <= price_max,
        )
        by_category: dict[str, list[AffiliateProduct]] = {}
        for product in query.order_by(AffiliateProduct.price.asc()).limit(2500):
            category = (product.category or "другое").strip() or "другое"
            bucket = by_category.setdefault(category, [])
            if len(bucket) >= per_category:
                continue
            bucket.append(product)
            if len(by_category) >= max_categories and all(len(items) >= per_category for items in by_category.values()):
                # Уже набрали достаточно — можно остановиться раньше на следующей итерации.
                pass
        if not by_category:
            return "В каталоге в этом бюджете товаров пока нет."
        # Берём категории с наибольшим числом примеров, стабильно по имени.
        ranked = sorted(by_category.items(), key=lambda pair: (-len(pair[1]), pair[0].lower()))[:max_categories]
        lines = [f"Ориентиры каталога в бюджете {price_min}–{price_max} ₽ (категория → примеры):"]
        for category, products in ranked:
            examples = "; ".join(f"{product.title[:80]} ({int(product.price or 0)} ₽)" for product in products)
            lines.append(f"- {category}: {examples}")
        lines.append(
            "Предлагай только идеи, которые можно найти среди таких категорий и брендов. "
            "Не выдумывай бренды и типы товаров, которых здесь нет."
        )
        return "\n".join(lines)

    @staticmethod
    def _extract_tokens(keywords: list[str]) -> list[str]:
        joined = " ".join(str(item) for item in keywords if str(item).strip())
        tokens = [token.lower() for token in _TOKEN_RE.findall(joined)]
        # Уникальные токены с сохранением порядка.
        seen: set[str] = set()
        ordered: list[str] = []
        stop = {"для", "или", "the", "and", "оригинал", "подарок"}
        for token in tokens:
            if token in stop:
                continue
            token = _stem(token)
            if token in seen:
                continue
            seen.add(token)
            ordered.append(token)
        return ordered
