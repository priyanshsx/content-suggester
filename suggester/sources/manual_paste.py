#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
import shutil
from datetime import date
from pathlib import Path

from suggester.core.log import get_logger
from suggester.core.paths import inbox_dir
from suggester.core.schemas import Query, SourceItem
from suggester.sources.base import clean_url
#--------------------------------------------------------------#

# Global variables
log = get_logger(__name__)
#--------------------------------------------------------------#

# Work out the platform from the URL
def platform_from_url(url: str) -> str:
    for key, platform in (("linkedin.com", "linkedin"), ("community.sap.com", "sap_community"),
                          ("x.com", "x"), ("twitter.com", "x"), ("reddit.com", "reddit"),
                          ("youtube.com", "youtube"), ("youtu.be", "youtube")):
        if key in url:
            return platform
    return "manual"
#--------------------------------------------------------------#

# Turn one pasted file's text into items
def parse_blocks(text: str, source: str = "manual_paste") -> list[SourceItem]:
    items = []
    for block in text.split("\n---"):
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
        if not lines or not lines[0].startswith("http"):
            continue
        url, rest = clean_url(lines[0]), lines[1:]
        author = None
        if rest and rest[0].lower().startswith("author:"):
            author = rest[0].split(":", 1)[1].strip() or None
            rest = rest[1:]
        items.append(SourceItem(platform=platform_from_url(url), source=source, url=url,
                                text="\n".join(rest), author_name=author,
                                raw={"pasted": True}))
    return items
#--------------------------------------------------------------#

# The adapter
class ManualPaste:
    name = "manual_paste"
    uses_queries = False

    def __init__(self, client: str):
        self.folder: Path = inbox_dir(client)

    def fetch(self, queries: list[Query], since: date) -> list[SourceItem]:
        if not self.folder.exists():
            return []
        items = []
        done = self.folder / "processed"
        for f in sorted(self.folder.glob("*.txt")):
            found = parse_blocks(f.read_text(encoding="utf-8"), self.name)
            log.info("manual_paste: %s -> %d posts", f.name, len(found))
            items.extend(found)
            done.mkdir(exist_ok=True)
            shutil.move(str(f), done / f.name)
        return items
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#