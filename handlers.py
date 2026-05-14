"""Хендлеры. Минимум логики: ловим всё, складываем в БД."""
from __future__ import annotations

import logging
from typing import Optional

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.db import save_message, upsert_user

logger = logging.getLogger(__name__)
router = Router()


def _detect_payload(msg: Message) -> tuple[str, Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Возвращает (тип, file_id, file_unique_id, file_name, mime_type)."""
    if msg.text:
        return "text", None, None, None, None
    if msg.document:
        d = msg.document
        return "document", d.file_id, d.file_unique_id, d.file_name, d.mime_type
    if msg.photo:
        # Фото приходят в нескольких размерах — берём самое крупное.
        p = msg.photo[-1]
        return "photo", p.file_id, p.file_unique_id, None, None
    if msg.voice:
        v = msg.voice
        return "voice", v.file_id, v.file_unique_id, None, v.mime_type
    if msg.audio:
        a = msg.audio
        return "audio", a.file_id, a.file_unique_id, a.file_name, a.mime_type
    if msg.video:
        v = msg.video
        return "video", v.file_id, v.file_unique_id, v.file_name, v.mime_type
    if msg.video_note:
        vn = msg.video_note
        return "video_note", vn.file_id, vn.file_unique_id, None, None
    if msg.sticker:
        s = msg.sticker
        return "sticker", s.file_id, s.file_unique_id, None, None
    if msg.animation:
        an = msg.animation
        return "animation", an.file_id, an.file_unique_id, an.file_name, an.mime_type
    if msg.poll:
        return "poll", None, None, None, None
    if msg.location:
        return "location", None, None, None, None
    return "other", None, None, None, None


@router.message(Command("ping"))
async def cmd_ping(msg: Message) -> None:
    await msg.reply("pong")


@router.message(Command("stats"))
async def cmd_stats(msg: Message) -> None:
    """Быстрая диагностика: сколько сообщений собрано в этом чате."""
    from bot.db import _pool
    if _pool is None:
        await msg.reply("БД не инициализирована")
        return
    row = await _pool.fetchrow(
        "SELECT COUNT(*) AS n, MIN(ts) AS first_ts, MAX(ts) AS last_ts "
        "FROM messages WHERE chat_id = $1",
        msg.chat.id,
    )
    await msg.reply(
        f"Сохранено сообщений: <b>{row['n']}</b>\n"
        f"Первое: {row['first_ts']}\n"
        f"Последнее: {row['last_ts']}"
    )


# Catch-all — должен быть последним. Срабатывает на ВСЁ, что не перехватили выше.
@router.message()
async def catch_all(msg: Message) -> None:
    try:
        if msg.from_user is not None:
            full_name = (msg.from_user.full_name or "").strip() \
                or msg.from_user.username \
                or str(msg.from_user.id)
            await upsert_user(
                user_id=msg.from_user.id,
                username=msg.from_user.username,
                full_name=full_name,
                is_bot=msg.from_user.is_bot,
            )

        mtype, file_id, file_unique_id, file_name, mime_type = _detect_payload(msg)
        text = msg.text or msg.caption

        await save_message(
            chat_id=msg.chat.id,
            message_id=msg.message_id,
            user_id=msg.from_user.id if msg.from_user else None,
            ts=msg.date,
            text=text,
            reply_to_message_id=msg.reply_to_message.message_id if msg.reply_to_message else None,
            message_type=mtype,
            file_id=file_id,
            file_unique_id=file_unique_id,
            file_name=file_name,
            mime_type=mime_type,
            edited_at=msg.edit_date,
            raw=msg.model_dump(mode="json", exclude_none=True),
        )
    except Exception:
        # Никогда не падаем в группе — иначе Telegram будет ретраить апдейт.
        logger.exception("Failed to persist message chat=%s msg_id=%s", msg.chat.id, msg.message_id)
