from __future__ import annotations

import argparse
from collections import Counter
import json
import random
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus


MARKETPLACES: tuple[str, ...] = (
    "ozon",
    "wildberries",
    "yandex_market",
)

# Explicitly block non-physical offerings.
FORBIDDEN_TOKENS: tuple[str, ...] = (
    "курс",
    "курсы",
    "сертификат",
    "онлайн",
    "тренировка",
    "вебинар",
    "подписка",
    "коучинг",
    "билет",
    "поездка",
    "впечатление",
    "абонемент",
    "консультация",
    "мастер-класс",
    "услуга",
)

COLORS: tuple[str, ...] = (
    "черный",
    "белый",
    "серый",
    "синий",
    "зеленый",
    "красный",
    "розовый",
    "бежевый",
    "золотой",
    "серебристый",
    "графит",
    "лаванда",
)

MATERIALS: tuple[str, ...] = (
    "ABS-пластик",
    "алюминий",
    "нержавеющая сталь",
    "экокожа",
    "натуральная кожа",
    "поликарбонат",
    "закаленное стекло",
    "карбон",
)

CAPACITY_OPTIONS: tuple[str, ...] = (
    "64 ГБ",
    "128 ГБ",
    "256 ГБ",
    "512 ГБ",
    "1 ТБ",
    "1.5 л",
    "2 л",
    "3 л",
    "4 л",
)

SIZE_OPTIONS: tuple[str, ...] = (
    "XS",
    "S",
    "M",
    "L",
    "XL",
    "XXL",
    "20 см",
    "24 см",
    "27 см",
    "32 см",
    "40 см",
)

EDITION_OPTIONS: tuple[str, ...] = (
    "2024 edition",
    "2025 edition",
    "2026 edition",
    "limited edition",
    "plus edition",
    "family pack",
    "gift box",
    "premium set",
)


@dataclass(frozen=True)
class ProductTemplate:
    category: str
    base_name: str
    brand_pool: tuple[str, ...]
    model_pool: tuple[str, ...]
    descriptor_pool: tuple[str, ...]
    audience_pool: tuple[str, ...]
    tags: tuple[str, ...]


@dataclass
class QualityStats:
    generated: int = 0
    valid: int = 0
    invalid: int = 0
    duplicate_signatures: int = 0
    forbidden_hits: int = 0
    missing_marketplace_links: int = 0
    price_out_of_bounds: int = 0
    malformed_records: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "generated": self.generated,
            "valid": self.valid,
            "invalid": self.invalid,
            "duplicate_signatures": self.duplicate_signatures,
            "forbidden_hits": self.forbidden_hits,
            "missing_marketplace_links": self.missing_marketplace_links,
            "price_out_of_bounds": self.price_out_of_bounds,
            "malformed_records": self.malformed_records,
        }


