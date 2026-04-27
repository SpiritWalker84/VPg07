"""Генерация текста через OpenAI-совместимый API (везде `base_url` = ProxyAPI)."""

from vpg_telegram.group.llm.responses import answer_with_citations, summarize_listening_session

__all__ = [
    "answer_with_citations",
    "summarize_listening_session",
]
