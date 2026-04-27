"""Сообщения Telegram → `Document` и запись через пайплайн."""

from vpg_telegram.group.ingestion.documents import build_group_message_document, build_session_summary_document
from vpg_telegram.group.ingestion.indexing import GroupMessageIndexingService

__all__ = [
    "GroupMessageIndexingService",
    "build_group_message_document",
    "build_session_summary_document",
]
