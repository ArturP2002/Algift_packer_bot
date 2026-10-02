import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.handlers import start
from bot.keyboards.inline import product_links_keyboard
from database.models import ItemFeedback, RecommendationItem, db, init_db
from database.repository import Repository

ITEMS = [
    {
        "name": "Колонка JBL Flip 7",
        "reason": "Для походов.",
        "keywords": ["колонка jbl"],
        "links": [{"keyword": "колонка jbl", "offers": [{"title": "JBL Flip 7", "price": 9990, "url": "https://e.com/1", "label": "JBL Flip 7 · 9 990 ₽"}]}],
    },
    {"name": "Настольная игра", "reason": "Для вечеров.", "keywords": ["настольная игра"], "links": []},
]


class FeedbackTests(unittest.TestCase):
    def setUp(self) -> None:
        init_db(":memory:")
        self.repository = Repository()
        user = self.repository.get_or_create_user(100, "tester")
        request = self.repository.create_request(
            user,
            {"mode": "quick", "age": 30, "gender": "мужской", "event": "birthday", "relation": "friend", "budget": 10000},
        )
        self.items = self.repository.save_items(request, ITEMS)

    def tearDown(self) -> None:
        if not db.is_closed():
            db.close()

    def test_items_saved_with_shown_offers(self) -> None:
        self.assertEqual(len(self.items), 2)
        offers = json.loads(RecommendationItem.get_by_id(self.items[0].id).offers_json)
        self.assertEqual(offers, [{"title": "JBL Flip 7", "price": 9990, "url": "https://e.com/1"}])

    def test_vote_is_overwritten(self) -> None:
        item_id = self.items[0].id
        self.assertTrue(self.repository.set_feedback(item_id, 100, 1))
        self.assertTrue(self.repository.set_feedback(item_id, 100, -1))
        votes = list(ItemFeedback.select().where(ItemFeedback.item == item_id))
        self.assertEqual([vote.vote for vote in votes], [-1])
        self.assertFalse(self.repository.set_feedback(999, 100, 1))

    def test_stats(self) -> None:
        self.repository.set_feedback(self.items[0].id, 100, 1)
        self.repository.set_feedback(self.items[1].id, 100, -1)
        stats = self.repository.feedback_stats()
        self.assertEqual(stats["week"], (1, 1))
        self.assertEqual(stats["recent_down"], [{"name": "Настольная игра", "event": "birthday", "budget": 10000}])

    def test_handler_saves_vote_and_replaces_feedback_row(self) -> None:
        item_id = self.items[0].id
        markup = product_links_keyboard(ITEMS[0]["links"][0], item_id)
        message = SimpleNamespace(reply_markup=markup, edit_reply_markup=AsyncMock())
        callback = SimpleNamespace(
            data=f"fb:{item_id}:up",
            from_user=SimpleNamespace(id=100),
            bot=SimpleNamespace(container=SimpleNamespace(repository=self.repository)),
            message=message,
            answer=AsyncMock(),
        )
        asyncio.run(start.item_feedback(callback))

        self.assertEqual(ItemFeedback.get(ItemFeedback.item == item_id).vote, 1)
        new_markup = message.edit_reply_markup.await_args.kwargs["reply_markup"]
        rows = new_markup.inline_keyboard
        self.assertEqual(rows[0][0].url, "https://e.com/1")
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[-1][0].text.startswith("✅ Оценка учтена"))

    def test_feedback_row_without_offers(self) -> None:
        markup = product_links_keyboard(None, self.items[1].id)
        self.assertEqual(len(markup.inline_keyboard), 1)
        self.assertEqual(markup.inline_keyboard[0][1].callback_data, f"fb:{self.items[1].id}:down")


if __name__ == "__main__":
    unittest.main()
