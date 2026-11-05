#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
from suggester.sources.linkedin_search import LinkedInSearch
from suggester.sources.manual_paste import ManualPaste
from suggester.sources.reddit_search import RedditSearch
from suggester.sources.sap_community import SapCommunity
#--------------------------------------------------------------#

# The registry
REGISTRY = {
    LinkedInSearch.name: LinkedInSearch,
    SapCommunity.name: SapCommunity,
    RedditSearch.name: RedditSearch,
    ManualPaste.name: ManualPaste,
}
#--------------------------------------------------------------#

# Create an adapter by name (some adapters need the client name, e.g. for their inbox folder)
def make_source(name: str, client: str):
    if name not in REGISTRY:
        raise ValueError(f"Unknown source {name!r}. Known sources: {sorted(REGISTRY)}")
    cls = REGISTRY[name]
    return cls(client) if name == ManualPaste.name else cls()
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#