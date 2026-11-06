#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
import argparse
import sys

from suggester.core.config import load_config
from suggester.core.db import connect, get_client_id, init_db
from suggester.core.llm import LLMError
from suggester.core.log import get_logger
from suggester.pipeline import (classify, collect, export, feedback, report, request_finder,
                                score, select, sheet_sync)
from suggester.pipeline.context import RunContext, iso_week
#--------------------------------------------------------------#

# Global variables: stage name -> function, and the order "all" runs them in
log = get_logger("suggester")

STAGES = {
    "collect": collect.run,
    "classify": classify.run,
    "score": score.run,
    "select": select.run,
    "export": export.run,
    "sync": sheet_sync.run,
    "requests": request_finder.run,
    "import-feedback": feedback.run,
    "report": report.run,
}
ALL_ORDER = ["collect", "classify", "score", "select", "sync"]   # export (CSV), feedback, report: run separately
#--------------------------------------------------------------#

# Read the command-line arguments
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="suggester", description="Weekly conversation-thread suggester")
    p.add_argument("--client", required=True, help="client folder name, e.g. vizcorn")
    p.add_argument("--stage", default="all", choices=[*STAGES, "all"])
    p.add_argument("--week", default=None, help="ISO week like 2026-W45 (default: this week)")
    p.add_argument("--dry-run", action="store_true", help="don't call paid APIs")
    p.add_argument("--file", default=None, help="CSV for --stage import-feedback")
    return p.parse_args(argv)
#--------------------------------------------------------------#

# Main: build the context once, then run the requested stage(s)
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.stage == "import-feedback" and not args.file:
        log.error("--stage import-feedback needs --file <path to reviewed CSV>")
        return 2

    try:
        cfg = load_config(args.client)
    except Exception as e:                           # missing folder, bad YAML, validation error
        log.error("Config problem for %r:\n%s", args.client, e)
        return 1

    conn = connect()
    try:
        init_db(conn)
        try:
            client_id = get_client_id(conn, args.client)
        except ValueError as e:
            log.error(str(e))
            return 1

        ctx = RunContext(cfg=cfg, conn=conn, client_id=client_id,
                         week=args.week or iso_week(), dry_run=args.dry_run,
                         feedback_file=args.file)
        stages = ALL_ORDER if args.stage == "all" else [args.stage]
        log.info("client=%s week=%s stages=%s%s", cfg.client, ctx.week, ",".join(stages),
                 " (dry run)" if ctx.dry_run else "")
        for name in stages:
            log.info("--- %s ---", name)
            try:
                STAGES[name](ctx)
            except (LLMError, FileNotFoundError) as e:   # setup problems: show one clear line
                log.error("%s stopped: %s", name, e)
                return 1
        log.info("done")
        return 0
    finally:
        conn.close()
#--------------------------------------------------------------#

if __name__ == "__main__":
    sys.exit(main())
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#