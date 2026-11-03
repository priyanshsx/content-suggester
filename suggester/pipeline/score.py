#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: suggester/pipeline/score.py
# Purpose: stage 3. Give every candidate thread a score using the weights in the config:
#   relevant          fixed points (only relevant items are candidates)
#   pain_or_question  points if the author has a problem or question
#   region_match      points if the region is one of the client's regions
#   recency           points x 0.5^(age_days / half_life)   -> newer = more points
#   engagement        points x percentile of comment count within the same platform
#   author type       buyer / peer / vendor / other points
# Candidates: relevant, not a job post, not suggested before, posted within lookback_days.
#--------------------------------------------------------------#

# Imports Libraries
import json
import re
from datetime import date

from suggester.core.log import get_logger
from suggester.pipeline.context import RunContext
#--------------------------------------------------------------#

# Global variables
log = get_logger(__name__)
COMMENTS = re.compile(r"(\d[\d,.]*)\s+(comments?|Kommentare?)", re.IGNORECASE)
#--------------------------------------------------------------#

# How many comments Google showed for the post (None if unknown)
def comment_count(item: dict) -> int | None:
    eng = json.loads(item.get("engagement_json") or "{}")
    if "comments" in eng:
        return int(eng["comments"])
    raw = json.loads(item.get("raw_json") or "{}")
    m = COMMENTS.search(f"{raw.get('title', '')} {raw.get('snippet', '')}")
    return int(re.sub(r"[,.]", "", m.group(1))) if m else None
#--------------------------------------------------------------#

# Age in days, using the post date or (if unknown) the day we first saw it
def age_days(item: dict, today: date) -> int:
    when = item.get("posted_at") or (item.get("first_seen_at") or "")[:10]
    try:
        return max((today - date.fromisoformat(when)).days, 0)
    except ValueError:
        return 0
#--------------------------------------------------------------#

# Percentile (0..1) of each value among the values of its platform; unknown = 0.5 (neutral)
def engagement_percentiles(items: list[dict]) -> dict[int, float]:
    by_platform: dict[str, list[int]] = {}
    for it in items:
        c = comment_count(it)
        if c is not None:
            by_platform.setdefault(it["platform"], []).append(c)
    result = {}
    for it in items:
        c, values = comment_count(it), by_platform.get(it["platform"], [])
        if c is None or len(values) < 2:
            result[it["id"]] = 0.5
        else:
            result[it["id"]] = sum(v <= c for v in values) / len(values)
    return result
#--------------------------------------------------------------#

# Candidates: relevant, not a job post, never suggested before
def candidates(ctx: RunContext) -> list[dict]:
    rows = ctx.conn.execute(
        "SELECT i.*, c.id AS classification_id, c.pillar, c.author_type, c.region, "
        "       c.has_pain_or_question "
        "FROM items i JOIN classifications c ON c.item_id = i.id "
        "LEFT JOIN suggestions s ON s.item_id = i.id AND s.client_id = i.client_id "
        "     AND s.week != ? "
        "WHERE i.client_id = ? AND c.is_relevant = 1 AND c.is_job_post = 0 "
        "  AND s.id IS NULL",
        (ctx.week, ctx.client_id)).fetchall()
    return [dict(r) for r in rows]
#--------------------------------------------------------------#

# Score one item; returns (total, breakdown)
def score_item(ctx: RunContext, item: dict, engagement_pct: float, today: date) -> tuple[float, dict]:
    s = ctx.cfg.scoring
    p = s.points
    parts = {
        "relevant": p.get("relevant", 0),
        "pain_or_question": p.get("pain_or_question", 0) * bool(item["has_pain_or_question"]),
        "region_match": p.get("region_match", 0) * (item["region"] in ctx.cfg.regions),
        "recency": p.get("recency", 0) * 0.5 ** (age_days(item, today) / s.recency_half_life_days),
        "engagement": p.get("engagement", 0) * engagement_pct,
        "author_type": s.author_type_points.get(item["author_type"], 0),
    }
    parts = {k: round(v, 1) for k, v in parts.items()}
    return round(sum(parts.values()), 1), parts
#--------------------------------------------------------------#

# Stage entry point (the CLI calls this)
def run(ctx: RunContext, today: date | None = None) -> None:
    today = today or date.today()
    items = [it for it in candidates(ctx) if age_days(it, today) <= ctx.cfg.lookback_days]
    pct = engagement_percentiles(items)
    for it in items:
        total, parts = score_item(ctx, it, pct[it["id"]], today)
        ctx.conn.execute("UPDATE classifications SET score = ?, score_json = ? WHERE id = ?",
                         (total, json.dumps(parts), it["classification_id"]))
    ctx.conn.commit()
    log.info("score: %d candidate threads scored", len(items))
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#
