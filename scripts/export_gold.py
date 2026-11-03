"""Export Part 1's Gold star schema to a pinned Parquet snapshot.

    uv run python scripts/export_gold.py

This is the only code in this repository that talks to Part 1's PostgreSQL, and
it does so through DuckDB's ``postgres`` extension with a ``READ_ONLY`` attach —
writing to the warehouse from here is not a policy, it is impossible.

What it does, in order:

1. attaches the warehouse read-only;
2. introspects ``gold.dim_*`` / ``gold.fact_*`` and compares the result against
   ``contracts/gold_columns.json``, failing on any difference;
3. copies each table verbatim to ``data/gold/<table>.parquet`` — no filtering,
   no renaming, no derived columns (that is dbt's job);
4. writes ``data/gold/manifest.json``: export time, row count per table and the
   ``match_date`` range every analysis cites.

Flags:
  --write-contract   Rewrite contracts/gold_columns.json from the live schema
                     instead of checking against it. Use this when Part 1 has
                     deliberately changed Gold, then commit the diff on its own
                     and review the analyses it touches.
  --out DIR          Write somewhere other than data/gold.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb
from dotenv import load_dotenv

# Import the shared package whether or not the repo is installed.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from football_analytics import gold  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "data" / "gold"
ATTACH_ALIAS = "gold_pg"


class ContractDrift(RuntimeError):
    """Gold no longer matches the committed contract."""


class EmptyWarehouse(RuntimeError):
    """Gold holds no matches, so exporting it would replace a good snapshot with nothing."""


def connection_string() -> str:
    """Build a libpq connection string from the GOLD_PG_* environment."""
    load_dotenv(REPO_ROOT / ".env")

    settings = {
        "host": os.environ.get("GOLD_PG_HOST", "localhost"),
        "port": os.environ.get("GOLD_PG_PORT", "5432"),
        "dbname": os.environ.get("GOLD_PG_DB", "football_dw"),
        "user": os.environ.get("GOLD_PG_USER", "football"),
        "password": os.environ.get("GOLD_PG_PASSWORD", ""),
    }
    if not settings["password"]:
        raise SystemExit("GOLD_PG_PASSWORD is not set. Copy .env.example to .env and fill it in.")
    # libpq keyword/value quoting: wrap every value, escape backslash and quote.
    parts = []
    for key, value in settings.items():
        escaped = str(value).replace("\\", "\\\\").replace("'", "\\'")
        parts.append(f"{key}='{escaped}'")
    return " ".join(parts)


def attach_read_only(con: duckdb.DuckDBPyConnection) -> None:
    """Attach the warehouse read-only, so this script cannot write to Part 1."""
    con.execute("INSTALL postgres")
    con.execute("LOAD postgres")
    # Two layers of quoting: the libpq values are already single-quoted, so every
    # quote has to be doubled again to survive the surrounding DuckDB literal.
    dsn = connection_string().replace("'", "''")
    con.execute(f"ATTACH '{dsn}' AS {ATTACH_ALIAS} (TYPE postgres, READ_ONLY)")


def live_schema(con: duckdb.DuckDBPyConnection) -> dict[str, list[gold.Column]]:
    """Introspect the attached warehouse's Gold star schema."""
    query = gold.introspection_sql().replace("'", "''")
    rows = con.execute(f"SELECT * FROM postgres_query('{ATTACH_ALIAS}', '{query}')").fetchall()
    if not rows:
        raise ContractDrift(
            "No gold.dim_* or gold.fact_* tables found. Is this the right database, "
            "and has Part 1's DDL run?"
        )
    return gold.columns_from_information_schema(rows)


def check_contract(actual: dict[str, list[gold.Column]]) -> None:
    """Fail loudly, and specifically, when Gold has drifted."""
    problems = gold.diff_contract(gold.load_contract(), actual)
    if problems:
        listing = "\n".join(f"  - {p}" for p in problems)
        raise ContractDrift(
            "Gold does not match contracts/gold_columns.json:\n"
            f"{listing}\n\n"
            "Part 1's schema changed. Review the analyses this affects, then re-run "
            "with --write-contract and commit the contract diff on its own."
        )


