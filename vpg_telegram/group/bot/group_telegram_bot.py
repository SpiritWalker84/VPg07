"""Сборка: Weaviate, Haystack, сессии «слушаю», RAG по @упоминанию / reply (PyTelegramBotAPI)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import telebot
from telebot import types

from vpg_telegram.group.bot.textutil import (
    chunk_telegram_text,
    expand_query_for_vector_search,
    extract_query_after_mention,
    is_message_to_bot,
)
from vpg_telegram.group.config import GroupOptions, load_group_options
from vpg_telegram.group.ingestion import (
    GroupMessageIndexingService,
    build_group_message_document,
    build_session_summary_document,
)
from vpg_telegram.group.llm import answer_with_citations, summarize_listening_session
from vpg_telegram.group.pipelines.index_pipeline import build_group_index_pipeline
from vpg_telegram.group.retrieval import GroupChatRagService
from vpg_telegram.group.retrieval.group_rag import format_hits_for_prompt
from vpg_telegram.group.state import ListeningSessionState, append_transcript_line
from vpg_telegram.group.group_vectorstore import build_group_document_store
from vpg07.config import Settings

logger = logging.getLogger(__name__)

_GROUP = frozenset({"group", "supergroup"})

_HELP_GROUP = (
    "Команды (только в группе): сессия «слушаю» — /listen on или /listen_on (старт) и /listen off или /listen_off (стоп и сводка). "
    "Пробел или подчёркивание: оба варианта. Далее: ответ (reply) на бота или @упоминание в тексте — вопрос по контексту. "
    "Сообщения для поиска пишем в Weaviate."
)
_HELP_PRIVATE = (
    "Этот бот рассчитан на **групповой** чат: добавьте бота в группу, отключите privacy mode (или выдайте права), "
    "чтобы бот видел сообщения. Задайте отдельное имя коллекции `WEAVIATE_GROUP_COLLECTION_NAME` в .env. "
    + _HELP_GROUP
)


class HayGroupTelegramBot:
    def __init__(self, settings: Settings, options: GroupOptions) -> None:
        self._settings = settings
        self._options = options
        self._store = build_group_document_store(settings)
        self._index_pipeline = build_group_index_pipeline(
            settings=settings,
            document_store=self._store,
        )
        self._indexer = GroupMessageIndexingService(index_pipeline=self._index_pipeline)
        self._rag = GroupChatRagService(
            settings=settings,
            options=options,
            document_store=self._store,
        )
        self._sessions = ListeningSessionState()
        self._bot = telebot.TeleBot(settings.telegram_bot_token, parse_mode=None)
        self._bot_user_id: int | None = None
        self._bot_username: str | None = None

    def _ensure_bot_identity(self) -> None:
        if self._bot_user_id is not None:
            return
        me = self._bot.get_me()
        self._bot_user_id = int(me.id) if me else None
        self._bot_username = (me.username or "").strip() if me else None

    def _index_group_text_message(self, message: types.Message, text: str) -> None:
        self._ensure_bot_identity()
        if not message.from_user or not message.chat:
            return
        chat_id = int(message.chat.id)
        s = self._sessions.get(chat_id)
        session_id = s.session_id if s else ""
        chat_ts: str | None = None
        if message.date:
            chat_ts = datetime.fromtimestamp(int(message.date), tz=timezone.utc).isoformat()
        doc = build_group_message_document(
            text=text,
            tg_chat_id=chat_id,
            tg_user_id=int(message.from_user.id),
            tg_message_id=int(message.message_id or 0),
            author_display=self._author_label(message),
            session_id=session_id,
            chat_ts=chat_ts,
        )
        self._indexer.index_documents([doc])

    @staticmethod
    def _author_label(message: types.Message) -> str:
        u = message.from_user
        if not u:
            return "—"
        parts = [u.first_name or "", u.last_name or ""]
        n = " ".join(p for p in parts if p).strip()
        if u.username:
            return f"{n} (@{u.username})".strip() if n else f"@{u.username}"
        return n or str(u.id)

    @staticmethod
    def _thread_kw(message: types.Message) -> dict:
        """
        В супергруппе с темами (forum) ответ должен идти в ту же ветку, иначе Telegram может
        не показать сообщение пользователю в теме.
        """
        mid = getattr(message, "message_thread_id", None)
        if mid is not None:
            return {"message_thread_id": int(mid)}
        return {}

    def _on_listen_on(self, message: types.Message) -> None:
        if not message.chat or not message.from_user:
            return
        if message.chat.type not in _GROUP:
            self._bot.reply_to(
                message,
                "Сессия «слушаю» доступна только в группе.",
                **self._thread_kw(message),
            )
            return
        sid = self._sessions.start(int(message.chat.id))
        logger.info("listen_on chat_id=%s session_id=%s", message.chat.id, sid)
        self._bot.reply_to(
            message,
            "Сессия «слушаю» включена. Сообщения пишем в вектор и накапливаем для итоговой сводки. "
            f"Остановка: /listen_off (id сессии: {sid[:8]}…).",
            **self._thread_kw(message),
        )

    def _on_listen_off(self, message: types.Message) -> None:
        if not message.chat or not message.from_user:
            return
        if message.chat.type not in _GROUP:
            self._bot.reply_to(message, "Команда только в группе.", **self._thread_kw(message))
            return
        chat_id = int(message.chat.id)
        st = self._sessions.stop(chat_id)
        if not st or not st.buffer_lines:
            self._bot.reply_to(
                message,
                "Активной сессии не было или в ней не было сообщений.",
                **self._thread_kw(message),
            )
            return
        transcript = "\n".join(st.buffer_lines).strip()[: self._options.session_transcript_max_chars]
        self._bot.send_chat_action(
            message.chat.id,
            "typing",
            **self._thread_kw(message),
        )
        summary = summarize_listening_session(
            self._settings, self._options, transcript=transcript
        )
        sum_doc = build_session_summary_document(
            summary_text=summary,
            tg_chat_id=chat_id,
            session_id=st.session_id,
        )
        self._indexer.index_documents([sum_doc])
        for part in chunk_telegram_text(
            f"Сессия завершена. Сводка (также сохранена в поиске):\n\n{summary}"
        ):
            self._bot.reply_to(message, part, **self._thread_kw(message))
        logger.info("listen_off chat_id=%s session_id=%s", chat_id, st.session_id)

    def _on_group_text(self, message: types.Message) -> None:
        body = (message.text or message.caption or "").strip()
        if not body or not message.chat or not message.from_user:
            return
        if body.startswith("/"):
            return
        if message.chat.type not in _GROUP:
            return
        self._ensure_bot_identity()
        if self._bot_user_id and int(message.from_user.id) == int(self._bot_user_id):
            return
        addr = is_message_to_bot(
            message,
            bot_user_id=self._bot_user_id or 0,
            bot_username=self._bot_username,
        )
        tw = self._thread_kw(message)
        logger.info(
            "group_in chat=%s thread=%s addr=%s u=%r body=%r",
            message.chat.id,
            getattr(message, "message_thread_id", None),
            addr,
            self._bot_username,
            (body[:120] + "…") if len(body) > 120 else body,
        )

        # 1) Всегда индексируем реплику
        self._index_group_text_message(message, body)

        # 2) Сессия «слушаю» — в буфер
        s = self._sessions.get(int(message.chat.id))
        if s:
            line = self._sessions.line_from_message(message, body)
            append_transcript_line(
                s,
                line,
                max_total_chars=self._options.session_transcript_max_chars,
            )

        # 3) Вопрос боту
        if not addr:
            return
        if not self._bot_user_id:
            logger.error("get_me: нет id бота, ответ невозможен")
            return
        q = extract_query_after_mention(body, self._bot_username)
        if not q:
            q = "Коротко: о чём договорились в последних сообщениях, что важно вспомнить?"

        self._bot.send_chat_action(message.chat.id, "typing", **tw)
        try:
            q_search = expand_query_for_vector_search(q)
            hits = self._rag.retrieve(
                tg_chat_id=int(message.chat.id),
                query_text=q_search,
            )
            block = format_hits_for_prompt(hits)
            answer = answer_with_citations(
                self._settings, self._options, user_question=q, context_block=block
            )
        except Exception:
            logger.exception("RAG/answer failed")
            self._bot.reply_to(
                message,
                "Ошибка при ответе по контексту. Попробуйте ещё раз.",
                **tw,
            )
            return
        for part in chunk_telegram_text(answer):
            try:
                self._bot.reply_to(message, part, **tw)
            except Exception:
                logger.exception("reply_to failed part=%r", (part[:200] if part else ""))
                try:
                    self._bot.send_message(
                        message.chat.id,
                        part,
                        **tw,
                    )
                except Exception:
                    logger.exception("send_message fallback failed")

    def _on_help(self, message: types.Message) -> None:
        if not message.chat:
            return
        t = _HELP_PRIVATE if message.chat.type == "private" else _HELP_GROUP
        self._bot.reply_to(message, t, **self._thread_kw(message))

    def register_handlers(self) -> None:
        @self._bot.message_handler(commands=["start", "help"])
        def h_help(message: types.Message) -> None:
            self._on_help(message)

        @self._bot.message_handler(commands=["listen_on", "listen_off"])
        def h_listen_underscore(message: types.Message) -> None:
            if not message.text:
                return
            first = (message.text or "").split(maxsplit=1)[0]
            base = first.split("@", 1)[0].lower()
            if base == "/listen_on":
                self._on_listen_on(message)
            elif base == "/listen_off":
                self._on_listen_off(message)

        @self._bot.message_handler(
            content_types=["text"],
            func=lambda m: m.chat is not None
            and m.chat.type in _GROUP
            and bool(m.text and m.text.strip())
            and m.text.split()[0].split("@", 1)[0].lower() == "/listen",
        )
        def h_listen_spaced(message: types.Message) -> None:
            """Совпадает с /listen и /listen@bot; второе слово: on / off (часто так удобнее людям)."""
            t = (message.text or "").strip()
            parts = t.split()
            if len(parts) < 2:
                self._bot.reply_to(
                    message,
                    "Напишите через пробел: /listen on — начать сессию, /listen off — остановить и получить сводку. "
                    "То же с подчёркиванием: /listen_on, /listen_off.",
                    **self._thread_kw(message),
                )
                return
            sub = parts[1].lower().strip()
            if sub in ("on", "вкл", "старт", "start"):
                self._on_listen_on(message)
            elif sub in ("off", "выкл", "стоп", "stop", "end"):
                self._on_listen_off(message)
            else:
                self._bot.reply_to(
                    message,
                    "После /listen ожидается on или off, например: /listen on",
                    **self._thread_kw(message),
                )

        @self._bot.message_handler(
            content_types=["text", "photo", "video", "document"],
            func=lambda m: m.chat is not None
            and m.chat.type in _GROUP
            and not (m.text or m.caption or "").lstrip().startswith("/")
            and (m.text is not None or m.caption is not None),
        )
        def h_group_text(message: types.Message) -> None:
            try:
                self._on_group_text(message)
            except Exception:
                logger.exception("h_group_text failed")

    def run(self) -> None:
        self._store.client
        self._indexer.warm_up()
        self._ensure_bot_identity()
        self.register_handlers()
        logger.info(
            "Group bot polling as @%s (id=%s)",
            self._bot_username,
            self._bot_user_id,
        )
        self._bot.infinity_polling(skip_pending=True, interval=0, timeout=60)

    def close(self) -> None:
        self._store.close()


def run() -> None:
    settings, opts = load_group_options()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Не путать с логом vpg_telegram.v2 (там Docling / личный сценарий).
    logger.info("entrypoint vpg_telegram.group: группы, Weaviate, RAG (не vpg_telegram.v2)")
    settings.require_bot()
    settings.require_openai()
    settings.require_weaviate()
    app = HayGroupTelegramBot(settings, opts)
    try:
        app.run()
    finally:
        app.close()
