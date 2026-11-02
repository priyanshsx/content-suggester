#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
import re
from datetime import date, datetime, timedelta
from typing import Protocol

from suggester.core.schemas import Query, SourceItem
#--------------------------------------------------------------#

# The adapter contract
class Source(Protocol):
    name: str
    uses_queries: bool

    def fetch(self, queries: list[Query], since: date) -> list[SourceItem]: ...
#--------------------------------------------------------------#

# Helper: turn search-engine dates ("3 days ago", "Oct 30, 2026") into an ISO date
_RELATIVE = re.compile(r"(\d+)\s+(minute|hour|day|week|month)s?\s+ago", re.IGNORECASE)
_UNIT_DAYS = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30}
_FORMATS = ("%b %d, %Y", "%d %b %Y", "%Y-%m-%d", "%d.%m.%Y")


def parse_search_date(text: str | None, today: date | None = None) -> str | None:
    if not text:
        return None
    today = today or date.today()
    m = _RELATIVE.search(text)
    if m:
        days = int(m.group(1)) * _UNIT_DAYS[m.group(2).lower()]
        return (today - timedelta(days=days)).isoformat()
    for fmt in _FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None
#--------------------------------------------------------------#

# Helper: drop tracking parameters so the same post always has the same URL (our dedupe key)
def clean_url(url: str) -> str:
    return url.split("?")[0].split("#")[0].rstrip("/")
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#