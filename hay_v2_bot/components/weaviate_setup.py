"""Weaviate DocumentStore для v2: расширенная схема под чанки файлов."""

from __future__ import annotations

from haystack.utils import Secret
from haystack_integrations.document_stores.weaviate.auth import AuthApiKey
from haystack_integrations.document_stores.weaviate.document_store import (
    DOCUMENT_COLLECTION_PROPERTIES,
    WeaviateDocumentStore,
)

from vpg07.config import Settings

_EXTRA_V2_PROPS = [
    {"name": "user_id", "dataType": ["int"]},
    {"name": "role", "dataType": ["text"]},
    {"name": "chat_ts", "dataType": ["text"]},
    {"name": "source_kind", "dataType": ["text"]},
    {"name": "filename", "dataType": ["text"]},
    {"name": "chunk_index", "dataType": ["int"]},
    {"name": "page_no", "dataType": ["int"]},
]


def collection_settings_v2(class_name: str) -> dict:
    """Схема коллекции Haystack + поля для памяти и загруженных файлов."""
    name = class_name[0].upper() + class_name[1:] if class_name else "Default"
    return {
        "class": name,
        "invertedIndexConfig": {"indexNullState": True},
        "properties": list(DOCUMENT_COLLECTION_PROPERTIES) + _EXTRA_V2_PROPS,
    }


def build_document_store(settings: Settings) -> WeaviateDocumentStore:
    """Создаёт хранилище; для v2 задайте отдельное WEAVIATE_COLLECTION_NAME в .env."""
    class_name = settings.weaviate_collection_name.strip() or "Vpg07HayV2"
    return WeaviateDocumentStore(
        url=settings.weaviate_url,
        auth_client_secret=AuthApiKey(api_key=Secret.from_token(settings.weaviate_api_key)),
        collection_settings=collection_settings_v2(class_name),
    )
