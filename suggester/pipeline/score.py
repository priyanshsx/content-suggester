#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: suggester/pipeline/score.py
# Purpose: score classified items with the config weights (built in step 4.3).
#          Placeholder for now: logs that it isn't built yet.
#--------------------------------------------------------------#

# Imports Libraries
from suggester.core.log import get_logger
from suggester.pipeline.context import RunContext
#--------------------------------------------------------------#

# Global variables
log = get_logger(__name__)
#--------------------------------------------------------------#

# Stage entry point (the CLI calls this)
def run(ctx: RunContext) -> None:
    log.info("score: not built yet")
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#
