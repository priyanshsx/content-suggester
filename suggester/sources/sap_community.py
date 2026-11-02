#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
import re
from datetime import date

from suggester.core.schemas import Query, SourceItem
from suggester.sources import serper
from suggester.sources.base import clean_url, parse_search_date
#--------------------------------------------------------------#

# Global variables: keep only threads/blog posts (SAP Community URLs contain /t5/)
THREAD_URL = re.compile(r"community\.sap\.com/t5/", re.IGNORECASE)
#--------------------------------------------------------------#

# The adapter
class SapCommunity:
    name = "sap_community"
    uses_queries = True

    def fetch(self, queries: list[Query], since: date) -> list[SourceItem]:
        items = []
        for q in queries:
            for r in serper.search(q.text, period="w"):
                url = r.get("link", "")
                if not THREAD_URL.search(url):
                    continue
                items.append(SourceItem(
                    platform="sap_community",
                    source=self.name,
                    url=clean_url(url),
                    text=f"{r.get('title', '')}\n{r.get('snippet', '')}".strip(),
                    posted_at=parse_search_date(r.get("date")),
                    source_query=q.text,
                    raw={**r, "_topic": q.topic, "_pillar": q.pillar, "_language": q.language},
                ))
        return items
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#