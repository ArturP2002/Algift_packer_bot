import unittest
from datetime import datetime

from database.models import AffiliateProduct, db, init_db
from services.budget_service import budget_floor, normalize_budget
from services.cache_service import CacheService
from services.product_service import ProductService


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        init_db(":memory:")
        AffiliateProduct.delete().execute()

    def tearDown(self) -> None:
        if not db.is_closed():
            db.close()

    def test_budget_normalization(self) -> None:
        self.assertEqual(normalize_budget("1000-3000"), 3000)
        self.assertEqual(normalize_budget("50000"), 50000)
        self.assertEqual(budget_floor("5000-10000"), 5000)
        self.assertEqual(budget_floor("40000"), 28000)

    def test_long_keyword_is_shortened_from_the_end(self) -> None:
        AffiliateProduct.create(
            source="manual",
            external_id="1",
            title="Колонка беспроводная JBL Flip 7",
            title_norm="колонка беспроводная jbl flip 7",
            price=9900,
            marketplace="mvideo",
            tracking_link="https://example.com/flip",
            updated_at=datetime.utcnow(),
        )
        links = ProductService().resolve_links(
            ["портативная колонка jbl flip для музыки на природе", "портативная колонка"],
            min_price=5000,
            max_price=11000,
        )
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["offers"][0]["url"], "https://example.com/flip")

    def test_product_offers_from_catalog(self) -> None:
        AffiliateProduct.create(
            source="manual",
            external_id="1",
            title="AirPods Pro 2 оригинал",
            title_norm="airpods pro 2 оригинал",
            price=24990,
            marketplace="ozon",
            tracking_link="https://example.com/ozon-airpods",
            updated_at=datetime.utcnow(),
        )
        AffiliateProduct.create(
            source="manual",
            external_id="2",
            title="AirPods Pro 2 наушники",
            title_norm="airpods pro 2 наушники",
            price=25990,
            marketplace="wildberries",
            tracking_link="https://example.com/wb-airpods",
            updated_at=datetime.utcnow(),
        )
        links = ProductService().resolve_links(["airpods pro 2"], min_price=20000, max_price=30000)
        self.assertEqual(len(links), 1)
        offers = links[0]["offers"]
        markets = {offer["marketplace"] for offer in offers}
        self.assertIn("ozon", markets)
        self.assertIn("wildberries", markets)
        self.assertTrue(all(offer["url"].startswith("https://") for offer in offers))

    def test_same_store_offers_are_diverse(self) -> None:
        products = [
            ("1", "Смартфон Apple iPhone 17 256GB Black (без RuStore)", 89999),
            ("2", "Смартфон Apple iPhone 17 256GB Sage (без RuStore)", 89999),
            ("3", "Смартфон Apple iPhone 17 256GB Blue (без RuStore)", 88999),
            ("4", "Смартфон Apple iPhone 17 512GB Black (без RuStore)", 99999),
            ("5", "Смартфон Apple iPhone 16 128GB Black (без RuStore)", 82999),
        ]
        for external_id, title, price in products:
            AffiliateProduct.create(
                source="manual",
                external_id=external_id,
                title=title,
                title_norm=title.lower(),
                price=price,
                marketplace="mvideo",
                tracking_link=f"https://example.com/{external_id}",
                updated_at=datetime.utcnow(),
            )
        offers = ProductService().find_offers(["смартфон apple iphone"], min_price=80000, max_price=100000)
        self.assertEqual(len(offers), 3)
        prices = [offer["price"] for offer in offers]
        self.assertEqual(prices, sorted(prices))
        self.assertEqual(len(set(prices)), 3)
        self.assertTrue(offers[0]["label"].startswith("Apple iPhone"))
        self.assertNotIn("М.Видео", offers[0]["label"])

    def test_similar_offers_exclude_same_product(self) -> None:
        AffiliateProduct.create(
            source="manual",
            external_id="1",
            title="Парфюмерная вода Amouage Interlude Black Iris Man",
            title_norm="парфюмерная вода amouage interlude black iris man",
            price=50952,
            marketplace="goldapple",
            tracking_link="https://example.com/amouage-iris",
            updated_at=datetime.utcnow(),
        )
        AffiliateProduct.create(
            source="manual",
            external_id="2",
            title="Парфюмерная вода Amouage Reflection Man",
            title_norm="парфюмерная вода amouage reflection man",
            price=42000,
            marketplace="goldapple",
            tracking_link="https://example.com/amouage-reflection",
            updated_at=datetime.utcnow(),
        )
        AffiliateProduct.create(
            source="manual",
            external_id="3",
            title="Парфюмерная вода Amouage Lyric Man",
            title_norm="парфюмерная вода amouage lyric man",
            price=39000,
            marketplace="goldapple",
            tracking_link="https://example.com/amouage-lyric",
            updated_at=datetime.utcnow(),
        )
        similar = ProductService().find_similar_offers(
            name="Парфюмерная вода Amouage Interlude Black Iris Man",
            keywords=["парфюм amouage", "мужской парфюм amouage"],
            exclude_urls={"https://example.com/amouage-iris"},
            max_offers=5,
        )
        urls = {offer["url"] for offer in similar}
        self.assertNotIn("https://example.com/amouage-iris", urls)
        self.assertTrue(urls)
        self.assertTrue(all("amouage" in offer["title"].lower() for offer in similar))
        self.assertFalse(any("interlude black iris" in offer["title"].lower() for offer in similar))

    def test_cache_key_determinism(self) -> None:
        cache = CacheService(ttl_seconds=100)
        payload = {
            "age": 23,
            "gender": "женский",
            "event": "birthday",
            "relation": "daughter",
            "budget": 50000,
            "hobbies": "танцы",
            "mode": "extended",
        }
        self.assertEqual(cache.make_key(payload), cache.make_key(payload.copy()))

    def test_cache_hit_miss(self) -> None:
        cache = CacheService(ttl_seconds=100)
        key = cache.make_key(
            {
                "age": 20,
                "gender": "женский",
                "event": "birthday",
                "relation": "friend",
                "budget": 5000,
                "hobbies": "",
                "mode": "quick",
            }
        )
        self.assertIsNone(cache.get(key))
        cache.set(key, {"ok": True})
        self.assertEqual(cache.get(key), {"ok": True})
        stats = cache.stats()
        self.assertEqual(stats.misses, 1)
        self.assertEqual(stats.hits, 1)


if __name__ == "__main__":
    unittest.main()
