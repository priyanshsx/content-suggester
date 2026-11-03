#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#


# Imports Libraries
import csv
import json
from datetime import date

import pytest

from suggester.core import db
from suggester.core.config import load_config
from suggester.core.schemas import ThreadClassification
from suggester.pipeline import classify, export, feedback, report, score, select
from suggester.pipeline.context import RunContext
#--------------------------------------------------------------#

# Fake data: (url, author, text, verdict)
TODAY = date(2026, 11, 3)


def verdict(relevant=True, author="buyer", pain=True, region="DACH", pillar="mdg"):
    return ThreadClassification(reason="test", is_relevant=relevant, pillar=pillar,
                                author_type=author, has_pain_or_question=pain, region=region,
                                comment_angle="say something useful" if relevant else "",
                                new_terms=["golden record"])


ITEMS = [
    ("https://l.com/posts/a_1", "Anna", "MDG rollout stalled, ownership unclear", verdict()),
    ("https://l.com/posts/a_2", "Anna", "Second MDG post from Anna", verdict()),
    ("https://l.com/posts/a_3", "Anna", "Third MDG post from Anna", verdict()),
    ("https://l.com/posts/b_1", "Ben", "Book a demo of our MDG tool today", verdict(author="vendor")),
    ("https://l.com/posts/c_1", "Cara", "Hiring SAP consultant in Berlin now", verdict(relevant=False)),
    ("https://l.com/posts/d_1", "Dan", "Duplicate vendors after BP conversion",
     verdict(pillar="s4hana_readiness")),
    ("https://l.com/posts/e_1", "Eva", "PM equipment master is a mess here",
     verdict(pillar="plant_maintenance", region="other", pain=False)),
]
#--------------------------------------------------------------#

# Setup: temp database with vizcorn + the fake items; fake LLM returns the verdict per text
@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("SUGGESTER_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setattr("suggester.pipeline.export.output_dir", lambda c: tmp_path / "out")
    monkeypatch.setattr("suggester.pipeline.report.output_dir", lambda c: tmp_path / "out")
    conn = db.connect()
    db.init_db(conn)
    cid = db.upsert(conn, "clients", {"name": "vizcorn", "config_path": "x",
                                      "created_at": db.now_iso()}, ["name"])
    by_text = {}
    for url, author, text, v in ITEMS:
        db.upsert(conn, "items", {"client_id": cid, "platform": "linkedin", "source": "fake",
                                  "url": url, "author_name": author, "text": text,
                                  "posted_at": "2026-11-01", "source_query": f"q-{author}",
                                  "raw_json": json.dumps({"title": f"post | {author} | 5 comments"}),
                                  "first_seen_at": db.now_iso(), "last_seen_at": db.now_iso()},
                  ["client_id", "url"])
        by_text[text] = v
    monkeypatch.setattr(classify, "call_llm",
                        lambda task, prompt, schema, conn, client_id:
                        next(v for t, v in by_text.items() if t in prompt))
    cfg = load_config("vizcorn").model_copy(update={"threads_per_week": 3})
    yield RunContext(cfg=cfg, conn=conn, client_id=cid, week="2026-W45")
    conn.close()


def picked_urls(ctx):
    return [r[0] for r in ctx.conn.execute(
        "SELECT i.url FROM suggestions s JOIN items i ON i.id = s.item_id ORDER BY s.rank")]


def run_until_select(ctx):
    classify.run(ctx)
    score.run(ctx, today=TODAY)
    select.run(ctx, today=TODAY)
#--------------------------------------------------------------#

# Tests: classify
def test_classify_stores_every_item_once(ctx):
    classify.run(ctx)
    classify.run(ctx)                                   # second run: nothing left to classify
    assert ctx.conn.execute("SELECT COUNT(*) FROM classifications").fetchone()[0] == len(ITEMS)


def test_unknown_pillar_becomes_none(ctx, monkeypatch):
    monkeypatch.setattr(classify, "call_llm", lambda *a, **k: verdict(pillar="made_up"))
    v = classify.classify_one(ctx.cfg, ctx.conn, ctx.client_id, {"text": "x" * 30})
    assert v.pillar == "none"
#--------------------------------------------------------------#

# Tests: score + select
def test_vendor_and_irrelevant_never_picked(ctx):
    run_until_select(ctx)
    urls = picked_urls(ctx)
    assert "https://l.com/posts/b_1" not in urls and "https://l.com/posts/c_1" not in urls


def test_max_per_author_and_count(ctx):
    run_until_select(ctx)
    urls = picked_urls(ctx)
    assert len(urls) == 3                               # threads_per_week
    assert sum("a_" in u for u in urls) <= ctx.cfg.max_per_author


def test_pain_and_region_score_higher(ctx):
    classify.run(ctx)
    score.run(ctx, today=TODAY)
    scores = dict(ctx.conn.execute(
        "SELECT i.author_name, c.score FROM classifications c JOIN items i ON i.id = c.item_id "
        "WHERE c.score IS NOT NULL"))
    assert scores["Dan"] > scores["Eva"]                # Dan: pain + DACH; Eva: neither


def test_rerun_same_week_is_stable(ctx):
    run_until_select(ctx)
    first = picked_urls(ctx)
    select.run(ctx, today=TODAY)
    assert picked_urls(ctx) == first


def test_never_resuggested_next_week(ctx):
    run_until_select(ctx)
    first = set(picked_urls(ctx))
    nxt = RunContext(cfg=ctx.cfg, conn=ctx.conn, client_id=ctx.client_id, week="2026-W46")
    score.run(nxt, today=TODAY)
    select.run(nxt, today=TODAY)
    week46 = [r[0] for r in ctx.conn.execute(
        "SELECT i.url FROM suggestions s JOIN items i ON i.id = s.item_id WHERE s.week='2026-W46'")]
    assert not first & set(week46)
#--------------------------------------------------------------#

# Tests: export -> feedback -> report
def test_export_feedback_report_round_trip(ctx, tmp_path):
    run_until_select(ctx)
    export.run(ctx)
    path = tmp_path / "out" / "2026-W45.csv"
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3 and rows[0]["comment_angle"] and rows[0]["status"] == ""

    rows[0]["status"], rows[1]["status"] = "engaged", "s"    # third left blank = not reviewed
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=export.COLUMNS)
        w.writeheader()
        w.writerows(rows)

    ctx.feedback_file = str(path)
    feedback.run(ctx)
    assert feedback.approval_rate(ctx) == (1, 2)

    report.run(ctx)
    with open(tmp_path / "out" / "new_terms.csv", encoding="utf-8-sig") as f:
        assert "golden record" in f.read()
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#