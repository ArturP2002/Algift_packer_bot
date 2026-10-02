from __future__ import annotations


class TelegramStarsIntegration:
    def __init__(self, provider_token: str) -> None:
        _ = provider_token

    async def create_invoice_payload(self, user_id: int, amount_rub: int, purpose: str, provider_payment_id: str) -> dict[str, str]:
        _ = user_id
        return {
            "title": "Оплата в Gift Bot",
            "description": purpose,
            "payload": provider_payment_id,
            "provider_token": "",
            "currency": "XTR",
            "amount": str(amount_rub),
        }
