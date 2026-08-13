#!/usr/bin/env python3
"""
telegram-admin.py - admin helpers for the Houdini Telegram gateway.

Run with the Hermes venv python (it has the telegram library):
    ~/.hermes/hermes-agent/venv/bin/python telegram-admin.py \
        create-topic <chat_id> <topic name>

Commands:
  create-topic <chat_id> <name>   create a forum topic; prints the thread_id

The bot token is read from ~/.hermes/.env (TELEGRAM_BOT_TOKEN) or the env.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


def get_token() -> str:
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


async def create_topic(chat_id: str, name: str) -> None:
    from telegram import Bot

    token = get_token()
    if not token:
        sys.exit("TELEGRAM_BOT_TOKEN not found in ~/.hermes/.env")
    bot = Bot(token=token)
    res = await bot.create_forum_topic(chat_id=int(chat_id), name=name)
    print(res.message_thread_id)


async def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    cmd = sys.argv[1]
    if cmd == "create-topic":
        if len(sys.argv) != 4:
            sys.exit("usage: telegram-admin.py create-topic <chat_id> <name>")
        await create_topic(sys.argv[2], sys.argv[3])
    else:
        sys.exit(f"unknown command: {cmd}")


if __name__ == "__main__":
    asyncio.run(main())
