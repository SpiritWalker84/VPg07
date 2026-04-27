"""Фабрика `WeaviateDocumentStore` для `vpg_telegram.group` (отдельная коллекция)."""

from __future__ import annotations

from haystack.utils import Secret
from haystack_integrations.document_stores.weaviate.auth import AuthApiKey
from haystack_integrations.document_stores.weaviate.document_store import WeaviateDocumentStore

from vpg_telegram.group.config import group_weaviate_collection_name
from vpg_telegram.group.group_vectorstore.schema import build_group_collection_settings
from vpg07.config import Settings


def build_group_document_store(settings: Settings) -> WeaviateDocumentStore:
    class_name = group_weaviate_collection_name()
    return WeaviateDocumentStore(
        url=settings.weaviate_url,
        auth_client_secret=AuthApiKey(api_key=Secret.from_token(settings.weaviate_api_key)),
        collection_settings=build_group_collection_settings(class_name),
    )
