"""Этап 4: краткое резюме после успешной индексации (по фрагментам текста чанков)."""

from __future__ import annotations

from haystack import Document

from vpg_telegram.v2.components.summarize import one_sentence_summary_ru
from vpg_telegram.v2.config import V2Options
from vpg07.config import Settings


def _excerpt_for_summary(documents: list[Document], max_chars: int) -> str:
    merged_preview: list[str] = []
    for d in documents:
        piece = (d.content or "").strip()
        if piece:
            merged_preview.append(piece)
    return "\n\n".join(merged_preview)[:max_chars]


def build_file_upload_summary(
    settings: Settings,
    options: V2Options,
    *,
    filename: str,
    annotated_chunks: list[Document],
) -> str:
    """Одно предложение на русском о содержимом файла (по отрывку из чанков)."""
    excerpt = _excerpt_for_summary(annotated_chunks, options.summary_input_max_chars)
    return one_sentence_summary_ru(
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base,
        chat_model=settings.openai_chat_model,
        filename=filename,
        content_excerpt=excerpt,
    )
