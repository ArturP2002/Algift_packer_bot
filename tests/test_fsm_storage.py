import asyncio
import unittest

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey

from bot.fsm_storage import SqliteStorage
from bot.states.survey import SurveyStates
from database.models import FsmRecord, db, init_db

KEY = StorageKey(bot_id=1, chat_id=42, user_id=42)


class SqliteStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        init_db(":memory:")

    def tearDown(self) -> None:
        if not db.is_closed():
            db.close()

    def test_survey_survives_restart(self) -> None:
        async def scenario():
            before = FSMContext(storage=SqliteStorage(), key=KEY)
            await before.set_state(SurveyStates.hobbies)
            await before.update_data(age=25, relation="Коллега", photo_urls=["u1"], pending_reco=True)

            after = FSMContext(storage=SqliteStorage(), key=KEY)
            self.assertEqual(await after.get_state(), SurveyStates.hobbies.state)
            self.assertEqual(
                await after.get_data(), {"age": 25, "relation": "Коллега", "photo_urls": ["u1"], "pending_reco": True}
            )
            self.assertTrue(await after.get_value("pending_reco"))

        asyncio.run(scenario())

    def test_clear_removes_record(self) -> None:
        async def scenario():
            state = FSMContext(storage=SqliteStorage(), key=KEY)
            await state.set_state(SurveyStates.age)
            await state.update_data(mode="quick")
            await state.clear()
            self.assertIsNone(await state.get_state())
            self.assertEqual(await state.get_data(), {})
            self.assertEqual(FsmRecord.select().count(), 0)

        asyncio.run(scenario())

    def test_users_are_isolated(self) -> None:
        async def scenario():
            first = FSMContext(storage=SqliteStorage(), key=KEY)
            second = FSMContext(storage=SqliteStorage(), key=StorageKey(bot_id=1, chat_id=7, user_id=7))
            await first.update_data(budget=3000)
            await second.update_data(budget=50000)
            self.assertEqual(await first.get_value("budget"), 3000)
            self.assertEqual(await second.get_value("budget"), 50000)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
