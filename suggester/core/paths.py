#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries 
import os 
from pathlib import Path 
#--------------------------------------------------------------#

# Finds the pyproject file 
def _find_root() -> Path:
    here = Path(__file__).resolve()
    for folder in [here, *here.parents]:
        if (folder / "pyproject.toml").exists():
            return folder
    raise RuntimeError("Couldn't find pyproject.toml above " + str(here))
#--------------------------------------------------------------#

# Specifies the path of each of the files and folders
ROOT = _find_root()
CONFIG_DIR = ROOT / "config"
CLIENTS_DIR = CONFIG_DIR / "clients"
PROMPTS_DIR = ROOT / "prompts"
SCHEMA_PATH = ROOT / "db" / "schema.sql"
MIGRATIONS_DIR = ROOT / "db" / "migrations"
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / "cache"
OUTPUTS_DIR = ROOT / "outputs"
#--------------------------------------------------------------#

def db_path() -> Path:
    return Path(os.environ.get("SUGGESTER_DB_PATH", DATA_DIR / "suggester.db"))

def inbox_dir(client: str) -> Path:
    return DATA_DIR / "inbox" / client / "threads"

def output_dir(client: str) -> Path:
    return OUTPUTS_DIR / client / "threads"
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#