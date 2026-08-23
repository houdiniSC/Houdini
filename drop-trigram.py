#!/usr/bin/env python3
"""Drop the SQLite 3.46+-conflicting trigram FTS tables from state.db.

Hermes officially supports 'trigram off' (hermes_state.py handles absent
tables gracefully). This removes the source of the documented 3.46+ FTS
malformed/rebuild problem (NousResearch/hermes-agent #86027 / #82867).
"""
import sqlite3
import sys

DB = "/root/.hermes/state.db"

TABLES = [
    "messages_fts_trigram",
    "messages_fts_trigram_data",
    "messages_fts_trigram_idx",
    "messages_fts_trigram_docsize",
    "messages_fts_trigram_config",
    "messages_fts_trigram_insert",
    "messages_fts_trigram_delete",
    "messages_fts_trigram_update",
]

c = sqlite3.connect(DB)
try:
    existing = [
        r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'messages_fts_trigram%'"
        )
    ]
    print("trigram tables found:", len(existing))
    if not existing:
        print("nothing to drop")
        sys.exit(0)
    for t in existing:
        c.execute(f'DROP TABLE IF EXISTS "{t}"')
    c.commit()
    before = 0
    print("dropped:", existing)
    c.execute("VACUUM")
    print("VACUUM done")
finally:
    c.close()

# verify
c = sqlite3.connect(DB)
left = c.execute(
    "SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'messages_fts_trigram%'"
).fetchone()[0]
import os

print("remaining trigram tables:", left)
print("state.db size now:", round(os.path.getsize(DB) / 1024 / 1024, 1), "MB")
c.close()
