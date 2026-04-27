"""Оркестрация загрузки файла: стадии parse → метаданные → Weaviate → резюме."""

from __future__ import annotations

from datetime import datetime, timezone

from haystack import Pipeline

from vpg_telegram.v2.config import V2Options
from vpg_telegram.v2.document_stages import (
    annotate_file_chunks,
    build_file_upload_summary,
    index_documents_in_weaviate,
    parse_file_to_chunk_documents,
)
from vpg07.config import Settings


class FileIngestionService:
    """Склеивает стадии обработки документа (без логики ответа агента)."""

    def __init__(
        self,
        *,
        settings: Settings,
        options: V2Options,
        parse_pipeline: Pipeline,
        index_pipeline: Pipeline,
    ) -> None:
        self._settings = settings
        self._options = options
        self._parse_pipeline = parse_pipeline
        self._index_pipeline = index_pipeline

    def warm_up(self) -> None:
        self._parse_pipeline.warm_up()
        self._index_pipeline.warm_up()

    def ingest_path(
        self,
        *,
        path: str,
        user_id: int,
        filename: str,
    ) -> tuple[int, str]:
        """
        Парсинг (Docling) → чанки → Weaviate → краткое резюме.
        Возвращает (число_чанков, одно_предложение_резюме).
        """
        raw_docs = parse_file_to_chunk_documents(self._parse_pipeline, path=path)
        ts = datetime.now(timezone.utc).isoformat()
        annotated = annotate_file_chunks(
            raw_docs,
            user_id=user_id,
            filename=filename,
            chat_ts=ts,
        )
        index_documents_in_weaviate(
            self._index_pipeline,
            documents=annotated,
            filename=filename,
            user_id=user_id,
        )
        summary = build_file_upload_summary(
            self._settings,
            self._options,
            filename=filename,
            annotated_chunks=annotated,
        )
        return len(annotated), summary
