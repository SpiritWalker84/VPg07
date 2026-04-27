"""Этап 3: эмбеддинги и запись чанков в Weaviate (векторное хранилище проекта)."""

from __future__ import annotations

import logging

from haystack import Document, Pipeline

logger = logging.getLogger(__name__)


def index_documents_in_weaviate(
    index_pipeline: Pipeline,
    *,
    documents: list[Document],
    filename: str,
    user_id: int,
) -> int | None:
    """
    Пайплайн embedder → writer. Возвращает documents_written из writer, если есть.
    """
    index_out = index_pipeline.run({"embedder": {"documents": documents}})
    written = index_out.get("writer", {}).get("documents_written")
    logger.info(
        "Weaviate index: file=%s user=%s chunks=%s written=%s",
        filename,
        user_id,
        len(documents),
        written,
    )
    return written
