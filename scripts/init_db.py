#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
from suggester.core.db import connect, init_db 
from suggester.core.paths import CACHE_DIR, CLIENTS_DIR, MIGRATIONS_DIR, OUTPUTS_DIR, db_path
#--------------------------------------------------------------#

# creates base folders and the database for each client
def main() -> None:
    for folder in (CACHE_DIR, OUTPUTS_DIR, CLIENTS_DIR, MIGRATIONS_DIR):
        folder.mkdir(parents=True, exist_ok=True)

    with connect() as conn:
        applied = init_db(conn)
        tables = [r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )]

    print(f"Database: {db_path()}")
    print(f"Tables ({len(tables)}): {", ".join(tables)}")
    print(f"Migrations applied now: {applied or 'none'}")

if __name__ == "__main__":
    main()
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#