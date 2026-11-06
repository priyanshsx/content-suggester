#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
from datetime import date

from suggester.core.db import now_iso
from suggester.core.log import get_logger
from suggester.pipeline.context import RunContext
from suggester.pipeline.score import age_days, candidates
#--------------------------------------------------------------#

# Global variables
log = get_logger(__name__)
#--------------------------------------------------------------#

# Author key: name if known, else handle, else the URL (unknown authors don't block each other)
def author_key(item: dict) -> str:
    return (item.get("author_name") or item.get("author_handle") or item["url"]).strip().lower()
#--------------------------------------------------------------#

# Greedy pick with diversity limits
def pick(items: list[dict], n: int, max_per_author: int, max_per_pillar: int,
         max_per_subreddit: int | None = None) -> list[dict]:
    chosen, per_author, per_pillar = [], {}, {}
    for it in sorted(items, key=lambda x: x["score"], reverse=True):
        a, p = author_key(it), it["pillar"]
        # On Reddit the "author" is the subreddit, so it gets its own limit
        cap = (max_per_subreddit or max_per_author) if it.get("platform") == "reddit" \
            else max_per_author
        if per_author.get(a, 0) >= cap or per_pillar.get(p, 0) >= max_per_pillar:
            continue
        chosen.append(it)
        per_author[a] = per_author.get(a, 0) + 1
        per_pillar[p] = per_pillar.get(p, 0) + 1
        if len(chosen) == n:
            break
    return chosen
#--------------------------------------------------------------#

# Stage entry point (the CLI calls this)
def run(ctx: RunContext, today: date | None = None) -> None:
    today = today or date.today()
    # Clear this week's unreviewed picks so a rerun starts fresh
    ctx.conn.execute(
        "DELETE FROM suggestions WHERE client_id = ? AND week = ? AND status = 'suggested' "
        "AND id NOT IN (SELECT suggestion_id FROM feedback)", (ctx.client_id, ctx.week))
    kept = {r[0] for r in ctx.conn.execute(
        "SELECT item_id FROM suggestions WHERE client_id = ? AND week = ?",
        (ctx.client_id, ctx.week))}

    scored = []
    for it in candidates(ctx):
        if it["id"] in kept or age_days(it, today) > ctx.cfg.lookback_days:
            continue
        row = ctx.conn.execute("SELECT score FROM classifications WHERE id = ?",
                               (it["classification_id"],)).fetchone()
        if row["score"] is not None:
            scored.append({**it, "score": row["score"]})

    slots = max(ctx.cfg.threads_per_week - len(kept), 0)
    chosen = pick(scored, slots, ctx.cfg.max_per_author, ctx.cfg.max_per_pillar,
                  ctx.cfg.max_per_subreddit)
    for rank, it in enumerate(chosen, start=len(kept) + 1):
        ctx.conn.execute(
            "INSERT INTO suggestions (client_id, item_id, week, score, rank, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'suggested', ?)",
            (ctx.client_id, it["id"], ctx.week, it["score"], rank, now_iso()))
    ctx.conn.commit()

    total = len(kept) + len(chosen)
    log.info("select: %d threads picked for %s (from %d candidates)", total, ctx.week, len(scored))
    if total < ctx.cfg.threads_per_week:
        log.warning("select: only %d of %d wanted. Add keywords/sources or paste posts manually.",
                    total, ctx.cfg.threads_per_week)
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#