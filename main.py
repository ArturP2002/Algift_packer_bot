
import asyncio
import logging
from bot.handlers import build_root_router
from bot_init import build_bot_and_dispatcher
from core.config import get_settings
from core.logger import setup_logging
from database.migrations import run_migrations
from database.models import db, init_db
from services.container import ServiceContainer

logger = logging.getLogger("gift_bot.main")


async def main() -> None:
    setup_logging()
    settings = get_settings()
    init_db(settings.sqlite_path)
    run_migrations(db)
    container = ServiceContainer(settings)
    cleaned = container.payment_service.cleanup_stale_paid_requests(settings.stale_paid_cleanup_hours)
    logger.info("Очистка висящих paid записей завершена: %s", cleaned)

    bot, dp = build_bot_and_dispatcher(settings.bot_token)
    bot.container = container
    dp.include_router(build_root_router())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
