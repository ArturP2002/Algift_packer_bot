from __future__ import annotations

from core.config import Settings
from database.repository import Repository
from integrations.telegram_stars import TelegramStarsIntegration
from integrations.yookassa import YooKassaIntegration
from services.cache_service import CacheService
from services.gpt_service import GPTService
from services.payment_service import PaymentService
from services.product_service import ProductService
from services.recommendation_service import RecommendationService


class ServiceContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repository = Repository()
        self.cache_service = CacheService(settings.cache_ttl_seconds)
        self.product_service = ProductService()
        self.gpt_service = GPTService(settings.openai_api_key, settings.openai_model)
        self.recommendation_service = RecommendationService(
            gpt_service=self.gpt_service,
            product_service=self.product_service,
            cache_service=self.cache_service,
        )
        self.payment_service = PaymentService(
            yookassa=YooKassaIntegration(settings.yookassa_shop_id, settings.yookassa_secret_key),
            stars=TelegramStarsIntegration(""),
            repository=self.repository,
            one_time_request_price_rub=settings.one_time_request_price_rub,
            monthly_subscription_price_rub=settings.subscription_month_price_rub,
            one_time_request_price_stars=settings.one_time_request_price_stars,
            monthly_subscription_price_stars=settings.subscription_month_price_stars,
        )
