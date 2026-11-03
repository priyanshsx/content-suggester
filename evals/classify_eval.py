#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
import argparse
import csv
import sys

from suggester.core.config import load_config
from suggester.core.db import connect, get_client_id, init_db
from suggester.core.paths import CLIENTS_DIR
from suggester.pipeline.classify import classify_one
#--------------------------------------------------------------#

# Global variables
COLUMNS = ["item_id", "platform", "url", "author_name", "text", "relevant", "author_type", "notes"]
AUTHOR_TYPES = {"buyer", "peer", "vendor", "other"}
#--------------------------------------------------------------#

# Step 1: export collected posts into a CSV for labeling (never overwrites your labels)
def make_template(client: str, n: int) -> None:
    path = CLIENTS_DIR / client / "test_set.csv"
    if path.exists():
        sys.exit(f"{path} already exists. Delete or rename it first; it may hold your labels.")
    with connect() as conn:
        init_db(conn)
        cid = get_client_id(conn, client)
        rows = conn.execute(
            "SELECT id AS item_id, platform, url, author_name, text FROM items "
            "WHERE client_id = ? AND length(COALESCE(text, '')) > 20 ORDER BY RANDOM() LIMIT ?",
            (cid, n)).fetchall()
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({**dict(r), "relevant": "", "author_type": "", "notes": ""})
    print(f"Wrote {len(rows)} posts to {path}. Fill in 'relevant' and 'author_type'.")
#--------------------------------------------------------------#

# Step 2: classify every labeled row and compare with the labels
def evaluate(client: str) -> None:
    path = CLIENTS_DIR / client / "test_set.csv"
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r.get("relevant", "").strip() in {"0", "1"}]
    if not rows:
        sys.exit(f"No labeled rows in {path}. Fill in 'relevant' (1 or 0) first.")

    cfg = load_config(client)
    rel_ok = type_ok = type_n = 0
    misses = []
    with connect() as conn:
        init_db(conn)
        cid = get_client_id(conn, client)
        for r in rows:
            v = classify_one(cfg, conn, cid, r)
            want_rel = r["relevant"].strip() == "1"
            if v.is_relevant == want_rel:
                rel_ok += 1
            else:
                misses.append(("relevant", r, f"you: {int(want_rel)}  model: {int(v.is_relevant)}",
                               v.reason))
            want_type = r.get("author_type", "").strip().lower()
            if want_type in AUTHOR_TYPES:
                type_n += 1
                if v.author_type == want_type:
                    type_ok += 1
                else:
                    misses.append(("author_type", r, f"you: {want_type}  model: {v.author_type}",
                                   v.reason))

    print(f"\nRelevance:   {rel_ok}/{len(rows)} = {100 * rel_ok / len(rows):.0f}%  (target 80%+)")
    if type_n:
        print(f"Author type: {type_ok}/{type_n} = {100 * type_ok / type_n:.0f}%")
    print(f"\nDisagreements ({len(misses)}):")
    for field, r, verdicts, reason in misses:
        print(f"\n[{field}] {verdicts}\n  {r['url']}\n  text:   {' '.join(r['text'].split())[:160]}"
              f"\n  model's reason: {reason}")
#--------------------------------------------------------------#

# Command-line entry point
def main() -> None:
    p = argparse.ArgumentParser(description="Classifier accuracy against your labels")
    p.add_argument("--client", required=True)
    p.add_argument("--make-template", type=int, metavar="N", help="export N posts to label")
    args = p.parse_args()
    if args.make_template:
        make_template(args.client, args.make_template)
    else:
        evaluate(args.client)
#--------------------------------------------------------------#

if __name__ == "__main__":
    main()
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#