TEMPLATES: tuple[ProductTemplate, ...] = (
    ProductTemplate(
        category="electronics",
        base_name="беспроводные наушники",
        brand_pool=("Sony", "Anker", "JBL", "Xiaomi", "Samsung"),
        model_pool=("A3", "Pro 2", "Max", "Lite", "S5"),
        descriptor_pool=("с ANC", "вакуумные", "влагозащита IPX4", "долгая автономность"),
        audience_pool=("унисекс", "для нее", "для него"),
        tags=("аудио", "гаджеты", "повседневное"),
    ),
    ProductTemplate(
        category="electronics",
        base_name="умные часы",
        brand_pool=("Huawei", "Amazfit", "Samsung", "Xiaomi", "Honor"),
        model_pool=("Watch 4", "Fit 3", "Active", "Pro", "Mini"),
        descriptor_pool=("AMOLED", "с GPS", "мониторинг сна", "NFC"),
        audience_pool=("унисекс", "для спорта", "для работы"),
        tags=("носимая электроника", "здоровье", "стиль"),
    ),
    ProductTemplate(
        category="home_appliances",
        base_name="робот-пылесос",
        brand_pool=("Dreame", "Xiaomi", "Roborock", "Kitfort", "Viomi"),
        model_pool=("R20", "S8", "X1", "Ultra", "Plus"),
        descriptor_pool=("с лидаром", "влажная уборка", "станция самоочистки", "тихий режим"),
        audience_pool=("для дома", "для семьи", "унисекс"),
        tags=("бытовая техника", "дом", "комфорт"),
    ),
    ProductTemplate(
        category="home_appliances",
        base_name="кофемашина",
        brand_pool=("DeLonghi", "Philips", "Krups", "Nivona", "Polaris"),
        model_pool=("Barista", "Series 2200", "Latte Pro", "Cappuccino", "Compact"),
        descriptor_pool=("автоматическая", "с капучинатором", "программируемые рецепты", "компактная"),
        audience_pool=("для дома", "для пары", "для офиса"),
        tags=("кофе", "быт", "премиум"),
    ),
    ProductTemplate(
        category="beauty",
        base_name="фен-стайлер",
        brand_pool=("Dyson", "Laifen", "Rowenta", "BaByliss", "Philips"),
        model_pool=("Air Pro", "Style+", "Salon", "Smooth", "ProCare"),
        descriptor_pool=("с насадками", "бережная сушка", "ионизация", "быстрая укладка"),
        audience_pool=("для нее", "унисекс"),
        tags=("уход", "волосы", "красота"),
    ),
    ProductTemplate(
        category="sports",
        base_name="электросамокат",
        brand_pool=("Ninebot", "Kugoo", "Xiaomi", "Aovo", "Yokamura"),
        model_pool=("M4", "Pro", "Urban", "Max", "Lite"),
        descriptor_pool=("запас хода 30+ км", "двойная амортизация", "складной", "дисковый тормоз"),
        audience_pool=("унисекс", "для города", "для активных"),
        tags=("транспорт", "спорт", "город"),
    ),
    ProductTemplate(
        category="home_office",
        base_name="эргономичное кресло",
        brand_pool=("Everprof", "Metta", "Brabix", "Chairman", "Aeronix"),
        model_pool=("Office Pro", "Ergo", "Smart", "Comfort", "Elite"),
        descriptor_pool=("поддержка поясницы", "регулировка 4D", "дышащая спинка", "усиленная база"),
        audience_pool=("для работы", "унисекс"),
        tags=("офис", "здоровье", "комфорт"),
    ),
    ProductTemplate(
        category="home_office",
        base_name="монитор 27 дюймов",
        brand_pool=("LG", "Samsung", "AOC", "Philips", "MSI"),
        model_pool=("QHD", "4K", "Pro", "Vision", "Creator"),
        descriptor_pool=("IPS матрица", "144 Гц", "USB-C", "точная цветопередача"),
        audience_pool=("для работы", "для дизайна", "для игр"),
        tags=("дисплей", "рабочее место", "техника"),
    ),
    ProductTemplate(
        category="kitchen",
        base_name="планетарный миксер",
        brand_pool=("KitchenAid", "Kitfort", "Bork", "Moulinex", "Redmond"),
        model_pool=("Chef", "Master", "Pro", "Series 7", "Home"),
        descriptor_pool=("металлическая чаша", "мощный мотор", "набор насадок", "тихая работа"),
        audience_pool=("для кухни", "для семьи", "для нее"),
        tags=("кухня", "выпечка", "дом"),
    ),
    ProductTemplate(
        category="fashion",
        base_name="кожаная сумка",
        brand_pool=("Furla", "Coccinelle", "Ekonika", "Guess", "Love Moschino"),
        model_pool=("Classic", "City", "Mini", "Soft", "Premium"),
        descriptor_pool=("натуральная кожа", "лаконичный дизайн", "на каждый день", "фурнитура premium"),
        audience_pool=("для нее",),
        tags=("аксессуары", "стиль", "гардероб"),
    ),
    ProductTemplate(
        category="fashion",
        base_name="кроссовки",
        brand_pool=("Nike", "Adidas", "New Balance", "Puma", "Asics"),
        model_pool=("Run", "Street", "X5", "Urban", "Cloud"),
        descriptor_pool=("амортизация", "дышащие материалы", "универсальный стиль", "легкие"),
        audience_pool=("унисекс", "для спорта", "для города"),
        tags=("обувь", "спорт", "стиль"),
    ),
    ProductTemplate(
        category="gaming",
        base_name="игровая консоль",
        brand_pool=("Sony", "Microsoft", "Nintendo"),
        model_pool=("PlayStation 5", "Xbox Series X", "Switch OLED"),
        descriptor_pool=("новое поколение", "быстрый SSD", "комплект с геймпадом", "4K"),
        audience_pool=("унисекс", "для игр"),
        tags=("игры", "технологии", "развлечения"),
    ),
    ProductTemplate(
        category="photo_video",
        base_name="экшн-камера",
        brand_pool=("GoPro", "DJI", "Insta360", "SJCAM", "Akaso"),
        model_pool=("Hero", "Action 4", "X3", "Pro", "Lite"),
        descriptor_pool=("стабилизация", "4K съемка", "водозащита", "широкий угол"),
        audience_pool=("унисекс", "для путешествий", "для спорта"),
        tags=("видео", "контент", "гаджеты"),
    ),
    ProductTemplate(
        category="travel",
        base_name="чемодан",
        brand_pool=("Samsonite", "American Tourister", "Xiaomi", "Polar", "Roncato"),
        model_pool=("M", "L", "Pro", "Air", "Flex"),
        descriptor_pool=("поликарбонат", "четыре колеса", "кодовый замок", "легкий корпус"),
        audience_pool=("унисекс", "для путешествий"),
        tags=("дорога", "багаж", "удобство"),
    ),
    ProductTemplate(
        category="kids",
        base_name="конструктор",
        brand_pool=("LEGO", "Mould King", "Cada", "Sluban", "Xingbao"),
        model_pool=("Technic", "City", "Architecture", "Creator", "Robotics"),
        descriptor_pool=("много деталей", "сложная сборка", "развивает логику", "коллекционная серия"),
        audience_pool=("для ребенка", "для подростка", "унисекс"),
        tags=("игрушки", "развитие", "хобби"),
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate high-quality marketplace-ready physical product dataset "
            "for any budget ranges."
        )
    )
    parser.add_argument("--count", type=int, default=1_000_000, help="Number of products to generate.")
    parser.add_argument("--min-price", type=int, default=500, help="Absolute minimum price in RUB.")
    parser.add_argument("--max-price", type=int, default=500_000, help="Absolute maximum price in RUB.")
    parser.add_argument(
        "--range-template",
        type=str,
        default="any",
        choices=("any", "tight", "normal", "wide"),
        help="How wide each product price interval should be.",
    )
    parser.add_argument(
        "--marketplaces",
        type=str,
        default="all",
        help='Comma separated list from: ozon,wildberries,yandex_market or "all".',
    )
    parser.add_argument("--seed", type=int, default=42, help="Deterministic random seed.")
    parser.add_argument(
        "--format",
        choices=("json", "ndjson"),
        default="ndjson",
        help="Output format; ndjson is recommended for very large datasets.",
    )
    parser.add_argument(
        "--quality-report",
        type=Path,
        default=Path("quality_report.json"),
        help="Where to write generation quality metrics JSON.",
    )
    parser.add_argument(
        "--strict-quality",
        action="store_true",
        help="Exit with error if any invalid records are detected.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Top-K categories/brands in quality report.",
    )
    parser.add_argument(
        "--sla-min-valid-ratio",
        type=float,
        default=0.999,
        help="SLA: minimum allowed valid_ratio in [0,1].",
    )
    parser.add_argument(
        "--sla-max-duplicate-ratio",
        type=float,
        default=0.03,
        help="SLA: maximum allowed duplicate_ratio in [0,1].",
    )
    parser.add_argument(
        "--sla-max-forbidden-hits",
        type=int,
        default=0,
        help="SLA: maximum allowed forbidden token hits.",
    )
    parser.add_argument(
        "--sla-max-missing-marketplace-links",
        type=int,
        default=0,
        help="SLA: maximum allowed missing marketplace links.",
    )
    parser.add_argument(
        "--sla-max-price-out-of-bounds",
        type=int,
        default=0,
        help="SLA: maximum allowed price out-of-bounds hits.",
    )
    parser.add_argument(
        "--sla-max-malformed-records",
        type=int,
        default=0,
        help="SLA: maximum allowed malformed records.",
    )
    parser.add_argument("--output", type=Path, default=Path("marketplace_products_1m.ndjson"))
    return parser.parse_args()


