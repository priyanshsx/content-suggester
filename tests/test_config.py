#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: tests/test_config.py
# Purpose: check that configs load, merge correctly and that typos are caught.
# Usage:   python -m pytest tests/test_config.py -v
#--------------------------------------------------------------#

# Imports Libraries
import pytest
from pydantic import ValidationError

from suggester.core import config
#--------------------------------------------------------------#

# Helper: a valid config as a plain dict, which tests then break on purpose
def valid_data():
    return config.load_config("vizcorn").model_dump()
#--------------------------------------------------------------#

# Tests: loading and merging
def test_vizcorn_config_loads():
    cfg = config.load_config("vizcorn")
    assert cfg.client == "vizcorn"
    assert cfg.threads_per_week == 10                  # from template
    assert cfg.languages == ["en", "de"]               # client overrides template
    assert len(cfg.topics) >= 1


def test_bacon_config_loads():
    cfg = config.load_config("bacon")
    assert cfg.sources == ["linkedin_search", "manual_paste"]   # no SAP Community
    assert cfg.languages == ["en"] and "hiring manager" in cfg.audience


def test_deep_merge_keeps_template_keys():
    base = {"scoring": {"a": 1, "b": 2}, "sources": ["x", "y"]}
    over = {"scoring": {"b": 20}, "sources": ["z"]}
    assert config.deep_merge(base, over) == {"scoring": {"a": 1, "b": 20}, "sources": ["z"]}
#--------------------------------------------------------------#

# Tests: validation catches mistakes
def test_misspelled_key_is_rejected():
    data = valid_data()
    data["threds_per_week"] = 5
    with pytest.raises(ValidationError):
        config.Config.model_validate(data)


def test_unknown_pillar_is_rejected():
    data = valid_data()
    data["topics"][0]["pillar"] = "no_such_pillar"
    with pytest.raises(ValidationError, match="unknown pillar"):
        config.Config.model_validate(data)


def test_keyword_language_must_be_listed():
    data = valid_data()
    data["languages"] = ["en"]                         # but topics have "de" keywords
    with pytest.raises(ValidationError, match="not in languages"):
        config.Config.model_validate(data)


def test_missing_client_folder():
    with pytest.raises(FileNotFoundError):
        config.load_config("does_not_exist")
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#
