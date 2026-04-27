"""Сессия «слушаю»: буфер транскрипта."""

from __future__ import annotations

from vpg_telegram.group.state import SessionInfo, append_transcript_line


def test_append_transcript_truncates_from_head() -> None:
    s = SessionInfo(session_id="x", buffer_lines=[])
    for _ in range(200):
        append_transcript_line(s, "x" * 30, max_total_chars=100)
    joined = "\n".join(s.buffer_lines)
    assert len(joined) <= 150
    assert s.buffer_lines
