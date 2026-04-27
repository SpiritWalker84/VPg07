"""Сборка `haystack.Document` из сообщений группы и сводок сессий."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from haystack import Document

from vpg_telegram.group.group_vectorstore.schema import SOURCE_GROUP_MESSAGE, SOURCE_SESSION_SUMMARY


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_group_message_document(
    *,
    text: str,
    tg_chat_id: int,
    tg_user_id: int,
    tg_message_id: int,
    author_display: str,
    session_id: str,
    chat_ts: str | None = None,
) -> Document:
    """Одно текстовое сообщение в группе (при сессии `session_id` непустой)."""
    ts = chat_ts or _iso_now()
    return Document(
        id=str(uuid.uuid4()),
        content=text.strip(),
        meta={
            "tg_chat_id": str(tg_chat_id),
            "tg_user_id": str(tg_user_id),
            "tg_message_id": int(tg_message_id),
            "author_display": (author_display or "").strip() or "—",
            "session_id": session_id or "",
            "source_kind": SOURCE_GROUP_MESSAGE,
            "chat_ts": ts,
        },
    )


def build_session_summary_document(
    *,
    summary_text: str,
    tg_chat_id: int,
    session_id: str,
    chat_ts: str | None = None,
) -> Document:
    """Итог сессии «слушаю» после команды стоп (для поиска по смыслу)."""
    ts = chat_ts or _iso_now()
    return Document(
        id=str(uuid.uuid4()),
        content=summary_text.strip(),
        meta={
            "tg_chat_id": str(tg_chat_id),
            "tg_user_id": "0",
            "tg_message_id": 0,
            "author_display": "Сводка сессии",
            "session_id": session_id,
            "source_kind": SOURCE_SESSION_SUMMARY,
            "chat_ts": ts,
        },
    )