def normalize_marketplaces(raw_value: str) -> tuple[str, ...]:
    if raw_value.strip().lower() == "all":
        return MARKETPLACES
    requested = tuple(part.strip().lower() for part in raw_value.split(",") if part.strip())
    invalid = [name for name in requested if name not in MARKETPLACES]
    if invalid:
        raise ValueError(f"Unknown marketplaces: {', '.join(invalid)}")
    if not requested:
        raise ValueError("At least one marketplace must be selected.")
    return requested


def choose_range_width(range_template: str, budget_hint: int) -> int:
    if range_template == "tight":
        return max(150, int(budget_hint * 0.04))
    if range_template == "normal":
        return max(300, int(budget_hint * 0.10))
    if range_template == "wide":
        return max(800, int(budget_hint * 0.24))
    # any: diverse widths
    return random.choice(
        (
            max(100, int(budget_hint * 0.03)),
            max(250, int(budget_hint * 0.08)),
            max(600, int(budget_hint * 0.18)),
            max(1200, int(budget_hint * 0.30)),
        )
    )


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def build_search_links(query: str, marketplaces: tuple[str, ...]) -> dict[str, str]:
    encoded = quote_plus(query)
    links: dict[str, str] = {}
    if "ozon" in marketplaces:
        links["ozon"] = f"https://www.ozon.ru/search/?text={encoded}"
    if "wildberries" in marketplaces:
        links["wildberries"] = f"https://www.wildberries.ru/catalog/0/search.aspx?search={encoded}"
    if "yandex_market" in marketplaces:
        links["yandex_market"] = f"https://market.yandex.ru/search?text={encoded}"
    return links


