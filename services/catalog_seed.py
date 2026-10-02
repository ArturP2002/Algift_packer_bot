"""Снимок каталога в репозитории: gift_bot.db в git не попадает, а без товаров бот не дает ссылок.

Локально после импорта каталог выгружается в data/catalog_seed.json.gz (его коммитят),
на сервере при запуске снимок загружается в базу, если там другой снимок или товаров нет.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

from peewee import chunked

from database.models import AffiliateProduct, AppSetting, db

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "catalog_seed.json.gz"
_VERSION_KEY = "catalog_seed_version"
_FIELDS = (
    "source",
    "external_id",
    "product_id",
    "sku",
    "title",
    "title_norm",
    "image_url",
    "price",
    "category",
    "marketplace",
    "store_title",
    "external_link",
    "tracking_link",
    "updated_at",
)
# 14 полей × 500 строк укладываются в лимит переменных SQLite на один INSERT.
_INSERT_CHUNK = 500

logger = logging.getLogger("gift_bot.catalog_seed")


def _version(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _remember_version(version: str) -> None:
    AppSetting.insert(key=_VERSION_KEY, value=version).on_conflict(
        conflict_target=[AppSetting.key],
        update={AppSetting.value: version, AppSetting.updated_at: datetime.utcnow()},
    ).execute()


def export_seed(path: Path = SEED_PATH) -> int:
    fields = [getattr(AffiliateProduct, name) for name in _FIELDS]
    rows = list(
        AffiliateProduct.select(*fields).order_by(AffiliateProduct.marketplace, AffiliateProduct.external_id).dicts()
    )
    for row in rows:
        row["updated_at"] = str(row["updated_at"]) if row["updated_at"] else None
    payload = json.dumps({"products": rows}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 — одинаковый каталог дает одинаковый файл, git не видит ложных изменений.
    with gzip.GzipFile(path, "wb", mtime=0) as file:
        file.write(payload)
    _remember_version(_version(path))
    return len(rows)


def sync_catalog_from_seed(path: Path = SEED_PATH) -> int | None:
    """Загружает снимок, если он новее загруженного. Возвращает число товаров или None, если делать нечего."""
    if not path.exists():
        logger.warning("Снимок каталога не найден: %s", path)
        return None
    version = _version(path)
    stored = AppSetting.get_or_none(AppSetting.key == _VERSION_KEY)
    if stored and stored.value == version and AffiliateProduct.select().exists():
        return None

    rows = json.loads(gzip.decompress(path.read_bytes()))["products"]
    sources = {row["source"] for row in rows}
    with db.atomic():
        AffiliateProduct.delete().where(AffiliateProduct.source.in_(sources)).execute()
        for chunk in chunked(rows, _INSERT_CHUNK):
            AffiliateProduct.insert_many(chunk).execute()
        _remember_version(version)
    logger.info("Каталог загружен из снимка: %s товаров", len(rows))
    return len(rows)
