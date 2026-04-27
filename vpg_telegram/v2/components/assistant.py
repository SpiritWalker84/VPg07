"""Агент v2: ответы (генерация) и склейка RAG-контекста (Weaviate) с диалогом."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from haystack.components.agents import Agent
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses import ChatMessage
from haystack.utils import Secret

from vpg_telegram.v2.config import V2Options
from vpg_telegram.v2.components.file_ingestion import FileIngestionService
from vpg_telegram.v2.components.weaviate_setup import build_document_store
from vpg_telegram.v2.pipelines.index_pipeline import build_index_pipeline
from vpg_telegram.v2.pipelines.parse_pipeline import build_parse_pipeline
from vpg_telegram.v2.retrieval import WeaviateContextService, format_file_hits_for_prompt
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


@dataclass(frozen=True)
class IngestResult:
    """Результат загрузки файла: число чанков и краткое резюме."""

    chunks: int
    summary: str


class HaystackV2Assistant:
    """Персональный агент: долговременная память + RAG по чанкам загруженных файлов."""

    def __init__(self, settings: Settings, options: V2Options) -> None:
        self._settings = settings
        self._options = options
        self._histories: dict[int, list[ChatMessage]] = defaultdict(list)

        self._document_store = build_document_store(settings)
        self._vctx = WeaviateContextService(
            settings=settings,
            options=options,
            document_store=self._document_store,
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

        api_key_secret = Secret.from_token(settings.openai_api_key)
        base = settings.openai_api_base or None
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
        memory_docs = self._vctx.retrieve_memory(user_id=user_id, query_text=user_text)
        file_docs = self._vctx.retrieve_file_chunks(user_id=user_id, query_text=user_text)
        memory_block = _format_memory_block(memory_docs)
        file_block = format_file_hits_for_prompt(file_docs)
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

        self._vctx.persist_user_message(user_id=user_id, user_text=user_text)
        return AssistantReply(text=assistant_text, photo_urls=photo_urls)