def contains_forbidden_tokens(*values: str) -> bool:
    merged = " ".join(values).lower()
    return any(token in merged for token in FORBIDDEN_TOKENS)


def record_signature(item: dict[str, object]) -> str:
    title = str(item.get("title", "")).lower()
    brand = str(item.get("brand", "")).lower()
    model = str(item.get("model", "")).lower()
    category = str(item.get("category", "")).lower()
    sku = str(item.get("sku", "")).lower()
    return f"{title}|{brand}|{model}|{category}|{sku}"


def validate_product_record(
    item: dict[str, object],
    min_price: int,
    max_price: int,
    required_marketplaces: tuple[str, ...],
) -> list[str]:
    errors: list[str] = []
    required_top = (
        "id",
        "sku",
        "title",
        "description",
        "category",
        "brand",
        "model",
        "price",
        "search",
        "marketplaces",
        "attributes",
    )
    for key in required_top:
        if key not in item:
            errors.append(f"missing:{key}")

    title = str(item.get("title", ""))
    description = str(item.get("description", ""))
    search = item.get("search")
    marketplaces = item.get("marketplaces")
    price = item.get("price")
    attributes = item.get("attributes")

    if contains_forbidden_tokens(title, description):
        errors.append("forbidden_token")

    if not isinstance(price, dict):
        errors.append("price_not_dict")
    else:
        pmin = int(price.get("min", 0))
        pmax = int(price.get("max", 0))
        pavg = int(price.get("avg", 0))
        if pmin < min_price or pmax > max_price or pmax < pmin:
            errors.append("price_out_of_bounds")
        if pavg < pmin or pavg > pmax:
            errors.append("price_avg_out_of_bounds")

    if not isinstance(search, dict) or not str(search.get("query", "")).strip():
        errors.append("bad_search")

    if not isinstance(marketplaces, dict):
        errors.append("marketplaces_not_dict")
    else:
        for mp in required_marketplaces:
            if not str(marketplaces.get(mp, "")).strip():
                errors.append(f"missing_marketplace:{mp}")

    if not isinstance(attributes, dict):
        errors.append("attributes_not_dict")
    else:
        if attributes.get("is_physical_product") is not True:
            errors.append("not_physical")
        if attributes.get("is_marketplace_ready") is not True:
            errors.append("not_marketplace_ready")

    return errors


def generate_valid_product_record(
    idx: int,
    min_price: int,
    max_price: int,
    marketplaces: tuple[str, ...],
    range_template: str,
    max_attempts: int = 25,
    known_signatures: set[str] | None = None,
) -> tuple[dict[str, object], list[str]]:
    last_errors: list[str] = []
    for _ in range(max_attempts):
        item = generate_product_record(idx, min_price, max_price, marketplaces, range_template)
        errors = validate_product_record(item, min_price, max_price, marketplaces)
        if not errors and known_signatures is not None:
            if record_signature(item) in known_signatures:
                errors = ["duplicate_signature"]
        if not errors:
            return item, []
        last_errors = errors
    return generate_product_record(idx, min_price, max_price, marketplaces, range_template), last_errors


