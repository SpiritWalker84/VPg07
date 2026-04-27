"""Weaviate: схема коллекции и фабрика document store (имя пакета не `weaviate`, чтобы не затенять клиент)."""

from vpg_telegram.group.group_vectorstore.schema import build_group_collection_settings
from vpg_telegram.group.group_vectorstore.store import build_group_document_store

__all__ = [
    "build_group_collection_settings",
    "build_group_document_store",
]
