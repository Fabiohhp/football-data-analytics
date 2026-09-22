"""Reading the dbt metrics layer.

The analyses read marts, not Gold. `snapshot.open_snapshot()` opens the Parquet
snapshot — the right entry point for profiling what is in the data — but every
headline number in a finished analysis comes from a tested dbt model (CLAUDE.md
§4), and those live in ``data/analytics.duckdb``.

    from football_analytics import marts

    m = marts.open_marts()
    m.df("SELECT * FROM mart_team_season WHERE season = '2024/25'")
    print(m.citation())

**It refuses to open a stale database.** The row count in ``stg_matches`` is
checked against ``fact_matches`` in the snapshot's ``manifest.json``, because the
failure this prevents is silent: re-exporting a snapshot without re-running
``dbt build`` leaves a database full of last week's numbers that answers every
query perfectly well.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import duckdb

from football_analytics import snapshot

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MARTS_PATH = REPO_ROOT / "data" / "analytics.duckdb"


class MartsMissingError(RuntimeError):
    """Raised when the metrics layer has not been built, or is out of date.

    Carries the command that fixes it, because the usual cause is a fresh clone
    or a snapshot that was re-exported without rebuilding.
    """


def marts_path() -> Path:
    """Where the DuckDB store is: ``ANALYTICS_DUCKDB`` if set, else ``data/analytics.duckdb``.

    A relative override resolves against the repository root, not the caller's
    working directory — the same rule and the same reason as
    :func:`snapshot.snapshot_dir`. pytest runs from the root and a notebook kernel
    runs from ``notebooks/``, so resolving against the cwd would make one setting
    mean two places and fail only in the notebook.
    """
    override = os.environ.get("ANALYTICS_DUCKDB")
    if not override:
        return DEFAULT_MARTS_PATH

    path = Path(override).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


@dataclass(frozen=True)
class Marts:
    """A read-only connection to the built metrics layer."""

    path: Path
    manifest: dict[str, Any]
    con: duckdb.DuckDBPyConnection

    def sql(self, query: str) -> duckdb.DuckDBPyRelation:
        return self.con.sql(query)

    def df(self, query: str) -> pd.DataFrame:
        return self.con.sql(query).df()

    def table(self, name: str) -> pd.DataFrame:
        return self.df(f"SELECT * FROM {name}")

    def citation(self) -> str:
        """The one line every analysis prints, naming the data behind its numbers.

        Deliberately cites the *snapshot*, not the database: the marts are a
        derivation, and the thing a reader needs in order to reproduce a figure is
        which export it came from (CLAUDE.md §7).
        """
        rng = self.manifest["match_date_range"]
        counts = self.manifest["tables"]
        return (
            f"dbt marts built from the Gold snapshot exported "
            f"{self.manifest['exported_at']}, matches {rng['min']} to {rng['max']} "
            f"({counts['fact_matches']['rows']:,} matches, "
            f"{counts['fact_player_events']['rows']:,} player events, "
            f"{counts['fact_shots']['rows']:,} shots)"
        )


def open_marts(path: Path | None = None, *, check_snapshot: bool = True) -> Marts:
    """Open the metrics layer read-only, and refuse it if it is stale.

    ``check_snapshot=False`` skips the freshness comparison. It exists for tests
    that build a database on purpose from something other than the current
    snapshot; an analysis should never pass it.
    """
    path = path or marts_path()
    if not path.exists():
        raise MartsMissingError(
            f"No metrics layer at {path}. Build it:\n"
            "  uv run dbt build --project-dir dbt --profiles-dir dbt"
        )

    manifest = snapshot.load_manifest()
    con = duckdb.connect(database=str(path), read_only=True)

    if check_snapshot:
        expected = manifest["tables"]["fact_matches"]["rows"]
        try:
            actual = con.execute("SELECT count(*) FROM stg_matches").fetchone()[0]
        except duckdb.Error as exc:  # pragma: no cover - only on a half-built db
            con.close()
            raise MartsMissingError(
                f"{path} exists but has no stg_matches table. Re-run:\n"
                "  uv run dbt build --project-dir dbt --profiles-dir dbt"
            ) from exc
        if actual != expected:
            con.close()
            raise MartsMissingError(
                f"The metrics layer is out of date with the snapshot: "
                f"stg_matches holds {actual:,} rows, but the snapshot's manifest "
                f"records {expected:,} matches. Re-run:\n"
                "  uv run dbt build --project-dir dbt --profiles-dir dbt"
            )

    return Marts(path=path, manifest=manifest, con=con)
