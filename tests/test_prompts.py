#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
import pytest

from suggester.core import prompts
#--------------------------------------------------------------#

# Setup: a throwaway prompt file in a temporary folder
@pytest.fixture
def prompt_dir(tmp_path, monkeypatch):
    (tmp_path / "hello.md").write_text(
        'Client: {{ client }}\nPost: {{text}}\nReply like {"ok": true}', encoding="utf-8")
    monkeypatch.setattr(prompts, "PROMPTS_DIR", tmp_path)
    return tmp_path
#--------------------------------------------------------------#

# Tests: rendering
def test_renders_placeholders_and_keeps_json_braces(prompt_dir):
    out = prompts.render_prompt("hello", client="Vizcorn", text="MDG question")
    assert out == 'Client: Vizcorn\nPost: MDG question\nReply like {"ok": true}'
#--------------------------------------------------------------#

# Tests: mistakes are caught
def test_missing_value_raises(prompt_dir):
    with pytest.raises(prompts.PromptError, match="needs values for"):
        prompts.render_prompt("hello", client="Vizcorn")


def test_unused_value_raises(prompt_dir):
    with pytest.raises(prompts.PromptError, match="no placeholder for"):
        prompts.render_prompt("hello", client="Vizcorn", text="x", txet="typo")


def test_missing_file_raises(prompt_dir):
    with pytest.raises(prompts.PromptError, match="not found"):
        prompts.render_prompt("nope")
#--------------------------------------------------------------#

# Tests: versioning
def test_version_changes_when_prompt_changes(prompt_dir):
    v1 = prompts.prompt_version("hello")
    (prompt_dir / "hello.md").write_text("changed {{client}} {{text}}", encoding="utf-8")
    assert prompts.prompt_version("hello") != v1
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#