"""Форматирование блоков контекста для системного промпта (фрагменты из файлов)."""

from __future__ import annotations

from haystack import Document


def format_file_hits_for_prompt(documents: list[Document]) -> str:
    if not documents:
        return "Фрагментов из загруженных файлов по этому запросу не найдено."
    lines: list[str] = []
    for doc in documents:
        score = doc.score
        score_s = f"{score:.3f}" if isinstance(score, float) else "n/a"
        meta = doc.meta or {}
        fn = (meta.get("filename") or "").strip()
        idx = meta.get("chunk_index")
        label_parts: list[str] = []
        if fn:
            label_parts.append(fn)
        if idx is not None:
            label_parts.append(f"чанк {idx}")
        prefix = ("[" + " · ".join(label_parts) + "] ") if label_parts else ""
        text = (doc.content or "").strip()
        if text:
            lines.append(f"- ({score_s}) {prefix}{text}")
    return "\n".join(lines) if lines else "Файлы проиндексированы, но текст фрагментов пуст."
