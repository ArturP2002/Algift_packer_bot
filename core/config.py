from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import find_dotenv, load_dotenv


def _load_env() -> None:
    env_path = find_dotenv()
    if env_path:
        load_dotenv(env_path)
    else:
        load_dotenv()


_load_env()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    sqlite_path: str = "gift_bot.db"
    cache_ttl_seconds: int = 3600
    max_photo_count: int = 6
    stale_paid_cleanup_hours: int = 24
    one_time_request_price_rub: int = 149
    subscription_month_price_rub: int = 499
    one_time_request_price_stars: int = 149
    subscription_month_price_stars: int = 499
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    admin_ids: tuple[int, ...] = ()


def get_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not bot_token:
        raise RuntimeError("Missing required env variable: BOT_TOKEN")
    if not openai_api_key:
        raise RuntimeError("Missing required env variable: OPENAI_API_KEY")
    return Settings(
        bot_token=bot_token,
        openai_api_key=openai_api_key,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        sqlite_path=os.getenv("SQLITE_PATH", "gift_bot.db"),
        cache_ttl_seconds=int(os.getenv("CACHE_TTL_SECONDS", "3600")),
        max_photo_count=int(os.getenv("MAX_PHOTO_COUNT", "6")),
        stale_paid_cleanup_hours=int(os.getenv("STALE_PAID_CLEANUP_HOURS", "24")),
        one_time_request_price_rub=int(os.getenv("ONE_TIME_REQUEST_PRICE_RUB", "149")),
        subscription_month_price_rub=int(os.getenv("SUBSCRIPTION_MONTH_PRICE_RUB", "499")),
        one_time_request_price_stars=int(os.getenv("ONE_TIME_REQUEST_PRICE_STARS", "149")),
        subscription_month_price_stars=int(os.getenv("SUBSCRIPTION_MONTH_PRICE_STARS", "499")),
        yookassa_shop_id=os.getenv("YOOKASSA_SHOP_ID", "").strip(),
        yookassa_secret_key=os.getenv("YOOKASSA_SECRET_KEY", "").strip(),
        admin_ids=tuple(
            int(item.strip())
            for item in os.getenv("ADMIN_IDS", "").split(",")
            if item.strip().isdigit()
        ),
    )
