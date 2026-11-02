#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
import hashlib
import re

from suggester.core.paths import PROMPTS_DIR
#--------------------------------------------------------------#

# Global variables and error class
# Double braces {{name}} so prompts can still contain normal JSON examples with { }
_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class PromptError(Exception):
    pass
#--------------------------------------------------------------#

# Read a prompt file
def _read(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise PromptError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")
#--------------------------------------------------------------#

# List the placeholders a prompt expects
def placeholders(name: str) -> set[str]:
    return set(_PLACEHOLDER.findall(_read(name)))
#--------------------------------------------------------------#

# Fill in the prompt. Fails on a missing value AND on an unused one (usually a typo)
def render_prompt(name: str, **values) -> str:
    text = _read(name)
    needed = set(_PLACEHOLDER.findall(text))
    missing = needed - values.keys()
    unused = values.keys() - needed
    if missing:
        raise PromptError(f"Prompt {name!r} needs values for: {sorted(missing)}")
    if unused:
        raise PromptError(f"Prompt {name!r} has no placeholder for: {sorted(unused)}")
    return _PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), text)
#--------------------------------------------------------------#

# Short fingerprint of the prompt file; changes whenever you edit the prompt
def prompt_version(name: str) -> str:
    return hashlib.sha256(_read(name).encode("utf-8")).hexdigest()[:10]
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#