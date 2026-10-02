from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any

from core.config import get_settings
from core.logger import setup_logging
from database.migrations import run_migrations
from database.models import AffiliateProduct, db, init_db
from services.catalog_import import to_price_int, upsert_product


logger = logging.getLogger("gift_bot.import_manual")

SOURCE = "manual"

# Не годятся в подарок: б/у, уценка, SIM-комплекты операторов, пополнения иностранных аккаунтов,
# чехлы (иначе по запросу «airpods» в малом бюджете найдётся чехол для AirPods), расходники.
EXCLUDED_TITLE_RE = re.compile(
    r"восстановлен|уцен[её]н|комплект для голосовой|sim-карт|тарифн|^пополнение|карта оплаты|^чехол"
    r"|^одноразов|^блок бреющ|^ножев|феромон|в ассортименте",
    re.IGNORECASE,
)


def _iter_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_dir():
            files.extend(sorted(path.glob("*.json")))
        elif path.suffix == ".json" and path.exists():
            files.append(path)
        else:
            logger.warning("Пропускаю %s: не найден JSON", path)
    return files


def _import_file(path: Path) -> int:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    store = str(payload.get("store") or "").strip().lower()
    items = payload.get("items") or []
    if not store or not isinstance(items, list):
        logger.warning("Пропускаю %s: нет store или items", path.name)
        return 0
    saved = 0
    skipped = 0
    with db.atomic():
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "").strip()
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or "").strip()
            price = to_price_int(item.get("price"))
            if not item_id or not url or not title or price <= 0:
                continue
            if EXCLUDED_TITLE_RE.search(title) or item.get("in_stock") is False:
                skipped += 1
                continue
            upsert_product(
                source=SOURCE,
                external_id=f"{store}:{item_id}",
                product_id=item_id,
                title=title,
                url=url,
                price=price,
                category=str(item.get("category") or payload.get("category") or "") or None,
                marketplace=store,
                store_title=str(item.get("brand") or "") or None,
            )
            saved += 1
    logger.info("%s: импортировано %s товаров, отфильтровано %s", path.name, saved, skipped)
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description="Импорт товаров, собранных сборщиками из tools/collectors")
    parser.add_argument("paths", nargs="+", help="JSON-файлы или папки с ними")
    args = parser.parse_args()
    setup_logging()

    settings = get_settings()
    init_db(settings.sqlite_path)
    run_migrations(db)

    files = _iter_files(args.paths)
    total = sum(_import_file(path) for path in files)
    in_db = AffiliateProduct.select().where(AffiliateProduct.source == SOURCE).count()
    print(f"Файлов: {len(files)}; импортировано: {total}; ручных товаров в БД: {in_db}")


if __name__ == "__main__":
    main()