def build_variant_payload(category: str) -> tuple[str, list[str]]:
    color = random.choice(COLORS)
    material = random.choice(MATERIALS)
    edition = random.choice(EDITION_OPTIONS)
    if category in {"electronics", "gaming", "photo_video"}:
        capacity = random.choice(CAPACITY_OPTIONS)
        return f"{capacity}, {color}, {edition}", [capacity, color, edition]
    if category in {"fashion", "travel"}:
        size = random.choice(SIZE_OPTIONS)
        return f"{size}, {material}, {color}", [size, material, color]
    if category in {"home_appliances", "kitchen", "home_office"}:
        capacity = random.choice(CAPACITY_OPTIONS)
        return f"{capacity}, {material}, {edition}", [capacity, material, edition]
    size = random.choice(SIZE_OPTIONS)
    return f"{size}, {color}, {edition}", [size, color, edition]


def generate_product_record(
    idx: int,
    min_price: int,
    max_price: int,
    marketplaces: tuple[str, ...],
    range_template: str,
) -> dict[str, object]:
    template = random.choice(TEMPLATES)
    brand = random.choice(template.brand_pool)
    model = random.choice(template.model_pool)
    descriptor = random.choice(template.descriptor_pool)
    audience = random.choice(template.audience_pool)
    variant_text, variant_keywords = build_variant_payload(template.category)
    sku = f"{brand[:3].upper()}-{template.category[:3].upper()}-{idx:07d}-{random.randint(100, 999)}"

    budget_hint = random.randint(min_price, max_price)
    width = choose_range_width(range_template, budget_hint)
    center_price = random.randint(min_price, max_price)
    price_min = max(min_price, center_price - width)
    price_max = min(max_price, center_price + width)
    if price_max < price_min:
        price_max = price_min

    title = clean_text(f"{template.base_name} {brand} {model} {variant_text}")
    subtitle = clean_text(f"{descriptor}, {audience}, SKU {sku}")
    search_query = clean_text(f"{template.base_name} {brand} {model} {descriptor} {variant_text}")
    description = (
        f"{title} — {subtitle}. Физический товар для покупки на маркетплейсе, "
        "без услуг и подписок."
    )

    # Hard guard against accidental non-product vocabulary.
    if contains_forbidden_tokens(title, subtitle, description, search_query):
        return generate_product_record(idx, min_price, max_price, marketplaces, range_template)

    return {
        "id": f"prd_{idx:07d}_{uuid.uuid4().hex[:8]}",
        "sku": sku,
        "title": title,
        "description": description,
        "category": template.category,
        "audience": audience,
        "brand": brand,
        "model": model,
        "attributes": {
            "descriptor": descriptor,
            "tags": list(template.tags),
            "is_physical_product": True,
            "is_marketplace_ready": True,
        },
        "price": {
            "currency": "RUB",
            "min": price_min,
            "max": price_max,
            "avg": int((price_min + price_max) / 2),
        },
        "search": {
            "query": search_query,
            "keywords": [
                template.base_name,
                brand,
                model,
                descriptor,
                *variant_keywords,
                template.category,
            ],
        },
        "marketplaces": build_search_links(search_query, marketplaces),
    }


def validate_bounds(min_price: int, max_price: int, count: int) -> None:
    if count <= 0:
        raise ValueError("--count must be > 0")
    if min_price <= 0:
        raise ValueError("--min-price must be > 0")
    if max_price < min_price:
        raise ValueError("--max-price must be >= --min-price")


def validate_sla_args(args: argparse.Namespace) -> None:
    ratio_fields = ("sla_min_valid_ratio", "sla_max_duplicate_ratio")
    for field in ratio_fields:
        value = float(getattr(args, field))
        if value < 0 or value > 1:
            raise ValueError(f"--{field.replace('_', '-')} must be in [0,1]")
    int_fields = (
        "sla_max_forbidden_hits",
        "sla_max_missing_marketplace_links",
        "sla_max_price_out_of_bounds",
        "sla_max_malformed_records",
    )
    for field in int_fields:
        value = int(getattr(args, field))
        if value < 0:
            raise ValueError(f"--{field.replace('_', '-')} must be >= 0")


