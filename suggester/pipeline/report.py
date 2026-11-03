#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
import csv
import json
from collections import Counter

from suggester.core.log import get_logger
from suggester.core.paths import output_dir
from suggester.pipeline.context import RunContext
#--------------------------------------------------------------#

# Global variables
log = get_logger(__name__)
COLUMNS = ["source_query", "found", "classified", "relevant", "relevant_pct",
           "suggested", "engaged", "skipped"]
#--------------------------------------------------------------#

# Per-query numbers
def keyword_rows(ctx: RunContext) -> list[dict]:
    rows = ctx.conn.execute(
        "SELECT COALESCE(i.source_query, i.source) AS source_query, "
        "       COUNT(*) AS found, COUNT(c.id) AS classified, "
        "       COALESCE(SUM(c.is_relevant), 0) AS relevant, "
        "       COUNT(s.id) AS suggested, "
        "       COALESCE(SUM(s.status = 'engaged'), 0) AS engaged, "
        "       COALESCE(SUM(s.status = 'skipped'), 0) AS skipped "
        "FROM items i LEFT JOIN classifications c ON c.item_id = i.id "
        "LEFT JOIN suggestions s ON s.item_id = i.id "
        "WHERE i.client_id = ? GROUP BY 1 ORDER BY engaged DESC, relevant DESC, found DESC",
        (ctx.client_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["relevant_pct"] = round(100 * d["relevant"] / d["classified"]) if d["classified"] else ""
        out.append(d)
    return out
#--------------------------------------------------------------#

# Phrases the classifier suggested, most frequent first
def new_terms(ctx: RunContext) -> list[tuple[str, int]]:
    counts: Counter = Counter()
    for (terms,) in ctx.conn.execute(
            "SELECT c.new_terms_json FROM classifications c JOIN items i ON i.id = c.item_id "
            "WHERE i.client_id = ? AND c.is_relevant = 1", (ctx.client_id,)):
        for t in json.loads(terms or "[]"):
            counts[t.strip().lower()] += 1
    return counts.most_common()
#--------------------------------------------------------------#

# Stage entry point (the CLI calls this)
def run(ctx: RunContext) -> None:
    folder = output_dir(ctx.cfg.client)
    folder.mkdir(parents=True, exist_ok=True)

    rows = keyword_rows(ctx)
    with open(folder / "keyword_report.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)

    terms = new_terms(ctx)
    with open(folder / "new_terms.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["term", "times_seen"])
        w.writerows(terms)

    dead = [r["source_query"] for r in rows if r["classified"] and not r["relevant"]]
    log.info("report: %d queries, %d found nothing relevant, %d new terms suggested",
             len(rows), len(dead), len(terms))
    log.info("report: written to %s", folder)
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#