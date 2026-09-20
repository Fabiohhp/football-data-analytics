"""The fixture has to keep matching the contract, and keep its traps.

CI runs everything against `tests/fixtures/gold`, so if the fixture drifts away
from the real Gold schema, CI starts proving the wrong thing. And if the traps
from CLAUDE.md §5 fall out of it, every model that mishandles one goes green.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

from football_analytics import gold

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))

import make_gold_fixture as fixture_builder  # noqa: E402

# DuckDB accepts short type names but reports the spelled-out form, so the two
# sides of the schema comparison are normalized before being compared.
DUCKDB_TYPE_ALIASES = {"TIMESTAMPTZ": "TIMESTAMP WITH TIME ZONE"}


def canonical(duckdb_type_name: str) -> str:
    return DUCKDB_TYPE_ALIASES.get(duckdb_type_name, duckdb_type_name)


class TestFixtureMatchesContract:
    def test_every_column_has_the_contract_type(self, snap):
        """A stale fixture is worse than no fixture: regenerate it when this fails."""
        contract = gold.load_contract()

        for table, columns in contract.items():
            actual = {
                name: canonical(type_)
                for name, type_ in snap.sql(
                    f"SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM {table})"
                ).fetchall()
            }
            expected = {c.name: canonical(fixture_builder.duckdb_type(c.type)) for c in columns}

            assert actual == expected, (
                f"{table} in the fixture no longer matches the contract. "
                "Re-run: uv run python tests/fixtures/make_gold_fixture.py"
            )

    def test_it_is_small_enough_to_commit(self, snap):
        total_bytes = sum(spec["bytes"] for spec in snap.manifest["tables"].values())
        assert total_bytes < 200_000, "the fixture is meant to be tiny"


class TestTrapsArePresent:
    """One test per trap in CLAUDE.md §5 that the fixture is supposed to carry."""

    def test_trap_1_and_2_one_player_has_two_scd2_versions(self, snap):
        versions = snap.df(
            "SELECT player_key, current_team_key, valid_from, valid_to, is_current "
            "FROM dim_players WHERE understat_player_id = 103 ORDER BY valid_from"
        )

        assert len(versions) == 2, "the transferred player must have two versions"
        assert versions["current_team_key"].tolist() == [3, 1], "the club must change"
        assert versions["is_current"].tolist() == [False, True]
        # Grouping this player's career by player_key splits it; by
        # understat_player_id it does not.
        by_key = snap.sql(
            "SELECT count(DISTINCT player_key) FROM fact_player_events "
            "WHERE understat_player_id = 103"
        ).fetchone()[0]
        assert by_key == 2

    def test_trap_3_every_dimension_has_an_unknown_member_at_key_zero(self, snap):
        for table, key in (
            ("dim_teams", "team_key"),
            ("dim_players", "player_key"),
            ("dim_referees", "referee_key"),
            ("dim_stadiums", "stadium_key"),
        ):
            name_column = {
                "dim_teams": "canonical_name",
                "dim_players": "player_name",
                "dim_referees": "referee_name",
                "dim_stadiums": "stadium_name",
            }[table]
            name = snap.sql(f"SELECT {name_column} FROM {table} WHERE {key} = 0").fetchone()
            assert name is not None and name[0] == "Unknown", f"{table} has no Unknown member"

    def test_trap_3_a_match_points_at_the_unknown_referee(self, snap):
        unknown = snap.sql("SELECT count(*) FROM fact_matches WHERE referee_key = 0").fetchone()[0]
        assert unknown >= 1, "no match with an unreported referee to exclude"

    def test_trap_4_both_event_facts_have_null_match_key_rows(self, snap):
        for table in ("fact_player_events", "fact_shots"):
            orphans = snap.sql(f"SELECT count(*) FROM {table} WHERE match_key IS NULL").fetchone()[
                0
            ]
            assert orphans >= 1, f"{table} has no NULL match_key row; inner joins look safe"

    def test_trap_5_seasons_straddle_the_august_cutoff(self, snap):
        seasons = snap.df(
            "SELECT season, min(match_date) lo, max(match_date) hi "
            "FROM fact_matches GROUP BY 1 ORDER BY 1"
        )
        assert seasons["season"].tolist() == ["2024/25", "2025/26"]
        # A 2025/26 match played in August 2025 is the case a naive
        # calendar-year derivation gets wrong.
        assert str(seasons.loc[seasons.season == "2025/26", "lo"].iloc[0]).startswith("2025-08")

    def test_trap_6_unfinished_matches_have_null_scores(self, snap):
        row = snap.df(
            "SELECT status, home_goals, away_goals FROM fact_matches WHERE status <> 'FINISHED'"
        )
        assert len(row) >= 1, "no unfinished match to filter out"
        assert row["home_goals"].isna().all()
        assert row["away_goals"].isna().all()

    def test_trap_7_a_finished_match_has_null_xg(self, snap):
        unpaired = snap.sql(
            "SELECT count(*) FROM fact_matches WHERE status = 'FINISHED' AND home_xg IS NULL"
        ).fetchone()[0]
        assert unpaired >= 1, "no NULL-xG match; COALESCE-to-zero bugs stay invisible"

    def test_trap_8_penalties_are_separable_in_the_shot_fact(self, snap):
        # There is no non-penalty xG per player, so npxG has to come from here.
        situations = {
            row[0] for row in snap.sql("SELECT DISTINCT situation FROM fact_shots").fetchall()
        }
        assert "Penalty" in situations
        assert situations - {"Penalty"}, "there must be non-penalty situations too"

    def test_trap_9_absent_columns_stay_absent(self, snap):
        stadiums = snap.df("SELECT city, capacity FROM dim_stadiums")
        assert stadiums["city"].isna().all(), "Gold has no source for city"
        assert stadiums["capacity"].isna().all(), "Gold has no source for capacity"

    def test_trap_10_penalties_sit_on_the_penalty_spot(self, snap):
        spot = snap.df(
            "SELECT avg(x) ax, avg(y) ay, count(*) n FROM fact_shots WHERE situation = 'Penalty'"
        )
        assert spot["n"].iloc[0] >= 1
        assert spot["ax"].iloc[0] == pytest.approx(0.885, abs=0.01)
        assert spot["ay"].iloc[0] == pytest.approx(0.5, abs=0.01)

    def test_trap_11_categoricals_hold_source_strings(self, snap):
        results = {row[0] for row in snap.sql("SELECT DISTINCT result FROM fact_shots").fetchall()}
        # Understat's spelling, including the odd plural. Never hardcode a list
        # without checking it against the snapshot first.
        assert "Goal" in results
        assert "MissedShots" in results

    def test_trap_13_one_fixture_exists_as_two_rows(self, snap):
        halves = snap.df(
            "SELECT football_data_match_id, understat_match_id, competition_code, result, home_xg "
            "FROM fact_matches WHERE home_team_key = 1 AND away_team_key = 4 "
            "AND match_date BETWEEN DATE '2025-08-30' AND DATE '2025-08-31' "
            "ORDER BY match_date"
        )

        assert len(halves) == 2, "the split fixture is missing"
        result_half, xg_half = halves.iloc[0], halves.iloc[1]
        # One half carries the result and no xG ...
        assert pd.notna(result_half["football_data_match_id"])
        assert pd.notna(result_half["result"])
        assert pd.isna(result_half["home_xg"])
        # ... the other carries the xG, with no result and no competition_code.
        assert pd.isna(xg_half["competition_code"])
        assert pd.isna(xg_half["result"])
        assert pd.notna(xg_half["home_xg"])

    def test_trap_13_counting_matches_needs_the_football_data_filter(self, snap):
        # Without the filter, the split fixture double-counts Arsenal's matches.
        unfiltered, filtered = snap.sql("""
            SELECT
              count(*) FILTER (WHERE true),
              count(*) FILTER (WHERE football_data_match_id IS NOT NULL)
            FROM fact_matches
            WHERE home_team_key = 1 OR away_team_key = 1
            """).fetchone()
        assert unfiltered == filtered + 1

    def test_trap_14_duplicate_shots_exist_under_different_ids(self, snap):
        dupes = snap.df("""
            SELECT match_key, player_key, minute, result, x, y, xg, count(*) n
            FROM fact_shots
            GROUP BY 1, 2, 3, 4, 5, 6, 7
            HAVING count(*) > 1
            """)
        assert len(dupes) >= 1, "no duplicated shots; double-counted xG stays invisible"
        assert (dupes["n"] == 2).all()


class TestFixtureIsInternallyConsistent:
    def test_shot_goals_agree_with_player_event_goals(self, snap):
        """A fixture that contradicts itself would teach the wrong lesson."""
        mismatch = snap.df("""
            WITH shots_dedup AS (
                SELECT DISTINCT match_key, player_key, minute, result, x, y, xg
                FROM fact_shots WHERE match_key IS NOT NULL
            ),
            from_shots AS (
                SELECT match_key, player_key, count(*) FILTER (WHERE result = 'Goal') goals
                FROM shots_dedup GROUP BY 1, 2
            )
            SELECT e.match_key, e.player_key, e.goals AS event_goals, s.goals AS shot_goals
            FROM fact_player_events e
            JOIN from_shots s USING (match_key, player_key)
            WHERE e.goals <> s.goals
            """)
        assert mismatch.empty, f"goals disagree between the facts:\n{mismatch}"

    def test_every_finished_match_has_a_result_consistent_with_its_score(self, snap):
        wrong = snap.df("""
            SELECT match_key, home_goals, away_goals, result FROM fact_matches
            WHERE status = 'FINISHED' AND result IS NOT NULL AND result <> CASE
                WHEN home_goals > away_goals THEN 'HOME_TEAM'
                WHEN away_goals > home_goals THEN 'AWAY_TEAM' ELSE 'DRAW' END
            """)
        assert wrong.empty, f"result does not match the score:\n{wrong}"

    def test_no_match_has_a_team_playing_itself(self, snap):
        assert (
            snap.sql(
                "SELECT count(*) FROM fact_matches WHERE home_team_key = away_team_key"
            ).fetchone()[0]
            == 0
        )

    def test_facts_only_reference_known_dimension_members(self, snap):
        for fact, column, dim, key in (
            ("fact_matches", "home_team_key", "dim_teams", "team_key"),
            ("fact_matches", "away_team_key", "dim_teams", "team_key"),
            ("fact_matches", "referee_key", "dim_referees", "referee_key"),
            ("fact_matches", "stadium_key", "dim_stadiums", "stadium_key"),
            ("fact_player_events", "player_key", "dim_players", "player_key"),
            ("fact_player_events", "team_key", "dim_teams", "team_key"),
            ("fact_shots", "player_key", "dim_players", "player_key"),
            ("fact_shots", "team_key", "dim_teams", "team_key"),
        ):
            orphans = snap.sql(
                f"SELECT count(*) FROM {fact} f LEFT JOIN {dim} d ON f.{column} = d.{key} "
                f"WHERE f.{column} IS NOT NULL AND d.{key} IS NULL"
            ).fetchone()[0]
            assert orphans == 0, f"{fact}.{column} points outside {dim}"

    def test_shot_xg_is_a_probability(self, snap):
        assert (
            snap.sql(
                "SELECT count(*) FROM fact_shots WHERE xg IS NOT NULL AND (xg < 0 OR xg > 1)"
            ).fetchone()[0]
            == 0
        )

    def test_shot_coordinates_are_normalized(self, snap):
        assert (
            snap.sql(
                "SELECT count(*) FROM fact_shots "
                "WHERE x IS NOT NULL AND (x < 0 OR x > 1 OR y < 0 OR y > 1)"
            ).fetchone()[0]
            == 0
        )


class TestGeneratorGuards:
    def test_unknown_column_is_rejected(self, tmp_path):
        """The generator must refuse a column the contract does not have."""
        import duckdb

        con = duckdb.connect(":memory:")
        columns = [gold.Column("team_key", "bigint", False)]

        with pytest.raises(SystemExit, match="not in the contract"):
            fixture_builder.write_table(
                con, "dim_teams", [{"team_key": 1, "tla": "ARS"}], columns, tmp_path
            )

    def test_double_round_robin_has_every_ordered_pair(self):
        pairs = fixture_builder.double_round_robin([1, 2, 3, 4])
        assert len(pairs) == 12
        assert len(set(pairs)) == 12
        assert all(h != a for h, a in pairs)
