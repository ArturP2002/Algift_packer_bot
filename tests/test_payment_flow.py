import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import start
from bot.states.survey import SurveyStates

SURVEY = {"age": 25, "gender": "мужской", "event": "birthday", "relation": "friend", "budget": 10000, "mode": "quick"}
USER = SimpleNamespace(id=42, username="tester")
BOT_USER = SimpleNamespace(id=999, username="gift_bot")


def make_state() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=BOT_USER.id, chat_id=USER.id, user_id=USER.id))


def make_bot() -> SimpleNamespace:
    container = SimpleNamespace(payment_service=MagicMock(), repository=MagicMock())
    return SimpleNamespace(container=container)


class PaymentFlowTests(unittest.TestCase):
    def run_async(self, coro):
        return asyncio.run(coro)

    def test_stars_payment_resumes_survey(self) -> None:
        async def scenario():
            state = make_state()
            await state.set_state(SurveyStates.hobbies)
            await state.update_data(**SURVEY, pending_reco=True)
            message = SimpleNamespace(
                bot=make_bot(),
                from_user=USER,
                answer=AsyncMock(),
                successful_payment=SimpleNamespace(invoice_payload="stars:one_time:42:abc"),
            )
            with patch.object(start, "_emit_recommendations", AsyncMock()) as emit, patch.object(
                start, "_send_cabinet_as_new_message", AsyncMock()
            ) as cabinet, patch.object(start.asyncio, "sleep", AsyncMock()):
                await start.successful_payment(message, state)
            emit.assert_awaited_once()
            self.assertIs(emit.await_args.args[2], USER)
            cabinet.assert_not_awaited()
            data = await state.get_data()
            self.assertEqual(data["budget"], SURVEY["budget"])
            self.assertTrue(data["paid_for_current_request"])
            self.assertFalse(data["pending_reco"])

        self.run_async(scenario())

    def test_yookassa_check_resumes_for_real_user(self) -> None:
        async def scenario():
            state = make_state()
            await state.update_data(**SURVEY, pending_reco=True)
            bot_message = SimpleNamespace(bot=make_bot(), from_user=BOT_USER, answer=AsyncMock())
            callback = SimpleNamespace(
                data="paycheck:yookassa:one_time:42:abc", from_user=USER, message=bot_message, answer=AsyncMock()
            )
            with patch.object(start, "_emit_recommendations", AsyncMock()) as emit, patch.object(
                start.asyncio, "sleep", AsyncMock()
            ):
                await start.check_yookassa(callback, state)
            emit.assert_awaited_once()
            self.assertIs(emit.await_args.args[2], USER)

        self.run_async(scenario())

    def test_payment_from_cabinet_opens_cabinet(self) -> None:
        async def scenario():
            state = make_state()
            message = SimpleNamespace(
                bot=make_bot(),
                from_user=USER,
                answer=AsyncMock(),
                successful_payment=SimpleNamespace(invoice_payload="stars:subscription:42:abc"),
            )
            with patch.object(start, "_emit_recommendations", AsyncMock()) as emit, patch.object(
                start, "_send_cabinet_as_new_message", AsyncMock()
            ) as cabinet, patch.object(start.asyncio, "sleep", AsyncMock()):
                await start.successful_payment(message, state)
            emit.assert_not_awaited()
            cabinet.assert_awaited_once()

        self.run_async(scenario())


class RecommendationFailureFlowTests(unittest.TestCase):
    def test_model_failure_keeps_survey_and_does_not_charge(self) -> None:
        async def scenario():
            state = make_state()
            await state.set_state(SurveyStates.hobbies)
            await state.update_data(**SURVEY, hobbies="PS5")
            bot = make_bot()
            bot.container.payment_service.get_access_state.return_value = SimpleNamespace(
                has_subscription=False, paid_requests_left=1
            )
            bot.container.recommendation_service = SimpleNamespace(
                get_recommendations=AsyncMock(side_effect=start.RecommendationUnavailable("401"))
            )
            bot.container.gpt_service = MagicMock()
            bot.container.repository.get_or_create_user.return_value = SimpleNamespace(id=1, telegram_id=USER.id)
            bot.container.repository.recent_recommendation_names.return_value = []
            bot.container.repository.recent_downvoted_names.return_value = []
            message = SimpleNamespace(bot=bot, from_user=USER, answer=AsyncMock())
            await start._emit_recommendations(message, state)
            bot.container.payment_service.consume_request.assert_not_called()
            last_call = message.answer.await_args_list[-1]
            self.assertEqual(last_call.args[0], start.texts.RECO_UNAVAILABLE)
            self.assertEqual(last_call.kwargs["reply_markup"].inline_keyboard[0][0].callback_data, "reco:retry")
            self.assertEqual((await state.get_data())["budget"], SURVEY["budget"])

        asyncio.run(scenario())

    def test_pending_start_opens_mode_picker(self) -> None:
        async def scenario():
            state = make_state()
            await state.update_data(pending_start=True)
            message = SimpleNamespace(
                bot=make_bot(),
                from_user=USER,
                answer=AsyncMock(),
                chat=SimpleNamespace(id=USER.id),
                successful_payment=SimpleNamespace(invoice_payload="stars:one_time:42:abc"),
            )
            with patch.object(start, "_emit_recommendations", AsyncMock()) as emit, patch.object(
                start, "_render_screen", AsyncMock()
            ) as render, patch.object(start, "_send_cabinet_as_new_message", AsyncMock()) as cabinet, patch.object(
                start.asyncio, "sleep", AsyncMock()
            ):
                await start.successful_payment(message, state)
            emit.assert_not_awaited()
            cabinet.assert_not_awaited()
            render.assert_awaited_once()
            self.assertEqual(render.await_args.kwargs["text"], start.texts.START_PICK_MODE)
            self.assertFalse((await state.get_data()).get("pending_start"))

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
