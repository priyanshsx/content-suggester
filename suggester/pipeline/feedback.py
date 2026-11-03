#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
import csv
from suggester.core.db import now_iso, upsert
from suggester.core.log import get_logger
from suggester.pipeline.context import RunContext
#--------------------------------------------------------------#

# Global variables
log = get_logger(__name__)
VERDICTS = {"engaged": "engaged", "e": "engaged", "yes": "engaged", "y": "engaged",
            "skipped": "skipped", "s": "skipped", "no": "skipped", "n": "skipped", "skip": "skipped"}
#--------------------------------------------------------------#

# Approval rate = engaged / reviewed, optionally for one week
def approval_rate(ctx: RunContext, week: str | None = None) -> tuple[int, int]:
    sql = ("SELECT SUM(f.verdict = 'engaged'), COUNT(*) FROM feedback f "
           "JOIN suggestions s ON s.id = f.suggestion_id WHERE f.client_id = ?")
    args = [ctx.client_id]
    if week:
        sql += " AND s.week = ?"
        args.append(week)
    engaged, reviewed = ctx.conn.execute(sql, args).fetchone()
    return engaged or 0, reviewed or 0
#--------------------------------------------------------------#

# Stage entry point (the CLI calls this)
def run(ctx: RunContext) -> None:
    with open(ctx.feedback_file, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    imported = ignored = 0
    weeks = set()
    for row in rows:
        verdict = VERDICTS.get((row.get("status") or "").strip().lower())
        sid = (row.get("suggestion_id") or "").strip()
        if not verdict or not sid.isdigit():
            ignored += 1
            continue
        owned = ctx.conn.execute("SELECT week FROM suggestions WHERE id = ? AND client_id = ?",
                                 (int(sid), ctx.client_id)).fetchone()
        if not owned:
            log.warning("suggestion_id %s is not one of this client's suggestions, ignored", sid)
            ignored += 1
            continue
        upsert(ctx.conn, "feedback", {"client_id": ctx.client_id, "suggestion_id": int(sid),
                                      "verdict": verdict, "note": (row.get("note") or "").strip(),
                                      "created_at": now_iso()},
               conflict_cols=["suggestion_id"], update_cols=["verdict", "note"])
        ctx.conn.execute("UPDATE suggestions SET status = ? WHERE id = ?", (verdict, int(sid)))
        weeks.add(owned["week"])
        imported += 1
    ctx.conn.commit()

    log.info("feedback: %d verdicts imported, %d rows without a valid status ignored",
             imported, ignored)
    for week in sorted(weeks):
        e, r = approval_rate(ctx, week)
        log.info("approval rate %s: %d/%d = %.0f%%", week, e, r, 100 * e / r)
    e_all, r_all = approval_rate(ctx)
    if r_all:
        log.info("approval rate, all time: %d/%d = %.0f%% (target: 70%%+)", e_all, r_all,
                 100 * e_all / r_all)
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#