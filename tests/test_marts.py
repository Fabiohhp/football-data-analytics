"""The metrics-layer loader.

The behaviour worth testing is not that DuckDB can run a query, but the two
guardrails: a **relative path resolves against the repository root** rather than
the caller's working directory, and the loader **refuses a database that is out of
date with the snapshot**. The second one prevents a silent failure — a notebook
answering every query correctly from last week's numbers.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from football_analytics import marts

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestMartsPath:
    def test_defaults_to_the_data_directory(self, monkeypatch):
        monkeypatch.delenv("ANALYTICS_DUCKDB", raising=False)
        assert marts.marts_path() == REPO_ROOT / "data" / "analytics.duckdb"

    def test_a_relative_override_resolves_against_the_repo_not_the_cwd(self, monkeypatch, tmp_path):
        # The same rule as snapshot.snapshot_dir(), and for the same reason: pytest
        # runs from the root and a notebook kernel runs from notebooks/.
        monkeypatch.setenv("ANALYTICS_DUCKDB", "data/somewhere.duckdb")
        monkeypatch.chdir(tmp_path)
        assert marts.marts_path() == (REPO_ROOT / "data" / "somewhere.duckdb").resolve()

    def test_an_absolute_override_is_used_as_given(self, monkeypatch, tmp_path):
        target = tmp_path / "elsewhere.duckdb"
        monkeypatch.setenv("ANALYTICS_DUCKDB", str(target))
        assert marts.marts_path() == target


class TestOpenMarts:
    def test_a_missing_database_names_the_command_that_builds_it(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANALYTICS_DUCKDB", str(tmp_path / "nothing.duckdb"))
        with pytest.raises(marts.MartsMissingError, match="dbt build"):
            marts.open_marts()

    def test_a_database_with_no_models_is_rejected(self, monkeypatch, tmp_path):
        path = tmp_path / "empty.duckdb"
        duckdb.connect(str(path)).close()
        monkeypatch.setenv("ANALYTICS_DUCKDB", str(path))

        with pytest.raises(marts.MartsMissingError, match="no stg_matches"):
            marts.open_marts()

    def test_a_stale_database_is_rejected_and_says_how_stale(self, monkeypatch, tmp_path):
        """The guardrail that matters: right shape, wrong data."""
        path = tmp_path / "stale.duckdb"
        con = duckdb.connect(str(path))
        con.execute("CREATE TABLE stg_matches AS SELECT 1 AS match_key")
        con.close()
        monkeypatch.setenv("ANALYTICS_DUCKDB", str(path))

        with pytest.raises(marts.MartsMissingError, match="out of date"):
            marts.open_marts()

    def test_the_freshness_check_can_be_waived(self, monkeypatch, tmp_path):
        path = tmp_path / "stale.duckdb"
        con = duckdb.connect(str(path))
        con.execute("CREATE TABLE stg_matches AS SELECT 1 AS match_key")
        con.close()
        monkeypatch.setenv("ANALYTICS_DUCKDB", str(path))

        opened = marts.open_marts(check_snapshot=False)
        assert opened.sql("SELECT count(*) FROM stg_matches").fetchone()[0] == 1

    def test_citation_names_the_snapshot_not_the_database(self, monkeypatch, tmp_path):
        # An analysis is reproducible from the snapshot it was built on, so that is
        # what the citation has to name (CLAUDE.md §7).
        path = tmp_path / "ok.duckdb"
        con = duckdb.connect(str(path))
        con.execute("CREATE TABLE stg_matches AS SELECT 1 AS match_key")
        con.close()
        monkeypatch.setenv("ANALYTICS_DUCKDB", str(path))

        citation = marts.open_marts(check_snapshot=False).citation()
        assert "Gold snapshot exported" in citation
        assert "matches" in citation and "shots" in citation
