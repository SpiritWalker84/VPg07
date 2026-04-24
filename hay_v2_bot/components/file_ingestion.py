"""Оркестрация: пайплайн разбора (Docling) + пайплайн индексации (эмбеддинги, Weaviate)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from datetime import datetime, timezone

from haystack import Document, Pipeline
from haystack.document_stores.types import DuplicatePolicy

from hay_v2_bot.config import V2Options
from hay_v2_bot.components.summarize import one_sentence_summary_ru
from vpg07.config import Settings

logger = logging.getLogger(__name__)

SOURCE_FILE_CHUNK = "file_chunk"


class FileIngestionService:
    """Связывает parse_pipeline и index_pipeline, добавляет метаданные чанков."""

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
        Прогоняет файл через Docling и сплиттер, пишет чанки в Weaviate.
        Возвращает (число_чанков, одно_предложение_резюме).
        """
        parsed = self._parse_pipeline.run({"converter": {"paths": [path]}})
        docs = list(parsed.get("splitter", {}).get("documents") or [])
        if not docs:
            raise RuntimeError("Docling не вернул фрагментов текста (пустой документ?).")

        ts = datetime.now(timezone.utc).isoformat()
        merged_preview: list[str] = []
        annotated: list[Document] = []
        for i, doc in enumerate(docs):
            new_meta = {
                **(doc.meta or {}),
                "user_id": int(user_id),
                "role": "document",
                "chat_ts": ts,
                "source_kind": SOURCE_FILE_CHUNK,
                "filename": filename,
                "chunk_index": int(i),
                "page_no": int((doc.meta or {}).get("page_no") or 0),
            }
            d = replace(doc, id=str(uuid.uuid4()), meta=new_meta)
            annotated.append(d)
            piece = (d.content or "").strip()
            if piece:
                merged_preview.append(piece)

        excerpt = "\n\n".join(merged_preview)[: self._options.summary_input_max_chars]

        index_out = self._index_pipeline.run({"embedder": {"documents": annotated}})
        written = index_out.get("writer", {}).get("documents_written")
        logger.info("Indexed file %s for user %s: chunks=%s, written=%s", filename, user_id, len(annotated), written)

        summary = one_sentence_summary_ru(
            api_key=self._settings.openai_api_key,
            base_url=self._settings.openai_api_base,
            chat_model=self._settings.openai_chat_model,
            filename=filename,
            content_excerpt=excerpt,
        )

        return len(annotated), summary
