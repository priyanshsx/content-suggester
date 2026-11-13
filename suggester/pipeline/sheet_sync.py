#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: suggester/pipeline/sheet_sync.py
# Purpose: stage "sync". Two-way sync between the database and the client's Google Sheet.
#          Posts tab:  pull your Status (engaged / skipped) and Note into the feedback table,
#                      then push suggested threads (new rows appended, changed engine cells updated).
#          Hiring tab: push job posts found (one-way for now).
#          Columns are found by header name: reordering or adding your own columns is fine,
#          renaming the engine's headers is not. Your columns are never overwritten.
#--------------------------------------------------------------#

# Imports Libraries
import re
from datetime import date

from gspread.utils import rowcol_to_a1

from suggester.core.log import get_logger
from suggester.core.sheets import open_worksheet
from suggester.pipeline.context import RunContext, iso_week
from suggester.pipeline.export import SNIPPET_CHARS
from suggester.pipeline.feedback import log_approval, record_verdict
#--------------------------------------------------------------#

# Global variables: sheet header -> field in the rows we build
log = get_logger(__name__)
POSTS_ENGINE = {                 # written by the tool; don't edit these in the sheet
    "Post ID": "suggestion_id",
    "Week": "week",
    "Priority": "priority",
    "Rank": "rank",
    "Score": "score",
    "Pillar": "pillar",
    "Platform": "platform",
    "Author": "author",
    "Posted": "posted_at",
    "URL": "url",
    "Snippet": "snippet",
    "Why it matters": "why_it_matters",
    "Comment angle": "comment_angle",
}
POSTS_TEAM = ["Status", "Note", "Last updated"]      # edited by you; the tool only reads these
HIRING_ENGINE = {
    "Item ID": "item_id",
    "Week found": "week",
    "Platform": "platform",
    "Author": "author",
    "Posted": "posted_at",
    "URL": "url",
    "Snippet": "snippet",
    "Who is hiring": "who_is_hiring",
}
HIRING_TEAM = ["Status", "Note"]
REQUESTS_ENGINE = {
    "Request ID": "request_id",
    "Found on": "found_on",
    "Platform": "platform",
    "Poster": "poster",
    "Poster profile": "poster_profile",
    "Company": "company",
    "What they need": "need",
    "Post link": "url",
    "Pillar": "pillar",
    "Region": "region",
}
REQUESTS_TEAM = ["Status", "Note", "Last updated"]     # Status: new, contacted, not relevant
REDDIT_USER = re.compile(r"\bu/([A-Za-z0-9_-]{3,20})\b")
#--------------------------------------------------------------#

# Priority from rank within its week: top third = high, middle third = medium, rest = low
def priority(rank: int, total: int) -> str:
    if rank <= max(1, round(total / 3)):
        return "high"
    return "medium" if rank <= round(2 * total / 3) else "low"
#--------------------------------------------------------------#

# Shorten post text to a one-line snippet
def snippet(text: str | None) -> str:
    text = " ".join((text or "").split())
    return text[:SNIPPET_CHARS] + ("..." if len(text) > SNIPPET_CHARS else "")
#--------------------------------------------------------------#

# All suggested threads for this client, every week, with priority per week
def post_rows(ctx: RunContext) -> list[dict]:
    rows = ctx.conn.execute(
        "SELECT s.id AS suggestion_id, s.week, s.rank, s.score, i.platform, c.pillar, "
        "       COALESCE(i.author_name, i.author_handle, '') AS author, "
        "       COALESCE(i.posted_at, substr(i.first_seen_at, 1, 10)) AS posted_at, i.url, "
        "       i.text, c.reason AS why_it_matters, c.comment_angle "
        "FROM suggestions s JOIN items i ON i.id = s.item_id "
        "JOIN classifications c ON c.item_id = i.id "
        "WHERE s.client_id = ? ORDER BY s.week DESC, s.rank",
        (ctx.client_id,)).fetchall()
    per_week: dict[str, int] = {}
    for r in rows:
        per_week[r["week"]] = per_week.get(r["week"], 0) + 1
    out = []
    for r in rows:
        d = dict(r)
        d["snippet"] = snippet(d.pop("text"))
        d["priority"] = priority(d["rank"], per_week[d["week"]])
        d["score"] = f"{d['score']:.1f}"
        out.append(d)
    return out
