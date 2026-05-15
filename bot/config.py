"""Настройки из переменных окружения. Бросает понятную ошибку, если что-то не задано."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Не задана обязательная переменная окружения: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    webhook_base: str       # https://your-app.onrender.com
    webhook_secret: str     # любая длинная случайная строка


settings = Settings(
    bot_token=_require("BOT_TOKEN"),
    database_url=_require("DATABASE_URL"),
    webhook_base=_require("WEBHOOK_BASE"),
    webhook_secret=_require("WEBHOOK_SECRET"),
)
