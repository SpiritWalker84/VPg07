"""Точка входа группового бота: `python vpg_telegram.group/main.py` (PYTHONPATH должен содержать `src` и корень)."""

from __future__ import annotations

from vpg_telegram.group.bot.group_telegram_bot import run

if __name__ == "__main__":
    run()
