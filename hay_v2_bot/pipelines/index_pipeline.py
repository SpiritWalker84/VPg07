"""Пайплайн записи в Weaviate: OpenAI Document Embedder → DocumentWriter."""

from __future__ import annotations

from haystack import Pipeline
from haystack.components.embedders import OpenAIDocumentEmbedder
from haystack.components.writers import DocumentWriter
from haystack.utils import Secret

from haystack_integrations.document_stores.weaviate.document_store import WeaviateDocumentStore

from vpg07.config import Settings


def build_index_pipeline(
    *,
    settings: Settings,
    document_store: WeaviateDocumentStore,
) -> Pipeline:
    """Эмбеддинги через OpenAI-совместимый API (ProxyAPI), запись в переданный store."""
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
