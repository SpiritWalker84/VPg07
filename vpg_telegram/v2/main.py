"""Точка входа v2-бота: PYTHONPATH должен включать корень репозитория и src/."""

from __future__ import annotations

import sys
from pathlib import Path

# Репозиторий: vpg_telegram/v2/main.py -> три уровня вверх
ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
for p in (ROOT, SRC):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from vpg_telegram.v2.bot.telegram_bot import run


if __name__ == "__main__":
    run()
