import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup

from bot.handlers import start
from bot.states.survey import SurveyStates

USER = SimpleNamespace(id=42, username="tester")


def make_state() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=USER.id, user_id=USER.id))


def make_message(text: str | None = None, photo=None) -> SimpleNamespace:
    bot = SimpleNamespace(edit_message_text=AsyncMock(), delete_message=AsyncMock(), token="token")
    return SimpleNamespace(
        bot=bot,
        chat=SimpleNamespace(id=USER.id),
        from_user=USER,
        text=text,
        photo=photo,
        answer=AsyncMock(return_value=SimpleNamespace(message_id=100)),
        delete=AsyncMock(),
    )


def sent_texts(message) -> list[str]:
    return [call.args[0] for call in message.answer.await_args_list]


class SurveyFlowTests(unittest.TestCase):
    def pick_budget(self, mode: str):
        async def scenario():
            state = make_state()
            await state.set_state(SurveyStates.budget)
            await state.update_data(mode=mode)
            message = make_message()
            callback = SimpleNamespace(data="budget:5000-10000", message=message, answer=AsyncMock())
            await start.budget(callback, state)
            return state, message

        return asyncio.run(scenario())

    def test_quick_mode_skips_photos(self) -> None:
        state, message = self.pick_budget("quick")
        self.assertEqual(asyncio.run(state.get_state()), SurveyStates.hobbies.state)
        self.assertEqual(sent_texts(message), [start.texts.ASK_HOBBIES])

    def test_smart_mode_asks_photos_with_done_button(self) -> None:
        state, message = self.pick_budget("extended")
        self.assertEqual(asyncio.run(state.get_state()), SurveyStates.photos.state)
        self.assertEqual(sent_texts(message)[0], start.texts.ASK_PHOTOS)
        self.assertIsInstance(message.answer.await_args_list[-1].kwargs["reply_markup"], ReplyKeyboardMarkup)

    def test_done_after_photo_does_not_say_without_photo(self) -> None:
        async def scenario():
            state = make_state()
            await state.set_state(SurveyStates.photos)
            await state.update_data(mode="extended", photos_count=1, photo_urls=["https://example.com/1.jpg"])
            message = make_message("Готово")
            await start.collect_photos(message, state)
            return state, message

        state, message = asyncio.run(scenario())
        self.assertNotIn(start.texts.PHOTO_SKIPPED, sent_texts(message))
        self.assertEqual(sent_texts(message), [start.texts.ASK_HOBBIES])
        self.assertEqual(asyncio.run(state.get_state()), SurveyStates.hobbies.state)

    def test_done_without_photos_warns(self) -> None:
        async def scenario():
            state = make_state()
            await state.set_state(SurveyStates.photos)
            await state.update_data(mode="extended")
            message = make_message("готово")
            await start.collect_photos(message, state)
            return message

        message = asyncio.run(scenario())
        self.assertEqual(sent_texts(message), [start.texts.PHOTO_SKIPPED, start.texts.ASK_HOBBIES])

    def test_photo_status_is_sent_below_photo(self) -> None:
        async def scenario():
            state = make_state()
            await state.set_state(SurveyStates.photos)
            await state.update_data(mode="extended", photo_status_message_id=77)
            message = make_message(photo=[SimpleNamespace(file_id="f1")])
            message.bot.get_file = AsyncMock(return_value=SimpleNamespace(file_path="photos/1.jpg"))
            message.bot.container = SimpleNamespace(gpt_service=SimpleNamespace(photo_has_face=AsyncMock(return_value=True)))
            await start.collect_photos(message, state)
            return state, message

        state, message = asyncio.run(scenario())
        message.bot.delete_message.assert_awaited_once_with(chat_id=USER.id, message_id=77)
        message.bot.edit_message_text.assert_not_awaited()
        self.assertEqual(sent_texts(message), [start.texts.PHOTO_ADDED.format(count=1)])
        self.assertEqual(asyncio.run(state.get_data())["photo_status_message_id"], 100)

    def test_photo_without_face_is_rejected(self) -> None:
        async def scenario():
            state = make_state()
            await state.set_state(SurveyStates.photos)
            await state.update_data(mode="extended")
            message = make_message(photo=[SimpleNamespace(file_id="f1")])
            message.bot.get_file = AsyncMock(return_value=SimpleNamespace(file_path="photos/1.jpg"))
            message.bot.container = SimpleNamespace(gpt_service=SimpleNamespace(photo_has_face=AsyncMock(return_value=False)))
            await start.collect_photos(message, state)
            return state, message

        state, message = asyncio.run(scenario())
        self.assertEqual(sent_texts(message), [start.texts.PHOTO_NO_FACE])
        self.assertEqual(asyncio.run(state.get_data()).get("photos_count", 0), 0)

    def test_new_pick_asks_reuse_when_last_survey_exists(self) -> None:
        async def scenario():
            state = make_state()
            last_survey = {
                "mode": "quick",
                "age": 30,
                "gender": "женский",
                "event": "birthday",
                "relation": "girlfriend",
                "budget": 10000,
                "budget_min": 5000,
                "hobbies": "йога",
            }
            await state.update_data(last_survey=last_survey)
            message = make_message()
            callback = SimpleNamespace(data="pick:again", message=message, from_user=USER, answer=AsyncMock())
            await start.pick_again(callback, state)
            return state, message

        state, message = asyncio.run(scenario())
        self.assertEqual(asyncio.run(state.get_state()), SurveyStates.choosing_reuse.state)
        text = sent_texts(message)[0]
        self.assertIn("Как продолжим новый подбор?", text)
        self.assertIn("йога", text)
        markup = message.answer.await_args_list[0].kwargs["reply_markup"]
        callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        self.assertEqual(callbacks, ["pick:reuse", "pick:fresh"])

    def test_pick_fresh_opens_mode_choice(self) -> None:
        async def scenario():
            state = make_state()
            await state.set_state(SurveyStates.choosing_reuse)
            await state.update_data(
                last_survey={
                    "mode": "quick",
                    "age": 30,
                    "gender": "женский",
                    "event": "birthday",
                    "relation": "girlfriend",
                    "budget": 10000,
                }
            )
            message = make_message()
            message.bot.container = SimpleNamespace(
                payment_service=SimpleNamespace(
                    get_access_state=lambda _uid: SimpleNamespace(has_subscription=True, paid_requests_left=0)
                ),
                repository=SimpleNamespace(get_or_create_user=lambda *a, **k: None),
            )
            callback = SimpleNamespace(data="pick:fresh", message=message, from_user=USER, answer=AsyncMock())
            await start.pick_fresh(callback, state)
            return state, message

        state, message = asyncio.run(scenario())
        self.assertEqual(asyncio.run(state.get_state()), SurveyStates.choosing_mode.state)
        self.assertEqual(sent_texts(message)[0], start.texts.START_PICK_MODE)


if __name__ == "__main__":
    unittest.main()
