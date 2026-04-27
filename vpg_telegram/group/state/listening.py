"""In-memory: активная сессия `listen_on` … `listen_off` (буфер для сводки в LLM)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from telebot import types

ChatKey = int


@dataclass
class SessionInfo:
    """Активная сессия в одном чате."""

    session_id: str
    buffer_lines: list[str] = field(default_factory=list)


class ListeningSessionState:
    """
    `chat_id` → сессия.

    Сообщения в буфер добавляются вне этого класса (формат строки);
    сессия создаётся/удаляется по командам.
    """

    def __init__(self) -> None:
        self._by_chat: dict[ChatKey, SessionInfo] = {}

    def start(self, chat_id: int) -> str:
        """Старт новой сессии. Если уже была — старая сбрасывается."""
        sid = str(uuid.uuid4())
        self._by_chat[int(chat_id)] = SessionInfo(session_id=sid, buffer_lines=[])
        return sid

    def is_active(self, chat_id: int) -> bool:
        return int(chat_id) in self._by_chat

    def get(self, chat_id: int) -> SessionInfo | None:
        return self._by_chat.get(int(chat_id))

    def stop(self, chat_id: int) -> SessionInfo | None:
        return self._by_chat.pop(int(chat_id), None)

    def line_from_message(
        self,
        message: types.Message,
        text: str,
    ) -> str:
        """Одна строка для итогового транскрипта (ISO + автор + текст)."""
        u = message.from_user
        name = "—"
        if u:
            parts = [u.first_name or "", u.last_name or ""]
            name = " ".join(p for p in parts if p).strip() or (u.username and f"@{u.username}" or str(u.id))
        ts = "?"
        if message.date:
            from datetime import datetime, timezone

            ts = datetime.fromtimestamp(int(message.date), tz=timezone.utc).isoformat()
        return f"[{ts}] {name}: {text.strip()}"


def append_transcript_line(
    st: SessionInfo,
    line: str,
    *,
    max_total_chars: int,
) -> None:
    """Добавляет строку; при переполнении отбрасывает самые ранние строки (хвост — свежий диалог)."""
    st.buffer_lines.append(line)
    while max_total_chars > 0 and len(st.buffer_lines) > 1:
        joined = "\n".join(st.buffer_lines)
        if len(joined) <= max_total_chars:
            break
        st.buffer_lines.pop(0)
