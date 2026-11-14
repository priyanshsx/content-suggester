#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: suggester/pipeline/themes.py
# Purpose: stage "themes". Turns the posts we already collect into content ideas:
#   1. pull the client's picks (status, note, published URL) from the Content Ideas tab
#   2. take relevant posts from the last window_days, grouped by expertise area (= pillar)
#   3. one LLM call per area finds recurring themes (prompts/theme_extract.md)
#   4. code enforces the rules: evidence from real posts, at least min_posts posts from
#      min_sources authors/communities, no near-duplicates of earlier themes, and at most
#      max_themes_per_area per area per week (a second run in the same week only fills free slots)
#   5. store themes + evidence in the database, push them to the Content Ideas tab
# Only runs for clients with themes.enabled: true. Never drafts posts and never posts anything.
# Usage:  python -m suggester --client quartermaster --stage themes   (once a week)
#--------------------------------------------------------------#

# Imports Libraries
import re
from datetime import date, timedelta

from suggester.core.db import now_iso
from suggester.core.llm import LLMError, call_llm
from suggester.core.log import get_logger
from suggester.core.prompts import prompt_version, render_prompt
from suggester.core.schemas import ThemeBatch
from suggester.pipeline.context import RunContext
#--------------------------------------------------------------#

# Global variables
log = get_logger(__name__)
PROMPT = "theme_extract"
POST_CHARS = 400                  # text shown to the LLM per post
DUPLICATE_OVERLAP = 0.6           # share of shared key words that makes two themes "the same"
STATUSES = {"new", "picked", "rejected", "published"}
STOPWORDS = set("""a an the and or but if then than of to in on at for from by with without into
about over under after before is are was were be been being do does did have has had it its this
that these those they them their there here what which who whom how why when where not no yes
you your we our us i me my he she his her so too very can could should would will just more most
less least much many some any all each every only also as up down out off""".split())

IDEAS_ENGINE = {                  # written by the tool; don't edit these in the sheet
    "theme_id": "theme_id",
    "run_date": "run_date",
    "expertise": "pillar",
    "expertise_rank": "pillar_rank",
    "theme": "theme",
    "angle": "angle",
    "what_to_measure": "research_cue",
    "post_count": "post_count",
    "source_count": "source_count",
    "evidence_urls": "evidence_urls",
}
IDEAS_TEAM = ["status", "client_note", "published_url"]     # edited by the client
#--------------------------------------------------------------#

