#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: suggester/sources/reddit_search.py
# Purpose: find Reddit threads through Google search (Serper), the same way linkedin_search
#          finds LinkedIn posts. No Reddit account or API key needed.
#          Query template (in the client's config): site:reddit.com/r "{keyword}"
#--------------------------------------------------------------#

# Imports Libraries
import re
from datetime import date

from suggester.core.schemas import Query, SourceItem
from suggester.sources import serper
from suggester.sources.base import clean_url, parse_search_date
#--------------------------------------------------------------#

# Global variables: keep only thread pages, e.g. reddit.com/r/investing/comments/abc123/title/
THREAD_URL = re.compile(r"reddit\.com/r/([A-Za-z0-9_]+)/comments/([a-z0-9]+)", re.IGNORECASE)
#--------------------------------------------------------------#

# The adapter
class RedditSearch:
    name = "reddit_search"
    uses_queries = True

    def fetch(self, queries: list[Query], since: date) -> list[SourceItem]:
        items = []
        for q in queries:
            for r in serper.search(q.text, period=serper.period_since(since)):
                url = r.get("link", "")
                match = THREAD_URL.search(url)
                if not match:
                    continue
                subreddit, thread_id = match.group(1), match.group(2)
                items.append(SourceItem(
                    platform="reddit",
                    source=self.name,
                    url=clean_url(url),
                    external_id=thread_id,
                    author_name=f"r/{subreddit}",          # the community; Google rarely shows the poster
                    text=f"{r.get('title', '')}\n{r.get('snippet', '')}".strip(),
                    posted_at=parse_search_date(r.get("date")),
                    source_query=q.text,
                    raw={**r, "_topic": q.topic, "_pillar": q.pillar, "_language": q.language},
                ))
        return items
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#
