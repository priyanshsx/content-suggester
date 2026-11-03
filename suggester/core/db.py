#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports libraries 

import re 
import sqlite3 
from datetime import datetime, timezone 
from suggester.core.paths import MIGRATIONS_DIR, SCHEMA_PATH, db_path
#--------------------------------------------------------------#

# Global variables 
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
#--------------------------------------------------------------#

# Fetches the current time 
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
#--------------------------------------------------------------#

# establishes the db connection 
def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row 
    conn.execute("PRAGMA foreign_keys = ON")
    return conn 
#--------------------------------------------------------------#

def init_db(conn: sqlite3.Connection) -> list[str]:
    conn.executescript(SCHEMA_PATH.read_text())
    done = {r["filename"] for r in conn.execute("SELECT filename FROM schema_migrations")}
    applied = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if f.name in done:
            continue
        conn.executescript(f.read_text())
        conn.execute(
            "INSERT INTO schema_migrations (filename, applied_at) VALUES (?, ?)",
            (f.name, now_iso())
        )
        applied.append(f.name)
    conn.commit()
    return applied
#--------------------------------------------------------------#

# whitelists table/col names
def _check(*names: str) -> None:
    for n in names:
        if not _NAME.match(n):
            raise ValueError(f"Invalid SQL name: {n!r}")
#--------------------------------------------------------------#

# inserts rows OR updates if conflict_cols already exist 
def upsert(conn: sqlite3.Connection, table: str, row: dict,
           conflict_cols: list[str], update_cols: list[str] | None = None) -> int:
    cols = list(row)
    if update_cols is None:
        update_cols = [c for c in cols if c not in conflict_cols]
    _check(table, *cols, *conflict_cols, *update_cols)

    sets = update_cols or [conflict_cols[0]]
    sql = (
        f"INSERT INTO {table} ({", ".join(cols)}) "
        f"VALUES ({", ".join('?' for _ in cols)}) "
        f"ON CONFLICT ({', '.join(conflict_cols)}) DO UPDATE SET "
        + ", ".join(f"{c} = excluded.{c}" for c in sets)
        + " RETURNING id"
    )
    row_id = conn.execute(sql, [row[c] for c in cols]).fetchone()["id"]
    conn.commit()
    return row_id 
#--------------------------------------------------------------#

def get_client_id(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute("SELECT id FROM clients WHERE name = ?", (name,)).fetchone()
    if row is None: 
        raise ValueError(f"Client {name!r} not found. Run: python scripts/new_client.py {name}")
    return row["id"]
#--------------------------------------------------------------#

#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#