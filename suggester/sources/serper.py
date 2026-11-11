#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
import hashlib
import json
import os
from datetime import date
from pathlib import Path

import httpx
from dotenv import load_dotenv

from suggester.core.log import get_logger
from suggester.core.paths import CACHE_DIR, ROOT
#--------------------------------------------------------------#

# Global variables and setup
load_dotenv(ROOT / ".env")
log = get_logger(__name__)

SERPER_URL = "https://google.serper.dev/search"
CACHE = CACHE_DIR / "serper"


class SerperError(Exception):
    pass
#--------------------------------------------------------------#

# Cache file for one query on one day
def _cache_path(payload: dict) -> Path:
    key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return CACHE / f"{date.today().isoformat()}_{key}.json"
#--------------------------------------------------------------#

# The actual HTTP call (tests replace this with a fake)
def _post(payload: dict) -> dict:
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        raise SerperError("SERPER_API_KEY is not set in .env")
    resp = httpx.post(SERPER_URL, json=payload, timeout=30,
                      headers={"X-API-KEY": api_key, "Content-Type": "application/json"})
    if resp.status_code != 200:
        raise SerperError(f"Serper returned {resp.status_code}: {resp.text[:300]}")
    return resp.json()
#--------------------------------------------------------------#

# Main entry point: search Google, return the organic results
#   period: "d" past day, "w" past week, "m" past month
#   gl/hl:  country and language, e.g. gl="de", hl="de" for German results
# Google's time filter for "posts since this date": week, month or year
def period_since(since) -> str:
    from datetime import date
    days = (date.today() - since).days
    return "w" if days <= 7 else "m" if days <= 31 else "y"
#--------------------------------------------------------------#

def search(q: str, period: str = "w", num: int = 10,
           gl: str | None = None, hl: str | None = None) -> list[dict]:
    payload = {"q": q, "tbs": f"qdr:{period}", "num": num}
    if gl:
        payload["gl"] = gl
    if hl:
        payload["hl"] = hl

    path = _cache_path(payload)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = _post(payload)
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        log.info("serper: %r -> %d results", q, len(data.get("organic", [])))
    return data.get("organic", [])
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#