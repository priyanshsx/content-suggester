#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
from pydantic import BaseModel

from suggester.core.db import connect, init_db
from suggester.core.llm import call_llm
#--------------------------------------------------------------#

# Answer shape and test prompt
class Verdict(BaseModel):
    is_relevant: bool
    author_type: str
    reason: str


POST = ("We're 8 months into our S/4HANA migration and still finding duplicate vendor "
        "records everywhere. How did others clean up master data before go-live?")

PROMPT = f"""A consultancy helps mid-sized manufacturers get SAP master data ready for S/4HANA.
Is this LinkedIn post a conversation they could usefully join?
author_type must be one of: buyer, peer, vendor, other.

Post: {POST}"""
#--------------------------------------------------------------#

# Make the call and print the answer plus the logged cost row
def main() -> None:
    with connect() as conn:
        init_db(conn)
        out = call_llm("smoke_test", PROMPT, Verdict, conn)
        last = conn.execute(
            "SELECT model, input_tokens, output_tokens, cost_usd, cached "
            "FROM llm_calls ORDER BY id DESC LIMIT 1").fetchone()
    print(out.model_dump())
    print(dict(last))
#--------------------------------------------------------------#

if __name__ == "__main__":
    main()
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#