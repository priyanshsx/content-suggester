#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
import json
from datetime import date, timedelta

from suggester.core.db import now_iso, upsert
from suggester.core.log import get_logger
from suggester.core.schemas import SourceItem
from suggester.pipeline.context import RunContext
from suggester.pipeline.queries import build_queries
from suggester.sources import make_source
#--------------------------------------------------------------#

# Global variables
log = get_logger(__name__)
UPDATE_ON_RERUN = ["text", "author_name", "posted_at", "engagement_json", "raw_json",
                   "last_seen_at"]                     # first_seen_at is kept
#--------------------------------------------------------------#

# Save one item; returns True if it was new
def store_item(ctx: RunContext, item: SourceItem) -> bool:
    exists = ctx.conn.execute("SELECT 1 FROM items WHERE client_id = ? AND url = ?",
                              (ctx.client_id, item.url)).fetchone()
    now = now_iso()
    upsert(ctx.conn, "items", {
        "client_id": ctx.client_id,
        "platform": item.platform,
        "source": item.source,
        "url": item.url,
        "external_id": item.external_id,
        "author_handle": item.author_handle,
        "author_name": item.author_name,
        "text": item.text,
        "posted_at": item.posted_at,
        "engagement_json": json.dumps(item.engagement, ensure_ascii=False),
        "source_query": item.source_query,
        "raw_json": json.dumps(item.raw, ensure_ascii=False),
        "first_seen_at": now,
        "last_seen_at": now,
    }, conflict_cols=["client_id", "url"], update_cols=UPDATE_ON_RERUN)
    return exists is None
#--------------------------------------------------------------#

# Stage entry point (the CLI calls this)
def run(ctx: RunContext) -> None:
    since = date.today() - timedelta(days=ctx.cfg.lookback_days)
    for name in ctx.cfg.sources:
        source = make_source(name, ctx.cfg.client)
        queries = build_queries(ctx.cfg, name)
        if source.uses_queries and not queries:
            log.warning("%s: no query template in config, skipped", name)
            continue
        if ctx.dry_run and source.uses_queries:
            log.info("%s (dry run): would run %d queries", name, len(queries))
            for q in queries:
                log.info("   %s", q.text)
            continue

        try:
            items = source.fetch(queries, since)
        except Exception as e:                         # one broken source must not stop the rest
            log.error("%s failed: %s", name, e)
            continue

        new = sum(store_item(ctx, it) for it in items)
        log.info("%s: %d items found, %d new, %d already known",
                 name, len(items), new, len(items) - new)
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#