#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries 
import pytest 
from suggester.core import db 
#--------------------------------------------------------------#

@pytest.fixture 
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("SUGGESTER_DB_PATH", str(tmp_path / "test.db"))
    c = db.connect()
    db.init_db(c)
    yield c 
    c.close()
#--------------------------------------------------------------#

def add_client(conn, name="acme"):
    return db.upsert(conn, "clients",
                     {"name": name, "config_path": f"config/clients/{name}", "created_at": db.now_iso()},
                     conflict_cols=["name"])
#--------------------------------------------------------------#

def test_init_db_twice_is_harmless(conn):
    db.init_db(conn)
#--------------------------------------------------------------#

def test_upsert_same_row_twice_gives_one_row(conn):
    first = add_client(conn) 
    second = add_client(conn)
    assert first == second 
    assert conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0] == 1
#--------------------------------------------------------------#

def test_upsert_updates_columns(conn):
    cid = add_client(conn)
    item = {"client_id": cid, "platform": "linkedin", "source": "linkedin_search",
            "url": "https://example.com/p/1", "text": "old",
            "first_seen_at": "2026-11-01", "last_seen_at": "2026-11-01"}
    db.upsert(conn, "items", item, ["client_id", "url"], update_cols=["text", "last_seen_at"])
    db.upsert(conn, "items", {**item, "text": "new", "first_seen_at": "2026-11-02", "last_seen_at": "2026-11-02"},
              ["client_id", "url"], update_cols=["text", "last_seen_at"])
    row = conn.execute("SELECT text, first_seen_at, last_seen_at FROM items").fetchone()
    assert (row["text"], row["first_seen_at"], row["last_seen_at"]) == ("new", "2026-11-01", "2026-11-02")
#--------------------------------------------------------------#

def test_get_client_id(conn):
    cid = add_client(conn)
    assert db.get_client_id(conn, "acme") == cid 
    with pytest.raises(ValueError):
        db.get_client_id(conn, "missing")
#--------------------------------------------------------------#

def test_deleting_client_deletes_its_items(conn):
    cid = add_client(conn)
    db.upsert(conn, "items", {"client_id": cid, "platform": "x", "source": "x_grok",
                              "url": "https://x.com/a/1", "first_seen_at": "t", "last_seen_at": "t"},
              ["client_id", "url"])
    conn.execute("DELETE FROM clients WHERE id = ?", (cid,))
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0
#--------------------------------------------------------------#
 
def test_bad_table_name_rejected(conn):
    with pytest.raises(ValueError):
        db.upsert(conn, "clients; DROP TABLE items", {"name": "x"}, ["name"])
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#