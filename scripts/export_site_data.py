"""Write the JSON the static dashboard reads, from the dbt marts.

    uv run python scripts/export_site_data.py

**This script selects, filters, renames and rounds. It never aggregates.**
CLAUDE.md §4: a `GROUP BY` here is a missing mart. That is not left to discipline —
:func:`rows` refuses any table whose name does not begin with ``mart_``, and every
query is built from a table name plus a column list, so there is nowhere to put an
aggregate even by accident. The same rule is why the dashboard's JavaScript only
filters, sorts and formats: every number a reviewer could ask about is defined in
dbt and tested there.

The connection is **read-only**, like every other reader in this repository.

Output (``site/data/``, gitignored until CLAUDE.md §13 decides what may be
published):

    meta.json               snapshot range, export time, thresholds
    league_table.json       one row per club per league-season
    team/<team_key>.json    one club's match-by-match form
    players/<season>.json   one season's player leaderboard
    shots/<team_key>.json   one club's shots

Split per club and per season on purpose: the Team, Players and Shots pages each
show one of those at a time, and a single 94,000-row shots file would make a phone
download the whole dataset to draw one team's shot map.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from football_analytics import marts  # noqa: E402

SITE_DATA = REPO_ROOT / "site" / "data"


class NotAMartError(RuntimeError):
    """Raised when something tries to read outside the metrics layer."""


def rows(
    connection: Any,
    table: str,
    columns: dict[str, str],
    *,
    where: str | None = None,
    order_by: str | None = None,
) -> list[dict[str, Any]]:
    """Select display-ready rows from one mart.

    ``columns`` maps the JSON key onto a SQL expression, so renaming and rounding
    are visible in one place. The table name is checked rather than trusted: the
    dashboard may only ever show numbers that a tested dbt model defined.
    """
    if not table.startswith("mart_"):
        raise NotAMartError(
            f"{table!r} is not a mart. The dashboard reads marts only (CLAUDE.md §4) — "
            "if the number you need is not in one, the mart is missing."
        )

    projection = ",\n           ".join(f"{expr} AS {name}" for name, expr in columns.items())
    sql = f"SELECT {projection}\n    FROM {table}"
    if where:
        sql += f"\n    WHERE {where}"
    if order_by:
        sql += f"\n    ORDER BY {order_by}"

    frame = connection.df(sql)
    # NaN is not valid JSON and pandas produces it for a SQL NULL in a float column.
    # Nulls here are meaningful — a match with no xG, a rolling window with nothing
    # in it (§5 trap 7) — so they travel as JSON null and the pages check for them.
    return json.loads(frame.to_json(orient="records"))


def write_json(path: Path, payload: Any) -> int:
    """Write one JSON file, compactly, and return its size in bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def slug(season: str) -> str:
    """``'2024/25'`` -> ``'2024-25'``, so a season can be a filename."""
    return season.replace("/", "-")


# --- the exports -----------------------------------------------------------


def export_league_table(connection: Any) -> list[dict[str, Any]]:
    """One row per club per league-season: the League table page, and every picker.

    The other pages read this file too, for their league and season dropdowns —
    it is already one row per club per season, so no page has to group anything to
    build a list of clubs.
    """
    return rows(
        connection,
        "mart_team_season",
        {
            "team_key": "team_key",
            "team": "team_name",
            "league": "competition_code",
            "league_name": "competition_name",
            "season": "season",
            "position": "table_position",
            "played": "played",
            "won": "won",
            "drawn": "drawn",
            "lost": "lost",
            "gf": "goals_for",
            "ga": "goals_against",
            "gd": "goal_difference",
            "points": "points",
            "xpts": "round(xpts, 1)",
            # The honest gap: points counted over the matches that have an xPTS
            # (§5 trap 7). The mart does that; this only rounds it.
            "points_minus_xpts": "round(points_minus_xpts, 1)",
            # Rank and band are mart-computed readings of that gap, so the page can
            # say "widest of 20" and "well ahead" without deriving either.
            "points_minus_xpts_rank": "points_minus_xpts_rank",
            "xg_difference_rank": "xg_difference_rank",
            "clubs_in_league": "clubs_in_league",
            "gap_band": "gap_band",
            "xgd": "round(xg_difference, 1)",
            "xg_for": "round(xg_for, 1)",
            "xg_against": "round(xg_against, 1)",
            "ppda": "round(ppda, 2)",
            "matches_with_xg": "matches_with_xg",
            "matches_with_xpts": "matches_with_xpts",
            "season_complete": "is_season_complete",
        },
        order_by="season DESC, competition_code, table_position",
    )