def check_has_matches(con: duckdb.DuckDBPyConnection) -> None:
    """Refuse an empty warehouse, before clear_previous() deletes the current snapshot."""
    matches = con.execute(f"SELECT count(*) FROM {ATTACH_ALIAS}.gold.fact_matches").fetchone()[0]
    if not matches:
        raise EmptyWarehouse(
            "gold.fact_matches is empty, so there is nothing to export and the current "
            "snapshot was left as it is. Part 1 has to load data first (its README, 'Run it')."
        )


def clear_previous(out_dir: Path) -> None:
    """Remove a previous snapshot so no stale table can survive a rename."""
    for stale in sorted([*out_dir.glob("*.parquet"), *out_dir.glob("manifest.json")]):
        print(f"  removing previous {stale.name}")
        stale.unlink()


def export_tables(
    con: duckdb.DuckDBPyConnection, tables: list[str], out_dir: Path
) -> dict[str, dict[str, object]]:
    """Copy each Gold table to Parquet verbatim and record what was written."""
    written: dict[str, dict[str, object]] = {}
    for table in tables:
        target = out_dir / f"{table}.parquet"
        con.execute(
            f"COPY (SELECT * FROM {ATTACH_ALIAS}.gold.{table}) "
            f"TO '{target}' (FORMAT PARQUET, COMPRESSION zstd)"
        )
        rows = con.execute(f"SELECT count(*) FROM read_parquet('{target}')").fetchone()[0]
        written[table] = {
            "file": target.name,
            "rows": rows,
            "bytes": target.stat().st_size,
        }
        print(f"  {table:<20} {rows:>9,} rows  {target.stat().st_size / 1e6:>7.1f} MB")
    return written


def match_date_range(con: duckdb.DuckDBPyConnection, out_dir: Path) -> dict[str, str]:
    """The snapshot's coverage window, read back from what was just written."""
    parquet = out_dir / "fact_matches.parquet"
    lo, hi = con.execute(
        f"SELECT min(match_date), max(match_date) FROM read_parquet('{parquet}')"
    ).fetchone()
    return {"min": lo.isoformat(), "max": hi.isoformat()}


def write_manifest(
    out_dir: Path,
    tables: dict[str, dict[str, object]],
    date_range: dict[str, str],
    source: str,
) -> Path:
    """Write the provenance file that every analysis cites."""
    manifest = {
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": source,
        "duckdb_version": duckdb.__version__,
        "contract": "contracts/gold_columns.json",
        "match_date_range": date_range,
        "tables": dict(sorted(tables.items())),
    }
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-contract",
        action="store_true",
        help="rewrite the contract from the live schema instead of checking it",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    args = parser.parse_args(argv)

    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(database=":memory:")
    print(f"Attaching {os.environ.get('GOLD_PG_DB', 'football_dw')} READ_ONLY ...")
    attach_read_only(con)

    actual = live_schema(con)
    tables = sorted(actual)

    if args.write_contract:
        gold.dump_contract(actual)
        print(
            f"Wrote {gold.CONTRACT_PATH.relative_to(REPO_ROOT)} from the live schema "
            f"({len(tables)} tables). Commit this on its own."
        )
        return 0

    check_contract(actual)
    print(f"Contract OK: {len(tables)} tables match contracts/gold_columns.json")
    check_has_matches(con)

    clear_previous(out_dir)
    print(f"Exporting to {out_dir} ...")
    written = export_tables(con, tables, out_dir)

    manifest = write_manifest(
        out_dir,
        written,
        match_date_range(con, out_dir),
        source=(
            f"{os.environ.get('GOLD_PG_USER')}@{os.environ.get('GOLD_PG_HOST')}"
            f":{os.environ.get('GOLD_PG_PORT')}/{os.environ.get('GOLD_PG_DB')} (gold schema)"
        ),
    )
    total = sum(int(spec["rows"]) for spec in written.values())
    print(f"Wrote {manifest.name}: {total:,} rows across {len(written)} tables")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ContractDrift, EmptyWarehouse) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
