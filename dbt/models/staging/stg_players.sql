-- One row per player **version**, from `gold.dim_players` (SCD Type 2).
--
-- Not one row per player. A player who changed clubs inside the loaded range has
-- several `player_key`s, so aggregating anything by `player_key` splits their
-- season in two: the durable key is `understat_player_id` (§5 trap 1). And a
-- player's club in a given match is `fact_player_events.team_key`, never
-- `current_team_key` here (§5 trap 2).
--
-- `valid_from` is a **first-seen date, not a transfer date.** Part 1 only ever
-- opens versions going forward, so a player's history starts at their first
-- appearance inside the loaded range — a `valid_from` in the snapshot's opening
-- weeks means "first seen then" and nothing more (CLAUDE.md §2).

select
    player_key,
    understat_player_id,
    player_name,
    position,
    current_team_key,
    valid_from,
    valid_to,
    is_current,
    loaded_at

from {{ source('gold', 'dim_players') }}
