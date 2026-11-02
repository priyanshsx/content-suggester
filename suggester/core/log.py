#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
import logging
import os
#--------------------------------------------------------------#

# Return a logger; configure the format once (set LOG_LEVEL=DEBUG in .env for more detail)
def get_logger(name: str) -> logging.Logger:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=os.environ.get("LOG_LEVEL", "INFO"),
            format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    return logging.getLogger(name)
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#