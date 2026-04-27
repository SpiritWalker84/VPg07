"""Тесты чистых функций группового бота (без Haystack)."""

from __future__ import annotations

from types import SimpleNamespace

from vpg_telegram.group.bot.textutil import (
    expand_query_for_vector_search,
    extract_query_after_mention,
    is_bot_addressed,
    is_message_to_bot,
)


def test_is_bot_addressed_reply() -> None:
    assert is_bot_addressed(
        "hello",
        reply_to_user_id=123,
        bot_user_id=123,
        bot_username="mybot",
    )


def test_is_bot_addressed_mention() -> None:
    assert is_bot_addressed(
        "hey @MyBot what is this",
        reply_to_user_id=None,
        bot_user_id=1,
        bot_username="mybot",
    )


def test_is_bot_addressed_no() -> None:
    assert not is_bot_addressed(
        "hello everyone",
        reply_to_user_id=None,
        bot_user_id=1,
        bot_username="mybot",
    )


def test_is_message_to_bot_text_mention() -> None:
    ent = SimpleNamespace(type="text_mention", user=SimpleNamespace(id=42))
    msg = SimpleNamespace(
        text="hello",
        caption=None,
        reply_to_message=None,
        entities=[ent],
    )
    assert is_message_to_bot(msg, bot_user_id=42, bot_username="any")


def test_extract_query() -> None:
    assert extract_query_after_mention("@mybot: скажи кто прав", "mybot") == "скажи кто прав"
    assert extract_query_after_mention("@mybot скажи", "mybot") == "скажи"


def test_expand_vector_query_short() -> None:
    out = expand_query_for_vector_search("что думаешь?")
    assert "недавн" in out.lower() or "групп" in out.lower()
    assert "что думаешь" in out.lower()
