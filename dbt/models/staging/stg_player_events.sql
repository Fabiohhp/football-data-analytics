-- One row per `gold.fact_player_events` row: one player's contribution to one
-- match. Renames, casts, and the one derivation staging is allowed (CLAUDE.md §4).
--
-- `season` is derived here from the row's **own** `match_date`, not by joining to
-- `stg_matches`. Two reasons, both from §5: only `fact_matches` carries `season`
-- (trap 5), and `match_key` is nullable (trap 4) — so a join for the season alone
-- would silently drop every player event Understat supplied before the
-- cross-source join matched its fixture. The `not_null` test on `season` is what
-- keeps that true: the CI fixture contains an orphan event on purpose, and it
-- would come back with a null season the moment this became a join.
--
-- `xg` here **includes penalties**; there is no non-penalty xG per player in Gold
-- (§5 trap 8). npxG has to be built from `fact_shots`.

select
    player_event_key,
    understat_match_id,
    understat_player_id,
    match_key,
    player_key,
    team_key,
    match_date,
    {{ season_label('match_date') }} as season,
    position,
    minutes_played,
    goals,
    own_goals,
    assists,
    shots,
    key_passes,
    cast(xg as double) as xg,
    cast(xa as double) as xa,
    cast(xg_chain as double) as xg_chain,
    cast(xg_buildup as double) as xg_buildup,
    yellow_cards,
    red_cards,
    loaded_at

from {{ source('gold', 'fact_player_events') }}
