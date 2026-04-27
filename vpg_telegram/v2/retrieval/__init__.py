"""RAG-контекст и форматирование: Weaviate, промпт-блоки по чанкам файлов."""

from vpg_telegram.v2.retrieval.prompt_blocks import format_file_hits_for_prompt
from vpg_telegram.v2.retrieval.weaviate_context import WeaviateContextService

__all__ = [
    "WeaviateContextService",
    "format_file_hits_for_prompt",
]
