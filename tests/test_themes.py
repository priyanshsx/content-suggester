#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: tests/test_themes.py
# Purpose: check the themes stage: which posts are used, the evidence rules (3 posts, 2 sources),
#          the cap per area, duplicate checks, stable IDs, and the Content Ideas tab round trip.
#          Uses a fake LLM and a fake Google Sheet: no API calls, no cost.
# Usage:   python -m pytest tests/test_themes.py -v
#--------------------------------------------------------------#

# Imports Libraries
from datetime import date

import pytest
from gspread.utils import a1_to_rowcol

from suggester.core import db
from suggester.core.config import load_config
from suggester.core.schemas import ThemeBatch, ThemeDraft
from suggester.pipeline import themes
from suggester.pipeline.context import RunContext
#--------------------------------------------------------------#

# Fake data
TODAY = date(2026, 11, 14)
WEEK = "2026-W46"

# (pillar, author, text, posted_at, relevant, job)
POSTS = [
    ("drawdowns_and_risk", "r/investing", "How long did it take you to recover from 2022?", "2026-11-10", 1, 0),
    ("drawdowns_and_risk", "r/Bitcoin", "Holding BTC through -70% was brutal, never again", "2026-11-09", 1, 0),
    ("drawdowns_and_risk", "Jane Trader", "Nobody talks about recovery time, only the drop", "2026-11-08", 1, 0),
    ("drawdowns_and_risk", "r/stocks", "Is a 30% drawdown normal for a growth portfolio?", "2026-11-07", 1, 0),
    ("drawdowns_and_risk", "r/investing", "My max drawdown made me sell at the bottom", "2026-11-06", 1, 0),
    ("drawdowns_and_risk", "Acme Recruiting", "JOBPOST hiring a quant risk analyst", "2026-11-10", 1, 1),
    ("drawdowns_and_risk", "r/investing", "OLDPOST from last month about crashes", "2026-10-01", 1, 0),
    ("volatility_and_tails", "r/options", "Fat tails are underrated", "2026-11-10", 1, 0),
    ("volatility_and_tails", "r/Bitcoin", "Vol crush after the halving?", "2026-11-09", 1, 0),
    ("cross_asset", "Gold Bug", "BTC vs gold, gold wins", "2026-11-10", 1, 0),
    ("cross_asset", "Gold Bug", "Gold beat BTC on risk again", "2026-11-09", 1, 0),
    ("cross_asset", "Gold Bug", "Gold is the real store of value", "2026-11-08", 1, 0),
    ("none", "r/random", "Unrelated post", "2026-11-10", 1, 0),
]


def draft(theme, evidence, angle="An angle", cue="Measure max drawdown and recovery for BTC 2022"):
    return ThemeDraft(reason="recurs", theme=theme, angle=angle, research_cue=cue, evidence=evidence)


# What the fake LLM answers per area (posts are numbered 1..N in score/date order, newest first)
ANSWERS = {
    "drawdowns_and_risk": ThemeBatch(themes=[
        draft("Traders judge crashes by depth but suffer most from recovery time", [1, 2, 3]),
        draft("One real post only", [1, 99]),                                  # 1 valid post: drop
        draft("Traders judge crashes by depth but suffer from long recovery time", [1, 2, 4]),  # repeat
        draft("Retail sells at the bottom because sizing ignored drawdowns", [3, 4, 5]),
        draft("A third good theme that exceeds the cap per area", [2, 4, 5]),   # cap of 2: drop
    ]),
    "cross_asset": ThemeBatch(themes=[draft("Gold keeps beating BTC on risk", [1, 2, 3])]),  # 1 author
}
#--------------------------------------------------------------#