def export_team_form(connection: Any, team_key: int) -> list[dict[str, Any]]:
    """One club's matches in order, with its rolling xG."""
    return rows(
        connection,
        "mart_team_form",
        {
            "season": "season",
            "league": "competition_code",
            "match_number": "match_number",
            "date": "cast(match_date AS VARCHAR)",
            "opponent": "opponent_name",
            "home": "is_home",
            "gf": "goals_for",
            "ga": "goals_against",
            "points": "points",
            "xg_for": "round(xg_for, 2)",
            "xg_against": "round(xg_against, 2)",
            "rolling_xg_for": "round(rolling_xg_for, 2)",
            "rolling_xg_against": "round(rolling_xg_against, 2)",
            "window_matches": "window_matches",
            "window_xg_matches": "window_xg_matches",
        },
        where=f"team_key = {team_key}",
        order_by="season, match_number",
    )


def export_players(connection: Any, season: str) -> list[dict[str, Any]]:
    """One season's players, for the per-90 leaderboard.

    Everyone is exported, not just those over the minutes floor, because the page
    has a minutes slider — pre-filtering here would silently cap how far down the
    reader could look. `meets_floor` travels with each row so the page can show the
    default threshold without knowing what it is.
    """
    return rows(
        connection,
        "mart_player_season",
        {
            "player": "player_name",
            "team": "primary_team_name",
            "team_key": "primary_team_key",
            "league": "competition_code",
            "clubs": "clubs",
            "matches": "matches",
            "minutes": "minutes",
            "goals": "goals",
            "assists": "assists",
            "np_goals": "np_goals",
            "npxg": "round(npxg, 1)",
            "xa": "round(xa, 1)",
            "shots": "shots",
            "np_goals_per_90": "round(np_goals_per_90, 2)",
            "npxg_per_90": "round(npxg_per_90, 2)",
            # The percentile is what makes a rate readable — "is 0.78 good?" — and it
            # is computed in the mart against a stated population, not here.
            "np_goals_per_90_pct": "np_goals_per_90_percentile",
            "npxg_per_90_pct": "npxg_per_90_percentile",
            "xa_per_90_pct": "xa_per_90_percentile",
            "shots_per_90_pct": "shots_per_90_percentile",
            "xa_per_90": "round(xa_per_90, 2)",
            "shots_per_90": "round(shots_per_90, 2)",
            # Finishing. The non-penalty version is the only one worth showing:
            # Understat's per-player xG includes penalties (§5 trap 8).
            "finishing": "round(np_goals_minus_npxg, 1)",
            "meets_floor": "meets_minutes_floor",
        },
        where=f"season = '{season}'",
        order_by="npxg DESC, player_name",
    )


def export_shots(connection: Any, team_key: int) -> list[dict[str, Any]]:
    """One club's shots, in Understat's [0, 1] coordinates.

    Coordinates are **not** rescaled (§5 trap 10) — the page's hand-drawn SVG pitch
    uses them as they are, oriented the same way as the notebooks' mplsoccer plots.
    Rounded to three places, which is finer than a pixel on any screen.
    """
    return rows(
        connection,
        "mart_shots",
        {
            "season": "season",
            "league": "competition_code",
            "date": "cast(match_date AS VARCHAR)",
            "player": "player_name",
            "minute": "minute",
            "x": "round(x, 3)",
            "y": "round(y, 3)",
            "xg": "round(xg, 3)",
            "result": "result",
            "situation": "situation",
            "body_part": "shot_type",
            "goal": "is_goal",
            "penalty": "is_penalty",
        },
        where=f"team_key = {team_key}",
        order_by="season, match_date, minute",
    )


