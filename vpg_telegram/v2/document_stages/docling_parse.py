"""Этап 1: разбор файла — Docling (Markdown) и чанкование по словам (Haystack Pipeline)."""

from __future__ import annotations

from haystack import Document, Pipeline


def parse_file_to_chunk_documents(parse_pipeline: Pipeline, *, path: str) -> list[Document]:
    """
    Запускает конвейер converter → splitter, возвращает чанки без пользовательских метаданных.
    """
    parsed = parse_pipeline.run({"converter": {"paths": [path]}})
    docs = list(parsed.get("splitter", {}).get("documents") or [])
    if not docs:
        raise RuntimeError("Docling не вернул фрагментов текста (пустой документ?).")
    return docs
