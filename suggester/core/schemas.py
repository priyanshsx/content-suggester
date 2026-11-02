#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
from pydantic import BaseModel, Field
#--------------------------------------------------------------#

# One search to run: a keyword turned into a platform-specific query
class Query(BaseModel):
    text: str                      # what we actually send, e.g. site:linkedin.com/posts "SAP MDG"
    keyword: str                   # the raw keyword from the config
    topic: str                     # topic name from the config
    pillar: str                    # pillar that topic belongs to
    language: str                  # "en", "de", ...
#--------------------------------------------------------------#

# One thread/post from any platform, in the same shape whatever the source
class SourceItem(BaseModel):
    platform: str                  # linkedin, sap_community, manual, x, reddit, youtube
    source: str                    # adapter name, e.g. linkedin_search
    url: str
    text: str = ""
    external_id: str | None = None
    author_handle: str | None = None
    author_name: str | None = None
    posted_at: str | None = None   # ISO date if known
    engagement: dict = Field(default_factory=dict)
    source_query: str | None = None
    raw: dict = Field(default_factory=dict)
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#