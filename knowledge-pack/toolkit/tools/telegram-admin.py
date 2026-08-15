#!/usr/bin/env python3
"""
telegram-admin.py - admin helpers for the Houdini Telegram gateway.

Run with the Hermes venv python (it has the telegram library):
    ~/.hermes/hermes-agent/venv/bin/python telegram-admin.py \
        create-topic <chat_id> <topic name> --icon-color 0

Commands:
  create-topic <chat_id> <name>   create a forum topic; prints the thread_id
    --icon-color <0-6>            native Telegram topic icon color (no emoji
                                  needed in the name - keeps titles short)
    --icon-emoji-id <custom_id>   optional custom emoji icon id

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


async def create_topic(
    chat_id: str,
    name: str,
    icon_color: int | None = None,
    icon_emoji_id: str | None = None,
) -> None:
    from telegram import Bot

    token = get_token()
    if not token:
        sys.exit("TELEGRAM_BOT_TOKEN not found in ~/.hermes/.env")
    bot = Bot(token=token)
    kwargs: dict = {}
    if icon_color is not None:
        kwargs["icon_color"] = icon_color
    if icon_emoji_id:
        kwargs["icon_custom_emoji_id"] = icon_emoji_id
    res = await bot.create_forum_topic(chat_id=int(chat_id), name=name, **kwargs)
    print(res.message_thread_id)


async def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    cmd = sys.argv[1]
    if cmd == "create-topic":
        args = sys.argv[2:]
        icon_color = None
        icon_emoji_id = None
        while args and args[0].startswith("--"):
            flag = args.pop(0)
            if flag == "--icon-color" and args:
                icon_color = int(args.pop(0))
            elif flag == "--icon-emoji-id" and args:
                icon_emoji_id = args.pop(0)
            else:
                sys.exit(f"unknown option: {flag}")
        if len(args) != 2:
            sys.exit(
                "usage: telegram-admin.py create-topic <chat_id> <name> "
                "[--icon-color 0-6] [--icon-emoji-id <id>]"
            )
        await create_topic(args[0], args[1], icon_color, icon_emoji_id)
    else:
        sys.exit(f"unknown command: {cmd}")


if __name__ == "__main__":
    asyncio.run(main())
