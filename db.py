"""Слой работы с БД: asyncpg-пул, схема, две операции записи."""
from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any, Optional

import asyncpg

from bot.config import settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id     BIGINT PRIMARY KEY,
    username    TEXT,
    full_name   TEXT,
    is_bot      BOOLEAN DEFAULT FALSE,
    first_seen  TIMESTAMPTZ DEFAULT NOW(),
    last_seen   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
    id                   BIGSERIAL PRIMARY KEY,
    chat_id              BIGINT NOT NULL,
    message_id           BIGINT NOT NULL,
    user_id              BIGINT,
    ts                   TIMESTAMPTZ NOT NULL,
    text                 TEXT,
    reply_to_message_id  BIGINT,
    message_type         TEXT NOT NULL,
    file_id              TEXT,
    file_unique_id       TEXT,
    file_name            TEXT,
    mime_type            TEXT,
    edited_at            TIMESTAMPTZ,
    raw                  JSONB NOT NULL,
    received_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (chat_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_chat_ts  ON messages (chat_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_messages_user     ON messages (user_id);
CREATE INDEX IF NOT EXISTS idx_messages_type     ON messages (message_type);
"""


async def init_db() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=1,
        max_size=5,
        command_timeout=30,
    )
    async with _pool.acquire() as conn:
        await conn.execute(SCHEMA)
    logger.info("DB pool initialized, schema ensured")


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def upsert_user(
    user_id: int,
    username: Optional[str],
    full_name: str,
    is_bot: bool,
) -> None:
    assert _pool is not None
    await _pool.execute(
        """
        INSERT INTO users (user_id, username, full_name, is_bot, last_seen)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (user_id) DO UPDATE
           SET username  = EXCLUDED.username,
               full_name = EXCLUDED.full_name,
               is_bot    = EXCLUDED.is_bot,
               last_seen = NOW()
        """,
        user_id, username, full_name, is_bot,
    )


async def save_message(
    *,
    chat_id: int,
    message_id: int,
    user_id: Optional[int],
    ts: dt.datetime,
    text: Optional[str],
    reply_to_message_id: Optional[int],
    message_type: str,
    file_id: Optional[str],
    file_unique_id: Optional[str],
    file_name: Optional[str],
    mime_type: Optional[str],
    edited_at: Optional[dt.datetime],
    raw: dict[str, Any],
) -> None:
    """Идемпотентно: при повторе по (chat_id, message_id) обновляем text/edited_at/raw."""
    assert _pool is not None
    await _pool.execute(
        """
        INSERT INTO messages (
            chat_id, message_id, user_id, ts, text, reply_to_message_id,
            message_type, file_id, file_unique_id, file_name, mime_type,
            edited_at, raw
        )
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb)
        ON CONFLICT (chat_id, message_id) DO UPDATE
           SET text       = EXCLUDED.text,
               edited_at  = EXCLUDED.edited_at,
               raw        = EXCLUDED.raw
        """,
        chat_id, message_id, user_id, ts, text, reply_to_message_id,
        message_type, file_id, file_unique_id, file_name, mime_type,
        edited_at, json.dumps(raw, ensure_ascii=False, default=str),
    )
