"""Этап 2: обогащение чанков метаданными пользователя и файла."""

from __future__ import annotations

import uuid
from dataclasses import replace

from haystack import Document

SOURCE_FILE_CHUNK = "file_chunk"


def annotate_file_chunks(
    docs: list[Document],
    *,
    user_id: int,
    filename: str,
    chat_ts: str,
) -> list[Document]:
    """Добавляет user_id, filename, chunk_index, source_kind и т.д. к каждому чанку."""
    annotated: list[Document] = []
    for i, doc in enumerate(docs):
        new_meta = {
            **(doc.meta or {}),
            "user_id": int(user_id),
            "role": "document",
            "chat_ts": chat_ts,
            "source_kind": SOURCE_FILE_CHUNK,
            "filename": filename,
            "chunk_index": int(i),
            "page_no": int((doc.meta or {}).get("page_no") or 0),
        }
        d = replace(doc, id=str(uuid.uuid4()), meta=new_meta)
        annotated.append(d)
    return annotated
