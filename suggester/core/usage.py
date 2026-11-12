#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: suggester/core/usage.py
# Purpose: log paid API calls other than the LLM (Serper searches) to api_calls, for the cost
#          dashboard. The CLI sets the client and stage once; sources just call log().
#          Prices come from .env (defaults in brackets): SERPER_USD_PER_CREDIT (0.001).
#--------------------------------------------------------------#

# Imports Libraries
import os
from suggester.core.db import connect, now_iso
from suggester.core.log import get_logger
#--------------------------------------------------------------#

# Global variables
log = get_logger(__name__)
_context = {"client_id": None, "task": None}
#--------------------------------------------------------------#

# Called once by the CLI
def set_context(client_id: int | None, task: str | None) -> None:
    _context.update(client_id=client_id, task=task)
#--------------------------------------------------------------#

def serper_price() -> float:
    return float(os.getenv("SERPER_USD_PER_CREDIT") or 0.001)
#--------------------------------------------------------------#

# Record one paid call. Never lets a logging problem stop the run.
def log_call(service: str, units: int, cost_usd: float) -> None:
    try:
        conn = connect()
        try:
            conn.execute("INSERT INTO api_calls (client_id, service, task, units, cost_usd, created_at) "
                         "VALUES (?, ?, ?, ?, ?, ?)",
                         (_context["client_id"], service, _context["task"], units, cost_usd, now_iso()))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        log.warning("couldn't log %s usage: %s", service, e)
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#
