#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: tests/test_sources.py
# Purpose: check the adapters turn raw results into clean SourceItems. No real API calls:
#          serper._post is replaced with a fake that returns Google-style results.
# Usage:   python -m pytest tests/test_sources.py -v
#--------------------------------------------------------------#

# Imports Libraries
from datetime import date

import pytest

from suggester.core.config import load_config
from suggester.core.schemas import Query
from suggester.pipeline.queries import build_queries
from suggester.sources import base, linkedin_search, make_source, manual_paste, serper
from suggester.sources.linkedin_search import LinkedInSearch
from suggester.sources.sap_community import SapCommunity
#--------------------------------------------------------------#

# Fake Google results, shaped like Serper's "organic" list
LINKEDIN_RESULTS = {"organic": [
    {"title": "Jane Doe on LinkedIn: 8 months into S/4HANA and still duplicates",
     "link": "https://www.linkedin.com/posts/jane-doe_s4hana-activity-123?utm_source=share",
     "snippet": "How did others clean vendor master data before go-live?", "date": "3 days ago"},
    {"title": "Jane Doe - SAP Lead | LinkedIn",                          # a profile, not a post
     "link": "https://www.linkedin.com/in/jane-doe", "snippet": "Profile"},
    {"title": "We're hiring | Acme Jobs",                                 # job ad
     "link": "https://www.linkedin.com/posts/c2c-jobs_sap-sd-lead-consultant-activity-1",
     "snippet": "SAP SD S/4HANA #JobSearch"},
    {"title": "Why MDG projects stall | Max Mustermann | 14 comments",
     "link": "https://www.linkedin.com/posts/max-mustermann_mdg-activity-456",
     "snippet": "Ownership is the real problem.", "date": "Oct 30, 2026"},
]}

SAP_RESULTS = {"organic": [
    {"title": "Duplicate BP after S/4 conversion", "snippet": "We see duplicates...",
     "link": "https://community.sap.com/t5/enterprise-resource-planning-q-a/dup/qaq-p/1"},
    {"title": "Financial Management", "snippet": "SAP InnoJam; SAP Inside Track",   # category page
     "link": "https://community.sap.com/t5/financial-management/ct-p/financial-management"},
    {"title": "SAP Community home", "link": "https://community.sap.com/", "snippet": "Home"},
]}


@pytest.fixture
def fake_serper(tmp_path, monkeypatch):
    """Replace the HTTP call; count calls; keep the cache in a temp folder."""
    calls = []
    monkeypatch.setattr(serper, "CACHE", tmp_path / "serper_cache")

    def install(response):
        def _fake_post(payload):
            calls.append(payload)
            return response
        monkeypatch.setattr(serper, "_post", _fake_post)
        return calls
    return install


def q(text="site:x \"kw\"", lang="en"):
    return Query(text=text, keyword="kw", topic="t", pillar="p", language=lang)
#--------------------------------------------------------------#

# Tests: shared helpers
def test_parse_search_date():
    today = date(2026, 11, 2)
    assert base.parse_search_date("3 days ago", today) == "2026-10-30"
    assert base.parse_search_date("2 weeks ago", today) == "2026-10-19"
    assert base.parse_search_date("5 hours ago", today) == "2026-11-02"
    assert base.parse_search_date("Oct 30, 2026", today) == "2026-10-30"
    assert base.parse_search_date("yesterday-ish", today) is None
    assert base.parse_search_date(None, today) is None


def test_clean_url_removes_tracking():
    assert base.clean_url("https://a.com/p/1?utm=x#top") == "https://a.com/p/1"


def test_author_from_title():
    assert linkedin_search.author_from_title("Jane Doe on LinkedIn: hi") == "Jane Doe"
    assert linkedin_search.author_from_title("Post | Max Mustermann | 3 comments") == "Max Mustermann"
    assert linkedin_search.author_from_title("Just a title") is None
#--------------------------------------------------------------#

# Tests: LinkedIn adapter
def test_linkedin_keeps_posts_only(fake_serper):
    fake_serper(LINKEDIN_RESULTS)
    items = LinkedInSearch().fetch([q()], date.today())
    assert len(items) == 3                                     # profile dropped, job ad kept
    first = items[0]
    assert first.url == "https://www.linkedin.com/posts/jane-doe_s4hana-activity-123"
    assert first.author_name == "Jane Doe"
    assert first.author_handle == "jane-doe"
    assert first.platform == "linkedin" and first.source == "linkedin_search"
    assert items[2].posted_at == "2026-10-30"


