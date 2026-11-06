#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: suggester/core/schemas.py
# Purpose: shared data shapes passed between adapters, the LLM and pipeline stages.
#--------------------------------------------------------------#

# Imports Libraries
from typing import Literal

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

# The classifier's verdict on one item (the LLM must reply in exactly this shape).
# "reason" comes first so the model thinks before it decides.
class ThreadClassification(BaseModel):
    reason: str = Field(description="One or two sentences: why this is or isn't worth joining")
    is_relevant: bool = Field(description="True if the post is worth commenting on, per the engagement goal")
    pillar: str = Field(description="One of the listed pillar names, or 'none'")
    author_type: Literal["buyer", "peer", "vendor", "other"]
    has_pain_or_question: bool = Field(description="Author describes a problem or asks a question")
    region: str = Field(description="One of the listed regions, 'other', or 'unknown'")
    comment_angle: str = Field(description="What the client could usefully say. Empty if not relevant")
    is_job_post: bool = Field(default=False,
                              description="True if the post advertises a job or looks for candidates")
    is_request: bool = Field(default=False,
                             description="True if the author is looking for outside help: a provider, "
                                         "consultant, freelancer, partner or recommendation")
    request_summary: str = Field(default="", description="One line: what they need. Empty if not a request")
    requester_company: str = Field(default="", description="Company the author represents, if stated")
    poster_kind: Literal["person", "company", "unknown"] = Field(
        default="unknown", description="Whether the post comes from a person or a company page")
    new_terms: list[str] = Field(default_factory=list, max_length=3,
                                 description="Up to 3 short phrases the author uses that are worth "
                                             "tracking as search keywords")
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#