# Key words of a sentence, for comparing themes
def key_words(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+(?:[/'-][a-z0-9]+)*", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


# True if two themes say mostly the same thing (overlap of key words, relative to the shorter one)
def is_duplicate(a: str, b: str) -> bool:
    wa, wb = key_words(a), key_words(b)
    if not wa or not wb:
        return False
    return len(wa & wb) / min(len(wa), len(wb)) >= DUPLICATE_OVERLAP
#--------------------------------------------------------------#

# Who a post is from, for the "different authors or communities" rule (Reddit: the subreddit)
def source_key(item: dict) -> str:
    return (item.get("author_name") or item.get("author_handle") or item["url"]).strip().lower()
#--------------------------------------------------------------#

# Relevant posts from the window, grouped by pillar; also returns how many landed in "other"
def posts_by_area(ctx: RunContext, today: date) -> tuple[dict[str, list[dict]], int, int]:
    since = (today - timedelta(days=ctx.cfg.themes.window_days)).isoformat()
    rows = ctx.conn.execute(
        "SELECT i.id, i.platform, i.url, i.author_name, i.author_handle, i.text, "
        "       COALESCE(i.posted_at, substr(i.first_seen_at, 1, 10)) AS day, "
        "       c.pillar, c.score "
        "FROM items i JOIN classifications c ON c.item_id = i.id "
        "WHERE i.client_id = ? AND c.is_relevant = 1 AND COALESCE(c.is_job_post, 0) = 0 "
        "  AND COALESCE(i.posted_at, substr(i.first_seen_at, 1, 10)) >= ? "
        "ORDER BY COALESCE(c.score, 0) DESC, day DESC",
        (ctx.client_id, since)).fetchall()
    groups: dict[str, list[dict]] = {}
    other = 0
    for r in rows:
        if not r["pillar"] or r["pillar"] == "none":
            other += 1
            continue
        groups.setdefault(r["pillar"], []).append(dict(r))
    return groups, other, len(rows)
#--------------------------------------------------------------#

# All themes already stored for this client (for the prompt and the duplicate check)
def existing_themes(ctx: RunContext) -> list[str]:
    return [r[0] for r in ctx.conn.execute(
        "SELECT theme FROM themes WHERE client_id = ? ORDER BY id", (ctx.client_id,))]
#--------------------------------------------------------------#

# Build the prompt for one area; posts are numbered 1..N so the LLM can cite them
def build_prompt(ctx: RunContext, pillar, posts: list[dict], existing: list[str]) -> str:
    cfg, t = ctx.cfg, ctx.cfg.themes
    lines = []
    for n, p in enumerate(posts, start=1):
        text = " ".join((p["text"] or "").split())[:POST_CHARS]
        who = p["author_name"] or p["author_handle"] or "unknown"
        lines.append(f"[{n}] {p['platform']} | {who} | {text}")
    cue_rule = (f"one line: {t.research_cue.strip()}" if t.research_cue
                else "leave empty.")
    return render_prompt(
        PROMPT,
        display_name=cfg.display_name, offer=cfg.offer.strip(), positioning=cfg.positioning.strip(),
        audience=cfg.audience.strip(), window_days=t.window_days,
        pillar_name=pillar.name, pillar_description=pillar.description,
        min_posts=t.min_posts, min_sources=t.min_sources, max_themes=t.max_themes_per_area,
        compliance_rules="\n".join(f"  - {r}" for r in cfg.compliance.rules) or "  - none",
        research_cue_rule=cue_rule,
        existing_themes="\n".join(f"- {e}" for e in existing[-40:]) or "- none yet",
        posts="\n".join(lines),
    )
#--------------------------------------------------------------#

# Check one area's LLM answer against the rules; returns the themes that pass, with their posts
def accept_themes(ctx: RunContext, batch: ThemeBatch, posts: list[dict],
                  existing: list[str], slots: int) -> list[dict]:
    t = ctx.cfg.themes
    kept = []
    if slots <= 0:
        return kept
    for draft in batch.themes:
        numbers = [n for n in dict.fromkeys(draft.evidence) if 1 <= n <= len(posts)]  # real, unique
        evidence = [posts[n - 1] for n in numbers]
        sources = {source_key(p) for p in evidence}
        if len(evidence) < t.min_posts or len(sources) < t.min_sources:
            log.info("   dropped (evidence %d posts / %d sources): %s",
                     len(evidence), len(sources), draft.theme)
            continue
        if any(is_duplicate(draft.theme, e) for e in existing + [k["theme"] for k in kept]):
            log.info("   dropped (repeat of an earlier theme): %s", draft.theme)
            continue
        kept.append({"theme": draft.theme.strip(), "angle": draft.angle.strip(),
                     "research_cue": draft.research_cue.strip() if t.research_cue else "",
                     "evidence": evidence, "source_count": len(sources)})
        if len(kept) == slots:
            break
    return kept
#--------------------------------------------------------------#

# Free theme slots for an area this week (max_themes_per_area minus themes already found)
def free_slots(ctx: RunContext, pillar_name: str) -> int:
    found = ctx.conn.execute("SELECT COUNT(*) FROM themes WHERE client_id = ? AND week = ? "
                             "AND pillar = ?", (ctx.client_id, ctx.week, pillar_name)).fetchone()[0]
    return ctx.cfg.themes.max_themes_per_area - found
#--------------------------------------------------------------#

# Next free theme ID for this week, e.g. quartermaster-2026w46-03
def next_theme_id(ctx: RunContext) -> str:
    prefix = f"{ctx.cfg.client}-{ctx.week.lower().replace('-', '')}-"
    count = ctx.conn.execute("SELECT COUNT(*) FROM themes WHERE theme_id LIKE ?",
                             (prefix + "%",)).fetchone()[0]
    return f"{prefix}{count + 1:02d}"
#--------------------------------------------------------------#

# Save one accepted theme and its evidence
def store_theme(ctx: RunContext, pillar, theme: dict, today: date, version: str) -> str:
    theme_id = next_theme_id(ctx)
    cur = ctx.conn.execute(
        "INSERT INTO themes (client_id, theme_id, run_date, week, pillar, pillar_rank, theme, angle, "
        "research_cue, post_count, source_count, status, prompt_version, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)",
        (ctx.client_id, theme_id, today.isoformat(), ctx.week, pillar.name, pillar.rank,
         theme["theme"], theme["angle"], theme["research_cue"] or None, len(theme["evidence"]),
         theme["source_count"], version, now_iso()))
    ctx.conn.executemany("INSERT INTO theme_items (theme_pk, item_id) VALUES (?, ?)",
                         [(cur.lastrowid, p["id"]) for p in theme["evidence"]])
    ctx.conn.commit()
    return theme_id
#--------------------------------------------------------------#

# All themes for this client, as rows for the Content Ideas tab
def idea_rows(ctx: RunContext) -> list[dict]:
    rows = ctx.conn.execute(
        "SELECT t.*, (SELECT GROUP_CONCAT(i.url, char(10)) FROM theme_items ti "
        "             JOIN items i ON i.id = ti.item_id WHERE ti.theme_pk = t.id) AS evidence_urls "
        "FROM themes t WHERE t.client_id = ? ORDER BY t.id DESC", (ctx.client_id,)).fetchall()
    return [dict(r) for r in rows]
#--------------------------------------------------------------#

# Pull the client's status / note / published URL from the sheet into the database
def pull_picks(ctx: RunContext, by_key: dict, col: dict) -> int:
    from suggester.pipeline.sheet_sync import cell
    changed = 0
    for theme_id, (_, row) in by_key.items():
        status = cell(row, col, "status").lower() or "new"
        if status not in STATUSES:
            log.warning("themes: %s has status %r; use new, picked, rejected or published",
                        theme_id, status)
            continue
        cur = ctx.conn.execute(
            "UPDATE themes SET status = ?, client_note = ?, published_url = ?, updated_at = ? "
            "WHERE theme_id = ? AND client_id = ? AND (status IS NOT ? OR client_note IS NOT ? "
            "      OR published_url IS NOT ?)",
            (status, cell(row, col, "client_note") or None, cell(row, col, "published_url") or None,
             now_iso(), theme_id, ctx.client_id, status, cell(row, col, "client_note") or None,
             cell(row, col, "published_url") or None))
        changed += cur.rowcount
    ctx.conn.commit()
    return changed
#--------------------------------------------------------------#

# Pick rate per area: picked or published / everything the client has reviewed
def log_pick_rate(ctx: RunContext) -> None:
    rows = ctx.conn.execute(
        "SELECT pillar, SUM(status IN ('picked', 'published')) AS picked, "
        "       SUM(status IN ('picked', 'published', 'rejected')) AS reviewed, COUNT(*) AS shown "
        "FROM themes WHERE client_id = ? GROUP BY pillar ORDER BY MIN(pillar_rank)",
        (ctx.client_id,)).fetchall()
    for r in rows:
        rate = f"{100 * r['picked'] / r['reviewed']:.0f}%" if r["reviewed"] else "not reviewed yet"
        log.info("   pick rate %-24s %s (%d of %d reviewed, %d shown)",
                 r["pillar"], rate, r["picked"], r["reviewed"], r["shown"])
#--------------------------------------------------------------#

# Stage entry point (the CLI calls this)
def run(ctx: RunContext, today: date | None = None) -> None:
    t = ctx.cfg.themes
    if not t.enabled:
        log.info("themes: not enabled for %s (set themes.enabled: true in its config)", ctx.cfg.client)
        return
    today = today or date.today()
    sheets = ctx.cfg.sheets
    use_sheet = bool(sheets.spreadsheet_id) and not ctx.dry_run

    # 1. Pull the client's picks first, so the duplicate check and pick rate are current
    ws = None
    if use_sheet:
        from suggester.core.sheets import open_worksheet
        from suggester.pipeline.sheet_sync import read_tab
        ws = open_worksheet(sheets.spreadsheet_id, sheets.ideas_tab)
        headers, col, by_key = read_tab(ws, list(IDEAS_ENGINE) + IDEAS_TEAM, "theme_id",
                                        numeric_keys=False)
        log.info("themes: %d picks / notes updated from the sheet", pull_picks(ctx, by_key, col))

    # 2. Posts by expertise area
    groups, other, total = posts_by_area(ctx, today)
    log.info("themes: %d relevant posts in the last %d days, %d (%.0f%%) fit no area ('other')",
             total, t.window_days, other, 100 * other / total if total else 0)

    # 3-4. One LLM call per area, strongest area first
    existing = existing_themes(ctx)
    version = prompt_version(PROMPT)
    pillars = sorted(ctx.cfg.pillars, key=lambda p: (p.rank or 99, p.name))
    added = []
    for pillar in pillars:
        posts = groups.get(pillar.name, [])[:t.max_posts_per_area]
        if len(posts) < t.min_posts:
            log.info("themes: %-24s %3d posts, too few for a theme this run", pillar.name, len(posts))
            continue
        slots = free_slots(ctx, pillar.name)
        if slots <= 0:
            log.info("themes: %-24s already has %d themes this week", pillar.name,
                     t.max_themes_per_area)
            continue
        if ctx.dry_run:
            log.info("themes: %-24s %3d posts, would ask the LLM (dry run)", pillar.name, len(posts))
            continue
        try:
            batch = call_llm("theme_extract", build_prompt(ctx, pillar, posts, existing),
                             ThemeBatch, ctx.conn, ctx.client_id, max_tokens=2500)
        except LLMError as e:                       # one area failing must not stop the others
            log.error("themes: %s failed: %s", pillar.name, e)
            continue
        kept = accept_themes(ctx, batch, posts, existing, slots)
        for theme in kept:
            added.append(store_theme(ctx, pillar, theme, today, version))
            existing.append(theme["theme"])
        log.info("themes: %-24s %3d posts, %d suggested, %d kept",
                 pillar.name, len(posts), len(batch.themes), len(kept))
    log.info("themes: %d new themes this run: %s", len(added), ", ".join(added) or "none")

    # 5. Push to the Content Ideas tab (new rows get status "new")
    if ws is not None:
        from suggester.pipeline.sheet_sync import push
        updated, new_rows = push(ws, headers, col, by_key, idea_rows(ctx), IDEAS_ENGINE, "theme_id",
                                 new_row_defaults={"status": "new"})
        log.info("themes: sheet %r, %d cells updated, %d themes added", sheets.ideas_tab,
                 updated, new_rows)
    log_pick_rate(ctx)
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#
