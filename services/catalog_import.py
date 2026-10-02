from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from database.models import AffiliateProduct


def normalize_title(value: str) -> str:
    lowered = value.lower().strip()
    return re.sub(r"\s+", " ", lowered)


def to_price_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(round(float(value))))
    text = str(value).replace("\xa0", " ").replace(" ", "").replace(",", ".")
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return 0
    return max(0, int(round(float(match.group(1)))))


def upsert_product(
    *,
    source: str,
    external_id: str,
    title: str,
    url: str,
    price: int,
    marketplace: str,
    product_id: str | None = None,
    image_url: str | None = None,
    category: str | None = None,
    store_title: str | None = None,
) -> None:
    title = (title or "").strip()
    url = (url or "").strip()
    if not title or not url or not external_id:
        return
    defaults = {
        "product_id": product_id,
        "title": title[:500],
        "title_norm": normalize_title(title)[:500],
        "image_url": image_url,
        "price": price,
        "category": (category or "")[:255] or None,
        "marketplace": (marketplace or "").strip().lower() or "unknown",
        "store_title": store_title,
        "external_link": url,
        "tracking_link": url,
        "updated_at": datetime.utcnow(),
    }
    product, created = AffiliateProduct.get_or_create(
        source=source,
        external_id=str(external_id),
        defaults=defaults,
    )
    if not created:
        for key, value in defaults.items():
            setattr(product, key, value)
        product.save()
