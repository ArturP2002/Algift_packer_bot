from aiogram import Bot, Dispatcher
from bot.fsm_storage import SqliteStorage
from bot.middlewares.logging import DetailedLoggingMiddleware


def build_bot_and_dispatcher(bot_token: str) -> tuple[Bot, Dispatcher]:
    storage = SqliteStorage()
    bot = Bot(token=bot_token)
    dp = Dispatcher(storage=storage)
    middleware = DetailedLoggingMiddleware()
    dp.message.middleware(middleware)
    dp.callback_query.middleware(middleware)
    dp.pre_checkout_query.middleware(middleware)
    return bot, dp
