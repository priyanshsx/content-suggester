#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: suggester/pipeline/export.py
# Purpose: write this week's CSV for review (built in step 4.5).
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
    log.info("export: not built yet")
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#
