import asyncio
import unittest
from datetime import datetime

from database.models import AffiliateProduct, db, init_db
from services.cache_service import CacheService
from services.product_service import ProductService
from services.recommendation_service import RecommendationContext, RecommendationService, RecommendationUnavailable


def make_context(**overrides) -> RecommendationContext:
    params = dict(
        mode="quick", age=30, gender="мужской", event="birthday", relation="friend", budget=10000, budget_min=5000
    )
    params.update(overrides)
    return RecommendationContext(**params)


def idea(name, keywords, price_min, price_max, category="", pitch="Короткая идея."):
    return {
        "name": name,
        "pitch": pitch,
        "category": category or name,
        "keywords": keywords,
        "price_min": price_min,
        "price_max": price_max,
    }


def choice(index, offer_ids, why="Подробное пояснение про выбранную модель."):
    return {
        "idea_index": index,
        "offer_ids": offer_ids,
        "why_for_person": why,
        "occasion_fit": "Уместно ко дню рождения.",
        "practical_value": "Будет пользоваться каждый день.",
        "presentation_tip": "Добавьте открытку.",
    }


class FakeGPTService:
    """Отвечает по имени схемы; selection=None — шаг выбора падает."""

    def __init__(self, ideas, selection=None):
        self.ideas = ideas
        self.selection = selection
        self.calls = []

    async def complete_json(self, *, name, instructions, prompt, schema, max_tokens=3000, temperature=0.4):
        self.calls.append({"name": name, "instructions": instructions, "prompt": prompt})
        if name == "gift_ideas":
            return {"ideas": self.ideas}
        if self.selection is None:
            raise RuntimeError("selection failed")
        return {"ideas": self.selection}


class FailingGPTService:
    async def complete_json(self, **kwargs):
        raise RuntimeError("401 invalid api key")


class CatalogTestCase(unittest.TestCase):
    products: tuple = ()

    def setUp(self) -> None:
        init_db(":memory:")
        AffiliateProduct.delete().execute()
        for external_id, title, price in self.products:
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

    def tearDown(self) -> None:
        if not db.is_closed():
            db.close()

    def run_service(self, gpt, context=None):
        service = RecommendationService(gpt, ProductService(), CacheService(3600))
        return asyncio.run(service.get_recommendations(context or make_context()))


