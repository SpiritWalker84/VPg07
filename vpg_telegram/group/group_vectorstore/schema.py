"""
Схема коллекции Weaviate для сообщений группы и сводок сессий.

Идентификаторы Telegram (chat_id, user_id) храним как text — в группах chat_id отрицательный и >32-bit.
"""

from __future__ import annotations

from haystack_integrations.document_stores.weaviate.document_store import DOCUMENT_COLLECTION_PROPERTIES

# Поля в meta у Haystack → свойства Weaviate (имена в нижнем регистре, как в интеграции).
_GROUP_EXTRA = [
    {"name": "tg_chat_id", "dataType": ["text"]},
    {"name": "tg_user_id", "dataType": ["text"]},
    {"name": "tg_message_id", "dataType": ["int"]},
    {"name": "author_display", "dataType": ["text"]},
    {"name": "session_id", "dataType": ["text"]},
    {"name": "source_kind", "dataType": ["text"]},
    {"name": "chat_ts", "dataType": ["text"]},
]

SOURCE_GROUP_MESSAGE = "group_message"
SOURCE_SESSION_SUMMARY = "session_summary"


def build_group_collection_settings(class_name: str) -> dict:
    """Схема: базовая коллекция Haystack + поля для Telegram и сессий."""
    name = class_name[0].upper() + class_name[1:] if class_name else "Default"
    return {
        "class": name,
        "invertedIndexConfig": {"indexNullState": True},
        "properties": list(DOCUMENT_COLLECTION_PROPERTIES) + _GROUP_EXTRA,
    }
