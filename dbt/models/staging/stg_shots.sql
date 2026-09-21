-- One row per `gold.fact_shots` row: renames and casts only.
--
-- No `season` column, unlike `stg_player_events`. `fact_shots` carries no date of
-- its own, so a season can only come from the match — and that is a join, which
-- is a reshape, which belongs in the intermediate layer rather than here
-- (CLAUDE.md §4). `mart_shots` attaches match, season and player in one place.
--
-- Two things this model does **not** do, both deliberate:
--   * it does not deduplicate. Understat returned every shot of two La Liga
--     matches twice under different shot ids (§5 trap 14), so 46 rows are
--     genuinely duplicated in Gold. Staging is 1:1 with Gold, and `mart_shots`
--     deduplicates on the *shape* of a shot — `(match_key, player_key, minute,
--     result, x, y, xg)` — because the ids differ and `distinct shot_key` would
--     not help.
--   * it does not normalize `result`, `situation` or `shot_type`. Those hold
--     source strings, tested against the measured vocabularies in schema.yml.
--     `MissedShots` really is plural, and `OwnGoal` really is a value of
--     `result` (§5 trap 11).

select
    shot_key,
    understat_shot_id,
    understat_match_id,
    match_key,
    player_key,
    team_key,
    assist_player_key,
    minute,
    is_home,

    -- Understat's normalized [0, 1] pitch coordinates. Higher `x` is closer to
    -- the goal being attacked; `y = 0.5` is the middle of the pitch (§5 trap 10).
    cast(x as double) as x,
    cast(y as double) as y,

    cast(xg as double) as xg,
    result,
    situation,
    shot_type,
    loaded_at

from {{ source('gold', 'fact_shots') }}
