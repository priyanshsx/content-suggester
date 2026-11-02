#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
from datetime import date

import pytest

from suggester import cli
from suggester.core import db
from suggester.pipeline.context import iso_week
#--------------------------------------------------------------#

# Setup: temporary database with vizcorn registered
@pytest.fixture
def registered(tmp_path, monkeypatch):
    monkeypatch.setenv("SUGGESTER_DB_PATH", str(tmp_path / "test.db"))
    with db.connect() as conn:
        db.init_db(conn)
        db.upsert(conn, "clients", {"name": "vizcorn", "config_path": "config/clients/vizcorn",
                                    "created_at": db.now_iso()}, ["name"])
#--------------------------------------------------------------#

# Tests: happy path
def test_all_stages_run(registered, monkeypatch):
    ran = []
    for name in cli.STAGES:
        monkeypatch.setitem(cli.STAGES, name, lambda ctx, n=name: ran.append((n, ctx.week)))
    assert cli.main(["--client", "vizcorn", "--stage", "all", "--week", "2026-W45"]) == 0
    assert ran == [(n, "2026-W45") for n in cli.ALL_ORDER]


def test_single_stage_runs(registered):
    assert cli.main(["--client", "vizcorn", "--stage", "collect", "--dry-run"]) == 0
#--------------------------------------------------------------#

# Tests: clear failures
def test_unregistered_client_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("SUGGESTER_DB_PATH", str(tmp_path / "empty.db"))
    assert cli.main(["--client", "vizcorn"]) == 1


def test_missing_config_fails(registered):
    assert cli.main(["--client", "no_such_client"]) == 1


def test_feedback_needs_file(registered):
    assert cli.main(["--client", "vizcorn", "--stage", "import-feedback"]) == 2


def test_unknown_stage_rejected(registered):
    with pytest.raises(SystemExit):
        cli.main(["--client", "vizcorn", "--stage", "colect"])
#--------------------------------------------------------------#

# Tests: week label
def test_iso_week():
    assert iso_week(date(2026, 11, 2)) == "2026-W45"
    assert iso_week(date(2027, 1, 1)) == "2026-W53"
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#
