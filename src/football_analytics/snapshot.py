"""Reading the Gold snapshot.

Every notebook, test and script starts here, so that "which data is this?" has
exactly one answer: the manifest written next to the Parquet files by
``scripts/export_gold.py``.

    from football_analytics import snapshot

    snap = snapshot.open_snapshot()
    snap.sql("SELECT count(*) FROM fact_matches").df()
    print(snap.citation())   # paste into an analysis

CI points this at ``tests/fixtures/gold`` through ``GOLD_SNAPSHOT_DIR``, so the
same code runs against the synthetic fixture without real data.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import duckdb

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SNAPSHOT_DIR = REPO_ROOT / "data" / "gold"
MANIFEST_NAME = "manifest.json"


def snapshot_dir() -> Path:
    """Where the snapshot lives: ``GOLD_SNAPSHOT_DIR`` if set, else ``data/gold``.

    **A relative ``GOLD_SNAPSHOT_DIR`` is relative to the repository root, not to
    the current directory.** The setting is repo-scoped, and the processes that
    read it do not share a working directory: pytest runs from the root, while a
    notebook kernel — under Jupyter and under nbclient in CI alike — runs from
    ``notebooks/``. Resolving against the caller's cwd would make the same
    ``GOLD_SNAPSHOT_DIR=tests/fixtures/gold`` mean two different places and fail
    only in the notebook, with an error that points at the snapshot rather than
    at the path.
    """
    override = os.environ.get("GOLD_SNAPSHOT_DIR")
    if not override:
        return DEFAULT_SNAPSHOT_DIR

    path = Path(override).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


class SnapshotMissingError(RuntimeError):
    """Raised when the snapshot has not been exported yet.

    Carries the command to fix it, because the usual cause is a fresh clone.
    """


@dataclass(frozen=True)
class Snapshot:
    """A read-only DuckDB view over one exported Gold snapshot."""

    directory: Path
    manifest: dict[str, Any]
    con: duckdb.DuckDBPyConnection

    # --- provenance -------------------------------------------------------

    @property
    def exported_at(self) -> str:
        return self.manifest["exported_at"]

    @property
    def first_match_date(self) -> date:
        return date.fromisoformat(self.manifest["match_date_range"]["min"])

    @property
    def last_match_date(self) -> date:
        return date.fromisoformat(self.manifest["match_date_range"]["max"])

    @property
    def row_counts(self) -> dict[str, int]:
        return {table: spec["rows"] for table, spec in self.manifest["tables"].items()}

    def citation(self) -> str:
        """One line naming the data behind a number, for every analysis to print.

        CLAUDE.md §7 asks every result to state the snapshot's ``match_date``
        range; this is that sentence.
        """
        return (
            f"Gold snapshot exported {self.exported_at}, "
            f"matches {self.first_match_date} to {self.last_match_date} "
            f"({self.row_counts.get('fact_matches', 0):,} matches, "
            f"{self.row_counts.get('fact_player_events', 0):,} player events, "
            f"{self.row_counts.get('fact_shots', 0):,} shots)"
        )

    # --- querying ---------------------------------------------------------

    def sql(self, query: str) -> duckdb.DuckDBPyRelation:
        """Run SQL against the snapshot. Each Gold table is a view of its name."""
        return self.con.sql(query)

    def df(self, query: str) -> pd.DataFrame:
        """Run SQL and return a pandas DataFrame."""
        return self.con.sql(query).df()

    def table(self, name: str) -> pd.DataFrame:
        """Read one whole Gold table into pandas."""
        return self.df(f"SELECT * FROM {name}")


def load_manifest(directory: Path | None = None) -> dict[str, Any]:
    """Read ``manifest.json``, or explain how to create it."""
    directory = directory or snapshot_dir()
    path = directory / MANIFEST_NAME
    if not path.exists():
        raise SnapshotMissingError(
            f"No Gold snapshot at {directory}. Start Part 1's database and export it:\n"
            "  (cd ../football-data-engineering && docker compose up -d postgres)\n"
            "  uv run python scripts/export_gold.py"
        )
    return json.loads(path.read_text())


def open_snapshot(directory: Path | None = None) -> Snapshot:
    """Open the snapshot and register one view per Gold table.

    The connection is in-memory: nothing here can modify the snapshot, and the
    Parquet files stay the only copy of the data.
    """
    directory = directory or snapshot_dir()
    manifest = load_manifest(directory)

    con = duckdb.connect(database=":memory:")
    for table, spec in manifest["tables"].items():
        parquet = directory / spec["file"]
        if not parquet.exists():
            raise SnapshotMissingError(
                f"{MANIFEST_NAME} lists {spec['file']} but it is not in {directory}. "
                "Re-run scripts/export_gold.py."
            )
        # The path is interpolated because DuckDB does not accept prepared
        # parameters inside a CREATE VIEW body; it comes from the manifest, not
        # from user input, and single quotes are escaped regardless.
        literal = str(parquet).replace("'", "''")
        con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{literal}')")
    return Snapshot(directory=directory, manifest=manifest, con=con)
