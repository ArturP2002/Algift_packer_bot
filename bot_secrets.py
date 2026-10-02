
import os
from dotenv import find_dotenv, load_dotenv

env_path = find_dotenv()
if env_path:
    load_dotenv(env_path)
else:
    load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")


def validate_config() -> None:
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if missing:
        raise RuntimeError(
            "Отсутствуют переменные окружения: " + ", ".join(missing)
        )
