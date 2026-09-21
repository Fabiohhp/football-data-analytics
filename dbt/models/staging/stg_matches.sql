-- One row per `gold.fact_matches` row: renames and casts, no filtering and no
-- business logic (CLAUDE.md §4).
--
-- In particular the two filters that decide which matches *count* towards a
-- league table live in `int_team_matches`, not here. This model deliberately
-- still holds the postponed fixture with its phantom 0-0 and both halves of every
-- duplicated fixture, so a test can count what the filters removed.

select
    match_key,
    football_data_match_id,
    understat_match_id,
    competition_code,
    competition_name,
    season,
    matchday,
    match_utc,
    match_date,
    status,
    home_team_key,
    away_team_key,
    referee_key,
    stadium_key,
    home_goals,
    away_goals,
    home_goals_ht,
    away_goals_ht,
    result,

    -- NUMERIC -> DOUBLE. Gold stores these as NUMERIC(8,4), which arrives as
    -- Python `Decimal` and refuses to arithmetic with floats in pandas.
    cast(home_xg as double) as home_xg,
    cast(away_xg as double) as away_xg,
    cast(home_npxg as double) as home_npxg,
    cast(away_npxg as double) as away_npxg,
    cast(home_ppda as double) as home_ppda,
    cast(away_ppda as double) as away_ppda,
    home_deep,
    away_deep,
    cast(home_xpts as double) as home_xpts,
    cast(away_xpts as double) as away_xpts,

    loaded_at

from {{ source('gold', 'fact_matches') }}
