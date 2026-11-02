#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
import hashlib
import json
import os
import sqlite3
from typing import TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from suggester.core.db import now_iso
from suggester.core.log import get_logger
from suggester.core.paths import ROOT
#--------------------------------------------------------------#

# Global variables and setup
load_dotenv(ROOT / ".env")
log = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)
MAX_RETRIES = 2
_client = None                                

SYSTEM = (
    "You are a precise data extraction and classification assistant. "
    "Reply with a single JSON object that matches the JSON Schema below. "
    "No markdown, no code fences, no text before or after the JSON.\n\n"
    "JSON Schema:\n{schema}"
)


class LLMError(Exception):
    pass
#--------------------------------------------------------------#

# Read model name and prices from the environment
def _settings() -> tuple[str, float, float]:
    model = os.environ.get("LLM_MODEL")
    if not model:
        raise LLMError("LLM_MODEL is not set in .env")
    price_in = float(os.environ.get("LLM_PRICE_INPUT_PER_MTOK", "0") or 0)
    price_out = float(os.environ.get("LLM_PRICE_OUTPUT_PER_MTOK", "0") or 0)
    return model, price_in, price_out
#--------------------------------------------------------------#

# One API call. Returns (text, input_tokens, output_tokens). Tests replace this with a fake.
def _send(model: str, system: str, messages: list[dict], max_tokens: int) -> tuple[str, int, int]:
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()       # reads ANTHROPIC_API_KEY from the environment
    resp = _client.messages.create(model=model, system=system, messages=messages,
                                   max_tokens=max_tokens)
    text = "".join(block.text for block in resp.content if block.type == "text")
    return text, resp.usage.input_tokens, resp.usage.output_tokens
#--------------------------------------------------------------#

# Helpers: pull the {...} out of a reply, build the cache key, log a call
def _extract_json(text: str) -> str:
    # Models sometimes wrap JSON in ``` fences or add a sentence; keep only the {...} part
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in the reply")
    return text[start:end + 1]


def _cache_key(model: str, schema_json: str, prompt: str) -> str:
    return hashlib.sha256(f"{model}\n{schema_json}\n{prompt}".encode("utf-8")).hexdigest()


def _log_call(conn, client_id, task, model, tokens_in, tokens_out, cost, cached) -> None:
    conn.execute(
        "INSERT INTO llm_calls (client_id, task, model, input_tokens, output_tokens, cost_usd, "
        "cached, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (client_id, task, model, tokens_in, tokens_out, cost, int(cached), now_iso()),
    )
    conn.commit()
#--------------------------------------------------------------#

# Main entry point
def call_llm(task: str, prompt: str, schema: type[T], conn: sqlite3.Connection,
             client_id: int | None = None, max_tokens: int = 1024, use_cache: bool = True) -> T:
    model, price_in, price_out = _settings()
    schema_json = json.dumps(schema.model_json_schema(), sort_keys=True)
    key = _cache_key(model, schema_json, prompt)

    # 1. Cache
    if use_cache:
        row = conn.execute("SELECT response_json FROM llm_cache WHERE key = ?", (key,)).fetchone()
        if row:
            _log_call(conn, client_id, task, model, 0, 0, 0.0, cached=True)
            return schema.model_validate_json(row["response_json"])

    # 2-3. Ask, validate, retry with the error
    system = SYSTEM.format(schema=schema_json)
    messages = [{"role": "user", "content": prompt}]
    tokens_in = tokens_out = 0
    last_error = ""
    result = None

    for attempt in range(MAX_RETRIES + 1):
        text, t_in, t_out = _send(model, system, messages, max_tokens)
        tokens_in += t_in
        tokens_out += t_out
        try:
            result = schema.model_validate_json(_extract_json(text))
            break
        except (ValueError, ValidationError) as e:
            last_error = str(e)
            log.warning("%s: invalid reply on attempt %d: %s", task, attempt + 1, last_error[:200])
            messages += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": f"That reply was invalid:\n{last_error}\n"
                                            "Reply again with only the corrected JSON object."},
            ]

    # 4. Log cost (also for failed attempts: you paid for them)
    cost = tokens_in / 1e6 * price_in + tokens_out / 1e6 * price_out
    _log_call(conn, client_id, task, model, tokens_in, tokens_out, cost, cached=False)
    if result is None:
        raise LLMError(f"{task}: no valid reply after {MAX_RETRIES + 1} attempts. "
                       f"Last error: {last_error}")

    # 5. Cache only valid answers
    conn.execute(
        "INSERT INTO llm_cache (key, response_json, created_at) VALUES (?, ?, ?) "
        "ON CONFLICT (key) DO UPDATE SET response_json = excluded.response_json",
        (key, result.model_dump_json(), now_iso()),
    )
    conn.commit()
    return result
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#