"""Обращение к Weaviate: семантический поиск (память + чанки файлов) и запись сообщений пользователя."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from haystack import Document
from haystack.components.embedders import OpenAIDocumentEmbedder, OpenAITextEmbedder
from haystack.document_stores.types import DuplicatePolicy
from haystack.utils import Secret
from haystack_integrations.components.retrievers.weaviate import WeaviateEmbeddingRetriever
from haystack_integrations.document_stores.weaviate.document_store import WeaviateDocumentStore

from vpg_telegram.v2.config import V2Options
from vpg_telegram.v2.document_stages.chunk_metadata import SOURCE_FILE_CHUNK
from vpg07.config import Settings

logger = logging.getLogger(__name__)


class WeaviateContextService:
    """
    Изолированный слой работы с векторным хранилищем (Weaviate):
    эмбеддинги запроса, фильтры по user_id, запись только user-сообщений в память.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        options: V2Options,
        document_store: WeaviateDocumentStore,
    ) -> None:
        self._settings = settings
        self._options = options
        self._document_store = document_store

        api_key_secret = Secret.from_token(settings.openai_api_key)
        base = settings.openai_api_base or None

        self._text_embedder = OpenAITextEmbedder(
            api_key=api_key_secret,
            model=settings.openai_embedding_model,
            api_base_url=base,
            dimensions=settings.embedding_dimension,
        )
        self._doc_embedder = OpenAIDocumentEmbedder(
            api_key=api_key_secret,
            model=settings.openai_embedding_model,
            api_base_url=base,
            dimensions=settings.embedding_dimension,
        )

        self._retriever = WeaviateEmbeddingRetriever(
            document_store=document_store,
            top_k=max(settings.memory_top_k, options.document_top_k),
            filters={},
        )

    @staticmethod
    def memory_filter(user_id: int) -> dict:
        return {
            "operator": "AND",
            "conditions": [
                {"field": "user_id", "operator": "==", "value": int(user_id)},
                {"field": "role", "operator": "==", "value": "user"},
            ],
        }

    @staticmethod
    def file_chunks_filter(user_id: int) -> dict:
        return {
            "operator": "AND",
            "conditions": [
                {"field": "user_id", "operator": "==", "value": int(user_id)},
                {"field": "source_kind", "operator": "==", "value": SOURCE_FILE_CHUNK},
            ],
        }

    def retrieve_memory(self, *, user_id: int, query_text: str) -> list[Document]:
        emb = self._text_embedder.run(text=query_text)["embedding"]
        out = self._retriever.run(
            query_embedding=emb,
            filters=self.memory_filter(user_id),
            top_k=self._settings.memory_top_k,
        )
        return list(out.get("documents") or [])

    def retrieve_file_chunks(self, *, user_id: int, query_text: str) -> list[Document]:
        emb = self._text_embedder.run(text=query_text)["embedding"]
        out = self._retriever.run(
            query_embedding=emb,
            filters=self.file_chunks_filter(user_id),
            top_k=self._options.document_top_k,
        )
        return list(out.get("documents") or [])

    def persist_user_message(self, *, user_id: int, user_text: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        docs = [
            Document(
                id=str(uuid.uuid4()),
                content=user_text.strip(),
                meta={"user_id": int(user_id), "role": "user", "chat_ts": ts},
            ),
        ]
        with_embeddings = self._doc_embedder.run(documents=docs)["documents"]
        n = self._document_store.write_documents(with_embeddings, policy=DuplicatePolicy.NONE)
        logger.info("Weaviate memory write (user only): %s documents", n)
