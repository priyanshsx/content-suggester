#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: suggester/pipeline/request_finder.py
# Purpose: stage "requests". Find posts where someone asks for help the client offers, and put
#          them in the Requests tab. Runs on its own (e.g. Monday and Thursday), separately from
#          the weekly threads:
#            1. search only the client's request phrases (requests.keywords, requests.sources)
#            2. classify new posts (the classifier flags requests with is_request)
#            3. sync the Requests tab
#          --dry-run: show the searches it would run, nothing else.
#--------------------------------------------------------------#

# Imports Libraries
from datetime import date, timedelta

from suggester.core.log import get_logger
from suggester.pipeline import classify, sheet_sync
from suggester.pipeline.collect import store_item
from suggester.pipeline.context import RunContext
from suggester.pipeline.queries import build_request_queries
from suggester.sources import make_source
#--------------------------------------------------------------#

# Global variables
log = get_logger(__name__)
#--------------------------------------------------------------#

# Stage entry point (the CLI calls this)
def run(ctx: RunContext) -> None:
    req = ctx.cfg.requests
    if not req.keywords or not req.sources:
        log.warning("requests: no requests.keywords or requests.sources in %s's config, skipping",
                    ctx.cfg.client)
        return

    # 1. Collect: request phrases only
    since = date.today() - timedelta(days=req.lookback_days)
    total_searches = 0
    for name in req.sources:
        queries = build_request_queries(ctx.cfg, name)
        total_searches += len(queries)
        if ctx.dry_run:
            log.info("requests %s (dry run): would run %d searches", name, len(queries))
            for q in queries:
                log.info("   %s", q.text)
            continue
        try:
            items = make_source(name, ctx.cfg.client).fetch(queries, since)
        except Exception as e:                       # one broken source must not stop the rest
            log.error("requests %s failed: %s", name, e)
            continue
        new = sum(store_item(ctx, it) for it in items)
        log.info("requests %s: %d searches, %d posts found, %d new", name, len(queries), len(items), new)
    if ctx.dry_run:
        log.info("requests (dry run): %d paid searches in total", total_searches)
        return

    # 2. Classify new posts (requests get is_request = 1)
    classify.run(ctx)

    # 3. Requests tab
    found = ctx.conn.execute(
        "SELECT COUNT(*) FROM items i JOIN classifications c ON c.item_id = i.id "
        "WHERE i.client_id = ? AND c.is_request = 1 AND i.first_seen_at >= date('now', ?)",
        (ctx.client_id, f"-{req.lookback_days} days")).fetchone()[0]
    log.info("requests: %d requests found in the last %d days", found, req.lookback_days)
    sheet_sync.sync_requests(ctx)
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#
