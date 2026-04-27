"""Стадии обработки загруженного файла: Docling → чанки → Weaviate → краткое резюме."""

from vpg_telegram.v2.document_stages.chunk_metadata import SOURCE_FILE_CHUNK, annotate_file_chunks
from vpg_telegram.v2.document_stages.docling_parse import parse_file_to_chunk_documents
from vpg_telegram.v2.document_stages.upload_summary import build_file_upload_summary
from vpg_telegram.v2.document_stages.weaviate_index import index_documents_in_weaviate

__all__ = [
    "SOURCE_FILE_CHUNK",
    "annotate_file_chunks",
    "build_file_upload_summary",
    "index_documents_in_weaviate",
    "parse_file_to_chunk_documents",
]
