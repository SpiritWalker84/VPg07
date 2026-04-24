"""Telegram-бот v2: текст (агент + RAG), документы (Docling → Weaviate), инструменты v1."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import telebot

from hay_v2_bot.components.assistant import HaystackV2Assistant
from hay_v2_bot.config import V2Options, load_v2_options
from vpg07.config import Settings

logger = logging.getLogger(__name__)

_TELEGRAM_MAX = 4096

_ALLOWED_MIME = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}


def _chunk_text(text: str, limit: int = _TELEGRAM_MAX) -> list[str]:
    t = text.strip()
    if not t:
        return ["Пустой ответ."]
    return [t[i : i + limit] for i in range(0, len(t), limit)]


class HaystackV2TelegramBot:
    """Long polling: агент Haystack v2 + загрузка PDF/DOC/DOCX через Docling."""

    def __init__(self, settings: Settings, options: V2Options) -> None:
        self._settings = settings
        self._options = options
        self._assistant = HaystackV2Assistant(settings, options)
        self._bot = telebot.TeleBot(settings.telegram_bot_token, parse_mode=None)

    def _display_name(self, message: telebot.types.Message) -> str:
        u = message.from_user
        if not u:
            return ""
        parts = [u.first_name or "", u.last_name or ""]
        name = " ".join(p for p in parts if p).strip()
        if u.username:
            return f"{name} (@{u.username})".strip()
        return name or str(u.id)

    def register_handlers(self) -> None:
        @self._bot.message_handler(commands=["start"])
        def on_start(message: telebot.types.Message) -> None:
            self._bot.reply_to(
                message,
                "Здравствуйте. Я персональный ассистент на базе Haystack: веду диалог с опорой на долговременную "
                "семантическую память (Weaviate) и на документы, которые вы загружаете в этот чат.\n\n"
                "Как пользоваться:\n"
                "• Напишите сообщение — я отвечу с учётом релевантных фрагментов вашей переписки и загруженных файлов.\n"
                "• Отправьте документ в формате PDF или Word (DOCX/DOC) — я проанализирую содержимое, сохраню структурированные "
                "фрагменты в векторное хранилище и после обработки пришлю краткое резюме; далее вы сможете задавать вопросы по тексту.\n\n"
                "Дополнительно по запросу доступны лёгкие сценарии: случайный факт о кошках и описание случайной собаки с фотографией.\n\n"
                "Команда /help — краткая справка по командам.",
            )

        @self._bot.message_handler(commands=["help"])
        def on_help(message: telebot.types.Message) -> None:
            self._bot.reply_to(
                message,
                "/start — приветствие и описание возможностей\n/help — эта справка\n\n"
                "Текстовые сообщения: диалог и поиск по смыслу по вашей памяти и по загруженным документам.\n"
                "Файлы: PDF, DOCX или DOC — разбор и индексация (Docling), затем краткое резюме содержимого.\n"
                "При развёртывании задайте отдельную коллекцию в Weaviate под этот бот (см. README и .env.example).",
            )

        @self._bot.message_handler(content_types=["document"])
        def on_document(message: telebot.types.Message) -> None:
            if not message.from_user or not message.document:
                return
            doc = message.document
            mime = (doc.mime_type or "").strip()
            filename = (doc.file_name or "upload").strip() or "upload"
            ext_ok = filename.lower().endswith((".pdf", ".docx", ".doc"))
            mime_ok = (not mime) or (mime in _ALLOWED_MIME)
            if not (mime_ok or ext_ok):
                self._bot.reply_to(
                    message,
                    "Поддерживаются PDF и документы Word (DOCX/DOC). Пришлите файл в одном из этих форматов.",
                )
                return
            size = int(doc.file_size or 0)
            if size > 20 * 1024 * 1024:
                self._bot.reply_to(message, "Файл слишком большой для Telegram (лимит 20 МБ).")
                return

            user_id = int(message.from_user.id)
            suffix = Path(filename).suffix
            if not suffix:
                suffix = ".pdf" if mime == "application/pdf" else ".docx"

            self._bot.reply_to(
                message,
                "Файл получен. Запускаю анализ и сохранение. Это может занять немного времени…",
            )

            tmp_path: str | None = None
            try:
                file_info = self._bot.get_file(doc.file_id)
                data = self._bot.download_file(file_info.file_path)
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(data)
                    tmp_path = tmp.name

                result = self._assistant.ingest_file(user_id=user_id, path=tmp_path, filename=filename)
                self._bot.reply_to(
                    message,
                    "Готово. Я изучил этот файл, теперь можем его обсудить.",
                )
                summary = (result.summary or "").strip()
                if summary:
                    self._bot.reply_to(message, summary)
            except Exception:
                logger.exception("document ingest failed")
                self._bot.reply_to(
                    message,
                    "Не удалось обработать файл. Проверьте формат и размер, попробуйте ещё раз позже.",
                )
            finally:
                if tmp_path:
                    Path(tmp_path).unlink(missing_ok=True)

        @self._bot.message_handler(content_types=["text"])
        def on_text(message: telebot.types.Message) -> None:
            if not message.from_user:
                return
            raw = (message.text or "").strip()
            if not raw:
                return
            user_id = int(message.from_user.id)
            name = self._display_name(message)
            try:
                reply = self._assistant.reply(user_id=user_id, user_text=raw, display_name=name)
            except Exception:
                logger.exception("assistant.reply failed")
                self._bot.reply_to(message, "Произошла ошибка при обработке. Попробуйте ещё раз позже.")
                return
            chat_id = message.chat.id
            reply_to = message.message_id
            for i, photo_url in enumerate(reply.photo_urls):
                try:
                    if i == 0:
                        self._bot.send_photo(chat_id, photo_url, reply_to_message_id=reply_to)
                    else:
                        self._bot.send_photo(chat_id, photo_url)
                except Exception:
                    logger.exception("send_photo failed for %s", photo_url)
            body = (reply.text or "").strip()
            if body:
                for chunk in _chunk_text(body):
                    if chunk.strip():
                        self._bot.reply_to(message, chunk)

    def run(self) -> None:
        self._assistant.warm_up()
        self.register_handlers()
        self._bot.infinity_polling(skip_pending=True, interval=0, timeout=60)

    def close(self) -> None:
        self._assistant.close()


def run() -> None:
    settings, opts = load_v2_options()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings.require_bot()
    settings.require_openai()
    settings.require_weaviate()
    bot = HaystackV2TelegramBot(settings, opts)
    try:
        bot.run()
    finally:
        bot.close()


if __name__ == "__main__":
    run()
