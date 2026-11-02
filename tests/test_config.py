#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

import pytest
from pydantic import ValidationError
from suggester.core import config
#--------------------------------------------------------------#

def test_vizcorn_config_loads():
    cfg = config.load_config("vizcorn")
    assert cfg.client == "vizcorn"
    assert cfg.threads_per_week == 10                  # from template
    assert cfg.languages == ["en", "de"]               # client overrides template
    assert len(cfg.topics) >= 1


def test_deep_merge_keeps_template_keys():
    base = {"scoring": {"a": 1, "b": 2}, "sources": ["x", "y"]}
    over = {"scoring": {"b": 20}, "sources": ["z"]}
    assert config.deep_merge(base, over) == {"scoring": {"a": 1, "b": 20}, "sources": ["z"]}


def valid_data():
    cfg = config.load_config("vizcorn")
    return cfg.model_dump()


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