def predictions_dir() -> Path:
    """Where Part 3's exported predictions are: ``PREDICTIONS_DIR``, or the sibling's.

    A relative override resolves against this repository's root, the same rule as
    ``GOLD_SNAPSHOT_DIR``. CI points it at ``tests/fixtures/predictions``, a synthetic
    copy, because Part 3 is not checked out there.
    """
    override = os.environ.get("PREDICTIONS_DIR")
    if not override:
        return (REPO_ROOT / ".." / "football-data-science" / "exports" / "predictions").resolve()
    path = Path(override).expanduser()
    return (path if path.is_absolute() else REPO_ROOT / path).resolve()


def copy_predictions() -> dict[str, int]:
    """Copy Part 3's predictions JSON into the site, unchanged.

    Part 3 (../football-data-science) fits the models, scores them and writes rows
    ready to display (its CLAUDE.md §9). Nothing is recomputed or reshaped here — the
    files are placed where the predictions page can fetch them. If Part 3 has not
    exported, the page says which command is missing instead of going blank.
    """
    source = predictions_dir()
    if not (source / "meta.json").exists():
        print(f"  predictions: none at {source} — the predictions page will say so")
        return {}
    target = SITE_DATA / "predictions"
    target.mkdir(parents=True, exist_ok=True)
    written = {}
    for path in sorted(source.glob("*.json")):
        shutil.copyfile(path, target / path.name)
        written[f"predictions/{path.name}"] = path.stat().st_size
    return written


def main() -> int:
    connection = marts.open_marts()
    manifest = connection.manifest

    # A clean rebuild: a club relegated out of the big five between snapshots would
    # otherwise leave a stale file behind for the pickers to point at.
    if SITE_DATA.exists():
        shutil.rmtree(SITE_DATA)
    SITE_DATA.mkdir(parents=True)

    written: dict[str, int] = {}

    table = export_league_table(connection)
    written["league_table.json"] = write_json(SITE_DATA / "league_table.json", table)

    # Clubs and seasons come from the league table itself, which is already one row
    # per club per season — so this is a projection, not an aggregation.
    club_keys = sorted({row["team_key"] for row in table})
    seasons = sorted({row["season"] for row in table}, reverse=True)

    for team_key in club_keys:
        written[f"team/{team_key}.json"] = write_json(
            SITE_DATA / "team" / f"{team_key}.json", export_team_form(connection, team_key)
        )
        written[f"shots/{team_key}.json"] = write_json(
            SITE_DATA / "shots" / f"{team_key}.json", export_shots(connection, team_key)
        )

    for season in seasons:
        written[f"players/{slug(season)}.json"] = write_json(
            SITE_DATA / "players" / f"{slug(season)}.json", export_players(connection, season)
        )

    # Every page shows the snapshot's match_date range (CLAUDE.md §9), and the
    # thresholds come from the marts rather than being retyped in JavaScript.
    thresholds = connection.df("SELECT max(min_minutes) AS min_minutes FROM mart_player_season")
    window = connection.df("SELECT max(form_window) AS form_window FROM mart_team_form")
    meta = {
        "exported_at": manifest["exported_at"],
        "match_date_range": manifest["match_date_range"],
        "counts": {name: spec["rows"] for name, spec in manifest["tables"].items()},
        "seasons": seasons,
        "min_minutes": int(thresholds.min_minutes.iloc[0]),
        "form_window": int(window.form_window.iloc[0]),
        "source": "Results from Football-Data.org, expected goals from Understat",
    }
    written["meta.json"] = write_json(SITE_DATA / "meta.json", meta)
    written.update(copy_predictions())

    total = sum(written.values())
    biggest = max(written.items(), key=lambda kv: kv[1])
    where = SITE_DATA.relative_to(REPO_ROOT)
    print(f"Wrote {len(written)} files to {where} ({total / 1e6:.2f} MB)")
    print(f"  clubs: {len(club_keys)}   seasons: {', '.join(seasons)}")
    print(f"  largest: {biggest[0]} ({biggest[1] / 1e3:.0f} kB)")
    print(f"  snapshot: {meta['match_date_range']['min']} to {meta['match_date_range']['max']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
