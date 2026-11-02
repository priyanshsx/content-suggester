#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: suggester/pipeline/context.py
# Purpose: everything a pipeline stage needs, bundled into one object (passed to every stage).
#--------------------------------------------------------------#

# Imports Libraries
import sqlite3
from dataclasses import dataclass
from datetime import date

from suggester.core.config import Config
#--------------------------------------------------------------#

# The run context
@dataclass
class RunContext:
    cfg: Config                    # the client's merged, validated config
    conn: sqlite3.Connection       # open database connection
    client_id: int                 # the client's row id in the clients table
    week: str                      # ISO week label, e.g. "2026-W45"
    dry_run: bool = False          # True = don't call paid APIs (stages decide what that means)
    feedback_file: str | None = None
#--------------------------------------------------------------#

# ISO week label for a date (Monday-start weeks, as used in DACH)
def iso_week(d: date | None = None) -> str:
    year, week, _ = (d or date.today()).isocalendar()
    return f"{year}-W{week:02d}"
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#
