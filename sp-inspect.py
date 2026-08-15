import sqlite3, glob

for db in glob.glob("/root/.hermes/*.db") + glob.glob("/root/.hermes/**/*.db", recursive=True):
    try:
        c = sqlite3.connect(db)
        tabs = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        print(f"{db}: {tabs[:12]}")
        c.close()
    except Exception as e:
        print(db, "ERR", str(e)[:60])
