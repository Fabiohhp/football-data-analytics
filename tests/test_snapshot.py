"""The snapshot loader: provenance, views, and a useful error when it is missing."""

from __future__ import annotations

from pathlib import Path

import pytest

from football_analytics import gold, snapshot


class TestSnapshotDir:
    def test_env_override_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GOLD_SNAPSHOT_DIR", str(tmp_path))
        assert snapshot.snapshot_dir() == tmp_path.resolve()

    def test_defaults_to_data_gold(self, monkeypatch):
        monkeypatch.delenv("GOLD_SNAPSHOT_DIR", raising=False)
        assert snapshot.snapshot_dir() == snapshot.DEFAULT_SNAPSHOT_DIR


class TestMissingSnapshot:
    def test_raises_with_the_command_that_fixes_it(self, tmp_path):
        # The usual cause is a fresh clone, so the error has to teach.
        with pytest.raises(snapshot.SnapshotMissingError) as excinfo:
            snapshot.load_manifest(tmp_path)

        message = str(excinfo.value)
        assert "export_gold.py" in message
        assert "docker compose up -d postgres" in message

    def test_raises_when_the_manifest_lists_a_missing_parquet(self, tmp_path):
        (tmp_path / "manifest.json").write_text(
            '{"exported_at": "x", "match_date_range": {"min": "2024-08-15", "max": "2026-09-19"},'
            ' "tables": {"fact_matches": {"file": "fact_matches.parquet", "rows": 1}}}'
        )

        with pytest.raises(snapshot.SnapshotMissingError, match="not in"):
            snapshot.open_snapshot(tmp_path)


class TestOpenSnapshot:
    def test_every_contract_table_is_queryable(self, snap):
        for table in gold.load_contract():
            rows = snap.sql(f"SELECT count(*) FROM {table}").fetchone()[0]
            assert rows > 0, f"{table} is empty in the fixture"

    def test_row_counts_agree_with_the_manifest(self, snap):
        for table, expected in snap.row_counts.items():
            actual = snap.sql(f"SELECT count(*) FROM {table}").fetchone()[0]
            assert actual == expected, f"{table}: manifest says {expected}, Parquet has {actual}"

    def test_provenance_is_exposed(self, snap):
        assert snap.first_match_date.isoformat() == "2024-08-17"
        assert snap.last_match_date.isoformat() == "2025-08-31"
        assert snap.exported_at.startswith("2026-09-20")

    def test_citation_names_the_window_and_the_volume(self, snap):
        # CLAUDE.md §7: every result states the snapshot's match_date range.
        citation = snap.citation()

        assert "2024-08-17" in citation
        assert "2025-08-31" in citation
        assert "matches" in citation and "shots" in citation

    def test_is_read_only(self, snap):
        # The Parquet files are the only copy of the data. Each table is a view,
        # so DuckDB rejects the write outright rather than buffering it.
        with pytest.raises(Exception, match="(?i)can only delete from base table"):
            snap.sql("DELETE FROM fact_matches")
        with pytest.raises(Exception, match="(?i)can only update base table"):
            snap.sql("UPDATE fact_matches SET home_goals = 99")

    def test_table_helper_returns_a_dataframe(self, snap):
        teams = snap.table("dim_teams")
        assert "canonical_name" in teams.columns
        assert len(teams) == snap.row_counts["dim_teams"]

    def test_directory_is_recorded(self, snap):
        assert snap.directory == Path(snapshot.snapshot_dir())
