from aiogram.fsm.state import State, StatesGroup


class SurveyStates(StatesGroup):
    choosing_mode = State()
    choosing_reuse = State()
    age = State()
    gender = State()
    event = State()
    relation = State()
    custom_relation = State()
    budget = State()
    custom_budget = State()
    photos = State()
    hobbies = State()
