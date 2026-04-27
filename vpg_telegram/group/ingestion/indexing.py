"""Оркестрация: эмбеддинг и запись документов группы в Weaviate через Haystack Pipeline."""

from __future__ import annotations

import logging

from haystack import Document, Pipeline

logger = logging.getLogger(__name__)


class GroupMessageIndexingService:
    """Оборачивает Haystack-пайплайн embedder → writer."""

    def __init__(self, *, index_pipeline: Pipeline) -> None:
        self._pipeline = index_pipeline

    def warm_up(self) -> None:
        self._pipeline.warm_up()

    def index_documents(self, documents: list[Document]) -> int | None:
        """Возвращает `documents_written` из writer, если есть."""
        if not documents:
            return 0
        out = self._pipeline.run({"embedder": {"documents": documents}})
        n = out.get("writer", {}).get("documents_written")
        logger.debug("group index: wrote %s documents (reported=%s)", len(documents), n)
        return n
