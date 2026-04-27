"""Чистые функции: обращение к боту, извлечение вопроса, нарезка длинного текста."""

from __future__ import annotations


def chunk_telegram_text(text: str, limit: int = 4096) -> list[str]:
    t = (text or "").strip()
    if not t:
        return ["(пусто)"]
    return [t[i : i + limit] for i in range(0, len(t), limit)]


def utf16_slice(text: str, offset: int, length: int) -> str:
    """
    Подстрока по offset/length в UTF-16 code units (как в Telegram `MessageEntity`).
    """
    if length <= 0 or not text:
        return ""
    as_le = text.encode("utf-16-le")
    b0, b1 = offset * 2, (offset + length) * 2
    if b0 < 0 or b0 > len(as_le):
        return ""
    try:
        return as_le[b0 : min(b1, len(as_le))].decode("utf-16-le")
    except UnicodeDecodeError:
        return ""


def _merge_entities(message: object) -> list:
    a = getattr(message, "entities", None) or []
    b = getattr(message, "caption_entities", None) or []
    return list(a) + list(b) if a or b else []


def is_bot_addressed(
    message_text: str | None,
    *,
    reply_to_user_id: int | None,
    bot_user_id: int,
    bot_username: str | None,
) -> bool:
    """
    Считаем, что к боту обращаются, если: ответ (reply) на сообщение бота
    ИЛИ в тексте есть @username бота.
    """
    if reply_to_user_id is not None and int(reply_to_user_id) == int(bot_user_id):
        return True
    if not message_text or not (bot_username and str(bot_username).strip()):
        return False
    u = str(bot_username).lstrip("@").lower()
    return f"@{u}" in (message_text or "").lower()


def is_message_to_bot(
    message: object,
    *,
    bot_user_id: int,
    bot_username: str | None,
) -> bool:
    """
    Тот же смысл, что и is_bot_addressed, плюс entity в Telegram: `text_mention` (у пользователя
    нет @username) и уточнённый `mention` по смещению в UTF-16 (как в API).
    """
    reply = getattr(message, "reply_to_message", None)
    if reply and getattr(reply, "from_user", None) is not None:
        if int(reply.from_user.id) == int(bot_user_id):
            return True
    text = (getattr(message, "text", None) or getattr(message, "caption", None) or "") or ""
    u = (str(bot_username).lstrip("@").lower() if bot_username and str(bot_username).strip() else "")
    if u and f"@{u}" in text.lower():
        return True
    for e in _merge_entities(message):
        et = getattr(e, "type", None)
        if et == "text_mention":
            eu = getattr(e, "user", None)
            if eu is not None and int(getattr(eu, "id", 0)) == int(bot_user_id):
                return True
        if et == "mention" and u and text:
            off, ln = int(getattr(e, "offset", 0) or 0), int(getattr(e, "length", 0) or 0)
            frag = utf16_slice(text, off, ln)
            if not frag and ln:
                frag = (text[off : off + ln] if off + ln <= len(text) else "")
            if frag.lower() == f"@{u}" or frag.lstrip("@").lower() == u:
                return True
    return False


def extract_query_after_mention(text: str, bot_username: str | None) -> str:
    """
    Оставляет содержимое вопроса, убирая первый префикс @bot (и типичный двоеточие в группе).
    """
    if not text or not (bot_username and str(bot_username).strip()):
        return (text or "").strip()
    u = str(bot_username).lstrip("@").strip()
    t = (text or "").strip()
    for prefix in (f"@{u}", f"@{u}:", f"@{u},", f"@{u} "):
        if t.lower().startswith(prefix.lower()):
            t = t[len(prefix) :].lstrip(" \t:,-—").strip()
            break
    if f"@{u}" in t:
        t = t.replace(f"@{u}", "", 1).strip(" \t:,-—")
    return t.strip()


def expand_query_for_vector_search(question: str) -> str:
    """
    Короткие вопросы вроде «что думаешь?» по эмбеддингу плохо бьют в тему переписки;
    добавляем нейтральный якорь для поиска по смыслу обсуждения.
    """
    q = (question or "").strip()
    if not q:
        return q
    low = q.lower()
    if len(q) > 64:
        return q
    vague = any(
        x in low
        for x in (
            "что думаешь",
            "что скажешь",
            "твоё мнение",
            "твое мнение",
            "как думаешь",
            "твоё отношение",
            "твое отношение",
            "согласен",
            "оцени",
        )
    )
    if not vague:
        return q
    # Без «курсов/планов» — иначе тянет старые векторы из прошлых обсуждений.
    return f"Недавние сообщения в группе, о чём сейчас говорят, факты и смысл реплик. Вопрос: {q}"
