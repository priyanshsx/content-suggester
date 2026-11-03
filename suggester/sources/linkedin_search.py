#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: suggester/sources/linkedin_search.py
# Purpose: LinkedIn posts found through Google (Serper) with "site:linkedin.com/posts".
#          We never visit LinkedIn itself: we only read what Google shows (title, snippet, date).
#--------------------------------------------------------------#

# Imports Libraries
import re
from datetime import date

from suggester.core.schemas import Query, SourceItem
from suggester.sources import serper
from suggester.sources.base import clean_url, parse_search_date
#--------------------------------------------------------------#

# Global variables
POST_URL = re.compile(r"linkedin\.com/(posts|feed/update)/", re.IGNORECASE)
HANDLE_IN_URL = re.compile(r"linkedin\.com/posts/([^_/]+)_", re.IGNORECASE)
#--------------------------------------------------------------#

# Guess the author's name from Google's title, e.g.
#   "Jane Doe on LinkedIn: Our S/4HANA migration..."  -> "Jane Doe"
#   "Our S/4HANA migration... | Jane Doe | 12 comments" -> "Jane Doe"
def author_from_title(title: str) -> str | None:
    if " on LinkedIn" in title:
        return title.split(" on LinkedIn")[0].strip() or None
    parts = [p.strip() for p in title.split("|")]
    if len(parts) >= 2:
        candidate = parts[1].replace(" posted on the topic", "").strip()
        if candidate and "comment" not in candidate.lower() and candidate.lower() != "linkedin":
            return candidate
    return None
#--------------------------------------------------------------#

# The adapter
class LinkedInSearch:
    name = "linkedin_search"
    uses_queries = True

    def fetch(self, queries: list[Query], since: date) -> list[SourceItem]:
        items = []
        for q in queries:
            gl = hl = q.language if q.language != "en" else None
            for r in serper.search(q.text, period="w", gl=gl, hl=hl):
                url = r.get("link", "")
                if not POST_URL.search(url):           # skip profiles, jobs, company pages
                    continue
                handle = HANDLE_IN_URL.search(url)
                items.append(SourceItem(
                    platform="linkedin",
                    source=self.name,
                    url=clean_url(url),
                    text=r.get("snippet", ""),
                    author_name=author_from_title(r.get("title", "")),
                    author_handle=handle.group(1) if handle else None,
                    posted_at=parse_search_date(r.get("date")),
                    source_query=q.text,
                    raw={**r, "_topic": q.topic, "_pillar": q.pillar, "_language": q.language},
                ))
        return items
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#
