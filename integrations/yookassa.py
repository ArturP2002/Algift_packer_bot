from __future__ import annotations


class YooKassaIntegration:
    def __init__(self, shop_id: str, secret_key: str) -> None:
        self.shop_id = shop_id
        self.secret_key = secret_key

    async def create_payment_link(self, amount_rub: int, description: str, user_id: int, payment_id: str) -> str:
        _ = (description, user_id, payment_id)
        if not self.shop_id or not self.secret_key:
            return "https://yookassa.ru/"
        return f"https://yookassa.ru/payments/mock?amount={amount_rub}&payment_id={payment_id}"
