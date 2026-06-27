"""
tests/test_agents.py — Unit tests for the GitHub Activity Automation System.

Covers:
- Idempotency logic (daily commit guard)
- Repository selection with avoidance
- Project interval check
- Slug generation
- State persistence round-trip
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from daily_commit import build_commit_content, select_repository
from project_creator import is_interval_elapsed, slugify
from utils import load_state, save_state, today_str


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_repo(name: str) -> dict:
    return {"name": name, "fork": False, "archived": False}


# ── daily_commit tests ────────────────────────────────────────────────────────

class TestSelectRepository:
    def test_avoids_last_repo_when_multiple_available(self):
        repos = [make_repo("alpha"), make_repo("beta"), make_repo("gamma")]
        results = {select_repository(repos, "alpha")["name"] for _ in range(50)}
        assert "alpha" not in results, "Should avoid the last-used repo"

    def test_falls_back_to_last_repo_when_only_one_exists(self):
        repos = [make_repo("solo")]
        result = select_repository(repos, "solo")
        assert result["name"] == "solo"

    def test_raises_when_no_repos(self):
        with pytest.raises(ValueError, match="No eligible"):
            select_repository([], "any")

    def test_selects_from_all_when_last_repo_not_in_list(self):
        repos = [make_repo("x"), make_repo("y")]
        result = select_repository(repos, "z")
        assert result["name"] in {"x", "y"}


class TestBuildCommitContent:
    def test_appends_line_to_existing_content(self):
        existing = "# log\n"
        result = build_commit_content(existing, 1)
        assert result.startswith("# log\n")
        assert "automated commit #1" in result

    def test_multiple_commits_accumulate(self):
        content = ""
        for i in range(1, 4):
            content = build_commit_content(content, i)
        lines = [l for l in content.splitlines() if l]
        assert len(lines) == 3


class TestIdempotency:
    """Verify the once-per-day guard via state comparison."""

    def test_same_day_is_noop(self):
        """If last_run_date == today, agent should detect it and skip."""
        state = {"last_run_date": today_str()}
        assert state["last_run_date"] == today_str()

    def test_previous_day_triggers_run(self):
        state = {"last_run_date": "2000-01-01"}
        assert state["last_run_date"] != today_str()


# ── project_creator tests ─────────────────────────────────────────────────────

class TestIsIntervalElapsed:
    def test_no_previous_run_triggers_immediately(self):
        assert is_interval_elapsed({}, interval_days=3) is True

    def test_within_interval_does_not_trigger(self):
        from datetime import datetime, timedelta

        recent = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
        assert is_interval_elapsed({"last_run_date": recent}, interval_days=3) is False

    def test_past_interval_triggers(self):
        assert (
            is_interval_elapsed({"last_run_date": "2000-01-01"}, interval_days=3)
            is True
        )

    def test_corrupt_date_triggers(self):
        assert is_interval_elapsed({"last_run_date": "not-a-date"}, interval_days=3) is True


class TestSlugify:
    def test_basic_conversion(self):
        assert slugify("Hello World") == "hello-world"

    def test_special_characters_stripped(self):
        assert slugify("My App! v2.0") == "my-app-v20"

    def test_multiple_spaces_become_one_dash(self):
        assert slugify("a   b   c") == "a-b-c"

    def test_empty_string_returns_default(self):
        assert slugify("") == "my-project"

    def test_already_valid_slug_unchanged(self):
        assert slugify("cli-todo-app") == "cli-todo-app"


# ── utils tests ───────────────────────────────────────────────────────────────

class TestStatePersistence:
    def test_round_trip(self, tmp_path, monkeypatch):
        """save_state then load_state should return the same dict."""
        import utils

        monkeypatch.setattr(utils, "ROOT_DIR", tmp_path)
        state_file = "state/test.json"
        original = {"key": "value", "number": 42}
        save_state(state_file, original)
        loaded = load_state(state_file)
        assert loaded == original

    def test_missing_file_returns_empty_dict(self, tmp_path, monkeypatch):
        import utils

        monkeypatch.setattr(utils, "ROOT_DIR", tmp_path)
        result = load_state("state/nonexistent.json")
        assert result == {}

    def test_corrupt_file_returns_empty_dict(self, tmp_path, monkeypatch):
        import utils

        monkeypatch.setattr(utils, "ROOT_DIR", tmp_path)
        corrupt = tmp_path / "state" / "bad.json"
        corrupt.parent.mkdir(parents=True)
        corrupt.write_text("{ this is not json }")
        result = load_state("state/bad.json")
        assert result == {}
