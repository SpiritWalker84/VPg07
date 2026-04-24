"""Агент v2: память пользователя + RAG по загруженным файлам, те же инструменты что в v1."""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from haystack import Document
from haystack.components.agents import Agent
from haystack.components.embedders import OpenAIDocumentEmbedder, OpenAITextEmbedder
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses import ChatMessage
from haystack.document_stores.types import DuplicatePolicy
from haystack.utils import Secret
from haystack_integrations.components.retrievers.weaviate import WeaviateEmbeddingRetriever

from hay_v2_bot.config import V2Options
from hay_v2_bot.components.file_ingestion import FileIngestionService, SOURCE_FILE_CHUNK
from hay_v2_bot.components.weaviate_setup import build_document_store
from hay_v2_bot.pipelines.index_pipeline import build_index_pipeline
from hay_v2_bot.pipelines.parse_pipeline import build_parse_pipeline
from vpg07.config import Settings
from vpg07.haystack_assistant import (
    AssistantReply,
    _extract_dog_photo_urls_for_current_turn,
    _format_memory_block,
    _strip_sent_photo_markdown,
    _strip_system,
)
from vpg07.tools_external import (
    TOOL_NAME_DESCRIBE_RANDOM_DOG_VISION,
    TOOL_NAME_FETCH_CAT_FACT,
    build_external_tools,
)

logger = logging.getLogger(__name__)


def _format_file_hits(documents: list[Document]) -> str:
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


@dataclass(frozen=True)
class IngestResult:
    """Результат загрузки файла в Weaviate."""

    chunks: int
    summary: str


