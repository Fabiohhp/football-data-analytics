"""The contract check is the repository's smoke alarm — so it gets tested.

If `diff_contract` ever returns an empty list for a real schema change, a wrong
number reaches a chart instead of the export failing. These tests pin that
behaviour down.
"""

from __future__ import annotations

import pytest

from football_analytics import gold


def col(name: str, type_: str = "bigint", nullable: bool = False) -> gold.Column:
    return gold.Column(name=name, type=type_, nullable=nullable)


class TestNormalizeType:
    def test_numeric_keeps_precision_and_scale(self):
        # A widened xG column changes what it can hold; the contract must see it.
        assert (
            gold.normalize_type("numeric", numeric_precision=8, numeric_scale=4) == "numeric(8,4)"
        )

    def test_numeric_without_scale_reads_as_zero(self):
        assert (
            gold.normalize_type("numeric", numeric_precision=6, numeric_scale=None)
            == "numeric(6,0)"
        )

    def test_varchar_keeps_length(self):
        assert gold.normalize_type("character varying", char_max_length=10) == "varchar(10)"

    def test_varchar_without_length(self):
        assert gold.normalize_type("character varying") == "varchar"

    def test_timestamptz_is_shortened(self):
        assert gold.normalize_type("timestamp with time zone") == "timestamptz"

    @pytest.mark.parametrize("plain", ["bigint", "smallint", "integer", "text", "date", "boolean"])
    def test_plain_types_pass_through(self, plain):
        assert gold.normalize_type(plain) == plain


class TestInformationSchemaParsing:
    def test_groups_rows_by_table(self):
        rows = [
            ("dim_teams", "team_key", "bigint", "NO", None, None, None),
            ("dim_teams", "canonical_name", "text", "NO", None, None, None),
            ("fact_shots", "xg", "numeric", "YES", 7, 4, None),
        ]
        tables = gold.columns_from_information_schema(rows)

        assert sorted(tables) == ["dim_teams", "fact_shots"]
        assert [c.name for c in tables["dim_teams"]] == ["team_key", "canonical_name"]
        assert tables["fact_shots"][0] == gold.Column("xg", "numeric(7,4)", True)

    def test_introspection_sql_covers_both_prefixes_and_excludes_staging(self):
        sql = gold.introspection_sql()

        for prefix in gold.TABLE_PREFIXES:
            assert f"c.table_name LIKE '{prefix}%'" in sql
        # `gold.staging` is Part 1's scratch space and must never be exported.
        assert "table_schema = 'gold'" in sql
        assert "staging" not in sql


class TestDiffContract:
    def test_identical_schemas_produce_no_problems(self):
        schema = {"dim_teams": [col("team_key"), col("canonical_name", "text")]}
        assert gold.diff_contract(schema, schema) == []

    def test_dropped_column_is_reported(self):
        expected = {"dim_teams": [col("team_key"), col("canonical_name", "text")]}
        actual = {"dim_teams": [col("team_key")]}

        problems = gold.diff_contract(expected, actual)

        assert len(problems) == 1
        assert "dim_teams.canonical_name" in problems[0]
        assert "dropped" in problems[0]

    def test_new_column_is_reported(self):
        # An addition is as interesting as a removal: Part 1 shipped something
        # and the analyses have not been told about it.
        expected = {"dim_teams": [col("team_key")]}
        actual = {"dim_teams": [col("team_key"), col("tla", "text", True)]}

        problems = gold.diff_contract(expected, actual)

        assert len(problems) == 1
        assert "dim_teams.tla" in problems[0]
        assert "not in the contract" in problems[0]

    def test_retyped_column_is_reported(self):
        expected = {"fact_shots": [col("xg", "numeric(7,4)", True)]}
        actual = {"fact_shots": [col("xg", "numeric(10,2)", True)]}

        problems = gold.diff_contract(expected, actual)

        assert problems == ["fact_shots.xg: type changed numeric(7,4) -> numeric(10,2)"]

    def test_nullability_change_is_reported_both_ways(self):
        strict = {"fact_matches": [col("match_date", "date", nullable=False)]}
        loose = {"fact_matches": [col("match_date", "date", nullable=True)]}

        assert "not null -> nullable" in gold.diff_contract(strict, loose)[0]
        assert "nullable -> not null" in gold.diff_contract(loose, strict)[0]

    def test_column_order_alone_is_not_a_change(self):
        # dim_stadiums.address really does sit after loaded_at in the warehouse,
        # because Part 1 added it with ALTER TABLE. Order is not the contract.
        expected = {"dim_stadiums": [col("a"), col("b"), col("c")]}
        actual = {"dim_stadiums": [col("c"), col("a"), col("b")]}

        assert gold.diff_contract(expected, actual) == []

    def test_missing_and_extra_tables_are_reported(self):
        expected = {"dim_teams": [col("team_key")], "dim_gone": [col("k")]}
        actual = {"dim_teams": [col("team_key")], "fact_new": [col("k")]}

        problems = gold.diff_contract(expected, actual)

        assert any("dim_gone" in p and "missing from Gold" in p for p in problems)
        assert any("fact_new" in p and "not in the contract" in p for p in problems)


class TestCommittedContract:
    def test_covers_the_whole_star_schema(self):
        contract = gold.load_contract()

        assert sorted(contract) == [
            "dim_players",
            "dim_referees",
            "dim_stadiums",
            "dim_teams",
            "fact_matches",
            "fact_player_events",
            "fact_shots",
        ]

    def test_documented_traps_are_in_the_contract(self):
        contract = gold.load_contract()
        columns = {t: {c.name: c for c in cols} for t, cols in contract.items()}

        # Trap 1: the durable player key, alongside the SCD2 surrogate.
        assert "understat_player_id" in columns["dim_players"]
        assert "valid_from" in columns["dim_players"]
        # Trap 2: a player's club in a match comes from the fact, not the dim.
        assert "team_key" in columns["fact_player_events"]
        # Trap 4: match_key really is nullable in both event facts.
        assert columns["fact_player_events"]["match_key"].nullable
        assert columns["fact_shots"]["match_key"].nullable
        # Trap 5: only fact_matches carries season.
        assert "season" in columns["fact_matches"]
        assert "season" not in columns["fact_player_events"]
        assert "season" not in columns["fact_shots"]
        # Trap 9: no possession/passes/tackles anywhere.
        for table in contract:
            for absent in ("possession", "passes", "tackles"):
                assert absent not in columns[table], f"{table}.{absent} appeared in Gold"
        # Trap 10: normalized shot coordinates.
        assert columns["fact_shots"]["x"].type.startswith("numeric")
        assert columns["fact_shots"]["y"].type.startswith("numeric")

    def test_round_trips_through_dump_and_load(self, tmp_path):
        original = gold.load_contract()
        path = tmp_path / "contract.json"

        gold.dump_contract(original, path)

        assert gold.load_contract(path) == original
