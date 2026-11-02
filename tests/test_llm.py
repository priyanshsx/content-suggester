#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
import pytest
from pydantic import BaseModel

from suggester.core import db, llm
#--------------------------------------------------------------#

# Answer shape used by the tests
class Verdict(BaseModel):
    is_relevant: bool
    reason: str
#--------------------------------------------------------------#

# Setup: test database + fake model settings ($1 per M input, $5 per M output)
@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("SUGGESTER_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_PRICE_INPUT_PER_MTOK", "1.0")
    monkeypatch.setenv("LLM_PRICE_OUTPUT_PER_MTOK", "5.0")
    c = db.connect()
    db.init_db(c)
    yield c
    c.close()


# Fake API: returns the given replies in order; each call "uses" 1000 input + 100 output tokens
def fake_api(monkeypatch, replies):
    calls = []

    def _fake_send(model, system, messages, max_tokens):
        calls.append(messages)
        return replies[len(calls) - 1], 1000, 100
    monkeypatch.setattr(llm, "_send", _fake_send)
    return calls
#--------------------------------------------------------------#

# Tests: reading replies
def test_valid_reply(conn, monkeypatch):
    fake_api(monkeypatch, ['{"is_relevant": true, "reason": "asks about MDG"}'])
    out = llm.call_llm("test", "prompt A", Verdict, conn)
    assert out.is_relevant is True and out.reason == "asks about MDG"


def test_reply_wrapped_in_code_fence(conn, monkeypatch):
    fake_api(monkeypatch, ['```json\n{"is_relevant": false, "reason": "vendor ad"}\n```'])
    assert llm.call_llm("test", "prompt B", Verdict, conn).is_relevant is False
#--------------------------------------------------------------#

# Tests: cache
def test_second_identical_call_uses_cache(conn, monkeypatch):
    calls = fake_api(monkeypatch, ['{"is_relevant": true, "reason": "x"}'])
    llm.call_llm("test", "same prompt", Verdict, conn)
    llm.call_llm("test", "same prompt", Verdict, conn)
    assert len(calls) == 1
    rows = conn.execute("SELECT cached, cost_usd FROM llm_calls ORDER BY id").fetchall()
    assert [(r["cached"], r["cost_usd"]) for r in rows] == [(0, pytest.approx(0.0015)), (1, 0.0)]
#--------------------------------------------------------------#

# Tests: retries
def test_retries_after_invalid_reply(conn, monkeypatch):
    calls = fake_api(monkeypatch, ["not json at all", '{"is_relevant": true, "reason": "ok"}'])
    out = llm.call_llm("test", "prompt C", Verdict, conn)
    assert out.reason == "ok"
    assert len(calls) == 2
    assert "invalid" in calls[1][-1]["content"]


def test_gives_up_after_max_retries(conn, monkeypatch):
    fake_api(monkeypatch, ['{"is_relevant": "maybe"}'] * 3)
    with pytest.raises(llm.LLMError):
        llm.call_llm("test", "prompt D", Verdict, conn)
    assert conn.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0] == 0
#--------------------------------------------------------------#

# Tests: cost logging
def test_cost_is_logged(conn, monkeypatch):
    fake_api(monkeypatch, ['{"is_relevant": true, "reason": "x"}'])
    llm.call_llm("test", "prompt E", Verdict, conn)
    cost = conn.execute("SELECT cost_usd FROM llm_calls").fetchone()[0]
    assert cost == pytest.approx(0.0015)              # 1000 x $1/M + 100 x $5/M
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#