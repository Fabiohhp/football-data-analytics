"""The Gold contract: what Part 1 promises this repository, and drift detection.

Part 1 owns ``gold.dim_*`` and ``gold.fact_*`` and may change them. This module
turns "what does Gold look like right now" into a comparable structure, so
``scripts/export_gold.py`` can refuse to build a snapshot from a schema this
repository was not written against (CLAUDE.md §4).

The rule is deliberately strict: *any* difference fails. A new column is as
interesting as a removed one, because it means Part 1 shipped something and the
analyses have not been told about it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Only the star schema is a contract. `gold.staging` is Part 1's per-run scratch
# space, and reading it from here is forbidden (CLAUDE.md §15).
TABLE_PREFIXES = ("dim_", "fact_")

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "contracts" / "gold_columns.json"


@dataclass(frozen=True)
class Column:
    """One column of a Gold table, reduced to what the contract cares about."""

    name: str
    type: str
    nullable: bool

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "type": self.type, "nullable": self.nullable}


def normalize_type(
    data_type: str,
    *,
    numeric_precision: int | None = None,
    numeric_scale: int | None = None,
    char_max_length: int | None = None,
) -> str:
    """Render a PostgreSQL ``information_schema`` type as a short stable string.

    Precision and scale are part of the contract, not decoration: a widened
    ``NUMERIC(8,4)`` would change what an xG column can hold, and a reviewer
    should see that in a diff rather than in a rounded chart.
    """
    if data_type == "numeric" and numeric_precision is not None:
        return f"numeric({numeric_precision},{numeric_scale or 0})"
    if data_type == "character varying":
        return f"varchar({char_max_length})" if char_max_length else "varchar"
    if data_type == "timestamp with time zone":
        return "timestamptz"
    if data_type == "timestamp without time zone":
        return "timestamp"
    return data_type


def columns_from_information_schema(rows: list[tuple[Any, ...]]) -> dict[str, list[Column]]:
    """Group ``information_schema.columns`` rows into ``{table: [Column, ...]}``.

    Rows arrive as ``(table_name, column_name, data_type, is_nullable,
    numeric_precision, numeric_scale, character_maximum_length)`` ordered by
    table then ordinal position — the shape of :data:`INTROSPECTION_SQL`.
    """
    tables: dict[str, list[Column]] = {}
    for table, column, data_type, is_nullable, precision, scale, length in rows:
        tables.setdefault(table, []).append(
            Column(
                name=column,
                type=normalize_type(
                    data_type,
                    numeric_precision=precision,
                    numeric_scale=scale,
                    char_max_length=length,
                ),
                nullable=(is_nullable == "YES"),
            )
        )
    return tables


# Kept next to the parser it feeds. `%` patterns come from TABLE_PREFIXES so the
# two can never drift apart.
INTROSPECTION_SQL = """
    SELECT c.table_name,
           c.column_name,
           c.data_type,
           c.is_nullable,
           c.numeric_precision,
           c.numeric_scale,
           c.character_maximum_length
    FROM information_schema.columns c
    JOIN information_schema.tables t
      ON t.table_schema = c.table_schema AND t.table_name = c.table_name
    WHERE c.table_schema = 'gold'
      AND t.table_type = 'BASE TABLE'
      AND ({prefix_filter})
    ORDER BY c.table_name, c.ordinal_position
"""


def introspection_sql() -> str:
    """The introspection query, with the table-prefix filter spelled out."""
    prefix_filter = " OR ".join(f"c.table_name LIKE '{p}%'" for p in TABLE_PREFIXES)
    return INTROSPECTION_SQL.format(prefix_filter=prefix_filter)


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, list[Column]]:
    """Read the committed contract file."""
    payload = json.loads(path.read_text())
    return {
        table: [Column(c["name"], c["type"], c["nullable"]) for c in spec["columns"]]
        for table, spec in payload["tables"].items()
    }


def dump_contract(tables: dict[str, list[Column]], path: Path = CONTRACT_PATH) -> None:
    """Write the contract file. Only ever called behind an explicit flag."""
    payload = {
        "_comment": (
            "Expected columns and types of Part 1's Gold star schema. "
            "scripts/export_gold.py fails on any difference against the live "
            "warehouse. Regenerate with --write-contract and commit the diff "
            "deliberately: it means the analyses need reviewing."
        ),
        "tables": {
            table: {"columns": [c.as_dict() for c in columns]}
            for table, columns in sorted(tables.items())
        },
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")


def diff_contract(expected: dict[str, list[Column]], actual: dict[str, list[Column]]) -> list[str]:
    """Return one human-readable line per difference; empty means Gold matches.

    Column order is not compared — only presence, type and nullability. A
    reordered ``SELECT *`` is not a contract change, but a retyped column is.
    """
    problems: list[str] = []

    for table in sorted(set(expected) - set(actual)):
        problems.append(f"{table}: table is in the contract but missing from Gold")
    for table in sorted(set(actual) - set(expected)):
        problems.append(f"{table}: table is in Gold but not in the contract (new Part 1 table?)")

    for table in sorted(set(expected) & set(actual)):
        exp = {c.name: c for c in expected[table]}
        act = {c.name: c for c in actual[table]}
        for name in sorted(set(exp) - set(act)):
            problems.append(
                f"{table}.{name}: dropped from Gold (contract expects {exp[name].type})"
            )
        for name in sorted(set(act) - set(exp)):
            problems.append(f"{table}.{name}: new in Gold ({act[name].type}), not in the contract")
        for name in sorted(set(exp) & set(act)):
            if exp[name].type != act[name].type:
                problems.append(
                    f"{table}.{name}: type changed {exp[name].type} -> {act[name].type}"
                )
            if exp[name].nullable != act[name].nullable:
                was, now = (
                    ("nullable", "not null") if exp[name].nullable else ("not null", "nullable")
                )
                problems.append(f"{table}.{name}: nullability changed {was} -> {now}")

    return problems
