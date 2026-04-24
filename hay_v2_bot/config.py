"""Параметры v2: базовые настройки из vpg07 + опции чанков и топ-k для документов."""

from __future__ import annotations

import os
from dataclasses import dataclass

from vpg07.config import load_settings


@dataclass(frozen=True)
class V2Options:
    """Дополнительные опции второй версии бота (файлы, RAG по чанкам)."""

    document_top_k: int
    chunk_words: int
    chunk_overlap: int
    summary_input_max_chars: int


def load_v2_options(env_file: str | None = ".env") -> tuple[Settings, V2Options]:
    """Загружает Settings и опции v2 из окружения."""
    settings = load_settings(env_file)
    opts = V2Options(
        document_top_k=int(os.environ.get("FILE_RAG_TOP_K", "8")),
        chunk_words=int(os.environ.get("DOC_CHUNK_WORDS", "200")),
        chunk_overlap=int(os.environ.get("DOC_CHUNK_OVERLAP", "40")),
        summary_input_max_chars=int(os.environ.get("DOC_SUMMARY_MAX_CHARS", "12000")),
    )
    return settings, opts
