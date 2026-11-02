#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries 
import sys 
from suggester.core.db import connect, init_db, now_iso, upsert 
from suggester.core.paths import CLIENTS_DIR, inbox_dir, output_dir

STARTER = """display_name: {name}
offer: TODO what the client sells, to whom
positioning: TODO one-line positioning
languages: [en]
regions: []
pillars:
  - name: example_pillar
    description: TODO
topics:
  - name: example_topic
    pillar: example_pillar
    keywords:
      en: ["TODO keyword"]
compliance:
  rules: []
"""

def main() -> None: 
    if len(sys.argv) != 2:
        sys.exit("Usage: python scripts/new_client.py <name")
    name = sys.argv[1].strip().lower()

    folder = CLIENTS_DIR / name 
    folder.mkdir(parents=True, exist_ok=True)
    cfg = folder / "config.yaml"

    if cfg.exists():
        print(f"Kept existing {cfg}")
    else:
        cfg.write_text(STARTER.format(name=name), encoding="utf-8")
        print(f"Created {cfg} (fill in the TODOs)")

    for d in (inbox_dir(name), output_dir(name)):
        d.mkdir(parents=True, exist_ok=True)

    with connect() as conn:
        init_db(conn)
        cid = upsert(conn, "clients",
                     {"name": name, "config_path": str(folder.relative_to(CLIENTS_DIR.parent.parent)),
                      "created_at": now_iso()},
                      conflict_cols=["name"], update_cols=["config_path"])
    print(f"Client {name!r} registered with id {cid}")

if __name__ == "__main__":
    main()
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#