"""Сводка сессии и ответ по контексту (чат-эндпоинт, не pipeline Haystack)."""

from __future__ import annotations

import logging
from openai import OpenAI

from vpg_telegram.group.config import GroupOptions
from vpg07.config import Settings

logger = logging.getLogger(__name__)


def _client(settings: Settings) -> OpenAI:
    return OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base,
    )


def summarize_listening_session(
    settings: Settings,
    options: GroupOptions,
    *,
    transcript: str,
) -> str:
    """
    Анализ диалога: краткое резюме; если спор — нейтральное мнение; если решение — зафиксировать.
    """
    t = (transcript or "").strip()
    if not t:
        return "Транскрипт сессии пуст — нечего резюмировать."
    t = t[: options.session_transcript_max_chars]
    system = (
        "Ты помощник в рабочем чате компании. Отвечай на русском, структурированно, без воды. "
        "Сначала краткое резюме обсуждения. Если обсуждение было полемикой, добавь в конце кратко "
        "сбалансированное мнение (без оскорблений). Если договорились о конкретных действиях/решениях, "
        "сформулируй итоговое решение и шаги. Используй эмодзи по минимуму (можно 0). "
    )
    user = f"Полный транскрипт (реплики с метками времени и авторами):\n\n{t}"
    try:
        c = _client(settings)
        out = c.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=options.session_summary_max_tokens,
            temperature=0.4,
        )
        text = (out.choices[0].message.content or "").strip()
        return text or "Не удалось сформировать сводку."
    except Exception:
        logger.exception("summarize_listening_session failed")
        return "Ошибка при обращении к модели для сводки сессии. Попробуйте позже."


def answer_with_citations(
    settings: Settings,
    options: GroupOptions,
    *,
    user_question: str,
    context_block: str,
) -> str:
    """
    RAG-ответ: фрагменты переписки группы. Ответ — как у коллеги, не «анализ» самого вопроса.
    """
    system = (
        "Ты деловой помощник в групповом чате команды. Пиши по-русски коротко и по делу. "
        "Ниже — выдержки из переписки этой же группы (релевантные поиску). "
        "Ответь на вопрос собеседника, опираясь на смысл этих реплик. "
        "Если вопрос в духе «что думаешь?» / «как смотришь?» — кратко сформулируй своё мнение как участника: "
        "согласись или предложи уточнение, опираясь на то, что люди уже написали (курсы, темы, договорённости). "
        "Не пересказывай мета-информацию вроде «в контексте нет…», «пользователь спрашивает бота…», дату формата ответа. "
        "Не придумывай факты, которых нет в выдержках; если выдержек мало, так и скажи в одно предложение и чего не хватает. "
        "По желанию — одна фраза, отсылающая к сути обсуждения (курсы, договорённости), без разбора «кто кому писал»."
    )
    user = (
        f"Вопрос в чате:\n{user_question.strip()}\n\n"
        f"Фрагменты переписки группы (для твоего ответа):\n{context_block}"
    )
    try:
        c = _client(settings)
        out = c.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=options.mention_answer_max_tokens,
            temperature=0.3,
        )
        return (out.choices[0].message.content or "").strip() or "Пустой ответ модели."
    except Exception:
        logger.exception("answer_with_citations failed")
        return "Ошибка при генерации ответа. Попробуйте позже."
