#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
import csv

from suggester.core.log import get_logger
from suggester.core.paths import output_dir
from suggester.pipeline.context import RunContext
#--------------------------------------------------------------#

# Global variables
log = get_logger(__name__)
COLUMNS = ["suggestion_id", "rank", "score", "platform", "pillar", "author", "posted_at", "url",
           "snippet", "why_it_matters", "comment_angle", "status", "note"]
SNIPPET_CHARS = 300
#--------------------------------------------------------------#

# Read this week's picks with everything a reviewer needs
def rows_for_week(ctx: RunContext) -> list[dict]:
    rows = ctx.conn.execute(
        "SELECT s.id AS suggestion_id, s.rank, s.score, i.platform, c.pillar, "
        "       COALESCE(i.author_name, i.author_handle, '') AS author, "
        "       COALESCE(i.posted_at, substr(i.first_seen_at, 1, 10)) AS posted_at, i.url, "
        "       i.text, c.reason AS why_it_matters, c.comment_angle, s.status "
        "FROM suggestions s JOIN items i ON i.id = s.item_id "
        "JOIN classifications c ON c.item_id = i.id "
        "WHERE s.client_id = ? AND s.week = ? ORDER BY s.rank",
        (ctx.client_id, ctx.week)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        text = " ".join((d.pop("text") or "").split())
        d["snippet"] = text[:SNIPPET_CHARS] + ("..." if len(text) > SNIPPET_CHARS else "")
        d["status"] = "" if d["status"] == "suggested" else d["status"]   # blank = to review
        d["note"] = ""
        out.append(d)
    return out
#--------------------------------------------------------------#

# Stage entry point (the CLI calls this)
def run(ctx: RunContext) -> None:
    rows = rows_for_week(ctx)
    folder = output_dir(ctx.cfg.client)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{ctx.week}.csv"
    # utf-8-sig so Excel shows German umlauts correctly
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({k: r.get(k, "") for k in COLUMNS} for r in rows)
    log.info("export: %d threads written to %s", len(rows), path)
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#