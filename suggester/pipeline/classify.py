#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: suggester/pipeline/classify.py
# Purpose: stage 2. Ask the LLM to judge every item that has no verdict yet, and store the
#          verdict in the classifications table. Items are never classified twice unless you
#          delete their classification (e.g. after improving the prompt).
#          --dry-run: only count what would be classified.
#--------------------------------------------------------------#

# Imports Libraries
import json

from suggester.core.config import Config
from suggester.core.db import now_iso, upsert
from suggester.core.llm import LLMError, _settings, call_llm
from suggester.core.log import get_logger
from suggester.core.prompts import prompt_version, render_prompt
from suggester.core.schemas import ThreadClassification
from suggester.pipeline.context import RunContext
#--------------------------------------------------------------#

# Global variables
log = get_logger(__name__)
PROMPT = "thread_classify"
MIN_TEXT_CHARS = 20                       # shorter than this = nothing to judge, no LLM call
#--------------------------------------------------------------#

# Build the prompt for one item (also used by the eval script)
def build_prompt(cfg: Config, item: dict) -> str:
    return render_prompt(
        PROMPT,
        display_name=cfg.display_name,
        offer=cfg.offer,
        positioning=cfg.positioning,
        regions=", ".join(cfg.regions) or "any",
        pillars="\n".join(f"- {p.name}: {p.description}" for p in cfg.pillars),
        engagement_goal=cfg.engagement_goal.strip(),
        audience=cfg.audience.strip(),
        compliance_rules="\n".join(f"- {r}" for r in cfg.compliance.rules) or "- none",
        platform=item.get("platform") or "unknown",
        author=item.get("author_name") or "unknown",
        posted_at=item.get("posted_at") or "unknown",
        url=item.get("url") or "",
        text=(item.get("text") or "").strip(),
        request_definition=(cfg.requests.what_counts.strip()
                            or f"help with what {cfg.display_name} offers (see Offer above)"),
    )
#--------------------------------------------------------------#

# Classify one item; returns the verdict (also used by the eval script)
def classify_one(cfg: Config, conn, client_id: int, item: dict) -> ThreadClassification:
    if len((item.get("text") or "").strip()) < MIN_TEXT_CHARS:
        return ThreadClassification(reason="No text to judge.", is_relevant=False, pillar="none",
                                    author_type="other", has_pain_or_question=False,
                                    region="unknown", comment_angle="")
    verdict = call_llm("thread_classify", build_prompt(cfg, item), ThreadClassification,
                       conn, client_id)
    # Keep the pillar honest: anything not in the config becomes "none"
    if verdict.pillar not in {p.name for p in cfg.pillars}:
        verdict.pillar = "none"
    if not verdict.is_relevant:
        verdict.comment_angle = ""
    if not verdict.is_request:
        verdict.request_summary = ""
    return verdict
#--------------------------------------------------------------#

# Items of this client that have no classification yet (newest first)
def unclassified(ctx: RunContext) -> list[dict]:
    rows = ctx.conn.execute(
        "SELECT i.* FROM items i LEFT JOIN classifications c ON c.item_id = i.id "
        "WHERE i.client_id = ? AND c.id IS NULL "
        "ORDER BY COALESCE(i.posted_at, i.first_seen_at) DESC LIMIT ?",
        (ctx.client_id, ctx.cfg.max_items_per_run)).fetchall()
    return [dict(r) for r in rows]
#--------------------------------------------------------------#

# Stage entry point (the CLI calls this)
def run(ctx: RunContext) -> None:
    items = unclassified(ctx)
    if not items:
        log.info("classify: nothing new to classify")
        return
    if ctx.dry_run:
        log.info("classify (dry run): %d items would be classified", len(items))
        return

    model = _settings()[0]
    version = prompt_version(PROMPT)
    done = relevant = jobs = requests = failed = 0
    for item in items:
        try:
            v = classify_one(ctx.cfg, ctx.conn, ctx.client_id, item)
        except LLMError as e:                      # one bad item must not stop the run
            log.error("item %s: %s", item["id"], e)
            failed += 1
            continue
        upsert(ctx.conn, "classifications", {
            "item_id": item["id"],
            "is_relevant": int(v.is_relevant),
            "pillar": v.pillar,
            "author_type": v.author_type,
            "has_pain_or_question": int(v.has_pain_or_question),
            "region": v.region,
            "comment_angle": v.comment_angle,
            "reason": v.reason,
            "new_terms_json": json.dumps(v.new_terms, ensure_ascii=False),
            "is_job_post": int(v.is_job_post),
            "is_request": int(v.is_request),
            "hiring_company": v.hiring_company if v.is_job_post else "",
            "request_summary": v.request_summary,
            "requester_company": v.requester_company,
            "poster_kind": v.poster_kind,
            "model": model,
            "prompt_version": version,
            "created_at": now_iso(),
        }, conflict_cols=["item_id"])
        done += 1
        relevant += v.is_relevant
        jobs += v.is_job_post
        requests += v.is_request
    log.info("classify: %d classified, %d relevant, %d job posts, %d requests, %d failed",
             done, relevant, jobs, requests, failed)
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#
