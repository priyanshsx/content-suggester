#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries 
from pathlib import Path 
import yaml 
from pydantic import BaseModel, ConfigDict, Field, model_validator 
from suggester.core.paths import CLIENTS_DIR, CONFIG_DIR
#--------------------------------------------------------------#

# classes for content pillars and global variables 
class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Pillar(Strict):
    name: str 
    description: str 

class Topic(Strict):
    name: str 
    pillar: str 
    keywords: dict[str, list[str]]

class Scoring(Strict):
    recency_half_life_days: float 
    points: dict[str, float]
    author_type_points: dict[str, float]

class Compliance(Strict):
    rules: list[str] = Field(default_factory=list)

class Config(Strict):
    client: str
    display_name: str 
    offer: str 
    positioning: str 
    languages: list[str]
    regions: list[str] = Field(default_factory=list)
    pillars: list[Pillar] = Field(min_length=1)
    topics: list[Topic] = Field(min_length=1)
    compliance: Compliance = Field(default_factory=Compliance)

    lookback_days: int = Field(gt=0)
    threads_per_week: int = Field(gt=0)
    max_per_author: int = Field(gt=0)
    max_items_per_run: int = Field(gt=0)
    sources: list[str] = Field(min_length=1)
    query_templates: dict[str, str]
    scoring: Scoring 
#--------------------------------------------------------------#

    @model_validator(mode="after")
    def check_references(self):
        """Catch typos between sections that Pydantic can't see on its own."""
        pillar_names = {p.name for p in self.pillars}
        for t in self.topics:
            if t.pillar not in pillar_names:
                raise ValueError(f"Topic {t.name!r} uses unknown pillar {t.pillar!r}. "
                                 f"Known pillars: {sorted(pillar_names)}")
            for lang in t.keywords:
                if lang not in self.languages:
                    raise ValueError(f"Topic {t.name!r} has keywords in {lang!r}, "
                                     f"which is not in languages {self.languages}")
        for tpl_name, tpl in self.query_templates.items():
            if "{keyword}" not in tpl:
                raise ValueError(f"Query template {tpl_name!r} must contain {{keyword}}")
        return self
#--------------------------------------------------------------# 
 
def deep_merge(base: dict, override: dict) -> dict:
    """Nested dicts are merged key by key; anything else (incl. lists) in override wins."""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out
#--------------------------------------------------------------#
 
def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping (key: value pairs)")
    return data
#--------------------------------------------------------------# 
 
def load_config(client: str) -> Config:
    template = _read_yaml(CONFIG_DIR / "template.yaml")
    client_cfg = _read_yaml(CLIENTS_DIR / client / "config.yaml")
    merged = deep_merge(template, client_cfg)
    merged["client"] = client
    return Config.model_validate(merged)
#--------------------------------------------------------------#

if __name__ == "__main__":
    import sys
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "vizcorn")
    print(yaml.safe_dump(cfg.model_dump(), sort_keys=False, allow_unicode=True))
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#