class HaystackV2Assistant:
    """Персональный агент: долговременная память (как в v1) + контекст из Docling-чанков."""

    def __init__(self, settings: Settings, options: V2Options) -> None:
        self._settings = settings
        self._options = options
        self._histories: dict[int, list[ChatMessage]] = defaultdict(list)

        self._document_store = build_document_store(settings)

        api_key_secret = Secret.from_token(settings.openai_api_key)
        base = settings.openai_api_base or None

        self._text_embedder = OpenAITextEmbedder(
            api_key=api_key_secret,
            model=settings.openai_embedding_model,
            api_base_url=base,
            dimensions=settings.embedding_dimension,
        )
        self._doc_embedder = OpenAIDocumentEmbedder(
            api_key=api_key_secret,
            model=settings.openai_embedding_model,
            api_base_url=base,
            dimensions=settings.embedding_dimension,
        )

        self._retriever = WeaviateEmbeddingRetriever(
            document_store=self._document_store,
            top_k=max(settings.memory_top_k, options.document_top_k),
            filters={},
        )

        parse_pipe = build_parse_pipeline(
            chunk_words=options.chunk_words,
            chunk_overlap=options.chunk_overlap,
        )
        index_pipe = build_index_pipeline(settings=settings, document_store=self._document_store)
        self._ingestion = FileIngestionService(
            settings=settings,
            options=options,
            parse_pipeline=parse_pipe,
            index_pipeline=index_pipe,
        )

        tools = build_external_tools(
            openai_api_key=settings.openai_api_key,
            openai_base_url=settings.openai_api_base,
            vision_model=settings.openai_vision_model,
        )

        self._agent = Agent(
            chat_generator=OpenAIChatGenerator(
                api_key=api_key_secret,
                model=settings.openai_chat_model,
                api_base_url=base,
                generation_kwargs={"temperature": 0.7},
            ),
            tools=tools,
            system_prompt=None,
            max_agent_steps=settings.max_agent_steps,
            exit_conditions=["text"],
        )

    def warm_up(self) -> None:
        self._document_store.client
        self._ingestion.warm_up()
        self._agent.warm_up()

    def close(self) -> None:
        self._document_store.close()

    def ingest_file(self, *, user_id: int, path: str, filename: str) -> IngestResult:
        n, summary = self._ingestion.ingest_path(path=path, user_id=user_id, filename=filename)
        return IngestResult(chunks=n, summary=summary)

    def _memory_filter(self, user_id: int) -> dict:
        return {
            "operator": "AND",
            "conditions": [
                {"field": "user_id", "operator": "==", "value": int(user_id)},
                {"field": "role", "operator": "==", "value": "user"},
            ],
        }

    def _file_filter(self, user_id: int) -> dict:
        return {
            "operator": "AND",
            "conditions": [
                {"field": "user_id", "operator": "==", "value": int(user_id)},
                {"field": "source_kind", "operator": "==", "value": SOURCE_FILE_CHUNK},
            ],
        }

    def _retrieve_memory(self, *, user_id: int, query_text: str) -> list[Document]:
        emb = self._text_embedder.run(text=query_text)["embedding"]
        out = self._retriever.run(
            query_embedding=emb,
            filters=self._memory_filter(user_id),
            top_k=self._settings.memory_top_k,
        )
        return list(out.get("documents") or [])

    def _retrieve_files(self, *, user_id: int, query_text: str) -> list[Document]:
        emb = self._text_embedder.run(text=query_text)["embedding"]
        out = self._retriever.run(
            query_embedding=emb,
            filters=self._file_filter(user_id),
            top_k=self._options.document_top_k,
        )
        return list(out.get("documents") or [])

    def _persist_user_message(self, *, user_id: int, user_text: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        docs = [
            Document(
                id=str(uuid.uuid4()),
                content=user_text.strip(),
                meta={"user_id": int(user_id), "role": "user", "chat_ts": ts},
            ),
        ]
        with_embeddings = self._doc_embedder.run(documents=docs)["documents"]
        n = self._document_store.write_documents(with_embeddings, policy=DuplicatePolicy.NONE)
        logger.info("Weaviate memory write (user only): %s documents", n)

    def _trim_history(self, user_id: int) -> None:
        max_m = self._settings.chat_history_max_messages
        hist = self._histories[user_id]
        if len(hist) > max_m:
            self._histories[user_id] = hist[-max_m:]

    def _build_system_prompt(
        self,
        *,
        memory_block: str,
        file_block: str,
        display_name: str,
    ) -> str:
        who = display_name or "пользователь"
        return (
            f"Ты умный персональный помощник в Telegram. Обращайся естественно, помни контекст разговора.\n"
            f"Собеседник: {who}.\n"
            "Ниже — релевантные фрагменты долговременной памяти (только прошлые сообщения пользователя) "
            "и отдельно — фрагменты из PDF/DOCX, которые пользователь загрузил в этот чат. "
            "Используй их, если уместно; не выдумывай факты, которых нет в этих фрагментах и переписке.\n"
            "Инструменты вызывай умеренно: только если пользователю уместны факты о кошках, собаке/породе "
            "или лёгкий развлекательный запрос. Не вызывай инструменты на каждое сообщение.\n"
            f"Список инструментов (имена в API):\n"
            f"- {TOOL_NAME_FETCH_CAT_FACT} — короткий факт о кошках (внешний API catfact.ninja), "
            "когда явно о кошках или в тему «факт дня».\n"
            f"- {TOOL_NAME_DESCRIBE_RANDOM_DOG_VISION} — **основной мультимодальный сценарий**: "
            "случайное фото с dog.ceo + краткое описание породы через vision; само фото пользователь "
            "получит отдельным сообщением в Telegram, не вставляй в ответ markdown-картинок ![...](url) "
            "и не дублируй URL — только обычный текст с выводом по породе.\n\n"
            f"Память (сообщения пользователя):\n{memory_block}\n\n"
            f"Загруженные документы:\n{file_block}"
        )

    def reply(self, *, user_id: int, user_text: str, display_name: str) -> AssistantReply:
        memory_docs = self._retrieve_memory(user_id=user_id, query_text=user_text)
        file_docs = self._retrieve_files(user_id=user_id, query_text=user_text)
        memory_block = _format_memory_block(memory_docs)
        file_block = _format_file_hits(file_docs)
        system_prompt = self._build_system_prompt(
            memory_block=memory_block,
            file_block=file_block,
            display_name=display_name,
        )

        prior = self._histories[user_id]
        messages_in = prior + [ChatMessage.from_user(user_text)]

        result = self._agent.run(messages=messages_in, system_prompt=system_prompt)
        out_messages = list(result.get("messages") or [])
        self._histories[user_id] = _strip_system(out_messages)
        self._trim_history(user_id)

        last = result.get("last_message")
        assistant_text = (last.text if last else "").strip()
        photo_urls = _extract_dog_photo_urls_for_current_turn(out_messages, user_text)
        if photo_urls:
            assistant_text = _strip_sent_photo_markdown(assistant_text, photo_urls).strip()
        if not assistant_text and not photo_urls:
            assistant_text = "Не удалось сформулировать ответ."

        self._persist_user_message(user_id=user_id, user_text=user_text)
        return AssistantReply(text=assistant_text, photo_urls=photo_urls)
