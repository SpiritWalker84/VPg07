"""RAG по одному `tg_chat_id`: ретривер Weaviate + эмбеддер запроса (OpenAI, base URL)."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from haystack import Document
from haystack.components.embedders import OpenAITextEmbedder
from haystack.utils import Secret
from haystack_integrations.components.retrievers.weaviate import WeaviateEmbeddingRetriever

if TYPE_CHECKING:
    from haystack_integrations.document_stores.weaviate.document_store import WeaviateDocumentStore

from vpg_telegram.group.config import GroupOptions
from vpg07.config import Settings

logger = logging.getLogger(__name__)


def _filter_chat(tg_chat_id: int) -> dict:
    return {
        "operator": "AND",
        "conditions": [
            {"field": "tg_chat_id", "operator": "==", "value": str(tg_chat_id)},
        ],
    }


def _parse_meta_ts(raw: str | None) -> datetime | None:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _rerank_by_semantic_and_recency(
    documents: list[Document],
    *,
    limit: int,
    hours_half_life: float = 2.5,
) -> list[Document]:
    """
    Сырые top-N из Weaviate по смыслу часто тянут старые, но «похожие» вектором реплики
    (например, прошлые темы). Подмешиваем свежесть `chat_ts`, чтобы «что думаешь?»
    относилось к только что сказанному в ветке.
    """
    if not documents:
        return []
    now = datetime.now(timezone.utc)
    scored: list[tuple[float, Document]] = []
    for d in documents:
        sem = float(d.score) if isinstance(d.score, (int, float)) else 0.0
        ts = _parse_meta_ts((d.meta or {}).get("chat_ts"))
        if ts is not None:
            age_h = max(0.0, (now - ts).total_seconds() / 3600.0)
        else:
            age_h = 24.0 * 30.0
        # Чем свежее, тем time_factor ближе к 1.0; полураспад ~ hours_half_life часа
        time_factor = math.exp(-age_h / max(0.5, float(hours_half_life)))
        # Вес: свежесть сопоставима с смыслом, чтобы недавние «апельсины» били сильные старые «курсы».
        combined = 0.42 * max(0.0, min(1.0, sem)) + 0.58 * (0.12 + 0.88 * time_factor)
        scored.append((combined, d))
    scored.sort(key=lambda x: -x[0])
    # Уникальность по (chat_ts + первые 80 символов), отсечь дубликаты индекса
    seen: set[str] = set()
    out: list[Document] = []
    for _, d in scored:
        key = f"{(d.meta or {}).get('chat_ts')!s}|{(d.content or '')[:80]!s}"
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
        if len(out) >= limit:
            break
    return out


def format_hits_for_prompt(docs: list[Document]) -> str:
    """Текст для LLM: цитаты с автором и временем."""
    if not docs:
        return (
            "(Пока нет релевантных фрагментов в индексе по этому запросу — возможно, сообщений в чате ещё мало "
            "или они не проиндексировались.)"
        )
    lines: list[str] = [
        "Ниже — фрагменты переписки (по смыслу запроса и **свежести** сообщений):",
    ]
    for d in docs:
        meta = d.meta or {}
        score = d.score
        sc = f"{score:.3f}" if isinstance(score, float) else "n/a"
        who = (meta.get("author_display") or "").strip() or "—"
        ts = (meta.get("chat_ts") or "").strip() or "?"
        kind = (meta.get("source_kind") or "").strip()
        prefix = f"[{kind}] {ts} — {who}"
        text = (d.content or "").strip()
        if text:
            lines.append(f"- ({sc}) {prefix}:\n{text[:4000]}")
    return "\n\n".join(lines) if lines else "(пусто)"


class GroupChatRagService:
    """Семантический поиск внутри одного чата (группы)."""

    def __init__(
        self,
        *,
        settings: Settings,
        options: GroupOptions,
        document_store: "WeaviateDocumentStore",
    ) -> None:
        self._settings = settings
        self._options = options
        self._retriever = WeaviateEmbeddingRetriever(
            document_store=document_store,
            top_k=options.rag_top_k * 2,
            filters={},
        )
        api = Secret.from_token(settings.openai_api_key)
        base = settings.openai_api_base or None
        self._text_embedder = OpenAITextEmbedder(
            api_key=api,
            model=settings.openai_embedding_model,
            api_base_url=base,
            dimensions=settings.embedding_dimension,
        )

    def retrieve(
        self,
        *,
        tg_chat_id: int,
        query_text: str,
    ) -> list[Document]:
        """Берём увеличенный пул кандидатов, затем переранжируем: смысл + недавние `chat_ts`."""
        pool = min(48, max(self._options.rag_top_k * 4, 16))
        emb = self._text_embedder.run(text=query_text)["embedding"]
        out = self._retriever.run(
            query_embedding=emb,
            filters=_filter_chat(tg_chat_id),
            top_k=pool,
        )
        raw = list(out.get("documents") or [])
        return _rerank_by_semantic_and_recency(
            raw,
            limit=self._options.rag_top_k,
        )
