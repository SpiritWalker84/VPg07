"""Параметры группового бота: поверх vpg07.Settings (OpenAI, Weaviate, ProxyAPI)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from vpg07.config import load_settings, Settings


@dataclass(frozen=True)
class GroupOptions:
    """Семантический поиск и лимиты для группового чата."""

    rag_top_k: int
    session_transcript_max_chars: int
    mention_answer_max_tokens: int
    session_summary_max_tokens: int


def load_group_options(env_file: str | None = ".env") -> tuple[Settings, GroupOptions]:
    """Загружает Settings и опции группового бота."""
    settings = load_settings(env_file)
    opts = GroupOptions(
        rag_top_k=int(os.environ.get("GROUP_RAG_TOP_K", "16")),
        session_transcript_max_chars=int(os.environ.get("GROUP_SESSION_MAX_CHARS", "200000")),
        mention_answer_max_tokens=int(os.environ.get("GROUP_MENTION_MAX_TOKENS", "2000")),
        session_summary_max_tokens=int(os.environ.get("GROUP_SESSION_SUMMARY_MAX_TOKENS", "2500")),
    )
    return settings, opts


def group_weaviate_collection_name() -> str:
    """Имя коллекции Weaviate только для group bot (отдельно от v1/v2)."""
    return (os.environ.get("WEAVIATE_GROUP_COLLECTION_NAME", "Vpg07GroupChat").strip() or "Vpg07GroupChat")