def test_german_query_sets_country_and_language(fake_serper):
    calls = fake_serper(LINKEDIN_RESULTS)
    LinkedInSearch().fetch([q(lang="de")], date.today())
    assert calls[0]["gl"] == "de" and calls[0]["hl"] == "de"
    assert calls[0]["tbs"] == "qdr:w"                          # past week only


def test_same_query_same_day_hits_cache(fake_serper):
    calls = fake_serper(LINKEDIN_RESULTS)
    LinkedInSearch().fetch([q()], date.today())
    LinkedInSearch().fetch([q()], date.today())
    assert len(calls) == 1                                     # second run was free
#--------------------------------------------------------------#

# Tests: SAP Community adapter
def test_sap_community_keeps_threads_only(fake_serper):
    fake_serper(SAP_RESULTS)
    items = SapCommunity().fetch([q()], date.today())
    assert len(items) == 1
    assert items[0].platform == "sap_community"
    assert items[0].text.startswith("Duplicate BP")
#--------------------------------------------------------------#

# Tests: manual paste
def test_parse_pasted_blocks():
    text = ("https://www.linkedin.com/posts/a_x?utm=1\nauthor: Anna\nPost one\nsecond line\n---\n"
            "https://community.sap.com/t5/x\nPost two\n---\nnot a url\n")
    items = manual_paste.parse_blocks(text)
    assert [i.platform for i in items] == ["linkedin", "sap_community"]
    assert items[0].author_name == "Anna" and items[0].text == "Post one\nsecond line"
    assert items[0].url == "https://www.linkedin.com/posts/a_x"


def test_manual_paste_moves_processed_files(tmp_path, monkeypatch):
    monkeypatch.setattr(manual_paste, "inbox_dir", lambda client: tmp_path)
    (tmp_path / "week45.txt").write_text("https://x.com/a/status/1\nhello", encoding="utf-8")
    items = make_source("manual_paste", "acme").fetch([], date.today())
    assert len(items) == 1 and items[0].platform == "x"
    assert not (tmp_path / "week45.txt").exists()
    assert (tmp_path / "processed" / "week45.txt").exists()
#--------------------------------------------------------------#

# Tests: registry and query builder
def test_unknown_source_rejected():
    with pytest.raises(ValueError, match="Unknown source"):
        make_source("linkdin_search", "acme")


def test_build_queries_for_vizcorn():
    cfg = load_config("vizcorn")
    qs = build_queries(cfg, "linkedin_search")
    assert qs and all(x.text.startswith('site:linkedin.com/posts "') for x in qs)
    assert {x.language for x in qs} == {"en", "de"}
    assert build_queries(cfg, "manual_paste") == []            # no template = no queries
# Tests: topics limited to some sources, and the Reddit per-subreddit cap
def test_topic_sources_limit_queries():
    cfg = load_config("bacon")
    linkedin = {x.keyword for x in build_queries(cfg, "linkedin_search")}
    reddit = {x.keyword for x in build_queries(cfg, "reddit_search")}
    assert "marketing" in reddit and "marketing" not in linkedin      # Reddit-only topic
    assert "AI slop" in reddit and "AI slop" in linkedin              # shared topic


def test_reddit_has_its_own_cap():
    from suggester.pipeline.select import pick
    reddit = [{"platform": "reddit", "author_name": "r/marketing", "url": f"u{i}",
               "pillar": f"p{i}", "score": 100 - i} for i in range(5)]
    linkedin = [{"platform": "linkedin", "author_name": "Jane", "url": f"l{i}",
                 "pillar": f"q{i}", "score": 50 - i} for i in range(5)]
    chosen = pick(reddit + linkedin, 20, max_per_author=2, max_per_pillar=10, max_per_subreddit=4)
    assert sum(c["platform"] == "reddit" for c in chosen) == 4
    assert sum(c["platform"] == "linkedin" for c in chosen) == 2
    # without max_per_subreddit, Reddit falls back to max_per_author (Quartermaster's behaviour)
    assert sum(c["platform"] == "reddit" for c in pick(reddit, 20, 3, 10)) == 3
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#