def update_quality_counters(
    item: dict[str, object],
    stats: QualityStats,
    signatures: set[str],
    categories: Counter[str],
    brands: Counter[str],
    marketplaces_counter: Counter[str],
    min_price_seen: list[int],
    max_price_seen: list[int],
    validation_errors: list[str],
) -> None:
    stats.generated += 1
    if validation_errors:
        stats.invalid += 1
        for err in validation_errors:
            if err == "forbidden_token":
                stats.forbidden_hits += 1
            elif err.startswith("missing_marketplace:"):
                stats.missing_marketplace_links += 1
            elif err in ("price_out_of_bounds", "price_avg_out_of_bounds"):
                stats.price_out_of_bounds += 1
            else:
                stats.malformed_records += 1
    else:
        stats.valid += 1

    signature = record_signature(item)
    if signature in signatures:
        stats.duplicate_signatures += 1
    else:
        signatures.add(signature)

    categories[str(item.get("category", "unknown"))] += 1
    brands[str(item.get("brand", "unknown"))] += 1

    price = item.get("price", {})
    if isinstance(price, dict):
        min_price_seen.append(int(price.get("min", 0)))
        max_price_seen.append(int(price.get("max", 0)))

    raw_marketplaces = item.get("marketplaces", {})
    if isinstance(raw_marketplaces, dict):
        for key, value in raw_marketplaces.items():
            if str(value).strip():
                marketplaces_counter[str(key)] += 1


