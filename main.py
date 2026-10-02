
import asyncio
import logging
from bot.handlers import build_root_router
from bot_init import build_bot_and_dispatcher
from core.config import get_settings
from core.logger import setup_logging
from database.migrations import run_migrations
from database.models import db, init_db
from services.catalog_seed import sync_catalog_from_seed
from services.container import ServiceContainer

logger = logging.getLogger("gift_bot.main")


async def main() -> None:
    setup_logging()
    settings = get_settings()
    init_db(settings.sqlite_path)
    run_migrations(db)
    sync_catalog_from_seed()
    container = ServiceContainer(settings)
    catalog_size = container.product_service.catalog_size()
    if catalog_size:
        logger.info("Товаров в каталоге: %s", catalog_size)
    else:
        logger.warning("Каталог товаров пуст: идеи будут без ссылок. Нужен data/catalog_seed.json.gz")
    cleaned = container.payment_service.cleanup_stale_paid_requests(settings.stale_paid_cleanup_hours)
    logger.info("Очистка висящих paid записей завершена: %s", cleaned)

    bot, dp = build_bot_and_dispatcher(settings.bot_token)
    bot.container = container
    dp.include_router(build_root_router())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
