"""Индексация `Document` в групповую коллекцию Weaviate (OpenAI-совместимый API + base URL)."""

from __future__ import annotations

from haystack import Pipeline
from haystack.components.embedders import OpenAIDocumentEmbedder
from haystack.components.writers import DocumentWriter
from haystack.utils import Secret

from haystack_integrations.document_stores.weaviate.document_store import WeaviateDocumentStore

from vpg07.config import Settings


def build_group_index_pipeline(
    *,
    settings: Settings,
    document_store: WeaviateDocumentStore,
) -> Pipeline:
    api_key_secret = Secret.from_token(settings.openai_api_key)
    base = settings.openai_api_base or None
    embedder = OpenAIDocumentEmbedder(
        api_key=api_key_secret,
        model=settings.openai_embedding_model,
        api_base_url=base,
        dimensions=settings.embedding_dimension,
    )
    pipe = Pipeline()
    pipe.add_component("embedder", embedder)
    pipe.add_component("writer", DocumentWriter(document_store=document_store))
    pipe.connect("embedder.documents", "writer.documents")
    return pipe
