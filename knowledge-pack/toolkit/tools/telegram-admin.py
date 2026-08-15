#!/usr/bin/env python3
"""
telegram-admin.py - admin helpers for the Houdini Telegram gateway.

Run with the Hermes venv python (it has the telegram library):
    VENV=$(grep -aoE '/[^ "]*/venv/bin/' "$(command -v hermes)" 2>/dev/null | head -1)
    PY="${VENV}python"
    [ -x "$PY" ] || PY=$(dirname $(dirname $(readlink -f $(command -v hermes))))/venv/bin/python
    $PY telegram-admin.py create-topic --icon-color 0 <chat_id> <topic name>

Commands (FLAGS FIRST - the parser consumes leading --flags before
positional args; putting flags after the name fails with the usage line):
  create-topic [--icon-color <0-6>] [--icon-emoji-id <custom_id>]
               [--icon <emoji>] <chat_id> <name>
    create a forum topic; prints the thread_id.
    --icon-color <0-6>            native Telegram topic icon color (no emoji
                                  needed in the name - keeps titles short)
    --icon <emoji>                pick the official Telegram topic icon whose
                                  emoji matches (112 official icons, resolved
                                  automatically via getForumTopicIconStickers)
    --icon-emoji-id <custom_id>   explicit custom emoji id

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


async def resolve_icon_id(bot: "telegram.Bot", icon_emoji: str) -> str | None:
    """Map a plain emoji (e.g. 🎯) to one of the 112 OFFICIAL Telegram
    topic icons via getForumTopicIconStickers. Returns the custom_emoji_id
    or None when no official icon matches that emoji."""
    try:
        stickers = await bot.get_forum_topic_icon_stickers()
    except Exception:
        return None
    for s in stickers:
        if getattr(s, "emoji", "") == icon_emoji:
            return s.custom_emoji_id
    return None


async def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    cmd = sys.argv[1]
    if cmd == "create-topic":
        args = sys.argv[2:]
        icon_color = None
        icon_emoji_id = None
        icon_emoji = None
        while args and args[0].startswith("--"):
            flag = args.pop(0)
            if flag == "--icon-color" and args:
                icon_color = int(args.pop(0))
            elif flag == "--icon-emoji-id" and args:
                icon_emoji_id = args.pop(0)
            elif flag == "--icon" and args:
                icon_emoji = args.pop(0)
            else:
                sys.exit(f"unknown option: {flag}")
        if len(args) != 2:
            sys.exit(
                "usage: telegram-admin.py create-topic [--icon-color 0-6] "
                "[--icon-emoji-id <id>] [--icon <emoji>] <chat_id> <name>"
            )
        if icon_emoji and not icon_emoji_id:
            from telegram import Bot

            bot = Bot(token=get_token())
            icon_emoji_id = await resolve_icon_id(bot, icon_emoji)
            if not icon_emoji_id:
                sys.exit(
                    f"no official topic icon matches emoji {icon_emoji} "
                    f"(run getForumTopicIconStickers to list the 112)"
                )
        await create_topic(args[0], args[1], icon_color, icon_emoji_id)
    else:
        sys.exit(f"unknown command: {cmd}")


if __name__ == "__main__":
    asyncio.run(main())
