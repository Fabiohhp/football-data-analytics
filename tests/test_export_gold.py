"""The export refuses an empty warehouse before it touches the current snapshot."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import duckdb
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "export_gold", REPO_ROOT / "scripts" / "export_gold.py"
)
export_gold = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_gold)


def attach_warehouse(con: duckdb.DuckDBPyConnection, matches: int) -> None:
    """Stand in for Part 1's PostgreSQL with a Gold schema holding ``matches`` rows."""
    alias = export_gold.ATTACH_ALIAS
    con.execute(f"ATTACH ':memory:' AS {alias}")
    con.execute(f"CREATE SCHEMA {alias}.gold")
    con.execute(
        f"CREATE TABLE {alias}.gold.fact_matches AS SELECT range AS match_key FROM range({matches})"
    )


def test_refuses_a_warehouse_with_no_matches():
    con = duckdb.connect()
    attach_warehouse(con, matches=0)

    with pytest.raises(export_gold.EmptyWarehouse, match="Part 1 has to load data"):
        export_gold.check_has_matches(con)


def test_accepts_a_warehouse_with_matches():
    con = duckdb.connect()
    attach_warehouse(con, matches=1)

    export_gold.check_has_matches(con)


def test_an_empty_warehouse_leaves_the_current_snapshot_in_place(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    parquet = tmp_path / "fact_matches.parquet"
    manifest.write_text("{}")
    parquet.write_bytes(b"current snapshot")
    monkeypatch.setattr(export_gold, "attach_read_only", lambda con: attach_warehouse(con, 0))
    monkeypatch.setattr(export_gold, "live_schema", lambda con: {})
    monkeypatch.setattr(export_gold, "check_contract", lambda actual: None)

    with pytest.raises(export_gold.EmptyWarehouse):
        export_gold.main(["--out", str(tmp_path)])

    assert manifest.read_text() == "{}"
    assert parquet.read_bytes() == b"current snapshot"
