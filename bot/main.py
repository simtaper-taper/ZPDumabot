"""Точка входа. Поднимает aiohttp-сервер, регистрирует вебхук в Telegram."""
from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import settings
from bot.db import close_db, init_db
from bot.handlers import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot) -> None:
    await init_db()
    url = f"{settings.webhook_base.rstrip('/')}/webhook/{settings.webhook_secret}"
    await bot.set_webhook(
        url=url,
        # Без этого в группах прилетают только команды боту.
        allowed_updates=[
            "message",
            "edited_message",
            "channel_post",
            "edited_channel_post",
        ],
        drop_pending_updates=False,
    )
    info = await bot.get_webhook_info()
    logger.info("Webhook set: url=%s pending=%s", info.url, info.pending_update_count)


async def on_shutdown(bot: Bot) -> None:
    # Вебхук НЕ снимаем: пусть Telegram копит апдейты во время
    # рестартов и доставляет их, когда сервис снова поднимется.
    await close_db()


def build_app() -> web.Application:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(
        app, path=f"/webhook/{settings.webhook_secret}"
    )
    setup_application(app, dp, bot=bot)

    async def health(_: web.Request) -> web.Response:
        return web.Response(text="ok")

    app.router.add_get("/", health)
    return app


def main() -> None:
    port = int(os.getenv("PORT", "10000"))
    web.run_app(build_app(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