# A fake Google Sheet tab with just what the sync code uses
class FakeSheet:
    def __init__(self):
        self.rows, self.col_count = [], 26

    def get_all_values(self):
        return [list(r) for r in self.rows]

    def update(self, range_name, values):                 # only used for the header row
        if self.rows:
            self.rows[0] = list(values[0])
        else:
            self.rows.append(list(values[0]))

    def add_cols(self, n):
        self.col_count += n

    def batch_update(self, updates, value_input_option=None):
        for u in updates:
            r, c = a1_to_rowcol(u["range"])
            row = self.rows[r - 1]
            row.extend([""] * (c - len(row)))
            row[c - 1] = u["values"][0][0]

    def insert_rows(self, rows, row=2, value_input_option=None):
        self.rows[row - 1:row - 1] = [list(x) for x in rows]

    def records(self):
        head = self.rows[0]
        return [dict(zip(head, r + [""] * (len(head) - len(r)))) for r in self.rows[1:]]
#--------------------------------------------------------------#

# Setup: temp database with Quartermaster's posts, fake LLM, fake sheet
@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("SUGGESTER_DB_PATH", str(tmp_path / "test.db"))
    conn = db.connect()
    db.init_db(conn)
    cid = db.upsert(conn, "clients", {"name": "quartermaster", "config_path": "x",
                                      "created_at": db.now_iso()}, ["name"])
    for n, (pillar, author, text, day, relevant, job) in enumerate(POSTS):
        item_id = db.upsert(conn, "items", {
            "client_id": cid, "platform": "reddit" if author.startswith("r/") else "linkedin",
            "source": "fake", "url": f"https://example.com/p/{n}", "author_name": author,
            "text": text, "posted_at": day, "first_seen_at": day, "last_seen_at": day},
            ["client_id", "url"])
        conn.execute("INSERT INTO classifications (item_id, is_relevant, pillar, is_job_post, score, "
                     "created_at) VALUES (?, ?, ?, ?, ?, ?)",
                     (item_id, relevant, pillar, job, 100 - n, db.now_iso()))
    conn.commit()

    calls = []

    def fake_llm(task, prompt, schema, conn, client_id=None, max_tokens=1024, use_cache=True):
        pillar = next(p for p in ANSWERS.keys() | {"volatility_and_tails"} if f"\n{p}:" in prompt)
        calls.append((pillar, prompt))
        return ANSWERS.get(pillar, ThemeBatch())
    monkeypatch.setattr(themes, "call_llm", fake_llm)

    sheet = FakeSheet()
    monkeypatch.setattr("suggester.core.sheets.open_worksheet", lambda sid, tab: sheet)

    cfg = load_config("quartermaster")
    context = RunContext(cfg=cfg, conn=conn, client_id=cid, week=WEEK)
    context.calls, context.sheet = calls, sheet
    yield context
    conn.close()


def stored(ctx):
    return [dict(r) for r in ctx.conn.execute("SELECT * FROM themes ORDER BY id")]
#--------------------------------------------------------------#

# Tests: the rules
def test_rules_evidence_duplicates_and_cap(ctx):
    themes.run(ctx, today=TODAY)
    rows = stored(ctx)
    assert [r["theme"] for r in rows] == [
        "Traders judge crashes by depth but suffer most from recovery time",
        "Retail sells at the bottom because sizing ignored drawdowns"]
    assert [r["theme_id"] for r in rows] == ["quartermaster-2026w46-01", "quartermaster-2026w46-02"]
    assert rows[0]["post_count"] == 3 and rows[0]["source_count"] == 3
    assert rows[0]["pillar_rank"] == 1 and rows[0]["research_cue"].startswith("Measure")
    assert rows[0]["status"] == "new"


def test_areas_with_too_few_posts_make_no_llm_call(ctx):
    themes.run(ctx, today=TODAY)
    assert sorted(p for p, _ in ctx.calls) == ["cross_asset", "drawdowns_and_risk"]   # not volatility


def test_one_author_is_not_enough(ctx):
    themes.run(ctx, today=TODAY)
    assert not any(r["pillar"] == "cross_asset" for r in stored(ctx))


def test_job_posts_old_posts_and_other_are_left_out(ctx):
    themes.run(ctx, today=TODAY)
    prompt = dict(ctx.calls)["drawdowns_and_risk"]
    assert "JOBPOST" not in prompt and "OLDPOST" not in prompt and "Unrelated" not in prompt