class SelectionTests(CatalogTestCase):
    products = (
        ("flip7", "Колонка беспроводная JBL Flip 7", 9990),
        ("flip6", "Колонка беспроводная JBL Flip 6", 8490),
        ("charge", "Колонка беспроводная JBL Charge 5", 10990),
        ("mouse", "Игровая мышь Razer DeathAdder V3", 9999),
        ("blender", "Блендер настольный Korting", 7990),
    )

    def test_buttons_are_only_chosen_offers(self) -> None:
        gpt = FakeGPTService(
            [idea("Колонка JBL", ["колонка jbl", "портативная колонка"], 8000, 11000)],
            # i0o9 — несуществующий id, i1o0 — чужой идеи: оба отбрасываются.
            [choice(0, ["i0o2", "i0o9", "i1o0", "i0o0"])],
        )
        items = self.run_service(gpt)
        self.assertEqual(len(items), 1)
        offers = items[0]["links"][0]["offers"]
        self.assertEqual(len(offers), 2)
        self.assertIn("Подробное пояснение про выбранную модель.", items[0]["reason"])
        self.assertIn("🎉 Почему к поводу: Уместно ко дню рождения.", items[0]["reason"])
        self.assertIn("🎀 Как подарить: Добавьте открытку.", items[0]["reason"])
        self.assertIn("Цена в каталоге", items[0]["reason"])
        self.assertNotIn("candidates", items[0])

    def test_selection_failure_falls_back_to_search(self) -> None:
        gpt = FakeGPTService(
            [idea("Колонка JBL", ["колонка jbl"], 8000, 11000, pitch="Он любит музыку в походах.")], selection=None
        )
        items = self.run_service(gpt)
        self.assertEqual(len(items[0]["links"][0]["offers"]), 3)
        self.assertTrue(items[0]["reason"].startswith("Он любит музыку в походах."))

    def test_empty_choice_falls_back_to_catalog_offers(self) -> None:
        gpt = FakeGPTService(
            [
                idea("Колонка JBL", ["колонка jbl"], 3000, 4000, category="аудио"),
                idea("Игровая мышь Razer", ["игровая мышь razer"], 7000, 9000, category="гейминг"),
            ],
            [choice(0, []), choice(1, [])],
        )
        items = self.run_service(gpt)
        # Пустой offer_ids больше не оставляет идею без ссылок — берём топ из каталога.
        self.assertEqual([item["name"] for item in items], ["Колонка JBL", "Игровая мышь Razer"])
        self.assertTrue(all(item["links"] for item in items))
        self.assertIn("Цена в каталоге", items[0]["reason"])

    def test_catalog_price_beats_model_estimate(self) -> None:
        gpt = FakeGPTService(
            [
                idea("Кулинарная книга", ["кулинарная книга"], 1000, 2000, category="книги"),
                idea("Настольная игра", ["настольная игра каркассон"], 6000, 8000, category="игры"),
                idea("Игровая мышь Razer", ["игровая мышь razer для геймеров", "игровая мышь"], 3000, 4000, category="гейминг"),
            ],
            selection=None,
        )
        items = self.run_service(gpt)
        # Идеи без матча в каталоге не показываем; остаётся только мышь со ссылкой.
        self.assertEqual([item["name"] for item in items], ["Игровая мышь Razer"])
        self.assertEqual([o["url"] for o in items[0]["links"][0]["offers"]], ["https://example.com/mouse"])
        self.assertIn("Цена в каталоге: 9 999 ₽", items[0]["reason"])

    def test_missing_catalog_idea_is_dropped(self) -> None:
        gpt = FakeGPTService(
            [idea("Штатив Manfrotto", ["штатив manfrotto", "штатив"], 5000, 7000, category="фото")],
            selection=None,
        )
        items = self.run_service(gpt)
        self.assertEqual(items, [])

    def test_exclude_names_skip_recent_gift(self) -> None:
        gpt = FakeGPTService(
            [idea("Колонка JBL Flip", ["колонка jbl", "портативная колонка"], 8000, 11000, category="аудио")],
            selection=None,
        )
        items = self.run_service(gpt, make_context(exclude_names=["Колонка JBL Flip"]))
        self.assertEqual(items, [])

    def test_category_limit(self) -> None:
        gpt = FakeGPTService(
            [idea(f"Идея {n}", ["колонка jbl"], 8000, 9000, category="Аудио") for n in range(4)],
            selection=None,
        )
        items = self.run_service(gpt)
        self.assertEqual(len(items), 2)

    def test_reason_fits_telegram_limit(self) -> None:
        long_text = "Очень подробное пояснение. " * 200
        gpt = FakeGPTService(
            [idea("Колонка JBL", ["колонка jbl"], 8000, 11000)], [choice(0, ["i0o0"], why=long_text)]
        )
        items = self.run_service(gpt)
        self.assertLessEqual(len(items[0]["reason"]), 3700)
        self.assertIn("Цена в каталоге", items[0]["reason"])


class PromptTests(CatalogTestCase):
    products = (("book", "Книга про танцы", 6500),)

    def test_prompt_uses_human_labels(self) -> None:
        gpt = FakeGPTService([idea("Книга", ["книга"], 6000, 7000)], selection=[choice(0, ["i0o0"])])
        context = make_context(gender="женский", relation="daughter", age=23, hobbies="танцы")
        self.run_service(gpt, context)
        prompts = " ".join(call["prompt"] for call in gpt.calls)
        self.assertIn("Получатель: дочь, 23 года, женщина.", prompts)
        self.assertIn("Повод: день рождения.", prompts)
        self.assertIn("Бюджет: 5 000–10 000 ₽ (допустимо до 11 000 ₽).", prompts)
        self.assertIn("Ориентиры каталога", prompts)
        self.assertNotIn("birthday", prompts)
        self.assertNotIn("daughter", prompts)

    def test_price_window_uses_selected_budget_range(self) -> None:
        context = make_context()
        self.assertEqual(context.price_window(), (5000, 11000))
        context.budget_min = 0
        self.assertEqual(context.price_window(), (7000, 11000))


class RecommendationFailureTests(CatalogTestCase):
    def test_model_failure_gives_no_template_ideas(self) -> None:
        service = RecommendationService(FailingGPTService(), ProductService(), CacheService(3600))
        with self.assertRaises(RecommendationUnavailable):
            asyncio.run(service.get_recommendations(make_context()))


if __name__ == "__main__":
    unittest.main()