#--------------------------------------------------------------#

# All job posts found for this client
def hiring_rows(ctx: RunContext) -> list[dict]:
    rows = ctx.conn.execute(
        "SELECT i.id AS item_id, i.platform, i.first_seen_at, "
        "       COALESCE(i.author_name, i.author_handle, '') AS author, "
        "       COALESCE(i.posted_at, substr(i.first_seen_at, 1, 10)) AS posted_at, i.url, "
        "       i.text, c.reason AS who_is_hiring "
        "FROM items i JOIN classifications c ON c.item_id = i.id "
        "WHERE i.client_id = ? AND c.is_job_post = 1 ORDER BY i.first_seen_at DESC",
        (ctx.client_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["snippet"] = snippet(d.pop("text"))
        d["week"] = iso_week(date.fromisoformat(d.pop("first_seen_at")[:10]))
        out.append(d)
    return out
#--------------------------------------------------------------#

# Read a tab once; add any missing headers at the end of row 1; index rows by their ID column
def read_tab(ws, headers_wanted: list[str], key_header: str):
    values = ws.get_all_values()
    headers = values[0] if values else []
    missing = [h for h in headers_wanted if h not in headers]
    if missing:
        headers = headers + missing
        if len(headers) > ws.col_count:
            ws.add_cols(len(headers) - ws.col_count)
        ws.update(range_name="A1", values=[headers])
    col = {h: i for i, h in enumerate(headers)}

    by_key = {}
    for row_number, row in enumerate(values[1:] if values else [], start=2):
        key = row[col[key_header]].strip() if col[key_header] < len(row) else ""
        if key.isdigit():
            by_key[key] = (row_number, row)
    return headers, col, by_key
#--------------------------------------------------------------#

# One cell's text from a row (blank if the row is shorter than the header)
def cell(row: list[str], col: dict, header: str) -> str:
    i = col[header]
    return row[i].strip() if i < len(row) else ""
#--------------------------------------------------------------#

# Push records into a tab: update changed engine cells, append new rows. Never touches team columns.
def push(ws, headers, col, by_key, records: list[dict], engine: dict, key_header: str) -> tuple[int, int]:
    updates, new_rows = [], []
    for rec in records:
        key = str(rec[engine[key_header]])
        values = {h: "" if rec.get(f) is None else str(rec.get(f)) for h, f in engine.items()}
        if key in by_key:
            row_number, row = by_key[key]
            for header, value in values.items():
                if cell(row, col, header) != value:
                    updates.append({"range": rowcol_to_a1(row_number, col[header] + 1),
                                    "values": [[value]]})
        else:
            row = [""] * len(headers)
            for header, value in values.items():
                row[col[header]] = value
            new_rows.append(row)
    if updates:
        ws.batch_update(updates, value_input_option="RAW")      # RAW: text is never a formula
    if new_rows:
        ws.insert_rows(new_rows, row=2, value_input_option="RAW")      # newest at the top, under the header
    return len(updates), len(new_rows)
#--------------------------------------------------------------#

# Profile link for a request's poster: LinkedIn from the post URL's handle, Reddit when the name is visible
def poster_profile(platform: str, handle: str | None, kind: str | None, text: str | None) -> str:
    if platform == "linkedin" and handle:
        if kind == "person":
            return f"https://www.linkedin.com/in/{handle}"
        if kind == "company":
            return f"https://www.linkedin.com/company/{handle}"
        return ""                                    # can't tell person from company page: use the post link
    if platform == "reddit":
        m = REDDIT_USER.search(text or "")
        return f"https://www.reddit.com/user/{m.group(1)}" if m else ""
    return ""
#--------------------------------------------------------------#

# All requests found for this client
def request_rows(ctx: RunContext) -> list[dict]:
    rows = ctx.conn.execute(
        "SELECT i.id AS request_id, i.platform, i.url, i.author_handle, i.text, "
        "       substr(i.first_seen_at, 1, 10) AS found_on, "
        "       COALESCE(i.author_name, i.author_handle, '') AS poster, "
        "       c.requester_company AS company, c.request_summary AS need, c.pillar, c.region, "
        "       c.poster_kind "
        "FROM items i JOIN classifications c ON c.item_id = i.id "
        "WHERE i.client_id = ? AND c.is_request = 1 ORDER BY i.first_seen_at DESC",
        (ctx.client_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["poster_profile"] = poster_profile(d["platform"], d.pop("author_handle"),
                                             d.pop("poster_kind"), d.pop("text"))
        if d["pillar"] == "none":
            d["pillar"] = ""
        out.append(d)
    return out
#--------------------------------------------------------------#

# Requests tab: pull your Status and Note, then push requests (new rows appended)
def sync_requests(ctx: RunContext) -> None:
    sheets = ctx.cfg.sheets
    if not sheets.spreadsheet_id:
        log.warning("sync: no sheets.spreadsheet_id in %s's config, skipping", ctx.cfg.client)
        return
    ws = open_worksheet(sheets.spreadsheet_id, sheets.requests_tab)
    headers, col, by_key = read_tab(ws, list(REQUESTS_ENGINE) + REQUESTS_TEAM, "Request ID")
    for key, (_, row) in by_key.items():
        ctx.conn.execute(
            "UPDATE classifications SET request_status = ?, request_note = ? WHERE item_id = ?",
            (cell(row, col, "Status").lower() or None, cell(row, col, "Note") or None, int(key)))
    ctx.conn.commit()
    updated, added = push(ws, headers, col, by_key, request_rows(ctx), REQUESTS_ENGINE, "Request ID")
    log.info("sync requests: %d reviewed rows pulled, %d cells updated, %d requests added (tab %r)",
             len(by_key), updated, added, sheets.requests_tab)
#--------------------------------------------------------------#

# Stage entry point (the CLI calls this)
def run(ctx: RunContext) -> None:
    sheets = ctx.cfg.sheets
    if not sheets.spreadsheet_id:
        log.warning("sync: no sheets.spreadsheet_id in %s's config, skipping", ctx.cfg.client)
        return
    if ctx.dry_run:
        log.info("sync: dry run, not reading or writing the sheet")
        return

    # Posts: pull your verdicts first, then push threads
    ws = open_worksheet(sheets.spreadsheet_id, sheets.posts_tab)
    headers, col, by_key = read_tab(ws, list(POSTS_ENGINE) + POSTS_TEAM, "Post ID")
    weeks, pulled = set(), 0
    for key, (_, row) in by_key.items():
        week = record_verdict(ctx, key, cell(row, col, "Status"), cell(row, col, "Note"))
        if week:
            weeks.add(week)
            pulled += 1
    ctx.conn.commit()
    updated, added = push(ws, headers, col, by_key, post_rows(ctx), POSTS_ENGINE, "Post ID")
    log.info("sync posts: %d verdicts pulled, %d cells updated, %d threads added (tab %r)",
             pulled, updated, added, sheets.posts_tab)
    log_approval(ctx, weeks)

    # Hiring tab: only if a client still sets one (job posts now go to the Leads tab via job-alerts)
    if sheets.hiring_tab:
        ws = open_worksheet(sheets.spreadsheet_id, sheets.hiring_tab)
        headers, col, by_key = read_tab(ws, list(HIRING_ENGINE) + HIRING_TEAM, "Item ID")
        updated, added = push(ws, headers, col, by_key, hiring_rows(ctx), HIRING_ENGINE, "Item ID")
        log.info("sync hiring: %d cells updated, %d job posts added (tab %r)",
                 updated, added, sheets.hiring_tab)

    # Requests: only for clients with request phrases in their config
    if ctx.cfg.requests.keywords:
        sync_requests(ctx)
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#