def write_quality_report(
    path: Path,
    stats: QualityStats,
    categories: Counter[str],
    brands: Counter[str],
    marketplaces_counter: Counter[str],
    min_price_seen: list[int],
    max_price_seen: list[int],
    top_k: int,
) -> None:
    dataset_min = min(min_price_seen) if min_price_seen else None
    dataset_max = max(max_price_seen) if max_price_seen else None
    report = {
        "stats": stats.to_dict(),
        "valid_ratio": round(stats.valid / max(1, stats.generated), 6),
        "duplicate_ratio": round(stats.duplicate_signatures / max(1, stats.generated), 6),
        "price_coverage": {
            "dataset_min_price": dataset_min,
            "dataset_max_price": dataset_max,
        },
        "top_categories": categories.most_common(top_k),
        "top_brands": brands.most_common(top_k),
        "marketplace_link_coverage": dict(marketplaces_counter),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def evaluate_sla(stats: QualityStats, args: argparse.Namespace) -> list[str]:
    violations: list[str] = []
    valid_ratio = stats.valid / max(1, stats.generated)
    duplicate_ratio = stats.duplicate_signatures / max(1, stats.generated)

    if valid_ratio < args.sla_min_valid_ratio:
        violations.append(
            f"valid_ratio {valid_ratio:.6f} < sla_min_valid_ratio {args.sla_min_valid_ratio:.6f}"
        )
    if duplicate_ratio > args.sla_max_duplicate_ratio:
        violations.append(
            f"duplicate_ratio {duplicate_ratio:.6f} > sla_max_duplicate_ratio {args.sla_max_duplicate_ratio:.6f}"
        )
    if stats.forbidden_hits > args.sla_max_forbidden_hits:
        violations.append(
            f"forbidden_hits {stats.forbidden_hits} > sla_max_forbidden_hits {args.sla_max_forbidden_hits}"
        )
    if stats.missing_marketplace_links > args.sla_max_missing_marketplace_links:
        violations.append(
            "missing_marketplace_links "
            f"{stats.missing_marketplace_links} > "
            f"sla_max_missing_marketplace_links {args.sla_max_missing_marketplace_links}"
        )
    if stats.price_out_of_bounds > args.sla_max_price_out_of_bounds:
        violations.append(
            f"price_out_of_bounds {stats.price_out_of_bounds} > "
            f"sla_max_price_out_of_bounds {args.sla_max_price_out_of_bounds}"
        )
    if stats.malformed_records > args.sla_max_malformed_records:
        violations.append(
            f"malformed_records {stats.malformed_records} > "
            f"sla_max_malformed_records {args.sla_max_malformed_records}"
        )
    return violations


def write_ndjson(
    path: Path,
    records: int,
    min_price: int,
    max_price: int,
    marketplaces: tuple[str, ...],
    range_template: str,
    stats: QualityStats,
    signatures: set[str],
    categories: Counter[str],
    brands: Counter[str],
    marketplaces_counter: Counter[str],
    min_price_seen: list[int],
    max_price_seen: list[int],
) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for idx in range(1, records + 1):
            item, validation_errors = generate_valid_product_record(
                idx,
                min_price,
                max_price,
                marketplaces,
                range_template,
                max_attempts=80,
                known_signatures=signatures,
            )
            update_quality_counters(
                item=item,
                stats=stats,
                signatures=signatures,
                categories=categories,
                brands=brands,
                marketplaces_counter=marketplaces_counter,
                min_price_seen=min_price_seen,
                max_price_seen=max_price_seen,
                validation_errors=validation_errors,
            )
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")


def write_json(
    path: Path,
    records: int,
    min_price: int,
    max_price: int,
    marketplaces: tuple[str, ...],
    range_template: str,
    stats: QualityStats,
    signatures: set[str],
    categories: Counter[str],
    brands: Counter[str],
    marketplaces_counter: Counter[str],
    min_price_seen: list[int],
    max_price_seen: list[int],
) -> None:
    with path.open("w", encoding="utf-8") as fh:
        fh.write("[\n")
        for idx in range(1, records + 1):
            item, validation_errors = generate_valid_product_record(
                idx,
                min_price,
                max_price,
                marketplaces,
                range_template,
                max_attempts=80,
                known_signatures=signatures,
            )
            update_quality_counters(
                item=item,
                stats=stats,
                signatures=signatures,
                categories=categories,
                brands=brands,
                marketplaces_counter=marketplaces_counter,
                min_price_seen=min_price_seen,
                max_price_seen=max_price_seen,
                validation_errors=validation_errors,
            )
            prefix = "" if idx == 1 else ",\n"
            fh.write(prefix + json.dumps(item, ensure_ascii=False))
        fh.write("\n]\n")


def main() -> None:
    args = parse_args()
    random.seed(args.seed)
    selected_marketplaces = normalize_marketplaces(args.marketplaces)
    validate_bounds(args.min_price, args.max_price, args.count)
    validate_sla_args(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    stats = QualityStats()
    signatures: set[str] = set()
    categories: Counter[str] = Counter()
    brands: Counter[str] = Counter()
    marketplaces_counter: Counter[str] = Counter()
    min_price_seen: list[int] = []
    max_price_seen: list[int] = []

    if args.format == "ndjson":
        write_ndjson(
            args.output,
            records=args.count,
            min_price=args.min_price,
            max_price=args.max_price,
            marketplaces=selected_marketplaces,
            range_template=args.range_template,
            stats=stats,
            signatures=signatures,
            categories=categories,
            brands=brands,
            marketplaces_counter=marketplaces_counter,
            min_price_seen=min_price_seen,
            max_price_seen=max_price_seen,
        )
    else:
        write_json(
            args.output,
            records=args.count,
            min_price=args.min_price,
            max_price=args.max_price,
            marketplaces=selected_marketplaces,
            range_template=args.range_template,
            stats=stats,
            signatures=signatures,
            categories=categories,
            brands=brands,
            marketplaces_counter=marketplaces_counter,
            min_price_seen=min_price_seen,
            max_price_seen=max_price_seen,
        )

    write_quality_report(
        path=args.quality_report,
        stats=stats,
        categories=categories,
        brands=brands,
        marketplaces_counter=marketplaces_counter,
        min_price_seen=min_price_seen,
        max_price_seen=max_price_seen,
        top_k=max(1, args.top_k),
    )

    sla_violations = evaluate_sla(stats, args)
    if sla_violations:
        raise SystemExit(
            "SLA failed:\n- " + "\n- ".join(sla_violations) + f"\nSee report: {args.quality_report}"
        )

    if args.strict_quality and stats.invalid > 0:
        raise SystemExit(
            f"Quality validation failed: {stats.invalid} invalid records. "
            f"See report: {args.quality_report}"
        )

    print(
        f"Generated {args.count} products into {args.output} "
        f"(format={args.format}, marketplaces={','.join(selected_marketplaces)}). "
        f"Quality report: {args.quality_report}"
    )


if __name__ == "__main__":
    main()
