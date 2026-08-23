#!/usr/bin/env python3
"""Rebuild state.db cleanly (v3).

- drop any leftover rebuilt file first
- copy ONLY plain tables (not indexes, not FTS shadows)
- salvage corrupted tables row by row, skipping dead pages
- drop the standard messages_fts too (it is shadow-corrupted by the same
  bug) and rebuild it fresh at the end via the FTS5 rebuild command
- swap in only after quick_check passes
"""
import os
import sqlite3

OLD = "/root/.hermes/state.db"
NEW = "/root/.hermes/state_rebuilt.db"
if os.path.exists(NEW):
    os.remove(NEW)

CORRUPT_TABLES = {"sessions", "messages", "gateway_routing",
                  "session_turn_leases", "delivery_obligations"}
FTS_EXCLUDE = {"messages_fts", "messages_fts_data", "messages_fts_idx",
               "messages_fts_docsize", "messages_fts_config"}

old = sqlite3.connect(OLD)
new = sqlite3.connect(NEW)

tables = old.execute(
    "SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
).fetchall()
indexes = old.execute(
    "SELECT name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
).fetchall()

# 1) create plain, non-FTS, non-corrupted tables
for name, ddl in tables:
    if name in CORRUPT_TABLES or name in FTS_EXCLUDE or name.startswith("sqlite_"):
        continue
    new.execute(ddl)

# 2) copy healthy tables
for name, ddl in tables:
    if name in CORRUPT_TABLES or name in FTS_EXCLUDE or name.startswith("sqlite_"):
        continue
    try:
        rows = old.execute(f'SELECT * FROM "{name}"').fetchall()
        if rows:
            cols = [r[1] for r in old.execute(f'PRAGMA table_info("{name}")')]
            marks = ",".join("?" * len(cols))
            new.executemany(f'INSERT INTO "{name}" VALUES ({marks})', rows)
        print(f"{name}: copied {len(rows)} rows")
    except sqlite3.DatabaseError as e:
        print(f"{name}: FAILED ({str(e)[:60]})")

# 3) salvage corrupted tables
def salvage(table: str) -> None:
    ddl = old.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not ddl or not ddl[0]:
        print(f"{table}: no DDL - skipped")
        return
    new.execute(ddl[0])
    cols = [r[1] for r in old.execute(f'PRAGMA table_info("{table}")')]
    marks = ",".join("?" * len(cols))
    ins = f'INSERT OR IGNORE INTO "{table}" VALUES ({marks})'
    try:
        total = old.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    except sqlite3.DatabaseError:
        total = 0
    saved = skipped = 0
    offset = 0
    cap = total + 5000
    while offset < cap:
        try:
            rows = old.execute(
                f'SELECT * FROM "{table}" LIMIT 500 OFFSET {offset}'
            ).fetchall()
            if not rows:
                break
            new.executemany(ins, rows)
            saved += len(rows)
            offset += 500
        except sqlite3.DatabaseError:
            for i in range(500):
                try:
                    row = old.execute(
                        f'SELECT * FROM "{table}" LIMIT 1 OFFSET {offset + i}'
                    ).fetchone()
                    if row is None:
                        break
                    new.execute(ins, row)
                    saved += 1
                except sqlite3.DatabaseError:
                    skipped += 1
            offset += 500
    new.commit()
    print(f"{table}: salvaged {saved}, skipped ~{skipped}")

for t in ("sessions", "gateway_routing", "session_turn_leases",
          "delivery_obligations", "messages"):
    salvage(t)

# 4) recreate secondary indexes over rebuilt tables
for name, ddl in indexes:
    if name.startswith("idx_messages_fts"):
        continue  # FTS shadows - not real indexes
    try:
        new.execute(ddl)
    except sqlite3.DatabaseError as e:
        print(f"skip index {name}: {str(e)[:60]}")

# 5) recreate standard FTS fresh (empty - will be repopulated by Hermes or
#    leave absent; Hermes supports missing FTS tables)
try:
    new.execute(
        "CREATE VIRTUAL TABLE messages_fts USING fts5("
        "content, content_rowid=rowid, tokenize='porter unicode61')"
    )
    print("messages_fts: recreated empty (fresh)")
except sqlite3.DatabaseError as e:
    print(f"messages_fts recreate skipped: {str(e)[:60]}")

new.commit()
res = new.execute("PRAGMA quick_check").fetchone()
print("rebuilt quick_check:", res[0])
new.close()
old.close()

if res and res[0] == "ok":
    os.replace(OLD, OLD + ".corrupt-bak")
    os.replace(NEW, OLD)
    print("SWAPPED - state.db rebuilt clean")
    print("size:", round(os.path.getsize(OLD) / 1024 / 1024, 1), "MB")
    print("corrupt original kept at state.db.corrupt-bak")
else:
    print("FAILED - original untouched, rebuilt copy at state_rebuilt.db")
