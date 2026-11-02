#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
import pytest

from suggester.core import db
from suggester.core.config import load_config
from suggester.core.schemas import SourceItem
from suggester.pipeline import collect
from suggester.pipeline.context import RunContext
#--------------------------------------------------------------#

# Fake sources
class FakeSource:
    name = "fake"
    uses_queries = False
    texts = ["first version"]

    def fetch(self, queries, since):
        return [SourceItem(platform="linkedin", source="fake", url="https://l.com/posts/a_1",
                           text=self.texts[-1]),
                SourceItem(platform="linkedin", source="fake", url="https://l.com/posts/b_2",
                           text="other post")]


class BrokenSource:
    name = "broken"
    uses_queries = False

    def fetch(self, queries, since):
        raise RuntimeError("API down")
#--------------------------------------------------------------#

# Setup: temp database, vizcorn registered, config pointed at the fake sources
@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("SUGGESTER_DB_PATH", str(tmp_path / "test.db"))
    conn = db.connect()
    db.init_db(conn)
    cid = db.upsert(conn, "clients", {"name": "vizcorn", "config_path": "x",
                                      "created_at": db.now_iso()}, ["name"])
    cfg = load_config("vizcorn").model_copy(update={"sources": ["broken", "fake"]})
    sources = {"fake": FakeSource(), "broken": BrokenSource()}
    monkeypatch.setattr(collect, "make_source", lambda name, client: sources[name])
    yield RunContext(cfg=cfg, conn=conn, client_id=cid, week="2026-W45")
    conn.close()


def count(ctx):
    return ctx.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
#--------------------------------------------------------------#

# Tests
def test_collect_stores_items_despite_broken_source(ctx):
    collect.run(ctx)                                            # "broken" fails, "fake" still runs
    assert count(ctx) == 2


def test_rerun_does_not_duplicate_and_updates_text(ctx):
    collect.run(ctx)
    first_seen = ctx.conn.execute("SELECT first_seen_at FROM items WHERE url LIKE '%a_1'").fetchone()[0]
    FakeSource.texts.append("edited version")
    collect.run(ctx)
    FakeSource.texts.pop()
    assert count(ctx) == 2
    row = ctx.conn.execute("SELECT text, first_seen_at FROM items WHERE url LIKE '%a_1'").fetchone()
    assert row["text"] == "edited version"
    assert row["first_seen_at"] == first_seen
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#