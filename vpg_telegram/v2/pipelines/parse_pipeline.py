"""Пайплайн разбора файла: Docling (Markdown) → разбиение на чанки по словам."""

from __future__ import annotations

from haystack import Pipeline
from haystack.components.preprocessors import DocumentSplitter
from docling_haystack.converter import DoclingConverter, ExportType


def build_parse_pipeline(*, chunk_words: int, chunk_overlap: int) -> Pipeline:
    """
    Конвейер без эмбеддингов: один документ на файл в Markdown, затем сплиттер Haystack.
    ExportType.MARKDOWN не использует HybridChunker и не тянет sentence-transformers.
    """
    pipe = Pipeline()
    pipe.add_component(
        "converter",
        DoclingConverter(export_type=ExportType.MARKDOWN),
    )
    pipe.add_component(
        "splitter",
        DocumentSplitter(
            split_by="word",
            split_length=chunk_words,
            split_overlap=chunk_overlap,
        ),
    )
    pipe.connect("converter.documents", "splitter.documents")
    return pipe
