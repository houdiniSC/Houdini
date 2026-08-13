#!/usr/bin/env python3
"""
session-titles.py - make Hermes session display names use the forum-topic
title, so the WebUI shows "🎯 <target>" instead of the group name.

1. Patches gateway/session.py (idempotent): session display_name prefers the
   title from ~/.hermes/topic_titles.json (key "<chat_id>:<thread_id>").
2. Rebuilds ~/.hermes/topic_titles.json from workspace_topics.json plus the
   known base topic names (keeps agent-recorded target titles).

Run with any python3:
    python3 ~/.hermes/toolkit/tools/session-titles.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERMES = Path.home() / ".hermes"
SESSION_PY = HERMES / "hermes-agent" / "gateway" / "session.py"
TITLES = HERMES / "topic_titles.json"
WORKSPACE = HERMES / "workspace_topics.json"

BASE_NAMES = {
    "general": "عام",
    "targets": "🎯 الأهداف",
    "reports": "📋 التقارير",
    "scheduled": "⏰ المهام المجدولة",
    "settings": "⚙️ الإعدادات",
}

PATCH_HELPER = '''
def _resolve_topic_title(chat_id, thread_id):
    """Prefer the forum-topic title recorded in topic_titles.json."""
    try:
        if not thread_id:
            return None
        p = Path.home() / ".hermes" / "topic_titles.json"
        if not p.is_file():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get(f"{chat_id}:{thread_id}") or None
    except Exception:
        return None
'''

OLD = "display_name=source.chat_name,"
NEW = "display_name=_resolve_topic_title(source.chat_id, source.thread_id) or source.chat_name,"


def patch_session_py() -> bool:
    if not SESSION_PY.is_file():
        print("session.py not found:", SESSION_PY)
        return False
    text = SESSION_PY.read_text(encoding="utf-8")
    if "_resolve_topic_title" in text:
        print("session.py already patched")
        return True
    marker = "from pathlib import Path"
    if marker not in text:
        print("import marker not found")
        return False
    text = text.replace(marker, marker + "\n" + PATCH_HELPER, 1)
    count = text.count(OLD)
    text = text.replace(OLD, NEW)
    SESSION_PY.write_text(text, encoding="utf-8")
    print(f"session.py patched ({count} display_name sites)")
    return True


def rebuild_titles() -> None:
    titles: dict = {}
    ws: dict = {}
    if WORKSPACE.is_file():
        try:
            ws = json.loads(WORKSPACE.read_text(encoding="utf-8"))
        except Exception:
            ws = {}
    hc = ws.get("home_channel") or {}
    chat_id = hc.get("chat_id")
    for slug, tid in (hc.get("topics") or {}).items():
        if chat_id is None:
            continue
        if str(slug).startswith("target:"):
            name = "🎯 " + str(slug).split(":", 1)[1]
        else:
            name = BASE_NAMES.get(str(slug), str(slug))
        titles[f"{chat_id}:{tid}"] = name
    if chat_id is not None:
        titles.setdefault(f"{chat_id}:1", "عام")  # Telegram built-in General topic
    old: dict = {}
    if TITLES.is_file():
        try:
            old = json.loads(TITLES.read_text(encoding="utf-8"))
        except Exception:
            old = {}
    old.update(titles)
    TITLES.parent.mkdir(parents=True, exist_ok=True)
    TITLES.write_text(json.dumps(old, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"topic_titles.json: {len(old)} entries")


if __name__ == "__main__":
    patch_session_py()
    rebuild_titles()
