#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: suggester/core/sheets.py
# Purpose: open one tab of a client's Google Sheet with the service account key
#          (the same key and helper as the job-alerts repo). Creates the tab if it's missing.
#--------------------------------------------------------------#

# Imports Libraries
import os

import gspread
from dotenv import load_dotenv

from suggester.core.paths import ROOT
#--------------------------------------------------------------#

# Global variables
load_dotenv(ROOT / ".env")
#--------------------------------------------------------------#

# Open (or create) a tab in a spreadsheet
def open_worksheet(spreadsheet_id: str, worksheet: str):
    key_file = ROOT / os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "secrets/google_service_account.json")
    if not key_file.exists():
        raise FileNotFoundError(
            f"Google service account key not found at {key_file}. "
            "Copy it from the job-alerts repo into secrets/, or set GOOGLE_SERVICE_ACCOUNT_FILE in .env."
        )
    gc = gspread.service_account(filename=str(key_file))
    spreadsheet = gc.open_by_key(spreadsheet_id)
    try:
        return spreadsheet.worksheet(worksheet)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=worksheet, rows=1000, cols=26)
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#