def test_evidence_is_stored_with_the_theme(ctx):
    themes.run(ctx, today=TODAY)
    n = ctx.conn.execute("SELECT COUNT(*) FROM theme_items ti JOIN themes t ON t.id = ti.theme_pk "
                         "WHERE t.theme_id = 'quartermaster-2026w46-01'").fetchone()[0]
    assert n == 3
#--------------------------------------------------------------#

# Tests: repeat runs and switches
def test_second_run_same_week_adds_nothing(ctx):
    themes.run(ctx, today=TODAY)
    calls_first_run = len(ctx.calls)
    themes.run(ctx, today=TODAY)
    assert len(stored(ctx)) == 2                                      # cap is per area per week
    # drawdowns is full, so only cross_asset (no themes yet) is asked again
    assert [p for p, _ in ctx.calls[calls_first_run:]] == ["cross_asset"]


def test_next_week_shows_earlier_themes_to_the_llm(ctx):
    themes.run(ctx, today=TODAY)
    ctx.week = "2026-W47"
    themes.run(ctx, today=TODAY)
    prompt = [pr for p, pr in ctx.calls if p == "drawdowns_and_risk"][-1]
    assert "Traders judge crashes by depth" in prompt                 # so it doesn't repeat them
    assert [r["theme_id"] for r in stored(ctx)][-1] == "quartermaster-2026w47-01"


def test_disabled_client_is_skipped(ctx):
    ctx.cfg = ctx.cfg.model_copy(update={"themes": ctx.cfg.themes.model_copy(update={"enabled": False})})
    themes.run(ctx, today=TODAY)
    assert ctx.calls == [] and stored(ctx) == []


def test_dry_run_makes_no_calls(ctx):
    ctx.dry_run = True
    themes.run(ctx, today=TODAY)
    assert ctx.calls == [] and stored(ctx) == []


def test_no_research_cue_when_not_configured(ctx):
    ctx.cfg = ctx.cfg.model_copy(update={"themes": ctx.cfg.themes.model_copy(update={"research_cue": ""})})
    themes.run(ctx, today=TODAY)
    assert all(r["research_cue"] is None for r in stored(ctx))
#--------------------------------------------------------------#

# Tests: Content Ideas tab
def test_sheet_gets_themes_and_picks_come_back(ctx):
    themes.run(ctx, today=TODAY)
    recs = ctx.sheet.records()
    assert [r["theme_id"] for r in recs] == ["quartermaster-2026w46-02", "quartermaster-2026w46-01"]
    assert all(r["status"] == "new" for r in recs)
    assert recs[1]["evidence_urls"].count("https://example.com/p/") == 3
    assert recs[1]["expertise"] == "drawdowns_and_risk" and recs[1]["expertise_rank"] == "1"

    # the client picks one and publishes it, and rejects the other
    head = ctx.sheet.rows[0]
    first = ctx.sheet.rows[2]                                   # quartermaster-2026w46-01
    first.extend([""] * (len(head) - len(first)))
    first[head.index("status")] = "Published"
    first[head.index("published_url")] = "https://x.com/me/status/1"
    second = ctx.sheet.rows[1]
    second[head.index("status")] = "rejected"

    themes.run(ctx, today=TODAY)
    by_id = {r["theme_id"]: r for r in stored(ctx)}
    assert by_id["quartermaster-2026w46-01"]["status"] == "published"
    assert by_id["quartermaster-2026w46-01"]["published_url"] == "https://x.com/me/status/1"
    assert by_id["quartermaster-2026w46-02"]["status"] == "rejected"
    assert len(ctx.sheet.records()) == 2                        # no duplicate rows
    assert ctx.sheet.records()[1]["status"] == "Published"     # the client's cell is never overwritten
#--------------------------------------------------------------#

# Tests: duplicate check
def test_is_duplicate():
    assert themes.is_duplicate("Retail panics in the first 20% drawdown",
                               "Retail traders panic during the first 20% drawdown")
    assert not themes.is_duplicate("Retail panics in the first 20% drawdown",
                                   "Gold beats bitcoin on risk-adjusted returns")
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#
